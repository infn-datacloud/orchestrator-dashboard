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

import copy
import datetime
import io
import os
import random
import re
import string
import uuid as uuid_generator
from typing import Optional
from urllib.parse import urlparse

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
from app.lib import (
    auth,
    dbhelpers,
    fed_reg,
    path_utils,
    providers,
    s3,
    utils
)
from app.lib import openstack as keystone
from app.lib import tosca_info as tosca_helpers
from app.lib.dbhelpers import (
    filter_provider,
    filter_group,
    filter_template,
    filter_date_range,
    build_excludedstatus_filter,
    get_all_statuses,
    nullorempty,
    notnullorempty,
    month_boundary,
    months_list
)
from app.lib.ldap_user import LdapUserManager
from app.models.Deployment import Deployment

# Initialize and turn on debug logging
openstack.enable_logging(debug=True)

deployments_bp = Blueprint(
    "deployments_bp", __name__, template_folder="templates", static_folder="static"
)

SHOW_HOME_ROUTE = "home_bp.portfolio"
SHOW_DEPLOYMENTS_ROUTE = "deployments_bp.showdeployments"
SHOW_DEPLOYMENTS_KWARGS = {
    "subject": "me",
    "showback": "False"
}
SHOW_ALLDEPLOYMENTS_ROUTE = "deployments_bp.showalldeployments"
SHOW_ALLDEPLOYMENTS_KWARGS = {
    "showback": "False"
}
MANAGE_RULES_ROUTE = "deployments_bp.manage_rules"
LOGIN_ROUTE = "home_bp.login"


def get_deployments_kwargs(subject):
    kwargs = SHOW_DEPLOYMENTS_KWARGS.copy()
    if subject != session["userid"]:
        kwargs["subject"] = subject
    return kwargs


class InputValidationError(Exception):
    """Exception raised for errors in the input validation process."""

    pass


