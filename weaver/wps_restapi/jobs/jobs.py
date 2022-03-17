import math
import os
import shutil
from copy import deepcopy
from typing import TYPE_CHECKING

from celery.utils.log import get_task_logger
from colander import Invalid
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNoContent,
    HTTPNotFound,
    HTTPOk,
    HTTPPermanentRedirect,
    HTTPUnauthorized,
    HTTPUnprocessableEntity
)
from pyramid.request import Request
from pyramid_celery import celery_app

from notify import encrypt_email
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
from weaver.execute import ExecuteTransmissionMode
from weaver.formats import ContentType, OutputFormat, get_format, repr_json
from weaver.owsexceptions import OWSNoApplicableCode, OWSNotFound
from weaver.processes.convert import (
    any2wps_literal_datatype,
    convert_input_values_schema,
    convert_output_params_schema,
    get_field
)
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import get_any_id, get_any_value, get_path_kvp, get_settings, get_weaver_url, is_uuid
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.constants import JobInputsOutputsSchema
from weaver.wps_restapi.providers.utils import forbid_local_only
from weaver.wps_restapi.swagger_definitions import datetime_interval_parser

if TYPE_CHECKING:
    from typing import Dict, Iterable, List, Optional, Tuple, Union

    from pyramid.httpexceptions import HTTPException

    from weaver.typedefs import AnySettingsContainer, AnyUUID, AnyValueType, HeadersTupleType, JSON, SettingsType
    from weaver.wps_restapi.constants import JobInputsOutputsSchemaType

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
            # new format: https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_job-exception-no-such-job
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
            # new format: https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_job-exception-no-such-job
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
            # new format: https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_job-exception-no-such-job
            # note: although 'no-such-process' error, return 'no-such-job' because process could exist, only mismatches
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
            "type": ContentType.APP_JSON, "title": "Alternate endpoint with equivalent set of filtered jobs."
        }]

    links = alt_links + [
        {"href": job_path, "rel": "collection",
         "type": ContentType.APP_JSON, "title": "Complete job listing (no filtering queries applied)."},
        {"href": base_url + sd.jobs_service.path, "rel": "search",
         "type": ContentType.APP_JSON, "title": "Generic query endpoint to search for jobs."},
        {"href": job_path + "?detail=false", "rel": "preview",
         "type": ContentType.APP_JSON, "title": "Job listing summary (UUID and count only)."},
        {"href": job_path, "rel": "http://www.opengis.net/def/rel/ogc/1.0/job-list",
         "type": ContentType.APP_JSON, "title": "List of registered jobs."},
        {"href": get_path_kvp(job_path, page=cur_page, **kvp_params), "rel": "current",
         "type": ContentType.APP_JSON, "title": "Current page of job query listing."},
        {"href": get_path_kvp(job_path, page=0, **kvp_params), "rel": "first",
         "type": ContentType.APP_JSON, "title": "First page of job query listing."},
        {"href": get_path_kvp(job_path, page=max_page, **kvp_params), "rel": "last",
         "type": ContentType.APP_JSON, "title": "Last page of job query listing."},
    ]
    if cur_page > 0:
        links.append({
            "href": get_path_kvp(job_path, page=cur_page - 1, **kvp_params), "rel": "prev",
            "type": ContentType.APP_JSON, "title": "Previous page of job query listing."
        })
    if cur_page < max_page:
        links.append({
            "href": get_path_kvp(job_path, page=cur_page + 1, **kvp_params), "rel": "next",
            "type": ContentType.APP_JSON, "title": "Next page of job query listing."
        })
    if parent_url:
        links.append({
            "href": parent_url, "rel": "up",
            "type": ContentType.APP_JSON, "title": "Parent collection for which listed jobs apply."
        })
    return links


def get_schema_query(schema, strict=True):
    # type: (Optional[JobInputsOutputsSchemaType], bool) -> Optional[JobInputsOutputsSchemaType]
    if not schema:
        return None
    # unescape query (eg: "OGC+strict" becomes "OGC string" from URL parsing)
    schema_checked = str(schema).replace(" ", "+").lower()
    if JobInputsOutputsSchema.get(schema_checked) is None:
        raise HTTPBadRequest(json={
            "type": "InvalidParameterValue",
            "detail": "Query parameter 'schema' value is invalid.",
            "status": HTTPBadRequest.code,
            "locator": "query",
            "value": str(schema),
        })
    if not strict:
        return schema_checked.split("+")[0]
    return schema_checked


