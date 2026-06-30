import copy
import json
import logging
import os
import pathlib
import warnings
from copy import deepcopy
from email import message_from_bytes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urljoin, urlparse

import colander
import docker
import yaml
from docker.errors import ImageNotFound  # pylint: disable=E0611
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPCreated,
    HTTPException,
    HTTPForbidden,
    HTTPNotFound,
    HTTPNotImplemented,
    HTTPOk,
    HTTPUnprocessableEntity,
    HTTPUnsupportedMediaType
)
from pyramid.settings import asbool

from weaver.compat import Version
from weaver.config import (
    WEAVER_CONFIG_DIR,
    WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
    WeaverFeature,
    get_weaver_config_file,
    get_weaver_configuration
)
from weaver.database import get_db
from weaver.datatype import DockerAuthentication, Process, Service
from weaver.exceptions import (
    InvalidIdentifierValue,
    MissingIdentifierValue,
    PackageNotFound,
    PackageRegistrationError,
    PackageTypeError,
    ProcessNotAccessible,
    ProcessNotFound,
    ProcessRegistrationError,
    ServiceNotFound,
    log_unhandled_exceptions
)
from weaver.formats import ContentType, repr_json
from weaver.processes.constants import PACKAGE_EXTENSIONS
from weaver.processes.convert import get_field, normalize_ordered_io, set_field
from weaver.processes.types import ProcessType
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import (
    VersionFormat,
    VersionLevel,
    as_version_major_minor_patch,
    fully_qualified_name,
    generate_diff,
    get_any_id,
    get_header,
    get_sane_name,
    get_settings,
    get_url_without_query,
    is_remote_file,
    is_update_version,
    load_file,
    parse_content_id,
    request_extra,
    str2bytes
)
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_client
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.utils import resolve_process_tag
from weaver.wps_restapi.utils import get_wps_restapi_base_url

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Union

    from docker.client import DockerClient

    from weaver.typedefs import (
        URL,
        AnyHeadersContainer,
        AnyRegistryContainer,
        AnyRequestType,
        AnySettingsContainer,
        AnyVersion,
        CWL,
        FileSystemPathType,
        JSON,
        Literal,
        NotRequired,
        Number,
        ProcessDeployment,
        PyramidRequest,
        SettingsType,
        TypedDict
    )
    from weaver.utils import LoggerHandler

    UpdateFieldListMethod = Literal["append", "override"]
    UpdateFieldListSpec = TypedDict("UpdateFieldListSpec", {
        "source": str,
        "target": NotRequired[str],
        "unique": NotRequired[bool],
        "method": UpdateFieldListMethod,
    }, total=True)
    UpdateFields = List[Union[str, UpdateFieldListMethod]]


def get_process(process_id=None, request=None, settings=None, store=None, revision=True):
    # type: (Optional[str], Optional[PyramidRequest], Optional[SettingsType], Optional[StoreProcesses], bool) -> Process
    """
    Obtain the specified process and validate information, returning appropriate HTTP error if invalid.

    Process identifier must be provided from either the request path definition or literal ID.
    Database must be retrievable from either the request, underlying settings, or direct store reference.

    .. versionchanged:: 4.20
        Process identifier can also be an 'id:version' tag. Also, the request query parameter 'version' can be used.
        If using the :paramref:`process_id` explicitly instead of the request, a versioned :term:`Process` reference
        MUST employ the tagged representation to resolve the appropriate :term:`Process` revision.

    Different parameter combinations are intended to be used as needed or more appropriate, such that redundant
    operations can be reduced where some objects are already fetched from previous operations.

    :param process_id: Explicit :term:`Process` identifier to employ for lookup.
    :param request: When no explicit ID specified, try to find information from the request.
    :param settings:
        Application settings for database connection. Can be guessed from local thread or request object if not given.
    :param store: Database process store reference.
    :param revision:
        When parsing the :term:`Process` ID (either explicit or from request), indicate if any tagged revision
        specifier should be used or dropped.
    """
    store = store or get_db(settings or request).get_store(StoreProcesses)
    try:
        if process_id is None and request is not None:
            process_id = resolve_process_tag(request)
        if not revision:
            process_id = Process.split_version(process_id)[0]
        process = store.fetch_by_id(process_id, visibility=Visibility.PUBLIC)
        return process
    except (InvalidIdentifierValue, MissingIdentifierValue, colander.Invalid) as exc:
        msg = getattr(exc, "msg", str(exc))
        raise HTTPBadRequest(json={
            "type": "InvalidIdentifierValue",
            "title": "Process ID is invalid.",
            "description": "Failed schema validation to retrieve process.",
            "cause": f"Invalid schema: [{msg}]",
            "error": exc.__class__.__name__,
            "value": str(process_id)
        })
    except ProcessNotAccessible:
        raise HTTPForbidden(f"Process with ID '{process_id!s}' is not accessible.")
    except ProcessNotFound:
        raise ProcessNotFound(json={
            "title": "NoSuchProcess",
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
            "detail": sd.NotFoundProcessResponse.description,
            "status": ProcessNotFound.code,
            "cause": str(process_id)
        })


def map_progress(progress, range_min, range_max):
    # type: (Number, Number, Number) -> Number
    """
    Calculates the relative progression of the percentage process within min/max values.
    """
    return max(range_min, min(range_max, range_min + (progress * (range_max - range_min)) / 100))


def get_process_information(process_description):
    # type: (JSON) -> JSON
    """
    Obtain the details for the process within its description considering various supported formats.
    """
    proc_desc = process_description.get("processDescription", {})
    if "process" in proc_desc:
        process = proc_desc.get("process", {})
        if isinstance(process, dict):  # some instance use 'process' to represent the full-URI identifier
            return process
    return proc_desc


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of deploy payload.",
                          is_request=False)
def _check_deploy(payload):
    # type: (JSON) -> Union[ProcessDeployment, CWL]
    """
    Validate minimum deploy payload field requirements with exception handling.
    """
    message = "Process deployment definition is invalid."
    try:
        results = sd.Deploy(schema_meta_include=False, schema_include=False).deserialize(payload)
        # Because many fields are optional during deployment to allow flexibility between compatible WPS/CWL
        # definitions, any invalid field at lower-level could make a full higher-level definition to be dropped.
        # Verify the result to ensure this was not the case for known cases to attempt early detection.
        p_process = payload.get("processDescription", {})
        r_process = results.get("processDescription", {})
        if "process" in p_process:
            # if process is nested, both provided/result description must align
            # don't use "get_process_information" to make sure everything is retrieved under same location
            p_process = p_process.get("process", {})
            r_process = r_process.get("process", {})
        for io_type, io_schema in [("inputs", sd.DeployInputTypeAny), ("outputs", sd.DeployOutputTypeAny)]:
            p_io = p_process.get(io_type)
            r_io = r_process.get(io_type)
            if p_io and p_io != r_io:
                message = f"Process deployment {io_type} definition is invalid."
                # try raising sub-schema to have specific reason
                d_io = io_schema(name=io_type).deserialize(p_io)
                # Raise directly if we were unable to detect the cause, but there is something incorrectly dropped.
                # Only raise if indirect vs direct deserialize differ such that auto-resolved defaults omitted from
                # submitted process I/O or unknowns fields that were correctly ignored don't cause false-positive diffs.
                if r_io != d_io:
                    message = (
                        f"Process deployment {p_io} definition resolved as valid schema "
                        f"but differ from submitted values. "
                        f"Validate provided {p_io} against resolved {p_io} with schemas "
                        f"to avoid mismatching definitions."
                    )
                    raise HTTPBadRequest(json={
                        "title": message,
                        "cause": "unknown",
                        "error": "Invalid",
                        "value": d_io
                    })
                LOGGER.warning(
                    "Detected difference between original/parsed deploy %s, but no invalid schema:\n%s",
                    io_type, generate_diff(p_io, r_io, val_name="original payload", ref_name="parsed result")
                )
        # Execution Unit is optional since process reference (e.g.: WPS-1 href) can be provided in processDescription
        # Cannot validate as CWL yet, since execution unit can also be an href that is not yet fetched (it will later)
        p_exec_unit = payload.get("executionUnit", [{}])
        r_exec_unit = results.get("executionUnit", [{}])
        if p_exec_unit and p_exec_unit != r_exec_unit:
            message = "Process deployment execution unit is invalid."
            d_exec_unit = sd.ExecutionUnitVariations(
                schema_meta_include=False,
                schema_include=False,
            ).deserialize(p_exec_unit)  # raises directly if caused by invalid schema
            if r_exec_unit != d_exec_unit:  # otherwise raise a generic error, don't allow differing definitions
                message = (
                    "Process deployment execution unit resolved as valid definition but differs from submitted "
                    "package. Aborting deployment to avoid mismatching package definitions."
                )
                raise HTTPBadRequest(json={
                    "title": message,
                    "cause": "unknown",
                    "error": PackageRegistrationError.__name__,
                    "value": d_exec_unit
                })
            LOGGER.warning(
                "Detected difference between original/parsed deploy execution unit, but no invalid schema:\n%s",
                generate_diff(p_exec_unit, r_exec_unit, val_name="original payload", ref_name="parsed result")
            )
        return results
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as exc:
        LOGGER.debug("Failed deploy body schema validation:\n%s", exc)
        raise HTTPBadRequest(json={
            "title": message,
            "detail": f"Invalid schema: [{exc.msg!s}]",
            "error": exc.__class__.__name__,
            "cause": exc.asdict(),
            "value": repr_json(exc.value),
        })


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of process definition.",
                          is_request=False)
def _validate_deploy_process_info(process_info, reference, package, settings, headers):
    # type: (JSON, Optional[str], Optional[CWL], SettingsType, Optional[AnyHeadersContainer]) -> JSON
    """
    Obtain the process definition from deploy payload with exception handling.

    .. seealso::
        - :func:`weaver.processes.wps_package.get_process_definition`
    """
    from weaver.processes.wps_package import check_package_instance_compatible, get_process_definition
    try:
        # data_source `None` forces workflow process to search locally for deployed step applications
        info = get_process_definition(
            process_info,
            reference,
            package,
            data_source=None,
            headers=headers,
            container=settings,
        )

        # validate process type and package against weaver configuration
        cfg = get_weaver_configuration(settings)
        if cfg not in WeaverFeature.REMOTE:
            problem = check_package_instance_compatible(info["package"])
            if problem:
                proc_type = info["type"]
                raise HTTPForbidden(json={
                    "description": (
                        f"Invalid process deployment of type [{proc_type}] on [{cfg}] instance. "
                        "Remote execution is required but not supported."
                    ),
                    "cause": problem
                })
        return info
    except PackageNotFound as ex:
        # raised when a workflow sub-process is not found (not deployed locally)
        raise HTTPNotFound(detail=str(ex))
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except (PackageRegistrationError, PackageTypeError) as ex:
        msg = f"Invalid package/reference definition. Loading generated error: [{ex!s}]"
        LOGGER.exception(msg)
        raise HTTPUnprocessableEntity(detail=msg)


