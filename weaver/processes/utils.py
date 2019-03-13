from weaver.config import get_weaver_configuration, WEAVER_CONFIGURATION_EMS
from weaver.datatype import Service, Process as ProcessDB
from weaver.database import get_db
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_PLAIN
from weaver.store.base import StoreProcesses
from weaver.utils import get_sane_name, get_settings, get_url_without_query
from weaver.processes import wps_package
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import wps_restapi_base_url
from weaver.exceptions import (
    InvalidIdentifierValue,
    ProcessRegistrationError,
    PackageRegistrationError,
    PackageTypeError,
    PackageNotFound,
)
from owslib.wps import ComplexData, is_reference
from owslib.wps import WebProcessingService
from pyramid.httpexceptions import (
    HTTPOk,
    HTTPNotFound,
    HTTPBadRequest,
    HTTPConflict,
    HTTPUnprocessableEntity,
    HTTPInternalServerError,
    HTTPException,
)
from copy import deepcopy
from distutils.version import LooseVersion
from six.moves.urllib.request import urlopen
from six.moves.urllib.parse import urlparse, parse_qs
from six.moves.urllib.error import URLError
from typing import TYPE_CHECKING
import colander
import warnings
import logging
import yaml
import json
import six
import os
if TYPE_CHECKING:
    from weaver.typedefs import JSON, AnyContainer, AnySettingsContainer, FileSystemPathType
    from typing import AnyStr, Dict, Union
    from pywps import Process as ProcessWPS
    import owslib.wps
LOGGER = logging.getLogger(__name__)


def _get_data(input_value):
    """
    Extract the data from the input value
    """
    # process output data are append into a list and
    # WPS standard v1.0.0 specify that Output data field has zero or one value
    if input_value.data:
        return input_value.data[0]
    else:
        return None


def _read_reference(input_value):
    """
    Read a WPS reference and return the content
    """
    try:
        return urlopen(input_value.reference).read()
    except URLError:
        # Don't raise exceptions coming from that.
        return None


def _get_json_multiple_inputs(input_value):
    """
    Since WPS standard does not allow to return multiple values for a single output,
    a lot of process actually return a json array containing references to these outputs.
    This function goal is to detect this particular format
    :return: An array of references if the input_value is effectively a json containing that,
             None otherwise
    """

    # Check for the json datatype and mimetype
    if input_value.dataType == "ComplexData" and input_value.mimeType == CONTENT_TYPE_APP_JSON:

        # If the json data is referenced read it's content
        if input_value.reference:
            json_data_str = _read_reference(input_value)
        # Else get the data directly
        else:
            json_data_str = _get_data(input_value)

        # Load the actual json dict
        json_data = json.loads(json_data_str)

        if isinstance(json_data, list):
            for data_value in json_data:
                if not is_reference(data_value):
                    return None
            return json_data
    return None


def jsonify_output(output, process_description):
    # type: (owslib.wps.Output, owslib.wps.Process) -> JSON
    """
    Utility method to jsonify an output element from a WPS1 process description.
    """

    if not output.dataType:
        for process_output in getattr(process_description, "processOutputs", []):
            if getattr(process_output, "identifier", '') == output.identifier:
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
        json_array = _get_json_multiple_inputs(output)
        if json_array and all(str(ref).startswith("http") for ref in json_array):
            json_output["data"] = json_array
    else:
        # WPS standard v1.0.0 specify that Output data field has Zero or one value
        json_output["data"] = output.data[0] if output.data else None

    if json_output["dataType"] == "ComplexData":
        json_output["mimeType"] = output.mimeType

    return json_output


def jsonify_value(value):
    # ComplexData type
    if isinstance(value, ComplexData):
        return {"mimeType": value.mimeType, 'encoding': value.encoding, 'schema': value.schema}
    # other type
    else:
        return value


def convert_process_wps_to_db(service, process, container):
    # type: (Union[Service, Dict[{"url": AnyStr, "name": AnyStr}]], ProcessWPS, AnySettingsContainer) -> ProcessDB
    """
    Converts an owslib WPS Process to local storage Process.
    """
    describe_process_url = "{base_url}/providers/{provider_id}/processes/{process_id}".format(
        base_url=wps_restapi_base_url(container),
        provider_id=service.get("name"),
        process_id=process.identifier)
    execute_process_url = "{describe_url}/jobs".format(describe_url=describe_process_url)

    default_format = {"mimeType": CONTENT_TYPE_TEXT_PLAIN}
    inputs = [dict(
        id=getattr(dataInput, "identifier", ""),
        title=getattr(dataInput, "title", ""),
        abstract=getattr(dataInput, "abstract", ""),
        minOccurs=str(getattr(dataInput, "minOccurs", 0)),  # FIXME: str applied to match OGC REST-API definition
        maxOccurs=str(getattr(dataInput, "maxOccurs", 0)),  # FIXME: str applied to match OGC REST-API definition
        dataType=dataInput.dataType,
        defaultValue=jsonify_value(getattr(dataInput, "defaultValue", None)),
        allowedValues=[jsonify_value(dataValue) for dataValue in getattr(dataInput, 'allowedValues', [])],
        supportedValues=[jsonify_value(dataValue) for dataValue in getattr(dataInput, "supportedValues", [])],
        formats=[jsonify_value(dataValue) for dataValue in getattr(dataInput, "supportedValues", [default_format])],
    ) for dataInput in getattr(process, "dataInputs", [])]

    outputs = [dict(
        id=getattr(processOutput, "identifier", ''),
        title=getattr(processOutput, "title", ''),
        abstract=getattr(processOutput, "abstract", ''),
        dataType=processOutput.dataType,
        defaultValue=jsonify_value(getattr(processOutput, "defaultValue", None)),
        formats=[jsonify_value(dataValue) for dataValue in getattr(processOutput, "supportedValues", [default_format])],
    ) for processOutput in getattr(process, "processOutputs", [])]

    return ProcessDB(
        id=process.identifier,
        label=getattr(process, "title", ''),
        title=getattr(process, "title", ''),
        abstract=getattr(process, "abstract", ""),
        inputs=inputs,
        outputs=outputs,
        url=describe_process_url,
        processEndpointWPS1=service.get("url"),
        processDescriptionURL=describe_process_url,
        executeEndpoint=execute_process_url,
        package=None,
    )


