import unittest
from unittest.mock import MagicMock, patch
from app.core.db import models, schemas

class TestNaturezaOperacao(unittest.TestCase):
    def test_pedido_model_natureza_operacao_metadata(self):
        """Verifica se o modelo Pedido possui a coluna natureza_operacao configurada como dropdown com 0 e 1"""
        col = models.Pedido.__table__.columns.get('natureza_operacao')
        self.assertIsNotNone(col, "Coluna 'natureza_operacao' deve existir no modelo Pedido")
        info = col.info or {}
        self.assertEqual(info.get('tab'), 'Fiscal', "O campo deve estar na aba 'Fiscal'")
        self.assertEqual(info.get('label'), 'Natureza da Operação', "O rótulo deve ser 'Natureza da Operação'")
        self.assertEqual(info.get('component'), 'select', "O componente deve ser 'select'")
        
        options = info.get('options')
        self.assertIsInstance(options, list, "As opções do select devem ser uma lista")
        self.assertEqual(len(options), 2, "Devem existir exatamente 2 opções (Entrada e Saída)")
        
        # Opções esperadas: 0 - Entrada, 1 - Saída
        options_map = {opt['value']: opt['label'] for opt in options if isinstance(opt, dict)}
        self.assertIn(0, options_map, "Opção 0 deve existir")
        self.assertIn(1, options_map, "Opção 1 deve existir")
        self.assertIn("Entrada", options_map[0])
        self.assertIn("Saída", options_map[1])

    def test_pedido_schemas_include_natureza_operacao(self):
        """Verifica se os schemas Pydantic de Pedido incluem natureza_operacao como Optional[int]"""
        self.assertIn('natureza_operacao', schemas.PedidoBase.model_fields, "PedidoBase deve ter o campo natureza_operacao")
        self.assertIn('natureza_operacao', schemas.PedidoUpdate.model_fields, "PedidoUpdate deve ter o campo natureza_operacao")

    def test_natureza_operacao_field_assignment(self):
        """Verifica se o modelo Pedido aceita atribuição de 0 (Entrada) e 1 (Saída)"""
        pedido = models.Pedido()
        self.assertTrue(hasattr(pedido, 'natureza_operacao'), "Pedido deve ter atributo natureza_operacao")
        
        pedido.natureza_operacao = 0
        self.assertEqual(pedido.natureza_operacao, 0)
        
        pedido.natureza_operacao = 1
        self.assertEqual(pedido.natureza_operacao, 1)

    def test_nfe_service_persists_natureza_operacao_code(self):
        """Verifica se o código fonte de nfe_service contém a atribuição pedido.natureza_operacao = int(tp_nf)"""
        import inspect
        from app.core.service.nfe_service import NFeService
        
        source = inspect.getsource(NFeService.emitir_nfe)
        self.assertIn('pedido.natureza_operacao = int(tp_nf)', source, 
                      "O método emitir_nfe deve atribuir pedido.natureza_operacao = int(tp_nf)")

    def test_metadata_endpoint_pedidos_has_natureza_operacao(self):
        """Verifica se o endpoint de metadados expõe natureza_operacao como select com as opções 0 e 1"""
        from app.api.v1.endpoints.metadata import get_model_metadata
        
        meta = get_model_metadata("pedidos")
        field = next((f for f in meta.fields if f.name == 'natureza_operacao'), None)
        self.assertIsNotNone(field, "natureza_operacao deve estar presente nos metadados de pedidos")
        self.assertEqual(field.label, "Natureza da Operação")
        self.assertEqual(field.tab, "Fiscal")
        self.assertEqual(field.type, "select")
        self.assertEqual(len(field.options), 2)
        opt_values = [opt['value'] for opt in field.options]
        self.assertIn(0, opt_values)
        self.assertIn(1, opt_values)

if __name__ == '__main__':
    unittest.main()