def resolve_cwl_graph(package):
    # type: (CWL) -> Union[CWL, Tuple[List[CWL], CWL]]
    """
    Resolve :term:`CWL` ``$graph`` into deployable packages.

    :returns:
        - Single :term:`CWL` ``dict`` if no ``$graph`` or ``$graph`` with 1 item (backward compatible)
        - ``tuple`` of (``list`` of :term:`CWL` ``dict`` items, original package with ``$graph``) if multiple items

    .. seealso::
        - `crim-ca/weaver#56 <https://github.com/crim-ca/weaver/issues/56>`_
        - `CWL Packed Documents <https://www.commonwl.org/v1.2/CommandLineTool.html#Packed_documents>`_
    """
    if "$graph" not in package:
        return package

    graph_items = package.get("$graph", [])
    if not isinstance(graph_items, list):
        return package

    if len(graph_items) == 1:
        # Single item: unpack as before (backward compatible)
        cwl_base = {k: v for k, v in package.items() if k != "$graph"}
        cwl_base.update(graph_items[0])
        return cwl_base

    # Multiple items: return list with original package for workflow reference resolution
    # Each item inherits top-level fields (e.g., cwlVersion)
    cwl_base = {k: v for k, v in package.items() if k != "$graph"}
    resolved_items = []
    for item in graph_items:
        cwl_item = deepcopy(cwl_base)
        cwl_item.update(item)
        resolved_items.append(cwl_item)

    return resolved_items, package


def resolve_deployment_order(cwl_packages):
    # type: (List[CWL]) -> Tuple[List[CWL], Optional[CWL]]
    """
    Determine deployment order for multiple :term:`CWL` packages.

    :param cwl_packages: ``list`` of :term:`CWL` package definitions to order.
    :returns:
        ``tuple`` of (dependencies, main_workflow)
        - dependencies: ``list`` of ``CommandLineTool``/``ExpressionTool`` to deploy first
        - main_workflow: The main ``Workflow`` (if any) to deploy last, or ``None``
    :raises HTTPNotImplemented: If multiple ``Workflow`` definitions are provided.
    :raises HTTPBadRequest: If multiple tools without a ``Workflow`` and no ``#main`` entry point.

    .. seealso::
        - `CWL Packed Documents <https://www.commonwl.org/v1.2/CommandLineTool.html#Packed_documents>`_
    """
    workflows = []
    tools = []

    for pkg in cwl_packages:
        cwl_class = pkg.get("class", "")
        if cwl_class == "Workflow":
            workflows.append(pkg)
        elif cwl_class in ["CommandLineTool", "ExpressionTool"]:
            tools.append(pkg)

    # FIXME: Temporarily require at least one Workflow in multi-CWL deployments.
    # See: https://github.com/crim-ca/weaver/issues/171
    # If multiple sub-Workflow do not work directly, keep this limit.
    # Otherwise, allow tool-only deployments and demonstrate multi-workflow deployment.
    if len(workflows) > 1:
        raise HTTPNotImplemented(json={
            "title": "Multiple Workflow definitions in $graph.",
            "description": "Only one top-level Workflow is supported per deployment.",
            "cause": {"workflow_count": len(workflows)},
            "value": [wf.get("id") for wf in workflows]
        })

    main_tool = None
    if len(cwl_packages) > 1:
        # Check for duplicate #main if explicitly used
        main_items = [pkg for pkg in cwl_packages if pkg.get("id") == "#main"]
        if len(main_items) > 1:
            raise HTTPBadRequest(json={
                "title": "Duplicate #main entry point in $graph.",
                "description": (
                    "Only one item in $graph can have id '#main' as the entry point."
                ),
                "cause": {"main_count": len(main_items)},
                "value": [item.get("class") for item in main_items]
            })

        # If Workflow exists, it's the main entry point (regardless of #main designation)
        if len(workflows) > 0:
            main_tool = None
        elif len(tools) > 1:
            # Multiple tools without Workflow: NOT ALLOWED (even with #main)
            main_tool_found = next((t for t in tools if t.get("id") == "#main"), None)
            raise HTTPBadRequest(json={
                "title": "No entry point in $graph.",
                "description": (
                    "Multi-CWL deployment with multiple tools requires a Workflow as the entry point, "
                    "according to CWL packed document specification. Multiple CommandLineTools or "
                    "ExpressionTools without a Workflow are not supported, even with #main designation."
                ),
                "cause": {"workflow_count": 0, "tool_count": len(tools), "main_found": bool(main_tool_found)},
                "value": [tool.get("id") for tool in tools]
            })
        elif len(tools) == 1:
            # Single tool: it's implicitly the main entry point
            main_tool = tools[0]

    main_workflow = workflows[0] if workflows else main_tool
    return tools, main_workflow


def resolve_multi_execution_units(execution_units):
    # type: (List[JSON]) -> List[CWL]
    """
    Extract all :term:`CWL` packages from multiple execution units.

    Each execution unit can contain either an inline package (``unit``) or a reference (``href``)
    to fetch the package from a remote location.

    :param execution_units:
        ``list`` of execution unit definitions.
        Each unit must have exactly one of ``unit`` or ``href`` (enforced by schema validation).
    :returns: ``list`` of resolved :term:`CWL` package definitions.
    :raises HTTPBadRequest: If unable to fetch a remote execution unit reference.
    """
    packages = []
    for idx, execution_unit in enumerate(execution_units):
        unit_package = execution_unit.get("unit")
        unit_reference = execution_unit.get("href")

        if unit_package:
            packages.append(unit_package)
        elif unit_reference:
            try:
                # To avoid circular dependencies
                from weaver.processes.wps_package import _generate_process_with_cwl_from_reference
                cwl_pkg, _ = _generate_process_with_cwl_from_reference(unit_reference)
                packages.append(cwl_pkg)
            except Exception as exc:
                raise HTTPBadRequest(json={
                    "title": "Failed to fetch execution unit reference",
                    "description": f"Could not retrieve CWL from href at index {idx}: {unit_reference}",
                    "cause": {"error": str(exc), "href": unit_reference, "index": idx}
                })

    return packages


def _get_multipart_content(content, request):
    # type: (Union[str, bytes], Optional[AnyRequestType]) -> bytes
    """
    Get raw multipart content as ``bytes``.    """
    if request is not None and hasattr(request, 'body'):
        return request.body
    try:
        return str2bytes(content)
    except TypeError as exc:
        raise HTTPBadRequest(f"Invalid multipart content format: {exc}")


def create_multipart_deploy(cwl_files, url, process_description=None, boundary=None):
    # type: (List[Union[str, CWL]], URL, Optional[JSON], Optional[str]) -> Tuple[bytes, str]
    """
    Create ``multipart/related`` deployment content from a ``list`` of :term:`CWL` files.

    :param cwl_files:
        ``list`` of :term:`CWL` files. Each item can be:

        - A file path (``str``) to a :term:`CWL` file (will be loaded)
        - A :term:`CWL` ``dict`` (already parsed)
    :param url: Domain or hostname for ``Content-ID`` header generation
    :param process_description: Optional :term:`Process` description metadata to include
    :param boundary: Optional custom ``boundary`` ``str`` (auto-generated if not provided)
    :returns:
        ``tuple`` of (multipart content ``bytes``, full ``Content-Type`` header with ``boundary``)
    """
    if not cwl_files:
        raise ValueError("At least one CWL file must be provided")

    msg = MIMEMultipart("related", boundary=boundary)
    main_workflow_cid = None
    workflow_count = 0

    # Add CWL parts
    for idx, cwl_item in enumerate(cwl_files):
        if isinstance(cwl_item, str):
            cwl_data = load_file(cwl_item)
        else:
            cwl_data = cwl_item

        cwl_class = cwl_data.get("class", "")
        is_workflow = cwl_class == "Workflow"

        cwl_id = cwl_data.get("id")
        if not cwl_id:
            raise ValueError(
                f"CWL package at index {idx} missing required 'id' field for multipart deployment. "
                f"Each CWL package must have an 'id' to be used as Content-ID."
            )

        if is_workflow:
            workflow_count += 1
            if workflow_count == 1:
                # First workflow becomes the main one
                main_workflow_cid = cwl_id

        # Create the CWL part
        cwl_json = json.dumps(cwl_data, indent=2)
        part = MIMEText(cwl_json, _subtype="json", _charset="utf-8")
        # Replace the default Content-Type (text/json) with the CWL-specific one
        part.replace_header("Content-Type", ContentType.APP_CWL_JSON)

        part.add_header("Content-ID", f"<{cwl_id}@{url}>")
        part.add_header("Content-Location", cwl_id)

        msg.attach(part)

    # Add process description if provided
    if process_description:
        desc_json = json.dumps(process_description, indent=2)
        desc_part = MIMEText(desc_json, _subtype="json", _charset="utf-8")
        # Replace the default Content-Type (text/json) with application/json
        desc_part.replace_header("Content-Type", ContentType.APP_JSON)
        desc_part.add_header("Content-ID", "<process-description>")
        msg.attach(desc_part)

    multipart_content = msg.as_bytes()

    # Build the Content-Type header with start parameter if we have a main workflow
    # Extract the boundary from the message (auto-generated if not explicitly provided)
    boundary = msg.get_boundary()
    content_type = f"multipart/related; boundary={boundary}"
    if main_workflow_cid:
        content_type += f"; start={main_workflow_cid}"

    return multipart_content, content_type


def _classify_multipart_part(part_data, cwl_packages, parts_by_cid, content_id, process_description):
    # type: (JSON, List[CWL], Dict[str, CWL], str, Optional[JSON]) -> Optional[JSON]
    """
    Classify parsed multipart part as CWL package or process description.

    Returns updated process_description if applicable.
    """
    if not isinstance(part_data, dict):
        return process_description

    if "class" in part_data and part_data["class"] in ["CommandLineTool", "Workflow", "ExpressionTool"]:
        cwl_packages.append(part_data)
        if content_id:
            parts_by_cid[content_id] = part_data
        return process_description

    if "cwlVersion" in part_data and "$graph" in part_data:
        cwl_packages.append(part_data)
        if content_id:
            parts_by_cid[content_id] = part_data
        return process_description

    if "processDescription" in part_data or "process" in part_data:
        if process_description is not None:
            LOGGER.warning("Multiple process descriptions found in multipart, using first one")
            return process_description
        return part_data

    if any(k in part_data for k in ["inputs", "outputs", "baseCommand", "steps"]):
        cwl_packages.append(part_data)
        if content_id:
            parts_by_cid[content_id] = part_data
        return process_description

    # Unknown part type - use as process description if we don't have one yet
    return process_description or part_data


