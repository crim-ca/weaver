import json
import logging
import os
import warnings
from copy import deepcopy
from distutils.version import LooseVersion
from typing import TYPE_CHECKING

import colander
import six
import yaml
from owslib.wps import WebProcessingService, is_reference
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPException,
    HTTPNotFound,
    HTTPOk,
    HTTPUnprocessableEntity
)
from pyramid.settings import asbool
from six.moves.urllib.error import URLError
from six.moves.urllib.parse import parse_qs, urlparse
from six.moves.urllib.request import urlopen

from weaver.config import (
    WEAVER_CONFIGURATION_EMS,
    WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
    get_weaver_config_file,
    get_weaver_configuration
)
from weaver.database import get_db
from weaver.datatype import Process as ProcessDB, Service
from weaver.exceptions import (
    InvalidIdentifierValue,
    PackageNotFound,
    PackageRegistrationError,
    PackageTypeError,
    ProcessNotFound,
    ProcessRegistrationError,
    ServiceNotFound,
    log_unhandled_exceptions
)
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_PLAIN
from weaver.processes.constants import WPS_COMPLEX_DATA
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW
from weaver.store.base import StoreProcesses, StoreServices
from weaver.utils import get_sane_name, get_settings, get_url_without_query
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.wps import get_wps_output_dir
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from weaver.typedefs import AnyContainer, AnySettingsContainer, FileSystemPathType, JSON, Number
    from typing import Any, AnyStr, List, Optional, Tuple, Union
    from pywps import Process as ProcessWPS
    import owslib.wps
LOGGER = logging.getLogger(__name__)


def _get_data(output):
    # type: (owslib.wps.Output) -> Optional[Any]
    """
    Extract the data from the output value.
    """
    # process output data are append into a list and
    # WPS standard v1.0.0 specify that Output data field has zero or one value
    if output.data:
        return output.data[0]
    return None


def _read_reference(url):
    # type: (AnyStr) -> Optional[AnyStr]
    """
    Read a reference HTTP(S) URL and return the content.
    """
    if not isinstance(url, six.string_types):
        return None
    if not url.lower().startswith("http"):
        LOGGER.warning("URL reading not allowed because of potentially insecure scheme: [%s]", url)
        return None
    try:
        return urlopen(url).read()  # nosec: B310
    except URLError:
        return None


def _get_multi_json_references(output, container):
    # type: (owslib.wps.Output, Optional[AnySettingsContainer]) -> Optional[List[JSON]]
    """
    Since WPS standard does not allow to return multiple values for a single output,
    a lot of process actually return a json array containing references to these outputs.

    Because the multi-output references are contained within this JSON file, it is not very convenient to retrieve
    the list of URLs as one always needs to open and read the file to get them. This function goal is to detect this
    particular format and expand the references to make them quickly available in the job output response.

    :return:
        Array of HTTP(S) references if the specified output is effectively a JSON containing that, ``None`` otherwise.
    """
    # Check for the json datatype and mime-type
    if output.dataType == WPS_COMPLEX_DATA and output.mimeType == CONTENT_TYPE_APP_JSON:
        try:
            # If the json data is referenced read it's content
            if output.reference:
                out_ref = output.reference
                if container:
                    if out_ref.startswith("file://"):
                        out_ref = out_ref[7:]
                    if out_ref.startswith("/"):
                        wps_out_dir = get_wps_output_dir(container)
                        out_ref = os.path.join(wps_out_dir, out_ref)
                    if not os.path.isfile(out_ref):
                        out_ref = output.reference
                json_data_str = _read_reference(out_ref)
            # Else get the data directly
            else:
                json_data_str = _get_data(output)

            # Load the actual json dict
            json_data = json.loads(json_data_str)
        except Exception:
            return None

        if isinstance(json_data, list):
            for data_value in json_data:
                if not is_reference(data_value):
                    return None
            return json_data
    return None


def map_progress(progress, range_min, range_max):
    # type: (Number, Number, Number) -> Number
    """Calculates the relative progression of the percentage process within min/max values."""
    return max(range_min, min(range_max, range_min + (progress * (range_max - range_min)) / 100))


