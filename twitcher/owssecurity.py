from twitcher.exceptions import AccessTokenNotFound
from twitcher.owsexceptions import OWSAccessForbidden, OWSInvalidParameterValue
from twitcher.utils import path_elements
from twitcher.store import tokenstore_factory
from twitcher.store import servicestore_factory
from twitcher.utils import parse_service_name
from twitcher.owsrequest import OWSRequest
from twitcher.esgf import fetch_certificate

import logging
logger = logging.getLogger(__name__)

protected_path = '/ows/'


def owssecurity_factory(registry):
    return OWSSecurity(tokenstore_factory(registry), servicestore_factory(registry))


class OWSSecurity(object):

    def __init__(self, tokenstore, servicestore):
        self.tokenstore = tokenstore
        self.servicestore = servicestore

    def get_token_param(self, request):
        token = None
        if 'access_token' in request.params:
            token = request.params['access_token']   # in params
        elif 'Access-Token' in request.headers:
            token = request.headers['Access-Token']  # in header
        else:  # in path
            elements = path_elements(request.path)
            if len(elements) > 1:  # there is always /ows/
                token = elements[-1]   # last path element
        return token

    def check_request(self, request):
        if request.path.startswith(protected_path):
            # TODO: fix this code
            try:
                service_name = parse_service_name(request.path)
                service = self.servicestore.fetch_by_name(service_name)
                if service.public is True:
                    logger.info('public access for service %s', service_name)
                    return
            except ValueError:
                logger.warn("Service not registered.")
            ows_request = OWSRequest(request)
            if not ows_request.service_allowed():
                raise OWSInvalidParameterValue(
                    "service %s not supported" % ows_request.service, value="service")
            if not ows_request.public_access():
                try:
                    token = self.get_token_param(request)
                    access_token = self.tokenstore.fetch_by_token(token)
                    if not access_token:
                        raise AccessTokenNotFound()
                    elif access_token.is_expired():
                        raise OWSAccessForbidden("Access token is expired.")
                    # update request with environ from access token
                    request.environ.update(access_token.environ)
                    if 'esgf_access_token' in request.environ and 'esgf_slcs_service_url' in request.environ:
                        workdir = fetch_certificate(request)
                        request.headers['X-Requested-Workdir'] = workdir
                except AccessTokenNotFound:
                    raise OWSAccessForbidden("Access token is required to access this service.")
