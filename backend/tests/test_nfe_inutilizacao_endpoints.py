import unittest
from unittest.mock import MagicMock, patch
import httpx

# Compatibilidade entre Starlette 0.36 e HTTPX 0.28
_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, app=None, **kwargs):
    return _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_current_active_user
from app.core.db.database import get_db

class TestNfeInutilizacaoEndpoints(unittest.TestCase):
    def setUp(self):
        self.mock_user = MagicMock()
        self.mock_user.id = 1
        self.mock_user.id_empresa = 1
        self.mock_user.perfil = "admin"
        app.dependency_overrides[get_current_active_user] = lambda: self.mock_user
        app.dependency_overrides[get_db] = lambda: MagicMock()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.core.service.nfe_service.NFeService.inutilizar_numeracao")
    def test_post_inutilizar_endpoint(self, mock_inut):
        mock_inut.return_value = {
            "sucesso": True,
            "cstat": "102",
            "xmotivo": "Inutilizacao de numero homologado",
            "protocolo": "135260000000001"
        }
        payload = {
            "modelo": "55",
            "serie": 1,
            "numero_inicial": 200,
            "numero_final": 200,
            "justificativa": "Pulo de numeracao devido a erro operacional"
        }
        res = self.client.post("/api/v1/nfe/inutilizar", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["cstat"], "102")
        mock_inut.assert_called_once_with(
            modelo="55",
            serie=1,
            numero_inicial=200,
            numero_final=200,
            justificativa="Pulo de numeracao devido a erro operacional",
            ano=None,
            id_usuario=1
        )

    @patch("app.core.service.nfe_service.NFeService.listar_inutilizacoes")
    def test_get_inutilizacoes_endpoint(self, mock_listar):
        mock_listar.return_value = [
            {
                "id": 1,
                "id_empresa": 1,
                "modelo": "55",
                "serie": 1,
                "numero_inicial": 200,
                "numero_final": 200,
                "ano": 2026,
                "justificativa": "Pulo de numeracao",
                "sucesso": True,
                "cstat": "102"
            }
        ]
        res = self.client.get("/api/v1/nfe/inutilizacoes?limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], 1)
        mock_listar.assert_called_once_with(limit=50, offset=0)
