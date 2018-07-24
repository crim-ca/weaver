from pyramid.view import view_config
from twitcher.wps_restapi.swagger_definitions import (jobs,
                                                      job_full,
                                                      job_short,
                                                      outputs_full,
                                                      outputs_short,
                                                      output_full,
                                                      output_short,
                                                      exceptions_full,
                                                      exceptions_short,
                                                      logs_full,
                                                      logs_short,
                                                      GetJobs,
                                                      GetJobStatusFull,
                                                      GetJobStatusShort,
                                                      DismissJobFull,
                                                      DismissJobShort,
                                                      GetJobOutputsFull,
                                                      GetJobOutputsShort,
                                                      GetSpecificOutputFull,
                                                      GetSpecificOutputShort,
                                                      GetExceptionsFull,
                                                      GetExceptionsShort,
                                                      GetLogsFull,
                                                      GetLogsShort,
                                                      get_all_jobs_response,
                                                      get_single_job_status_response,
                                                      get_single_job_outputs_response,
                                                      get_single_output_response,
                                                      get_exceptions_response,
                                                      get_logs_response)
import uuid
import requests
from datetime import datetime
from twitcher.db import MongoDB
from twitcher.wps_restapi.utils import restapi_base_url, get_cookie_headers
from twitcher.adapter import servicestore_factory
from pyramid.security import authenticated_userid
from pymongo import ASCENDING, DESCENDING
from pyramid_celery import celery_app as app
from owslib.wps import WPSExecution
from owslib.wps import WebProcessingService

from lxml import etree

from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

status_categories = {
    'Running': ['ProcessAccepted', 'ProcessPaused', 'ProcessStarted'],
    'Finished': ['ProcessSucceeded', 'ProcessFailed']
}


def job_url(request, job):
    return '{base_url}/providers/{provider_id}/processes/{process_id}/jobs/{job_id}'.format(
        base_url=restapi_base_url(request),
        provider_id=job['provider_id'],
        process_id=job['process_id'],
        job_id=job['task_id'])


def add_job(db, task_id, process_id, provider_id, title=None, abstract=None,
            service_name=None, service=None, status_location=None,
            is_workflow=False, caption=None, userid=None,
            async=True):
    tags = ['dev']
    if is_workflow:
        tags.append('workflow')
    else:
        tags.append('single')
    if async:
        tags.append('async')
    else:
        tags.append('sync')
    job = dict(
        identifier=uuid.uuid4().get_hex(),
        task_id=task_id,             # TODO: why not using as identifier?
        userid=userid,
        is_workflow=is_workflow,
        service_name=service_name,        # wps service name (service identifier)
        service=service or service_name,  # wps service title (url, service_name or service title)
        process_id=process_id,                  # process identifier
        provider_id=provider_id,  # process identifier
        title=title or process_id,              # process title (identifier or title)
        abstract=abstract or "No Summary",
        status_location=status_location,
        created=datetime.now(),
        tags=tags,
        caption=caption,
        status="ProcessAccepted",
        response=None,
        request=None,
    )
    db.jobs.insert(job)
    return job


def check_status(url=None, response=None, sleep_secs=2, verify=False):
    """
    Run owslib.wps check_status with additional exception handling.

    :param verify: Flag to enable SSL verification. Default: False
    :return: OWSLib.wps.WPSExecution object.
    """
    execution = WPSExecution()
    if response:
        logger.debug("using response document ...")
        xml = response
    elif url:
        logger.debug('using status_location url ...')
        xml = requests.get(url, verify=verify).content
    else:
        raise Exception("you need to provide a status-location url or response object.")
    if type(xml) is unicode:
        xml = xml.encode('utf8', errors='ignore')
    execution.checkStatus(response=xml, sleepSecs=sleep_secs)
    if execution.response is None:
        raise Exception("check_status failed!")
    # TODO: workaround for owslib type change of reponse
    if not isinstance(execution.response, etree._Element):
        execution.response = etree.fromstring(execution.response)
    return execution


def filter_jobs(collection, request, page=0, limit=10, process=None, provider=None, tag=None, access=None, status=None, sort='created'):
    search_filter = {}
    if access == 'public':
        search_filter['tags'] = 'public'
    elif access == 'private':
        search_filter['tags'] = {'$ne': 'public'}
        search_filter['userid'] = authenticated_userid(request)
    elif access == 'all' and request.has_permission('admin'):
        pass
    else:
        if tag is not None:
            search_filter['tags'] = tag
        search_filter['userid'] = authenticated_userid(request)

    if status in status_categories.keys():
        search_filter['status'] = {'$in': status_categories[status]}
    elif status:
        search_filter['status'] = status

    if process is not None:
        search_filter['process_id'] = process

    if provider is not None:
        search_filter['provider_id'] = provider

    count = collection.find(search_filter).count()
    if sort == 'user':
        sort = 'userid'
    elif sort == 'process':
        sort = 'title'

    sort_order = DESCENDING if sort == 'finished' or sort == 'created' else ASCENDING
    sort_criteria = [(sort, sort_order)]
    items = list(collection.find(search_filter).skip(page * limit).limit(limit).sort(sort_criteria))
    return items, count


