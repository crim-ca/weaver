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
    WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
    WeaverFeature,
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
from weaver.processes.types import ProcessType
from weaver.store.base import StoreProcesses, StoreServices
from weaver.utils import fully_qualified_name, get_sane_name, get_settings, get_url_without_query, generate_diff
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_client
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import List, Optional, Tuple, Union

    from pyramid.request import Request

    from weaver.typedefs import (
        AnyContainer,
        AnyHeadersContainer,
        AnySettingsContainer,
        CWL,
        FileSystemPathType,
        JSON,
        Number,
        SettingsType
    )


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
        process = store.fetch_by_id(process_id, visibility=Visibility.PUBLIC)
        return process
    except (InvalidIdentifierValue, MissingIdentifierValue) as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPForbidden(f"Process with ID '{process_id!s}' is not accessible.")
    except ProcessNotFound:
        raise ProcessNotFound(json={
            "title": "NoSuchProcess",
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
            "detail": "Process with specified reference identifier does not exist.",
            "status": ProcessNotFound.code,
            "cause": str(process_id)
        })
    except colander.Invalid as ex:
        raise HTTPBadRequest(f"Invalid schema:\n[{ex!r}].")


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
    """
    Validate minimum deploy payload field requirements with exception handling.
    """
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    message = "Process deployment definition is invalid."
    try:
        results = sd.Deploy().deserialize(payload)
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
        p_inputs = p_process.get("inputs")
        r_inputs = r_process.get("inputs")
        if p_inputs and p_inputs != r_inputs:
            message = "Process deployment inputs definition is invalid."
            # try raising sub-schema to have specific reason
            d_inputs = sd.DeployInputTypeAny().deserialize(p_inputs)
            # Raise directly if we where not able to detect the cause, but there is something incorrectly dropped.
            # Only raise if indirect vs direct inputs deserialize differ such that auto-resolved defaults omitted from
            # submitted process inputs or unknowns fields that were correctly ignored don't cause false-positive diffs.
            if r_inputs != d_inputs:
                message = (
                    "Process deployment inputs definition resolved as valid schema but differ from submitted values. "
                    "Validate provided inputs against resolved inputs with schemas to avoid mismatching definitions."
                )
                raise HTTPBadRequest(json={
                    "description": message,
                    "cause": "unknown",
                    "error": "Invalid",
                    "value": d_inputs
                })
        # Execution Unit is optional since process reference (e.g.: WPS-1 href) can be provided in processDescription
        # Cannot validate as CWL yet, since execution unit can also be an href that is not yet fetched (it will later)
        p_exec_unit = payload.get("executionUnit", [{}])
        r_exec_unit = results.get("executionUnit", [{}])
        if p_exec_unit and p_exec_unit != r_exec_unit:
            message = "Process deployment execution unit is invalid."
            d_exec_unit = sd.ExecutionUnitList().deserialize(p_exec_unit)  # raises directly if caused by invalid schema
            if r_exec_unit != d_exec_unit:  # otherwise raise a generic error, don't allow differing definitions
                message = (
                    "Process deployment execution unit resolved as valid definition but differs from submitted "
                    "package. Aborting deployment to avoid mismatching package definitions."
                )
                raise HTTPBadRequest(json={
                    "description": message,
                    "cause": "unknown",
                    "error": PackageRegistrationError.__name__,
                    "value": d_exec_unit
                })
            LOGGER.warning(
                "Detected difference between original/parsed deploy payload, but no invalid schema:\n%s",
                generate_diff(p_exec_unit, r_exec_unit, val_name="original payload", ref_name="parsed result")
            )
        return results
    except colander.Invalid as exc:
        LOGGER.debug("Failed deploy body schema validation:\n%s", exc)
        raise HTTPBadRequest(json={
            "description": message,
            "cause": f"Invalid schema: [{exc.msg!s}]",
            "error": exc.__class__.__name__,
            "value": exc.value
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
        info = get_process_definition(process_info, reference, package, data_source=None, headers=headers)

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
    # use deepcopy of to remove any circular dependencies before writing to mongodb or any updates to the payload
    payload_copy = deepcopy(payload)
    payload = _check_deploy(payload)

    # validate identifier naming for unsupported characters
    process_description = payload.get("processDescription")
    process_info = process_description.get("process", process_description)
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
        if not any(deployment_profile_name.endswith(typ) for typ in [ProcessType.APPLICATION, ProcessType.WORKFLOW]):
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

    if process_info.get("type", "") == ProcessType.BUILTIN:
        raise HTTPBadRequest(
            f"Invalid process type resolved from package: [{ProcessType.BUILTIN}]. "
            f"Deployment of {ProcessType.BUILTIN} process is not allowed."
        )

    # update and validate process information using WPS process offering, CWL/WPS reference or CWL package definition
    settings = get_settings(container)
    headers = getattr(container, "headers", {})  # container is any request (as when called from API Deploy request)
    process_info = _validate_deploy_process_info(process_info, reference, package, settings, headers)

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

    return HTTPCreated(json={
        "description": sd.OkPostProcessesResponse.description,
        "processSummary": process_summary,
        "deploymentDone": True
    })


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
    # otherwise replace silently bad character since since is requested to be inferred
    svc_name = get_sane_name(svc_name or url_p.hostname, assert_invalid=bool(svc_name))
    svc_proc = svc_proc or qs_p.get("identifier", [])  # noqa  # 'identifier=a,b,c' techically allowed
    svc_proc = [proc.strip() for proc in svc_proc if proc.strip()]  # remote empty
    if not isinstance(svc_name, str):
        raise ValueError(f"Invalid service value: [{svc_name!s}].")
    if not isinstance(svc_proc, list):
        raise ValueError(f"Invalid process value: [{svc_proc!s}].")
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
        proc_id = f"{service_name}_{get_sane_name(wps_process.identifier)}"
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
    except Exception as exc:
        msg = f"Invalid WPS-1 providers configuration file caused: [{fully_qualified_name(exc)}]({exc!s})."
        LOGGER.exception(msg)
        raise RuntimeError(msg)
