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
    HTTPNoContent,
    HTTPNotFound,
    HTTPOk
)
from pyramid.response import FileResponse
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
from weaver.execute import ExecuteResponse, ExecuteTransmissionMode, parse_prefer_header_return, ExecuteReturnPreference
from weaver.formats import ContentType, get_format, repr_json
from weaver.owsexceptions import OWSNoApplicableCode, OWSNotFound
from weaver.processes.constants import JobInputsOutputsSchema
from weaver.processes.convert import any2wps_literal_datatype, convert_output_params_schema, get_field
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import (
    data2str,
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
    make_link_header,
)
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.utils import resolve_process_tag
from weaver.wps_restapi.providers.utils import forbid_local_only

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

    from weaver.execute import AnyExecuteResponse, AnyExecuteTransmissionMode
    from weaver.processes.constants import JobInputsOutputsSchemaType
    from weaver.typedefs import (
        AnyDataStream,
        AnyHeadersContainer,
        AnyRequestType,
        AnyResponseType,
        AnySettingsContainer,
        AnyUUID,
        AnyValueType,
        ExecutionResultArray,
        ExecutionResultObject,
        ExecutionResults,
        ExecutionResultValue,
        HeadersTupleType,
        HeadersType,
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


def get_schema_query(schema, strict=True):
    # type: (Optional[JobInputsOutputsSchemaType], bool) -> Optional[JobInputsOutputsSchemaType]
    if not schema:
        return None
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


def make_result_link(result_id, result, job_id, settings):
    # type: (str, Union[ExecutionResultObject, ExecutionResultArray], AnyUUID, SettingsType) -> List[str]
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
            loc = os.path.join(str(job_id), f"{result_id}{suffix}.txt")
            url = f"{wps_url}/{loc}"
            path = os.path.join(out, loc)
            path = get_secure_path(path)
            with open(path, mode="w", encoding=enc) as out_file:
                out_file.write(val)
        else:
            fmt = get_field(result, "format", default={"mediaType": ContentType.TEXT_PLAIN})
            typ = get_field(fmt, "mime_type", search_variations=True, default=ContentType.TEXT_PLAIN)
            enc = get_field(fmt, "encoding", search_variations=True, default=None)
            url = get_any_value(value, data=False, file=True)  # should already include full path
            if fmt == ContentType.TEXT_PLAIN and not enc:  # only if text, otherwise binary content could differ
                enc = "UTF-8"  # default both omit/empty
        link_header = make_link_header(url, rel=f"{result_id}{suffix}", type=typ, charset=enc)
        links.append(link_header)
    return links


def get_results(  # pylint: disable=R1260
    job,                                # type: Job
    container,                          # type: AnySettingsContainer
    value_key=None,                     # type: Optional[str]
    schema=JobInputsOutputsSchema.OLD,  # type: Optional[JobInputsOutputsSchemaType]
    link_references=False,              # type: bool
    convert_output_transmission=False,  # type: bool
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
    :param convert_output_transmission:
        If disabled (default), data/link representation preserves original results as per their literal/complex type.
        If enabled, an output that was requested as reference will be converted as an :term:`URL`, whereas
        an output requested by value will be converted to its literal contents, both as needed according to
        their original results literal/complex type.
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
        res_multi = len(array) > 1
        for val_idx, val_item in enumerate(array):
            val_data = val_item
            if isinstance(val_item, dict) and isinstance(value, list):
                rtype = "href" if get_any_value(val_item, key=True, file=True, data=False) else "data"
                val_data = get_any_value(val_item, file=True, data=False)
            if not isinstance(val_item, dict):
                # use the representation that contains all metadata if possible, otherwise rely on literal data only
                val_item = result if isinstance(result, dict) else {rtype: val_data}

            out_key = rtype
            is_ref = rtype == "href"
            out_mode = get_job_output_transmission(job, out_id, is_reference=is_ref)
            as_ref = link_references and out_mode == ExecuteTransmissionMode.REFERENCE
            res_id = f"{out_id}{val_idx}" if res_multi else out_id

            # on-demand convertion to requested transmission mode
            if convert_output_transmission:
                res_hdr, val_data = generate_or_resolve_result(job, val_item, res_id, out_id, out_mode, settings)
                if val_data is not None and is_ref:     # data generated from reference
                    is_ref = as_ref = False
                    out_key = value_key or "data"       # OGC schema overrides after as needed
                elif val_data is None and not is_ref:   # reference generated from data
                    is_ref = as_ref = True
                    out_key = "href"
                    val_data = res_hdr["Content-Location"]

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
    headers = []
    for out_id, output in references.items():
        res_links = make_result_link(out_id, output, job.id, settings)
        headers.extend([("Link", link) for link in res_links])

    return outputs, headers


def get_job_return(job=None, body=None, headers=None):
    # type: (Optional[Job], Optional[JSON], Optional[AnyHeadersContainer]) -> AnyExecuteResponse
    """
    Obtain the :term:`Job` result representation based on the resolution order of preferences and request parameters.

    Body and header parameters are considered first, in case they provide 'overrides' for the active request.
    Then, if the :paramref:`job` was already parsed from the original request, and contains pre-resolved return,
    this format is employed. When doing the initial parsing, ``job=None`` MUST be used.
    """
    body = body or {}
    resp = ExecuteResponse.get(body.get("response"))
    if resp:
        return resp

    pref = parse_prefer_header_return(headers)
    if pref == ExecuteReturnPreference.MINIMAL:
        return ExecuteResponse.DOCUMENT
    if pref == ExecuteReturnPreference.REPRESENTATION:
        return ExecuteResponse.RAW

    if not job:
        return ExecuteResponse.DOCUMENT
    return job.execution_response


def get_job_output_transmission(job, output_id, is_reference):
    # type: (Job, str, bool) -> AnyExecuteTransmissionMode
    """
    Obtain the requested :term:`Job` output ``transmissionMode``.
    """
    outputs = job.outputs or {}
    outputs = convert_output_params_schema(outputs, JobInputsOutputsSchema.OGC)
    out = outputs.get(output_id) or {}
    mode = out.get("transmissionMode")
    # because mode can be omitted, resolve their default explicitly
    if not mode and is_reference:
        return ExecuteTransmissionMode.REFERENCE
    if not mode and not is_reference:
        return ExecuteTransmissionMode.VALUE
    return cast("AnyExecuteTransmissionMode", mode)


def get_job_results_response(
    job,                        # type: Job
    container,                  # type: AnySettingsContainer
    *,                          # type: Any
    headers=None,               # type: Optional[AnyHeadersContainer]
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
    :param headers: Additional headers to provide in the response.
    :param results_headers: Headers that override originally submitted job parameters when requesting results.
    :param results_contents: Body contents that override originally submitted job parameters when requesting results.
    """
    raise_job_dismissed(job, container)
    raise_job_bad_status(job, container)

    # when 'response=document', ignore 'transmissionMode=value|reference', respect it when 'response=raw'
    # resolution of 'transmissionMode' for document representation will be done by its own handler function
    # See:
    #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#_response_7 (/req/core/job-results-async-document)
    #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-document
    is_raw = get_job_return(job, results_contents, results_headers) == ExecuteResponse.RAW
    # when multipart is requested explicitly, do NOT use 'link_references' at this point
    # this is to simplify multipart content generation by grouping everything under a single 'results' container
    is_accept_multipart = (
        isinstance(job.accept_type, str) and
        any(ctype in job.accept_type for ctype in ContentType.ANY_MULTIPART)
    )
    results, refs = get_results(
        job, container, value_key="value",
        schema=JobInputsOutputsSchema.OGC,  # not strict to provide more format details
        link_references=is_raw and not is_accept_multipart,
        convert_output_transmission=is_raw and not is_accept_multipart,
    )

    headers = ResponseHeaders(headers or {})
    headers.pop("Location", None)
    headers.setdefault("Content-Location", job.results_url(container))
    for link in job.links(container, self_link="results"):
        link_header = make_link_header(link)
        headers.add("Link", link_header)

    if not is_raw and not is_accept_multipart:
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

        # use deserialized contents such that only the applicable fields remain
        # (simplify compares, this is assumed by the following call)
        results_json = get_job_results_document(job, results_json, container=container)
        headers.extend(refs)
        return HTTPOk(json=results_json, headers=headers)

    if not results:  # avoid schema validation error if all by reference
        # Status code 204 for empty body
        # see:
        #   - https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-ref
        headers.extend(refs)
        return HTTPNoContent(headers=headers)

    # raw response can be data-only value, link-only or a mix of them
    if results:
        # https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-value-one
        out_vals = list(results.items())  # type: List[Tuple[str, ExecutionResultValue]]  # noqa
        out_info = out_vals[0][-1]        # type: ExecutionResultValue
        out_type = get_any_value(out_info, key=True)
        out_data = get_any_value(out_info)

        # multipart response
        if (
            len(results) > 1 or
            (isinstance(out_data, list) and len(out_data) > 1) or
            is_accept_multipart
        ):
            return get_job_results_multipart(job, results, headers=headers, container=container)

        # single value only
        out_data = out_data[0] if isinstance(out_data, list) else out_data
        if out_type == "href":
            out_path = map_wps_output_location(out_data, container, exists=True, url=False)
            out_type = out_info.get("type")  # noqa
            out_headers = get_href_headers(out_path, download_headers=True, content_headers=True, content_type=out_type)
            resp = FileResponse(out_path)
            resp.headers.update(out_headers)
            resp.headers.update(headers)
        else:
            resp = HTTPOk(body=out_data, charset="UTF-8", content_type=ContentType.TEXT_PLAIN, headers=headers)
    else:
        resp = HTTPOk(headers=headers)
    if refs:
        # https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-ref
        # https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-mixed-multi
        resp.headerlist.extend(refs)
    return resp


def generate_or_resolve_result(
    job,            # type: Job
    result,         # type: ExecutionResultObject
    result_id,      # type: str
    output_id,      # type: str
    output_mode,    # type: AnyExecuteTransmissionMode
    settings,       # type: SettingsType
):                  # type: (...) -> Tuple[HeadersType, Optional[AnyDataStream]]
    """
    Obtains the local file path and the corresponding :term:`URL` reference for a given result, generating it as needed.

    :param job: Job with results details.
    :param result: The specific output value or reference (could be an item index within an array of a given output).
    :param result_id: Specific identifier of the result, including any array index as applicable.
    :param output_id: Generic identifier of the output containing the result.
    :param output_mode: Desired output transmission mode.
    :param settings: Application settings to resolve locations.
    :return:
        Resolved headers and data (as applicable) for the result.
        If only returned by reference, ``None`` data is returned. An empty-data contents would be an empty string.
        Therefore, the explicit check of ``None`` is important to identify a by-reference result.
    """
    key = get_any_value(result, key=True)
    val = get_any_value(result)
    cid = f"{result_id}@{job.id}"
    url = None
    loc = None
    typ = None
    res_data = None
    c_length = None
    is_val = key in ["value", "data"]
    is_ref = key in ["href", "reference"]

    # NOTE:
    #   work with local files (since we have them), to avoid unnecessary loopback request
    #   then, rewrite the locations after generating their headers to obtain the final result URL

    # FIXME: Handle S3 output storage. Should multipart response even be allowed in this case?

    if is_ref:
        url = val
        typ = result.get("type") or ContentType.APP_OCTET_STREAM
        loc = map_wps_output_location(val, settings, exists=True, url=False)
        # FIXME: fails if output path is the "relative" results '/{jobID}/...'

    if not url:
        out_dir = get_wps_output_dir(settings)
        out_name = f"{result_id}.txt"
        job_path = job.result_path(output_id=output_id, file_name=out_name)
        loc = os.path.join(out_dir, job_path)
        url = map_wps_output_location(loc, settings, exists=False, url=True)

    if is_val:
        res_data = io.StringIO()
        c_length = res_data.write(data2str(val))
        typ = result.get("mediaType") or ContentType.TEXT_PLAIN

    if is_val and output_mode == ExecuteTransmissionMode.REFERENCE:
        if not os.path.isfile(loc):
            os.makedirs(os.path.dirname(loc), exist_ok=True)
            with open(loc, mode="w", encoding="utf-8") as out_file:
                out_file.write(val)

    if is_ref and output_mode == ExecuteTransmissionMode.VALUE:
        res_data = io.FileIO(loc, mode="rb")

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
    if not os.path.exists(loc):
        res_headers.pop("Content-Location", None)
    return res_headers, res_data


def get_job_results_document(job, results, *, container):
    # type: (Job, ExecutionResults, Any, AnySettingsContainer) -> ExecutionResults
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
    settings = get_settings(container)

    def make_result(result, result_id, output_id):
        # type: (ExecutionResultValue, str, str) -> Union[AnyValueType, ExecutionResultObject]
        if isinstance(result, dict):
            key = get_any_value(result, key=True)
            val = get_any_value(result)
        else:
            key = "value"
            val = result
            result = {"value": val}
        mode = get_job_output_transmission(job, result_id, is_reference=(key == "href"))
        headers, data = generate_or_resolve_result(job, result, result_id, output_id, mode, settings)
        if data is None:
            ref = {
                "href": headers["Content-Location"],
                "type": headers["Content-Type"],
            }
            return ref

        c_type = headers.get("Content-Type") or ""
        c_enc = headers.get("Content-Encoding")
        if not c_type or (
            # note:
            #   Explicit content-type check to consider that any additional parameter provided
            #   with text/plain must be reported. Only "purely" plain/text can be removed.
            c_type == ContentType.TEXT_PLAIN and not c_enc
        ):
            value = val  # use original to avoid string conversion
        else:
            value = {
                "value": data2str(data),
                "mediaType": c_type,
            }
            if c_enc:
                value["encoding"] = c_enc
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


def get_job_results_multipart(job, results, *, headers, container):
    # type: (Job, ExecutionResults, Any, AnyHeadersContainer, AnySettingsContainer) -> HTTPOk
    """
    Generates the :term:`Job` results multipart response from available or requested outputs with necessary conversions.

    .. seealso::
        - Function :func:`get_results` should be used to avoid re-processing all output format combinations.
        - Details of ``multipart`` (:rfc:`2046#section-5.1`) :term:`Media-Type` family.

    :param job: Job definition with potential metadata about requested outputs.
    :param results: Pre-filtered and pre-processed results in a normalized format structure.
    :param headers: Additional headers to include in the response.
    :param container: Application settings to resolve locations.
    """
    settings = get_settings(container)

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

            key = get_any_value(result, key=True)
            mode = get_job_output_transmission(job, out_id, is_reference=(key == "href"))
            res_headers, res_data = generate_or_resolve_result(job, result, res_id, out_id, mode, settings)
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

    body["description"] = sd.CreatedLaunchJobResponse.description
    body = sd.CreatedJobStatusSchema().deserialize(body)
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
        # must use OWS instead of HTTP class to preserve provided JSON body
        # otherwise, pyramid considers it as not found view/path and rewrites contents in append slash handler
        raise OWSNotFound(json={
            "title": "JobResultsNotReady",
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/result-not-ready",
            "detail": "Job is not ready to obtain results.",
            "status": HTTPNotFound.code,
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
