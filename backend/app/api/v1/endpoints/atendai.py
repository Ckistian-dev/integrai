from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.core.db import database, models
from app.core.service.atendai_service import AtendaiService

router = APIRouter()


@router.post("/atendai/sync")
def sync_atendai_pedidos(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Sincroniza todos os pedidos da empresa com a URL webhook do AtendAI.
    """
    atendai_svc = AtendaiService(db, current_user.id_empresa)
    res = atendai_svc.sync_all_orders()
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("message", "Falha ao sincronizar pedidos com o AtendAI.")
        )
    return res
