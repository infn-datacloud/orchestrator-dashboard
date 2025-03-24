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

from app.models import UsersGroup
from sqlalchemy.orm import backref, relationship
from app.models import UsersGroup, Service
from app.extensions import db

class ServiceAccess(db.Model):
    __tablename__ = "service_access"
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("service.id", ondelete="cascade"))
    group_id = db.Column(
        db.String(128), db.ForeignKey("users_group.name", ondelete="cascade")
    )
