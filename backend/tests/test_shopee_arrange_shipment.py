import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.core.service.shopee_service import ShopeeService
from app.core.db import models

class TestShopeeArrangeShipment(unittest.TestCase):
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
    @patch("requests.get")
    def test_arrange_shipment_stops_when_get_param_fails(self, mock_get, mock_post):
        mock_resp_param = MagicMock()
        mock_resp_param.status_code = 200
        mock_resp_param.json.return_value = {
            "error": "logistics.order_not_ready_to_ship",
            "message": "Package is not ready to ship"
        }
        mock_get.return_value = mock_resp_param

        service = ShopeeService(self.mock_db, id_empresa=1)
        res = service.arrange_shipment(order_sn="261103AWGJFXFK")

        mock_post.assert_not_called()
        self.assertIn(res.get("status"), ["warning", "error"])

    @patch("requests.post")
    @patch("requests.get")
    def test_arrange_shipment_stops_when_no_shipping_methods_returned(self, mock_get, mock_post):
        mock_resp_param = MagicMock()
        mock_resp_param.status_code = 200
        mock_resp_param.json.return_value = {
            "response": {}
        }
        mock_get.return_value = mock_resp_param

        service = ShopeeService(self.mock_db, id_empresa=1)
        res = service.arrange_shipment(order_sn="261103AWGJFXFK")

        mock_post.assert_not_called()
        self.assertIn(res.get("status"), ["warning", "error"])

    @patch("requests.post")
    @patch("requests.get")
    def test_arrange_shipment_skips_if_already_processed_or_shipped(self, mock_get, mock_post):
        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.shopee_order_status = "SHIPPED"

        res = service.arrange_shipment(order_sn="261103AWGJFXFK", pedido=pedido)
        mock_get.assert_not_called()
        mock_post.assert_not_called()
        self.assertEqual(res.get("status"), "success")

    @patch.object(ShopeeService, "arrange_shipment")
    @patch.object(ShopeeService, "get_shopee_order_detail", return_value={"order_status": "READY_TO_SHIP"})
    def test_ready_to_ship_does_not_call_arrange_shipment(self, mock_detail, mock_arrange):
        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 7299
        pedido.shopee_order_sn = "261103AWGJFXFK"
        pedido.shopee_order_status = "READY_TO_SHIP"
        pedido.shopee_xml_enviado = True
        pedido.situacao = "faturamento"

        res = service.update_shopee_order_status(pedido=pedido, target_status="READY_TO_SHIP")
        mock_arrange.assert_not_called()

    @patch.object(ShopeeService, "get_shopee_order_detail", return_value={"order_status": "SHIPPED"})
    @patch.object(ShopeeService, "arrange_shipment", return_value={"status": "success"})
    @patch.object(ShopeeService, "update_tracking_status", return_value={"success": True})
    def test_rule_priority_shipped_wins_over_xml_enviado(self, mock_track, mock_arrange, mock_detail):
        # Configure 2 rules: xml_enviado (READY_TO_SHIP) and situacao (SHIPPED)
        self.mock_config.regras_atualizacao_status = [
            {"coluna_pedido": "shopee_xml_enviado", "valor_coluna": "True", "status_shopee": "READY_TO_SHIP"},
            {"coluna_pedido": "situacao", "valor_coluna": "despachado", "status_shopee": "SHIPPED"}
        ]
        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 7299
        pedido.shopee_order_sn = "261103AWGJFXFK"
        pedido.shopee_order_status = "READY_TO_SHIP"
        pedido.shopee_xml_enviado = True
        pedido.situacao = "despachado"

        res = service.update_shopee_order_status(pedido=pedido)
        self.assertEqual(res.get("target_status"), "SHIPPED")
        mock_arrange.assert_called_once()

    @patch.object(ShopeeService, "arrange_shipment")
    @patch.object(ShopeeService, "get_shopee_order_detail")
    def test_do_not_downgrade_already_shipped_order_to_ready_to_ship(self, mock_detail, mock_arrange):
        self.mock_config.regras_atualizacao_status = [
            {"coluna_pedido": "shopee_xml_enviado", "valor_coluna": "True", "status_shopee": "READY_TO_SHIP"}
        ]
        service = ShopeeService(self.mock_db, id_empresa=1)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 7299
        pedido.shopee_order_sn = "261103AWGJFXFK"
        pedido.shopee_order_status = "SHIPPED"
        pedido.shopee_xml_enviado = True
        pedido.situacao = "faturamento"

        res = service.update_shopee_order_status(pedido=pedido)
        mock_arrange.assert_not_called()
        self.assertTrue(res.get("success"))

if __name__ == '__main__':
    unittest.main()
