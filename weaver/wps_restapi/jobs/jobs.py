from typing import TYPE_CHECKING

from celery.utils.log import get_task_logger
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPOk, HTTPPermanentRedirect, HTTPUnauthorized
from pyramid.request import Request
from pyramid.settings import asbool
from pyramid_celery import celery_app as app

from notify import encrypt_email
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
from weaver.formats import CONTENT_TYPE_TEXT_PLAIN, OUTPUT_FORMAT_JSON, get_format
from weaver.owsexceptions import OWSNotFound
from weaver.processes.convert import any2wps_literal_datatype
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import get_any_id, get_any_value, get_settings
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps.utils import get_wps_output_url
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import List, Optional, Tuple, Union
    from pyramid.httpexceptions import HTTPException
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
        raise OWSNotFound(code="NoSuchJob", locator="JobID", description="Could not find job with specified 'job_id'.")

    provider_id = request.matchdict.get("provider_id", job.service)
    process_id = request.matchdict.get("process_id", job.process)

    if job.service != provider_id:
        raise OWSNotFound(
            code="NoSuchProvider",
            locator="provider",
            description="Could not find job corresponding to specified 'provider_id'."
        )
    if job.process != process_id:
        raise OWSNotFound(
            code="NoSuchProcess",
            locator="process",
            description="Could not find job corresponding to specified 'process_id'."
        )
    return job


def get_results(job, container, value_key=None, ogc_api=False):
    # type: (Job, AnySettingsContainer, Optional[str], bool) -> Union[List[JSON], JSON]
    """
    Obtains the job results with extended full WPS output URL as applicable and according to configuration settings.

    :param job: job from which to retrieve results.
    :param container: any container giving access to instance settings (to resolve reference output location).
    :param value_key:
        If not specified, the returned values will have the appropriate ``data``/``href`` key according to the content.
        Otherwise, all values will have the specified key.
    :param ogc_api:
        If ``True``, formats the results using the ``OGC-API - Processes`` format.
    :returns: list of all outputs each with minimally an ID and value under the requested key.
    """
    wps_url = get_wps_output_url(container)
    if not wps_url.endswith("/"):
        wps_url = wps_url + "/"
    outputs = {} if ogc_api else []
    fmt_key = "mediaType" if ogc_api else "mimeType"
    for result in job.results:
        rtype = "data" if any(k in result for k in ["data", "value"]) else "href"
        value = get_any_value(result)
        out_id = get_any_id(result)
        out_key = rtype
        if rtype == "href":
            # fix paths relative to instance endpoint, but leave explicit links as is (eg: S3 bucket, remote HTTP, etc.)
            if value.startswith("/"):
                value = wps_url + str(value).lstrip("/")
        elif ogc_api:
            out_key = "value"
        elif value_key:
            out_key = value_key
        output = {out_key: value}
        if rtype == "href":  # required for the rest to be there, other fields optional
            if "mimeType" not in result:
                result["mimeType"] = get_format(value, default=CONTENT_TYPE_TEXT_PLAIN).mime_type
            output["format"] = {fmt_key: result["mimeType"]}
            for field in ["encoding", "schema"]:
                if field in result:
                    output["format"][field] = result[field]
        elif rtype != "href":
            # literal data
            # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
            dtype = result.get("dataType", any2wps_literal_datatype(value, is_value=True) or "string")
            if ogc_api:
                output["dataType"] = {"name": dtype}
            else:
                output["dataType"] = dtype

        if ogc_api:
            if out_id in outputs:
                output_list = outputs[out_id]
                if not isinstance(output_list, list):
                    output_list = [output_list]
                output_list.append(output)
                outputs[out_id] = output_list
            else:
                outputs[out_id] = output
        else:
            # if ordered insert supported by python version, insert ID first
            output = dict([("id", out_id)] + list(output.items()))  # noqa
            outputs.append(output)
    return outputs


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
        raise HTTPNotFound(json={
            "code": "NoSuch{}".format(item_type),
            "description": "{} of id '{}' cannot be found.".format(item_type, item_test)
        })
    except (ServiceNotAccessible, ProcessNotAccessible):
        raise HTTPUnauthorized(json={
            "code": "Unauthorized{}".format(item_type),
            "description": "{} of id '{}' is not accessible.".format(item_type, item_test)
        })
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(json={
            "code": InvalidIdentifierValue.__name__,
            "description": str(ex)
        })

    return service_name, process_name


