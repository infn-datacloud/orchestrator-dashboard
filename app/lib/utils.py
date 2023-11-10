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

import enum
import json
import linecache
import os
import shutil
import subprocess
import re
import sys
import string
import secrets
from threading import Thread
from hashlib import md5
import requests
import randomcolor
from flask_mail import Message
from flask import current_app as app, session, render_template
from markupsafe import Markup
from app.extensions import mail


def to_pretty_json(value):
    """
    Convert a Python data structure to a formatted JSON string.

    This function takes a Python data structure (e.g., a dictionary or list) and
    returns a formatted JSON string with sorted keys, indentation, and specified
    key-value separators.

    Args:
        value: Any valid Python data structure to be converted to JSON.

    Returns:
        str: A pretty-printed JSON string.
    """
    return json.dumps(value, sort_keys=True,
                      indent=4, separators=(',', ': '))


def enum_to_string(obj):
    """
    Convert an Enum member to its string representation (name).

    This function is used to extract the string representation (name) of an Enum
    member. If the input is not an Enum member, the input is returned as is,
    allowing Jinja or other template engines to use their default behavior.

    Args:
        obj: An object that may be an Enum member or any other type.

    Returns:
        str or obj: If `obj` is an Enum member, its name (a string) is returned.
                    If `obj` is not an Enum member, `obj` is returned unchanged.
    """
    if isinstance(obj, enum.Enum):
        return obj.name
    # For all other types, let Jinja use default behavior
    return obj

def str2bool(s):
    """
    Convert a string representation of a boolean to a boolean value.

    This function takes a string 's' and converts it to a boolean value. The conversion
    is case-insensitive and considers values like 'yes', '1', and 'true' as True, while
    values like 'no', '0', and 'false' are considered as False.

    Args:
        s (str): A string representing a boolean value.

    Returns:
        bool: True if 's' represents a truthy value, False otherwise.
    """
    return s.lower() in ['yes', '1', 'true']

def python_eval(obj):
    """
    Safely evaluate a Python expression from a string.

    This function is designed to safely evaluate a Python expression provided as
    a string. If the input is a valid Python expression, it is evaluated. If there
    are any errors during evaluation, a warning message is logged, and the original
    input is returned as is.

    Args:
        obj: A string containing a Python expression to be evaluated.

    Returns:
        Any: If `obj` is a valid Python expression, the result of the evaluation is
             returned. If there is an error during evaluation, `obj` is returned
             unchanged.

    Example:
        result = python_eval("3 + 4")
        print(result)  # Output: 7

        invalid_expr = "3 / 0"
        result = python_eval(invalid_expr)
        print(result)  # Output: "3 / 0" (no division by zero error)
    """
    if isinstance(obj, str):
        try:
            return eval(obj)
        except Exception as e:
            app.logger.warn("Error calling python_eval(): {}".format(e))
    return obj


def gencolors(hue, n):
    """
    Generate a list of random colors with a specified hue and count.

    This function generates a list of random colors with a given hue and count
    using the RandomColor library. The generated colors have a specified luminosity.

    Args:
        hue (str): The hue for the generated colors, e.g., "red", "blue", "green".
        n (int): The number of random colors to generate.

    Returns:
        list: A list of random color strings in hexadecimal format.
    """
    rand_color = randomcolor.RandomColor(42)
    rcolors = rand_color.generate(hue=hue, luminosity="dark", count=n)
    return rcolors


def genstatuscolors(statuses):
    """
    Generate a list of colors corresponding to a list of deployment statuses.

    This function takes a list of deployment statuses and maps each status to a
    specific color. The resulting list contains colors corresponding to each
    status in the input list. Unknown statuses are represented with a default
    light grey color.

    Args:
        statuses (list): A list of deployment statuses, e.g., ["CREATE_COMPLETE",
                         "CREATE_IN_PROGRESS", "DELETE_IN_PROGRESS", ...].

    Returns:
        list: A list of color strings representing the colors for each status.
    """
    colors = []
    for status in statuses:
        if status == "CREATE_COMPLETE":
            colors.append('green')
        elif status == "CREATE_IN_PROGRESS":
            colors.append("lightgreen")
        elif status == "DELETE_IN_PROGRESS":
            colors.append('salmon')
        elif status == "CREATE_FAILED":
            colors.append('red')
        elif status == "DELETE_FAILED":
            colors.append('firebrick')
        else:
            colors.append('lightgrey')
    return colors


