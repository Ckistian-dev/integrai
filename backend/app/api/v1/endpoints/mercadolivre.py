import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Any
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.service.meli_service import MeliService
from app.core.db.schemas import Page, ModelMetadata, FieldMetadata
from fastapi.responses import RedirectResponse
router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/mercadolivre/pedidos", response_model=Page)
async def list_ml_orders_proxy(
    skip: int = 0,
    limit: int = 10,
    filters: str = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint que imita o /generic/list mas busca dados da API do Mercado Livre.
    """
    try:
        logger.info(f"Requisição recebida: list_ml_orders_proxy | Empresa: {current_user.id_empresa} | Skip: {skip} | Limit: {limit}")
        service = MeliService(db, current_user.id_empresa)
        data = await service.list_orders(limit=limit, offset=skip)
        
        # Aplica filtros avançados localmente (se houver)
        if filters and data.get('items'):
            try:
                filter_list = json.loads(filters)
                
                if filter_list:
                    filtered_items = []
                    
                    for item in data['items']:
                        match = True
                        for f in filter_list:
                            field = f.get("field")
                            operator = f.get("operator")
                            value = str(f.get("value", "")).lower()
                            
                            item_val = str(item.get(field, "")).lower()
                            
                            if operator == "contains":
                                if value not in item_val: match = False
                            elif operator == "equals":
                                if item_val != value: match = False
                            elif operator == "starts_with":
                                if not item_val.startswith(value): match = False
                            elif operator == "ends_with":
                                if not item_val.endswith(value): match = False
                            elif operator == "neq":
                                if item_val == value: match = False
                            elif operator == "is_true":
                                if not item.get(field): match = False
                            elif operator == "is_false":
                                if item.get(field): match = False
                            # Operadores numéricos simples (gt, lt) podem ser adicionados convertendo para float se necessário
                            
                            if not match:
                                break
                        
                        if match:
                            filtered_items.append(item)
                    
                    data['items'] = filtered_items
                    data['total_count'] = len(filtered_items) # Atualiza contagem visual
            except json.JSONDecodeError:
                pass

        logger.info(f"Sucesso ao listar pedidos ML. Retornando {len(data.get('items', []))} itens de um total de {data.get('total_count', 0)}")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao listar pedidos ML para empresa {current_user.id_empresa}")
        raise e

@router.post("/mercadolivre/sync")
async def sync_ml_connection(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    try:
        service = MeliService(db, current_user.id_empresa)
        await service.force_refresh_token()
        return {"message": "Conexão com Mercado Livre sincronizada com sucesso!"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao sincronizar conexão ML para empresa {current_user.id_empresa}")
        raise e

@router.delete("/mercadolivre/connection")
async def disconnect_ml_connection(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Remove as credenciais de conexão com o Mercado Livre, forçando um novo login.
    """
    try:
        service = MeliService(db, current_user.id_empresa)
        service.disconnect()
        return {"message": "Desconectado com sucesso! Realize o login novamente."}
    except Exception as e:
        logger.exception(f"Erro ao desconectar ML para empresa {current_user.id_empresa}")
        raise e

@router.post("/mercadolivre/pedidos/{order_id}/importar")
async def import_ml_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    try:
        service = MeliService(db, current_user.id_empresa)
        pedido = await service.import_order(order_id)
        return {"message": "Pedido importado com sucesso!", "id": pedido.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao importar pedido {order_id} para empresa {current_user.id_empresa}")
        raise e

@router.get("/mercadolivre/auth_url")
async def get_auth_url(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = MeliService(db, current_user.id_empresa)
    return await service.get_auth_url()


@router.get("/mercadolivre/callback")
async def meli_auth_callback(
    code: str = Query(...),
    state: str = Query(None), # Opcional por enquanto
    db: Session = Depends(get_db),
    # Nota: Callbacks do ML não enviam token JWT do seu sistema, 
    # então aqui não usamos Depends(get_current_active_user) diretamente se for um redirect do browser.
    # Precisamos de uma estratégia para identificar a empresa (ex: state contendo id_empresa criptografado).
    # SIMPLIFICAÇÃO: Vamos assumir que o usuário está logado no front e o front captura o code e manda para outro endpoint, 
    # OU passamos o id_empresa hardcoded no state para este exemplo.
):
    """
    Callback que o Mercado Livre redireciona. 
    Idealmente, o front recebe isso e chama o backend, mas se for direto:
    """
    # Para simplificar a integração com seu GenericList, recomendo que a Redirect URI 
    # aponte para uma rota do seu FRONTEND (ex: /mercadolivre/callback).
    # O Frontend pega o `code` da URL e chama um endpoint POST autenticado do backend.
    
    return {"message": "Por favor, configure o Redirect URI para o Frontend ou use o endpoint POST /auth com o code."}

@router.post("/mercadolivre/auth")
async def exchange_code(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    code = payload.get("code")
    code_verifier = payload.get("code_verifier")
    
    if not code:
        raise HTTPException(status_code=400, detail="Code obrigatório")
    
    # Se você iniciou o fluxo com PKCE, o verifier é OBRIGATÓRIO aqui
    if not code_verifier:
        logger.error(f"Erro: code_verifier não enviado para a empresa {current_user.id_empresa}")
        raise HTTPException(status_code=400, detail="code_verifier é obrigatório para o fluxo PKCE.")
        
    try:
        service = MeliService(db, current_user.id_empresa)
        result = await service.authenticate(code, code_verifier)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro na autenticação ML para empresa {current_user.id_empresa}")
        raise e


@router.post("/mercadolivre/pedidos/{pedido_id}/enviar-xml")
async def reenviar_xml_ml(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Envia ou re-envia o XML da NFe autorizada de um pedido para o Mercado Livre.
    Funciona para qualquer modalidade de frete (Mercado Envios e outras transportadoras).
    """
    import re
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id == pedido_id,
        models.Pedido.id_empresa == current_user.id_empresa
    ).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    if not pedido.xml_autorizado:
        raise HTTPException(status_code=400, detail="Este pedido não possui XML da NFe autorizado no ERP.")

    # 1. Prioridade: novos campos dedicados
    order_id_ml = pedido.meli_order_id or pedido.meli_pack_id

    # 2. Fallback: regex na observação
    if not order_id_ml:
        obs = pedido.observacao or ""
        match_pack = re.search(r"Pedido ML:\s*(\d+)", obs)
        if match_pack:
            order_id_ml = match_pack.group(1)
        else:
            match_id = re.search(r"ID:\s*(\d+)", obs)
            order_id_ml = match_id.group(1) if match_id else None

    if not order_id_ml:
        raise HTTPException(status_code=400, detail="Não foi localizado um ID do Mercado Livre na observação nem nos campos do pedido.")

    service = MeliService(db, current_user.id_empresa)
    res = await service.upload_xml(
        order_id_ml=order_id_ml,
        xml_content=pedido.xml_autorizado,
        chave_acesso=pedido.chave_acesso,
        numero_nf=pedido.numero_nf
    )

    if res and isinstance(res, dict) and res.get('status') in ['success', 'already_sent', 'warning']:
        pedido.meli_xml_enviado = True
        db.commit()
        msg = "XML já constava no Mercado Livre!" if res.get('status') == 'already_sent' else "XML enviado com sucesso ao Mercado Livre!"
        return {"success": True, "message": res.get("message") or msg, "details": res}
    else:
        err_msg = res.get('message') if isinstance(res, dict) and res.get('message') else "Erro ao enviar XML ao Mercado Livre."
        return {"success": False, "message": err_msg, "details": res}