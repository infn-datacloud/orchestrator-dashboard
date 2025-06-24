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
from flask import current_app as app


def get_all_groups(
    access_token
):

    headers = {"Authorization": "Bearer %s" % access_token}
    itemsPerPage = 10
    startIndex = 1
    totalGroups = 0
    timeout = 60

    params = []
    params.append("startIndex={}".format(startIndex))
    params.append("itemsPerPage={}".format(itemsPerPage))
    str_params = "?{}".format("&".join(params))
    url = f"{app.settings.iam_url}/iam/group/search{str_params}"

    groups = list()

    try:
        while True:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            totalResults = int(response.json()["totalResults"])
            resources = response.json()["Resources"]
            for r in resources:
                if r["meta"]["resourceType"] == "Group":
                    groupName = r["displayName"]
                    if groupName not in groups:
                        groups.append(groupName)
                totalGroups+=1
            if totalGroups < totalResults:
                startIndex += itemsPerPage
                params.clear()
                params.append("startIndex={}".format(startIndex))
                params.append("itemsPerPage={}".format(itemsPerPage))
                str_params = "?{}".format("&".join(params))
                url = f"{app.settings.iam_url}/iam/group/search{str_params}"
            else:
                break
    except Exception as e:
        raise Exception("Error retrieving iam groups list: {}".format(str(e)))
    return groups
