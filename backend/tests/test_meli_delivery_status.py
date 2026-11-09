import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
import asyncio

from app.core.db import models
from app.core.service.meli_service import MeliService
from app.api.v1.endpoints.mercadolivre import (
    atualizar_status_pedido_ml,
    confirmar_entrega_pedido_meli,
    confirmar_entrega_por_ml_id,
    sincronizar_entregas_pendentes_meli
)

class TestMeliDeliveryStatus(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.id_empresa = 1

    def test_default_status_mapping_delivered_from_situacao(self):
        """Verifica se pedidos com situacao='Entregue' ou 'Finalizado' mapeiam automaticamente para 'delivered'."""
        svc = MeliService(self.mock_db, self.id_empresa)
        svc.config = MagicMock()
        svc.config.regras_atualizacao_status = []
        svc.config.campo_link_rastreio = None

        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 501
        pedido.id_sequencial = 501
        pedido.situacao = models.PedidoSituacaoEnum.entregue
        pedido.status_intelipost = ""
        pedido.meli_order_id = "2000015711968005"
        pedido.meli_shipment_id = "44123456789"
        pedido.meli_status_envio = "shipped"

        with patch.object(svc, "update_shipment_status_by_order", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = True
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(svc.update_meli_order_status(pedido))
                self.assertTrue(res)
                mock_update.assert_called_once()
                self.assertEqual(mock_update.call_args.kwargs.get("target_ml_status"), "delivered")
            finally:
                loop.close()

    def test_default_status_mapping_delivered_from_intelipost(self):
        """Verifica se pedido com status_intelipost='DELIVERED' sobrepõe situacao='Despachado' e envia 'delivered'."""
        svc = MeliService(self.mock_db, self.id_empresa)
        svc.config = MagicMock()
        svc.config.regras_atualizacao_status = [
            {"coluna_pedido": "situacao", "valor_coluna": "Despachado", "status_meli": "shipped"}
        ]
        svc.config.campo_link_rastreio = None

        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 502
        pedido.id_sequencial = 502
        pedido.situacao = models.PedidoSituacaoEnum.despachado
        pedido.status_intelipost = "DELIVERED"
        pedido.meli_order_id = "2000015703647253"
        pedido.meli_shipment_id = "44987654321"
        pedido.meli_status_envio = "shipped"

        with patch.object(svc, "update_shipment_status_by_order", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = True
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(svc.update_meli_order_status(pedido))
                self.assertTrue(res)
                mock_update.assert_called_once()
                # A prioridade de delivered (40) do status_intelipost deve vencer shipped (30) da regra
                self.assertEqual(mock_update.call_args.kwargs.get("target_ml_status"), "delivered")
            finally:
                loop.close()

    def test_update_shipment_status_already_shipped_to_delivered(self):
        """Verifica envio de 'delivered' quando o envio já está em 'shipped' (sem transição preliminar desnecessária)."""
        svc = MeliService(self.mock_db, self.id_empresa)
        svc.config = MagicMock()
        svc.config.campo_link_rastreio = None

        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 503
        pedido.id_sequencial = 503
        pedido.meli_order_id = "2000015701436883"
        pedido.meli_shipment_id = "44556677889"
        pedido.meli_status_envio = "shipped"
        pedido.meli_historico = []

        mock_client = AsyncMock()
        # Mock do GET /shipments/44556677889
        mock_ship_get = MagicMock()
        mock_ship_get.status_code = 200
        mock_ship_get.json.return_value = {
            "id": 44556677889,
            "mode": "me1",
            "status": "shipped",
            "substatus": None,
            "site_id": "MLB"
        }
        mock_client.get.return_value = mock_ship_get

        # Mock do POST /seller_notifications
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.text = '{"message": "Notification received"}'
        mock_post_resp.json.return_value = {"status": "delivered"}
        mock_client.post.return_value = mock_post_resp

        with patch.object(svc, "get_client", new_callable=AsyncMock) as mock_get_client, \
             patch.object(svc, "_resolve_all_ml_ids", new_callable=AsyncMock) as mock_res_ids:
            mock_get_client.return_value = mock_client
            mock_res_ids.return_value = {"shipment_id": "44556677889", "order_id": "2000015701436883"}

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    svc.update_shipment_status_by_order(
                        order_id_ml="44556677889",
                        erp_status="Entregue",
                        target_ml_status="delivered",
                        pedido=pedido
                    )
                )
                self.assertTrue(res)
                # Como já estava em 'shipped', deve enviar apenas 1 POST para 'delivered'
                self.assertEqual(mock_client.post.call_count, 1)
                called_body = mock_client.post.call_args.kwargs.get("json", {})
                self.assertEqual(called_body.get("status"), "delivered")
                self.assertIsNone(called_body.get("substatus"))
                # Deve atualizar situacao para entregue
                self.assertEqual(pedido.situacao, models.PedidoSituacaoEnum.entregue)
                self.assertEqual(pedido.meli_status_envio, "delivered")
            finally:
                loop.close()

    def test_update_shipment_status_preliminary_shipped_then_delivered(self):
        """Verifica que envia transição preliminar 'shipped' antes de 'delivered' se ainda estava em 'ready_to_ship'."""
        svc = MeliService(self.mock_db, self.id_empresa)
        svc.config = MagicMock()
        svc.config.campo_link_rastreio = None

        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 504
        pedido.id_sequencial = 504
        pedido.meli_order_id = "2000015799999999"
        pedido.meli_shipment_id = "44999999999"
        pedido.meli_status_envio = "ready_to_ship"
        pedido.meli_historico = []

        mock_client = AsyncMock()
        mock_ship_get = MagicMock()
        mock_ship_get.status_code = 200
        mock_ship_get.json.return_value = {
            "id": 44999999999,
            "mode": "me1",
            "status": "ready_to_ship",
            "substatus": None,
            "site_id": "MLB"
        }
        mock_client.get.return_value = mock_ship_get

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.text = '{"message": "OK"}'
        mock_post_resp.json.return_value = {"status": "ok"}
        mock_client.post.return_value = mock_post_resp

        with patch.object(svc, "get_client", new_callable=AsyncMock) as mock_get_client, \
             patch.object(svc, "_resolve_all_ml_ids", new_callable=AsyncMock) as mock_res_ids:
            mock_get_client.return_value = mock_client
            mock_res_ids.return_value = {"shipment_id": "44999999999", "order_id": "2000015799999999"}

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    svc.update_shipment_status_by_order(
                        order_id_ml="44999999999",
                        erp_status="Entregue",
                        target_ml_status="delivered",
                        pedido=pedido
                    )
                )
                self.assertTrue(res)
                # Deve enviar 2 notificações: 1ª 'shipped' (preliminar), 2ª 'delivered' (final)
                self.assertEqual(mock_client.post.call_count, 2)
                first_body = mock_client.post.call_args_list[0].kwargs.get("json", {})
                second_body = mock_client.post.call_args_list[1].kwargs.get("json", {})
                self.assertEqual(first_body.get("status"), "shipped")
                self.assertEqual(second_body.get("status"), "delivered")
            finally:
                loop.close()

    def test_confirmar_entrega_endpoint(self):
        """Verifica o endpoint de confirmação explícita de entrega de pedido ME1."""
        mock_pedido = MagicMock(spec=models.Pedido)
        mock_pedido.id = 100
        mock_pedido.id_sequencial = 100
        mock_pedido.id_empresa = 1
        mock_pedido.meli_status_envio = "delivered"
        mock_pedido.meli_historico = []

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pedido
        self.mock_db.query.return_value = mock_query

        mock_user = MagicMock(spec=models.Usuario)
        mock_user.id = 3
        mock_user.id_empresa = 1

        with patch("app.api.v1.endpoints.mercadolivre.MeliService") as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_svc_instance.update_meli_order_status = AsyncMock(return_value=True)
            mock_service_cls.return_value = mock_svc_instance

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    confirmar_entrega_pedido_meli(
                        pedido_id=100,
                        db=self.mock_db,
                        current_user=mock_user
                    )
                )
                self.assertTrue(res["success"])
                self.assertEqual(res["status_envio"], "delivered")
                mock_svc_instance.update_meli_order_status.assert_called_once_with(
                    mock_pedido, target_status="delivered", is_manual=True
                )
            finally:
                loop.close()

    def test_confirmar_entrega_por_ml_id_endpoint(self):
        """Verifica endpoint de confirmação de entrega diretamente pelo Order ID do Mercado Livre."""
        mock_pedido = MagicMock(spec=models.Pedido)
        mock_pedido.id = 101
        mock_pedido.meli_order_id = "2000015711968005"
        mock_pedido.meli_status_envio = "delivered"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pedido
        self.mock_db.query.return_value = mock_query

        mock_user = MagicMock(spec=models.Usuario)
        mock_user.id = 3
        mock_user.id_empresa = 1

        with patch("app.api.v1.endpoints.mercadolivre.MeliService") as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_svc_instance.update_meli_order_status = AsyncMock(return_value=True)
            mock_service_cls.return_value = mock_svc_instance

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    confirmar_entrega_por_ml_id(
                        order_id_ml="2000015711968005",
                        db=self.mock_db,
                        current_user=mock_user
                    )
                )
                self.assertTrue(res["success"])
                self.assertIn("confirmada com sucesso", res["message"])
                mock_svc_instance.update_meli_order_status.assert_called_once_with(
                    mock_pedido, target_status="delivered", is_manual=True
                )
            finally:
                loop.close()

    def test_process_meli_webhook_delivered_updates_situacao(self):
        """Verifica que o webhook do Mercado Livre atualiza pedido.situacao para 'Entregue'."""
        svc = MeliService(self.mock_db, self.id_empresa)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 601
        pedido.situacao = models.PedidoSituacaoEnum.despachado
        pedido.meli_status_envio = "shipped"
        pedido.meli_shipment_id = "48351911188"
        pedido.meli_tracking_number = None
        pedido.meli_logistic_type = None
        pedido.meli_historico = []
        pedido.data_finalizacao = None
        pedido.data_entrega = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = pedido
        self.mock_db.query.return_value = mock_query

        mock_client = AsyncMock()
        mock_ship_resp = MagicMock()
        mock_ship_resp.status_code = 200
        mock_ship_resp.json.return_value = {
            "id": 48351911188,
            "order_id": 2000015711968005,
            "status": "delivered",
            "substatus": None,
            "tracking_number": "869838889",
            "logistic_type": "custom"
        }
        mock_client.get.return_value = mock_ship_resp

        with patch.object(svc, "get_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_client
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(svc.process_meli_webhook("shipments", "/shipments/48351911188"))
                self.assertEqual(res.get("status"), "success")
                self.assertEqual(pedido.situacao, models.PedidoSituacaoEnum.entregue)
                self.assertEqual(pedido.meli_status_envio, "delivered")
                self.assertIsNotNone(pedido.data_finalizacao)
                self.assertIsNotNone(pedido.data_entrega)
            finally:
                loop.close()

    def test_process_meli_webhook_out_for_delivery_updates_situacao(self):
        """Verifica que o webhook do ML com substatus 'out_for_delivery' atualiza situacao para saiu_para_entrega."""
        svc = MeliService(self.mock_db, self.id_empresa)
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 602
        pedido.situacao = models.PedidoSituacaoEnum.despachado
        pedido.meli_status_envio = "shipped"
        pedido.meli_shipment_id = "48351911188"
        pedido.meli_tracking_number = None
        pedido.meli_logistic_type = None
        pedido.meli_historico = []
        pedido.data_despacho = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = pedido
        self.mock_db.query.return_value = mock_query

        mock_client = AsyncMock()
        mock_ship_resp = MagicMock()
        mock_ship_resp.status_code = 200
        mock_ship_resp.json.return_value = {
            "id": 48351911188,
            "order_id": 2000015711968005,
            "status": "shipped",
            "substatus": "out_for_delivery",
            "tracking_number": "869838889",
            "logistic_type": "custom"
        }
        mock_client.get.return_value = mock_ship_resp

        with patch.object(svc, "get_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_client
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(svc.process_meli_webhook("shipments", "/shipments/48351911188"))
                self.assertEqual(res.get("status"), "success")
                self.assertEqual(pedido.situacao, models.PedidoSituacaoEnum.saiu_para_entrega)
                self.assertEqual(pedido.meli_status_envio, "shipped (out_for_delivery)")
            finally:
                loop.close()

    def test_intelipost_webhook_delivered_updates_situacao(self):
        """Verifica que o webhook da Intelipost com DELIVERED atualiza situacao para 'Entregue'."""
        from app.api.v1.endpoints.intelipost import _processar_webhook_intelipost
        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 701
        pedido.id_empresa = 1
        pedido.id_pedido_intelipost = "VAR701N"
        pedido.situacao = models.PedidoSituacaoEnum.despachado
        pedido.status_intelipost = "Saiu para entrega"
        pedido.intelipost_tracking_code = "869838889"
        pedido.intelipost_tracking_url = "https://track.example.com"
        pedido.intelipost_historico = []
        pedido.data_finalizacao = None
        pedido.data_entrega = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = pedido
        self.mock_db.query.return_value = mock_query

        payload = {
            "order_number": "VAR701N",
            "status": "Entregue",
            "history": {
                "shipment_order_volume_state": "DELIVERED",
                "shipment_order_volume_state_localized": "Entregue",
                "event_date_iso": "2026-11-09T10:00:00Z"
            }
        }
        mock_request = MagicMock()
        mock_bg = MagicMock()
        mock_user = MagicMock()
        mock_user.id_empresa = 1

        with patch("app.api.v1.endpoints.intelipost.flag_modified"):
            res = _processar_webhook_intelipost(
                request=mock_request,
                background_tasks=mock_bg,
                payload=payload,
                db=self.mock_db,
                current_user=mock_user
            )
        self.assertEqual(res["status"], "success")
        self.assertEqual(pedido.situacao, models.PedidoSituacaoEnum.entregue)
        self.assertEqual(pedido.status_intelipost, "Entregue")
        self.assertIsNotNone(pedido.data_finalizacao)
        self.assertIsNotNone(pedido.data_entrega)

    def test_update_shipment_status_already_delivered_in_ml_updates_situacao(self):
        """Verifica que se o envio já consta como 'delivered' no Mercado Livre, o ERP sincroniza situacao para 'Entregue'."""
        svc = MeliService(self.mock_db, self.id_empresa)
        svc.config = MagicMock()
        svc.config.campo_link_rastreio = None

        pedido = MagicMock(spec=models.Pedido)
        pedido.id = 801
        pedido.situacao = models.PedidoSituacaoEnum.despachado
        pedido.meli_order_id = "2000015711968005"
        pedido.meli_shipment_id = "48351911188"
        pedido.meli_status_envio = "shipped"
        pedido.meli_historico = []
        pedido.data_entrega = None
        pedido.data_finalizacao = None

        mock_client = AsyncMock()
        mock_ship_get = MagicMock()
        mock_ship_get.status_code = 200
        mock_ship_get.json.return_value = {
            "id": 48351911188,
            "mode": "me1",
            "status": "delivered",
            "substatus": None,
            "site_id": "MLB"
        }
        mock_client.get.return_value = mock_ship_get

        with patch.object(svc, "get_client", new_callable=AsyncMock) as mock_get_client, \
             patch.object(svc, "_resolve_all_ml_ids", new_callable=AsyncMock) as mock_res_ids:
            mock_get_client.return_value = mock_client
            mock_res_ids.return_value = {"shipment_id": "48351911188", "order_id": "2000015711968005"}

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    svc.update_shipment_status_by_order(
                        order_id_ml="48351911188",
                        erp_status="Entregue",
                        target_ml_status="delivered",
                        pedido=pedido
                    )
                )
                self.assertTrue(res)
                # Como já estava 'delivered' no ML, não precisa fazer novo POST, mas DEVE sincronizar o pedido local para 'Entregue'
                self.assertEqual(pedido.situacao, models.PedidoSituacaoEnum.entregue)
                self.assertEqual(pedido.meli_status_envio, "delivered")
                self.assertIsNotNone(pedido.data_entrega)
                self.assertIsNotNone(pedido.data_finalizacao)
            finally:
                loop.close()

if __name__ == "__main__":
    unittest.main()


