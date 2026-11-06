import unittest
import unicodedata
import json
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.db import models
from app.api.v1.endpoints.generic import apply_search_filter, extract_search_tokens

class TestGlobalSearchTokens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine('sqlite:///:memory:')
        @event.listens_for(cls.engine, 'connect')
        def connect(dbapi_connection, connection_record):
            dbapi_connection.create_function(
                'unaccent', 1,
                lambda s: ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn') if s is not None else ''
            )

        models.Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        # Cria empresa base
        self.empresa = models.Empresa(
            id=1,
            razao="Empresa Teste",
            fantasia="Empresa Fantasia",
            cnpj="00000000000000",
            cep="80000-000",
            estado="PR"
        )
        self.session.add(self.empresa)

        # Cria cliente Felipe Henrique Ferreira da Costa
        self.cliente = models.Cadastro(
            id_empresa=1,
            id_sequencial=101,
            nome_razao="FELIPE HENRIQUE FERREIRA DA COSTA",
            fantasia="Felipe Tech",
            tipo_pessoa="fisica",
            tipo_cadastro="cliente",
            cpf_cnpj="00000000000",
            cep="80000-000",
            cidade="Curitiba",
            bairro="Batel",
            email="felipe.costa@example.com"
        )
        self.session.add(self.cliente)

        # Cria outro cliente para garantir que não retorna resultados espúrios
        self.cliente_outro = models.Cadastro(
            id_empresa=1,
            id_sequencial=102,
            nome_razao="MARIA SILVA DA COSTA",
            fantasia="Maria Modas",
            tipo_pessoa="fisica",
            tipo_cadastro="cliente",
            cpf_cnpj="00000000000",
            cep="80000-001",
            cidade="Londrina",
            bairro="Centro",
            email="maria.costa@example.com"
        )
        self.session.add(self.cliente_outro)
        self.session.commit()

    def tearDown(self):
        self.session.query(models.Cadastro).delete()
        self.session.query(models.Empresa).delete()
        self.session.commit()
        self.session.close()

    def test_single_token_search(self):
        """Busca por um único termo 'Felipe' deve retornar o cliente"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe")
        results = q.all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].nome_razao, "FELIPE HENRIQUE FERREIRA DA COSTA")

    def test_multi_token_search_felipe_costa(self):
        """Busca global por 'Felipe Costa' deve encontrar 'FELIPE HENRIQUE FERREIRA DA COSTA'"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe Costa")
        results = q.all()
        self.assertEqual(len(results), 1, "Deveria retornar exatamente 1 cliente para 'Felipe Costa'")
        self.assertEqual(results[0].id_sequencial, 101)

    def test_multi_token_search_felipe_ferreira(self):
        """Busca global por 'Felipe Ferreira' deve encontrar 'FELIPE HENRIQUE FERREIRA DA COSTA'"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe Ferreira")
        results = q.all()
        self.assertEqual(len(results), 1, "Deveria retornar exatamente 1 cliente para 'Felipe Ferreira'")
        self.assertEqual(results[0].id_sequencial, 101)

    def test_multi_token_reverse_order(self):
        """Busca global por 'Costa Felipe' (ordem invertida) deve encontrar o cliente"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Costa Felipe")
        results = q.all()
        self.assertEqual(len(results), 1, "Deveria retornar 1 cliente para 'Costa Felipe'")
        self.assertEqual(results[0].id_sequencial, 101)

    def test_multi_token_across_fields(self):
        """Busca global com termos em campos diferentes ('Felipe Curitiba' = nome + cidade)"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe Curitiba")
        results = q.all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id_sequencial, 101)

    def test_multi_token_no_false_positive(self):
        """Busca por 'Felipe Silva' não deve retornar Felipe Costa nem Maria Silva"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe Silva")
        results = q.all()
        self.assertEqual(len(results), 0, "Felipe Silva não deve casar com Felipe Costa nem Maria Costa")

    def test_search_field_multi_token(self):
        """Busca em campo específico 'nome_razao' por 'Felipe Costa' deve retornar o cliente"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe Costa", search_field="nome_razao")
        results = q.all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id_sequencial, 101)

    def test_accent_insensitive_search(self):
        """Busca acentuada ou não acentuada 'Felipe Cósta' deve retornar 'FELIPE HENRIQUE FERREIRA DA COSTA'"""
        q = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "Felipe Cósta")
        results = q.all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id_sequencial, 101)

    def test_exact_phrase_with_quotes(self):
        """Busca com aspas exatas '\"Felipe Henrique\"' deve encontrar, mas '\"Felipe Costa\"' não (não são contíguos)"""
        q1 = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, '"Felipe Henrique"')
        self.assertEqual(len(q1.all()), 1)

        q2 = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, '"Felipe Costa"')
        self.assertEqual(len(q2.all()), 0)

    def test_internal_id_not_matched_in_global_search(self):
        """Busca global por número correspondente ao ID interno (id=1) não deve retornar o registro quando existe id_sequencial (101)"""
        # self.cliente tem id=1 (gerado pelo sqlite) e id_sequencial=101
        # self.cliente não possui o dígito '1' em nenhum campo de texto (cpf_cnpj, cep, nome, etc.)
        self.assertEqual(self.cliente.id, 1)
        self.assertEqual(self.cliente.id_sequencial, 101)

        # Busca pelo ID interno '1' NÃO deve retornar self.cliente na busca global
        q_internal = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "1")
        results_internal = q_internal.all()
        returned_seq_ids = [r.id_sequencial for r in results_internal]
        self.assertNotIn(101, returned_seq_ids, "Registro com id_sequencial=101 não deve ser retornado apenas porque seu id interno é 1")

        # Busca pelo id_sequencial '101' DEVE retornar o cliente
        q_seq = apply_search_filter(self.session.query(models.Cadastro), models.Cadastro, "101")
        results_seq = q_seq.all()
        self.assertEqual(len(results_seq), 1, "Busca pelo id_sequencial deve encontrar o registro")
        self.assertEqual(results_seq[0].id_sequencial, 101)

    def test_extract_search_tokens_helper(self):
        """Verifica tokenização com aspas, múltiplos espaços e termos simples"""
        self.assertEqual(extract_search_tokens("Felipe Costa"), ["Felipe", "Costa"])
        self.assertEqual(extract_search_tokens('  Felipe   "Henrique Ferreira"   Costa  '), ["Felipe", "Henrique Ferreira", "Costa"])
        self.assertEqual(extract_search_tokens(""), [])
        self.assertEqual(extract_search_tokens(None), [])

if __name__ == "__main__":
    unittest.main()
