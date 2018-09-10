"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""

from twitcher.config import TWITCHER_CONFIGURATION_EMS
from twitcher.wps_restapi.utils import wps_restapi_base_path
from twitcher.wps_restapi.status import status_values, STATUS_ACCEPTED
from twitcher.wps_restapi.sort import sort_values, SORT_CREATED
from cornice import Service
from colander import *


API_TITLE = 'Twitcher REST API'


#########################################################################
# API endpoints
#########################################################################

api_frontpage_uri = '/'
api_swagger_ui_uri = '/api'
api_swagger_json_uri = '/json'
api_versions_uri = '/versions'

processes_uri = '/processes'
process_uri = '/processes/{process_id}'
process_package_uri = '/processes/{process_id}/package'
process_jobs_uri = '/processes/{process_id}/jobs'
process_job_uri = '/processes/{process_id}/jobs/{job_id}'
process_results_uri = '/processes/{process_id}/jobs/{job_id}/results'
process_result_uri = '/processes/{process_id}/jobs/{job_id}/results/{result_id}'
process_exceptions_uri = '/processes/{process_id}/jobs/{job_id}/exceptions'
process_logs_uri = '/processes/{process_id}/jobs/{job_id}/logs'

providers_uri = '/providers'
provider_uri = '/providers/{provider_id}'

provider_processes_uri = '/providers/{provider_id}/processes'
provider_process_uri = '/providers/{provider_id}/processes/{process_id}'

jobs_short_uri = '/jobs'
jobs_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs'
job_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}'
job_exceptions_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions'
job_short_uri = '/jobs/{job_id}'

results_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/results'
results_short_uri = '/jobs/{job_id}/results'
result_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/results/{result_id}'
result_short_uri = '/jobs/{job_id}/results/{result_id}'

exceptions_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions'
exceptions_short_uri = '/jobs/{job_id}/exceptions'

logs_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/logs'
logs_short_uri = '/jobs/{job_id}/logs'

#########################################################
# API tags
#########################################################

api_tag = 'API'
jobs_tag = 'Jobs'
provider_processes_tag = 'Provider Processes'
providers_tag = 'Providers'
processes_tag = 'Local Processes'
getcapabilities_tag = 'GetCapabilities'
describeprocess_tag = 'DescribeProcess'
execute_tag = 'Execute'
dismiss_tag = 'Dismiss'
status_tag = 'Status'
deploy_tag = 'Deploy'
results_tag = 'Results'
exceptions_tag = 'Exceptions'
logs_tag = 'Logs'

###############################################################################
# These "services" are wrappers that allow Cornice to generate the api's json
###############################################################################

api_frontpage_service = Service(name='api_frontpage', path=api_frontpage_uri)
api_swagger_ui_service = Service(name='api_swagger_ui', path=api_swagger_ui_uri)
api_swagger_json_service = Service(name='api_swagger_json', path=api_swagger_json_uri)
api_versions_service = Service(name='api_versions', path=api_versions_uri)

processes_service = Service(name='processes', path=processes_uri)
process_service = Service(name='process', path=process_uri)
process_package_service = Service(name='process_package', path=process_package_uri)
process_jobs_service = Service(name='process_jobs', path=process_jobs_uri)
process_job_service = Service(name='process_job', path=process_job_uri)
process_results_service = Service(name='process_results', path=process_results_uri)
process_result_service = Service(name='process_result', path=process_result_uri)
process_exceptions_service = Service(name='process_exceptions', path=process_exceptions_uri)
process_logs_service = Service(name='process_logs', path=process_logs_uri)

providers_service = Service(name='providers', path=providers_uri)
provider_service = Service(name='provider', path=provider_uri)

provider_processes_service = Service(name='provider_processes', path=provider_processes_uri)
provider_process_service = Service(name='provider_process', path=provider_process_uri)

jobs_short_service = Service(name='jobs_short', path=jobs_short_uri)
jobs_full_service = Service(name='jobs_full', path=jobs_full_uri)
job_full_service = Service(name='job_full', path=job_full_uri)
job_short_service = Service(name='job_short', path=job_short_uri)

