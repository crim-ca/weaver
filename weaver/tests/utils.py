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
from weaver.datatype import Service
from weaver.adapter import (
    weaver_ADAPTER_DEFAULT,
    servicestore_factory,
    processstore_factory,
    jobstore_factory,
    tokenstore_factory,
)
from weaver.database.mongodb import MongoDatabase
from weaver.store.mongodb import MongodbServiceStore, MongodbProcessStore, MongodbJobStore
from weaver.config import WEAVER_CONFIGURATION_DEFAULT
from weaver.wps import get_wps_url, get_wps_output_url, get_wps_output_path
from weaver.warning import MissingParameterWarning, UnsupportedOperationWarning
import pyramid_celery
import warnings
# noinspection PyPackageRequirements
import mock
import os

SettingsType = Dict[AnyStr, Union[AnyStr, float, int, bool]]


def ignore_wps_warnings(func):
    """Wrapper that eliminates WPS related warnings during testing logging."""
    def do_test(self, *args, **kwargs):
        with warnings.catch_warnings():
            for warn in [MissingParameterWarning, UnsupportedOperationWarning]:
                for msg in ["Parameter 'request*", "Parameter 'service*"]:
                    warnings.filterwarnings(action="ignore", message=msg, category=warn)
            func(self, *args, **kwargs)
    return do_test


def get_settings_from_config_ini(config_ini_path=None, ini_section_name='app:main'):
    # type: (Optional[AnyStr], Optional[AnyStr]) -> SettingsType
    parser = ConfigParser()
    parser.read([config_ini_path or get_default_config_ini_path()])
    settings = dict(parser.items(ini_section_name))
    return settings


def get_default_config_ini_path():
    # type: (...) -> AnyStr
    return os.path.expanduser('~/birdhouse/etc/weaver/weaver.ini')


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
    settings = {'mongodb.host': '127.0.0.1',
                'mongodb.port': '27027',
                'mongodb.db_name': 'weaver_test',
                'weaver.db_factory': MongoDatabase.type}
    settings = settings or {}
    config = config or testing.setUp(settings=settings)

    factory_setting = 'weaver.db_factory'
    factory_value = config.registry.settings.get(factory_setting)
    if factory_value != MongoDatabase.type:
        warnings.warn("Overriding value `{}` expected to be `{}`, was `{}`."
                      .format(factory_setting, MongoDatabase.type, factory_value))

    return config


def setup_mongodb_servicestore(config):
    # type: (Configurator) -> MongodbServiceStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = servicestore_factory(config.registry)
    store.clear_services()
    # noinspection PyTypeChecker
    return store


def setup_mongodb_processstore(config):
    # type: (Configurator) -> MongodbProcessStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = processstore_factory(config.registry)
    store.clear_processes()
    # store must be recreated after clear because processes are added automatically on __init__
    store = processstore_factory(config.registry)
    # noinspection PyTypeChecker
    return store


def setup_mongodb_jobstore(config):
    # type: (Configurator) -> MongodbJobStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = jobstore_factory(config.registry)
    store.clear_jobs()
    # noinspection PyTypeChecker
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


def get_test_weaver_config(config=None, settings_override=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> Configurator
    if not config:
        # default db required if none specified by config
        config = setup_config_from_settings({'weaver.db_factory': MongoDatabase.type})
    if 'weaver.adapter' not in config.registry.settings:
        config.registry.settings['weaver.adapter'] = weaver_ADAPTER_DEFAULT
    if 'weaver.configuration' not in config.registry.settings:
        config.registry.settings['weaver.configuration'] = WEAVER_CONFIGURATION_DEFAULT
    config.registry.settings['weaver.url'] = "https://localhost"
    config.registry.settings['weaver.rpcinterface'] = False
    if settings_override:
        config.registry.settings.update(settings_override)
    # create the test application
    config.include('weaver.wps')
    config.include('weaver.wps_restapi')
    config.include('weaver.rpcinterface')
    config.include('weaver.tweens')
    return config


def get_test_weaver_app(config=None, settings_override=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> TestApp
    config = get_test_weaver_config(config=config, settings_override=settings_override)
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


def init_weaver_service(registry):
    # type: (Registry) -> None
    service_store = servicestore_factory(registry)
    service_store.save_service(Service({
        'type': '',
        'name': 'weaver',
        'url': 'http://localhost/ows/proxy/weaver',
        'public': True
    }))
