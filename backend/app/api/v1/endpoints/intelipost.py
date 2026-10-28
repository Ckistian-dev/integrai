import json
import asyncio
import hashlib
import time
import anyio
import threading
from collections import OrderedDict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request, BackgroundTasks, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from typing import Optional, Dict, Any, Tuple
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.service.intelipost_service import IntelipostService
from app.core.logger import log_info, log_error, log_warning
from app.core.error_codes import IntelipostErrorCode, LogStatus

router = APIRouter()

security_basic = HTTPBasic(auto_error=False)

# ==============================================================================
# Controle de Deduplicação Exata de Payloads e Ocorrências Intelipost
# Regra: Só exclui se for 100% exatamente idêntica; caso contrário, processa sem perder nenhuma
# ==============================================================================
_PAYLOAD_LOCK = threading.Lock()
_RECENT_PAYLOAD_HASHES: Dict[str, float] = OrderedDict()  # hash -> timestamp
_IN_FLIGHT_PAYLOADS = set()
PAYLOAD_DEDUP_TTL = 300.0  # 5 minutos
MAX_PAYLOAD_CACHE_SIZE = 5000

def _calculate_payload_hash(payload: Any) -> str:
    """Gera hash canônico do payload JSON para detecção de requisições exatamente idênticas."""
    try:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        canonical = str(payload)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def _check_and_register_payload(payload_hash: str) -> bool:
    """
    Retorna True se for uma requisição com payload exatamente idêntico já em processamento
    ou recebida nos últimos minutos. Caso contrário, registra e retorna False.
    """
    now = time.time()
    with _PAYLOAD_LOCK:
        if payload_hash in _IN_FLIGHT_PAYLOADS:
            return True

        # Limpeza por TTL
        expired = [h for h, ts in _RECENT_PAYLOAD_HASHES.items() if (now - ts) > PAYLOAD_DEDUP_TTL]
        for h in expired:
            _RECENT_PAYLOAD_HASHES.pop(h, None)

        if payload_hash in _RECENT_PAYLOAD_HASHES:
            return True

        _IN_FLIGHT_PAYLOADS.add(payload_hash)
        return False

def _finish_payload(payload_hash: str):
    """Finaliza o processamento do payload e o armazena no histórico recente."""
    now = time.time()
    with _PAYLOAD_LOCK:
        _IN_FLIGHT_PAYLOADS.discard(payload_hash)
        _RECENT_PAYLOAD_HASHES[payload_hash] = now
        while len(_RECENT_PAYLOAD_HASHES) > MAX_PAYLOAD_CACHE_SIZE:
            _RECENT_PAYLOAD_HASHES.popitem(last=False)

def _normalize_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()

def _normalize_date_str(val: Any) -> str:
    if not val:
        return ""
    s = str(val).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return s

def _is_exact_duplicate_occurrence(new_entry: Dict[str, Any], existing_entry: Dict[str, Any]) -> bool:
    """
    Compara duas ocorrências e retorna True APENAS se todos os 8 atributos forem EXATAMENTE IDÊNTICOS.
    Se qualquer atributo for diferente (ex: status mudou, data mudou, mensagem mudou, tracking mudou),
    retorna False para que a ocorrência seja processada sem perder nenhuma atualização.
    """
    if not isinstance(existing_entry, dict):
        return False

    # 1. Status
    if _normalize_str(new_entry.get("status")) != _normalize_str(existing_entry.get("status")):
        return False

    # 2. State do volume
    if _normalize_str(new_entry.get("state")) != _normalize_str(existing_entry.get("state")):
        return False

    # 3. Micro State
    if _normalize_str(new_entry.get("micro_state")) != _normalize_str(existing_entry.get("micro_state")):
        return False

    # 4. Mensagem do provedor / transportadora
    if _normalize_str(new_entry.get("provider_message")) != _normalize_str(existing_entry.get("provider_message")):
        return False

    # 5. Data da ocorrência
    new_date = _normalize_date_str(new_entry.get("event_date"))
    old_date = _normalize_date_str(existing_entry.get("event_date"))
    if new_date != old_date:
        return False

    # 6. Código de rastreio
    if _normalize_str(new_entry.get("tracking_code")) != _normalize_str(existing_entry.get("tracking_code")):
        return False

    # 7. URL de rastreio
    if _normalize_str(new_entry.get("tracking_url")) != _normalize_str(existing_entry.get("tracking_url")):
        return False

    # 8. Número do volume
    if _normalize_str(new_entry.get("volume_number")) != _normalize_str(existing_entry.get("volume_number")):
        return False

    return True

