import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.core.service.shopee_service import ShopeeService
from app.core.db import models

class TestShopeeWebhook(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_config = MagicMock()
        self.mock_config.partner_id = "12345"
        self.mock_config.partner_key = "secret_key"
        self.mock_config.shop_id = "99999"
        self.mock_config.access_token = "valid_token"
        self.mock_config.token_expires_at = datetime.now(timezone.utc).replace(year=2030)
        self.mock_config.environment = "production"
        
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_config

    def test_process_shopee_webhook_order_status_update(self):
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 42
        pedido.shopee_order_sn = "241012DCXHJUIKJ"
        pedido.shopee_order_status = "READY_TO_SHIP"
        pedido.shopee_historico = []
        pedido.data_despacho = None

        def query_side_effect(model_cls):
            mock_q = MagicMock()
            if model_cls == models.ShopeeConfiguracao:
                mock_q.filter.return_value.first.return_value = self.mock_config
            elif model_cls == models.Pedido:
                mock_q.filter.return_value.first.return_value = pedido
            return mock_q

        self.mock_db.query.side_effect = query_side_effect
        service = ShopeeService(self.mock_db, id_empresa=1)

        payload = {
            "shop_id": 99999,
            "code": 3,
            "timestamp": 1600000000,
            "data": {
                "ordersn": "241012DCXHJUIKJ",
                "status": "SHIPPED",
                "update_time": 1600000000
            }
        }

        result = service.process_shopee_webhook(payload)

        self.assertTrue(result.get("success"), f"Expected success=True, got {result}")
        self.assertEqual(pedido.shopee_order_status, "SHIPPED")
        self.assertIsNotNone(pedido.data_despacho, "data_despacho deve ser preenchida ao mudar para SHIPPED")
        self.assertTrue(len(pedido.shopee_historico) > 0, "Historico deve conter o registro do webhook")
        
        hist = pedido.shopee_historico[-1]
        self.assertIn("Webhook", hist["evento"])
        self.assertEqual(hist["origem"], "webhook_shopee")
        self.assertEqual(hist["status"], "SHIPPED")
        self.assertEqual(hist["status_shopee"], "SHIPPED")
        self.assertEqual(hist["status_retorno"], "success")
        self.assertTrue(hist["sucesso"])
        self.assertIn("payload", hist)
        self.assertEqual(hist["payload"], payload)
        self.assertIn("data_evento", hist)
        self.assertIn("comentario", hist)

    def test_process_shopee_webhook_tracking_update(self):
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 42
        pedido.shopee_order_sn = "241012DCXHJUIKJ"
        pedido.shopee_tracking_number = None
        pedido.shopee_historico = []

        def query_side_effect(model_cls):
            mock_q = MagicMock()
            if model_cls == models.ShopeeConfiguracao:
                mock_q.filter.return_value.first.return_value = self.mock_config
            elif model_cls == models.Pedido:
                mock_q.filter.return_value.first.return_value = pedido
            return mock_q

        self.mock_db.query.side_effect = query_side_effect
        service = ShopeeService(self.mock_db, id_empresa=1)

        payload = {
            "shop_id": 99999,
            "code": 4,
            "timestamp": 1600000000,
            "data": {
                "ordersn": "241012DCXHJUIKJ",
                "tracking_no": "BR9988776655",
                "logistics_status": "LOGISTICS_PICKUP_DONE"
            }
        }

        result = service.process_shopee_webhook(payload)

        self.assertTrue(result.get("success"))
        self.assertEqual(pedido.shopee_tracking_number, "BR9988776655")
        self.assertTrue(len(pedido.shopee_historico) > 0)
        hist = pedido.shopee_historico[-1]
        self.assertEqual(hist["origem"], "webhook_shopee")
        self.assertEqual(hist["tracking_code"], "BR9988776655")
        self.assertEqual(hist["logistics_status"], "LOGISTICS_PICKUP_DONE")

    def test_process_shopee_webhook_fallback_observacao(self):
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 99
        pedido.shopee_order_sn = None
        pedido.observacao = "Pedido Shopee 241012DCXHJUIKJ importado"
        pedido.shopee_historico = []

        mock_pedido_q = MagicMock()
        mock_pedido_q.filter.return_value.first.side_effect = [None, None, pedido]

        def query_side_effect(model_cls):
            if model_cls == models.ShopeeConfiguracao:
                mock_q = MagicMock()
                mock_q.filter.return_value.first.return_value = self.mock_config
                return mock_q
            elif model_cls == models.Pedido:
                return mock_pedido_q
            return MagicMock()

        self.mock_db.query.side_effect = query_side_effect
        service = ShopeeService(self.mock_db, id_empresa=1)

        payload = {
            "shop_id": 99999,
            "code": 3,
            "data": {
                "ordersn": "241012DCXHJUIKJ",
                "status": "COMPLETED"
            }
        }

        result = service.process_shopee_webhook(payload)
        self.assertTrue(result.get("success"))
        self.assertEqual(pedido.shopee_order_sn, "241012DCXHJUIKJ")
        self.assertEqual(pedido.shopee_order_status, "COMPLETED")
        self.assertTrue(len(pedido.shopee_historico) > 0)

    @patch("app.core.service.shopee_service.ShopeeService.process_shopee_webhook")
    def test_webhook_http_endpoint(self, mock_process):
        mock_process.return_value = {"success": True, "order_sn": "241012DCXHJUIKJ"}
        from fastapi.testclient import TestClient
        from app.main import app
        from app.core.db.database import get_db

        def override_get_db():
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = self.mock_config
            yield mock_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            response = client.post("/api/v1/shopee/webhook", json={
                "shop_id": 99999,
                "code": 3,
                "data": {"ordersn": "241012DCXHJUIKJ", "status": "SHIPPED"}
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("message"), "success")
            mock_process.assert_called_once()
        finally:
            app.dependency_overrides.clear()

if __name__ == '__main__':
    unittest.main()

