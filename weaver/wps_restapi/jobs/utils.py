import io
import math
import os
import shutil
from copy import deepcopy
from typing import TYPE_CHECKING, cast

import colander
from celery.utils.log import get_task_logger
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPCreated,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPLocked,
    HTTPNoContent,
    HTTPNotFound,
    HTTPOk
)
from pyramid_celery import celery_app
from requests_toolbelt.multipart.encoder import MultipartEncoder
from webob.headers import ResponseHeaders

from weaver.database import get_db
from weaver.datatype import Job, Process
from weaver.exceptions import (
    InvalidIdentifierValue,
    JobGone,
    JobInvalidParameter,
    JobNotFound,
    ProcessNotAccessible,
    ProcessNotFound,
    ServiceNotAccessible,
    ServiceNotFound
)
from weaver.execute import (
    ExecuteResponse,
    ExecuteReturnPreference,
    ExecuteTransmissionMode,
    parse_prefer_header_return,
    update_preference_applied_return_header
)
from weaver.formats import ContentEncoding, ContentType, get_format, repr_json
from weaver.owsexceptions import OWSNoApplicableCode, OWSNotFound
from weaver.processes.constants import JobInputsOutputsSchema
from weaver.processes.convert import any2wps_literal_datatype, convert_output_params_schema, get_field
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import (
    data2str,
    fetch_file,
    get_any_id,
    get_any_value,
    get_header,
    get_href_headers,
    get_path_kvp,
    get_sane_name,
    get_secure_path,
    get_settings,
    get_weaver_url,
    is_uuid,
    make_link_header
)
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.utils import resolve_process_tag
from weaver.wps_restapi.providers.utils import forbid_local_only

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

    from weaver.execute import AnyExecuteResponse, AnyExecuteReturnPreference, AnyExecuteTransmissionMode
    from weaver.formats import AnyContentEncoding
    from weaver.processes.constants import JobInputsOutputsSchemaType
    from weaver.typedefs import (
        AnyDataStream,
        AnyHeadersContainer,
        AnyRequestType,
        AnyResponseType,
        AnySettingsContainer,
        AnyValueType,
        ExecutionResultObject,
        ExecutionResults,
        ExecutionResultValue,
        HeadersTupleType,
        HeadersType,
        JobValueFormat,
        JSON,
        PyramidRequest,
        SettingsType
    )

    MultiPartFieldsParamsType = Union[
        AnyDataStream,
        # filename, data/io
        Tuple[Optional[str], AnyDataStream],
        # filename, data/io, content-type
        Tuple[Optional[str], AnyDataStream, Optional[str]],
        # filename, data/io, content-type, headers
        Tuple[Optional[str], AnyDataStream, Optional[str], HeadersType],
    ]
    MultiPartFieldsType = Sequence[Tuple[str, MultiPartFieldsParamsType]]

LOGGER = get_task_logger(__name__)


