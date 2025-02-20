import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from beaker.cache import cache_region
from box import Box
from cornice.service import get_services
from pyramid.authentication import Authenticated, IAuthenticationPolicy
from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import (
    HTTPException,
    HTTPForbidden,
    HTTPFound,
    HTTPMethodNotAllowed,
    HTTPNotFound,
    HTTPOk,
    HTTPServerError,
    HTTPUnauthorized
)
from pyramid.renderers import render_to_response
from pyramid.request import Request as PyramidRequest
from pyramid.settings import asbool
from simplejson import JSONDecodeError

from weaver import __meta__
from weaver.formats import ContentType, OutputFormat, guess_target_format
from weaver.owsexceptions import OWSException
from weaver.utils import get_header, get_registry, get_settings, get_weaver_url
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_extras import CorniceOpenAPI
from weaver.wps_restapi.constants import ConformanceCategory
from weaver.wps_restapi.utils import get_wps_restapi_base_path, get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Any, Callable, List, Optional
    from typing_extensions import TypedDict

    from pyramid.config import Configurator
    from pyramid.registry import Registry

    from weaver.typedefs import (
        AnyRequestType,
        AnyResponseType,
        AnySettingsContainer,
        JSON,
        OpenAPISpecification,
        OpenAPISpecInfo,
        SettingsType,
        ViewHandler
    )
    from weaver.wps_restapi.constants import AnyConformanceCategory

    Conformance = TypedDict("Conformance", {
        "conformsTo": List[str]
    }, total=True)


LOGGER = logging.getLogger(__name__)


