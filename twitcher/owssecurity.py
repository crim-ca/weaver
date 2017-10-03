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

#import sys
#sys.path.insert(0, '/home/deruefx/CrimProjects/PAVICS/Magpie')



from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy

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

            from magpie.services import service_factory
            from magpie.models import Service
            service_name = parse_service_name(request.path)
            service = Service.by_service_name(service_name, db_session=request.db) #fetch from the database

            service_specific = service_factory(service, request) #return a specific type of service, ex: ServiceWPS with all the acl (loaded according to the service_type)
            #should contain all the acl, this the only thing important
            permission_requested = service_specific.permission_requested() #parse request (GET/POST) to get the permission requested for that service

            if permission_requested:
                authn_policy = request.registry.queryUtility(IAuthenticationPolicy)
                authz_policy = request.registry.queryUtility(IAuthorizationPolicy)
                principals = authn_policy.effective_principals(request)
                has_permission = authz_policy.permits(service_specific, principals, permission_requested)
                if not has_permission:
                    raise OWSAccessForbidden("Not authorized to access this resource.")
