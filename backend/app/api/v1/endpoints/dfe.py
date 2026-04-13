from fastapi import APIRouter, Depends, HTTPException, Body, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from app.core.db import database, models
from app.api.dependencies import get_current_active_user
from app.core.service.nfe_service import NFeService
from lxml import etree
from typing import List, Dict, Any
from fastapi.responses import Response

router = APIRouter()

@router.post("/sync")
async def sync_dfe(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Busca novos documentos destinados no Web Service da SEFAZ."""
    service = NFeService(db, current_user.id_empresa)
    return service.sincronizar_dfe()

@router.post("/manifest/{nota_id}")
async def manifest_dfe(
    nota_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Envia evento de Ciência da Operação para liberar o download do XML completo."""
    service = NFeService(db, current_user.id_empresa)
    return service.manifestar_ciencia(nota_id)

@router.get("/detalhes/{nota_id}")
async def get_detalhes(
    nota_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Lê o XML completo da nota recebida e prepara os dados para o modal de importação."""
    nota = db.query(models.NotaFiscalRecebida).filter(
        models.NotaFiscalRecebida.id == nota_id,
        models.NotaFiscalRecebida.id_empresa == current_user.id_empresa
    ).first()
    
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    
    if not nota.xml_completo:
        raise HTTPException(status_code=400, detail="XML completo ainda não disponível. Realize a Ciência da Operação e aguarde a próxima sincronização.")

    if nota.tipo_documento != "nfeProc":
        raise HTTPException(status_code=400, detail=f"O documento selecionado é um {nota.tipo_documento} e não contém itens de produtos.")

    try:
        root = etree.fromstring(nota.xml_completo.encode('utf-8'))
        ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
        
        items = []
        detalhes_nos = root.xpath('//ns:det', namespaces=ns)
        
        for det in detalhes_nos:
            prod = det.xpath('ns:prod', namespaces=ns)[0]
            sku_forn = prod.xpath('ns:cProd', namespaces=ns)[0].text
            x_prod = prod.xpath('ns:xProd', namespaces=ns)[0].text
            q_com = prod.xpath('ns:qCom', namespaces=ns)[0].text
            
            # Tenta encontrar produto no ERP que já tenha esse SKU do fornecedor nas 'variacoes'
            produto_erp = db.query(models.Produto).filter(
                models.Produto.id_empresa == current_user.id_empresa,
                cast(models.Produto.variacoes, String).contains(f'"{sku_forn}"')
            ).first()
            
            items.append({
                "sku_fornecedor": sku_forn,
                "descricao": x_prod,
                "quantidade": float(q_com),
                "id_produto_erp": produto_erp.id if produto_erp else None
            })
            
        tPag_nodes = root.xpath('//ns:pag/ns:detPag/ns:tPag', namespaces=ns)
        forma_pagamento_xml = tPag_nodes[0].text if tPag_nodes else "90"
        return {"itens": items, "forma_pagamento": forma_pagamento_xml}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar itens do XML: {str(e)}")

@router.post("/importar")
async def importar_dfe(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Executa a importação da nota, atualizando estoque, financeiro e variações de produtos."""
    service = NFeService(db, current_user.id_empresa)
    return service.importar_nfe_compra(
        nota_id=payload.get("nota_id"),
        mapeamento_itens=payload.get("mapeamento"),
        movimentar_estoque=payload.get("movimentar_estoque"),
        gerar_financeiro=payload.get("gerar_financeiro"),
        id_classificacao_contabil=payload.get("id_classificacao_contabil"),
        caixa_destino_origem=payload.get("caixa_destino_origem"),
        forma_pagamento=payload.get("forma_pagamento")
    )

@router.get("/download-xml/{nota_id}")
async def download_xml(
    nota_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Busca o XML completo no banco e retorna como download de arquivo."""
    nota = db.query(models.NotaFiscalRecebida).filter(
        models.NotaFiscalRecebida.id == nota_id,
        models.NotaFiscalRecebida.id_empresa == current_user.id_empresa
    ).first()
    
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    
    if not nota.xml_completo:
        raise HTTPException(
            status_code=400, 
            detail="XML completo ainda não disponível. Realize a Ciência da Operação e sincronize novamente."
        )

    # Define o nome do arquivo usando a chave de acesso ou o ID
    filename = f"NFe_{nota.chave_acesso or nota.id}.xml"

    return Response(
        content=nota.xml_completo,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.post("/upload")
async def upload_xml(
    files: List[UploadFile] = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Faz o upload manual de um ou mais arquivos XML para a tabela nfe_recebidas."""
    service = NFeService(db, current_user.id_empresa)
    success_count = 0
    errors = []
    
    for file in files:
        try:
            content = await file.read()
            service.importar_xml_manual(content)
            success_count += 1
        except Exception as e:
            errors.append(f"Erro no arquivo {file.filename}: {str(e)}")
            
    return {
        "success": True,
        "message": f"{success_count} arquivos processados com sucesso.",
        "errors": errors
    }