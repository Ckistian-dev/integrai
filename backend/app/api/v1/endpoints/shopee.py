import logging
from fastapi import APIRouter, Depends, Body, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.db.schemas import Page
from app.core.service.shopee_service import ShopeeService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/shopee/pedidos", response_model=Page)
def list_shopee_orders_proxy(
    skip: int = 0,
    limit: int = 10,
    filters: str = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint Proxy: Busca pedidos diretamente na API da Shopee e retorna formatado.
    """
    try:
        service = ShopeeService(db, current_user.id_empresa)
        data = service.list_orders(limit=limit, offset=skip, filters=filters)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao listar pedidos Shopee: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/shopee/pedidos/{order_sn}/importar")
def import_shopee_order(
    order_sn: str,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Importa um pedido específico da Shopee para o banco local.
    """
    try:
        service = ShopeeService(db, current_user.id_empresa)
        pedido, produtos_criados = service.import_order(order_sn)
        
        msg = "Pedido importado com sucesso!"
        if produtos_criados:
            msg += f" Produtos criados: {', '.join(produtos_criados)}"
            
        response = {"message": msg, "id": pedido.id}
        return response
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Erro ao importar pedido Shopee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/shopee/teste-conexao")
def testar_conexao_shopee(
    config: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint auxiliar para testar credenciais antes de salvar.
    """
    try:
        partner_id = config.get('partner_id')
        partner_key = config.get('partner_key')
        
        if partner_id and partner_key:
            return {"message": "Credenciais validadas! Conclua a autorização para conectar a loja.", "sucesso": True}
        else:
            return {"message": "Partner ID e Partner Key são obrigatórios", "sucesso": False}
    except Exception as e:
        return {"message": f"Erro ao testar conexão: {str(e)}", "sucesso": False}

@router.get("/shopee/auth_url")
def get_auth_url(
    redirect_uri: str = Query(None),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera a URL de autorização da Shopee.
    """
    try:
        service = ShopeeService(db, current_user.id_empresa)
        return service.get_auth_url(redirect_uri=redirect_uri)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao gerar auth_url Shopee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/shopee/callback")
def shopee_auth_callback(
    code: str = Query(None),
    shop_id: str = Query(None),
    db: Session = Depends(get_db)
):
    """
    Callback redirecionado pela Shopee após o aceite do usuário.
    """
    return {"message": "Autorização Shopee recebida!", "code": code, "shop_id": shop_id}

@router.post("/shopee/auth")
def authenticate_shopee(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Troca o código de autorização e shop_id pelo access_token.
    """
    code = payload.get("code")
    shop_id = payload.get("shop_id")

    if not code:
        raise HTTPException(status_code=400, detail="Código de autorização é obrigatório.")
    if not shop_id:
        raise HTTPException(status_code=400, detail="Shop ID é obrigatório.")
        
    try:
        service = ShopeeService(db, current_user.id_empresa)
        result = service.authenticate(code=code, shop_id=str(shop_id))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro na autenticação Shopee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/shopee/sync")
def sync_shopee(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Verifica se a conexão com a Shopee está ativa e renova tokens se necessário.
    """
    try:
        service = ShopeeService(db, current_user.id_empresa)
        token = service._get_valid_access_token()
        if not token:
            raise HTTPException(status_code=403, detail="Shopee não autorizada.")
        return {"message": "Conexão com a Shopee sincronizada com sucesso!"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao sincronizar conexão Shopee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/shopee/connection")
def disconnect_shopee(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Remove os tokens de conexão da Shopee.
    """
    try:
        service = ShopeeService(db, current_user.id_empresa)
        service.disconnect()
        return {"message": "Conexão com a Shopee desfeita com sucesso!"}
    except Exception as e:
        logger.exception(f"Erro ao desconectar Shopee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/shopee/pedidos/{pedido_id}/enviar-xml")
def reenviar_xml_shopee(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Re-envia o XML/NFe de um pedido para a Shopee.
    """
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        models.Pedido.id_sequencial == pedido_id
    ).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    if not pedido.shopee_order_sn:
        raise HTTPException(status_code=400, detail="Este pedido não possui ID da Shopee (shopee_order_sn).")

    if not pedido.xml_autorizado:
        raise HTTPException(status_code=400, detail="Este pedido não possui XML da NFe autorizado no ERP.")

    service = ShopeeService(db, current_user.id_empresa)
    res = service.upload_xml(
        order_sn=pedido.shopee_order_sn,
        xml_content=pedido.xml_autorizado,
        chave_acesso=pedido.chave_acesso,
        numero_nf=pedido.numero_nf
    )

    return {"success": True, "message": "XML transmitido para a Shopee com sucesso!", "details": res}
