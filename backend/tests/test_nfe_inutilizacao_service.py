import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app.core.service.nfe_service import NFeService
from app.core.db.models import Empresa, EmpresaAmbienteSefazEnum, NfeInutilizacao

class TestNfeInutilizacaoService(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_empresa = MagicMock()
        self.mock_empresa.id = 1
        self.mock_empresa.cnpj = "12345678000195"
        self.mock_empresa.estado = "SP"
        self.mock_empresa.nfe_serie = 1
        self.mock_empresa.ambiente_sefaz = EmpresaAmbienteSefazEnum.homologacao
        self.mock_empresa.certificado_arquivo = b"fake-cert"
        self.mock_empresa.certificado_senha = "fake-password"
        self.mock_db.query(Empresa).filter().first.return_value = self.mock_empresa

    def test_valida_justificativa_curta(self):
        service = NFeService(self.mock_db, id_empresa=1)
        with self.assertRaises(HTTPException) as ctx:
            service.inutilizar_numeracao(modelo="55", serie=1, numero_inicial=1, numero_final=1, justificativa="Curta", id_usuario=1)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("15 caracteres", ctx.exception.detail)

    def test_valida_faixa_invalida(self):
        service = NFeService(self.mock_db, id_empresa=1)
        with self.assertRaises(HTTPException) as ctx:
            service.inutilizar_numeracao(modelo="55", serie=1, numero_inicial=10, numero_final=5, justificativa="Justificativa com mais de 15 caracteres", id_usuario=1)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("app.core.service.nfe_service.ComunicacaoSefaz")
    @patch("tempfile.NamedTemporaryFile")
    def test_inutilizacao_sucesso_homologado_102(self, mock_tmp, mock_sefaz_cls):
        mock_sefaz = MagicMock()
        mock_sefaz_cls.return_value = mock_sefaz
        # XML de retorno com cStat 102
        xml_retorno = """<retInutNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
            <infInut>
                <cStat>102</cStat>
                <xMotivo>Inutilizacao de numero homologado</xMotivo>
                <nProt>135260000000001</nProt>
                <dhRecbto>2026-11-04T14:30:00-03:00</dhRecbto>
            </infInut>
        </retInutNFe>"""
        mock_sefaz.inutilizacao.return_value = xml_retorno.encode('utf-8')

        service = NFeService(self.mock_db, id_empresa=1)
        res = service.inutilizar_numeracao(
            modelo="55", serie=1, numero_inicial=100, numero_final=102,
            justificativa="Quebra de sequencia devido a falha de conexao", id_usuario=1
        )
        self.assertEqual(res["cstat"], "102")
        self.assertEqual(res["protocolo"], "135260000000001")
        self.assertTrue(res["sucesso"])
        self.mock_db.add.assert_called()
        self.mock_db.commit.assert_called()

    @patch("app.core.service.nfe_service.ComunicacaoSefaz")
    @patch("tempfile.NamedTemporaryFile")
    def test_inutilizacao_rejeicao_sefaz(self, mock_tmp, mock_sefaz_cls):
        mock_sefaz = MagicMock()
        mock_sefaz_cls.return_value = mock_sefaz
        # XML de retorno com cStat 206 (rejeição)
        xml_retorno = """<retInutNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
            <infInut>
                <cStat>206</cStat>
                <xMotivo>Rejeicao: NF-e ja esta inutilizada na Base de Dados da SEFAZ</xMotivo>
                <dhRecbto>2026-11-04T14:30:00-03:00</dhRecbto>
            </infInut>
        </retInutNFe>"""
        mock_sefaz.inutilizacao.return_value = xml_retorno.encode('utf-8')

        service = NFeService(self.mock_db, id_empresa=1)
        res = service.inutilizar_numeracao(
            modelo="55", serie=1, numero_inicial=100, numero_final=100,
            justificativa="Tentativa de reutilizacao de numeracao cancelada", id_usuario=1
        )
        self.assertEqual(res["cstat"], "206")
        self.assertFalse(res["sucesso"])
        self.assertIn("ja esta inutilizada", res["xmotivo"])

    def test_listar_inutilizacoes(self):
        service = NFeService(self.mock_db, id_empresa=1)
        mock_query = MagicMock()
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [{"id": 1, "numero_inicial": 100}]

        resultado = service.listar_inutilizacoes(limit=10, offset=0)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["id"], 1)
