import math
import os
import shutil
from copy import deepcopy
from typing import TYPE_CHECKING

from celery.utils.log import get_task_logger
from colander import Invalid
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPOk,
    HTTPPermanentRedirect,
    HTTPUnauthorized,
    HTTPUnprocessableEntity
)
from pyramid.request import Request
from pyramid_celery import celery_app

from notify import encrypt_email
from weaver import status
from weaver.database import get_db
from weaver.datatype import Job
from weaver.exceptions import (
    InvalidIdentifierValue,
    JobGone,
    JobInvalidParameter,
    JobNotFound,
    ProcessNotAccessible,
    ProcessNotFound,
    ServiceNotAccessible,
    ServiceNotFound,
    log_unhandled_exceptions
)
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_PLAIN, OUTPUT_FORMAT_JSON, get_format
from weaver.owsexceptions import OWSNotFound
from weaver.processes.convert import any2wps_literal_datatype
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import get_any_id, get_any_value, get_path_kvp, get_settings, get_weaver_url, is_uuid, repr_json
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.providers.utils import forbid_local_only
from weaver.wps_restapi.swagger_definitions import datetime_interval_parser

if TYPE_CHECKING:
    from typing import Dict, List, Optional, Tuple, Union
    from pyramid.httpexceptions import HTTPException
    from weaver.typedefs import AnySettingsContainer, AnyValueType, JSON

LOGGER = get_task_logger(__name__)


def get_job(request):
    # type: (Request) -> Job
    """
    Obtain a job from request parameters.

    :returns: Job information if found.
    :raise HTTPNotFound: with JSON body details on missing/non-matching job, process, provider IDs.
    """
    job_id = request.matchdict.get("job_id")
    try:
        if not is_uuid(job_id):
            raise JobInvalidParameter
        store = get_db(request).get_store(StoreJobs)
        job = store.fetch_by_id(job_id)
    except (JobInvalidParameter, JobNotFound) as exc:
        exception = type(exc)
        if exception is JobInvalidParameter:
            desc = "Invalid job reference is not a valid UUID."
        else:
            desc = "Could not find job with specified reference."
        title = "NoSuchJob"
        raise exception(
            # new format: https://docs.ogc.org/DRAFTS/18-062.html#_error_situations_7
            json={
                "title": title,
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-job",
                "detail": desc,
                "status": exception.code,
                "cause": str(job_id)
            },
            code=title, locator="JobID", description=desc  # old format
        )

    provider_id = request.matchdict.get("provider_id", job.service)
    process_id = request.matchdict.get("process_id", job.process)
    if provider_id:
        forbid_local_only(request)

    if job.service != provider_id:
        title = "NoSuchProvider"
        desc = "Could not find job reference corresponding to specified provider reference."
        raise OWSNotFound(
            # new format: https://docs.ogc.org/DRAFTS/18-062.html#_error_situations_5
            json={
                "title": title,
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-job",
                "detail": desc,
                "status": OWSNotFound.code,
                "cause": str(process_id)
            },
            code=title, locator="provider", description=desc  # old format
        )
    if job.process != process_id:
        title = "NoSuchProcess"
        desc = "Could not find job reference corresponding to specified process reference."
        raise OWSNotFound(
            # new format: https://docs.ogc.org/DRAFTS/18-062.html#_error_situations_5
            json={
                "title": title,
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-job",
                "detail": desc,
                "status": OWSNotFound.code,
                "cause": str(process_id)
            },
            code=title, locator="process", description=desc  # old format
        )
    return job


