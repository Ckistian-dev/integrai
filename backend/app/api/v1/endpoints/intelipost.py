import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request, BackgroundTasks, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.crud import crud_user
from app.core.service.intelipost_service import IntelipostService

router = APIRouter()

security_basic = HTTPBasic(auto_error=False)

async def _sync_meli_status_background(pedido_id: int, id_empresa: int):
    from app.core.db.database import SessionLocal
    from app.core.service.meli_service import MeliService
    from app.core.db import models
    
    db_bg = SessionLocal()
    try:
        pedido = db_bg.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
        if pedido:
            meli_svc = MeliService(db_bg, id_empresa)
            await meli_svc.update_meli_order_status(pedido)
    except Exception as e:
        print(f"[INTELIPOST BG] Erro ao sincronizar status ML em background para pedido #{pedido_id}: {e}")
    finally:
        db_bg.close()

def _sync_shopee_status_background(pedido_id: int, id_empresa: int):
    from app.core.db.database import SessionLocal
    from app.core.service.shopee_service import ShopeeService
    from app.core.db import models
    
    db_bg = SessionLocal()
    try:
        pedido = db_bg.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
        if pedido:
            shopee_svc = ShopeeService(db_bg, id_empresa)
            shopee_svc.update_shopee_order_status(pedido)
    except Exception as e:
        print(f"[INTELIPOST BG] Erro ao sincronizar status Shopee em background para pedido #{pedido_id}: {e}")
    finally:
        db_bg.close()

def verify_intelipost_basic_auth(
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic),
    db: Session = Depends(get_db)
) -> Optional[models.Usuario]:
    if not credentials:
        print("[INTELIPOST WEBHOOK AUTH DEBUG] Nenhum cabeçalho de autenticação HTTP Basic recebido.")
        return None
    print(f"\n[INTELIPOST WEBHOOK AUTH DEBUG] Credenciais recebidas -> Username: '{credentials.username}'")
    user = crud_user.authenticate_user(db, email=credentials.username, senha=credentials.password)
    if not user:
        print(f"[INTELIPOST WEBHOOK AUTH DEBUG] Autenticação FALHOU para '{credentials.username}'")
        return None
    print(f"[INTELIPOST WEBHOOK AUTH DEBUG] Autenticação BEM-SUCEDIDA! Usuário ID={user.id}, Empresa ID={user.id_empresa}")
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
async def receber_webhook_intelipost(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Optional[models.Usuario] = Depends(verify_intelipost_basic_auth),
    subpath: Optional[str] = None
):
    """
    Recebe atualizações de status via Webhook da Intelipost.
    Suporta rotas dinâmicas/aninhadas e rotas com parâmetros de ocorrências.
    """
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

        # 1. Busca por id_pedido_intelipost exato (ex: "VAR3821N" ou "VAR3316N")
        if order_number:
            res = run_query(models.Pedido.id_pedido_intelipost == str(order_number))
            if res: return res

        # 2. Busca por intelipost_id (ID da ordem na Intelipost)
        if shipment_order_id:
            res = run_query(models.Pedido.intelipost_id == str(shipment_order_id))
            if res: return res

        # 3. Busca por chave de acesso da NFe (invoice_key)
        if invoice_key:
            res = run_query(models.Pedido.chave_acesso == str(invoice_key))
            if res: return res

        # 4. Busca por número da Nota Fiscal (invoice_number / numero_nf)
        if invoice_number:
            res = run_query(models.Pedido.numero_nf == str(invoice_number))
            if res: return res

        # 5. Busca por id_sequencial ou id extraído do order_number (ex: "VAR3316N" -> 3316)
        if order_number:
            if str(order_number).isdigit():
                val = int(order_number)
                res = run_query(or_(models.Pedido.id_sequencial == val, models.Pedido.id == val))
                if res: return res

            digits = "".join(filter(str.isdigit, str(order_number)))
            if digits:
                val = int(digits)
                res = run_query(or_(models.Pedido.id_sequencial == val, models.Pedido.id == val))
                if res: return res

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

    # 3. Atualização do Pedido com Informações do Webhook
    print(f"[DEBUG WEBHOOK SUCCESS] Pedido localizado! ID={pedido.id}, Status antigo='{pedido.status_intelipost}', Novo Status='{status_encontrado}'")
    
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

    # Gravação do Histórico de Ocorrências (JSON)
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
    current_history.append(history_entry)
    pedido.intelipost_historico = current_history
    flag_modified(pedido, "intelipost_historico")

    db.commit()
    db.refresh(pedido)

    # 🎯 Sincronização automática de status com o Mercado Livre se for pedido ML
    is_ml_order = bool(
        getattr(pedido, 'meli_order_id', None) or 
        getattr(pedido, 'meli_pack_id', None) or 
        getattr(pedido, 'meli_shipment_id', None) or
        "mercado livre" in (pedido.origem_venda or "").lower() or
        "pedido ml:" in (pedido.observacao or "").lower() or
        "id ml:" in (pedido.observacao or "").lower()
    )
    if is_ml_order:
        empresa_id = id_empresa or pedido.id_empresa
        background_tasks.add_task(_sync_meli_status_background, pedido.id, empresa_id)

    # 🎯 Sincronização automática de status com a Shopee se for pedido Shopee
    is_shopee_order = bool(
        getattr(pedido, 'shopee_order_sn', None) or
        "shopee" in (pedido.origem_venda or "").lower() or
        "pedido shopee" in (pedido.observacao or "").lower()
    )
    if is_shopee_order:
        empresa_id = id_empresa or pedido.id_empresa
        background_tasks.add_task(_sync_shopee_status_background, pedido.id, empresa_id)

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