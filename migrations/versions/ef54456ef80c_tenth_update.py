"""tenth update

Revision ID: ef54456ef80c
Revises: 514c0e87e61f
Create Date: 2023-10-26 10:41:53.725316

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'ef54456ef80c'
down_revision = '514c0e87e61f'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('deployments', 'vault_secret_key',
               existing_type=mysql.VARCHAR(length=36),
               type_=sa.Text())

def downgrade():
    op.alter_column('deployments', 'vault_secret_key',
               existing_type=sa.Text(),
               type_=mysql.VARCHAR(36))