def get_job(request):
    # type: (PyramidRequest) -> Job
    """
    Obtain a :term:`Job` from request parameters.

    .. versionchanged:: 4.20
        When looking for :term:`Job` that refers to a local :term:`Process`, allow implicit resolution of the
        unspecified ``version`` portion to automatically resolve the identifier. Consider that validation of
        the expected :term:`Process` for this :term:`Job` is "good enough", since the specific ID is not actually
        required to obtain the :term:`Job` (could be queried by ID only on the ``/jobs/{jobId}`` endpoint.
        If the ``version`` is provided though (either query parameter or tagged representation), the validation
        will ensure that it matches explicitly.

    :param request: Request with path and query parameters to retrieve the desired job.
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
    process_tag = request.matchdict.get("process_id")
    if process_tag:
        process_tag = resolve_process_tag(request)  # find version if available as well
    else:
        process_tag = job.process
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
                "cause": str(provider_id)
            },
            code=title, locator="provider", description=desc  # old format
        )

    process_id = Process.split_version(process_tag)[0]
    if job.process not in [process_id, process_tag]:
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
                "cause": str(process_tag)
            },
            code=title, locator="process", description=desc  # old format
        )
    return job


def get_job_list_links(job_total, filters, request):
    # type: (int, Dict[str, AnyValueType], AnyRequestType) -> List[JSON]
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
        {"href": f"{job_path}?detail=false", "rel": "preview",
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


def get_schema_query(
    schema,         # type: Optional[JobInputsOutputsSchemaType]
    strict=True,    # type: bool
    default=None,   # type: Optional[JobInputsOutputsSchemaType]
):                  # type: (...) -> Optional[JobInputsOutputsSchemaType]
    if not schema:
        return default
    # unescape query (eg: "OGC+strict" becomes "OGC string" from URL parsing)
    schema_checked = cast(
        "JobInputsOutputsSchemaType",
        str(schema).replace(" ", "+").lower()
    )
    if JobInputsOutputsSchema.get(schema_checked) is None:
        raise HTTPBadRequest(json={
            "type": "InvalidParameterValue",
            "detail": "Query parameter 'schema' value is invalid.",
            "status": HTTPBadRequest.code,
            "locator": "query",
            "value": str(schema),
        })
    if not strict:
        return schema_checked.split("+", 1)[0]
    return schema_checked


def make_result_link(
    job,                    # type: Job
    result,                 # type: ExecutionResultValue
    output_id,              # type: str
    output_mode,            # type: AnyExecuteTransmissionMode
    output_format=None,     # type: Optional[JobValueFormat]
    *,                      # force named keyword arguments after
    settings,               # type: SettingsType
):                          # type: (...) -> List[str]
    """
    Convert a result definition as ``value`` into the corresponding ``reference`` for output transmission.

    .. seealso::
        :rfc:`8288`: HTTP ``Link`` header specification.
    """
    values = result if isinstance(result, list) else [result]
    suffixes = list(f".{idx}" for idx in range(len(values))) if isinstance(result, list) else [""]
    links = []
    for suffix, value in zip(suffixes, values):
        result_id = f"{output_id}{suffix}"
        headers, _ = generate_or_resolve_result(job, value, result_id, output_id, output_mode, output_format, settings)
        url = headers["Content-Location"]
        typ = headers["Content-Type"]
        enc = headers.get("Content-Encoding", None)
        link_header = make_link_header(url, rel=result_id, type=typ, charset=enc)
        links.append(link_header)
    return links


def get_results(  # pylint: disable=R1260
    job,                                # type: Job
    container,                          # type: AnySettingsContainer
    value_key=None,                     # type: Optional[str]
    schema=JobInputsOutputsSchema.OLD,  # type: Optional[JobInputsOutputsSchemaType]
    link_references=False,              # type: bool
):                                      # type: (...) -> Tuple[ExecutionResults, HeadersTupleType]
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
        If enabled, an output that was requested by reference instead of by value will be returned as ``Link`` header.
    :returns:
        Tuple with:
            - List or mapping of all outputs each with minimally an ID and value under the requested key.
            - List of ``Link`` headers for reference outputs when requested. Empty otherwise.
    """
    settings = get_settings(container)
    wps_url = get_wps_output_url(settings)
    if not wps_url.endswith("/"):
        wps_url = f"{wps_url}/"
    schema = JobInputsOutputsSchema.get(str(schema).lower(), default=JobInputsOutputsSchema.OLD)
    strict = schema.endswith("+strict")
    schema = schema.split("+")[0]
    ogc_api = schema == JobInputsOutputsSchema.OGC
    outputs = {} if ogc_api else []
    fmt_key = "mediaType" if ogc_api else "mimeType"
    references = {}
    for result in job.results:
        # Filter outputs not requested, unless 'all' requested by omitting
        out_id = get_any_id(result)
        if (
            (isinstance(job.outputs, dict) and out_id not in job.outputs) or
            (isinstance(job.outputs, list) and not any(get_any_id(out) == out_id for out in job.outputs))
        ):
            LOGGER.debug("Removing [%s] from %s results response because not requested.", out_id, job)
            continue

        # Complex result could contain both 'data' and a reference (eg: JSON file and its direct representation).
        # Literal result is only by itself. Therefore, find applicable field by non 'data' match.
        rtype = "href" if get_any_value(result, key=True, file=True, data=False) else "data"
        value = get_any_value(result)
        # An array of literals can be merged as-is
        if (
            isinstance(value, list) and
            all(
                isinstance(val, (bool, float, int, str, type(None)))
                for val in value
            )
        ):
            array = [value]  # array of array such that it iterated as the array of literals directly
        # Any other type of array implies complex data (bbox, collection, file, etc.)
        # They must be defined on their own with respective media-type/format details per item.
        else:
            array = value if isinstance(value, list) else [value]

        for val_item in array:
            val_data = val_item
            if isinstance(val_item, dict) and isinstance(value, list):
                rtype = "href" if get_any_value(val_item, key=True, file=True, data=False) else "data"
                val_data = get_any_value(val_item, file=True, data=False)
            if not isinstance(val_item, dict):
                # use the representation that contains all metadata if possible, otherwise rely on literal data only
                val_item = result if isinstance(result, dict) else {rtype: val_data}

            out_key = rtype
            is_ref = rtype == "href"
            out_mode, out_fmt = get_job_output_transmission(job, out_id, is_reference=is_ref)
            as_ref = link_references and out_mode == ExecuteTransmissionMode.REFERENCE

            if is_ref and isinstance(val_data, str):
                # fix paths relative to instance endpoint,
                # but leave explicit links as is (eg: S3 bucket, remote HTTP, etc.)
                if val_data.startswith("/"):
                    val_data = val_data.lstrip("/")
                if "://" not in val_data:
                    val_data = wps_url + val_data
            elif ogc_api:
                out_key = "value"
            elif value_key:
                out_key = value_key

            output = {out_key: val_data}

            # required for the rest to be there, other fields optional
            if is_ref:
                if "mimeType" not in val_item:
                    val_item["mimeType"] = get_format(val_data, default=ContentType.TEXT_PLAIN).mime_type
                if ogc_api or not strict:
                    output["type"] = val_item["mimeType"]
                if not ogc_api or not strict or as_ref:
                    output["format"] = {fmt_key: val_item["mimeType"]}
                    for field in ["encoding", "schema"]:
                        if field in result:
                            output["format"][field] = val_item[field]
            elif not is_ref:
                dtype = result.get("dataType", any2wps_literal_datatype(val_data, is_value=True) or "string")
                if ogc_api:
                    output["dataType"] = {"name": dtype}
                else:
                    output["dataType"] = dtype

            if schema == JobInputsOutputsSchema.OGC_STRICT:
                out_fmt = output.pop("format", {})
                for fmt_key, fmt_val in out_fmt.items():
                    output.setdefault(fmt_key, fmt_val)

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
    headers = get_job_results_links(job, references, {}, headers=[], settings=settings)

    return outputs, headers


