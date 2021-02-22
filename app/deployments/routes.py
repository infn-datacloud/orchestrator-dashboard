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

import copy

from flask import Blueprint, session, render_template, flash, redirect, url_for, json, request
from app import app, iam_blueprint, tosca, vaultservice
from app.lib import auth, utils, settings, dbhelpers, yourls
from app.lib.ldap_user import LdapUserManager
from app.models.Deployment import Deployment
from app.providers import sla
from app.lib import ToscaInfo as tosca_helpers
from app.lib import openstack as keystone
from app.lib import s3 as s3
from werkzeug.utils import secure_filename
from app.swift.swift import Swift
from packaging import version
from urllib.parse import urlparse
import uuid as uuid_generator
import requests
import yaml
import io
import os
import re


deployments_bp = Blueprint('deployments_bp', __name__,
                           template_folder='templates',
                           static_folder='static')

iam_base_url = settings.iamUrl
iam_client_id = settings.iamClientID
iam_client_secret = settings.iamClientSecret

issuer = settings.iamUrl
if not issuer.endswith('/'):
    issuer += '/'


@deployments_bp.route('/all')
@auth.authorized_with_valid_token
def showdeployments():
    access_token = iam_blueprint.session.token['access_token']

    headers = {'Authorization': 'bearer %s' % access_token}
    params = "createdBy=me&page={}&size={}".format(0, 999999)

    if 'active_usergroup' in session and session['active_usergroup'] is not None:
        params = params + "&userGroup={}".format(session['active_usergroup'])

    url = settings.orchestratorUrl + "/deployments?{}".format(params)
    response = requests.get(url, headers=headers)

    deployments = {}
    if not response.ok:
        flash("Error retrieving deployment list: \n" + response.text, 'warning')
    else:
        deployments = response.json()["content"]
        result = dbhelpers.updatedeploymentsstatus(deployments, session['userid'])
        deployments = result['deployments']
        app.logger.debug("Deployments: " + str(deployments))

        deployments_uuid_array = result['iids']
        session['deployments_uuid_array'] = deployments_uuid_array

    return render_template('deployments.html', deployments=deployments)


@deployments_bp.route('/<depid>/template')
@auth.authorized_with_valid_token
def deptemplate(depid=None):
    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % access_token}

    url = settings.orchestratorUrl + "/deployments/" + depid + "/template"
    response = requests.get(url, headers=headers)

    if not response.ok:
        flash("Error getting template: " + response.text, 'danger')
        return redirect(url_for('home_bp.home'))

    template = response.text
    return render_template('deptemplate.html', template=template)


@deployments_bp.route('/<depid>/lock')
@auth.authorized_with_valid_token
def lockdeployment(depid=None):
    dep = dbhelpers.get_deployment(depid)
    if dep is not None:
        dep.locked = 1
        dbhelpers.add_object(dep)
    return redirect(url_for('deployments_bp.showdeployments'))


@deployments_bp.route('/<depid>/unlock')
@auth.authorized_with_valid_token
def unlockdeployment(depid=None):
    dep = dbhelpers.get_deployment(depid)
    if dep is not None:
        dep.locked = 0
        dbhelpers.add_object(dep)
    return redirect(url_for('deployments_bp.showdeployments'))


def preprocess_outputs(browser, outputs, stoutputs):
    for key, value in stoutputs.items():
        if value.get("type") == "download-url":
            if key in outputs:
                if value.get("action") == "shorturl":
                    origin_url = urlparse(outputs[key])
                    try:
                        shorturl = yourls.url_shorten(outputs[key])
                        if shorturl:
                            outputs[key] = shorturl
                    except Exception as e:
                        app.logger.debug('Error creating short url: {}'.format(str(e)))
                        pass

                if origin_url.scheme == 'http' and browser['name'] == "chrome" and browser['version'] >= 86:
                    message = stoutputs[key]['warning'] if 'warning' in stoutputs[key] else ""
                    stoutputs[key]['warning'] = "{}<br>{}".format("The download will be blocked by Chrome. Please, use Firefox for a full user experience.", message)

