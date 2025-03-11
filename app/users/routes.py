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

import requests
from flask import (
    current_app as app,
    Blueprint,
    session,
    render_template,
    flash,
    request,
)
from app.lib import auth, dbhelpers
from app.lib.dbhelpers import filter_function
from app.models.User import User
from app.iam import iam


users_bp = Blueprint(
    "users_bp", __name__, template_folder="templates", static_folder="static"
)


@users_bp.route("/")
@auth.authorized_with_valid_token
@auth.only_for_admin
def show_users():
    users = dbhelpers.get_users()
    return render_template("users.html", users=users)


@users_bp.route("/<subject>/<ronly>", methods=["GET", "POST"])
@auth.authorized_with_valid_token
@auth.only_for_admin
def show_user(subject,ronly):
    if request.method == "POST":
        # cannot change its own role
        if session["userid"] == subject:
            role = session["userrole"]
        else:
            role = request.form["role"]
        active = request.form["active"]
        # update database
        dbhelpers.update_user(subject, dict(role=role, active=bool(active)))

    user = dbhelpers.get_user(subject)
    if user is not None:
        return render_template("user.html", user=user, ronly=ronly)
    else:
        return render_template(app.config.get("HOME_TEMPLATE"))


@users_bp.route("/<subject>/deployments", methods=["GET", "POST"])
@auth.authorized_with_valid_token
@auth.only_for_admin
def show_deployments(subject):

    access_token = iam.token["access_token"]
    user = dbhelpers.get_user(subject)

    if user is not None:

        issuer = iam.base_url
        if not issuer.endswith("/"):
            issuer += "/"
        show_deleted = "False"
        if request.method == "POST":
            show_deleted = request.form.to_dict()["showhdep"]

        '''
        headers = {"Authorization": "bearer %s" % access_token}

        url = (
            app.settings.orchestrator_url
            + "/deployments?createdBy={}&page={}&size={}".format(
                "{}@{}".format(subject, issuer), 0, 999999
            )
        )
        response = requests.get(url, headers=headers)

        iids = []
        if response.ok:
            deporch = response.json()["content"]
            iids = dbhelpers.updatedeploymentsstatus(deporch, subject)["iids"]

        #
        # retrieve deployments from DB
        deployments = dbhelpers.cvdeployments(dbhelpers.get_user_deployments(user.sub))
        '''

        deployments = []
        try:
            deployments = app.orchestrator.get_deployments(
                access_token, created_by="{}@{}".format(subject, issuer)
            )
        except Exception as e:
            flash("Error retrieving deployment list: \n" + str(e), "warning")

        if deployments:
            result = dbhelpers.sanitizedeployments(deployments)
            deployments = result["deployments"]
            if (show_deleted == "False"):
                deployments = filter_function(deployments,
                                              ["DELETE_COMPLETE", "DELETE_IN_PROGRESS"], False)
            app.logger.debug("Deployments: " + str(deployments))

        return render_template("dep_user.html", user=user, deployments=deployments, showdepdel=show_deleted)
    else:
        flash("User not found!", "warning")
        users = User.get_users()
        return render_template("users.html", users=users)
