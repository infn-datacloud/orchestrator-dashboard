# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2020
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

from app import app
from flask import render_template, session, json
from functools import wraps
import ast
import requests
from . import utils, settings, dbhelpers


def get_access_token(sub):
    user = dbhelpers.get_user(sub)
    if user is not None:
        return user.oauth.token
    return None


def validate_configuration():
    if not settings.orchestratorConf.get('im_url'):
        app.logger.debug("Trying to (re)load config from Orchestrator: " + json.dumps(settings.orchestratorConf))
        access_token = app.get_auth_blueprint().session.token['access_token']
        configuration = utils.getorchestratorconfiguration(settings.orchestratorUrl, access_token)
        settings.orchestratorConf = configuration


def authorized_with_valid_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not app.get_auth_blueprint().session.authorized or 'username' not in session:
            return render_template(app.config.get('HOME_TEMPLATE'))

        if app.get_auth_blueprint().session.token['expires_in'] < 60:
            app.logger.debug("Force refresh token")
            app.get_auth_userinfo()

        validate_configuration()

        return f(*args, **kwargs)

    return decorated_function


def only_for_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session['userrole'].lower() == 'admin':
            return render_template(app.config.get('HOME_TEMPLATE'))

        return f(*args, **kwargs)

    return decorated_function


def exchange_token_with_audience(iam_url, client_id, client_secret, iam_token, audience):

    payload_string = '{ "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange", "audience": "' \
                     + audience + '", "subject_token": "' + iam_token + '", "scope": "openid profile" }'

    # Convert string payload to dictionary
    payload = ast.literal_eval(payload_string)

    iam_response = requests.post(iam_url + "/token", data=payload, auth=(client_id, client_secret), verify=False)

    if not iam_response.ok:
        raise Exception("Error exchanging token: {} - {}".format(iam_response.status_code, iam_response.text))

    deserialized_iam_response = json.loads(iam_response.text)

    return deserialized_iam_response['access_token']
