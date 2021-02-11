from typing import TYPE_CHECKING

from celery.utils.log import get_task_logger
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPOk, HTTPUnauthorized
from pyramid.request import Request
from pyramid.settings import asbool
from pyramid_celery import celery_app as app

from weaver import sort, status
from weaver.database import get_db
from weaver.datatype import Job
from weaver.exceptions import (
    InvalidIdentifierValue,
    JobNotFound,
    ProcessNotAccessible,
    ProcessNotFound,
    ServiceNotAccessible,
    ServiceNotFound,
    log_unhandled_exceptions
)
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import get_any_id, get_any_value, get_settings
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps.utils import get_wps_output_url
from weaver.wps_restapi import swagger_definitions as sd
from notify import encrypt_email
from weaver.wps_restapi.utils import OUTPUT_FORMAT_JSON

if TYPE_CHECKING:
    from typing import Optional, Tuple
    from weaver.typedefs import AnySettingsContainer, JSON

LOGGER = get_task_logger(__name__)


def get_job(request):
    # type: (Request) -> Job
    """
    Obtain a job from request parameters.

    :returns: Job information if found.
    :raise HTTPNotFound: with JSON body details on missing/non-matching job, process, provider IDs.
    """
    job_id = request.matchdict.get("job_id")
    store = get_db(request).get_store(StoreJobs)
    try:
        job = store.fetch_by_id(job_id)
    except JobNotFound:
        raise HTTPNotFound("Could not find job with specified 'job_id'.")

    provider_id = request.matchdict.get("provider_id", job.service)
    process_id = request.matchdict.get("process_id", job.process)

    if job.service != provider_id:
        raise HTTPNotFound("Could not find job with specified 'provider_id'.")
    if job.process != process_id:
        raise HTTPNotFound("Could not find job with specified 'process_id'.")
    return job


def validate_service_process(request):
    # type: (Request) -> Tuple[Optional[str], Optional[str]]
    """
    Verifies that service or process specified by path or query will raise the appropriate error if applicable.
    """
    service_name = request.matchdict.get("provider_id", None) or request.params.get("service", None)
    process_name = request.matchdict.get("process_id", None) or request.params.get("process", None)
    item_test = None
    item_type = None

    try:
        service = None
        if service_name:
            item_type = "Service"
            item_test = service_name
            store = get_db(request).get_store(StoreServices)
            service = store.fetch_by_name(service_name, visibility=VISIBILITY_PUBLIC)
        if process_name:
            item_type = "Process"
            item_test = process_name
            # local process
            if not service:
                store = get_db(request).get_store(StoreProcesses)
                store.fetch_by_id(process_name, visibility=VISIBILITY_PUBLIC)
            # remote process
            else:
                from weaver.wps_restapi.processes.processes import list_remote_processes
                processes = list_remote_processes(service, request)
                if process_name not in [p.id for p in processes]:
                    raise ProcessNotFound
    except (ServiceNotFound, ProcessNotFound):
        raise HTTPNotFound("{} of id '{}' cannot be found.".format(item_type, item_test))
    except (ServiceNotAccessible, ProcessNotAccessible):
        raise HTTPUnauthorized("{} of id '{}' is not accessible.".format(item_type, item_test))
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))

    return service_name, process_name


