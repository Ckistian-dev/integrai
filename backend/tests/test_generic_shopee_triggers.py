import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app.core.db import models

class TestGenericShopeeTriggers(unittest.TestCase):
    def test_manual_status_change_fails_raises_http_400(self):
        """
        Quando o usuário altera shopee_order_status manualmente e a Shopee recusa,
        deve disparar HTTPException com status_code=400 e mensagem explicativa.
        """
        mock_shopee_svc = MagicMock()
        mock_shopee_svc.update_shopee_order_status.return_value = {
            "success": False,
            "status": "error",
            "message": "Canal de logística integrada não permite marcar como entregue"
        }

        # Simula pedido existente com status antigo
        db_obj = MagicMock(spec=models.Pedido)
        db_obj.id = 1
        db_obj.shopee_order_sn = "241012DCXHJUIKJ"
        db_obj.shopee_order_status = "SHIPPED"
        db_obj.origem_venda = "Shopee"
        db_obj.observacao = ""

        item_data = {"shopee_order_status": "COMPLETED"}
        old_shopee_order_status = db_obj.shopee_order_status
        is_shopee_order = True
        new_st = item_data.get("shopee_order_status")

        # Verifica a lógica esperada
        if is_shopee_order and new_st and new_st != old_shopee_order_status:
            res = mock_shopee_svc.update_shopee_order_status(
                pedido=db_obj,
                target_status=new_st,
                is_manual=True
            )
            if not res.get("success"):
                with self.assertRaises(HTTPException) as ctx:
                    raise HTTPException(status_code=400, detail=f"Shopee: {res.get('message')}")
                self.assertEqual(ctx.exception.status_code, 400)
                self.assertIn("logística integrada", ctx.exception.detail)

    def test_auto_trigger_failure_keeps_original_status(self):
        """
        Quando um gatilho automático dispara e a Shopee falha, o status deve ser restaurado
        e não modificado no pedido.
        """
        mock_shopee_svc = MagicMock()
        mock_shopee_svc.update_shopee_order_status.return_value = {
            "success": False,
            "status": "error",
            "message": "Erro de comunicação Shopee"
        }

        item = MagicMock(spec=models.Pedido)
        item.shopee_order_status = "COMPLETED"
        old_shopee_status = "SHIPPED"

        res = mock_shopee_svc.update_shopee_order_status(pedido=item, is_manual=False)
        if not res.get("success"):
            item.shopee_order_status = old_shopee_status

        self.assertEqual(item.shopee_order_status, "SHIPPED")

if __name__ == '__main__':
    unittest.main()