def _validate_and_reorder_multipart_workflow(cwl_packages, root_workflow_cid, parts_by_cid):
    # type: (List[CWL], Optional[str], Dict[str, CWL]) -> List[CWL]
    """
    Validate and reorder :term:`CWL` packages based on root workflow reference.

    Validates that the root document (specified by ``start`` parameter or first element) is a ``Workflow``
    as per RFC 5621 requirements for ``multipart/related``.

    :param cwl_packages: ``list`` of :term:`CWL` packages extracted from multipart content
    :param root_workflow_cid: Content-ID of the root workflow from ``start`` parameter (if provided)
    :param parts_by_cid: ``dict`` mapping Content-IDs to :term:`CWL` packages
    :returns: Reordered ``list`` of :term:`CWL` packages with root workflow last
    :raises HTTPBadRequest: If ``start`` parameter references a non-Workflow :term:`CWL`
    """
    if root_workflow_cid and root_workflow_cid in parts_by_cid:
        root_pkg = parts_by_cid[root_workflow_cid]
        # Validate that the root is actually a Workflow (per RFC 5621 and multipart/related requirements)
        root_class = root_pkg.get("class", "")
        if root_class != "Workflow":
            raise HTTPBadRequest(json={
                "title": "Invalid root workflow reference",
                "description": (
                    f"The 'start' parameter references a CWL with class '{root_class}', "
                    "but only 'Workflow' is permitted as root document in multipart/related."
                ),
                "cause": {"Content-ID": root_workflow_cid, "class": root_class}
            })
        cwl_packages = [pkg for pkg in cwl_packages if pkg is not root_pkg]
        cwl_packages.append(root_pkg)
    elif not root_workflow_cid and cwl_packages:
        # No explicit start parameter: validate first element is a Workflow (RFC 5621 §7 default)
        first_pkg = cwl_packages[0]
        first_class = first_pkg.get("class", "")
        if first_class and first_class != "Workflow":
            LOGGER.warning(
                "No 'start' parameter provided in multipart/related. First element has class '%s' "
                "but 'Workflow' is recommended for root document. Proceeding with deployment.",
                first_class
            )

    return cwl_packages


def _fetch_multipart_content_location(content_location, part_content, request=None):
    # type: (str, str, Optional[AnyRequestType]) -> str
    """
    Fetch :term:`CWL` content from ``Content-Location`` header if part body is empty.

    Checks if part body is empty and ``Content-Location`` is a URL, then fetches the content from that location.
    ``Content-Location`` can be a static :term:`CWL` file URL or an API endpoint (Weaver, WPS, OGC API).
    Relative URLs are resolved against the base API URL.

    :param content_location: ``Content-Location`` header value (absolute or relative URL)
    :param part_content: Current part content (may be empty)
    :param request: Optional request object for resolving relative URLs
    :returns: Updated part content (either original or fetched from ``Content-Location``)
    :raises HTTPBadRequest: If fetching from ``Content-Location`` fails
    """
    # Only fetch if part body is empty AND Content-Location is provided
    if not content_location or (part_content and part_content.strip()):
        return part_content

    # Resolve relative URLs using base API URL
    absolute_url = content_location
    if not any(content_location.startswith(scheme) for scheme in ["http://", "https://", "file://", "s3://"]):
        # Relative URL - resolve against base API URL
        if request:
            base_url = get_wps_restapi_base_url(request)
            absolute_url = urljoin(f"{base_url}/", content_location)
            LOGGER.debug(
                "Resolving relative Content-Location [%s] to absolute URL [%s]",
                content_location, absolute_url
            )
        else:
            # No request context to resolve relative URL
            LOGGER.error(
                "Content-Location [%s] is relative but no request context available to resolve it.",
                content_location
            )
            raise HTTPBadRequest(json={
                "title": "Invalid Content-Location",
                "description": (
                    f"Content-Location [{content_location}] is a relative URL but cannot be resolved "
                    f"without request context."
                ),
                "cause": {"location": content_location}
            })

    LOGGER.debug("Fetching CWL from Content-Location: %s", absolute_url)
    try:
        # Content-Location can be:
        # 1. A static CWL file URL (http/https/s3/file)
        # 2. A Weaver process package endpoint (/processes/{pid}/package)
        # 3. A WPS process endpoint (/wps?request=DescribeProcess&identifier=...)
        # 4. An OGC API Processes endpoint

        _, ext = os.path.splitext(absolute_url.split('?')[0])  # strip query params
        if ext.replace('.', '') in PACKAGE_EXTENSIONS:
            return load_file(absolute_url, text=True)

        # Could be an API endpoint (Weaver, WPS, OGC API)
        # Use the process definition resolver that handles all reference types
        from weaver.processes.wps_package import _generate_process_with_cwl_from_reference
        cwl_pkg, _ = _generate_process_with_cwl_from_reference(absolute_url)
        return json.dumps(cwl_pkg) if isinstance(cwl_pkg, dict) else str(cwl_pkg)
    except Exception as exc:
        LOGGER.error("Failed to fetch content from Content-Location %s: %s", absolute_url, exc)
        raise HTTPBadRequest(json={
            "title": "Failed to fetch Content-Location",
            "description": f"Could not retrieve CWL from Content-Location: {content_location}",
            "cause": {"error": str(exc), "Content-Location": content_location, "location": absolute_url}
        })


def _parse_multipart_message(content, content_type, request=None):
    # type: (Union[str, bytes], str, Optional[AnyRequestType]) -> Any
    """
    Parse raw multipart content into an email.message.Message object.

    :param content: Raw multipart content (``str`` or ``bytes``)
    :param content_type: ``Content-Type`` header value (must include ``boundary`` parameter)
    :param request: Optional request object for extracting body
    :returns: Parsed multipart message object
    :raises HTTPBadRequest: If multipart content is malformed
    """
    raw_content = _get_multipart_content(content, request)
    msg_bytes = b"Content-Type: " + content_type.encode('utf-8') + b"\r\n\r\n" + raw_content

    try:
        msg = message_from_bytes(msg_bytes)
    except Exception as exc:
        raise HTTPBadRequest(json={
            "title": "Failed to parse multipart content",
            "description": str(exc),
            "cause": {"error": exc.__class__.__name__}
        })

    if not msg.is_multipart():
        raise HTTPBadRequest("Content is not multipart format")

    return msg


def _extract_multipart_start_parameter(content_type):
    # type: (str) -> Optional[str]
    """
    Extract the ``start`` parameter from a ``multipart/related`` ``Content-Type`` header.

    :param content_type: Full ``Content-Type`` header value
    :returns: ``Content-ID`` from ``start`` parameter, or ``None`` if not present
    """
    if ContentType.MULTIPART_RELATED in content_type.lower() and "start=" in content_type:
        start_part = content_type.split("start=")[1].split(";")[0].strip().strip('"').strip('<>')
        return start_part
    return None


def _interpret_multipart_part(part, request=None):
    # type: (Any, Optional[AnyRequestType]) -> Optional[Tuple[str, str, str, JSON]]
    """
    Interpret a single multipart part: decode, fetch content if needed, and parse.

    :param part: Single part from multipart message
    :param request: Optional request object for resolving relative ``Content-Location`` URLs
    :returns:
        ``tuple`` of (content_type, content_id, content_location, parsed_data) or ``None`` if part cannot be parsed
    """
    part_content_type = part.get_content_type()
    content_id = part.get('Content-ID', '').strip('<>')
    content_location = part.get('Content-Location', '').strip()

    # Decode part content
    part_content = part.get_payload(decode=True)
    if isinstance(part_content, bytes):
        charset = part.get_content_charset() or 'utf-8'
        try:
            part_content = part_content.decode(charset)
        except (UnicodeDecodeError, LookupError):
            part_content = part_content.decode('utf-8', errors='replace')

    # Fetch from Content-Location if part body is empty
    part_content = _fetch_multipart_content_location(content_location, part_content, request)

    # Parse JSON/YAML if applicable
    if (part_content_type in ContentType.ANY_CWL or
            part_content_type in [ContentType.APP_JSON, ContentType.APP_YAML]):
        try:
            part_data = yaml.safe_load(part_content)
            return part_content_type, content_id, content_location, part_data
        except Exception as exc:
            LOGGER.warning("Failed to parse part with Content-Type %s: %s", part_content_type, exc)
            return None

    return None


def _organize_deploy_parts(interpreted_parts, root_workflow_cid):
    # type: (List[Tuple[str, str, str, JSON]], Optional[str]) -> Tuple[List[CWL], Optional[JSON]]
    """
    Organize interpreted multipart parts into CWL packages and process description.

    :param interpreted_parts: ``list`` of interpreted parts (content_type, content_id, content_location, data)
    :param root_workflow_cid: Content-ID of root workflow from ``start`` parameter (if any)
    :returns: ``tuple`` of (``list`` of :term:`CWL` packages, optional process description)
    :raises HTTPBadRequest: If no CWL packages found or root workflow validation fails
    """
    cwl_packages = []
    process_description = None
    parts_by_cid = {}

    for _, content_id, _, part_data in interpreted_parts:
        process_description = _classify_multipart_part(
            part_data, cwl_packages, parts_by_cid, content_id, process_description
        )

    if not cwl_packages:
        raise HTTPBadRequest(json={
            "title": "No CWL packages found in multipart content",
            "description": "Multipart request must contain at least one CWL package part.",
            "cause": {"parts_found": len(interpreted_parts)}
        })

    cwl_packages = _validate_and_reorder_multipart_workflow(cwl_packages, root_workflow_cid, parts_by_cid)

    return cwl_packages, process_description


