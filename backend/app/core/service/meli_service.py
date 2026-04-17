import httpx
import re
import json
import secrets
import hashlib
import base64
import logging
import io
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.core.db import models
from app.core.db.models import (
    CadastroTipoPessoaEnum, CadastroTipoCadastroEnum, CadastroIndicadorIEEnum,
    PedidoSituacaoEnum, PedidoModalidadeFreteEnum, FiscalPagamentoEnum
)
from app.core.config import settings

logger = logging.getLogger(__name__)

class MeliService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        self.base_url = "https://api.mercadolibre.com"
        logger.debug(f"Inicializando MeliService para empresa {id_empresa}")
        
        # Carrega configurações
        self.config = self.db.query(models.MeliConfiguracao).filter(
            models.MeliConfiguracao.id_empresa == self.id_empresa
        ).first()

        if not self.config:
            logger.error(f"Configuração ML não encontrada para empresa {self.id_empresa}. Verifique a tabela meli_configuracoes.")
            raise HTTPException(status_code=400, detail="Configuração do Mercado Livre não encontrada.")
            
        logger.debug(f"Configuração ML carregada com sucesso para empresa {self.id_empresa}")
        self.credentials = self.db.query(models.MeliCredentials).filter(
            models.MeliCredentials.id_empresa == self.id_empresa
        ).first()

        if not self.credentials:
            logger.info(f"Empresa {self.id_empresa} possui configuração, mas ainda não está autenticada (tabela meli_credentials vazia).")

    async def get_auth_url(self):
        """Gera URL para iniciar OAuth com PKCE"""
        logger.info(f"Gerando URL de autorização ML para empresa {self.id_empresa}")
        if not self.config.app_id or not self.config.redirect_uri:
            logger.error(f"App ID ou Redirect URI ausentes na configuração da empresa {self.id_empresa}")
            raise HTTPException(status_code=400, detail="App ID e Redirect URI são obrigatórios.")

        # PKCE Generation
        code_verifier = secrets.token_urlsafe(64)
        hashed = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(hashed).decode('utf-8').replace('=', '')
        logger.debug(f"PKCE gerado. Challenge: {code_challenge}")
        
        # Na prática real, você deve salvar o code_verifier temporariamente (ex: Redis ou Cache)
        # associado a um 'state' para validar no callback. 
        # Para simplificar aqui, retornamos o verifier para o front mandar de volta ou usamos cookie.
        
        auth_url = (
            f"https://auth.mercadolivre.com.br/authorization?"
            f"response_type=code&client_id={self.config.app_id}&redirect_uri={self.config.redirect_uri}"
            f"&code_challenge={code_challenge}&code_challenge_method=S256"
        )
        logger.debug(f"URL de autenticação construída: {auth_url}")
        return {"url": auth_url, "verifier": code_verifier}

    async def _refresh_token(self):
        """Renova o token se expirado"""
        logger.info(f"Iniciando renovação de token ML para empresa {self.id_empresa}")
        url = f"{self.base_url}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.config.app_id,
            "client_secret": self.config.client_secret,
            "refresh_token": self.credentials.refresh_token,
        }
        async with httpx.AsyncClient() as client:
            logger.debug(f"Enviando requisição de refresh para {url}")
            resp = await client.post(url, data=payload)
            if resp.status_code != 200:
                error_resp = resp.text
                
                # Se o erro indicar incompatibilidade de Client ID (troca de conta/app), limpamos as credenciais antigas
                if "client_id does not match" in error_resp or "invalid_grant" in error_resp:
                    logger.warning(f"Erro de renovação esperado (troca de credenciais): {resp.status_code} - {error_resp}")
                    logger.warning("Token incompatível com o App ID atual. Removendo credenciais antigas.")
                    self.db.delete(self.credentials)
                    self.db.commit()
                    raise HTTPException(
                        status_code=403, 
                        detail="As credenciais salvas não correspondem ao novo App ID. Por favor, realize a conexão (Login) novamente."
                    )

                logger.error(f"Erro ao renovar token ML para empresa {self.id_empresa}: {resp.status_code} - {error_resp}")
                raise HTTPException(status_code=403, detail=f"Falha ao renovar token ML: {error_resp}")
            
            data = resp.json()
            self.credentials.access_token = data['access_token']
            self.credentials.refresh_token = data['refresh_token']
            self.credentials.expires_in = data['expires_in']
            self.credentials.last_updated = datetime.now(timezone.utc)
            logger.info(f"Token renovado com sucesso para empresa {self.id_empresa}. Expira em {data['expires_in']}s")
            self.db.commit()

    def disconnect(self):
        """Remove as credenciais do banco de dados para forçar re-autenticação"""
        if self.credentials:
            logger.info(f"Removendo credenciais ML para empresa {self.id_empresa} a pedido do usuário.")
            self.db.delete(self.credentials)
            self.db.commit()
            self.credentials = None
        else:
            logger.info(f"Solicitação de desconexão para empresa {self.id_empresa}, mas não havia credenciais.")

    async def force_refresh_token(self):
        """Força a renovação do token (Sincronização de Conexão)"""
        if not self.credentials:
            raise HTTPException(status_code=403, detail="Não há credenciais para sincronizar. Por favor, realize a conexão (Login) novamente.")
        await self._refresh_token()

    async def get_client(self):
        """Retorna um cliente HTTP autenticado"""
        logger.debug(f"Solicitando cliente HTTP autenticado para empresa {self.id_empresa}")
        if not self.credentials:
             logger.warning(f"Tentativa de usar API do Mercado Livre sem tokens para empresa {self.id_empresa}. O usuário precisa realizar o login via OAuth.")
             raise HTTPException(status_code=403, detail="Não conectado ao Mercado Livre. Realize o login novamente.")

        # Verifica expiração (margem de 2 min)
        expiration = self.credentials.last_updated + timedelta(seconds=self.credentials.expires_in - 120)
        now = datetime.now(timezone.utc)
        if now > expiration:
            logger.info(f"Token da empresa {self.id_empresa} expirado ou prestes a expirar (Expiração: {expiration}, Agora: {now}). Renovando...")
            await self._refresh_token()
            
        logger.debug(f"Cliente HTTP pronto para uso (Empresa {self.id_empresa})")
        return httpx.AsyncClient(headers={"Authorization": f"Bearer {self.credentials.access_token}"})

    async def list_orders(self, limit=10, offset=0):
        """Lista todos os pedidos (qualquer status e qualquer data) da API do ML"""
        logger.info(f"Listando pedidos ML para empresa {self.id_empresa} (limit={limit}, offset={offset})")
        client = await self.get_client()
        
        logger.debug("Buscando dados do usuário autenticado (/users/me)...")
        me_resp = await client.get(f"{self.base_url}/users/me")
        if me_resp.status_code != 200:
            logger.error(f"Erro ao buscar dados do usuário (me) no ML: {me_resp.status_code} - {me_resp.text}")
            raise HTTPException(status_code=me_resp.status_code, detail=f"Erro ao buscar dados do usuário no ML: {me_resp.text}")
            
        user_id = me_resp.json().get('id')
        logger.debug(f"User ID ML identificado: {user_id}. Iniciando busca total de pedidos...")

        # Define o intervalo de tempo para ignorar o limite padrão de 15 dias do ML
        # Buscando desde 2015 até agora para pegar todo o histórico disponível na busca comum
        agora = datetime.now().isoformat()
        
        # Busca Pedidos
        url = f"{self.base_url}/orders/search"
        params = {
            "seller": user_id,
            "sort": "date_desc",
            "limit": limit,
            "offset": offset,
            # Filtros de data para trazer tudo:
            "order.date_created.from": "2015-01-01T00:00:00.000-00:00",
            "order.date_created.to": f"{agora}-03:00", # Ajustado para timezone Brasil se necessário
        }
        
        # Ao NÃO enviar o parâmetro "status", o Mercado Livre traz todos (paid, cancelled, etc.)
        
        logger.debug(f"Enviando GET para {url} com params: {params}")
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.error(f"Erro ao buscar pedidos ML para empresa {self.id_empresa}: {resp.status_code} - {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=f"Erro ao buscar pedidos ML: {resp.text}")
            
        data = resp.json()
        results = data.get("results", [])
        total = data.get("paging", {}).get("total", 0)
        
        logger.info(f"API do ML retornou {len(results)} resultados (Total disponível no filtro: {total})")

        formatted_items = []
        for order in results:
            order_id = order.get('id')
            
            # Verifica se já importamos este pedido
            search_str = f"{order_id}"
            exists = self.db.query(models.Pedido).filter(
                models.Pedido.observacao.contains(search_str),
                models.Pedido.id_empresa == self.id_empresa,
                models.Pedido.situacao != 'cancelado'
            ).first()
            
            item_title = "Vários itens"
            if order.get('order_items') and len(order['order_items']) > 0:
                item_title = order['order_items'][0]['item']['title']

            # Copia todos os dados originais do pedido para incluir todas as colunas da API
            item_data = order.copy()

            # Adiciona campos calculados
            item_data.update({
                "id": str(order_id),
                "buyer_nickname": order['buyer']['nickname'],
                "item_title": item_title,
                "ja_importado": bool(exists)
            })

            formatted_items.append(item_data)
            
        return {
            "items": formatted_items,
            "total_count": total
        }

    async def authenticate(self, code: str, code_verifier: str = None):
        """Troca o Code pelo Token e salva/atualiza no banco"""
        logger.info(f"Iniciando processo de troca de code por token para empresa {self.id_empresa}")
        url = "https://api.mercadolibre.com/oauth/token"
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.config.app_id,
            "code": code,
            "redirect_uri": self.config.redirect_uri,
        }

        if self.config.client_secret:
            payload["client_secret"] = self.config.client_secret

        if code_verifier:
            payload["code_verifier"] = code_verifier
        
        async with httpx.AsyncClient() as client:
            logger.debug(f"Enviando requisição de autenticação para {url}")
            resp = await client.post(url, data=payload)
            if resp.status_code != 200:
                logger.error(f"Erro ao obter token ML para empresa {self.id_empresa}: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=400, detail=f"Erro ao obter token: {resp.text}")
            
            data = resp.json()
            
            # Validação defensiva para evitar KeyError
            access_token = data.get('access_token')
            refresh_token = data.get('refresh_token')
            user_id = data.get('user_id')
            expires_in = data.get('expires_in', 21600) # Default 6h se não vier

            if not access_token or not user_id:
                logger.error(f"Resposta do ML incompleta para empresa {self.id_empresa}. Chaves recebidas: {list(data.keys())}")
                raise HTTPException(status_code=400, detail="O Mercado Livre não retornou os tokens de acesso necessários.")

            # Atualiza ou cria credenciais
            if not self.credentials:
                logger.info(f"Criando novas credenciais para empresa {self.id_empresa} (User ML: {user_id})")
                self.credentials = models.MeliCredentials(
                    user_id_ml=user_id,
                    id_empresa=self.id_empresa,
                    access_token=access_token,
                    refresh_token=refresh_token or "", # Evita KeyError se o ML não retornar
                    expires_in=expires_in
                )
                self.db.add(self.credentials)
            else:
                logger.info(f"Atualizando credenciais existentes para empresa {self.id_empresa}")
                self.credentials.access_token = access_token
                if refresh_token:
                    self.credentials.refresh_token = refresh_token
                self.credentials.expires_in = expires_in
                self.credentials.last_updated = datetime.now(timezone.utc)
            
            self.db.commit()
            logger.info(f"Autenticação finalizada com sucesso para empresa {self.id_empresa}")
            return {"message": "Autenticado com sucesso!", "user_id": data['user_id']}

    def _find_or_create_customer(self, ml_order: dict, shipment_details: dict, billing_info: dict = None) -> models.Cadastro:
        """Lógica portada do sistema antigo para SQLAlchemy"""
        logger.info(f"Buscando ou criando cliente para o pedido ML {ml_order['id']}")
        
        # 1. Prioridade: Billing Info (Endpoint específico)
        doc_number = billing_info.get('doc_number') if billing_info else None
        doc_type = billing_info.get('doc_type') if billing_info else None
        
        if not doc_number:
            # 2. Fallback: Shipment (Receiver ID)
            receiver_id = shipment_details.get('receiver_identification', {})
            doc_number = receiver_id.get('number')
            if not doc_type:
                doc_type = receiver_id.get('type')

        if not doc_number:
            # 3. Fallback Final: ID do Comprador
            doc_number = f"ML{ml_order['buyer']['id']}" # Fallback
            logger.debug(f"Documento não encontrado no envio. Usando fallback: {doc_number}")
        
        # 2. Verifica se cliente existe
        cliente = self.db.query(models.Cadastro).filter(
            models.Cadastro.cpf_cnpj == str(doc_number),
            models.Cadastro.id_empresa == self.id_empresa
        ).first()

        if cliente:
            logger.info(f"Cliente {doc_number} já existe no ERP para empresa {self.id_empresa}")
            return cliente

        # 3. Se não existe, cria novo
        shipping_addr = shipment_details.get('receiver_address', {})
        
        # --- NOVA LÓGICA: PRIORIZA NOME DO RECEBEDOR (ENTREGA) ---
        nome_completo = shipping_addr.get('receiver_name')
        
        if not nome_completo:
            # Fallback para dados do comprador caso o nome do recebedor não esteja disponível
            nome = ml_order['buyer'].get('first_name')
            sobrenome = ml_order['buyer'].get('last_name')
            nome_completo = f"{nome or ''} {sobrenome or ''}".strip()
            if not nome_completo:
                nome_completo = ml_order['buyer']['nickname']

        # Determina tipo de pessoa
        tipo_pessoa = CadastroTipoPessoaEnum.fisica
        if doc_type == 'CNPJ':
            tipo_pessoa = CadastroTipoPessoaEnum.juridica
        elif len(str(doc_number)) > 11 and str(doc_number).isdigit():
             tipo_pessoa = CadastroTipoPessoaEnum.juridica

        logger.info(f"Criando novo cliente {doc_number} ({nome_completo}) para empresa {self.id_empresa}")
        novo_cliente = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj=str(doc_number),
            nome_razao=nome_completo[:255].upper(), # Limita tamanho e converte para caixa alta
            fantasia="CLIENTE MERCADO LIVRE",
            tipo_pessoa=tipo_pessoa,
            tipo_cadastro=CadastroTipoCadastroEnum.cliente,
            email=f"ml_{ml_order['buyer']['id']}@not-real.com", # ML esconde emails hoje em dia
            telefone="".join(filter(str.isdigit, str(shipping_addr.get('receiver_phone') or '')))[:20],
            
            # Endereço
            cep="".join(filter(str.isdigit, str(shipping_addr.get('zip_code') or '')))[:9],
            logradouro=(shipping_addr.get('street_name') or '')[:255],
            numero=str(shipping_addr.get('street_number') or 'S/N')[:20],
            complemento=(shipping_addr.get('comment') or '')[:255],
            cidade=(shipping_addr.get('city', {}).get('name') or '')[:255],
            estado=(shipping_addr.get('state', {}).get('id') or '')[-2:], # Ex: BR-SP -> SP
            bairro=(shipping_addr.get('neighborhood', {}).get('name') or '')[:255],
            
            indicador_ie=CadastroIndicadorIEEnum.nao_contribuinte,
            situacao=True
        )
        
        self.db.add(novo_cliente)
        self.db.commit()
        self.db.refresh(novo_cliente)
        logger.info(f"Novo cliente criado com ID ERP: {novo_cliente.id}")
        return novo_cliente

    def _create_product_from_ml_item(self, item_data: dict, sku: str) -> models.Produto:
        """Cria um produto novo baseado nos dados do item do ML"""
        logger.info(f"Criando produto automático para SKU: {sku}")
        
        title = item_data['item'].get('title', 'Produto Importado ML')
        price = float(item_data.get('unit_price', 0))
        
        novo_produto = models.Produto(
            id_empresa=self.id_empresa,
            sku=sku,
            descricao=title[:255],
            unidade=models.ProdutoUnidadeEnum.un,
            tipo_produto=models.ProdutoTipoEnum.mercadoria_revenda,
            preco=price,
            custo=0,
            situacao=True,
            origem=models.ProdutoOrigemEnum.nacional
        )
        
        self.db.add(novo_produto)
        self.db.commit()
        self.db.refresh(novo_produto)
        return novo_produto

    def _find_or_create_carrier(self, shipment_details: dict) -> models.Cadastro:
        """Busca ou cria transportadora com lógica avançada para ME1 (Rodonaves, etc)"""
        
        # 1. LOG RADICAL: Vamos ver tudo o que tem dentro do envio para não perder nada
        try:
            logger.info(f"DEBUG FULL SHIPMENT: {json.dumps(shipment_details, default=str)}")
        except:
            pass

        # Extração de campos
        logistic_type = shipment_details.get('logistic_type')
        tracking_method = shipment_details.get('tracking_method')
        mode = shipment_details.get('mode')
        carrier_info = shipment_details.get('carrier_info')
        shipping_option = shipment_details.get('shipping_option') or {}
        service_id = shipment_details.get('service_id')

        carrier_name = None

        # --- ESTRATÉGIA DE DESCOBERTA DE NOME ---

        # 1. Prioridade Absoluta: carrier_info preenchido
        if carrier_info:
            if isinstance(carrier_info, str):
                carrier_name = carrier_info
            elif isinstance(carrier_info, dict):
                carrier_name = carrier_info.get('description') or carrier_info.get('new_description')

        # 2. Se for ME1 (Logística do Vendedor), o nome costuma estar no tracking_method
        # Ex: tracking_method: "Rodonaves", "Jadlog", "Azul Cargo"
        if not carrier_name and mode == 'me1':
            if tracking_method and tracking_method not in ['common_carrier', 'custom']:
                # O ML às vezes manda "rodonaves" minúsculo, vamos formatar
                carrier_name = tracking_method.title() 

        # 3. Tenta pelo nome do Serviço (shipping_option -> name)
        # Vendedores configuram tabelas de frete com nomes tipo "Rodonaves - SP"
        if not carrier_name and shipping_option:
            opt_name = shipping_option.get('name', '')
            # Ignora nomes genéricos do ML
            termos_genericos = ['normal', 'expresso', 'express', 'standard', 'grátis', 'super expresso']
            if opt_name and opt_name.lower() not in termos_genericos:
                carrier_name = opt_name

        # 4. Fallback para nomes conhecidos baseados no service_id (Casos raros)
        if not carrier_name and service_id:
            # Aqui você pode mapear IDs específicos se descobrir padrões
            pass

        # 5. Definições Padrão ML (Se nada acima funcionou)
        if not carrier_name:
            if logistic_type == 'fulfillment':
                carrier_name = "Mercado Livre Full"
            elif logistic_type == 'cross_docking':
                carrier_name = "Mercado Envíos (Coleta)"
            elif logistic_type == 'drop_off':
                carrier_name = "Mercado Envíos (Agência)"
            elif mode == 'me2':
                carrier_name = "Mercado Envíos"
            else:
                # Se não achou nada, coloca "A Definir" ou o método genérico para não quebrar
                carrier_name = "Transportadora Padrão"

        logger.info(f"Transportadora Identificada: '{carrier_name}' (Mode: {mode} | Method: {tracking_method})")

        if not carrier_name:
            return None

        carrier_name = str(carrier_name).strip()

        # --- BUSCA NO BANCO DE DADOS (CASE INSENSITIVE) ---
        carrier = self.db.query(models.Cadastro).filter(
            models.Cadastro.nome_razao.ilike(carrier_name),
            models.Cadastro.tipo_cadastro == CadastroTipoCadastroEnum.transportadora,
            models.Cadastro.id_empresa == self.id_empresa
        ).first()

        if carrier:
            return carrier

        # --- CRIAÇÃO AUTOMÁTICA ---
        logger.info(f"Criando transportadora '{carrier_name}' para empresa {self.id_empresa}")
        new_carrier = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj='00000000000000', # Dummy
            nome_razao=carrier_name,
            fantasia=carrier_name,
            tipo_cadastro=CadastroTipoCadastroEnum.transportadora,
            tipo_pessoa=CadastroTipoPessoaEnum.juridica,
            situacao=True,
            cep="00000-000",
            logradouro="Endereço Virtual ML",
            numero="S/N",
            cidade="Indefinida",
            estado="SP"
        )
        self.db.add(new_carrier)
        self.db.commit()
        self.db.refresh(new_carrier)
        return new_carrier

    def _extract_weight_from_item(self, item_ml: dict) -> float:
        """
        Tenta extrair o peso (em KG) dos atributos do item do ML.
        Procura por IDs comuns de atributos de peso (ex: 'WEIGHT', 'PACKAGE_WEIGHT').
        """
        weight_kg = 0.0
        attributes = item_ml.get('item', {}).get('attributes', []) or []
        
        for attr in attributes:
            # IDs comuns para peso no ML
            if attr.get('id') in ['WEIGHT', 'PACKAGE_WEIGHT', 'NET_WEIGHT']:
                val = attr.get('value_name')
                if val:
                    try:
                        # Ex: "200 g" ou "1 kg"
                        parts = val.split()
                        if len(parts) == 2:
                            numero = float(parts[0].replace(',', '.'))
                            unidade = parts[1].lower()
                            if 'kg' in unidade:
                                weight_kg = numero
                            elif 'g' in unidade:
                                weight_kg = numero / 1000
                            elif 'lb' in unidade:
                                weight_kg = numero * 0.453592
                        # Se achou, para o loop (prioriza peso da embalagem se houver)
                        if attr.get('id') == 'PACKAGE_WEIGHT': 
                            break
                    except:
                        pass
        return weight_kg

    def _map_payment_method(self, payments_data: list) -> FiscalPagamentoEnum:
        """
        Mapeia os tipos de pagamento do ML para os da NFe (Sefaz).
        """
        if not payments_data:
            return FiscalPagamentoEnum.sem_pagamento

        # 1. Prioriza pagamentos aprovados e pega o de maior valor
        approved = [p for p in payments_data if p.get('status') == 'approved']
        if approved:
            target = max(approved, key=lambda x: float(x.get('transaction_amount', 0)))
        else:
            target = payments_data[0] # Fallback

        # Normaliza para string e lower case para evitar erro
        pay_type = str(target.get('payment_type_id') or target.get('payment_type') or '').lower()
        pay_method = str(target.get('payment_method_id') or '').lower()

        # LOG DEBUG ESSENCIAL PARA DESCOBRIR O QUE O ML MANDOU
        logger.info(f"DEBUG PAGAMENTO ML - Type: {pay_type} | Method: {pay_method}")

        # --- Lógica de Mapeamento ---

        # PIX (O ML pode retornar como 'bank_transfer' com method 'pix' ou 'pec')
        if 'bank_transfer' in pay_type or 'pix' in pay_method:
            return FiscalPagamentoEnum.pix  # 17

        # Cartão de Crédito
        if 'credit_card' in pay_type:
            return FiscalPagamentoEnum.cartao_credito # 03

        # Cartão de Débito
        if 'debit_card' in pay_type or 'prepaid_card' in pay_type:
            return FiscalPagamentoEnum.cartao_debito # 04

        # Boleto
        if 'ticket' in pay_type or 'bolbradesco' in pay_method:
            return FiscalPagamentoEnum.boleto_bancario # 15

        # Saldo em Conta (Account Money)
        # Contadores geralmente pedem para usar 99 (Outros) ou 05 (Crédito Loja).
        # Vamos manter 99 (Outros) pois é o mais seguro fiscalmente para "Saldo Virtual".
        if 'account_money' in pay_type:
            return FiscalPagamentoEnum.outros # 99

        # Fallback
        return FiscalPagamentoEnum.outros # 99

    async def import_order(self, order_id_ml: str):
        """Lógica principal de importação com dados completos de frete"""
        logger.info(f"Iniciando importação detalhada do pedido ML {order_id_ml}")

        # 1. Verifica duplicidade
        search_str = f"ID ML: {order_id_ml}"
        exists = self.db.query(models.Pedido).filter(
            models.Pedido.observacao.contains(search_str),
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.situacao != 'cancelado'
        ).first()
        if exists:
            logger.info(f"Pedido {order_id_ml} já importado.")
            raise HTTPException(status_code=409, detail=f"Pedido {order_id_ml} já importado.")

        client_http = await self.get_client()
        
        # 2. Busca dados do Pedido e Envio
        try:
            order_resp = await client_http.get(f"{self.base_url}/orders/{order_id_ml}")
            order_resp.raise_for_status()
            ml_order = order_resp.json()
            
            shipping_data = ml_order.get('shipping') or {}
            ship_id = shipping_data.get('id')
            shipment_details = {}
            billing_info = {}

            # Busca Shipment (Detalhes do Frete)
            if ship_id:
                try:
                    ship_resp = await client_http.get(f"{self.base_url}/shipments/{ship_id}")
                    if ship_resp.status_code == 200:
                        shipment_details = ship_resp.json()
                    else:
                        logger.warning(f"Erro ao buscar shipment {ship_id}: {ship_resp.status_code}")
                except Exception as e:
                    logger.warning(f"Falha na requisição de shipment: {e}")

            # Busca Billing Info (Dados Fiscais/CPF)
            try:
                billing_resp = await client_http.get(f"{self.base_url}/orders/{order_id_ml}/billing_info")
                if billing_resp.status_code == 200:
                    billing_info = billing_resp.json().get('billing_info', {})
            except:
                pass

        except Exception as e:
            logger.exception(f"Erro fatal ao buscar dados ML: {e}")
            raise HTTPException(status_code=400, detail="Erro de comunicação com Mercado Livre")

        # 3. Busca ou Cria Cliente
        cliente_erp = self._find_or_create_customer(ml_order, shipment_details, billing_info)

        # 4. Processa Itens e Calcula Peso Total
        itens_erp = []
        total_produtos = 0.0
        total_ipi_global = 0.0
        peso_bruto_total = 0.0
        
        for item in ml_order.get('order_items', []):
            sku = item['item'].get('seller_sku')
            
            # Validação básica de SKU
            if not sku:
                 # Fallback: Tenta criar um SKU baseado no ID do item se não tiver
                 sku = f"ML-{item['item']['id']}"
            
            produto = self.db.query(models.Produto).filter(
                models.Produto.sku == sku,
                models.Produto.id_empresa == self.id_empresa
            ).first()

            if not produto:
                produto = self._create_product_from_ml_item(item, sku)

            # --- Lógica de Peso ---
            # 1. Tenta pegar peso do cadastro do produto no ERP
            peso_unitario = float(produto.peso) if produto.peso else 0.0
            
            # 2. Se for zero, tenta extrair dos atributos do JSON do ML (agora em tempo real)
            if peso_unitario == 0:
                peso_unitario = self._extract_weight_from_item(item)

            qtd = int(float(item['quantity']))
            preco_unit = float(item['unit_price'])
            subtotal = preco_unit * qtd
            
            peso_bruto_total += (peso_unitario * qtd)
            total_produtos += subtotal

            # --- Lógica de IPI e Totais Detalhados ---
            ipi_aliquota = float(produto.ipi_aliquota or 0)
            valor_ipi = round(subtotal * (ipi_aliquota / 100), 2)
            total_com_ipi = round(subtotal + valor_ipi, 2)
            total_ipi_global += valor_ipi

            itens_erp.append({
                "id_produto": produto.id,
                "sku": produto.sku,
                "descricao": produto.descricao,
                "gtin": produto.gtin or "SEM GTIN",
                "ncm": produto.ncm,
                "unidade": produto.unidade.value if hasattr(produto.unidade, 'value') else str(produto.unidade),
                "quantidade": qtd,
                "valor_unitario": preco_unit,
                "subtotal": subtotal,
                "peso_unitario": peso_unitario,
                "ipi_aliquota": ipi_aliquota,
                "valor_ipi": valor_ipi,
                "total_com_ipi": total_com_ipi
            })

        # 5. Processamento Detalhado do Frete (O PULO DO GATO)
        valor_frete = 0.0
        modalidade_frete = PedidoModalidadeFreteEnum.sem_frete
        data_entrega = None
        transportadora_id = None
        
        # Dados de Volumes
        volumes_qtd = 0
        volumes_especie = None
        volumes_marca = None
        
        # Extração de Custos
        shipping_option = shipment_details.get('shipping_option') or {}
        
        # Tenta pegar o custo do objeto detalhado de envio (shipment_details) - ONDE ESTÁ O 112.46
        cost_shipment = shipping_option.get('cost')
        
        # Tenta pegar do objeto do pedido (fallback)
        cost_order = ml_order.get('shipping', {}).get('cost')

        # Lógica de Prioridade
        if cost_shipment is not None:
            valor_frete = float(cost_shipment)
        elif cost_order is not None:
            valor_frete = float(cost_order)

        # Definição da Modalidade (FOB vs CIF)
        # Forçado para CIF (0) conforme regra de negócio (99.99% dos casos)
        modalidade_frete = PedidoModalidadeFreteEnum.cif

        logger.info(f"Frete Calculado: R$ {valor_frete} (Modalidade: {modalidade_frete.value})")

        # Data de Entrega
        est_time = shipping_option.get('estimated_delivery_time') or {}
        est_date_str = est_time.get('date')
        if est_date_str:
            try:
                data_entrega = datetime.fromisoformat(est_date_str.replace('Z', '+00:00')).date()
            except ValueError:
                pass

        # Transportadora
        # Alterado: Não buscar/criar transportadora para deixar campos vazios
        transportadora_id = None
            
        # --- Preenchimento de Campos de Volumes (Logística) ---
        tracking_number = shipment_details.get('tracking_number')
        
        if tracking_number or shipment_details.get('status'):
            # Se tem rastreio ou status de envio, assumimos ao menos 1 volume
            volumes_qtd = 1 
            volumes_especie = "VOLUME"
            
            # Marca vazia na importação
            volumes_marca = None
        else:
            # Produto digital ou a combinar
            volumes_qtd = 0
            volumes_especie = None

        # Total do Pedido
        # Se for FOB, o valor do frete soma ao total da nota. Se for CIF, já está embutido ou é por conta da casa.
        total_pedido = total_produtos + total_ipi_global
        if modalidade_frete == PedidoModalidadeFreteEnum.fob:
            total_pedido += valor_frete

        # Observações ricas
        obs_text = f"Pedido ML: {ml_order['id']} | Comprador: {ml_order['buyer']['nickname']}"
        if tracking_number:
            obs_text += f" | Rastreio: {tracking_number}"
        if shipping_option.get('name'):
            obs_text += f" | Serviço: {shipping_option.get('name')}"
        if shipment_details.get('logistic_type'):
            obs_text += f" | Logística: {shipment_details.get('logistic_type')}"

        # --- DETERMINAÇÃO DO PAGAMENTO ---
        payments_list = ml_order.get('payments', [])
        
        # LOG BRUTO PARA DEBUG (Se der erro de novo, me mande esse log)
        logger.info(f"DEBUG PAYMENTS JSON: {json.dumps(payments_list, default=str)}")
        
        forma_pagamento = self._map_payment_method(payments_list)
        logger.info(f"Pagamento detectado no ERP: {forma_pagamento.description if forma_pagamento else 'N/A'}")

        # --- MELHORIA NA OBSERVAÇÃO E PAGAMENTO ---
        # Adiciona detalhe do pagamento na obs se for algo específico
        pagamento_descricao_erp = None
        if payments_list:
            # Pega o primeiro pagamento relevante
            p_resumo = payments_list[0]
            metodo_real = p_resumo.get('payment_method_id', '').upper()
            tipo_real = p_resumo.get('payment_type_id', '')
            
            # Se a forma mapeada for "Outros", preenchemos o campo específico para a NFe
            if forma_pagamento == FiscalPagamentoEnum.outros:
                pagamento_descricao_erp = f"{metodo_real} ({tipo_real})"
                obs_text += f" | Pagamento: {pagamento_descricao_erp}"
            elif forma_pagamento == FiscalPagamentoEnum.cartao_credito:
                # Ex: Cartão: VISA
                obs_text += f" | Cartão: {metodo_real}"

        # 6. Criação do Pedido
        data_ml = datetime.fromisoformat(ml_order['date_created'].replace('Z', '+00:00'))
        
        # Pega os dados do envio que já foram buscados
        shipping_addr = shipment_details.get('receiver_address', {})
        
        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=cliente_erp.id,
            id_vendedor=self.config.vendedor_padrao_id,
            situacao=self.config.situacao_pedido_inicial or PedidoSituacaoEnum.orcamento,
            data_orcamento=data_ml.date(),
            data_validade=data_ml.date(),
            data_entrega=data_entrega,
            origem_venda="Mercado Livre",
            
            # --- DADOS FINANCEIROS E TOTAIS ---
            total=total_pedido,
            pagamento=forma_pagamento,
            pagamento_descricao=pagamento_descricao_erp,
            caixa_destino_origem=self.config.caixa_padrao,
            
            # --- DADOS DE FRETE COMPLETOS ---
            valor_frete=valor_frete,
            modalidade_frete=modalidade_frete,
            id_transportadora=transportadora_id,
            
            # --- ENDEREÇO DE ENTREGA IMPORTADO DO ML ---
            endereco_cep="".join(filter(str.isdigit, str(shipping_addr.get('zip_code') or '')))[:9],
            endereco_logradouro=(shipping_addr.get('street_name') or '')[:255],
            endereco_numero=str(shipping_addr.get('street_number') or 'S/N')[:20],
            endereco_complemento=(shipping_addr.get('comment') or '')[:255],
            endereco_cidade=(shipping_addr.get('city', {}).get('name') or '')[:255],
            endereco_estado=(shipping_addr.get('state', {}).get('id') or '')[-2:],
            endereco_bairro=(shipping_addr.get('neighborhood', {}).get('name') or '')[:255],
            
            # Veículo (ML não fornece placa, deixamos NULL)
            veiculo_placa=None, 
            veiculo_uf=None,
            
            # Volumes e Pesos
            volumes_quantidade=volumes_qtd,
            volumes_especie=volumes_especie,
            volumes_marca=volumes_marca,
            volumes_numeracao=None, # ML não manda numeração sequencial de volume
            volumes_peso_bruto=peso_bruto_total if peso_bruto_total > 0 else None,
            volumes_peso_liquido=peso_bruto_total if peso_bruto_total > 0 else None, # Assumindo liq = bruto se não tiver info

            itens=itens_erp,
            observacao=obs_text
        )

        logger.info(f"Salvando pedido {order_id_ml} no ERP para empresa {self.id_empresa}")
        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)
        
        logger.info(f"Pedido {order_id_ml} importado com frete completo. ID ERP: {novo_pedido.id}")
        return novo_pedido

    async def upload_xml(self, order_id_ml: str, xml_content: str):
        """
        Envia o XML da NFe para o Mercado Livre.
        CORREÇÃO DEFINITIVA: Força MIME application/xml e adiciona cabeçalho XML.
        """
        if settings.ENVIRONMENT != "production":
            logger.info(f"Simulando upload de XML para pedido ML {order_id_ml} (Ambiente: {settings.ENVIRONMENT})")
            return {"status": "success", "message": "Simulado: XML enviado (Ambient de Testes)"}

        logger.info(f"Iniciando upload de XML para pedido ML {order_id_ml}")
        client = await self.get_client()

        try:
            # 1. Busca Pack ID (Obrigatório para Mercado Envios)
            order_resp = await client.get(f"{self.base_url}/orders/{order_id_ml}")
            
            if order_resp.status_code != 200:
                logger.error(f"Erro ao buscar pack_id: {order_resp.text}")
                return None
            
            order_data = order_resp.json()
            pack_id = order_data.get('pack_id')
            target_id = pack_id if pack_id else order_id_ml

            if pack_id:
                url = f"{self.base_url}/packs/{pack_id}/fiscal_documents"
            else:
                url = f"{self.base_url}/orders/{order_id_ml}/fiscal_documents"

            # 2. Tratamento do conteúdo do XML
            if isinstance(xml_content, str):
                xml_str = xml_content.strip()
            else:
                # Se vier bytes, decodifica para string para limpar e adicionar header
                xml_str = xml_content.decode('utf-8').strip()

            # Garante que o XML tenha a declaração padrão (boa prática para APIs java/legacy)
            if not xml_str.startswith('<?xml'):
                xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + xml_str

            # Converte de volta para bytes finais
            xml_bytes = xml_str.encode('utf-8')

            # 3. Montagem do Multipart (A Chave da Solução)
            # O 3º elemento da tupla DEVE ser 'application/xml'
            files = {
                'fiscal_document': (
                    'nfe.xml',       
                    xml_bytes,       
                    'application/xml' # <--- O ML SÓ ACEITA ISSO. NÃO USE text/xml.
                )
            }
            
            logger.debug(f"Enviando POST Multipart para {url} | Content-Type: application/xml | Tamanho: {len(xml_bytes)} bytes")
            
            resp = await client.post(url, files=files)

            if resp.status_code in [200, 201]:
                logger.info(f"✅ XML anexado com sucesso no ML para {target_id}!")
                return resp.json()
            elif resp.status_code == 400 and "nfe_already_generated" in resp.text:
                logger.warning(f"XML já consta no ML para {target_id}.")
                return {"status": "already_sent"}
            elif resp.status_code == 409:
                # Erro 409 Conflict: Geralmente indica que o limite de arquivos foi atingido (XML já enviado)
                logger.warning(f"Conflito no ML (XML já existente ou limite atingido): {resp.text}")
                return {"status": "already_sent"}
            elif resp.status_code == 403:
                # Tratamento específico para erro de Faturador do ML
                try:
                    err_data = resp.json()
                    msg = err_data.get('message', '') or err_data.get('error', '')
                    if "biller" in str(msg).lower():
                        logger.warning(f"Upload bloqueado pelo ML (Faturador Ativo): {msg}")
                        return {"status": "error", "message": "Upload bloqueado: Sua conta está configurada para usar o Faturador do Mercado Livre. Desative-o no painel do ML para emitir pelo ERP."}
                except:
                    pass
                logger.error(f"❌ Erro ML 403: {resp.text}")
                return {"status": "error", "message": f"Acesso negado pelo Mercado Livre (403). Verifique permissões ou configurações de faturamento."}
            else:
                logger.error(f"❌ Erro ML {resp.status_code}: {resp.text}")
                return {"status": "error", "message": f"Erro na API do Mercado Livre ({resp.status_code}): {resp.text}"}

        except httpx.TimeoutException:
            logger.error(f"Timeout ao comunicar com Mercado Livre para o pedido {order_id_ml}")
            return {"status": "error", "message": "Tempo de resposta esgotado ao comunicar com o Mercado Livre. Tente novamente."}
        except httpx.ConnectError:
            logger.error(f"Erro de conexão com Mercado Livre para o pedido {order_id_ml}")
            return {"status": "error", "message": "Falha de conexão com o servidor do Mercado Livre. Verifique sua internet."}
        except json.JSONDecodeError:
            logger.error(f"Erro ao processar resposta JSON do Mercado Livre para o pedido {order_id_ml}")
            return {"status": "error", "message": "O Mercado Livre retornou uma resposta inválida."}
        except Exception as e:
            logger.exception(f"Erro fatal no upload_xml: {e}")
            return {"status": "error", "message": f"Erro inesperado na integração ML: {str(e)}"}