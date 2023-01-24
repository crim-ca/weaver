import os
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import yaml
from pyramid.settings import asbool

from weaver import WEAVER_ROOT_DIR
from weaver.config import WEAVER_DEFAULT_DATA_SOURCES_CONFIG, get_weaver_config_file
from weaver.processes.constants import OpenSearchField
from weaver.utils import get_settings
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Optional, Text

    from weaver.typedefs import DataSourceConfig

DATA_SOURCES = {}  # type: DataSourceConfig
"""
Data sources configuration.

Unless explicitly overridden, the configuration will be loaded from file as specified by``weaver.data_sources`` setting.
Following JSON schema format is expected (corresponding YAML also supported):

.. code-block:: json

  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Data Sources",
    "type": "object",
    "patternProperties": {
      ".*": {
        "type": "object",
        "required": [ "netloc", "ades" ],
        "additionalProperties": false,
        "properties": {
          "netloc": {
            "type": "string",
            "description": "Net location of a data source url use to match this data source."
          },
          "ades": {
            "type": "string",
            "description": "ADES endpoint where the processing of this data source can occur."
          },
          "default": {
            "type": "string",
            "description": "True indicate that if no data source match this one should be used (Use the first default)."
          }
        }
      }
    }
  }
"""


def fetch_data_sources():
    # type: () -> DataSourceConfig
    global DATA_SOURCES  # pylint: disable=W0603,global-statement

    if DATA_SOURCES:
        return DATA_SOURCES

    settings = get_settings()
    data_source_config = settings.get("weaver.data_sources", "")
    if data_source_config:
        data_source_config = get_weaver_config_file(str(data_source_config), WEAVER_DEFAULT_DATA_SOURCES_CONFIG)
        if not os.path.isabs(data_source_config):
            data_source_config = os.path.normpath(os.path.join(WEAVER_ROOT_DIR, data_source_config))
        try:
            with open(data_source_config, mode="r", encoding="utf-8") as f:
                DATA_SOURCES = yaml.safe_load(f)  # both JSON/YAML
        except Exception as exc:
            raise ValueError(f"Data sources file [{data_source_config}] cannot be loaded due to error: [{exc!r}].")
    if not DATA_SOURCES:
        raise ValueError("No data sources found in setting 'weaver.data_sources'. Data source required for EMS.")
    return DATA_SOURCES


def get_default_data_source(data_sources):
    # type: (DataSourceConfig) -> str

    # Check for a data source with the default property
    for src, val in data_sources.items():
        if asbool(val.get("default", False)):
            return src

    # Use the first one if no default have been set
    return next(iter(data_sources))


def retrieve_data_source_url(data_source):
    # type: (Optional[Text]) -> str
    """
    Finds the data source URL using the provided data source identifier.

    :returns: found URL, 'default' data source if not found, or current weaver WPS Rest API base URL if `None`.
    """
    if data_source is None:
        # get local data source
        return get_wps_restapi_base_url(get_settings())
    data_sources = fetch_data_sources()
    return data_sources[data_source if data_source in data_sources else get_default_data_source(data_sources)]["ades"]


def get_data_source_from_url(data_url):
    # type: (str) -> str
    data_sources = fetch_data_sources()
    try:
        parsed = urlparse(data_url)
        netloc, path, scheme = parsed.netloc, parsed.path, parsed.scheme
        if netloc:
            for src, val in data_sources.items():
                if val["netloc"] == netloc:
                    return src
        elif scheme == OpenSearchField.LOCAL_FILE_SCHEME:
            # for file links, try to find if any rootdir matches in the file path
            for src, val in data_sources.items():
                if path.startswith(val["rootdir"]):
                    return src
    except Exception:  # noqa: W0703 # nosec: B110
        pass
    return get_default_data_source(data_sources)
