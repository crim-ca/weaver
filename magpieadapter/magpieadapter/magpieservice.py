"""
Store adapters to read data from magpie.
"""

import logging
import requests
import json
LOGGER = logging.getLogger(__name__)


from twitcher.store.base import ServiceStore
from twitcher.datatype import Service
from twitcher.exceptions import ServiceRegistrationError
from twitcher.exceptions import ServiceNotFound
from twitcher import namesgenerator
from twitcher.utils import baseurl
from pyramid.exceptions import ConfigurationError


class MagpieServiceStore(ServiceStore):
    """
    Registry for OWS services. Uses magpie to fetch service url and attributes.
    """
    def __init__(self, registry, headers=None):
        self.headers = headers
        try:
            self.magpie_url = registry.settings.get('magpie.url').strip('/')
        except AttributeError:
            #If magpie.url does not exist, calling strip fct over None will raise this issue
            raise ConfigurationError('magpie.url config cannot be found')

    def save_service(self, service, overwrite=True):
        """
        Magpie store is read-only, use magpie api to add services
        """
        raise NotImplementedError

    def delete_service(self, name):
        """
        Magpie store is read-only, use magpie api to delete services
        """
        raise NotImplementedError

    def list_services(self):
        """
        Lists all services registered in magpie.
        """
        my_services = []
        response = requests.get(self.magpie_url + '/services/types/wps', headers=self.headers)
        if response.status_code != 200:
            raise response.raise_for_status()
        services = json.loads(response.text)
        if 'wps' in services['services']:
            for key, service in services['services']['wps'].items():
                my_services.append(Service(url=service['service_url'], name=service['service_name']))
        return my_services

    def fetch_by_name(self, name):
        """
        Gets service for given ``name`` from magpie.
        """
        response = requests.get(self.magpie_url + '/services/{name}'.format(name=name), headers=self.headers)
        if response.status_code == 404:
            raise ServiceNotFound
        if response.status_code != 200:
            raise response.raise_for_status()
        services = json.loads(response.text)
        if name in services:
            return Service(url=services[name]['service_url'], name=services[name]['service_name'])
        raise ServiceNotFound

    def fetch_by_url(self, url):
        """
        Gets service for given ``url`` from mongodb storage.
        """
        services = self.list_services()
        for service in services:
            if service.url == url:
                return service
        raise ServiceNotFound


    def clear_services(self):
        """
        Magpie store is read-only, use magpie api to delete services
        """
        raise NotImplementedError