def intersect(a, b):
    """
    Compute the intersection of two iterables.

    This function takes two iterable objects (e.g., lists, sets) 'a' and 'b' and
    returns a new set containing elements that are common to both 'a' and 'b'.

    Args:
        a (iterable): The first iterable.
        b (iterable): The second iterable.

    Returns:
        set: A set containing elements that are present in both 'a' and 'b'.
    """
    return set(a).intersection(b)


def extract_netinterface_ips(input):
    """
    Extract network interface IP addresses from a dictionary.

    This function iterates through the keys and values in the input dictionary and
    extracts IP addresses associated with network interfaces. It looks for keys in
    the format 'net_interface.<number>.ip' and converts the keys to a modified
    format with underscores ('_') in the resulting dictionary.

    Args:
        input (dict): A dictionary containing key-value pairs.

    Returns:
        dict: A dictionary with modified keys and their corresponding IP values
              extracted from the input.
    """
    res = {}
    for key,value in input.items():
        if re.match("net_interface.[0-9].ip", key):
            new_key = key.replace('.','_')
            res[new_key] = value

    return res

def xstr(s):
    """
    Convert a value to a string or return an empty string if the value is None.

    This function takes a value 's' and converts it to a string representation if
    's' is not None. If 's' is None, it returns an empty string.

    Args:
        s: Any value that can be converted to a string.

    Returns:
        str: A string representation of 's' if 's' is not None, or an empty string.
    """
    return '' if s is None else str(s)


def nnstr(s):
    """
    Convert a value to a string or return an empty string if the value is None or empty.

    This function takes a value 's' and converts it to a string representation if 's'
    is not None and not an empty string. If 's' is None or an empty string, it returns
    an empty string.

    Args:
        s: Any value that can be converted to a string.

    Returns:
        str: A string representation of 's' if 's' is not None and not an empty string,
             or an empty string.
    """
    return '' if (s is None or s == '') else str(s)


def avatar(email, size):
    """
    Generate a Gravatar URL for a given email address and image size.

    This function generates a Gravatar URL for the provided email address and image
    size. Gravatar is a service that provides globally recognized avatars based on email
    addresses. The URL points to the avatar image, and the 'identicon' is used as the
    default image if no Gravatar is associated with the email.

    Args:
        email (str): The email address for which to generate the Gravatar URL.
        size (int, optional): The size of the Gravatar image (default is 80).

    Returns:
        str: The Gravatar URL with the specified email and image size.
    """
    digest = md5(email.lower().encode('utf-8')).hexdigest()
    return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)


def logexception(err):
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    app.logger.error('{} at ({}, LINE {} "{}"): {}'.format(err, filename, lineno, line.strip(), exc_obj))


def getorchestratorversion(orchestrator_url):
    url = orchestrator_url + "/info"
    response = requests.get(url)

    return response.json()['build']['version']


def getorchestratorconfiguration(orchestrator_url, access_token):
    headers = {'Authorization': 'bearer %s' % access_token}

    url = orchestrator_url + "/configuration"
    response = requests.get(url, headers=headers)

    configuration = {}
    if response.ok:
        configuration = response.json()

    return configuration

def format_json_radl(vminfo):
    res = {}
    for elem in vminfo:
        if elem["class"] == "system":
            for field, value in elem.items():
                if field not in ["class", "id"]:
                    if field.endswith("_min"):
                        field = field[:-4]
                    res[field] = value

    return res


def generate_password():
    alphabet = string.ascii_letters + string.digits
    password = ""
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(10))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and sum(c.isdigit() for c in password) >= 3):
            break

    return password


def send_authorization_request_email(service_type, **kwargs):
    user_email = kwargs['email'] if 'email' in kwargs else ""
    message = kwargs['message'] if 'message' in kwargs else ""
    message = Markup(
        "The following user has requested access for service \"{}\": <br>username: {} " \
        "<br>IAM id (sub): {} <br>IAM groups: {} <br>email registered in IAM: {} " \
        "<br>email provided by the user: {} " \
        "<br>Message: {}".format(service_type, session['username'], session['userid'],
                                 session['usergroups'], session['useremail'], user_email, message))

    sender = kwargs['email'] if 'email' in kwargs else session['useremail']
    send_email("New Authorization Request",
               sender=sender,
               recipients=[app.config.get('SUPPORT_EMAIL')],
               html_body=message)

