import base64
import logging
import os
import secrets
import smtplib
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from mako.template import Template
from pyramid.settings import asbool

from weaver import WEAVER_MODULE_DIR
from weaver.datatype import Job
from weaver.processes.constants import JobInputsOutputsSchema
from weaver.status import Status, StatusCategory, map_status
from weaver.utils import bytes2str, fully_qualified_name, get_settings, request_extra, str2bytes
from weaver.wps_restapi.jobs.utils import get_results

if TYPE_CHECKING:
    from typing import Optional

    from weaver.typedefs import AnySettingsContainer, ExecutionSubscribers, JSON, SettingsType

LOGGER = logging.getLogger(__name__)

__SALT_LENGTH__ = 16
__TOKEN_LENGTH__ = 32
__ROUNDS_LENGTH__ = 4
__DEFAULT_ROUNDS__ = 100_000


def resolve_email_template(job, settings):
    # type: (Job, SettingsType) -> Template
    """
    Finds the most appropriate Mako Template email notification file based on configuration and :term:`Job` context.

    The example template is used by default *ONLY* if the template directory was not overridden. If overridden, failing
    to match any of the template file locations will raise to report the issue instead of silently using the default.

    .. seealso::
        https://github.com/crim-ca/weaver/blob/master/weaver/wps_restapi/templates/notification_email_example.mako

    :raises IOError:
        If the template directory was configured explicitly, but cannot be resolved, or if any of the possible
        combinations of template file names cannot be resolved under that directory.
    :returns: Matched template instance based on resolution order as described in the documentation.
    """
    template_dir = settings.get("weaver.wps_email_notify_template_dir") or ""

    # find appropriate template according to settings
    if not template_dir and not os.path.isdir(template_dir):
        LOGGER.warning("No default email template directory configured. Using default template.")
        template_file = os.path.join(WEAVER_MODULE_DIR, "wps_restapi/templates/notification_email_example.mako")
        template = Template(filename=template_file)  # nosec: B702
    else:
        default_setting = "weaver.wps_email_notify_template_default"
        default_default = "default.mako"
        default_name = settings.get(default_setting) or default_default
        process_name = f"{job.process!s}.mako"
        process_status_name = f"{job.process!s}/{job.status!s}.mako"
        default_template = os.path.join(template_dir, default_name)
        process_template = os.path.join(template_dir, process_name)
        process_status_template = os.path.join(template_dir, process_status_name)
        if os.path.isfile(process_status_template):
            template = Template(filename=process_status_template)  # nosec: B702
        elif os.path.isfile(process_template):
            template = Template(filename=process_template)  # nosec: B702
        elif os.path.isfile(default_template):
            template = Template(filename=default_template)  # nosec: B702
        else:
            raise IOError(
                f"No Mako Template file could be resolved under the template directory: [{template_dir}]. Expected "
                f"OneOf[{process_status_name!s}, {process_name!s}, {{{default_setting!s}}}, {default_default!s}]"
            )
    return template


def notify_job_email(job, to_email_recipient, container):
    # type: (Job, str, AnySettingsContainer) -> None
    """
    Send email notification of a :term:`Job` status.
    """
    settings = get_settings(container)
    smtp_host = settings.get("weaver.wps_email_notify_smtp_host")
    from_addr = settings.get("weaver.wps_email_notify_from_addr")
    password = settings.get("weaver.wps_email_notify_password")
    timeout = int(settings.get("weaver.wps_email_notify_timeout") or 10)
    port = settings.get("weaver.wps_email_notify_port")
    ssl = asbool(settings.get("weaver.wps_email_notify_ssl", True))

    if not smtp_host or not port:  # pragma: no cover  # only raise to warn service manager
        # note: don't expose the values to avoid leaking them in logs
        raise ValueError(
            "The email server configuration is missing or incomplete. "
            "Validate that SMTP host and port are properly configured."
        )
    port = int(port)

    template = resolve_email_template(job, settings)
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