@deployments_bp.route("/<subject>/<showback>/list", methods=["GET", "POST"])
@auth.authorized_with_valid_token
def showdeployments(subject, showback):
    access_token = iam.token["access_token"]

    if subject == 'me' or subject == session["userid"]:
        subject = created_by = 'me'
        userid = session["userid"]
    else:
        userid = subject
        issuer = path_utils.path_ensure_slash(iam.base_url)
        created_by = "{}@{}".format(subject, issuer)

    user = dbhelpers.get_user(userid)

    if user is not None:
        group = "None"
        provider = "None"
        selected_status = "actives"
        only_remote = True
        datestart = None
        dateend = None
        if request.method == "POST":
            dr = request.form.to_dict()
            if "group" in dr:
                group = dr.get("group")
            if "provider" in dr:
                provider = dr.get("provider")
            if "start_date" in dr:
                datestart = dr.get("start_date")
            if "end_date" in dr:
                dateend = dr.get("end_date")
            selected_status = dr.get("selected_status")

        if nullorempty(datestart):
            datestart = None
        if nullorempty(dateend):
            dateend = None

        if (group == "None"):
            group = None
        # if "active_usergroup" in session and session["active_usergroup"] is not None:
        #    group = session["active_usergroup"]

        if (provider == "None"):
            provider = None

        excluded_status = build_excludedstatus_filter(selected_status)

        # only_effective = app.config.get("FEATURE_SHOW_BROKEN_DEPLOYMENTS", "no") == "no"
        deployments = []
        try:
            if excluded_status is not None:
                deployments = app.orchestrator.get_deployments(
                    access_token, created_by=created_by, excluded_status=excluded_status
                )
            else:
                deployments = app.orchestrator.get_deployments(
                    access_token, created_by=created_by
                )
        except Exception as e:
            flash("Error retrieving deployment list: \n" + str(e), "warning")

        if deployments:
            deployments = dbhelpers.sanitizedeployments(deployments)["deployments"]

        providers_to_split = app.config.get("PROVIDER_NAMES_TO_SPLIT", None)
        if providers_to_split:
            providers_to_split = providers_to_split.lower()

        groups_labels = []
        providers_labels = []

        # first round, load labels (names)
        for dep in deployments:
            if only_remote == False or dep.remote == True:

                user_group = dep.user_group or "UNKNOWN"
                if user_group and user_group not in groups_labels:
                    groups_labels.append(user_group)

                dep_provider = dep.provider_name or "UNKNOWN"
                if dep.region_name:
                    provider_ext = (dep_provider + "-" + dep.region_name).lower()
                    if providers_to_split and provider_ext in providers_to_split:
                        dep_provider = dep_provider + "-" + dep.region_name.lower()
                if dep_provider and dep_provider not in providers_labels:
                    providers_labels.append(dep_provider)

        if subject == 'me':
            for g in session['supported_usergroups']:
                if g not in groups_labels:
                    groups_labels.append(g)

        # filter eventually dates
        if notnullorempty(datestart) or notnullorempty(dateend):
            dstart = month_boundary(datestart, True)
            dend = month_boundary(dateend, False)
            deployments = filter_date_range(
                deployments,
                dstart,
                dend,
                True)

        # filter eventually provider
        providers_to_filter = []
        if provider:
            providers_to_filter.append(provider)
            deployments = filter_provider(
                deployments,
                providers_to_filter,
                True,
                providers_to_split)

        # filter eventually group
        groups_to_filter = []
        if group:
            groups_to_filter.append(group)
            deployments = filter_group(
                deployments,
                groups_to_filter,
                True)

        app.logger.debug("Deployments: " + str(deployments))

        return render_template("deployments.html",
                               user=user,
                               subject=subject,
                               deployments=deployments,
                               groups_labels=groups_labels,
                               providers_labels=providers_labels,
                               status_labels=get_all_statuses(),
                               group=group,
                               provider=provider,
                               selected_status=selected_status,
                               showback=showback)
    else:
        flash("User not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))


@deployments_bp.route("/<showback>/listall", methods=["GET", "POST"])
@auth.authorized_with_valid_token
def showalldeployments(showback):
    access_token = iam.token["access_token"]

    group = "None"
    provider = "None"
    selected_status = "actives"
    selected_template = "None"
    only_remote = True
    datestart = None
    dateend = None
    if request.method == "POST":
        dr = request.form.to_dict()
        if "group" in dr:
            group = dr.get("group")
        if "provider" in dr:
            provider = dr.get("provider")
        if "date_start" in dr:
            datestart = dr.get("date_start")
        if "date_end" in dr:
            datestart = dr.get("date_end")
        if "selected_status" in dr:
            selected_status = dr.get("selected_status")
        if "selected_template" in dr:
            selected_template = dr.get("selected_template")

    if nullorempty(datestart):
        datestart = None

    if nullorempty(dateend):
        dateend = None

    if (group == "None"):
        group = None

    if (provider == "None"):
        provider = None

    if (selected_template == "None"):
        selected_template = None

    excluded_status = build_excludedstatus_filter(selected_status)

    # only_effective = app.config.get("FEATURE_SHOW_BROKEN_DEPLOYMENTS", "no") == "no"
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

    if deployments:
        deployments = dbhelpers.sanitizedeployments(deployments)["deployments"]

    providers_to_split = app.config.get("PROVIDER_NAMES_TO_SPLIT", None)
    if providers_to_split:
        providers_to_split = providers_to_split.lower()

    groups_labels = []
    providers_labels = []

    # first round, load labels (names)
    for dep in deployments:
        if only_remote == False or dep.remote == True:

            user_group = dep.user_group or "UNKNOWN"
            if user_group and user_group not in groups_labels:
                groups_labels.append(user_group)

            dep_provider = dep.provider_name or "UNKNOWN"
            if dep.region_name:
                provider_ext = (dep_provider + "-" + dep.region_name).lower()
                if providers_to_split and provider_ext in providers_to_split:
                    dep_provider = dep_provider + "-" + dep.region_name.lower()
            if dep_provider and dep_provider not in providers_labels:
                providers_labels.append(dep_provider)

    # filter eventually dates
    if notnullorempty(datestart) or notnullorempty(dateend):
        dstart = month_boundary(datestart, True)
        dend = month_boundary(dateend, False)
        deployments = filter_date_range(
            deployments,
            dstart,
            dend,
            True)

    # filter eventually provider
    if provider:
        providers_to_filter = []
        providers_to_filter.append(provider)
        deployments = filter_provider(
            deployments,
            providers_to_filter,
            True,
            providers_to_split)

    # filter eventually group
    if group:
        groups_to_filter = []
        groups_to_filter.append(group)
        deployments = filter_group(
            deployments,
            groups_to_filter,
            True)

    # filter eventually template
    if selected_template:
        template_to_filter = []
        template_to_filter.append(selected_template)
        deployments = filter_template(
            deployments,
            template_to_filter,
            True)

    app.logger.debug("Deployments: " + str(deployments))

    return render_template("deploymentsall.html",
                           deployments=deployments,
                           groups_labels=groups_labels,
                           providers_labels=providers_labels,
                           status_labels=get_all_statuses(),
                           group=group,
                           provider=provider,
                           selected_status=selected_status,
                           selected_template=selected_template,
                           showback=showback)


@deployments_bp.route("/overview", methods=["GET", "POST"])
@auth.authorized_with_valid_token
def showdeploymentsoverview():
    access_token = iam.token["access_token"]

    only_remote = True
    piemaxvalues = app.config.get("FEATURE_MAX_PIE_SLICES", 0)
    only_effective = False  # app.config.get("FEATURE_SHOW_BROKEN_DEPLOYMENTS", "no") == "no"

    group = "None"
    provider = "None"
    selected_status = "actives"
    if request.method == "POST":
        group = request.form.to_dict()["group"]
        provider = request.form.to_dict()["provider"]
        selected_status = request.form.to_dict()["selected_status"]

    if (group == "None"):
        group = None

    if (provider == "None"):
        provider = None

    excluded_status = build_excludedstatus_filter(selected_status)

    deployments = []
    try:
        if excluded_status is not None:
            deployments = app.orchestrator.get_deployments(
                access_token, created_by="me", excluded_status=excluded_status
            )
        else:
            deployments = app.orchestrator.get_deployments(
                access_token, created_by="me"
            )
    except Exception as e:
        flash("Error retrieving deployment list: \n" + str(e), "warning")

    # sanitize data and filter undesired states
    if deployments:
        deployments = dbhelpers.sanitizedeployments(deployments)["deployments"]

    # Initialize dictionaries for status, projects, and providers
    statuses = {"UNKNOWN": 0}
    groups = {"UNKNOWN": 0}
    providers = {"UNKNOWN": 0}

    providers_to_split = app.config.get("PROVIDER_NAMES_TO_SPLIT", None)
    if providers_to_split:
        providers_to_split = providers_to_split.lower()

    groups_labels = []
    providers_labels = []

    # first round, load labels (names)
    for dep in deployments:
        if only_remote == False or dep.remote == 1:

            user_group = dep.user_group or "UNKNOWN"
            if user_group and user_group not in groups_labels:
                groups_labels.append(user_group)

            dep_provider = dep.provider_name or "UNKNOWN"
            if dep.region_name:
                provider_ext = (dep_provider + "-" + dep.region_name).lower()
                if providers_to_split and provider_ext in providers_to_split:
                    dep_provider = dep_provider + "-" + dep.region_name.lower()
            if dep_provider and dep_provider not in providers_labels:
                providers_labels.append(dep_provider)

    # filter eventually provider
    providers_to_filter = []
    if provider:
        providers_to_filter.append(provider)
        deployments = filter_provider(
            deployments,
            providers_to_filter,
            True,
            providers_to_split)

    # filter eventually group
    groups_to_filter = []
    if group:
        groups_to_filter.append(group)
        deployments = filter_group(
            deployments,
            groups_to_filter,
            True)

    # second round, count instances
    for dep in deployments:
        status = dep.status or "UNKNOWN"
        if (only_remote == False or dep.remote == 1) and \
                (only_effective == False or dep.selected_template):
            statuses[status] = statuses.get(status, 0) + 1

            user_group = dep.user_group or "UNKNOWN"
            groups[user_group] = groups.get(user_group, 0) + 1

            dep_provider = dep.provider_name or "UNKNOWN"
            if dep.region_name:
                provider_ext = (dep_provider + "-" + dep.region_name).lower()
                if providers_to_split and provider_ext in providers_to_split:
                    dep_provider = dep_provider + "-" + dep.region_name.lower()

            providers[dep_provider] = providers.get(dep_provider, 0) + 1

    # remove unused UNKNOWN entries
    if groups["UNKNOWN"] == 0:
        groups.pop("UNKNOWN")
    if statuses["UNKNOWN"] == 0:
        statuses.pop("UNKNOWN")
    if providers["UNKNOWN"] == 0:
        providers.pop("UNKNOWN")

    s_title = "All Deployment Status" if selected_status == "all" else "Deployment Status: " + selected_status
    p_title = "All Groups" if not group else "Group: " + group
    pr_title = "All Providers" if not provider else "Provider: " + provider

    return render_template(
        "depoverview.html",
        s_title=s_title,
        s_labels=list(statuses.keys()),
        s_values=list(statuses.values()),
        s_colors=utils.genstatuscolors(statuses),
        p_title=p_title,
        p_labels=list(groups.keys()),
        p_values=list(groups.values()),
        p_colors=utils.gencolors("blue", len(groups)),
        pr_title=pr_title,
        pr_labels=list(providers.keys()),
        pr_values=list(providers.values()),
        pr_colors=utils.gencolors("green", len(providers)),
        groups_labels=groups_labels,
        providers_labels=providers_labels,
        status_labels=get_all_statuses(),
        group=group,
        provider=provider,
        selected_status=selected_status,
        s_maxvalues=piemaxvalues
    )


@deployments_bp.route("/depstats", methods=["GET", "POST"])
@auth.authorized_with_valid_token
def showdeploymentstats():
    access_token = iam.token["access_token"]

    only_remote = True
    piemaxvalues = app.config.get("FEATURE_MAX_PIE_SLICES", 0)
    only_effective = app.config.get("FEATURE_SHOW_BROKEN_DEPLOYMENTS", "no") == "no"
    group = "None"
    provider = "None"
    templaterq = None
    selected_status = "actives"
    datestart = None
    dateend = None
    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
            templaterq = data.get("id")
            group = data.get("group")
            provider = data.get("provider")
            selected_status = data.get("selected_status")
        else:
            group = request.form.to_dict()["group"]
            provider = request.form.to_dict()["provider"]
            selected_status = request.form.to_dict()["selected_status"]

    if group == "None":
        group = None

    if provider == "None":
        provider = None

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

    # filter eventually dates
    hasfilterdate = False
    if notnullorempty(datestart) or notnullorempty(dateend):
        dstart = month_boundary(datestart, True)
        dend = month_boundary(dateend, False)
        hasfilterdate = True
        deployments = filter_date_range(
            deployments,
            dstart,
            dend,
            True)

    # Initialize dictionaries for status, projects, and providers
    statuses = {"UNKNOWN": 0}
    groups = {"UNKNOWN": 0}
    providers = {"UNKNOWN": 0}
    templates = {"UNKNOWN": 0}

    t_info, _, _, _, _ = tosca.get()

    for info in t_info:
        templates[info] = 0

    providers_to_split = app.config.get("PROVIDER_NAMES_TO_SPLIT", None)
    if providers_to_split:
        providers_to_split = providers_to_split.lower()

    groups_labels = []
    providers_labels = []

    # first round, load labels (names)
    for dep in deployments:
        if only_remote == False or dep.remote == 1:

            user_group = dep.user_group or "UNKNOWN"
            if user_group and user_group not in groups_labels:
                groups_labels.append(user_group)

            dep_provider = dep.provider_name or "UNKNOWN"
            if dep.region_name:
                provider_ext = (dep_provider + "-" + dep.region_name).lower()
                if providers_to_split and provider_ext in providers_to_split:
                    dep_provider = dep_provider + "-" + dep.region_name.lower()
            if dep_provider and dep_provider not in providers_labels:
                providers_labels.append(dep_provider)

    # filter eventually provider
    providers_to_filter = []
    if provider:
        providers_to_filter.append(provider)
        deployments = filter_provider(
            deployments,
            providers_to_filter,
            True,
            providers_to_split)

    # filter eventually group
    groups_to_filter = []
    if group:
        groups_to_filter.append(group)
        deployments = filter_group(
            deployments,
            groups_to_filter,
            True)

    # second round, count instances
    for dep in deployments:
        status = dep.status or "UNKNOWN"
        if (only_remote == False or dep.remote == 1) and \
                (only_effective == False or dep.selected_template):
            statuses[status] = statuses.get(status, 0) + 1

            user_group = dep.user_group or "UNKNOWN"
            groups[user_group] = groups.get(user_group, 0) + 1

            dep_provider = dep.provider_name or "UNKNOWN"
            if dep.region_name:
                provider_ext = (dep_provider + "-" + dep.region_name).lower()
                if providers_to_split and provider_ext in providers_to_split:
                    dep_provider = dep_provider + "-" + dep.region_name.lower()

            providers[dep_provider] = providers.get(dep_provider, 0) + 1

            template = dep.selected_template or "UNKNOWN"
            templates[template] = templates.get(template, 0) + 1

    # remove unused UNKNOWN entries
    if groups["UNKNOWN"] == 0:
        groups.pop("UNKNOWN")
    if statuses["UNKNOWN"] == 0:
        statuses.pop("UNKNOWN")
    if providers["UNKNOWN"] == 0:
        providers.pop("UNKNOWN")
    if templates["UNKNOWN"] == 0:
        templates.pop("UNKNOWN")

    if templaterq is not None:
        occurrences = {"UNKNOWN": 0}
        for dep in deployments:
            tmpl = dep.selected_template or "UNKNOWN"
            if tmpl == templaterq:
                depdate = dep.creation_time.strftime("%Y-%m")
                occurrences[depdate] = occurrences.get(depdate, 0) + 1
        if occurrences["UNKNOWN"] == 0:
            occurrences.pop("UNKNOWN")
        s_occurrences = dict(sorted(occurrences.items()))
        # add empty bins
        if len(s_occurrences) > 0:
            k_occurrences = list(s_occurrences.keys())
            kocc = list(k_occurrences)
            datestart = kocc[0]
            dateend = kocc[len(kocc) - 1]
            # get full interval list
            months = months_list(datestart, dateend)
            for month in months:
                if not month in s_occurrences:
                    s_occurrences[month] = 0
            s_occurrences = dict(sorted(s_occurrences.items()))

        if len(s_occurrences.keys()) > 0:
            return jsonify({"labels": list(s_occurrences.keys()),
                            "values": list(s_occurrences.values()),
                            "group": group,
                            "provider": provider,
                            "selected_status": selected_status,
                            "bar_colors": utils.gencolors("green", len(s_occurrences))
                            })

        else:
            return jsonify({"error": "Template not found!"}), 404

    else:
        occurrences = dict()

        # count instances
        for dep in deployments:
            depdate = dep.creation_time.strftime("%Y-%m")
            sub = dep.sub
            datelist = occurrences.get(depdate, dict({}))
            if not sub in datelist:
                datelist[sub] = 1
            else:
                datelist[sub] = datelist[sub] + 1
            occurrences[depdate] = datelist

        s_occurrences = dict(sorted(occurrences.items(), key=lambda item: item[0]))
        k_occurrences = list(s_occurrences.keys())
        # get default date interval if not user defined
        if not hasfilterdate and len(s_occurrences) > 0:
            kocc = list(k_occurrences)
            datestart = kocc[0]
            dateend = datetime.date.today().strftime("%Y-%m")  # kocc[len(kocc)-1]

            # get full interval list
            months = months_list(datestart, dateend)
            for month in months:
                if not month in s_occurrences:
                    s_occurrences[month] = dict()

        # new sort
        s_occurrences = dict(sorted(s_occurrences.items(), key=lambda item: item[0]))
        k_occurrences = list(s_occurrences.keys())
        v_occurrences = list()
        # count instances
        for k in s_occurrences.values():
            v = 0
            for j in k.values():
                v = v + j
            v_occurrences.append(v)

        s_title = "All Deployment Status" if selected_status == "all" else "Deployment Status: " + selected_status
        p_title = "All Groups" if not group else "Group: " + group
        pr_title = "All Providers" if not provider else "Provider: " + provider
        bar_title = "Deployments over time"

        return render_template(
            "depstatistics.html",
            s_title=s_title,
            s_labels=list(statuses.keys()),
            s_values=list(statuses.values()),
            s_colors=utils.genstatuscolors(statuses.keys()),
            p_title=p_title,
            p_labels=list(groups.keys()),
            p_values=list(groups.values()),
            p_colors=utils.gencolors("blue", len(groups)),
            pr_title=pr_title,
            pr_labels=list(providers.keys()),
            pr_values=list(providers.values()),
            pr_colors=utils.gencolors("green", len(providers)),
            d_templates=templates,
            groups_labels=groups_labels,
            providers_labels=providers_labels,
            status_labels=get_all_statuses(),
            group=group,
            provider=provider,
            selected_status=selected_status,
            s_maxvalues=piemaxvalues,
            k_occurrences=k_occurrences,
            v_occurrences=v_occurrences,
            bar_title=bar_title,
            bar_colors=utils.gencolors("green", len(v_occurrences))
        )


@deployments_bp.route("/<depid>/template")
@auth.authorized_with_valid_token
def deptemplate(depid=None):
    access_token = iam.token["access_token"]
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))
    try:
        template = app.orchestrator.get_template(access_token, depid)
    except Exception:
        flash("Error getting template: ".format(), "danger")
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    return render_template("deptemplate.html", template=template)


