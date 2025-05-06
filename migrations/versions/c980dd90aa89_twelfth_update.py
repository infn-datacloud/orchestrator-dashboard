"""Tewlfth update - Remove users/deployments relations and fk

Revision ID: c980dd90aa89
Revises: a160bd75dc93
Create Date: 2025-05-06 12:38:00

"""
from alembic import op
import sqlalchemy as sa
from app.lib import alembic_helper

# revision identifiers, used by Alembic.
revision = "c980dd90aa89"
down_revision = "a160bd75dc93"
branch_labels = None
depends_on = None


def upgrade():
    keyname = alembic_helper.fk_exists('deployments', 'users', ['sub'], ['sub'])
    if keyname:
        op.drop_constraint(keyname, 'deployments', type_='foreignkey')
    # ### end Alembic commands ###


def downgrade():
    keyname = alembic_helper.fk_exists('deployments', 'users', ['sub'], ['sub'])
    if not keyname:
        op.create_foreign_key(None, 'deployments', 'users', ['sub'], ['sub'])
    # ### end Alembic commands ###





