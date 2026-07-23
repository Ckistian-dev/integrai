"""Adiciona tabela atendai_configuracoes

Revision ID: f8a9b0c1d2e3
Revises: 5809b558ec78
Create Date: 2026-07-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.core.db.types


# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = '5809b558ec78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'atendai_configuracoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url_webhook', sa.String(), nullable=False),
        sa.Column('webhook_token', app.core.db.types.EncryptedString(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True, default=True),
        sa.Column('id_empresa', sa.Integer(), sa.ForeignKey('empresas.id'), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_atendai_configuracoes_id'), 'atendai_configuracoes', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_atendai_configuracoes_id'), table_name='atendai_configuracoes')
    op.drop_table('atendai_configuracoes')
