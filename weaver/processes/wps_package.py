"""
Representation of :term:`WPS` process with an internal :term:`CWL` package definition.

Functions and classes that offer interoperability and conversion between corresponding elements
defined as :term:`CWL` `CommandLineTool`/`Workflow` and :term:`WPS` `ProcessDescription` in order to
generate :term:`ADES`/:term:`EMS` deployable :term:`Application Package`.

.. seealso::
    - `CWL specification <https://www.commonwl.org/specification/>`_
    - `WPS-1/2 XML schemas <http://schemas.opengis.net/wps/>`_
    - `WPS-REST schemas <https://github.com/opengeospatial/wps-rest-binding>`_
    - :mod:`weaver.wps_restapi.api` conformance details
"""
import copy
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import uuid
from functools import cache
from typing import TYPE_CHECKING, cast, overload
from urllib.parse import parse_qsl, urlparse

import colander
import cwltool
import cwltool.docker
import cwltool.process
import yaml
from cwltool.context import LoadingContext, RuntimeContext
from cwltool.cwlprov.writablebagfile import close_ro, packed_workflow
from cwltool.factory import Factory as CWLFactory, WorkflowStatus as CWLException
from cwltool.process import shortname, use_custom_schema
from cwltool.secrets import SecretStore
from pyramid.httpexceptions import HTTPOk, HTTPServiceUnavailable
from pyramid.settings import asbool
from pywps import Process
from pywps.inout.basic import SOURCE_TYPE, DataHandler, FileHandler, IOHandler, NoneIOHandler
from pywps.inout.formats import Format
from pywps.inout.inputs import BoundingBoxInput, ComplexInput, LiteralInput
from pywps.inout.outputs import BoundingBoxOutput, ComplexOutput
from pywps.inout.storage import STORE_TYPE, CachedStorage
from pywps.inout.storage.file import FileStorage, FileStorageBuilder
from pywps.inout.storage.s3 import S3Storage, S3StorageBuilder
from pywps.validator import get_validator
from pywps.validator.base import emptyvalidator
from pywps.validator.mode import MODE
from requests.structures import CaseInsensitiveDict

from weaver.config import WeaverConfiguration, WeaverFeature, get_weaver_configuration
from weaver.database import get_db
from weaver.datatype import DockerAuthentication
from weaver.exceptions import (
    PackageAuthenticationError,
    PackageException,
    PackageExecutionError,
    PackageNotFound,
    PackageRegistrationError,
    PackageTypeError,
    PayloadNotFound
)
from weaver.formats import (
    DEFAULT_FORMAT,
    ContentType,
    clean_media_type_format,
    get_content_type,
    get_cwl_file_format,
    get_extension,
    get_format,
    map_cwl_media_type,
    repr_json
)
from weaver.processes import opensearch
from weaver.processes.constants import (
    CWL_NAMESPACE_CWLTOOL_URL,
    CWL_NAMESPACE_SCHEMA_ID,
    CWL_NAMESPACE_SCHEMA_METADATA_AUTHOR,
    CWL_NAMESPACE_SCHEMA_METADATA_CODE_REPOSITORY,
    CWL_NAMESPACE_SCHEMA_METADATA_CONTRIBUTOR,
    CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS,
    CWL_NAMESPACE_SCHEMA_METADATA_PERSON,
    CWL_NAMESPACE_SCHEMA_METADATA_SOFTWARE_VERSION,
    CWL_NAMESPACE_SCHEMA_METADATA_SUPPORTED,
    CWL_NAMESPACE_SCHEMA_METADATA_VERSION,
    CWL_NAMESPACE_SCHEMA_URL,
    CWL_NAMESPACE_WEAVER_DEFINITION,
    CWL_NAMESPACE_WEAVER_ID,
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_LOCAL,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_REMOTE,
    CWL_REQUIREMENT_APP_TYPES,
    CWL_REQUIREMENT_APP_WEAVER_CLASSES,
    CWL_REQUIREMENT_APP_WEAVER_DEFINITION,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_CUDA,
    CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS,
    CWL_REQUIREMENT_CUDA_NAME,
    CWL_REQUIREMENT_CUDA_NAMESPACE,
    CWL_REQUIREMENT_ENV_VAR,
    CWL_REQUIREMENT_RESOURCE,
    CWL_REQUIREMENT_SECRETS,
    CWL_REQUIREMENTS_SUPPORTED,
    IO_INPUT,
    IO_OUTPUT,
    PACKAGE_COMPLEX_TYPES,
    PACKAGE_DIRECTORY_TYPE,
    PACKAGE_EXTENSIONS,
    PACKAGE_FILE_TYPE
)
from weaver.processes.convert import (
    any2json_literal_data,
    cwl2wps_io,
    get_cwl_io_type,
    json2wps_field,
    json2wps_io,
    merge_package_io,
    normalize_ordered_io,
    ogcapi2cwl_process,
    resolve_cwl_namespaced_name,
    wps2json_io,
    xml_wps2cwl
)
from weaver.processes.sources import retrieve_data_source_url
from weaver.processes.types import ProcessType
from weaver.processes.utils import load_package_file, map_progress, pull_docker
from weaver.provenance import WeaverResearchObject
from weaver.status import STATUS_PYWPS_IDS, Status, StatusCompliant, map_status
from weaver.store.base import StoreJobs, StoreProcesses
from weaver.utils import (
    SUPPORTED_FILE_SCHEMES,
    Lazify,
    OutputMethod,
    adjust_directory_local,
    adjust_file_local,
    bytes2str,
    fetch_directory,
    fetch_file,
    fully_qualified_name,
    generate_diff,
    get_any_id,
    get_any_value,
    get_header,
    get_job_log_msg,
    get_log_date_fmt,
    get_log_fmt,
    get_sane_name,
    get_secure_directory_name,
    get_settings,
    list_directory_recursive,
    null,
    open_module_resource_file,
    request_extra,
    setup_loggers
)
from weaver.vault.utils import (
    decrypt_from_vault,
    get_authorized_file,
    get_vault_url,
    map_vault_location,
    parse_vault_token
)
from weaver.wps.storage import ReferenceStatusLocationStorage
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, AnyStr, Callable, Deque, Dict, List, Optional, Tuple, Type, Union

    from cwltool.factory import Callable as CWLFactoryCallable
    from cwltool.process import Process as ProcessCWL
    from owslib.wps import WPSExecution
    from pywps.response.execute import ExecuteResponse

    from weaver.datatype import Authentication, Job
    from weaver.processes.constants import CWL_RequirementCUDANameType, CWL_RequirementDockerGpuType, IO_Select_Type
    from weaver.processes.convert import ANY_IO_Type, JSON_IO_Type, PKG_IO_Type, WPS_Input_Type, WPS_Output_Type
    from weaver.status import AnyStatusType
    from weaver.typedefs import (
        AnyHeadersContainer,
        AnySettingsContainer,
        AnyValueType,
        CWL,
        CWL_AnyRequirementObject,
        CWL_AnyRequirements,
        CWL_Input_Type,
        CWL_IO_ComplexType,
        CWL_IO_Type,
        CWL_Requirement,
        CWL_RequirementNames,
        CWL_RequirementsDict,
        CWL_RequirementsList,
        CWL_Results,
        CWL_SchemaNames,
        CWL_SchemaSalad,
        CWL_ToolPathObject,
        CWL_WorkflowInputs,
        CWL_WorkflowStepPackage,
        CWL_WorkflowStepPackageMap,
        CWL_WorkflowStepReference,
        Default,
        ExecutionInputs,
        JobValueItem,
        JSON,
        Literal,
        Number,
        Path,
        ValueType
    )
    from weaver.wps.service import WorkerRequest


# NOTE:
#   Only use this logger for 'utility' methods (not residing under WpsPackage).
#   In that case, employ 'self.log_message' instead so that the executed process has its self-contained job log entries.
LOGGER = logging.getLogger(__name__)

# CWL package references
PACKAGE_DEFAULT_FILE_NAME = "package"
PACKAGE_OUTPUT_HOOK_LOG_UUID = "PACKAGE_OUTPUT_HOOK_LOG_{}"

# process execution progress
PACKAGE_PROGRESS_PREP_LOG = 1
PACKAGE_PROGRESS_LAUNCHING = 2
PACKAGE_PROGRESS_LOADING = 5
PACKAGE_PROGRESS_GET_INPUT = 6
PACKAGE_PROGRESS_ADD_EO_IMAGES = 7
PACKAGE_PROGRESS_CONVERT_INPUT = 8
PACKAGE_PROGRESS_PREPARATION = 9
PACKAGE_PROGRESS_CWL_RUN = 10
PACKAGE_PROGRESS_CWL_DONE = 95
PACKAGE_PROGRESS_PREP_OUT = 98
PACKAGE_PROGRESS_DONE = 100

PACKAGE_SCHEMA_CACHE = {}  # type: Dict[str, Tuple[str, str]]


def get_status_location_log_path(status_location, out_dir=None):
    # type: (str, Optional[str]) -> str
    log_path = f"{os.path.splitext(status_location)[0]}.log"
    return os.path.join(out_dir, os.path.split(log_path)[-1]) if out_dir else log_path


def retrieve_package_job_log(execution, job, progress_min=0, progress_max=100):
    # type: (WPSExecution, Job, Number, Number) -> None
    """
    Obtains the underlying WPS execution log from the status file to add them after existing job log entries.
    """
    try:
        # weaver package log every status update into this file (we no longer rely on the http monitoring)
        out_dir = get_wps_output_dir(get_settings())
        if job.context:
            out_dir = os.path.join(out_dir, job.context)
        # if the process is a weaver package this status xml should be available in the process output dir
        log_path = get_status_location_log_path(execution.statusLocation, out_dir=out_dir)
        with open(log_path, mode="r", encoding="utf-8") as log_file:
            log_lines = log_file.readlines()
        if not log_lines:
            return
        total = float(len(log_lines))
        for i, line in enumerate(log_lines):
            progress = map_progress(i / total * 100, progress_min, progress_max)
            job.save_log(message=line.rstrip("\n"), progress=progress, status=Status.RUNNING)
    except (KeyError, IOError):  # pragma: no cover
        LOGGER.warning("Failed retrieving package log for %s", job)


def get_process_location(process_id_or_url, data_source=None, container=None):
    # type: (Union[Dict[str, Any], str], Optional[str], Optional[AnySettingsContainer]) -> str
    """
    Obtains the URL of a WPS REST DescribeProcess given the specified information.

    :param process_id_or_url: process "identifier" or literal URL to DescribeProcess WPS-REST location.
    :param data_source: identifier of the data source to map to specific ADES, or map to localhost if ``None``.
    :param container: Container that provides access to application settings.
    :return: URL of EMS or ADES WPS-REST DescribeProcess.
    """
    # if an URL was specified, return it as is
    if urlparse(process_id_or_url).scheme != "":
        return process_id_or_url
    data_source_url = retrieve_data_source_url(data_source, container=container)
    process_id = get_sane_name(process_id_or_url, min_len=1)
    process_url = sd.process_service.path.format(process_id=process_id)
    return f"{data_source_url}{process_url}"


def get_package_workflow_steps(package_dict_or_url):
    # type: (Union[CWL, str]) -> List[CWL_WorkflowStepReference]
    """
    Obtain references to intermediate steps of a CWL workflow.

    :param package_dict_or_url: process package definition or literal URL to DescribeProcess WPS-REST location.
    :return: list of workflow steps as {"name": <name>, "reference": <reference>}
        where `name` is the generic package step name, and `reference` is the id/url of a registered WPS package.
    """
    if isinstance(package_dict_or_url, str):
        package_dict_or_url, _ = _get_process_package(package_dict_or_url)
    workflow_steps_ids = []
    package_type = _get_package_type(package_dict_or_url)
    if package_type == ProcessType.WORKFLOW:
        workflow_steps = package_dict_or_url.get("steps")
        for step in workflow_steps:
            step_package_ref = workflow_steps[step].get("run")
            # if a local file reference was specified, convert it to process id
            package_ref_name, package_ref_ext = os.path.splitext(step_package_ref)
            if urlparse(step_package_ref).scheme == "" and package_ref_ext.replace(".", "") in PACKAGE_EXTENSIONS:
                step_package_ref = package_ref_name
            workflow_steps_ids.append({"name": step, "reference": step_package_ref})
    return workflow_steps_ids


def _fetch_process_info(process_info_url, fetch_error, container=None):
    # type: (str, Type[Exception], Optional[AnySettingsContainer]) -> JSON
    """
    Fetches the JSON process information from the specified URL and validates that it contains something.

    :raises fetch_error: provided exception with URL message if the process information could not be retrieved.
    """
    def _info_not_found_error():
        return fetch_error(f"Could not find reference: '{process_info_url!s}'")

    if not isinstance(process_info_url, str):
        raise _info_not_found_error()
    settings = get_settings(container)
    resp = request_extra("get", process_info_url, headers={"Accept": ContentType.APP_JSON}, settings=settings)
    if resp.status_code != HTTPOk.code:
        raise _info_not_found_error()
    body = resp.json()
    if not isinstance(body, dict) or not len(body):
        raise _info_not_found_error()
    return body


def _get_process_package(process_url, container=None):
    # type: (str, Optional[AnySettingsContainer]) -> Tuple[CWL, str]
    """
    Retrieves the WPS process package content from given process ID or literal URL.

    :param process_url: process literal URL to DescribeProcess WPS-REST location.
    :return: tuple of package body as dictionary and package reference name.
    """
    package_url = f"{process_url}/package"
    package_body = _fetch_process_info(package_url, PackageNotFound, container=container)
    package_name = process_url.split("/")[-1]
    return package_body, package_name


def _get_process_payload(process_url, container=None):
    # type: (str, Optional[AnySettingsContainer]) -> JSON
    """
    Retrieves the WPS process payload content from given process ID or literal URL.

    :param process_url: process literal URL to DescribeProcess WPS-REST location.
    :return: payload body as dictionary.
    """
    process_url = get_process_location(process_url)
    payload_url = f"{process_url}/payload"
    payload_body = _fetch_process_info(payload_url, PayloadNotFound, container=container)
    return payload_body


def _get_package_type(package_dict):
    # type: (CWL) -> Literal[ProcessType.APPLICATION, ProcessType.WORKFLOW]
    return ProcessType.WORKFLOW if package_dict.get("class", "").lower() == "workflow" else ProcessType.APPLICATION


def _get_package_requirements_normalized(requirements, as_dict=False):
    # type: (CWL_AnyRequirements, bool) -> CWL_AnyRequirements
    """
    Converts :term:`CWL` package ``requirements`` or ``hints`` into :class:`list` or :class:`dict` representation.

    Uniformization of :term:`CWL` ``requirements`` or ``hints`` into the :class:`list` representation (default)
    or as :class:`dict` if requested, whether the input definitions where provided using the dictionary definition
    as ``{"<req-class>": {<params>}}`` or  the list of dictionary requirements ``[{<req-class + params>}]``
    each with a ``class`` key.
    """
    if isinstance(requirements, dict):
        if as_dict:
            return {req: dict(params) for req, params in requirements.items()}  # ensure literals instead of dict-like
        reqs = []
        for req in requirements:
            reqs.append({"class": req})
            reqs[-1].update(requirements[req] or {})
        return reqs
    # ensure list-of-dict instead of sequence of dict-like
    reqs = [dict(req) for req in requirements]  # type: CWL_RequirementsList
    if as_dict:
        return cast(
            "CWL_RequirementsDict",
            {req.pop("class"): req for req in reqs}  # noqa
        )
    return reqs