def jsonify_output(output, process_description, container=None):
    # type: (owslib.wps.Output, owslib.wps.Process, Optional[AnySettingsContainer]) -> JSON
    """
    Utility method to jsonify an output element from a WPS1 process description.

    In the case that a reference JSON output is specified and that it refers to a file that contains an array list of
    URL references to simulate a multiple-output, this specific output gets expanded to contain both the original
    URL ``reference`` field and the loaded URL list under ``data`` field for easier access from the response body.
    """

    if not output.dataType:
        for process_output in getattr(process_description, "processOutputs", []):
            if getattr(process_output, "identifier", "") == output.identifier:
                output.dataType = process_output.dataType
                break

    json_output = dict(identifier=output.identifier,
                       title=output.title,
                       dataType=output.dataType)

    # WPS standard v1.0.0 specify that either a reference or a data field has to be provided
    if output.reference:
        json_output["reference"] = output.reference

        # Handle special case where we have a reference to a json array containing dataset reference
        # Avoid reference to reference by fetching directly the dataset references
        json_array = _get_multi_json_references(output, container)
        if json_array and all(str(ref).startswith("http") for ref in json_array):
            json_output["data"] = json_array
    else:
        # WPS standard v1.0.0 specify that Output data field has Zero or one value
        json_output["data"] = output.data[0] if output.data else None

    if json_output["dataType"] == WPS_COMPLEX_DATA:
        json_output["mimeType"] = output.mimeType

    return json_output


def convert_process_wps_to_db(service, process, container):
    # type: (Service, ProcessWPS, AnySettingsContainer) -> ProcessDB
    """
    Converts an owslib WPS Process to local storage Process.
    """
    from weaver.processes.wps_package import complex2json as jsonify_value

    describe_process_url = "{base_url}/providers/{provider_id}/processes/{process_id}".format(
        base_url=get_wps_restapi_base_url(container),
        provider_id=service.get("name"),
        process_id=process.identifier)
    execute_process_url = "{describe_url}/jobs".format(describe_url=describe_process_url)

    default_format = {"mimeType": CONTENT_TYPE_TEXT_PLAIN}
    inputs = [dict(
        id=getattr(dataInput, "identifier", ""),
        title=getattr(dataInput, "title", ""),
        abstract=getattr(dataInput, "abstract", ""),
        minOccurs=str(getattr(dataInput, "minOccurs", 0)),
        maxOccurs=str(getattr(dataInput, "maxOccurs", 0)),
        dataType=dataInput.dataType,
        defaultValue=jsonify_value(getattr(dataInput, "defaultValue", None)),
        allowedValues=[jsonify_value(dataValue) for dataValue in getattr(dataInput, "allowedValues", [])],
        supportedValues=[jsonify_value(dataValue) for dataValue in getattr(dataInput, "supportedValues", [])],
        formats=[jsonify_value(dataValue) for dataValue in getattr(dataInput, "supportedValues", [default_format])],
    ) for dataInput in getattr(process, "dataInputs", [])]

    outputs = [dict(
        id=getattr(processOutput, "identifier", ""),
        title=getattr(processOutput, "title", ""),
        abstract=getattr(processOutput, "abstract", ""),
        dataType=processOutput.dataType,
        defaultValue=jsonify_value(getattr(processOutput, "defaultValue", None)),
        formats=[jsonify_value(dataValue) for dataValue in getattr(processOutput, "supportedValues", [default_format])],
    ) for processOutput in getattr(process, "processOutputs", [])]

    return ProcessDB(
        id=process.identifier,
        label=getattr(process, "title", ""),
        title=getattr(process, "title", ""),
        abstract=getattr(process, "abstract", ""),
        inputs=inputs,
        outputs=outputs,
        url=describe_process_url,
        processEndpointWPS1=service.get("url"),
        processDescriptionURL=describe_process_url,
        executeEndpoint=execute_process_url,
        package=None,
    )


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of deploy payload.",
                          is_request=False)
def _check_deploy(payload):
    """Validate minimum deploy payload field requirements with exception handling."""
    try:
        sd.Deploy().deserialize(payload)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of process definition.",
                          is_request=False)
def _get_deploy_process_info(process_info, reference, package):
    """Obtain the process definition from deploy payload with exception handling."""
    from weaver.processes.wps_package import get_process_definition
    try:
        # data_source `None` forces workflow process to search locally for deployed step applications
        return get_process_definition(process_info, reference, package, data_source=None)
    except PackageNotFound as ex:
        # raised when a workflow sub-process is not found (not deployed locally)
        raise HTTPNotFound(detail=str(ex))
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except (PackageRegistrationError, PackageTypeError) as ex:
        msg = "Invalid package/reference definition. Loading generated error: [{!s}]".format(ex)
        LOGGER.exception(msg)
        raise HTTPUnprocessableEntity(detail=msg)


