"""Estoque ledger: add observacoes column and update situacao enum

Revision ID: a1b2c3d4e5f6
Revises: 5809b558ec78
Create Date: 2026-04-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5809b558ec78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Adiciona a coluna 'observacoes' na tabela 'estoques' (se não existir).
    2. Atualiza os valores do enum de situacao para o novo padrão de ledger:
       Disponivel -> Entrada, Reservado -> Entrada, Indisponível -> Saída
       e adiciona o valor 'Inventário'.
    Como o campo é VARCHAR (native_enum=False), basta fazer UPDATE dos valores existentes.
    """
    # Adiciona a coluna observacoes se ela ainda não existir
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('estoques')]
    
    if 'observacoes' not in columns:
        op.add_column('estoques', sa.Column('observacoes', sa.Text(), nullable=True))
    
    # Migra os valores antigos do enum para os novos valores
    # Disponivel -> Entrada
    conn.execute(sa.text(
        "UPDATE estoques SET situacao = 'Entrada' WHERE situacao IN ('Disponivel', 'disponivel', 'Disponível')"
    ))
    # Reservado -> Entrada (era um status de lote, não de movimento, vira entrada por padrão)
    conn.execute(sa.text(
        "UPDATE estoques SET situacao = 'Entrada' WHERE situacao IN ('Reservado', 'reservado')"
    ))
    # Indisponível -> Saída
    conn.execute(sa.text(
        "UPDATE estoques SET situacao = 'Saída' WHERE situacao IN ('Indisponível', 'indisponivel', 'Indisponivel')"
    ))


def downgrade() -> None:
    """Reverte: remove a coluna observacoes. Os valores de enum não são revertidos."""
    op.drop_column('estoques', 'observacoes')
