
"""Ninth Update

Revision ID: a0c034ff9873
Revises: a0b6f9dd0342
Create Date: 2021-09-07 15:00:00.192947

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a0c034ff9873'
down_revision = '7e9fa167c199'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.drop_constraint('deployments_ibfk_1', 'deployments', type_='foreignkey')
    except:
        pass
    op.alter_column('deployments', 'sub',
               existing_type=mysql.VARCHAR(length=36),
               type_=mysql.VARCHAR(length=256),
               nullable=False)
    op.alter_column('users', 'sub',
               existing_type=mysql.VARCHAR(length=36),
               type_=mysql.VARCHAR(length=256),
               nullable=False)
    op.create_foreign_key('deployments_ibfk_1', 'deployments', 'users', ['sub'], ['sub'])
    op.create_table('flask_dance_oauth',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('provider', sa.String(length=50), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('token', sqlalchemy_utils.types.json.JSONType(), nullable=False),
                    sa.Column('provider_user_id', sa.String(length=256), nullable=False),
                    sa.Column('user_id', sa.String(length=256), nullable=False),
                    sa.Column('issuer', sa.String(length=50), nullable=False),
                    sa.ForeignKeyConstraint(['user_id'], ['users.sub'], ),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('provider', 'provider_user_id')
                    )

    # ### end Alembic commands ###


def downgrade():
    op.drop_table('flask_dance_oauth')
    try:
        op.drop_constraint('deployments_ibfk_1', 'deployments', type_='foreignkey')
    except:
        pass
    op.alter_column('deployments', 'sub',
               existing_type=mysql.VARCHAR(length=256),
               type_=mysql.VARCHAR(length=36),
               nullable=False)
    op.alter_column('users', 'sub',
               existing_type=mysql.VARCHAR(length=256),
               type_=mysql.VARCHAR(length=36),
               nullable=False)
    op.create_foreign_key('deployments_ibfk_1', 'deployments', 'users', ['sub'], ['sub'])
    # ### end Alembic commands ###