@cache_region("doc", sd.api_conformance_service.name)
def get_conformance(category, settings):
    # type: (Optional[AnyConformanceCategory], SettingsType) -> Conformance
    """
    Obtain the conformance references.

    .. seealso::
        - https://github.com/opengeospatial/ogcapi-common/tree/master/collections
        - https://github.com/opengeospatial/ogcapi-processes/tree/master/core
        - https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/deploy_replace_undeploy
        - https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/workflows

    .. seealso::
        - OGC API - Processes, Core document: https://docs.ogc.org/is/18-062r2/18-062r2.html
        - Best-Practices document: https://docs.ogc.org/bp/20-089r1.html
    """
    # pylint: disable=C0301,line-too-long  # many long comment links cannot be split

    ows_wps1 = "http://schemas.opengis.net/wps/1.0.0"
    ows_wps2 = "http://www.opengis.net/spec/WPS/2.0"
    ows_wps_enabled = asbool(settings.get("weaver.wps", True))
    ows_wps_conformance = [
        # "http://www.opengis.net/spec/wfs-1/3.0/req/core",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/oas30",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/html",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/geojson",
        f"{ows_wps1}/",
        f"{ows_wps2}/",
        f"{ows_wps2}/req/service/binding/rest-json/core",
        f"{ows_wps2}/req/service/binding/rest-json/oas30",  # /ows/wps?...&f=json
        # ows_wps2 + "/req/service/binding/rest-json/html"
    ] if ows_wps_enabled else []

    ogcapi_common = "http://www.opengis.net/spec/ogcapi-common-1/1.0"
    ogcapi_proc_core = "http://www.opengis.net/spec/ogcapi-processes-1/1.0"
    ogcapi_proc_part2 = "http://www.opengis.net/spec/ogcapi-processes-2/1.0"
    ogcapi_proc_part3 = "http://www.opengis.net/spec/ogcapi-processes-3/0.0"
    ogcapi_proc_part4 = "http://www.opengis.net/spec/ogcapi-processes-4/1.0"
    ogcapi_proc_apppkg = "http://www.opengis.net/spec/eoap-bp/1.0"
    # FIXME: https://github.com/crim-ca/weaver/issues/412
    # ogcapi_proc_part3 = "http://www.opengis.net/spec/ogcapi-processes-3/1.0"
    ogcapi_proc_enabled = asbool(settings.get("weaver.wps_restapi", True))
    ogcapi_proc_html = asbool(settings.get("weaver.wps_restapi_html", True))
    ogcapi_proc_prov = asbool(settings.get("weaver.cwl_prov", True))
    ogcapi_proc_conformance = ([
        f"{ogcapi_common}/conf/core",
        f"{ogcapi_common}/per/core/additional-link-relations",
        f"{ogcapi_common}/per/core/additional-status-codes",
        f"{ogcapi_common}/per/core/query-param-name-specified",
        f"{ogcapi_common}/per/core/query-param-name-tolerance",
        f"{ogcapi_common}/per/core/query-param-value-specified",
        f"{ogcapi_common}/per/core/query-param-value-tolerance",
        f"{ogcapi_common}/rec/core/cross-origin",
        # f"{ogcapi_common}/rec/core/etag",
    ] + ([
        f"{ogcapi_common}/rec/core/html",
    ] if ogcapi_proc_html else []) + [
        f"{ogcapi_common}/rec/core/json",
        f"{ogcapi_common}/rec/core/link-header",
        # FIXME: error details (for all below: https://github.com/crim-ca/weaver/issues/320)
        # ogcapi_common + "/rec/core/problem-details",
        # ogcapi_common + "/rec/core/query-param-capitalization",
        # ogcapi_common + "/rec/core/query-param-value-special",
        # FIXME: https://github.com/crim-ca/weaver/issues/112 (language/translate)
        # ogcapi_common + "/rec/core/string-i18n",
        f"{ogcapi_common}/req/collections",
        # ogcapi_common + "/req/collections/collection-definition",
        # ogcapi_common + "/req/collections/src-md-op",
        # ogcapi_common + "/req/collections/src-md-success",
        # ogcapi_common + "/req/collections/rc-bbox-collection-response",
        f"{ogcapi_common}/req/collections/rc-bbox-unsupported",
        f"{ogcapi_common}/req/collections/rc-datetime-collection-response",
        f"{ogcapi_common}/req/collections/rc-datetime-definition",
        f"{ogcapi_common}/req/collections/rc-datetime-unsupported",
        f"{ogcapi_common}/req/collections/rc-datetime-response",
        f"{ogcapi_common}/req/collections/rc-limit-unsupported",
        f"{ogcapi_common}/req/collections/rc-limit-collection-response",
        f"{ogcapi_common}/req/collections/rc-links",
        # FIXME: https://github.com/crim-ca/weaver/issues/318
        # ogcapi_common + "/rec/collections/rc-md-extent",
        # ogcapi_common + "/rec/collections/rc-md-extent-single",
        # ogcapi_common + "/rec/collections/rc-md-extent-extensions",
        # ogcapi_common + "/req/collections/rc-md-items",
        # ogcapi_common + "/rec/collections/rc-md-item-type",
        # ogcapi_common + "/rec/collections/rc-md-items-descriptions",
        # ogcapi_common + "/req/collections/rc-md-items-links",
        # ogcapi_common + "/rec/collections/rc-md-op",
        # ogcapi_common + "/rec/collections/rc-md-success",
        # ogcapi_common + "/req/collections/rc-numberMatched"
        # ogcapi_common + "/req/collections/rc-numberReturned"
        # ogcapi_common + "/req/collections/rc-op",
        # ogcapi_common + "/req/collections/rc-response",
        # ogcapi_common + "/req/collections/rc-subset-collection-response"
        # ogcapi_common + "/req/collections/rc-timeStamp",
        f"{ogcapi_common}/req/core/http",
        f"{ogcapi_common}/req/core/query-param-capitalization",
        f"{ogcapi_common}/req/core/query-param-list-delimiter",
        f"{ogcapi_common}/req/core/query-param-list-empty",
        f"{ogcapi_common}/req/core/query-param-list-escape",
        # ogcapi_common + "/req/core/query-param-name-unknown",
        f"{ogcapi_common}/req/core/query-param-value-boolean",
        f"{ogcapi_common}/req/core/query-param-value-decimal",
        f"{ogcapi_common}/req/core/query-param-value-double",
        f"{ogcapi_common}/req/core/query-param-value-integer",
        f"{ogcapi_common}/req/core/query-param-value-invalid",
        # FIXME: Following applicable if result output endpoint to offer content returned directly is added
        #   https://github.com/crim-ca/weaver/issues/18
        f"{ogcapi_common}/req/geojson",
        # ogcapi_common + "/req/geojson/content",
        # ogcapi_common + "/req/geojson/definition",
    ] + ([
        f"{ogcapi_common}/req/html",
        f"{ogcapi_common}/req/html/content",
        f"{ogcapi_common}/req/html/definition",
    ] if ogcapi_proc_html else []) + [
        f"{ogcapi_common}/req/json",
        f"{ogcapi_common}/req/json/content",
        f"{ogcapi_common}/req/json/definition",
        f"{ogcapi_common}/req/landing-page",
        f"{ogcapi_common}/req/oas30",  # OpenAPI 3.0
        # ogcapi_common + "/req/simple-query",
        # ogcapi_common + "/req/umd-collection",
        f"{ogcapi_proc_core}/conf/core",
        f"{ogcapi_proc_core}/conf/core/api-definition-op",
        f"{ogcapi_proc_core}/conf/core/api-definition-success",
        f"{ogcapi_proc_core}/conf/core/conformance-op",
        f"{ogcapi_proc_core}/conf/core/conformance-success",
        f"{ogcapi_proc_core}/conf/core/http",
        f"{ogcapi_proc_core}/conf/core/job-exception-no-such-job",
        f"{ogcapi_proc_core}/conf/core/job-op",
        f"{ogcapi_proc_core}/conf/core/job-result",
        f"{ogcapi_proc_core}/conf/core/job-results",
        f"{ogcapi_proc_core}/conf/core/job-results-async-many",
        # FIXME: https://github.com/crim-ca/weaver/issues/18
        # f"{ogcapi_proc_core}/conf/core/job-results-async-one",
        f"{ogcapi_proc_core}/conf/core/job-results-exception-no-such-job",
        f"{ogcapi_proc_core}/conf/core/job-results-exception-results-not-ready",
        f"{ogcapi_proc_core}/conf/core/job-results-failed",
        # FIXME: results 'outputs' query parameter (https://github.com/crim-ca/weaver/issues/733)
        # f"{ogcapi_proc_core}/conf/core/job-results-param-outputs",
        # f"{ogcapi_proc_core}/conf/core/job-results-param-outputs-empty",
        f"{ogcapi_proc_core}/conf/core/job-results-param-outputs-omit",
        f"{ogcapi_proc_core}/conf/core/job-results-param-outputs-response",
        f"{ogcapi_proc_core}/conf/core/job-results-success-sync",
        f"{ogcapi_proc_core}/conf/core/job-success",
        f"{ogcapi_proc_core}/conf/core/landingpage-op",
        f"{ogcapi_proc_core}/conf/core/landingpage-success",
        f"{ogcapi_proc_core}/conf/core/pl-limit-definition",
        f"{ogcapi_proc_core}/conf/core/pl-limit-response",
        f"{ogcapi_proc_core}/conf/core/pl-links",
        f"{ogcapi_proc_core}/conf/core/process-description",
        f"{ogcapi_proc_core}/conf/core/process-description-success",
        f"{ogcapi_proc_core}/conf/core/process-description-no-such-process",
        f"{ogcapi_proc_core}/conf/core/process-execute-auto-execution-mode",
        f"{ogcapi_proc_core}/conf/core/process-execute-default-execution-mode",
        f"{ogcapi_proc_core}/conf/core/process-execute-default-outputs",
        f"{ogcapi_proc_core}/conf/core/process-execute-input-array",
        f"{ogcapi_proc_core}/conf/core/process-execute-input-inline-bbox",
        f"{ogcapi_proc_core}/conf/core/process-execute-input-inline-binary",
        f"{ogcapi_proc_core}/conf/core/process-execute-input-inline-mixed",
        f"{ogcapi_proc_core}/conf/core/process-execute-input-inline-object",
        f"{ogcapi_proc_core}/conf/core/process-execute-input-validation",
        f"{ogcapi_proc_core}/conf/core/process-execute-inputs",
        f"{ogcapi_proc_core}/conf/core/process-execute-op",
        f"{ogcapi_proc_core}/conf/core/process-execute-request",
        f"{ogcapi_proc_core}/conf/core/process-execute-success-async",
        # FIXME: https://github.com/crim-ca/weaver/issues/18
        # f"{ogcapi_proc_core}/conf/core/process-execute-sync-one",
        f"{ogcapi_proc_core}/conf/core/process-execute-sync-default-content",
        f"{ogcapi_proc_core}/conf/core/process-execute-sync-many-json",
        f"{ogcapi_proc_core}/conf/core/process-list",
        f"{ogcapi_proc_core}/conf/core/process-list-op",
        f"{ogcapi_proc_core}/conf/core/process-list-success",
        f"{ogcapi_proc_core}/conf/core/process-summary-links",
        f"{ogcapi_proc_core}/conf/callback",
        f"{ogcapi_proc_core}/conf/callback/job-callback",
        f"{ogcapi_proc_core}/conf/dismiss",
    ] + ([
        f"{ogcapi_proc_core}/conf/html",
        f"{ogcapi_proc_core}/conf/html/content",
        f"{ogcapi_proc_core}/conf/html/definition",
    ] if ogcapi_proc_html else []) + [
        f"{ogcapi_proc_core}/conf/dismiss/job-dismiss-op",
        f"{ogcapi_proc_core}/conf/dismiss/job-dismiss-success",
        f"{ogcapi_proc_core}/conf/json",
        f"{ogcapi_proc_core}/conf/json/content",
        f"{ogcapi_proc_core}/conf/json/definition",
        f"{ogcapi_proc_core}/conf/job-list",
        # FIXME: KVP exec (https://github.com/crim-ca/weaver/issues/607, https://github.com/crim-ca/weaver/issues/445)
        # f"{ogcapi_proc_core}/conf/kvp-execute",
        f"{ogcapi_proc_core}/conf/oas30",
        # FIXME: https://github.com/crim-ca/weaver/issues/231
        #  List all supported requirements, recommendations and abstract tests
        f"{ogcapi_proc_core}/conf/ogc-process-description",
        f"{ogcapi_proc_core}/conf/ogc-process-description/links",
        f"{ogcapi_proc_core}/per/core/additional-status-codes",
        f"{ogcapi_proc_core}/per/core/alternative-process-description",
        f"{ogcapi_proc_core}/per/core/alternative-process-paths",
        f"{ogcapi_proc_core}/per/core/api-definition-uri",
        f"{ogcapi_proc_core}/per/core/process-execute-input-inline-bbox",
        f"{ogcapi_proc_core}/per/core/process-execute-sync-job",
        f"{ogcapi_proc_core}/per/core/limit-response",
        f"{ogcapi_proc_core}/per/core/limit-default-minimum-maximum",
        f"{ogcapi_proc_core}/per/core/prev",
        f"{ogcapi_proc_core}/per/job-list/limit-response",
        f"{ogcapi_proc_core}/per/job-list/prev",
        # f"{ogcapi_proc_core}/rec/core/access-control-expose-headers",
        f"{ogcapi_proc_core}/rec/core/api-definition-oas",
        f"{ogcapi_proc_core}/rec/core/cross-origin",
        f"{ogcapi_proc_core}/rec/core/content-length",
    ] + ([
        f"{ogcapi_proc_core}/rec/core/html",
    ] if ogcapi_proc_html else []) + [
        f"{ogcapi_proc_core}/rec/core/http-head",
        f"{ogcapi_proc_core}/rec/core/job-status",
        f"{ogcapi_proc_core}/rec/core/job-results-async-many-json-prefer-none",
        f"{ogcapi_proc_core}/rec/core/job-results-async-many-json-prefer-minimal",
        f"{ogcapi_proc_core}/rec/core/job-results-async-many-json-prefer-representation",
        f"{ogcapi_proc_core}/per/core/job-results-async-many-other-formats",
        f"{ogcapi_proc_core}/rec/core/process-execute-sync-many-json-prefer-none",
        f"{ogcapi_proc_core}/rec/core/process-execute-sync-many-json-prefer-minimal",
        f"{ogcapi_proc_core}/rec/core/process-execute-sync-many-json-prefer-representation",
        f"{ogcapi_proc_core}/rec/core/link-header",
        f"{ogcapi_proc_core}/rec/core/ogc-process-description",
        f"{ogcapi_proc_core}/rec/core/problem-details",
        f"{ogcapi_proc_core}/rec/core/process-execute-handle-prefer",
        f"{ogcapi_proc_core}/rec/core/process-execute-honor-prefer",
        f"{ogcapi_proc_core}/rec/core/process-execute-mode-auto",
        f"{ogcapi_proc_core}/rec/core/process-execute-preference-applied",
        f"{ogcapi_proc_core}/rec/core/process-execute-sync-document-ref",
        f"{ogcapi_proc_core}/rec/core/next-1",
        f"{ogcapi_proc_core}/rec/core/next-2",
        f"{ogcapi_proc_core}/rec/core/next-3",
        f"{ogcapi_proc_core}/rec/core/test-process",
        f"{ogcapi_proc_core}/rec/job-list/job-list-landing-page",
        f"{ogcapi_proc_core}/rec/job-list/next-1",
        f"{ogcapi_proc_core}/rec/job-list/next-2",
        f"{ogcapi_proc_core}/rec/job-list/next-3",
        f"{ogcapi_proc_core}/req/callback/job-callback",
        f"{ogcapi_proc_core}/req/core",
        f"{ogcapi_proc_core}/req/core/api-definition-op",
        f"{ogcapi_proc_core}/req/core/api-definition-success",
        f"{ogcapi_proc_core}/req/core/conformance-op",
        f"{ogcapi_proc_core}/req/core/conformance-success",
        f"{ogcapi_proc_core}/req/core/http",
        f"{ogcapi_proc_core}/req/core/job",
        f"{ogcapi_proc_core}/req/core/job-exception-no-such-job",
        f"{ogcapi_proc_core}/req/core/job-results-exception/no-such-job",
        f"{ogcapi_proc_core}/req/core/job-results-exception/results-not-ready",
        f"{ogcapi_proc_core}/req/core/job-results-failed",
        f"{ogcapi_proc_core}/req/core/job-results",
        f"{ogcapi_proc_core}/req/core/job-results-async-document",
        f"{ogcapi_proc_core}/req/core/job-results-async-many",
        # FIXME: /results/{id} (https://github.com/crim-ca/weaver/issues/18)
        # f"{ogcapi_proc_core}/req/core/job-results-async-one",
        f"{ogcapi_proc_core}/req/core/job-results-async-raw-mixed-multi",
        f"{ogcapi_proc_core}/req/core/job-results-async-raw-ref",
        f"{ogcapi_proc_core}/req/core/job-results-async-raw-value-multi",
        f"{ogcapi_proc_core}/req/core/job-results-async-raw-value-one",
        f"{ogcapi_proc_core}/req/core/job-results-success-sync",
        # FIXME: results 'outputs' query parameter (https://github.com/crim-ca/weaver/issues/733)
        # f"{ogcapi_proc_core}/req/core/job-results-param-outputs",
        # f"{ogcapi_proc_core}/req/core/job-results-param-outputs-empty",
        f"{ogcapi_proc_core}/req/core/job-results-param-outputs-omit",
        # f"{ogcapi_proc_core}/req/core/job-results-param-outputs-response",
        f"{ogcapi_proc_core}/req/core/job-success",
        f"{ogcapi_proc_core}/req/core/landingpage-op",
        f"{ogcapi_proc_core}/req/core/landingpage-success",
        f"{ogcapi_proc_core}/req/core/pl-links",
        f"{ogcapi_proc_core}/req/core/process",
        f"{ogcapi_proc_core}/req/core/process-success",
        f"{ogcapi_proc_core}/req/core/process-exception/no-such-process",
        f"{ogcapi_proc_core}/req/core/process-execute-auto-execution-mode",
        f"{ogcapi_proc_core}/req/core/process-execute-default-execution-mode",
        f"{ogcapi_proc_core}/req/core/process-execute-default-outputs",
        f"{ogcapi_proc_core}/req/core/process-execute-input-array",
        f"{ogcapi_proc_core}/req/core/process-execute-input-inline-bbox",
        f"{ogcapi_proc_core}/req/core/process-execute-input-inline-binary",
        f"{ogcapi_proc_core}/req/core/process-execute-input-mixed-type",
        f"{ogcapi_proc_core}/req/core/process-execute-input-inline-object",
        f"{ogcapi_proc_core}/req/core/process-execute-input-validation",
        f"{ogcapi_proc_core}/req/core/process-execute-inputs",
        f"{ogcapi_proc_core}/req/core/process-execute-op",
        f"{ogcapi_proc_core}/req/core/process-execute-request",
        f"{ogcapi_proc_core}/req/core/process-execute-success-async",
        f"{ogcapi_proc_core}/req/core/process-execute-sync-document",
        f"{ogcapi_proc_core}/req/core/process-execute-sync-raw-mixed-multi",
        f"{ogcapi_proc_core}/req/core/process-execute-sync-raw-ref",
        f"{ogcapi_proc_core}/req/core/process-execute-sync-raw-value-multi",
        f"{ogcapi_proc_core}/req/core/process-execute-sync-raw-value-one",
        f"{ogcapi_proc_core}/req/core/pl-limit-definition",
        f"{ogcapi_proc_core}/req/core/pl-limit-response",
        f"{ogcapi_proc_core}/req/core/process-list",
        f"{ogcapi_proc_core}/req/core/process-list-success",
        f"{ogcapi_proc_core}/req/core/test-process",
        f"{ogcapi_proc_core}/req/dismiss",
        f"{ogcapi_proc_core}/req/dismiss/job-dismiss-op",
        f"{ogcapi_proc_core}/req/dismiss/job-dismiss-success",
    ] + ([
        f"{ogcapi_proc_core}/req/html",
        f"{ogcapi_proc_core}/req/html/content",
        f"{ogcapi_proc_core}/req/html/definition",
    ] if ogcapi_proc_html else []) + [
        # FIXME: https://github.com/crim-ca/weaver/issues/231
        #  List all supported requirements, recommendations and abstract tests
        f"{ogcapi_proc_core}/conf/ogc-process-description",
        f"{ogcapi_proc_core}/req/json",
        f"{ogcapi_proc_core}/req/json/definition",
        f"{ogcapi_proc_core}/req/job-list/datetime-definition",
        f"{ogcapi_proc_core}/req/job-list/datetime-response",
        f"{ogcapi_proc_core}/req/job-list/duration-definition",
        f"{ogcapi_proc_core}/req/job-list/duration-response",
        f"{ogcapi_proc_core}/req/job-list/links",
        f"{ogcapi_proc_core}/req/job-list/jl-limit-definition",
        f"{ogcapi_proc_core}/req/job-list/job-list-op",
        f"{ogcapi_proc_core}/req/job-list/processID-definition",
        f"{ogcapi_proc_core}/req/job-list/processID-mandatory",
        f"{ogcapi_proc_core}/req/job-list/processid-response",
        f"{ogcapi_proc_core}/req/job-list/status-definition",
        f"{ogcapi_proc_core}/req/job-list/status-response",
        f"{ogcapi_proc_core}/req/job-list/type-definition",
        f"{ogcapi_proc_core}/req/job-list/type-response",
        # FIXME: KVP exec (https://github.com/crim-ca/weaver/issues/607, https://github.com/crim-ca/weaver/issues/445)
        # f"{ogcapi_proc_core}/req/kvp-execute",
        # f"{ogcapi_proc_core}/req/kvp-execute/process-execute-op",
        # f"{ogcapi_proc_core}/req/kvp-execute/f-definition",
        # f"{ogcapi_proc_core}/req/kvp-execute/f-response",
        # f"{ogcapi_proc_core}/req/kvp-execute/prefer-definition",
        # f"{ogcapi_proc_core}/req/kvp-execute/input-query-parameters",
        # f"{ogcapi_proc_core}/req/kvp-execute/input-query-parameter-values",
        # f"{ogcapi_proc_core}/req/kvp-execute/string-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/numeric-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/boolean-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/complex-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/array-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/binary-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/binary-input-value-qualified",
        # f"{ogcapi_proc_core}/req/kvp-execute/bbox-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/bbox-crs-input-value",
        # f"{ogcapi_proc_core}/req/kvp-execute/input-by-reference",
        # f"{ogcapi_proc_core}/req/kvp-execute/input-cardinality",
        # f"{ogcapi_proc_core}/req/kvp-execute/output",
        f"{ogcapi_proc_core}/req/oas30",  # OpenAPI 3.0
        f"{ogcapi_proc_core}/req/oas30/completeness",
        f"{ogcapi_proc_core}/req/oas30/exceptions-codes",
        f"{ogcapi_proc_core}/req/oas30/oas-definition-1",
        f"{ogcapi_proc_core}/req/oas30/oas-definition-2",
        f"{ogcapi_proc_core}/req/oas30/oas-impl",
        f"{ogcapi_proc_core}/req/oas30/security",
        f"{ogcapi_proc_core}/req/ogc-process-description/input-def",
        f"{ogcapi_proc_core}/req/ogc-process-description/input-mixed-type",
        f"{ogcapi_proc_core}/req/ogc-process-description/inputs-def",
        f"{ogcapi_proc_core}/req/ogc-process-description/json-encoding",
        f"{ogcapi_proc_core}/req/ogc-process-description/output-def",
        f"{ogcapi_proc_core}/req/ogc-process-description/output-mixed-type",
        f"{ogcapi_proc_core}/req/ogc-process-description/outputs-def",
        f"{ogcapi_proc_part2}/conf/cwl",
        f"{ogcapi_proc_part2}/conf/cwl/deploy-body",
        f"{ogcapi_proc_part2}/conf/cwl/deploy-response-body",
        f"{ogcapi_proc_part2}/conf/cwl/deploy-response",
        f"{ogcapi_proc_part2}/conf/cwl/replace-body",
        f"{ogcapi_proc_part2}/conf/cwl/replace-response",
        # FIXME: support 'docker' direct deployment without CWL?
        # f"{ogcapi_proc_part2}/conf/docker",
        # f"{ogcapi_proc_part2}/conf/docker/deploy-body",
        # f"{ogcapi_proc_part2}/conf/docker/replace-body",
        f"{ogcapi_proc_part2}/conf/dru",
        f"{ogcapi_proc_part2}/conf/dru/deploy-content-type",
        f"{ogcapi_proc_part2}/conf/dru/deploy-post-op",
        f"{ogcapi_proc_part2}/conf/dru/deploy-unsupported-content-type",
        f"{ogcapi_proc_part2}/conf/dru/replace-content-type",
        f"{ogcapi_proc_part2}/conf/dru/replace-put-op",
        f"{ogcapi_proc_part2}/conf/dru/replace-unsupported-content-type",
        f"{ogcapi_proc_part2}/conf/dru/undeploy/delete-op",
        f"{ogcapi_proc_part2}/conf/dru/undeploy/response-immutable-success",
        f"{ogcapi_proc_part2}/conf/dru/undeploy/response-immutable",
        f"{ogcapi_proc_part2}/conf/dru/undeploy/response",
        f"{ogcapi_proc_part2}/conf/dru/undeploy/mutable-process",
        f"{ogcapi_proc_part2}/conf/dru/process-list-success",
        f"{ogcapi_proc_part2}/conf/dru/static-indicator",
        f"{ogcapi_proc_part2}/conf/dru/test-process",
        f"{ogcapi_proc_part2}/conf/dru/test-process",
        f"{ogcapi_proc_part2}/conf/deploy-replace-undeploy",
        f"{ogcapi_proc_part2}/conf/ogcapppkg",
        f"{ogcapi_proc_part2}/conf/ogcapppkg/deploy-body",
        f"{ogcapi_proc_part2}/conf/ogcapppkg/deploy-response",
        f"{ogcapi_proc_part2}/conf/ogcapppkg/deploy-response-duplicate",
        f"{ogcapi_proc_part2}/conf/ogcapppkg/deploy-response-success",
        f"{ogcapi_proc_part2}/conf/ogcapppkg/replace-body",
        f"{ogcapi_proc_part2}/conf/ogcapppkg/replace-response",
        f"{ogcapi_proc_part2}/req/cwl",
        f"{ogcapi_proc_part2}/req/cwl/execution-unit",
        f"{ogcapi_proc_part2}/req/cwl/deploy-body",
        # FIXME: multi-CWL $graph (class: Workflow), must allow section of 1 with 'w' query param
        # (https://github.com/crim-ca/weaver/issues/739)
        # f"{ogcapi_proc_part2}/req/cwl/deploy-w-param",
        # f"{ogcapi_proc_part2}/req/cwl/deploy-exception-workflow-not-found",
        f"{ogcapi_proc_part2}/req/cwl/package-response-body",
        f"{ogcapi_proc_part2}/req/cwl/replace-body",
        f"{ogcapi_proc_part2}/per/deploy-replace-undeploy/additional-status-codes",
        f"{ogcapi_proc_part2}/per/deploy-replace-undeploy/replace-body",
        f"{ogcapi_proc_part2}/rec/deploy-replace-undeploy/deploy-body-ogcapppkg",
        f"{ogcapi_proc_part2}/rec/deploy-replace-undeploy/package-response-cwl",
        # FIXME: support 'application/ogcapppkg+json' as alternate Accept header
        # f"{ogcapi_proc_part2}/rec/deploy-replace-undeploy/package-response-ogcapppkg",
        f"{ogcapi_proc_part2}/rec/deploy-replace-undeploy/replace-body-ogcapppkg",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-body",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-content-type",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-post-op",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-response-body",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-response-pid",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-response",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/deploy-unsupported-content-type",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/package-get-op",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/package-response-body",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/package-response-success",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/replace-body",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/replace-content-type",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/replace-put-op",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/replace-response",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/replace-unsupported-content-type",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/static/indicator",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/undeploy/delete-op",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/undeploy/response",
        f"{ogcapi_proc_part2}/req/deploy-replace-undeploy/ogcapppkg",
        f"{ogcapi_proc_part2}/req/dru/mutable-process",
        f"{ogcapi_proc_part2}/req/dru/test-process",
        f"{ogcapi_proc_part2}/req/ogcapppkg",
        f"{ogcapi_proc_part2}/req/ogcapppkg/deploy-body",
        # FIXME: support 'docker' direct deployment without CWL?
        # f"{ogcapi_proc_part2}/req/ogcapppkg/execution-unit-docker",
        f"{ogcapi_proc_part2}/req/ogcapppkg/package-response-body",
        f"{ogcapi_proc_part2}/req/ogcapppkg/process-description",
        f"{ogcapi_proc_part2}/req/ogcapppkg/profile-docker",
        f"{ogcapi_proc_part2}/req/ogcapppkg/replace-body",
        f"{ogcapi_proc_part2}/req/ogcapppkg/schema",
        # FIXME: below partially, for full Part 3, would need $graph support
        # (see https://github.com/crim-ca/weaver/issues/56 and below '/conf/app-pck/cwl')
        f"{ogcapi_proc_part3}/req/cwl-workflows",
        f"{ogcapi_proc_part3}/conf/cwl-workflows",
        f"{ogcapi_proc_part3}/conf/nested-processes",
        f"{ogcapi_proc_part3}/conf/remote-core-processes",
        f"{ogcapi_proc_part3}/conf/collection-input",
        f"{ogcapi_proc_part3}/conf/remote-collections",
        f"{ogcapi_proc_part3}/conf/input-fields-modifiers",
        # f"{ogcapi_proc_part3}/conf/output-fields-modifiers",
        # f"{ogcapi_proc_part3}/conf/deployable-workflows",
        # f"{ogcapi_proc_part3}/conf/collection-output",
        f"{ogcapi_proc_part3}/req/collection-input",
        # f"{ogcapi_proc_part3}/req/collection-output",
        # f"{ogcapi_proc_part3}/req/deployable-workflows",
        # f"{ogcapi_proc_part3}/req/input-fields-modifiers",
        # f"{ogcapi_proc_part3}/req/output-fields-modifiers",
        f"{ogcapi_proc_part3}/req/nested-processes",
        f"{ogcapi_proc_part3}/req/remote-collections",
        f"{ogcapi_proc_part3}/req/remote-collections/collection-access",
        f"{ogcapi_proc_part3}/req/remote-collections/referenced-collection",
        f"{ogcapi_proc_part3}/req/remote-collections/process-execution",
        f"{ogcapi_proc_part3}/req/remote-core-processes",
        f"{ogcapi_proc_part3}/req/remote-core-processes/referenced-process",
        # FIXME: support openEO processes (https://github.com/crim-ca/weaver/issues/564)
        # f"{ogcapi_proc_part3}/conf/openeo-workflows",
        # f"{ogcapi_proc_part3}/req/openeo-workflows",
        f"{ogcapi_proc_part4}/conf/job-management",
        f"{ogcapi_proc_part4}/conf/jm/create/post-op",
        f"{ogcapi_proc_part4}/per/job-management/additional-status-codes",  # see 'weaver.status.map_status'
        f"{ogcapi_proc_part4}/per/job-management/create-body",              # Weaver has XML for WPS
        f"{ogcapi_proc_part4}/per/job-management/create-content-schema",
        f"{ogcapi_proc_part4}/per/job-management/update-body",
        f"{ogcapi_proc_part4}/per/job-management/update-content-schema",
        f"{ogcapi_proc_part4}/rec/job-management/create-body-ogcapi-processes",
        f"{ogcapi_proc_part4}/rec/job-management/update-body-ogcapi-processes",
        # FIXME: support openEO processes (https://github.com/crim-ca/weaver/issues/564)
        # f"{ogcapi_proc_part4}/rec/job-management/create-body-openeo",
        # f"{ogcapi_proc_part4}/rec/job-management/update-body-openeo",
        f"{ogcapi_proc_part4}/req/job-management/create-post-op",
        f"{ogcapi_proc_part4}/req/job-management/create-content-type",
        f"{ogcapi_proc_part4}/req/job-management/create-response-body",
        f"{ogcapi_proc_part4}/req/job-management/create-response-jobid",
        f"{ogcapi_proc_part4}/req/job-management/create-response-success",
        # FIXME: support Content-Schema and Profile header negotiation (https://github.com/crim-ca/weaver/issues/754)
        # f"{ogcapi_proc_part4}/req/job-management/create-unsupported-schema",
        f"{ogcapi_proc_part4}/req/job-management/create-unsupported-media-type",
        f"{ogcapi_proc_part4}/req/job-management/definition-get-op",
        f"{ogcapi_proc_part4}/req/job-management/definition-response-body",
        f"{ogcapi_proc_part4}/req/job-management/definition-response-success",
        f"{ogcapi_proc_part4}/req/job-management/start-post-op",
        f"{ogcapi_proc_part4}/req/job-management/start-response",
        f"{ogcapi_proc_part4}/req/job-management/update-body",
        f"{ogcapi_proc_part4}/req/job-management/update-content-type",
        f"{ogcapi_proc_part4}/req/job-management/update-patch-op",
        f"{ogcapi_proc_part4}/req/job-management/update-response",
        f"{ogcapi_proc_part4}/req/job-management/update-response-locked",
    ] + ([
        f"{ogcapi_proc_part4}/req/provenance",
        f"{ogcapi_proc_part4}/req/provenance/prov-get-op",
        f"{ogcapi_proc_part4}/req/provenance/prov-response",
        f"{ogcapi_proc_part4}/req/provenance/prov-content-negotiation",
        f"{ogcapi_proc_part4}/req/provenance/inputs-get-op",
        f"{ogcapi_proc_part4}/req/provenance/inputs-response",
    ] if ogcapi_proc_prov else []) + [
        # FIXME: employ 'weaver.wps_restapi.quotation.utils.check_quotation_supported' to add below conditionally
        # FIXME: https://github.com/crim-ca/weaver/issues/156  (billing/quotation)
        # https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/billing
        # https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/quotation
        # FIXME: (CWL App Package) https://github.com/crim-ca/weaver/issues/294
        f"{ogcapi_proc_apppkg}/conf/app",
        f"{ogcapi_proc_apppkg}/req/app",
        f"{ogcapi_proc_apppkg}/conf/app/cmd-line",
        f"{ogcapi_proc_apppkg}/req/app/cmd-line",
        f"{ogcapi_proc_apppkg}/conf/app/container",
        f"{ogcapi_proc_apppkg}/req/app/container",
        f"{ogcapi_proc_apppkg}/conf/app/registry",
        f"{ogcapi_proc_apppkg}/req/app/registry",
        f"{ogcapi_proc_apppkg}/conf/app-stage-in",
        f"{ogcapi_proc_apppkg}/req/app-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        # f"{ogcapi_proc_apppkg}/conf/app/stac-input",
        # f"{ogcapi_proc_apppkg}/req/app/stac-input",
        f"{ogcapi_proc_apppkg}/conf/app-stage-out",
        f"{ogcapi_proc_apppkg}/req/app-stage-out",
        # f"{ogcapi_proc_apppkg}/req/app/stac-out",
        # f"{ogcapi_proc_apppkg}/conf/app/stac-out",
        # f"{ogcapi_proc_apppkg}/rec/app/stac-out-metadata",
        # f"{ogcapi_proc_apppkg}/rec/conf/stac-out-metadata",
        f"{ogcapi_proc_apppkg}/conf/app-pck",
        f"{ogcapi_proc_apppkg}/req/app-pck",
        # FIXME: Support embedded step definition in CWL (https://github.com/crim-ca/weaver/issues/56)
        #   Allow definition of a '$graph' with list of Workflow + >=1 CommandLineTool all together
        #   see: https://docs.ogc.org/bp/20-089r1.html#toc28
        # f"{ogcapi_proc_apppkg}/conf/app-pck/cwl",
        # f"{ogcapi_proc_apppkg}/req/app-pck/cwl",
        f"{ogcapi_proc_apppkg}/req/app-pck/clt",
        f"{ogcapi_proc_apppkg}/req/app-pck/wf",
        f"{ogcapi_proc_apppkg}/req/app-pck/wf-inputs",
        f"{ogcapi_proc_apppkg}/req/app-pck/metadata",
        f"{ogcapi_proc_apppkg}/rec/app-pck/fan-out",
        f"{ogcapi_proc_apppkg}/conf/app-pck-stage-in",
        f"{ogcapi_proc_apppkg}/req/app-pck-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        #   not sure about requirement: "staging of EO products SHALL be of type 'Directory'."
        # f"{ogcapi_proc_apppkg}/req/app-pck-stage-in/clt-stac",
        # f"{ogcapi_proc_apppkg}/req/app-pck-stage-in/wf-stac",
        f"{ogcapi_proc_apppkg}/conf/app-pck-stage-out",
        f"{ogcapi_proc_apppkg}/req/app-pck-stage-out",
        # f"{ogcapi_proc_apppkg}/req/app-pck-stage-out/output-stac"
        f"{ogcapi_proc_apppkg}/conf/plt",
        f"{ogcapi_proc_apppkg}/req/plt",
        f"{ogcapi_proc_apppkg}/req/plt/api",
        f"{ogcapi_proc_apppkg}/req/plt/inputs",
        f"{ogcapi_proc_apppkg}/req/plt/file",
        f"{ogcapi_proc_apppkg}/conf/plt-stage-in",
        f"{ogcapi_proc_apppkg}/req/plt-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        # f"{ogcapi_proc_apppkg}/req/plt-stage-in/input-stac",
        # f"{ogcapi_proc_apppkg}/req/plt-stage-in/stac-stage",
        f"{ogcapi_proc_apppkg}/conf/plt-stage-out",
        f"{ogcapi_proc_apppkg}/req/plt-stage-out",
        # f"{ogcapi_proc_apppkg}/req/plt-stage-out/stac-stage",
    ]) if ogcapi_proc_enabled else []

    conformance = ows_wps_conformance + ogcapi_proc_conformance
    if category not in [None, ConformanceCategory.ALL]:
        cat = f"/{category}/"
        conformance = filter(lambda item: cat in item, conformance)
    data = {"conformsTo": list(sorted(conformance))}
    return data