def get_job_return(
    job=None,       # type: Optional[Job]
    body=None,      # type: Optional[JSON]
    headers=None,   # type: Optional[AnyHeadersContainer]
):                  # type: (...) -> Tuple[AnyExecuteResponse, AnyExecuteReturnPreference]
    """
    Obtain the :term:`Job` result representation based on the resolution order of preferences and request parameters.

    Body and header parameters are considered first, in case they provide 'overrides' for the active request.
    Then, if the :paramref:`job` was already parsed from the original request, and contains pre-resolved return,
    this format is employed. When doing the initial parsing, ``job=None`` MUST be used.
    """
    body = body or {}
    resp = ExecuteResponse.get(body.get("response"))
    if resp:
        return resp, ExecuteReturnPreference.MINIMAL

    pref = parse_prefer_header_return(headers)
    if pref == ExecuteReturnPreference.MINIMAL:
        return ExecuteResponse.DOCUMENT, ExecuteReturnPreference.MINIMAL
    if pref == ExecuteReturnPreference.REPRESENTATION:
        return ExecuteResponse.RAW, ExecuteReturnPreference.REPRESENTATION

    if not job:
        return ExecuteResponse.DOCUMENT, ExecuteReturnPreference.MINIMAL
    return job.execution_response, job.execution_return


def get_job_output_transmission(job, output_id, is_reference):
    # type: (Job, str, bool) -> Tuple[AnyExecuteTransmissionMode, Optional[JobValueFormat]]
    """
    Obtain the requested :term:`Job` output ``transmissionMode`` and ``format``.
    """
    outputs = job.outputs or {}
    outputs = convert_output_params_schema(outputs, JobInputsOutputsSchema.OGC)
    out = outputs.get(output_id) or {}
    out_mode = cast("AnyExecuteTransmissionMode", out.get("transmissionMode"))
    out_fmt = cast("JobValueFormat", out.get("format"))

    # raw/representation can change the output transmission mode if they are not overriding it
    # document/minimal return is not checked, since it is our default, and will resolve as such anyway
    if (
        not out_mode and
        job.execution_return == ExecuteReturnPreference.REPRESENTATION and
        job.execution_response == ExecuteResponse.RAW
    ):
        return ExecuteTransmissionMode.VALUE, out_fmt

    # because mode can be omitted, resolve their default explicitly
    if not out_mode:
        out_mode = ExecuteTransmissionMode.REFERENCE if is_reference else ExecuteTransmissionMode.VALUE
    return out_mode, out_fmt


