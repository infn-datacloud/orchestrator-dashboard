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


import io
import json
import os
import re
import uuid
from fnmatch import fnmatch
import jsonschema
import Levenshtein
import sys
import yaml
from app.lib.path_utils import url_path_join, path_ensure_slash
from app.lib.strings import notnullorempty

class ToscaInfo:
    """Class to load tosca templates and metadata at application start"""

    def __init__(self):
        self.redis_client = None
        self.tosca_dir = None
        self.tosca_params_dir = None
        self.tosca_metadata_dir = None
        self.metadata_schema = None
        self.app = None

    def init_app(self, app, redis_client):
        """
        Initialize the flask extension
        :param tosca_dir: the dir of the tosca templates
        :param settings_dir: the dir of the params and metadata files
        """
        self.redis_client = redis_client
        self.tosca_dir = app.settings.tosca_dir
        self.tosca_params_dir = app.settings.tosca_params_dir
        self.tosca_metadata_dir = app.settings.tosca_metadata_dir
        self.metadata_schema = app.settings.metadata_schema
        self.app = app
        self.reload("init")


    def reload(self, mode):
        tosca_templates = self._loadtoscatemplates()
        tosca_info, tosca_filenames = self._extractalltoscainfo(tosca_templates)
        tosca_gmetadata, tosca_gversion = self._loadmetadata()

        self.redis_client.set("tosca_templates", json.dumps(tosca_templates))
        self.redis_client.set("tosca_info", json.dumps(tosca_info))
        self.redis_client.set("tosca_filenames", json.dumps(tosca_filenames))
        self.redis_client.set("tosca_gmetadata", json.dumps(tosca_gmetadata))
        self.redis_client.set("tosca_gversion", tosca_gversion)

        self.app.logger.info(f"Reloading tosca configuration on {mode}")

    def _loadmetadata(self):
        mpath = url_path_join(self.tosca_metadata_dir, "metadata.yml")
        if not os.path.isfile(mpath):
            mpath = url_path_join(self.tosca_metadata_dir, "metadata.yaml")
            if not os.path.isfile(mpath):
                return {}, "1.0.0"
        with io.open(mpath) as stream:
            metadata = yaml.full_load(stream)

            # validate against schema
            jsonschema.validate(
                metadata,
                self.metadata_schema,
                format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
            )
            tosca_gmetadata = {str(uuid.uuid4()): service for service in metadata["services"]}
            tosca_gversion = "1.0.0"  if "version" not in metadata else metadata["version"]
            return tosca_gmetadata, tosca_gversion

    def _loadtoscatemplates(self):
        toscatemplates = []
        for path, subdirs, files in os.walk(self.tosca_dir):
            for name in files:
                if fnmatch(name, "*.yml") or fnmatch(name, "*.yaml"):
                    # skip hidden files
                    if name[0] != ".":
                        toscatemplates.append(
                            os.path.relpath(os.path.join(path, name), self.tosca_dir)
                        )

        return sorted(toscatemplates)

    def _extractalltoscainfo(self, tosca_templates):
        tosca_info = dict()
        tosca_filenames = dict()
        for tosca in tosca_templates:
            with io.open(
                os.path.join(self.tosca_dir, tosca), encoding="utf-8"
            ) as stream:
                template = yaml.full_load(stream)
                info = self.extracttoscainfo(template, tosca)
                template_name = info["metadata"]["template_name"]
                tosca_info[template_name] = info
                tosca_filenames[template_name] = tosca
        return tosca_info, tosca_filenames

    def extracttoscainfo(self, template, tosca):
        tosca_info = {
            "valid": True,
            "description": "TOSCA Template",
            "metadata": {
                "icon": "https://cdn4.iconfinder.com/data/icons/mosaicon-04/512/websettings-512.png",
                "visibility": {"type": "public"},
                "require_ssh_key": True,
                "template_type": "",
            },
            "enable_config_form": False,
            "inputs": {},
            "outputs": {},
            "node_templates": {},
            "policies": {},
            "tabs": {},
            "metadata_file": "",
            "parameters_file": "",
        }

        if "topology_template" not in template:
            tosca_info["valid"] = False

        else:
            if "description" in template:
                tosca_info["description"] = template["description"]

            if "metadata" in template and template["metadata"] is not None:
                for k, v in template["metadata"].items():
                    tosca_info["metadata"][k] = v

            if tosca and self.tosca_metadata_dir:
                tosca_metadata_path = path_ensure_slash(self.tosca_metadata_dir)
                for mpath, msubs, mnames in os.walk(tosca_metadata_path):
                    for mname in mnames:
                        fmname = os.path.relpath(
                            url_path_join(mpath, mname), self.tosca_metadata_dir
                        )
                        if fnmatch(fmname, os.path.splitext(tosca)[0] + ".metadata.yml") or \
                            fnmatch(fmname, os.path.splitext(tosca)[0] + ".metadata.yaml"
                        ):
                            # skip hidden files
                            if mname[0] != ".":
                                tosca_metadata_file = os.path.join(mpath, mname)
                                with io.open(tosca_metadata_file) as metadata_file:
                                    tosca_info["metadata_file"] = metadata_file.read()
                                    metadata_template = yaml.full_load(
                                        io.StringIO(tosca_info["metadata_file"])
                                    )

                                    if (
                                        "metadata" in metadata_template
                                        and metadata_template["metadata"] is not None
                                    ):
                                        for k, v in metadata_template["metadata"].items():
                                            tosca_info["metadata"][k] = v

            # override description from metadata, if available
            if "description" in tosca_info["metadata"]:
                tosca_info["description"] = tosca_info["metadata"]["description"]

            # initialize inputs/outputs
            tosca_inputs = {}
            tosca_outputs = {}
            # get inputs/outputs from template, if provided
            topology_template = template["topology_template"]
            if "inputs" in topology_template:
                tosca_inputs = tosca_info["inputs"] = topology_template["inputs"]

            if "outputs" in topology_template:
                tosca_outputs = tosca_info["outputs"] = topology_template["outputs"]

            if "node_templates" in topology_template:
                tosca_info["deployment_type"] = getdeploymenttype(topology_template["node_templates"])

            if "policies" in topology_template:
                tosca_info["policies"] = topology_template["policies"]

            # add parameters code here
            if tosca and self.tosca_params_dir:
                tosca_pars_path = path_ensure_slash(self.tosca_params_dir)
                for fpath, subs, fnames in os.walk(tosca_pars_path):
                    for fname in fnames:
                        ffname = os.path.relpath(os.path.join(fpath, fname), self.tosca_params_dir)
                        if fnmatch(
                            ffname, os.path.splitext(tosca)[0] + ".parameters.yml"
                        ) or fnmatch(ffname, os.path.splitext(tosca)[0] + ".parameters.yaml"):
                            # skip hidden files
                            if fname[0] != ".":
                                tosca_pars_file = os.path.join(fpath, fname)
                                with io.open(tosca_pars_file) as pars_file:
                                    tosca_info["enable_config_form"] = True
                                    parameters_data = pars_file.read()
                                if isinstance(parameters_data, str):
                                    if parameters_data.startswith(".."):
                                        with io.open(
                                                os.path.realpath(os.path.join(fpath, parameters_data))) as pars_file:
                                            parameters_data = pars_file.read()
                                if isinstance(parameters_data, str):
                                    tosca_info["parameters_file"] = parameters_data
                                    pars_data = yaml.full_load(
                                        io.StringIO(tosca_info["parameters_file"])
                                    )
                                    if "inputs" in pars_data:
                                        pars_inputs = pars_data["inputs"]
                                        tosca_info["inputs"] = {}

                                        # First, iterate over tosca_inputs to maintain order
                                        for key in tosca_inputs:
                                            tosca_info["inputs"][key] = {**tosca_inputs[key], **pars_inputs.get(key, {})}

                                        # Then, add any new keys from pars_inputs that were not in tosca_inputs
                                        for key in pars_inputs:
                                            if key not in tosca_inputs:
                                                tosca_info["inputs"][key] = pars_inputs[key]

                                    if "outputs" in pars_data:
                                        pars_outputs = pars_data["outputs"]
                                        tosca_info["outputs"] = {}

                                        # First, iterate over tosca_outputs to maintain order
                                        for key in tosca_outputs:
                                            tosca_info["outputs"][key] = {**tosca_outputs[key], **pars_outputs.get(key, {})}

                                        # Then, add any new keys from pars_outputs that were not in tosca_outputs
                                        for key in pars_outputs:
                                            if key not in tosca_outputs:
                                                tosca_info["outputs"][key] = pars_outputs[key]

                                    if "tabs" in pars_data:
                                        tosca_info["tabs"] = pars_data["tabs"]

            updatable = updatabledeployment(tosca_info["inputs"])
            tosca_info["updatable"] = updatable

            s3_node_found, s3_node = has_node_of_type(template, "tosca.nodes.indigo.S3Bucket")
            if s3_node_found:
                tosca_info["inputs"]["__" + s3_node.get("name")] = {
                    "type": "openstack_ec2credentials",
                    "url": s3_node.get("properties").get("s3_url"),
                }

        return tosca_info

    def get(self):
        serialised_value = self.redis_client.get("tosca_info")
        tosca_info = json.loads(serialised_value)
        serialised_value = self.redis_client.get("tosca_filenames")
        tosca_filenames = json.loads(serialised_value)
        serialised_value = self.redis_client.get("tosca_templates")
        tosca_templates = json.loads(serialised_value)
        serialised_value = self.redis_client.get("tosca_gmetadata")
        tosca_gmetadata = json.loads(serialised_value)
        tosca_gversion = self.redis_client.get("tosca_gversion")
        return tosca_info, tosca_filenames, tosca_templates, tosca_gmetadata, tosca_gversion

    def gettemplates(self) -> list[str]:
        serialised_value = self.redis_client.get("tosca_templates")
        tosca_templates = json.loads(serialised_value)
        return tosca_templates

    def getinfo(self) -> dict[str, any]:
        serialised_value = self.redis_client.get("tosca_info")
        tosca_info = json.loads(serialised_value)
        return tosca_info

    def getfilenames(self) -> dict[str, any]:
        serialised_value = self.redis_client.get("tosca_filenames")
        tosca_filenames = json.loads(serialised_value)
        return tosca_filenames

    def getversion(self):
        tosca_gversion = self.redis_client.get("tosca_gversion")
        return tosca_gversion

    def getmetadata(self):
        serialised_value = self.redis_client.get("tosca_gmetadata")
        tosca_gmetadata = json.loads(serialised_value)
        return tosca_gmetadata

    def _findpublicnetwork(self, obj):
        if isinstance(obj, dict):
            if "pub_network" in obj:
                return True
            for iv in obj.values():
                if self._findpublicnetwork(iv):
                    return True
        if isinstance(obj, list):
            for iv in obj:
                if self._findpublicnetwork(iv):
                    return True
        if isinstance(obj, str):
                if "public_address" in obj or "pub_network" in obj:
                    return True
        return False

    def find_template_name(self, selected_template, template, toscainfo=None, mindist=0.8):
        if toscainfo is None:
            tt = self.getinfo()
        else:
            tt = toscainfo
        try:
            # try use selected_template field
            if notnullorempty(selected_template):
                if selected_template in tt:
                    t = tt[selected_template]
                    try:
                        tname = t["metadata"]["template_name"]
                    except:
                        tname = None
                    if notnullorempty(tname):
                        return tname
            # try use display_name
            ld = dict()
            if notnullorempty(template):
                # Replace tab with 2 spaces (only on loaded template not on DB)
                clean_template = re.sub(r'\t', '  ', template)
                dt = yaml.full_load(io.StringIO(clean_template))
                try:
                    nt = dt["topology_template"]["node_templates"]
                    privnetwork = not self._findpublicnetwork(nt)
                except:
                    privnetwork = False
                if privnetwork:
                    try:
                        vo = dt["topology_template"]["outputs"]
                        for vk, vv in vo.items():
                            if self._findpublicnetwork(vv):
                                privnetwork = False
                                break
                    except:
                        privnetwork = False

                if "metadata" in dt:
                    try:
                        displayname = dt["metadata"]["display_name"]
                    except:
                        displayname = None
                    if notnullorempty(displayname):

                        for tn, tv in tt.items():
                            try:
                                tvname = tv["metadata"]["display_name"]
                            except:
                                tvname = None
                            if notnullorempty(tvname):
                                if (not privnetwork and ("private" not in tn.lower())) or (
                                        privnetwork and ("private" in tn.lower())):
                                    ld[tn] = Levenshtein.ratio(displayname, tvname)
                        ld = dict(sorted(ld.items(), key=lambda item: item[1], reverse=True))

                        if ld:
                            topk = list(ld.keys())[0]
                            topv = list(ld.values())[0]
                            if topv >= mindist:
                                t = tt[topk]
                                try:
                                    tname = t["metadata"]["template_name"]
                                except:
                                    tname = None
                                if notnullorempty(tname):
                                    return tname
                #try use description
                ld.clear()
                try:
                    description = dt["description"]
                except:
                    description = None
                if notnullorempty(description):
                    for tn, tv in tt.items():
                        try:
                            tvdescription = tv["description"]
                        except:
                            tvdescription = None
                        if notnullorempty(tvdescription):
                            if (not privnetwork and ("private" not in tn.lower())) or (
                                    privnetwork and ("private" in tn.lower())):
                                ld[tn] = Levenshtein.ratio(description, tvdescription)
                    ld = dict(sorted(ld.items(), key=lambda item: item[1], reverse=True))

                    if ld:
                        topk = list(ld.keys())[0]
                        topv = list(ld.values())[0]
                        if topv >= mindist:
                            t = tt[topk]
                            try:
                                tname = t["metadata"]["template_name"]
                            except:
                                tname = None
                            if notnullorempty(tname):
                                return tname
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(str(e), exc_type, fname, exc_tb.tb_lineno)

        return None




