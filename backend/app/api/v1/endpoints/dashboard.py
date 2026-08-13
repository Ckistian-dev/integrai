from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, case, cast, String, Date, and_, or_, DateTime, inspect
from datetime import date, timedelta, datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal
import json
from pydantic import BaseModel

from app.core.db import models, database
from app.core.db.schemas import DashboardPreferenciaUpdate, CardQuery
from app.api.v1.endpoints.generic import apply_search_filter
from app.api.v1.model_dispatch import get_registry_entry
from app.api.dependencies import get_current_active_user

class DynamicSeries(BaseModel):
    id: str
    nome: Optional[str] = None
    tipo: Optional[str] = None
    campo: Optional[str] = None
    operacao: Optional[str] = "sum"
    formato: Optional[str] = "numero"
    is_meta: Optional[bool] = False
    valor_meta: Optional[float] = None
    meta_progressiva: Optional[bool] = False
    cor: Optional[str] = None

class DynamicCardQuery(BaseModel):
    modelo: str
    campo: Optional[str] = "id"
    campo2: Optional[str] = None
    agrupar_por: Optional[str] = ""
    operacao: Optional[str] = "count"
    tipo: str
    colunas: Optional[List[str]] = []
    filtros: Optional[List[Dict[str, Any]]] = []
    series: Optional[List[DynamicSeries]] = []
    search_term: Optional[str] = None
    eixo_x_nome: Optional[str] = None
    eixo_x_formato: Optional[str] = None
    eixo_x_cor: Optional[str] = None
    eixo_x_preencher_vazio: Optional[bool] = False

router = APIRouter()

# ==============================================================================
# ROTAS DO DASHBOARD DINÂMICO
# ==============================================================================

