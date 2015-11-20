"""
pywps wrapper
"""

from pyramid.view import view_config, view_defaults

import pywps
from pywps.Exceptions import WPSException, NoApplicableCode

@view_defaults(permission='view')
class PyWPSWrapper(object):
    def __init__(self, request):
        self.request = request
        self.response = self.request.response

    @view_config(route_name='wps', renderer='string')
    def pywps(self):
        """
        TODO: add xml response renderer
        TODO: fix exceptions
        """
        self.response.status = "200 OK"
        self.response.content_type = "text/xml"

        # TODO: is this the right way for get/post?
        inputQuery = None
        if self.request.method == "GET":
            inputQuery = self.request.query_string
        elif "wsgi.input" in self.request.params:
            inputQuery = self.request.params['wsgi.input']

        if not inputQuery:
            err =  NoApplicableCode("No query string found.")
            return [err.getResponse()]

        # create the WPS object
        try:
            wps = pywps.Pywps(self.request.method)
            if wps.parseRequest(inputQuery):
                pywps.debug(wps.inputs)
                return wps.performRequest()
        except WPSException,e:
            return [e]
        except Exception, e:
            return [e]

def includeme(config):
    config.add_route('wps', '/ows/wps')