@deployments_bp.route("/<depid>/lock")
@auth.authorized_with_valid_token
def lockdeployment(depid=None):
    dep = dbhelpers.get_deployment(depid)
    if dep is not None:
        dep.locked = 1
        dbhelpers.add_object(dep)
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))
    else:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))


@deployments_bp.route("/<depid>/unlock")
@auth.authorized_with_valid_token
def unlockdeployment(depid=None):
    dep = dbhelpers.get_deployment(depid)
    if dep is not None:
        dep.locked = 0
        dbhelpers.add_object(dep)
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))
    else:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))


@deployments_bp.route("/edit", methods=["POST"])
@auth.authorized_with_valid_token
def editdeployment():
    form_data = request.form.to_dict()
    dbhelpers.update_deployment(
        form_data["deployment_uuid"], dict(description=form_data["description"])
    )
    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **SHOW_DEPLOYMENTS_KWARGS))


def preprocess_outputs(outputs, stoutputs, inputs):
    """
    Preprocesses the outputs based on the given inputs and stoutputs.

    :param outputs: The outputs to be preprocessed.
    :param stoutputs: The stoutputs containing conditions for preprocessing.
    :param inputs: The inputs used to evaluate the output conditions.
    """
    # note: inputs parameter is made available in this function
    # for evaluating output conditions (see below)

    for key, value in stoutputs.items():
        if "condition" in value:
            try:
                if not eval(value.get("condition")) and key in outputs:
                    del outputs[key]
            except InputValidationError as ex:
                app.logger.warning(f"Error evaluating condition for output {key}: {ex}")


@deployments_bp.route("/<depid>/details")
@auth.authorized_with_valid_token
def depoutput(depid=None):
    """
    A function to render the details of a deployment, including inputs, outputs,
    and structured outputs.
    Parameters:
    - depid: str, the ID of the deployment
    Returns:
    - rendered template with deployment details, inputs, outputs, and structured outputs
    """
    # retrieve deployment from DB
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))

    inputs, outputs, stoutputs = process_deployment_data(dep)

    return render_template(
        "depoutput.html",
        deployment=dep,
        inputs=inputs,
        outputs=outputs,
        stoutputs=stoutputs,
    )


def is_input_printable(stinputs, k):
    """
    Check if the input is printable
    Args:
        stinputs: The input dictionary.
        k: The key to check in the input dictionary.
    Returns:
        A boolean indicating whether the input is printable
        or True if the key is not in the input dictionary.
    """
    return stinputs.get(k, {}).get("printable", True) if k in stinputs else True


def process_deployment_data(dep):
    """
    Process deployment data and return inputs, outputs, and stoutputs.

    Parameters:
    dep: The deployment data to process.

    Returns:
    inputs: The processed inputs.
    outputs: The processed outputs.
    stoutputs: The processed stoutputs.
    """

    try:
        i = dep.inputs.strip('"') if dep.inputs else None
        i = json.loads(i) if (i and i != '') else {}
    except:
        i = {}

    try:
        stinputs = dep.stinputs.strip('"') if dep.stinputs else None
        stinputs = json.loads(stinputs) if (stinputs and stinputs != '') else {}
    except:
        stinputs = {}

    try:
        outputs = dep.outputs.strip('"') if dep.outputs else None
        outputs = json.loads(outputs) if (outputs and outputs != '') else {}
    except:
        outputs = {}

    try:
        stoutputs = dep.stoutputs.strip('"') if dep.stoutputs else None
        stoutputs = json.loads(stoutputs) if (stoutputs and stoutputs != '') else {}
    except:
        stoutputs = {}

    inputs = {k: v for k, v in i.items() if is_input_printable(stinputs, k)}

    preprocess_outputs(outputs, stoutputs, inputs)

    return inputs, outputs, stoutputs


@deployments_bp.route("/<depid>/templatedb")
@auth.authorized_with_valid_token
def deptemplatedb(depid):
    # retrieve deployment from DB
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))
    else:
        template = dep.template
        return render_template("deptemplate.html", template=template)


@deployments_bp.route("/<depid>/log")
@auth.authorized_with_valid_token
def deplog(depid=None):
    access_token = iam.token["access_token"]
    dep = dbhelpers.get_deployment(depid)

    log = "Not available"
    if dep is not None:
        try:
            log = app.orchestrator.get_log(access_token, depid)
        except Exception:
            pass
    return render_template("deplog.html", log=log)


def extract_vm_details(depid, resources):
    details = []
    for resource in resources:
        if "VirtualMachineInfo" in resource["metadata"]:
            vminfo = json.loads(resource["metadata"]["VirtualMachineInfo"])
            vmprop = utils.format_json_radl(vminfo["vmProperties"])
            vmprop["state"] = resource["state"]
            vmprop["resId"] = resource["uuid"]
            vmprop["depId"] = depid
            details.append(vmprop)
    return details


def process_tosca_info(dep):
    template = dep.template
    tosca_info = tosca.extracttoscainfo(yaml.full_load(io.StringIO(template)), None)
    inputs = dep.inputs.strip('"') if dep.inputs else None
    inputs = json.loads(inputs) if (inputs and inputs != '') else {}
    stinputs = dep.stinputs.strip('"') if dep.stinputs else None
    stinputs = json.loads(stinputs) if (stinputs and stinputs != '') else {}
    tosca_info["inputs"] = {**tosca_info["inputs"], **stinputs}

    for k, v in tosca_info["inputs"].items():
        if k in inputs and "default" in tosca_info["inputs"][k]:
            tosca_info["inputs"][k]["default"] = inputs[k]

    stoutputs = dep.stoutputs.strip('"') if dep.stoutputs else None
    stoutputs = json.loads(stoutputs) if (stoutputs and stoutputs != '') else {}
    tosca_info["outputs"] = {**tosca_info["outputs"], **stoutputs}
    return tosca_info


@deployments_bp.route("/<depid>/infradetails")
@auth.authorized_with_valid_token
def depinfradetails(depid=None):
    access_token = iam.token["access_token"]

    dep = dbhelpers.get_deployment(depid)

    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))

    if dep.physicalId is None:
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    try:
        resources = app.orchestrator.get_resources(access_token, depid)
    except Exception as e:
        flash(str(e), "warning")
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    details = extract_vm_details(depid, resources)
    tosca_info = process_tosca_info(dep)

    return render_template(
        "depinfradetails.html",
        vmsdetails=details,
        deployment=dep,
        template=tosca_info,
        update=True,
    )


# PORTS MANAGEMENT
def get_openstack_connection(
        *,
        endpoint: str,
        provider_name: str,
        provider_type: Optional[str] = None,
        region_name: Optional[str] = None,
) -> openstack.connection.Connection:
    """Create openstack connection, to target project, using access token."""
    conn = None

    # Fed-Reg
    if app.settings.use_fed_reg:
        # Find target provider
        providers = fed_reg.get_providers(
            access_token=iam.token["access_token"],
            with_conn=True,
            name=provider_name,
            type=provider_type,
        )
        assert len(providers) < 2, (
            f"Found multiple providers with name '{provider_name}' and type '{provider_type}'"
        )
        assert len(providers) > 0, (
            f"Provider with name '{provider_name}' and type '{provider_type}' not found"
        )
        provider = providers[0]

        # Retrieve the authentication details matching the current identity provider
        identity_provider = next(
            filter(
                lambda x: x["endpoint"] == session["iss"],
                provider["identity_providers"],
            )
        )
        auth_method = identity_provider["relationship"]

        # Retrieve the auth_url matching the target region. In older deployments,
        # if not inferred from the provider name, the region is None.
        if region_name is not None:
            region = next(
                filter(lambda x: x["name"] == region_name, provider["regions"])
            )
        else:
            region = provider["regions"][0]
        identity_service = next(
            filter(lambda x: x["type"] == "identity", region["services"])
        )

        # Retrieve user groups to get target project
        user_group = next(
            filter(
                lambda x: x["name"] == session["active_usergroup"],
                identity_provider["user_groups"],
            )
        )
        projects = fed_reg.get_projects(
            access_token=iam.token["access_token"],
            with_conn=True,
            provider_uid=provider["uid"],
            user_group_uid=user_group["uid"],
        )
        assert len(projects) < 2, "Found multiple projects"
        assert len(projects) > 0, "Projects not found"
        project = projects[0]

        # Create openstack connection
        conn = openstack.connect(
            auth=dict(
                auth_url=identity_service["endpoint"],
                project_id=project["uuid"],
                protocol=auth_method["protocol"],
                identity_provider=auth_method["idp_name"],
                access_token=iam.token["access_token"],
            ),
            region_name=region_name,
            identity_api_version=3,
            auth_type="v3oidcaccesstoken",
        )
    # SLAM
    elif app.settings.slam_url is not None:
        service = app.cmdb.get_service_by_endpoint(
            iam.token["access_token"], endpoint, provider_name, False
        )

        prj, idp = app.cmdb.get_service_project(
            iam.token["access_token"],
            session["iss"],
            service,
            session["active_usergroup"],
        )

        if not prj or not idp:
            raise Exception("Unable to get service/project information.")

        conn = openstack.connect(
            auth=dict(
                auth_url=service["endpoint"],
                project_id=prj.get("tenant_id"),
                protocol=idp["protocol"],
                identity_provider=idp["name"],
                access_token=iam.token["access_token"],
            ),
            region_name=service["region"],
            identity_api_version=3,
            auth_type="v3oidcaccesstoken",
        )

    return conn


def get_vm_info(depid):
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))
    if dep.physicalId is None:
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    try:
        resources = app.orchestrator.get_resources(iam.token["access_token"], depid)
    except Exception as e:
        flash(str(e), "warning")
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    def find_node_with_pubip(resources):
        for resource in resources:
            if "VirtualMachineInfo" in resource["metadata"]:
                if "vmProperties" in resource["metadata"]["VirtualMachineInfo"]:
                    vm_info = json.loads(resource["metadata"]["VirtualMachineInfo"])[
                        "vmProperties"
                    ]
                    networks = [i for i in vm_info if i.get("class") == "network"]
                    vmi = next(i for i in vm_info if i.get("class") == "system")

                    for network in networks:
                        if network.get("id") == "pub_network":
                            return vmi.get("instance_id"), vmi.get("provider.host")
        return "", ""

    vm_id, vm_endpoint = find_node_with_pubip(resources)
    return {
        "vm_id": vm_id,
        "vm_endpoint": vm_endpoint,
        "vm_provider_type": dep.provider_type,
        "vm_region": dep.region_name,
    }


def get_sec_groups(conn, server_id, public=True):
    # Fetch the security groups associated with the server
    all_security_groups = conn.list_server_security_groups(server_id)

    # Remove duplicates using a dictionary
    unique_security_groups = {
        group["id"]: group for group in all_security_groups
    }.values()

    # Filter for public groups if required
    if public:
        public_network_key = "pub_network"
        unique_security_groups = filter(
            lambda group: public_network_key in group["name"], unique_security_groups
        )

    return list(unique_security_groups)


