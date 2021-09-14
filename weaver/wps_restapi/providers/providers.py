import logging
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPCreated,
    HTTPNoContent,
    HTTPNotFound,
    HTTPOk,
    HTTPUnprocessableEntity
)
from pyramid.settings import asbool

from weaver.database import get_db
from weaver.datatype import Service
from weaver.exceptions import ServiceNotFound, log_unhandled_exceptions
from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.owsexceptions import OWSMissingParameterValue, OWSNotImplemented
from weaver.store.base import StoreServices
from weaver.utils import get_any_id, get_settings
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_schema_ref

if TYPE_CHECKING:
    from typing import List

    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


def get_provider_services(container, check=True):
    # type: (AnySettingsContainer, bool) -> List[Service]
    """
    Obtain the list of remote provider services.

    :param container: definition to retrieve settings and database connection.
    :param check: request that all provider services are remotely accessible to fetch metadata from them.
    """
    settings = get_settings(container)
    store = get_db(settings).get_store(StoreServices)
    providers = []
    if not check:
        LOGGER.info("Skipping remote provider service check. Accessibility of listed services will not be validated.")
    for service in store.list_services():
        if check and not service.check_accessible(settings):
            LOGGER.warning("Skipping unresponsive service (%s) [%s]", service.name, service.url)
            continue
        providers.append(service)
    return providers


@sd.providers_service.get(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                          schema=sd.GetProviders(), response_schemas=sd.get_providers_list_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
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


def get_service(request):
    """
    Get the request service using provider_id from the service store.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get("provider_id")
    try:
        service = store.fetch_by_name(provider_id)
    except ServiceNotFound:
        raise HTTPNotFound("Provider {0} cannot be found.".format(provider_id))
    return service, store


@sd.providers_service.post(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.PostProvider(), response_schemas=sd.post_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
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
def get_provider(request):
    """
    Get a provider definition (GetCapabilities).
    """
    service, _ = get_service(request)
    return HTTPOk(json=service.summary(request))
