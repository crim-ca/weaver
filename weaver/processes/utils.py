import logging
import warnings
from copy import deepcopy
from distutils.version import LooseVersion
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import colander
import yaml
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPCreated,
    HTTPException,
    HTTPForbidden,
    HTTPNotFound,
    HTTPOk,
    HTTPUnprocessableEntity
)
from pyramid.settings import asbool

from weaver.config import (
    WEAVER_CONFIGURATION_EMS,
    WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
    get_weaver_config_file,
    get_weaver_configuration
)
from weaver.database import get_db
from weaver.datatype import Process, Service
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
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW
from weaver.store.base import StoreProcesses, StoreServices
from weaver.utils import get_sane_name, get_settings, get_url_without_query
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.wps.utils import get_wps_client
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import List, Optional, Tuple, Union

    from pyramid.request import Request

    from weaver.typedefs import AnyContainer, AnySettingsContainer, FileSystemPathType, JSON, Number, SettingsType


# FIXME:
#   https://github.com/crim-ca/weaver/issues/215
#   define common Exception classes that won't require this type of conversion
def get_process(process_id=None, request=None, settings=None, store=None):
    # type: (Optional[str], Optional[Request], Optional[SettingsType], Optional[StoreProcesses]) -> Process
    """
    Obtain the specified process and validate information, returning appropriate HTTP error if invalid.

    Process identifier must be provided from either the request path definition or literal ID.
    Database must be retrievable from either the request, underlying settings, or direct store reference.

    Different parameter combinations are intended to be used as needed or more appropriate, such that redundant
    operations can be reduced where some objects are already fetched from previous operations.
    """
    if process_id is None and request is not None:
        process_id = request.matchdict.get("process_id")
    if store is None:
        store = get_db(settings or request).get_store(StoreProcesses)
    try:
        process = store.fetch_by_id(process_id, visibility=VISIBILITY_PUBLIC)
        return process
    except (InvalidIdentifierValue, MissingIdentifierValue) as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPForbidden("Process with ID '{!s}' is not accessible.".format(process_id))
    except ProcessNotFound:
        raise HTTPNotFound("Process with ID '{!s}' does not exist.".format(process_id))
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema:\n[{0!r}].".format(ex))


def get_job_submission_response(body):
    # type: (JSON) -> HTTPCreated
    """
    Generates the successful response from contents returned by job submission process.

    .. seealso::
        :func:`weaver.processes.execution.submit_job`
    """
    return HTTPCreated(location=body["location"], json=body)


def map_progress(progress, range_min, range_max):
    # type: (Number, Number, Number) -> Number
    """Calculates the relative progression of the percentage process within min/max values."""
    return max(range_min, min(range_max, range_min + (progress * (range_max - range_min)) / 100))


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of deploy payload.",
                          is_request=False)
def _check_deploy(payload):
    """Validate minimum deploy payload field requirements with exception handling."""
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    try:
        sd.Deploy().deserialize(payload)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of process definition.",
                          is_request=False)
def _get_deploy_process_info(process_info, reference, package):
    """
    Obtain the process definition from deploy payload with exception handling.

    .. seealso::
        - :func:`weaver.processes.wps_package.get_process_definition`
    """
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