def get_job_results_response(
    job,                        # type: Job
    *,                          # force named keyword arguments after
    container,                  # type: AnySettingsContainer
    request_headers=None,       # type: Optional[AnyHeadersContainer]
    response_headers=None,      # type: Optional[AnyHeadersContainer]
    results_headers=None,       # type: Optional[AnyHeadersContainer]
    results_contents=None,      # type: Optional[JSON]
):                              # type: (...) -> AnyResponseType
    """
    Generates the :term:`OGC` compliant :term:`Job` results response according to submitted execution parameters.

    Parameters that impact the format of the response are:
        - Body parameter ``outputs`` with the amount of *requested outputs* to be returned.
        - Body parameter ``response: raw|document`` for content representation.
        - Body parameter ``transmissionMode: value|reference`` per output.
        - Header parameter ``Prefer: return=representation|minimal`` for content representation.
        - Overrides, for any of the previous parameters, allowing request of an alternate representation.

    Resolution order/priority:

    1. :paramref:`override_contents`
    2. :paramref:`override_headers`
    3. :paramref:`job` definitions

    The logic of the resolution order is that any body parameters resolving to an equivalent information provided
    by header parameters will be more important, since ``Prefer`` are *soft* requirements, whereas body parameters
    are *hard* requirements. The parameters stored in the :paramref:`job` are defined during :term:`Job` submission,
    which become the "default" results representation if requested as is. If further parameters are provided to
    override during the results request, they modify the "default" results representation. In this case, an header
    provided in the results request overrides the body parameters from the original :term:`Job`, since their results
    request context is "closer" than the ones at the time of the :term:`Job` submission.

    .. seealso::
        More details available for each combination:
        - https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execute_response
        - https://docs.ogc.org/is/18-062r2/18-062r2.html#_response_7
        - :ref:`proc_op_job_results`
        - :ref:`proc_exec_results`

    :param job: Job for which to generate the results response, which contains the originally submitted parameters.
    :param container: Application settings.
    :param request_headers: Original headers submitted to the request that leads to this response.
    :param response_headers: Additional headers to provide in the response.
    :param results_headers: Headers that override originally submitted job parameters when requesting results.
    :param results_contents: Body contents that override originally submitted job parameters when requesting results.
    """
    raise_job_dismissed(job, container)
    raise_job_bad_status_success(job, container)
    settings = get_settings(container)

    results, _ = get_results(
        job, container,
        value_key="value",
        schema=JobInputsOutputsSchema.OGC,  # not strict to provide more format details
        # no link headers since they are represented differently based on request parameters
        # leave it up to each following content-type/response specific representation to define them
        link_references=False,
    )

    headers = ResponseHeaders(response_headers or {})
    headers.pop("Location", None)
    headers.setdefault("Content-Location", job.results_url(container))
    for link in job.links(container, self_link="results"):
        link_header = make_link_header(link)
        headers.add("Link", link_header)

    # resolve request details to redirect for appropriate response handlers
    job_resp, job_ret = get_job_return(job, results_contents, results_headers)
    is_accept_multipart = (
        isinstance(job.accept_type, str) and
        any(ctype in job.accept_type for ctype in ContentType.ANY_MULTIPART)
    )
    is_rep = job_ret == ExecuteReturnPreference.REPRESENTATION
    is_raw = job_resp == ExecuteResponse.RAW

    # if a single output is explicitly requested, the representation must be ignored and return it directly
    # (single result does not matter for a process generating only one, it is the N output requested that matters)
    is_single_output_minimal = (
        job.outputs is not None and len(job.outputs) == 1 and
        not is_rep and ContentType.APP_JSON not in job.accept_type  # alternative way to request 'minimal'/'document'
    )

    headers = update_preference_applied_return_header(job, request_headers, headers)

    # document/minimal response
    if not is_raw and not is_accept_multipart and not is_single_output_minimal:
        try:
            results_schema = sd.ResultsDocument()
            results_json = results_schema.deserialize(results)
            if len(results_json) != len(results):  # pragma: no cover  # ensure no outputs silently dismissed
                raise colander.Invalid(
                    results_schema,
                    msg=f"Failed validation for values of outputs: {list(set(results) - set(results_json))}",
                    value=results,
                )
        except colander.Invalid as exc:  # pragma: no cover
            raise HTTPInternalServerError(
                json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
                    "type": "InvalidSchema",
                    "title": "Invalid Results",
                    "detail": "Results body failed schema validation.",
                    "status": HTTPInternalServerError.status_code,
                    "error": exc.msg,
                    "value": repr_json(exc.value),
                })
            )

        # resolution of 'transmissionMode' for document representation will be done by its own handler function
        #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#_response_7 (/req/core/job-results-async-document)
        #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-document
        # use deserialized contents such that only the applicable fields remain
        # (simplify compares, this is assumed by the following call)
        results_json = get_job_results_document(job, results_json, settings=settings)
        return HTTPOk(json=results_json, headers=headers)

    if not results:  # avoid schema validation error if all by reference
        # Status code 204 for empty body
        # see:
        #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-ref
        #   - https://docs.ogc.org/DRAFTS/18-062.html#req_core_job-results-param-outputs-empty
        return HTTPNoContent(headers=headers)

    # raw response can be data-only value, link-only or a mix of them
    # if raw representation is requested and all requested outputs resolve as links
    # without explicit 'accept: multipart', then all must use link headers
    #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-ref
    res_refs = {
        out_id: bool(get_any_value(out, key=True, file=True, data=False))
        for out_id, out in results.items()
    }
    out_transmissions = {
        out_id: get_job_output_transmission(job, out_id, is_ref)
        for out_id, is_ref in res_refs.items()
    }
    if is_raw and not is_rep and all(
        out_mode == ExecuteTransmissionMode.REFERENCE
        for out_mode, _ in out_transmissions.values()
    ):
        headers = get_job_results_links(job, results, out_transmissions, headers=headers, settings=settings)
        return HTTPNoContent(headers=headers)

    # FIXME: support ZIP or similar "container" output (https://github.com/crim-ca/weaver/issues/726)
    # FIXME: support Metalink - needs by-reference only (https://github.com/crim-ca/weaver/issues/663)
    # multipart response
    #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-value-multi
    #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-mixed-multi
    #   - https://docs.ogc.org/DRAFTS/18-062.html#per_core_job-results-async-many-other-formats
    # extract data to see if it happens to be an array (i.e.: 1 output "technically", but needs multipart)
    out_vals = list(results.items())  # type: List[Tuple[str, ExecutionResultValue]]  # noqa
    out_info = out_vals[0][-1]  # type: ExecutionResultValue
    out_data = get_any_value(out_info)
    if (
        len(results) > 1 or
        (isinstance(out_data, list) and len(out_data) > 1) or  # single output is an array, needs multipart
        is_accept_multipart
    ):
        return get_job_results_multipart(job, results, headers=headers, settings=settings)

    # https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-value-one
    res_id = out_vals[0][0]
    # FIXME: add transform for requested output format (https://github.com/crim-ca/weaver/pull/548)
    #   req_fmt = guess_target_format(container)   where container=request
    #   out_fmt (see above)
    #   out_type = result.get("type")
    #   out_select = req_fmt or out_fmt or out_type  (resolution order/precedence)
    out_fmt = None
    return get_job_results_single(job, out_info, res_id, out_fmt, headers=headers, settings=settings)


