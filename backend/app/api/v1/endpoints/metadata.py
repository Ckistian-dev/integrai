from fastapi import APIRouter, HTTPException
from typing import List, Optional
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy import String, Integer, Boolean, Numeric, Date, DateTime, JSON, LargeBinary, Enum as SQLAlchemyEnum
from sqlalchemy.sql.elements import ClauseElement

from app.core.db.schemas import ModelMetadata, FieldMetadata
from app.api.v1.model_dispatch import get_registry_entry

router = APIRouter()


# Mapeia nomes de colunas para labels amigáveis
def get_field_label(col_name: str) -> str:
    if col_name.lower() == "id_sequencial":
        return "ID"
    if col_name.lower() == "id":
        return "ID Interno"
    # 🎯 1. Remove prefixos e sufixos de ID
    if col_name.startswith("id_"):
        col_name = col_name[3:] # "id_vendedor" -> "vendedor"
    elif col_name.endswith("_id"):
        col_name = col_name[:-3] # "vendedor_id" -> "vendedor"
    
    # 2. Substitui underscores por espaços
    text_with_spaces = col_name.replace("_", " ") # "nome_razao" -> "nome razao"
    
    # 3. Capitaliza a primeira letra de cada palavra
    return text_with_spaces.title() # "nome razao" -> "Nome Razao", "vendedor" -> "Vendedor"

# Campos que não devem aparecer no formulário do frontend
SKIPPED_FIELDS = ["id_empresa", "id"]

def get_format_mask(col_name: str, col_type: TypeEngine) -> Optional[str]:
    # Converte para minúsculas para facilitar a comparação
    name = col_name.lower()
    
    if isinstance(col_type, DateTime):
        return 'datetime' # Ex: 31/12/2025 14:30
    if isinstance(col_type, Date):
        return 'date'     # Ex: 31/12/2025
    
    # Máscaras de CPF/CNPJ
    if 'cnpj' in name or 'cpf_cnpj' in name:
        return 'cnpj' # O frontend decide qual aplicar com base no tamanho
    # Máscaras de CEP
    if 'cep' in name:
        return 'cep'
    # Máscaras de Telefone/Celular
    if 'telefone' in name or 'celular' in name:
        return 'phone' # O frontend pode usar uma máscara dinâmica
    
    # 🎯 CORREÇÃO: Detecta explicitamente a classe Currency criada no models.py
    # Verifica pelo nome da classe para evitar importação circular
    if col_type.__class__.__name__ == 'Currency':
        return 'currency'

    # Percentuais (aliquota, reducao_bc_perc, etc.)
    if name.endswith('aliquota') or name.endswith('perc'):
         return 'percent:2'

    # Campos Numéricos (Peso, Dimensões, etc)
    if isinstance(col_type, Numeric):
        scale = getattr(col_type, 'scale', None)
        if scale == 3:
            return 'decimal:3'
        # Default para 2 casas decimais (inclui scale=2 e scale=None)
        if scale == 2 or scale is None:
            return 'decimal:2'

    return None # Nenhuma máscara especial


