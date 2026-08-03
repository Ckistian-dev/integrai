import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

def sync_database_schema(engine: Engine, base):
    """
    Inspeciona todas as tabelas registradas no SQLAlchemy Base.metadata.
    Se uma tabela já existe no banco de dados mas possui colunas no modelo SQLAlchemy
    que não existem na tabela física do PostgreSQL, adiciona essas colunas automaticamente.
    """
    logger.info("Iniciando verificação de colunas e sincronização do banco de dados...")
    
    try:
        # 1. Garante que novas tabelas (que ainda não existem) sejam criadas
        base.metadata.create_all(bind=engine)
        
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        
        with engine.begin() as conn:
            for table_name, table in base.metadata.tables.items():
                if table_name not in existing_tables:
                    continue
                
                # Obtém nomes das colunas físicas no banco de dados (em lowercase)
                existing_columns = {col["name"].lower() for col in inspector.get_columns(table_name)}
                
                for column in table.columns:
                    col_name = column.name
                    if col_name.lower() not in existing_columns:
                        logger.info(f"Coluna faltante detectada: '{table_name}.{col_name}'. Adicionando ao banco de dados...")
                        
                        try:
                            # Compila o tipo da coluna para a sintaxe do dialeto (PostgreSQL)
                            compiled_type = column.type.compile(engine.dialect)
                            
                            # SQL para adicionar a coluna
                            sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {compiled_type}'
                            
                            # Executa o ALTER TABLE
                            conn.execute(text(sql))
                            logger.info(f"Coluna '{table_name}.{col_name}' (Tipo: {compiled_type}) adicionada com sucesso.")
                        except Exception as col_err:
                            logger.error(f"Erro ao adicionar coluna '{table_name}.{col_name}': {col_err}")

        logger.info("Sincronização do esquema do banco de dados concluída com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao sincronizar esquema do banco de dados: {e}")