@sd.api_frontpage_service.get(
    tags=[sd.TAG_API],
    schema=sd.FrontpageEndpoint(),
    accept=ContentType.TEXT_HTML,
    renderer="weaver.wps_restapi:templates/responses/frontpage.mako",
    response_schemas=sd.derive_responses(
        sd.get_api_frontpage_responses,
        sd.GenericHTMLResponse(name="HTMLFrontpage", description="API Frontpage.")
    ),
)
@sd.api_frontpage_service.get(
    tags=[sd.TAG_API],
    schema=sd.FrontpageEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_api_frontpage_responses,
)
def api_frontpage(request):
    # type: (SettingsType) -> JSON
    """
    Frontpage of Weaver.
    """
    settings = get_settings(request)
    body = api_frontpage_body(settings)
    return Box(body)


@cache_region("doc", sd.api_frontpage_service.name)
def api_frontpage_body(settings):
    # type: (SettingsType) -> JSON
    """
    Generates the JSON body describing the Weaver API and documentation references.
    """

    # import here to avoid circular import errors
    from weaver.config import get_weaver_configuration

    weaver_url = get_weaver_url(settings)
    weaver_config = get_weaver_configuration(settings)

    weaver_rtd_url = "https://pavics-weaver.readthedocs.io/en/latest"
    weaver_api = asbool(settings.get("weaver.wps_restapi", True))
    weaver_api_url = get_wps_restapi_base_url(settings)
    weaver_api_oas_ui = weaver_url + sd.api_openapi_ui_service.path if weaver_api else None
    weaver_api_swagger = weaver_url + sd.api_swagger_ui_service.path if weaver_api else None
    weaver_api_spec = weaver_url + sd.openapi_json_service.path if weaver_api else None
    weaver_api_doc = settings.get("weaver.wps_restapi_doc", None) if weaver_api else None
    weaver_api_ref = settings.get("weaver.wps_restapi_ref", None) if weaver_api else None
    weaver_api_html = asbool(settings.get("weaver.wps_restapi_html", True)) and weaver_api
    weaver_api_html_url = f"{weaver_api_url}?f={OutputFormat.HTML}"
    weaver_api_prov = asbool(settings.get("weaver.cwl_prov", True)) and weaver_api
    weaver_api_prov_doc = f"{weaver_rtd_url}/processes.html#job-provenance"
    weaver_api_prov_oas = f"{weaver_api_oas_ui}#/Provenance" if weaver_api_prov else None
    weaver_wps = asbool(settings.get("weaver.wps"))
    weaver_wps_url = get_wps_url(settings) if weaver_wps else None
    weaver_wps_oas = f"{weaver_api_oas_ui}#/WPS" if weaver_wps else None
    weaver_conform_url = weaver_url + sd.api_conformance_service.path
    weaver_process_url = weaver_api_url + sd.processes_service.path
    weaver_jobs_url = weaver_api_url + sd.jobs_service.path
    weaver_vault = asbool(settings.get("weaver.vault"))
    weaver_vault_url = f"{weaver_api_url}/vault" if weaver_vault else None
    weaver_vault_api = f"{weaver_api_oas_ui}#/Vault" if weaver_vault else None
    weaver_vault_doc = f"{weaver_rtd_url}/processes.html#vault-upload"
    weaver_links = [
        {"href": weaver_url, "rel": "self", "type": ContentType.APP_JSON, "title": "This landing page."},
        {"href": weaver_conform_url, "rel": "http://www.opengis.net/def/rel/ogc/1.0/conformance",
         "type": ContentType.APP_JSON, "title": "Conformance classes implemented by this service."},
        {"href": __meta__.__license_url__, "rel": "license",
         "type": ContentType.TEXT_PLAIN, "title": __meta__.__license_long__}
    ]
    if weaver_api:
        weaver_links.extend([
            {"href": weaver_api_url,
             "rel": "service", "type": ContentType.APP_JSON,
             "title": "WPS REST API endpoint of this service."},
            {"href": weaver_api_spec,
             "rel": "service-desc", "type": ContentType.APP_OAS_JSON,
             "title": "OpenAPI specification of this service."},
            {"href": weaver_api_oas_ui,
             "rel": "service-doc", "type": ContentType.TEXT_HTML,
             "title": "Human-readable OpenAPI documentation of this service."},
            {"href": weaver_api_spec,
             "rel": "OpenAPI", "type": ContentType.APP_OAS_JSON,
             "title": "OpenAPI specification of this service."},
            {"href": weaver_api_swagger,
             "rel": "swagger-ui", "type": ContentType.TEXT_HTML,
             "title": "WPS REST API definition of this service."},
            {"href": weaver_process_url,
             "rel": "http://www.opengis.net/def/rel/ogc/1.0/processes", "type": ContentType.APP_JSON,
             "title": "Processes offered by this service."},
            {"href": sd.OGC_API_REPO_URL,
             "rel": "ogcapi-processes-repository", "type": ContentType.TEXT_HTML,
             "title": "OGC API - Processes schema definitions repository."},
            {"href": weaver_jobs_url,
             "rel": "http://www.opengis.net/def/rel/ogc/1.0/job-list", "type": ContentType.APP_JSON,
             "title": "Job search and listing endpoint of executions registered under this service."},
            {"href": sd.CWL_BASE_URL,
             "rel": "cwl-home", "type": ContentType.TEXT_HTML,
             "title": "Common Workflow Language (CWL) homepage."},
            {"href": sd.CWL_REPO_URL,
             "rel": "cwl-repository", "type": ContentType.TEXT_HTML,
             "title": "Common Workflow Language (CWL) repositories."},
            {"href": sd.CWL_SPEC_URL,
             "rel": "cwl-specification", "type": ContentType.TEXT_HTML,
             "title": "Common Workflow Language (CWL) specification."},
            {"href": sd.CWL_USER_GUIDE_URL,
             "rel": "cwl-user-guide", "type": ContentType.TEXT_HTML,
             "title": "Common Workflow Language (CWL) user guide."},
            {"href": sd.CWL_CMD_TOOL_URL,
             "rel": "cwl-command-line-tool", "type": ContentType.TEXT_HTML,
             "title": "Common Workflow Language (CWL) CommandLineTool specification."},
            {"href": sd.CWL_WORKFLOW_URL,
             "rel": "cwl-workflow", "type": ContentType.TEXT_HTML,
             "title": "Common Workflow Language (CWL) Workflow specification."},
        ])
        if weaver_api_ref:
            # sample:
            #   https://app.swaggerhub.com/apis/geoprocessing/WPS/
            weaver_links.append({"href": weaver_api_ref, "rel": "reference", "type": ContentType.APP_JSON,
                                 "title": "API reference specification of this service."})
        if isinstance(weaver_api_doc, str):
            # sample:
            #   https://raw.githubusercontent.com/opengeospatial/wps-rest-binding/develop/docs/18-062.pdf
            if "." in weaver_api_doc:  # pylint: disable=E1135,unsupported-membership-test
                ext_type = weaver_api_doc.rsplit(".", 1)[-1]
                doc_type = f"application/{ext_type}"
            else:
                doc_type = ContentType.TEXT_PLAIN  # default most basic type
            weaver_links.append({"href": weaver_api_doc, "rel": "documentation", "type": doc_type,
                                 "title": "API reference documentation about this service."})
        else:
            weaver_links.append({"href": __meta__.__documentation_url__, "rel": "documentation",
                                 "type": ContentType.TEXT_HTML,
                                 "title": "API reference documentation about this service."})
    if weaver_api_html:
        weaver_links.append({
            "href": weaver_api_html_url,
            "type": ContentType.TEXT_HTML,
            "rel": "alternate",
            "title": "HTML view of the API frontpage."
        })
    if weaver_wps:
        weaver_links.extend([
            {"href": weaver_wps_url,
             "rel": "wps", "type": ContentType.TEXT_XML,
             "title": "WPS 1.0.0/2.0 XML endpoint of this service."},
            {"href": "https://docs.opengeospatial.org/is/14-065/14-065.html",
             "rel": "wps-specification", "type": ContentType.TEXT_HTML,
             "title": "WPS 1.0.0/2.0 definition of this service."},
            {"href": "https://schemas.opengis.net/wps/",
             "rel": "wps-schema-repository", "type": ContentType.TEXT_HTML,
             "title": "WPS 1.0.0/2.0 XML schemas repository."},
            {"href": "https://schemas.opengis.net/wps/1.0.0/wpsAll.xsd",
             "rel": "wps-schema-1", "type": ContentType.TEXT_XML,
             "title": "WPS 1.0.0 XML validation schemas entrypoint."},
            {"href": "https://schemas.opengis.net/wps/2.0/wps.xsd",
             "rel": "wps-schema-2", "type": ContentType.TEXT_XML,
             "title": "WPS 2.0 XML validation schemas entrypoint."},
        ])
    body = sd.FrontpageSchema().deserialize(
        {
            "message": "Weaver Information",
            "configuration": weaver_config,
            "description": __meta__.__description__,
            "attribution": __meta__.__author__,
            "parameters": [
                {"name": "api", "enabled": weaver_api, "url": weaver_api_url,
                 "doc": weaver_rtd_url, "api": weaver_api_oas_ui},
                {"name": "html", "enabled": weaver_api_html, "url": weaver_api_html_url, "api": weaver_api_oas_ui},
                {"name": "prov", "enabled": weaver_api_prov, "doc": weaver_api_prov_doc, "api": weaver_api_prov_oas},
                {"name": "vault", "enabled": weaver_vault, "url": weaver_vault_url,
                 "doc": weaver_vault_doc, "api": weaver_vault_api},
                {"name": "wps", "enabled": weaver_wps, "url": weaver_wps_url, "api": weaver_wps_oas},
            ],
            "links": weaver_links,
        }
    )
    return body