def map_job_subscribers(job_body, settings):
    # type: (JSON, SettingsType) -> Optional[ExecutionSubscribers]
    """
    Converts the :term:`Job` subscribers definition submitted at execution into a mapping for later reference.

    The returned contents must be sorted in the relevant :term:`Job` object.
    For backward compatibility, ``notification_email`` directly provided at the root will be used if corresponding
    definitions were not provided for the corresponding subscriber email fields.
    """
    notification_email = job_body.get("notification_email")
    submit_subscribers = job_body.get("subscribers") or {}
    mapped_subscribers = {}
    for status_category, name, sub_type, alt in [
        (StatusCategory.RUNNING, "inProgressEmail", "emails", None),
        (StatusCategory.FAILED, "failedEmail", "emails", notification_email),
        (StatusCategory.SUCCESS, "successEmail", "emails", notification_email),
        (StatusCategory.RUNNING, "inProgressUri", "callbacks", None),
        (StatusCategory.FAILED, "failedUri", "callbacks", None),
        (StatusCategory.SUCCESS, "successUri", "callbacks", None),
    ]:
        value = submit_subscribers.get(name) or alt
        if not value:
            continue
        if sub_type == "emails":
            value = encrypt_email(value, settings)
        status_category = status_category.value.lower()
        mapped_subscribers.setdefault(sub_type, {})
        mapped_subscribers[sub_type][status_category] = value
    return mapped_subscribers or None


def send_job_notification_email(job, task_logger, settings):
    # type: (Job, logging.Logger, SettingsType) -> None
    """
    Sends a notification email about the execution status for the subscriber if requested during :term:`Job` submission.
    """
    job_subs = job.subscribers or {}
    job_status_category = map_status(job.status, category=True)
    if job_status_category == Status.UNKNOWN:  # pragma: no cover
        LOGGER.warning("Unknown status unmapped in subscribers notification email: [%s]", job.status)
        return
    category = job_status_category.value.lower()
    notification_email = job_subs.get("emails", {}).get(category)
    if notification_email:
        try:
            email = decrypt_email(notification_email, settings)
            notify_job_email(job, email, settings)
            message = "Notification email sent successfully."
            job.save_log(logger=task_logger, message=message)
        except Exception as exc:  # pragma: no cover
            exception = f"{fully_qualified_name(exc)}: {exc!s}"
            message = f"Couldn't send notification email: [{exception}]"
            job.save_log(errors=message, logger=task_logger, message=message)


def send_job_callback_request(job, task_logger, settings):
    # type: (Job, logging.Logger, SettingsType) -> None
    """
    Send a callback request about the execution status for the subscriber if requested at :term:`Job` execution.
    """
    job_subs = job.subscribers or {}
    job_status_category = map_status(job.status, category=True)
    if job_status_category == Status.UNKNOWN:  # pragma: no cover
        LOGGER.warning("Unknown status unmapped in subscribers callback request: [%s]", job.status)
        return
    category = job_status_category.value.lower()
    request_uri = job_subs.get("callbacks", {}).get(category)
    if request_uri:
        try:
            if job_status_category != StatusCategory.SUCCESS:
                body = job.json(settings)
            else:
                # OGC-compliant request body needed to respect 'subscribers' callback definition
                # (https://github.com/opengeospatial/ogcapi-processes/blob/master/core/examples/yaml/callbacks.yaml)
                body, _ = get_results(
                    job,
                    settings,
                    value_key="value",
                    schema=JobInputsOutputsSchema.OGC,
                    link_references=False,
                )
            request_extra(
                "POST",
                request_uri,
                json=body,
                allowed_codes=[200, 201, 202],
                cache_enabled=False,
                settings=settings,
            )
            message = "Notification callback request sent successfully."
            job.save_log(logger=task_logger, message=message)
        except Exception as exc:  # pragma: no cover
            exception = f"{fully_qualified_name(exc)}: {exc!s}"
            message = f"Couldn't send notification callback request: [{exception}]"
            job.save_log(errors=message, logger=task_logger, message=message)


def notify_job_subscribers(job, task_logger, settings):
    # type: (Job, logging.Logger, SettingsType) -> None
    """
    Send notifications to all requested :term:`Job` subscribers according to its current status.

    All notification operations must be implemented as non-raising.
    In case of error, the :term:`Job` logs will be updated with relevant error details and resume execution.
    """
    try:
        send_job_notification_email(job, task_logger, settings)
        send_job_callback_request(job, task_logger, settings)
    except Exception as exc:  # pragma: no cover
        exception = f"{fully_qualified_name(exc)}: {exc!s}"
        message = (
            f"Unhandled error occurred when processing a job notification subscriber: [{exception}]. "
            "Error ignored to resume execution."
        )
        job.save_log(errors=message, logger=task_logger, message=message)
