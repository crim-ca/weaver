from pyramid.view import view_config


@view_config(route_name='jobs', request_method='GET')
def get_processes(request):
    """
    Retrieve the list of jobs which can be filtered/sorted using :
    ?page=[number]
    &limit=[number]
    &status=[ProcessAccepted, ProcessStarted, ProcessPaused, ProcessFailed, ProcessSucceeded] 
    &process=[process_name]
    &provider=[provider_name]
    &sort=[created, status, process, provider]
    """
    pass


@view_config(route_name='job', request_method='GET')
def describe_process(request):
    """
    Retrieve the status of a job
    """
    # TODO Validate param somehow (provider_name and process_id are optional)
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


@view_config(route_name='job', request_method='DELETE')
def submit_job(request):
    """
    Dismiss a job"
    """
    # TODO Validate param somehow (provider_name and process_id are optional)
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


@view_config(route_name='outputs', request_method='GET')
def describe_process(request):
    """
    Retrieve the result(s) of a job"
    """
    # TODO Validate param somehow (provider_name and process_id are optional)
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


@view_config(route_name='output', request_method='GET')
def submit_job(request):
    """
    Retrieve the result of a particular job output
    """
    # TODO Validate param somehow (provider_name and process_id are optional)
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')
    output_id = request.matchdict.get('output_id')
