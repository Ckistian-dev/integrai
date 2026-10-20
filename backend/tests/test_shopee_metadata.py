import unittest
from app.core.db import models

class TestShopeeMetadata(unittest.TestCase):
    def test_shopee_order_status_metadata(self):
        col = models.Pedido.__table__.columns.get('shopee_order_status')
        self.assertIsNotNone(col, "Coluna shopee_order_status deve existir no modelo Pedido")
        info = col.info or {}
        self.assertEqual(info.get('component'), 'select', "component deve ser 'select'")
        options = info.get('options')
        self.assertIsInstance(options, list, "options deve ser uma lista")
        
        values = [opt['value'] for opt in options if isinstance(opt, dict)]
        expected_values = [
            'READY_TO_SHIP', 'PROCESSED', 'SHIPPED', 
            'TO_CONFIRM_RECEIVE', 'COMPLETED', 'CANCELLED', 
            'IN_CANCEL', 'UNPAID', 'TO_RETURN'
        ]
        for val in expected_values:
            self.assertIn(val, values, f"Valor {val} deve estar presente nas opções de status da Shopee")

if __name__ == '__main__':
    unittest.main()