def _patch_cuda_requirement(package, app_pkg_req, patch_requirement):
    # type: (CWL, CWL_Requirement, Union[CWL_RequirementCUDANameType, CWL_RequirementDockerGpuType]) -> CWL
    """
    Updates legacy :term:`CWL` definitions for combinations of `CUDA` and `Docker` requirements and/or hints.
    """
    # backup original for later compare and find requirements of interest
    # requirements unrelated to update must remain in same locations and formats to preserve behavior
    r_original = package.get("requirements", {})
    h_original = package.get("hints", {})
    r_list = _get_package_requirements_normalized(r_original)
    h_list = _get_package_requirements_normalized(h_original)
    search_reqs = {patch_requirement, CWL_REQUIREMENT_CUDA_NAME}
    r_no_patched = list(filter(lambda _req: not _req["class"].endswith(patch_requirement), r_list))
    h_no_patched = list(filter(lambda _req: not _req["class"].endswith(patch_requirement), h_list))
    r_other = list(filter(lambda _req: not any(_req["class"].endswith(name) for name in search_reqs), r_no_patched))
    h_other = list(filter(lambda _req: not any(_req["class"].endswith(name) for name in search_reqs), h_no_patched))
    r_cuda = list(filter(lambda _req: _req["class"].endswith(CWL_REQUIREMENT_CUDA_NAME), r_list))
    h_cuda = list(filter(lambda _req: _req["class"].endswith(CWL_REQUIREMENT_CUDA_NAME), h_list))
    if patch_requirement.endswith(CWL_REQUIREMENT_APP_DOCKER_GPU):
        app_pkg_req["class"] = CWL_REQUIREMENT_APP_DOCKER  # GPU to official Docker requirement (preserve other params)
    else:
        app_pkg_req = {}  # updating only namespaced CUDA requirement, no application pacakge requirement
    if (r_cuda and h_cuda) or len(r_cuda) > 1 or len(h_cuda) > 1:
        h_cuda = [] if r_cuda else h_cuda
        LOGGER.warning(
            "Detected multiple CUDA requirements/hints employed simultaneously. "
            "Will keep only the first definition, with prioritized requirements over hints. "
            "Remaining items will be ignored."
        )
    cuda_req = r_cuda or h_cuda
    cuda_found = bool(cuda_req)
    # if CUDA not explicitly provided along the older GPU requirement, define default, otherwise reuse
    cuda_req = CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS.copy() if not cuda_req else cuda_req[0]
    cuda_req["class"] = CWL_REQUIREMENT_CUDA  # force always with namespace
    r_app_pkg = [app_pkg_req] if app_pkg_req and r_list != r_other and h_list == h_no_patched else []
    h_app_pkg = [app_pkg_req] if app_pkg_req and h_list != h_other and r_list == r_no_patched else []
    if not cuda_found:  # apply default in same place as the application requirement
        r_cuda = [cuda_req] if r_app_pkg else []
        h_cuda = [cuda_req] if h_app_pkg else []
    r_list = r_app_pkg + r_cuda + r_other
    h_list = h_app_pkg + h_cuda + h_other
    # revert list conversion if necessary
    r_list = _get_package_requirements_normalized(r_list, as_dict=isinstance(r_original, dict))
    h_list = _get_package_requirements_normalized(h_list, as_dict=isinstance(h_original, dict))
    if r_list:
        package["requirements"] = r_list
    if h_list:
        package["hints"] = h_list
    package.setdefault("$namespaces", {})
    package["$namespaces"].update(dict(CWL_REQUIREMENT_CUDA_NAMESPACE))
    return package


def _update_package_compatibility(package):
    # type: (CWL) -> CWL
    """
    Update a :term:`CWL` package with backward compatibility changes if applicable.
    """
    package_original = copy.deepcopy(package)
    package_type = _get_package_type(package)
    if package_type == ProcessType.APPLICATION:
        app_pkg_req = get_application_requirement(package, validate=False, required=False)
        if app_pkg_req["class"].endswith(CWL_REQUIREMENT_APP_DOCKER_GPU):
            _patch_cuda_requirement(package, app_pkg_req, CWL_REQUIREMENT_APP_DOCKER_GPU)
            LOGGER.warning(
                "CWL package definition updated using '%s' backward-compatibility definition. "
                "Consider updating the Application Package with relevant changes to avoid this warning.\n%s",
                CWL_REQUIREMENT_APP_DOCKER_GPU,
                generate_diff(package_original, package, val_name="Original CWL", ref_name="Updated CWL")
            )
        # CUDA requirement missing cwltool-specific namespace
        # This is not considered an Application Package requirement for a process by itself.
        # Therefore, all requirements/hints must be checked as 'get_application_requirement' will not return it.
        elif any(
            req["class"] == CWL_REQUIREMENT_CUDA_NAME for req in
            _get_package_requirements_normalized(package.get("requirements", [])) +
            _get_package_requirements_normalized(package.get("hints", []))
        ):
            _patch_cuda_requirement(package, app_pkg_req, CWL_REQUIREMENT_CUDA_NAME)
            LOGGER.warning(
                "CWL package definition with '%s' updated using namespaced '%s' definition. "
                "Consider updating the Application Package with relevant changes to avoid this warning.\n%s",
                CWL_REQUIREMENT_CUDA_NAME, CWL_REQUIREMENT_CUDA,
                generate_diff(package_original, package, val_name="Original CWL", ref_name="Updated CWL")
            )
        # weaver-specific requirements extensions with namespaced specification
        elif (
            not app_pkg_req["class"].startswith(f"{CWL_NAMESPACE_WEAVER_ID}:")
            and any(app_pkg_req["class"].endswith(req) for req in CWL_REQUIREMENT_APP_WEAVER_CLASSES)
        ):
            weaver_hint = app_pkg_req["class"]  # type: CWL_RequirementNames  # noqa
            weaver_req = f"{CWL_NAMESPACE_WEAVER_ID}:{weaver_hint}"  # type: CWL_RequirementNames  # noqa
            app_pkg_hints = package.get("hints", [])  # don't need to check requirements (would not have worked anyway)
            if isinstance(app_pkg_hints, dict):
                hint = app_pkg_hints.pop(weaver_hint)
                app_pkg_hints[weaver_req] = hint
            else:
                for hint in app_pkg_hints:
                    if hint["class"] == weaver_hint:
                        hint["class"] = weaver_req
                        break
            package.setdefault("$namespaces", {})
            package["$namespaces"].update(CWL_NAMESPACE_WEAVER_DEFINITION)
            LOGGER.warning(
                "CWL package definition with '%s' updated using namespaced '%s' definition. "
                "Consider updating the Application Package with relevant changes to avoid this warning.\n%s",
                weaver_hint, weaver_req,
                generate_diff(package_original, package, val_name="Original CWL", ref_name="Updated CWL")
            )
    return package


@cache
def _load_weaver_extensions_schema():
    # type: () -> CWL_SchemaSalad
    LOGGER.debug("Loading Weaver schema extensions...")
    with open_module_resource_file("weaver", "schemas/cwl/weaver-extensions.yml") as r_file:
        weaver_schema = yaml.safe_load(r_file)
    return weaver_schema


def _load_supported_schemas():
    # type: () -> None
    """
    Loads :term:`CWL` schemas supported by `Weaver` to avoid validation errors when provided in requirements.

    Use a similar strategy as :func:`cwltool.main.setup_schema`, but skipping the :term:`CLI` context and limiting
    loaded schema definitions to those that `Weaver` allows. Drops extensions that could cause misbehaving
    functionalities when other :term:`Process` types than :term:`CWL`-based :term:`Application Package` are used.

    This operation must be called before the :class:`CWLFactory` attempts loading and validating a :term:`CWL` document.
    """
    # explicitly omit dev versions, only released versions allowed
    extension_resources = {
        "v1.0": "extensions.yml",
        "v1.1": "extensions-v1.1.yml",
        "v1.2": "extensions-v1.2.yml",
    }
    for version, ext_version_file in extension_resources.items():
        # use our own cache on top of cwltool cache to distinguish between 'v1.x' names
        # pointing at "CWL standard", "cwltool-flavored extensions" or "weaver-flavored extensions"
        if version in PACKAGE_SCHEMA_CACHE:
            LOGGER.debug("Reusing cached CWL %s schema extensions.", version)
            continue
        LOGGER.debug("Loading CWL %s schema extensions...", version)
        with open_module_resource_file(cwltool, ext_version_file) as r_file:
            schema = yaml.safe_load(r_file)

        weaver_ext_schema = _load_weaver_extensions_schema()
        extensions_weaver = weaver_ext_schema["$graph"]
        schema.setdefault("$namespaces", {})
        schema["$namespaces"].update(weaver_ext_schema.get("$namespaces", {}))

        extensions_cwl = schema["$graph"]
        extensions_supported = []
        extensions_imports = []
        extensions_enabled = set()
        extensions_dropped = set()
        for ext in extensions_cwl + extensions_weaver:
            if "name" not in ext and "$import" in ext:
                extensions_imports.append(ext)
                continue
            ext_name = ext["name"]
            if ext_name in CWL_REQUIREMENTS_SUPPORTED:
                extensions_enabled.add(ext_name)
                extensions_supported.append(ext)
            else:
                extensions_dropped.add(ext_name)
        extensions_enabled = sorted(list(extensions_enabled))
        extensions_dropped = sorted(list(extensions_dropped))
        LOGGER.debug(
            "Configuring CWL %s schema extensions:\n  Enabled: %s\n  Dropped: %s",
            version, extensions_enabled, extensions_dropped,
        )
        schema["$graph"] = extensions_imports + extensions_supported

        schema_data = bytes2str(yaml.safe_dump(schema, encoding="utf-8", sort_keys=False))
        schema_base = CWL_NAMESPACE_CWLTOOL_URL.split("#", 1)[0]
        use_custom_schema(version, schema_base, schema_data)
        PACKAGE_SCHEMA_CACHE[version] = (schema_base, schema_data)

    # ensure that any weaver-namespaced requirement can be loaded by cwltool
    cwltool.process.supportedProcessRequirements.extend(set(CWL_REQUIREMENT_APP_WEAVER_DEFINITION.values()))


@overload
def _load_package_content(package_dict,                             # type: CWL
                          package_name=PACKAGE_DEFAULT_FILE_NAME,   # type: str
                          data_source=None,                         # type: Optional[str]
                          only_dump_file=False,                     # type: Literal[True]
                          tmp_dir=None,                             # type: Optional[str]
                          loading_context=None,                     # type: Optional[LoadingContext]
                          runtime_context=None,                     # type: Optional[RuntimeContext]
                          process_offering=None,                    # type: Optional[JSON]
                          container=None,                           # type: Optional[AnySettingsContainer]
                          ):                                        # type: (...) -> None
    ...


@overload
def _load_package_content(package_dict,                             # type: CWL
                          package_name=PACKAGE_DEFAULT_FILE_NAME,   # type: str
                          data_source=None,                         # type: Optional[str]
                          only_dump_file=False,                     # type: Literal[False]
                          tmp_dir=None,                             # type: Optional[str]
                          loading_context=None,                     # type: Optional[LoadingContext]
                          runtime_context=None,                     # type: Optional[RuntimeContext]
                          process_offering=None,                    # type: Optional[JSON]
                          container=None,                           # type: Optional[AnySettingsContainer]
                          ):  # type: (...) -> Tuple[CWLFactoryCallable, str, CWL_WorkflowStepPackageMap]
    ...


def _load_package_content(package_dict,                             # type: CWL
                          package_name=PACKAGE_DEFAULT_FILE_NAME,   # type: str
                          data_source=None,                         # type: Optional[str]
                          only_dump_file=False,                     # type: bool
                          tmp_dir=None,                             # type: Optional[str]
                          loading_context=None,                     # type: Optional[LoadingContext]
                          runtime_context=None,                     # type: Optional[RuntimeContext]
                          process_offering=None,                    # type: Optional[JSON]
                          container=None,                           # type: Optional[AnySettingsContainer]
                          ):  # type: (...) -> Optional[Tuple[CWLFactoryCallable, str, CWL_WorkflowStepPackageMap]]
    """
    Loads :term:`CWL` package definition using various contextual resources.

    Following operations are accomplished to validate the package:

    - Starts by resolving any intermediate sub-packages steps if the parent package is a :term:`Workflow`
      in order to recursively generate and validate their process and package, potentially using remote reference.
      Each of the following operations are applied to every step individually.
    - Package I/O are reordered using any reference process offering hints if provided to generate consistent results.
    - Perform backward compatibility checks and conversions to the package if applicable.
    - The resulting package definition is dumped to a temporary JSON file, to validate the content can be serialized.
    - Optionally, the :term:`CWL` factory is employed to create the application runner, validating any provided loading
      and runtime contexts, and considering all resolved :term:`Workflow` steps if applicable, or the atomic application
      otherwise.

    :param package_dict: Package content representation as a dictionary.
    :param package_name: Name to use to create the package file and :term:`CWL` identifiers.
    :param data_source:
        Identifier of the :term:`Data Source` to map to specific :term:`ADES`, or map to ``localhost`` if ``None``.
    :param only_dump_file: Specify if the :class:`CWLFactoryCallable` should be validated and returned.
    :param tmp_dir: Location of the temporary directory to dump files (deleted on exit).
    :param loading_context: :mod:`cwltool` context used to create the :term:`CWL` package.
    :param runtime_context: :mod:`cwltool` context used to execute the :term:`CWL` package.
    :param process_offering: :term:`JSON` body of the process description payload (used as I/O hint ordering).
    :param container: Container that provides access to application settings.
    :returns:
        If :paramref:`only_dump_file` is ``True``, returns ``None``.
        Otherwise, :class:`tuple` of:

        - Instance of :class:`CWLFactoryCallable`
        - Package type (:attr:`ProcessType.WORKFLOW` or :attr:`ProcessType.APPLICATION`)
        - Package sub-steps definitions if package represents a :attr:`ProcessType.WORKFLOW`. Otherwise, empty mapping.
          Mapping of each step name contains their respective package ID and :term:`CWL` definition that must be run.

    .. warning::
        Specified :paramref:`tmp_dir` will be deleted on exit.
    """

    tmp_dir = tmp_dir or tempfile.mkdtemp()
    tmp_json_cwl = os.path.join(tmp_dir, package_name)

    # for workflows, retrieve each 'sub-package' file
    package_dict = _update_package_compatibility(package_dict)
    package_type = _get_package_type(package_dict)
    workflow_steps = get_package_workflow_steps(package_dict)
    step_packages = {}
    for step in workflow_steps:
        # generate sub-package file and update workflow step to point to it
        step_process_url = get_process_location(step["reference"], data_source, container=container)
        package_body, package_name = _get_process_package(step_process_url, container=container)
        _load_package_content(
            package_body,
            package_name,
            tmp_dir=tmp_dir,
            data_source=data_source,
            loading_context=loading_context,
            runtime_context=runtime_context,
            container=container,
            only_dump_file=True,
        )
        step_name = step["name"]
        package_dict["steps"][step_name]["run"] = package_name
        step_packages[step_name] = {"id": package_name, "package": package_body}

    # fix I/O to preserve ordering from dump/load, and normalize them to consistent list of objects
    process_offering_hint = process_offering or {}
    package_input_hint = process_offering_hint.get("inputs", [])
    package_output_hint = process_offering_hint.get("outputs", [])
    package_dict["inputs"] = normalize_ordered_io(package_dict["inputs"], order_hints=package_input_hint)
    package_dict["outputs"] = normalize_ordered_io(package_dict["outputs"], order_hints=package_output_hint)

    with open(tmp_json_cwl, mode="w", encoding="utf-8") as f:
        json.dump(package_dict, f)
    if only_dump_file:
        return

    _load_supported_schemas()
    factory = CWLFactory(loading_context=loading_context, runtime_context=runtime_context)
    package = factory.make(tmp_json_cwl)  # type: CWLFactoryCallable
    shutil.rmtree(tmp_dir)
    return package, package_type, step_packages


def _merge_package_inputs_outputs(wps_inputs_defs,      # type: Union[List[ANY_IO_Type], Dict[str, ANY_IO_Type]]
                                  cwl_inputs_list,      # type: List[WPS_Input_Type]
                                  wps_outputs_defs,     # type: Union[List[ANY_IO_Type], Dict[str, ANY_IO_Type]]
                                  cwl_outputs_list,     # type: List[WPS_Output_Type]
                                  ):                    # type: (...) -> Tuple[List[JSON_IO_Type], List[JSON_IO_Type]]
    """
    Merges corresponding metadata of I/O definitions from :term:`CWL` and :term:`WPS` sources.

    Merges I/O definitions to use for process creation and returned by ``GetCapabilities``, ``DescribeProcess``
    using the `WPS` specifications (from request ``POST``) and `CWL` specifications (extracted from file).

    .. note::
        Parameters :paramref:`cwl_inputs_list` and :paramref:`cwl_outputs_list` are expected to be
        in :term:`WPS`-like format (i.e.: :term:`CWL` I/O converted to corresponding :term:`WPS` I/O objects).

    .. seealso::
        Conversion of :term:`CWL` to :term:`WPS`-equivalent objects is handled by :func:`_get_package_inputs_outputs`
        and its underlying functions.

    :param wps_inputs_defs: list or mapping of provided :term:`WPS` input definitions.
    :param cwl_inputs_list: processed list of :term:`CWL` inputs from the :term:`Application Package`.
    :param wps_outputs_defs: list or mapping of provided :term:`WPS` output definitions.
    :param cwl_outputs_list: processed list of :term:`CWL` inputs from the :term:`Application Package`.
    :returns:
        Tuple of (inputs, outputs) consisting of lists of I/O with merged contents between :term:`CWL` and :term:`WPS`.
    """
    wps_inputs_defs = normalize_ordered_io(wps_inputs_defs)
    wps_outputs_defs = normalize_ordered_io(wps_outputs_defs)
    wps_inputs_merged = merge_package_io(wps_inputs_defs, cwl_inputs_list, IO_INPUT)
    wps_outputs_merged = merge_package_io(wps_outputs_defs, cwl_outputs_list, IO_OUTPUT)
    return wps_inputs_merged, wps_outputs_merged


