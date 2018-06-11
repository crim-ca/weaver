from pyramid.view import view_config


@view_config(route_name='processes', request_method='GET')
def get_processes(request):
    """
    Retrieve available processes
    """
    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')


@view_config(route_name='process', request_method='GET')
def describe_process(request):
    """
    Retrieve a process description
    """
    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')


@view_config(route_name='process', request_method='POST')
def submit_job(request):
    """
    Execute a process. Parameters: ?sync-execute=true|false (false being the default value)
    """
    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')
