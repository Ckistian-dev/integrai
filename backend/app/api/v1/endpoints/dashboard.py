from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import date, timedelta
from typing import List, Dict, Any

from app.core.db import models, database
from app.api.dependencies import get_current_active_user

router = APIRouter()

@router.get("/dashboard/stats")
def get_dashboard_stats(
    start_date: date = None,
    end_date: date = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    """
    Retorna estatísticas consolidadas para o dashboard.
    """
    # Padrão: Últimos 30 dias se não informado
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # --- 1. Resumo de Vendas (Receita e Quantidade) ---
    sales_query = db.query(
        func.sum(models.Pedido.total).label("total_revenue"),
        func.count(models.Pedido.id).label("total_orders")
    ).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        models.Pedido.data_emissao >= start_date,
        models.Pedido.data_emissao <= end_date,
        models.Pedido.situacao != models.PedidoSituacaoEnum.cancelado
    ).first()

    total_revenue = float(sales_query.total_revenue or 0)
    total_orders = sales_query.total_orders or 0

    # --- 2. Vendas por Situação (Gráfico de Pizza) ---
    sales_by_status = db.query(
        models.Pedido.situacao,
        func.count(models.Pedido.id).label("count")
    ).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        models.Pedido.data_emissao >= start_date,
        models.Pedido.data_emissao <= end_date
    ).group_by(models.Pedido.situacao).all()

    # --- 3. Resumo Financeiro (A Receber vs A Pagar no período) ---
    financials = db.query(
        models.Conta.tipo_conta,
        func.sum(models.Conta.valor).label("total")
    ).filter(
        models.Conta.id_empresa == current_user.id_empresa,
        models.Conta.situacao != models.ContaSituacaoEnum.cancelado,
        models.Conta.data_vencimento >= start_date,
        models.Conta.data_vencimento <= end_date
    ).group_by(models.Conta.tipo_conta).all()

    to_receive = 0.0
    to_pay = 0.0
    for f in financials:
        if f.tipo_conta == models.ContaTipoEnum.a_receber:
            to_receive = float(f.total or 0)
        elif f.tipo_conta == models.ContaTipoEnum.a_pagar:
            to_pay = float(f.total or 0)

    # --- 4. Pedidos Recentes (Tabela) ---
    recent_orders = db.query(models.Pedido).filter(
        models.Pedido.id_empresa == current_user.id_empresa
    ).order_by(models.Pedido.data_emissao.desc()).limit(5).all()
    
    recent_orders_data = [{
        "id": o.id,
        "cliente": o.cliente.nome_razao if o.cliente else "Consumidor Final",
        "total": float(o.total or 0),
        "situacao": o.situacao.value,
        "data": o.data_emissao
    } for o in recent_orders]

    # --- 5. Estoque Baixo (Alerta) ---
    # Agrupa estoque por produto e soma quantidades
    low_stock_query = db.query(
        models.Produto.sku,
        models.Produto.descricao,
        func.sum(models.Estoque.quantidade).label("total_qty")
    ).join(models.Estoque, models.Estoque.id_produto == models.Produto.id)\
    .filter(models.Produto.id_empresa == current_user.id_empresa)\
    .group_by(models.Produto.id)\
    .having(func.sum(models.Estoque.quantidade) < 10)\
    .limit(5)
    
    low_stock_data = [{"sku": r.sku, "produto": r.descricao, "quantidade": r.total_qty} for r in low_stock_query.all()]

    # --- 6. Evolução de Vendas (Diário) ---
    sales_evolution = db.query(
        models.Pedido.data_emissao,
        func.sum(models.Pedido.total).label("total")
    ).filter(
        models.Pedido.id_empresa == current_user.id_empresa,
        models.Pedido.situacao != models.PedidoSituacaoEnum.cancelado,
        models.Pedido.data_emissao >= start_date,
        models.Pedido.data_emissao <= end_date
    ).group_by(models.Pedido.data_emissao).order_by(models.Pedido.data_emissao).all()

    # --- MOCK DATA (DEV MODE) ---
    # Se não houver vendas (banco vazio), gera dados fictícios para visualização
    # Verifica se a empresa possui algum pedido no histórico total para decidir se exibe mock
    total_orders_global = db.query(func.count(models.Pedido.id)).filter(
        models.Pedido.id_empresa == current_user.id_empresa
    ).scalar() or 0

    print(total_orders_global)

    if total_orders_global < 100:
        import random
        
        # Gera evolução diária baseada no intervalo selecionado
        num_days = (end_date - start_date).days + 1
        mock_evolution = []
        
        for i in range(num_days):
            day = start_date + timedelta(days=i)
            # Valor aleatório entre 1k e 8k para ficar bonito no gráfico
            val = random.uniform(1000, 8000) 
            mock_evolution.append({
                "date": day.strftime("%d/%m"),
                "value": round(val, 2)
            })
            
        mock_revenue = sum(d['value'] for d in mock_evolution)
        
        return {
            "summary": {
                "revenue": mock_revenue,
                "orders": int(num_days * random.uniform(1.5, 4.0)),
                "to_receive": mock_revenue * 0.65,
                "to_pay": mock_revenue * 0.45,
                "net_balance": (mock_revenue * 0.65) - (mock_revenue * 0.45)
            },
            "charts": {
                "orders_by_status": [
                    {"name": "Orçamento", "value": random.randint(10, 30)},
                    {"name": "Aprovação", "value": random.randint(5, 15)},
                    {"name": "Produção", "value": random.randint(8, 25)},
                    {"name": "Expedição", "value": random.randint(3, 10)},
                    {"name": "Faturamento", "value": random.randint(15, 40)},
                ],
                "sales_evolution": mock_evolution
            },
            "recent_orders": [
                {"id": 9005, "cliente": "Tech Demo Ltda", "total": 4500.00, "situacao": "Produção", "data": end_date},
                {"id": 9004, "cliente": "Comércio Exemplo", "total": 1250.50, "situacao": "Faturamento", "data": end_date},
                {"id": 9003, "cliente": "Indústria Mock", "total": 8900.00, "situacao": "Aprovação", "data": end_date - timedelta(days=1)},
                {"id": 9002, "cliente": "Loja Teste", "total": 340.00, "situacao": "Expedição", "data": end_date - timedelta(days=2)},
                {"id": 9001, "cliente": "Cliente Novo", "total": 120.00, "situacao": "Orçamento", "data": end_date - timedelta(days=3)},
            ],
            "low_stock": [
                {"sku": "DEMO-01", "produto": "Produto A (Demo)", "quantidade": 2},
                {"sku": "DEMO-02", "produto": "Produto B (Demo)", "quantidade": 5},
                {"sku": "DEMO-03", "produto": "Produto C (Demo)", "quantidade": 0},
                {"sku": "DEMO-04", "produto": "Produto D (Demo)", "quantidade": 1},
                {"sku": "DEMO-05", "produto": "Produto E (Demo)", "quantidade": 3},
            ]
        }

    return {
        "summary": {
            "revenue": total_revenue,
            "orders": total_orders,
            "to_receive": to_receive,
            "to_pay": to_pay,
            "net_balance": to_receive - to_pay
        },
        "charts": {
            "orders_by_status": [{"name": s[0].value, "value": s[1]} for s in sales_by_status],
            "sales_evolution": [{"date": s.data_emissao.strftime("%d/%m"), "value": float(s.total or 0)} for s in sales_evolution]
        },
        "recent_orders": recent_orders_data,
        "low_stock": low_stock_data
    }