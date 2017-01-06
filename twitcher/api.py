from twitcher.datatype import Service
from twitcher.utils import parse_service_name

import logging
logger = logging.getLogger(__name__)


class ITokenManager(object):
    def generate_token(self, valid_in_hours=1, environ=None):
        """
        Generates an access token which is valid for ``valid_in_hours``.

        Arguments:

        * ``valid_in_hours``: number of hours the token is valid.
        * ``environ``: environment used with this token (dict object).

        Possible keys: ``esgf_access_token``, ``esgf_slcs_service_url``.
        """
        raise NotImplementedError

    def revoke_token(self, token):
        """
        Remove token from tokenstore.
        """
        raise NotImplementedError

    def revoke_all_tokens(self):
        """
        Removes all tokens from tokenstore.
        """
        raise NotImplementedError


class IRegistry(object):
    def register_service(self, url, name, service_type, public, c4i, overwrite):
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
        Lists all registred OWS services.
        """
        raise NotImplementedError

    def clear_services(self):
        """
        Removes all services from the service store.
        """
        raise NotImplementedError


class TokenManager(ITokenManager):
    def __init__(self, tokengenerator, tokenstore):
        self.tokengenerator = tokengenerator
        self.store = tokenstore

    def generate_token(self, valid_in_hours=1, environ=None):
        """
        Generates an access token which is valid for ``valid_in_hours``.

        Arguments:

        * ``valid_in_hours``: number of hours the token is valid.
        * ``environ``: environment used with this token (dict object).

        Possible keys: ``esgf_access_token``, ``esgf_slcs_service_url``.
        """
        access_token = self.tokengenerator.create_access_token(
            valid_in_hours=valid_in_hours,
            environ=environ,
        )
        self.store.save_token(access_token)
        return access_token.params

    def revoke_token(self, token):
        """
        Remove token from tokenstore.
        """
        try:
            self.store.delete_token(token)
        except:
            logger.exception('Failed to remove token.')
            return False
        else:
            return True

    def revoke_all_tokens(self):
        """
        Removes all tokens from tokenstore.
        """
        try:
            self.store.clear_tokens()
        except:
            logger.exception('Failed to remove tokens.')
            return False
        else:
            return True


class Registry(IRegistry):
    def __init__(self, servicestore):
        self.store = servicestore

    def register_service(self, url, name, service_type, public, c4i, overwrite):
        """
        Adds an OWS service with the given ``url`` to the service store.
        """
        service = Service(url=url, name=name, type=service_type, public=public, c4i=c4i)
        service = self.store.save_service(service, overwrite=overwrite)
        return service.params

    def unregister_service(self, name):
        """
        Removes OWS service with the given ``name`` from the service store.
        """
        try:
            self.store.delete_service(name=name)
        except:
            logger.exception('unregister failed')
            return False
        else:
            return True

    def get_service_by_name(self, name):
        """
        Gets service with given ``name`` from service store.
        """
        try:
            service = self.store.fetch_by_name(name=name)
        except:
            logger.error('Could not get service with name %s', name)
            return {}
        else:
            return service.params

    def get_service_by_url(self, url):
        """
        Gets service with given ``url`` from service store.
        """
        try:
            service = self.store.fetch_by_url(url=url)
        except:
            logger.error('Could not get service with url %s', url)
            return {}
        else:
            return service.params

    def list_services(self):
        """
        Lists all registred OWS services.
        """
        try:
            services = [service.params for service in self.store.list_services()]
        except:
            logger.error('List services failed.')
            return []
        else:
            return services

    def clear_services(self):
        """
        Removes all services from the service store.
        """
        try:
            self.store.clear_services()
        except:
            logger.error('Clear services failed.')
            return False
        else:
            return True
