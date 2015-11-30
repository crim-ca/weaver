from twitcher.owsexceptions import OWSAccessForbidden
from twitcher.utils import path_elements

class OWSSecurity(object):

    def __init__(self):
        pass

    
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