def parse_multipart_deploy(content, content_type, request=None):
    # type: (Union[str, bytes], str, Optional[AnyRequestType]) -> Tuple[List[CWL], Optional[JSON]]
    """
    Parse ``multipart/mixed`` or ``multipart/related`` deployment content.

    Extracts :term:`CWL` packages and optional :term:`Process` description from multipart request.

    :param content: Raw multipart content (``str`` or ``bytes``)
    :param content_type: ``Content-Type`` header value (must include ``boundary`` parameter)
    :param request: Optional request object for extracting body
    :returns: ``tuple`` of (``list`` of :term:`CWL` packages, optional :term:`Process` description metadata)
    :raises HTTPBadRequest: If multipart content is malformed or invalid
    """
    msg = _parse_multipart_message(content, content_type, request)
    root_workflow_cid = _extract_multipart_start_parameter(content_type)
    interpreted_parts = []

    for part in msg.get_payload():
        interpreted = _interpret_multipart_part(part, request)
        if interpreted:
            interpreted_parts.append(interpreted)

    return _organize_deploy_parts(interpreted_parts, root_workflow_cid)


def parse_process_deploy_content(
    request=None,                                       # type: Optional[AnyRequestType]
    content=None,                                       # type: Optional[Union[JSON, str]]
    content_schema=None,                                # type: Optional[colander.SchemaNode]
    content_type=sd.RequestContentTypeHeader.default,   # type: Optional[ContentType]
    content_type_schema=sd.RequestContentTypeHeader,    # type: Optional[colander.SchemaNode]
):                                                      # type: (...) -> Union[JSON, CWL]
    """
    Load the request content with validation of expected content type and their schema.
    """

    # Get full Content-Type header (including parameters like boundary) from request if available
    if request is not None:
        # Use get_header to get the full header value with parameters, not request.content_type which strips them
        request_headers = getattr(request, 'headers', {})
        full_content_type = get_header("Content-Type", request_headers)
        if full_content_type:
            content_type = full_content_type

    # If content is already a parsed dict (from recursive calls), skip parsing
    if isinstance(content, dict):
        pass  # Content already parsed, proceed to validation
    elif content_type and any(mt in content_type.lower() for mt in ContentType.ANY_MULTIPART):
        LOGGER.info("Detected multipart deployment request")
        cwl_packages, _ = parse_multipart_deploy(
            content=content if content is not None else request.body,
            content_type=content_type,
            request=request
        )

        if len(cwl_packages) == 1:
            # Single CWL package - use as-is
            # This avoids double-wrapping if the package already contains a $graph
            content = cwl_packages[0]
        else:
            # Multiple packages - return as list to be wrapped in $graph
            content = cwl_packages
        # Content is now parsed, skip to validation
    else:
        # Non-multipart content: parse from request or string
        try:
            if request is not None:
                content = request.text
                content_type = request.content_type
            if content_type is not None and content_type_schema is not None:
                content_type = content_type_schema().deserialize(content_type)
            if isinstance(content, str):
                content = yaml.safe_load(content)
            if not isinstance(content, dict):
                raise TypeError("Not a valid JSON body for process deployment.")
        except colander.Invalid as exc:
            raise HTTPUnsupportedMediaType(json={
                "title": "Unsupported Media Type",
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0/unsupported-media-type",
                "detail": str(exc),
                "status": HTTPUnsupportedMediaType.code,
                "cause": {"Content-Type": None if content_type is None else str(content_type)},
            })
        except Exception as exc:
            raise HTTPBadRequest(json={
                "title": "Bad Request",
                "type": "BadRequest",
                "detail": "Unable to parse contents.",
                "status": HTTPBadRequest.code,
                "cause": str(exc),
            })

    # Validate content schema (applies to both multipart and non-multipart)
    try:
        if content_schema is not None:
            content = content_schema().deserialize(content)
    except colander.Invalid as exc:
        raise HTTPUnprocessableEntity(json={
            "type": "InvalidParameterValue",
            "title": "Failed schema validation.",
            "status": HTTPUnprocessableEntity.code,
            "error": colander.Invalid.__name__,
            "cause": exc.msg,
            "value": repr_json(exc.value, force_string=False),
        })
    return content


def deploy_process_from_payload(payload, container, overwrite=False):  # pylint: disable=R1260,too-complex
    # type: (Union[JSON, str], Union[AnySettingsContainer, AnyRequestType], Union[bool, Process]) -> HTTPException
    """
    Deploy the process after resolution of all references and validation of the parameters from payload definition.

    Adds a :class:`weaver.datatype.Process` instance to storage using the provided JSON ``payload``
    matching :class:`weaver.wps_restapi.swagger_definitions.ProcessDescription`.

    :param payload: JSON payload that was specified during the process deployment request.
    :param container:
        Container to retrieve application settings.
        If it is a ``request``-like object, additional parameters may be used to identify the payload schema.
    :param overwrite:
        In case of a pure deployment (from scratch), indicates (using :class:`bool`) whether to allow override of
        an existing process definition if conflict occurs. No versioning is applied in this case (full replacement).
        In case of an update deployment (from previous), indicates which process to be replaced with updated version.
        The new version should not conflict with another existing process version. If payload doesn't provide a new
        version, the following `MAJOR` version from the specified overwrite process is used to define the new revision.
    :returns: HTTPOk if the process registration was successful.
    :raises HTTPException: for any invalid process deployment step.
    """
    headers = getattr(container, "headers", {})  # container is any request (as when called from API Deploy request)
    c_type_full = get_header("Content-Type", headers) or ContentType.APP_OGC_PKG_JSON

    # use deepcopy of to remove any circular dependencies before writing to mongodb or any updates to the payload
    # For multipart requests, we need to pass the request object to access the raw body
    payload = parse_process_deploy_content(
        request=container if hasattr(container, 'body') else None,
        content=payload,
        content_type=c_type_full,  # Pass full Content-Type with parameters (e.g., boundary)
        content_type_schema=sd.DeployContentType,
    )

    # Extract process ID from Content-ID header if provided (RFC 2392)
    content_id_header = get_header("Content-ID", headers)
    resource_id = None
    if content_id_header:
        try:
            resource_id, _ = parse_content_id(content_id_header)
        except ValueError as exc:
            raise HTTPBadRequest(json={
                "title": "Invalid Content-ID header format",
                "description": (
                    f"Content-ID header does not conform to RFC 2392 format: {exc}. "
                    "Expected format: '<resource-id@context>'"
                ),
                "cause": {"Content-ID": content_id_header, "error": str(exc)},
            })

        if resource_id:
            # Extract process ID from payload - check multiple possible locations
            payload_id = payload.get("id")  # Direct CWL or top-level
            if not payload_id and "processDescription" in payload:
                process_desc = payload.get("processDescription", {})
                # OLD schema: processDescription.process.id
                if "process" in process_desc and isinstance(process_desc["process"], dict):
                    payload_id = process_desc["process"].get("id")
                # OGC schema: processDescription.id
                elif "id" in process_desc:
                    payload_id = process_desc.get("id")

            # Validate Content-ID matches payload ID
            if payload_id and payload_id != resource_id:
                raise HTTPUnprocessableEntity(json={
                    "title": "Content-ID header mismatch",
                    "description": (
                        f"Content-ID header resource [{resource_id}] does not match payload id [{payload_id}]. "
                        "Please ensure they match or omit the Content-ID header."
                    ),
                    "cause": {"Content-ID": content_id_header, "payload_id": payload_id},
                })

    # For multipart/list payload, skip validation and go directly to multi-CWL deployment
    # Each individual CWL package will be validated during recursive deployment
    # WARNING: Multi-CWL deployment is NOT atomic. If deployment fails midway, previously deployed
    # tools remain in the database without rollback. Retry attempts will skip already-deployed tools.
    if isinstance(payload, list):
        LOGGER.info("Detected multi-CWL deployment (multipart) with %d packages", len(payload))
        return _deploy_process_multi_cwl(payload, container, overwrite)

    payload_copy = deepcopy(payload)
    payload = _check_deploy(payload)

    # Remove schema fields regardless of deployment type
    payload.pop("$schema", None)
    payload.pop("$id", None)

    # validate identifier naming for unsupported characters
    process_desc = payload.get("processDescription", {})  # empty possible if CWL directly passed
    process_info = process_desc.get("process", process_desc)
    process_href = process_desc.pop("href", None) or payload.get("process", None)
    process_href = process_href if isinstance(process_href, str) else None
    if "process" in process_desc:
        process_param = "processDescription.process"
    elif process_href and "process" in payload:
        process_param = "process"
        payload.pop("process")
        process_info = payload
    else:
        process_param = "processDescription"

    # retrieve CWL package definition, either via "href" (WPS-1/2), "owsContext" or "executionUnit" (package/reference)
    deployment_profile_name = payload.get("deploymentProfileName", "")
    ows_context = process_info.pop("owsContext", None)
    reference = None
    package = None
    found = False

    # Detect direct CWL format (vs OGC deployment wrapper with processDescription/executionUnit).
    # Recursion is safe: resolve_cwl_graph() unpacks $graph items before recursive calls.
    if "cwlVersion" in payload:
        # Extract and remove Weaver-specific 'version' field before CWL processing.
        # The 'version' field is a Weaver extension for process versioning and is not part of the CWL standard.
        # Leaving it in would cause CWL schema validation errors downstream.
        process_info = {"version": payload.pop("version", None)}
        package = resolve_cwl_graph(payload)
        found = True
    elif process_href:
        reference = process_href  # reference type handled downstream
        found = isinstance(reference, str)
    elif isinstance(ows_context, dict):
        offering = ows_context.get("offering")
        if not isinstance(offering, dict):
            raise HTTPUnprocessableEntity(f"Invalid parameter '{process_param}.owsContext.offering'.")
        content = offering.get("content")
        if not isinstance(content, dict):
            raise HTTPUnprocessableEntity(f"Invalid parameter '{process_param}.owsContext.offering.content'.")
        package = None
        reference = content.get("href")
        found = isinstance(reference, str)
    else:  # ogc-apppkg type, but no explicit check since used by default (backward compat)
        if deployment_profile_name:  # optional hint
            allowed_profile_suffix = [ProcessType.APPLICATION, ProcessType.WORKFLOW]
            if not any(deployment_profile_name.lower().endswith(typ) for typ in allowed_profile_suffix):
                raise HTTPBadRequest("Invalid value for parameter 'deploymentProfileName'.")
        execution_units = payload.get("executionUnit")
        if isinstance(execution_units, dict):
            if "unit" not in execution_units and "href" not in execution_units:
                execution_units = {"unit": execution_units}
            execution_units = [execution_units]
        if (not isinstance(execution_units, list) or len(execution_units) < 1 or
                not isinstance(execution_units[0], dict)):
            raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")

        if len(execution_units) == 1:
            execution_unit = execution_units[0]
            package = execution_unit.get("unit")
            reference = execution_unit.get("href")
            found = package or reference
        else:
            # Multiple execution units: extract all packages (inline or fetch from references)
            package = resolve_multi_execution_units(execution_units)
            reference = None
            found = True
    if not found:
        params = [
            "process (href)",
            "processDescription.process.href",
            "processDescription.process.owsContext.content.href",
            "processDescription.href",
            "processDescription.owsContext.content.href",
            "executionUnit[*].(unit|href)",
            "{ <CWL> }",
        ]
        raise HTTPBadRequest(
            f"Missing one of required parameters {params} to obtain package/process definition or reference."
        )

    if process_info.get("type", "") == ProcessType.BUILTIN:
        raise HTTPBadRequest(
            f"Invalid process type resolved from package: [{ProcessType.BUILTIN}]. "
            f"Deployment of {ProcessType.BUILTIN} process is not allowed."
        )

    settings = get_settings(container)

    # Handle multi-CWL deployment from $graph
    if isinstance(package, tuple):
        # package is (list_of_cwls, original_payload_with_graph)
        package, _ = package
    if isinstance(package, list):
        return _deploy_process_multi_cwl(package, container, overwrite)

    # update and validate process information using WPS process offering, CWL/WPS reference or CWL package definition
    process_info = _validate_deploy_process_info(process_info, reference, package, settings, headers)

    restapi_url = get_wps_restapi_base_url(settings)
    description_url = "/".join([restapi_url, "processes", process_info["identifier"]])
    execute_endpoint = "/".join([description_url, "jobs"])

    # ensure that required "processEndpointWPS1" in db is added,
    # will be auto-fixed to localhost if not specified in body
    process_info["processEndpointWPS1"] = process_desc.get("processEndpointWPS1")
    process_info["executeEndpoint"] = execute_endpoint
    process_info["payload"] = payload_copy
    process_info["jobControlOptions"] = process_desc.get("jobControlOptions", [])
    process_info["outputTransmission"] = process_desc.get("outputTransmission", [])
    process_info["processDescriptionURL"] = description_url

    # insert the "resolved" context using details retrieved from "executionUnit"/"href" or directly with "owsContext"
    if "owsContext" not in process_info and reference:
        process_info["owsContext"] = {"offering": {"content": {"href": str(reference)}}}
    elif isinstance(ows_context, dict):
        process_info["owsContext"] = ows_context
    # if user provided additional links that have valid schema,
    # process them separately since links are generated dynamically from API settings per process
    # don't leave them there as they would be seen as if the 'Process' class generated the field
    if "links" in process_info:
        process_info["additional_links"] = process_info.pop("links")
    # remove schema to avoid later deserialization error if different, but remaining content is valid
    # also, avoid storing this field in the process object, regenerate it as needed during responses
    process_info.pop("$schema", None)
    process_info.pop("$id", None)

    try:
        process = Process(process_info)  # if 'version' was provided in deploy info, it will be added as hint here
        if isinstance(overwrite, Process):
            process_summary = _update_deploy_process_version(process, overwrite, VersionLevel.MAJOR, container)
        else:
            process_summary = _save_deploy_process(process, overwrite, container)
    except ValueError as exc:
        LOGGER.error("Failed schema validation of deployed process summary:\n%s", exc)
        raise HTTPBadRequest(detail=str(exc))
    except HTTPException:
        raise
    links = process.links(container)
    loc_url = next(link["href"] for link in links if link["rel"] == "self")
    process_summary["links"] = links
    data = {
        "description": sd.OkPostProcessesResponse.description,
        "processSummary": process_summary,
        "deploymentDone": True,
    }
    if deployment_profile_name:
        data["deploymentProfileName"] = deployment_profile_name
    headers = {
        "Content-Type": ContentType.APP_JSON,
        "Content-Location": loc_url,
        "Location": loc_url,
    }
    if overwrite and (
        isinstance(overwrite, bool) or (
            isinstance(overwrite, Process) and
            overwrite.version == process_summary.get("version")
        )
    ):
        http_cls = HTTPOk
    else:
        http_cls = HTTPCreated
    return http_cls(json=data, headers=headers)


