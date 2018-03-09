from twitcher.store.base import ServiceStore
from twitcher.datatype import Service
from twitcher.exceptions import ServiceNotFound


import magpie.models as mpmodel


class PostgresServiceStore(ServiceStore):
    """
    Registry for OWS services. Uses postgres to store service url and attributes.
    """

    def __init__(self, db_session):
        self.session = db_session

    def fetch_by_name(self, name):
        """
        Gets service for given ``name`` from mongodb storage.
        """
        magpie_service = mpmodel.Service.by_service_name(service_name=name, db_session=self.session)
        if not magpie_service:
            raise ServiceNotFound

        # Convert magpie.Service to dict
        service = {}
        service['name'] = magpie_service.resource_name
        service['url'] = magpie_service.url
        service['type'] = magpie_service.type

        return Service(service)


    def save_service(self, service, overwrite=True):
        pass

    def delete_service(self, name):
        pass

    def fetch_by_url(self, url):
        pass

    def list_services(self):
        pass

    def clear_services(self):
        pass