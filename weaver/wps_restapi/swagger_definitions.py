"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""

from weaver import __meta__
from weaver.config import WEAVER_CONFIGURATION_EMS
from weaver.wps_restapi.utils import wps_restapi_base_path
from weaver.status import job_status_categories, STATUS_ACCEPTED, STATUS_COMPLIANT_OGC
from weaver.sort import job_sort_values, quote_sort_values, SORT_CREATED, SORT_ID, SORT_PROCESS
from weaver.formats import CONTENT_TYPE_TEXT_HTML, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_PLAIN
from weaver.execute import (
    EXECUTE_MODE_AUTO,
    EXECUTE_MODE_ASYNC,
    execute_mode_options,
    EXECUTE_CONTROL_OPTION_ASYNC,
    execute_control_options,
    EXECUTE_RESPONSE_RAW,
    execute_response_options,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
    execute_transmission_mode_options,
)
from weaver.visibility import visibility_values, VISIBILITY_PUBLIC
from weaver.wps_restapi.colander_extras import OneOfMappingSchema, SchemaNodeDefault as SchemaNode
from colander import String, Boolean, Integer, Float, DateTime, MappingSchema, SequenceSchema, drop, OneOf
from cornice import Service

API_TITLE = "weaver REST API"
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
TAG_PROVIDER_PROCESS = "Provider Processes"
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

###############################################################################
# These "services" are wrappers that allow Cornice to generate the JSON API
###############################################################################

api_frontpage_service = Service(name="api_frontpage", path=api_frontpage_uri)
api_swagger_ui_service = Service(name="api_swagger_ui", path=api_swagger_ui_uri)
api_swagger_json_service = Service(name="api_swagger_json", path=api_swagger_json_uri)
api_versions_service = Service(name="api_versions", path=api_versions_uri)

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


class KeywordList(SequenceSchema):
    keyword = SchemaNode(String())


class JsonLink(MappingSchema):
    href = SchemaNode(String(), format=URL)
    rel = SchemaNode(String(), missing=drop)
    type = SchemaNode(String(), missing=drop)
    hreflang = SchemaNode(String(), missing=drop)
    title = SchemaNode(String(), missing=drop)


class Metadata(JsonLink):
    role = SchemaNode(String(), format=URL, missing=drop)
    value = SchemaNode(String(), missing=drop)


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


class Range(MappingSchema):
    minimumValue = SchemaNode(String(), missing=drop)
    maximumValue = SchemaNode(String(), missing=drop)
    spacing = SchemaNode(String(), missing=drop)
    rangeClosure = SchemaNode(String(), missing=drop,
                              validator=OneOf(["closed", "open", "open-closed", "closed-open"]))


class AllowedRangesList(SequenceSchema):
    allowedRanges = Range()


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
               AnyValue)  # must be last because it's the most permissive
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
        LiteralInputType,  # must be last because it's the most permissive (all can default if omitted)
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
        LiteralOutputType,  # must be last because it's the most permissive (all can default if omitted)
    )


class OutputDescriptionList(SequenceSchema):
    item = OutputType()


class JobExecuteModeEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(JobExecuteModeEnum, self).__init__(
            String(),
            title=kwargs.get('title', 'mode'),
            default=kwargs.get('default', EXECUTE_MODE_AUTO),
            example=kwargs.get('example', EXECUTE_MODE_ASYNC),
            validator=OneOf(list(execute_mode_options)),
            **kwargs)


class JobControlOptionsEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(JobControlOptionsEnum, self).__init__(
            String(),
            title='jobControlOptions',
            default=kwargs.get('default', EXECUTE_CONTROL_OPTION_ASYNC),
            example=kwargs.get('example', EXECUTE_CONTROL_OPTION_ASYNC),
            validator=OneOf(list(execute_control_options)),
            **kwargs)


class JobResponseOptionsEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(JobResponseOptionsEnum, self).__init__(
            String(),
            title=kwargs.get('title', 'response'),
            default=kwargs.get('default', EXECUTE_RESPONSE_RAW),
            example=kwargs.get('example', EXECUTE_RESPONSE_RAW),
            validator=OneOf(list(execute_response_options)),
            **kwargs)


class TransmissionModeEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(TransmissionModeEnum, self).__init__(
            String(),
            title=kwargs.get('title', 'transmissionMode'),
            default=kwargs.get('default', EXECUTE_TRANSMISSION_MODE_REFERENCE),
            example=kwargs.get('example', EXECUTE_TRANSMISSION_MODE_REFERENCE),
            validator=OneOf(list(execute_transmission_mode_options)),
            **kwargs)


class JobStatusEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(JobStatusEnum, self).__init__(
            String(),
            default=kwargs.get('default', None),
            example=kwargs.get('example', STATUS_ACCEPTED),
            validator=OneOf(list(job_status_categories[STATUS_COMPLIANT_OGC])),
            **kwargs)


class JobSortEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(JobSortEnum, self).__init__(
            String(),
            default=kwargs.get('default', SORT_CREATED),
            example=kwargs.get('example', SORT_CREATED),
            validator=OneOf(list(job_sort_values)),
            **kwargs)


class LaunchJobQuerystring(MappingSchema):
    field_string = SchemaNode(String(), default=None, missing=drop,
                              description='Comma separated tags that can be used to filter jobs later')
    field_string.name = 'tags'


class Visibility(MappingSchema):
    value = SchemaNode(String(), validator=OneOf(list(visibility_values)), example=VISIBILITY_PUBLIC)


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class FrontpageEndpoint(MappingSchema):
    header = AcceptHeader()


class VersionsEndpoint(MappingSchema):
    header = AcceptHeader()


class SwaggerJSONEndpoint(MappingSchema):
    header = AcceptHeader()


class SwaggerUIEndpoint(MappingSchema):
    pass


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


class ConformsToList(SequenceSchema):
    item = SchemaNode(String())


class ReqClasses(MappingSchema):
    conformsTo = ConformsToList()


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
    executeEndpoint = SchemaNode(String(), format=URL, missing=drop)


class ProcessOutputDescriptionSchema(MappingSchema):
    """WPS process output definition."""
    dataType = SchemaNode(String())
    defaultValue = MappingSchema()
    id = SchemaNode(String())
    abstract = SchemaNode(String())
    title = SchemaNode(String())


class JobStatusInfo(MappingSchema):
    jobID = SchemaNode(String(), example='a9d14bf4-84e0-449a-bac8-16e598efe807', description="ID of the job.")
    status = JobStatusEnum()
    message = SchemaNode(String(), missing=drop)
    logs = SchemaNode(String(), missing=drop)
    expirationDate = SchemaNode(DateTime(), missing=drop)
    estimatedCompletion = SchemaNode(DateTime(), missing=drop)
    duration = SchemaNode(DateTime(), missing=drop)
    nextPoll = SchemaNode(DateTime(), missing=drop)
    percentCompleted = SchemaNode(Integer(), example=0, validator=Range(min=0, max=100))


class JobCollectionList(SequenceSchema):
    item = SchemaNode(String(), description='Job ID.')


class JobCollection(MappingSchema):
    jobs = JobCollectionList()


class CreatedJobStatusSchema(MappingSchema):
    status = SchemaNode(String(), example=STATUS_ACCEPTED)
    location = SchemaNode(String(), example='http://{host}/weaver/processes/{my-process-id}/jobs/{my-job-id}')
    jobID = SchemaNode(String(), example='a9d14bf4-84e0-449a-bac8-16e598efe807', description="ID of the created job.")


class CreatedQuotedJobStatusSchema(CreatedJobStatusSchema):
    bill = SchemaNode(String(), example='d88fda5c-52cc-440b-9309-f2cd20bcd6a2', description="ID of the created bill.")


class GetPagingJobsSchema(MappingSchema):
    jobs = JobCollection()
    limit = SchemaNode(Integer())
    page = SchemaNode(Integer())


