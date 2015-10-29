import pymongo

from twitcher.exceptions import OWSServiceNotFound, OWSServiceException
from twitcher.utils import namesgenerator, baseurl

import logging
logger = logging.getLogger(__name__)


def add_service(request, url, identifier=None):
    # get baseurl
    service_url = baseurl(url)
    # check if service is already registered
    service = request.db.services.find_one({'url': service_url})
    if service is None:
        if identifier is None:
            identifier = namesgenerator.get_random_name()
            if not request.db.services.find_one({'identifier': identifier}) is None:
                identifier = namesgenerator.get_random_name(retry=True)
        service = dict(identifier = identifier, url = service_url)
        if request.db.services.find_one({'identifier': identifier}):
            raise OWSServiceException("identifier %s already registered." % (identifier))
        request.db.services.insert_one(service)
        service = request.db.services.find_one({'identifier': service['identifier']})
    return service


def remove_service(request, identifier):
    request.db.services.delete_one({'identifier': identifier})

    
def list_services(request):
    my_services = []
    for service in request.db.services.find().sort('identifer', pymongo.ASCENDING):
        my_services.append({
            'identifier': service['identifier'],
            'url': service['url'],
            'proxy_url': proxyurl(request, service['identifier'])})
    return my_services


def get_service(request, identifier):
    service = request.db.services.find_one({'identifier': identifier})
    if service is None:
        raise OWSServiceNotFound('service not found')
    if not 'url' in service:
        raise OWSServiceNotFound('service has no url')
    return dict(url=service.get('url'),
                identifier=identifier,
                proxy_url=proxyurl(request, service['identifier']))


def clear(request):
    """
    removes all services.
    """
    request.db.services.drop()


def proxyurl(request, identifier):
    return request.route_url('owsproxy', service_id=identifier)

    
    