@deployments_bp.route('/<depid>/details')
@auth.authorized_with_valid_token
def depoutput(depid=None):
    if not session['userrole'].lower() == 'admin' and depid not in session['deployments_uuid_array']:
        flash("You are not allowed to browse this page!", 'danger')
        return redirect(url_for('deployments_bp.showdeployments'))

    # retrieve deployment from DB
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        return redirect(url_for('home_bp.home'))
    else:
        i = json.loads(dep.inputs.strip('\"')) if dep.inputs else {}
        stinputs = json.loads(dep.stinputs.strip('\"')) if dep.stinputs else {}
        outputs = json.loads(dep.outputs.strip('\"')) if dep.outputs else {}
        stoutputs = json.loads(dep.stoutputs.strip('\"')) if dep.stoutputs else {}
        inputs = {}
        for k, v in i.items():
            if ((stinputs[k]['printable'] if 'printable' in stinputs[k] else True) if k in stinputs else True):
                inputs[k] = v


        additional_outputs = getadditionaloutputs(dep, iam_blueprint.session.token['access_token'])

        outputs = {**outputs, **additional_outputs}

        browser = request.user_agent.browser
        version = request.user_agent.version and int(request.user_agent.version.split('.')[0])

        preprocess_outputs(dict(name = browser, version = version), outputs, stoutputs)

        return render_template('depoutput.html',
                               deployment=dep,
                               inputs=inputs,
                               outputs=outputs,
                               stoutputs=stoutputs)

def getadditionaloutputs(dep, access_token):
    uuid = dep.uuid
    status = dep.status
    template_type = dep.template_type
    additional_outputs = json.loads(dep.additional_outputs.strip('\"')) if dep.additional_outputs else {}

    update = False
    if status == "CREATE_COMPLETE" and additional_outputs == {} and template_type == 'kubernetes':
        # try to get kubeconfig file from log
        try:
            kubeconfig = extract_info_from_deplog(access_token, uuid, 'kubeconfig')
            additional_outputs = { "kubeconfig": kubeconfig }
            update = True
        except:
            app.logger.debug("Error while extracting kubeconfig file from log for deployment {}".format(dep.uuid))

    if update:
        dep.additional_outputs = json.dumps(additional_outputs)
        dbhelpers.add_object(dep)

    return additional_outputs



def extract_info_from_deplog(access_token, uuid, info_type):
    headers = {'Authorization': 'bearer %s' % access_token}

    url = settings.orchestratorUrl + "/deployments/" + uuid + "/log"
    response = requests.get(url, headers=headers)

    info = ""

    if response.ok:
        log = response.text
        lines = log.split('\n\n')

        if info_type == "kubeconfig":

            match = None
            for line in lines:
                match = re.search('^.*KUBECONFIG file.*\n.*\n.*\n.*\n.*\n.*\"(apiVersion.*)\"\n.*\n.*$', line)
                if match is not None:
                    info = match.group(1)

    return info

@deployments_bp.route('/<depid>/templatedb')
def deptemplatedb(depid):
    if not iam_blueprint.session.authorized:
        return redirect(url_for('home_bp.login'))

    # retrieve deployment from DB
    dep = dbhelpers.get_deployment(depid)
    if dep is None:
        return redirect(url_for('home_bp.home'))
    else:
        template = dep.template
        return render_template('deptemplate.html', template=template)


@deployments_bp.route('/<depid>/log')
@auth.authorized_with_valid_token
def deplog(depid=None):
    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % access_token}

    # app.logger.debug("Configuration: " + json.dumps(settings.orchestratorConf))
    dep = dbhelpers.get_deployment(depid)

    log = "Not available"

    if dep is not None:
        url = settings.orchestratorUrl + "/deployments/" + depid + "/log"
        response = requests.get(url, headers=headers)
        log = "Not available" if not response.ok else response.text

    return render_template('deplog.html', log=log)


