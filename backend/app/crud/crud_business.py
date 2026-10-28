from sqlalchemy.orm import Session
from typing import Optional

from app.core.db import models
from app.core.db.schemas import EmpresaCreate, EmpresaUpdate # Mantemos schemas para tipagem
from app.core.logger import log_info, log_error, log_warning
from app.core.error_codes import GenericErrorCode, LogStatus

def get_business(db: Session, *, id_empresa: int) -> Optional[models.Empresa]:
    """
    Busca uma empresa específica pelo ID.
    (Esta função não usa mais uma classe)
    """
    return db.query(models.Empresa).filter(models.Empresa.id == id_empresa).first()

# Adicione outras funções de 'business' aqui se precisar
# (ex: create_business, update_business, etc.)
#
# def create_business(db: Session, *, obj_in: EmpresaCreate) -> models.Empresa:
#     db_obj = models.Empresa(**obj_in.model_dump())
#     db.add(db_obj)
#     db.commit()
#     db.refresh(db_obj)
#     return db_obj

