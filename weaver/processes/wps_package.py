"""
Representation of :term:`WPS` process with an internal :term:`CWL` package definition.

Functions and classes that offer interoperability and conversion between corresponding elements
defined as :term:`CWL` `CommandLineTool`/`Workflow` and :term:`WPS` `ProcessDescription` in order to
generate :term:`ADES`/:term:`EMS` deployable :term:`Application Package`.

.. seealso::
    - `CWL specification <https://www.commonwl.org/#Specification>`_
    - `WPS-1/2 schemas <http://schemas.opengis.net/wps/>`_
    - `WPS-REST schemas <https://github.com/opengeospatial/wps-rest-binding>`_
    - :mod:`weaver.wps_restapi.api` conformance details
"""

import json
import logging
import os
import posixpath  # pylint: disable=C0411,wrong-import-order
import shutil
import sys
import tempfile
import time
import uuid
from collections import OrderedDict  # pylint: disable=E0611,no-name-in-module   # moved to .abc in Python 3
from copy import deepcopy
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import cwltool
import cwltool.docker
import yaml
from cwltool.context import LoadingContext, RuntimeContext
from cwltool.factory import Factory as CWLFactory, WorkflowStatus as CWLException
from pyramid.httpexceptions import HTTPOk, HTTPServiceUnavailable
from pywps import Process
from pywps.inout import BoundingBoxInput, ComplexInput, LiteralInput
from pywps.inout.basic import SOURCE_TYPE
from pywps.inout.literaltypes import AnyValue
from pywps.inout.storage.file import FileStorageBuilder
from pywps.inout.storage.s3 import S3StorageBuilder
from yaml.scanner import ScannerError

from weaver.config import WEAVER_CONFIGURATION_HYBRID, WEAVER_CONFIGURATIONS_REMOTE, get_weaver_configuration
from weaver.database import get_db
from weaver.exceptions import (
    PackageException,
    PackageExecutionError,
    PackageNotFound,
    PackageRegistrationError,
    PackageTypeError,
    PayloadNotFound
)
from weaver.formats import CONTENT_TYPE_ANY_XML, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_PLAIN, get_cwl_file_format
from weaver.processes import opensearch
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_TYPES,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_INIT_WORKDIR,
    WPS_INPUT,
    WPS_OUTPUT
)
from weaver.processes.convert import (
    cwl2wps_io,
    get_field,
    is_cwl_array_type,
    json2wps_field,
    json2wps_io,
    merge_package_io,
    wps2json_io,
    xml_wps2cwl
)
from weaver.processes.sources import retrieve_data_source_url
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW
from weaver.processes.utils import map_progress
from weaver.status import (
    STATUS_COMPLIANT_PYWPS,
    STATUS_EXCEPTION,
    STATUS_FAILED,
    STATUS_PYWPS_IDS,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    map_status
)
from weaver.store.base import StoreJobs
from weaver.utils import (
    SUPPORTED_FILE_SCHEMES,
    fetch_file,
    get_any_id,
    get_header,
    get_job_log_msg,
    get_log_date_fmt,
    get_log_fmt,
    get_sane_name,
    get_settings,
    request_extra,
    setup_loggers
)
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location
from weaver.wps_restapi.swagger_definitions import process_service

if TYPE_CHECKING:
    from typing import Any, Deque, Dict, List, Optional, Tuple, Type, Union

    from cwltool.factory import Callable as CWLFactoryCallable
    from cwltool.process import Process as ProcessCWL
    from owslib.wps import WPSExecution
    from pywps.app import WPSRequest
    from pywps.response.execute import ExecuteResponse

    from weaver.datatype import Job
    from weaver.processes.convert import (
        ANY_IO_Type,
        CWL_Input_Type,
        JSON_IO_Type,
        PKG_IO_Type,
        WPS_Input_Type,
        WPS_Output_Type
    )
    from weaver.status import AnyStatusType
    from weaver.typedefs import AnyValueType, CWL, JSON, Number, ToolPathObjectType, TypedDict, ValueType

    # note: below requirements also include 'hints'
    CWLRequirement = TypedDict("CWLRequirement", {"class": str}, total=False)
    DictCWLRequirements = Dict[str, Dict[str, str]]  # {'<req>': {<param>: <val>}}
    ListCWLRequirements = List[CWLRequirement]       # [{'class': <req>, <param>: <val>}]
    AnyCWLRequirements = Union[DictCWLRequirements, ListCWLRequirements]
    # results from CWL execution
    CWLResultFile = TypedDict("CWLResultFile", {"location": str}, total=False)
    CWLResultValue = Union[AnyValueType, List[AnyValueType]]
    CWLResultEntry = Union[Dict[str, CWLResultValue], CWLResultFile, List[CWLResultFile]]
    CWLResults = Dict[str, CWLResultEntry]

# NOTE:
#   Only use this logger for 'utility' methods (not residing under WpsPackage).
#   In that case, employ 'self.logger' instead so that the executed process has its self-contained job log entries.
LOGGER = logging.getLogger(__name__)

# CWL package references
PACKAGE_DEFAULT_FILE_NAME = "package"
PACKAGE_EXTENSIONS = frozenset(["yaml", "yml", "json", "cwl", "job"])
PACKAGE_OUTPUT_HOOK_LOG_UUID = "PACKAGE_OUTPUT_HOOK_LOG_{}"

# process execution progress
PACKAGE_PROGRESS_PREP_LOG = 1
PACKAGE_PROGRESS_LAUNCHING = 2
PACKAGE_PROGRESS_LOADING = 5
PACKAGE_PROGRESS_GET_INPUT = 6
PACKAGE_PROGRESS_ADD_EO_IMAGES = 7
PACKAGE_PROGRESS_CONVERT_INPUT = 8
PACKAGE_PROGRESS_CWL_RUN = 10
PACKAGE_PROGRESS_CWL_DONE = 95
PACKAGE_PROGRESS_PREP_OUT = 98
PACKAGE_PROGRESS_DONE = 100


def get_status_location_log_path(status_location, out_dir=None):
    # type: (str, Optional[str]) -> str
    log_path = os.path.splitext(status_location)[0] + ".log"
    return os.path.join(out_dir, os.path.split(log_path)[-1]) if out_dir else log_path


def retrieve_package_job_log(execution, job, progress_min=0, progress_max=100):
    # type: (WPSExecution, Job, Number, Number) -> None
    """
    Obtains the underlying WPS execution log from the status file to add them after existing job log entries.
    """
    try:
        # weaver package log every status update into this file (we no longer rely on the http monitoring)
        out_dir = get_wps_output_dir(get_settings())
        # if the process is a weaver package this status xml should be available in the process output dir
        log_path = get_status_location_log_path(execution.statusLocation, out_dir=out_dir)
        with open(log_path, "r") as log_file:
            log_lines = log_file.readlines()
        if not log_lines:
            return
        total = float(len(log_lines))
        for i, line in enumerate(log_lines):
            progress = map_progress(i / total * 100, progress_min, progress_max)
            job.save_log(message=line.rstrip("\n"), progress=progress, status=STATUS_RUNNING)
    except (KeyError, IOError):
        LOGGER.warning("Failed retrieving package log for %s", job)


def get_process_location(process_id_or_url, data_source=None):
    # type: (Union[Dict[str, Any], str], Optional[str]) -> str
    """
    Obtains the URL of a WPS REST DescribeProcess given the specified information.

    :param process_id_or_url: process "identifier" or literal URL to DescribeProcess WPS-REST location.
    :param data_source: identifier of the data source to map to specific ADES, or map to localhost if ``None``.
    :return: URL of EMS or ADES WPS-REST DescribeProcess.
    """
    # if an URL was specified, return it as is
    if urlparse(process_id_or_url).scheme != "":
        return process_id_or_url
    data_source_url = retrieve_data_source_url(data_source)
    process_id = get_sane_name(process_id_or_url)
    process_url = process_service.path.format(process_id=process_id)
    return "{host}{path}".format(host=data_source_url, path=process_url)


