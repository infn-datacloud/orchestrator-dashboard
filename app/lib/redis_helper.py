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

import redis
from app.lib.dbhelpers import notnullorempty
from urllib.parse import urlparse

def get_redis(redis_url):
    if notnullorempty(redis_url):
        parsed_url = urlparse(redis_url)
        return redis.Redis(
            host=parsed_url.hostname,
            port=parsed_url.port,
            password=parsed_url.password,
            db=int(parsed_url.path.strip('/')) if parsed_url.path else 0,
            decode_responses=True
        )
    else:
        return redis.Redis()
