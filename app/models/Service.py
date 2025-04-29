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
import enum
from datetime import datetime
from app.models import UsersGroup, ServiceAccess
from sqlalchemy.orm import backref, relationship

from app.extensions import db


class Visibility(enum.Enum):
    private = 0
    public = 1


class Service(db.Model):
    __tablename__ = "service"
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(128), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    icon = db.Column(db.String(128), default="", nullable=False)
    description = db.Column(db.String(2048), nullable=True)
    visibility = db.Column(db.Enum(Visibility), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    groups = relationship(
        "UsersGroup", secondary="service_access", backref=backref("service")
    )

    def __repr__(self):
        return "<Service {}>: {}".format(self.name, self.url)

    def get_groups_list(self):
        return [g.name for g in self.groups]


