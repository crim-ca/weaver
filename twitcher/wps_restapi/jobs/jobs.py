from pyramid.view import view_config
from twitcher.wps_restapi.swagger_definitions import (jobs,
                                                      job_full,
                                                      job_short,
                                                      outputs_full,
                                                      outputs_short,
                                                      output_full,
                                                      output_short,
                                                      GetJobs,
                                                      GetJobStatusFull,
                                                      GetJobStatusShort,
                                                      DismissJobFull,
                                                      DismissJobShort,
                                                      GetJobOutputsFull,
                                                      GetJobOutputsShort,
                                                      GetSpecificOutputFull,
                                                      GetSpecificOutputShort,
                                                      get_all_jobs_response,
                                                      get_single_job_status_response,
                                                      get_single_job_outputs_response,
                                                      get_single_output_response)


@jobs.get(tags=['jobs'], schema=GetJobs(), response_schemas=get_all_jobs_response)
def get_jobs(request):
    """
    Retrieve the list of jobs which can be filtered/sorted using :
    ?page=[number]
    &limit=[number]
    &status=[ProcessAccepted, ProcessStarted, ProcessPaused, ProcessFailed, ProcessSucceeded] 
    &process=[process_name]
    &provider=[provider_id]
    &sort=[created, status, process, provider]
    """
    pass


@job_full.get(tags=['jobs'], schema=GetJobStatusFull(), response_schemas=get_single_job_status_response)
@job_short.get(tags=['jobs'], schema=GetJobStatusShort(), response_schemas=get_single_job_status_response)
def get_job_status(request):
    """
    Retrieve the status of a job
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


@job_full.delete(tags=['jobs'], schema=DismissJobFull())
@job_short.delete(tags=['jobs'], schema=DismissJobShort())
def cancel_job(request):
    """
    Dismiss a job
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


@outputs_full.get(tags=['jobs'], schema=GetJobOutputsFull(), response_schemas=get_single_job_outputs_response)
@outputs_short.get(tags=['jobs'], schema=GetJobOutputsShort(), response_schemas=get_single_job_outputs_response)
def get_outputs(request):
    """
    Retrieve the result(s) of a job
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


@output_full.get(tags=['jobs'], schema=GetSpecificOutputFull(), response_schemas=get_single_output_response)
@output_short.get(tags=['jobs'], schema=GetSpecificOutputShort(), response_schemas=get_single_output_response)
def get_output(request):
    """
    Retrieve the result of a particular job output
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')
    output_id = request.matchdict.get('output_id')