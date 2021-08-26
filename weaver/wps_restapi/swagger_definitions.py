"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
# pylint: disable=C0103,invalid-name

import os
from typing import TYPE_CHECKING

import yaml
from colander import DateTime, Email, OneOf, Range, Regex, drop, required
from cornice import Service
from dateutil import parser as date_parser

from weaver import __meta__
from weaver.config import WEAVER_CONFIGURATION_EMS
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_CONTROL_OPTIONS,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_OPTIONS,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_RESPONSE_OPTIONS,
    EXECUTE_TRANSMISSION_MODE_OPTIONS,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import (
    ACCEPT_LANGUAGE_EN_CA,
    ACCEPT_LANGUAGE_EN_US,
    ACCEPT_LANGUAGES,
    CONTENT_TYPE_ANY,
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_APP_XML,
    CONTENT_TYPE_TEXT_HTML,
    CONTENT_TYPE_TEXT_PLAIN,
    CONTENT_TYPE_TEXT_XML
)
from weaver.owsexceptions import OWSMissingParameterValue
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_INIT_WORKDIR,
    PACKAGE_ARRAY_BASE,
    PACKAGE_ARRAY_ITEMS,
    PACKAGE_CUSTOM_TYPES,
    PACKAGE_ENUM_BASE,
    PACKAGE_TYPE_POSSIBLE_VALUES,
    WPS_LITERAL_DATA_TYPE_NAMES
)
from weaver.sort import JOB_SORT_VALUES, QUOTE_SORT_VALUES, SORT_CREATED, SORT_ID, SORT_PROCESS
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_ACCEPTED, STATUS_COMPLIANT_OGC
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_VALUES
from weaver.wps_restapi.colander_extras import (
    AllOfKeywordSchema,
    AnyOfKeywordSchema,
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
    SchemeURL,
    SemanticVersion,
    StringRange,
    XMLObject
)
from weaver.wps_restapi.utils import wps_restapi_base_path

if TYPE_CHECKING:
    from typing import List, Optional

    from weaver.typedefs import DatetimeIntervalType, JSON, SettingsType, TypedDict

    ViewInfo = TypedDict("ViewInfo", {"name": str, "pattern": str})


API_TITLE = "Weaver REST API"
API_INFO = {
    "description": __meta__.__description__,
    "contact": {"name": __meta__.__authors__, "email": __meta__.__emails__, "url": __meta__.__source_repository__}
}
API_DOCS = {
    "description": "{} documentation".format(__meta__.__title__),
    "url": __meta__.__documentation_url__
}
DOC_URL = "{}/en/latest".format(__meta__.__documentation_url__)

CWL_VERSION = "v1.1"
CWL_REPO_URL = "https://github.com/common-workflow-language"
CWL_BASE_URL = "https://www.commonwl.org"
CWL_SPEC_URL = "{}/#Specification".format(CWL_BASE_URL)
CWL_USER_GUIDE_URL = "{}/user_guide".format(CWL_BASE_URL)
CWL_CMD_TOOL_URL = "{}/{}/CommandLineTool.html".format(CWL_BASE_URL, CWL_VERSION)
CWL_WORKFLOW_URL = "{}/{}/Workflow.html".format(CWL_BASE_URL, CWL_VERSION)
CWL_DOC_MESSAGE = (
    "Note that multiple formats are supported and not all specification variants or parameters "
    "are presented here. Please refer to official CWL documentation for more details "
    "({}).".format(CWL_BASE_URL)
)

IO_INFO_IDS = (
    "Identifier of the {first} {what}. To merge details between corresponding {first} and {second} "
    "{what} specifications, this is the value that will be used to associate them together."
)

OGC_API_REPO_URL = "https://github.com/opengeospatial/ogcapi-processes"
OGC_API_SCHEMA_URL = "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes"

DATETIME_INTERVAL_CLOSED_SYMBOL = "/"
DATETIME_INTERVAL_OPEN_START_SYMBOL = "../"
DATETIME_INTERVAL_OPEN_END_SYMBOL = "/.."

# fields ordering for generation of ProcessDescription body (shared for OGC/OLD schema format)
PROCESS_DESCRIPTION_FIELD_FIRST = [
    "id",
    "title",
    "version",
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
    "links"
]
# fields ordering for nested process definition of OLD schema format of ProcessDescription
PROCESS_DESCRIPTION_FIELD_FIRST_OLD_SCHEMA = ["process"]
PROCESS_DESCRIPTION_FIELD_AFTER_OLD_SCHEMA = ["links"]

PROCESS_IO_FIELD_FIRST = ["id", "title", "description", "minOccurs", "maxOccurs"]
PROCESS_IO_FIELD_AFTER = ["literalDataDomains", "formats", "crs", "bbox"]

PROVIDER_DESCRIPTION_FIELD_FIRST = [
    "id",
    "title",
    "version",
    "description",
    "url",
    "type",
    "public",
    "keywords",
    "metadata",
]
PROVIDER_DESCRIPTION_FIELD_AFTER = ["links"]

#########################################################
# Examples
#########################################################

# load examples by file names as keys
SCHEMA_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "examples")
EXAMPLES = {}
for name in os.listdir(SCHEMA_EXAMPLE_DIR):
    path = os.path.join(SCHEMA_EXAMPLE_DIR, name)
    ext = os.path.splitext(name)[-1]
    with open(path, "r") as f:
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
quote_service = Service(name="quote", path=quotes_service.path + "/{quote_id}")
bills_service = Service(name="bills", path="/bills")
bill_service = Service(name="bill", path=bills_service.path + "/{bill_id}")

jobs_service = Service(name="jobs", path="/jobs")
job_service = Service(name="job", path=jobs_service.path + "/{job_id}")
job_results_service = Service(name="job_results", path=job_service.path + "/results")
job_exceptions_service = Service(name="job_exceptions", path=job_service.path + "/exceptions")
job_outputs_service = Service(name="job_outputs", path=job_service.path + "/outputs")
job_inputs_service = Service(name="job_inputs", path=job_service.path + "/inputs")
job_logs_service = Service(name="job_logs", path=job_service.path + "/logs")

processes_service = Service(name="processes", path="/processes")
process_service = Service(name="process", path=processes_service.path + "/{process_id}")
process_quotes_service = Service(name="process_quotes", path=process_service.path + quotes_service.path)
process_quote_service = Service(name="process_quote", path=process_service.path + quote_service.path)
process_visibility_service = Service(name="process_visibility", path=process_service.path + "/visibility")
process_package_service = Service(name="process_package", path=process_service.path + "/package")
process_payload_service = Service(name="process_payload", path=process_service.path + "/payload")
process_jobs_service = Service(name="process_jobs", path=process_service.path + jobs_service.path)
process_job_service = Service(name="process_job", path=process_service.path + job_service.path)
process_results_service = Service(name="process_results", path=process_service.path + job_results_service.path)
process_inputs_service = Service(name="process_inputs", path=process_service.path + job_inputs_service.path)
process_outputs_service = Service(name="process_outputs", path=process_service.path + job_outputs_service.path)
process_exceptions_service = Service(name="process_exceptions", path=process_service.path + job_exceptions_service.path)
process_logs_service = Service(name="process_logs", path=process_service.path + job_logs_service.path)

process_execution_service = Service(name="process_execution", path=process_service.path + "/execution")

providers_service = Service(name="providers", path="/providers")
provider_service = Service(name="provider", path=providers_service.path + "/{provider_id}")
provider_processes_service = Service(name="provider_processes", path=provider_service.path + processes_service.path)
provider_process_service = Service(name="provider_process", path=provider_service.path + process_service.path)
provider_jobs_service = Service(name="provider_jobs", path=provider_service.path + process_jobs_service.path)
provider_job_service = Service(name="provider_job", path=provider_service.path + process_job_service.path)
provider_results_service = Service(name="provider_results", path=provider_service.path + process_results_service.path)
provider_inputs_service = Service(name="provider_inputs", path=provider_service.path + process_inputs_service.path)
provider_outputs_service = Service(name="provider_outputs", path=provider_service.path + process_outputs_service.path)
provider_logs_service = Service(name="provider_logs", path=provider_service.path + process_logs_service.path)
provider_exceptions_service = Service(name="provider_exceptions",
                                      path=provider_service.path + process_exceptions_service.path)

# backward compatibility deprecated routes
job_result_service = Service(name="job_result", path=job_service.path + "/result")
process_result_service = Service(name="process_result", path=process_service.path + job_result_service.path)
provider_result_service = Service(name="provider_result", path=provider_service.path + process_result_service.path)

#########################################################
# Generic schemas
#########################################################


