import json
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
from weaver.wps_restapi.colander_extras import OAS3TypeConversionDispatcher
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
    weaver_api_spec = weaver_api_url + sd.openapi_json_service.path if weaver_api else None
    weaver_wps = asbool(settings.get("weaver.wps"))
    weaver_wps_url = get_wps_url(settings) if weaver_wps else None
    weaver_conform_url = weaver_url + sd.api_conformance_service.path
    weaver_process_url = weaver_url + sd.processes_service.path
    weaver_links = [
        {"href": weaver_url, "rel": "self", "type": CONTENT_TYPE_APP_JSON, "title": "This document"},
        {"href": weaver_conform_url, "rel": "conformance", "type": CONTENT_TYPE_APP_JSON,
         "title": "WPS conformance classes implemented by this service."},
    ]
    if weaver_api:
        weaver_links.extend([
            {"href": weaver_api_url,
             "rel": "service", "type": CONTENT_TYPE_APP_JSON,
             "title": "WPS REST API endpoint of this service."},
            {"href": weaver_api_def,
             "rel": "swagger-ui", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "WPS REST API definition of this service."},
            {"href": weaver_api_spec,
             "rel": "OpenAPI", "type": CONTENT_TYPE_APP_JSON,
             "title": "WPS REST API specification of this service."},
            {"href": weaver_process_url,
             "rel": "processes", "type": CONTENT_TYPE_APP_JSON,
             "title": "Processes offered by this service."},
            {"href": sd.OGC_API_REPO_URL,
             "rel": "ogcapi-processes-repository", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "OGC-API - Processes schema definitions repository."},
            {"href": sd.CWL_BASE_URL,
             "rel": "cwl-home", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "Common Workflow Language (CWL) homepage."},
            {"href": sd.CWL_REPO_URL,
             "rel": "cwl-repository", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "Common Workflow Language (CWL) repositories."},
            {"href": sd.CWL_SPEC_URL,
             "rel": "cwl-specification", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "Common Workflow Language (CWL) specification."},
            {"href": sd.CWL_USER_GUIDE_URL,
             "rel": "cwl-user-guide", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "Common Workflow Language (CWL) user guide."},
            {"href": sd.CWL_CMD_TOOL_URL,
             "rel": "cwl-command-line-tool", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "Common Workflow Language (CWL) CommandLineTool specification."},
            {"href": sd.CWL_WORKFLOW_URL,
             "rel": "cwl-workflow", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "Common Workflow Language (CWL) Workflow specification."},
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
            {"href": weaver_wps_url,
             "rel": "wps", "type": CONTENT_TYPE_TEXT_XML,
             "title": "WPS 1.0.0/2.0 XML endpoint of this service."},
            {"href": "http://docs.opengeospatial.org/is/14-065/14-065.html",
             "rel": "wps-specification", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "WPS 1.0.0/2.0 definition of this service."},
            {"href": "http://schemas.opengis.net/wps/",
             "rel": "wps-schema-repository", "type": CONTENT_TYPE_TEXT_HTML,
             "title": "WPS 1.0.0/2.0 XML schemas repository."},
            {"href": "http://schemas.opengis.net/wps/1.0.0/wpsAll.xsd",
             "rel": "wps-schema-1", "type": CONTENT_TYPE_TEXT_XML,
             "title": "WPS 1.0.0 XML validation schemas entrypoint."},
            {"href": "http://schemas.opengis.net/wps/2.0/wps.xsd",
             "rel": "wps-schema-2", "type": CONTENT_TYPE_TEXT_XML,
             "title": "WPS 2.0 XML validation schemas entrypoint."},
        ])
    return {
        "message": "Weaver Information",
        "configuration": weaver_config,
        "description": __meta__.__description__,
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
        "https://github.com/opengeospatial/wps-rest-binding",  # old reference for bw-compat
        # see ogcapi-processes schemas details:
        #   https://github.com/opengeospatial/ogcapi-processes
        # see other references:
        #   https://github.com/crim-ca/weaver/issues/53
        # https://htmlpreview.github.io/?https://github.com/opengeospatial/ogcapi-processes/blob/master/docs/18-062.html
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/ogc-process-description",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json",
        # FIXME: https://github.com/crim-ca/weaver/issues/210
        # "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/html",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/oas30",  # OpenAPI 3.0
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/job-list",
        # FIXME: https://github.com/crim-ca/weaver/issues/230
        # "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/callback",
        # FIXME: https://github.com/crim-ca/weaver/issues/228
        # "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/dismiss",

    ]}
    return HTTPOk(json=conformance)


