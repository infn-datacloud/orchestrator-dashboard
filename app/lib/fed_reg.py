import os
from typing import Any, Optional

import requests

from flask import current_app as app, flash, session


def get_user_groups(timeout: int = 60, *, access_token: str, **kwargs):
    """Retrieve all user group details and related entities."""
    url = os.path.join(app.settings.fed_reg_url, "user_groups")
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {**kwargs}

    app.logger.debug("Request URL: {}".format(url))
    app.logger.debug("Request params: {}".format(params))

    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    app.logger.debug("Retrieved user groups: {}".format(resp.json()))

    return resp.json()


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
                        "id": provider["uid"],
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


def retrieve_slas_from_specific_user_group(
    *,
    access_token: str,
    service_type: Optional[str] = None,
    deployment_type: Optional[str] = None,
) -> list[dict[str, str]]:
    """Retrieve the SLAs associated to the current user group."""
    # From session retrieve current user group and issuer
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
        )
        assert len(user_groups) == 1, "Invalid number of returned user groups"

        # Retrieve linked user group services
        return remap_slas_from_user_group(
            user_group=user_groups[0],
            service_type=service_type,
            deployment_type=deployment_type,
        )

    except Exception as e:
        flash("Error retrieving user groups list: \n" + str(e), "warning")
