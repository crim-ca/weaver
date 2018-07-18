"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
from cornice import Service
from colander import (MappingSchema,
                      SequenceSchema,
                      SchemaNode,
                      String,
                      Boolean,
                      Integer,
                      Mapping)

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


class LaunchJobRequestBody(SequenceSchema):
    input = JobInput()


class ProviderSchema(MappingSchema):
    """WPS provider definition"""
    url = SchemaNode(String())
    abstract = SchemaNode(String())
    title = SchemaNode(String())
    id = SchemaNode(String())
    public = SchemaNode(Boolean())
    contact = SchemaNode(String())


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


class OkGetProvidersSchema(MappingSchema):
    body = ProvidersSchema()


class OkGetProcessesSchema(MappingSchema):
    body = ProcessesSchema()


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


get_all_providers_response = {
    '200': OkGetProvidersSchema(description='success')
}
get_processes_response = {
    '200': OkGetProcessesSchema(description='success')
}
get_process_description_response = {
    '200': OkGetProcessDescription(description='success')
}
post_provider_response = {
    '200': OkPostProvider(description='success')
}
launch_job_response = {
    '200': OkLaunchJobResponse(description='success')
}
get_all_jobs_response = {
    '200': OkGetAllJobsResponse(description='success')
}
get_single_job_status_response = {
    '200': OkGetSingleJobStatusResponse(description='success')
}
get_single_job_outputs_response = {
    '200': OkGetSingleJobOutputsResponse(description='success')
}
get_single_output_response = {
    '200': OkGetSingleOutputResponse(description='success')
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


class PostProcess(MappingSchema):
    """Launching a new process request definition"""
    querystring = ProcessEndpoint()
    body = LaunchJobRequestBody()


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
