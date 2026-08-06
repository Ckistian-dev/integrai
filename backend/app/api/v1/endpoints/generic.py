from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import StreamingResponse # Importar StreamingResponse
import io # Importar io
import urllib.request # Importar urllib.request
import csv # Importar csv
import json # Importar json
import zipfile # Importar zipfile
import enum # Importar enum
from sqlalchemy.orm import Session, aliased
from sqlalchemy import or_, and_, String, cast, func, distinct, text, asc, desc, inspect, case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import Text, Enum, Date, DateTime, Integer, Numeric, Boolean, Float
from typing import List, Any, Dict
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A6, A4, landscape
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.graphics import renderPDF
from reportlab.lib.colors import black, white, red, blue
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.api.dependencies import get_current_active_user
from app.core.db import models, database, schemas
from app.api.v1.model_dispatch import get_registry_entry
from app.core.service.nfe_service import NFeService
from app.core.service.elastic_email_service import ElasticEmailService

# Constante global para o fuso horário de Brasília
TZ_BR = timezone(timedelta(hours=-3))

from app.crud import crud_user

router = APIRouter()

def apply_search_filter(query, model, search_term: str, search_field: str = None):
    """Aplica filtro de busca textual em colunas e relacionamentos (FKs)."""
    if not search_term:
        return query

    # Campos que nunca devem ser buscados (segurança/sistema)
    ALWAYS_SKIP = ["id_empresa", "senha", "hashed_password"]
    
    # Campos que são pulados na busca global, mas permitidos na busca específica
    GLOBAL_SKIP = ["id", "criado_em", "atualizado_em"]

    filter_conditions = []
    if isinstance(search_term, str):
        search_term = search_term.strip()
    
    search_pattern = f"%{search_term}%"
    
    # 1. Busca nas colunas do próprio modelo
    for col in model.__table__.columns:
        if col.name in ALWAYS_SKIP:
            continue
            
        # Se não for busca específica, pula os campos globais ignorados
        if not search_field and col.name in GLOBAL_SKIP:
            continue
            
        # Se for busca específica, ignora colunas que não são a alvo
        if search_field and col.name != search_field:
            continue

        column_attr = getattr(model, col.name)
        filter_conditions.append(
            func.unaccent(cast(column_attr, String)).ilike(func.unaccent(search_pattern))
        )

    # 2. Busca em relacionamentos (Foreign Keys)
    mapper = inspect(model)
    PREFERRED_DISPLAY_FIELDS = [
        "nome_razao", "fantasia", "nome", "descricao", "razao", "sku", "email", "titulo", "increment_id"
    ]

    for rel in mapper.relationships:
        if rel.direction.name == 'MANYTOONE':
            # Se for busca específica, verifica se o campo alvo é a FK deste relacionamento
            if search_field:
                # Verifica se search_field é uma das colunas locais da FK (ex: id_cliente)
                is_target_rel = any(c.name == search_field for c in rel.local_columns)
                if not is_target_rel:
                    continue

            related_model = rel.mapper.class_
            display_field = None
            for field in PREFERRED_DISPLAY_FIELDS:
                if hasattr(related_model, field):
                    display_field = field
                    break
            
            if display_field:
                rel_alias = aliased(related_model)
                rel_attr = getattr(model, rel.key)
                query = query.outerjoin(rel_alias, rel_attr)
                related_column_attr = getattr(rel_alias, display_field)
                filter_conditions.append(
                    func.unaccent(cast(related_column_attr, String)).ilike(func.unaccent(search_pattern))
                )

    if filter_conditions:
        query = query.filter(or_(*filter_conditions))
    
    return query

# --- NOVA ROTA DE ETIQUETA (AJUSTE FINO - VISUAL JADLOG IDÊNTICO) ---
@router.get("/pedidos/etiqueta/{id}")
def generate_shipping_label(
    id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera etiqueta estilo Jadlog compacta (100x75mm).
    """
    # 1. Busca Dados
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id == id, 
        models.Pedido.id_empresa == current_user.id_empresa
    ).first()
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    empresa = db.query(models.Empresa).filter(models.Empresa.id == current_user.id_empresa).first()
    
    # Tratamento de dados da empresa (evitar None)
    empresa_dados = {
        "razao": empresa.razao if empresa else "Empresa",
        "logradouro": empresa.logradouro if empresa else "",
        "numero": empresa.numero if empresa else "",
        "bairro": empresa.bairro if empresa else "",
        "cidade": empresa.cidade if empresa else "",
        "uf": empresa.estado if empresa else "",
        "cep": empresa.cep if empresa else "",
        "url_logo": empresa.url_logo if empresa else None
    }
    # Correção para Enum no estado da empresa, se houver
    if hasattr(empresa_dados['uf'], 'value'):
         empresa_dados['uf'] = empresa_dados['uf'].value

    # --- NOVO: PRE-FETCH DO LOGO COM TIMEOUT ---
    logo_reader = None
    logo_url = empresa_dados.get('url_logo')
    if logo_url:
        if logo_url.startswith("data:"):
            try:
                import base64
                header, base64_data = logo_url.split(",", 1)
                decoded_bytes = base64.b64decode(base64_data)
                logo_reader = ImageReader(io.BytesIO(decoded_bytes))
            except Exception as e:
                print(f"Aviso: Erro ao decodificar logo em base64: {e}")
        else:
            try:
                req = urllib.request.Request(logo_url, headers={'User-Agent': 'Mozilla/5.0'})
                # Timeout de 3 segundos para evitar travamento
                with urllib.request.urlopen(req, timeout=3) as response:
                    logo_reader = ImageReader(io.BytesIO(response.read()))
            except Exception as e:
                print(f"Aviso: Erro ao baixar logo: {e}")


    # 2. Configuração do Canvas (TAMANHO CRÍTICO: 100x75mm)
    # Isso faz o layout ficar compacto igual à referência
    w_page = 100 * mm
    h_page = 65 * mm 
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(w_page, h_page))
    filename = f"Etiqueta_{id}.pdf"
    c.setTitle(filename)
    
    margin = 3 * mm
    
    # --- LOOP DE VOLUMES ---
    total_volumes = pedido.volumes_quantidade or 1
    
    for current_vol in range(1, total_volumes + 1):
        # ==========================================================================
        # SEÇÃO 1: CABEÇALHO (Logo Esq | Dados Dir)
        # ==========================================================================
        top_y = h_page - margin
        
        # > LOGO (Canto Superior Esquerdo)
        logo_drawn_on_page = False # Renomeado para evitar conflito com a flag global
        if logo_reader:
            try:
                # Desenha logo contido em 40x20mm
                c.drawImage(logo_reader, margin, top_y - 20*mm, width=40*mm, height=20*mm, mask='auto', preserveAspectRatio=True, anchor='nw')
                logo_drawn_on_page = True
            except:
                pass

        if not logo_drawn_on_page:
            # Fallback: Texto simples se não tiver logo
            c.setFont("Helvetica-Bold", 14)
            c.drawString(margin, top_y - 10*mm, empresa_dados['razao'][:15])

        # > DADOS DO PEDIDO (Canto Superior Direito)
        c.setFillColor(black)
        
        # Preparar valores
        nf_val = "-"
        if pedido.chave_acesso and len(pedido.chave_acesso) == 44:
            # O número da NF-e (nNF) são 9 dígitos a partir da posição 25
            nf_val = pedido.chave_acesso[25:34].lstrip('0')

        # ShipmentID: Usa chave de acesso (14 chars) ou ID
        shipment_val = pedido.chave_acesso[:14] if (pedido.chave_acesso and len(pedido.chave_acesso) >= 14) else str(pedido.id).zfill(14)
        
        # --- ATUALIZAÇÃO: Volume dinâmico ---
        vol_str = f"{current_vol}/{total_volumes}"
        
        # Novos campos solicitados
        cnpj_remetente = empresa.cnpj if empresa else ""
        transportadora_nome = pedido.transportadora.nome_razao if pedido.transportadora else "Próprio"

        dados_topo = [
            ("Pedido:", str(pedido.id)),
            ("Nota Fiscal:", nf_val),
            ("Volume:", vol_str)
        ]
        
        # Posição: Metade direita (X=50mm)
        x_data = 50 * mm
        y_data = top_y - 3.5 * mm # Começa bem no topo
        line_spacing = 4.5 * mm   # Espaçamento aumentado
        
        for label, value in dados_topo:
            # Rótulo normal
            c.setFont("Helvetica", 9)
            c.drawString(x_data, y_data, label)
            
            # Valor negrito (calcula deslocamento baseado no tamanho do label)
            lbl_w = c.stringWidth(label, "Helvetica", 9)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(x_data + lbl_w + 2*mm, y_data, value)
            
            y_data -= line_spacing

        # ==========================================================================
        # SEÇÃO 2: BARRA PRETA (Divisor)
        # ==========================================================================
        # A barra fica logo abaixo do logo/dados
        bar_y = top_y - 24 * mm 
        bar_h = 5 * mm
        
        c.setFillColor(black)
        # Desenha de ponta a ponta (0 a 100mm)
        c.rect(0, bar_y, w_page, bar_h, fill=1, stroke=0)
        
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 10)
        # Texto dentro da barra
        c.drawString(margin, bar_y + 1.5*mm, "DESTINATÁRIO")
        c.drawRightString(w_page - margin, bar_y + 1.5*mm, "SHIPMENT ID")

        # ==========================================================================
        # SEÇÃO 3: CORPO (Endereço Esq | Barcode Dir)
        # ==========================================================================
        content_y = bar_y - 4 * mm
        c.setFillColor(black)
        
        # --- COLUNA ESQUERDA: ENDEREÇO ---
        cliente = pedido.cliente
        if cliente:
            nome = (cliente.nome_razao or "Consumidor")
            end = f"{cliente.logradouro or ''}, {cliente.numero or ''}"
            bairro = cliente.bairro or ""
            
            # Correção do Bug "EstadoEnum.SP" -> Pega o valor se for Enum
            uf_val = cliente.estado
            if hasattr(uf_val, 'value'):
                uf_val = uf_val.value
            
            cidade_uf = f"{cliente.cidade or ''}/{uf_val or ''}"
            cep = f"CEP: {cliente.cep or ''}"
        else:
            nome, end, bairro, cidade_uf, cep = "Cliente não identificado", "", "", "", ""

        # Desenha Endereço (Compacto na esquerda)
        c.setFont("Helvetica-Bold", 9)
        # Limitamos a largura para não invadir o código de barras e quebramos a linha se necessário
        max_name_w = 45 * mm
        name_lines = simpleSplit(nome, "Helvetica-Bold", 9, max_name_w)

        current_text_y = content_y
        for line in name_lines[:2]: # No máximo 2 linhas para o nome
            c.drawString(margin, current_text_y, line)
            current_text_y -= 3 * mm
        
        c.setFont("Helvetica", 8)
        current_text_y = content_y - 6.5 * mm
        c.drawString(margin, current_text_y, end[:32]) # Corta se muito longo
        
        current_text_y -= 3 * mm
        c.drawString(margin, current_text_y, bairro[:32])
        
        current_text_y -= 3 * mm
        c.drawString(margin, current_text_y, cidade_uf)
        
        current_text_y -= 3 * mm
        c.drawString(margin, current_text_y, cep)

        # --- COLUNA DIREITA: BARCODE ---
        # O Barcode fica embaixo do título "SHIPMENT ID" da barra preta
        barcode_val = shipment_val
        
        # Configuração para ficar "gordo" e baixo (igual Jadlog)
        # barHeight 16mm (não muito alto)
        # barWidth 1.15 (bem largo)
        bc = code128.Code128(barcode_val, barHeight=16*mm, barWidth=1.15)
        
        # Posiciona no quadrante direito
        # X = Largura da página - Largura do código - Margem
        bc_x = w_page - bc.width - margin
        # Garante que não invada a esquerda (mínimo 50mm)
        if bc_x < 50*mm: bc_x = 50*mm
            
        bc_y = content_y - 14 * mm # Posiciona verticalmente
        
        bc.drawOn(c, bc_x, bc_y)
        
        # Texto numérico centralizado NO código de barras
        c.setFont("Helvetica-Bold", 8)
        bc_center = bc_x + (bc.width / 2)
        c.drawCentredString(bc_center, bc_y - 3*mm, barcode_val)

        # ==========================================================================
        # SEÇÃO 4: RODAPÉ (Remetente)
        # ==========================================================================
        # Linha divisória de ponta a ponta
        line_y = 13 * mm
        c.setLineWidth(0.5)
        c.line(0, line_y, w_page, line_y)
        
        footer_y = line_y - 3.5 * mm
        
        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin, footer_y, "Remetente:")
        
        # Nome Remetente
        c.setFont("Helvetica", 7)
        lbl_w = c.stringWidth("Remetente:", "Helvetica-Bold", 7)
        c.drawString(margin + lbl_w + 2*mm, footer_y, f"{empresa_dados['razao'][:40]}  {cnpj_remetente}")
        
        # Endereço Remetente
        rem_end = f"{empresa_dados['logradouro']}, {empresa_dados['numero']} - {empresa_dados['bairro']} - {empresa_dados['cidade']}/{empresa_dados['uf']}"
        c.drawString(margin, footer_y - 3*mm, rem_end[:65])
        
        # Transportadora
        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin, footer_y - 6*mm, "Transportadora:")
        c.setFont("Helvetica", 7)
        lbl_w_transp = c.stringWidth("Transportadora:", "Helvetica-Bold", 7)
        c.drawString(margin + lbl_w_transp + 2*mm, footer_y - 6*mm, transportadora_nome[:35])

        # Finaliza página atual
        c.showPage()

    c.save()
    
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/pedidos/etiqueta-lote")
def generate_batch_shipping_labels(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera etiquetas em lote em um único arquivo PDF.
    """
    pedido_ids = payload.get("pedido_ids", [])
    if not pedido_ids:
        raise HTTPException(status_code=400, detail="Nenhum pedido selecionado.")

    w_page = 100 * mm
    h_page = 65 * mm 
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(w_page, h_page))
    margin = 3 * mm

    empresa = db.query(models.Empresa).filter(models.Empresa.id == current_user.id_empresa).first()
    empresa_dados = {
        "razao": empresa.razao if empresa else "Empresa",
        "logradouro": empresa.logradouro if empresa else "",
        "numero": empresa.numero if empresa else "",
        "bairro": empresa.bairro if empresa else "",
        "cidade": empresa.cidade if empresa else "",
        "uf": (empresa.estado.value if hasattr(empresa.estado, 'value') else empresa.estado) if empresa else "",
        "cep": empresa.cep if empresa else "",
        "url_logo": empresa.url_logo if empresa else None,
        "cnpj": empresa.cnpj if empresa else ""
    }

    # --- NOVO: PRE-FETCH DO LOGO COM TIMEOUT (PARA O LOTE) ---
    logo_reader = None
    logo_url = empresa_dados.get('url_logo')
    if logo_url:
        if logo_url.startswith("data:"):
            try:
                import base64
                header, base64_data = logo_url.split(",", 1)
                decoded_bytes = base64.b64decode(base64_data)
                logo_reader = ImageReader(io.BytesIO(decoded_bytes))
            except Exception as e:
                print(f"Aviso: Erro ao decodificar logo em base64 no lote: {e}")
        else:
            try:
                req = urllib.request.Request(logo_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=3) as response:
                    logo_reader = ImageReader(io.BytesIO(response.read()))
            except Exception as e:
                print(f"Aviso: Erro ao baixar logo no lote: {e}")

    for pid in pedido_ids:
        pedido = db.query(models.Pedido).filter(models.Pedido.id == pid, models.Pedido.id_empresa == current_user.id_empresa).first()
        if not pedido: continue

        total_volumes = pedido.volumes_quantidade or 1
        for current_vol in range(1, total_volumes + 1):
            top_y = h_page - margin
            
            # Logo (agora usando logo_reader pré-carregado)
            logo_drawn_on_page = False
            if logo_reader:
                try:
                    c.drawImage(logo_reader, margin, top_y - 20*mm, width=40*mm, height=20*mm, mask='auto', preserveAspectRatio=True, anchor='nw')
                    logo_drawn_on_page = True
                except: pass
            if not logo_drawn_on_page:
                c.setFont("Helvetica-Bold", 14)
                c.drawString(margin, top_y - 10*mm, empresa_dados['razao'][:15])

            # Dados Pedido
            nf_val = "-"
            if pedido.chave_acesso and len(pedido.chave_acesso) == 44:
                nf_val = pedido.chave_acesso[25:34].lstrip('0')
            shipment_val = pedido.chave_acesso[:14] if (pedido.chave_acesso and len(pedido.chave_acesso) >= 14) else str(pedido.id).zfill(14)
            
            dados_topo = [("Pedido:", str(pedido.id)), ("Nota Fiscal:", nf_val), ("Volume:", f"{current_vol}/{total_volumes}")]
            x_data, y_data, line_spacing = 50 * mm, top_y - 3.5 * mm, 4.5 * mm
            for label, value in dados_topo:
                c.setFont("Helvetica", 9)
                c.drawString(x_data, y_data, label)
                lbl_w = c.stringWidth(label, "Helvetica", 9)
                c.setFont("Helvetica-Bold", 11)
                c.drawString(x_data + lbl_w + 2*mm, y_data, value)
                y_data -= line_spacing

            # Divisor
            bar_y, bar_h = top_y - 24 * mm, 5 * mm
            c.setFillColor(black)
            c.rect(0, bar_y, w_page, bar_h, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin, bar_y + 1.5*mm, "DESTINATÁRIO")
            c.drawRightString(w_page - margin, bar_y + 1.5*mm, "SHIPMENT ID")

            # Destinatário
            content_y = bar_y - 4 * mm
            c.setFillColor(black)
            cliente = pedido.cliente
            if cliente:
                nome = (cliente.nome_razao or "Consumidor")
                end = f"{cliente.logradouro or ''}, {cliente.numero or ''}"
                uf_val = cliente.estado.value if hasattr(cliente.estado, 'value') else cliente.estado
                cidade_uf = f"{cliente.cidade or ''}/{uf_val or ''}"
                cep = f"CEP: {cliente.cep or ''}"
                bairro = cliente.bairro or ""
            else:
                nome, end, bairro, cidade_uf, cep = "Cliente não identificado", "", "", "", ""

            c.setFont("Helvetica-Bold", 9)
            max_name_w = 45 * mm
            name_lines = simpleSplit(nome, "Helvetica-Bold", 9, max_name_w)

            current_text_y = content_y
            for line in name_lines[:2]:
                c.drawString(margin, current_text_y, line)
                current_text_y -= 3 * mm

            c.setFont("Helvetica", 8)
            c.drawString(margin, content_y - 6.5*mm, end[:32])
            c.drawString(margin, content_y - 9.5*mm, bairro[:32])
            c.drawString(margin, content_y - 12.5*mm, cidade_uf)
            c.drawString(margin, content_y - 15.5*mm, cep)

            # Barcode
            bc = code128.Code128(shipment_val, barHeight=16*mm, barWidth=1.15)
            bc_x = max(50*mm, w_page - bc.width - margin)
            bc_y = content_y - 14 * mm
            bc.drawOn(c, bc_x, bc_y)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(bc_x + (bc.width / 2), bc_y - 3*mm, shipment_val)

            # Rodapé
            line_y = 13 * mm
            c.setLineWidth(0.5)
            c.line(0, line_y, w_page, line_y)
            footer_y = line_y - 3.5 * mm
            c.setFont("Helvetica-Bold", 7)
            c.drawString(margin, footer_y, "Remetente:")
            c.setFont("Helvetica", 7)
            lbl_w = c.stringWidth("Remetente:", "Helvetica-Bold", 7)
            c.drawString(margin + lbl_w + 2*mm, footer_y, f"{empresa_dados['razao'][:40]}  {empresa_dados['cnpj']}")
            rem_end = f"{empresa_dados['logradouro']}, {empresa_dados['numero']} - {empresa_dados['bairro']} - {empresa_dados['cidade']}/{empresa_dados['uf']}"
            c.drawString(margin, footer_y - 3*mm, rem_end[:65])
            
            transportadora_nome = pedido.transportadora.nome_razao if pedido.transportadora else "Próprio / Retira"
            c.setFont("Helvetica-Bold", 7)
            c.drawString(margin, footer_y - 6*mm, "Transportadora:")
            c.setFont("Helvetica", 7)
            lbl_w_transp = c.stringWidth("Transportadora:", "Helvetica-Bold", 7)
            c.drawString(margin + lbl_w_transp + 2*mm, footer_y - 6*mm, transportadora_nome[:35])

            c.showPage()

    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=etiquetas_lote.pdf"})

