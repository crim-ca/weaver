from typing import TYPE_CHECKING

from celery.utils.log import get_task_logger
from colander import Invalid
from pyramid.httpexceptions import HTTPBadRequest, HTTPOk, HTTPPermanentRedirect, HTTPUnprocessableEntity

from notify import encrypt_email
from weaver.database import get_db
from weaver.datatype import Job
from weaver.exceptions import JobNotFound, JobStatisticsNotFound, log_unhandled_exceptions
from weaver.formats import ContentType, OutputFormat, add_content_type_charset, guess_target_format, repr_json
from weaver.processes.convert import convert_input_values_schema, convert_output_params_schema
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory
from weaver.store.base import StoreJobs
from weaver.utils import get_settings
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs.utils import (
    dismiss_job_task,
    get_job,
    get_job_list_links,
    get_job_results_response,
    get_results,
    get_schema_query,
    raise_job_bad_status,
    raise_job_dismissed,
    validate_service_process
)
from weaver.wps_restapi.swagger_definitions import datetime_interval_parser

if TYPE_CHECKING:
    from typing import Iterable, List

    from weaver.typedefs import JSON, AnyResponseType, PyramidRequest

LOGGER = get_task_logger(__name__)


@sd.provider_jobs_service.get(tags=[sd.TAG_JOBS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                              schema=sd.GetProviderJobsEndpoint(), response_schemas=sd.get_prov_all_jobs_responses)
@sd.process_jobs_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS], renderer=OutputFormat.JSON,
                             schema=sd.GetProcessJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_service.get(tags=[sd.TAG_JOBS], renderer=OutputFormat.JSON,
                     schema=sd.GetJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_queried_jobs(request):
    # type: (PyramidRequest) -> HTTPOk
    """
    Retrieve the list of jobs which can be filtered, sorted, paged and categorized using query parameters.
    """

    settings = get_settings(request)
    params = dict(request.params)
    if params.get("datetime", False):
        # replace white space with '+' since request.params replaces '+' with whitespaces when parsing
        params["datetime"] = params["datetime"].replace(" ", "+")

    try:
        params = sd.GetJobsQueries().deserialize(params)
    except Invalid as ex:
        raise HTTPBadRequest(json={
            "code": "JobInvalidParameter",
            "description": "Job query parameters failed validation.",
            "error": Invalid.__name__,
            "cause": str(ex),
            "value": repr_json(ex.value or params, force_string=False),
        })

    service, process = validate_service_process(request)
    LOGGER.debug("Job search queries (raw):\n%s", repr_json(params, indent=2))
    for param_name in ["process", "processID", "provider", "service"]:
        params.pop(param_name, None)
    filters = {**params, "process": process, "service": service}

    detail = filters.pop("detail", False)
    groups = filters.pop("groups", "").split(",") if filters.get("groups", False) else filters.pop("groups", None)

    filters["status"] = filters["status"].split(",") if "status" in filters else None
    filters["tags"] = list(filter(lambda s: s, filters["tags"].split(",") if filters.get("tags", False) else ""))
    filters["notification_email"] = (
        encrypt_email(filters["notification_email"], settings)
        if filters.get("notification_email", False) else None
    )
    filters["min_duration"] = filters.pop("minDuration", None)
    filters["max_duration"] = filters.pop("maxDuration", None)
    filters["job_type"] = filters.pop("type", None)

    dti = datetime_interval_parser(params["datetime"]) if params.get("datetime", False) else None
    if dti and dti.get("before", False) and dti.get("after", False) and dti["after"] > dti["before"]:
        raise HTTPUnprocessableEntity(json={
            "code": "InvalidDateFormat",
            "description": "Datetime at the start of the interval must be less than the datetime at the end."
        })
    filters["datetime_interval"] = dti
    LOGGER.debug("Job search queries (processed):\n%s", repr_json(filters, indent=2))

    store = get_db(request).get_store(StoreJobs)
    items, total = store.find_jobs(request=request, group_by=groups, **filters)
    body = {"total": total}

    def _job_list(jobs):  # type: (Iterable[Job]) -> List[JSON]
        return [j.json(settings) if detail else j.id for j in jobs]

    paging = {}
    if groups:
        for grouped_jobs in items:
            grouped_jobs["jobs"] = _job_list(grouped_jobs["jobs"])
        body.update({"groups": items})
    else:
        paging = {"page": filters["page"], "limit": filters["limit"]}
        body.update({"jobs": _job_list(items), **paging})
    try:
        body.update({"links": get_job_list_links(total, filters, request)})
    except IndexError as exc:
        raise HTTPBadRequest(json={
            "code": "JobInvalidParameter",
            "description": str(exc),
            "cause": "Invalid paging parameters.",
            "error": type(exc).__name__,
            "value": repr_json(paging, force_string=False)
        })
    body = sd.GetQueriedJobsSchema().deserialize(body)
    return HTTPOk(json=body)


@sd.provider_job_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                             schema=sd.ProviderJobEndpoint(), response_schemas=sd.get_prov_single_job_status_responses)
@sd.process_job_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS, sd.TAG_STATUS], renderer=OutputFormat.JSON,
                            schema=sd.GetProcessJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.job_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS], renderer=OutputFormat.JSON,
                    schema=sd.JobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_status(request):
    # type: (PyramidRequest) -> HTTPOk
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    job_status = job.json(request, self_link="status")
    return HTTPOk(json=job_status)


