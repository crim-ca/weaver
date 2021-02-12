"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
# pylint: disable=C0103,invalid-name

from typing import TYPE_CHECKING

from colander import (
    Boolean,
    DateTime,
    Float,
    Integer,
    MappingSchema as MapSchema,
    OneOf,
    Range,
    SequenceSchema as SeqSchema,
    String,
    drop
)
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
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_HTML, CONTENT_TYPE_TEXT_PLAIN
from weaver.owsexceptions import OWSMissingParameterValue
from weaver.sort import JOB_SORT_VALUES, QUOTE_SORT_VALUES, SORT_CREATED, SORT_ID, SORT_PROCESS
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_ACCEPTED, STATUS_COMPLIANT_OGC
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_VALUES
from weaver.wps_restapi.colander_extras import (
    DropableNoneSchema,
    OneOfCaseInsensitive,
    OneOfMappingSchema,
    SchemaNodeDefault,
    VariableMappingSchema
)
from weaver.wps_restapi.utils import wps_restapi_base_path

if TYPE_CHECKING:
    from weaver.typedefs import SettingsType, TypedDict

    ViewInfo = TypedDict("ViewInfo", {"name": str, "pattern": str})


class SchemaNode(SchemaNodeDefault):
    """
    Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
    actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

    .. seealso::
        Implementation in :class:`SchemaNodeDefault`.
    """
    @staticmethod
    def schema_type():
        raise NotImplementedError


class SequenceSchema(DropableNoneSchema, SeqSchema):
    """
    Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
    when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.
    """
    schema_type = SeqSchema.schema_type


class MappingSchema(DropableNoneSchema, MapSchema):
    """
    Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
    when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.
    """
    schema_type = MapSchema.schema_type


class ExplicitMappingSchema(MapSchema):
    """
    Original behaviour of :class:`colander.MappingSchema` implementation, where fields referencing
    to ``None`` values are kept as an explicit indication of an *undefined* or *missing* value for this field.
    """


API_TITLE = "Weaver REST API"
API_INFO = {
    "description": __meta__.__description__,
    "contact": {"name": __meta__.__authors__, "email": __meta__.__emails__, "url": __meta__.__source_repository__}
}
URL = "url"

#########################################################################
# API endpoints
#########################################################################

api_frontpage_uri = "/"
api_swagger_ui_uri = "/api"
api_swagger_json_uri = "/json"
api_versions_uri = "/versions"
api_conformance_uri = "/conformance"

processes_uri = "/processes"
process_uri = "/processes/{process_id}"
process_package_uri = "/processes/{process_id}/package"
process_payload_uri = "/processes/{process_id}/payload"
process_visibility_uri = "/processes/{process_id}/visibility"
process_jobs_uri = "/processes/{process_id}/jobs"
process_job_uri = "/processes/{process_id}/jobs/{job_id}"
process_quotes_uri = "/processes/{process_id}/quotations"
process_quote_uri = "/processes/{process_id}/quotations/{quote_id}"
process_results_uri = "/processes/{process_id}/jobs/{job_id}/result"
process_exceptions_uri = "/processes/{process_id}/jobs/{job_id}/exceptions"
process_logs_uri = "/processes/{process_id}/jobs/{job_id}/logs"

providers_uri = "/providers"
provider_uri = "/providers/{provider_id}"

provider_processes_uri = "/providers/{provider_id}/processes"
provider_process_uri = "/providers/{provider_id}/processes/{process_id}"

jobs_short_uri = "/jobs"
jobs_full_uri = "/providers/{provider_id}/processes/{process_id}/jobs"
job_full_uri = "/providers/{provider_id}/processes/{process_id}/jobs/{job_id}"
job_exceptions_uri = "/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions"
job_short_uri = "/jobs/{job_id}"

quotes_uri = "/quotations"
quote_uri = "/quotations/{quote_id}"
bills_uri = "/bills"
bill_uri = "/bill/{bill_id}"

results_full_uri = "/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/result"
results_short_uri = "/jobs/{job_id}/result"
result_full_uri = "/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/result/{result_id}"
result_short_uri = "/jobs/{job_id}/result/{result_id}"

exceptions_full_uri = "/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions"
exceptions_short_uri = "/jobs/{job_id}/exceptions"

logs_full_uri = "/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/logs"
logs_short_uri = "/jobs/{job_id}/logs"

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
# These "services" are wrappers that allow Cornice to generate the JSON API
###############################################################################

api_frontpage_service = Service(name="api_frontpage", path=api_frontpage_uri)
api_swagger_ui_service = Service(name="api_swagger_ui", path=api_swagger_ui_uri)
api_swagger_json_service = Service(name="api_swagger_json", path=api_swagger_json_uri)
api_versions_service = Service(name="api_versions", path=api_versions_uri)
api_conformance_service = Service(name="api_conformance", path=api_conformance_uri)

processes_service = Service(name="processes", path=processes_uri)
process_service = Service(name="process", path=process_uri)
process_package_service = Service(name="process_package", path=process_package_uri)
process_payload_service = Service(name="process_payload", path=process_payload_uri)
process_visibility_service = Service(name="process_visibility", path=process_visibility_uri)
process_jobs_service = Service(name="process_jobs", path=process_jobs_uri)
process_job_service = Service(name="process_job", path=process_job_uri)
process_quotes_service = Service(name="process_quotes", path=process_quotes_uri)
process_quote_service = Service(name="process_quote", path=process_quote_uri)
process_results_service = Service(name="process_results", path=process_results_uri)
process_exceptions_service = Service(name="process_exceptions", path=process_exceptions_uri)
process_logs_service = Service(name="process_logs", path=process_logs_uri)

providers_service = Service(name="providers", path=providers_uri)
provider_service = Service(name="provider", path=provider_uri)

provider_processes_service = Service(name="provider_processes", path=provider_processes_uri)
provider_process_service = Service(name="provider_process", path=provider_process_uri)

jobs_short_service = Service(name="jobs_short", path=jobs_short_uri)
jobs_full_service = Service(name="jobs_full", path=jobs_full_uri)
job_full_service = Service(name="job_full", path=job_full_uri)
job_short_service = Service(name="job_short", path=job_short_uri)

quotes_service = Service(name="quotes", path=quotes_uri)
quote_service = Service(name="quote", path=quote_uri)
bills_service = Service(name="bills", path=bills_uri)
bill_service = Service(name="bill", path=bill_uri)

