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
    if col_name.lower() == "id":
        return "ID"
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
SKIPPED_FIELDS = ["id_empresa"]

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

    registry_entry = get_registry_entry(model_name)
    if not registry_entry:
        raise HTTPException(status_code=404, detail="Model not found")

    model = registry_entry["model"]
    display_name = registry_entry["display_name"]
    display_field = registry_entry.get("display_field", None)
    fields: List[FieldMetadata] = []
    
    

    try:
        
        # Inspeciona as colunas do modelo SQLAlchemy
        for col in model.__table__.columns:
            if col.name in SKIPPED_FIELDS:
                continue
            
            tab_name = col.info.get('tab', 'Dados Gerais')
            
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
            
            required = not col.nullable and not col.primary_key
            
            foreign_key_model = None
            foreign_key_label_field = None
            filename_field = col.info.get('filename_field')
            col_span = col.info.get('col_span')
            visible = col.info.get('visible', True)
            
            if col.foreign_keys:
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
            
            read_only = col.info.get('read_only', False)
            if col.name in ["criado_em", "atualizado_em"]:
                read_only = True
                visible = False

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
                foreign_key_model=foreign_key_model,
                foreign_key_label_field=foreign_key_label_field,
                filename_field=filename_field,
                col_span=col_span,
                read_only=read_only,
                visible=visible
            )
            fields.append(field)
            
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
            fields=fields,
            display_field=display_field
        )
    except Exception as e:
        # Adiciona um print para debug no console do backend
        print(f"Erro Crítico ao inspecionar modelo {model_name}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error inspecting model: {e}")