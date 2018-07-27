"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
from cornice import Service
from colander import *

"""
API endpoints
"""
providers_uri = '/providers'
provider_uri = '/providers/{provider_id}'

processes_uri = '/providers/{provider_id}/processes'
process_uri = '/providers/{provider_id}/processes/{process_id}'

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

"""
These "services" are wrappers that allow Cornice to generate the api's json
"""
providers = Service(name='providers', path=providers_uri)
provider = Service(name='provider', path=provider_uri)

processes = Service(name='processes', path=processes_uri)
process = Service(name='process', path=process_uri)

jobs = Service(name='jobs', path=jobs_uri)
job_full = Service(name='job_full', path=job_full_uri)
job_short = Service(name='job_short', path=job_short_uri)
outputs_full = Service(name='outputs_full', path=outputs_full_uri)
outputs_short = Service(name='outputs_short', path=outputs_short_uri)
output_full = Service(name='output_full', path=output_full_uri)
output_short = Service(name='output_short', path=output_short_uri)
exceptions_full = Service(name='exceptions_full', path=exceptions_full_uri)
exceptions_short = Service(name='exceptions_short', path=exceptions_short_uri)
logs_full = Service(name='logs_full', path=logs_full_uri)
logs_short = Service(name='logs_short', path=logs_short_uri)

"""
Query parameter definitions
"""
provider_id = SchemaNode(String(), description='The provider id')
process_id = SchemaNode(String(), description='The process id')
job_id = SchemaNode(String(), description='The job id')
output_id = SchemaNode(String(), description='The output id')

"""
These classes define each of the endpoints parameters
"""


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


"""
These classes define schemas for requests that feature a body
"""


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
    jobs = AllJobsSchema()
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
    providers = ProviderSchema()


class ProcessesSchema(SequenceSchema):
    processes = ProcessSchema()


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


class OkGetProvidersSchema(MappingSchema):
    body = ProvidersSchema()


class OkGetProviderCapabilitiesSchema(MappingSchema):
    body = ProviderCapabilitiesSchema()


class OkGetProcessesSchema(MappingSchema):
    body = ProcessesSchema()


class OkPostProcessesSchema(MappingSchema):
    body = ProcessSchema()


class OkGetProcessDescription(MappingSchema):
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


get_all_providers_responses = {
    '200': OkGetProvidersSchema(description='success')
}
get_one_provider_responses = {
    '200': OkGetProviderCapabilitiesSchema(description='success')
}
get_processes_responses = {
    '200': OkGetProcessesSchema(description='success')
}
post_processes_responses = {
    '200': OkPostProcessesSchema(description='success')
}
get_process_description_responses = {
    '200': OkGetProcessDescription(description='success')
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


class GetProvider(MappingSchema):
    querystring = ProviderEndpoint()


class GetProviders(MappingSchema):
    pass


class PostProvider(MappingSchema):
    body = CreateProviderRequestBody()


class DeleteProvider(MappingSchema):
    querystring = ProviderEndpoint()


"""
Processes schemas
"""


class GetProcesses(MappingSchema):
    # reusing the Provider query because both only have provider_id as field in the query string
    querystring = ProviderEndpoint()


class GetProcess(MappingSchema):
    querystring = ProcessEndpoint()


class PostProviderProcessRequestHeader(MappingSchema):
    content_type = SchemaNode(String(), example='application/json')
    content_type.name = 'Content-Type'


class PostProviderProcessRequestQuery(MappingSchema):
    sync_execute = SchemaNode(Boolean(), example='application/json', default=False, missing=drop)
    sync_execute.name = 'sync-execute'


class PostProviderProcessRequestBody(MappingSchema):
    inputs = JobInputList()
    outputs = JobOutputList()


class PostProviderProcessRequest(MappingSchema):
    """Launching a new process request definition"""
    header = PostProviderProcessRequestHeader()
    querystring = PostProviderProcessRequestQuery()
    body = PostProviderProcessRequestBody()


class GetJobs(MappingSchema):
    pass


class GetJobStatusFull(MappingSchema):
    querystring = FullJobEndpoint()


class GetJobStatusShort(MappingSchema):
    querystring = ShortJobEndpoint()


class DismissJobFull(MappingSchema):
    querystring = FullJobEndpoint()


class DismissJobShort(MappingSchema):
    querystring = ShortJobEndpoint()


class GetJobOutputsFull(MappingSchema):
    querystring = FullJobEndpoint()


class GetJobOutputsShort(MappingSchema):
    querystring = ShortJobEndpoint()


class GetSpecificOutputFull(MappingSchema):
    querystring = FullOutputEndpoint()


class GetSpecificOutputShort(MappingSchema):
    querystring = ShortOutputEndpoint()


class GetExceptionsFull(MappingSchema):
    querystring = FullExceptionsEndpoint()


class GetExceptionsShort(MappingSchema):
    querystring = ShortExceptionsEndpoint()


class GetLogsFull(MappingSchema):
    querystring = FullLogsEndpoint()


class GetLogsShort(MappingSchema):
    querystring = ShortLogsEndpoint()
