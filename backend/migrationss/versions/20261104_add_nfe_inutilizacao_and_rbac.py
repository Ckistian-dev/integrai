"""Adiciona tabela nfe_inutilizacoes e migra permissoes RBAC

Revision ID: 20261104_add_nfe_inutilizacao_and_rbac
Revises: c1d2e3f4a5b6
Create Date: 2026-11-04 14:45:00.000000

"""
from typing import Sequence, Union
import json
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20261104_add_nfe_inutilizacao_and_rbac'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'nfe_inutilizacoes' not in tables:
        op.create_table(
            'nfe_inutilizacoes',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('id_empresa', sa.Integer(), sa.ForeignKey('empresas.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('modelo', sa.String(length=2), nullable=False, server_default='55'),
            sa.Column('serie', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('numero_inicial', sa.Integer(), nullable=False),
            sa.Column('numero_final', sa.Integer(), nullable=False),
            sa.Column('ano', sa.Integer(), nullable=False),
            sa.Column('justificativa', sa.String(length=255), nullable=False),
            sa.Column('cstat', sa.String(length=10), nullable=True),
            sa.Column('xmotivo', sa.String(length=255), nullable=True),
            sa.Column('protocolo', sa.String(length=50), nullable=True),
            sa.Column('data_recebimento', sa.DateTime(), nullable=True),
            sa.Column('xml_retorno', sa.Text(), nullable=True),
            sa.Column('sucesso', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('id_usuario', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        )

    # Migração RBAC: atualizar permissoes de perfis
    perfil_table_name = None
    if 'perfil' in tables:
        perfil_table_name = 'perfil'
    elif 'perfis' in tables:
        perfil_table_name = 'perfis'

    if perfil_table_name:
        res = conn.execute(sa.text(f"SELECT id, permissoes FROM {perfil_table_name}")).fetchall()
        for row in res:
            p_id = row[0]
            permissoes = row[1]
            if isinstance(permissoes, str):
                try:
                    permissoes = json.loads(permissoes)
                except Exception:
                    permissoes = {}
            elif not isinstance(permissoes, dict):
                permissoes = {}

            pedidos_perm = permissoes.get('pedidos')
            if pedidos_perm and (pedidos_perm is True or (isinstance(pedidos_perm, dict) and pedidos_perm.get('acesso'))):
                if 'notas_fiscais' not in permissoes:
                    permissoes['notas_fiscais'] = {'acesso': True}
                    conn.execute(
                        sa.text(f"UPDATE {perfil_table_name} SET permissoes = :perm WHERE id = :id"),
                        {"perm": json.dumps(permissoes), "id": p_id}
                    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'nfe_inutilizacoes' in tables:
        op.drop_table('nfe_inutilizacoes')
