import base64
import gzip
import json
import logging
import math
import urllib.parse
from typing import TYPE_CHECKING

from typing_extensions import get_args

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPOk, HTTPUnprocessableEntity
from pyramid.settings import asbool

from weaver.compat import InvalidVersion
from weaver.config import WeaverFeature, get_weaver_configuration
from weaver.database import get_db
from weaver.formats import ContentType, OutputFormat, clean_media_type_format, guess_target_format
from weaver.ogc_definitions import normalize as normalize_ogc_uri
from weaver.store.base import StoreProcesses
from weaver.typedefs import MetadataQueryScope, PreferHeaderHandling
from weaver.utils import get_header, get_path_kvp, get_settings, make_link_header
from weaver.visibility import Visibility
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Dict, List, Optional, Tuple

    from weaver.datatype import Process, Service
    from weaver.typedefs import AnyViewResponse, JSON, PyramidRequest

LOGGER = logging.getLogger(__name__)


def resolve_process_tag(request, process_query=False):
    # type: (PyramidRequest, bool) -> str
    """
    Obtain the tagged :term:`Process` reference from request path and/or query according to available information.

    Whether the :term:`Process` is specified by path or query, another ``version`` query can be provided to specify
    the desired revision by itself. This ``version`` query is considered only if another version indication is not
    already specified in the :term:`Process` reference using the tagged semantic.

    When ``process_query = False``, possible combinations are as follows:

    - ``/processes/{processID}:{version}``
    - ``/processes/{processID}?version={version}``

    When ``process_query = True``, possible combinations are as follows:

    - ``/...?process={processID}:{version}``
    - ``/...?process={processID}&version={version}``

    :param request: Request from which to retrieve the process reference.
    :param process_query: Whether the process ID reference is located in request path or ``process={id}`` query.
    """
    if process_query:
        process_id = request.params.get("process")
    else:
        process_id = request.matchdict.get("process_id", "")
    params = sd.LocalProcessQuery().deserialize(request.params)
    version = params.get("version")
    if version and ":" not in process_id:  # priority to tagged version over query if specified
        process_id = f"{process_id}:{version}"
    process_id = sd.ProcessIdentifierTag(name="ProcessID").deserialize(process_id)
    return process_id


def get_processes_filtered_by_valid_schemas(request, detail=True, links=True):
    # type: (PyramidRequest, bool, bool) -> Tuple[List[JSON], List[str], Dict[str, Optional[int]], bool, int]
    """
    Validates the processes summary schemas and returns them into valid/invalid lists.

    :returns: List of valid process and invalid processes IDs for manual cleanup, along with filtering parameters.
    """
    settings = get_settings(request)
    with_providers = False
    if get_weaver_configuration(settings) in WeaverFeature.REMOTE:
        with_providers = asbool(request.params.get("providers", False))
    revisions_param = sd.ProcessRevisionsQuery(unknown="ignore").deserialize(request.params)
    with_revisions = revisions_param.get("revisions")
    with_links = links and detail
    paging_query = sd.ProcessPagingQuery()
    paging_value = {param.name: param.default for param in paging_query.children}
    paging_names = set(paging_value)
    paging_param = paging_query.deserialize(request.params)
    if with_providers and any(value != paging_value[param] for param, value in paging_param.items()):
        raise HTTPBadRequest(json={
            "description": "Cannot combine paging/sorting parameters with providers full listing query.",
            "error": "ListingInvalidParameter",
            "value": list(paging_names.intersection(request.params))
        })

    metadata_filters = parse_metadata_query_filters(request)
    store = get_db(request).get_store(StoreProcesses)
    processes, total_local_processes = store.list_processes(
        visibility=Visibility.PUBLIC,
        total=True,
        metadata=metadata_filters,
        **revisions_param,
        **paging_param
    )
    valid_processes = []
    invalid_processes_ids = []
    for process in processes:  # type: Process
        try:
            try:
                valid_processes.append(process.summary(revision=with_revisions, links=with_links, container=request))
            except (InvalidVersion, ValueError) as exc:
                raise colander.Invalid(sd.ProcessSummary, value=None, msg=str(exc))
        except colander.Invalid as invalid:
            process_ref = process.tag if with_revisions else process.identifier
            LOGGER.debug("Invalid process [%s] because:\n%s", process_ref, invalid)
            invalid_processes_ids.append(process.identifier)
    return valid_processes, invalid_processes_ids, paging_param, with_providers, total_local_processes


