# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Optional

from flask import current_app as app
from flask import flash

from app.lib import fed_reg
from app.providers import sla


def getslas(*, access_token: str):
    slas = []
    try:
        # Fed-Reg
        if app.settings.use_fed_reg:
            app.logger.debug("FED_REG_URL: {}".format(app.settings.fed_reg_url))
            slas = fed_reg.retrieve_slas_from_active_user_group(
                access_token=access_token
            )
        # SLAM
        elif app.settings.slam_url is not None and app.settings.cmdb_url is not None:
            app.logger.debug("SLAM_URL: {}".format(app.settings.slam_url))
            slas = sla.get_slas(
                access_token,
                app.settings.slam_url,
                app.settings.cmdb_url,
            )
        app.logger.debug("SLAs: {}".format(slas))

    except Exception as e:
        flash("Error retrieving SLAs list: \n" + str(e), "warning")

    return slas


def getslasdt(
    *, access_token: str, service_type: Optional[str] = "compute", deployment_type: str
):
    slas = []
    try:
        # Fed-Reg
        if app.settings.use_fed_reg:
            app.logger.debug("FED_REG_URL: {}".format(app.settings.fed_reg_url))
            slas = fed_reg.retrieve_slas_from_active_user_group(
                access_token=access_token,
                service_type=service_type,
                deployment_type=deployment_type,
            )
        # SLAM
        elif app.settings.slam_url is not None and app.settings.cmdb_url is not None:
            app.logger.debug("SLAM_URL: {}".format(app.settings.slam_url))
            slas = sla.get_slas(
                access_token,
                app.settings.slam_url,
                app.settings.cmdb_url,
                deployment_type,
            )
        app.logger.debug("SLAs: {}".format(slas))
    except Exception as e:
        flash("Error retrieving SLAs list: \n" + str(e), "warning")

    return slas
