import pymongo

from twitcher.exceptions import OWSServiceNotFound, OWSServiceException
from twitcher.utils import namesgenerator, baseurl

import logging
logger = logging.getLogger(__name__)

def add_service(request, url, service_name=None, service_type='WPS'):
    # get baseurl
    service_url = baseurl(url)
    # check if service is already registered
    service = request.db.services.find_one({'url': service_url})
    if service is None:
        if service_name is None:
            service_name = namesgenerator.get_random_name()
            if not request.db.services.find_one({'name': service_name}) is None:
                name = namesgenerator.get_random_name(retry=True)
        service = dict(url=service_url, name=service_name, type=service_type)
        if request.db.services.find_one({'name': service_name}):
            raise OWSServiceException("service %s already registered." % (service_name))
        request.db.services.insert_one(service)
        service = request.db.services.find_one({'name': service['name']})
    return service


def remove_service(request, service_name):
    request.db.services.delete_one({'name': service_name})

    
def list_services(request):
    my_services = []
    for service in request.db.services.find().sort('name', pymongo.ASCENDING):
        my_services.append({
            'name': service['name'],
            'type': service['type'],
            'url': service['url'],
            'proxy_url': proxyurl(request, service['name'])})
    return my_services


def get_service(request, service_name):
    service = request.db.services.find_one({'name': service_name})
    if service is None:
        raise OWSServiceNotFound('service not found')
    if not 'url' in service:
        raise OWSServiceNotFound('service has no url')
    return dict(url=service.get('url'),
                name=service_name,
                proxy_url=proxyurl(request, service['name']))


def clear_services(request):
    """
    removes all services.
    """
    request.db.services.drop()


def proxyurl(request, service_name):
    return request.route_url('owsproxy', service_name=service_name)

    
    





