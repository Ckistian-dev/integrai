from sqlalchemy.orm import Session
from typing import List, Optional, Type, Any
from pydantic import BaseModel
from app.core.db.database import Base

ModelType = Type[Base] # Tipo para o modelo SQLAlchemy

def get(db: Session, *, model: ModelType, id: int, id_empresa: int) -> Optional[Base]:
    """Busca um item por ID, garantindo que pertença ao id_empresa."""
    return db.query(model).filter(
        model.id == id,
        model.id_empresa == id_empresa
    ).first()

def get_multi(
    db: Session, *, model: ModelType, id_empresa: int, skip: int = 0, limit: int = 100
) -> List[Base]:
    """Busca múltiplos itens, garantindo que pertençam ao id_empresa."""
    return db.query(model).filter(
        model.id_empresa == id_empresa
    ).offset(skip).limit(limit).all()

def create(db: Session, *, model: ModelType, obj_in: BaseModel, id_empresa: int) -> Base:
    """
    Cria um novo item, injetando o id_empresa.
    'obj_in' já deve ser um schema Pydantic validado.
    """
    obj_in_data = obj_in.model_dump()
    db_obj = model(**obj_in_data, id_empresa=id_empresa)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def update(
    db: Session, *, db_obj: Base, obj_in: BaseModel
) -> Base:
    """
    Atualiza um item. O db_obj já deve ter sido validado pelo id_empresa.
    'obj_in' já deve ser um schema Pydantic validado.
    """
    update_data = obj_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(db_obj, field, value)
            
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete(db: Session, *, model: ModelType, id: int, id_empresa: int) -> Optional[Base]:
    """Deleta um item, garantindo que pertença ao id_empresa."""
    obj = get(db, model=model, id=id, id_empresa=id_empresa)
    if obj:
        db.delete(obj)
        db.commit()
    return obj
