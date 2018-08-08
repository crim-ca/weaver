from pyramid.httpexceptions import *
from pyramid.security import authenticated_userid
from pyramid_celery import celery_app as app
from datetime import datetime
from twitcher.db import MongoDB
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.utils import wps_restapi_base_url
from twitcher.wps_restapi.status import *
from twitcher.wps_restapi.sort import *
from pymongo import ASCENDING, DESCENDING
from owslib.wps import WPSExecution
from lxml import etree
from celery.utils.log import get_task_logger
import uuid
import requests

logger = get_task_logger(__name__)


def job_url(request, job):
    return '{base_url}/providers/{provider_id}/processes/{process_id}/jobs/{job_id}'.format(
        base_url=wps_restapi_base_url(request.registry.settings),
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
        status=STATUS_ACCEPTED,
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
    # TODO: workaround for owslib type change of response
    if not isinstance(execution.response, etree._Element):
        execution.response = etree.fromstring(execution.response)
    return execution


def filter_jobs(collection, request, page=0, limit=10, process=None,
                provider=None, tag=None, access=None, status=None, sort=SORT_CREATED):
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
    if sort == SORT_USER:
        sort = 'userid'
    elif sort == SORT_PROCESS:
        sort = SORT_TITLE

    sort_order = DESCENDING if sort == SORT_FINISHED or sort == SORT_CREATED else ASCENDING
    sort_criteria = [(sort, sort_order)]
    items = list(collection.find(search_filter).skip(page * limit).limit(limit).sort(sort_criteria))
    return items, count


def get_job(request):
    """
    :returns: Job information if found.
    :raises: HTTPNotFound with JSON body details on missing/non-matching job, process, provider IDs.
    """
    job_id = request.matchdict.get('job_id')

    db = MongoDB.get(request.registry)
    collection = db.jobs
    job = collection.find_one({'task_id': job_id})

    if not job:
        raise HTTPNotFound('Could not find specified `job_id`.')

    provider_id = request.matchdict.get('provider_id', job['provider_id'])
    process_id = request.matchdict.get('process_id', job['process_id'])

    if job['provider_id'] != provider_id:
        raise HTTPNotFound('Could not find specified `provider_id`.')
    if job['process_id'] != process_id:
        raise HTTPNotFound('Could not find specified `process_id`.')
    return job


@sd.jobs_service.get(tags=[sd.jobs_tag], renderer='json',
                     schema=sd.GetJobsRequest(), response_schemas=sd.get_all_jobs_responses)
def get_jobs(request):
    """
    Retrieve the list of jobs which can be filtered/sorted using queries.
    """

    page = int(request.params.get('page', '0'))
    limit = int(request.params.get('limit', '10'))
    process = request.params.get('process', None)
    provider = request.params.get('provider', None)
    tag = request.params.get('tag', None)
    access = request.params.get('access', None)
    status = request.params.get('status', None)
    sort = request.params.get('sort', SORT_CREATED)

    db = MongoDB.get(request.registry)
    collection = db.jobs

    items, count = filter_jobs(collection, request, page, limit, process, provider, tag, access, status, sort)
    return HTTPOk(json={
        'count': count,
        'page': page,
        'limit': limit,
        'jobs': [{
            'jobID': item['task_id'],
            'status': item['status'],
            'location': job_url(request, item)
        } for item in items]
    })


@sd.job_full_service.get(tags=[sd.jobs_tag, sd.status_tag], renderer='json',
                         schema=sd.FullJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.job_short_service.get(tags=[sd.jobs_tag, sd.status_tag], renderer='json',
                          schema=sd.ShortJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
def get_job_status(request):
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    response = {
        "jobID": job['task_id'],
        "status": job['status']
    }
    if job['status'] in status_categories[STATUS_RUNNING]:
        response["Progress"] = job['progress'] if 'progress' in job else 0
    else:
        if job['status'] == STATUS_SUCCEEDED:
            resource = 'outputs'
        else:
            resource = 'exceptions'

        response[resource] = '{job_url}/{resource}'.format(job_url=job_url(request, job), resource=resource.lower())
        response['log'] = '{job_url}/log'.format(job_url=job_url(request, job))

    return HTTPOk(json=response)


@sd.job_full_service.delete(tags=[sd.jobs_tag, sd.dismiss_tag], renderer='json',
                            schema=sd.FullJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_short_service.delete(tags=[sd.jobs_tag, sd.dismiss_tag], renderer='json',
                             schema=sd.ShortJobEndpoint(), response_schemas=sd.delete_job_responses)
def cancel_job(request):
    """
    Dismiss a job.
    Note: Will only stop tracking this particular process (WPS 1.0 doesn't allow to stop a process)
    """
    job = get_job(request)
    app.control.revoke(job['task_id'], terminate=True)

    return HTTPOk(json={
        'status': job.get('status', 'unknown'),
        'message': 'Job dismissed.',
        'progress': job.get('progress', 0),
    })


@sd.results_full_service.get(tags=[sd.jobs_tag, sd.result_tag], renderer='json',
                             schema=sd.FullJobEndpoint(), response_schemas=sd.get_single_job_results_responses)
@sd.results_short_service.get(tags=[sd.jobs_tag, sd.result_tag], renderer='json',
                              schema=sd.ShortJobEndpoint(), response_schemas=sd.get_single_job_results_responses)
def get_job_results(request):
    """
    Retrieve the result(s) of a job.
    """
    job = get_job(request)
    outputs = job['outputs']
    for output in outputs:
        output['url'] = '{job_url}/outputs/{result_id}'.format(job_url=job_url(request, job),
                                                               result_id=output['identifier'])
    return HTTPOk(json=outputs)


@sd.result_full_service.get(tags=[sd.jobs_tag, sd.result_tag], renderer='json',
                            schema=sd.FullOutputEndpoint(), response_schemas=sd.get_single_result_responses)
@sd.result_short_service.get(tags=[sd.jobs_tag, sd.result_tag], renderer='json',
                             schema=sd.ShortOutputEndpoint(), response_schemas=sd.get_single_result_responses)
def get_job_result(request):
    """
    Retrieve the result of a particular job output.
    """
    job = get_job(request)
    result_id = request.matchdict.get('result_id')

    for output in job['outputs']:
        if output['identifier'] == result_id:
            output['url'] = '{job_url}/outputs/{result_id}'.format(job_url=job_url(request, job),
                                                                   result_id=output['identifier'])
            return HTTPOk(json=output)
    raise HTTPNotFound('Could not find job output.')


@sd.exceptions_full_service.get(tags=[sd.jobs_tag], renderer='json',
                                schema=sd.FullExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.exceptions_short_service.get(tags=[sd.jobs_tag], renderer='json',
                                 schema=sd.ShortExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
def get_job_exceptions(request):
    """
    Retrieve the result(s) of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job['exceptions'])


@sd.logs_full_service.get(tags=[sd.jobs_tag], renderer='json',
                          schema=sd.FullLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.logs_short_service.get(tags=[sd.jobs_tag], renderer='json',
                           schema=sd.ShortLogsEndpoint(), response_schemas=sd.get_logs_responses)
def get_job_log(request):
    """
    Retrieve the result(s) of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job['log'])
