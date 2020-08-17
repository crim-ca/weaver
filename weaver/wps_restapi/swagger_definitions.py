"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
# pylint: disable=C0103,invalid-name

from typing import TYPE_CHECKING

from colander import Boolean, DateTime, Float, Integer, OneOf, Range, String, Time, drop
from cornice import Service

from weaver import __meta__
from weaver.config import WEAVER_CONFIGURATION_EMS
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_CONTROL_OPTIONS,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_AUTO,
    EXECUTE_MODE_OPTIONS,
    EXECUTE_RESPONSE_OPTIONS,
    EXECUTE_RESPONSE_RAW,
    EXECUTE_TRANSMISSION_MODE_OPTIONS,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import (
    ACCEPT_LANGUAGE_EN_CA,
    ACCEPT_LANGUAGES,
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_APP_XML,
    CONTENT_TYPE_TEXT_HTML,
    CONTENT_TYPE_TEXT_PLAIN
)
from weaver.owsexceptions import OWSMissingParameterValue
from weaver.sort import JOB_SORT_VALUES, QUOTE_SORT_VALUES, SORT_CREATED, SORT_ID, SORT_PROCESS
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_ACCEPTED, STATUS_COMPLIANT_OGC
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_VALUES
from weaver.wps_restapi.colander_extras import (
    AnyOfKeywordSchema,
    OneOfCaseInsensitive,
    ExtendedMappingSchema,
    ExtendedSchemaNode,
    ExtendedSequenceSchema,
    NotKeywordSchema,
    OneOfKeywordSchema,
    PermissiveMappingSchema
)
from weaver.wps_restapi.utils import wps_restapi_base_path

if TYPE_CHECKING:
    from weaver.typedefs import SettingsType, TypedDict

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

CWL_DOC_MESSAGE = "Note that multiple formats are supported and not all specification variants or parameters " \
                  "are presented here. Please refer to official CWL documentation for more details " \
                  "(https://www.commonwl.org/)."

IO_INFO_IDS = "Identifier of the {first} {what}. To merge details between corresponding {first} and {second} " \
              "{what} specifications, this is the value that will be used to associate them together."

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

###############################################################################
# API endpoints
# These "services" are wrappers that allow Cornice to generate the JSON API
###############################################################################

api_frontpage_service = Service(name="api_frontpage", path="/")
api_swagger_ui_service = Service(name="api_swagger_ui", path="/api")
api_swagger_json_service = Service(name="api_swagger_json", path="/json")
api_versions_service = Service(name="api_versions", path="/versions")
api_conformance_service = Service(name="api_conformance", path="/conformance")

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

#########################################################
# Generic schemas
#########################################################


class SLUG(ExtendedSchemaNode):
    schema_type = String
    description = "Slug name pattern."
    example = "some-object-slug-name"
    pattern = "^[a-z0-9]+(?:-[a-z0-9]+)*$"


class URL(ExtendedSchemaNode):
    schema_type = String
    description = "URL reference"
    format = "url"


class UUID(ExtendedSchemaNode):
    schema_type = String
    description = "UUID"
    example = "a9d14bf4-84e0-449a-bac8-16e598efe807"
    format = "uuid"
    title = "UUID"


class AnyId(OneOfKeywordSchema):
    _one_of = (
        SLUG(description="Generic identifier. This is a user-friendly slug-name. "
                         "Note that this will represent the latest process matching this name. "
                         "For specific process version, use the UUID instead.", title="ID"),
        UUID(description="Unique identifier.")
    )


# NOTE: future (https://github.com/crim-ca/weaver/issues/107)
#  replace process/provider 'AnyIdentifier' by above 'AnyId'
class AnyIdentifier(ExtendedSchemaNode):
    schema_type = String


class Version(ExtendedSchemaNode):
    # note: internally use LooseVersion, so don't be too strict about pattern
    schema_type = String
    description = "Version string."
    example = "1.2.3"
    format = "version"
    pattern = r"^\d+(\.\d+(\.\d+(\.[a-zA-Z0-9\-_]+)*)*)*$"


class JsonHeader(ExtendedMappingSchema):
    content_type = ExtendedSchemaNode(String(), example=CONTENT_TYPE_APP_JSON, default=CONTENT_TYPE_APP_JSON)
    content_type.name = "Content-Type"


class HtmlHeader(ExtendedMappingSchema):
    content_type = ExtendedSchemaNode(String(), example=CONTENT_TYPE_TEXT_HTML, default=CONTENT_TYPE_TEXT_HTML)
    content_type.name = "Content-Type"


class XmlHeader(ExtendedMappingSchema):
    content_type = ExtendedSchemaNode(String(), example=CONTENT_TYPE_APP_XML, default=CONTENT_TYPE_APP_XML)
    content_type.name = "Content-Type"


class RequestContentTypeHeader(OneOfKeywordSchema):
    _one_of = (
        JsonHeader(),
        XmlHeader(),
    )


class ResponseContentTypeHeader(OneOfKeywordSchema):
    _one_of = (
        JsonHeader(),
        XmlHeader(),
        HtmlHeader(),
    )


class AcceptHeader(ExtendedMappingSchema):
    Accept = ExtendedSchemaNode(String(), missing=drop, default=CONTENT_TYPE_APP_JSON, validator=OneOf([
        CONTENT_TYPE_APP_JSON,
        CONTENT_TYPE_APP_XML,
        # CONTENT_TYPE_TEXT_HTML,   # defaults to JSON for easy use within browsers
    ]))


class AcceptLanguageHeader(ExtendedMappingSchema):
    AcceptLanguage = ExtendedSchemaNode(String(), missing=drop)
    AcceptLanguage.name = "Accept-Language"


class RequestHeaders(AcceptHeader, AcceptLanguageHeader, RequestContentTypeHeader):
    """Headers that can indicate how to adjust the behavior and/or result the be provided in the response."""


class ResponseHeaders(ResponseContentTypeHeader):
    """Headers describing resulting response."""


class KeywordList(ExtendedSequenceSchema):
    keyword = ExtendedSchemaNode(String())


class Language(ExtendedSchemaNode):
    schema_type = String
    example = ACCEPT_LANGUAGE_EN_CA
    validator = OneOf(ACCEPT_LANGUAGES)


