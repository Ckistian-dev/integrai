import unittest
from unittest.mock import patch, MagicMock
from app.core.error_codes import ShopeeErrorCode, MeliErrorCode, LogStatus

class TestMarketplaceLogs(unittest.IsolatedAsyncioTestCase):
    @patch("app.api.v1.endpoints.shopee.log_error")
    @patch("app.api.v1.endpoints.shopee.log_info")
    def test_shopee_list_orders_logs_structured_flow(self, mock_info, mock_err):
        from app.api.v1.endpoints.shopee import list_shopee_orders_proxy
        db = MagicMock()
        user = MagicMock()
        user.id_empresa = 1

        with patch("app.api.v1.endpoints.shopee.ShopeeService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.list_orders.return_value = {"items": [], "total": 0}
            mock_service_cls.return_value = mock_service

            res = list_shopee_orders_proxy(skip=0, limit=10, filters=None, db=db, current_user=user)
            self.assertIsNotNone(res)
            mock_info.assert_called()
            args, _ = mock_info.call_args
            self.assertEqual(args[0], "SHOPEE")
            self.assertEqual(args[1], "shopee_endpoint")

    @patch("app.api.v1.endpoints.mercadolivre.log_info")
    async def test_meli_list_orders_logs_structured_flow(self, mock_info):
        from app.api.v1.endpoints.mercadolivre import list_ml_orders_proxy
        db = MagicMock()
        user = MagicMock()
        user.id_empresa = 1

        with patch("app.api.v1.endpoints.mercadolivre.MeliService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.list_orders = unittest.mock.AsyncMock(return_value={"items": [], "total": 0})
            mock_service_cls.return_value = mock_service

            res = await list_ml_orders_proxy(skip=0, limit=10, filters=None, db=db, current_user=user)
            self.assertIsNotNone(res)
            mock_info.assert_called()
            args, _ = mock_info.call_args
            self.assertEqual(args[0], "MELI")
            self.assertEqual(args[1], "meli_endpoint")

if __name__ == "__main__":
    unittest.main()
