"""Atualização 1 (CORRIGIDA)

Revision ID: cf3b1c16751c
Revises: 39e6e0702a6c
Create Date: 2025-11-06 14:10:00.000000 
"""
from alembic import op
import sqlalchemy as sa

# --- INÍCIO DA CORREÇÃO ---

# O nome do tipo ENUM no Postgres
enum_name = 'cadastroindicadorieenum'

# OS VALORES CORRETOS (strings) como definidos no models.py
enum_values_corretos = ('0', '1', '2', '9')
enum_type_correto = sa.Enum(*enum_values_corretos, name=enum_name)

# OS VALORES INCORRETOS (que eu sugeri antes, para podermos limpar)
# Isso é necessário caso o upgrade anterior tenha falhado e deixado o tipo "ruim" no banco
enum_values_incorretos = ('nao_se_aplica', 'contribuinte_icms', 'isento', 'nao_contribuinte')
enum_type_incorreto = sa.Enum(*enum_values_incorretos, name=enum_name)

# --- FIM DA CORREÇÃO ---


# revision identifiers, used by Alembic.
revision = 'cf3b1c16751c'
# O 'down_revision' deve ser o ID da migração ANTERIOR a esta
# Verifique no nome do seu arquivo, o meu log dizia:
down_revision = '39e6e0702a6c' 
branch_labels = None
depends_on = None


def upgrade():
    # === PASSO 1: Limpar o ENUM incorreto, se ele existir ===
    # O upgrade anterior falhou, então podemos ter um enum "ruim" no banco
    # Vamos tentar dropar o enum com os valores ruins (texto), se existir.
    enum_type_incorreto.drop(op.get_bind(), checkfirst=True)
    
    # === PASSO 2: Criar o tipo ENUM CORRETO no PostgreSQL ===
    # Agora criamos o tipo com os valores corretos ("0", "1", "2", "9")
    enum_type_correto.create(op.get_bind(), checkfirst=True)
    
    # === PASSO 3: Alterar a coluna, usando os valores corretos ('2' e '9') ===
    # Assumindo que:
    #   true  (Boolean) -> '2' (isento)
    #   false (Boolean) -> '9' (nao_contribuinte)
    op.alter_column('cadastros', 'indicador_ie',
           existing_type=sa.BOOLEAN(),
           type_=enum_type_correto, # Usa o tipo CORRETO
           existing_nullable=False,
           # A lógica USING está correta, ela só falhou porque o ENUM estava errado
           postgresql_using="CASE WHEN indicador_ie = true THEN '2'::cadastroindicadorieenum ELSE '9'::cadastroindicadorieenum END"
    )
    
    # Altera o default no nível do banco (o seu default no models.py é '9')
    op.alter_column('cadastros', 'indicador_ie', server_default='9')


def downgrade():
    # === PASSO 1: Alterar a coluna de volta para BOOLEAN ===
    # Lógica reversa: se for '2', volta para TRUE, senão vira FALSE.
    op.alter_column('cadastros', 'indicador_ie',
           existing_type=enum_type_correto, # Usa o tipo CORRETO
           type_=sa.BOOLEAN(),
           existing_nullable=False,
           # Converte de volta para booleano
           postgresql_using="(indicador_ie::text = '2')"
    )
    
    # === PASSO 2: Remover o tipo ENUM CORRETO do banco ===
    enum_type_correto.drop(op.get_bind(), checkfirst=True)
    
    # Limpa o server_default
    op.alter_column('cadastros', 'indicador_ie', server_default=None)