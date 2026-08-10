import requests
import logging
import json
import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException
from requests_oauthlib import OAuth1
from oauthlib.oauth1 import SIGNATURE_HMAC_SHA256
from app.core.db import models
from app.core.db.models import (
    CadastroTipoPessoaEnum, CadastroTipoCadastroEnum, CadastroIndicadorIEEnum,
    PedidoModalidadeFreteEnum
)

logger = logging.getLogger(__name__)

class MagentoService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        
        # Carrega configurações
        self.config = self.db.query(models.MagentoConfiguracao).filter(
            models.MagentoConfiguracao.id_empresa == self.id_empresa
        ).first()

        if not self.config:
            raise HTTPException(status_code=400, detail="Configuração Magento não encontrada.")
            
        # Normaliza a URL base (garante que não tenha barra no final e inclui o protocolo se faltar)
        self.base_url = self.config.base_url.rstrip('/')
        if not self.base_url.startswith('http'):
            self.base_url = f"https://{self.base_url}"
            
        self.api_base = f"{self.base_url}/rest/{self.config.store_view_code}/V1"

    def _get_auth(self):
        """
        Retorna o objeto de autenticação OAuth 1.0 com HMAC-SHA256.
        """
        # Validação de segurança
        if not all([
            self.config.consumer_key, 
            self.config.consumer_secret, 
            self.config.access_token, 
            self.config.token_secret
        ]):
            logger.error(f"Credenciais OAuth incompletas para empresa {self.id_empresa}.")
            raise HTTPException(
                status_code=500, 
                detail="Configuração de integração incompleta (Chaves OAuth faltando)."
            )

        return OAuth1(
            self.config.consumer_key,
            client_secret=self.config.consumer_secret,
            resource_owner_key=self.config.access_token,
            resource_owner_secret=self.config.token_secret,
            signature_method=SIGNATURE_HMAC_SHA256
        )

    def _extract_field_value(self, order, field):
        """Helper para extrair valor do pedido para filtragem, tratando campos virtuais"""
        if field == 'payment_method':
            return order.get('payment', {}).get('method')
        elif field == 'customer_name':
            first = order.get('customer_firstname') or order.get('billing_address', {}).get('firstname', '')
            last = order.get('customer_lastname') or order.get('billing_address', {}).get('lastname', '')
            return f"{first} {last}".strip()
        elif field == 'ja_importado':
            return str(order.get('ja_importado', False)).lower()
        return order.get(field)

    def list_orders(self, limit=10, offset=0, filters=None):
        """
        Lista pedidos do Magento usando SearchCriteria.
        Converte offset/limit para currentPage/pageSize.
        """
        logger.info(f"Listando pedidos Magento para empresa {self.id_empresa} (limit={limit}, offset={offset})")
        # Aumentamos o limite para buscar um lote maior e filtrar localmente, evitando erro 500 no Magento
        page_size = 200 
        current_page = 1 # Buscamos sempre os mais recentes para o processo de importação

        # Monta a URL com SearchCriteria
        # Filtra apenas pedidos recentes ou todos (aqui configurado para buscar os mais recentes primeiro)
        url = f"{self.api_base}/orders"
        params = {
            "searchCriteria[pageSize]": page_size,
            "searchCriteria[currentPage]": current_page,
            "searchCriteria[sortOrders][0][field]": "created_at",
            "searchCriteria[sortOrders][0][direction]": "DESC",
            "searchCriteria[filter_groups][0][filters][0][field]": "status",
            "searchCriteria[filter_groups][0][filters][0][value]": "processing,complete,em_producao",
            "searchCriteria[filter_groups][0][filters][0][condition_type]": "in"
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            logger.debug(f"Enviando requisição GET para {url} com params: {params}")
            resp = requests.get(url, auth=self._get_auth(), params=params, headers=headers, timeout=60.0)
            logger.debug(f"Resposta Magento (list_orders): Status {resp.status_code} - Body: {resp.text}")
            if resp.status_code == 401:
                logger.error(f"Erro de autenticação no Magento para empresa {self.id_empresa}: Token inválido.")
                raise HTTPException(status_code=401, detail="Token de acesso Magento inválido.")
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"Erro de conexão Magento para empresa {self.id_empresa}: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Erro na comunicação com Magento: {str(e)}")

        orders = data.get('items', [])

        # --- PRE-PROCESSAMENTO: Verificar status de importação ---
        # Verifica quais pedidos já estão no banco para permitir filtragem
        for order in orders:
            magento_id = order.get('entity_id')
            search_str = f"ID Magento: {magento_id}"
            exists = self.db.query(models.Pedido.id).filter(
                models.Pedido.observacao.contains(search_str),
                models.Pedido.id_empresa == self.id_empresa,
                models.Pedido.situacao != 'cancelado'
            ).first()
            order['ja_importado'] = True if exists else False

        # --- FILTRAGEM GLOBAL POR CONFIGURAÇÃO (NOVO) ---
        if self.config.payment_method_contains:
            term = self.config.payment_method_contains.lower()
            orders = [
                o for o in orders 
                if term in str(o.get('payment', {}).get('method', '')).lower()
            ]

        # --- GERAÇÃO DINÂMICA DE FILTROS ---
        # Extraímos os valores únicos presentes no lote de 200 pedidos para popular o filtro
        unique_statuses = sorted(list(set(o.get('status') for o in orders if o.get('status'))))
        
        pm_map = {} # value -> label
        for o in orders:
            pm_code = o.get('payment', {}).get('method')
            if pm_code:
                # Tenta capitalizar ou formatar o nome do método
                label = pm_code.replace('_', ' ').title()
                pm_map[pm_code] = label
        
        dynamic_filters = [
            {
                "label": "Status", 
                "value": "status", 
                "type": "multiselect", 
                "options": [{"label": s.replace('_', ' ').title(), "value": s} for s in unique_statuses]
            },
            {
                "label": "Método de Pagamento", 
                "value": "payment_method", 
                "type": "multiselect", 
                "options": [{"label": v, "value": k} for k, v in pm_map.items()]
            },
            {
                "label": "Importado", 
                "value": "ja_importado", 
                "type": "multiselect", 
                "options": [{"label": "Importado", "value": "true"}, {"label": "Não Importado", "value": "false"}]
            }
        ]

        # --- FILTRAGEM LOCAL (Evita erro 500 por URL muito longa no Magento) ---
        # Prioriza filtros passados via argumento (do Modal Novo), senão usa os da config (Legado)
        active_filters = []
        # CORREÇÃO: Verifica se filters não é None (pode ser lista vazia [], que deve sobrepor o default)
        if filters is not None:
            # Se vier como string JSON (do endpoint generic), faz parse
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
                    operator = filtro.get('operator', 'equals') # Default para legado
                    value = filtro.get('value', '')
                    
                    order_val_raw = self._extract_field_value(order, field)
                    item_val = str(order_val_raw or "").lower()

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
        
        # Paginação manual no resultado filtrado
        orders = orders[offset : offset + limit]

        formatted_items = []
        for order in orders:
            # Verifica duplicidade via observação
            magento_id = order.get('entity_id')
            increment_id = order.get('increment_id')

            # Formata nome do cliente
            cust_first = order.get('customer_firstname') or order.get('billing_address', {}).get('firstname', '')
            cust_last = order.get('customer_lastname') or order.get('billing_address', {}).get('lastname', '')
            
            payment = order.get('payment', {})
            payment_method = payment.get('method')

            # Copia todos os dados originais do pedido para incluir todas as colunas da API
            item_data = order.copy()
            
            # Adiciona/Sobrescreve com campos calculados/formatados essenciais
            item_data.update({
                "entity_id": magento_id,
                "increment_id": increment_id,
                "payment_method": payment_method,
                "customer_name": f"{cust_first} {cust_last}",
                "items_count": len(order.get('items', [])),
                "ja_importado": order.get('ja_importado', False)
            })
            
            formatted_items.append(item_data)

        return {
            "items": formatted_items,
            "total_count": total_count,
            "extra": {"available_filters": dynamic_filters}
        }

    def _calculate_delivery_date(self, shipping_description: str, created_at_str: str) -> datetime.date:
        """Calcula data de entrega estimada baseada na descrição do frete (Considerando dias úteis)"""
        days = 0
        if shipping_description:
            # Procura por "X dias" ou "X dia"
            match = re.search(r'(\d+)\s*dia', shipping_description, re.IGNORECASE)
            if match:
                days = int(match.group(1))
        
        base_date = datetime.now()
        if created_at_str:
            try:
                base_date = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
            except:
                pass
        
        # Adiciona dias úteis
        current_date = base_date
        while days > 0:
            current_date += timedelta(days=1)
            if current_date.weekday() < 5: # 0-4 = Segunda a Sexta
                days -= 1
                
        return current_date.date()

    def _find_carrier(self, shipping_description: str) -> models.Cadastro:
        """Busca transportadora baseada na descrição do frete (Contém)"""
        if not shipping_description:
            return None
            
        # Limpeza e extração do nome
        # Ex: "Opções de frete - Rodonaves Standard 2 - Em média 8 dias..." -> "Rodonaves Standard 2"
        clean_desc = shipping_description.replace("Opções de frete - ", "")
        parts = clean_desc.split(" - ")
        carrier_name = parts[0].strip()
        
        if not carrier_name:
            return None
            
        # Busca no banco (Nome ou Fantasia CONTÉM o nome extraído)
        carrier = self.db.query(models.Cadastro).filter(
            or_(
                models.Cadastro.nome_razao.ilike(f"%{carrier_name}%"),
                models.Cadastro.fantasia.ilike(f"%{carrier_name}%")
            ),
            models.Cadastro.tipo_cadastro == CadastroTipoCadastroEnum.transportadora,
            models.Cadastro.id_empresa == self.id_empresa
        ).first()
        
        return carrier

    def import_order(self, magento_entity_id: int):
        """Importa um pedido específico pelo entity_id"""
        logger.info(f"Iniciando importação do pedido Magento {magento_entity_id} para empresa {self.id_empresa}")
        
        # 1. Busca detalhes completos do pedido
        url = f"{self.api_base}/orders/{magento_entity_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        logger.debug(f"Enviando requisição GET para {url}")
        resp = requests.get(url, auth=self._get_auth(), headers=headers, timeout=30.0)
        logger.debug(f"Resposta Magento (import_order): Status {resp.status_code} - Body: {resp.text}")
        if resp.status_code != 200:
            logger.error(f"Erro ao buscar pedido {magento_entity_id} no Magento: {resp.status_code} - {resp.text}")
            raise HTTPException(status_code=400, detail="Erro ao buscar pedido no Magento.")
        order_data = resp.json()

        # Verifica duplicidade novamente para segurança
        search_str = f"ID Magento: {magento_entity_id}"
        exists = self.db.query(models.Pedido).filter(
            models.Pedido.observacao.contains(search_str),
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.situacao != 'cancelado'
        ).first()
        if exists:
            logger.info(f"Pedido Magento {magento_entity_id} já foi importado anteriormente para empresa {self.id_empresa}")
            raise HTTPException(status_code=409, detail=f"Pedido {order_data.get('increment_id')} já importado.")

        # 2. Busca ou Cria Cliente
        cliente_erp = self._find_or_create_customer(order_data)

        # 3. Processa Itens
        itens_erp = []
        total_calculado = 0
        total_ipi_global = 0
        produtos_criados = []
        
        logger.debug(f"Processando {len(order_data.get('items', []))} itens do pedido Magento")
        for item in order_data.get('items', []):
            # Magento retorna itens pai (Configurable) e filhos (Simple). 
            # Geralmente importamos o pai ou filho dependendo da lógica.
            # Aqui vamos ignorar itens filhos se o pai já estiver na lista para evitar duplicidade de valor,
            # OU ignorar o pai se quisermos controle de estoque do filho.
            # Lógica simples: Se tem parent_item_id, é um filho.
            
            # Se for um item filho (componente de um configurável), pegamos o preço do pai geralmente.
            # Simplificação: Importar itens que não tem parent_item_id ou tratar tipo 'simple'
            
            # CORREÇÃO: Ignora itens filhos (que possuem parent_item_id) para evitar duplicidade de linhas
            if item.get('parent_item_id'):
                continue
            
            # SKU
            sku = item.get('sku')
            
            # Busca Produto no ERP
            logger.debug(f"Buscando produto com SKU '{sku}' no ERP")
            produto = self.db.query(models.Produto).filter(
                models.Produto.sku == sku,
                models.Produto.id_empresa == self.id_empresa
            ).first()

            if not produto:
                logger.info(f"SKU '{sku}' não encontrado. Criando produto automaticamente para empresa {self.id_empresa}")
                produto = models.Produto(
                    id_empresa=self.id_empresa,
                    sku=sku,
                    descricao=item.get('name', 'Produto Importado')[:255],
                    unidade=models.ProdutoUnidadeEnum.un,
                    tipo_produto=models.ProdutoTipoEnum.mercadoria_revenda,
                    origem=models.ProdutoOrigemEnum.nacional,
                    preco=float(item.get('price', 0)),
                    custo=0,
                    peso=float(item.get('weight', 0)),
                    situacao=True
                )
                self.db.add(produto)
                self.db.commit()
                self.db.refresh(produto)
                produtos_criados.append(sku)

            qtd = int(float(item.get('qty_ordered', 0)))
            preco = float(item.get('price', 0)) 
            
            # Correção para configuráveis: Se preço for 0 e tiver parent, buscar lógica complexa.
            # Assumindo produtos simples para este exemplo básico.
            
            # --- Lógica de IPI e Totais Detalhados ---
            ipi_aliquota = float(produto.ipi_aliquota or 0)
            subtotal = round(qtd * preco, 2)
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
                "valor_unitario": preco,
                "subtotal": subtotal,
                "peso_unitario": float(produto.peso or 0),
                "ipi_aliquota": ipi_aliquota,
                "valor_ipi": valor_ipi,
                "total_com_ipi": total_com_ipi
            })
            total_calculado += qtd * preco

        logger.debug(f"Total calculado dos itens: {total_calculado}")
        
        # --- Extração de Frete e Transportadora ---
        shipping_amount = float(order_data.get('base_shipping_amount', 0))
        shipping_desc = order_data.get('shipping_description', '')
        data_entrega = self._calculate_delivery_date(shipping_desc, order_data.get('created_at'))
        transportadora = self._find_carrier(shipping_desc)
        id_transportadora = transportadora.id_sequencial if transportadora else None
        
        carrier_warning = None
        if shipping_desc and not transportadora:
             clean_desc = shipping_desc.replace("Opções de frete - ", "")
             parts = clean_desc.split(" - ")
             carrier_name = parts[0].strip()
             if carrier_name:
                 carrier_warning = f"Transportadora '{carrier_name}' não encontrada. Campo deixado vazio."

        # --- Extrair Endereço de Entrega (Shipping) ---
        shipping_address = {}
        extension_attributes = order_data.get('extension_attributes', {})
        shipping_assignments = extension_attributes.get('shipping_assignments', [])
        if shipping_assignments:
            shipping_address = shipping_assignments[0].get('shipping', {}).get('address', {})
        else:
            shipping_address = order_data.get('billing_address', {}) # Fallback

        street_lines = shipping_address.get('street', [])
        rua = street_lines[0] if len(street_lines) > 0 else ''
        numero = street_lines[1] if len(street_lines) > 1 else 'S/N'
        complemento = ''
        bairro = ''
        if len(street_lines) >= 4:
            complemento = street_lines[2]
            bairro = street_lines[3]
        elif len(street_lines) == 3:
            bairro = street_lines[2]
        else:
            bairro = street_lines[2] if len(street_lines) > 2 else ''

        # 4. Cria Pedido
        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=cliente_erp.id_sequencial,
            id_vendedor=self.config.vendedor_padrao_id,
            situacao=self.config.situacao_pedido_inicial,
            data_orcamento=datetime.now(),
            data_validade=datetime.now(),
            data_entrega=data_entrega,
            origem_venda="Magento Ecommerce",
            total=order_data.get('grand_total'), # Usa total do Magento (inclui frete/taxas)
            valor_frete=shipping_amount,
            modalidade_frete=PedidoModalidadeFreteEnum.cif,
            id_transportadora=id_transportadora,
            
            # --- ENDEREÇO DE ENTREGA IMPORTADO DO MAGENTO ---
            endereco_cep="".join(filter(str.isdigit, str(shipping_address.get('postcode') or '')))[:9],
            endereco_logradouro=rua,
            endereco_numero=numero,
            endereco_complemento=complemento,
            endereco_bairro=bairro,
            endereco_cidade=shipping_address.get('city'),
            endereco_estado=shipping_address.get('region_code'),
            
            itens=itens_erp,
            observacao=f"Pedido importado do Magento. ID Magento: {magento_entity_id}. Increment ID: {order_data.get('increment_id')}"
        )

        logger.info(f"Salvando pedido Magento {magento_entity_id} no ERP para empresa {self.id_empresa}")
        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)
        
        logger.info(f"Pedido Magento {magento_entity_id} importado com sucesso. ID ERP: {novo_pedido.id}")
        
        if carrier_warning:
            setattr(novo_pedido, 'import_warning', carrier_warning)
            
        return novo_pedido, produtos_criados

    def _find_or_create_customer(self, order_data: dict) -> models.Cadastro:
        """Busca cliente por email ou CPF (taxvat) usando dados do endereço de COBRANÇA (billing_address)"""
        logger.info(f"Buscando ou criando cliente para o pedido Magento {order_data.get('increment_id')}")

        # --- DADOS DO CLIENTE: USA BILLING_ADDRESS (COBRANÇA) COMO FONTE PRINCIPAL ---
        billing = order_data.get('billing_address', {})

        email = order_data.get('customer_email') or billing.get('email')
        taxvat = order_data.get('customer_taxvat') or billing.get('vat_id')

        # Tenta buscar por CPF/CNPJ se existir
        cliente = None
        if taxvat:
            # Remove pontuação
            clean_doc = "".join(c for c in taxvat if c.isalnum()).upper()
            cliente = self.db.query(models.Cadastro).filter(
                models.Cadastro.cpf_cnpj == clean_doc,
                models.Cadastro.id_empresa == self.id_empresa
            ).first()
        
        # Se não achou, tenta por email
        if not cliente and email:
             cliente = self.db.query(models.Cadastro).filter(
                models.Cadastro.email == email,
                models.Cadastro.id_empresa == self.id_empresa
            ).first()

        if cliente:
            logger.info(f"Cliente {taxvat or email} já existe no ERP para empresa {self.id_empresa}")
            return cliente

        # Cria novo cliente com dados do billing_address (cobrança)
        logger.info(f"Criando novo cliente {taxvat or email} para empresa {self.id_empresa}")
        street_lines = billing.get('street', [])
        rua = street_lines[0] if len(street_lines) > 0 else ''
        numero = street_lines[1] if len(street_lines) > 1 else 'S/N'
        
        # Mapeamento de endereço (Padrão 4 linhas: Rua, Numero, Complemento, Bairro)
        complemento = ''
        bairro = ''
        if len(street_lines) >= 4:
            complemento = street_lines[2]
            bairro = street_lines[3]
        elif len(street_lines) == 3:
            bairro = street_lines[2]
        else:
            bairro = street_lines[2] if len(street_lines) > 2 else ''

        clean_doc_create = "".join(c for c in taxvat if c.isalnum()).upper() if taxvat else '00000000000'
        novo_cliente = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj=clean_doc_create,
            nome_razao=f"{billing.get('firstname', '')} {billing.get('lastname', '')}".strip().upper(),
            tipo_cadastro=CadastroTipoCadastroEnum.cliente,
            tipo_pessoa=CadastroTipoPessoaEnum.juridica if len(clean_doc_create) > 11 else CadastroTipoPessoaEnum.fisica,
            email=email,
            telefone="".join(filter(str.isdigit, str(billing.get('telephone') or '')))[:20],
            cep="".join(filter(str.isdigit, str(billing.get('postcode') or '')))[:9],
            estado=billing.get('region_code'),
            cidade=billing.get('city'),
            logradouro=rua,
            numero=numero,
            complemento=complemento,
            bairro=bairro,
            situacao=True
        )
        self.db.add(novo_cliente)
        self.db.commit()
        self.db.refresh(novo_cliente)
        logger.info(f"Novo cliente criado com ID ERP: {novo_cliente.id}")
        return novo_cliente

    def update_magento_order_status(self, pedido):
        """
        Atualiza a situação do pedido no Magento com base na mudança de status do ERP.
        """
        # Extrai o ID do Magento da observação do pedido
        observacao = pedido.observacao or ""
        match = re.search(r"ID Magento:\s*(\d+)", observacao)
        if not match:
            logger.info(f"Nenhum ID do Magento encontrado na observação do pedido ERP #{pedido.id}")
            return False
        magento_entity_id = int(match.group(1))

        # Obter o valor da situação do ERP
        erp_status = pedido.situacao.value if hasattr(pedido.situacao, 'value') else str(pedido.situacao)
        erp_status_lower = erp_status.lower()

        # Mapeamento do status do ERP para o status do Magento
        status_mapping = {
            "orcamento": "pending",
            "orçamento": "pending",
            "aprovacao": "processing",
            "aprovação": "processing",
            "programacao": "processing",
            "programação": "processing",
            "producao": "em_producao",
            "produção": "em_producao",
            "embalagem": "processing",
            "faturamento": "processing",
            "expedicao": "processing",
            "expedição": "processing",
            "despachado": "complete",
            "cancelado": "canceled"
        }

        new_magento_status = status_mapping.get(erp_status_lower)
        if not new_magento_status:
            logger.info(f"Nenhum status correspondente no Magento para o status ERP '{erp_status}'. Sincronização ignorada.")
            return False

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            if new_magento_status == "canceled":
                url = f"{self.api_base}/orders/{magento_entity_id}/cancel"
                logger.info(f"Cancelando pedido Magento {magento_entity_id} via API")
                resp = requests.post(url, auth=self._get_auth(), json={}, headers=headers, timeout=30.0)
            else:
                url = f"{self.api_base}/orders/{magento_entity_id}/comments"
                payload = {
                    "statusHistory": {
                        "status": new_magento_status,
                        "comment": f"Status atualizado pelo ERP para {erp_status}.",
                        "is_customer_notified": 0,
                        "is_visible_on_front": 0
                    }
                }
                logger.info(f"Atualizando status do pedido Magento {magento_entity_id} para {new_magento_status} via API")
                resp = requests.post(url, auth=self._get_auth(), json=payload, headers=headers, timeout=30.0)

            logger.info(f"Resposta Magento para pedido {magento_entity_id}: Status {resp.status_code} - {resp.text[:200]}")
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar status do pedido Magento {magento_entity_id}: {e}")
            raise e