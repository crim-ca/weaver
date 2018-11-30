from pyramid.httpexceptions import *
from pyramid.settings import asbool
from pyramid.request import Request
from pyramid_celery import celery_app as app
from twitcher.adapter import servicestore_factory, processstore_factory, jobstore_factory
from twitcher.exceptions import (
    InvalidIdentifierValue,
    ServiceNotFound,
    ProcessNotAccessible,
    ProcessNotFound,
    JobNotFound,
)
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.utils import wps_restapi_base_url
from twitcher.visibility import VISIBILITY_PUBLIC
from twitcher import status, sort
from typing import AnyStr, Optional, Union, Tuple
from owslib.wps import WPSExecution
from lxml import etree
from celery.utils.log import get_task_logger
import requests
from requests_file import FileAdapter

logger = get_task_logger(__name__)


def job_url(request, job):
    base_job_url = wps_restapi_base_url(request.registry.settings)
    if job.service is not None:
        base_job_url += '/providers/{provider_id}'.format(provider_id=job.service)
    return '{base_job_url}/processes/{process_id}/jobs/{job_id}'.format(
        base_job_url=base_job_url,
        process_id=job.process,
        job_id=job.id)


def job_format_json(request, job):
    job_json = {
        "jobID": job.id,
        "status": job.status,
        "message": job.status_message,
        "duration": job.duration,
        "percentCompleted": job.progress,
    }
    if job.status in status.job_status_categories[status.STATUS_CATEGORY_FINISHED]:
        job_status = status.map_status(job.status)
        if job_status == status.STATUS_SUCCEEDED:
            resource_type = 'result'
        else:
            resource_type = 'exceptions'
        job_json[resource_type] = '{job_url}/{res}'.format(job_url=job_url(request, job), res=resource_type.lower())

    job_json['logs'] = '{job_url}/logs'.format(job_url=job_url(request, job))
    return job_json


def check_status(url=None, response=None, sleep_secs=2, verify=False):
    # type: (Optional[AnyStr, None], Optional[etree.ElementBase], Optional[int], Optional[bool]) -> WPSExecution
    """
    Run owslib.wps check_status with additional exception handling.

    :param url: job URL where to look for job status.
    :param response: WPS response document of job status.
    :param sleep_secs: number of seconds to sleep before returning control to the caller.
    :param verify: Flag to enable SSL verification.
    :return: OWSLib.wps.WPSExecution object.
    """
    execution = WPSExecution()
    if response:
        logger.debug("using response document ...")
        xml = response
    elif url:
        logger.debug('using status_location url ...')
        request_session = requests.Session()
        request_session.mount('file://', FileAdapter())
        xml = request_session.get(url, verify=verify).content
    else:
        raise Exception("you need to provide a status-location url or response object.")
    if type(xml) is unicode:
        xml = xml.encode('utf8', errors='ignore')
    execution.checkStatus(response=xml, sleepSecs=sleep_secs)
    if execution.response is None:
        raise Exception("check_status failed!")
    # TODO: workaround for owslib type change of response
    # noinspection PyProtectedMember
    if not isinstance(execution.response, etree._Element):
        execution.response = etree.fromstring(execution.response)
    return execution


def get_job(request):
    """
    :returns: Job information if found.
    :raises: HTTPNotFound with JSON body details on missing/non-matching job, process, provider IDs.
    """
    job_id = request.matchdict.get('job_id')
    store = jobstore_factory(request.registry)
    try:
        job = store.fetch_by_id(job_id, request=request)
    except JobNotFound:
        raise HTTPNotFound('Could not find job with specified `job_id`.')

    provider_id = request.matchdict.get('provider_id', job.service)
    process_id = request.matchdict.get('process_id', job.process)

    if job.service != provider_id:
        raise HTTPNotFound('Could not find job with specified `provider_id`.')
    if job.process != process_id:
        raise HTTPNotFound('Could not find job with specified `process_id`.')
    return job


def validate_service_process(request):
    # type: (Request) -> Tuple[Union[None, AnyStr], Union[None, AnyStr]]
    """
    Verifies that service or process specified by path will raise the appropriate error if applicable.
    """
    path_service = request.matchdict.get('provider_id', None)
    path_process = request.matchdict.get('process_id', None)
    path_type = None
    path_test = None

    try:
        if path_service:
            path_type = 'Service'
            path_test = path_service
            store = servicestore_factory(request.registry)
            store.fetch_by_name(path_service, request=request)
        if path_process:
            path_type = 'Process'
            path_test = path_process
            store = processstore_factory(request.registry)
            store.fetch_by_id(path_process, visibility=VISIBILITY_PUBLIC, request=request)
    except (ServiceNotFound, ProcessNotFound):
        raise HTTPNotFound("{} of id `{}` cannot be found.".format(path_type, path_test))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("{} of id `{}` is not accessible.".format(path_type, path_test))
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(ex.message)

    return path_service, path_process


