import tempfile

from twitcher.store.base import AccessTokenStore, ServiceStore
from twitcher.exceptions import AccessTokenNotFound
from twitcher.exceptions import ServiceNotFound
from twitcher.owsexceptions import OWSAccessForbidden, OWSInvalidParameterValue
from twitcher.utils import path_elements
from twitcher.utils import parse_service_name
from twitcher.owsrequest import OWSRequest
from twitcher.esgf import fetch_certificate, ESGF_CREDENTIALS
from twitcher.datatype import Service

import logging
LOGGER = logging.getLogger("TWITCHER")


def verify_cert(request):
    if not request.headers.get('X-Ssl-Client-Verify', '') == 'SUCCESS':
        raise OWSAccessForbidden("A valid X.509 client certificate is needed.")


class OWSSecurityInterface(object):

    def check_request(self, request):
        raise NotImplementedError

    @staticmethod
    def get_token_param(request):
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

    @staticmethod
    def prepare_headers(request, access_token):
        if "esgf_access_token" in access_token.data or "esgf_credentials" in access_token.data:
            workdir = tempfile.mkdtemp(prefix=request.prefix, dir=request.workdir)
            if fetch_certificate(workdir=workdir, data=access_token.data):
                request.headers['X-Requested-Workdir'] = workdir
                request.headers['X-X509-User-Proxy'] = workdir + '/' + ESGF_CREDENTIALS
                LOGGER.debug("Prepared request headers.")
        return request


class OWSSecurity(OWSSecurityInterface):

    def __init__(self, tokenstore, servicestore):
        # type: (AccessTokenStore, ServiceStore) -> None
        super(OWSSecurity, self).__init__()
        self.tokenstore = tokenstore
        self.servicestore = servicestore

    def verify_access(self, request, service):
        # TODO: public service access handling is confusing.
        try:
            if service.auth == 'cert':
                verify_cert(request)
            else:  # token
                self._verify_access_token(request)
        except OWSAccessForbidden:
            if not service.public:
                raise

    def _verify_access_token(self, request):
        try:
            # try to get access_token ... if no access restrictions then don't complain.
            token = self.get_token_param(request)
            access_token = self.tokenstore.fetch_by_token(token)
            if access_token.is_expired():
                raise OWSAccessForbidden("Access token is expired.")
            # update request with data from access token
            # request.environ.update(access_token.data)
            # TODO: is this really the way we want to do this?
            request = self.prepare_headers(request, access_token)
        except AccessTokenNotFound:
            raise OWSAccessForbidden("Access token is required to access this service.")

    def check_request(self, request):
        protected_path = request.registry.settings.get('twitcher.ows_proxy_protected_path', '/ows')
        if request.path.startswith(protected_path):
            # TODO: refactor this code
            try:
                service_name = parse_service_name(request.path, protected_path)
                service = self.servicestore.fetch_by_name(service_name, request=request)
                if service.public is True:
                    LOGGER.warn('public access for service %s', service_name)
            except ServiceNotFound:
                # TODO: why not raising an exception?
                service = Service(url='unregistered', name='unregistered', public=False, auth='token')
                LOGGER.warn("Service not registered.")
            ows_request = OWSRequest(request)
            if not ows_request.service_allowed():
                raise OWSInvalidParameterValue(
                    "service %s not supported" % ows_request.service, value="service")
            if not ows_request.public_access():
                self.verify_access(request, service)
