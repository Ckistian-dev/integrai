import sys
import os
from decimal import Decimal

# Adiciona o diretório /app ao sys.path para importar os módulos corretos
sys.path.append('/app')

from app.core.db.database import SessionLocal
from app.core.db import models
from app.core.service.nfe_service import NFeService, safe_decimal

def test_calculation():
    db = SessionLocal()
    try:
        # Busca o pedido complementar
        pedido = db.query(models.Pedido).filter(models.Pedido.id == 2192).first()
        if not pedido:
            print("Erro: Pedido 2192 não encontrado!")
            return

        print(f"=== TESTANDO PEDIDO #{pedido.id} ===")
        print(f"Tipo de Operação do Pedido: {pedido.tipo_operacao}")
        print(f"Total do Pedido no Banco: {pedido.total}")
        print(f"Itens do Pedido:")
        for idx, item in enumerate(pedido.itens):
            print(f"  Item {idx}: {item}")

        service = NFeService(db, pedido.id_empresa)
        
        # Simula as variáveis do emitente e destinatário
        crt_val = '3'  # Lucro Real (Regime Normal)
        uf_empresa = 'PR'  # Paraná
        
        cliente = db.query(models.Cadastro).filter(models.Cadastro.id == pedido.id_cliente).first()
        uf_cliente = cliente.estado.value if hasattr(cliente.estado, 'value') else cliente.estado
        
        ind_destino = 1  # Interna
        if uf_empresa != uf_cliente:
            ind_destino = 2  # Interestadual
            
        print(f"UF Empresa: {uf_empresa} | UF Cliente: {uf_cliente} | Destino: {'Interestadual' if ind_destino == 2 else 'Interno'}")

        # Simula o pré-cálculo
        total_produtos_pedido = Decimal('0.00')
        lista_itens = pedido.itens or []
        tipo_op_enum = pedido.tipo_operacao
        
        for item in lista_itens:
            qtd = safe_decimal(item.get('quantidade', 0))
            valor_unit = safe_decimal(item.get('valor_unitario', 0))
            subtotal = safe_decimal(item.get('subtotal'))
            total_com_ipi = safe_decimal(item.get('total_com_ipi'))
            
            if tipo_op_enum == models.RegraTipoOperacaoEnum.complemento:
                if subtotal > 0:
                    v_item = subtotal
                elif total_com_ipi > 0:
                    v_item = total_com_ipi
                else:
                    v_item = (qtd * valor_unit).quantize(Decimal('0.01'))
                
                if v_item == 0 and len(lista_itens) == 1 and pedido.total and pedido.total > 0:
                    v_item = safe_decimal(pedido.total)
            else:
                v_item = (qtd * valor_unit).quantize(Decimal('0.01'))
            total_produtos_pedido += v_item
            
        print(f"Total Produtos Pedido (Pré-cálculo): {total_produtos_pedido}")

        # Simula o loop principal
        for i, item in enumerate(lista_itens):
            prod_id = item.get('id_produto') or item.get('produto_id')
            produto_db = db.query(models.Produto).filter(models.Produto.id == prod_id).first()
            
            if not produto_db:
                print(f"Produto ID {prod_id} não encontrado!")
                continue
                
            qtd = safe_decimal(item.get('quantidade'))
            valor_unit = safe_decimal(item.get('valor_unitario'))
            subtotal = safe_decimal(item.get('subtotal'))
            total_com_ipi = safe_decimal(item.get('total_com_ipi'))
            
            if tipo_op_enum == models.RegraTipoOperacaoEnum.complemento:
                if subtotal > 0:
                    valor_total = subtotal
                elif total_com_ipi > 0:
                    valor_total = total_com_ipi
                else:
                    valor_total = (qtd * valor_unit).quantize(Decimal('0.01'))
                
                if valor_total == 0 and len(lista_itens) == 1 and pedido.total and pedido.total > 0:
                    valor_total = safe_decimal(pedido.total)
            else:
                valor_total = (qtd * valor_unit).quantize(Decimal('0.01'))
                
            print(f"\n--- Item {i+1} ({produto_db.sku}) ---")
            print(f"Qtd: {qtd} | Valor Unit: {valor_unit} | Subtotal: {subtotal} | Total Com IPI: {total_com_ipi}")
            print(f"Valor Total do Item Definido: {valor_total}")
            
            # Busca Regra
            regra = service._encontrar_regra_tributaria(produto_db, cliente, tipo_op_enum)
            if not regra and tipo_op_enum in [models.RegraTipoOperacaoEnum.devolucao_entrada, models.RegraTipoOperacaoEnum.devolucao_saida, models.RegraTipoOperacaoEnum.complemento]:
                print("Buscando regra de Venda em fallback...")
                regra = service._encontrar_regra_tributaria(produto_db, cliente, models.RegraTipoOperacaoEnum.venda_mercadoria)
                
            if not regra:
                print("WARNING: Nenhuma regra tributária encontrada!")
                continue
                
            print(f"Regra Encontrada ID: {regra.id}")
            print(f"Regra ICMS CST: {regra.icms_cst}")
            
            # Resolve Alíquota e ICMS CST
            icms_cst_val = regra.icms_cst.value if regra.icms_cst else '40'
            aliq_intra = Decimal('0.00')
            aliq_inter = Decimal('0.00')
            
            # Simula resolução do JSON
            if regra.regras_uf:
                padrao_uf = regra.regras_uf.get('padrao_uf', {}) if 'padrao_uf' in regra.regras_uf else regra.regras_uf
                dados_uf = padrao_uf.get(uf_cliente, {})
                if dados_uf:
                    aliq_intra = safe_decimal(dados_uf.get('aliq_intra', 0))
                    aliq_inter = safe_decimal(dados_uf.get('aliq_inter', 0))
            
            aliq_inter_padrao = service._get_aliquota_interestadual(uf_empresa, uf_cliente, '0')
            if aliq_inter == 0:
                aliq_inter = aliq_inter_padrao
                
            aliquota_final_item = aliq_inter if ind_destino == 2 else (aliq_intra if aliq_intra > 0 else Decimal('0.00'))
            
            print(f"Aliq Intra: {aliq_intra}% | Aliq Inter: {aliq_inter}% | Alíquota Final: {aliquota_final_item}%")
            
            # Destaque de imposto passado no faturamento do frontend
            # O modal de faturamento do frontend pode enviar aliquota_final_item ou usar o da regra
            # Vamos ver se o item do pedido tinha aliq_icms
            aliquota_front = item.get('aliq_icms')
            print(f"Alíquota no Item (Front): {aliquota_front}")
            
            # No código de emitir_nfe:
            # aliquota_final_item = safe_decimal(item.get('aliq_icms'))
            # Se for nula, usa aliquota_final_item do cálculo da regra.
            
            # Cálculos finais
            base_icms = valor_total  # Simples, sem frete/ipi para o teste
            val_icms_operacao = service._calc_valor(base_icms, aliquota_final_item)
            val_icms = val_icms_operacao
            
            print(f"Calculado: Base ICMS = {base_icms} | Val ICMS = {val_icms}")
            
            v_bc_normal = base_icms
            v_icms_normal = val_icms
            p_icms_normal = aliquota_final_item
            
            print(f"Resultado Normal: v_bc_normal={v_bc_normal} | v_icms_normal={v_icms_normal} | p_icms_normal={p_icms_normal}")
            
    finally:
        db.close()

if __name__ == '__main__':
    test_calculation()
