"""Fifth Update.

Revision ID: 98c3d8971d70
Revises: 98c3d8971d6f
Create Date: 2020-04-09
"""
from alembic import op
import sqlalchemy as sa
from app.lib import alembic_helper

# revision identifiers, used by Alembic.
revision = '98c3d8971d70'
down_revision = '98c3d8971d6f'
branch_labels = None
depends_on = None


def upgrade():
    if not alembic_helper.column_exists('deployments', 'template_parameters'):
        op.add_column('deployments', sa.Column('template_parameters', sa.Text, nullable=True))
    if not alembic_helper.column_exists('deployments', 'template_metadata'):
        op.add_column('deployments', sa.Column('template_metadata', sa.Text, nullable=True))
    # ### end Alembic commands ###


def downgrade():
    if alembic_helper.column_exists('deployments', 'template_parameters'):
        op.drop_column('deployments', 'template_parameters')
    if alembic_helper.column_exists('deployments', 'template_metadata'):
        op.drop_column('deployments', 'template_metadata')
    # ### end Alembic commands ###