@router.get("/dashboard/custom/preferences")
def get_dashboard_preferences(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Busca as configurações salvas do dashboard customizado da empresa."""
    prefs = db.query(models.DashboardPreferencia).filter(
        models.DashboardPreferencia.id_empresa == current_user.id_empresa
    ).first()

    if not prefs:
        # Retorna um layout padrão vazio se for o primeiro acesso
        return {"layout": [], "cards_config": {}}
    
    return {"layout": prefs.layout, "cards_config": prefs.cards_config}

@router.put("/dashboard/custom/preferences")
def update_dashboard_preferences(
    data: DashboardPreferenciaUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Salva ou atualiza a disposição e configuração dos cards para a empresa."""
    prefs = db.query(models.DashboardPreferencia).filter(
        models.DashboardPreferencia.id_empresa == current_user.id_empresa
    ).first()

    if not prefs:
        user_id_seq = current_user.id_sequencial if getattr(current_user, 'id_sequencial', None) is not None else current_user.id
        prefs = models.DashboardPreferencia(
            id_usuario=user_id_seq,
            id_empresa=current_user.id_empresa,
            layout=data.layout,
            cards_config=data.cards_config
        )
        db.add(prefs)
    else:
        prefs.layout = data.layout
        prefs.cards_config = data.cards_config
    
    db.commit()
    return {"message": "Dashboard atualizado com sucesso"}

def resolve_model_field(model, field_path: str, joined_rels: dict, db_query):
    """
    Resolve um caminho de campo (ex: 'id_cliente' ou 'cliente.nome_razao')
    retornando a coluna SQLAlchemy correspondente e a query com os joins necessários.
    Prioriza id_sequencial quando o campo for 'id'.
    """
    if not field_path:
        return None, db_query

    target_field = field_path
    if target_field == "id" and hasattr(model, "id_sequencial"):
        target_field = "id_sequencial"

    if "." in field_path:
        rel_name, col_name = field_path.split(".", 1)
        mapper = inspect(model)
        rel = mapper.relationships.get(rel_name)
        if rel:
            related_model = rel.mapper.class_
            if col_name == "id" and hasattr(related_model, "id_sequencial"):
                col_name = "id_sequencial"
            if hasattr(related_model, col_name):
                if rel_name not in joined_rels:
                    rel_alias = aliased(related_model, name=f"join_{rel_name}")
                    db_query = db_query.outerjoin(rel_alias, getattr(model, rel_name))
                    joined_rels[rel_name] = rel_alias
                else:
                    rel_alias = joined_rels[rel_name]
                return getattr(rel_alias, col_name), db_query
            else:
                return None, db_query
        else:
            return None, db_query
    else:
        if hasattr(model, target_field):
            return getattr(model, target_field), db_query
        elif hasattr(model, field_path):
            return getattr(model, field_path), db_query
        return None, db_query

@router.post("/dashboard/custom/data")
def get_dynamic_card_data(
    query: DynamicCardQuery,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Processa a query dinâmica de um card específico baseado na sua configuração.
    Usa o model_dispatch para acessar qualquer tabela do ERP.
    """
    registry = get_registry_entry(query.modelo)
    if not registry:
        raise HTTPException(status_code=400, detail=f"Modelo '{query.modelo}' não encontrado.")
        
    model = registry["model"]
    
    # Inicia a Query base isolando o tenant (empresa)
    db_query = db.query(model).filter(model.id_empresa == current_user.id_empresa)
    
    search_term = getattr(query, 'search_term', None)
    sort_by = 'id'
    sort_order = 'desc'
    joined_rels = {}

    # Validação e Resolução do Campo Alvo Principal
    target_col, db_query = resolve_model_field(model, query.campo, joined_rels, db_query)
    if target_col is None:
        raise HTTPException(status_code=400, detail=f"A coluna '{query.campo}' não existe no modelo '{query.modelo}' ou em seus relacionamentos.")
        
    if query.agrupar_por:
        # Validação do campo de agrupamento (sem modificar a query principal ainda)
        temp_group_col, _ = resolve_model_field(model, query.agrupar_por, {}, db_query)
        if temp_group_col is None:
            raise HTTPException(status_code=400, detail=f"A coluna de agrupamento '{query.agrupar_por}' não existe no modelo '{query.modelo}' ou em seus relacionamentos.")

    # --- Aplicação de Filtros (Opcional, similar ao Relatórios/GenericList) ---
    if query.filtros:
        for f in query.filtros:
            field_name = f.get("field")
            operator = f.get("operator")
            value = f.get("value")
            
            if field_name == '__search__':
                search_term = value
                continue
                
            if field_name == '__sort__':
                sort_by = value
                sort_order = operator
                continue

            if not field_name:
                continue

            attr, db_query = resolve_model_field(model, field_name, joined_rels, db_query)
            if attr is None:
                continue
                
            if operator == "equals":
                if isinstance(value, str) and "," in value:
                    vals = [v.strip() for v in value.split(",")]
                    db_query = db_query.filter(attr.in_(vals))
                else:
                    db_query = db_query.filter(attr == value)
            elif operator == "contains":
                db_query = db_query.filter(cast(attr, String).ilike(f"%{value}%"))
            elif operator == "gt": db_query = db_query.filter(attr > value)
            elif operator == "lt": db_query = db_query.filter(attr < value)
            elif operator == "gte": db_query = db_query.filter(attr >= value)
            elif operator == "lte": db_query = db_query.filter(attr <= value)
            elif operator == "date_range":
                if isinstance(value, str) and "," in value:
                    start_d, end_d = value.split(",", 1)
                    start_d = start_d.strip()
                    end_d = end_d.strip()
                    if start_d:
                        db_query = db_query.filter(cast(attr, Date) >= start_d)
                    if end_d:
                        db_query = db_query.filter(cast(attr, Date) <= end_d)
            elif operator == "today":
                db_query = db_query.filter(cast(attr, Date) == date.today())
            elif operator == "last_days":
                try: days = int(value)
                except: days = 30
                hoje = date.today()
                db_query = db_query.filter(and_(cast(attr, Date) >= hoje - timedelta(days=days), cast(attr, Date) <= hoje))

    # --- Aplica a Busca Global (Mesma inteligência do GenericList) ---
    if search_term:
        db_query = apply_search_filter(db_query, model, search_term)

    # --- LÓGICA: CARD DE VALOR ÚNICO (Metric) ---
    if query.tipo == "metrica":
        if query.operacao == "sum":
            agg_func = func.sum(target_col)
        elif query.operacao == "avg":
            agg_func = func.avg(target_col)
        else: # Default é COUNT
            # Evita contar colunas vazias se não for o ID
            agg_func = func.count(target_col)
            
        resultado = db_query.with_entities(agg_func).scalar()
        return {"value": float(resultado or 0)}

    # --- LÓGICA: CARD DE GRÁFICO (Pizza, Barra, Linha, Area, Composed) ---
    elif query.tipo in ["pizza", "barra", "linha", "area", "composed"]:
        if not query.agrupar_por:
            raise HTTPException(status_code=400, detail="Gráficos exigem a definição de um campo 'agrupar_por'.")
             
        group_col, db_query = resolve_model_field(model, query.agrupar_por, joined_rels, db_query)
        
        # --- Lógica para substituir FK pelo nome de exibição ---
        if "." not in query.agrupar_por:
            mapper = inspect(model)
            column = model.__table__.columns.get(query.agrupar_por)
            if column is not None and column.foreign_keys:
                rel = next((r for r in mapper.relationships if column in r.local_columns and r.direction.name == 'MANYTOONE'), None)
                if rel:
                    related_model = rel.mapper.class_
                    PREFERRED_DISPLAY_FIELDS = ["nome_razao", "fantasia", "nome", "descricao", "razao", "sku", "email", "titulo", "increment_id", "id_sequencial"]
                    display_field = next((f for f in PREFERRED_DISPLAY_FIELDS if hasattr(related_model, f)), None)
                    
                    if display_field:
                        rel_name = rel.key
                        if rel_name not in joined_rels:
                            rel_alias = aliased(related_model, name=f"fk_group_{rel_name}")
                            db_query = db_query.outerjoin(rel_alias, getattr(model, rel_name))
                            joined_rels[rel_name] = rel_alias
                        else:
                            rel_alias = joined_rels[rel_name]
                        group_col = getattr(rel_alias, display_field)
        
        # Se for uma coluna do tipo DateTime (direto ou via relacionamento), converte para Date
        try:
            if hasattr(group_col, 'type') and isinstance(group_col.type, DateTime):
                group_col = cast(group_col, Date)
        except:
            pass
        
        agg_funcs = []
        series_ids = []
        
        # --- Nova Lógica: Séries Dinâmicas ---
        if getattr(query, 'series', None) and len(query.series) > 0:
            for s in query.series:
                if s.is_meta:
                    continue # Metas fixas não entram na query SQL
                if not s.campo:
                    continue
                
                s_col, db_query = resolve_model_field(model, s.campo, joined_rels, db_query)
                if s_col is None:
                    continue
                
                op = s.operacao
                if op == 'cumulative_sum':
                    op = 'sum' # Acumulação feita pelo frontend
                    
                if op == "sum": agg_funcs.append(func.sum(s_col).label(s.id))
                elif op == "avg": agg_funcs.append(func.avg(s_col).label(s.id))
                else: agg_funcs.append(func.count(s_col).label(s.id))
                
                series_ids.append(s.id)
        else:
            # --- Lógica Legada (Compatibilidade) ---
            target_cols = []
            if getattr(query, 'colunas', None) and len(query.colunas) > 0:
                for c in query.colunas:
                    c_col, db_query = resolve_model_field(model, c, joined_rels, db_query)
                    if c_col is not None:
                        target_cols.append(c_col)
            if not target_cols: target_cols = [target_col]
                
            for i, t_col in enumerate(target_cols):
                if query.operacao == "sum": agg_funcs.append(func.sum(t_col).label(f"value{i}"))
                elif query.operacao == "avg": agg_funcs.append(func.avg(t_col).label(f"value{i}"))
                else: agg_funcs.append(func.count(t_col).label(f"value{i}"))
                series_ids.append(f"value{i}")
                
        if not agg_funcs:
            return []
            
        entities = [group_col.label("name")]
        entities.extend(agg_funcs)
            
        # Ordenação Cronológica se for data para gráficos de crescimento, senão decrescente
        is_date = False
        try:
            if hasattr(group_col, 'type') and hasattr(group_col.type, 'python_type'):
                is_date = group_col.type.python_type in (date, datetime)
        except: pass
        
        # Tenta achar o range de data para preencher
        start_d, end_d = None, None
        if getattr(query, 'eixo_x_preencher_vazio', False):
            for f in getattr(query, 'filtros', []):
                if f.get("operator") == "date_range":
                    val = f.get("value")
                    if isinstance(val, str) and "," in val:
                        s, e = val.split(",", 1)
                        try:
                            if s: start_d = date.fromisoformat(s.strip()[:10])
                            if e: end_d = date.fromisoformat(e.strip()[:10])
                        except ValueError: pass
                        break
                elif f.get("operator") == "last_days":
                    try: days = int(f.get("value"))
                    except: days = 30
                    end_d = date.today()
                    start_d = end_d - timedelta(days=days)
                    break
                elif f.get("operator") == "today":
                    start_d = date.today()
                    end_d = date.today()
                    break

        if is_date or "data" in query.agrupar_por.lower() or "criado" in query.agrupar_por.lower():
            order_func = group_col.asc()
        else:
            order_func = agg_funcs[0].desc()
            
        resultados = db_query.with_entities(*entities).group_by(group_col).order_by(order_func).all()
        
        formatted_results = []
        results_dict = {}
        for r in resultados:
            nome = r.name
            if hasattr(nome, 'value'): nome = nome.value
            if isinstance(nome, datetime): nome = nome.date() # Normaliza para garantir conversão
            if isinstance(nome, date): nome = nome.isoformat()
            
            res_item = {"name": str(nome) if nome is not None else "Sem Categoria"}
            for s_id in series_ids:
                res_item[s_id] = float(getattr(r, s_id) or 0)
                
            # Fallback frontend antigo
            if not getattr(query, 'series', None) and len(series_ids) > 0:
                res_item["value"] = res_item[series_ids[0]]
                if len(series_ids) > 1:
                    res_item["value2"] = res_item[series_ids[1]]
                    
            results_dict[res_item["name"]] = res_item
            formatted_results.append(res_item)
            
        # Se for para preencher o vazio e estamos lidando com datas
        if getattr(query, 'eixo_x_preencher_vazio', False) and (is_date or "data" in query.agrupar_por.lower() or "criado" in query.agrupar_por.lower()):
            # Se o usuário não enviou no filtro, inferimos das datas presentes
            if not start_d and not end_d and formatted_results:
                dates = []
                for r in formatted_results:
                    if r["name"] != "Sem Categoria" and "-" in r["name"]:
                        try: dates.append(date.fromisoformat(r["name"][:10]))
                        except ValueError: pass
                if dates:
                    start_d = min(dates)
                    end_d = max(dates)
            
            if start_d and end_d:
                filled_results = []
                delta = timedelta(days=1)
                curr_d = start_d
                
                # Limite de segurança de 10 anos (3650 dias) para não travar a aplicação/gráfico
                if (end_d - start_d).days > 3650:
                    start_d = end_d - timedelta(days=3650)
                    curr_d = start_d
                
                while curr_d <= end_d:
                    d_iso = curr_d.isoformat()
                    if d_iso in results_dict:
                        filled_results.append(results_dict[d_iso])
                    else:
                        empty_item = {"name": d_iso}
                        for s_id in series_ids:
                            empty_item[s_id] = 0.0
                        if not getattr(query, 'series', None) and len(series_ids) > 0:
                            empty_item["value"] = 0.0
                            if len(series_ids) > 1:
                                empty_item["value2"] = 0.0
                        filled_results.append(empty_item)
                    curr_d += delta
                return filled_results

        return formatted_results

    # --- LÓGICA: CARD DE TABELA ---
    elif query.tipo == "tabela":
        effective_sort_by = sort_by
        if effective_sort_by == 'id' and hasattr(model, 'id_sequencial'):
            effective_sort_by = 'id_sequencial'

        if hasattr(model, effective_sort_by):
            sort_col = getattr(model, effective_sort_by)
            if sort_order == 'asc':
                db_query = db_query.order_by(sort_col.asc())
            else:
                db_query = db_query.order_by(sort_col.desc())
        elif hasattr(model, "id_sequencial"):
            db_query = db_query.order_by(model.id_sequencial.desc())
        else:
            db_query = db_query.order_by(model.id.desc())
            
        resultados = db_query.all()
        formatted_results = []
        
        schema = registry.get("schema")
        for r in resultados:
            # Converte usando o schema Pydantic se existir, senão pega direto das colunas
            if schema:
                data = schema.from_orm(r).model_dump() if hasattr(schema, 'model_dump') else schema.from_orm(r).dict()
            else:
                data = {c.name: getattr(r, c.name) for c in model.__table__.columns}

            if hasattr(r, 'id_sequencial') and getattr(r, 'id_sequencial', None) is not None:
                data['id_sequencial'] = getattr(r, 'id_sequencial')
            
            # Filtra apenas as colunas solicitadas
            if query.colunas:
                data = {k: v for k, v in data.items() if k in query.colunas or k == "id" or k == "id_sequencial"}
                
            # Formatação segura para JSON (Converte Enums e Decimals)
            for k, v in data.items():
                if hasattr(v, 'value'): data[k] = v.value
                elif isinstance(v, Decimal): data[k] = float(v)
                elif isinstance(v, date): data[k] = v.isoformat()
                
            formatted_results.append(data)
            
        return formatted_results