def deploy_process_from_payload(payload, container):
    # type: (JSON, AnyContainer) -> HTTPException
    """
    Adds a :class:`weaver.datatype.Process` instance to storage using the provided JSON ``payload`` matching
    :class:`weaver.wps_restapi.swagger_definitions.ProcessDescription`.

    :returns: HTTPOk if the process registration was successful
    :raises HTTPException: otherwise
    """
    _check_deploy(payload)

    # use deepcopy of to remove any circular dependencies before writing to mongodb or any updates to the payload
    payload_copy = deepcopy(payload)

    # validate identifier naming for unsupported characters
    process_description = payload.get("processDescription")
    process_info = process_description.get("process", {})
    process_href = process_description.pop("href", None)

    # retrieve CWL package definition, either via "href" (WPS-1/2), "owsContext" or "executionUnit" (package/reference)
    deployment_profile_name = payload.get("deploymentProfileName", "").lower()
    ows_context = process_info.pop("owsContext", None)
    reference = None
    package = None
    if process_href:
        reference = process_href  # reference type handled downstream
    elif isinstance(ows_context, dict):
        offering = ows_context.get("offering")
        if not isinstance(offering, dict):
            raise HTTPUnprocessableEntity("Invalid parameter 'processDescription.process.owsContext.offering'.")
        content = offering.get("content")
        if not isinstance(content, dict):
            raise HTTPUnprocessableEntity("Invalid parameter 'processDescription.process.owsContext.offering.content'.")
        package = None
        reference = content.get("href")
    elif deployment_profile_name:
        if not any(deployment_profile_name.endswith(typ) for typ in [PROCESS_APPLICATION, PROCESS_WORKFLOW]):
            raise HTTPBadRequest("Invalid value for parameter 'deploymentProfileName'.")
        execution_units = payload.get("executionUnit")
        if not isinstance(execution_units, list):
            raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")
        for execution_unit in execution_units:
            if not isinstance(execution_unit, dict):
                raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")
            package = execution_unit.get("unit")
            reference = execution_unit.get("href")
            # stop on first package/reference found, simultaneous usage will raise during package retrieval
            if package or reference:
                break
    else:
        raise HTTPBadRequest("Missing one of required parameters [href, owsContext, deploymentProfileName].")

    # obtain updated process information using WPS process offering, CWL/WPS reference or CWL package definition
    process_info = _get_deploy_process_info(process_info, reference, package)

    # validate process type against weaver configuration
    settings = get_settings(container)
    process_type = process_info["type"]
    if process_type == PROCESS_WORKFLOW:
        weaver_config = get_weaver_configuration(settings)
        if weaver_config != WEAVER_CONFIGURATION_EMS:
            raise HTTPBadRequest("Invalid [{0}] package deployment on [{1}].".format(process_type, weaver_config))

    restapi_url = get_wps_restapi_base_url(settings)
    description_url = "/".join([restapi_url, "processes", process_info["identifier"]])
    execute_endpoint = "/".join([description_url, "jobs"])

    # ensure that required "processEndpointWPS1" in db is added,
    # will be auto-fixed to localhost if not specified in body
    process_info["processEndpointWPS1"] = process_description.get("processEndpointWPS1")
    process_info["executeEndpoint"] = execute_endpoint
    process_info["payload"] = payload_copy
    process_info["jobControlOptions"] = process_description.get("jobControlOptions", [])
    process_info["outputTransmission"] = process_description.get("outputTransmission", [])
    process_info["processDescriptionURL"] = description_url
    # insert the "resolved" context using details retrieved from "executionUnit"/"href" or directly with "owsContext"
    if "owsContext" not in process_info and reference:
        process_info["owsContext"] = {"offering": {"content": {"href": str(reference)}}}
    elif isinstance(ows_context, dict):
        process_info["owsContext"] = ows_context

    try:
        store = get_db(container).get_store(StoreProcesses)
        saved_process = store.save_process(ProcessDB(process_info), overwrite=False)
    except ProcessRegistrationError as ex:
        raise HTTPConflict(detail=str(ex))
    except ValueError as ex:
        # raised on invalid process name
        raise HTTPBadRequest(detail=str(ex))

    json_response = {"processSummary": saved_process.process_summary(), "deploymentDone": True}
    return HTTPOk(json=json_response)   # FIXME: should be 201 (created), update swagger accordingly


def parse_wps_process_config(config_entry):
    # type: (Union[JSON, AnyStr]) -> Tuple[AnyStr, AnyStr, List[AnyStr], bool]
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
    elif isinstance(config_entry, six.string_types):
        svc_url = config_entry
        svc_name = None
        svc_proc = []
        svc_vis = False
    else:
        raise ValueError("Invalid service value: [{!s}].".format(config_entry))
    url_p = urlparse(svc_url)
    qs_p = parse_qs(url_p.query)
    svc_url = get_url_without_query(url_p)
    svc_name = svc_name or get_sane_name(url_p.hostname)
    svc_proc = svc_proc or qs_p.get("identifier", [])
    if not isinstance(svc_name, six.string_types):
        raise ValueError("Invalid service value: [{!s}].".format(svc_name))
    if not isinstance(svc_proc, list):
        raise ValueError("Invalid process value: [{!s}].".format(svc_proc))
    return svc_name, svc_url, svc_proc, svc_vis


