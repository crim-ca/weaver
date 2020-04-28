import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from beaker.cache import cache_region
from cornice.service import get_services
from cornice_swagger import CorniceSwagger
from pyramid.authentication import Authenticated, IAuthenticationPolicy
from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import (
    HTTPException,
    HTTPForbidden,
    HTTPMethodNotAllowed,
    HTTPNotFound,
    HTTPOk,
    HTTPServerError,
    HTTPUnauthorized
)
from pyramid.renderers import render_to_response
from pyramid.request import Request
from pyramid.response import Response
from pyramid.settings import asbool
from simplejson import JSONDecodeError

from weaver import __meta__
from weaver.formats import (
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_TEXT_HTML,
    CONTENT_TYPE_TEXT_PLAIN,
    CONTENT_TYPE_TEXT_XML,
    OUTPUT_FORMAT_JSON
)
from weaver.owsexceptions import OWSException
from weaver.utils import get_header, get_settings, get_weaver_url
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_extras import CustomTypeConversionDispatcher
from weaver.wps_restapi.utils import get_wps_restapi_base_url, wps_restapi_base_path

if TYPE_CHECKING:
    from typing import Optional
    from weaver.typedefs import JSON, SettingsType

LOGGER = logging.getLogger(__name__)


@sd.api_frontpage_service.get(tags=[sd.TAG_API], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.FrontpageEndpoint(), response_schemas=sd.get_api_frontpage_responses)
def api_frontpage(request):
    """Frontpage of Weaver."""
    settings = get_settings(request)
    return api_frontpage_body(settings)


@cache_region("doc", sd.api_frontpage_service.name)
def api_frontpage_body(settings):
    # type: (SettingsType) -> JSON
    """Generates the JSON body describing the Weaver API and documentation references."""

    # import here to avoid circular import errors
    from weaver.config import get_weaver_configuration

    weaver_url = get_weaver_url(settings)
    weaver_config = get_weaver_configuration(settings)

    weaver_api = asbool(settings.get("weaver.wps_restapi"))
    weaver_api_url = get_wps_restapi_base_url(settings) if weaver_api else None
    weaver_api_def = weaver_api_url + sd.api_swagger_ui_service.path if weaver_api else None
    weaver_api_doc = settings.get("weaver.wps_restapi_doc", None) if weaver_api else None
    weaver_api_ref = settings.get("weaver.wps_restapi_ref", None) if weaver_api else None
    weaver_wps = asbool(settings.get("weaver.wps"))
    weaver_wps_url = get_wps_url(settings) if weaver_wps else None
    weaver_conform_url = weaver_url + sd.api_conformance_service.path
    weaver_process_url = weaver_url + sd.processes_service.path
    weaver_links = [
        {"href": weaver_url, "rel": "self", "type": CONTENT_TYPE_APP_JSON, "title": "This document"},
        {"href": weaver_conform_url, "rel": "conformance", "type": CONTENT_TYPE_APP_JSON,
         "title": "WPS 2.0/3.0 REST-JSON Binding Extension conformance classes implemented by this service."},
    ]
    if weaver_api_def:
        weaver_links.append({"href": weaver_api_def, "rel": "service", "type": CONTENT_TYPE_APP_JSON,
                             "title": "OpenAPI schema specification of this service."})
    if weaver_api:
        weaver_links.extend([
            {"href": weaver_api_url,
             "rel": "service", "type": CONTENT_TYPE_APP_JSON,
             "title": "WPS REST API endpoint of this service."},
            {"href": weaver_api_def,
             "rel": "OpenAPI", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "WPS REST API definition of this service."},
            {"href": weaver_process_url,
             "rel": "processes", "type": CONTENT_TYPE_APP_JSON,
             "title": "Processes offered by this service."}
        ])
        if weaver_api_ref:
            # sample:
            #   https://app.swaggerhub.com/apis/geoprocessing/WPS/
            weaver_links.append({"href": weaver_api_ref, "rel": "reference", "type": CONTENT_TYPE_APP_JSON,
                                 "title": "API reference specification of this service."})
        if isinstance(weaver_api_doc, str):
            # sample:
            #   https://raw.githubusercontent.com/opengeospatial/wps-rest-binding/develop/docs/18-062.pdf
            if "." in weaver_api_doc:  # pylint: disable=E1135,unsupported-membership-test
                ext_type = weaver_api_doc.split(".")[-1]
                doc_type = "application/{}".format(ext_type)
            else:
                doc_type = CONTENT_TYPE_TEXT_PLAIN  # default most basic type
            weaver_links.append({"href": weaver_api_doc, "rel": "documentation", "type": doc_type,
                                 "title": "API reference documentation about this service."})
    if weaver_wps:
        weaver_links.extend([
            {"href": weaver_wps,
             "rel": "wps", "type": CONTENT_TYPE_TEXT_XML,
             "title": "WPS 1/2 endpoint of this service."},
            {"href": "http://docs.opengeospatial.org/is/14-065/14-065.html",
             "rel": "wps-xml-specification", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "WPS 1/2 definition of this service."},
            {"href": "http://schemas.opengis.net/wps/",
             "rel": "wps-xml-schema", "type": CONTENT_TYPE_TEXT_XML,
             "title": "WPS 1/2 XML validation schemas."}
        ])
    return {
        "message": "Weaver Information",
        "configuration": weaver_config,
        "parameters": [
            {"name": "api", "enabled": weaver_api,
             "url": weaver_api_url,
             "api": weaver_api_def},
            {"name": "wps", "enabled": weaver_wps,
             "url": weaver_wps_url},
        ],
        "links": weaver_links,
    }


