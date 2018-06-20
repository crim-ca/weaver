from pyramid.view import view_config


@view_config(route_name='wps_restapi', request_method='GET', renderer='json')
def api(request):
    return {}