@deployments_bp.route("/<depid>/security_groups")
@auth.authorized_with_valid_token
def security_groups(depid=None):
    try:
        sec_groups = ""
        subject = request.args.get("subject")
        vm_provider = request.args.get("depProvider")
        vm_info = get_vm_info(depid)
        vm_id = vm_info["vm_id"]
        vm_endpoint = vm_info["vm_endpoint"]

        conn = get_openstack_connection(
            endpoint=vm_endpoint,
            provider_name=vm_provider,
            provider_type=vm_info["vm_provider_type"],
            region_name=vm_info["vm_region"],
        )
        sec_groups = get_sec_groups(conn, vm_id)

        if len(sec_groups) == 1:
            return redirect(
                url_for(
                    MANAGE_RULES_ROUTE,
                    depid=depid,
                    provider=vm_provider,
                    sec_group_id=sec_groups[0]["id"],
                )
            )

        return render_template("depsecgroups.html", depid=depid, sec_groups=sec_groups)
    except Exception as e:
        flash(str(e), "warning")
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(subject)))


@deployments_bp.route("/<depid>/<sec_group_id>/manage_rules")
@auth.authorized_with_valid_token
def manage_rules(depid=None, sec_group_id=None):
    provider = request.args.get("provider")

    vm_info = get_vm_info(depid)
    conn = get_openstack_connection(
        endpoint=vm_info["vm_endpoint"],
        provider_name=provider,
        provider_type=vm_info["vm_provider_type"],
        region_name=vm_info["vm_region"],
    )

    rules = conn.list_security_groups({"id": sec_group_id})

    if len(rules) != 0:
        rules = rules[0].security_group_rules
    else:
        rules = []

    return render_template(
        "depgrouprules.html",
        depid=depid,
        provider=provider,
        sec_group_id=sec_group_id,
        rules=rules,
    )


@deployments_bp.route("/<depid>/<sec_group_id>/create_rule", methods=["POST"])
@auth.authorized_with_valid_token
def create_rule(depid=None, sec_group_id=None):
    # Custom rule templates
    RULE_TEMPLATES = {
        "dns": {
            "description": "DNS traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 53,
            "port_range_max": 53,
        },
        "http": {
            "description": "HTTP traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 80,
            "port_range_max": 80,
        },
        "https": {
            "description": "HTTPS traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 443,
            "port_range_max": 443,
        },
        "imap": {
            "description": "IMAP traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 143,
            "port_range_max": 143,
        },
        "imaps": {
            "description": "IMAPS traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 993,
            "port_range_max": 993,
        },
        "ldap": {
            "description": "LDAP traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 389,
            "port_range_max": 389,
        },
        "ms_sql": {
            "description": "MS SQL traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 1433,
            "port_range_max": 1433,
        },
        "mysql": {
            "description": "MySQL traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 3306,
            "port_range_max": 3306,
        },
        "pop3": {
            "description": "POP3 traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 110,
            "port_range_max": 110,
        },
        "pop3s": {
            "description": "POP3S traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 995,
            "port_range_max": 995,
        },
        "rdp": {
            "description": "RDP traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 3389,
            "port_range_max": 3389,
        },
        "smtp": {
            "description": "SMTP traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 25,
            "port_range_max": 25,
        },
        "smtps": {
            "description": "SMTPS traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 465,
            "port_range_max": 465,
        },
        "ssh": {
            "description": "SSH traffic",
            "direction": "ingress",
            "ethertype": "IPv4",
            "protocol": "tcp",
            "port_range_min": 22,
            "port_range_max": 22,
        },
    }

    provider = request.args.get("provider")
    vm_info = get_vm_info(depid)
    rule_template = RULE_TEMPLATES.get(request.form["input_rule"])

    if rule_template:
        if request.form["input_description"] != "":
            rule_template["description"] = request.form["input_description"]

        if request.form["input_CIDR"] != "":
            rule_template["remote_ip_prefix"] = request.form["input_CIDR"]
        else:
            rule_template["remote_ip_prefix"] = "0.0.0.0/0"

    else:
        rule_template = {
            "direction": request.form["input_direction"],
            "ethertype": "IPv4",
            "description": request.form["input_description"]
            if request.form["input_description"] != ""
            else None,
            "port_range_min": request.form["input_port_from"]
            if request.form["input_port_from"] != ""
            else None,
            "port_range_max": request.form["input_port_to"]
            if request.form["input_port_to"] != ""
            else None,
            "protocol": request.form["input_ip_protocol"]
            if request.form["input_ip_protocol"] != ""
            else "tcp",
            "remote_ip_prefix": request.form["input_CIDR"]
            if request.form["input_CIDR"] != ""
            else "0.0.0.0/0",
        }

    try:
        conn = get_openstack_connection(
            endpoint=vm_info["vm_endpoint"],
            provider_name=provider,
            provider_type=vm_info["vm_provider_type"],
            region_name=vm_info["vm_region"],
        )

        conn.network.create_security_group_rule(
            security_group_id=sec_group_id, **rule_template
        )
        flash("Port created successfully!", "success")
    except Exception as e:
        flash("Error: \n" + str(e), "danger")

    return redirect(
        url_for(
            MANAGE_RULES_ROUTE,
            depid=depid,
            provider=provider,
            sec_group_id=sec_group_id,
        )
    )


@deployments_bp.route("/<depid>/<sec_group_id>/<rule_id>/delete_rule")
@auth.authorized_with_valid_token
def delete_rule(depid=None, sec_group_id=None, rule_id=None):
    provider = request.args.get("provider")
    vm_info = get_vm_info(depid)
    try:
        conn = get_openstack_connection(
            endpoint=vm_info["vm_endpoint"],
            provider_name=provider,
            provider_type=vm_info["vm_provider_type"],
            region_name=vm_info["vm_region"],
        )
        conn.delete_security_group_rule(rule_id)
        flash("Port deleted successfully!", "success")
    except Exception as e:
        flash("Error: \n" + str(e), "danger")

    return redirect(
        url_for(
            MANAGE_RULES_ROUTE,
            depid=depid,
            provider=provider,
            sec_group_id=sec_group_id,
        )
    )


# ---


@deployments_bp.route("/<depid>/actions", methods=["POST"])
@auth.authorized_with_valid_token
def depaction(depid):
    access_token = iam.token["access_token"]
    dep = dbhelpers.get_deployment(depid)
    if dep is not None and dep.physicalId is not None:
        try:
            app.logger.debug(f"Requested action on deployment {dep.uuid}")
            app.orchestrator.post_action(
                access_token, depid, request.args["vmid"], request.args["action"]
            )
            flash("Action successfully triggered.", "success")
        except Exception as e:
            app.logger.error(f"Action on deployment {dep.uuid} failed: {str(e)}")
            flash(str(e), "warning")

    return redirect(url_for("deployments_bp.depinfradetails", depid=depid))


@deployments_bp.route("/<depid>/delnode", methods=["POST"])
@auth.authorized_with_valid_token
def delnode(depid):
    access_token = iam.token["access_token"]
    dep = dbhelpers.get_deployment(depid)
    if dep is not None and dep.physicalId is not None:
        try:
            vm_id = request.args["vmid"]
            app.logger.debug(
                f"Requested deletion of node {vm_id} on deployment {dep.uuid}"
            )
            resource = app.orchestrator.get_resource(access_token, depid, vm_id)
            resources = app.orchestrator.get_resources(access_token, depid)

            node = next((res for res in resources if res.get("uuid") == vm_id), None)
            node_name = node.get("toscaNodeName")
            # current count -1 --> remove one node
            filtered = list(filter(lambda res: res.get("toscaNodeName") == node_name, resources))
            count = len(filtered) - 1

            app.logger.debug(f"Resource details: {resource}")
            app.logger.debug(f"Count = {count}")

            template = app.orchestrator.get_template(access_token, depid)

            template_dict = yaml.full_load(io.StringIO(template))

            new_template, new_inputs = tosca_helpers.set_removal_list(
                template_dict, node_name, [vm_id], count
            )

            template_text = yaml.dump(
                new_template, default_flow_style=False, sort_keys=False
            )
            app.logger.debug(f"{template_text}")

            app.orchestrator.update(
                access_token,
                depid,
                template_text,
                new_inputs,
                dep.keep_last_attempt,
                app.config["PROVIDER_TIMEOUT"],
                app.config["OVERALL_TIMEOUT"],
                app.config["CALLBACK_URL"],
            )
            # update inputs for deployment stored in the DB
            oldinputs = json.loads(dep.inputs.strip('"')) if dep.inputs else {}
            updatedinputs = {**oldinputs, **new_inputs}
            dep.inputs = (json.dumps(updatedinputs),)
            dbhelpers.add_object(dep)

            flash("Node deletion successfully triggered.", "success")
        except Exception as e:
            err_msg = f"Node deletion on deployment {dep.uuid} failed: {str(e)}"
            app.logger.error(err_msg)
            flash(err_msg, "warning")

    return redirect(url_for("deployments_bp.depinfradetails", depid=depid))


@deployments_bp.route("/<depid>/qcgdetails")
@auth.authorized_with_valid_token
def depqcgdetails(depid=None):
    access_token = iam.token["access_token"]

    dep = dbhelpers.get_deployment(depid)
    if dep is not None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))
    if dep.physicalId is not None and dep.deployment_type == "QCG":
        try:
            job = json.loads(app.orchestrator.get_extra_info(access_token, depid))
        except Exception as e:
            app.logger.warning("Error decoding Job details response: {}".format(str(e)))
            job = None

        return render_template("depqcgdetails.html", job=(job[0] if job else None))
    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))


@deployments_bp.route("/<depid>/<mode>/<force>/delete")
@auth.authorized_with_valid_token
def depdel(depid=None, mode="user", force="false"):
    access_token = iam.token["access_token"]

    dep = dbhelpers.get_deployment(depid)
    # should happen as a callback on the cancellation message from the orchestrator
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))

    if dep.storage_encryption == 1:
        secret_path = session["userid"] + "/" + dep.vault_secret_uuid
        delete_secret_from_vault(access_token, secret_path)
    ##

    try:
        app.orchestrator.delete(
            access_token,
            depid,
            force)

    except Exception as e:
        flash(str(e), "danger")

    if mode == "user":
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))
    else:
        return redirect(url_for(SHOW_ALLDEPLOYMENTS_ROUTE, **SHOW_ALLDEPLOYMENTS_KWARGS))


@deployments_bp.route("/<depid>/<mode>/reset")
@auth.authorized_with_valid_token
def depreset(depid=None, mode="user"):
    access_token = iam.token["access_token"]
    # add check last update time to ensure stuck state
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))
    if dep.status == "DELETE_IN_PROGRESS":
        try:
            app.orchestrator.patch(access_token, depid, "DELETE_FAILED")
        except Exception as e:
            flash(str(e), "danger")

    if mode == "user":
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))
    else:
        return redirect(url_for(SHOW_ALLDEPLOYMENTS_ROUTE, **SHOW_ALLDEPLOYMENTS_KWARGS))


