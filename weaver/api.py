from weaver.datatype import Service

import logging
LOGGER = logging.getLogger("weaver")


class IRegistry(object):
    def register_service(self, url, data, overwrite):
        """
        Adds an OWS service with the given ``url`` to the service store.
        """
        raise NotImplementedError

    def unregister_service(self, name):
        """
        Removes OWS service with the given ``name`` from the service store.
        """
        raise NotImplementedError

    def get_service_by_name(self, name):
        """
        Gets service with given ``name`` from service store.
        """
        raise NotImplementedError

    def get_service_by_url(self, url):
        """
        Gets service with given ``url`` from service store.
        """
        raise NotImplementedError

    def list_services(self):
        """
        Lists all registered OWS services.
        """
        raise NotImplementedError

    def clear_services(self):
        """
        Removes all services from the service store.
        """
        raise NotImplementedError


# noinspection PyBroadException
class Registry(IRegistry):
    """
    Implementation of :class:`weaver.api.IRegistry`.
    """
    def __init__(self, servicestore):
        self.store = servicestore

    def register_service(self, url, data=None, overwrite=True):
        """
        Implementation of :meth:`weaver.api.IRegistry.register_service`.
        """
        data = data or {}

        args = dict(data)
        args['url'] = url
        service = Service(**args)
        service = self.store.save_service(service, overwrite=overwrite)
        return service.params

    def unregister_service(self, name):
        """
        Implementation of :meth:`weaver.api.IRegistry.unregister_service`.
        """
        try:
            self.store.delete_service(name=name)
        except Exception:
            LOGGER.exception('unregister failed')
            return False
        else:
            return True

    def get_service_by_name(self, name):
        """
        Implementation of :meth:`weaver.api.IRegistry.get_service_by_name`.
        """
        try:
            service = self.store.fetch_by_name(name=name)
        except Exception:
            LOGGER.error('Could not get service with name %s', name)
            return {}
        else:
            return service.params

    def get_service_by_url(self, url):
        """
        Implementation of :meth:`weaver.api.IRegistry.get_service_by_url`.
        """
        try:
            service = self.store.fetch_by_url(url=url)
        except Exception:
            LOGGER.error('Could not get service with url %s', url)
            return {}
        else:
            return service.params

    def list_services(self):
        """
        Implementation of :meth:`weaver.api.IRegistry.list_services`.
        """
        try:
            services = [service.params for service in self.store.list_services()]
        except Exception:
            LOGGER.error('List services failed.')
            return []
        else:
            return services

    def clear_services(self):
        """
        Implementation of :meth:`weaver.api.IRegistry.clear_services`.
        """
        try:
            self.store.clear_services()
        except Exception:
            LOGGER.error('Clear services failed.')
            return False
        else:
            return True