def _save_deploy_process(process, override, container):
    # type: (Process, bool, AnySettingsContainer) -> JSON
    """
    Store the :class:`Process` to database with error handling and appropriate message reporting the problem.
    """
    try:
        sd.ProcessSummary().deserialize(process)  # make it fail before save if invalid, then apply for real
        db = get_db(container)
        store = db.get_store(StoreProcesses)
        new_process = store.save_process(process, overwrite=override)
        process_summary = new_process.summary(container=container)
    except ProcessRegistrationError as exc:
        raise HTTPConflict(json={
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0/duplicated-process",
            "title": "Process definition conflict.",
            "detail": str(exc),
            "status": HTTPConflict.code,
            "cause": {"process_id": process.id},
        })
    except colander.Invalid as exc:
        LOGGER.error("Failed schema validation of updated process summary:\n%s", exc)
        raise HTTPBadRequest(json={
            "description": "Failed schema validation of process summary.",
            "cause": f"Invalid schema: [{exc.msg or exc!s}]",
            "error": exc.__class__.__name__,
            "value": exc.value
        })
    return process_summary


def _deploy_process_multi_cwl(
    cwl_packages,   # type: List[CWL]
    container,      # type: Union[AnySettingsContainer, AnyRequestType]
    overwrite,      # type: Union[bool, Process]
):                  # type: (...) -> HTTPException
    """
    Deploy multiple :term:`CWL` packages from a ``$graph`` definition using recursive deployment calls.

    Rather than duplicating deployment logic, this function orchestrates the deployment order and recursively
    calls :func:`deploy_process_from_payload` for each package to reuse all validation, URL setup, and storage logic.

    .. warning::
        This deployment is **NOT atomic**. If any CWL package fails during deployment:

        - Previously deployed tools remain in the database (no rollback)
        - Retry attempts will skip already-deployed tools (``HTTPConflict`` is caught and ignored)
        - Child tools are always deployed with ``overwrite=False``, even if the main process uses ``overwrite=True``

        This means partial deployments can leave orphaned processes that must be manually cleaned up.

    :param cwl_packages: ``list`` of resolved :term:`CWL` package definitions.
    :param container: Application container.
    :param overwrite: Whether to overwrite existing processes. Note: only applies to main process, not child tools.
    :returns: HTTP response with deployment result from the main process.
    """
    LOGGER.info("Deploying multi-CWL package with %d definitions", len(cwl_packages))

    # Resolve deployment order (tools first, main process last)
    # main_process is either the Workflow or the tool with id "#main"/"main"
    tools, main_process_pkg = resolve_deployment_order(cwl_packages)

    main_process_id = main_process_pkg.get("id")
    deployed_processes = []

    # Deploy CommandLineTools first (but skip the one that will be the main process)
    for tool_pkg in tools:
        tool_id = tool_pkg.get("id")

        # Skip if this tool will be deployed as the main process
        if tool_id == main_process_id:
            LOGGER.info("Skipping child deployment of %s (will be deployed as main process)", tool_id)
            continue

        LOGGER.info("Deploying CWL tool: %s", tool_id)

        # Strip # prefix from tool ID if present (valid in $graph but not as process ID)
        tool_pkg_deploy = deepcopy(tool_pkg)
        if tool_id and tool_id.startswith("#"):
            tool_pkg_deploy["id"] = tool_id[1:]

        # Pass CWL package directly - it will be detected as CWL content by cwlVersion field
        # NOTE: Child tools are always deployed with overwrite=False to preserve existing dependencies.
        # This means retrying a failed multi-CWL deployment will skip already-deployed tools.
        try:
            response = deploy_process_from_payload(tool_pkg_deploy, container, overwrite=False)
            deployed_processes.append(response.json["processSummary"])
            LOGGER.info("Successfully deployed CWL tool: %s", tool_id)
        except HTTPConflict:
            # Tool already exists from a previous (possibly failed) deployment attempt.
            # Continue deployment to allow retry scenarios without requiring manual cleanup.
            LOGGER.info("CWL tool already exists: %s, skipping deployment", tool_id)
        except Exception as exc:
            # Any other error (validation, permission, etc.) stops the entire deployment.
            # WARNING: Previously deployed tools from this attempt are NOT rolled back.
            LOGGER.error("Failed to deploy CWL tool %s: %s", tool_id, exc)
            raise

    # Deploy main process (workflow or main tool)
    main_pkg_deploy = deepcopy(main_process_pkg)

    # Strip # prefix from main process ID if present
    if main_process_id and main_process_id.startswith("#"):
        main_pkg_deploy["id"] = main_process_id[1:]

    # For workflows, update step references (remove # prefixes to reference deployed processes)
    if main_pkg_deploy.get("class") == "Workflow" and "steps" in main_pkg_deploy:
        for step_data in main_pkg_deploy.get("steps", {}).values():
            if "run" in step_data and isinstance(step_data["run"], str):
                if step_data["run"].startswith("#"):
                    step_data["run"] = step_data["run"][1:]

    # Pass CWL package directly
    LOGGER.info("Deploying main CWL process: %s", main_process_id)
    response = deploy_process_from_payload(main_pkg_deploy, container, overwrite)

    LOGGER.info("Successfully deployed multi-CWL package: main process %s with %d child processes",
                main_process_id, len(deployed_processes))

    return response


