"""Add region_name col to deployment

Revision ID: 9461be74dd62
Revises: 514c0e87e61f
Create Date: 2024-09-26 16:16:44.486790

"""

from alembic import op
import sqlalchemy as sa
from app.lib import alembic_helper

# revision identifiers, used by Alembic.
revision = "9461be74dd62"
down_revision = "514c0e87e61f"
branch_labels = None
depends_on = None


def upgrade():
    if not alembic_helper.column_exists('deployments', 'provider_type'):
        op.add_column("deployments", sa.Column("provider_type", sa.String(length=128), nullable=True))
    if not alembic_helper.column_exists('deployments', 'region_name'):
        op.add_column("deployments", sa.Column("region_name", sa.String(length=128), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    if alembic_helper.column_exists('deployments', 'provider_type'):
        op.drop_column("deployments", "provider_type")
    if alembic_helper.column_exists('deployments', 'region_name'):
        op.drop_column("deployments", "region_name")
    # ### end Alembic commands ###
