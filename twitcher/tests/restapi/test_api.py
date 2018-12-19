import unittest
import colander
from pyramid.httpexceptions import HTTPFound
from twitcher.wps_restapi.swagger_definitions import (
    api_frontpage_uri,
    api_versions_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_swagger_json_service,
    API_TITLE,
    FrontpageSchema,
    VersionsSchema,
)
from twitcher.tests.utils import get_test_twitcher_app, get_test_twitcher_config, get_settings_from_testapp
from twitcher.database.memory import MemoryDatabase
from twitcher.adapter import TWITCHER_ADAPTER_DEFAULT


class GenericApiRoutesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        settings = {'twitcher.adapter': TWITCHER_ADAPTER_DEFAULT, 'twitcher.db_factory': MemoryDatabase.type}
        cls.testapp = get_test_twitcher_app(settings_override=settings)
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}

    def test_frontpage_format(self):
        resp = self.testapp.get(api_frontpage_uri, headers=self.json_headers)
        assert 200 == resp.status_code
        try:
            FrontpageSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))

    def test_version_format(self):
        resp = self.testapp.get(api_versions_uri, headers=self.json_headers)
        assert 200 == resp.status_code
        try:
            VersionsSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))

    def test_swagger_api_format(self):
        resp = self.testapp.get(api_swagger_ui_uri)
        assert 200 == resp.status_code
        assert "<title>{}</title>".format(API_TITLE) in resp.body

        resp = self.testapp.get(api_swagger_json_uri, headers=self.json_headers)
        assert 200 == resp.status_code
        assert 'tags' in resp.json
        assert 'info' in resp.json
        assert 'host' in resp.json
        assert 'paths' in resp.json
        assert 'swagger' in resp.json
        assert 'basePath' in resp.json


class AlternativeProxyBaseUrlApiRoutesTestCase(unittest.TestCase):

    # noinspection PyUnusedLocal
    @staticmethod
    def redirect_api_view(request):
        return HTTPFound(location=api_swagger_json_service.path)

    @classmethod
    def setUpClass(cls):
        cls.proxy_api_base_path = '/twitcher/rest'    # derived path for test
        cls.proxy_api_base_name = api_swagger_json_service.name + '_proxy'

        # create redirect view to simulate the server proxy pass
        settings = {'twitcher.adapter': TWITCHER_ADAPTER_DEFAULT, 'twitcher.db_factory': MemoryDatabase.type}
        config = get_test_twitcher_config(settings_override=settings)
        config.add_route(name=cls.proxy_api_base_name, path=cls.proxy_api_base_path)
        config.add_view(cls.redirect_api_view, route_name=cls.proxy_api_base_name)

        cls.testapp = get_test_twitcher_app(config)
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}

    def test_swagger_api_request_base_path(self):
        resp = self.testapp.get(api_swagger_ui_uri)
        assert 200 == resp.status_code
        assert "<title>{}</title>".format(API_TITLE) in resp.body

        twitcher_server_url = get_settings_from_testapp(self.testapp).get('twitcher.url') + self.proxy_api_base_path
        resp = self.testapp.get(self.proxy_api_base_path, headers=self.json_headers,
                                extra_environ={'TWITCHER_URL': twitcher_server_url})
        resp = resp.follow()
        assert 200 == resp.status_code
        assert resp.json['basePath'] == self.proxy_api_base_path
