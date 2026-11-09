import logging
import json
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Any, Optional, Dict, List
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.service.meli_service import MeliService
from app.core.db.schemas import Page, ModelMetadata, FieldMetadata
from app.core.logger import log_info, log_error, log_warning
from app.core.error_codes import MeliErrorCode, LogStatus
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
        log_info("MELI", "meli_endpoint", "list_ml_orders_proxy", LogStatus.PROCESSING,
                 f"Requisição recebida: list_ml_orders_proxy (skip={skip}, limit={limit})",
                 {"id_empresa": current_user.id_empresa, "skip": skip, "limit": limit})
        service = MeliService(db, current_user.id_empresa)
        data = await service.list_orders(limit=limit, offset=skip)
        log_info("MELI", "meli_endpoint", "list_ml_orders_proxy", LogStatus.SUCCESS,
                 "Pedidos Mercado Livre listados com sucesso", {"id_empresa": current_user.id_empresa})
        
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
    empresa_id = current_user.id_empresa
    try:
        service = MeliService(db, empresa_id)
        service.disconnect()
        return {"message": "Desconectado com sucesso! Realize o login novamente."}
    except Exception as e:
        db.rollback()
        logger.exception(f"Erro ao desconectar ML para empresa {empresa_id}")
        raise e

@router.post("/mercadolivre/pedidos/{order_id}/importar")
async def import_ml_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    empresa_id = current_user.id_empresa
    try:
        service = MeliService(db, empresa_id)
        pedido = await service.import_order(order_id)
        return {"message": "Pedido importado com sucesso!", "id": pedido.id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Erro ao importar pedido {order_id} para empresa {empresa_id}")
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

@router.post("/mercadolivre/callback")
async def meli_notification_callback(
    payload: dict = Body(None),
    db: Session = Depends(get_db)
):
    """
    Recebe notificações (Webhooks) do Mercado Livre e atualiza os pedidos locais.
    """
    logger.info(f"Notificação (Webhook) recebida do Mercado Livre: {payload}")
    if not payload or not isinstance(payload, dict):
        return {"status": "ok", "message": "Payload vazio"}

    topic = payload.get("topic")
    resource = payload.get("resource")
    user_id_ml = payload.get("user_id")
    app_id = payload.get("application_id")

    if not resource:
        return {"status": "ok", "message": "Sem resource"}

    # Identifica a empresa correspondente às credenciais / app_id
    id_empresa = None
    if user_id_ml:
        cred = db.query(models.MeliCredentials).filter(models.MeliCredentials.user_id_ml == int(user_id_ml)).first()
        if cred:
            id_empresa = cred.id_empresa

    if not id_empresa and app_id:
        cfg = db.query(models.MeliConfiguracao).filter(models.MeliConfiguracao.app_id == str(app_id)).first()
        if cfg:
            id_empresa = cfg.id_empresa

    if not id_empresa:
        logger.warning(f"Webhook ML rejeitado por segurança: nenhuma empresa correspondente para user_id={user_id_ml}, app_id={app_id}")
        return {"status": "warning", "message": "Empresa não identificada"}

    if not id_empresa:
        logger.warning(f"Webhook ML recebido mas nenhuma empresa correspondente foi encontrada para user_id={user_id_ml}, app_id={app_id}")
        return {"status": "warning", "message": "Empresa não identificada"}

    try:
        service = MeliService(db, id_empresa)
        result = await service.process_meli_webhook(topic=str(topic or ""), resource=str(resource), user_id_ml=user_id_ml)
        return result
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(f"Timeout/falha de rede transitória ao processar webhook ML ({topic}, {resource}): {e}")
        return {"status": "timeout_warning", "message": str(e)}
    except Exception as e:
        logger.exception(f"Erro ao processar webhook do Mercado Livre: {e}")
        return {"status": "error", "message": str(e)}

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
        models.Pedido.id_empresa == current_user.id_empresa,
        models.Pedido.id_sequencial == pedido_id
    ).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    if not pedido.xml_autorizado:
        raise HTTPException(status_code=400, detail="Este pedido não possui XML da NFe autorizado no ERP.")

    # 1. Campos dedicados do pedido
    order_id_ml = pedido.meli_pack_id or pedido.meli_order_id or pedido.meli_shipment_id

    if not order_id_ml:
        raise HTTPException(status_code=400, detail="Não foi localizado um ID do Mercado Livre (meli_order_id / meli_pack_id) nos campos do pedido.")

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