def deploy_process_from_payload(payload, container, overwrite=False):
    # type: (JSON, AnyContainer, bool) -> HTTPException
    """
    Adds a :class:`weaver.datatype.Process` instance to storage using the provided JSON ``payload`` matching
    :class:`weaver.wps_restapi.swagger_definitions.ProcessDescription`.

    :param payload: JSON payload that was specified during the process deployment request.
    :param container: container to retrieve application settings.
    :param overwrite: whether to allow override of an existing process definition if conflict occurs.
    :returns: HTTPOk if the process registration was successful.
    :raises HTTPException: for any invalid process deployment step.
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
    # bw-compat abstract/description (see: ProcessDeployment schema)
    if "description" not in process_info or not process_info["description"]:
        process_info["description"] = process_info.get("abstract", "")

    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    try:
        store = get_db(container).get_store(StoreProcesses)
        process = Process(process_info)
        sd.ProcessSummary().deserialize(process)  # make if fail before save if invalid
        store.save_process(process, overwrite=False)
        process_summary = process.summary()
    except ProcessRegistrationError as ex:
        raise HTTPConflict(detail=str(ex))
    except (ValueError, colander.Invalid) as ex:
        # raised on invalid process name
        raise HTTPBadRequest(detail=str(ex))

    json_response = {"processSummary": process_summary, "deploymentDone": True}
    return HTTPCreated(json=json_response)


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
        raise ValueError("Invalid service value: [{!s}].".format(config_entry))
    url_p = urlparse(svc_url)
    qs_p = parse_qs(url_p.query)
    svc_url = get_url_without_query(url_p)
    svc_name = svc_name or get_sane_name(url_p.hostname)
    svc_proc = svc_proc or qs_p.get("identifier", [])  # noqa
    if not isinstance(svc_name, str):
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

    .. versionadded:: 1.14.0
        When references are specified using ``providers`` section instead of ``processes``, the registration
        only saves the remote WPS provider endpoint to dynamically populate WPS processes on demand.

    .. seealso::
        - `weaver.wps_processes.yml.example` for additional file format details
    """
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
        with open(wps_processes_file_path, "r") as f:
            processes_config = yaml.safe_load(f)
        processes = processes_config.get("processes") or []
        providers = processes_config.get("providers") or []
        if not processes and not providers:
            LOGGER.warning("Nothing to process from file: [%s]", wps_processes_file_path)
            return

        db = get_db(container)
        process_store = db.get_store(StoreProcesses)    # type: StoreProcesses
        service_store = db.get_store(StoreServices)     # type: StoreServices

        # either 'service' references to register every underlying 'process' individually
        # or explicit 'process' references to register by themselves
        for cfg_service in processes:
            svc_name, svc_url, svc_proc, svc_vis = parse_wps_process_config(cfg_service)

            # fetch data
            LOGGER.info("Fetching WPS-1: [%s]", svc_url)
            wps = get_wps_client(svc_url, container)
            if LooseVersion(wps.version) >= LooseVersion("2.0"):
                LOGGER.warning("Invalid WPS-1 provider, version was [%s]", wps.version)
                continue
            wps_processes = [wps.describeprocess(p) for p in svc_proc] or wps.processes
            for wps_process in wps_processes:
                proc_id = "{}_{}".format(svc_name, get_sane_name(wps_process.identifier))
                proc_url = "{}?service=WPS&request=DescribeProcess&identifier={}&version={}" \
                           .format(svc_url, wps_process.identifier, wps.version)
                svc_vis = VISIBILITY_PUBLIC if svc_vis else VISIBILITY_PRIVATE
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
                        raise RuntimeError("Process registration failed: [{}]".format(proc_id))
                except Exception as ex:
                    LOGGER.exception("Exception during process registration: [%r]. Skipping...", ex)
                    continue

        # direct WPS providers to register
        for cfg_service in providers:
            svc_name, svc_url, _, svc_vis = parse_wps_process_config(cfg_service)
            LOGGER.info("Register WPS-1/2 provider: [%s]", svc_url)
            try:
                get_wps_client(svc_url, container)  # only attempt fetch to validate it exists
            except Exception as ex:
                LOGGER.exception("Exception during provider validation: [%s] [%r]. Skipping...", svc_name, ex)
                continue
            new_service = Service(name=svc_name, url=svc_url, public=svc_vis)
            try:
                old_service = service_store.fetch_by_name(svc_name)
            except ServiceNotFound:
                LOGGER.info("Registering new provider: [%s]...", svc_name)
            else:
                if new_service == old_service:
                    LOGGER.warning("Provider already registered: [%s]. Skipping...", svc_name)
                    continue
                LOGGER.warning("Provider matches registered service: [%s]. Updating details...", svc_name)
            try:
                service_store.save_service(new_service, overwrite=True)
            except Exception as ex:
                LOGGER.exception("Exception during provider registration: [%s] [%r]. Skipping...", svc_name, ex)
                continue

        LOGGER.info("Finished processing configuration file [%s].", wps_processes_file_path)
    except Exception as exc:
        msg = "Invalid WPS-1 providers configuration file [{!r}].".format(exc)
        LOGGER.exception(msg)
        raise RuntimeError(msg)
