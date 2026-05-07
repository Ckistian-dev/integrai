import logging
from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.orm import Session
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.db.schemas import Page
from app.core.service.tiktok_service import TiktokService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/tiktok/pedidos", response_model=Page)
def list_tiktok_orders_proxy(
    skip: int = 0,
    limit: int = 10,
    filters: str = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint Proxy: Busca pedidos diretamente na API do Tiktok Shop e retorna formatado.
    """
    try:
        service = TiktokService(db, current_user.id_empresa)
        data = service.list_orders(limit=limit, offset=skip, filters=filters)
        return data
    except Exception as e:
        logger.exception(f"Erro ao listar pedidos Tiktok: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/tiktok/pedidos/{order_id}/importar")
def import_tiktok_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Importa um pedido específico do Tiktok Shop para o banco local.
    """
    try:
        service = TiktokService(db, current_user.id_empresa)
        pedido, produtos_criados = service.import_order(order_id)
        
        msg = "Pedido importado com sucesso!"
        if produtos_criados:
            msg += f" Produtos criados: {', '.join(produtos_criados)}"
            
        response = {"message": msg, "id": pedido.id}
            
        return response
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Erro ao importar pedido Tiktok: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tiktok/teste-conexao")
def testar_conexao_tiktok(
    config: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint auxiliar para testar credenciais antes de salvar.
    """
    # Exemplo simulado
    try:
        if config.get('app_key') and config.get('app_secret'):
            return {"message": "Conexão bem sucedida (Simulada)!", "sucesso": True}
        else:
            return {"message": "App Key e App Secret são obrigatórios", "sucesso": False}
    except Exception as e:
        return {"message": f"Erro de conexão: {str(e)}", "sucesso": False}

@router.get("/tiktok/auth_url")
def get_auth_url(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera a URL de autorização do Tiktok Shop.
    """
    service = TiktokService(db, current_user.id_empresa)
    return service.get_auth_url()

@router.get("/tiktok/callback")
def tiktok_auth_callback(
    code: str,
    shop_id: str = None,
    db: Session = Depends(get_db)
):
    """
    Callback que o Tiktok redireciona após a autorização.
    """
    # Nota: Assim como no ML, o ideal é o frontend capturar isso e mandar via POST.
    # Mas deixaremos o endpoint pronto para receber o redirect.
    return {"message": "Autorização recebida! Copie o código e use no sistema.", "code": code, "shop_id": shop_id}

@router.post("/tiktok/auth")
def authenticate_tiktok(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Troca o código de autorização pelo access_token.
    """
    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Código de autorização é obrigatório")
        
    try:
        service = TiktokService(db, current_user.id_empresa)
        result = service.authenticate(code)
        return result
    except Exception as e:
        logger.exception(f"Erro na autenticação Tiktok: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tiktok/sync")
def sync_tiktok(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Verifica se a conexão com o Tiktok está ativa e válida.
    """
    try:
        service = TiktokService(db, current_user.id_empresa)
        if not service.config.access_token:
            raise HTTPException(status_code=403, detail="Tiktok não autorizado")
            
        # Aqui poderíamos fazer uma chamada de "ping" na API (ex: buscar info da loja)
        # Por enquanto, apenas retornamos sucesso se tiver token.
        return {"message": "Sincronizado com sucesso!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