def _update_deploy_process_version(process, process_overwrite, update_level, container=None):
    # type: (Process, Process, VersionLevel, Optional[AnySettingsContainer]) -> JSON
    """
    Handle all necessary update operations of a :term:`Process` definition.

    Validate that any specified version for :term:`Process` deployment is valid against any other existing versions.
    Perform any necessary database adjustments to replace the old :term:`Process` references for the creation of the
    updated :term:`Process` to ensure all versions and links remain valid against their original references.

    :param process: Desired new process definition.
    :param process_overwrite: Old process from which update of the definition in database could be required.
    :param update_level:
        Minimum semantic version level required for this update operation.
        If the new :term:`Process` definition did not provide a version explicitly, this level will be used to
        automatically infer the following revision number based on the old :term:`Process` reference.
    :param container: Any container to retrieve a database connection.
    :returns: Process summary with definition retrieved from storage (saved) after all operations were applied.
    :raises HTTPException: Relevant error is raised in the even of any erroneous process definition (old and new).
    """
    if not process.mutable:
        raise HTTPForbidden(json={
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0/immutable-process",
            "title": "Process immutable.",
            "detail": "Cannot update an immutable process.",
            "status": HTTPForbidden.code,
            "cause": {"mutable": False}
        })

    if process.name != process_overwrite.name:
        raise HTTPBadRequest(json={
            "type": "InvalidParameterValue",
            "title": "Invalid process identifier.",
            "detail": "Specified process identifier in payload definition does not match expected ID in request path.",
            "status": HTTPBadRequest.code,
            "cause": {"pathProcessID": process_overwrite.name, "bodyProcessID": process.name}
        })

    db = get_db(container)
    store = db.get_store(StoreProcesses)

    # if no new version was specified, simply take the next one relevant for the update level
    # then check that new version is within available range against target process for required update level
    new_version = process.version if process.version else _bump_process_version(process_overwrite.version, update_level)
    taken_versions = store.find_versions(process.id, VersionFormat.STRING)  # string format for output if error
    if not is_update_version(new_version, taken_versions, update_level):
        new_version = as_version_major_minor_patch(new_version, VersionFormat.STRING)
        ref_version = as_version_major_minor_patch(process_overwrite.version, VersionFormat.STRING)
        if new_version in taken_versions:
            http_error = HTTPConflict
            message = "Process version conflicts with already taken revisions."
        else:
            http_error = HTTPUnprocessableEntity
            message = "Semantic version is not of appropriate update level for requested changes."
        raise http_error(json={
            "type": "InvalidParameterValue",
            "title": "Invalid version value.",
            "detail": message,
            "status": http_error.code,
            "cause": {
                "revisions": taken_versions,
                "reference": ref_version,
                "version": new_version,
                "change": update_level,
            }
        })

    old_version = None
    op_override = process_overwrite
    try:
        # if source process for update is not the latest, no need to rewrite 'id:version' since it is not only 'id'
        # otherwise, replace latest process 'id' by explicit 'id:version'
        if process_overwrite.latest:
            pid_only = process_overwrite.name
            old_version = process_overwrite.version
            old_process = store.update_version(pid_only, old_version)
            process_tag = old_process.tag
            # since 'id' reference changes from old to new process,
            # reflect the change in any job that could refer to it
            job_store = db.get_store(StoreJobs)
            n_updated = job_store.batch_update_jobs({"process": pid_only}, {"process": process_tag})
            LOGGER.debug("Updated %s jobs from process [%s] to old revision [%s]", n_updated, pid_only, process_tag)
            op_override = False  # make sure no conflict when saving process afterward
        process.version = new_version
        process_summary = _save_deploy_process(process, op_override, container)
    # add more version information to already handled error to better report the real conflict of revisions if any
    except (ProcessRegistrationError, HTTPConflict):
        if old_version is not None:
            old_version = as_version_major_minor_patch(old_version, VersionFormat.STRING)
        if new_version is not None:
            new_version = as_version_major_minor_patch(new_version, VersionFormat.STRING)
        raise HTTPConflict(json={
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0/duplicated-process",
            "title": "Process definition conflict.",
            "detail": "Failed update of process conflicting with another definition or revision.",
            "status": HTTPConflict.code,
            "cause": {"process_id": process.id, "old_version": old_version, "new_version": new_version},
        })
    return process_summary


def _bump_process_version(version, update_level):
    # type: (AnyVersion, VersionLevel) -> AnyVersion
    """
    Obtain the relevant version with specified level incremented by one.
    """
    new_version = list(as_version_major_minor_patch(version, VersionFormat.PARTS))
    if update_level == VersionLevel.PATCH:
        new_version[2] += 1
    elif update_level == VersionLevel.MINOR:
        new_version[1] += 1
        new_version[2] = 0
    elif update_level == VersionLevel.MAJOR:
        new_version[0] += 1
        new_version[1] = 0
        new_version[2] = 0
    return new_version


def _apply_process_metadata(process, update_data):  # pylint: disable=R1260,too-complex  # FIXME
    # type: (Process, JSON) -> VersionLevel
    """
    Apply requested changes for update of the :term:`Process`.

    Assumes that update data was pre-validated with appropriate schema validation to guarantee relevant typings
    and formats are applied for expected fields. Validation of fields metadata with their specific conditions is
    accomplished when attempting to apply changes.

    .. seealso::
        Schema :class:`sd.PatchProcessBodySchema` describes specific field handling based on unspecified value, null
        or empty-list. Corresponding update levels required for fields are also provided in this schema definition.

    :param process: Process to modify. Can be the latest or a previously tagged version.
    :param update_data: Fields with updated data to apply to the process.
    :return: Applicable update level based on updates to be applied.
    """
    patch_update_fields = [
        "title",
        "description",
        {"source": "keywords", "method": "append", "unique": True},
        {"source": "metadata", "method": "append"},
        {"source": "links", "method": "append", "target": "additional_links"},
    ]
    minor_update_fields = [
        {"source": "jobControlOptions", "method": "override", "unique": True},
        {"source": "outputTransmission", "method": "override", "unique": True},
        "visibility",
    ]
    update_level = VersionLevel.PATCH  # metadata only, elevate to MINOR if corresponding fields changed
    field = value = None  # any last set item that raises an unexpected error can be reported in exception handler

    def _apply_change(data, dest, name, update_fields):
        # type: (JSON, Union[Process, JSON], str, UpdateFields) -> bool
        """
        Apply sub-changes to relevant destination container.

        :param data: New information changes to be applied.
        :param dest: Target location to set new value changes.
        :param name: Target location name for error reporting.
        :param update_fields: Fields that can be updated, with extra specifications on how to handle them.
        :return: Status indicating if any change was applied.
        """
        nonlocal field, value  # propagate outside function

        any_change = False
        for source in update_fields:
            target = source
            method = None
            unique = False
            if isinstance(source, dict):
                src = source["source"]
                target = source.get("target", src)
                method = source.get("method", None)
                unique = source.get("unique", False)
                source = src
            value = data.get(source)
            if value is None:
                continue
            field = f"{name}.{target}"
            # list appends new content unless explicitly empty to reset
            # list override always replace full content
            if isinstance(value, list) and method == "append":
                if not len(value):
                    current = get_field(dest, target, default=[])
                    if current != value:
                        set_field(dest, target, [])
                        any_change = True
                else:
                    current = get_field(dest, source, default=[])
                    merged = copy.deepcopy(current)
                    merged.extend(value)
                    if unique:
                        merged = list(dict.fromkeys(merged))  # not set to preserve order
                    if current != merged:
                        set_field(dest, target, current)
                        any_change = True
            else:
                current = get_field(dest, target, default=None)
                if unique and isinstance(value, list):
                    value = list(dict.fromkeys(value))  # not set to preserve order
                if current != value:
                    set_field(dest, target, value)
                    any_change = True
        return any_change

    try:
        any_update_inputs = any_update_outputs = False

        inputs = update_data.get("inputs")
        if inputs:
            inputs_current = process.inputs
            inputs_changes = normalize_ordered_io(inputs, order_hints=inputs_current)
            inputs_updated = {get_any_id(i, pop=True): i for i in copy.deepcopy(inputs_current)}
            inputs_allowed = list(inputs_updated)
            for input_data in inputs_changes:
                input_id = get_any_id(input_data)
                if input_id not in inputs_allowed:
                    raise HTTPUnprocessableEntity(json={
                        "type": "InvalidParameterValue",
                        "title": "Unknown input identifier.",
                        "detail": "Process update parameters specified an input unknown to this process.",
                        "status": HTTPUnprocessableEntity.code,
                        "cause": {"input.id": input_id, "inputs": inputs_allowed},
                    })
                input_def = inputs_updated[input_id]
                input_name = f"process.inputs[{input_id}]"
                any_update_inputs |= _apply_change(input_data, input_def, input_name, patch_update_fields)

            # early exit if nothing was updated when fields were specified expecting something to be applied
            # avoids potentially indicating that update was accomplished when it would not be
            if not any_update_inputs:
                raise HTTPBadRequest(json={
                    "type": "InvalidParameterValue",
                    "title": "Failed process input parameter update.",
                    "detail": "Provided parameters not applicable for update or no changed values could be detected.",
                    "value": repr_json(update_data, force_string=False),
                })
            field = "process.inputs"
            value = normalize_ordered_io(inputs_updated, order_hints=inputs_current)
            process.inputs = value

        outputs = update_data.get("outputs")
        if outputs:
            outputs_current = process.outputs
            outputs_changes = normalize_ordered_io(outputs, order_hints=outputs_current)
            outputs_updated = {get_any_id(o, pop=True): o for o in copy.deepcopy(outputs_current)}
            outputs_allowed = list(outputs_updated)
            for output_data in outputs_changes:
                output_id = get_any_id(output_data)
                if output_id not in outputs_allowed:
                    raise HTTPUnprocessableEntity(json={
                        "type": "InvalidParameterValue",
                        "title": "Unknown output identifier.",
                        "detail": "Process update parameters specified an output unknown to this process.",
                        "status": HTTPUnprocessableEntity.code,
                        "cause": {"output.id": output_id, "outputs": outputs_allowed},
                    })
                output_def = outputs_updated[output_id]
                output_name = f"process.outputs[{output_id}]"
                any_update_outputs |= _apply_change(output_data, output_def, output_name, patch_update_fields)

            # early exit if nothing was updated when fields were specified expecting something to be applied
            # avoid potentially indicating that update was accomplished when it would not be
            if not any_update_outputs:
                raise HTTPBadRequest(json={
                    "type": "InvalidParameterValue",
                    "title": "Failed process output parameter update.",
                    "detail": "Provided parameters not applicable for update or no changed values could be detected.",
                    "value": repr_json(update_data, force_string=False),
                })
            field = "process.outputs"
            value = normalize_ordered_io(outputs_updated, order_hints=outputs_current)
            process.outputs = value

        any_update_process = _apply_change(update_data, process, "process", patch_update_fields)
        any_update_minor = _apply_change(update_data, process, "process", minor_update_fields)
        if any_update_minor:
            update_level = VersionLevel.MINOR

        if not any((any_update_process, any_update_minor, any_update_inputs, any_update_outputs)):
            raise HTTPBadRequest(json={
                "type": "InvalidParameterValue",
                "title": "Failed process parameter update.",
                "detail": "Provided parameters not applicable for update or no changed values could be detected.",
                "value": repr_json(update_data, force_string=False),
            })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPBadRequest(json={
            "type": "InvalidParameterValue",
            "title": "Failed process parameter update.",
            "detail": "Process update parameters failed validation or produced an error when applying change.",
            "error": fully_qualified_name(exc),
            "cause": {"message": str(exc), "field": field},
            "value": repr_json(value, force_string=False),
        })

    return update_level