def deploy_process_from_payload(payload, container):
    # type: (JSON, AnyContainer) -> HTTPException
    """
    Adds a :class:`weaver.datatype.Process` instance to storage using the provided JSON ``payload`` matching
    :class:`weaver.wps_restapi.swagger_definitions.ProcessDescription`.

    :returns: HTTPOk if the process registration was successful
    :raises HTTPException: otherwise
    """
    # validate minimum field requirements
    try:
        sd.Deploy().deserialize(payload)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))
    except Exception as ex:
        raise HTTPInternalServerError("Unhandled error when parsing 'processDescription': [{}]".format(str(ex)))

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
    try:
        # data_source `None` forces workflow process to search locally for deployed step applications
        process_info = wps_package.get_process_definition(process_info, reference, package, data_source=None)
    except PackageNotFound as ex:
        # raised when a workflow sub-process is not found (not deployed locally)
        raise HTTPNotFound(detail=str(ex))
    except (PackageRegistrationError, PackageTypeError) as ex:
        raise HTTPUnprocessableEntity(detail=str(ex))
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except Exception as ex:
        raise HTTPBadRequest("Invalid package/reference definition. Loading generated error: [{!r}]".format(ex))

    # validate process type against weaver configuration
    settings = get_settings(container)
    process_type = process_info["type"]
    if process_type == PROCESS_WORKFLOW:
        weaver_config = get_weaver_configuration(settings)
        if weaver_config != WEAVER_CONFIGURATION_EMS:
            raise HTTPBadRequest("Invalid [{0}] package deployment on [{1}].".format(process_type, weaver_config))

    restapi_url = wps_restapi_base_url(settings)
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
    return HTTPOk(json=json_response)


def register_wps_provider_processes(wps_providers_file_path, container):
    # type: (FileSystemPathType, AnySettingsContainer) -> None
    """
    Loads a `wps_provider.yml` file and registers `WPS-1` providers processes to the
    current `Weaver` instance as equivalent `WPS-2` processes.

    .. seealso::
        - `weaver.wps_providers.yml.example`
    """
    if not os.path.isfile(wps_providers_file_path):
        warnings.warn("No file specified for WPS-1 providers registration.", RuntimeWarning)
        return
    try:
        with open(wps_providers_file_path, 'r') as f:
            providers_config = yaml.safe_load(f)
        providers = providers_config.get('providers')
        if not providers:
            LOGGER.warning("Nothing to process from file: [{}]".format(wps_providers_file_path))
            return

        from weaver.wps_restapi.processes.processes import list_remote_processes
        for cfg_service in providers:
            # parse info
            if isinstance(cfg_service, dict):
                svc_url = cfg_service["url"]
                svc_name = cfg_service.get("name")
                svc_proc = cfg_service.get("processes", [])
            elif isinstance(cfg_service, six.string_types):
                svc_url = cfg_service
                svc_name = None
                svc_proc = []
            else:
                raise ValueError("Invalid service value: [{!s}].".format(cfg_service))
            url_p = urlparse(svc_url)
            qs_p = parse_qs(url_p.query)
            svc_url = get_url_without_query(url_p)
            svc_name = svc_name or get_sane_name(url_p.hostname)
            svc_proc = svc_proc or qs_p.get("identifier", [])
            if not isinstance(svc_name, six.string_types):
                raise ValueError("Invalid service value: [{!s}].".format(svc_name))
            if not isinstance(svc_proc, list):
                raise ValueError("Invalid process value: [{!s}].".format(svc_proc))

            # fetch data
            LOGGER.info("Fetching WPS-1: [{}]".format(svc_url))
            wps = WebProcessingService(url=svc_url)
            if LooseVersion(wps.version) >= LooseVersion('2.0'):
                LOGGER.warning("Invalid WPS-1 provider, version was [{}]".format(wps.version))
                continue
            wps_processes = [wps.describeprocess(p) for p in svc_proc] or wps.processes
            for wps_process in wps_processes:
                proc_id = "{}_{}".format(svc_name, get_sane_name(wps_process.identifier))
                proc_url = "{}?service=WPS&request=DescribeProcess&identifier={}&version={}" \
                           .format(svc_url, wps_process.identifier, wps.version)
                payload = {
                    "processDescription": {"process": {"id": proc_id}},
                    "executionUnit": [{"href": proc_url}],
                    "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
                }
                try:
                    deploy_process_from_payload(payload, container)
                except HTTPConflict:
                    LOGGER.warning("Process already registered: [{}]".format(proc_id))
                    continue
                LOGGER.info("Process registered: []".format(proc_id))

    except Exception as exc:
        msg = "Invalid WPS-1 providers configuration file [{!r}].".format(exc)
        LOGGER.exception(msg)
        raise RuntimeError(msg)
