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
"""
Main module for running the Flask application.

This module initializes the Flask application using the `create_app` function from the `app` module.
The application is then run with the specified host and port when the script is executed directly.
"""
from app import create_app, redis_listener
import threading

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

@app.before_request
def start_redis_listener():
    app.before_request_funcs[None].remove(start_redis_listener)
    thread = threading.Thread(target=redis_listener, args=(app.config.get("REDIS_URL"),), daemon=True)
    thread.start()
    app.logger.debug(f"Redis listener thread started")

