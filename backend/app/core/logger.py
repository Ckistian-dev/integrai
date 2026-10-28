"""
Módulo Central de Logging Estruturado do ERP IntegraAI.
Fornece taxonomia hierárquica (Geral -> Específico com Código de Erro),
sanitização de dados sensíveis e gravação diária em arquivo .txt.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Any, Dict, Optional
import pytz

SENSITIVE_KEYS = {
    "password", "senha", "token", "access_token", "refresh_token",
    "secret", "client_secret", "client_id", "authorization",
    "cert_password", "senha_certificado", "private_key"
}

SP_TZ = pytz.timezone("America/Sao_Paulo")
DEFAULT_LOGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))

_current_file_handler: Optional[logging.FileHandler] = None
_current_log_date: Optional[str] = None
_configured_logs_dir: str = DEFAULT_LOGS_DIR

def sanitize_context(context: Any) -> Any:
    """Substitui recursivamente valores de campos sensíveis por [PROTEGIDO]."""
    if context is None:
        return {}
    if isinstance(context, dict):
        sanitized = {}
        for k, v in context.items():
            key_lower = str(k).lower()
            if any(sens in key_lower for sens in SENSITIVE_KEYS):
                sanitized[k] = "[PROTEGIDO]"
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_context(v)
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(context, list):
        return [sanitize_context(item) for item in context]
    return context

def format_context_str(context: Optional[Dict[str, Any]]) -> str:
    """Converte o contexto de metadados em string legível para o log."""
    if not context:
        return ""
    clean = sanitize_context(context)
    if isinstance(clean, dict):
        parts = [f"{k}: {v}" for k, v in clean.items()]
        return " | " + " | ".join(parts)
    return f" | Contexto: {clean}"

def format_log_line(
    level: str,
    modulo: str,
    submodulo: str,
    funcao: str,
    status_ou_codigo: str,
    mensagem: str,
    context: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None
) -> str:
    """Gera a linha de log estruturada no padrão [TIMESTAMP] [NÍVEL] [MÓDULO:SUBMÓDULO:FUNÇÃO] [CÓDIGO/STATUS] - Mensagem | Contexto."""
    if now is None:
        now = datetime.now(SP_TZ)
    time_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    ctx_str = format_context_str(context)
    return f"[{time_str}] [{level.upper()}] [{modulo}:{submodulo}:{funcao}] [{status_ou_codigo}] - {mensagem}{ctx_str}"

def get_current_log_filepath(logs_dir: Optional[str] = None) -> str:
    """Retorna o caminho absoluto do arquivo de log do dia corrente."""
    target_dir = logs_dir or _configured_logs_dir
    now = datetime.now(SP_TZ)
    filename = f"integrai_logs_{now.strftime('%Y-%m-%d')}.txt"
    return os.path.join(target_dir, filename)

def close_logging():
    """Fecha e desconecta todos os handlers de arquivo abertos."""
    global _current_file_handler
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        if isinstance(h, logging.FileHandler):
            h.flush()
            h.close()
            root_logger.removeHandler(h)
    _current_file_handler = None

def init_logging(logs_dir: Optional[str] = None, log_level: int = logging.INFO):
    """Inicializa os handlers do logging raiz (Console e Arquivo diário .txt)."""
    global _current_file_handler, _current_log_date, _configured_logs_dir

    if logs_dir:
        _configured_logs_dir = os.path.abspath(logs_dir)

    os.makedirs(_configured_logs_dir, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remover handlers antigos duplicados se houver
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. File Handler para o arquivo do dia
    now = datetime.now(SP_TZ)
    _current_log_date = now.strftime("%Y-%m-%d")
    log_filepath = get_current_log_filepath(_configured_logs_dir)
    
    file_handler = logging.FileHandler(log_filepath, encoding="utf-8", mode="a")
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    _current_file_handler = file_handler

def get_logger(name: str = "integrai") -> logging.Logger:
    """Retorna a instância do logger base."""
    return logging.getLogger(name)

def _emit_log(
    level_num: int,
    level_str: str,
    modulo: str,
    submodulo: str,
    funcao: str,
    codigo_ou_status: str,
    mensagem: str,
    exc: Optional[Exception] = None,
    context: Optional[Dict[str, Any]] = None
):
    """Emite a linha estruturada no logger raiz e cuida de traceback se fornecido."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        init_logging()

    # Se a data mudou durante o dia, atualiza o handler de arquivo
    global _current_file_handler, _current_log_date
    now = datetime.now(SP_TZ)
    today_str = now.strftime("%Y-%m-%d")
    if _current_log_date != today_str and _current_file_handler is not None:
        init_logging(_configured_logs_dir)

    line = format_log_line(level_str, modulo, submodulo, funcao, codigo_ou_status, mensagem, context, now=now)
    root_logger.log(level_num, line)
    
    if exc:
        root_logger.log(level_num, f"  -> Exceção capturada: {type(exc).__name__}: {str(exc)}", exc_info=exc)

def log_info(modulo: str, submodulo: str, funcao: str, status_ou_codigo: str, mensagem: str, context: Optional[Dict[str, Any]] = None):
    _emit_log(logging.INFO, "INFO", modulo, submodulo, funcao, status_ou_codigo, mensagem, context=context)

def log_warning(modulo: str, submodulo: str, funcao: str, codigo: str, mensagem: str, context: Optional[Dict[str, Any]] = None):
    _emit_log(logging.WARNING, "WARNING", modulo, submodulo, funcao, codigo, mensagem, context=context)

def log_error(modulo: str, submodulo: str, funcao: str, codigo: str, mensagem: str, exc: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None):
    _emit_log(logging.ERROR, "ERROR", modulo, submodulo, funcao, codigo, mensagem, exc=exc, context=context)

def log_critical(modulo: str, submodulo: str, funcao: str, codigo: str, mensagem: str, exc: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None):
    _emit_log(logging.CRITICAL, "CRITICAL", modulo, submodulo, funcao, codigo, mensagem, exc=exc, context=context)

def log_debug(modulo: str, submodulo: str, funcao: str, status_ou_codigo: str, mensagem: str, context: Optional[Dict[str, Any]] = None):
    _emit_log(logging.DEBUG, "DEBUG", modulo, submodulo, funcao, status_ou_codigo, mensagem, context=context)