# Helper functions
def getdeploymenttype(nodes):
    deployment_type = ""
    for j, u in nodes.items():
        if deployment_type == "":
            for k, v in u.items():
                if k == "type":
                    if v == "tosca.nodes.indigo.Compute":
                        deployment_type = "CLOUD"
                        break
                    if v == "tosca.nodes.indigo.Container.Application.Docker.Marathon":
                        deployment_type = "MARATHON"
                        break
                    if v == "tosca.nodes.indigo.Container.Application.Docker.Chronos":
                        deployment_type = "CHRONOS"
                        break
                    if v == "tosca.nodes.indigo.Qcg.Job":
                        deployment_type = "QCG"
                        break
        else:
            break
    return deployment_type


def getslapolicy(template):
    sla_id = ""
    if "policies" in template:
        for policy in template["policies"]:
            if sla_id == "":
                for k, v in policy.items():
                    if "type" in v and (
                        v["type"] == "tosca.policies.indigo.SlaPlacement"
                        or v["type"] == "tosca.policies.Placement"
                    ):
                        if "properties" in v:
                            sla_id = (
                                v["properties"]["sla_id"] if "sla_id" in v["properties"] else ""
                            )
                        break
            else:
                break
    return sla_id


def eleasticdeployment(template):
    found, _ = has_node_of_type(template, "tosca.nodes.indigo.ElasticCluster")
    return found