@sd.api_versions_service.get(
    tags=[sd.TAG_API],
    schema=sd.VersionsEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_api_versions_responses,
)
def api_versions(request):  # noqa: F811
    # type: (PyramidRequest) -> HTTPException
    """
    Weaver versions information.
    """
    weaver_info = {"name": "weaver", "version": __meta__.__version__, "type": "api"}
    return HTTPOk(json={"versions": [weaver_info]})


@sd.api_conformance_service.get(
    tags=[sd.TAG_API],
    schema=sd.ConformanceEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_api_conformance_responses,
)
def api_conformance(request):  # noqa: F811
    # type: (PyramidRequest) -> HTTPException
    """
    Weaver specification conformance information.
    """
    cat = ConformanceCategory.get(request.params.get("category"), ConformanceCategory.CONFORMANCE)
    data = get_conformance(cat, get_settings(request))
    return HTTPOk(json=data)


def get_openapi_json(
    http_scheme="http",             # type: str
    http_host="localhost",          # type: str
    base_url=None,                  # type: Optional[str]
    use_refs=True,                  # type: bool
    use_docstring_summary=True,     # type: bool
    container=None,                 # type: Optional[AnySettingsContainer]
):                                  # type: (...) -> OpenAPISpecification
    """
    Obtains the JSON schema of Weaver OpenAPI from request and response views schemas.

    :param http_scheme: Protocol scheme to use for building the API base if not provided by base URL parameter.
    :param http_host: Hostname to use for building the API base if not provided by base URL parameter.
    :param base_url: Explicit base URL to employ of as API base instead of HTTP scheme/host parameters.
    :param use_refs: Generate schemas with ``$ref`` definitions or expand every schema content.
    :param use_docstring_summary: Extra function docstring to auto-generate the summary field of responses.
    :param container:
        Container with the :mod:`pyramid` registry and settings to retrieve
        further metadata details to be added to the :term:`OpenAPI`.

    .. seealso::
        - :mod:`weaver.wps_restapi.swagger_definitions`
    """
    depth = -1 if use_refs else 0
    registry = get_registry(container)
    settings = get_settings(registry)
    swagger = CorniceOpenAPI(
        get_services(),
        def_ref_depth=depth,
        param_ref=use_refs,
        resp_ref=use_refs,
        # registry needed to map to the resolved paths using any relevant route prefix
        # if unresolved, routes will use default endpoint paths without configured setting prefixes (if any)
        pyramid_registry=registry,
    )
    swagger.ignore_methods = ["OPTIONS"]  # don't ignore HEAD, used by vault
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
            "url": f"{__meta__.__source_repository__}/blob/master/LICENSE.txt",
        }
    }  # type: OpenAPISpecInfo
    if settings:
        for key in ["name", "email", "url"]:
            val = settings.get(f"weaver.wps_metadata_contact_{key}")
            if val:
                swagger_info.setdefault("contact", {})
                swagger_info["contact"][key] = val
        abstract = settings.get("weaver.wps_metadata_identification_abstract")
        if abstract:
            swagger_info["description"] = f"{abstract}\n\n{__meta__.__description__}"
        terms = settings.get("weaver.wps_metadata_identification_accessconstraints")
        if terms and "http" in terms:
            if "," in terms:
                terms = [term.strip() for term in terms.split(",")]
            else:
                terms = [terms]
            terms = [term for term in terms if "http" in term]
            if terms:
                swagger_info["termsOfService"] = terms[0]

    swagger_json = swagger.generate(
        title=sd.API_TITLE,
        version=__meta__.__version__,
        info=swagger_info,
        base_path=swagger_base_path,
        openapi_spec=3,
    )
    swagger_json["externalDocs"] = sd.API_DOCS
    return swagger_json