@deployments_bp.route("/depupdate/<depid>")
@auth.authorized_with_valid_token
def depupdate(depid=None):
    dep = dbhelpers.get_deployment(depid)

    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))

    access_token = iam.token["access_token"]
    template = dep.template
    tosca_info = tosca.extracttoscainfo(yaml.full_load(io.StringIO(template)), None)
    inputs = json.loads(dep.inputs.strip('"')) if dep.inputs else {}
    stinputs = json.loads(dep.stinputs.strip('"')) if dep.stinputs else {}
    tosca_info["inputs"] = {**tosca_info["inputs"], **stinputs}

    for k, v in tosca_info["inputs"].items():
        if k in inputs and "default" in tosca_info["inputs"][k]:
            tosca_info["inputs"][k]["default"] = inputs[k]

    stoutputs = json.loads(dep.stoutputs.strip('"')) if dep.stoutputs else {}
    tosca_info["outputs"] = {**tosca_info["outputs"], **stoutputs}

    sla_id = tosca_helpers.getslapolicy(tosca_info)

    slas = providers.getslasdt(
        access_token=access_token, deployment_type=dep.deployment_type
    )

    ssh_pub_key = dbhelpers.get_ssh_pub_key(session["userid"])

    return render_template(
        "updatedep.html",
        template=tosca_info,
        template_description=tosca_info["description"],
        instance_description=dep.description,
        feedback_required=dep.feedback_required,
        keep_last_attempt=dep.keep_last_attempt,
        provider_timeout=app.config["PROVIDER_TIMEOUT"],
        selectedTemplate=dep.selected_template,
        ssh_pub_key=ssh_pub_key,
        slas=slas,
        sla_id=sla_id,
        depid=depid,
        update=True,
    )


@deployments_bp.route("/addnodes/<depid>", methods=["POST"])
@auth.authorized_with_valid_token
def addnodes(depid):
    access_token = iam.token["access_token"]

    form_data = request.form.to_dict()

    app.logger.debug(f"Form data for dep {depid}: {json.dumps(form_data)}")

    dep = dbhelpers.get_deployment(depid)

    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))
    if dep.physicalId is None:
        flash("Deployment invalid.", "warning")
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    try:
        template = app.orchestrator.get_template(access_token, depid)

        template_dict = yaml.full_load(io.StringIO(template))

        template_text = yaml.dump(
            template_dict, default_flow_style=False, sort_keys=False
        )

        new_inputs = extract_inputs(form_data)

        old_inputs = json.loads(dep.inputs.strip('"')) if dep.inputs else {}

        # do not trigger an update if nothing changes
        if not form_data.get("extra_opts.force_update") and all(
                old_inputs.get(k) == v for k, v in new_inputs.items()
        ):
            message = (
                f"Node addition Aborted for Deployment {dep.uuid}: No changes detected"
            )
            app.logger.error(message)
            flash(message, "warning")
            return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

        app.orchestrator.update(
            access_token,
            depid,
            template_text,
            new_inputs,
            dep.keep_last_attempt,
            app.config["PROVIDER_TIMEOUT"],
            app.config["OVERALL_TIMEOUT"],
            app.config["CALLBACK_URL"],
        )
        # update inputs for deployment stored in the DB
        updatedinputs = {**old_inputs, **new_inputs}
        dep.inputs = (json.dumps(updatedinputs),)
        dbhelpers.add_object(dep)
        flash("Node addition successfully triggered.", "success")
    except Exception as e:
        err_msg = f"Node addition on deployment {dep.uuid} failed: {str(e)}"
        app.logger.error(err_msg)
        flash(err_msg, "warning")

    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))


@deployments_bp.route("/updatedep", methods=["POST"])
@auth.authorized_with_valid_token
def updatedep():
    access_token = iam.token["access_token"]

    form_data = request.form.to_dict()

    app.logger.debug("Form data: " + json.dumps(form_data))

    depid = form_data["_depid"]

    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))

    template = yaml.full_load(io.StringIO(dep.template))

    if form_data["extra_opts.schedtype"].lower() == "man":
        template = add_sla_to_template(template, form_data["extra_opts.selectedSLA"])
    else:
        remove_sla_from_template(template)
    app.logger.debug(yaml.dump(template, default_flow_style=False))

    stinputs = json.loads(dep.stinputs.strip('"')) if dep.stinputs else {}
    inputs = {
        k: v
        for (k, v) in form_data.items()
        if not k.startswith("extra_opts.")
           and k != "_depid"
           and (
                   k in stinputs
                   and "updatable" in stinputs[k]
                   and stinputs[k]["updatable"] is True
           )
    }

    app.logger.debug("Parameters: " + json.dumps(inputs))

    template_text = yaml.dump(template, default_flow_style=False, sort_keys=False)

    app.logger.debug(f"[Deployment Update] inputs: {json.dumps(inputs)}")
    app.logger.debug(f"[Deployment Update] Template: {template_text}")

    keep_last_attempt = (
        1 if "extra_opts.keepLastAttempt" in form_data else dep.keep_last_attempt
    )
    feedback_required = (
        1 if "extra_opts.sendEmailFeedback" in form_data else dep.feedback_required
    )

    provider_timeout_mins = (
        form_data["extra_opts.providerTimeout"]
        if "extra_opts.providerTimeoutSet" in form_data
        else app.config["PROVIDER_TIMEOUT"]
    )

    try:
        app.orchestrator.update(
            access_token,
            depid,
            template_text,
            inputs,
            keep_last_attempt,
            provider_timeout_mins,
            app.config["OVERALL_TIMEOUT"],
            app.config["CALLBACK_URL"],
        )
        # store data into database
        dep.keep_last_attempt = keep_last_attempt
        dep.feedback_required = feedback_required
        dep.template = template_text
        oldinputs = json.loads(dep.inputs.strip('"')) if dep.inputs else {}
        updatedinputs = {**oldinputs, **inputs}
        dep.inputs = (json.dumps(updatedinputs),)
        dbhelpers.add_object(dep)

    except Exception as e:
        flash(str(e), "danger")

    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))


@deployments_bp.route("/configure", methods=["GET"])
@auth.authorized_with_valid_token
def configure():
    _, _, tosca_gmetadata, _, _ = tosca.get()

    selected_group = request.args.get("selected_group", None)

    ssh_pub_key = dbhelpers.get_ssh_pub_key(session["userid"])
    if not ssh_pub_key and app.config.get("FEATURE_REQUIRE_USER_SSH_PUBKEY") == "yes":
        flash(
            "Warning! You will not be able to deploy your service \
                as no Public SSH key has been uploaded.",
            "danger",
        )

    if selected_group is None:
        selected_group = session['selected_group']

    if selected_group is not None:
        session["selected_group"] = selected_group
        templates = tosca_gmetadata[selected_group]["templates"]

        if len(templates) == 1:
            selected_tosca = templates[0]["name"]
            return configure_select_scheduling(selected_tosca, False)

        items = []
        for template in templates:
            item = {
                "name": template.get("name", ""),
                "description": template.get("description", ""),
                "option": template.get("option", ""),
            }
            items.append(item)
        return render_template(
            "choosedep.html", templates=templates, ssh_pub_key=ssh_pub_key
        )

    flash("Error getting selected_group (not found)", "danger")
    return redirect(url_for(SHOW_HOME_ROUTE))


@deployments_bp.route("/configure_select_scheduling", methods=["GET"])
@auth.authorized_with_valid_token
def configure_select_scheduling(selected_tosca=None, multi_templates=True):
    access_token = iam.token["access_token"]

    steps = {"current": 1, "total": 3}
    if multi_templates:
        steps = {"current": 2, "total": 4}

    # If not only one tosca template, read the chosen tosca from query parameters
    if not selected_tosca:
        selected_tosca = request.args.get("selected_tosca")  # Changed from form to args

    tosca_info, _, _, _, _ = tosca.get()
    template = tosca_info.get(os.path.normpath(selected_tosca), None)
    if template is None:
        flash("Error getting template (not found)", "danger")
        return redirect(url_for(SHOW_HOME_ROUTE))

    slas = providers.getslasdt(
        access_token=access_token, deployment_type=template["deployment_type"]
    )
    # TODO: Consider saving this list in Redis for caching?)

    ssh_pub_key = dbhelpers.get_ssh_pub_key(session["userid"])

    return render_template(
        "chooseprovider.html",
        slas=slas,
        selected_tosca=selected_tosca,
        steps=steps,
        ssh_pub_key=ssh_pub_key,
    )


@deployments_bp.route("/configure_form", methods=["GET"])
@auth.authorized_with_valid_token
def configure_form():
    access_token = iam.token["access_token"]
    steps = {
        "current": int(request.args.get("steps_current", 0)) + 1,
        "total": int(request.args.get("steps_total", 0)),
    }
    selected_sla = None

    selected_tosca = request.args.get("selected_tosca")
    if selected_tosca is None:
        flash("Error getting template (not found)", "danger")
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **SHOW_DEPLOYMENTS_KWARGS))

    tosca_info, _, _, _, _ = tosca.get()
    template = copy.deepcopy(tosca_info[os.path.normpath(selected_tosca)])

    sched_type = request.args.get(
        "extra_opts.schedtype", "auto"
    )
    if sched_type == "man":
        selected_sla = request.args.get(
            "extra_opts.selectedSLA"
        )
        if selected_sla:
            sla_id, region_name = selected_sla.split("_")
            template = patch_template(
                access_token=access_token,
                template=template,
                sla_id=sla_id,
                region_name=region_name,
            )
    else:
        template = patch_template(access_token=access_token, template=template)

    ssh_pub_key = dbhelpers.get_ssh_pub_key(session["userid"])

    return render_template(
        "createdep.html",
        template=template,
        template_inputs=json.dumps(template["inputs"], ensure_ascii=False),
        feedback_required=True,
        keep_last_attempt=False,
        provider_timeout=app.config["PROVIDER_TIMEOUT"],
        selectedTemplate=selected_tosca,
        ssh_pub_key=ssh_pub_key,
        steps=steps,
        update=False,
        sched_type=sched_type,
        selected_sla=selected_sla,
    )


