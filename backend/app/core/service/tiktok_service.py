import requests
import logging
import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException
from app.core.db import models
from app.core.db.models import (
    CadastroTipoPessoaEnum, CadastroTipoCadastroEnum,
    PedidoModalidadeFreteEnum
)

import hmac
import hashlib
import time
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class TiktokService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        
        # Carrega configurações
        self.config = self.db.query(models.TiktokConfiguracao).filter(
            models.TiktokConfiguracao.id_empresa == self.id_empresa
        ).first()

        if not self.config:
            raise HTTPException(status_code=400, detail="Configuração Tiktok Shop não encontrada.")
            
        # URL base oficial da API do Tiktok Shop (V2 - Global/Rest of World)
        self.api_base = "https://open-api.tiktokglobalshop.com"
        self.auth_url_base = "https://auth.tiktok-shops.com/oauth/v2/authorize"

    def _generate_signature(self, path, params):
        """Gera a assinatura HMAC-SHA256 exigida pelo Tiktok"""
        # 1. Ordena parâmetros por chave (exceto o próprio sign)
        sorted_keys = sorted(params.keys())
        
        # 2. Concatena path + params (key1value1key2value2...)
        sign_str = path
        for key in sorted_keys:
            if key != "sign":
                sign_str += f"{key}{params[key]}"
        
        # 3. Adiciona app_secret no início e no fim (algumas APIs pedem isso)
        # No Tiktok Shop, a lógica é concatenar a string e assinar com o secret.
        # Referência: https://partner.tiktokshop.com/doc/page/262507
        
        signature = hmac.new(
            self.config.app_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature

    def get_auth_url(self):
        """Gera a URL para redirecionar o usuário e obter o 'code'"""
        params = {
            "app_key": self.config.app_key,
            "state": str(self.id_empresa)
        }
        url = f"{self.auth_url_base}?{urlencode(params)}"
        return {"url": url}

    def authenticate(self, code: str):
        """Troca o 'code' pelo 'access_token'"""
        # No V2, o endpoint de token fica em auth.tiktok-shops.com
        url = "https://auth.tiktok-shops.com/api/v2/token/get"
        
        params = {
            "app_key": self.config.app_key,
            "app_secret": self.config.app_secret,
            "auth_code": code,
            "grant_type": "authorized_code"
        }
        
        try:
            resp = requests.get(url, params=params)
            data = resp.json()
            
            if data.get("code") == 0:
                auth_data = data.get("data", {})
                
                # Salva no banco de dados
                self.config.access_token = auth_data.get("access_token")
                self.config.refresh_token = auth_data.get("refresh_token")
                # Outros campos se necessário
                
                self.db.commit()
                return {"message": "Autenticado com sucesso!", "data": auth_data}
            else:
                raise HTTPException(status_code=400, detail=data.get("message", "Erro desconhecido na autenticação"))
                
        except Exception as e:
            logger.error(f"Erro ao autenticar no Tiktok: {e}")
            raise e


    def _get_headers(self):
        """
        Retorna os headers de autenticação para a API do Tiktok Shop.
        """
        if not self.config.access_token:
            raise HTTPException(
                status_code=500, 
                detail="Configuração de integração incompleta (Access Token faltando)."
            )

        return {
            "Content-Type": "application/json",
            "x-tts-access-token": self.config.access_token
        }

    def list_orders(self, limit=10, offset=0, filters=None):
        """
        Lista pedidos do Tiktok Shop.
        """
        logger.info(f"Listando pedidos Tiktok Shop para empresa {self.id_empresa} (limit={limit}, offset={offset})")
        
        # Simulação de chamada de API. 
        # Em uma integração real, isso faria um requests.post ou get para self.api_base + '/orders/search'
        # Passando app_key, app_secret, sign etc.
        
        url = f"{self.api_base}/orders/search"
        # Aqui deveria construir os parâmetros reais, mas vamos simular para não quebrar sem a doc exata.
        # params = { "app_key": self.config.app_key, "shop_id": self.config.shop_id }
        
        # Mocking data for the example, replace with actual requests
        # resp = requests.post(url, headers=self._get_headers(), json={"page_size": 200})
        # data = resp.json()
        orders = []

        # --- PRE-PROCESSAMENTO: Verificar status de importação ---
        for order in orders:
            order_id = order.get('order_id')
            search_str = f"ID Tiktok: {order_id}"
            exists = self.db.query(models.Pedido.id).filter(
                models.Pedido.observacao.contains(search_str),
                models.Pedido.id_empresa == self.id_empresa,
                models.Pedido.situacao != 'cancelado'
            ).first()
            order['ja_importado'] = True if exists else False

        # --- FILTRAGEM LOCAL (Semelhante ao Magento) ---
        active_filters = []
        if filters is not None:
            if isinstance(filters, str):
                try:
                    active_filters = json.loads(filters)
                except:
                    active_filters = []
            else:
                active_filters = filters
        elif self.config.filtros_padrao:
            active_filters = self.config.filtros_padrao

        if active_filters:
            filtered_orders = []
            for order in orders:
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
            orders = filtered_orders

        total_count = len(orders)
        orders = orders[offset : offset + limit]

        formatted_items = []
        for order in orders:
            item_data = order.copy()
            formatted_items.append(item_data)

        dynamic_filters = [
            {
                "label": "Status", 
                "value": "order_status", 
                "type": "multiselect", 
                "options": [{"label": "Unpaid", "value": "UNPAID"}, {"label": "Awaiting Shipment", "value": "AWAITING_SHIPMENT"}]
            },
            {
                "label": "Importado", 
                "value": "ja_importado", 
                "type": "multiselect", 
                "options": [{"label": "Importado", "value": "true"}, {"label": "Não Importado", "value": "false"}]
            }
        ]

        return {
            "items": formatted_items,
            "total_count": total_count,
            "extra": {"available_filters": dynamic_filters}
        }

    def import_order(self, order_id: str):
        """Importa um pedido específico pelo order_id do Tiktok"""
        logger.info(f"Iniciando importação do pedido Tiktok {order_id} para empresa {self.id_empresa}")
        
        # Verifica duplicidade
        search_str = f"ID Tiktok: {order_id}"
        exists = self.db.query(models.Pedido).filter(
            models.Pedido.observacao.contains(search_str),
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.situacao != 'cancelado'
        ).first()
        if exists:
            logger.info(f"Pedido Tiktok {order_id} já foi importado anteriormente")
            raise HTTPException(status_code=409, detail=f"Pedido {order_id} já importado.")

        # Buscar detalhes reais da API
        # url = f"{self.api_base}/orders/detail"
        # resp = requests.post(url, headers=self._get_headers(), json={"order_id_list": [order_id]})
        # order_data = resp.json().get('data', {}).get('order_list', [])[0]
        
        # Simulando order_data para não quebrar:
        order_data = {
            "order_id": order_id,
            "buyer_email": "buyer@example.com",
            "payment_method": "Credit Card",
            "item_list": [],
            "payment_info": { "total_amount": 0, "shipping_fee": 0 },
            "recipient_address": {
                "name": "Cliente Teste",
                "phone": "11999999999",
                "zipcode": "01000000",
                "state": "SP",
                "city": "São Paulo",
                "address_line1": "Rua Teste",
                "address_line2": "123"
            }
        }

        # 2. Busca ou Cria Cliente
        cliente_erp = self._find_or_create_customer(order_data)

        # 3. Processa Itens
        itens_erp = []
        produtos_criados = []
        total_calculado = 0
        
        for item in order_data.get('item_list', []):
            sku = item.get('sku_id', 'SKU-INDEFINIDO')
            
            produto = self.db.query(models.Produto).filter(
                models.Produto.sku == sku,
                models.Produto.id_empresa == self.id_empresa
            ).first()

            if not produto:
                produto = models.Produto(
                    id_empresa=self.id_empresa,
                    sku=sku,
                    descricao=item.get('product_name', 'Produto Importado Tiktok')[:255],
                    unidade=models.ProdutoUnidadeEnum.un,
                    tipo_produto=models.ProdutoTipoEnum.mercadoria_revenda,
                    origem=models.ProdutoOrigemEnum.nacional,
                    preco=float(item.get('sale_price', 0)),
                    custo=0,
                    situacao=True
                )
                self.db.add(produto)
                self.db.commit()
                self.db.refresh(produto)
                produtos_criados.append(sku)

            qtd = int(float(item.get('quantity', 0)))
            preco = float(item.get('sale_price', 0)) 
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

        shipping_amount = float(order_data.get('payment_info', {}).get('shipping_fee', 0))
        address = order_data.get('recipient_address', {})

        # 4. Cria Pedido
        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=cliente_erp.id_sequencial if cliente_erp else None,
            id_vendedor=self.config.vendedor_padrao_id,
            situacao=self.config.situacao_pedido_inicial,
            data_orcamento=datetime.now(),
            data_validade=datetime.now(),
            origem_venda="Tiktok Shop",
            total=order_data.get('payment_info', {}).get('total_amount', 0),
            valor_frete=shipping_amount,
            modalidade_frete=PedidoModalidadeFreteEnum.cif,
            
            endereco_cep=address.get('zipcode', '')[:9],
            endereco_logradouro=address.get('address_line1'),
            endereco_numero=address.get('address_line2') or 'S/N',
            endereco_cidade=address.get('city'),
            endereco_estado=address.get('state'),
            
            itens=itens_erp,
            observacao=f"Pedido importado do Tiktok Shop. ID Tiktok: {order_id}"
        )

        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)
        
        logger.info(f"Pedido Tiktok {order_id} importado com sucesso. ID ERP: {novo_pedido.id}")
            
        return novo_pedido, produtos_criados

    def _find_or_create_customer(self, order_data: dict) -> models.Cadastro:
        address = order_data.get('recipient_address', {})
        email = order_data.get('buyer_email')
        phone = address.get('phone')

        cliente = None
        if email:
            cliente = self.db.query(models.Cadastro).filter(
                models.Cadastro.email == email,
                models.Cadastro.id_empresa == self.id_empresa
            ).first()

        if cliente:
            return cliente

        novo_cliente = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj='00000000000',
            nome_razao=address.get('name', 'CLIENTE TIKTOK').upper(),
            tipo_cadastro=CadastroTipoCadastroEnum.cliente,
            tipo_pessoa=CadastroTipoPessoaEnum.fisica,
            email=email,
            telefone="".join(filter(str.isdigit, str(phone or '')))[:20],
            cep="".join(filter(str.isdigit, str(address.get('zipcode') or '')))[:9],
            estado=address.get('state'),
            cidade=address.get('city'),
            logradouro=address.get('address_line1'),
            numero=address.get('address_line2') or 'S/N',
            situacao=True
        )
        self.db.add(novo_cliente)
        self.db.commit()
        self.db.refresh(novo_cliente)
        return novo_cliente
