import tempfile

from twitcher.exceptions import AccessTokenNotFound
from twitcher.exceptions import ServiceNotFound
from twitcher.owsexceptions import OWSAccessForbidden, OWSInvalidParameterValue
from twitcher.utils import path_elements
from twitcher.store import tokenstore_factory
from twitcher.store import servicestore_factory
from twitcher.utils import parse_service_name
from twitcher.owsrequest import OWSRequest
from twitcher.esgf import fetch_certificate, ESGF_CREDENTIALS

import logging
LOGGER = logging.getLogger("TWITCHER")

protected_path = '/ows/'


def owssecurity_factory(registry):
    return OWSSecurity(tokenstore_factory(registry), servicestore_factory(registry))


class OWSSecurity(object):

    def __init__(self, tokenstore, servicestore):
        self.tokenstore = tokenstore
        self.servicestore = servicestore

    def get_token_param(self, request):
        token = None
        if 'token' in request.params:
            token = request.params['token']   # in params
        elif 'access_token' in request.params:
            token = request.params['access_token']   # in params
        elif 'Access-Token' in request.headers:
            token = request.headers['Access-Token']  # in header
        else:  # in path
            elements = path_elements(request.path)
            if len(elements) > 1:  # there is always /ows/
                token = elements[-1]   # last path element
        return token

    def prepare_headers(self, request, access_token):
        if "esgf_access_token" in access_token.data or "esgf_credentials" in access_token.data:
            workdir = tempfile.mkdtemp(prefix=request.prefix, dir=request.workdir)
            if fetch_certificate(workdir=workdir, data=access_token.data):
                request.headers['X-Requested-Workdir'] = workdir
                request.headers['X-X509-User-Proxy'] = workdir + '/' + ESGF_CREDENTIALS
                LOGGER.debug("Prepared request headers.")
        return request

    def check_request(self, request):
        if request.path.startswith(protected_path):
            # TODO: fix this code
            try:
                service_name = parse_service_name(request.path)
                service = self.servicestore.fetch_by_name(service_name)
                is_public = service.public
                if service.public is True:
                    LOGGER.warn('public access for service %s', service_name)
            except ServiceNotFound:
                is_public = False
                LOGGER.warn("Service not registered.")
            ows_request = OWSRequest(request)
            if not ows_request.service_allowed():
                raise OWSInvalidParameterValue(
                    "service %s not supported" % ows_request.service, value="service")
            if not ows_request.public_access():
                try:
                    # try to get access_token ... if no access restrictions then don't complain.
                    token = self.get_token_param(request)
                    access_token = self.tokenstore.fetch_by_token(token)
                    if access_token.is_expired() and not is_public:
                        raise OWSAccessForbidden("Access token is expired.")
                    # update request with data from access token
                    # request.environ.update(access_token.data)
                    request = self.prepare_headers(request, access_token)
                except AccessTokenNotFound:
                    if not is_public:
                        raise OWSAccessForbidden("Access token is required to access this service.")
