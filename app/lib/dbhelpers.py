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

import ast
from datetime import datetime, date
import calendar

from typing import Any, Optional

from dateutil import parser
from flask import current_app as app
from flask import json
from flask import session

from app.extensions import db
from app.iam import iam

from app.models.Deployment import Deployment
from app.models.Service import Service
from app.models.UsersGroup import UsersGroup
from app.models.User import User
from app.models.Setting import Setting
from app.models.DbVersion import DbVersion


def add_object(object):
    db.session.add(object)
    db.session.commit()


def remove_object(object):
    db.session.remove(object)
    db.session.commit()


def get_user(subject):
    return User.query.get(subject)


def get_users():
    users = User.query.order_by(User.family_name.desc(), User.given_name.desc()).all()
    return users


def update_user(subject, data):
    User.query.filter_by(sub=subject).update(data)
    db.session.commit()


def get_admins_email():
    admins = User.query.filter_by(role="admin").all()
    return [user.email for user in admins]


def get_ssh_pub_key(subject):
    user = User.query.get(subject)
    return user.sshkey


def delete_ssh_key(subject):
    User.query.get(subject).sshkey = None
    db.session.commit()


def update_deployment(depuuid, data):
    Deployment.query.filter_by(uuid=depuuid).update(data)
    db.session.commit()


def get_deployment(uuid):
    return Deployment.query.get(uuid)


def getdeploymenttype(dep):
    deptype = ""
    if "cloudProviderEndpoint" in dep:
        endpoint = dep["cloudProviderEndpoint"]
        if "deploymentType" in endpoint:
            etype = endpoint["deploymentType"]
            if (
                etype == "OPENSTACK"
                or etype == "OPENNEBULA"
                or etype == "AWS"
                or etype == "OTC"
                or etype == "AZURE"
            ):
                deptype = "CLOUD"
            else:
                deptype = etype
        else:
            iaas_type = endpoint.get("iaasType", "")
            if iaas_type in ["OPENSTACK", "OPENNEBULA", "AWS", "OTC", "AZURE"]:
                return "CLOUD"
            return iaas_type
    return deptype


def get_provider_type(dep: dict[str:Any]) -> Optional[str]:
    """Return deployment's provider type if provided."""
    endpoint = dep.get("cloudProviderEndpoint", None)
    if endpoint is not None:
        return endpoint.get("iaasType", None)
    return None


def get_deployment_region(dep: dict[str:Any]) -> Optional[str]:
    """Return deployment's region if provided."""
    endpoint = dep.get("cloudProviderEndpoint", None)
    if endpoint is not None:
        return endpoint.get("region", None)
    return None


def sanitizedeployments(deployments):

    deps = list()

    access_token = iam.token["access_token"]
    providers = app.config.get("PROVIDER_NAMES_TO_SPLIT", None)
    dtformat = "%Y-%m-%d %H:%M:%S"

    # update deployments status in database
    for dep_json in deployments:
        uuid = dep_json["uuid"]

        # sanitize date
        dt = parser.parse(dep_json["creationTime"])
        dep_json["creationTime"] = dt.strftime(dtformat)
        creation_time = datetime.strptime(dep_json["creationTime"], dtformat)

        dt = parser.parse(dep_json["updateTime"])
        dep_json["updateTime"] = dt.strftime(dtformat)
        update_time = datetime.strptime(dep_json["updateTime"], dtformat)

        providername = dep_json["cloudProviderName"] if "cloudProviderName" in dep_json else ""
        # Older deployments saved as provider name both the provider name and the
        # region, but in the Fed-Reg they are separate details.
        if providername != "" and providers and providername in ast.literal_eval(
            providers
        ):
            providername, region_name = providername.split("-")
            region_name = region_name.lower()
        else:
            region_name = get_deployment_region(dep_json)
        provider_type = get_provider_type(dep_json)
        max_length = 65535
        status_reason = dep_json.get("statusReason", "")[:max_length]
        subject = dep_json["createdBy"]["subject"]
        vphid = dep_json["physicalId"] if "physicalId" in dep_json else ""

        dep = get_deployment(uuid)

        if dep is not None:
            if (
                dep.status != dep_json["status"]
                or dep.provider_name != providername
                or dep.provider_type != provider_type
                or dep.region_name != region_name
                or str(dep.status_reason or "") != status_reason
            ):
                dep.update_time = update_time
                dep.physicalId = vphid
                dep.status = dep_json["status"]
                dep.outputs = json.dumps(dep_json["outputs"])
                dep.task = dep_json["task"]
                dep.links = json.dumps(dep_json["links"])
                dep.remote = 1
                dep.provider_name = providername
                dep.provider_type = provider_type
                dep.region_name = region_name
                dep.status_reason = status_reason

                add_object(dep)

            deps.append(dep)
        else:
            app.logger.info("Deployment with uuid:{} not found!".format(uuid))

            # retrieve template
            try:
                template = app.orchestrator.get_template(access_token, uuid)
            except Exception:
                template = ""

            # insert missing deployment in database
            endpoint = (
                dep_json["outputs"]["endpoint"]
                if "endpoint" in dep_json["outputs"]
                else ""
            )

            try:
                #check user existence
                user = get_user(subject)
                #create inactive unknown user if not exists
                if user is None:
                    user = User(
                        sub=subject,
                        name="unknown",
                        username=subject,
                        given_name="unknown",
                        family_name="unknown",
                        email="unknown",
                        organisation_name=session["organisation_name"],
                        role="user",
                        active=0
                    )

                    add_object(user)

                deployment = Deployment(
                    uuid=uuid,
                    creation_time=creation_time,
                    update_time=update_time,
                    physicalId=vphid,
                    description="",
                    status=dep_json["status"],
                    outputs=json.dumps(dep_json["outputs"]),
                    stoutputs="",
                    task=dep_json["task"],
                    links=json.dumps(dep_json["links"]),
                    sub=subject,
                    template=template,
                    template_parameters="",
                    template_metadata="",
                    selected_template="",
                    inputs=json.dumps(dep_json.get("inputs", "")),
                    stinputs=json.dumps(dep_json.get("stinputs", "")),
                    params="",
                    deployment_type=getdeploymenttype(dep_json),
                    provider_name=providername,
                    provider_type=provider_type,
                    region_name=region_name,
                    user_group=dep_json.get("userGroup"),
                    endpoint=endpoint,
                    remote=1,
                    locked=0,
                    feedback_required=0,
                    keep_last_attempt=0,
                    issuer=dep_json["createdBy"]["issuer"],
                    storage_encryption=0,
                    vault_secret_uuid="",
                    vault_secret_key="",
                    elastic=0,
                    updatable=0,
                )

                add_object(deployment)

                deps.append(deployment)
            except Exception:
                app.logger.info("Error sanitizing deployment with uuid:{}".format(uuid))

    return deps