class ValueLanguage(ExtendedMappingSchema):
    value = ExtendedSchemaNode(String())
    lang = Language(missing=drop)


class LinkLanguage(ExtendedMappingSchema):
    href = URL()
    hreflang = Language(missing=drop)


class LinkMeta(ExtendedMappingSchema):
    rel = ExtendedSchemaNode(String())
    type = ExtendedSchemaNode(String(), missing=drop)
    title = ExtendedSchemaNode(String(), missing=drop)


class Link(LinkLanguage, LinkMeta):
    pass


class MetadataContent(OneOfKeywordSchema, LinkMeta):
    _one_of = [
        LinkLanguage(),
        ValueLanguage()
    ]


class Metadata(MetadataContent):
    role = URL(missing=drop)


class MetadataList(ExtendedSequenceSchema):
    item = Metadata()


class LinkList(ExtendedSequenceSchema):
    link = Link()


class LandingPage(ExtendedMappingSchema):
    links = LinkList()


class Format(ExtendedMappingSchema):
    mimeType = ExtendedSchemaNode(String(), missing=drop)
    schema = ExtendedSchemaNode(String(), missing=drop)
    encoding = ExtendedSchemaNode(String(), missing=drop)


class FormatDefault(Format):
    """Format for process input are assumed plain text if the MIME-type was omitted and is not
    one of the known formats by this instance. When executing a job, the best match will be used
    to run the process, and will fallback to the default as last resort.
    """
    mimeType = ExtendedSchemaNode(String(), default=CONTENT_TYPE_TEXT_PLAIN, example=CONTENT_TYPE_APP_JSON)


class FormatDescription(FormatDefault):
    maximumMegabytes = ExtendedSchemaNode(Integer(), missing=drop)
    default = ExtendedSchemaNode(
        Boolean(), missing=drop, default=False,
        description="Indicate if this format should be considered as the default one in case none "
                    "of the other allowed/supported formats is matched against the job input."
    )


class FormatDescriptionList(ExtendedSequenceSchema):
    format = FormatDescription()


class AdditionalParameterValuesList(ExtendedSequenceSchema):
    values = ExtendedSchemaNode(String())


class AdditionalParameter(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    values = AdditionalParameterValuesList()


class AdditionalParameterList(ExtendedSequenceSchema):
    item = AdditionalParameter()


class AdditionalParameters(ExtendedMappingSchema):
    role = ExtendedSchemaNode(String(), missing=drop)
    parameters = AdditionalParameterList(missing=drop)


class AdditionalParametersList(ExtendedSequenceSchema):
    additionalParameter = AdditionalParameters()


class Content(ExtendedMappingSchema):
    href = URL(description="URL to CWL file.", title="href",
               example="http://some.host/applications/cwl/multisensor_ndvi.cwl")


class Offering(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String(), missing=drop, description="Descriptor of represented information in 'content'.")
    content = Content(title="content", missing=drop)


class OWSContext(ExtendedMappingSchema):
    offering = Offering(title="offering")


class DescriptionType(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop)
    abstract = ExtendedSchemaNode(String(), missing=drop)
    keywords = KeywordList(missing=drop)
    owsContext = OWSContext(missing=drop, title="owsContext")
    metadata = MetadataList(missing=drop)
    additionalParameters = AdditionalParametersList(missing=drop, title="additionalParameters")
    links = LinkList(missing=drop, title="links")


class AnyOccursType(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String())
    ]


class WithMinMaxOccurs(ExtendedMappingSchema):
    minOccurs = AnyOccursType(title="minOccurs", missing=drop,
                              description="Minimum allowed number of data occurrences of this item.")
    maxOccurs = AnyOccursType(title="maxOccurs", missing=drop,
                              description="Maximum allowed number of data occurrences of this item.")


class ProcessDescriptionType(DescriptionType):
    id = AnyIdentifier(description="Process identifier.")


class InputDescriptionType(DescriptionType):
    id = SLUG(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="input"))


class OutputDescriptionType(DescriptionType):
    id = SLUG(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="output"))


class WithFormats(ExtendedMappingSchema):
    formats = FormatDescriptionList()


class ComplexInputType(WithMinMaxOccurs, WithFormats):
    pass


class SupportedCRS(ExtendedMappingSchema):
    crs = URL(tile="crs", description="Coordinate Reference System")
    default = ExtendedSchemaNode(Boolean(), missing=drop)


class SupportedCRSList(ExtendedSequenceSchema):
    item = SupportedCRS(title="SupportedCRS")


class BoundingBoxInputType(WithMinMaxOccurs):
    supportedCRS = SupportedCRSList()


class LiteralReference(ExtendedMappingSchema):
    reference = URL()


class DataTypeSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    reference = URL(missing=drop)


class UomSchema(DataTypeSchema):
    pass


class AllowedValuesList(ExtendedSequenceSchema):
    allowedValues = ExtendedSchemaNode(String())


class AllowedValues(ExtendedMappingSchema):
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


class ValuesReference(ExtendedMappingSchema):
    valueReference = URL()


class LiteralDataDomainType(OneOfKeywordSchema):
    _one_of = (
        AllowedValues,
        AllowedRanges,
        ValuesReference,
        AnyValue,  # must be last because it"s the most permissive (always valid)
    )
    defaultValue = ExtendedSchemaNode(String(), missing=drop)
    dataType = DataTypeSchema(missing=drop)
    uom = UomSchema(missing=drop)


class LiteralDataDomainTypeList(ExtendedSequenceSchema):
    literalDataDomain = LiteralDataDomainType()


class LiteralInputType(NotKeywordSchema, WithMinMaxOccurs):
    _not = (WithFormats, )
    literalDataDomains = LiteralDataDomainTypeList(missing=drop)


