import base64
import logging
import os
import secrets
import smtplib
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import TYPE_CHECKING

from mako.template import Template
from pyramid.settings import asbool

from weaver.datatype import Job
from weaver.utils import bytes2str, get_settings, str2bytes

if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer, SettingsType

LOGGER = logging.getLogger(__name__)

__DEFAULT_TEMPLATE__ = """
<%doc>
    This is an example notification message to be sent by email when a job is done.
    It is formatted using the Mako template library (https://www.makotemplates.org/).
    The content must also include the message header.

    The provided variables are:
    to: Recipient's address
    job: weaver.datatype.Job object
    settings: application settings

    And every variable returned by the `weaver.datatype.Job.json` method.
    Below is a non-exhaustive list of example parameters from this method.
    Refer to the method for complete listing.

        status:           succeeded, failed
        logs:             url to the logs
        jobID:            example "617f23d3-f474-47f9-a8ec-55da9dd6ac71"
        result:           url to the outputs
        duration:         example "0:01:02"
        message:          example "Job succeeded."
        percentCompleted: example 100
</%doc>
From: Weaver
To: ${to}
Subject: Job ${job.process} ${job.status.title()}
Content-Type: text/plain; charset=UTF-8

Dear user,

Your job submitted on ${job.created.strftime("%Y/%m/%d %H:%M %Z")} to ${settings.get("weaver.url")} ${job.status}.

% if job.status == "succeeded":
You can retrieve the output(s) at the following link: ${job.results_url(settings)}
% elif job.status == "failed":
You can retrieve potential error details from the following link: ${job.exceptions_url(settings)}
% endif

The job logs are available at the following link: ${job.logs_url(settings)}

Regards,
Weaver
"""

__SALT_LENGTH__ = 16
__TOKEN_LENGTH__ = 32
__ROUNDS_LENGTH__ = 4
__DEFAULT_ROUNDS__ = 100_000


def notify_job_complete(job, to_email_recipient, container):
    # type: (Job, str, AnySettingsContainer) -> None
    """
    Send email notification of a job completion.
    """
    settings = get_settings(container)
    smtp_host = settings.get("weaver.wps_email_notify_smtp_host")
    from_addr = settings.get("weaver.wps_email_notify_from_addr")
    password = settings.get("weaver.wps_email_notify_password")
    timeout = int(settings.get("weaver.wps_email_notify_timeout") or 10)
    port = settings.get("weaver.wps_email_notify_port")
    ssl = asbool(settings.get("weaver.wps_email_notify_ssl", True))
    # an example template is located in
    # weaver/wps_restapi/templates/notification_email_example.mako
    template_dir = settings.get("weaver.wps_email_notify_template_dir") or ""

    if not smtp_host or not port:
        raise ValueError("The email server configuration is missing.")
    port = int(port)

    # find appropriate template according to settings
    if not os.path.isdir(template_dir):
        LOGGER.warning("No default email template directory configured. Using default format.")
        template = Template(text=__DEFAULT_TEMPLATE__)  # nosec: B702
    else:
        default_name = settings.get("weaver.wps_email_notify_template_default", "default.mako")
        process_name = f"{job.process!s}.mako"
        default_template = os.path.join(template_dir, default_name)
        process_template = os.path.join(template_dir, process_name)
        if os.path.isfile(process_template):
            template = Template(filename=process_template)  # nosec: B702
        elif os.path.isfile(default_template):
            template = Template(filename=default_template)  # nosec: B702
        else:
            raise IOError(f"Template file doesn't exist: OneOf[{process_name!s}, {default_name!s}]")

    job_json = job.json(settings)
    contents = template.render(to=to_email_recipient, job=job, settings=settings, **job_json)
    message = f"{contents}".strip("\n")

    if ssl:
        server = smtplib.SMTP_SSL(smtp_host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(smtp_host, port, timeout=timeout)
        server.ehlo()
        try:
            server.starttls()
            server.ehlo()
        except smtplib.SMTPException:
            pass

    try:
        if password:
            server.login(from_addr, password)
        result = server.sendmail(from_addr, to_email_recipient, message.encode("utf8"))
    finally:
        server.close()

    if result:
        code, error_message = result[to_email_recipient]
        raise IOError(f"Code: {code}, Message: {error_message}")


# https://stackoverflow.com/a/55147077
def get_crypto_key(settings, salt, rounds):
    # type: (SettingsType, bytes, int) -> bytes
    """
    Get the cryptographic key used for encoding and decoding the email.
    """
    backend = default_backend()
    pwd = str2bytes(settings.get("weaver.wps_email_encrypt_salt"))  # use old param for backward-compat even if not salt
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=__TOKEN_LENGTH__, salt=salt, iterations=rounds, backend=backend)
    return base64.urlsafe_b64encode(kdf.derive(pwd))


def encrypt_email(email, settings):
    # type: (str, SettingsType) -> str
    if not email or not isinstance(email, str):
        raise TypeError(f"Invalid email: {email!s}")
    LOGGER.debug("Job email encrypt.")
    try:
        salt = secrets.token_bytes(__SALT_LENGTH__)
        rounds = int(settings.get("weaver.wps_email_encrypt_rounds", __DEFAULT_ROUNDS__))
        iters = rounds.to_bytes(__ROUNDS_LENGTH__, "big")
        key = get_crypto_key(settings, salt, rounds)
        msg = base64.urlsafe_b64decode(Fernet(key).encrypt(str2bytes(email)))
        token = salt + iters + msg
        return bytes2str(base64.urlsafe_b64encode(token))
    except Exception as ex:
        LOGGER.debug("Job email encrypt failed [%r].", ex)
        raise ValueError("Cannot register job, server not properly configured for notification email.")


def decrypt_email(email, settings):
    # type: (str, SettingsType) -> str
    if not email or not isinstance(email, str):
        raise TypeError(f"Invalid email: {email!s}")
    LOGGER.debug("Job email decrypt.")
    try:
        token = base64.urlsafe_b64decode(str2bytes(email))
        salt = token[:__SALT_LENGTH__]
        iters = int.from_bytes(token[__SALT_LENGTH__:__SALT_LENGTH__ + __ROUNDS_LENGTH__], "big")
        token = base64.urlsafe_b64encode(token[__SALT_LENGTH__ + __ROUNDS_LENGTH__:])
        key = get_crypto_key(settings, salt, iters)
        return bytes2str(Fernet(key).decrypt(token))
    except Exception as ex:
        LOGGER.debug("Job email decrypt failed [%r].", ex)
        raise ValueError("Cannot complete job, server not properly configured for notification email.")