results_full_service = Service(name='results_full', path=results_full_uri)
results_short_service = Service(name='results_short', path=results_short_uri)
result_full_service = Service(name='result_full', path=result_full_uri)
result_short_service = Service(name='result_short', path=result_short_uri)

exceptions_full_service = Service(name='exceptions_full', path=exceptions_full_uri)
exceptions_short_service = Service(name='exceptions_short', path=exceptions_short_uri)

logs_full_service = Service(name='logs_full', path=logs_full_uri)
logs_short_service = Service(name='logs_short', path=logs_short_uri)

#########################################################
# Path parameter definitions
#########################################################

provider_id = SchemaNode(String(), description='The provider id')
process_id = SchemaNode(String(), description='The process id')
job_id = SchemaNode(String(), description='The job id')
result_id = SchemaNode(String(), description='The result id')

#########################################################
# Generic schemas
#########################################################


class JsonHeader(MappingSchema):
    content_type = SchemaNode(String(), example='application/json', default='application/json')
    content_type.name = 'Content-Type'


class HtmlHeader(MappingSchema):
    content_type = SchemaNode(String(), example='text/html', default='text/html')
    content_type.name = 'Content-Type'


class XmlHeader(MappingSchema):
    content_type = SchemaNode(String(), example='application/xml', default='application/xml')
    content_type.name = 'Content-Type'


# TODO:
# return XML when Accept=application/xml, add header=AcceptHeader() to 'request' MappingSchema (create for GETs)
# only HTTPExceptions >= 400 properly do it using tweens because of the formatter, HTTP 2xx/3xx are always JSON
# for how to generate doc with content-type specific responses (create the selector in swagger-ui), see:
#   https://github.com/Cornices/cornice.ext.swagger/blob/master/docs/source/tutorial.rst#extracting-produced-types-from-renderers
class AcceptHeader(MappingSchema):
    # 'default' is json since 'return HTTP*(json={})' are used
    Accept = SchemaNode(String(), missing=drop, default='application/json', validator=OneOf([
        'application/json',
        #'application/xml',
        #'text/html'
    ]))


class KeywordList(SequenceSchema):
    keyword = SchemaNode(String())


class MetadataObject(MappingSchema):
    role = SchemaNode(String(), missing=drop)
    href = SchemaNode(String(), missing=drop)


class MetadataList(SequenceSchema):
    metadata = MetadataObject()


class FormatObject(MappingSchema):
    mimeType = SchemaNode(String())
    schema = SchemaNode(String(), missing=drop)
    encoding = SchemaNode(String(), missing=drop)
    maximumMegabytes = SchemaNode(Integer(), missing=drop)
    default = SchemaNode(Boolean(), missing=drop, default=False)


class FormatList(SequenceSchema):
    format = FormatObject()


class LiteralDataDomainObject(MappingSchema):
    pass


class BaseInputTypeBody(MappingSchema):
    identifier = SchemaNode(String())
    title = SchemaNode(String(), missing=drop)
    abstract = SchemaNode(String(), missing=drop)
    keywords = KeywordList(missing=drop)
    metadata = MetadataList(missing=drop)
    formats = FormatList()
    minOccurs = SchemaNode(Integer(), missing=drop)
    maxOccurs = SchemaNode(Integer(), missing=drop)


class BaseOutputTypeBody(MappingSchema):
    identifier = SchemaNode(String())
    title = SchemaNode(String(), missing=drop)
    abstract = SchemaNode(String(), missing=drop)
    keywords = KeywordList(missing=drop)
    metadata = MetadataList(missing=drop)
    formats = FormatList()
    minOccurs = SchemaNode(Integer(), missing=drop)
    maxOccurs = SchemaNode(Integer(), missing=drop)


class LiteralInputTypeBody(BaseInputTypeBody):
    LiteralDataDomain = LiteralDataDomainObject(missing=drop)


class ComplexInputTypeBody(BaseInputTypeBody):
    pass


class BoundingBoxInputTypeBody(BaseInputTypeBody):
    pass


class LiteralOutputTypeBody(BaseOutputTypeBody):
    LiteralDataDomain = LiteralDataDomainObject(missing=drop)