@router.get("/metadata/{model_name}", response_model=ModelMetadata)
def get_model_metadata(model_name: str):
    """
    Retorna os metadados de um modelo para o frontend construir
    formulários e tabelas dinamicamente.
    """
    # 1. INTERCEPTAÇÃO MANUAL (Coloque isto NO TOPO da função)
    if model_name == "mercadolivre_pedidos":
        return ModelMetadata(
            model_name="mercadolivre_pedidos",
            display_name="Pedidos Mercado Livre",
            display_field="id",
            fields=[] # Campos dinâmicos construídos pelo frontend
        )

    if model_name == "magento_pedidos":
        return ModelMetadata(
            model_name="magento_pedidos",
            display_name="Pedidos Magento",
            display_field="increment_id",
            fields=[] # Campos dinâmicos construídos pelo frontend
        )

    if model_name == "tiktok_pedidos":
        return ModelMetadata(
            model_name="tiktok_pedidos",
            display_name="Pedidos Tiktok Shop",
            display_field="id",
            fields=[] # Campos dinâmicos construídos pelo frontend
        )

    if model_name == "shopee_pedidos":
        return ModelMetadata(
            model_name="shopee_pedidos",
            display_name="Pedidos Shopee",
            display_field="order_sn",
            fields=[] # Campos dinâmicos construídos pelo frontend
        )

    registry_entry = get_registry_entry(model_name)
    if not registry_entry:
        raise HTTPException(status_code=404, detail="Model not found")

    model = registry_entry["model"]
    display_name = registry_entry["display_name"]
    display_field = registry_entry.get("display_field", None)
    is_single_record = (
        model_name == "empresas" or 
        model_name.endswith("_configuracao") or 
        model_name.endswith("_configuracoes") or 
        getattr(model, '__is_single_record__', False)
    )
    fields: List[FieldMetadata] = []
    
    

    try:
        
        # Inspeciona as colunas do modelo SQLAlchemy
        for col in model.__table__.columns:
            if col.name in SKIPPED_FIELDS:
                continue
            
            tab_name = col.info.get('tab', 'Dados Gerais')
            sub_tab_name = col.info.get('sub_tab')
            
            # Tenta pegar label e placeholder do col.info
            label = col.info.get('label')
            if not label:
                label = get_field_label(col.name)
            placeholder = col.info.get('placeholder')
            
            # Tenta pegar o valor default (prioridade: info > model default)
            default_value = col.info.get('default')
            if default_value is None and col.default and hasattr(col.default, 'arg'):
                # Verifica se é um valor escalar (não função/callable) para enviar ao front
                arg = col.default.arg
                if not callable(arg) and not isinstance(arg, ClauseElement):
                    default_value = arg

            # Tenta pegar a máscara do col.info primeiro, se não, tenta detectar
            format_mask = col.info.get('format_mask')
            if not format_mask:
                format_mask = get_format_mask(col.name, col.type)
            
            required = col.info.get('required') if col.info.get('required') is not None else (not col.nullable and not col.primary_key)
            
            foreign_key_model = col.info.get('foreign_key_model')
            foreign_key_label_field = col.info.get('foreign_key_label_field')
            filename_field = col.info.get('filename_field')
            col_span = col.info.get('col_span')
            visible = col.info.get('visible', True)
            
            if not foreign_key_model and col.foreign_keys:
                fk = next(iter(col.foreign_keys), None)
                if fk:
                    # 1. Obtém o nome da tabela referenciada (ex: "cadastros")
                    fk_model_name = fk.column.table.name
                    foreign_key_model = fk_model_name
                    
                    # 2. Busca o registro desse modelo (usando sua função)
                    try:
                        fk_registry_entry = get_registry_entry(fk_model_name)
                        if fk_registry_entry:
                            # 3. Pega o display_field (ex: "nome_razao")
                            foreign_key_label_field = fk_registry_entry.get("display_field")
                        
                        if not foreign_key_label_field:
                            foreign_key_label_field = "id" # Fallback
                    except Exception:
                        foreign_key_label_field = "id" # Fallback

            # --- 3. LÓGICA DE TIPO (Agora respeitando a FK) ---
            field_type = "text" # Padrão
            options = None
            col_type = col.type
            
            # SÓ define os tipos se NÃO for uma FK (pois FK será tratada pelo AsyncSelect)
            if not foreign_key_model:
                # 0. Verifica se há um componente visual forçado no model (ex: creatable_select)
                if col.info.get('component'):
                    field_type = col.info.get('component')
                elif col.info.get('type'):
                    field_type = col.info.get('type')
                # 🎯 Adicionado para detectar o campo de regras e atribuir um tipo customizado
                elif isinstance(col_type, JSON) and col.name == 'regras':
                    field_type = "rule_builder"
                elif isinstance(col_type, JSON) and col.name == 'itens':
                    field_type = "order_items"
                elif isinstance(col_type, SQLAlchemyEnum):
                    field_type = "select"
                    if hasattr(col_type, 'python_type') and col_type.python_type:
                        options = [
                            {"label": getattr(item, 'description', item.name.replace('_', ' ').title()), "value": item.value}
                            for item in col_type.python_type
                        ]
                elif isinstance(col_type, (Integer, Numeric)):
                    field_type = "number"
                elif isinstance(col_type, Boolean):
                    field_type = "boolean"
                elif isinstance(col_type, DateTime):
                    field_type = "datetime" # Tipo específico
                elif isinstance(col_type, Date):
                    field_type = "date"     # Tipo específico
                elif isinstance(col_type, LargeBinary):
                    field_type = "file"     # Novo tipo para upload
                elif isinstance(col_type, String):
                    if "email" in col.name.lower():
                        field_type = "email"
                    else:
                        field_type = "text"
            
            # Se houver opções definidas manualmente no model (info), elas têm prioridade
            if col.info.get('options'):
                options = col.info.get('options')
            if col.info.get('available_fields'):
                options = col.info.get('available_fields')

            if col.name == "filtros_padrao":
                if model_name == "shopee_configuracoes":
                    options = [
                        {"label": "Status do Pedido", "value": "order_status", "type": "multiselect", "options": [
                            {"label": "Aguardando Pagamento (UNPAID)", "value": "UNPAID"},
                            {"label": "Pronto para Envio (READY_TO_SHIP)", "value": "READY_TO_SHIP"},
                            {"label": "Processado (PROCESSED)", "value": "PROCESSED"},
                            {"label": "Enviado (SHIPPED)", "value": "SHIPPED"},
                            {"label": "Concluído (COMPLETED)", "value": "COMPLETED"},
                            {"label": "Em Cancelamento (IN_CANCEL)", "value": "IN_CANCEL"},
                            {"label": "Cancelado (CANCELLED)", "value": "CANCELLED"},
                            {"label": "Devolução (TO_RETURN)", "value": "TO_RETURN"},
                        ]},
                        {"label": "Número do Pedido", "value": "order_sn", "type": "text"},
                        {"label": "Nome do Comprador", "value": "buyer_username", "type": "text"},
                        {"label": "Transportadora", "value": "shipping_carrier", "type": "text"},
                        {"label": "Código de Rastreio", "value": "tracking_number", "type": "text"},
                    ]
                elif model_name == "magento_configuracoes":
                    options = [
                        {"label": "Status do Pedido", "value": "status", "type": "multiselect", "options": [
                            {"label": "Pendente (pending)", "value": "pending"},
                            {"label": "Processando (processing)", "value": "processing"},
                            {"label": "Concluído (complete)", "value": "complete"},
                            {"label": "Fechado (closed)", "value": "closed"},
                            {"label": "Cancelado (canceled)", "value": "canceled"},
                            {"label": "Em Espera (holded)", "value": "holded"},
                        ]},
                        {"label": "Número do Pedido (Increment ID)", "value": "increment_id", "type": "text"},
                        {"label": "Nome do Cliente", "value": "customer_name", "type": "text"},
                        {"label": "E-mail do Cliente", "value": "customer_email", "type": "text"},
                        {"label": "Método de Pagamento", "value": "payment_method", "type": "text"},
                    ]
                elif model_name == "tiktok_configuracoes":
                    options = [
                        {"label": "Status do Pedido", "value": "order_status", "type": "multiselect", "options": [
                            {"label": "Aguardando Pagamento (UNPAID)", "value": "UNPAID"},
                            {"label": "Aguardando Envio (AWAITING_SHIPMENT)", "value": "AWAITING_SHIPMENT"},
                            {"label": "Aguardando Coleta (AWAITING_COLLECTION)", "value": "AWAITING_COLLECTION"},
                            {"label": "Em Trânsito (IN_TRANSIT)", "value": "IN_TRANSIT"},
                            {"label": "Entregue (DELIVERED)", "value": "DELIVERED"},
                            {"label": "Concluído (COMPLETED)", "value": "COMPLETED"},
                            {"label": "Cancelado (CANCELLED)", "value": "CANCELLED"},
                        ]},
                        {"label": "Número do Pedido", "value": "order_id", "type": "text"},
                        {"label": "Nome do Comprador", "value": "buyer_name", "type": "text"},
                        {"label": "Provedor de Envio", "value": "shipping_provider", "type": "text"},
                        {"label": "Código de Rastreio", "value": "tracking_number", "type": "text"},
                    ]
                elif model_name in ("meli_configuracoes", "meli_configuracao"):
                    options = [
                        {"label": "Status do Pedido", "value": "status", "type": "multiselect", "options": [
                            {"label": "Pago (paid)", "value": "paid"},
                            {"label": "Confirmado (confirmed)", "value": "confirmed"},
                            {"label": "Pagamento Solicitado (payment_required)", "value": "payment_required"},
                            {"label": "Em Processamento de Pagamento (payment_in_process)", "value": "payment_in_process"},
                            {"label": "Cancelado (cancelled)", "value": "cancelled"},
                        ]},
                        {"label": "Número do Pedido", "value": "id", "type": "text"},
                        {"label": "Apelido do Comprador", "value": "buyer_nickname", "type": "text"},
                        {"label": "Modo de Envio", "value": "shipping_mode", "type": "text"},
                    ]
            
            read_only = col.info.get('read_only', False)
            if col.name in ["criado_em", "atualizado_em", "id_sequencial"]:
                read_only = True
                if col.name == "id_sequencial":
                    label = col.info.get('label', "ID")
                    if col.info.get('visible') is not None:
                        visible = col.info.get('visible')
                    elif is_single_record:
                        visible = False
                    else:
                        visible = True
                    if not placeholder:
                        placeholder = "(Gerado automaticamente)"
                elif col.name in ["criado_em", "atualizado_em"]:
                    visible = False
            
            ui_type = col.info.get('ui_type')
            # Se não houver ui_type manual, mas o nome sugerir senha, define como password
            if not ui_type and ("senha" in col.name.lower() or "password" in col.name.lower()):
                ui_type = "password"

            # --- 3. CRIA O FIELDMETADATA (com a aba) ---
            field = FieldMetadata(
                name=col.name,
                label=label,
                placeholder=placeholder,
                type=field_type,
                required=required,
                options=options,
                default_value=default_value,
                format_mask=format_mask,
                tab=tab_name,
                sub_tab=sub_tab_name,
                foreign_key_model=foreign_key_model,
                foreign_key_label_field=foreign_key_label_field,
                filename_field=filename_field,
                col_span=col_span,
                read_only=read_only,
                visible=visible,
                ui_type=ui_type
            )
            fields.append(field)
            
        # --- NOVO: Adiciona campos das tabelas referenciadas (para filtros do dashboard) ---
        from sqlalchemy import inspect
        mapper = inspect(model)
        for rel in mapper.relationships:
            if rel.direction.name == 'MANYTOONE':
                related_model = rel.mapper.class_
                for rel_col in related_model.__table__.columns:
                    if rel_col.name in SKIPPED_FIELDS or "senha" in rel_col.name.lower() or "password" in rel_col.name.lower():
                        continue
                    
                    label = rel_col.info.get('label') or get_field_label(rel_col.name)
                    rel_label = get_field_label(rel.key)
                    label = f"{rel_label} - {label}"
                    
                    # Usa tipo select se for Enum, para manter as opções no front
                    rel_field_type = "text"
                    rel_options = None
                    if isinstance(rel_col.type, SQLAlchemyEnum) and hasattr(rel_col.type, 'python_type') and rel_col.type.python_type:
                        rel_field_type = "select"
                        rel_options = [
                            {"label": getattr(item, 'description', item.name.replace('_', ' ').title()), "value": item.value}
                            for item in rel_col.type.python_type
                        ]
                    
                    fields.append(FieldMetadata(
                        name=f"{rel.key}.{rel_col.name}",
                        label=label,
                        type=rel_field_type,
                        required=False,
                        options=rel_options,
                        tab="Relacionamentos",
                        visible=False
                    ))
            
        # 🎯 Adiciona campos virtuais para a visão de estoque
        if model_name == "estoque":
            fields.append(FieldMetadata(
                name="custo",
                label="Custo Unit.",
                type="number",
                required=False,
                format_mask="currency",
                visible=True,
                read_only=True,
                tab="Principal"
            ))
            fields.append(FieldMetadata(
                name="valor_total",
                label="Valor Total",
                type="number",
                required=False,
                format_mask="currency",
                visible=True,
                read_only=True,
                tab="Principal"
            ))

            
        return ModelMetadata(
            model_name=model_name,
            display_name=display_name,
            display_name_singular=registry_entry.get("display_name_singular", display_name),
            display_name_plural=registry_entry.get("display_name_plural", display_name),
            fields=fields,
            display_field=display_field,
            is_single_record=is_single_record
        )
    except Exception as e:
        # Adiciona um print para debug no console do backend
        print(f"Erro Crítico ao inspecionar modelo {model_name}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error inspecting model: {e}")