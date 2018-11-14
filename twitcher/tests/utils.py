"""
Utility methods for various TestCase setup operations.
"""
from six.moves.configparser import ConfigParser
from typing import Any, Optional, Text, Dict
from pyramid import testing
# noinspection PyPackageRequirements
from webtest import TestApp
from twitcher.adapter import servicestore_factory
from twitcher.datatype import Service
from twitcher.store import SUPPORTED_DB_FACTORIES, DB_MEMORY
from twitcher.config import TWITCHER_CONFIGURATION_DEFAULT
from twitcher import main
import os


def get_settings_from_config_ini(config_ini_path, ini_main_section_name='app:main'):
    parser = ConfigParser()
    parser.read([config_ini_path])
    settings = dict(parser.items(ini_main_section_name))
    return settings


def config_setup_from_ini(config_ini_file_path):
    settings = get_settings_from_config_ini(config_ini_file_path, 'app:main')
    settings.update(get_settings_from_config_ini(config_ini_file_path, 'celery'))
    config = testing.setUp(settings=settings)
    return config


def get_test_twitcher_app(twitcher_config=TWITCHER_CONFIGURATION_DEFAULT):
    # parse settings from ini file to pass them to the application
    config = config_setup_from_ini('/home/fractal/birdhouse/etc/twitcher/twitcher.ini')
    # create the test application
    config.registry.settings['twitcher.db_factory'] = get_test_store_type_from_env()
    config.registry.settings['twitcher.rpcinterface'] = False
    config.registry.settings['twitcher.configuration'] = twitcher_config
    config.registry.settings['twitcher.url'] = 'https://localhost'
    app = TestApp(main({}, **config.registry.settings))
    return app


def get_settings_from_testapp(app):
    # type: (TestApp) -> Dict
    return app.app.registry.settings or {}


def get_setting(app, env_var_name, setting_name=None):
    # type: (TestApp, Text, Optional[Text]) -> Any
    val = os.getenv(env_var_name)
    if val:
        return val
    if setting_name:
        settings = get_settings_from_testapp(app)
        if settings:
            val = settings.get(setting_name)
            if val:
                return val
    return None


def init_twitcher_service(registry):
    service_store = servicestore_factory(registry)
    service_store.save_service(Service({
        'type': '',
        'name': 'twitcher',
        'url': 'http://localhost/ows/proxy/twitcher',
        'public': True
    }))


def get_test_store_type_from_env():
    twitcher_store_type = os.environ.get('TWITCHER_STORE_TYPE', DB_MEMORY)
    if twitcher_store_type not in SUPPORTED_DB_FACTORIES:
        raise Exception('The store type `{}` is not implemented'.format(twitcher_store_type))
    return twitcher_store_type