def make_result_link(result_id, result, job_id, settings):
    # type: (str, Union[JSON, List[JSON]], AnyUUID, SettingsType) -> List[str]
    """
    Convert a result definition as ``value`` into the corresponding ``reference`` for output transmission.

    .. seealso::
        :rfc:`8288`: HTTP ``Link`` header specification.
    """
    values = result if isinstance(result, list) else [result]
    suffixes = list(f".{idx}" for idx in range(len(values))) if isinstance(result, list) else [""]
    wps_url = get_wps_output_url(settings).strip("/")
    links = []
    for suffix, value in zip(suffixes, values):
        key = get_any_value(result, key=True)
        if key != "href":
            # literal data to be converted to link
            # plain text file must be created containing the raw literal data
            typ = ContentType.TEXT_PLAIN  # as per '/rec/core/process-execute-sync-document-ref'
            enc = "UTF-8"
            out = get_wps_output_dir(settings)
            val = get_any_value(value, data=True, file=False)
            loc = os.path.join(job_id, result_id + suffix + ".txt")
            url = f"{wps_url}/{loc}"
            path = os.path.join(out, loc)
            with open(path, mode="w", encoding=enc) as out_file:
                out_file.write(val)
        else:
            fmt = get_field(result, "format", default={"mediaType": ContentType.TEXT_PLAIN})
            typ = get_field(fmt, "mime_type", search_variations=True, default=ContentType.TEXT_PLAIN)
            enc = get_field(fmt, "encoding", search_variations=True, default=None)
            url = get_any_value(value, data=False, file=True)  # should already include full path
        links.append(f"<{url}>; rel=\"{result_id}{suffix}\"; type={typ}; charset={enc}")
    return links


def get_results(job,                                # type: Job
                container,                          # type: AnySettingsContainer
                value_key=None,                     # type: Optional[str]
                schema=JobInputsOutputsSchema.OLD,  # type: JobInputsOutputsSchemaType
                link_references=False,              # type: bool
                ):                                  # type: (...) -> Tuple[Union[List[JSON], JSON], HeadersTupleType]
    """
    Obtains the job results with extended full WPS output URL as applicable and according to configuration settings.

    :param job: job from which to retrieve results.
    :param container: any container giving access to instance settings (to resolve reference output location).
    :param value_key:
        If not specified, the returned values will have the appropriate ``data``/``href`` key according to the content.
        Otherwise, all values will have the specified key.
    :param schema:
        Selects which schema to employ for representing the output results (listing or mapping).
    :param link_references:
        If enabled, an output that was requested by reference instead of value will be returned as ``Link`` reference.
    :returns:
        Tuple with:
            - List or mapping of all outputs each with minimally an ID and value under the requested key.
            - List of ``Link`` headers for reference outputs when requested. Empty otherwise.
    """
    settings = get_settings(container)
    wps_url = get_wps_output_url(settings)
    if not wps_url.endswith("/"):
        wps_url = wps_url + "/"
    schema = JobInputsOutputsSchema.get(str(schema).lower(), default=JobInputsOutputsSchema.OLD)
    strict = schema.endswith("+strict")
    schema = schema.split("+")[0]
    ogc_api = schema == JobInputsOutputsSchema.OGC
    outputs = {} if ogc_api else []
    fmt_key = "mediaType" if ogc_api else "mimeType"
    out_ref = convert_output_params_schema(job.outputs, JobInputsOutputsSchema.OGC) if link_references else {}
    references = {}
    for result in job.results:
        rtype = "data" if any(k in result for k in ["data", "value"]) else "href"
        value = get_any_value(result)
        out_key = rtype
        out_id = get_any_id(result)
        out_mode = out_ref.get(out_id, {}).get("transmissionMode")
        as_ref = link_references and out_mode == ExecuteTransmissionMode.REFERENCE
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
                result["mimeType"] = get_format(value, default=ContentType.TEXT_PLAIN).mime_type
            if ogc_api or not strict:
                output["type"] = result["mimeType"]
            if not ogc_api or not strict or as_ref:
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

        if ogc_api or as_ref:
            mapping = references if as_ref else outputs
            if out_id in mapping:
                output_list = mapping[out_id]
                if not isinstance(output_list, list):
                    output_list = [output_list]
                output_list.append(output)
                mapping[out_id] = output_list
            else:
                mapping[out_id] = output
        else:
            # if ordered insert supported by python version, insert ID first
            output = dict([("id", out_id)] + list(output.items()))  # noqa
            outputs.append(output)

    # needed to collect and aggregate outputs of same ID first in case of array
    # convert any requested link references using indices if needed
    headers = []
    for out_id, output in references.items():
        res_links = make_result_link(out_id, output, job.id, settings)
        headers.extend([("Link", link) for link in res_links])

    return outputs, headers


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
            service = store.fetch_by_name(service_name, visibility=Visibility.PUBLIC)
        if process_name:
            item_type = "Process"
            item_test = process_name
            # local process
            if not service:
                store = get_db(request).get_store(StoreProcesses)
                store.fetch_by_id(process_name, visibility=Visibility.PUBLIC)
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