class SLUG(ExtendedSchemaNode):
    schema_type = String
    description = "Slug name pattern."
    example = "some-object-slug-name"
    pattern = "^[A-Za-z0-9]+(?:(-|_)[A-Za-z0-9]+)*$"


class URL(ExtendedSchemaNode):
    schema_type = String
    description = "URL reference."
    format = "url"


class DateTimeInterval(ExtendedSchemaNode):
    schema_type = String
    description = (
        "DateTime format against OGC-API - Processes, "
        "to get values before a certain date-time use '../' before the date-time, "
        "to get values after a certain date-time use '/..' after the date-time like the example, "
        "to get values between two date-times use '/' between the date-times, "
        "to get values with a specific date-time just pass the datetime. "
    )
    example = "2022-03-02T03:32:38.487000+00:00/.."
    regex_datetime = r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(([+-]\d\d:\d\d)|Z)?)"
    regex_interval_closed = r"{i}\/{i}".format(i=regex_datetime)
    regex_interval_open_start = r"\.\.\/{}".format(regex_datetime)
    regex_interval_open_end = r"{}\/\.\.".format(regex_datetime)

    pattern = "^{}|{}|{}|{}$".format(regex_datetime, regex_interval_closed,
                                     regex_interval_open_start, regex_interval_open_end)


class S3Bucket(ExtendedSchemaNode):
    schema_type = String
    description = "S3 bucket shorthand URL representation [s3://<bucket>/<job-uuid>/<output>.ext]"
    pattern = r"^s3://\S+$"


class FileLocal(ExtendedSchemaNode):
    schema_type = String
    description = "Local file reference."
    format = "file"
    validator = Regex(r"^(file://)?(?:/|[/?]\S+)$")


class FileURL(ExtendedSchemaNode):
    schema_type = String
    description = "URL file reference."
    format = "url"
    validator = SchemeURL(schemes=["http", "https"])


class ReferenceURL(AnyOfKeywordSchema):
    _any_of = [
        FileURL(),
        FileLocal(),
        S3Bucket(),
    ]


class UUID(ExtendedSchemaNode):
    schema_type = String
    description = "Unique identifier."
    example = "a9d14bf4-84e0-449a-bac8-16e598efe807"
    format = "uuid"
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


class Version(ExtendedSchemaNode):
    # note: internally use LooseVersion, so don't be too strict about pattern
    schema_type = String
    description = "Version string."
    example = "1.2.3"
    validator = SemanticVersion()


class ContentTypeHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Content-Type"
    schema_type = String


class AcceptHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept"
    schema_type = String
    # FIXME: raise HTTPNotAcceptable in not one of those?
    validator = OneOf([
        CONTENT_TYPE_APP_JSON,
        CONTENT_TYPE_APP_XML,
        CONTENT_TYPE_TEXT_XML,
        CONTENT_TYPE_TEXT_HTML,
        CONTENT_TYPE_TEXT_PLAIN,
        CONTENT_TYPE_ANY,
    ])
    missing = drop
    default = CONTENT_TYPE_APP_JSON  # defaults to JSON for easy use within browsers


class AcceptLanguageHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept-Language"
    schema_type = String
    missing = drop
    default = ACCEPT_LANGUAGE_EN_CA
    # FIXME: oneOf validator for supported languages (?)


class JsonHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=CONTENT_TYPE_APP_JSON, default=CONTENT_TYPE_APP_JSON)


class HtmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=CONTENT_TYPE_TEXT_HTML, default=CONTENT_TYPE_TEXT_HTML)


class XmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=CONTENT_TYPE_APP_XML, default=CONTENT_TYPE_APP_XML)


class RequestContentTypeHeader(OneOfKeywordSchema):
    _one_of = [
        JsonHeader(),
        XmlHeader(),
    ]


class ResponseContentTypeHeader(OneOfKeywordSchema):
    _one_of = [
        JsonHeader(),
        XmlHeader(),
        HtmlHeader(),
    ]


class RequestHeaders(RequestContentTypeHeader):
    """Headers that can indicate how to adjust the behavior and/or result the be provided in the response."""
    accept = AcceptHeader()
    accept_language = AcceptLanguageHeader()


class ResponseHeaders(ResponseContentTypeHeader):
    """Headers describing resulting response."""


class RedirectHeaders(ResponseHeaders):
    Location = ExtendedSchemaNode(String(), example="https://job/123/result", description="Redirect resource location.")


class NoContent(ExtendedMappingSchema):
    description = "Empty response body."
    default = {}


class KeywordList(ExtendedSequenceSchema):
    keyword = ExtendedSchemaNode(String())


class Language(ExtendedSchemaNode):
    schema_type = String
    example = ACCEPT_LANGUAGE_EN_CA
    validator = OneOf(ACCEPT_LANGUAGES)


class ValueLanguage(ExtendedMappingSchema):
    lang = Language(missing=drop, description="Language of the value content.")


class LinkLanguage(ExtendedMappingSchema):
    hreflang = Language(missing=drop, description="Language of the content located at the link.")


class MetadataBase(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), missing=drop)
    title = ExtendedSchemaNode(String(), missing=drop)


class MetadataRole(ExtendedMappingSchema):
    role = URL(missing=drop)


class LinkRelationship(ExtendedMappingSchema):
    rel = SLUG(description="Relationship of the link to the current content.")


class LinkBase(LinkLanguage, MetadataBase):
    href = URL(description="Hyperlink reference.")


class Link(LinkRelationship, LinkBase):
    pass


class MetadataValue(NotKeywordSchema, ValueLanguage, MetadataBase):
    _not = [
        # make sure value metadata does not allow 'rel' and 'hreflang' reserved for link reference
        # explicitly refuse them such that when an href/rel link is provided, only link details are possible
        LinkRelationship(description="Field 'rel' must refer to a link reference with 'href'."),
        LinkLanguage(description="Field 'hreflang' must refer to a link reference with 'href'."),
    ]
    value = ExtendedSchemaNode(String(), description="Plain text value of the information.")


