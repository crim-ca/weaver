from weaver.datatype import Job
from mako.template import Template
from typing import TYPE_CHECKING
import yagmail
import os
if TYPE_CHECKING:
    from typing import Dict


def notify_job(job, job_json, to, settings):
    # type: (Job, Dict, str, Dict) -> None
    subject = "Job {} {}".format(job.process, job.status.title())
    from_addr = settings.get("weaver.wps_email_notify_from_addr")
    password = settings.get("weaver.wps_email_notify_password")
    user = {from_addr: "WPS Notifications"}
    yag = yagmail.SMTP(user=user, password=password)

    # an example template is located in
    # weaver/wps_restapi/templates/notification_email_example.mako
    template_path = settings.get("weaver.wps_email_notify_template")
    if not os.path.exists(template_path):
        raise IOError("Template file doesn't exist: {}".format(template_path))

    template = Template(filename=template_path)
    contents = template.render(job=job, **job_json)
    yag.send(to, subject, contents)
