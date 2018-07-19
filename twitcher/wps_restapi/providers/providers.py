from pyramid.view import view_config
from twitcher.adapter import servicestore_factory
from owslib.wps import WebProcessingService
from twitcher.datatype import Service
from twitcher.wps_restapi.utils import restapi_base_url, get_cookie_headers
import pyramid.httpexceptions as exc


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
            pass

    return providers


def add_provider(request):
    """
    Add a provider
    """
    store = servicestore_factory(request.registry)

    # TODO Validate that params have at least a url and a name
    new_service = Service(url=request.json['url'], name=request.json['id'])
    if 'public' in request.json:
        new_service['public'] = request.json['public']
    if 'auth' in request.json:
        new_service['auth'] = request.json['auth']

    try:
        store.save_service(new_service, request=request)
    except NotImplementedError:
        raise exc.HTTPNotImplemented(detail='Add provider not supported')

    return {}


def remove_provider(request):
    """
    Remove a provider
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')

    try:
        store.delete_service(provider_id, request=request)
    except NotImplementedError:
        raise exc.HTTPNotImplemented(detail='Add provider not supported')

    return {}


def get_capabilities(request):
    """
    GetCapabilities of a wps provider
    """

    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')

    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))

    return dict(
        id=provider_id,
        title=wps.identification.title,
        abstract=wps.identification.abstract,
        url='{base_url}/providers/{provider_id}'.format(
            base_url=restapi_base_url(request),
            provider_id=provider_id),
        processes='{base_url}/providers/{provider_id}/processes'.format(
            base_url=restapi_base_url(request),
            provider_id=provider_id),
        type='WPS',
        contact=wps.provider.contact.name)