class ComplexOutputTypeBody(BaseOutputTypeBody):
    pass


class BoundingBoxOutputTypeBody(BaseOutputTypeBody):
    pass


class InputTypeBody(BaseInputTypeBody):
    literal = LiteralInputTypeBody()
    complex = ComplexInputTypeBody()
    bounding_box = BoundingBoxInputTypeBody()


class OutputTypeBody(BaseOutputTypeBody):
    literal = LiteralOutputTypeBody()
    complex = ComplexOutputTypeBody()
    bounding_box = BoundingBoxOutputTypeBody()


class InputTypeList(SequenceSchema):
    input = InputTypeBody(validator=OneOf(['literal', 'complex', 'bounding_box']))


class OutputTypeList(SequenceSchema):
    output = OutputTypeBody(validator=OneOf(['literal', 'complex', 'bounding_box']))


JobControlOptionsEnum = SchemaNode(String(), validator=OneOf(['sync-execute', 'async-execute']), missing=drop)
OutputTransmissionEnum = SchemaNode(String(), validator=OneOf(['value', 'reference']), missing=drop)


class LaunchJobQuerystring(MappingSchema):
    sync_execute = SchemaNode(Boolean(), example='application/json', default=False, missing=drop)
    sync_execute.name = 'sync-execute'


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


class ProviderEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id


class ProviderProcessEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id


class ProcessEndpoint(MappingSchema):
    header = AcceptHeader()
    process_id = process_id


class FullJobEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ShortJobEndpoint(MappingSchema):
    header = AcceptHeader()
    job_id = job_id


class ProcessResultsEndpoint(MappingSchema):
    header = AcceptHeader()
    process_id = process_id
    job_id = job_id


class FullResultsEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ProcessResultEndpoint(MappingSchema):
    header = AcceptHeader()
    process_id = process_id
    job_id = job_id


class ShortResultsEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class FullResultEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id
    job_id = job_id
    result_id = result_id


class ShortResultEndpoint(MappingSchema):
    header = AcceptHeader()
    job_id = job_id
    result_id = result_id


class FullExceptionsEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ShortExceptionsEndpoint(MappingSchema):
    header = AcceptHeader()
    job_id = job_id


class ProcessExceptionsEndpoint(MappingSchema):
    header = AcceptHeader()
    process_id = process_id
    job_id = job_id


class FullLogsEndpoint(MappingSchema):
    header = AcceptHeader()
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ShortLogsEndpoint(MappingSchema):
    header = AcceptHeader()
    job_id = job_id


class ProcessLogsEndpoint(MappingSchema):
    header = AcceptHeader()
    process_id = process_id
    job_id = job_id


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class CreateProviderRequestBody(MappingSchema):
    id = SchemaNode(String())
    url = SchemaNode(String())
    public = SchemaNode(Boolean())


class JobInput(MappingSchema):
    id = SchemaNode(String())
    value = SchemaNode(String())
    type = SchemaNode(String())


class JobOutput(MappingSchema):
    id = SchemaNode(String())
    type = SchemaNode(String())


class JobInputList(SequenceSchema):
    item = JobInput()


class JobOutputList(SequenceSchema):
    item = JobOutput()


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


class ProcessSummarySchema(MappingSchema):
    """WPS process definition."""
    identifier = SchemaNode(String())
    title = SchemaNode(String())
    abstract = SchemaNode(String())
    keywords = KeywordList(missing=drop)
    metadata = MetadataList(missing=drop)
    executeEndpoint = SchemaNode(String(), missing=drop)    # URL


class ProcessListSchema(SequenceSchema):
    process = ProcessSummarySchema(missing=drop)


class ProviderSummaryProcessesSchema(ProviderSummarySchema):
    processes = ProcessListSchema()


class ProviderProcessListSchema(SequenceSchema):
    provider = ProviderSummaryProcessesSchema(missing=drop)