def get_all_statuses():
    return list(["CREATE_COMPLETE","CREATE_IN_PROGRESS","CREATE_FAILED","UPDATE_COMPLETE","UPDATE_IN_PROGRESS","UPDATE_FAILED","DELETE_COMPLETE","DELETE_IN_PROGRESS","DELETE_FAILED"])


def get_active_statuses():
    return list(["CREATE_COMPLETE","CREATE_IN_PROGRESS","CREATE_FAILED","UPDATE_COMPLETE","UPDATE_IN_PROGRESS","UPDATE_FAILED","DELETE_IN_PROGRESS","DELETE_FAILED"])


def get_inactive_statuses():
    return list(["DELETE_COMPLETE"])


def build_excludedstatus_filter(status):
    if "all" in status:
        return None
    if "actives" in status:
        slist = get_inactive_statuses()
        sfilter = list()
    else:
        slist = get_all_statuses()
        sfilter = status
    excluded_status = ""
    for st in slist:
        if not st in sfilter:
            if excluded_status != "":
                excluded_status += ","
            excluded_status += st
    return excluded_status


def month_boundary(ym_str: str, first_day: bool = True) -> date:
    """
    Converte una stringa 'YYYY-MM' in una data:
    - Se first_day è True, restituisce il primo giorno del mese
    - Se False, restituisce l'ultimo giorno del mese
    - Se errore ritorna None
    """
    try:
        dt = datetime.strptime(ym_str, "%Y-%m")
    except ValueError:
        return None

    year, month = dt.year, dt.month

    if first_day:
        return date(year, month, 1)
    else:
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)


def months_list(start, end):
    """Restituisce una lista di stringhe 'YYYY-MM' tra due date (incluse).
    I parametri possono essere oggetti `date` o stringhe 'YYYY-MM'.
    """
    if isinstance(start, str):
        start_date = datetime.strptime(start, "%Y-%m").date()
    else:
        start_date = date(start.year, start.month, 1)

    if isinstance(end, str):
        end_date = datetime.strptime(end, "%Y-%m").date()
    else:
        end_date = date(end.year, end.month, 1)

    # Genera la lista
    result = []
    current = start_date

    while current <= end_date:
        result.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return result


def filter_date_range(deployments, start, end, negate):
    def iterator_func(x):
        if (start is None or x.creation_time.date() >= start) and \
                (end is None or x.creation_time.date() <= end):
            return negate
        return not negate
    return list(filter(iterator_func, deployments))


def filter_status(deployments, search_string_list, negate):
    def iterator_func(x):
        if x.status in search_string_list:
            return negate
        return not negate
    return list(filter(iterator_func, deployments))