class MetadataContent(OneOfKeywordSchema):
    _one_of = [
        Link(title="MetadataLink"),
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
    links = LinkList()


class FormatMimeType(ExtendedMappingSchema):
    """
    Used to respect ``mimeType`` field to work with pre-existing processes.
    """
    title = "Format"
    mimeType = ExtendedSchemaNode(
        String(), default=CONTENT_TYPE_TEXT_PLAIN, example=CONTENT_TYPE_APP_JSON)
    schema = ExtendedSchemaNode(String(), missing=drop)
    encoding = ExtendedSchemaNode(String(), missing=drop)


class Format(ExtendedMappingSchema):
    """
    Used to respect ``mediaType`` field as suggested per `OGC-API`.
    """
    title = "Format"
    mediaType = ExtendedSchemaNode(String(), default=CONTENT_TYPE_TEXT_PLAIN, example=CONTENT_TYPE_APP_JSON)
    schema = ExtendedSchemaNode(String(), missing=drop)
    encoding = ExtendedSchemaNode(String(), missing=drop)


class DeployFormatDefaultMimeType(FormatMimeType, ExtendedMappingSchema):
    """
    Format for process input are assumed plain text if the MIME-type was omitted and is not
    one of the known formats by this instance. When executing a job, the best match will be used
    to run the process, and will fallback to the default as last resort.
    """
    # NOTE:
    # The default is override from FormatMimeType since the FormatSelection 'oneOf' always fails,
    # due to the 'default' value which is always generated and it causes the presence of both Format and FormatMimeType
    mimeType = ExtendedSchemaNode(String(), example=CONTENT_TYPE_APP_JSON)


class DeployFormatDefault(Format, ExtendedMappingSchema):
    """
    Format for process input are assumed plain text if the MEDIA-type was omitted and is not
    one of the known formats by this instance. When executing a job, the best match will be used
    to run the process, and will fallback to the default as last resort.
    """
    # NOTE:
    # The default is override from Format since the FormatSelection 'oneOf' always fails,
    # due to the 'default' value which is always generated and it causes the presence of both Format and FormatMimeType
    mediaType = ExtendedSchemaNode(String(), example=CONTENT_TYPE_APP_JSON)


class FormatSelection(OneOfKeywordSchema):
    """
    Validation against ``mimeType`` or ``mediaType`` format.

    .. seealso::
        - :class:`DeployFormatDefault`
        - :class:`DeployFormatDefaultMimeType`

    .. note::
        Format are validated to be retro-compatible with pre-existing/deployed/remote processes.
    """
    _one_of = [
        DeployFormatDefault(),
        DeployFormatDefaultMimeType()
    ]


class FormatExtra(ExtendedMappingSchema):
    maximumMegabytes = ExtendedSchemaNode(Integer(), missing=drop)


class FormatDefault(ExtendedMappingSchema):
    default = ExtendedSchemaNode(
        Boolean(), missing=drop, default=False,
        description=(
            "Indicates if this format should be considered as the default one in case none of the other "
            "allowed or supported formats was matched nor provided as input during job submission."
        )
    )


class DescriptionFormat(Format, FormatExtra, FormatDefault):
    # NOTE:
    #  The 'OGC-API' suggest to use 'mediaType' field for FormatType, but retro-compatibility is supported,
    #  FormatType can be with either old 'mimeType' or new 'mediaType' during deployment,
    #  but only 'mediaType' is used for description
    pass


class DeploymentFormat(FormatSelection, FormatExtra, FormatDefault):
    # NOTE:
    #  The 'OGC-API' suggest to use 'mediaType' field for FormatType, but retro-compatibility is supported,
    #  FormatType can be with either old 'mimeType' or new 'mediaType' during deployment,
    #  but only 'mediaType' is used for description
    pass


class FormatMedia(FormatExtra):
    """Format employed for reference results respecting 'OGC-API - Processes' schemas."""
    schema_ref = "{}/master/core/openapi/schemas/formatDescription.yaml".format(OGC_API_SCHEMA_URL)
    mediaType = ExtendedSchemaNode(String())
    schema = ExtendedSchemaNode(String(), missing=drop)
    encoding = ExtendedSchemaNode(String(), missing=drop)


class DescriptionFormatList(ExtendedSequenceSchema):
    format = DescriptionFormat()


class DeploymentFormatList(ExtendedSequenceSchema):
    format = DeploymentFormat()


class AdditionalParameterValuesList(ExtendedSequenceSchema):
    values = ExtendedSchemaNode(String())


class AdditionalParameter(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    values = AdditionalParameterValuesList()


class AdditionalParameterList(ExtendedSequenceSchema):
    additionalParameter = AdditionalParameter()


class AdditionalParametersMeta(LinkBase, MetadataRole):
    pass


class AdditionalParameters(ExtendedMappingSchema):
    parameters = AdditionalParameterList()


class AdditionalParametersItem(AnyOfKeywordSchema):
    _any_of = [
        AdditionalParametersMeta(missind=drop),
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


class DeployDescriptionType(DescriptionType):
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
        super(InputOutputDescriptionMeta, self).__init__(*args, **kwargs)
        for child in self.children:
            if child.name in ["keywords", "metadata"]:
                child.missing = drop


class MinOccursDefinition(OneOfKeywordSchema):
    description = "Minimum amount of values required for this input."
    title = "MinOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0),
                           description="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$",
                           description="Numerical string representing a positive integer."),
    ]


class MaxOccursDefinition(OneOfKeywordSchema):
    description = "Maximum amount of values allowed for this input."
    title = "MaxOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0),
                           description="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$",
                           description="Numerical string representing a positive integer."),
        ExtendedSchemaNode(String(), validator=OneOf(["unbounded"])),
    ]


class WithMinMaxOccurs(ExtendedMappingSchema):
    minOccurs = MinOccursDefinition(missing=drop)
    maxOccurs = MaxOccursDefinition(missing=drop)


# does not inherit from 'DescriptionLinks' because other 'ProcessDescription<>' schema depend from this without 'links'
class ProcessDescriptionType(DescriptionBase, DescriptionExtra):
    id = ProcessIdentifier()
    version = Version(missing=drop)


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


class LiteralReference(ExtendedMappingSchema):
    reference = ReferenceURL()


class NameReferenceType(ExtendedMappingSchema):
    schema_ref = "{}/master/core/openapi/schemas/nameReferenceType.yaml".format(OGC_API_SCHEMA_URL)
    name = ExtendedSchemaNode(String())
    reference = ReferenceURL(missing=drop)


class DataTypeSchema(NameReferenceType):
    description = "Type of the literal data representation."
    title = "DataType"
    # any named type that can be converted by: 'weaver.processes.convert.any2wps_literal_datatype'
    name = ExtendedSchemaNode(String(), validator=OneOf(list(WPS_LITERAL_DATA_TYPE_NAMES)))


class UomSchema(NameReferenceType):
    title = "UnitOfMeasure"


class AllowedValuesList(ExtendedSequenceSchema):
    allowedValues = ExtendedSchemaNode(String())


class AllowedValues(ExtendedMappingSchema):
    """
    Allows string values (enum).
    """
    allowedValues = AllowedValuesList()


class AllowedRange(ExtendedMappingSchema):
    minimumValue = ExtendedSchemaNode(String(), missing=drop)
    maximumValue = ExtendedSchemaNode(String(), missing=drop)
    spacing = ExtendedSchemaNode(String(), missing=drop)
    rangeClosure = ExtendedSchemaNode(String(), missing=drop,
                                      validator=OneOf(["closed", "open", "open-closed", "closed-open"]))


class AllowedRangesList(ExtendedSequenceSchema):
    allowedRanges = AllowedRange()


class AllowedRanges(ExtendedMappingSchema):
    allowedRanges = AllowedRangesList()


class AnyValue(ExtendedMappingSchema):
    anyValue = ExtendedSchemaNode(Boolean(), missing=drop, default=True)


class ValuesReference(ReferenceURL):
    """
    URL where to retrieve applicable values.
    """


class AnyLiteralType(OneOfKeywordSchema):
    """
    .. seealso::
        - :class:`AnyLiteralDataType`
        - :class:`AnyLiteralValueType`
        - :class:`AnyLiteralDefaultType`
    """
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(Boolean()),
        ExtendedSchemaNode(String()),
    ]


class SequenceStringType(ExtendedSequenceSchema):
    value = ExtendedSchemaNode(String())


class SequenceBooleanType(ExtendedSequenceSchema):
    value = ExtendedSchemaNode(Boolean())


class SequenceNumberType(ExtendedSequenceSchema):
    value = ExtendedSchemaNode(Float())


class ArrayLiteralType(OneOfKeywordSchema):
    _one_of = [
        SequenceNumberType(),
        SequenceBooleanType(),
        SequenceStringType()
    ]


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


class LiteralDataDomainDefinition(ExtendedMappingSchema):
    default = AnyLiteralDefaultType()
    defaultValue = ExtendedSchemaNode(String(), missing=drop)
    dataType = DataTypeSchema(missing=drop)
    uom = UomSchema(missing=drop)


class LiteralDataValueDefinition(OneOfKeywordSchema):
    _one_of = [
        AllowedValues,
        AllowedRanges,
        ValuesReference,
        AnyValue,  # must be last because it's the most permissive (always valid, default)
    ]


class LiteralDataDomainConstraints(LiteralDataDomainDefinition):
    valueDefinition = LiteralDataValueDefinition()


class LiteralDataDomainList(ExtendedSequenceSchema):
    """
    Constraints that apply to the literal data values.
    """
    literalDataDomain = LiteralDataDomainConstraints()


class LiteralInputType(NotKeywordSchema, ExtendedMappingSchema):
    _not = [
        DescribeWithFormats,
    ]
    literalDataDomains = LiteralDataDomainList(missing=drop)


class DescribeInputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process description definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        DescribeComplexInputType,  # should be 2nd to last because very permissive, but requires format at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    ]


class DeployInputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process deployment definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        DeployComplexInputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    ]