def update_process_metadata(request):
    # type: (AnyRequestType) -> HTTPException
    """
    Update only MINOR or PATCH level :term:`Process` metadata.

    Desired new version can be eiter specified explicitly in request payload, or will be guessed accordingly to
    detected changes to be applied.
    """
    data = parse_process_deploy_content(request, content_schema=sd.PatchProcessBodySchema)
    old_process = get_process(request=request)
    new_process = copy.deepcopy(old_process)
    update_level = _apply_process_metadata(new_process, data)
    # apply the new version requested by the user,
    # or make sure the old one is removed to avoid conflict
    user_version = data.get("version") or None
    if user_version:
        new_process.version = user_version
    else:
        new_process.pop("version", None)
    new_process.id = old_process.name  # remove any version reference in ID
    process_summary = _update_deploy_process_version(new_process, old_process, update_level, request)
    data = {
        "description": sd.OkPatchProcessResponse.description,
        "processSummary": process_summary,
        "links": new_process.links(request),
    }
    return HTTPOk(json=data)


def parse_wps_process_config(config_entry):
    # type: (Union[JSON, str]) -> Tuple[str, str, List[str], bool]
    """
    Parses the available WPS provider or process entry to retrieve its relevant information.

    :return: WPS provider name, WPS service URL, and list of process identifier(s).
    :raise ValueError: if the entry cannot be parsed correctly.
    """
    if isinstance(config_entry, dict):
        svc_url = config_entry["url"]
        svc_name = config_entry.get("name")
        svc_proc = config_entry.get("id", [])
        svc_vis = asbool(config_entry.get("visible", False))
    elif isinstance(config_entry, str):
        svc_url = config_entry
        svc_name = None
        svc_proc = []
        svc_vis = False
    else:
        raise ValueError(f"Invalid service value: [{config_entry!s}].")
    url_p = urlparse(svc_url)
    qs_p = parse_qs(url_p.query)
    svc_url = get_url_without_query(url_p)
    # if explicit name was provided, validate it (assert fail if not),
    # otherwise replace silently bad character since it is requested to be inferred
    svc_name = get_sane_name(svc_name or url_p.hostname, assert_invalid=bool(svc_name), min_len=1)
    svc_proc = svc_proc or qs_p.get("identifier", [])  # noqa  # 'identifier=a,b,c' techically allowed
    svc_proc = [proc.strip() for proc in svc_proc if proc.strip()]  # remote empty
    if not isinstance(svc_name, str):
        raise ValueError(f"Invalid service value: [{svc_name!s}].")
    if not isinstance(svc_proc, list):
        raise ValueError(f"Invalid process value: [{svc_proc!s}].")
    return svc_name, svc_url, svc_proc, svc_vis