def get_package_workflow_steps(package_dict_or_url):
    # type: (Union[Dict[str, Any], str]) -> List[Dict[str, str]]
    """
    Obtain references to intermediate steps of a CWL workflow.

    :param package_dict_or_url: process package definition or literal URL to DescribeProcess WPS-REST location.
    :return: list of workflow steps as {"name": <name>, "reference": <reference>}
        where `name` is the generic package step name, and `reference` is the id/url of a registered WPS package.
    """
    if isinstance(package_dict_or_url, str):
        package_dict_or_url = _get_process_package(package_dict_or_url)
    workflow_steps_ids = list()
    package_type = _get_package_type(package_dict_or_url)
    if package_type == PROCESS_WORKFLOW:
        workflow_steps = package_dict_or_url.get("steps")
        for step in workflow_steps:
            step_package_ref = workflow_steps[step].get("run")
            # if a local file reference was specified, convert it to process id
            package_ref_name, package_ref_ext = os.path.splitext(step_package_ref)
            if urlparse(step_package_ref).scheme == "" and package_ref_ext.replace(".", "") in PACKAGE_EXTENSIONS:
                step_package_ref = package_ref_name
            workflow_steps_ids.append({"name": step, "reference": step_package_ref})
    return workflow_steps_ids


def _fetch_process_info(process_info_url, fetch_error):
    # type: (str, Type[Exception]) -> JSON
    """
    Fetches the JSON process information from the specified URL and validates that it contains something.

    :raises fetch_error: provided exception with URL message if the process information could not be retrieved.
    """
    def _info_not_found_error():
        return fetch_error("Could not find reference: '{!s}'".format(process_info_url))

    if not isinstance(process_info_url, str):
        raise _info_not_found_error()
    resp = request_extra("get", process_info_url, headers={"Accept": CONTENT_TYPE_APP_JSON}, settings=get_settings())
    if resp.status_code != HTTPOk.code:
        raise _info_not_found_error()
    body = resp.json()
    if not isinstance(body, dict) or not len(body):
        raise _info_not_found_error()
    return body


def _get_process_package(process_url):
    # type: (str) -> Tuple[CWL, str]
    """
    Retrieves the WPS process package content from given process ID or literal URL.

    :param process_url: process literal URL to DescribeProcess WPS-REST location.
    :return: tuple of package body as dictionary and package reference name.
    """
    package_url = "{!s}/package".format(process_url)
    package_body = _fetch_process_info(package_url, PackageNotFound)
    package_name = process_url.split("/")[-1]
    return package_body, package_name


def _get_process_payload(process_url):
    # type: (str) -> JSON
    """
    Retrieves the WPS process payload content from given process ID or literal URL.

    :param process_url: process literal URL to DescribeProcess WPS-REST location.
    :return: payload body as dictionary.
    """
    process_url = get_process_location(process_url)
    payload_url = "{!s}/payload".format(process_url)
    payload_body = _fetch_process_info(payload_url, PayloadNotFound)
    return payload_body


def _get_package_type(package_dict):
    # type: (CWL) -> Union[PROCESS_APPLICATION, PROCESS_WORKFLOW]
    return PROCESS_WORKFLOW if package_dict.get("class").lower() == "workflow" else PROCESS_APPLICATION


def _get_package_requirements_as_class_list(requirements):
    # type: (AnyCWLRequirements) -> ListCWLRequirements
    """
    Converts `CWL` package ``requirements`` or ``hints`` into list representation.

    Uniformization `CWL` requirements into the list representation, whether the input definitions where
    provided using the dictionary definition as ``{"<req-class>": {<params>}}`` or
    the list of dictionary requirements ``[{<req-class+params>}]`` each with a ``class`` key.
    """
    if isinstance(requirements, dict):
        reqs = []
        for req in requirements:
            reqs.append({"class": req})
            reqs[-1].update(requirements[req] or {})
        return reqs
    return [dict(req) for req in requirements]  # ensure list-of-dict instead of sequence of dict-like


def _get_package_ordered_io(io_section, order_hints=None):
    # type: (Union[List[JSON], Dict[str, Union[JSON, str]]], Optional[List[JSON]]) -> List[JSON]
    """
    Reorders and converts `CWL` I/O from any representation and considering specified ordering hints.

    First, converts `CWL` package I/O definitions defined as dictionary to an equivalent :class:`list` representation,
    in order to work only with a single representation method. The :class:`list` is chosen over :class:`dict` because
    sequences can enforce a specific order, while mapping have no particular order. The list representation ensures
    that I/O order is preserved when written to file and reloaded afterwards regardless of each server and/or library's
    implementation of the mapping container.

    If this function fails to correctly order any I/O or cannot correctly guarantee such result because of the provided
    parameters (e.g.: no hints given when required), the result will not break nor change the final processing behaviour
    of the `CWL` engine. This is merely *cosmetic* adjustments to ease readability of I/O to avoid always shuffling
    their order across multiple :term:`Application Package` reporting.

    The important result of this function is to provide the `CWL` I/O as a consistent list of objects so it is less
    cumbersome to compare/merge/iterate over the elements with all functions that will follow.

    .. note::
        When defined as a dictionary, an :class:`OrderedDict` is expected as input to ensure preserved field order.
        Prior to Python 3.7 or CPython 3.5, preserved order is not guaranteed for *builtin* :class:`dict`.
        In this case the :paramref:`order_hints` is required to ensure same order.

    :param io_section: Definition contained under the `CWL` ``inputs`` or ``outputs`` package fields.
    :param order_hints: Optional/partial list of WPS I/O definitions hinting an order to sort CWL unsorted-dict I/O.
    :returns: I/O specified as list of dictionary definitions with preserved order (as best as possible).
    """
    if isinstance(io_section, list):
        return io_section
    io_list = []
    io_dict = OrderedDict()
    if isinstance(io_section, dict) and not isinstance(io_section, OrderedDict) and order_hints and len(order_hints):
        # pre-order I/O that can be resolved with hint when the specified I/O section is not ordered
        io_section = deepcopy(io_section)
        for hint in order_hints:
            hint_id = get_field(hint, "identifier", search_variations=True)
            if hint_id in io_section:
                io_dict[hint_id] = io_section.pop(hint_id)
        for hint in io_section:
            io_dict[hint] = io_section[hint]
    else:
        io_dict = io_section
    for io_id, io_value in io_dict.items():
        # I/O value can be a literal type string or dictionary with more details at this point
        # make it always detailed dictionary to avoid problems for later parsing
        # this is also required to make the list, since all list items must have a matching type
        if isinstance(io_value, str):
            io_list.append({"type": io_value})
        else:
            io_list.append(io_value)
        io_list[-1]["id"] = io_id
    return io_list


def _check_package_file(cwl_file_path_or_url):
    # type: (str) -> Tuple[str, bool]
    """
    Validates that the specified CWL file path or URL points to an existing and allowed file format.

    :param cwl_file_path_or_url: one of allowed file types path on disk, or an URL pointing to one served somewhere.
    :return: absolute_path, is_url: absolute path or URL, and boolean indicating if it is a remote URL file.
    :raises PackageRegistrationError: in case of missing file, invalid format or invalid HTTP status code.
    """
    is_url = False
    cwl_file_path_or_url = cwl_file_path_or_url.replace("file://", "")
    scheme = urlparse(cwl_file_path_or_url).scheme
    if scheme != "" and not posixpath.ismount("{}:".format(scheme)):    # windows partition
        is_url = True
    if is_url:
        cwl_path = cwl_file_path_or_url
        cwl_resp = request_extra("head", cwl_path, settings=get_settings())
        is_url = True
        if cwl_resp.status_code != HTTPOk.code:
            raise PackageRegistrationError("Cannot find CWL file at: '{}'.".format(cwl_path))
    else:
        cwl_path = os.path.abspath(cwl_file_path_or_url)
        if not os.path.isfile(cwl_path):
            raise PackageRegistrationError("Cannot find CWL file at: '{}'.".format(cwl_path))

    file_ext = os.path.splitext(cwl_path)[-1].replace(".", "")
    if file_ext not in PACKAGE_EXTENSIONS:
        raise PackageRegistrationError("Not a valid CWL file type: '{}'.".format(file_ext))
    return cwl_path, is_url