# Limitação estrita de concorrência para tarefas em background (evita esgotar o connection pool do SQLAlchemy)
_MELI_SYNC_SEMAPHORE = asyncio.Semaphore(2)
_SHOPEE_SYNC_SEMAPHORE = asyncio.Semaphore(2)

# Controle de serialização por pedido e estado sincronizado
_ORDER_SYNC_LOCKS: Dict[Tuple[str, int], asyncio.Lock] = {}
_ORDER_LOCK_DICT_LOCK = asyncio.Lock()
_LAST_SYNCED_STATE: Dict[Tuple[str, int], Tuple[str, str, str]] = {}
_ACTIVE_SYNC_ORDERS = set()  # Mantido para retrocompatibilidade

async def _get_order_sync_lock(platform: str, pedido_id: int) -> asyncio.Lock:
    key = (platform, pedido_id)
    async with _ORDER_LOCK_DICT_LOCK:
        if key not in _ORDER_SYNC_LOCKS:
            _ORDER_SYNC_LOCKS[key] = asyncio.Lock()
        return _ORDER_SYNC_LOCKS[key]

async def _sync_meli_order_background(pedido_id: int, id_empresa: int, tracking_url: Optional[str] = None):
    order_lock = await _get_order_sync_lock("meli", pedido_id)
    async with order_lock:
        async with _MELI_SYNC_SEMAPHORE:
            from app.core.db.database import SessionLocal
            from app.core.service.meli_service import MeliService
            from app.core.db import models

            db_bg = SessionLocal()
            try:
                pedido = db_bg.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
                if not pedido:
                    return

                current_state = (
                    str(pedido.status_intelipost or "").strip(),
                    str(pedido.intelipost_tracking_code or "").strip(),
                    str(pedido.intelipost_tracking_url or "").strip()
                )
                state_key = ("meli", pedido_id)
                last_state = _LAST_SYNCED_STATE.get(state_key)

                # Só ignora se for EXATAMENTE IDÊNTICO ao que já foi sincronizado com sucesso
                if last_state == current_state:
                    print(f"[INTELIPOST BG] Pedido #{pedido_id} já sincronizado com ML exatamente com este estado {current_state}. Ignorando duplicata.")
                    return

                meli_svc = MeliService(db_bg, id_empresa)
                await meli_svc.update_meli_order_status(pedido)
                if tracking_url and not getattr(pedido, 'rastreio_enviado', False):
                    await meli_svc.send_meli_tracking_link(pedido, tracking_url)

                _LAST_SYNCED_STATE[state_key] = current_state
            except Exception as e:
                print(f"[INTELIPOST BG] Erro ao sincronizar status ML em background para pedido #{pedido_id}: {e}")
            finally:
                db_bg.close()