@sd.process_jobs_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.GetProcessJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_full_service.get(tags=[sd.TAG_JOBS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                          schema=sd.GetProviderJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_short_service.get(tags=[sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.GetJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetJobsResponse.description)
def get_queried_jobs(request):
    """
    Retrieve the list of jobs which can be filtered, sorted, paged and categorized using query parameters.
    """
    settings = get_settings(request)
    service, process = validate_service_process(request)
    detail = asbool(request.params.get("detail", False))
    page = int(request.params.get("page", "0"))
    limit = int(request.params.get("limit", "10"))
    email = request.params.get("notification_email", None)
    filters = {
        "page": page,
        "limit": limit,
        # split by comma and filter empty stings
        "tags": list(filter(lambda s: s, request.params.get("tags", "").split(","))),
        "access": request.params.get("access", None),
        "status": request.params.get("status", None),
        "sort": request.params.get("sort", sort.SORT_CREATED),
        "notification_email": encrypt_email(email, settings) if email else None,
        # service and process can be specified by query (short route) or by path (full route)
        "process": process,
        "service": service,
    }
    groups = request.params.get("groups", "")
    groups = groups.split(",") if groups else None
    store = get_db(request).get_store(StoreJobs)
    items, total = store.find_jobs(request=request, group_by=groups, **filters)
    body = {"total": total}

    def _job_list(jobs):
        return [j.json(settings) if detail else j.id for j in jobs]

    if groups:
        for grouped_jobs in items:
            grouped_jobs["jobs"] = _job_list(grouped_jobs["jobs"])
        body.update({"groups": items})
    else:
        body.update({"jobs": _job_list(items), "page": page, "limit": limit})
    body = sd.GetQueriedJobsSchema().deserialize(body)
    return HTTPOk(json=body)


@sd.job_full_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                         schema=sd.FullJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.job_short_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS], renderer=OUTPUT_FORMAT_JSON,
                          schema=sd.ShortJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.process_job_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS, sd.TAG_STATUS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.GetProcessJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetJobStatusResponse.description)
def get_job_status(request):
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job.json(request))


@sd.job_full_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.FullJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_short_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.ShortJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.process_job_service.delete(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OUTPUT_FORMAT_JSON,
                               schema=sd.DeleteProcessJobEndpoint(), response_schemas=sd.delete_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorDeleteJobResponse.description)
def cancel_job(request):
    """
    Dismiss a job.

    Note: Will only stop tracking this particular process (WPS 1.0 doesn't allow to stop a process)
    """
    job = get_job(request)
    app.control.revoke(job.task_id, terminate=True)
    store = get_db(request).get_store(StoreJobs)
    job.status_message = "Job dismissed."
    job.status = status.map_status(status.STATUS_DISMISSED)
    store.update_job(job)

    return HTTPOk(json={
        "jobID": job.id,
        "status": job.status,
        "message": job.status_message,
        "percentCompleted": job.progress,
    })


def get_results(job, container):
    # type: (Job, AnySettingsContainer) -> JSON
    """
    Obtains the results with extended full WPS output URL as applicable and according to configuration settings.
    """
    wps_url = get_wps_output_url(container)
    if not wps_url.endswith("/"):
        wps_url = wps_url + "/"
    outputs = []
    for result in job.results:
        rtype = "data" if any(k in result for k in ["data", "value"]) else "href"
        value = get_any_value(result)
        if rtype == "href" and "://" not in value:
            value = wps_url + str(value).lstrip("/")
        outputs.append({"id": get_any_id(result), rtype: value})
    return {"outputs": outputs}


@sd.results_full_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.FullResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.results_short_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.ShortResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.process_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetJobResultsResponse.description)
def get_job_results(request):
    """
    Retrieve the results of a job.
    """
    job = get_job(request)
    results = get_results(job, request)
    return HTTPOk(json=results)


@sd.exceptions_full_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.FullExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.exceptions_short_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.ShortExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.process_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.ProcessExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetJobExceptionsResponse.description)
def get_job_exceptions(request):
    """
    Retrieve the exceptions of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job.exceptions)


@sd.logs_full_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                          schema=sd.FullLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.logs_short_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.ShortLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.process_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.ProcessLogsEndpoint(), response_schemas=sd.get_logs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetJobLogsResponse.description)
def get_job_logs(request):
    """
    Retrieve the logs of a job.
    """
    job = get_job(request)
    return HTTPOk(json=job.logs)


# TODO: https://github.com/crim-ca/weaver/issues/18
# @sd.process_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
#                              schema=sd.ProcessOutputEndpoint(), response_schemas=sd.get_job_output_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetJobOutputResponse.description)
def get_job_output(request):
    pass
