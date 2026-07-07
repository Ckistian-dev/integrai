import subprocess
import os
import logging
import asyncio
import tempfile
import shutil
import glob
from datetime import datetime, timedelta
import pytz
from app.services.google_drive_service import get_drive_service
from app.core.config import settings

logger = logging.getLogger(__name__)

def find_pg_dump() -> str:
    """
    Encontra o caminho do executável pg_dump dinamicamente.
    Funciona tanto dentro do container Docker quanto localmente no Windows/Linux.
    """
    # 1. Verifica se foi configurado explicitamente no ambiente
    env_path = os.getenv("PG_DUMP_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
        
    # 2. Tenta encontrar no PATH (comum em Linux/Docker e Windows configurado)
    shutil_path = shutil.which("pg_dump")
    if shutil_path:
        return shutil_path
        
    # 3. Se estiver no Windows, procura nas pastas padrão do PostgreSQL
    if os.name == 'nt':
        default_paths = glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe")
        if default_paths:
            # Retorna a versão mais recente encontrada (última em ordem alfabética)
            latest_path = default_paths[-1]
            logger.info(f"Backup: pg_dump detectado no Windows em: {latest_path}")
            return latest_path
            
    # Caso padrão, tenta chamar diretamente pelo PATH
    return "pg_dump"

def perform_database_backup():
    """
    Executa o pg_dump do banco de dados e envia para a pasta configurada do Google Drive.
    """
    logger.info("Backup: Iniciando processo de backup do banco de dados...")
    
    # 1. Verificar se o serviço do Drive está ativo e configurado
    drive_service = get_drive_service()
    if not drive_service or not drive_service.service:
        logger.warning("Backup: Serviço Google Drive não foi inicializado. Verifique a variável GOOGLE_SERVICE_ACCOUNT_JSON no .env.")
        return

    # 2. Obter a URL do banco e adaptar para o pg_dump (remover driver se houver)
    if not settings.DATABASE_URL:
        logger.error("Backup: DATABASE_URL não configurada.")
        return
        
    db_url = str(settings.DATABASE_URL)
    # Remove qualquer driver do tipo postgresql+driver:// para que o pg_dump aceite a URI
    if "://" in db_url:
        scheme, rest = db_url.split("://", 1)
        if "+" in scheme:
            scheme = scheme.split("+")[0]
        db_url = f"{scheme}://{rest}"
    
    # Nome do arquivo de backup com data/hora formatada no horário de São Paulo
    sp_tz = pytz.timezone("America/Sao_Paulo")
    now = datetime.now(sp_tz)
    filename = f"backup_integrai_{now.strftime('%Y%m%d_%H%M%S')}.dump"
    
    # Cria o caminho temporário no diretório de temporários padrão do SO
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, filename)
    
    try:
        # Encontra o executável pg_dump
        pg_dump_cmd = find_pg_dump()
        logger.info(f"Backup: Usando pg_dump de: {pg_dump_cmd}")
        logger.info(f"Backup: Executando pg_dump para {temp_path}...")
        
        # Prepara variáveis de ambiente caso precise injetar a senha explicitamente
        env = os.environ.copy()
        if settings.POSTGRES_PASSWORD:
            env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
            
        # Executa o pg_dump usando formato customizado (-F c)
        result = subprocess.run(
            [pg_dump_cmd, "--dbname=" + db_url, "-F", "c", "-f", temp_path],
            capture_output=True,
            text=True,
            env=env
        )
        
        if result.returncode != 0:
            logger.error(f"Backup: Erro no pg_dump: {result.stderr}")
            raise Exception(f"pg_dump falhou com código {result.returncode}: {result.stderr}")
            
        logger.info(f"Backup: pg_dump concluído com sucesso. Tamanho: {os.path.getsize(temp_path)} bytes.")
        
        # 3. Ler os bytes do arquivo gerado
        with open(temp_path, "rb") as f:
            backup_bytes = f.read()
            
        # 4. Fazer upload para o Google Drive
        folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
        logger.info(f"Backup: Enviando backup '{filename}' para a pasta do Google Drive (ID: {folder_id})...")
        file_id = drive_service.upload_file(
            file_content_bytes=backup_bytes,
            file_name=filename,
            parent_folder_id=folder_id,
            mime_type="application/octet-stream"
        )
        logger.info(f"Backup: Backup enviado com sucesso! Google Drive File ID: {file_id}")
        
        # 5. Excluir backups com mais de 30 dias da mesma pasta
        logger.info("Backup: Verificando backups antigos para limpeza...")
        deleted = drive_service.delete_old_backups(folder_id=folder_id, days=30)
        if deleted:
            logger.info(f"Backup: {deleted} backup(s) com mais de 30 dias excluído(s) do Google Drive.")
        else:
            logger.info("Backup: Nenhum backup antigo encontrado para excluir.")
        
    except Exception as e:
        logger.error(f"Backup: Erro crítico durante o backup do banco de dados: {e}", exc_info=True)
    finally:
        # Remover o arquivo temporário
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info(f"Backup: Arquivo temporário {temp_path} removido.")
            except Exception as clean_ex:
                logger.warning(f"Backup: Não foi possível remover o arquivo temporário {temp_path}: {clean_ex}")

async def backup_scheduler_loop():
    """
    Loop que calcula o tempo restante até as 3h da madrugada (horário de Brasília)
    e executa o backup diariamente.
    """
    logger.info("Backup: Iniciando loop do agendador de backup...")
    sp_tz = pytz.timezone("America/Sao_Paulo")
    
    while True:
        try:
            # 1. Obter a hora atual no fuso horário de SP
            now_local = datetime.now(sp_tz)
            
            # 2. Definir o próximo horário de execução para hoje às 3:00 AM
            target_time = now_local.replace(hour=3, minute=0, second=0, microsecond=0)
            
            # 3. Se já passou das 3:00 AM hoje, agenda para amanhã às 3:00 AM
            if now_local >= target_time:
                target_time += timedelta(days=1)
                
            # 4. Calcular os segundos de espera
            sleep_seconds = (target_time - now_local).total_seconds()
            logger.info(f"Backup: Próximo backup agendado para {target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}. Aguardando {sleep_seconds:.1f} segundos...")
            
            # 5. Dormir até o horário de execução
            await asyncio.sleep(sleep_seconds)
            
            # 6. Executar o backup
            # Executamos a função síncrona de backup em um thread pool para evitar o bloqueio do loop principal do FastAPI
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, perform_database_backup)
            
        except asyncio.CancelledError:
            logger.info("Backup: Loop do agendador de backup cancelado.")
            break
        except Exception as e:
            logger.error(f"Backup: Erro no loop do agendador de backup: {e}", exc_info=True)
            # Em caso de erro inesperado, aguarda 1 minuto antes de tentar recalcular para evitar loop infinito rápido
            await asyncio.sleep(60)

backup_task = None

def start_backup_scheduler():
    """
    Inicia o agendador de backup como uma tarefa de segundo plano assíncrona.
    """
    global backup_task
    logger.info("Backup: Iniciando agendador de backup...")
    backup_task = asyncio.create_task(backup_scheduler_loop())
