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

from datetime import datetime
from typing import Any, Optional

import requests
from flask import current_app as app
from flask import flash, session

from app.lib import path_utils


def get(
    *,
    access_token: str,
    entity: str,
    uid: Optional[str] = None,
    version: str = "v1",
    timeout: int = 60,
    **kwargs,
):
    """Execute generic get on Fed-Reg."""
    if app.settings.use_fed_reg:
        url = path_utils.url_path_join(app.settings.fed_reg_url, version, entity)
        if uid is not None:
            url = path_utils.url_path_join(url, uid)

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
    return get(
        access_token=access_token, entity="projects", uid=uid, timeout=timeout, **kwargs
    )


def get_providers(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all providers details and related entities."""
    return get(access_token=access_token, entity="providers", timeout=timeout, **kwargs)


def get_provider(*, access_token: str, uid: str, timeout: int = 60, **kwargs):
    """Retrieve single provider details and related entities."""
    return get(
        access_token=access_token,
        entity="providers",
        uid=uid,
        timeout=timeout,
        **kwargs,
    )


def get_user_groups(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all user groups details and related entities."""
    return get(
        access_token=access_token, entity="user_groups", timeout=timeout, **kwargs
    )


def get_user_group(*, access_token: str, uid: str, timeout: int = 60, **kwargs):
    """Retrieve all user groups details and related entities."""
    return get(
        access_token=access_token,
        entity="user_groups",
        uid=uid,
        timeout=timeout,
        **kwargs,
    )


def get_flavors(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all flavors details and related entities."""
    return get(access_token=access_token, entity="flavors", timeout=timeout, **kwargs)


def get_images(*, access_token: str, timeout: int = 60, **kwargs):
    """Retrieve all images details and related entities."""
    return get(access_token=access_token, entity="images", timeout=timeout, **kwargs)


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
                        "provider_id": provider["uid"],
                        "provider_name": provider["name"],
                        "service_type": service["name"],
                        "endpoint": service["endpoint"],
                        "region_name": region["name"],
                    }
    app.logger.debug("Extracted services: {}".format(slas))

    # For providers with multiple services (and regions) append to the sitename
    # the service's target region name
    provider_names = [i["provider_name"] for i in slas.values()]
    d = {k: provider_names.count(v["provider_name"]) for k, v in slas.items()}
    for k, v in d.items():
        if v > 1:
            slas[k]["sitename"] = (
                slas[k]["provider_name"] + " - " + slas[k]["region_name"]
            )
        else:
            slas[k]["sitename"] = slas[k]["provider_name"]

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


def retrieve_active_user_group(*, access_token: str):
    """Retrieve the active user group data."""
    # From session retrieve current user group name and issuer
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


def filter_resources(
    resources: list[dict],
    *,
    project_uid: str,
    provider_uid: str,
    region_name: Optional[str] = None,
) -> list[dict]:
    """Filter resources (flavors and images).

    Keep public resources or private ones accessible from the target project and
    belonging to the same region-provider couples.
    """
    filtered = []
    for resource in resources:
        services = resource.get("services", None)
        if services is None:
            service = resource.get("service", None)
            services = [] if service is None else [service]
        for service in services:
            if (
                service["region"]["provider"]["uid"] == provider_uid
                and (region_name is None or service["region"]["name"] == region_name)
                and (
                    resource.get("is_public", False)
                    or resource.get("is_shared", False)
                    or project_uid in [i["uid"] for i in resource.get("projects", [])]
                )
            ):
                filtered.append(resource)
    return filtered


def remap_flavors(flavors: list[dict]) -> dict[str, dict]:
    """Keep only flavors' relevant values and remove duplicates.

    Keep vcpus, disk, ram, gpus and gpu model attributes.
    Define the flavor unique name based on its attributes.
    Keep only one flavor for each of these names.
    """
    MB = 1024.0
    d = {}
    for flavor in flavors:
        ram_d = float(flavor["ram"])
        if ram_d % MB != 0:
            ram_f = "{:.1f}"
        else:
            ram_f = "{:.0f}"
        ram = ram_d / MB
        cpu = int(flavor["vcpus"])
        disk = int(flavor["disk"])
        gpus = int(flavor["gpus"])
        gpu_model = flavor["gpu_model"]
        name = ",".join((str(cpu), str(ram), str(gpus), str(disk)))
        if name not in d:
            f = {
                "name": name,
                "cpu": cpu,
                "ram": ram,
                "ram_f": ram_f,
                "disk": disk,
                "gpus": gpus,
                "gpu_model": gpu_model,
                "enable_gpu": gpus > 0,
            }
            d[name] = f
    return d


def remap_images(images: list[dict]) -> dict[str, dict]:
    """Keep only images' relevant values and remove duplicates.

    Keep OS distro, OS version, name, description, creation time and support for GPUs.
    Define the image unique name based on its attributes.
    Keep only one image for each of these names.
    When there is a duplicate, keep the most recent one.
    """
    d = {}
    for image in images:
        os_distro = image["os_distro"]
        os_version = image["os_version"]
        description = image["description"]
        name = ",".join((str(os_distro), str(os_version), str(description)))
        created_at = datetime.strptime(image["created_at"], "%Y-%m-%dT%H:%M:%S%z")
        if name not in d or created_at > datetime.strptime(
            d[name]["created_at"],
            "%Y-%m-%dT%H:%M:%S%z",
        ):
            i = {
                "name": image["name"],
                "description": description,
                "os_distro": os_distro,
                "os_version": os_version,
                "gpu_driver": image["gpu_driver"],
                "created_at": image["created_at"],
            }
            d[name] = i
    return d


def make_image_label(
    *,
    distro: Optional[str],
    version: Optional[str],
    description: Optional[str],
    name: Optional[str],
) -> str:
    """Build the image label to show on the dashboard."""
    if description and version and distro:
        return "{} {} ( {} )".format(distro, version, description)
    if version and distro:
        return "{} {}".format(distro, version)
    if name:
        return name
    return "no label"


def make_flavor_label(
    *,
    cpu: Optional[int],
    ram: Optional[float],
    disk: Optional[int],
    gpus: Optional[int],
    ram_f: Optional[str],
) -> str:
    """Build the flavor label to show on the dashboard."""
    if gpus > 0 and disk > 0:
        return ("{} VCPUs, " + ram_f + " GB RAM, {} GB DISK, {} GPUS").format(
            cpu, ram, disk, gpus
        )
    if gpus > 0:
        return ("{} VCPUs, " + ram_f + " GB RAM, {} GPUs").format(cpu, ram, gpus)
    if disk > 0:
        return ("{} VCPUs, " + ram_f + " GB RAM, {} GB DISK").format(cpu, ram, disk)
    return ("{} VCPUs, " + ram_f + " GB RAM").format(cpu, ram)


def sort_and_prepare_flavors(flavors: dict[str, dict]) -> list[dict]:
    """Sort flavors and return a list of dict with filtered values for the dashboard."""
    all = []
    no_gpu = []
    with_gpu = []
    sorted_flavors = dict(
        sorted(
            flavors.items(),
            key=lambda x: [
                x[1]["cpu"],
                x[1]["ram"],
                x[1]["gpus"],
                x[1]["disk"],
            ],
        )
    )
    for i, v in enumerate(sorted_flavors.values()):
        flavor = {
            "value": "{}".format(i + 1),
            "label": make_flavor_label(
                cpu=v["cpu"],
                ram=v["ram"],
                disk=v["disk"],
                gpus=v["gpus"],
                ram_f=v["ram_f"],
            ),
            "set": {
                "num_cpus": "{}".format(v["cpu"]),
                "mem_size": (v["ram_f"] + " GB").format(v["ram"]),
                "disk_size": "{} GB".format(v["disk"]),
                "num_gpus": "{}".format(v["gpus"]),
                "gpu_model": "{}".format(v["gpu_model"]),
                "enable_gpu": "{}".format(v["enable_gpu"]),
            },
        }
        all.append(flavor)
        if v["enable_gpu"] == True:
            with_gpu.append(flavor)
        else:
            no_gpu.append(flavor)
    return all, no_gpu, with_gpu


def sort_and_prepare_images(images: dict[str, dict]) -> list[dict]:
    """Sort images and return a list of dict with filtered values for the dashboard."""
    outputs = []
    sorted_images = dict(
        sorted(
            images.items(),
            key=lambda x: (
                (x[1]["os_distro"] is None, x[1]["os_distro"]),
                (x[1]["os_version"] is None, x[1]["os_version"]),
            ),
        )
    )
    for i, v in enumerate(sorted_images.values()):
        image = {
            "value": "{}".format(i + 1),
            "label": make_image_label(
                distro=v["os_distro"],
                version=v["os_version"],
                description=v["description"],
                name=v["name"],
            ),
            "set": {
                "os_distribution": "{}".format(v["os_distro"]),
                "os_version": "{}".format(v["os_version"]),
            },
        }
        outputs.append(image)
    return outputs


def retrieve_active_user_group_resources(
    *,
    access_token: str,
    user_group: Any,
    sla_id: Optional[str] = None,
    region_name: Optional[str] = None,
) -> tuple[list[dict], list[dict]]:
    # TODO: initialize with the original template values so
    # if the try-except fails it returns the template defaults

    # Retrieve all flavors and images
    try:
        fed_reg_flavors = get_flavors(access_token=access_token, with_conn=True)
    except Exception as e:
        flash("Error retrieving flavors data: \n" + str(e), "warning")

    try:
        fed_reg_images = get_images(access_token=access_token, with_conn=True)
    except Exception as e:
        flash("Error retrieving flavors data: \n" + str(e), "warning")

    # Filter flavors and images accessible to the user group
    # and matching the target provider if defined
    project_flavors = []
    project_images = []
    for sla in user_group["slas"]:
        if sla_id is None or sla["uid"] == sla_id:
            for project in sla["projects"]:
                project_flavors += filter_resources(
                    region_name=region_name,
                    project_uid=project["uid"],
                    provider_uid=project["provider"]["uid"],
                    resources=fed_reg_flavors,
                )
                project_images += filter_resources(
                    region_name=region_name,
                    project_uid=project["uid"],
                    provider_uid=project["provider"]["uid"],
                    resources=fed_reg_images,
                )

    # Handle flavors and images list: get useful fields and remove duplicates
    temp_flavors = remap_flavors(project_flavors)
    temp_images = remap_images(project_images)

    # Sort flavors and images
    sorted_flavors, sorted_nogpu_flavors, sorted_gpu_flavors = sort_and_prepare_flavors(temp_flavors)
    sorted_images = sort_and_prepare_images(temp_images)

    return sorted_flavors, sorted_nogpu_flavors, sorted_gpu_flavors, sorted_images
