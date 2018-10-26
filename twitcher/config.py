import os
import tempfile
from pyramid.exceptions import ConfigurationError
from pyramid.settings import asbool


import logging
LOGGER = logging.getLogger("TWITCHER")


TWITCHER_CONFIGURATION_DEFAULT = 'DEFAULT'
TWITCHER_CONFIGURATIONS = frozenset([
    TWITCHER_CONFIGURATION_DEFAULT,
    # TODO: add other configurations here
])


def get_twitcher_configuration(settings):
    twitcher_config = settings.get('twitcher.configuration')
    if not twitcher_config:
        LOGGER.warn("Setting 'twitcher.configuration' not specified, using '{}'".format(TWITCHER_CONFIGURATION_DEFAULT))
        twitcher_config = TWITCHER_CONFIGURATION_DEFAULT
    twitcher_config_up = twitcher_config.upper()
    if twitcher_config_up not in TWITCHER_CONFIGURATIONS:
        raise ConfigurationError("Unknown setting 'twitcher.configuration' specified: '{}'".format(twitcher_config))
    return twitcher_config_up


def _workdir(request):
    settings = request.registry.settings
    workdir = settings.get('twitcher.workdir')
    workdir = workdir or tempfile.gettempdir()
    if not os.path.exists(workdir):
        os.makedirs(workdir)
    LOGGER.debug('using workdir %s', workdir)
    return workdir


def _prefix(request):
    settings = request.registry.settings
    prefix = settings.get('twitcher.prefix')
    prefix = prefix or 'twitcher_'
    return prefix


def includeme(config):
    # settings = config.registry.settings

    LOGGER.debug("Loading twitcher configuration.")

    config.add_request_method(_workdir, 'workdir', reify=True)
    config.add_request_method(_prefix, 'prefix', reify=True)
