import logging
logger = logging.getLogger(__name__)

# -- Pyramid ----


# -- Ziggurat_foundation ----

#import sys
#sys.path.insert(0, '/home/deruefx/CrimProjects/PAVICS/Magpie')
import os

__version__ = '0.3.7'


from pyramid.exceptions import ConfigurationError


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

    # include twitcher components
    config.include('twitcher.config')
    config.include('twitcher.frontpage')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    config.include('twitcher.wps_restapi')

    auth_method = config.get_settings().get('twitcher.ows_security_provider', None)
    if auth_method == 'magpie':
        from magpie.models import get_user
        config.set_request_property(get_user, 'user', reify=True)
        config.include('twitcher.magpieconfig')
    else:
        config.include('twitcher.rpcinterface')


    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    config.scan()

    return config.make_wsgi_app()
