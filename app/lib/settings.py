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

from app.extensions import db
from app.lib import dbhelpers, utils, path_utils
from app.models.Setting import Setting
from flask import json

class Settings:
    """
    A class to manage application settings and configuration values.

    This class is responsible for encapsulating various configuration settings used
    throughout the application. It provides a convenient way to access these settings
    and maintain a clear separation between configuration values and application logic.

    Args:
        app (Flask): The Flask application instance to retrieve configuration values.

    Attributes:
        settings_dir (str): The directory path for application settings.
        tosca_dir (str): The directory path for TOSCA templates.
        tosca_params_dir (str): The directory path for TOSCA parameters.
        tosca_metadata_dir (str): The directory path for TOSCA metadata.
        iam_url (str): The IAM base URL.
        iam_client_id (str): The IAM client ID.
        iam_client_secret (str): The IAM client secret.
        iam_groups (list): List of IAM group memberships.
        orchestrator_url (str): The orchestrator's base URL.
        orchestrator_conf (dict): Configuration parameters for the orchestrator, including
            CMDB URL, SLAM URL, IM URL, monitoring URL, and Vault URL.
    """

    _keyiamgroups = "IAM_GROUP_MEMBERSHIP"
    _keyreposconf = "REPOSITORY_CONFIGURATION"
    _keysettingsv = "SETTINGS_VERSION"

    def __init__(self, app):
        temp_settings_dir = app.config.get("SETTINGS_DIR")
        if temp_settings_dir is None:
            raise Exception("SETTINGS_DIR is not defined in configuration")
        self.settings_dir = path_utils.url_path_join(temp_settings_dir, "/")
        temp_tosca_dir = app.config.get("TOSCA_TEMPLATES_DIR")
        if temp_tosca_dir is None:
            raise Exception("TOSCA_TEMPLATES_DIR is not defined in configuration")
        self.tosca_dir = path_utils.url_path_join(temp_tosca_dir, "/")
        self.tosca_params_dir = path_utils.url_path_join(temp_settings_dir, "tosca-parameters")
        self.tosca_metadata_dir = path_utils.url_path_join(temp_settings_dir, "tosca-metadata")
        self.metadata_schema = app.config.get("METADATA_SCHEMA")

        self.iam_url = app.config.get("IAM_BASE_URL")
        self.iam_client_id = app.config.get("IAM_CLIENT_ID")
        self.iam_client_secret = app.config.get("IAM_CLIENT_SECRET")
        self._iam_groups = app.config.get("IAM_GROUP_MEMBERSHIP")

        self.fed_reg_url = app.config.get("FED_REG_URL", None)
        self.use_fed_reg = True if self.fed_reg_url is not None else False

        if not self.use_fed_reg:
            temp_slam_url = app.config.get("SLAM_URL", None)
            if temp_slam_url is not None:
                if not temp_slam_url.endswith("/rest/slam"):
                    temp_slam_url = utils.url_path_join(temp_settings_dir, "/rest/slam")
            self.slam_url = temp_slam_url
            self.cmdb_url = app.config.get("CMDB_URL", None)
        else:
            self.slam_url = None
            self.cmdb_url = None

        self.orchestrator_url = app.config.get("ORCHESTRATOR_URL")

        self.orchestrator_conf = {
            "cmdb_url": self.cmdb_url,
            "slam_url": self.slam_url,
            "im_url": app.config.get("IM_URL"),
            "monitoring_url": app.config.get("MONITORING_URL", ""),
            "vault_url": app.config.get("VAULT_URL"),
            "fed_reg_url": self.fed_reg_url,
        }

    def align_db(self, app):

        # settings version
        self.db_settings_version = dbhelpers.get_setting(self._keysettingsv)
        if not self.db_settings_version:
            # set initial version
            self.db_settings_version = "1"
            self._save_setting(self._keysettingsv, self.db_settings_version)

        # iam groups membership
        db_iam_groups = dbhelpers.get_setting(self._keyiamgroups)
        if not db_iam_groups:
            # get default from config file if present
            config_iam_groups = app.config.get("IAM_GROUP_MEMBERSHIP")
            self._save_setting(self._keyiamgroups, json.dumps(config_iam_groups))

        # repository configuration
        db_repository_configuration = dbhelpers.get_setting(self._keyreposconf)
        if not db_repository_configuration:
            self._save_setting(self._keyreposconf, json.dumps(dict()))

    def _save_setting(self,id,value):
        if dbhelpers.get_setting(id):
            dbhelpers.update_setting(id, dict(value=value))
        else:
            dbhelpers.add_object(Setting(id=id, value=value))

    @property
    def iam_groups(self):
        setting = dbhelpers.get_setting(self._keyiamgroups)
        if setting:
            return json.loads(setting.value)
        return None

    @iam_groups.setter
    def iam_groups(self, value):
        if value:
            self._save_setting(self._keyiamgroups, json.dumps(value))
        else:
            self._save_setting(self._keyiamgroups, None)

    @property
    def repository_configuration(self):
        setting = dbhelpers.get_setting(self._keyreposconf)
        if setting:
            return json.loads(setting.value)
        return None

    @repository_configuration.setter
    def repository_configuration(self, value):
        self._save_setting(self._keyreposconf, json.dumps(value))

