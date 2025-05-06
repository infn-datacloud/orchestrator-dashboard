from alembic import op
from sqlalchemy import inspect, Table, MetaData

def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)

def fk_exists(table_name, destination_table, column_names, referred_column_names):
    bind = op.get_context().bind
    insp = inspect(bind)
    foreign_keys = insp.get_foreign_keys(table_name)
    for kf in foreign_keys:
        if kf['referred_table'] == destination_table and \
            set(column_names).intersection(kf['constrained_columns']) == set(column_names) and \
                set(referred_column_names).intersection(kf['referred_columns']) == set(referred_column_names):
            return kf['name']
    return None
