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
from pyramid.settings import asbool
from simplejson import JSONDecodeError

from weaver import __meta__
from weaver.formats import ContentType, OutputFormat
from weaver.owsexceptions import OWSException
from weaver.utils import get_header, get_settings, get_weaver_url
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_extras import OAS3TypeConversionDispatcher
from weaver.wps_restapi.constants import ConformanceCategory
from weaver.wps_restapi.utils import get_wps_restapi_base_url, wps_restapi_base_path

if TYPE_CHECKING:
    from typing import Callable, List, Optional

    from weaver.typedefs import JSON, SettingsType, TypedDict
    from weaver.wps_restapi.constants import AnyConformanceCategory

    Conformance = TypedDict("Conformance", {
        "conformsTo": List[str]
    }, total=True)


LOGGER = logging.getLogger(__name__)


def get_conformance(category):
    # type: (Optional[AnyConformanceCategory]) -> Conformance
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
    ogcapi_common = "http://www.opengis.net/spec/ogcapi-common-2/1.0"
    ogcapi_proc_core = "http://www.opengis.net/spec/ogcapi-processes-1/1.0"
    ogcapi_proc_part2 = "http://www.opengis.net/spec/ogcapi-processes-2/1.0"
    ogcapi_proc_apppkg = "http://www.opengis.net/spec/eoap-bp/1.0"
    # FIXME: https://github.com/crim-ca/weaver/issues/412
    # ogcapi_proc_part3 = "http://www.opengis.net/spec/ogcapi-processes-3/1.0"
    conformance = [
        # "http://www.opengis.net/spec/wfs-1/3.0/req/core",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/oas30",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/html",
        # "http://www.opengis.net/spec/wfs-1/3.0/req/geojson",
        ows_wps1 + "/",
        ows_wps2 + "/",
        ows_wps2 + "/req/service/binding/rest-json/core",
        ows_wps2 + "/req/service/binding/rest-json/oas30",  # /ows/wps?...&f=json
        # ows_wps2 + "/req/service/binding/rest-json/html"
        ogcapi_common + "/conf/core",
        ogcapi_common + "/per/core/additional-link-relations",
        ogcapi_common + "/per/core/additional-status-codes",
        ogcapi_common + "/per/core/query-param-name-specified",
        ogcapi_common + "/per/core/query-param-name-tolerance",
        ogcapi_common + "/per/core/query-param-value-specified",
        ogcapi_common + "/per/core/query-param-value-tolerance",
        ogcapi_common + "/rec/core/cross-origin",
        # ogcapi_common + "/rec/core/etag",
        # ogcapi_common + "/rec/core/html",
        ogcapi_common + "/rec/core/json",
        # ogcapi_common + "/rec/core/link-header",
        # FIXME: error details (for all below: https://github.com/crim-ca/weaver/issues/320)
        # ogcapi_common + "/rec/core/problem-details",
        # ogcapi_common + "/rec/core/query-param-capitalization",
        # ogcapi_common + "/rec/core/query-param-value-special",
        # FIXME: https://github.com/crim-ca/weaver/issues/112 (language/translate)
        # ogcapi_common + "/rec/core/string-i18n",
        ogcapi_common + "/req/collections",
        # ogcapi_common + "/req/collections/collection-definition",
        # ogcapi_common + "/req/collections/src-md-op",
        # ogcapi_common + "/req/collections/src-md-success",
        # ogcapi_common + "/req/collections/rc-bbox-collection-response",
        ogcapi_common + "/req/collections/rc-bbox-unsupported",
        ogcapi_common + "/req/collections/rc-datetime-collection-response",
        ogcapi_common + "/req/collections/rc-datetime-unsupported",
        ogcapi_common + "/req/collections/rc-limit-unsupported",
        ogcapi_common + "/req/collections/rc-limit-collection-response",
        ogcapi_common + "/req/collections/rc-links",
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
        ogcapi_common + "/req/core/http",
        ogcapi_common + "/req/core/query-param-capitalization",
        ogcapi_common + "/req/core/query-param-list-delimiter",
        ogcapi_common + "/req/core/query-param-list-empty",
        ogcapi_common + "/req/core/query-param-list-escape",
        # ogcapi_common + "/req/core/query-param-name-unknown",
        ogcapi_common + "/req/core/query-param-value-boolean",
        ogcapi_common + "/req/core/query-param-value-decimal",
        ogcapi_common + "/req/core/query-param-value-double",
        ogcapi_common + "/req/core/query-param-value-integer",
        ogcapi_common + "/req/core/query-param-value-invalid",
        # FIXME: Following applicable if result output endpoint to offer content returned directly is added
        #   https://github.com/crim-ca/weaver/issues/18
        ogcapi_common + "/req/geojson",
        # ogcapi_common + "/req/geojson/content",
        # ogcapi_common + "/req/geojson/definition",
        # FIXME: https://github.com/crim-ca/weaver/issues/210
        # https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/requirements_class_html.adoc
        # ogcapi_common + "/req/html",
        # ogcapi_common + "/req/html/content",
        # ogcapi_common + "/req/html/definition",
        ogcapi_common + "/req/json",
        ogcapi_common + "/req/json/content",
        ogcapi_common + "/req/json/definition",
        ogcapi_common + "/req/landing-page",
        ogcapi_common + "/req/oas30",  # OpenAPI 3.0
        # ogcapi_common + "/req/simple-query",
        # ogcapi_common + "/req/umd-collection",
        ogcapi_proc_core + "/conf/core",
        # FIXME: https://github.com/crim-ca/weaver/issues/230
        # ogcapi_proc_core + "/conf/callback",
        ogcapi_proc_core + "/conf/dismiss",
        # FIXME: https://github.com/crim-ca/weaver/issues/210
        # ogcapi_proc_core + "/conf/html",
        # ogcapi_proc_core + "/conf/html/content",
        # ogcapi_proc_core + "/conf/html/definition",
        ogcapi_proc_core + "/conf/json",
        ogcapi_proc_core + "/conf/job-list",
        ogcapi_proc_core + "/conf/oas30",
        ogcapi_proc_core + "/per/core/additional-status-codes",
        ogcapi_proc_core + "/per/core/alternative-process-description",
        ogcapi_proc_core + "/per/core/alternative-process-paths",
        ogcapi_proc_core + "/per/core/api-definition-uri",
        # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
        # ogcapi_proc_core + "/per/core/process-execute-input-inline-bbox",
        ogcapi_proc_core + "/per/core/process-execute-sync-job",
        ogcapi_proc_core + "/per/core/limit-response",
        # ogcapi_proc_core + "/per/core/limit-default-minimum-maximum",
        ogcapi_proc_core + "/per/core/prev",
        ogcapi_proc_core + "/per/job-list/limit-response",
        ogcapi_proc_core + "/per/job-list/prev",
        # ogcapi_proc_core + "/rec/core/access-control-expose-headers",
        ogcapi_proc_core + "/rec/core/api-definition-oas",
        ogcapi_proc_core + "/rec/core/cross-origin",
        ogcapi_proc_core + "/rec/core/content-length",
        # ogcapi_proc_core + "/rec/core/html",
        # ogcapi_proc_core + "/rec/core/http-head",
        ogcapi_proc_core + "/rec/core/job-status",
        ogcapi_proc_core + "/rec/core/job-results-async-many-json-prefer-none",
        # FIXME: https://github.com/crim-ca/weaver/issues/414
        # ogcapi_proc_core + "/rec/core/job-results-async-many-json-prefer-minimal",
        # ogcapi_proc_core + "/rec/core/job-results-async-many-json-prefer-representation",
        # ogcapi_proc_core + "/per/core/job-results-async-many-other-formats",
        ogcapi_proc_core + "/rec/core/process-execute-sync-many-json-prefer-none",
        # ogcapi_proc_core + "/rec/core/process-execute-sync-many-json-prefer-minimal",
        # ogcapi_proc_core + "/rec/core/process-execute-sync-many-json-prefer-representation",
        # ogcapi_proc_core + "/rec/core/link-header",
        ogcapi_proc_core + "/rec/core/ogc-process-description",
        # FIXME: error details (for all below: https://github.com/crim-ca/weaver/issues/320)
        # ogcapi_proc_core + "/rec/core/problem-details",
        ogcapi_proc_core + "/rec/core/process-execute-handle-prefer",
        ogcapi_proc_core + "/rec/core/process-execute-honor-prefer",
        ogcapi_proc_core + "/rec/core/process-execute-mode-auto",
        ogcapi_proc_core + "/rec/core/process-execute-preference-applied",
        ogcapi_proc_core + "/rec/core/process-execute-sync-document-ref",
        ogcapi_proc_core + "/rec/core/next-1",
        ogcapi_proc_core + "/rec/core/next-2",
        ogcapi_proc_core + "/rec/core/next-3",
        # ogcapi_proc_core + "/rec/core/test-process",
        ogcapi_proc_core + "/rec/job-list/job-list-landing-page",
        ogcapi_proc_core + "/rec/job-list/next-1",
        ogcapi_proc_core + "/rec/job-list/next-2",
        ogcapi_proc_core + "/rec/job-list/next-3",
        # FIXME: https://github.com/crim-ca/weaver/issues/230
        # ogcapi_proc_core + "/req/callback/job-callback",
        ogcapi_proc_core + "/req/core",
        ogcapi_proc_core + "/req/core/api-definition-op",
        ogcapi_proc_core + "/req/core/api-definition-success",
        ogcapi_proc_core + "/req/core/conformance-op",
        ogcapi_proc_core + "/req/core/conformance-success",
        ogcapi_proc_core + "/req/core/http",
        ogcapi_proc_core + "/req/core/job",
        ogcapi_proc_core + "/req/core/job-exception-no-such-job",
        ogcapi_proc_core + "/req/core/job-results-exception/no-such-job",
        ogcapi_proc_core + "/req/job-list/links",
        ogcapi_proc_core + "/req/job-list/jl-limit-definition",
        ogcapi_proc_core + "/req/job-list/job-list-op",
        ogcapi_proc_core + "/req/job-list/processID-definition",
        ogcapi_proc_core + "/req/job-list/processID-mandatory",
        ogcapi_proc_core + "/req/job-list/processid-response",
        ogcapi_proc_core + "/req/job-list/type-definition",
        ogcapi_proc_core + "/req/job-list/type-response",
        ogcapi_proc_core + "/req/core/job-results-exception/results-not-ready",
        ogcapi_proc_core + "/req/core/job-results-failed",
        ogcapi_proc_core + "/req/core/job-results",
        ogcapi_proc_core + "/req/core/job-results-async-document",
        # FIXME: support raw multipart (https://github.com/crim-ca/weaver/issues/376)
        # ogcapi_proc_core + "/req/core/job-results-async-raw-mixed-multi",
        ogcapi_proc_core + "/req/core/job-results-async-raw-ref",
        # ogcapi_proc_core + "/req/core/job-results-async-raw-value-multi",
        ogcapi_proc_core + "/req/core/job-results-async-raw-value-one",
        ogcapi_proc_core + "/req/core/job-results-success-sync",
        ogcapi_proc_core + "/req/core/job-success",
        ogcapi_proc_core + "/req/core/landingpage-op",
        ogcapi_proc_core + "/req/core/landingpage-success",
        ogcapi_proc_core + "/req/core/pl-links",
        ogcapi_proc_core + "/req/core/process",
        ogcapi_proc_core + "/req/core/process-success",
        ogcapi_proc_core + "/req/core/process-exception/no-such-process",
        ogcapi_proc_core + "/req/core/process-execute-auto-execution-mode",
        ogcapi_proc_core + "/req/core/process-execute-default-execution-mode",
        ogcapi_proc_core + "/req/core/process-execute-default-outputs",
        ogcapi_proc_core + "/req/core/process-execute-input-array",
        # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
        # ogcapi_proc_core + "/req/core/process-execute-input-inline-bbox",
        # FIXME: support byte/binary type (string + format:byte) ?
        # ogcapi_proc_core + "/req/core/process-execute-input-inline-binary",
        ogcapi_proc_core + "/req/core/process-execute-input-mixed-type",
        ogcapi_proc_core + "/req/core/process-execute-input-inline-object",
        ogcapi_proc_core + "/req/core/process-execute-input-validation",
        ogcapi_proc_core + "/req/core/process-execute-inputs",
        ogcapi_proc_core + "/req/core/process-execute-op",
        ogcapi_proc_core + "/req/core/process-execute-request",
        ogcapi_proc_core + "/req/core/process-execute-success-async",
        ogcapi_proc_core + "/req/core/process-execute-sync-document",
        # ogcapi_proc_core + "/req/core/process-execute-sync-raw-mixed-multi",
        ogcapi_proc_core + "/req/core/process-execute-sync-raw-ref",
        # FIXME: support raw multipart (https://github.com/crim-ca/weaver/issues/376)
        # ogcapi_proc_core + "/req/core/process-execute-sync-raw-value-multi",
        ogcapi_proc_core + "/req/core/process-execute-sync-raw-value-one",
        ogcapi_proc_core + "/req/core/pl-limit-definition",
        ogcapi_proc_core + "/req/core/pl-limit-response",
        ogcapi_proc_core + "/req/core/process-list",
        ogcapi_proc_core + "/req/core/process-list-success",
        # ogcapi_proc_core + "/req/core/test-process",
        ogcapi_proc_core + "/req/dismiss",
        ogcapi_proc_core + "/req/dismiss/job-dismiss-op",
        ogcapi_proc_core + "/req/dismiss/job-dismiss-success",
        # https://github.com/opengeospatial/ogcapi-processes/blob/master/core/clause_7_core.adoc#sc_requirements_class_html
        # ogcapi_proc_core + "/req/html",
        # ogcapi_proc_core + "/req/html/content",
        # ogcapi_proc_core + "/req/html/definition",
        # FIXME: https://github.com/crim-ca/weaver/issues/231
        #  List all supported requirements, recommendations and abstract tests
        ogcapi_proc_core + "/conf/ogc-process-description",
        ogcapi_proc_core + "/req/json",
        ogcapi_proc_core + "/req/json/definition",
        ogcapi_proc_core + "/req/oas30",  # OpenAPI 3.0
        ogcapi_proc_core + "/req/oas30/completeness",
        ogcapi_proc_core + "/req/oas30/exceptions-codes",
        ogcapi_proc_core + "/req/oas30/oas-definition-1",
        ogcapi_proc_core + "/req/oas30/oas-definition-2",
        ogcapi_proc_core + "/req/oas30/oas-impl",
        ogcapi_proc_core + "/req/oas30/security",
        # FIXME: https://github.com/crim-ca/weaver/issues/245 (schema field)
        # ogcapi_proc_core + "/req/ogc-process-description/input-def",
        # ogcapi_proc_core + "/req/ogc-process-description/input-mixed-type",
        ogcapi_proc_core + "/req/ogc-process-description/inputs-def",
        ogcapi_proc_core + "/req/ogc-process-description/json-encoding",
        # FIXME: https://github.com/crim-ca/weaver/issues/245 (schema field)
        # ogcapi_proc_core + "/req/ogc-process-description/output-def",
        # ogcapi_proc_core + "/req/ogc-process-description/output-mixed-type",
        ogcapi_proc_core + "/req/ogc-process-description/outputs-def",
        ogcapi_proc_part2 + "/per/deploy-replace-undeploy/replace/body",
        ogcapi_proc_part2 + "/rec/deploy-replace-undeploy/deploy/body-ogcapppkg",
        ogcapi_proc_part2 + "/rec/deploy-replace-undeploy/replace/body-ogcapppkg",
        ogcapi_proc_part2 + "/req/ogcapppkg",
        ogcapi_proc_part2 + "/req/ogcapppkg/execution-unit-docker",
        ogcapi_proc_part2 + "/req/ogcapppkg/process-description",
        # FIXME: 'deploymentProfile = http://www.opengis.net/profiles/eoc/dockerizedApplication'
        #   https://github.com/crim-ca/weaver/issues/319
        # ogcapi_proc_part2 + "/req/ogcapppkg/profile-docker",
        ogcapi_proc_part2 + "/req/ogcapppkg/schema",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/deploy/body",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/deploy/content-type",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/deploy/post-op",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/deploy/response-body",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/deploy/response-pid",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/deploy/response",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/replace/body",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/replace/content-type",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/replace/put-op",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/replace/response",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/static/indicator",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/undeploy/delete-op",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/undeploy/response",
        ogcapi_proc_part2 + "/req/deploy-replace-undeploy/ogcapppkg",
        # FIXME: support part 3: workflows (?)
        #   https://github.com/crim-ca/weaver/issues/412
        # ogcapi_proc_part3 + "/req/workflows",
        # ogcapi_proc_part3 + "/req/workflows/collection/body",
        # ogcapi_proc_part3 + "/req/workflows/collection/content-type",
        # ogcapi_proc_part3 + "/req/workflows/collection/post-op",
        # ogcapi_proc_part3 + "/req/workflows/collection/response-body",
        # ogcapi_proc_part3 + "/req/workflows/collection/response",
        # FIXME: https://github.com/crim-ca/weaver/issues/156  (billing/quotation)
        # https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/billing
        # https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/quotation
        # FIXME: (CWL App Package) https://github.com/crim-ca/weaver/issues/294
        ogcapi_proc_apppkg + "/conf/app",
        ogcapi_proc_apppkg + "/req/app",
        ogcapi_proc_apppkg + "/conf/app/cmd-line",
        ogcapi_proc_apppkg + "/req/app/cmd-line",
        ogcapi_proc_apppkg + "/conf/app/container",
        ogcapi_proc_apppkg + "/req/app/container",
        ogcapi_proc_apppkg + "/conf/app/registry",
        ogcapi_proc_apppkg + "/req/app/registry",
        ogcapi_proc_apppkg + "/conf/app-stage-in",
        ogcapi_proc_apppkg + "/req/app-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        # ogcapi_proc_apppkg + "/conf/app/stac-input",
        # ogcapi_proc_apppkg + "/req/app/stac-input",
        ogcapi_proc_apppkg + "/conf/app-stage-out",
        ogcapi_proc_apppkg + "/req/app-stage-out",
        # ogcapi_proc_apppkg + "/req/app/stac-out",
        # ogcapi_proc_apppkg + "/conf/app/stac-out",
        # ogcapi_proc_apppkg + "/rec/app/stac-out-metadata",
        # ogcapi_proc_apppkg + "/rec/conf/stac-out-metadata",
        ogcapi_proc_apppkg + "/conf/app-pck",
        ogcapi_proc_apppkg + "/req/app-pck",
        # FIXME: Support embedded step definition in CWL (https://github.com/crim-ca/weaver/issues/56)
        #   Allow definition of a '$graph' with list of Workflow + >=1 CommandLineTool all together
        #   see: https://docs.ogc.org/bp/20-089r1.html#toc28
        # ogcapi_proc_apppkg + "/conf/app-pck/cwl",
        # ogcapi_proc_apppkg + "/req/app-pck/cwl",
        ogcapi_proc_apppkg + "/req/app-pck/clt",
        ogcapi_proc_apppkg + "/req/app-pck/wf",
        ogcapi_proc_apppkg + "/req/app-pck/wf-inputs",
        ogcapi_proc_apppkg + "/req/app-pck/metadata",
        # FIXME: Support Fan-In/Fan-Out workflow (https://github.com/crim-ca/weaver/issues/105)
        # ogcapi_proc_apppkg + "/rec/app-pck/fan-out",
        # ogcapi_proc_apppkg + "/conf/app-pck-stage-in",
        # ogcapi_proc_apppkg + "/req/app-pck-stage-in",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        #   not sure about requirement: "staging of EO products SHALL be of type 'Directory'."
        # ogcapi_proc_apppkg + "/req/app-pck-stage-in/clt-stac",
        # ogcapi_proc_apppkg + "/req/app-pck-stage-in/wf-stac",
        # ogcapi_proc_apppkg + "/conf/app-pck-stage-out",
        # ogcapi_proc_apppkg + "/req/app-pck-stage-out",
        # ogcapi_proc_apppkg + "/req/app-pck-stage-out/output-stac"
        ogcapi_proc_apppkg + "/conf/plt",
        ogcapi_proc_apppkg + "/req/plt",
        ogcapi_proc_apppkg + "/req/plt/api",
        ogcapi_proc_apppkg + "/req/plt/inputs",
        ogcapi_proc_apppkg + "/req/plt/file",
        # FIXME: Support for STAC metadata (https://github.com/crim-ca/weaver/issues/103)
        # ogcapi_proc_apppkg + "/conf/plt-stage-in",
        # ogcapi_proc_apppkg + "/req/plt-stage-in",
        # ogcapi_proc_apppkg + "/req/plt-stage-in/input-stac",
        # ogcapi_proc_apppkg + "/req/plt-stage-in/stac-stage",
        # ogcapi_proc_apppkg + "/conf/plt-stage-out",
        # ogcapi_proc_apppkg + "/req/plt-stage-out",
        # ogcapi_proc_apppkg + "/req/plt-stage-out/stac-stage",
    ]
    if category not in [None, ConformanceCategory.ALL]:
        cat = f"/{category}/"
        conformance = filter(lambda item: cat in item, conformance)
    data = {"conformsTo": list(sorted(conformance))}
    return data