@jobs.get(tags=['jobs'], schema=GetJobs(), response_schemas=get_all_jobs_response)
def get_jobs(request):
    """
    Retrieve the list of jobs which can be filtered/sorted using :
    ?page=[number]
    &limit=[number]
    &status=[ProcessAccepted, ProcessStarted, ProcessPaused, ProcessFailed, ProcessSucceeded] 
    &process=[process_name]
    &provider=[provider_id]
    &sort=[created, status, process, provider]
    """

    page = int(request.params.get('page', '0'))
    limit = int(request.params.get('limit', '10'))
    process = request.params.get('process', None)
    provider = request.params.get('provider', None)
    tag = request.params.get('tag', None)
    access = request.params.get('access', None)
    status = request.params.get('status', None)
    sort = request.params.get('sort', 'created')

    db = MongoDB.get(request.registry)
    collection = db.jobs

    items, count = filter_jobs(collection, request, page, limit, process, provider, tag, access, status, sort)
    return {
        'count': count,
        'page': page,
        'limit': limit,
        'jobs': [{
            'jobID': item['task_id'],
            'status': item['status'],
            'location': job_url(request, item)
        } for item in items]
    }


def get_job(request):
    # TODO Validate param somehow
    job_id = request.matchdict.get('job_id')

    db = MongoDB.get(request.registry)
    collection = db.jobs
    job = collection.find_one({'task_id': job_id})

    if job:
        provider_id = request.matchdict.get('provider_id', job['provider_id'])
        process_id = request.matchdict.get('process_id', job['process_id'])

        if job['provider_id'] != provider_id or job['process_id'] != process_id:
            return None
    return job


@job_full.get(tags=['jobs'], schema=GetJobStatusFull(), response_schemas=get_single_job_status_response)
@job_short.get(tags=['jobs'], schema=GetJobStatusShort(), response_schemas=get_single_job_status_response)
def get_job_status(request):
    """
    Retrieve the status of a job
    """
    job = get_job(request)
    if not job:
        # TODO Return a not found job response
        return 404

    response = {
        "jobID": job['task_id'],
        "status": job['status']
    }
    if job['status'] in status_categories['Running']:
        response["Progress"] = job['progress'] if 'progress' in job else 0
    else:
        if job['status'] == 'ProcessSucceeded':
            resource = 'outputs'
        else:
            resource = 'exceptions'

        response[resource] = '{job_url}/{resource}'.format(job_url=job_url(request, job), resource=resource.lower())
        response['log'] = '{job_url}/log'.format(job_url=job_url(request, job))

    return response


@job_full.delete(tags=['jobs'], schema=DismissJobFull())
@job_short.delete(tags=['jobs'], schema=DismissJobShort())
def cancel_job(request):
    """
    Dismiss a job.
    Note: Will only stop tracking this particular process (WPS 1.0 doesn't allow to stop a process)
    """
    job = get_job(request)
    if not job:
        # TODO Return a not found job response
        return 404

    app.control.revoke(job['task_id'], terminate=True)

    return 200


@outputs_full.get(tags=['jobs'], schema=GetJobOutputsFull(), response_schemas=get_single_job_outputs_response)
@outputs_short.get(tags=['jobs'], schema=GetJobOutputsShort(), response_schemas=get_single_job_outputs_response)
def get_outputs(request):
    """
    Retrieve the result(s) of a job
    """
    job = get_job(request)
    if not job:
        # TODO Return a not found job response
        return 404

    outputs = job['outputs']
    for output in outputs:
        output['url'] = '{job_url}/outputs/{output_id}'.format(job_url=job_url(request, job),
                                                               output_id=output['identifier'])
    return outputs


@output_full.get(tags=['jobs'], schema=GetSpecificOutputFull(), response_schemas=get_single_output_response)
@output_short.get(tags=['jobs'], schema=GetSpecificOutputShort(), response_schemas=get_single_output_response)
def get_output(request):
    """
    Retrieve the result of a particular job output
    """
    job = get_job(request)
    if not job:
        # TODO Return a not found job response
        return 404

    output_id = request.matchdict.get('output_id')

    for output in job['outputs']:
        if output['identifier'] == output_id:
            output['url'] = '{job_url}/outputs/{output_id}'.format(job_url=job_url(request, job),
                                                                   output_id=output['identifier'])
            return output
    return 404


@exceptions_full.get(tags=['jobs'], schema=GetExceptionsFull(), response_schemas=get_exceptions_response)
@exceptions_short.get(tags=['jobs'], schema=GetExceptionsShort(), response_schemas=get_exceptions_response)
def get_exceptions(request):
    """
    Retrieve the result(s) of a job"
    """
    job = get_job(request)
    if not job:
        # TODO Return a not found job response
        return 404

    return job['exceptions']


@logs_full.get(tags=['jobs'], schema=GetLogsFull(), response_schemas=get_logs_response)
@logs_short.get(tags=['jobs'], schema=GetLogsShort(), response_schemas=get_logs_response)
def get_log(request):
    """
    Retrieve the result(s) of a job"
    """
    job = get_job(request)
    if not job:
        # TODO Return a not found job response
        return 404

    return job['log']
