from pyramid.view import view_config


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


def get_job_status(request):
    """
    Retrieve the status of a job
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


def cancel_job(request):
    """
    Dismiss a job"
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


def get_outputs(request):
    """
    Retrieve the result(s) of a job"
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')


def get_output(request):
    """
    Retrieve the result of a particular job output
    """
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    job_id = request.matchdict.get('job_id')
    output_id = request.matchdict.get('output_id')