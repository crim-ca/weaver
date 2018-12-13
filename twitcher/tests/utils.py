"""
Utility methods for various TestCase setup operations.
"""
from six.moves.configparser import ConfigParser
from typing import Any, AnyStr, Dict, Optional, Union
from pyramid import testing
from pyramid.registry import Registry
from pyramid.config import Configurator
# noinspection PyPackageRequirements
from webtest import TestApp
from twitcher.datatype import Service, AccessToken
from twitcher.tokengenerator import tokengenerator_factory
from twitcher.adapter import (
    TWITCHER_ADAPTER_DEFAULT,
    servicestore_factory,
    processstore_factory,
    jobstore_factory,
    tokenstore_factory,
)
from twitcher.database.mongodb import MongoDatabase
from twitcher.store.mongodb import MongodbServiceStore, MongodbProcessStore, MongodbJobStore
from twitcher.config import TWITCHER_CONFIGURATION_DEFAULT
from twitcher.wps import get_wps_url, get_wps_output_url, get_wps_output_path
import pyramid_celery
# noinspection PyPackageRequirements
import mock
import os

SettingsType = Dict[AnyStr, Union[AnyStr, float, int, bool]]


def get_settings_from_config_ini(config_ini_path=None, ini_section_name='app:main'):
    # type: (Optional[AnyStr], Optional[AnyStr]) -> SettingsType
    parser = ConfigParser()
    parser.read([config_ini_path or get_default_config_ini_path()])
    settings = dict(parser.items(ini_section_name))
    return settings


def get_default_config_ini_path():
    # type: (...) -> AnyStr
    return os.path.expanduser('~/birdhouse/etc/twitcher/twitcher.ini')


def setup_config_from_settings(settings=None):
    # type: (Optional[SettingsType]) -> Configurator
    settings = settings or {}
    config = testing.setUp(settings=settings)
    return config


def setup_config_from_ini(config_ini_file_path=None):
    # type: (Optional[AnyStr]) -> Configurator
    config_ini_file_path = config_ini_file_path or get_default_config_ini_path()
    settings = get_settings_from_config_ini(config_ini_file_path, 'app:main')
    settings.update(get_settings_from_config_ini(config_ini_file_path, 'celery'))
    config = testing.setUp(settings=settings)
    return config


def setup_config_with_mongodb(config=None):
    # type: (Optional[Configurator]) -> Configurator
    settings = {'mongodb.host': '127.0.0.1', 'mongodb.port': '27027', 'mongodb.db_name': 'twitcher_test'}
    settings = settings or {}
    config = config or testing.setUp(settings=settings)
    return config


def setup_mongodb_tokenstore(config):
    # type: (Configurator) -> AccessToken
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


def setup_config_with_pywps(config):
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


def setup_config_with_celery(config):
    # type: (Configurator) -> Configurator
    settings = config.get_settings()

    # override celery loader to specify configuration directly instead of ini file
    celery_settings = {
        'CELERY_BROKER_URL': 'mongodb://{}:{}/celery'.format(settings.get('mongodb.host'), settings.get('mongodb.port'))
    }
    pyramid_celery.loaders.INILoader.read_configuration = mock.MagicMock(return_value=celery_settings)
    config.include('pyramid_celery')
    config.configure_celery('')  # value doesn't matter because overloaded
    return config


def get_test_twitcher_app(config=None, settings_override=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> TestApp
    if not config:
        # default db required if none specified by config
        config = setup_config_from_settings({'twitcher.db_factory': MongoDatabase.type})
    if 'twitcher.adapter' not in config.registry.settings:
        config.registry.settings['twitcher.adapter'] = TWITCHER_ADAPTER_DEFAULT
    if 'twitcher.configuration' not in config.registry.settings:
        config.registry.settings['twitcher.configuration'] = TWITCHER_CONFIGURATION_DEFAULT
    config.registry.settings['twitcher.url'] = "https://localhost"
    config.registry.settings['twitcher.rpcinterface'] = False
    if settings_override:
        config.registry.settings.update(settings_override)
    # create the test application
    config.include('twitcher.wps')
    config.include('twitcher.wps_restapi')
    config.include('twitcher.rpcinterface')
    config.include('twitcher.tweens')
    config.scan()
    return TestApp(config.make_wsgi_app())


def get_settings_from_testapp(testapp):
    # type: (TestApp) -> Dict
    settings = {}
    if hasattr(testapp.app, 'registry'):
        settings = testapp.app.registry.settings or {}
    return settings


class Null(object):
    pass


def get_setting(env_var_name, app=None, setting_name=None):
    # type: (AnyStr, Optional[TestApp], Optional[AnyStr]) -> Any
    val = os.getenv(env_var_name, Null())
    if not isinstance(val, Null):
        return val
    if app:
        val = app.extra_environ.get(env_var_name, Null())
        if not isinstance(val, Null):
            return val
        if setting_name:
            val = app.extra_environ.get(setting_name, Null())
            if not isinstance(val, Null):
                return val
            settings = get_settings_from_testapp(app)
            if settings:
                val = settings.get(setting_name, Null())
                if not isinstance(val, Null):
                    return val
    return Null()


def init_twitcher_service(registry):
    # type: (Registry) -> None
    service_store = servicestore_factory(registry)
    service_store.save_service(Service({
        'type': '',
        'name': 'twitcher',
        'url': 'http://localhost/ows/proxy/twitcher',
        'public': True
    }))