@deployments_bp.route('/<depid>/infradetails')
@auth.authorized_with_valid_token
def depinfradetails(depid=None, path=None):
    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % access_token}

    # app.logger.debug("Configuration: " + json.dumps(settings.orchestratorConf))
    dep = dbhelpers.get_deployment(depid)
    if dep is not None and dep.physicalId is not None:
        url = settings.orchestratorUrl + "/deployments/" + depid + "/extrainfo"

        response = requests.get(url, headers=headers)
        vminfos = json.loads(response.text)
        app.logger.debug("VMs details: {}".format(response.text))
        details = []
        for vm_details in vminfos:
             vminfo = utils.format_json_radl(vm_details["vmProperties"])
             details.append(vminfo)

        return render_template('depinfradetails.html', vmsdetails=details)
    return redirect(url_for('deployments_bp.showdeployments'))

@deployments_bp.route('/<depid>/qcgdetails')
@auth.authorized_with_valid_token
def depqcgdetails(depid=None, path=None):
    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % access_token}

    # app.logger.debug("Configuration: " + json.dumps(settings.orchestratorConf))
    dep = dbhelpers.get_deployment(depid)
    if dep is not None and dep.physicalId is not None and dep.deployment_type == "QCG":
        url = settings.orchestratorUrl + "/deployments/" + depid + "/extrainfo"

        response = requests.get(url, headers=headers)
        app.logger.debug("Job details: {}".format(response.text))
        try:
            job = json.loads(response.text)
        except:
            app.logger.warning("Error decoding Job details response: {}".format(response.text))
            job = None

        return render_template('depqcgdetails.html', job=(job[0] if job else None))
    return redirect(url_for('deployments_bp.showdeployments'))


@deployments_bp.route('/<depid>/delete')
@auth.authorized_with_valid_token
def depdel(depid=None):
    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % access_token}
    url = settings.orchestratorUrl + "/deployments/" + depid
    response = requests.delete(url, headers=headers)

    if not response.ok:
        flash("Error deleting deployment: " + response.text, 'danger')
    else:
        dep = dbhelpers.get_deployment(depid)
        if dep is not None and dep.storage_encryption == 1:
            secret_path = session['userid'] + "/" + dep.vault_secret_uuid
            delete_secret_from_vault(access_token, secret_path)

    return redirect(url_for('deployments_bp.showdeployments'))


@deployments_bp.route('/depupdate/<depid>')
@auth.authorized_with_valid_token
def depupdate(depid=None):
    if depid is not None:
        dep = dbhelpers.get_deployment(depid)
        if dep is not None:
            access_token = iam_blueprint.session.token['access_token']
            template = dep.template
            tosca_info = tosca.extracttoscainfo(yaml.full_load(io.StringIO(template)), None)
            inputs = json.loads(dep.inputs.strip('\"')) if dep.inputs else {}
            stinputs = json.loads(dep.stinputs.strip('\"')) if dep.stinputs else {}
            tosca_info['inputs'] = {**tosca_info['inputs'], **stinputs}

            for (k, v) in tosca_info['inputs'].items():
                if k in inputs:
                    if 'default' in tosca_info['inputs'][k]:
                        tosca_info['inputs'][k]['default'] = inputs[k]

            stoutputs = json.loads(dep.stoutputs.strip('\"')) if dep.stoutputs else {}
            tosca_info['outputs'] = {**tosca_info['outputs'], **stoutputs}

            sla_id = tosca_helpers.getslapolicy(tosca_info)
            slas = sla.get_slas(access_token, settings.orchestratorConf['slam_url'],
                                settings.orchestratorConf['cmdb_url'], dep.deployment_type)
            ssh_pub_key = dbhelpers.get_ssh_pub_key(session['userid'])


            return render_template('updatedep.html',
                                   template=tosca_info,
                                   template_description=tosca_info['description'],
                                   instance_description=dep.description,
                                   feedback_required=dep.feedback_required,
                                   keep_last_attempt=dep.keep_last_attempt,
                                   provider_timeout=app.config['PROVIDER_TIMEOUT'],
                                   selectedTemplate=dep.selected_template,
                                   ssh_pub_key=ssh_pub_key,
                                   slas=slas,
                                   sla_id=sla_id,
                                   depid=depid,
                                   update=True)

    return redirect(url_for('deployments_bp.showdeployments'))


