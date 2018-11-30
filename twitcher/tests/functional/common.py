from pyramid import testing
from pyramid.config import Configurator
from typing import Optional
from twitcher.wps import get_wps_url, get_wps_output_url, get_wps_output_path
from twitcher.tokengenerator import tokengenerator_factory
from twitcher.store import tokenstore_factory
from twitcher.adapter import servicestore_factory, processstore_factory, jobstore_factory
from twitcher.store.mongodb import MongodbTokenStore, MongodbServiceStore, MongodbProcessStore, MongodbJobStore


def setup_with_mongodb(config=None):
    # type: (Optional[Configurator]) -> Configurator
    settings = {'mongodb.host': '127.0.0.1', 'mongodb.port': '27027', 'mongodb.db_name': 'twitcher_test'}
    settings = settings or {}
    config = config or testing.setUp(settings=settings)
    return config


def setup_with_pywps(config):
    # type: (Configurator) -> Configurator
    settings = config.get_settings()
    settings.update({
        'PYWPS_CFG': {
            'server.url': get_wps_url(settings),
            'server.outputurl': get_wps_output_url(settings),
            'server.outputpath': get_wps_output_path(settings),
        },
    })
    config.registry.settings.update(settings)
    return config


def setup_celery(config):
    settings = config.get_settings()
    return {
        ''
        'CELERY_BROKER_URL': 'mongodb://{}:{}/celery'.format(settings.get('mongodb.host'), settings.get('mongodb.port'))
    }


def setup_mongodb_tokenstore(config):
    # type: (Configurator) -> MongodbTokenStore
    store = tokenstore_factory(config.registry)
    generator = tokengenerator_factory(config.registry)
    store.clear_tokens()
    access_token = generator.create_access_token()
    store.save_token(access_token)
    return access_token.token


def setup_mongodb_servicestore(config):
    # type: (Configurator) -> MongodbServiceStore
    store = servicestore_factory(config.registry)
    store.clear_services()
    return store


def setup_mongodb_processstore(config):
    # type: (Configurator) -> MongodbProcessStore
    store = processstore_factory(config.registry)
    store.clear_processes()
    # store must be recreated after clear because processes are added automatically on __init__
    store = processstore_factory(config.registry)
    return store


def setup_mongodb_jobstore(config):
    # type: (Configurator) -> MongodbJobStore
    store = jobstore_factory(config.registry)
    store.clear_jobs()
    return store