@sd.provider_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                schema=sd.ProviderJobEndpoint(), response_schemas=sd.delete_prov_job_responses)
@sd.process_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.DeleteProcessJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OutputFormat.JSON,
                       schema=sd.JobEndpoint(), response_schemas=sd.delete_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def cancel_job(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Dismiss a planned or running job execution, or remove result artifacts of a completed job.

    Note:
        Will only stop tracking this particular process execution when not supported by underlying provider
        services such as WPS 1.0. Services supporting cancel operation could attempt to terminate remote jobs.
    """
    job = get_job(request)
    job = dismiss_job_task(job, request)
    return HTTPOk(json={
        "jobID": str(job.id),
        "status": job.status,
        "message": job.status_message,
        "percentCompleted": job.progress,
    })


@sd.provider_jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                 schema=sd.DeleteProviderJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@sd.process_jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                schema=sd.DeleteProcessJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@sd.jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OutputFormat.JSON,
                        schema=sd.DeleteJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def cancel_job_batch(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Dismiss operation for multiple jobs.

    Note:
        Will only stop tracking jobs when underlying remote provider services do not support cancel operation.
    """
    try:
        body = sd.DeleteJobsBodySchema().deserialize(request.json)
        jobs = body["jobs"]
    except Invalid as exc:
        raise HTTPUnprocessableEntity(json={"code": Invalid.__name__, "description": str(exc)})
    except Exception as exc:
        raise HTTPBadRequest(json={"code": "Could not parse request body.", "description": str(exc)})

    store = get_db(request).get_store(StoreJobs)
    found_jobs = []
    for job_id in jobs:
        try:
            job = store.fetch_by_id(job_id)
        except JobNotFound as exc:
            LOGGER.debug("Job [%s] not found, cannot be dismissed: [%s]", job_id, exc)
            continue
        found_jobs.append(job.id)
        try:
            dismiss_job_task(job, request)
        except JobNotFound as exc:
            LOGGER.debug("Job [%s] cannot be dismissed: %s.", job_id, exc.description)

    body["description"] = "Following jobs have been successfully dismissed."
    body = sd.BatchDismissJobsBodySchema().deserialize({"jobs": found_jobs})
    return HTTPOk(json=body)


@sd.provider_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                schema=sd.ProviderInputsEndpoint(), response_schemas=sd.get_prov_inputs_responses)
@sd.process_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.ProcessInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@sd.job_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS], renderer=OutputFormat.JSON,
                           schema=sd.JobInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_inputs(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the inputs values and outputs definitions of a job.
    """
    job = get_job(request)
    schema = get_schema_query(request.params.get("schema"), strict=False)
    job_inputs = job.inputs
    job_outputs = job.outputs
    if schema:
        job_inputs = convert_input_values_schema(job_inputs, schema)
        job_outputs = convert_output_params_schema(job_outputs, schema)
    body = {"inputs": job_inputs, "outputs": job_outputs}
    body.update({"links": job.links(request, self_link="inputs")})
    body = sd.JobInputsBody().deserialize(body)
    return HTTPOk(json=body)


@sd.provider_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                 schema=sd.ProviderOutputsEndpoint(), response_schemas=sd.get_prov_outputs_responses)
@sd.process_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                schema=sd.ProcessOutputsEndpoint(), response_schemas=sd.get_job_outputs_responses)
@sd.job_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                            schema=sd.JobOutputsEndpoint(), response_schemas=sd.get_job_outputs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_outputs(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the output values resulting from a job execution.
    """
    job = get_job(request)
    raise_job_dismissed(job, request)
    raise_job_bad_status(job, request)
    schema = get_schema_query(request.params.get("schema"))
    results, _ = get_results(job, request, schema=schema, link_references=False)
    outputs = {"outputs": results}
    outputs.update({"links": job.links(request, self_link="outputs")})
    outputs = sd.JobOutputsBody().deserialize(outputs)
    return HTTPOk(json=outputs)


@sd.provider_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                 schema=sd.ProviderResultsEndpoint(), response_schemas=sd.get_prov_results_responses)
@sd.process_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                schema=sd.ProcessResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@sd.job_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS], renderer=OutputFormat.JSON,
                            schema=sd.JobResultsEndpoint(), response_schemas=sd.get_job_results_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_results(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the results of a job.
    """
    job = get_job(request)
    resp = get_job_results_response(job, request)
    return resp


@sd.provider_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROVIDERS],
                                    renderer=OutputFormat.JSON, schema=sd.ProviderExceptionsEndpoint(),
                                    response_schemas=sd.get_prov_exceptions_responses)
@sd.process_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                   schema=sd.ProcessExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.job_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS], renderer=OutputFormat.JSON,
                               schema=sd.JobExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_exceptions(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the exceptions of a job.
    """
    job = get_job(request)
    raise_job_dismissed(job, request)
    exceptions = sd.JobExceptionsSchema().deserialize(job.exceptions)
    return HTTPOk(json=exceptions)


@sd.provider_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                              schema=sd.ProviderLogsEndpoint(), response_schemas=sd.get_prov_logs_responses)
@sd.process_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                             schema=sd.ProcessLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.job_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS], renderer=OutputFormat.JSON,
                         schema=sd.JobLogsEndpoint(), response_schemas=sd.get_logs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_logs(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the logs of a job.
    """
    job = get_job(request)
    raise_job_dismissed(job, request)
    logs = sd.JobLogsSchema().deserialize(job.logs)
    ctype = guess_target_format(request)
    if ctype == ContentType.TEXT_PLAIN:
        ctype = add_content_type_charset(ctype, charset="UTF-8")
        return HTTPOk(body="\n".join(logs), content_type=ctype)
    if ctype in set(ContentType.ANY_XML) | {ContentType.APP_YAML}:
        data = OutputFormat.convert(logs, ctype, item_root="logs")
        ctype = add_content_type_charset(ctype, charset="UTF-8")
        return HTTPOk(body=data, content_type=ctype)
    return HTTPOk(json=logs)


@sd.provider_stats_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATISTICS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                               schema=sd.ProviderJobStatisticsEndpoint(), response_schemas=sd.get_prov_stats_responses)
@sd.process_stats_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATISTICS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                              schema=sd.ProcessJobStatisticsEndpoint(), response_schemas=sd.get_stats_responses)
@sd.job_stats_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATISTICS], renderer=OutputFormat.JSON,
                          schema=sd.JobStatisticsEndpoint(), response_schemas=sd.get_stats_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_stats(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the statistics of a job.
    """
    job = get_job(request)
    raise_job_dismissed(job, request)
    if job.status not in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED] or job.status != Status.SUCCEEDED:
        raise JobStatisticsNotFound(json={
            "title": "NoJobStatistics",
            "type": "no-job-statistics",  # unofficial
            "detail": "Job statistics are only available for completed and successful jobs.",
            "status": JobStatisticsNotFound.code,
            "cause": {"status": job.status},
        })
    stats = job.statistics
    if not stats:  # backward compatibility for existing jobs before feature was added
        raise JobStatisticsNotFound(json={
            "title": "NoJobStatistics",
            "type": "no-job-statistics",  # unofficial
            "detail": "Job statistics were not collected for this execution.",
            "status": JobStatisticsNotFound.code,
            "cause": "Empty statistics."
        })
    body = sd.JobStatisticsSchema().deserialize(stats)
    return HTTPOk(json=body)


@sd.provider_result_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS, sd.TAG_DEPRECATED],
                                renderer=OutputFormat.JSON, schema=sd.ProviderResultEndpoint(),
                                response_schemas=sd.get_result_redirect_responses)
@sd.process_result_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES, sd.TAG_DEPRECATED],
                               renderer=OutputFormat.JSON, schema=sd.ProcessResultEndpoint(),
                               response_schemas=sd.get_result_redirect_responses)
@sd.job_result_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_DEPRECATED],
                           renderer=OutputFormat.JSON, schema=sd.JobResultEndpoint(),
                           response_schemas=sd.get_result_redirect_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def redirect_job_result(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Deprecated job result endpoint that is now returned by corresponding outputs path with added links.
    """
    location = request.url.rsplit("/", 1)[0] + "/outputs"
    LOGGER.warning("Deprecated route redirection [%s] -> [%s]", request.url, location)
    return HTTPPermanentRedirect(comment="deprecated", location=location)
