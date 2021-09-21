# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2020-2021
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
from flaat import tokentools, issuertools
from app import app, flaat

class IndigoTokenDecoder:
    def get_groups(self, info):
        return info['groups']

class EgiTokenDecoder:
    def get_groups(self, info):
        memberships = info['eduperson_entitlement']
        pattern = 'urn:mace:egi.eu:group:(.*):role=vm_operator#aai.egi.eu'

        groups=[]
        for m in memberships:
            match = re.search(pattern, m)
            if match:
                groups.append(match.group(1))

        return groups

class TokenDecoderFactory:

    def __init__(self):
        self._creators = {}

    def register_format(self, format, creator):
        self._creators[format] = creator

    def get_decoder(self, format):
        creator = self._creators.get(format)
        if not creator:
            raise ValueError(format)
        return creator()


factory = TokenDecoderFactory()
factory.register_format('indigoiam', IndigoTokenDecoder)
factory.register_format('egicheckin', EgiTokenDecoder)


class TokenDecoder:
    def get_groups(self, request):
        access_token = tokentools.get_access_token_from_request(request)
        issuer = issuertools.find_issuer_config_in_at(access_token)
        #info = flaat.get_info_thats_in_at(access_token)
        info = flaat.get_info_from_userinfo_endpoints(access_token)
        iss = issuer['issuer']

        idp = next(filter(lambda x: x['iss']==iss, app.config.get('TRUSTED_OIDC_IDP_LIST')))

        if 'client_id' in idp and 'client_secret' in idp:
            flaat.set_client_id(idp['client_id'])
            flaat.set_client_secret(idp['client_secret'])
            info = flaat.get_info_from_introspection_endpoints(access_token)
        decoder = factory.get_decoder(idp['type'])
        return decoder.get_groups(info)