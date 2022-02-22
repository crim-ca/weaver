import logging
import os
import shutil
from typing import TYPE_CHECKING

from pyramid.exceptions import ConfigurationError

from weaver import WEAVER_CONFIG_DIR
from weaver.base import Constants
from weaver.utils import get_settings

if TYPE_CHECKING:
    from typing import Optional

    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


class WeaverConfiguration(Constants):
    """
    Configuration mode for which the `Weaver` instance should operate to provide different functionalities.
    """
    DEFAULT = "DEFAULT"
    ADES = "ADES"
    EMS = "EMS"
    HYBRID = "HYBRID"


class WeaverFeature(Constants):
    """
    Features enabled accordingly to different combinations of :class:`WeaverConfiguration` modes.
    """
    REMOTE = frozenset([
        WeaverConfiguration.EMS,
        WeaverConfiguration.HYBRID,
    ])
    QUOTING = frozenset([
        WeaverConfiguration.ADES,
        WeaverConfiguration.EMS,
        WeaverConfiguration.HYBRID,
    ])


WEAVER_DEFAULT_INI_CONFIG = "weaver.ini"
WEAVER_DEFAULT_DATA_SOURCES_CONFIG = "data_sources.yml"
WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG = "request_options.yml"
WEAVER_DEFAULT_WPS_PROCESSES_CONFIG = "wps_processes.yml"
WEAVER_DEFAULT_CONFIGS = frozenset([
    WEAVER_DEFAULT_INI_CONFIG,
    WEAVER_DEFAULT_DATA_SOURCES_CONFIG,
    WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG,
    WEAVER_DEFAULT_WPS_PROCESSES_CONFIG,
])


def get_weaver_configuration(container):
    # type: (AnySettingsContainer) -> str
    """
    Obtains the defined operation configuration mode.

    :returns: one value amongst :py:data:`weaver.config.WEAVER_CONFIGURATIONS`.
    """
    settings = get_settings(container)
    weaver_config = settings.get("weaver.configuration")
    if not weaver_config:
        LOGGER.warning("Setting 'weaver.configuration' not specified, using '%s'", WeaverConfiguration.DEFAULT)
        weaver_config = WeaverConfiguration.DEFAULT
    weaver_config_up = weaver_config.upper()
    if weaver_config_up not in WeaverConfiguration:
        raise ConfigurationError("Unknown setting 'weaver.configuration' specified: '{}'".format(weaver_config))
    return weaver_config_up


def get_weaver_config_file(file_path, default_config_file, generate_default_from_example=True):
    # type: (Optional[str], str, bool) -> str
    """
    Validates that the specified configuration file can be found, or falls back to the default one.

    Handles 'relative' paths for settings in ``WEAVER_DEFAULT_INI_CONFIG`` referring to other configuration files.
    Default file must be one of ``WEAVER_DEFAULT_CONFIGS``.

    If both the specified file and the default file cannot be found, default file under ``WEAVER_DEFAULT_INI_CONFIG`` is
    auto-generated from the corresponding ``.example`` file if :paramref:`generate_default_from_example` is ``True``.
    If it is ``False``, an empty string is returned instead without generation since no existing file can be guaranteed,
    and it is up to the caller to handle this situation as it explicitly disabled generation.

    :param file_path: path to a configuration file (can be relative if resolvable or matching a default file name)
    :param default_config_file: one of :py:data:`WEAVER_DEFAULT_CONFIGS`.
    :param generate_default_from_example: enable fallback copy of default configuration file from corresponding example.
    :returns: absolute path of the resolved file.
    """
    if default_config_file not in WEAVER_DEFAULT_CONFIGS:
        raise ValueError("Invalid default configuration file [{}] is not one of {}"
                         .format(default_config_file, list(WEAVER_DEFAULT_CONFIGS)))
    default_path = os.path.abspath(os.path.join(WEAVER_CONFIG_DIR, default_config_file))
    if file_path in [None, "", default_config_file, os.path.join(os.curdir, default_config_file)]:
        file_path = default_path
    if str(file_path).strip() != "":
        file_path = os.path.abspath(file_path)
    if os.path.isfile(file_path):
        LOGGER.info("Resolved specified configuration file: [%s]", file_path)
        return file_path
    LOGGER.warning("Cannot find configuration file: [%s]. Falling back to default.", file_path or "<empty>")
    if os.path.isfile(default_path):
        LOGGER.info("Resolved default configuration file: [%s]", default_path)
        return default_path
    example_file = default_config_file + ".example"
    example_path = default_path + ".example"
    LOGGER.warning("Could not find default configuration file: [%s]. ", file_path)
    if not generate_default_from_example:
        LOGGER.warning("Default file generation from default disabled. No file returned.")
        return ""
    LOGGER.warning("Using generated file copied from: [%s]", example_file)
    if not os.path.isfile(example_path):
        raise RuntimeError("Could not find expected example configuration file: [{}]".format(example_path))
    shutil.copyfile(example_path, default_path)
    return default_path


def includeme(config):  # noqa: E811
    LOGGER.debug("Loading weaver configuration.")