class ProcessDetailSchema(MappingSchema):
    identifier = SchemaNode(String())
    title = SchemaNode(String(), missing=drop)
    abstract = SchemaNode(String(), missing=drop)
    keywords = KeywordList(missing=drop)
    metadata = MetadataList(missing=drop)
    inputs = InputTypeList(missing=drop)
    outputs = OutputTypeList(missing=drop)
    version = SchemaNode(String(), missing=drop)
    jobControlOptions = JobControlOptionsEnum
    outputTransmission = OutputTransmissionEnum
    executeEndpoint = SchemaNode(String(), format='url', missing=drop)


class ProcessOutputDescriptionSchema(MappingSchema):
    """WPS process output definition."""
    dataType = SchemaNode(String())
    defaultValue = SchemaNode(Mapping())
    id = SchemaNode(String())
    abstract = SchemaNode(String())
    title = SchemaNode(String())


JobStatusEnum = SchemaNode(
    String(),
    default=None,
    validator=OneOf(status_values),
    example=STATUS_ACCEPTED)
JobSortEnum = SchemaNode(
    String(),
    missing=drop,
    default=SORT_CREATED,
    validator=OneOf(sort_values),
    example=SORT_CREATED)


class GetJobsQueries(MappingSchema):
    page = SchemaNode(Integer(), missing=drop, default=0)
    limit = SchemaNode(Integer(), missing=drop, default=10)
    status = JobStatusEnum
    process = SchemaNode(String(), missing=drop, default=None)
    provider = SchemaNode(String(), missing=drop, default=None)
    sort = JobSortEnum


class GetJobsRequest(MappingSchema):
    header = AcceptHeader()
    querystring = GetJobsQueries()


class SingleJobStatusSchema(MappingSchema):
    status = JobStatusEnum
    message = SchemaNode(String(), example='Job {}.'.format(STATUS_ACCEPTED))
    progress = SchemaNode(Integer(), example=0)
    exceptions = SchemaNode(String(), missing=drop,
                            example='http://twitcher/providers/my-wps/processes/my-process/jobs/my-job/exceptions')
    outputs = SchemaNode(String(), missing=drop,
                         example='http://twitcher/providers/my-wps/processes/my-process/jobs/my-job/outputs')
    logs = SchemaNode(String(), missing=drop,
                      example='http://twitcher/providers/my-wps/processes/my-process/jobs/my-job/logs')


class JobListSchema(SequenceSchema):
    job = SchemaNode(String(), description='Job ID.')


class ProcessJobStatusSchema(MappingSchema):
    status = SchemaNode(String(), example=STATUS_ACCEPTED)
    message = SchemaNode(String(), example='Job accepted.')
    progress = SchemaNode(Integer(), example=0)


class GetAllJobsSchema(MappingSchema):
    count = SchemaNode(Integer())
    jobs = JobListSchema()
    limit = SchemaNode(Integer())
    page = SchemaNode(Integer())


class DismissedJobSchema(MappingSchema):
    status = JobStatusEnum
    message = SchemaNode(String(), example='Job dismissed.')
    progress = SchemaNode(Integer(), example=0)


class SupportedValues(MappingSchema):
    pass


class DefaultValues(MappingSchema):
    pass


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


class ProcessDescriptionBodySchema(MappingSchema):
    process = ProcessDescriptionSchema()


class ProvidersSchema(SequenceSchema):
    providers_service = ProviderSummarySchema()


class ProcessesSchema(SequenceSchema):
    provider_processes_service = ProcessDetailSchema()


class JobOutputSchema(MappingSchema):
    ID = SchemaNode(String())
    value = SchemaNode(String())


class JobOutputsSchema(SequenceSchema):
    output = JobOutputSchema()


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


class FrontpageSchema(MappingSchema):
    message = SchemaNode(String(), default='hello')
    configuration = SchemaNode(String(), default='default')


class AdapterDescriptionSchema(MappingSchema):
    name = SchemaNode(String(), description="Name of the loaded Twitcher adapter.", missing=drop, example='default')
    version = SchemaNode(String(), description="Version of the loaded Twitcher adapter.", missing=drop, example='0.3.0')


class SwaggerJSONSpecSchema(MappingSchema):
    pass


class SwaggerUISpecSchema(MappingSchema):
    pass


