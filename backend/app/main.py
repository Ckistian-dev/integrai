import os
import logging
from fastapi import FastAPI, Response, status
from app.api.v1.api import api_router as v1_router
from app.core.db.database import Base, engine
from app.api.v1.endpoints import nfe, dfe # Importa os endpoints
from fastapi.middleware.cors import CORSMiddleware
from app.services.backup_service import start_backup_scheduler

# Configuração de logging para exibir mensagens de DEBUG
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(title="ERP IntegraAI API")

# Obtém as origens do .env (separadas por vírgula) ou usa padrão local
origins_str = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
origins = [origin.strip() for origin in origins_str.split(",") if origin]

# Configuracão do CORS
app.add_middleware(
    CORSMiddleware,
    # Atualize para a origem do seu frontend (Vite geralmente usa 5173)
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclui o roteador da v1
app.include_router(v1_router, prefix="/api/v1")
# Inclui o roteador de NFe separadamente (ou adicione ao api_router se preferir)
app.include_router(nfe.router, prefix="/api/v1", tags=["NFe"])
app.include_router(dfe.router, prefix="/api/v1/dfe", tags=["DF-e"])

@app.on_event("startup")
def on_startup():
    """Cria as tabelas do banco de dados na inicialização."""
    Base.metadata.create_all(bind=engine)
    start_backup_scheduler()


@app.get("/")
def read_root():
    return {"message": "Bem-vindo à API do ERP IntegraAI"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)
