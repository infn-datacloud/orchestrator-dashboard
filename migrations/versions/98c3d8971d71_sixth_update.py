"""Sixth Update - Add deployment_type col to deployments

Revision ID: 98c3d8971d71
Revises: 98c3d8971d70
Create Date: 2020-04-23
"""
from alembic import op
import sqlalchemy as sa
from app.lib import alembic_helper

# revision identifiers, used by Alembic.
revision = '98c3d8971d71'
down_revision = '98c3d8971d70'
branch_labels = None
depends_on = None


def upgrade():
    if not alembic_helper.column_exists('deployments', 'deployment_type'):
        op.add_column('deployments', sa.Column('deployment_type', sa.String(length=16), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    if alembic_helper.column_exists('deployments', 'deployment_type'):
        op.drop_column('deployments', 'deployment_type')
    # ### end Alembic commands ###