@sd.api_frontpage_service.get(tags=[sd.TAG_API], renderer=OutputFormat.JSON,
                              schema=sd.FrontpageEndpoint(), response_schemas=sd.get_api_frontpage_responses)
def api_frontpage(request):
    """
    Frontpage of Weaver.
    """
    settings = get_settings(request)
    return api_frontpage_body(settings)


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

    weaver_api = asbool(settings.get("weaver.wps_restapi"))
    weaver_api_url = get_wps_restapi_base_url(settings) if weaver_api else None
    weaver_api_oas_ui = weaver_api_url + sd.api_openapi_ui_service.path if weaver_api else None
    weaver_api_swagger = weaver_api_url + sd.api_swagger_ui_service.path if weaver_api else None
    weaver_api_doc = settings.get("weaver.wps_restapi_doc", None) if weaver_api else None
    weaver_api_ref = settings.get("weaver.wps_restapi_ref", None) if weaver_api else None
    weaver_api_spec = weaver_api_url + sd.openapi_json_service.path if weaver_api else None
    weaver_wps = asbool(settings.get("weaver.wps"))
    weaver_wps_url = get_wps_url(settings) if weaver_wps else None
    weaver_conform_url = weaver_url + sd.api_conformance_service.path
    weaver_process_url = weaver_url + sd.processes_service.path
    weaver_jobs_url = weaver_url + sd.jobs_service.path
    weaver_vault = asbool(settings.get("weaver.vault"))
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
             "rel": "service-desc", "type": ContentType.APP_JSON,
             "title": "OpenAPI specification of this service."},
            {"href": weaver_api_oas_ui,
             "rel": "service-doc", "type": ContentType.TEXT_HTML,
             "title": "Human readable OpenAPI documentation of this service."},
            {"href": weaver_api_spec,
             "rel": "OpenAPI", "type": ContentType.APP_JSON,
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
                ext_type = weaver_api_doc.split(".")[-1]
                doc_type = f"application/{ext_type}"
            else:
                doc_type = ContentType.TEXT_PLAIN  # default most basic type
            weaver_links.append({"href": weaver_api_doc, "rel": "documentation", "type": doc_type,
                                 "title": "API reference documentation about this service."})
        else:
            weaver_links.append({"href": __meta__.__documentation_url__, "rel": "documentation",
                                 "type": ContentType.TEXT_HTML,
                                 "title": "API reference documentation about this service."})
    if weaver_wps:
        weaver_links.extend([
            {"href": weaver_wps_url,
             "rel": "wps", "type": ContentType.TEXT_XML,
             "title": "WPS 1.0.0/2.0 XML endpoint of this service."},
            {"href": "http://docs.opengeospatial.org/is/14-065/14-065.html",
             "rel": "wps-specification", "type": ContentType.TEXT_HTML,
             "title": "WPS 1.0.0/2.0 definition of this service."},
            {"href": "http://schemas.opengis.net/wps/",
             "rel": "wps-schema-repository", "type": ContentType.TEXT_HTML,
             "title": "WPS 1.0.0/2.0 XML schemas repository."},
            {"href": "http://schemas.opengis.net/wps/1.0.0/wpsAll.xsd",
             "rel": "wps-schema-1", "type": ContentType.TEXT_XML,
             "title": "WPS 1.0.0 XML validation schemas entrypoint."},
            {"href": "http://schemas.opengis.net/wps/2.0/wps.xsd",
             "rel": "wps-schema-2", "type": ContentType.TEXT_XML,
             "title": "WPS 2.0 XML validation schemas entrypoint."},
        ])
    return {
        "message": "Weaver Information",
        "configuration": weaver_config,
        "description": __meta__.__description__,
        "parameters": [
            {"name": "api", "enabled": weaver_api, "url": weaver_api_url, "api": weaver_api_oas_ui},
            {"name": "vault", "enabled": weaver_vault},
            {"name": "wps", "enabled": weaver_wps, "url": weaver_wps_url},
        ],
        "links": weaver_links,
    }


@sd.api_versions_service.get(tags=[sd.TAG_API], renderer=OutputFormat.JSON,
                             schema=sd.VersionsEndpoint(), response_schemas=sd.get_api_versions_responses)
def api_versions(request):  # noqa: F811
    # type: (Request) -> HTTPException
    """
    Weaver versions information.
    """
    weaver_info = {"name": "weaver", "version": __meta__.__version__, "type": "api"}
    return HTTPOk(json={"versions": [weaver_info]})


@sd.api_conformance_service.get(tags=[sd.TAG_API], renderer=OutputFormat.JSON,
                                schema=sd.ConformanceEndpoint(), response_schemas=sd.get_api_conformance_responses)
def api_conformance(request):  # noqa: F811
    # type: (Request) -> HTTPException
    """
    Weaver specification conformance information.
    """
    cat = ConformanceCategory.get(request.params.get("category"), ConformanceCategory.CONFORMANCE)
    data = get_conformance(cat)
    return HTTPOk(json=data)


def get_openapi_json(http_scheme="http", http_host="localhost", base_url=None,
                     use_refs=True, use_docstring_summary=True, settings=None):
    # type: (str, str, Optional[str], bool, bool, Optional[SettingsType]) -> JSON
    """
    Obtains the JSON schema of Weaver OpenAPI from request and response views schemas.

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
    }
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

    swagger_json = swagger.generate(title=sd.API_TITLE, version=__meta__.__version__, info=swagger_info,
                                    base_path=swagger_base_path, openapi_spec=3)
    swagger_json["externalDocs"] = sd.API_DOCS
    return swagger_json


@cache_region("doc", sd.openapi_json_service.name)
def openapi_json_cached(*args, **kwargs):
    return get_openapi_json(*args, **kwargs)


@sd.openapi_json_service.get(tags=[sd.TAG_API], renderer=OutputFormat.JSON,
                             schema=sd.OpenAPIEndpoint(), response_schemas=sd.get_openapi_json_responses)
def openapi_json(request):  # noqa: F811
    # type: (Request) -> dict
    """
    Weaver OpenAPI schema definitions.
    """
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
    """
    Weaver OpenAPI schema definitions rendering using Swagger-UI viewer.
    """
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
    """
    Weaver OpenAPI schema definitions rendering using Redoc viewer.
    """
    return redoc_ui_cached(request)


def get_request_info(request, detail=None):
    # type: (Request, Optional[str]) -> JSON
    """
    Provided additional response details based on the request and execution stack on failure.
    """
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
    # type: (Callable[[Request], HTTPException]) -> Callable[[HTTPException, Request], HTTPException]
    """
    Decorator that adds additional detail in the response's JSON body if this is the returned content-type.
    """
    def format_response_details(response, request):
        # type: (HTTPException, Request) -> HTTPException
        http_response = function(request)
        http_headers = get_header("Content-Type", http_response.headers) or []
        req_headers = get_header("Accept", request.headers) or []
        if any([ContentType.APP_JSON in http_headers, ContentType.APP_JSON in req_headers]):
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
