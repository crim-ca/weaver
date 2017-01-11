"""
OWSExceptions are based on pyramid.httpexceptions.

See also: https://github.com/geopython/pywps/blob/master/pywps/exceptions.py
"""


from string import Template

from zope.interface import implementer

from webob import html_escape as _html_escape

from pyramid.interfaces import IExceptionResponse
from pyramid.response import Response


@implementer(IExceptionResponse)
class OWSException(Response, Exception):

    code = 'NoApplicableCode'
    value = None
    locator = 'NoApplicableCode'
    explanation = 'Unknown Error'

    page_template = Template('''\
<?xml version="1.0" encoding="utf-8"?>
<ExceptionReport version="1.0.0"
    xmlns="http://www.opengis.net/ows/1.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd">
    <Exception exceptionCode="${code}" locator="${locator}">
        <ExceptionText>${message}</ExceptionText>
    </Exception>
</ExceptionReport>''')

    def __init__(self, detail=None, value=None, **kw):
        Response.__init__(self, status='200 OK', **kw)
        Exception.__init__(self, detail)
        self.message = detail or self.explanation
        if value:
            self.locator = value

    def __str__(self):
        return self.message

    def prepare(self, environ):
        if not self.body:
            self.content_type = 'text/xml'
            args = {
                'code': _html_escape(self.code),
                'locator': _html_escape(self.locator),
                'message': _html_escape(self.message or ''),
            }
            page = self.page_template.substitute(args)
            page = page.encode(self.charset)
            self.app_iter = [page]
            self.body = page

    @property
    def wsgi_response(self):
        # bw compat only
        return self

    exception = wsgi_response  # bw compat only

    def __call__(self, environ, start_response):
        # differences from webob.exc.WSGIHTTPException
        #
        # - does not try to deal with HEAD requests
        #
        # - does not manufacture a new response object when generating
        #   the default response
        #
        self.prepare(environ)
        return Response.__call__(self, environ, start_response)


class OWSAccessForbidden(OWSException):
    locator = "AccessForbidden"
    explanation = "Access to this service is forbidden"


class OWSAccessFailed(OWSException):
    locator = "NotAcceptable"
    explanation = "Access to this service failed"


class OWSNoApplicableCode(OWSException):
    pass


class OWSMissingParameterValue(OWSException):
    """MissingParameterValue WPS Exception"""
    code = "MissingParameterValue"
    locator = ""
    explanation = "Parameter value is missing"


class OWSInvalidParameterValue(OWSException):
    """InvalidParameterValue WPS Exception"""
    code = "InvalidParameterValue"
    locator = ""
    explanation = "Parameter value is invalid"
