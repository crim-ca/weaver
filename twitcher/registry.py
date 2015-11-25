import pymongo

from twitcher.utils import namesgenerator, baseurl

import logging
logger = logging.getLogger(__name__)


def proxyurl(request, service_name):
    """
    Shortcut method to return route url to service name.
    """
    return request.route_url('owsproxy', service_name=service_name)


def registry_factory(request):
    return ServiceRegistry(request)


class ServiceRegistry(object):
    """
    Registry for OWS services. Uses mongodb to store service url and attributes. 
    """
    
    def __init__(self, request):
        self.request = request
        self.db = request.db.services

    def add_service(self, url, service_name=None, service_type='WPS'):
        """
        Adds OWS service with given name to registry database.
        """
        
        service_url = baseurl(url)
        # check if service is already registered
        service = self.db.find_one({'url': service_url})
        if service is None:
            if service_name is None:
                service_name = namesgenerator.get_random_name()
                if not self.db.find_one({'name': service_name}) is None:
                    name = namesgenerator.get_random_name(retry=True)
            service = dict(url=service_url, name=service_name, type=service_type)
            if self.db.find_one({'name': service_name}):
                raise ValueError("service %s already registered." % (service_name))
            self.db.insert_one(service)
            service = self.db.find_one({'name': service['name']})
        return service


    def remove_service(self, service_name):
        """
        Removes service from registry database.
        """
        self.db.delete_one({'name': service_name})


    def list_services(self):
        """
        Lists all servcies in registry database.
        """
        my_services = []
        for service in self.db.find().sort('name', pymongo.ASCENDING):
            my_services.append({
                'name': service['name'],
                'type': service['type'],
                'url': service['url'],
                'proxy_url': proxyurl(self.request, service['name'])})
        return my_services


    def get_service(self, service_name):
        """
        Get service url and proxy_url for given ``service_name`` from registry database.
        """
        service = self.db.find_one({'name': service_name})
        if service is None:
            raise ValueError('service not found')
        if not 'url' in service:
            raise ValueError('service has no url')
        return dict(url=service.get('url'),
                    name=service_name,
                    proxy_url=proxyurl(self.request, service['name']))


    def clear_services(self):
        """
        Removes all OWS services from registry database.
        """
        self.db.drop()




    
    