class VersionsSpecSchema(MappingSchema):
    twitcher = SchemaNode(String(), description="Twitcher version string.", example='0.3.0')
    adapter = AdapterDescriptionSchema()


class VersionsSchema(MappingSchema):
    version = VersionsSpecSchema()


#################################
# Local Processes schemas
#################################


class ProcessOfferingBody(MappingSchema):
    process = ProcessDetailSchema(title='Process')


class PackageBody(MappingSchema):
    pass


class ExecutionUnitBody(MappingSchema):
    package = PackageBody(missing=drop, description="CWL file content as JSON.")
    reference = SchemaNode(String(), missing=drop, description="CWL file or docker image reference.")


class ProfileExtensionBody(MappingSchema):
    pass


class DeploymentProfileBody(MappingSchema):
    deploymentProfileName = SchemaNode(String(), missing=drop, description="Name of the deployment profile.")
    executionUnit = ExecutionUnitBody(description="Package/Reference definition.", title='ExecutionUnit',
                                      validator=OneOf(['reference', 'package']))
    profileExtension = ProfileExtensionBody(missing=drop, title='ProfileExtension',
                                            description="Additional parameters for docker image.")


class PostProcessRequestBody(MappingSchema):
    processOffering = ProcessOfferingBody(title='ProcessOffering')
    deploymentProfile = DeploymentProfileBody(title='DeploymentProfile')


class ProcessesEndpoint(MappingSchema):
    header = AcceptHeader()
    body = PostProcessRequestBody(title='Deploy')


class PostProcessJobBody(MappingSchema):
    inputs = JobInputList(missing=drop)


class PostProcessJobsEndpoint(MappingSchema):
    process_id = process_id
    header = AcceptHeader()
    body = PostProcessJobBody()


class GetProcessJobsEndpoint(MappingSchema):
    header = AcceptHeader()


class GetProcessJobEndpoint(MappingSchema):
    header = AcceptHeader()


class DeleteProcessJobEndpoint(MappingSchema):
    header = AcceptHeader()


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


class PostProviderProcessJobRequestBody(MappingSchema):
    inputs = JobInputList()
    # outputs = JobOutputList()


class PostProviderProcessJobRequest(MappingSchema):
    """Launching a new process request definition."""
    header = AcceptHeader()
    querystring = LaunchJobQuerystring()
    body = PostProviderProcessJobRequestBody()


#################################
# Responses schemas
#################################


class OkGetFrontpageSchema(MappingSchema):
    header = JsonHeader()
    body = FrontpageSchema()


class OkGetSwaggerJSONSchema(MappingSchema):
    header = JsonHeader()
    body = SwaggerJSONSpecSchema(description="Swagger JSON of Twitcher API.")


class OkGetSwaggerUISchema(MappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of Twitcher API.")


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
        description="List local processes as well as all sub-processes of all registered providers. " +
                    "Applicable only for Twitcher in {} mode, false otherwise.".format(TWITCHER_CONFIGURATION_EMS))


class GetProcessesRequest(MappingSchema):
    querystring = GetProcessesQuery()


class OkGetProcessesBodySchema(MappingSchema):
    processes = ProcessListSchema(title='ProcessCollection')
    providers = ProviderProcessListSchema(missing=drop)


class OkGetProcessesSchema(MappingSchema):
    header = JsonHeader()
    body = OkGetProcessesBodySchema()


class OkPostProcessDeployBodySchema(MappingSchema):
    deploymentDone = SchemaNode(Boolean(), description="Indicates if the process was successfully deployed.",
                                default=False, example=True)
    processSummary = ProcessSummarySchema(missing=drop, description="Deployed process summary if successful.")
    failureReason = SchemaNode(String(), missing=drop, description="Description of deploy failure if applicable.")


class OkPostProcessesSchema(MappingSchema):
    header = JsonHeader()
    body = OkPostProcessDeployBodySchema()


class OkGetProcessBodySchema(MappingSchema):
    process = ProcessDetailSchema()


class OkGetProcessSchema(MappingSchema):
    header = JsonHeader()
    body = OkGetProcessBodySchema()