def _get_package_io(package_factory, io_select, as_json):
    # type: (CWLFactoryCallable, IO_Select_Type, bool) -> List[PKG_IO_Type]
    """
    Retrieves I/O definitions from a validated :class:`CWLFactoryCallable`.

    .. seealso::
        Factory can be obtained with validation using :func:`_load_package_content`.

    :param package_factory: :term:`CWL` factory that contains I/O references to the package definition.
    :param io_select: either :data:`IO_INPUT` or :data:`IO_OUTPUT` according to what needs to be processed.
    :param as_json: toggle to the desired output type.
        If ``True``, converts the I/O definitions into :term:`JSON` representation.
        If ``False``, converts the I/O definitions into :term:`WPS` objects.
    :returns: I/O format depending on value :paramref:`as_json`.
    """
    if io_select == IO_OUTPUT:
        io_attrib = "outputs_record_schema"
    elif io_select == IO_INPUT:
        io_attrib = "inputs_record_schema"
    else:
        raise PackageTypeError(f"Unknown I/O selection: '{io_select}'.")
    cwl_package_io = getattr(package_factory.t, io_attrib)
    wps_package_io = [cwl2wps_io(io_item, io_select) for io_item in cwl_package_io["fields"]]
    if as_json:
        return [wps2json_io(io) for io in wps_package_io]
    return wps_package_io


def _get_package_inputs_outputs(package_factory,    # type: CWLFactoryCallable
                                as_json=False,      # type: bool
                                ):                  # type: (...) -> Tuple[List[PKG_IO_Type], List[PKG_IO_Type]]
    """
    Generates :term:`WPS`-like ``(inputs, outputs)`` tuple using parsed CWL package definitions.
    """
    return (_get_package_io(package_factory, io_select=IO_INPUT, as_json=as_json),
            _get_package_io(package_factory, io_select=IO_OUTPUT, as_json=as_json))


def _update_package_metadata(wps_metadata, cwl_package):
    # type: (JSON, CWL) -> None
    """
    Updates the package :term:`WPS` metadata dictionary from extractable `CWL` package definition.
    """
    wps_metadata["title"] = wps_metadata.get("title", cwl_package.get("label", ""))
    wps_metadata["abstract"] = wps_metadata.get("abstract", cwl_package.get("doc", ""))

    if (
        CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS in cwl_package and
        isinstance(cwl_package[CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS], list)
    ):
        wps_metadata["keywords"] = list(
            set(wps_metadata.get("keywords", [])) |
            set(cwl_package.get(CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS, []))
        )

    # specific use case with a different mapping
    # https://docs.ogc.org/bp/20-089r1.html#toc31
    if (
        CWL_NAMESPACE_SCHEMA_METADATA_VERSION in cwl_package or
        CWL_NAMESPACE_SCHEMA_METADATA_SOFTWARE_VERSION in cwl_package
    ):
        version_value = (
            wps_metadata.get("version")
            or cwl_package.get(CWL_NAMESPACE_SCHEMA_METADATA_VERSION)
            or cwl_package.get(CWL_NAMESPACE_SCHEMA_METADATA_SOFTWARE_VERSION)
        )
        # Only set the key if version_value is not empty or null
        if version_value:
            wps_metadata["version"] = str(version_value)
    else:
        version_value = wps_metadata.get("version")
        if version_value:
            wps_metadata["version"] = str(version_value)

    schema_ns = f"{CWL_NAMESPACE_SCHEMA_ID}:"
    metadata = wps_metadata.get("metadata", [])
    for meta_name in CWL_NAMESPACE_SCHEMA_METADATA_SUPPORTED:
        if meta_name in [  # skip handled above
            CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS,
            CWL_NAMESPACE_SCHEMA_METADATA_VERSION,
            CWL_NAMESPACE_SCHEMA_METADATA_SOFTWARE_VERSION,
        ]:
            continue

        meta_uri = meta_name.replace(schema_ns, CWL_NAMESPACE_SCHEMA_URL)

        # CWL package => WPS context
        if meta_name in cwl_package:
            if (
                isinstance(cwl_package[meta_name], str)
                and urlparse(cwl_package[meta_name]).scheme != ""
            ):
                url = cwl_package[meta_name]
                if meta_name == CWL_NAMESPACE_SCHEMA_METADATA_CODE_REPOSITORY:
                    ctype = ContentType.TEXT_HTML
                else:
                    ctype = get_content_type(os.path.splitext(url)[-1], default=ContentType.TEXT_PLAIN)
                metadata.append({
                    "type": ctype,
                    "rel": meta_uri,
                    "href": cwl_package[meta_name]
                })
            elif isinstance(cwl_package[meta_name], str):
                metadata.append({
                    "role": meta_uri,
                    "value": cwl_package[meta_name]
                })
            else:
                for objects in cwl_package[meta_name]:
                    class_name = objects["class"].strip(schema_ns)
                    value = {
                        "$schema": f"{CWL_NAMESPACE_SCHEMA_URL}{class_name}"
                    }
                    for key, val in objects.items():
                        if key.startswith(schema_ns):
                            value[key.strip(schema_ns)] = val
                    metadata.append({
                        "role": meta_uri,
                        "value": value
                    })
            wps_metadata["metadata"] = metadata

        # CWL package <= WPS context
        # note:
        #   this mapping is accomplished only if the CWL did not already result in creating the other mapping
        #   purposely avoid overriding a field already provided in CWL (the "truth"), even if they mismatch
        #   this could be done on purpose, such as attributing different authors for the process vs package
        else:
            metadata_found = [meta for meta in metadata if (meta.get("role") or meta.get("rel")) == meta_uri]
            if not metadata_found:
                continue
            metadata_found = copy.deepcopy(metadata_found)
            if meta_name in [CWL_NAMESPACE_SCHEMA_METADATA_AUTHOR, CWL_NAMESPACE_SCHEMA_METADATA_CONTRIBUTOR]:
                for meta in metadata_found:
                    if "value" not in meta or not isinstance(meta["value"], dict):
                        continue  # pragma: no cover  # sanity check, should not happen (fails validation)
                    meta_schema = meta.get("$schema", "").replace(CWL_NAMESPACE_SCHEMA_URL, schema_ns)
                    meta_schema = meta_schema or CWL_NAMESPACE_SCHEMA_METADATA_PERSON
                    meta["class"] = meta_schema
                    meta.pop("role", None)
                    meta.pop("$schema", None)
                    meta["value"].pop("$schema", None)
                    meta_value = meta.pop("value")
                    for field in list(meta_value):
                        field_ns = f"{CWL_NAMESPACE_SCHEMA_ID}:{field}"
                        meta[field_ns] = meta_value.pop(field)
                cwl_package[meta_name] = metadata_found

            # all other fields must be a single string
            # ignore others to avoid injecting unknown structures that could break the CWL
            elif len(metadata_found) == 1:
                meta_key = get_any_value(metadata_found[0], key=True)
                meta_value = metadata_found[0][meta_key]
                if not isinstance(meta_value, str):
                    continue  # pragma: no cover  # sanity check, should not happen (fails validation)
                cwl_package[meta_name] = meta_value


def _patch_wps_process_description_url(reference, process_hint):
    # type: (str, Optional[JSON]) -> str
    """
    Rebuilds a :term:`WPS` ``ProcessDescription`` URL from other details.

    A ``GetCapabilities`` request can be submitted with an ID in query params directly.
    Otherwise, check if a process hint can provide the ID.
    """
    parts = reference.split("?", 1)
    if len(parts) == 2:
        url, query = parts
        params = CaseInsensitiveDict(parse_qsl(query))
        process_id = get_any_id(params)
        if not process_id:
            process_id = get_any_id(process_hint or {})
            if process_id:
                params["identifier"] = process_id
        if process_id and params.get("request", "").lower() == "getcapabilities":
            params["request"] = "DescribeProcess"
        query = "&".join([f"{key}={val}" for key, val in params.items()])
        reference = f"{url}?{query}"
    return reference


def _generate_process_with_cwl_from_reference(reference, process_hint=None):
    # type: (str, Optional[JSON]) -> Tuple[CWL, JSON]
    """
    Resolves the ``reference`` type representing a remote :term:`Process` and generates a `CWL` ``package`` for it.

    The reference can point to any definition amongst below known structures:
    - :term:`CWL`
    - :term:`WPS`-1/2
    - :term:`WPS-REST`
    - :term:`OGC API - Processes`

    Additionally, provides minimal :term:`Process` details retrieved from the ``reference``.
    The number of details obtained will depend on available parameters from its description as well
    as the number of metadata that can be mapped between it and the generated :term:`CWL` package.

    The resulting :term:`Process` and its :term:`CWL` will correspond to a remote instance to which execution should
    be dispatched and monitored, except if the reference was directly a :term:`CWL` file.

    .. warning::
        Only conversion of the reference into a potential :term:`CWL` definition is accomplished by this function.
        Further validations must still be applied to ensure the loaded definition is valid and meets all requirements.

    .. seealso::
        - :class:`weaver.processes.ogc_api_process.OGCAPIRemoteProcess`
        - :class:`weaver.processes.wps1_process.Wps1Process`
        - :class:`weaver.processes.wps3_process.Wps3Process`
    """
    cwl_package = None
    process_info = {}

    # match against direct CWL reference
    reference_path, reference_ext = os.path.splitext(reference)
    reference_name = os.path.split(reference_path)[-1]
    if reference_ext.replace(".", "") in PACKAGE_EXTENSIONS:
        try:
            cwl_package = load_package_file(reference)
        except PackageRegistrationError as exc:
            LOGGER.debug("Skipping reference [%s] not matching a valid CWL package due to [%s]", reference, exc)
        process_info = {"identifier": reference_name}

    # match reference against WPS-1/2 or WPS-3/OGC-API (with CWL href) or CWL (without extension, e.g.: API endpoint)
    if not cwl_package:
        settings = get_settings()
        # since WPS-1/2 servers can sometimes reply with an error if missing query parameters, provide them
        # even in the case of potential *OGC API - Processes* reference since we don't know yet what it refers to
        ref_wps = _patch_wps_process_description_url(reference, process_hint)
        response = request_extra("GET", ref_wps, retries=3, settings=settings)
        if response.status_code != HTTPOk.code:
            raise HTTPServiceUnavailable(
                f"Couldn't obtain a valid response from [{ref_wps}]. "
                f"Service response: [{response.status_code} {response.reason}]"
            )
        content_type = get_header("Content-Type", response.headers, default="")
        ogc_api_ctypes = {
            ContentType.APP_JSON,
            ContentType.APP_YAML,
            ContentType.APP_OGC_PKG_JSON,
            ContentType.APP_OGC_PKG_YAML,
        }.union(ContentType.ANY_CWL)
        ogc_api_json = {ctype for ctype in ogc_api_ctypes if ctype.endswith("json")}

        # try to detect incorrectly reported media-type using common structures
        if ContentType.TEXT_PLAIN in content_type or not content_type:
            data = response.text
            if (data.startswith("{") and data.endswith("}")) or reference.endswith(".json"):
                LOGGER.warning("Attempting auto-resolution of invalid Content-Type [%s] to [%s] "
                               "for CWL reference [%s].", content_type, ContentType.APP_JSON, reference)
                content_type = ContentType.APP_JSON
            elif reference.endswith(".yml") or reference.endswith(".yaml"):
                LOGGER.warning("Attempting auto-resolution of invalid Content-Type [%s] to [%s] "
                               "for CWL reference [%s].", content_type, ContentType.APP_YAML, reference)
                content_type = ContentType.APP_YAML
            elif reference.endswith(".cwl"):
                LOGGER.warning("Attempting auto-resolution of invalid Content-Type [%s] to [%s] "
                               "for CWL reference [%s].", content_type, ContentType.APP_CWL, reference)
                content_type = ContentType.APP_CWL
            elif data.startswith("<?xml") or reference.endswith(".xml"):
                LOGGER.warning("Attempting auto-resolution of invalid Content-Type [%s] to [%s] "
                               "for WPS reference [%s].", content_type, ContentType.TEXT_XML, reference)
                content_type = ContentType.TEXT_XML

        payload = None
        if any(ct in content_type for ct in ContentType.ANY_XML):
            # attempt to retrieve a WPS-1 ProcessDescription definition
            cwl_package, process_info = xml_wps2cwl(response, settings)

        elif any(ct in content_type for ct in ogc_api_ctypes):
            # use property with preloaded contents to be faster if reported explicitly of this type
            # YAML load can still parse JSON if not reported explicitly
            payload = response.json() if content_type in ogc_api_json else yaml.safe_load(response.text)
            # attempt to retrieve a WPS-3 Process definition
            # - owsContext possible in older body definitions
            # - OLD schema nests everything under 'process'
            # - OGC schema provides everything at the root, but must distinguish from CWL with 'id'
            if (
                ("process" in payload or "owsContext" in payload or "id" in payload)
                and isinstance(payload, dict) and "cwlVersion" not in payload
                and sd.ProcessDescription(missing=colander.drop).deserialize(payload) is not colander.drop
            ):
                payload.update(process_hint or {})  # apply provided process overrides, such as alternative ID
                cwl_package, process_info = ogcapi2cwl_process(payload, reference)
            # if somehow the CWL was referenced without an extension, handle it here
            elif isinstance(payload, dict) and "cwlVersion" in payload:
                cwl_package = payload
                process_info = {"identifier": reference_name}

        if not process_info or not cwl_package:
            raise PackageNotFound(
                f"Unknown parsing methodology of Content-Type [{content_type}] "
                f"for reference [{reference}] with contents:\n{repr_json(payload)}\n"
            )
    if not cwl_package:
        raise PackageNotFound(
            f"Could not resolve any package from reference [{reference}]."
        )
    return cwl_package, process_info


def get_application_requirement(package,        # type: CWL
                                search=None,    # type: Optional[CWL_RequirementNames]
                                default=null,   # type: Optional[Union[CWL_Requirement, Default]]
                                validate=True,  # type: bool
                                required=True,  # type: bool
                                ):              # type: (...) -> Union[CWL_Requirement, Default]
    """
    Retrieves a requirement or hint from the :term:`CWL` package definition.

    If no :paramref:`search` filter is specified (default), retrieve the *principal* requirement that allows
    mapping to the appropriate :term:`Process` implementation. The *principal* requirement can be extracted
    for an :term:`Application Package` of type :data:`ProcessType.APPLICATION` because only one is permitted
    simultaneously amongst :data:`CWL_REQUIREMENT_APP_TYPES`. If the :term:`CWL` is not of type
    :data:`ProcessType.APPLICATION`, the requirement check is skipped regardless of :paramref:`required`.

    If a :paramref:`search` filter is provided, this specific requirement or hint is looked for instead.
    Regardless of the applied filter, only a unique item can be matched across ``requirements``/``hints`` mapping
    and/or listing representations.

    When :paramref:`validate` is enabled, all ``requirements`` and ``hints`` must also be defined
    within :data:`CWL_REQUIREMENTS_SUPPORTED` for the :term:`CWL` package to be considered valid.

    When :paramref:`convert` is enabled, any backward compatibility definitions will be converted to their
    corresponding definition.

    :param package: CWL definition to parse.
    :param search: Specific requirement/hint name to search and retrieve the definition if available.
    :param default: Default value to return if no match was found. If ``None``, returns an empty ``{"class": ""}``.
    :param validate: Validate supported requirements/hints definition while extracting requested one.
    :param required: Validation will fail if no supported requirements/hints definition could be found.
    :returns: dictionary that minimally has ``class`` field, and optionally other parameters from that requirement.
    """
    # package can define requirements and/or hints,
    # if it's an application, only one CWL_REQUIREMENT_APP_TYPES is allowed,
    # workflow can have multiple, but they are not explicitly handled
    reqs = package.get("requirements", {})
    hints = package.get("hints", {})
    all_hints = _get_package_requirements_normalized(reqs) + _get_package_requirements_normalized(hints)
    if search:
        app_hints = list(filter(lambda h: h["class"] == search, all_hints))
    else:
        app_hints = list(filter(lambda h: any(h["class"].endswith(t) for t in CWL_REQUIREMENT_APP_TYPES), all_hints))
    if len(app_hints) > 1:
        raise PackageTypeError(
            f"Package 'requirements' and/or 'hints' define too many conflicting values: {list(app_hints)}, "
            f"only one requirement is permitted amongst {list(CWL_REQUIREMENT_APP_TYPES)}."
        )
    req_default = default if default is not null else {"class": ""}
    requirement = app_hints[0] if app_hints else req_default

    if validate:
        all_classes = sorted(list(set(resolve_cwl_namespaced_name(item.get("class")) for item in all_hints)))
        app_required = _get_package_type(package) == ProcessType.APPLICATION
        if required and app_required:
            cwl_impl_type_reqs = sorted(list(CWL_REQUIREMENT_APP_TYPES))
            if not all_classes or not any(cls in cwl_impl_type_reqs for cls in all_classes):
                raise PackageTypeError(
                    f"Invalid package requirement. One supported requirement amongst {cwl_impl_type_reqs} is expected. "
                    f"Detected package specification {all_classes} did not provide any of the mandatory requirements. "
                    f"If a script definition is indented for this application, the '{CWL_REQUIREMENT_APP_DOCKER}' "
                    "requirement can be used to provide a suitable execution environment with needed dependencies. "
                    f"Refer to '{sd.DOC_URL}/package.html#script-application' for examples."
                )
        cwl_supported_reqs = sorted(list(CWL_REQUIREMENTS_SUPPORTED))
        cwl_invalid_reqs = sorted(filter(lambda cls: cls not in cwl_supported_reqs, all_classes))
        if cwl_invalid_reqs:
            raise PackageTypeError(
                f"Invalid package requirement. Unknown requirement detected: {cwl_invalid_reqs}. "
                f"Expected requirements and hints must be amongst the following definitions {cwl_supported_reqs}."
            )

    return requirement