def generate_or_resolve_result(
    job,            # type: Job
    result,         # type: ExecutionResultObject
    result_id,      # type: str
    output_id,      # type: str
    output_mode,    # type: AnyExecuteTransmissionMode
    output_format,  # type: Optional[JobValueFormat]  # FIXME: implement (https://github.com/crim-ca/weaver/pull/548)
    settings,       # type: SettingsType
):                  # type: (...) -> Tuple[HeadersType, Optional[AnyDataStream]]
    """
    Obtains the local file path and the corresponding :term:`URL` reference for a given result, generating it as needed.

    :param job: Job with results details.
    :param result: The specific output value or reference (could be an item index within an array of a given output).
    :param result_id: Specific identifier of the result, including any array index as applicable.
    :param output_id: Generic identifier of the output containing the result.
    :param output_mode: Desired output transmission mode.
    :param output_format: Desired output transmission ``format``, with minimally the :term:`Media-Type`.
    :param settings: Application settings to resolve locations.
    :return:
        Resolved headers and data (as applicable) for the result.
        If only returned by reference, ``None`` data is returned. An empty-data contents would be an empty string.
        Therefore, the explicit check of ``None`` is important to identify a by-reference result.
    """
    is_val = bool(get_any_value(result, key=True, file=False, data=True))
    is_ref = bool(get_any_value(result, key=True, file=True, data=False))
    val = get_any_value(result)
    cid = f"{result_id}@{job.id}"
    url = None
    loc = None
    res_data = None
    c_length = None

    # NOTE:
    #   work with local files (since we have them), to avoid unnecessary loopback request
    #   then, rewrite the locations after generating their headers to obtain the final result URL

    if is_ref:
        url = val
        typ = result.get("type")  # expected for typical link, but also check media-type variants in case pre-converted
        typ = typ or get_field(result, "mime_type", search_variations=True, default=ContentType.APP_OCTET_STREAM)
        job_out_url = job.result_path(output_id=output_id)
        wps_out_url = get_wps_output_url(settings)
        if url.startswith(f"/{job_out_url}/"):  # job "relative" path
            url = os.path.join(wps_out_url, url[1:])
        if url.startswith(wps_out_url):
            loc = map_wps_output_location(url, settings, exists=True, url=False)
            loc = get_secure_path(loc)
        else:
            loc = url  # remote storage, S3, etc.
    else:
        typ = get_field(result, "mime_type", search_variations=True, default=ContentType.TEXT_PLAIN)

    if not url:
        out_dir = get_wps_output_dir(settings)
        out_name = f"{result_id}.txt"
        job_path = job.result_path(output_id=output_id, file_name=out_name)
        loc = os.path.join(out_dir, job_path)
        loc = get_secure_path(loc)
        url = map_wps_output_location(loc, settings, exists=False, url=True)
    loc = loc[7:] if loc.startswith("file://") else loc
    is_local = loc.startswith("/")

    if is_val and output_mode == ExecuteTransmissionMode.VALUE:
        res_data = io.StringIO()
        c_length = res_data.write(data2str(val))

    if is_val and output_mode == ExecuteTransmissionMode.REFERENCE:
        if not os.path.isfile(loc):
            os.makedirs(os.path.dirname(loc), exist_ok=True)
            with open(loc, mode="w", encoding="utf-8") as out_file:
                out_file.write(data2str(val))

    if is_ref and output_mode == ExecuteTransmissionMode.VALUE and typ != ContentType.APP_DIR:
        res_path = loc
        if not is_local:
            # reference is a remote file, but by-value requested explicitly
            # try to retrieve its content locally to return it
            wps_out_dir = get_wps_output_dir(settings)
            job_out_dir = job.result_path(output_id=output_id)
            job_out_dir = os.path.join(wps_out_dir, job_out_dir)
            os.makedirs(job_out_dir, exist_ok=True)
            res_path = fetch_file(res_path, job_out_dir, settings=settings)
        res_data = io.FileIO(res_path, mode="rb")

    res_headers = get_href_headers(
        loc,
        download_headers=True,
        missing_ok=True,        # only basic details if file does not exist
        content_headers=True,
        content_type=typ,
        content_id=cid,
        content_name=result_id,
        content_location=url,   # rewrite back the original URL
        settings=settings,
    )
    if output_mode == ExecuteTransmissionMode.VALUE and not res_headers.get("Content-Length") and c_length is not None:
        res_headers["Content-Length"] = str(c_length)
    if output_mode == ExecuteTransmissionMode.REFERENCE:
        res_data = None
        res_headers["Content-Length"] = "0"
    if not os.path.exists(loc) and is_local:
        res_headers.pop("Content-Location", None)
    return res_headers, res_data


def resolve_result_json_literal(
    result,                 # type: ExecutionResultValue
    output_format,          # type: Optional[JobValueFormat]
    content_type=None,      # type: Optional[str]
    content_encoding=None,  # type: Optional[str]
):                          # type: (...) -> ExecutionResultValue
    """
    Generates a :term:`JSON` literal string or object representation according to requested format and result contents.

    If not a ``value`` structure, the result is returned unmodified. If no output ``format`` is provided, or that
    the extracted result :term:`Media-Type` does not correspond to a :term:`JSON` value, the result is also unmodified.
    Otherwise, string/object representation is resolved according to the relevant  :term:`Media-Type`.

    :param result: Container with nested data.
    :param output_format: Desired output transmission ``format``, with minimally the :term:`Media-Type`.
    :param content_type: Explicit :term:`Media-Type` to employ instead of an embedded ``mediaType`` result property.
    :param content_encoding: Explicit data encoding to employ instead of an embedded ``encoding`` result property.
    :return: Converted :term:`JSON` data or the original result as applicable.
    """
    if not result or not isinstance(result, dict) or "value" not in result:
        return result
    if not content_type:
        content_type = get_field(result, "mediaType", default=None, search_variations=True)
    if not content_encoding:
        content_encoding = get_field(result, "encoding", default="utf-8", search_variations=True)
    if content_type == ContentType.APP_JSON and "value" in result:
        is_ascii = str(content_encoding).lower() == "ascii"
        out_type = get_field(output_format, "mediaType", default=ContentType.APP_JSON)
        if out_type == ContentType.APP_JSON:
            result["value"] = repr_json(result["value"], force_string=False, ensure_ascii=is_ascii)
        elif out_type in [ContentType.TEXT_PLAIN, ContentType.APP_RAW_JSON]:
            result["value"] = repr_json(
                result["value"],
                force_string=True,
                ensure_ascii=is_ascii,
                # following for minimal representation
                indent=None,
                separators=(",", ":"),
            )
            result["mediaType"] = ContentType.APP_RAW_JSON  # ensure disambiguation from other plain text
    return result


