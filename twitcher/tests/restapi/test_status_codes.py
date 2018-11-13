from unittest import TestCase
# noinspection PyPackageRequirements
from webtest import TestApp
from twitcher.wps_restapi.swagger_definitions import (
    api_frontpage_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_versions_uri,
    providers_uri,
    jobs_short_uri,
    jobs_full_uri,
)
from six.moves import configparser
from pyramid import testing
from twitcher import main
from twitcher.config import TWITCHER_CONFIGURATION_DEFAULT
from twitcher.adapter import servicestore_factory
from twitcher.datatype import Service
import os

store_type_memory = 'memory'
store_type_mongodb = 'mongodb'
store_types = [
    store_type_memory,
    store_type_mongodb,
]

public_routes = [
    api_frontpage_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_versions_uri,
]
forbidden_routes = [
    jobs_short_uri,     # should always be visible
    jobs_full_uri,      # could be 401
]
not_found_routes = [
    '/jobs/not-found',
    '/providers/not-found',
]


def get_settings_from_config_ini(config_ini_path, ini_main_section_name='app:main'):
    parser = configparser.ConfigParser()
    parser.read([config_ini_path])
    settings = dict(parser.items(ini_main_section_name))
    return settings


def config_setup_from_ini(config_ini_file_path):
    settings = get_settings_from_config_ini(config_ini_file_path, 'app:main')
    settings.update(get_settings_from_config_ini(config_ini_file_path, 'celery'))
    config = testing.setUp(settings=settings)
    return config


def get_test_twitcher_app():
    # parse settings from ini file to pass them to the application
    config = config_setup_from_ini('/home/fractal/birdhouse/etc/twitcher/twitcher.ini')
    # create the test application
    config.registry.settings['twitcher.db_factory'] = get_test_store_type_from_env()
    config.registry.settings['twitcher.rpcinterface'] = False
    #init_twitcher_service(config.registry)
    app = TestApp(main({'__file__': '/home/fractal/birdhouse/etc/twitcher/twitcher.ini'}, **config.registry.settings))
    return app


def init_twitcher_service(registry):
    service_store = servicestore_factory(registry)
    service_store.save_service(Service({
        'type': '',
        'name': 'twitcher',
        'url': 'http://localhost/ows/proxy/twitcher',
        'public': True
    }))


def get_test_store_type_from_env():
    twitcher_store_type = os.environ.get('TWITCHER_STORE_TYPE', store_type_memory)
    if twitcher_store_type not in store_types:
        raise Exception('The store type {} is not implemented'.format(twitcher_store_type))
    return twitcher_store_type


"""
this routine should verify that the twitcher app returns correct status codes for common cases, such as
- not found
- forbidden (possibly with a difference between unauthorized and unauthentificated
- resource added
- ok
"""
# create a twitcher app using configuration
# invoke request on app:
#   not found provider, job and process
#   private resource
#   login, then private resource
#   add job
#   fetch job and find it
#   search features
# receive response and assert that status codes match


class StatusCodeTestCase(TestCase):

    headers = {'accept': 'application/json'}

    def setUp_old(self):
        self.app = get_test_twitcher_app()

    def setUp(self):
        config = testing.setUp()
        config.registry.settings['twitcher.configuration'] = TWITCHER_CONFIGURATION_DEFAULT
        config.registry.settings['twitcher.url'] = 'https://localhost'
        app = main({}, **config.registry.settings)
        self.testapp = TestApp(app)

    def test_200(self):
        for uri in public_routes:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(200, resp.status_code, 'route {} did not return 200'.format(uri))

    """
    def test_401(self):
        for uri in forbidden_routes:
            resp = self.app.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(401, resp.status_code, 'route {} did not return 401'.format(uri))
    """

    def test_404(self):
        for uri in not_found_routes:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(404, resp.status_code, 'route {} did not return 404'.format(uri))


"""
this routine should make sure that the services store jobs, processes and providers correctly,
  but directly from the services, and not only by status codes
foreach of jobs, processes, providers
  save entity
  fetch entity and verify informations
"""
# create a store
# instantiate wps_restapi with that store
# test provider
#   create provider
#   create process in provider
#   fetch process data
#   submit job with dummy data
#   fetch job and see its existence
# sda


class CRUDTestCase(TestCase):
    pass
