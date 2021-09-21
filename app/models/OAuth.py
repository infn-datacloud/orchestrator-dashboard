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

from app import db
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import attribute_mapped_collection
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from app.models.User import User
from flaat import tokentools


class OAuth(OAuthConsumerMixin, db.Model):
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_user_id"),
    )
    provider_user_id = db.Column(db.String(256), nullable=False)
    user_id = db.Column(db.String(256), db.ForeignKey(User.sub), nullable=False)
    issuer = db.Column(db.String(50), nullable=False)
    user = db.relationship(
        User,
        # This `backref` thing sets up an `oauth` property on the User model,
        # which is a dictionary of OAuth models associated with that user,
        # where the dictionary key is the OAuth provider name.
        backref=db.backref(
            "oauth",
            collection_class=attribute_mapped_collection("provider"),
            cascade="all, delete-orphan",
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        token = kwargs['token']
        jwt = tokentools.get_accesstoken_info(token['id_token'])
        if not 'provider_user_id' in kwargs:
            self.provider_user_id = jwt['body']['sub']
        if not 'issuer' in kwargs:
            self.issuer = jwt['body']['iss']