def get_job_results_links(
    job,            # type: Job
    references,     # type: Dict[str, ExecutionResultValue]
    transmissions,  # type: Dict[str, Tuple[AnyExecuteTransmissionMode, JobValueFormat]]
    headers,        # type: AnyHeadersContainer
    *,              # force named keyword arguments after
    settings,       # type: SettingsType
):                  # type: (...) -> AnyHeadersContainer
    """
    Generates ``Link`` headers for all specified result references and adds them to the specified header container.
    """
    for out_id, output in references.items():
        out_trans = transmissions.get(out_id)
        out_fmt = out_trans[-1] if out_trans else None
        out_mode = ExecuteTransmissionMode.REFERENCE
        res_links = make_result_link(job, output, out_id, out_mode, out_fmt, settings=settings)
        headers.extend([("Link", link) for link in res_links])
    return headers


def get_job_results_single(
    job,            # type: Job
    result,         # type: ExecutionResultObject
    output_id,      # type: str
    output_format,  # type: Optional[JobValueFormat]
    headers,        # type: AnyHeadersContainer
    *,              # force named keyword arguments after
    settings,       # type: AnySettingsContainer
):                  # type: (...) -> Union[HTTPOk, HTTPNoContent]
    """
    Generates a single result response according to specified or resolved output transmission and format.

    :param job: Job definition to obtain relevant path resolution.
    :param result: Result to be represented.
    :param output_id: Identifier of the corresponding result output.
    :param output_format: Desired output format for convertion, as applicable.
    :param headers: Additional headers to include in the response.
    :param settings: Application settings to resolve locations.
    :return:
    """
    # FIXME: implement (https://github.com/crim-ca/weaver/pull/548)
    #   for .../results/{id} transform might need to force 'Prefer' over job preference
    #   (explicitly request value/link contrary to resolved results/mode from the job)

    is_ref = bool(get_any_value(result, key=True, file=True, data=False))
    out_data = get_any_value(result, file=is_ref, data=not is_ref)
    out_mode, out_fmt = get_job_output_transmission(job, output_id, is_ref)
    output_format = output_format or out_fmt
    if out_mode == ExecuteTransmissionMode.REFERENCE:
        link = make_result_link(job, result, output_id, out_mode, output_format, settings=settings)
        headers.extend([("Link", link[0])])
        return HTTPNoContent(headers=headers)

    # convert value as needed since reference transmission was not requested/resolved
    out_headers = {}
    if is_ref:
        output_mode = ExecuteTransmissionMode.VALUE
        out_headers, out_data = generate_or_resolve_result(
            job,
            result,
            output_id,
            output_id,
            output_mode,
            output_format,
            settings=settings,
        )
        headers.update(out_headers)

    ctype = out_headers.get("Content-Type")
    if not ctype:
        ctype = get_field(result, "mediaType", search_variations=True, default=ContentType.TEXT_PLAIN)
    c_enc = cast("AnyContentEncoding", headers.get("Content-Encoding") or "UTF-8")  # type: AnyContentEncoding
    out_data = data2str(out_data)
    out_data = ContentEncoding.encode(out_data, c_enc)
    return HTTPOk(body=out_data, content_type=ctype, charset=c_enc, headers=headers)


def get_job_results_document(job, results, *, settings):
    # type: (Job, ExecutionResults, Any, SettingsType) -> ExecutionResults
    """
    Generates the :term:`Job` results document response from available or requested outputs with necessary conversions.

    Removes nested literal value definitions if qualified value representation is not needed.
    Qualified value representation is not needed if no other field than ``value`` is provided with the literal data,
    or when the specified :term:`Media-Type` is simply the plain text default for data literals.
    The simplification is applied for both literals on their own and nested array of literals.
    However, when processing an array, the qualified value representation is preserved if any of the items requires
    the explicit mention of another :term:`Media-Type` than plain text, to return a consistent structure.

    Uses the :paramref:`job` definition and submitted ``headers``

    .. warning::
        This function assumes that schema deserialization was applied beforehand.
        Therefore, it will not attempt matching every possible combination of the results representation.
    """

    def make_result(result, result_id, output_id):
        # type: (ExecutionResultValue, str, str) -> Union[AnyValueType, ExecutionResultObject]
        if isinstance(result, dict):
            is_ref = bool(get_any_value(result, key=True, file=True, data=False))
            val = get_any_value(result)
        else:
            is_ref = False
            val = result
            result = {"value": val}
        out_mode, out_fmt = get_job_output_transmission(job, result_id, is_reference=is_ref)
        headers, data = generate_or_resolve_result(job, result, result_id, output_id, out_mode, out_fmt, settings)
        if data is None:
            ref = {
                "href": headers["Content-Location"],
                "type": headers["Content-Type"],
            }
            return ref

        c_type = headers.get("Content-Type") or ""
        c_enc = ContentEncoding.get(headers.get("Content-Encoding"))
        if not c_type or (
            # note:
            #   Explicit content-type check to consider that any additional parameter provided
            #   with text/plain must be reported. Only "purely" plain/text can be removed.
            c_type == ContentType.TEXT_PLAIN and not c_enc
        ):
            value = val  # use original to avoid string conversion
        else:
            value = {"mediaType": c_type}
            data = data2str(data)
            if c_enc:
                data = ContentEncoding.encode(data, c_enc)
                value["encoding"] = c_enc
            value["value"] = data

        # special case of nested JSON data within the JSON document
        value = resolve_result_json_literal(value, out_fmt, c_type, c_enc)

        return value

    out_results = {}
    for out_id, res_val in results.items():
        if isinstance(res_val, list):
            res_data = []
            for out_idx, item in enumerate(res_val):
                res_id = f"{out_id}.{out_idx}"
                out_res = make_result(item, res_id, out_id)
                res_data.append(out_res)

            # backtrack is not all literals (all qualified or none qualified, but no mix)
            is_qualified = [isinstance(item, dict) for item in res_data]
            if not all(is_qualified) and len([item for item in is_qualified if item]):
                res_data = [
                    item
                    if isinstance(item, dict)
                    else {"value": data2str(item), "mediaType": ContentType.TEXT_PLAIN}
                    for item in res_data
                ]

        else:
            res_data = make_result(res_val, out_id, out_id)

        out_results[out_id] = res_data
    return out_results


