"""
Serviço de Ciclo de Vida e Sincronização de Logs com o Google Drive.
Responsável por rotacionar os logs diariamente às 03:00 (horário de Brasília),
enviar arquivos .txt anteriores para o Google Drive, manter retenção de 30 dias na nuvem
e garantir que no disco local persista apenas o arquivo do dia corrente.
"""

import os
import glob
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pytz

from app.core.config import settings
from app.core.logger import (
    init_logging, close_logging, SP_TZ, DEFAULT_LOGS_DIR,
    log_info, log_error, log_warning
)
from app.core.error_codes import SystemErrorCode, LogStatus
from app.core.service.google_drive_service import get_drive_service

logger = logging.getLogger(__name__)

def rotate_and_sync_logs(logs_dir: Optional[str] = None, drive_service: Any = None) -> Dict[str, Any]:
    """
    Executa o ciclo de rotação:
    1. Localiza arquivos de log de dias anteriores.
    2. Envia para a pasta configurada do Google Drive.
    3. Exclui o arquivo anterior do disco local somente após upload confirmado.
    4. Purga logs com mais de 30 dias no Google Drive.
    5. Reinicia o handler local de log para o dia corrente.
    """
    target_dir = logs_dir or DEFAULT_LOGS_DIR
    os.makedirs(target_dir, exist_ok=True)
    
    svc = drive_service or get_drive_service()
    now_sp = datetime.now(SP_TZ)
    today_filename = f"integrai_logs_{now_sp.strftime('%Y-%m-%d')}.txt"
    today_filepath = os.path.join(target_dir, today_filename)

    uploaded_count = 0
    deleted_drive_count = 0
    errors = []

    # Fecha handlers para garantir flush completo e liberar o lock no Windows
    close_logging()

    try:
        # Encontra todos os arquivos de log no diretório
        pattern = os.path.join(target_dir, "integrai_logs_*.txt")
        found_files = glob.glob(pattern)

        for file_path in found_files:
            file_name = os.path.basename(file_path)
            # Ignora o arquivo do dia atual (ele permanece ativo localmente)
            if file_name == today_filename:
                continue

            try:
                if svc and hasattr(svc, "upload_file"):
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()

                    folder_id = getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)
                    log_info("SYSTEM", "log_service", "rotate_and_sync_logs", LogStatus.PROCESSING,
                             f"Enviando log {file_name} para o Google Drive...")
                    
                    file_id = svc.upload_file(
                        file_content_bytes=file_bytes,
                        file_name=file_name,
                        parent_folder_id=folder_id,
                        mime_type="text/plain"
                    )
                    uploaded_count += 1
                    log_info("SYSTEM", "log_service", "rotate_and_sync_logs", LogStatus.SUCCESS,
                             f"Log {file_name} enviado com sucesso ao Drive (ID: {file_id}).")

                    # Remove arquivo local com segurança após confirmação de upload
                    try:
                        os.remove(file_path)
                        log_info("SYSTEM", "log_service", "rotate_and_sync_logs", LogStatus.SUCCESS,
                                 f"Arquivo local anterior {file_name} removido do disco.")
                    except Exception as rm_err:
                        log_warning("SYSTEM", "log_service", "rotate_and_sync_logs", SystemErrorCode.FILE_IO_ERROR,
                                    f"Falha ao remover arquivo local {file_name}: {rm_err}")
                else:
                    log_warning("SYSTEM", "log_service", "rotate_and_sync_logs", SystemErrorCode.CONFIGURATION_MISSING,
                                "Serviço Google Drive não configurado ou indisponível. Arquivo local preservado.")
                    errors.append("Google Drive service unavailable")
            except Exception as up_err:
                log_error("SYSTEM", "log_service", "rotate_and_sync_logs", SystemErrorCode.DRIVE_UPLOAD_FAILED,
                          f"Falha ao enviar arquivo de log {file_name} para o Google Drive: {up_err}", exc=up_err)
                errors.append(str(up_err))

        # Purga no Google Drive logs anteriores a 30 dias
        if svc and hasattr(svc, "delete_old_files_by_prefix"):
            try:
                folder_id = getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)
                deleted_drive_count = svc.delete_old_files_by_prefix(
                    folder_id=folder_id,
                    prefix="integrai_logs_",
                    days=30
                )
                log_info("SYSTEM", "log_service", "rotate_and_sync_logs", LogStatus.SUCCESS,
                         f"Limpeza de logs no Drive concluída: {deleted_drive_count} arquivo(s) > 30 dias excluído(s).")
            except Exception as clean_err:
                log_error("SYSTEM", "log_service", "rotate_and_sync_logs", SystemErrorCode.DRIVE_CLEANUP_FAILED,
                          f"Erro ao purgar logs antigos do Google Drive: {clean_err}", exc=clean_err)
                errors.append(str(clean_err))

    finally:
        # Reconecta o handler de logging no arquivo do dia atual
        init_logging(target_dir)

    success = len(errors) == 0
    return {
        "success": success,
        "uploaded_files": uploaded_count,
        "deleted_drive_files": deleted_drive_count,
        "errors": errors
    }

async def log_scheduler_loop():
    """
    Loop que calcula o tempo restante até as 3h da madrugada (horário de Brasília)
    e executa a rotação e sincronização diariamente.
    """
    log_info("SYSTEM", "log_service", "log_scheduler_loop", LogStatus.PROCESSING,
             "Iniciando agendador de rotação diária de logs (03:00 AM)...")

    while True:
        try:
            now_local = datetime.now(SP_TZ)
            target_time = now_local.replace(hour=3, minute=0, second=0, microsecond=0)
            if now_local >= target_time:
                target_time += timedelta(days=1)

            sleep_seconds = (target_time - now_local).total_seconds()
            log_info("SYSTEM", "log_service", "log_scheduler_loop", LogStatus.PENDING,
                     f"Próxima rotação de logs agendada para {target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}. Aguardando {sleep_seconds:.1f}s.")

            await asyncio.sleep(sleep_seconds)

            # Executa a rotação síncrona em background executor
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, rotate_and_sync_logs)

        except asyncio.CancelledError:
            log_info("SYSTEM", "log_service", "log_scheduler_loop", LogStatus.SUCCESS,
                     "Loop do agendador de rotação de logs cancelado.")
            break
        except Exception as e:
            log_error("SYSTEM", "log_service", "log_scheduler_loop", SystemErrorCode.LOG_ROTATION_FAILED,
                      f"Erro no loop do agendador de logs: {e}", exc=e)
            await asyncio.sleep(60)

_log_task = None

def start_log_scheduler():
    """Inicia o agendador de logs em background."""
    global _log_task
    _log_task = asyncio.create_task(log_scheduler_loop())
    return _log_task