class OkGetProcessPackageSchema(MappingSchema):
    header = JsonHeader()
    body = MappingSchema(default={})


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


class CreatedLaunchJobHeader(JsonHeader):
    Location = SchemaNode(String(), description='Location URL of the created job execution status.')


class CreatedLaunchJobResponse(MappingSchema):
    header = CreatedLaunchJobHeader()
    body = SingleJobStatusSchema()


class OkGetAllProcessJobsResponse(MappingSchema):
    header = JsonHeader()
    body = JobListSchema()


class OkGetProcessJobResponse(MappingSchema):
    header = JsonHeader()
    body = ProcessJobStatusSchema()


class OkDeleteProcessJobResponse(MappingSchema):
    header = JsonHeader()
    body = DismissedJobSchema()


class OkGetAllJobsResponse(MappingSchema):
    header = JsonHeader()
    body = GetAllJobsSchema()


class OkDismissJobResponse(MappingSchema):
    header = JsonHeader()
    body = DismissedJobSchema()


class OkGetSingleJobStatusResponse(MappingSchema):
    header = JsonHeader()
    body = SingleJobStatusSchema()


class OkGetSingleJobOutputsResponse(MappingSchema):
    header = JsonHeader()
    body = JobOutputsSchema()


class OkGetSingleOutputResponse(MappingSchema):
    header = JsonHeader()
    body = JobOutputSchema()


class OkGetExceptionsResponse(MappingSchema):
    header = JsonHeader()
    body = ExceptionsOutputSchema()


class OkGetLogsResponse(MappingSchema):
    header = JsonHeader()
    body = LogsOutputSchema()


get_api_frontpage_responses = {
    '200': OkGetFrontpageSchema(description='success')
}
get_api_swagger_json_responses = {
    '200': OkGetSwaggerJSONSchema(description='success')
}
get_api_swagger_ui_responses = {
    '200': OkGetSwaggerUISchema(description='success')
}
get_api_versions_responses = {
    '200': OkGetVersionsSchema(description='success')
}
get_processes_responses = {
    '200': OkGetProcessesSchema(description='success')
}
post_processes_responses = {
    '200': OkPostProcessesSchema(description='success')
}
get_process_responses = {
    '200': OkGetProcessSchema(description='success')
}
get_process_package_responses = {
    '200': OkGetProcessPackageSchema(description='success')
}
delete_process_responses = {
    '200': OkDeleteProcessSchema(description='success')
}
get_all_providers_responses = {
    '200': OkGetProvidersSchema(description='success')
}
get_one_provider_responses = {
    '200': OkGetProviderCapabilitiesSchema(description='success')
}
delete_provider_responses = {
    '204': NoContentDeleteProviderSchema(description='success')
}
get_provider_processes_responses = {
    '200': OkGetProviderProcessesSchema(description='success')
}
get_provider_process_description_responses = {
    '200': OkGetProviderProcessDescription(description='success')
}
post_provider_responses = {
    '201': CreatedPostProvider(description='success')
}
post_provider_process_job_responses = {
    '201': CreatedLaunchJobResponse(description='success')
}
post_process_jobs_responses = {
    '201': CreatedLaunchJobResponse(description='success')
}
get_all_jobs_responses = {
    '200': OkGetAllJobsResponse(description='success')
}
get_single_job_status_responses = {
    '200': OkGetSingleJobStatusResponse(description='success')
}
delete_job_responses = {
    '200': OkDismissJobResponse(description='success')
}
get_job_results_responses = {
    '200': OkGetSingleJobOutputsResponse(description='success')
}
get_single_result_responses = {
    '200': OkGetSingleOutputResponse(description='success')
}
get_exceptions_responses = {
    '200': OkGetExceptionsResponse(description='success')
}
get_logs_responses = {
    '200': OkGetLogsResponse(description='success')
}


#################################################################
# Utility methods
#################################################################


def service_api_route_info(service_api, settings):
    api_base = wps_restapi_base_path(settings)
    return {'name': service_api.name, 'pattern': '{base}{path}'.format(base=api_base, path=service_api.path)}
