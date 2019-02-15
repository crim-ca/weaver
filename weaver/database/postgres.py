from weaver.database.base import DatabaseInterface
from weaver import WEAVER_ROOT_DIR
from sqlalchemy.engine import engine_from_config
from sqlalchemy.orm import sessionmaker, configure_mappers
from sqlalchemy.engine.reflection import Inspector
# noinspection PyPackageRequirements
from zope.sqlalchemy import register as sa_register
import sqlalchemy as sa
import transaction
import inspect
import alembic
import warnings
import os


# run configure_mappers after defining all of the models to ensure
# all relationships can be setup
configure_mappers()


class PostgresDatabase(DatabaseInterface):
    _db_session = None
    _registry = None
    type = 'postgres'

    def __init__(self, registry):
        # TODO: remove when implemented
        warnings.warn("Not implemented {} implementation (models not defined).".format(self.type))
        super(PostgresDatabase, self).__init__(registry)
        self._registry = registry
        self._db_session = get_postgres_session_from_settings(registry.settings)

    def is_ready(self):
        return is_database_ready(self._registry.settings)

    def run_migration(self):
        run_database_migration(self._registry.settings)

    def rollback(self):
        self._db_session.rollback()

    def get_store(self, store_type, **store_kwargs):
        warnings.warn("Not implemented {}.get_store implementation.".format(self.type))
        raise NotImplementedError

    def get_session(self):
        return self._db_session

    def get_information(self):
        s = sa.sql.select(['version_num'], from_obj='alembic_version')
        result = self._db_session.execute(s).fetchone()
        db_version = result['version_num']
        return {'version': db_version, 'type': self.type}

    def get_revision(self):
        warnings.warn("Not implemented {}.get_revision implementation.".format(self.type))
        raise NotImplementedError


def get_postgresdb_url():
    return "postgresql://%s:%s@%s:%s/%s" % (
        os.getenv("POSTGRES_USER", "postgres"),
        os.getenv("POSTGRES_PASSWORD", "postgres"),
        os.getenv("POSTGRES_HOST", "localhost"),
        os.getenv("POSTGRES_PORT", "5432"),
        os.getenv("POSTGRES_DB", "weaver_db"),
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


def get_postgres_session_from_settings(settings):
    session_factory = get_session_factory(get_postgres_engine(settings))
    db_session = get_tm_session(session_factory, transaction)
    return db_session


def get_alembic_ini_path():
    return '{path}/alembic.ini'.format(path=WEAVER_ROOT_DIR)


def run_database_migration(settings):
    if settings.get('weaver.db_factory') == PostgresDatabase.type:
        alembic_args = ['-c', get_alembic_ini_path(), 'upgrade', 'heads']
        # noinspection PyUnresolvedReferences
        alembic.config.main(argv=alembic_args)


# noinspection PyUnusedLocal
def is_database_ready(settings):
    # TODO: make models and refer them in 'models' file
    warnings.warn("Not implemented {}.is_database_ready implementation.".format(PostgresDatabase.type))
    return False

    inspector = Inspector.from_engine(get_postgres_engine(dict()))
    table_names = inspector.get_table_names()

    for name, obj in inspect.getmembers(models):
        if inspect.isclass(obj):
            # noinspection PyBroadException
            try:
                curr_table_name = obj.__tablename__
                if curr_table_name not in table_names:
                    return False
            except Exception:
                continue
    return True
