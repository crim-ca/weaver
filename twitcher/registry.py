import pymongo

from twitcher.utils import namesgenerator, baseurl
from twitcher.db import mongodb
from twitcher.exceptions import RegistrationException

import logging
logger = logging.getLogger(__name__)


def parse_service_name(url):
    from urlparse import urlparse
    parsed_url = urlparse(url)
    service_name = None
    if parsed_url.path.startswith("/ows/proxy"):
        parts = parsed_url.path.strip('/').split('/')
        if len(parts) > 2:
            service_name = parts[2]
    if not service_name:
        raise ValueError('service_name not found')
    return service_name


def service_registry_factory(registry):
    db = mongodb(registry)
    return ServiceRegistry(collection=db.services)


def doc2dict(doc):
    """
    Converts a mongodb document to a dictionary
    """
    return dict(
        url=doc.get('url'),
        name=doc.get('name'),
        public=doc.get('public', False),
        c4i=doc.get('c4i', False))


class ServiceRegistry(object):
    """
    Registry for OWS services. Uses mongodb to store service url and attributes.
    """

    def __init__(self, collection):
        self.collection = collection

    def register_service(self, url, name=None, service_type='wps', public=False, c4i=False, overwrite=True):
        """
        Adds OWS service with given name to registry database.
        """

        service_url = baseurl(url)
        # check if service is already registered
        if self.collection.count({'url': service_url}) > 0:
            if overwrite:
                self.collection.delete_one({'url': service_url})
            else:
                raise RegistrationException("service url already registered.")

        name = namesgenerator.get_sane_name(name)
        if not name:
            name = namesgenerator.get_random_name()
            if self.collection.count({'name': name}) > 0:
                name = namesgenerator.get_random_name(retry=True)
        if self.collection.count({'name': name}) > 0:
            if overwrite:
                self.collection.delete_one({'name': name})
            else:
                raise Exception("service name already registered.")
        service = dict(url=service_url, name=name, type=service_type, public=public, c4i=c4i)
        self.collection.insert_one(service)
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
                'url': service['url'],
                'public': service.get('public', False),
                'c4i': service.get('c4i', False)})
        return my_services

    def get_service_by_name(self, name):
        """
        Get service for given ``name`` from registry database.
        """
        service = self.collection.find_one({'name': name})
        if service is None:
            raise ValueError('service not found')
        if 'url' not in service:
            raise ValueError('service has no url')
        return doc2dict(service)

    def get_service_by_url(self, url):
        """
        Get service for given ``url`` from registry database.
        """
        service = self.collection.find_one({'url': baseurl(url)})
        if not service:
            raise ValueError('service not found')
        return doc2dict(service)

    def get_service_name(self, url):
        try:
            service_name = parse_service_name(url)
        except ValueError:
            service = self.get_service_by_url(url)
            service_name = service['name']
        return service_name

    def is_public(self, name):
        try:
            service = self.get_service_by_name(name)
            public = service.get('public', False)
        except ValueError:
            public = False
        return public

    def clear_services(self):
        """
        Removes all OWS services from registry database.
        """
        self.collection.drop()