@sd.provider_jobs_service.get(tags=[sd.TAG_JOBS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                              schema=sd.GetProviderJobsEndpoint(), response_schemas=sd.get_prov_all_jobs_responses)
@sd.process_jobs_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_JOBS], renderer=OutputFormat.JSON,
                             schema=sd.GetProcessJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@sd.jobs_service.get(tags=[sd.TAG_JOBS], renderer=OutputFormat.JSON,
                     schema=sd.GetJobsEndpoint(), response_schemas=sd.get_all_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_queried_jobs(request):
    # type: (Request) -> HTTPOk
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
    # type: (Request) -> HTTPOk
    """
    Retrieve the status of a job.
    """
    job = get_job(request)
    job_status = job.json(request, self_link="status")
    return HTTPOk(json=job_status)


def raise_job_bad_status(job, container=None):
    # type: (Job, Optional[AnySettingsContainer]) -> None
    """
    Raise the appropriate message for :term:`Job` not ready or unable to retrieve output results due to status.
    """
    if job.status != Status.SUCCEEDED:
        links = job.links(container=container)
        if job.status == Status.FAILED:
            err_code = None
            err_info = None
            err_known_modules = [
                "pywps.exceptions",
                "owslib.wps",
                "weaver.exceptions",
                "weaver.owsexceptions",
            ]
            # try to infer the cause, fallback to generic error otherwise
            for error in job.exceptions:
                try:
                    if isinstance(error, dict):
                        err_code = error.get("Code")
                        err_info = error.get("Text")
                    elif isinstance(error, str) and any(error.startswith(mod) for mod in err_known_modules):
                        err_code, err_info = error.split(":", 1)
                        err_code = err_code.split(".")[-1].strip()
                        err_info = err_info.strip()
                except Exception:
                    err_code = None
                if err_code:
                    break
            if not err_code:  # default
                err_code = OWSNoApplicableCode.code
                err_info = "unknown"
            # /req/core/job-results-failed
            raise HTTPBadRequest(json={
                "title": "JobResultsFailed",
                "type": err_code,
                "detail": "Job results not available because execution failed.",
                "status": HTTPBadRequest.code,
                "cause": err_info,
                "links": links
            })

        # /req/core/job-results-exception/results-not-ready
        raise HTTPBadRequest(json={
            "title": "JobResultsNotReady",
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/result-not-ready",
            "detail": "Job is not ready to obtain results.",
            "status": HTTPBadRequest.code,
            "cause": {"status": job.status},
            "links": links
        })


def raise_job_dismissed(job, container=None):
    # type: (Job, Optional[AnySettingsContainer]) -> None
    """
    Raise the appropriate messages for dismissed :term:`Job` status.
    """
    if job.status == Status.DISMISSED:
        # provide the job status links since it is still available for reference
        settings = get_settings(container)
        job_links = job.links(settings)
        job_links = [link for link in job_links if link["rel"] in ["status", "alternate", "collection", "up"]]
        raise JobGone(
            json={
                "title": "JobDismissed",
                "type": "JobDismissed",
                "status": JobGone.code,
                "detail": "Job was dismissed and artifacts have been removed.",
                "cause": {"status": job.status},
                "value": str(job.id),
                "links": job_links
            }
        )


def dismiss_job_task(job, container):
    # type: (Job, AnySettingsContainer) -> Job
    """
    Cancels any pending or running :mod:`Celery` task and removes completed job artifacts.

    .. note::
        The :term:`Job` object itself is not deleted, only its artifacts.
        Therefore, its inputs, outputs, logs, exceptions, etc. are still available in the database,
        but corresponding files that would be exposed by ``weaver.wps_output`` configurations are removed.

    :param job: Job to cancel or cleanup.
    :param container: Application settings.
    :return: Updated and dismissed job.
    """
    raise_job_dismissed(job, container)
    if job.status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
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
    job.status_message = "Job {}.".format(Status.DISMISSED)
    job.status = map_status(Status.DISMISSED)
    job = store.update_job(job)
    return job


@sd.provider_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                schema=sd.ProviderJobEndpoint(), response_schemas=sd.delete_prov_job_responses)
@sd.process_job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.DeleteProcessJobEndpoint(), response_schemas=sd.delete_job_responses)
@sd.job_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OutputFormat.JSON,
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


