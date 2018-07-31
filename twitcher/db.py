# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
# maybe use event to register mongodb

from sqlalchemy.engine import engine_from_config
from sqlalchemy.orm.session import sessionmaker
from zope.sqlalchemy import register as sa_register
import transaction
import pymongo
import os

import logging
logger = logging.getLogger(__name__)


class MongoDB:
    __db = None

    @classmethod
    def get(cls, registry):
        if not cls.__db:
            settings = registry.settings
            client = pymongo.MongoClient(settings['mongodb.host'], int(settings['mongodb.port']))
            cls.__db = client[settings['mongodb.db_name']]
        return cls.__db


def mongodb(registry):
    db = MongoDB.get(registry)
    db.services.create_index("name", unique=True)
    db.services.create_index("url", unique=True)
    db.processes.create_index("identifier", unique=True)
    return db


def get_postgresdb_url():
    return "postgresql://%s:%s@%s:%s/%s" % (
        os.getenv("POSTGRES_USER", "postgres"),
        os.getenv("POSTGRES_PASSWORD", "postgres"),
        os.getenv("POSTGRES_HOST", "localhost"),
        os.getenv("POSTGRES_PORT", "5432"),
        os.getenv("POSTGRES_DB", "twitcher_db"),
    )


def get_postgres_engine(settings, prefix='sqlalchemy.'):
    settings[prefix+'url'] = get_postgresdb_url()
    return engine_from_config(settings, prefix)


def get_session_factory(engine):
    factory = sessionmaker()
    factory.configure(bind=engine)
    return factory


def get_tm_session(session_factory, transaction_manager):
    db_session = session_factory()
    sa_register(db_session, transaction_manager=transaction_manager)
    return db_session


def get_postgresdb_session_from_settings(settings):
    session_factory = get_session_factory(get_postgres_engine(settings))
    db_session = get_tm_session(session_factory, transaction)
    return db_session


def database_factory(registry):
    settings = registry.settings
    if settings.get('db_factory') == 'postgres':
        return get_postgresdb_session_from_settings(settings)
    return mongodb(registry)


def includeme(config):
    config.registry.db = database_factory(config.registry)

    def _add_db(request):
        db = request.registry.db
        # if db_url.username and db_url.password:
        #     db.authenticate(db_url.username, db_url.password)
        return db
    config.add_request_method(_add_db, 'db', reify=True)
    config.add_request_method(lambda r: get_tm_session(_add_db, r.tm), 'db_session', reify=True)
