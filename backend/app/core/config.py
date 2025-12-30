from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, validator
from typing import Any, Dict, Optional

class Settings(BaseSettings):
    # Carrega as variáveis do .env
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_SERVER: str = "db" # Nome do serviço do DB no docker-compose.yml

    # Monta a URL de conexão do banco de dados dinamicamente
    DATABASE_URL: Optional[PostgresDsn] = None

    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+psycopg2", # Usar psycopg2, que está no requirements.txt
            username=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_SERVER"), # Conecta ao serviço 'db'
            path=f"{values.get('POSTGRES_DB') or ''}",
        )

    # Chave secreta para assinar os tokens JWT
    # Gere um com: openssl rand -hex 32
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 horas

    # Configuração para o Pydantic ler o arquivo .env (sintaxe Pydantic V2)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
