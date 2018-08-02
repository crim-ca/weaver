"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
from cornice import Service
from colander import *

#########################################################
# API endpoints
#########################################################

api_frontpage_uri = '/'
api_swagger_ui_uri = '/api'
api_swagger_json_uri = '/api/json'

processes_uri = '/processes'
process_uri = '/processes/{process_id}'

providers_uri = '/providers'
provider_uri = '/providers/{provider_id}'

provider_processes_uri = '/providers/{provider_id}/processes'
provider_process_uri = '/providers/{provider_id}/processes/{process_id}'

jobs_uri = '/jobs'
job_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}'
job_exceptions_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions'
job_short_uri = '/jobs/{job_id}'

outputs_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/outputs'
outputs_short_uri = '/jobs/{job_id}/outputs'
output_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/outputs/{output_id}'
output_short_uri = '/jobs/{job_id}/outputs/{output_id}'

exceptions_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions'
exceptions_short_uri = '/jobs/{job_id}/exceptions'

logs_full_uri = '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/log'
logs_short_uri = '/jobs/{job_id}/log'

#########################################################
# API tags
#########################################################

api_tag = 'API'
provider_processes_tag = 'Provider Processes'
provider_jobs_tag = 'Jobs'
providers_tag = 'Providers'
processes_tag = 'Local Processes'

###############################################################################
# These "services" are wrappers that allow Cornice to generate the api's json
###############################################################################

api_frontpage_service = Service(name='api_frontpage', path=api_frontpage_uri)
api_swagger_ui_service = Service(name='api_swagger_ui', path=api_swagger_ui_uri)
api_swagger_json_service = Service(name='api_swagger_json', path=api_swagger_json_uri)

processes_service = Service(name='processes', path=processes_uri)
process_service = Service(name='process', path=process_uri)

providers_service = Service(name='providers', path=providers_uri)
provider_service = Service(name='provider', path=provider_uri)

provider_processes_service = Service(name='provider_processes', path=provider_processes_uri)
provider_process_service = Service(name='provider_process', path=provider_process_uri)

jobs_service = Service(name='jobs', path=jobs_uri)
job_full_service = Service(name='job_full', path=job_full_uri)
job_short_service = Service(name='job_short', path=job_short_uri)

outputs_full_service = Service(name='outputs_full', path=outputs_full_uri)
outputs_short_service = Service(name='outputs_short', path=outputs_short_uri)
output_full_service = Service(name='output_full', path=output_full_uri)
output_short_service = Service(name='output_short', path=output_short_uri)

exceptions_full_service = Service(name='exceptions_full', path=exceptions_full_uri)
exceptions_short_service = Service(name='exceptions_short', path=exceptions_short_uri)

logs_full_service = Service(name='logs_full', path=logs_full_uri)
logs_short_service = Service(name='logs_short', path=logs_short_uri)

#########################################################
# Query parameter definitions
#########################################################

provider_id = SchemaNode(String(), description='The provider id')
process_id = SchemaNode(String(), description='The process id')
job_id = SchemaNode(String(), description='The job id')
output_id = SchemaNode(String(), description='The output id')

#########################################################
# Generic schemas
#########################################################


class JsonHeader(MappingSchema):
    content_type = SchemaNode(String(), example='application/json', default='application/json')
    content_type.name = 'Content-Type'


class HtmlHeader(MappingSchema):
    content_type = SchemaNode(String(), example='text/html', default='text/html')
    content_type.name = 'Content-Type'


class StringList(SequenceSchema):
    item = SchemaNode(String())


class MetadataObject(MappingSchema):
    role = SchemaNode(String(), missing=drop)
    href = SchemaNode(String(), missing=drop)


class MetadataList(SequenceSchema):
    item = MetadataObject()


class FormatObject(MappingSchema):
    mimeType = SchemaNode(String())
    schema = SchemaNode(String(), missing=drop)
    encoding = SchemaNode(String(), missing=drop)
    maximumMegabytes = SchemaNode(Integer(), missing=drop)
    default = SchemaNode(Boolean(), missing=drop, default=False)


class FormatList(SequenceSchema):
    item = FormatObject()


class LiteralDataDomainObject(MappingSchema):
    pass


class BaseTypeBody(MappingSchema):
    id = SchemaNode(String())
    title = SchemaNode(String(), missing=drop)
    abstract = SchemaNode(String(), missing=drop)
    keywords = StringList(missing=drop)
    metadata = MetadataList(missing=drop)
    formats = FormatList()
    minOccurs = SchemaNode(Integer(), missing=drop)
    maxOccurs = SchemaNode(Integer(), missing=drop)


class LiteralInputTypeBody(BaseTypeBody):
    LiteralDataDomain = LiteralDataDomainObject(missing=drop)


