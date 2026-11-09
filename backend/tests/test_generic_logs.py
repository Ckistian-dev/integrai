import unittest
from unittest.mock import patch, MagicMock
from app.core.error_codes import GenericErrorCode, EmailErrorCode, LogStatus

class TestGenericLogs(unittest.TestCase):
    def test_generic_endpoint_uses_structured_logger(self):
        from app.api.v1.endpoints import generic
        self.assertTrue(hasattr(generic, 'log_error') or hasattr(generic, 'log_info'))

    def test_crud_generic_uses_structured_logger(self):
        from app.crud import crud_generic
        self.assertTrue(hasattr(crud_generic, 'log_info') or hasattr(crud_generic, 'log_error'))

    def test_elastic_email_service_uses_structured_logger(self):
        from app.core.service import elastic_email_service
        self.assertTrue(hasattr(elastic_email_service, 'log_info') or hasattr(elastic_email_service, 'log_error'))

    @patch("app.core.service.elastic_email_service.log_info")
    def test_elastic_email_logs_simulation_or_success(self, mock_log_info):
        import asyncio
        from app.core.service.elastic_email_service import ElasticEmailService
        
        mock_db = MagicMock()
        mock_config = MagicMock()
        mock_config.api_key = "dummy"
        mock_config.from_name = "Test"
        mock_config.from_email = "test@example.com"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        service = ElasticEmailService(mock_db, id_empresa=1)
        mock_regra = MagicMock()
        mock_regra.nome = "Regra Teste"
        mock_regra.subject = "Teste"
        mock_regra.body_html = "<p>Teste</p>"
        mock_regra.anexos = []
        
        mock_pedido = MagicMock()
        mock_pedido.id = 123
        mock_pedido.cliente.email = "cliente@teste.com"
        mock_pedido.cliente.nome_razao = "Cliente Teste"

        # Chamada de _send_for_regra no ambiente de teste/dev
        res = asyncio.run(service._send_for_regra(mock_regra, mock_pedido, "Aberto", "Faturamento", None, None))
        self.assertTrue(res.get("success"))
        mock_log_info.assert_called()

    @patch("app.core.service.elastic_email_service.log_info")
    def test_elastic_email_send_trigger_emails_no_rules_skipped(self, mock_log_info):
        import asyncio
        from app.core.service.elastic_email_service import ElasticEmailService
        
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        
        service = ElasticEmailService(mock_db, id_empresa=1)
        mock_pedido = MagicMock()
        mock_pedido.id = 8832

        results = asyncio.run(service.send_trigger_emails(
            pedido=mock_pedido,
            situacao_de="Em Aberto",
            situacao_para="Atendido",
        ))
        self.assertEqual(results, [])
        mock_log_info.assert_called_once()
        # Valida que o quarto argumento passado ao log_info é LogStatus.SKIPPED
        args, kwargs = mock_log_info.call_args
        self.assertEqual(args[3], LogStatus.SKIPPED)

if __name__ == "__main__":
    unittest.main()
