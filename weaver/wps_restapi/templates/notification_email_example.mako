## -*- coding: utf-8 -*-
<%doc>
    This is an example notification message to be sent by email when a job is done
    It is formatted using the Mako template library (https://www.makotemplates.org/)

    The provided variables are:
    job: a weaver.datatype.Job object

    And every variable returned by the `weaver.wps_restapi.jobs.jobs.job_format_json` function:
    status:           success, failure, etc
    logs:             url to the logs
    jobID:	          example "617f23d3-f474-47f9-a8ec-55da9dd6ac71"
    result:           url to the outputs
    duration:         example "0:01:02"
    message:          example "Job succeeded."
    percentCompleted: example "100"
</%doc>

Dear user,

Your job submitted on ${job.created.strftime('%Y/%m/%d %H:%M %Z')} ${job.status}.

% if job.status == 'succeeded':
You can retrieve the output(s) at the following link: ${result}
% endif

The logs are available here: ${logs}

Regards,
