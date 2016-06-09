import pymongo

from twitcher.utils import namesgenerator, baseurl
from twitcher.db import mongodb

import logging
logger = logging.getLogger(__name__)


def proxy_url(request, service_name):
    """
    Shortcut method to return route url to service name.
    """
    return request.route_url('owsproxy', service_name=service_name)


def update_with_proxy_url(request, services):
    for service in services:
        service['proxy_url'] = proxy_url(request, service['name'])
    return services

def service_name_of_proxy_url(proxy_url):
    from urlparse import urlparse
    parsed_url = urlparse(proxy_url)
    service_name = None
    if parsed_url.path.startswith("/ows/proxy"):
        service_name = parsed_url.path.strip('/').split('/')[2]
    return service_name


def service_registry_factory(registry):
    db = mongodb(registry)
    return ServiceRegistry(collection=db.services)


class ServiceRegistry(object):
    """
    Registry for OWS services. Uses mongodb to store service url and attributes. 
    """
    
    def __init__(self, collection):
        self.collection = collection

    def register_service(self, url, name=None, service_type='wps'):
        """
        Adds OWS service with given name to registry database.
        """
        
        service_url = baseurl(url)
        # check if service is already registered
        service = self.collection.find_one({'url': service_url})
        if service is None:
            name = namesgenerator.get_sane_name(name)
            if name is None:
                name = namesgenerator.get_random_name()
                if not self.collection.find_one({'name': name}) is None:
                    name = namesgenerator.get_random_name(retry=True)
            service = dict(url=service_url, name=name, type=service_type)
            if self.collection.find_one({'name': name}):
                logging.info("update registered service %s." % (name))
                self.collection.update_one({'name': name}, {'$set': service})
            else:
                self.collection.insert_one(service)
            service = self.collection.find_one({'name': service['name']})
        return service


    def unregister_service(self, name):
        """
        Removes service from registry database.
        """
        self.collection.delete_one({'name': name})


    def list_services(self):
        """
        Lists all servcies in registry database.
        """
        my_services = []
        for service in self.collection.find().sort('name', pymongo.ASCENDING):
            my_services.append({
                'name': service['name'],
                'type': service['type'],
                'url': service['url']})
        return my_services


    def get_service(self, name):
        """
        Get service for given ``name`` from registry database.
        """
        service = self.collection.find_one({'name': name})
        if service is None:
            raise ValueError('service not found')
        if not 'url' in service:
            raise ValueError('service has no url')
        return dict(url=service.get('url'), name=name)


    def get_service_by_url(self, url):
        """
        Get service for given ``url`` from registry database.
        """
        service = self.collection.find_one({'url': url})
        if service is None:
            raise ValueError('service not found')
        return dict(name=service.get('name'), url=url)
    
    def clear_services(self):
        """
        Removes all OWS services from registry database.
        """
        self.collection.drop()




    
    