results_full_service = Service(name="results_full", path=results_full_uri)
results_short_service = Service(name="results_short", path=results_short_uri)

exceptions_full_service = Service(name="exceptions_full", path=exceptions_full_uri)
exceptions_short_service = Service(name="exceptions_short", path=exceptions_short_uri)

logs_full_service = Service(name="logs_full", path=logs_full_uri)
logs_short_service = Service(name="logs_short", path=logs_short_uri)

#########################################################
# Path parameter definitions
#########################################################


class ProcessPath(MappingSchema):
    process_id = SchemaNode(String(), description="The process id")


class ProviderPath(MappingSchema):
    provider_id = SchemaNode(String(), description="The provider id")


class JobPath(MappingSchema):
    job_id = SchemaNode(String(), description="The job id")


class BillPath(MappingSchema):
    bill_id = SchemaNode(String(), description="The bill id")


class QuotePath(MappingSchema):
    quote_id = SchemaNode(String(), description="The quote id")


class ResultPath(MappingSchema):
    result_id = SchemaNode(String(), description="The result id")


#########################################################
# Generic schemas
#########################################################


class JsonHeader(MappingSchema):
    content_type = SchemaNode(String(), example=CONTENT_TYPE_APP_JSON, default=CONTENT_TYPE_APP_JSON)
    content_type.name = "Content-Type"


class HtmlHeader(MappingSchema):
    content_type = SchemaNode(String(), example=CONTENT_TYPE_TEXT_HTML, default=CONTENT_TYPE_TEXT_HTML)
    content_type.name = "Content-Type"


class XmlHeader(MappingSchema):
    content_type = SchemaNode(String(), example=CONTENT_TYPE_APP_XML, default=CONTENT_TYPE_APP_XML)
    content_type.name = "Content-Type"


class AcceptHeader(MappingSchema):
    Accept = SchemaNode(String(), missing=drop, default=CONTENT_TYPE_APP_JSON, validator=OneOf([
        CONTENT_TYPE_APP_JSON,
        CONTENT_TYPE_APP_XML,
        CONTENT_TYPE_TEXT_HTML,
    ]))


class AcceptLanguageHeader(AcceptHeader):
    AcceptLanguage = SchemaNode(String(), missing=drop)
    AcceptLanguage.name = "Accept-Language"


class KeywordList(SequenceSchema):
    keyword = SchemaNode(String())


class JsonLink(MappingSchema):
    href = SchemaNode(String(), format=URL, description="Reference URL.")
    rel = SchemaNode(String(), description="Relationship of the contained link respective to the current element.")
    type = SchemaNode(String(), missing=drop)
    hreflang = SchemaNode(String(), missing=drop)
    title = SchemaNode(String(), missing=drop)


class MetadataBase(MappingSchema):
    title = SchemaNode(String(), missing=drop)
    role = SchemaNode(String(), format=URL, missing=drop)
    type = SchemaNode(String(), description="Type of metadata entry.")


class MetadataLink(MetadataBase, JsonLink):
    pass


class MetadataValue(MetadataBase):
    value = SchemaNode(String())
    lang = SchemaNode(String())


class Metadata(OneOfMappingSchema):
    _one_of = (MetadataLink, MetadataValue)


class MetadataList(SequenceSchema):
    item = Metadata()


class JsonLinkList(SequenceSchema):
    item = JsonLink()


class LandingPage(MappingSchema):
    links = JsonLinkList()


class Format(MappingSchema):
    mimeType = SchemaNode(String(), default=CONTENT_TYPE_TEXT_PLAIN)
    schema = SchemaNode(String(), missing=drop)
    encoding = SchemaNode(String(), missing=drop)


class FormatDescription(Format):
    maximumMegabytes = SchemaNode(Integer(), missing=drop)
    default = SchemaNode(Boolean(), missing=drop, default=False)


class FormatDescriptionList(SequenceSchema):
    format = FormatDescription()


class AdditionalParameterValuesList(SequenceSchema):
    values = SchemaNode(String())


class AdditionalParameter(MappingSchema):
    name = SchemaNode(String())
    values = AdditionalParameterValuesList()


class AdditionalParameterList(SequenceSchema):
    item = AdditionalParameter()


class AdditionalParameters(MappingSchema):
    role = SchemaNode(String(), missing=drop)
    parameters = AdditionalParameterList(missing=drop)


class AdditionalParametersList(SequenceSchema):
    additionalParameter = AdditionalParameters()


class Content(MappingSchema):
    href = SchemaNode(String(), format=URL, description="URL to CWL file.", title="href",
                      example="http://some.host/applications/cwl/multisensor_ndvi.cwl")


class Offering(MappingSchema):
    code = SchemaNode(String(), missing=drop, description="Descriptor of represented information in 'content'.")
    content = Content(title="content", missing=drop)


class OWSContext(MappingSchema):
    offering = Offering(title="offering")


class DescriptionType(MappingSchema):
    id = SchemaNode(String())
    title = SchemaNode(String(), missing=drop)
    abstract = SchemaNode(String(), missing=drop)
    keywords = KeywordList(missing=drop)
    owsContext = OWSContext(missing=drop, title="owsContext")
    metadata = MetadataList(missing=drop)
    additionalParameters = AdditionalParametersList(missing=drop, title="additionalParameters")
    links = JsonLinkList(missing=drop, title="links")


class MinMaxOccursInt(MappingSchema):
    minOccurs = SchemaNode(Integer(), missing=drop)
    maxOccurs = SchemaNode(Integer(), missing=drop)


class MinMaxOccursStr(MappingSchema):
    minOccurs = SchemaNode(String(), missing=drop)
    maxOccurs = SchemaNode(String(), missing=drop)


class WithMinMaxOccurs(OneOfMappingSchema):
    _one_of = (MinMaxOccursStr, MinMaxOccursInt)


class ComplexInputType(DescriptionType, WithMinMaxOccurs):
    formats = FormatDescriptionList()


class SupportedCrs(MappingSchema):
    crs = SchemaNode(String(), format=URL)
    default = SchemaNode(Boolean(), missing=drop)


class SupportedCrsList(SequenceSchema):
    item = SupportedCrs()


class BoundingBoxInputType(DescriptionType, WithMinMaxOccurs):
    supportedCRS = SupportedCrsList()


class DataTypeSchema(MappingSchema):
    name = SchemaNode(String())
    reference = SchemaNode(String(), format=URL, missing=drop)


