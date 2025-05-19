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

from app.models.User import User
from flask import (
    Blueprint,
    flash,
    render_template,
    request,
    session,
)
from flask import current_app as app

from app.iam import iam
from app.lib import auth, dbhelpers, fed_reg, providers, s3, utils
from app.lib.dbhelpers import month_boundary, filter_date_range, build_excludedstatus_filter, nullorempty, notnullorempty, get_all_statuses

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


@users_bp.route("/userstats", methods=["GET", "POST"])
@auth.authorized_with_valid_token
@auth.only_for_admin
def showuserstats():

    access_token = iam.token["access_token"]

    only_effective = app.config.get("FEATURE_SHOW_BROKEN_DEPLOYMENTS", "no") == "no"
    datestart = None
    dateend = None
    selected_status = "actives"
    if request.method == "POST":
        selected_status = request.form.to_dict()["selected_status"]
        datestart = request.form.to_dict()["start_date"]
        dateend = request.form.to_dict()["end_date"]

    if nullorempty(datestart):
        datestart = None
    if nullorempty(dateend):
        dateend = None

    excluded_status = build_excludedstatus_filter(selected_status)

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
    hasfilterdate = False

    # filter eventually dates
    if notnullorempty(datestart) or notnullorempty(dateend):
        dstart = month_boundary(datestart, True)
        dend = month_boundary(dateend, False)
        hasfilterdate = True
        deployments =  filter_date_range(
                deployments,
                dstart,
                dend,
                True)

    # second round, count instances
    for dep in deployments:
        depdate = dep.creation_time.strftime("%Y-%m")
        sub = dep.sub
        datelist = occurrences.get(depdate, dict({}))
        if not sub in datelist:
            datelist[sub] = 1
        else:
            datelist[sub] = datelist[sub]  + 1
        occurrences[depdate] = datelist

    s_occurrences = dict(sorted(occurrences.items(), key=lambda item: item[0]))
    k_occurrences = list(s_occurrences.keys())
    v_occurrences = list()
    for k in s_occurrences.values():
        v = 0
        for j in k.values():
            v = v+j
        v_occurrences.append(v)

    # get default date interval if not user defined
    if not hasfilterdate and len(s_occurrences) > 0:
        kocc = list(k_occurrences)
        datestart = kocc[0]
        dateend = kocc[len(kocc)-1]

    # get users list and count deployments
    s_users = dict()
    o_users = dict()
    for occurrence in s_occurrences.values():
        for keyu, c in occurrence.items():
            if not keyu in s_users:
                s_users[keyu] = 0
            s_users[keyu] = s_users[keyu] + c
            if not keyu in o_users:
                user = dbhelpers.get_user(keyu)
                o_users[keyu] = user

    s_title = "Active users over time for all statuses" if selected_status == "all" else "Active users over time for status: " + selected_status

    return render_template(
        "showuserstats.html",
        s_title=s_title,
        s_labels=list(k_occurrences),
        s_values=list(v_occurrences),
        status_labels=get_all_statuses(),
        selected_status=selected_status,
        datestart=datestart,
        dateend=dateend,
        s_users=s_users,
        o_users=o_users.values()
    )