def check_package_instance_compatible(package):
    # type: (CWL) -> Optional[str]
    """
    Verifies if an :term:`Application Package` definition is valid for the employed `Weaver` instance configuration.

    Given that the :term:`CWL` is invalid for the active application, explains the reason why that package `always`
    require remote execution.

    When a package can sometimes be executed locally (:term:`ADES`) or remotely (:term:`EMS`) depending on the instance
    configuration, such as in the case of a :data:`CWL_REQUIREMENT_APP_DOCKER`, return ``None``. This function instead
    detects cases where a remote server is mandatory without ambiguity related to the current `Weaver` instance,
    regardless whether remote should be an :term:`ADES` or a remote :term:`Provider` (:term:`WPS` or :term:`ESGF-CWT`).

    :param package: CWL definition for the process.
    :returns: reason message if it must be executed remotely or ``None`` if it *could* be executed locally.
    """
    if _get_package_type(package) == ProcessType.WORKFLOW:
        return f"CWL package defines a [{ProcessType.WORKFLOW}] process that uses remote step-processes."
    requirement = get_application_requirement(package)
    req_class = requirement["class"]
    if req_class in CWL_REQUIREMENT_APP_LOCAL:
        return None
    if req_class in CWL_REQUIREMENT_APP_REMOTE:
        return f"CWL package hint/requirement [{req_class}] requires a remote provider."
    # other undefined hint/requirement for remote execution (aka: ADES dispatched WPS-3/REST/OGC-API)
    remote = all(req in req_class for req in ["provider", "process"])
    if remote:
        return f"CWL package hint/requirement [{req_class}] defines a remote provider entry."
    return None


def get_auth_requirements(requirement, headers):
    # type: (JSON, Optional[AnyHeadersContainer]) -> Optional[Authentication]
    """
    Extract any authentication related definitions provided in request headers corresponding to the application type.

    :param requirement: :term:`Application Package` requirement as defined by :term:`CWL` requirements.
    :param headers: Requests headers received during deployment.
    :return: Matched authentication details when applicable, otherwise None.
    :raises TypeError: When the authentication object cannot be created due to invalid or missing inputs.
    :raises ValueError: When the authentication object cannot be created due to incorrectly formed inputs.
    """
    if not headers:
        LOGGER.debug("No headers provided, cannot extract any authentication requirements.")
        return None
    if requirement["class"] == CWL_REQUIREMENT_APP_DOCKER:
        x_auth_docker = get_header(sd.XAuthDockerHeader.name, headers)
        link_ref_docker = requirement.get("dockerPull", None)
        if x_auth_docker and link_ref_docker:
            LOGGER.info("Detected authentication details for Docker image reference in Application Package.")
            auth_details = x_auth_docker.split(" ")
            # note: never provide any parts in errors in case of incorrect parsing, first could be token by mistake
            if not len(auth_details) == 2:
                raise ValueError(
                    "Invalid authentication header provided without an authentication scheme or content "
                    "(see also: https://www.iana.org/assignments/http-authschemes/http-authschemes.xhtml)."
                )
            auth_scheme, auth_token = auth_details[0].strip(), auth_details[1].strip()
            auth_supported = {
                "Basic": "https://datatracker.ietf.org/doc/html/rfc7617",
                # "Bearer": "https://datatracker.ietf.org/doc/html/rfc6750"  # FIXME: Docker client not supporting it
            }
            if auth_scheme not in auth_supported:
                if auth_scheme.capitalize() not in auth_supported:
                    supported_schemes = ", ".join([
                        f"{scheme} ({rfc_spec})" for scheme, rfc_spec in auth_supported.items()
                    ])
                    raise ValueError(
                        "Invalid authentication header scheme is not supported. "
                        f"Supported schemes are: {supported_schemes}."
                    )
                auth_scheme = auth_scheme.capitalize()
            auth = DockerAuthentication(link_ref_docker, auth_scheme, auth_token)
            LOGGER.debug("Authentication details for Docker image reference in Application Package correctly parsed.")
            return auth

    LOGGER.debug("No associated authentication details for application requirement: %s", requirement["class"])
    return None


def mask_process_inputs(package, inputs, secret_store=None):
    # type: (CWL, ExecutionInputs, Optional[SecretStore]) -> ExecutionInputs
    """
    Obtains a masked representation of the input values as applicable.

    .. seealso::
        :data:`CWL_REQUIREMENT_SECRETS`
    """
    if not package:
        return inputs
    req_secrets = get_application_requirement(package, search=CWL_REQUIREMENT_SECRETS, required=False, default={})
    if not req_secrets or "secrets" not in req_secrets:
        return inputs
    masked_inputs = copy.deepcopy(inputs)
    secret_store = secret_store or SecretStore()
    is_input_map = isinstance(inputs, dict)
    for idx_or_key, input_def in (
        masked_inputs.items() if is_input_map else enumerate(masked_inputs)
    ):  # type: Union[str, int], JobValueItem
        input_id = idx_or_key if is_input_map else get_any_id(input_def)
        if input_id in req_secrets["secrets"]:
            if isinstance(input_def, dict):
                val_key = get_any_value(input_def, key=True, data=True)
                value = input_def.get(val_key)
                if val_key and isinstance(value, str):
                    input_def[val_key] = secret_store.add(value)
                    masked_inputs[idx_or_key] = input_def
            elif isinstance(input_def, str):
                masked_inputs[idx_or_key] = secret_store.add(input_def)
    return masked_inputs


def get_process_identifier(process_info, package):
    # type: (JSON, CWL) -> str
    """
    Obtain a sane name identifier reference from the :term:`Process` or the :term:`Application Package`.
    """
    process_id = get_any_id(process_info)
    if not process_id:
        process_id = package.get("id")
    process_id = get_sane_name(process_id, assert_invalid=True, min_len=1)
    return process_id


def get_process_definition(
    process_offering,   # type: JSON
    reference=None,     # type: Optional[str]
    package=None,       # type: Optional[CWL]
    data_source=None,   # type: Optional[str]
    headers=None,       # type: Optional[AnyHeadersContainer]
    builtin=False,      # type: bool
    container=None,     # type: Optional[AnySettingsContainer]
):                      # type: (...) -> JSON
    """
    Resolve the process definition considering corresponding metadata from the offering, package and references.

    Returns an updated process definition dictionary ready for storage using provided `WPS` ``process_offering``
    and a package definition passed by ``reference`` or ``package`` `CWL` content.
    The returned process information can be used later on to load an instance of :class:`weaver.wps_package.WpsPackage`.

    :param process_offering: `WPS REST-API` (`WPS-3`) process offering as :term:`JSON`.
    :param reference: URL to :term:`CWL` package, `WPS-1 DescribeProcess` endpoint or `WPS-3 Process` endpoint.
    :param package: Literal :term:`CWL` package definition (`YAML` or `JSON` format).
    :param data_source: Where to resolve process IDs (default: localhost if ``None``).
    :param headers: Request headers provided during deployment to retrieve details such as authentication tokens.
    :param builtin: Indicate if the package is expected to be a :data:`CWL_REQUIREMENT_APP_BUILTIN` definition.
    :param container: Container that provides access to application settings.
    :return: Updated process definition with resolved/merged information from ``package``/``reference``.
    """

    def try_or_raise_package_error(call, reason):
        # type: (Callable[[], Any], str) -> Any
        try:
            LOGGER.debug("Attempting: [%s].", reason)
            return call()
        except Exception as exc:
            # re-raise any exception already handled by a "package" error as is, but with a more detailed message
            # handle any other sub-exception that wasn't processed by a "package" error as a registration error
            exc_type = type(exc) if isinstance(exc, PackageException) else PackageRegistrationError
            exc_msg = str(exc)
            LOGGER.exception(exc_msg)
            raise exc_type(f"Invalid package/reference definition. {reason} generated error: [{exc!s}].")

    if not (isinstance(package, dict) or isinstance(reference, str)):
        raise PackageRegistrationError("Invalid parameters, one of [package, reference] is required.")
    if package and reference:
        raise PackageRegistrationError("Simultaneous parameters [package, reference] not allowed.")

    process_info = process_offering
    if reference:
        package, process_info = try_or_raise_package_error(
            lambda: _generate_process_with_cwl_from_reference(reference, process_info),
            reason="Loading package from reference",
        )
        process_info.update(process_offering)   # override upstream details
    if not isinstance(package, dict):
        raise PackageRegistrationError("Cannot decode process package contents.")
    if "class" not in package:
        raise PackageRegistrationError("Cannot obtain process type from package class.")

    LOGGER.debug("Using data source: '%s'", data_source)
    package_factory, process_type, _ = try_or_raise_package_error(
        lambda: _load_package_content(
            package,
            data_source=data_source,
            process_offering=process_info,
            container=container,
        ),
        reason="Loading package content",
    )

    package_inputs, package_outputs = try_or_raise_package_error(
        lambda: _get_package_inputs_outputs(package_factory),
        reason="Definition of package/process inputs/outputs",
    )
    process_inputs = process_info.get("inputs", [])
    process_outputs = process_info.get("outputs", [])

    try_or_raise_package_error(
        lambda: _update_package_metadata(process_info, package),
        reason="Metadata update",
    )

    process_inputs, process_outputs = try_or_raise_package_error(
        lambda: _merge_package_inputs_outputs(process_inputs, package_inputs, process_outputs, package_outputs),
        reason="Merging of inputs/outputs",
    )

    app_requirement = try_or_raise_package_error(
        lambda: get_application_requirement(package, validate=True, required=not builtin),
        reason="Validate requirements and hints",
    )

    auth_requirements = try_or_raise_package_error(
        lambda: get_auth_requirements(app_requirement, headers),
        reason="Obtaining authentication requirements",
    )

    # obtain any retrieved process id if not already provided from upstream process offering, and clean it
    process_id = try_or_raise_package_error(
        lambda: get_process_identifier(process_info, package),
        reason="Obtaining process identifier"
    )
    if not process_id:
        raise PackageRegistrationError("Could not retrieve any process identifier.")

    process_offering.update({
        "identifier": process_id,
        "package": package,
        "type": process_type,
        "inputs": process_inputs,
        "outputs": process_outputs,
        "auth": auth_requirements,
    })
    return process_offering


def format_extension_validator(data_input, mode):
    # type: (Union[ComplexInput, ComplexOutput], int) -> bool
    """
    Validator that will only check that the extension matches the selected data format.
    """
    if not isinstance(data_input, (ComplexInput, ComplexOutput)):
        return False  # validator applied on wrong type
    if mode == MODE.NONE or data_input.data_format is None:
        return True
    ext = get_extension(data_input.data_format.mime_type, dot=True)
    return os.path.splitext(data_input._iohandler._file)[-1] == ext


class DirectoryNestedStorage(CachedStorage):
    """
    Generates a nested storage for a directory where each contained file will be managed by the storage.
    """

    def __init__(self, storage):
        # type: (Union[FileStorage, S3Storage]) -> None
        """
        Initializes the storage.

        :param storage: Storage implementation that is employed for storing files in a directory-like structure.
        """
        self.__dict__["_cache"] = {}
        self.__dict__["storage"] = storage
        super(DirectoryNestedStorage, self).__init__()

    def __getattr__(self, item):
        # type: (str) -> Any
        return getattr(self.storage, item)

    def __setattr__(self, key, value):
        # type: (str, Any) -> None
        """
        Setting a property on this storage applies it on the nested file storage.
        """
        if key in self.__dict__:
            object.__setattr__(self, key, value)
        else:
            setattr(self.storage, key, value)

    @property
    def type(self):
        # type: () -> STORE_TYPE
        return STORE_TYPE.PATH if isinstance(self.storage, FileStorage) else STORE_TYPE.S3

    def _patch_destination(self, destination):
        # type: (str) -> str
        destination = destination.lstrip("/")  # avoid issues with prefix path join
        # file storage already does the target-dir/output-dir join
        # however, s3 storage does not...
        if isinstance(self.storage, S3Storage):
            return os.path.join(self.prefix, destination)
        return destination

    def _do_store(self, output):
        # type: (ComplexOutput) -> Tuple[STORE_TYPE, Path, str]
        """
        Store all files contained in a directory recursively.

        .. note::
            This is called from :meth:`CachedStorage.store` only if not already in storage using cached output ID.
        """
        root = output.file
        if not os.path.isdir(root):
            raise ValueError(f"Location is not a directory: [{root}]")
        files = list_directory_recursive(root)
        root = f"{root.rstrip('/')}/"
        loc_path = f"{self.location(output.identifier)}/"  # local directory or S3 location
        url_path = f"{self.url(output.identifier)}/"       # HTTP output or same S3 location
        default_support = [DEFAULT_FORMAT] + [get_format(ctype) for ctype in [ContentType.ANY, ContentType.TEXT_PLAIN]]
        for file in files:
            out_file_path_rel = file.split(root, 1)[-1]
            out_cache_key = self._patch_destination(os.path.join(str(output.uuid), out_file_path_rel))
            out_ext = os.path.splitext(out_file_path_rel)[-1]
            out_ctype = get_content_type(out_ext)  # attempt guessing more specific format
            out_fmt = get_format(out_ctype)
            out_fmts = default_support + ([out_fmt] if out_fmt else [])
            out_file = ComplexOutput(out_cache_key, title=output.title, data_format=out_fmt, supported_formats=out_fmts)
            out_file.file = file
            out_file.uuid = output.uuid  # forward base directory auto-generated when storing file
            # create a copy in case the storage is used by many dirs, avoid concurrent read/write of distinct prefixes
            dir_storage = copy.copy(self.storage)
            if isinstance(dir_storage, S3Storage):
                # patch S3 nested prefix under current directory
                # S3 storage methods use only the file name to generate the bucket object key
                # to preserve the nested output dir definition, it must be pushed as prefix
                dir_storage.prefix = os.path.dirname(out_cache_key)
            out_file.storage = dir_storage
            out_type, out_path, out_url = dir_storage.store(out_file)
            self._cache[out_cache_key] = (out_type, out_path, out_url)  # propagate up for direct reference as needed
            LOGGER.debug("Stored file [%s] for reference [%s] under [%s] directory located in [%s] for reference [%s].",
                         out_path, out_url, output.uuid, loc_path, url_path)
        return self.type, loc_path, url_path

    def write(self, data, destination, data_format=None):
        # type: (AnyStr, str, Optional[Format]) -> str
        """
        Write data representing the directory itself or dispatch call to base storage for any other file contents.

        When the directory itself is targeted, upload an empty bucket object for S3 base storage, or makes the
        directory structure for base file storage.
        """
        dest_patched = self._patch_destination(destination)
        if destination != "" and not destination.endswith("/"):
            return self.storage.write(data, dest_patched, data_format=data_format)
        if isinstance(self.storage, FileStorage):
            os.makedirs(self.storage.target, exist_ok=True)
            return self.url(dest_patched)
        if isinstance(self.storage, S3Storage):
            path = f"{dest_patched.rstrip('/')}/"
            args = {
                "ContentLength": 0,
                "ContentType": ContentType.APP_DIR,
            }
            # create a bucket object that represents the dir
            return self.storage.uploadData("", path, args)
        raise NotImplementedError

    def url(self, destination):
        # type: (str) -> str
        destination = self._patch_destination(destination)
        if destination in ["/", ""]:
            return self.storage.url("")
        return self.storage.url(destination)

    def location(self, destination):
        # type: (str) -> Path
        destination = self._patch_destination(destination)
        if destination in ["/", ""]:
            return self.storage.location("")
        return self.storage.location(destination)


