from weaver.datatype import Job
from mako.template import Template
from typing import TYPE_CHECKING
import os
import smtplib
if TYPE_CHECKING:
    from typing import Dict


def notify_job(job, job_json, to, settings):
    # type: (Job, Dict, str, Dict) -> None
    subject = "Job {} {}".format(job.process, job.status.title())
    smtp_host = settings.get("weaver.wps_email_notify_smtp_host")
    from_addr = settings.get("weaver.wps_email_notify_from_addr")
    password = settings.get("weaver.wps_email_notify_password")
    port = settings.get("weaver.wps_email_notify_port")
    ssl = settings.get("weaver.wps_email_notify_ssl")
    # an example template is located in
    # weaver/wps_restapi/templates/notification_email_example.mako
    template_path = settings.get("weaver.wps_email_notify_template")

    if not os.path.exists(template_path):
        raise IOError("Template file doesn't exist: {}".format(template_path))

    template = Template(filename=template_path)
    contents = template.render(job=job, **job_json)

    message = 'Subject: {}\n\n{}'.format(subject, contents)

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
        result = server.sendmail(from_addr, to, message)
    finally:
        server.close()

    if result:
        code, error_message = result[to]
        raise IOError("Code: {}, Message: {}".format(code, error_message))