def _run_shopee_sync_sync(pedido_id: int, id_empresa: int, tracking_url: Optional[str] = None):
    from app.core.db.database import SessionLocal
    from app.core.service.shopee_service import ShopeeService
    from app.core.db import models

    db_bg = SessionLocal()
    try:
        pedido = db_bg.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
        if not pedido:
            return

        current_state = (
            str(pedido.status_intelipost or "").strip(),
            str(pedido.intelipost_tracking_code or "").strip(),
            str(pedido.intelipost_tracking_url or "").strip()
        )
        state_key = ("shopee", pedido_id)
        last_state = _LAST_SYNCED_STATE.get(state_key)

        # Só ignora se for EXATAMENTE IDÊNTICO ao que já foi sincronizado com sucesso
        if last_state == current_state:
            print(f"[INTELIPOST BG] Pedido #{pedido_id} já sincronizado com Shopee exatamente com este estado {current_state}. Ignorando duplicata.")
            return

        shopee_svc = ShopeeService(db_bg, id_empresa)
        shopee_svc.update_shopee_order_status(pedido)
        if tracking_url and not getattr(pedido, 'rastreio_enviado', False):
            shopee_svc.send_shopee_tracking_link(pedido, tracking_url)

        _LAST_SYNCED_STATE[state_key] = current_state
    except Exception as e:
        print(f"[INTELIPOST BG] Erro ao sincronizar Shopee em background para pedido #{pedido_id}: {e}")
    finally:
        db_bg.close()

async def _sync_shopee_order_background(pedido_id: int, id_empresa: int, tracking_url: Optional[str] = None):
    order_lock = await _get_order_sync_lock("shopee", pedido_id)
    async with order_lock:
        async with _SHOPEE_SYNC_SEMAPHORE:
            await anyio.to_thread.run_sync(_run_shopee_sync_sync, pedido_id, id_empresa, tracking_url)

class AuthCacheEntry:
    def __init__(self, user_id: int, id_empresa: int):
        self.id = user_id
        self.id_empresa = id_empresa
        self.created_at = time.time()

# Cache de autenticação HTTP Basic (evita sobrecarga de CPU por Bcrypt e queries redundantes em rajadas de webhooks)
_auth_cache: Dict[str, AuthCacheEntry] = {}
AUTH_CACHE_TTL = 300  # 5 minutos

def _get_auth_key(username: str, password: str) -> str:
    combined = f"{username}:{password}".encode('utf-8')
    return hashlib.sha256(combined).hexdigest()

def verify_intelipost_basic_auth(
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic),
    db: Session = Depends(get_db)
) -> Optional[Any]:
    if not credentials:
        print("[INTELIPOST WEBHOOK AUTH DEBUG] Nenhum cabeçalho de autenticação HTTP Basic recebido.")
        return None

    auth_key = _get_auth_key(credentials.username, credentials.password)
    cached = _auth_cache.get(auth_key)
    now = time.time()

    if cached and (now - cached.created_at) < AUTH_CACHE_TTL:
        return cached

    print(f"\n[INTELIPOST WEBHOOK AUTH DEBUG] Credenciais recebidas -> Username: '{credentials.username}'")
    user = crud_user.authenticate_user(db, email=credentials.username, senha=credentials.password)
    if not user:
        print(f"[INTELIPOST WEBHOOK AUTH DEBUG] Autenticação FALHOU para '{credentials.username}'")
        return None

    print(f"[INTELIPOST WEBHOOK AUTH DEBUG] Autenticação BEM-SUCEDIDA! Usuário ID={user.id}, Empresa ID={user.id_empresa}")
    entry = AuthCacheEntry(user.id, user.id_empresa)
    _auth_cache[auth_key] = entry
    return user

class IntelipostFreteSelection(BaseModel):
    delivery_method_id: int
    final_shipping_cost: float
    delivery_method_name: str
    quote_id: Optional[int] = None
    prazo_entrega: Optional[int] = None

@router.post("/intelipost/webhook")
@router.post("/intelipost/webhook/ocorrencias")
@router.post("/intelipost/webhook/{subpath:path}")
def receber_webhook_intelipost(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Optional[Any] = Depends(verify_intelipost_basic_auth),
    subpath: Optional[str] = None
):
    """
    Recebe atualizações de status via Webhook da Intelipost.
    Suporta rotas dinâmicas/aninhadas e rotas com parâmetros de ocorrências.
    Descarta duplicatas APENAS se forem 100% exatamente idênticas.
    Processa todas as atualizações sem perda de nenhuma ocorrência.
    """
    # 0. Deduplicação em nível de Payload JSON exato (rajadas/retries de rede)
    payload_hash = _calculate_payload_hash(payload)
    if _check_and_register_payload(payload_hash):
        print(f"[INTELIPOST WEBHOOK] Payload duplicado exatamente idêntico detectado (hash: {payload_hash[:12]}...). Ignorando duplicata.")
        return {
            "status": "success",
            "message": "Webhook duplicado exatamente idêntico ignorado com sucesso.",
            "duplicada_ignorada": True,
            "payload_hash": payload_hash
        }

    try:
        return _processar_webhook_intelipost(
            request=request,
            background_tasks=background_tasks,
            payload=payload,
            db=db,
            current_user=current_user,
            subpath=subpath
        )
    finally:
        _finish_payload(payload_hash)

