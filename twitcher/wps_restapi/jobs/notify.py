import yagmail
from typing import Dict

from twitcher.datatype import Job


def notify_job(job, to, settings):
    # type: (Job, str, Dict) -> None
    subject = "Job {} {}".format(job.process, job.status.title())

    from_addr = settings.get('twitcher.wps_email_notify_from_addr')
    password = settings.get('twitcher.wps_email_notify_password')

    user = {from_addr: "WPS Notifications"}

    yag = yagmail.SMTP(user=user, password=password)
    contents = job.logs

    yag.send(to, subject, contents)