def resolve_metadata_query_uri(value, instance):
    # type: (str, str) -> str
    """
    Validates and resolves a ``role``/``profile`` reference (`IRI`, `URN` or Safe :term:`CURIE`) to its long-form `URI`.

    Relies on :func:`weaver.ogc_definitions.normalize` as the authority for :term:`CURIE`/`URN` resolution. An
    absolute `IRI` is returned as-is. Any other value left unresolved (unchanged, or not an `IRI`) by that utility
    is considered an invalid or unresolvable reference.

    :raises HTTPBadRequest: If ``value`` is empty or contains whitespace (not a valid `IRI`/`URN`/Safe :term:`CURIE`).
    :raises HTTPUnprocessableEntity: If ``value`` has valid syntax, but its :term:`CURIE` prefix is unresolvable.
    """
    if value.startswith(("http://", "https://")):
        return value
    if not value or " " in value:
        raise HTTPBadRequest(json={
            "type": sd.OGC_API_PROC_PART5_EXC_INVALID_METADATA_PROFILE_URI,
            "title": "Invalid metadata query reference.",
            "detail": "Query parameter 'metadata[<role>]' role/profile must be a valid IRI, URN or Safe CURIE.",
            "status": HTTPBadRequest.code,
            "instance": instance,
        })
    resolved = normalize_ogc_uri(value)
    if resolved == value or not resolved.startswith(("http://", "https://")):
        raise HTTPUnprocessableEntity(json={
            "type": sd.OGC_API_PROC_PART5_EXC_UNSUPPORTED_METADATA_PROFILE_URI,
            "title": "Unsupported metadata query reference.",
            "detail": "Query parameter 'metadata[<role>]' role/profile CURIE prefix could not be resolved.",
            "status": HTTPUnprocessableEntity.code,
            "instance": instance,
        })
    return resolved


_METADATA_QUERY_SCOPES = get_args(MetadataQueryScope)


def decode_compressed_metadata_query(value):
    # type: (str) -> JSON
    """
    Decodes a ``base64url(gzip(<QUERY content>))`` compacted/encoded single-value ``metadata`` query parameter.

    .. seealso::
        ``/req/metadata-profiles/query-compression``

    :raises HTTPBadRequest: If the value cannot be decoded, decompressed or parsed as JSON ``QUERY`` content.
    :returns: Decoded ``QUERY`` content (``{"process": {role: [profile, ...]}, "inputs": {...}, "outputs": {...}}``).
    """
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        if raw[:2] != b"\x1f\x8b":  # gzip magic number
            raise ValueError("Missing gzip magic number.")
        content = json.loads(gzip.decompress(raw))
        if not isinstance(content, dict) or not set(content).issubset(_METADATA_QUERY_SCOPES):
            raise ValueError("Invalid 'QUERY' content structure.")
    except Exception as exc:
        raise HTTPBadRequest(json={
            "type": sd.OGC_API_PROC_PART5_EXC_INVALID_METADATA_PROFILE_URI,
            "title": "Invalid metadata query parameter.",
            "detail": f"Compacted 'metadata' query parameter could not be decoded, decompressed or parsed: {exc}",
            "status": HTTPBadRequest.code,
            "instance": "metadata",
        }) from exc
    return content


