import tempfile
from twitcher.owsexceptions import OWSAccessForbidden
from twitcher.utils import parse_service_name
from twitcher.esgf import fetch_certificate, ESGF_CREDENTIALS
from twitcher.datatype import Service
from magpie.services import service_factory
from magpie.models import Service
from magpie.api_except import evaluate_call, verify_param
from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound
from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy

import logging
LOGGER = logging.getLogger("TWITCHER")


class MagpieOWSSecurity(object):

    def prepare_headers(self, request, access_token):
        if "esgf_access_token" in access_token.data or "esgf_credentials" in access_token.data:
            workdir = tempfile.mkdtemp(prefix=request.prefix, dir=request.workdir)
            if fetch_certificate(workdir=workdir, data=access_token.data):
                request.headers['X-Requested-Workdir'] = workdir
                request.headers['X-X509-User-Proxy'] = workdir + '/' + ESGF_CREDENTIALS
                LOGGER.debug("Prepared request headers.")
        return request

    def check_request(self, request):
        twitcher_protected_path = request.registry.settings.get('twitcher.ows_proxy_protected_path', '/ows')
        if request.path.startswith(twitcher_protected_path):
            service_name = parse_service_name(request.path, twitcher_protected_path)
            service = evaluate_call(lambda: Service.by_service_name(service_name, db_session=request.db),
                                    fallback=lambda: request.db.rollback(),
                                    httpError=HTTPForbidden, msgOnFail="Service query by name refused by db")
            verify_param(service, notNone=True, httpError=HTTPNotFound, msgOnFail="Service name not found in db")

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
