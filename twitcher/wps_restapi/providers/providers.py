from pyramid.view import view_config


@view_config(route_name='providers', request_method='GET')
def get_providers(request):
    """
    Lists providers
    """
    pass


@view_config(route_name='providers', request_method='POST')
def add_provider(request):
    """
    Add a provider
    """
    pass


@view_config(route_name='providers', request_method='DELETE')
def remove_provider(request):
    """
    Remove a provider
    """
    pass


@view_config(route_name='get_capabilities', request_method='GET')
def get_capabilities(request):
    """
    GetCapabilities of a wps provider
    """
    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')