def get_metadata_query_bracket_handling(request):
    # type: (PyramidRequest) -> PreferHeaderHandling
    """
    Resolves the lenient/strict handling of literal (non-percent-encoded) brackets in ``metadata`` query parameters.

    A client can request the ``strict`` handling (refusing literal ``[``/``]`` characters, accepting only their
    percent-encoded ``%5B``/``%5D`` form) using the ``Prefer: handling=strict`` request header
    (:rfc:`7240`, Section 4.4), as per ``/per/metadata-profiles/query-literal-brackets``. Any other (or missing)
    value defaults to the ``lenient`` handling (literal brackets accepted).

    :returns: Either ``"strict"`` or ``"lenient"`` (:data:`weaver.typedefs.PreferHeaderHandling`).
    """
    lenient, strict = get_args(PreferHeaderHandling)
    prefer = request.headers.get("Prefer", "")
    for pref in prefer.split(","):
        key, _, value = pref.strip().partition("=")
        if key.strip().lower() == "handling" and value.strip().strip('"').lower() == strict:
            return strict
    return lenient


def parse_metadata_query_filters(request):
    # type: (PyramidRequest) -> List[Tuple[MetadataQueryScope, str, str]]
    """
    Parses ``metadata[<scope>][<role>]=<profile>`` query parameters used to filter process listing by metadata.

    The ``<scope>`` must be one of ``process``, ``inputs`` or ``outputs``, indicating respectively whether the
    ``<role>``/``<profile>`` must be matched against a ``metadata`` entry of the process itself, or of at least one
    of its inputs (respectively outputs). Both ``<role>`` and ``<profile>`` can be provided as `IRI`, `URN` or Safe
    :term:`CURIE`, and are resolved to their long-form `URI` using :func:`weaver.ogc_definitions.normalize` for
    consistent matching against stored metadata. Multiple ``<profile>`` for the same ``<role>`` can be supplied as
    comma-separated values, or using repeated query parameters, and must ALL be matched (logical AND). Only
    ``metadata`` entries that are profile links (``rel`` set to
    :data:`weaver.wps_restapi.swagger_definitions.OGC_API_PROC_PART5_METADATA_PROFILE_REL_URI`) are considered
    for the ``<role>``/``<profile>`` matching, as per ``/req/metadata-profiles/profile-link``. When ``<role>``
    is itself a Safe :term:`CURIE`, it is provided with doubled brackets in the parameter name
    (e.g., ``metadata[outputs][[ogc-profile:data-type]]``), since the outer brackets delimit the ``deepObject``
    key, and the inner ones belong to the Safe CURIE, as per ``/req/metadata-profiles/query-curie-matching``.

    By default (``lenient`` handling), literal (non-percent-encoded) ``[``/``]`` characters are accepted in the
    ``metadata`` query parameter names/values, even though :rfc:`3986` (Section 3.4) disallows them in the query
    component. A client requesting the ``Prefer: handling=strict`` request header
    (see :func:`get_metadata_query_bracket_handling`) instead requires all brackets to be percent-encoded
    (``%5B``/``%5D``), as per ``/per/metadata-profiles/query-literal-brackets`` and
    ``/rec/metadata-profiles/query-literal-brackets-error``.

    Alternatively, a single ``metadata`` query parameter (not using the ``metadata[<scope>][<role>]`` form) is
    interpreted as a `base64url`-encoded, `gzip`-compressed `JSON` ``QUERY`` content representation, as defined by
    ``/req/metadata-profiles/query-compression``, of the equivalent ``{"process": {<role>: [<profile>, ...]}}``
    (and/or ``inputs``/``outputs``) filter structure.

    .. seealso::
        OGC API - Processes - Part 5: Provenance and Profiles (``metadata-profiles`` conformance class).

    :raises HTTPBadRequest: If a ``<scope>`` is not one of the supported values, or ``<role>``/``<profile>`` is not
        a valid `IRI`/`URN`/Safe :term:`CURIE`, or the compacted/encoded ``metadata`` value cannot be processed, or
        the ``strict`` handling is requested and literal brackets are found in the raw query string.
    :raises HTTPUnprocessableEntity: If a ``<role>``/``<profile>`` Safe :term:`CURIE` prefix cannot be resolved.
    :returns: List of resolved ``(scope, role, profile)`` filters to be matched against process ``metadata`` entries.
    """
    bracket_handling = get_metadata_query_bracket_handling(request)
    request.metadata_bracket_handling = bracket_handling
    _, strict_mode = get_args(PreferHeaderHandling)
    if bracket_handling == strict_mode:
        raw_query = request.query_string or ""
        for raw_param in raw_query.split("&"):
            raw_key = raw_param.split("=", 1)[0]
            if raw_key.startswith("metadata") and ("[" in raw_key or "]" in raw_key):
                raise HTTPBadRequest(json={
                    "type": sd.OGC_API_PROC_PART5_EXC_INVALID_METADATA_PROFILE_URI,
                    "title": "Invalid metadata query parameter.",
                    "detail": (
                        "Literal brackets are not accepted under the 'strict' handling preference. "
                        "Percent-encode '[' and ']' as '%5B' and '%5D'."
                    ),
                    "status": HTTPBadRequest.code,
                    "instance": raw_key,
                })
    filters = []
    for key, values in request.params.dict_of_lists().items():
        if key == "metadata":
            content = decode_compressed_metadata_query(values[0])
            for scope, role_profiles in content.items():
                for role, profiles in role_profiles.items():
                    role = resolve_metadata_query_uri(role, key)
                    for profile in (profiles if isinstance(profiles, list) else [profiles]):
                        filters.append((scope, role, resolve_metadata_query_uri(profile, key)))
            continue
        if not (key.startswith("metadata[") and key.endswith("]")):
            continue
        scope_role = key[len("metadata["):-1]
        scope, _, role = scope_role.partition("][")
        if not role or scope not in _METADATA_QUERY_SCOPES:
            raise HTTPBadRequest(json={
                "type": sd.OGC_API_PROC_PART5_EXC_INVALID_METADATA_PROFILE_URI,
                "title": "Invalid metadata query parameter.",
                "detail": f"Query parameter '{key}' must be of form 'metadata[process|inputs|outputs][<role>]'.",
                "status": HTTPBadRequest.code,
                "instance": key,
            })
        role = resolve_metadata_query_uri(role, key)
        for value in values:
            for profile in value.split(","):
                profile = resolve_metadata_query_uri(profile, key)
                filters.append((scope, role, profile))
    return filters