class InputType(OneOfKeywordSchema, InputDescriptionType):
    _one_of = (
        BoundingBoxInputType,
        ComplexInputType,  # should be 2nd to last because very permissive, but requires format at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    )


class InputTypeList(ExtendedSequenceSchema):
    input = InputType()


class LiteralOutputType(NotKeywordSchema, ExtendedMappingSchema):
    _not = (WithFormats, )
    literalDataDomains = LiteralDataDomainTypeList(missing=drop)


class BoundingBoxOutputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


class ComplexOutputType(WithFormats):
    pass


class OutputType(OneOfKeywordSchema, OutputDescriptionType):
    _one_of = (
        BoundingBoxOutputType,
        ComplexOutputType,  # should be 2nd to last because very permission, but requires format at least
        LiteralOutputType,  # must be last because it"s the most permissive (all can default if omitted)
    )


class OutputDescriptionList(ExtendedSequenceSchema):
    item = OutputType()


class JobExecuteModeEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobExecuteModeEnum, self).__init__(
            self.schema_type(),
            title=kwargs.get("title", "mode"),
            default=kwargs.get("default", EXECUTE_MODE_AUTO),
            example=kwargs.get("example", EXECUTE_MODE_ASYNC),
            validator=OneOf(list(EXECUTE_MODE_OPTIONS)),
            **kwargs)


class JobControlOptionsEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobControlOptionsEnum, self).__init__(
            self.schema_type(),
            title="jobControlOptions",
            default=kwargs.get("default", EXECUTE_CONTROL_OPTION_ASYNC),
            example=kwargs.get("example", EXECUTE_CONTROL_OPTION_ASYNC),
            validator=OneOf(list(EXECUTE_CONTROL_OPTIONS)),
            **kwargs)


class JobResponseOptionsEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobResponseOptionsEnum, self).__init__(
            self.schema_type(),
            title=kwargs.get("title", "response"),
            default=kwargs.get("default", EXECUTE_RESPONSE_RAW),
            example=kwargs.get("example", EXECUTE_RESPONSE_RAW),
            validator=OneOf(list(EXECUTE_RESPONSE_OPTIONS)),
            **kwargs)


class TransmissionModeEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(TransmissionModeEnum, self).__init__(
            self.schema_type(),
            title=kwargs.get("title", "transmissionMode"),
            default=kwargs.get("default", EXECUTE_TRANSMISSION_MODE_REFERENCE),
            example=kwargs.get("example", EXECUTE_TRANSMISSION_MODE_REFERENCE),
            validator=OneOf(list(EXECUTE_TRANSMISSION_MODE_OPTIONS)),
            **kwargs)


class JobStatusEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobStatusEnum, self).__init__(
            self.schema_type(),
            default=kwargs.get("default", None),
            example=kwargs.get("example", STATUS_ACCEPTED),
            validator=OneOf(list(JOB_STATUS_CATEGORIES[STATUS_COMPLIANT_OGC])),
            **kwargs)


class JobSortEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobSortEnum, self).__init__(
            String(),
            default=kwargs.get("default", SORT_CREATED),
            example=kwargs.get("example", SORT_CREATED),
            validator=OneOf(list(JOB_SORT_VALUES)),
            **kwargs)


class QuoteSortEnum(ExtendedSchemaNode):
    schema_type = String

    def __init__(self, *_, **kwargs):
        kwargs.pop("validator", None)  # ignore passed argument and enforce the validator
        super(QuoteSortEnum, self).__init__(
            self.schema_type(),
            default=kwargs.get("default", SORT_ID),
            example=kwargs.get("example", SORT_PROCESS),
            validator=OneOf(list(QUOTE_SORT_VALUES)),
            **kwargs)


class LaunchJobQuerystring(ExtendedMappingSchema):
    tags = ExtendedSchemaNode(String(), default=None, missing=drop,
                              description="Comma separated tags that can be used to filter jobs later")


class VisibilityValue(ExtendedSchemaNode):
    schema_type = String
    validator = OneOf(list(VISIBILITY_VALUES))
    example = VISIBILITY_PUBLIC


class Visibility(ExtendedMappingSchema):
    value = VisibilityValue()


#########################################################
# Path parameter definitions
#########################################################


class ProcessPath(ExtendedMappingSchema):
    process_id = AnyIdentifier(description="The process identifier.")


class ProviderPath(ExtendedMappingSchema):
    provider_id = AnyIdentifier(description="The provider identifier")


class JobPath(ExtendedMappingSchema):
    job_id = UUID(description="The job id")


class BillPath(ExtendedMappingSchema):
    bill_id = UUID(description="The bill id")


class QuotePath(ExtendedMappingSchema):
    quote_id = UUID(description="The quote id")


class ResultPath(ExtendedMappingSchema):
    result_id = UUID(description="The result id")


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class FrontpageEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class VersionsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class ConformanceEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class SwaggerJSONEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class SwaggerUIEndpoint(ExtendedMappingSchema):
    pass


class WPSParameters(ExtendedMappingSchema):
    service = ExtendedSchemaNode(String(), example="WPS", description="Service selection.",
                                 validator=OneOfCaseInsensitive(["WPS"]))
    request = ExtendedSchemaNode(String(), example="GetCapabilities", description="WPS operation to accomplish",
                                 validator=OneOfCaseInsensitive(["GetCapabilities", "DescribeProcess", "Execute"]))
    version = ExtendedSchemaNode(String(), exaple="1.0.0", default="1.0.0", validator=OneOf(["1.0.0", "2.0.0"]))
    identifier = ExtendedSchemaNode(String(), exaple="hello", description="Process identifier.", missing=drop)
    data_inputs = ExtendedSchemaNode(String(), name="DataInputs", missing=drop, example="message=hi",
                                     description="Process execution inputs provided as Key-Value Pairs (KVP).")


class WPSBody(ExtendedMappingSchema):
    content = ExtendedSchemaNode(String(), description="XML data inputs provided for WPS POST request.")


class WPSEndpoint(ExtendedMappingSchema):
    header = AcceptHeader()
    querystring = WPSParameters()
    body = WPSBody()


class WPSXMLSuccessBodySchema(ExtendedMappingSchema):
    pass


class OkWPSResponse(ExtendedMappingSchema):
    description = "WPS operation successful"
    header = XmlHeader()
    body = WPSXMLSuccessBodySchema()


class WPSXMLErrorBodySchema(ExtendedMappingSchema):
    pass


class ErrorWPSResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred on WPS endpoint."
    header = XmlHeader()
    body = WPSXMLErrorBodySchema()


class ProviderEndpoint(ProviderPath):
    header = RequestHeaders()


class ProviderProcessEndpoint(ProviderPath, ProcessPath):
    header = RequestHeaders()


class ProcessEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessPackageEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessPayloadEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityGetEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityPutEndpoint(ProcessPath):
    header = RequestHeaders()
    body = Visibility()


class FullJobEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ShortJobEndpoint(JobPath):
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


class ProcessResultsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class FullResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ShortResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class FullExceptionsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ShortExceptionsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessExceptionsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class FullLogsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ShortLogsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessLogsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class CreateProviderRequestBody(ExtendedMappingSchema):
    id = ExtendedSchemaNode(String())
    url = URL(description="Endpoint where to query the provider.")
    public = ExtendedSchemaNode(Boolean())


class InputDataType(ExtendedMappingSchema):
    id = ExtendedSchemaNode(String())


class OutputDataType(ExtendedMappingSchema):
    id = ExtendedSchemaNode(String())
    format = Format(missing=drop)


class Output(OutputDataType):
    transmissionMode = TransmissionModeEnum(missing=drop)


class OutputList(ExtendedSequenceSchema):
    output = Output()


class ProviderSummarySchema(ExtendedMappingSchema):
    """WPS provider summary definition."""
    id = ExtendedSchemaNode(String())
    url = URL(description="Endpoint of the provider.")
    title = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    public = ExtendedSchemaNode(Boolean())


class ProviderCapabilitiesSchema(ExtendedMappingSchema):
    """WPS provider capabilities."""
    id = ExtendedSchemaNode(String())
    url = URL(description="WPS GetCapabilities URL of the provider.")
    title = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    contact = ExtendedSchemaNode(String())
    type = ExtendedSchemaNode(String())


class TransmissionModeList(ExtendedSequenceSchema):
    item = TransmissionModeEnum(missing=drop)


class JobControlOptionsList(ExtendedSequenceSchema):
    item = JobControlOptionsEnum(missing=drop)


class ExceptionReportType(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String())
    description = ExtendedSchemaNode(String(), missing=drop)


class ProcessSummary(ProcessDescriptionType):
    """WPS process definition."""
    version = ExtendedSchemaNode(String(), missing=drop)
    jobControlOptions = JobControlOptionsList(missing=drop)
    outputTransmission = TransmissionModeList(missing=drop)
    processDescriptionURL = URL(description="Process description endpoint.",
                                missing=drop, title="processDescriptionURL")


class ProcessSummaryList(ExtendedSequenceSchema):
    item = ProcessSummary()


class ProcessCollection(ExtendedMappingSchema):
    processes = ProcessSummaryList()


class Process(ProcessDescriptionType):
    inputs = InputTypeList(missing=drop)
    outputs = OutputDescriptionList(missing=drop)
    visibility = VisibilityValue(missing=drop)
    executeEndpoint = URL(description="Endpoint where the process can be executed from.", missing=drop)


class ProcessOutputDescriptionSchema(ExtendedMappingSchema):
    """WPS process output definition."""
    dataType = ExtendedSchemaNode(String())
    defaultValue = ExtendedMappingSchema()
    id = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    title = ExtendedSchemaNode(String())


