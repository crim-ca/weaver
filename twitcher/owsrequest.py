"""
The OWSRequest is based on pywps code:

* https://github.com/geopython/PyWPS/tree/master/pywps/Parser
* https://github.com/jachym/pywps-4/blob/master/pywps/app/WPSRequest.py
"""

from pyramid.httpexceptions import HTTPBadRequest
from twitcher.owsexceptions import OWSInvalidParameterValue, OWSMissingParameterValue

allowed_ows_services = ('wps', 'wms', 'wcs', 'wfs')
allowed_request_types = ('getcapabilities', 'describeprocess', 'execute')

class OWSRequest(object):
    """
    ``OWSRequest`` parses on OWS request and provides methods to access the parameters.
    """

    def __init__(self, request):
        self.parser = ows_parser_factory(request)
        self.parser.parse()

    @property
    def service(self):
        return self.parser.params['service']

    @property
    def request(self):
        return self.parser.params['request']


def ows_parser_factory(request):
    if request.method == 'GET':
        return Get(request)
    elif request.method == 'POST':
        return Post(request)
    else:
        raise HTTPBadRequest()
        
class OWSParser(object):

    def __init__(self, request):
        self.request = request
        self.params = {}

    def parse(self):
        pass
    
class Get(OWSParser):

    def parse(self):
        self._get_service()
        self._get_request_type()
        return self.params


    def _get_service(self):
        """Check mandatory service name parameter."""
        if "service" in self.request.params:
            value = self.request.params["service"].lower()
            if value in allowed_ows_services:
                self.params["service"] = value
            else:
                raise OWSInvalidParameterValue("Service %s is not supported" % value, value="service")
        else:
            raise OWSMissingParameterValue('Parameter "service" is missing', value="service")
        return self.params["service"]


    def _get_request_type(self):
        """Find requested request type."""
        if "request" in self.request.params:
            value = self.request.params["request"].lower()
            if value in allowed_request_types:
                self.params["request"] = value
            else:
                raise OWSInvalidParameterValue("Request type %s is not supported" % value, value="request")
        else:
            raise OWSMissingParameterValue('Parameter "request" is missing', value="request")
        return self.params["request"]

       
       
class Post(OWSParser):
    pass