@deployments_bp.route('/updatedep', methods=['POST'])
@auth.authorized_with_valid_token
def updatedep():

    access_token = iam_blueprint.session.token['access_token']

    form_data = request.form.to_dict()

    app.logger.debug("Form data: " + json.dumps(form_data))

    depid = form_data['_depid']
    if depid is not None:
        dep = dbhelpers.get_deployment(depid)

        template = yaml.full_load(io.StringIO(dep.template))
        params = {}

        keep_last_attempt = 1 if 'extra_opts.keepLastAttempt' in form_data \
            else dep.keep_last_attempt
        feedback_required = 1 if 'extra_opts.sendEmailFeedback' in form_data else dep.feedback_required
        params['keepLastAttempt'] = 'true' if keep_last_attempt == 1 else 'false'
        params['providerTimeoutMins'] = form_data[
            'extra_opts.providerTimeout'] if 'extra_opts.providerTimeoutSet' in form_data else app.config[
            'PROVIDER_TIMEOUT']
        params['timeoutMins'] = app.config['OVERALL_TIMEOUT']
        params['callback'] = app.config['CALLBACK_URL']

        if form_data['extra_opts.schedtype'].lower() == "man":
            template = add_sla_to_template(template, form_data['extra_opts.selectedSLA'])
        else:
            remove_sla_from_template(template)

        inputs = {k: v for (k, v) in form_data.items() if not k.startswith("extra_opts.") and not k == '_depid'}
        #oldinputs = json.loads(dep.inputs.strip('\"')) if dep.inputs else {}
        #inputs = {**oldinputs, **inputs}

        additionaldescription = form_data['additional_description']

        if additionaldescription is not None:
            inputs['additional_description'] = additionaldescription

        app.logger.debug("Parameters: " + json.dumps(inputs))

        template_text = yaml.dump(template, default_flow_style=False, sort_keys=False)
        payload = {"template": template_text, "parameters": inputs}
        payload.update(params)

        app.logger.debug("[Deployment Update] inputs: {}".format(json.dumps(inputs)))
        app.logger.debug("[Deployment Update] Template: {}".format(template_text))

        url = settings.orchestratorUrl + "/deployments/" + depid
        headers = {'Content-Type': 'application/json', 'Authorization': 'bearer %s' % access_token}
        response = requests.put(url, json=payload, headers=headers)

        if not response.ok:
            flash("Error updating deployment: \n" + response.text, 'danger')
        else:
            # store data into database
            dep.keep_last_attempt = keep_last_attempt
            dep.feedback_required = feedback_required
            dep.description = additionaldescription
            dep.template = template_text
            #dep.inputs = json.dumps(inputs),
            oldinputs = json.loads(dep.inputs.strip('\"')) if dep.inputs else {}
            updatedinputs = {**oldinputs, **inputs}
            dep.inputs = json.dumps(updatedinputs),
            dbhelpers.add_object(dep)

    return redirect(url_for('deployments_bp.showdeployments'))


@deployments_bp.route('/configure', methods=['GET', 'POST'])
@auth.authorized_with_valid_token
def configure():
    access_token = iam_blueprint.session.token['access_token']

    selected_tosca = None

    if request.method == 'POST':
        selected_tosca = request.form.get('selected_tosca')

    if 'selected_tosca' in request.args:
        selected_tosca = request.args['selected_tosca']

    if 'active_user_group' in request.args:
        session['active_usergroup'] = request.args['active_user_group']

    if 'selected_group' in request.args:
        templates = tosca.tosca_gmetadata[request.args['selected_group']]['templates']
        if len(templates) == 1:
            selected_tosca = templates[0]['name']
        else:
            return render_template('choosedep.html', templates=templates)

    if selected_tosca:

        template = tosca.tosca_info[selected_tosca]
        sla_id = tosca_helpers.getslapolicy(template)

        slas = sla.get_slas(access_token, settings.orchestratorConf['slam_url'], settings.orchestratorConf['cmdb_url'],
                            template["deployment_type"])

        ssh_pub_key = dbhelpers.get_ssh_pub_key(session['userid'])

        return render_template('createdep.html',
                               template=template,
                               feedback_required=True,
                               keep_last_attempt=False,
                               provider_timeout=app.config['PROVIDER_TIMEOUT'],
                               selectedTemplate=selected_tosca,
                               ssh_pub_key=ssh_pub_key,
                               slas=slas,
                               sla_id=sla_id,
                               update=False)