@sd.process_jobs_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.GetProcessJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.provider_jobs_service.get(tags=[sd.TAG_JOBS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.GetProviderJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_service.get(tags=[sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                     schema=sd.GetJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_queried_jobs(request):
    """
    Retrieve the list of jobs which can be filtered, sorted, paged and categorized using query parameters.
    """
    settings = get_settings(request)
    service, process = validate_service_process(request)
    detail = asbool(request.params.get("detail", False))
    page = request.params.get("page", "0")
    page = int(page) if str.isnumeric(page) else 0
    limit = request.params.get("limit", "10")
    limit = int(limit) if str.isnumeric(limit) else 10
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


@sd.provider_job_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.ProviderJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.job_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS], renderer=OUTPUT_FORMAT_JSON,
                    schema=sd.JobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.process_job_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS, sd.TAG_STATUS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.GetProcessJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_status(request):
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    job_status = job.json(request, self_link="status")
    return HTTPOk(json=job_status)


@sd.provider_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProviderJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OUTPUT_FORMAT_JSON,
                       schema=sd.JobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.process_job_service.delete(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OUTPUT_FORMAT_JSON,
                               schema=sd.DeleteProcessJobEndpoint(), response_schemas=sd.delete_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
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


@sd.provider_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProviderInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@sd.process_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                               schema=sd.ProcessInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@sd.job_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.JobInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_inputs(request):
    # type: (Request) -> HTTPException
    """
    Retrieve the inputs of a job.
    """
    job = get_job(request)
    inputs = dict(inputs=[dict(id=get_any_id(_input), value=get_any_value(_input)) for _input in job.inputs])
    inputs.update(job.links(request, self_link="inputs"))
    inputs = sd.JobInputsSchema().deserialize(inputs)
    return HTTPOk(json=inputs)


@sd.provider_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.ProviderOutputsEndpoint(), response_schemas=sd.get_job_outputs_responses)
@sd.process_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessOutputsEndpoint(), response_schemas=sd.get_job_outputs_responses)
@sd.job_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.JobOutputsEndpoint(), response_schemas=sd.get_job_outputs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_outputs(request):
    # type: (Request) -> HTTPException
    """
    Retrieve the outputs of a job.
    """
    job = get_job(request)
    outputs = {"outputs": get_results(job, request)}
    outputs.update(job.links(request, self_link="outputs"))
    outputs = sd.JobOutputsSchema().deserialize(outputs)
    return HTTPOk(json=outputs)


@sd.provider_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.ProviderResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.process_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.job_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.JobResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_results(request):
    # type: (Request) -> HTTPException
    """
    Retrieve the results of a job.
    """
    job = get_job(request)
    job_status = status.map_status(job.status)
    if job_status in status.JOB_STATUS_CATEGORIES[status.STATUS_CATEGORY_RUNNING]:
        raise HTTPNotFound(json={
            "code": "ResultsNotReady",
            "description": "Job status is '{}'. Results are not yet available.".format(job_status)
        })
    results = get_results(job, request, value_key="value", ogc_api=True)
    results = sd.Result().deserialize(results)
    return HTTPOk(json=results)


@sd.provider_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROVIDERS],
                                    renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderExceptionsEndpoint(),
                                    response_schemas=sd.get_exceptions_responses)
@sd.job_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS], renderer=OUTPUT_FORMAT_JSON,
                               schema=sd.JobExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.process_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.ProcessExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_exceptions(request):
    """
    Retrieve the exceptions of a job.
    """
    job = get_job(request)
    exceptions = sd.JobExceptionsSchema().deserialize(job.exceptions)
    return HTTPOk(json=exceptions)


@sd.provider_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.ProviderLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.job_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS], renderer=OUTPUT_FORMAT_JSON,
                         schema=sd.JobLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.process_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.ProcessLogsEndpoint(), response_schemas=sd.get_logs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_logs(request):
    """
    Retrieve the logs of a job.
    """
    job = get_job(request)
    logs = sd.JobLogsSchema().deserialize(job.logs)
    return HTTPOk(json=logs)


@sd.provider_result_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS, sd.TAG_DEPRECATED],
                                renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderResultEndpoint(),
                                response_schemas=sd.get_result_redirect_responses)
@sd.process_result_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES, sd.TAG_DEPRECATED],
                               renderer=OUTPUT_FORMAT_JSON, schema=sd.ProcessResultEndpoint(),
                               response_schemas=sd.get_result_redirect_responses)
@sd.job_result_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_DEPRECATED],
                           renderer=OUTPUT_FORMAT_JSON, schema=sd.JobResultEndpoint(),
                           response_schemas=sd.get_result_redirect_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def redirect_job_result(request):
    """
    Deprecated job result endpoint that is now returned by corresponding outputs path with added links.
    """
    location = request.url.rsplit("/", 1)[0] + "/outputs"
    LOGGER.warning("Deprecated route redirection [%s] -> [%s]", request.url, location)
    return HTTPPermanentRedirect(comment="deprecated", location=location)
