import logging
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPCreated,
    HTTPNoContent,
    HTTPOk,
    HTTPUnprocessableEntity
)
from pyramid.settings import asbool

from weaver.database import get_db
from weaver.datatype import Process, Service
from weaver.exceptions import ServiceNotFound, ServiceParsingError, log_unhandled_exceptions
from weaver.formats import ContentType, OutputFormat
from weaver.owsexceptions import OWSMissingParameterValue, OWSNotImplemented
from weaver.processes.execution import submit_job
from weaver.store.base import StoreServices
from weaver.utils import get_any_id
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.utils import get_process_list_links
from weaver.wps_restapi.providers.utils import check_provider_requirements, get_provider_services, get_service
from weaver.wps_restapi.utils import get_schema_ref, handle_schema_validation

if TYPE_CHECKING:
    from typing import Optional, Tuple

    from pyramid.config import Configurator

    from weaver.typedefs import AnyViewResponse, PyramidRequest

LOGGER = logging.getLogger(__name__)


@sd.providers_service.get(
    tags=[sd.TAG_PROVIDERS],
    schema=sd.GetProviders(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_providers_list_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_providers(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Lists registered providers.
    """
    detail = asbool(request.params.get("detail", True))
    check = asbool(request.params.get("check", True))
    ignore = asbool(request.params.get("ignore", True))
    reachable_services = get_provider_services(request, check=check, ignore=ignore)
    providers = []
    for service in reachable_services:
        summary = service.summary(request, fetch=check, ignore=ignore) if detail else service.name
        if summary:
            providers.append(summary)
    data = {"checked": check, "providers": providers}
    return HTTPOk(json=sd.ProvidersBodySchema().deserialize(data))


@sd.providers_service.post(
    tags=[sd.TAG_PROVIDERS],
    content_type=ContentType.APP_JSON,
    schema=sd.PostProvider(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_provider_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def add_provider(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Register a new service provider.
    """
    schema = sd.CreateProviderRequestBody()
    schema_ref = get_schema_ref(schema, request)
    try:
        body = schema.deserialize(request.json)
    except colander.Invalid as invalid:
        data = {
            "description": f"Invalid schema: [{invalid!s}]",
            "value": invalid.value
        }
        data.update(schema_ref)
        raise HTTPBadRequest(json=data)

    store = get_db(request).get_store(StoreServices)
    prov_id = get_any_id(body)
    try:
        store.fetch_by_name(prov_id)
    except ServiceNotFound:
        pass
    else:
        raise HTTPConflict(f"Provider [{prov_id}] already exists.")
    try:
        new_service = Service(url=body["url"], name=prov_id)
    except KeyError as exc:
        raise OWSMissingParameterValue(f"Missing JSON parameter '{exc!s}'.", value=exc)

    if "public" in body:
        new_service["public"] = body["public"]
    if "auth" in body:
        new_service["auth"] = body["auth"]

    try:
        # validate that metadata or any pre-fetch operation can be resolved
        service = new_service.summary(request, fetch=True, ignore=False)
        if not service:
            raise colander.Invalid(None, value=body)
        store.save_service(new_service)
    except NotImplementedError:  # raised when supported service types / conversion
        raise OWSNotImplemented(sd.NotImplementedPostProviderResponse.description, value=new_service)
    except ServiceParsingError:  # derives from HTTPUnprocessableEntity with relevant error message
        raise
    except colander.Invalid as invalid:
        data = {
            "description": "Provider properties could not be parsed correctly.",
            "value": invalid.value
        }
        data.update(schema_ref)
        raise HTTPUnprocessableEntity(json=data)
    data = get_schema_ref(sd.ProviderSummarySchema, request)
    data.update(service)
    return HTTPCreated(json=data)


@sd.provider_service.delete(
    tags=[sd.TAG_PROVIDERS],
    schema=sd.ProviderEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.delete_provider_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def remove_provider(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Remove an existing service provider.
    """
    store = get_db(request).get_store(StoreServices)
    service = get_service(request)

    try:
        store.delete_service(service.name)
    except NotImplementedError:
        raise OWSNotImplemented(sd.NotImplementedDeleteProviderResponse.description)

    return HTTPNoContent(json={})


@sd.provider_service.get(
    tags=[sd.TAG_PROVIDERS],
    schema=sd.ProviderEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_provider_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_provider(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get a provider definition (GetCapabilities).
    """
    service = get_service(request)
    data = get_schema_ref(sd.ProviderSummarySchema, request, ref_name=False)
    info = service.summary(request)
    data.update(info)
    return HTTPOk(json=data)


# FIXME: Add HTML view??? (same as local process, but extra 'provider' field?)
@sd.provider_processes_service.get(
    tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
    schema=sd.ProviderProcessesEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_provider_processes_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_provider_processes(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Retrieve available provider processes (GetCapabilities).
    """
    detail = asbool(request.params.get("detail", True))
    with_links = asbool(request.params.get("links", True)) and detail
    provider_id = request.matchdict.get("provider_id")
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id)
    processes = service.processes(request)
    processes = [p.summary(links=with_links, container=request) if detail else p.id for p in processes]
    links = get_process_list_links(request, paging={}, total=None, provider=service)
    body = {"processes": processes, "links": links}
    body = sd.ProcessesListing().deserialize(body)
    return HTTPOk(json=body)


@check_provider_requirements
def describe_provider_process(request, provider_id=None):
    # type: (PyramidRequest, Optional[str]) -> Tuple[Process, Service]
    """
    Obtains a remote service process description in a compatible local process format.

    Note: this processes won't be stored to the local process storage.
    """
    service = get_service(request, provider_id=provider_id)
    # FIXME: support other providers (https://github.com/crim-ca/weaver/issues/130)
    wps = service.wps(request)  # will cache, returned 'service' can reuse metadata without re-fetch
    proc_id = request.matchdict.get("process_id")
    process = wps.describeprocess(proc_id)
    return Process.convert(process, service, container=request), service


@sd.provider_process_service.get(
    tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    schema=sd.ProviderProcessEndpoint(),
    response_schemas=sd.get_provider_process_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@handle_schema_validation()
@check_provider_requirements
def get_provider_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Retrieve a remote provider's process description (DescribeProcess).
    """
    process, _ = describe_provider_process(request)
    schema = request.params.get("schema")
    offering = process.offering(schema)
    return HTTPOk(json=offering)


@sd.provider_process_package_service.get(
    tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProviderProcessPackageEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_provider_process_package_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_provider_process_package(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Retrieve a remote provider's process Application Package definition.
    """
    process, _ = describe_provider_process(request)
    return HTTPOk(json=process.package or {})


@sd.provider_execution_service.post(
    tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS],
    schema=sd.PostProviderProcessJobRequest(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_provider_process_job_responses,
)
@sd.provider_jobs_service.post(
    tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS],
    schema=sd.PostProviderProcessJobRequest(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_provider_process_job_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def submit_provider_job(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Execute a remote provider process.
    """
    service = get_service(request)
    return submit_job(request, service, tags=["wps-rest"])


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API provider views...")
    config.add_cornice_service(sd.providers_service)
    config.add_cornice_service(sd.provider_service)
    config.add_cornice_service(sd.provider_processes_service)
    config.add_cornice_service(sd.provider_process_service)
    config.add_cornice_service(sd.provider_process_package_service)
    config.add_cornice_service(sd.provider_execution_service)