def remove_sla_from_template(template):
    if 'policies' in template['topology_template']:
        for policy in template['topology_template']['policies']:
            for (k, v) in policy.items():
                if "type" in v \
                        and (
                        v['type'] == "tosca.policies.indigo.SlaPlacement" or v['type'] == "tosca.policies.Placement"):
                    template['topology_template']['policies'].remove(policy)
                    break
        if len(template['topology_template']['policies']) == 0:
            del template['topology_template']['policies']


def add_sla_to_template(template, sla_id):
    # Add or replace the placement policy

    if version.parse(utils.getorchestratorversion(settings.orchestratorUrl)) >= version.parse("2.2.0-SNAPSHOT"):
        tosca_sla_placement_type = "tosca.policies.indigo.SlaPlacement"
    else:
        tosca_sla_placement_type = "tosca.policies.Placement"
    template['topology_template']['policies'] = \
        [{"deploy_on_specific_site": {"type": tosca_sla_placement_type, "properties": {"sla_id": sla_id}}}]

    app.logger.debug(yaml.dump(template, default_flow_style=False))

    return template


@deployments_bp.route('/submit', methods=['POST'])
@auth.authorized_with_valid_token
def createdep():
    access_token = iam_blueprint.session.token['access_token']
    selected_template = request.args.get('template')
    source_template = tosca.tosca_info[selected_template]

    app.logger.debug("Form data: " + json.dumps(request.form.to_dict()))


    with io.open(os.path.join(settings.toscaDir, selected_template)) as stream:
        template = yaml.full_load(stream)
        # rewind file
        stream.seek(0)
        template_text = stream.read()

    form_data = request.form.to_dict()

    params = {}

    keep_last_attempt = 1 if 'extra_opts.keepLastAttempt' in form_data else 0
    params['keepLastAttempt'] = 'true' if 'extra_opts.keepLastAttempt' in form_data else 'false'
    feedback_required = 1 if 'extra_opts.sendEmailFeedback' in form_data else 0
    params['providerTimeoutMins'] = form_data[
        'extra_opts.providerTimeout'] if 'extra_opts.providerTimeoutSet' in form_data else app.config[
        'PROVIDER_TIMEOUT']
    params['timeoutMins'] = app.config['OVERALL_TIMEOUT']
    params['callback'] = app.config['CALLBACK_URL']
    if 'active_usergroup' in session and session['active_usergroup'] is not None:
        params['userGroup'] = session['active_usergroup']

    if form_data['extra_opts.schedtype'].lower() == "man":
        template = add_sla_to_template(template, form_data['extra_opts.selectedSLA'])
    else:
        remove_sla_from_template(template)

    additionaldescription = form_data['additional_description']

    inputs = {k: v for (k, v) in form_data.items() if not k.startswith("extra_opts.")}

    stinputs = copy.deepcopy(source_template['inputs'])

    doprocess = True
    swift = None
    swift_filename = []
    swift_map = {}

    uuidgen_deployment = str(uuid_generator.uuid1());

    for key,value in stinputs.items():
        # Manage security groups
        if value["type"]=="map" and value["entry_schema"]["type"]=="tosca.datatypes.network.PortSpec":
            if key in inputs:
                try:
                    inputs[key] = json.loads(form_data[key])
                    for k,v in inputs[key].items():
                        if ',' in v['source']:
                          v['source_range'] = json.loads(v.pop('source', None))
                except:
                    del inputs[key]
                    inputs[key] = { "ssh": { "protocol": "tcp", "source": 22 } }

                if "required_ports" in value:
                    inputs[key] = {**value["required_ports"], **inputs[key]}
            else:
                inputs[key] = { "ssh": { "protocol": "tcp", "source": 22 } }
        # Manage map of string
        if value["type"]=="map" and value["entry_schema"]["type"]=="string":
            if key in inputs:
                try:
                    inputs[key] = {}
                    map = json.loads(form_data[key])
                    for k,v in map.items():
                        inputs[key][v['key']] = v['value']
                except:
                    del inputs[key]
        # Manage list
        if value["type"]=="list":
            if key in inputs:
                try:
                    json_data = json.loads(form_data[key])
                    if value["entry_schema"]["type"]=="map" and value["entry_schema"]["entry_schema"]["type"]=="string":
                        array = []
                        for el in json_data:
                            array.append({el['key']: el['value']})
                        inputs[key] = array
                    else:
                        inputs[key] = json_data
                except:
                    del inputs[key]

        # Manage special type 'dependent_definition'
        if value["type"] == "dependent_definition":
            # retrieve the real type from dedicated field
            value["type"] = inputs[key + "-type"]
            del inputs[key + "-type"]

        # Manage Swift-related fields
        if value["type"] == "swift_autouuid":
            if key in inputs:
                swift_uuid = inputs[key] = str(uuid_generator.uuid1())

        if value["type"] == "hidden":
                try:
                    if re.match(r"^swift_[avuktc]$", value["default"]):
                        if key in inputs:
                            swift_map[value["default"]] = key
                except:
                    pass


        if value["type"] == "swift_token":
            if key in inputs:
                swift = Swift(token=inputs[key])
                del inputs[key]

        if value["type"] == "swift_upload":
            if key in request.files:
                swift_filename.append(key)

        if value["type"] == "random_password":
            inputs[key] = utils.generate_password()

        if value["type"] == "uuidgen":
            prefix = ''
            suffix = ''
            if "extra_specs" in value:
              prefix = value["extra_specs"]["prefix"] if "prefix" in value["extra_specs"] else ""
              suffix = value["extra_specs"]["suffix"] if "suffix" in value["extra_specs"] else ""
            inputs[key] = prefix + uuidgen_deployment + suffix

        if value["type"] == "openstack_ec2credentials":
            try:
                del inputs[key]
                access, secret = keystone.get_or_create_ec2_creds(access_token, value["auth"]["url"], value["auth"]["identity_provider"], value["auth"]["protocol"])
                access_key_input_name = value["inputs"]["aws_access_key"]
                inputs[access_key_input_name] = access
                secret_key_input_name = value["inputs"]["aws_secret_key"]
                inputs[secret_key_input_name] = secret

                functions = {'s3.create_bucket': s3.create_bucket, "s3.delete_bucket": s3.delete_bucket}

                if "tests" in value and value["tests"]:
                    for test in value["tests"]:
                       func = test["action"]
                       args = test["args"]
                       args["access_key"] = access
                       args["secret_key"] = secret
                       if func in functions:
                           functions[func](**args)
            except Exception as e:
                flash(" The deployment submission failed with: {} <br><strong>Please contact the admin(s):</strong> {}".format(e, app.config.get('SUPPORT_EMAIL')), 'danger')
                doprocess = False

        if value["type"] == "ldap_user":
            try:
                del inputs[key]

                iam_base_url = settings.iamUrl
                iam_client_id = settings.iamClientID
                iam_client_secret = settings.iamClientSecret

                username = '{}_{}'.format(session['userid'], urlparse(iam_base_url).netloc)
                email = session['useremail']

                jwt_token = auth.exchange_token_with_audience(iam_base_url,
                                                      iam_client_id,
                                                      iam_client_secret,
                                                      access_token,
                                                      app.config.get('VAULT_BOUND_AUDIENCE'))

                vaultclient = vaultservice.connect(jwt_token, app.config.get("VAULT_ROLE"))
                luser = LdapUserManager(app.config.get('LDAP_SOCKET'),
                                        app.config.get('LDAP_BASE'),
                                        app.config.get('LDAP_BIND_USER'),
                                        app.config.get('LDAP_BIND_PASSWORD'),
                                        vaultclient)

                username, password = luser.create_user(username, email)
                username_input_name = value["inputs"]["username"]
                inputs[username_input_name] = username
                password_input_name = value["inputs"]["password"]
                inputs[password_input_name] = password

            except Exception as e:
                flash(" The deployment submission failed with: {} <br><strong>Please contact the admin(s):</strong> {}".format(e, app.config.get('SUPPORT_EMAIL')), 'danger')
                doprocess = False



    if swift and swift_map:
        for k, v in swift_map.items():
            val = swift.mapvalue(k)
            if val is not None:
                inputs[v] = val



    swiftprocess = False
    containername = filename = None

    if swift_filename:

      for f in swift_filename:

        file = request.files[f]
        if file:
            upload_folder = app.config['UPLOAD_FOLDER']
            upload_folder = os.path.join(upload_folder, swift_uuid)
            filename = secure_filename(file.filename)
            fullfilename = os.path.join(upload_folder, filename)
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            file.save(fullfilename)

            if f not in inputs:
                inputs[f] = file.filename

            containername = basecontainername = swift.basecontainername
            containers = swift.getownedcontainers()
            basecontainer = next(filter(lambda x: x['name'] == basecontainername, containers), None)
            if basecontainer is None:
                swift.createcontainer(basecontainername)


            containername = basecontainername + "/" + swift_uuid

            with open(fullfilename, 'rb') as f:
                calchash = swift.md5hash(f)
            with open(fullfilename, 'rb') as f:
                objecthash = swift.createobject(containername, filename, contents=f.read())

            if hash is not None and objecthash != swift.emptyMd5:
                swiftprocess = True

            os.remove(fullfilename)
            os.rmdir(upload_folder)

            if calchash != objecthash:
                doprocess = False
                flash("Wrong swift file checksum!", 'danger')
        else:
            doprocess = False
            flash("Missing file object!", 'danger')



    if doprocess:

        storage_encryption, vault_secret_uuid, vault_secret_key = add_storage_encryption(access_token, inputs)

        if 'instance_key_pub' in inputs and inputs['instance_key_pub'] == '':
            inputs['instance_key_pub'] = dbhelpers.get_ssh_pub_key(session['userid'])

        app.logger.debug("Parameters: " + json.dumps(inputs))

        payload = {"template": yaml.dump(template, default_flow_style=False, sort_keys=False),
                   "parameters": inputs}
        # set additional params
        payload.update(params)

        elastic = tosca_helpers.eleasticdeployment(template)
        updatable = source_template['updatable']

        url = settings.orchestratorUrl + "/deployments/"
        headers = {'Content-Type': 'application/json', 'Authorization': 'bearer %s' % access_token}
        response = requests.post(url, json=payload, headers=headers)

        if not response.ok:
            flash("Error submitting deployment: \n" + response.text, 'danger')
            doprocess = False
        else:
            # store data into database
            rs_json = json.loads(response.text)
            uuid = rs_json['uuid']
            deployment = dbhelpers.get_deployment(uuid)
            if deployment is None:

                vphid = rs_json['physicalId'] if 'physicalId' in rs_json else ''
                providername = rs_json['cloudProviderName'] if 'cloudProviderName' in rs_json else ''

                deployment = Deployment(uuid=uuid,
                                        creation_time=rs_json['creationTime'],
                                        update_time=rs_json['updateTime'],
                                        physicalId=vphid,
                                        description=additionaldescription,
                                        status=rs_json['status'],
                                        outputs=json.dumps(rs_json['outputs']),
                                        stoutputs=json.dumps(source_template['outputs']),
                                        task=rs_json['task'],
                                        links=json.dumps(rs_json['links']),
                                        sub=rs_json['createdBy']['subject'],
                                        template=template_text,
                                        template_metadata=source_template['metadata_file'],
                                        template_parameters=source_template['parameters_file'],
                                        selected_template=selected_template,
                                        inputs=json.dumps(inputs),
                                        stinputs=json.dumps(stinputs),
                                        params=json.dumps(params),
                                        deployment_type=source_template['deployment_type'],
                                        template_type=source_template['metadata']['template_type'],
                                        provider_name=providername,
                                        user_group=rs_json['userGroup'],
                                        endpoint='',
                                        feedback_required=feedback_required,
                                        keep_last_attempt=keep_last_attempt,
                                        remote=1,
                                        issuer=rs_json['createdBy']['issuer'],
                                        storage_encryption=storage_encryption,
                                        vault_secret_uuid=vault_secret_uuid,
                                        vault_secret_key=vault_secret_key,
                                        elastic=elastic,
                                        updatable=updatable)
                dbhelpers.add_object(deployment)

            else:
                flash("Deployment with uuid:{} is already in the database!".format(uuid), 'warning')

    if doprocess is False and swiftprocess is True:
        swift.removeobject(containername, filename)

    return redirect(url_for('deployments_bp.showdeployments'))


