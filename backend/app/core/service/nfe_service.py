import os
import re
import asyncio
import gzip
import io
import base64
import tempfile
import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone
import logging
from decimal import Decimal


# Constante global para o fuso horário de Brasília
TZ_BR = timezone(timedelta(hours=-3))
from typing import Tuple
import time # Importar para usar time.sleep()
from lxml import etree

from fastapi import HTTPException
from sqlalchemy.orm import Session

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.entidades.cliente import Cliente
from pynfe.entidades.emitente import Emitente
from pynfe.entidades.transportadora import Transportadora
from pynfe.entidades.notafiscal import NotaFiscal
from pynfe.entidades.evento import EventoCancelarNota, EventoCartaCorrecao
from pynfe.entidades.fonte_dados import _fonte_dados
from pynfe.processamento.serializacao import SerializacaoXML
from pynfe.processamento.assinatura import AssinaturaA1
from pynfe.utils.flags import CODIGO_BRASIL

from app.core.config import settings
from app.core.service.meli_service import MeliService
from app.core.service.intelipost_service import IntelipostService
from app.core.service.elastic_email_service import ElasticEmailService
from app.core.db import models
from app.core.db.models import (
    PedidoSituacaoEnum, RegraRegimeEmitenteEnum, RegraTipoOperacaoEnum,
    RegraTipoClienteEnum, RegraLocalizacaoDestinoEnum, CadastroIndicadorIEEnum,
    CadastroTipoPessoaEnum, FiscalPagamentoEnum, FiscalOrigemEnum,
    PedidoIndicadorPresencaEnum
)

logger = logging.getLogger(__name__)

# Cache em memória para gerenciar o cooldown da SEFAZ e evitar o erro 656
_cooldown_sefaz = {}

def debug_xml_erro_schema(xml_input, erro_msg: str):
    """
    Analisa a mensagem de erro do SAX/Schema, extrai a linha e coluna,
    e imprime o trecho exato do XML onde o erro ocorreu.
    Aceita string, bytes ou objeto lxml.etree._Element.
    """
    try:
        # 1. Normalização da entrada para String
        xml_str = ""
        if hasattr(xml_input, 'xpath') or hasattr(xml_input, 'tag'):
            # É um objeto lxml, converte para string
            xml_str = etree.tostring(xml_input, encoding='unicode')
        elif isinstance(xml_input, bytes):
            xml_str = xml_input.decode('utf-8', errors='ignore')
        else:
            xml_str = str(xml_input)

        # Regex para capturar coluna e linha (padrão Java SAX / lxml)
        # Ex: "... lineNumber: 1; columnNumber: 4395; ..."
        match = re.search(r'lineNumber:\s*(\d+);\s*columnNumber:\s*(\d+)', str(erro_msg))
        
        if match:
            line_num = int(match.group(1))
            col_num = int(match.group(2))
            
            lines = xml_str.split('\n')
            
            # Se for linha única (minificado) e linha 1
            if len(lines) == 1 and line_num == 1:
                total_len = len(xml_str)
                # Pega um contexto maior (150 caracteres)
                start = max(0, col_num - 150) 
                end = min(total_len, col_num + 150) 
                
                snippet = xml_str[start:end]
                # Calcula onde apontar a seta
                pointer_idx = col_num - start - 1
                pointer = " " * pointer_idx + "^ AQUI"
                
                log_text = (
                    f"\n{'='*40}\n"
                    f"ERRO DE SCHEMA XML (Col: {col_num})\n"
                    f"Contexto:\n{snippet}\n{pointer}\n"
                    f"{'='*40}"
                )
                logger.error(log_text)
                print(log_text) # Garante output no stdout
            else:
                # Logica para XML formatado (multi-linhas)
                if 0 <= line_num - 1 < len(lines):
                    log_text = f"Erro na linha {line_num}: {lines[line_num-1]}"
                    logger.error(log_text)
        
        # Check especial para o erro "None"
        if "Value 'None'" in str(erro_msg):
            logger.error("ALERTA CRÍTICO: O valor 'None' (string) foi encontrado no XML.")

    except Exception as e:
        logger.error(f"Falha interna ao gerar debug do XML: {e}")

def log_xml_pretty(xml_content, level="ERROR"):
    """Formata e loga o XML de forma legível"""
    try:
        if isinstance(xml_content, str):
            xml_content = xml_content.encode('utf-8')
            
        parser = etree.XMLParser(remove_blank_text=True)
        elem = etree.fromstring(xml_content, parser=parser)
        xml_pretty = etree.tostring(elem, pretty_print=True, encoding='unicode')
        
        msg = f"\n--- XML COMPLETO ({level}) ---\n{xml_pretty}\n-----------------------------"
        if level == "ERROR":
            logger.error(msg)
        else:
            logger.info(msg)
    except Exception as e:
        logger.error(f"Não foi possível formatar o XML: {e}")

def safe_decimal(val, default="0.00") -> Decimal:
    if val is None:
        return Decimal(default)
    val_str = str(val).strip()
    if val_str == "" or val_str.lower() == "none":
        return Decimal(default)
    try:
        val_str = val_str.replace(",", ".").replace("R$", "").strip()
        return Decimal(val_str)
    except Exception:
        return Decimal(default)