class GroupedJobsCategorySchema(MappingSchema):
    category = MappingSchema(description="Corresponding grouping values that compose the resulting job list category.")
    jobs = JobCollection(description="List of jobs that matched the corresponding grouping values.")
    count = SchemaNode(Integer(), description="Number of matching jobs for the corresponding group category.")


class GetGroupedJobsSchema(SequenceSchema):
    job_group_category = GroupedJobsCategorySchema()


class GetFilteredJobsSchema(OneOfMappingSchema):
    _one_of = (
        GetPagingJobsSchema,
        GetGroupedJobsSchema,
    )
    total = SchemaNode(Integer(), description="Total number of matched jobs regardless of grouping or paging result.")


class DismissedJobSchema(MappingSchema):
    status = JobStatusEnum()
    jobID = SchemaNode(String(), example='a9d14bf4-84e0-449a-bac8-16e598efe807', description="ID of the job.")
    message = SchemaNode(String(), example='Job dismissed.')
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
    mode = SchemaNode(String(), validator=OneOf(list(execute_mode_options)))
    notification_email = SchemaNode(
        String(),
        missing=drop,
        description="Optionally send a notification email when the job is done.")
    response = SchemaNode(String(), validator=OneOf(list(execute_response_options)))


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


class ProcessesSchema(SequenceSchema):
    provider_processes_service = Process()


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
    name = SchemaNode(String(), example='api')
    enabled = SchemaNode(Boolean(), example=True)
    url = SchemaNode(String(), example='https://weaver-host', missing=drop)
    doc = SchemaNode(String(), example='https://weaver-host/api', missing=drop)


class FrontpageParameters(SequenceSchema):
    param = FrontpageParameterSchema()


class FrontpageSchema(MappingSchema):
    message = SchemaNode(String(), default='Weaver Information', example='Weaver Information')
    configuration = SchemaNode(String(), default='default', example='default')
    parameters = FrontpageParameters()


class SwaggerJSONSpecSchema(MappingSchema):
    pass


class SwaggerUISpecSchema(MappingSchema):
    pass


class VersionsSpecSchema(MappingSchema):
    name = SchemaNode(String(), description="Identification name of the current item.", example='weaver')
    type = SchemaNode(String(), description="Identification type of the current item.", example='api')
    version = SchemaNode(String(), description="Version of the current item.", example='0.1.0')


class VersionsList(SequenceSchema):
    item = VersionsSpecSchema()


class VersionsSchema(MappingSchema):
    versions = VersionsList()


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
    process = Process()
    processVersion = SchemaNode(String(), missing=drop)
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


class PostProcessEndpoint(MappingSchema):
    header = AcceptHeader()
    body = Deploy(title='Deploy')


class PostProcessJobsEndpoint(ProcessPath):
    header = AcceptHeader()
    body = Execute()


class GetJobsQueries(MappingSchema):
    detail = SchemaNode(Boolean(), description="Provide job details instead of IDs.",
                        default=False, example=True, missing=drop)
    page = SchemaNode(Integer(), missing=drop, default=0)
    limit = SchemaNode(Integer(), missing=drop, default=10)
    status = JobStatusEnum(missing=drop)
    process = SchemaNode(String(), missing=drop, default=None)
    provider = SchemaNode(String(), missing=drop, default=None)
    sort = JobSortEnum(missing=drop)
    tags = SchemaNode(String(), missing=drop, default=None,
                      description='Comma-separated values of tags assigned to jobs')


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


class QuoteSortEnum(SchemaNode):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        kwargs.pop('validator', None)   # ignore passed argument and enforce the validator
        super(QuoteSortEnum, self).__init__(
            String(),
            default=kwargs.get('default', SORT_ID),
            example=kwargs.get('example', SORT_PROCESS),
            validator=OneOf(quote_sort_values),
            **kwargs)


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


class ErrorJsonResponseBodySchema(MappingSchema):
    code = SchemaNode(String(), example="NoApplicableCode")
    description = SchemaNode(String(), example="Not authorized to access this resource.")


class UnauthorizedJsonResponseSchema(MappingSchema):
    header = JsonHeader()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageSchema(MappingSchema):
    header = JsonHeader()
    body = FrontpageSchema()