def updatabledeployment(inputs):
    updatable = False
    for key, value in inputs.items():
        if "updatable" in value:
            if value["updatable"]:
                updatable = True
                break

    return updatable


def has_node_of_type(template, nodetype):
    found = False
    node = None
    if "topology_template" in template:
        if "node_templates" in template["topology_template"]:
            for j, u in template["topology_template"]["node_templates"].items():
                if found:
                    break
                for k, v in u.items():
                    if k == "type" and nodetype in v:
                        found = True
                        node = u
                        node["name"] = j  # add node name
                        break
    return found, node


def set_removal_list(template_dict, node_name, removal_list, count):
    # Check if the node_templates section exists
    if (
        "topology_template" not in template_dict
        or "node_templates" not in template_dict["topology_template"]
    ):
        raise KeyError("The 'node_templates' section is missing in the TOSCA template.")

    node_templates = template_dict["topology_template"]["node_templates"]

    # Check if the node exists
    if node_name not in node_templates:
        raise KeyError(f"Node '{node_name}' does not exist in the TOSCA template.")

    node = node_templates[node_name]

    # Check if the capabilities section exists
    if "capabilities" not in node:
        node["capabilities"] = {}
    capabilities = node["capabilities"]

    # Check if the scalable section exists
    if "scalable" not in capabilities:
        capabilities["scalable"] = {}
    scalable = capabilities["scalable"]

    # Check if the properties section exists
    if "properties" not in scalable:
        scalable["properties"] = {}
    properties = scalable["properties"]

    # Update the removal_list property
    properties["removal_list"] = removal_list

    count_property = properties["count"]
    inputs = {}
    if isinstance(count_property, dict):
        if "get_input" in count_property:
            input_name = count_property["get_input"]
            inputs = {input_name: count}
    else:
        # Update the count property
        properties["count"] = count

    return template_dict, inputs