class DescribeInputType(AllOfKeywordSchema):
    _all_of = [
        DescriptionType(),
        InputOutputDescriptionMeta(),
        DescribeInputTypeDefinition(),
        WithMinMaxOccurs(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DescribeInputTypeWithID(InputIdentifierType, DescribeInputType):
    pass


# Different definition than 'Describe' such that nested 'complex' type 'formats' can be validated and backward
# compatible with pre-existing/deployed/remote processes, with either ``mediaType`` and ``mimeType`` formats.
class DeployInputType(AllOfKeywordSchema):
    _all_of = [
        DeployDescriptionType(),
        InputOutputDescriptionMeta(),
        DeployInputTypeDefinition(),
        WithMinMaxOccurs(),
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
        variable="<input-id>",
        description="Input definition under mapping of process description.",
        missing=drop,  # allowed because process can have empty inputs (see schema: ProcessDescriptionOGC)
    )


# for [{id: "", ...}] representation within ProcessDeployment (OLD schema)
class DeployInputTypeList(ExtendedSequenceSchema):
    """
    Listing of process input definitions to deploy.
    """
    input = DeployInputTypeWithID()


# for {"<id>": {...}} representation within ProcessDeployment (OGC schema)
class DeployInputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process inputs under mapping.
    """
    input_id = DeployInputType(
        variable="<input-id>",
        description="Input definition under mapping of process deployment."
    )


class DeployInputTypeAny(OneOfKeywordSchema):
    _one_of = [
        DeployInputTypeList,
        DeployInputTypeMap,
    ]


class LiteralOutputType(NotKeywordSchema, ExtendedMappingSchema):
    _not = [
        DescribeWithFormats,
    ]
    literalDataDomains = LiteralDataDomainList(missing=drop)


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
        variable="<output-id>", title="ProcessOutputDefinition",
        description="Output definition under mapping of process description."
    )


# Different definition than 'Describe' such that nested 'complex' type 'formats' can be validated and backward
# compatible with pre-existing/deployed/remote processes, with either ``mediaType`` and ``mimeType`` formats.
class DeployOutputType(AllOfKeywordSchema):
    _all_of = [
        DeployDescriptionType(),
        InputOutputDescriptionMeta(),
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
        variable="<input-id>",
        description="Output definition under mapping of process deployment."
    )


class DeployOutputTypeAny(OneOfKeywordSchema):
    _one_of = [
        DeployOutputTypeList,
        DeployOutputTypeMap,
    ]


class JobExecuteModeEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobExecuteMode"
    # no default to enforce required input as per OGC-API schemas
    # https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/execute.yaml
    # default = EXECUTE_MODE_AUTO
    example = EXECUTE_MODE_ASYNC
    validator = OneOf(EXECUTE_MODE_OPTIONS)


class JobControlOptionsEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobControlOptions"
    default = EXECUTE_CONTROL_OPTION_ASYNC
    example = EXECUTE_CONTROL_OPTION_ASYNC
    validator = OneOf(EXECUTE_CONTROL_OPTIONS)


class JobResponseOptionsEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobResponseOptions"
    # no default to enforce required input as per OGC-API schemas
    # https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/execute.yaml
    # default = EXECUTE_RESPONSE_DOCUMENT
    example = EXECUTE_RESPONSE_DOCUMENT
    validator = OneOf(EXECUTE_RESPONSE_OPTIONS)


class TransmissionModeEnum(ExtendedSchemaNode):
    schema_type = String
    title = "TransmissionMode"
    default = EXECUTE_TRANSMISSION_MODE_REFERENCE
    example = EXECUTE_TRANSMISSION_MODE_REFERENCE
    validator = OneOf(EXECUTE_TRANSMISSION_MODE_OPTIONS)


class JobStatusEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobStatus"
    default = STATUS_ACCEPTED
    example = STATUS_ACCEPTED
    validator = OneOf(JOB_STATUS_CATEGORIES[STATUS_COMPLIANT_OGC])


class JobSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobSortingMethod"
    default = SORT_CREATED
    example = SORT_CREATED
    validator = OneOf(JOB_SORT_VALUES)


class QuoteSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "QuoteSortingMethod"
    default = SORT_ID
    example = SORT_PROCESS
    validator = OneOf(QUOTE_SORT_VALUES)


class LaunchJobQuerystring(ExtendedMappingSchema):
    tags = ExtendedSchemaNode(String(), title="JobTags", default=None, missing=drop,
                              description="Comma separated tags that can be used to filter jobs later")


class VisibilityValue(ExtendedSchemaNode):
    schema_type = String
    validator = OneOf(VISIBILITY_VALUES)
    example = VISIBILITY_PUBLIC


class JobAccess(VisibilityValue):
    pass


class Visibility(ExtendedMappingSchema):
    value = VisibilityValue()


#########################################################
# Path parameter definitions
#########################################################


class ProcessPath(ExtendedMappingSchema):
    # FIXME: support versioning with <id:tag> (https://github.com/crim-ca/weaver/issues/107)
    process_id = AnyIdentifier(description="Process identifier.", example="jsonarray2netcdf")


class ProviderPath(ExtendedMappingSchema):
    provider_id = AnyIdentifier(description="Remote provider identifier.", example="hummingbird")


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


class ConformanceEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class OpenAPIEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


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
    example = CONTENT_TYPE_APP_JSON


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
    default = ACCEPT_LANGUAGE_EN_US
    example = ACCEPT_LANGUAGE_EN_CA


class OWSLanguageAttribute(OWSLanguage):
    description = "RFC-4646 language code of the human-readable text."
    name = "language"
    attribute = True


class OWSService(ExtendedSchemaNode, OWSNamespace):
    description = "Desired service to produce the response (SHOULD be 'WPS')."
    schema_type = String
    name = "service"
    attribute = True
    default = ACCEPT_LANGUAGE_EN_US
    example = ACCEPT_LANGUAGE_EN_CA


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
    default = ACCEPT_LANGUAGE_EN_US
    example = ACCEPT_LANGUAGE_EN_CA


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
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/RequestBaseType.xsd"
    accepted_versions = OWSAcceptVersions(missing=drop, default="1.0.0")
    language = OWSLanguageAttribute(missing=drop)
    service = OWSService()


class WPSGetCapabilitiesPost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_request.xsd"
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
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_request.xsd"
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
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"
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
    position = OWSString(name="PositionName", title="OWSPositionName", example="One Man Team", missing=drop)
    contact = OWSContactInfo(missing=drop, default={})


class OWSServiceProvider(ExtendedMappingSchema, OWSNamespace):
    description = "Details about the institution providing the service."
    name = "ServiceProvider"
    title = "ServiceProvider"
    provider_name = OWSString(name="ProviderName", title="OWSProviderName", example="EXAMPLE")
    provider_site = OWSString(name="ProviderName", title="OWSProviderName", example="http://schema-example.com")
    contact = OWSServiceContact(required=False, defalult={})


class WPSDescriptionType(ExtendedMappingSchema, OWSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/DescriptionType.xsd"
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


class OWS_HTTP(ExtendedMappingSchema, OWSNamespace):
    get = OperationRequest(name="Get", title="OWSGet")
    post = OperationRequest(name="Post", title="OWSPost")


class OWS_DCP(ExtendedMappingSchema, OWSNamespace):
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
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/ResponseBaseType.xsd"
    service = WPSServiceAttribute()
    version = WPSVersionAttribute()
    lang = WPSLanguageAttribute()


class WPSProcessVersion(ExtendedSchemaNode, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/ProcessVersion.xsd"
    schema_type = String
    description = "Release version of this Process."
    name = "processVersion"
    attribute = True


class WPSInputDescriptionType(WPSDescriptionType):
    identifier = OWSIdentifier(description="Unique identifier of the input.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human readable representation of the process input.")
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
    mime_type = XMLString(name="MimeType", default=CONTENT_TYPE_TEXT_PLAIN, example=CONTENT_TYPE_TEXT_PLAIN)
    encoding = XMLString(name="Encoding", missing=drop, example="base64")
    schema = XMLString(name="Schema", missing=drop)


class WPSFileFormat(ExtendedMappingSchema, XMLObject):
    name = "Format"
    format = WPSFormatDefinition()


class WPSFormatList(ExtendedSequenceSchema):
    format = WPSFileFormat()


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
    _title = OWSTitle(description="Human readable representation of the process output.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class ProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSOutputDescriptionType()


class WPSGetCapabilities(WPSResponseBaseType):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_response.xsd"
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
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_response.xsd"
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
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_response.xsd"
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


class ProcessDescriptionSchemaQuery(ExtendedMappingSchema):
    # see: 'ProcessDescription' schema and 'Process.offering' method
    schema = ExtendedSchemaNode(
        String(), example="OGC", default="OGC", validator=OneOfCaseInsensitive(["OGC", "OLD"]),
        description="Selects the desired schema representation of the process description."
    )


class ProviderProcessEndpoint(ProviderPath, ProcessPath):
    header = RequestHeaders()
    querystring = ProcessDescriptionSchemaQuery()


class ProcessEndpoint(ProcessPath):
    header = RequestHeaders()
    querystring = ProcessDescriptionSchemaQuery()


class ProcessPackageEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessPayloadEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityGetEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityPutEndpoint(ProcessPath):
    header = RequestHeaders()
    body = Visibility()


class ProviderJobEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobEndpoint(JobPath):
    header = RequestHeaders()


class ProcessInputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderInputsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobInputsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessOutputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderOutputsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobOutputsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessResultEndpoint(ProcessOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProviderResultEndpoint(ProviderOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class JobResultEndpoint(JobOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProcessResultsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderExceptionsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobExceptionsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessExceptionsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderLogsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobLogsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessLogsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class ProviderPublic(ExtendedMappingSchema):
    public = ExtendedSchemaNode(
        Boolean(),
        description="Whether the service is defined as publicly visible. "
                    "This will not control allowance/denial of requests to the registered endpoint of the service. "
                    "It only indicates if it should appear during listing of providers."
    )


class CreateProviderRequestBody(ProviderPublic):
    id = AnyIdentifier()
    url = URL(description="Endpoint where to query the provider.")


class InputDataType(InputIdentifierType):
    pass


class OutputDataType(OutputIdentifierType):
    format = Format(missing=drop)


class ExecuteOutputDefinition(OutputDataType):
    transmissionMode = TransmissionModeEnum(missing=drop)


class ExecuteOutputFilterList(ExtendedSequenceSchema):
    """
    Filter list of outputs to be obtained from execution.
    """
    # FIXME:
    #   nothing done with this currently... execution just generates all outputs anyway
    #   useful only in for limiting reported outputs in 'sync' mode that should reply after only with those specified
    output = ExecuteOutputDefinition()


class ProviderSummarySchema(DescriptionType, ProviderPublic, DescriptionMeta, DescriptionLinks):
    """
    Service provider summary definition.
    """
    id = AnyIdentifier()
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
    jobControlOptions = JobControlOptionsList(missing=[EXECUTE_CONTROL_OPTION_ASYNC],
                                              default=[EXECUTE_CONTROL_OPTION_ASYNC])
    outputTransmission = TransmissionModeList(missing=[EXECUTE_TRANSMISSION_MODE_REFERENCE],
                                              default=[EXECUTE_TRANSMISSION_MODE_REFERENCE])


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
    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessSummaryList(ExtendedSequenceSchema):
    summary = ProcessSummary()


class ProcessCollection(ExtendedMappingSchema):
    processes = ProcessSummaryList()
    links = LinkList(missing=drop)


class ProcessVisibility(ExtendedMappingSchema):
    visibility = VisibilityValue(missing=drop)


class Process(
    # following are like 'ProcessSummary',
    # except without 'ProcessControl' and 'DescriptionLinks' that are outside of nested 'process'
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


class ProcessDescriptionOLD(ProcessControl, DescriptionLinks):
    """
    Old schema for process description.
    """
    deprecated = True
    process = Process()

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST_OLD_SCHEMA
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER_OLD_SCHEMA


class ProcessDescriptionOGC(ProcessSummary, ProcessContext, ProcessVisibility, ProcessLocations, DescriptionLinks):
    """
    OGC-API schema for process description.
    """
    # technically, empty inputs are allowed for processes that should generate constant/randomized outputs
    # example:
    #   https://pavics.ouranos.ca/twitcher/ows/proxy/catalog
    #   ?service=WPS&request=DescribeProcess&version=1.0.0&identifier=pavicstestdocs
    inputs = DescribeInputTypeMap(description="Inputs definition of the process.", missing=drop, default={})
    outputs = DescribeOutputTypeMap(description="Outputs definition of the process.")

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
                    "overrides (see '{}/package.html#correspondence-between-cwl-and-wps-fields')".format(DOC_URL))
    outputs = DeployOutputTypeAny(
        missing=drop, title="DeploymentOutputs",
        description="Additional definitions for process outputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    "overrides (see '{}/package.html#correspondence-between-cwl-and-wps-fields')".format(DOC_URL))
    visibility = VisibilityValue(missing=drop)


class JobStatusInfo(ExtendedMappingSchema):
    jobID = UUID(example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the job.")
    status = JobStatusEnum(description="Last updated status.")
    message = ExtendedSchemaNode(String(), missing=drop, description="Information about the last status update.")
    created = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process execution job was created.")
    started = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process started execution if applicable.")
    finished = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                  description="Timestamp when the process completed execution if applicable.")
    # note: using String instead of Time because timedelta object cannot be directly handled (missing parts at parsing)
    duration = ExtendedSchemaNode(String(), missing=drop,
                                  description="Duration since the start of the process execution.")
    runningSeconds = ExtendedSchemaNode(Integer(), missing=drop,
                                        description="Duration in seconds since the start of the process execution.")
    expirationDate = ExtendedSchemaNode(DateTime(), missing=drop,
                                        description="Timestamp when the job will be canceled if not yet completed.")
    estimatedCompletion = ExtendedSchemaNode(DateTime(), missing=drop)
    nextPoll = ExtendedSchemaNode(DateTime(), missing=drop,
                                  description="Timestamp when the job will prompted for updated status details.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0, validator=Range(min=0, max=100),
                                          description="Completion percentage of the job as indicated by the process.")
    links = LinkList(missing=drop)


class JobEntrySchema(OneOfKeywordSchema):
    # note:
    #   Since JobID is a simple string (not a dict), no additional mapping field can be added here.
    #   They will be discarded by `OneOfKeywordSchema.deserialize()`.
    _one_of = [
        JobStatusInfo,
        ExtendedSchemaNode(String(), description="Job ID."),
    ]


class JobCollection(ExtendedSequenceSchema):
    item = JobEntrySchema()


class CreatedJobStatusSchema(ExtendedMappingSchema):
    status = ExtendedSchemaNode(String(), example=STATUS_ACCEPTED)
    location = ExtendedSchemaNode(String(), example="http://{host}/weaver/processes/{my-process-id}/jobs/{my-job-id}")
    jobID = UUID(description="ID of the created job.")


class CreatedQuotedJobStatusSchema(CreatedJobStatusSchema):
    bill = UUID(description="ID of the created bill.")


class GetPagingJobsSchema(ExtendedMappingSchema):
    jobs = JobCollection()
    limit = ExtendedSchemaNode(Integer(), missing=10, default=10, validator=Range(min=0, max=10000))
    page = ExtendedSchemaNode(Integer(), validator=Range(min=0))


class JobCategoryFilters(PermissiveMappingSchema):
    category = ExtendedSchemaNode(String(), title="CategoryFilter", variable="<category>", default=None, missing=None,
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
        GetPagingJobsSchema,
        GetGroupedJobsSchema,
    ]
    total = ExtendedSchemaNode(Integer(),
                               description="Total number of matched jobs regardless of grouping or paging result.")


class DismissedJobSchema(ExtendedMappingSchema):
    status = JobStatusEnum()
    jobID = UUID(description="ID of the job.")
    message = ExtendedSchemaNode(String(), example="Job dismissed.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0)


class QuoteProcessParametersSchema(ExtendedMappingSchema):
    inputs = DescribeInputTypeList(missing=drop)
    outputs = DescribeOutputTypeList(missing=drop)
    mode = JobExecuteModeEnum()
    response = JobResponseOptionsEnum()


class AlternateQuotation(ExtendedMappingSchema):
    id = UUID(description="Quote ID.")
    title = ExtendedSchemaNode(String(), description="Name of the quotation.", missing=drop)
    description = ExtendedSchemaNode(String(), description="Description of the quotation.", missing=drop)
    price = ExtendedSchemaNode(Float(), description="Process execution price.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.")
    expire = ExtendedSchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    details = ExtendedSchemaNode(String(), description="Details of the quotation.", missing=drop)
    estimatedTime = ExtendedSchemaNode(String(), description="Estimated process execution duration.", missing=drop)


class AlternateQuotationList(ExtendedSequenceSchema):
    step = AlternateQuotation(description="Quote of a workflow step process.")


# same as base Format, but for process/job responses instead of process submission
# (ie: 'Format' is for allowed/supported formats, this is the result format)
class DataEncodingAttributes(FormatSelection):
    pass


class Reference(ExtendedMappingSchema):
    title = "Reference"
    href = ReferenceURL(description="Endpoint of the reference.")
    format = DataEncodingAttributes(missing=drop)
    body = ExtendedSchemaNode(String(), missing=drop)
    bodyReference = ReferenceURL(missing=drop)


class ArrayReference(ExtendedSequenceSchema):
    item = Reference()


class ArrayReferenceValueType(ExtendedMappingSchema):
    value = ArrayReference()


class AnyType(OneOfKeywordSchema):
    """Permissive variants that we attempt to parse automatically."""
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
        Reference()
    ]


class ExecuteInput(InputDataType, AnyType):
    """
    Default value to be looked for uses key 'value' to conform to OGC API standard.
    We still look for 'href', 'data' and 'reference' to remain back-compatible.
    """


class ExecuteInputString(ExtendedSchemaNode):
    schema_type = String
    title = "String input"
    description = "Execute input string definition."
    example = "This is a string"


class ExecuteInputInteger(ExtendedSchemaNode):
    schema_type = Integer
    title = "Integer input"
    description = "Execute input integer definition."
    example = 8


class ExecuteInputFloat(ExtendedSchemaNode):
    schema_type = Float
    title = "Float input"
    description = "Execute input float definition."
    example = 2.45


class ExecuteInputTypes(OneOfKeywordSchema):
    title = "Execute inputs types"
    description = "Execute input supported types."
    _one_of = [
        ExecuteInputInteger(summary="Execute input integer value."),
        ExecuteInputFloat(summary="Execute input float value."),
        ExecuteInputString(summary="Execute input string value")
    ]


class ExecuteInputValue(OneOfKeywordSchema):
    _one_of = [
        ExecuteInputTypes(),
        ExtendedMappingSchema()
    ]


class ExecuteInputObject(PermissiveMappingSchema):
    value = ExecuteInputValue(variable="<input-id>")
    inputBinding = ExtendedMappingSchema(missing=drop, title="Input Binding",
                                         description="Defines how to specify the input for the command.")


class ExecuteInputListValues(ExtendedSequenceSchema):
    description = "List of allowed direct Execute values."
    items = ExecuteInputTypes()


class ExecuteInputDict(OneOfKeywordSchema):
    description = "Execute type definition of the input."
    _one_of = [
        ExecuteInputTypes(variable="<input-id>"),
        ExecuteInputListValues(summary="Execute input list."),
        ExecuteInputObject(summary="Execute input value definition with parameters."),
    ]


class ExecuteInputMap(PermissiveMappingSchema):
    input_id = ExecuteInputDict(variable="<input-id>", title="ExecuteInputIdentifier",
                                description="Received mapping input definition during job submission.")


class ExecuteInputList(ExtendedSequenceSchema):
    input_item = ExecuteInput(missing=drop, description="Received list input definition during job submission.")


class ExecuteInputsDefinition(OneOfKeywordSchema):
    _one_of = [
        ExecuteInputList(missing=drop, description="Package inputs defined as items."),
        ExecuteInputMap(description="Package inputs defined as mapping."),
    ]


class Execute(ExtendedMappingSchema):
    # permit unspecified inputs for processes that could technically allow no-inputs definition (CWL),
    # but very unlikely/unusual in real world scenarios (possible case: constant endpoint fetcher?)
    inputs = ExecuteInputsDefinition(missing=drop)
    outputs = ExecuteOutputFilterList()
    mode = JobExecuteModeEnum()
    notification_email = ExtendedSchemaNode(
        String(),
        missing=drop,
        validator=Email(),
        description="Optionally send a notification email when the job is done.")
    response = JobResponseOptionsEnum()


class Quotation(ExtendedMappingSchema):
    id = UUID(description="Quote ID.")
    title = ExtendedSchemaNode(String(), description="Name of the quotation.", missing=drop)
    description = ExtendedSchemaNode(String(), description="Description of the quotation.", missing=drop)
    processId = UUID(description="Corresponding process ID.")
    price = ExtendedSchemaNode(Float(), description="Process execution price.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.")
    expire = ExtendedSchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    userId = UUID(description="User id that requested the quote.")
    details = ExtendedSchemaNode(String(), description="Details of the quotation.", missing=drop)
    estimatedTime = ExtendedSchemaNode(DateTime(), missing=drop,
                                       description="Estimated duration of the process execution.")
    processParameters = Execute(title="ProcessExecuteParameters")
    alternativeQuotations = AlternateQuotationList(missing=drop)


class QuoteProcessListSchema(ExtendedSequenceSchema):
    step = Quotation(description="Quote of a workflow step process.")


class QuoteSchema(ExtendedMappingSchema):
    id = UUID(description="Quote ID.")
    process = AnyIdentifier(description="Corresponding process ID.")
    steps = QuoteProcessListSchema(description="Child processes and prices.")
    total = ExtendedSchemaNode(Float(), description="Total of the quote including step processes.")


class QuotationList(ExtendedSequenceSchema):
    quote = ExtendedSchemaNode(String(), description="Quote ID.")


class QuotationListSchema(ExtendedMappingSchema):
    quotations = QuotationList()


class BillSchema(ExtendedMappingSchema):
    id = UUID(description="Bill ID.")
    title = ExtendedSchemaNode(String(), description="Name of the bill.")
    description = ExtendedSchemaNode(String(), missing=drop)
    price = ExtendedSchemaNode(Float(), description="Price associated to the bill.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the bill in ISO-8601 format.")
    userId = ExtendedSchemaNode(Integer(), description="User id that requested the quote.")
    quotationId = UUID(description="Corresponding quote ID.", missing=drop)


class BillList(ExtendedSequenceSchema):
    bill = ExtendedSchemaNode(String(), description="Bill ID.")


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


class RequirementClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "RequirementClass"
    schema_type = String
    description = "CWL requirement class specification."


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
    description = (
        "Docker requirement with GPU-enabled support (https://github.com/NVIDIA/nvidia-docker). "
        "The instance must have the NVIDIA toolkit installed to use this feature."
    )


class DockerGpuRequirementMap(ExtendedMappingSchema):
    req = DockerGpuRequirementSpecification(name=CWL_REQUIREMENT_APP_DOCKER_GPU)


class DockerGpuRequirementClass(DockerGpuRequirementSpecification):
    title = CWL_REQUIREMENT_APP_DOCKER_GPU
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER_GPU, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER_GPU]))


class DirectoryListing(PermissiveMappingSchema):
    entry = ExtendedSchemaNode(String(), missing=drop)


class InitialWorkDirListing(ExtendedSequenceSchema):
    listing = DirectoryListing()


class InitialWorkDirRequirementSpecification(PermissiveMappingSchema):
    listing = InitialWorkDirListing()


class InitialWorkDirRequirementMap(ExtendedMappingSchema):
    req = InitialWorkDirRequirementSpecification(name=CWL_REQUIREMENT_INIT_WORKDIR)


class InitialWorkDirRequirementClass(InitialWorkDirRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_INIT_WORKDIR,
                              validator=OneOf([CWL_REQUIREMENT_INIT_WORKDIR]))


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


class ESGF_CWT_RequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_ESGF_CWT
    description = (
        "Hint indicating that the Application Package corresponds to an ESGF-CWT provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote ESGF-CWT provider.")
    provider = AnyIdentifier(description="ESGF-CWT provider endpoint.")


class ESGF_CWT_RequirementMap(ExtendedMappingSchema):
    req = ESGF_CWT_RequirementSpecification(name=CWL_REQUIREMENT_APP_ESGF_CWT)


class ESGF_CWT_RequirementClass(ESGF_CWT_RequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_ESGF_CWT, validator=OneOf([CWL_REQUIREMENT_APP_ESGF_CWT]))


class WPS1RequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_WPS1
    description = (
        "Hint indicating that the Application Package corresponds to a WPS-1 provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote WPS provider.")
    provider = AnyIdentifier(description="WPS provider endpoint.")


class WPS1RequirementMap(ExtendedMappingSchema):
    req = WPS1RequirementSpecification(name=CWL_REQUIREMENT_APP_WPS1)


class WPS1RequirementClass(WPS1RequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_WPS1, validator=OneOf([CWL_REQUIREMENT_APP_WPS1]))


class UnknownRequirementClass(PermissiveMappingSchema):
    _class = RequirementClass(example="UnknownRequirement")


class CWLRequirementsMap(AnyOfKeywordSchema):
    _any_of = [
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        PermissiveMappingSchema(missing=drop),
    ]


class CWLRequirementsItem(OneOfKeywordSchema):
    _one_of = [
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
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
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        ESGF_CWT_RequirementMap(missing=drop),
        WPS1RequirementMap(missing=drop),
    ]


class CWLHintsItem(OneOfKeywordSchema, PermissiveMappingSchema):
    # validators of individual requirements define which one applies
    # in case of ambiguity, 'discriminator' distinguish between them using their 'example' values in 'class' field
    discriminator = "class"
    _one_of = [
        BuiltinRequirementClass(missing=drop),
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        ESGF_CWT_RequirementClass(missing=drop),
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
    # in this case it is ok to use 'name' because target fields receiving it will
    # cause issues against builtin 'type' of Python reserved keyword
    title = "Type"
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
    inputBinding = ExtendedMappingSchema(missing=drop, title="Input Binding",
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
    input_id = CWLInputType(variable="<input-id>", title="CWLInputIdentifierType",
                            description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input") +
                            " (Note: '<input-id>' is a variable corresponding for each identifier)")


class CWLInputItem(CWLInputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input"))


class CWLInputList(ExtendedSequenceSchema):
    input = CWLInputItem(title="Input", description="Input specification. " + CWL_DOC_MESSAGE)


class CWLInputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLInputList(description="Package inputs defined as items."),
        CWLInputMap(description="Package inputs defined as mapping."),
    ]


class OutputBinding(PermissiveMappingSchema):
    glob = ExtendedSchemaNode(String(), missing=drop,
                              description="Glob pattern the will find the output on disk or mounted docker volume.")


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
    output_id = CWLOutputType(variable="<output-id>", title="CWLOutputIdentifierType",
                              description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output") +
                              " (Note: '<output-id>' is a variable corresponding for each identifier)")


class CWLOutputItem(CWLOutputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output"))


class CWLOutputList(ExtendedSequenceSchema):
    input = CWLOutputItem(description="Output specification. " + CWL_DOC_MESSAGE)


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


class CWL(PermissiveMappingSchema):
    cwlVersion = CWLVersion()
    _class = CWLClass()
    requirements = CWLRequirements(description="Explicit requirement to execute the application package.", missing=drop)
    hints = CWLHints(description="Non-failing additional hints that can help resolve extra requirements.", missing=drop)
    baseCommand = CWLCommand(description="Command called in the docker image or on shell according to requirements "
                                         "and hints specifications. Can be omitted if already defined in the "
                                         "docker image.", missing=drop)
    arguments = CWLArguments(description="Base arguments passed to the command.", missing=drop)
    inputs = CWLInputsDefinition(description="All inputs available to the Application Package.")
    outputs = CWLOutputsDefinition(description="All outputs produced by the Application Package.")


class Unit(ExtendedMappingSchema):
    unit = CWL(description="Execution unit definition as CWL package specification. " + CWL_DOC_MESSAGE)


class UndeploymentResult(ExtendedMappingSchema):
    id = AnyIdentifier()


class DeploymentResult(ExtendedMappingSchema):
    processSummary = ProcessSummary()


class ProvidersListSchema(ExtendedSequenceSchema):
    provider_service = ProviderSummarySchema()


class ProviderNamesSchema(ExtendedSequenceSchema):
    provider_name = AnyIdentifier()


class ProviderListing(OneOfKeywordSchema):
    _one_of = [
        ProvidersListSchema(description="Listing of provider summary details retrieved from remote service."),
        ProviderNamesSchema(description="Listing of provider names, possibly unvalidated from remote service."),
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


class JobOutputValue(OneOfKeywordSchema):
    _one_of = [
        Reference(tilte="JobOutputReference"),
        AnyLiteralDataType(title="JobOutputLiteral")
    ]


class JobOutput(AllOfKeywordSchema):
    _all_of = [
        OutputDataType(),
        JobOutputValue(),
    ]


class JobOutputList(ExtendedSequenceSchema):
    title = "JobOutputList"
    output = JobOutput(description="Job output result with specific keyword according to represented format.")


# implement only literal part of:
#   https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/inlineOrRefData.yaml
class ResultLiteral(AnyLiteralValueType, LiteralDataDomainDefinition):
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
    format = FormatMedia()


class ValueFormattedList(ExtendedSequenceSchema):
    result = ValueFormatted()


class ResultReference(ExtendedMappingSchema):
    href = ReferenceURL(description="Result file reference.")
    format = FormatMedia()


class ResultReferenceList(ExtendedSequenceSchema):
    result = ResultReference()


class ResultData(OneOfKeywordSchema):
    schema_ref = "{}/master/core/openapi/schemas/result.yaml".format(OGC_API_SCHEMA_URL)
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
    """Result outputs obtained from a successful process job execution."""
    example_ref = "{}/master/core/examples/json/Result.json".format(OGC_API_SCHEMA_URL)
    output_id = ResultData(
        variable="<output-id>", title="Output Identifier",
        description=(
            "Resulting value of the output that conforms to 'OGC-API - Processes' standard. "
            "(Note: '<output-id>' is a variable corresponding for each output identifier of the process)"
        )
    )


class JobInputsSchema(ExtendedMappingSchema):
    inputs = ExecuteInputList()
    links = LinkList(missing=drop)


class JobOutputsSchema(ExtendedMappingSchema):
    outputs = JobOutputList()
    links = LinkList(missing=drop)


class JobException(ExtendedMappingSchema):
    # note: test fields correspond exactly to 'owslib.wps.WPSException', they are deserialized as is
    Code = ExtendedSchemaNode(String())
    Locator = ExtendedSchemaNode(String(), default=None)
    Text = ExtendedSchemaNode(String())


class JobExceptionsSchema(ExtendedSequenceSchema):
    exceptions = JobException()


class JobLogsSchema(ExtendedSequenceSchema):
    log = ExtendedSchemaNode(String())


class FrontpageParameterSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), example="api")
    enabled = ExtendedSchemaNode(Boolean(), example=True)
    url = URL(description="Referenced parameter endpoint.", example="https://weaver-host", missing=drop)
    doc = ExtendedSchemaNode(String(), example="https://weaver-host/api", missing=drop)


class FrontpageParameters(ExtendedSequenceSchema):
    parameter = FrontpageParameterSchema()


class FrontpageSchema(ExtendedMappingSchema):
    message = ExtendedSchemaNode(String(), default="Weaver Information", example="Weaver Information")
    configuration = ExtendedSchemaNode(String(), default="default", example="default")
    parameters = FrontpageParameters()


class SwaggerJSONSpecSchema(ExtendedMappingSchema):
    pass


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


class ProcessDeploymentOffering(ExtendedMappingSchema):
    process = ProcessDeployment()
    processVersion = Version(title="processVersion", missing=drop)
    jobControlOptions = JobControlOptionsList(missing=drop)
    outputTransmission = TransmissionModeList(missing=drop)


class ProcessDescriptionChoiceType(OneOfKeywordSchema):
    _one_of = [
        Reference(),
        ProcessDeploymentOffering()
    ]


class Deploy(ExtendedMappingSchema):
    processDescription = ProcessDescriptionChoiceType()
    immediateDeployment = ExtendedSchemaNode(Boolean(), missing=drop, default=True)
    executionUnit = ExecutionUnitList()
    deploymentProfileName = URL(missing=drop)
    owsContext = OWSContext(missing=drop)


class PostProcessesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    body = Deploy(title="Deploy")


class PostProcessJobsEndpoint(ProcessPath):
    header = AcceptLanguageHeader()
    body = Execute()


class GetJobsQueries(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(Boolean(), description="Provide job details instead of IDs.",
                                default=False, example=True, missing=drop)
    groups = ExtendedSchemaNode(String(),
                                description="Comma-separated list of grouping fields with which to list jobs.",
                                default=False, example="process,service", missing=drop)
    page = ExtendedSchemaNode(Integer(), missing=0, default=0, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(), missing=10, default=10, validator=Range(min=0, max=10000))
    datetime = DateTimeInterval(missing=drop, default=None)
    status = JobStatusEnum(missing=drop, default=None)
    process = AnyIdentifier(missing=drop)
    provider = ExtendedSchemaNode(String(), missing=drop, default=None)
    sort = JobSortEnum(missing=drop)
    access = JobAccess(missing=drop, default=None)
    notification_email = ExtendedSchemaNode(String(), missing=drop, validator=Email())
    tags = ExtendedSchemaNode(String(), missing=drop, default=None,
                              description="Comma-separated values of tags assigned to jobs")


class GetJobsRequest(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetJobsQueries()


class GetJobsEndpoint(GetJobsRequest):
    pass


class GetProcessJobsEndpoint(GetJobsRequest, ProcessPath):
    pass


class GetProviderJobsEndpoint(GetJobsRequest, ProviderPath, ProcessPath):
    pass


class GetProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class DeleteProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class BillsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class BillEndpoint(BillPath):
    header = RequestHeaders()


class ProcessQuotesEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessQuoteEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()


class GetQuotesQueries(ExtendedMappingSchema):
    page = ExtendedSchemaNode(Integer(), missing=drop, default=0)
    limit = ExtendedSchemaNode(Integer(), missing=10, default=10, validator=Range(min=0, max=10000))
    process = AnyIdentifier(missing=None)
    sort = QuoteSortEnum(missing=drop)


class QuotesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetQuotesQueries()


class QuoteEndpoint(QuotePath):
    header = RequestHeaders()


class PostProcessQuote(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = NoContent()


class PostQuote(QuotePath):
    header = RequestHeaders()
    body = NoContent()


class PostProcessQuoteRequestEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = QuoteProcessParametersSchema()


# ################################################################
# Provider Processes schemas
# ################################################################


class ProvidersQuerySchema(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="Return summary details about each provider, or simply their IDs."
    )
    check = ExtendedSchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="List only reachable providers, dropping unresponsive ones that cannot be checked for listing. "
                    "Otherwise, all registered providers are listed regardless of their availability. When requesting "
                    "details, less metadata will be provided since it will not be fetched from remote services."
    )


class GetProviders(ExtendedMappingSchema):
    querystring = ProvidersQuerySchema()
    header = RequestHeaders()


class PostProvider(ExtendedMappingSchema):
    header = RequestHeaders()
    body = CreateProviderRequestBody()


class GetProviderProcesses(ExtendedMappingSchema):
    header = RequestHeaders()


class GetProviderProcess(ExtendedMappingSchema):
    header = RequestHeaders()


class PostProviderProcessJobRequest(ExtendedMappingSchema):
    """Launching a new process request definition."""
    header = RequestHeaders()
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
    """Error content in XML format"""
    description = "OWS formatted exception."
    code = OWSErrorCode(example="NoSuchProcess")
    locator = ExtendedSchemaNode(String(), example="identifier",
                                 description="Indication of the element that caused the error.")
    message = ExtendedSchemaNode(String(), example="Invalid process ID.",
                                 description="Specific description of the error.")


class ErrorJsonResponseBodySchema(ExtendedMappingSchema):
    code = OWSErrorCode()
    description = ExtendedSchemaNode(String(), description="Detail about the cause of error.")
    error = ErrorDetail(missing=drop)
    exception = OWSExceptionResponse(missing=drop)


class UnprocessableEntityResponseSchema(ExtendedMappingSchema):
    description = "Wrong format of given parameters."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProcessAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced process is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProviderAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced provider is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class InternalServerErrorResponseSchema(ExtendedMappingSchema):
    description = "Unhandled internal server error."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = FrontpageSchema()


class OkGetSwaggerJSONResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = SwaggerJSONSpecSchema(description="OpenAPI JSON schema of Weaver API.")


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


class GetProcessesQuery(ExtendedMappingSchema):
    providers = ExtendedSchemaNode(
        Boolean(), example=True, default=False, missing=drop,
        description="List local processes as well as all sub-processes of all registered providers. "
                    "Applicable only for Weaver in {} mode, false otherwise.".format(WEAVER_CONFIGURATION_EMS))
    detail = ExtendedSchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class GetProcessesEndpoint(ExtendedMappingSchema):
    querystring = GetProcessesQuery()


class OkGetProcessesListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessCollection()


class OkPostProcessDeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully deployed.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of deploy failure if applicable.")


class OkPostProcessesResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = OkPostProcessDeployBodySchema()


class BadRequestGetProcessInfoResponse(ExtendedMappingSchema):
    description = "Missing process identifier."
    body = NoContent()


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
    header = ResponseHeaders()
    body = OkDeleteProcessUndeployBodySchema()


class OkGetProviderProcessDescriptionResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDescription()


class CreatedPostProvider(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderSummarySchema()


class NotImplementedPostProviderResponse(ExtendedMappingSchema):
    description = "Provider registration not supported using referenced storage."


class CreatedLaunchJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedJobStatusSchema()


class OkGetProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class OkDeleteProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetQueriedJobsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = GetQueriedJobsSchema()


class OkDismissJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetJobStatusResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class NotFoundJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference UUID cannot be found."
    examples = {
        "JobNotFound": {
            "summary": "Example response when specified job reference cannot be found.",
            "value": EXAMPLES["job_not_found.json"]
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetJobInputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobInputsSchema()


class OkGetJobOutputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobOutputsSchema()


class RedirectResultResponse(ExtendedMappingSchema):
    header = RedirectHeaders()


class OkGetJobResultsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Result()


class CreatedQuoteExecuteResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedQuotedJobStatusSchema()


class CreatedQuoteRequestResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class OkGetQuoteInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class OkGetQuoteListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuotationListSchema()


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


get_api_frontpage_responses = {
    "200": OkGetFrontpageResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_openapi_json_responses = {
    "200": OkGetSwaggerJSONResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_swagger_ui_responses = {
    "200": OkGetSwaggerUIResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_redoc_ui_responses = {
    "200": OkGetRedocUIResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_versions_responses = {
    "200": OkGetVersionsResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_conformance_responses = {
    "200": OkGetConformanceResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_processes_responses = {
    "200": OkGetProcessesListResponse(description="success", examples={
        "ProcessesList": {
            "summary": "Listing of local processes registered in Weaver.",
            "value": EXAMPLES["local_process_listing.json"],
        }
    }),
    "500": InternalServerErrorResponseSchema(),
}
post_processes_responses = {
    "201": OkPostProcessesResponse(description="success"),
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
        }
    }),
    "400": BadRequestGetProcessInfoResponse(),
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
    "500": InternalServerErrorResponseSchema(),
}
get_process_visibility_responses = {
    "200": OkGetProcessVisibilitySchema(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
put_process_visibility_responses = {
    "200": OkPutProcessVisibilitySchema(description="success"),
    "403": ForbiddenVisibilityUpdateResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_process_responses = {
    "200": OkDeleteProcessResponse(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
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
    "500": InternalServerErrorResponseSchema(),
}
delete_provider_responses = {
    "204": NoContentDeleteProviderSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedDeleteProviderResponse(),
}
get_provider_processes_responses = {
    "200": OkGetProviderProcessesSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
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
    "500": InternalServerErrorResponseSchema(),
}
post_provider_responses = {
    "201": CreatedPostProvider(description="success"),
    "400": ExtendedMappingSchema(description=OWSMissingParameterValue.description),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedPostProviderResponse(),
}
post_provider_process_job_responses = {
    "201": CreatedLaunchJobResponse(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_process_jobs_responses = {
    "201": CreatedLaunchJobResponse(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_all_jobs_responses = {
    "200": OkGetQueriedJobsResponse(description="success", examples={
        "JobListing": {
            "summary": "Job ID listing with default queries.",
            "value": EXAMPLES["jobs_listing.json"]
        }
    }),
    "422": UnprocessableEntityResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_single_job_status_responses = {
    "200": OkGetJobStatusResponse(description="success", examples={
        "JobStatusSuccess": {
            "summary": "Successful job status response.",
            "value": EXAMPLES["job_status_success.json"]},
        "JobStatusFailure": {
            "summary": "Failed job status response.",
            "value": EXAMPLES["job_status_failed.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_job_responses = {
    "200": OkDismissJobResponse(description="success"),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_job_inputs_responses = {
    "200": OkGetJobInputsResponse(description="success", examples={
        "JobInputs": {
            "summary": "Submitted job input values at for process execution.",
            "value": EXAMPLES["job_inputs.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_job_outputs_responses = {
    "200": OkGetJobOutputsResponse(description="success", examples={
        "JobOutputs": {
            "summary": "Obtained job outputs values following process execution.",
            "value": EXAMPLES["job_outputs.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
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
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_exceptions_responses = {
    "200": OkGetJobExceptionsResponse(description="success", examples={
        "JobExceptions": {
            "summary": "Job exceptions that occurred during failing process execution.",
            "value": EXAMPLES["job_exceptions.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_logs_responses = {
    "200": OkGetJobLogsResponse(description="success", examples={
        "JobLogs": {
            "summary": "Job logs registered and captured throughout process execution.",
            "value": EXAMPLES["job_logs.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_quote_list_responses = {
    "200": OkGetQuoteListResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_quote_responses = {
    "200": OkGetQuoteInfoResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
post_quotes_responses = {
    "201": CreatedQuoteRequestResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
post_quote_responses = {
    "201": CreatedQuoteExecuteResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_list_responses = {
    "200": OkGetBillListResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_responses = {
    "200": OkGetBillDetailResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
wps_responses = {
    "200": OkWPSResponse(examples={
        "GetCapabilities": {
            "summary": "GetCapabilities example response.",
            "value": EXAMPLES["wps_getcapabilities.xml"]
        },
        "DescribeProcess": {
            "summary": "DescribeProcess example response.",
            "value": EXAMPLES["wps_describeprocess.xml"]
        },
        "Execute": {
            "summary": "Execute example response.",
            "value": EXAMPLES["wps_execute_response.xml"]
        }
    }),
    "400": ErrorWPSResponse(examples={
        "MissingParameterError": {
            "summary": "Error report in case of missing request parameter.",
            "value": EXAMPLES["wps_missing_parameter.xml"],
        }
    }),
    "500": ErrorWPSResponse(),
}


#################################################################
# Utility methods
#################################################################


def service_api_route_info(service_api, settings):
    # type: (Service, SettingsType) -> ViewInfo
    api_base = wps_restapi_base_path(settings)
    return {"name": service_api.name, "pattern": "{base}{path}".format(base=api_base, path=service_api.path)}


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
