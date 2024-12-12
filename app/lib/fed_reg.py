# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2024
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

from app.lib import utils
from typing import Any, Optional

import requests

from flask import current_app as app, flash, session


def get(
    *,
    access_token: str,
    entity: str,
    uid: Optional[str] = None,
    version: str = "v1",
    timeout: int = 60,
    **kwargs,
):
    if app.settings.use_fed_reg:
        """Execute generic get on Fed-Reg."""
        url = utils.url_path_join(app.settings.fed_reg_url, version, entity)
        if uid is not None:
            url = utils.url_path_join(url, uid)

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {**kwargs}

        app.logger.debug("Request URL: {}".format(url))
        app.logger.debug("Request params: {}".format(params))

        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        app.logger.debug("Retrieved {}: {}".format(entity, resp.json()))

        return resp.json()

    return None

def get_projects(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all projects details and related entities."""
    return get(access_token=access_token, entity="projects", timeout=timeout, **kwargs)


def get_project(*, access_token: str, uid: str, timeout: int = 60, **kwargs):
    """Retrieve single project details and related entities."""
    return get(access_token=access_token, entity="projects", uid=uid, timeout=timeout, **kwargs)


def get_providers(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all providers details and related entities."""
    return get(access_token=access_token, entity="providers", timeout=timeout, **kwargs)


def get_provider(*, access_token: str, uid: str, timeout: int = 60, **kwargs):
    """Retrieve single provider details and related entities."""
    return get(access_token=access_token, entity="providers", uid=uid, timeout=timeout, **kwargs)


def get_user_groups(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all user groups details and related entities."""
    return get(access_token=access_token, entity="user_groups", timeout=timeout, **kwargs)


def get_user_group(*, access_token: str, uid: str, timeout: int = 60, **kwargs):
    """Retrieve all user groups details and related entities."""
    return get(access_token=access_token, entity="user_groups", uid=uid, timeout=timeout, **kwargs)


def get_flavors(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all flavors details and related entities."""
    return get(access_token=access_token, entity="flavors", timeout=timeout, **kwargs)


def deployment_supports_service(*, deployment_type: str, service_name: str):
    """A deployment type supports only specific service categories."""
    if deployment_type == "CLOUD":
        return service_name in ["org.openstack.nova", "com.amazonaws.ec2"]
    if deployment_type == "MARATHON":
        return service_name in ["eu.indigo-datacloud.marathon"]
    if deployment_type == "CHRONOS":
        return service_name in ["eu.indigo-datacloud.chronos"]
    if deployment_type == "QCG":
        return service_name in ["eu.deep.qcg"]
    return True


def remap_slas_from_user_group(
    *,
    user_group: dict[str, Any],
    service_type: Optional[str] = None,
    deployment_type: Optional[str] = None,
) -> list[dict[str, str]]:
    """Extract from a user group related entities the SLA.

    Map data to be backward compatible with the previous version.
    """
    slas = {}
    for sla in user_group["slas"]:
        for project in sla["projects"]:
            provider = project["provider"]
            for quota in project["quotas"]:
                service = quota["service"]
                region = service["region"]
                if (
                    sla.get(service["uid"], None) is None
                    and (service_type is None or service["type"] == service_type)
                    and deployment_supports_service(
                        deployment_type=deployment_type, service_name=service["name"]
                    )
                ):
                    slas[service["uid"]] = {
                        "id": sla["uid"],
                        "sitename": provider["name"],
                        "service_type": service["name"],
                        "endpoint": service["endpoint"],
                        "region": region["name"],
                    }
    app.logger.debug("Extracted services: {}".format(slas))

    # For providers with multiple services (and regions) append to the sitename
    # the service's target region name
    provider_names = [i["sitename"] for i in slas.values()]
    d = {k: provider_names.count(v["sitename"]) for k, v in slas.items()}
    for k, v in d.items():
        if v > 1:
            slas[k]["sitename"] = slas[k]["sitename"] + " - " + slas[k]["region"]

    app.logger.debug("Renamed sitenames: {}".format(slas))
    return [i for i in slas.values()]


def retrieve_slas_from_active_user_group(
    *,
    access_token: str,
    service_type: Optional[str] = None,
    deployment_type: Optional[str] = None,
) -> list[dict[str, str]]:

    slas = []
    try:
        active_group = retrieve_active_user_group(access_token=access_token)
        if active_group is not None:
            # Retrieve linked user group services
            slas = remap_slas_from_user_group(
                user_group=active_group,
                service_type=service_type,
                deployment_type=deployment_type,
            )

    except Exception as e:
        flash("Error retrieving user group slas: \n" + str(e), "warning")

    return slas


def retrieve_active_user_group(
    *,
    access_token: str,
):
    """Retrieve the active user group data."""
    # From session retrieve current user group name and issuer
    if app.settings.use_fed_reg:
        if "active_usergroup" in session and session["active_usergroup"] is not None:
            user_group_name = session["active_usergroup"]
        else:
            user_group_name = session["organisation_name"]
        issuer = session["iss"]

        try:
            # Retrieve target user group and related entities
            user_groups = get_user_groups(
                access_token=access_token,
                name=user_group_name,
                idp_endpoint=issuer,
                with_conn=True,
                provider_status="active",
            )
            assert len(user_groups) == 1, "Invalid number of returned user groups"

            # Retrieve linked user group services
            return user_groups[0]

        except Exception as e:
            flash("Error retrieving active user group data: \n" + str(e), "warning")
            return None
    return None

def retrieve_flavors_from_active_user_group(
    *,
    access_token: str,
) -> list[dict]:

    flavors = []

    if app.settings.use_fed_reg:
        temp_flavors = {}
        idx = 1

        try:
            user_group = retrieve_active_user_group(
                access_token=access_token
            )
            if user_group is not None:
                for sla in user_group["slas"]:
                    for project in sla["projects"]:
                        project_flavors = get_project(
                            access_token=access_token,
                            with_conn=True,
                            uid=project['uid']
                        )["flavors"]
                        # get useful fields and remove duplicates
                        for flavor in project_flavors:
                            if flavor["is_public"] == True:
                                ram = int(flavor["ram"] / 1024)
                                cpu = int(flavor["vcpus"])
                                disk = int (flavor["disk"])
                                gpus = int(flavor["gpus"])
                                gpu_model = flavor["gpu_model"]
                                name = ",".join((str(cpu),str(ram),str(gpus),str(disk)))
                                if not name in temp_flavors:
                                    f = {
                                        "name": name,
                                        "cpu": cpu,
                                        "ram": ram,
                                        "disk": disk,
                                        "gpus": gpus,
                                        "gpu_model": gpu_model,
                                        "enable_gpu": True if gpus > 0 else False
                                    }
                                    temp_flavors[name] = f
                # sort flavors
                sorted_flavors = {k: v for k, v in sorted(temp_flavors.items(),
                                            key=lambda x: (x[1]['cpu'], x[1]['ram'], x[1]['gpus'], x[1]['disk']))}
                # create list
                for f in sorted_flavors.values():
                    flavor = {
                                "value": "{}".format(idx),
                                "label": make_flavor_label(
                                    cpu = f["cpu"],
                                    ram = f["ram"],
                                    disk = f["disk"],
                                    gpus = f["gpus"]
                                ),
                                "set": {"num_cpus": "{}".format(f["cpu"]),
                                        "mem_size": "{} GB".format(f["ram"]),
                                        "disk_size": "{} GB".format(f["disk"]),
                                        "num_gpus": "{}".format(f["gpus"]),
                                        "gpu_model": "{}".format(f["gpu_model"]),
                                        "enable_gpu": "{}".format(f["enable_gpu"])
                                        }
                            }
                    flavors.append(flavor)
                    idx+=1

        except Exception as e:
            flash("Error retrieving user group flavors: \n" + str(e), "warning")

    return flavors

def make_flavor_label(
        *,
        cpu: int,
        ram: int,
        disk: int,
        gpus: int
):
    if gpus > 0 and disk > 0:
        return "{} VCPUs, {} GB RAM, {} GB DISK, {} GPUS".format(cpu, ram, disk, gpus)
    if gpus > 0:
        return "{} VCPUs, {} GB RAM, {} GPUs".format(cpu, ram, gpus)
    if disk > 0:
        return "{} VCPUs, {} GB RAM, {} GB DISK".format(cpu, ram, disk)
    return "{} VCPUs, {} GB RAM".format(cpu, ram)