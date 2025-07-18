"""Fourth Update - Add selected_template col to deployments

Revision ID: 98c3d8971d6f
Revises: 98c3d8971d6e
Create Date: 2020-04-02
"""
from alembic import op
import sqlalchemy as sa
from app.lib import alembic_helper

# revision identifiers, used by Alembic.
revision = '98c3d8971d6f'
down_revision = '98c3d8971d6e'
branch_labels = None
depends_on = None


def upgrade():
    if not alembic_helper.column_exists('deployments', 'selected_template'):
        op.add_column('deployments', sa.Column('selected_template', sa.Text, nullable=True))
    # ### end Alembic commands ###


def downgrade():
    if alembic_helper.column_exists('deployments', 'selected_template'):
        op.drop_column('deployments', 'selected_template')
    # ### end Alembic commands ###