class UomSchema(DataTypeSchema):
    pass


class AllowedValuesList(SequenceSchema):
    allowedValues = SchemaNode(String())


class AllowedValues(MappingSchema):
    allowedValues = AllowedValuesList()


class AllowedRange(MappingSchema):
    minimumValue = SchemaNode(String(), missing=drop)
    maximumValue = SchemaNode(String(), missing=drop)
    spacing = SchemaNode(String(), missing=drop)
    rangeClosure = SchemaNode(String(), missing=drop,
                              validator=OneOf(["closed", "open", "open-closed", "closed-open"]))


class AllowedRangesList(SequenceSchema):
    allowedRanges = AllowedRange()


class AllowedRanges(MappingSchema):
    allowedRanges = AllowedRangesList()


class AnyValue(MappingSchema):
    anyValue = SchemaNode(Boolean(), missing=drop, default=True)


class ValuesReference(MappingSchema):
    valueReference = SchemaNode(String(), format=URL, )


class LiteralDataDomainType(OneOfMappingSchema):
    _one_of = (AllowedValues,
               AllowedRanges,
               ValuesReference,
               AnyValue)  # must be last because it"s the most permissive
    defaultValue = SchemaNode(String(), missing=drop)
    dataType = DataTypeSchema(missing=drop)
    uom = UomSchema(missing=drop)


class LiteralDataDomainTypeList(SequenceSchema):
    literalDataDomain = LiteralDataDomainType()


class LiteralInputType(DescriptionType, WithMinMaxOccurs):
    literalDataDomains = LiteralDataDomainTypeList(missing=drop)


class InputType(OneOfMappingSchema):
    _one_of = (
        BoundingBoxInputType,
        ComplexInputType,  # should be 2nd to last because very permission, but requires format at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    )


class InputTypeList(SequenceSchema):
    input = InputType()


class LiteralOutputType(MappingSchema):
    literalDataDomains = LiteralDataDomainTypeList(missing=drop)


class BoundingBoxOutputType(MappingSchema):
    supportedCRS = SupportedCrsList()


class ComplexOutputType(MappingSchema):
    formats = FormatDescriptionList()


class OutputDataDescriptionType(DescriptionType):
    pass


class OutputType(OneOfMappingSchema, OutputDataDescriptionType):
    _one_of = (
        BoundingBoxOutputType,
        ComplexOutputType,  # should be 2nd to last because very permission, but requires format at least
        LiteralOutputType,  # must be last because it"s the most permissive (all can default if omitted)
    )


class OutputDescriptionList(SequenceSchema):
    item = OutputType()


class JobExecuteModeEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobExecuteModeEnum, self).__init__(
            self.schema_type(),
            title=kwargs.get("title", "mode"),
            default=kwargs.get("default", EXECUTE_MODE_AUTO),
            example=kwargs.get("example", EXECUTE_MODE_ASYNC),
            validator=OneOf(list(EXECUTE_MODE_OPTIONS)),
            **kwargs)


class JobControlOptionsEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobControlOptionsEnum, self).__init__(
            self.schema_type(),
            title="jobControlOptions",
            default=kwargs.get("default", EXECUTE_CONTROL_OPTION_ASYNC),
            example=kwargs.get("example", EXECUTE_CONTROL_OPTION_ASYNC),
            validator=OneOf(list(EXECUTE_CONTROL_OPTIONS)),
            **kwargs)


class JobResponseOptionsEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobResponseOptionsEnum, self).__init__(
            self.schema_type(),
            title=kwargs.get("title", "response"),
            default=kwargs.get("default", EXECUTE_RESPONSE_RAW),
            example=kwargs.get("example", EXECUTE_RESPONSE_RAW),
            validator=OneOf(list(EXECUTE_RESPONSE_OPTIONS)),
            **kwargs)


class TransmissionModeEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(TransmissionModeEnum, self).__init__(
            self.schema_type(),
            title=kwargs.get("title", "transmissionMode"),
            default=kwargs.get("default", EXECUTE_TRANSMISSION_MODE_REFERENCE),
            example=kwargs.get("example", EXECUTE_TRANSMISSION_MODE_REFERENCE),
            validator=OneOf(list(EXECUTE_TRANSMISSION_MODE_OPTIONS)),
            **kwargs)


class JobStatusEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobStatusEnum, self).__init__(
            self.schema_type(),
            default=kwargs.get("default", None),
            example=kwargs.get("example", STATUS_ACCEPTED),
            validator=OneOf(list(JOB_STATUS_CATEGORIES[STATUS_COMPLIANT_OGC])),
            **kwargs)


class JobSortEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)   # ignore passed argument and enforce the validator
        super(JobSortEnum, self).__init__(
            String(),
            default=kwargs.get("default", SORT_CREATED),
            example=kwargs.get("example", SORT_CREATED),
            validator=OneOf(list(JOB_SORT_VALUES)),
            **kwargs)


class QuoteSortEnum(SchemaNode):
    schema_type = String

    def __init__(self, *args, **kwargs):    # noqa: E811
        kwargs.pop("validator", None)  # ignore passed argument and enforce the validator
        super(QuoteSortEnum, self).__init__(
            self.schema_type(),
            default=kwargs.get("default", SORT_ID),
            example=kwargs.get("example", SORT_PROCESS),
            validator=OneOf(list(QUOTE_SORT_VALUES)),
            **kwargs)


class LaunchJobQuerystring(MappingSchema):
    tags = SchemaNode(String(), default=None, missing=drop,
                      description="Comma separated tags that can be used to filter jobs later")


class VisibilityValue(SchemaNode):
    schema_type = String
    validator = OneOf(list(VISIBILITY_VALUES))
    example = VISIBILITY_PUBLIC


class Visibility(MappingSchema):
    value = VisibilityValue()


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class FrontpageEndpoint(MappingSchema):
    header = AcceptHeader()


class VersionsEndpoint(MappingSchema):
    header = AcceptHeader()


class ConformanceEndpoint(MappingSchema):
    header = AcceptHeader()


class SwaggerJSONEndpoint(MappingSchema):
    header = AcceptHeader()


class SwaggerUIEndpoint(MappingSchema):
    pass