@cache_region("doc", sd.openapi_json_service.name)
def openapi_json_cached(*args, **kwargs):
    # type: (*Any, **Any) -> OpenAPISpecification
    return get_openapi_json(*args, **kwargs)


@sd.openapi_json_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_openapi_json_responses,
)
def openapi_json(request):  # noqa: F811
    # type: (PyramidRequest) -> HTTPException
    """
    Weaver OpenAPI schema definitions.
    """
    # obtain 'server' host and api-base-path, which doesn't correspond necessarily to the app's host and path
    # ex: 'server' adds '/weaver' with proxy redirect before API routes
    weaver_server_url = get_weaver_url(request)
    LOGGER.debug("Request app URL:   [%s]", request.url)
    LOGGER.debug("Weaver config URL: [%s]", weaver_server_url)
    spec = openapi_json_cached(base_url=weaver_server_url, use_docstring_summary=True, container=request)
    return HTTPOk(json=spec, content_type=ContentType.APP_OAS_JSON)


@cache_region("doc", sd.api_swagger_ui_service.name)
def swagger_ui_cached(request):
    # type: (PyramidRequest) -> AnyResponseType
    json_path = sd.openapi_json_service.path
    json_path = json_path.lstrip("/")   # if path starts by '/', swagger-ui doesn't find it on remote
    data_mako = {"api_title": sd.API_TITLE, "openapi_json_path": json_path, "api_version": __meta__.__version__}
    resp = render_to_response("templates/swagger_ui.mako", data_mako, request=request)
    return resp