class WpsPackage(Process):
    def __init__(
        self,
        *,
        identifier,     # type: str
        title=None,     # type: Optional[str]
        package=None,   # type: CWL
        payload=None,   # type; Optional[JSON]
        settings=None,  # type: Optional[AnySettingsContainer]
        **kw,           # type: Any
    ):                  # type: (...) -> None
        """
        Creates a `WPS-3 Process` instance to execute a `CWL` application package definition.

        Process parameters should be loaded from an existing :class:`weaver.datatype.Process`
        instance generated using :func:`weaver.wps_package.get_process_definition`.

        Provided ``kw`` should correspond to :meth:`weaver.datatype.Process.params_wps`
        """
        # defined only after/while _handler is called (or sub-methods)
        self.package_id = identifier            # type: str
        self.package_type = None                # type: Optional[str]
        self.package_requirement = None         # type: Optional[CWL_RequirementsDict]
        self.package_log_hook_stderr = None     # type: Optional[str]
        self.package_log_hook_stdout = None     # type: Optional[str]
        self.percent = None                     # type: Optional[Number]
        self.status = None                      # type: Optional[AnyStatusType]
        self.remote_execution = None            # type: Optional[bool]
        self._log_file = None                   # type: Optional[str]
        self._log_level = None                  # type: Optional[int]
        self._logger = None                     # type: Optional[logging.Logger]
        self.step_packages = {}                 # type: CWL_WorkflowStepPackageMap
        self.step_launched = []                 # type: List[str]
        self.request = None                     # type: Optional[WorkerRequest]
        self.response = None                    # type: Optional[ExecuteResponse]
        self.uuid = None                        # type: Optional[uuid.UUID]
        self._job = None                        # type: Optional[Job]
        self._job_status_file = None            # type: Optional[str]

        self.payload = payload
        self.package = package
        self.settings = get_settings(settings)
        if not self.package:
            raise PackageRegistrationError("Missing required package definition for package process.")
        if not isinstance(self.package, dict):
            raise PackageRegistrationError("Unknown parsing of package definition for package process.")

        # prepare some metadata about the package that are often reused
        self.package_type = _get_package_type(self.package)
        self.package_requirement = get_application_requirement(self.package)
        self.step_packages = self.package.get("steps") or {}

        inputs = kw.pop("inputs", [])
        # handle EOImage inputs
        inputs = opensearch.replace_inputs_describe_process(inputs=inputs, payload=self.payload)

        inputs = [json2wps_io(i, IO_INPUT) for i in inputs]
        outputs = [json2wps_io(o, IO_OUTPUT) for o in kw.pop("outputs", [])]
        metadata = [json2wps_field(meta_kw, "metadata") for meta_kw in kw.pop("metadata", [])]

        super(WpsPackage, self).__init__(
            self._handler,
            identifier,
            title=title or identifier,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            store_supported=True,
            status_supported=True,
            **kw
        )

    @property
    def status_filename(self):
        # type: () -> str
        """
        Obtain the XML status location of this process when executed.

        The status location applies the ``WPS-Output-Context`` if defined such that any following output
        or log file references that derive from it will be automatically stored in the same nested context.
        """
        if self._job_status_file:
            return self._job_status_file
        # avoid error in case process execution is a remote provider (eg: during workflow step)
        # file is already defined in a specific location and cannot be moved
        if isinstance(self.status_store, ReferenceStatusLocationStorage):
            self._job_status_file = self.status_store.location()
            return self._job_status_file
        status_file = super(WpsPackage, self).status_filename
        if self.job.context:
            status_store_ctx_dir = os.path.join(self.status_store.target, self.job.context)
            os.makedirs(status_store_ctx_dir, exist_ok=True)
            status_file = os.path.join(self.job.context, status_file)
        self._job_status_file = status_file
        return status_file

    def setup_loggers(self, log_stdout_stderr=True):
        # type: (bool) -> None
        """
        Configures useful loggers to catch most of the common output and/or error messages during package execution.

        .. seealso::
            :meth:`insert_package_log`
            :func:`retrieve_package_job_log`
        """
        setup_loggers(self.settings)
        self._log_level = self._log_level or logging.getLogger("weaver").getEffectiveLevel()

        # file logger for output
        self._log_file = get_status_location_log_path(self.status_location)
        log_file_handler = logging.FileHandler(self._log_file)
        log_file_formatter = logging.Formatter(fmt=get_log_fmt(), datefmt=get_log_date_fmt())
        log_file_formatter.converter = time.gmtime
        log_file_handler.setFormatter(log_file_formatter)

        # prepare package logger
        self._logger = logging.getLogger(f"{LOGGER.name}|{self.package_id}")
        if not any(isinstance(handler, logging.FileHandler) for handler in self._logger.handlers):
            self._logger.addHandler(log_file_handler)
        self._logger.setLevel(self._log_level)

        # add CWL job and CWL runner logging to current package logger
        job_logger = logging.getLogger(f"job {PACKAGE_DEFAULT_FILE_NAME}")
        if not any(isinstance(handler, logging.FileHandler) for handler in job_logger.handlers):
            job_logger.addHandler(log_file_handler)
        job_logger.setLevel(self._log_level)
        cwl_logger = logging.getLogger("cwltool")
        if not any(isinstance(handler, logging.FileHandler) for handler in cwl_logger.handlers):
            cwl_logger.addHandler(log_file_handler)
        cwl_logger.setLevel(self._log_level)

        # add stderr/stdout CWL hook to capture logs/prints/echos from subprocess execution
        # using same file so all kind of message are kept in chronological order of generation
        # NOTE:
        #   If the package itself defined stdout/stderr at the root of the CWL document,
        #   it is possibly employed by one of its outputs as output binding glob.
        #   The value in this case must not be overridden or it could break the defined package.
        if log_stdout_stderr:
            self.package_log_hook_stderr = self.package.get(
                "stderr",
                PACKAGE_OUTPUT_HOOK_LOG_UUID.format(str(uuid.uuid4())),
            )
            self.package_log_hook_stdout = self.package.get(
                "stdout",
                PACKAGE_OUTPUT_HOOK_LOG_UUID.format(str(uuid.uuid4())),
            )
            package_outputs = self.package.get("outputs")
            if isinstance(package_outputs, list):
                package_outputs.extend([{"id": self.package_log_hook_stderr, "type": "stderr"},
                                        {"id": self.package_log_hook_stdout, "type": "stdout"}])
            else:
                package_outputs.update({self.package_log_hook_stderr: {"type": "stderr"},
                                        self.package_log_hook_stdout: {"type": "stdout"}})
            self.package.setdefault("stderr", "stderr.log")
            self.package.setdefault("stdout", "stdout.log")

        # add weaver Tweens logger to current package logger
        weaver_tweens_logger = logging.getLogger("weaver.tweens")
        if not any(isinstance(handler, logging.FileHandler) for handler in weaver_tweens_logger.handlers):
            weaver_tweens_logger.addHandler(log_file_handler)
        weaver_tweens_logger.setLevel(self._log_level)

    def insert_package_log(self, result):
        # type: (Union[CWL_Results, CWLException]) -> List[str]
        """
        Retrieves additional `CWL` sub-process logs captures to retrieve internal application output and/or errors.

        After execution of this method, the `WPS` output log (which can be obtained by :func:`retrieve_package_job_log`)
        will have additional ``stderr/stdout`` entries extracted from the underlying application package tool execution.

        The outputs and errors are inserted *as best as possible* in the logical order to make reading of the merged
        logs appear as a natural and chronological order. In the event that both output and errors are available, they
        are appended one after another as merging in an orderly fashion cannot be guaranteed by outside `CWL` runner.

        .. note::
            In case of any exception, log reporting is aborted and ignored.

        .. todo::
            Improve for realtime updates when using async routine (https://github.com/crim-ca/weaver/issues/131)

        .. seealso::
            :meth:`setup_loggers`
            :func:`retrieve_package_job_log`

        :param result: output results returned by successful `CWL` package instance execution or raised CWL exception.
        :returns: captured execution log lines retrieved from files
        """
        captured_log = []
        status = Status.RUNNING
        try:
            if isinstance(result, CWLException):
                result = getattr(result, "out")
                status = Status.FAILED
            stderr_file = result.get(self.package_log_hook_stderr, {}).get("location", "").replace("file://", "")
            stdout_file = result.get(self.package_log_hook_stdout, {}).get("location", "").replace("file://", "")
            with_stderr_file = os.path.isfile(stderr_file)
            with_stdout_file = os.path.isfile(stdout_file)
            if not with_stdout_file and not with_stderr_file:
                self.log_message(
                    "Could not retrieve any internal application log.",
                    status=status,
                    level=logging.WARNING,
                )
                return captured_log
            out_log = []
            if with_stdout_file:
                with open(stdout_file, mode="r", encoding="utf-8") as app_log_fd:
                    out_log = app_log_fd.readlines()
                    if out_log:
                        out_log = ["----- Captured Log (stdout) -----\n"] + out_log
            err_log = []
            if with_stderr_file:
                with open(stderr_file, mode="r", encoding="utf-8") as app_log_fd:
                    err_log = app_log_fd.readlines()
                    if err_log:
                        err_log = ["----- Captured Log (stderr) -----\n"] + err_log
            if not out_log and not err_log:
                self.log_message(
                    "Nothing captured from internal application logs.",
                    status=status,
                    level=logging.INFO,
                )
                return captured_log
            with open(self._log_file, mode="r", encoding="utf-8") as pkg_log_fd:
                pkg_log = pkg_log_fd.readlines()
            cwl_end_index = -1
            cwl_end_search = f"[cwltool] [job {self.package_id}] completed"  # success/permanentFail
            for i in reversed(range(len(pkg_log))):
                if cwl_end_search in pkg_log[i]:
                    cwl_end_index = i
                    break
            captured_log = out_log + err_log + ["----- End of Logs -----\n"]
            merged_log = pkg_log[:cwl_end_index] + captured_log + pkg_log[cwl_end_index:]
            with open(self._log_file, mode="w", encoding="utf-8") as pkg_log_fd:
                pkg_log_fd.writelines(merged_log)
        except Exception as exc:  # pragma: no cover  # log exception, but non-failing
            self.exception_message(PackageExecutionError, exception=exc, level=logging.WARNING, status=status,
                                   message="Error occurred when retrieving internal application log.")
        return captured_log

    def setup_docker_image(self):
        # type: () -> Optional[bool]
        """
        Pre-pull the :term:`Docker` image locally for running the process if authentication is required to get it.

        :returns: success status if operation was successful, or ``None`` when it does not apply.
        """
        # check multiple conditions where Docker authentication never applies
        if self.remote_execution:
            self.log_message("Skipping Docker setup not needed for remote execution.", level=logging.DEBUG)
            return None
        if self.package_type != ProcessType.APPLICATION:
            self.log_message(
                "Skipping Docker setup not needed for CWL Workflow. Sub-step must take care of it if needed.",
                level=logging.DEBUG,
            )
            return None
        if self.package_requirement["class"] != CWL_REQUIREMENT_APP_DOCKER:
            self.log_message(
                "Skipping Docker setup not needed for CWL application without Docker requirement.",
                level=logging.DEBUG,
            )
            return None
        if self.job.service:
            self.log_message(
                "Skipping Docker setup not needed for remote WPS provider process.",
                level=logging.DEBUG,
            )
            return None

        store = get_db(self.settings).get_store(StoreProcesses)
        process = store.fetch_by_id(self.job.process)
        if not isinstance(process.auth, DockerAuthentication):
            self.log_message("Skipping Docker setup not needed for public repository access.", level=logging.DEBUG)
            return None
        if self.package_requirement["dockerPull"] != process.auth.link:
            # this is mostly to make sure references are still valid (process/package modified after deployment?)
            # since they should originate from the same CWL 'dockerPull', something went wrong if they don't match
            self.log_message(
                "Skipping Docker setup not applicable for Application Package's Docker reference "
                "mismatching registered Process Authentication Docker reference.",
                level=logging.DEBUG,
            )
            return None

        client = pull_docker(process.auth, logger=self)
        return client is not None

    def setup_runtime(self):
        # type: () -> Dict[str, AnyValueType]
        """
        Prepares the runtime parameters for the :term:`CWL` package execution.

        Parameter ``weaver.wps_workdir`` is the base-dir where sub-dir per application packages will be generated.
        Parameter :attr:`workdir` is the actual location PyWPS reserved for this process (already with sub-dir).
        If no ``weaver.wps_workdir`` was provided, reuse PyWps parent workdir since we got access to it.
        Other steps handling outputs need to consider that ``CWL<->WPS`` out dirs could match because of this.

        :return: resolved runtime parameters
        """
        wps_workdir = self.settings.get("weaver.wps_workdir", os.path.dirname(self.workdir))
        # cwltool will add additional unique characters after prefix paths
        cwl_workdir = os.path.join(wps_workdir, "cwltool_tmp_")
        cwl_outdir = os.path.join(wps_workdir, "cwltool_out_")
        res_req = get_application_requirement(self.package, CWL_REQUIREMENT_RESOURCE, default={}, validate=False)
        runtime_params = {
            # provide name reference to inject the value in log entries by cwltool
            "name": self.identifier,
            # force explicit staging if write needed (InitialWorkDirRequirement in CWL package)
            # protect input paths that can be re-used to avoid potential in-place modifications
            "no_read_only": False,
            # employ enforced user/group from provided config or auto-resolved ones from running user
            "no_match_user": False,
            # directories for CWL to move files around, auto cleaned up by cwltool when finished processing
            # (paths used are according to DockerRequirement and InitialWorkDirRequirement)
            "tmpdir_prefix": cwl_workdir,
            "tmp_outdir_prefix": cwl_outdir,
            # ask CWL to move tmp outdir results to the WPS process workdir (otherwise we loose them on cleanup)
            "outdir": self.workdir,
            "debug": self._logger.isEnabledFor(logging.DEBUG),
            # when process is a docker image, memory monitoring information is obtained with CID file
            # this file is only generated when the below command is explicitly None (not even when '')
            "user_space_docker_cmd": None,
            # if 'ResourceRequirement' is specified to limit RAM/CPU usage, below must be added to ensure it is applied
            # but don't enable it otherwise, since some defaults are applied which could break existing processes
            "strict_memory_limit": bool(res_req),
            "strict_cpu_limit": bool(res_req),
        }
        return runtime_params

    def setup_provenance(self, loading_context, runtime_context):
        # type: (LoadingContext, RuntimeContext) -> None
        """
        Configure ``PROV`` runtime options.

        .. seealso::
            - https://www.w3.org/TR/prov-overview/
            - https://cwltool.readthedocs.io/en/latest/CWLProv.html
            - https://docs.ogc.org/DRAFTS/24-051.html#_requirements_class_provenance
        """
        weaver_cwl_prov = asbool(self.settings.get("weaver.cwl_prov", True))
        if not weaver_cwl_prov:
            loading_context.research_obj = None
            runtime_context.research_obj = None
            runtime_context.prov_obj = None
            return

        runtime_context.prov_user = loading_context.user_provenance = True
        runtime_context.prov_host = loading_context.host_provenance = True

        if not runtime_context.research_obj:
            ro = WeaverResearchObject(
                self.job,  # align the RO definition with the job (make the UUIDs equal)
                self.settings,
                runtime_context.make_fs_access(""),
                temp_prefix_ro=runtime_context.tmpdir_prefix,
                orcid=runtime_context.orcid,
                full_name=runtime_context.cwl_full_name,
            )

            loading_context.research_obj = ro
            runtime_context.research_obj = ro

    def finalize_provenance(self, runtime_context):
        # type: (RuntimeContext) -> None
        if runtime_context.research_obj:
            # perform packaging of the workflow
            packed_wf_str = repr_json(self.package, force_string=True, indent=2)
            packed_workflow(runtime_context.research_obj, packed_wf_str)

            # sign-off and persist completed PROV
            prov_dir = self.job.prov_path(self.settings)
            close_ro(runtime_context.research_obj, prov_dir)

    def update_requirements(self):
        # type: () -> None
        """
        Inplace modification of :attr:`package` to adjust invalid items that would break behaviour we must enforce.
        """
        is_builtin = False
        for req_type in ["hints", "requirements"]:
            req_items = self.package.get(req_type, {})
            for req_cls in req_items:
                if not isinstance(req_cls, dict):
                    req_def = req_items[req_cls]
                else:
                    req_def = req_cls
                    req_cls = req_cls["class"]
                if req_cls == CWL_REQUIREMENT_APP_BUILTIN:
                    is_builtin = True
                if req_cls != CWL_REQUIREMENT_APP_DOCKER:
                    continue
                # remove build-related parameters because we forbid this in our case
                # remove output directory since we must explicitly define it to match with WPS
                for req_rm in ["dockerFile", "dockerOutputDirectory"]:
                    is_rm = req_def.pop(req_rm, None)
                    if is_rm:
                        self.log_message(
                            f"Removed CWL [{req_cls}.{req_rm}] {req_type[:-1]} "
                            f"parameter from [{self.package_id}] package definition (forced).",
                            level=logging.WARNING,
                        )

        # update python reference if builtin script
        #   since subprocess is created by CWL, the default python detected is from the OS
        #   when running from within Weaver Docker, this doesn't matter much as OS Python == Weaver Env Python
        #   but running in any other situation (e.g.: local, tests) will not necessarily point to same instance
        if is_builtin:
            python_path = os.getenv("PYTHONPATH")
            if not python_path:
                return
            req_items = self.package.get("requirements", {})
            if not isinstance(req_items, dict):
                # definition as list
                req_env = {"class": CWL_REQUIREMENT_ENV_VAR, "envDef": {}}
                for req in req_items:
                    if req["class"] == CWL_REQUIREMENT_ENV_VAR:
                        req_env = req
                        break
                req_items.append(req_env)
            else:
                # definition as mapping
                req_items.setdefault(CWL_REQUIREMENT_ENV_VAR, {"envDef": {}})
                req_env = req_items.get(CWL_REQUIREMENT_ENV_VAR)
            active_python_path = os.path.join(sys.exec_prefix, "bin")
            env_path = os.getenv("PATH") or ""
            env_path = f":{env_path}" if env_path else ""
            env_path = f"{active_python_path}{env_path}"
            req_env["envDef"].update({"PATH": env_path})
            if self.package.get("baseCommand") == "python":
                self.package["baseCommand"] = os.path.join(active_python_path, "python")

    def update_cwl_schema_names(self):
        # type: () -> None
        """
        Detect duplicate :term:`CWL` schema types not referred by name to provide one and avoid resolution failure.

        Doing this resolution avoids reused definitions being considered as "conflicts" because of missing ``name``.
        To avoid introducing a real conflict, names are injected only under corresponding :term:`CWL` I/O by ID.
        The most common type of definition resolved this way is when :term:`CWL` ``Enum`` is reused for single and
        array-based definitions simultaneously without using an explicit ``SchemaDefRequirement`` for them.

        .. seealso::
            - :func:`weaver.processes.convert.resolve_cwl_io_type_schema`
            - :meth:`weaver.processes.wps_package.WpsPackage.make_inputs`

        .. fixme:
        .. todo::
            Workaround for https://github.com/common-workflow-language/cwltool/issues/1908.
        """
        for io_select in ["inputs", "outputs"]:
            if isinstance(self.package[io_select], dict):
                io_items = self.package[io_select]  # type: Dict[str, CWL_IO_Type]
            else:
                io_items = {item["id"]: item for item in self.package[io_select]}  # type: Dict[str, CWL_IO_Type]
            for io_name, io_def in io_items.items():
                if isinstance(io_def["type"], list):
                    item_enum = None
                    array_enum = None
                    for io_item in io_def["type"]:
                        if not isinstance(io_item, dict):
                            continue
                        if io_item.get("type") == "enum":
                            item_enum = io_item
                            continue
                        if io_item.get("type") != "array":
                            continue
                        if not isinstance(io_item.get("items", {}), dict):
                            continue
                        if io_item["items"].get("type") == "enum":
                            array_enum = io_item["items"]
                    # only apply the name reference if not already provided (eg: explicit name defined in original CWL)
                    if item_enum and array_enum and item_enum == array_enum and "name" not in item_enum:
                        item_enum["name"] = array_enum["name"] = f"{io_name}{uuid.uuid4()}"

    def update_effective_user(self):
        # type: () -> None
        """
        Update effective user/group for the `Application Package` to be executed.

        FIXME: (experimental) update user/group permissions

        Reducing permissions is safer inside docker application since weaver/cwltool could be running as root
        but this requires that mounted volumes have the required permissions so euid:egid can use them.

        Overrides :mod:`cwltool`'s function to retrieve user/group id for ones we enforce.
        """
        if sys.platform == "win32":
            return

        cfg_euid = str(self.settings.get("weaver.cwl_euid", ""))
        cfg_egid = str(self.settings.get("weaver.cwl_egid", ""))
        app_euid, app_egid = str(os.geteuid()), str(os.getgid())  # pylint: disable=E1101
        if cfg_euid not in ["", "0", app_euid] and cfg_egid not in ["", "0", app_egid]:
            self.log_message("Enforcing CWL euid:egid [%s,%s]", cfg_euid, cfg_egid)
            cwltool.docker.docker_vm_id = lambda *_, **__: (int(cfg_euid), int(cfg_egid))
        else:
            self.log_message(
                "Visible application CWL euid:egid [%s:%s]", app_euid, app_egid,
                level=logging.WARNING if (app_euid == "0" or app_egid == "0") else logging.INFO,
            )

    def update_status(self, message, progress, status, error=None, step=False):
        # type: (str, Number, AnyStatusType, Optional[Exception], bool) -> None
        """
        Updates the :mod:`pywps` real job status from a specified parameters.
        """
        self.percent = progress or self.percent or 0
        self.status = status

        # ignore pywps hook when not yet in runtime context
        if self.response:
            # find the enum PyWPS status matching the given one as string
            pywps_status = map_status(status, StatusCompliant.PYWPS)
            pywps_status_id = STATUS_PYWPS_IDS[pywps_status]
            # NOTE:
            #   When running process in sync (because executed within celery worker already async),
            #   pywps reverts status file output flag. Re-enforce it for our needs.
            #   (see: 'weaver.wps.WorkerService.execute_job')
            self.response.store_status_file = True
            # pywps overrides 'status' by 'accepted' in 'update_status'
            # therefore, use the '_update_status' to enforce the status
            # using protected method also avoids weird overrides of progress
            # percent on failure and final 'success' status
            self.response._update_status(pywps_status_id, message, self.percent, clean=not step)  # noqa: W0212

        if isinstance(error, Exception):
            self.exception_message(exception_type=type(error), exception=error,
                                   status=status, message=message, progress=progress)
        else:
            self.log_message(status=status, message=message, progress=progress)

    def step_update_status(self,
                           message,                 # type: str
                           progress,                # type: Number
                           start_step_progress,     # type: Number
                           end_step_progress,       # type: Number
                           step_name,               # type: str
                           target_host,             # type: str
                           status,                  # type: AnyStatusType
                           error=None,              # type: Optional[Exception]
                           ):                       # type: (...) -> None
        # ensure the status of the current workflow is not changed to 'success' if up a step-update
        # setting to 'success' will report the wrong value in the status XML document
        # this would also trigger cleanup, which would remove an staged file needed by a future step
        if status == Status.SUCCEEDED:
            status = Status.RUNNING
        self.update_status(
            message=f"[provider: {target_host}, step: {step_name}] - {str(message).strip()}",
            progress=map_progress(progress, start_step_progress, end_step_progress),
            status=status,
            error=error,
            step=True,
        )

    def log(self, level, message, *args, **kwargs):
        # type: (int, str, *str, **Any) -> None
        """
        Logging interface matching :class:`logging.Logger` for use by other utilities.
        """
        self.log_message(message, *args, level=level, **kwargs)

    def log_message(self, message, *args, status=None, progress=None, level=logging.INFO, **kwargs):
        # type: (str, *str, Optional[AnyStatusType], Optional[Number], int, **Any) -> None
        if not self._logger.isEnabledFor(level):
            return
        status = map_status(status or self.status)
        progress = progress if progress is not None else self.percent
        message = get_job_log_msg(status=status, message=message, progress=progress)
        if args:
            message = message.replace("% ", "%% ")  # escape to avoid string formatting error when passed to logger
        # Avoid logging plain 'NoneType: None' if exception was handled (therefore nothing raised) but should still
        # be reported as error. Otherwise, include it manually the same way it would be added automatically.
        exc_info = kwargs.pop("exc_info", None)
        if exc_info is None and level > logging.INFO:
            exc_info = sys.exc_info()
            if exc_info == (None, None, None):
                exc_info = None
        self._logger.log(level, message, *args, exc_info=exc_info, **kwargs)

    def exception_message(self, exception_type, exception=None, message="no message",
                          status=Status.EXCEPTION, progress=None, level=logging.ERROR):
        # type: (Type[Exception], Optional[Exception], str, AnyStatusType, Optional[Number], int) -> Exception
        """
        Logs to the job the specified error message with the provided exception type.

        :returns: formatted exception with message to be raised by calling function.
        """
        exc_msg = f": [{exception!s}]" if isinstance(exception, Exception) else ""
        err_msg = f"{message}\n{fully_qualified_name(exception_type)}{exc_msg}"
        self.log_message(status=status, level=level, message=err_msg, progress=progress)
        return exception_type(f"{message}{exc_msg}")

    @property
    def job(self):
        # type: () -> Job
        """
        Obtain the job associated to this package execution as specified by the provided UUID.

        Process must be in "execute" state under :mod:`pywps` for this job to be available.
        """
        if self._job is None:
            store = get_db(self.settings).get_store(StoreJobs)
            self._job = store.fetch_by_id(self.uuid)
        return self._job

    @classmethod
    def map_step_progress(cls, step_index, steps_total):
        # type: (int, int) -> Number
        """
        Calculates the percentage progression of a single step of the full process.

        .. note::
            The step procession is adjusted according to delimited start/end of the underlying `CWL` execution to
            provide a continuous progress percentage over the complete execution. Otherwise, we would have values
            that jump around according to whichever progress the underlying remote `WPS` or monitored `CWL` employs,
            if any is provided.
        """
        return map_progress(100 * step_index / steps_total, PACKAGE_PROGRESS_CWL_RUN, PACKAGE_PROGRESS_CWL_DONE)

    @property
    def auth(self):
        # type: () -> AnyHeadersContainer
        if self.request:
            return self.request.auth_headers
        return {}

    def _handler(self, request, response):
        # type: (WorkerRequest, ExecuteResponse) -> ExecuteResponse
        """
        Method called when process receives the WPS execution request.
        """
        # pylint: disable=R1260,too-complex  # FIXME

        # note: only 'LOGGER' call allowed here, since 'setup_loggers' not called yet
        LOGGER.debug("HOME=%s, Current Dir=%s", os.environ.get("HOME"), os.path.abspath(os.curdir))
        self.request = request
        self.response = response
        self.package_id = self.request.identifier

        try:
            try:
                # workflows do not support stdout/stderr
                log_stdout_stderr = (
                    self.package_type != ProcessType.WORKFLOW
                    and self.package_requirement.get("class") not in CWL_REQUIREMENT_APP_REMOTE
                )
                self.setup_loggers(log_stdout_stderr)
                self.update_status("Preparing package logs done.", PACKAGE_PROGRESS_PREP_LOG, Status.RUNNING)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed preparing package logging.")

            self.update_status("Launching package...", PACKAGE_PROGRESS_LAUNCHING, Status.RUNNING)

            # early validation to ensure proper instance is defined for target process/package
            # Note:
            #   This is only to ensure we stop execution in case some process was deployed somehow with mandatory
            #   remote execution, but cannot accomplish it due to mismatching configuration. This can occur if
            #   configuration was modified and followed by Weaver reboot with persisted WPS-remote process.
            config = get_weaver_configuration(self.settings)
            self.remote_execution = config in WeaverFeature.REMOTE
            problem_needs_remote = check_package_instance_compatible(self.package)
            if not self.remote_execution:
                if problem_needs_remote:
                    raise self.exception_message(
                        PackageExecutionError,
                        message=(
                            f"Weaver instance is configured as [{config}] but remote execution with one "
                            f"of {list(WeaverFeature.REMOTE)} is required for process [{self.package_id}] "
                            f"because {problem_needs_remote}. Aborting execution."
                        )
                    )
            # switch back to local execution if hybrid execution can handle this package by itself (eg: Docker, builtin)
            elif config == WeaverConfiguration.HYBRID:
                self.remote_execution = problem_needs_remote is not None

            loading_context = LoadingContext()
            if self.remote_execution:
                # EMS/Hybrid dispatch the execution to ADES or remote WPS
                loading_context.construct_tool_object = self.make_tool

            self.update_effective_user()
            self.update_requirements()
            self.update_cwl_schema_names()

            runtime_params = self.setup_runtime()
            self.log_message(
                f"Using cwltool.RuntimeContext args:\n{Lazify(lambda: json.dumps(runtime_params, indent=2))}",
                level=logging.DEBUG,
            )
            runtime_context = RuntimeContext(kwargs=runtime_params)
            runtime_context.secret_store = SecretStore()  # pre-allocate to reuse the same references as needed
            self.setup_provenance(loading_context, runtime_context)
            try:
                self.step_launched = []
                package_inst, _, self.step_packages = _load_package_content(self.package,
                                                                            package_name=self.package_id,
                                                                            # no data source for local package
                                                                            data_source=None,
                                                                            loading_context=loading_context,
                                                                            runtime_context=runtime_context)
            except Exception as ex:
                raise PackageRegistrationError(f"Exception occurred on package instantiation: '{ex!r}'")
            self.update_status("Loading package content done.", PACKAGE_PROGRESS_LOADING, Status.RUNNING)

            try:
                cwl_inputs_info = {i["name"]: i for i in package_inst.t.inputs_record_schema["fields"]}
                self.update_status("Retrieve package inputs done.", PACKAGE_PROGRESS_GET_INPUT, Status.RUNNING)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed retrieving package input types.")
            try:
                # identify EOImages from payload
                request.inputs = opensearch.get_original_collection_id(self.payload, request.inputs)
                eoimage_data_sources = opensearch.get_eo_images_data_sources(self.payload, request.inputs)
                if eoimage_data_sources:
                    self.update_status("Found EOImage data-source definitions. "
                                       "Updating inputs with OpenSearch sources.",
                                       PACKAGE_PROGRESS_ADD_EO_IMAGES, Status.RUNNING)
                    accept_mime_types = opensearch.get_eo_images_mime_types(self.payload)
                    opensearch.insert_max_occurs(self.payload, request.inputs)
                    request.inputs = opensearch.query_eo_images_from_wps_inputs(request.inputs,
                                                                                eoimage_data_sources,
                                                                                accept_mime_types,
                                                                                settings=self.settings)
                cwl_schema_refs = package_inst.t.names.names
                cwl_inputs = self.make_inputs(request.inputs, cwl_inputs_info, cwl_schema_refs)
                self.update_status("Convert package inputs done.", PACKAGE_PROGRESS_CONVERT_INPUT, Status.RUNNING)
            except PackageException as exc:
                raise self.exception_message(type(exc), None, str(exc))  # re-raise as is, but with extra log entry
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed to load package inputs.")

            try:
                self.update_status("Checking package prerequisites... "
                                   "(operation could take a while depending on requirements)",
                                   PACKAGE_PROGRESS_PREPARATION, Status.RUNNING)
                setup_status = self.setup_docker_image()
                if setup_status not in [None, True]:
                    raise PackageAuthenticationError
                self.update_status("Package ready for execution.", PACKAGE_PROGRESS_PREPARATION, Status.RUNNING)
            except Exception:  # noqa: W0703 # nosec: B110  # don't pass exception to below message
                raise self.exception_message(PackageAuthenticationError, None, "Failed Docker image preparation.")

            try:
                self.update_status("Running package...", PACKAGE_PROGRESS_CWL_RUN, Status.RUNNING)
                cwl_inputs = mask_process_inputs(self.package, cwl_inputs, runtime_context.secret_store)
                self.log_message(
                    f"Launching process package with inputs:\n{Lazify(lambda: json.dumps(cwl_inputs, indent=2))}",
                    level=logging.DEBUG,
                )
                result = package_inst(**cwl_inputs)  # type: CWL_Results
                self.update_status("Package execution done.", PACKAGE_PROGRESS_CWL_DONE, Status.RUNNING)
            except Exception as exc:
                if isinstance(exc, CWLException):
                    lines = self.insert_package_log(exc)
                    LOGGER.debug("Captured logs:\n%s", "\n".join(lines))
                raise self.exception_message(PackageExecutionError, exc, "Failed package execution.")
            # FIXME: this won't be necessary using async routine (https://github.com/crim-ca/weaver/issues/131)
            self.insert_package_log(result)
            try:
                self.make_outputs(result)
                self.update_status("Generate package outputs done.", PACKAGE_PROGRESS_PREP_OUT, Status.RUNNING)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed to save package outputs.")
            try:
                self.finalize_provenance(runtime_context)
            except Exception as exc:  # pragma: no cover  # only safeguard, it's good if this branch never occurs!
                self.exception_message(
                    PackageExecutionError,
                    exc,
                    "Failed to save package PROV metadata. Ignoring error to avoid failing execution.",
                    level=logging.WARN,
                )
        except Exception:
            # return log file location by status message since outputs are not obtained by WPS failed process
            log_url = f"{get_wps_output_url(self.settings)}/{self.uuid}.log"
            error_msg = f"Package completed with errors. Server logs: [{self._log_file}], Available at: [{log_url}]"
            self.update_status(error_msg, self.percent, Status.FAILED)
            raise
        self.update_status("Package operations complete.", PACKAGE_PROGRESS_DONE, Status.SUCCEEDED)
        return self.response

    def must_fetch(self, input_ref, input_type):
        # type: (str, PACKAGE_COMPLEX_TYPES) -> bool
        """
        Figures out if file reference should be fetched immediately for local execution.

        If anything else than local script/docker, remote ADES/WPS process will fetch it.
        S3 are handled here to avoid error on remote WPS not supporting it.

        .. seealso::
            - :ref:`file_ref_types`
            - :ref:`dir_ref_type`
        """
        if self.remote_execution or self.package_type == ProcessType.WORKFLOW:
            return False
        if self.package_requirement["class"] in CWL_REQUIREMENT_APP_REMOTE:
            if input_ref.startswith("s3://"):
                return True
            return False
        if input_type == PACKAGE_FILE_TYPE:
            return not os.path.isfile(input_ref)
        # fetch if destination directory was created in advance but not yet populated with its contents
        return not os.path.isdir(input_ref) or not os.listdir(input_ref)

    def make_inputs(self,
                    wps_inputs,         # type: Dict[str, Deque[WPS_Input_Type]]
                    cwl_inputs_info,    # type: Dict[str, CWL_Input_Type]
                    cwl_schema_names,   # type: CWL_SchemaNames
                    ):                  # type: (...) -> Dict[str, ValueType]
        """
        Converts :term:`WPS` input values to corresponding :term:`CWL` input values for processing by the package.

        The :term:`WPS` inputs must correspond to :mod:`pywps` definitions.
        Multiple values (repeated objects with corresponding IDs) are adapted to arrays as needed.
        All :term:`WPS` `Complex` types are converted to appropriate locations based on data or reference specification.

        :param wps_inputs: Actual :term:`WPS` inputs parsed from execution request.
        :param cwl_inputs_info: Expected CWL input definitions for mapping.
        :param cwl_schema_names: Mapping of CWL type schema references to resolve 'type: <ref>' if used in a definition.
        :return: :term:`CWL` input values.
        """
        cwl_inputs = {}
        for input_id in wps_inputs:
            # skip empty inputs (if that is even possible...)
            input_occurs = wps_inputs[input_id]
            if len(input_occurs) <= 0:
                continue
            # process single occurrences
            input_i = input_occurs[0]
            # handle as reference/data
            io_def = get_cwl_io_type(cwl_inputs_info[input_id], cwl_schema_names=cwl_schema_names)
            if isinstance(input_i, (ComplexInput, BoundingBoxInput)) or io_def.type in PACKAGE_COMPLEX_TYPES:
                # extend array data that allow max_occur > 1
                # drop invalid inputs returned as None
                if io_def.array:
                    input_href = [self.make_location_input(io_def.type, input_def) for input_def in input_occurs]
                    input_href = [cwl_input for cwl_input in input_href if cwl_input is not None]
                else:
                    input_href = self.make_location_input(io_def.type, input_i)
                if input_href:
                    cwl_inputs[input_id] = input_href
            elif isinstance(input_i, LiteralInput):
                # extend array data that allow max_occur > 1
                if io_def.array:
                    input_data = [self.make_literal_input(input_def) for input_def in input_occurs]
                else:
                    input_data = self.make_literal_input(input_i)
                cwl_inputs[input_id] = input_data
            else:
                raise PackageTypeError(f"Undefined package input for execution: {type(input_i)}.")
        return cwl_inputs

    @staticmethod
    def make_literal_input(input_definition):
        # type: (LiteralInput) -> JSON
        """
        Converts Literal Data representations to compatible :term:`CWL` contents with :term:`JSON` encodable values.
        """
        if input_definition.as_reference:
            return input_definition.url
        return any2json_literal_data(input_definition.data, input_definition.data_type)

    @staticmethod
    def make_location_bbox(input_definition):
        # type: (BoundingBoxInput) -> None
        """
        Convert a Bounding Box to a compatible :term:`CWL` ``File`` using corresponding IOHandler of a Complex input.
        """
        input_definition.data_format = Format(ContentType.APP_JSON, schema=sd.OGC_API_BBOX_FORMAT)
        input_location = IOHandler._build_file_name(input_definition)
        input_definition._iohandler = FileHandler(input_location, input_definition)
        input_value = {"bbox": input_definition.data, "crs": input_definition.crs or input_definition.crss[0]}
        input_definition.data = input_value

        # make sure the file is generated with its contents
        with open(input_definition.file, mode="w", encoding="utf-8") as bbox_file:
            json.dump(input_value, bbox_file, ensure_ascii=False)

    def make_location_input_security_check(self, input_scheme, input_type, input_id, input_location, input_definition):
        # type: (str, CWL_IO_ComplexType, str, str, ComplexInput) -> str
        """
        Perform security access validation of the reference, and resolve it afterwards if accessible.

        Auto-map local file if possible to avoid useless download from current server.
        Resolve :term:`Vault` reference with local file stored after decryption.

        :returns: Updated file location if any resolution occurred.
        """
        if input_scheme == "vault":
            if input_type != PACKAGE_FILE_TYPE:
                raise PackageExecutionError(
                    f"Vault reference must be a file, but resolved [{input_type}] type "
                    f"instead for input [{input_id}] from location [{input_location}]."
                )
            vault_id = bytes2str(urlparse(input_location).hostname)
            input_url = get_vault_url(vault_id, self.settings)
            resp = request_extra("HEAD", input_url, settings=self.settings, headers=self.auth)
            if resp.status_code == 200:
                self.log_message(
                    f"Detected and validated remotely accessible reference [{input_location}] "
                    f"matching local Vault [{input_url}]. Replacing URL reference for local access.",
                    level=logging.DEBUG,
                )
                # pre-fetch by move and delete file from vault and decrypt it (as download would)
                # to save transfer time/data from local file already available
                auth = parse_vault_token(self.auth.get(sd.XAuthVaultFileHeader.name), unique=False)
                file = get_authorized_file(vault_id, auth.get(vault_id), self.settings)
                input_location = map_vault_location(input_url, self.settings)
                input_location = decrypt_from_vault(file, input_location,
                                                    out_dir=input_definition.workdir, delete_encrypted=True)
                self.log_message(
                    f"Moved Vault file to temporary location: [{input_location}]. "
                    "File not accessible from Vault endpoint anymore. "
                    "Location will be deleted after process execution.",
                    level=logging.DEBUG,
                )
            else:
                self.log_message(
                    f"Detected Vault file reference that is not accessible [{input_location}] caused "
                    f"by HTTP [{resp.status_code}] Detail:\n{Lazify(lambda: repr_json(resp.text, indent=2))}",
                    level=logging.ERROR,
                )
                raise PackageAuthenticationError(
                    f"Input {input_id} with Vault reference [{vault_id}] is not accessible."
                )
        else:
            input_local_ref = map_wps_output_location(input_location, self.settings)
            if input_local_ref:
                resp = request_extra("HEAD", input_location, settings=self.settings, headers=self.auth)
                if resp.status_code == 200:  # if failed, following fetch will produce the appropriate HTTP error
                    self.log_message(
                        f"Detected and validated remotely accessible reference [{input_location}] "
                        f"matching local WPS outputs [{input_local_ref}]. Skipping fetch using direct reference.",
                        level=logging.DEBUG,
                    )
                    input_location = input_local_ref
        return input_location

    def make_location_input(self, input_type, input_definition):
        # type: (CWL_IO_ComplexType, Union[ComplexInput, BoundingBoxInput]) -> Optional[JSON]
        """
        Generates the JSON content required to specify a `CWL` ``File`` or ``Directory`` input from a location.

        If the input reference corresponds to an HTTP URL that is detected as matching the local WPS output endpoint,
        implicitly convert the reference to the local WPS output directory to avoid useless download of available file.
        Since that endpoint could be protected though, perform a minimal HEAD request to validate its accessibility.
        Otherwise, this operation could incorrectly grant unauthorized access to protected files by forging the URL.

        If the process requires ``OpenSearch`` references that should be preserved as is, scheme defined by
        :py:data:`weaver.processes.constants.OpenSearchField.LOCAL_FILE_SCHEME` prefix instead of ``http(s)://``
        is expected.

        Any other variant of file reference will be fetched as applicable by the relevant schemes.

        If the reference corresponds to a ``Directory``, all files that can be located in it will be fetched as
        applicable by the relevant scheme of the reference. It is up to the remote location to provide listing
        capabilities accordingly to view available files.

        .. seealso::
            Documentation details of resolution based on schemes defined in :ref:`file_ref_types` section.
        """
        # NOTE:
        #   When running as EMS, must not call data/file methods if URL reference, otherwise contents
        #   get fetched automatically by PyWPS objects.
        input_location = None
        input_id = input_definition.identifier
        # cannot rely only on 'as_reference' as often it is not provided by the request, although it's an href
        if input_definition.as_reference:
            input_location = input_definition.url
        # convert the BBOX to a compatible CWL File using corresponding IOHandler setup as ComplexInput
        if isinstance(input_definition._iohandler, NoneIOHandler) and isinstance(input_definition, BoundingBoxInput):
            self.make_location_bbox(input_definition)
        # FIXME: PyWPS bug
        #   Calling 'file' method fetches it, and it is always called by the package itself
        #   during type validation if the MODE is anything else than disabled (MODE.NONE).
        #   MODE.SIMPLE is needed minimally to check MIME-TYPE of input against supported formats.
        #       - https://github.com/geopython/pywps/issues/526
        #       - https://github.com/crim-ca/weaver/issues/91
        #   since href is already handled (pulled and staged locally), use it directly to avoid double fetch with CWL
        #   validate using the internal '_file' instead of 'file' otherwise we trigger the fetch
        #   normally, file should be pulled and this check should fail
        input_definition_file = input_definition._iohandler._file  # noqa: W0212
        if input_definition_file and os.path.isfile(input_definition_file):
            # Because storage handlers assume files, a directory (pseudo-file with trailing '/' unknown to PyWPS)
            # could be mistakenly generated as an empty file. Wipe it in this case to ensure proper resolution.
            if input_type == PACKAGE_DIRECTORY_TYPE and os.stat(input_definition_file).st_size == 0:
                os.remove(input_definition_file)
            else:
                input_location = input_definition_file
        # if source type is data, we actually need to call 'data' (without fetch of remote file, already fetched)
        # value of 'file' in this case points to a local file path where the wanted link was dumped as raw data
        if input_definition.source_type == SOURCE_TYPE.DATA:
            if input_definition.data is not None:
                # use 'file' instead of '_iohandler._file' in this case to make sure
                # the reference containing 'data' is generated if not already done
                # this file will be needed to pass down to CWL by reference
                input_location = input_definition.file
        input_scheme = None
        if not input_location:
            url = getattr(input_definition, "url")
            if isinstance(url, str):
                input_scheme = urlparse(url).scheme
            if input_scheme and input_scheme in SUPPORTED_FILE_SCHEMES:
                input_location = url
            else:
                # last option, could not resolve 'lazily' so will fetch data if needed
                input_location = input_definition.data
                input_scheme = None
        # FIXME: PyWPS bug (https://github.com/geopython/pywps/issues/633)
        #   Optional File inputs receive 'data' content that correspond to 'default format' definition if not provided.
        #   This is invalid since input is not provided, it should not be there at all (default format != default data).
        #   Patch with a combination of available detection methods to be safe:
        #   - The 'file' attribute gets resolved to the process '{workdir}/input' temporary file.
        #     This 'file' is instead named 'input_{uuid}' when it is actually resolved to real input href/data contents.
        #     The IO handler reports 'None' more reliably with its internal '_file' attribute.
        #   - For even more robustness, verify that erroneous 'data' matches the 'default format'.
        #     The media-type should match and 'default' argument should True since it resolve with '_default' argument.
        default_format_def = getattr(input_definition, "_default", None)
        if (
            isinstance(default_format_def, dict) and
            input_location == default_format_def and
            input_definition_file is None and
            # input_definition.size == 0 and  # not reliable, sometimes fails because 'data' is dict instead of str
            default_format_def.get("default") is True and
            any(default_format_def.get("mimeType") == fmt.mime_type and fmt.mime_type is not None
                for fmt in input_definition.supported_formats)
        ):
            self.log_message(
                f"{input_type} input ({input_id}) DROPPED. Detected default format as data.",
                level=logging.DEBUG,
            )
            return None

        input_location = self.make_location_input_security_check(
            input_scheme,
            input_type,
            input_id,
            input_location,
            input_definition
        )

        if self.must_fetch(input_location, input_type):
            self.log_message(f"{input_type} input ({input_id}) ATTEMPT fetch: [{input_location}]")
            if input_type == PACKAGE_FILE_TYPE:
                input_location = fetch_file(input_location, input_definition.workdir,
                                            settings=self.settings, headers=self.auth)
            elif input_type == PACKAGE_DIRECTORY_TYPE:
                # Because a directory reference can contain multiple sub-dir definitions,
                # avoid possible conflicts with other inputs by nesting them under the ID.
                # This also ensures that each directory input can work with a clean staging directory.
                out_dir = cast(str, os.path.join(input_definition.workdir, input_definition.identifier))
                locations = fetch_directory(input_location, out_dir,
                                            settings=self.settings, headers=self.auth)
                if not locations:
                    raise PackageExecutionError(
                        f"Directory reference resolution method for input [{input_id}] "
                        f"from location [{input_location}] did not produce any staged file."
                    )
                input_directory_name = get_secure_directory_name(input_definition.url)
                input_location = os.path.join(out_dir, input_directory_name)
            else:
                raise PackageExecutionError(
                    f"Unknown reference staging resolution method for [{input_type}] type "
                    f"specified for input [{input_id}] from location [{input_location}]."
                )
        else:
            self.log_message(f"{input_type} input ({input_id}) SKIPPED fetch: [{input_location}]")

        # when the process is passed around between OWSLib and PyWPS, it is very important to provide the scheme
        # otherwise, they will interpret complex data directly instead of by reference
        # (see for example 'owslib.wps.ComplexDataInput.get_xml' that relies only on the
        #  presence of the scheme to infer whether the complex data is a reference or not)
        if "://" not in input_location:
            input_location = f"file://{input_location}"

        location = {"location": input_location, "class": input_type}
        if input_definition.data_format is not None and input_definition.data_format.mime_type:
            fmt = get_cwl_file_format(input_definition.data_format.mime_type, make_reference=True)
            if fmt is not None:
                location["format"] = fmt
        return location

    def make_outputs(self, cwl_result):
        # type: (CWL_Results) -> None
        """
        Maps `CWL` result outputs to corresponding `WPS` outputs.
        """
        for output_id in self.request.outputs:  # iterate over original WPS outputs, extra such as logs are dropped
            if isinstance(cwl_result[output_id], list) and not isinstance(self.response.outputs[output_id], list):
                # provide more details than poorly descriptive IndexError
                if not len(cwl_result[output_id]):
                    raise PackageExecutionError(
                        f"Process output '{output_id}' expects at least one value but none was found. "
                        "Possible incorrect glob pattern definition in CWL Application Package."
                    )
                self.make_array_output(cwl_result, output_id)
                continue

            if isinstance(cwl_result[output_id], dict):
                if "location" not in cwl_result[output_id] and os.path.isfile(str(cwl_result[output_id])):
                    raise PackageTypeError(
                        f"Process output '{output_id}' defines CWL type other than 'File'. "
                        "Application output results must use 'File' type to return file references."
                    )
                if "location" in cwl_result[output_id]:
                    self.make_location_output(cwl_result, output_id)
                if isinstance(self.response.outputs[output_id], ComplexOutput):
                    continue

                # unpack CWL File into Bounding Box
                if isinstance(self.response.outputs[output_id], BoundingBoxOutput):
                    self.make_bbox_output(cwl_result, output_id)
                    continue

            self.make_literal_output(cwl_result, output_id)

    def make_array_output(self, cwl_result, output_id):
        # type: (CWL_Results, str) -> None
        """
        Converts an array output into a :term:`JSON` literal representation.
        """
        # apply the relevant operation for each item type
        # appropriate validation, storage and data-format conversion should be applied
        collect_items = []
        for idx, item in enumerate(cwl_result[output_id]):
            if isinstance(item, dict):
                if "location" in item:
                    self.make_location_output(cwl_result, output_id, index=idx)
                else:
                    self.make_bbox_output(cwl_result, output_id, index=idx)
            else:
                self.make_literal_output(cwl_result, output_id, index=idx)

            # retrieve the temporarily stored result as a single item
            collect_items.append(self.response.outputs[output_id].json)

        # use a custom representation to allow us handling the raw data array properly
        array_data = repr_json(collect_items, force_string=True, indent=None)

        # avoid error on mismatching atomic item type and the JSON array as string
        self.response.outputs[output_id] = ComplexOutput(  # convert in case it was a literal
            self.response.outputs[output_id].identifier,
            self.response.outputs[output_id].title,
            # use an alternate RAW+JSON media-type to avoid ambiguity between a real complex data
            # that uses a JSON file (potentially reported as raw data instead of reference) and
            # this workaround embedded JSON string for encapsulating multi-value outputs unsupported by WPS
            data_format=Format(mime_type=ContentType.APP_RAW_JSON),
            supported_formats=[Format(mime_type=ContentType.APP_RAW_JSON)],
            as_reference=False,
            mode=MODE.NONE,
        )
        self.response.outputs[output_id]._iohandler = DataHandler(array_data, self.response.outputs[output_id])
        self.log_message(f"Resolved WPS output [{output_id}] as complex array data embedded as JSON string")

    def make_literal_output(self, cwl_result, output_id, index=None):
        # type: (CWL_Results, str, Optional[int]) -> None
        """
        Converts Literal Data representations to compatible :term:`CWL` contents with :term:`JSON` encodable values.
        """
        data_cwl = cwl_result[output_id][index] if index is not None else cwl_result[output_id]
        data_output = repr_json(data_cwl, force_string=False)
        self.response.outputs[output_id].data = data_output
        self.response.outputs[output_id].as_reference = False
        self.log_message(f"Resolved WPS output [{output_id}] as literal data")

    def make_bbox_output(self, cwl_result, output_id, index=None):
        # type: (CWL_Results, str, Optional[int]) -> None
        """
        Generates the :term:`WPS` Bounding Box output from the :term:`CWL` ``File``.

        Assumes that location outputs were resolved beforehand, such that the file is available locally.
        """
        bbox_cwl = cwl_result[output_id][index] if index is not None else cwl_result[output_id]
        bbox_loc = bbox_cwl["location"]
        if bbox_loc.startswith("file://"):
            bbox_loc = bbox_loc[7:]
        with open(bbox_loc, mode="r", encoding="utf-8") as bbox_file:
            bbox_data = json.load(bbox_file)
        self.response.outputs[output_id].data = bbox_data["bbox"]
        self.response.outputs[output_id].crs = bbox_data["crs"]
        self.response.outputs[output_id].dimensions = len(bbox_data["bbox"]) // 2
        self.response.outputs[output_id].as_reference = False

    def make_location_output(self, cwl_result, output_id, index=None):
        # type: (CWL_Results, str, Optional[int]) -> None
        """
        Rewrite the :term:`WPS` output with required location using result path from :term:`CWL` execution.

        Configures the parameters such that :mod:`pywps` will either auto-resolve the local paths to match with URL
        defined by ``weaver.wps_output_url`` or upload it to `S3` bucket from ``weaver.wps_output_s3_bucket`` and
        provide reference directly.

        .. seealso::
            - :func:`weaver.wps.load_pywps_config`
        """
        s3_bucket = self.settings.get("weaver.wps_output_s3_bucket")
        result_cwl = cwl_result[output_id][index] if index is not None else cwl_result[output_id]
        result_loc = result_cwl["location"].replace("file://", "").rstrip("/")
        result_path = os.path.split(result_loc)[-1]
        result_type = result_cwl.get("class", PACKAGE_FILE_TYPE)
        result_cwl_fmt = result_cwl.get("format")
        result_is_dir = result_type == PACKAGE_DIRECTORY_TYPE
        if result_is_dir and not result_path.endswith("/"):
            result_path += "/"
            result_loc += "/"
            result_cwl_fmt = ContentType.APP_DIR

        # PyWPS internally sets a new FileStorage (default) inplace when generating the JSON definition of the output.
        # This is done such that the generated XML status document in WPS response can obtain the output URL location.
        # Call Stack:
        #   - self.update_status (the one called right after 'self.make_outputs' is called)
        #   - self.response._update_status
        #   - pywps.response.execute.ExecuteResponse._update_status_doc
        #   - pywps.response.execute.ExecuteResponse._construct_doc
        #   - pywps.response.execute.ExecuteResponse.json
        #   - pywps.response.execute.ExecuteResponse.process.json
        #   - pywps.app.Process.Process.json
        #   - pywps.inout.outputs.ComplexOutput.json  (for each output in Process)
        #   - pywps.inout.outputs.ComplexOutput._json_reference
        # Which sets:
        #   - pywps.inout.outputs.ComplexOutput.storage = FileStorageBuilder().build()
        # Followed by:
        #   - pywps.inout.outputs.ComplexOutput.get_url()
        #   - pywps.inout.outputs.ComplexOutput.storage.store()
        # But, setter "pywps.inout.basic.ComplexOutput.storage" doesn't override predefined 'storage'.
        # Therefore, preemptively override "ComplexOutput._storage" to whichever location according to use case.
        # Override builder per output to allow distinct S3/LocalFile for it and XML status that should remain local.
        storage_type = STORE_TYPE.S3 if s3_bucket else STORE_TYPE.PATH
        storage = self.make_location_storage(storage_type, result_type, output_id)
        self.response.outputs[output_id]._storage = storage  # noqa: W0212

        # pywps will resolve file paths for us using its WPS request UUID
        os.makedirs(self.workdir, exist_ok=True)
        result_wps = os.path.join(self.workdir, result_path)

        if os.path.realpath(result_loc) != os.path.realpath(result_wps):
            self.log_message(f"Moving [{output_id}]: [{result_loc}] -> [{result_wps}]")
            if result_is_dir:
                adjust_directory_local(result_loc, self.workdir, OutputMethod.MOVE)
            else:
                adjust_file_local(result_loc, self.workdir, OutputMethod.MOVE)

        # params 'as_reference + file' triggers 'ComplexOutput.json' to map the WPS-output URL from the WPS workdir
        resp_output = self.response.outputs[output_id]  # type: ComplexOutput
        resp_output.as_reference = True

        # Since each output has its own storage already prefixed by '[Context/]JobID/', avoid JobID nesting another dir.
        # Instead, let it create a dir matching the output ID to get '[Context/]JobID/OutputID/[file(s).ext]'
        resp_output.uuid = output_id

        # guess the produced file media-type to override the default one selected
        # this step must be done before setting 'file' attribute, as that will trigger the validator check
        if isinstance(resp_output, ComplexOutput):  # don't process bbox that are 'File' in CWL
            self.resolve_output_format(resp_output, result_path, result_cwl_fmt)

        resp_output.file = result_wps
        self.log_message(f"Resolved WPS output [{output_id}] as file reference: [{result_wps}]")

    @staticmethod
    def resolve_output_format(output, result_path, result_cwl_format):
        # type: (ComplexOutput, str, Optional[str]) -> None
        """
        Resolves the obtained media-type for an output :term:`CWL` ``File``.

        Considers :term:`CWL` results ``format``, the file path, and the :term:`Process` description to resolve the
        best possible match, retaining a much as possible the metadata that can be resolved from their corresponding
        details.

        When the media-type is resolved, ensure that an appropriate format validator is applied to perform relevant
        checks, or omit them when not implemented.
        """
        result_ctype = map_cwl_media_type(result_cwl_format)
        if not result_ctype:
            # fallback attempt using extension if available
            result_ext = os.path.splitext(result_path)[-1]
            if result_ext:
                result_ctype = get_content_type(result_ext)
        if not result_ctype:
            if output.valid_mode != MODE.NONE and output.validator is emptyvalidator:
                output.valid_mode = MODE.NONE  # disable to avoid ensured failure
            return

        # - When resolving media-types, use the corresponding supported format defined in the process definition
        #   instead of the generated one from CWL format, because process supported formats can provide more details
        #   than the CWL format does, such as the encoding and any reference schema.
        # - If no match is found, leave default format without applying the result CWL format since
        #   we cannot generate an invalid output with unsupported formats (will raise later anyway).
        # - Clean the media-types to consider partial match from extra parameters such as charset.
        #   Gradually attempt mathing from exact type to looser definitions.
        result_format_base = get_format(result_ctype)
        result_ctype_clean = clean_media_type_format(
            result_format_base.mime_type,
            strip_parameters=True,
            suffix_subtype=True,
        )
        result_formats = [result_format_base]
        if result_format_base.mime_type != result_ctype_clean:
            result_formats.append(get_format(result_ctype_clean))
        for result_format in result_formats:
            for strip, simplify in [
                (False, False),
                (True, False),
                (False, True),
                (True, True),
            ]:
                for fmt in output.supported_formats:
                    fmt_type = clean_media_type_format(fmt.mime_type, strip_parameters=strip, suffix_subtype=simplify)
                    if fmt_type == result_format.mime_type:
                        output.data_format = fmt
                        validator = get_validator(fmt.mime_type)
                        if output.valid_mode != MODE.NONE and validator is emptyvalidator:
                            if fmt_type == ContentType.TEXT_PLAIN:
                                output.valid_mode = MODE.NONE  # disable since text can be used with many extensions
                            else:
                                output.data_format.validate = format_extension_validator
                        return

        # if the format is the "any" media-type default, allow override by explicit format defined by the result
        if output.data_format.mime_type in [ContentType.TEXT_PLAIN, ContentType.ANY] and output.data_format.default:
            output.supported_formats = (result_format_base, )
            output.data_format = result_format_base

        # no match found, minimally check for extension
        if output.valid_mode != MODE.NONE and output.validator is emptyvalidator:
            output.data_format.validate = format_extension_validator

    def make_location_storage(self, storage_type, location_type, output_id):
        # type: (STORE_TYPE, PACKAGE_COMPLEX_TYPES, str) -> Union[FileStorage, S3Storage, DirectoryNestedStorage]
        """
        Generates the relevant storage implementation with requested types and references.

        :param storage_type: Where to store the outputs.
        :param location_type: Type of output as defined by CWL package type.
        :param output_id: expected output identifier that will employ this storage.
        :return: Storage implementation.
        """
        if location_type == PACKAGE_FILE_TYPE and storage_type == STORE_TYPE.PATH:
            storage = FileStorageBuilder().build()
        elif location_type == PACKAGE_FILE_TYPE and storage_type == STORE_TYPE.S3:
            storage = S3StorageBuilder().build()
        elif location_type == PACKAGE_DIRECTORY_TYPE and storage_type == STORE_TYPE.PATH:
            storage = DirectoryNestedStorage(FileStorageBuilder().build())
        elif location_type == PACKAGE_DIRECTORY_TYPE and storage_type == STORE_TYPE.S3:
            storage = DirectoryNestedStorage(S3StorageBuilder().build())
        else:
            raise PackageExecutionError(
                "Cannot resolve unknown location storage for "
                f"(storage: {storage_type}, type: {location_type})."
            )

        output_job_id = str(self.response.uuid)
        output_prefix = self.job.result_path(job_id=output_job_id)
        # pylint: disable=attribute-defined-outside-init  # references to nested storage dynamically created
        if storage_type == STORE_TYPE.S3:
            # when using S3 storage, the 'prefix' is directly employed with the file name
            # results should be nested under their output ID to allow arrays and alternate types
            # therefore, preemptively adjust the prefix to do as such
            # however, do not do it for the case of directories, since the output ID is already the directory itself
            if location_type == PACKAGE_DIRECTORY_TYPE:
                storage.prefix = output_prefix
            else:
                storage.prefix = os.path.join(output_prefix, output_id)
        else:
            # when using other storage than S3, the 'target' is automatically built using a join
            # of 'prefix' and the output ID stored in the parent result object containing this storage
            storage.target = os.path.join(storage.target, output_prefix)
            storage.output_url = os.path.join(str(storage.output_url), output_prefix)
            os.makedirs(storage.target, exist_ok=True)  # pywps handles Job UUID dir creation, but not nested dirs
        return storage

    def make_tool(self, toolpath_object, loading_context):
        # type: (CWL_ToolPathObject, LoadingContext) -> ProcessCWL
        """
        Method called by :mod:`cwltool` to generate the tool object from the :term:`CWL` definition.
        """
        from weaver.processes.wps_workflow import default_make_tool

        # When the tool package ID corresponds directly to the toolpath object ID,
        # it means that either an atomic process was invoked, or that the top-most Workflow is called.
        # In such case, it is safe to return the self-reference for the tool job, as it will refer to the same log/job.
        # Also, this avoids duplicate setup of log handlers, which would result in inconsistant progress tracking.
        process_id = shortname(toolpath_object["id"])
        if self.package_id == process_id:
            return default_make_tool(toolpath_object, loading_context, self)

        # Otherwise, the tool creation was triggered by a step under the Workflow.
        # An intermediate package definition must be created to pass around references.
        # However, the PyWPS response and UUID references will not exist yet (since the step job is not yet started).
        # Therefore, only partial initialization can be performed.
        # Their respective full-initialization will be done by the resulting job submitted by the 'remote' execution.
        package_process = WpsPackage(
            identifier=process_id,
            title=process_id,
            package=toolpath_object,
            settings=self.settings,
        )
        # transfer references that will allow the workflow step to correctly
        # update its intermediate logs relative to the overall workflow execution
        package_process.request = self.request
        package_process.response = self.response
        package_process.uuid = self.uuid
        package_process._job = self.job
        package_process.step_packages = self.step_packages
        package_process.step_launched = self.step_launched

        # make sure the logger references are defined to allow logging minimal status update messages
        # however, skip stdout/stderr setup that is not supported by workflows (each steps will do it as needed)
        package_process.setup_loggers(log_stdout_stderr=False)
        return default_make_tool(toolpath_object, loading_context, package_process)

    def get_workflow_step_package(self, job_name):
        # type: (str) -> CWL_WorkflowStepPackage
        """
        Resolve the step :term:`CWL` definition under a :term:`Workflow`.
        """
        try:
            step_details = self.step_packages[job_name]
        except KeyError:  # Perform check directly first in case a step was called literally as '<name>_<index>'
            # In case of Workflow with scattering, job name might be suffixed with an index.
            # Also, to avoid ambiguous references of Workflow steps running in parallel (distinct jobs),
            # unique keys are generated for matching step names, since their sub-CWL might differ.
            # (see 'cwltool.process.uniquename')
            if "_" not in job_name:
                raise
            job_name, job_index = job_name.rsplit("_", 1)
            if not job_index.isnumeric():
                raise
            LOGGER.debug("Resolved step name with index: [%s](%s)", job_name, job_index)
            step_details = self.step_packages[job_name]
        return step_details

    def get_job_process_definition(self, job_name, job_order):  # noqa: E811
        # type: (str, CWL_WorkflowInputs) -> WpsPackage
        """
        Obtain the execution job definition for the given process (:term:`Workflow` step implementation).

        This function is called before running an :term:`ADES` :term:`Job` (either from a :term:`workflow` step or
        simple :term:`EMS` :term:`Job` dispatching).

        It must return a :class:`weaver.processes.wps_process.WpsProcess` instance configured with the
        proper :term:`CWL` package definition, :term:`ADES` target and cookies to access it (if protected).

        :param job_name: The workflow step or the package ID that must be executed.
        :param job_order: Execution input values submitted for the job.
        """

        if job_name == self.package_id:
            # A step is the package itself only for non-workflow package being executed on the EMS
            # default action requires ADES dispatching but hints can indicate also WPS1 or ESGF-CWT provider
            job_type = "package"
        else:
            job_type = "step"

        # Progress made with steps presumes that they are done sequentially and have the same progress weight
        start_step_progress = self.map_step_progress(len(self.step_launched), max(1, len(self.step_packages)))
        end_step_progress = self.map_step_progress(len(self.step_launched) + 1, max(1, len(self.step_packages)))

        self.step_launched.append(job_name)
        self.update_status(f"Preparing to launch {job_type} [{job_name}].", start_step_progress, Status.RUNNING)

        def _update_status_dispatch(_message, _progress, _status, _provider, *_, error=None, **__):
            # type: (str, Number, AnyStatusType, str, Any, Optional[Exception], Any) -> None
            if LOGGER.isEnabledFor(logging.DEBUG) and (_ or __):
                LOGGER.debug("Received additional unhandled args/kwargs to dispatched update status: %s, %s", _, __)
            self.step_update_status(
                _message, _progress, start_step_progress, end_step_progress, job_name, _provider, _status, error=error
            )

        def _get_req_params(_requirement, required_params):
            # type: (CWL_AnyRequirementObject, List[str]) -> CWL_Requirement
            _wps_params = {}
            for _param in required_params:
                if _param not in _requirement:
                    _req = _requirement["class"]
                    raise ValueError(f"Missing requirement detail [{_req}]: {_param}")
                _wps_params[_param] = _requirement[_param]
            return _wps_params

        req_class = resolve_cwl_namespaced_name(self.package_requirement["class"])
        req_source = "requirement/hint"
        if self.package_type == ProcessType.WORKFLOW:
            req_class = ProcessType.WORKFLOW
            req_source = "tool class"

        if (
            (job_type == "step" or self.payload is None)
            and not any(req_class.endswith(req) for req in [CWL_REQUIREMENT_APP_WPS1, CWL_REQUIREMENT_APP_ESGF_CWT])
        ):
            LOGGER.debug("Retrieve WPS-3 process payload for potential Data Source definitions to resolve.")
            self.payload = _get_process_payload(self.identifier, container=self.settings)

        if req_class.endswith(CWL_REQUIREMENT_APP_WPS1):
            self.log_message(f"WPS-1 Package resolved from [{req_source}]: {req_class}")
            from weaver.processes.wps1_process import Wps1Process
            params = _get_req_params(self.package_requirement, ["provider", "process"])
            return Wps1Process(
                provider=params["provider"],
                process=params["process"],
                request=self.request,
                update_status=_update_status_dispatch,
            )
        elif req_class.endswith(CWL_REQUIREMENT_APP_ESGF_CWT):
            self.log_message(f"ESGF-CWT Package resolved from [{req_source}]: {req_class}")
            from weaver.processes.esgf_process import ESGFProcess
            params = _get_req_params(self.package_requirement, ["provider", "process"])
            return ESGFProcess(
                provider=params["provider"],
                process=params["process"],
                request=self.request,
                update_status=_update_status_dispatch,
            )
        elif req_class.endswith(CWL_REQUIREMENT_APP_OGC_API):
            self.log_message(f"OGC API Package resolved from [{req_source}]: {req_class}")
            from weaver.processes.ogc_api_process import OGCAPIRemoteProcess
            params = _get_req_params(self.package_requirement, ["process"])
            return OGCAPIRemoteProcess(step_payload=self.payload,
                                       process=params["process"],
                                       request=self.request,
                                       update_status=_update_status_dispatch)
        else:
            # implements:
            # - `ProcessType.APPLICATION` with `CWL_REQUIREMENT_APP_BUILTIN`
            # - `ProcessType.APPLICATION` with `CWL_REQUIREMENT_APP_DOCKER`
            # - `ProcessType.WORKFLOW` nesting calls to other processes of various types and locations
            self.log_message(f"WPS-3 Package resolved from [{req_source}]: {req_class}")
            from weaver.processes.wps3_process import Wps3Process
            return Wps3Process(step_payload=self.payload,
                               job_order=job_order,
                               process=self.identifier,
                               request=self.request,
                               update_status=_update_status_dispatch)
