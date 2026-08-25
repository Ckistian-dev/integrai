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

    def _extract_state_code(self, address_data: dict) -> models.EstadoEnum:
        """Extrai e valida o código do estado (UF) de um endereço do ML"""
        state_id = address_data.get('state', {}).get('id') or ''
        country_id = address_data.get('country', {}).get('id') or 'BR'
        
        # Se for exterior, mapeia para EX
        if country_id != 'BR':
            return models.EstadoEnum.EX
            
        if not state_id:
            return None
            
        # Pega os últimos 2 caracteres (ex: BR-SP -> SP ou simplesmente SP)
        extracted = str(state_id)[-2:].upper()
        if extracted in models.EstadoEnum.__members__:
            return models.EstadoEnum[extracted]
            
        return None

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
        logger.info(f"Resultado da pesquisa de pedidos da API do Mercado Livre: {json.dumps(data, default=str)}")
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
        
        # 1. Prioridade: Billing Info (Endpoint específico, com dados fiscais/CPF do comprador)
        doc_number = billing_info.get('doc_number') if billing_info else None
        doc_type = billing_info.get('doc_type') if billing_info else None
        
        if not doc_number:
            # 2. Fallback: Dados fiscais/billing do comprador dentro do pedido
            buyer_billing = ml_order.get('buyer', {}).get('billing_info', {})
            doc_number = buyer_billing.get('doc_number')
            if not doc_type:
                doc_type = buyer_billing.get('doc_type')

        if not doc_number:
            # 3. Fallback Final: ID do Comprador
            doc_number = f"ML{ml_order['buyer']['id']}" # Fallback
            logger.debug(f"Documento não encontrado nos dados do comprador. Usando fallback ID: {doc_number}")
        else:
            doc_number = "".join(c for c in str(doc_number) if c.isalnum()).upper()
        
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
        
        # --- NOVA LÓGICA: DADOS DO COMPRADOR ---
        nome_completo = None

        # 1. Tenta obter o nome/razão social a partir do billing_info (adicional ou principal)
        if billing_info:
            # 1a. Verifica additional_info
            add_info = billing_info.get('additional_info') or []
            if isinstance(add_info, list):
                # Procura por BUSINESS_NAME (Razão Social / Nome da empresa)
                bus_name = next((x.get('value') for x in add_info if x.get('type') == 'BUSINESS_NAME'), None)
                if bus_name:
                    nome_completo = bus_name
                else:
                    first = next((x.get('value') for x in add_info if x.get('type') == 'FIRST_NAME'), '')
                    last = next((x.get('value') for x in add_info if x.get('type') == 'LAST_NAME'), '')
                    full = f"{first} {last}".strip()
                    if full:
                        nome_completo = full

            # 1b. Fallback para campos principais do billing_info
            if not nome_completo:
                b_name = billing_info.get('name')
                b_last = billing_info.get('last_name')
                if b_name:
                    nome_completo = f"{b_name} {b_last or ''}".strip()

        # 2. Fallback para os dados de billing dentro do objeto do comprador no pedido
        if not nome_completo:
            buyer_billing = ml_order.get('buyer', {}).get('billing_info', {})
            if buyer_billing:
                b_name = buyer_billing.get('name')
                b_last = buyer_billing.get('last_name')
                if b_name:
                    nome_completo = f"{b_name} {b_last or ''}".strip()

        # 3. Fallback final para os dados gerais do comprador (first_name, last_name ou nickname)
        if not nome_completo:
            nome = ml_order.get('buyer', {}).get('first_name')
            sobrenome = ml_order.get('buyer', {}).get('last_name')
            nome_completo = f"{nome or ''} {sobrenome or ''}".strip()
            if not nome_completo:
                nome_completo = ml_order.get('buyer', {}).get('nickname')

        # Determina tipo de pessoa
        tipo_pessoa = CadastroTipoPessoaEnum.fisica
        if doc_type == 'CNPJ':
            tipo_pessoa = CadastroTipoPessoaEnum.juridica
        elif len(str(doc_number)) > 11:
             tipo_pessoa = CadastroTipoPessoaEnum.juridica

        logger.info(f"Criando novo cliente {doc_number} ({nome_completo}) para empresa {self.id_empresa}")
        novo_cliente = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj=str(doc_number),
            nome_razao=nome_completo[:255].upper(), # Limita tamanho e converte para caixa alta
            fantasia="CLIENTE MERCADO LIVRE",
            tipo_pessoa=tipo_pessoa,
            tipo_cadastro=CadastroTipoCadastroEnum.cliente,
            email=None, 
            telefone="".join(filter(str.isdigit, str(shipping_addr.get('receiver_phone') or '')))[:20],
            
            # Endereço
            cep="".join(filter(str.isdigit, str(shipping_addr.get('zip_code') or '')))[:9],
            logradouro=(shipping_addr.get('street_name') or '')[:255],
            numero=str(shipping_addr.get('street_number') or '')[:20],
            complemento=(shipping_addr.get('comment') or '')[:255],
            cidade=(shipping_addr.get('city', {}).get('name') or '')[:255],
            estado=self._extract_state_code(shipping_addr),
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
        """Busca ou cria transportadora com lógica avançada de assemelhação para ME1 e ME2"""
        if not shipment_details:
            return None

        # Extração de campos nativos do ML
        logistic_type = shipment_details.get('logistic_type')
        tracking_method = shipment_details.get('tracking_method')
        mode = shipment_details.get('mode')
        carrier_info = shipment_details.get('carrier_info')
        shipping_option = shipment_details.get('shipping_option') or {}

        carrier_name = None

        # 1. Prioridade: carrier_info estruturado
        if carrier_info:
            if isinstance(carrier_info, str):
                carrier_name = carrier_info
            elif isinstance(carrier_info, dict):
                carrier_name = carrier_info.get('description') or carrier_info.get('new_description')

        # 2. Se for ME1 (Logística Própria), valida pelo método de rastreio
        if not carrier_name and mode == 'me1':
            if tracking_method and tracking_method not in ['common_carrier', 'custom']:
                carrier_name = tracking_method.title() 

        # 3. Tenta pelo nome da opção selecionada pelo comprador
        if not carrier_name and shipping_option:
            opt_name = shipping_option.get('name', '')
            termos_genericos = ['normal', 'expresso', 'express', 'standard', 'grátis', 'super expresso']
            if opt_name and opt_name.lower() not in termos_genericos:
                carrier_name = opt_name

        # 4. Fallbacks baseados no tipo de logística interna do ML
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
                carrier_name = "Transportadora Padrão"

        carrier_name = str(carrier_name).strip()
        
        # --- ESTRATÉGIA DE ASSEMLHAÇÃO / NORMALIZAÇÃO ---
        normalized_lower = carrier_name.lower()
        search_terms = [carrier_name] # Lista de variações aceitáveis para o banco

        # Se for qualquer variação de logística oficial do ML, mira nos termos core do seu ERP
        if any(x in normalized_lower for x in ["mercado livre", "mercado envios", "meli"]):
            search_terms.extend(["Mercado Envios", "Mercado Livre", "MercadoLivre"])
        
        # Se for Correios
        elif "correios" in normalized_lower or "ect" in normalized_lower:
            search_terms.extend(["Correios", "ECT", "Empresa Brasileira de Correios"])
            
        # Para transportadoras ME1 de terceiros (ex: remove " - SP" de "Rodonaves - SP")
        else:
            clean_name = re.sub(r'\s*-\s*.*', '', carrier_name).strip()
            if clean_name and clean_name != carrier_name:
                search_terms.append(clean_name)

        # --- CONSULTA DINÂMICA COM OR NO BANCO ---
        from sqlalchemy import or_
        
        # Monta os filtros de aproximação baseados nos termos mapeados
        or_conditions = []
        for term in search_terms:
            or_conditions.append(models.Cadastro.nome_razao.ilike(f"%{term}%"))
            or_conditions.append(models.Cadastro.fantasia.ilike(f"%{term}%"))

        carrier = self.db.query(models.Cadastro).filter(
            models.Cadastro.tipo_cadastro == CadastroTipoCadastroEnum.transportadora,
            models.Cadastro.id_empresa == self.id_empresa,
            models.Cadastro.situacao == True,
            or_(*or_conditions)
        ).first()

        if carrier:
            logger.info(f"Transportadora vinculada com sucesso no ERP: '{carrier.nome_razao}' para o envio do ML '{carrier_name}'")
            return carrier

        # --- FALLBACK: CRIA SE NÃO EXISTIR ---
        # Garante o fluxo criando uma entidade limpa baseada no termo core principal encontrado
        display_name = "MERCADO ENVIOS" if "Mercado Envios" in search_terms else carrier_name.upper()
        
        logger.warning(f"Nenhuma transportadora compatível encontrada no ERP para '{carrier_name}'. Criando registro virtual.")
        new_carrier = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj='00000000000000',  # Dummy fiscal padrão para e-commerce
            nome_razao=display_name,
            fantasia=display_name,
            tipo_cadastro=CadastroTipoCadastroEnum.transportadora,
            tipo_pessoa=CadastroTipoPessoaEnum.juridica,
            situacao=True,
            criar_pedido_intelipost=False,
            cep="00000-000",
            logradouro="Endereço Virtual Logística ML",
            numero="S/N",
            cidade="Indefinida",
            estado=models.EstadoEnum.SP
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
        search_str = f"{order_id_ml}"
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
            logger.info(f"Resultado da busca do pedido {order_id_ml} na API do Mercado Livre: {json.dumps(ml_order, default=str)}")
            
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
                "id_produto": produto.id_sequencial,
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
        carrier_erp = self._find_or_create_carrier(shipment_details)
        transportadora_id = carrier_erp.id_sequencial if carrier_erp else None
            
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
        pack_id = ml_order.get('pack_id')
        if pack_id:
            obs_text = f"Pedido ML: {pack_id} | ID: {ml_order['id']} | Comprador: {ml_order['buyer']['nickname']}"
        else:
            obs_text = f"Pedido ML: {ml_order['id']} | Comprador: {ml_order['buyer']['nickname']}"
            
        if tracking_number:
            obs_text += f" | Rastreio: {tracking_number}"
        if shipping_option.get('name'):
            obs_text += f" | Serviço: {shipping_option.get('name')}"
        if shipment_details.get('logistic_type'):
            obs_text += f" | Logística: {shipment_details.get('logistic_type')}"
        
        # Identifica se não há endereço para marcar como "A Combinar"
        if not shipment_details.get('receiver_address'):
            obs_text += " | Entrega a Combinar"

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

        # Verifica se já existe um pedido importado com o mesmo pack_id
        pack_id = ml_order.get('pack_id')
        if pack_id:
            search_pack = f"Pedido ML: {pack_id}"
            existing_pedido = self.db.query(models.Pedido).filter(
                models.Pedido.observacao.contains(search_pack),
                models.Pedido.id_empresa == self.id_empresa,
                models.Pedido.situacao != 'cancelado'
            ).first()

            if existing_pedido:
                logger.info(f"Encontrado pedido existente {existing_pedido.id} com o mesmo pack_id {pack_id}. Unificando itens...")
                # Unifica itens
                current_items = list(existing_pedido.itens) if existing_pedido.itens else []
                for new_item in itens_erp:
                    found = False
                    for existing_item in current_items:
                        if existing_item.get('id_produto') == new_item['id_produto'] and existing_item.get('valor_unitario') == new_item['valor_unitario']:
                            existing_item['quantidade'] += new_item['quantidade']
                            existing_item['subtotal'] = round(existing_item['subtotal'] + new_item['subtotal'], 2)
                            existing_item['valor_ipi'] = round(existing_item['valor_ipi'] + new_item['valor_ipi'], 2)
                            existing_item['total_com_ipi'] = round(existing_item['total_com_ipi'] + new_item['total_com_ipi'], 2)
                            found = True
                            break
                    if not found:
                        current_items.append(new_item)
                existing_pedido.itens = current_items
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(existing_pedido, "itens")

                # Atualiza volumes e pesos
                peso_bruto_total_merged = (float(existing_pedido.volumes_peso_bruto) if existing_pedido.volumes_peso_bruto else 0.0) + peso_bruto_total
                existing_pedido.volumes_peso_bruto = peso_bruto_total_merged if peso_bruto_total_merged > 0 else None
                existing_pedido.volumes_peso_liquido = peso_bruto_total_merged if peso_bruto_total_merged > 0 else None

                # Atualiza valor de frete (soma se houver frete adicional)
                existing_pedido.valor_frete = float(existing_pedido.valor_frete or 0) + valor_frete

                # Recalcula total final
                total_prod_merged = sum(float(item['subtotal']) for item in current_items)
                total_ipi_merged = sum(float(item.get('valor_ipi') or 0) for item in current_items)
                
                total_pedido_merged = total_prod_merged + total_ipi_merged
                if existing_pedido.modalidade_frete == PedidoModalidadeFreteEnum.fob:
                    total_pedido_merged += float(existing_pedido.valor_frete or 0)
                existing_pedido.total = total_pedido_merged

                # Atualiza observação para incluir os dois IDs reais do Mercado Livre
                obs = existing_pedido.observacao or ""
                match_id = re.search(r"ID:\s*([\d,\s]+)", obs)
                if match_id:
                    old_ids = match_id.group(1).strip()
                    existing_ids_list = [x.strip() for x in old_ids.split(',')]
                    if order_id_ml not in existing_ids_list:
                        new_ids_str = f"{old_ids}, {order_id_ml}"
                        obs = obs.replace(match_id.group(0), f"ID: {new_ids_str}")
                else:
                    obs += f" | ID: {order_id_ml}"
                existing_pedido.observacao = obs

                # Atualiza campos dedicados de integração
                if existing_pedido.meli_order_id:
                    existing_ids = [x.strip() for x in str(existing_pedido.meli_order_id).split(',')]
                    if str(order_id_ml) not in existing_ids:
                        existing_pedido.meli_order_id = f"{existing_pedido.meli_order_id}, {order_id_ml}"
                else:
                    existing_pedido.meli_order_id = str(order_id_ml)
                if not existing_pedido.meli_pack_id and pack_id:
                    existing_pedido.meli_pack_id = str(pack_id)
                if not existing_pedido.meli_shipment_id and ship_id:
                    existing_pedido.meli_shipment_id = str(ship_id)
                if not existing_pedido.meli_tracking_number and tracking_number:
                    existing_pedido.meli_tracking_number = tracking_number
                if not existing_pedido.meli_logistic_type and shipment_details.get('logistic_type'):
                    existing_pedido.meli_logistic_type = shipment_details.get('logistic_type')
                if not existing_pedido.meli_shipping_service and shipping_option.get('name'):
                    existing_pedido.meli_shipping_service = shipping_option.get('name')
                if shipment_details.get('status'):
                    existing_pedido.meli_status_envio = str(shipment_details.get('status'))

                self.db.add(existing_pedido)
                self.db.commit()
                self.db.refresh(existing_pedido)
                logger.info(f"Pedido unificado com sucesso no ID ERP {existing_pedido.id}")
                return existing_pedido

        # 6. Criação do Pedido
        data_ml = datetime.fromisoformat(ml_order['date_created'].replace('Z', '+00:00'))
        
        # Pega os dados do envio que já foram buscados
        shipping_addr = shipment_details.get('receiver_address', {})
        
        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=cliente_erp.id_sequencial,
            id_vendedor=self.config.vendedor_padrao_id,
            situacao=self.config.situacao_pedido_inicial or PedidoSituacaoEnum.orcamento,
            data_orcamento=data_ml.date(),
            data_validade=data_ml.date(),
            data_entrega=data_entrega,
            origem_venda="Mercado Livre",
            
            # --- CAMPOS DEDICADOS MERCADO LIVRE ---
            meli_order_id=str(ml_order['id']),
            meli_pack_id=str(pack_id) if pack_id else None,
            meli_shipment_id=str(ship_id) if ship_id else None,
            meli_buyer_nickname=ml_order.get('buyer', {}).get('nickname'),
            meli_tracking_number=tracking_number,
            meli_logistic_type=shipment_details.get('logistic_type'),
            meli_shipping_service=shipping_option.get('name'),
            meli_status_envio=str(shipment_details.get('status')) if shipment_details.get('status') else None,

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
            endereco_numero=str(shipping_addr.get('street_number') or '')[:20],
            endereco_complemento=(shipping_addr.get('comment') or '')[:255],
            endereco_cidade=(shipping_addr.get('city', {}).get('name') or '')[:255],
            endereco_estado=self._extract_state_code(shipping_addr),
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

    async def _resolve_all_ml_ids(self, client, order_id_ml: str):
        """
        Resolve todos os IDs (order_id, pack_id, shipment_id) a partir de qualquer ID do Mercado Livre.
        """
        logger.info(f"Resolvendo estrutura de IDs ML para: {order_id_ml}")
        ids = {
            "order_id": None,
            "pack_id": None,
            "shipment_id": None
        }

        # 1. Tenta como Order ID
        try:
            order_resp = await client.get(f"{self.base_url}/orders/{order_id_ml}")
            if order_resp.status_code == 200:
                order_data = order_resp.json()
                ids["order_id"] = str(order_data.get('id'))
                if order_data.get('pack_id'):
                    ids["pack_id"] = str(order_data.get('pack_id'))
                ship_id = order_data.get('shipping', {}).get('id')
                if ship_id:
                    ids["shipment_id"] = str(ship_id)
                logger.info(f"IDs resolvidos via Order: {ids}")
                return ids
        except Exception as e:
            logger.debug(f"Falha ao resolver como Order ID: {e}")

        # 2. Tenta como Pack ID
        try:
            pack_resp = await client.get(f"{self.base_url}/packs/{order_id_ml}")
            if pack_resp.status_code == 200:
                pack_data = pack_resp.json()
                ids["pack_id"] = str(order_id_ml)
                orders = pack_data.get('orders', [])
                if orders:
                    first_order_id = orders[0].get('id')
                    if first_order_id:
                        ids["order_id"] = str(first_order_id)
                        try:
                            order_resp = await client.get(f"{self.base_url}/orders/{first_order_id}")
                            if order_resp.status_code == 200:
                                ship_id = order_resp.json().get('shipping', {}).get('id')
                                if ship_id:
                                    ids["shipment_id"] = str(ship_id)
                        except:
                            pass
                logger.info(f"IDs resolvidos via Pack: {ids}")
                return ids
        except Exception as e:
            logger.debug(f"Falha ao resolver como Pack ID: {e}")

        # 3. Tenta como Shipment ID
        try:
            ship_resp = await client.get(f"{self.base_url}/shipments/{order_id_ml}")
            if ship_resp.status_code == 200:
                ship_data = ship_resp.json()
                ids["shipment_id"] = str(order_id_ml)
                if ship_data.get('order_id'):
                    ids["order_id"] = str(ship_data.get('order_id'))
                logger.info(f"IDs resolvidos via Shipment: {ids}")
                return ids
        except Exception as e:
            logger.debug(f"Falha ao resolver como Shipment ID: {e}")

        # Fallback se nada respondeu 200
        ids["order_id"] = str(order_id_ml)
        return ids

    async def _resolve_shipment_id(self, client, order_id_ml: str):
        """
        Método de compatibilidade para obter apenas o shipment_id.
        """
        all_ids = await self._resolve_all_ml_ids(client, order_id_ml)
        return all_ids.get("shipment_id")

    async def upload_xml(
        self,
        order_id_ml: str,
        xml_content: str,
        chave_acesso: str = None,
        numero_nf: str = None,
        data_emissao: str = None
    ):
        """
        Envia o XML da NFe para o Mercado Livre utilizando estratégias adaptativas
        para Mercado Envios (ME2) e Envio Próprio / Outras Transportadoras (Custom, ME1, Packs, etc.).
        """
        if settings.ENVIRONMENT != "production":
            logger.info(f"Simulando upload de XML para pedido ML {order_id_ml} (Ambiente: {settings.ENVIRONMENT})")
            return {"status": "success", "message": "Simulado: XML enviado (Ambiente de Testes)"}

        logger.info(f"Iniciando upload de XML para pedido ML {order_id_ml}")
        client = await self.get_client()

        # 1. Parse de metadados do XML se ausentes
        xml_str = xml_content if isinstance(xml_content, str) else xml_content.decode('utf-8')
        xml_str = xml_str.strip()
        if not xml_str.startswith('<?xml'):
            xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + xml_str
        xml_bytes = xml_str.encode('utf-8')

        serie = "1"
        try:
            if not chave_acesso:
                ch_match = re.search(r"<chNFe>([^<]+)</chNFe>", xml_str)
                if ch_match:
                    chave_acesso = ch_match.group(1)
                else:
                    id_match = re.search(r'infNFe\s+Id="NFe([^"]+)"', xml_str)
                    if id_match:
                        chave_acesso = id_match.group(1)

            if not numero_nf:
                n_nf_match = re.search(r"<nNF>([^<]+)</nNF>", xml_str)
                if n_nf_match:
                    numero_nf = n_nf_match.group(1)

            s_match = re.search(r"<serie>([^<]+)</serie>", xml_str)
            if s_match:
                serie = s_match.group(1)

            if not data_emissao:
                dh_emi_match = re.search(r"<dhEmi>([^<]+)</dhEmi>", xml_str)
                if dh_emi_match:
                    dh_emi = dh_emi_match.group(1)
                    if "." not in dh_emi:
                        tz_match = re.search(r"([+-]\d{2}:\d{2}|Z)$", dh_emi)
                        if tz_match:
                            tz = tz_match.group(1)
                            base_time = dh_emi[:-len(tz)]
                            data_emissao = f"{base_time}.000{tz}"
                        else:
                            data_emissao = f"{dh_emi}.000"
                    else:
                        data_emissao = dh_emi
                else:
                    data_emissao = datetime.now().isoformat()
        except Exception as parse_err:
            logger.warning(f"Erro ao extrair metadados do XML no upload_xml: {parse_err}")

        # 2. Resolve a estrutura completa de IDs
        resolved_ids = await self._resolve_all_ml_ids(client, order_id_ml)
        shipment_id = resolved_ids.get("shipment_id")
        pack_id = resolved_ids.get("pack_id")
        order_id = resolved_ids.get("order_id") or order_id_ml

        logger.info(f"Tentando upload XML Mercado Livre com IDs: shipment_id={shipment_id}, pack_id={pack_id}, order_id={order_id}")

        params = {"siteId": "MLB", "site_id": "MLB"}
        errors_logged = []

        def is_already_sent_response(resp_status: int, resp_text: str) -> bool:
            txt = resp_text.lower()
            if resp_status in [400, 409] and any(k in txt for k in ["already", "duplicat", "salva", "gerada", "existente"]):
                return True
            return False

        def check_biller_error(resp_status: int, resp_text: str):
            if resp_status == 403 and "biller" in resp_text.lower():
                return {"status": "warning", "message": "Upload ignorado: Sua conta está configurada para usar o Faturador do Mercado Livre. Desative-o no painel do ML para emitir pelo ERP."}
            return None

        # --- ESTRATÉGIA 1: POST /shipments/{shipment_id}/invoice_data com Raw XML (Content-Type: application/xml) ---
        if shipment_id:
            try:
                url_ship = f"{self.base_url}/shipments/{shipment_id}/invoice_data"
                logger.debug(f"Tentativa 1 (Raw application/xml): {url_ship}")
                resp1 = await client.post(url_ship, content=xml_bytes, headers={"Content-Type": "application/xml"}, params=params)
                
                biller_warn = check_biller_error(resp1.status_code, resp1.text)
                if biller_warn:
                    return biller_warn

                if resp1.status_code in [200, 201]:
                    logger.info(f"✅ XML anexado com sucesso via raw application/xml (shipment {shipment_id})")
                    return {"status": "success"}
                elif is_already_sent_response(resp1.status_code, resp1.text):
                    logger.warning(f"XML já consta no ML para shipment {shipment_id}")
                    return {"status": "already_sent"}
                else:
                    err_str = f"Raw application/xml ({resp1.status_code}): {resp1.text}"
                    errors_logged.append(err_str)
                    logger.debug(f"Tentativa 1 não concluída: {err_str}")
            except Exception as e:
                logger.debug(f"Exceção na tentativa 1: {e}")
                errors_logged.append(f"Raw application/xml erro interno: {e}")

        # --- ESTRATÉGIA 2: POST /shipments/{shipment_id}/invoice_data com Raw XML (Content-Type: text/xml) ---
        if shipment_id:
            try:
                url_ship_txt = f"{self.base_url}/shipments/{shipment_id}/invoice_data"
                logger.debug(f"Tentativa 2 (Raw text/xml): {url_ship_txt}")
                resp2 = await client.post(url_ship_txt, content=xml_bytes, headers={"Content-Type": "text/xml; charset=utf-8"}, params=params)
                
                biller_warn = check_biller_error(resp2.status_code, resp2.text)
                if biller_warn:
                    return biller_warn

                if resp2.status_code in [200, 201]:
                    logger.info(f"✅ XML anexado com sucesso via raw text/xml (shipment {shipment_id})")
                    return {"status": "success"}
                elif is_already_sent_response(resp2.status_code, resp2.text):
                    logger.warning(f"XML já consta no ML para shipment {shipment_id}")
                    return {"status": "already_sent"}
                else:
                    err_str = f"Raw text/xml ({resp2.status_code}): {resp2.text}"
                    errors_logged.append(err_str)
                    logger.debug(f"Tentativa 2 não concluída: {err_str}")
            except Exception as e:
                logger.debug(f"Exceção na tentativa 2: {e}")
                errors_logged.append(f"Raw text/xml erro interno: {e}")

        # --- ESTRATÉGIA 3: POST /shipments/{shipment_id}/invoice_data com Multipart (fiscal_document) ---
        if shipment_id:
            try:
                url_ship_mp = f"{self.base_url}/shipments/{shipment_id}/invoice_data"
                logger.debug(f"Tentativa 3 (Shipment Multipart): {url_ship_mp}")
                files = {
                    'fiscal_document': ('nfe.xml', xml_bytes, 'application/xml')
                }
                resp3 = await client.post(url_ship_mp, files=files, params=params)
                
                biller_warn = check_biller_error(resp3.status_code, resp3.text)
                if biller_warn:
                    return biller_warn

                if resp3.status_code in [200, 201]:
                    logger.info(f"✅ XML anexado com sucesso via multipart em shipment {shipment_id}")
                    return {"status": "success"}
                elif is_already_sent_response(resp3.status_code, resp3.text):
                    return {"status": "already_sent"}
                else:
                    err_str = f"Shipment Multipart ({resp3.status_code}): {resp3.text}"
                    errors_logged.append(err_str)
                    logger.debug(f"Tentativa 3 não concluída: {err_str}")
            except Exception as e:
                logger.debug(f"Exceção na tentativa 3: {e}")
                errors_logged.append(f"Shipment Multipart erro interno: {e}")

        # --- ESTRATÉGIA 4: POST /packs/{pack_id}/fiscal_documents com Multipart (Apenas quando pack_id existe) ---
        if pack_id:
            try:
                url_pack_mp = f"{self.base_url}/packs/{pack_id}/fiscal_documents"
                logger.debug(f"Tentativa 4 (Pack Multipart): {url_pack_mp}")
                files = {
                    'fiscal_document': ('nfe.xml', xml_bytes, 'application/xml')
                }
                resp4 = await client.post(url_pack_mp, files=files, params=params)
                
                biller_warn = check_biller_error(resp4.status_code, resp4.text)
                if biller_warn:
                    return biller_warn

                if resp4.status_code in [200, 201]:
                    logger.info(f"✅ XML anexado com sucesso via multipart em pack {pack_id}")
                    return {"status": "success"}
                elif is_already_sent_response(resp4.status_code, resp4.text):
                    return {"status": "already_sent"}
                else:
                    err_str = f"Pack Fiscal Documents ({resp4.status_code}): {resp4.text}"
                    errors_logged.append(err_str)
                    logger.debug(f"Tentativa 4 não concluída: {err_str}")
            except Exception as e:
                logger.debug(f"Exceção na tentativa 4: {e}")
                errors_logged.append(f"Pack Fiscal Documents erro interno: {e}")

        # Se todas as tentativas válidas falharam
        main_error = errors_logged[0] if errors_logged else "Envio recusado pelo Mercado Livre"
        all_details = " | ".join(errors_logged)
        logger.error(f"❌ Todas as tentativas de upload de XML para o pedido ML {order_id_ml} falharam. Detalhes: {all_details}")
        return {"status": "error", "message": f"Erro na API do Mercado Livre ao anexar XML da NF-e: {main_error}"}

    def _extract_ml_ids_from_pedido(self, pedido):
        """
        Extrai os IDs do Mercado Livre do pedido (order_id, pack_id, shipment_id),
        com fallback inteligente para extração a partir do campo 'observacao'
        caso as colunas dedicadas ainda não tenham sido preenchidas.
        """
        ids = set()
        if getattr(pedido, 'meli_order_id', None):
            for part in str(pedido.meli_order_id).split(','):
                clean = part.strip()
                if clean:
                    ids.add(clean)
        if getattr(pedido, 'meli_pack_id', None):
            for part in str(pedido.meli_pack_id).split(','):
                clean = part.strip()
                if clean:
                    ids.add(clean)
        if getattr(pedido, 'meli_shipment_id', None):
            ids.add(str(pedido.meli_shipment_id).strip())

        # Fallback para parsing de observacao
        if not ids and getattr(pedido, 'observacao', None):
            obs = pedido.observacao
            m_pack_and_id = re.search(r"Pedido ML:\s*(\d+)\s*\|\s*ID:\s*([\d,\s]+)", obs)
            if m_pack_and_id:
                pack_id = m_pack_and_id.group(1).strip()
                order_id = m_pack_and_id.group(2).strip()
                ids.add(pack_id)
                for o_id in order_id.split(','):
                    if o_id.strip():
                        ids.add(o_id.strip())
                if not pedido.meli_pack_id:
                    pedido.meli_pack_id = pack_id
                if not pedido.meli_order_id:
                    pedido.meli_order_id = order_id
            else:
                m_single_id = re.search(r"Pedido ML:\s*([\d,\s]+)", obs)
                if m_single_id:
                    order_id = m_single_id.group(1).strip()
                    for o_id in order_id.split(','):
                        if o_id.strip():
                            ids.add(o_id.strip())
                    if not pedido.meli_order_id:
                        pedido.meli_order_id = order_id
                else:
                    m_generic_id = re.search(r"(?:Pedido|ID ML:?)\s*(\d{15,})", obs)
                    if m_generic_id:
                        order_id = m_generic_id.group(1).strip()
                        ids.add(order_id)
                        if not pedido.meli_order_id:
                            pedido.meli_order_id = order_id

            m_buyer = re.search(r"Comprador:\s*([^|]+)", obs)
            if m_buyer and not pedido.meli_buyer_nickname:
                pedido.meli_buyer_nickname = m_buyer.group(1).strip()

            m_service = re.search(r"Servi[çc]o:\s*([^|]+)", obs)
            if m_service and not pedido.meli_shipping_service:
                pedido.meli_shipping_service = m_service.group(1).strip()

            m_log = re.search(r"Log[íi]stica:\s*([^|]+)", obs)
            if m_log and not pedido.meli_logistic_type:
                pedido.meli_logistic_type = m_log.group(1).strip()

            if ids:
                try:
                    self.db.add(pedido)
                    self.db.commit()
                except Exception:
                    pass

        return list(ids)

    async def update_shipment_status_by_order(self, order_id_ml: str, erp_status: str, tracking_number: str = None, target_ml_status: str = None, pedido = None):
        """
        Busca a shipment associada ao pedido no ML e atualiza seu status.
        Utiliza _resolve_all_ml_ids para tratar tanto order_id quanto pack_id e shipment_id.
        """
        try:
            client = await self.get_client()
            
            # 1. Resolve o shipment_id a partir do ID fornecido (suporta order_id, pack_id e shipment_id)
            resolved = await self._resolve_all_ml_ids(client, order_id_ml)
            shipment_id = resolved.get("shipment_id")
            
            if not shipment_id:
                logger.warning(f"ID Mercado Livre {order_id_ml} não possui shipment_id associado.")
                return False
                
            # 2. Busca dados do envio para verificar a modalidade logística
            ship_resp = await client.get(f"{self.base_url}/shipments/{shipment_id}")
            if ship_resp.status_code != 200:
                logger.error(f"Erro ao buscar envio {shipment_id}: {ship_resp.status_code} - {ship_resp.text}")
                return False
                
            shipment_details = ship_resp.json()
            mode = shipment_details.get('mode') or ''
            logistic_type = shipment_details.get('logistic_type') or ''
            current_status = shipment_details.get('status')
            
            logger.info(f"Envio {shipment_id} - Mode: '{mode}' | Logistic Type: '{logistic_type}' | Status ML Atual: '{current_status}'")
            
            # Atualiza no pedido local o status e dados do ML
            if pedido:
                pedido.meli_shipment_id = str(shipment_id)
                if current_status:
                    pedido.meli_status_envio = str(current_status)
                if logistic_type and not pedido.meli_logistic_type:
                    pedido.meli_logistic_type = str(logistic_type)
                try:
                    self.db.add(pedido)
                    self.db.commit()
                except Exception:
                    pass

            # Verificação de modalidade manual (ME1 / Custom Shipping / Frete Próprio)
            # ME1 tem mode='me1' e logistic_type='default'
            is_manual_mode = (
                mode in ['me1', 'custom', 'not_specified'] or 
                logistic_type in ['custom', 'not_specified'] or 
                not mode
            )
            
            if not is_manual_mode:
                logger.info(f"Envio {shipment_id} utiliza Mercado Envios 2 ({logistic_type}/{mode}). A mudança para 'a caminho' e 'entregue' ocorre via leitura/bip da agência/coleta do ML e baixa da transportadora.")
                return True
                
            # Mapeamento e atualização para envios manuais / ME1
            new_ml_status = target_ml_status
            if not new_ml_status:
                erp_status_lower = (erp_status or "").lower()
                if erp_status_lower in ['despachado', 'em transito', 'em trânsito', 'shipped']:
                    new_ml_status = 'shipped'
                elif erp_status_lower in ['faturamento', 'expedicao', 'expedição', 'embalagem', 'produção', 'producao']:
                    if current_status in ['pending', 'handling']:
                        new_ml_status = 'handling'
                elif erp_status_lower in ['finalizado', 'entregue', 'delivered']:
                    new_ml_status = 'delivered'
                        
            if not new_ml_status:
                logger.debug(f"Nenhum status correspondente para atualizar no ML para o status ERP {erp_status}.")
                return False
                
            if current_status == new_ml_status and not tracking_number:
                logger.info(f"Envio {shipment_id} já está no status {new_ml_status}.")
                return True
                
            # 3. Executa a atualização do status e rastreio do envio (ME1 / Custom)
            payload = {"status": new_ml_status}
            if tracking_number:
                payload["tracking_number"] = tracking_number

            # Se for ME1 / Custom, o Mercado Livre exige obrigatoriamente 'service_id' para marcar como shipped
            if mode == 'me1' or logistic_type in ['default', 'custom']:
                existing_service_id = shipment_details.get('service_id')
                if existing_service_id:
                    payload["service_id"] = existing_service_id
                else:
                    shipping_opt_name = str(shipment_details.get('shipping_option', {}).get('name') or '').lower()
                    shipping_method_id = shipment_details.get('shipping_option', {}).get('shipping_method_id')
                    if "expresso" in shipping_opt_name or shipping_method_id == 182:
                        payload["service_id"] = 22  # Sedex / Expresso
                    else:
                        payload["service_id"] = 21  # PAC / Normal (Padrão ME1 MLB)

            logger.info(f"Enviando atualização para envio {shipment_id}: {payload}")
            url = f"{self.base_url}/shipments/{shipment_id}"
            resp = await client.put(url, json=payload)
            
            if resp.status_code in [200, 201]:
                logger.info(f"Status do envio {shipment_id} atualizado com sucesso para {new_ml_status}!")
                if pedido:
                    pedido.meli_status_envio = new_ml_status
                    try:
                        self.db.add(pedido)
                        self.db.commit()
                    except Exception:
                        pass
                return True
            else:
                logger.error(f"Erro ao atualizar status do envio {shipment_id}: {resp.status_code} - {resp.text}")
                return False
                
        except Exception as e:
            logger.exception(f"Erro ao atualizar status de envio no Mercado Livre: {e}")
            return False

    async def update_meli_order_status(self, pedido):
        """
        Atualiza o status dos envios no Mercado Livre associados a um pedido do ERP.
        Utiliza os campos dedicados com fallback para parsing da observação.
        """
        import unicodedata
        
        def normalize_str(val):
            if not val:
                return ""
            val_str = str(val).strip().lower()
            return ''.join(c for c in unicodedata.normalize('NFD', val_str) if unicodedata.category(c) != 'Mn')

        ml_order_ids = self._extract_ml_ids_from_pedido(pedido)
        if not ml_order_ids:
            logger.debug(f"Nenhum ID do Mercado Livre configurado ou localizado no pedido {pedido.id}")
            return False
            
        situacao_para_str = pedido.situacao.value if hasattr(pedido.situacao, 'value') else str(pedido.situacao or "")
        tracking_number = (
            getattr(pedido, 'meli_tracking_number', None) or 
            getattr(pedido, 'intelipost_tracking_code', None) or
            getattr(pedido, 'numero_nf', None)
        )

        # Avaliação de Regras da MeliConfiguracao (se houver)
        target_ml_status = None
        regras = getattr(self.config, 'regras_atualizacao_status', None) or []
        if isinstance(regras, list):
            for regra in regras:
                coluna = regra.get('coluna_pedido')
                valor_esperado_norm = normalize_str(regra.get('valor_coluna', ''))
                status_alvo_ml = regra.get('status_meli')
                
                if coluna and valor_esperado_norm and status_alvo_ml:
                    val_atual = getattr(pedido, coluna, None)
                    if hasattr(val_atual, 'value'):
                        val_atual = val_atual.value
                    elif hasattr(val_atual, 'name'):
                        val_atual = val_atual.name
                    val_atual_norm = normalize_str(val_atual)
                    
                    # Match exato ou equivalências semânticas
                    matched = False
                    if val_atual_norm == valor_esperado_norm:
                        matched = True
                    elif valor_esperado_norm in ["entregue", "delivered"] and val_atual_norm in ["entregue", "delivered"]:
                        matched = True
                    elif valor_esperado_norm in ["em transito", "shipped", "despachado", "a caminho"] and val_atual_norm in ["em transito", "shipped", "despachado", "a caminho"]:
                        matched = True
                    elif valor_esperado_norm in ["faturamento", "handling"] and val_atual_norm in ["faturamento", "handling"]:
                        matched = True

                    if matched:
                        target_ml_status = status_alvo_ml
                        logger.info(f"Regra ML casou! Coluna '{coluna}' = '{val_atual}' -> Status ML: '{target_ml_status}'")
                        break
            
        logger.info(f"Atualizando status no Mercado Livre para pedido ERP #{pedido.id} ({situacao_para_str}) -> IDs ML: {ml_order_ids} | Status ML Alvo: {target_ml_status or 'Auto/Padrão'}")
        
        success = True
        for ml_order_id in ml_order_ids:
            res = await self.update_shipment_status_by_order(ml_order_id, situacao_para_str, tracking_number, target_ml_status=target_ml_status, pedido=pedido)
            if not res:
                success = False
        return success

    async def process_meli_webhook(self, topic: str, resource: str, user_id_ml: int = None):
        """
        Processa notificações (Webhooks) do Mercado Livre para manter os pedidos atualizados no ERP.
        Suporta tópicos: 'shipments', 'orders_v2', 'orders', 'packs'.
        """
        from sqlalchemy import or_
        logger.info(f"Processando Webhook ML: topic={topic}, resource={resource}, user_id={user_id_ml} para empresa {self.id_empresa}")
        client = await self.get_client()

        if topic == "shipments" or "/shipments/" in resource:
            shipment_id = resource.strip().split('/')[-1]
            if not shipment_id.isdigit():
                return {"status": "ignored", "reason": "invalid_shipment_id"}

            ship_resp = await client.get(f"{self.base_url}/shipments/{shipment_id}")
            if ship_resp.status_code != 200:
                logger.error(f"Erro ao consultar shipment {shipment_id} no webhook: {ship_resp.status_code}")
                return {"status": "error", "message": ship_resp.text}

            ship_data = ship_resp.json()
            order_id = str(ship_data.get('order_id') or '')
            ml_status = ship_data.get('status')
            ml_substatus = ship_data.get('substatus')
            tracking_number = ship_data.get('tracking_number')
            logistic_type = ship_data.get('logistic_type')
            
            logger.info(f"Webhook ML Shipment {shipment_id}: Status={ml_status}, Substatus={ml_substatus}, OrderID={order_id}")

            # Localiza o pedido no ERP
            pedido = self.db.query(models.Pedido).filter(
                models.Pedido.id_empresa == self.id_empresa,
                or_(
                    models.Pedido.meli_shipment_id == str(shipment_id),
                    models.Pedido.meli_order_id.contains(str(order_id)) if order_id else False,
                    models.Pedido.observacao.contains(str(order_id)) if order_id else False,
                    models.Pedido.observacao.contains(str(shipment_id))
                )
            ).first()

            if not pedido:
                logger.info(f"Pedido correspondente ao shipment {shipment_id} / order {order_id} não encontrado no banco local.")
                return {"status": "not_found", "shipment_id": shipment_id}

            # Atualiza campos dedicados
            pedido.meli_shipment_id = str(shipment_id)
            if ml_status:
                pedido.meli_status_envio = str(ml_status)
            if tracking_number and not pedido.meli_tracking_number:
                pedido.meli_tracking_number = str(tracking_number)
            if logistic_type and not pedido.meli_logistic_type:
                pedido.meli_logistic_type = str(logistic_type)

            # Atualiza datas de despacho / entrega
            if ml_status in ['shipped', 'in_transit']:
                if not pedido.data_despacho:
                    pedido.data_despacho = datetime.now(timezone.utc).date()
            elif ml_status in ['delivered']:
                if not pedido.data_finalizacao:
                    pedido.data_finalizacao = datetime.now(timezone.utc).date()
                if not pedido.data_entrega:
                    pedido.data_entrega = datetime.now(timezone.utc).date()

            self.db.commit()
            self.db.refresh(pedido)
            logger.info(f"Pedido ERP #{pedido.id} atualizado via Webhook ML! meli_status_envio={pedido.meli_status_envio}")
            return {"status": "success", "pedido_id": pedido.id, "meli_status_envio": pedido.meli_status_envio}

        elif topic in ["orders_v2", "orders"] or "/orders/" in resource:
            order_id = resource.strip().split('/')[-1]
            if not order_id.isdigit():
                return {"status": "ignored", "reason": "invalid_order_id"}

            order_resp = await client.get(f"{self.base_url}/orders/{order_id}")
            if order_resp.status_code != 200:
                return {"status": "error", "message": order_resp.text}

            order_data = order_resp.json()
            shipping_id = order_data.get('shipping', {}).get('id')
            
            pedido = self.db.query(models.Pedido).filter(
                models.Pedido.id_empresa == self.id_empresa,
                or_(
                    models.Pedido.meli_order_id.contains(str(order_id)),
                    models.Pedido.observacao.contains(str(order_id)),
                    models.Pedido.meli_shipment_id == str(shipping_id) if shipping_id else False
                )
            ).first()

            if pedido:
                if shipping_id and not pedido.meli_shipment_id:
                    pedido.meli_shipment_id = str(shipping_id)
                self.db.commit()
                return {"status": "success", "pedido_id": pedido.id}

        return {"status": "ok"}