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
from weaver.utils import accepts_gzip_encoding, get_header, get_registry, get_settings, get_weaver_url
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_extras import CorniceOpenAPI
from weaver.wps_restapi.constants import ConformanceCategory
from weaver.wps_restapi.records import get_catalog_links
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

    ows_wps_enabled = asbool(settings.get("weaver.wps", True))
    ows_wps_conformance = [
        # "http://www.opengis.net/spec/wfs-1/3.0/req/core",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/oas30",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/html",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/geojson",
        f"{sd.OGC_WPS1_BASE_URI}/",
        f"{sd.OGC_WPS2_BASE_URI}/",
        f"{sd.OGC_WPS2_BASE_URI}/req/service/binding/rest-json/core",
        f"{sd.OGC_WPS2_BASE_URI}/req/service/binding/rest-json/oas30",  # /ows/wps?...&f=json
        # sd.OGC_WPS2_BASE_URI + "/req/service/binding/rest-json/html"
    ] if ows_wps_enabled else []

    # FIXME: https://github.com/crim-ca/weaver/issues/412
    # sd.OGC_API_PROC_PART3_BASE_URI = "http://www.opengis.net/spec/ogcapi-processes-3/1.0"
    ogcapi_proc_enabled = asbool(settings.get("weaver.wps_restapi", True))
    ogcapi_proc_html = asbool(settings.get("weaver.wps_restapi_html", True))
    ogcapi_proc_prov = asbool(settings.get("weaver.cwl_prov", True))
    ogcapi_proc_conformance = ([
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/conf/core",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/per/core/additional-link-relations",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/per/core/additional-status-codes",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/per/core/query-param-name-specified",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/per/core/query-param-name-tolerance",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/per/core/query-param-value-specified",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/per/core/query-param-value-tolerance",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/rec/core/cross-origin",
        # f"{sd.OGC_API_COMMON_PART1_BASE_URI}/rec/core/etag",
    ] + ([
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/rec/core/html",
    ] if ogcapi_proc_html else []) + [
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/rec/core/json",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/rec/core/link-header",
        # FIXME: error details (for all below: https://github.com/crim-ca/weaver/issues/320)
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/core/problem-details",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/core/query-param-capitalization",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/core/query-param-value-special",
        # FIXME: https://github.com/crim-ca/weaver/issues/112 (language/translate)
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/core/string-i18n",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/collection-definition",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/src-md-op",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/src-md-success",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-bbox-collection-response",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-bbox-unsupported",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-datetime-collection-response",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-datetime-definition",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-datetime-unsupported",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-datetime-response",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-limit-unsupported",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-limit-collection-response",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/collections/rc-links",
        # FIXME: https://github.com/crim-ca/weaver/issues/318
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-extent",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-extent-single",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-extent-extensions",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-md-items",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-item-type",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-items-descriptions",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-md-items-links",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-op",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/rec/collections/rc-md-success",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-numberMatched"
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-numberReturned"
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-op",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-response",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-subset-collection-response"
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/collections/rc-timeStamp",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/http",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-capitalization",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-list-delimiter",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-list-empty",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-list-escape",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/core/query-param-name-unknown",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-value-boolean",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-value-decimal",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-value-double",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-value-integer",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/core/query-param-value-invalid",
    ] + ([
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/html",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/html/content",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/html/definition",
    ] if ogcapi_proc_html else []) + [
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/json",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/json/content",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/json/definition",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/landing-page",
        f"{sd.OGC_API_COMMON_PART1_BASE_URI}/req/oas30",  # OpenAPI 3.0
        f"{sd.OGC_API_COMMON_PART2_BASE_URI}/conf/simple-query",
        # sd.OGC_API_COMMON_PART1_BASE_URI + "/req/umd-collection",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/sorting",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/sorting",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/filtering",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/filtering",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/cql-filter",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/cql-filter",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/autodiscovery",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/autodiscovery",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/local-resources-catalog",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/local-resources-catalog",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/local-resources-catalog-query-parameters",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/local-resources-catalog/query-parameters",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/local-resources-catalog-sorting",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/local-resources-catalog/sorting",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/conf/local-resources-catalog-filtering",
        f"{sd.OGC_API_RECORDS_PART1_BASE_URI}/req/local-resources-catalog/filtering",
        f"{sd.OGC_API_CQL2_BASE_URI}/conf/basic-cql2",
        f"{sd.OGC_API_CQL2_BASE_URI}/conf/cql2-json",
        f"{sd.OGC_API_CQL2_BASE_URI}/conf/cql2-text",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/core",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/api-definition-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/api-definition-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/conformance-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/conformance-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/http",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-exception-no-such-job",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-result",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-async-many",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-async-one",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-async-one-multi-valued",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-result-op-0th",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-result-op-Nth",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-success-async-one-Nth",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-exception-no-such-job",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-exception-results-not-ready",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-failed",
        # FIXME: results 'outputs' query parameter (https://github.com/crim-ca/weaver/issues/733)
        # (support pre-filtering with 'outputs' in body already available, above feature is extra at job post-execution)
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-param-outputs",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-param-outputs-empty",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-param-outputs-omit",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-param-outputs-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-results-success-sync",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/job-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/landingpage-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/landingpage-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/pl-limit-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/pl-limit-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/pl-links",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-description",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-description-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-description-no-such-process",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-auto-execution-mode",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-default-execution-mode",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-default-outputs",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-input-array",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-input-inline-bbox",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-input-inline-binary",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-input-inline-mixed",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-input-inline-object",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-input-validation",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-inputs",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-request",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-success-async",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-sync-one",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-sync-default-content",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-execute-sync-many-json",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-list",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-list-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-list-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/core/process-summary-links",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/callback",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/callback",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/callback/job-callback",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/dismiss",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/dismiss",
    ] + ([
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/html",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/html",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/html/content",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/html/definition",
    ] if ogcapi_proc_html else []) + [
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/dismiss/job-dismiss-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/dismiss/job-dismiss-success",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/json",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/json",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/json/content",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/json/definition",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/job-list",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/job-list",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/kvp-execute",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/oas30",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/oas",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/oas30",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/oas31",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/conf/ogc-process-description",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/ogc-process-description",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/conf/ogc-process-description/links",
        # FIXME: https://github.com/crim-ca/weaver/issues/231
        #  List all supported requirements, recommendations and abstract tests
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/additional-status-codes",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/alternative-process-description",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/alternative-process-paths",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/api-definition-uri",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/process-execute-input-inline-bbox",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/process-execute-sync-job",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/per/core/process-execute-sync-one-result",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/per/core/process-exception-job-gone",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/per/core/process-exception-process-gone",  # NOT used
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/per/core/job-results-exception-job-gone",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/limit-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/limit-default-minimum-maximum",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/prev",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/job-list/limit-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/job-list/prev",
        # f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/access-control-expose-headers",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/api-definition-oas",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/cross-origin",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/content-length",
    ] + ([
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/html",
    ] if ogcapi_proc_html else []) + [
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/http-head",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/rec/core/job-links",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/job-status",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/job-results-async-many-json-prefer-none",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/job-results-async-many-json-prefer-minimal",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/job-results-async-many-json-prefer-representation",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/per/core/job-results-async-many-other-formats",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/job-results-exception-results-not-available",
        # FIXME: /results/{id} (https://github.com/crim-ca/weaver/issues/18, https://github.com/crim-ca/weaver/pull/548)
        #   see https://github.com/opengeospatial/ogcapi-processes/pull/531
        #   when the requested outputID is not present within available results (originally requested)
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/job-results-exception-no-such-output",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-sync-many-json-prefer-none",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-sync-many-json-prefer-minimal",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-sync-many-json-prefer-representation",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/link-header",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/ogc-process-description",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/problem-details",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-handle-prefer",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-honor-prefer",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-mode-auto",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-preference-applied",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/process-execute-sync-document-ref",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/next-1",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/next-2",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/next-3",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/core/test-process",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/job-list/job-list-landing-page",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/job-list/next-1",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/job-list/next-2",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/rec/job-list/next-3",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/callback/job-callback",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/api-definition-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/api-definition-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/conformance-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/conformance-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/http",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-exception-no-such-job",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-exception-no-such-job",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-exception-results-not-ready",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-failed",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-document",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-many",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-one",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-one-multi-valued",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-result-op-0th",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-result-op-Nth",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-success-async-one-Nth",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-raw-mixed-multi",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-raw-ref",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-raw-value-multi",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-async-raw-value-one",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-success-sync",
        # FIXME: results 'outputs' query parameter (https://github.com/crim-ca/weaver/issues/733)
        # (support pre-filtering with 'outputs' in body already available, above feature is extra at job post-execution)
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-param-outputs",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-param-outputs-empty",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-param-outputs-omit",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-results-param-outputs-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/job-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/landingpage-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/landingpage-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/pl-links",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-exception/no-such-process",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-auto-execution-mode",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-default-execution-mode",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-default-outputs",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/process-execute-empty-outputs"
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-input-array",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-input-inline-bbox",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-input-inline-binary",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-input-mixed-type",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-input-inline-object",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-input-validation",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-inputs",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-op",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/process-execute-omitted-outputs"
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-request",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-success-async",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/process-execute-success-async-outputs"
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/process-execute-success-async-outputs-omitted"
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/process-execute-success-async-outputs-empty"
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/core/process-execute-success-sync-empty-outputs"
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-sync-document",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-sync-raw-mixed-multi",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-sync-raw-ref",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-sync-raw-value-multi",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-execute-sync-raw-value-one",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/pl-limit-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/pl-limit-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-list",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/process-list-success",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/core/test-process",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/dismiss",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/dismiss/job-dismiss-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/dismiss/job-dismiss-success",
    ] + ([
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/html",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/html/content",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/html/definition",
    ] if ogcapi_proc_html else []) + [
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/json",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/json/definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/datetime-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/datetime-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/duration-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/duration-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/links",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/jl-limit-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/job-list-op",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/processID-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/processID-mandatory",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/processid-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/status-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/status-response",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/type-definition",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/job-list/type-response",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/array-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/bbox-crs-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/bbox-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/binary-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/binary-input-value-qualified",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/boolean-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/complex-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/f-definition",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/f-response",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/input-by-reference",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/input-cardinality",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/input-query-parameter-values",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/input-query-parameters",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/numeric-input-value",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/output",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/prefer-definition",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/prefer-response",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/process-execute-op",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/kvp-execute/string-input-value",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30",  # OpenAPI 3.0
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30/completeness",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30/exceptions-codes",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30/oas-definition-1",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30/oas-definition-2",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30/oas-impl",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/oas30/security",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/input-def",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/input-mixed-type",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/inputs-def",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/json-encoding",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/output-def",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/output-mixed-type",
        f"{sd.OGC_API_PROC_PART1_BASE_URI}/req/ogc-process-description/outputs-def",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/query-param-profile",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/query-param-profile/definition",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/query-param-profile/response",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/rec/query-param-profile/link-header",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/per/query-param-profile/profiles-of-media-type",
        # ------ Part 3 Collection definitions migrated to Part 1 Core v2.0 ------
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-input",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-input/collection-access",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-input/referenced-collection",
        # FIXME: Collection Outputs (https://github.com/crim-ca/weaver/issues/683)
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-output",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-output/collection-response",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-output/data-access-mechanisms",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-output/landing-page",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-output/landing-page-response",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/collection-output/response-query-parameter",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/per/collection-output/expiry",
        # FIXME: Collection 'properties'
        #  (https://github.com/crim-ca/weaver/issues/750, PR https://github.com/crim-ca/weaver/pull/752)
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/input-fields-modifiers/derived-fields",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/input-fields-modifiers/filtering",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/input-fields-modifiers/sorting",
        # FIXME: Collection Outputs (https://github.com/crim-ca/weaver/issues/683)
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/output-fields-modifiers/derived-fields",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/output-fields-modifiers/filtering",
        # f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/output-fields-modifiers/sorting",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/remote-collections/collection-access",
        f"{sd.OGC_API_PROC_PART1_V2_BASE_URI}/req/remote-collections/referenced-collection",
        # ------------------------------------------------------------------------
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/cwl",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/cwl/deploy-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/cwl/deploy-response-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/cwl/deploy-response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/cwl/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/cwl/replace-response",
        # FIXME: support 'docker' direct deployment without CWL?
        # f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/docker",
        # f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/docker/deploy-body",
        # f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/docker/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/deploy-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/deploy-post-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/deploy-unsupported-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/replace-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/replace-put-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/replace-unsupported-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/undeploy/delete-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/undeploy/response-immutable-success",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/undeploy/response-immutable",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/undeploy/response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/undeploy/mutable-process",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/process-list-success",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/static-indicator",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/test-process",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/dru/test-process",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/deploy-replace-undeploy",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg/deploy-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg/deploy-response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg/deploy-response-duplicate",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg/deploy-response-success",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/conf/ogcapppkg/replace-response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/execution-unit",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/deploy-body",
        # FIXME: multi-CWL $graph (class: Workflow), must allow section of 1 with 'w' query param
        # (https://github.com/crim-ca/weaver/issues/739)
        # f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/deploy-w-param",
        # f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/deploy-exception-workflow-not-found",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/package-response-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/cwl/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/per/deploy-replace-undeploy/additional-status-codes",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/per/deploy-replace-undeploy/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/per/deploy-replace-undeploy/replace-response-insert",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/per/cwl/multipart-cwl-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/rec/deploy-replace-undeploy/deploy-body-ogcapppkg",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/rec/deploy-replace-undeploy/package-response-cwl",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/rec/deploy-replace-undeploy/package-response-ogcapppkg",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/rec/deploy-replace-undeploy/replace-body-ogcapppkg",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-post-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-response-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-response-pid",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/deploy-unsupported-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/package-get-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/package-response-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/package-response-success",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/replace-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/replace-put-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/replace-response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/replace-response-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/replace-unsupported-content-type",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/resources-endpoint",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/resource-endpoint",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/static-indicator",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/undeploy-delete-op",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/undeploy-response",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/deploy-replace-undeploy/ogcapppkg",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/dru/mutable-process",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/dru/test-process",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/deploy-body",
        # FIXME: support 'docker' direct deployment without CWL?
        # f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/execution-unit-docker",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/package-response-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/process-description",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/profile-docker",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/replace-body",
        f"{sd.OGC_API_PROC_PART2_BASE_URI}/req/ogcapppkg/schema",
        # FIXME: below partially, for full Part 3, would need $graph support
        # (see https://github.com/crim-ca/weaver/issues/56 and below '/conf/app-pck/cwl')
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/cwl-workflows",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/cwl-workflows",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/nested-processes",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/remote-core-processes",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/collection-input",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/remote-collections",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/input-fields-modifiers",
        # FIXME: Collection Outputs (https://github.com/crim-ca/weaver/issues/683)
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/output-fields-modifiers",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/deployable-workflows",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/collection-output",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/collection-input",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/collection-output",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/deployable-workflows",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/input-fields-modifiers",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/output-fields-modifiers",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/nested-processes",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/remote-collections",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/remote-collections/collection-access",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/remote-collections/referenced-collection",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/remote-collections/process-execution",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/remote-core-processes",
        f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/remote-core-processes/referenced-process",
        # FIXME: support openEO processes (https://github.com/crim-ca/weaver/issues/564)
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/conf/openeo-workflows",
        # f"{sd.OGC_API_PROC_PART3_BASE_URI}/req/openeo-workflows",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/conf/job-management",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/conf/jm/create/post-op",
        # see 'weaver.status.map_status'
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/per/job-management/additional-status-codes",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/per/job-management/create-body",              # Weaver has XML for WPS
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/per/job-management/create-content-schema",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/per/job-management/update-body",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/per/job-management/update-content-schema",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/rec/job-management/create-body-ogcapi-processes",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/rec/job-management/update-body-ogcapi-processes",
        # FIXME: support openEO processes (https://github.com/crim-ca/weaver/issues/564)
        # f"{sd.OGC_API_PROC_PART4_BASE_URI}/rec/job-management/create-body-openeo",
        # f"{sd.OGC_API_PROC_PART4_BASE_URI}/rec/job-management/update-body-openeo",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-post-op",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-content-type",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-response-body",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-response-jobid",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-response-success",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-unsupported-schema",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/create-unsupported-media-type",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/definition-get-op",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/definition-response-body",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/definition-response-body-ogcapi",
        # FIXME: support openEO job graph (https://github.com/crim-ca/weaver/issues/564)
        # f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/definition-response-body-alternate",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/definition-response-success",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/start-post-op",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/start-response",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/update-body",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/update-content-type",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/update-patch-op",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/update-response",
        f"{sd.OGC_API_PROC_PART4_BASE_URI}/req/job-management/update-response-locked",
    ] + ([
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/conf/provenance",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-get-op",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-response",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-missing",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-unsupported-format",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-namespaces",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-job-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-process-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-job-activity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-input-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-result-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-collection-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/provenance/prov-content-file-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/provenance/prov-job-status-link",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/provenance/prov-content-type-json",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/provenance/prov-content-data-entity",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/provenance/prov-content-timing",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/provenance/prov-content-software-agent",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/provenance/prov-content-associations",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/per/provenance/prov-content-negotiation",
    ] if ogcapi_proc_prov else []) + [
        # OGC API - Processes - Part 5: Provenance and Profiles, 'metadata-profiles' conformance class
        # (see https://github.com/opengeospatial/ogcapi-processes/pull/637)
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/conf/metadata-profiles",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/profile-link",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/role-register",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/concept-relations",
        # '?metadata[<role>]=<profile>' query filtering of process listing (GET method only, JSON/HTML content)
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-parameter",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-matching",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-options",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-method",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/invalid-metadata-profile",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/invalid-role",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-curie-matching",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/per/metadata-profiles/safe-curie",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/per/metadata-profiles/query-optional",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/per/metadata-profiles/query-literal-brackets",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/rec/metadata-profiles/query-literal-brackets-error",
        # FIXME: HTTP QUERY method not implemented. Require OpenAPI 3.2 and custom tweaks of CorniceSwagger
        # f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-content",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/query-compression",
        f"{sd.OGC_API_PROC_PART5_BASE_URI}/req/metadata-profiles/unsupported-metadata-encoding",
    ] + [
        # OGC API - Processes - 'Part 6: Versioning' (unofficial)
        # (see https://github.com/opengeospatial/ogcapi-processes/pull/578)
        f"{sd.OGC_API_PROC_PART6_BASE_URI}/rec/versioning/replace-response-links"
    ] + [
        # FIXME: employ 'weaver.wps_restapi.quotation.utils.check_quotation_supported' to add below conditionally
        # FIXME: https://github.com/crim-ca/weaver/issues/156  (billing/quotation)
        # https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/billing
        # https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/quotation
        # FIXME: (CWL App Package) https://github.com/crim-ca/weaver/issues/294
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app/cmd-line",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app/cmd-line",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app/container",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app/container",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app/registry",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app/registry",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app-stage-in",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app/stac-input",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app/stac-input",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app-stage-out",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-stage-out",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app/stac-out",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app/stac-out",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/rec/app/stac-out-metadata",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/rec/conf/stac-out-metadata",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app-pck",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck",
        # FIXME: Support embedded step definition in CWL (https://github.com/crim-ca/weaver/issues/56)
        #   Allow definition of a '$graph' with list of Workflow + >=1 CommandLineTool all together
        #   see: https://docs.ogc.org/bp/20-089r1.html#toc28
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app-pck/cwl",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck/cwl",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck/clt",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck/wf",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck/wf-inputs",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck/metadata",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/rec/app-pck/fan-out",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app-pck-stage-in",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        #   not sure about requirement: "staging of EO products SHALL be of type 'Directory'."
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck-stage-in/clt-stac",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck-stage-in/wf-stac",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/app-pck-stage-out",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck-stage-out",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/app-pck-stage-out/output-stac"
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/plt",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt/api",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt/inputs",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt/file",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/plt-stage-in",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt-stage-in/input-stac",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt-stage-in/stac-stage",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/conf/plt-stage-out",
        f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt-stage-out",
        # f"{sd.OGC_API_PROC_EOAP_BP_BASE_URI}/req/plt-stage-out/stac-stage",
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
    # bare base URLs (no sub-path) must include a trailing slash to satisfy strict URL schema validation
    weaver_url_href = f"{weaver_url}/"
    weaver_api_url_href = f"{weaver_api_url}/"
    weaver_links = [
        {"href": weaver_url_href, "rel": "self", "type": ContentType.APP_JSON, "title": "This landing page."},
        {"href": weaver_conform_url, "rel": sd.OGC_API_PROC_REL_CONFORMANCE_URI,
         "type": ContentType.APP_JSON, "title": "Conformance classes implemented by this service."},
        {"href": __meta__.__license_url__, "rel": "license",
         "type": ContentType.TEXT_PLAIN, "title": __meta__.__license_long__}
    ]
    if weaver_api:
        weaver_links.extend([
            {"href": weaver_api_url_href,
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
             "rel": sd.OGC_API_PROC_REL_PROCESSES_URI, "type": ContentType.APP_JSON,
             "title": "Processes offered by this service."},
            {"href": f"{weaver_url}{sd.processes_queryables_service.path}",
             "rel": sd.OGC_API_REL_QUERYABLES_URI, "type": ContentType.APP_SCHEMA_JSON,
             "title": "Supported process queryables."},
            {"href": f"{weaver_url}{sd.processes_sortables_service.path}",
             "rel": sd.OGC_API_REL_SORTABLES_URI, "type": ContentType.APP_SCHEMA_JSON,
             "title": "Supported process sortables."},
            {"href": weaver_process_url,
             "rel": sd.OGC_API_REL_CATALOG_URI, "type": ContentType.APP_JSON,
             "title": "Local resources catalog of processes offered by this service."},
            {"href": f"{weaver_url}{sd.jobs_queryables_service.path}",
             "rel": sd.OGC_API_REL_QUERYABLES_URI, "type": ContentType.APP_SCHEMA_JSON,
             "title": "Supported job queryables."},
            {"href": f"{weaver_url}{sd.jobs_sortables_service.path}",
             "rel": sd.OGC_API_REL_SORTABLES_URI, "type": ContentType.APP_SCHEMA_JSON,
             "title": "Supported job sortables."},
            {"href": sd.OGC_API_REPO_URL,
             "rel": "ogcapi-processes-repository", "type": ContentType.TEXT_HTML,
             "title": "OGC API - Processes schema definitions repository."},
            {"href": weaver_jobs_url,
             "rel": sd.OGC_API_PROC_REL_JOB_LIST_URI, "type": ContentType.APP_JSON,
             "title": "Job search and listing endpoint of executions registered under this service."},
            {"href": weaver_jobs_url,
             "rel": sd.OGC_API_REL_CATALOG_URI, "type": ContentType.APP_JSON,
             "title": "Local resources catalog of jobs registered under this service."},
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
                {"name": "api", "enabled": weaver_api, "url": weaver_api_url_href,
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


@sd.queryables_service.get(
    tags=[sd.TAG_API],
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas={"200": sd.CatalogLinksResponseSchema()},
)
def api_queryables(request):
    # type: (PyramidRequest) -> JSON
    """
    Links to the queryables of each collection.
    """
    return get_catalog_links(request, sd.OGC_API_REL_QUERYABLES_URI, {
        "process": sd.processes_queryables_service,
        "job": sd.jobs_queryables_service,
    })


@sd.sortables_service.get(
    tags=[sd.TAG_API],
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas={"200": sd.CatalogLinksResponseSchema()},
)
def api_sortables(request):
    # type: (PyramidRequest) -> JSON
    """
    Links to the sortables of each collection.
    """
    return get_catalog_links(request, sd.OGC_API_REL_SORTABLES_URI, {
        "process": sd.processes_sortables_service,
        "job": sd.jobs_sortables_service,
    })


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
    swagger.ignore_methods = []  # don't ignore HEAD or OPTIONS (explicitly defined by routes)
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
    swagger_json["tags"].sort(key=lambda tag: (tag["name"] == sd.TAG_DEPRECATED, tag["name"]))
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
    response = HTTPOk(json=spec, content_type=ContentType.APP_OAS_JSON)
    response.vary = "Accept-Encoding"
    if accepts_gzip_encoding(request.headers.get("Accept-Encoding", "")):
        response.encode_content("gzip")
    return response


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
        sd.queryables_service,
        sd.sortables_service,
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