class NFeService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        
        self.empresa = self.db.query(models.Empresa).filter(models.Empresa.id == id_empresa).first()
        if not self.empresa:
            raise HTTPException(status_code=400, detail="Empresa não encontrada.")
            
        if not self.empresa.certificado_arquivo or not self.empresa.certificado_senha:
            raise HTTPException(status_code=400, detail="Certificado digital ou senha não configurados na empresa.")

    def _get_certificado_path(self) -> str:
        """
        Escreve o certificado (bytes) em um arquivo temporário para o PyNFE ler.
        O chamador deve remover o arquivo após o uso.
        """
        try:
            content = self.empresa.certificado_arquivo
            
            # Verifica se o conteúdo precisa ser decodificado de Base64
            # PFX binário geralmente começa com 0x30 (Sequence ASN.1)
            # Se não começar com 0x30, tentamos decodificar base64
            if content and len(content) > 0 and content[0] != 0x30:
                try:
                    decoded = base64.b64decode(content, validate=True)
                    content = decoded
                except Exception:
                    pass

            # Cria um arquivo temporário .pfx
            # delete=False pois precisamos do caminho para passar para a lib, 
            # e ela vai abrir o arquivo. Se delete=True, ao fechar aqui ele sumiria.
            tmp = tempfile.NamedTemporaryFile(suffix=".pfx", delete=False)
            tmp.write(content)
            tmp.close()
            return tmp.name
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo do certificado: {str(e)}")

    def _limpar_formatacao(self, valor: str) -> str:
        if not valor:
            return ""
        return "".join(c for c in str(valor) if c.isalnum()).upper()

    def _limpar_texto(self, valor: str, max_len: int = None) -> str:
        if not valor:
            return ""
        
        # Converte para string
        valor = str(valor)
        
        # Normalização de pontuações comuns fora do range latin1/ASCII
        valor = valor.replace("–", "-").replace("—", "-")
        valor = valor.replace("“", '"').replace("”", '"')
        valor = valor.replace("‘", "'").replace("’", "'")
        
        # Filtra mantendo apenas caracteres no range da SEFAZ (espaço a ÿ)
        valor_filtrado = "".join(c for c in valor if "\x20" <= c <= "\xff")
        
        # Substitui múltiplos espaços (inclusive quebras de linha/abas) por um único espaço e limpa as pontas
        cleaned = re.sub(r'\s+', ' ', valor_filtrado).strip()
        
        if max_len is not None:
            cleaned = cleaned[:max_len].strip()
            
        return cleaned

    def _to_decimal(self, val) -> Decimal:
        if val is None:
            return Decimal('0.00')
        val_str = str(val).strip().replace(',', '.')
        if not val_str or val_str == 'None':
            return Decimal('0.00')
        try:
            return Decimal(val_str)
        except:
            return Decimal('0.00')

    def _gerar_danfe(self, xml_nfe, nProt: str, dhRecbto: str, chNFe: str, c=None, is_cancelada: bool = False) -> str:
        """
        Gera DANFE Final: Layout ajustado, textos contidos e espaçamentos corrigidos.
        """
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.graphics.barcode import code128
            from reportlab.lib.utils import ImageReader
            from reportlab.lib.utils import simpleSplit
            import textwrap

            # --- Configurações ---
            FONT_REGULAR = "Helvetica"
            FONT_BOLD = "Helvetica-Bold"
            
            if isinstance(xml_nfe, (str, bytes)):
                xml_nfe = etree.fromstring(xml_nfe)

            save_pdf = False
            if c is None:
                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=A4)
                c.setTitle(f"DANFE_{chNFe}.pdf")
                save_pdf = True
                
            w_page, h_page = A4
            
            ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
            
            # --- Helpers ---
            def get_val(node, xpath):
                try:
                    r = node.xpath(xpath, namespaces=ns)
                    if r:
                        return r[0].text.upper() if r[0].text else ""
                    return ""
                except:
                    return ""

            def format_currency(value):
                try:
                    val = float(value)
                    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                except:
                    return "0,00"

            def format_date(date_str):
                try:
                    if 'T' in date_str:
                        date_obj = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
                        return date_obj.strftime('%d/%m/%Y')
                    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    return ""
            
            def format_doc(value):
                v = str(value)
                if len(v) == 14: return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
                if len(v) == 11: return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"
                return v

            def format_protocolo(n_prot, dh_recbto):
                try:
                    # Formato esperado: "2026-01-21T14:24:50-03:00"
                    if dh_recbto and 'T' in str(dh_recbto):
                        val_str = str(dh_recbto)
                        # 1. Separa Data (YYYY-MM-DD) da Hora (HH:MM:SS...)
                        partes = val_str.split('T')
                        data_iso = partes[0]  # "2026-01-21"
                        hora_suja = partes[1] # "14:24:50-03:00" ou "14:24:50"

                        # 2. Formata Data
                        ano, mes, dia = data_iso.split('-')
                        
                        # 3. Limpa Hora (remove fuso horário - ou +)
                        hora = hora_suja.split('-')[0].split('+')[0]
                        
                        return f"{n_prot} - {dia}/{mes}/{ano} {hora}"
                    
                    return f"{n_prot} - {dh_recbto}"
                except:
                    # Fallback em caso de erro no parse
                    return f"{n_prot} - {dh_recbto}"

            # --- NOVA FUNÇÃO DE DESENHO DE TEXTO SEGURO ---
            # --- NOVA FUNÇÃO DE DESENHO DE TEXTO SEGURO (Com margem esquerda ajustada) ---
            def draw_text_fitted(c, x, y, w, text, font_name=FONT_REGULAR, max_size=8, min_size=5, align='left'):
                """
                Desenha texto tentando reduzir a fonte. Agora com recuo esquerdo maior.
                """
                text = str(text).strip()
                if not text: return 0
                
                curr_size = max_size
                # Margem de segurança para cálculo de largura (evita estourar a caixa)
                padding_calc = 2 * mm 
                
                # 1. Redução de Fonte
                while curr_size >= min_size:
                    c.setFont(font_name, curr_size)
                    txt_w = c.stringWidth(text, font_name, curr_size)
                    if txt_w <= (w - padding_calc):
                        break 
                    curr_size -= 0.5
                
                # 2. Truncamento
                c.setFont(font_name, curr_size)
                if c.stringWidth(text, font_name, curr_size) > (w - padding_calc):
                    while len(text) > 0 and c.stringWidth(text + "...", font_name, curr_size) > (w - padding_calc):
                        text = text[:-1]
                    text += "..."
                
                final_w = c.stringWidth(text, font_name, curr_size)
                
                # 3. Desenho e Alinhamento
                draw_x = x
                if align == 'center':
                    draw_x = x + (w - final_w) / 2
                elif align == 'right':
                    draw_x = x + w - final_w - 1*mm 
                else: # left
                    # CORREÇÃO: Aumentei para 1.5mm para o texto não colar na borda
                    draw_x = x + 1.5*mm 

                c.drawString(draw_x, y, text)
                return final_w

            def draw_field(x, y, w, h, title, value, align='left', font_size_val=8, bold_val=False, title_size=5):
                c.setLineWidth(0.5)
                c.rect(x, y, w, h)
                
                # Título (fixo no topo)
                c.setFont(FONT_REGULAR, title_size)
                c.drawString(x + 1*mm, y + h - 2.5*mm, title.upper())
                
                # Valor (centralizado verticalmente na área restante)
                title_space = 3*mm
                usable_h = h - title_space
                font_name = FONT_BOLD if bold_val else FONT_REGULAR
                
                # Estima altura da fonte para centralizar Y
                # Como a fonte pode variar no draw_text_fitted, usamos uma média visual
                y_text = y + (usable_h / 2) - (font_size_val / 3.5) # Ajuste fino vertical
                
                draw_text_fitted(c, x, y_text, w, value, font_name, max_size=font_size_val, min_size=5, align=align)

            # ==============================================================================
            # EXTRAÇÃO XML
            # ==============================================================================
            emit = xml_nfe.xpath('//ns:emit', namespaces=ns)[0]
            dest_nodes = xml_nfe.xpath('//ns:dest', namespaces=ns)
            dest = dest_nodes[0] if dest_nodes else None
            ide = xml_nfe.xpath('//ns:ide', namespaces=ns)[0]
            total = xml_nfe.xpath('//ns:total/ns:ICMSTot', namespaces=ns)[0]
            transp_nodes = xml_nfe.xpath('//ns:transp', namespaces=ns)
            transp = transp_nodes[0] if transp_nodes else None

            items = xml_nfe.xpath('//ns:det', namespaces=ns)
            total_items = len(items)

            # --- LÓGICA DE PAGINAÇÃO AVANÇADA ---
            items_per_page = []
            remaining = total_items
            while True:
                is_p1 = len(items_per_page) == 0
                if is_p1:
                    if remaining <= 18:
                        items_per_page.append(remaining)
                        break
                    else:
                        take = min(23, remaining)
                        items_per_page.append(take)
                        remaining -= take
                else:
                    if remaining <= 33:
                        items_per_page.append(remaining)
                        break
                    else:
                        take = min(37, remaining)
                        items_per_page.append(take)
                        remaining -= take
            
            total_paginas = len(items_per_page)

            item_idx = 0

            # ==============================================================================
            # LOOP DE DESENHO DAS PÁGINAS
            # ==============================================================================
            for pagina_atual in range(1, total_paginas + 1):
                left_m = 10*mm
                top_m = h_page - 10*mm
                cur_y = top_m
                content_w = w_page - 20*mm
                
                # Variáveis fixas de rodapé para cálculo do grid (padronizado)
                h_foot = 25.5*mm       
                y_foot_start = 12*mm   
                
                if pagina_atual == total_paginas:
                    y_limit_grid = y_foot_start + h_foot + 2*mm 
                else:
                    y_limit_grid = y_foot_start + 2*mm # Estica a tabela até embaixo

                # 1. CANHOTO (Layout conforme Imagem de Exemplo)
                h_sect = 20*mm # Aumentei levemente para 20mm para caber as duas linhas confortavelmente
                cur_y -= h_sect
                c.rect(left_m, cur_y, content_w, h_sect)
                
                # --- DIVISÕES ESTRUTURAIS ---
                w_nfe_box = 30*mm
                x_nfe_box = left_m + content_w - w_nfe_box
                w_left_area = content_w - w_nfe_box
                h_bottom_row = 7*mm # Altura da linha de assinatura
                y_div_horiz = cur_y + h_bottom_row
                
                # Linha Vertical separando a caixa da NF-e (Direita)
                c.line(x_nfe_box, cur_y, x_nfe_box, cur_y + h_sect)
                
                # Linha Horizontal separando Texto (Topo) de Assinatura (Baixo) na área esquerda
                c.line(left_m, y_div_horiz, x_nfe_box, y_div_horiz)
                
                # Linha Vertical separando Data de Recebimento (Baixo Esquerda)
                w_data_rec = 35*mm
                c.line(left_m + w_data_rec, cur_y, left_m + w_data_rec, y_div_horiz)

                # --- CONTEÚDO SUPERIOR (TEXTOS CENTRALIZADOS) ---
                # Linha 1: Recebemos de...
                msg_linha1 = f"RECEBEMOS DE {get_val(emit, 'ns:xNome')} OS PRODUTOS/SERVIÇOS CONSTANTES DA NOTA FISCAL INDICADA AO LADO"
                
                # Linha 2: Resumo (Emissão, Destinatário, Valor)
                dt_emi = format_date(get_val(ide, 'ns:dhEmi'))
                dest_nome = get_val(dest, 'ns:xNome') or "CONSUMIDOR"
                v_total = format_currency(get_val(total, 'ns:vNF'))
                msg_linha2 = f"EMISSÃO: {dt_emi} - DEST. / REM.: {dest_nome} - VALOR TOTAL: R$ {v_total}"

                # Desenha centralizado na área disponível (superior esquerda)
                center_x_text = left_m + (w_left_area / 2)
                
                # Ajuste fino de Y para as duas linhas
                y_text1 = cur_y + h_sect - 4*mm
                y_text2 = cur_y + h_sect - 8*mm
                
                # Usa draw_text_fitted com align='center' para garantir que não corte
                draw_text_fitted(c, left_m + 1*mm, y_text1, w_left_area - 2*mm, msg_linha1, FONT_REGULAR, max_size=7, min_size=5, align='center')
                draw_text_fitted(c, left_m + 1*mm, y_text2, w_left_area - 2*mm, msg_linha2, FONT_REGULAR, max_size=7, min_size=5, align='center')

                # --- CONTEÚDO INFERIOR (CAMPOS DE ASSINATURA) ---
                # Data de Recebimento
                c.setFont(FONT_REGULAR, 5)
                c.drawString(left_m + 1*mm, cur_y + h_bottom_row - 2.5*mm, "DATA DE RECEBIMENTO")
                
                # Identificação e Assinatura
                c.drawString(left_m + w_data_rec + 1*mm, cur_y + h_bottom_row - 2.5*mm, "IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR")

                # --- CAIXA NF-E (DIREITA) ---
                center_nfe = x_nfe_box + (w_nfe_box / 2)
                c.setFont(FONT_BOLD, 12)
                c.drawCentredString(center_nfe, cur_y + 14*mm, "NF-e")
                c.setFont(FONT_BOLD, 9)
                c.drawCentredString(center_nfe, cur_y + 9*mm, f"Nº {get_val(ide, 'ns:nNF')}")
                c.drawCentredString(center_nfe, cur_y + 5*mm, f"SÉRIE {get_val(ide, 'ns:serie')}")
                
                cur_y -= 4*mm

                # 2. CABEÇALHO (Emitente + DANFE + Chave)
                h_header = 32*mm
                base_header_y = cur_y - h_header
                
                # --- CAIXA EMITENTE (Lado Esquerdo) ---
                w_emit_box = 85*mm
                c.rect(left_m, base_header_y, w_emit_box, h_header)
                
                # Label pequeno no topo (Fixo)
                c.setFont(FONT_REGULAR, 5)
                c.drawString(left_m + 1*mm, base_header_y + h_header - 2.5*mm, "IDENTIFICAÇÃO DO EMITENTE")

                # --- PREPARAÇÃO DO CONTEÚDO (Strings e Configurações) ---
                # Vamos montar uma lista de linhas para calcular a altura total antes de desenhar
                
                # Dados básicos
                nm_emit = get_val(emit, 'ns:xNome')
                nm_fant = get_val(emit, 'ns:xFant')
                
                lgr = get_val(emit, 'ns:enderEmit/ns:xLgr')
                nro = get_val(emit, 'ns:enderEmit/ns:nro')
                cpl = get_val(emit, 'ns:enderEmit/ns:xCpl')
                bairro = get_val(emit, 'ns:enderEmit/ns:xBairro')
                mun = get_val(emit, 'ns:enderEmit/ns:xMun')
                uf = get_val(emit, 'ns:enderEmit/ns:UF')
                cep = get_val(emit, 'ns:enderEmit/ns:CEP')
                fone = get_val(emit, 'ns:enderEmit/ns:fone')

                # Formatação das Linhas
                line_end = f"{lgr}, {nro}"
                if cpl: line_end += f" - {cpl}"
                line_cid = f"{bairro} - {mun} / {uf}"
                
                line_contact = ""
                if cep: 
                    cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep
                    line_contact += f"CEP: {cep_fmt}"
                if fone:
                    if line_contact: line_contact += " - "
                    line_contact += f"Fone: {fone}"

                # Lista de Objetos de Texto (Texto, Fonte, Tamanho Max, Altura da Linha)
                lines_to_draw = []
                
                # 1. Razão Social (Maior destaque)
                lines_to_draw.append({"text": nm_emit, "font": FONT_BOLD, "max": 9, "min": 6, "step": 4*mm})
                
                # 2. Nome Fantasia (Opcional)
                if nm_fant:
                     lines_to_draw.append({"text": nm_fant, "font": FONT_REGULAR, "max": 8, "min": 5, "step": 3.5*mm})
                
                # 3. Endereço
                lines_to_draw.append({"text": line_end, "font": FONT_REGULAR, "max": 7, "min": 5, "step": 3*mm})
                lines_to_draw.append({"text": line_cid, "font": FONT_REGULAR, "max": 7, "min": 5, "step": 3*mm})
                lines_to_draw.append({"text": line_contact, "font": FONT_REGULAR, "max": 7, "min": 5, "step": 3*mm})

                # --- LÓGICA DE POSICIONAMENTO E LOGO ---
                img_w = 26*mm
                img_h = 22*mm
                margin_logo = 2*mm
                has_logo = False
                
                # Área de texto padrão (Centralizado na caixa total)
                text_x = left_m + 2*mm
                text_w = w_emit_box - 4*mm
                
                # Tenta carregar logo
                if self.empresa.url_logo:
                    try:
                        logo_data = self.empresa.url_logo
                        if logo_data.startswith("data:"):
                            try:
                                header, base64_data = logo_data.split(",", 1)
                                decoded_bytes = base64.b64decode(base64_data)
                                logo_img = ImageReader(io.BytesIO(decoded_bytes))
                            except Exception as decode_err:
                                print(f"Erro ao decodificar logo em base64: {decode_err}")
                                logo_img = ImageReader(logo_data)
                        else:
                            logo_img = ImageReader(logo_data)
                            
                        # Centraliza Logo Verticalmente na área disponível
                        logo_y = base_header_y + (h_header - img_h) / 2 - 1*mm
                        c.drawImage(logo_img, left_m + margin_logo, logo_y, width=img_w, height=img_h, mask='auto', preserveAspectRatio=True, anchor='c')
                        has_logo = True
                        
                        # Se tem logo, o texto fica na área restante à direita
                        text_x = left_m + img_w + 3*mm
                        text_w = w_emit_box - img_w - 4*mm
                    except Exception as e:
                        print(f"Erro Logo: {e}")

                # --- CÁLCULO DE CENTRALIZAÇÃO VERTICAL ---
                total_text_height = sum(line["step"] for line in lines_to_draw)
                
                # Altura disponível na caixa (descontando o label do topo)
                available_h_box = h_header - 3*mm 
                
                # Margem superior calculada para centralizar o bloco
                top_margin_dynamic = (available_h_box - total_text_height) / 2
                
                # Posição inicial do cursor (Topo do bloco de texto)
                y_cursor = base_header_y + available_h_box - top_margin_dynamic

                # --- DESENHO DAS LINHAS ---
                for line in lines_to_draw:
                    # Move cursor para a base da linha atual (simula o espaço da linha)
                    y_cursor -= line["step"]
                    
                    # Ajuste fino para baseline (levanta um pouco texto do fundo da linha imaginária)
                    y_baseline = y_cursor + (line["step"] * 0.3) 
                    
                    # Desenha CENTRALIZADO (align='center') tanto horizontalmente quanto verticalmente (via y calculado)
                    draw_text_fitted(
                        c, text_x, y_baseline, text_w, 
                        line["text"], line["font"], 
                        max_size=line["max"], min_size=line["min"], 
                        align='center' # Força alinhamento ao centro
                    )

                # --- CAIXA DANFE (Centro) ---
                x_danfe = left_m + w_emit_box
                w_danfe = 32*mm
                c.rect(x_danfe, base_header_y, w_danfe, h_header)
                
                c.setFont(FONT_BOLD, 14); c.drawCentredString(x_danfe + w_danfe/2, base_header_y + 26*mm, "DANFE")
                c.setFont(FONT_REGULAR, 6); c.drawCentredString(x_danfe + w_danfe/2, base_header_y + 23*mm, "Documento Auxiliar da"); c.drawCentredString(x_danfe + w_danfe/2, base_header_y + 21*mm, "Nota Fiscal Eletrônica")
                
                c.setFont(FONT_REGULAR, 8)
                c.drawString(x_danfe + 2*mm, base_header_y + 16*mm, "0 - Entrada")
                c.drawString(x_danfe + 2*mm, base_header_y + 12*mm, "1 - Saída")
                
                tp_nf = get_val(ide, 'ns:tpNF')
                c.rect(x_danfe + 20*mm, base_header_y + 11.5*mm, 5*mm, 5*mm)
                c.setFont(FONT_BOLD, 10); c.drawCentredString(x_danfe + 22.5*mm, base_header_y + 13*mm, tp_nf)
                
                c.setFont(FONT_BOLD, 9)
                c.drawCentredString(x_danfe + w_danfe/2, base_header_y + 7*mm, f"Nº {get_val(ide, 'ns:nNF')}")
                c.drawCentredString(x_danfe + w_danfe/2, base_header_y + 3*mm, f"SÉRIE {get_val(ide, 'ns:serie')}")
                
                c.setFont(FONT_REGULAR, 7)
                c.drawCentredString(x_danfe + w_danfe/2, base_header_y + 0.5*mm, f"Folha {pagina_atual} de {total_paginas}")

                # --- CÓDIGO DE BARRAS / CHAVE (Direita) ---
                x_chave = x_danfe + w_danfe
                w_chave = content_w - w_emit_box - w_danfe
                c.rect(x_chave, base_header_y, w_chave, h_header)
                
                if chNFe:
                    try:
                        barcode = code128.Code128(chNFe, barHeight=11*mm, barWidth=0.24*mm)
                        bc_x = x_chave + (w_chave - barcode.width)/2
                        barcode.drawOn(c, bc_x, base_header_y + 19*mm)
                    except: pass
                
                draw_field(x_chave, base_header_y + 9*mm, w_chave, 8*mm, "CHAVE DE ACESSO", chNFe, align='center', font_size_val=8, bold_val=True)
                
                c.setFont(FONT_REGULAR, 7)
                c.drawCentredString(x_chave + w_chave/2, base_header_y + 6*mm, "Consulta de autenticidade no portal nacional da NF-e")
                c.drawCentredString(x_chave + w_chave/2, base_header_y + 3*mm, "www.nfe.fazenda.gov.br/portal ou no site da Sefaz Autorizadora")
                
                cur_y = base_header_y
                
                # --- NATUREZA DA OPERAÇÃO / PROTOCOLO ---
                h_nat = 7*mm
                cur_y -= h_nat
                
                # Divisão: Natureza ocupa o espaço restante após reservar espaço fixo para o Protocolo
                w_prot = 100*mm 
                w_nat = content_w - w_prot
                
                # Campo Natureza
                nat_op = get_val(ide, 'ns:natOp')
                draw_field(left_m, cur_y, w_nat, h_nat, "NATUREZA DA OPERAÇÃO", nat_op, font_size_val=7)
                
                # Campo Protocolo (Centralizado visualmente na caixa)
                prot_val = format_protocolo(nProt, dhRecbto)
                draw_field(left_m + w_nat, cur_y, w_prot, h_nat, "PROTOCOLO DE AUTORIZAÇÃO DE USO", prot_val, align='center')

                # --- INSCRIÇÕES ESTADUAIS / CNPJ ---
                cur_y -= h_nat # Mesma altura da linha anterior
                
                w_col = content_w / 3 # 3 colunas iguais
                
                # 1. Inscrição Estadual
                ie_val = get_val(emit, 'ns:IE')
                draw_field(left_m, cur_y, w_col, h_nat, "INSCRIÇÃO ESTADUAL", ie_val, align='left')
                
                # 2. Inscrição Estadual Subst. Tributária
                iest_val = get_val(emit, 'ns:IEST')
                draw_field(left_m + w_col, cur_y, w_col, h_nat, "INSCRIÇÃO ESTADUAL DO SUBST. TRIB.", iest_val, align='left')
                
                # 3. CNPJ (Formatado)
                cnpj_val = format_doc(get_val(emit, 'ns:CNPJ'))
                draw_field(left_m + 2*w_col, cur_y, w_col, h_nat, "CNPJ", cnpj_val, align='left')

                if pagina_atual == 1:
                    # 3. DESTINATÁRIO / REMETENTE
                    # Título da Seção (pequeno, fora da caixa)
                    cur_y -= 2*mm
                    c.setFont(FONT_BOLD, 6)
                    c.drawString(left_m, cur_y, "DESTINATÁRIO / REMETENTE")
                    cur_y -= 0.5*mm
                    
                    h_row = 7*mm # Altura padrão das linhas desta seção
                    
                    # --- LINHA 1: NOME | CNPJ | DATA EMISSÃO ---
                    cur_y -= h_row
                    
                    # Definição de Larguras (Ajustado visualmente conforme a imagem)
                    w_data_emi = 28*mm
                    w_cnpj = 38*mm
                    w_nome = content_w - w_cnpj - w_data_emi
                    
                    # Nome / Razão Social
                    nome_dest = get_val(dest, 'ns:xNome')
                    draw_field(left_m, cur_y, w_nome, h_row, "NOME / RAZÃO SOCIAL", nome_dest, font_size_val=8)
                    
                    # CNPJ / CPF
                    doc_dest = format_doc(get_val(dest, 'ns:CNPJ') or get_val(dest, 'ns:CPF'))
                    draw_field(left_m + w_nome, cur_y, w_cnpj, h_row, "CNPJ / CPF", doc_dest, align='center', font_size_val=8)
                    
                    # Data Emissão
                    dt_emi = format_date(get_val(ide, 'ns:dhEmi'))
                    draw_field(left_m + w_nome + w_cnpj, cur_y, w_data_emi, h_row, "DATA DA EMISSÃO", dt_emi, align='center', font_size_val=8)

                    # --- LINHA 2: ENDEREÇO | BAIRRO | CEP | DATA SAÍDA ---
                    cur_y -= h_row
                    
                    w_data_sai = 28*mm
                    w_cep = 24*mm
                    w_bairro = 45*mm
                    w_end = content_w - w_bairro - w_cep - w_data_sai
                    
                    # Endereço Completo (Logradouro + Numero + Complemento)
                    lgr_d = get_val(dest, 'ns:enderDest/ns:xLgr')
                    nro_d = get_val(dest, 'ns:enderDest/ns:nro')
                    cpl_d = get_val(dest, 'ns:enderDest/ns:xCpl')
                    end_completo = f"{lgr_d}, {nro_d}"
                    if cpl_d: end_completo += f" - {cpl_d}"
                    
                    draw_field(left_m, cur_y, w_end, h_row, "ENDEREÇO", end_completo, font_size_val=7)
                    
                    # Bairro
                    bairro_d = get_val(dest, 'ns:enderDest/ns:xBairro')
                    draw_field(left_m + w_end, cur_y, w_bairro, h_row, "BAIRRO / DISTRITO", bairro_d, font_size_val=7)
                    
                    # CEP
                    cep_d = get_val(dest, 'ns:enderDest/ns:CEP')
                    if len(cep_d) == 8: cep_d = f"{cep_d[:5]}-{cep_d[5:]}"
                    draw_field(left_m + w_end + w_bairro, cur_y, w_cep, h_row, "CEP", cep_d, align='center', font_size_val=7)
                    
                    # Data Saída
                    dt_sai = format_date(get_val(ide, 'ns:dhSaiEnt'))
                    draw_field(left_m + w_end + w_bairro + w_cep, cur_y, w_data_sai, h_row, "DATA SAÍDA/ENTRADA", dt_sai, align='center', font_size_val=8)

                    # --- LINHA 3: MUNICIPIO | FONE | UF | IE | HORA SAÍDA ---
                    cur_y -= h_row
                    
                    w_hora = 28*mm
                    w_ie = 34*mm
                    w_uf = 10*mm # Pequeno conforme imagem
                    w_fone = 34*mm
                    w_mun = content_w - w_fone - w_uf - w_ie - w_hora
                    
                    # Município
                    mun_d = get_val(dest, 'ns:enderDest/ns:xMun')
                    draw_field(left_m, cur_y, w_mun, h_row, "MUNICÍPIO", mun_d, font_size_val=7)
                    
                    # Fone
                    fone_d = get_val(dest, 'ns:enderDest/ns:fone')
                    draw_field(left_m + w_mun, cur_y, w_fone, h_row, "FONE / FAX", fone_d, align='left', font_size_val=7)
                    
                    # UF
                    uf_d = get_val(dest, 'ns:enderDest/ns:UF')
                    draw_field(left_m + w_mun + w_fone, cur_y, w_uf, h_row, "UF", uf_d, align='center', font_size_val=7)
                    
                    # Inscrição Estadual
                    ie_d = get_val(dest, 'ns:IE')
                    draw_field(left_m + w_mun + w_fone + w_uf, cur_y, w_ie, h_row, "INSCRIÇÃO ESTADUAL", ie_d, align='left', font_size_val=7)
                    
                    # Hora Saída
                    dh_sai_full = get_val(ide, 'ns:dhSaiEnt')
                    hora_sai = ""
                    if 'T' in dh_sai_full:
                        hora_sai = dh_sai_full.split('T')[1][:8] # Pega HH:MM:SS
                    draw_field(left_m + w_mun + w_fone + w_uf + w_ie, cur_y, w_hora, h_row, "HORA DA SAÍDA", hora_sai, align='center', font_size_val=8)

                    # 4. FATURA (Bloco J)
                    cur_y -= 2*mm
                    c.setFont(FONT_BOLD, 6)
                    c.drawString(left_m, cur_y, "FATURA") # Título da Seção (Fora da caixa)
                    cur_y -= 0.5*mm
                    
                    h_fat = 8.5*mm # Altura do campo
                    
                    # --- LÓGICA DE EXTRAÇÃO DO PAGAMENTO ---
                    mapa_pag = {
                        '01': 'DINHEIRO', '02': 'CHEQUE', '03': 'CARTÃO DE CRÉDITO',
                        '04': 'CARTÃO DE DÉBITO', '05': 'CRÉDITO LOJA', '10': 'VALE ALIMENTAÇÃO',
                        '11': 'VALE REFEIÇÃO', '12': 'VALE PRESENTE', '13': 'VALE COMBUSTÍVEL',
                        '14': 'DUPLICATA MERCANTIL', '15': 'BOLETO BANCÁRIO', '16': 'DEPÓSITO BANCÁRIO',
                        '17': 'PIX', '18': 'DÉBITO EM CONTA', '90': 'SEM PAGAMENTO', '99': 'OUTROS'
                    }
                    
                    pag_textos = []
                    
                    # 1. Verifica Duplicatas
                    dups = xml_nfe.xpath('//ns:cobr/ns:dup', namespaces=ns)
                    if dups:
                        pag_textos.append("PAGAMENTO À PRAZO")
                        
                        detalhes_dups = []
                        for d in dups:
                            n_dup = get_val(d, 'ns:nDup')
                            v_dup = format_currency(get_val(d, 'ns:vDup'))
                            dt_ven = format_date(get_val(d, 'ns:dVenc'))
                            detalhes_dups.append(f"Num: {n_dup} Venc: {dt_ven} Valor: R${v_dup}")
                        
                        if detalhes_dups:
                            # Se houver espaço, mostra os detalhes, senão fica só o resumo
                            pag_textos.append(" / ".join(detalhes_dups))

                    else:
                        # 2. Pagamento À Vista / Outros
                        pags = xml_nfe.xpath('//ns:pag/ns:detPag', namespaces=ns)
                        for p in pags:
                            t_pag = get_val(p, 'ns:tPag')
                            v_pag = get_val(p, 'ns:vPag')
                            desc = mapa_pag.get(t_pag, 'OUTROS')
                            val_fmt = format_currency(v_pag)
                            pag_textos.append(f"{desc}: R$ {val_fmt}")
                    
                    str_fatura = " - ".join(pag_textos) if pag_textos else "PAGAMENTO À VISTA"
                    
                    # CORREÇÃO: Usamos draw_field para criar a caixa com o rótulo "PAGAMENTO"
                    # Isso garante que apareça "PAGAMENTO" pequeno no canto superior esquerdo da caixa
                    draw_field(left_m, cur_y - h_fat, content_w, h_fat, "PAGAMENTO", str_fatura, align='left', font_size_val=8)
                    
                    cur_y -= h_fat

                    # 5. CÁLCULO DO IMPOSTO (Bloco K)
                    cur_y -= 2*mm
                    c.setFont(FONT_BOLD, 6)
                    c.drawString(left_m, cur_y, "CÁLCULO DO IMPOSTO")
                    cur_y -= 0.5*mm
                    
                    h_row = 7*mm
                    
                    # --- LINHA 1 ---
                    cur_y -= h_row
                    w_col = content_w / 6 # 6 colunas iguais
                    
                    # Extração dos valores
                    v_bc = format_currency(get_val(total, 'ns:vBC'))
                    v_icms = format_currency(get_val(total, 'ns:vICMS'))
                    v_bcst = format_currency(get_val(total, 'ns:vBCST'))
                    v_st = format_currency(get_val(total, 'ns:vST'))
                    v_prod = format_currency(get_val(total, 'ns:vProd'))
                    
                    # Valor Aprox. Tributos (vTotTrib geralmente está em ICMSTot na NFe 4.0)
                    v_tot_trib = format_currency(get_val(total, 'ns:vTotTrib'))
                    
                    # Desenho Linha 1
                    x_acc = left_m
                    draw_field(x_acc, cur_y, w_col, h_row, "BASE DE CÁLC. DO ICMS", v_bc, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR DO ICMS", v_icms, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "BASE CÁLC. ICMS SUBST.", v_bcst, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR DO ICMS SUBST.", v_st, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR APROX. DOS TRIBUTOS", v_tot_trib, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR TOTAL DOS PRODUTOS", v_prod, align='right')

                    # --- LINHA 2 ---
                    cur_y -= h_row
                    
                    # Extração dos valores
                    v_frete = format_currency(get_val(total, 'ns:vFrete'))
                    v_seg = format_currency(get_val(total, 'ns:vSeg'))
                    v_desc = format_currency(get_val(total, 'ns:vDesc'))
                    v_outro = format_currency(get_val(total, 'ns:vOutro'))
                    v_ipi = format_currency(get_val(total, 'ns:vIPI'))
                    v_nf = format_currency(get_val(total, 'ns:vNF'))
                    
                    # Desenho Linha 2
                    x_acc = left_m
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR DO FRETE", v_frete, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR DO SEGURO", v_seg, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "DESCONTO", v_desc, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "OUTRAS DESP. ACESS.", v_outro, align='right'); x_acc += w_col
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR DO IPI", v_ipi, align='right'); x_acc += w_col
                    
                    # EFEITO VISUAL: Fundo Cinza para Valor Total da Nota
                    c.setFillColorRGB(0.9, 0.9, 0.9) # Cinza Claro
                    c.rect(x_acc, cur_y, w_col, h_row, fill=1, stroke=0) # Desenha retângulo preenchido
                    c.setFillColorRGB(0, 0, 0) # Volta para preto para o texto
                    
                    draw_field(x_acc, cur_y, w_col, h_row, "VALOR TOTAL DA NOTA", v_nf, align='right', bold_val=True)

                    # 6. TRANSPORTADOR / VOLUMES TRANSPORTADOS (Bloco L)
                    cur_y -= 2*mm
                    c.setFont(FONT_BOLD, 6)
                    c.drawString(left_m, cur_y, "TRANSPORTADOR / VOLUMES TRANSPORTADOS")
                    cur_y -= 0.5*mm
                    
                    h_row = 7*mm
                    
                    # --- LINHA 1: RAZÃO | FRETE | ANTT | PLACA | UF | CNPJ ---
                    cur_y -= h_row
                    
                    w_frete = 32*mm
                    w_antt = 20*mm
                    w_placa = 20*mm
                    w_uf_veic = 8*mm
                    w_cnpj = 32*mm
                    w_razao = content_w - w_frete - w_antt - w_placa - w_uf_veic - w_cnpj
                    
                    # Extração de Dados
                    mod_frete = get_val(transp, 'ns:modFrete')
                    lbl_frete = {
                        '0': '0 - REMETENTE', '1': '1 - DESTINATÁRIO', '2': '2 - TERCEIROS',
                        '3': '3 - PRÓPRIO REM.', '4': '4 - PRÓPRIO DEST.', '9': '9 - SEM FRETE'
                    }.get(mod_frete, mod_frete)
                    
                    xNome_transp = get_val(transp, 'ns:transporta/ns:xNome')
                    doc_transp = format_doc(get_val(transp, 'ns:transporta/ns:CNPJ') or get_val(transp, 'ns:transporta/ns:CPF'))
                    antt = get_val(transp, 'ns:veicTransp/ns:RNTC')
                    placa = get_val(transp, 'ns:veicTransp/ns:placa')
                    uf_veic = get_val(transp, 'ns:veicTransp/ns:UF')
                    
                    x_acc = left_m
                    draw_field(x_acc, cur_y, w_razao, h_row, "RAZÃO SOCIAL", xNome_transp, font_size_val=7); x_acc += w_razao
                    draw_field(x_acc, cur_y, w_frete, h_row, "FRETE POR CONTA", lbl_frete, align='center', font_size_val=7, bold_val=True); x_acc += w_frete
                    draw_field(x_acc, cur_y, w_antt, h_row, "CÓDIGO ANTT", antt, align='center'); x_acc += w_antt
                    draw_field(x_acc, cur_y, w_placa, h_row, "PLACA DO VEÍCULO", placa, align='center'); x_acc += w_placa
                    draw_field(x_acc, cur_y, w_uf_veic, h_row, "UF", uf_veic, align='center'); x_acc += w_uf_veic
                    draw_field(x_acc, cur_y, w_cnpj, h_row, "CNPJ / CPF", doc_transp, align='center', font_size_val=7)

                    # --- LINHA 2: ENDEREÇO | MUNICÍPIO | UF | IE ---
                    cur_y -= h_row
                    
                    w_mun = 60*mm
                    w_uf_transp = 8*mm
                    w_ie_transp = 32*mm
                    w_end_transp = content_w - w_mun - w_uf_transp - w_ie_transp
                    
                    ender_transp = get_val(transp, 'ns:transporta/ns:xEnder')
                    mun_transp = get_val(transp, 'ns:transporta/ns:xMun')
                    uf_transp = get_val(transp, 'ns:transporta/ns:UF')
                    ie_transp = get_val(transp, 'ns:transporta/ns:IE')
                    
                    x_acc = left_m
                    draw_field(x_acc, cur_y, w_end_transp, h_row, "ENDEREÇO", ender_transp, font_size_val=7); x_acc += w_end_transp
                    draw_field(x_acc, cur_y, w_mun, h_row, "MUNICÍPIO", mun_transp, font_size_val=7); x_acc += w_mun
                    draw_field(x_acc, cur_y, w_uf_transp, h_row, "UF", uf_transp, align='center'); x_acc += w_uf_transp
                    draw_field(x_acc, cur_y, w_ie_transp, h_row, "INSCRIÇÃO ESTADUAL", ie_transp, align='center', font_size_val=7)

                    # --- LINHA 3: VOLUMES (QTD, ESPÉCIE, MARCA, NUM, PESO B, PESO L) ---
                    cur_y -= h_row
                    
                    w_esp = 30*mm
                    w_marca = 30*mm
                    w_num = 30*mm
                    w_peso = 30*mm
                    w_qtd = content_w - w_esp - w_marca - w_num - (w_peso * 2)
                    
                    # Dados do primeiro volume (se houver)
                    vol_node = xml_nfe.xpath('//ns:transp/ns:vol', namespaces=ns)
                    vol = vol_node[0] if vol_node else None
                    
                    qVol = get_val(vol, 'ns:qVol') if vol is not None else ""
                    esp = get_val(vol, 'ns:esp') if vol is not None else ""
                    marca = get_val(vol, 'ns:marca') if vol is not None else ""
                    nVol = get_val(vol, 'ns:nVol') if vol is not None else ""
                    pesoB = format_currency(get_val(vol, 'ns:pesoB')) if vol is not None else ""
                    pesoL = format_currency(get_val(vol, 'ns:pesoL')) if vol is not None else ""
                    
                    # Se peso for zero visualmente (0,00), as vezes prefere-se deixar vazio, mas vou deixar 0,00 padrão
                    if pesoB == "0,00": pesoB = ""
                    if pesoL == "0,00": pesoL = ""

                    x_acc = left_m
                    draw_field(x_acc, cur_y, w_qtd, h_row, "QUANTIDADE", qVol, align='center'); x_acc += w_qtd
                    draw_field(x_acc, cur_y, w_esp, h_row, "ESPÉCIE", esp, align='center'); x_acc += w_esp
                    draw_field(x_acc, cur_y, w_marca, h_row, "MARCA", marca, align='center'); x_acc += w_marca
                    draw_field(x_acc, cur_y, w_num, h_row, "NUMERAÇÃO", nVol, align='center'); x_acc += w_num
                    draw_field(x_acc, cur_y, w_peso, h_row, "PESO BRUTO", pesoB, align='right'); x_acc += w_peso
                    draw_field(x_acc, cur_y, w_peso, h_row, "PESO LÍQUIDO", pesoL, align='right')
                else:
                    cur_y -= 5*mm

                # 7. DADOS DO PRODUTO / SERVIÇOS (Bloco M - Ajustado)
                cur_y -= 2*mm
                c.setFont(FONT_BOLD, 6)
                c.drawString(left_m, cur_y, "DADOS DO PRODUTO / SERVIÇOS")
                cur_y -= 0.5*mm

                # --- 1. PREPARAÇÃO DA TABELA DE ITENS ---
                max_items_page = items_per_page[pagina_atual - 1]
                itens_pagina = items[item_idx : item_idx + max_items_page]
                
                h_header_row = 7*mm
                h_line_item = 5*mm
                
                # Se for a última página, estica a tabela até o rodapé
                # Se for intermediária, encerra a tabela exatamente no último item
                if pagina_atual == total_paginas:
                    y_bottom_final = y_limit_grid
                else:
                    y_bottom_final = cur_y - h_header_row - (len(itens_pagina) * h_line_item)

                h_grid_total = cur_y - y_bottom_final
                
                # Desenha a borda externa
                c.setLineWidth(0.5)
                c.rect(left_m, y_bottom_final, content_w, h_grid_total)

                # --- 2. CONFIGURAÇÃO DE COLUNAS (Soma exata < 190mm) ---
                # Total disponível: 190mm. Soma abaixo: ~189mm
                cols_config = [
                    ("CÓDIGO", 11*mm, 'left'),
                    ("DESCRIÇÃO DO PRODUTO / SERVIÇO", 59*mm, 'left'), # Aumentei aqui
                    ("NCM/SH", 10*mm, 'center'),
                    ("CST", 7*mm, 'center'),
                    ("CFOP", 7*mm, 'center'),
                    ("UNID", 6*mm, 'center'),
                    ("QUANT.", 11*mm, 'right'),
                    ("V.UNIT", 12*mm, 'right'),
                    ("V.TOTAL", 12*mm, 'right'),
                    ("V.DESC", 10*mm, 'right'),
                    ("BC ICMS", 11*mm, 'right'),
                    ("V.ICMS", 10*mm, 'right'),
                    ("V.IPI", 9*mm, 'right'),
                    ("ALÍQ.IC", 7*mm, 'right'), 
                    ("ALÍQ.IP", 7*mm, 'right')
                ]
                
                # --- 3. CABEÇALHO ---
                h_header_row = 7*mm
                y_header_base = cur_y - h_header_row
                
                # Linha horizontal separando cabeçalho dos itens
                c.line(left_m, y_header_base, left_m + content_w, y_header_base)
                
                x_acc = left_m
                c.setFont(FONT_REGULAR, 5)
                
                # Desenha Títulos
                for titulo, largura, align in cols_config:
                    c.drawCentredString(x_acc + (largura/2), cur_y - 4*mm, titulo)
                    x_acc += largura

                # --- 4. ITENS ---
                y_item = y_header_base
                c.setFont(FONT_REGULAR, 6)
                
                # Salva a posição Y inicial para desenhar as linhas verticais depois
                y_start_verticals = cur_y 
                
                for det in itens_pagina:
                    prod = det.find('ns:prod', namespaces=ns)
                    imposto = det.find('ns:imposto', namespaces=ns)
                    
                    # Helpers de extração
                    icms = imposto.find('.//ns:ICMS', namespaces=ns)
                    ipi = imposto.find('.//ns:IPI', namespaces=ns)
                    
                    def get_tag_icms(tag_name):
                        if icms is not None and len(icms) > 0:
                            child = icms[0] 
                            return get_val(child, f'ns:{tag_name}')
                        return ""

                    # Extração de valores
                    cst_val = get_tag_icms('CST') or get_tag_icms('CSOSN')
                    bc_val = get_tag_icms('vBC')
                    vicms_val = get_tag_icms('vICMS')
                    picms_val = get_tag_icms('pICMS')
                    
                    vipi_val = ""
                    pipi_val = ""
                    if ipi is not None:
                        ipitrib = ipi.find('ns:IPITrib', namespaces=ns)
                        if ipitrib is not None:
                            vipi_val = get_val(ipitrib, 'ns:vIPI')
                            pipi_val = get_val(ipitrib, 'ns:pIPI')

                    row_data = [
                        get_val(prod, 'ns:cProd'),
                        get_val(prod, 'ns:xProd'),
                        get_val(prod, 'ns:NCM'),
                        cst_val,
                        get_val(prod, 'ns:CFOP'),
                        get_val(prod, 'ns:uCom'),
                        format_currency(get_val(prod, 'ns:qCom')),
                        format_currency(get_val(prod, 'ns:vUnCom')),
                        format_currency(get_val(prod, 'ns:vProd')),
                        format_currency(get_val(prod, 'ns:vDesc')),
                        format_currency(bc_val),
                        format_currency(vicms_val),
                        format_currency(vipi_val),
                        format_currency(picms_val).replace(',00', ''),
                        format_currency(pipi_val).replace(',00', '')
                    ]
                    
                    x_col = left_m
                    # Centraliza texto verticalmente na linha
                    y_text = y_item - 3.5*mm 
                    
                    for idx, data in enumerate(row_data):
                        w_c = cols_config[idx][1]
                        a_c = cols_config[idx][2]
                        draw_text_fitted(c, x_col, y_text, w_c, data, FONT_REGULAR, 6, 4, align=a_c)
                        x_col += w_c

                    y_item -= h_line_item
                    
                    # Linha horizontal fina entre itens (opcional, comum em DANFE)
                    # Se não quiser linhas entre itens, comente a linha abaixo:
                    c.line(left_m, y_item, left_m + content_w, y_item)

                # --- 5. DESENHA LINHAS VERTICAIS (APENAS ONDE TEM CONTEÚDO) ---
                # Elas vão do topo (cabeçalho) até o fundo do último item desenhado (y_item)
                y_end_verticals = y_item 
                
                x_vert = left_m
                # Pula a primeira (borda esquerda) e desenha as internas
                for i in range(len(cols_config) - 1):
                    x_vert += cols_config[i][1]
                    c.line(x_vert, y_start_verticals, x_vert, y_end_verticals)

                item_idx += len(itens_pagina)

                # Atualiza cursor para o fim do quadrado externo (para o próximo bloco saber onde começar)
                cur_y = y_limit_grid

                # 8. DADOS ADICIONAIS (Bloco N)
                if pagina_atual == total_paginas:
                    cur_y = y_foot_start + h_foot # Topo da caixa
                    
                    # Título da Seção
                    c.setFont(FONT_BOLD, 6)
                    c.drawString(left_m, cur_y + 0.2*mm, "DADOS ADICIONAIS")
                    
                    # Desenha a caixa principal
                    c.setLineWidth(0.5)
                    c.rect(left_m, y_foot_start, content_w, h_foot)
                    
                    # Divisão Vertical (70% para Info Compl. | 30% para Fisco)
                    w_info = content_w * 0.7
                    w_fisco = content_w * 0.3
                    c.line(left_m + w_info, y_foot_start, left_m + w_info, y_foot_start + h_foot)
                    
                    # --- ESQUERDA: INFORMAÇÕES COMPLEMENTARES ---
                    c.setFont(FONT_REGULAR, 5)
                    c.drawString(left_m + 1*mm, cur_y - 2.5*mm, "INFORMAÇÕES COMPLEMENTARES")
                    
                    # 1. Pega o conteúdo original da nota (se houver)
                    inf_cpl = get_val(xml_nfe, '//ns:infAdic/ns:infCpl')
                    
                    # Lista para acumular mensagens adicionais geradas pelo sistema
                    textos_sistema = []
                    
                    # --- A. CÁLCULO DOS TRIBUTOS APROXIMADOS (IBPT E REFORMA) ITEM A ITEM ---
                    tot_ibpt_fed = 0.0
                    tot_ibpt_est = 0.0
                    tot_ibs_danfe = 0.0
                    tot_cbs_danfe = 0.0
                    
                    # --- B. VARREDURA DOS ITENS (Reforma Tributária + IBPT) ---
                    det_items = xml_nfe.xpath('//ns:det', namespaces=ns)
                    msgs_itens = []
                    
                    for det in det_items:
                        n_item = det.get('nItem')
                        inf_ad_prod = get_val(det, 'ns:infAdProd')
                        if inf_ad_prod:
                            # Tenta separar a parte da Reforma das outras informações
                            partes = [p.strip() for p in str(inf_ad_prod).split('|') if p.strip()]
                            partes_limpas = [p for p in partes if not p.upper().startswith("TRIB. 2026")]
                            if partes_limpas:
                                texto_limpo = " | ".join(partes_limpas)
                                msgs_itens.append(f"(Item {n_item}: {texto_limpo})")

                        # Cálculo IBPT (Federal vs Estadual) e Reforma (IBS/CBS)
                        try:
                            def get_float(node, path):
                                v = get_val(node, path)
                                return float(v) if v else 0.0

                            imposto = det.find('ns:imposto', namespaces=ns)
                            
                            # Federal: PIS + COFINS + IPI
                            v_pis = get_float(imposto, 'ns:PIS//ns:vPIS')
                            v_cofins = get_float(imposto, 'ns:COFINS//ns:vCOFINS')
                            
                            v_ipi = 0.0
                            ipi_node = imposto.find('ns:IPI', namespaces=ns)
                            if ipi_node is not None:
                                v_ipi = get_float(ipi_node, './/ns:vIPI')
                                
                            tot_ibpt_fed += (v_pis + v_cofins + v_ipi)

                            # Estadual: ICMS + ST + FCP
                            v_icms = 0.0
                            v_st = 0.0
                            v_fcp = 0.0
                            
                            icms_node = imposto.find('ns:ICMS', namespaces=ns)
                            if icms_node is not None:
                                 v_icms = get_float(icms_node, './/ns:vICMS')
                                 v_st = get_float(icms_node, './/ns:vST')
                                 # Soma todos os FCPs possíveis
                                 v_fcp = get_float(icms_node, './/ns:vFCP')
                                 v_fcp += get_float(icms_node, './/ns:vFCPST')
                                 v_fcp += get_float(icms_node, './/ns:vFCPSTRet')
                            
                            tot_ibpt_est += (v_icms + v_st + v_fcp)
                            
                            # Reforma Tributária: IBS e CBS
                            ibscbs_node = imposto.find('.//ns:IBSCBS', namespaces=ns)
                            if ibscbs_node is not None:
                                tot_ibs_danfe += get_float(ibscbs_node, './/ns:vIBS')
                                tot_cbs_danfe += get_float(ibscbs_node, './/ns:vCBS')

                        except:
                            pass # Evita quebra se falhar conversão numérica

                    # Adiciona mensagens dos itens (se houver outras coisas além da reforma)
                    if msgs_itens:
                        textos_sistema.append(" ".join(msgs_itens))
                        
                    # Adiciona Resumo da Reforma Tributária
                    if tot_ibs_danfe > 0 or tot_cbs_danfe > 0:
                        partes_reforma = []
                        if tot_ibs_danfe > 0: partes_reforma.append(f"Total IBS: R$ {format_currency(tot_ibs_danfe)}")
                        if tot_cbs_danfe > 0: partes_reforma.append(f"Total CBS: R$ {format_currency(tot_cbs_danfe)}")
                        textos_sistema.append("Trib. 2026: " + " | ".join(partes_reforma))

                    # --- C. TEXTO DIFAL E REGIME ESPECIAL ---
                    try:
                        # Busca totais do DIFAL no cabeçalho <total>
                        v_icms_uf_dest_tot = float(get_val(total, 'ns:vICMSUFDest') or 0)
                        v_fcp_uf_dest_tot = float(get_val(total, 'ns:vFCPUFDest') or 0)
                        
                        # Se houver DIFAL, insere o texto legal
                        if v_icms_uf_dest_tot > 0:
                            inf_cpl_upper = str(inf_cpl).upper()
                            if "EC 87/2015" not in inf_cpl_upper and "DIFAL" not in inf_cpl_upper:
                                str_difal = (
                                    f"ICMS DIFAL a não contribuinte consumidor final, disposto na EC 87/2015. "
                                    f"Valor ICMS para UF destino: R${format_currency(v_icms_uf_dest_tot)}. "
                                    f"Valor FCP para o destino: R${format_currency(v_fcp_uf_dest_tot)}."
                                )
                                textos_sistema.append(str_difal)
                                
                                # Adiciona Regime Especial (Geralmente associado a operações interestaduais/específicas)
                                textos_sistema.append("Procedimento autorizado pelo Regime Especial nº 8.092/2024")
                    except:
                        pass

                    # --- D. TRIBUTOS APROXIMADOS (IBPT) ---
                    if tot_ibpt_fed > 0 or tot_ibpt_est > 0:
                        # Fonte fixa conforme solicitado: IBPT 1C2537
                        str_ibpt = (
                            f"Tributos aproximados: R$ {format_currency(tot_ibpt_fed)} (Federal) e "
                            f"R$ {format_currency(tot_ibpt_est)} (Estadual). Fonte: IBPT 1C2537"
                        )
                        textos_sistema.append(str_ibpt)

                    # --- MONTAGEM FINAL DO TEXTO ---
                    # Junta as mensagens do sistema
                    texto_agregado = " - ".join(textos_sistema)
                    
                    # Concatena com o que já veio da nota (infCpl)
                    if inf_cpl:
                        inf_cpl += " - " + texto_agregado
                    elif texto_agregado:
                        inf_cpl = texto_agregado
                    
                    # Limpeza de quebras de linha para o PDF
                    inf_cpl = str(inf_cpl).replace('\n', ' ').replace('\r', ' ').strip()
                    
                    # Configuração de Wrap (Quebra de linha automática baseada na largura real)
                    c.setFont(FONT_REGULAR, 5)
                    
                    # CORREÇÃO AQUI: Substituímos textwrap por simpleSplit
                    # w_info - 2*mm cria uma pequena margem de segurança interna
                    lines = simpleSplit(inf_cpl, FONT_REGULAR, 5, w_info - 2*mm)
                    
                    y_txt = cur_y - 6*mm # Posição da primeira linha de texto
                    
                    for ln in lines:
                        # Se o texto for muito longo, para de desenhar antes de sair da caixa
                        if y_txt < (y_foot_start + 2*mm): 
                            break 
                        c.drawString(left_m + 1*mm, y_txt, ln)
                        y_txt -= 2.5*mm # Espaçamento entre linhas

                    # --- DIREITA: RESERVADO AO FISCO ---
                    # Título interno
                    c.setFont(FONT_REGULAR, 5)
                    c.drawString(left_m + w_info + 1*mm, cur_y - 2.5*mm, "RESERVADO AO FISCO")
                    
                    # Conteúdo (Se houver informações do fisco)
                    inf_fisco = get_val(xml_nfe, '//ns:infAdic/ns:infAdFisco')
                    if inf_fisco:
                        c.setFont(FONT_REGULAR, 6)
                        # CORREÇÃO AQUI TAMBÉM: Usar simpleSplit para o fisco
                        lines_fisco = simpleSplit(inf_fisco, FONT_REGULAR, 6, w_fisco - 2*mm)
                        y_txt_fisco = cur_y - 6*mm
                        for ln in lines_fisco:
                            if y_txt_fisco < (y_foot_start + 2*mm): break
                            c.drawString(left_m + w_info + 1*mm, y_txt_fisco, ln)
                            y_txt_fisco -= 2.5*mm
                            
                # --- MARCA D'ÁGUA DE CANCELAMENTO ---
                if is_cancelada:
                    c.saveState()
                    from reportlab.lib.colors import Color
                    c.setFillColor(Color(1, 0, 0, alpha=0.4))
                    c.setFont(FONT_BOLD, 90)
                    c.translate(w_page / 2, h_page / 2)
                    c.rotate(45)
                    c.drawCentredString(0, 0, "CANCELADO")
                    c.restoreState()

                # --- RODAPÉ DO SISTEMA (Créditos) --- (Comum a todas as páginas)
                c.setFont(FONT_REGULAR, 4)
                c.drawCentredString(w_page / 2, y_foot_start - 3*mm, "CJS Soluções - Documento fiscal impresso pelo sistema Integra AI 79034")

                c.showPage()
                
            if save_pdf:
                c.save()
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
            return None

        except Exception as e:
            print(f"Erro PDF: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _gerar_danfe_simplificada(self, xml_nfe, nProt: str, dhRecbto: str, chNFe: str, c=None, is_cancelada: bool = False) -> str:
        """
        Gera DANFE Simplificada para etiqueta 10x15cm (100mm x 150mm) conforme modelo oficial.
        """
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import mm
            from reportlab.graphics.barcode import code128
            from reportlab.lib.utils import simpleSplit

            FONT_REGULAR = "Helvetica"
            FONT_BOLD = "Helvetica-Bold"

            if isinstance(xml_nfe, (str, bytes)):
                xml_nfe = etree.fromstring(xml_nfe)

            ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

            def get_val(node, xpath):
                try:
                    r = node.xpath(xpath, namespaces=ns)
                    if r:
                        return r[0].text.upper() if r[0].text else ""
                    return ""
                except:
                    return ""

            def format_date(date_str):
                try:
                    if 'T' in str(date_str):
                        date_obj = datetime.strptime(str(date_str).split('T')[0], '%Y-%m-%d')
                        return date_obj.strftime('%d/%m/%Y')
                    return datetime.strptime(str(date_str), '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    return ""

            def format_doc(value):
                v = str(value or "")
                if len(v) == 14: return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
                if len(v) == 11: return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"
                return v

            def format_protocolo(n_prot, dh_recbto):
                try:
                    if dh_recbto and 'T' in str(dh_recbto):
                        val_str = str(dh_recbto)
                        partes = val_str.split('T')
                        data_iso = partes[0]
                        hora_suja = partes[1]
                        ano, mes, dia = data_iso.split('-')
                        hora = hora_suja.split('-')[0].split('+')[0]
                        return f"{n_prot} {dia}/{mes}/{ano} {hora}"
                    return f"{n_prot} {dh_recbto}"
                except:
                    return f"{n_prot} {dh_recbto}"

            page_w, page_h = 100 * mm, 150 * mm

            save_pdf = False
            if c is None:
                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
                c.setTitle(f"DANFE_SIMPLIFICADA_{chNFe}.pdf")
                save_pdf = True
            else:
                c.setPageSize((page_w, page_h))

            # XML Nodes
            emit = xml_nfe.xpath('//ns:emit', namespaces=ns)[0]
            dest_nodes = xml_nfe.xpath('//ns:dest', namespaces=ns)
            dest = dest_nodes[0] if dest_nodes else None
            ide = xml_nfe.xpath('//ns:ide', namespaces=ns)[0]
            inf_cpl = get_val(xml_nfe, '//ns:infAdic/ns:infCpl')

            # Border setup
            margin_left = 3 * mm
            margin_bottom = 3 * mm
            w = page_w - 6 * mm
            h = page_h - 6 * mm

            c.setLineWidth(0.6)
            # Outer border box
            c.rect(margin_left, margin_bottom, w, h)

            # -------------------------------------------------------------
            # SECTION 1: TOP HEADER
            # -------------------------------------------------------------
            # Left Box (Bordered)
            box_x = margin_left + 1.5 * mm
            box_y = 126 * mm
            box_w = 34 * mm
            box_h = 19.5 * mm
            c.rect(box_x, box_y, box_w, box_h)

            tp_nf = get_val(ide, 'ns:tpNF')
            tp_str = "0 - Entrada" if tp_nf == "0" else "1 - Saida"
            n_nf = get_val(ide, 'ns:nNF')
            serie = get_val(ide, 'ns:serie')
            try:
                n_nf_fmt = f"{int(n_nf):,}".replace(",", ".")
            except:
                n_nf_fmt = n_nf
            num_serie_str = f"Número {n_nf_fmt}/Serie {serie}"
            dt_emi = format_date(get_val(ide, 'ns:dhEmi'))

            c.setFont(FONT_REGULAR, 7)
            c.drawString(box_x + 1.5 * mm, box_y + 14 * mm, tp_str)
            c.setFont(FONT_BOLD, 7)
            c.drawString(box_x + 1.5 * mm, box_y + 9 * mm, num_serie_str)
            c.setFont(FONT_REGULAR, 7)
            c.drawString(box_x + 1.5 * mm, box_y + 4 * mm, f"Emissão {dt_emi}")

            # Right Box Text (Centered in right section)
            right_x = box_x + box_w + 1 * mm
            right_w = margin_left + w - right_x - 1 * mm
            center_right_x = right_x + right_w / 2

            c.setFont(FONT_BOLD, 11)
            c.drawCentredString(center_right_x, 141 * mm, "Chave de acesso")

            key_font_size = 6.5
            c.setFont(FONT_REGULAR, key_font_size)
            c.drawCentredString(center_right_x, 136.5 * mm, chNFe)

            c.setFont(FONT_BOLD, 9.5)
            c.drawCentredString(center_right_x, 131 * mm, "Protocolo de Autorização de uso")

            prot_str = format_protocolo(nProt, dhRecbto)
            c.setFont(FONT_REGULAR, 8)
            c.drawCentredString(center_right_x, 126.5 * mm, prot_str)

            # -------------------------------------------------------------
            # DIVIDER LINE 1: Y = 125 * mm
            # -------------------------------------------------------------
            c.line(margin_left, 125 * mm, margin_left + w, 125 * mm)

            # -------------------------------------------------------------
            # SECTION 2: BARCODE
            # -------------------------------------------------------------
            if chNFe:
                try:
                    barcode = code128.Code128(chNFe, barHeight=17 * mm, barWidth=0.21 * mm)
                    bc_x = margin_left + (w - barcode.width) / 2
                    barcode.drawOn(c, bc_x, 104 * mm)
                except Exception as b_err:
                    print(f"Erro ao gerar código de barras no DANFE Simplificado: {b_err}")

            c.setFont(FONT_REGULAR, 7.5)
            c.drawCentredString(margin_left + w / 2, 99 * mm, chNFe)

            # -------------------------------------------------------------
            # DIVIDER LINE 2: Y = 97 * mm
            # -------------------------------------------------------------
            c.line(margin_left, 97 * mm, margin_left + w, 97 * mm)

            # -------------------------------------------------------------
            # SECTION 3: REMETENTE & DESTINATÁRIO & DANFE SIMPLIFICADO
            # -------------------------------------------------------------
            pad_x = margin_left + 2 * mm
            end_x = margin_left + w - 2 * mm

            emit_nome = get_val(emit, 'ns:xNome')
            emit_cnpj = format_doc(get_val(emit, 'ns:CNPJ'))
            emit_ie = get_val(emit, 'ns:IE')
            emit_uf = get_val(emit, 'ns:enderEmit/ns:UF')

            # Line 1: Remetente
            c.setFont(FONT_BOLD, 8)
            c.drawString(pad_x, 91.5 * mm, "Remetente: ")
            rem_title_w = c.stringWidth("Remetente: ", FONT_BOLD, 8)
            c.setFont(FONT_REGULAR, 8)
            c.drawString(pad_x + rem_title_w, 91.5 * mm, emit_nome[:45])

            # Line 2: CNPJ | IE | UF
            c.setFont(FONT_BOLD, 7)
            c.drawString(pad_x, 85.5 * mm, "CNPJ: ")
            cnpj_lbl_w = c.stringWidth("CNPJ: ", FONT_BOLD, 7)
            c.setFont(FONT_REGULAR, 7)
            c.drawString(pad_x + cnpj_lbl_w, 85.5 * mm, emit_cnpj)

            x_ie = pad_x + cnpj_lbl_w + c.stringWidth(emit_cnpj, FONT_REGULAR, 7) + 4 * mm
            c.setFont(FONT_BOLD, 7)
            c.drawString(x_ie, 85.5 * mm, "INSCRIÇÃO ESTADUAL: ")
            ie_lbl_w = c.stringWidth("INSCRIÇÃO ESTADUAL: ", FONT_BOLD, 7)
            c.setFont(FONT_REGULAR, 7)
            c.drawString(x_ie + ie_lbl_w, 85.5 * mm, emit_ie)

            uf_rem_str = f"UF: {emit_uf}"
            c.setFont(FONT_BOLD, 7)
            c.drawString(end_x - c.stringWidth(uf_rem_str, FONT_BOLD, 7), 85.5 * mm, uf_rem_str)

            # Line 3: Destinatário | UF
            dest_nome = get_val(dest, 'ns:xNome') if dest else ""
            dest_uf = get_val(dest, 'ns:enderDest/ns:UF') if dest else ""

            c.setFont(FONT_BOLD, 8)
            c.drawString(pad_x, 77.5 * mm, "DESTINATARIO: ")
            dest_lbl_w = c.stringWidth("DESTINATARIO: ", FONT_BOLD, 8)
            c.setFont(FONT_REGULAR, 8)
            c.drawString(pad_x + dest_lbl_w, 77.5 * mm, dest_nome[:42])

            uf_dest_str = f"UF: {dest_uf}"
            c.setFont(FONT_BOLD, 8)
            c.drawString(end_x - c.stringWidth(uf_dest_str, FONT_BOLD, 8), 77.5 * mm, uf_dest_str)

            # Line 4: DANFE SIMPLIFICADO
            c.setFont(FONT_BOLD, 9)
            c.drawString(pad_x, 68.5 * mm, "DANFE SIMPLIFICADO")

            # -------------------------------------------------------------
            # DIVIDER LINE 3: Y = 64 * mm
            # -------------------------------------------------------------
            c.line(margin_left, 64 * mm, margin_left + w, 64 * mm)

            # -------------------------------------------------------------
            # SECTION 4: MIDDLE SECTION (Blank Box)
            # -------------------------------------------------------------

            # -------------------------------------------------------------
            # DIVIDER LINE 4: Y = 30 * mm
            # -------------------------------------------------------------
            c.line(margin_left, 30 * mm, margin_left + w, 30 * mm)

            # -------------------------------------------------------------
            # SECTION 5: DADOS ADICIONAIS
            # -------------------------------------------------------------
            c.setFont(FONT_BOLD, 8)
            c.drawString(pad_x, 25.5 * mm, "DADOS ADICIONAIS")

            if inf_cpl:
                c.setFont(FONT_REGULAR, 6)
                inf_cpl_clean = str(inf_cpl).replace('\n', ' ').replace('\r', ' ').strip()
                lines = simpleSplit(inf_cpl_clean, FONT_REGULAR, 6, w - 4 * mm)
                y_txt = 21 * mm
                for ln in lines:
                    if y_txt < (margin_bottom + 2 * mm):
                        break
                    c.drawString(pad_x, y_txt, ln)
                    y_txt -= 2.6 * mm

            # Watermark if canceled
            if is_cancelada:
                c.saveState()
                from reportlab.lib.colors import Color
                c.setFillColor(Color(1, 0, 0, alpha=0.4))
                c.setFont(FONT_BOLD, 40)
                c.translate(page_w / 2, page_h / 2)
                c.rotate(45)
                c.drawCentredString(0, 0, "CANCELADO")
                c.restoreState()

            c.showPage()

            if save_pdf:
                c.save()
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
            return None

        except Exception as e:
            print(f"Erro PDF Simplificado: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _gerar_pdf_cce(self, chave_acesso: str, cnpj_cpf: str, protocolo: str, data_evento: str, uf: str, texto_correcao: str) -> str:
        """
        Gera o PDF da Carta de Correção (CC-e) no layout padronizado.
        """
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.lib.utils import simpleSplit
            import io
            from datetime import datetime

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            c.setTitle(f"CCe_{chave_acesso}.pdf")
            
            w_page, h_page = A4
            
            # --- Configurações de Margem e Dimensões ---
            left_m = 10 * mm
            top_m = h_page - 10 * mm
            content_w = w_page - 20 * mm
            
            # Alturas das sessões
            h_header = 20 * mm
            h_middle = 50 * mm
            h_footer = 25 * mm
            total_h = h_header + h_middle + h_footer
            
            cur_y = top_m

            # --- Formatações ---
            # Formata CNPJ
            doc_fmt = cnpj_cpf
            if len(cnpj_cpf) == 14:
                doc_fmt = f"{cnpj_cpf[:2]}.{cnpj_cpf[2:5]}.{cnpj_cpf[5:8]}/{cnpj_cpf[8:12]}-{cnpj_cpf[12:]}"
            elif len(cnpj_cpf) == 11:
                doc_fmt = f"{cnpj_cpf[:3]}.{cnpj_cpf[3:6]}.{cnpj_cpf[6:9]}-{cnpj_cpf[9:]}"
                
            # Formata Data
            data_formatada = data_evento
            try:
                # Trata data ISO: 2026-01-21T14:24:50-03:00
                if 'T' in data_evento:
                    dt_obj = datetime.fromisoformat(data_evento)
                    data_formatada = dt_obj.strftime("%d/%m/%Y %H:%M")
            except:
                pass

            # --- LINHA 1: CABEÇALHO ---
            y_header = cur_y - h_header
            c.setLineWidth(1)
            c.rect(left_m, y_header, content_w, h_header) # Caixa externa do header
            
            w_left_header = 90 * mm
            c.line(left_m + w_left_header, y_header, left_m + w_left_header, y_header + h_header) # Divisória vertical
            c.line(left_m + w_left_header, y_header + (h_header/2), left_m + content_w, y_header + (h_header/2)) # Divisória horizontal dir.
            
            # Título Carta de Correção
            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(left_m + (w_left_header/2), y_header + 8*mm, "CARTA DE CORREÇÃO")
            
            # CNPJ/CPF
            c.setFont("Helvetica-Bold", 7)
            c.drawString(left_m + w_left_header + 2*mm, y_header + h_header - 3.5*mm, "CNPJ/CPF")
            c.setFont("Helvetica", 9)
            c.drawString(left_m + w_left_header + 2*mm, y_header + h_header - 8*mm, doc_fmt)
            
            # Chave de Acesso
            c.setFont("Helvetica-Bold", 7)
            c.drawString(left_m + w_left_header + 2*mm, y_header + (h_header/2) - 3.5*mm, "CHAVE DE ACESSO")
            c.setFont("Helvetica", 9)
            c.drawString(left_m + w_left_header + 2*mm, y_header + (h_header/2) - 8*mm, chave_acesso)

            # --- LINHA 2: MEIO (INFORMAÇÕES E CORREÇÃO) ---
            cur_y = y_header
            y_middle = cur_y - h_middle
            c.rect(left_m, y_middle, content_w, h_middle)
            
            w_left_mid = 45 * mm
            c.line(left_m + w_left_mid, y_middle, left_m + w_left_mid, y_middle + h_middle)
            
            # Linhas horizontais do bloco esquerdo
            h_row = h_middle / 5
            for i in range(1, 5):
                c.line(left_m, y_middle + (i * h_row), left_m + w_left_mid, y_middle + (i * h_row))
                
            # Dados bloco esquerdo (de baixo para cima no desenho)
            labels = ["DATA", "TIPO EVENTO", "PROTOCOLO", "ORGÃO", "LOTE"]
            values = [data_formatada, "110110", protocolo, uf, "1"]
            
            for i in range(5):
                base_y = y_middle + (i * h_row)
                c.setFont("Helvetica-Bold", 7)
                c.drawString(left_m + 2*mm, base_y + h_row - 3.5*mm, labels[i])
                c.setFont("Helvetica", 9)
                c.drawString(left_m + 2*mm, base_y + 2*mm, values[i])
                
            # Bloco Direito (Texto da Correção)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(left_m + w_left_mid + 2*mm, y_middle + h_middle - 4*mm, "CORREÇÃO")
            c.setFont("Helvetica", 9)
            
            texto_linhas = simpleSplit(texto_correcao, "Helvetica", 9, content_w - w_left_mid - 4*mm)
            y_txt = y_middle + h_middle - 9*mm
            for linha in texto_linhas:
                c.drawString(left_m + w_left_mid + 2*mm, y_txt, linha)
                y_txt -= 4*mm

            # --- LINHA 3: RODAPÉ LEGAL ---
            cur_y = y_middle
            y_footer = cur_y - h_footer
            c.rect(left_m, y_footer, content_w, h_footer)
            
            texto_legal = (
                "\"A Carta de Correção é disciplinada pelo § 1º-A do art. 7º do Convênio S/N, de 15 de dezembro de 1970 e pode ser utilizada para\n"
                "regularização de erro ocorrido na emissão de documento fiscal, desde que o erro não esteja relacionado com:\n"
                "I - as variáveis que determinam o valor do imposto tais como: base de cálculo, alíquota, diferença de preço, quantidade, valor da operação\n"
                "ou da prestação;\n"
                "II - a correção de dados cadastrais que implique mudança do remetente ou do destinatário;\n"
                "III - a data de emissão ou de saída.\""
            )
            
            y_txt_leg = y_footer + h_footer - 4*mm
            c.setFont("Helvetica", 8)
            for linha in texto_legal.split('\n'):
                c.drawString(left_m + 2*mm, y_txt_leg, linha.strip())
                y_txt_leg -= 3.5*mm

            # Rodapé do Sistema
            c.setFont("Helvetica", 6)
            c.drawRightString(left_m + content_w, y_footer - 3*mm, "Emitido por Integra AI")

            c.save()
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def _encontrar_regra_tributaria(self, produto: models.Produto, cliente: models.Cadastro, tipo_operacao_pedido: RegraTipoOperacaoEnum = None) -> models.Tributacao:
        """
        Busca a regra tributária mais específica para o cenário (Produto + Cliente + Empresa).
        """
        # 1. Determina Regime do Emitente
        regime_emitente = RegraRegimeEmitenteEnum.simples_nacional
        
        if self.empresa.crt == models.EmpresaCRTEnum.lucro_real:
            regime_emitente = RegraRegimeEmitenteEnum.lucro_real
        elif self.empresa.crt == models.EmpresaCRTEnum.lucro_presumido:
            regime_emitente = RegraRegimeEmitenteEnum.lucro_presumido
        # Caso contrário (1 ou 2), mantém simples_nacional

        # 2. Determina Tipo de Operação
        tipo_operacao = tipo_operacao_pedido or RegraTipoOperacaoEnum.venda_mercadoria

        # 3. Determina Tipo de Cliente
        tipo_cliente = RegraTipoClienteEnum.pf
        if cliente.tipo_pessoa == CadastroTipoPessoaEnum.juridica:
            raw_ie = str(cliente.inscricao_estadual or '').strip()
            ie_clean = self._limpar_formatacao(raw_ie)
            val_ind_ie = str(cliente.indicador_ie.value if hasattr(cliente.indicador_ie, 'value') else cliente.indicador_ie or '')
            
            if val_ind_ie == '1' or (ie_clean and raw_ie.upper() not in ['ISENTO', 'ISENTA']):
                tipo_cliente = RegraTipoClienteEnum.pj_contribuinte
            elif val_ind_ie == '2' or raw_ie.upper() in ['ISENTO', 'ISENTA']:
                tipo_cliente = RegraTipoClienteEnum.pj_isento
            else:
                tipo_cliente = RegraTipoClienteEnum.pj_nao_contribuinte
        
        # 4. Determina Localização de Destino
        uf_empresa = self.empresa.estado.value if hasattr(self.empresa.estado, 'value') else self.empresa.estado
        uf_cliente = cliente.estado.value if hasattr(cliente.estado, 'value') else cliente.estado
        
        if uf_cliente == 'EX':
            localizacao = RegraLocalizacaoDestinoEnum.exterior
        elif uf_empresa == uf_cliente:
            localizacao = RegraLocalizacaoDestinoEnum.interna
        else:
            localizacao = RegraLocalizacaoDestinoEnum.interestadual

        # FIX: Mapeamento de Origem do Produto (Enum Produto -> Enum Fiscal)
        origem_produto_val = produto.origem.value if hasattr(produto.origem, 'value') else str(produto.origem)
        
        mapa_origem = {
            "nacional": FiscalOrigemEnum.origem_0,
            "estrangeira_import_direta": FiscalOrigemEnum.origem_1,
            "estrangeira_adq_merc_interno": FiscalOrigemEnum.origem_2,
            "nacional_conteudo_import_40": FiscalOrigemEnum.origem_3,
            "nacional_producao_basica": FiscalOrigemEnum.origem_4,
            "nacional_conteudo_import_70": FiscalOrigemEnum.origem_8,
        }
        
        fiscal_origem = mapa_origem.get(origem_produto_val)
        if not fiscal_origem and origem_produto_val.isdigit():
             try:
                 fiscal_origem = FiscalOrigemEnum(origem_produto_val)
             except:
                 pass
        
        if not fiscal_origem:
             fiscal_origem = FiscalOrigemEnum.origem_0

        # 5. Busca Regras no Banco (Ordenadas por Prioridade)
        # Filtra pelas chaves principais
        query = self.db.query(models.Tributacao).filter(
            models.Tributacao.id_empresa == self.id_empresa,
            models.Tributacao.situacao == True,
            models.Tributacao.regime_emitente == regime_emitente,
            models.Tributacao.tipo_operacao == tipo_operacao,
            models.Tributacao.tipo_cliente == tipo_cliente,
            models.Tributacao.localizacao_destino == localizacao,
            models.Tributacao.origem_produto == fiscal_origem
        ).order_by(models.Tributacao.prioridade.desc())

        regras = query.all()

        # 6. Filtro de NCM em memória (para suportar wildcards ou 'Geral')
        # Se ncm_chave for nulo ou '*', aceita. Se for específico, tem que bater.
        prod_ncm = self._limpar_formatacao(produto.ncm)
        
        regra_selecionada = None
        
        for regra in regras:
            chave = regra.ncm_chave
            if not chave or chave == '*' or chave.lower() == 'geral':
                regra_selecionada = regra
                # Continua procurando se achar um mais específico? 
                # Como ordenamos por prioridade DESC, o primeiro que bater deve ser o melhor,
                # assumindo que o usuário configurou prioridade maior para NCMs específicos.
                break
            
            # Limpa formatação da chave
            chave_limpa = self._limpar_formatacao(chave)
            
            # Match exato ou prefixo (ex: 6109.*)
            if prod_ncm == chave_limpa:
                regra_selecionada = regra
                break
            
            # Suporte simples a prefixo se a chave tiver menos digitos que o NCM
            if len(chave_limpa) < 8 and prod_ncm.startswith(chave_limpa):
                regra_selecionada = regra
                break

        return regra_selecionada

    def _get_aliquota_interestadual(self, uf_origem: str, uf_destino: str, origem_produto: str) -> Decimal:
        """
        Define a alíquota interestadual (4%, 7% ou 12%).
        """
        # 1. Produtos Importados (Origem 1, 2, 3, 8) = 4%
        # Verifica se a origem é importada (convertendo enum ou string)
        origem_str = str(origem_produto)
        if origem_str in ['1', '2', '3', '8']:
            return Decimal('4.00')

        # Estados do Sul e Sudeste (exceto ES)
        estados_ricos = ['MG', 'PR', 'RS', 'RJ', 'SC', 'SP']
        
        # 2. Se origem for Sul/Sudeste e destino for Norte/Nordeste/Centro-Oeste/ES = 7%
        if uf_origem in estados_ricos and uf_destino not in estados_ricos:
            return Decimal('7.00')
            
        # 3. Regra Geral (Entre estados da mesma região ou "pobres" para "ricos") = 12%
        return Decimal('12.00')

    def _calc_valor(self, base: Decimal, aliquota: Decimal) -> Decimal:
        if not base or not aliquota:
            return Decimal('0.00')
        return (base * (aliquota / Decimal('100'))).quantize(Decimal('0.01'))
    
    def gerar_devolucao(self, pedido_id: int):
        """
        Duplica um pedido existente com finalidade de devolução e tenta emitir a NFe.
        """
        # 1. Busca pedido original
        pedido_origem = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.id_sequencial == pedido_id
        ).first()

        if not pedido_origem:
            raise HTTPException(status_code=404, detail="Pedido original não encontrado.")
        
        if not pedido_origem.chave_acesso:
            raise HTTPException(status_code=400, detail="Pedido original não possui NFe autorizada para referenciar.")

        num_origem = pedido_origem.id_sequencial if pedido_origem.id_sequencial is not None else pedido_origem.id

        # 2. Cria novo pedido (Duplicação)
        # Copia itens explicitamente para garantir nova lista
        itens_copia = [item.copy() for item in pedido_origem.itens] if pedido_origem.itens else []

        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=pedido_origem.id_cliente,
            id_vendedor=pedido_origem.id_vendedor,
            id_transportadora=pedido_origem.id_transportadora,
            origem_venda=pedido_origem.origem_venda,
            situacao=PedidoSituacaoEnum.faturamento, # Vai para Faturamento para conferência antes de emitir
            data_orcamento=datetime.now(TZ_BR).date() if 'TZ_BR' in globals() else datetime.now().date(),
            
            # Copia exata dos dados financeiros e itens
            itens=itens_copia,
            total=pedido_origem.total,
            desconto=pedido_origem.desconto,
            total_desconto=pedido_origem.total_desconto,
            pagamento=pedido_origem.pagamento,
            pagamento_descricao=pedido_origem.pagamento_descricao,
            caixa_destino_origem=pedido_origem.caixa_destino_origem,
            ordem_finalizacao=pedido_origem.ordem_finalizacao,
            
            # Endereço de Entrega
            endereco_cep=pedido_origem.endereco_cep,
            endereco_estado=pedido_origem.endereco_estado,
            endereco_cidade=pedido_origem.endereco_cidade,
            endereco_bairro=pedido_origem.endereco_bairro,
            endereco_logradouro=pedido_origem.endereco_logradouro,
            endereco_numero=pedido_origem.endereco_numero,
            endereco_complemento=pedido_origem.endereco_complemento,
            
            # Dados de Frete e Logística
            modalidade_frete=pedido_origem.modalidade_frete,
            valor_frete=pedido_origem.valor_frete,
            ipi_frete=pedido_origem.ipi_frete,
            total_frete=pedido_origem.total_frete,
            volumes_quantidade=pedido_origem.volumes_quantidade,
            volumes_especie=pedido_origem.volumes_especie,
            volumes_marca=pedido_origem.volumes_marca,
            volumes_numeracao=pedido_origem.volumes_numeracao,
            volumes_peso_bruto=pedido_origem.volumes_peso_bruto,
            volumes_peso_liquido=pedido_origem.volumes_peso_liquido,
            
            # Dados de Veículo
            veiculo_placa=pedido_origem.veiculo_placa,
            veiculo_uf=pedido_origem.veiculo_uf,
            veiculo_antt=pedido_origem.veiculo_antt,
            
            # Outros e Integrações
            indicador_presenca=pedido_origem.indicador_presenca,
            modelo_fiscal=pedido_origem.modelo_fiscal,
            delivery_method_id_intelipost=pedido_origem.delivery_method_id_intelipost,
            quote_id=pedido_origem.quote_id,
            intelipost_id=pedido_origem.intelipost_id,
            meli_xml_enviado=pedido_origem.meli_xml_enviado,
            intelipost_criado=pedido_origem.intelipost_criado,
            email_enviado=pedido_origem.email_enviado,

            # Alterações para Devolução
            tipo_operacao=RegraTipoOperacaoEnum.devolucao_entrada,
            chave_nfe_referencia=pedido_origem.chave_acesso,
            observacao=f"{pedido_origem.observacao} | Devolução referente ao pedido #{num_origem}" if pedido_origem.observacao else f"Devolução referente ao pedido #{num_origem}"
        )

        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)

        num_novo = novo_pedido.id_sequencial if novo_pedido.id_sequencial is not None else novo_pedido.id

        # 3. Retorna sucesso sem emitir NFe (agora vai para Faturamento)
        return {
            "success": True, 
            "message": f"Pedido de devolução #{num_novo} gerado com sucesso! Encontra-se em Faturamento.",
            "id": num_novo
        }

    def gerar_complemento(self, pedido_id: int):
        """
        Duplica um pedido existente com finalidade complementar e o coloca em Faturamento.
        """
        # 1. Busca pedido original
        pedido_origem = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.id_sequencial == pedido_id
        ).first()

        if not pedido_origem:
            raise HTTPException(status_code=404, detail="Pedido original não encontrado.")
        
        if not pedido_origem.chave_acesso:
            raise HTTPException(status_code=400, detail="Pedido original não possui NFe autorizada para referenciar.")

        num_origem = pedido_origem.id_sequencial if pedido_origem.id_sequencial is not None else pedido_origem.id

        # 2. Cria novo pedido (Duplicação)
        itens_copia = [item.copy() for item in pedido_origem.itens] if pedido_origem.itens else []

        novo_pedido = models.Pedido(
            id_empresa=self.id_empresa,
            id_cliente=pedido_origem.id_cliente,
            id_vendedor=pedido_origem.id_vendedor,
            id_transportadora=pedido_origem.id_transportadora,
            origem_venda=pedido_origem.origem_venda,
            situacao=PedidoSituacaoEnum.faturamento, # Vai para Faturamento para conferência antes de emitir
            data_orcamento=datetime.now(TZ_BR).date() if 'TZ_BR' in globals() else datetime.now().date(),
            
            # Copia exata dos dados financeiros e itens
            itens=itens_copia,
            total=pedido_origem.total,
            desconto=pedido_origem.desconto,
            total_desconto=pedido_origem.total_desconto,
            pagamento=pedido_origem.pagamento,
            pagamento_descricao=pedido_origem.pagamento_descricao,
            caixa_destino_origem=pedido_origem.caixa_destino_origem,
            ordem_finalizacao=pedido_origem.ordem_finalizacao,
            
            # Endereço de Entrega
            endereco_cep=pedido_origem.endereco_cep,
            endereco_estado=pedido_origem.endereco_estado,
            endereco_cidade=pedido_origem.endereco_cidade,
            endereco_bairro=pedido_origem.endereco_bairro,
            endereco_logradouro=pedido_origem.endereco_logradouro,
            endereco_numero=pedido_origem.endereco_numero,
            endereco_complemento=pedido_origem.endereco_complemento,
            
            # Dados de Frete e Logística
            modalidade_frete=pedido_origem.modalidade_frete,
            valor_frete=pedido_origem.valor_frete,
            ipi_frete=pedido_origem.ipi_frete,
            total_frete=pedido_origem.total_frete,
            volumes_quantidade=pedido_origem.volumes_quantidade,
            volumes_especie=pedido_origem.volumes_especie,
            volumes_marca=pedido_origem.volumes_marca,
            volumes_numeracao=pedido_origem.volumes_numeracao,
            volumes_peso_bruto=pedido_origem.volumes_peso_bruto,
            volumes_peso_liquido=pedido_origem.volumes_peso_liquido,
            
            # Dados de Veículo
            veiculo_placa=pedido_origem.veiculo_placa,
            veiculo_uf=pedido_origem.veiculo_uf,
            veiculo_antt=pedido_origem.veiculo_antt,
            
            # Outros e Integrações
            indicador_presenca=pedido_origem.indicador_presenca,
            modelo_fiscal=pedido_origem.modelo_fiscal,
            delivery_method_id_intelipost=pedido_origem.delivery_method_id_intelipost,
            quote_id=pedido_origem.quote_id,
            intelipost_id=pedido_origem.intelipost_id,
            meli_xml_enviado=pedido_origem.meli_xml_enviado,
            intelipost_criado=pedido_origem.intelipost_criado,
            email_enviado=pedido_origem.email_enviado,

            # Alterações para Complemento
            tipo_operacao=RegraTipoOperacaoEnum.complemento,
            chave_nfe_referencia=pedido_origem.chave_acesso,
            observacao=f"{pedido_origem.observacao} | Complemento referente ao pedido #{num_origem}" if pedido_origem.observacao else f"Complemento referente ao pedido #{num_origem}",
            observacoes_nf=f"Nota Fiscal Complementar referente a NF-e chave {pedido_origem.chave_acesso}"
        )

        self.db.add(novo_pedido)
        self.db.commit()
        self.db.refresh(novo_pedido)

        num_novo = novo_pedido.id_sequencial if novo_pedido.id_sequencial is not None else novo_pedido.id

        # 3. Retorna sucesso sem emitir NFe (agora vai para Faturamento)
        return {
            "success": True, 
            "message": f"Pedido de complemento #{num_novo} gerado com sucesso! Encontra-se em Faturamento.",
            "id": num_novo
        }

    def emitir_nfe(self, pedido_id: int, id_regra_tributaria: int = None):
        # 1. Busca Dados do Pedido
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.id_sequencial == pedido_id
        ).first()

        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        
        if not pedido.cliente:
            raise HTTPException(status_code=400, detail="Pedido sem cliente vinculado.")

        # --- NOVA LÓGICA: VERIFICA SE JÁ ESTÁ AUTORIZADA ---
        # Se já estiver autorizada (cStat 100) e tiver XML, apenas tenta re-enviar para o ML se necessário
        if pedido.status_sefaz and pedido.status_sefaz.startswith('100') and pedido.xml_autorizado:
            # --- EXECUTA INTEGRAÇÕES ---
            meli_res, intelipost_res, email_res = self._executar_integracoes_faturamento(
                pedido, pedido.xml_autorizado, pedido.pdf_danfe
            )

            # Move para expedição apenas se as integrações críticas (ML e Intelipost) passaram
            # Se meli_res for None (não é ML) ou meli_res["success"] for True
            # E se intelipost_res for None (não tem integração) ou intelipost_res["success"] for True
            meli_ok = (meli_res is None or meli_res.get("success"))
            intelipost_ok = (intelipost_res is None or intelipost_res.get("success"))

            if meli_ok and intelipost_ok:
                pedido.situacao = PedidoSituacaoEnum.expedicao
            self.db.commit()
            
            return {
                "success": True,
                "nfe": {"success": True, "message": "Nota já autorizada anteriormente.", "chave": pedido.chave_acesso},
                "meli": meli_res,
                "intelipost": intelipost_res,
                "email": email_res,
                "xml": pedido.xml_autorizado,
                "pdf": pedido.pdf_danfe
            }

        # Validação de Volumes (Obrigatório para Faturamento)
        if not pedido.volumes_quantidade or pedido.volumes_quantidade <= 0:
             raise HTTPException(status_code=400, detail="A quantidade de volumes é obrigatória para emitir a NFe. Verifique a aba Frete do pedido.")

        # Carrega regra forçada se houver (selecionada manualmente no modal)
        regra_forcada = None
        if id_regra_tributaria:
            regra_forcada = self.db.query(models.Tributacao).filter(
                models.Tributacao.id == id_regra_tributaria,
                models.Tributacao.id_empresa == self.id_empresa
            ).first()

        # 2. Configurações Iniciais
        cert_path = self._get_certificado_path()
        senha_cert = self.empresa.certificado_senha
        
        # Ajuste para pegar o valor do Enum se for Enum, senão string
        uf_empresa = self.empresa.estado.value if hasattr(self.empresa.estado, 'value') else self.empresa.estado
        uf_empresa = uf_empresa.upper()
        
        # Verifica se estamos no ambiente de desenvolvimento
        is_development = settings.ENVIRONMENT != "production"

        # 1=Produção, 2=Homologação
        ambiente_homologacao = (self.empresa.ambiente_sefaz.value == 2) or is_development

        try:
            # --- CLIENTE ---
            cli_db = pedido.cliente
            
            # Define UF do Cliente (prioridade para o endereço do pedido)
            uf_cliente_obj = pedido.endereco_estado or cli_db.estado
            uf_cliente = (uf_cliente_obj.value if hasattr(uf_cliente_obj, 'value') else uf_cliente_obj or "").upper()
            
            tipo_doc = 'CPF' if len(self._limpar_formatacao(cli_db.cpf_cnpj)) == 11 else 'CNPJ'
            
            # Lógica para indicador IE e Inscrição Estadual
            raw_ie = str(cli_db.inscricao_estadual or '').strip()
            ie_clean = self._limpar_formatacao(raw_ie)
            
            ind_ie = 9 # Default: Não contribuinte
            if cli_db.indicador_ie:
                try:
                    val_str = cli_db.indicador_ie.value if hasattr(cli_db.indicador_ie, 'value') else str(cli_db.indicador_ie)
                    ind_ie = int(val_str)
                except:
                    ind_ie = 9

            # Ajustes inteligentes:
            # 1. Se no cadastro a IE for 'ISENTO' / 'ISENTA' ou ind_ie for 2
            if raw_ie.upper() in ['ISENTO', 'ISENTA'] or ind_ie == 2:
                ind_ie = 2
                ie_clean = None
            # 2. Se houver dígitos de IE preenchidos no cadastro, força ind_ie = 1 (Contribuinte ICMS)
            elif ie_clean:
                ind_ie = 1
            else:
                ie_clean = None

            # Em homologação, a Razão Social do destinatário deve ser fixa (Regra SEFAZ)
            razao_social_cli = cli_db.nome_razao
            if ambiente_homologacao:
                razao_social_cli = 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'

            # --- PRÉ-VALIDAÇÃO E SANITIZAÇÃO DO CLIENTE (DESTINATÁRIO) ---
            razao_social_clean = self._limpar_texto(razao_social_cli)
            logradouro_clean = self._limpar_texto(pedido.endereco_logradouro or cli_db.logradouro)
            numero_clean = self._limpar_texto(pedido.endereco_numero or cli_db.numero)
            complemento_clean = self._limpar_texto(pedido.endereco_complemento or cli_db.complemento or '', max_len=60) or None
            bairro_clean = self._limpar_texto(pedido.endereco_bairro or cli_db.bairro)
            municipio_clean = self._limpar_texto(pedido.endereco_cidade or cli_db.cidade)
            cep_clean = self._limpar_formatacao(pedido.endereco_cep or cli_db.cep)
            telefone_clean = self._limpar_formatacao(cli_db.telefone or cli_db.celular)
            
            erros_cliente = []
            if not razao_social_clean:
                erros_cliente.append("Nome/Razão Social")
            if not logradouro_clean:
                erros_cliente.append("Logradouro (Rua/Avenida)")
            if not numero_clean:
                erros_cliente.append("Número (se não houver, preencha como 'S/N')")
            if not bairro_clean:
                erros_cliente.append("Bairro")
            if not municipio_clean:
                erros_cliente.append("Município/Cidade")
            if not uf_cliente:
                erros_cliente.append("Estado (UF)")
            if not cep_clean or len(cep_clean) != 8:
                erros_cliente.append("CEP válido (8 dígitos)")
            if ind_ie == 1 and not ie_clean:
                erros_cliente.append("Inscrição Estadual (IE) válida para destinatário Contribuinte do ICMS")
                
            if erros_cliente:
                raise HTTPException(
                    status_code=400,
                    detail=f"Erro ao emitir NFe: O cadastro do destinatário ou o endereço de entrega do pedido está incompleto. Por favor, preencha os seguintes campos obrigatórios: {', '.join(erros_cliente)}."
                )

            cliente = Cliente(
                razao_social=razao_social_clean,
                tipo_documento=tipo_doc,
                email=self._limpar_texto(cli_db.email or ''),
                numero_documento=self._limpar_formatacao(cli_db.cpf_cnpj),
                indicador_ie=ind_ie,
                inscricao_estadual=ie_clean or '',
                endereco_logradouro=logradouro_clean,
                endereco_numero=numero_clean,
                endereco_complemento=complemento_clean,
                endereco_bairro=bairro_clean,
                endereco_municipio=municipio_clean,
                endereco_uf=uf_cliente,
                endereco_cep=cep_clean,
                endereco_pais=CODIGO_BRASIL,
                endereco_telefone=telefone_clean
            )

            # --- NOTA FISCAL (CABEÇALHO) ---
            if is_development:
                import random
                numero_nf = random.randint(900000000, 999999999)
                logger.info(f"[NFe] Ambiente de desenvolvimento detectado. Usando número aleatório: {numero_nf}")
            else:
                # BLOQUEIO DE CONCORRÊNCIA: Busca a empresa novamente com 'FOR UPDATE' 
                # para garantir que nenhuma outra thread use o mesmo número simultaneamente.
                # populate_existing() forca o SQLAlchemy a ignorar o cache local e trazer o valor atual do banco.
                empresa_lock = self.db.query(models.Empresa).with_for_update().populate_existing().filter(
                    models.Empresa.id == self.id_empresa
                ).first()
                
                if not empresa_lock:
                    raise HTTPException(status_code=400, detail="Erro ao bloquear registro da empresa para numeração.")
                
                # Atualiza a referência local para o objeto bloqueado
                self.empresa = empresa_lock
                numero_nf = self.empresa.nfe_numero_sequencial
                
                # --- LÓGICA DE INTEGRIDADE "PERFEITA" ---
                # Verifica se este número já foi usado por outro pedido autorizado (Evita pulos por erro humano/DB)
                while True:
                    conflito = self.db.query(models.Pedido).filter(
                        models.Pedido.id_empresa == self.id_empresa,
                        models.Pedido.numero_nf == str(numero_nf),
                        models.Pedido.status_sefaz.like('100%')
                    ).first()
                    
                    if conflito:
                        logger.warning(f"[NFe] Conflito de Sequencial: O número {numero_nf} já foi usado no Pedido #{conflito.id}. Saltando para o próximo...")
                        self.empresa.nfe_numero_sequencial += 1
                        numero_nf = self.empresa.nfe_numero_sequencial
                    else:
                        break

                logger.info(f"[NFe] Iniciando emissão para Pedido #{pedido_id}. Usando número sequencial: {numero_nf}")
            
            serie_nf = self.empresa.nfe_serie

            # Modalidade Frete
            mod_frete = 9
            if pedido.modalidade_frete:
                try:
                    mod_frete = int(pedido.modalidade_frete.value)
                except:
                    pass

            # Determina Natureza da Operação PADRÃO (Baseado no Enum do Pedido)
            nat_op = 'VENDA DE MERCADORIA'
            tipo_op_enum = RegraTipoOperacaoEnum.venda_mercadoria
            
            if pedido.tipo_operacao:
                tipo_op_enum = pedido.tipo_operacao
                # Normaliza para ASCII Maiúsculo (Padrão NFe)
                raw_val = tipo_op_enum.value
                normalized = unicodedata.normalize('NFKD', raw_val).encode('ASCII', 'ignore').decode('ASCII')
                nat_op = normalized.upper()

            # Determina Finalidade (1=Normal, 2=Complementar, 4=Devolução)
            fin_nfe = 1
            tp_nf = 1 # 1=Saída (Padrão)
            
            if tipo_op_enum == RegraTipoOperacaoEnum.devolucao_entrada:
                fin_nfe = 4
                nat_op = 'DEVOLUCAO - ENTRADA'
                tp_nf = 0 # 0=Entrada
            elif tipo_op_enum == RegraTipoOperacaoEnum.devolucao_saida:
                fin_nfe = 4
                nat_op = 'DEVOLUCAO - SAIDA'
                tp_nf = 1 # 1=Saída
            elif tipo_op_enum == RegraTipoOperacaoEnum.complemento:
                fin_nfe = 2
                nat_op = 'COMPLEMENTO'
                tp_nf = 1 # 1=Saída

            # Lógica de Pagamento
            t_pag = '90' # Sem pagamento (default)
            ind_pag = 0  # Vista (default)

            # ==============================================================================
            # CORREÇÃO ERRO 871: Devolução/Complementar exige Meio de Pagamento = 90 (Sem Pagamento)
            # ==============================================================================
            if fin_nfe in [2, 3, 4]:
                t_pag = '90'
                ind_pag = 0
            # Se NÃO for devolução/complementar, segue a lógica normal do pedido
            elif pedido.pagamento:
                t_pag = pedido.pagamento.value
                
                # Heurística para indPag (0=Vista, 1=Prazo)
                # Consideramos Prazo: Cartão Crédito(03), Crédito Loja(05), Duplicata(14), Boleto(15)
                if t_pag in ['03', '05', '14', '15']:
                    ind_pag = 1
                else:
                    ind_pag = 0

            # --- NOVA LÓGICA: SOBRESCREVER COM DESCRIÇÃO DA REGRA ---
            # O objetivo é usar o nome da regra (ex: "Venda Consumidor PR") se houver uma regra definida.
            
            regra_para_header = regra_forcada
            
            # Garante que lista_itens esteja disponível
            lista_itens = pedido.itens if isinstance(pedido.itens, list) else []

            # Se não tem regra forçada manualmente, tentamos descobrir a regra do PRIMEIRO ITEM
            # para usar sua descrição como Natureza da Operação da nota toda.
            if not regra_para_header and lista_itens:
                try:
                    item_0 = lista_itens[0]
                    pid_0 = item_0.get('id_produto') or item_0.get('produto_id')
                    if pid_0:
                        prod_0 = self.db.query(models.Produto).filter(
                            models.Produto.id_empresa == self.id_empresa,
                            models.Produto.id_sequencial == pid_0
                        ).first()
                        if prod_0:
                            # Busca a regra que seria aplicada a este produto
                            regra_para_header = self._encontrar_regra_tributaria(prod_0, cli_db, tipo_op_enum)
                except Exception as e:
                    print(f"Aviso: Não foi possível definir regra para o cabeçalho: {e}")

            # Lógica para pegar IE ST do JSON se houver regra para o estado do cliente
            iest_especifico = None
            if regra_para_header and hasattr(regra_para_header, 'regras_uf') and regra_para_header.regras_uf:
                 regras_json = regra_para_header.regras_uf
                 # Suporte a estrutura nova (padrao_uf) e legada (direto)
                 padrao_uf = regras_json.get('padrao_uf', {})
                 if 'padrao_uf' not in regras_json and 'excecoes' not in regras_json:
                     padrao_uf = regras_json
                 
                 uf_rules = padrao_uf.get(uf_cliente, {})
                 if uf_rules.get('ie_st'):
                     iest_especifico = self._limpar_formatacao(uf_rules['ie_st'])

            # Se encontrou uma regra e ela tem descrição, usa ela!
            if regra_para_header and regra_para_header.descricao:
                # Remove acentos e caracteres especiais para não quebrar o XML
                desc_limpa = unicodedata.normalize('NFKD', regra_para_header.descricao).encode('ASCII', 'ignore').decode('ASCII')
                
                # Joga para maiúsculo e limita a 60 caracteres (Limite SEFAZ)
                nat_op = self._limpar_texto(desc_limpa.upper(), max_len=60)
            # --------------------------------------------------------

            # --- EMITENTE ---
            # CRT: 1=Simples Nacional, 2=Simples Excesso, 3=Regime Normal
            # Mapeamento do Enum interno (que separa Real/Presumido) para o código CRT da NFe
            crt_map = {
                models.EmpresaCRTEnum.simples_nacional: '1',
                models.EmpresaCRTEnum.simples_excesso: '2',
                models.EmpresaCRTEnum.lucro_presumido: '3',
                models.EmpresaCRTEnum.lucro_real: '3'
            }
            crt_val = crt_map.get(self.empresa.crt, '1')
            
            # --- PRÉ-VALIDAÇÃO E SANITIZAÇÃO DO EMITENTE (EMPRESA) ---
            emp_razao_clean = self._limpar_texto(self.empresa.razao)
            emp_fantasia_clean = self._limpar_texto(self.empresa.fantasia or self.empresa.razao)
            emp_logradouro_clean = self._limpar_texto(self.empresa.logradouro)
            emp_numero_clean = self._limpar_texto(self.empresa.numero)
            emp_bairro_clean = self._limpar_texto(self.empresa.bairro)
            emp_municipio_clean = self._limpar_texto(self.empresa.cidade)
            emp_cep_clean = self._limpar_formatacao(self.empresa.cep)
            emp_cnpj_clean = self._limpar_formatacao(self.empresa.cnpj)
            emp_ie_clean = self._limpar_formatacao(self.empresa.inscricao_estadual)
            
            erros_emitente = []
            if not emp_razao_clean:
                erros_emitente.append("Razão Social")
            if not emp_cnpj_clean:
                erros_emitente.append("CNPJ")
            if not emp_ie_clean:
                erros_emitente.append("Inscrição Estadual")
            if not emp_logradouro_clean:
                erros_emitente.append("Logradouro (Rua/Avenida)")
            if not emp_numero_clean:
                erros_emitente.append("Número")
            if not emp_bairro_clean:
                erros_emitente.append("Bairro")
            if not emp_municipio_clean:
                erros_emitente.append("Município/Cidade")
            if not emp_cep_clean or len(emp_cep_clean) != 8:
                erros_emitente.append("CEP válido (8 dígitos)")
                
            if erros_emitente:
                raise HTTPException(
                    status_code=400,
                    detail=f"Erro ao emitir NFe: Os dados da sua Empresa (Emitente) estão incompletos nas configurações. Por favor, preencha: {', '.join(erros_emitente)}."
                )

            emitente = Emitente(
                razao_social=emp_razao_clean,
                nome_fantasia=emp_fantasia_clean,
                cnpj=emp_cnpj_clean,
                codigo_de_regime_tributario=crt_val,
                inscricao_estadual=emp_ie_clean,
                inscricao_municipal=self._limpar_formatacao(self.empresa.inscricao_municipal),
                cnae_fiscal=self._limpar_formatacao(self.empresa.cnae),
                endereco_logradouro=emp_logradouro_clean,
                endereco_numero=emp_numero_clean,
                endereco_bairro=emp_bairro_clean,
                endereco_municipio=emp_municipio_clean,
                endereco_uf=uf_empresa,
                endereco_cep=emp_cep_clean,
                endereco_pais=CODIGO_BRASIL,
                inscricao_estadual_subst_tributaria=iest_especifico,
                endereco_telefone=self._limpar_formatacao(self.empresa.telefone)
            )

            # Lógica de Destino (idDest)
            # 1=Interna, 2=Interestadual, 3=Exterior
            ind_destino = 1
            if uf_cliente == 'EX':
                ind_destino = 3
            elif uf_cliente and uf_empresa and uf_cliente != uf_empresa:
                ind_destino = 2

            # Indicador de Presença (Lógica baseada no campo do Pedido)
            ind_pres = 1 # Default: Presencial
            if pedido.indicador_presenca:
                # Pega o valor inteiro do Enum
                ind_pres = pedido.indicador_presenca.value if hasattr(pedido.indicador_presenca, 'value') else pedido.indicador_presenca

            # Define Timezone BR
            fuso_br = timezone(timedelta(hours=-3))
            agora_br = datetime.now(fuso_br)

            nota_fiscal = NotaFiscal(
                emitente=emitente,
                cliente=cliente,
                uf=uf_empresa,
                natureza_operacao=self._limpar_texto(nat_op),
                # REMOVIDO: forma_pagamento e tipo_pagamento (Deprecated na NFe 4.0)
                # forma_pagamento=ind_pag, 
                # tipo_pagamento=t_pag,
                modelo=55,
                serie=str(serie_nf),
                numero_nf=str(numero_nf),
                data_emissao=agora_br,
                data_saida_entrada=agora_br,
                tipo_documento=tp_nf, # 1=Saída, 0=Entrada
                municipio=self._limpar_formatacao(self.empresa.cidade_ibge), # Sanitização do IBGE (7 dígitos)
                municipio_fato_gerador_ibs=self._limpar_formatacao(self.empresa.cidade_ibge),
                tipo_impressao_danfe=1,
                forma_emissao='1', # Normal
                cliente_final=1,   # Consumidor Final (Simplificado)
                indicador_destino=ind_destino, 
                indicador_presencial=ind_pres, # Dinâmico via Pedido
                finalidade_emissao=fin_nfe, # 1=Normal, 4=Devolução
                processo_emissao=0,
                transporte_modalidade_frete=mod_frete,
                informacoes_adicionais_interesse_fisco='',
                informacoes_complementares_interesse_contribuinte=self._limpar_texto(pedido.observacoes_nf or '')
            )
            nota_fiscal.informacoes_complementares = nota_fiscal.informacoes_complementares_interesse_contribuinte

            # --- TRANSPORTADORA ---
            if pedido.transportadora:
                transp_db = pedido.transportadora
                
                # --- PRÉ-VALIDAÇÃO E SANITIZAÇÃO DA TRANSPORTADORA ---
                transp_razao_clean = self._limpar_texto(transp_db.nome_razao, max_len=60)
                transp_cnpj_cpf_clean = self._limpar_formatacao(transp_db.cpf_cnpj)
                transp_logradouro_clean = self._limpar_texto(transp_db.logradouro, max_len=60)
                transp_municipio_clean = self._limpar_texto(transp_db.cidade, max_len=60)
                transp_uf = (transp_db.estado.value if hasattr(transp_db.estado, 'value') else transp_db.estado or "").upper()
                
                erros_transp = []
                if not transp_razao_clean:
                    erros_transp.append("Razão Social")
                if not transp_cnpj_cpf_clean:
                    erros_transp.append("CNPJ/CPF")
                
                # Se o endereço começar a ser preenchido, valida as partes obrigatórias do endereço da transportadora
                if transp_logradouro_clean or transp_municipio_clean or transp_uf:
                    if not transp_logradouro_clean:
                        erros_transp.append("Logradouro (Rua/Avenida)")
                    if not transp_municipio_clean:
                        erros_transp.append("Município/Cidade")
                    if not transp_uf:
                        erros_transp.append("Estado (UF)")
                
                if erros_transp:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Erro ao emitir NFe: Os dados da Transportadora selecionada estão incompletos. Por favor, preencha os seguintes campos obrigatórios: {', '.join(erros_transp)}."
                    )

                # 1. PREPARAÇÃO DOS DADOS
                doc_transp = transp_cnpj_cpf_clean
                
                # Tratamento da Inscrição Estadual
                ie_transp = self._limpar_formatacao(transp_db.inscricao_estadual)
                if not ie_transp:
                    ie_transp = None
                
                # 2. DEFINIÇÃO DO TIPO DE DOCUMENTO
                tipo_doc = "CNPJ"
                num_doc = doc_transp
                if len(doc_transp) == 11:
                    tipo_doc = "CPF"
                
                # 3. CRIAÇÃO DO OBJETO
                transportadora_nfe = Transportadora(
                    razao_social=transp_razao_clean,
                    tipo_documento=tipo_doc,
                    numero_documento=num_doc,
                    inscricao_estadual=ie_transp,
                    endereco_logradouro=transp_logradouro_clean or None,
                    endereco_municipio=transp_municipio_clean or None,
                    endereco_uf=transp_uf or None,
                    endereco_bairro=self._limpar_texto(transp_db.bairro, max_len=60) if transp_db.bairro else None
                )

                # VINCULA À NOTA
                nota_fiscal.transporte_transportadora = transportadora_nfe

                # 4. DADOS DO VEÍCULO E FRETE (Ficam na NotaFiscal, não na Transportadora)
                # Define a modalidade do frete na nota
                nota_fiscal.transporte_modalidade_frete = mod_frete

                if pedido.veiculo_placa:
                    # Limpa placa (remove traços/espaços e joga pra maiúsculo)
                    placa_clean = pedido.veiculo_placa.replace("-", "").replace(" ", "").upper().strip()
                    nota_fiscal.transporte_veiculo_placa = placa_clean
                
                if pedido.veiculo_uf:
                    uf_veic = pedido.veiculo_uf.value if hasattr(pedido.veiculo_uf, 'value') else pedido.veiculo_uf
                    nota_fiscal.transporte_veiculo_uf = uf_veic
                
                if pedido.veiculo_antt:
                    nota_fiscal.transporte_veiculo_rntc = self._limpar_formatacao(pedido.veiculo_antt)

            else:
                # Se não tem transportadora, define apenas a modalidade (ex: 9 - Sem Frete)
                nota_fiscal.transporte_modalidade_frete = mod_frete
            
            # --- NOTA REFERENCIADA (Para Devolução) ---
            icms_referenciado_zero = False
            if fin_nfe in [2, 4] and pedido.chave_nfe_referencia:
                nota_fiscal.adicionar_nota_fiscal_referenciada(
                    chave_acesso=pedido.chave_nfe_referencia,
                    tipo='Nota Fiscal eletronica'  # Importante definir o tipo para cair no serializador correto
                )
                
                # Tenta localizar a nota no banco para evitar a Rejeição 546 (ICMS superior à referenciada)
                ref_db = self.db.query(models.Pedido).filter(models.Pedido.chave_acesso == pedido.chave_nfe_referencia).first()
                if ref_db and ref_db.xml_autorizado:
                    xml_ref = ref_db.xml_autorizado
                    # Busca rápida: se o total de ICMS na original era 0.00
                    # Removemos espaços para busca mais robusta em XMLs minificados ou formatados
                    xml_clean = xml_ref.replace(' ', '').replace('\n', '').replace('\r', '')
                    if '<vICMS>0.00</vICMS>' in xml_clean or '<vICMS>0</vICMS>' in xml_clean:
                        icms_referenciado_zero = True
                        print(f"DEBUG: Detectado vICMS=0 na nota referenciada {pedido.chave_nfe_referencia}. Ativando proteção Rejeição 546.")

            # Override manual via observações (caso seja nota externa não presente no banco)
            if pedido.observacoes_nf and 'ZERAR_ICMS' in pedido.observacoes_nf.upper():
                icms_referenciado_zero = True
                print("DEBUG: Ativando proteção Rejeição 546 via palavra-chave ZERAR_ICMS nas observações.")

            # --- VOLUMES ---
            if pedido.volumes_quantidade and pedido.volumes_quantidade > 0:
                
                # Função auxiliar para garantir Decimal ou 0.00
                def sanitizar_peso(valor):
                    return safe_decimal(valor, "0.000")

                # --- FALLBACK DE PESO (Cálculo automático se zerado) ---
                peso_liquido_final = sanitizar_peso(pedido.volumes_peso_liquido)
                peso_bruto_final = sanitizar_peso(pedido.volumes_peso_bruto)

                if peso_liquido_final == 0 or peso_bruto_final == 0:
                    print("DEBUG: Pesos zerados no pedido. Calculando fallback via cadastro de produtos...")
                    peso_total_calc = Decimal('0.000')
                    
                    for item_dict in lista_itens:
                        try:
                            p_id = item_dict.get('id_produto') or item_dict.get('produto_id')
                            qtd_val = item_dict.get('quantidade', 0)
                            qtd = safe_decimal(qtd_val)
                            
                            if p_id and qtd > 0:
                                prod_peso = self.db.query(models.Produto.peso).filter(
                                    models.Produto.id_empresa == self.id_empresa,
                                    models.Produto.id_sequencial == p_id
                                ).scalar()
                                if prod_peso:
                                    peso_total_calc += (safe_decimal(prod_peso) * qtd)
                        except Exception as e:
                            print(f"Erro ao calcular peso fallback item: {e}")

                    # Arredonda o final para 3 casas
                    peso_total_calc = peso_total_calc.quantize(Decimal('0.000'))

                    if peso_liquido_final == 0: peso_liquido_final = peso_total_calc
                    if peso_bruto_final == 0: peso_bruto_final = peso_total_calc

                nota_fiscal.adicionar_transporte_volume(
                    quantidade=pedido.volumes_quantidade,
                    especie=pedido.volumes_especie,
                    marca=pedido.volumes_marca,
                    numeracao=pedido.volumes_numeracao,
                    peso_liquido=peso_liquido_final,
                    peso_bruto=peso_bruto_final
                )

            # --- ITENS DO PEDIDO ---
            
            # --- PREPARAÇÃO PARA ACUMULADORES (Correção do Pagamento) ---
            total_nfe_calculado = Decimal('0.00') # Soma de vProd + vFrete + vIPI + vST + vOutro - vDesc
            
            # Lista para guardar dados de DIFAL para injeção manual posterior
            difal_data_injection = {} 
            icms51_data_injection = {} 
            
            # [NOVO] Dicionários para Injeção da Reforma Tributária (IBS/CBS)
            ibscbs_data_injection = {}
            totais_ibscbs = {
                'vBCIBSCBS': Decimal('0.00'),
                'vIBSUF': Decimal('0.00'),
                'vIBSMun': Decimal('0.00'),
                'vIBS': Decimal('0.00'),
                'vCBS': Decimal('0.00')
            }

            # Busca o pedido de origem (se for complemento) para servir de base para os impostos
            origem_itens_map = {}
            if tipo_op_enum == RegraTipoOperacaoEnum.complemento and ref_db and ref_db.itens:
                for orig_item in ref_db.itens:
                    orig_prod_id = orig_item.get('id_produto') or orig_item.get('produto_id')
                    orig_sku = orig_item.get('sku')
                    if orig_prod_id:
                        origem_itens_map[f"id_{orig_prod_id}"] = orig_item
                    if orig_sku:
                        origem_itens_map[f"sku_{orig_sku}"] = orig_item

            if not lista_itens:
                raise HTTPException(status_code=400, detail="O pedido não possui itens. Impossível emitir NFe.")

            # Pré-cálculo do total dos produtos para rateio de frete
            total_produtos_pedido = Decimal('0.00')
            for item in lista_itens:
                qtd = safe_decimal(item.get('quantidade', 0))
                valor_unit = safe_decimal(item.get('valor_unitario', 0))
                subtotal = safe_decimal(item.get('subtotal'))
                total_com_ipi = safe_decimal(item.get('total_com_ipi'))
                prod_id = item.get('id_produto') or item.get('produto_id')
                
                if tipo_op_enum == RegraTipoOperacaoEnum.complemento:
                    if subtotal > 0:
                        v_item = subtotal
                    elif total_com_ipi > 0:
                        v_item = total_com_ipi
                    else:
                        # Tenta buscar do item original
                        orig_item = None
                        sku = item.get('sku')
                        if prod_id and f"id_{prod_id}" in origem_itens_map:
                            orig_item = origem_itens_map[f"id_{prod_id}"]
                        elif sku and f"sku_{sku}" in origem_itens_map:
                            orig_item = origem_itens_map[f"sku_{sku}"]
                        
                        orig_subtotal = Decimal('0.00')
                        if orig_item:
                            orig_subtotal = safe_decimal(orig_item.get('subtotal') or orig_item.get('total_com_ipi'))
                        
                        if orig_subtotal > 0:
                            v_item = orig_subtotal
                        else:
                            v_item = (qtd * valor_unit).quantize(Decimal('0.01'))
                    
                    # Fallback robusto: se o item resultou em 0, mas é o único item e o pedido tem total manual,
                    # usamos o total do pedido como base para o cálculo dos impostos do item!
                    if v_item == 0 and len(lista_itens) == 1 and pedido.total and pedido.total > 0:
                        v_item = safe_decimal(pedido.total)
                else:
                    v_item = (qtd * valor_unit).quantize(Decimal('0.01'))
                total_produtos_pedido += v_item

            total_produtos = Decimal('0.00')
            total_tributos_aprox = Decimal('0.00')
            itens_adicionados_count = 0
            
            for i, item in enumerate(lista_itens):
                prod_id = item.get('id_produto')
                # Fallback se o JSON vier com 'produto_id'
                if not prod_id:
                    prod_id = item.get('produto_id')

                if not prod_id:
                    print(f"Item {i} sem ID de produto. Pulando.")
                    continue

                produto_db = self.db.query(models.Produto).filter(
                    models.Produto.id_empresa == self.id_empresa,
                    models.Produto.id_sequencial == prod_id
                ).first()
                
                if not produto_db:
                    print(f"Produto ID {prod_id} não encontrado no banco. Pulando.")
                    continue

                itens_adicionados_count += 1

                # CORREÇÃO (Proteção contra None/empty e suporte a complemento)
                qtd_raw = item.get('quantidade')
                qtd = safe_decimal(qtd_raw)

                val_raw = item.get('valor_unitario')
                valor_unit = safe_decimal(val_raw)
                
                subtotal = safe_decimal(item.get('subtotal'))
                total_com_ipi = safe_decimal(item.get('total_com_ipi'))

                if tipo_op_enum == RegraTipoOperacaoEnum.complemento:
                    if subtotal > 0:
                        valor_total = subtotal
                    elif total_com_ipi > 0:
                        valor_total = total_com_ipi
                    else:
                        # Tenta buscar do item original
                        orig_item = None
                        sku = item.get('sku')
                        if prod_id and f"id_{prod_id}" in origem_itens_map:
                            orig_item = origem_itens_map[f"id_{prod_id}"]
                        elif sku and f"sku_{sku}" in origem_itens_map:
                            orig_item = origem_itens_map[f"sku_{sku}"]
                        
                        orig_subtotal = Decimal('0.00')
                        if orig_item:
                            orig_subtotal = safe_decimal(orig_item.get('subtotal') or orig_item.get('total_com_ipi'))
                        
                        if orig_subtotal > 0:
                            valor_total = orig_subtotal
                        else:
                            valor_total = (qtd * valor_unit).quantize(Decimal('0.01'))
                    
                    # Fallback robusto: se o item resultou em 0, mas é o único item e o pedido tem total manual,
                    # usamos o total do pedido como base para o cálculo dos impostos do item!
                    if valor_total == 0 and len(lista_itens) == 1 and pedido.total and pedido.total > 0:
                        valor_total = safe_decimal(pedido.total)
                else:
                    valor_total = (qtd * valor_unit).quantize(Decimal('0.01'))
                
                total_produtos += valor_total

                # Rateio de Frete
                valor_frete_item = Decimal('0.00')
                if pedido.valor_frete and total_produtos_pedido > 0:
                    valor_frete_item = (pedido.valor_frete * (valor_total / total_produtos_pedido)).quantize(Decimal('0.01'))
                # Sanitização: TDec_1302 não aceita valores negativos no XML
                if valor_frete_item < Decimal('0.00'):
                    print(f"AVISO: valor_frete_item negativo ({valor_frete_item}), convertendo para positivo.")
                    valor_frete_item = abs(valor_frete_item)

                # Rateio de Desconto
                valor_desconto_item = Decimal('0.00')
                if pedido.desconto and total_produtos_pedido > 0:
                    valor_desconto_item = (pedido.desconto * (valor_total / total_produtos_pedido)).quantize(Decimal('0.01'))
                # Sanitização: TDec_1302 não aceita valores negativos no XML (ex: desconto negativo = acréscimo)
                if valor_desconto_item < Decimal('0.00'):
                    print(f"AVISO: valor_desconto_item negativo ({valor_desconto_item}), convertendo para positivo. pedido.desconto={pedido.desconto}")
                    valor_desconto_item = abs(valor_desconto_item)

                ncm = self._limpar_formatacao(produto_db.ncm) or '00000000'
                cfop = None
                
                unidade = produto_db.unidade.value if hasattr(produto_db.unidade, 'value') else 'UN'
                unidade = unidade.upper()

                # --- CORREÇÃO AQUI: Mapeamento de Origem ---
                # Pega o valor do banco (ex: "nacional")
                origem_db = produto_db.origem.value if hasattr(produto_db.origem, 'value') else str(produto_db.origem)
                
                # Tabela De/Para conforme Manual da NFe
                mapa_origem = {
                    "nacional": FiscalOrigemEnum.origem_0.value,
                    "estrangeira_import_direta": FiscalOrigemEnum.origem_1.value,
                    "estrangeira_adq_merc_interno": FiscalOrigemEnum.origem_2.value,
                    "nacional_conteudo_import_40": FiscalOrigemEnum.origem_3.value,
                    "nacional_producao_basica": FiscalOrigemEnum.origem_4.value,
                    "nacional_conteudo_import_70": FiscalOrigemEnum.origem_8.value,
                }
                
                # Se não achar no mapa, tenta usar o valor do banco (caso já seja numérico) ou assume "0"
                icms_origem_val = mapa_origem.get(origem_db, FiscalOrigemEnum.origem_0.value)
                if origem_db.isdigit(): # Se o banco já tiver "0", "1", etc.
                    icms_origem_val = origem_db

                # --- 1. INTEGRAÇÃO TRIBUTÁRIA E LEITURA DO JSON (AGORA NO INÍCIO) ---
                regra = regra_forcada
                if not regra:
                    regra = self._encontrar_regra_tributaria(produto_db, cli_db, tipo_op_enum)
                    
                    # FALLBACK DEVOLUÇÃO E COMPLEMENTO: Se não encontrar regra específica de devolução ou complemento,
                    # tenta aplicar a regra de Venda para manter a tributação (destaque de ICMS/IBS/CBS)
                    if not regra and tipo_op_enum in [RegraTipoOperacaoEnum.devolucao_entrada, RegraTipoOperacaoEnum.devolucao_saida, RegraTipoOperacaoEnum.complemento]:
                        print(f"DEBUG: Fallback - Buscando regra de Venda para produto {produto_db.sku}")
                        regra = self._encontrar_regra_tributaria(produto_db, cli_db, RegraTipoOperacaoEnum.venda_mercadoria)
                
                # Se a regra tributária tiver uma origem forçada, ela prevalece
                if regra and regra.origem_produto:
                    icms_origem_val = regra.origem_produto.value
                
                # Valores padrão (Fallback)
                icms_cst_val = '400' if crt_val == '1' else '41'
                pis_cst_val = '07'
                cofins_cst_val = '07'
                ipi_cst_val = '53' # Não tributado
                cfop = '5102'
                aliq_intra = Decimal('0.00')
                aliq_inter = Decimal('0.00') 
                fcp_final = Decimal('0.00')
                cbenef_val = None
                
                # Definição preliminar da alíquota interestadual (padrão 4, 7 ou 12)
                aliq_inter_padrao = self._get_aliquota_interestadual(uf_empresa, uf_cliente, icms_origem_val)
                
                # --- LEITURA DO JSON (Prioridade Máxima) ---
                excecao_aplicada = None
                if regra and hasattr(regra, 'regras_uf') and regra.regras_uf:
                    regras_json = regra.regras_uf
                    
                    # Normalização da estrutura
                    padrao_uf = regras_json.get('padrao_uf', {}) if 'padrao_uf' in regras_json else regras_json
                    excecoes = regras_json.get('excecoes', [])

                    # 1.1 Busca Exceções (Produto específico)
                    for ex in excecoes:
                        if uf_cliente in ex.get('ufs', []):
                            ex_prod_id = str(ex.get('id_produto')) if ex.get('id_produto') else None
                            item_prod_id = str(produto_db.id)
                            if not ex_prod_id or ex_prod_id == item_prod_id:
                                excecao_aplicada = ex
                                break
                    
                    if excecao_aplicada:
                        if excecao_aplicada.get('cst'): icms_cst_val = excecao_aplicada['cst']
                        if excecao_aplicada.get('cfop'): cfop = self._limpar_formatacao(excecao_aplicada['cfop'])
                        if excecao_aplicada.get('aliq_intra'): aliq_intra = safe_decimal(excecao_aplicada['aliq_intra'])
                        # Se tiver alíquota interestadual específica na exceção
                        if excecao_aplicada.get('aliq_inter'): aliq_inter = safe_decimal(excecao_aplicada['aliq_inter'])
                        if excecao_aplicada.get('cbenef'): cbenef_val = excecao_aplicada['cbenef']

                    # 1.2 Busca Padrão UF (Se não achou na exceção)
                    if aliq_intra == 0:
                        dados_uf = padrao_uf.get(uf_cliente, {})
                        if dados_uf:
                            if dados_uf.get('aliq_intra'): aliq_intra = safe_decimal(dados_uf['aliq_intra'])
                            if dados_uf.get('fcp'): fcp_final = safe_decimal(dados_uf['fcp'])
                            if dados_uf.get('aliq_inter'): aliq_inter = safe_decimal(dados_uf['aliq_inter'])

                # Fallback: Se o JSON não definiu a interestadual, usa a regra padrão (4/7/12)
                if aliq_inter == 0:
                    aliq_inter = aliq_inter_padrao

                # --- DEFINIÇÃO DA ALÍQUOTA FINAL DO ITEM ---
                # Se for interestadual, usa a aliq_inter do JSON. Se for interna, usa a aliq_intra do JSON.
                aliquota_final_item = Decimal('0.00')
                
                if ind_destino == 2: # Interestadual
                    aliquota_final_item = aliq_inter
                else: # Interna
                    aliquota_final_item = aliq_intra if aliq_intra > 0 else Decimal('0.00')

                print(f"DEBUG ITEM {i+1}: Alíquota definida pelo JSON: {aliquota_final_item}% (Destino: {ind_destino})")

                # Inicializa variáveis de diferimento
                p_dif = Decimal('0.00')
                val_icms_operacao = Decimal('0.00')
                val_icms_diferido = Decimal('0.00')

                # Inicializa variáveis de valor para cálculo do total aproximado
                val_icms = Decimal('0.00')
                val_pis = Decimal('0.00')
                val_cofins = Decimal('0.00')
                val_ipi = Decimal('0.00')
                val_fcp = Decimal('0.00')

                # Dicionário de tributos para o PyNFE
                # Inicializamos com os atributos que costumam dar erro de "missing attribute" na lib
                kwargs_tributos = {
                    'icms_credito': Decimal('0.00'),
                    'icms_aliquota_credito': Decimal('0.00')
                }
                inf_adicional_item = ""

                if regra:
                    # Atualiza CSTs com base na regra, se não vieram da exceção do JSON
                    if regra.icms_cst and not excecao_aplicada: icms_cst_val = regra.icms_cst.value
                    if regra.pis_cst: pis_cst_val = regra.pis_cst.value
                    if regra.cofins_cst: cofins_cst_val = regra.cofins_cst.value
                    if regra.ipi_cst: ipi_cst_val = regra.ipi_cst.value
                    if regra.cfop and not excecao_aplicada: cfop = self._limpar_formatacao(regra.cfop)
                    if hasattr(regra, 'cbenef') and regra.cbenef and not excecao_aplicada: cbenef_val = regra.cbenef

                    # --- CÁLCULO IPI (CORREÇÃO DE MAPEAMENTO PYNFE) ---
                    # A biblioteca PyNFE (nesta versão) usa 'ipi_codigo_enquadramento' para gerar a tag <CST>
                    # e usa 'ipi_classe_enquadramento' para gerar a tag <cEnq>.
                    # Por isso, precisamos inverter o mapeamento padrão.
                    
                    c_enq = regra.ipi_codigo_enquadramento or '999'
                    
                    if regra.ipi_cst: 
                        # CST (ex: 50)
                        ipi_cst_val = regra.ipi_cst.value
                        
                        # Prioriza a alíquota salva no item do pedido, fallback para o cadastro do produto
                        aliq_ipi_val = item.get('ipi_aliquota')
                        if aliq_ipi_val is None or str(aliq_ipi_val).strip() == "":
                            aliq_ipi_val = produto_db.ipi_aliquota or Decimal('0.00')
                        aliq_ipi = safe_decimal(aliq_ipi_val)
                        
                        # Base de Cálculo do IPI = Valor Produto + Frete
                        base_ipi = valor_total + valor_frete_item
                        
                        # Calcula valor se a alíquota for maior que zero
                        val_ipi = Decimal('0.00')
                        if aliq_ipi > 0:
                             val_ipi = self._calc_valor(base_ipi, aliq_ipi)

                        kwargs_tributos.update({
                            'ipi_codigo_enquadramento': ipi_cst_val,
                            'ipi_classe_enquadramento': c_enq,
                            'ipi_valor_ipi': val_ipi,
                            'ipi_aliquota': aliq_ipi,
                            'ipi_valor_base_calculo': base_ipi
                        })

                    # --- CÁLCULO ICMS ---
                    if tipo_op_enum == RegraTipoOperacaoEnum.complemento:
                        total_com_descontos = safe_decimal(pedido.total_desconto)
                        if total_com_descontos == 0:
                            total_com_descontos = safe_decimal(pedido.total) - safe_decimal(pedido.desconto)
                        
                        if total_com_descontos > 0:
                            if len(lista_itens) == 1:
                                base_icms = total_com_descontos
                            elif total_produtos_pedido > 0:
                                base_icms = (total_com_descontos * (valor_total / total_produtos_pedido)).quantize(Decimal('0.01'))
                            else:
                                base_icms = (total_com_descontos / Decimal(len(lista_itens))).quantize(Decimal('0.01'))
                        else:
                            base_icms = valor_total + valor_frete_item + val_ipi - valor_desconto_item
                    else:
                        base_icms = valor_total + valor_frete_item + val_ipi - valor_desconto_item

                    if base_icms < 0: base_icms = Decimal('0.00')

                    if regra.icms_reducao_bc_perc and regra.icms_reducao_bc_perc > 0:
                        base_icms = base_icms * (1 - (regra.icms_reducao_bc_perc / 100))
                    
                    base_icms = base_icms.quantize(Decimal('0.01'))

                    # AQUI ESTÁ A MÁGICA: Usamos aliquota_final_item (vinda do JSON)
                    val_icms_operacao = self._calc_valor(base_icms, aliquota_final_item)
                    
                    # Lógica de Diferimento (CST 51)
                    val_icms_diferido = Decimal('0.00')
                    p_dif = Decimal('0.00')
                    if icms_cst_val == '51':
                        p_dif = regra.icms_p_dif or Decimal('0.00')
                        if p_dif > 0:
                            val_icms_diferido = self._calc_valor(val_icms_operacao, p_dif)
                    
                    val_icms = val_icms_operacao - val_icms_diferido
                    val_fcp = self._calc_valor(base_icms, regra.fcp_aliquota) # FCP usa mesma base do ICMS geralmente

                    if fin_nfe == 4 and icms_referenciado_zero:
                        val_icms = Decimal('0.00')
                        val_fcp = Decimal('0.00')

                    # Mapeamento CST/CSOSN
                    if crt_val == '1': # Simples Nacional
                        
                        # --- CORREÇÃO ERRO 531 ---
                        # Para CSOSN que não destaca imposto (102, 103, 300, 400, etc), 
                        # devemos zerar os valores passados para a lib, caso contrário
                        # ela soma no Total da Nota, mas o XML do item fica sem valor.
                        v_bc_sn = base_icms
                        v_icms_sn = val_icms
                        p_icms_sn = aliquota_final_item

                        # Lista de CSOSNs que NÃO devem jogar valor para o Total da Nota
                        # (O 900 é exceção pois pode tributar)
                        if icms_cst_val in ['101', '102', '103', '300', '400', '500'] or (fin_nfe == 4 and icms_referenciado_zero):
                            v_bc_sn = Decimal('0.00')
                            v_icms_sn = Decimal('0.00')
                            p_icms_sn = Decimal('0.00')
                        # -------------------------

                        kwargs_tributos.update({
                            'icms_modalidade': icms_cst_val, # PyNFE usa 'modalidade' para definir a classe (ICMSSN102, etc)
                            'icms_csosn': icms_cst_val,
                            'icms_origem': icms_origem_val,
                            'icms_valor': v_icms_sn,
                            'icms_aliquota': p_icms_sn,
                            'icms_valor_base_calculo': v_bc_sn
                        })
                    else: # Regime Normal
                        
                        # --- CORREÇÃO ERROS 531 E 532 (REGIME NORMAL) ---
                        # A pynfe não gera as tags <vBC> e <vICMS> nos itens para alguns CSTs.
                        # Se passarmos o valor para a lib, ela soma no Total, mas omite no Item, 
                        # causando rejeição por divergência na SEFAZ.
                        v_bc_normal = base_icms
                        v_icms_normal = val_icms
                        p_icms_normal = aliquota_final_item
                        
                        # Lista de CSTs onde a pynfe ignora a Base de Cálculo e o ICMS:
                        # REMOVIDO 51 desta lista para permitir destaque de diferimento
                        csts_sem_vbc = ['30', '40', '41', '50', '60']
                        
                        if icms_cst_val in csts_sem_vbc or (fin_nfe == 4 and icms_referenciado_zero):
                            v_bc_normal = Decimal('0.00')
                            v_icms_normal = Decimal('0.00')
                            p_icms_normal = Decimal('0.00')

                        kwargs_tributos.update({
                            'icms_modalidade': icms_cst_val,
                            'icms_modalidade_determinacao_bc': 3,
                            'icms_origem': icms_origem_val,
                            'icms_valor': v_icms_normal,
                            'icms_aliquota': p_icms_normal,
                            'icms_valor_base_calculo': v_bc_normal
                        })
                        
                        # Adiciona campos de diferimento se for CST 51
                        if icms_cst_val == '51':
                            # Nomes corretos conforme notafiscal.py (mesmo que sob o comentário monofásico)
                            kwargs_tributos.update({
                                'icms_p_dif': p_dif,
                                'icms_v_icms_mono_op': val_icms_operacao,
                                'icms_v_icms_mono_dif': val_icms_diferido,
                            })

                            icms51_data_injection[itens_adicionados_count] = {
                                'vBC': base_icms,
                                'pICMS': aliquota_final_item,
                                'vICMSOp': val_icms_operacao,
                                'pDif': p_dif,
                                'vICMSDif': val_icms_diferido,
                                'vICMS': val_icms,
                                'pRedBC': regra.icms_reducao_bc_perc or Decimal('0.00')
                            }
                        
                        if val_fcp > 0:
                            kwargs_tributos['fcp_valor'] = val_fcp
                            kwargs_tributos['fcp_aliquota'] = regra.fcp_aliquota
                            kwargs_tributos['fcp_valor_base_calculo'] = base_icms

                    # --- CÁLCULO PIS/COFINS ---
                    # Ajuste: Base = Valor Produto + Frete - Desconto (Seguro/Outras se houver)
                    base_pis_cofins = valor_total + valor_frete_item - valor_desconto_item
                    if base_pis_cofins < 0: base_pis_cofins = Decimal('0.00')

                    val_pis = self._calc_valor(base_pis_cofins, regra.pis_aliquota)
                    val_cofins = self._calc_valor(base_pis_cofins, regra.cofins_aliquota)
                    kwargs_tributos.update({
                        'pis_modalidade': pis_cst_val,
                        'pis_valor': val_pis,
                        'pis_aliquota_percentual': regra.pis_aliquota or Decimal('0.00'),
                        'pis_valor_base_calculo': base_pis_cofins,
                        'cofins_modalidade': cofins_cst_val,
                        'cofins_valor': val_cofins,
                        'cofins_aliquota_percentual': regra.cofins_aliquota or Decimal('0.00'),
                        'cofins_valor_base_calculo': base_pis_cofins
                    })

                else:
                    # --- FALLBACK (QUANDO NÃO ACHA REGRA) ---
                    # Se for Simples Nacional (CRT 1)
                    if crt_val == '1':
                        kwargs_tributos.update({
                            'icms_modalidade': '102', # CSOSN
                            'icms_csosn': '102',
                            'icms_origem': icms_origem_val,
                            'pis_modalidade': '07',   # Isento
                            'cofins_modalidade': '07' # Isento
                        })
                    else:
                        # Se for Regime Normal (CRT 3 - Lucro Real/Presumido)
                        # Fallback seguro: CST 00 (Tributada Integralmente) mas com valores zerados
                        kwargs_tributos.update({
                            'icms_modalidade': '00', # CST 00
                            'icms_origem': icms_origem_val,
                            'icms_valor': Decimal('0.00'),
                            'icms_aliquota': Decimal('0.00'),
                            'icms_valor_base_calculo': valor_total,
                            'pis_modalidade': '07',
                            'cofins_modalidade': '07',
                            'pis_valor': Decimal('0.00'),
                            'cofins_valor': Decimal('0.00')
                        })

                # ==============================================================================
                # TRATAMENTO CBENEF (REJEIÇÃO 930 - PARANÁ, RS, RJ, SC)
                # ==============================================================================
                csts_exigem_cbenef = ['20', '30', '40', '41', '60', '70', '90']
                if crt_val != '1' and icms_cst_val in csts_exigem_cbenef:
                    if not cbenef_val:
                        cbenef_val = 'SEM CBENEF' # Fallback automático aceito pela SEFAZ
                
                if cbenef_val:
                    kwargs_tributos['cbenef'] = cbenef_val # Injeta direto no construtor da pynfe
                # ==============================================================================
                
                # Cálculo da carga tributária aproximada (Lei da Transparência)
                valor_tributos_aprox = (val_icms + val_pis + val_cofins + val_ipi + val_fcp).quantize(Decimal('0.01'))
                total_tributos_aprox += valor_tributos_aprox

                # =================================================================
                # CÁLCULO DIFAL POR DENTRO (BASE DUPLA / LC 190)
                # =================================================================
                
                # Regra de negócio: Gera DIFAL apenas para Interestadual (2) e Não Contribuinte (9)
                gera_difal = (ind_destino == 2 and ind_ie == 9)
                
                if gera_difal:
                    # 1. Definição das Alíquotas em Decimal
                    aliq_dest_dec = aliq_intra / Decimal('100')
                    aliq_inter_dec = aliq_inter / Decimal('100')
                    aliq_fcp_dec = fcp_final / Decimal('100')

                    # 2. Definição da Base Original (Valor da Operação)
                    # Base = Valor Produto + Frete + IPI + Outras - Desconto
                    base_operacao = valor_total + valor_frete_item + val_ipi - valor_desconto_item
                    if base_operacao < 0: base_operacao = Decimal('0.00')
                    
                    # 3. CÁLCULO DA BASE DUPLA ("POR DENTRO")
                    # Passo A: Remover o ICMS de Origem para achar o valor líquido
                    # (Assumindo que o preço de venda já incluía o ICMS de origem)
                    valor_liquido = base_operacao * (Decimal('1.00') - aliq_inter_dec)

                    # Passo B: Formar a nova base incluindo o ICMS de Destino (+ FCP se houver)
                    # O divisor é (1 - Carga Tributária Destino)
                    carga_tributaria_dest = aliq_dest_dec + aliq_fcp_dec
                    divisor = Decimal('1.00') - carga_tributaria_dest

                    if divisor > 0:
                        base_difal_por_dentro = valor_liquido / divisor
                    else:
                        base_difal_por_dentro = base_operacao

                    base_difal_por_dentro = base_difal_por_dentro.quantize(Decimal('0.01'))

                    # 4. Cálculo dos Valores Finais
                    # Valor do ICMS no Destino (Full)
                    valor_icms_destino_cheio = (base_difal_por_dentro * aliq_dest_dec).quantize(Decimal('0.01'))
                    
                    # Valor do ICMS na Origem (Creditado)
                    valor_icms_origem = (base_operacao * aliq_inter_dec).quantize(Decimal('0.01'))

                    # DIFAL a pagar é a diferença
                    valor_difal = valor_icms_destino_cheio - valor_icms_origem
                    
                    if valor_difal < 0:
                        valor_difal = Decimal('0.00')

                    # 5. Cálculo do FCP (Sobre a nova base por dentro)
                    valor_fcp_dest = (base_difal_por_dentro * aliq_fcp_dec).quantize(Decimal('0.01'))

                    print(f"-> DIFAL (POR DENTRO) ITEM {itens_adicionados_count}: Base Orig={base_operacao} | Base Dest={base_difal_por_dentro} | DIFAL={valor_difal}")

                    # Armazena para injeção no XML
                    difal_data_injection[itens_adicionados_count] = {
                        'vBCUFDest': base_difal_por_dentro,      # A Base no XML deve ser a base "por dentro"
                        'vBCFCPUFDest': base_difal_por_dentro,   # Mesma base para o FCP
                        'pFCPUFDest': fcp_final,
                        'pICMSUFDest': aliq_intra,
                        'pICMSInter': aliq_inter,
                        'pICMSInterPart': Decimal('100.00'),
                        'vFCPUFDest': valor_fcp_dest,
                        'vICMSUFDest': valor_difal,
                        'vICMSUFRemet': Decimal('0.00')
                    }

                # --- REFORMA TRIBUTÁRIA 2026 (IBS/CBS) ---
                val_ibs = Decimal('0.00')
                val_cbs = Decimal('0.00')
                
                # Base de cálculo
                base_reforma = valor_total + valor_frete_item - valor_desconto_item
                if base_reforma < 0: base_reforma = Decimal('0.00')

                if regra and (regra.ibs_aliquota or regra.cbs_aliquota):
                    aliquota_ibs = regra.ibs_aliquota or Decimal('0.00')
                    aliquota_cbs = regra.cbs_aliquota or Decimal('0.00')
                    
                    val_ibs = self._calc_valor(base_reforma, aliquota_ibs)
                    val_cbs = self._calc_valor(base_reforma, aliquota_cbs)

                    cst_reforma = regra.reforma_cst or '000'
                    class_trib = regra.reforma_c_class_trib or '000001'

                    # Guarda os dados exatos para injeção direta no XML do item
                    ibscbs_data_injection[itens_adicionados_count] = {
                        'CST': cst_reforma,
                        'cClassTrib': class_trib,
                        'vBC': base_reforma,
                        'pIBSUF': aliquota_ibs,
                        'vIBSUF': val_ibs,
                        'pIBSMun': Decimal('0.00'),
                        'vIBSMun': Decimal('0.00'),
                        'vIBS': val_ibs,
                        'pCBS': aliquota_cbs,
                        'vCBS': val_cbs
                    }

                    # Acumula os Totais para a tag final <IBSCBSTot>
                    if cst_reforma in ['000', '010', '200', '400', '510', '600', '620', '800', '810', '900']:
                        totais_ibscbs['vBCIBSCBS'] += base_reforma
                        totais_ibscbs['vIBSUF'] += val_ibs
                        totais_ibscbs['vIBS'] += val_ibs
                        totais_ibscbs['vCBS'] += val_cbs

                # ==============================================================================
                # CORREÇÃO AUTOMÁTICA DE CFOP (ERRO 733 + 327)
                # ==============================================================================
                if cfop and len(cfop) == 4:
                    cfop_original = cfop
                    novo_cfop = list(cfop)
                    
                    # 1. Correção de Prefixo (Geografia) - Erro 733
                    primeiro_digito = novo_cfop[0]
                    
                    if ind_destino == 2 and primeiro_digito == '5': # Interestadual
                        novo_cfop[0] = '6'
                    elif ind_destino == 1 and primeiro_digito == '6': # Interna
                        novo_cfop[0] = '5'
                        
                    # 2. Correção de Natureza (Devolução) - Erro 327
                    # CORREÇÃO: Converte str(fin_nfe) para garantir que funcione se for int ou str
                    if str(fin_nfe) == '4':
                        segundo_digito = novo_cfop[1]
                        # Transforma Venda (x1xx) em Devolução (x2xx)
                        if segundo_digito == '1':
                            novo_cfop[1] = '2'
                            print(f"DEBUG: Alterando natureza de Venda para Devolução (x1xx -> x2xx)")

                    cfop = "".join(novo_cfop)

                    if cfop != cfop_original:
                        print(f"DEBUG: CFOP Corrigido automaticamente: {cfop_original} -> {cfop}")

                # --- CONCATENAÇÃO SEGURA (Evita erro 225) ---
                lista_infos = []
                
                # 1. Info que veio do banco/parâmetro (se houver)
                if inf_adicional_item:
                    lista_infos.append(str(inf_adicional_item).strip())
                    
                # Junta com o separador " | " e garante que não tem espaços nas pontas
                inf_prod_final = " | ".join(lista_infos).strip()

                # ADICIONAR PRODUTO
                gtin_val = produto_db.gtin if produto_db.gtin else 'SEM GTIN'

                # Se for um complemento e a quantidade for zero, o valor do produto bruto no XML (vProd) deve ser 0.00
                v_prod_xml = valor_total
                if tipo_op_enum == RegraTipoOperacaoEnum.complemento and qtd == 0:
                    v_prod_xml = Decimal('0.00')

                nota_fiscal.adicionar_produto_servico(
                    codigo=self._limpar_texto(str(produto_db.sku)),
                    descricao=self._limpar_texto(produto_db.descricao),
                    ncm=ncm,
                    cfop=cfop,
                    unidade_comercial=unidade,
                    ean=gtin_val,
                    ean_tributavel=gtin_val,
                    quantidade_comercial=qtd,
                    valor_unitario_comercial=valor_unit,
                    valor_total_bruto=v_prod_xml,
                    unidade_tributavel=unidade,
                    quantidade_tributavel=qtd,
                    valor_unitario_tributavel=valor_unit,
                    ind_total=1,
                    valor_tributos_aprox=valor_tributos_aprox,
                    informacoes_adicionais=self._limpar_texto(inf_prod_final),
                    total_frete=valor_frete_item,
                    desconto=valor_desconto_item,

                    **kwargs_tributos
                )

            if itens_adicionados_count == 0:
                raise HTTPException(status_code=400, detail="Nenhum item válido foi processado. Verifique se os IDs dos produtos no pedido existem no banco de dados.")

            # --- PAGAMENTO (Grupo Pag - NFe 4.0) ---
            # Adiciona o grupo de pagamento usando o método correto
            
            if fin_nfe not in [3, 4]:
                # Venda Normal
                lista_pags = pedido.pagamentos if isinstance(pedido.pagamentos, list) else []
                pags_validos = [p for p in lista_pags if isinstance(p, dict) and (safe_decimal(p.get('valor')) > 0)]

                if len(pags_validos) > 0:
                    for item_p in pags_validos:
                        t_p = '99'
                        pag_val_raw = item_p.get('pagamento')
                        if pag_val_raw:
                            if hasattr(pag_val_raw, 'value'):
                                t_p = pag_val_raw.value
                            elif isinstance(pag_val_raw, str):
                                if pag_val_raw.isdigit():
                                    t_p = pag_val_raw
                                else:
                                    try:
                                        t_p = FiscalPagamentoEnum(pag_val_raw).value
                                    except Exception:
                                        t_p = '99'

                        v_p = safe_decimal(item_p.get('valor'))
                        ind_p = 1 if t_p in ['03', '05', '14', '15'] else 0
                        desc_p = (item_p.get('pagamento_descricao') or "Outros") if t_p == '99' else ""

                        nota_fiscal.adicionar_pagamento(
                            t_pag=t_p,
                            v_pag=v_p,
                            ind_pag=ind_p,
                            x_pag=desc_p[:60].strip() if t_p == '99' else ""
                        )
                else:
                    # Ajuste: Usa o totalizador da nota (vNF) calculado pela lib para bater centavos (inclui IPI, ST, Frete etc)
                    valor_pagamento = nota_fiscal.totais_icms_total_nota

                    if t_pag == '90' or not valor_pagamento:
                        valor_pagamento = Decimal('0.00000001')

                    # Pega a descrição (se for 99 Outros)
                    desc_pagamento = pedido.pagamento_descricao or "Outros" if t_pag == '99' else ""

                    nota_fiscal.adicionar_pagamento(
                        t_pag=t_pag,
                        v_pag=valor_pagamento,
                        ind_pag=ind_pag,
                        x_pag=desc_pagamento[:60].strip() if t_pag == '99' else ""
                    )
            else:
                # Devolução (Fin=4): A lib gera o XML <pag> sozinha e corretamente.
                # Apenas para garantir que o objeto Python tenha o dado em memória (opcional),
                # podemos adicionar, mas sabendo que o serializador vai ignorar esta lista e usar o hardcoded.
                nota_fiscal.adicionar_pagamento(
                    t_pag='90',
                    v_pag=Decimal('0.00'),
                    ind_pag=0
                )

            # Define o total aproximado de tributos na nota (ICMSTot)
            nota_fiscal.valor_tot_trib = total_tributos_aprox

            # ==============================================================================
            # CORREÇÃO ERRO 799: Preencher Totais DIFAL no Objeto PyNFE
            # ==============================================================================
            if difal_data_injection:
                print("DEBUG: Atualizando objeto nota_fiscal com totais do DIFAL...")
                
                # Soma os valores calculados no loop dos itens
                tot_vFCPUFDest = sum(d['vFCPUFDest'] for d in difal_data_injection.values())
                tot_vICMSUFDest = sum(d['vICMSUFDest'] for d in difal_data_injection.values())
                tot_vICMSUFRemet = sum(d['vICMSUFRemet'] for d in difal_data_injection.values())

                # Atribui diretamente aos campos da classe NotaFiscal (pynfe/entidades/notafiscal.py)
                # Assim a serialização nativa gera as tags <vICMSUFDest> etc. na ordem correta.
                nota_fiscal.totais_fcp_destino = tot_vFCPUFDest
                nota_fiscal.totais_icms_inter_destino = tot_vICMSUFDest
                nota_fiscal.totais_icms_inter_remetente = tot_vICMSUFRemet
                
                print(f"DEBUG: Totais definidos no objeto -> Dest: {tot_vICMSUFDest} | FCP: {tot_vFCPUFDest}")

                # Injeta texto legal do DIFAL nas informações complementares (rodapé)
                difal_parts = []
                tot_vBCUFDest = sum(d['vBCUFDest'] for d in difal_data_injection.values())
                
                if tot_vBCUFDest > 0:
                    difal_parts.append(f"Base de Calculo: R$ {f'{tot_vBCUFDest:.2f}'.replace('.', ',')}")
                if tot_vICMSUFDest > 0:
                    difal_parts.append(f"DIFAL UF Destino: R$ {f'{tot_vICMSUFDest:.2f}'.replace('.', ',')}")
                if tot_vFCPUFDest > 0:
                    difal_parts.append(f"FCP: R$ {f'{tot_vFCPUFDest:.2f}'.replace('.', ',')}")
                if tot_vICMSUFRemet > 0:
                    difal_parts.append(f"DIFAL UF Origem: R$ {f'{tot_vICMSUFRemet:.2f}'.replace('.', ',')}")
                
                if difal_parts:
                    difal_text = "ICMS DIFAL a nao contribuinte consumidor final, disposto na EC 87/2015. " + " | ".join(difal_parts) + "."
                    difal_text += " Procedimento autorizado pelo Regime Especial n 8.092/2024."
                    
                    difal_text = self._limpar_texto(difal_text)
                    
                    current_inf = getattr(nota_fiscal, 'informacoes_complementares_interesse_contribuinte', '') or getattr(nota_fiscal, 'informacoes_complementares', '') or ""
                    if current_inf:
                        # Previne duplicação caso essa função seja rodada de novo
                        if "EC 87/2015" not in current_inf:
                            texto_final = current_inf.strip() + " - " + difal_text
                        else:
                            texto_final = current_inf
                    else:
                        texto_final = difal_text

                    nota_fiscal.informacoes_complementares_interesse_contribuinte = texto_final
                    nota_fiscal.informacoes_complementares = texto_final

            # --- RESPONSÁVEL TÉCNICO (Obrigatório no PR) ---
            # Dados carregados do .env via settings
            
            # Seleção de CSRT por ambiente
            if ambiente_homologacao:
                id_csrt_atual = getattr(settings, "RESP_TECNICO_ID_CSRT_HOMOLOGACAO", None)
                csrt_atual = getattr(settings, "RESP_TECNICO_CSRT_HOMOLOGACAO", None)
            else:
                id_csrt_atual = getattr(settings, "RESP_TECNICO_ID_CSRT_PRODUCAO", None)
                csrt_atual = getattr(settings, "RESP_TECNICO_CSRT_PRODUCAO", None)
            
            # Fallback para variáveis antigas
            if not id_csrt_atual:
                id_csrt_atual = getattr(settings, "RESP_TECNICO_ID_CSRT", None)
            if not csrt_atual:
                csrt_atual = getattr(settings, "RESP_TECNICO_CSRT", None)

            if settings.RESP_TECNICO_CNPJ:
                nota_fiscal.adicionar_responsavel_tecnico(
                    cnpj=settings.RESP_TECNICO_CNPJ,
                    contato=settings.RESP_TECNICO_CONTATO,
                    email=settings.RESP_TECNICO_EMAIL,
                    fone=settings.RESP_TECNICO_FONE,
                    csrt=csrt_atual
                )

            # --- SERIALIZAÇÃO E ASSINATURA ---
            serializador = SerializacaoXML(_fonte_dados, homologacao=ambiente_homologacao)
            nfe_xml_obj = serializador.exportar()

            # 1. Garante que temos um objeto lxml (root)
            if isinstance(nfe_xml_obj, str):
                root = etree.fromstring(nfe_xml_obj.encode('utf-8'))
            elif isinstance(nfe_xml_obj, bytes):
                root = etree.fromstring(nfe_xml_obj)
            else:
                root = nfe_xml_obj

            # ==============================================================================
            # FIX: INJEÇÃO MANUAL DO vTotTrib (Regra 685)
            # O PyNFE 0.6.0 pode não serializar este campo automaticamente no <total>
            # ==============================================================================
            try:
                ns_nfe = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                icms_tot = root.xpath('//ns:infNFe/ns:total/ns:ICMSTot', namespaces=ns_nfe)
                
                if icms_tot:
                    node_tot = icms_tot[0]
                    # Verifica se a tag já existe
                    if node_tot.find('ns:vTotTrib', namespaces=ns_nfe) is None:
                        # Cria a tag vTotTrib com o namespace correto
                        # Importante: vTotTrib é o ÚLTIMO elemento de ICMSTot, então append funciona bem
                        v_tot_trib_elem = etree.SubElement(node_tot, f'{{http://www.portalfiscal.inf.br/nfe}}vTotTrib')
                        v_tot_trib_elem.text = f"{total_tributos_aprox:.2f}"
                        print(f"DEBUG: vTotTrib injetado manualmente no cabeçalho: {v_tot_trib_elem.text}")
            except Exception as e:
                print(f"Erro ao injetar vTotTrib: {e}")

            # ==============================================================================
            # INJEÇÃO 2: DIFAL (NOVA LÓGICA)
            # ==============================================================================
            if difal_data_injection:
                print(f"DEBUG: Chamando injetor para {len(difal_data_injection)} itens...")
                self._inject_difal(root, difal_data_injection)
            else:
                print("DEBUG: Nenhum dado de DIFAL para injetar.")

            if icms51_data_injection:
                print(f"DEBUG: Chamando injetor ICMS51 para {len(icms51_data_injection)} itens...")
                self._inject_icms51(root, icms51_data_injection)

            # [NOVO] INJEÇÃO DA REFORMA TRIBUTÁRIA
            if ibscbs_data_injection:
                self._inject_ibscbs(
                    root, 
                    ibscbs_data_injection, 
                    totais_ibscbs, 
                    self._limpar_formatacao(self.empresa.cidade_ibge)
                )

            # ==============================================================================
            # 1. INJEÇÃO DO vTotTrib (FIX CRÍTICO 685)
            # MOVIDO PARA ANTES DA SANITIZAÇÃO
            # ==============================================================================
            try:
                # Formata o valor corretamente (2 casas decimais, ponto como separador)
                v_tot_trib_str = "{:.2f}".format(total_tributos_aprox)
                
                ns_nfe = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                
                # Procura o nó ICMSTot dentro de total
                icms_tot_nodes = root.xpath('//ns:total/ns:ICMSTot', namespaces=ns_nfe)
                
                # Fallback sem namespace se não encontrar
                if not icms_tot_nodes:
                     icms_tot_nodes = root.xpath('//*[local-name()="total"]/*[local-name()="ICMSTot"]')

                if icms_tot_nodes:
                    node_tot = icms_tot_nodes[0]
                    
                    # Verifica se a tag JÁ existe para não duplicar (verificando local-name para segurança)
                    exists = False
                    for child in node_tot:
                        if etree.QName(child).localname == 'vTotTrib':
                            exists = True
                            break
                            
                    if not exists:
                        # Cria o elemento com o namespace correto explícito
                        v_tot_trib_elem = etree.Element(f'{{http://www.portalfiscal.inf.br/nfe}}vTotTrib')
                        v_tot_trib_elem.text = v_tot_trib_str
                        
                        # Adiciona ao final de ICMSTot
                        node_tot.append(v_tot_trib_elem)
                        print("DEBUG: SUCESSO - vTotTrib injetado no XML (Pré-Sanitização)!")
                    else:
                        print("DEBUG: vTotTrib já existia no XML.")
                else:
                    print("DEBUG: ERRO - Nó ICMSTot não encontrado no XML.")
                    
            except Exception as e:
                print(f"DEBUG: ERRO ao injetar vTotTrib: {str(e)}")

            # ==============================================================================
            # 3. LÓGICA CSRT (Apenas cálculo e inserção, SEM sanitização ainda)
            # ==============================================================================
            if csrt_atual and id_csrt_atual:
                try:
                    from lxml.etree import QName
                    ns_uri = 'http://www.portalfiscal.inf.br/nfe'
                    inf_nfe = None

                    # Busca robusta pelo elemento infNFe
                    if root.get('Id') and root.get('Id').startswith('NFe'):
                        inf_nfe = root
                    else:
                        for element in root.iter():
                            if element.get('Id') and element.get('Id').startswith('NFe'):
                                inf_nfe = element
                                break

                    if inf_nfe is not None:
                        inf_resp_tec = None
                        for child in inf_nfe:
                            if QName(child).localname == 'infRespTec':
                                inf_resp_tec = child
                                break
                        
                        if inf_resp_tec is not None:
                            has_csrt = False
                            for child in inf_resp_tec:
                                if QName(child).localname == 'idCSRT':
                                    has_csrt = True
                                    break
                            
                            if not has_csrt:
                                # Calcula Hash
                                chave_id = inf_nfe.get('Id')
                                chave_acesso = chave_id.replace('NFe', '')
                                
                                csrt_value = csrt_atual
                                concat_str = csrt_value + chave_acesso
                                hash_bytes = hashlib.sha1(concat_str.encode('utf-8')).digest()
                                hash_csrt = base64.b64encode(hash_bytes).decode('utf-8')
                                
                                # Insere os elementos
                                id_elem = etree.SubElement(inf_resp_tec, f'{{{ns_uri}}}idCSRT')
                                id_elem.text = id_csrt_atual
                                
                                hash_elem = etree.SubElement(inf_resp_tec, f'{{{ns_uri}}}hashCSRT')
                                hash_elem.text = hash_csrt
                                print(f"DEBUG: CSRT calculado e injetado.")
                except Exception as e:
                    print(f"Erro Crítico ao injetar CSRT: {e}")

            # ==============================================================================
            # 4. SANITIZAÇÃO FINAL (VIA RECONSTRUÇÃO RECURSIVA - CORREÇÃO DEFINITIVA)
            # Abandona XSLT/Regex e reconstrói a árvore limpa nó a nó.
            # Corrige erros: 298 (Assinatura) e "Attribute xmlns redefined"
            # ==============================================================================
            try:
                def clean_recursive(node):
                    # 1. Define o Namespace Oficial da NFe
                    ns_uri = "http://www.portalfiscal.inf.br/nfe"
                    
                    # 2. Extrai apenas o nome da tag (remove prefixos ns0:, ns1: ou namespaces errados)
                    local_name = etree.QName(node).localname
                    
                    # 3. Cria novo elemento limpo com o namespace correto
                    # nsmap={None: ...} força que não haja prefixo (ex: <infNFe> e não <ns0:infNFe>)
                    new_node = etree.Element(f"{{{ns_uri}}}{local_name}", nsmap={None: ns_uri})
                    
                    # 4. Copia Atributos Reais
                    for key, value in node.attrib.items():
                        # Proteção: Não copia se o atributo for definição de namespace explícita
                        if 'xmlns' not in key:
                            new_node.set(key, value)
                    
                    # 5. Copia Conteúdo (Texto e "Cauda")
                    new_node.text = node.text
                    new_node.tail = node.tail
                    
                    # 6. Recursão para os filhos
                    for child in node:
                        new_node.append(clean_recursive(child))
                        
                    return new_node

                # Executa a limpeza reconstruindo a árvore a partir da raiz
                root = clean_recursive(root)
                
                # debug visual opcional
                # print(etree.tostring(root, pretty_print=True).decode())

                print("DEBUG: XML Sanitizado via Reconstrução Recursiva com sucesso.")

            except Exception as e:
                print(f"ERRO FATAL na sanitização Recursiva: {e}")
                import traceback
                traceback.print_exc()
                # Mantemos o objeto 'root' original para tentar enviar, mas avisamos no log.

            # ==============================================================================
            # 5. ASSINATURA E ENVIO (V4 - CORREÇÃO DE TIPO PYNFE)
            # Limpa os bytes e reconverte para Elemento para satisfazer a lib pynfe
            # ==============================================================================
            
            # 1. Configura e Assina (usando o root limpo da etapa anterior)
            assinador = AssinaturaA1(cert_path, senha_cert)
            xml_assinado_element = assinador.assinar(root)

            # 2. Serialização para Bytes (Para limpeza cirúrgica) - REMOVIDO PARA EVITAR ERRO 298
            # A limpeza via regex quebra a assinatura digital.
            
            root_enviar = xml_assinado_element

            # 5. Envio SEFAZ
            con = ComunicacaoSefaz(uf_empresa, cert_path, senha_cert, homologacao=ambiente_homologacao)
            
            print(f"DEBUG: Enviando XML para SEFAZ (Objeto assinado)...")
            
            # Agora passamos 'root_enviar' que é do tipo _Element
            envio = con.autorizacao(modelo='nfe', nota_fiscal=root_enviar)
            
            # Compatibilidade com código posterior
            xml_assinado = etree.tostring(root_enviar, encoding='unicode', xml_declaration=False)

            # --- PROCESSAMENTO DO RETORNO ---
            if envio[0] == 0:
                # Sucesso na comunicação
                xml_resp = envio[1]
                
                ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                
                # Tenta pegar cStat
                cStat_list = xml_resp.xpath('//ns:cStat', namespaces=ns)
                cStat = cStat_list[0].text if cStat_list else ''
                
                xMotivo_list = xml_resp.xpath('//ns:xMotivo', namespaces=ns)
                xMotivo = xMotivo_list[0].text if xMotivo_list else ''
                
                # 100 = Autorizado
                if cStat == '100':
                    chNFe_list = xml_resp.xpath('//ns:chNFe', namespaces=ns)
                    chNFe = chNFe_list[0].text if chNFe_list else ''
                    
                    nProt_list = xml_resp.xpath('//ns:nProt', namespaces=ns)
                    nProt = nProt_list[0].text if nProt_list else ''
                    
                    dhRecbto_list = xml_resp.xpath('//ns:dhRecbto', namespaces=ns)
                    dhRecbto = dhRecbto_list[0].text if dhRecbto_list else datetime.now(TZ_BR).isoformat()

                    # Gera o PDF da DANFE
                    pdf_b64 = self._gerar_danfe(xml_assinado, nProt, dhRecbto, chNFe)
                    
                    # --- MONTAGEM DO XML DE DISTRIBUIÇÃO (nfeProc) ---
                    # O Mercado Livre e outros marketplaces exigem o XML completo (NFe + Protocolo)
                    ns_nfe = "http://www.portalfiscal.inf.br/nfe"
                    nfe_proc = etree.Element(f"{{{ns_nfe}}}nfeProc", versao="4.00", nsmap={None: ns_nfe})
                    
                    # Adiciona a NFe assinada
                    nfe_proc.append(etree.fromstring(xml_assinado.encode('utf-8')))
                    
                    # Adiciona o Protocolo (extraído da resposta da SEFAZ)
                    prot_nfe = xml_resp.xpath('//ns:protNFe', namespaces=ns)
                    if prot_nfe:
                        nfe_proc.append(prot_nfe[0])
                    else:
                        # Fallback caso o namespace ou estrutura varie
                        prot_nfe_fallback = xml_resp.xpath('//*[local-name()="protNFe"]')
                        if prot_nfe_fallback:
                            nfe_proc.append(prot_nfe_fallback[0])

                    xml_str = etree.tostring(nfe_proc, encoding="unicode")

                    # Atualiza Pedido
                    pedido.chave_acesso = chNFe
                    pedido.protocolo_autorizacao = nProt
                    pedido.status_sefaz = f"{cStat} - {xMotivo}"
                    pedido.xml_autorizado = xml_str
                    pedido.data_nf = datetime.now(TZ_BR).date() # Preenche a data da NF
                    pedido.pdf_danfe = pdf_b64
                    pedido.numero_nf = str(numero_nf)
                    
                    # Atualiza Sequencial da Empresa (Apenas se não for desenvolvimento)
                    is_development = os.getenv("ENVIRONMENT", "development") == "development"
                    if not is_development:
                        proximo_numero = self.empresa.nfe_numero_sequencial + 1
                        logger.info(f"[NFe] Sucesso SEFAZ. Incrementando sequencial da empresa {self.empresa.razao}: {self.empresa.nfe_numero_sequencial} -> {proximo_numero}")
                        self.empresa.nfe_numero_sequencial = proximo_numero
                    
                    # --- EXECUTA INTEGRAÇÕES ---
                    meli_res, intelipost_res, email_res = self._executar_integracoes_faturamento(
                        pedido, xml_str, pdf_b64
                    )

                    # Verifica se todas as integrações ativas passaram
                    all_ok = (meli_res is None or meli_res.get("success")) and \
                             (intelipost_res is None or intelipost_res.get("success")) and \
                             (email_res is None or email_res.get("success"))
                    
                    situation_changed = False
                    if all_ok:
                        pedido.situacao = PedidoSituacaoEnum.expedicao
                        situation_changed = True
                        
                    self.db.commit()

                    return {
                        "success": True,
                        "situation_changed": situation_changed,
                        "nfe": {"success": True, "message": f"Nota Autorizada! Protocolo: {nProt}", "chave": chNFe},
                        "meli": meli_res,
                        "intelipost": intelipost_res,
                        "email": email_res,
                        "xml": xml_str,
                        "pdf": pdf_b64
                    }
                elif cStat == '539':
                    # CASO 2: DUPLICIDADE
                    # A numeração já existe na SEFAZ com outra chave.
                    
                    erro_detalhado = (
                        f"Duplicidade de NF-e: A numeração {numero_nf} já foi utilizada na SEFAZ "
                        f"com outra chave de acesso."
                    )
                    
                    pedido.status_sefaz = f"{cStat} - {xMotivo}"
                    self.db.commit()
                    
                    raise HTTPException(status_code=409, detail=erro_detalhado)
                
                else:
                    # Rejeição
                    pedido.status_sefaz = f"{cStat} - {xMotivo}"
                    self.db.commit()
                    raise HTTPException(status_code=400, detail=f"{cStat} - {xMotivo}")

            else:
                # Erro de comunicação ou validação local
                # Tenta extrair cStat e xMotivo mesmo em caso de erro (ex: 656 - Consumo Indevido)
                response_data = envio[1]
                cStat_err = ''
                xMotivo_err = ''
                
                try:
                    # Se for objeto lxml
                    if hasattr(response_data, 'xpath'):
                        xml_err = response_data
                    # Se for string/bytes/outro
                    else:
                        if hasattr(response_data, 'text'):
                            raw_str = response_data.text
                        elif hasattr(response_data, 'content'):
                            raw_str = response_data.content.decode('utf-8', errors='ignore')
                        else:
                            raw_str = str(response_data)

                        # Remove declaração de encoding se houver para evitar erro de parse
                        if '<?xml' in raw_str:
                            raw_str = raw_str.split('?>')[-1]
                        xml_err = etree.fromstring(raw_str.encode('utf-8'))

                    if xml_err is not None:
                        cStat_nodes = xml_err.xpath('//*[local-name()="cStat"]')
                        if cStat_nodes:
                            cStat_err = cStat_nodes[0].text
                        
                        xMotivo_nodes = xml_err.xpath('//*[local-name()="xMotivo"]')
                        if xMotivo_nodes:
                            xMotivo_err = xMotivo_nodes[0].text
                except Exception as e:
                    print(f"Erro ao parsear resposta de erro SEFAZ: {e}")

                # === ADICIONE A CHAMADA AQUI ===
                # Se o erro indicar falha de Schema (215, 225, ou mensagem SAX)
                if 'SAXParseException' in xMotivo_err or 'Schema' in xMotivo_err or cStat_err == '225':
                    # Passamos o XML assinado que tentamos enviar e a mensagem de erro
                    debug_xml_erro_schema(xml_assinado, xMotivo_err)
                # ===============================

                if cStat_err:
                    pedido.status_sefaz = f"{cStat_err} - {xMotivo_err}"
                    self.db.commit()

                    if cStat_err == '232':
                        msg_detalhada = (
                            "Erro 232: IE do destinatário não informada. A SEFAZ identificou que o destinatário "
                            "é Contribuinte do ICMS. Por favor, edite o cadastro do cliente, informe a Inscrição Estadual (IE) "
                            "e ajuste o Indicador IE para 'Contribuinte ICMS'."
                        )
                        raise HTTPException(status_code=400, detail=msg_detalhada)

                    # 656 = Consumo Indevido (Too Many Requests)
                    status_code = 429 if cStat_err == '656' else 400
                    raise HTTPException(status_code=status_code, detail=f"{cStat_err} - {xMotivo_err}")

                erro_msg = response_data.text if hasattr(response_data, 'text') else str(response_data)
                raise HTTPException(status_code=500, detail=f"Erro na comunicação SEFAZ: {erro_msg}")

        except Exception as e:
            # Logar erro real
            print(f"Erro NFe: {e}")
            import traceback
            traceback.print_exc()
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Erro ao emitir NFe: {str(e)}")
        
        finally:
            # Remove arquivo temporário do certificado
            if os.path.exists(cert_path):
                try:
                    os.remove(cert_path)
                except:
                    pass

    def cancelar_nfe(self, pedido_id: int, justificativa: str):
        """
        Realiza o cancelamento de uma NFe autorizada.
        """
        # 1. Busca Dados do Pedido
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.id_sequencial == pedido_id
        ).first()

        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        
        if not pedido.chave_acesso or not pedido.protocolo_autorizacao:
            raise HTTPException(status_code=400, detail="Pedido não possui NFe autorizada para cancelar.")

        # 2. Configurações
        cert_path = self._get_certificado_path()
        senha_cert = self.empresa.certificado_senha
        uf_empresa = self.empresa.estado.value if hasattr(self.empresa.estado, 'value') else self.empresa.estado
        uf_empresa = uf_empresa.upper()
        ambiente_homologacao = (self.empresa.ambiente_sefaz.value == 2)

        try:
            # --- CORREÇÃO DE FUSO HORÁRIO ---
            # FIX: Usar UTC direto. O problema anterior era que datetime.now(br_tz) gerava 11:46-03:00.
            # O serializador do evento estava ignorando o -03:00 e gerando 11:46+00:00 (UTC), o que é 3h no passado.
            # Usando UTC direto (14:46+00:00), o horário absoluto fica correto.
            dh_evento = datetime.now(timezone.utc)

            # 3. Cria Evento de Cancelamento
            evento = EventoCancelarNota(
                cnpj=self._limpar_formatacao(self.empresa.cnpj),
                chave=pedido.chave_acesso,
                data_emissao=dh_evento, # Passamos a data com timezone aware
                uf=uf_empresa,
                protocolo=pedido.protocolo_autorizacao,
                justificativa=justificativa
            )

            # 4. Serialização e Assinatura
            serializador = SerializacaoXML(_fonte_dados, homologacao=ambiente_homologacao)
            xml_evento = serializador.serializar_evento(evento)
            
            assinador = AssinaturaA1(cert_path, senha_cert)
            xml_assinado = assinador.assinar(xml_evento)

            # 5. Envio para SEFAZ
            con = ComunicacaoSefaz(uf_empresa, cert_path, senha_cert, homologacao=ambiente_homologacao)
            envio = con.evento(modelo='nfe', evento=xml_assinado)

            # 6. Processamento do Retorno
            xml_resp = None

            # Verifica se retornou a Tupla padrão do PyNFE (status, xml)
            if isinstance(envio, tuple):
                if envio[0] == 0:
                    xml_resp = envio[1]
                else:
                    # Se retornou erro na tupla, geralmente o segundo item é o erro
                    raise HTTPException(status_code=500, detail=f"Erro na comunicação: {envio}")

            # Verifica se retornou um objeto Response direto (O caso do seu erro)
            elif hasattr(envio, 'status_code'):
                if envio.status_code == 200:
                    # Precisamos fazer o parse manual do XML retornado
                    try:
                        # envio.content contém os bytes do XML
                        xml_resp = etree.fromstring(envio.content)
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=f"Erro ao ler XML de retorno: {str(e)}")
                else:
                    raise HTTPException(status_code=envio.status_code, detail=f"Erro HTTP SEFAZ: {envio.status_code}")
            
            else:
                raise HTTPException(status_code=500, detail="Formato de retorno desconhecido da SEFAZ.")

            # Se temos um XML de resposta válido, prosseguimos com a leitura
            if xml_resp is not None:
                ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                
                try:
                    # 1. Busca o status do LOTE (Nível Superior)
                    # Tenta com namespace
                    cStat_nodes = xml_resp.xpath('//ns:cStat', namespaces=ns)
                    xMotivo_nodes = xml_resp.xpath('//ns:xMotivo', namespaces=ns)
                    
                    # Fallback sem namespace
                    if not cStat_nodes:
                        cStat_nodes = xml_resp.xpath('//*[local-name()="cStat"]')
                        xMotivo_nodes = xml_resp.xpath('//*[local-name()="xMotivo"]')

                    cStat = cStat_nodes[0].text if cStat_nodes else ''
                    xMotivo = xMotivo_nodes[0].text if xMotivo_nodes else 'Sem motivo'

                    # 2. LOGICA DE CORREÇÃO: Se for 128 (Lote Processado), precisamos mergulhar no <retEvento>
                    if cStat == '128':
                        # Busca especificamente dentro de retEvento -> infEvento
                        # Nota: infEvento tem o Id, cStat, xMotivo do processamento real
                        cStat_evt_nodes = xml_resp.xpath('//ns:retEvento/ns:infEvento/ns:cStat', namespaces=ns)
                        xMot_evt_nodes = xml_resp.xpath('//ns:retEvento/ns:infEvento/ns:xMotivo', namespaces=ns)

                        if not cStat_evt_nodes:
                             # Fallback sem namespace
                             cStat_evt_nodes = xml_resp.xpath('//*[local-name()="retEvento"]/*[local-name()="infEvento"]/*[local-name()="cStat"]')
                             xMot_evt_nodes = xml_resp.xpath('//*[local-name()="retEvento"]/*[local-name()="infEvento"]/*[local-name()="xMotivo"]')

                        if cStat_evt_nodes:
                            cStat = cStat_evt_nodes[0].text
                            xMotivo = xMot_evt_nodes[0].text
                            print(f"DEBUG: Status atualizado para o do Evento: {cStat} - {xMotivo}")

                    # --- DEBUG FINAL ---
                    print(f"DEBUG SEFAZ FINAL: cStat={cStat} | xMotivo={xMotivo}")
                    # -------------------

                    # 135 = Evento registrado e vinculado a NF-e (Cancelamento Homologado)
                    # 155 = Cancelamento homologado fora de prazo
                    if cStat in ['135', '155']:
                        pedido.situacao = PedidoSituacaoEnum.faturamento
                        pedido.status_sefaz = f"CANCELADA: {cStat} - {xMotivo}"
                        self.db.commit()
                        return {"success": True, "message": f"NFe Cancelada com Sucesso! ({cStat})"}
                    else:
                        # Se for outro erro (ex: 420 - Já cancelada, 220 - Prazo, etc)
                        raise HTTPException(status_code=400, detail=f"{cStat} - {xMotivo}")
                
                except IndexError:
                    xml_str = etree.tostring(xml_resp, encoding='unicode')
                    raise HTTPException(status_code=500, detail=f"Erro de leitura do XML: {xml_str}")

            else:
                raise HTTPException(status_code=500, detail="Erro desconhecido: Sem XML de resposta.")

        finally:
            if os.path.exists(cert_path):
                try: os.remove(cert_path)
                except: pass

    def corrigir_nfe(self, pedido_id: int, texto_correcao: str):
        """
        Emite uma Carta de Correção Eletrônica (CC-e) para uma NFe autorizada.
        """
        # 1. Busca Dados do Pedido
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.id_sequencial == pedido_id
        ).first()

        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        
        if not pedido.chave_acesso:
            raise HTTPException(status_code=400, detail="Pedido não possui NFe autorizada para corrigir.")

        # 2. Configurações
        cert_path = self._get_certificado_path()
        senha_cert = self.empresa.certificado_senha
        uf_empresa = self.empresa.estado.value if hasattr(self.empresa.estado, 'value') else self.empresa.estado
        uf_empresa = uf_empresa.upper()
        ambiente_homologacao = (self.empresa.ambiente_sefaz.value == 2)

        try:
            n_seq = 1
            while n_seq <= 20:
                # 3. Cria Evento de Carta de Correção
                # Nota: n_seq_evento agora dinâmico para tratar duplicidade (Rejeição 631)
                evento = EventoCartaCorrecao(
                    cnpj=self._limpar_formatacao(self.empresa.cnpj),
                    chave=pedido.chave_acesso,
                    data_emissao=datetime.now(timezone.utc),
                    uf=uf_empresa,
                    n_seq_evento=n_seq, 
                    correcao=texto_correcao
                )

                # 4. Serialização e Assinatura
                serializador = SerializacaoXML(_fonte_dados, homologacao=ambiente_homologacao)
                xml_evento = serializador.serializar_evento(evento)
                
                assinador = AssinaturaA1(cert_path, senha_cert)
                xml_assinado = assinador.assinar(xml_evento)

                # 5. Envio para SEFAZ
                con = ComunicacaoSefaz(uf_empresa, cert_path, senha_cert, homologacao=ambiente_homologacao)
                envio = con.evento(modelo='nfe', evento=xml_assinado)

                # 6. Processamento do Retorno (Lógica similar ao cancelamento)
                xml_resp = None

                if isinstance(envio, tuple):
                    if envio[0] == 0:
                        xml_resp = envio[1]
                    else:
                        raise HTTPException(status_code=500, detail=f"Erro na comunicação: {envio}")
                elif hasattr(envio, 'status_code'):
                    if envio.status_code == 200:
                        try:
                            xml_resp = etree.fromstring(envio.content)
                        except Exception as e:
                            raise HTTPException(status_code=500, detail=f"Erro ao ler XML de retorno: {str(e)}")
                    else:
                        raise HTTPException(status_code=envio.status_code, detail=f"Erro HTTP SEFAZ: {envio.status_code}")
                else:
                    raise HTTPException(status_code=500, detail="Formato de retorno desconhecido da SEFAZ.")

                if xml_resp is not None:
                    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                    try:
                        # Busca cStat e xMotivo (com fallback para sem namespace)
                        cStat_nodes = xml_resp.xpath('//ns:retEvento/ns:infEvento/ns:cStat', namespaces=ns)
                        xMot_nodes = xml_resp.xpath('//ns:retEvento/ns:infEvento/ns:xMotivo', namespaces=ns)
                        
                        if not cStat_nodes:
                            cStat_nodes = xml_resp.xpath('//*[local-name()="cStat"]')
                            xMot_nodes = xml_resp.xpath('//*[local-name()="xMotivo"]')

                        cStat = cStat_nodes[0].text if cStat_nodes else ''
                        xMotivo = xMot_nodes[0].text if xMot_nodes else 'Sem motivo'

                        # TRATAMENTO DE DUPLICIDADE (631): Incrementa e tenta novamente
                        if cStat == '631':
                            logger.warning(f"CC-e seq {n_seq} já existe para a chave {pedido.chave_acesso}. Tentando seq {n_seq + 1}...")
                            n_seq += 1
                            continue

                        # 135 = Evento registrado e vinculado a NF-e
                        if cStat == '135':
                            # Tenta extrair nProt e dhRegEvento do retorno para a CCe
                            nProt_nodes = xml_resp.xpath('//ns:retEvento/ns:infEvento/ns:nProt', namespaces=ns)
                            dhReg_nodes = xml_resp.xpath('//ns:retEvento/ns:infEvento/ns:dhRegEvento', namespaces=ns)
                            
                            # Fallbacks sem namespace
                            if not nProt_nodes:
                                nProt_nodes = xml_resp.xpath('//*[local-name()="nProt"]')
                                dhReg_nodes = xml_resp.xpath('//*[local-name()="dhRegEvento"]')

                            nProt_cce = nProt_nodes[0].text if nProt_nodes else 'N/A'
                            dhReg_cce = dhReg_nodes[0].text if dhReg_nodes else datetime.now(TZ_BR).isoformat()
                            
                            cnpj_cpf = self._limpar_formatacao(self.empresa.cnpj)

                            # GERA O PDF
                            pdf_cce_b64 = self._gerar_pdf_cce(
                                chave_acesso=pedido.chave_acesso,
                                cnpj_cpf=cnpj_cpf,
                                protocolo=nProt_cce,
                                data_evento=dhReg_cce,
                                uf=uf_empresa,
                                texto_correcao=texto_correcao
                            )

                            # Atualiza status SEFAZ no pedido para refletir a correção
                            pedido.status_sefaz = f"CC-e Registrada: {xMotivo}"
                            pedido.pdf_cce = pdf_cce_b64
                            self.db.commit()
                            
                            return {
                                "success": True, 
                                "message": f"Carta de Correção Registrada! ({cStat})",
                                "pdf": pdf_cce_b64 # Retorna o PDF para o Frontend
                            }
                        else:
                            raise HTTPException(status_code=400, detail=f"{cStat} - {xMotivo}")
                    
                    except IndexError:
                        xml_str = etree.tostring(xml_resp, encoding='unicode')
                        raise HTTPException(status_code=500, detail=f"Erro de leitura do XML: {xml_str}")
                else:
                    raise HTTPException(status_code=500, detail="Erro desconhecido: Sem XML de resposta.")
            
            raise HTTPException(status_code=400, detail="Limite de tentativas de sequencial de CC-e atingido (20).")

        finally:
            if os.path.exists(cert_path):
                try: os.remove(cert_path)
                except: pass

    def _inject_difal(self, root, difal_data):
        """
        Injeta a tag ICMSUFDest de forma agressiva/robusta, ignorando namespaces.
        """
        try:
            print("--- INICIANDO INJEÇÃO DO DIFAL NO XML ---")
            
            # Busca todas as tags <det> independente do namespace
            dets = root.xpath('//*[local-name()="det"]')
            print(f"DEBUG: Encontrados {len(dets)} itens (det) no XML.")
            
            for det in dets:
                n_item_str = det.get('nItem')
                n_item = int(n_item_str)
                print(f"DEBUG: Processando item nItem={n_item}...")
                
                # Se temos dados de DIFAL para este item
                if n_item in difal_data:
                    dados = difal_data[n_item]
                    
                    # Busca a tag <imposto> dentro deste <det>
                    # O ponto (.) no início do xpath garante que busca apenas dentro deste nó
                    imposto_nodes = det.xpath('.//*[local-name()="imposto"]')
                    
                    if imposto_nodes:
                        imposto_node = imposto_nodes[0]
                        print(f"DEBUG: Nó <imposto> encontrado para item {n_item}. Criando tags...")

                        # Cria o grupo ICMSUFDest com o namespace correto da NFe 4.00
                        # Necessário prefixar o namespace manualmente para não herdar lixo
                        ns_map = "http://www.portalfiscal.inf.br/nfe"
                        icms_uf_dest = etree.Element(f'{{{ns_map}}}ICMSUFDest')
                        
                        # Função auxiliar para criar sub-tags formatadas
                        def add_tag(parent, tag_name, value):
                            elem = etree.SubElement(parent, f'{{{ns_map}}}{tag_name}')
                            elem.text = "{:.2f}".format(value)

                        # A ORDEM É CRÍTICA (Schema XSD)
                        add_tag(icms_uf_dest, 'vBCUFDest', dados['vBCUFDest'])
                        add_tag(icms_uf_dest, 'vBCFCPUFDest', dados['vBCFCPUFDest'])
                        add_tag(icms_uf_dest, 'pFCPUFDest', dados['pFCPUFDest'])
                        add_tag(icms_uf_dest, 'pICMSUFDest', dados['pICMSUFDest'])
                        add_tag(icms_uf_dest, 'pICMSInter', dados['pICMSInter'])
                        add_tag(icms_uf_dest, 'pICMSInterPart', dados['pICMSInterPart'])
                        add_tag(icms_uf_dest, 'vFCPUFDest', dados['vFCPUFDest'])
                        add_tag(icms_uf_dest, 'vICMSUFDest', dados['vICMSUFDest'])
                        add_tag(icms_uf_dest, 'vICMSUFRemet', dados['vICMSUFRemet'])
                        
                        imposto_node.append(icms_uf_dest)
                        print(f"DEBUG: SUCESSO! Tag <ICMSUFDest> injetada no item {n_item}.")
                    else:
                        print(f"DEBUG: ERRO CRÍTICO - Tag <imposto> não encontrada no item {n_item}.")
                else:
                    print(f"DEBUG: Item {n_item} não possui dados de DIFAL para injetar.")

        except Exception as e:
            print(f"ERRO FATAL AO INJETAR DIFAL: {e}")
            import traceback
            traceback.print_exc()

    def _inject_icms51(self, root, icms51_data):
        """
        Injeta tags faltantes no ICMS51 (vBC, pICMS, vICMSOp, pDif, vICMSDif, vICMS).
        A lib pynfe 0.6.0 não gera estas tags para o CST 51.
        """
        try:
            ns_map = "http://www.portalfiscal.inf.br/nfe"
            dets = root.xpath('//*[local-name()="det"]')
            for det in dets:
                n_item = int(det.get('nItem'))
                if n_item in icms51_data:
                    dados = icms51_data[n_item]
                    icms51_nodes = det.xpath('.//*[local-name()="ICMS51"]')
                    if icms51_nodes:
                        node = icms51_nodes[0]
                        
                        # Encontra modBC para inserir após ele (ordem do schema)
                        ref_node = None
                        for child in node:
                            if etree.QName(child).localname == 'modBC':
                                ref_node = child
                                break
                        
                        def insert_tag(tag_name, value, format_str="{:.2f}"):
                            nonlocal ref_node
                            elem = etree.Element(f'{{{ns_map}}}{tag_name}')
                            elem.text = format_str.format(value)
                            if ref_node is not None:
                                ref_node.addnext(elem)
                            else:
                                node.insert(0, elem)
                            ref_node = elem

                        insert_tag('pRedBC', dados.get('pRedBC', Decimal('0.00')))
                        insert_tag('vBC', dados['vBC'])
                        insert_tag('pICMS', dados['pICMS'])
                        insert_tag('vICMSOp', dados['vICMSOp'])
                        # CORREÇÃO AQUI: Removido o "{:.4f}". 
                        # Agora ele usará o padrão "{:.2f}", gerando "38.46" em vez de "38.4600"
                        insert_tag('pDif', dados['pDif'])
                        insert_tag('vICMSDif', dados['vICMSDif'])
                        insert_tag('vICMS', dados['vICMS'])
        except Exception as e:
            print(f"Erro ao injetar ICMS51: {e}")

    def _inject_ibscbs(self, root, ibscbs_data, totais_ibscbs, municipio_fg):
        """ Injeta a estrutura completa do IBS e CBS direto no XML final """
        try:
            ns_map = "http://www.portalfiscal.inf.br/nfe"
            
            # 1. Injetar cMunFGIBS no cabeçalho (grupo ide)
            # REGRA: cMunFGIBS só deve ser informado se indPres = 5 (Operação presencial, fora do estabelecimento)
            ind_pres_nodes = root.xpath('//*[local-name()="ide"]//*[local-name()="indPres"]')
            ind_pres_val = ind_pres_nodes[0].text if ind_pres_nodes else None
            
            if str(ind_pres_val) == '5' and municipio_fg:
                ide_nodes = root.xpath('//*[local-name()="ide"]')
                if ide_nodes:
                    ide_node = ide_nodes[0]
                    if ide_node.find(f'{{{ns_map}}}cMunFGIBS') is None:
                        cmunfg_ibs = etree.Element(f'{{{ns_map}}}cMunFGIBS')
                        cmunfg_ibs.text = str(municipio_fg)
                        ide_node.append(cmunfg_ibs)
                        
                        # Ordena os filhos de ide_node conforme a ordem do XSD
                        ordem_ide = [
                            'cUF', 'cNF', 'natOp', 'mod', 'serie', 'nNF', 'dhEmi', 'dhSaiEnt',
                            'tpNF', 'idDest', 'cMunFG', 'tpImp', 'tpEmis', 'cDV', 'tpAmb',
                            'finNFe', 'indFinal', 'indPres', 'procEmi', 'verProc', 'dhCont',
                            'xJust', 'indIntermed', 'dPrevEntrega', 'cMunFGIBS', 'tpNFDebito',
                            'tpNFCredito'
                        ]
                        
                        def get_ide_sort_key(element):
                            tag_name = etree.QName(element).localname
                            if tag_name in ordem_ide:
                                return ordem_ide.index(tag_name)
                            return len(ordem_ide)
                            
                        children = list(ide_node)
                        children.sort(key=get_ide_sort_key)
                        
                        for child in children:
                            ide_node.remove(child)
                        for child in children:
                            ide_node.append(child)
            
            # 2. Injetar IBSCBS nos itens (grupo imposto)
            dets = root.xpath('//*[local-name()="det"]')
            for det in dets:
                n_item = int(det.get('nItem'))
                if n_item in ibscbs_data:
                    dados = ibscbs_data[n_item]
                    imposto_nodes = det.xpath('.//*[local-name()="imposto"]')
                    if imposto_nodes:
                        imposto_node = imposto_nodes[0]
                        # Previne duplicação
                        if imposto_node.find(f'{{{ns_map}}}IBSCBS') is None:
                            ibscbs = etree.Element(f'{{{ns_map}}}IBSCBS')
                            etree.SubElement(ibscbs, f'{{{ns_map}}}CST').text = dados['CST']
                            etree.SubElement(ibscbs, f'{{{ns_map}}}cClassTrib').text = dados['cClassTrib']
                            
                            cst_tributados = ['000', '010', '200', '400', '510', '600', '620', '800', '810', '900']
                            if dados['CST'] in cst_tributados:
                                gIBSCBS = etree.SubElement(ibscbs, f'{{{ns_map}}}gIBSCBS')
                                etree.SubElement(gIBSCBS, f'{{{ns_map}}}vBC').text = "{:.2f}".format(dados['vBC'])
                                
                                gIBSUF = etree.SubElement(gIBSCBS, f'{{{ns_map}}}gIBSUF')
                                etree.SubElement(gIBSUF, f'{{{ns_map}}}pIBSUF').text = "{:.4f}".format(dados['pIBSUF'])
                                etree.SubElement(gIBSUF, f'{{{ns_map}}}vIBSUF').text = "{:.2f}".format(dados['vIBSUF'])
                                
                                gIBSMun = etree.SubElement(gIBSCBS, f'{{{ns_map}}}gIBSMun')
                                etree.SubElement(gIBSMun, f'{{{ns_map}}}pIBSMun').text = "{:.4f}".format(dados['pIBSMun'])
                                etree.SubElement(gIBSMun, f'{{{ns_map}}}vIBSMun').text = "{:.2f}".format(dados['vIBSMun'])
                                
                                etree.SubElement(gIBSCBS, f'{{{ns_map}}}vIBS').text = "{:.2f}".format(dados['vIBS'])
                                
                                gCBS = etree.SubElement(gIBSCBS, f'{{{ns_map}}}gCBS')
                                etree.SubElement(gCBS, f'{{{ns_map}}}pCBS').text = "{:.4f}".format(dados['pCBS'])
                                etree.SubElement(gCBS, f'{{{ns_map}}}vCBS').text = "{:.2f}".format(dados['vCBS'])
                            
                            imposto_node.append(ibscbs)
                            
                            # Ordena os filhos de imposto_node conforme a ordem do XSD
                            ordem_imposto = [
                                'vTotTrib', 'ICMS', 'ISSQN', 'IPI', 'II', 
                                'PIS', 'PISST', 'COFINS', 'COFINSST', 
                                'ICMSUFDest', 'IBSCBS'
                            ]
                            
                            def get_imposto_sort_key(element):
                                tag_name = etree.QName(element).localname
                                if tag_name in ordem_imposto:
                                    return ordem_imposto.index(tag_name)
                                return len(ordem_imposto)
                                
                            children = list(imposto_node)
                            children.sort(key=get_imposto_sort_key)
                            
                            for child in children:
                                imposto_node.remove(child)
                            for child in children:
                                imposto_node.append(child)

            # 3. Injetar Totais (IBSCBSTot no grupo total)
            has_values = any(totais_ibscbs[k] > 0 for k in ['vBCIBSCBS', 'vIBS', 'vCBS'])
            if has_values:
                total_nodes = root.xpath('//*[local-name()="total"]')
                if total_nodes:
                    total_node = total_nodes[0]
                    if total_node.find(f'{{{ns_map}}}IBSCBSTot') is None:
                        ibscbs_tot = etree.Element(f'{{{ns_map}}}IBSCBSTot')
                        etree.SubElement(ibscbs_tot, f'{{{ns_map}}}vBCIBSCBS').text = "{:.2f}".format(totais_ibscbs['vBCIBSCBS'])
                        
                        if totais_ibscbs['vIBS'] > 0 or totais_ibscbs['vIBSUF'] > 0:
                            gIBS = etree.SubElement(ibscbs_tot, f'{{{ns_map}}}gIBS')
                            
                            gIBSUF = etree.SubElement(gIBS, f'{{{ns_map}}}gIBSUF')
                            etree.SubElement(gIBSUF, f'{{{ns_map}}}vDif').text = "0.00"
                            etree.SubElement(gIBSUF, f'{{{ns_map}}}vDevTrib').text = "0.00"
                            etree.SubElement(gIBSUF, f'{{{ns_map}}}vIBSUF').text = "{:.2f}".format(totais_ibscbs['vIBSUF'])
                            
                            gIBSMun = etree.SubElement(gIBS, f'{{{ns_map}}}gIBSMun')
                            etree.SubElement(gIBSMun, f'{{{ns_map}}}vDif').text = "0.00"
                            etree.SubElement(gIBSMun, f'{{{ns_map}}}vDevTrib').text = "0.00"
                            etree.SubElement(gIBSMun, f'{{{ns_map}}}vIBSMun').text = "{:.2f}".format(totais_ibscbs['vIBSMun'])
                            
                            etree.SubElement(gIBS, f'{{{ns_map}}}vIBS').text = "{:.2f}".format(totais_ibscbs['vIBS'])
                            etree.SubElement(gIBS, f'{{{ns_map}}}vCredPres').text = "0.00"
                            etree.SubElement(gIBS, f'{{{ns_map}}}vCredPresCondSus').text = "0.00"

                        if totais_ibscbs['vCBS'] > 0:
                            gCBS = etree.SubElement(ibscbs_tot, f'{{{ns_map}}}gCBS')
                            etree.SubElement(gCBS, f'{{{ns_map}}}vDif').text = "0.00"
                            etree.SubElement(gCBS, f'{{{ns_map}}}vDevTrib').text = "0.00"
                            etree.SubElement(gCBS, f'{{{ns_map}}}vCBS').text = "{:.2f}".format(totais_ibscbs['vCBS'])
                            etree.SubElement(gCBS, f'{{{ns_map}}}vCredPres').text = "0.00"
                            etree.SubElement(gCBS, f'{{{ns_map}}}vCredPresCondSus').text = "0.00"
                        
                        total_node.append(ibscbs_tot)
                        
                        # Ordena os filhos de total_node conforme a ordem do XSD
                        ordem_total = [
                            'ICMSTot', 'ISSQNTot', 'retTrib', 'IBSCBSTot'
                        ]
                        
                        def get_total_sort_key(element):
                            tag_name = etree.QName(element).localname
                            if tag_name in ordem_total:
                                return ordem_total.index(tag_name)
                            return len(ordem_total)
                            
                        children = list(total_node)
                        children.sort(key=get_total_sort_key)
                        
                        for child in children:
                            total_node.remove(child)
                        for child in children:
                            total_node.append(child)
        except Exception as e:
            print(f"Erro ao injetar IBSCBS: {e}")

    def _executar_integracoes_faturamento(self, pedido: models.Pedido, xml_str: str, pdf_b64: str) -> Tuple[dict, dict, dict]:
        """
        Executa as integrações de faturamento (Mercado Livre, Intelipost e E-mail).
        """
        meli_res = None
        intelipost_res = None
        email_res = None

        # 1. Integração Mercado Livre
        if pedido.origem_venda == "Mercado Livre" or "Pedido ML:" in (pedido.observacao or "") or "ID:" in (pedido.observacao or ""):
            if settings.ENVIRONMENT != "production":
                meli_res = {"success": True, "message": "Simulado: XML enviado para o Mercado Livre (Ambiente de Testes)"}
                pedido.meli_xml_enviado = True
            else:
                try:
                    # IMPORTANTE: O campo "Pedido ML:" é o pack_id (nível de pacote), que é o
                    # identificador correto para o endpoint /packs/{id}/fiscal_documents do ML.
                    # O campo "ID:" é o sub-order ID individual e NÃO funciona no endpoint de fiscal_documents.
                    match_pack = re.search(r"Pedido ML:\s*(\d+)", pedido.observacao or "")
                    if match_pack:
                        order_id_ml = match_pack.group(1)
                    else:
                        # Fallback: se não tem "Pedido ML:", usa "ID:" (pedido simples sem pack)
                        match_id = re.search(r"ID:\s*(\d+)", pedido.observacao or "")
                        order_id_ml = match_id.group(1) if match_id else None

                    if order_id_ml:
                        chave_acesso = pedido.chave_acesso
                        numero_nf = pedido.numero_nf
                        
                        dh_emi_match = re.search(r"<dhEmi>([^<]+)</dhEmi>", xml_str)
                        if dh_emi_match:
                            dh_emi = dh_emi_match.group(1)
                            if "." not in dh_emi:
                                tz_match = re.search(r"([+-]\d{2}:\d{2}|Z)$", dh_emi)
                                if tz_match:
                                    tz = tz_match.group(1)
                                    base_time = dh_emi[:-len(tz)]
                                    data_emissao = f"{base_time}.000{tz}"
                                else:
                                    data_emissao = f"{dh_emi}.000"
                            else:
                                data_emissao = dh_emi
                        else:
                            if pedido.data_nf:
                                data_emissao = f"{pedido.data_nf.isoformat()}T12:00:00.000-03:00"
                            else:
                                data_emissao = datetime.now(TZ_BR).isoformat()

                        meli_service = MeliService(self.db, self.id_empresa)
                        res = asyncio.run(meli_service.upload_xml(
                            order_id_ml=order_id_ml,
                            xml_content=xml_str,
                            chave_acesso=chave_acesso,
                            numero_nf=numero_nf,
                            data_emissao=data_emissao
                        ))
                        
                        if res and isinstance(res, dict) and res.get('status') == 'warning':
                            meli_res = {"success": True, "message": f"Aviso Mercado Livre: {res.get('message')}"}
                            pedido.meli_xml_enviado = True
                        elif res and not (isinstance(res, dict) and res.get('status') == 'error'):
                            meli_res = {"success": True, "message": "XML enviado com sucesso para o Mercado Livre!"}
                            pedido.meli_xml_enviado = True
                        else:
                            error_msg = res.get('message') if isinstance(res, dict) and res.get('message') else "Erro desconhecido no upload."
                            meli_res = {"success": False, "message": f"Falha no Mercado Livre: {error_msg}"}
                    else:
                        meli_res = {"success": False, "message": "ID do pedido ML não encontrado para envio do XML."}
                except Exception as e:
                    meli_res = {"success": False, "message": f"Erro ao enviar para ML: {str(e)}"}

            # --- Transmissão de XML NFe para a Shopee ---
            if getattr(pedido, 'shopee_order_sn', None):
                try:
                    from app.core.service.shopee_service import ShopeeService
                    shopee_service = ShopeeService(self.db, self.id_empresa)
                    shopee_service.upload_xml(
                        order_sn=pedido.shopee_order_sn,
                        xml_content=xml_str,
                        chave_acesso=chave_acesso,
                        numero_nf=numero_nf
                    )
                except Exception as e:
                    import logging as _logging
                    _logging.getLogger(__name__).error(f"Erro ao transmitir XML para a Shopee no pedido #{pedido.id}: {e}")

        # 2. Integração Intelipost (Shipment Order)
        # O pedido na intelipost deve ser sempre criado se houver configuração da integração
        # mesmo se não tiver o id da cotação.
        intelipost_config = self.db.query(models.IntelipostConfiguracao).filter(
            models.IntelipostConfiguracao.id_empresa == self.id_empresa
        ).first()

        is_mercado_envios = False
        if pedido.transportadora and pedido.transportadora.nome_razao:
            nome_transp = pedido.transportadora.nome_razao.lower()
            if "mercado" in nome_transp and ("env" in nome_transp or "livre" in nome_transp):
                is_mercado_envios = True

        if intelipost_config and intelipost_config.api_key and not is_mercado_envios:
            if pedido.intelipost_criado:
                intelipost_res = {"success": True, "message": "Ordem de envio já criada na Intelipost."}
            elif settings.ENVIRONMENT != "production":
                intelipost_res = {"success": True, "message": "Simulado: Ordem de envio criada na Intelipost (Ambiente de Testes)"}
                pedido.intelipost_criado = True
            else:
                try:
                    intelipost_service = IntelipostService(self.db, self.id_empresa)
                    dados_frete = {
                        "delivery_method_id": pedido.delivery_method_id_intelipost,
                        "quote_id": pedido.quote_id,
                        "final_shipping_cost": float(pedido.valor_frete or 0),
                        "data_entrega": pedido.data_entrega.isoformat() if pedido.data_entrega else None
                    }
                    res = asyncio.run(intelipost_service.criar_pedido_envio(pedido.id_sequencial or pedido.id, dados_frete))
                    
                    if isinstance(res, dict) and res.get("status") == "warning":
                        intelipost_res = {"success": True, "message": res.get("message"), "warning": True}
                        pedido.intelipost_criado = True
                    else:
                        intelipost_res = {"success": True, "message": "Ordem de envio criada na Intelipost!"}
                        pedido.intelipost_criado = True
                        
                    # Tenta salvar o ID da ordem de envio retornado pela Intelipost
                    if isinstance(res, dict) and res.get("content"):
                        shipment_id = res["content"].get("shipment_order_id")
                        if shipment_id:
                            pedido.intelipost_id = str(shipment_id)
                except Exception as e:
                    logger.error(f"Erro ao criar envio na Intelipost: {e}")
                    # Reforço: se a exceção contiver "já existe", trata como aviso e não bloqueia a alteração de situação
                    err_str = str(e).lower()
                    if "já existe" in err_str or "already.existing.order.number" in err_str:
                        intelipost_res = {"success": True, "message": f"Aviso Intelipost: {str(e)}", "warning": True}
                        pedido.intelipost_criado = True
                    else:
                        intelipost_res = {"success": False, "message": f"Erro Intelipost: {str(e)}"}

        # 3. Integração E-mail
        try:
            if settings.ENVIRONMENT != "production":
                email_res = {"success": True, "message": "E-mail simulado com sucesso! (Ambiente de Desenvolvimento)"}
                pedido.email_enviado = True
            else:
                email_svc = ElasticEmailService(self.db, self.id_empresa)
                email_res = asyncio.run(email_svc.send_invoice_email(pedido, pdf_b64, xml_str))
                if email_res and email_res.get("success"):
                    pedido.email_enviado = True
        except Exception as e:
            logger.error(f"Erro ao enviar e-mail: {e}")
            email_res = {"success": False, "message": f"Erro envio e-mail: {str(e)}"}

        return meli_res, intelipost_res, email_res

    def gerar_danfe_manual(self, pedido_id: int, tipo: str = "completa") -> bytes:
        """
        Gera o PDF da DANFE (completa ou simplificada) a partir do XML já autorizado do pedido.
        Salva no pedido e retorna os bytes do PDF.
        """
        pedido = self.db.query(models.Pedido).filter(
            models.Pedido.id_empresa == self.id_empresa,
            models.Pedido.id_sequencial == pedido_id
        ).first()

        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
            
        if not pedido.xml_autorizado:
             raise HTTPException(status_code=400, detail="Pedido não possui XML autorizado. Emita a NFe primeiro.")

        try:
            # Parse do XML para obter dhRecbto (Data de Recebimento do Protocolo)
            root = etree.fromstring(pedido.xml_autorizado.encode('utf-8'))
            ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
            
            dhRecbto = datetime.now(TZ_BR).isoformat()
            # Tenta extrair do protocolo
            prot_nodes = root.xpath('//ns:protNFe/ns:infProt/ns:dhRecbto', namespaces=ns)
            if prot_nodes:
                dhRecbto = prot_nodes[0].text
            
            is_cancelada = False
            if pedido.situacao == PedidoSituacaoEnum.cancelado or (pedido.status_sefaz and "CANCELADA" in pedido.status_sefaz.upper()):
                is_cancelada = True

            if tipo == "simplificada":
                pdf_b64 = self._gerar_danfe_simplificada(root, pedido.protocolo_autorizacao, dhRecbto, pedido.chave_acesso, is_cancelada=is_cancelada)
            else:
                pdf_b64 = self._gerar_danfe(root, pedido.protocolo_autorizacao, dhRecbto, pedido.chave_acesso, is_cancelada=is_cancelada)
            
            if not pdf_b64:
                raise HTTPException(status_code=500, detail="Falha na geração do PDF (retorno vazio).")

            pedido.pdf_danfe = pdf_b64
            self.db.commit()
            
            return base64.b64decode(pdf_b64)

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Erro ao gerar DANFE: {str(e)}")

    def gerar_danfe_lote(self, pedido_ids: list[int], tipo: str = "completa") -> bytes:
        """
        Gera um único PDF contendo as DANFEs de todos os pedidos selecionados.
        """
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        
        buffer = io.BytesIO()
        if tipo == "simplificada":
            c = canvas.Canvas(buffer, pagesize=(100 * mm, 150 * mm))
        else:
            c = canvas.Canvas(buffer, pagesize=A4)
        
        for pid in pedido_ids:
            pedido = self.db.query(models.Pedido).filter(
                models.Pedido.id_empresa == self.id_empresa,
                models.Pedido.id_sequencial == pid
            ).first()
            
            if pedido and pedido.xml_autorizado:
                root = etree.fromstring(pedido.xml_autorizado.encode('utf-8'))
                ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                dhRecbto = pedido.protocolo_autorizacao
                prot_nodes = root.xpath('//ns:protNFe/ns:infProt/ns:dhRecbto', namespaces=ns)
                if prot_nodes:
                    dhRecbto = prot_nodes[0].text
                
                is_cancelada = False
                if pedido.situacao == PedidoSituacaoEnum.cancelado or (pedido.status_sefaz and "CANCELADA" in pedido.status_sefaz.upper()):
                    is_cancelada = True
                
                if tipo == "simplificada":
                    self._gerar_danfe_simplificada(root, pedido.protocolo_autorizacao, dhRecbto, pedido.chave_acesso, c=c, is_cancelada=is_cancelada)
                else:
                    self._gerar_danfe(root, pedido.protocolo_autorizacao, dhRecbto, pedido.chave_acesso, c=c, is_cancelada=is_cancelada)
        
        c.save()
        return buffer.getvalue()

    def emitir_nfe_lote(self, pedido_ids: list[int]):
        """
        Realiza a emissão de NFe para múltiplos pedidos em lote.
        Cada pedido terá sua regra tributária selecionada automaticamente.
        """
        resultados = []
        for pid in pedido_ids:
            try:
                # Chama a emissão individual sem passar regra_id (ativa busca automática)
                res = self.emitir_nfe(pid)
                resultados.append({
                    "id": pid,
                    "success": True,
                    "message": res.get("nfe", {}).get("message"),
                    "chave": res.get("nfe", {}).get("chave")
                })
            except HTTPException as e:
                resultados.append({
                    "id": pid,
                    "success": False,
                    "message": f"Erro {e.status_code}: {e.detail}"
                })
            except Exception as e:
                resultados.append({
                    "id": pid,
                    "success": False,
                    "message": f"Erro inesperado: {str(e)}"
                })
        return resultados

    def sincronizar_dfe(self):
        """Busca novos documentos destinados na SEFAZ via NSU."""
        agora = datetime.now(TZ_BR)
        
        # --- TRAVA DE COOLDOWN (BLOQUEIO PRÉVIO) ---
        if self.id_empresa in _cooldown_sefaz:
            tempo_liberacao = _cooldown_sefaz[self.id_empresa]
            if agora < tempo_liberacao:
                raise HTTPException(
                    status_code=429, 
                    detail=f"Em repouso obrigatório da SEFAZ. Tente novamente após {tempo_liberacao.strftime('%H:%M:%S')}."
                )
            else:
                del _cooldown_sefaz[self.id_empresa]
        
        logger.info(f"Iniciando sincronização de DF-e para empresa {self.empresa.razao} (ID: {self.id_empresa})")
        cert_path = self._get_certificado_path()
        try:
            con = ComunicacaoSefaz(self.empresa.estado.value, cert_path, self.empresa.certificado_senha, homologacao=False)
            cnpj = self._limpar_formatacao(self.empresa.cnpj)
            
            novas_notas = 0
            continua_busca = True
            lotes_processados = 0
            limite_lotes = 10 # Reduzido ligeiramente para evitar timeout, limite seguro da SEFAZ

            while continua_busca and lotes_processados < limite_lotes:
                lotes_processados += 1
                nsu_para_requisicao = self.empresa.nfe_ultimo_nsu or '0'
                logger.debug(f"Processando lote {lotes_processados}... Solicitando a partir do NSU: {nsu_para_requisicao}")

                resp = con.consulta_distribuicao(cnpj=cnpj, nsu=nsu_para_requisicao)
                if not resp.text:
                    logger.warning(f"Resposta vazia da SEFAZ no lote {lotes_processados}")
                    break
                
                root = etree.fromstring(resp.text.encode('utf-8'))
                ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
                
                c_stat_nodes = root.xpath('//ns:cStat', namespaces=ns)
                if not c_stat_nodes: # Se não encontrar cStat, algo deu muito errado
                    logger.error(f"cStat não encontrado na resposta da SEFAZ no lote {lotes_processados}")
                    break
                
                cStat = c_stat_nodes[0].text
                logger.debug(f"cStat retornado pela SEFAZ: {cStat}")
                
                # --- TRATAMENTO DOS ERROS CRÍTICOS ---
                if cStat == '656': 
                    # Coloca a empresa de castigo no cache por 1 hora
                    _cooldown_sefaz[self.id_empresa] = datetime.now(TZ_BR) + timedelta(hours=1)
                    raise HTTPException(
                        status_code=429, 
                        detail="SEFAZ bloqueou por Consumo Indevido. CNPJ em repouso por 1 hora."
                    )

                if cStat == '137': 
                    # Fim da fila: Aplicar o cooldown obrigatório de 1 hora
                    logger.info("SEFAZ informou cStat 137. Aplicando cooldown de 1 hora.")
                    _cooldown_sefaz[self.id_empresa] = datetime.now(TZ_BR) + timedelta(hours=1)
                    continua_busca = False
                    break

                if cStat not in ['138']: # 138 é Documento Localizado. Qualquer outra coisa paramos para evitar punição
                    x_motivo_nodes = root.xpath('//ns:xMotivo', namespaces=ns)
                    motivo = x_motivo_nodes[0].text if x_motivo_nodes else "Erro desconhecido"
                    logger.warning(f"Retorno inesperado da SEFAZ: cStat {cStat} - {motivo}. Abortando este lote.")
                    raise HTTPException(status_code=400, detail=f"Erro SEFAZ: {cStat} - {motivo}")

                max_nsu_sefaz = root.xpath('//ns:maxNSU', namespaces=ns)[0].text
                ult_nsu_sefaz = root.xpath('//ns:ultNSU', namespaces=ns)[0].text
                logger.debug(f"NSU Máximo disponível na SEFAZ: {max_nsu_sefaz} | Último NSU deste lote: {ult_nsu_sefaz}")
                
                docs = root.xpath('//ns:docZip', namespaces=ns)
                logger.info(f"Lote {lotes_processados} trouxe {len(docs)} documentos.")

                # Atualiza o ponteiro no banco APENAS se o NSU realmente avançou
                # A comparação de string funciona para NSUs porque eles têm comprimento fixo e são numéricos.
                if ult_nsu_sefaz > nsu_para_requisicao:
                    self.empresa.nfe_ultimo_nsu = ult_nsu_sefaz
                else:
                    # Se o ult_nsu_sefaz não avançou, mas não é 137, pode ser um lote vazio ou erro.
                    # Para evitar loop infinito, se não houver documentos e o NSU não avançou, paramos.
                    if len(docs) == 0:
                        logger.info("NSU não avançou e nenhum documento foi retornado. Encerrando busca para evitar loop.")
                        continua_busca = False
                        break
                
                for doc in docs:
                    nsu_doc = doc.get('NSU')
                    logger.debug(f"Processando documento compactado NSU: {nsu_doc}")
                    xml_decode = gzip.decompress(base64.b64decode(doc.text))
                    doc_root = etree.fromstring(xml_decode)
                    tag_local = etree.QName(doc_root).localname
                    
                    # Busca chave de acesso (comum em quase todos os docs)
                    ch_node = doc_root.xpath('//ns:chNFe', namespaces=ns) or doc_root.xpath('//*[local-name()="chNFe"]')
                    chave = ch_node[0].text if ch_node else None
                    
                    # 1. Diferencia o tipo de documento pelo tipo de evento (se existir)
                    # Ex: 'resEvento' vira 'resEvento_210210' (Ciência) ou 'resEvento_110111' (Cancelamento)
                    tipo_doc_salvar = tag_local
                    if 'Evento' in tag_local:
                        tp_evento_node = doc_root.xpath('//*[local-name()="tpEvento"]')
                        if tp_evento_node:
                            tipo_doc_salvar = f"{tag_local}_{tp_evento_node[0].text}"
                    
                    # 2. Verifica se já temos esse documento exato (pelo NSU que é único para o evento)
                    doc_existente = self.db.query(models.NotaFiscalRecebida).filter_by(nsu=nsu_doc, id_empresa=self.id_empresa).first()
                    
                    # 3. (Removido) Permite a inserção de múltiplos eventos do mesmo tipo 
                    # para a mesma nota, desde que o NSU seja diferente (que é o padrão da SEFAZ).
                    # if not doc_existente and chave:
                    #     doc_existente = self.db.query(models.NotaFiscalRecebida).filter_by(
                    #         chave_acesso=chave,
                    #         tipo_documento=tipo_doc_salvar,
                    #         id_empresa=self.id_empresa
                    #     ).first()

                    if not doc_existente:
                        logger.info(f"Inserindo novo documento DF-e: {tag_local}, NSU: {nsu_doc}")
                        novo_doc = models.NotaFiscalRecebida(
                            nsu=nsu_doc,
                            chave_acesso=chave,
                            tipo_documento=tipo_doc_salvar,
                            xml_completo=etree.tostring(doc_root, encoding='unicode'),
                            id_empresa=self.id_empresa,
                            situacao_manifestacao="Recebido"
                        )
                        
                        # Extração de metadados "best effort" dependendo do tipo
                        try:
                            if tag_local == 'resNFe':
                                novo_doc.cnpj_emitente = doc_root.xpath('//ns:CNPJ', namespaces=ns)[0].text
                                novo_doc.nome_emitente = doc_root.xpath('//ns:xNome', namespaces=ns)[0].text
                                novo_doc.valor_total = Decimal(doc_root.xpath('//ns:vNF', namespaces=ns)[0].text)
                                novo_doc.data_emissao = datetime.fromisoformat(doc_root.xpath('//ns:dhEmi', namespaces=ns)[0].text)
                            
                            elif tag_local == 'nfeProc':
                                emit = doc_root.xpath('//ns:emit', namespaces=ns)[0]
                                total = doc_root.xpath('//ns:total/ns:ICMSTot', namespaces=ns)[0]
                                ide = doc_root.xpath('//ns:ide', namespaces=ns)[0]
                                novo_doc.cnpj_emitente = (emit.xpath('ns:CNPJ', namespaces=ns) or emit.xpath('ns:CPF', namespaces=ns))[0].text
                                novo_doc.nome_emitente = emit.xpath('ns:xNome', namespaces=ns)[0].text
                                novo_doc.valor_total = Decimal(total.xpath('ns:vNF', namespaces=ns)[0].text)
                                novo_doc.data_emissao = datetime.fromisoformat(ide.xpath('ns:dhEmi', namespaces=ns)[0].text.replace('Z', ''))
                                novo_doc.situacao_manifestacao = "Completa"

                            elif 'Evento' in tag_local:
                                if not novo_doc.data_emissao:
                                    dh_node = doc_root.xpath('//*[local-name()="dhEvento"]')
                                    if dh_node: novo_doc.data_emissao = datetime.fromisoformat(dh_node[0].text.replace('Z', ''))
                        except Exception as e:
                            logger.warning(f"Erro ao extrair metadados para NSU {nsu_doc}: {e}")

                        self.db.add(novo_doc)
                        novas_notas += 1
                    else:
                        # Se já existe mas recebemos a versão completa (nfeProc) agora
                        if tag_local == 'nfeProc' and doc_existente.tipo_documento != 'nfeProc':
                            doc_existente.tipo_documento = 'nfeProc'
                            doc_existente.xml_completo = etree.tostring(doc_root, encoding='unicode')
                            doc_existente.situacao_manifestacao = "Completa"
                
                # Salva o progresso deste lote
                self.db.commit()
                logger.debug(f"Commit do lote {lotes_processados} realizado com sucesso.")
                
                # Se o último NSU recebido for igual ao máximo da SEFAZ, não há mais nada para puxar
                if ult_nsu_sefaz == max_nsu_sefaz:
                    logger.info("Alcançado o NSU máximo disponível na SEFAZ. Encerrando busca.")
                    _cooldown_sefaz[self.id_empresa] = datetime.now(TZ_BR) + timedelta(hours=1)
                    continua_busca = False

                if continua_busca:
                    # Delay OBRIGATÓRIO de 3 segundos entre lotes para evitar o Consumo Indevido (Rejeição 656)
                    logger.debug("Aguardando 3 segundos antes do próximo lote para respeitar limite da SEFAZ...")
                    time.sleep(5)

            logger.info(f"Sincronização DF-e concluída. Novas notas encontradas: {novas_notas}. NSU Final: {self.empresa.nfe_ultimo_nsu}")
            return {"success": True, "novas_notas": novas_notas, "atual_nsu": self.empresa.nfe_ultimo_nsu}
        finally:
            if os.path.exists(cert_path): os.remove(cert_path)

    def manifestar_ciencia(self, nota_id: int):
        """Envia evento de Ciência da Operação (210210) para destravar XML."""
        logger.info(f"Iniciando manifestação de ciência para nota ID: {nota_id}")
        nota = self.db.query(models.NotaFiscalRecebida).filter(
            models.NotaFiscalRecebida.id_empresa == self.id_empresa,
            models.NotaFiscalRecebida.id_sequencial == nota_id
        ).first()
        cert_path = self._get_certificado_path()
        try:
            from pynfe.entidades.evento import Evento
            logger.debug(f"Manifestando ciência para Chave: {nota.chave_acesso}")
            
            # Extrai e formata a UF de forma segura (evitando erros se não for Enum)
            uf_empresa = self.empresa.estado.value if hasattr(self.empresa.estado, 'value') else self.empresa.estado
            uf_empresa = uf_empresa.upper() if uf_empresa else 'SP' # Fallback para evitar erro crítico
            
            con = ComunicacaoSefaz(uf_empresa, cert_path, self.empresa.certificado_senha, homologacao=False)
            
            evento = Evento(
                cnpj=self._limpar_formatacao(self.empresa.cnpj),
                chave=nota.chave_acesso,
                tipo='210210',
                motivo='Ciencia da Operacao',
                data_emissao=datetime.now(timezone.utc),
                uf=uf_empresa
            )
            
            serializador = SerializacaoXML(_fonte_dados, homologacao=False)
            xml_evento = serializador.serializar_evento(evento)
            assinador = AssinaturaA1(cert_path, self.empresa.certificado_senha)
            xml_assinado = assinador.assinar(xml_evento)
            
            resp = con.evento(modelo='nfe', evento=xml_assinado)
            logger.info(f"Evento de ciência enviado para Chave {nota.chave_acesso}. Resposta SEFAZ: {resp}")

            nota.situacao_manifestacao = "Ciencia Realizada"
            self.db.commit()
            return {"success": True, "message": "Ciência enviada. Aguarde a próxima sincronização para baixar o XML completo."}
        finally:
            if os.path.exists(cert_path): os.remove(cert_path)

    def importar_xml_manual(self, xml_content: str):
        """
        Recebe o conteúdo de um XML, valida e salva na tabela nfe_recebidas.
        Suporta nfeProc e NFe.
        """
        try:
            # 1. Parse do XML
            if isinstance(xml_content, str):
                xml_data = xml_content.encode('utf-8')
            else:
                xml_data = xml_content
            
            root = etree.fromstring(xml_data)
            
            # Namespaces
            ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
            
            tag_local = etree.QName(root).localname
            
            # 2. Busca Chave de Acesso
            ch_node = root.xpath('//ns:chNFe', namespaces=ns) or root.xpath('//*[local-name()="chNFe"]')
            if not ch_node:
                raise Exception("Chave de acesso não encontrada no XML.")
            
            chave = ch_node[0].text
            
            # 3. Verifica se já existe
            nota_existente = self.db.query(models.NotaFiscalRecebida).filter_by(
                chave_acesso=chave, 
                id_empresa=self.id_empresa
            ).first()
            
            if nota_existente:
                # Se já existe, apenas atualiza se for uma versão mais completa (ex: nfeProc)
                if tag_local == 'nfeProc' and nota_existente.tipo_documento != 'nfeProc':
                    nota_existente.tipo_documento = 'nfeProc'
                    nota_existente.xml_completo = etree.tostring(root, encoding='unicode')
                    nota_existente.situacao_manifestacao = "Completa"
                    self.db.commit()
                return nota_existente

            # 4. Cria nova nota
            nova_nota = models.NotaFiscalRecebida(
                chave_acesso=chave,
                tipo_documento=tag_local,
                xml_completo=etree.tostring(root, encoding='unicode'),
                id_empresa=self.id_empresa,
                situacao_manifestacao="Recebido"
            )

            # 5. Extração de Metadados
            try:
                if tag_local == 'resNFe':
                    node_cnpj = root.xpath('//ns:CNPJ', namespaces=ns)
                    if node_cnpj: nova_nota.cnpj_emitente = node_cnpj[0].text
                    
                    node_nome = root.xpath('//ns:xNome', namespaces=ns)
                    if node_nome: nova_nota.nome_emitente = node_nome[0].text
                    
                    node_vinf = root.xpath('//ns:vNF', namespaces=ns)
                    if node_vinf: nova_nota.valor_total = Decimal(node_vinf[0].text)
                    
                    node_dh = root.xpath('//ns:dhEmi', namespaces=ns)
                    if node_dh: nova_nota.data_emissao = datetime.fromisoformat(node_dh[0].text.replace('Z', ''))
                
                elif tag_local == 'nfeProc' or tag_local == 'NFe':
                    emit = root.xpath('//ns:emit', namespaces=ns)
                    if emit:
                        emit = emit[0]
                        node_cnpj = emit.xpath('ns:CNPJ', namespaces=ns) or emit.xpath('ns:CPF', namespaces=ns)
                        if node_cnpj: nova_nota.cnpj_emitente = node_cnpj[0].text
                        
                        node_nome = emit.xpath('ns:xNome', namespaces=ns)
                        if node_nome: nova_nota.nome_emitente = node_nome[0].text
                    
                    total = root.xpath('//ns:total/ns:ICMSTot', namespaces=ns)
                    if total:
                        vnf_node = total[0].xpath('ns:vNF', namespaces=ns)
                        if vnf_node: nova_nota.valor_total = Decimal(vnf_node[0].text)
                    
                    ide = root.xpath('//ns:ide', namespaces=ns)
                    if ide:
                        dh_emi_node = ide[0].xpath('ns:dhEmi', namespaces=ns)
                        if dh_emi_node:
                            dh_emi_str = dh_emi_node[0].text
                            nova_nota.data_emissao = datetime.fromisoformat(dh_emi_str.replace('Z', ''))
                    
                    if tag_local == 'nfeProc':
                        nova_nota.situacao_manifestacao = "Completa"
            except Exception as e:
                logger.warning(f"Erro ao extrair metadados do XML manual (Chave: {chave}): {e}")

            self.db.add(nova_nota)
            self.db.commit()
            return nova_nota

        except Exception as e:
            self.db.rollback()
            logger.error(f"Erro ao importar XML manual: {e}")
            raise HTTPException(status_code=400, detail=f"Erro ao processar XML: {str(e)}")

    def importar_nfe_compra(
        self,
        nota_id: int,
        mapeamento_itens: list,
        movimentar_estoque: bool,
        gerar_financeiro: bool,
        id_classificacao_contabil: int = None,
        caixa_destino_origem: str = None,
        forma_pagamento: str = None
    ):
        """
        Importa a nota para o sistema, vinculando variações de SKUs e gerando movimentos.
        mapeamento_itens: [{"sku_fornecedor": "ABC", "id_produto_erp": 10, "quantidade": 5}, ...]
        """
        logger.info(f"Iniciando importação de NFe de Compra. Nota ID: {nota_id}")
        nota = self.db.query(models.NotaFiscalRecebida).filter(
            models.NotaFiscalRecebida.id_empresa == self.id_empresa,
            models.NotaFiscalRecebida.id_sequencial == nota_id
        ).first()

        if not nota:
            logger.error(f"NotaFiscalRecebida ID {nota_id} não encontrada.")
            raise HTTPException(status_code=404, detail="Nota não encontrada.")

        if not nota.xml_completo:
            logger.error(f"Tentativa de importar nota ID {nota_id} sem XML completo.")
            raise HTTPException(status_code=400, detail="XML completo ainda não disponível. Realize a Ciência primeiro.")

        try:
            root = etree.fromstring(nota.xml_completo.encode('utf-8'))
            ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

            # ==========================================
            # 1. VERIFICAÇÃO / CRIAÇÃO DO FORNECEDOR
            # ==========================================
            emit_node = root.xpath('//ns:emit', namespaces=ns)[0]
            
            # Pega CNPJ ou CPF (caso o fornecedor seja produtor rural/PF)
            cpf_cnpj_node = emit_node.xpath('ns:CNPJ', namespaces=ns) or emit_node.xpath('ns:CPF', namespaces=ns)
            cnpj_fornecedor = cpf_cnpj_node[0].text if cpf_cnpj_node else None
            nome_fornecedor = emit_node.xpath('ns:xNome', namespaces=ns)[0].text

            fornecedor = self.db.query(models.Cadastro).filter(
                models.Cadastro.cpf_cnpj == cnpj_fornecedor,
                models.Cadastro.id_empresa == self.id_empresa
            ).first()

            if not fornecedor:
                logger.info(f"Fornecedor não encontrado. Criando novo: {nome_fornecedor} - {cnpj_fornecedor}")
                
                # --- EXTRAÇÃO DE ENDEREÇO E CONTATO ---
                ender_emit = emit_node.xpath('ns:enderEmit', namespaces=ns)
                
                cep_val = '00000000' # Fallback para evitar erro 500 caso a tag venha vazia
                logradouro_val = numero_val = bairro_val = cidade_val = estado_val = None
                cidade_ibge_val = telefone_val = complemento_val = None
                
                if ender_emit:
                    ender = ender_emit[0]
                    cep_node = ender.xpath('ns:CEP', namespaces=ns)
                    if cep_node and cep_node[0].text:
                        cep_val = cep_node[0].text
                        
                    lgr_node = ender.xpath('ns:xLgr', namespaces=ns)
                    logradouro_val = lgr_node[0].text if lgr_node else None
                    
                    nro_node = ender.xpath('ns:nro', namespaces=ns)
                    numero_val = nro_node[0].text if nro_node else None
                    
                    cpl_node = ender.xpath('ns:xCpl', namespaces=ns)
                    complemento_val = cpl_node[0].text if cpl_node else None
                    
                    bairro_node = ender.xpath('ns:xBairro', namespaces=ns)
                    bairro_val = bairro_node[0].text if bairro_node else None
                    
                    mun_node = ender.xpath('ns:xMun', namespaces=ns)
                    cidade_val = mun_node[0].text if mun_node else None
                    
                    cmun_node = ender.xpath('ns:cMun', namespaces=ns)
                    cidade_ibge_val = cmun_node[0].text if cmun_node else None
                    
                    uf_node = ender.xpath('ns:UF', namespaces=ns)
                    estado_val = uf_node[0].text if uf_node else None
                    
                    fone_node = ender.xpath('ns:fone', namespaces=ns)
                    telefone_val = fone_node[0].text if fone_node else None

                # --- EXTRAÇÃO DE INSCRIÇÃO ESTADUAL ---
                ie_node = emit_node.xpath('ns:IE', namespaces=ns)
                ie_val = ie_node[0].text if ie_node else None
                
                # Tipo de pessoa (Física ou Jurídica)
                tipo_pessoa = models.CadastroTipoPessoaEnum.juridica
                if cpf_cnpj_node and etree.QName(cpf_cnpj_node[0]).localname == 'CPF':
                    tipo_pessoa = models.CadastroTipoPessoaEnum.fisica

                # Lógica para indicador IE (Contribuinte ou Não)
                indicador_ie = models.CadastroIndicadorIEEnum.nao_contribuinte
                if ie_val and ie_val.upper() != 'ISENTO':
                    indicador_ie = models.CadastroIndicadorIEEnum.contribuinte_icms

                fornecedor = models.Cadastro(
                    cpf_cnpj=cnpj_fornecedor,
                    nome_razao=nome_fornecedor,
                    tipo_pessoa=tipo_pessoa,
                    tipo_cadastro=models.CadastroTipoCadastroEnum.fornecedor,
                    indicador_ie=indicador_ie,
                    inscricao_estadual=ie_val,
                    cep=cep_val,
                    estado=estado_val,
                    cidade=cidade_val,
                    cidade_ibge=cidade_ibge_val,
                    bairro=bairro_val,
                    logradouro=logradouro_val,
                    numero=numero_val,
                    complemento=complemento_val,
                    telefone=telefone_val,
                    id_empresa=self.id_empresa,
                    situacao=True
                )
                self.db.add(fornecedor)
                self.db.flush()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao processar XML da Nota ID {nota_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao processar XML da nota: {str(e)}")

        if not mapeamento_itens:
            mapeamento_itens = []

        for item in mapeamento_itens:
            if not item or 'id_produto_erp' not in item or not item.get('id_produto_erp'):
                continue

            prod_id_erp = item['id_produto_erp']
            produto = self.db.query(models.Produto).filter(
                models.Produto.id_empresa == self.id_empresa,
                models.Produto.id_sequencial == prod_id_erp
            ).first()

            if not produto:
                logger.warning(f"Produto ERP ID {item['id_produto_erp']} não encontrado durante importação da nota {nota_id}.")
                continue

            logger.debug(f"Vinculando SKU fornecedor {item.get('sku_fornecedor')} ao produto ERP {produto.sku}")
            if item.get('sku_fornecedor') and item['sku_fornecedor'] not in (produto.variacoes or []):
                novas_vars = list(produto.variacoes or [])
                novas_vars.append(item['sku_fornecedor'])
                produto.variacoes = novas_vars

            produto.id_fornecedor = fornecedor.id_sequencial if fornecedor else None

            if movimentar_estoque:
                logger.info(f"Movimentando estoque para produto {produto.sku}. Qtd: {item.get('quantidade', 0)}")
                novo_estoque = models.Estoque(
                    id_produto=produto.id_sequencial or produto.id,
                    quantidade=item.get('quantidade', 0),
                    id_empresa=self.id_empresa,
                    lote=f"ENTRADA_NFE_{nota.id}"
                )
                self.db.add(novo_estoque)

        if gerar_financeiro:
            try:
                nNF = root.xpath('//ns:ide/ns:nNF', namespaces=ns)
                nNF = nNF[0].text if nNF else None

                tPag_nodes = root.xpath('//ns:pag/ns:detPag/ns:tPag', namespaces=ns)
                tPag_xml = forma_pagamento if forma_pagamento else (tPag_nodes[0].text if tPag_nodes else '90')

                try:
                    pagamento_enum = models.FiscalPagamentoEnum(tPag_xml)
                except ValueError:
                    pagamento_enum = models.FiscalPagamentoEnum.outros if hasattr(models.FiscalPagamentoEnum, 'outros') else models.FiscalPagamentoEnum.cst_90 if hasattr(models.FiscalPagamentoEnum, 'cst_90') else None

                dup_nodes = root.xpath('//ns:cobr/ns:dup/ns:dVenc', namespaces=ns)
                data_vencimento = datetime.fromisoformat(dup_nodes[0].text).date() if dup_nodes else datetime.now(TZ_BR).date() + timedelta(days=30)

                descricao_nota = f"Compra NFe {nNF or nota.chave_acesso[:10]} - {nome_fornecedor}"

                nova_conta = models.Conta(
                    tipo_conta=models.ContaTipoEnum.a_pagar,
                    situacao=models.ContaSituacaoEnum.em_aberto,
                    valor=nota.valor_total,
                    descricao=descricao_nota,
                    numero_conta=nNF,
                    pagamento=pagamento_enum,
                    id_fornecedor=fornecedor.id_sequencial if fornecedor else None,
                    id_classificacao_contabil=id_classificacao_contabil,
                    caixa_destino_origem=caixa_destino_origem,
                    data_emissao=nota.data_emissao.date() if getattr(nota, 'data_emissao', None) else datetime.now(TZ_BR).date(),
                    data_vencimento=data_vencimento,
                    id_empresa=self.id_empresa
                )
                self.db.add(nova_conta)
            except Exception as e:
                logger.error(f"Erro ao gerar financeiro para nota {nota_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Erro ao gerar financeiro: {str(e)}")

        nota.ja_importado = True
        self.db.commit()
        logger.info(f"Importação da nota ID {nota_id} finalizada com sucesso.")
        return {"success": True}