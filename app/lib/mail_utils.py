# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2021
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
from app import app, mail
from flask_mail import Message
from threading import Thread
from flask import session, render_template
from markupsafe import Markup

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

