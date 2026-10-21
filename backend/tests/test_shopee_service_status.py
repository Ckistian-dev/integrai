import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.core.service.shopee_service import ShopeeService
from app.core.db import models

class TestShopeeServiceStatus(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_config = MagicMock()
        self.mock_config.partner_id = "12345"
        self.mock_config.partner_key = "secret_key"
        self.mock_config.shop_id = "99999"
        self.mock_config.access_token = "valid_token"
        self.mock_config.token_expires_at = datetime.now(timezone.utc).replace(year=2030)
        self.mock_config.environment = "production"
        self.mock_config.regras_atualizacao_status = []
        
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_config

    @patch("requests.post")
    def test_update_tracking_status_delivery_done_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "", "message": "success"}
        mock_post.return_value = mock_resp

        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 10
        pedido.shopee_order_sn = "241012DCXHJUIKJ"
        pedido.shopee_historico = []

        res = service.update_tracking_status(
            order_sn="241012DCXHJUIKJ",
            logistics_status="logistics_delivery_done",
            pedido=pedido
        )

        self.assertTrue(res.get("success"), f"Expected success=True, got {res}")
        self.assertEqual(res.get("status"), "success")
        # Check payload sent to Shopee API
        called_args, called_kwargs = mock_post.call_args
        sent_json = called_kwargs.get("json", {})
        self.assertEqual(sent_json.get("order_sn"), "241012DCXHJUIKJ")
        self.assertEqual(sent_json.get("logistics_status"), "logistics_delivery_done")

    @patch("requests.post")
    def test_update_tracking_status_integrated_channel_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": "error_param",
            "message": "logistics channel not support this action"
        }
        mock_post.return_value = mock_resp

        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 10
        pedido.shopee_order_sn = "241012DCXHJUIKJ"
        pedido.shopee_historico = []

        res = service.update_tracking_status(
            order_sn="241012DCXHJUIKJ",
            logistics_status="logistics_delivery_done",
            pedido=pedido,
            is_manual=True
        )

        self.assertFalse(res.get("success"), "Manual update on integrated channel must fail")
        self.assertTrue(res.get("is_ssl_channel"), "Should be detected as integrated logistics channel")
        self.assertIn("Logística Integrada", res.get("message"))

    @patch.object(ShopeeService, "get_shopee_order_detail", return_value={"order_status": "SHIPPED"})
    @patch.object(ShopeeService, "arrange_shipment", return_value={"status": "success"})
    @patch.object(ShopeeService, "update_tracking_status")
    def test_update_shopee_order_status_shipped(self, mock_update_tracking, mock_arrange, mock_detail):
        mock_update_tracking.return_value = {"success": True, "status": "success", "message": "Coletado"}

        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 10
        pedido.shopee_order_sn = "241012DCXHJUIKJ"
        pedido.shopee_historico = []
        pedido.situacao = "faturamento"

        res = service.update_shopee_order_status(pedido=pedido, target_status="SHIPPED")

        self.assertTrue(res.get("success"))
        mock_arrange.assert_called_once()
        mock_update_tracking.assert_called_once()

if __name__ == '__main__':
    unittest.main()
