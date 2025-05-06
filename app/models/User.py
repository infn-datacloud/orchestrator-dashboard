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

from sqlalchemy.orm import relationship
from app.extensions import db


class User(db.Model):
    __tablename__ = "users"
    sub = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(128), nullable=True)
    username = db.Column(db.String(64), nullable=False)
    given_name = db.Column(db.String(64), nullable=True)
    family_name = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(64), nullable=False)
    organisation_name = db.Column(db.String(64), nullable=True)
    picture = db.Column(db.String(128), nullable=True)
    role = db.Column(db.String(32), nullable=False, default="user")
    sshkey = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=1)

    def __repr__(self):
        return "<User {}>".format(self.sub)
