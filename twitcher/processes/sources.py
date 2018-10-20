import json
from urlparse import urlparse
from pyramid.settings import asbool
from pyramid_celery import celery_app as app

# Data source cache
DATA_SOURCES = {}


def fetch_data_sources():
    if DATA_SOURCES:
        return DATA_SOURCES

    global DATA_SOURCES

    registry = app.conf['PYRAMID_REGISTRY']
    data_source = registry.settings.get('twitcher.data_sources', '{}')
    try:
        DATA_SOURCES = json.loads(data_source)
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