@sd.api_versions_service.get(tags=[sd.TAG_API], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.VersionsEndpoint(), response_schemas=sd.get_api_versions_responses)
def api_versions(request):  # noqa: F811
    # type: (Request) -> HTTPException
    """Weaver versions information."""
    weaver_info = {"name": "weaver", "version": __meta__.__version__, "type": "api"}
    return HTTPOk(json={"versions": [weaver_info]})


@sd.api_conformance_service.get(tags=[sd.TAG_API], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ConformanceEndpoint(), response_schemas=sd.get_api_conformance_responses)
def api_conformance(request):  # noqa: F811
    # type: (Request) -> HTTPException
    """Weaver specification conformance information."""
    # TODO: follow updates with https://github.com/geopython/pygeoapi/issues/198
    conformance = {"conformsTo": [
        # "http://www.opengis.net/spec/wfs-1/3.0/req/core",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/oas30",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/html",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/geojson",
        "http://schemas.opengis.net/wps/1.0.0/",
        "http://schemas.opengis.net/wps/2.0/",
        "http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/core",
        # "http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/oas30",
        # "http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/html"
        "https://github.com/opengeospatial/wps-rest-binding",
    ]}
    return HTTPOk(json=conformance)


def get_swagger_json(http_scheme="http", http_host="localhost", base_url=None, use_docstring_summary=True):
    # type: (str, str, Optional[str], bool) -> JSON
    """Obtains the JSON schema of weaver API from request and response views schemas.

    :param http_scheme: Protocol scheme to use for building the API base if not provided by base URL parameter.
    :param http_host: Hostname to use for building the API base if not provided by base URL parameter.
    :param base_url: Explicit base URL to employ of as API base instead of HTTP scheme/host parameters.
    :param use_docstring_summary:
        Setting that controls if function docstring should be used to auto-generate the summary field of responses.

    .. seealso::
        - :mod:`weaver.wps_restapi.swagger_definitions`
    """
    CorniceSwagger.type_converter = CustomTypeConversionDispatcher
    swagger = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    swagger.summary_docstrings = use_docstring_summary
    swagger_base_spec = {"schemes": [http_scheme]}

    if base_url:
        weaver_parsed_url = urlparse(base_url)
        swagger_base_spec["host"] = weaver_parsed_url.netloc
        swagger_base_path = weaver_parsed_url.path
    else:
        swagger_base_spec["host"] = http_host
        swagger_base_path = sd.api_frontpage_service.path
    swagger.swagger = swagger_base_spec
    swagger_json = swagger.generate(title=sd.API_TITLE, version=__meta__.__version__,
                                    base_path=swagger_base_path, openapi_spec=3)
    swagger_json["externalDocs"] = sd.API_DOCS
    return swagger_json


@sd.api_swagger_json_service.get(tags=[sd.TAG_API], renderer=OUTPUT_FORMAT_JSON,
                                 schema=sd.SwaggerJSONEndpoint(), response_schemas=sd.get_api_swagger_json_responses)
