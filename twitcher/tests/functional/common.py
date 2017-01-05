from pyramid import testing

from twitcher.tokengenerator import tokengenerator_factory
from twitcher.store import tokenstore_factory
from twitcher.store import servicestore_factory


def setup_with_mongodb():
    settings = {'mongodb.host': '127.0.0.1', 'mongodb.port': '27027', 'mongodb.db_name': 'twitcher_test'}
    config = testing.setUp(settings=settings)
    return config


def setup_mongodb_tokenstore(config):
    store = tokenstore_factory(config.registry)
    generator = tokengenerator_factory(config.registry)
    store.clear_tokens()
    access_token = generator.create_access_token()
    store.save_token(access_token)
    return access_token.token


def setup_mongodb_servicestore(config):
    store = servicestore_factory(config.registry)
    store.clear_services()
