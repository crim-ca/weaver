"""
pywps wrapper
"""

from pyramid.view import view_config, view_defaults
from pyramid.httpexceptions import HTTPBadRequest

import pywps
from pywps.Exceptions import WPSException
from twitcher.owsexceptions import OWSNoApplicableCode

import logging
logger = logging.getLogger(__name__)

@view_defaults(renderer='string')
class PyWPSWrapper(object):
    def __init__(self, request):
        self.request = request
        self.response = request.response

    @view_config(route_name='wps')
    @view_config(route_name='wps_secured')
    def pywps(self):
        """
        TODO: add xml response renderer
        TODO: fix exceptions ... use OWSException (raise ...)
        """
        self.response.status = "200 OK"
        self.response.content_type = "text/xml"

        inputQuery = None
        if self.request.method == "GET":
            inputQuery = self.request.query_string
        elif self.request.method == "POST":
            inputQuery = self.request.body_file_raw
        else:
            return HTTPBadRequest()

        if not inputQuery:
            return OWSNoApplicableCode("No query string found.")

        # create the WPS object
        try:
            wps = pywps.Pywps(self.request.method)
            if wps.parseRequest(inputQuery):
                pywps.debug(wps.inputs)
                return wps.performRequest()
        except WPSException,e:
            return e
        except Exception, e:
            return OWSNoApplicablCode(e.message)

def includeme(config):
    config.add_route('wps', '/ows/wps')
    config.add_route('wps_secured', '/ows/wps/{access_token}')



