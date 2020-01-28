import logging
import warnings

from owslib.wps import WebProcessingService
from pyramid.httpexceptions import HTTPCreated, HTTPNoContent, HTTPNotFound, HTTPOk

from utils import get_cookie_headers
from weaver.database import get_db
from weaver.datatype import Service
from weaver.exceptions import ServiceNotFound, log_unhandled_exceptions
from weaver.owsexceptions import OWSMissingParameterValue, OWSNotImplemented
from weaver.processes.types import PROCESS_WPS
from weaver.store.base import StoreServices
from weaver.utils import get_any_id, get_settings
from weaver.warning import NonBreakingExceptionWarning
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import OUTPUT_FORMAT_JSON, get_wps_restapi_base_url

LOGGER = logging.getLogger(__name__)


@sd.providers_service.get(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                          schema=sd.GetProviders(), response_schemas=sd.get_providers_list_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProvidersListResponse.description)
def get_providers(request):
    """
    Lists registered providers.
    """
    store = get_db(request).get_store(StoreServices)
    providers = []

    for service in store.list_services(request=request):
        try:
            if service.type.lower() != "wps":
                continue

            wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
            providers.append(dict(
                id=service.name,
                title=getattr(wps.identification, "title", ""),
                abstract=getattr(wps.identification, "abstract", ""),
                url="{base_url}/providers/{provider_id}".format(
                    base_url=get_wps_restapi_base_url(get_settings(request)),
                    provider_id=service.name),
                public=service.public))
        except Exception as exc:
            warnings.warn("Exception occurred while fetching wps {0} : {1!r}".format(service.url, exc),
                          NonBreakingExceptionWarning)

    return HTTPOk(json=providers)


def get_capabilities(service, request):
    """
    GetCapabilities of a wps provider.
    """
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    settings = get_settings(request)
    return dict(
        id=service.name,
        title=wps.identification.title,
        abstract=wps.identification.abstract,
        url="{base_url}/providers/{provider_id}".format(
            base_url=get_wps_restapi_base_url(settings),
            provider_id=service.name),
        processes="{base_url}/providers/{provider_id}/processes".format(
            base_url=get_wps_restapi_base_url(settings),
            provider_id=service.name),
        type=PROCESS_WPS,
        contact=wps.provider.contact.name)


def get_service(request):
    """
    Get the request service using provider_id from the service store.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get("provider_id")
    try:
        service = store.fetch_by_name(provider_id, request=request)
    except ServiceNotFound:
        raise HTTPNotFound("Provider {0} cannot be found.".format(provider_id))
    return service, store


@sd.providers_service.post(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.PostProvider(), response_schemas=sd.post_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorPostProviderResponse.description)
def add_provider(request):
    """
    Add a provider.
    """
    store = get_db(request).get_store(StoreServices)

    try:
        new_service = Service(url=request.json["url"], name=get_any_id(request.json))
    except KeyError as exc:
        raise OWSMissingParameterValue("Missing json parameter '{!s}'.".format(exc), value=exc)

    if "public" in request.json:
        new_service["public"] = request.json["public"]
    if "auth" in request.json:
        new_service["auth"] = request.json["auth"]

    try:
        store.save_service(new_service, request=request)
    except NotImplementedError:
        raise OWSNotImplemented(sd.NotImplementedPostProviderResponse.description, value=new_service)

    return HTTPCreated(json=get_capabilities(new_service, request))


@sd.provider_service.delete(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                            schema=sd.ProviderEndpoint(), response_schemas=sd.delete_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorDeleteProviderResponse.description)
def remove_provider(request):
    """
    Remove a provider.
    """
    service, store = get_service(request)

    try:
        store.delete_service(service.name, request=request)
    except NotImplementedError:
        raise OWSNotImplemented(sd.NotImplementedDeleteProviderResponse.description)

    return HTTPNoContent(json={})


@sd.provider_service.get(tags=[sd.TAG_PROVIDERS], renderer=OUTPUT_FORMAT_JSON,
                         schema=sd.ProviderEndpoint(), response_schemas=sd.get_provider_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProviderCapabilitiesResponse.description)
def get_provider(request):
    """
    Get a provider definition (GetCapabilities).
    """
    service, _ = get_service(request)
    return HTTPOk(json=get_capabilities(service, request))
