import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# --- INÍCIO DAS MODIFICAÇÕES ---
# Importa sua Base e todos os seus modelos
# (Ajuste os caminhos se a sua estrutura for diferente)
from app.core.db.database import Base
from app.core.db import models # Isso importa todos os modelos

# Importa suas configurações para pegar a URL do banco
from app.core.config import settings 

# O Alembic precisa saber quais são seus modelos
target_metadata = Base.metadata

# Carrega a URL do banco das suas settings
# Pydantic (em settings) lê o .env sem problemas com '%'
DB_URL = settings.DATABASE_URL
# --- FIM DAS MODIFICAÇÕES ---

# Esta é a configuração do Alembic que lê o alembic.ini
config = context.config

# --- REMOVIDA A LINHA QUE CAUSA O ERRO ---
# config.set_main_option("sqlalchemy.url", DB_URL) 
# --- FIM DA REMOÇÃO ---

# Interpreta o arquivo de configuração para logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ... (Restante do arquivo) ...

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    ...
    """
    # --- MODIFICAÇÃO AQUI ---
    # Usa a URL lida diretamente das settings
    url = DB_URL 
    # --- FIM DA MODIFICAÇÃO ---
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    ...
    """
    
    # --- MODIFICAÇÃO AQUI ---
    # Pega a configuração base do alembic.ini
    db_config = config.get_section(config.config_ini_section, {})
    
    # Sobrescreve a URL com a nossa, que Pydantic leu corretamente
    db_config["sqlalchemy.url"] = DB_URL

    # Cria a conexão usando nosso dicionário modificado
    connectable = engine_from_config(
        db_config, # Usa o dicionário
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # --- FIM DA MODIFICAÇÃO ---

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

