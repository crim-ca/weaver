from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import os

import logging
logger = logging.getLogger(__name__)


def postgresdb(registry):
    settings = registry.settings
    #engine = create_engine('postgresql://postgres:postgres@localhost/ziggudb', echo=True)

    '''
    database_url = 'postgresql://'\
                   +settings['postgresdb.user_name'] + \
                   ':'+settings['postgresdb.password'] + \
                   '@' + settings['postgresdb.host'] +\
                   '/' + settings['postgresdb.db_name']
    '''
    database_url = 'postgresql://' \
                   + os.getenv('POSTGRES_USER') + \
                   ':' + os.getenv('POSTGRES_PASSWORD') + \
                   '@' + os.getenv('POSTGRES_HOST') + \
                   '/' + os.getenv('POSTGRES_DB')

    engine = create_engine(database_url, echo=True)
    db = sessionmaker(bind=engine)()
    return db

def includeme(config):
    config.registry.db = postgresdb(config.registry)

    def _add_db(request):
        db = request.registry.db
        # if db_url.username and db_url.password:
        #     db.authenticate(db_url.username, db_url.password)
        return db
    config.add_request_method(_add_db, 'db', reify=True)
