import httpx
import logging
import base64
import asyncio
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.db import models
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_placeholders(pedido: models.Pedido, situacao_para: str = None, from_name: str = None) -> dict:
    """Monta o dicionário de placeholders disponíveis para substituição em subject/body."""
    valor_total = ""
    if pedido.total is not None:
        try:
            valor_total = f"R$ {pedido.total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        except Exception:
            valor_total = str(pedido.total)

    return {
        "{cliente_nome}": (pedido.cliente.nome_razao if pedido.cliente else "") or "",
        "{pedido_id}": str(pedido.id),
        "{valor_total}": valor_total,
        "{empresa_nome}": from_name or "Nossa Empresa",
        "{situacao}": situacao_para or (pedido.situacao.value if pedido.situacao else ""),
        "{situacao_anterior}": "",  # Preenchido dinamicamente quando disponível
        "{numero_nf}": pedido.numero_nf or "",
        "{chave_acesso}": pedido.chave_acesso or "",
    }


def _apply_placeholders(text: str, placeholders: dict) -> str:
    """Substitui todos os placeholders no texto."""
    if not text:
        return text
    for key, val in placeholders.items():
        text = text.replace(key, str(val))
    return text


class ElasticEmailService:
    def __init__(self, db: Session, id_empresa: int):
        self.db = db
        self.id_empresa = id_empresa
        self.base_url = "https://api.elasticemail.com/v4"

        # Carrega a configuração principal (credenciais) — pode ser None se não configurado
        self.config = self.db.query(models.ElasticEmailConfiguracao).filter(
            models.ElasticEmailConfiguracao.id_empresa == self.id_empresa
        ).first()

    # -------------------------------------------------------------------
    # Método público principal: disparo por trigger de status
    # -------------------------------------------------------------------
    async def send_trigger_emails(
        self,
        pedido: models.Pedido,
        situacao_de: Optional[str],
        situacao_para: str,
        pdf_b64: Optional[str] = None,
        xml_str: Optional[str] = None,
    ) -> list:
        """
        Busca todas as EmailRegras ativas que correspondem à transição
        (situacao_de -> situacao_para) e envia um e-mail para cada uma.

        A configuração de credenciais (API Key) é resolvida automaticamente
        pela empresa — não é necessário selecionar manualmente.
        """
        # Carrega todas as regras ativas da empresa
        regras = self.db.query(models.EmailRegra).filter(
            models.EmailRegra.id_empresa == self.id_empresa,
            models.EmailRegra.ativo == True,
        ).all()

        # Filtra pelas regras cujo trigger corresponde à transição atual
        # Usa as propriedades situacao_de / situacao_para derivadas do campo trigger
        regras_matching = []
        for r in regras:
            r_de = r.situacao_de       # None = qualquer origem
            r_para = r.situacao_para   # destino obrigatório

            if r_para != situacao_para:
                continue
            if r_de is not None and r_de != situacao_de:
                continue
            regras_matching.append(r)

        if not regras_matching:
            logger.info(
                f"Nenhuma regra de e-mail encontrada para a transição "
                f"'{situacao_de}' -> '{situacao_para}' na empresa {self.id_empresa}."
            )
            return []

        results = []
        for regra in regras_matching:
            result = await self._send_for_regra(regra, pedido, situacao_de, situacao_para, pdf_b64, xml_str)
            results.append(result)

        return results

    async def _send_for_regra(
        self,
        regra: models.EmailRegra,
        pedido: models.Pedido,
        situacao_de: Optional[str],
        situacao_para: str,
        pdf_b64: Optional[str],
        xml_str: Optional[str],
    ) -> dict:
        """Envia o e-mail para uma regra específica usando a config da empresa."""

        # A config é resolvida automaticamente pela empresa (sem FK manual)
        elastic_config = self.config

        if not elastic_config or not elastic_config.api_key:
            logger.warning(f"Regra '{regra.nome}' sem configuração de API Key válida. Configure o Elastic Email primeiro.")
            return {"success": False, "regra": regra.nome, "message": "API Key não configurada."}

        if not pedido.cliente or not pedido.cliente.email:
            logger.warning(
                f"Pedido {pedido.id} sem e-mail de cliente. Regra '{regra.nome}' não enviada."
            )
            return {"success": False, "regra": regra.nome, "message": "Cliente sem e-mail."}

        # Monta placeholders
        placeholders = _build_placeholders(pedido, situacao_para, elastic_config.from_name)
        placeholders["{situacao_anterior}"] = situacao_de or ""

        subject = _apply_placeholders(regra.subject or "Atualização do Pedido #{pedido_id}", placeholders)
        body = _apply_placeholders(
            regra.body_html or f"<p>Olá {placeholders['{cliente_nome}']},<br>Seu pedido #{placeholders['{pedido_id}']} foi atualizado para <strong>{situacao_para}</strong>.</p>",
            placeholders
        )

        # Converte quebras de linha em <br>
        body = body.replace("\r\n", "<br>").replace("\n", "<br>")

        # Monta payload base
        payload = {
            "Recipients": [
                {
                    "Email": pedido.cliente.email,
                    "Fields": {"name": pedido.cliente.nome_razao or ""},
                }
            ],
            "Content": {
                "Body": [
                    {
                        "ContentType": "HTML",
                        "Content": body,
                        "Charset": "utf-8",
                    }
                ],
                "From": f"{elastic_config.from_name} <{elastic_config.from_email}>",
                "Subject": subject,
            },
        }

        # Adiciona anexos conforme selecionado na regra
        if regra.anexos:
            attachments = []
            if 'danfe' in regra.anexos and pdf_b64:
                attachments.append({
                    "BinaryContent": pdf_b64,
                    "Name": f"DANFE_Pedido_{pedido.id}.pdf",
                    "ContentType": "application/pdf",
                })
            if 'xml' in regra.anexos and xml_str:
                attachments.append({
                    "BinaryContent": base64.b64encode(xml_str.encode("utf-8")).decode("utf-8"),
                    "Name": f"NFe_Pedido_{pedido.id}.xml",
                    "ContentType": "application/xml",
                })
            
            if attachments:
                payload["Content"]["Attachments"] = attachments

        headers = {
            "X-ElasticEmail-ApiKey": elastic_config.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info(
                    f"[EmailRegra '{regra.nome}'] Enviando e-mail para "
                    f"{pedido.cliente.email} (Pedido #{pedido.id}, {situacao_de} -> {situacao_para})..."
                )

                if settings.ENVIRONMENT != "production":
                    logger.info(f"[EmailRegra '{regra.nome}'] SIMULADO: E-mail não enviado pois o ambiente é '{settings.ENVIRONMENT}'.")
                    return {
                        "success": True,
                        "regra": regra.nome,
                        "message": "E-mail simulado com sucesso! (Ambiente de Desenvolvimento)",
                    }

                resp = await client.post(
                    f"{self.base_url}/emails", json=payload, headers=headers, timeout=30.0
                )

                if resp.status_code in [200, 201, 202]:
                    data = resp.json()
                    logger.info(
                        f"[EmailRegra '{regra.nome}'] Enviado! TransactionID: {data.get('TransactionID')}"
                    )
                    return {
                        "success": True,
                        "regra": regra.nome,
                        "message": "E-mail enviado com sucesso!",
                        "transaction_id": data.get("TransactionID"),
                    }
                else:
                    logger.error(
                        f"[EmailRegra '{regra.nome}'] Erro API Elastic Email: "
                        f"{resp.status_code} - {resp.text}"
                    )
                    return {
                        "success": False,
                        "regra": regra.nome,
                        "message": f"Erro na API: {resp.status_code}",
                        "error": resp.text,
                    }

        except Exception as e:
            logger.exception(f"[EmailRegra '{regra.nome}'] Falha fatal: {str(e)}")
            return {
                "success": False,
                "regra": regra.nome,
                "message": f"Falha ao enviar e-mail: {str(e)}",
                "error": str(e),
            }

    # -------------------------------------------------------------------
    # Método legado (mantido para compatibilidade com nfe_service.py)
    # -------------------------------------------------------------------
    async def send_invoice_email(self, pedido: models.Pedido, pdf_b64: str, xml_str: str):
        """
        [LEGADO] Envia o e-mail de NFe.
        Agora integra com as EmailRegras, priorizando a transição 'Faturamento' -> 'Expedição',
        que é o fluxo padrão de emissão de NFe.
        """
        # 1. Tenta disparar via regra específica da transição atual (Faturamento -> Expedição)
        results = await self.send_trigger_emails(
            pedido=pedido,
            situacao_de="Faturamento",
            situacao_para="Expedição",
            pdf_b64=pdf_b64,
            xml_str=xml_str,
        )

        # 2. Se não houver, tenta regras genéricas de 'Faturamento' (legado de gatilho único)
        if not results:
            results = await self.send_trigger_emails(
                pedido=pedido,
                situacao_de=None,
                situacao_para="Faturamento",
                pdf_b64=pdf_b64,
                xml_str=xml_str,
            )

        if results:
            # Retorna o resultado do primeiro envio bem-sucedido
            sucesso = next((r for r in results if r.get("success")), None)
            return sucesso or results[-1]

        logger.info(f"Nenhuma regra de e-mail encontrada para o fluxo de NFe do pedido {pedido.id}. Nenhum e-mail enviado.")
        return None
