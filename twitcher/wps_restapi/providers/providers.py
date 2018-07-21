from pyramid.response import Response
import pyramid.httpexceptions as exc
from owslib.wps import WebProcessingService

from twitcher.adapter import servicestore_factory
from twitcher.datatype import Service
from twitcher.exceptions import ServiceNotFound
from twitcher.wps_restapi.utils import restapi_base_url, get_cookie_headers

import logging
logger = logging.getLogger('TWITCHER')


def get_providers(request):
    """
    Lists providers
    """
    store = servicestore_factory(request.registry)
    providers = []

    for service in store.list_services(request=request):
        try:
            wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
            providers.append(dict(
                id=service.name,
                title=getattr(wps.identification, 'title', ''),
                abstract=getattr(wps.identification, 'abstract', ''),
                url='{base_url}/providers/{provider_id}'.format(
                    base_url=restapi_base_url(request),
                    provider_id=service.name),
                public=service.public))
        except Exception as e:
            logger.warn('Exception occurs while fetching wps {0} : {1!r}'.format(service.url, e))
            pass

    return providers


def get_capabilities(service, request):
    """
    GetCapabilities of a wps provider
    """
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))

    return dict(
        id=service.name,
        title=wps.identification.title,
        abstract=wps.identification.abstract,
        url='{base_url}/providers/{provider_id}'.format(
            base_url=restapi_base_url(request),
            provider_id=service.name),
        processes='{base_url}/providers/{provider_id}/processes'.format(
            base_url=restapi_base_url(request),
            provider_id=service.name),
        type='WPS',
        contact=wps.provider.contact.name)


def get_service(request):
    """
    Get the request service using provider_id from the service store
    """
    store = servicestore_factory(request.registry)
    provider_id = request.matchdict.get('provider_id')
    try:
        service = store.fetch_by_name(provider_id, request=request)
    except ServiceNotFound:
        logger.warn('Provider {0} cannot be found'.format(provider_id))
        raise exc.HTTPNotFound('Provider {0} cannot be found'.format(provider_id))
    return service, store


def add_provider(request):
    """
    Add a provider
    """
    store = servicestore_factory(request.registry)

    try:
        new_service = Service(url=request.json['url'], name=request.json['id'])
    except KeyError as e:
        logger.warn('Missing json parameter {0}'.format(e))
        raise exc.HTTPBadRequest(detail='Missing json parameter {0}'.format(e))

    if 'public' in request.json:
        new_service['public'] = request.json['public']
    if 'auth' in request.json:
        new_service['auth'] = request.json['auth']

    try:
        store.save_service(new_service, request=request)
    except NotImplementedError:
        logger.warn('Add provider not supported')
        raise exc.HTTPNotImplemented(detail='Add provider not supported')

    return get_capabilities(new_service, request)


def remove_provider(request):
    """
    Remove a provider
    """
    service, store = get_service(request)

    try:
        store.delete_service(service.name, request=request)
    except NotImplementedError:
        logger.warn('Delete provider not supported')
        raise exc.HTTPNotImplemented(detail='Delete provider not supported')

    return Response(status=204)


def get_provider(request):
    """
    GetCapabilities of a wps provider
    """
    service, store = get_service(request)
    return get_capabilities(service, request)
