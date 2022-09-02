# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2020-2021
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
from flask import flash, current_app as app
from flask_dance import OAuth2ConsumerBlueprint
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from app import db
from app.models.OAuth import OAuth
from app.models.User import User
from flask_login import current_user, login_user
from app import app, flaat
from app.lib import utils, dbhelpers, decoders
from flaat import tokentools

from flask import json, session


def create_blueprint():
    egicheckin_base_url = app.config['EGI_AAI_BASE_URL']
    egicheckin_token_url = egicheckin_base_url + '/protocol/openid-connect/token'
    egicheckin_refresh_url = egicheckin_base_url + '/protocol/openid-connect/token'
    egicheckin_authorization_url = egicheckin_base_url + '/protocol/openid-connect/auth'

    return OAuth2ConsumerBlueprint(
        "egiaai", __name__,
        client_id=app.config['EGI_AAI_CLIENT_ID'],
        client_secret=app.config['EGI_AAI_CLIENT_SECRET'],
        auto_refresh_kwargs={
            "client_id": app.config['EGI_AAI_CLIENT_ID'],
            "client_secret": app.config['EGI_AAI_CLIENT_SECRET'],
        },
        base_url=egicheckin_base_url,
        token_url=egicheckin_token_url,
        auto_refresh_url=egicheckin_refresh_url,
        authorization_url=egicheckin_authorization_url,
        scope=['openid', 'profile', 'email', 'offline_access', 'eduperson_entitlement'],
        redirect_to='home',
        storage=SQLAlchemyStorage(OAuth, db.session, user=current_user)
    )

def auth_blueprint_login(blueprint, token):
    if not token:
        flash("Failed to log in with EGI Checkin.", category="error")
        return False

    account_info = blueprint.session.get('/auth/realms/egi/protocol/openid-connect/userinfo')
    jwt = tokentools.get_accesstoken_info(token['access_token'])

    if not account_info.ok:
        msg = "Failed to fetch user info."
        flash(msg, category="error")
        return False

    user_id = jwt['body']['sub']
    issuer = jwt['body']['iss']

    account_info_json = account_info.json()
    session['userid'] = user_id  # account_info_json['sub']
    session['username'] = account_info_json['preferred_username']
    email = account_info_json['email']
    session['useremail'] = email
    admins = json.dumps(app.config['ADMINS'])
    role = 'admin' if email in admins else 'user'
    session['userrole'] = role
    session['gravatar'] = utils.avatar(account_info_json['email'], 26)
    session['organisation_name'] = user_id.split('@')[1]

    info = flaat.get_info_from_userinfo_endpoints(token['access_token'])
    groups = decoders.EgiTokenDecoder.get_groups(info)
    session['usergroups'] = groups

    # check database
    # if user not found, insert
    #
    app.logger.info(dir(User))
    user = dbhelpers.get_user(account_info_json['sub'])
    if user is None:
        user = User(sub=user_id,
                    name=account_info_json['name'],
                    username=account_info_json['preferred_username'],
                    given_name=account_info_json['given_name'],
                    family_name=account_info_json['family_name'],
                    email=email,
                    organisation_name=user_id.split('@')[1],
                    picture=utils.avatar(email, 26),
                    role=role,
                    active=1)
        dbhelpers.add_object(user)

    # session['userrole'] = user.role  # role

    # Find this OAuth token in the database, or create it
    oauth = OAuth.query.filter_by(
        provider=blueprint.name,
        provider_user_id=user_id,
    ).first()

    if not oauth:
        oauth = OAuth(provider=blueprint.name,
                      provider_user_id=user_id,
                      token=token,
                      issuer=issuer)
    else:
        oauth.token = token  # store token

    if not oauth.user:
        oauth.user = user

    dbhelpers.add_object(oauth)
    login_user(oauth.user)
    # flash("Successfully signed in.")

    return False