class OkGetSwaggerJSONSchema(MappingSchema):
    header = JsonHeader()
    body = SwaggerJSONSpecSchema(description="Swagger JSON of weaver API.")


class OkGetSwaggerUISchema(MappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of weaver API.")


class OkGetVersionsSchema(MappingSchema):
    header = JsonHeader()
    body = VersionsSchema()


class OkGetProvidersSchema(MappingSchema):
    header = JsonHeader()
    body = ProvidersSchema()


class OkGetProviderCapabilitiesSchema(MappingSchema):
    header = JsonHeader()
    body = ProviderCapabilitiesSchema()


class NoContentDeleteProviderSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


class OkGetProviderProcessesSchema(MappingSchema):
    header = JsonHeader()
    body = ProcessesSchema()


class GetProcessesQuery(MappingSchema):
    providers = SchemaNode(
        Boolean(), example=True, default=False, missing=drop,
        description="List local processes as well as all sub-processes of all registered providers. "
                    "Applicable only for weaver in {} mode, false otherwise.".format(WEAVER_CONFIGURATION_EMS))
    detail = SchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class GetProcessesEndpoint(MappingSchema):
    querystring = GetProcessesQuery()


class OkGetProcessesSchema(MappingSchema):
    header = JsonHeader()
    body = ProcessCollection()


class OkPostProcessDeployBodySchema(MappingSchema):
    deploymentDone = SchemaNode(Boolean(), description="Indicates if the process was successfully deployed.",
                                default=False, example=True)
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = SchemaNode(String(), missing=drop, description="Description of deploy failure if applicable.")


class OkPostProcessesSchema(MappingSchema):
    header = JsonHeader()
    body = OkPostProcessDeployBodySchema()


class OkGetProcessSchema(MappingSchema):
    header = JsonHeader()
    body = ProcessOffering()


class OkGetProcessPackageSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


class OkGetProcessPayloadSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


class ProcessVisibilityResponseBodySchema(MappingSchema):
    value = SchemaNode(String(), validator=OneOf(list(visibility_values)), example=VISIBILITY_PUBLIC)


class OkGetProcessVisibilitySchema(MappingSchema):
    header = JsonHeader()
    body = ProcessVisibilityResponseBodySchema()


class OkPutProcessVisibilitySchema(MappingSchema):
    header = JsonHeader()
    body = ProcessVisibilityResponseBodySchema()


class OkDeleteProcessUndeployBodySchema(MappingSchema):
    deploymentDone = SchemaNode(Boolean(), description="Indicates if the process was successfully undeployed.",
                                default=False, example=True)
    identifier = SchemaNode(String(), example='workflow')
    failureReason = SchemaNode(String(), missing=drop, description="Description of undeploy failure if applicable.")


class OkDeleteProcessSchema(MappingSchema):
    header = JsonHeader()
    body = OkDeleteProcessUndeployBodySchema()


class OkGetProviderProcessDescription(MappingSchema):
    header = JsonHeader()
    body = ProcessDescriptionBodySchema()


class CreatedPostProvider(MappingSchema):
    header = JsonHeader()
    body = ProviderSummarySchema()


class CreatedLaunchJobResponse(MappingSchema):
    header = JsonHeader()
    body = CreatedJobStatusSchema()


class OkGetAllProcessJobsResponse(MappingSchema):
    header = JsonHeader()
    body = JobCollection()


class OkGetProcessJobResponse(MappingSchema):
    header = JsonHeader()
    body = JobStatusInfo()


class OkDeleteProcessJobResponse(MappingSchema):
    header = JsonHeader()
    body = DismissedJobSchema()


class OkGetAllJobsResponse(MappingSchema):
    header = JsonHeader()
    body = GetFilteredJobsSchema()


class OkDismissJobResponse(MappingSchema):
    header = JsonHeader()
    body = DismissedJobSchema()


class OkGetSingleJobStatusResponse(MappingSchema):
    header = JsonHeader()
    body = JobStatusInfo()


class Result(MappingSchema):
    outputs = OutputInfoList()
    links = JsonLinkList(missing=drop)


class OkGetSingleJobResultsResponse(MappingSchema):
    header = JsonHeader()
    body = Result()


class OkGetSingleOutputResponse(MappingSchema):
    header = JsonHeader()
    body = JobOutputSchema()


class CreatedQuoteExecuteResponse(MappingSchema):
    header = JsonHeader()
    body = CreatedQuotedJobStatusSchema()


class CreatedQuoteRequestResponse(MappingSchema):
    header = JsonHeader()
    body = QuoteSchema()


class OkGetQuoteResponse(MappingSchema):
    header = JsonHeader()
    body = QuoteSchema()


class OkGetQuoteListResponse(MappingSchema):
    header = JsonHeader()
    body = QuotationListSchema()


class OkGetBillDetailResponse(MappingSchema):
    header = JsonHeader()
    body = BillSchema()


class OkGetBillListResponse(MappingSchema):
    header = JsonHeader()
    body = BillListSchema()


class OkGetExceptionsResponse(MappingSchema):
    header = JsonHeader()
    body = ExceptionsOutputSchema()


class OkGetLogsResponse(MappingSchema):
    header = JsonHeader()
    body = LogsOutputSchema()


get_api_frontpage_responses = {
    '200': OkGetFrontpageSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_api_swagger_json_responses = {
    '200': OkGetSwaggerJSONSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_api_swagger_ui_responses = {
    '200': OkGetSwaggerUISchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_api_versions_responses = {
    '200': OkGetVersionsSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_processes_responses = {
    '200': OkGetProcessesSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
post_processes_responses = {
    # TODO: status should be 201 when properly modified to match API conformance
    '200': OkPostProcessesSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_process_responses = {
    '200': OkGetProcessSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_process_package_responses = {
    '200': OkGetProcessPackageSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_process_payload_responses = {
    '200': OkGetProcessPayloadSchema(description='success')
}
get_process_visibility_responses = {
    '200': OkGetProcessVisibilitySchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
put_process_visibility_responses = {
    '200': OkPutProcessVisibilitySchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
delete_process_responses = {
    '200': OkDeleteProcessSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_all_providers_responses = {
    '200': OkGetProvidersSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_one_provider_responses = {
    '200': OkGetProviderCapabilitiesSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
delete_provider_responses = {
    '204': NoContentDeleteProviderSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_provider_processes_responses = {
    '200': OkGetProviderProcessesSchema(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_provider_process_description_responses = {
    '200': OkGetProviderProcessDescription(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
post_provider_responses = {
    '201': CreatedPostProvider(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
post_provider_process_job_responses = {
    '201': CreatedLaunchJobResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
post_process_jobs_responses = {
    '201': CreatedLaunchJobResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_all_jobs_responses = {
    '200': OkGetAllJobsResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_single_job_status_responses = {
    '200': OkGetSingleJobStatusResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
delete_job_responses = {
    '200': OkDismissJobResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_job_results_responses = {
    '200': OkGetSingleJobResultsResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_quote_list_responses = {
    '200': OkGetQuoteListResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_quote_responses = {
    '200': OkGetQuoteResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
post_quote_responses = {
    '201': CreatedQuoteExecuteResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
post_quotes_responses = {
    '201': CreatedQuoteRequestResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_bill_list_responses = {
    '200': OkGetBillListResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_bill_responses = {
    '200': OkGetBillDetailResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_single_result_responses = {
    '200': OkGetSingleOutputResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_exceptions_responses = {
    '200': OkGetExceptionsResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}
get_logs_responses = {
    '200': OkGetLogsResponse(description='success'),
    '401': UnauthorizedJsonResponseSchema(description='unauthorized'),
}


#################################################################
# Utility methods
#################################################################


def service_api_route_info(service_api, settings):
    api_base = wps_restapi_base_path(settings)
    return {'name': service_api.name, 'pattern': '{base}{path}'.format(base=api_base, path=service_api.path)}