def get_openapi_json(http_scheme="http", http_host="localhost", base_url=None,
                     use_refs=True, use_docstring_summary=True, settings=None):
    # type: (str, str, Optional[str], bool, bool, Optional[SettingsType]) -> JSON
    """Obtains the JSON schema of Weaver OpenAPI from request and response views schemas.

    :param http_scheme: Protocol scheme to use for building the API base if not provided by base URL parameter.
    :param http_host: Hostname to use for building the API base if not provided by base URL parameter.
    :param base_url: Explicit base URL to employ of as API base instead of HTTP scheme/host parameters.
    :param use_refs: Generate schemas with ``$ref`` definitions or expand every schema content.
    :param use_docstring_summary: Extra function docstring to auto-generate the summary field of responses.
    :param settings: Application settings to retrieve further metadata details to be added to the OpenAPI.

    .. seealso::
        - :mod:`weaver.wps_restapi.swagger_definitions`
    """
    CorniceSwagger.type_converter = OAS3TypeConversionDispatcher
    depth = -1 if use_refs else 0
    swagger = CorniceSwagger(get_services(), def_ref_depth=depth, param_ref=use_refs, resp_ref=use_refs)
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
    swagger_info = {
        "description": __meta__.__description__,
        "licence": {
            "name": __meta__.__license_type__,
            "url": "{}/blob/master/LICENSE.txt".format(__meta__.__source_repository__),
        }
    }
    if settings:
        for key in ["name", "email", "url"]:
            val = settings.get("weaver.wps_metadata_contact_{}".format(key))
            if val:
                swagger_info.setdefault("contact", {})
                swagger_info["contact"][key] = val
        abstract = settings.get("weaver.wps_metadata_identification_abstract")
        if abstract:
            swagger_info["description"] = "{}\n\n{}".format(abstract, __meta__.__description__)
        terms = settings.get("weaver.wps_metadata_identification_accessconstraints")
        if terms and "http" in terms:
            if "," in terms:
                terms = [term.strip() for term in terms.split(",")]
            else:
                terms = [terms]
            terms = [term for term in terms if "http" in term]
            if terms:
                swagger_info["termsOfService"] = terms[0]

    swagger_json = swagger.generate(title=sd.API_TITLE, version=__meta__.__version__, info=swagger_info,
                                    base_path=swagger_base_path, openapi_spec=3)
    swagger_json["externalDocs"] = sd.API_DOCS
    return swagger_json


@cache_region("doc", sd.openapi_json_service.name)
def openapi_json_cached(*args, **kwargs):
    return get_openapi_json(*args, **kwargs)


@sd.openapi_json_service.get(tags=[sd.TAG_API], renderer=OUTPUT_FORMAT_JSON,
                             schema=sd.OpenAPIEndpoint(), response_schemas=sd.get_openapi_json_responses)
def openapi_json(request):  # noqa: F811
    # type: (Request) -> dict
    """Weaver OpenAPI schema definitions."""
    # obtain 'server' host and api-base-path, which doesn't correspond necessarily to the app's host and path
    # ex: 'server' adds '/weaver' with proxy redirect before API routes
    settings = get_settings(request)
    weaver_server_url = get_weaver_url(settings)
    LOGGER.debug("Request app URL:   [%s]", request.url)
    LOGGER.debug("Weaver config URL: [%s]", weaver_server_url)
    return openapi_json_cached(base_url=weaver_server_url, use_docstring_summary=True, settings=settings)


@cache_region("doc", sd.api_swagger_ui_service.name)
def swagger_ui_cached(request):
    json_path = wps_restapi_base_path(request) + sd.openapi_json_service.path
    json_path = json_path.lstrip("/")   # if path starts by '/', swagger-ui doesn't find it on remote
    data_mako = {"api_title": sd.API_TITLE, "openapi_json_path": json_path, "api_version": __meta__.__version__}
    resp = render_to_response("templates/swagger_ui.mako", data_mako, request=request)
    return resp


@sd.api_openapi_ui_service.get(tags=[sd.TAG_API], schema=sd.SwaggerUIEndpoint(),
                               response_schemas=sd.get_api_swagger_ui_responses)
@sd.api_swagger_ui_service.get(tags=[sd.TAG_API], schema=sd.SwaggerUIEndpoint(),
                               response_schemas=sd.get_api_swagger_ui_responses)
def api_swagger_ui(request):
    """Weaver OpenAPI schema definitions rendering using Swagger-UI viewer."""
    return swagger_ui_cached(request)


@cache_region("doc", sd.api_redoc_ui_service.name)
def redoc_ui_cached(request):
    settings = get_settings(request)
    weaver_server_url = get_weaver_url(settings)
    spec = openapi_json_cached(base_url=weaver_server_url, settings=settings,
                               use_docstring_summary=True, use_refs=False)
    data_mako = {"openapi_spec": json.dumps(spec, ensure_ascii=False)}
    resp = render_to_response("templates/redoc_ui.mako", data_mako, request=request)
    return resp


@sd.api_redoc_ui_service.get(tags=[sd.TAG_API], schema=sd.RedocUIEndpoint(),
                             response_schemas=sd.get_api_redoc_ui_responses)
def api_redoc_ui(request):
    """Weaver OpenAPI schema definitions rendering using Redoc viewer."""
    return redoc_ui_cached(request)


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