def api_swagger_json(request):  # noqa: F811
    # type: (Request) -> dict
    """weaver REST API schema generation in JSON format."""
    # obtain 'server' host and api-base-path, which doesn't correspond necessarily to the app's host and path
    # ex: 'server' adds '/weaver' with proxy redirect before API routes
    weaver_server_url = get_weaver_url(request)
    LOGGER.debug("Request app URL:   [%s]", request.url)
    LOGGER.debug("Weaver config URL: [%s]", weaver_server_url)
    # http_scheme=request.scheme, http_host=request.host
    return get_swagger_json(base_url=weaver_server_url, use_docstring_summary=True)


@sd.api_swagger_ui_service.get(tags=[sd.TAG_API],
                               schema=sd.SwaggerUIEndpoint(), response_schemas=sd.get_api_swagger_ui_responses)
def api_swagger_ui(request):
    """weaver REST API swagger-ui schema documentation (this page)."""
    json_path = wps_restapi_base_path(request.registry.settings) + sd.api_swagger_json_service.path
    json_path = json_path.lstrip("/")   # if path starts by '/', swagger-ui doesn't find it on remote
    data_mako = {"api_title": sd.API_TITLE, "api_swagger_json_path": json_path, "api_version": __meta__.__version__}
    return render_to_response("templates/swagger_ui.mako", data_mako, request=request)


def get_request_info(request, detail=None):
    # type: (Request, Optional[str]) -> JSON
    """Provided additional response details based on the request and execution stack on failure."""
    content = {u"route": str(request.upath_info), u"url": str(request.url), u"method": request.method}
    if isinstance(detail, str):
        content.update({"detail": detail})
    if hasattr(request, "exception"):
        # handle error raised simply by checking for 'json' property in python 3 when body is invalid
        has_json = False
        try:
            has_json = hasattr(request.exception, "json")
        except JSONDecodeError:
            pass
        if has_json and isinstance(request.exception.json, dict):
            content.update(request.exception.json)
        elif isinstance(request.exception, HTTPServerError) and hasattr(request.exception, "message"):
            content.update({u"exception": str(request.exception.message)})
    elif hasattr(request, "matchdict"):
        if request.matchdict is not None and request.matchdict != "":
            content.update(request.matchdict)
    return content


def ows_json_format(function):
    """Decorator that adds additional detail in the response's JSON body if this is the returned content-type."""
    def format_response_details(response, request):
        # type: (Response, Request) -> HTTPException
        http_response = function(request)
        http_headers = get_header("Content-Type", http_response.headers) or []
        req_headers = get_header("Accept", request.headers) or []
        if any([CONTENT_TYPE_APP_JSON in http_headers, CONTENT_TYPE_APP_JSON in req_headers]):
            body = OWSException.json_formatter(http_response.status, response.message or "",
                                               http_response.title, request.environ)
            body["detail"] = get_request_info(request)
            http_response._json = body
        if http_response.status_code != response.status_code:
            raise http_response  # re-raise if code was fixed
        return http_response
    return format_response_details


@ows_json_format
def not_found_or_method_not_allowed(request):
    """
    Overrides the default is HTTPNotFound [404] by appropriate HTTPMethodNotAllowed [405] when applicable.

    Not found response can correspond to underlying process operation not finding a required item, or a completely
    unknown route (path did not match any existing API definition).
    Method not allowed is more specific to the case where the path matches an existing API route, but the specific
    request method (GET, POST, etc.) is not allowed on this path.

    Without this fix, both situations return [404] regardless.
    """
    path_methods = request.exception._safe_methods  # noqa: W0212
    if isinstance(request.exception, PredicateMismatch) and request.method not in path_methods:
        http_err = HTTPMethodNotAllowed
        http_msg = ""  # auto-generated by HTTPMethodNotAllowed
    else:
        http_err = HTTPNotFound
        http_msg = str(request.exception)
    return http_err(http_msg)


@ows_json_format
def unauthorized_or_forbidden(request):
    """
    Overrides the default is HTTPForbidden [403] by appropriate HTTPUnauthorized [401] when applicable.

    Unauthorized response is for restricted user access according to credentials and/or authorization headers.
    Forbidden response is for operation refused by the underlying process operations.

    Without this fix, both situations return [403] regardless.

    .. seealso::
        - http://www.restapitutorial.com/httpstatuscodes.html
    """
    authn_policy = request.registry.queryUtility(IAuthenticationPolicy)
    if authn_policy:
        principals = authn_policy.effective_principals(request)
        if Authenticated not in principals:
            return HTTPUnauthorized("Unauthorized access to this resource.")
    return HTTPForbidden("Forbidden operation under this resource.")
