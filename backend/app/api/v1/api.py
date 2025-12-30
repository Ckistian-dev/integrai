from fastapi import APIRouter

from app.api.v1.endpoints import auth, generic, metadata

api_router = APIRouter()

# Inclui todos os roteadores da v1
api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(metadata.router, tags=["Metadata"])
api_router.include_router(generic.router, tags=["Generic CRUD"])
