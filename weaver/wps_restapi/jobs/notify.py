from __future__ import unicode_literals
from weaver.datatype import Job
from weaver.utils import str2bytes, bytes2str
from pyramid.settings import asbool
from mako.template import Template
from typing import TYPE_CHECKING
import os
import six
import smtplib
import hashlib
import binascii
import logging
if TYPE_CHECKING:
    from typing import Dict

LOGGER = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """
<%doc>
    This is an example notification message to be sent by email when a job is
    done. It is formatted using the Mako template library
    (https://www.makotemplates.org/). The content must also include the message
    header.

    The provided variables are:
    to: Recipient's address
    job: a weaver.datatype.Job object
    settings: application settings

    And every variable returned by the `weaver.wps_restapi.jobs.jobs.job_format_json` function:
    status:           succeeded, failed
    logs:             url to the logs
    jobID:	          example "617f23d3-f474-47f9-a8ec-55da9dd6ac71"
    result:           url to the outputs
    duration:         example "0:01:02"
    message:          example "Job succeeded."
    percentCompleted: example "100"
</%doc>
From: Weaver
To: ${to}
Subject: Job ${job.process} ${job.status.title()}
Content-Type: text/plain; charset=UTF-8

Dear user,

Your job submitted on ${job.created.strftime('%Y/%m/%d %H:%M %Z')} to ${settings.get('weaver.url')} ${job.status}.

% if job.status == 'succeeded':
You can retrieve the output(s) at the following link: ${job.results[0]['reference']}
% endif

The logs are available here: ${logs}

Regards,
Weaver
"""


def notify_job(job, job_json, to, settings):
    # type: (Job, Dict, str, Dict) -> None
    smtp_host = settings.get("weaver.wps_email_notify_smtp_host")
    from_addr = settings.get("weaver.wps_email_notify_from_addr")
    password = settings.get("weaver.wps_email_notify_password")
    port = settings.get("weaver.wps_email_notify_port")
    ssl = asbool(settings.get("weaver.wps_email_notify_ssl"))
    # an example template is located in
    # weaver/wps_restapi/templates/notification_email_example.mako
    template_dir = settings.get("weaver.wps_email_notify_template_dir")

    if not smtp_host or not port:
        raise ValueError("The email server configuration is missing.")

    # find appropriate template according to settings
    if not os.path.isdir(template_dir):
        LOGGER.warning("No default email template directory configured. Using default format.")
        template = Template(text=DEFAULT_TEMPLATE)
    else:
        default_name = settings.get("weaver.wps_email_notify_template_default", "default.mako")
        process_name = "{!s}.mako".format(job.process)
        default_template = os.path.join(template_dir, default_name)
        process_template = os.path.join(template_dir, process_name)
        if os.path.isfile(process_template):
            template = Template(filename=process_template)
        elif os.path.isfile(default_template):
            template = Template(filename=default_template)
        else:
            raise IOError("Template file doesn't exist: OneOf[{!s}, {!s}]".
                          format(process_name, default_name))

    contents = template.render(to=to, job=job, settings=settings, **job_json)
    message = u'{}'.format(contents).strip(u'\n')

    if ssl:
        server = smtplib.SMTP_SSL(smtp_host, port)
    else:
        server = smtplib.SMTP(smtp_host, port)
        server.ehlo()
        try:
            server.starttls()
            server.ehlo()
        except smtplib.SMTPException:
            pass

    try:
        if password:
            server.login(from_addr, password)
        result = server.sendmail(from_addr, to, message.encode("utf8"))
    finally:
        server.close()

    if result:
        code, error_message = result[to]
        raise IOError("Code: {}, Message: {}".format(code, error_message))


def encrypt_email(email, settings):
    if not email or not isinstance(email, six.string_types):
        raise TypeError("Invalid email: {!s}".format(email))
    LOGGER.debug("Job email setup.")
    try:
        salt = str2bytes(settings.get("weaver.wps_email_encrypt_salt"))
        email = str2bytes(email)
        rounds = int(settings.get("weaver.wps_email_encrypt_rounds", 100000))
        derived_key = hashlib.pbkdf2_hmac("sha256", email, salt, rounds)
        return bytes2str(binascii.hexlify(derived_key))
    except Exception as ex:
        LOGGER.debug("Job email setup failed [{!r}].".format(ex))
        raise ValueError("Cannot register job, server not properly configured for notification email.")