class JobStatusInfo(ExtendedMappingSchema):
    jobID = UUID(example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the job.")
    status = JobStatusEnum()
    message = ExtendedSchemaNode(String(), missing=drop)
    expirationDate = ExtendedSchemaNode(DateTime(), missing=drop)
    estimatedCompletion = ExtendedSchemaNode(DateTime(), missing=drop)
    duration = ExtendedSchemaNode(Time(), missing=drop, description="Duration of the process execution.")
    nextPoll = ExtendedSchemaNode(DateTime(), missing=drop)
    percentCompleted = ExtendedSchemaNode(Integer(), example=0, validator=Range(min=0, max=100))
    links = LinkList(missing=drop)


class JobEntrySchema(OneOfKeywordSchema):
    # note:
    #   Since JobID is a simple string (not a dict), no additional mapping field can be added here.
    #   They will be discarded by `OneOfKeywordSchema.deserialize()`.
    _one_of = (
        JobStatusInfo,
        ExtendedSchemaNode(String(), description="Job ID."),
    )


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
    limit = ExtendedSchemaNode(Integer())
    page = ExtendedSchemaNode(Integer())


class GroupedJobsCategorySchema(ExtendedMappingSchema):
    category = PermissiveMappingSchema(description="Grouping values that compose the corresponding job list category.")
    jobs = JobCollection(description="List of jobs that matched the corresponding grouping values.")
    count = ExtendedSchemaNode(Integer(), description="Number of matching jobs for the corresponding group category.")


class GroupedCategoryJobsSchema(ExtendedSequenceSchema):
    job_group_category_item = GroupedJobsCategorySchema()


class GetGroupedJobsSchema(ExtendedMappingSchema):
    groups = GroupedCategoryJobsSchema()


class GetQueriedJobsSchema(OneOfKeywordSchema):
    _one_of = (
        GetPagingJobsSchema,
        GetGroupedJobsSchema,
    )
    total = ExtendedSchemaNode(Integer(),
                               description="Total number of matched jobs regardless of grouping or paging result.")


class DismissedJobSchema(ExtendedMappingSchema):
    status = JobStatusEnum()
    jobID = UUID(description="ID of the job.")
    message = ExtendedSchemaNode(String(), example="Job dismissed.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0)


class QuoteProcessParametersSchema(ExtendedMappingSchema):
    inputs = InputTypeList(missing=drop)
    outputs = OutputDescriptionList(missing=drop)
    mode = JobExecuteModeEnum(missing=drop)
    response = JobResponseOptionsEnum(missing=drop)


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
class DataEncodingAttributes(Format):
    pass


class Reference(DataEncodingAttributes):
    href = URL(description="Endpoint of the reference.")
    body = ExtendedSchemaNode(String(), missing=drop)
    bodyReference = URL(missing=drop)


class DataInteger(ExtendedMappingSchema):
    data = ExtendedSchemaNode(Integer())


class DataBoolean(ExtendedMappingSchema):
    data = ExtendedSchemaNode(Boolean())


class DataString(ExtendedMappingSchema):
    data = ExtendedSchemaNode(String())


class DataFloat(ExtendedMappingSchema):
    data = ExtendedSchemaNode(Float())


class AnyDataTypeFormats(ExtendedMappingSchema):
    """Items with 'data' key, only literal data.

    .. note::
        :class:`URL` is not here contrary to :class:`ValueTypeFormats`.

    .. seealso::
        - :class:`DataType`
        - :class:`AnyType`
    """
    _any_of = (
        DataFloat(),
        DataInteger(),
        DataBoolean(),
        DataString(),
        # ###ExtendedSchemaNode(Float()),  # before Integer because more restrictive Number format
        # ###ExtendedSchemaNode(Integer()),  # before Boolean because bool can be interpreted using int
        # ###ExtendedSchemaNode(Boolean()),
        # ###ExtendedSchemaNode(String())
    )


# ##class DataType(DataEncodingAttributes):
# ##   data = DataTypeFormats(description="Value provided by one of the accepted types.")


class DefaultFloat(ExtendedMappingSchema):
    default = ExtendedSchemaNode(Float())


class DefaultInteger(ExtendedMappingSchema):
    default = ExtendedSchemaNode(Integer())


class DefaultBoolean(ExtendedMappingSchema):
    default = ExtendedSchemaNode(Boolean())


class DefaultString(ExtendedMappingSchema):
    default = ExtendedSchemaNode(String())


# ###class ValueTypeFormats(OneOfKeywordSchema):
class AnyDefaultTypeFormats(AnyOfKeywordSchema):
    """Default format, always 'default' key regardless of content."""
    _any_of = (
        DefaultString(),
        DefaultBoolean(),
        DefaultInteger(),
        DefaultFloat(),
    )


class ValueFloat(ExtendedMappingSchema):
    value = ExtendedSchemaNode(Float())


class ValueInteger(ExtendedMappingSchema):
    value = ExtendedSchemaNode(Integer())


class ValueBoolean(ExtendedMappingSchema):
    value = ExtendedSchemaNode(Boolean())


class ValueString(ExtendedMappingSchema):
    value = ExtendedSchemaNode(String())


# ###class ValueTypeFormats(OneOfKeywordSchema):
class AnyValueTypeFormats(AnyOfKeywordSchema):
    """OGC-specific format, always 'value' key regardless of content.

    .. seealso::
        - :class:`ValueType`
        - :class:`AnyType`
    """
    _any_of = (
        ValueString(),
        ValueBoolean(),
        ValueInteger(),
        ValueFloat(),
        # ###ExtendedSchemaNode(Float()),  # before Integer because more restrictive Number format
        # ###ExtendedSchemaNode(Integer()),  # before Boolean because bool can be interpreted using int
        # ###ExtendedSchemaNode(Boolean()),
        # ###ExtendedSchemaNode(String()),
        # ###URL(),  # any-of will override previous string if URL validator succeeds because they have the same keys
    )


# ###class ValueType(ExtendedMappingSchema):
# ###    value = ValueTypeFormats(description="Value provided by one of the accepted types.")


# ###class AnyType(OneOfKeywordSchema):
class AnyType(AnyOfKeywordSchema):
    """Permissive variants that we attempt to parse automatically."""
    _any_of = (
        # literal data with 'data' key
        AnyDataTypeFormats(),
        # ### DataType,
        # same with 'value' key (OGC specification)
        AnyValueTypeFormats(),
        # ###ValueType,
        # HTTP references with various keywords
        LiteralReference(),
        Reference(),
    )


class Input(InputDataType, AnyType):
    """
    Default value to be looked for uses key 'value' to conform to OGC API standard.
    We still look for 'href', 'data' and 'reference' to remain back-compatible.
    """


class InputList(ExtendedSequenceSchema):
    item = Input(missing=drop, description="Received input definition during job submission.")


class Execute(ExtendedMappingSchema):
    inputs = InputList(missing=drop)
    outputs = OutputList()
    mode = ExtendedSchemaNode(String(), validator=OneOf(list(EXECUTE_MODE_OPTIONS)))
    notification_email = ExtendedSchemaNode(
        String(),
        missing=drop,
        description="Optionally send a notification email when the job is done.")
    response = ExtendedSchemaNode(String(), validator=OneOf(list(EXECUTE_RESPONSE_OPTIONS)))


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
    process = ExtendedSchemaNode(String(), description="Corresponding process ID.")
    steps = QuoteProcessListSchema(description="Child processes and prices.")
    total = ExtendedSchemaNode(Float(), description="Total of the quote including step processes.")


class QuotationList(ExtendedSequenceSchema):
    item = ExtendedSchemaNode(String(), description="Bill ID.")


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
    item = ExtendedSchemaNode(String(), description="Bill ID.")


class BillListSchema(ExtendedMappingSchema):
    bills = BillList()


class SupportedValues(ExtendedMappingSchema):
    pass


class DefaultValues(ExtendedMappingSchema):
    pass


class CWLClass(ExtendedSchemaNode):
    schema_type = String
    title = "Class"
    name = "class"
    example = "CommandLineTool"
    validator = OneOf(["CommandLineTool", "ExpressionTool", "Workflow"])
    description = "CWL class specification. This is used to differentiate between single Application Package (AP)" \
                  "definitions and Workflow that chains multiple packages."


class DockerRequirementSpecification(PermissiveMappingSchema):
    dockerPull = URL(example="docker-registry.host.com/namespace/image:1.2.3",
                     title="Docker pull reference",
                     description="Reference package that will be retrieved and executed by CWL.")


class DockerRequirement(DockerRequirementSpecification):
    name = "DockerRequirement"
    title = "DockerRequirement"


class DockerGpuRequirement(DockerRequirementSpecification):
    name = "DockerGpuRequirement"
    title = "DockerGpuRequirement"
    description = "Docker requirement with GPU-enabled support (https://github.com/NVIDIA/nvidia-docker). " \
                  "The instance must have the NVIDIA toolkit installed to use this feature."


class InitialWorkDirRequirement(PermissiveMappingSchema):
    name = "InitialWorkDirRequirement"
    title = "InitialWorkDirRequirement"
    listing = PermissiveMappingSchema()


class BuiltinRequirement(PermissiveMappingSchema):
    name = "BuiltinRequirement"
    title = "BuiltinRequirement"
    description = "Hint indicating that the Application Package corresponds to a builtin process of " \
                  "this instance. (note: can only be an hint as it is unofficial CWL specification)."
    process = AnyIdentifier()


class CWLRequirements(AnyOfKeywordSchema, PermissiveMappingSchema):
    _any_of = [
        DockerRequirement(missing=drop),
        DockerGpuRequirement(missing=drop),
        InitialWorkDirRequirement(missing=drop),
    ]


class CWLHints(AnyOfKeywordSchema, PermissiveMappingSchema):
    _any_of = [
        BuiltinRequirement(missing=drop),
        DockerRequirement(missing=drop),
        DockerGpuRequirement(missing=drop),
        InitialWorkDirRequirement(missing=drop),
    ]


class CWLArguments(ExtendedSequenceSchema):
    argument = ExtendedSchemaNode(String())


class CWLSymbols(ExtendedSequenceSchema):
    symbol = ExtendedSchemaNode(String())


class CWLTypeMap(PermissiveMappingSchema):
    type = ExtendedSchemaNode(String(), summary="CWL Type")
    items = ExtendedSchemaNode(String(), missing=drop, summary="Sub-type when defining an array.")
    symbols = CWLSymbols(missing=drop, summary="Allowed symbols (enum).")


class CWLType(OneOfKeywordSchema):
    title = "CWL Type"
    _one_of = [
        ExtendedSchemaNode(String(), title="Type", description="Literal type.", example="float"),
        CWLTypeMap(summary="CWL type with additional properties.")
    ]


class CWLInputBase(PermissiveMappingSchema):
    type = CWLType()
    inputBinding = ExtendedMappingSchema(missing=drop, title="Input Binding",
                                         description="Defines how to specify the input for the command.")


class CWLInputObject(AnyOfKeywordSchema):
    _any_of = [
        CWLInputBase(),
        AnyDefaultTypeFormats(missing=drop),
    ]


class CWLInputMap(ExtendedMappingSchema):
    input_id = CWLInputObject(variable="<input-id>", title="Input Identifier",
                              description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input") +
                              " (Note: '<input-id>' is a variable corresponding for each identifier)")


class CWLInputItem(CWLInputObject):
    id = ExtendedSchemaNode(String(), description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input"))


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
    outputBinding = OutputBinding(description="Defines how to retrieve the output result from the command.")


class CWLOutputMap(ExtendedMappingSchema):
    output_id = CWLOutputObject(variable="<output-id>", title="Output Identifier",
                                description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output") +
                                " (Note: '<output-id>' is a variable corresponding for each identifier)")


class CWLOutputItem(CWLOutputObject):
    id = ExtendedSchemaNode(String())


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


class CWL(PermissiveMappingSchema):
    cwlVersion = Version(description="CWL version of the described application package.")
    _class = CWLClass()
    requirements = CWLRequirements(description="Explicit requirement to execute the application package.", missing=drop)
    hints = CWLHints(description="Non-failing additional hints that can help resolve extra requirements.", missing=drop)
    baseCommand = CWLCommand(description="Command called in the docker image or on shell according to requirements "
                                         "and hints specifications. Can be omitted if already defined in the "
                                         "docker image.", missing=drop)
    arguments = CWLArguments(description="Base arguments passed to the command.", missing=drop)
    inputs = CWLInputsDefinition(description="All inputs available to the Application Package.")
    outputs = CWLOutputsDefinition(description="All outputs produced by the Application Package.")


class UnitType(ExtendedMappingSchema):
    unit = CWL(description="Execution unit definition as CWL package specification. " + CWL_DOC_MESSAGE)


class ProcessInputDescriptionSchema(ExtendedMappingSchema):
    minOccurs = ExtendedSchemaNode(Integer())
    maxOccurs = ExtendedSchemaNode(Integer())
    title = ExtendedSchemaNode(String())
    dataType = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    id = ExtendedSchemaNode(String())
    defaultValue = ExtendedSequenceSchema(DefaultValues())
    supportedValues = ExtendedSequenceSchema(SupportedValues())


class ProcessDescriptionSchema(ExtendedMappingSchema):
    outputs = ExtendedSequenceSchema(ProcessOutputDescriptionSchema())
    inputs = ExtendedSequenceSchema(ProcessInputDescriptionSchema())
    description = ExtendedSchemaNode(String())
    id = ExtendedSchemaNode(String())
    label = ExtendedSchemaNode(String())


class UndeploymentResult(ExtendedMappingSchema):
    id = ExtendedSchemaNode(String())


class DeploymentResult(ExtendedMappingSchema):
    processSummary = ProcessSummary()


class ProcessDescriptionBodySchema(ExtendedMappingSchema):
    process = ProcessDescriptionSchema()


class ProvidersSchema(ExtendedSequenceSchema):
    providers_service = ProviderSummarySchema()


class ProcessesSchema(ExtendedSequenceSchema):
    provider_processes_service = Process()


class JobOutput(OneOfKeywordSchema, OutputDataType):
    id = UUID(description="Job output id corresponding to process description outputs.")
    _one_of = (
        Reference(),
        AnyDataTypeFormats()
    )


class JobOutputList(ExtendedSequenceSchema):
    output = JobOutput(description="Job output result with specific keyword according to represented format.")


class JobResultValue(AnyOfKeywordSchema):
    _any_of = [
        OutputDataType(),
        AnyValueTypeFormats(description="Job outputs result conforming to OGC standard.")
    ]


class JobException(ExtendedMappingSchema):
    # note: test fields correspond exactly to 'owslib.wps.WPSException', they are serialized as is
    Code = ExtendedSchemaNode(String())
    Locator = ExtendedSchemaNode(String(), default=None)
    Text = ExtendedSchemaNode(String())


class JobExceptionList(ExtendedSequenceSchema):
    exceptions = JobException()


class JobLogList(ExtendedSequenceSchema):
    log = ExtendedSchemaNode(String())


class FrontpageParameterSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), example="api")
    enabled = ExtendedSchemaNode(Boolean(), example=True)
    url = URL(description="Referenced parameter endpoint.", example="https://weaver-host", missing=drop)
    doc = ExtendedSchemaNode(String(), example="https://weaver-host/api", missing=drop)


class FrontpageParameters(ExtendedSequenceSchema):
    param = FrontpageParameterSchema()


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
    item = VersionsSpecSchema()


class VersionsSchema(ExtendedMappingSchema):
    versions = VersionsList()


class ConformanceList(ExtendedSequenceSchema):
    item = URL(description="Conformance specification link.",
               example="http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/core")


class ConformanceSchema(ExtendedMappingSchema):
    conformsTo = ConformanceList()


# #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
# Local Processes schemas
# #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####


class PackageBody(ExtendedMappingSchema):
    pass


class ExecutionUnit(OneOfKeywordSchema):
    _one_of = (Link, UnitType)


class ExecutionUnitList(ExtendedSequenceSchema):
    unit = ExecutionUnit(description="Definition of the Application Package to execute.")


class ProcessOffering(ExtendedMappingSchema):
    process = Process()
    processVersion = Version(title="processVersion", missing=drop)
    jobControlOptions = JobControlOptionsList(missing=drop)
    outputTransmission = TransmissionModeList(missing=drop)


class ProcessDescriptionChoiceType(OneOfKeywordSchema):
    _one_of = (Reference, ProcessOffering)


class Deploy(ExtendedMappingSchema):
    processDescription = ProcessDescriptionChoiceType()
    immediateDeployment = ExtendedSchemaNode(Boolean(), missing=drop, default=True)
    executionUnit = ExecutionUnitList()
    deploymentProfileName = URL(missing=drop)
    owsContext = OWSContext(title="owsContext", missing=drop)


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
    page = ExtendedSchemaNode(Integer(), missing=drop, default=0)
    limit = ExtendedSchemaNode(Integer(), missing=drop, default=10)
    status = JobStatusEnum(missing=drop)
    process = ExtendedSchemaNode(String(), missing=drop, default=None)
    provider = ExtendedSchemaNode(String(), missing=drop, default=None)
    sort = JobSortEnum(missing=drop)
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
    limit = ExtendedSchemaNode(Integer(), missing=drop, default=10)
    process = ExtendedSchemaNode(String(), missing=drop, default=None)
    sort = QuoteSortEnum(missing=drop)


class QuotesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetQuotesQueries()


class QuoteEndpoint(QuotePath):
    header = RequestHeaders()


class PostProcessQuote(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = ExtendedMappingSchema(default={})


class PostQuote(QuotePath):
    header = RequestHeaders()
    body = ExtendedMappingSchema(default={})


class PostProcessQuoteRequestEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = QuoteProcessParametersSchema()


# #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
# Provider Processes schemas
# #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####


class GetProviders(ExtendedMappingSchema):
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


# #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
# Responses schemas
# #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

class ErrorDetail(ExtendedMappingSchema):
    code = ExtendedSchemaNode(Integer(), description="HTTP status code.", example=400)
    status = ExtendedSchemaNode(String(), description="HTTP status detail.", example="400 Bad Request")


class OWSErrorCode(ExtendedSchemaNode):
    schema_type = String()
    example = "InvalidParameterValue"
    description = "OWS error code."


class OWSExceptionResponse(ExtendedMappingSchema):
    """Error content in XML format"""
    code = OWSErrorCode()
    locator = ExtendedSchemaNode(String(), example="identifier",
                                 description="Indication of the element that caused the error.")
    message = ExtendedSchemaNode(String(), example="Invalid process ID.",
                                 description="Specific description of the error.")


class ErrorJsonResponseBodySchema(ExtendedMappingSchema):
    code = OWSErrorCode()
    description = ExtendedSchemaNode(String(), description="", example="Process identifier is invalid.")
    error = ErrorDetail(missing=drop)


class UnauthorizedJsonResponseSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = FrontpageSchema()


class OkGetSwaggerJSONResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = SwaggerJSONSpecSchema(description="Swagger JSON of weaver API.")


class OkGetSwaggerUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of weaver API.")


class OkGetVersionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = VersionsSchema()


class OkGetConformanceResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ConformanceSchema()


class OkGetProvidersListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProvidersSchema()


class InternalServerErrorGetProvidersListResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during providers listing."


class OkGetProviderCapabilitiesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderCapabilitiesSchema()


class InternalServerErrorGetProviderCapabilitiesResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during provider capabilities request."


class NoContentDeleteProviderSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ExtendedMappingSchema(default={})


class InternalServerErrorDeleteProviderResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during provider removal."


class NotImplementedDeleteProviderResponse(ExtendedMappingSchema):
    description = "Provider removal not supported using referenced storage."


class OkGetProviderProcessesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessesSchema()


class InternalServerErrorGetProviderProcessesListResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during provider processes listing."


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


class InternalServerErrorGetProcessesListResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during processes listing."


class OkPostProcessDeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully deployed.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of deploy failure if applicable.")


class OkPostProcessesResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = OkPostProcessDeployBodySchema()


class InternalServerErrorPostProcessesResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process deployment."


class BadRequestGetProcessInfoResponse(ExtendedMappingSchema):
    description = "Missing process identifier."
    body = ExtendedMappingSchema(default={})


class OkGetProcessInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessOffering()


class InternalServerErrorGetProcessResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process description."


class OkGetProcessPackageSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ExtendedMappingSchema(default={})


class InternalServerErrorGetProcessPackageResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process package description."


class OkGetProcessPayloadSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ExtendedMappingSchema(default={})


class InternalServerErrorGetProcessPayloadResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process payload description."


class ProcessVisibilityResponseBodySchema(ExtendedMappingSchema):
    value = VisibilityValue()


class OkGetProcessVisibilitySchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessVisibilityResponseBodySchema()


class InternalServerErrorGetProcessVisibilityResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process visibility retrieval."


class OkPutProcessVisibilitySchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessVisibilityResponseBodySchema()


class InternalServerErrorPutProcessVisibilityResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process visibility update."


class OkDeleteProcessUndeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully undeployed.")
    identifier = ExtendedSchemaNode(String(), example="workflow")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of undeploy failure if applicable.")


class OkDeleteProcessResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = OkDeleteProcessUndeployBodySchema()


class InternalServerErrorDeleteProcessResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process deletion."


class OkGetProviderProcessDescriptionResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDescriptionBodySchema()


class InternalServerErrorGetProviderProcessResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during provider process description."


class CreatedPostProvider(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderSummarySchema()


class InternalServerErrorPostProviderResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during provider process registration."


class NotImplementedPostProviderResponse(ExtendedMappingSchema):
    description = "Provider registration not supported using referenced storage."


class CreatedLaunchJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedJobStatusSchema()


class InternalServerErrorPostProcessJobResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process job submission."


class InternalServerErrorPostProviderProcessJobResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during process job submission."


class OkGetProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class OkDeleteProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetQueriedJobsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = GetQueriedJobsSchema()


class InternalServerErrorGetJobsResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during jobs listing."


class OkDismissJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class InternalServerErrorDeleteJobResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during job dismiss request."


class OkGetJobStatusResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class InternalServerErrorGetJobStatusResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during provider process description."


class Inputs(ExtendedMappingSchema):
    inputs = InputList()
    links = LinkList(missing=drop)


class OkGetJobInputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Inputs()


class Outputs(ExtendedMappingSchema):
    outputs = JobOutputList()
    links = LinkList(missing=drop)


class OkGetJobOutputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Outputs()


class Results(ExtendedSequenceSchema):
    """List of outputs obtained from a successful process job execution."""
    result = JobResultValue()


class OkGetJobResultsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Results()  # list is returned directly without extra metadata, OGC-standard


class InternalServerErrorGetJobResultsResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during job results listing."


class InternalServerErrorGetJobOutputResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during job results listing."


class CreatedQuoteExecuteResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedQuotedJobStatusSchema()


class InternalServerErrorPostQuoteExecuteResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during quote job execution."


class CreatedQuoteRequestResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class InternalServerErrorPostQuoteRequestResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during quote submission."


class OkGetQuoteInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class InternalServerErrorGetQuoteInfoResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during quote retrieval."


class OkGetQuoteListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuotationListSchema()


class InternalServerErrorGetQuoteListResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during quote listing."


class OkGetBillDetailResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillSchema()


class InternalServerErrorGetBillInfoResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during bill retrieval."


class OkGetBillListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillListSchema()


class InternalServerErrorGetBillListResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during bill listing."


class OkGetJobExceptionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobExceptionList()


class InternalServerErrorGetJobExceptionsResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during job exceptions listing."


class OkGetJobLogsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobLogList()


class InternalServerErrorGetJobLogsResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred during job logs listing."


get_api_frontpage_responses = {
    "200": OkGetFrontpageResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
}
get_api_swagger_json_responses = {
    "200": OkGetSwaggerJSONResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
}
get_api_swagger_ui_responses = {
    "200": OkGetSwaggerUIResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
}
get_api_versions_responses = {
    "200": OkGetVersionsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
}
get_api_conformance_responses = {
    "200": OkGetConformanceResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized")
}
get_processes_responses = {
    "200": OkGetProcessesListResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorGetProcessesListResponse(),
}
post_processes_responses = {
    "201": OkPostProcessesResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorPostProcessesResponse(),
}
get_process_responses = {
    "200": OkGetProcessInfoResponse(description="success"),
    "400": BadRequestGetProcessInfoResponse(),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProcessResponse(),
}
get_process_package_responses = {
    "200": OkGetProcessPackageSchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProcessPackageResponse(),
}
get_process_payload_responses = {
    "200": OkGetProcessPayloadSchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProcessPayloadResponse(),
}
get_process_visibility_responses = {
    "200": OkGetProcessVisibilitySchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProcessVisibilityResponse(),
}
put_process_visibility_responses = {
    "200": OkPutProcessVisibilitySchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorPutProcessVisibilityResponse(),
}
delete_process_responses = {
    "200": OkDeleteProcessResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorDeleteProcessResponse(),
}
get_providers_list_responses = {
    "200": OkGetProvidersListResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProvidersListResponse(),
}
get_provider_responses = {
    "200": OkGetProviderCapabilitiesSchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProviderCapabilitiesResponse(),
}
delete_provider_responses = {
    "204": NoContentDeleteProviderSchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorDeleteProviderResponse(),
    "501": NotImplementedDeleteProviderResponse(),
}
get_provider_processes_responses = {
    "200": OkGetProviderProcessesSchema(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProviderProcessesListResponse(),
}
get_provider_process_responses = {
    "200": OkGetProviderProcessDescriptionResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetProviderProcessResponse(),
}
post_provider_responses = {
    "201": CreatedPostProvider(description="success"),
    "400": ExtendedMappingSchema(description=OWSMissingParameterValue.description),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorPostProviderResponse(),
    "501": NotImplementedPostProviderResponse(),
}
post_provider_process_job_responses = {
    "201": CreatedLaunchJobResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorPostProviderProcessJobResponse(),
}
post_process_jobs_responses = {
    "201": CreatedLaunchJobResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorPostProcessJobResponse(),
}
get_all_jobs_responses = {
    "200": OkGetQueriedJobsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobsResponse(),
}
get_single_job_status_responses = {
    "200": OkGetJobStatusResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobStatusResponse(),
}
delete_job_responses = {
    "200": OkDismissJobResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorDeleteJobResponse(),
}
get_job_inputs_responses = {
    "200": OkGetJobInputsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobResultsResponse(),
}
get_job_outputs_responses = {
    "200": OkGetJobOutputsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobOutputResponse(),
}
get_job_results_responses = {
    "200": OkGetJobResultsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorGetJobResultsResponse(),
}
get_exceptions_responses = {
    "200": OkGetJobExceptionsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobExceptionsResponse(),
}
get_logs_responses = {
    "200": OkGetJobLogsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobLogsResponse(),
}
get_quote_list_responses = {
    "200": OkGetQuoteListResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorGetQuoteListResponse(),
}
get_quote_responses = {
    "200": OkGetQuoteInfoResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorGetQuoteInfoResponse(),
}
post_quotes_responses = {
    "201": CreatedQuoteRequestResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorPostQuoteRequestResponse(),
}
post_quote_responses = {
    "201": CreatedQuoteExecuteResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorPostQuoteExecuteResponse(),
}
get_bill_list_responses = {
    "200": OkGetBillListResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorGetBillListResponse(),
}
get_bill_responses = {
    "200": OkGetBillDetailResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "500": InternalServerErrorGetBillInfoResponse(),
}
wps_responses = {
    "200": OkWPSResponse(),
    "500": ErrorWPSResponse(),
}


#################################################################
# Utility methods
#################################################################


def service_api_route_info(service_api, settings):
    # type: (Service, SettingsType) -> ViewInfo
    api_base = wps_restapi_base_path(settings)
    return {"name": service_api.name, "pattern": "{base}{path}".format(base=api_base, path=service_api.path)}