class WPSParameters(MappingSchema):
    service = SchemaNode(String(), example="WPS", description="Service selection.",
                         validator=OneOfCaseInsensitive(["WPS"]))
    request = SchemaNode(String(), example="GetCapabilities", description="WPS operation to accomplish",
                         validator=OneOfCaseInsensitive(["GetCapabilities", "DescribeProcess", "Execute"]))
    version = SchemaNode(String(), exaple="1.0.0", default="1.0.0", validator=OneOf(["1.0.0", "2.0.0"]))
    identifier = SchemaNode(String(), exaple="hello", description="Process identifier.", missing=drop)
    data_inputs = SchemaNode(String(), name="DataInputs", missing=drop, example="message=hi",
                             description="Process execution inputs provided as Key-Value Pairs (KVP).")


class WPSBody(MappingSchema):
    content = SchemaNode(String(), description="XML data inputs provided for WPS POST request.")


class WPSEndpoint(MappingSchema):
    header = AcceptHeader()
    querystring = WPSParameters()
    body = WPSBody()


class WPSXMLSuccessBodySchema(MappingSchema):
    pass


class OkWPSResponse(MappingSchema):
    description = "WPS operation successful"
    header = XmlHeader()
    body = WPSXMLSuccessBodySchema()


class WPSXMLErrorBodySchema(MappingSchema):
    pass


class ErrorWPSResponse(MappingSchema):
    description = "Unhandled error occurred on WPS endpoint."
    header = XmlHeader()
    body = WPSXMLErrorBodySchema()


class ProviderEndpoint(ProviderPath):
    header = AcceptHeader()


class ProviderProcessEndpoint(ProviderPath, ProcessPath):
    header = AcceptHeader()


class ProcessEndpoint(ProcessPath):
    header = AcceptHeader()


class ProcessPackageEndpoint(ProcessPath):
    header = AcceptHeader()


class ProcessPayloadEndpoint(ProcessPath):
    header = AcceptHeader()


class ProcessVisibilityGetEndpoint(ProcessPath):
    header = AcceptHeader()


class ProcessVisibilityPutEndpoint(ProcessPath):
    header = AcceptHeader()
    body = Visibility()


class FullJobEndpoint(ProviderPath, ProcessPath, JobPath):
    header = AcceptHeader()


class ShortJobEndpoint(JobPath):
    header = AcceptHeader()


class ProcessResultsEndpoint(ProcessPath, JobPath):
    header = AcceptHeader()


class FullResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = AcceptHeader()


class ShortResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = AcceptHeader()


class FullExceptionsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = AcceptHeader()


class ShortExceptionsEndpoint(JobPath):
    header = AcceptHeader()


class ProcessExceptionsEndpoint(ProcessPath, JobPath):
    header = AcceptHeader()


class FullLogsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = AcceptHeader()


class ShortLogsEndpoint(JobPath):
    header = AcceptHeader()


class ProcessLogsEndpoint(ProcessPath, JobPath):
    header = AcceptHeader()


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class CreateProviderRequestBody(MappingSchema):
    id = SchemaNode(String())
    url = SchemaNode(String())
    public = SchemaNode(Boolean())


class InputDataType(MappingSchema):
    id = SchemaNode(String())


class OutputDataType(MappingSchema):
    id = SchemaNode(String())
    format = Format(missing=drop)


class Output(OutputDataType):
    transmissionMode = TransmissionModeEnum(missing=drop)


class OutputList(SequenceSchema):
    output = Output()


class ProviderSummarySchema(MappingSchema):
    """WPS provider summary definition."""
    id = SchemaNode(String())
    url = SchemaNode(String())
    title = SchemaNode(String())
    abstract = SchemaNode(String())
    public = SchemaNode(Boolean())


class ProviderCapabilitiesSchema(MappingSchema):
    """WPS provider capabilities."""
    id = SchemaNode(String())
    url = SchemaNode(String())
    title = SchemaNode(String())
    abstract = SchemaNode(String())
    contact = SchemaNode(String())
    type = SchemaNode(String())


class TransmissionModeList(SequenceSchema):
    item = TransmissionModeEnum(missing=drop)


class JobControlOptionsList(SequenceSchema):
    item = JobControlOptionsEnum(missing=drop)


class ExceptionReportType(MappingSchema):
    code = SchemaNode(String())
    description = SchemaNode(String(), missing=drop)


class ProcessSummary(DescriptionType):
    """WPS process definition."""
    version = SchemaNode(String(), missing=drop)
    jobControlOptions = JobControlOptionsList(missing=drop)
    outputTransmission = TransmissionModeList(missing=drop)
    processDescriptionURL = SchemaNode(String(), format=URL, missing=drop)


class ProcessSummaryList(SequenceSchema):
    item = ProcessSummary()


class ProcessCollection(MappingSchema):
    processes = ProcessSummaryList()


class Process(DescriptionType):
    inputs = InputTypeList(missing=drop)
    outputs = OutputDescriptionList(missing=drop)
    visibility = VisibilityValue(missing=drop)
    executeEndpoint = SchemaNode(String(), format=URL, missing=drop)


class ProcessOutputDescriptionSchema(MappingSchema):
    """WPS process output definition."""
    dataType = SchemaNode(String())
    defaultValue = MappingSchema()
    id = SchemaNode(String())
    abstract = SchemaNode(String())
    title = SchemaNode(String())


