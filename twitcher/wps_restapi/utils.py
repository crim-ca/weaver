

def restapi_base_url(request):
    twitcher_url = request.registry.settings.get('twitcher.url').rstrip('/')
    restapi_path = request.registry.settings.get('twitcher.restapi_path', '').rstrip('/')
    return twitcher_url + restapi_path