@router.post("/pedidos/emitir-lote")
def emitir_nfe_lote(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Endpoint para emissão de NFe em lote.
    """
    pedido_ids = payload.get("pedido_ids", [])
    if not pedido_ids:
        raise HTTPException(status_code=400, detail="Nenhum pedido selecionado.")
    
    nfe_service = NFeService(db, current_user.id_empresa)
    return nfe_service.emitir_nfe_lote(pedido_ids)

# --- NOVA ROTA DE ETIQUETA DE VOLUME (2.5cm x 10cm) ---
@router.get("/pedidos/etiqueta_volume/{id}")
def generate_volume_label(
    id: int,
    volumes: int = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera etiqueta de volume (2.5cm x 10cm) para itens do pedido.
    """
    # 1. Busca Dados
    pedido = db.query(models.Pedido).filter(
        models.Pedido.id == id, 
        models.Pedido.id_empresa == current_user.id_empresa
    ).first()
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    # Dados do Cliente
    cliente = pedido.cliente
    cliente_nome = cliente.nome_razao if cliente else "Consumidor"
    uf_dest = cliente.estado.value if hasattr(cliente.estado, 'value') else cliente.estado
    if not uf_dest: uf_dest = "UF"
    cidade_dest = cliente.cidade if cliente else ""

    # Dados da Transportadora
    transp = pedido.transportadora
    transp_nome = transp.nome_razao if transp else "Retira / Próprio"

    # 2. Configuração do Canvas (100mm x 25mm)
    w_page = 100 * mm
    h_page = 25 * mm 
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(w_page, h_page))
    filename = f"Etiquetas_Volume_Pedido_{id}.pdf"
    c.setTitle(filename)
    
    # Margens
    m_left = 3 * mm
    
    # Define quantidade de volumes (Loop por volume e não por item)
    if volumes and volumes > 0:
        total_volumes = volumes
    else:
        total_volumes = int(pedido.volumes_quantidade) if pedido.volumes_quantidade and pedido.volumes_quantidade > 0 else 1
    
    # Prepara lista de produtos
    linhas_produtos = []
    if pedido.itens:
        for item in pedido.itens:
            sku = item.get('sku') or item.get('codigo') or ''
            desc_item = item.get('descricao') or item.get('nome') or "ITEM"
            
            if sku:
                linhas_produtos.append(desc_item)
            else:
                linhas_produtos.append(desc_item)
    else:
        linhas_produtos.append("DIVERSOS")

    for current_vol in range(1, total_volumes + 1):
        # ==========================================================================
        # SEÇÃO 1: CABEÇALHO (Pedido | Cliente)
        # ==========================================================================
        c.setFillColor(black)
        
        # Pedido
        c.setFont("Helvetica-Bold", 8)
        c.drawString(m_left, h_page - 4*mm, f"PEDIDO: {pedido.id}")
        
        # Cliente
        c.setFont("Helvetica", 8)
        c.drawRightString(w_page - m_left, h_page - 4*mm, cliente_nome[:30])

        # ==========================================================================
        # SEÇÃO 2: BARRA PRETA (Divisor)
        # ==========================================================================
        bar_y = h_page - 9 * mm
        bar_h = 4 * mm
        
        c.rect(0, bar_y, w_page, bar_h, fill=1, stroke=0)
        
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(m_left, bar_y + 1*mm, "DESTINO")
        
        # Cidade / UF na barra preta à direita
        dest_str = f"{cidade_dest} / {uf_dest}".upper()
        c.drawRightString(w_page - m_left, bar_y + 1*mm, dest_str[:35])

        # ==========================================================================
        # SEÇÃO 3: CORPO (UF Grande | SKU | Qtd)
        # ==========================================================================
        c.setFillColor(black)
        
        # UF Grande (Esquerda)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(m_left, bar_y - 8*mm, str(uf_dest)[:2])
        
        # Produtos (Lista dinâmica)
        c.setFont("Helvetica-Bold", 6)
        prod_y = bar_y - 2.5*mm
        
        # Limita a 3 linhas
        max_lines = 3
        display_lines = linhas_produtos[:max_lines]
        if len(linhas_produtos) > max_lines:
            display_lines[-1] = "..."
            
        for line in display_lines:
            c.drawString(m_left + 16*mm, prod_y, line[:65])
            prod_y -= 2.2*mm
        
        # Quantidade (Destaque)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(m_left + 16*mm, bar_y - 10.5*mm, f"VOL: {current_vol}/{total_volumes}   QTD: _______")
        
        # ==========================================================================
        # SEÇÃO 4: RODAPÉ (Transportadora)
        # ==========================================================================
        line_y = 4 * mm
        c.setLineWidth(0.5)
        c.line(0, line_y, w_page, line_y)
        
        c.setFont("Helvetica", 6)
        c.drawString(m_left, line_y - 2.5*mm, f"TRANSPORTADORA: {transp_nome}".upper())
        
        c.showPage()
    
    c.save()
    
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- Endpoints de Inventário ---
@router.get("/estoque/inventario", response_model=Any)
def get_inventario_saldo(
    search_term: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Retorna o saldo atual de todos os produtos para o modal de inventário.
    Entrada soma, Saída subtrai, Inventário soma.
    """
    quantidade_expr = func.coalesce(func.sum(
        case(
            (models.Estoque.situacao == 'Saída', -models.Estoque.quantidade),
            else_=models.Estoque.quantidade
        )
    ), 0)

    query = db.query(
        models.Produto.id.label("id_produto"),
        models.Produto.descricao.label("produto_descricao"),
        models.Produto.sku.label("produto_sku"),
        models.Produto.unidade.label("produto_unidade"),
        models.Produto.custo.label("custo"),
        quantidade_expr.label("saldo_atual")
    ).outerjoin(
        models.Estoque,
        and_(
            or_(models.Estoque.id_produto == models.Produto.id_sequencial, models.Estoque.id_produto == models.Produto.id),
            models.Estoque.id_empresa == current_user.id_empresa
        )
    ).filter(
        models.Produto.id_empresa == current_user.id_empresa,
        models.Produto.situacao == True
    ).group_by(
        models.Produto.id, models.Produto.descricao, models.Produto.sku,
        models.Produto.unidade, models.Produto.custo
    )

    if search_term:
        query = query.filter(
            or_(
                models.Produto.descricao.ilike(f"%{search_term}%"),
                models.Produto.sku.ilike(f"%{search_term}%")
            )
        )

    total_count = query.count()
    items_raw = query.order_by(models.Produto.descricao.asc()).offset(skip).limit(limit).all()

    result = []
    for row in items_raw:
        result.append({
            "id_produto": row.id_produto,
            "produto_descricao": row.produto_descricao,
            "produto_sku": row.produto_sku,
            "produto_unidade": row.produto_unidade.value if hasattr(row.produto_unidade, 'value') else (row.produto_unidade or 'un'),
            "custo": float(row.custo or 0),
            "saldo_atual": float(row.saldo_atual),
            "quantidade_inventario": None
        })

    return {"items": result, "total_count": total_count}


@router.post("/estoque/inventario", response_model=Any)
def processar_inventario(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Processa um inventário. Para cada produto informado:
    1. Registra uma linha de 'Inventário' com a quantidade contada.
    2. Se houver diferença (contado != saldo atual), registra uma linha de ajuste
       (Entrada ou Saída) para igualar o saldo.
    """
    itens = payload.get("itens", [])
    observacao_geral = payload.get("observacao", "")
    
    # Validação e captura de data do inventário
    data_inventario_str = payload.get("data_inventario")

    if data_inventario_str:
        try:
            # Tenta converter ISO format (do JS toISOString) que vem em UTC
            dt_utc = datetime.fromisoformat(data_inventario_str.replace("Z", "+00:00"))
            # Converte para o fuso local (BR -3)
            data_inventario_dt = dt_utc.astimezone(TZ_BR)
        except:
            data_inventario_dt = datetime.now(TZ_BR)
    else:
        data_inventario_dt = datetime.now(TZ_BR)
        
    data_formatada = data_inventario_dt.strftime("%d/%m/%Y %H:%M")

    if not itens:
        raise HTTPException(status_code=400, detail="Nenhum item informado para o inventário.")

    criados = []

    for item in itens:
        id_produto = item.get("id_produto")
        quantidade_inventario = item.get("quantidade_inventario")

        if id_produto is None or quantidade_inventario is None:
            continue

        # Verifica se o produto pertence à empresa
        produto = db.query(models.Produto).filter(
            models.Produto.id == id_produto,
            models.Produto.id_empresa == current_user.id_empresa
        ).first()
        if not produto:
            continue

        # Calcula saldo atual na data/hora do inventário (ou atual se for agora)
        # IMPORTANTE: Para inventário retroativo, o saldo deveria ser o saldo NAQUELA DATA.
        # Por simplicidade e seguindo o padrão atual, vamos usar o saldo atual, 
        # mas permitindo que a movimentação tenha a data escolhida.
        saldo_row = db.query(
            func.coalesce(func.sum(
                case(
                    (models.Estoque.situacao == 'Saída', -func.abs(models.Estoque.quantidade)),
                    else_=func.abs(models.Estoque.quantidade)
                )
            ), 0).label("saldo")
        ).filter(
            models.Estoque.id_produto == id_produto,
            models.Estoque.id_empresa == current_user.id_empresa,
            models.Estoque.situacao != 'Inventário'
        ).first()

        saldo_atual = int(saldo_row.saldo or 0)
        quantidade_inventario = int(quantidade_inventario)

        obs_inventario = f"Inventário realizado em {data_formatada}"
        if observacao_geral:
            obs_inventario = f"{obs_inventario} - {observacao_geral}"

        # 1. Linha de inventário (registro do que foi contado fisicamente)
        mov_inventario = models.Estoque(
            id_produto=id_produto,
            id_empresa=current_user.id_empresa,
            quantidade=quantidade_inventario,
            situacao=models.EstoqueSituacaoEnum.inventario,
            observacoes=obs_inventario,
            criado_em=data_inventario_dt # Aplica a data retroativa
        )
        db.add(mov_inventario)
        criados.append(mov_inventario)

        # 2. Linha de ajuste se houver diferença
        diferenca = quantidade_inventario - saldo_atual
        if diferenca != 0:
            if diferenca > 0:
                tipo_ajuste = models.EstoqueSituacaoEnum.entrada
                obs_ajuste = f"Ajuste de inventário ({data_formatada}): acréscimo de {diferenca} unidades para equalizar saldo"
            else:
                tipo_ajuste = models.EstoqueSituacaoEnum.saida
                obs_ajuste = f"Ajuste de inventário ({data_formatada}): redução de {abs(diferenca)} unidades para equalizar saldo"

            mov_ajuste = models.Estoque(
                id_produto=id_produto,
                id_empresa=current_user.id_empresa,
                quantidade=diferenca, # Agora armazena o valor com sinal (negativo para saídas)
                situacao=tipo_ajuste,
                observacoes=obs_ajuste,
                criado_em=data_inventario_dt # Aplica a data retroativa
            )
            db.add(mov_ajuste)
            criados.append(mov_ajuste)

    db.commit()
    for c in criados:
        db.refresh(c)

    return {"success": True, "registros_criados": len(criados)}


# --- Endpoint de Listagem (GET) ---
@router.get("/generic/{model_name}", response_model=Any)
def list_items(
    model_name: str,
    db: Session = Depends(database.get_db),
    skip: int = 0,
    limit: int = 10,
    search_term: str = None,
    search_field: str = None,
    situacao: str = None,
    id_produto: int = None,
    filters: str = None, # JSON string com filtros avançados
    sort_by: str = "id",
    sort_order: str = "desc",
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
    
    # Lógica especial para Estoque (Saldo / Movimentações / Disponível por Lote)
    is_estoque_saldo = (model_name == "estoque" and situacao == "Saldo")
    is_estoque_mov = (model_name == "estoque" and situacao == "Movimentações")
    is_estoque_disponivel = (model_name == "estoque" and situacao == "disponivel")

    if is_estoque_saldo or is_estoque_mov or is_estoque_disponivel:
        situacao = None

    if is_estoque_disponivel:
        # Retorna o saldo agrupado por lote e depósito para um produto específico
        if not id_produto:
            return {"items": [], "total_count": 0}
            
        quantidade_expr = func.coalesce(func.sum(
            case(
                (models.Estoque.situacao == 'Saída', -func.abs(models.Estoque.quantidade)),
                (models.Estoque.situacao == 'Inventário', 0),
                else_=func.abs(models.Estoque.quantidade)
            )
        ), 0)

        query = db.query(
            func.max(models.Estoque.id).label("id"), # Retorna um ID real para o frontend
            models.Estoque.lote,
            models.Estoque.deposito,
            models.Estoque.rua,
            models.Estoque.nivel,
            models.Estoque.cor,
            quantidade_expr.label("quantidade")
        ).filter(
            models.Estoque.id_empresa == current_user.id_empresa,
            models.Estoque.id_produto == id_produto,
            models.Estoque.situacao != 'Inventário'
        ).group_by(
            models.Estoque.lote,
            models.Estoque.deposito,
            models.Estoque.rua,
            models.Estoque.nivel,
            models.Estoque.cor
        ).having(quantidade_expr > 0) # Apenas o que tem saldo positivo

        items_raw = query.order_by(models.Estoque.lote.asc()).all()
        total_count = len(items_raw)

        serialized_items = []
        for row in items_raw:
            serialized_items.append({
                "id": row.id,
                "id_produto": id_produto,
                "lote": row.lote,
                "deposito": row.deposito,
                "rua": row.rua,
                "nivel": row.nivel,
                "cor": row.cor,
                "quantidade": float(row.quantidade)
            })

        return {"items": serialized_items, "total_count": total_count}

    if is_estoque_saldo:
        # Retorna a soma de tudo agrupado por produto
        # Entrada soma, Saída subtrai, Inventário soma
        quantidade_expr = func.coalesce(func.sum(
            case(
                (models.Estoque.situacao == 'Saída', -func.abs(models.Estoque.quantidade)),
                (models.Estoque.situacao == 'Inventário', 0),
                else_=func.abs(models.Estoque.quantidade)
            )
        ), 0)

        query = db.query(
            models.Produto.id.label("id_produto"),
            models.Produto.descricao.label("produto_descricao"),
            models.Produto.sku.label("produto_sku"),
            models.Produto.custo.label("custo"),
            quantidade_expr.label("quantidade")
        ).outerjoin(
            models.Estoque, 
            and_(
                or_(models.Estoque.id_produto == models.Produto.id_sequencial, models.Estoque.id_produto == models.Produto.id),
                models.Estoque.id_empresa == current_user.id_empresa
            )
        ).filter(
            models.Produto.id_empresa == current_user.id_empresa
        ).group_by(models.Produto.id, models.Produto.descricao, models.Produto.sku, models.Produto.custo)

        if search_term:
            query = query.filter(models.Produto.descricao.ilike(f"%{search_term}%"))

        total_count = query.count()
        
        totals_row_q = db.query(
            func.coalesce(func.sum(
                case(
                    (models.Estoque.situacao == 'Saída', -func.abs(models.Estoque.quantidade)),
                    (models.Estoque.situacao == 'Inventário', 0),
                    else_=func.abs(models.Estoque.quantidade)
                ) * models.Produto.custo
            ), 0).label("total_valor")
        ).select_from(models.Produto).outerjoin(
            models.Estoque, 
            and_(
                or_(models.Estoque.id_produto == models.Produto.id_sequencial, models.Estoque.id_produto == models.Produto.id),
                models.Estoque.id_empresa == current_user.id_empresa
            )
        ).filter(
            models.Produto.id_empresa == current_user.id_empresa
        )
        if search_term:
            totals_row_q = totals_row_q.filter(models.Produto.descricao.ilike(f"%{search_term}%"))
        totals_row = totals_row_q.first()
        totals = {
            "quantidade": 0,
            "valor_total": float(totals_row.total_valor or 0)
        }

        items_raw = query.order_by(models.Produto.descricao.asc()).offset(skip).limit(limit).all()

        serialized_items = []
        for row in items_raw:
            custo = float(row.custo or 0)
            quantidade = float(row.quantidade)
            serialized_items.append({
                "id": row.id_produto,
                "id_empresa": current_user.id_empresa,
                "id_produto": row.id_produto,
                "quantidade": quantidade,
                "custo": custo,
                "valor_total": custo * quantidade,
                "situacao": "Entrada",
                "produto": {"id": row.id_produto, "descricao": row.produto_descricao, "sku": row.produto_sku},
                "produto_sku": row.produto_sku,
                "criado_em": datetime.now(TZ_BR).isoformat(),
                "lote": "-",
                "deposito": "-",
                "rua": "-",
                "nivel": "-",
                "cor": "-"
            })

        return {"items": serialized_items, "total_count": total_count, "totals": totals}

    if is_estoque_mov:
        # Query para movimentações incluindo o custo atual do produto
        query = db.query(
            models.Estoque,
            models.Produto.custo.label("produto_custo")
        ).join(
            models.Produto,
            and_(
                or_(models.Estoque.id_produto == models.Produto.id_sequencial, models.Estoque.id_produto == models.Produto.id),
                models.Produto.id_empresa == current_user.id_empresa
            )
        ).filter(
            models.Estoque.id_empresa == current_user.id_empresa,
            models.Estoque.situacao != 'Inventário'
        )

        if search_term:
            query = query.filter(or_(
                models.Produto.descricao.ilike(f"%{search_term}%"),
                models.Estoque.lote.ilike(f"%{search_term}%"),
                models.Estoque.observacoes.ilike(f"%{search_term}%")
            ))
        
        # Aplica filtros avancados de situação se passados via filters param
        if filters:
            try:
                filter_list = json.loads(filters)
                for f in filter_list:
                    if f.get("field") == "situacao" and f.get("value"):
                        query = query.filter(models.Estoque.situacao == f["value"])
            except: pass

        total_count = query.count()
        items_raw = query.order_by(models.Estoque.criado_em.desc()).offset(skip).limit(limit).all()
        
        totals_q = db.query(
            func.coalesce(func.sum(
                case(
                    (models.Estoque.situacao == 'Saída', -func.abs(models.Estoque.quantidade)),
                    (models.Estoque.situacao == 'Inventário', 0),
                    else_=func.abs(models.Estoque.quantidade)
                ) * models.Produto.custo
            ), 0).label("total_valor")
        ).select_from(models.Estoque).join(
            models.Produto,
            and_(
                or_(models.Estoque.id_produto == models.Produto.id_sequencial, models.Estoque.id_produto == models.Produto.id),
                models.Produto.id_empresa == current_user.id_empresa
            )
        ).filter(
            models.Estoque.id_empresa == current_user.id_empresa,
            models.Estoque.situacao != 'Inventário'
        )

        if search_term:
            totals_q = totals_q.filter(or_(
                models.Produto.descricao.ilike(f"%{search_term}%"),
                models.Estoque.lote.ilike(f"%{search_term}%"),
                models.Estoque.observacoes.ilike(f"%{search_term}%")
            ))
        
        if filters:
            try:
                filter_list = json.loads(filters)
                for f in filter_list:
                    if f.get("field") == "situacao" and f.get("value"):
                        totals_q = totals_q.filter(models.Estoque.situacao == f["value"])
            except: pass

        t_row = totals_q.first()
        totals = {
            "quantidade": 0,
            "valor_total": float(t_row.total_valor or 0)
        }

        serialized_items = []
        for estoque_obj, prod_custo in items_raw:
            item_dict = registry["schema"].from_orm(estoque_obj).dict()
            custo = float(prod_custo or 0)
            item_dict["custo"] = custo
            item_dict["valor_total"] = custo * item_dict["quantidade"]
            serialized_items.append(item_dict)

        return {"items": serialized_items, "total_count": total_count, "totals": totals}


    if situacao:
        # Verifica se o modelo realmente tem a coluna "situacao"
        if hasattr(registry["model"], "situacao"):
            if "," in situacao:
                statuses = [s.strip() for s in situacao.split(",")]
                base_query = base_query.filter(registry["model"].situacao.in_(statuses))
            else:
                base_query = base_query.filter(registry["model"].situacao == situacao)
    
    # Filtro por ID do Produto (Útil para verificar estoque)
    if id_produto is not None:
        if hasattr(registry["model"], "id_produto"):
            base_query = base_query.filter(registry["model"].id_produto == id_produto)
    
    # 2. Aplica Filtros Avançados (JSON)
    if filters:
        try:
            filter_list = json.loads(filters)
            # Agrupa filtros por campo para permitir lógica OR em múltiplos "equals"
            filters_by_field = {}
            for f in filter_list:
                fname = f.get("field")
                if fname:
                    if fname not in filters_by_field: filters_by_field[fname] = []
                    filters_by_field[fname].append(f)

            relation_aliases = {}
            for field_name, field_filters in filters_by_field.items():
                field_conditions = []
                
                # Resolve atributo (suporta caminhos aninhados como 'cliente.nome_razao')
                parts = field_name.split('.')
                if len(parts) == 1:
                    if not hasattr(registry["model"], field_name): continue
                    
                    # Verificação de FK para busca textual automática em relacionamentos
                    model = registry["model"]
                    mapper = inspect(model)
                    column = model.__table__.columns.get(field_name)
                    column_attr = getattr(model, field_name)

                    # Se for uma FK e a busca for textual (contains/starts_with), tenta buscar no campo de display do relacionado
                    is_textual_search = any(f.get("operator") in ["contains", "starts_with", "ends_with"] for f in field_filters)
                    
                    if column is not None and column.foreign_keys and is_textual_search:
                        rel = next((r for r in mapper.relationships if column in r.local_columns and r.direction.name == 'MANYTOONE'), None)
                        if rel:
                            related_model = rel.mapper.class_
                            PREFERRED_DISPLAY_FIELDS = ["nome_razao", "fantasia", "nome", "descricao", "razao", "sku", "email", "titulo", "increment_id"]
                            display_field = next((f for f in PREFERRED_DISPLAY_FIELDS if hasattr(related_model, f)), None)
                            
                            if display_field:
                                rel_name = rel.key
                                if rel_name not in relation_aliases:
                                    rel_alias = aliased(related_model, name=rel_name)
                                    base_query = base_query.outerjoin(rel_alias, getattr(model, rel_name))
                                    relation_aliases[rel_name] = rel_alias
                                
                                column_attr = getattr(relation_aliases[rel_name], display_field)
                else:
                    rel_name = parts[0]
                    field_part = parts[1]
                    if rel_name not in relation_aliases:
                        if not hasattr(registry["model"], rel_name): continue
                        rel_attr = getattr(registry["model"], rel_name)
                        try:
                            related_model = rel_attr.property.mapper.class_
                            rel_alias = aliased(related_model, name=rel_name)
                            base_query = base_query.outerjoin(rel_alias, rel_attr)
                            relation_aliases[rel_name] = rel_alias
                        except: continue
                    
                    column_attr = getattr(relation_aliases[rel_name], field_part, None)
                    if column_attr is None: continue
                
                for f in field_filters:
                    operator = f.get("operator")
                    value = f.get("value")
                    
                    if operator == "contains":
                        field_conditions.append(func.unaccent(cast(column_attr, String)).ilike(func.unaccent(f"%{value}%")))
                    elif operator == "equals":
                        if isinstance(value, str) and "," in value:
                            vals = [v.strip() for v in value.split(",")]
                            field_conditions.append(column_attr.in_(vals))
                        else:
                            field_conditions.append(column_attr == value)
                    elif operator == "in":
                        vals = [v.strip() for v in str(value).split(",")] if isinstance(value, str) else value
                        field_conditions.append(column_attr.in_(vals))
                    elif operator == "starts_with":
                        field_conditions.append(func.unaccent(cast(column_attr, String)).ilike(func.unaccent(f"{value}%")))
                    elif operator == "ends_with":
                        field_conditions.append(func.unaccent(cast(column_attr, String)).ilike(func.unaccent(f"%{value}")))
                    elif operator == "gt": field_conditions.append(column_attr > value)
                    elif operator == "gte": field_conditions.append(column_attr >= value)
                    elif operator == "lt": field_conditions.append(column_attr < value)
                    elif operator == "lte": field_conditions.append(column_attr <= value)
                    elif operator == "neq": field_conditions.append(column_attr != value)
                    elif operator == "is_true": field_conditions.append(column_attr == True)
                    elif operator == "is_false": field_conditions.append(column_attr == False)
                    elif operator == "today":
                        today = date.today()
                        field_conditions.append(cast(column_attr, Date) == today)
                    elif operator == "last_days":
                        try:
                            days = int(value)
                        except:
                            days = 0
                        today = date.today()
                        field_conditions.append(and_(cast(column_attr, Date) >= today - timedelta(days=days), cast(column_attr, Date) <= today))
                
                if field_conditions:
                    # Se múltiplos 'equals' ou 'in' no mesmo campo -> OR. Senão -> AND.
                    if all(f.get("operator") in ["equals", "in"] for f in field_filters):
                        base_query = base_query.filter(or_(*field_conditions))
                    else:
                        base_query = base_query.filter(and_(*field_conditions))
                
        except json.JSONDecodeError:
            pass # Ignora filtros mal formados

    # 3. Aplica o filtro de busca textual (Search Term)
    if search_term:
        base_query = apply_search_filter(base_query, registry["model"], search_term, search_field)

    # 4. Ordenação Dinâmica
    if sort_by:
        model = registry["model"]
        sort_by_list = [s.strip() for s in sort_by.split(",")]
        sort_order_list = [s.strip() for s in sort_order.split(",")] if sort_order else []
        
        order_by_clauses = []
        for i, sb in enumerate(sort_by_list):
            so = sort_order_list[i] if i < len(sort_order_list) else (sort_order_list[0] if sort_order_list else "desc")
            
            sort_col = None
            # Caso 1: Notação de ponto (ex: 'cliente.nome_razao')
            if "." in sb:
                parts = sb.split(".")
                if len(parts) == 2:
                    rel_name, field_name = parts
                    if hasattr(model, rel_name):
                        rel_attr = getattr(model, rel_name)
                        try:
                            related_model = rel_attr.property.mapper.class_
                            rel_alias = aliased(related_model, name=f"sort_{i}_{rel_name}")
                            base_query = base_query.outerjoin(rel_alias, rel_attr)
                            sort_col = getattr(rel_alias, field_name, None)
                        except: pass
            
            # Caso 2: Atributo direto do modelo
            if sort_col is None and hasattr(model, sb):
                sort_col = getattr(model, sb)
                
                # Se for uma Foreign Key, tenta ordenar pelo campo de display do relacionado automaticamente
                mapper = inspect(model)
                column = model.__table__.columns.get(sb)
                if column is not None and column.foreign_keys:
                    rel = next((r for r in mapper.relationships if column in r.local_columns and r.direction.name == 'MANYTOONE'), None)
                    if rel:
                        related_model = rel.mapper.class_
                        PREFERRED_DISPLAY_FIELDS = [
                            "nome_razao", "fantasia", "nome", "descricao", "razao", "sku", "email", "titulo", "increment_id"
                        ]
                        display_field = next((f for f in PREFERRED_DISPLAY_FIELDS if hasattr(related_model, f)), None)
                        if display_field:
                            rel_alias = aliased(related_model, name=f"sort_auto_{i}_{rel.key}")
                            base_query = base_query.outerjoin(rel_alias, getattr(model, rel.key))
                            sort_col = getattr(rel_alias, display_field)

            if sort_col is not None:
                # Identifica o tipo da coluna para decidir a estratégia de ordenação
                is_text_field = False
                if hasattr(sort_col, "type") and isinstance(sort_col.type, (String, Text)):
                    is_text_field = True

                needs_numeric_sort = any(kw in sb.lower() for kw in ['numero', 'nsu', 'cep', 'cpf_cnpj'])
                
                # Define a expressão de ordenação conforme o tipo do campo
                if needs_numeric_sort:
                    sort_expressions = [func.length(cast(sort_col, String)), sort_col]
                elif is_text_field:
                    sort_expressions = [func.unaccent(func.lower(sort_col))]
                else:
                    sort_expressions = [sort_col]

                for expr in sort_expressions:
                    if so == "desc":
                        order_by_clauses.append(expr.desc().nulls_last())
                    else:
                        order_by_clauses.append(expr.asc().nulls_last())

        # Garante desempate determinístico pela chave primária (ID) para evitar duplicações na paginação
        model = registry["model"]
        has_id_sort = any(sb == "id" or sb.endswith(".id") for sb in sort_by_list)
        if not has_id_sort and hasattr(model, "id"):
            last_order = sort_order_list[-1] if sort_order_list else "desc"
            if last_order == "desc":
                order_by_clauses.append(model.id.desc().nulls_last())
            else:
                order_by_clauses.append(model.id.asc().nulls_last())

        if order_by_clauses:
            base_query = base_query.order_by(*order_by_clauses)
        else:
            base_query = base_query.order_by(registry["model"].id.desc().nulls_last())
    else:
        # Ordenação padrão (ID desc) se não especificado
        base_query = base_query.order_by(registry["model"].id.desc().nulls_last())

    # 5. Obter a contagem total (removendo ordenação para otimizar e evitar conflito no PostgreSQL)
    total_count = base_query.order_by(None).count()
    
    # --- CÁLCULO DE TOTAIS (Para todas as páginas) ---
    totals = {}
    model = registry["model"]
    sum_columns = []
    
    # Identifica colunas numéricas (Numeric, Integer, Float) que fazem sentido somar
    for col in model.__table__.columns:
        # Ignora chaves primárias, chaves estrangeiras e campos de controle/configuração
        if isinstance(col.type, (Numeric, Integer, Float)) and not col.primary_key and not col.foreign_keys:
            # Lista de campos comuns que não devem ser somados mesmo sendo numéricos
            if col.name.lower() in [
                "nfe_serie", "nfe_numero_sequencial", "nfce_serie", "nfce_numero_sequencial", 
                "modelo_fiscal", "indicador_presenca", "prioridade", "id_empresa",
                "numero_nf", "ordem_finalizacao", "numero_conta", "codigo_ibge", "cep",
                "crt", "indicador_ie", "id_integracao", "entity_id"
            ]:
                continue
            sum_columns.append(col)

    if sum_columns:
        # Cria expressões de soma: func.sum(Model.coluna)
        sum_exprs = [func.sum(getattr(model, col.name)).label(col.name) for col in sum_columns]
        # Executa a query de agregação removendo a ordenação para otimizar a performance
        totals_row = base_query.order_by(None).with_entities(*sum_exprs).first()
        
        if totals_row:
            for i, col in enumerate(sum_columns):
                val = totals_row[i]
                # Converte para float para garantir serialização JSON correta
                totals[col.name] = float(val) if val is not None else 0

    # 6. Obter os itens paginados (APLICA OFFSET E LIMIT DEPOIS DO FILTRO)
    items = base_query.offset(skip).limit(limit).all()
    
    # 7. Serializar os itens
    serialized_items = [registry["schema"].from_orm(item) for item in items]
    
    return {"items": serialized_items, "total_count": total_count, "totals": totals}

@router.get("/generic/{model_name}/distinct/{field_name}", response_model=List[Any])
def get_distinct_values(
    model_name: str,
    field_name: str,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Retorna valores distintos de um campo para preencher dropdowns dinâmicos (CreatableSelect).
    Sempre retorna List[{"value": str, "label": str}].
    Suporta:
      - Campos simples (String, Enum, Integer, Boolean, etc.)
      - Campos FK (join automático com tabela relacionada, retornando label amigável)
      - Campos de relacionamento via notação "relacionamento.campo" (ex: cliente.cidade)
    """
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' não encontrado.")

    model = registry["model"]
    mapper = inspect(model)

    # ── CASO 1: campo de relacionamento com notação "rel.campo" (ex: cliente.cidade) ──
    if "." in field_name:
        rel_name, col_name = field_name.split(".", 1)
        rel = mapper.relationships.get(rel_name)
        if not rel:
            raise HTTPException(status_code=400, detail=f"Relacionamento '{rel_name}' não encontrado em '{model_name}'.")

        related_model = rel.mapper.class_
        if not hasattr(related_model, col_name):
            raise HTTPException(status_code=400, detail=f"Campo '{col_name}' não encontrado no modelo relacionado '{rel_name}'.")

        rel_alias = aliased(related_model)
        column = getattr(rel_alias, col_name)

        results = (
            db.query(distinct(column))
            .outerjoin(rel_alias, getattr(model, rel_name))
            .filter(model.id_empresa == current_user.id_empresa, column.isnot(None))
            .order_by(column.asc())
            .all()
        )

        out = []
        seen = set()
        for r in results:
            val = r[0]
            if hasattr(val, 'value'):
                val = val.value
            val_str = str(val).strip() if val is not None else ''
            if val_str and val_str not in seen:
                seen.add(val_str)
                out.append({"value": val_str, "label": val_str})
        return out

    # ── CASO 2: campo direto no modelo ──
    if not hasattr(model, field_name):
        raise HTTPException(status_code=400, detail=f"Campo '{field_name}' não encontrado em '{model_name}'.")

    column = getattr(model, field_name)
    col_obj = model.__table__.columns.get(field_name)

    # ── CASO 2A: FK — join com tabela relacionada para label amigável ──
    if col_obj is not None and col_obj.foreign_keys:
        rel = next(
            (r for r in mapper.relationships if col_obj in r.local_columns and r.direction.name == 'MANYTOONE'),
            None
        )
        if rel:
            related_model = rel.mapper.class_
            PREFERRED_DISPLAY_FIELDS = [
                "nome_razao", "fantasia", "nome", "descricao", "razao",
                "sku", "email", "titulo", "increment_id", "chave_acesso"
            ]
            display_field = next((f for f in PREFERRED_DISPLAY_FIELDS if hasattr(related_model, f)), None)

            if display_field:
                rel_alias = aliased(related_model)
                results = (
                    db.query(column, getattr(rel_alias, display_field))
                    .outerjoin(rel_alias, getattr(model, rel.key))
                    .filter(model.id_empresa == current_user.id_empresa, column.isnot(None))
                    .distinct()
                    .all()
                )
                out = []
                seen = set()
                for r in results:
                    val_id = str(r[0]) if r[0] is not None else None
                    val_label = str(r[1]).strip() if r[1] else val_id
                    if val_id and val_id not in seen:
                        seen.add(val_id)
                        out.append({"value": val_id, "label": val_label})
                return sorted(out, key=lambda x: x["label"])

    # ── CASO 2B: campo simples (String puro, Enum, Integer, Boolean, etc.) ──
    col_type = col_obj.type if col_obj is not None else None

    # Enum é subclasse de String no SQLAlchemy — não pode usar cast + != '' para Enum
    is_plain_string = isinstance(col_type, (String, Text)) and not isinstance(col_type, Enum)

    filters = [
        model.id_empresa == current_user.id_empresa,
        column.isnot(None),
    ]
    if is_plain_string:
        # Só filtra string vazia em colunas puramente textuais
        filters.append(cast(column, String) != "")

    try:
        unaccent_col = func.unaccent(cast(column, String))
        results = db.query(column, unaccent_col).filter(*filters).distinct().order_by(unaccent_col.asc()).all()
    except Exception:
        # Fallback sem unaccent (ex: tipos não-texto)
        results = db.query(column).filter(*filters).distinct().all()

    out = []
    seen = set()
    for r in results:
        val = r[0]
        if hasattr(val, 'value'):
            val = val.value
        elif hasattr(val, 'name'):
            val = str(val.name)
        val_str = str(val).strip() if val is not None else ''
        if val_str and val_str not in seen:
            seen.add(val_str)
            out.append({"value": val_str, "label": val_str})
    return out

@router.get("/generic/{model_name}/export")
def export_items_to_csv(
    model_name: str,
    db: Session = Depends(database.get_db),
    search_term: str = None,
    search_field: str = None,
    situacao: str = None,
    id_produto: int = None,
    filters: str = None, # JSON string com filtros avançados
    sort_by: str = "id",
    sort_order: str = "desc",
    visible_columns: str = None, # Lista de colunas visíveis separadas por vírgula
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
            if "," in situacao:
                statuses = [s.strip() for s in situacao.split(",")]
                base_query = base_query.filter(registry["model"].situacao.in_(statuses))
            else:
                base_query = base_query.filter(registry["model"].situacao == situacao)

    # Filtro por ID do Produto (Igual à listagem)
    if id_produto is not None:
        if hasattr(registry["model"], "id_produto"):
            base_query = base_query.filter(registry["model"].id_produto == id_produto)

    # 2. Aplica Filtros Avançados (JSON)
    relation_aliases = {}
    if filters:
        try:
            filter_list = json.loads(filters)
            # Agrupa filtros por campo para permitir lógica OR em múltiplos "equals"
            filters_by_field = {}
            for f in filter_list:
                fname = f.get("field")
                if fname:
                    if fname not in filters_by_field: filters_by_field[fname] = []
                    filters_by_field[fname].append(f)

            for field_name, field_filters in filters_by_field.items():
                field_conditions = []
                
                # Resolve atributo (suporta caminhos aninhados como 'cliente.nome_razao')
                parts = field_name.split('.')
                if len(parts) == 1:
                    if not hasattr(registry["model"], field_name): continue
                    
                    # Verificação de FK para busca textual automática em relacionamentos
                    model = registry["model"]
                    mapper = inspect(model)
                    column = model.__table__.columns.get(field_name)
                    column_attr = getattr(model, field_name)

                    # Se for uma FK e a busca for textual (contains/starts_with), tenta buscar no campo de display do relacionado
                    is_textual_search = any(f.get("operator") in ["contains", "starts_with", "ends_with"] for f in field_filters)
                    
                    if column is not None and column.foreign_keys and is_textual_search:
                        rel = next((r for r in mapper.relationships if column in r.local_columns and r.direction.name == 'MANYTOONE'), None)
                        if rel:
                            related_model = rel.mapper.class_
                            PREFERRED_DISPLAY_FIELDS = ["nome_razao", "fantasia", "nome", "descricao", "razao", "sku", "email", "titulo", "increment_id"]
                            display_field = next((f for f in PREFERRED_DISPLAY_FIELDS if hasattr(related_model, f)), None)
                            
                            if display_field:
                                rel_name = rel.key
                                if rel_name not in relation_aliases:
                                    rel_alias = aliased(related_model, name=rel_name)
                                    base_query = base_query.outerjoin(rel_alias, getattr(model, rel_name))
                                    relation_aliases[rel_name] = rel_alias
                                
                                column_attr = getattr(relation_aliases[rel_name], display_field)
                else:
                    rel_name = parts[0]
                    field_part = parts[1]
                    if rel_name not in relation_aliases:
                        if not hasattr(registry["model"], rel_name): continue
                        rel_attr = getattr(registry["model"], rel_name)
                        try:
                            related_model = rel_attr.property.mapper.class_
                            rel_alias = aliased(related_model, name=rel_name)
                            base_query = base_query.outerjoin(rel_alias, rel_attr)
                            relation_aliases[rel_name] = rel_alias
                        except: continue
                    
                    column_attr = getattr(relation_aliases[rel_name], field_part, None)
                    if column_attr is None: continue
                
                for f in field_filters:
                    operator = f.get("operator")
                    value = f.get("value")
                    
                    if operator == "contains":
                        field_conditions.append(func.unaccent(cast(column_attr, String)).ilike(func.unaccent(f"%{value}%")))
                    elif operator == "equals":
                        if isinstance(value, str) and "," in value:
                            vals = [v.strip() for v in value.split(",")]
                            field_conditions.append(column_attr.in_(vals))
                        else:
                            field_conditions.append(column_attr == value)
                    elif operator == "in":
                        vals = [v.strip() for v in str(value).split(",")] if isinstance(value, str) else value
                        field_conditions.append(column_attr.in_(vals))
                    elif operator == "starts_with":
                        field_conditions.append(func.unaccent(cast(column_attr, String)).ilike(func.unaccent(f"{value}%")))
                    elif operator == "ends_with":
                        field_conditions.append(func.unaccent(cast(column_attr, String)).ilike(func.unaccent(f"%{value}")))
                    elif operator == "gt": field_conditions.append(column_attr > value)
                    elif operator == "gte": field_conditions.append(column_attr >= value)
                    elif operator == "lt": field_conditions.append(column_attr < value)
                    elif operator == "lte": field_conditions.append(column_attr <= value)
                    elif operator == "neq": field_conditions.append(column_attr != value)
                    elif operator == "is_true": field_conditions.append(column_attr == True)
                    elif operator == "is_false": field_conditions.append(column_attr == False)
                    elif operator == "today":
                        today = date.today()
                        field_conditions.append(cast(column_attr, Date) == today)
                    elif operator == "last_days":
                        try:
                            days = int(value)
                        except:
                            days = 0
                        today = date.today()
                        field_conditions.append(and_(cast(column_attr, Date) >= today - timedelta(days=days), cast(column_attr, Date) <= today))
                
                if field_conditions:
                    # Se múltiplos 'equals' ou 'in' no mesmo campo -> OR. Senão -> AND.
                    if all(f.get("operator") in ["equals", "in"] for f in field_filters):
                        base_query = base_query.filter(or_(*field_conditions))
                    else:
                        base_query = base_query.filter(and_(*field_conditions))
                
        except json.JSONDecodeError:
            pass # Ignora filtros mal formados

    # 3. Aplica o filtro de busca (igual à listagem)
    if search_term:
        base_query = apply_search_filter(base_query, registry["model"], search_term, search_field)

    # 4. Ordenação Dinâmica (Igual à listagem)
    if sort_by:
        model = registry["model"]
        sort_by_list = [s.strip() for s in sort_by.split(",")]
        sort_order_list = [s.strip() for s in sort_order.split(",")] if sort_order else []
        
        order_by_clauses = []
        for i, sb in enumerate(sort_by_list):
            so = sort_order_list[i] if i < len(sort_order_list) else (sort_order_list[0] if sort_order_list else "desc")
            
            sort_col = None
            # Caso 1: Notação de ponto (ex: 'cliente.nome_razao')
            if "." in sb:
                parts = sb.split(".")
                if len(parts) == 2:
                    rel_name, field_name = parts
                    if hasattr(model, rel_name):
                        rel_attr = getattr(model, rel_name)
                        try:
                            related_model = rel_attr.property.mapper.class_
                            rel_alias = aliased(related_model, name=f"sort_export_{i}_{rel_name}")
                            base_query = base_query.outerjoin(rel_alias, rel_attr)
                            sort_col = getattr(rel_alias, field_name, None)
                        except: pass
            
            # Caso 2: Atributo direto do modelo
            if sort_col is None and hasattr(model, sb):
                sort_col = getattr(model, sb)
                
                # Se for uma Foreign Key, tenta ordenar pelo campo de display do relacionado automaticamente
                mapper = inspect(model)
                column = model.__table__.columns.get(sb)
                if column is not None and column.foreign_keys:
                    rel = next((r for r in mapper.relationships if column in r.local_columns and r.direction.name == 'MANYTOONE'), None)
                    if rel:
                        related_model = rel.mapper.class_
                        PREFERRED_DISPLAY_FIELDS = [
                            "nome_razao", "fantasia", "nome", "descricao", "razao", "sku", "email", "titulo", "increment_id"
                        ]
                        display_field = next((f for f in PREFERRED_DISPLAY_FIELDS if hasattr(related_model, f)), None)
                        if display_field:
                            rel_alias = aliased(related_model, name=f"sort_export_auto_{i}_{rel.key}")
                            base_query = base_query.outerjoin(rel_alias, getattr(model, rel.key))
                            sort_col = getattr(rel_alias, display_field)

            if sort_col is not None:
                # Identifica o tipo da coluna para decidir a estratégia de ordenação
                is_text_field = False
                if hasattr(sort_col, "type") and isinstance(sort_col.type, (String, Text)):
                    is_text_field = True

                needs_numeric_sort = any(kw in sb.lower() for kw in ['numero', 'nsu', 'cep', 'cpf_cnpj'])
                
                # Define a expressão de ordenação conforme o tipo do campo
                if needs_numeric_sort:
                    sort_expressions = [func.length(cast(sort_col, String)), sort_col]
                elif is_text_field:
                    sort_expressions = [func.unaccent(func.lower(sort_col))]
                else:
                    sort_expressions = [sort_col]

                for expr in sort_expressions:
                    if so == "desc":
                        order_by_clauses.append(expr.desc().nulls_last())
                    else:
                        order_by_clauses.append(expr.asc().nulls_last())

        if order_by_clauses:
            base_query = base_query.order_by(*order_by_clauses)
        else:
            base_query = base_query.order_by(registry["model"].id.desc().nulls_last())
    else:
        base_query = base_query.order_by(registry["model"].id.desc().nulls_last())

    # 5. Busca TODOS os itens (sem paginação)
    items = base_query.all()

    # Define os campos que não queremos no CSV (campos internos)
    SKIPPED_FIELDS = ["id_empresa", "hashed_password"]
    
    # --- PRE-FETCH PARA PEDIDOS (OTIMIZAÇÃO) ---
    product_map = {}
    if model_name == 'pedidos':
        all_product_ids = set()
        for item in items:
            if item.itens and isinstance(item.itens, list):
                for line in item.itens:
                    pid = line.get('id_produto') or line.get('produto_id')
                    if pid:
                        try:
                            all_product_ids.add(int(pid))
                        except:
                            pass
        
        if all_product_ids:
            prods = db.query(models.Produto).filter(models.Produto.id.in_(all_product_ids)).all()
            for p in prods:
                product_map[p.id] = p.descricao
    
    # --- LÓGICA DE SUBSTITUIÇÃO DE ID POR LABEL ---
    mapper = inspect(registry["model"])
    columns_map = [] 
    
    # Determina quais colunas processar
    if visible_columns:
        requested_cols = [c.strip() for c in visible_columns.split(",") if c.strip()]
        # Filtra apenas colunas que existem no modelo e não são ignoradas
        target_col_names = [c for c in requested_cols if c in registry["model"].__table__.columns and c not in SKIPPED_FIELDS]
    else:
        # Se não especificou, pega todas (exceto ignoradas)
        target_col_names = [c.name for c in registry["model"].__table__.columns if c.name not in SKIPPED_FIELDS]

    for col_name in target_col_names:
        col = registry["model"].__table__.columns[col_name]
        
        col_def = {
            "header": col.name,
            "attr": col.name,
            "is_fk": False,
            "relation_attr": None,
            "display_field": None
        }

        if col.foreign_keys:
            fk = next(iter(col.foreign_keys))
            target_table = fk.column.table.name
            
            for rel in mapper.relationships:
                if col in rel.local_columns:
                    col_def["is_fk"] = True
                    col_def["relation_attr"] = rel.key
                    
                    try:
                        target_registry = get_registry_entry(target_table)
                        if target_registry:
                            col_def["display_field"] = target_registry.get("display_field", "id")
                    except:
                        pass
                    break
        
        columns_map.append(col_def)

    # Cria um buffer de string na memória
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    # Escreve o cabeçalho
    writer.writerow([c["header"] for c in columns_map])

    # Escreve as linhas de dados
    for item in items:
        row = []
        for col_def in columns_map:
            val = getattr(item, col_def["attr"], "")
            
            if col_def["is_fk"] and col_def["relation_attr"] and col_def["display_field"]:
                rel_obj = getattr(item, col_def["relation_attr"], None)
                if rel_obj:
                    display_val = getattr(rel_obj, col_def["display_field"], None)
                    if display_val is not None:
                        val = display_val
            
            # --- LÓGICA ESPECÍFICA PARA JSON DE ITENS (PEDIDOS) ---
            if model_name == 'pedidos' and col_def["attr"] == 'itens' and isinstance(val, list):
                new_val_list = []
                for line in val:
                    new_line = line.copy()
                    pid = line.get('id_produto') or line.get('produto_id')
                    if pid:
                        try:
                            pid_int = int(pid)
                            if pid_int in product_map:
                                label = product_map[pid_int]
                                if 'id_produto' in new_line: new_line['id_produto'] = label
                                if 'produto_id' in new_line: new_line['produto_id'] = label
                        except:
                            pass
                    new_val_list.append(new_line)
                val = json.dumps(new_val_list, ensure_ascii=False)
            
            # Se for um Enum, pega o valor (texto amigável) em vez do objeto/nome
            if isinstance(val, enum.Enum):
                if hasattr(val, "description"):
                    val = val.description
                elif isinstance(val.value, str):
                    val = val.value
                else:
                    val = val.name.replace('_', ' ').title()
            
            # Formatação de valores numéricos (Currency/Decimal) para padrão PT-BR (vírgula)
            if isinstance(val, (Decimal, float)):
                val = f"{val:.2f}".replace('.', ',')

            row.append(str(val) if val is not None else "")
            
        writer.writerow(row)

    # Prepara o nome do arquivo
    timestamp = datetime.now(TZ_BR).strftime("%Y%m%d_%H%M%S")
    filename = f"{model_name}_{timestamp}.csv"
    
    # Retorna uma StreamingResponse
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/reports/generate-pdf/{report_id}")
def generate_custom_report_pdf(
    report_id: int,
    model_name: str = None,
    config_json: str = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera um relatório PDF com layout dinâmico (Retrato ou Paisagem), 
    sem margens, estilo clean (sem grades e fundo branco) e totais automáticos.
    """
    # 1. Busca ou monta a configuração do relatório
    if report_id > 0:
        relatorio = db.query(models.Relatorio).filter(
            models.Relatorio.id == report_id,
            models.Relatorio.id_empresa == current_user.id_empresa
        ).first()

        if not relatorio:
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")
        
        modelo_base = relatorio.modelo
        config = relatorio.config or {}
        report_name = relatorio.nome
        report_desc = relatorio.descricao
    else:
        if not model_name or not config_json:
            raise HTTPException(status_code=400, detail="Para report_id=0, model_name e config_json são obrigatórios.")
        
        modelo_base = model_name
        try:
            config = json.loads(config_json)
        except:
            raise HTTPException(status_code=400, detail="config_json inválido.")
        
        report_name = config.get('report_name', f"Exportação {model_name}")
        report_desc = config.get('report_description', "")

    # 2. Busca dados da empresa para o cabeçalho
    empresa = db.query(models.Empresa).filter(models.Empresa.id == current_user.id_empresa).first()

    # 3. Identifica o modelo base e monta a query
    registry = get_registry_entry(modelo_base)
    if not registry:
        raise HTTPException(status_code=400, detail=f"Modelo base '{modelo_base}' inválido.")
    
    Model = registry["model"]
    query = db.query(Model).filter(Model.id_empresa == current_user.id_empresa)
    
    # --- JOINS, FILTROS E ORDENAÇÃO ---
    joins_needed = set()
    columns_config = config.get('columns', [])
    for col in columns_config:
        field_path = col.get('field', '').split('.')
        if len(field_path) > 1: joins_needed.add(field_path[0])

    relation_aliases = {}
    for relation_name in joins_needed:
        if hasattr(Model, relation_name):
            rel_attr = getattr(Model, relation_name)
            if hasattr(rel_attr, 'property') and hasattr(rel_attr.property, 'mapper'):
                related_model = rel_attr.property.mapper.class_
                rel_alias = aliased(related_model, name=relation_name)
                query = query.outerjoin(rel_alias, rel_attr)
                relation_aliases[relation_name] = rel_alias

    # --- LÓGICA ESPECIAL PARA ESTOQUE (INJEÇÃO DE CUSTO/TOTAL) ---
    if modelo_base == "estoque":
        p_alias = relation_aliases.get("produto")
        if p_alias is not None:
            query = query.add_columns(p_alias.custo.label("_custo_v"))
        else:
            query = query.outerjoin(models.Produto, Model.id_produto == models.Produto.id)
            query = query.add_columns(models.Produto.custo.label("_custo_v"))

    # --- FILTROS ---
    filter_list = config.get('filters', [])
    filters_by_field = {}
    for f in filter_list:
        fname = f.get("field")
        if fname:
            if fname not in filters_by_field: filters_by_field[fname] = []
            filters_by_field[fname].append(f)

    for field_raw, field_filters in filters_by_field.items():
        field_conditions = []
        
        parts = field_raw.split('.')
        if len(parts) == 1:
            attr = getattr(Model, parts[0], None)
        else:
            rel_name = parts[0]
            field_name = parts[1]
            if rel_name in relation_aliases:
                attr = getattr(relation_aliases[rel_name], field_name, None)
            else:
                attr = None
        
        if not attr: continue

        for f in field_filters:
            operator = f.get('operator')
            value = f.get('value')
            
            if operator == 'equals':
                if isinstance(value, str) and "," in value:
                    vals = [v.strip() for v in value.split(",")]
                    field_conditions.append(attr.in_(vals))
                else:
                    field_conditions.append(attr == value)
            elif operator == 'in':
                vals = [v.strip() for v in str(value).split(",")] if isinstance(value, str) else value
                field_conditions.append(attr.in_(vals))
            elif operator == 'contains': field_conditions.append(cast(attr, String).ilike(f"%{value}%"))
            elif operator == 'gt': field_conditions.append(attr > value)
            elif operator == 'gte': field_conditions.append(attr >= value)
            elif operator == 'lt': field_conditions.append(attr < value)
            elif operator == 'lte': field_conditions.append(attr <= value)
            elif operator == 'is_true': field_conditions.append(attr == True)
            elif operator == 'is_false': field_conditions.append(attr == False)
            elif operator == 'neq': field_conditions.append(attr != value)
            elif operator == 'today':
                today = date.today()
                field_conditions.append(cast(attr, Date) == today)
            elif operator == 'last_days':
                try:
                    days = int(value)
                except:
                    days = 0
                today = date.today()
                field_conditions.append(and_(cast(attr, Date) >= today - timedelta(days=days), cast(attr, Date) <= today))
        
        if field_conditions:
            if all(f.get("operator") in ["equals", "in"] for f in field_filters):
                query = query.filter(or_(*field_conditions))
            else:
                query = query.filter(and_(*field_conditions))

    # --- ORDENAÇÃO ---
    sorts = config.get('sort', [])
    for s in sorts:
        field_raw = s.get('field')
        direction = s.get('direction', 'asc')
        if not field_raw: continue
        
        parts = field_raw.split('.')
        if len(parts) == 1:
            attr = getattr(Model, parts[0], None)
        else:
            rel_name = parts[0]
            field_name = parts[1]
            if rel_name in relation_aliases:
                attr = getattr(relation_aliases[rel_name], field_name, None)
            else:
                attr = None
                
        if attr is not None:
            needs_numeric_sort = any(kw in field_raw.lower() for kw in ['numero', 'nsu', 'cep', 'cpf_cnpj'])
            if direction == 'desc':
                if needs_numeric_sort:
                    query = query.order_by(func.length(cast(attr, String)).desc().nulls_last(), attr.desc().nulls_last())
                else:
                    query = query.order_by(attr.desc().nulls_last())
            else:
                if needs_numeric_sort:
                    query = query.order_by(func.length(cast(attr, String)).asc().nulls_last(), attr.asc().nulls_last())
                else:
                    query = query.order_by(attr.asc().nulls_last())

    # Executa a query
    raw_results = query.all()
    results = []
    if modelo_base == "estoque":
        for row in raw_results:
            obj = row[0]
            custo = float(row[1] or 0)
            setattr(obj, "custo", custo)
            setattr(obj, "valor_total", custo * obj.quantidade)
            results.append(obj)
    else:
        results = raw_results

    # --- MONTAGEM DOS DADOS E CÁLCULO DE LARGURA ---
    def format_val(v):
        if isinstance(v, enum.Enum):
            if hasattr(v, "description"): return v.description
            if isinstance(v.value, str): return v.value
            return v.name.replace('_', ' ').title()
        if isinstance(v, (Decimal, float)):
            return f"{float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return str(v) if v is not None else ""

    headers = [c.get('label', c.get('field')) for c in columns_config]
    table_data = [headers]

    col_totals = [0.0] * len(columns_config)
    is_numeric_col = [False] * len(columns_config)

    for row in results:
        processed_values = []
        num_rows_for_this_record = 1
        
        for i, col in enumerate(columns_config):
            field_path = col.get('field', '').split('.')
            val = row
            for part in field_path:
                val = getattr(val, part, None)
                if val is None: break
            
            if isinstance(val, (int, float, Decimal)):
                is_numeric_col[i] = True
                col_totals[i] += float(val)

            is_expanded = False
            if col.get('json_key') and isinstance(val, (dict, list)):
                if isinstance(val, dict): val = val.get(col['json_key'])
                elif isinstance(val, list):
                    extracted = []
                    for item in val:
                        if isinstance(item, dict): extracted.append(item.get(col['json_key']))
                        else: extracted.append(item)
                    val = extracted
                    is_expanded = True
                    num_rows_for_this_record = max(num_rows_for_this_record, len(val))
            
            if is_expanded: formatted_val = [format_val(v) for v in val]
            else: formatted_val = format_val(val)
            processed_values.append((formatted_val, is_expanded))

        for i in range(num_rows_for_this_record):
            pdf_row = []
            for (val, is_expanded) in processed_values:
                cell_val = val[i] if is_expanded and i < len(val) else (val if not is_expanded else "")
                pdf_row.append(cell_val)
            table_data.append(pdf_row)

    if any(is_numeric_col):
        total_row = []
        for i in range(len(columns_config)):
            if i == 0: total_row.append("Totais")
            elif is_numeric_col[i]:
                formatted_total = f"{col_totals[i]:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                total_row.append(formatted_total)
            else: total_row.append("")
        table_data.append(total_row)

    # --- ANÁLISE DE ESPAÇO PARA ORIENTAÇÃO DINÂMICA ---
    max_col_lengths = [len(str(h)) for h in headers]
    for row in table_data[1:]:
        for i, cell_value in enumerate(row):
            if i < len(max_col_lengths):
                max_col_lengths[i] = max(max_col_lengths[i], len(str(cell_value)))

    total_chars = sum(max_col_lengths)
    num_cols = len(headers)

    # Regra: Se a soma dos caracteres passar de ~110 ou houver mais de 7 colunas, usa Paisagem
    if total_chars > 110 or num_cols > 7:
        tamanho_pagina = landscape(A4)
    else:
        tamanho_pagina = A4

    # Largura total disponível = largura exata da página (pois as margens serão 0)
    avail_width = tamanho_pagina[0]

    # Criação do documento com margens laterais zeradas e metadados
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=tamanho_pagina, 
        rightMargin=0, 
        leftMargin=0, 
        topMargin=0, 
        bottomMargin=0,
        title=report_name,       # Define o título na aba do navegador
        author=empresa.fantasia or empresa.razao    # Define o autor nos metadados do PDF
    )
    elements = []
    styles = getSampleStyleSheet()

    # --- CABEÇALHO ---
    data_atual = datetime.now(TZ_BR).strftime("%d/%m/%Y")
    nome_empresa = empresa.fantasia or empresa.razao or "Empresa"

    if empresa.url_logo:
        try:
            if empresa.url_logo.startswith("data:"):
                import base64
                header, base64_data = empresa.url_logo.split(",", 1)
                decoded_bytes = base64.b64decode(base64_data)
                logo = Image(io.BytesIO(decoded_bytes), width=35*mm, height=15*mm, kind='proportional')
            else:
                logo = Image(empresa.url_logo, width=35*mm, height=15*mm, kind='proportional')
            elemento_esq = logo
        except Exception as e:
            print(f"Erro ao carregar logo no relatorio: {e}")
            elemento_esq = Paragraph(f"<b>{nome_empresa}</b>", styles['Normal'])
    else:
        elemento_esq = Paragraph(f"<b>{nome_empresa}</b>", styles['Normal'])

    titulo_formatado = f"<para align=center><b><font size=12>{report_name}</font></b>"
    if report_desc:
        titulo_formatado += f"<br/><font size=8>{report_desc}</font>"
    titulo_formatado += "</para>"
    elemento_centro = Paragraph(titulo_formatado, styles['Normal'])

    elemento_dir = Paragraph(f"<para align=right>Dia {data_atual}</para>", styles['Normal'])

    # O cabeçalho usa a largura total da página distribuída
    header_table = Table(
        [[elemento_esq, elemento_centro, elemento_dir]], 
        colWidths=[50*mm, avail_width - 100*mm, 50*mm]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        # Espaçamento lateral do cabeçalho para não ficar colado na borda do papel
        ('LEFTPADDING', (0, 0), (0, 0), 10*mm),
        ('RIGHTPADDING', (-1, -1), (-1, -1), 10*mm),
    ]))
    
    elements.append(header_table)
    elements.append(Spacer(1, 8*mm))

    # --- TABELA DE DADOS ---
    # Distribui a largura proporcionalmente (textos grandes ganham mais espaço)
    if total_chars > 0:
        col_widths = [(l / total_chars) * avail_width for l in max_col_lengths]
    else:
        col_widths = [avail_width / num_cols] * num_cols if num_cols > 0 else [avail_width]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Estilo 100% limpo: fundo branco, sem zebrado, alinhado e compacto
    table_styles = [
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        
        # Dados (Fundo branco fixo)
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7), 
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
    ]

    # Alinhamento Automático
    for i, is_num in enumerate(is_numeric_col):
        if is_num:
            table_styles.append(('ALIGN', (i, 0), (i, -1), 'RIGHT'))
        else:
            table_styles.append(('ALIGN', (i, 0), (i, -1), 'LEFT'))

    if any(is_numeric_col):
        table_styles.extend([
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.white),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ])

    t.setStyle(TableStyle(table_styles))
    elements.append(t)

    # --- RODAPÉ DINÂMICO ---
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        footer_text = f"Página {canvas.getPageNumber()}"
        canvas.drawCentredString(tamanho_pagina[0]/2, 5*mm, footer_text)
        canvas.restoreState()

    doc.build(elements, onLaterPages=footer, onFirstPage=footer)
    
    buffer.seek(0)
    filename = f"{report_name.replace(' ', '_')}_{datetime.now(TZ_BR).strftime('%d_%m_%Y')}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def gerar_contas_financeiras_pedido(db: Session, item: models.Pedido, current_user: models.Usuario, obs_origem: str = ""):
    try:
        desc_conta = f"Pedido de Venda #{item.id}"
        existing_conta = db.query(models.Conta).filter(
            models.Conta.id_empresa == current_user.id_empresa,
            models.Conta.descricao.contains(desc_conta),
            models.Conta.tipo_conta == models.ContaTipoEnum.a_receber
        ).first()

        if existing_conta:
            return

        # Sincroniza campos legados com o primeiro item de pagamentos se houver
        lista_pagamentos = item.pagamentos if isinstance(item.pagamentos, list) else []
        if lista_pagamentos and len(lista_pagamentos) > 0:
            first_pag = lista_pagamentos[0]
            if isinstance(first_pag, dict):
                if first_pag.get('pagamento'):
                    try:
                        pag_val = first_pag.get('pagamento')
                        item.pagamento = models.FiscalPagamentoEnum(pag_val) if isinstance(pag_val, str) else pag_val
                    except Exception:
                        pass
                if first_pag.get('caixa_destino_origem'):
                    item.caixa_destino_origem = first_pag.get('caixa_destino_origem')
                if first_pag.get('pagamento_descricao'):
                    item.pagamento_descricao = first_pag.get('pagamento_descricao')

        valor_final = item.total_desconto if (item.total_desconto and item.total_desconto > 0) else item.total
        if not valor_final or valor_final <= 0:
            return

        # 1. Fallback Cliente Seguro
        cliente_nome = item.cliente.nome_razao if item.cliente else "Consumidor Final"
        cliente_id = item.id_cliente
        if not cliente_id:
            fallback_cli = db.query(models.Cadastro).filter(models.Cadastro.id_empresa == current_user.id_empresa).first()
            if fallback_cli:
                cliente_id = fallback_cli.id_sequencial or fallback_cli.id
            else:
                novo_cli = models.Cadastro(
                    id_empresa=current_user.id_empresa,
                    cpf_cnpj="00000000000",
                    nome_razao="CONSUMIDOR FINAL",
                    tipo_cadastro=models.CadastroTipoCadastroEnum.cliente,
                    cep="00000000"
                )
                db.add(novo_cli)
                db.flush()
                cliente_id = novo_cli.id_sequencial or novo_cli.id

        # 2. Resgata e Garante o Plano de Contas
        empresa_obj = db.query(models.Empresa).filter(models.Empresa.id == current_user.id_empresa).first()
        classificacao_id = empresa_obj.id_classificacao_contabil_padrao if empresa_obj else None
        if not classificacao_id:
            fallback_class = db.query(models.ClassificacaoContabil).filter(
                models.ClassificacaoContabil.id_empresa == current_user.id_empresa,
                models.ClassificacaoContabil.tipo.ilike('%receita%')
            ).first() or db.query(models.ClassificacaoContabil).filter(
                models.ClassificacaoContabil.id_empresa == current_user.id_empresa
            ).first()
            if fallback_class:
                classificacao_id = fallback_class.id_sequencial or fallback_class.id
            else:
                nova_class = models.ClassificacaoContabil(
                    id_empresa=current_user.id_empresa,
                    grupo="Receitas",
                    descricao="Vendas de Mercadorias",
                    tipo="Receita",
                    considerar=True
                )
                db.add(nova_class)
                db.flush()
                classificacao_id = nova_class.id_sequencial or nova_class.id

        pagamentos_validos = [p for p in lista_pagamentos if isinstance(p, dict) and (float(p.get('valor', 0) or 0) > 0)]

        if len(pagamentos_validos) > 0:
            for idx, pag_item in enumerate(pagamentos_validos, 1):
                val_p = Decimal(str(pag_item.get('valor', 0)))
                pag_enum = None
                if pag_item.get('pagamento'):
                    try:
                        pag_enum = models.FiscalPagamentoEnum(pag_item.get('pagamento'))
                    except Exception:
                        pass
                caixa_p = pag_item.get('caixa_destino_origem') or item.caixa_destino_origem
                
                label_forma = ""
                if pag_enum and hasattr(pag_enum, 'description'):
                    label_forma = pag_enum.description
                elif pag_item.get('pagamento'):
                    label_forma = str(pag_item.get('pagamento'))

                sub_desc = f"{desc_conta} - {cliente_nome}"
                if label_forma:
                    sub_desc += f" ({label_forma})"
                if caixa_p:
                    sub_desc += f" [{caixa_p}]"

                nova_conta = models.Conta(
                    id_empresa=current_user.id_empresa,
                    tipo_conta=models.ContaTipoEnum.a_receber,
                    situacao=models.ContaSituacaoEnum.em_aberto,
                    descricao=sub_desc,
                    numero_conta=str(item.id),
                    id_fornecedor=cliente_id,
                    valor=val_p,
                    data_emissao=datetime.now(TZ_BR).date(),
                    data_vencimento=datetime.now(TZ_BR).date(),
                    pagamento=pag_enum,
                    caixa_destino_origem=caixa_p,
                    id_classificacao_contabil=classificacao_id,
                    observacoes=f"{obs_origem} Pagamento {idx}/{len(pagamentos_validos)}".strip()
                )
                db.add(nova_conta)
        else:
            nova_conta = models.Conta(
                id_empresa=current_user.id_empresa,
                tipo_conta=models.ContaTipoEnum.a_receber,
                situacao=models.ContaSituacaoEnum.em_aberto,
                descricao=f"{desc_conta} - {cliente_nome}",
                numero_conta=str(item.id),
                id_fornecedor=cliente_id,
                valor=valor_final,
                data_emissao=datetime.now(TZ_BR).date(),
                data_vencimento=datetime.now(TZ_BR).date(),
                pagamento=item.pagamento,
                caixa_destino_origem=item.caixa_destino_origem,
                id_classificacao_contabil=classificacao_id,
                observacoes=obs_origem
            )
            db.add(nova_conta)

        db.commit()
    except Exception as e:
        print(f"Erro ao gerar financeiro automático do pedido: {e}")