def register_wps_processes_static(service_url, service_name, service_visibility, service_processes, container):
    # type: (str, str, bool, List[str], AnyRegistryContainer) -> None
    """
    Register WPS-1 :term:`Process` under a service :term:`Provider` as static references.

    For a given WPS provider endpoint, either iterates over all available processes under it to register them one
    by one, or limit itself only to those of the reduced set specified by :paramref:`service_processes`.

    The registered `WPS-1` processes generate a **static** reference, meaning that metadata of each process as well
    as any other modifications to the real remote reference will not be tracked, including validation of even their
    actual existence, or modifications to inputs/outputs. The :term:`Application Package` will only point to it
    assuming it remains valid.

    Each of the deployed processes using *static* reference will be accessible directly under `Weaver` endpoints::

        /processes/<service-name>_<process-id>

    The service is **NOT** deployed as :term:`Provider` since the processes are registered directly.

    .. seealso::
        - :func:`register_wps_processes_dynamic`

    :param service_url: WPS-1 service location (where ``GetCapabilities`` and ``DescribeProcess`` requests can be made).
    :param service_name: Identifier to employ for generating the full process identifier.
    :param service_visibility: Visibility flag of the provider.
    :param service_processes: process IDs under the service to be registered, or all if empty.
    :param container: settings to retrieve required configuration settings.
    """
    db = get_db(container)
    process_store = db.get_store(StoreProcesses)  # type: StoreProcesses

    LOGGER.info("Fetching WPS-1: [%s]", service_url)
    wps = get_wps_client(service_url, container)
    if Version(wps.version) >= Version("2.0"):
        LOGGER.warning("Invalid WPS-1 provider, version was [%s]", wps.version)
        return
    wps_processes = [wps.describeprocess(p) for p in service_processes] or wps.processes
    for wps_process in wps_processes:
        proc_id = f"{service_name}_{get_sane_name(wps_process.identifier, min_len=1)}"
        wps_pid = wps_process.identifier
        proc_url = f"{service_url}?service=WPS&request=DescribeProcess&identifier={wps_pid}&version={wps.version}"
        svc_vis = Visibility.PUBLIC if service_visibility else Visibility.PRIVATE
        try:
            old_process = process_store.fetch_by_id(proc_id)
        except ProcessNotFound:
            pass
        else:
            if (
                old_process.id == proc_id
                and old_process.processDescriptionURL == proc_url
                and old_process.visibility == svc_vis
            ):
                LOGGER.warning("Process already registered: [%s]. Skipping...", proc_id)
                continue
            LOGGER.warning("Process matches registered one: [%s]. Updating details...", proc_id)
        payload = {
            "processDescription": {"process": {"id": proc_id, "visibility": svc_vis}},
            "executionUnit": [{"href": proc_url}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        try:
            resp = deploy_process_from_payload(payload, container, overwrite=True)
            if resp.status_code == HTTPOk.code:
                LOGGER.info("Process registered: [%s]", proc_id)
            else:
                raise RuntimeError(f"Process registration failed: [{proc_id}]")
        except Exception as ex:
            LOGGER.exception("Exception during process registration: [%r]. Skipping...", ex)
            continue


def register_wps_processes_dynamic(service_name, service_url, service_visibility, container):
    # type: (str, str, bool, AnyRegistryContainer) -> None
    """
    Register a WPS service ``provider`` such that ``processes`` under it are dynamically accessible on demand.

    The registered `WPS-1` provider generates a **dynamic** reference to processes under it. Only the :term:`Provider`
    reference itself is actually registered. No :term:`Process` are directly registered following this operation.

    When information about the offered processes, descriptions of those processes or their execution are requested,
    `Weaver` will query the referenced :term:`Provider` for details and convert the corresponding :term:`Process`
    dynamically. This means that latest metadata of the :term:`Process`, and any modification to it on the remote
    service will be immediately reflected on `Weaver` without any need to re-deploy processes.

    Each of the deployed processes using *dynamic* reference will be accessible under `Weaver` endpoints::

        /providers/<service-name>/processes/<process-id>

    The processes are **NOT** deployed locally since the processes are retrieved from the :term:`Provider` itself.

    .. seealso::
        - :func:`register_wps_processes_static`

    :param service_url: WPS-1 service location (where ``GetCapabilities`` and ``DescribeProcess`` requests can be made).
    :param service_name: Identifier to employ for registering the provider identifier.
    :param service_visibility: Visibility flag of the provider.
    :param container: settings to retrieve required configuration settings.
    """
    db = get_db(container)
    service_store = db.get_store(StoreServices)     # type: StoreServices

    LOGGER.info("Register WPS-1/2 provider: [%s]", service_url)
    try:
        get_wps_client(service_url, container)  # only attempt fetch to validate it exists
    except Exception as ex:
        LOGGER.exception("Exception during provider validation: [%s] [%r]. Skipping...", service_name, ex)
        return
    new_service = Service(name=service_name, url=service_url, public=service_visibility)
    try:
        old_service = service_store.fetch_by_name(service_name)
    except ServiceNotFound:
        LOGGER.info("Registering new provider: [%s]...", service_name)
    else:
        if new_service == old_service:
            LOGGER.warning("Provider already registered: [%s]. Skipping...", service_name)
            return
        LOGGER.warning("Provider matches registered service: [%s]. Updating details...", service_name)
    try:
        service_store.save_service(new_service, overwrite=True)
    except Exception as ex:
        LOGGER.exception("Exception during provider registration: [%s] [%r]. Skipping...", service_name, ex)


def register_wps_processes_from_config(container, wps_processes_file_path=None):
    # type: (AnySettingsContainer, Optional[FileSystemPathType]) -> None
    """
    Registers remote :term:`WPS` providers and/or processes as specified from the configuration file.

    Loads a ``wps_processes.yml`` file and registers  processes under :ref:`proc_wps_12` providers to the
    current `Weaver` instance as equivalent :term:`OGC API - Processes` instances.

    References listed under ``processes`` are registered statically (by themselves, unchanging snapshot).
    References listed under ``providers``, the :term:`WPS` themselves are registered, making each :term:`Process`
    listed in their ``GetCapabilities`` available. In this case, registered processes are defined dynamically,
    meaning they will be fetched on the provider each time a request refers to them, keeping their definition
    up-to-date with the remote server.

    .. versionadded:: 1.14
        When references are specified using ``providers`` section instead of ``processes``, the registration
        only saves the remote WPS provider endpoint to dynamically populate :term:`WPS` processes on demand.
        Previous behavior was to register each :term:`WPS` process individually with ID ``[service]_[process]``.

    .. versionchanged:: 4.19
        Parameter position are inverted.
        If :paramref:`wps_processes_file_path` is explicitly provided, it is used directly without considering settings.
        Otherwise, automatically employ the definition in setting: ``weaver.wps_processes_file``.

    .. seealso::
        - `weaver.wps_processes.yml.example` for additional file format details.

    .. note::
        Settings with an explicit empty ``weaver.wps_processes_file`` entry will be considered as *nothing to load*.
        If the entry is omitted, default location :data:`WEAVER_DEFAULT_WPS_PROCESSES_CONFIG` is attempted instead.

    :param container: Registry container to obtain database reference as well as application settings.
    :param wps_processes_file_path: Override file path to employ instead of default settings definition.
    """
    if wps_processes_file_path is not None:
        LOGGER.info("Using WPS-1 explicit override parameter to obtain file reference.")
    else:
        LOGGER.info("Using WPS-1 file reference from configuration settings.")
        settings = get_settings(container)
        wps_processes_file_path = settings.get("weaver.wps_processes_file")

    if wps_processes_file_path is None:
        warnings.warn("No file specified for WPS-1 providers registration.", RuntimeWarning)
        wps_processes_file_path = get_weaver_config_file("", WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
                                                         generate_default_from_example=False)
    elif wps_processes_file_path == "":
        warnings.warn("Configuration file for WPS-1 providers registration explicitly defined as empty in settings. "
                      "Not loading anything.", RuntimeWarning)
        return
    # reprocess the path in case it is relative to default config directory
    wps_processes_file_path = get_weaver_config_file(wps_processes_file_path, WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
                                                     generate_default_from_example=False)
    if wps_processes_file_path == "":
        warnings.warn("No file specified for WPS-1 providers registration.", RuntimeWarning)
        return
    LOGGER.info("Using WPS-1 provider processes file: [%s]", wps_processes_file_path)
    try:
        with open(wps_processes_file_path, mode="r", encoding="utf-8") as f:
            # if file is empty (not even processes/providers section), None is return instead of dict
            processes_config = yaml.safe_load(f) or {}
        if processes_config:
            processes = processes_config.get("processes") or []
            providers = processes_config.get("providers") or []
        else:
            processes = providers = None
        if not processes and not providers:
            LOGGER.warning("Nothing to process from file: [%s]", wps_processes_file_path)
            return

        # either 'service' references to register every underlying 'process' individually
        # or explicit 'process' references to register by themselves
        for cfg_service in processes:
            svc_name, svc_url, svc_proc, svc_vis = parse_wps_process_config(cfg_service)
            register_wps_processes_static(svc_url, svc_name, svc_vis, svc_proc, container)

        # direct WPS providers to register
        for cfg_service in providers:
            svc_name, svc_url, _, svc_vis = parse_wps_process_config(cfg_service)
            register_wps_processes_dynamic(svc_name, svc_url, svc_vis, container)

        LOGGER.info("Finished processing configuration file [%s].", wps_processes_file_path)
    except Exception as exc:  # pragma: no cover
        msg = f"Invalid WPS-1 providers configuration file caused: [{fully_qualified_name(exc)}]({exc!s})."
        LOGGER.exception(msg)
        raise RuntimeError(msg)


def _check_package_file(cwl_file_path_or_url):
    # type: (str) -> str
    """
    Validates that the specified :term:`CWL` file path or URL points to an existing and allowed file format.

    :param cwl_file_path_or_url: one of allowed file types path on disk, or an URL pointing to one served somewhere.
    :returns: validated absolute path or URL of the file reference.
    :raises PackageRegistrationError: in case of missing file, invalid format or invalid HTTP status code.
    """
    if is_remote_file(cwl_file_path_or_url):
        cwl_path = cwl_file_path_or_url
        cwl_resp = request_extra("head", cwl_path, settings=get_settings())
        if cwl_resp.status_code != HTTPOk.code:
            raise PackageRegistrationError(f"Cannot find CWL file at: '{cwl_path}'.")
    else:
        cwl_path = cwl_file_path_or_url[7:] if cwl_file_path_or_url.startswith("file://") else cwl_file_path_or_url
        cwl_path = os.path.abspath(cwl_path)
        if not os.path.isfile(cwl_path):
            raise PackageRegistrationError(f"Cannot find CWL file at: '{cwl_file_path_or_url}'.")

    file_ext = os.path.splitext(cwl_path)[-1].replace(".", "")
    if file_ext not in PACKAGE_EXTENSIONS:
        raise PackageRegistrationError(f"Not a valid CWL file type: '{file_ext}'.")
    return cwl_path


def is_cwl_package(package):
    # type: (Any) -> bool
    """
    Perform minimal validation of a :term:`CWL` package definition.
    """
    return isinstance(package, dict) and "cwlVersion" in package


def load_package_file(file_path):
    # type: (str) -> CWL
    """
    Loads the package in :term:`YAML`/:term:`JSON` format specified by the file path.
    """
    file_path = _check_package_file(file_path)
    try:
        file_data = load_file(file_path)
    except ValueError as ex:
        raise PackageRegistrationError(f"Package parsing generated an error: [{ex!s}]")
    if is_cwl_package(file_data):
        return file_data
    raise PackageRegistrationError(f"Package is not a valid CWL document: [{file_path}]")


def register_cwl_processes_from_config(container):
    # type: (AnySettingsContainer) -> int
    """
    Load multiple :term:`CWL` definitions from a directory to register corresponding :term:`Process`.

    .. versionadded:: 4.19

    Each individual :term:`CWL` definition must fully describe a :term:`Process` by itself. Therefore, an ``id`` must
    be available in the file to indicate the target deployment reference. In case of conflict, the existing database
    :term:`Process` will be overridden to ensure file updates are applied.

    Files are loaded in alphabetical order. If a :term:`Workflow` needs to refer to other processes, they should be
    named in way that dependencies will be resolvable prior to the registration of the :term:`Workflow` :term:`Process`.
    The resolved directory to search for :term:`CWL` will be traversed recursively.
    This, along with the name of :term:`CWL` files themselves, can be used to resolve order-dependent loading cases.
    Only ``.cwl`` extensions are considered to avoid invalid parsing of other files that could be defined in the shared
    configuration directory.

    .. note::
        Settings with an explicit empty ``weaver.cwl_processes_dir`` entry will be considered as *nothing to load*.
        If the entry is omitted, default location :data:`WEAVER_CONFIG_DIR` is used to search for :term:`CWL` files.

    :param container: Registry container to obtain database reference as well as application settings.
    :returns: Number of successfully registered processes from found :term:`CWL` files.
    """
    settings = get_settings(container)
    cwl_processes_dir = settings.get("weaver.cwl_processes_dir")

    if cwl_processes_dir is None:
        warnings.warn("No configuration setting [weaver.cwl_processes_dir] specified for CWL processes registration. "
                      f"Will use default location: [{WEAVER_CONFIG_DIR}]", RuntimeWarning)
        cwl_processes_dir = WEAVER_CONFIG_DIR
    elif cwl_processes_dir == "":
        warnings.warn("Configuration setting [weaver.cwl_processes_dir] for CWL processes registration "
                      "is explicitly defined as empty. Not loading anything.", RuntimeWarning)
        return 0

    if not os.path.isdir(cwl_processes_dir):
        warnings.warn(
            "Configuration setting [weaver.cwl_processes_dir] for CWL processes registration "
            f"is not an existing directory: [{cwl_processes_dir}]. Not loading anything.", RuntimeWarning
        )
        return 0
    cwl_processes_dir = os.path.abspath(cwl_processes_dir)
    cwl_files = sorted(pathlib.Path(cwl_processes_dir).rglob("*.cwl"),
                       # consider directory structure to sort, then use usual alphabetical order for same level
                       key=lambda file: (len(str(file).split("/")), str(file)))
    if not cwl_files:
        warnings.warn(
            f"Configuration directory [{cwl_processes_dir}] for CWL processes registration "
            "does not contain any CWL file. Not loading anything.", RuntimeWarning
        )
        return 0

    register_count = 0
    register_total = len(cwl_files)
    register_error = asbool(settings.get("weaver.cwl_processes_register_error", False))
    for cwl_path in cwl_files:
        try:
            cwl = load_package_file(str(cwl_path))
            deploy_process_from_payload(cwl, settings, overwrite=True)
            register_count += 1
        except (HTTPException, PackageRegistrationError) as exc:
            msg = (
                f"Failed registration of process from CWL file: [{cwl_path!s}] "
                f"caused by [{fully_qualified_name(exc)}]({exc!s})."
            )
            if register_error:
                LOGGER.info("Requested immediate CWL registration failure with 'weaver.cwl_processes_register_error'.")
                LOGGER.error(msg)
                raise
            warnings.warn(f"{msg} Skipping definition.", RuntimeWarning)
            continue
    if register_count and register_count == register_total:
        LOGGER.info("Successfully registered %s processes from CWL files.", register_total)
    elif register_count != register_total:
        LOGGER.warning("Partial registration of CWL processes, only %s/%s succeeded.", register_count, register_total)
    return register_count


def pull_docker(docker_auth, logger=LOGGER):
    # type: (DockerAuthentication, LoggerHandler) -> Optional[DockerClient]
    """
    Pulls the referenced Docker image to local cache from an optionally secured registry.

    If the Docker image is already available locally, simply validates it.
    Authentication are applied as necessary using the provided parameters.

    .. warning::
        Logging calls must employ the

    :param docker_auth: Docker reference with optional authentication parameters.
    :param logger: Alternative logger reference to log status messages about the operation.
    :returns: Docker client to perform further operations with the retrieved or validated image. None if failed.
    """
    client = None
    image = None
    ref = docker_auth.reference
    try:
        # load from env is the same as CLI call
        client = docker.from_env()  # pylint: disable=I1101
        # following login does not update '~/.docker/config.json' by design, but can use it if available
        # session remains active only within the client
        # Note:
        #   Force re-auth to ensure credentials are validated against remote registry and API Status is returned.
        #   This way, even if the auth were pre-resolved, we make sure they are still valid.
        #   This is important mostly because Docker images could still be present in cache, so pull doesn't occur.
        # Warning:
        #   Without re-auth, plain credentials resolved from auth config are returned in body instead!
        #   With re-auth, body *could* contain an identity token depending on auth method.
        if docker_auth.credentials:
            logger.log(logging.DEBUG, "Retrieving image [%s] from Docker registry or cache.", ref)
            body = client.login(reauth=True, **docker_auth.credentials)
            if body.get("Status") != "Login Succeeded":
                logger.log(
                    logging.DEBUG,
                    "Failed authentication to Docker private registry [%s].",
                    docker_auth.registry,
                )
                return None
        else:
            logger.log(logging.WARNING, "Expecting public access for image [%s] in Docker registry.", ref)
        logger.log(logging.DEBUG, "Retrieving image [%s] from Docker registry or cache.", ref)
        # docker client pulls all available images when no tag, provide the default to limit
        try:
            tag = docker_auth.tag or "latest"
            image = client.images.pull(docker_auth.repository, tag)  # actual pull or raise ImageNotFound
        except ImageNotFound:
            image = client.images.get(ref)  # resolved from cache or raise ImageNotFound
            LOGGER.warning("Failed pull of image [%s] from Docker registry, but found it in cache.", ref)
    except Exception as exc:  # noqa: W0703 # nosec: B110  # do not let anything up to avoid leaking auths
        logger.log(
            logging.DEBUG,
            "Unhandled exception [%s] during Docker registry authentication or image retrieval.",
            exc.__class__.__name__, exc_info=False,  # only class name to help debug, but no contents
        )
    if not image or docker_auth.docker not in image.tags:
        logger.log(
            logging.DEBUG,
            "Failed authorization or could not retrieve Docker image [%s] from private registry.",
            ref,
        )
        return None
    logger.log(logging.DEBUG, "Docker image [%s] retrieved.", ref)
    return client
