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

        status:           succeeded, failed, started
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
