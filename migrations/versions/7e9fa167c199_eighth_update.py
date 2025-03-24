"""Add user_group column in deployment table

Revision ID: 7e9fa167c199
Revises: a0b6f9dd0342
Create Date: 2021-02-20 19:41:03.825639

"""
from alembic import op
import sqlalchemy as sa
from app.lib import alembic_helper

# revision identifiers, used by Alembic.
revision = '7e9fa167c199'
down_revision = 'a0b6f9dd0342'
branch_labels = None
depends_on = None


def upgrade():
    if not alembic_helper.column_exists('deployments', 'user_group'):
        op.add_column('deployments', sa.Column('user_group', sa.String(length=256), nullable=True))


def downgrade():
    if alembic_helper.column_exists('deployments', 'user_group'):
        op.drop_column('deployments', 'user_group')
