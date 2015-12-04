from pyramid import testing

from twitcher.tokens import tokenstore_factory, tokengenerator_factory

def setup_with_db():
    settings = {'mongodb.host':'127.0.0.1', 'mongodb.port':'27027', 'mongodb.db_name': 'twitcher_test'}
    config = testing.setUp(settings=settings)
    return config

def setup_tokenstore(config):
    store = tokenstore_factory(config.registry)
    generator = tokengenerator_factory(config.registry)
    store.clean_tokens()
    access_token = generator.create_access_token()
    store.save_token(access_token)
    return access_token.token

      