def _processar_webhook_intelipost(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session,
    current_user: Optional[Any],
    subpath: Optional[str] = None
):
    print("\n" + "="*80)
    print(">>> [INTELIPOST WEBHOOK RECEBIDO] <<<")
    print(f"URL: {request.url}")
    if subpath:
        print(f"SUBPATH CAPTURADO: '{subpath}'")
    print(f"HEADERS: {dict(request.headers)}")
    print("PAYLOAD BRUTO (JSON):")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("="*80)

    # 1. Extração do Status e Micro Status
    history = payload.get("history", {}) if isinstance(payload.get("history"), dict) else {}
    micro_state = history.get("shipment_volume_micro_state", {}) if isinstance(history.get("shipment_volume_micro_state"), dict) else {}
    
    status_encontrado = (
        history.get("shipment_order_volume_state_localized") or
        history.get("shipment_order_volume_state_title") or
        history.get("shipment_order_volume_state_name") or
        micro_state.get("shipment_volume_state_localized") or
        micro_state.get("default_name") or
        micro_state.get("name") or
        history.get("shipment_order_volume_state") or
        payload.get("shipment_order_volume_state_localized") or
        payload.get("shipment_order_volume_state_title") or
        payload.get("order_status") or
        payload.get("status")
    )
    
    print(f"[DEBUG WEBHOOK] Status extraído do payload: '{status_encontrado}'")

    # 2. Extração de Informações Adicionais (Tracking, Mensagem, Datas, Invoice)
    tracking_code = (
        payload.get("tracking_code") or
        history.get("tracking_code") or
        history.get("shipment_order_volume_id")
    )
    if tracking_code is not None:
        tracking_code = str(tracking_code)

    tracking_url = payload.get("tracking_url") or history.get("tracking_url")

    provider_message = (
        history.get("provider_message") or
        history.get("esprinter_message") or
        micro_state.get("description") or
        history.get("shipment_order_volume_state_localized")
    )

    # Data da Ocorrência
    event_date_iso = history.get("event_date_iso") or history.get("created_iso")
    event_date_dt = None
    if event_date_iso:
        try:
            event_date_dt = datetime.fromisoformat(str(event_date_iso))
        except Exception:
            pass
    elif history.get("event_date"):
        try:
            event_date_dt = datetime.fromtimestamp(history["event_date"] / 1000.0)
        except Exception:
            pass

    # Data Estimada de Entrega
    estimated_delivery_dt = None
    est_del_obj = payload.get("estimated_delivery_date")
    if isinstance(est_del_obj, dict):
        client_est = est_del_obj.get("client", {})
        if isinstance(client_est, dict):
            est_iso = client_est.get("current_iso") or client_est.get("original_iso")
            if est_iso:
                try:
                    estimated_delivery_dt = datetime.fromisoformat(str(est_iso))
                except Exception:
                    pass
            elif client_est.get("current"):
                try:
                    estimated_delivery_dt = datetime.fromtimestamp(client_est["current"] / 1000.0)
                except Exception:
                    pass

    # Identificadores da Ordem / Pedido
    shipment_order_id = (
        payload.get("shipment_order_id") or 
        payload.get("db_id") or 
        history.get("shipment_order_id")
    )
    
    order_number = payload.get("order_number") or payload.get("sales_order_number")
    
    invoice_data = payload.get("invoice", {}) if isinstance(payload.get("invoice"), dict) else {}
    invoice_key = invoice_data.get("invoice_key")
    invoice_number = invoice_data.get("invoice_number")
    invoice_series = invoice_data.get("invoice_series")
    
    print(f"[DEBUG WEBHOOK] Identificadores extraídos -> shipment_order_id: '{shipment_order_id}', order_number: '{order_number}', invoice_key: '{invoice_key}'")

    id_empresa = current_user.id_empresa if current_user else None

    def find_pedido():
        def run_query(criterion):
            q = db.query(models.Pedido).filter(criterion)
            if id_empresa:
                q = q.filter(models.Pedido.id_empresa == id_empresa)
            return q.first()

        # 1. Se order_number informado (ex: "VAR3821N" ou "3821")
        if order_number:
            order_str = str(order_number).strip()
            # 1a. Busca direta por id_pedido_intelipost (indexado)
            res = run_query(models.Pedido.id_pedido_intelipost == order_str)
            if res:
                return res

            # 1b. Extrai dígitos (número do pedido ERP / id_sequencial, que possui índice composto com id_empresa)
            digits = "".join(filter(str.isdigit, order_str))
            if digits:
                val = int(digits)
                res = run_query(or_(models.Pedido.id_sequencial == val, models.Pedido.id == val))
                if res:
                    return res

        # 2. Busca por intelipost_id (indexado)
        if shipment_order_id:
            res = run_query(models.Pedido.intelipost_id == str(shipment_order_id).strip())
            if res:
                return res

        # 3. Busca por chave de acesso (chave_acesso já possui índice)
        if invoice_key:
            res = run_query(models.Pedido.chave_acesso == str(invoice_key).strip())
            if res:
                return res

        # 4. Busca por número da Nota Fiscal (indexado)
        if invoice_number:
            res = run_query(models.Pedido.numero_nf == str(invoice_number).strip())
            if res:
                return res

        return None

    pedido = find_pedido()

    if not pedido:
        print(f"[DEBUG WEBHOOK WARN] Pedido NÃO encontrado no banco de dados para os dados informados.")
        return {
            "status": "warning",
            "message": "Webhook recebido e logado, mas nenhum pedido correspondente foi localizado.",
            "order_number": order_number,
            "shipment_order_id": shipment_order_id,
            "status_intelipost": status_encontrado,
            "payload_recebido": payload
        }

    # 3. Ocorrência correspondente a este evento
    history_entry = {
        "status": str(status_encontrado) if status_encontrado else None,
        "state": history.get("shipment_order_volume_state"),
        "micro_state": micro_state.get("name") or micro_state.get("default_name"),
        "provider_message": str(provider_message) if provider_message else None,
        "event_date": str(event_date_iso) if event_date_iso else (event_date_dt.isoformat() if event_date_dt else None),
        "tracking_code": tracking_code,
        "tracking_url": str(tracking_url) if tracking_url else None,
        "volume_number": payload.get("volume_number"),
        "recebido_em": datetime.now().isoformat()
    }

    current_history = list(pedido.intelipost_historico) if isinstance(pedido.intelipost_historico, list) else []

    # 4. Verificação de Ocorrência Exatamente Idêntica no Histórico
    is_exact_duplicate_in_history = any(
        _is_exact_duplicate_occurrence(history_entry, existing)
        for existing in current_history
    )

    status_antigo = pedido.status_intelipost
    novo_status = str(status_encontrado) if status_encontrado else None
    status_mudou = bool(novo_status and novo_status != status_antigo)

    tracking_antigo_code = pedido.intelipost_tracking_code
    tracking_antigo_url = pedido.intelipost_tracking_url
    tracking_mudou = bool(
        (tracking_code and tracking_code != tracking_antigo_code) or
        (tracking_url and str(tracking_url) != str(tracking_antigo_url or ""))
    )

    # Só descarta se a ocorrência for EXATAMENTE IDÊNTICA a uma já existente E não houver alteração de status nem tracking no pedido
    if is_exact_duplicate_in_history and not status_mudou and not tracking_mudou:
        print(f"[DEBUG WEBHOOK] Ocorrência exatamente idêntica já presente no histórico do pedido #{pedido.id}. Ignorando duplicata.")
        return {
            "status": "success",
            "message": "Ocorrência exatamente idêntica já registrada no histórico do pedido. Ignorando duplicata.",
            "duplicada_ignorada": True,
            "pedido_id": pedido.id,
            "id_pedido_intelipost": pedido.id_pedido_intelipost,
            "status_intelipost": pedido.status_intelipost,
            "tracking_code": pedido.intelipost_tracking_code,
            "tracking_url": pedido.intelipost_tracking_url
        }

    # 5. Atualização do Pedido com Informações do Webhook (Processamento sem perda de dados)
    print(f"[DEBUG WEBHOOK SUCCESS] Pedido localizado! ID={pedido.id}, Status antigo='{status_antigo}', Novo Status='{novo_status}', Mudou={status_mudou}")
    
    if status_encontrado:
        pedido.status_intelipost = str(status_encontrado)
    
    if shipment_order_id:
        pedido.intelipost_id = str(shipment_order_id)
        
    if order_number:
        pedido.id_pedido_intelipost = str(order_number)

    if tracking_code:
        pedido.intelipost_tracking_code = tracking_code

    if tracking_url:
        pedido.intelipost_tracking_url = str(tracking_url)

    if provider_message:
        pedido.intelipost_mensagem = str(provider_message)

    if event_date_dt:
        pedido.intelipost_data_ocorrencia = event_date_dt

    if estimated_delivery_dt:
        pedido.intelipost_data_entrega_estimada = estimated_delivery_dt.date()
        if not pedido.data_entrega:
            pedido.data_entrega = estimated_delivery_dt.date()

    if invoice_key and not pedido.chave_acesso:
        pedido.chave_acesso = str(invoice_key)

    if invoice_number and not pedido.numero_nf:
        pedido.numero_nf = str(invoice_number)

    # Atualização de datas no Pedido (Despacho / Finalização)
    state_str = str(
        history.get("shipment_order_volume_state") or 
        micro_state.get("shipment_volume_state") or 
        status_encontrado or ""
    ).upper()

    ref_date = event_date_dt.date() if event_date_dt else datetime.now().date()

    if any(s in state_str for s in ["DELIVERED", "ENTREGUE"]):
        if not pedido.data_finalizacao:
            pedido.data_finalizacao = ref_date
    elif any(s in state_str for s in ["SHIPPED", "IN_TRANSIT", "TRANSITO", "DESPACHADO", "EM_TRANSITO"]):
        if not pedido.data_despacho:
            pedido.data_despacho = ref_date

    # Gravação no histórico apenas se a ocorrência não for duplicada
    if not is_exact_duplicate_in_history:
        current_history.append(history_entry)
        pedido.intelipost_historico = current_history
        flag_modified(pedido, "intelipost_historico")

    # Persiste alterações no banco e fecha a transação
    db.commit()

    empresa_id = id_empresa or pedido.id_empresa

    # 🎯 Sincronização automática de status com o Mercado Livre se for pedido ML
    is_ml_order = bool(
        getattr(pedido, 'meli_order_id', None) or
        getattr(pedido, 'meli_pack_id', None) or
        getattr(pedido, 'meli_shipment_id', None) or
        "mercado livre" in (pedido.origem_venda or "").lower() or
        "pedido ml:" in (pedido.observacao or "").lower() or
        "id ml:" in (pedido.observacao or "").lower()
    )

    # 🎯 Sincronização automática de status com a Shopee se for pedido Shopee
    is_shopee_order = bool(
        getattr(pedido, 'shopee_order_sn', None) or
        "shopee" in (pedido.origem_venda or "").lower() or
        "pedido shopee" in (pedido.observacao or "").lower()
    )

    # Resolução de link de rastreio para envio caso ainda não tenha sido transmitido
    meli_tracking_to_send = None
    shopee_tracking_to_send = None

    if (tracking_url or tracking_code) and not getattr(pedido, 'rastreio_enviado', False):
        if is_ml_order:
            meli_cfg = db.query(models.MeliConfiguracao.campo_link_rastreio).filter(
                models.MeliConfiguracao.id_empresa == empresa_id
            ).first()
            if meli_cfg and meli_cfg[0]:
                val_to_send = getattr(pedido, meli_cfg[0], None)
                if val_to_send:
                    meli_tracking_to_send = str(val_to_send).strip()

        if is_shopee_order:
            shopee_cfg = db.query(models.ShopeeConfiguracao.campo_link_rastreio).filter(
                models.ShopeeConfiguracao.id_empresa == empresa_id
            ).first()
            if shopee_cfg and shopee_cfg[0]:
                val_to_send = getattr(pedido, shopee_cfg[0], None)
                if val_to_send:
                    shopee_tracking_to_send = str(val_to_send).strip()

    # Só dispara rotinas de sincronização se houve mudança de status, de tracking ou link a ser transmitido
    should_sync = status_mudou or tracking_mudou or bool(meli_tracking_to_send or shopee_tracking_to_send)

    if should_sync:
        if is_ml_order:
            background_tasks.add_task(_sync_meli_order_background, pedido.id, empresa_id, meli_tracking_to_send)
        if is_shopee_order:
            background_tasks.add_task(_sync_shopee_order_background, pedido.id, empresa_id, shopee_tracking_to_send)

    return {
        "status": "success",
        "message": "Webhook Intelipost processado e dados atualizados com sucesso.",
        "pedido_id": pedido.id,
        "id_pedido_intelipost": pedido.id_pedido_intelipost,
        "status_intelipost": pedido.status_intelipost,
        "tracking_code": pedido.intelipost_tracking_code,
        "tracking_url": pedido.intelipost_tracking_url,
        "mensagem": pedido.intelipost_mensagem,
        "data_ocorrencia": pedido.intelipost_data_ocorrencia.isoformat() if pedido.intelipost_data_ocorrencia else None,
        "data_entrega_estimada": pedido.intelipost_data_entrega_estimada.isoformat() if pedido.intelipost_data_entrega_estimada else None
    }

