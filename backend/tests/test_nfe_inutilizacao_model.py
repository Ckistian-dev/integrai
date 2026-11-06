import unittest
from datetime import datetime
from app.core.db.models import NfeInutilizacao, Empresa, Usuario

class TestNfeInutilizacaoModel(unittest.TestCase):
    def test_model_fields_and_tablename(self):
        self.assertEqual(NfeInutilizacao.__tablename__, "nfe_inutilizacoes")
        
        agora = datetime.utcnow()
        inut = NfeInutilizacao(
            id_empresa=1,
            id_usuario=2,
            modelo="55",
            serie=1,
            numero_inicial=100,
            numero_final=105,
            ano=2026,
            justificativa="Quebra de numeracao por falha de transmissao",
            cstat="102",
            xmotivo="Inutilizacao de numero homologado",
            protocolo="135260000000001",
            data_recebimento=agora,
            xml_retorno="<retInutNFe/>",
            sucesso=True,
            created_at=agora
        )
        self.assertEqual(inut.id_empresa, 1)
        self.assertEqual(inut.id_usuario, 2)
        self.assertEqual(inut.modelo, "55")
        self.assertEqual(inut.serie, 1)
        self.assertEqual(inut.numero_inicial, 100)
        self.assertEqual(inut.numero_final, 105)
        self.assertEqual(inut.ano, 2026)
        self.assertEqual(inut.justificativa, "Quebra de numeracao por falha de transmissao")
        self.assertEqual(inut.xml_retorno, "<retInutNFe/>")
        self.assertTrue(inut.sucesso)
        self.assertEqual(inut.cstat, "102")
        self.assertEqual(inut.xmotivo, "Inutilizacao de numero homologado")
        self.assertEqual(inut.protocolo, "135260000000001")
        self.assertEqual(inut.data_recebimento, agora)
        self.assertEqual(inut.created_at, agora)

    def test_model_defaults(self):
        inut = NfeInutilizacao()
        self.assertEqual(inut.modelo, "55")
        self.assertEqual(inut.serie, 1)
        self.assertFalse(inut.sucesso)
