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
from weaver.exceptions import ServiceNotFound, log_unhandled_exceptions
from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.owsexceptions import OWSMissingParameterValue, OWSNotImplemented
from weaver.processes.execution import submit_job
from weaver.processes.utils import get_job_submission_response
from weaver.store.base import StoreServices
from weaver.utils import get_any_id, get_settings
from weaver.wps.utils import get_wps_client
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.providers.utils import check_provider_requirements, get_provider_services, get_service
from weaver.wps_restapi.utils import get_schema_ref

if TYPE_CHECKING:
    from pyramid.request import Request

LOGGER = logging.getLogger(__name__)


@sd.providers_service.get(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                          schema=sd.GetProviders(), response_schemas=sd.get_providers_list_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_providers(request):
    """
    Lists registered providers.
    """
    detail = asbool(request.params.get("detail", True))
    check = asbool(request.params.get("check", True))
    reachable_services = get_provider_services(request, check=check)
    providers = []
    for service in reachable_services:
        summary = service.summary(request, fetch=check) if detail else service.name
        if summary:
            providers.append(summary)
    data = {"checked": check, "providers": providers}
    return HTTPOk(json=sd.ProvidersBodySchema().deserialize(data))


@sd.providers_service.post(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.PostProvider(), response_schemas=sd.post_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def add_provider(request):
    """
    Register a new service provider.
    """
    schema = sd.CreateProviderRequestBody()
    schema_ref = get_schema_ref(schema, request)
    try:
        body = schema.deserialize(request.json)
    except colander.Invalid as invalid:
        data = {
            "description": "Invalid schema: [{!s}]".format(invalid),
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
        raise HTTPConflict("Provider [{}] already exists.".format(prov_id))
    try:
        new_service = Service(url=body["url"], name=prov_id)
    except KeyError as exc:
        raise OWSMissingParameterValue("Missing JSON parameter '{!s}'.".format(exc), value=exc)

    if "public" in body:
        new_service["public"] = body["public"]
    if "auth" in body:
        new_service["auth"] = body["auth"]

    try:
        store.save_service(new_service)
    except NotImplementedError:
        raise OWSNotImplemented(sd.NotImplementedPostProviderResponse.description, value=new_service)
    try:
        service = new_service.summary(request)
        if not service:
            raise colander.Invalid(None, value=body)
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


@sd.provider_service.delete(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.ProviderEndpoint(), response_schemas=sd.delete_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def remove_provider(request):
    """
    Remove an existing service provider.
    """
    service, store = get_service(request)

    try:
        store.delete_service(service.name)
    except NotImplementedError:
        raise OWSNotImplemented(sd.NotImplementedDeleteProviderResponse.description)

    return HTTPNoContent(json={})


@sd.provider_service.get(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                         schema=sd.ProviderEndpoint(), response_schemas=sd.get_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_provider(request):
    """
    Get a provider definition (GetCapabilities).
    """
    service, _ = get_service(request)
    return HTTPOk(json=service.summary(request))


@sd.provider_processes_service.get(tags=[sd.TAG_PROVIDERS, sd.TAG_PROCESSES, sd.TAG_PROVIDERS, sd.TAG_GETCAPABILITIES],
                                   renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderEndpoint(),
                                   response_schemas=sd.get_provider_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def get_provider_processes(request):
    """
    Retrieve available provider processes (GetCapabilities).
    """
    provider_id = request.matchdict.get("provider_id")
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id)
    processes = service.processes(request)
    return HTTPOk(json={"processes": [p.summary() for p in processes]})


@check_provider_requirements
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
@check_provider_requirements
def get_provider_process(request):
    """
    Retrieve a process description (DescribeProcess).
    """
    try:
        process = describe_provider_process(request)
        schema = request.params.get("schema")
        offering = process.offering(schema)
        return HTTPOk(json=offering)
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@sd.provider_jobs_service.post(tags=[sd.TAG_PROVIDERS, sd.TAG_PROVIDERS, sd.TAG_EXECUTE, sd.TAG_JOBS],
                               renderer=OUTPUT_FORMAT_JSON, schema=sd.PostProviderProcessJobRequest(),
                               response_schemas=sd.post_provider_process_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
@check_provider_requirements
def submit_provider_job(request):
    """
    Execute a remote provider process.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get("provider_id")
    service = store.fetch_by_name(provider_id)
    body = submit_job(request, service, tags=["wps-rest"])
    return get_job_submission_response(body)
