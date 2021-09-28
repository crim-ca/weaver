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
    WEAVER_CONFIGURATIONS_REMOTE,
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
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_BUILTIN, PROCESS_WORKFLOW
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
    body = sd.CreatedJobStatusSchema().deserialize(body)
    return HTTPCreated(location=body["location"], json=body)


def map_progress(progress, range_min, range_max):
    # type: (Number, Number, Number) -> Number
    """
    Calculates the relative progression of the percentage process within min/max values.
    """
    return max(range_min, min(range_max, range_min + (progress * (range_max - range_min)) / 100))


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of deploy payload.",
                          is_request=False)
def _check_deploy(payload):
    """
    Validate minimum deploy payload field requirements with exception handling.
    """
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    try:
        sd.Deploy().deserialize(payload)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@log_unhandled_exceptions(logger=LOGGER, message="Unhandled error occurred during parsing of process definition.",
                          is_request=False)
def _validate_deploy_process_info(process_info, reference, package, settings):
    """
    Obtain the process definition from deploy payload with exception handling.

    .. seealso::
        - :func:`weaver.processes.wps_package.get_process_definition`
    """
    from weaver.processes.wps_package import check_package_instance_compatible, get_process_definition
    try:
        # data_source `None` forces workflow process to search locally for deployed step applications
        info = get_process_definition(process_info, reference, package, data_source=None)

        # validate process type and package against weaver configuration
        cfg = get_weaver_configuration(settings)
        if cfg not in WEAVER_CONFIGURATIONS_REMOTE:
            problem = check_package_instance_compatible(info["package"])
            if problem:
                raise HTTPForbidden(json={
                    "description": "Invalid process deployment of type [{}] on [{}] instance. "
                                   "Remote execution is required but not supported.".format(info["type"], cfg),
                    "cause": problem
                })
        return info
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
    Deploy the process after resolution of all references and validation of the parameters from payload definition.

    Adds a :class:`weaver.datatype.Process` instance to storage using the provided JSON ``payload``
    matching :class:`weaver.wps_restapi.swagger_definitions.ProcessDescription`.

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

    if process_info.get("type", "") == PROCESS_BUILTIN:
        raise HTTPBadRequest(
            "Invalid process type resolved from package: [{0}]. Deployment of {0} process is not allowed."
            .format(PROCESS_BUILTIN))

    # update and validate process information using WPS process offering, CWL/WPS reference or CWL package definition
    settings = get_settings(container)
    process_info = _validate_deploy_process_info(process_info, reference, package, settings)

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
        store.save_process(process, overwrite=overwrite)
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
    # if explicit name was provided, validate it (assert fail if not),
    # otherwise replace silently bad character since since is requested to be inferred
    svc_name = get_sane_name(svc_name or url_p.hostname, assert_invalid=bool(svc_name))
    svc_proc = svc_proc or qs_p.get("identifier", [])  # noqa  # 'identifier=a,b,c' techically allowed
    svc_proc = [proc.strip() for proc in svc_proc if proc.strip()]  # remote empty
    if not isinstance(svc_name, str):
        raise ValueError("Invalid service value: [{!s}].".format(svc_name))
    if not isinstance(svc_proc, list):
        raise ValueError("Invalid process value: [{!s}].".format(svc_proc))
    return svc_name, svc_url, svc_proc, svc_vis


def register_wps_processes_static(service_url, service_name, service_visibility, service_processes, container):
    # type: (str, str, bool, List[str], AnySettingsContainer) -> None
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
    if LooseVersion(wps.version) >= LooseVersion("2.0"):
        LOGGER.warning("Invalid WPS-1 provider, version was [%s]", wps.version)
        return
    wps_processes = [wps.describeprocess(p) for p in service_processes] or wps.processes
    for wps_process in wps_processes:
        proc_id = "{}_{}".format(service_name, get_sane_name(wps_process.identifier))
        proc_url = "{}?service=WPS&request=DescribeProcess&identifier={}&version={}".format(
            service_url, wps_process.identifier, wps.version
        )
        svc_vis = VISIBILITY_PUBLIC if service_visibility else VISIBILITY_PRIVATE
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


def register_wps_processes_dynamic(service_name, service_url, service_visibility, container):
    # type: (str, str, bool, AnySettingsContainer) -> None
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


def register_wps_processes_from_config(wps_processes_file_path, container):
    # type: (Optional[FileSystemPathType], AnySettingsContainer) -> None
    """
    Registers remote `WPS` providers and/or processes as specified from the configuration file.

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
    except Exception as exc:
        msg = "Invalid WPS-1 providers configuration file caused: [{!s}]({!s}).".format(type(exc).__name__, exc)
        LOGGER.exception(msg)
        raise RuntimeError(msg)