def get_job_list_links(job_total, filters, request):
    # type: (int, Dict[str, AnyValueType], Request) -> List[JSON]
    """
    Obtains a list of all relevant links for the corresponding job listing defined by query parameter filters.

    :raises IndexError: if the paging values are out of bounds compared to available total :term:`Job` matching search.
    """
    base_url = get_weaver_url(request)

    # reapply queries that must be given to obtain the same result in case of subsequent requests (sort, limits, etc.)
    kvp_params = {param: value for param, value in request.params.items() if param != "page"}
    # patch datetime that have some extra character manipulation (reapply '+' auto-converted to ' ' by params parser)
    if "datetime" in kvp_params:
        kvp_params["datetime"] = kvp_params["datetime"].replace(" ", "+")
    alt_kvp = deepcopy(kvp_params)

    # request job uses general endpoint, obtain the full path if any service/process was given as alternate location
    if request.path.startswith(sd.jobs_service.path):
        job_path = base_url + sd.jobs_service.path
        alt_path = None
        parent_url = None
        # cannot generate full path apply for 'service' by itself
        if filters["process"] and filters["service"]:
            alt_path = base_url + sd.provider_jobs_service.path.format(
                provider_id=filters["service"], process_id=filters["process"]
            )
            parent_url = alt_path.rsplit("/", 1)[0]
        elif filters["process"]:
            alt_path = base_url + sd.process_jobs_service.path.format(process_id=filters["process"])
            parent_url = alt_path.rsplit("/", 1)[0]
        for param in ["service", "provider", "process"]:
            alt_kvp.pop(param, None)
    # path is whichever specific service/process endpoint, jobs are pre-filtered by them
    # transform sub-endpoints into matching query parameters and use generic path as alternate location
    else:
        job_path = base_url + request.path
        alt_path = base_url + sd.jobs_service.path
        alt_kvp["process"] = filters["process"]
        if filters["service"]:
            alt_kvp["provider"] = filters["service"]
        parent_url = job_path.rsplit("/", 1)[0]

    cur_page = filters["page"]
    per_page = filters["limit"]
    max_page = max(math.ceil(job_total / per_page) - 1, 0)
    if cur_page < 0 or cur_page > max_page:
        raise IndexError(f"Page index {cur_page} is out of range from [0,{max_page}].")

    alt_links = []
    if alt_path:
        alt_links = [{
            "href": get_path_kvp(alt_path, page=cur_page, **alt_kvp), "rel": "alternate",
            "type": CONTENT_TYPE_APP_JSON, "title": "Alternate endpoint with equivalent set of filtered jobs."
        }]

    links = alt_links + [
        {"href": job_path, "rel": "collection",
         "type": CONTENT_TYPE_APP_JSON, "title": "Complete job listing (no filtering queries applied)."},
        {"href": base_url + sd.jobs_service.path, "rel": "search",
         "type": CONTENT_TYPE_APP_JSON, "title": "Generic query endpoint to search for jobs."},
        {"href": job_path + "?detail=false", "rel": "preview",
         "type": CONTENT_TYPE_APP_JSON, "title": "Job listing summary (UUID and count only)."},
        {"href": job_path, "rel": "http://www.opengis.net/def/rel/ogc/1.0/job-list",
         "type": CONTENT_TYPE_APP_JSON, "title": "List of registered jobs."},
        {"href": get_path_kvp(job_path, page=cur_page, **kvp_params), "rel": "current",
         "type": CONTENT_TYPE_APP_JSON, "title": "Current page of job query listing."},
        {"href": get_path_kvp(job_path, page=0, **kvp_params), "rel": "first",
         "type": CONTENT_TYPE_APP_JSON, "title": "First page of job query listing."},
        {"href": get_path_kvp(job_path, page=max_page, **kvp_params), "rel": "last",
         "type": CONTENT_TYPE_APP_JSON, "title": "Last page of job query listing."},
    ]
    if cur_page > 0:
        links.append({
            "href": get_path_kvp(job_path, page=cur_page - 1, **kvp_params), "rel": "prev",
            "type": CONTENT_TYPE_APP_JSON, "title": "Previous page of job query listing."
        })
    if cur_page < max_page:
        links.append({
            "href": get_path_kvp(job_path, page=cur_page + 1, **kvp_params), "rel": "next",
            "type": CONTENT_TYPE_APP_JSON, "title": "Next page of job query listing."
        })
    if parent_url:
        links.append({
            "href": parent_url, "rel": "up",
            "type": CONTENT_TYPE_APP_JSON, "title": "Parent collection for which listed jobs apply."
        })
    return links


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
        If ``True``, formats the results using the ``OGC API - Processes`` format.
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
                value = str(value).lstrip("/")
            if "://" not in value:
                value = wps_url + value
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
    service_name = (
        request.matchdict.get("provider_id", None) or
        request.params.get("provider", None) or
        request.params.get("service", None)  # backward compatibility
    )
    process_name = (
        request.matchdict.get("process_id", None) or
        request.params.get("process", None) or
        request.params.get("processID", None)  # OGC-API conformance
    )
    item_test = None
    item_type = None

    try:
        service = None
        if service_name:
            forbid_local_only(request)
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
                processes = service.processes(request)
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


