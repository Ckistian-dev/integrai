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
        if not self.db:
            return None
        return self.db.query(models.AtendaiConfiguracao).filter(
            models.AtendaiConfiguracao.id_empresa == self.id_empresa,
            models.AtendaiConfiguracao.ativo == True
        ).first()

    def is_configured(self) -> bool:
        return bool(self.config and self.config.url_webhook and self.config.ativo)

    def _serialize_pedido(self, pedido: models.Pedido) -> Dict[str, Any]:
        """Serializa os dados completos e estruturados de um pedido em formato JSON."""
        
        # --- 1. Empresa ---
        empresa_data = None
        if getattr(pedido, "empresa", None):
            empresa_data = {
                "id": pedido.empresa.id,
                "razao_social": getattr(pedido.empresa, "razao", None),
                "nome_fantasia": getattr(pedido.empresa, "fantasia", None),
                "cnpj": getattr(pedido.empresa, "cnpj", None),
            }

        # --- 2. Cliente ---
        cliente_data = None
        if getattr(pedido, "cliente", None):
            tipo_pessoa = getattr(pedido.cliente, "tipo_pessoa", None)
            tipo_pessoa_str = tipo_pessoa.value if hasattr(tipo_pessoa, "value") else str(tipo_pessoa or "")
            cliente_data = {
                "id": pedido.cliente.id,
                "nome_razao": pedido.cliente.nome_razao,
                "cpf_cnpj": getattr(pedido.cliente, "cpf_cnpj", None),
                "email": getattr(pedido.cliente, "email", None),
                "telefone": getattr(pedido.cliente, "telefone", None),
                "cidade": getattr(pedido.cliente, "cidade", None),
                "estado": str(pedido.cliente.estado) if getattr(pedido.cliente, "estado", None) else None,
                "cep": getattr(pedido.cliente, "cep", None),
                "tipo_pessoa": tipo_pessoa_str,
            }

        # --- 3. Vendedor ---
        vendedor_data = None
        if getattr(pedido, "vendedor", None):
            vendedor_data = {
                "id": pedido.vendedor.id,
                "nome_razao": pedido.vendedor.nome_razao,
                "email": getattr(pedido.vendedor, "email", None),
                "telefone": getattr(pedido.vendedor, "telefone", None),
            }

        # --- 4. Transportadora ---
        transportadora_data = None
        if getattr(pedido, "transportadora", None):
            transportadora_data = {
                "id": pedido.transportadora.id,
                "nome_razao": pedido.transportadora.nome_razao,
                "cpf_cnpj": getattr(pedido.transportadora, "cpf_cnpj", None),
            }

        # --- 5. Endereço de Entrega ---
        endereco_entrega = {
            "logradouro": getattr(pedido, "endereco_logradouro", None),
            "numero": getattr(pedido, "endereco_numero", None),
            "complemento": getattr(pedido, "endereco_complemento", None),
            "bairro": getattr(pedido, "endereco_bairro", None),
            "cidade": getattr(pedido, "endereco_cidade", None),
            "estado": str(pedido.endereco_estado) if getattr(pedido, "endereco_estado", None) else None,
            "cep": getattr(pedido, "endereco_cep", None),
        }

        # --- 6. Formatação de Enums ---
        # Situação do Pedido
        situacao_codigo = pedido.situacao.value if hasattr(pedido.situacao, 'value') else str(pedido.situacao or "")
        situacao_descricao = str(pedido.situacao.name).capitalize() if hasattr(pedido.situacao, 'name') else situacao_codigo

        # Forma de Pagamento
        pagamento_obj = getattr(pedido, "pagamento", None)
        pagamento_codigo = pagamento_obj.value if hasattr(pagamento_obj, 'value') else str(pagamento_obj or "") if pagamento_obj else None
        pagamento_descricao = (
            pagamento_obj.description if hasattr(pagamento_obj, 'description')
            else getattr(pedido, "pagamento_descricao", None) or pagamento_codigo
        )

        # Modalidade de Frete
        frete_obj = getattr(pedido, "modalidade_frete", None)
        frete_codigo = frete_obj.value if hasattr(frete_obj, 'value') else str(frete_obj or "") if frete_obj else None
        frete_desc_map = {
            "0": "0 - CIF (Contratação do Frete por conta do Remetente)",
            "1": "1 - FOB (Contratação do Frete por conta do Destinatário)",
            "2": "2 - Terceiros (Contratação do Frete por conta de Terceiros)",
            "3": "3 - Transporte Próprio por conta do Remetente",
            "4": "4 - Transporte Próprio por conta do Destinatário",
            "9": "9 - Sem Ocorrência de Transporte"
        }
        frete_descricao = frete_desc_map.get(frete_codigo, frete_codigo) if frete_codigo else None

        # Tipo de Operação Fiscal
        operacao_obj = getattr(pedido, "tipo_operacao", None)
        tipo_operacao_codigo = operacao_obj.value if hasattr(operacao_obj, 'value') else str(operacao_obj or "") if operacao_obj else None
        tipo_operacao_descricao = operacao_obj.description if hasattr(operacao_obj, 'description') else tipo_operacao_codigo

        # Indicador de Presença
        presenca_obj = getattr(pedido, "indicador_presenca", None)
        presenca_codigo = presenca_obj.value if hasattr(presenca_obj, 'value') else presenca_obj
        presenca_desc_map = {
            0: "0 - Não se aplica",
            1: "1 - Operação presencial",
            2: "2 - Operação não presencial, pela Internet",
            3: "3 - Operação não presencial, Teleatendimento",
            4: "4 - NFC-e em operação com entrega a domicílio",
            5: "5 - Operação presencial, fora do estabelecimento",
            9: "9 - Operação não presencial, outros"
        }
        presenca_descricao = presenca_desc_map.get(presenca_codigo, str(presenca_codigo)) if presenca_codigo is not None else None

        # Modelo Fiscal
        modelo_fiscal_val = getattr(pedido, "modelo_fiscal", 55)
        modelo_fiscal_descricao = "55 - Nota Fiscal Eletrônica (NF-e)" if modelo_fiscal_val == 55 else "65 - Nota Fiscal de Consumidor Eletrônica (NFC-e)"

        # --- 7. Serialização dos Itens do Pedido ---
        itens_data = []
        if hasattr(pedido, "itens") and pedido.itens:
            for item in pedido.itens:
                if isinstance(item, dict):
                    id_val = item.get("id") or item.get("id_produto")
                    id_prod = item.get("id_produto")
                    desc = item.get("descricao") or item.get("nome") or item.get("produto")
                    sku_val = item.get("sku")
                    qty = float(item.get("quantidade") or 0.0)
                    unit_val = float(item.get("valor_unitario") or 0.0)
                    tot_val = float(item.get("valor_total") if item.get("valor_total") is not None else (qty * unit_val))
                    obs_item = item.get("observacoes")
                else:
                    id_val = getattr(item, "id", None) or getattr(item, "id_produto", None)
                    id_prod = getattr(item, "id_produto", None)
                    prod = getattr(item, "produto", None)
                    desc = getattr(item, "descricao", None) or (getattr(prod, "nome", None) if prod else None)
                    sku_val = getattr(prod, "sku", None) if prod else None
                    qty = float(getattr(item, "quantidade", 0.0) or 0.0)
                    unit_val = float(getattr(item, "valor_unitario", 0.0) or 0.0)
                    tot_val = float(getattr(item, "valor_total", None) if getattr(item, "valor_total", None) is not None else (qty * unit_val))
                    obs_item = getattr(item, "observacoes", None)

                itens_data.append({
                    "id": id_val,
                    "id_produto": id_prod,
                    "descricao": desc,
                    "sku": sku_val,
                    "quantidade": qty,
                    "valor_unitario": unit_val,
                    "valor_total": tot_val,
                    "observacoes": obs_item,
                })

        # --- 8. Retorno Completo do JSON do Pedido ---
        return {
            "id": pedido.id,
            "numero_pedido": pedido.id,
            "situacao": situacao_codigo,
            "situacao_descricao": situacao_descricao,
            "origem_venda": getattr(pedido, "origem_venda", None),
            
            # Dados da Empresa e Cliente
            "id_empresa": pedido.id_empresa,
            "empresa": empresa_data,
            "id_cliente": pedido.id_cliente,
            "cliente": cliente_data,
            "id_vendedor": getattr(pedido, "id_vendedor", None),
            "vendedor": vendedor_data,

            # Endereço e Frete
            "endereco_entrega": endereco_entrega,
            "id_transportadora": getattr(pedido, "id_transportadora", None),
            "transportadora": transportadora_data,
            "modalidade_frete": frete_codigo,
            "modalidade_frete_descricao": frete_descricao,
            "valor_frete": float(pedido.valor_frete) if getattr(pedido, "valor_frete", None) is not None else 0.0,
            "ipi_frete": float(pedido.ipi_frete) if getattr(pedido, "ipi_frete", None) is not None else 0.0,
            "total_frete": float(pedido.total_frete) if getattr(pedido, "total_frete", None) is not None else (
                float(getattr(pedido, "valor_frete", 0.0) or 0.0) + float(getattr(pedido, "ipi_frete", 0.0) or 0.0)
            ),
            "volumes_quantidade": getattr(pedido, "volumes_quantidade", None),
            "volumes_especie": getattr(pedido, "volumes_especie", None),
            "volumes_peso_bruto": float(pedido.volumes_peso_bruto) if getattr(pedido, "volumes_peso_bruto", None) is not None else None,
            "volumes_peso_liquido": float(pedido.volumes_peso_liquido) if getattr(pedido, "volumes_peso_liquido", None) is not None else None,

            # Valores e Pagamento
            "total": float(pedido.total) if pedido.total is not None else 0.0,
            "desconto": float(pedido.desconto) if getattr(pedido, "desconto", None) is not None else 0.0,
            "total_desconto": float(pedido.total_desconto) if pedido.total_desconto is not None else 0.0,
            "pagamento": pagamento_codigo,
            "pagamento_descricao": pagamento_descricao,
            "pagamento_detalhe": getattr(pedido, "pagamento_descricao", None),
            "caixa_destino_origem": getattr(pedido, "caixa_destino_origem", None),

            # Datas e Prazos
            "data_orcamento": str(pedido.data_orcamento) if getattr(pedido, "data_orcamento", None) else None,
            "data_validade": str(pedido.data_validade) if getattr(pedido, "data_validade", None) else None,
            "data_pedido": str(pedido.data_pedido) if getattr(pedido, "data_pedido", None) else None,
            "data_entrega": str(pedido.data_entrega) if getattr(pedido, "data_entrega", None) else None,
            "data_finalizacao": str(pedido.data_finalizacao) if getattr(pedido, "data_finalizacao", None) else None,
            "data_despacho": str(pedido.data_despacho) if getattr(pedido, "data_despacho", None) else None,
            "data_nf": str(pedido.data_nf) if getattr(pedido, "data_nf", None) else None,

            # Dados Fiscais
            "tipo_operacao": tipo_operacao_codigo,
            "tipo_operacao_descricao": tipo_operacao_descricao,
            "numero_nf": getattr(pedido, "numero_nf", None),
            "chave_acesso": getattr(pedido, "chave_acesso", None),
            "chave_nfe_referencia": getattr(pedido, "chave_nfe_referencia", None),
            "protocolo_autorizacao": getattr(pedido, "protocolo_autorizacao", None),
            "status_sefaz": getattr(pedido, "status_sefaz", None),
            "modelo_fiscal": modelo_fiscal_val,
            "modelo_fiscal_descricao": modelo_fiscal_descricao,
            "indicador_presenca": presenca_codigo,
            "indicador_presenca_descricao": presenca_descricao,

            # Observações
            "observacao": getattr(pedido, "observacao", None),
            "observacoes_nf": getattr(pedido, "observacoes_nf", None),

            # Itens do Pedido
            "itens": itens_data,

            # Registro de Sistema
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