def delete_secret_from_vault(access_token, secret_path):
    vault_url = app.config.get('VAULT_URL')

    vault_secrets_path = app.config.get('VAULT_SECRETS_PATH')
    vault_bound_audience = app.config.get('VAULT_BOUND_AUDIENCE')
    vault_delete_policy = app.config.get("DELETE_POLICY")
    vault_delete_token_time_duration = app.config.get("DELETE_TOKEN_TIME_DURATION")
    vault_delete_token_renewal_time_duration = app.config.get("DELETE_TOKEN_RENEWAL_TIME_DURATION")
    vault_role = app.config.get("VAULT_ROLE")

    jwt_token = auth.exchange_token_with_audience(iam_base_url,
                                                  iam_client_id,
                                                  iam_client_secret,
                                                  access_token,
                                                  vault_bound_audience)

    vault_client = vaultservice.connect(jwt_token, vault_role)

    delete_token = vault_client.get_token(vault_delete_policy,
                                          vault_delete_token_time_duration,
                                          vault_delete_token_renewal_time_duration)

    vault_client.delete_secret(delete_token, secret_path)


def add_storage_encryption(access_token, inputs):
    vault_url = app.config.get('VAULT_URL')
    vault_role = app.config.get("VAULT_ROLE")
    vault_bound_audience = app.config.get('VAULT_BOUND_AUDIENCE')
    vault_wrapping_token_time_duration = app.config.get("WRAPPING_TOKEN_TIME_DURATION")
    vault_write_policy = app.config.get("WRITE_POLICY")
    vault_write_token_time_duration = app.config.get("WRITE_TOKEN_TIME_DURATION")
    vault_write_token_renewal_time_duration = app.config.get("WRITE_TOKEN_RENEWAL_TIME_DURATION")

    storage_encryption = 0
    vault_secret_uuid = ''
    vault_secret_key = ''
    if 'storage_encryption' in inputs and inputs['storage_encryption'].lower() == 'true':
        storage_encryption = 1
        vault_secret_key = 'secret'

    if storage_encryption == 1:
        inputs['vault_url'] = vault_url
        vault_secret_uuid = str(uuid_generator.uuid4())
        if 'vault_secret_key' in inputs:
            vault_secret_key = inputs['vault_secret_key']
        app.logger.debug("Storage encryption enabled, appending wrapping token.")

        jwt_token = auth.exchange_token_with_audience(iam_base_url,
                                                      iam_client_id,
                                                      iam_client_secret,
                                                      access_token,
                                                      vault_bound_audience)

        vault_client = vaultservice.connect(jwt_token, vault_role)

        wrapping_token = vault_client.get_wrapping_token(vault_wrapping_token_time_duration,
                                                         vault_write_policy,
                                                         vault_write_token_time_duration,
                                                         vault_write_token_renewal_time_duration)

        inputs['vault_wrapping_token'] = wrapping_token
        inputs['vault_secret_path'] = session['userid'] + '/' + vault_secret_uuid

    return storage_encryption, vault_secret_uuid, vault_secret_key