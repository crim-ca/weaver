from unittest import TestCase
from webtest import TestApp
from twitcher.wps_restapi.swagger_definitions import api_frontpage_uri, api_swagger_ui_uri, api_swagger_json_uri, \
    api_versions_uri, providers_uri, jobs_short_uri
from pyramid.config import Configurator
from six.moves import configparser
from pyramid import testing
from twitcher import main
from os import environ

public_routes = [
    api_frontpage_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_versions_uri,
]
forbidden_routes = [
    providers_uri,
    jobs_short_uri,
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
    # required redefinition because root models' location is not the same from within this test file
    # config.add_settings({'ziggurat_foundations.model_locations.User': 'models:User',
    #                     'ziggurat_foundations.model_locations.user': 'models:User', })
    # config.include('ziggurat_foundations.ext.pyramid.sign_in')
    # config.registry.settings['magpie.db_migration_disabled'] = True
    # scan dependencies
    # config.include('magpie')
    # create the test application
    config.registry.settings['twitcher.db_factory'] = 'memory'
    config.registry.settings['twitcher.rpcinterface'] = False
    app = TestApp(main({'__file__': '/home/fractal/birdhouse/etc/twitcher/twitcher.ini'}, **config.registry.settings))
    return app




class StatusCodeTestCase(TestCase):

    def setUp(self):
        self.app = get_test_twitcher_app()

    def test_200(self):
        for uri in public_routes:
            resp = self.app.get(uri, expect_errors=True)
            self.assertEqual(200, resp.status_code, 'route {} did not return 200'.format(uri))

    def test_401(self):
        for uri in forbidden_routes:
            resp = self.app.get(uri, expect_errors=True)
            self.assertEqual(401, resp.status_code, 'route {} did not return 401'.format(uri))

    def test_404(self):
        for uri in not_found_routes:
            resp = self.app.get(uri, expect_errors=True)
            self.assertEqual(404, resp.status_code, 'route {} did not return 404'.format(uri))
