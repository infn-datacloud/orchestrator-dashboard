"""Eleventh update - Add settings table

Revision ID: a160bd75dc93
Revises: 9461be74dd62
Create Date: 2025-03-21 15:36:00

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a160bd75dc93"
down_revision = "9461be74dd62"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('settings', if_exists=True)
    op.create_table('settings',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('value', sa.Text, nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    op.drop_table('settings', if_exists=True)
    # ### end Alembic commands ###