def get_job_results_multipart(job, results, *, headers, settings):
    # type: (Job, ExecutionResults, Any, AnyHeadersContainer, SettingsType) -> HTTPOk
    """
    Generates the :term:`Job` results multipart response from available or requested outputs with necessary conversions.

    .. seealso::
        - Function :func:`get_results` should be used to avoid re-processing all output format combinations.
        - Details of ``multipart`` (:rfc:`2046#section-5.1`) :term:`Media-Type` family.

    :param job: Job definition with potential metadata about requested outputs.
    :param results: Pre-filtered and pre-processed results in a normalized format structure.
    :param headers: Additional headers to include in the response.
    :param settings: Application settings to resolve locations.
    """

    def add_result_parts(result_parts):
        # type: (List[Tuple[str, str, ExecutionResultObject]]) -> MultiPartFieldsType
        for out_id, res_id, result in result_parts:
            if isinstance(result, list):
                sub_parts = [(out_id, f"{out_id}.{out_idx}", data) for out_idx, data in enumerate(result)]
                sub_parts = add_result_parts(sub_parts)
                sub_multi = MultipartEncoder(sub_parts, content_type=ContentType.MULTIPART_MIXED)
                sub_out_url = job.result_path(output_id=out_id)
                sub_headers = {
                    "Content-Type": sub_multi.content_type,
                    "Content-ID": f"<{out_id}@{job.id}>",
                    "Content-Location": sub_out_url,
                    "Content-Disposition": f"attachment; name=\"{out_id}\"",
                }
                yield res_id, (None, sub_multi, None, sub_headers)

            is_ref = bool(get_any_value(result, key=True, file=True, data=False))
            out_mode, out_fmt = get_job_output_transmission(job, out_id, is_reference=is_ref)
            res_headers, res_data = generate_or_resolve_result(job, result, res_id, out_id, out_mode, out_fmt, settings)
            c_type = res_headers.get("Content-Type")
            c_loc = res_headers.get("Content-Location")
            c_fn = os.path.basename(c_loc) if c_loc else None
            yield res_id, (c_fn, res_data, c_type, res_headers)

    results_parts = [(_res_id, _res_id, _res_val) for _res_id, _res_val in results.items()]
    results_parts = list(add_result_parts(results_parts))
    res_multi = MultipartEncoder(results_parts, content_type=ContentType.MULTIPART_MIXED)
    resp_headers = headers or {}
    resp_headers.update({"Content-Type": res_multi.content_type})
    resp = HTTPOk(detail=f"Multipart Response for {job}", headers=resp_headers)
    resp.body = res_multi.read()
    return resp


def get_job_submission_response(body, headers, error=False):
    # type: (JSON, AnyHeadersContainer, bool) -> Union[HTTPOk, HTTPCreated, HTTPBadRequest]
    """
    Generates the response contents returned by :term:`Job` submission process.

    If :term:`Job` already finished processing within requested ``Prefer: wait=X`` seconds delay (and if allowed by
    the :term:`Process` ``jobControlOptions``), return the successful status immediately instead of created status.

    If the status is not successful, return the failed :term:`Job` status response.

    Otherwise, return the status monitoring location of the created :term:`Job` to be monitored asynchronously.

    .. seealso::
        - :func:`weaver.processes.execution.submit_job`
        - :func:`weaver.processes.execution.submit_job_handler`
        - :ref:`proc_op_job_status`
    """
    # convert headers to pass as list to avoid any duplicate Content-related headers
    # otherwise auto-added by JSON handling when provided by dict-like structure
    if hasattr(headers, "items"):
        headers = list(headers.items())
    get_header("Content-Type", headers, pop=True)
    headers.append(("Content-Type", ContentType.APP_JSON))

    status = map_status(body.get("status"))
    if status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
        if error:
            http_class = HTTPBadRequest
            http_desc = sd.FailedSyncJobResponse.description
        else:
            http_class = HTTPOk
            http_desc = sd.CompletedJobResponse.description
            body = sd.CompletedJobStatusSchema().deserialize(body)

        body["description"] = http_desc
        return http_class(json=body, headerlist=headers)

    if status == Status.CREATED:
        body["description"] = (
            "Job successfully submitted for creation. "
            "Waiting on trigger request to being execution."
        )
    else:
        body["description"] = (
            "Job successfully submitted to processing queue. "
            "Execution should begin when resources are available."
        )
    body = sd.CreatedJobStatusSchema().deserialize(body)
    headers.setdefault("Location", body["location"])
    return HTTPCreated(json=body, headerlist=headers)


