import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
import asyncio

from fastapi import BackgroundTasks
from fastapi.security import HTTPBasicCredentials
from app.core.db import models
from app.api.v1.endpoints.intelipost import (
    verify_intelipost_basic_auth,
    receber_webhook_intelipost,
    _auth_cache,
    _ACTIVE_SYNC_ORDERS,
    _RECENT_PAYLOAD_HASHES,
    _IN_FLIGHT_PAYLOADS,
    _LAST_SYNCED_STATE,
    _ORDER_SYNC_LOCKS,
    _sync_meli_order_background,
    _sync_shopee_order_background
)

class TestIntelipostWebhook(unittest.TestCase):
    def setUp(self):
        _auth_cache.clear()
        _ACTIVE_SYNC_ORDERS.clear()
        _RECENT_PAYLOAD_HASHES.clear()
        _IN_FLIGHT_PAYLOADS.clear()
        _LAST_SYNCED_STATE.clear()
        _ORDER_SYNC_LOCKS.clear()
        self.mock_db = MagicMock()
        self.patcher = patch("app.api.v1.endpoints.intelipost.flag_modified")
        self.mock_flag_modified = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_basic_auth_caching(self):
        """Testa se o cache do Basic Auth evita consultas repetidas ao banco de dados."""
        creds = HTTPBasicCredentials(username="fabio@var.com", password="secret_password")
        mock_user = MagicMock(spec=models.Usuario)
        mock_user.id = 3
        mock_user.id_empresa = 1

        with patch("app.crud.crud_user.authenticate_user", return_value=mock_user) as mock_auth:
            # 1ª chamada: Cache miss -> chama crud_user.authenticate_user
            user1 = verify_intelipost_basic_auth(creds, self.mock_db)
            self.assertIsNotNone(user1)
            self.assertEqual(user1.id, 3)
            self.assertEqual(user1.id_empresa, 1)
            self.assertEqual(mock_auth.call_count, 1)

            # 2ª chamada: Cache hit -> NÃO deve chamar crud_user.authenticate_user novamente
            user2 = verify_intelipost_basic_auth(creds, self.mock_db)
            self.assertIsNotNone(user2)
            self.assertEqual(user2.id, 3)
            self.assertEqual(user2.id_empresa, 1)
            self.assertEqual(mock_auth.call_count, 1, "Cache hit deveria evitar nova chamada ao DB")

    def test_receber_webhook_find_pedido_and_update(self):
        """Testa processamento do webhook com localização por id_pedido_intelipost e extração de dígitos."""
        mock_pedido = MagicMock(spec=models.Pedido)
        mock_pedido.id = 100
        mock_pedido.id_empresa = 1
        mock_pedido.id_sequencial = 3821
        mock_pedido.status_intelipost = "EM_TRANSITO"
        mock_pedido.intelipost_historico = []
        mock_pedido.intelipost_tracking_code = "TRK123"
        mock_pedido.intelipost_tracking_url = "https://tracking.com"
        mock_pedido.rastreio_enviado = True
        mock_pedido.meli_order_id = "2000018714798792"
        mock_pedido.shopee_order_sn = None
        mock_pedido.origem_venda = "Mercado Livre"
        mock_pedido.observacao = ""
        mock_pedido.chave_acesso = "12345678901234567890123456789012345678901234"
        mock_pedido.numero_nf = "1001"
        mock_pedido.data_entrega = None
        mock_pedido.data_finalizacao = None
        mock_pedido.data_despacho = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pedido
        self.mock_db.query.return_value = mock_query

        bg_tasks = MagicMock(spec=BackgroundTasks)
        mock_user = MagicMock()
        mock_user.id = 3
        mock_user.id_empresa = 1

        payload = {
            "order_number": "VAR3821N",
            "shipment_order_id": "9999",
            "history": {
                "shipment_order_volume_state": "DELIVERED",
                "shipment_order_volume_state_localized": "Entregue",
                "event_date_iso": "2026-10-28T12:00:00Z"
            }
        }
        mock_request = MagicMock()
        mock_request.url = "http://testserver/api/v1/intelipost/webhook"
        mock_request.headers = {}

        result = receber_webhook_intelipost(
            request=mock_request,
            background_tasks=bg_tasks,
            payload=payload,
            db=self.mock_db,
            current_user=mock_user
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_pedido.status_intelipost, "Entregue")
        self.mock_db.commit.assert_called_once()
        # Como o status mudou de 'EM_TRANSITO' para 'Entregue', deve ter disparado a sincronização em background
        bg_tasks.add_task.assert_called_once()

    def test_exact_duplicate_payload_excluded(self):
        """Testa se requisições com payloads exatamente idênticos são descartadas como duplicatas exatas."""
        mock_pedido = MagicMock(spec=models.Pedido)
        mock_pedido.id = 100
        mock_pedido.id_empresa = 1
        mock_pedido.status_intelipost = "EM_TRANSITO"
        mock_pedido.intelipost_historico = []
        mock_pedido.intelipost_tracking_code = "TRK123"
        mock_pedido.intelipost_tracking_url = "https://tracking.com"
        mock_pedido.rastreio_enviado = True
        mock_pedido.meli_order_id = "2000018714798792"
        mock_pedido.origem_venda = "Mercado Livre"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pedido
        self.mock_db.query.return_value = mock_query

        bg_tasks = MagicMock(spec=BackgroundTasks)
        mock_user = MagicMock()
        mock_user.id = 3
        mock_user.id_empresa = 1

        payload = {
            "order_number": "VAR3821N",
            "shipment_order_id": "9999",
            "history": {
                "shipment_order_volume_state": "DELIVERED",
                "shipment_order_volume_state_localized": "Entregue",
                "event_date_iso": "2026-10-28T12:00:00Z"
            }
        }
        mock_request = MagicMock()
        mock_request.url = "http://testserver/api/v1/intelipost/webhook"
        mock_request.headers = {}

        # 1ª chamada com o payload: processa normalmente
        res1 = receber_webhook_intelipost(
            request=mock_request,
            background_tasks=bg_tasks,
            payload=payload,
            db=self.mock_db,
            current_user=mock_user
        )
        self.assertEqual(res1["status"], "success")
        self.assertFalse(res1.get("duplicada_ignorada", False))
        self.assertEqual(self.mock_db.commit.call_count, 1)

        # 2ª chamada com o payload EXATAMENTE IDÊNTICO: deve ignorar como duplicata exata
        res2 = receber_webhook_intelipost(
            request=mock_request,
            background_tasks=bg_tasks,
            payload=payload,
            db=self.mock_db,
            current_user=mock_user
        )
        self.assertEqual(res2["status"], "success")
        self.assertTrue(res2.get("duplicada_ignorada"))
        # db.commit não deve ser chamado novamente!
        self.assertEqual(self.mock_db.commit.call_count, 1)

    def test_exact_duplicate_occurrence_in_history_excluded(self):
        """Testa se ocorrências exatamente idênticas já no histórico do pedido são descartadas sem duplicar."""
        mock_pedido = MagicMock(spec=models.Pedido)
        mock_pedido.id = 101
        mock_pedido.id_empresa = 1
        mock_pedido.status_intelipost = "Entregue"
        mock_pedido.intelipost_tracking_code = "TRK123"
        mock_pedido.intelipost_tracking_url = "https://tracking.com"
        mock_pedido.intelipost_mensagem = "Entregue ao cliente"
        # Já existe exatamente essa ocorrência registrada no histórico:
        mock_pedido.intelipost_historico = [{
            "status": "Entregue",
            "state": "DELIVERED",
            "micro_state": None,
            "provider_message": "Entregue ao cliente",
            "event_date": "2026-10-28T12:00:00Z",
            "tracking_code": "TRK123",
            "tracking_url": "https://tracking.com",
            "volume_number": None,
            "recebido_em": "2026-10-28T12:01:00"
        }]
        mock_pedido.rastreio_enviado = True
        mock_pedido.meli_order_id = "2000018714798792"
        mock_pedido.origem_venda = "Mercado Livre"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pedido
        self.mock_db.query.return_value = mock_query

        bg_tasks = MagicMock(spec=BackgroundTasks)
        mock_user = MagicMock()
        mock_user.id = 3
        mock_user.id_empresa = 1

        # Payload diferente no outer envelope, mas a ocorrência interna é 100% idêntica
        payload = {
            "order_number": "VAR3821N",
            "client_timestamp": 1234567,  # garante hash de payload diferente
            "history": {
                "shipment_order_volume_state": "DELIVERED",
                "shipment_order_volume_state_localized": "Entregue",
                "provider_message": "Entregue ao cliente",
                "event_date_iso": "2026-10-28T12:00:00Z",
                "tracking_code": "TRK123",
                "tracking_url": "https://tracking.com"
            }
        }
        mock_request = MagicMock()
        mock_request.url = "http://testserver/api/v1/intelipost/webhook"
        mock_request.headers = {}

        result = receber_webhook_intelipost(
            request=mock_request,
            background_tasks=bg_tasks,
            payload=payload,
            db=self.mock_db,
            current_user=mock_user
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(result.get("duplicada_ignorada"))
        # Histórico NÃO deve ser duplicado
        self.assertEqual(len(mock_pedido.intelipost_historico), 1)
        # Nenhuma transação no banco realizada
        self.mock_db.commit.assert_not_called()

    def test_non_identical_occurrence_processed_without_loss(self):
        """Testa se ocorrência com qualquer campo diferente (ex: nova mensagem ou data) é processada sem perda."""
        mock_pedido = MagicMock(spec=models.Pedido)
        mock_pedido.id = 102
        mock_pedido.id_empresa = 1
        mock_pedido.status_intelipost = "EM_TRANSITO"
        mock_pedido.intelipost_tracking_code = "TRK123"
        mock_pedido.intelipost_tracking_url = "https://tracking.com"
        mock_pedido.intelipost_mensagem = "Objeto postado"
        mock_pedido.intelipost_historico = [{
            "status": "EM_TRANSITO",
            "state": "SHIPPED",
            "micro_state": None,
            "provider_message": "Objeto postado",
            "event_date": "2026-10-28T10:00:00Z",
            "tracking_code": "TRK123",
            "tracking_url": "https://tracking.com",
            "volume_number": None,
            "recebido_em": "2026-10-28T10:05:00"
        }]
        mock_pedido.rastreio_enviado = True
        mock_pedido.meli_order_id = "2000018714798792"
        mock_pedido.origem_venda = "Mercado Livre"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pedido
        self.mock_db.query.return_value = mock_query

        bg_tasks = MagicMock(spec=BackgroundTasks)
        mock_user = MagicMock()
        mock_user.id = 3
        mock_user.id_empresa = 1

        # Mesma situação (EM_TRANSITO), mas NOVA data e NOVA mensagem (não é duplicata exata!)
        payload = {
            "order_number": "VAR3821N",
            "history": {
                "shipment_order_volume_state": "IN_TRANSIT",
                "shipment_order_volume_state_localized": "EM_TRANSITO",
                "provider_message": "Objeto saiu para rota de entrega",
                "event_date_iso": "2026-10-28T15:30:00Z",
                "tracking_code": "TRK123",
                "tracking_url": "https://tracking.com"
            }
        }
        mock_request = MagicMock()
        mock_request.url = "http://testserver/api/v1/intelipost/webhook"
        mock_request.headers = {}

        result = receber_webhook_intelipost(
            request=mock_request,
            background_tasks=bg_tasks,
            payload=payload,
            db=self.mock_db,
            current_user=mock_user
        )

        self.assertEqual(result["status"], "success")
        self.assertFalse(result.get("duplicada_ignorada", False))
        # Deve ter atualizado a mensagem no pedido
        self.assertEqual(mock_pedido.intelipost_mensagem, "Objeto saiu para rota de entrega")
        # Deve ter adicionado a nova ocorrência ao histórico (agora tem 2)
        self.assertEqual(len(mock_pedido.intelipost_historico), 2)
        # Deve ter commitado a alteração
        self.mock_db.commit.assert_called_once()

    def test_background_task_deduplication(self):
        """Testa se chamadas de sincronização com o mesmo estado são deduplicadas."""
        async def run_dedup_test():
            call_count = 0
            async def fake_update(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.05)

            mock_session = MagicMock()
            mock_pedido = MagicMock()
            mock_pedido.status_intelipost = "DELIVERED"
            mock_pedido.intelipost_tracking_code = "TRK123"
            mock_pedido.intelipost_tracking_url = "https://tracking.com"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_pedido

            with patch("app.core.db.database.SessionLocal", return_value=mock_session), \
                 patch("app.core.service.meli_service.MeliService.update_meli_order_status", side_effect=fake_update):
                # Executa 3 chamadas simultâneas para o mesmo pedido_id=999 com o mesmo estado
                await asyncio.gather(
                    _sync_meli_order_background(999, 1),
                    _sync_meli_order_background(999, 1),
                    _sync_meli_order_background(999, 1)
                )

            # Somente 1 deve ter executado, as outras 2 devem ter sido ignoradas por deduplicação de estado idêntico
            self.assertEqual(call_count, 1)

        asyncio.run(run_dedup_test())

    def test_background_task_processes_different_states_without_loss(self):
        """Testa se chamadas sequenciais com estados DIFERENTES são ambas executadas sem perda."""
        async def run_diff_state_test():
            call_count = 0
            synced_statuses = []
            async def fake_update(pedido, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                synced_statuses.append(pedido.status_intelipost)
                await asyncio.sleep(0.01)

            mock_session = MagicMock()
            mock_pedido = MagicMock()
            mock_pedido.status_intelipost = "EM_TRANSITO"
            mock_pedido.intelipost_tracking_code = "TRK123"
            mock_pedido.intelipost_tracking_url = "https://tracking.com"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_pedido

            with patch("app.core.db.database.SessionLocal", return_value=mock_session), \
                 patch("app.core.service.meli_service.MeliService.update_meli_order_status", side_effect=fake_update):
                
                # 1. Primeira sincronização: EM_TRANSITO
                await _sync_meli_order_background(888, 1)
                
                # 2. O pedido muda de status para ENTREGUE
                mock_pedido.status_intelipost = "ENTREGUE"
                
                # 3. Segunda sincronização: ENTREGUE (não idêntica!)
                await _sync_meli_order_background(888, 1)

            # Ambas as chamadas devem ter sido executadas! Nenhuma foi perdida!
            self.assertEqual(call_count, 2)
            self.assertEqual(synced_statuses, ["EM_TRANSITO", "ENTREGUE"])

        asyncio.run(run_diff_state_test())

if __name__ == "__main__":
    unittest.main()