def filter_group(deployments, search_string_list, negate):
    def iterator_func(x):
        if x.user_group in search_string_list:
            return negate
        return not negate
    return list(filter(iterator_func, deployments))


def filter_template(deployments, search_string_list, negate):
    def iterator_func(x):
        template = x.selected_template or "UNKNOWN"
        if template in search_string_list:
            return negate
        return not negate
    return list(filter(iterator_func, deployments))


def filter_provider(deployments, search_string_list, negate, providers_to_split):
    def iterator_func(x):
        provider = buildprovidername(providers_to_split, x.provider_name, x.region_name)
        if provider in search_string_list:
            return negate
        return not negate
    return list(filter(iterator_func, deployments))


def buildprovidername(providers_to_split, dep_provider, dep_region_name):
    provider = dep_provider or "UNKNOWN"
    if dep_region_name:
        provider_ext = (provider + "-" + dep_region_name).lower()
        if providers_to_split and provider_ext in providers_to_split:
            return provider + "-" + dep_region_name.lower()
    return provider


def nullorempty(value):
    return True if value is None or value == "" or value == "None" else False

def notnullorempty(value):
    return not nullorempty(value)


def defaulttoempty(value):
    return value if value is not None else ""


def cvdeployments(deps):
    deployments = []
    for d in deps:
        deployments.append(cvdeployment(d))
    return deployments


def cvdeployment(d):
    deployment = Deployment(
        uuid=d.uuid,
        creation_time=d.creation_time,
        update_time=d.update_time,
        physicalId=defaulttoempty(d.physicalId),
        description=d.description,
        status=d.status,
        status_reason=d.status_reason,
        outputs=json.loads(d.outputs.replace("\n", "\\n")) if notnullorempty(d.outputs) else "",
        stoutputs=json.loads(d.stoutputs.replace("\n", "\\n")) if notnullorempty(d.stoutputs) else "",
        task=d.task,
        links=json.loads(d.links.replace("\n", "\\n")) if notnullorempty(d.links) else "",
        sub=d.sub,
        template=d.template,
        template_parameters=defaulttoempty(d.template_parameters),
        template_metadata=defaulttoempty(d.template_metadata),
        selected_template=d.selected_template,
        inputs=json.loads(d.inputs.replace("\n", "\\n")) if notnullorempty(d.inputs) else "",
        stinputs=json.loads(d.stinputs.replace("\n", "\\n")) if notnullorempty(d.stinputs) else "",
        params=d.params,
        deployment_type=d.deployment_type,
        provider_name=defaulttoempty(d.provider_name),
        provider_type=d.provider_type,
        region_name=d.region_name,
        user_group=defaulttoempty(d.user_group),
        endpoint=d.endpoint,
        remote=d.remote,
        locked=d.locked,
        issuer=d.issuer,
        feedback_required=d.feedback_required,
        keep_last_attempt=d.keep_last_attempt,
        storage_encryption=d.storage_encryption,
        vault_secret_uuid=defaulttoempty(d.vault_secret_uuid),
        vault_secret_key=defaulttoempty(d.vault_secret_key),
        elastic=d.elastic,
        updatable=d.updatable,
    )
    return deployment


def get_services(visibility, groups=[]):
    services = []
    if visibility == "public":
        services = Service.query.filter_by(visibility="public").all()
    if visibility == "private":
        services = []
        ss = Service.query.all()
        for s in ss:
            s_groups = [g.name for g in s.groups]
            if not set(s_groups).isdisjoint(groups):
                services.append(s)
    if visibility == "all":
        services = Service.query.all()

    return services


def get_service(id):
    return Service.query.get(id)


def __update_service(s, data):
    s.name = data.get("name")
    s.description = data.get("description")
    s.url = data.get("url")
    if data.get("icon"):
        s.icon = data.get("icon")
    s.visibility = data.get("visibility")
    s.groups = []

    if s.visibility == "private":
        for g in data.get("groups"):
            group = get_usergroup(g)
            if not group:
                group = UsersGroup()
                group.name = g
            s.groups.append(group)


def update_service(id, data):
    s = Service.query.filter_by(id=id).first()
    __update_service(s, data)
    db.session.add(s)
    db.session.commit()


def delete_service(id):
    service = Service.query.filter_by(id=id).first()
    db.session.delete(service)
    db.session.commit()


def add_service(data):
    s = Service()
    __update_service(s, data)
    db.session.add(s)
    db.session.commit()


def get_usergroup(name):
    return UsersGroup.query.get(name)


def get_usergroups():
    return UsersGroup.query.all()


def get_setting(id):
    return Setting.query.get(id)


def get_settings():
    return Setting.query.all()


def update_setting(id, data):
    Setting.query.filter_by(id=id).update(data)
    db.session.commit()


def get_dbversion():
    return DbVersion.query.all()[0].version_num
