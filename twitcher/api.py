from twitcher.tokengenerator import tokengenerator_factory
from twitcher.store import tokenstore_factory
from twitcher.store import servicestore_factory
from twitcher.datatype import Service
from twitcher.utils import parse_service_name

import logging
logger = logging.getLogger(__name__)


def service_api_factory(registry):
    return ServiceAPI(
        tokengenerator=tokengenerator_factory(registry),
        tokenstore=tokenstore_factory(registry),
        servicestore=servicestore_factory(registry))


class ServiceAPI(object):
    def __init__(self, tokengenerator, tokenstore, servicestore):
        self.tokengenerator = tokengenerator
        self.tokenstore = tokenstore
        self.servicestore = servicestore

    # token management
    # ----------------

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
        self.tokenstore.save_token(access_token)
        return access_token.params

    def revoke_token(self, token):
        """
        Remove token from tokenstore.
        """
        try:
            self.tokenstore.delete_token(token)
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
            self.tokenstore.clear_tokens()
        except:
            logger.exception('Failed to remove tokens.')
            return False
        else:
            return True

    # service servicestore
    # ----------------

    def register_service(self, url, name, service_type, public, c4i, overwrite):
        """
        Adds an OWS service with the given ``url`` to the servicestore.
        """
        service = Service(url=url, name=name, type=service_type, public=public, c4i=c4i)
        service = self.servicestore.save_service(service, overwrite=overwrite)
        return service.params

    def unregister_service(self, name):
        """
        Removes OWS service with the given ``name`` from the servicestore.
        """
        try:
            self.servicestore.delete_service(name=name)
        except:
            logger.exception('unregister failed')
            return False
        else:
            return True

    def get_service_by_name(self, name):
        """
        Get service for given ``name`` from servicestore database.
        """
        try:
            service = self.servicestore.fetch_by_name(name=name)
        except:
            logger.exception('could not get service with name %s', name)
            return {}
        else:
            return service

    def get_service_by_url(self, url):
        """
        Get service for given ``url`` from servicestore database.
        """
        try:
            service = self.servicestore.fetch_by_url(url=url)
        except:
            logger.exception('could not get service with url %s', url)
            return {}
        else:
            return service

    def list_services(self):
        """
        Lists all registred OWS services.
        """
        try:
            services = self.servicestore.list_services()
            for service in services:
                service['proxy_url'] = self.request.route_url('owsproxy', service_name=service['name'])
            return services
        except:
            logger.exception('register failed')
            return []

    def clear_services(self):
        """
        Removes all services from the servicestore.
        """
        try:
            self.servicestore.clear_services()
        except:
            logger.exception('clear failed')
            return False
        else:
            return True
