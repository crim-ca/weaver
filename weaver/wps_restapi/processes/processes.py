import logging
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPNotFound,
    HTTPOk,
    HTTPServiceUnavailable,
    HTTPUnprocessableEntity
)
from pyramid.request import Request
from pyramid.settings import asbool

from weaver.config import WEAVER_CONFIGURATIONS_REMOTE, get_weaver_configuration
from weaver.database import get_db
from weaver.datatype import Process, Service
from weaver.exceptions import ProcessNotFound, log_unhandled_exceptions
from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.processes import opensearch
from weaver.processes.execution import submit_job
from weaver.processes.types import PROCESS_BUILTIN
from weaver.processes.utils import deploy_process_from_payload, get_job_submission_response, get_process
from weaver.store.base import StoreProcesses, StoreServices
from weaver.utils import get_any_id, get_settings, parse_request_query
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_VALUES
from weaver.wps.utils import get_wps_client
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.providers.providers import get_provider_services

if TYPE_CHECKING:
    from weaver.typedefs import JSON
    from typing import List, Tuple

LOGGER = logging.getLogger(__name__)


@sd.provider_jobs_service.post(tags=[sd.TAG_PROVIDERS, sd.TAG_PROVIDERS, sd.TAG_EXECUTE, sd.TAG_JOBS],
                               renderer=OUTPUT_FORMAT_JSON, schema=sd.PostProviderProcessJobRequest(),
                               response_schemas=sd.post_provider_process_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def submit_provider_job(request):
    """
    Execute a remote provider process.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get("provider_id")
    service = store.fetch_by_name(provider_id)
    body = submit_job(request, service, tags=["wps-rest"])
    return get_job_submission_response(body)


def list_remote_processes(service, request):
    # type: (Service, Request) -> List[Process]
    """
    Obtains a list of remote service processes in a compatible :class:`weaver.datatype.Process` format.

    Note: remote processes won't be stored to the local process storage.
    """
    # FIXME: support other providers (https://github.com/crim-ca/weaver/issues/130)
    wps = get_wps_client(service.url, request)
    settings = get_settings(request)
    return [Process.convert(process, service, settings) for process in wps.processes]


@sd.provider_processes_service.get(tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_PROVIDERS, sd.TAG_GETCAPABILITIES],
                                   renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderEndpoint(),
                                   response_schemas=sd.get_provider_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_provider_processes(request):
    """
    Retrieve available provider processes (GetCapabilities).
    """
    provider_id = request.matchdict.get("provider_id")
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id)
    processes = list_remote_processes(service, request)
    return HTTPOk(json={"processes": [p.summary() for p in processes]})


def describe_provider_process(request):
    # type: (Request) -> Process
    """
    Obtains a remote service process description in a compatible local process format.

    Note: this processes won't be stored to the local process storage.
    """
    provider_id = request.matchdict.get("provider_id")
    process_id = request.matchdict.get("process_id")
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id)
    # FIXME: support other providers (https://github.com/crim-ca/weaver/issues/130)
    wps = get_wps_client(service.url, request)
    process = wps.describeprocess(process_id)
    return Process.convert(process, service, get_settings(request))


@sd.provider_process_service.get(tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_PROVIDERS, sd.TAG_DESCRIBEPROCESS],
                                 renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderProcessEndpoint(),
                                 response_schemas=sd.get_provider_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_provider_process(request):
    """
    Retrieve a process description (DescribeProcess).
    """
    try:
        process = describe_provider_process(request)
        process_offering = process.offering()
        return HTTPOk(json=process_offering)
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


def get_processes_filtered_by_valid_schemas(request):
    # type: (Request) -> Tuple[List[JSON], List[str]]
    """
    Validates the processes summary schemas and returns them into valid/invalid lists.
    :returns: list of valid process summaries and invalid processes IDs for manual cleanup.
    """
    store = get_db(request).get_store(StoreProcesses)
    processes = store.list_processes(visibility=VISIBILITY_PUBLIC)
    valid_processes = list()
    invalid_processes_ids = list()
    for process in processes:
        try:
            valid_processes.append(process.summary())
        except colander.Invalid as invalid:
            LOGGER.debug("Invalid process [%s] because:\n%s", process.identifier, invalid)
            invalid_processes_ids.append(process.identifier)
    return valid_processes, invalid_processes_ids


@sd.processes_service.get(schema=sd.GetProcessesEndpoint(), tags=[sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
                          response_schemas=sd.get_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_processes(request):
    """
    List registered processes (GetCapabilities). Optionally list both local and provider processes.
    """
    detail = asbool(request.params.get("detail", True))
    try:
        # get local processes and filter according to schema validity
        # (previously deployed process schemas can become invalid because of modified schema definitions
        processes, invalid_processes = get_processes_filtered_by_valid_schemas(request)
        if invalid_processes:
            raise HTTPServiceUnavailable(
                "Previously deployed processes are causing invalid schema integrity errors. "
                "Manual cleanup of following processes is required: {}".format(invalid_processes))
        response_body = {"processes": processes if detail else [get_any_id(p) for p in processes]}

        # if 'EMS' and '?providers=True', also fetch each provider's processes
        settings = get_settings(request)
        if get_weaver_configuration(settings) in WEAVER_CONFIGURATIONS_REMOTE:
            queries = parse_request_query(request)
            # FIXME: many steps below suppose that everything goes well...
            if "providers" in queries and asbool(queries["providers"][0]) is True:
                services = get_provider_services(request)
                response_body.update({
                    "providers": [svc.summary(request) if detail else {"id": svc.name} for svc in services]
                })
                for i, provider in enumerate(services):
                    processes = list_remote_processes(provider, request)
                    response_body["providers"][i].update({
                        "processes": processes if detail else [get_any_id(proc) for proc in processes.json()]
                    })
        return HTTPOk(json=response_body)
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@sd.processes_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.PostProcessesEndpoint(), response_schemas=sd.post_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def add_local_process(request):
    """
    Register a local process.
    """
    return deploy_process_from_payload(request.json, request)


@sd.process_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OUTPUT_FORMAT_JSON,
                        schema=sd.ProcessEndpoint(), response_schemas=sd.get_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process(request):
    """
    Get a registered local process information (DescribeProcess).
    """
    try:
        process = get_process(request=request)
        process["inputs"] = opensearch.replace_inputs_describe_process(process.inputs, process.payload)
        return HTTPOk(json=process.offering())
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]\nValue: [{!s}]".format(ex, ex.value))


@sd.process_package_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessPackageEndpoint(), response_schemas=sd.get_process_package_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process_package(request):
    """
    Get a registered local process package definition.
    """
    process = get_process(request=request)
    return HTTPOk(json=process.package or {})


@sd.process_payload_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessPayloadEndpoint(), response_schemas=sd.get_process_payload_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process_payload(request):
    """
    Get a registered local process payload definition.
    """
    process = get_process(request=request)
    return HTTPOk(json=process.payload or {})


@sd.process_visibility_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.ProcessVisibilityGetEndpoint(),
                                   response_schemas=sd.get_process_visibility_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_process_visibility(request):
    """
    Get the visibility of a registered local process.
    """
    process = get_process(request=request)
    return HTTPOk(json={u"value": process.visibility})


@sd.process_visibility_service.put(tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.ProcessVisibilityPutEndpoint(),
                                   response_schemas=sd.put_process_visibility_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def set_process_visibility(request):
    """
    Set the visibility of a registered local process.
    """
    visibility_value = request.json.get("value")
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, str):
        raise HTTPUnprocessableEntity("Invalid process identifier.")
    if not isinstance(visibility_value, str):
        raise HTTPUnprocessableEntity("Invalid visibility value specified. String expected.")
    if visibility_value not in VISIBILITY_VALUES:
        raise HTTPBadRequest("Invalid visibility value specified: {!s}".format(visibility_value))

    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id)
        if process.type == PROCESS_BUILTIN:
            raise HTTPForbidden("Cannot change the visibility of builtin process.")
        store.set_visibility(process_id, visibility_value)
        return HTTPOk(json={u"value": visibility_value})
    except TypeError:
        raise HTTPBadRequest("Value of visibility must be a string.")
    except ValueError:
        raise HTTPUnprocessableEntity("Value of visibility must be one of : {!s}".format(list(VISIBILITY_VALUES)))
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))


@sd.process_service.delete(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.ProcessEndpoint(), response_schemas=sd.delete_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def delete_local_process(request):
    """
    Unregister a local process.
    """
    store = get_db(request).get_store(StoreProcesses)
    process = get_process(request=request, store=store)
    process_id = process.id
    if process.type == PROCESS_BUILTIN:
        raise HTTPForbidden("Cannot delete a builtin process.")
    if store.delete_process(process_id, visibility=VISIBILITY_PUBLIC):
        return HTTPOk(json={"undeploymentDone": True, "identifier": process_id})
    LOGGER.error("Existing process [%s] should have been deleted with success status.", process_id)
    raise HTTPForbidden("Deletion of process has been refused by the database or could not have been validated.")


@sd.process_execution_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.PostProcessJobsEndpoint(), response_schemas=sd.post_process_jobs_responses)
@sd.process_jobs_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.PostProcessJobsEndpoint(), response_schemas=sd.post_process_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def submit_local_job(request):
    """
    Execute a process registered locally. Execution location and method is according to deployed Application Package.
    """
    process = get_process(request=request)
    body = submit_job(request, process, tags=["wps-rest"])
    return get_job_submission_response(body)
