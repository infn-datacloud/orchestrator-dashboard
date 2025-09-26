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

from flask import g
from flask_dance.consumer import OAuth2ConsumerBlueprint
from werkzeug.local import LocalProxy
import requests


def make_iam_blueprint(
    client_id=None, client_secret=None, base_url=None, redirect_to=None, scope=[]
):
    """
    Create an OAuth2 blueprint for integrating with an IAM service.

    This function creates an OAuth2 blueprint using Flask-Dance for integrating your
    application with an Identity and Access Management (IAM) service. It allows users
    to log in and authorize your application to access their IAM data. You can provide
    the necessary configuration parameters to establish the connection with the IAM
    service.

    Args:
        client_id (str, optional): The client ID for your application.
        client_secret (str, optional): The client secret for your application.
        base_url (str, optional): The base URL for the IAM service.
        token_url (str, optional): The URL to obtain OAuth2 tokens.
        auto_refresh_url (str, optional): The URL to automatically refresh tokens.
        authorization_url (str, optional): The URL to initiate the OAuth2 authorization process.
        redirect_to (str, optional): The URL to redirect to after successful authentication.

    Returns:
        OAuth2ConsumerBlueprint: A Flask-Dance OAuth2 blueprint for IAM integration.
    """

    # get iam token and authorization url
    response = requests.get(base_url + "/.well-known/openid-configuration")
    
    if response.status_code != 200:
        token_url = base_url + "/token"
        authorization_url = base_url + "/authorize"
    else:
        token_url = response.json().get("token_endpoint", base_url + "/token")
        authorization_url = response.json().get("authorization_endpoint", base_url + "/authorization")

    # initialize the OAuth2 blueprint
    iam_bp = OAuth2ConsumerBlueprint(
        "iam",
        __name__,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        token_url=token_url,
        auto_refresh_url=token_url,
        authorization_url=authorization_url,
        redirect_to=redirect_to,
        scope=scope,
    )

    @iam_bp.before_app_request
    def set_applocal_session():
        g.flask_dance_iam = iam_bp.session

    return iam_bp


def get_current_iam():
    return iam.base_url


def get_all_groups():

    itemsPerPage = 10
    startIndex = 1
    totalGroups = 0
    params = []
    groups = list()

    try:
        while True:
            params.append("startIndex={}".format(startIndex))
            params.append("itemsPerPage={}".format(itemsPerPage))
            str_params = "?{}".format("&".join(params))
            url = f"/iam/group/search{str_params}"
            response = iam.get(url)
            response.raise_for_status()
            totalResults = int(response.json()["totalResults"])
            resources = response.json()["Resources"]
            for r in resources:
                if r["meta"]["resourceType"] == "Group":
                    groupName = r["displayName"]
                    if groupName not in groups:
                        groups.append(groupName)
                totalGroups+=1
            if totalGroups < totalResults:
                startIndex += itemsPerPage
                params.clear()
            else:
                break
    except Exception as e:
        raise Exception("Error retrieving IAM groups list: {}".format(str(e)))
    return groups


iam = LocalProxy(lambda: g.flask_dance_iam)