def _load_package_file(file_path):
    # type: (str) -> CWL
    """
    Loads the package in YAML/JSON format specified by the file path.
    """

    file_path, is_url = _check_package_file(file_path)
    # if URL, get the content and validate it by loading, otherwise load file directly
    # yaml properly loads json as well, error can print out the parsing error location
    try:
        if is_url:
            settings = get_settings()
            cwl_resp = request_extra("get", file_path, headers={"Accept": CONTENT_TYPE_TEXT_PLAIN}, settings=settings)
            return yaml.safe_load(cwl_resp.content)
        with open(file_path, "r") as f:
            return yaml.safe_load(f)
    except ScannerError as ex:
        raise PackageRegistrationError("Package parsing generated an error: [{!s}]".format(ex))


def _load_package_content(package_dict,                             # type: Dict
                          package_name=PACKAGE_DEFAULT_FILE_NAME,   # type: str
                          data_source=None,                         # type: Optional[str]
                          only_dump_file=False,                     # type: bool
                          tmp_dir=None,                             # type: Optional[str]
                          loading_context=None,                     # type: Optional[LoadingContext]
                          runtime_context=None,                     # type: Optional[RuntimeContext]
                          process_offering=None,                    # type: Optional[JSON]
                          ):  # type: (...) -> Optional[Tuple[CWLFactoryCallable, str, Dict[str, str]]]
    """
    Loads `CWL` package definition using various contextual resources.

    Following operations are accomplished to validate the package:

    - Starts by resolving any intermediate sub-packages steps if the parent package is a `Workflow` (CWL class),
      in order to recursively generate and validate their process and package, potentially using remote reference.
      Each of those operations are applied to every step.
    - Package I/O are reordered using any reference process offering hints if provided to generate consistent results.
    - The resulting package definition is dumped to a temporary JSON file, to validate the content can be serialized.
    - Optionally, the `CWL` factory is employed to create the application runner, validating any provided loading and
      runtime contexts, and considering all Workflow steps if applicable, or the single application otherwise.

    :param package_dict: package content representation as a json dictionary.
    :param package_name: name to use to create the package file.
    :param data_source: identifier of the data source to map to specific ADES, or map to localhost if ``None``.
    :param only_dump_file: specify if the ``CWLFactoryCallable`` should be validated and returned.
    :param tmp_dir: location of the temporary directory to dump files (deleted on exit).
    :param loading_context: cwltool context used to create the cwl package (required if ``only_dump_file=False``)
    :param runtime_context: cwltool context used to execute the cwl package (required if ``only_dump_file=False``)
    :param process_offering: JSON body of the process description payload (used as I/O hint ordering)
    :returns:
        If ``only_dump_file`` is ``True``: ``None``.
        Otherwise, tuple of:
        - instance of ``CWLFactoryCallable``
        - package type (``PROCESS_WORKFLOW`` or ``PROCESS_APPLICATION``)
        - mapping of each step ID with their package name that must be run

    .. warning::
        Specified :paramref:`tmp_dir` will be deleted on exit.
    """

    tmp_dir = tmp_dir or tempfile.mkdtemp()
    tmp_json_cwl = os.path.join(tmp_dir, package_name)

    # for workflows, retrieve each 'sub-package' file
    package_type = _get_package_type(package_dict)
    workflow_steps = get_package_workflow_steps(package_dict)
    step_packages = {}
    for step in workflow_steps:
        # generate sub-package file and update workflow step to point to it
        step_process_url = get_process_location(step["reference"], data_source)
        package_body, package_name = _get_process_package(step_process_url)
        _load_package_content(package_body, package_name, tmp_dir=tmp_dir,
                              data_source=data_source, only_dump_file=True)
        package_dict["steps"][step["name"]]["run"] = package_name
        step_packages[step["name"]] = package_name

    # fix I/O to preserve ordering from dump/load, and normalize them to consistent list of objects
    process_offering_hint = process_offering or {}
    package_input_hint = process_offering_hint.get("inputs", [])
    package_output_hint = process_offering_hint.get("outputs", [])
    package_dict["inputs"] = _get_package_ordered_io(package_dict["inputs"], order_hints=package_input_hint)
    package_dict["outputs"] = _get_package_ordered_io(package_dict["outputs"], order_hints=package_output_hint)

    with open(tmp_json_cwl, "w") as f:
        json.dump(package_dict, f)
    if only_dump_file:
        return

    factory = CWLFactory(loading_context=loading_context, runtime_context=runtime_context)
    package = factory.make(tmp_json_cwl)  # type: CWLFactoryCallable
    shutil.rmtree(tmp_dir)
    return package, package_type, step_packages


def _merge_package_inputs_outputs(wps_inputs_list,      # type: List[ANY_IO_Type]
                                  cwl_inputs_list,      # type: List[WPS_Input_Type]
                                  wps_outputs_list,     # type: List[ANY_IO_Type]
                                  cwl_outputs_list,     # type: List[WPS_Output_Type]
                                  ):                    # type: (...) -> Tuple[List[JSON_IO_Type], List[JSON_IO_Type]]
    """
    Merges corresponding metadata of I/O definitions from `CWL` and `WPS` sources.

    Merges I/O definitions to use for process creation and returned by ``GetCapabilities``, ``DescribeProcess``
    using the `WPS` specifications (from request ``POST``) and `CWL` specifications (extracted from file).

    .. note::
        Parameters ``cwl_inputs_list`` and ``cwl_outputs_list`` are expected to be in `WPS`-like format
        (ie: `CWL` I/O converted to corresponding `WPS` I/O).
    """
    wps_inputs_merged = merge_package_io(wps_inputs_list, cwl_inputs_list, WPS_INPUT)
    wps_outputs_merged = merge_package_io(wps_outputs_list, cwl_outputs_list, WPS_OUTPUT)
    return [wps2json_io(i) for i in wps_inputs_merged], [wps2json_io(o) for o in wps_outputs_merged]


def _get_package_io(package_factory, io_select, as_json):
    # type: (CWLFactoryCallable, str, bool) -> List[PKG_IO_Type]
    """
    Retrieves I/O definitions from a validated :class:`CWLFactoryCallable`.

    .. seealso::
        Factory can be obtained with validation using :func:`_load_package_content`.

    :param package_factory: `CWL` factory that contains I/O references to the package definition.
    :param io_select: either :data:`WPS_INPUT` or :data:`WPS_OUTPUT` according to what needs to be processed.
    :param as_json: toggle to specific the desired output type.
    :returns: I/O format depends on value :paramref:`as_json`.
        If ``True``, converts the I/O definitions into `JSON` representation.
        If ``False``, converts the I/O definitions into `WPS` objects.
    """
    if io_select == WPS_OUTPUT:
        io_attrib = "outputs_record_schema"
    elif io_select == WPS_INPUT:
        io_attrib = "inputs_record_schema"
    else:
        raise PackageTypeError("Unknown I/O selection: '{}'.".format(io_select))
    cwl_package_io = getattr(package_factory.t, io_attrib)
    wps_package_io = [cwl2wps_io(io_item, io_select) for io_item in cwl_package_io["fields"]]
    if as_json:
        return [wps2json_io(io) for io in wps_package_io]
    return wps_package_io


def _get_package_inputs_outputs(package_factory,    # type: CWLFactoryCallable
                                as_json=False,      # type: bool
                                ):                  # type: (...) -> Tuple[List[PKG_IO_Type], List[PKG_IO_Type]]
    """
    Generates `WPS-like` ``(inputs, outputs)`` tuple using parsed CWL package definitions.
    """
    return (_get_package_io(package_factory, io_select=WPS_INPUT, as_json=as_json),
            _get_package_io(package_factory, io_select=WPS_OUTPUT, as_json=as_json))


def _update_package_metadata(wps_package_metadata, cwl_package_package):
    # type: (JSON, CWL) -> None
    """
    Updates the package `WPS` metadata dictionary from extractable `CWL` package definition.
    """
    wps_package_metadata["title"] = wps_package_metadata.get("title", cwl_package_package.get("label", ""))
    wps_package_metadata["abstract"] = wps_package_metadata.get("abstract", cwl_package_package.get("doc", ""))

    if (
        "$schemas" in cwl_package_package
        and isinstance(cwl_package_package["$schemas"], list)
        and "$namespaces" in cwl_package_package
        and isinstance(cwl_package_package["$namespaces"], dict)
    ):
        metadata = wps_package_metadata.get("metadata", [])
        namespaces_inv = {v: k for k, v in cwl_package_package["$namespaces"]}
        for schema in cwl_package_package["$schemas"]:
            for namespace_url in namespaces_inv:
                if schema.startswith(namespace_url):
                    metadata.append({"title": namespaces_inv[namespace_url], "href": schema})
        wps_package_metadata["metadata"] = metadata

    if "s:keywords" in cwl_package_package and isinstance(cwl_package_package["s:keywords"], list):
        wps_package_metadata["keywords"] = list(
            set(wps_package_metadata.get("keywords", [])) | set(cwl_package_package.get("s:keywords", []))
        )