def patch_template(
        *,
        access_token: str,
        template: dict,
        sla_id: Optional[str] = None,
        region_name: Optional[str] = None,
):
    if app.settings.use_fed_reg:
        user_group = fed_reg.retrieve_active_user_group(access_token=access_token)
        if user_group is None:
            flash("Error getting user_group (not found)", "danger")
            return redirect(url_for(SHOW_HOME_ROUTE))

        # Manage group overrides
        for k, v in list(template["inputs"].items()):
            # skip images override
            x = re.search("operating_system", k)
            if not x and "group_overrides" in v:
                if user_group["name"] in v["group_overrides"]:
                    overrides = v["group_overrides"][user_group["name"]]
                    template["inputs"][k] = {**v, **overrides}
                    del template["inputs"][k]["group_overrides"]

        # flavor patterns
        pattern = r"^(?=.*flavor)(?!.*partition).*"

        flavors, nogpu_flavors, gpu_flavors, images = fed_reg.retrieve_active_user_group_resources(
            access_token=access_token, user_group=user_group, sla_id=sla_id, region_name=region_name
        )

        # patch flavors
        if flavors:
            for k in template["inputs"].keys():
                if bool(re.match(pattern, k)):
                    if re.search("gpu", k):
                        flavors = nogpu_flavors
                        break

            # override template flavors with provider flavors
            for k, v in list(template["inputs"].items()):
                # search for flavors key and rename if needed
                x = bool(re.match(pattern, k))
                if x is True and "constraints" in v:
                    k_flavors = k
                    k_cpu = None
                    k_mem = None
                    k_disk = None
                    k_gpus = None
                    k_gpu_model = None
                    # search for cpu key
                    for ff in v["constraints"]:
                        if k_cpu:
                            break
                        for fk in ff["set"].keys():
                            x = re.search("num_cpus", fk)
                            if x is not None:
                                k_cpu = fk
                                break
                    # search for mem key
                    for ff in v["constraints"]:
                        if k_mem:
                            break
                        for fk in ff["set"].keys():
                            x = re.search("mem_size", fk)
                            if x is not None:
                                k_mem = fk
                                break
                    # search for disk key
                    for ff in v["constraints"]:
                        if k_disk:
                            break
                        for fk in ff["set"].keys():
                            x = re.search("disk_size", fk)
                            if x is not None:
                                k_disk = fk
                                break
                    # search for gpu key
                    for ff in v["constraints"]:
                        if k_gpus:
                            break
                        for fk in ff["set"].keys():
                            x = re.search("num_gpus", fk)
                            if x is not None:
                                k_gpus = fk
                                break
                    # search for gpu model key
                    for ff in v["constraints"]:
                        if k_gpu_model:
                            break
                        for fk in ff["set"].keys():
                            x = re.search("gpu_model", fk)
                            if x is not None:
                                k_gpu_model = fk
                                break
                    # if renaming needed
                    if k_mem or k_cpu or k_disk or k_gpus or k_gpu_model:
                        if not k_mem:
                            k_mem = "mem_size"
                        if not k_cpu:
                            k_cpu = "num_cpus"
                        if not k_disk:
                            k_disk = "disk_size"
                        if not k_gpus:
                            k_gpus = "num_gpus"
                        if not k_gpu_model:
                            k_gpu_model = "gpu_model"
                        rflavors = []
                        if re.search("gpu", k_flavors):
                            ff = gpu_flavors
                        else:
                            ff = flavors
                        for f in ff:
                            flavor = {
                                "value": f["value"],
                                "label": f["label"],
                                "set": {
                                    k_cpu: "{}".format(f["set"]["num_cpus"]),
                                    k_mem: "{}".format(f["set"]["mem_size"]),
                                    k_disk: "{}".format(f["set"]["disk_size"]),
                                    k_gpus: "{}".format(f["set"]["num_gpus"]),
                                    k_gpu_model: "{}".format(f["set"]["gpu_model"]),
                                },
                            }
                            rflavors.append(flavor)
                        template["inputs"][k_flavors]["constraints"] = rflavors
                    else:
                        if re.search("gpu", k_flavors):
                            template["inputs"][k_flavors]["constraints"] = gpu_flavors
                        else:
                            template["inputs"][k_flavors]["constraints"] = flavors
                    if "group_overrides" in v:
                        del template["inputs"][k_flavors]["group_overrides"]

        # patch images
        if images:
            # override template flavors with provider flavors
            for k, v in list(template["inputs"].items()):
                # search for flavors key and rename if needed
                x = re.search("operating_system", k)
                if x is not None and "constraints" in v:
                    k_images = k
                    template["inputs"][k_images]["constraints"] = images
                    if "group_overrides" in v:
                        del template["inputs"][k_images]["group_overrides"]
        else:
            # Manage possible overrides
            for k, v in list(template["inputs"].items()):
                x = re.search("operating_system", k)
                if (
                        x is not None
                        and "group_overrides" in v
                        and user_group["name"] in v["group_overrides"]
                ):
                    overrides = v["group_overrides"][user_group["name"]]
                    template["inputs"][k] = {**v, **overrides}
                    del template["inputs"][k]["group_overrides"]

    return template


def remove_sla_from_template(template):
    if "topology_template" in template:
        if "policies" in template["topology_template"]:
            for policy in template["topology_template"]["policies"]:
                for k, v in policy.items():
                    if "type" in v and (
                            v["type"] == "tosca.policies.indigo.SlaPlacement"
                            or v["type"] == "tosca.policies.Placement"
                    ):
                        template["topology_template"]["policies"].remove(policy)
                        break
            if len(template["topology_template"]["policies"]) == 0:
                del template["topology_template"]["policies"]
    else:
        if "policies" in template:
            for policy in template["policies"]:
                for k, v in policy.items():
                    if "type" in v and (
                            v["type"] == "tosca.policies.indigo.SlaPlacement"
                            or v["type"] == "tosca.policies.Placement"
                    ):
                        template["policies"].remove(policy)
                        break
            if len(template["policies"]) == 0:
                del template["policies"]
    return template


def add_sla_to_template(template, sla):
    # Add or replace the placement policy
    sla_id, sla_region = sla.split("_")

    tosca_sla_placement_type = "tosca.policies.indigo.SlaPlacement"
    if "topology_template" in template:
        template["topology_template"]["policies"] = [
            {
                "deploy_on_specific_site": {
                    "type": tosca_sla_placement_type,
                    "properties": {"sla_id": sla_id, "region": sla_region},
                }
            }
        ]
    else:
        template["policies"] = [
            {
                "deploy_on_specific_site": {
                    "type": tosca_sla_placement_type,
                    "properties": {"sla_id": sla_id, "region": sla_region},
                }
            }
        ]
    return template


def extract_inputs(form_data):
    return {
        k: v
        for (k, v) in form_data.items()
        if not k.startswith("extra_opts.") and k != "csrf_token"
    }


def load_template(selected_template):
    with io.open(
            os.path.join(app.settings.tosca_dir, selected_template), encoding="utf-8"
    ) as stream:
        template = yaml.full_load(stream)
        stream.seek(0)
        template_text = stream.read()
    return template, template_text


def process_dependent_definition(key: str, inputs: dict, stinputs: dict):
    value = stinputs[key]
    if value["type"] == "dependent_definition":
        # retrieve the real type from dedicated field
        if inputs[key + "-ref"] in stinputs:
            stinputs[key] = stinputs[inputs[key + "-ref"]]
        del inputs[key + "-ref"]


def process_security_groups(key: str, inputs: dict, stinputs: dict, form_data: dict):
    value = stinputs.get(key)

    if not value or value["type"] != "map":
        return

    port_types = [
        "tosca.datatypes.network.PortSpec",
        "tosca.datatypes.indigo.network.PortSpec",
    ]
    if not any(value["entry_schema"]["type"] == t for t in port_types):
        return

    if key in inputs:
        process_inputs_for_security_groups(key, value, inputs, form_data)


def process_inputs_for_security_groups(key, value, inputs, form_data):
    try:
        inputs[key] = json.loads(form_data.get(key, {}))
        for k, v in inputs[key].items():
            if "," in v["source"]:
                v["source_range"] = json.loads(v.pop("source", None))
    except Exception:
        del inputs[key]
        inputs[key] = {"ssh": {"protocol": "tcp", "source": 22}}

    if "required_ports" in value:
        inputs[key] = {**value["required_ports"], **inputs[key]}


def process_map(key: str, inputs: dict, stinputs: dict, form_data: dict):
    value = stinputs[key]
    if value["type"] == "map" and value["entry_schema"]["type"] == "string":
        if key in inputs:
            try:
                inputs[key] = {}
                imap = json.loads(form_data[key])
                for k, v in imap.items():
                    inputs[key][v["key"]] = v["value"]
            except Exception:
                del inputs[key]


def process_list(key: str, inputs: dict, stinputs: dict, form_data: dict):
    value = stinputs[key]

    if value["type"] == "list" and key in inputs:
        try:
            json_data = json.loads(form_data[key])
            if (
                    value["entry_schema"]["type"] == "map"
                    and value["entry_schema"]["entry_schema"]["type"] == "string"
            ):
                array = []
                for el in json_data:
                    array.append({el["key"]: el["value"]})
                inputs[key] = array
            else:
                inputs[key] = json_data
        except Exception:
            del inputs[key]


def process_ssh_user(key: str, inputs: dict, stinputs: dict):
    value = stinputs[key]
    if value["type"] == "ssh_user":
        app.logger.info("Add ssh user")
        if app.config.get("FEATURE_REQUIRE_USER_SSH_PUBKEY") == "yes":
            if dbhelpers.get_ssh_pub_key(session["userid"]):
                inputs[key] = [
                    {
                        "os_user_name": session["preferred_username"],
                        "os_user_add_to_sudoers": True,
                        "os_user_ssh_public_key": dbhelpers.get_ssh_pub_key(
                            session["userid"]
                        ),
                    }
                ]
            else:
                flash(
                    "Deployment request failed: no SSH key found. Please upload your key.",
                    "danger",
                )
                raise InputValidationError(
                    "Deployment request failed: no SSH key found. Please upload your key."
                )


def process_random_password(key: str, inputs: dict, stinputs: dict):
    value = stinputs[key]
    if value["type"] == "random_password":
        inputs[key] = utils.generate_password()


def process_uuidgen(key: str, inputs: dict, stinputs: dict, uuidgen_deployment: str):
    value = stinputs[key]
    if value["type"] == "uuidgen":
        prefix = ""
        suffix = ""
        if "extra_specs" in value:
            prefix = (
                value["extra_specs"]["prefix"]
                if "prefix" in value["extra_specs"]
                else ""
            )
            suffix = (
                value["extra_specs"]["suffix"]
                if "suffix" in value["extra_specs"]
                else ""
            )
        inputs[key] = prefix + uuidgen_deployment + suffix


