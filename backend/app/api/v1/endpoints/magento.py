import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.db.schemas import Page
from app.core.service.magento_service import MagentoService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/magento/pedidos", response_model=Page)
def list_magento_orders_proxy(
    skip: int = 0,
    limit: int = 10,
    filters: str = None,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint Proxy: Busca pedidos diretamente na API do Magento com cache inteligente.
    """
    try:
        service = MagentoService(db, current_user.id_empresa)
        data = service.list_orders(limit=limit, offset=skip, filters=filters, force_refresh=refresh)
        return data
    except Exception as e:
        logger.exception(f"Erro ao listar pedidos Magento: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/magento/sync")
def sync_magento_connection(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Força atualização da lista de pedidos do Magento limpando o cache em memória.
    """
    try:
        MagentoService.clear_cache(current_user.id_empresa)
        return {"message": "Sincronização com Magento concluída com sucesso!"}
    except Exception as e:
        logger.exception(f"Erro ao sincronizar Magento: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/magento/pedidos/{entity_id}/importar")
def import_magento_order(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Importa um pedido específico do Magento para o banco local.
    """
    try:
        service = MagentoService(db, current_user.id_empresa)
        pedido, produtos_criados = service.import_order(entity_id)
        
        msg = "Pedido importado com sucesso!"
        if produtos_criados:
            msg += f" Produtos criados: {', '.join(produtos_criados)}"
            
        response = {"message": msg, "id": pedido.id}
        
        if hasattr(pedido, 'import_warning'):
            response['warning'] = getattr(pedido, 'import_warning')
            
        return response
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Erro ao importar pedido Magento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/magento/teste-conexao")
def testar_conexao_magento(
    config: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint auxiliar para testar credenciais antes de salvar.
    """
    # Cria uma instância temporária do serviço (ou usa httpx direto) para validar
    import requests
    from requests_oauthlib import OAuth1
    from oauthlib.oauth1 import SIGNATURE_HMAC_SHA256
    
    base_url = config.get('base_url', '').rstrip('/')
    if not base_url.startswith('http'):
        base_url = f"https://{base_url}"
    
    url = f"{base_url}/rest/{config.get('store_view_code', 'default')}/V1/store/storeViews"
    
    auth = OAuth1(
        config.get('consumer_key'),
        client_secret=config.get('consumer_secret'),
        resource_owner_key=config.get('access_token'),
        resource_owner_secret=config.get('token_secret'),
        signature_method=SIGNATURE_HMAC_SHA256
    )
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        resp = requests.get(url, auth=auth, headers=headers, timeout=5.0)
        if resp.status_code == 200:
            return {"message": "Conexão bem sucedida!", "sucesso": True}
        else:
            return {"message": f"Falha: {resp.status_code} - {resp.text}", "sucesso": False}
    except Exception as e:
        return {"message": f"Erro de conexão: {str(e)}", "sucesso": False}