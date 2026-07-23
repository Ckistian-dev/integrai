from fastapi import APIRouter

from app.api.v1.endpoints import auth, generic, metadata, dashboard, intelipost, mercadolivre, magento, nfe, tiktok, atendai

api_router = APIRouter()

# Inclui todos os roteadores da v1
api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(dashboard.router, tags=["Dashboard"])
api_router.include_router(metadata.router, tags=["Metadata"])
api_router.include_router(generic.router, tags=["Generic CRUD"])
api_router.include_router(intelipost.router, tags=["Intelipost"])
api_router.include_router(mercadolivre.router, tags=["Mercado Livre"])
api_router.include_router(magento.router, tags=["Magento Commerce"])
api_router.include_router(nfe.router, tags=["NFe / Faturamento"])
api_router.include_router(tiktok.router, tags=["Tiktok Shop"])
api_router.include_router(atendai.router, tags=["AtendAI"])