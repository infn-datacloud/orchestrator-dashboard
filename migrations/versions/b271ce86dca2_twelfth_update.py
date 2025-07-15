"""Twelfth update - Convert selected_template field

Revision ID: b271ce86dca2
Revises: a160bd75dc93
Create Date: 2025-07-04 10:00:00

"""

import os
import sys
from app.extensions import tosca
from app.lib import dbhelpers
from app.lib.strings import notnullorempty


# revision identifiers, used by Alembic.
revision = "b271ce86dca2"
down_revision = "a160bd75dc93"
branch_labels = None
depends_on = None


def upgrade():

    templates = tosca.getinfo()
    deployments = dbhelpers.get_deployments()
    updated_deployments = list()
    for d in deployments:
        template_name = tosca.find_template_name(d.selected_template, d.template, templates)
        if notnullorempty(template_name):
            d.selected_template = template_name
            updated_deployments.append(d)

    if updated_deployments:
        for d in updated_deployments:
            try:
                dbhelpers.add_object(d)
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(str(e), exc_type, fname, exc_tb.tb_lineno)

    # ### end Alembic commands ###


def downgrade():
    templatefilenames = tosca.getfilenames()
    deployments = dbhelpers.get_deployments()
    updated_deployments = list()
    for d in deployments:
        if d.selected_template:
            file_name = templatefilenames.get(d.selected_template)
            d.selected_template = file_name
            updated_deployments.append(d)
    if updated_deployments:
        for d in updated_deployments:
            try:
                dbhelpers.add_object(d)
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(str(e), exc_type, fname, exc_tb.tb_lineno)

    # ### end Alembic commands ###