def get_process_list_links(request, paging, total, provider=None):
    # type: (PyramidRequest, Dict[str, int], Optional[int], Optional[Service]) -> List[JSON]
    """
    Obtains a list of all relevant links for the corresponding :term:`Process` listing defined by query parameters.

    :raises IndexError: if the paging values are out of bounds compared to available total :term:`Process`.
    """
    # reapply queries that must be given to obtain the same result in case of subsequent requests (sort, limits, etc.)
    kvp_params = {param: value for param, value in request.params.items() if param != "page"}
    base_url = get_wps_restapi_base_url(request)
    links = []
    if provider:
        proc_path = sd.provider_processes_service.path.format(provider_id=provider.id)
        links.extend(provider.links(request, self_link="provider"))
    else:
        proc_path = sd.processes_service.path
    proc_url = base_url + proc_path
    req_fmt, req_src = guess_target_format(request, default=ContentType.APP_JSON, return_source=True)
    req_params = dict(request.params)
    if req_src == "header":
        req_fmt = clean_media_type_format(req_fmt)
        req_params["f"] = OutputFormat.get(req_fmt)
    links.extend([
        {"href": proc_url, "rel": "collection",
         "type": ContentType.APP_JSON, "title": "Process listing (no filtering queries applied)."},
        {"href": proc_url, "rel": "search",
         "type": ContentType.APP_JSON, "title": "Generic query endpoint to list processes."},
        {"href": f"{proc_url}?detail=false", "rel": "preview",
         "type": ContentType.APP_JSON, "title": "Process listing summary (identifiers and count only)."},
        {"href": f"{proc_url}?f=json", "rel": "http://www.opengis.net/def/rel/ogc/1.0/processes",
         "type": ContentType.APP_JSON, "title": "List of registered local processes."},
        {"href": f"{proc_url}?{urllib.parse.urlencode(req_params)}", "rel": "self",
         "type": req_fmt, "title": "Current process listing."},
    ])
    if provider:
        prov_url = proc_url.rsplit("/", 1)[0]
        links.append({"href": prov_url, "rel": "up", "type": ContentType.APP_JSON, "title": "Provider description."})
    else:
        links.extend([
            {"href": sd.OGC_API_PROC_PROFILE_PROC_LIST_URI, "rel": "profile", "title": "Process listing profile."},
            {"href": f"{base_url}/", "rel": "up", "type": ContentType.APP_JSON, "title": "API entrypoint."}
        ])

    cur_page = paging.get("page", None)
    per_page = paging.get("limit", None)
    if all(isinstance(num, int) for num in [cur_page, per_page, total]):
        max_page = max(math.ceil(total / per_page) - 1, 0)
        if cur_page < 0 or cur_page > max_page:
            raise IndexError(f"Page index {cur_page} is out of range from [0,{max_page}].")
        links.extend([
            {"href": get_path_kvp(proc_url, page=cur_page, **kvp_params), "rel": "current",
             "type": ContentType.APP_JSON, "title": "Current page of processes query listing."},
            {"href": get_path_kvp(proc_url, page=0, **kvp_params), "rel": "first",
             "type": ContentType.APP_JSON, "title": "First page of processes query listing."},
            {"href": get_path_kvp(proc_url, page=max_page, **kvp_params), "rel": "last",
             "type": ContentType.APP_JSON, "title": "Last page of processes query listing."},
        ])
        if cur_page > 0:
            links.append({
                "href": get_path_kvp(proc_url, page=cur_page - 1, **kvp_params), "rel": "prev",
                "type": ContentType.APP_JSON, "title": "Previous page of processes query listing."
            })
        if cur_page < max_page:
            links.append({
                "href": get_path_kvp(proc_url, page=cur_page + 1, **kvp_params), "rel": "next",
                "type": ContentType.APP_JSON, "title": "Next page of processes query listing."
            })
    process = kvp_params.get("process")
    if process and ":" not in str(process):
        proc_hist = f"{proc_url}?detail=false&revisions=true&process={process}"
        proc_desc = f"{proc_url}/{process}"
        links.extend([
            {"href": proc_desc, "rel": "latest-version",
             "type": ContentType.APP_JSON, "title": "Most recent revision of this process."},
            {"href": proc_hist, "rel": "version-history",
             "type": ContentType.APP_JSON, "title": "Listing of all revisions of this process."},
        ])
    return links