def send_ports_request_email(deployment_uuid, **kwargs):
    user_email = kwargs['email'] if 'email' in kwargs else ""
    message = kwargs['message'] if 'message' in kwargs else ""
    message = Markup(
        "The following user has requested to open further ports for deployment \"{}\": <br>username: {} " \
        "<br>IAM id (sub): {} <br>email registered in IAM: {} " \
        "<br>email provided by the user: {} " \
        "<br>Message: {}".format(deployment_uuid, session['username'], session['userid'],
                                  session['useremail'], user_email, message))

    sender = kwargs['email'] if 'email' in kwargs else session['useremail']
    send_email("New Ports Request",
               sender=sender,
               recipients=[app.config.get('SUPPORT_EMAIL')],
               html_body=message)

def create_and_send_email(subject, sender, recipients, uuid, status):
    send_email(subject,
               sender=sender,
               recipients=recipients,
               html_body=render_template(app.config.get('MAIL_TEMPLATE'), uuid=uuid, status=status))


def send_email(subject, sender, recipients, html_body):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.html = html_body
    msg.body = "This email is an automatic notification"  # Add plain text, needed to avoid MPART_ALT_DIFF with AntiSpam
    Thread(target=send_async_email, args=(app, msg)).start()


def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)


def has_write_permission(directory):
    parent_directory = os.path.dirname(os.path.normpath(directory))
    try:
        test_file = os.path.join(parent_directory, '.test_file')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return True
    except Exception:
        return False


def backup_directory(directory):
    try:
        backup_path = f"{os.path.normpath(directory)}.bak"
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)
        shutil.copytree(directory, backup_path)
        return backup_path
    except Exception as e:
        app.logger.error(f"Error creating backup: {e}")
        return None


def restore_directory(backup_path, target_directory):
    try:
        if os.path.exists(target_directory):
            shutil.rmtree(target_directory)
        shutil.copytree(backup_path, target_directory)
        return True
    except Exception as e:
        app.logger.error(f"Error restoring directory: {e}")
        return False


def download_git_repo(repo_url, target_directory, tag_or_branch=None, private=False, username=None, deploy_token=None):
    try:
        if not has_write_permission(target_directory):
            return False, "No permission for creating the directory {}".format(target_directory)

        backup_path = backup_directory(target_directory)

        try:
            # Check if the target directory is not empty
            if os.path.exists(target_directory) and os.listdir(target_directory):
                app.logger.warn(f"Warning: Target directory '{target_directory}' is not empty. Removing existing contents.")
                shutil.rmtree(target_directory)

            # Clone the repository
            if private and username and deploy_token:
                git_url = repo_url.replace("https://", f"https://{username}:{deploy_token}@")
                subprocess.run(['git', 'clone', git_url, target_directory], check=True, capture_output=True)
            else:
                subprocess.run(['git', 'clone', repo_url, target_directory], check=True, capture_output=True)

            # Change directory to the cloned repository
            cwd = target_directory
            if tag_or_branch:
                subprocess.run(['git', 'checkout', tag_or_branch], cwd=cwd, check=True, capture_output=True)
                app.logger.info(f"Switched to tag/branch '{tag_or_branch}'.")

            app.logger.info(f"Repository '{repo_url}' (branch: '{tag_or_branch}') downloaded to '{target_directory}'.")
            return True, f"Repository '{repo_url}' (branch: '{tag_or_branch}') downloaded to '{target_directory}'."
        except subprocess.CalledProcessError as e:
            sanitized_error_message = f"{e} {e.stderr.decode('utf-8')}".replace(username + ':' + deploy_token, '[SENSITIVE DATA]')
            restore_directory(backup_path, target_directory)
            app.logger.error(f"Error: {sanitized_error_message}")
            return False, f"Error: {sanitized_error_message}"
    except Exception as e:
        app.logger.error(f"An error occurred: {e}")
        return False, f"An error occurred: {e}"
