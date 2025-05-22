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

import re
import urllib.parse

def url_path_join(
    base_url,
    *paths
):
    """
       Parse and join url parts into a well-formed URL.

       Args:
           base_url (str): The base URL to join.
           *paths (str,): Parts of the path to join.

       Returns:
           str: A well-formed URL.
    """
    parsed_url = urllib.parse.urlsplit(base_url)
    base_path = re.sub('/+', '/', parsed_url.path)
    if paths:
        if len(base_path) and base_path[-1] != '/':
            base_path += '/'
        for path in paths[:-1]:
            path = re.sub('/+', '/', path).lstrip('/') + '/'
            base_path = urllib.parse.urljoin(base_path, path)
        path = paths[-1]
        path = re.sub('/+', '/', path).lstrip('/')
        base_path = urllib.parse.urljoin(base_path, path)
    return urllib.parse.urlunsplit(parsed_url._replace(path=base_path))

