from pyramid.exceptions import ConfigurationError
import logging
LOGGER = logging.getLogger(__name__)


WEAVER_CONFIGURATION_DEFAULT = "DEFAULT"
WEAVER_CONFIGURATION_ADES = "ADES"
WEAVER_CONFIGURATION_EMS = "EMS"
WEAVER_CONFIGURATIONS = frozenset([
    WEAVER_CONFIGURATION_DEFAULT,
    WEAVER_CONFIGURATION_ADES,
    WEAVER_CONFIGURATION_EMS,
])


def get_weaver_configuration(settings):
    weaver_config = settings.get("weaver.configuration")
    if not weaver_config:
        LOGGER.warn("Setting 'weaver.configuration' not specified, using '{}'".format(WEAVER_CONFIGURATION_DEFAULT))
        weaver_config = WEAVER_CONFIGURATION_DEFAULT
    weaver_config_up = weaver_config.upper()
    if weaver_config_up not in WEAVER_CONFIGURATIONS:
        raise ConfigurationError("Unknown setting 'weaver.configuration' specified: '{}'".format(weaver_config))
    return weaver_config_up


# noinspection PyUnusedLocal
def includeme(config):
    LOGGER.debug("Loading weaver configuration.")
