"""
The OWSRequest is based on pywps code:

* https://github.com/geopython/pywps/tree/pywps-3.2/pywps/Parser
* https://github.com/geopython/pywps/blob/master/pywps/app/WPSRequest.py
"""

import lxml.etree

from pyramid.httpexceptions import HTTPBadRequest
from twitcher.owsexceptions import (OWSNoApplicableCode,
                                    OWSInvalidParameterValue,
                                    OWSMissingParameterValue)
from twitcher.utils import lxml_strip_ns

import logging
logger = logging.getLogger(__name__)

allowed_ows_services = ('wps', 'wms', 'wcs', 'wfs')
allowed_request_types = ('getcapabilities', 'describeprocess', 'execute')
allowed_versions = ('1.0.0')

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

    @property
    def version(self):
        return self.parser.params['version']


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
        self._get_service()
        self._get_request_type()
        self._get_version()
        return self.params

    def _get_service(self):
        raise NotImplementedError 

    def _get_request_type(self):
        raise NotImplementedError

    def _get_version(self):
        raise NotImplementedError 
    
class Get(OWSParser):

    def _get_param(self, param, allowed_values=None, optional=False):
        """Get parameter in GET request."""
        if param in self.request.params:
            value = self.request.params[param].lower()
            if not allowed_values is None:
                if value in allowed_values:
                    self.params[param] = value
                else:
                    raise OWSInvalidParameterValue("%s %s is not supported" % (param, value), value=param)
        elif optional:
            self.params[param] = None
        else:
            raise OWSMissingParameterValue('Parameter "%s" is missing' % param, value=param)            
        return self.params[param]
    

    def _get_service(self):
        """Check mandatory service name parameter in GET request."""
        return self._get_param(param="service", allowed_values=allowed_ows_services)


    def _get_request_type(self):
        """Find requested request type in GET request."""
        return self._get_param(param="request", allowed_values=allowed_request_types)


    def _get_version(self):
        """Find requested version in GET request."""
        version = self._get_param(param="version", allowed_values=allowed_versions, optional=True)
        if version is None and self._get_request_type() != "getcapabilities":
            raise OWSMissingParameterValue('Parameter "version" is missing', value="version")
        else:
            return version
        

       
class Post(OWSParser):

    def __init__(self, request):
        super(Post, self).__init__(request)
        
        try:
            self.document = lxml.etree.fromstring(self.request.body)
            lxml_strip_ns(self.document)
        except Exception as e:
            raise OWSNoApplicableCode(e.message)

        
    def _get_service(self):
        """Check mandatory service name parameter in POST request."""
        if "service" in self.document.attrib:
            value = self.document.attrib["service"].lower()
            if value in allowed_ows_services:
                self.params["service"] = value
            else:
                raise OWSInvalidParameterValue("Service %s is not supported" % value, value="service")
        else:
            raise OWSMissingParameterValue('Parameter "service" is missing', value="service")
        return self.params["service"]

    
    def _get_request_type(self):
        """Find requested request type in POST request."""
        value = self.document.tag.lower()
        if value in allowed_request_types:
            self.params["request"] = value
        else:
            raise OWSInvalidParameterValue("Request type %s is not supported" % value, value="request")
        return self.params["request"]


    def _get_version(self):
        """Find requested version in POST request."""
        if "version" in self.document.attrib:
            value = self.document.attrib["version"].lower()
            if value in allowed_versions:
                self.params["version"] = value
            else:
                raise OWSInvalidParameterValue("Version %s is not supported" % value, value="version")
        elif self._get_request_type() == "getcapabilities":
            self.params["version"] = None
        else:
            raise OWSMissingParameterValue('Parameter "version" is missing', value="version")
        return self.params["version"]
    
