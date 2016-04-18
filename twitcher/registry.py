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
            if name is None or len(name.strip()) < 3:
                name = namesgenerator.get_random_name()
                if not self.collection.find_one({'name': name}) is None:
                    name = namesgenerator.get_random_name(retry=True)
            service = dict(_id=name, url=service_url, name=name, type=service_type)
            if self.collection.find_one({'name': name}):
                logging.info("update registered service %s." % (name))
                self.collection.update_one({'name': name}, service)
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
        Get service url and proxy_url for given ``name`` from registry database.
        """
        service = self.collection.find_one({'name': name})
        if service is None:
            raise ValueError('service not found')
        if not 'url' in service:
            raise ValueError('service has no url')
        return dict(url=service.get('url'), name=name)

    
    def clear_services(self):
        """
        Removes all OWS services from registry database.
        """
        self.collection.drop()




    
    





