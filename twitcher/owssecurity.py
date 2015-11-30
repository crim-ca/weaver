from twitcher.exceptions import AccessTokenNotFound
from twitcher.owsexceptions import OWSAccessForbidden, OWSInvalidParameterValue
from twitcher.utils import path_elements
from twitcher.tokens import tokenstore_factory
from twitcher.owsrequest import OWSRequest


allowed_service_types = ('wps',)
allowed_request_types = ('getcapabilities', 'describeprocess')
protected_path = '/ows/'

def owssecurity_factory(registry):
    return OWSSecurity(tokenstore_factory(registry))


class OWSSecurity(object):

    def __init__(self, tokenstore):
        self.tokenstore = tokenstore

    
    def get_token(self, request):
        token = None
        if 'access_token' in request.params:
            token = request.params['access_token']   # in params
        elif 'Access-Token' in request.headers:
            token = request.headers['Access-Token']  # in header
        else:  # in path
            elements = path_elements(request.path)
            if len(elements) > 1: # there is always /ows/
                token = elements[-1]   # last path element

        if token is None:
            raise OWSAccessForbidden("You need to provide an access token to use this service.")
        return token

    
    def validate_token(self, token):
        try: 
            access_token = self.tokenstore.fetch_by_token(token)
            if not access_token or not access_token.is_valid():
                raise OWSAccessForbidden("Access token is invalid.")
        except AccessTokenNotFound as e:
            raise OWSAccessForbidden("Access token not found.")
        else:
            return access_token


    def check_request(self, request):
        if request.path.startswith(protected_path):
            ows_request = OWSRequest(request)
            if not ows_request.service in allowed_service_types:
                raise OWSInvalidParameterValue(
                    "service %s not supported" % ows_request.service, value="service")
            if not ows_request.request in allowed_request_types:
                token = self.get_token(request)
                access_token = self.validate_token(token)
                # update request with user environ from access token
                request.environ.update( access_token.user_environ )
        