_TABLE_TO_MODEL_MAP = {}

def _get_model_class_by_tablename(tablename: str):
    if not _TABLE_TO_MODEL_MAP:
        from app.core.db.database import Base
        for mapper in Base.registry.mappers:
            cls = mapper.class_
            tbl = getattr(cls, "__tablename__", None)
            if tbl:
                _TABLE_TO_MODEL_MAP[tbl] = cls
    return _TABLE_TO_MODEL_MAP.get(tablename)

def resolve_related_ids(db: Session, model: Any, item_data: Dict[str, Any], id_empresa: int) -> Dict[str, Any]:
    """
    Garante que os campos com ID de tabelas relacionadas utilizem o id_sequencial da tabela destino,
    convertendo se o payload enviar o id primário interno.
    """
    if not item_data or not isinstance(item_data, dict):
        return item_data

    try:
        mapper_inspector = inspect(model)
        for col in mapper_inspector.columns:
            col_name = col.name
            if col_name in item_data and item_data[col_name] is not None:
                val = item_data[col_name]
                if col.foreign_keys:
                    for fk in col.foreign_keys:
                        target_table_name = fk.column.table.name
                        if target_table_name == "empresas":
                            continue

                        target_model = _get_model_class_by_tablename(target_table_name)
                        if target_model and hasattr(target_model, "id_sequencial"):
                            if isinstance(val, (int, str)) and str(val).isdigit():
                                num_val = int(val)
                                q = db.query(target_model)
                                if hasattr(target_model, "id_empresa"):
                                    q = q.filter(target_model.id_empresa == id_empresa)

                                target_obj = q.filter(target_model.id_sequencial == num_val).first()
                                if target_obj and target_obj.id_sequencial is not None:
                                    item_data[col_name] = target_obj.id_sequencial
                                else:
                                    target_obj_by_id = q.filter(target_model.id == num_val).first()
                                    if target_obj_by_id and target_obj_by_id.id_sequencial is not None:
                                        item_data[col_name] = target_obj_by_id.id_sequencial
    except Exception as e:
        print(f"Aviso ao resolver IDs relacionados em {model}: {e}")

    # Processa itens aninhados em Pedidos (ex: id_produto / produto_id)
    if "itens" in item_data and isinstance(item_data["itens"], list):
        for item in item_data["itens"]:
            if isinstance(item, dict):
                for prod_key in ["id_produto", "produto_id"]:
                    prod_val = item.get(prod_key)
                    if prod_val is not None and str(prod_val).isdigit():
                        num_prod = int(prod_val)
                        prod_q = db.query(models.Produto).filter(models.Produto.id_empresa == id_empresa)
                        prod_obj = prod_q.filter(models.Produto.id_sequencial == num_prod).first()
                        if prod_obj and prod_obj.id_sequencial is not None:
                            item[prod_key] = prod_obj.id_sequencial
                        else:
                            prod_obj_by_id = prod_q.filter(models.Produto.id == num_prod).first()
                            if prod_obj_by_id and prod_obj_by_id.id_sequencial is not None:
                                item[prod_key] = prod_obj_by_id.id_sequencial

    return item_data


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

    # Resolução de IDs de tabelas relacionadas para id_sequencial
    resolve_related_ids(db, registry["model"], item_data, current_user.id_empresa)

    # --- Validação: Trim em todos os campos de string ---
    for key, value in item_data.items():
        if isinstance(value, str):
            item_data[key] = value.strip()

    # Normalização para Caixa Alta (Cadastro e Empresa)
    if model_name in ["cadastros", "empresas"]:
        for field in ["nome_razao", "fantasia", "razao"]:
            if field in item_data and isinstance(item_data[field], str):
                item_data[field] = item_data[field].upper()

    # Validação de Duplicidade para Cadastros (CPF/CNPJ único por Empresa)
    if model_name == "cadastros":
        cpf_cnpj = item_data.get("cpf_cnpj")
        if cpf_cnpj:
            existing = db.query(models.Cadastro).filter(
                models.Cadastro.cpf_cnpj == cpf_cnpj,
                models.Cadastro.id_empresa == current_user.id_empresa
            ).first()
            if existing:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Já existe um cadastro com o CPF/CNPJ {cpf_cnpj}.")

    # 🎯 LÓGICA ESPECÍFICA: Preencher data_validade padrão para Pedidos
    if model_name == "pedidos" and (not item_data.get("data_validade")):
        empresa = db.query(models.Empresa).filter(models.Empresa.id == current_user.id_empresa).first()
        validade_dias = empresa.validade_orcamento if (empresa and empresa.validade_orcamento) else 7
        item_data["data_validade"] = (datetime.now(TZ_BR) + timedelta(days=validade_dias)).date()

    # 🎯 LÓGICA ESPECÍFICA: Validação de Plano de Contas vs Tipo de Conta
    if model_name == "contas":
        id_classificacao = item_data.get("id_classificacao_contabil")
        tipo_conta = item_data.get("tipo_conta")
        if id_classificacao:
            classificacao = db.query(models.ClassificacaoContabil).filter(
                models.ClassificacaoContabil.id == id_classificacao,
                models.ClassificacaoContabil.id_empresa == current_user.id_empresa
            ).first()
            if classificacao:
                if tipo_conta == "A Receber" and classificacao.tipo_movimentacao != "Entrada":
                    raise HTTPException(status_code=400, detail="Contas a Receber só podem utilizar planos de contas do tipo Entrada.")
                if tipo_conta == "A Pagar" and classificacao.tipo_movimentacao == "Entrada":
                    raise HTTPException(status_code=400, detail="Contas a Pagar não podem utilizar planos de contas do tipo Entrada.")

    try:
        CreateSchema = registry["create_schema"]
        validated_data = CreateSchema(**item_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}")

    try:
        # 🎯 CORREÇÃO PARA HASH DE SENHA NA CRIAÇÃO
        if model_name == "usuarios":
            item = crud_user.create_user(
                db=db,
                obj_in=validated_data,
                id_empresa=current_user.id_empresa
            )
        else:
            item = registry["crud"].create(
                db,
                model=registry["model"],
                obj_in=validated_data,
                id_empresa=current_user.id_empresa
            )

            # 🎯 LÓGICA ESPECÍFICA: Gerar Financeiro ao Criar Pedido já Aprovado (Programação)
            if model_name == "pedidos":
                if item.situacao == models.PedidoSituacaoEnum.programacao:
                    gerar_contas_financeiras_pedido(db, item, current_user, "Gerado automaticamente na criação do pedido aprovado.")

            # 🎯 LÓGICA ESPECÍFICA: Notificação AtendAI na criação de pedido
            if model_name == "pedidos":
                try:
                    from app.core.service.atendai_service import AtendaiService
                    atendai_svc = AtendaiService(db, current_user.id_empresa)
                    atendai_svc.send_order_notification(item, event_type="pedido_criado")
                except Exception as e:
                    print(f"Erro ao notificar AtendAI na criação do pedido #{item.id}: {e}")
    except IntegrityError as e:
        db.rollback()
        error_info = str(e.orig) if e.orig else str(e)
        
        # Verifica se é erro de chave primária duplicada (sequência desincronizada)
        if "unique constraint" in error_info and "_pkey" in error_info:
            try:
                # Tenta corrigir a sequência automaticamente (PostgreSQL)
                table_name = registry["model"].__tablename__
                sql = text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), (SELECT MAX(id) FROM {table_name}));")
                db.execute(sql)
                db.commit()
                raise HTTPException(status_code=409, detail="A sequência de IDs do banco estava desincronizada e foi corrigida automaticamente. Por favor, clique em Salvar novamente.")
            except Exception:
                pass # Se falhar a correção automática, cai no erro padrão abaixo
        
        raise HTTPException(status_code=400, detail=f"Erro de integridade de dados: {error_info}")

    return registry["schema"].from_orm(item)