def process_openstack_ec2credentials(key: str, inputs: dict, stinputs: dict):
    value = stinputs[key]

    if value["type"] == "openstack_ec2credentials" and key.startswith("__"):
        try:
            # remove from inputs array since it is not a real input to pass to the orchestrator
            del inputs[key]
            s3_url = value["url"]

            # Fed-Reg
            if app.settings.use_fed_reg:
                user_groups = fed_reg.get_user_groups(
                    access_token=iam.token["access_token"],
                    with_conn=True,
                    name=session["active_usergroup"],
                    idp_endpoint=session["iss"],
                )
                assert len(user_groups) < 2, (
                    f"Found multiple user groups with name '{session['active_usergroup']}' and issuer '{session['iss']}'"
                )
                assert len(user_groups) > 0, (
                    f"User group with name '{session['active_usergroup']}' and issuer '{session['iss']}' not found"
                )
                user_group = user_groups[0]

                # Find project, provider and region matching service url
                found = False
                for sla in user_group["slas"]:
                    for project in sla["projects"]:
                        _provider = project["provider"]
                        for quota in filter(
                                lambda x: not x["usage"], project["quotas"]
                        ):
                            service = quota["service"]
                            region = service["region"]
                            if (
                                    service["type"] == "object-store"
                                    and "s3" in service["name"]
                                    and service["endpoint"].startswith(s3_url)
                            ):
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if not found:
                    raise Exception("Unable to get EC2 credentials")

                # Get target provider details
                provider = fed_reg.get_provider(
                    uid=_provider["uid"],
                    access_token=iam.token["access_token"],
                    with_conn=True,
                )
                assert provider, f"Provider with uid '{provider['uid']}' not found"

                # Retrieve the authentication details matching the current identity provider
                identity_provider = next(
                    filter(
                        lambda x: x["endpoint"] == session["iss"],
                        provider["identity_providers"],
                    )
                )
                auth_method = identity_provider["relationship"]

                # Retrieve the auth_url matching the target region. In older deployments,
                # if not inferred from the provider name, the region is None.
                region = provider["regions"][0]
                identity_service = next(
                    filter(lambda x: x["type"] == "identity", region["services"])
                )

                # Retrieve EC2 access and secret
                access, secret = keystone.get_or_create_ec2_creds(
                    access_token=iam.token["access_token"],
                    project=project["name"],
                    auth_url=identity_service["endpoint"].rstrip("/v3"),
                    identity_provider=auth_method["idp_name"],
                    protocol=auth_method["protocol"],
                )
            # SLAM
            elif app.settings.slam_url is not None:
                service = app.cmdb.get_service_by_endpoint(
                    iam.token["access_token"], s3_url
                )
                prj, idp = app.cmdb.get_service_project(
                    iam.token["access_token"],
                    session["iss"],
                    service,
                    session["active_usergroup"],
                )

                if not prj or not idp:
                    raise Exception("Unable to get EC2 credentials")

                if prj and idp:
                    access, secret = keystone.get_or_create_ec2_creds(
                        iam.token["access_token"],
                        prj.get("tenant_name"),
                        service["auth_url"].rstrip("/v3"),
                        idp["name"],
                        idp["protocol"],
                    )

            if access is not None and secret is not None:
                iam_base_url = app.settings.iam_url
                iam_client_id = app.settings.iam_client_id
                iam_client_secret = app.settings.iam_client_secret

                jwt_token = auth.exchange_token_with_audience(
                    iam_base_url,
                    iam_client_id,
                    iam_client_secret,
                    iam.token["access_token"],
                    app.config.get("VAULT_BOUND_AUDIENCE"),
                )

                vaultclient = vaultservice.connect(
                    jwt_token, app.config.get("VAULT_ROLE")
                )

                secret_path = (
                        session["userid"]
                        + "/services_credential/"
                        + urlparse(s3_url).netloc
                        + "/"
                        + session["active_usergroup"]
                )

                vaultclient.write_secret_dict(
                    None,
                    secret_path,
                    {"aws_access_key": access, "aws_secret_key": secret},
                )

                app.logger.debug(f"EC2 Credentials saved to Vault path {secret_path}")

                test_backet_name = "".join(random.choices(string.ascii_lowercase, k=8))
                s3.create_bucket(
                    s3_url=s3_url,
                    access_key=access,
                    secret_key=secret,
                    bucket=test_backet_name,
                )
                s3.delete_bucket(
                    s3_url=s3_url,
                    access_key=access,
                    secret_key=secret,
                    bucket=test_backet_name,
                )

                app.logger.debug(
                    f"Bucket creation/deletion test performed with bucket name {test_backet_name}"
                )

        except Forbidden as e:
            app.logger.error("Error while testing S3: {}".format(e))
            flash(
                " Sorry, your request needs a special authorization. \
                        A notification has been sent automatically to the support team. \
                        You will be contacted soon.",
                "danger",
            )
            utils.send_authorization_request_email(
                "Sync&Share aaS for group {}".format(session["active_usergroup"])
            )
            raise


def process_ldap_user(key: str, inputs: dict, stinputs: dict):
    value = stinputs[key]

    if value["type"] == "ldap_user":
        try:
            del inputs[key]

            iam_base_url = app.settings.iam_url
            iam_client_id = app.settings.iam_client_id
            iam_client_secret = app.settings.iam_client_secret

            username = "{}_{}".format(session["userid"], urlparse(iam_base_url).netloc)
            email = session["useremail"]

            jwt_token = auth.exchange_token_with_audience(
                iam_base_url,
                iam_client_id,
                iam_client_secret,
                iam.token["access_token"],
                app.config.get("VAULT_BOUND_AUDIENCE"),
            )

            vaultclient = vaultservice.connect(jwt_token, app.config.get("VAULT_ROLE"))
            luser = LdapUserManager(
                app.config["LDAP_SOCKET"],
                app.config["LDAP_TLS_CACERT_FILE"],
                app.config["LDAP_BASE"],
                app.config["LDAP_BIND_USER"],
                app.config["LDAP_BIND_PASSWORD"],
                vaultclient,
            )

            username, password = luser.create_user(username, email)
            username_input_name = value["inputs"]["username"]
            inputs[username_input_name] = username
            password_input_name = value["inputs"]["password"]
            inputs[password_input_name] = password

        except Exception as e:
            app.logger.error("Error: {}".format(e))
            flash(
                " The deployment submission failed with: {}. \
                        Please try later or contact the admin(s): {}".format(
                    e, app.config.get("SUPPORT_EMAIL")
                ),
                "danger",
            )
            raise InputValidationError(e)


def process_userinfo(key, inputs, stinputs):
    value = stinputs[key]

    if value["type"] == "userinfo":
        if key in inputs and value["attribute"] == "sub":
            inputs[key] = session["userid"]


def process_multiselect(key, inputs, stinputs):
    value = stinputs[key]
    if value["type"] == "multiselect" and key in inputs:
        try:
            lval = request.form.getlist(key)
            if "format" in value and value["format"]["type"] == "string":
                inputs[key] = value["format"]["delimiter"].join(lval)
            else:
                inputs[key] = lval
        except Exception as e:
            app.logger.error("Error processing input {}: {}".format(key, e))
            flash(
                " The deployment submission failed with: {}. \
                        Please try later or contact the admin(s): {}".format(
                    e, app.config.get("SUPPORT_EMAIL")
                ),
                "danger",
            )
            raise InputValidationError(e)


def process_inputs(source_template, inputs, form_data, uuidgen_deployment):
    doprocess = True

    stinputs = copy.deepcopy(source_template["inputs"])

    for k, v in list(stinputs.items()):
        if (
                "group_overrides" in v
                and session["active_usergroup"] in v["group_overrides"]
        ):
            overrides = v["group_overrides"][session["active_usergroup"]]
            stinputs[k] = {**v, **overrides}
            del stinputs[k]["group_overrides"]

    for key in stinputs.keys():
        try:
            # Manage special type 'dependent_definition' as first
            process_dependent_definition(key, inputs, stinputs)

            # Manage security groups
            process_security_groups(key, inputs, stinputs, form_data)

            # Manage map of string
            process_map(key, inputs, stinputs, form_data)

            # Manage list
            process_list(key, inputs, stinputs, form_data)

            process_ssh_user(key, inputs, stinputs)

            process_random_password(key, inputs, stinputs)

            process_uuidgen(key, inputs, stinputs, uuidgen_deployment)

            process_openstack_ec2credentials(key, inputs, stinputs)

            process_ldap_user(key, inputs, stinputs)

            process_userinfo(key, inputs, stinputs)

            process_multiselect(key, inputs, stinputs)
        except Exception as e:
            msg = f"Error in validating deployment request: {e}"
            flash(msg, "danger")
            app.logger.error(msg)
            doprocess = False

    return doprocess, inputs, stinputs


def create_deployment(
        template,
        inputs,
        stinputs,
        form_data,
        selected_template,
        source_template,
        template_text,
        additionaldescription,
        params,
        storage_encryption,
        vault_secret_uuid,
        vault_secret_key,
):
    access_token = iam.token["access_token"]

    keep_last_attempt = 1 if "extra_opts.keepLastAttempt" in form_data else 0
    feedback_required = 1 if "extra_opts.sendEmailFeedback" in form_data else 0
    provider_timeout_mins = (
        form_data["extra_opts.providerTimeout"]
        if "extra_opts.providerTimeoutSet" in form_data
        else app.config["PROVIDER_TIMEOUT"]
    )

    user_group = (
        session["active_usergroup"]
        if "active_usergroup" in session and session["active_usergroup"] is not None
        else None
    )

    elastic = tosca_helpers.eleasticdeployment(template)
    updatable = source_template["updatable"]

    try:
        rs_json = app.orchestrator.create(
            access_token,
            user_group,
            yaml.dump(template, default_flow_style=False, sort_keys=False),
            inputs,
            keep_last_attempt,
            provider_timeout_mins,
            app.config["OVERALL_TIMEOUT"],
            app.config["CALLBACK_URL"],
        )
    except Exception as e:
        flash(str(e), "danger")
        app.logger.error("Error creating deployment: {}".format(e))
        return redirect(url_for(SHOW_HOME_ROUTE))

    # store data into database
    uuid = rs_json["uuid"]
    deployment = dbhelpers.get_deployment(uuid)
    if deployment is None:
        vphid = rs_json["physicalId"] if "physicalId" in rs_json else ""
        providername = (
            rs_json["cloudProviderName"] if "cloudProviderName" in rs_json else ""
        )

        deployment = Deployment(
            uuid=uuid,
            creation_time=rs_json["creationTime"],
            update_time=rs_json["updateTime"],
            physicalId=vphid,
            description=additionaldescription,
            status=rs_json["status"],
            outputs=json.dumps(rs_json["outputs"]),
            stoutputs=json.dumps(source_template["outputs"]),
            task=rs_json["task"],
            links=json.dumps(rs_json["links"]),
            sub=rs_json["createdBy"]["subject"],
            template=template_text,
            template_metadata=source_template["metadata_file"],
            template_parameters=source_template["parameters_file"],
            selected_template=selected_template,
            inputs=json.dumps(inputs),
            stinputs=json.dumps(stinputs),
            params=json.dumps(params),
            deployment_type=source_template["deployment_type"],
            template_type=source_template["metadata"]["template_type"],
            provider_name=providername,
            user_group=rs_json["userGroup"],
            endpoint="",
            feedback_required=feedback_required,
            keep_last_attempt=keep_last_attempt,
            remote=1,
            issuer=rs_json["createdBy"]["issuer"],
            storage_encryption=storage_encryption,
            vault_secret_uuid=vault_secret_uuid,
            vault_secret_key=vault_secret_key,
            elastic=elastic,
            updatable=updatable,
        )
        dbhelpers.add_object(deployment)

    else:
        flash(
            "Deployment with uuid:{} is already in the database!".format(uuid),
            "warning",
        )


