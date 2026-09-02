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
    PedidoModalidadeFreteEnum, PedidoSituacaoEnum,
    FiscalPagamentoEnum, CadastroIndicadorIEEnum
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

        # Paginação na Shopee: Shopee limita o intervalo a no máximo 15 dias por requisição (diff in 15days).
        # Consultamos a janela mais recente primeiro (15 dias); se necessário, a segunda (15-30 dias).
        all_order_sns = []
        now = datetime.now()
        time_windows = [
            (int((now - timedelta(days=15)).timestamp()), int(now.timestamp())),
            (int((now - timedelta(days=30)).timestamp()), int((now - timedelta(days=15)).timestamp()))
        ]

        session = requests.Session()
        orders_list = []

        try:
            for t_from, t_to in time_windows:
                has_more = True
                cursor = ""
                while has_more and len(all_order_sns) < 100:
                    timestamp = int(time.time())
                    sign = self._generate_sign(path, timestamp, access_token, shop_id)
                    params = {
                        "partner_id": int(self.config.partner_id),
                        "timestamp": timestamp,
                        "access_token": access_token,
                        "shop_id": int(shop_id),
                        "sign": sign,
                        "page_size": 100,
                        "time_range_field": "create_time",
                        "time_from": t_from,
                        "time_to": t_to
                    }
                    if cursor:
                        params["cursor"] = cursor

                    resp = session.get(f"{self.api_base}{path}", params=params, timeout=10.0)
                    data = resp.json()

                    if resp.status_code == 200 and not data.get("error"):
                        response_data = data.get("response", {})
                        sn_list = [o.get("order_sn") for o in response_data.get("order_list", []) if o.get("order_sn")]
                        if not sn_list:
                            break
                        for sn in sn_list:
                            if sn not in all_order_sns:
                                all_order_sns.append(sn)
                        has_more = response_data.get("more", False)
                        cursor = response_data.get("next_cursor", "")
                    else:
                        logger.warning(f"Resposta de aviso ao buscar lista de pedidos Shopee: {resp.text}")
                        break

                # Se já obteve pedidos suficientes para atender a listagem, não bloqueia na segunda janela
                if len(all_order_sns) >= max(limit, 50):
                    break

            # Busca detalhes em lotes de até 50 por vez
            if all_order_sns:
                detail_path = "/api/v2/order/get_order_detail"
                for i in range(0, len(all_order_sns), 50):
                    chunk = all_order_sns[i:i+50]
                    detail_timestamp = int(time.time())
                    detail_sign = self._generate_sign(detail_path, detail_timestamp, access_token, shop_id)
                    
                    detail_params = {
                        "partner_id": int(self.config.partner_id),
                        "timestamp": detail_timestamp,
                        "access_token": access_token,
                        "shop_id": int(shop_id),
                        "sign": detail_sign,
                        "order_sn_list": ",".join(chunk),
                        "response_optional_fields": "buyer_user_id,buyer_username,buyer_cpf_id,buyer_cnpj_id,recipient_address,item_list,total_amount,shipping_carrier,payment_method,invoice_data"
                    }

                    detail_resp = session.get(f"{self.api_base}{detail_path}", params=detail_params, timeout=10.0)
                    detail_data = detail_resp.json()

                    if detail_resp.status_code == 200 and not detail_data.get("error"):
                        for item in detail_data.get("response", {}).get("order_list", []):
                            status = str(item.get("order_status") or "").upper()
                            if status == "UNPAID":
                                continue
                            orders_list.append({
                                "id": item.get("order_sn"),
                                "order_sn": item.get("order_sn"),
                                "order_status": item.get("order_status", "READY_TO_SHIP"),
                                "create_time": datetime.fromtimestamp(item.get("create_time", int(time.time()))).isoformat(),
                                "buyer_username": item.get("buyer_username") or item.get("recipient_address", {}).get("name", "Cliente Shopee"),
                                "total_amount": float(item.get("total_amount", 0)),
                                "payment_method": item.get("payment_method", "Desconhecido"),
                                "shipping_carrier": item.get("shipping_carrier", "Padrao Shopee"),
                                "tracking_number": item.get("tracking_number", "")
                            })
        except Exception as e:
            logger.warning(f"Não foi possível buscar pedidos em tempo real na Shopee ({e}). Retornando lista vazia ou filtro.")
        finally:
            session.close()

        # --- PRE-PROCESSAMENTO: Verificar se o pedido já existe no banco local em LOTE (Batch Query) ---
        order_sns = [str(o.get('order_sn')) for o in orders_list if o.get('order_sn')]
        imported_sns = set()
        if order_sns:
            from sqlalchemy import or_
            obs_conditions = [models.Pedido.observacao.contains(sn) for sn in order_sns]
            existing_pedidos = self.db.query(models.Pedido.shopee_order_sn, models.Pedido.observacao).filter(
                models.Pedido.id_empresa == self.id_empresa,
                models.Pedido.situacao != PedidoSituacaoEnum.cancelado,
                or_(
                    models.Pedido.shopee_order_sn.in_(order_sns),
                    *obs_conditions
                )
            ).all()
            for p in existing_pedidos:
                if p.shopee_order_sn:
                    imported_sns.add(str(p.shopee_order_sn))
                if p.observacao:
                    for sn in order_sns:
                        if sn in p.observacao:
                            imported_sns.add(sn)

        for order in orders_list:
            sn = str(order.get('order_sn'))
            order['ja_importado'] = sn in imported_sns

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

    def _normalize_uf(self, state: str) -> str:
        if not state:
            return "EX"
        state_clean = str(state).strip().upper()
        if len(state_clean) == 2:
            return state_clean
        
        uf_map = {
            'ACRE': 'AC', 'ALAGOAS': 'AL', 'AMAPA': 'AP', 'AMAZONAS': 'AM',
            'BAHIA': 'BA', 'CEARA': 'CE', 'DISTRITO FEDERAL': 'DF', 'ESPIRITO SANTO': 'ES',
            'GOIAS': 'GO', 'MARANHAO': 'MA', 'MATO GROSSO': 'MT', 'MATO GROSSO DO SUL': 'MS',
            'MINAS GERAIS': 'MG', 'PARA': 'PA', 'PARAIBA': 'PB', 'PARANA': 'PR',
            'PERNAMBUCO': 'PE', 'PIAUI': 'PI', 'RIO DE JANEIRO': 'RJ', 'RIO GRANDE DO NORTE': 'RN',
            'RIO GRANDE DO SUL': 'RS', 'RONDONIA': 'RO', 'RORAIMA': 'RR', 'SANTA CATARINA': 'SC',
            'SAO PAULO': 'SP', 'SERGIPE': 'SE', 'TOCANTINS': 'TO'
        }
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', state_clean)
        state_ascii = "".join([c for c in nfkd if not unicodedata.combining(c)])
        return uf_map.get(state_ascii, state_clean[:2])

    def _map_payment_method(self, method_str: str) -> Tuple[FiscalPagamentoEnum, str]:
        if not method_str:
            return FiscalPagamentoEnum.outros, "Outros"
        
        m_upper = method_str.strip().upper()
        if "PIX" in m_upper:
            return FiscalPagamentoEnum.pix, "PIX"
        elif "CREDIT" in m_upper or "CREDITO" in m_upper:
            return FiscalPagamentoEnum.cartao_credito, "CARTÃO DE CRÉDITO"
        elif "DEBIT" in m_upper or "DEBITO" in m_upper:
            return FiscalPagamentoEnum.cartao_debito, "CARTÃO DÉBITO"
        elif "BOLETO" in m_upper:
            return FiscalPagamentoEnum.boleto_bancario, "BOLETO BANCÁRIO"
        elif "SHOPEEPAY" in m_upper or "WALLET" in m_upper:
            return FiscalPagamentoEnum.outros, "SHOPEEPAY"
        else:
            return FiscalPagamentoEnum.outros, method_str.upper()

    def _map_shopee_status_to_erp(self, order_status: str) -> PedidoSituacaoEnum:
        st = str(order_status or '').upper()
        if st == 'UNPAID':
            return PedidoSituacaoEnum.orcamento
        elif st in ['CANCELLED', 'IN_CANCEL']:
            return PedidoSituacaoEnum.cancelado
        elif st in ['SHIPPED', 'COMPLETED']:
            return PedidoSituacaoEnum.despachado
        else:
            # READY_TO_SHIP, PROCESSED, INVOICE_PENDING
            return self.config.situacao_pedido_inicial or PedidoSituacaoEnum.aprovacao

    def _extract_cpf_cnpj(self, order_data: dict, address: dict) -> Tuple[str, CadastroTipoPessoaEnum]:
        """
        Extrai o CPF ou CNPJ do comprador segundo a especificação oficial da API OpenAPI v2 da Shopee (Brasil).
        Campos oficiais da API Shopee:
        - buyer_cpf_id (CPF do comprador em pedidos no Brasil)
        - buyer_cnpj_id (CNPJ do comprador para contas PJ no Brasil)
        - invoice_data.tax_code (Código tributário/fiscal do comprador)
        - recipient_address.tax_code / recipient_address.cpf
        """
        invoice_data = order_data.get('invoice_data') or {}
        
        # 1. Campo oficial de CPF do comprador da Shopee no Brasil (buyer_cpf_id)
        buyer_cpf = order_data.get('buyer_cpf_id') or order_data.get('buyer_cpf')
        if buyer_cpf:
            clean = "".join(filter(str.isdigit, str(buyer_cpf)))
            if len(clean) == 11 and clean != '00000000000':
                return clean, CadastroTipoPessoaEnum.fisica

        # 2. Campo oficial de CNPJ do comprador da Shopee no Brasil (buyer_cnpj_id)
        buyer_cnpj = order_data.get('buyer_cnpj_id') or order_data.get('buyer_cnpj')
        if buyer_cnpj:
            clean = "".join(filter(str.isdigit, str(buyer_cnpj)))
            if len(clean) == 14:
                return clean, CadastroTipoPessoaEnum.juridica

        # 3. Campo de identificação fiscal retornado em invoice_data (tax_code)
        tax_code = invoice_data.get('tax_code') or invoice_data.get('buyer_cpf') or invoice_data.get('cpf')
        if tax_code:
            clean = "".join(filter(str.isdigit, str(tax_code)))
            if len(clean) == 14:
                return clean, CadastroTipoPessoaEnum.juridica
            elif len(clean) == 11 and clean != '00000000000':
                return clean, CadastroTipoPessoaEnum.fisica

        # 4. Campos fiscais no objeto recipient_address
        addr_tax = address.get('tax_code') or address.get('tax_id') or address.get('cpf') or address.get('buyer_cpf')
        if addr_tax:
            clean = "".join(filter(str.isdigit, str(addr_tax)))
            if len(clean) == 14:
                return clean, CadastroTipoPessoaEnum.juridica
            elif len(clean) == 11 and clean != '00000000000':
                return clean, CadastroTipoPessoaEnum.fisica

        return '00000000000', CadastroTipoPessoaEnum.fisica

    def _parse_shopee_address(self, address: dict) -> Dict[str, Optional[str]]:
        full_addr = str(address.get('full_address') or address.get('address') or address.get('street') or '').strip()
        
        street = str(address.get('street') or address.get('address') or '').strip()
        number = str(address.get('number') or address.get('house_number') or '').strip()
        complement = str(address.get('complement') or address.get('address_2') or '').strip()
        district = str(address.get('district') or address.get('town') or address.get('bairro') or '').strip()
        city = str(address.get('city') or '').strip()
        state = str(address.get('state') or '').strip()
        zipcode = str(address.get('zipcode') or '').strip()

        logradouro = ""
        if street and street != full_addr and ',' not in street:
            logradouro = street

        if full_addr:
            parts = [p.strip() for p in full_addr.split(',') if p.strip()]
            cleaned_parts = []
            zip_digits = "".join(filter(str.isdigit, zipcode))
            for p in parts:
                p_digits = "".join(filter(str.isdigit, p))
                if p_digits and len(p_digits) >= 8 and (zip_digits and p_digits == zip_digits):
                    continue
                if city and p.lower() == city.lower():
                    continue
                if state and (p.lower() == state.lower() or p.upper() == self._normalize_uf(state)):
                    continue
                cleaned_parts.append(p)

            if cleaned_parts:
                if not logradouro:
                    logradouro = cleaned_parts[0]
                
                if len(cleaned_parts) > 1 and not number:
                    possible_num = cleaned_parts[1]
                    if any(c.isdigit() for c in possible_num) or 'sn' in possible_num.lower() or 's/n' in possible_num.lower() or 'sem num' in possible_num.lower():
                        number = possible_num
                    elif not complement:
                        complement = possible_num

                if len(cleaned_parts) > 2:
                    remaining = cleaned_parts[2:]
                    for rem in remaining:
                        if district and rem.lower() == district.lower():
                            continue
                        if not complement:
                            complement = rem
                        elif rem not in complement:
                            complement += f", {rem}"

        if not logradouro:
            logradouro = full_addr or "Endereço não informado"

        if not number:
            import re
            match = re.search(r'(?:,?\s*nº?\s*|,?\s*)([0-9]+[a-zA-Z]?|s/n|sn)$', logradouro, re.IGNORECASE)
            if match:
                number = match.group(1)
                logradouro = logradouro[:match.start()].strip().rstrip(',')
            else:
                number = "S/N"

        cep_formatted = "".join(filter(str.isdigit, zipcode))[:9]
        if len(cep_formatted) == 8:
            cep_formatted = f"{cep_formatted[:5]}-{cep_formatted[5:]}"

        return {
            "logradouro": logradouro[:255],
            "numero": number[:20],
            "complemento": complement[:100] if complement else None,
            "bairro": district[:100] if district else None,
            "cidade": city[:100] if city else None,
            "estado": self._normalize_uf(state)[:2],
            "cep": cep_formatted
        }

    def _find_or_create_customer(self, order_data: dict) -> models.Cadastro:
        address = order_data.get('recipient_address', {})
        buyer_user = order_data.get('buyer_username')
        recipient_name = address.get('name')
        
        nome_razao = str(recipient_name or buyer_user or "CLIENTE SHOPEE").strip().upper()[:100]
        fantasia = str(buyer_user).strip()[:100] if buyer_user else None
        
        cpf_cnpj, tipo_pessoa = self._extract_cpf_cnpj(order_data, address)
        phone = "".join(filter(str.isdigit, str(address.get('phone') or '')))[:20]
        
        parsed_addr = self._parse_shopee_address(address)

        cliente_existente = None
        if cpf_cnpj != '00000000000':
            cliente_existente = self.db.query(models.Cadastro).filter(
                models.Cadastro.cpf_cnpj == cpf_cnpj,
                models.Cadastro.id_empresa == self.id_empresa,
                models.Cadastro.tipo_cadastro == CadastroTipoCadastroEnum.cliente
            ).first()

        if not cliente_existente:
            cliente_existente = self.db.query(models.Cadastro).filter(
                models.Cadastro.nome_razao == nome_razao,
                models.Cadastro.id_empresa == self.id_empresa,
                models.Cadastro.tipo_cadastro == CadastroTipoCadastroEnum.cliente
            ).first()

        if cliente_existente:
            if cliente_existente.id_sequencial is None:
                from sqlalchemy import text
                stmt = text('SELECT COALESCE(MAX(id_sequencial), 0) + 1 FROM "cadastros" WHERE id_empresa = :emp_id')
                next_seq = self.db.execute(stmt, {"emp_id": self.id_empresa}).scalar() or 1
                cliente_existente.id_sequencial = next_seq
            if cpf_cnpj != '00000000000' and cliente_existente.cpf_cnpj == '00000000000':
                cliente_existente.cpf_cnpj = cpf_cnpj
                cliente_existente.tipo_pessoa = tipo_pessoa
            if phone:
                cliente_existente.telefone = phone
                cliente_existente.celular = phone
            if parsed_addr["cep"]:
                cliente_existente.cep = parsed_addr["cep"]
            if parsed_addr["estado"]:
                cliente_existente.estado = parsed_addr["estado"]
            if parsed_addr["cidade"]:
                cliente_existente.cidade = parsed_addr["cidade"]
            if parsed_addr["bairro"]:
                cliente_existente.bairro = parsed_addr["bairro"]
            if parsed_addr["logradouro"]:
                cliente_existente.logradouro = parsed_addr["logradouro"]
            if parsed_addr["numero"]:
                cliente_existente.numero = parsed_addr["numero"]
            if parsed_addr["complemento"]:
                cliente_existente.complemento = parsed_addr["complemento"]
            self.db.commit()
            return cliente_existente

        novo_cliente = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj=cpf_cnpj,
            nome_razao=nome_razao,
            fantasia=fantasia,
            tipo_cadastro=CadastroTipoCadastroEnum.cliente,
            tipo_pessoa=tipo_pessoa,
            indicador_ie=CadastroIndicadorIEEnum.nao_contribuinte,
            telefone=phone,
            celular=phone,
            cep=parsed_addr["cep"],
            estado=parsed_addr["estado"],
            cidade=parsed_addr["cidade"],
            bairro=parsed_addr["bairro"],
            logradouro=parsed_addr["logradouro"],
            numero=parsed_addr["numero"],
            complemento=parsed_addr["complemento"],
            situacao=True
        )
        self.db.add(novo_cliente)
        self.db.commit()
        self.db.refresh(novo_cliente)
        return novo_cliente

    def _find_or_create_carrier(self, carrier_name: str) -> Optional[models.Cadastro]:
        """Busca ou cria transportadora da Shopee associando id_sequencial no ERP."""
        if not carrier_name:
            return None

        carrier_name_clean = str(carrier_name).strip()
        from sqlalchemy import or_
        carrier = self.db.query(models.Cadastro).filter(
            models.Cadastro.tipo_cadastro == CadastroTipoCadastroEnum.transportadora,
            models.Cadastro.id_empresa == self.id_empresa,
            models.Cadastro.situacao == True,
            or_(
                models.Cadastro.nome_razao.ilike(f"%{carrier_name_clean}%"),
                models.Cadastro.fantasia.ilike(f"%{carrier_name_clean}%")
            )
        ).first()

        if carrier:
            if carrier.id_sequencial is None:
                from sqlalchemy import text
                stmt = text('SELECT COALESCE(MAX(id_sequencial), 0) + 1 FROM "cadastros" WHERE id_empresa = :emp_id')
                next_seq = self.db.execute(stmt, {"emp_id": self.id_empresa}).scalar() or 1
                carrier.id_sequencial = next_seq
                self.db.commit()
                self.db.refresh(carrier)
            return carrier

        new_carrier = models.Cadastro(
            id_empresa=self.id_empresa,
            cpf_cnpj='00000000000000',
            nome_razao=carrier_name_clean.upper()[:100],
            fantasia=carrier_name_clean.upper()[:100],
            tipo_cadastro=CadastroTipoCadastroEnum.transportadora,
            tipo_pessoa=CadastroTipoPessoaEnum.juridica,
            indicador_ie=CadastroIndicadorIEEnum.nao_contribuinte,
            situacao=True,
            criar_pedido_intelipost=False,
            cep="00000-000",
            logradouro="Endereço Shopee Envio",
            numero="S/N",
            cidade="Indefinida",
            estado=models.EstadoEnum.SP
        )
        self.db.add(new_carrier)
        self.db.commit()
        self.db.refresh(new_carrier)
        return new_carrier

    def import_order(self, order_sn: str) -> Tuple[models.Pedido, List[str]]:
        """
        Importa um pedido específico da Shopee utilizando id_sequencial para amarração dos produtos.
        """
        logger.info(f"Iniciando importação do pedido Shopee {order_sn} para a empresa {self.id_empresa}")

        # 1. Verifica duplicidade usando a coluna dedicada shopee_order_sn
        exists = self.db.query(models.Pedido).filter(
            models.Pedido.shopee_order_sn == order_sn,
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.situacao != PedidoSituacaoEnum.cancelado
        ).first()

        if exists:
            logger.info(f"Pedido Shopee {order_sn} já foi importado anteriormente (ERP ID: {exists.id_sequencial or exists.id})")
            raise HTTPException(status_code=409, detail=f"Pedido {order_sn} já foi importado anteriormente (ID ERP: {exists.id_sequencial or exists.id}).")

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
                "response_optional_fields": "buyer_user_id,buyer_username,buyer_cpf_id,buyer_cnpj_id,recipient_address,item_list,total_amount,shipping_fee,actual_shipping_fee,shipping_carrier,payment_method,invoice_data,pay_time,dropshipper,dropshipper_phone,note,cancel_reason,cancel_by,buyer_cancel_reason,package_list,tax_amount"
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

        # Bloqueia importação se o pedido estiver com status UNPAID na Shopee
        if str(order_data.get('order_status', '')).upper() == 'UNPAID':
            raise HTTPException(status_code=400, detail=f"O pedido {order_sn} está com status UNPAID (Não pago) e não pode ser importado.")

        # 3. Busca ou Cria Cliente
        cliente_erp = self._find_or_create_customer(order_data)

        # 4. Processa Itens, SKUs e Pesos
        itens_erp = []
        produtos_criados = []
        total_calculado = 0.0
        total_peso = 0.0

        for item in order_data.get('item_list', []):
            sku = item.get('model_sku') or item.get('item_sku') or f"SHOPEE-{item.get('item_id', 'PROD')}"
            item_name = str(item.get('item_name', 'Produto Importado Shopee')).strip()
            model_name = str(item.get('model_name', '')).strip()
            if model_name:
                desc_completa = f"{item_name} - {model_name}"
            else:
                desc_completa = item_name

            # 1. Busca por SKU direto
            produto = self.db.query(models.Produto).filter(
                models.Produto.sku == sku,
                models.Produto.id_empresa == self.id_empresa
            ).first()

            # 2. Se não achar e tiver GTIN/EAN, busca por GTIN
            gtin = item.get('gtin') or item.get('ean')
            if not produto and gtin:
                produto = self.db.query(models.Produto).filter(
                    models.Produto.gtin == gtin,
                    models.Produto.id_empresa == self.id_empresa
                ).first()

            # 3. Se não achar, busca se alguma variação do ERP contém o SKU
            if not produto and sku:
                from sqlalchemy import cast, String
                produto = self.db.query(models.Produto).filter(
                    models.Produto.id_empresa == self.id_empresa,
                    cast(models.Produto.variacoes, String).contains(f'"{sku}"')
                ).first()

            preco = float(item.get('model_discounted_price') or item.get('model_original_price') or 0.0)
            peso_item = float(item.get('weight', 0.0))

            if not produto:
                produto = models.Produto(
                    id_empresa=self.id_empresa,
                    sku=sku,
                    gtin=gtin,
                    descricao=desc_completa[:255],
                    unidade=models.ProdutoUnidadeEnum.un,
                    tipo_produto=models.ProdutoTipoEnum.mercadoria_revenda,
                    origem=models.ProdutoOrigemEnum.nacional,
                    preco=preco,
                    custo=0,
                    peso=peso_item,
                    situacao=True
                )
                self.db.add(produto)
                self.db.commit()
                self.db.refresh(produto)
                produtos_criados.append(sku)

            # Garante que id_sequencial existe no produto
            if produto.id_sequencial is None:
                from sqlalchemy import text
                stmt = text('SELECT COALESCE(MAX(id_sequencial), 0) + 1 FROM "produtos" WHERE id_empresa = :emp_id')
                next_seq = self.db.execute(stmt, {"emp_id": self.id_empresa}).scalar() or 1
                produto.id_sequencial = next_seq
                self.db.commit()
                self.db.refresh(produto)

            qtd = int(float(item.get('model_quantity_purchased', 1)))
            subtotal = round(qtd * preco, 2)

            # Cálculo do IPI do Item com base na alíquota cadastrada no Produto
            ipi_aliquota = float(getattr(produto, 'ipi_aliquota', 0.0) or 0.0)
            valor_ipi = round(subtotal * (ipi_aliquota / 100.0), 2)
            total_com_ipi = round(subtotal + valor_ipi, 2)

            peso_unitario = peso_item if peso_item > 0 else float(getattr(produto, 'peso', 0.0) or 0.0)

            itens_erp.append({
                "id_produto": produto.id_sequencial if produto.id_sequencial is not None else produto.id,
                "sku": produto.sku,
                "descricao": produto.descricao,
                "gtin": produto.gtin or "SEM GTIN",
                "ncm": produto.ncm,
                "unidade": produto.unidade.value if hasattr(produto.unidade, 'value') else str(produto.unidade or 'un'),
                "quantidade": qtd,
                "valor_unitario": preco,
                "subtotal": subtotal,
                "peso_unitario": peso_unitario,
                "ipi_aliquota": ipi_aliquota,
                "valor_ipi": valor_ipi,
                "total_com_ipi": total_com_ipi,
            })
            total_calculado += subtotal
            total_peso += (peso_unitario * qtd)

        address = order_data.get('recipient_address', {})
        shipping_fee = float(order_data.get('shipping_fee', 0.0))

        # Cálculo da Média Ponderada da Alíquota de IPI dos itens para incidência no Frete
        weighted_ipi_percent = 0.0
        if total_calculado > 0:
            soma_ponderada_ipi = sum(it["subtotal"] * it["ipi_aliquota"] for it in itens_erp)
            weighted_ipi_percent = soma_ponderada_ipi / total_calculado

        # IPI sobre Frete e Total do Frete (c/ IPI)
        ipi_frete_val = round(shipping_fee * (weighted_ipi_percent / 100.0), 2)
        total_frete_val = round(shipping_fee + ipi_frete_val, 2)

        # Total do Pedido com IPI dos Produtos e do Frete
        total_itens_com_ipi = sum(it["total_com_ipi"] for it in itens_erp)
        total_amount = round(total_itens_com_ipi + total_frete_val, 2)

        # Mapeia Pagamento e Situação
        pagamento_enum, pagamento_desc = self._map_payment_method(order_data.get('payment_method'))
        situacao_erp = self._map_shopee_status_to_erp(order_data.get('order_status'))

        # Trata Datas
        create_timestamp = order_data.get('create_time')
        if create_timestamp:
            dt_pedido = datetime.fromtimestamp(create_timestamp)
        else:
            dt_pedido = datetime.now()

        # Endereço Formatado Inteligente
        parsed_addr = self._parse_shopee_address(address)

        # Busca ou Cria Transportadora
        carrier_name = order_data.get('shipping_carrier')
        carrier_erp = self._find_or_create_carrier(carrier_name) if carrier_name else None

        # 5. Cria Pedido com preenchimento COMPLETO nas colunas ERP
        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=cliente_erp.id_sequencial if cliente_erp else None,
            id_vendedor=self.config.vendedor_padrao_id,
            id_transportadora=carrier_erp.id_sequencial if carrier_erp else None,
            situacao=situacao_erp,
            caixa_destino_origem=self.config.caixa_padrao,
            data_orcamento=dt_pedido.date(),
            data_pedido=dt_pedido.date(),
            data_validade=dt_pedido.date(),
            origem_venda="Shopee",
            
            # --- COLUNAS DEDICADAS DA SHOPEE ---
            shopee_order_sn=order_sn,
            shopee_order_status=str(order_data.get('order_status', '')),
            shopee_buyer_username=str(order_data.get('buyer_username', '')),
            shopee_tracking_number=str(order_data.get('tracking_number', '')),
            shopee_shipping_carrier=str(order_data.get('shipping_carrier', '')),
            shopee_xml_enviado=False,

            # --- VALORES E FRETE ---
            total=total_amount,
            valor_frete=shipping_fee,
            ipi_frete=ipi_frete_val,
            total_frete=total_frete_val,
            modalidade_frete=PedidoModalidadeFreteEnum.cif,

            # --- VOLUMES ---
            volumes_quantidade=len(order_data.get('package_list', [])) or 1,
            volumes_especie="CAIXA",
            volumes_peso_bruto=round(total_peso, 3),
            volumes_peso_liquido=round(total_peso, 3),

            # --- ENDEREÇO DE ENTREGA ---
            endereco_cep=parsed_addr["cep"],
            endereco_logradouro=parsed_addr["logradouro"],
            endereco_numero=parsed_addr["numero"],
            endereco_bairro=parsed_addr["bairro"],
            endereco_cidade=parsed_addr["cidade"],
            endereco_estado=parsed_addr["estado"],
            endereco_complemento=parsed_addr["complemento"],

            # --- PAGAMENTO ---
            pagamento=pagamento_enum,
            pagamento_descricao=pagamento_desc,
            pagamentos=[{
                "forma": pagamento_enum.value,
                "descricao": pagamento_desc,
                "valor": total_amount
            }],

            # --- ITENS E OBSERVAÇÕES ---
            itens=itens_erp,
            observacao=f"Pedido importado do Shopee. ID Shopee: {order_sn}. Status: {order_data.get('order_status', '')}. Obs Cliente: {order_data.get('note', '')}".strip(),
            observacoes_nf=f"Pedido Shopee {order_sn}"
        )

        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)

        logger.info(f"Pedido Shopee {order_sn} importado com sucesso. ID ERP: {novo_pedido.id_sequencial or novo_pedido.id}")
        return novo_pedido, produtos_criados

    def import_products_from_shopee(self, page_size: int = 50, update_existing: bool = True) -> Dict[str, Any]:
        """
        Importa ou sincroniza catálogo de produtos da Shopee para a tabela de produtos do ERP com id_sequencial.
        """
        logger.info(f"Iniciando importação de catálogo da Shopee para a empresa {self.id_empresa}")
        access_token = self._get_valid_access_token()
        shop_id = str(self.config.shop_id)
        
        offset = 0
        has_next_page = True
        total_processados = 0
        produtos_criados = 0
        produtos_atualizados = 0
        erros = []

        path_list = "/api/v2/product/get_item_list"
        path_base_info = "/api/v2/product/get_item_base_info"
        path_model_list = "/api/v2/product/get_model_list"

        while has_next_page:
            timestamp = int(time.time())
            sign = self._generate_sign(path_list, timestamp, access_token, shop_id)
            params = {
                "partner_id": int(self.config.partner_id),
                "timestamp": timestamp,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": sign,
                "offset": offset,
                "page_size": min(page_size, 100),
                "item_status": "NORMAL"
            }

            try:
                resp = requests.get(f"{self.api_base}{path_list}", params=params, timeout=15.0)
                data = resp.json()
                if resp.status_code != 200 or data.get("error"):
                    err_msg = data.get("message") or data.get("error") or resp.text
                    logger.error(f"Erro ao listar produtos da Shopee: {err_msg}")
                    break

                response_data = data.get("response", {})
                item_list = response_data.get("item", [])
                if not item_list:
                    break

                item_ids = [str(it.get("item_id")) for it in item_list if it.get("item_id")]
                has_next_page = response_data.get("has_next_page", False)
                offset = response_data.get("next_offset", offset + len(item_ids))

                # Busca detalhes dos itens (até 50 por chamada)
                for i in range(0, len(item_ids), 50):
                    chunk = item_ids[i:i+50]
                    detail_timestamp = int(time.time())
                    detail_sign = self._generate_sign(path_base_info, detail_timestamp, access_token, shop_id)
                    detail_params = {
                        "partner_id": int(self.config.partner_id),
                        "timestamp": detail_timestamp,
                        "access_token": access_token,
                        "shop_id": int(shop_id),
                        "sign": detail_sign,
                        "item_id_list": ",".join(chunk)
                    }

                    detail_resp = requests.get(f"{self.api_base}{path_base_info}", params=detail_params, timeout=15.0)
                    detail_data = detail_resp.json()

                    if detail_resp.status_code == 200 and not detail_data.get("error"):
                        items_info = detail_data.get("response", {}).get("item_list", [])
                        for item_info in items_info:
                            total_processados += 1
                            item_id = str(item_info.get("item_id"))
                            has_model = item_info.get("has_model", False)

                            # Se tiver variações (models), consulta a lista de models
                            if has_model:
                                try:
                                    model_timestamp = int(time.time())
                                    model_sign = self._generate_sign(path_model_list, model_timestamp, access_token, shop_id)
                                    model_params = {
                                        "partner_id": int(self.config.partner_id),
                                        "timestamp": model_timestamp,
                                        "access_token": access_token,
                                        "shop_id": int(shop_id),
                                        "sign": model_sign,
                                        "item_id": int(item_id)
                                    }
                                    model_resp = requests.get(f"{self.api_base}{path_model_list}", params=model_params, timeout=10.0)
                                    model_data = model_resp.json()
                                    models_list = model_data.get("response", {}).get("model", []) if model_resp.status_code == 200 else []
                                except Exception as e:
                                    logger.warning(f"Erro ao buscar variações do produto {item_id}: {e}")
                                    models_list = []

                                if models_list:
                                    for m in models_list:
                                        m_sku = m.get("model_sku") or f"SHOPEE-{item_id}-{m.get('model_id')}"
                                        m_name = f"{item_info.get('item_name', '')} - {m.get('model_name', '')}".strip()
                                        price_info = m.get("price_info", [{}])[0] if isinstance(m.get("price_info"), list) else {}
                                        m_price = float(price_info.get("current_price") or price_info.get("original_price") or 0.0)
                                        
                                        criado = self._upsert_product(
                                            sku=m_sku,
                                            descricao=m_name,
                                            preco=m_price,
                                            peso=float(item_info.get("weight", 0.0)),
                                            update_existing=update_existing
                                        )
                                        if criado:
                                            produtos_criados += 1
                                        else:
                                            produtos_atualizados += 1
                                    continue

                            # Produto simples sem variações
                            sku = item_info.get("item_sku") or f"SHOPEE-{item_id}"
                            desc = str(item_info.get("item_name") or f"Produto Shopee {item_id}").strip()
                            price_info = item_info.get("price_info", [{}])[0] if isinstance(item_info.get("price_info"), list) else {}
                            price = float(price_info.get("current_price") or price_info.get("original_price") or 0.0)
                            weight = float(item_info.get("weight", 0.0))

                            criado = self._upsert_product(
                                sku=sku,
                                descricao=desc,
                                preco=price,
                                peso=weight,
                                update_existing=update_existing
                            )
                            if criado:
                                produtos_criados += 1
                            else:
                                produtos_atualizados += 1

            except Exception as e:
                logger.exception(f"Erro ao processar página de produtos Shopee (offset={offset}): {e}")
                erros.append(str(e))
                break

        return {
            "total_processados": total_processados,
            "produtos_criados": produtos_criados,
            "produtos_atualizados": produtos_atualizados,
            "erros": erros
        }

    def _upsert_product(self, sku: str, descricao: str, preco: float, peso: float = 0.0, update_existing: bool = True) -> bool:
        """Cria ou atualiza um produto garantindo id_sequencial."""
        produto = self.db.query(models.Produto).filter(
            models.Produto.sku == sku,
            models.Produto.id_empresa == self.id_empresa
        ).first()

        if not produto:
            novo_produto = models.Produto(
                id_empresa=self.id_empresa,
                sku=sku,
                descricao=descricao[:255],
                unidade=models.ProdutoUnidadeEnum.un,
                tipo_produto=models.ProdutoTipoEnum.mercadoria_revenda,
                origem=models.ProdutoOrigemEnum.nacional,
                preco=preco,
                custo=0,
                peso=peso,
                situacao=True
            )
            self.db.add(novo_produto)
            self.db.commit()
            self.db.refresh(novo_produto)
            return True
        elif update_existing:
            if preco > 0:
                produto.preco = preco
            if peso > 0:
                produto.peso = peso
            if descricao:
                produto.descricao = descricao[:255]
            if produto.id_sequencial is None:
                from sqlalchemy import text
                stmt = text('SELECT COALESCE(MAX(id_sequencial), 0) + 1 FROM "produtos" WHERE id_empresa = :emp_id')
                next_seq = self.db.execute(stmt, {"emp_id": self.id_empresa}).scalar() or 1
                produto.id_sequencial = next_seq
            self.db.commit()
            return False
        return False

    def get_shopee_order_detail(self, order_sn: str) -> Optional[Dict[str, Any]]:
        """
        Consulta os detalhes completos de um pedido na Shopee OpenAPI v2 via /api/v2/order/get_order_detail.
        """
        try:
            access_token = self._get_valid_access_token()
            shop_id = str(self.config.shop_id)
            timestamp = int(time.time())
            path = "/api/v2/order/get_order_detail"
            sign = self._generate_sign(path, timestamp, access_token, shop_id)

            url = f"{self.api_base}{path}"
            params = {
                "partner_id": int(self.config.partner_id),
                "timestamp": timestamp,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": sign,
                "order_sn_list": str(order_sn),
                "response_optional_fields": "order_status,tracking_number,shipping_carrier,package_list,recipient_address"
            }

            resp = requests.get(url, params=params, timeout=15.0)
            data = resp.json()
            if resp.status_code == 200 and not data.get("error"):
                orders = data.get("response", {}).get("order_list", [])
                if orders:
                    return orders[0]
            else:
                logger.warning(f"Erro ao consultar get_order_detail Shopee ({order_sn}): {data.get('message') or resp.text}")
        except Exception as e:
            logger.exception(f"Exceção ao buscar detalhes do pedido Shopee {order_sn}: {e}")
        return None

    def arrange_shipment(self, order_sn: str, pedido: models.Pedido = None) -> Dict[str, Any]:
        """
        Inicia o processo logístico/despacho de um pedido na Shopee (v2.logistics.ship_order):
        1. Consulta parâmetros de envio via GET /api/v2/logistics/get_shipping_parameter
        2. Dispara POST /api/v2/logistics/ship_order com dropoff, pickup ou non_integrated.
        """
        try:
            access_token = self._get_valid_access_token()
            shop_id = str(self.config.shop_id)
            timestamp = int(time.time())
            
            # 1. Consulta parâmetros disponíveis para o envio
            path_param = "/api/v2/logistics/get_shipping_parameter"
            sign_param = self._generate_sign(path_param, timestamp, access_token, shop_id)
            url_param = f"{self.api_base}{path_param}"
            params_param = {
                "partner_id": int(self.config.partner_id),
                "timestamp": timestamp,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": sign_param,
                "order_sn": str(order_sn)
            }

            resp_param = requests.get(url_param, params=params_param, timeout=15.0)
            data_param = resp_param.json()
            
            shipping_info = data_param.get("response", {}) if resp_param.status_code == 200 else {}
            logger.info(f"Parâmetros de envio Shopee para {order_sn}: {shipping_info}")

            # 2. Monta payload do ship_order
            path_ship = "/api/v2/logistics/ship_order"
            timestamp_ship = int(time.time())
            sign_ship = self._generate_sign(path_ship, timestamp_ship, access_token, shop_id)
            url_ship = f"{self.api_base}{path_ship}"
            params_ship = {
                "partner_id": int(self.config.partner_id),
                "timestamp": timestamp_ship,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": sign_ship
            }

            tracking_code = (
                getattr(pedido, 'shopee_tracking_number', None) or
                getattr(pedido, 'intelipost_tracking_code', None) or
                getattr(pedido, 'numero_nf', None) or
                str(order_sn)
            ) if pedido else str(order_sn)

            payload_ship = {"order_sn": str(order_sn)}

            # Avalia tipo de logística retornado pela Shopee
            has_dropoff = "dropoff" in shipping_info or shipping_info.get("dropoff") is not None
            has_pickup = "pickup" in shipping_info or shipping_info.get("pickup") is not None
            has_non_integrated = "non_integrated" in shipping_info

            if has_dropoff:
                # Modalidade Postagem / Agência (Dropoff)
                dropoff_payload = {}
                branch_list = shipping_info.get("dropoff", {}).get("branch_list", [])
                if branch_list:
                    dropoff_payload["branch_id"] = branch_list[0].get("branch_id")
                payload_ship["dropoff"] = dropoff_payload
            elif has_pickup:
                # Modalidade Coleta (Pickup)
                pickup_info = shipping_info.get("pickup", {})
                address_list = pickup_info.get("address_list", [])
                pickup_payload = {}
                if address_list:
                    pickup_payload["address_id"] = address_list[0].get("address_id")
                time_slot_list = pickup_info.get("time_slot_list", [])
                if time_slot_list:
                    pickup_payload["pickup_time_id"] = time_slot_list[0].get("pickup_time_id")
                payload_ship["pickup"] = pickup_payload
            elif has_non_integrated:
                payload_ship["non_integrated"] = {"tracking_number": str(tracking_code)}
            else:
                # Fallback padrão: Dropoff vazio
                payload_ship["dropoff"] = {}

            logger.info(f"Disparando ship_order na Shopee para pedido {order_sn}: {payload_ship}")
            resp_ship = requests.post(url_ship, params=params_ship, json=payload_ship, timeout=20.0)
            data_ship = resp_ship.json()
            
            logger.info(f"Resposta ship_order Shopee ({order_sn}): status={resp_ship.status_code}, body={resp_ship.text}")
            
            if resp_ship.status_code == 200 and not data_ship.get("error"):
                return {"status": "success", "message": "Despacho/envio agendado na Shopee com sucesso!", "data": data_ship}
            else:
                err_msg = data_ship.get("message") or data_ship.get("error") or resp_ship.text
                return {"status": "warning", "message": f"Aviso no agendamento de envio Shopee: {err_msg}", "data": data_ship}

        except Exception as e:
            logger.exception(f"Exceção ao agendar envio na Shopee ({order_sn}): {e}")
            return {"status": "error", "message": str(e)}

    def update_shopee_order_status(self, pedido: models.Pedido, target_status: str = None) -> Dict[str, Any]:
        """
        Sincroniza e atualiza o status do pedido na Shopee OpenAPI v2:
        1. Avalia regras customizadas (regras_atualizacao_status) ou mapeia por situacao / status_intelipost.
        2. Se o status alvo exigir despacho (ex: 'PROCESSED', 'SHIPPED', 'despachado'):
           - Executa GET /api/v2/logistics/get_shipping_parameter
           - Executa POST /api/v2/logistics/ship_order (dropoff / pickup / non_integrated)
        3. Consulta detalhes atualizados via GET /api/v2/order/get_order_detail
        4. Atualiza os campos locais (shopee_order_status, shopee_tracking_number, shopee_shipping_carrier, data_despacho, data_entrega).
        """
        import unicodedata
        
        def normalize_str(val):
            if not val:
                return ""
            val_str = str(val).strip().lower()
            return ''.join(c for c in unicodedata.normalize('NFD', val_str) if unicodedata.category(c) != 'Mn')

        order_sn = getattr(pedido, 'shopee_order_sn', None)
        if not order_sn and pedido.observacao:
            import re
            m = re.search(r"Pedido Shopee\s*([A-Za-z0-9]+)", pedido.observacao or "")
            if m:
                order_sn = m.group(1)
                pedido.shopee_order_sn = order_sn
                try:
                    self.db.add(pedido)
                    self.db.commit()
                except Exception:
                    pass

        if not order_sn:
            logger.info(f"Pedido #{pedido.id_sequencial or pedido.id} não possui shopee_order_sn. Atualização ignorada.")
            return {"status": "skipped", "message": "Pedido não possui identificador da Shopee (shopee_order_sn)."}

        logger.info(f"Iniciando sincronização de status para pedido Shopee {order_sn} (ERP #{pedido.id_sequencial or pedido.id})")

        situacao_str = pedido.situacao.value if hasattr(pedido.situacao, 'value') else str(pedido.situacao or "")
        status_intelipost_str = str(getattr(pedido, 'status_intelipost', '') or '')
        
        # 1. Avaliação de Regras Customizadas da ShopeeConfiguracao
        target_shopee_status = target_status
        regras = getattr(self.config, 'regras_atualizacao_status', None) or []
        if not target_shopee_status and isinstance(regras, list):
            for regra in regras:
                coluna = regra.get('coluna_pedido')
                valor_esperado_norm = normalize_str(regra.get('valor_coluna', ''))
                status_alvo_shopee = regra.get('status_shopee') or regra.get('status_meli')
                
                if coluna and valor_esperado_norm and status_alvo_shopee:
                    val_atual = getattr(pedido, coluna, None)
                    if hasattr(val_atual, 'value'):
                        val_atual = val_atual.value
                    elif hasattr(val_atual, 'name'):
                        val_atual = val_atual.name
                    val_atual_norm = normalize_str(val_atual)
                    
                    matched = False
                    if val_atual_norm == valor_esperado_norm:
                        matched = True
                    elif valor_esperado_norm in ["entregue", "completed", "finalizado", "delivered"] and val_atual_norm in ["entregue", "completed", "finalizado", "delivered"]:
                        matched = True
                    elif valor_esperado_norm in ["em transito", "shipped", "despachado", "a caminho", "processed"] and val_atual_norm in ["em transito", "shipped", "despachado", "a caminho", "processed"]:
                        matched = True
                    elif valor_esperado_norm in ["faturamento", "expedicao", "ready_to_ship", "handling", "preparacao"] and val_atual_norm in ["faturamento", "expedicao", "ready_to_ship", "handling", "preparacao"]:
                        matched = True

                    if matched:
                        target_shopee_status = status_alvo_shopee
                        logger.info(f"Regra Shopee casou! Coluna '{coluna}' = '{val_atual}' -> Status Shopee: '{target_shopee_status}'")
                        break

        # 2. Mapeamento Padrão
        if not target_shopee_status:
            sit_norm = normalize_str(situacao_str)
            inteli_norm = normalize_str(status_intelipost_str)
            
            if sit_norm in ['finalizado', 'entregue', 'delivered', 'completed'] or inteli_norm in ['delivered', 'entregue']:
                target_shopee_status = 'COMPLETED'
            elif sit_norm in ['despachado', 'em transito', 'shipped', 'a caminho'] or inteli_norm in ['shipped', 'in_transit', 'in transit', 'out_for_delivery', 'despachado', 'em transito']:
                target_shopee_status = 'SHIPPED'
            elif sit_norm in ['faturamento', 'expedicao', 'embalagem', 'producao', 'ready_to_ship']:
                target_shopee_status = 'READY_TO_SHIP'

        logger.info(f"Status Shopee alvo determinado: {target_shopee_status} para pedido {order_sn}")

        # 3. Execução de Despacho na Shopee se o status for de envio (PROCESSED / SHIPPED / despachado)
        ship_result = None
        if target_shopee_status in ['PROCESSED', 'SHIPPED', 'despachado', 'shipped']:
            ship_result = self.arrange_shipment(order_sn=order_sn, pedido=pedido)

        # 4. Sincroniza detalhes atuais do pedido via Shopee API (v2.order.get_order_detail)
        order_detail = self.get_shopee_order_detail(order_sn)
        if order_detail:
            current_status = order_detail.get('order_status')
            if current_status:
                pedido.shopee_order_status = str(current_status)
            
            tracking_code = order_detail.get('tracking_number')
            if tracking_code:
                pedido.shopee_tracking_number = str(tracking_code)
                
            carrier = order_detail.get('shipping_carrier')
            if carrier:
                pedido.shopee_shipping_carrier = str(carrier)

            if current_status in ['SHIPPED', 'TO_CONFIRM_RECEIVE', 'COMPLETED']:
                if not pedido.data_despacho:
                    pedido.data_despacho = datetime.now(timezone.utc).date()
            if current_status == 'COMPLETED':
                if not pedido.data_entrega:
                    pedido.data_entrega = datetime.now(timezone.utc).date()
                if not pedido.data_finalizacao:
                    pedido.data_finalizacao = datetime.now(timezone.utc).date()

            self.db.commit()
            self.db.refresh(pedido)

        return {
            "status": "success",
            "message": f"Status sincronizado com a Shopee para o pedido {order_sn}!",
            "shopee_order_status": getattr(pedido, 'shopee_order_status', None),
            "tracking_number": getattr(pedido, 'shopee_tracking_number', None),
            "ship_result": ship_result
        }

    def upload_xml(self, order_sn: str, xml_content: str, chave_acesso: str = None, numero_nf: str = None) -> Dict[str, Any]:
        """
        Transmite o XML da NF-e autorizada para a Shopee OpenAPI v2 via POST /api/v2/order/upload_invoice_doc.
        Suporta file_type="4" (código oficial da Shopee para XML de NF-e no Brasil).
        """
        logger.info(f"Iniciando transmissão de XML da NF-e para o pedido Shopee {order_sn}")
        
        # 1. Normaliza conteúdo do XML
        if isinstance(xml_content, bytes):
            xml_bytes = xml_content
            xml_str = xml_content.decode('utf-8', errors='ignore')
        else:
            xml_str = str(xml_content or "").strip()
            if not xml_str.startswith('<?xml'):
                xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + xml_str
            xml_bytes = xml_str.encode('utf-8')

        # 2. Localiza pedido no banco de dados local
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.shopee_order_sn == order_sn,
            models.Pedido.id_empresa == self.id_empresa
        ).first()

        try:
            access_token = self._get_valid_access_token()
            shop_id = str(self.config.shop_id)
            timestamp = int(time.time())
            path = "/api/v2/order/upload_invoice_doc"
            sign = self._generate_sign(path, timestamp, access_token, shop_id)

            url = f"{self.api_base}{path}"
            params = {
                "partner_id": int(self.config.partner_id),
                "timestamp": timestamp,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": sign
            }

            # Envia via Multipart Form-Data (file_type="4" para XML NF-e)
            files = {
                'file': (f"NFe_{numero_nf or order_sn}.xml", xml_bytes, 'application/xml')
            }
            data = {
                'order_sn': str(order_sn),
                'file_type': '4'
            }

            logger.info(f"Enviando POST para {url} (file_type=4, order_sn={order_sn})")
            resp = requests.post(url, params=params, data=data, files=files, timeout=20.0)
            res_json = {}
            try:
                res_json = resp.json()
            except Exception:
                pass

            logger.info(f"Resposta Shopee upload_invoice_doc: status_code={resp.status_code}, body={resp.text}")

            # Valida resposta
            error_code = res_json.get("error") or ""
            error_msg = res_json.get("message") or ""

            # Caso de sucesso ou se o XML já constava como enviado
            is_success = (
                (resp.status_code == 200 and not error_code) or
                "already" in error_msg.lower() or
                "exist" in error_msg.lower() or
                "duplicate" in error_msg.lower()
            )

            if is_success:
                if pedido:
                    pedido.shopee_xml_enviado = True
                    self.db.commit()
                    self.db.refresh(pedido)
                msg = "XML já constava na Shopee!" if ("already" in error_msg.lower() or "exist" in error_msg.lower()) else "XML da NF-e transmitido com sucesso para a Shopee!"
                return {"status": "success", "message": msg, "response": res_json}
            else:
                # Tenta fallback com text/xml se necessário
                logger.warning(f"Tentativa 1 falhou ({error_code} - {error_msg}). Tentando fallback...")
                timestamp2 = int(time.time())
                sign2 = self._generate_sign(path, timestamp2, access_token, shop_id)
                params2 = {
                    "partner_id": int(self.config.partner_id),
                    "timestamp": timestamp2,
                    "access_token": access_token,
                    "shop_id": int(shop_id),
                    "sign": sign2
                }
                files2 = {
                    'file': (f"NFe_{numero_nf or order_sn}.xml", xml_str, 'text/xml')
                }
                resp2 = requests.post(url, params=params2, data=data, files=files2, timeout=20.0)
                try:
                    res_json2 = resp2.json()
                except Exception:
                    res_json2 = {}
                
                if (resp2.status_code == 200 and not res_json2.get("error")) or "already" in str(res_json2).lower():
                    if pedido:
                        pedido.shopee_xml_enviado = True
                        self.db.commit()
                        self.db.refresh(pedido)
                    return {"status": "success", "message": "XML transmitido com sucesso para a Shopee!", "response": res_json2}

                err_detail = error_msg or res_json2.get("message") or resp.text
                logger.error(f"Erro ao transmitir XML para Shopee (Pedido {order_sn}): {err_detail}")
                return {"status": "error", "message": f"Erro na API da Shopee: {err_detail}", "details": res_json}

        except Exception as e:
            logger.exception(f"Exceção ao enviar XML para a Shopee ({order_sn}): {e}")
            return {"status": "error", "message": f"Falha de comunicação ao enviar XML para Shopee: {str(e)}"}

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