# --- Endpoint de Atualização em Lote (PUT) ---
@router.put("/generic/{model_name}/batch-update")
def batch_update_items(
    model_name: str,
    ids: List[int] = Body(...),
    item_data: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Atualiza múltiplos itens de uma vez."""
    registry = get_registry_entry(model_name)
    if not registry:
        raise HTTPException(status_code=404, detail="Model not found")

    # Resolução de IDs de tabelas relacionadas para id_sequencial
    resolve_related_ids(db, registry["model"], item_data, current_user.id_empresa)

    # --- Validação: Trim em todos os campos de string ---
    for key, value in item_data.items():
        if isinstance(value, str):
            item_data[key] = value.strip()
        
    # Busca os itens garantindo que pertencem à empresa
    items = db.query(registry["model"]).filter(
        registry["model"].id.in_(ids),
        registry["model"].id_empresa == current_user.id_empresa
    ).all()
    
    if not items:
        raise HTTPException(status_code=404, detail="Nenhum item encontrado para os IDs fornecidos.")
        
    for item in items:
        for key, value in item_data.items():
            if hasattr(item, key):
                val_to_set = value
                if key == "data_despacho" and isinstance(value, str):
                    try:
                        val_to_set = datetime.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                setattr(item, key, val_to_set)

    # 🎯 Lógica específica: Preencher data_despacho se estiver despachando pedidos
    if model_name == "pedidos" and item_data.get("situacao") in ["Despachado", models.PedidoSituacaoEnum.despachado]:
        hoje = datetime.now(TZ_BR).date()
        for item in items:
            if getattr(item, "data_despacho", None) is None:
                setattr(item, "data_despacho", hoje)
                
    db.commit()

    if model_name == "pedidos":
        try:
            from app.core.service.atendai_service import AtendaiService
            atendai_svc = AtendaiService(db, current_user.id_empresa)
            for item in items:
                atendai_svc.send_order_notification(item, event_type="pedido_atualizado")
        except Exception as e:
            print(f"Erro ao notificar AtendAI na atualização em lote de pedidos: {e}")

    return {"message": f"{len(items)} itens atualizados com sucesso."}

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

    # Resolução de IDs de tabelas relacionadas para id_sequencial
    resolve_related_ids(db, registry["model"], item_data, current_user.id_empresa)

    # --- Validação: Trim em todos os campos de string ---
    for key, value in item_data.items():
        if isinstance(value, str):
            item_data[key] = value.strip()

    # Busca o objeto existente
    db_obj = registry["crud"].get(
        db,
        model=registry["model"],
        id=id,
        id_empresa=current_user.id_empresa
    )
    if not db_obj:
        raise HTTPException(status_code=404, detail="Item not found")

    # Normalização para Caixa Alta (Cadastro e Empresa)
    if model_name in ["cadastros", "empresas"]:
        for field in ["nome_razao", "fantasia", "razao"]:
            if field in item_data and isinstance(item_data[field], str):
                item_data[field] = item_data[field].upper()

    # Validação de Duplicidade para Cadastros (CPF/CNPJ único por Empresa)
    if model_name == "cadastros":
        cpf_cnpj = item_data.get("cpf_cnpj")
        if cpf_cnpj:
            existing = db.query(models.Cadastro).filter(
                models.Cadastro.cpf_cnpj == cpf_cnpj,
                models.Cadastro.id_empresa == current_user.id_empresa,
                models.Cadastro.id != id
            ).first()
            if existing:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Já existe outro cadastro com o CPF/CNPJ {cpf_cnpj}.")

    # --- CAPTURA ESTADO ANTERIOR (Para Pedidos) ---
    old_situacao = None
    if model_name == "pedidos" and hasattr(db_obj, "situacao"):
        old_situacao = db_obj.situacao

    # 🎯 LÓGICA ESPECÍFICA: Preencher data_pedido ao aprovar
    if model_name == "pedidos":
        new_situacao_from_payload = item_data.get("situacao")
        if new_situacao_from_payload and (new_situacao_from_payload == models.PedidoSituacaoEnum.aprovacao or new_situacao_from_payload == models.PedidoSituacaoEnum.programacao):
            if db_obj.data_pedido is None:
                item_data["data_pedido"] = datetime.now(TZ_BR).date()
        
        # 🎯 LÓGICA ESPECÍFICA: Bloquear Expedição se não tiver Intelipost
        if new_situacao_from_payload == models.PedidoSituacaoEnum.expedicao:
            # Só valida se houver configuração da Intelipost ativa e não for Mercado Envios
            intelipost_config = db.query(models.IntelipostConfiguracao).filter(
                models.IntelipostConfiguracao.id_empresa == current_user.id_empresa
            ).first()
            
            is_mercado_envios = False
            if db_obj.transportadora and db_obj.transportadora.nome_razao:
                nome_transp = db_obj.transportadora.nome_razao.lower()
                if "mercado" in nome_transp and ("env" in nome_transp or "livre" in nome_transp):
                    is_mercado_envios = True
            
            if intelipost_config and intelipost_config.api_key and not is_mercado_envios:
                if not db_obj.intelipost_criado:
                    raise HTTPException(
                        status_code=400, 
                        detail="O pedido não pode ser movido para Expedição pois ainda não foi criado na Intelipost. Realize o faturamento/integração primeiro."
                    )
        
        # Lógica específica: Preencher data_despacho ao despachar
        if new_situacao_from_payload == models.PedidoSituacaoEnum.despachado and db_obj.data_despacho is None:
            item_data["data_despacho"] = datetime.now(TZ_BR).date()

    # 🎯 LÓGICA ESPECÍFICA: Validação de Plano de Contas vs Tipo de Conta
    if model_name == "contas":
        id_classificacao = item_data.get("id_classificacao_contabil", db_obj.id_classificacao_contabil)
        tipo_conta = item_data.get("tipo_conta", db_obj.tipo_conta)
        
        if id_classificacao:
            classificacao = db.query(models.ClassificacaoContabil).filter(
                models.ClassificacaoContabil.id == id_classificacao,
                models.ClassificacaoContabil.id_empresa == current_user.id_empresa
            ).first()
            if classificacao:
                tipo_str = tipo_conta.value if hasattr(tipo_conta, 'value') else str(tipo_conta)
                if tipo_str == "A Receber" and classificacao.tipo_movimentacao != "Entrada":
                    raise HTTPException(status_code=400, detail="Contas a Receber só podem utilizar planos de contas do tipo Entrada.")
                if tipo_str == "A Pagar" and classificacao.tipo_movimentacao == "Entrada":
                    raise HTTPException(status_code=400, detail="Contas a Pagar não podem utilizar planos de contas do tipo Entrada.")

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
        
        # 🎯 LÓGICA ESPECÍFICA: Processar retiradas do estoque (Apenas vindo do Modal de Programação)
        if model_name == "pedidos" and hasattr(validated_data, "retiradas_detalhadas") and validated_data.retiradas_detalhadas:
            # Garantimos que só processa se estiver MUDANDO para 'Produção' (para evitar duplicidade)
            if old_situacao != models.PedidoSituacaoEnum.producao and item.situacao == models.PedidoSituacaoEnum.producao:
                for retirada in validated_data.retiradas_detalhadas:
                    quantidade = retirada.get("quantidade", 0)
                    if quantidade > 0:
                        novo_movimento = models.Estoque(
                            id_produto=retirada.get("id_produto"),
                            quantidade=-abs(quantidade),  # Movimentação negativa!
                            situacao="Saída",            # Tipo Saída
                            lote=retirada.get("lote"),
                            deposito=retirada.get("deposito"),
                            observacoes=f"Retirada automática para Pedido #{item.id} (Modal Programação)",
                            id_empresa=current_user.id_empresa
                        )
                        db.add(novo_movimento)
                db.commit()
        
        # 🎯 LÓGICA ESPECÍFICA: Propagação de regras_uf em Tributacao
        # Se o usuário alterou o JSON de regras por UF (alíquotas estaduais),
        # replicamos essa configuração para TODAS as regras tributárias da empresa.
        if registry["model"].__name__ == "Tributacao" and "regras_uf" in item_data:
            try:
                new_regras_uf = getattr(validated_data, "regras_uf", {})
                
                db.query(models.Tributacao).filter(
                    models.Tributacao.id_empresa == current_user.id_empresa,
                    models.Tributacao.id != item.id
                ).update(
                    {models.Tributacao.regras_uf: new_regras_uf},
                    synchronize_session=False
                )
                db.commit()
            except Exception as e:
                print(f"Erro ao propagar regras_uf: {e}")

        # 🎯 LÓGICA ESPECÍFICA: Gerar Financeiro ao Aprovar Pedido (Programação)
        if model_name == "pedidos":
            # Se mudou para Programação (Aprovado) e não estava antes
            if old_situacao != item.situacao and item.situacao == models.PedidoSituacaoEnum.programacao:
                gerar_contas_financeiras_pedido(db, item, current_user, "Gerado automaticamente na aprovação do pedido.")
            
            # 🎯 LÓGICA ESPECÍFICA: Cancelar contas financeiras ao cancelar pedido
            if old_situacao != item.situacao and item.situacao == models.PedidoSituacaoEnum.cancelado:
                try:
                    desc_conta = f"Pedido de Venda #{item.id}"
                    # Busca contas a receber geradas para este pedido
                    contas_relacionadas = db.query(models.Conta).filter(
                        models.Conta.id_empresa == current_user.id_empresa,
                        models.Conta.tipo_conta == models.ContaTipoEnum.a_receber,
                        (models.Conta.numero_conta == str(item.id)) | (models.Conta.descricao.contains(desc_conta))
                    ).all()

                    for conta in contas_relacionadas:
                        conta.situacao = models.ContaSituacaoEnum.cancelado
                    
                    db.commit()
                except Exception as e:
                    print(f"Erro ao cancelar contas relacionadas ao pedido: {e}")

            # 🎯 LÓGICA ESPECÍFICA: Disparo de E-mails por Trigger de Status
            if old_situacao != item.situacao:
                try:
                    import asyncio
                    situacao_de_str = old_situacao.value if hasattr(old_situacao, 'value') else str(old_situacao or "")
                    situacao_para_str = item.situacao.value if hasattr(item.situacao, 'value') else str(item.situacao)
                    
                    email_svc = ElasticEmailService(db, current_user.id_empresa)
                    asyncio.run(email_svc.send_trigger_emails(
                        pedido=item,
                        situacao_de=situacao_de_str,
                        situacao_para=situacao_para_str,
                        pdf_b64=None,  # Sem NFe anexada por padrão (regras com anexar_nfe=True precisam da NFe gerada)
                        xml_str=None,
                    ))
                except Exception as e:
                    # Erro de e-mail não deve bloquear a atualização do pedido
                    import logging as _logging
                    _logging.getLogger(__name__).error(f"Erro ao disparar e-mails por trigger: {e}")

                # 🎯 LÓGICA ESPECÍFICA: Sincronização de Status com Mercado Livre
                is_ml_order = bool(getattr(item, 'meli_order_id', None) or getattr(item, 'meli_pack_id', None) or "Pedido ML:" in (item.observacao or ""))
                if is_ml_order:
                    try:
                        import asyncio
                        from app.core.service.meli_service import MeliService
                        
                        meli_svc = MeliService(db, current_user.id_empresa)
                        asyncio.run(meli_svc.update_meli_order_status(item))
                    except Exception as e:
                        import logging as _logging
                        _logging.getLogger(__name__).error(f"Erro ao sincronizar status com Mercado Livre para pedido #{item.id}: {e}")

                # 🎯 LÓGICA ESPECÍFICA: Sincronização de Status com Magento
                if "ID Magento:" in (item.observacao or ""):
                    try:
                        from app.core.service.magento_service import MagentoService
                        magento_svc = MagentoService(db, current_user.id_empresa)
                        magento_svc.update_magento_order_status(item)
                    except Exception as e:
                        import logging as _logging
                        _logging.getLogger(__name__).error(f"Erro ao sincronizar status com Magento para pedido #{item.id}: {e}")

        # 🎯 LÓGICA ESPECÍFICA: Notificação AtendAI em qualquer alteração de pedido
        if model_name == "pedidos":
            try:
                from app.core.service.atendai_service import AtendaiService
                atendai_svc = AtendaiService(db, current_user.id_empresa)
                atendai_svc.send_order_notification(item, event_type="pedido_atualizado")
            except Exception as e:
                print(f"Erro ao notificar AtendAI na atualização do pedido #{item.id}: {e}")

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
        
    # 1. Busca o item para garantir existência e serializar
    db_obj = registry["crud"].get(
        db, 
        model=registry["model"], 
        id=id, 
        id_empresa=current_user.id_empresa
    )
    
    if not db_obj:
        raise HTTPException(status_code=404, detail="Item not found")
        
    # 2. Serializa ANTES de deletar (evita DetachedInstanceError em relacionamentos lazy)
    serialized_item = registry["schema"].from_orm(db_obj)
    
    # 3. Deleta
    registry["crud"].delete(
        db, 
        model=registry["model"], 
        id=id, 
        id_empresa=current_user.id_empresa
    )
        
    return serialized_item

# --- Endpoints de Opções de Campos (CreatableSelect) ---

@router.get("/options/{model_name}/{field_name}", response_model=List[schemas.OpcaoCampo])
def list_field_options(
    model_name: str,
    field_name: str,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Lista as opções salvas para um campo específico."""
    # Lógica para compartilhar opções de 'caixa_destino_origem' entre Pedidos e Contas
    target_model = model_name
    target_field = field_name

    if field_name == 'caixa_destino_origem' and model_name == 'pedidos':
        target_model = 'contas'
    elif field_name == 'caixa_padrao' and model_name == 'meli_configuracoes':
        target_model = 'contas'
        target_field = 'caixa_destino_origem'

    return db.query(models.OpcaoCampo).filter(
        models.OpcaoCampo.model_name == target_model,
        models.OpcaoCampo.field_name == target_field,
        models.OpcaoCampo.id_empresa == current_user.id_empresa
    ).order_by(models.OpcaoCampo.valor).all()

@router.post("/options", response_model=schemas.OpcaoCampo)
def create_field_option(
    option: schemas.OpcaoCampoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Cria uma nova opção para um campo."""
    # Apenas o perfil admin pode criar novas opções para dropdowns editáveis
    if not current_user.perfil or current_user.perfil.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem criar novas opções para o dropdown."
        )

    # Lógica para compartilhar opções de 'caixa_destino_origem' entre Pedidos e Contas
    target_model = option.model_name
    target_field = option.field_name

    if option.field_name == 'caixa_destino_origem' and option.model_name == 'pedidos':
        target_model = 'contas'
    elif option.field_name == 'caixa_padrao' and option.model_name == 'meli_configuracoes':
        target_model = 'contas'
        target_field = 'caixa_destino_origem'

    # Verifica duplicidade
    existing = db.query(models.OpcaoCampo).filter(
        models.OpcaoCampo.model_name == target_model,
        models.OpcaoCampo.field_name == target_field,
        models.OpcaoCampo.valor == option.valor,
        models.OpcaoCampo.id_empresa == current_user.id_empresa
    ).first()
    
    if existing:
        return existing

    db_obj = models.OpcaoCampo(
        model_name=target_model,
        field_name=target_field,
        valor=option.valor,
        id_empresa=current_user.id_empresa
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.put("/options/{option_id}", response_model=schemas.OpcaoCampo)
def update_field_option(
    option_id: int,
    option_data: schemas.OpcaoCampoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Atualiza uma opção existente."""
    # Apenas o perfil admin pode editar opções de dropdowns editáveis
    if not current_user.perfil or current_user.perfil.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem editar opções do dropdown."
        )

    db_obj = db.query(models.OpcaoCampo).filter(models.OpcaoCampo.id == option_id, models.OpcaoCampo.id_empresa == current_user.id_empresa).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Opção não encontrada")
    db_obj.valor = option_data.valor
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/options/{option_id}")
def delete_field_option(
    option_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Remove uma opção."""
    # Apenas o perfil admin pode excluir opções de dropdowns editáveis
    if not current_user.perfil or current_user.perfil.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem excluir opções do dropdown."
        )

    db.query(models.OpcaoCampo).filter(models.OpcaoCampo.id == option_id, models.OpcaoCampo.id_empresa == current_user.id_empresa).delete()
    db.commit()
    return {"ok": True}

# --- Endpoints de Preferências de Usuário (Filtros Salvos) ---

@router.get("/preferences/{model_name}", response_model=schemas.UsuarioPreferencia)
def get_user_preferences(
    model_name: str,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Retorna as preferências salvas do usuário para um modelo específico."""
    user_id_target = current_user.id_sequencial if getattr(current_user, 'id_sequencial', None) is not None else current_user.id
    pref = db.query(models.UsuarioPreferencia).filter(
        or_(models.UsuarioPreferencia.id_usuario == user_id_target, models.UsuarioPreferencia.id_usuario == current_user.id),
        models.UsuarioPreferencia.model_name == model_name
    ).first()
    
    if not pref:
        # Retorna objeto vazio se não existir
        return schemas.UsuarioPreferencia(id=0, id_usuario=user_id_target, model_name=model_name, config={})
    
    return pref

@router.post("/preferences/{model_name}", response_model=schemas.UsuarioPreferencia)
def save_user_preferences(
    model_name: str,
    config: Dict[str, Any] = Body(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """Salva ou atualiza as preferências do usuário."""
    user_id_target = current_user.id_sequencial if getattr(current_user, 'id_sequencial', None) is not None else current_user.id
    pref = db.query(models.UsuarioPreferencia).filter(
        or_(models.UsuarioPreferencia.id_usuario == user_id_target, models.UsuarioPreferencia.id_usuario == current_user.id),
        models.UsuarioPreferencia.model_name == model_name
    ).first()
    
    if pref:
        pref.config = config
    else:
        pref = models.UsuarioPreferencia(id_usuario=user_id_target, model_name=model_name, config=config)
        db.add(pref)
    
    db.commit()
    db.refresh(pref)
    return pref

# --- Endpoint de Geração de Relatórios ---

@router.get("/reports/generate/{report_id}")
def generate_custom_report(
    report_id: int,
    model_name: str = None,
    config_json: str = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera um relatório personalizado baseado na configuração salva e retorna um CSV.
    """
    # 1. Busca ou monta a configuração do relatório
    if report_id > 0:
        relatorio = db.query(models.Relatorio).filter(
            models.Relatorio.id == report_id,
            models.Relatorio.id_empresa == current_user.id_empresa
        ).first()

        if not relatorio:
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")
        
        modelo_base = relatorio.modelo
        config = relatorio.config or {}
        report_name = relatorio.nome
    else:
        if not model_name or not config_json:
            raise HTTPException(status_code=400, detail="Para report_id=0, model_name e config_json são obrigatórios.")
        
        modelo_base = model_name
        try:
            config = json.loads(config_json)
        except:
            raise HTTPException(status_code=400, detail="config_json inválido.")
        
        report_name = config.get('report_name', f"Exportação {model_name}")

    # 2. Identifica o modelo base
    registry = get_registry_entry(modelo_base)
    if not registry:
        raise HTTPException(status_code=400, detail=f"Modelo base '{modelo_base}' inválido.")
    
    Model = registry["model"]
    
    # 3. Inicia a Query
    query = db.query(Model).filter(Model.id_empresa == current_user.id_empresa)
    
    # --- JOINS (Tabelas Referenciadas) ---
    joins_needed = set()
    
    # Analisa colunas e filtros para descobrir joins implícitos
    columns_config = config.get('columns', [])
    for col in columns_config:
        field_path = col.get('field', '').split('.')
        if len(field_path) > 1:
            joins_needed.add(field_path[0]) # Ex: 'cliente' de 'cliente.nome_razao'

    filters_config = config.get('filters', [])
    for f in filters_config:
        field_path = f.get('field', '').split('.')
        if len(field_path) > 1:
            joins_needed.add(field_path[0])

    # Aplica Joins
    relation_aliases = {}
    for relation_name in joins_needed:
        if hasattr(Model, relation_name):
            rel_attr = getattr(Model, relation_name)
            if hasattr(rel_attr, 'property') and hasattr(rel_attr.property, 'mapper'):
                related_model = rel_attr.property.mapper.class_
                rel_alias = aliased(related_model, name=relation_name)
                query = query.outerjoin(rel_alias, rel_attr)
                relation_aliases[relation_name] = rel_alias

    # --- LÓGICA ESPECIAL PARA ESTOQUE (INJEÇÃO DE CUSTO/TOTAL) ---
    if modelo_base == "estoque":
        p_alias = relation_aliases.get("produto")
        if p_alias is not None:
            query = query.add_columns(p_alias.custo.label("_custo_v"))
        else:
            query = query.outerjoin(models.Produto, Model.id_produto == models.Produto.id)
            query = query.add_columns(models.Produto.custo.label("_custo_v"))

    # --- FILTROS ---
    filter_list = config.get('filters', [])
    filters_by_field = {}
    for f in filter_list:
        fname = f.get("field")
        if fname:
            if fname not in filters_by_field: filters_by_field[fname] = []
            filters_by_field[fname].append(f)

    for field_raw, field_filters in filters_by_field.items():
        field_conditions = []
        
        # Resolve o atributo (Model.campo ou RelatedModel.campo)
        parts = field_raw.split('.')
        if len(parts) == 1:
            attr = getattr(Model, parts[0], None)
        else:
            rel_name = parts[0]
            field_name = parts[1]
            if rel_name in relation_aliases:
                attr = getattr(relation_aliases[rel_name], field_name, None)
            else:
                attr = None
        
        if not attr: continue

        for f in field_filters:
            operator = f.get('operator')
            value = f.get('value')
            
            if operator == 'equals':
                if isinstance(value, str) and "," in value:
                    vals = [v.strip() for v in value.split(",")]
                    field_conditions.append(attr.in_(vals))
                else:
                    field_conditions.append(attr == value)
            elif operator == 'in':
                vals = [v.strip() for v in str(value).split(",")] if isinstance(value, str) else value
                field_conditions.append(attr.in_(vals))
            elif operator == 'contains': field_conditions.append(cast(attr, String).ilike(f"%{value}%"))
            elif operator == 'gt': field_conditions.append(attr > value)
            elif operator == 'gte': field_conditions.append(attr >= value)
            elif operator == 'lt': field_conditions.append(attr < value)
            elif operator == 'lte': field_conditions.append(attr <= value)
            elif operator == 'is_true': field_conditions.append(attr == True)
            elif operator == 'is_false': field_conditions.append(attr == False)
            elif operator == 'neq': field_conditions.append(attr != value)
            elif operator == 'today':
                today = date.today()
                field_conditions.append(cast(attr, Date) == today)
            elif operator == 'last_days':
                try:
                    days = int(value)
                except:
                    days = 0
                today = date.today()
                field_conditions.append(and_(cast(attr, Date) >= today - timedelta(days=days), cast(attr, Date) <= today))
        
        if field_conditions:
            if all(f.get("operator") in ["equals", "in"] for f in field_filters):
                query = query.filter(or_(*field_conditions))
            else:
                query = query.filter(and_(*field_conditions))

    # --- ORDENAÇÃO ---
    sorts = config.get('sort', [])
    for s in sorts:
        field_raw = s.get('field')
        direction = s.get('direction', 'asc')
        if not field_raw: continue
        
        parts = field_raw.split('.')
        if len(parts) == 1:
            attr = getattr(Model, parts[0], None)
        else:
            rel_name = parts[0]
            field_name = parts[1]
            if rel_name in relation_aliases:
                attr = getattr(relation_aliases[rel_name], field_name, None)
            else:
                attr = None
                
        if attr is not None:
            needs_numeric_sort = any(kw in field_raw.lower() for kw in ['numero', 'nsu', 'cep', 'cpf_cnpj'])
            if direction == 'desc':
                if needs_numeric_sort:
                    query = query.order_by(func.length(cast(attr, String)).desc().nulls_last(), attr.desc().nulls_last())
                else:
                    query = query.order_by(attr.desc().nulls_last())
            else:
                if needs_numeric_sort:
                    query = query.order_by(func.length(cast(attr, String)).asc().nulls_last(), attr.asc().nulls_last())
                else:
                    query = query.order_by(attr.asc().nulls_last())

    # Executa a query
    raw_results = query.all()
    results = []
    if modelo_base == "estoque":
        for row in raw_results:
            obj = row[0]
            custo = float(row[1] or 0)
            # Injeta campos virtuais para o extrator de colunas
            setattr(obj, "custo", custo)
            setattr(obj, "valor_total", custo * obj.quantidade)
            results.append(obj)
    else:
        results = raw_results

    # --- GERAÇÃO DO CSV ---
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';') # Ponto e vírgula para Excel PT-BR

    # Cabeçalho
    headers = [c.get('label', c.get('field')) for c in columns_config]
    writer.writerow(headers)

    def format_val(v):
        if isinstance(v, enum.Enum):
            if hasattr(v, "description"): return v.description
            if isinstance(v.value, str): return v.value
            return v.name.replace('_', ' ').title()
        if isinstance(v, (Decimal, float)):
            return f"{v:.2f}".replace('.', ',')
        return v

    # Linhas
    for row in results:
        processed_values = [] # Lista de tuplas (valor, is_expanded)
        num_rows_for_this_record = 1

        for col in columns_config:
            field_path = col.get('field', '').split('.')
            val = row
            
            # Navega no objeto (ex: pedido.cliente.nome)
            for part in field_path:
                val = getattr(val, part, None)
                if val is None: break
            
            # Extração de JSON (se configurado)
            is_expanded = False
            if col.get('json_key') and isinstance(val, (dict, list)):
                if isinstance(val, dict):
                    val = val.get(col['json_key'])
                elif isinstance(val, list):
                    # Extrai a chave de cada item e mantém como lista para expansão de linhas
                    extracted = []
                    for item in val:
                        if isinstance(item, dict):
                            extracted.append(item.get(col['json_key']))
                        else:
                            extracted.append(item)
                    val = extracted
                    is_expanded = True
                    num_rows_for_this_record = max(num_rows_for_this_record, len(val))
            
            # Formatação de Enums e Valores Numéricos (suporta listas expandidas)
            if is_expanded:
                val = [format_val(v) for v in val]
            else:
                val = format_val(val)

            processed_values.append((val, is_expanded))

        # Gera as linhas expandidas (uma para cada item na lista JSON, ou uma se não houver lista)
        for i in range(num_rows_for_this_record):
            csv_row = []
            for val, is_expanded in processed_values:
                if is_expanded:
                    # Pega o item correspondente ao índice atual da lista JSON
                    cell_val = val[i] if i < len(val) else ""
                else:
                    # Repete a informação para as outras colunas (ex: ID do Pedido)
                    cell_val = val
                
                csv_row.append(str(cell_val) if cell_val is not None else "")
            writer.writerow(csv_row)

    output.seek(0)
    # Nome do arquivo baseado no nome do relatório + data e hora (DD_MM_AAAA_HHMMSS)
    timestamp = datetime.now(TZ_BR).strftime("%d_%m_%Y_%H%M%S")
    report_name_clean = report_name.replace(' ', '_')
    filename = f"{report_name_clean}_{timestamp}.csv"
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')), # BOM para Excel
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/reports/generate-xml/{report_id}")
def generate_xml_report(
    report_id: int,
    model_name: str = None,
    config_json: str = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Gera um relatório personalizado de XMLs e retorna um arquivo ZIP.
    Apenas válido para pedidos.
    """
    # 1. Busca ou monta a configuração do relatório
    if report_id > 0:
        relatorio = db.query(models.Relatorio).filter(
            models.Relatorio.id == report_id,
            models.Relatorio.id_empresa == current_user.id_empresa
        ).first()

        if not relatorio:
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")
        
        modelo_base = relatorio.modelo
        config = relatorio.config or {}
        report_name = relatorio.nome
    else:
        if not model_name or not config_json:
            raise HTTPException(status_code=400, detail="Para report_id=0, model_name e config_json são obrigatórios.")
        
        modelo_base = model_name
        try:
            config = json.loads(config_json)
        except:
            raise HTTPException(status_code=400, detail="config_json inválido.")
        
        report_name = config.get('report_name', f"Exportação {model_name}")

    if modelo_base != "pedidos":
        raise HTTPException(status_code=400, detail="Apenas relatórios de Pedidos podem exportar XML.")

    # 2. Identifica o modelo base
    registry = get_registry_entry(modelo_base)
    if not registry:
        raise HTTPException(status_code=400, detail=f"Modelo base '{modelo_base}' inválido.")
    
    Model = registry["model"]
    
    # 3. Inicia a Query
    query = db.query(Model).filter(Model.id_empresa == current_user.id_empresa)
    
    # --- JOINS (Tabelas Referenciadas) ---
    joins_needed = set()
    
    # Analisa colunas e filtros para descobrir joins implícitos
    columns_config = config.get('columns', [])
    for col in columns_config:
        field_path = col.get('field', '').split('.')
        if len(field_path) > 1:
            joins_needed.add(field_path[0])

    filters_config = config.get('filters', [])
    for f in filters_config:
        field_path = f.get('field', '').split('.')
        if len(field_path) > 1:
            joins_needed.add(field_path[0])

    # Aplica Joins
    relation_aliases = {}
    for relation_name in joins_needed:
        if hasattr(Model, relation_name):
            rel_attr = getattr(Model, relation_name)
            if hasattr(rel_attr, 'property') and hasattr(rel_attr.property, 'mapper'):
                related_model = rel_attr.property.mapper.class_
                rel_alias = aliased(related_model, name=relation_name)
                query = query.outerjoin(rel_alias, rel_attr)
                relation_aliases[relation_name] = rel_alias

    # --- FILTROS ---
    filter_list = config.get('filters', [])
    filters_by_field = {}
    for f in filter_list:
        fname = f.get("field")
        if fname:
            if fname not in filters_by_field: filters_by_field[fname] = []
            filters_by_field[fname].append(f)

    for field_raw, field_filters in filters_by_field.items():
        field_conditions = []
        
        # Resolve o atributo (Model.campo ou RelatedModel.campo)
        parts = field_raw.split('.')
        if len(parts) == 1:
            attr = getattr(Model, parts[0], None)
        else:
            rel_name = parts[0]
            field_name = parts[1]
            if rel_name in relation_aliases:
                attr = getattr(relation_aliases[rel_name], field_name, None)
            else:
                attr = None
        
        if not attr: continue

        for f in field_filters:
            operator = f.get('operator')
            value = f.get('value')
            
            if operator == 'equals':
                if isinstance(value, str) and "," in value:
                    vals = [v.strip() for v in value.split(",")]
                    field_conditions.append(attr.in_(vals))
                else:
                    field_conditions.append(attr == value)
            elif operator == 'in':
                vals = [v.strip() for v in str(value).split(",")] if isinstance(value, str) else value
                field_conditions.append(attr.in_(vals))
            elif operator == 'contains': field_conditions.append(cast(attr, String).ilike(f"%{value}%"))
            elif operator == 'gt': field_conditions.append(attr > value)
            elif operator == 'gte': field_conditions.append(attr >= value)
            elif operator == 'lt': field_conditions.append(attr < value)
            elif operator == 'lte': field_conditions.append(attr <= value)
            elif operator == 'is_true': field_conditions.append(attr == True)
            elif operator == 'is_false': field_conditions.append(attr == False)
            elif operator == 'neq': field_conditions.append(attr != value)
            elif operator == 'today':
                today = date.today()
                field_conditions.append(cast(attr, Date) == today)
            elif operator == 'last_days':
                try:
                    days = int(value)
                except:
                    days = 0
                today = date.today()
                field_conditions.append(and_(cast(attr, Date) >= today - timedelta(days=days), cast(attr, Date) <= today))
        
        if field_conditions:
            if all(f.get("operator") in ["equals", "in"] for f in field_filters):
                query = query.filter(or_(*field_conditions))
            else:
                query = query.filter(and_(*field_conditions))

    # --- ORDENAÇÃO ---
    sorts = config.get('sort', [])
    for s in sorts:
        field_raw = s.get('field')
        direction = s.get('direction', 'asc')
        if not field_raw: continue
        
        parts = field_raw.split('.')
        if len(parts) == 1:
            attr = getattr(Model, parts[0], None)
        else:
            rel_name = parts[0]
            field_name = parts[1]
            if rel_name in relation_aliases:
                attr = getattr(relation_aliases[rel_name], field_name, None)
            else:
                attr = None
                
        if attr is not None:
            needs_numeric_sort = any(kw in field_raw.lower() for kw in ['numero', 'nsu', 'cep', 'cpf_cnpj'])
            if direction == 'desc':
                if needs_numeric_sort:
                    query = query.order_by(func.length(cast(attr, String)).desc().nulls_last(), attr.desc().nulls_last())
                else:
                    query = query.order_by(attr.desc().nulls_last())
            else:
                if needs_numeric_sort:
                    query = query.order_by(func.length(cast(attr, String)).asc().nulls_last(), attr.asc().nulls_last())
                else:
                    query = query.order_by(attr.asc().nulls_last())

    # Executa a query
    results = query.all()

    # --- GERAÇÃO DO ZIP ---
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for row in results:
            if isinstance(row, models.Pedido):
                pedido = row
            elif hasattr(row, '__getitem__'): # se for row[0]
                pedido = row[0]
            else:
                pedido = row

            xml_content = getattr(pedido, 'xml_autorizado', None)
            if not xml_content:
                xml_content = '<?xml version="1.0" encoding="UTF-8"?><nfe><info>XML nao gerado para este pedido</info></nfe>'

            chave = getattr(pedido, 'chave_acesso', None)
            if chave:
                xml_filename = f"nfe-{chave}.xml"
            else:
                numero_nf = getattr(pedido, 'numero_nf', None)
                if numero_nf:
                    xml_filename = f"nfe-sem_chave-nf_{numero_nf}.xml"
                else:
                    xml_filename = f"nfe-pedido_{pedido.id}_sem_nf.xml"
            
            zip_file.writestr(xml_filename, xml_content)

    output.seek(0)
    
    timestamp = datetime.now(TZ_BR).strftime("%d_%m_%Y_%H%M%S")
    report_name_clean = report_name.replace(' ', '_')
    filename = f"{report_name_clean}_{timestamp}_xmls.zip"
    
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )