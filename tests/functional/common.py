from pyramid import testing

def setup_with_db():
    settings = {'mongodb.host':'127.0.0.1', 'mongodb.port':'27027', 'mongodb.db_name': 'twitcher_test'}
    config = testing.setUp(settings=settings)
    return config
      
