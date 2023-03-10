"""
Schema definitions for `OpenAPI` generation and validation of data from received requests and returned responses.

This module should contain any and every definition in use to build the Swagger UI and the OpenAPI JSON schema
so that one can update the specification without touching any other files after the initial integration.

Schemas defined in this module are employed (through ``deserialize`` method calls) to validate that data conforms to
reported definitions. This makes the documentation of the API better aligned with resulting code execution under it.
It also provides a reference point for external users to understand expected data structures with complete schema
definitions generated on the exposed endpoints (JSON and Swagger UI).

The definitions are also employed to generate the `OpenAPI` definitions reported in the documentation published
on `Weaver`'s `ReadTheDocs` page.
"""
# pylint: disable=C0103,invalid-name
import colander
import datetime
import inspect
import os
import re
from copy import copy
from typing import TYPE_CHECKING

import duration
import jsonschema
import yaml
from babel.numbers import list_currencies
from colander import All, DateTime, Email, Length, Money, OneOf, Range, drop, null, required
from dateutil import parser as date_parser

from weaver import WEAVER_SCHEMA_DIR, __meta__
from weaver.config import WeaverFeature
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import AcceptLanguage, ContentType, OutputFormat
from weaver.owsexceptions import OWSMissingParameterValue
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_CUDA,
    CWL_REQUIREMENT_INIT_WORKDIR,
    CWL_REQUIREMENT_INLINE_JAVASCRIPT,
    CWL_REQUIREMENT_INPLACE_UPDATE,
    CWL_REQUIREMENT_LOAD_LISTING,
    CWL_REQUIREMENT_NETWORK_ACCESS,
    CWL_REQUIREMENT_RESOURCE,
    CWL_REQUIREMENT_SCATTER,
    CWL_REQUIREMENT_TIME_LIMIT,
    CWL_REQUIREMENT_WORK_REUSE,
    OAS_COMPLEX_TYPES,
    OAS_DATA_TYPES,
    PACKAGE_ARRAY_BASE,
    PACKAGE_ARRAY_ITEMS,
    PACKAGE_CUSTOM_TYPES,
    PACKAGE_ENUM_BASE,
    PACKAGE_TYPE_POSSIBLE_VALUES,
    WPS_LITERAL_DATA_TYPES,
    JobInputsOutputsSchema,
    ProcessSchema
)
from weaver.quotation.status import QuoteStatus
from weaver.sort import Sort, SortMethods
from weaver.status import JOB_STATUS_CODE_API, JOB_STATUS_SEARCH_API, Status
from weaver.utils import AWS_S3_BUCKET_REFERENCE_PATTERN, load_file
from weaver.visibility import Visibility
from weaver.wps_restapi.colander_extras import (
    NO_DOUBLE_SLASH_PATTERN,
    AllOfKeywordSchema,
    AnyOfKeywordSchema,
    BoundedRange,
    CommaSeparated,
    EmptyMappingSchema,
    ExpandStringList,
    ExtendedBoolean as Boolean,
    ExtendedFloat as Float,
    ExtendedInteger as Integer,
    ExtendedMappingSchema,
    ExtendedSchemaNode,
    ExtendedSequenceSchema,
    ExtendedString as String,
    NotKeywordSchema,
    OneOfCaseInsensitive,
    OneOfKeywordSchema,
    PermissiveMappingSchema,
    PermissiveSequenceSchema,
    SchemeURL,
    SemanticVersion,
    StrictMappingSchema,
    StringOneOf,
    StringRange,
    XMLObject
)
from weaver.wps_restapi.constants import ConformanceCategory
from weaver.wps_restapi.patches import ServiceOnlyExplicitGetHead as Service  # warning: don't use 'cornice.Service'

if TYPE_CHECKING:
    from typing import Any, Union
    from typing_extensions import TypedDict

    from weaver.typedefs import JSON, DatetimeIntervalType, SettingsType

    ViewInfo = TypedDict("ViewInfo", {"name": str, "pattern": str})


WEAVER_CONFIG_REMOTE_LIST = f"[{', '.join(WeaverFeature.REMOTE)}]"

API_TITLE = "Weaver REST API"
API_INFO = {
    "description": __meta__.__description__,
    "contact": {"name": __meta__.__authors__, "email": __meta__.__emails__, "url": __meta__.__source_repository__}
}
API_DOCS = {
    "description": f"{__meta__.__title__} documentation",
    "url": __meta__.__documentation_url__
}
DOC_URL = f"{__meta__.__documentation_url__}/en/latest"

CWL_VERSION = "v1.2"
CWL_REPO_URL = "https://github.com/common-workflow-language"
CWL_BASE_URL = "https://www.commonwl.org"
CWL_SPEC_URL = f"{CWL_BASE_URL}/#Specification"
CWL_USER_GUIDE_URL = f"{CWL_BASE_URL}/user_guide"
CWL_DOC_BASE_URL = f"{CWL_BASE_URL}/{CWL_VERSION}"
CWL_CMD_TOOL_URL = f"{CWL_DOC_BASE_URL}/CommandLineTool.html"
CWL_WORKFLOW_URL = f"{CWL_DOC_BASE_URL}/Workflow.html"
CWL_DOC_MESSAGE = (
    "Note that multiple formats are supported and not all specification variants or parameters "
    f"are presented here. Please refer to official CWL documentation for more details ({CWL_BASE_URL})."
)

IO_INFO_IDS = (
    "Identifier of the {first} {what}. To merge details between corresponding {first} and {second} "
    "{what} specifications, this is the value that will be used to associate them together."
)

# development references
OGC_API_REPO_URL = "https://github.com/opengeospatial/ogcapi-processes"
OGC_API_SCHEMA_URL = "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes"
OGC_API_SCHEMA_VERSION = "master"
OGC_API_SCHEMA_BASE = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}"
OGC_API_SCHEMA_CORE = f"{OGC_API_SCHEMA_BASE}/openapi/schemas/processes-core"
OGC_API_EXAMPLES_CORE = f"{OGC_API_SCHEMA_BASE}/core/examples"
# FIXME: OGC OpenAPI schema restructure (https://github.com/opengeospatial/ogcapi-processes/issues/319)
# OGC_API_SCHEMA_EXT_DEPLOY = f"{OGC_API_SCHEMA_BASE}/openapi/schemas/processes-dru"
OGC_API_SCHEMA_EXT_DEPLOY = f"{OGC_API_SCHEMA_BASE}/extensions/deploy_replace_undeploy/standard/openapi/schemas"
OGC_API_EXAMPLES_EXT_DEPLOY = f"{OGC_API_SCHEMA_BASE}/extensions/deploy_replace_undeploy/examples"
# not available yet:
OGC_API_SCHEMA_EXT_BILL = f"{OGC_API_SCHEMA_BASE}/extensions/billing/standard/openapi/schemas"
OGC_API_SCHEMA_EXT_QUOTE = f"{OGC_API_SCHEMA_BASE}/extensions/quotation/standard/openapi/schemas"
OGC_API_SCHEMA_EXT_WORKFLOW = f"{OGC_API_SCHEMA_BASE}/extensions/workflows/standard/openapi/schemas"

# official/published references
OGC_API_PROC_PART1 = "https://schemas.opengis.net/ogcapi/processes/part1/1.0"
OGC_API_PROC_PART1_SCHEMAS = f"{OGC_API_PROC_PART1}/openapi/schemas"
OGC_API_PROC_PART1_RESPONSES = f"{OGC_API_PROC_PART1}/openapi/responses"
OGC_API_PROC_PART1_PARAMETERS = f"{OGC_API_PROC_PART1}/openapi/parameters"
OGC_API_PROC_PART1_EXAMPLES = f"{OGC_API_PROC_PART1}/examples"

WEAVER_SCHEMA_VERSION = "master"
WEAVER_SCHEMA_URL = f"https://raw.githubusercontent.com/crim-ca/weaver/{WEAVER_SCHEMA_VERSION}/weaver/schemas"

DATETIME_INTERVAL_CLOSED_SYMBOL = "/"
DATETIME_INTERVAL_OPEN_START_SYMBOL = "../"
DATETIME_INTERVAL_OPEN_END_SYMBOL = "/.."

# fields ordering for generation of ProcessDescription body (shared for OGC/OLD schema format)
PROCESS_DESCRIPTION_FIELD_FIRST = [
    "id",
    "title",
    "version",
    "mutable",
    "abstract",  # backward compat for deployment
    "description",
    "keywords",
    "metadata",
    "inputs",
    "outputs"
]
PROCESS_DESCRIPTION_FIELD_AFTER = [
    "processDescriptionURL",
    "processEndpointWPS1",
    "executeEndpoint",
    "deploymentProfile",
    "links"
]
# fields ordering for nested process definition of OLD schema format of ProcessDescription
PROCESS_DESCRIPTION_FIELD_FIRST_OLD_SCHEMA = ["process"]
PROCESS_DESCRIPTION_FIELD_AFTER_OLD_SCHEMA = ["links"]

PROCESS_IO_FIELD_FIRST = ["id", "title", "description", "minOccurs", "maxOccurs"]
PROCESS_IO_FIELD_AFTER = ["literalDataDomains", "formats", "crs", "bbox"]

PROCESSES_LISTING_FIELD_FIRST = ["description", "processes", "providers"]
PROCESSES_LISTING_FIELD_AFTER = ["page", "limit", "count", "total", "links"]

PROVIDER_DESCRIPTION_FIELD_FIRST = [
    "id",
    "title",
    "version",
    "mutable",
    "description",
    "url",
    "type",
    "public",
    "keywords",
    "metadata",
]
PROVIDER_DESCRIPTION_FIELD_AFTER = ["links"]

JOBS_LISTING_FIELD_FIRST = ["description", "jobs", "groups"]
JOBS_LISTING_FIELD_AFTER = ["page", "limit", "count", "total", "links"]

QUOTES_LISTING_FIELD_FIRST = ["description", "quotations"]
QUOTES_LISTING_FIELD_AFTER = ["page", "limit", "count", "total", "links"]

#########################################################
# Examples
#########################################################

# load examples by file names as keys
SCHEMA_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "examples")
EXAMPLES = {}
for name in os.listdir(SCHEMA_EXAMPLE_DIR):
    path = os.path.join(SCHEMA_EXAMPLE_DIR, name)
    ext = os.path.splitext(name)[-1]
    with open(path, "r", encoding="utf-8") as f:
        if ext in [".json", ".yaml", ".yml"]:
            EXAMPLES[name] = yaml.safe_load(f)  # both JSON/YAML
        else:
            EXAMPLES[name] = f.read()


#########################################################
# API tags
#########################################################

TAG_API = "API"
TAG_JOBS = "Jobs"
TAG_VISIBILITY = "Visibility"
TAG_BILL_QUOTE = "Billing & Quoting"
TAG_PROVIDERS = "Providers"
TAG_PROCESSES = "Processes"
TAG_GETCAPABILITIES = "GetCapabilities"
TAG_DESCRIBEPROCESS = "DescribeProcess"
TAG_EXECUTE = "Execute"
TAG_DISMISS = "Dismiss"
TAG_STATUS = "Status"
TAG_DEPLOY = "Deploy"
TAG_RESULTS = "Results"
TAG_EXCEPTIONS = "Exceptions"
TAG_LOGS = "Logs"
TAG_STATISTICS = "Statistics"
TAG_VAULT = "Vault"
TAG_WPS = "WPS"
TAG_DEPRECATED = "Deprecated Endpoints"

###############################################################################
# API endpoints
# These "services" are wrappers that allow Cornice to generate the JSON API
###############################################################################

api_frontpage_service = Service(name="api_frontpage", path="/")
api_openapi_ui_service = Service(name="api_openapi_ui", path="/api")  # idem to swagger
api_swagger_ui_service = Service(name="api_swagger_ui", path="/swagger")
api_redoc_ui_service = Service(name="api_redoc_ui", path="/redoc")
api_versions_service = Service(name="api_versions", path="/versions")
api_conformance_service = Service(name="api_conformance", path="/conformance")
openapi_json_service = Service(name="openapi_json", path="/json")

quotes_service = Service(name="quotes", path="/quotations")
quote_service = Service(name="quote", path=f"{quotes_service.path}/{{quote_id}}")
bills_service = Service(name="bills", path="/bills")
bill_service = Service(name="bill", path=f"{bills_service.path}/{{bill_id}}")

jobs_service = Service(name="jobs", path="/jobs")
job_service = Service(name="job", path=f"{jobs_service.path}/{{job_id}}")
job_results_service = Service(name="job_results", path=f"{job_service.path}/results")
job_exceptions_service = Service(name="job_exceptions", path=f"{job_service.path}/exceptions")
job_outputs_service = Service(name="job_outputs", path=f"{job_service.path}/outputs")
job_inputs_service = Service(name="job_inputs", path=f"{job_service.path}/inputs")
job_logs_service = Service(name="job_logs", path=f"{job_service.path}/logs")
job_stats_service = Service(name="job_stats", path=f"{job_service.path}/statistics")

processes_service = Service(name="processes", path="/processes")
process_service = Service(name="process", path=f"{processes_service.path}/{{process_id}}")
process_quotes_service = Service(name="process_quotes", path=process_service.path + quotes_service.path)
process_quote_service = Service(name="process_quote", path=process_service.path + quote_service.path)
process_estimator_service = Service(name="process_estimator_service", path=f"{process_service.path}/estimator")
process_visibility_service = Service(name="process_visibility", path=f"{process_service.path}/visibility")
process_package_service = Service(name="process_package", path=f"{process_service.path}/package")
process_payload_service = Service(name="process_payload", path=f"{process_service.path}/payload")
process_jobs_service = Service(name="process_jobs", path=process_service.path + jobs_service.path)
process_job_service = Service(name="process_job", path=process_service.path + job_service.path)
process_results_service = Service(name="process_results", path=process_service.path + job_results_service.path)
process_inputs_service = Service(name="process_inputs", path=process_service.path + job_inputs_service.path)
process_outputs_service = Service(name="process_outputs", path=process_service.path + job_outputs_service.path)
process_exceptions_service = Service(name="process_exceptions", path=process_service.path + job_exceptions_service.path)
process_logs_service = Service(name="process_logs", path=process_service.path + job_logs_service.path)
process_stats_service = Service(name="process_stats", path=process_service.path + job_stats_service.path)
process_execution_service = Service(name="process_execution", path=f"{process_service.path}/execution")

providers_service = Service(name="providers", path="/providers")
provider_service = Service(name="provider", path=f"{providers_service.path}/{{provider_id}}")
provider_processes_service = Service(name="provider_processes", path=provider_service.path + processes_service.path)
provider_process_service = Service(name="provider_process", path=provider_service.path + process_service.path)
provider_jobs_service = Service(name="provider_jobs", path=provider_service.path + process_jobs_service.path)
provider_job_service = Service(name="provider_job", path=provider_service.path + process_job_service.path)
provider_results_service = Service(name="provider_results", path=provider_service.path + process_results_service.path)
provider_inputs_service = Service(name="provider_inputs", path=provider_service.path + process_inputs_service.path)
provider_outputs_service = Service(name="provider_outputs", path=provider_service.path + process_outputs_service.path)
provider_logs_service = Service(name="provider_logs", path=provider_service.path + process_logs_service.path)
provider_stats_service = Service(name="provider_stats", path=provider_service.path + process_stats_service.path)
provider_exceptions_service = Service(name="provider_exceptions",
                                      path=provider_service.path + process_exceptions_service.path)
provider_execution_service = Service(name="provider_execution", path=f"{provider_process_service.path}/execution")

# backward compatibility deprecated routes
job_result_service = Service(name="job_result", path=f"{job_service.path}/result")
process_result_service = Service(name="process_result", path=process_service.path + job_result_service.path)
provider_result_service = Service(name="provider_result", path=provider_service.path + process_result_service.path)

vault_service = Service(name="vault", path="/vault")
vault_file_service = Service(name="vault_file", path=f"{vault_service.path}/{{file_id}}")

#########################################################
# Generic schemas
#########################################################


class SLUG(ExtendedSchemaNode):
    schema_type = String
    description = "Slug name pattern."
    example = "some-object-slug-name"
    pattern = re.compile(r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")


class Tag(ExtendedSchemaNode):
    schema_type = String
    description = "Identifier with optional tagged version forming a unique reference."
    # ranges used to remove starting/ending ^$ characters
    pattern = re.compile(
        rf"{SLUG.pattern.pattern[:-1]}"
        rf"(:{SemanticVersion(v_prefix=False, rc_suffix=False).pattern[1:-1]})?$"
    )


class URL(ExtendedSchemaNode):
    schema_type = String
    description = "URL reference."
    format = "url"


class MediaType(ExtendedSchemaNode):
    schema_type = String
    description = "IANA identifier of content and format."
    example = ContentType.APP_JSON
    pattern = re.compile(r"^\w+\/[-.\w]+(?:\+[-.\w]+)?(?:\;\s*.+)*$")


class QueryBoolean(Boolean):
    description = "Boolean query parameter that allows handles common truthy/falsy values."

    def __init__(self, *_, **__):
        # type: (*Any, **Any) -> None
        super(QueryBoolean, self).__init__(
            allow_string=True,
            false_choices=("False", "false", "0", "off", "no", "null", "Null", "none", "None", ""),
            true_choices=("True", "true", "1", "on", "yes")
        )


class DateTimeInterval(ExtendedSchemaNode):
    _schema = f"{OGC_API_PROC_PART1_PARAMETERS}/datetime.yaml"
    schema_type = String
    description = (
        "DateTime format against OGC API - Processes, "
        "to get values before a certain date-time use '../' before the date-time, "
        "to get values after a certain date-time use '/..' after the date-time like the example, "
        "to get values between two date-times use '/' between the date-times, "
        "to get values with a specific date-time just pass the datetime. "
    )
    example = "2022-03-02T03:32:38.487000+00:00/.."
    regex_datetime = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(([+-]\d\d:\d\d)|Z)?)")
    regex_interval_closed = re.compile(rf"{regex_datetime.pattern}\/{regex_datetime.pattern}")
    regex_interval_open_start = re.compile(rf"\.\.\/{regex_datetime.pattern}")
    regex_interval_open_end = re.compile(rf"{regex_datetime.pattern}\/\.\.")
    pattern = re.compile(
        rf"^{regex_datetime.pattern}"
        rf"|{regex_interval_closed.pattern}"
        rf"|{regex_interval_open_start.pattern}"
        rf"|{regex_interval_open_end.pattern}"
        r"$"
    )


class S3BucketReference(ExtendedSchemaNode):
    schema_type = String
    description = "S3 bucket shorthand URL representation: 's3://{bucket}/[{dirs}/][{file-key}]'"
    pattern = AWS_S3_BUCKET_REFERENCE_PATTERN


class FileLocal(ExtendedSchemaNode):
    schema_type = String
    description = "Local file reference."
    format = "file"
    pattern = re.compile(rf"^(file://)?{NO_DOUBLE_SLASH_PATTERN}(?:/|[/?]\S+)$")


class FileURL(ExtendedSchemaNode):
    schema_type = String
    description = "URL file reference."
    format = "url"
    validator = SchemeURL(schemes=["http", "https"])


class VaultReference(ExtendedSchemaNode):
    schema_type = String
    description = "Vault file reference."
    example = "vault://399dc5ac-ff66-48d9-9c02-b144a975abe4"
    pattern = re.compile(r"^vault://[a-f0-9]{8}(?:-?[a-f0-9]{4}){3}-?[a-f0-9]{12}$")


class ProcessURL(ExtendedSchemaNode):
    schema_type = String
    description = "Process URL reference."
    format = "url"
    validator = SchemeURL(schemes=["http", "https"], path_pattern=r"(?:/processes/\S+/?)")


class ReferenceURL(AnyOfKeywordSchema):
    _any_of = [
        FileURL(),
        FileLocal(),
        S3BucketReference(),
    ]


class ExecuteReferenceURL(AnyOfKeywordSchema):
    _any_of = [
        FileURL(),
        FileLocal(),
        S3BucketReference(),
        VaultReference(),
    ]


class UUID(ExtendedSchemaNode):
    schema_type = String
    description = "Unique identifier."
    example = "a9d14bf4-84e0-449a-bac8-16e598efe807"
    format = "uuid"
    pattern = re.compile("^[a-f0-9]{8}(?:-?[a-f0-9]{4}){3}-?[a-f0-9]{12}$")
    title = "UUID"


class AnyIdentifier(SLUG):
    pass


class ProcessIdentifier(AnyOfKeywordSchema):
    description = "Process identifier."
    _any_of = [
        # UUID first because more strict than SLUG, and SLUG can be similar to UUID, but in the end any is valid
        UUID(description="Unique identifier."),
        SLUG(description="Generic identifier. This is a user-friendly slug-name. "
                         "Note that this will represent the latest process matching this name. "
                         "For specific process version, use the UUID instead.", title="ID"),
    ]


class ProcessIdentifierTag(AnyOfKeywordSchema):
    description = "Process identifier with optional revision tag."
    _schema = f"{OGC_API_PROC_PART1_PARAMETERS}/processIdPathParam.yaml"
    _any_of = [Tag] + ProcessIdentifier._any_of  # type: ignore  # noqa: W0212


class JobID(UUID):
    _schema = f"{OGC_API_PROC_PART1_PARAMETERS}/jobId.yaml"
    description = "ID of the job."
    example = "a9d14bf4-84e0-449a-bac8-16e598efe807"


class Version(ExtendedSchemaNode):
    schema_type = String
    description = "Version string."
    example = "1.2.3"
    validator = SemanticVersion()


class ContentTypeHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Content-Type"
    schema_type = String


class ContentLengthHeader(ExtendedSchemaNode):
    name = "Content-Length"
    schema_type = String
    example = "125"


class ContentDispositionHeader(ExtendedSchemaNode):
    name = "Content-Disposition"
    schema_type = String
    example = "attachment; filename=test.json"


class DateHeader(ExtendedSchemaNode):
    description = "Creation date and time of the contents."
    name = "Date"
    schema_type = String
    example = "Thu, 13 Jan 2022 12:37:19 GMT"


class LastModifiedHeader(ExtendedSchemaNode):
    description = "Modification date and time of the contents."
    name = "Last-Modified"
    schema_type = String
    example = "Thu, 13 Jan 2022 12:37:19 GMT"


class AcceptHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept"
    schema_type = String
    # FIXME: raise HTTPNotAcceptable in not one of those?
    validator = OneOf([
        ContentType.APP_JSON,
        ContentType.APP_XML,
        ContentType.TEXT_XML,
        ContentType.TEXT_HTML,
        ContentType.TEXT_PLAIN,
        ContentType.ANY,
    ])
    missing = drop
    default = ContentType.APP_JSON  # defaults to JSON for easy use within browsers


class AcceptLanguageHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept-Language"
    schema_type = String
    missing = drop
    default = AcceptLanguage.EN_CA
    # FIXME: oneOf validator for supported languages (?)


class JsonHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_JSON, default=ContentType.APP_JSON)


class HtmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.TEXT_HTML, default=ContentType.TEXT_HTML)


class XmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_XML, default=ContentType.APP_XML)


class XAuthDockerHeader(ExtendedSchemaNode):
    summary = "Authentication header for private Docker registry access."
    description = (
        "Authentication header for private registry access in order to retrieve the Docker image reference "
        "specified in an Application Package during Process deployment. When provided, this header should "
        "contain similar details as typical Authentication or X-Auth-Token headers "
        f"(see {DOC_URL}/package.html#dockerized-applications for more details)."
    )
    name = "X-Auth-Docker"
    example = "Basic {base64-auth-credentials}"
    schema_type = String
    missing = drop


class RequestContentTypeHeader(ContentTypeHeader):
    example = ContentType.APP_JSON
    default = ContentType.APP_JSON
    validator = OneOf([
        ContentType.APP_JSON,
        # ContentType.APP_XML,
    ])


class ResponseContentTypeHeader(ContentTypeHeader):
    example = ContentType.APP_JSON
    default = ContentType.APP_JSON
    validator = OneOf([
        ContentType.APP_JSON,
        ContentType.APP_XML,
        ContentType.TEXT_XML,
        ContentType.TEXT_HTML,
    ])


class RequestHeaders(ExtendedMappingSchema):
    """
    Headers that can indicate how to adjust the behavior and/or result to be provided in the response.
    """
    accept = AcceptHeader()
    accept_language = AcceptLanguageHeader()
    content_type = RequestContentTypeHeader()


class ResponseHeaders(ResponseContentTypeHeader):
    """
    Headers describing resulting response.
    """
    content_type = ResponseContentTypeHeader()


class RedirectHeaders(ResponseHeaders):
    Location = URL(example="https://job/123/result", description="Redirect resource location.")


class AcceptFormatHeaders(ExtendedMappingSchema):
    accept = AcceptHeader(description="Output format selector. Equivalent to 'f' or 'format' queries.")
    accept_language = AcceptLanguageHeader(description="Output content language if supported.")


class OutputFormatQuery(ExtendedSchemaNode):
    schema_type = String
    description = "Output format selector for requested contents."
    example = OutputFormat.JSON
    validator = OneOf(OutputFormat.values())


class FormatQueryValue(OneOfKeywordSchema):
    _one_of = [
        MediaType(),
        OutputFormatQuery()
    ]


class FormatQuery(ExtendedMappingSchema):
    f = FormatQueryValue(
        missing=drop,
        description="Output format selector. Equivalent to 'format' query or 'Accept' header."
    )
    format = FormatQueryValue(
        missing=drop,
        description="Output format selector. Equivalent to 'f' query or 'Accept' header."
    )


class NoContent(ExtendedMappingSchema):
    description = "Empty response body."
    default = {}


class FileUploadHeaders(RequestHeaders):
    # MUST be multipart for upload
    content_type = ContentTypeHeader(
        example=f"{ContentType.MULTI_PART_FORM}; boundary=43003e2f205a180ace9cd34d98f911ff",
        default=ContentType.MULTI_PART_FORM,
        description="Desired Content-Type of the file being uploaded.", missing=required)
    content_length = ContentLengthHeader(description="Uploaded file contents size in bytes.")
    content_disposition = ContentDispositionHeader(example="form-data; name=\"file\"; filename=\"desired-name.ext\"",
                                                   description="Expected ")


class FileUploadContent(ExtendedSchemaNode):
    schema_type = String()
    description = (
        "Contents of the file being uploaded with multipart. When prefixed with 'Content-Type: {media-type}', the "
        "specified format will be applied to the input that will be attributed the 'vault://{UUID}' during execution. "
        "Contents can also have 'Content-Disposition' definition to provide the desired file name."
    )


class FileResponseHeaders(NoContent):
    content_type = ContentTypeHeader(example=ContentType.APP_JSON)
    content_length = ContentLengthHeader()
    content_disposition = ContentDispositionHeader()
    date = DateHeader()
    last_modified = LastModifiedHeader()


class AccessToken(ExtendedSchemaNode):
    schema_type = String


class DescriptionSchema(ExtendedMappingSchema):
    description = ExtendedSchemaNode(String(), description="Description of the obtained contents.")


class KeywordList(ExtendedSequenceSchema):
    keyword = ExtendedSchemaNode(String(), validator=Length(min=1))


class Language(ExtendedSchemaNode):
    schema_type = String
    example = AcceptLanguage.EN_CA
    validator = OneOf(AcceptLanguage.values())


class ValueLanguage(ExtendedMappingSchema):
    lang = Language(missing=drop, description="Language of the value content.")


class LinkLanguage(ExtendedMappingSchema):
    hreflang = Language(missing=drop, description="Language of the content located at the link.")