def _generate_process_with_cwl_from_reference(reference):
    # type: (str) -> Tuple[CWL, JSON]
    """
    Resolves the ``reference`` type (`CWL`, `WPS-1`, `WPS-2`, `WPS-3`) and generates a `CWL` ``package`` from it.

    Additionally provides minimal process details retrieved from the ``reference``.
    The number of details obtained from the process will depend on available parameters from its description as well
    as the number of metadata that can be mapped between it and the generated `CWL` package.
    """
    cwl_package = None
    process_info = dict()

    # match against direct CWL reference
    reference_path, reference_ext = os.path.splitext(reference)
    reference_name = os.path.split(reference_path)[-1]
    if reference_ext.replace(".", "") in PACKAGE_EXTENSIONS:
        cwl_package = _load_package_file(reference)
        process_info = {"identifier": reference_name}

    # match against WPS-1/2 reference
    else:
        settings = get_settings()
        response = request_extra("GET", reference, retries=3, settings=settings)
        if response.status_code != HTTPOk.code:
            raise HTTPServiceUnavailable("Couldn't obtain a valid response from [{}]. Service response: [{} {}]"
                                         .format(reference, response.status_code, response.reason))
        content_type = get_header("Content-Type", response.headers)
        if any(ct in content_type for ct in CONTENT_TYPE_ANY_XML):
            # attempt to retrieve a WPS-1 ProcessDescription definition
            cwl_package, process_info = xml_wps2cwl(response, settings)

        elif any(ct in content_type for ct in [CONTENT_TYPE_APP_JSON]):
            payload = response.json()
            # attempt to retrieve a WPS-3 Process definition, owsContext is expected in body
            if "process" in payload:
                process_info = payload["process"]
                ows_ref = process_info.get("owsContext", {}).get("offering", {}).get("content", {}).get("href")
                cwl_package = _load_package_file(ows_ref)
            # if somehow the CWL was referenced without an extension, handle it here
            # also handle parsed WPS-3 process description also with a reference
            elif "cwlVersion" in payload:
                cwl_package = _load_package_file(reference)
                process_info = {"identifier": reference_name}

    return cwl_package, process_info


