import os
import json
from urlparse import urlparse
from pyramid.settings import asbool
from pyramid_celery import celery_app as app
from twitcher import TWITCHER_ROOT_DIR

# Data source cache
"""
Schema

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

DATA_SOURCES = {}


def fetch_data_sources():
    if DATA_SOURCES:
        return DATA_SOURCES

    global DATA_SOURCES

    registry = app.conf['PYRAMID_REGISTRY']
    data_source_cfg = registry.settings.get('twitcher.data_sources', None)
    if data_source_cfg:
        if not os.path.isabs(data_source_cfg):
            try:
                data_source_cfg = os.path.normpath(os.path.join(TWITCHER_ROOT_DIR, data_source_cfg))
                with open(data_source_cfg) as f:
                    DATA_SOURCES = json.load(f)
            except Exception:
                pass
    return DATA_SOURCES


def get_default_data_source(data_sources):
    # Check for a data source with the default property
    for src, val in data_sources.items():
        if asbool(val.get('default', False)):
            return src

    # Use the first one if no default have been set
    return next(iter(data_sources))


def retrieve_data_source_url(data_source):
    data_sources = fetch_data_sources()
    return data_sources[data_source if data_source in data_sources else get_default_data_source(data_sources)]['ades']


def get_data_source_from_url(data_url):
    data_sources = fetch_data_sources()
    try:
        netloc = urlparse(data_url).netloc
        for src, val in data_sources.items():
            if val['netloc'] == netloc:
                return src
    except Exception as exc:
        pass
    return get_default_data_source(data_sources)