@deployments_bp.route("/submit", methods=["POST"])
@auth.authorized_with_valid_token
def createdep():
    tosca_info, _, _, _, tosca_text = tosca.get()
    access_token = iam.token["access_token"]
    # validate input
    request_template = os.path.normpath(request.args.get("selectedTemplate"))
    if request_template not in tosca_info.keys():
        raise ValueError("Template path invalid (not found in current configuration")

    selected_template = request_template
    source_template = patch_template(
        access_token=access_token, template=copy.deepcopy(tosca_info[selected_template])
    )

    form_data = request.form.to_dict()
    additionaldescription = form_data["additional_description"]

    inputs = extract_inputs(form_data)

    template, template_text = load_template(selected_template)

    if form_data["extra_opts.schedtype"].lower() == "man":
        template = add_sla_to_template(template, form_data["extra_opts.selectedSLA"])
    else:
        remove_sla_from_template(template)
    app.logger.debug(yaml.dump(template, default_flow_style=False))

    create_dep_method(
        source_template,
        selected_template,
        additionaldescription,
        inputs,
        form_data,
        template,
        template_text,
    )

    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **SHOW_DEPLOYMENTS_KWARGS))


@deployments_bp.route("/<depid>/retry")
@auth.authorized_with_valid_token
def retrydep(depid=None):
    """
    A function to retry a failed deployment.
    Parameters:
    - depid: str, the ID of the deployment
    """
    tosca_info, _, _, _, _ = tosca.get()

    try:
        access_token = iam.token["access_token"]
    except Exception as e:
        flash("Access token not provided: \n" + str(e), "danger")

    # retrieve deployment from DB
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        flash("Deployment not found!", "warning")
        return redirect(url_for(SHOW_HOME_ROUTE))

    if dep.selected_template == "":
        flash(
            "The selected deployment is invalid. Try creating it from scratch.",
            "danger",
        )
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    inputs = process_deployment_data(dep)

    if len(inputs) > 0:
        inputs = inputs[0]

    # Get the max num retry for the new name
    max_num_retry = 0
    str_retry = " retry_"
    tmp_name = ""

    if len(dep.description.split(str_retry)) > 0:
        tmp_name = dep.description.split(str_retry)[0]

    group = None
    if "active_usergroup" in session and session["active_usergroup"] is not None:
        group = session["active_usergroup"]

    deployments = []
    try:
        deployments = app.orchestrator.get_deployments(
            access_token, created_by="me", user_group=group
        )
    except Exception as e:
        flash("Error retrieving deployment list: \n" + str(e), "danger")

    if deployments:
        result = dbhelpers.sanitizedeployments(deployments)
        deployments = result["deployments"]
        app.logger.debug("Deployments: " + str(deployments))

        for tmp_dep in deployments:
            if (
                    tmp_name + str_retry in tmp_dep.description
                    and "DELETE_COMPLETE" not in tmp_dep.status
            ):
                num_retry = 0
                split_desc = tmp_dep.description.split(str_retry)

                if len(split_desc) > 1:
                    num_retry = int(split_desc[1])

                if num_retry > max_num_retry:
                    max_num_retry = num_retry

    additionaldescription = f"{tmp_name}{str_retry}{max_num_retry + 1}"

    source_template = tosca_info.get(dep.selected_template, None)
    if source_template is None:
        flash(
            "The selected deployment is invalid. Try creating it from scratch.",
            "danger",
        )
        return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))

    form_data = inputs

    template, template_text = load_template(dep.selected_template)

    create_dep_method(
        source_template,
        dep.selected_template,
        additionaldescription,
        inputs,
        form_data,
        template,
        template_text,
    )

    flash(
        f"Retry action for deployment {dep.description} <{depid}> successfully triggered!",
        "success",
    )

    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **get_deployments_kwargs(dep.sub)))


def create_dep_method(
        source_template,
        selected_template,
        additionaldescription,
        inputs,
        form_data,
        template,
        template_text,
):
    access_token = iam.token["access_token"]

    uuidgen_deployment = str(uuid_generator.uuid1())

    doprocess, inputs, stinputs = process_inputs(
        source_template, inputs, form_data, uuidgen_deployment
    )

    # If input is a bucket_name check for validity
    for name in inputs:
        if "bucket_name" in name:
            errors = check_s3_bucket_name(uuidgen_deployment + "-" + inputs[name])

            if len(errors) > 0:
                for error in errors:
                    flash(error, "danger")
                return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **SHOW_DEPLOYMENTS_KWARGS))

    app.logger.debug(f"Calling orchestrator with inputs: {inputs}")

    if doprocess:
        storage_encryption, vault_secret_uuid, vault_secret_key = (
            add_storage_encryption(access_token, inputs)
        )
        params = {}  # is it needed??
        create_deployment(
            template,
            inputs,
            stinputs,
            form_data,
            selected_template,
            source_template,
            template_text,
            additionaldescription,
            params,
            storage_encryption,
            vault_secret_uuid,
            vault_secret_key,
        )


def check_s3_bucket_name(name):
    """
    Validates an S3 bucket name based on the given rules.

    :param name: The bucket name to validate.
    :return: A tuple (bool, list) where the bool indicates if the name is valid,
             and the list contains validation error messages (if any).
    """
    errors = []

    # Rule 1: Length between 3 and 63 characters
    if not (3 <= len(name) <= 63):
        errors.append("Bucket names must be between 3 and 63 characters long.")

    # Rule 2: Allowed characters
    if not re.match(r"^[a-z0-9.-]+$", name):
        errors.append(
            "Bucket names can only contain lowercase letters, numbers, dots (.), and hyphens (-)."
        )

    # Rule 3: Begin and end with a letter or number
    if not re.match(r"^[a-z0-9].*[a-z0-9]$", name):
        errors.append("Bucket names must begin and end with a letter or number.")

    # Rule 4: Must not contain two adjacent periods
    if ".." in name:
        errors.append("Bucket names must not contain two adjacent periods.")

    # Rule 5: Must not be formatted as an IP address
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", name):
        errors.append(
            "Bucket names must not be formatted as an IP address (e.g., 192.168.5.4)."
        )

    # Rule 6: Must not start with prohibited prefixes
    prohibited_prefixes = ["xn--", "sthree-", "sthree-configurator", "amzn-s3-demo-"]
    if any(name.startswith(prefix) for prefix in prohibited_prefixes):
        errors.append(
            f"Bucket names must not start with the prefixes: {', '.join(prohibited_prefixes)}."
        )

    # Rule 7: Must not end with prohibited suffixes
    prohibited_suffixes = ["-s3alias", "--ol-s3", ".mrap", "--x-s3"]
    if any(name.endswith(suffix) for suffix in prohibited_suffixes):
        errors.append(
            f"Bucket names must not end with the suffixes: {', '.join(prohibited_suffixes)}."
        )

    # Rule 8: Bucket names must be unique across AWS accounts
    # This rule cannot be validated here; it's enforced by AWS.

    return errors


def delete_secret_from_vault(access_token, secret_path):
    vault_bound_audience = app.config.get("VAULT_BOUND_AUDIENCE")
    vault_delete_policy = app.config.get("DELETE_POLICY")
    vault_delete_token_time_duration = app.config.get("DELETE_TOKEN_TIME_DURATION")
    vault_delete_token_renewal_time_duration = app.config.get(
        "DELETE_TOKEN_RENEWAL_TIME_DURATION"
    )
    vault_role = app.config.get("VAULT_ROLE")

    jwt_token = auth.exchange_token_with_audience(
        app.settings.iam_url,
        app.settings.iam_client_id,
        app.settings.iam_client_secret,
        access_token,
        vault_bound_audience,
    )

    vault_client = vaultservice.connect(jwt_token, vault_role)

    delete_token = vault_client.get_token(
        vault_delete_policy,
        vault_delete_token_time_duration,
        vault_delete_token_renewal_time_duration,
    )

    vault_client.delete_secret(delete_token, secret_path)


def add_storage_encryption(access_token, inputs):
    vault_url = app.config.get("VAULT_URL")
    vault_role = app.config.get("VAULT_ROLE")
    vault_bound_audience = app.config.get("VAULT_BOUND_AUDIENCE")
    vault_wrapping_token_time_duration = app.config.get("WRAPPING_TOKEN_TIME_DURATION")
    vault_write_policy = app.config.get("WRITE_POLICY")
    vault_write_token_time_duration = app.config.get("WRITE_TOKEN_TIME_DURATION")
    vault_write_token_renewal_time_duration = app.config.get(
        "WRITE_TOKEN_RENEWAL_TIME_DURATION"
    )

    storage_encryption = 0
    vault_secret_uuid = ""
    vault_secret_key = ""
    if (
            "storage_encryption" in inputs
            and inputs["storage_encryption"].lower() == "true"
    ):
        storage_encryption = 1
        vault_secret_key = "secret"

    if storage_encryption == 1:
        inputs["vault_url"] = vault_url
        vault_secret_uuid = str(uuid_generator.uuid4())
        if "vault_secret_key" in inputs:
            vault_secret_key = inputs["vault_secret_key"]
        app.logger.debug("Storage encryption enabled, appending wrapping token.")

        jwt_token = auth.exchange_token_with_audience(
            app.settings.iam_url,
            app.settings.iam_client_id,
            app.settings.iam_client_secret,
            access_token,
            vault_bound_audience,
        )

        vault_client = vaultservice.connect(jwt_token, vault_role)

        wrapping_token = vault_client.get_wrapping_token(
            vault_wrapping_token_time_duration,
            vault_write_policy,
            vault_write_token_time_duration,
            vault_write_token_renewal_time_duration,
        )

        inputs["vault_wrapping_token"] = wrapping_token
        inputs["vault_secret_path"] = session["userid"] + "/" + vault_secret_uuid

    return storage_encryption, vault_secret_uuid, vault_secret_key


@deployments_bp.route("/sendportsreq", methods=["POST"])
@auth.authorized_with_valid_token
def sendportsrequest():
    form_data = request.form.to_dict()

    try:
        utils.send_ports_request_email(
            form_data["deployment_uuid"],
            email=form_data["email"],
            message=form_data["message"],
        )

        flash(
            "Your request has been sent to the support team. \
                You will receive soon a notification email about your request. Thank you!",
            "success",
        )

    except Exception:
        utils.logexception("sending email:".format())
        flash(
            "Sorry, an error occurred while sending your request. Please retry.",
            "danger",
        )

    return redirect(url_for(SHOW_DEPLOYMENTS_ROUTE, **SHOW_DEPLOYMENTS_KWARGS))