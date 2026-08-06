import json
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.crud import crud_user
from app.core.service.intelipost_service import IntelipostService

router = APIRouter()

security_basic = HTTPBasic()

def verify_intelipost_basic_auth(
    credentials: HTTPBasicCredentials = Depends(security_basic),
    db: Session = Depends(get_db)
) -> models.Usuario:
    print(f"\n[INTELIPOST WEBHOOK AUTH DEBUG] Credenciais recebidas -> Username: '{credentials.username}'")
    user = crud_user.authenticate_user(db, email=credentials.username, senha=credentials.password)
    if not user:
        print(f"[INTELIPOST WEBHOOK AUTH DEBUG] Autenticação FALHOU para '{credentials.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas para o Webhook Intelipost.",
            headers={"WWW-Authenticate": "Basic"}
        )
    print(f"[INTELIPOST WEBHOOK AUTH DEBUG] Autenticação BEM-SUCEDIDA! Usuário ID={user.id}, Empresa ID={user.id_empresa}")
    return user

class IntelipostFreteSelection(BaseModel):
    delivery_method_id: int
    final_shipping_cost: float
    delivery_method_name: str
    quote_id: Optional[int] = None
    prazo_entrega: Optional[int] = None

@router.post("/intelipost/webhook")
async def receber_webhook_intelipost(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(verify_intelipost_basic_auth)
):
    """
    Recebe atualizações de status via Webhook da Intelipost.
    Autenticação via HTTP Basic Auth.
    Imprime depurações detalhadas do payload no console.
    """
    print("\n" + "="*80)
    print(">>> [INTELIPOST WEBHOOK RECEBIDO] <<<")
    print(f"URL: {request.url}")
    print(f"HEADERS: {dict(request.headers)}")
    print("PAYLOAD BRUTO (JSON):")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("="*80)

    # 1. Extração do Status
    history = payload.get("history", {}) if isinstance(payload.get("history"), dict) else {}
    status_encontrado = (
        history.get("shipment_order_volume_state_localized") or
        history.get("shipment_order_volume_state_title") or
        history.get("shipment_order_volume_state_name") or
        history.get("shipment_order_volume_state") or
        payload.get("shipment_order_volume_state_localized") or
        payload.get("shipment_order_volume_state_title") or
        payload.get("order_status") or
        payload.get("status")
    )
    
    print(f"[DEBUG WEBHOOK] Status extraído do payload: '{status_encontrado}'")

    # 2. Identificação da Ordem / Pedido
    shipment_order_id = (
        payload.get("shipment_order_id") or 
        payload.get("db_id") or 
        history.get("shipment_order_id")
    )
    
    order_number = payload.get("order_number") or payload.get("sales_order_number")
    
    print(f"[DEBUG WEBHOOK] Identificadores extraídos -> shipment_order_id: '{shipment_order_id}', order_number: '{order_number}'")

    pedido = None

    # 1. Busca exatamente pelo id_pedido_intelipost registrado no ERP (ex: "VAR4535N")
    if order_number:
        pedido = db.query(models.Pedido).filter(
            models.Pedido.id_empresa == current_user.id_empresa,
            models.Pedido.id_pedido_intelipost == str(order_number)
        ).first()

    # 2. Se não encontrou por id_pedido_intelipost, busca pelo intelipost_id (ID da Ordem de Envio Intelipost)
    if not pedido and shipment_order_id:
        pedido = db.query(models.Pedido).filter(
            models.Pedido.id_empresa == current_user.id_empresa,
            models.Pedido.intelipost_id == str(shipment_order_id)
        ).first()

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

    # 3. Atualização do Pedido
    print(f"[DEBUG WEBHOOK SUCCESS] Pedido localizado! ID={pedido.id}, Status antigo='{pedido.status_intelipost}', Novo Status='{status_encontrado}'")
    
    if status_encontrado:
        pedido.status_intelipost = str(status_encontrado)
    
    if shipment_order_id and not pedido.intelipost_id:
        pedido.intelipost_id = str(shipment_order_id)
        
    if order_number and not pedido.id_pedido_intelipost:
        pedido.id_pedido_intelipost = str(order_number)

    db.commit()
    db.refresh(pedido)

    return {
        "status": "success",
        "message": "Webhook Intelipost processado e status atualizado com sucesso.",
        "pedido_id": pedido.id,
        "id_pedido_intelipost": pedido.id_pedido_intelipost,
        "status_intelipost": pedido.status_intelipost
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
        "id": transportadora.id,
        "nome_razao": transportadora.nome_razao
    }