@sd.process_jobs_service.get(tags=[sd.processes_tag, sd.jobs_tag], renderer='json',
                             schema=sd.GetProcessJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_full_service.get(tags=[sd.jobs_tag, sd.providers_tag], renderer='json',
                          schema=sd.GetJobsRequest(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_short_service.get(tags=[sd.jobs_tag], renderer='json',
                           schema=sd.GetJobsRequest(), response_schemas=sd.get_all_jobs_responses)
def get_jobs(request):
    """
    Retrieve the list of jobs which can be filtered/sorted using queries.
    """
    path_service, path_process = validate_service_process(request)
    detail = asbool(request.params.get('detail', False))
    page = int(request.params.get('page', '0'))
    limit = int(request.params.get('limit', '10'))
    filters = {
        'page': page,
        'limit': limit,
        # split by comma and filter empty stings
        'tags': filter(lambda s: s, request.params.get('tags', '').split(',')),
        'access': request.params.get('access', None),
        'status': request.params.get('status', None),
        'sort': request.params.get('sort', sort.SORT_CREATED),
        # service and process can be specified by query (short route) or by path (full route)
        'process': path_process or request.params.get('process', None),
        'service': path_service or request.params.get('provider', None),
    }
    store = jobstore_factory(request.registry)
    items, count = store.find_jobs(request, **filters)
    return HTTPOk(json={
        'count': count,
        'page': page,
        'limit': limit,
        'jobs': [job_format_json(request, job) if detail else job.id for job in items]
    })


@sd.job_full_service.get(tags=[sd.jobs_tag, sd.status_tag, sd.providers_tag], renderer='json',
                         schema=sd.FullJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.job_short_service.get(tags=[sd.jobs_tag, sd.status_tag], renderer='json',
                          schema=sd.ShortJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.process_job_service.get(tags=[sd.processes_tag, sd.jobs_tag, sd.status_tag], renderer='json',
                            schema=sd.GetProcessJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
def get_job_status(request):
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    response = job_format_json(request, job)
    return HTTPOk(json=response)


@sd.job_full_service.delete(tags=[sd.jobs_tag, sd.dismiss_tag, sd.providers_tag], renderer='json',
                            schema=sd.FullJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_short_service.delete(tags=[sd.jobs_tag, sd.dismiss_tag], renderer='json',
                             schema=sd.ShortJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.process_job_service.delete(tags=[sd.processes_tag, sd.jobs_tag, sd.dismiss_tag], renderer='json',
                               schema=sd.DeleteProcessJobEndpoint(), response_schemas=sd.delete_job_responses)
def cancel_job(request):
    """
    Dismiss a job.
    Note: Will only stop tracking this particular process (WPS 1.0 doesn't allow to stop a process)
    """
    job = get_job(request)
    app.control.revoke(job.task_id, terminate=True)
    store = jobstore_factory(request.registry)
    job.status_message = 'Job dismissed.'
    job.status = status.map_status(status.STATUS_DISMISSED)
    store.update_job(job)

    return HTTPOk(json={
        'jobID': job.id,
        'status': job.status,
        'message': job.status_message,
        'percentCompleted': job.progress,
    })


@sd.results_full_service.get(tags=[sd.jobs_tag, sd.results_tag, sd.providers_tag], renderer='json',
                             schema=sd.FullResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.results_short_service.get(tags=[sd.jobs_tag, sd.results_tag], renderer='json',
                              schema=sd.ShortResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.process_results_service.get(tags=[sd.jobs_tag, sd.results_tag, sd.processes_tag], renderer='json',
                                schema=sd.ProcessResultsEndpoint(), response_schemas=sd.get_job_results_responses)
def get_job_results(request):
    """
    Retrieve the results of a job.
    """
    job = get_job(request)
    results = dict(outputs=[dict(id=result['identifier'], href=result['reference']) for result in job.results])
    return HTTPOk(json=results)


@sd.exceptions_full_service.get(tags=[sd.jobs_tag, sd.exceptions_tag, sd.providers_tag], renderer='json',
                                schema=sd.FullExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.exceptions_short_service.get(tags=[sd.jobs_tag, sd.exceptions_tag], renderer='json',
                                 schema=sd.ShortExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.process_exceptions_service.get(tags=[sd.jobs_tag, sd.exceptions_tag, sd.processes_tag], renderer='json',
                                   schema=sd.ProcessExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
def get_job_exceptions(request):
    """
    Retrieve the exceptions of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job.exceptions)


@sd.logs_full_service.get(tags=[sd.jobs_tag, sd.logs_tag, sd.providers_tag], renderer='json',
                          schema=sd.FullLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.logs_short_service.get(tags=[sd.jobs_tag, sd.logs_tag], renderer='json',
                           schema=sd.ShortLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.process_logs_service.get(tags=[sd.jobs_tag, sd.logs_tag, sd.processes_tag], renderer='json',
                             schema=sd.ProcessLogsEndpoint(), response_schemas=sd.get_logs_responses)
def get_job_logs(request):
    """
    Retrieve the logs of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job.logs)
