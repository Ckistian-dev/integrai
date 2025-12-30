from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import StreamingResponse # Importar StreamingResponse
import io # Importar io
import csv # Importar csv
from sqlalchemy.orm import Session
from sqlalchemy import or_, String, cast, func
from sqlalchemy.types import Text, Enum 
from typing import List, Any, Dict

from app.api.dependencies import get_current_active_user
from app.core.db import models, database, schemas
from app.api.v1.model_dispatch import get_registry_entry

from app.crud import crud_user
from app.api.dependencies import get_current_active_user

router = APIRouter()

# --- Endpoint de Listagem (GET) ---
@router.get("/generic/{model_name}", response_model=schemas.Page)
def list_items(
    model_name: str,
    db: Session = Depends(database.get_db),
    skip: int = 0,
    limit: int = 10,
    search_term: str = None,
    situacao: str = None,
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Lista itens paginados de um modelo para o business do usuário,
    com filtro de busca opcional.
    """
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # 1. Monta a query base
    base_query = db.query(registry["model"]).filter(
        registry["model"].id_empresa == current_user.id_empresa
    )
    
    if situacao:
        # Verifica se o modelo realmente tem a coluna "situacao"
        if hasattr(registry["model"], "situacao"):
            base_query = base_query.filter(registry["model"].situacao == situacao)
    
    # 2. Aplica o filtro de busca (NOVO)
    if search_term:
        
        NON_SEARCHABLE_FIELDS = [
            "id", 
            "id_empresa", 
            "criado_em", 
            "atualizado_em", 
            "senha", 
            "hashed_password"
        ]

        filter_conditions = []
        
        # 🎯 Prepara o termo de busca para o ILIKE
        search_pattern = f"%{search_term}%"
        
        for col in registry["model"].__table__.columns:
            
            if col.name in NON_SEARCHABLE_FIELDS:
                continue

            column_attr = getattr(registry["model"], col.name)
            
            # 🎯 CORREÇÃO:
            # 1. Converte a coluna para String (cast)
            # 2. Aplica unaccent() NA COLUNA
            # 3. Aplica unaccent() NO TERMO DE BUSCA
            filter_conditions.append(
                func.unaccent(cast(column_attr, String)).ilike(func.unaccent(search_pattern))
            )
        
        if filter_conditions:
            base_query = base_query.filter(or_(*filter_conditions))

    # 3. Obter a contagem total (AGORA VEM DA QUERY FILTRADA)
    total_count = base_query.count()
    
    # 4. Obter os itens paginados (APLICA OFFSET E LIMIT DEPOIS DO FILTRO)
    items = base_query.offset(skip).limit(limit).all()
    
    # 5. Serializar os itens
    serialized_items = [registry["schema"].from_orm(item) for item in items]
    
    # 6. Retornar no formato de página
    return {"items": serialized_items, "total_count": total_count}

@router.get("/generic/{model_name}/export")
def export_items_to_csv(
    model_name: str,
    db: Session = Depends(database.get_db),
    search_term: str = None,
    situacao: str = None,
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Exporta TODOS os itens (filtrados pelo search_term, se houver)
    para um arquivo CSV.
    """
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")

    # 1. Monta a query base (igual à listagem)
    base_query = db.query(registry["model"]).filter(
        registry["model"].id_empresa == current_user.id_empresa
    )

    if situacao:
        if hasattr(registry["model"], "situacao"):
            base_query = base_query.filter(registry["model"].situacao == situacao)

    # 2. Aplica o filtro de busca (igual à listagem)
    if search_term:
        
        NON_SEARCHABLE_FIELDS = [
            "id", 
            "id_empresa", 
            "criado_em", 
            "atualizado_em", 
            "senha", 
            "hashed_password"
        ]

        filter_conditions = []
        
        # 🎯 Prepara o termo de busca para o ILIKE
        search_pattern = f"%{search_term}%"

        for col in registry["model"].__table__.columns:
            
            if col.name in NON_SEARCHABLE_FIELDS:
                continue

            column_attr = getattr(registry["model"], col.name)
            
            # 🎯 CORREÇÃO (igual ao list_items)
            filter_conditions.append(
                func.unaccent(cast(column_attr, String)).ilike(func.unaccent(search_pattern))
            )
        
        if filter_conditions:
            base_query = base_query.filter(or_(*filter_conditions))

    # 3. Busca TODOS os itens (sem paginação)
    items = base_query.all()

    # Define os campos que não queremos no CSV (campos internos)
    SKIPPED_FIELDS = ["id_empresa", "hashed_password"]
    
    # Pega os cabeçalhos do modelo, pulando os campos internos
    headers = [
        col.name for col in registry["model"].__table__.columns 
        if col.name not in SKIPPED_FIELDS
    ]

    # Cria um buffer de string na memória
    output = io.StringIO()
    writer = csv.writer(output)

    # Escreve o cabeçalho
    writer.writerow(headers)

    # Escreve as linhas de dados
    for item in items:
        row = [getattr(item, h, "") for h in headers]
        writer.writerow(row)

    # Prepara o nome do arquivo
    filename = f"{model_name}_export_{current_user.id_empresa}.csv"
    
    # Retorna uma StreamingResponse
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- Endpoint de Criação (POST) ---
@router.post("/generic/{model_name}", response_model=Any)
def create_item(
    model_name: str,
    item_data: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Cria um novo item, validando com o schema de criação."""
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")

    try:
        CreateSchema = registry["create_schema"]
        validated_data = CreateSchema(**item_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}")

    # 🎯 CORREÇÃO PARA HASH DE SENHA NA CRIAÇÃO
    if model_name == "usuarios":
        # 1. Adiciona o id_empresa do usuário logado aos dados validados
        #    (O crud_user.create_user espera isso dentro do obj_in)
        validated_data.id_empresa = current_user.id_empresa

        # 2. Chama a função específica que SABE fazer o hash da senha
        item = crud_user.create_user(
            db=db,
            obj_in=validated_data
        )
    else:
        # 3. Para todos os outros modelos, usa o CRUD genérico
        item = registry["crud"].create(
            db,
            model=registry["model"], # Passa o modelo
            obj_in=validated_data,
            id_empresa=current_user.id_empresa
        )

    return registry["schema"].from_orm(item)

# --- Endpoint de Detalhe (GET by ID) ---
@router.get("/generic/{model_name}/{id}", response_model=Any)
def read_item(
    model_name: str,
    id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Busca um item específico pelo ID."""
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")
        
    # CORREÇÃO: Chama a função crud_generic.get
    item = registry["crud"].get(
        db, 
        model=registry["model"], # Passa o modelo
        id=id, 
        id_empresa=current_user.id_empresa
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    return registry["schema"].from_orm(item)

# --- Endpoint de Atualização (PUT) ---
@router.put("/generic/{model_name}/{id}", response_model=Any)
def update_item(
    model_name: str,
    id: int,
    item_data: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Atualiza um item."""
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")

    # Busca o objeto existente
    db_obj = registry["crud"].get(
        db,
        model=registry["model"],
        id=id,
        id_empresa=current_user.id_empresa
    )
    if not db_obj:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        UpdateSchema = registry["update_schema"]
        validated_data = UpdateSchema(**item_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}")

    # 🎯 CORREÇÃO PARA HASH DE SENHA NA ATUALIZAÇÃO
    if model_name == "usuarios":
        # 1. Chama a função específica que SABE fazer o hash da senha
        item = crud_user.update_user(
            db=db,
            db_obj=db_obj,      # O objeto de usuário que já buscamos
            obj_in=validated_data # Os dados validados (Pydantic schema)
        )
    else:
        # 2. Para todos os outros modelos, usa o CRUD genérico
        item = registry["crud"].update(
            db,
            db_obj=db_obj,
            obj_in=validated_data
        )

    return registry["schema"].from_orm(item)

# --- Endpoint de Deleção (DELETE) ---
@router.delete("/generic/{model_name}/{id}", response_model=Any)
def delete_item(
    model_name: str,
    id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Deleta um item."""
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")
        
    # CORREÇÃO: Chama a função crud_generic.delete
    item = registry["crud"].delete(
        db, 
        model=registry["model"], # Passa o modelo
        id=id, 
        id_empresa=current_user.id_empresa
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    return registry["schema"].from_orm(item)
