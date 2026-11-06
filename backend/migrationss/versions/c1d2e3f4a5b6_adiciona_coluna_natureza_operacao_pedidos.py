"""Adiciona coluna natureza_operacao na tabela pedidos

Revision ID: c1d2e3f4a5b6
Revises: b9c8d7e6f5a4
Create Date: 2026-11-04 11:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b9c8d7e6f5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('pedidos')]
    
    if 'natureza_operacao' not in columns:
        op.add_column('pedidos', sa.Column('natureza_operacao', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('pedidos', 'natureza_operacao')

