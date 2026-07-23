import logging
import httpx
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.core.db import models

logger = logging.getLogger(__name__)


class AtendaiService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        self.config = self._get_config()

    def _get_config(self) -> Optional[models.AtendaiConfiguracao]:
        return self.db.query(models.AtendaiConfiguracao).filter(
            models.AtendaiConfiguracao.id_empresa == self.id_empresa,
            models.AtendaiConfiguracao.ativo == True
        ).first()

    def is_configured(self) -> bool:
        return bool(self.config and self.config.url_webhook and self.config.ativo)

    def _serialize_pedido(self, pedido: models.Pedido) -> Dict[str, Any]:
        """Serializa os dados completos de um pedido em formato JSON."""
        cliente_data = None
        if pedido.cliente:
            cliente_data = {
                "id": pedido.cliente.id,
                "nome_razao": pedido.cliente.nome_razao,
                "cpf_cnpj": pedido.cliente.cpf_cnpj,
                "email": getattr(pedido.cliente, "email", None),
                "telefone": getattr(pedido.cliente, "telefone", None),
                "cidade": getattr(pedido.cliente, "cidade", None),
                "estado": str(pedido.cliente.estado) if getattr(pedido.cliente, "estado", None) else None,
            }

        transportadora_data = None
        if pedido.transportadora:
            transportadora_data = {
                "id": pedido.transportadora.id,
                "nome_razao": pedido.transportadora.nome_razao,
                "cpf_cnpj": getattr(pedido.transportadora, "cpf_cnpj", None),
            }

        itens_data = []
        if hasattr(pedido, "itens") and pedido.itens:
            for item in pedido.itens:
                itens_data.append({
                    "id": item.id,
                    "id_produto": item.id_produto,
                    "descricao": getattr(item, "descricao", None) or (item.produto.nome if getattr(item, "produto", None) else None),
                    "sku": getattr(item.produto, "sku", None) if getattr(item, "produto", None) else None,
                    "quantidade": float(item.quantidade) if item.quantidade is not None else 0.0,
                    "valor_unitario": float(item.valor_unitario) if item.valor_unitario is not None else 0.0,
                    "valor_total": float(item.valor_total) if getattr(item, "valor_total", None) is not None else (
                        (float(item.quantidade or 0) * float(item.valor_unitario or 0))
                    ),
                })

        situacao_str = pedido.situacao.value if hasattr(pedido.situacao, 'value') else str(pedido.situacao)

        return {
            "id": pedido.id,
            "situacao": situacao_str,
            "id_empresa": pedido.id_empresa,
            "id_cliente": pedido.id_cliente,
            "cliente": cliente_data,
            "transportadora": transportadora_data,
            "total": float(pedido.total) if pedido.total is not None else 0.0,
            "total_desconto": float(pedido.total_desconto) if pedido.total_desconto is not None else 0.0,
            "valor_frete": float(pedido.valor_frete) if getattr(pedido, "valor_frete", None) is not None else 0.0,
            "data_pedido": str(pedido.data_pedido) if pedido.data_pedido else None,
            "data_despacho": str(pedido.data_despacho) if getattr(pedido, "data_despacho", None) else None,
            "data_validade": str(pedido.data_validade) if getattr(pedido, "data_validade", None) else None,
            "pagamento": getattr(pedido, "pagamento", None),
            "observacao": getattr(pedido, "observacao", None),
            "numero_nf": getattr(pedido, "numero_nf", None),
            "chave_acesso": getattr(pedido, "chave_acesso", None),
            "itens": itens_data,
            "criado_em": pedido.criado_em.isoformat() if getattr(pedido, "criado_em", None) else None,
            "atualizado_em": pedido.atualizado_em.isoformat() if getattr(pedido, "atualizado_em", None) else None,
        }

    def send_order_notification(self, pedido: models.Pedido, event_type: str = "pedido_atualizado") -> bool:
        """Envia notificação HTTP POST para a URL do AtendAI com o cabeçalho X-Webhook-Token."""
        if not self.is_configured():
            logger.debug(f"AtendAI não configurado/ativo para a empresa {self.id_empresa}.")
            return False

        url = self.config.url_webhook
        token = self.config.webhook_token or ""

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Token": token,
            "User-Agent": "ERP-IntegraAI-Webhook/1.0",
        }

        payload = {
            "event": event_type,
            "pedido": self._serialize_pedido(pedido)
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code in [200, 201, 202, 204]:
                    logger.info(f"AtendAI webhook enviado com sucesso para pedido #{pedido.id} (Status {response.status_code})")
                    return True
                else:
                    logger.warning(f"AtendAI webhook retornou status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao enviar webhook AtendAI para pedido #{pedido.id}: {e}")
            return False

    def sync_all_orders(self) -> Dict[str, Any]:
        """Sincroniza todos os pedidos da empresa com o AtendAI."""
        if not self.is_configured():
            return {
                "success": False,
                "message": "Integração AtendAI não está configurada ou ativa nesta empresa.",
                "total": 0
            }

        pedidos = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa
        ).all()

        url = self.config.url_webhook
        token = self.config.webhook_token or ""

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Token": token,
            "User-Agent": "ERP-IntegraAI-Webhook/1.0",
        }

        pedidos_serialized = [self._serialize_pedido(p) for p in pedidos]

        payload = {
            "event": "sync_pedidos",
            "id_empresa": self.id_empresa,
            "total_pedidos": len(pedidos_serialized),
            "pedidos": pedidos_serialized
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code in [200, 201, 202, 204]:
                    return {
                        "success": True,
                        "message": f"{len(pedidos)} pedidos sincronizados com o AtendAI com sucesso.",
                        "total": len(pedidos)
                    }
                else:
                    return {
                        "success": False,
                        "message": f"O webhook AtendAI retornou erro status {response.status_code}: {response.text[:200]}",
                        "total": len(pedidos)
                    }
        except Exception as e:
            logger.error(f"Erro ao sincronizar pedidos com AtendAI: {e}")
            return {
                "success": False,
                "message": f"Erro de conexão ao enviar para o AtendAI: {str(e)}",
                "total": len(pedidos)
            }