class LinkHeader(ExtendedSchemaNode):
    schema_type = String
    example = "<http://example.com>; rel=\"relation\"; type=text/plain"


class MetadataBase(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop)


class MetadataRole(ExtendedMappingSchema):
    role = URL(missing=drop)


class LinkRelationshipType(OneOfKeywordSchema):
    description = (
        "Link relation as registered or extension type "
        "(see https://www.rfc-editor.org/rfc/rfc8288.html#section-2.1)."
    )
    _one_of = [
        SLUG(description=(
            "Relationship of the link to the current content. "
            "This should be one item amongst registered relations https://www.iana.org/assignments/link-relations/."
        )),
        URL(description="Fully qualified extension link relation to the current content.")
    ]


class LinkRelationship(ExtendedMappingSchema):
    rel = LinkRelationshipType()


class LinkBase(LinkLanguage, MetadataBase):
    href = URL(description="Hyperlink reference.")
    type = MediaType(description="IANA identifier of content-type located at the link.", missing=drop)


class Link(LinkRelationship, LinkBase):
    pass


class MetadataValue(NotKeywordSchema, ValueLanguage, MetadataBase):
    _not = [
        # make sure value metadata does not allow 'rel' and 'hreflang' reserved for link reference
        # explicitly refuse them such that when a href/rel link is provided, only link details are possible
        LinkRelationship(description="Field 'rel' must refer to a link reference with 'href'."),
        LinkLanguage(description="Field 'hreflang' must refer to a link reference with 'href'."),
    ]
    value = ExtendedSchemaNode(String(), description="Plain text value of the information.")


class MetadataLink(Link):
    pass


class MetadataContent(OneOfKeywordSchema):
    _one_of = [
        MetadataLink(),
        MetadataValue(),
    ]


class Metadata(MetadataContent, MetadataRole):
    pass


class MetadataList(ExtendedSequenceSchema):
    metadata = Metadata()


class LinkList(ExtendedSequenceSchema):
    description = "List of links relative to the applicable object."
    title = "Links"
    link = Link()


class LandingPage(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/landingPage.yaml"
    links = LinkList()


# sub-schema within:
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/format.yaml
class FormatSchema(OneOfKeywordSchema):
    _one_of = [
        # pointer to a file or JSON schema relative item (as in OpenAPI definitions)
        ReferenceURL(description="Reference where the schema definition can be retrieved to describe referenced data."),
        # literal JSON schema, permissive since it can be anything
        PermissiveMappingSchema(description="Explicit schema definition of the formatted reference data.")
    ]

    # because some pre-existing processes + pywps default schema is ""
    # deserialization against the validator pattern of 'ReferenceURL' makes it always fail
    # this causes the whole 'Format' container (and others similar) fail and be dropped
    # to resolve this issue, preemptively detect the empty string and signal the parent OneOf to remove it
    def deserialize(self, cstruct):  # type: ignore
        if isinstance(cstruct, str) and cstruct == "":
            return drop  # field that refers to this schema will drop the field key entirely
        return super(FormatSchema, self).deserialize(cstruct)


class FormatMimeType(ExtendedMappingSchema):
    """
    Used to respect ``mimeType`` field to work with pre-existing processes.
    """
    mimeType = MediaType(default=ContentType.TEXT_PLAIN, example=ContentType.APP_JSON)
    encoding = ExtendedSchemaNode(String(), missing=drop)
    schema = FormatSchema(missing=drop)


class Format(ExtendedMappingSchema):
    """
    Used to respect ``mediaType`` field as suggested per `OGC-API`.
    """
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/format.yaml"
    mediaType = MediaType(default=ContentType.TEXT_PLAIN, example=ContentType.APP_JSON)
    encoding = ExtendedSchemaNode(String(), missing=drop)
    schema = FormatSchema(missing=drop)


class FormatDefaultMimeType(FormatMimeType):
    description = (
        "Format for process input are assumed plain/text if the media-type was omitted and is not one of the known "
        "formats by this instance. When executing a job, the best match against supported formats by the process "
        "definition will be used to run the process, and will fall back to the default as last resort."
    )
    # NOTE:
    # The default is overridden from FormatMimeType since the FormatSelection 'oneOf' always fails,
    # due to the 'default' value which is always generated, and it causes the presence of both Format and FormatMimeType
    mimeType = MediaType(example=ContentType.APP_JSON)


class FormatDefaultMediaType(Format):
    description = (
        "Format for process input are assumed plain/text if the media-type was omitted and is not one of the known "
        "formats by this instance. When executing a job, the best match against supported formats by the process "
        "definition will be used to run the process, and will fall back to the default as last resort."
    )
    # NOTE:
    # The default is overridden from Format since the FormatSelection 'oneOf' always fails,
    # due to the 'default' value which is always generated, and it causes the presence of both Format and FormatMimeType
    mediaType = MediaType(example=ContentType.APP_JSON)


class FormatSelection(OneOfKeywordSchema):
    """
    Validation against ``mimeType`` or ``mediaType`` format.

    .. seealso::
        - :class:`FormatDefaultMediaType`
        - :class:`FormatDefaultMimeType`

    .. note::
        Format are validated to be retro-compatible with pre-existing/deployed/remote processes.
    """
    _one_of = [
        FormatDefaultMediaType(),
        FormatDefaultMimeType()
    ]


# only extra portion from:
# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1538-L1547
class FormatDescription(ExtendedMappingSchema):
    maximumMegabytes = ExtendedSchemaNode(Integer(), missing=drop, validator=Range(min=1))


# although original schema defines 'default' in above 'FormatDescription', separate it in order to omit it
# from 'ResultFormat' employed for result reporting, which shouldn't have a default (applied vs supported format)
class FormatDefault(ExtendedMappingSchema):
    default = ExtendedSchemaNode(
        Boolean(), missing=drop,
        # don't insert "default" field if omitted in deploy body to avoid causing differing "inputs"/"outputs"
        # definitions between the submitted payload and the validated one (in 'weaver.processes.utils._check_deploy')
        # default=False,
        description=(
            "Indicates if this format should be considered as the default one in case none of the other "
            "allowed or supported formats was matched nor provided as input during job submission."
        )
    )


class DescriptionFormat(Format, FormatDescription, FormatDefault):
    pass


class DeploymentFormat(FormatSelection, FormatDescription, FormatDefault):
    # NOTE:
    #   The 'OGC-API' suggest to use 'mediaType' field for format representation, but retro-compatibility is
    #   supported during deployment only, where either old 'mimeType' or new 'mediaType', but only 'mediaType'
    #   is used for process description and result reporting. This support is added for deployment so that
    #   pre-existing deploy definitions remain valid without need to update them.
    pass


class ResultFormat(FormatDescription):
    """
    Format employed for reference results respecting 'OGC API - Processes' schemas.
    """
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/format.yaml"
    mediaType = MediaType(String())
    encoding = ExtendedSchemaNode(String(), missing=drop)
    schema = FormatSchema(missing=drop)


class DescriptionFormatList(ExtendedSequenceSchema):
    format_item = DescriptionFormat()


class DeploymentFormatList(ExtendedSequenceSchema):
    format_item = DeploymentFormat()


class AdditionalParameterUnique(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), title="InputParameterLiteral.String"),
        ExtendedSchemaNode(Boolean(), title="InputParameterLiteral.Boolean"),
        ExtendedSchemaNode(Integer(), title="InputParameterLiteral.Integer"),
        ExtendedSchemaNode(Float(), title="InputParameterLiteral.Float"),
        # PermissiveMappingSchema(title="InputParameterLiteral.object"),
    ]


class AdditionalParameterListing(ExtendedSequenceSchema):
    param = AdditionalParameterUnique()


class AdditionalParameterValues(OneOfKeywordSchema):
    _one_of = [
        AdditionalParameterUnique(),
        AdditionalParameterListing()
    ]


class AdditionalParameterDefinition(ExtendedMappingSchema):
    name = SLUG(title="AdditionalParameterName", example="EOImage")
    values = AdditionalParameterValues(example=["true"])


class AdditionalParameterList(ExtendedSequenceSchema):
    param = AdditionalParameterDefinition()


class AdditionalParametersMeta(OneOfKeywordSchema):
    _one_of = [
        LinkBase(title="AdditionalParameterLink"),
        MetadataRole(title="AdditionalParameterRole")
    ]


class AdditionalParameters(ExtendedMappingSchema):
    parameters = AdditionalParameterList()


class AdditionalParametersItem(AnyOfKeywordSchema):
    _any_of = [
        AdditionalParametersMeta(),
        AdditionalParameters()
    ]


class AdditionalParametersList(ExtendedSequenceSchema):
    additionalParameter = AdditionalParametersItem()


class Content(ExtendedMappingSchema):
    href = ReferenceURL(description="URL to CWL file.", title="OWSContentURL",
                        default=drop,       # if invalid, drop it completely,
                        missing=required,   # but still mark as 'required' for parent objects
                        example="http://some.host/applications/cwl/multisensor_ndvi.cwl")


class Offering(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String(), missing=drop, description="Descriptor of represented information in 'content'.")
    content = Content()


class OWSContext(ExtendedMappingSchema):
    description = "OGC Web Service definition from an URL reference."
    title = "owsContext"
    offering = Offering()


class DescriptionBase(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop, description="Short human-readable name of the object.")
    description = ExtendedSchemaNode(String(), missing=drop, description="Detailed explanation of the object.")


class DescriptionLinks(ExtendedMappingSchema):
    links = LinkList(missing=drop, description="References to endpoints with information related to object.")


class ProcessContext(ExtendedMappingSchema):
    owsContext = OWSContext(missing=drop)


class DescriptionExtra(ExtendedMappingSchema):
    additionalParameters = AdditionalParametersList(missing=drop)


class DescriptionType(DescriptionBase, DescriptionLinks, DescriptionExtra):
    pass


class DeploymentType(DescriptionType):
    deprecated = True
    abstract = ExtendedSchemaNode(
        String(), missing=drop, deprecated=True,
        description="Description of the object. Will be replaced by 'description' field if not already provided. "
                    "Preserved for backward compatibility of pre-existing process deployment. "
                    "Consider using 'description' directly instead."
    )


class DescriptionMeta(ExtendedMappingSchema):
    # employ empty lists by default if nothing is provided for process description
    keywords = KeywordList(
        default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        default=[],
        description="External references to documentation or metadata sources relevant to the process.")


class ProcessDeployMeta(ExtendedMappingSchema):
    # don't require fields at all for process deployment, default to empty if omitted
    keywords = KeywordList(
        missing=drop, default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        missing=drop, default=[],
        description="External references to documentation or metadata sources relevant to the process.")


class InputOutputDescriptionMeta(ExtendedMappingSchema):
    # remove unnecessary empty lists by default if nothing is provided for inputs/outputs
    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        super(InputOutputDescriptionMeta, self).__init__(*args, **kwargs)
        for child in self.children:
            if child.name in ["keywords", "metadata"]:
                child.missing = drop


class ReferenceOAS(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/reference.yaml"
    _ref = ReferenceURL(name="$ref", description="External OpenAPI schema reference.")


class TypeOAS(ExtendedSchemaNode):
    name = "type"
    schema_type = String
    validator = OneOf(OAS_DATA_TYPES)


class EnumItemOAS(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String()),
    ]


class EnumOAS(ExtendedSequenceSchema):
    enum = EnumItemOAS()


class RequiredOAS(ExtendedSequenceSchema):
    required_field = ExtendedSchemaNode(String(), description="Name of the field that is required under the object.")


class MultipleOfOAS(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
    ]


class PermissiveDefinitionOAS(NotKeywordSchema, PermissiveMappingSchema):
    _not = [
        ReferenceOAS
    ]


# cannot make recursive declarative schemas
# simulate it and assume it is sufficient for validation purposes
class PseudoObjectOAS(OneOfKeywordSchema):
    _one_of = [
        ReferenceOAS(),
        PermissiveDefinitionOAS(),
    ]


class KeywordObjectOAS(ExtendedSequenceSchema):
    item = PseudoObjectOAS()


class AdditionalPropertiesOAS(OneOfKeywordSchema):
    _one_of = [
        ReferenceOAS(),
        PermissiveDefinitionOAS(),
        ExtendedSchemaNode(Boolean())
    ]


class AnyValueOAS(AnyOfKeywordSchema):
    _any_of = [
        PermissiveMappingSchema(),
        PermissiveSequenceSchema(),
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(Boolean()),
        ExtendedSchemaNode(String()),
    ]


# reference:
#   https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/schema.yaml
# note:
#   although reference definition provides multiple 'default: 0|false' entries, we omit them since the behaviour
#   of colander with extended schema nodes is to set this value by default in deserialize result if they were missing,
#   but reference 'default' correspond more to the default *interpretation* value if none was provided.
#   It is preferable in our case to omit (i.e.: drop) these defaults to keep obtained/resolved definitions succinct,
#   since those defaults can be defined (by default...) if needed. No reason to add them explicitly.
# WARNING:
#   cannot use any KeywordMapper derived instance here, otherwise conflicts with same OpenAPI keywords as children nodes
class PropertyOAS(PermissiveMappingSchema):
    _type = TypeOAS(name="type", missing=drop)  # not present if top-most schema is {allOf,anyOf,oneOf,not}
    _format = ExtendedSchemaNode(String(), name="format", missing=drop)
    default = AnyValueOAS(unknown="preserve", missing=drop)
    example = AnyValueOAS(unknown="preserve", missing=drop)
    title = ExtendedSchemaNode(String(), missing=drop)
    description = ExtendedSchemaNode(String(), missing=drop)
    enum = EnumOAS(missing=drop)
    items = PseudoObjectOAS(name="items", missing=drop)
    required = RequiredOAS(missing=drop)
    nullable = ExtendedSchemaNode(Boolean(), missing=drop)
    deprecated = ExtendedSchemaNode(Boolean(), missing=drop)
    read_only = ExtendedSchemaNode(Boolean(), name="readOnly", missing=drop)
    write_only = ExtendedSchemaNode(Boolean(), name="writeOnly", missing=drop)
    multiple_of = MultipleOfOAS(name="multipleOf", missing=drop, validator=BoundedRange(min=0, exclusive_min=True))
    minimum = ExtendedSchemaNode(Integer(), name="minimum", missing=drop, validator=Range(min=0))  # default=0
    maximum = ExtendedSchemaNode(Integer(), name="maximum", missing=drop, validator=Range(min=0))
    exclusive_min = ExtendedSchemaNode(Boolean(), name="exclusiveMinimum", missing=drop)  # default=False
    exclusive_max = ExtendedSchemaNode(Boolean(), name="exclusiveMaximum", missing=drop)  # default=False
    min_length = ExtendedSchemaNode(Integer(), name="minLength", missing=drop, validator=Range(min=0))  # default=0
    max_length = ExtendedSchemaNode(Integer(), name="maxLength", missing=drop, validator=Range(min=0))
    pattern = ExtendedSchemaNode(Integer(), missing=drop)
    min_items = ExtendedSchemaNode(Integer(), name="minItems", missing=drop, validator=Range(min=0))  # default=0
    max_items = ExtendedSchemaNode(Integer(), name="maxItems", missing=drop, validator=Range(min=0))
    unique_items = ExtendedSchemaNode(Boolean(), name="uniqueItems", missing=drop)  # default=False
    min_prop = ExtendedSchemaNode(Integer(), name="minProperties", missing=drop, validator=Range(min=0))  # default=0
    max_prop = ExtendedSchemaNode(Integer(), name="maxProperties", missing=drop, validator=Range(min=0))
    content_type = ExtendedSchemaNode(String(), name="contentMediaType", missing=drop)
    content_encode = ExtendedSchemaNode(String(), name="contentEncoding", missing=drop)
    content_schema = ExtendedSchemaNode(String(), name="contentSchema", missing=drop)
    _not_key = PseudoObjectOAS(name="not", title="not", missing=drop)
    _all_of = KeywordObjectOAS(name="allOf", missing=drop)
    _any_of = KeywordObjectOAS(name="anyOf", missing=drop)
    _one_of = KeywordObjectOAS(name="oneOf", missing=drop)
    x_props = AdditionalPropertiesOAS(name="additionalProperties", missing=drop)
    properties = PermissiveMappingSchema(missing=drop)  # cannot do real recursive definitions, simply check mapping


# this class is only to avoid conflicting names with keyword mappers
class AnyPropertyOAS(OneOfKeywordSchema):
    _one_of = [
        ReferenceOAS(),
        PropertyOAS(),
    ]


class ObjectPropertiesOAS(ExtendedMappingSchema):
    property_name = AnyPropertyOAS(
        variable="{property-name}",
        description="Named of the property being defined under the OpenAPI object.",
    )


# would not need this if we could do explicit recursive definitions but at the very least, validate that when an
# object type is specified, its properties are as well and are slightly more specific than permissive mapping
class ObjectOAS(NotKeywordSchema, ExtendedMappingSchema):
    _not = [ReferenceOAS]
    _type = TypeOAS(name="type", missing=drop, validator=OneOf(OAS_COMPLEX_TYPES))
    properties = ObjectPropertiesOAS()  # required and more specific contrary to 'properties' in 'PropertyOAS'


# since we redefine 'properties', do not cause validation error for 'oneOf'
class DefinitionOAS(AnyOfKeywordSchema):
    _any_of = [
        ObjectOAS(),
        PropertyOAS(),  # for top-level keyword schemas {allOf,anyOf,oneOf,not}
    ]


class OAS(OneOfKeywordSchema):
    description = "OpenAPI schema definition."
    # _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/schema.yaml"  # definition used by OAP, but JSON-schema is more accurate
    _schema = "http://json-schema.org/draft-07/schema#"
    _one_of = [
        ReferenceOAS(),
        DefinitionOAS(),
    ]


class InputOutputDescriptionSchema(ExtendedMappingSchema):
    # Validation is accomplished only for the first few levels of the OpenAPI definition.
    # This is sufficient to know if the I/O type is literal/bbox/complex. If 'schema' is explicitly provided, it
    # should minimally succeed those top-level validation for proper I/O interpretation. Pseudo-recursive schema
    # are defined for any more deeply nested definition to keep everything intact (eg: explicit object structure).
    schema = OAS(missing=drop)


class MinOccursDefinition(OneOfKeywordSchema):
    description = "Minimum amount of values required for this input."
    title = "MinOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0), title="MinOccurs.integer",
                           ddescription="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$", title="MinOccurs.string",
                           description="Numerical string representing a positive integer."),
    ]


class MaxOccursDefinition(OneOfKeywordSchema):
    description = "Maximum amount of values allowed for this input."
    title = "MaxOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0), title="MaxOccurs.integer",
                           description="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$", title="MaxOccurs.string",
                           description="Numerical string representing a positive integer."),
        ExtendedSchemaNode(String(), validator=OneOf(["unbounded"]), title="MaxOccurs.unbounded",
                           description="Special value indicating no limit to occurrences."),
    ]


class DescribeMinMaxOccurs(ExtendedMappingSchema):
    minOccurs = MinOccursDefinition()
    maxOccurs = MaxOccursDefinition()


class DeployMinMaxOccurs(ExtendedMappingSchema):
    # entirely omitted definitions are permitted to allow inference from fields in package (CWL) or using defaults
    # if explicitly provided though, schema format and values should be validated
    # - do not use 'missing=drop' to ensure we raise provided invalid value instead of ignoring it
    # - do not use any specific value (e.g.: 1) for 'default' such that we do not inject an erroneous value when it
    #   was originally omitted, since it could be resolved differently depending on matching CWL inputs definitions
    minOccurs = MinOccursDefinition(default=null, missing=null)
    maxOccurs = MaxOccursDefinition(default=null, missing=null)


# does not inherit from 'DescriptionLinks' because other 'ProcessDescription<>' schema depend on this without 'links'
class ProcessDescriptionType(DescriptionBase, DescriptionExtra):
    id = ProcessIdentifierTag()
    version = Version(missing=None, default=None, example="1.2.3")
    mutable = ExtendedSchemaNode(Boolean(), default=True, description=(
        "Indicates if the process is mutable (dynamically deployed), or immutable (builtin with this instance)."
    ))


class InputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="input"))


class OutputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="output"))


class DescribeWithFormats(ExtendedMappingSchema):
    formats = DescriptionFormatList()


class DeployWithFormats(ExtendedMappingSchema):
    formats = DeploymentFormatList()


class DescribeComplexInputType(DescribeWithFormats):
    pass


class DeployComplexInputType(DeployWithFormats):
    pass


class SupportedCRS(ExtendedMappingSchema):
    crs = URL(title="CRS", description="Coordinate Reference System")
    default = ExtendedSchemaNode(Boolean(), missing=drop)


class SupportedCRSList(ExtendedSequenceSchema):
    crs = SupportedCRS(title="SupportedCRS")


class BoundingBoxInputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


# FIXME: support byte/binary type (string + format:byte) ?
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/binaryInputValue.yaml
class AnyLiteralType(OneOfKeywordSchema):
    """
    Submitted values that correspond to literal data.

    .. seealso::
        - :class:`AnyLiteralDataType`
        - :class:`AnyLiteralValueType`
        - :class:`AnyLiteralDefaultType`
    """
    _one_of = [
        ExtendedSchemaNode(Float(), description="Literal data type representing a floating point number."),
        ExtendedSchemaNode(Integer(), description="Literal data type representing an integer number."),
        ExtendedSchemaNode(Boolean(), description="Literal data type representing a boolean flag."),
        ExtendedSchemaNode(String(), description="Literal data type representing a generic string."),
    ]


class Number(OneOfKeywordSchema):
    """
    Represents a literal number, integer or float.
    """
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
    ]


class NumericType(OneOfKeywordSchema):
    """
    Represents a numeric-like value.
    """
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String(), pattern="^[0-9]+$"),
    ]


class Decimal(ExtendedSchemaNode):
    schema_type = colander.Decimal
    format = "decimal"


class PositiveNumber(AnyOfKeywordSchema):
    """
    Represents a literal number, integer or float, of positive value.
    """
    _any_of = [
        Decimal(validator=Range(min=0.0)),
        ExtendedSchemaNode(Float(), validator=Range(min=0.0)),
        ExtendedSchemaNode(Integer(), validator=Range(min=0)),
    ]