def get_process_package_response(request, process):
    # type: (PyramidRequest, Process) -> AnyViewResponse
    """
    Resolve the specific :term:`Application Package` response representation based on negotiated request contents.

    :param request: Request to resolve negotiated contents.
    :param process: Specific :term:`Process` reference, either local or via remote :term:`Provider`.
    :returns: Resolved packaged representation.
    """
    content_type = get_header("Accept", request.headers, default=ContentType.APP_CWL_JSON)
    # ignore default browser request injecting HTML
    # ignore 'weaver.wps_restapi_html_override_user_agent' as well since HTML cannot apply here
    if all(ctype in content_type for ctype in [ContentType.TEXT_HTML, ContentType.ANY]):
        content_type = ContentType.APP_CWL_JSON
    headers = {
        "Link": make_link_header(sd.CWL_SCHEMA_URL, rel="profile", type=ContentType.APP_YAML),
        "Content-Schema": sd.CWL_SCHEMA_URL,
        "Content-Profile": sd.CWL_SCHEMA_URL,
    }
    yml_fmt = [ContentType.APP_YAML, ContentType.APP_CWL_YAML]
    cwl_fmt = OutputFormat.YAML if any(ctype in content_type for ctype in yml_fmt) else OutputFormat.JSON
    package = OutputFormat.convert(process.package, cwl_fmt)
    content = {"json": package} if cwl_fmt == OutputFormat.JSON else {"body": package}
    content = content if package else {}
    return HTTPOk(headers=headers, content_type=content_type, charset="utf-8", **content)
