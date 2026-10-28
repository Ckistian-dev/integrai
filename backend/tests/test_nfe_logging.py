import unittest
from unittest.mock import patch, MagicMock
from app.core.service.nfe_service import NFeService
from app.core.error_codes import NfeErrorCode

class TestNfeLogging(unittest.TestCase):
    @patch("app.core.service.nfe_service.log_error")
    def test_nfe_invalid_xml_logs_structured_error(self, mock_log_err):
        mock_db = MagicMock()
        mock_empresa = MagicMock()
        mock_empresa.certificado_arquivo = b"fake_cert"
        mock_empresa.certificado_senha = "123"
        mock_db.query().filter().first.return_value = mock_empresa

        service = NFeService(mock_db, id_empresa=1)
        # Tenta gerar DANFE com XML inválido
        result = service._gerar_danfe(xml_nfe="<xml>invalido</xml>", nProt="123", dhRecbto="2026-10-28", chNFe="3526")
        self.assertIsNone(result)
        mock_log_err.assert_called()
        args, kwargs = mock_log_err.call_args
        self.assertEqual(args[0], "NFE")
        self.assertEqual(args[1], "nfe_service")
        self.assertEqual(args[2], "_gerar_danfe")
        self.assertEqual(args[3], NfeErrorCode.DANFE_GENERATION)

if __name__ == "__main__":
    unittest.main()