class ComplexInputTypeBody(BaseTypeBody):
    pass


class BoundingBoxInputTypeBody(BaseTypeBody):
    pass


class InputTypeList(SequenceSchema):
    item = MappingSchema(default={},
                         validator=OneOf([LiteralInputTypeBody, ComplexInputTypeBody, BoundingBoxInputTypeBody]))


class OutputTypeBody(BaseTypeBody):
    pass


class OutputTypeList(SequenceSchema):
    item = OutputTypeBody()


JobControlOptionsEnum = SchemaNode(String(), validator=OneOf(['sync-execute', 'async-execute']), missing=drop)
OutputTransmissionEnum = SchemaNode(String(), validator=OneOf(['value', 'reference']), missing=drop)


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class ProviderEndpoint(MappingSchema):
    provider_id = provider_id


class ProcessEndpoint(MappingSchema):
    provider_id = provider_id
    process_id = process_id


class FullJobEndpoint(MappingSchema):
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ShortJobEndpoint(MappingSchema):
    job_id = job_id


class FullOutputEndpoint(MappingSchema):
    provider_id = provider_id
    process_id = process_id
    job_id = job_id
    output_id = output_id


class ShortOutputEndpoint(MappingSchema):
    job_id = job_id
    output_id = output_id


class FullExceptionsEndpoint(MappingSchema):
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ShortExceptionsEndpoint(MappingSchema):
    job_id = job_id


class FullLogsEndpoint(MappingSchema):
    provider_id = provider_id
    process_id = process_id
    job_id = job_id


class ShortLogsEndpoint(MappingSchema):
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


class ProviderSchema(MappingSchema):
    """WPS provider shortened definition"""
    url = SchemaNode(String())
    abstract = SchemaNode(String())
    title = SchemaNode(String())
    id = SchemaNode(String())
    public = SchemaNode(Boolean())


class ProviderCapabilitiesSchema(MappingSchema):
    """WPS provider capabilities"""
    contact = SchemaNode(String())
    title = SchemaNode(String())
    url = SchemaNode(String())
    abstract = SchemaNode(String())
    type = SchemaNode(String())
    id = SchemaNode(String())


class ProcessSchema(MappingSchema):
    """WPS process definition"""
    url = SchemaNode(String())
    abstract = SchemaNode(String())
    id = SchemaNode(String())
    title = SchemaNode(String())


class ProcessListSchema(SequenceSchema):
    item = ProcessSchema(missing=drop)


class ProcessOutputDescriptionSchema(MappingSchema):
    """WPS process output definition"""
    dataType = SchemaNode(String())
    defaultValue = SchemaNode(Mapping())
    id = SchemaNode(String())
    abstract = SchemaNode(String())
    title = SchemaNode(String())


class JobStatusSchema(MappingSchema):
    Status = SchemaNode(String())
    Location = SchemaNode(String())
    Exceptions = SchemaNode(String())
    JobID = SchemaNode(String())


class AllJobsSchema(SequenceSchema):
    job = JobStatusSchema()


class GetAllJobsSchema(MappingSchema):
    count = SchemaNode(Integer())
    jobs_service = AllJobsSchema()
    limit = SchemaNode(Integer())
    page = SchemaNode(Integer())


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


class ProvidersSchema(SequenceSchema):
    providers_service = ProviderSchema()


class ProcessesSchema(SequenceSchema):
    provider_processes_service = ProcessSchema()


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


class OkGetFrontpageSchema(MappingSchema):
    body = FrontpageSchema()


class OkGetSwaggerJSONSchema(MappingSchema):
    body = MappingSchema(default={}, description="")


class OkGetSwaggerUISchema(MappingSchema):
    header = HtmlHeader()


class OkGetProvidersSchema(MappingSchema):
    body = ProvidersSchema()


class OkGetProviderCapabilitiesSchema(MappingSchema):
    body = ProviderCapabilitiesSchema()


class OkGetProviderProcessesSchema(MappingSchema):
    body = ProcessesSchema()


class OkGetProcessesBodySchema(MappingSchema):
    processes = ProcessListSchema()


class OkGetProcessesSchema(MappingSchema):
    body = OkGetProcessesBodySchema()


class OkPostProcessesSchema(MappingSchema):
    body = ProcessSchema()


class OkGetProcessBodySchema(MappingSchema):
    process = ProcessSchema()


class OkGetProcessSchema(MappingSchema):
    body = OkGetProcessBodySchema()


class DeleteProcessRequestSchema(MappingSchema):
    pass


class OkDeleteProcessBodySchema(MappingSchema):
    deploymentDone = SchemaNode(String(), default='success', example='success')
    id = SchemaNode(String(), example='workflow')


