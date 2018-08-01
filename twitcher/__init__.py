__version__ = '0.3.9'

import os
import sys
TWITCHER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
TWITCHER_ROOT_DIR = os.path.abspath(os.path.dirname(TWITCHER_MODULE_DIR))
sys.path.insert(0, TWITCHER_ROOT_DIR)
sys.path.insert(0, TWITCHER_MODULE_DIR)

from twitcher import adapter
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPServerError
from pyramid.view import exception_view_config, notfound_view_config, forbidden_view_config


@notfound_view_config()
def notfound_view(request):
    exception_view(request)


@exception_view_config()
def exception_view(request):
    content = {u'route_name': str(request.upath_info), u'request_url': str(request.url),
               u'detail': request.detail or u'undefined', u'method': request.method}
    if hasattr(request, 'exception'):
        if hasattr(request.exception, 'json'):
            if type(request.exception.json) is dict:
                content.update(request.exception.json)
        elif isinstance(request.exception, HTTPServerError) and hasattr(request.exception, 'message'):
            content.update({u'exception': str(request.exception.message)})
    elif hasattr(request, 'matchdict'):
        if request.matchdict is not None and request.matchdict != '':
            content.update(request.matchdict)
    return content


def parse_extra_options(option_str):
    """
    Parses the extra options parameter.

    The option_str is a string with coma separated ``opt=value`` pairs.
    Example::

        tempdir=/path/to/tempdir,archive_root=/path/to/archive

    :param option_str: A string parameter with the extra options.
    :return: A dict with the parsed extra options.
    """
    if option_str:
        try:
            extra_options = option_str.split(',')
            extra_options = dict([('=' in opt) and opt.split('=', 1) for opt in extra_options])
        except Exception:
            msg = "Can not parse extra-options: {}".format(option_str)
            raise ConfigurationError(msg)
    else:
        extra_options = {}
    return extra_options


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """

    # Parse extra_options and add each of them in the settings dict
    settings.update(parse_extra_options(settings.get('twitcher.extra_options', '')))

    from twitcher.adapter import adapter_factory

    config = adapter_factory(settings).configurator_factory(settings)

    # celery
    config.include('pyramid_celery')
    config.configure_celery(global_config['__file__'])

    # include twitcher components
    config.include('twitcher.config')
    config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    config.include('twitcher.wps_restapi')
    config.include('twitcher.processes')

    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    ##config.add_exception_view(exception_view)

    config.scan()

    return config.make_wsgi_app()