@sd.api_openapi_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIFormatRedirect(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_openapi_json_responses,
)
@sd.api_openapi_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIFormatRedirect(),
    accept=ContentType.APP_OAS_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_openapi_json_responses,
)
@sd.api_openapi_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIFormatRedirect(),
    accept=ContentType.APP_YAML,
    response_schemas=sd.get_openapi_json_responses,
)
@sd.api_openapi_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.SwaggerUIEndpoint(),
    renderer="templates/swagger_ui.mako",
    response_schemas=sd.get_api_swagger_ui_responses,
)
@sd.api_swagger_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIFormatRedirect(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_openapi_json_responses,
)
@sd.api_swagger_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIFormatRedirect(),
    accept=ContentType.APP_OAS_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_openapi_json_responses,
)
@sd.api_swagger_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.OpenAPIFormatRedirect(),
    accept=ContentType.APP_YAML,
    response_schemas=sd.get_openapi_json_responses,
)
@sd.api_swagger_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.SwaggerUIEndpoint(),
    renderer="templates/swagger_ui.mako",
    response_schemas=sd.get_api_swagger_ui_responses,
)
def api_swagger_ui(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Weaver OpenAPI schema definitions rendering using Swagger-UI viewer.
    """
    c_type = guess_target_format(request, default=ContentType.TEXT_HTML)
    if c_type in [ContentType.APP_JSON, ContentType.APP_OAS_JSON]:
        return openapi_json(request)
    if c_type == ContentType.APP_YAML:
        resp = openapi_json(request)
        data = OutputFormat.convert(resp.json, ContentType.APP_YAML)
        return HTTPOk(body=data, charset="UTF-8", content_type=ContentType.APP_YAML)
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


@sd.api_redoc_ui_service.get(
    tags=[sd.TAG_API],
    schema=sd.RedocUIEndpoint(),
    accept=ContentType.TEXT_HTML,
    renderer="templates/redoc_ui.mako",
    response_schemas=sd.get_api_redoc_ui_responses,
)
def api_redoc_ui(request):
    """
    Weaver OpenAPI schema definitions rendering using Redoc viewer.
    """
    return redoc_ui_cached(request)


def get_request_info(request, detail=None):
    # type: (PyramidRequest, Optional[str]) -> JSON
    """
    Provided additional response details based on the request and execution stack on failure.
    """
    content = {"route": str(request.upath_info), "url": str(request.url), "method": request.method}
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
            content.update({"exception": str(request.exception.message)})
    elif hasattr(request, "matchdict"):
        if request.matchdict is not None and request.matchdict != "":
            content.update(request.matchdict)
    return content


def ows_json_format(function):
    # type: (ViewHandler) -> Callable[[HTTPException, PyramidRequest], HTTPException]
    """
    Decorator that adds additional detail in the response's JSON body if this is the returned content-type.
    """
    def format_response_details(response, request):
        # type: (HTTPException, AnyRequestType) -> HTTPException
        http_response = function(request)
        http_headers = get_header("Content-Type", http_response.headers) or []
        req_headers = get_header("Accept", request.headers) or []
        if any([ContentType.APP_JSON in http_headers, ContentType.APP_JSON in req_headers]):
            req_detail = get_request_info(request)
            # return the response instead of generate less detailed one if it was already formed with JSON error details
            # this can happen when a specific code like 404 triggers a pyramid lookup against other route/view handlers
            if isinstance(response, HTTPException) and isinstance(req_detail, dict):
                return response
            body = OWSException.json_formatter(http_response.status, response.message or "",
                                               http_response.title, request.environ)
            body["detail"] = req_detail
            http_response._json = body
        if http_response.status_code != response.status_code:
            raise http_response  # re-raise if code was fixed
        return http_response
    return format_response_details


@ows_json_format
def not_found_or_method_not_allowed(request):
    # type: (PyramidRequest) -> HTTPException
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
    # type: (PyramidRequest) -> HTTPException
    """
    Overrides the default is HTTPForbidden [403] by appropriate HTTPUnauthorized [401] when applicable.

    Unauthorized response is for restricted user access according to credentials and/or authorization headers.
    Forbidden response is for operation refused by the underlying process operations.

    Without this fix, both situations return [403] regardless.

    .. seealso::
        - https://www.restapitutorial.com/httpstatuscodes.html
    """
    registry: "Registry" = request.registry  # type: ignore
    authn_policy = registry.queryUtility(IAuthenticationPolicy)
    if authn_policy:
        principals = authn_policy.effective_principals(request)
        if Authenticated not in principals:
            return HTTPUnauthorized("Unauthorized access to this resource.")
    return HTTPForbidden("Forbidden operation under this resource.")


def redirect_view(request):
    # type: (PyramidRequest) -> HTTPException
    """
    Handles redirection of :term:`API` core requests to the :term:`OGC API - Processes` prefixed endpoints.

    When ``weaver.wps_restapi_path`` is set to another endpoint than the default, the core :term:`API` endpoints
    used to report documentation details such as the :term:`OpenAPI` definition and the entrypoint page become
    available on both the prefixed and non-prefixed paths. This is required to provide details that are not *only*
    relevant for the :term:`OGC API - Processes` endpoints, but also other locations such as for the :term:`WPS`
    and :term:`Vault` requests.

    Because the `HTTP 302 Found` request emitted for redirection could "loose" the ``Accept`` header originally
    provided (or resolved from a format query), an ``f`` query parameter reflecting the desired format will be
    re-applied to ensure the redirection yields the intended ``Content-Type`` result. If none of the format specifier
    where provided, the default resolution will leave out the ``f`` query to let the destination URL resolved its own
    default ``Content-Type``.
    """
    api_base = get_wps_restapi_base_path(request)
    url_base = request.path.rsplit(api_base, 1)[-1] or "/"
    content_type, source = guess_target_format(request, return_source=True)
    format_query = f"?f={OutputFormat.get(content_type)}" if source != "default" else ""
    location = f"{url_base}{format_query}"
    return HTTPFound(location=location)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding API core views...")
    config.add_forbidden_view(unauthorized_or_forbidden)
    config.add_notfound_view(not_found_or_method_not_allowed, append_slash=True)

    api_base_services = [
        sd.api_frontpage_service,
        sd.openapi_json_service,
        sd.api_openapi_ui_service,
        sd.api_swagger_ui_service,
        sd.api_redoc_ui_service,
        sd.api_versions_service,
        sd.api_conformance_service,
    ]
    for api_svc in api_base_services:
        config.add_cornice_service(api_svc)

    url_base = get_weaver_url(config)
    api_base = get_wps_restapi_base_url(config)
    if url_base != api_base:
        api_path = get_wps_restapi_base_path(config)
        LOGGER.info("Adding API core redirect views [%s => /]...", api_path)
        for api_svc in api_base_services:
            redirect_name = f"redirect-{api_svc.name}"
            redirect_path = api_path + api_svc.path.rstrip("/")
            config.add_route(name=redirect_name, pattern=redirect_path)
            config.add_view(route_name=redirect_name, view=redirect_view, request_method="GET")
