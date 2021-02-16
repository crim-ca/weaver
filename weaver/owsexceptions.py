"""
OWSExceptions definitions.

Exceptions are based on :mod:`pyramid.httpexceptions` and :mod:`pywps.exceptions` to handle more cases where they can
be caught whether the running process is via :mod:`weaver` or through :mod:`pywps` service.

Furthermore, interrelation with :mod:`weaver.exceptions` classes (with base
:exception:`weaver.exceptions.WeaverException`) also employ specific :exception:`OWSExceptions` definitions to provide
specific error details.
"""
import json
import warnings
from string import Template
from typing import TYPE_CHECKING

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotAcceptable,
    HTTPNotFound,
    HTTPNotImplemented,
    HTTPOk,
)
from pyramid.interfaces import IExceptionResponse
from pyramid.response import Response
from pywps.exceptions import InvalidParameterValue, MissingParameterValue, NoApplicableCode
from webob.acceptparse import create_accept_header
from zope.interface import implementer

from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_XML
from weaver.utils import clean_json_text_body
from weaver.warning import MissingParameterWarning, UnsupportedOperationWarning

if TYPE_CHECKING:
    from weaver.typedefs import JSON, SettingsType


@implementer(IExceptionResponse)
class OWSException(Response, Exception):

    code = "NoApplicableCode"
    value = None
    locator = "NoApplicableCode"
    explanation = "Unknown Error"

    page_template = Template("""\
<?xml version="1.0" encoding="utf-8"?>
<ExceptionReport version="1.0.0"
    xmlns="http://www.opengis.net/ows/1.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd">
    <Exception exceptionCode="${code}" locator="${locator}">
        <ExceptionText>${message}</ExceptionText>
    </Exception>
</ExceptionReport>""")

    def __init__(self, detail=None, value=None, **kw):
        status = kw.pop("status", None)
        if isinstance(status, type) and issubclass(status, HTTPException):
            status = status().status
        elif isinstance(status, str):
            try:
                int(status.split()[0])
            except Exception:
                raise ValueError("status specified as string must be of format '<code> <title>'")
        elif isinstance(status, HTTPException):
            status = status.status
        elif not status:
            status = HTTPOk().status
        Response.__init__(self, status=status, **kw)
        Exception.__init__(self, detail)
        self.message = detail or self.explanation
        self.content_type = CONTENT_TYPE_TEXT_XML
        value = kw.get("locator", value)
        if value:
            self.locator = value

    def __str__(self, skip_body=False):
        return self.message

    def __repr__(self):
        if self.message:
            return "{}{}".format(type(self), self.message)
        return str(type(self))

    @staticmethod
    def json_formatter(status, body, title, environ):  # noqa: F811
        # type: (str, str, str, SettingsType) -> JSON
        body = clean_json_text_body(body)
        return {"description": body, "code": int(status.split()[0]), "status": status, "title": title}

    def prepare(self, environ):
        if not self.body:
            accept_value = environ.get("HTTP_ACCEPT", "")
            accept = create_accept_header(accept_value)

            # Attempt to match xml or json, if those don't match, we will fall through to defaulting to xml
            match = accept.best_match([CONTENT_TYPE_TEXT_XML, CONTENT_TYPE_APP_JSON])

            if match == CONTENT_TYPE_APP_JSON:
                self.content_type = CONTENT_TYPE_APP_JSON

                # json exception response should not have status 200
                if self.status_code == HTTPOk.code:
                    self.status = HTTPInternalServerError.code

                class JsonPageTemplate(object):
                    def __init__(self, excobj):
                        self.excobj = excobj

                    def substitute(self, code, locator, message):
                        status = self.excobj.status
                        data = self.excobj.json_formatter(status=status, body=message, title=None, environ=environ)
                        data["exception"] = {
                            "code": code or "",
                            "locator": locator or "",
                            "message": message or "",
                        }
                        return json.dumps(data)

                page_template = JsonPageTemplate(self)

            else:
                self.content_type = CONTENT_TYPE_TEXT_XML
                page_template = self.page_template

            args = {
                "code": self.code,
                "locator": self.locator,
                "message": self.message or "",
            }
            page = page_template.substitute(**args)
            if isinstance(page, str):
                page = page.encode(self.charset if self.charset else "UTF-8")
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
    code = "AccessForbidden"
    locator = ""
    explanation = "Access to this service is forbidden."

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPForbidden
        super(OWSAccessForbidden, self).__init__(*args, **kwargs)


class OWSNotFound(OWSException):
    code = "NotFound"
    locator = ""
    explanation = "Resource does not exist."

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPNotFound
        super(OWSNotFound, self).__init__(*args, **kwargs)


class OWSNotAcceptable(OWSException):
    code = "NotAcceptable"
    locator = ""
    explanation = "Cannot produce requested Accept format."

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPNotAcceptable
        super(OWSNotAcceptable, self).__init__(*args, **kwargs)


class OWSNoApplicableCode(OWSException, NoApplicableCode):
    """WPS Bad Request Exception"""
    code = "NoApplicableCode"
    locator = ""
    explanation = "Undefined error"

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPInternalServerError
        super(OWSNoApplicableCode, self).__init__(*args, **kwargs)
        warnings.warn(self.message, UnsupportedOperationWarning)


class OWSMissingParameterValue(OWSException, MissingParameterValue):
    """MissingParameterValue WPS Exception"""
    code = "MissingParameterValue"
    locator = ""
    explanation = "Parameter value is missing"

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPBadRequest
        super(OWSMissingParameterValue, self).__init__(*args, **kwargs)
        warnings.warn(self.message, MissingParameterWarning)


class OWSInvalidParameterValue(OWSException, InvalidParameterValue):
    """InvalidParameterValue WPS Exception"""
    code = "InvalidParameterValue"
    locator = ""
    explanation = "Parameter value is not acceptable."

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPBadRequest
        super(OWSInvalidParameterValue, self).__init__(*args, **kwargs)
        warnings.warn(self.message, UnsupportedOperationWarning)


class OWSNotImplemented(OWSException):
    code = "NotImplemented"
    locator = ""
    explanation = "Operation is not implemented."

    def __init__(self, *args, **kwargs):
        kwargs["status"] = HTTPNotImplemented
        super(OWSNotImplemented, self).__init__(*args, **kwargs)
        warnings.warn(self.message, UnsupportedOperationWarning)
