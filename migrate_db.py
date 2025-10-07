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

import logging
import sys
from flask_migrate import upgrade
from app import create_app


app_upgrade = create_app(aligndb=False)

# Fallback log su stderr
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
app_upgrade.logger.addHandler(console_handler)


def run_migration():
    with app_upgrade.app_context():
        try:
            app_upgrade.logger.info("Starting database migration...")
            # apply schema upgrades
            upgrade(directory="migrations", revision="head")
            app_upgrade.logger.info("Database migration successfully completed.")
        except Exception as e:
            app_upgrade.logger.error(f"Error during database migration: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    run_migration()

