"""
Módulo de Defesa e Segurança Centralizada do ERP Talatto (OWASP Top 10 Hardening).
Implementa proteções contra SSRF, XXE, BOLA, vazamento de segredos e controle de acesso RBAC.
"""

import io
import ipaddress
import urllib.parse
import urllib.request
import logging
from typing import Optional, Any, Dict, List
from lxml import etree
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. PROTEÇÃO ANTI-SSRF (Server-Side Request Forgery)
# ==============================================================================

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback IPv4
    ipaddress.ip_network("10.0.0.0/8"),       # Privada Classe A
    ipaddress.ip_network("172.16.0.0/12"),    # Privada Classe B
    ipaddress.ip_network("192.168.0.0/16"),   # Privada Classe C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("0.0.0.0/8"),        # Rede atual
    ipaddress.ip_network("::1/128"),          # Loopback IPv6
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA privada
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]

def is_safe_external_url(url: str) -> bool:
    """
    Valida se a URL fornecida é estritamente HTTP/HTTPS público.
    Bloqueia schemes perigosos (file://, gopher://, ftp://) e IPs privados/loopback/cloud metadata.
    """
    if not url or not isinstance(url, str):
        return False

    url_clean = url.strip()
    try:
        parsed = urllib.parse.urlparse(url_clean)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            logger.warning(f"[ANTI-SSRF] Esquema inválido bloqueado: {scheme} em {url_clean}")
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower()
        blocked_hostnames = {
            "localhost", "127.0.0.1", "::1", "metadata.google.internal",
            "instance-data", "169.254.169.254"
        }
        if hostname_lower in blocked_hostnames or hostname_lower.endswith(".internal") or hostname_lower.endswith(".local"):
            logger.warning(f"[ANTI-SSRF] Hostname bloqueado: {hostname_lower}")
            return False

        # Verifica se hostname é IP numérico em rede privada
        try:
            ip = ipaddress.ip_address(hostname)
            for net in BLOCKED_IP_NETWORKS:
                if ip in net:
                    logger.warning(f"[ANTI-SSRF] IP privado/loopback bloqueado: {ip}")
                    return False
        except ValueError:
            # É nome de domínio público normal
            pass

        return True
    except Exception as e:
        logger.warning(f"[ANTI-SSRF] Erro ao validar URL '{url}': {e}")
        return False