class JobStatusInfo(MappingSchema):
    jobID = SchemaNode(String(), example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the job.")
    status = JobStatusEnum()
    message = SchemaNode(String(), missing=drop)
    # fixme: use href links (https://github.com/crim-ca/weaver/issues/58) [logs/result/exceptions]
    logs = SchemaNode(String(), missing=drop)
    result = SchemaNode(String(), missing=drop)
    exceptions = SchemaNode(String(), missing=drop)
    expirationDate = SchemaNode(DateTime(), missing=drop)
    estimatedCompletion = SchemaNode(DateTime(), missing=drop)
    duration = SchemaNode(String(), missing=drop, description="Duration of the process execution.")
    nextPoll = SchemaNode(DateTime(), missing=drop)
    percentCompleted = SchemaNode(Integer(), example=0, validator=Range(min=0, max=100))


class JobEntrySchema(OneOfMappingSchema):
    _one_of = (
        JobStatusInfo,
        SchemaNode(String(), description="Job ID."),
    )
    # note:
    #   Since JobId is a simple string (not a dict), no additional mapping field can be added here.
    #   They will be discarded by `OneOfMappingSchema.deserialize()`.


class JobCollection(SequenceSchema):
    item = JobEntrySchema()


class CreatedJobStatusSchema(MappingSchema):
    status = SchemaNode(String(), example=STATUS_ACCEPTED)
    location = SchemaNode(String(), example="http://{host}/weaver/processes/{my-process-id}/jobs/{my-job-id}")
    jobID = SchemaNode(String(), example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the created job.")


class CreatedQuotedJobStatusSchema(CreatedJobStatusSchema):
    bill = SchemaNode(String(), example="d88fda5c-52cc-440b-9309-f2cd20bcd6a2", description="ID of the created bill.")


class GetPagingJobsSchema(MappingSchema):
    jobs = JobCollection()
    limit = SchemaNode(Integer())
    page = SchemaNode(Integer())


class GroupedJobsCategorySchema(MappingSchema):
    category = VariableMappingSchema(description="Grouping values that compose the corresponding job list category.")
    jobs = JobCollection(description="List of jobs that matched the corresponding grouping values.")
    count = SchemaNode(Integer(), description="Number of matching jobs for the corresponding group category.")


class GroupedCategoryJobsSchema(SequenceSchema):
    job_group_category_item = GroupedJobsCategorySchema()


class GetGroupedJobsSchema(MappingSchema):
    groups = GroupedCategoryJobsSchema()


class GetQueriedJobsSchema(OneOfMappingSchema):
    _one_of = (
        GetPagingJobsSchema,
        GetGroupedJobsSchema,
    )
    total = SchemaNode(Integer(), description="Total number of matched jobs regardless of grouping or paging result.")


class DismissedJobSchema(MappingSchema):
    status = JobStatusEnum()
    jobID = SchemaNode(String(), example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the job.")
    message = SchemaNode(String(), example="Job dismissed.")
    percentCompleted = SchemaNode(Integer(), example=0)


class QuoteProcessParametersSchema(MappingSchema):
    inputs = InputTypeList(missing=drop)
    outputs = OutputDescriptionList(missing=drop)
    mode = JobExecuteModeEnum(missing=drop)
    response = JobResponseOptionsEnum(missing=drop)


class AlternateQuotation(MappingSchema):
    id = SchemaNode(String(), description="Quote ID.")
    title = SchemaNode(String(), description="Name of the quotation.", missing=drop)
    description = SchemaNode(String(), description="Description of the quotation.", missing=drop)
    price = SchemaNode(Float(), description="Process execution price.")
    currency = SchemaNode(String(), description="Currency code in ISO-4217 format.")
    expire = SchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = SchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    details = SchemaNode(String(), description="Details of the quotation.", missing=drop)
    estimatedTime = SchemaNode(String(), description="Estimated duration of the process execution.", missing=drop)


class AlternateQuotationList(SequenceSchema):
    step = AlternateQuotation(description="Quote of a workflow step process.")


class Reference(MappingSchema):
    href = SchemaNode(String())
    mimeType = SchemaNode(String(), missing=drop)
    schema = SchemaNode(String(), missing=drop)
    encoding = SchemaNode(String(), missing=drop)
    body = SchemaNode(String(), missing=drop)
    bodyReference = SchemaNode(String(), missing=drop, format=URL)


class DataEncodingAttributes(MappingSchema):
    mimeType = SchemaNode(String(), missing=drop)
    schema = SchemaNode(String(), missing=drop)
    encoding = SchemaNode(String(), missing=drop)


class DataFloat(DataEncodingAttributes):
    data = SchemaNode(Float())


class DataInteger(DataEncodingAttributes):
    data = SchemaNode(Integer())


class DataString(DataEncodingAttributes):
    data = SchemaNode(String())


class DataBoolean(DataEncodingAttributes):
    data = SchemaNode(Boolean())


class ValueType(OneOfMappingSchema):
    _one_of = (DataFloat,
               DataInteger,
               DataString,
               DataBoolean,
               Reference)


class Input(InputDataType, ValueType):
    pass


class InputList(SequenceSchema):
    item = Input(missing=drop)


class Execute(MappingSchema):
    inputs = InputList(missing=drop)
    outputs = OutputList()
    mode = SchemaNode(String(), validator=OneOf(list(EXECUTE_MODE_OPTIONS)))
    notification_email = SchemaNode(
        String(),
        missing=drop,
        description="Optionally send a notification email when the job is done.")
    response = SchemaNode(String(), validator=OneOf(list(EXECUTE_RESPONSE_OPTIONS)))


class Quotation(MappingSchema):
    id = SchemaNode(String(), description="Quote ID.")
    title = SchemaNode(String(), description="Name of the quotation.", missing=drop)
    description = SchemaNode(String(), description="Description of the quotation.", missing=drop)
    processId = SchemaNode(String(), description="Corresponding process ID.")
    price = SchemaNode(Float(), description="Process execution price.")
    currency = SchemaNode(String(), description="Currency code in ISO-4217 format.")
    expire = SchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = SchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    userId = SchemaNode(String(), description="User id that requested the quote.")
    details = SchemaNode(String(), description="Details of the quotation.", missing=drop)
    estimatedTime = SchemaNode(String(), description="Estimated duration of the process execution.", missing=drop)
    processParameters = Execute()
    alternativeQuotations = AlternateQuotationList(missing=drop)


class QuoteProcessListSchema(SequenceSchema):
    step = Quotation(description="Quote of a workflow step process.")


class QuoteSchema(MappingSchema):
    id = SchemaNode(String(), description="Quote ID.")
    process = SchemaNode(String(), description="Corresponding process ID.")
    steps = QuoteProcessListSchema(description="Child processes and prices.")
    total = SchemaNode(Float(), description="Total of the quote including step processes.")


class QuotationList(SequenceSchema):
    item = SchemaNode(String(), description="Bill ID.")


class QuotationListSchema(MappingSchema):
    quotations = QuotationList()


class BillSchema(MappingSchema):
    id = SchemaNode(String(), description="Bill ID.")
    title = SchemaNode(String(), description="Name of the bill.")
    description = SchemaNode(String(), missing=drop)
    price = SchemaNode(Float(), description="Price associated to the bill.")
    currency = SchemaNode(String(), description="Currency code in ISO-4217 format.")
    created = SchemaNode(DateTime(), description="Creation date and time of the bill in ISO-8601 format.")
    userId = SchemaNode(String(), description="User id that requested the quote.")
    quotationId = SchemaNode(String(), description="Corresponding quote ID.", missing=drop)


class BillList(SequenceSchema):
    item = SchemaNode(String(), description="Bill ID.")


class BillListSchema(MappingSchema):
    bills = BillList()


class SupportedValues(MappingSchema):
    pass


class DefaultValues(MappingSchema):
    pass


class Unit(MappingSchema):
    pass


class UnitType(MappingSchema):
    unit = Unit()


class ProcessInputDescriptionSchema(MappingSchema):
    minOccurs = SchemaNode(Integer())
    maxOccurs = SchemaNode(Integer())
    title = SchemaNode(String())
    dataType = SchemaNode(String())
    abstract = SchemaNode(String())
    id = SchemaNode(String())
    defaultValue = SequenceSchema(DefaultValues())
    supportedValues = SequenceSchema(SupportedValues())


class ProcessDescriptionSchema(MappingSchema):
    outputs = SequenceSchema(ProcessOutputDescriptionSchema())
    inputs = SequenceSchema(ProcessInputDescriptionSchema())
    description = SchemaNode(String())
    id = SchemaNode(String())
    label = SchemaNode(String())


class UndeploymentResult(MappingSchema):
    id = SchemaNode(String())


class DeploymentResult(MappingSchema):
    processSummary = ProcessSummary()


class ProcessDescriptionBodySchema(MappingSchema):
    process = ProcessDescriptionSchema()


class ProvidersSchema(SequenceSchema):
    providers_service = ProviderSummarySchema()


class JobOutputSchema(MappingSchema):
    id = SchemaNode(String(), description="Job output id corresponding to process description outputs.")
    data = SchemaNode(String(), missing=drop)
    href = SchemaNode(String(), format=URL, missing=drop)
    mimeType = SchemaNode(String(), missing=drop)
    schema = SchemaNode(String(), missing=drop)
    encoding = SchemaNode(String(), missing=drop)


class JobOutputsSchema(SequenceSchema):
    output = JobOutputSchema()


class OutputInfo(OutputDataType, OneOfMappingSchema):
    _one_of = (DataFloat,
               DataInteger,
               DataString,
               DataBoolean,
               Reference)


class OutputInfoList(SequenceSchema):
    output = OutputInfo()


class ExceptionTextList(SequenceSchema):
    text = SchemaNode(String())


class ExceptionSchema(MappingSchema):
    Code = SchemaNode(String())
    Locator = SchemaNode(String())
    Text = ExceptionTextList()


class ExceptionsOutputSchema(SequenceSchema):
    exceptions = ExceptionSchema()


class LogsOutputSchema(MappingSchema):
    pass


class FrontpageParameterSchema(MappingSchema):
    name = SchemaNode(String(), example="api")
    enabled = SchemaNode(Boolean(), example=True)
    url = SchemaNode(String(), example="https://weaver-host", missing=drop)
    doc = SchemaNode(String(), example="https://weaver-host/api", missing=drop)


class FrontpageParameters(SequenceSchema):
    param = FrontpageParameterSchema()


class FrontpageSchema(MappingSchema):
    message = SchemaNode(String(), default="Weaver Information", example="Weaver Information")
    configuration = SchemaNode(String(), default="default", example="default")
    parameters = FrontpageParameters()


class SwaggerJSONSpecSchema(MappingSchema):
    pass


class SwaggerUISpecSchema(MappingSchema):
    pass


class VersionsSpecSchema(MappingSchema):
    name = SchemaNode(String(), description="Identification name of the current item.", example="weaver")
    type = SchemaNode(String(), description="Identification type of the current item.", example="api")
    version = SchemaNode(String(), description="Version of the current item.", example="0.1.0")


class VersionsList(SequenceSchema):
    item = VersionsSpecSchema()


class VersionsSchema(MappingSchema):
    versions = VersionsList()


class ConformanceList(SequenceSchema):
    item = SchemaNode(String(), description="Conformance specification link.",
                      example="http://www.opengis.net/spec/wfs-1/3.0/req/core")


class ConformanceSchema(MappingSchema):
    conformsTo = ConformanceList()


#################################
# Local Processes schemas
#################################


class PackageBody(MappingSchema):
    pass


class ExecutionUnit(MappingSchema):
    _one_of = (Reference,
               UnitType)


class ExecutionUnitList(SequenceSchema):
    item = ExecutionUnit()


class ProcessOffering(MappingSchema):
    processVersion = SchemaNode(String(), missing=drop)
    process = Process()
    processEndpointWPS1 = SchemaNode(String(), missing=drop, format=URL)
    jobControlOptions = JobControlOptionsList(missing=drop)
    outputTransmission = TransmissionModeList(missing=drop)


class ProcessDescriptionChoiceType(OneOfMappingSchema):
    _one_of = (Reference,
               ProcessOffering)


class Deploy(MappingSchema):
    processDescription = ProcessDescriptionChoiceType()
    immediateDeployment = SchemaNode(Boolean(), missing=drop, default=True)
    executionUnit = ExecutionUnitList()
    deploymentProfileName = SchemaNode(String(), missing=drop)
    owsContext = OWSContext(missing=drop)


class PostProcessesEndpoint(MappingSchema):
    header = AcceptHeader()
    body = Deploy(title="Deploy")


class PostProcessJobsEndpoint(ProcessPath):
    header = AcceptLanguageHeader()
    body = Execute()


class GetJobsQueries(MappingSchema):
    detail = SchemaNode(Boolean(), description="Provide job details instead of IDs.",
                        default=False, example=True, missing=drop)
    groups = SchemaNode(String(), description="Comma-separated list of grouping fields with which to list jobs.",
                        default=False, example="process,service", missing=drop)
    page = SchemaNode(Integer(), missing=drop, default=0)
    limit = SchemaNode(Integer(), missing=drop, default=10)
    status = JobStatusEnum(missing=drop)
    process = SchemaNode(String(), missing=drop, default=None)
    provider = SchemaNode(String(), missing=drop, default=None)
    sort = JobSortEnum(missing=drop)
    tags = SchemaNode(String(), missing=drop, default=None,
                      description="Comma-separated values of tags assigned to jobs")


class GetJobsRequest(MappingSchema):
    header = AcceptHeader()
    querystring = GetJobsQueries()


class GetJobsEndpoint(GetJobsRequest):
    pass


class GetProcessJobsEndpoint(GetJobsRequest, ProcessPath):
    pass


class GetProviderJobsEndpoint(GetJobsRequest, ProviderPath, ProcessPath):
    pass


class GetProcessJobEndpoint(ProcessPath):
    header = AcceptHeader()


class DeleteProcessJobEndpoint(ProcessPath):
    header = AcceptHeader()


class BillsEndpoint(MappingSchema):
    header = AcceptHeader()


class BillEndpoint(BillPath):
    header = AcceptHeader()


class ProcessQuotesEndpoint(ProcessPath):
    header = AcceptHeader()


class ProcessQuoteEndpoint(ProcessPath, QuotePath):
    header = AcceptHeader()


class GetQuotesQueries(MappingSchema):
    page = SchemaNode(Integer(), missing=drop, default=0)
    limit = SchemaNode(Integer(), missing=drop, default=10)
    process = SchemaNode(String(), missing=drop, default=None)
    sort = QuoteSortEnum(missing=drop)


class QuotesEndpoint(MappingSchema):
    header = AcceptHeader()
    querystring = GetQuotesQueries()


class QuoteEndpoint(QuotePath):
    header = AcceptHeader()


class PostProcessQuote(ProcessPath, QuotePath):
    header = AcceptHeader()
    body = MappingSchema(default={})


class PostQuote(QuotePath):
    header = AcceptHeader()
    body = MappingSchema(default={})


class PostProcessQuoteRequestEndpoint(ProcessPath, QuotePath):
    header = AcceptHeader()
    body = QuoteProcessParametersSchema()


#################################
# Provider Processes schemas
#################################


class GetProviders(MappingSchema):
    header = AcceptHeader()


class PostProvider(MappingSchema):
    header = AcceptHeader()
    body = CreateProviderRequestBody()


class GetProviderProcesses(MappingSchema):
    header = AcceptHeader()


class GetProviderProcess(MappingSchema):
    header = AcceptHeader()


class PostProviderProcessJobRequest(MappingSchema):
    """Launching a new process request definition."""
    header = AcceptHeader()
    querystring = LaunchJobQuerystring()
    body = Execute()


#################################
# Responses schemas
#################################


class OWSExceptionResponse(MappingSchema):
    code = SchemaNode(String(), description="OWS error code.", example="InvalidParameterValue")
    locator = SchemaNode(String(), description="Indication of the element that caused the error.", example="identifier")
    message = SchemaNode(String(), description="Specific description of the error.", example="Invalid process ID.")


class ErrorJsonResponseBodySchema(MappingSchema):
    code = SchemaNode(Integer(), description="HTTP status code.", example=400)
    status = SchemaNode(String(), description="HTTP status detail.", example="400 Bad Request")
    title = SchemaNode(String(), description="HTTP status message.", example="Bad Request")
    description = SchemaNode(String(), description="", example="Process identifier is invalid.")
    exception = OWSExceptionResponse(missing=drop)


class UnauthorizedJsonResponseSchema(MappingSchema):
    header = JsonHeader()
    body = ErrorJsonResponseBodySchema()


class ForbiddenJsonResponseSchema(MappingSchema):
    header = JsonHeader()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageResponse(MappingSchema):
    header = JsonHeader()
    body = FrontpageSchema()


class OkGetSwaggerJSONResponse(MappingSchema):
    header = JsonHeader()
    body = SwaggerJSONSpecSchema(description="Swagger JSON of weaver API.")


class OkGetSwaggerUIResponse(MappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of weaver API.")


class OkGetVersionsResponse(MappingSchema):
    header = JsonHeader()
    body = VersionsSchema()


class OkGetConformanceResponse(MappingSchema):
    header = JsonHeader()
    body = ConformanceSchema()


class OkGetProvidersListResponse(MappingSchema):
    header = JsonHeader()
    body = ProvidersSchema()


class InternalServerErrorGetProvidersListResponse(MappingSchema):
    description = "Unhandled error occurred during providers listing."


class OkGetProviderCapabilitiesSchema(MappingSchema):
    header = JsonHeader()
    body = ProviderCapabilitiesSchema()


class InternalServerErrorGetProviderCapabilitiesResponse(MappingSchema):
    description = "Unhandled error occurred during provider capabilities request."


class NoContentDeleteProviderSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


class InternalServerErrorDeleteProviderResponse(MappingSchema):
    description = "Unhandled error occurred during provider removal."


class NotImplementedDeleteProviderResponse(MappingSchema):
    description = "Provider removal not supported using referenced storage."


class OkGetProviderProcessesSchema(MappingSchema):
    header = JsonHeader()
    body = ProcessCollection()


class InternalServerErrorGetProviderProcessesListResponse(MappingSchema):
    description = "Unhandled error occurred during provider processes listing."


class GetProcessesQuery(MappingSchema):
    providers = SchemaNode(
        Boolean(), example=True, default=False, missing=drop,
        description="List local processes as well as all sub-processes of all registered providers. "
                    "Applicable only for Weaver in {} mode, false otherwise.".format(WEAVER_CONFIGURATION_EMS))
    detail = SchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class GetProcessesEndpoint(MappingSchema):
    querystring = GetProcessesQuery()


class OkGetProcessesListResponse(MappingSchema):
    header = JsonHeader()
    body = ProcessCollection()


class InternalServerErrorGetProcessesListResponse(MappingSchema):
    description = "Unhandled error occurred during processes listing."


class OkPostProcessDeployBodySchema(MappingSchema):
    deploymentDone = SchemaNode(Boolean(), description="Indicates if the process was successfully deployed.",
                                default=False, example=True)
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = SchemaNode(String(), missing=drop, description="Description of deploy failure if applicable.")


class OkPostProcessesResponse(MappingSchema):
    header = JsonHeader()
    body = OkPostProcessDeployBodySchema()


class InternalServerErrorPostProcessesResponse(MappingSchema):
    description = "Unhandled error occurred during process deployment."


class OkGetProcessInfoResponse(MappingSchema):
    header = JsonHeader()
    body = ProcessOffering()


class BadRequestGetProcessInfoResponse(MappingSchema):
    description = "Missing process identifier."
    body = MappingSchema(default={})


class InternalServerErrorGetProcessResponse(MappingSchema):
    description = "Unhandled error occurred during process description."


class OkGetProcessPackageSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


class InternalServerErrorGetProcessPackageResponse(MappingSchema):
    description = "Unhandled error occurred during process package description."


class OkGetProcessPayloadSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


class InternalServerErrorGetProcessPayloadResponse(MappingSchema):
    description = "Unhandled error occurred during process payload description."


class ProcessVisibilityResponseBodySchema(MappingSchema):
    value = VisibilityValue()


class OkGetProcessVisibilitySchema(MappingSchema):
    header = JsonHeader()
    body = ProcessVisibilityResponseBodySchema()


class InternalServerErrorGetProcessVisibilityResponse(MappingSchema):
    description = "Unhandled error occurred during process visibility retrieval."


class OkPutProcessVisibilitySchema(MappingSchema):
    header = JsonHeader()
    body = ProcessVisibilityResponseBodySchema()


class InternalServerErrorPutProcessVisibilityResponse(MappingSchema):
    description = "Unhandled error occurred during process visibility update."


class OkDeleteProcessUndeployBodySchema(MappingSchema):
    deploymentDone = SchemaNode(Boolean(), description="Indicates if the process was successfully undeployed.",
                                default=False, example=True)
    identifier = SchemaNode(String(), example="workflow")
    failureReason = SchemaNode(String(), missing=drop, description="Description of undeploy failure if applicable.")


class OkDeleteProcessResponse(MappingSchema):
    header = JsonHeader()
    body = OkDeleteProcessUndeployBodySchema()


class InternalServerErrorDeleteProcessResponse(MappingSchema):
    description = "Unhandled error occurred during process deletion."


class OkGetProviderProcessDescriptionResponse(MappingSchema):
    header = JsonHeader()
    body = ProcessDescriptionBodySchema()


class InternalServerErrorGetProviderProcessResponse(MappingSchema):
    description = "Unhandled error occurred during provider process description."


class CreatedPostProvider(MappingSchema):
    header = JsonHeader()
    body = ProviderSummarySchema()


class InternalServerErrorPostProviderResponse(MappingSchema):
    description = "Unhandled error occurred during provider process registration."


class NotImplementedPostProviderResponse(MappingSchema):
    description = "Provider registration not supported using referenced storage."


class CreatedLaunchJobResponse(MappingSchema):
    header = JsonHeader()
    body = CreatedJobStatusSchema()


class InternalServerErrorPostProcessJobResponse(MappingSchema):
    description = "Unhandled error occurred during process job submission."


class InternalServerErrorPostProviderProcessJobResponse(MappingSchema):
    description = "Unhandled error occurred during process job submission."


class OkGetProcessJobResponse(MappingSchema):
    header = JsonHeader()
    body = JobStatusInfo()


class OkDeleteProcessJobResponse(MappingSchema):
    header = JsonHeader()
    body = DismissedJobSchema()


class OkGetQueriedJobsResponse(MappingSchema):
    header = JsonHeader()
    body = GetQueriedJobsSchema()


class InternalServerErrorGetJobsResponse(MappingSchema):
    description = "Unhandled error occurred during jobs listing."


class OkDismissJobResponse(MappingSchema):
    header = JsonHeader()
    body = DismissedJobSchema()


class InternalServerErrorDeleteJobResponse(MappingSchema):
    description = "Unhandled error occurred during job dismiss request."


class OkGetJobStatusResponse(MappingSchema):
    header = JsonHeader()
    body = JobStatusInfo()


class InternalServerErrorGetJobStatusResponse(MappingSchema):
    description = "Unhandled error occurred during provider process description."


class Result(MappingSchema):
    outputs = OutputInfoList()
    links = JsonLinkList(missing=drop)


class OkGetJobResultsResponse(MappingSchema):
    header = JsonHeader()
    body = Result()


class InternalServerErrorGetJobResultsResponse(MappingSchema):
    description = "Unhandled error occurred during job results listing."


class OkGetOutputResponse(MappingSchema):
    header = JsonHeader()
    body = JobOutputSchema()


class InternalServerErrorGetJobOutputResponse(MappingSchema):
    description = "Unhandled error occurred during job results listing."


class CreatedQuoteExecuteResponse(MappingSchema):
    header = JsonHeader()
    body = CreatedQuotedJobStatusSchema()


class InternalServerErrorPostQuoteExecuteResponse(MappingSchema):
    description = "Unhandled error occurred during quote job execution."


class CreatedQuoteRequestResponse(MappingSchema):
    header = JsonHeader()
    body = QuoteSchema()


class InternalServerErrorPostQuoteRequestResponse(MappingSchema):
    description = "Unhandled error occurred during quote submission."


class OkGetQuoteInfoResponse(MappingSchema):
    header = JsonHeader()
    body = QuoteSchema()


class InternalServerErrorGetQuoteInfoResponse(MappingSchema):
    description = "Unhandled error occurred during quote retrieval."


class OkGetQuoteListResponse(MappingSchema):
    header = JsonHeader()
    body = QuotationListSchema()


class InternalServerErrorGetQuoteListResponse(MappingSchema):
    description = "Unhandled error occurred during quote listing."


class OkGetBillDetailResponse(MappingSchema):
    header = JsonHeader()
    body = BillSchema()


class InternalServerErrorGetBillInfoResponse(MappingSchema):
    description = "Unhandled error occurred during bill retrieval."


class OkGetBillListResponse(MappingSchema):
    header = JsonHeader()
    body = BillListSchema()


class InternalServerErrorGetBillListResponse(MappingSchema):
    description = "Unhandled error occurred during bill listing."


class OkGetJobExceptionsResponse(MappingSchema):
    header = JsonHeader()
    body = ExceptionsOutputSchema()


class InternalServerErrorGetJobExceptionsResponse(MappingSchema):
    description = "Unhandled error occurred during job exceptions listing."


class OkGetJobLogsResponse(MappingSchema):
    header = JsonHeader()
    body = LogsOutputSchema()


class InternalServerErrorGetJobLogsResponse(MappingSchema):
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
    # FIXME:
    #   status should be 201 when properly modified to match API conformance
    #   https://github.com/crim-ca/weaver/issues/14
    "200": OkPostProcessesResponse(description="success"),
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
    "400": MappingSchema(description=OWSMissingParameterValue.explanation),
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
get_job_results_responses = {
    "200": OkGetJobResultsResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobResultsResponse(),
}
get_job_output_responses = {
    "200": OkGetOutputResponse(description="success"),
    "401": UnauthorizedJsonResponseSchema(description="unauthorized"),
    "403": UnauthorizedJsonResponseSchema(description="forbidden"),
    "500": InternalServerErrorGetJobOutputResponse(),
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