def get_application_requirement(package):
    # type: (CWL) -> Dict[str, Any]
    """
    Retrieve the principal requirement that allows mapping to the appropriate process implementation.

    Obtains the first item in `CWL` package ``requirements`` or ``hints`` that corresponds to a `Weaver`-specific
    application type as defined in :py:data:`CWL_REQUIREMENT_APP_TYPES`.

    :returns: dictionary that minimally has ``class`` field, and optionally other parameters from that requirement.
    """
    # package can define requirements and/or hints,
    # if it's an application, only one CWL_REQUIREMENT_APP_TYPES is allowed,
    # workflow can have multiple, but they are not explicitly handled
    reqs = package.get("requirements", {})
    hints = package.get("hints", {})
    all_hints = _get_package_requirements_as_class_list(reqs) + _get_package_requirements_as_class_list(hints)
    app_hints = list(filter(lambda h: any(h["class"].endswith(t) for t in CWL_REQUIREMENT_APP_TYPES), all_hints))
    if len(app_hints) > 1:
        raise ValueError("Package 'requirements' and/or 'hints' define too many conflicting values: {}, "
                         "only one permitted amongst {}.".format(list(app_hints), list(CWL_REQUIREMENT_APP_TYPES)))
    requirement = app_hints[0] if app_hints else {"class": ""}

    cwl_supported_reqs = [item for item in CWL_REQUIREMENT_APP_TYPES] + [CWL_REQUIREMENT_INIT_WORKDIR]
    if not all(item.get("class") in cwl_supported_reqs for item in all_hints):
        raise PackageTypeError("Invalid requirement, the requirements supported are {0}".format(cwl_supported_reqs))

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
    :returns: reason message if must be executed remotely or ``None`` if it *could* be executed locally.
    """
    if _get_package_type(package) == PROCESS_WORKFLOW:
        return "CWL package defines a [{}] process that uses remote step-processes.".format(PROCESS_WORKFLOW)
    requirement = get_application_requirement(package)
    req_class = requirement["class"]
    req_local = [CWL_REQUIREMENT_APP_BUILTIN, CWL_REQUIREMENT_APP_DOCKER]
    req_remote = [CWL_REQUIREMENT_APP_ESGF_CWT, CWL_REQUIREMENT_APP_WPS1]
    if req_class in req_local:
        return None
    if req_class in req_remote:
        return "CWL package hint/requirement [{}] requires a remote provider.".format(req_class)
    # other undefined hint/requirement for remote execution (aka: ADES dispatched WPS-3/REST/OGC-API)
    remote = all(req in req_class for req in ["provider", "process"])
    if remote:
        return "CWL package hint/requirement [{}] defines a remote provider entry.".format(req_class)
    return None


def get_process_definition(process_offering, reference=None, package=None, data_source=None):
    # type: (JSON, Optional[str], Optional[CWL], Optional[str]) -> JSON
    """
    Resolve the process definition considering corresponding metadata from the offering, package and references.

    Returns an updated process definition dictionary ready for storage using provided `WPS` ``process_offering``
    and a package definition passed by ``reference`` or ``package`` `CWL` content.
    The returned process information can be used later on to load an instance of :class:`weaver.wps_package.WpsPackage`.

    :param process_offering: `WPS REST-API` (`WPS-3`) process offering as `JSON`.
    :param reference: URL to `CWL` package definition, `WPS-1 DescribeProcess` endpoint or `WPS-3 Process` endpoint.
    :param package: literal `CWL` package definition (`YAML` or `JSON` format).
    :param data_source: where to resolve process IDs (default: localhost if ``None``).
    :return: updated process definition with resolved/merged information from ``package``/``reference``.
    """

    def try_or_raise_package_error(call, reason):
        try:
            LOGGER.debug("Attempting: [%s].", reason)
            return call()
        except Exception as exc:
            # re-raise any exception already handled by a "package" error as is, but with a more detailed message
            # handle any other sub-exception that wasn't processed by a "package" error as a registration error
            package_errors = (PackageRegistrationError, PackageTypeError, PackageRegistrationError, PackageNotFound)
            exc_type = type(exc) if isinstance(exc, package_errors) else PackageRegistrationError
            exc_msg = str(exc)
            LOGGER.exception(exc_msg)
            raise exc_type("Invalid package/reference definition. {0} generated error: [{1!r}].".format(reason, exc))

    if not (isinstance(package, dict) or isinstance(reference, str)):
        raise PackageRegistrationError("Invalid parameters amongst one of [package, reference].")
    if package and reference:
        raise PackageRegistrationError("Simultaneous parameters [package, reference] not allowed.")

    process_info = process_offering
    if reference:
        package, process_info = _generate_process_with_cwl_from_reference(reference)
        process_info.update(process_offering)   # override upstream details
    if not isinstance(package, dict):
        raise PackageRegistrationError("Cannot decode process package contents.")
    if "class" not in package:
        raise PackageRegistrationError("Cannot obtain process type from package class.")

    LOGGER.debug("Using data source: '%s'", data_source)
    package_factory, process_type, _ = try_or_raise_package_error(
        lambda: _load_package_content(package, data_source=data_source, process_offering=process_info),
        reason="Loading package content")

    package_inputs, package_outputs = try_or_raise_package_error(
        lambda: _get_package_inputs_outputs(package_factory),
        reason="Definition of package/process inputs/outputs")
    process_inputs = process_info.get("inputs", list())
    process_outputs = process_info.get("outputs", list())

    try_or_raise_package_error(
        lambda: _update_package_metadata(process_info, package),
        reason="Metadata update")

    package_inputs, package_outputs = try_or_raise_package_error(
        lambda: _merge_package_inputs_outputs(process_inputs, package_inputs, process_outputs, package_outputs),
        reason="Merging of inputs/outputs")

    try_or_raise_package_error(lambda: get_application_requirement(package), reason="Validate requirements and hints")

    # obtain any retrieved process id if not already provided from upstream process offering, and clean it
    process_id = get_sane_name(get_any_id(process_info), assert_invalid=False)
    if not process_id:
        raise PackageRegistrationError("Could not retrieve any process identifier.")

    process_offering.update({
        "identifier": process_id,
        "package": package,
        "type": process_type,
        "inputs": package_inputs,
        "outputs": package_outputs
    })
    return process_offering


class WpsPackage(Process):
    # defined on __init__ call
    package = None                  # type: Optional[CWL]
    # defined only after/while _handler is called (or sub-methods)
    package_id = None               # type: Optional[str]
    package_type = None             # type: Optional[str]
    package_log_hook_stderr = None  # type: Optional[str]
    package_log_hook_stdout = None  # type: Optional[str]
    percent = None                  # type: Optional[Number]
    remote_execution = None         # type: Optional[bool]
    log_file = None                 # type: Optional[str]
    log_level = None                # type: Optional[int]
    logger = None                   # type: Optional[logging.Logger]
    step_packages = None            # type: Optional[Dict[str, str]]
    step_launched = None            # type: Optional[List[str]]
    request = None                  # type: Optional[WPSRequest]
    response = None                 # type: Optional[ExecuteResponse]
    _job = None                     # type: Optional[Job]

    def __init__(self, **kw):
        """
        Creates a `WPS-3 Process` instance to execute a `CWL` application package definition.

        Process parameters should be loaded from an existing :class:`weaver.datatype.Process`
        instance generated using :func:`weaver.wps_package.get_process_definition`.

        Provided ``kw`` should correspond to :meth:`weaver.datatype.Process.params_wps`
        """
        self.payload = kw.pop("payload")
        self.package = kw.pop("package")
        self.settings = get_settings()
        if not self.package:
            raise PackageRegistrationError("Missing required package definition for package process.")
        if not isinstance(self.package, dict):
            raise PackageRegistrationError("Unknown parsing of package definition for package process.")

        inputs = kw.pop("inputs", [])

        # handle EOImage inputs
        inputs = opensearch.replace_inputs_describe_process(inputs=inputs, payload=self.payload)

        inputs = [json2wps_io(i, WPS_INPUT) for i in inputs]
        outputs = [json2wps_io(o, WPS_OUTPUT) for o in kw.pop("outputs", list())]
        metadata = [json2wps_field(meta_kw, "metadata") for meta_kw in kw.pop("metadata", list())]

        super(WpsPackage, self).__init__(
            self._handler,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            store_supported=True,
            status_supported=True,
            **kw
        )

    def setup_loggers(self, log_stdout_stderr=True):
        # type: (bool) -> None
        """
        Configures useful loggers to catch most of the common output and/or error messages during package execution.

        .. seealso::
            :meth:`insert_package_log`
            :func:`retrieve_package_job_log`
        """
        setup_loggers(self.settings)
        self.log_level = self.log_level or logging.getLogger("weaver").getEffectiveLevel()

        # file logger for output
        self.log_file = get_status_location_log_path(self.status_location)
        log_file_handler = logging.FileHandler(self.log_file)
        log_file_formatter = logging.Formatter(fmt=get_log_fmt(), datefmt=get_log_date_fmt())
        log_file_formatter.converter = time.gmtime
        log_file_handler.setFormatter(log_file_formatter)

        # prepare package logger
        self.logger = logging.getLogger("{}|{}".format(LOGGER.name, self.package_id))
        self.logger.addHandler(log_file_handler)
        self.logger.setLevel(self.log_level)

        # add CWL job and CWL runner logging to current package logger
        job_logger = logging.getLogger("job {}".format(PACKAGE_DEFAULT_FILE_NAME))
        job_logger.addHandler(log_file_handler)
        job_logger.setLevel(self.log_level)
        cwl_logger = logging.getLogger("cwltool")
        cwl_logger.addHandler(log_file_handler)
        cwl_logger.setLevel(self.log_level)

        # add stderr/stdout CWL hook to capture logs/prints/echos from subprocess execution
        # using same file so all kind of message are kept in chronological order of generation
        if log_stdout_stderr:
            self.package_log_hook_stderr = PACKAGE_OUTPUT_HOOK_LOG_UUID.format(str(uuid.uuid4()))
            self.package_log_hook_stdout = PACKAGE_OUTPUT_HOOK_LOG_UUID.format(str(uuid.uuid4()))
            package_outputs = self.package.get("outputs")
            if isinstance(package_outputs, list):
                package_outputs.extend([{"id": self.package_log_hook_stderr, "type": "stderr"},
                                        {"id": self.package_log_hook_stdout, "type": "stdout"}])
            else:
                package_outputs.update({self.package_log_hook_stderr: {"type": "stderr"},
                                        self.package_log_hook_stdout: {"type": "stdout"}})
            self.package.update({"stderr": "stderr.log", "stdout": "stdout.log"})

        # add weaver Tweens logger to current package logger
        weaver_tweens_logger = logging.getLogger("weaver.tweens")
        weaver_tweens_logger.addHandler(log_file_handler)
        weaver_tweens_logger.setLevel(self.log_level)

    def insert_package_log(self, result):
        # type: (Union[CWLResults, CWLException]) -> List[str]
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
        status = STATUS_RUNNING
        try:
            if isinstance(result, CWLException):
                result = getattr(result, "out")
                status = STATUS_FAILED
            stderr_file = result.get(self.package_log_hook_stderr, {}).get("location", "").replace("file://", "")
            stdout_file = result.get(self.package_log_hook_stdout, {}).get("location", "").replace("file://", "")
            with_stderr_file = os.path.isfile(stderr_file)
            with_stdout_file = os.path.isfile(stdout_file)
            if not with_stdout_file and not with_stderr_file:
                self.log_message(status, "Could not retrieve any internal application log.", level=logging.WARNING)
                return captured_log
            out_log = []
            if with_stdout_file:
                with open(stdout_file) as app_log_fd:
                    out_log = app_log_fd.readlines()
                    if out_log:
                        out_log = ["----- Captured Log (stdout) -----\n"] + out_log
            err_log = []
            if with_stderr_file:
                with open(stderr_file) as app_log_fd:
                    err_log = app_log_fd.readlines()
                    if err_log:
                        err_log = ["----- Captured Log (stderr) -----\n"] + err_log
            if not out_log and not err_log:
                self.log_message(status, "Nothing captured from internal application logs.", level=logging.INFO)
                return captured_log
            with open(self.log_file, "r") as pkg_log_fd:
                pkg_log = pkg_log_fd.readlines()
            cwl_end_index = -1
            cwl_end_search = "[cwltool] [job {}] completed".format(self.package_id)  # success/permanentFail
            for i in reversed(range(len(pkg_log))):
                if cwl_end_search in pkg_log[i]:
                    cwl_end_index = i
                    break
            captured_log = out_log + err_log
            merged_log = pkg_log[:cwl_end_index] + captured_log + pkg_log[cwl_end_index:]
            with open(self.log_file, "w") as pkg_log_fd:
                pkg_log_fd.writelines(merged_log)
        except Exception as exc:
            # log exception, but non-failing
            self.exception_message(PackageExecutionError, exception=exc, level=logging.WARNING, status=status,
                                   message="Error occurred when retrieving internal application log.")
        return captured_log

    def update_requirements(self):
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
                # remove output directory since we must explicitly defined it to match with WPS
                for req_rm in ["dockerFile", "dockerOutputDirectory"]:
                    is_rm = req_def.pop(req_rm, None)
                    if is_rm:
                        self.logger.warning("Removed CWL [%s.%s] %s parameter from [%s] package definition (forced).",
                                            req_cls, req_rm, req_type[:-1], self.package_id)

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
                req_env = {"class": "EnvVarRequirement", "envDef": {}}
                for req in req_items:
                    if req["class"] == "EnvVarRequirement":
                        req_env = req
                        break
                req_items.append(req_env)
            else:
                # definition as mapping
                req_items.setdefault("EnvVarRequirement", {"envDef": {}})
                req_env = req_items.get("EnvVarRequirement")
            active_python_path = os.path.join(sys.exec_prefix, "bin")
            env_path = "{}:{}".format(active_python_path, os.getenv("PATH"))
            req_env["envDef"].update({"PATH": env_path})
            if self.package.get("baseCommand") == "python":
                self.package["baseCommand"] = os.path.join(active_python_path, "python")

    def update_effective_user(self):
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
            self.logger.info("Enforcing CWL euid:egid [%s,%s]", cfg_euid, cfg_egid)
            cwltool.docker.docker_vm_id = lambda *_, **__: (int(cfg_euid), int(cfg_egid))
        else:
            self.logger.log(logging.WARNING if (app_euid == "0" or app_egid == "0") else logging.INFO,
                            "Visible application CWL euid:egid [%s:%s]", app_euid, app_egid)

    def update_status(self, message, progress, status):
        # type: (str, Number, AnyStatusType) -> None
        """
        Updates the `PyWPS` real job status from a specified parameters.
        """
        self.percent = progress or self.percent or 0

        # find the enum PyWPS status matching the given one as string
        pywps_status = map_status(status, STATUS_COMPLIANT_PYWPS)
        pywps_status_id = STATUS_PYWPS_IDS[pywps_status]

        # NOTE:
        #   When running process in sync (because executed within celery worker already async),
        #   pywps reverts status file output flag. Re-enforce it for our needs.
        #   (see: 'weaver.wps.WorkerService.execute_job')
        self.response.store_status_file = True

        # pywps overrides 'status' by 'accepted' in 'update_status', so use the '_update_status' to enforce the status
        # using protected method also avoids weird overrides of progress percent on failure and final 'success' status
        self.response._update_status(pywps_status_id, message, self.percent)  # noqa: W0212
        self.log_message(status=status, message=message, progress=progress)

    def step_update_status(self, message, progress, start_step_progress, end_step_progress, step_name,
                           target_host, status):
        # type: (str, Number, Number, Number, str, AnyValue, str) -> None
        self.update_status(
            message="{0} [{1}] - {2}".format(target_host, step_name, str(message).strip()),
            progress=map_progress(progress, start_step_progress, end_step_progress),
            status=status,
        )

    def log_message(self, status, message, progress=None, level=logging.INFO):
        # type: (AnyStatusType, str, Optional[Number], int) -> None
        progress = progress if progress is not None else self.percent
        message = get_job_log_msg(status=map_status(status), message=message, progress=progress)
        self.logger.log(level, message, exc_info=level > logging.INFO)

    def exception_message(self, exception_type, exception=None, message="no message",
                          status=STATUS_EXCEPTION, level=logging.ERROR):
        # type: (Type[Exception], Optional[Exception], str, AnyStatusType, int) -> Exception
        """
        Logs to the job the specified error message with the provided exception type.

        :returns: formatted exception with message to be raised by calling function.
        """
        exception_msg = " [{}]".format(repr(exception)) if isinstance(exception, Exception) else ""
        self.log_message(status=status, level=level,
                         message="{0}: {1}{2}".format(exception_type.__name__, message, exception_msg))
        return exception_type("{0}{1}".format(message, exception_msg))

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

    def _handler(self, request, response):
        # type: (WPSRequest, ExecuteResponse) -> ExecuteResponse
        """
        Method called when process receives the WPS execution request.
        """

        # note: only 'LOGGER' call allowed here, since 'setup_loggers' not called yet
        LOGGER.debug("HOME=%s, Current Dir=%s", os.environ.get("HOME"), os.path.abspath(os.curdir))
        self.request = request
        self.response = response
        self.package_id = self.request.identifier

        try:
            try:
                # workflows do not support stdout/stderr
                self.package_type = _get_package_type(self.package)
                log_stdout_stderr = self.package_type != PROCESS_WORKFLOW
                self.setup_loggers(log_stdout_stderr)
                self.update_status("Preparing package logs done.", PACKAGE_PROGRESS_PREP_LOG, STATUS_RUNNING)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed preparing package logging.")

            self.update_status("Launching package...", PACKAGE_PROGRESS_LAUNCHING, STATUS_RUNNING)

            # early validation to ensure proper instance is defined for target process/package
            # Note:
            #   This is only to ensure we stop execution in case some process was deployed somehow with mandatory
            #   remote execution, but cannot accomplish it due to mismatching configuration. This can occur if
            #   configuration was modified and followed by Weaver reboot with persisted WPS-remote process.
            config = get_weaver_configuration(self.settings)
            self.remote_execution = config in WEAVER_CONFIGURATIONS_REMOTE
            problem_needs_remote = check_package_instance_compatible(self.package)
            if not self.remote_execution:
                if problem_needs_remote:
                    raise self.exception_message(
                        PackageExecutionError,
                        message="Weaver instance is configured as [{}] but remote execution with one of {} is "
                                "required for process [{}] because {}. Aborting execution.".format(
                                    config, list(WEAVER_CONFIGURATIONS_REMOTE), self.package_id, problem_needs_remote
                                )
                    )
            # switch back to local execution if hybrid execution can handle this package by itself (eg: Docker, builtin)
            elif config == WEAVER_CONFIGURATION_HYBRID:
                self.remote_execution = problem_needs_remote is not None

            if self.remote_execution:
                # EMS/Hybrid dispatch the execution to ADES or remote WPS
                loading_context = LoadingContext()
                loading_context.construct_tool_object = self.make_tool
            else:
                # ADES/Hybrid execute the CWL/AppPackage locally
                loading_context = None

            self.update_effective_user()
            self.update_requirements()

            # note:
            #   Parameter 'weaver.wps_workdir' is the base-dir where sub-dir per application packages will be generated.
            #   Parameter 'self.workdir' is the actual location PyWPS reserved for this process (already with sub-dir).
            #   If no 'weaver.wps_workdir' was provided, reuse PyWps parent workdir since we got access to it.
            #   Other steps handling outputs need to consider that CWL<->WPS out dirs could match because of this.
            wps_workdir = self.settings.get("weaver.wps_workdir", os.path.dirname(self.workdir))
            # cwltool will add additional unique characters after prefix paths
            cwl_workdir = os.path.join(wps_workdir, "cwltool_tmp_")
            cwl_outdir = os.path.join(wps_workdir, "cwltool_out_")
            runtime_params = {
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
                "debug": self.logger.isEnabledFor(logging.DEBUG)
            }
            self.logger.debug("Using cwltool.RuntimeContext args:\n%s", json.dumps(runtime_params, indent=2))
            runtime_context = RuntimeContext(kwargs=runtime_params)
            try:
                package_inst, _, self.step_packages = _load_package_content(self.package,
                                                                            package_name=self.package_id,
                                                                            # no data source for local package
                                                                            data_source=None,
                                                                            loading_context=loading_context,
                                                                            runtime_context=runtime_context)
                self.step_launched = []

            except Exception as ex:
                raise PackageRegistrationError("Exception occurred on package instantiation: '{!r}'".format(ex))
            self.update_status("Loading package content done.", PACKAGE_PROGRESS_LOADING, STATUS_RUNNING)

            try:
                cwl_inputs_info = {i["name"]: i for i in package_inst.t.inputs_record_schema["fields"]}
                self.update_status("Retrieve package inputs done.", PACKAGE_PROGRESS_GET_INPUT, STATUS_RUNNING)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed retrieving package input types.")
            try:
                # identify EOImages from payload
                request.inputs = opensearch.get_original_collection_id(self.payload, request.inputs)
                eoimage_data_sources = opensearch.get_eo_images_data_sources(self.payload, request.inputs)
                if eoimage_data_sources:
                    self.update_status("Found EOImage data-source definitions. "
                                       "Updating inputs with OpenSearch sources.",
                                       PACKAGE_PROGRESS_ADD_EO_IMAGES, STATUS_RUNNING)
                    accept_mime_types = opensearch.get_eo_images_mime_types(self.payload)
                    opensearch.insert_max_occurs(self.payload, request.inputs)
                    request.inputs = opensearch.query_eo_images_from_wps_inputs(request.inputs,
                                                                                eoimage_data_sources,
                                                                                accept_mime_types,
                                                                                settings=self.settings)
                cwl_inputs = self.make_inputs(request.inputs, cwl_inputs_info)
                self.update_status("Convert package inputs done.", PACKAGE_PROGRESS_CONVERT_INPUT, STATUS_RUNNING)
            except PackageException as exc:
                raise self.exception_message(type(exc), None, str(exc))  # re-raise as is, but with extra log entry
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed to load package inputs.")

            try:
                self.update_status("Running package...", PACKAGE_PROGRESS_CWL_RUN, STATUS_RUNNING)
                self.logger.debug("Launching process package with inputs:\n%s", json.dumps(cwl_inputs, indent=2))
                result = package_inst(**cwl_inputs)  # type: CWLResults
                self.update_status("Package execution done.", PACKAGE_PROGRESS_CWL_DONE, STATUS_RUNNING)
            except Exception as exc:
                if isinstance(exc, CWLException):
                    lines = self.insert_package_log(exc)
                    LOGGER.debug("Captured logs:\n%s", "\n".join(lines))
                raise self.exception_message(PackageExecutionError, exc, "Failed package execution.")
            # FIXME: this won't be necessary using async routine (https://github.com/crim-ca/weaver/issues/131)
            self.insert_package_log(result)
            try:
                self.make_outputs(result)
                self.update_status("Generate package outputs done.", PACKAGE_PROGRESS_PREP_OUT, STATUS_RUNNING)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed to save package outputs.")
        except Exception:
            # return log file location by status message since outputs are not obtained by WPS failed process
            log_url = "{}/{}.log".format(get_wps_output_url(self.settings), self.uuid)
            error_msg = "Package completed with errors. Server logs: [{}], Available at [{}]:".format(
                self.log_file, log_url
            )
            self.update_status(error_msg, self.percent, STATUS_FAILED)
            raise
        else:
            self.update_status("Package complete.", PACKAGE_PROGRESS_DONE, STATUS_SUCCEEDED)
        return self.response

    def must_fetch(self, input_ref):
        # type: (str) -> bool
        """
        Figures out if file reference should be fetched immediately for local execution.

        If anything else than local script/docker, remote ADES/WPS process will fetch it.
        S3 are handled here to avoid error on remote WPS not supporting it.

        .. seealso::
            - :ref:`File Reference Types`
        """
        if self.remote_execution or self.package_type == PROCESS_WORKFLOW:
            return False
        app_req = get_application_requirement(self.package)
        if app_req["class"] not in [CWL_REQUIREMENT_APP_BUILTIN, CWL_REQUIREMENT_APP_DOCKER]:
            if input_ref.startswith("s3://"):
                return True
            return False
        return not os.path.isfile(input_ref)

    def make_inputs(self,
                    wps_inputs,         # type: Dict[str, Deque[WPS_Input_Type]]
                    cwl_inputs_info,    # type: Dict[str, CWL_Input_Type]
                    ):                  # type: (...) -> Dict[str, ValueType]
        """
        Converts WPS input values to corresponding CWL input values for processing by CWL package instance.

        The WPS inputs must correspond to :mod:`pywps` definitions.
        Multiple values are adapted to arrays as needed.
        WPS ``Complex`` types (files) are converted to appropriate locations based on data or reference specification.

        :param wps_inputs: actual WPS inputs parsed from execution request
        :param cwl_inputs_info: expected CWL input definitions for mapping
        :return: CWL input values
        """
        cwl_inputs = dict()
        for input_id in wps_inputs:
            # skip empty inputs (if that is even possible...)
            input_occurs = wps_inputs[input_id]
            if len(input_occurs) <= 0:
                continue
            # process single occurrences
            input_i = input_occurs[0]
            # handle as reference/data
            is_array, elem_type, _, _ = is_cwl_array_type(cwl_inputs_info[input_id])
            if isinstance(input_i, ComplexInput) or elem_type == "File":
                # extend array data that allow max_occur > 1
                # drop invalid inputs returned as None
                if is_array:
                    input_href = [self.make_location_input(elem_type, input_def) for input_def in input_occurs]
                    input_href = [cwl_input for cwl_input in input_href if cwl_input is not None]
                else:
                    input_href = self.make_location_input(elem_type, input_i)
                if input_href:
                    cwl_inputs[input_id] = input_href
            elif isinstance(input_i, (LiteralInput, BoundingBoxInput)):
                # extend array data that allow max_occur > 1
                if is_array:
                    input_data = [i.url if i.as_reference else i.data for i in input_occurs]
                else:
                    input_data = input_i.url if input_i.as_reference else input_i.data
                cwl_inputs[input_id] = input_data
            else:
                raise PackageTypeError("Undefined package input for execution: {}.".format(type(input_i)))
        return cwl_inputs

    def make_location_input(self, input_type, input_definition):
        # type: (str, ComplexInput) -> Optional[JSON]
        """
        Generates the JSON content required to specify a `CWL` ``File`` input definition from a location.

        If the input reference corresponds to an HTTP URL that is detected as matching the local WPS output endpoint,
        implicitly convert the reference to the local WPS output directory to avoid useless download of available file.
        Since that endpoint could be protected though, perform a minimal HEAD request to validate its accessibility.
        Otherwise, this operation could incorrectly grant unauthorized access to protected files by forging the URL.

        If the process requires ``OpenSearch`` references that should be preserved as is, scheme defined by
        :py:data:`weaver.processes.constants.OPENSEARCH_LOCAL_FILE_SCHEME` prefix instead of ``http(s)://`` is expected.

        Any other variant of file reference will be fetched as applicable by the relevant schemes.

        .. seealso::
            Documentation details of resolution based on schemes defined in :ref:`file_reference_types` section.
        """
        # NOTE:
        #   When running as EMS, must not call data/file methods if URL reference, otherwise contents
        #   get fetched automatically by PyWPS objects.
        input_location = None
        # cannot rely only on 'as_reference' as often it is not provided by the request although it's an href
        if input_definition.as_reference:
            input_location = input_definition.url
        # FIXME: PyWPS bug
        #   Calling 'file' method fetches it, and it is always called by the package itself
        #   during type validation if the MODE is anything else than disabled.
        #   MODE.SIMPLE is needed minimally to check MIME-TYPE of input against supported formats.
        #       - https://github.com/geopython/pywps/issues/526
        #       - https://github.com/crim-ca/weaver/issues/91
        #   since href is already handled (pulled and staged locally), use it directly to avoid double fetch with CWL
        #   validate using the internal '_file' instead of 'file' otherwise we trigger the fetch
        #   normally, file should be pulled an this check should fail
        input_definition_file = input_definition._iohandler._file  # noqa: W0212
        if input_definition_file and os.path.isfile(input_definition_file):
            input_location = input_definition_file
        # if source type is data, we actually need to call 'data' (without fetch of remote file, already fetched)
        # value of 'file' in this case points to a local file path where the wanted link was dumped as raw data
        if input_definition.source_type == SOURCE_TYPE.DATA:
            input_location = input_definition.data
        if not input_location:
            url = getattr(input_definition, "url")
            if isinstance(url, str) and any(url.startswith("{}://".format(p)) for p in SUPPORTED_FILE_SCHEMES):
                input_location = url
            else:
                # last option, could not resolve 'lazily' so will fetch data if needed
                input_location = input_definition.data
        # FIXME: PyWPS bug (https://github.com/geopython/pywps/issues/633)
        #   Optional File inputs receive 'data' content that correspond to 'default format' definition if not provided.
        #   This is invalid since input is not provided, it should not be there at all (default format != default data).
        #   Patch with a combination of available detection methods to be safe:
        #   - The 'file' attribute gets resolved to the process '{workdir}/input' temporary file.
        #     This 'file' is instead named 'input_{uuid}' when it is actually resolved to real input href/data contents.
        #     The IO handler better reports 'None' in its internal '_file' attribute.
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
            self.logger.debug("File input (%s) DROPPED. Detected default format as data.", input_definition.identifier)
            return None

        # auto-map local if possible after security check
        input_local_ref = map_wps_output_location(input_location, self.settings)
        if input_local_ref:
            resp = request_extra("HEAD", input_location, settings=self.settings)
            if resp.status_code == 200:  # if failed, following fetch will produce the appropriate HTTP error
                self.logger.debug("Detected and validated remotely accessible reference [%s] "
                                  "matching local WPS outputs [%s]. Skipping fetch using direct reference.",
                                  input_location, input_local_ref)
                input_location = input_local_ref

        if self.must_fetch(input_location):
            self.logger.info("File input (%s) ATTEMPT fetch: [%s]", input_definition.identifier, input_location)
            input_location = fetch_file(input_location, input_definition.workdir, settings=self.settings)
        else:
            self.logger.info("File input (%s) SKIPPED fetch: [%s]", input_definition.identifier, input_location)

        location = {"location": input_location, "class": input_type}
        if input_definition.data_format is not None and input_definition.data_format.mime_type:
            fmt = get_cwl_file_format(input_definition.data_format.mime_type, make_reference=True)
            if fmt is not None:
                location["format"] = fmt
        return location

    def make_outputs(self, cwl_result):
        # type: (CWLResults) -> None
        """
        Maps `CWL` result outputs to corresponding `WPS` outputs.
        """
        for output_id in self.request.outputs:  # iterate over original WPS outputs, extra such as logs are dropped
            # TODO: adjust output for glob patterns (https://github.com/crim-ca/weaver/issues/24)
            if isinstance(cwl_result[output_id], list) and not isinstance(self.response.outputs[output_id], list):
                if len(cwl_result[output_id]) > 1:
                    self.logger.warning(
                        "Dropping additional output values (%s total), only 1 supported per identifier.",
                        len(cwl_result[output_id])
                    )
                # provide more details than poorly descriptive IndexError
                if not len(cwl_result[output_id]):
                    raise PackageExecutionError(
                        "Process output '{}' expects at least one value but none was found. "
                        "Possible incorrect glob pattern definition in CWL Application Package.".format(output_id)
                    )
                cwl_result[output_id] = cwl_result[output_id][0]  # expect only one output

            if "location" not in cwl_result[output_id] and os.path.isfile(str(cwl_result[output_id])):
                raise PackageTypeError("Process output '{}' defines CWL type other than 'File'. ".format(output_id) +
                                       "Application output results must use 'File' type to return file references.")
            if "location" in cwl_result[output_id]:
                self.make_location_output(cwl_result, output_id)
                continue

            # data output
            self.response.outputs[output_id].data = cwl_result[output_id]
            self.response.outputs[output_id].as_reference = False
            self.logger.info("Resolved WPS output [%s] as literal data", output_id)

    def make_location_output(self, cwl_result, output_id):
        # type: (CWLResults, str) -> None
        """
        Rewrite the `WPS` output with required location using result path from `CWL` execution.

        Configures the parameters such that `PyWPS` will either auto-resolve the local paths to match with URL
        defined by ``weaver.wps_output_url`` or upload it to `S3` bucket from ``weaver.wps_output_s3_bucket`` and
        provide reference directly.

        .. seealso::
            - :func:`weaver.wps.load_pywps_config`
        """
        s3_bucket = self.settings.get("weaver.wps_output_s3_bucket")
        result_loc = cwl_result[output_id]["location"].replace("file://", "")
        result_path = os.path.split(result_loc)[-1]

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
        if s3_bucket:
            # when 'url' is directly enforced, 'ComplexOutput.json' will use it instead of 'file' from temp workdir
            # override builder only here so that only results are uploaded to S3, and not XML status
            # using this storage builder, other settings (bucket, region, etc.) are retrieved from PyWPS server config
            self.response.outputs[output_id]._storage = S3StorageBuilder().build()  # noqa: W0212
            self.response.outputs[output_id].storage.prefix = str(self.response.uuid)  # job UUID
        elif self.job.context:
            storage = FileStorageBuilder().build()
            storage.target = os.path.join(storage.target, self.job.context)
            storage.output_url = os.path.join(storage.output_url, self.job.context)
            os.makedirs(storage.target, exist_ok=True)  # pywps handles UUID-dir creation, but not nested context-dir
            self.response.outputs[output_id]._storage = storage  # noqa: W0212

        # pywps will resolve file paths for us using its WPS request UUID
        os.makedirs(self.workdir, exist_ok=True)
        result_wps = os.path.join(self.workdir, result_path)

        if os.path.realpath(result_loc) != os.path.realpath(result_wps):
            self.logger.info("Moving [%s]: [%s] -> [%s]", output_id, result_loc, result_wps)
            shutil.move(result_loc, result_wps)
        # params 'as_reference + file' triggers 'ComplexOutput.json' to map the WPS-output URL from the WPS workdir
        self.response.outputs[output_id].as_reference = True
        self.response.outputs[output_id].file = result_wps

        self.logger.info("Resolved WPS output [%s] as file reference: [%s]", output_id, result_wps)

    def make_tool(self, toolpath_object, loading_context):
        # type: (ToolPathObjectType, LoadingContext) -> ProcessCWL
        from weaver.processes.wps_workflow import default_make_tool
        return default_make_tool(toolpath_object, loading_context, self.get_job_process_definition)

    def get_job_process_definition(self, jobname, joborder, tool):  # noqa: E811
        # type: (str, JSON, CWL) -> WpsPackage
        """
        Obtain the execution job definition for the given process.

        This function is called before running an `ADES` job (either from a workflow step or a simple `EMS` dispatch).
        It must return a :class:`weaver.processes.wps_process.WpsProcess` instance configured with the proper ``CWL``
        package definition, ADES target and cookies to access it (if protected).

        :param jobname: The workflow step or the package id that must be launched on an ADES :class:`string`
        :param joborder: The params for the job :class:`dict {input_name: input_value}`
                         input_value is one of `input_object` or `array [input_object]`
                         input_object is one of `string` or `dict {class: File, location: string}`
                         in our case input are expected to be File object
        :param tool: Whole `CWL` config including hints requirement
                     (see: :py:data:`weaver.processes.constants.CWL_REQUIREMENT_APP_TYPES`)
        """

        if jobname == self.package_id:
            # A step is the package itself only for non-workflow package being executed on the EMS
            # default action requires ADES dispatching but hints can indicate also WPS1 or ESGF-CWT provider
            step_payload = self.payload
            process = self.package_id
            jobtype = "package"
        else:
            # Here we got a step part of a workflow (self is the workflow package)
            step_payload = _get_process_payload(self.step_packages[jobname])
            process = self.step_packages[jobname]
            jobtype = "step"

        # Progress made with steps presumes that they are done sequentially and have the same progress weight
        start_step_progress = self.map_step_progress(len(self.step_launched), max(1, len(self.step_packages)))
        end_step_progress = self.map_step_progress(len(self.step_launched) + 1, max(1, len(self.step_packages)))

        self.step_launched.append(jobname)
        self.update_status("Preparing to launch {type} {name}.".format(type=jobtype, name=jobname),
                           start_step_progress, STATUS_RUNNING)

        def _update_status_dispatch(_provider, _message, _progress, _status):
            self.step_update_status(
                _message, _progress, start_step_progress, end_step_progress, jobname, _provider, _status
            )

        def _get_wps1_params(_requirement):
            _wps_params = {}
            required_params = ["provider", "process"]
            for _param in required_params:
                if _param not in _requirement:
                    raise ValueError("Missing requirement detail [{}]: {}".format(_requirement["class"], _param))
                _wps_params[_param] = _requirement[_param]
            return _wps_params

        requirement = get_application_requirement(self.package)
        req_class = requirement["class"]

        if req_class.endswith(CWL_REQUIREMENT_APP_WPS1):
            self.logger.info("WPS-1 Package resolved from requirement/hint: %s", req_class)
            from weaver.processes.wps1_process import Wps1Process
            params = _get_wps1_params(requirement)
            return Wps1Process(
                provider=params["provider"],
                process=params["process"],
                request=self.request,
                update_status=_update_status_dispatch,
            )
        elif req_class.endswith(CWL_REQUIREMENT_APP_ESGF_CWT):
            self.logger.info("ESGF-CWT Package resolved from requirement/hint: %s", req_class)
            from weaver.processes.esgf_process import ESGFProcess
            params = _get_wps1_params(requirement)
            return ESGFProcess(
                provider=params["provider"],
                process=params["process"],
                request=self.request,
                update_status=_update_status_dispatch,
            )
        else:
            # implements both `PROCESS_APPLICATION` with `CWL_REQUIREMENT_APP_DOCKER` and `PROCESS_WORKFLOW`
            self.logger.info("WPS-3 Package resolved from requirement/hint: %s", req_class)
            from weaver.processes.wps3_process import Wps3Process
            return Wps3Process(step_payload=step_payload,
                               joborder=joborder,
                               process=process,
                               request=self.request,
                               update_status=_update_status_dispatch)
