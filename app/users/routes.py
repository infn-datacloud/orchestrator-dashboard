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

import requests
from app.models.User import User
import copy
import io
import os
import random
import re
import string
import uuid as uuid_generator
from typing import Optional
from urllib.parse import urlparse
from distutils.util import strtobool

import openstack
import openstack.connection
import yaml
from flask import (
    Blueprint,
    flash,
    json,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask import current_app as app
from werkzeug.exceptions import Forbidden

from app.extensions import tosca, vaultservice
from app.iam import iam
from app.lib import auth, dbhelpers, fed_reg, providers, s3, utils
from app.lib import openstack as keystone
from app.lib import tosca_info as tosca_helpers
from app.lib.dbhelpers import filter_date_range, build_status_filter
from app.lib.ldap_user import LdapUserManager
from app.models.Deployment import Deployment

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
def show_user(subject, ronly):
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
        excluded_status = "DELETE_COMPLETE"

        if request.method == "POST":
            show_deleted = request.form.to_dict()["showhdep"]

        deployments = []
        try:
            if show_deleted == "False":
                deployments = app.orchestrator.get_deployments(
                    access_token, created_by="{}@{}".format(subject, issuer), excluded_status=excluded_status
                )
            else:
                deployments = app.orchestrator.get_deployments(
                    access_token, created_by="{}@{}".format(subject, issuer)
                )
        except Exception as e:
            flash("Error retrieving deployment list: \n" + str(e), "warning")

        if deployments:
            deployments = dbhelpers.sanitizedeployments(deployments)["deployments"]
            app.logger.debug("Deployments: " + str(deployments))

        return render_template("dep_user.html", user=user, deployments=deployments, showdepdel=show_deleted)
    else:
        flash("User not found!", "warning")
        users = User.get_users()
        return render_template("users.html", users=users)


@users_bp.route("/userstats", methods=["GET", "POST"])
@auth.authorized_with_valid_token
@auth.only_for_admin
def showuserstats():

    access_token = iam.token["access_token"]

    status_labels = ["CREATE_COMPLETE","CREATE_IN_PROGRESS","CREATE_FAILED","UPDATE_COMPLETE","UPDATE_IN_PROGRESS","UPDATE_FAILED","DELETE_COMPLETE","DELETE_IN_PROGRESS","DELETE_FAILED"]
    only_effective = app.config.get("FEATURE_SHOW_BROKEN_DEPLOYMENTS", "no") == "no"
    datestart = None
    dateend = None
    selected_status = "actives"
    if request.method == "POST":
        selected_status = request.form.to_dict()["selected_status"]

    excluded_status = build_status_filter(selected_status, status_labels)

    deployments = []
    try:
        if excluded_status is not None:
            deployments = app.orchestrator.get_deployments(
                access_token, excluded_status=excluded_status
        )
        else:
            deployments = app.orchestrator.get_deployments(
                access_token
        )
    except Exception as e:
        flash("Error retrieving deployment list: \n" + str(e), "warning")

    # sanitize data and filter undesired states
    if deployments:
        deployments = dbhelpers.sanitizedeployments(deployments)["deployments"]

    # Initialize dictionaries for occurrences
    occurrences = dict()

    #filter eventually dates
    deployments =  filter_date_range(
            deployments,
            datestart,
            dateend,
            False)

    # second round, count instances
    for dep in deployments:
        depdate = dep.creation_time.strftime("%Y-%m")
        sub = dep.sub
        datelist = occurrences.get(depdate, list([]))
        if not sub in datelist:
            datelist.append(sub)
            occurrences[depdate] = datelist
    for k in occurrences.keys():
        occurrences[k] = len(occurrences[k])

    s_occurrences = dict(sorted(occurrences.items(), key=lambda item: item[0]))

    s_title = "Users active using all statuses" if selected_status == "all" else "Users active using status: " + selected_status

    return render_template(
        "showuserstats.html",
        s_title=s_title,
        s_labels=list(s_occurrences.keys()),
        s_values=list(s_occurrences.values()),
        status_labels=status_labels,
        selected_status=selected_status
    )