def register_wps_processes_from_config(wps_processes_file_path, container):
    # type: (Optional[FileSystemPathType], AnySettingsContainer) -> None
    """
    Loads a `wps_processes.yml` file and registers `WPS-1` providers processes to the
    current `Weaver` instance as equivalent `WPS-2` processes.

    References listed under ``processes`` are registered.
    When the reference is a service (provider), registration of each WPS process is done individually
    for each of the specified providers with ID ``[service]_[process]`` per listed process by ``GetCapabilities``.

    .. versionchanged:: 1.14.0
        When references are specified using ``providers`` section instead of ``processes``, the registration
        only saves the remote WPS provider endpoint to dynamically populate WPS processes on demand.

    .. seealso::
        - `weaver.wps_processes.yml.example` for additional file format details
    """
    if wps_processes_file_path is None:
        warnings.warn("No file specified for WPS-1 providers registration.", RuntimeWarning)
        wps_processes_file_path = get_weaver_config_file("", WEAVER_DEFAULT_WPS_PROCESSES_CONFIG)
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
        with open(wps_processes_file_path, "r") as f:
            processes_config = yaml.safe_load(f)
        processes = processes_config.get("processes") or []
        providers = processes_config.get("providers") or []
        if not processes and not providers:
            LOGGER.warning("Nothing to process from file: [%s]", wps_processes_file_path)
            return

        db = get_db(container)
        process_store = db.get_store(StoreProcesses)
        service_store = db.get_store(StoreServices)

        # either 'service' references to register every underlying 'process' individually
        # or explicit 'process' references to register by themselves
        for cfg_service in processes:
            svc_name, svc_url, svc_proc, svc_vis = parse_wps_process_config(cfg_service)

            # fetch data
            LOGGER.info("Fetching WPS-1: [%s]", svc_url)
            wps = WebProcessingService(url=svc_url)
            if LooseVersion(wps.version) >= LooseVersion("2.0"):
                LOGGER.warning("Invalid WPS-1 provider, version was [%s]", wps.version)
                continue
            wps_processes = [wps.describeprocess(p) for p in svc_proc] or wps.processes
            for wps_process in wps_processes:
                proc_id = "{}_{}".format(svc_name, get_sane_name(wps_process.identifier))
                try:
                    process_store.fetch_by_id(proc_id)
                except ProcessNotFound:
                    pass
                else:
                    LOGGER.warning("Process already registered: [%s]. Skipping...", proc_id)
                    continue
                proc_url = "{}?service=WPS&request=DescribeProcess&identifier={}&version={}" \
                           .format(svc_url, wps_process.identifier, wps.version)
                svc_vis = VISIBILITY_PUBLIC if svc_vis else VISIBILITY_PRIVATE
                payload = {
                    "processDescription": {"process": {"id": proc_id, "visibility": svc_vis}},
                    "executionUnit": [{"href": proc_url}],
                    "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
                }
                try:
                    resp = deploy_process_from_payload(payload, container)
                    if resp.status_code == HTTPOk.code:
                        LOGGER.info("Process registered: [%s]", proc_id)
                    else:
                        raise RuntimeError("Process registration failed: [{}]".format(proc_id))
                except Exception as ex:
                    LOGGER.exception("Exception during process registration: [%r]. Skipping...", ex)
                    continue

        # direct WPS providers to register
        for cfg_service in providers:
            svc_name, svc_url, _, svc_vis = parse_wps_process_config(cfg_service)
            LOGGER.info("Register WPS-1 provider: [%s]", svc_url)
            WebProcessingService(url=svc_url)  # only attempt fetch to validate it exists
            try:
                service_store.fetch_by_name(svc_name)
            except ServiceNotFound:
                pass
            else:
                LOGGER.warning("Provider already registered: [%s]. Skipping...", svc_name)
                continue
            try:
                service_store.save_service(Service(name=svc_name, url=svc_url, public=svc_vis))
            except Exception as ex:
                LOGGER.exception("Exception during provider registration: [%r]. Skipping...", ex)
                continue

        LOGGER.info("Finished processing configuration file [%s].", wps_processes_file_path)
    except Exception as exc:
        msg = "Invalid WPS-1 providers configuration file [{!r}].".format(exc)
        LOGGER.exception(msg)
        raise RuntimeError(msg)
