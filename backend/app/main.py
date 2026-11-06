import os
import logging
from fastapi import FastAPI, Response, status, Request
from fastapi.responses import JSONResponse
from app.api.v1.api import api_router as v1_router
from app.core.db.database import Base, engine
import app.core.db.models as models
from app.api.v1.endpoints import nfe, dfe # Importa os endpoints
from fastapi.middleware.cors import CORSMiddleware
from app.core.service.backup_service import start_backup_scheduler
from app.core.service.log_service import start_log_scheduler
from app.core.logger import init_logging, log_error, log_info
from app.core.error_codes import SystemErrorCode, LogStatus

# Inicializa o subsistema de logs estruturados e rotação diária
init_logging()

app = FastAPI(title="ERP IntegraAI API")

# Obtém as origens do .env (separadas por vírgula) ou usa padrão local
origins_str = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
origins = [origin.strip() for origin in origins_str.split(",") if origin]

# Configuracão do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de cabeçalhos de segurança (OWASP Top 10 Hardening)
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Middleware global para interceptar exceções não tratadas e registrar com código de erro estruturado
@app.middleware("http")
async def global_exception_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        log_error(
            "SYSTEM",
            "api",
            "global_exception_middleware",
            SystemErrorCode.UNHANDLED_EXCEPTION,
            f"Exceção não tratada capturada no endpoint {request.method} {request.url.path}: {str(exc)}",
            exc=exc,
            context={"path": request.url.path, "method": request.method}
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno do servidor. O incidente foi registrado para auditoria."}
        )

# Inclui o roteador da v1
app.include_router(v1_router, prefix="/api/v1")
# Inclui o roteador de NFe separadamente (ou adicione ao api_router se preferir)
app.include_router(nfe.router, prefix="/api/v1", tags=["NFe"])
app.include_router(dfe.router, prefix="/api/v1/dfe", tags=["DF-e"])

from app.core.db.sync import sync_database_schema

@app.on_event("startup")
def on_startup():
    """Cria e sincroniza colunas do banco de dados na inicialização."""
    sync_database_schema(engine, Base)
    start_backup_scheduler()
    start_log_scheduler()


@app.get("/")
def read_root():
    return {"message": "Bem-vindo à API do ERP IntegraAI"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)