@router.post("/intelipost/cotacao/{pedido_id}")
async def cotar_frete_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = IntelipostService(db, current_user.id_empresa)
    return await service.cotar_por_pedido(pedido_id)

@router.post("/intelipost/pedido_envio/{pedido_id}")
async def criar_pedido_envio_intelipost(
    pedido_id: int,
    dados: IntelipostFreteSelection,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = IntelipostService(db, current_user.id_empresa)
    return await service.criar_pedido_envio(pedido_id, dados.model_dump())

@router.get("/intelipost/transportadora/buscar")
def buscar_transportadora_por_nome(
    nome: str,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Busca uma transportadora no banco local pelo nome retornado da Intelipost (fuzzy search simples).
    """
    # Tenta achar contains (ILIKE)
    # Nota: Em produção idealmente usaria unaccent
    transportadora = db.query(models.Cadastro).filter(
        models.Cadastro.id_empresa == current_user.id_empresa,
        models.Cadastro.tipo_cadastro == 'transportadora',
        models.Cadastro.nome_razao.ilike(f"%{nome}%")
    ).first()
    
    if not transportadora:
         # Tenta pela fantasia
         transportadora = db.query(models.Cadastro).filter(
            models.Cadastro.id_empresa == current_user.id_empresa,
            models.Cadastro.tipo_cadastro == 'transportadora',
            models.Cadastro.fantasia.ilike(f"%{nome}%")
        ).first()

    if not transportadora:
        raise HTTPException(status_code=404, detail="Transportadora não encontrada no cadastro local.")

    return {
        "id": transportadora.id_sequencial if transportadora.id_sequencial is not None else transportadora.id,
        "nome_razao": transportadora.nome_razao
    }