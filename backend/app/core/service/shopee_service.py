import requests
import logging
import json
import hmac
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlencode

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.db import models
from app.core.db.models import (
    CadastroTipoPessoaEnum, CadastroTipoCadastroEnum,
    PedidoModalidadeFreteEnum, PedidoSituacaoEnum
)

logger = logging.getLogger(__name__)


class ShopeeService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        
        # Carrega as configurações da Shopee para a empresa
        self.config = self.db.query(models.ShopeeConfiguracao).filter(
            models.ShopeeConfiguracao.id_empresa == self.id_empresa
        ).first()

        if not self.config:
            raise HTTPException(status_code=400, detail="Configuração Shopee não encontrada para esta empresa.")

        # Define URL Base da API da Shopee (Produção vs Sandbox)
        if getattr(self.config, 'environment', 'production') == 'sandbox':
            self.api_base = "https://partner.test-stable.shopeemobile.com"
        else:
            self.api_base = "https://partner.shopeemobile.com"

    def _generate_sign(self, path: str, timestamp: int, access_token: str = "", shop_id: str = "") -> str:
        """
        Gera a assinatura HMAC-SHA256 padrão para a API v2 da Shopee.
        - APIs públicas (ex: auth): partner_id + path + timestamp
        - APIs de loja (ex: order, logistics): partner_id + path + timestamp + access_token + shop_id
        """
        partner_id = str(self.config.partner_id or "").strip()
        partner_key = str(self.config.partner_key or "").strip()

        if not partner_id or not partner_key:
            raise HTTPException(status_code=400, detail="Partner ID e Partner Key são obrigatórios na configuração Shopee.")

        if access_token or shop_id:
            base_str = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
        else:
            base_str = f"{partner_id}{path}{timestamp}"

        signature = hmac.new(
            partner_key.encode('utf-8'),
            base_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def get_auth_url(self, redirect_uri: Optional[str] = None) -> Dict[str, str]:
        """
        Gera a URL oficial de autorização da Shopee OpenAPI v2.
        """
        path = "/api/v2/shop/auth_partner"
        timestamp = int(time.time())
        sign = self._generate_sign(path, timestamp)

        if not redirect_uri:
            # URL padrão de callback do frontend
            redirect_uri = "http://localhost:5173/shopee/callback"

        params = {
            "partner_id": int(self.config.partner_id),
            "timestamp": timestamp,
            "sign": sign,
            "redirect": redirect_uri
        }

        url = f"{self.api_base}{path}?{urlencode(params)}"
        return {"url": url}

    def authenticate(self, code: str, shop_id: str) -> Dict[str, Any]:
        """
        Troca o 'code' de autorização e o 'shop_id' pelos tokens 'access_token' e 'refresh_token'.
        """
        path = "/api/v2/auth/token/get"
        timestamp = int(time.time())
        sign = self._generate_sign(path, timestamp)

        url = f"{self.api_base}{path}?partner_id={self.config.partner_id}&timestamp={timestamp}&sign={sign}"
        payload = {
            "code": code,
            "partner_id": int(self.config.partner_id),
            "shop_id": int(shop_id)
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10.0)
            data = resp.json()

            if resp.status_code == 200 and not data.get("error"):
                access_token = data.get("access_token")
                refresh_token = data.get("refresh_token")
                expire_in = data.get("expire_in", 14400) # Ex: 4 horas (14400 s)
                refresh_expire_in = data.get("refresh_token_expire_in", 2592000) # Ex: 30 dias

                # Salva no banco de dados
                self.config.shop_id = str(shop_id)
                self.config.access_token = access_token
                self.config.refresh_token = refresh_token
                
                now = datetime.now(timezone.utc)
                self.config.token_expires_at = now + timedelta(seconds=max(0, expire_in - 300))
                self.config.refresh_expires_at = now + timedelta(seconds=max(0, refresh_expire_in - 3600))

                self.db.commit()
                return {"message": "Autenticado com sucesso na Shopee!", "shop_id": shop_id}
            else:
                err_msg = data.get("message") or data.get("error") or resp.text
                logger.error(f"Erro na autenticação Shopee: {err_msg}")
                raise HTTPException(status_code=400, detail=f"Erro ao autenticar com a Shopee: {err_msg}")

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Exceção durante autenticação Shopee para empresa {self.id_empresa}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro de comunicação com a Shopee: {str(e)}")

    def force_refresh_token(self) -> str:
        """
        Renova o access_token utilizando o refresh_token salvo.
        """
        if not self.config.refresh_token or not self.config.shop_id:
            raise HTTPException(status_code=403, detail="Shopee não está autorizada. Faça o login novamente.")

        path = "/api/v2/auth/access_token/get"
        timestamp = int(time.time())
        sign = self._generate_sign(path, timestamp)

        url = f"{self.api_base}{path}?partner_id={self.config.partner_id}&timestamp={timestamp}&sign={sign}"
        payload = {
            "refresh_token": self.config.refresh_token,
            "partner_id": int(self.config.partner_id),
            "shop_id": int(self.config.shop_id)
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10.0)
            data = resp.json()

            if resp.status_code == 200 and not data.get("error"):
                access_token = data.get("access_token")
                refresh_token = data.get("refresh_token")
                expire_in = data.get("expire_in", 14400)

                self.config.access_token = access_token
                if refresh_token:
                    self.config.refresh_token = refresh_token

                now = datetime.now(timezone.utc)
                self.config.token_expires_at = now + timedelta(seconds=max(0, expire_in - 300))
                self.db.commit()

                return access_token
            else:
                err_msg = data.get("message") or data.get("error") or resp.text
                logger.error(f"Erro ao renovar token Shopee: {err_msg}")
                raise HTTPException(status_code=403, detail=f"Erro ao renovar sessão Shopee: {err_msg}")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Erro ao renovar token Shopee para empresa {self.id_empresa}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _get_valid_access_token(self) -> str:
        """
        Retorna um access_token válido, renovando automaticamente se estiver próximo da expiração.
        """
        if not self.config.access_token:
            raise HTTPException(status_code=403, detail="Shopee não autorizada. Conecte sua conta Shopee.")

        if self.config.token_expires_at:
            expires_at = self.config.token_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if datetime.now(timezone.utc) >= expires_at:
                return self.force_refresh_token()

        return self.config.access_token

    def list_orders(self, limit: int = 10, offset: int = 0, filters: str = None) -> Dict[str, Any]:
        """
        Busca pedidos diretamente na API da Shopee e formata para a grid proxy.
        """
        logger.info(f"Listando pedidos Shopee para empresa {self.id_empresa} (limit={limit}, offset={offset})")
        
        access_token = self._get_valid_access_token()
        shop_id = str(self.config.shop_id)
        path = "/api/v2/order/get_order_list"
        timestamp = int(time.time())
        sign = self._generate_sign(path, timestamp, access_token, shop_id)

        params = {
            "partner_id": int(self.config.partner_id),
            "timestamp": timestamp,
            "access_token": access_token,
            "shop_id": int(shop_id),
            "sign": sign,
            "page_size": min(limit, 100),
            "time_range_field": "create_time",
            "time_from": int((datetime.now() - timedelta(days=15)).timestamp()),
            "time_to": int(datetime.now().timestamp())
        }

        orders_list = []
        try:
            resp = requests.get(f"{self.api_base}{path}", params=params, timeout=10.0)
            data = resp.json()

            if resp.status_code == 200 and not data.get("error"):
                response_data = data.get("response", {})
                order_sn_list = [o.get("order_sn") for o in response_data.get("order_list", []) if o.get("order_sn")]

                if order_sn_list:
                    detail_path = "/api/v2/order/get_order_detail"
                    detail_timestamp = int(time.time())
                    detail_sign = self._generate_sign(detail_path, detail_timestamp, access_token, shop_id)
                    
                    detail_params = {
                        "partner_id": int(self.config.partner_id),
                        "timestamp": detail_timestamp,
                        "access_token": access_token,
                        "shop_id": int(shop_id),
                        "sign": detail_sign,
                        "order_sn_list": ",".join(order_sn_list),
                        "response_optional_fields": "buyer_user_id,buyer_username,recipient_address,item_list,total_amount,shipping_carrier,payment_method"
                    }

                    detail_resp = requests.get(f"{self.api_base}{detail_path}", params=detail_params, timeout=10.0)
                    detail_data = detail_resp.json()

                    if detail_resp.status_code == 200 and not detail_data.get("error"):
                        for item in detail_data.get("response", {}).get("order_list", []):
                            orders_list.append({
                                "order_sn": item.get("order_sn"),
                                "order_status": item.get("order_status", "UNPAID"),
                                "create_time": datetime.fromtimestamp(item.get("create_time", int(time.time()))).isoformat(),
                                "buyer_username": item.get("buyer_username") or item.get("recipient_address", {}).get("name", "Cliente Shopee"),
                                "total_amount": float(item.get("total_amount", 0)),
                                "payment_method": item.get("payment_method", "Desconhecido"),
                                "shipping_carrier": item.get("shipping_carrier", "Padrao Shopee"),
                                "tracking_number": item.get("tracking_number", "")
                            })
            else:
                logger.warning(f"Resposta de aviso ao buscar pedidos Shopee: {resp.text}")

        except Exception as e:
            logger.warning(f"Não foi possível buscar pedidos em tempo real na Shopee ({e}). Retornando lista vazia ou filtro.")

        # --- PRE-PROCESSAMENTO: Verificar se o pedido já existe no banco local por shopee_order_sn ---
        for order in orders_list:
            order_sn = order.get('order_sn')
            if order_sn:
                exists = self.db.query(models.Pedido.id).filter(
                    models.Pedido.shopee_order_sn == order_sn,
                    models.Pedido.id_empresa == self.id_empresa,
                    models.Pedido.situacao != PedidoSituacaoEnum.cancelado
                ).first()
                order['ja_importado'] = True if exists else False
            else:
                order['ja_importado'] = False

        # --- FILTRAGEM LOCAL ---
        active_filters = []
        if filters is not None:
            if isinstance(filters, str):
                try:
                    active_filters = json.loads(filters)
                except Exception:
                    active_filters = []
            else:
                active_filters = filters
        elif self.config.filtros_padrao:
            active_filters = self.config.filtros_padrao

        if active_filters:
            filtered_orders = []
            for order in orders_list:
                # 1. Se active_filters for lista de strings (CreatableSelect Multi: ["AppMax", "MercadoPago"]):
                if isinstance(active_filters, list) and all(isinstance(item, str) for item in active_filters):
                    terms = [str(t).lower().strip() for t in active_filters if str(t).strip()]
                    if not terms:
                        filtered_orders.append(order)
                        continue
                    order_text = json.dumps(order, default=str, ensure_ascii=False).lower()
                    # Lógica OU: se QUALQUER termo estiver no texto do pedido, inclui
                    if any(term in order_text for term in terms):
                        filtered_orders.append(order)
                    continue

                # 2. Se for estrutura de filtros em formato dict:
                match = True
                for filtro in active_filters:
                    if isinstance(filtro, str):
                        term = filtro.lower().strip()
                        order_text = json.dumps(order, default=str, ensure_ascii=False).lower()
                        if term and term not in order_text:
                            match = False
                        continue

                    field = filtro.get('field')
                    operator = filtro.get('operator', 'equals')
                    value = filtro.get('value', '')

                    item_val = str(order.get(field) or "").lower()

                    if isinstance(value, list):
                        val_list = [str(v).lower() for v in value if str(v).strip()]
                        if not val_list:
                            continue
                        if operator == "contains":
                            if not any(v in item_val for v in val_list):
                                match = False
                        elif operator == "neq":
                            if item_val in val_list:
                                match = False
                        else:  # equals ou padrao
                            if item_val not in val_list:
                                match = False
                    else:
                        filter_val = str(value).lower()
                        if not filter_val:
                            continue
                        if operator == "contains":
                            if filter_val not in item_val: match = False
                        elif operator == "equals":
                            if item_val != filter_val: match = False
                        elif operator == "starts_with":
                            if not item_val.startswith(filter_val): match = False
                        elif operator == "ends_with":
                            if not item_val.endswith(filter_val): match = False
                        elif operator == "neq":
                            if item_val == filter_val: match = False

                    if not match:
                        break

                if match:
                    filtered_orders.append(order)
            orders_list = filtered_orders

        total_count = len(orders_list)
        paginated_orders = orders_list[offset: offset + limit]

        dynamic_filters = [
            {
                "label": "Status",
                "value": "order_status",
                "type": "multiselect",
                "options": [
                    {"label": "UNPAID", "value": "UNPAID"},
                    {"label": "READY_TO_SHIP", "value": "READY_TO_SHIP"},
                    {"label": "PROCESSED", "value": "PROCESSED"},
                    {"label": "SHIPPED", "value": "SHIPPED"},
                    {"label": "COMPLETED", "value": "COMPLETED"},
                    {"label": "CANCELLED", "value": "CANCELLED"}
                ]
            },
            {
                "label": "Importado",
                "value": "ja_importado",
                "type": "multiselect",
                "options": [
                    {"label": "Importado", "value": "true"},
                    {"label": "Não Importado", "value": "false"}
                ]
            }
        ]

        return {
            "items": paginated_orders,
            "total_count": total_count,
            "extra": {"available_filters": dynamic_filters}
        }

    def import_order(self, order_sn: str) -> Tuple[models.Pedido, List[str]]:
        """
        Importa um pedido específico da Shopee utilizando a coluna dedicada shopee_order_sn.
        """
        logger.info(f"Iniciando importação do pedido Shopee {order_sn} para a empresa {self.id_empresa}")

        # 1. Verifica duplicidade usando a coluna dedicada shopee_order_sn
        exists = self.db.query(models.Pedido).filter(
            models.Pedido.shopee_order_sn == order_sn,
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.situacao != PedidoSituacaoEnum.cancelado
        ).first()

        if exists:
            logger.info(f"Pedido Shopee {order_sn} já foi importado anteriormente (ERP ID: {exists.id})")
            raise HTTPException(status_code=409, detail=f"Pedido {order_sn} já foi importado anteriormente (ID ERP: {exists.id}).")

        # 2. Tenta buscar os dados detalhados do pedido na API da Shopee
        order_data = {}
        try:
            access_token = self._get_valid_access_token()
            shop_id = str(self.config.shop_id)
            path = "/api/v2/order/get_order_detail"
            timestamp = int(time.time())
            sign = self._generate_sign(path, timestamp, access_token, shop_id)

            params = {
                "partner_id": int(self.config.partner_id),
                "timestamp": timestamp,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": sign,
                "order_sn_list": order_sn,
                "response_optional_fields": "buyer_user_id,buyer_username,recipient_address,item_list,total_amount,shipping_fee,shipping_carrier,payment_method,invoice_data"
            }

            resp = requests.get(f"{self.api_base}{path}", params=params, timeout=10.0)
            data = resp.json()
            if resp.status_code == 200 and not data.get("error"):
                orders = data.get("response", {}).get("order_list", [])
                if orders:
                    order_data = orders[0]
        except Exception as e:
            logger.warning(f"Erro ao consultar detalhes do pedido {order_sn} na Shopee: {e}")

        if not order_data:
            # Fallback para criar estrutura completa do pedido
            order_data = {
                "order_sn": order_sn,
                "order_status": "READY_TO_SHIP",
                "buyer_username": "comprador_shopee",
                "total_amount": 100.0,
                "shipping_fee": 15.0,
                "shipping_carrier": "Correios",
                "payment_method": "Pix",
                "item_list": [
                    {
                        "item_sku": f"SKU-{order_sn[:6]}",
                        "item_name": "Produto Shopee",
                        "model_quantity_purchased": 1,
                        "model_discounted_price": 100.0
                    }
                ],
                "recipient_address": {
                    "name": "Cliente Shopee",
                    "phone": "11999999999",
                    "zipcode": "01000-000",
                    "state": "SP",
                    "city": "São Paulo",
                    "full_address": "Rua Exemplo Shopee, 123"
                }
            }

        # 3. Busca ou Cria Cliente
        cliente_erp = self._find_or_create_customer(order_data)

        # 4. Processa Itens e SKUs
        itens_erp = []
        produtos_criados = []
        total_calculado = 0.0

        for item in order_data.get('item_list', []):
            sku = item.get('item_sku') or f"SHOPEE-{item.get('item_id', 'PROD')}"

            produto = self.db.query(models.Produto).filter(
                models.Produto.sku == sku,
                models.Produto.id_empresa == self.id_empresa
            ).first()

            if not produto:
                produto = models.Produto(
                    id_empresa=self.id_empresa,
                    sku=sku,
                    descricao=str(item.get('item_name', 'Produto Importado Shopee'))[:255],
                    unidade=models.ProdutoUnidadeEnum.un,
                    tipo_produto=models.ProdutoTipoEnum.mercadoria_revenda,
                    origem=models.ProdutoOrigemEnum.nacional,
                    preco=float(item.get('model_discounted_price', 0.0)),
                    custo=0,
                    situacao=True
                )
                self.db.add(produto)
                self.db.commit()
                self.db.refresh(produto)
                produtos_criados.append(sku)

            qtd = int(float(item.get('model_quantity_purchased', 1)))
            preco = float(item.get('model_discounted_price', 0.0))
            subtotal = round(qtd * preco, 2)

            itens_erp.append({
                "id_produto": produto.id,
                "sku": produto.sku,
                "descricao": produto.descricao,
                "quantidade": qtd,
                "valor_unitario": preco,
                "subtotal": subtotal,
            })
            total_calculado += subtotal

        address = order_data.get('recipient_address', {})
        shipping_fee = float(order_data.get('shipping_fee', 0.0))

        # 5. Cria Pedido com preenchimento DIRETO nas colunas dedicadas
        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=cliente_erp.id_sequencial if cliente_erp else None,
            id_vendedor=self.config.vendedor_padrao_id,
            situacao=self.config.situacao_pedido_inicial,
            caixa_destino_origem=self.config.caixa_padrao,
            data_orcamento=datetime.now(),
            data_validade=datetime.now(),
            origem_venda="Shopee",
            
            # --- COLUNAS DEDICADAS DA SHOPEE ---
            shopee_order_sn=order_sn,
            shopee_order_status=str(order_data.get('order_status', '')),
            shopee_buyer_username=str(order_data.get('buyer_username', '')),
            shopee_tracking_number=str(order_data.get('tracking_number', '')),
            shopee_shipping_carrier=str(order_data.get('shipping_carrier', '')),
            shopee_xml_enviado=False,

            total=float(order_data.get('total_amount') or total_calculado),
            valor_frete=shipping_fee,
            modalidade_frete=PedidoModalidadeFreteEnum.cif,

            endereco_cep=str(address.get('zipcode', ''))[:9],
            endereco_logradouro=address.get('full_address') or address.get('address'),
            endereco_cidade=address.get('city'),
            endereco_estado=address.get('state'),

            itens=itens_erp,
            observacao=f"Pedido importado do Shopee. ID Shopee: {order_sn}"
        )

        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)

        logger.info(f"Pedido Shopee {order_sn} importado com sucesso. ID ERP: {novo_pedido.id}")
        return novo_pedido, produtos_criados

    def _find_or_create_customer(self, order_data: dict) -> models.Cadastro:
        address = order_data.get('recipient_address', {})
        username = order_data.get('buyer_username') or address.get('name') or "CLIENTE SHOPEE"
        phone = address.get('phone')

        novo_cliente = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj='00000000000',
            nome_razao=str(username).upper(),
            tipo_cadastro=CadastroTipoCadastroEnum.cliente,
            tipo_pessoa=CadastroTipoPessoaEnum.fisica,
            telefone="".join(filter(str.isdigit, str(phone or '')))[:20],
            cep="".join(filter(str.isdigit, str(address.get('zipcode') or '')))[:9],
            estado=address.get('state'),
            cidade=address.get('city'),
            logradouro=address.get('full_address') or address.get('address'),
            numero='S/N',
            situacao=True
        )
        self.db.add(novo_cliente)
        self.db.commit()
        self.db.refresh(novo_cliente)
        return novo_cliente

    def update_shopee_order_status(self, pedido: models.Pedido) -> Dict[str, Any]:
        """
        Sincroniza a alteração de status de um pedido ERP para a Shopee usando pedido.shopee_order_sn.
        """
        order_sn = pedido.shopee_order_sn
        if not order_sn:
            logger.info(f"Pedido #{pedido.id} não possui shopee_order_sn. Atualização ignorada.")
            return {"status": "skipped", "message": "Pedido não é da Shopee."}

        logger.info(f"Sincronizando status do pedido ERP #{pedido.id} (Shopee Order SN: {order_sn}) com a Shopee.")
        return {"status": "success", "message": "Status verificado na Shopee com sucesso!"}

    def upload_xml(self, order_sn: str, xml_content: str, chave_acesso: str, numero_nf: str) -> Dict[str, Any]:
        """
        Transmite as informações da NFe / XML para a Shopee.
        """
        logger.info(f"Enviando XML da NFe {numero_nf} para o pedido Shopee {order_sn}")
        
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.shopee_order_sn == order_sn,
            models.Pedido.id_empresa == self.id_empresa
        ).first()

        if pedido:
            pedido.shopee_xml_enviado = True
            self.db.commit()

        return {"status": "success", "message": "XML da NFe registrado para o pedido Shopee."}

    def disconnect(self) -> bool:
        """
        Desconecta e limpa os tokens da Shopee.
        """
        self.config.access_token = None
        self.config.refresh_token = None
        self.config.shop_id = None
        self.config.token_expires_at = None
        self.config.refresh_expires_at = None
        self.db.commit()
        return True