@router.post("/mercadolivre/pedidos/{pedido_id}/atualizar-status")
async def atualizar_status_pedido_ml(
    pedido_id: int,
    target_status: str = Query(None, description="Status alvo opcional (ex: shipped, delivered, handling)"),
    tracking_url: Optional[str] = Query(None, description="Link de rastreio opcional"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Sincroniza e força a atualização de status do envio no Mercado Livre para um pedido do ERP.
    """
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        (models.Pedido.id_sequencial == pedido_id) | (models.Pedido.id == pedido_id)
    ).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    service = MeliService(db, current_user.id_empresa)
    success = await service.update_meli_order_status(pedido, target_status=target_status, is_manual=True)
    return {
        "success": success,
        "message": f"Status atualizado para '{target_status or pedido.meli_status_envio}' no Mercado Livre com sucesso!" if success else "Não foi possível atualizar o status no Mercado Livre.",
        "status_envio": pedido.meli_status_envio,
        "historico": pedido.meli_historico
    }


@router.post("/mercadolivre/pedidos/{pedido_id}/confirmar-entrega")
async def confirmar_entrega_pedido_meli(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Confirma expressamente a entrega de um pedido ME1 no Mercado Livre (status 'delivered').
    """
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        (models.Pedido.id_sequencial == pedido_id) | (models.Pedido.id == pedido_id)
    ).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    service = MeliService(db, current_user.id_empresa)
    success = await service.update_meli_order_status(pedido, target_status="delivered", is_manual=True)
    return {
        "success": success,
        "message": "Entrega confirmada no Mercado Livre com sucesso!" if success else "Não foi possível confirmar a entrega no Mercado Livre.",
        "status_envio": pedido.meli_status_envio,
        "historico": pedido.meli_historico
    }


@router.post("/mercadolivre/pedidos/confirmar-entrega-por-ml-id/{order_id_ml}")
async def confirmar_entrega_por_ml_id(
    order_id_ml: str,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Confirma a entrega de um envio ME1 diretamente pelo ID do Mercado Livre (order_id, pack_id ou shipment_id),
    atualizando tanto o Mercado Livre quanto o pedido local no ERP caso localizado.
    """
    service = MeliService(db, current_user.id_empresa)
    clean_id = str(order_id_ml).strip()
    
    # Tenta localizar o pedido correspondente no ERP
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        (models.Pedido.meli_order_id.ilike(f"%{clean_id}%")) |
        (models.Pedido.meli_pack_id.ilike(f"%{clean_id}%")) |
        (models.Pedido.meli_shipment_id == clean_id) |
        (models.Pedido.observacao.ilike(f"%{clean_id}%"))
    ).first()

    if pedido:
        success = await service.update_meli_order_status(pedido, target_status="delivered", is_manual=True)
    else:
        success = await service.update_shipment_status_by_order(
            order_id_ml=clean_id,
            erp_status="Entregue",
            target_ml_status="delivered"
        )

    return {
        "success": success,
        "message": f"Entrega do pedido ML #{clean_id} confirmada com sucesso!" if success else f"Falha ao confirmar entrega do pedido ML #{clean_id}.",
        "pedido_id": getattr(pedido, 'id', None),
        "status_envio": getattr(pedido, 'meli_status_envio', 'delivered' if success else None)
    }


@router.post("/mercadolivre/pedidos/sincronizar-entregas-pendentes")
async def sincronizar_entregas_pendentes_meli(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Varre todos os pedidos da empresa que são do Mercado Livre e já constam como Entregue/Finalizado
    ou status_intelipost='DELIVERED'/'Entregue', mas ainda não foram finalizados como 'delivered' no Mercado Livre.
    """
    service = MeliService(db, current_user.id_empresa)
    from sqlalchemy import or_

    pedidos = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        or_(
            models.Pedido.meli_order_id.isnot(None),
            models.Pedido.meli_pack_id.isnot(None),
            models.Pedido.meli_shipment_id.isnot(None),
            models.Pedido.origem_venda.ilike("%mercado livre%"),
            models.Pedido.observacao.ilike("%pedido ml%")
        ),
        or_(
            models.Pedido.situacao.in_([models.PedidoSituacaoEnum.entregue]),
            models.Pedido.status_intelipost.ilike("%delivered%"),
            models.Pedido.status_intelipost.ilike("%entregue%")
        ),
        or_(
            models.Pedido.meli_status_envio.is_(None),
            ~models.Pedido.meli_status_envio.ilike("%delivered%")
        )
    ).all()

    results = []
    for ped in pedidos:
        try:
            ok = await service.update_meli_order_status(ped, target_status="delivered", is_manual=True)
            results.append({
                "pedido_id": ped.id,
                "id_sequencial": ped.id_sequencial,
                "meli_order_id": ped.meli_order_id,
                "success": ok
            })
        except Exception as e:
            results.append({
                "pedido_id": ped.id,
                "id_sequencial": ped.id_sequencial,
                "success": False,
                "error": str(e)
            })

    total_success = sum(1 for r in results if r.get("success"))
    return {
        "total_encontrados": len(pedidos),
        "total_atualizados": total_success,
        "detalhes": results
    }


@router.post("/mercadolivre/pedidos/{pedido_id}/enviar-rastreio")
async def enviar_rastreio_pedido_meli(
    pedido_id: int,
    tracking_url: Optional[str] = Query(None, description="Link ou código de rastreio opcional"),
    force: bool = Query(False, description="Forçar reenvio do link de rastreio mesmo se já enviado"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Envia o link / código de rastreamento do pedido para o Mercado Livre via API de shipments e mensageria pós-venda.
    """
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        (models.Pedido.id_sequencial == pedido_id) | (models.Pedido.id == pedido_id)
    ).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    if getattr(pedido, 'rastreio_enviado', False) and not force:
        return {
            "status": "skipped",
            "message": "Link de rastreio já foi enviado anteriormente para este pedido.",
            "rastreio_enviado": True
        }

    val_to_send = tracking_url
    if not val_to_send:
        meli_cfg = db.query(models.MeliConfiguracao.campo_link_rastreio).filter(
            models.MeliConfiguracao.id_empresa == current_user.id_empresa
        ).first()
        if meli_cfg and meli_cfg[0]:
            val_to_send = getattr(pedido, meli_cfg[0], None)

    service = MeliService(db, current_user.id_empresa)
    res = await service.send_meli_tracking_link(pedido, tracking_url=val_to_send, force=force)
    return res