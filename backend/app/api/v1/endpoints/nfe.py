from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, Optional, List, Dict
from pydantic import BaseModel
import io

from app.core.db.database import get_db
from app.api.dependencies import get_current_active_user
from app.core.db import models
from app.core.service.nfe_service import NFeService
from app.core.logger import log_info, log_error, log_warning
from app.core.error_codes import NfeErrorCode, LogStatus

router = APIRouter()

class EmitirNFeRequest(BaseModel):
    id_regra_tributaria: Optional[int] = None
    itens: Optional[List[Any]] = None
    total_nota: Optional[float] = None
    data_vencimento: Optional[str] = None

class CancelarNFeRequest(BaseModel):
    justificativa: str

class CorrigirNFeRequest(BaseModel):
    correcao: str

class InutilizarNFeRequest(BaseModel):
    modelo: str = "55"
    serie: int
    numero_inicial: int
    numero_final: int
    ano: Optional[int] = None
    justificativa: str


@router.post("/nfe/emitir/{pedido_id}")
def emitir_nfe(
    pedido_id: int,
    payload: Optional[EmitirNFeRequest] = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
) -> Any:
    """
    Emite a NFe para um pedido específico usando PyNFE.
    """
    id_regra = payload.id_regra_tributaria if payload else None
    log_info("NFE", "nfe_endpoint", "emitir_nfe", LogStatus.PROCESSING,
             f"Recebida requisição de emissão de NF-e para o pedido #{pedido_id}",
             {"pedido_id": pedido_id, "id_regra_tributaria": id_regra, "id_empresa": current_user.id_empresa})
    service = NFeService(db, current_user.id_empresa)
    resultado = service.emitir_nfe(pedido_id, id_regra_tributaria=id_regra)
    log_info("NFE", "nfe_endpoint", "emitir_nfe", LogStatus.SUCCESS,
             f"Emissão de NF-e finalizada para o pedido #{pedido_id}", {"pedido_id": pedido_id})
    return resultado

@router.post("/nfe/devolucao/{pedido_id}")
def gerar_devolucao(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Gera um pedido de devolução e emite a NFe."""
    service = NFeService(db, current_user.id_empresa)
    return service.gerar_devolucao(pedido_id)

@router.post("/nfe/complemento/{pedido_id}")
def emitir_complemento(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera um pedido complementar duplicado na situação Faturamento.
    """
    service = NFeService(db, current_user.id_empresa)
    return service.gerar_complemento(pedido_id)

@router.post("/nfe/cancelar/{pedido_id}")
def cancelar_nfe(
    pedido_id: int,
    payload: CancelarNFeRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = NFeService(db, current_user.id_empresa)
    return service.cancelar_nfe(pedido_id, payload.justificativa)

@router.post("/nfe/corrigir/{pedido_id}")
def corrigir_nfe(
    pedido_id: int,
    payload: CorrigirNFeRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = NFeService(db, current_user.id_empresa)
    return service.corrigir_nfe(pedido_id, payload.correcao)

@router.get("/nfe/danfe/{pedido_id}")
def gerar_danfe(
    pedido_id: int,
    tipo: str = "completa",
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = NFeService(db, current_user.id_empresa)
    pdf_bytes = service.gerar_danfe_manual(pedido_id, tipo=tipo)
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=danfe_{pedido_id}.pdf"}
    )

@router.post("/nfe/danfe-lote")
def gerar_danfe_lote(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    pedido_ids = payload.get("pedido_ids", [])
    tipo = payload.get("tipo", "completa")
    service = NFeService(db, current_user.id_empresa)
    pdf_bytes = service.gerar_danfe_lote(pedido_ids, tipo=tipo)
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=danfes_lote.pdf"}
    )

@router.post("/nfe/inutilizar")
def inutilizar_nfe(
    payload: InutilizarNFeRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Inutiliza uma faixa de numeração de NF-e/NFC-e junto à SEFAZ.
    """
    service = NFeService(db, current_user.id_empresa)
    return service.inutilizar_numeracao(
        modelo=payload.modelo,
        serie=payload.serie,
        numero_inicial=payload.numero_inicial,
        numero_final=payload.numero_final,
        justificativa=payload.justificativa,
        ano=payload.ano,
        id_usuario=current_user.id
    )

@router.get("/nfe/inutilizacoes")
def listar_inutilizacoes(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Lista o histórico de inutilizações de numeração homologadas ou rejeitadas da empresa.
    """
    service = NFeService(db, current_user.id_empresa)
    return service.listar_inutilizacoes(limit=limit, offset=offset)