class OkDeleteProcessSchema(MappingSchema):
    body = OkDeleteProcessBodySchema()


class OkGetProviderProcessDescription(MappingSchema):
    body = ProcessDescriptionSchema()


class OkPostProvider(MappingSchema):
    body = ProviderSchema()


class OkLaunchJobResponse(MappingSchema):
    body = JobStatusSchema()


class OkGetAllJobsResponse(MappingSchema):
    body = GetAllJobsSchema()


class OkGetSingleJobStatusResponse(MappingSchema):
    body = JobStatusSchema()


class OkGetSingleJobOutputsResponse(MappingSchema):
    body = JobOutputsSchema()


class OkGetSingleOutputResponse(MappingSchema):
    body = JobOutputSchema()


class OkGetExceptionsResponse(MappingSchema):
    body = ExceptionsOutputSchema()


class OkGetLogsResponse(MappingSchema):
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
get_processes_responses = {
    '200': OkGetProcessesSchema(description='success')
}
post_processes_responses = {
    '200': OkPostProcessesSchema(description='success')
}
get_process_responses = {
    '200': OkGetProcessSchema(description='success')
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
get_provider_processes_responses = {
    '200': OkGetProviderProcessesSchema(description='success')
}
get_provider_process_description_responses = {
    '200': OkGetProviderProcessDescription(description='success')
}
post_provider_responses = {
    '200': OkPostProvider(description='success')
}
launch_job_responses = {
    '200': OkLaunchJobResponse(description='success')
}
get_all_jobs_responses = {
    '200': OkGetAllJobsResponse(description='success')
}
get_single_job_status_responses = {
    '200': OkGetSingleJobStatusResponse(description='success')
}
get_single_job_outputs_responses = {
    '200': OkGetSingleJobOutputsResponse(description='success')
}
get_single_output_responses = {
    '200': OkGetSingleOutputResponse(description='success')
}
get_exceptions_responses = {
    '200': OkGetExceptionsResponse(description='success')
}
get_logs_responses = {
    '200': OkGetLogsResponse(description='success')
}


class LaunchJobQuerystring(MappingSchema):
    sync_execute = SchemaNode(Boolean(), example='application/json', default=False, missing=drop)
    sync_execute.name = 'sync-execute'


class PostProvider(MappingSchema):
    body = CreateProviderRequestBody()
    header = JsonHeader()


#################################
# Local Processes schemas
#################################


class ProcessBody(MappingSchema):
    identifier = SchemaNode(String())
    title = SchemaNode(String(), missing=drop)
    abstract = SchemaNode(String(), missing=drop)
    keywords = StringList(missing=drop)
    metadata = MetadataList(missing=drop)
    inputs = InputTypeList(missing=drop)
    outputs = OutputTypeList(missing=drop)
    version = SchemaNode(String(), missing=drop)
    jobControlOptions = JobControlOptionsEnum
    outputTransmission = OutputTransmissionEnum
    executeEndpoint = SchemaNode(String(), missing=drop)    # URL


class ProcessOfferingBody(MappingSchema):
    process = ProcessBody()


class PackageBody(MappingSchema):
    workflow = SchemaNode(String(), description="Workflow file content.")  # TODO: maybe binary?


class ExecutionUnitBody(MappingSchema):
    package = PackageBody(missing=drop)
    reference = SchemaNode(String(), missing=drop)


class ProfileExtensionBody(MappingSchema):
    pass


class DeploymentProfileBody(MappingSchema):
    deploymentProfileName = SchemaNode(String(), description="Name of the deployment profile.")
    executionUnit = ExecutionUnitBody(missing=drop)
    profileExtension = ProfileExtensionBody(missing=drop)


class PostProcessRequestBody(MappingSchema):
    processOffering = ProcessOfferingBody()
    deploymentProfile = DeploymentProfileBody()


class PostProcessRequest(MappingSchema):
    header = JsonHeader()
    body = PostProcessRequestBody()


#################################
# Provider Processes schemas
#################################

class GetProviderProcesses(MappingSchema):
    pass


class GetProviderProcess(MappingSchema):
    pass


class PostProviderProcessRequestQuery(MappingSchema):
    sync_execute = SchemaNode(Boolean(), example='application/json', default=False, missing=drop)
    sync_execute.name = 'sync-execute'


class PostProviderProcessRequestBody(MappingSchema):
    inputs = JobInputList()
    # outputs = JobOutputList()


class PostProviderProcessRequest(MappingSchema):
    """Launching a new process request definition"""
    header = JsonHeader()
    querystring = PostProviderProcessRequestQuery()
    body = PostProviderProcessRequestBody()


def service_api_route_info(service_api):
    return {'name': service_api.name, 'pattern': service_api.path}
