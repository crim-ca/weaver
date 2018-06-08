__version__ = '0.3.7'


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from pyramid.config import Configurator

    config = Configurator(settings=settings)
    auth_method = config.get_settings().get('twitcher.auth', None)
    # include twitcher components
    config.include('twitcher.config')
    config.include('twitcher.frontpage')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    if not auth_method:
        config.include('twitcher.rpcinterface')
    if auth_method == 'magpie':
        config.include('twitcher.magpieconfig')


    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    config.scan()

    return config.make_wsgi_app()
