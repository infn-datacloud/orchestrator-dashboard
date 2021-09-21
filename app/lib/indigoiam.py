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
from flaat import tokentools
from flask import current_app as app, flash
from flask_dance import OAuth2ConsumerBlueprint
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from app import db
from flask_login import current_user, login_user
from app import app
from app.lib import utils,  settings, dbhelpers
from app.models.OAuth import OAuth
from app.models.User import User
from markupsafe import Markup
from werkzeug.exceptions import Forbidden
from flask import  json, session


def create_blueprint():
    iam_base_url = app.config['IAM_BASE_URL']
    iam_token_url = iam_base_url + '/token'
    iam_refresh_url = iam_base_url + '/token'
    iam_authorization_url = iam_base_url + '/authorize'

    return OAuth2ConsumerBlueprint(
    "iam", __name__,
    client_id=app.config['IAM_CLIENT_ID'],
    client_secret=app.config['IAM_CLIENT_SECRET'],
    scope=['openid', 'profile', 'email', 'offline_access'],
    base_url=iam_base_url,
    token_url=iam_token_url,
    auto_refresh_url=iam_refresh_url,
    authorization_url=iam_authorization_url,
    redirect_to='home',
    storage=SQLAlchemyStorage(OAuth, db.session, user=current_user)
  )


def auth_blueprint_login(blueprint, token):
    if not token:
        flash("Failed to log in with IAM.", category="error")
        return False

    account_info = blueprint.session.get('/userinfo')
    jwt = tokentools.get_accesstoken_info(token['access_token'])

    if not account_info.ok:
        msg = "Failed to fetch user info."
        flash(msg, category="error")
        return False

    user_id = jwt['body']['sub']
    issuer = jwt['body']['iss']

    account_info_json = account_info.json()
    user_groups = account_info_json['groups']

    if settings.iamGroups:
        if set(settings.iamGroups) & set(user_groups) == set():
            app.logger.debug("No match on group membership. User group membership: "
                             + json.dumps(user_groups))
            message = Markup(
                'Your identity has been verified successfully, but you are not authorized to access the services.<br>' +
                'Please, contact the administrators ({}) in order to get proper permissions'.format(
                    app.config.get('SUPPORT_EMAIL')))
            raise Forbidden(description=message)

    session['userid'] = user_id  #account_info_json['sub']
    session['username'] = account_info_json['name']
    session['useremail'] = account_info_json['email']
    session['userrole'] = 'user'
    session['gravatar'] = utils.avatar(account_info_json['email'], 26)
    session['organisation_name'] = account_info_json['organisation_name']
    session['usergroups'] = account_info_json['groups']

    # check database
    # if user not found, insert
    #
    app.logger.info(dir(User))
    user = dbhelpers.get_user(account_info_json['sub'])
    if user is None:
        email = account_info_json['email']
        admins = json.dumps(app.config['ADMINS'])
        role = 'admin' if email in admins else 'user'

        user = User(sub=account_info_json['sub'],
                    name=account_info_json['name'],
                    username=account_info_json['preferred_username'],
                    given_name=account_info_json['given_name'],
                    family_name=account_info_json['family_name'],
                    email=email,
                    organisation_name=account_info_json['organisation_name'],
                    picture=utils.avatar(email, 26),
                    role=role,
                    active=1)
        dbhelpers.add_object(user)

    session['userrole'] = user.role  # role

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
        oauth.token = token #store token

    if not oauth.user:
        oauth.user = user
        dbhelpers.add_object(oauth)

    login_user(oauth.user)
    # flash("Successfully signed in.")

    return False





