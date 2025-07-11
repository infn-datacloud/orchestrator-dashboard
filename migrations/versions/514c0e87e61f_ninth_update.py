"""Ninth update - add service, users_group and service_access tables

Revision ID: 514c0e87e61f
Revises: 7e9fa167c199
Create Date: 2022-06-09 21:43:03.802422

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '514c0e87e61f'
down_revision = '7e9fa167c199'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('service', if_exists=True)
    op.create_table('service',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=128), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('icon', sa.String(length=128), nullable=False, server_default=""),
    sa.Column('description', sa.String(length=2048), nullable=True),
    sa.Column('visibility', sa.Enum('private', 'public', name='visibility'), nullable=False, server_default='private'),
    sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )
    op.drop_table('users_group', if_exists=True)
    op.create_table('users_group',
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
    op.drop_table('service_access', if_exists=True)
    op.create_table('service_access',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=True),
    sa.Column('group_id', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['users_group.name'], ondelete='cascade'),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ondelete='cascade'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    op.drop_table('service_access', if_exists=True)
    op.drop_table('users_group', if_exists=True)
    op.drop_table('service', if_exists=True)
    # ### end Alembic commands ###
