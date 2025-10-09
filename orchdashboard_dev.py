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

import os
import sys
from flask_migrate import upgrade
from app import create_app, redis_listener
import threading

app = create_app(aligndb=False)

def run_migration():
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        with app.app_context():
            try:
                app.logger.info("Starting database migration...")
                # apply schema upgrades
                upgrade(directory="migrations", revision="head")
                app.logger.info("Database migration successfully completed.")
                # align configuration with database
                with app.app_context():
                    app.settings.align_db(app)
            except Exception as e:
                app.logger.error(f"Error during database migration: {e}", exc_info=True)
                sys.exit(1)
    else:
        app.logger.info("Reloader process, database migration skipped.")


    if __name__ == "__main__":
        app.run(host='0.0.0.0', port=5001)

@app.before_request
def start_redis_listener():
    app.before_request_funcs[None].remove(start_redis_listener)
    thread = threading.Thread(target=redis_listener, args=(app.config.get("REDIS_URL"),), daemon=True)
    thread.start()
    app.logger.info(f"Redis listener thread started")

run_migration()