@sd.provider_jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                 schema=sd.DeleteProviderJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@sd.process_jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                schema=sd.DeleteProcessJobsEndpoint(), response_schemas=sd.delete_jobs_responses)
@sd.jobs_service.delete(tags=[sd.TAG_JOBS, sd.TAG_DISMISS], renderer=OutputFormat.JSON,
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


@sd.provider_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                                schema=sd.ProviderInputsEndpoint(), response_schemas=sd.get_prov_inputs_responses)
@sd.process_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.ProcessInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@sd.job_inputs_service.get(tags=[sd.TAG_JOBS, sd.TAG_RESULTS], renderer=OutputFormat.JSON,
                           schema=sd.JobInputsEndpoint(), response_schemas=sd.get_job_inputs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_inputs(request):
    # type: (Request) -> HTTPException
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
    # type: (Request) -> HTTPException
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
    # type: (Request) -> HTTPException
    """
    Retrieve the results of a job.
    """
    job = get_job(request)
    raise_job_dismissed(job, request)
    raise_job_bad_status(job, request)
    job_status = map_status(job.status)
    if job_status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
        raise HTTPNotFound(json={
            "code": "ResultsNotReady",
            "description": "Job status is '{}'. Results are not yet available.".format(job_status)
        })

    results, refs = get_results(job, request, value_key="value",
                                schema=JobInputsOutputsSchema.OGC, link_references=True)
    # note:
    #   Cannot add "links" field in response body because variable Output ID keys are directly at the root
    #   Possible conflict with an output that would be named "links".

    if results:  # avoid error if all by reference
        results = sd.Result().deserialize(results)
        HTTPOk(json=results, headers=refs)
    return HTTPNoContent(headers=refs)


@sd.provider_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROVIDERS],
                                    renderer=OutputFormat.JSON, schema=sd.ProviderExceptionsEndpoint(),
                                    response_schemas=sd.get_prov_exceptions_responses)
@sd.job_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS], renderer=OutputFormat.JSON,
                               schema=sd.JobExceptionsEndpoint(), response_schemas=sd.get_exceptions_responses)
@sd.process_exceptions_service.get(tags=[sd.TAG_JOBS, sd.TAG_EXCEPTIONS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
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


@sd.provider_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROVIDERS], renderer=OutputFormat.JSON,
                              schema=sd.ProviderLogsEndpoint(), response_schemas=sd.get_prov_logs_responses)
@sd.job_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS], renderer=OutputFormat.JSON,
                         schema=sd.JobLogsEndpoint(), response_schemas=sd.get_logs_responses)
@sd.process_logs_service.get(tags=[sd.TAG_JOBS, sd.TAG_LOGS, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
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
    """
    Deprecated job result endpoint that is now returned by corresponding outputs path with added links.
    """
    location = request.url.rsplit("/", 1)[0] + "/outputs"
    LOGGER.warning("Deprecated route redirection [%s] -> [%s]", request.url, location)
    return HTTPPermanentRedirect(comment="deprecated", location=location)
