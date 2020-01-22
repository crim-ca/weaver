from weaver import WEAVER_CONFIG_DIR
from weaver.utils import get_settings

from pyramid.exceptions import ConfigurationError

import logging
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weaver.typedefs import AnyStr, AnySettingsContainer  # noqa: F401

LOGGER = logging.getLogger(__name__)

WEAVER_CONFIGURATION_DEFAULT = "DEFAULT"
WEAVER_CONFIGURATION_ADES = "ADES"
WEAVER_CONFIGURATION_EMS = "EMS"
WEAVER_CONFIGURATIONS = frozenset([
    WEAVER_CONFIGURATION_DEFAULT,
    WEAVER_CONFIGURATION_ADES,
    WEAVER_CONFIGURATION_EMS,
])

WEAVER_DEFAULT_INI_CONFIG = "weaver.ini"
WEAVER_DEFAULT_DATA_SOURCES_CONFIG = "data_sources.json"
WEAVER_DEFAULT_WPS_PROCESSES_CONFIG = "wps_processes.yml"
WEAVER_DEFAULT_CONFIGS = frozenset([
    WEAVER_DEFAULT_INI_CONFIG,
    WEAVER_DEFAULT_DATA_SOURCES_CONFIG,
    WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
])


def get_weaver_configuration(container):
    # type: (AnySettingsContainer) -> AnyStr
    """Obtains the defined operation configuration mode.

    :returns: one value amongst :py:data:`weaver.config.WEAVER_CONFIGURATIONS`.
    """
    settings = get_settings(container)
    weaver_config = settings.get("weaver.configuration")
    if not weaver_config:
        LOGGER.warn("Setting 'weaver.configuration' not specified, using '%s'", WEAVER_CONFIGURATION_DEFAULT)
        weaver_config = WEAVER_CONFIGURATION_DEFAULT
    weaver_config_up = weaver_config.upper()
    if weaver_config_up not in WEAVER_CONFIGURATIONS:
        raise ConfigurationError("Unknown setting 'weaver.configuration' specified: '{}'".format(weaver_config))
    return weaver_config_up


def get_weaver_config_file(file_path, default_config_file):
    # type: (AnyStr, AnyStr) -> AnyStr
    """Validates that the specified configuration file can be found, or falls back to the default one.

    Handles 'relative' paths for settings in ``WEAVER_DEFAULT_INI_CONFIG`` referring to other configuration files.
    Default file must be one of ``WEAVER_DEFAULT_CONFIGS``.
    If the default file cannot be found, it is auto-generated from the corresponding example file.

    :param file_path: path to a configuration file (can be relative if resolvable or matching a default file name)
    :param default_config_file: one of :py:data:`WEAVER_DEFAULT_CONFIGS`.
    """
    if default_config_file not in WEAVER_DEFAULT_CONFIGS:
        raise ValueError("Invalid default configuration file [%s] is not one of %s",
                         default_config_file, list(WEAVER_DEFAULT_CONFIGS))
    default_path = os.path.abspath(os.path.join(WEAVER_CONFIG_DIR, default_config_file))
    if file_path in [default_config_file, os.path.join(os.curdir, default_config_file)]:
        file_path = default_path
    file_path = os.path.abspath(file_path)
    if os.path.isfile(file_path):
        LOGGER.info("Resolved specified configuration file: [%s]", file_path)
        return file_path
    LOGGER.warning("Cannot find configuration file: [%s]. Falling back to default.", file_path)
    if os.path.isfile(default_path):
        LOGGER.info("Resolved default configuration file: [%s]", default_path)
        return default_path
    example_file = default_config_file + ".example"
    example_path = default_path + ".example"
    LOGGER.warning("Could not find default configuration file: [%s]. "
                   "Using generated file copied from: [%s]", file_path, example_file)
    if not os.path.isfile(example_path):
        raise RuntimeError("Could not find expected example configuration file: [%s]", example_path)
    shutil.copyfile(example_path, default_path)
    return default_path


def includeme(config):  # noqa: E811
    LOGGER.debug("Loading weaver configuration.")
