import os
import tempfile
from pyramid.exceptions import ConfigurationError

import logging
LOGGER = logging.getLogger(__name__)


WEAVER_CONFIGURATION_DEFAULT = 'DEFAULT'
WEAVER_CONFIGURATION_ADES = 'ADES'
WEAVER_CONFIGURATION_EMS = 'EMS'
weaver_CONFIGURATIONS = frozenset([
    WEAVER_CONFIGURATION_DEFAULT,
    WEAVER_CONFIGURATION_ADES,
    WEAVER_CONFIGURATION_EMS,
])


def get_weaver_configuration(settings):
    weaver_config = settings.get('weaver.configuration')
    if not weaver_config:
        LOGGER.warn("Setting 'weaver.configuration' not specified, using '{}'".format(WEAVER_CONFIGURATION_DEFAULT))
        weaver_config = WEAVER_CONFIGURATION_DEFAULT
    weaver_config_up = weaver_config.upper()
    if weaver_config_up not in weaver_CONFIGURATIONS:
        raise ConfigurationError("Unknown setting 'weaver.configuration' specified: '{}'".format(weaver_config))
    return weaver_config_up


def _workdir(request):
    settings = request.registry.settings
    workdir = settings.get('weaver.workdir')
    workdir = workdir or tempfile.gettempdir()
    if not os.path.exists(workdir):
        os.makedirs(workdir)
    LOGGER.debug('using workdir %s', workdir)
    return workdir


def _prefix(request):
    settings = request.registry.settings
    prefix = settings.get('weaver.prefix')
    prefix = prefix or 'weaver_'
    return prefix


def includeme(config):
    # settings = config.registry.settings

    LOGGER.debug("Loading weaver configuration.")

    config.add_request_method(_workdir, 'workdir', reify=True)
    config.add_request_method(_prefix, 'prefix', reify=True)