def safe_download_image(url: str, timeout: int = 3, max_bytes: int = 5 * 1024 * 1024) -> Optional[bytes]:
    """
    Baixa imagens remotas com verificação estrita de SSRF, timeout curto e limite de tamanho.
    """
    if not is_safe_external_url(url):
        logger.warning(f"[ANTI-SSRF] Download de imagem cancelado: URL insegura '{url}'")
        return None

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ERP-Talatto-SafeImageFetcher/1.0", "Accept": "image/*"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                logger.warning(f"[ANTI-SSRF] Imagem excede tamanho máximo ({content_length} bytes)")
                return None

            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                logger.warning(f"[ANTI-SSRF] Imagem excedeu o buffer máximo de {max_bytes} bytes")
                return None

            return data
    except Exception as e:
        logger.warning(f"[ANTI-SSRF] Falha ao baixar imagem segura de {url}: {e}")
        return None


# ==============================================================================
# 2. PARSE SEGURO DE XML (Anti-XXE e Anti-Bomba XML)
# ==============================================================================

def safe_xml_fromstring(xml_content: str | bytes) -> etree._Element:
    """
    Faz o parse de XML com proteção anti-XXE e limitação contra ataques DoS (Billion Laughs).
    Desativa expansão de entidades externas, DTD e conexões de rede.
    """
    if isinstance(xml_content, str):
        xml_data = xml_content.encode("utf-8")
    else:
        xml_data = xml_content

    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        remove_blank_text=True,
        huge_tree=False
    )
    return etree.fromstring(xml_data, parser=parser)


# ==============================================================================
# 3. RBAC E CONTROLE DE ACESSO (Anti-BOLA e Escalação de Privilégios)
# ==============================================================================

ADMIN_ONLY_MODELS = {
    "perfil", "perfis",
    "intelipost_configuracoes", "intelipost_configuracao",
    "shopee_configuracoes", "shopee_configuracao",
    "magento_configuracoes", "magento_configuracao",
    "tiktok_configuracoes", "tiktok_configuracao",
    "meli_configuracoes", "meli_configuracao", "meli_credentials",
    "elastic_email_configuracoes", "elastic_email_configuracao",
    "atendai_configuracoes", "atendai_configuracao",
    "outras_empresas_configuracoes", "outras_empresas_configuracao"
}

MODULE_MAP = {
    "pedidos": "pedidos",
    "pedidos_itens": "pedidos",
    "pedido_itens": "pedidos",
    "contas": "contas",
    "cadastros": "cadastros",
    "produtos": "produtos",
    "estoque": "estoque",
    "embalagens": "embalagens",
    "tributacoes": "tributacoes",
    "regras_tributarias": "tributacoes",
    "classificacao_contabil": "contas",
    "classificacoes_contabeis": "contas",
    "relatorios": "relatorios",
    "nfe_inutilizacoes": "notas_fiscais",
    "nfe_inutilizacao": "notas_fiscais",
    "notas_fiscais": "notas_fiscais",
    "nfe_recebidas": "notas_fiscais",
    "nfe_rece_bidas": "nfe_rece_bidas",
    "usuarios": "usuarios",
    "empresas": "empresas",
    "mercadolivre_pedidos": "integracoes",
    "magento_pedidos": "integracoes",
    "shopee_pedidos": "integracoes",
    "tiktok_pedidos": "integracoes",
    "intelipost": "integracoes",
    "email_regras": "integracoes"
}

def verify_model_access(model_name: str, action: str, current_user: Any):
    """
    Garante que:
    1. Apenas usuários 'admin' acessem modelos estritamente administrativos e credenciais de integrações.
    2. Operadores respeitem a matriz de permissões de módulo ('acesso' e 'acoes').
    """
    model_lower = model_name.lower().strip()
    user_profile = (getattr(current_user, "perfil", "") or "").lower()
    is_admin = (user_profile == "admin")

    # 1. Tabelas Administrativas são exclusivas para perfil Administrador
    if model_lower in ADMIN_ONLY_MODELS:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado: o recurso '{model_name}' requer privilégios de Administrador."
            )
        return

    # Administrador tem acesso total a todos os modelos
    if is_admin:
        return

    # 2. Verificação de Permissões para usuários comuns
    permissoes = getattr(current_user, "permissoes", {}) or {}
    if not isinstance(permissoes, dict):
        permissoes = {}

    # Caso especial: Usuários e Minha Empresa requerem admin ou permissão explícita no módulo
    if model_lower in ("usuarios", "empresas"):
        mod_key = "usuarios" if model_lower == "usuarios" else "empresas"
        if not (permissoes.get(mod_key, {}).get("acesso") is True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado: o recurso '{model_name}' requer privilégios de Administrador."
            )

    module_key = MODULE_MAP.get(model_lower)
    if module_key:
        if module_key in ("notas_fiscais", "nfe_rece_bidas"):
            mod_perm = permissoes.get("notas_fiscais") or permissoes.get("nfe_rece_bidas")
        else:
            mod_perm = permissoes.get(module_key)

        # Se o módulo não estiver nas permissões ou tiver acesso == False
        if not mod_perm or (isinstance(mod_perm, dict) and mod_perm.get("acesso") is False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado: você não tem permissão para acessar o módulo '{module_key}'."
            )

        if isinstance(mod_perm, dict):
            acoes = mod_perm.get("acoes", [])
            if isinstance(acoes, list) and len(acoes) > 0:
                if action == "delete" and not any(a in acoes for a in ["excluir", "deletar", "delete"]):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Acesso negado: você não tem permissão de exclusão no módulo '{module_key}'."
                    )
                if action == "create" and not any(a in acoes for a in ["criar", "create"]):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Acesso negado: você não tem permissão de criação no módulo '{module_key}'."
                    )
                if action == "update" and not any(a in acoes for a in ["editar", "edit", "update"]):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Acesso negado: você não tem permissão de edição no módulo '{module_key}'."
                    )


# ==============================================================================
# 4. SANITIZAÇÃO DE DADOS SENSÍVEIS EM RESPOSTAS DA API (Censura de Segredos)
# ==============================================================================

SENSITIVE_OUTPUT_FIELDS = {
    "senha", "password", "certificado_senha", "certificado_arquivo",
    "partner_key", "consumer_secret", "token_secret", "app_secret",
    "client_secret", "webhook_token"
}

def sanitize_record_dict(record_dict: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """Remove ou mascara campos sensíveis antes de enviar ao cliente."""
    if not isinstance(record_dict, dict):
        return record_dict

    clean = record_dict.copy()
    model_lower = model_name.lower().strip()

    # Senhas de usuários NUNCA saem na API
    if "senha" in clean:
        clean.pop("senha", None)
    if "password" in clean:
        clean.pop("password", None)

    # Certificados digitais da empresa
    if model_lower == "empresas":
        if clean.get("certificado_arquivo"):
            clean["tem_certificado"] = True
        clean.pop("certificado_arquivo", None)
        clean.pop("certificado_senha", None)

    # Segredos de integrações
    if any(m in model_lower for m in ["shopee", "intelipost", "meli", "magento", "tiktok", "elastic_email", "atendai"]):
        for f in SENSITIVE_OUTPUT_FIELDS:
            if f in clean and clean[f]:
                clean[f] = "********"

    return clean

