import httpx
import json
import traceback
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status
from typing import Dict, Any, List
from datetime import datetime
from decimal import Decimal

from app.core.db import models
from app.core.config import settings

class IntelipostService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        self.base_url = "https://api.intelipost.com.br/api/v1"
        
        # Busca configuração usando ORM
        config = self.db.query(models.IntelipostConfiguracao).filter(
            models.IntelipostConfiguracao.id_empresa == self.id_empresa
        ).first()

        if not config or not config.api_key:
            # Se não tiver config, lançamos erro ou iniciamos vazio (depende da estratégia)
            # Aqui vou lançar erro para forçar configuração
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Integração Intelipost não configurada para esta empresa."
            )
        
        self.api_key = config.api_key
        self.origin_zip_code = config.origin_zip_code.replace("-", "") if config.origin_zip_code else ""
        self.origin_warehouse_code = config.origin_warehouse_code or "CD01"
        
        self.headers = {
            'api-key': self.api_key,
            'Content-Type': 'application/json',
            'platform': 'IntegraAI'
        }
        
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=30.0)

    def _find_carrier_by_intelipost_id(self, delivery_method_id: Any) -> models.Cadastro:
        """
        Busca a transportadora (Cadastro) que possua o delivery_method_id informado
        em seu campo delivery_method_id_intelipost (suporta múltiplos IDs separados por ';').
        """
        if not delivery_method_id:
            return None
            
        search_id = str(delivery_method_id).strip()
        
        return self.db.query(models.Cadastro).filter(
            models.Cadastro.id_empresa == self.id_empresa,
            models.Cadastro.tipo_cadastro == models.CadastroTipoCadastroEnum.transportadora,
            or_(
                models.Cadastro.delivery_method_id_intelipost == search_id,
                models.Cadastro.delivery_method_id_intelipost.like(f"%;{search_id}"),
                models.Cadastro.delivery_method_id_intelipost.like(f"{search_id};%"),
                models.Cadastro.delivery_method_id_intelipost.like(f"%;{search_id};%"),
                # Variações com espaços para garantir compatibilidade
                models.Cadastro.delivery_method_id_intelipost.like(f"%; {search_id}"),
                models.Cadastro.delivery_method_id_intelipost.like(f"{search_id}; %"),
                models.Cadastro.delivery_method_id_intelipost.like(f"%; {search_id};%")
            )
        ).first()

    def _evaluate_formula(self, formula_list: List[Dict[str, str]], context: Dict[str, float]) -> float:
        if not formula_list:
            return 0.0
        
        expression = ""
        for token in formula_list:
            t_type = token.get('tipo')
            t_val = token.get('valor')
            
            if t_type == 'variavel':
                val = context.get(t_val, 0.0)
                expression += str(val)
            elif t_type == 'numero':
                expression += str(t_val)
            elif t_type == 'operador':
                if t_val in ['+', '-', '*', '/', '(', ')']:
                    expression += t_val
        
        try:
            return float(eval(expression, {"__builtins__": None}, {}))
        except Exception:
            return 0.0

    async def _calculate_volumes_for_item(self, item_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calcula volumes baseados no produto do banco de dados via ORM.
        """
        produto_id = item_dict.get('id_produto') or item_dict.get('produto_id')
        quantidade = float(item_dict.get('quantidade', 0))

        if quantidade <= 0:
            return []

        # Busca produto no banco
        produto = self.db.query(models.Produto).filter(
            models.Produto.id == produto_id,
            models.Produto.id_empresa == self.id_empresa
        ).first()

        if not produto:
            return []

        # Pega dimensões (com fallbacks para evitar erro se estiver vazio)
        altura = float(produto.altura or 10)
        largura = float(produto.largura or 10)
        comprimento = float(produto.comprimento or 10)
        peso = float(produto.peso or 0.1)
        
        # --- CORREÇÃO DE PREÇO ZERO ---
        preco_cadastro = float(produto.preco or 0)
        preco_pedido = float(item_dict.get('valor_unitario') or item_dict.get('preco') or 0)

        # Prioriza o preço do pedido; se não tiver, usa o do cadastro
        preco = preco_pedido if preco_pedido > 0 else preco_cadastro
        
        if preco <= 0:
             # Fallback de emergência: tenta deduzir pelo total do item se existir
             total_item = float(item_dict.get('subtotal') or item_dict.get('total') or 0)
             qtd_item = float(item_dict.get('quantidade') or 1)
             if total_item > 0 and qtd_item > 0:
                 preco = total_item / qtd_item
             else:
                 preco = 0.01 # Valor simbólico para evitar Crash 500

        volumes = []
        qtd_remaining = quantidade

        # Verifica se o produto tem embalagem definida e regras
        if produto.id_embalagem:
            embalagem = self.db.query(models.Embalagem).filter(
                models.Embalagem.id == produto.id_embalagem,
                models.Embalagem.id_empresa == self.id_empresa
            ).first()

            if embalagem and embalagem.regras:
                rules_data = embalagem.regras
                # O frontend salva como { rules: [...] }
                rules = rules_data.get('rules', []) if isinstance(rules_data, dict) else []
                # Ordena por prioridade decrescente
                rules.sort(key=lambda x: int(x.get('prioridade', 0)), reverse=True)

                loop_limit = 1000
                loop_count = 0

                while qtd_remaining > 0 and loop_count < loop_limit:
                    loop_count += 1
                    matched_rule = None

                    for rule in rules:
                        cond = rule.get('condicao_gatilho')
                        val_gatilho_str = rule.get('valor_gatilho')
                        
                        # Parse do valor do gatilho
                        val_gatilho = 0.0
                        try:
                            if val_gatilho_str and cond != 'ENTRE':
                                val_gatilho = float(val_gatilho_str)
                        except:
                            pass

                        match = False
                        if cond == 'SEMPRE':
                            match = True
                        elif cond == 'MAIOR_IGUAL_A':
                            match = qtd_remaining >= val_gatilho
                        elif cond == 'IGUAL_A':
                            match = qtd_remaining == val_gatilho
                        elif cond == 'MENOR_QUE':
                            match = qtd_remaining < val_gatilho
                        elif cond == 'ENTRE':
                            try:
                                parts = str(val_gatilho_str).split(',')
                                if len(parts) == 2:
                                    v_min, v_max = float(parts[0]), float(parts[1])
                                    match = v_min <= qtd_remaining <= v_max
                            except:
                                match = False
                        
                        if match:
                            matched_rule = rule
                            break
                    
                    if matched_rule:
                        context = {
                            'QTD_A_PROCESSAR': qtd_remaining,
                            'QTD_TOTAL_PEDIDO': quantidade,
                            'PESO_ITEM_UNICO': peso,
                            'ALTURA_ITEM_UNICO': altura,
                            'LARGURA_ITEM_UNICO': largura,
                            'COMPRIMENTO_ITEM_UNICO': comprimento,
                            'ACRESCIMO_EMBALAGEM': 0 
                        }

                        items_in_vol = self._evaluate_formula(matched_rule.get('formula_itens', []), context)
                        # Garante que pegue pelo menos 1 se a fórmula der 0 ou negativo, e não mais que o restante
                        items_in_vol = max(1.0, items_in_vol)
                        items_in_vol = min(items_in_vol, qtd_remaining)

                        # Atualiza contexto para dimensões
                        context['QTD_NESTE_VOLUME'] = items_in_vol
                        
                        vol_h = max(0.1, self._evaluate_formula(matched_rule.get('formula_altura', []), context))
                        vol_w = max(0.1, self._evaluate_formula(matched_rule.get('formula_largura', []), context))
                        vol_l = max(0.1, self._evaluate_formula(matched_rule.get('formula_comprimento', []), context))
                        vol_weight = max(0.01, self._evaluate_formula(matched_rule.get('formula_peso', []), context))

                        volumes.append({
                            "weight": vol_weight,
                            "cost_of_goods": round(preco * items_in_vol, 2),
                            "width": vol_w,
                            "height": vol_h,
                            "length": vol_l,
                            "volume_type": "BOX",
                            "products_quantity": int(items_in_vol)
                        })

                        qtd_remaining -= items_in_vol
                    else:
                        # Nenhuma regra bateu, sai do loop para fallback
                        break
        
        # Fallback: Se sobrou quantidade ou não tinha embalagem, cria volume com o restante
        if qtd_remaining > 0:
            volumes.append({
                "weight": peso * qtd_remaining,
                "cost_of_goods": round(preco * qtd_remaining, 2),
                "width": largura,
                "height": altura,
                "length": comprimento,
                "volume_type": "BOX",
                "volume_type_code": "BOX",
                "products_quantity": int(qtd_remaining)
            })
            
        return volumes

    async def criar_pedido_envio(self, pedido_id: int, dados_frete: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria a ordem de envio (Shipment Order) na Intelipost.
        """
        if settings.ENVIRONMENT != "production":
            return {"status": "success", "message": "Simulado: Ordem de envio criada na Intelipost (Ambiente de Testes)"}

        # 1. Busca Pedido e Relacionamentos
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.id == pedido_id,
            models.Pedido.id_empresa == self.id_empresa
        ).first()

        if not pedido or not pedido.cliente:
            raise HTTPException(status_code=404, detail="Pedido ou Cliente não encontrado.")

        empresa = self.db.query(models.Empresa).filter(models.Empresa.id == self.id_empresa).first()

        # 2. Recalcula volumes (para garantir consistência com o que foi cotado)
        # Nota: Idealmente, persistiríamos os volumes da cotação, mas recalcular é seguro se os itens não mudaram.
        lista_itens = pedido.itens if isinstance(pedido.itens, list) else []
        tasks = [self._calculate_volumes_for_item(item) for item in lista_itens]
        results = await asyncio.gather(*tasks)
        all_volumes = [vol for sublist in results for vol in sublist]

        # Ajusta os volumes para corresponder exatamente à quantidade de volumes no campo de pedidos (pedido.volumes_quantidade)
        target_qty = pedido.volumes_quantidade
        if target_qty and target_qty > 0:
            # Pega as medidas diretamente do cadastro de produtos do pedido
            prod_dimensions = []
            for item in lista_itens:
                prod_id = item.get('id_produto') or item.get('produto_id')
                if prod_id:
                    prod = self.db.query(models.Produto).filter(
                        models.Produto.id == prod_id,
                        models.Produto.id_empresa == self.id_empresa
                    ).first()
                    if prod:
                        w = float(prod.largura or 10.0)
                        h = float(prod.altura or 10.0)
                        l = float(prod.comprimento or 10.0)
                        qtd = int(float(item.get('quantidade') or 1))
                        for _ in range(max(1, qtd)):
                            prod_dimensions.append((w, h, l))

            # Se não conseguimos nenhuma dimensão, usamos fallback padrão
            if not prod_dimensions:
                prod_dimensions = [(10.0, 10.0, 10.0)]

            # Ajusta a lista de dimensões para ter exatamente target_qty elementos
            if len(prod_dimensions) < target_qty:
                last_dim = prod_dimensions[-1]
                while len(prod_dimensions) < target_qty:
                    prod_dimensions.append(last_dim)
            elif len(prod_dimensions) > target_qty:
                prod_dimensions = prod_dimensions[:target_qty]

            # Pega o peso bruto total do pedido
            peso_bruto_total = float(pedido.volumes_peso_bruto) if pedido.volumes_peso_bruto and pedido.volumes_peso_bruto > 0 else sum(vol.get('weight', 0.0) for vol in all_volumes)
            if peso_bruto_total <= 0:
                peso_bruto_total = 1.0 # fallback
            
            peso_individual = peso_bruto_total / target_qty

            # Reconstrói os volumes para ter exatamente target_qty volumes com as medidas dos produtos
            adjusted_volumes = []
            for i in range(target_qty):
                w, h, l = prod_dimensions[i]
                adjusted_volumes.append({
                    "weight": round(peso_individual, 3),
                    "width": w,
                    "height": h,
                    "length": l,
                    "volume_type_code": "BOX",
                    "products_quantity": 1
                })
            all_volumes = adjusted_volumes

        if not all_volumes:
            raise HTTPException(status_code=400, detail="Não há volumes calculados para este pedido.")

        # 3. Prepara dados do Cliente (Destinatário)
        nome_parts = (pedido.cliente.nome_razao or "").split(" ", 1)
        first_name = nome_parts[0]
        last_name = nome_parts[1] if len(nome_parts) > 1 else "."

        # 4. Prepara dados da Empresa (Remetente)
        seller_parts = (empresa.razao or "").split(" ", 1)
        seller_first = seller_parts[0]
        seller_last = seller_parts[1] if len(seller_parts) > 1 else "."

        # Prefixo para o número do pedido (3 primeiras letras do Fantasia + ID Sequencial + 'N')
        nome_base = empresa.fantasia if empresa.fantasia else (empresa.razao or "")
        prefixo = nome_base.strip()[:3].upper()
        codigo_pedido = pedido.id_sequencial if pedido.id_sequencial is not None else pedido.id
        numero_pedido_intelipost = f"{prefixo}{codigo_pedido}N"

        # Salva o id_pedido_intelipost no pedido
        pedido.id_pedido_intelipost = numero_pedido_intelipost
        self.db.commit()

        # -------------------------------------------------------------
        # CORREÇÃO 1: Datas sem microsegundos e Lógica de Estimativa
        # -------------------------------------------------------------
        from datetime import timedelta, timezone
        
        fuso_br = timezone(timedelta(hours=-3))
        now = datetime.now(fuso_br).replace(microsecond=0) # Remove microsegundos
        now_iso = now.isoformat()
        
        # Prioriza a data de entrega já existente no pedido
        if pedido.data_entrega:
            estimated_dt = datetime.combine(pedido.data_entrega, datetime.min.time(), tzinfo=fuso_br)
            estimated_iso = estimated_dt.isoformat()
        else:
            # Fallback: Caso não haja data, usa o prazo da cotação para calcular
            prazo_dias = int(dados_frete.get('delivery_time') or 5)
            estimated_dt = now + timedelta(days=max(prazo_dias, 1))
            estimated_iso = estimated_dt.isoformat()
            
            # Persiste a data calculada no pedido para futuras consultas
            pedido.data_entrega = estimated_dt.date()
            self.db.commit()

        # Helper para formatar data da nota (também sem microsegundos)
        def format_invoice_date(dt):
            if not dt: return now_iso
            if isinstance(dt, str): return dt
            # Garante datetime
            if not hasattr(dt, 'hour'): 
                dt = datetime.combine(dt, datetime.min.time(), tzinfo=fuso_br)
            elif not dt.tzinfo:
                dt = dt.replace(tzinfo=fuso_br)
            return dt.replace(microsecond=0).isoformat()

        # 5. Monta Payload Intelipost
        # Mapeia os volumes para o formato de shipment order (adicionando shipment_order_volume_number)
        shipment_volumes = []
        for idx, vol in enumerate(all_volumes):
            vol_copy = vol.copy()
            vol_copy['shipment_order_volume_number'] = idx + 1
            vol_copy['products_nature'] = 'Mercadorias'
            
            # Garante dimensões como float (Intelipost pode rejeitar inteiros ou strings mal formatadas)
            vol_copy['length'] = float(vol_copy.get('length', 1))
            vol_copy['width'] = float(vol_copy.get('width', 1))
            vol_copy['height'] = float(vol_copy.get('height', 1))
            vol_copy['volume_type_code'] = vol_copy.get('volume_type_code') or vol_copy.get('volume_type') or 'BOX'

            # REMOVE CAMPOS QUE NÃO EXISTEM NA DOC DE SHIPMENT (mas existiam na cotação)
            # 'cost_of_goods' no nível do volume pode quebrar o shipment
            vol_copy.pop('cost_of_goods', None)
            vol_copy.pop('volume_type', None)

            # Se tiver dados de nota fiscal no pedido, adiciona aqui
            if pedido.chave_acesso and len(pedido.chave_acesso) == 44:
                try:
                    serie = str(int(pedido.chave_acesso[22:25]))
                    numero = str(int(pedido.chave_acesso[25:34]))
                    
                    valor_total = float(pedido.total or 0)
                    valor_frete = float(pedido.valor_frete or 0)
                    valor_produtos = valor_total - valor_frete

                    vol_copy['shipment_order_volume_invoice'] = {
                        "invoice_series": serie,
                        "invoice_number": numero,
                        "invoice_key": pedido.chave_acesso,
                        "invoice_date": format_invoice_date(pedido.data_nf),
                        "invoice_total_value": valor_total,
                        "invoice_products_value": round(valor_produtos, 2)
                    }
                except ValueError:
                    pass
            shipment_volumes.append(vol_copy)

        # Garante que o estado seja string (caso seja Enum)
        uf_cliente = pedido.cliente.estado
        if hasattr(uf_cliente, 'value'):
            uf_cliente = uf_cliente.value

        # Tratamento de telefone (evitar string vazia)
        phone_cliente = pedido.cliente.celular or pedido.cliente.telefone or "0000000000"

        # --- LÓGICA PARA QUOTE_ID ---
        quote_id = dados_frete.get('quote_id') or dados_frete.get('id_cotacao')

        # Preparação prévia de dados para o Seller (Empresa)
        # Verifica se o estado é objeto/enum ou string direta
        uf_empresa = empresa.estado
        if hasattr(uf_empresa, 'value'):
            uf_empresa = uf_empresa.value
        
        # Formata CEP da empresa (remove traços e pontos)
        cep_empresa = empresa.cep.replace("-", "").replace(".", "") if empresa.cep else self.origin_zip_code

        # --- LÓGICA PARA DELIVERY METHOD ID ---
        # Prioriza o que veio no payload (dados da cotação), 
        # senão busca no cadastro da transportadora atrelada ao pedido.
        delivery_method_id = dados_frete.get('delivery_method_id')

        # Se recebemos um ID de método (vindo da seleção de cotação), 
        # tentamos encontrar a transportadora correspondente no ERP para atualizar o pedido.
        if delivery_method_id:
            pedido.delivery_method_id_intelipost = str(delivery_method_id)
            carrier = self._find_carrier_by_intelipost_id(delivery_method_id)
            if carrier:
                pedido.id_transportadora = carrier.id_sequencial or carrier.id

        if not delivery_method_id:
            delivery_method_id = pedido.delivery_method_id_intelipost

        if not delivery_method_id and pedido.transportadora:
            delivery_method_id = pedido.transportadora.delivery_method_id_intelipost

        # Suporte a múltiplos IDs separados por ';' (limpa espaços e pega o primeiro)
        if delivery_method_id and isinstance(delivery_method_id, str):
            ids_limpos = [i.strip() for i in delivery_method_id.split(';') if i.strip()]
            delivery_method_id = ids_limpos[0] if ids_limpos else None

        payload = {
            "order_number": numero_pedido_intelipost,
            "sales_order_number": numero_pedido_intelipost,
            "delivery_method_id": int(delivery_method_id) if delivery_method_id else None,
            "final_shipping_cost": float(dados_frete.get('final_shipping_cost', 0)),
            "provider_shipping_costs": float(dados_frete.get('final_shipping_cost', 0)),
            
            "origin_warehouse_code": self.origin_warehouse_code, 
            "origin_zip_code": self.origin_zip_code, # Usa o CEP configurado na classe
            
            "shipment_order_type": "NORMAL",
            "shipment_order_volume_array": shipment_volumes,
            "customer_shipping_costs": float(pedido.valor_frete or dados_frete.get('final_shipping_cost', 0)),
            "sales_channel": (pedido.origem_venda or "").strip() or "IntegraAI",
            "scheduled": False,
            "created": now_iso,
            # CAMPO OBRIGATÓRIO ADICIONADO:
            "shipped_date": now_iso,
            # CAMPO RECOMENDADO ADICIONADO:
            "estimated_delivery_date": estimated_iso,
            # Destinatário
            "end_customer": {
                "first_name": first_name,
                "last_name": last_name,
                "email": pedido.cliente.email or "nao_informado@email.com",
                "phone": phone_cliente,
                "is_company": str(pedido.cliente.tipo_pessoa) == 'juridica',
                "federal_tax_payer_id": pedido.cliente.cpf_cnpj,
                "shipping_address": pedido.cliente.logradouro,
                "shipping_number": pedido.cliente.numero,
                "shipping_additional": pedido.cliente.complemento,
                "shipping_quarter": pedido.cliente.bairro,
                "shipping_city": pedido.cliente.cidade,
                "shipping_state": uf_cliente,
                "shipping_zip_code": pedido.cliente.cep.replace("-", ""),
                "shipping_country": "BR"
            },
            # Remetente
            "seller": {
                "first_name": seller_first,
                "last_name": seller_last,
                "email": "contato@talatto.com.br", # Idealmente vir do cadastro da empresa
                "phone": empresa.telefone,
                "is_company": True,
                "federal_tax_payer_id": empresa.cnpj,
                "state_tax_payer_id": empresa.inscricao_estadual,
                
                # --- NOVOS CAMPOS ADICIONADOS ---
                "country": "Brasil",
                "state": uf_empresa,             # Estado da empresa (Ex: PR)
                "city": empresa.cidade,          # Cidade
                "address": empresa.logradouro,   # Rua/Logradouro
                "number": empresa.numero,        # Número
                "additional": empresa.complemento or "", # Complemento (evitar null)
                "quarter": empresa.bairro,       # Bairro
                "zip_code": cep_empresa,         # CEP formatado
                "reference": ""                  # Referência (opcional)
            }
        }

        # --- INCLUIR quote_id APENAS SE ELE REALMENTE EXISTIR ---
        if quote_id:
            payload["quote_id"] = quote_id

        # Limpeza final de chaves com valor None
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            # Endpoint para criar ordem de envio
            response = await self.client.post('/shipment_order', json=payload)

            # --- LOG BRUTO (DEBUG) ---
            print("\n" + "="*60)
            print(">>> REQUEST INTELIPOST (shipment_order)")
            print(f"METHOD: {response.request.method}")
            print(f"URL: {response.request.url}")
            print("HEADERS:")
            for k, v in response.request.headers.items():
                if k.lower() == 'api-key':
                    print(f"  {k}: {v[:5]}...***")
                else:
                    print(f"  {k}: {v}")
            print("BODY:")
            print(response.request.content.decode('utf-8') if response.request.content else "Empty")
            print("-" * 60)
            print("<<< RESPONSE INTELIPOST")
            print(f"STATUS: {response.status_code}")
            print("BODY:")
            print(response.text)
            print("="*60 + "\n")

            response.raise_for_status()
            res_json = response.json()
            pedido.intelipost_criado = True
            if isinstance(res_json.get("content"), dict) and res_json["content"].get("id"):
                pedido.intelipost_id = str(res_json["content"]["id"])
            self.db.commit()
            return res_json
        except httpx.HTTPStatusError as e:
            # Tenta extrair a mensagem amigável do JSON da Intelipost
            try:
                err_json = e.response.json()
                messages = err_json.get('messages', [])
                if messages and isinstance(messages, list):
                    err_msg = messages[0].get('text', e.response.text)
                else:
                    err_msg = e.response.text
            except:
                err_msg = e.response.text

            print(f"Erro Intelipost Shipment: {err_msg}")
            
            # Se já existe (conforme reportado no erro IND314), não é um erro impeditivo.
            # Verificamos no corpo da resposta e na mensagem amigável de forma insensível a maiúsculas.
            err_msg_lower = str(err_msg).lower()
            already_exists = (
                "already.existing.order.number" in e.response.text or 
                "já existe" in err_msg_lower or 
                "já possui uma ordem de envio" in err_msg_lower
            )
            if already_exists:
                 return {"status": "warning", "message": f"Aviso Intelipost: {err_msg}", "details": err_json if 'err_json' in locals() else None}
            
            raise HTTPException(status_code=e.response.status_code, detail=f"Erro Intelipost: {err_msg}")
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    async def cotar_por_pedido(self, pedido_id: int, update_db: bool = True) -> Dict[str, Any]:
        """
        Busca o pedido, cliente e itens via ORM e realiza a cotação.
        """
        # 1. Busca Pedido
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.id == pedido_id,
            models.Pedido.id_empresa == self.id_empresa
        ).first()

        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")

        # 2. Busca Cliente (para o CEP)
        if not pedido.cliente:
             raise HTTPException(status_code=400, detail="Pedido sem cliente vinculado.")
        
        cep_destino = pedido.cliente.cep.replace("-", "").replace(".", "")
        if not cep_destino:
            raise HTTPException(status_code=400, detail="Cliente sem CEP cadastrado.")

        # 3. Processa Itens (O campo 'itens' no modelo novo é JSON)
        lista_itens = pedido.itens if isinstance(pedido.itens, list) else []
        if not lista_itens:
            raise HTTPException(status_code=400, detail="Pedido sem itens.")

        tasks = [self._calculate_volumes_for_item(item) for item in lista_itens]
        results = await asyncio.gather(*tasks)
        
        # Flatten na lista de volumes
        all_volumes = [vol for sublist in results for vol in sublist]

        if not all_volumes:
            raise HTTPException(status_code=400, detail="Não foi possível calcular volumes dos produtos.")

        # --- Atualiza Pedido com os Volumes Calculados ---
        if update_db:
            total_peso = sum(float(v.get('weight', 0)) for v in all_volumes)
            
            pedido.volumes_quantidade = len(all_volumes)
            pedido.volumes_peso_bruto = Decimal(f"{total_peso:.3f}")
            pedido.volumes_peso_liquido = Decimal(f"{total_peso:.3f}")
            pedido.volumes_especie = 'VOLUMES'
            
            self.db.commit()
            self.db.refresh(pedido)

        # 4. Payload Intelipost
        payload = {
            "origin_zip_code": self.origin_zip_code,
            "destination_zip_code": cep_destino,
            "volumes": all_volumes,
            "additional_information": {
                "sales_channel": (pedido.origem_venda or "").strip() or "IntegraAI",
                "client_type": "gold" # Exemplo
            }
        }

        try:
            response = await self.client.post('/quote', json=payload)
            response.raise_for_status()
            return {
                "volumes": all_volumes,
                "cotacao": response.json()
            }
        except httpx.HTTPStatusError as e:
            try:
                err_json = e.response.json()
                messages = err_json.get('messages', [])
                err_msg = messages[0].get('text', "Erro ao cotar na Intelipost.") if messages else "Erro ao cotar na Intelipost."
            except:
                err_msg = "Erro ao cotar na Intelipost."

            print(f"Erro Intelipost Cotação: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=err_msg)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))