@sd.provider_jobs_service.get(tags=[sd.TAG_JOBS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.GetProviderJobsEndpoint(), response_schemas=sd.get_prov_all_jobs_responses)
@sd.process_jobs_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.GetProcessJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_service.get(tags=[sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                     schema=sd.GetJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_queried_jobs(request):
    """
    Retrieve the list of jobs which can be filtered, sorted, paged and categorized using query parameters.
    """

    settings = get_settings(request)
    service, process = validate_service_process(request)

    params = dict(request.params)
    LOGGER.debug("Job search queries (raw):\n%s", repr_json(params, indent=2))
    for param_name in ["process", "processID", "provider", "service"]:
        params.pop(param_name, None)
    filters = {**params, "process": process, "provider": service}

    if params.get("datetime", False):
        # replace white space with '+' since request.params replaces '+' with whitespaces when parsing
        filters["datetime"] = params["datetime"].replace(" ", "+")

    try:
        filters = sd.GetJobsQueries().deserialize(filters)
    except Invalid as ex:
        raise HTTPBadRequest(json={
            "code": "JobInvalidParameter",
            "description": "Job query parameters failed validation.",
            "error": Invalid.__name__,
            "cause": str(ex),
            "value": repr_json(ex.value or filters, force_string=False),
        })

    detail = filters.pop("detail", False)
    groups = filters.pop("groups", "").split(",") if filters.get("groups", False) else filters.pop("groups", None)

    filters["tags"] = list(filter(lambda s: s, filters["tags"].split(",") if filters.get("tags", False) else ""))
    filters["notification_email"] = (
        encrypt_email(filters["notification_email"], settings)
        if filters.get("notification_email", False) else None
    )
    filters["service"] = filters.pop("provider", None)
    filters["min_duration"] = filters.pop("minDuration", None)
    filters["max_duration"] = filters.pop("maxDuration", None)
    filters["job_type"] = filters.pop("type", None)

    dti = datetime_interval_parser(filters["datetime"]) if filters.get("datetime", False) else None
    if dti and dti.get("before", False) and dti.get("after", False) and dti["after"] > dti["before"]:
        raise HTTPUnprocessableEntity(json={
            "code": "InvalidDateFormat",
            "description": "Datetime at the start of the interval must be less than the datetime at the end."
        })
    filters.pop("datetime", None)
    filters["datetime_interval"] = dti
    LOGGER.debug("Job search queries (processed):\n%s", repr_json(filters, indent=2))

    store = get_db(request).get_store(StoreJobs)
    items, total = store.find_jobs(request=request, group_by=groups, **filters)
    body = {"total": total}

    def _job_list(jobs):
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


@sd.provider_job_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.ProviderJobEndpoint(), response_schemas=sd.get_prov_single_job_status_responses)
@sd.process_job_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS, sd.TAG_STATUS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.GetProcessJobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@sd.job_service.get(tags=[sd.TAG_JOBS, sd.TAG_STATUS], renderer=OUTPUT_FORMAT_JSON,
                    schema=sd.JobEndpoint(), response_schemas=sd.get_single_job_status_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_status(request):
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    job_status = job.json(request, self_link="status")
    return HTTPOk(json=job_status)


def raise_job_dismissed(job, container=None):
    # type: (Job, Optional[AnySettingsContainer]) -> None
    """
    Raise the appropriate messages for dismissed job status.
    """
    if job.status == status.STATUS_DISMISSED:
        # provide the job status links since it is still available for reference
        settings = get_settings(container)
        job_links = job.links(settings)
        job_links = [link for link in job_links if link["rel"] in ["status", "alternate", "collection", "up"]]
        raise JobGone(
            json={
                "code": "JobDismissed",
                "description": "Job was dismissed and artifacts have been removed.",
                "value": job.id,
                "links": job_links
            }
        )


def dismiss_job_task(job, container):
    # type: (Job, AnySettingsContainer) -> Job
    """
    Cancels any pending or running :mod:`Celery` task and removes completed job artifacts.

    :param job: job to cancel or cleanup.
    :param container:
    :return:
    """
    raise_job_dismissed(job, container)
    if job.status in status.JOB_STATUS_CATEGORIES[status.JOB_STATUS_CATEGORY_RUNNING]:
        # signal to stop celery task. Up to it to terminate remote if any.
        LOGGER.debug("Job [%s] dismiss operation: Canceling task [%s]", job.id, job.task_id)
        celery_app.control.revoke(job.task_id, terminate=True)

    wps_out_dir = get_wps_output_dir(container)
    job_out_dir = os.path.join(wps_out_dir, str(job.id))
    job_out_log = os.path.join(wps_out_dir, str(job.id) + ".log")
    job_out_xml = os.path.join(wps_out_dir, str(job.id) + ".xml")
    if os.path.isdir(job_out_dir):
        LOGGER.debug("Job [%s] dismiss operation: Removing output results.", job.id)
        shutil.rmtree(job_out_dir, onerror=lambda func, path, _exc: LOGGER.warning(
            "Job [%s] dismiss operation: Failed to delete [%s] due to [%s]", job.id, job_out_dir, _exc
        ))
    if os.path.isfile(job_out_log):
        LOGGER.debug("Job [%s] dismiss operation: Removing output logs.", job.id)
        try:
            os.remove(job_out_log)
        except OSError as exc:
            LOGGER.warning("Job [%s] dismiss operation: Failed to delete [%s] due to [%s]", job.id, job_out_log, exc)
    if os.path.isfile(job_out_xml):
        LOGGER.debug("Job [%s] dismiss operation: Removing output WPS status.", job.id)
        try:
            os.remove(job_out_xml)
        except OSError as exc:
            LOGGER.warning("Job [%s] dismiss operation: Failed to delete [%s] due to [%s]", job.id, job_out_xml, exc)

    LOGGER.debug("Job [%s] dismiss operation: Updating job status.")
    store = get_db(container).get_store(StoreJobs)
    job.status_message = "Job {}.".format(status.STATUS_DISMISSED)
    job.status = status.map_status(status.STATUS_DISMISSED)
    job = store.update_job(job)
    return job


@sd.provider_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProviderJobEndpoint(), response_schemas=sd.delete_prov_job_responses)
@sd.process_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                               schema=sd.DeleteProcessJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OUTPUT_FORMAT_JSON,
                       schema=sd.JobEndpoint(), response_schemas=sd.delete_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def cancel_job(request):
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


@sd.provider_jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.DeleteProviderJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@sd.process_jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.DeleteProcessJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@sd.jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OUTPUT_FORMAT_JSON,
                        schema=sd.DeleteJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def cancel_job_batch(request):
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


@sd.provider_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProviderInputsEndpoint(), response_schemas=sd.get_prov_inputs_responses)
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
    inputs.update({"links": job.links(request, self_link="inputs")})
    inputs = sd.JobInputsSchema().deserialize(inputs)
    return HTTPOk(json=inputs)


@sd.provider_outputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.ProviderOutputsEndpoint(), response_schemas=sd.get_prov_outputs_responses)
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
    raise_job_dismissed(job, request)
    outputs = {"outputs": get_results(job, request)}
    outputs.update({"links": job.links(request, self_link="outputs")})
    outputs = sd.JobOutputsSchema().deserialize(outputs)
    return HTTPOk(json=outputs)


@sd.provider_results_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.ProviderResultsEndpoint(), response_schemas=sd.get_prov_results_responses)
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
    raise_job_dismissed(job, request)
    job_status = status.map_status(job.status)
    if job_status in status.JOB_STATUS_CATEGORIES[status.JOB_STATUS_CATEGORY_RUNNING]:
        raise HTTPNotFound(json={
            "code": "ResultsNotReady",
            "description": "Job status is '{}'. Results are not yet available.".format(job_status)
        })
    results = get_results(job, request, value_key="value", ogc_api=True)
    # note: cannot add links in this case because variable OutputID keys are directly at the root
    results = sd.Result().deserialize(results)
    return HTTPOk(json=results)


@sd.provider_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROVIDERS],
                                    renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderExceptionsEndpoint(),
                                    response_schemas=sd.get_prov_exceptions_responses)
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
    raise_job_dismissed(job, request)
    exceptions = sd.JobExceptionsSchema().deserialize(job.exceptions)
    return HTTPOk(json=exceptions)


@sd.provider_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.ProviderLogsEndpoint(), response_schemas=sd.get_prov_logs_responses)
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
    raise_job_dismissed(job, request)
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
