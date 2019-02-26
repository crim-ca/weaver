from weaver.database import get_db
from weaver.datatype import Service
from weaver.exceptions import ServiceNotFound
from weaver.warning import NonBreakingExceptionWarning
from weaver.owsexceptions import OWSMissingParameterValue, OWSNotImplemented
from weaver.store.base import StoreServices
from weaver.utils import get_any_id
from weaver.wps_restapi.utils import wps_restapi_base_url, get_cookie_headers
from weaver.wps_restapi import swagger_definitions as sd
from owslib.wps import WebProcessingService
from pyramid.httpexceptions import *
import warnings
import logging
logger = logging.getLogger('weaver')


@sd.providers_service.get(tags=[sd.providers_tag], renderer='json',
                          schema=sd.GetProviders(), response_schemas=sd.get_all_providers_responses)
def get_providers(request):
    """
    Lists registered providers.
    """
    store = get_db(request).get_store(StoreServices)
    providers = []

    for service in store.list_services(request=request):
        try:
            if service.type.lower() != 'wps':
                continue

            wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
            providers.append(dict(
                id=service.name,
                title=getattr(wps.identification, 'title', ''),
                abstract=getattr(wps.identification, 'abstract', ''),
                url='{base_url}/providers/{provider_id}'.format(
                    base_url=wps_restapi_base_url(request.registry.settings),
                    provider_id=service.name),
                public=service.public))
        except Exception as e:
            warnings.warn("Exception occurs while fetching wps {0} : {1!r}".format(service.url, e),
                          NonBreakingExceptionWarning)
            pass

    return HTTPOk(json=providers)


def get_capabilities(service, request):
    """
    GetCapabilities of a wps provider.
    """
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))

    return dict(
        id=service.name,
        title=wps.identification.title,
        abstract=wps.identification.abstract,
        url='{base_url}/providers/{provider_id}'.format(
            base_url=wps_restapi_base_url(request.registry.settings),
            provider_id=service.name),
        processes='{base_url}/providers/{provider_id}/processes'.format(
            base_url=wps_restapi_base_url(request.registry.settings),
            provider_id=service.name),
        type='WPS',
        contact=wps.provider.contact.name)


def get_service(request):
    """
    Get the request service using provider_id from the service store.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get('provider_id')
    try:
        service = store.fetch_by_name(provider_id, request=request)
    except ServiceNotFound:
        raise HTTPNotFound("Provider {0} cannot be found.".format(provider_id))
    return service, store


@sd.providers_service.post(tags=[sd.providers_tag], renderer='json',
                           schema=sd.PostProvider(), response_schemas=sd.post_provider_responses)
def add_provider(request):
    """
    Add a provider.
    """
    store = get_db(request).get_store(StoreServices)

    try:
        new_service = Service(url=request.json['url'], name=get_any_id(request.json))
    except KeyError as e:
        raise OWSMissingParameterValue("Missing json parameter '{!s}'.".format(e), value=str(e))

    if 'public' in request.json:
        new_service['public'] = request.json['public']
    if 'auth' in request.json:
        new_service['auth'] = request.json['auth']

    try:
        store.save_service(new_service, request=request)
    except NotImplementedError:
        raise OWSNotImplemented("Add provider not supported.", value=new_service)

    return HTTPCreated(json=get_capabilities(new_service, request))


@sd.provider_service.delete(tags=[sd.providers_tag], renderer='json',
                            schema=sd.ProviderEndpoint(), response_schemas=sd.delete_provider_responses)
def remove_provider(request):
    """
    Remove a provider.
    """
    service, store = get_service(request)

    try:
        store.delete_service(service.name, request=request)
    except NotImplementedError:
        raise OWSNotImplemented("Delete provider not supported.")

    return HTTPNoContent(json={})


@sd.provider_service.get(tags=[sd.providers_tag], renderer='json',
                         schema=sd.ProviderEndpoint(), response_schemas=sd.get_one_provider_responses)
def get_provider(request):
    """
    Get a provider description.
    """
    service, store = get_service(request)
    return HTTPOk(json=get_capabilities(service, request))