class LiteralReference(ExtendedMappingSchema):
    reference = ExecuteReferenceURL()


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1707-L1716
class NameReferenceType(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/nameReferenceType.yaml"
    name = ExtendedSchemaNode(String())
    reference = ExecuteReferenceURL(missing=drop, description="Reference URL to schema definition of the named entity.")


class DataTypeSchema(NameReferenceType):
    description = "Type of the literal data representation."
    title = "DataType"
    # any named type that can be converted by: 'weaver.processes.convert.any2wps_literal_datatype'
    name = ExtendedSchemaNode(String(), validator=OneOf(list(WPS_LITERAL_DATA_TYPES)))


class UomSchema(NameReferenceType):
    title = "UnitOfMeasure"


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1423
# NOTE: Original is only 'string', but we allow any literal type
class AllowedValuesList(ExtendedSequenceSchema):
    value = AnyLiteralType()


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1772-L1787
# NOTE:
#   Contrary to original schema where all fields are 'string', we allow any literal type as well since those make more
#   sense when parsing corresponding data values (eg: float, integer, bool).
class AllowedRange(ExtendedMappingSchema):
    minimumValue = NumericType(missing=drop)
    maximumValue = NumericType(missing=drop)
    spacing = NumericType(missing=drop)
    rangeClosure = ExtendedSchemaNode(String(), missing=drop,
                                      validator=OneOf(["closed", "open", "open-closed", "closed-open"]))


class AllowedRangesList(ExtendedSequenceSchema):
    range = AllowedRange()


class AllowedValues(OneOfKeywordSchema):
    _one_of = [
        AllowedRangesList(description="List of value ranges and constraints."),  # array of {range}
        AllowedValuesList(description="List of enumerated allowed values."),     # array of "value"
        ExtendedSchemaNode(String(), description="Single allowed value."),       # single "value"
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1425-L1430
class AnyValue(ExtendedMappingSchema):
    anyValue = ExtendedSchemaNode(
        Boolean(), missing=drop, default=True,
        description="Explicitly indicate if any value is allowed. "
                    "This is the default behaviour if no other constrains are specified."
    )


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1801-L1803
class ValuesReference(ExecuteReferenceURL):
    description = "URL where to retrieve applicable values."


class ArrayLiteralType(ExtendedSequenceSchema):
    value_item = AnyLiteralType()


class ArrayLiteralDataType(ExtendedMappingSchema):
    data = ArrayLiteralType()


class ArrayLiteralValueType(ExtendedMappingSchema):
    value = ArrayLiteralType()


class AnyLiteralDataType(ExtendedMappingSchema):
    data = AnyLiteralType()


class AnyLiteralValueType(ExtendedMappingSchema):
    value = AnyLiteralType()


class AnyLiteralDefaultType(ExtendedMappingSchema):
    default = AnyLiteralType()


class LiteralDataValueDefinition(OneOfKeywordSchema):
    _one_of = [
        AllowedValues(description="Constraints of allowed values."),
        ValuesReference(description="Reference URL where to retrieve allowed values."),
        # 'AnyValue' must be last because it's the most permissive (always valid, default)
        AnyValue(description="Permissive definition for any allowed value."),
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1675-L1688
#  literalDataDomain:
#    valueDefinition: oneOf(<allowedValues, anyValue, valuesReference>)
#    defaultValue: <string>
#    dataType: <nameReferenceType>
#    uom: <nameReferenceType>
class LiteralDataDomain(ExtendedMappingSchema):
    default = ExtendedSchemaNode(Boolean(), default=True,
                                 description="Indicates if this literal data domain definition is the default one.")
    defaultValue = AnyLiteralType(missing=drop, description="Default value to employ if none was provided.")
    dataType = DataTypeSchema(missing=drop, description="Type name and reference of the literal data representation.")
    uom = UomSchema(missing=drop, description="Unit of measure applicable for the data.")
    valueDefinition = LiteralDataValueDefinition(description="Literal data domain constraints.")


class LiteralDataDomainList(ExtendedSequenceSchema):
    """
    Constraints that apply to the literal data values.
    """
    literalDataDomain = LiteralDataDomain()


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1689-L1697
class LiteralDataType(NotKeywordSchema, ExtendedMappingSchema):
    # NOTE:
    #   Apply 'missing=drop' although original schema of 'literalDataDomains' (see link above) requires it because
    #   we support omitting it for minimalistic literal input definition.
    #   This is because our schema validation allows us to do detection of 'basic' types using the literal parsing.
    #   Because there is not explicit requirement though (ie: missing would fail schema validation), we must check
    #   that 'format' is not present to avoid conflict with minimalistic literal data definition in case of ambiguity.
    literalDataDomains = LiteralDataDomainList(missing=drop)
    _not = [
        DescribeWithFormats,
    ]


class LiteralInputType(LiteralDataType):
    pass


class DescribeInputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process description definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        DescribeComplexInputType,  # should be 2nd to last because very permissive, but requires format at least
        LiteralInputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class DeployInputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process deployment definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        DeployComplexInputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralInputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class DescribeInputType(AllOfKeywordSchema):
    _all_of = [
        DescriptionType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DescribeInputTypeDefinition(),
        DescribeMinMaxOccurs(),
        DescriptionExtra(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DescribeInputTypeWithID(InputIdentifierType, DescribeInputType):
    title = "DescribeInputTypeWithID"


# Different definition than 'Describe' such that nested 'complex' type 'formats' can be validated and backward
# compatible with pre-existing/deployed/remote processes, with either ``mediaType`` and ``mimeType`` formats.
class DeployInputType(AllOfKeywordSchema):
    _all_of = [
        DeploymentType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DeployInputTypeDefinition(),
        DeployMinMaxOccurs(),
        DescriptionExtra(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DeployInputTypeWithID(InputIdentifierType, DeployInputType):
    pass


# for [{id: "", ...}] representation within ProcessDescription (OLD schema)
class DescribeInputTypeList(ExtendedSequenceSchema):
    """
    Listing of process inputs descriptions.
    """
    input = DescribeInputTypeWithID()


# for {"<id>": {...}} representation within ProcessDescription (OGC schema)
class DescribeInputTypeMap(PermissiveMappingSchema):
    """
    Description of all process inputs under mapping.
    """
    input_id = DescribeInputType(
        variable="{input-id}",
        description="Input definition under mapping of process description.",
        missing=drop,  # allowed because process can have empty inputs (see schema: ProcessDescriptionOGC)
    )


# for [{id: "", ...}] representation within ProcessDeployment (OLD schema)
class DeployInputTypeList(ExtendedSequenceSchema):
    """
    Listing of process input definitions to deploy.
    """
    input_item = DeployInputTypeWithID()


# for {"<id>": {...}} representation within ProcessDeployment (OGC schema)
class DeployInputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process inputs under mapping.
    """
    input_id = DeployInputType(
        variable="{input-id}",
        description="Input definition under mapping of process deployment."
    )


class DeployInputTypeAny(OneOfKeywordSchema):
    _one_of = [
        DeployInputTypeList(),
        DeployInputTypeMap(),
    ]


class LiteralOutputType(LiteralDataType):
    pass


class BoundingBoxOutputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


class DescribeComplexOutputType(DescribeWithFormats):
    pass


class DeployComplexOutputType(DeployWithFormats):
    pass


class DescribeOutputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        BoundingBoxOutputType,
        DescribeComplexOutputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralOutputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class DeployOutputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        BoundingBoxOutputType,
        DeployComplexOutputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralOutputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class DescribeOutputType(AllOfKeywordSchema):
    _all_of = [
        DescriptionType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DescribeOutputTypeDefinition(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DescribeOutputTypeWithID(OutputIdentifierType, DescribeOutputType):
    pass


class DescribeOutputTypeList(ExtendedSequenceSchema):
    """
    Listing of process outputs descriptions.
    """
    output = DescribeOutputTypeWithID()


# for {"<id>": {...}} representation within ProcessDescription (OGC schema)
class DescribeOutputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process outputs under mapping.
    """
    output_id = DescribeOutputType(
        variable="{output-id}", title="ProcessOutputDefinition",
        description="Output definition under mapping of process description."
    )


# Different definition than 'Describe' such that nested 'complex' type 'formats' can be validated and backward
# compatible with pre-existing/deployed/remote processes, with either ``mediaType`` and ``mimeType`` formats.
class DeployOutputType(AllOfKeywordSchema):
    _all_of = [
        DeploymentType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DeployOutputTypeDefinition(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DeployOutputTypeWithID(OutputIdentifierType, DeployOutputType):
    pass


# for [{id: "", ...}] representation within ProcessDeployment (OLD schema)
class DeployOutputTypeList(ExtendedSequenceSchema):
    """
    Listing of process output definitions to deploy.
    """
    input = DeployOutputTypeWithID()


# for {"<id>": {...}} representation within ProcessDeployment (OGC schema)
class DeployOutputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process outputs under mapping.
    """
    input_id = DeployOutputType(
        variable="{input-id}",
        description="Output definition under mapping of process deployment."
    )


class DeployOutputTypeAny(OneOfKeywordSchema):
    _one_of = [
        DeployOutputTypeList,
        DeployOutputTypeMap,
    ]


class JobExecuteModeEnum(ExtendedSchemaNode):
    # _schema: none available by itself, legacy parameter that was directly embedded in 'execute.yaml'
    # (https://github.com/opengeospatial/ogcapi-processes/blob/1.0-draft.5/core/openapi/schemas/execute.yaml)
    schema_type = String
    title = "JobExecuteMode"
    # no default to enforce required input as per OGC-API schemas
    # default = EXECUTE_MODE_AUTO
    example = ExecuteMode.ASYNC
    validator = OneOf(ExecuteMode.values())


class JobControlOptionsEnum(ExtendedSchemaNode):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/jobControlOptions.yaml"
    schema_type = String
    title = "JobControlOptions"
    default = ExecuteControlOption.ASYNC
    example = ExecuteControlOption.ASYNC
    validator = OneOf(ExecuteControlOption.values())


class JobResponseOptionsEnum(ExtendedSchemaNode):
    # _schema: none available by itself, legacy parameter that was directly embedded in 'execute.yaml'
    # (https://github.com/opengeospatial/ogcapi-processes/blob/1.0-draft.6/core/openapi/schemas/execute.yaml)
    schema_type = String
    title = "JobResponseOptions"
    # no default to enforce required input as per OGC-API schemas
    # default = ExecuteResponse.DOCUMENT
    example = ExecuteResponse.DOCUMENT
    validator = OneOf(ExecuteResponse.values())


class TransmissionModeEnum(ExtendedSchemaNode):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/transmissionMode.yaml"
    schema_type = String
    title = "TransmissionMode"
    default = ExecuteTransmissionMode.VALUE
    example = ExecuteTransmissionMode.VALUE
    validator = OneOf(ExecuteTransmissionMode.values())


class JobStatusEnum(ExtendedSchemaNode):
    _schema = f"{OGC_API_PROC_PART1_PARAMETERS}/status.yaml"  # subset of this implementation
    schema_type = String
    title = "JobStatus"
    default = Status.ACCEPTED
    example = Status.ACCEPTED
    validator = OneOf(JOB_STATUS_CODE_API)


class JobStatusSearchEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobStatusSearch"
    default = Status.ACCEPTED
    example = Status.ACCEPTED
    validator = StringOneOf(JOB_STATUS_SEARCH_API, delimiter=",", case_sensitive=False)


class JobTypeEnum(ExtendedSchemaNode):
    _schema = f"{OGC_API_PROC_PART1_PARAMETERS}/type.yaml"  # subset of this implementation
    schema_type = String
    title = "JobType"
    default = null
    example = "process"
    validator = OneOf(["process", "provider", "service"])


class JobSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobSortingMethod"
    default = Sort.CREATED
    example = Sort.CREATED
    validator = OneOf(SortMethods.JOB)


class ProcessSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "ProcessSortMethod"
    default = Sort.ID
    example = Sort.CREATED
    validator = OneOf(SortMethods.PROCESS)


class QuoteSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "QuoteSortingMethod"
    default = Sort.ID
    example = Sort.PROCESS
    validator = OneOf(SortMethods.QUOTE)


class JobTagsCommaSeparated(ExpandStringList, ExtendedSchemaNode):
    schema_type = String
    validator = CommaSeparated()
    default = None
    missing = drop
    description = (
        "Comma-separated tags that can be used to filter jobs. "
        f"Only {validator.allow_chars} characters are permitted."
    )


class JobGroupsCommaSeparated(ExpandStringList, ExtendedSchemaNode):
    schema_type = String
    default = None
    example = "process,service"
    missing = drop
    description = "Comma-separated list of grouping fields with which to list jobs."
    validator = StringOneOf(["process", "provider", "service", "status"], delimiter=",", case_sensitive=True)


class LaunchJobQuerystring(ExtendedMappingSchema):
    tags = JobTagsCommaSeparated()


class VisibilityValue(ExtendedSchemaNode):
    schema_type = String
    validator = OneOf(Visibility.values())
    example = Visibility.PUBLIC


class JobAccess(VisibilityValue):
    pass


class VisibilitySchema(ExtendedMappingSchema):
    value = VisibilityValue()


class QuoteEstimatorConfigurationSchema(ExtendedMappingSchema):
    _schema = f"{WEAVER_SCHEMA_URL}/quotation/quote-estimator.yaml#/definitions/Configuration"
    description = "Quote Estimator Configuration"

    def deserialize(self, cstruct):
        schema = ExtendedMappingSchema(_schema=self._schema)  # avoid recursion
        return validate_node_schema(schema, cstruct)


class QuoteEstimatorWeightedParameterSchema(ExtendedMappingSchema):
    # NOTE:
    #   value/size parameters omitted since they will be provided at runtime by the
    #   quote estimation job obtained from submitted body in 'QuoteProcessParametersSchema'
    weight = ExtendedSchemaNode(
        Float(),
        default=1.0,
        missing=drop,
        description="Weight attributed to this parameter when submitted for quote estimation.",
    )


class QuoteEstimatorInputParametersSchema(ExtendedMappingSchema):
    description = "Parametrization of inputs for quote estimation."
    input_id = QuoteEstimatorWeightedParameterSchema(
        variable="{input-id}",
        title="QuoteEstimatorInputParameters",
        description="Mapping of input definitions for quote estimation.",
    )


class QuoteEstimatorOutputParametersSchema(ExtendedMappingSchema):
    description = "Parametrization of outputs for quote estimation."
    output_id = QuoteEstimatorWeightedParameterSchema(
        variable="{output-id}",
        title="QuoteEstimatorOutputParameters",
        description="Mapping of output definitions for quote estimation.",
    )


class QuoteEstimatorSchema(ExtendedMappingSchema):
    _schema = f"{WEAVER_SCHEMA_URL}/quotation/quote-estimator.yaml"
    description = "Configuration of the quote estimation algorithm for a given process."
    config = QuoteEstimatorConfigurationSchema()
    inputs = QuoteEstimatorInputParametersSchema(missing=drop, default={})
    outputs = QuoteEstimatorOutputParametersSchema(missing=drop, default={})


#########################################################
# Path parameter definitions
#########################################################


class LocalProcessQuery(ExtendedMappingSchema):
    version = Version(example="1.2.3", missing=drop, description=(
        "Specific process version to locate. "
        "If process ID was requested with tagged 'id:version' revision format, this parameter is ignored."
    ))


class LocalProcessPath(ExtendedMappingSchema):
    process_id = ProcessIdentifierTag(
        example="jsonarray2netcdf[:1.0.0]",
        summary="Process identifier with optional tag version.",
        description=(
            "Process identifier with optional tag version. "
            "If tag is omitted, the latest version of that process is assumed. "
            "Otherwise, the specific process revision as 'id:version' must be matched. "
            "Alternatively, the plain process ID can be specified in combination to 'version' query parameter."
        ),
    )


class ProviderPath(ExtendedMappingSchema):
    provider_id = AnyIdentifier(description="Remote provider identifier.", example="hummingbird")


class ProviderProcessPath(ProviderPath):
    # note: Tag representation not allowed in this case
    process_id = ProcessIdentifier(example="provider-process", description=(
        "Identifier of a process that is offered by the remote provider."
    ))


class JobPath(ExtendedMappingSchema):
    job_id = UUID(description="Job ID", example="14c68477-c3ed-4784-9c0f-a4c9e1344db5")


class BillPath(ExtendedMappingSchema):
    bill_id = UUID(description="Bill ID")


class QuotePath(ExtendedMappingSchema):
    quote_id = UUID(description="Quote ID")


class ResultPath(ExtendedMappingSchema):
    result_id = UUID(description="Result ID")


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class FrontpageEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class VersionsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class ConformanceQueries(ExtendedMappingSchema):
    category = ExtendedSchemaNode(
        String(),
        missing=drop,
        default=ConformanceCategory.CONFORMANCE,
        validator=OneOf(ConformanceCategory.values()),
        description="Select the desired conformance item references to be returned."
    )


class ConformanceEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = ConformanceQueries()


# FIXME: support YAML (https://github.com/crim-ca/weaver/issues/456)
class OpenAPIAcceptHeader(AcceptHeader):
    default = ContentType.APP_OAS_JSON
    validator = OneOf([ContentType.APP_OAS_JSON, ContentType.APP_JSON])


class OpenAPIRequestHeaders(RequestHeaders):
    accept = OpenAPIAcceptHeader()


class OpenAPIEndpoint(ExtendedMappingSchema):
    header = OpenAPIRequestHeaders()


class SwaggerUIEndpoint(ExtendedMappingSchema):
    pass


class RedocUIEndpoint(ExtendedMappingSchema):
    pass


class OWSNamespace(XMLObject):
    prefix = "ows"
    namespace = "http://www.opengis.net/ows/1.1"


class WPSNamespace(XMLObject):
    prefix = "wps"
    namespace = "http://www.opengis.net/wps/1.0.0"


class XMLNamespace(XMLObject):
    prefix = "xml"


class XMLReferenceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "href"
    prefix = "xlink"
    format = "url"


class MimeTypeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "mimeType"
    prefix = drop
    example = ContentType.APP_JSON


class EncodingAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "encoding"
    prefix = drop
    example = "UTF-8"


class OWSVersion(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Version"
    default = "1.0.0"
    example = "1.0.0"


class OWSAcceptVersions(ExtendedSequenceSchema, OWSNamespace):
    description = "Accepted versions to produce the response."
    name = "AcceptVersions"
    item = OWSVersion()


class OWSLanguage(ExtendedSchemaNode, OWSNamespace):
    description = "Desired language to produce the response."
    schema_type = String
    name = "Language"
    default = AcceptLanguage.EN_US
    example = AcceptLanguage.EN_CA


class OWSLanguageAttribute(OWSLanguage):
    description = "RFC-4646 language code of the human-readable text."
    name = "language"
    attribute = True


class OWSService(ExtendedSchemaNode, OWSNamespace):
    description = "Desired service to produce the response (SHOULD be 'WPS')."
    schema_type = String
    name = "service"
    attribute = True
    default = AcceptLanguage.EN_US
    example = AcceptLanguage.EN_CA


class WPSServiceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "service"
    attribute = True
    default = "WPS"
    example = "WPS"


class WPSVersionAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "version"
    attribute = True
    default = "1.0.0"
    example = "1.0.0"


class WPSLanguageAttribute(ExtendedSchemaNode, XMLNamespace):
    schema_type = String
    name = "lang"
    attribute = True
    default = AcceptLanguage.EN_US
    example = AcceptLanguage.EN_CA


class WPSParameters(ExtendedMappingSchema):
    service = ExtendedSchemaNode(String(), example="WPS", description="Service selection.",
                                 validator=OneOfCaseInsensitive(["WPS"]))
    request = ExtendedSchemaNode(String(), example="GetCapabilities", description="WPS operation to accomplish",
                                 validator=OneOfCaseInsensitive(["GetCapabilities", "DescribeProcess", "Execute"]))
    version = Version(exaple="1.0.0", default="1.0.0", validator=OneOf(["1.0.0", "2.0.0", "2.0"]))
    identifier = ExtendedSchemaNode(String(), exaple="hello", missing=drop,
                                    example="example-process,another-process",
                                    description="Single or comma-separated list of process identifiers to describe, "
                                                "and single one for execution.")
    data_inputs = ExtendedSchemaNode(String(), name="DataInputs", missing=drop,
                                     example="message=hi&names=user1,user2&value=1",
                                     description="Process execution inputs provided as Key-Value Pairs (KVP).")


class WPSOperationGetNoContent(ExtendedMappingSchema):
    description = "No content body provided (GET requests)."
    default = {}


class WPSOperationPost(ExtendedMappingSchema):
    _schema = "http://schemas.opengis.net/wps/1.0.0/common/RequestBaseType.xsd"
    accepted_versions = OWSAcceptVersions(missing=drop, default="1.0.0")
    language = OWSLanguageAttribute(missing=drop)
    service = OWSService()


class WPSGetCapabilitiesPost(WPSOperationPost, WPSNamespace):
    _schema = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_request.xsd"
    name = "GetCapabilities"
    title = "GetCapabilities"


class OWSIdentifier(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Identifier"


class OWSIdentifierList(ExtendedSequenceSchema, OWSNamespace):
    name = "Identifiers"
    item = OWSIdentifier()


class OWSTitle(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Title"


class OWSAbstract(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Abstract"


class OWSMetadataLink(ExtendedSchemaNode, XMLObject):
    schema_name = "Metadata"
    schema_type = String
    attribute = True
    name = "Metadata"
    prefix = "xlink"
    example = "WPS"
    wrapped = False  # metadata xlink at same level as other items


class OWSMetadata(ExtendedSequenceSchema, OWSNamespace):
    schema_type = String
    name = "Metadata"
    title = OWSMetadataLink(missing=drop)


class WPSDescribeProcessPost(WPSOperationPost, WPSNamespace):
    _schema = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_request.xsd"
    name = "DescribeProcess"
    title = "DescribeProcess"
    identifier = OWSIdentifierList(
        description="Single or comma-separated list of process identifier to describe.",
        example="example"
    )


class WPSExecuteDataInputs(ExtendedMappingSchema, WPSNamespace):
    description = "XML data inputs provided for WPS POST request (Execute)."
    name = "DataInputs"
    title = "DataInputs"
    # FIXME: missing details about 'DataInputs'


class WPSExecutePost(WPSOperationPost, WPSNamespace):
    _schema = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"
    name = "Execute"
    title = "Execute"
    identifier = OWSIdentifier(description="Identifier of the process to execute with data inputs.")
    dataInputs = WPSExecuteDataInputs(description="Data inputs to be provided for process execution.")


class WPSRequestBody(OneOfKeywordSchema):
    _one_of = [
        WPSExecutePost(),
        WPSDescribeProcessPost(),
        WPSGetCapabilitiesPost(),
    ]
    examples = {
        "Execute": {
            "summary": "Execute request example.",
            "value": EXAMPLES["wps_execute_request.xml"]
        }
    }


class WPSHeaders(ExtendedMappingSchema):
    accept = AcceptHeader(missing=drop)


class WPSEndpointGet(ExtendedMappingSchema):
    header = WPSHeaders()
    querystring = WPSParameters()
    body = WPSOperationGetNoContent(missing=drop)


class WPSEndpointPost(ExtendedMappingSchema):
    header = WPSHeaders()
    body = WPSRequestBody()


class XMLBooleanAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = Boolean
    attribute = True


class XMLString(ExtendedSchemaNode, XMLObject):
    schema_type = String


class OWSString(ExtendedSchemaNode, OWSNamespace):
    schema_type = String


class OWSKeywordList(ExtendedSequenceSchema, OWSNamespace):
    title = "OWSKeywords"
    keyword = OWSString(name="Keyword", title="OWSKeyword", example="Weaver")


class OWSType(ExtendedMappingSchema, OWSNamespace):
    schema_type = String
    name = "Type"
    example = "theme"
    additionalProperties = {
        "codeSpace": {
            "type": "string",
            "example": "ISOTC211/19115",
            "xml": {"attribute": True}
        }
    }


class OWSPhone(ExtendedMappingSchema, OWSNamespace):
    name = "Phone"
    voice = OWSString(name="Voice", title="OWSVoice", example="1-234-567-8910", missing=drop)
    facsimile = OWSString(name="Facsimile", title="OWSFacsimile", missing=drop)


class OWSAddress(ExtendedMappingSchema, OWSNamespace):
    name = "Address"
    delivery_point = OWSString(name="DeliveryPoint", title="OWSDeliveryPoint",
                               example="123 Place Street", missing=drop)
    city = OWSString(name="City", title="OWSCity", example="Nowhere", missing=drop)
    country = OWSString(name="Country", title="OWSCountry", missing=drop)
    admin_area = OWSString(name="AdministrativeArea", title="AdministrativeArea", missing=drop)
    postal_code = OWSString(name="PostalCode", title="OWSPostalCode", example="A1B 2C3", missing=drop)
    email = OWSString(name="ElectronicMailAddress", title="OWSElectronicMailAddress",
                      example="mail@me.com", validator=Email, missing=drop)


class OWSContactInfo(ExtendedMappingSchema, OWSNamespace):
    name = "ContactInfo"
    phone = OWSPhone(missing=drop)
    address = OWSAddress(missing=drop)


class OWSServiceContact(ExtendedMappingSchema, OWSNamespace):
    name = "ServiceContact"
    individual = OWSString(name="IndividualName", title="OWSIndividualName", example="John Smith", missing=drop)
    position = OWSString(name="PositionName", title="OWSPositionName", example="One-Man Team", missing=drop)
    contact = OWSContactInfo(missing=drop, default={})


class OWSServiceProvider(ExtendedMappingSchema, OWSNamespace):
    description = "Details about the institution providing the service."
    name = "ServiceProvider"
    title = "ServiceProvider"
    provider_name = OWSString(name="ProviderName", title="OWSProviderName", example="EXAMPLE")
    provider_site = OWSString(name="ProviderName", title="OWSProviderName", example="http://schema-example.com")
    contact = OWSServiceContact(required=False, defalult={})


class WPSDescriptionType(ExtendedMappingSchema, OWSNamespace):
    _schema = "http://schemas.opengis.net/wps/1.0.0/common/DescriptionType.xsd"
    name = "DescriptionType"
    _title = OWSTitle(description="Title of the service.", example="Weaver")
    abstract = OWSAbstract(description="Detail about the service.", example="Weaver WPS example schema.", missing=drop)
    metadata = OWSMetadata(description="Metadata of the service.", example="Weaver WPS example schema.", missing=drop)


class OWSServiceIdentification(WPSDescriptionType, OWSNamespace):
    name = "ServiceIdentification"
    title = "ServiceIdentification"
    keywords = OWSKeywordList(name="Keywords")
    type = OWSType()
    svc_type = OWSString(name="ServiceType", title="ServiceType", example="WPS")
    svc_type_ver1 = OWSString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="1.0.0")
    svc_type_ver2 = OWSString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="2.0.0")
    fees = OWSString(name="Fees", title="Fees", example="NONE", missing=drop, default="NONE")
    access = OWSString(name="AccessConstraints", title="AccessConstraints",
                       example="NONE", missing=drop, default="NONE")
    provider = OWSServiceProvider()


class OWSOperationName(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    attribute = True
    name = "name"
    example = "GetCapabilities"
    validator = OneOf(["GetCapabilities", "DescribeProcess", "Execute"])


class OperationLink(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "href"
    prefix = "xlink"
    example = "http://schema-example.com/wps"


class OperationRequest(ExtendedMappingSchema, OWSNamespace):
    href = OperationLink()


class OWS_HTTP(ExtendedMappingSchema, OWSNamespace):  # noqa: N802
    get = OperationRequest(name="Get", title="OWSGet")
    post = OperationRequest(name="Post", title="OWSPost")


class OWS_DCP(ExtendedMappingSchema, OWSNamespace):  # noqa: N802
    http = OWS_HTTP(name="HTTP", missing=drop)
    https = OWS_HTTP(name="HTTPS", missing=drop)


class Operation(ExtendedMappingSchema, OWSNamespace):
    name = OWSOperationName()
    dcp = OWS_DCP()


class OperationsMetadata(ExtendedSequenceSchema, OWSNamespace):
    name = "OperationsMetadata"
    op = Operation()


class ProcessVersion(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    attribute = True


class OWSProcessSummary(ExtendedMappingSchema, WPSNamespace):
    version = ProcessVersion(name="processVersion", default="None", example="1.2",
                             description="Version of the corresponding process summary.")
    identifier = OWSIdentifier(example="example", description="Identifier to refer to the process.")
    _title = OWSTitle(example="Example Process", description="Title of the process.")
    abstract = OWSAbstract(example="Process for example schema.", description="Detail about the process.")


class WPSProcessOfferings(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOfferings"
    title = "ProcessOfferings"
    process = OWSProcessSummary(name="Process")


class WPSLanguagesType(ExtendedSequenceSchema, WPSNamespace):
    title = "LanguagesType"
    wrapped = False
    lang = OWSLanguage(name="Language")


class WPSLanguageSpecification(ExtendedMappingSchema, WPSNamespace):
    name = "Languages"
    title = "Languages"
    default = OWSLanguage(name="Default")
    supported = WPSLanguagesType(name="Supported")


class WPSResponseBaseType(PermissiveMappingSchema, WPSNamespace):
    _schema = "http://schemas.opengis.net/wps/1.0.0/common/ResponseBaseType.xsd"
    service = WPSServiceAttribute()
    version = WPSVersionAttribute()
    lang = WPSLanguageAttribute()


class WPSProcessVersion(ExtendedSchemaNode, WPSNamespace):
    _schema = "http://schemas.opengis.net/wps/1.0.0/common/ProcessVersion.xsd"
    schema_type = String
    description = "Release version of this Process."
    name = "processVersion"
    attribute = True


class WPSInputDescriptionType(WPSDescriptionType):
    identifier = OWSIdentifier(description="Unique identifier of the input.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human-readable representation of the process input.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class WPSLiteralInputType(ExtendedMappingSchema, XMLObject):
    pass


class WPSLiteralData(WPSLiteralInputType):
    name = "LiteralData"


class WPSCRSsType(ExtendedMappingSchema, WPSNamespace):
    crs = XMLString(name="CRS", description="Coordinate Reference System")


class WPSSupportedCRS(ExtendedSequenceSchema):
    crs = WPSCRSsType(name="CRS")


class WPSSupportedCRSType(ExtendedMappingSchema, WPSNamespace):
    name = "SupportedCRSsType"
    default = WPSCRSsType(name="Default")
    supported = WPSSupportedCRS(name="Supported")


class WPSBoundingBoxData(ExtendedMappingSchema, XMLObject):
    data = WPSSupportedCRSType(name="BoundingBoxData")


class WPSFormatDefinition(ExtendedMappingSchema, XMLObject):
    mime_type = XMLString(name="MimeType", default=ContentType.TEXT_PLAIN, example=ContentType.TEXT_PLAIN)
    encoding = XMLString(name="Encoding", missing=drop, example="base64")
    schema = XMLString(name="Schema", missing=drop)


class WPSFileFormat(ExtendedMappingSchema, XMLObject):
    name = "Format"
    format_item = WPSFormatDefinition()


class WPSFormatList(ExtendedSequenceSchema):
    format_item = WPSFileFormat()


class WPSComplexInputType(ExtendedMappingSchema, WPSNamespace):
    max_mb = XMLString(name="maximumMegabytes", attribute=True)
    defaults = WPSFileFormat(name="Default")
    supported = WPSFormatList(name="Supported")


class WPSComplexData(ExtendedMappingSchema, XMLObject):
    data = WPSComplexInputType(name="ComplexData")


class WPSInputFormChoice(OneOfKeywordSchema):
    title = "InputFormChoice"
    _one_of = [
        WPSComplexData(),
        WPSLiteralData(),
        WPSBoundingBoxData(),
    ]


class WPSMinOccursAttribute(MinOccursDefinition, XMLObject):
    name = "minOccurs"
    attribute = True


class WPSMaxOccursAttribute(MinOccursDefinition, XMLObject):
    name = "maxOccurs"
    prefix = drop
    attribute = True


class WPSDataInputDescription(ExtendedMappingSchema):
    min_occurs = WPSMinOccursAttribute()
    max_occurs = WPSMaxOccursAttribute()


class WPSDataInputItem(AllOfKeywordSchema, WPSNamespace):
    _all_of = [
        WPSInputDescriptionType(),
        WPSInputFormChoice(),
        WPSDataInputDescription(),
    ]


class WPSDataInputs(ExtendedSequenceSchema, WPSNamespace):
    name = "DataInputs"
    title = "DataInputs"
    input = WPSDataInputItem()


class WPSOutputDescriptionType(WPSDescriptionType):
    name = "OutputDescriptionType"
    title = "OutputDescriptionType"
    identifier = OWSIdentifier(description="Unique identifier of the output.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human-readable representation of the process output.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class ProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSOutputDescriptionType()


class WPSGetCapabilities(WPSResponseBaseType):
    _schema = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_response.xsd"
    name = "Capabilities"
    title = "Capabilities"  # not to be confused by 'GetCapabilities' used for request
    svc = OWSServiceIdentification()
    ops = OperationsMetadata()
    offering = WPSProcessOfferings()
    languages = WPSLanguageSpecification()


class WPSProcessDescriptionType(WPSResponseBaseType, WPSProcessVersion):
    name = "ProcessDescriptionType"
    description = "Description of the requested process by identifier."
    store = XMLBooleanAttribute(name="storeSupported", example=True, default=True)
    status = XMLBooleanAttribute(name="statusSupported", example=True, default=True)
    inputs = WPSDataInputs()
    outputs = ProcessOutputs()


class WPSProcessDescriptionList(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessDescriptions"
    title = "ProcessDescriptions"
    description = "Listing of process description for every requested identifier."
    wrapped = False
    process = WPSProcessDescriptionType()


class WPSDescribeProcess(WPSResponseBaseType):
    _schema = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_response.xsd"
    name = "DescribeProcess"
    title = "DescribeProcess"
    process = WPSProcessDescriptionList()


class WPSStatusLocationAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "statusLocation"
    prefix = drop
    attribute = True
    format = "file"


class WPSServiceInstanceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "serviceInstance"
    prefix = drop
    attribute = True
    format = "url"


class CreationTimeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = DateTime
    name = "creationTime"
    title = "CreationTime"
    prefix = drop
    attribute = True


class WPSStatusSuccess(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    name = "ProcessSucceeded"
    title = "ProcessSucceeded"


class WPSStatusFailed(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    name = "ProcessFailed"
    title = "ProcessFailed"


class WPSStatus(ExtendedMappingSchema, WPSNamespace):
    name = "Status"
    title = "Status"
    creationTime = CreationTimeAttribute()
    status_success = WPSStatusSuccess(missing=drop)
    status_failed = WPSStatusFailed(missing=drop)


class WPSProcessSummary(ExtendedMappingSchema, WPSNamespace):
    name = "Process"
    title = "Process"
    identifier = OWSIdentifier()
    _title = OWSTitle()
    abstract = OWSAbstract(missing=drop)


class WPSOutputBase(ExtendedMappingSchema):
    identifier = OWSIdentifier()
    _title = OWSTitle()
    abstract = OWSAbstract(missing=drop)


class WPSOutputDefinitionItem(WPSOutputBase, WPSNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'WPSProcessOutputs'
    title = "OutputDefinition"


class WPSOutputDefinitions(ExtendedSequenceSchema, WPSNamespace):
    name = "OutputDefinitions"
    title = "OutputDefinitions"
    out_def = WPSOutputDefinitionItem()


class WPSOutputLiteral(ExtendedMappingSchema):
    data = ()


class WPSReference(ExtendedMappingSchema, WPSNamespace):
    href = XMLReferenceAttribute()
    mimeType = MimeTypeAttribute()
    encoding = EncodingAttribute()


class WPSOutputReference(ExtendedMappingSchema):
    title = "OutputReference"
    reference = WPSReference(name="Reference")


class WPSOutputData(OneOfKeywordSchema):
    _one_of = [
        WPSOutputLiteral(),
        WPSOutputReference(),
    ]


class WPSDataOutputItem(AllOfKeywordSchema, WPSNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'WPSOutputDefinitions'
    title = "DataOutput"
    _all_of = [
        WPSOutputBase(),
        WPSOutputData(),
    ]


class WPSProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSDataOutputItem()


class WPSExecuteResponse(WPSResponseBaseType, WPSProcessVersion):
    _schema = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_response.xsd"
    name = "ExecuteResponse"
    title = "ExecuteResponse"  # not to be confused by 'Execute' used for request
    location = WPSStatusLocationAttribute()
    svc_loc = WPSServiceInstanceAttribute()
    process = WPSProcessSummary()
    status = WPSStatus()
    inputs = WPSDataInputs(missing=drop)          # when lineage is requested only
    out_def = WPSOutputDefinitions(missing=drop)  # when lineage is requested only
    outputs = WPSProcessOutputs()


class WPSXMLSuccessBodySchema(OneOfKeywordSchema):
    _one_of = [
        WPSGetCapabilities(),
        WPSDescribeProcess(),
        WPSExecuteResponse(),
    ]


class OWSExceptionCodeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "exceptionCode"
    title = "Exception"
    attribute = True


class OWSExceptionLocatorAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "locator"
    attribute = True


class OWSExceptionText(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "ExceptionText"


class OWSException(ExtendedMappingSchema, OWSNamespace):
    name = "Exception"
    title = "Exception"
    code = OWSExceptionCodeAttribute(example="MissingParameterValue")
    locator = OWSExceptionLocatorAttribute(default="None", example="service")
    text = OWSExceptionText(example="Missing service")


class OWSExceptionReport(ExtendedMappingSchema, OWSNamespace):
    name = "ExceptionReport"
    title = "ExceptionReport"
    exception = OWSException()


class WPSException(ExtendedMappingSchema):
    report = OWSExceptionReport()


class OkWPSResponse(ExtendedMappingSchema):
    description = "WPS operation successful"
    header = XmlHeader()
    body = WPSXMLSuccessBodySchema()


class ErrorWPSResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred on WPS endpoint."
    header = XmlHeader()
    body = WPSException()


class ProviderEndpoint(ProviderPath):
    header = RequestHeaders()


class ProcessDescriptionQuery(ExtendedMappingSchema):
    # see: 'ProcessDescription' schema and 'Process.offering' method
    schema = ExtendedSchemaNode(
        String(), example=ProcessSchema.OGC, default=ProcessSchema.OGC,
        validator=OneOfCaseInsensitive(ProcessSchema.values()),
        summary="Selects the desired schema representation of the process description.",
        description=(
            "Selects the desired schema representation of the process description. "
            f"When '{ProcessSchema.OGC}' is used, inputs and outputs will be represented as mapping of objects. "
            "Process metadata are also directly provided at the root of the content. "
            f"When '{ProcessSchema.OLD}' is used, inputs and outputs will be represented as list of objects with ID. "
            "Process metadata are also reported nested under a 'process' field. "
            "See '#/definitions/ProcessDescription' schema for more details about each case. "
            "These schemas are all represented with JSON content. "
            f"For the XML definition, employ '{ProcessSchema.WPS}' or any format selector (f, format, Accept) with XML."
        )
    )


class ProviderProcessEndpoint(ProviderProcessPath):
    header = RequestHeaders()
    querystring = ProcessDescriptionQuery()


class LocalProcessDescriptionQuery(ProcessDescriptionQuery, LocalProcessQuery, FormatQuery):
    pass


class LocalProcessEndpointHeaders(AcceptFormatHeaders, RequestHeaders):  # order important for descriptions to appear
    pass


class ProcessEndpoint(LocalProcessPath):
    header = LocalProcessEndpointHeaders()
    querystring = LocalProcessDescriptionQuery()


class ProcessPackageEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProcessPayloadEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProcessQuoteEstimatorGetEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProcessQuoteEstimatorPutEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()
    body = QuoteEstimatorSchema()


class ProcessQuoteEstimatorDeleteEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProcessVisibilityGetEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProcessVisibilityPutEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()
    body = VisibilitySchema()


class ProviderJobEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


class JobEndpoint(JobPath):
    header = RequestHeaders()


class ProcessInputsEndpoint(LocalProcessPath, JobPath):
    header = RequestHeaders()


class ProviderInputsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


class JobInputsOutputsQuery(ExtendedMappingSchema):
    schema = ExtendedSchemaNode(
        String(),
        title="JobInputsOutputsQuerySchema",
        example=JobInputsOutputsSchema.OGC,
        default=JobInputsOutputsSchema.OLD,
        validator=OneOfCaseInsensitive(JobInputsOutputsSchema.values()),
        summary="Selects the schema employed for representation of submitted job inputs and outputs.",
        description=(
            "Selects the schema employed for representing job inputs and outputs that were submitted for execution. "
            f"When '{JobInputsOutputsSchema.OLD}' is employed, listing of object with IDs is returned. "
            f"When '{JobInputsOutputsSchema.OGC}' is employed, mapping of object definitions is returned. "
            "If no schema is requested, the original formats from submission are employed, which could be a mix of "
            "both representations. Providing a schema forces their corresponding conversion as applicable."
        )
    )


class JobInputsEndpoint(JobPath):
    header = RequestHeaders()
    querystring = JobInputsOutputsQuery()


class JobResultsQuery(ExtendedMappingSchema):
    schema = ExtendedSchemaNode(
        String(),
        title="JobOutputResultsSchema",
        example=JobInputsOutputsSchema.OGC,
        default=JobInputsOutputsSchema.OLD,
        validator=OneOfCaseInsensitive(JobInputsOutputsSchema.values()),
        summary="Selects the schema employed for representation of job outputs.",
        description=(
            "Selects the schema employed for representation of job results (produced outputs) "
            "for providing file Content-Type details. "
            f"When '{JobInputsOutputsSchema.OLD}' is employed, "
            "'format.mimeType' is used and 'type' is reported as well. "
            f"When '{JobInputsOutputsSchema.OGC}' is employed, "
            "'format.mediaType' is used and 'type' is reported as well. "
            "When the '+strict' value is added, only the 'format' or 'type' will be represented according to the "
            f"reference standard ({JobInputsOutputsSchema.OGC}, {JobInputsOutputsSchema.OLD}) representation."
        )
    )


class LocalProcessJobResultsQuery(LocalProcessQuery, JobResultsQuery):
    pass


class JobOutputsEndpoint(JobPath):
    header = RequestHeaders()
    querystring = LocalProcessJobResultsQuery()


class ProcessOutputsEndpoint(LocalProcessPath, JobPath):
    header = RequestHeaders()
    querystring = LocalProcessJobResultsQuery()


class ProviderOutputsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()
    querystring = JobResultsQuery()


class ProcessResultEndpoint(ProcessOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProviderResultEndpoint(ProviderOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class JobResultEndpoint(JobPath):
    deprecated = True
    header = RequestHeaders()


class ProcessResultsEndpoint(LocalProcessPath, JobPath):
    header = RequestHeaders()


class ProviderResultsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


class JobResultsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


class ProviderExceptionsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


class JobExceptionsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessExceptionsEndpoint(LocalProcessPath, JobPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProviderLogsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


class JobLogsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessLogsEndpoint(LocalProcessPath, JobPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class JobStatisticsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessJobStatisticsEndpoint(LocalProcessPath, JobPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProviderJobStatisticsEndpoint(ProviderProcessPath, JobPath):
    header = RequestHeaders()


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class ProviderPublic(ExtendedMappingSchema):
    public = ExtendedSchemaNode(
        Boolean(),
        default=False,
        description="Whether the service is defined as publicly visible. "
                    "This will not control allowance/denial of requests to the registered endpoint of the service. "
                    "It only indicates if it should appear during listing of providers."
    )


class CreateProviderRequestBody(ProviderPublic):
    id = AnyIdentifier()
    url = URL(description="Endpoint where to query the provider.")


class ExecuteInputDataType(InputIdentifierType):
    pass


class ExecuteOutputDataType(OutputIdentifierType):
    pass


class ExecuteOutputDefinition(ExtendedMappingSchema):
    transmissionMode = TransmissionModeEnum(missing=drop)
    format = Format(missing=drop)


class ExecuteOutputItem(ExecuteOutputDataType, ExecuteOutputDefinition):
    pass


class ExecuteOutputSpecList(ExtendedSequenceSchema):
    """
    Filter list of outputs to be obtained from execution and their reporting method.
    """
    output = ExecuteOutputItem()


class ExecuteOutputMapAdditionalProperties(ExtendedMappingSchema):
    output_id = ExecuteOutputDefinition(variable="{output-id}", title="ExecuteOutputSpecMap",
                                        description="Desired output reporting method.")


class ExecuteOutputSpecMap(AnyOfKeywordSchema):
    _any_of = [
        ExecuteOutputMapAdditionalProperties(),  # normal {"<output-id>": {...}}
        EmptyMappingSchema(),                    # allows explicitly provided {}
    ]


class ExecuteOutputSpec(OneOfKeywordSchema):
    """
    Filter list of outputs to be obtained from execution and define their reporting method.
    """
    _one_of = [
        # OLD format: {"outputs": [{"id": "<id>", "transmissionMode": "value|reference"}, ...]}
        ExecuteOutputSpecList(),
        # OGC-API:    {"inputs": {"<id>": {"transmissionMode": "value|reference"}, ...}}
        ExecuteOutputSpecMap(),
    ]


class ProviderNameSchema(AnyIdentifier):
    title = "ProviderName"
    description = "Identifier of the remote provider."


class ProviderSummarySchema(DescriptionType, ProviderPublic, DescriptionMeta, DescriptionLinks):
    """
    Service provider summary definition.
    """
    id = ProviderNameSchema()
    url = URL(description="Endpoint of the service provider.")
    type = ExtendedSchemaNode(String())

    _sort_first = PROVIDER_DESCRIPTION_FIELD_FIRST
    _sort_after = PROVIDER_DESCRIPTION_FIELD_AFTER


class ProviderCapabilitiesSchema(ProviderSummarySchema):
    """
    Service provider detailed capabilities.
    """


class TransmissionModeList(ExtendedSequenceSchema):
    transmissionMode = TransmissionModeEnum()


class JobControlOptionsList(ExtendedSequenceSchema):
    jobControlOption = JobControlOptionsEnum()


class ExceptionReportType(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String())
    description = ExtendedSchemaNode(String(), missing=drop)


class ProcessControl(ExtendedMappingSchema):
    jobControlOptions = JobControlOptionsList(missing=ExecuteControlOption.values(),
                                              default=ExecuteControlOption.values())
    outputTransmission = TransmissionModeList(missing=ExecuteTransmissionMode.values(),
                                              default=ExecuteTransmissionMode.values())


class ProcessLocations(ExtendedMappingSchema):
    """
    Additional endpoint locations specific to the process.
    """
    processDescriptionURL = URL(description="Process description endpoint using OGC-API interface.",
                                missing=drop, title="processDescriptionURL")
    processEndpointWPS1 = URL(description="Process description endpoint using WPS-1 interface.",
                              missing=drop, title="processEndpointWPS1")
    executeEndpoint = URL(description="Endpoint where the process can be executed from.",
                          missing=drop, title="executeEndpoint")
    # 'links' already included via 'ProcessDescriptionType->DescriptionType'


class ProcessSummary(
    ProcessDescriptionType,
    DescriptionMeta,
    ProcessControl,
    ProcessLocations,
    DescriptionLinks
):
    """
    Summary process definition.
    """
    _schema = f"{OGC_API_SCHEMA_CORE}/processSummary.yaml"
    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessSummaryList(ExtendedSequenceSchema):
    summary = ProcessSummary()


class ProcessNamesList(ExtendedSequenceSchema):
    process_name = ProcessIdentifierTag(
        description="Process identifier or tagged representation if revision was requested."
    )


class ProcessListing(OneOfKeywordSchema):
    _one_of = [
        ProcessSummaryList(description="Listing of process summary details from existing definitions."),
        ProcessNamesList(description="Listing of process names when not requesting details.",
                         missing=drop),  # in case of empty list, both schema are valid, drop this one to resolve
    ]


class ProcessCollection(ExtendedMappingSchema):
    processes = ProcessListing()


class ProcessPagingQuery(ExtendedMappingSchema):
    sort = ProcessSortEnum(missing=drop)
    # if page is omitted but limit provided, use reasonable zero by default
    page = ExtendedSchemaNode(Integer(allow_string=True), missing=0, default=0, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(allow_string=True), missing=None, default=None, validator=Range(min=1),
                               schema=f"{OGC_API_PROC_PART1_PARAMETERS}/limit.yaml")


class ProcessVisibility(ExtendedMappingSchema):
    visibility = VisibilityValue(missing=drop)


class ProcessDeploymentProfile(ExtendedMappingSchema):
    deploymentProfile = URL(missing=drop)


class Process(
    # following are like 'ProcessSummary',
    # except without 'ProcessControl' and 'DescriptionLinks' that are outside the nested 'process'
    ProcessDescriptionType, DescriptionMeta,
    # following are additional fields only in description, just like for OGC-API ProcessDescription
    ProcessContext, ProcessVisibility, ProcessLocations
):
    """
    Old nested process schema for process description.
    """
    # note: deprecated in favor of OGC-API schema
    inputs = DescribeInputTypeList(description="Inputs definition of the process.")
    outputs = DescribeOutputTypeList(description="Outputs definition of the process.")

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessDescriptionOLD(ProcessControl, ProcessDeploymentProfile, DescriptionLinks):
    """
    Old schema for process description.
    """
    deprecated = True
    process = Process()

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST_OLD_SCHEMA
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER_OLD_SCHEMA


class ProcessDescriptionOGC(
    ProcessSummary,
    ProcessContext,
    ProcessVisibility,
    ProcessLocations,
    ProcessDeploymentProfile,
    DescriptionLinks
):
    """
    OGC-API schema for process description.
    """
    # technically, empty inputs are allowed for processes that should generate constant/randomized outputs
    # example:
    #   https://pavics.ouranos.ca/twitcher/ows/proxy/catalog
    #   ?service=WPS&request=DescribeProcess&version=1.0.0&identifier=pavicstestdocs
    inputs = DescribeInputTypeMap(description="Inputs definition of the process.", missing=drop, default={})
    outputs = DescribeOutputTypeMap(description="Outputs definition of the process.")

    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/process.yaml"
    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessDescription(OneOfKeywordSchema):
    """
    Supported schema representations of a process description (based on specified query parameters).
    """
    _one_of = [
        ProcessDescriptionOGC,
        ProcessDescriptionOLD,
    ]


class ProcessDeployment(ProcessSummary, ProcessContext, ProcessDeployMeta):
    # override ID to forbid deploy to contain a tagged version part
    # if version should be applied, it must be provided with its 'Version' field
    id = ProcessIdentifier()

    # explicit "abstract" handling for bw-compat, new versions should use "description"
    # only allowed in deploy to support older servers that report abstract (or parsed from WPS-1/2)
    # recent OGC-API v1+ will usually provide directly "description" as per the specification
    abstract = ExtendedSchemaNode(String(), missing=drop, deprecated=True,
                                  description="Detailed explanation of the process being deployed. "
                                              "[Deprecated] Consider using 'description' instead.")
    # allowed undefined I/O during deploy because of reference from owsContext or executionUnit
    inputs = DeployInputTypeAny(
        missing=drop, title="DeploymentInputs",
        description="Additional definitions for process inputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    f"overrides (see '{DOC_URL}/package.html#correspondence-between-cwl-and-wps-fields')")
    outputs = DeployOutputTypeAny(
        missing=drop, title="DeploymentOutputs",
        description="Additional definitions for process outputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    f"overrides (see '{DOC_URL}/package.html#correspondence-between-cwl-and-wps-fields')")
    visibility = VisibilityValue(missing=drop)

    _schema = f"{OGC_API_SCHEMA_EXT_DEPLOY}/processSummary.yaml"
    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class Duration(ExtendedSchemaNode):
    # note: using String instead of Time because timedelta object cannot be directly handled (missing parts at parsing)
    schema_type = String
    description = "Human-readable representation of the duration."
    example = "hh:mm:ss"


# FIXME: use ISO-8601 duration (?) - P[n]Y[n]M[n]DT[n]H[n]M[n]S
#       https://pypi.org/project/isodate/
#       https://en.wikipedia.org/wiki/ISO_8601#Durations
#   See:
#       'duration.to_iso8601' already employed for quotes, should apply for jobs as well
class DurationISO(ExtendedSchemaNode):
    """
    Duration represented using ISO-8601 format.

    .. seealso::
        - https://json-schema.org/draft/2019-09/json-schema-validation.html#rfc.section.7.3.1
        - :rfc:`3339#appendix-A`
    """
    schema_type = String
    description = "ISO-8601 representation of the duration."
    example = "P[n]Y[n]M[n]DT[n]H[n]M[n]S"
    format = "duration"

    def deserialize(self, cstruct):
        # type: (Union[datetime.timedelta, str]) -> str
        if isinstance(cstruct, datetime.timedelta) or isinstance(cstruct, str) and not cstruct.startswith("P"):
            return duration.to_iso8601(cstruct)
        return cstruct


class JobStatusInfo(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/statusInfo.yaml"
    jobID = JobID()
    processID = ProcessIdentifierTag(missing=None, default=None,
                                     description="Process identifier corresponding to the job execution.")
    providerID = ProcessIdentifier(missing=None, default=None,
                                   description="Provider identifier corresponding to the job execution.")
    type = JobTypeEnum(description="Type of the element associated to the creation of this job.")
    status = JobStatusEnum(description="Last updated status.")
    message = ExtendedSchemaNode(String(), missing=drop, description="Information about the last status update.")
    created = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process execution job was created.")
    started = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process started execution if applicable.")
    finished = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                  description="Timestamp when the process completed execution if applicable.")
    updated = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp of the last update of the job status. This can correspond to "
                                             "any of the other timestamps according to current execution status or "
                                             "even slightly after job finished execution according to the duration "
                                             "needed to deallocate job resources and store results.")
    duration = Duration(missing=drop, description="Duration since the start of the process execution.")
    runningDuration = DurationISO(missing=drop,
                                  description="Duration in ISO-8601 format since the start of the process execution.")
    runningSeconds = Number(missing=drop,
                            description="Duration in seconds since the start of the process execution.")
    expirationDate = ExtendedSchemaNode(DateTime(), missing=drop,
                                        description="Timestamp when the job will be canceled if not yet completed.")
    estimatedCompletion = ExtendedSchemaNode(DateTime(), missing=drop)
    nextPoll = ExtendedSchemaNode(DateTime(), missing=drop,
                                  description="Timestamp when the job will be prompted for updated status details.")
    percentCompleted = Number(example=0, validator=Range(min=0, max=100),
                              description="Completion percentage of the job as indicated by the process.")
    progress = ExtendedSchemaNode(Integer(), example=100, validator=Range(0, 100),
                                  description="Completion progress of the job (alias to 'percentCompleted').")
    links = LinkList(missing=drop)


class JobEntrySchema(OneOfKeywordSchema):
    # note:
    #   Since JobID is a simple string (not a dict), no additional mapping field can be added here.
    #   They will be discarded by `OneOfKeywordSchema.deserialize()`.
    _one_of = [
        JobStatusInfo,
        UUID(description="Job ID."),
    ]


class JobCollection(ExtendedSequenceSchema):
    item = JobEntrySchema()


class CreatedJobStatusSchema(DescriptionSchema):
    jobID = JobID(description="Unique identifier of the created job for execution.")
    processID = ProcessIdentifierTag(description="Identifier of the process that will be executed.")
    providerID = AnyIdentifier(description="Remote provider identifier if applicable.", missing=drop)
    status = ExtendedSchemaNode(String(), example=Status.ACCEPTED)
    location = ExtendedSchemaNode(String(), example="http://{host}/weaver/processes/{my-process-id}/jobs/{my-job-id}")


class PagingBodySchema(ExtendedMappingSchema):
    # don't use defaults if missing, otherwise we might report incorrect values compared to actual contents
    count = ExtendedSchemaNode(Integer(), missing=drop, validator=Range(min=0),
                               description="Number of items returned within this paged result.")
    limit = ExtendedSchemaNode(Integer(), missing=drop, validator=Range(min=1, max=1000),
                               schema=f"{OGC_API_PROC_PART1_PARAMETERS}/limit.yaml",
                               description="Maximum number of items returned per page.")
    page = ExtendedSchemaNode(Integer(), missing=drop, validator=Range(min=0),
                              description="Paging index.")
    total = ExtendedSchemaNode(Integer(), missing=drop, validator=Range(min=0),
                               description="Total number of items regardless of paging.")


class GetPagingJobsSchema(PagingBodySchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/jobList.yaml"  # technically, no 'links' yet, but added after by oneOf
    jobs = JobCollection()


class JobCategoryFilters(PermissiveMappingSchema):
    category = ExtendedSchemaNode(String(), title="CategoryFilter", variable="{category}", default=None, missing=None,
                                  description="Value of the corresponding parameter forming that category group.")


class GroupedJobsCategorySchema(ExtendedMappingSchema):
    category = JobCategoryFilters(description="Grouping values that compose the corresponding job list category.")
    jobs = JobCollection(description="List of jobs that matched the corresponding grouping values.")
    count = ExtendedSchemaNode(Integer(), description="Number of matching jobs for the corresponding group category.")


class GroupedCategoryJobsSchema(ExtendedSequenceSchema):
    job_group_category_item = GroupedJobsCategorySchema()


class GetGroupedJobsSchema(ExtendedMappingSchema):
    groups = GroupedCategoryJobsSchema()


class GetQueriedJobsSchema(OneOfKeywordSchema):
    _one_of = [
        GetPagingJobsSchema(description="Matched jobs according to filter queries."),
        GetGroupedJobsSchema(description="Matched jobs grouped by specified categories."),
    ]
    total = ExtendedSchemaNode(Integer(),
                               description="Total number of matched jobs regardless of grouping or paging result.")
    links = LinkList()  # required by OGC schema

    _sort_first = JOBS_LISTING_FIELD_FIRST
    _sort_after = JOBS_LISTING_FIELD_AFTER


class DismissedJobSchema(ExtendedMappingSchema):
    status = JobStatusEnum()
    jobID = JobID()
    message = ExtendedSchemaNode(String(), example="Job dismissed.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0)


# same as base Format, but for process/job responses instead of process submission
# (ie: 'Format' is for allowed/supported formats, this is the result format)
class DataEncodingAttributes(FormatSelection):
    pass


class ReferenceBase(ExtendedMappingSchema):
    format = DataEncodingAttributes(missing=drop)
    body = ExtendedSchemaNode(String(), missing=drop)
    bodyReference = ReferenceURL(missing=drop)


class Reference(ReferenceBase):
    title = "Reference"
    href = ReferenceURL(description="Endpoint of the reference.")


class ExecuteReference(ReferenceBase):
    title = "ExecuteReference"
    href = ExecuteReferenceURL(description="Endpoint of the reference.")


class ArrayReference(ExtendedSequenceSchema):
    item = ExecuteReference()


class ArrayReferenceValueType(ExtendedMappingSchema):
    value = ArrayReference()


# Backward compatible data-input that allows values to be nested under 'data' or 'value' fields,
# both for literal values and link references, for inputs submitted as list-items.
# Also allows the explicit 'href' (+ optional format) reference for a link.
#
# Because this data-input structure applies only to list-items (see 'ExecuteInputItem' below), mapping is always needed.
# (i.e.: values cannot be submitted inline in the list, because field 'id' of each input must also be provided)
# For this reason, one of 'value', 'data', 'href' or 'reference' is mandatory.
class ExecuteInputAnyType(OneOfKeywordSchema):
    """
    Permissive variants that we attempt to parse automatically.
    """
    _one_of = [
        # Array of literal data with 'data' key
        ArrayLiteralDataType(),
        # same with 'value' key (OGC specification)
        ArrayLiteralValueType(),
        # Array of HTTP references with various keywords
        ArrayReferenceValueType(),
        # literal data with 'data' key
        AnyLiteralDataType(),
        # same with 'value' key (OGC specification)
        AnyLiteralValueType(),
        # HTTP references with various keywords
        LiteralReference(),
        ExecuteReference()
    ]


class ExecuteInputItem(ExecuteInputDataType, ExecuteInputAnyType):
    description = (
        "Default value to be looked for uses key 'value' to conform to older drafts of OGC-API standard. "
        "Even older drafts that allowed other fields 'data' instead of 'value' and 'reference' instead of 'href' "
        "are also looked for to remain back-compatible."
    )


# backward compatible definition:
#
#   inputs: [
#     {"id": "<id>", "value": <data>},
#     {"id": "<id>", "href": <link>}
#     ... (other variants) ...
#   ]
#
class ExecuteInputListValues(ExtendedSequenceSchema):
    input_item = ExecuteInputItem(summary="Received list input value definition during job submission.")


# same as 'ExecuteInputReference', but using 'OGC' schema with 'type' field
# Defined as:
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/link.yaml
# But explicitly in the context of an execution input, rather than any other link (eg: metadata)
class ExecuteInputFileLink(Link):  # for other metadata (title, hreflang, etc.)
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/link.yaml"
    href = ExecuteReferenceURL(  # not just a plain 'URL' like 'Link' has (extended with s3, vault, etc.)
        description="Location of the file reference."
    )
    type = MediaType(
        default=ContentType.TEXT_PLAIN,  # as per OGC, not mandatory (ie: 'default' supported format)
        description="IANA identifier of content-type located at the link."
    )
    rel = LinkRelationshipType(missing=drop)  # optional opposite to normal 'Link'


# same as 'ExecuteInputLink', but using 'OLD' schema with 'format' field
class ExecuteInputReference(Reference):
    summary = "Execute input reference link definition with parameters."


class ExecuteInputFile(AnyOfKeywordSchema):
    _any_of = [                   # 'href' required for both to provide file link/reference
        ExecuteInputFileLink(),   # 'OGC' schema with 'type: <MediaType>'
        ExecuteInputReference(),  # 'OLD' schema with 'format: {mimeType|mediaType: <MediaType>}'
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/inputValueNoObject.yaml
# Any literal value directly provided inline in input mapping.
#
#   {"inputs": {"<id>": <literal-data>}}
#
# Excludes objects to avoid conflict with later object mapping and {"value": <data>} definitions.
# Excludes array literals that will be defined separately with allowed array of any item within this schema.
# FIXME: does not support byte/binary type (string + format:byte) - see also: 'AnyLiteralType'
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/binaryInputValue.yaml
# FIXME: does not support bbox
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/bbox.yaml
class ExecuteInputInlineValue(OneOfKeywordSchema):
    description = "Execute input value provided inline."
    _one_of = [
        ExtendedSchemaNode(Float(), title="ExecuteInputValueFloat"),
        ExtendedSchemaNode(Integer(), title="ExecuteInputValueInteger"),
        ExtendedSchemaNode(Boolean(), title="ExecuteInputValueBoolean"),
        ExtendedSchemaNode(String(), title="ExecuteInputValueString"),
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/inputValue.yaml
#
#   oneOf:
#     - $ref: "inputValueNoObject.yaml"
#     - type: object
class ExecuteInputObjectData(OneOfKeywordSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/inputValue.yaml"
    description = "Data value of any schema "
    _one_of = [
        ExecuteInputInlineValue(),
        PermissiveMappingSchema(description="Data provided as any object schema."),
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/qualifiedInputValue.yaml
class ExecuteInputQualifiedValue(Format):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/qualifiedInputValue.yaml"
    value = ExecuteInputObjectData()    # can be anything, including literal value, array of them, nested object


# https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/inlineOrRefData.yaml
#
#   oneOf:
#     - $ref: "inputValueNoObject.yaml"     # in OGC-API spec, includes a generic array
#     - $ref: "qualifiedInputValue.yaml"
#     - $ref: "link.yaml"
#
class ExecuteInputInlineOrRefData(OneOfKeywordSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/inlineOrRefData.yaml"
    _one_of = [
        ExecuteInputInlineValue(),     # <inline-literal>
        ExecuteInputQualifiedValue(),  # {"value": <anything>, "mediaType": "<>", "schema": <OAS link or object>}
        ExecuteInputFile(),            # 'href' with either 'type' (OGC) or 'format' (OLD)
        # FIXME: other types here, 'bbox+crs', 'collection', 'nested process', etc.
    ]


class ExecuteInputArrayValues(ExtendedSequenceSchema):
    item_value = ExecuteInputInlineOrRefData()


# combine 'inlineOrRefData' and its 'array[inlineOrRefData]' variants to simplify 'ExecuteInputAny' definition
class ExecuteInputData(OneOfKeywordSchema):
    description = "Execute data definition of the input."
    _one_of = [
        ExecuteInputInlineOrRefData,
        ExecuteInputArrayValues,
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/execute.yaml
#
#   inputs:
#     additionalProperties:           # this is the below 'variable=<input-id>'
#       oneOf:
#       - $ref: "inlineOrRefData.yaml"
#       - type: array
#         items:
#           $ref: "inlineOrRefData.yaml"
#
class ExecuteInputMapAdditionalProperties(ExtendedMappingSchema):
    input_id = ExecuteInputData(variable="{input-id}", title="ExecuteInputValue",
                                description="Received mapping input value definition during job submission.")


class ExecuteInputMapValues(AnyOfKeywordSchema):
    _any_of = [
        ExecuteInputMapAdditionalProperties(),  # normal {"<input-id>": {...}}
        EmptyMappingSchema(),                   # allows explicitly provided {}
    ]


class ExecuteInputValues(OneOfKeywordSchema):
    _one_of = [
        # OLD format: {"inputs": [{"id": "<id>", "value": <data>}, ...]}
        ExecuteInputListValues(description="Process job execution inputs defined as item listing."),
        # OGC-API:    {"inputs": {"<id>": <data>, "<id>": {"value": <data>}, ...}}
        ExecuteInputMapValues(description="Process job execution inputs defined as mapping."),
    ]


class ExecuteInputOutputs(ExtendedMappingSchema):
    # Permit unspecified (optional) inputs for processes that could technically allow no-inputs definition (CWL).
    # This is very unusual in real world scenarios, but has some possible cases: constant endpoint fetcher, RNG output.
    #
    # NOTE:
    #   It is **VERY** important to use 'default={}' and not 'missing=drop' contrary to other optional fields.
    #   Using 'drop' causes and invalid input definition to be ignored/removed and not be validated for expected schema.
    #   We want to ensure format is validated if present to rapidly report the issue and not move on to full execution.
    #   If 'inputs' are indeed omitted, the default with match against and empty 'ExecuteInputMapValues' schema.
    #   If 'inputs' are explicitly provided as '{}' or '[]', it will also behave the right way for no-inputs process.
    #
    # See tests validating both cases (incorrect schema vs optionals inputs):
    #   - 'tests.wps_restapi.test_processes.WpsRestApiProcessesTest.test_execute_process_missing_required_params'
    #   - 'tests.wps_restapi.test_providers.WpsRestApiProcessesTest.test_execute_process_no_error_not_required_params'
    #   - 'tests.wps_restapi.test_providers.WpsRestApiProcessesTest.test_get_provider_process_no_inputs'
    #   - 'tests.wps_restapi.test_colander_extras.test_oneof_variable_dict_or_list'
    inputs = ExecuteInputValues(default={}, description="Values submitted for execution.")
    outputs = ExecuteOutputSpec(
        description=(
            "Defines which outputs to be obtained from the execution (filtered or all), "
            "as well as the reporting method for each output according to 'transmissionMode', "
            "the 'response' type, and the execution 'mode' provided "
            f"(see for more details: {DOC_URL}/processes.html#execution-body)."
        ),
        default={}
    )


class Execute(ExecuteInputOutputs):
    # OGC 'execute.yaml' does not enforce any required item
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/execute.yaml"
    examples = {
        "ExecuteJSON": {
            "summary": "Execute a process job using REST JSON payload with OGC API schema.",
            "value": EXAMPLES["job_execute.json"],
        },
    }
    mode = JobExecuteModeEnum(
        missing=drop,
        default=ExecuteMode.AUTO,
        deprecated=True,
        description=(
            "Desired execution mode specified directly. This is intended for backward compatibility support. "
            "To obtain more control over execution mode selection, employ the official Prefer header instead "
            f"(see for more details: {DOC_URL}/processes.html#execution-mode)."
        ),
        validator=OneOf(ExecuteMode.values())
    )
    response = JobResponseOptionsEnum(
        missing=drop,
        default=ExecuteResponse.DOCUMENT,
        description=(
            "Indicates the desired representation format of the response. "
            f"(see for more details: {DOC_URL}/processes.html#execution-body)."
        ),
        validator=OneOf(ExecuteResponse.values())
    )
    notification_email = ExtendedSchemaNode(
        String(),
        missing=drop,
        validator=Email(),
        description="Optionally send a notification email when the job is done."
    )


class QuoteStatusSchema(ExtendedSchemaNode):
    schema_type = String
    validator = OneOf(QuoteStatus.values())


class PartialQuoteSchema(ExtendedMappingSchema):
    status = QuoteStatusSchema()
    quoteID = UUID(description="Quote ID.")
    processID = ProcessIdentifierTag(description="Process identifier corresponding to the quote definition.")


class PriceAmount(ExtendedSchemaNode):
    schema_type = Money()
    format = "decimal"  # https://github.com/OAI/OpenAPI-Specification/issues/845#issuecomment-378139730
    description = "Monetary value of the price."
    validator = Range(min=0)


class PriceCurrency(ExtendedSchemaNode):
    schema_type = String()
    description = "Currency code in ISO-4217 format."
    default = "USD"  # most common online
    validator = All(
        Length(min=3, max=3),
        OneOf(list_currencies()),
    )


class PriceSchema(ExtendedMappingSchema):
    amount = PriceAmount()
    currency = PriceCurrency()

    def __json__(self, value):
        """
        Handler for :mod:`pyramid` and :mod:`webob` if the object reaches the JSON serializer.

        Combined with :mod:`simplejson` to automatically handle :class:`Decimal` conversion.
        """
        return super().deserialize(value)


class QuoteProcessParameters(PermissiveMappingSchema, ExecuteInputOutputs):
    description = (
        "Parameters passed for traditional process execution (inputs, outputs) "
        "with added metadata for quote evaluation."
    )


class QuoteEstimateValue(PermissiveMappingSchema):
    description = "Details of an estimated value, with it attributed rate and resulting cost."
    estimate = PositiveNumber(default=0, missing=None)
    rate = PositiveNumber(default=0, missing=None)
    cost = PositiveNumber(default=0, missing=0.0)


class QuoteStepChainedInputLiteral(StrictMappingSchema, QuoteEstimatorWeightedParameterSchema):
    value = AnyLiteralType()


class QuoteStepChainedInputComplex(StrictMappingSchema, QuoteEstimatorWeightedParameterSchema):
    size = PositiveNumber()


class QuoteStepChainedInput(OneOfKeywordSchema):
    _one_of = [
        QuoteStepChainedInputLiteral(),
        QuoteStepChainedInputComplex(),
    ]


class QuoteStepOutputParameters(ExtendedMappingSchema):
    description = "Outputs from a quote estimation to be chained as inputs for a following Workflow step."
    output_id = QuoteStepChainedInput(
        variable="{output-id}",
        description="Mapping of output to chain as input for quote estimation.",
    )


class QuoteProcessResults(PermissiveMappingSchema):
    _schema = f"{WEAVER_SCHEMA_URL}/quotation/quote-estimation-result.yaml"
    description = (
        "Results of the quote estimation. "
        "Will be empty until completed. "
        "Contents may vary according to the estimation methodology. "
        "Each category provides details about its contribution toward the total."
    )
    flat = QuoteEstimateValue(missing=drop)
    memory = QuoteEstimateValue(missing=drop)
    storage = QuoteEstimateValue(missing=drop)
    duration = QuoteEstimateValue(missing=drop)
    cpu = QuoteEstimateValue(missing=drop)
    gpu = QuoteEstimateValue(missing=drop)
    total = PositiveNumber(default=0.0)


class UserIdSchema(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), missing=drop),
        ExtendedSchemaNode(Integer(), default=None),
    ]


class StepQuotation(PartialQuoteSchema):
    detail = ExtendedSchemaNode(String(), description="Detail about quote processing.", missing=None)
    price = PriceSchema(description="Estimated price for process execution.")
    expire = ExtendedSchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    userID = UserIdSchema(description="User ID that requested the quote.", missing=required, default=None)
    estimatedTime = Duration(missing=drop,
                             description="Estimated duration of process execution in human-readable format.")
    estimatedSeconds = ExtendedSchemaNode(Integer(), missing=drop,
                                          description="Estimated duration of process execution in seconds.")
    estimatedDuration = DurationISO(missing=drop,
                                    description="Estimated duration of process execution in ISO-8601 format.")
    processParameters = QuoteProcessParameters(title="QuoteProcessParameters")
    results = QuoteProcessResults(title="QuoteProcessResults", default={})
    outputs = QuoteStepOutputParameters(missing=drop)


class StepQuotationList(ExtendedSequenceSchema):
    description = "Detailed child processes and prices part of the complete quote."
    step = StepQuotation(description="Quote of a workflow step process.")


class Quotation(StepQuotation):
    paid = ExtendedSchemaNode(Boolean(), default=False, description=(
        "Indicates if the quote as been paid by the user. "
        "This is mandatory in order to execute the job corresponding to the produced quote."
    ))
    steps = StepQuotationList(missing=drop)


class QuoteStepReferenceList(ExtendedSequenceSchema):
    description = "Summary of child process quote references part of the complete quote."
    ref = ReferenceURL()


class QuoteSummary(PartialQuoteSchema):
    steps = QuoteStepReferenceList()
    total = PriceSchema(description="Total of the quote including step processes if applicable.")


class QuoteSchema(Quotation):
    total = PriceSchema(description="Total of the quote including step processes if applicable.")


class QuotationList(ExtendedSequenceSchema):
    quote = UUID(description="Quote ID.")


class QuotationListSchema(PagingBodySchema):
    _sort_first = QUOTES_LISTING_FIELD_FIRST
    _sort_after = QUOTES_LISTING_FIELD_AFTER

    quotations = QuotationList()


class CreatedQuotedJobStatusSchema(PartialQuoteSchema, CreatedJobStatusSchema):
    billID = UUID(description="ID of the created bill.")


class BillSchema(ExtendedMappingSchema):
    billID = UUID(description="Bill ID.")
    quoteID = UUID(description="Original quote ID that produced this bill.", missing=drop)
    processID = ProcessIdentifierTag()
    jobID = JobID()
    title = ExtendedSchemaNode(String(), description="Name of the bill.")
    description = ExtendedSchemaNode(String(), missing=drop)
    price = PriceSchema(description="Price associated to the bill.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the bill in ISO-8601 format.")
    userID = ExtendedSchemaNode(Integer(), description="User id that requested the quote.")


class BillList(ExtendedSequenceSchema):
    bill = UUID(description="Bill ID.")


class BillListSchema(ExtendedMappingSchema):
    bills = BillList()


class SupportedValues(ExtendedMappingSchema):
    pass


class DefaultValues(ExtendedMappingSchema):
    pass


class CWLClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "Class"
    schema_type = String
    example = "CommandLineTool"
    validator = OneOf(["CommandLineTool", "ExpressionTool", "Workflow"])
    description = (
        "CWL class specification. This is used to differentiate between single Application Package (AP)"
        "definitions and Workflow that chains multiple packages."
    )


class CWLExpression(ExtendedSchemaNode):
    schema_type = String
    title = "CWLExpression"
    description = (
        f"When combined with '{CWL_REQUIREMENT_INLINE_JAVASCRIPT}', "
        "this field allows runtime parameter references "
        f"(see also: {CWL_CMD_TOOL_URL}#Expression)."
    )


class RequirementClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "RequirementClass"
    schema_type = String
    description = "CWL requirement class specification."


class CUDAComputeCapability(ExtendedSchemaNode):
    schema_type = String
    example = "3.0"
    title = "CUDA compute capability"
    description = "The compute capability supported by the GPU hardware."
    validator = SemanticVersion(regex=r"^\d+\.\d+$")


class CUDAComputeCapabilityArray(ExtendedSequenceSchema):
    item = CUDAComputeCapability()
    validator = Length(min=1)


class CUDAComputeCapabilitySchema(OneOfKeywordSchema):
    # https://github.com/common-workflow-language/cwltool/blob/67a180/cwltool/extensions.yml#L178
    title = CUDAComputeCapability.title
    description = inspect.cleandoc("""
        The compute capability supported by the GPU hardware.

        * If this is a single value, it defines only the minimum
          compute capability.  GPUs with higher capability are also
          accepted.
        * If it is an array value, then only select GPUs with compute
          capabilities that explicitly appear in the array.

        See https://docs.nvidia.com/deploy/cuda-compatibility/#faq and
        https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#cuda-compute-capability for details.
    """)
    _one_of = [
        CUDAComputeCapability,
        CUDAComputeCapabilityArray,
    ]


class CUDARequirementSpecification(PermissiveMappingSchema):
    # https://github.com/common-workflow-language/cwltool/blob/67a180/cwltool/extensions.yml#L178
    cudaVersionMin = ExtendedSchemaNode(
        String(),
        example="11.4",
        title="CUDA version minimum",
        description=inspect.cleandoc("""
            The minimum CUDA version required to run the software. This corresponds to a CUDA SDK release.

            When run in a container, the container image should provide the CUDA runtime, and the host
            driver is injected into the container.  In this case, because CUDA drivers are backwards compatible,
            it is possible to use an older SDK with a newer driver across major versions.

            See https://docs.nvidia.com/deploy/cuda-compatibility/ for details.
        """),
        validator=SemanticVersion(regex=r"^\d+\.\d+$"),
    )
    cudaComputeCapability = CUDAComputeCapabilitySchema()
    cudaDeviceCountMin = ExtendedSchemaNode(
        Integer(),
        example=1,
        default=1,
        validator=Range(min=1),
        title="CUDA device count minimum",
        description="The minimum amount of devices required.",
    )
    cudaDeviceCountMax = ExtendedSchemaNode(
        Integer(),
        example=8,
        default=1,
        validator=Range(min=1),
        title="CUDA device count maximum",
        description="The maximum amount of devices required.",
    )


class CUDARequirementMap(ExtendedMappingSchema):
    CUDARequirement = CUDARequirementSpecification(
        name=CWL_REQUIREMENT_CUDA,
        title=CWL_REQUIREMENT_CUDA,
    )


class CUDARequirementClass(CUDARequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_CUDA, validator=OneOf([CWL_REQUIREMENT_CUDA]))


class NetworkAccessRequirementSpecification(PermissiveMappingSchema):
    networkAccess = ExtendedSchemaNode(
        Boolean(),
        example=True,
        title="Network Access",
        description="Indicate whether a process requires outgoing IPv4/IPv6 network access.",
    )


class NetworkAccessRequirementMap(ExtendedMappingSchema):
    NetworkAccessRequirement = NetworkAccessRequirementSpecification(
        name=CWL_REQUIREMENT_NETWORK_ACCESS,
        title=CWL_REQUIREMENT_NETWORK_ACCESS,
    )


class NetworkAccessRequirementClass(NetworkAccessRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_NETWORK_ACCESS, validator=OneOf([CWL_REQUIREMENT_NETWORK_ACCESS]))


class ResourceRequirementValue(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float(), validator=BoundedRange(min=0.0, exclusive_min=True)),
        ExtendedSchemaNode(Integer(), validator=Range(min=1)),
        CWLExpression,
    ]


class ResourceRequirementSpecification(PermissiveMappingSchema):
    description = inspect.cleandoc(f"""
        Specify basic hardware resource requirements
        (see also: {CWL_CMD_TOOL_URL}#{CWL_REQUIREMENT_RESOURCE}).
    """)
    coresMin = ResourceRequirementValue(
        missing=drop,
        default=1,
        title="ResourceCoresMinimum",
        summary="Minimum reserved number of CPU cores.",
        description=inspect.cleandoc("""
            Minimum reserved number of CPU cores.

            May be a fractional value to indicate to a scheduling algorithm that one core can be allocated
            to multiple jobs. For example, a value of 0.25 indicates that up to 4 jobs may run in parallel
            on 1 core. A value of 1.25 means that up to 3 jobs can run on a 4 core system (4/1.25 ≈ 3).

            Processes can only share a core allocation if the sum of each of their 'ramMax', 'tmpdirMax',
            and 'outdirMax' requests also do not exceed the capacity of the node.

            Processes sharing a core must have the same level of isolation (typically a container or VM)
            that they would normally have.

            The reported number of CPU cores reserved for the process, which is available to expressions on the
            'CommandLineTool' as 'runtime.cores', must be a non-zero integer, and may be calculated by rounding up
            the cores request to the next whole number.

            Scheduling systems may allocate fractional CPU resources by setting quotas or scheduling weights.
            Scheduling systems that do not support fractional CPUs may round up the request to the next whole number.
        """),
    )
    coresMax = ResourceRequirementValue(
        missing=drop,
        title="ResourceCoresMaximum",
        summary="Maximum reserved number of CPU cores.",
        description=inspect.cleandoc("""
            Maximum reserved number of CPU cores.
            See 'coresMin' for discussion about fractional CPU requests.
        """),
    )
    ramMin = ResourceRequirementValue(
        missing=drop,
        default=256,
        title="ResourceRAMMinimum",
        summary="Minimum reserved RAM in mebibytes.",
        description=inspect.cleandoc("""
            Minimum reserved RAM in mebibytes (2**20).

            May be a fractional value. If so, the actual RAM request must be rounded up to the next whole number.
            The reported amount of RAM reserved for the process, which is available to expressions on the
            'CommandLineTool' as 'runtime.ram', must be a non-zero integer.
        """),
    )
    ramMax = ResourceRequirementValue(
        missing=drop,
        title="ResourceRAMMaximum",
        summary="Maximum reserved RAM in mebibytes.",
        description=inspect.cleandoc("""
            Maximum reserved RAM in mebibytes (2**20).
            See 'ramMin' for discussion about fractional RAM requests.
        """),
    )
    tmpdirMin = ResourceRequirementValue(
        missing=drop,
        default=1024,
        title="ResourceTmpDirMinimum",
        summary="Minimum reserved filesystem based storage for the designated temporary directory in mebibytes.",
        description=inspect.cleandoc("""
            Minimum reserved filesystem based storage for the designated temporary directory in mebibytes (2**20).

            May be a fractional value. If so, the actual storage request must be rounded up to the next whole number.
            The reported amount of storage reserved for the process, which is available to expressions on the
            'CommandLineTool' as 'runtime.tmpdirSize', must be a non-zero integer.
        """),
    )
    tmpdirMax = ResourceRequirementValue(
        missing=drop,
        title="ResourceTmpDirMaximum",
        summary="Maximum reserved filesystem based storage for the designated temporary directory in mebibytes.",
        description=inspect.cleandoc("""
            Maximum reserved filesystem based storage for the designated temporary directory in mebibytes (2**20).
            See 'tmpdirMin' for discussion about fractional storage requests.
        """),
    )
    outdirMin = ResourceRequirementValue(
        missing=drop,
        default=1024,
        title="ResourceOutDirMinimum",
        summary="Minimum reserved filesystem based storage for the designated output directory in mebibytes.",
        description=inspect.cleandoc("""
            Minimum reserved filesystem based storage for the designated output directory in mebibytes (2**20).

            May be a fractional value. If so, the actual storage request must be rounded up to the next whole number.
            The reported amount of storage reserved for the process, which is available to expressions on the
            'CommandLineTool' as runtime.outdirSize, must be a non-zero integer.
        """),
    )
    outdirMax = ResourceRequirementValue(
        missing=drop,
        default=1,
        title="ResourceOutDirMaximum",
        summary="Maximum reserved filesystem based storage for the designated output directory in mebibytes.",
        description=inspect.cleandoc("""
            Maximum reserved filesystem based storage for the designated output directory in mebibytes (2**20).
            See 'outdirMin' for discussion about fractional storage requests.
        """),
    )


class ResourceRequirementMap(ExtendedMappingSchema):
    ResourceRequirement = ResourceRequirementSpecification(
        name=CWL_REQUIREMENT_RESOURCE,
        title=CWL_REQUIREMENT_RESOURCE,
    )


class ResourceRequirementClass(ResourceRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_RESOURCE, validator=OneOf([CWL_REQUIREMENT_RESOURCE]))


class DockerRequirementSpecification(PermissiveMappingSchema):
    dockerPull = ExtendedSchemaNode(
        String(),
        example="docker-registry.host.com/namespace/image:1.2.3",
        title="Docker pull reference",
        description="Reference package that will be retrieved and executed by CWL."
    )


class DockerRequirementMap(ExtendedMappingSchema):
    DockerRequirement = DockerRequirementSpecification(
        name=CWL_REQUIREMENT_APP_DOCKER,
        title=CWL_REQUIREMENT_APP_DOCKER
    )


class DockerRequirementClass(DockerRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER]))


class DockerGpuRequirementSpecification(DockerRequirementSpecification):
    deprecated = True
    description = inspect.cleandoc(f"""
        Docker requirement with GPU-enabled support (https://github.com/NVIDIA/nvidia-docker).
        The instance must have the NVIDIA toolkit installed to use this feature.

        WARNING:
        This requirement is specific to Weaver and is preserved only for backward compatibility.
        Prefer the combined use of official '{CWL_REQUIREMENT_APP_DOCKER}' and '{CWL_REQUIREMENT_CUDA}'
        for better support of GPU capabilities and portability to other CWL-supported platforms.
    """)


class DockerGpuRequirementMap(ExtendedMappingSchema):
    deprecated = True
    req = DockerGpuRequirementSpecification(name=CWL_REQUIREMENT_APP_DOCKER_GPU)


class DockerGpuRequirementClass(DockerGpuRequirementSpecification):
    deprecated = True
    title = CWL_REQUIREMENT_APP_DOCKER_GPU
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER_GPU, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER_GPU]))


class DirectoryListingItem(PermissiveMappingSchema):
    entry = ExtendedSchemaNode(String(), missing=drop)
    entryname = ExtendedSchemaNode(String(), missing=drop)
    writable = ExtendedSchemaNode(Boolean(), missing=drop)


class InitialWorkDirListing(ExtendedSequenceSchema):
    item = DirectoryListingItem()


class InitialWorkDirRequirementSpecification(PermissiveMappingSchema):
    listing = InitialWorkDirListing()


class InitialWorkDirRequirementMap(ExtendedMappingSchema):
    req = InitialWorkDirRequirementSpecification(name=CWL_REQUIREMENT_INIT_WORKDIR)


class InitialWorkDirRequirementClass(InitialWorkDirRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_INIT_WORKDIR,
                              validator=OneOf([CWL_REQUIREMENT_INIT_WORKDIR]))


class InlineJavascriptLibraries(ExtendedSequenceSchema):
    description = inspect.cleandoc("""
        Additional code fragments that will also be inserted before executing the expression code.
        Allows for function definitions that may be called from CWL expressions.
    """)
    exp_lib = ExtendedSchemaNode(String(), missing=drop)


class InlineJavascriptRequirementSpecification(PermissiveMappingSchema):
    description = inspect.cleandoc(f"""
        Indicates that the workflow platform must support inline Javascript expressions.
        If this requirement is not present, the workflow platform must not perform expression interpolation
        (see also: {CWL_CMD_TOOL_URL}#{CWL_REQUIREMENT_INLINE_JAVASCRIPT}).
    """)
    expressionLib = InlineJavascriptLibraries(missing=drop)


class InlineJavascriptRequirementMap(ExtendedMappingSchema):
    req = InlineJavascriptRequirementSpecification(name=CWL_REQUIREMENT_INLINE_JAVASCRIPT)


class InlineJavascriptRequirementClass(InlineJavascriptRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_INLINE_JAVASCRIPT,
                              validator=OneOf([CWL_REQUIREMENT_INLINE_JAVASCRIPT]))


class InplaceUpdateRequirementSpecification(PermissiveMappingSchema):
    description = inspect.cleandoc(f"""
        If 'inplaceUpdate' is true, then an implementation supporting this feature may permit tools to directly
        update files with 'writable: true' in '{CWL_REQUIREMENT_INIT_WORKDIR}'. That is, as an optimization,
        files may be destructively modified in place as opposed to copied and updated
        (see also: {CWL_CMD_TOOL_URL}#{CWL_REQUIREMENT_INPLACE_UPDATE}).
    """)
    inplaceUpdate = ExtendedSchemaNode(Boolean())


class InplaceUpdateRequirementMap(ExtendedMappingSchema):
    req = InplaceUpdateRequirementSpecification(name=CWL_REQUIREMENT_INPLACE_UPDATE)


class InplaceUpdateRequirementClass(InplaceUpdateRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_INPLACE_UPDATE,
                              validator=OneOf([CWL_REQUIREMENT_INPLACE_UPDATE]))


class LoadListingEnum(ExtendedSchemaNode):
    schema_type = String
    title = "LoadListingEnum"
    validator = OneOf(["no_listing", "shallow_listing", "deep_listing"])


class LoadListingRequirementSpecification(PermissiveMappingSchema):
    description = (
        "Specify the desired behavior for loading the listing field of a 'Directory' object for use by expressions "
        f"(see also: {CWL_CMD_TOOL_URL}#{CWL_REQUIREMENT_LOAD_LISTING})."
    )
    loadListing = LoadListingEnum()


class LoadListingRequirementMap(ExtendedMappingSchema):
    req = LoadListingRequirementSpecification(name=CWL_REQUIREMENT_LOAD_LISTING)


class LoadListingRequirementClass(LoadListingRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_LOAD_LISTING,
                              validator=OneOf([CWL_REQUIREMENT_LOAD_LISTING]))


class IdentifierArray(ExtendedSequenceSchema):
    item = AnyIdentifier()


class ScatterIdentifiersSchema(OneOfKeywordSchema):
    title = "Scatter"
    description = inspect.cleandoc("""
        The scatter field specifies one or more input parameters which will be scattered.
        An input parameter may be listed more than once. The declared type of each input parameter implicitly
        becomes an array of items of the input parameter type. If a parameter is listed more than once, it
        becomes a nested array. As a result, upstream parameters which are connected to scattered parameters
        must be arrays.

        All output parameter types are also implicitly wrapped in arrays. Each job in the scatter results in an
        entry in the output array.

        If any scattered parameter runtime value is an empty array, all outputs are set to empty arrays and
        no work is done for the step, according to applicable scattering rules.
    """)
    _one_of = [
        AnyIdentifier(),
        IdentifierArray(validator=Length(min=1)),
    ]


class ScatterFeatureRequirementSpecification(PermissiveMappingSchema):
    description = inspect.cleandoc(f"""
        A 'scatter' operation specifies that the associated Workflow step should execute separately over a list of
        input elements. Each job making up a scatter operation is independent and may be executed concurrently
        (see also: {CWL_WORKFLOW_URL}#WorkflowStep).
    """)
    scatter = ScatterIdentifiersSchema()
    scatterMethod = ExtendedSchemaNode(
        String(),
        validator=OneOf(["dotproduct", "nested_crossproduct", "flat_crossproduct"]),
        default="dotproduct",
        missing=drop,
        description=inspect.cleandoc("""
            If 'scatter' declares more than one input parameter, 'scatterMethod' describes how to decompose the
            input into a discrete set of jobs.

            - dotproduct: specifies that each of the input arrays are aligned and one element taken from each array
              to construct each job. It is an error if all input arrays are not the same length.

            - nested_crossproduct: specifies the Cartesian product of the inputs, producing a job for every
              combination of the scattered inputs. The output must be nested arrays for each level of scattering,
              in the order that the input arrays are listed in the 'scatter' field.

            - flat_crossproduct: specifies the Cartesian product of the inputs, producing a job for every combination
              of the scattered inputs. The output arrays must be flattened to a single level, but otherwise listed in
              the order that the input arrays are listed in the 'scatter' field.
        """)
    )


class ScatterFeatureRequirementMap(ExtendedMappingSchema):
    req = ScatterFeatureRequirementSpecification(name=CWL_REQUIREMENT_SCATTER)


class ScatterFeatureRequirementClass(ScatterFeatureRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_SCATTER, validator=OneOf([CWL_REQUIREMENT_SCATTER]))


class TimeLimitValue(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float(), validator=Range(min=0.0)),
        ExtendedSchemaNode(Integer(), validator=Range(min=0)),
        CWLExpression,
    ]


class ToolTimeLimitRequirementSpecification(PermissiveMappingSchema):
    description = inspect.cleandoc("""
        Set an upper limit on the execution time of a CommandLineTool.
        A CommandLineTool whose execution duration exceeds the time limit may be preemptively terminated
        and considered failed. May also be used by batch systems to make scheduling decisions.
        The execution duration excludes external operations, such as staging of files, pulling a docker image etc.,
        and only counts wall-time for the execution of the command line itself.
    """)
    timelimit = TimeLimitValue(
        description=inspect.cleandoc("""
            The time limit, in seconds.
            A time limit of zero means no time limit.
            Negative time limits are an error.
        """)
    )


class ToolTimeLimitRequirementMap(ExtendedMappingSchema):
    req = ToolTimeLimitRequirementSpecification(name=CWL_REQUIREMENT_TIME_LIMIT)


class ToolTimeLimitRequirementClass(ToolTimeLimitRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_TIME_LIMIT, validator=OneOf([CWL_REQUIREMENT_TIME_LIMIT]))


class EnableReuseValue(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Boolean(allow_string=False)),
        CWLExpression,
    ]


class WorkReuseRequirementSpecification(PermissiveMappingSchema):
    description = inspect.cleandoc(f"""
        For implementations that support reusing output from past work
        (on the assumption that same code and same input produce same results),
        control whether to enable or disable the reuse behavior for a particular tool or step
        (to accommodate situations where that assumption is incorrect).
        A reused step is not executed but instead returns the same output as the original execution.

        If '{CWL_REQUIREMENT_WORK_REUSE}' is not specified, correct tools should assume it is enabled by default.
    """)
    enableReuse = EnableReuseValue(
        description=inspect.cleandoc(f"""
            Indicates if reuse is enabled for this tool.
            Can be an expression when combined with '{CWL_REQUIREMENT_INLINE_JAVASCRIPT}'
            (see also: {CWL_CMD_TOOL_URL}#Expression).
        """)
    )


class WorkReuseRequirementMap(ExtendedMappingSchema):
    req = WorkReuseRequirementSpecification(name=CWL_REQUIREMENT_WORK_REUSE)


class WorkReuseRequirementClass(WorkReuseRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_WORK_REUSE, validator=OneOf([CWL_REQUIREMENT_WORK_REUSE]))


class BuiltinRequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_BUILTIN
    description = (
        "Hint indicating that the Application Package corresponds to a builtin process of "
        "this instance. (note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Builtin process identifier.")


class BuiltinRequirementMap(ExtendedMappingSchema):
    req = BuiltinRequirementSpecification(name=CWL_REQUIREMENT_APP_BUILTIN)


class BuiltinRequirementClass(BuiltinRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_BUILTIN, validator=OneOf([CWL_REQUIREMENT_APP_BUILTIN]))


class ESGF_CWT_RequirementSpecification(PermissiveMappingSchema):  # noqa: N802
    title = CWL_REQUIREMENT_APP_ESGF_CWT
    description = (
        "Hint indicating that the Application Package corresponds to an ESGF-CWT provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote ESGF-CWT provider.")
    provider = URL(description="ESGF-CWT provider endpoint.")


class ESGF_CWT_RequirementMap(ExtendedMappingSchema):  # noqa: N802
    req = ESGF_CWT_RequirementSpecification(name=CWL_REQUIREMENT_APP_ESGF_CWT)


class ESGF_CWT_RequirementClass(ESGF_CWT_RequirementSpecification):  # noqa: N802
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_ESGF_CWT, validator=OneOf([CWL_REQUIREMENT_APP_ESGF_CWT]))


class OGCAPIRequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_OGC_API
    description = (
        "Hint indicating that the Application Package corresponds to an OGC API - Processes provider"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = ReferenceURL(description="Process URL of the remote OGC API Process.")


class OGCAPIRequirementMap(ExtendedMappingSchema):
    req = OGCAPIRequirementSpecification(name=CWL_REQUIREMENT_APP_OGC_API)


class OGCAPIRequirementClass(OGCAPIRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_OGC_API, validator=OneOf([CWL_REQUIREMENT_APP_OGC_API]))


class WPS1RequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_WPS1
    description = (
        "Hint indicating that the Application Package corresponds to a WPS-1 provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote WPS provider.")
    provider = URL(description="WPS provider endpoint.")


class WPS1RequirementMap(ExtendedMappingSchema):
    req = WPS1RequirementSpecification(name=CWL_REQUIREMENT_APP_WPS1)


class WPS1RequirementClass(WPS1RequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_WPS1, validator=OneOf([CWL_REQUIREMENT_APP_WPS1]))


class UnknownRequirementMap(PermissiveMappingSchema):
    description = "Generic schema to allow alternative CWL requirements/hints not explicitly defined in schemas."


class UnknownRequirementClass(PermissiveMappingSchema):
    _class = RequirementClass(example="UnknownRequirement")


class CWLRequirementsMap(AnyOfKeywordSchema):
    _any_of = [
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        InlineJavascriptRequirementMap(missing=drop),
        InplaceUpdateRequirementMap(missing=drop),
        LoadListingRequirementMap(missing=drop),
        NetworkAccessRequirementMap(missing=drop),
        ResourceRequirementMap(missing=drop),
        ScatterFeatureRequirementMap(missing=drop),
        ToolTimeLimitRequirementMap(missing=drop),
        WorkReuseRequirementMap(missing=drop),
        UnknownRequirementMap(missing=drop),  # allows anything, must be last
    ]


class CWLRequirementsItem(OneOfKeywordSchema):
    # in case there is any conflict between definitions,
    # the class field can be used to discriminate which one is expected.
    discriminator = "class"
    _one_of = [
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        InlineJavascriptRequirementClass(missing=drop),
        InplaceUpdateRequirementClass(missing=drop),
        LoadListingRequirementClass(missing=drop),
        NetworkAccessRequirementClass(missing=drop),
        ResourceRequirementClass(missing=drop),
        ScatterFeatureRequirementClass(missing=drop),
        ToolTimeLimitRequirementClass(missing=drop),
        WorkReuseRequirementClass(missing=drop),
        UnknownRequirementClass(missing=drop),  # allows anything, must be last
    ]


class CWLRequirementsList(ExtendedSequenceSchema):
    requirement = CWLRequirementsItem()


class CWLRequirements(OneOfKeywordSchema):
    _one_of = [
        CWLRequirementsMap(),
        CWLRequirementsList(),
    ]


class CWLHintsMap(AnyOfKeywordSchema, PermissiveMappingSchema):
    _any_of = [
        BuiltinRequirementMap(missing=drop),
        CUDARequirementMap(missing=drop),
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        InlineJavascriptRequirementMap(missing=drop),
        InplaceUpdateRequirementMap(missing=drop),
        LoadListingRequirementMap(missing=drop),
        NetworkAccessRequirementMap(missing=drop),
        ResourceRequirementMap(missing=drop),
        ScatterFeatureRequirementMap(missing=drop),
        ToolTimeLimitRequirementMap(missing=drop),
        WorkReuseRequirementMap(missing=drop),
        ESGF_CWT_RequirementMap(missing=drop),
        OGCAPIRequirementMap(missing=drop),
        WPS1RequirementMap(missing=drop),
        UnknownRequirementMap(missing=drop),  # allows anything, must be last
    ]


class CWLHintsItem(OneOfKeywordSchema, PermissiveMappingSchema):
    # validators of individual requirements define which one applies
    # in case of ambiguity, 'discriminator' distinguish between them using their 'example' values in 'class' field
    discriminator = "class"
    _one_of = [
        BuiltinRequirementClass(missing=drop),
        CUDARequirementClass(missing=drop),
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        InlineJavascriptRequirementClass(missing=drop),
        InplaceUpdateRequirementClass(missing=drop),
        LoadListingRequirementClass(missing=drop),
        NetworkAccessRequirementClass(missing=drop),
        ResourceRequirementClass(missing=drop),
        ScatterFeatureRequirementClass(missing=drop),
        ToolTimeLimitRequirementClass(missing=drop),
        WorkReuseRequirementClass(missing=drop),
        ESGF_CWT_RequirementClass(missing=drop),
        OGCAPIRequirementClass(missing=drop),
        WPS1RequirementClass(missing=drop),
        UnknownRequirementClass(missing=drop),  # allows anything, must be last
    ]


class CWLHintsList(ExtendedSequenceSchema):
    hint = CWLHintsItem()


class CWLHints(OneOfKeywordSchema):
    _one_of = [
        CWLHintsMap(),
        CWLHintsList(),
    ]


class CWLArguments(ExtendedSequenceSchema):
    argument = ExtendedSchemaNode(String())


class CWLTypeString(ExtendedSchemaNode):
    schema_type = String
    description = "Field type definition."
    example = "float"
    validator = OneOf(PACKAGE_TYPE_POSSIBLE_VALUES)


class CWLTypeSymbolValues(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String()),
    ]


class CWLTypeSymbols(ExtendedSequenceSchema):
    symbol = CWLTypeSymbolValues()


class CWLTypeArray(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), example=PACKAGE_ARRAY_BASE, validator=OneOf([PACKAGE_ARRAY_BASE]))
    items = CWLTypeString(title="CWLTypeArrayItems", validator=OneOf(PACKAGE_ARRAY_ITEMS))


class CWLTypeEnum(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), example=PACKAGE_ENUM_BASE, validator=OneOf(PACKAGE_CUSTOM_TYPES))
    symbols = CWLTypeSymbols(summary="Allowed values composing the enum.")


class CWLTypeBase(OneOfKeywordSchema):
    _one_of = [
        CWLTypeString(summary="CWL type as literal value."),
        CWLTypeArray(summary="CWL type as list of items."),
        CWLTypeEnum(summary="CWL type as enum of values."),
    ]


class CWLTypeList(ExtendedSequenceSchema):
    type = CWLTypeBase()


class CWLType(OneOfKeywordSchema):
    title = "CWL Type"
    _one_of = [
        CWLTypeBase(summary="CWL type definition."),
        CWLTypeList(summary="Combination of allowed CWL types."),
    ]


class AnyLiteralList(ExtendedSequenceSchema):
    default = AnyLiteralType()


class CWLDefault(OneOfKeywordSchema):
    _one_of = [
        AnyLiteralType(),
        AnyLiteralList(),
    ]


class CWLInputObject(PermissiveMappingSchema):
    type = CWLType()
    default = CWLDefault(missing=drop, description="Default value of input if not provided for task execution.")
    inputBinding = PermissiveMappingSchema(missing=drop, title="Input Binding",
                                           description="Defines how to specify the input for the command.")


class CWLTypeStringList(ExtendedSequenceSchema):
    description = "List of allowed direct CWL type specifications as strings."
    type = CWLType()


class CWLInputType(OneOfKeywordSchema):
    description = "CWL type definition of the input."
    _one_of = [
        CWLTypeString(summary="Direct CWL type string specification."),
        CWLTypeStringList(summary="List of allowed CWL type strings."),
        CWLInputObject(summary="CWL type definition with parameters."),
    ]


class CWLInputMap(PermissiveMappingSchema):
    input_id = CWLInputType(variable="{input-id}", title="CWLInputDefinition",
                            description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input") +
                            " (Note: '{input-id}' is a variable corresponding for each identifier)")


class CWLInputItem(CWLInputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input"))


class CWLInputList(ExtendedSequenceSchema):
    input = CWLInputItem(title="Input", description=f"Input specification. {CWL_DOC_MESSAGE}")


class CWLInputEmpty(EmptyMappingSchema):
    pass


class CWLInputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLInputList(description="Package inputs defined as items."),
        CWLInputMap(description="Package inputs defined as mapping."),
        CWLInputEmpty(description="Package inputs as empty mapping when it takes no arguments."),
    ]


class OutputBinding(PermissiveMappingSchema):
    glob = ExtendedSchemaNode(String(), missing=drop,
                              description="Glob pattern to find the output on disk or mounted docker volume.")


class CWLOutputObject(PermissiveMappingSchema):
    type = CWLType()
    # 'outputBinding' should usually be there most of the time (if not always) to retrieve file,
    # but can technically be omitted in some very specific use-cases such as output literal or output is std logs
    outputBinding = OutputBinding(
        missing=drop,
        description="Defines how to retrieve the output result from the command."
    )


class CWLOutputType(OneOfKeywordSchema):
    _one_of = [
        CWLTypeString(summary="Direct CWL type string specification."),
        CWLTypeStringList(summary="List of allowed CWL type strings."),
        CWLOutputObject(summary="CWL type definition with parameters."),
    ]


class CWLOutputMap(ExtendedMappingSchema):
    output_id = CWLOutputType(variable="{output-id}", title="CWLOutputDefinition",
                              description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output") +
                              " (Note: '{output-id}' is a variable corresponding for each identifier)")


class CWLOutputItem(CWLOutputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output"))


class CWLOutputList(ExtendedSequenceSchema):
    input = CWLOutputItem(description=f"Output specification. {CWL_DOC_MESSAGE}")


class CWLOutputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLOutputList(description="Package outputs defined as items."),
        CWLOutputMap(description="Package outputs defined as mapping."),
    ]


class CWLCommandParts(ExtendedSequenceSchema):
    cmd = ExtendedSchemaNode(String())


class CWLCommand(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), title="String command."),
        CWLCommandParts(title="Command Parts")
    ]


class CWLVersion(Version):
    description = "CWL version of the described application package."
    example = CWL_VERSION
    validator = SemanticVersion(v_prefix=True, rc_suffix=False)


class CWLIdentifier(ProcessIdentifier):
    description = (
        "Reference to the process identifier. If CWL is provided within a process deployment payload, this can be "
        "omitted. If used in a deployment with only CWL details, this information is required."
    )


class CWLIntentURL(URL):
    description = (
        "Identifier URL to a concept for the type of computational operation accomplished by this Process "
        "(see example operations: http://edamontology.org/operation_0004)."
    )


class CWLIntent(ExtendedSequenceSchema):
    item = CWLIntentURL()


class CWLBase(ExtendedMappingSchema):
    cwlVersion = CWLVersion()


class CWLScatterMulti(ExtendedSequenceSchema):
    id = CWLIdentifier("")


class CWLScatter(OneOfKeywordSchema):
    _one_of = [
        CWLIdentifier(),
        CWLScatterMulti()
    ]


class CWLScatterMethod(ExtendedSchemaNode):
    schema_type = String
    description = (
        "Describes how to decompose the scattered input into a discrete set of jobs. "
        "When 'dotproduct', specifies that each of the input arrays are aligned and one element taken from each array"
        "to construct each job. It is an error if all input arrays are of different length. "
        "When 'nested_crossproduct', specifies the Cartesian product of the inputs, producing a job for every "
        "combination of the scattered inputs. The output must be nested arrays for each level of scattering, "
        "in the order that the input arrays are listed in the scatter field. "
        "When 'flat_crossproduct', specifies the Cartesian product of the inputs, producing a job for every "
        "combination of the scattered inputs. The output arrays must be flattened to a single level, but otherwise "
        "listed in the order that the input arrays are listed in the scatter field."
    )
    validator = OneOf(["dotproduct", "nested_crossproduct", "flat_crossproduct"])


class CWLApp(PermissiveMappingSchema):
    _class = CWLClass()
    id = CWLIdentifier(missing=drop)  # can be omitted only if within a process deployment that also includes it
    intent = CWLIntent(missing=drop)
    requirements = CWLRequirements(description="Explicit requirement to execute the application package.", missing=drop)
    hints = CWLHints(description="Non-failing additional hints that can help resolve extra requirements.", missing=drop)
    baseCommand = CWLCommand(description="Command called in the docker image or on shell according to requirements "
                                         "and hints specifications. Can be omitted if already defined in the "
                                         "docker image.", missing=drop)
    arguments = CWLArguments(description="Base arguments passed to the command.", missing=drop)
    inputs = CWLInputsDefinition(description="All inputs available to the Application Package.")
    outputs = CWLOutputsDefinition(description="All outputs produced by the Application Package.")
    scatter = CWLScatter(missing=drop, description=(
        "One or more input identifier of an application step within a Workflow were an array-based input to that "
        "Workflow should be scattered across multiple instances of the step application."
    ))
    scatterMethod = CWLScatterMethod(missing=drop)


class CWL(CWLBase, CWLApp):
    _sort_first = ["cwlVersion", "id", "class"]


class Unit(ExtendedMappingSchema):
    unit = CWL(description=f"Execution unit definition as CWL package specification. {CWL_DOC_MESSAGE}")


class UndeploymentResult(ExtendedMappingSchema):
    id = AnyIdentifier()


class DeploymentResult(ExtendedMappingSchema):
    processSummary = ProcessSummary()


class ProviderSummaryList(ExtendedSequenceSchema):
    provider_service = ProviderSummarySchema()


class ProviderNamesList(ExtendedSequenceSchema):
    provider_name = ProviderNameSchema()


class ProviderListing(OneOfKeywordSchema):
    _one_of = [
        ProviderSummaryList(description="Listing of provider summary details retrieved from remote service."),
        ProviderNamesList(description="Listing of provider names, possibly unvalidated from remote service.",
                          missing=drop),  # in case of empty list, both schema are valid, drop this one to resolve
    ]


class ProvidersBodySchema(ExtendedMappingSchema):
    checked = ExtendedSchemaNode(
        Boolean(),
        description="Indicates if the listed providers have been validated and are accessible from registered URL. "
                    "In such case, provider metadata was partially retrieved from remote services and is accessible. "
                    "Otherwise, only local metadata is provided and service availability is not guaranteed."
    )
    providers = ProviderListing(description="Providers listing according to specified query parameters.")


class ProviderProcessesSchema(ExtendedSequenceSchema):
    provider_process = ProcessSummary()


class JobOutputReference(ExtendedMappingSchema):
    href = ReferenceURL(description="Output file reference.")
    # either with 'type', 'format.mediaType' or 'format.mimeType' according requested 'schema=OGC/OLD'
    # if 'schema=strict' as well, either 'type' or 'format' could be dropped altogether
    type = MediaType(missing=drop, description="IANA Content-Type of the file reference.")
    format = FormatSelection(missing=drop)


class JobOutputValue(OneOfKeywordSchema):
    _one_of = [
        JobOutputReference(tilte="JobOutputReference"),
        AnyLiteralDataType(title="JobOutputLiteral")
    ]


class JobOutput(AllOfKeywordSchema):
    _all_of = [
        OutputIdentifierType(),
        JobOutputValue(),
    ]


class JobOutputMap(ExtendedMappingSchema):
    output_id = JobOutputValue(
        variable="{output-id}", title="JobOutputData",
        description=(
            "Output data as literal value or file reference. "
            "(Note: '{output-id}' is a variable corresponding for each identifier)"
        )
    )


class JobOutputList(ExtendedSequenceSchema):
    title = "JobOutputList"
    output = JobOutput(description="Job output result with specific keyword according to represented format.")


class JobOutputs(OneOfKeywordSchema):
    _one_of = [
        JobOutputMap(),
        JobOutputList(),
    ]


# implement only literal parts from following schemas:
# https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/inlineOrRefData.yaml
# https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/qualifiedInputValue.yaml
#
# Other parts are implemented separately with:
#   - 'ValueFormatted' (qualifiedInputValue)
#   - 'ResultReference' (link)
class ResultLiteral(AnyLiteralValueType):
    # value = <AnyLiteralValueType>
    pass


class ResultLiteralList(ExtendedSequenceSchema):
    result = ResultLiteral()


class ValueFormatted(ExtendedMappingSchema):
    value = ExtendedSchemaNode(
        String(),
        example="<xml><data>test</data></xml>",
        description="Formatted content value of the result."
    )
    format = ResultFormat()


class ValueFormattedList(ExtendedSequenceSchema):
    result = ValueFormatted()


class ResultReference(ExtendedMappingSchema):
    href = ReferenceURL(description="Result file reference.")
    type = MediaType(description="IANA Content-Type of the file reference.")
    format = ResultFormat()


class ResultReferenceList(ExtendedSequenceSchema):
    result = ResultReference()


class ResultData(OneOfKeywordSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/result.yaml"
    _one_of = [
        # must place formatted value first since both value/format fields are simultaneously required
        # other classes require only one of the two, and therefore are more permissive during schema validation
        ValueFormatted(description="Result formatted content value."),
        ValueFormattedList(description="Result formatted content of multiple values."),
        ResultReference(description="Result reference location."),
        ResultReferenceList(description="Result locations for multiple references."),
        ResultLiteral(description="Result literal value."),
        ResultLiteralList(description="Result list of literal values."),
    ]


class Result(ExtendedMappingSchema):
    """
    Result outputs obtained from a successful process job execution.
    """
    example_ref = f"{OGC_API_PROC_PART1_SCHEMAS}/result.yaml"
    output_id = ResultData(
        variable="{output-id}", title="ResultData",
        description=(
            "Resulting value of the output that conforms to 'OGC API - Processes' standard. "
            "(Note: '{output-id}' is a variable corresponding for each output identifier of the process)"
        )
    )


class JobInputsBody(ExecuteInputOutputs):
    links = LinkList(missing=drop)


class JobOutputsBody(ExtendedMappingSchema):
    outputs = JobOutputs()
    links = LinkList(missing=drop)


class JobExceptionPlain(ExtendedSchemaNode):
    schema_type = String
    description = "Generic exception description corresponding to any error message."


class JobExceptionDetailed(ExtendedMappingSchema):
    description = "Fields correspond exactly to 'owslib.wps.WPSException' represented as dictionary."
    Code = ExtendedSchemaNode(String())
    Locator = ExtendedSchemaNode(String(), default=None)
    Text = ExtendedSchemaNode(String())


class JobException(OneOfKeywordSchema):
    _one_of = [
        JobExceptionDetailed(),
        JobExceptionPlain()
    ]


class JobExceptionsSchema(ExtendedSequenceSchema):
    exceptions = JobException()


class JobLogsSchema(ExtendedSequenceSchema):
    log = ExtendedSchemaNode(String())


class ApplicationStatisticsSchema(ExtendedMappingSchema):
    mem = ExtendedSchemaNode(String(), name="usedMemory", example="10 MiB")
    mem_bytes = ExtendedSchemaNode(Integer(), name="usedMemoryBytes", example=10485760)


class ProcessStatisticsSchema(ExtendedMappingSchema):
    rss = ExtendedSchemaNode(String(), name="rss", example="140 MiB")
    rss_bytes = ExtendedSchemaNode(Integer(), name="rssBytes", example=146800640)
    uss = ExtendedSchemaNode(String(), name="uss", example="80 MiB")
    uss_bytes = ExtendedSchemaNode(Integer(), name="ussBytes", example=83886080)
    vms = ExtendedSchemaNode(String(), name="vms", example="1.4 GiB")
    vms_bytes = ExtendedSchemaNode(Integer(), name="vmsBytes", example=1503238554)
    used_threads = ExtendedSchemaNode(Integer(), name="usedThreads", example=10)
    used_cpu = ExtendedSchemaNode(Integer(), name="usedCPU", example=2)
    used_handles = ExtendedSchemaNode(Integer(), name="usedHandles", example=0)
    mem = ExtendedSchemaNode(String(), name="usedMemory", example="10 MiB",
                             description="RSS memory employed by the job execution omitting worker memory.")
    mem_bytes = ExtendedSchemaNode(Integer(), name="usedMemoryBytes", example=10485760,
                                   description="RSS memory employed by the job execution omitting worker memory.")
    total_size = ExtendedSchemaNode(String(), name="totalSize", example="10 MiB",
                                    description="Total size to store job output files.")
    total_size_bytes = ExtendedSchemaNode(Integer(), name="totalSizeBytes", example=10485760,
                                          description="Total size to store job output files.")


class OutputStatisticsSchema(ExtendedMappingSchema):
    size = ExtendedSchemaNode(String(), name="size", example="5 MiB")
    size_bytes = ExtendedSchemaNode(Integer(), name="sizeBytes", example=5242880)


class OutputStatisticsMap(ExtendedMappingSchema):
    output = OutputStatisticsSchema(variable="{output-id}", description="Spaced used by this output file.")


class JobStatisticsSchema(ExtendedMappingSchema):
    application = ApplicationStatisticsSchema(missing=drop)
    process = ProcessStatisticsSchema(missing=drop)
    outputs = OutputStatisticsMap(missing=drop)


class FrontpageParameterSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), example="api")
    enabled = ExtendedSchemaNode(Boolean(), example=True)
    url = URL(description="Referenced parameter endpoint.", example="https://weaver-host", missing=drop)
    doc = ExtendedSchemaNode(String(), example="https://weaver-host/api", missing=drop)


class FrontpageParameters(ExtendedSequenceSchema):
    parameter = FrontpageParameterSchema()


class FrontpageSchema(LandingPage, DescriptionSchema):
    message = ExtendedSchemaNode(String(), default="Weaver Information", example="Weaver Information")
    configuration = ExtendedSchemaNode(String(), default="default", example="default")
    parameters = FrontpageParameters()


class OpenAPISpecSchema(ExtendedMappingSchema):
    # "http://json-schema.org/draft-04/schema#"
    _schema = "https://spec.openapis.org/oas/3.0/schema/2021-09-28"


class SwaggerUISpecSchema(ExtendedMappingSchema):
    pass


class VersionsSpecSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), description="Identification name of the current item.", example="weaver")
    type = ExtendedSchemaNode(String(), description="Identification type of the current item.", example="api")
    version = Version(description="Version of the current item.", example="0.1.0")


class VersionsList(ExtendedSequenceSchema):
    version = VersionsSpecSchema()


class VersionsSchema(ExtendedMappingSchema):
    versions = VersionsList()


class ConformanceList(ExtendedSequenceSchema):
    conformance = URL(description="Conformance specification link.",
                      example="http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/core")


class ConformanceSchema(ExtendedMappingSchema):
    conformsTo = ConformanceList()


#################################################################
# Local Processes schemas
#################################################################


class PackageBody(ExtendedMappingSchema):
    pass


class ExecutionUnit(OneOfKeywordSchema):
    _one_of = [
        Reference(name="Reference", title="Reference", description="Execution Unit reference."),
        Unit(name="Unit", title="Unit", description="Execution Unit definition."),
    ]


class ExecutionUnitList(ExtendedSequenceSchema):
    unit = ExecutionUnit(
        name="ExecutionUnit",
        title="ExecutionUnit",
        description="Definition of the Application Package to execute."
    )
    validator = Length(min=1, max=1)


class ProcessDeploymentWithContext(ProcessDeployment):
    description = "Process deployment with OWS Context reference."
    owsContext = OWSContext(missing=required)


class ProcessVersionField(ExtendedMappingSchema):
    processVersion = Version(
        title="processVersion", missing=drop, deprecated=True,
        description="Old method of specifying the process version, prefer 'version' under 'process'."
    )


class DeployProcessOfferingContext(ProcessControl, ProcessVersionField):
    # alternative definition to make 'executionUnit' optional if instead provided through 'owsContext'
    # case where definition is nested under 'processDescription.process'
    process = ProcessDeploymentWithContext(
        description="Process definition nested under process field for backward compatibility."
    )


class DeployProcessDescriptionContext(NotKeywordSchema, ProcessDeploymentWithContext, ProcessControl):
    # alternative definition to make 'executionUnit' optional if instead provided through 'owsContext'
    # case where definition is directly under 'processDescription'
    _not = [
        Reference()  # avoid conflict with deploy by href
    ]


class DeployProcessContextChoiceType(OneOfKeywordSchema):
    _one_of = [
        DeployProcessOfferingContext(),
        DeployProcessDescriptionContext(),
    ]


class DeployProcessOffering(ProcessControl, ProcessVersionField):
    process = ProcessDeployment(description="Process definition nested under process field for backward compatibility.")


class DeployProcessDescription(NotKeywordSchema, ProcessDeployment, ProcessControl):
    _not = [
        Reference()  # avoid conflict with deploy by href
    ]
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/process.yaml"
    description = "Process description fields directly provided."


class DeployReference(Reference):
    id = ProcessIdentifier(missing=drop, description=(
        "Optional identifier of the specific process to obtain the description from in case the reference URL "
        "corresponds to an endpoint that can refer to multiple process definitions (e.g.: GetCapabilities)."
    ))


class ProcessDescriptionChoiceType(OneOfKeywordSchema):
    _one_of = [
        DeployReference(),
        DeployProcessOffering(),
        DeployProcessDescription(),
    ]


class ExecutionUnitDefinition(ExtendedMappingSchema):
    executionUnit = ExecutionUnitList()


class DeployParameters(ExtendedMappingSchema):
    immediateDeployment = ExtendedSchemaNode(Boolean(), missing=drop, default=True)
    deploymentProfileName = URL(missing=drop)


class DeployOGCAppPackage(NotKeywordSchema, ExecutionUnitDefinition, DeployParameters):
    description = "Deployment using standard OGC Application Package definition."
    _schema = f"{OGC_API_SCHEMA_EXT_DEPLOY}/ogcapppkg.yaml"
    _not = [
        CWLBase()
    ]
    processDescription = ProcessDescriptionChoiceType()


class DeployContextDefinition(NotKeywordSchema, DeployParameters):
    # alternative definition to make 'executionUnit' optional if instead provided in 'owsContext' (somewhere nested)
    _not = [
        CWLBase(),
        ExecutionUnitDefinition(),
    ]
    processDescription = DeployProcessContextChoiceType()


class CWLGraphItem(CWLApp):  # no 'cwlVersion', only one at the top
    id = CWLIdentifier()  # required in this case


class CWLGraphList(ExtendedSequenceSchema):
    cwl = CWLGraphItem()


# FIXME: supported nested and $graph multi-deployment (https://github.com/crim-ca/weaver/issues/56)
class CWLGraphBase(ExtendedMappingSchema):
    graph = CWLGraphList(
        name="$graph", description=(
            "Graph definition that defines *exactly one* CWL application package represented as list. "
            "Multiple definitions simultaneously deployed is NOT supported currently."
            # "Graph definition that combines one or many CWL application packages within a single payload. "
            # "If a single application is given (list of one item), it will be deployed as normal CWL by itself. "
            # "If multiple applications are defined, the first MUST be the top-most Workflow process. "
            # "Deployment of other items will be performed, and the full deployment will be persisted only if all are "
            # "valid. The resulting Workflow will be registered as a package by itself (i.e: not as a graph)."
        ),
        validator=Length(min=1, max=1)
    )


class UpdateVersion(ExtendedMappingSchema):
    version = Version(missing=drop, example="1.2.3", description=(
        "Explicit version to employ for initial or updated process definition. "
        "Must not already exist and must be greater than the latest available semantic version for the "
        "corresponding version level according to the applied update operation. "
        "For example, if only versions '1.2.3' and '1.3.1' exist, the submitted version can be anything before "
        "version '1.2.0' excluding it (i.e.: '1.1.X', '0.1.2', etc.), between '1.2.4' and '1.3.0' exclusively, or "
        "'1.3.2' and anything above. If no version is provided, the next *patch* level after the current process "
        "version is applied. If the current process did not define any version, it is assumed '0.0.0' and this patch"
        "will use '0.0.1'. The applicable update level (MAJOR, MINOR, PATCH) depends on the operation being applied. "
        "As a rule of thumb, if changes affect only metadata, PATCH is required. If changes affect parameters or "
        "execution method of the process, but not directly its entire definition, MINOR is required. If the process "
        "must be completely redeployed due to application redefinition, MAJOR is required."
    ))


class DeployCWLGraph(CWLBase, CWLGraphBase, UpdateVersion):
    _sort_first = ["cwlVersion", "version", "$graph"]


class DeployCWL(NotKeywordSchema, CWL, UpdateVersion):
    _sort_first = ["cwlVersion", "version", "id", "class"]
    _not = [
        CWLGraphBase()
    ]
    id = CWLIdentifier()  # required in this case, cannot have a version directly as tag, use 'version' field instead


class DeployOGCRemoteProcess(ExtendedMappingSchema):
    id = ProcessIdentifier(missing=drop, description=(
        "Optional identifier for the new process to deploy. "
        "If not provided, the ID inferred from the specified OGC API - Processes endpoint is reused."
    ))
    process = ProcessURL()


class Deploy(OneOfKeywordSchema):
    _one_of = [
        DeployOGCRemoteProcess(),
        DeployOGCAppPackage(),
        DeployContextDefinition(),
        DeployCWL(),
        DeployCWLGraph(),
    ]


class DeployContentType(ContentTypeHeader):
    example = ContentType.APP_JSON
    default = ContentType.APP_JSON
    validator = OneOf([
        ContentType.APP_JSON,
        ContentType.APP_CWL,
        ContentType.APP_CWL_JSON,
        ContentType.APP_CWL_YAML,
        ContentType.APP_CWL_X,
        ContentType.APP_OGC_PKG_JSON,
        ContentType.APP_OGC_PKG_YAML,
        ContentType.APP_YAML,
    ])


class DeployHeaders(RequestHeaders):
    x_auth_docker = XAuthDockerHeader()
    content_type = DeployContentType()


class PostProcessesEndpoint(ExtendedMappingSchema):
    header = DeployHeaders(description="Headers employed for process deployment.")
    body = Deploy(title="Deploy", examples={
        "DeployCWL": {
            "summary": "Deploy a process from a CWL definition.",
            "value": EXAMPLES["deploy_process_cwl.json"],
        },
        "DeployOGC": {
            "summary": "Deploy a process from an OGC Application Package definition.",
            "value": EXAMPLES["deploy_process_ogcapppkg.json"],
        },
        "DeployWPS": {
            "summary": "Deploy a process from a remote WPS-1 reference URL.",
            "value": EXAMPLES["deploy_process_wps1.json"],
        }
    })


class UpdateInputOutputBase(DescriptionType, InputOutputDescriptionMeta):
    pass


class UpdateInputOutputItem(InputIdentifierType, UpdateInputOutputBase):
    pass


class UpdateInputOutputList(ExtendedSequenceSchema):
    io_item = UpdateInputOutputItem()


class UpdateInputOutputMap(PermissiveMappingSchema):
    io_id = UpdateInputOutputBase(
        variable="{input-output-id}",
        description="Input/Output definition under mapping for process update."
    )


class UpdateInputOutputDefinition(OneOfKeywordSchema):
    _one_of = [
        UpdateInputOutputMap(),
        UpdateInputOutputList(),
    ]


class PatchProcessBodySchema(UpdateVersion):
    title = ExtendedSchemaNode(String(), missing=drop, description=(
        "New title to override current one. "
        "Minimum required change version level: PATCH."
    ))
    description = ExtendedSchemaNode(String(), missing=drop, description=(
        "New description to override current one. "
        "Minimum required change version level: PATCH."
    ))
    keywords = KeywordList(missing=drop, description=(
        "Keywords to add (append) to existing definitions. "
        "To remove all keywords, submit an empty list. "
        "To replace keywords, perform two requests, one with empty list and the following one with new definitions. "
        "Minimum required change version level: PATCH."
    ))
    metadata = MetadataList(missing=drop, description=(
        "Metadata to add (append) to existing definitions. "
        "To remove all metadata, submit an empty list. "
        "To replace metadata, perform two requests, one with empty list and the following one with new definitions. "
        "Relations must be unique across existing and new submitted metadata. "
        "Minimum required change version level: PATCH."
    ))
    links = LinkList(missing=drop, description=(
        "Links to add (append) to existing definitions. Relations must be unique. "
        "To remove all (additional) links, submit an empty list. "
        "To replace links, perform two requests, one with empty list and the following one with new definitions. "
        "Note that modifications to links only considers custom links. Other automatically generated links such as "
        "API endpoint and navigation references cannot be removed or modified. "
        "Relations must be unique across existing and new submitted links. "
        "Minimum required change version level: PATCH."
    ))
    inputs = UpdateInputOutputDefinition(missing=drop, description=(
        "Update details of individual input elements. "
        "Minimum required change version levels are the same as process-level fields of corresponding names."
    ))
    outputs = UpdateInputOutputDefinition(missing=drop, description=(
        "Update details of individual output elements. "
        "Minimum required change version levels are the same as process-level fields of corresponding names."
    ))
    jobControlOptions = JobControlOptionsList(missing=drop, description=(
        "New job control options supported by this process for its execution. "
        "All desired job control options must be provided (full override, not appending). "
        "Order is important to define the default behaviour (first item) to use when unspecified during job execution. "
        "Minimum required change version level: MINOR."
    ))
    outputTransmission = TransmissionModeList(missing=drop, description=(
        "New output transmission methods supported following this process execution. "
        "All desired output transmission modes must be provided (full override, not appending). "
        "Minimum required change version level: MINOR."
    ))
    visibility = VisibilityValue(missing=drop, description=(
        "New process visibility. "
        "Minimum required change version level: MINOR."
    ))


class PutProcessBodySchema(Deploy):
    description = "Process re-deployment using an updated version and definition."


class PatchProcessEndpoint(LocalProcessPath):
    headers = RequestHeaders()
    querystring = LocalProcessQuery()
    body = PatchProcessBodySchema()


class PutProcessEndpoint(LocalProcessPath):
    headers = RequestHeaders()
    querystring = LocalProcessQuery()
    body = PutProcessBodySchema()


class WpsOutputContextHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "X-WPS-Output-Context"
    description = (
        "Contextual location where to store WPS output results from job execution. ",
        "When provided, value must be a directory or sub-directories slug. ",
        "Resulting contextual location will be relative to server WPS outputs when no context is provided.",
    )
    schema_type = String
    missing = drop
    example = "my-directory/sub-project"
    default = None


class ExecuteHeadersBase(RequestHeaders):
    description = "Request headers supported for job execution."
    x_wps_output_context = WpsOutputContextHeader()


class ExecuteHeadersJSON(ExecuteHeadersBase):
    content_type = ContentTypeHeader(
        missing=drop, default=ContentType.APP_JSON,
        validator=OneOf([ContentType.APP_JSON])
    )


class ExecuteHeadersXML(ExecuteHeadersBase):
    content_type = ContentTypeHeader(
        missing=drop, default=ContentType.APP_XML,
        validator=OneOf(ContentType.ANY_XML)
    )


class PostProcessJobsEndpointJSON(LocalProcessPath):
    content_type = ContentType.APP_JSON
    header = ExecuteHeadersJSON()
    querystring = LocalProcessQuery()
    body = Execute()


class PostProcessJobsEndpointXML(LocalProcessPath):
    content_type = ContentType.APP_XML
    header = ExecuteHeadersXML()
    querystring = LocalProcessQuery()
    body = WPSExecutePost(
        # very important to override 'name' in this case
        # original schema uses it to specify the XML class name
        # in this context, it is used to define the 'in' location of this schema to form 'requestBody' in OpenAPI
        name="body",
        examples={
            "ExecuteXML": {
                "summary": "Execute a process job using WPS-like XML payload.",
                "value": EXAMPLES["wps_execute_request.xml"],
            }
        }
    )


class PagingQueries(ExtendedMappingSchema):
    page = ExtendedSchemaNode(Integer(allow_string=True), missing=0, default=0, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(allow_string=True), missing=10, default=10, validator=Range(min=1, max=1000),
                               schema=f"{OGC_API_PROC_PART1_PARAMETERS}/limit.yaml")


class GetJobsQueries(PagingQueries):
    # note:
    #   This schema is also used to generate any missing defaults during filter parameter handling.
    #   Items with default value are added if omitted, except 'default=null' which are removed after handling by alias.
    detail = ExtendedSchemaNode(QueryBoolean(), default=False, example=True, missing=drop,
                                description="Provide job details instead of IDs.")
    groups = JobGroupsCommaSeparated()
    min_duration = ExtendedSchemaNode(
        Integer(allow_string=True), name="minDuration", missing=drop, default=null, validator=Range(min=0),
        schema=f"{OGC_API_PROC_PART1_PARAMETERS}/minDuration.yaml",
        description="Minimal duration (seconds) between started time and current/finished time of jobs to find.")
    max_duration = ExtendedSchemaNode(
        Integer(allow_string=True), name="maxDuration", missing=drop, default=null, validator=Range(min=0),
        schema=f"{OGC_API_PROC_PART1_PARAMETERS}/maxDuration.yaml",
        description="Maximum duration (seconds) between started time and current/finished time of jobs to find.")
    datetime = DateTimeInterval(missing=drop, default=None)
    status = JobStatusSearchEnum(description="One of more comma-separated statuses to filter jobs.",
                                 missing=drop, default=None)
    processID = ProcessIdentifierTag(missing=drop, default=null,
                                     schema=f"{OGC_API_PROC_PART1_PARAMETERS}/processIdQueryParam.yaml",
                                     description="Alias to 'process' for OGC-API compliance.")
    process = ProcessIdentifierTag(missing=drop, default=None,
                                   description="Identifier and optional version tag of the process to filter search.")
    version = Version(
        missing=drop, default=None, example="0.1.0", description=(
            "Version of the 'process' or 'processID' query parameters. "
            "If version is provided, those query parameters should specify the ID without tag."
        )
    )
    service = AnyIdentifier(missing=drop, default=null, description="Alias to 'provider' for backward compatibility.")
    provider = AnyIdentifier(missing=drop, default=None, description="Identifier of service provider to filter search.")
    type = JobTypeEnum(missing=drop, default=null,
                       description="Filter jobs only to matching type (note: 'service' and 'provider' are aliases).")
    sort = JobSortEnum(missing=drop)
    access = JobAccess(missing=drop, default=None)
    notification_email = ExtendedSchemaNode(String(), missing=drop, validator=Email())
    tags = JobTagsCommaSeparated()


class GetProcessJobsQuery(LocalProcessQuery, GetJobsQueries):
    pass


class GetProviderJobsQueries(GetJobsQueries):  # ':version' not allowed for process ID in this case
    pass


class GetJobsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetProcessJobsQuery()  # allowed version in this case since can be either local or remote processes


class GetProcessJobsEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = GetProcessJobsQuery()


class GetProviderJobsEndpoint(ProviderProcessPath):
    header = RequestHeaders()
    querystring = GetProviderJobsQueries()


class JobIdentifierList(ExtendedSequenceSchema):
    job_id = UUID(description="ID of a job to dismiss. Identifiers not matching any known job are ignored.")


class DeleteJobsBodySchema(ExtendedMappingSchema):
    jobs = JobIdentifierList()


class DeleteJobsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    body = DeleteJobsBodySchema()


class DeleteProcessJobsEndpoint(DeleteJobsEndpoint, LocalProcessPath):
    querystring = LocalProcessQuery()


class DeleteProviderJobsEndpoint(DeleteJobsEndpoint, ProviderProcessPath):
    pass


class GetProcessJobEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class DeleteProcessJobEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class BillsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class BillEndpoint(BillPath):
    header = RequestHeaders()


class ProcessQuotesEndpoint(LocalProcessPath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class ProcessQuoteEndpoint(LocalProcessPath, QuotePath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()


class GetQuotesQueries(PagingQueries):
    process = AnyIdentifier(missing=None)
    sort = QuoteSortEnum(missing=drop)


class QuotesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetQuotesQueries()


class QuoteEndpoint(QuotePath):
    header = RequestHeaders()


class PostProcessQuote(LocalProcessPath, QuotePath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()
    body = NoContent()


class PostQuote(QuotePath):
    header = RequestHeaders()
    body = NoContent()


class QuoteProcessParametersSchema(ExecuteInputOutputs):
    pass


class PostProcessQuoteRequestEndpoint(LocalProcessPath, QuotePath):
    header = RequestHeaders()
    querystring = LocalProcessQuery()
    body = QuoteProcessParametersSchema()


# ################################################################
# Provider Processes schemas
# ################################################################


class ProvidersQuerySchema(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Return summary details about each provider, or simply their IDs."
    )
    check = ExtendedSchemaNode(
        QueryBoolean(),
        example=True, default=True, missing=drop,
        description="List only reachable providers, dropping unresponsive ones that cannot be checked for listing. "
                    "Otherwise, all registered providers are listed regardless of their availability. When requesting "
                    "details, less metadata will be provided since it will not be fetched from remote services."
    )
    ignore = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="When listing providers with check of reachable remote service definitions, unresponsive response "
                    "or unprocessable contents will be silently ignored and dropped from full listing in the response. "
                    "Disabling this option will raise an error immediately instead of ignoring invalid services."
    )


class GetProviders(ExtendedMappingSchema):
    querystring = ProvidersQuerySchema()
    header = RequestHeaders()


class PostProvider(ExtendedMappingSchema):
    header = RequestHeaders()
    body = CreateProviderRequestBody()


class ProcessDetailQuery(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class ProcessLinksQuery(ExtendedMappingSchema):
    links = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Return summary details with included links for each process."
    )


class ProcessRevisionsQuery(ExtendedMappingSchema):
    process = ProcessIdentifier(missing=drop, description=(
        "Process ID (excluding version) for which to filter results. "
        "When combined with 'revisions=true', allows listing of all reversions of a given process. "
        "If omitted when 'revisions=true', all revisions of every process ID will be returned. "
        "If used without 'revisions' query, list should include a single process as if summary was requested directly."
    ))
    revisions = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=False, missing=drop, description=(
            "Return all revisions of processes, or simply their latest version. When returning all revisions, "
            "IDs will be replaced by '{processID}:{version}' tag representation to avoid duplicates."
        )
    )


class ProviderProcessesQuery(ProcessPagingQuery, ProcessDetailQuery, ProcessLinksQuery):
    pass


class ProviderProcessesEndpoint(ProviderPath):
    header = RequestHeaders()
    querystring = ProviderProcessesQuery()


class GetProviderProcess(ExtendedMappingSchema):
    header = RequestHeaders()


class PostProviderProcessJobRequest(ExtendedMappingSchema):
    """
    Launching a new process request definition.
    """
    header = ExecuteHeadersJSON()
    querystring = LaunchJobQuerystring()
    body = Execute()


# ################################################################
# Responses schemas
# ################################################################

class ErrorDetail(ExtendedMappingSchema):
    code = ExtendedSchemaNode(Integer(), description="HTTP status code.", example=400)
    status = ExtendedSchemaNode(String(), description="HTTP status detail.", example="400 Bad Request")


class OWSErrorCode(ExtendedSchemaNode):
    schema_type = String
    example = "InvalidParameterValue"
    description = "OWS error code."


class OWSExceptionResponse(ExtendedMappingSchema):
    """
    Error content in XML format.
    """
    description = "OWS formatted exception."
    code = OWSErrorCode(example="NoSuchProcess")
    locator = ExtendedSchemaNode(String(), example="identifier",
                                 description="Indication of the element that caused the error.")
    message = ExtendedSchemaNode(String(), example="Invalid process ID.",
                                 description="Specific description of the error.")


class ErrorCause(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), description="Error message from exception or cause of failure."),
        PermissiveMappingSchema(description="Relevant error fields with details about the cause."),
    ]


class ErrorJsonResponseBodySchema(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/exception.yaml"
    description = "JSON schema for exceptions based on RFC 7807"
    type = OWSErrorCode()
    title = ExtendedSchemaNode(String(), description="Short description of the error.", missing=drop)
    detail = ExtendedSchemaNode(String(), description="Detail about the error cause.", missing=drop)
    status = ExtendedSchemaNode(Integer(), description="Error status code.", example=500)
    cause = ErrorCause(missing=drop)
    value = ErrorCause(missing=drop)
    error = ErrorDetail(missing=drop)
    instance = ExtendedSchemaNode(String(), missing=drop)
    exception = OWSExceptionResponse(missing=drop)


class ServerErrorBaseResponseSchema(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/ServerError.yaml"


class BadRequestResponseSchema(ServerErrorBaseResponseSchema):
    description = "Incorrectly formed request contents."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ConflictRequestResponseSchema(ServerErrorBaseResponseSchema):
    description = "Conflict between the affected entity and another existing definition."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class UnprocessableEntityResponseSchema(ServerErrorBaseResponseSchema):
    description = "Wrong format of given parameters."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class UnsupportedMediaTypeResponseSchema(ServerErrorBaseResponseSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/NotSupported.yaml"
    description = "Media-Type not supported for this request."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class MethodNotAllowedErrorResponseSchema(ServerErrorBaseResponseSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/NotAllowed.yaml"
    description = "HTTP method not allowed for requested path."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class NotFoundResponseSchema(ServerErrorBaseResponseSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/NotFound.yaml"
    description = "Requested resource could not be found."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProcessAccessResponseSchema(ServerErrorBaseResponseSchema):
    description = "Referenced process is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProviderAccessResponseSchema(ServerErrorBaseResponseSchema):
    description = "Referenced provider is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProviderLocalResponseSchema(ServerErrorBaseResponseSchema):
    description = (
        "Provider operation is not allowed on local-only Weaver instance. "
        f"Applies only when application configuration is not within: {WEAVER_CONFIG_REMOTE_LIST}"
    )
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class InternalServerErrorResponseSchema(ServerErrorBaseResponseSchema):
    description = "Unhandled internal server error."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageResponse(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/LandingPage.yaml"
    header = ResponseHeaders()
    body = FrontpageSchema()


class OpenAPIResponseContentTypeHeader(ContentTypeHeader):
    example = ContentType.APP_OAS_JSON
    default = ContentType.APP_OAS_JSON
    validator = OneOf([ContentType.APP_OAS_JSON])


class OpenAPIResponseHeaders(ResponseHeaders):
    content_type = OpenAPIResponseContentTypeHeader()


class OkGetSwaggerJSONResponse(ExtendedMappingSchema):
    header = OpenAPIResponseHeaders()
    body = OpenAPISpecSchema(description="OpenAPI JSON schema of Weaver API.")
    examples = {
        "OpenAPI Schema": {
            "summary": "OpenAPI specification of this API.",
            "value": {"$ref": OpenAPISpecSchema._schema},
        }
    }


class OkGetSwaggerUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of Weaver API.")


class OkGetRedocUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Redoc UI of Weaver API.")


class OkGetVersionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = VersionsSchema()


class OkGetConformanceResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ConformanceSchema()


class OkGetProvidersListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProvidersBodySchema()


class OkGetProviderCapabilitiesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderCapabilitiesSchema()


class NoContentDeleteProviderSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class NotImplementedDeleteProviderResponse(ExtendedMappingSchema):
    description = "Provider removal not supported using referenced storage."


class OkGetProviderProcessesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderProcessesSchema()


class GetProcessesQuery(ProcessPagingQuery, ProcessDetailQuery, ProcessLinksQuery, ProcessRevisionsQuery):
    providers = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=False, missing=drop,
        description="List local processes as well as all sub-processes of all registered providers. "
                    "Paging and sorting query parameters are unavailable when providers are requested since lists are "
                    "populated dynamically and cannot ensure consistent process lists per page across providers. "
                    f"Applicable only for Weaver configurations {WEAVER_CONFIG_REMOTE_LIST}, ignored otherwise."
    )
    ignore = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Only when listing provider processes, any unreachable remote service definitions "
                    "or unprocessable contents will be silently ignored and dropped from full listing in the response. "
                    "Disabling this option will raise an error immediately instead of ignoring invalid providers."
    )


class GetProcessesEndpoint(ExtendedMappingSchema):
    querystring = GetProcessesQuery()


class ProviderProcessesListing(ProcessCollection):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/processList.yaml"
    _sort_first = ["id", "processes"]
    id = ProviderNameSchema()


class ProviderProcessesList(ExtendedSequenceSchema):
    item = ProviderProcessesListing(description="Processes offered by the identified remote provider.")


class ProvidersProcessesCollection(ExtendedMappingSchema):
    providers = ProviderProcessesList(missing=drop)


class ProcessListingLinks(ExtendedMappingSchema):
    links = LinkList(missing=drop)


class ProcessListingMetadata(PagingBodySchema):
    description = "Metadata relative to the listed processes."
    total = ExtendedSchemaNode(Integer(), description="Total number of local processes, or also including all "
                                                      "remote processes across providers if requested.")


class ProcessesListing(ProcessCollection, ProcessListingLinks):
    _schema = f"{OGC_API_PROC_PART1_SCHEMAS}/processList.yaml"
    _sort_first = PROCESSES_LISTING_FIELD_FIRST
    _sort_after = PROCESSES_LISTING_FIELD_AFTER


class MultiProcessesListing(DescriptionSchema, ProcessesListing, ProvidersProcessesCollection, ProcessListingMetadata):
    pass


class OkGetProcessesListResponse(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/ProcessList.yaml"
    description = "Listing of available processes successful."
    header = ResponseHeaders()
    body = MultiProcessesListing()


class OkPostProcessDeployBodySchema(ExtendedMappingSchema):
    description = ExtendedSchemaNode(String(), description="Detail about the operation.")
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully deployed.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of deploy failure if applicable.")


class OkPostProcessesResponse(ExtendedMappingSchema):
    description = "Process successfully deployed."
    header = ResponseHeaders()
    body = OkPostProcessDeployBodySchema()


class OkPatchProcessUpdatedBodySchema(ExtendedMappingSchema):
    description = ExtendedSchemaNode(String(), description="Detail about the operation.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")


class OkPatchProcessResponse(ExtendedMappingSchema):
    description = "Process successfully updated."
    header = ResponseHeaders()
    body = OkPatchProcessUpdatedBodySchema()


class BadRequestGetProcessInfoResponse(ExtendedMappingSchema):
    description = "Missing process identifier."
    body = NoContent()


class NotFoundProcessResponse(NotFoundResponseSchema):
    description = "Process with specified reference identifier does not exist."
    examples = {
        "ProcessNotFound": {
            "summary": "Example response when specified process reference cannot be found.",
            "value": EXAMPLES["local_process_not_found.json"]
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetProcessInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDescription()


class OkGetProcessPackageSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class OkGetProcessPayloadSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class ProcessVisibilityResponseBodySchema(ExtendedMappingSchema):
    value = VisibilityValue()


class OkGetProcessVisibilitySchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessVisibilityResponseBodySchema()


class OkPutProcessVisibilitySchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessVisibilityResponseBodySchema()


class ForbiddenVisibilityUpdateResponseSchema(ExtendedMappingSchema):
    description = "Visibility value modification not allowed."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkDeleteProcessUndeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully undeployed.")
    identifier = ExtendedSchemaNode(String(), example="workflow")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of undeploy failure if applicable.")


class OkDeleteProcessResponse(ExtendedMappingSchema):
    description = "Process successfully undeployed."
    header = ResponseHeaders()
    body = OkDeleteProcessUndeployBodySchema()


class OkGetProviderProcessDescriptionResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDescription()


class CreatedPostProvider(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderSummarySchema()


class NotImplementedPostProviderResponse(ExtendedMappingSchema):
    description = "Provider registration not supported using specified definition."


class PreferenceAppliedHeader(ExtendedSchemaNode):
    description = "Applied preferences from submitted 'Prefer' header after validation."
    name = "Preference-Applied"
    schema_type = String
    example = "wait=10s, respond-async"


class LocationHeader(URL):
    name = "Location"


class CreatedJobLocationHeader(ResponseHeaders):
    location = LocationHeader(description="Status monitoring location of the job execution.")
    prefer_applied = PreferenceAppliedHeader(missing=drop)


class CreatedLaunchJobResponse(ExtendedMappingSchema):
    description = "Job successfully submitted to processing queue. Execution should begin when resources are available."
    examples = {
        "JobAccepted": {
            "summary": "Job accepted for execution.",
            "value": EXAMPLES["job_status_accepted.json"]
        }
    }
    header = CreatedJobLocationHeader()
    body = CreatedJobStatusSchema()


class CompletedJobLocationHeader(ResponseHeaders):
    location = LocationHeader(description="Status location of the completed job execution.")
    prefer_applied = PreferenceAppliedHeader(missing=drop)


class CompletedJobStatusSchema(DescriptionSchema, JobStatusInfo):
    pass


class CompletedJobResponse(ExtendedMappingSchema):
    description = "Job submitted and completed execution synchronously."
    header = CompletedJobLocationHeader()
    body = CompletedJobStatusSchema()


class FailedSyncJobResponse(CompletedJobResponse):
    description = "Job submitted and failed synchronous execution. See server logs for more details."


class InvalidJobParametersResponse(ExtendedMappingSchema):
    description = "Job parameters failed validation."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkDeleteProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetQueriedJobsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = GetQueriedJobsSchema()


class BatchDismissJobsBodySchema(DescriptionSchema):
    jobs = JobIdentifierList(description="Confirmation of jobs that have been dismissed.")


class OkBatchDismissJobsResponseSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BatchDismissJobsBodySchema()


class OkDismissJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetJobStatusResponse(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/Status.yaml"
    header = ResponseHeaders()
    body = JobStatusInfo()


class InvalidJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference is not a valid UUID."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class NotFoundJobResponseSchema(NotFoundResponseSchema):
    description = "Job reference UUID cannot be found."
    examples = {
        "JobNotFound": {
            "summary": "Example response when specified job reference cannot be found.",
            "value": EXAMPLES["job_not_found.json"]
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class GoneJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference UUID cannot be dismissed again or its result artifacts were removed."
    examples = {
        "JobDismissed": {
            "summary": "Example response when specified job reference was already dismissed.",
            "value": EXAMPLES["job_dismissed_error.json"]
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetJobInputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobInputsBody()


class OkGetJobOutputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobOutputsBody()


class RedirectResultResponse(ExtendedMappingSchema):
    header = RedirectHeaders()


class OkGetJobResultsResponse(ExtendedMappingSchema):
    _schema = f"{OGC_API_PROC_PART1_RESPONSES}/Results.yaml"
    header = ResponseHeaders()
    body = Result()


class NoContentJobResultsHeaders(NoContent):
    content_length = ContentLengthHeader(example="0")
    link = LinkHeader(description=(
        "Link to a result requested by reference output transmission. "
        "Link relation indicates the result ID. "
        "Additional parameters indicate expected content-type of the resource. "
        "Literal data requested by reference are returned with contents dumped to plain text file."
    ))


class NoContentJobResultsResponse(ExtendedMappingSchema):
    header = NoContentJobResultsHeaders()
    body = NoContent(default="")


class CreatedQuoteExecuteResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedQuotedJobStatusSchema()


class CreatedQuoteResponse(ExtendedMappingSchema):
    description = "Quote successfully obtained for process execution definition."
    header = ResponseHeaders()
    body = QuoteSchema()


class AcceptedQuoteResponse(ExtendedMappingSchema):
    summary = "Quote successfully submitted."
    description = (
        "Quote successfully submitted for evaluating process execution definition. "
        "Complete details will be available once evaluation has completed."
    )
    header = ResponseHeaders()
    body = PartialQuoteSchema()


class QuotePaymentRequiredResponse(ServerErrorBaseResponseSchema):
    description = "Quoted process execution refused due to missing payment."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetQuoteInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class NotFoundQuoteResponse(NotFoundResponseSchema):
    description = "Quote with specified reference identifier does not exist."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetQuoteListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuotationListSchema()


class OkGetEstimatorResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteEstimatorSchema()


class OkPutEstimatorResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DescriptionSchema()


class OkDeleteEstimatorResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DescriptionSchema()


class OkGetBillDetailResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillSchema()


class OkGetBillListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillListSchema()


class OkGetJobExceptionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobExceptionsSchema()


class OkGetJobLogsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobLogsSchema()


class OkGetJobStatsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatisticsSchema()


class VaultFileID(UUID):
    description = "Vault file identifier."
    example = "78977deb-28af-46f3-876b-cdd272742678"


class VaultAccessToken(UUID):
    description = "Vault file access token."
    example = "30d889cfb7ae3a63229a8de5f91abc1ef5966bb664972f234a4db9d28f8148e0e"  # nosec


class VaultEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class VaultUploadBody(ExtendedSchemaNode):
    schema_type = String
    description = "Multipart file contents for upload to the vault."
    examples = {
        ContentType.MULTI_PART_FORM: {
            "summary": "Upload JSON file to vault as multipart content.",
            "value": EXAMPLES["vault_file_upload.txt"],
        }
    }


class VaultUploadEndpoint(ExtendedMappingSchema):
    header = FileUploadHeaders()
    body = VaultUploadBody()


class VaultFileUploadedBodySchema(ExtendedMappingSchema):
    access_token = AccessToken()
    file_id = VaultFileID()
    file_href = VaultReference()


class VaultFileUploadedHeaders(ResponseHeaders):
    location = URL(name="Location", description="File download location.",
                   example=f"https://localhost:4002{vault_file_service.path.format(file_id=VaultFileID.example)}")


class OkVaultFileUploadedResponse(ExtendedMappingSchema):
    description = "File successfully uploaded to vault."
    header = VaultFileUploadedHeaders()
    body = VaultFileUploadedBodySchema()


class BadRequestVaultFileUploadResponse(ExtendedMappingSchema):
    description = "Missing or incorrectly formed file contents."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class UnprocessableEntityVaultFileUploadResponse(ExtendedMappingSchema):
    description = (
        "Invalid filename refused for upload. "
        "Filename should include only alphanumeric, underscore, dash, and dot characters. "
        "Filename should include both the base name and the desired file extension."
    )
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class XAuthVaultFileHeader(ExtendedSchemaNode):
    summary = "Authorization header with token for Vault file access."
    description = (
        "For accessing a single file from the Vault, such as to obtain file metadata, requests can simply provide "
        "the 'token {access-token}' portion in the header without additional parameters. If multiple files require "
        "access such as during an Execute request, all applicable tokens should be provided using a comma separated "
        "list of access tokens, each with their indented input ID and array index if applicable "
        f"(see {DOC_URL}/processes.html#file-vault-inputs for more details)."
    )
    name = "X-Auth-Vault"
    example = "token {access-token}[; id={vault-id}]"
    schema_type = String


class VaultFileRequestHeaders(ExtendedMappingSchema):
    access_token = XAuthVaultFileHeader()


class VaultFileEndpoint(VaultEndpoint):
    header = VaultFileRequestHeaders()
    file_id = VaultFileID()


class OkVaultFileDetailResponse(ExtendedMappingSchema):
    header = FileResponseHeaders()
    body = NoContent(default="")


class OkVaultFileDownloadResponse(OkVaultFileDetailResponse):
    pass


class BadRequestVaultFileAccessResponse(ExtendedMappingSchema):
    description = "Invalid file vault reference."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenVaultFileDownloadResponse(ExtendedMappingSchema):
    description = "Forbidden access to vault file. Invalid authorization from provided token."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class GoneVaultFileDownloadResponse(ExtendedMappingSchema):
    description = "Vault File resource corresponding to specified ID is not available anymore."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


get_api_frontpage_responses = {
    "200": OkGetFrontpageResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_openapi_json_responses = {
    "200": OkGetSwaggerJSONResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_api_swagger_ui_responses = {
    "200": OkGetSwaggerUIResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_api_redoc_ui_responses = {
    "200": OkGetRedocUIResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_api_versions_responses = {
    "200": OkGetVersionsResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_api_conformance_responses = {
    "200": OkGetConformanceResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_processes_responses = {
    "200": OkGetProcessesListResponse(examples={
        "ProcessesListing": {
            "summary": "Listing of identifiers of local processes registered in Weaver.",
            "value": EXAMPLES["local_process_listing.json"],
        },
        "ProcessesDetails": {
            "summary": "Detailed definitions of local processes registered in Weaver.",
            "value": EXAMPLES["local_process_listing.json"],
        },
        "ProvidersProcessesListing": {
            "summary": "List of identifiers combining all local and remote processes known by Weaver.",
            "value": EXAMPLES["providers_processes_listing.json"],
        },
        "ProvidersProcessesDetails": {
            "summary": "Detailed definitions Combining all local and remote processes known by Weaver.",
            "value": EXAMPLES["providers_processes_listing.json"],
        }
    }),
    "400": BadRequestResponseSchema(description="Error in case of invalid listing query parameters."),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_processes_responses = {
    "201": OkPostProcessesResponse(examples={
        "ProcessDeployed": {
            "summary": "Process successfully deployed.",
            "value": EXAMPLES["local_process_deploy_success.json"],
        }
    }),
    "400": BadRequestResponseSchema(description="Unable to parse process definition"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "409": ConflictRequestResponseSchema(description="Process with same ID already exists."),
    "415": UnsupportedMediaTypeResponseSchema(description="Unsupported Media-Type for process deployment."),
    "422": UnprocessableEntityResponseSchema(description="Invalid schema for process definition."),
    "500": InternalServerErrorResponseSchema(),
}
put_process_responses = copy(post_processes_responses)
put_process_responses.update({
    "404": NotFoundProcessResponse(description="Process to update could not be found."),
    "405": MethodNotAllowedErrorResponseSchema(),
    "409": ConflictRequestResponseSchema(description="Process with same ID or version already exists."),
})
patch_process_responses = {
    "200": OkPatchProcessResponse(),
    "400": BadRequestGetProcessInfoResponse(description="Unable to parse process definition"),
    "404": NotFoundProcessResponse(description="Process to update could not be found."),
    "405": MethodNotAllowedErrorResponseSchema(),
    "409": ConflictRequestResponseSchema(description="Process with same ID or version already exists."),
    "422": UnprocessableEntityResponseSchema(description="Invalid schema for process definition."),
    "500": InternalServerErrorResponseSchema(),
}
get_process_responses = {
    "200": OkGetProcessInfoResponse(description="success", examples={
        "ProcessDescriptionSchemaOGC": {
            "summary": "Description of a local process registered in Weaver (OGC Schema) "
                       "with fields on top-level and using inputs/outputs as mapping with keys as IDs.",
            "value": EXAMPLES["local_process_description_ogc_api.json"],
        },
        "ProcessDescriptionSchemaOld": {
            "summary": "Description of a local process registered in Weaver (Old Schema) "
                       "with fields nested under a process section and using inputs/outputs listed with IDs.",
            "value": EXAMPLES["local_process_description.json"],
        },
        "ProcessDescriptionSchemaWPS": {
            "Summary": "Description of a local process registered in Weaver (WPS Schema) when requesting XML format.",
            "value": EXAMPLES["wps_describeprocess_response.xml"],
        }
    }),
    "400": BadRequestGetProcessInfoResponse(),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_package_responses = {
    "200": OkGetProcessPackageSchema(description="success", examples={
        "PackageCWL": {
            "summary": "CWL Application Package definition of the local process.",
            "value": EXAMPLES["local_process_package.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_payload_responses = {
    "200": OkGetProcessPayloadSchema(description="success", examples={
        "Payload": {
            "summary": "Payload employed during process deployment and registration.",
            "value": EXAMPLES["local_process_payload.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_visibility_responses = {
    "200": OkGetProcessVisibilitySchema(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
put_process_visibility_responses = {
    "200": OkPutProcessVisibilitySchema(description="success"),
    "403": ForbiddenVisibilityUpdateResponseSchema(),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_process_responses = {
    "200": OkDeleteProcessResponse(examples={
        "ProcessUndeployed": {
            "summary": "Process successfully undeployed.",
            "value": EXAMPLES["local_process_undeploy_success.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_providers_list_responses = {
    "200": OkGetProvidersListResponse(description="success", examples={
        "ProviderList": {
            "summary": "Listing of registered remote providers.",
            "value": EXAMPLES["provider_listing.json"],
        },
        "ProviderNames": {
            "summary": "Listing of registered providers names without validation.",
            "value": EXAMPLES["provider_names.json"],
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_provider_responses = {
    "200": OkGetProviderCapabilitiesSchema(description="success", examples={
        "ProviderDescription": {
            "summary": "Description of a registered remote WPS provider.",
            "value": EXAMPLES["provider_description.json"],
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_provider_responses = {
    "204": NoContentDeleteProviderSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedDeleteProviderResponse(),
}
get_provider_processes_responses = {
    "200": OkGetProviderProcessesSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_provider_process_responses = {
    "200": OkGetProviderProcessDescriptionResponse(description="success", examples={
        "ProviderProcessWPS": {
            "summary": "Description of a remote WPS provider process converted to OGC-API Processes format.",
            "value": EXAMPLES["provider_process_description.json"]
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_provider_responses = {
    "201": CreatedPostProvider(description="success"),
    "400": ExtendedMappingSchema(description=OWSMissingParameterValue.description),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedPostProviderResponse(),
}
post_provider_process_job_responses = {
    "200": CompletedJobResponse(description="success"),
    "201": CreatedLaunchJobResponse(description="success"),
    "204": NoContentJobResultsResponse(description="success"),
    "400": InvalidJobParametersResponse(),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_process_jobs_responses = {
    "200": CompletedJobResponse(description="success"),
    "201": CreatedLaunchJobResponse(description="success"),
    "204": NoContentJobResultsResponse(description="success"),
    "400": InvalidJobParametersResponse(),
    "403": ForbiddenProviderAccessResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_all_jobs_responses = {
    "200": OkGetQueriedJobsResponse(description="success", examples={
        "JobListing": {
            "summary": "Job ID listing with default queries.",
            "value": EXAMPLES["jobs_listing.json"]
        }
    }),
    "400": BadRequestResponseSchema(description="Error in case of invalid search query parameters."),
    "405": MethodNotAllowedErrorResponseSchema(),
    "422": UnprocessableEntityResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_jobs_responses = {
    "200": OkBatchDismissJobsResponseSchema(description="success"),
    "400": BadRequestResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "422": UnprocessableEntityResponseSchema(),
}
get_prov_all_jobs_responses = copy(get_all_jobs_responses)
get_prov_all_jobs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_single_job_status_responses = {
    "200": OkGetJobStatusResponse(description="success", examples={
        "JobStatusSuccess": {
            "summary": "Successful job status response.",
            "value": EXAMPLES["job_status_success.json"],
        },
        "JobStatusFailure": {
            "summary": "Failed job status response.",
            "value": EXAMPLES["job_status_failed.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_single_job_status_responses = copy(get_single_job_status_responses)
get_prov_single_job_status_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
delete_job_responses = {
    "200": OkDismissJobResponse(description="success", examples={
        "JobDismissedSuccess": {
            "summary": "Successful job dismissed response.",
            "value": EXAMPLES["job_dismissed_success.json"]
        },
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_prov_job_responses = copy(delete_job_responses)
delete_prov_job_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_job_inputs_responses = {
    "200": OkGetJobInputsResponse(description="success", examples={
        "JobInputs": {
            "summary": "Submitted job input values at for process execution.",
            "value": EXAMPLES["job_inputs.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_inputs_responses = copy(get_job_inputs_responses)
get_prov_inputs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_job_outputs_responses = {
    "200": OkGetJobOutputsResponse(description="success", examples={
        "JobOutputs": {
            "summary": "Obtained job outputs values following process execution.",
            "value": EXAMPLES["job_outputs.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_outputs_responses = copy(get_job_outputs_responses)
get_prov_outputs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_result_redirect_responses = {
    "308": RedirectResultResponse(description="Redirects '/result' (without 's') to corresponding '/results' path."),
}
get_job_results_responses = {
    "200": OkGetJobResultsResponse(description="success", examples={
        "JobResults": {
            "summary": "Obtained job results.",
            "value": EXAMPLES["job_results.json"],
        }
    }),
    "204": NoContentJobResultsResponse(description="success"),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_results_responses = copy(get_job_results_responses)
get_prov_results_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_exceptions_responses = {
    "200": OkGetJobExceptionsResponse(description="success", examples={
        "JobExceptions": {
            "summary": "Job exceptions that occurred during failing process execution.",
            "value": EXAMPLES["job_exceptions.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_exceptions_responses = copy(get_exceptions_responses)
get_prov_exceptions_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_logs_responses = {
    "200": OkGetJobLogsResponse(description="success", examples={
        "JobLogs": {
            "summary": "Job logs registered and captured throughout process execution.",
            "value": EXAMPLES["job_logs.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_logs_responses = copy(get_logs_responses)
get_prov_logs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_stats_responses = {
    "200": OkGetJobStatsResponse(description="success", examples={
        "JobStatistics": {
            "summary": "Job statistics collected following process execution.",
            "value": EXAMPLES["job_statistics.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_stats_responses = copy(get_stats_responses)
get_prov_stats_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_quote_list_responses = {
    "200": OkGetQuoteListResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_quote_responses = {
    "200": OkGetQuoteInfoResponse(description="success"),
    "404": NotFoundQuoteResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_quotes_responses = {
    "201": CreatedQuoteResponse(),
    "202": AcceptedQuoteResponse(),
    "400": InvalidJobParametersResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_quote_responses = {
    "201": CreatedQuoteExecuteResponse(description="success"),
    "400": InvalidJobParametersResponse(),
    "402": QuotePaymentRequiredResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_quote_estimator_responses = {
    "200": OkGetEstimatorResponse(description="success"),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
put_process_quote_estimator_responses = {
    "200": OkPutEstimatorResponse(description="success"),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_process_quote_estimator_responses = {
    "204": OkDeleteEstimatorResponse(description="success"),
    "404": NotFoundProcessResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_list_responses = {
    "200": OkGetBillListResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_responses = {
    "200": OkGetBillDetailResponse(description="success"),
    "405": MethodNotAllowedErrorResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_vault_responses = {
    "200": OkVaultFileUploadedResponse(description="success", examples={
        "VaultFileUploaded": {
            "summary": "File successfully uploaded to vault.",
            "value": EXAMPLES["vault_file_uploaded.json"],
        }
    }),
    "400": BadRequestVaultFileUploadResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "422": UnprocessableEntityVaultFileUploadResponse(),
    "500": InternalServerErrorResponseSchema(),
}
head_vault_file_responses = {
    "200": OkVaultFileDetailResponse(description="success", examples={
        "VaultFileDetails": {
            "summary": "Obtain vault file metadata.",
            "value": EXAMPLES["vault_file_head.json"],
        }
    }),
    "400": BadRequestVaultFileAccessResponse(),
    "403": ForbiddenVaultFileDownloadResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneVaultFileDownloadResponse(),
    "500": InternalServerErrorResponseSchema(),
}
get_vault_file_responses = {
    "200": OkVaultFileDownloadResponse(description="success"),
    "400": BadRequestVaultFileAccessResponse(),
    "403": ForbiddenVaultFileDownloadResponse(),
    "405": MethodNotAllowedErrorResponseSchema(),
    "410": GoneVaultFileDownloadResponse(),
    "500": InternalServerErrorResponseSchema(),
}
wps_responses = {
    "200": OkWPSResponse(examples={
        "GetCapabilities": {
            "summary": "GetCapabilities example response.",
            "value": EXAMPLES["wps_getcapabilities_response.xml"]
        },
        "DescribeProcess": {
            "summary": "DescribeProcess example response.",
            "value": EXAMPLES["wps_describeprocess_response.xml"]
        },
        "ExecuteSuccess": {
            "summary": "Successful process execute example response.",
            "value": EXAMPLES["wps_execute_response.xml"]
        },
        "ExecuteFailed": {
            "summary": "Failed process execute example response.",
            "value": EXAMPLES["wps_execute_failed_response.xml"]
        }
    }),
    "400": ErrorWPSResponse(examples={
        "MissingParameterError": {
            "summary": "Error report in case of missing request parameter.",
            "value": EXAMPLES["wps_missing_parameter_response.xml"],
        },
        "AccessForbiddenError": {
            "summary": "Error report in case of forbidden access to the service.",
            "value": EXAMPLES["wps_access_forbidden_response.xml"],
        }
    }),
    "405": ErrorWPSResponse(),
    "500": ErrorWPSResponse(),
}


#################################################################
# Utility methods
#################################################################


def service_api_route_info(service_api, settings):
    # type: (Service, SettingsType) -> ViewInfo
    """
    Automatically generates the view configuration parameters from the :mod:`cornice` service definition.

    :param service_api: cornice service with name and path definition.
    :param settings: settings to obtain the base path of the application.
    :return: view configuration parameters that can be passed directly to ``config.add_route`` call.
    """
    from weaver.wps_restapi.utils import wps_restapi_base_path  # import here to avoid circular import errors

    api_base = wps_restapi_base_path(settings)
    return {"name": service_api.name, "pattern": f"{api_base}{service_api.path}"}


def datetime_interval_parser(datetime_interval):
    # type: (str) -> DatetimeIntervalType
    """
    This function parses a given datetime or interval into a dictionary that will be easy for database process.
    """
    parsed_datetime = {}

    if datetime_interval.startswith(DATETIME_INTERVAL_OPEN_START_SYMBOL):
        datetime_interval = datetime_interval.replace(DATETIME_INTERVAL_OPEN_START_SYMBOL, "")
        parsed_datetime["before"] = date_parser.parse(datetime_interval)

    elif datetime_interval.endswith(DATETIME_INTERVAL_OPEN_END_SYMBOL):
        datetime_interval = datetime_interval.replace(DATETIME_INTERVAL_OPEN_END_SYMBOL, "")
        parsed_datetime["after"] = date_parser.parse(datetime_interval)

    elif DATETIME_INTERVAL_CLOSED_SYMBOL in datetime_interval:
        datetime_interval = datetime_interval.split(DATETIME_INTERVAL_CLOSED_SYMBOL)
        parsed_datetime["after"] = date_parser.parse(datetime_interval[0])
        parsed_datetime["before"] = date_parser.parse(datetime_interval[-1])
    else:
        parsed_datetime["match"] = date_parser.parse(datetime_interval)

    return parsed_datetime


def validate_node_schema(schema_node, cstruct):
    # type: (ExtendedMappingSchema, JSON) -> JSON
    """
    Validate a schema node defined against a reference schema within :data:`WEAVER_SCHEMA_DIR`.

    If the reference contains an anchor (e.g.: ``#/definitions/Def``), the sub-schema of that
    reference will be used for validation against the data structure.
    """
    schema_node.deserialize(cstruct)
    schema_file = schema_node._schema.replace(WEAVER_SCHEMA_URL, WEAVER_SCHEMA_DIR)
    schema_path = []
    if "#" in schema_file:
        schema_file, schema_ref = schema_file.split("#", 1)
        schema_path = [ref for ref in schema_ref.split("/") if ref]
    schema = load_file(schema_file)
    if schema_path:
        for part in schema_path:
            schema = schema[part]
    jsonschema.validate(cstruct, schema)
    return cstruct