def validate_service_process(request):
    # type: (PyramidRequest) -> Tuple[Optional[str], Optional[str]]
    """
    Verifies that any :term:`Provider` or :term:`Process` specified by path or query are valid.

    :raises HTTPException: Relevant HTTP error with details if validation failed.
    :returns: Validated and existing service and process if specified.
    """
    provider_path = request.matchdict.get("provider_id", None)
    provider_query = request.params.get("provider", None)
    service_query = request.params.get("service", None)  # backward compatibility
    provider_items = {item for item in (provider_path, provider_query, service_query) if item is not None}
    if len(provider_items) > 1:
        raise HTTPBadRequest(json={
            "type": InvalidIdentifierValue.__name__,
            "title": "Multiple provider/service ID specified.",
            "description": "Cannot resolve a unique service provider when distinct ID in path/query are specified.",
            "value": repr_json(list(provider_items)),
        })
    service_name = (provider_path or provider_query or service_query)

    process_path = request.matchdict.get("process_id", None)
    process_query = request.params.get("process", None)
    proc_id_query = request.params.get("processID", None)  # OGC-API conformance
    process_items = {item for item in (process_path, process_query, proc_id_query) if item is not None}
    if len(process_items) > 1:
        raise HTTPBadRequest(json={
            "type": InvalidIdentifierValue.__name__,
            "title": "Multiple provider/service ID specified.",
            "description": "Cannot resolve a unique service provider when distinct ID in path/query are specified.",
            "value": repr_json(list(process_items)),
        })
    process_name = (process_path or process_query or proc_id_query)

    item_test = None
    item_type = None
    try:
        service = None
        if service_name:
            forbid_local_only(request)
            item_type = "Service"
            item_test = get_sane_name(service_name, assert_invalid=True)
            store = get_db(request).get_store(StoreServices)
            service = store.fetch_by_name(service_name, visibility=Visibility.PUBLIC)
        if process_name:
            item_type = "Process"
            item_test = resolve_process_tag(request, process_query=not process_path)
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
            "code": f"NoSuch{item_type}",
            "description": f"{item_type} reference '{item_test}' cannot be found."
        })
    except (ServiceNotAccessible, ProcessNotAccessible):
        raise HTTPForbidden(json={
            "code": f"Unauthorized{item_type}",
            "description": f"{item_type} reference '{item_test}' is not accessible."
        })
    except colander.Invalid as exc:
        raise HTTPBadRequest(json={
            "type": InvalidIdentifierValue.__name__,
            "title": "Invalid path or query parameter value.",
            "description": "Provided path or query parameters for process and/or provider reference are invalid.",
            "cause": f"Invalid schema: [{exc.msg!s}]",
            "error": exc.__class__.__name__,
            "value": exc.value
        })
    return service_name, process_name


def raise_job_bad_status_locked(job, container=None):
    # type: (Job, Optional[AnySettingsContainer]) -> None
    """
    Raise the appropriate message for :term:`Job` unable to be modified.
    """
    if job.status != Status.CREATED:
        links = job.links(container=container)
        headers = [("Link", make_link_header(link)) for link in links]
        job_reason = ""
        if job.status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            job_reason = " It has already finished execution."
        elif job.status in JOB_STATUS_CATEGORIES[StatusCategory.PENDING]:
            job_reason = " It is already queued for execution."
        elif job.status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
            job_reason = " It is already executing."
        raise HTTPLocked(
            headers=headers,
            json={
                "title": "Job Locked for Execution",
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-4/1.0/locked",
                "detail": f"Job cannot be modified.{job_reason}",
                "status": HTTPLocked.code,
                "cause": {"status": job.status},
                "links": links
            }
        )


def raise_job_bad_status_success(job, container=None):
    # type: (Job, Optional[AnySettingsContainer]) -> None
    """
    Raise the appropriate message for :term:`Job` not ready or unable to retrieve output results due to status.
    """
    if job.status != Status.SUCCEEDED:
        links = job.links(container=container)
        headers = [("Link", make_link_header(link)) for link in links]
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
            raise HTTPBadRequest(
                headers=headers,
                json={
                    "title": "JobResultsFailed",
                    "type": err_code,
                    "detail": "Job results not available because execution failed.",
                    "status": HTTPBadRequest.code,
                    "cause": err_info,
                    "links": links
                }
            )

        # /req/core/job-results-exception/results-not-ready
        # must use OWS instead of HTTP class to preserve provided JSON body
        # otherwise, pyramid considers it as not found view/path and rewrites contents in append slash handler
        raise OWSNotFound(
            headers=headers,
            json={
                "title": "JobResultsNotReady",
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/result-not-ready",
                "detail": "Job is not ready to obtain results.",
                "status": HTTPNotFound.code,
                "cause": {"status": job.status},
                "links": links
            }
        )


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
        headers = [("Link", make_link_header(link)) for link in job_links]
        raise JobGone(
            headers=headers,
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
    job_out_log = os.path.join(wps_out_dir, f"{str(job.id)}.log")
    job_out_xml = os.path.join(wps_out_dir, f"{str(job.id)}.xml")
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
    job.status_message = f"Job {Status.DISMISSED}."
    job.status = map_status(Status.DISMISSED)
    job = store.update_job(job)
    return job
