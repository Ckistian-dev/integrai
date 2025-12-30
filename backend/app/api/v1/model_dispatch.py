import app.core.db.models as models
import app.core.db.schemas as schemas
from app.crud import crud_generic, crud_user
from typing import Dict, Any, Optional

def get_registry_entry(model_name: str) -> Optional[Dict[str, Any]]:
    """
    Busca (ou constrói dinamicamente) a entrada de registro para
    um nome de modelo, baseado em convenção de nomenclatura,
    incluindo regras para a singularização em Português (ex: -ões -> -ão).
    """
    
    # --- 1. APLICA A CONVENÇÃO E CRIA AS TENTATIVAS DE NOME ---
    
    singular_name = model_name
    
    # REGRA ESPECIAL: Trata palavras que terminam em 'ões' (sem acento: 'oes' ou 'coes')
    # Ex: 'tributacoes' -> 'tributacao'
    if model_name.endswith('coes'):
        singular_name = model_name.removesuffix('coes') + 'cao'
    elif model_name.endswith('ns'):
        singular_name = model_name.removesuffix('ns') + 'm'
    # REGRA GENÉRICA: Se terminar em 's' (e não foi tratada acima), remove o 's'
    elif model_name.endswith('s') and len(model_name) > 1:
        singular_name = model_name.rstrip('s')

    # Tentativa principal (User, Tributacao) - USADO PARA SCHEMAS
    primary_class_name = singular_name.capitalize()
    
    # Tentativa de fallback (Users, Tributacoes) - USADO APENAS PARA MODELO
    fallback_class_name = model_name.capitalize()
    
    # --- 2. BUSCA AS CLASSES DINAMICAMENTE (COM FALLBACK) ---
    
    # 2.1. Define a ordem de classes a tentar para o MODELO (models.py)
    class_name_attempts = [primary_class_name]
    if primary_class_name != fallback_class_name:
        class_name_attempts.append(fallback_class_name)
    
    model_class = None
    
    # 2.2. Tenta encontrar a classe do MODELO em models.py
    for attempt_name in class_name_attempts:
        try:
            model_class = getattr(models, attempt_name)
            # final_class_name = attempt_name # Não é mais necessário guardar
            break 
        except AttributeError:
            continue

    if model_class is None:
        print(f"Erro de convenção: Falha ao encontrar a classe de Modelo para '{model_name}'. Tentativas: {class_name_attempts}.")
        return None

    # 2.3. Busca os SCHEMAS usando o NOME PRINCIPAL/SINGULARIZADO
    # O Pydantic geralmente usa o nome singular: User, UserCreate, Tributacao, TributacaoCreate
    try:
        schema_class = getattr(schemas, primary_class_name)
        create_schema_class = getattr(schemas, f"{primary_class_name}Create")
        update_schema_class = getattr(schemas, f"{primary_class_name}Update")

        # --- 3. GERA O DISPLAY_NAME AUTOMATICAMENTE ---
        table_name = model_class.__tablename__
        
        # Aplicar a lógica de singularização baseada na convenção (já existente):
        singular_table_name = table_name

        # REGRA ESPECIAL: Trata 'acoes' (deve ser tratado no model_name, mas para garantir a tabela)
        if table_name.endswith('coes'):
            singular_table_name = table_name.removesuffix('coes') + 'cao'
        elif table_name.endswith('ns'):
            singular_table_name = table_name.removesuffix('ns') + 'm'
        # REGRA GENÉRICA: Se terminar em 's' (e não foi tratada acima), remove o 's'
        elif table_name.endswith('s') and len(table_name) > 1:
            singular_table_name = table_name.rstrip('s')

        # Define o nome de exibição **SINGULAR** (o que você já estava usando)
        display_name_singular = singular_table_name.replace("_", " ").capitalize()
        
        
        # **************** INÍCIO DA CORREÇÃO DA PLURALIZAÇÃO ****************
        # 1. Define o plural como o nome da tabela capitalizado por padrão (Ex: Users)
        display_name_plural = table_name.replace("_", " ").capitalize()
        
        # 2. CASO ESPECIAL 'ÕES' (que viraram 'coes' / 'cao')
        if table_name.endswith('coes'):
            # Recria o plural com o acento correto (Ex: Tributa + ções)
            display_name_plural = table_name.removesuffix('coes') + 'ções' 
            display_name_plural = display_name_plural.capitalize() # Garante a capitalização (Ex: Tributações)
            
        
        # O display_name original agora aponta para o singular
        display_name = display_name_singular
        
        # **************** FIM DA CORREÇÃO DA PLURALIZAÇÃO ****************

        # 🎯 2. LÓGICA PARA DETERMINAR O DISPLAY_FIELD DINAMICAMENTE
        # Lista de nomes preferenciais em ordem de prioridade
        PREFERRED_DISPLAY_FIELDS = [
            "nome_razao",  # (ex: Cadastros)
            "fantasia",    # (ex: Empresa, Cadastros)
            "nome",        # (ex: Usuario)
            "descricao",   # (ex: Produto, Embalagem, Regra Tributaria)
            "razao",       # (ex: Empresa)
            "sku",         # (ex: Produto)
            "email"        # (ex: Usuario)
        ]
        
        # Pega todas as colunas do modelo
        model_columns = [c.name for c in model_class.__table__.columns]
        
        display_field = None
        
        # Encontra o primeiro campo preferencial que existe no modelo
        for field_name in PREFERRED_DISPLAY_FIELDS:
            if field_name in model_columns:
                display_field = field_name
                break
                
        # Fallback: Se nenhum campo preferencial for encontrado, usa 'id'
        if display_field is None:
            display_field = "id" 
        
        # 🎯 3. LÓGICA PARA DETERMINAR O CRUD (CORRIGINDO O BUG)
        crud_service = crud_generic
        if model_name == "usuarios":
            crud_service = crud_user

        # --- 4. RETORNA O DICIONÁRIO COMPLETO ---
        return {
            "model": model_class,
            "schema": schema_class,
            "create_schema": create_schema_class,
            "update_schema": update_schema_class,
            "crud": crud_service,
            "display_name": display_name,
            "display_name_singular": display_name_singular,
            "display_name_plural": display_name_plural,
            "display_field": display_field,
        }
    
    except AttributeError as e:
        # Se o Schema não for encontrado (ex: 'TributacaoCreate' não existe)
        print(f"Erro de convenção: Falha ao encontrar Schemas para o modelo '{model_name}' (usando o nome '{primary_class_name}').")
        print(f"Classe/Atributo faltando: {e}")
        return None
    except Exception as e:
        print(f"Erro inesperado ao construir registro para {model_name}: {e}")
        return None