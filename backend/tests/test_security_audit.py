import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.security_guard import (
    is_safe_external_url,
    safe_xml_fromstring,
    verify_model_access,
    sanitize_record_dict,
    ADMIN_ONLY_MODELS
)
from app.core.db import schemas, models
from app.crud.crud_user import authenticate_user
from app.api.v1.endpoints.auth import _check_rate_limit, _record_failed_attempt, _clear_attempts, MAX_LOGIN_ATTEMPTS

class TestSecurityAudit(unittest.TestCase):
    """Suite de testes automatizados de segurança e fluxos defensivos."""

    def test_anti_ssrf_blocking(self):
        """Verifica se URLs de loopback, intranet e protocolos perigosos são estritamente bloqueadas."""
        malicious_urls = [
            "file:///etc/passwd",
            "file:///C:/backend/.env",
            "http://127.0.0.1:8000/secret",
            "http://localhost:5432",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/admin",
            "http://192.168.1.1/router",
            "http://172.16.0.5/api",
            "gopher://localhost:70",
            "ftp://anonymous@internal.corp",
            "http://metadata.google.internal/computeMetadata/v1/"
        ]
        for url in malicious_urls:
            self.assertFalse(is_safe_external_url(url), f"URL maliciosa deveria ter sido bloqueada: {url}")

        safe_urls = [
            "https://cdn.empresa.com.br/logo.png",
            "https://images.unsplash.com/photo.jpg",
            "http://meusitepublico.com.br/assets/logo.jpg"
        ]
        for url in safe_urls:
            self.assertTrue(is_safe_external_url(url), f"URL pública segura deveria ter sido permitida: {url}")

    def test_safe_xml_parser(self):
        """Verifica se o parser XML seguro não resolve entidades externas (XXE)."""
        xxe_xml = """<?xml version="1.0"?>
        <!DOCTYPE foo [
        <!ELEMENT foo ANY >
        <!ENTITY xxe SYSTEM "file:///etc/passwd" >]>
        <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
            <chNFe>&xxe;12345678901234567890123456789012345678901234</chNFe>
        </nfeProc>"""

        root = safe_xml_fromstring(xxe_xml)
        ch_node = root.xpath("//*[local-name()='chNFe']")
        self.assertTrue(len(ch_node) > 0)
        # O valor não deve conter o conteúdo do arquivo /etc/passwd
        self.assertNotIn("root:", ch_node[0].text or "")

    def test_rbac_admin_only_models_blocked_for_normal_users(self):
        """Verifica se usuários não-administradores recebem 403 Forbidden em tabelas administrativas."""
        mock_user = MagicMock(spec=models.Usuario)
        mock_user.perfil = "Vendedor"
        mock_user.permissoes = {"pedidos": {"acesso": True}}

        # Tabelas estritamente administrativas ou de usuários: bloqueadas para leitura e escrita
        for model in ["usuarios", "perfil", "shopee_configuracoes", "intelipost_configuracoes"]:
            with self.assertRaises(HTTPException) as ctx:
                verify_model_access(model, "read", mock_user)
            self.assertEqual(ctx.exception.status_code, 403)

            with self.assertRaises(HTTPException) as ctx:
                verify_model_access(model, "create", mock_user)
            self.assertEqual(ctx.exception.status_code, 403)

            with self.assertRaises(HTTPException) as ctx:
                verify_model_access(model, "delete", mock_user)
            self.assertEqual(ctx.exception.status_code, 403)

        # Minha Empresa: criação, atualização e exclusão são bloqueadas para usuários sem permissão no módulo
        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("empresas", "create", mock_user)
        self.assertEqual(ctx.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("empresas", "update", mock_user)
        self.assertEqual(ctx.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("empresas", "delete", mock_user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_rbac_operational_reference_models_read_allowed_but_edit_blocked(self):
        """
        Garante que dados de apoio (empresas, produtos, tributações, embalagens, cadastros)
        podem ser lidos para rotinas operacionais (faturamento, pedidos, etiquetas),
        mas qualquer tentativa de edição sem a respectiva permissão resulta em 403 Forbidden.
        """
        mock_user = MagicMock(spec=models.Usuario)
        mock_user.perfil = "Operador"
        # Usuário só tem acesso ao módulo de pedidos
        mock_user.permissoes = {
            "pedidos": {
                "acesso": True,
                "acoes": ["faturamento", "conferencia"]
            }
        }

        # 1. Leitura é permitida para apoiar faturamento e visualização
        verify_model_access("empresas", "read", mock_user)
        verify_model_access("produtos", "read", mock_user)
        verify_model_access("tributacoes", "read", mock_user)
        verify_model_access("embalagens", "read", mock_user)
        verify_model_access("cadastros", "read", mock_user)

        # 2. Edição/criação/exclusão de empresa é estritamente bloqueada
        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("empresas", "update", mock_user)
        self.assertEqual(ctx.exception.status_code, 403)

        # 3. Edição/criação/exclusão de produtos é estritamente bloqueada
        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("produtos", "update", mock_user)
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("produtos", "create", mock_user)
        self.assertEqual(ctx.exception.status_code, 403)

        # 4. Atualização de pedidos com ação operacional (faturamento/conferencia) é permitida
        verify_model_access("pedidos", "update", mock_user)

    def test_rbac_admin_user_allowed_access(self):
        """Verifica se usuário com perfil admin possui acesso irrestrito aos modelos."""
        mock_admin = MagicMock(spec=models.Usuario)
        mock_admin.perfil = "admin"
        mock_admin.permissoes = {}

        # Não deve levantar exceção para nenhum modelo
        for model in ["usuarios", "empresas", "pedidos", "contas"]:
            verify_model_access(model, "read", mock_admin)
            verify_model_access(model, "create", mock_admin)
            verify_model_access(model, "delete", mock_admin)

    def test_rbac_granular_actions_and_modules(self):
        """Verifica se controle de ações granulares (create, update, delete) e módulos é estritamente aplicado."""
        mock_operador = MagicMock(spec=models.Usuario)
        mock_operador.perfil = "Operador"
        mock_operador.permissoes = {
            "pedidos": {
                "acesso": True,
                "acoes": ["create", "edit"] # Sem delete
            },
            "notas_fiscais": {
                "acesso": True,
                "acoes": ["visualizar", "export"]
            }
        }

        # Pedidos: create e update permitidos, delete bloqueado
        verify_model_access("pedidos", "read", mock_operador)
        verify_model_access("pedidos", "create", mock_operador)
        verify_model_access("pedidos", "update", mock_operador)
        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("pedidos", "delete", mock_operador)
        self.assertEqual(ctx.exception.status_code, 403)

        # Notas Fiscais e Inutilizações: permitidos via notas_fiscais
        verify_model_access("notas_fiscais", "read", mock_operador)
        verify_model_access("nfe_inutilizacoes", "read", mock_operador)

        # Módulo não concedido (contas / financeiro): bloqueado
        with self.assertRaises(HTTPException) as ctx:
            verify_model_access("contas", "read", mock_operador)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_user_password_censored_in_schema(self):
        """Garante que o schema Usuario nunca serializa o campo de senha."""
        now = datetime.now(timezone.utc)
        user_schema = schemas.Usuario(
            id=1,
            id_sequencial=1,
            id_empresa=10,
            nome="Administrador",
            email="admin@talatto.com",
            senha="PlainTextSuperSecretPassword123!",
            situacao=True,
            criado_em=now,
            empresa={"id": 10, "razao": "Empresa Teste", "cnpj": "00.000.000/0001-00", "cep": "00000-000", "criado_em": now}
        )

        serialized = user_schema.model_dump()
        self.assertNotIn("senha", serialized, "A senha NUNCA deve ser incluída no dump serializado de Usuario")

    def test_company_certificate_and_password_censored_in_schema(self):
        """Garante que o certificado digital e sua senha são excluídos da serialização."""
        now = datetime.now(timezone.utc)
        empresa_schema = schemas.Empresa(
            id=1,
            cnpj="12.345.678/0001-99",
            razao="Talatto Indústria e Comércio Ltda",
            cep="14400-000",
            criado_em=now,
            certificado_arquivo=b"CERTIFICATE_PRIVATE_KEY_BINARY_DATA",
            certificado_senha="PrivateCertPassword123"
        )

        serialized = empresa_schema.model_dump()
        self.assertNotIn("certificado_senha", serialized)
        self.assertNotIn("certificado_arquivo", serialized)

    def test_integration_secrets_masked_in_schema(self):
        """Garante que chaves de API da Shopee e Intelipost saem mascaradas como ********."""
        now = datetime.now(timezone.utc)
        shopee_cfg = schemas.ShopeeConfiguracao(
            id=1,
            id_empresa=1,
            partner_id="123456",
            partner_key="super_secret_partner_key_12345",
            shop_id="998877",
            access_token="real_access_token_abcde",
            refresh_token="real_refresh_token_xyz",
            criado_em=now
        )
        serialized_shopee = shopee_cfg.model_dump()
        self.assertEqual(serialized_shopee.get("partner_key"), "********")
        self.assertEqual(serialized_shopee.get("access_token"), "********")
        self.assertEqual(serialized_shopee.get("refresh_token"), "********")

        inteli_cfg = schemas.IntelipostConfiguracao(
            id=1,
            id_empresa=1,
            api_key="intelipost_secret_api_key_live",
            origin_zip_code="14400-000",
            criado_em=now
        )
        serialized_inteli = inteli_cfg.model_dump()
        self.assertEqual(serialized_inteli.get("api_key"), "********")

    def test_login_brute_force_rate_limiting(self):
        """Verifica se exceder o limite de tentativas no login bloqueia com HTTP 429."""
        test_key = "192.168.100.5:attacker@test.com"
        _clear_attempts(test_key)

        for _ in range(MAX_LOGIN_ATTEMPTS - 1):
            _check_rate_limit(test_key)
            _record_failed_attempt(test_key)

        _record_failed_attempt(test_key)
        with self.assertRaises(HTTPException) as ctx:
            _check_rate_limit(test_key)
        self.assertEqual(ctx.exception.status_code, 429)

        _clear_attempts(test_key)

    def test_security_headers_middleware(self):
        """Verifica se os cabeçalhos de proteção HTTP são injetados pela aplicação."""
        import asyncio
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        async def _check_headers():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
                res = await client.get("/")
                return res

        response = asyncio.run(_check_headers())
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

if __name__ == "__main__":
    unittest.main()

