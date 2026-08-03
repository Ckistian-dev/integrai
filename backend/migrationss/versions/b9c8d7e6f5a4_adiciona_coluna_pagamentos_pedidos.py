"""Adiciona coluna pagamentos na tabela pedidos

Revision ID: b9c8d7e6f5a4
Revises: f8a9b0c1d2e3
Create Date: 2026-08-03 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9c8d7e6f5a4'
down_revision: Union[str, Sequence[str], None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('pedidos')]
    
    if 'pagamentos' not in columns:
        op.add_column('pedidos', sa.Column('pagamentos', sa.JSON(), nullable=True, server_default='[]'))


def downgrade() -> None:
    op.drop_column('pedidos', 'pagamentos')
