from pyramid.httpexceptions import HTTPFound, HTTPUnauthorized, HTTPForbidden
from weaver.wps_restapi.swagger_definitions import (
    api_frontpage_uri,
    api_versions_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_swagger_json_service,
    API_TITLE,
    FrontpageSchema,
    VersionsSchema,
)
from weaver.tests.utils import get_test_weaver_app, get_test_weaver_config, get_settings_from_testapp
from weaver.database.memory import MemoryDatabase
from weaver.adapter import WEAVER_ADAPTER_DEFAULT
import colander
import unittest
# noinspection PyPackageRequirements
import mock
import os


class GenericApiRoutesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        settings = {'weaver.adapter': WEAVER_ADAPTER_DEFAULT, 'weaver.db_factory': MemoryDatabase.type}
        cls.testapp = get_test_weaver_app(settings_override=settings)
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

    def test_status_unauthorized_and_forbidden(self):
        # methods should return corresponding status codes, shouldn't be the default '403' on both cases
        with mock.patch('weaver.utils.get_weaver_url', side_effect=HTTPUnauthorized):
            resp = self.testapp.get(api_frontpage_uri, headers=self.json_headers, expect_errors=True)
            assert 401 == resp.status_code
        with mock.patch('weaver.utils.get_weaver_url', side_effect=HTTPForbidden):
            resp = self.testapp.get(api_frontpage_uri, headers=self.json_headers, expect_errors=True)
            assert 403 == resp.status_code

    def test_status_not_found_and_method_not_allowed(self):
        resp = self.testapp.post('/random', headers=self.json_headers, expect_errors=True)
        assert 404 == resp.status_code

        # test an existing route with wrong method, shouldn't be the default '404' on both cases
        resp = self.testapp.post(api_frontpage_uri, headers=self.json_headers, expect_errors=True)
        assert 405 == resp.status_code


class AlternativeProxyBaseUrlApiRoutesTestCase(unittest.TestCase):

    # noinspection PyUnusedLocal
    @staticmethod
    def redirect_api_view(request):
        return HTTPFound(location=api_swagger_json_service.path)

    @classmethod
    def setUpClass(cls):
        # derived path for testing simulated server proxy pass
        cls.proxy_api_base_path = '/weaver/rest'
        cls.proxy_api_base_name = api_swagger_json_service.name + '_proxy'

        # create redirect view to simulate the server proxy pass
        settings = {'weaver.adapter': WEAVER_ADAPTER_DEFAULT, 'weaver.db_factory': MemoryDatabase.type}
        config = get_test_weaver_config(settings_override=settings)
        config.add_route(name=cls.proxy_api_base_name, path=cls.proxy_api_base_path)
        config.add_view(cls.redirect_api_view, route_name=cls.proxy_api_base_name)

        cls.testapp = get_test_weaver_app(config)
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}

    def test_swagger_api_request_base_path_proxied(self):
        """
        Validates that Swagger JSON properly redefines the host/path to test live requests on Swagger UI
        when the app's URI results from a proxy pass redirect under another route.
        """
        # setup environment that would define the new weaver location for the proxy pass
        weaver_server_host = get_settings_from_testapp(self.testapp).get('weaver.url')
        weaver_server_url = weaver_server_host + self.proxy_api_base_path
        with mock.patch.dict('os.environ', {'WEAVER_URL': weaver_server_url}):
            resp = self.testapp.get(self.proxy_api_base_path, headers=self.json_headers)
            resp = resp.follow()
            assert 200 == resp.status_code
            assert self.proxy_api_base_path not in resp.json['host']
            assert resp.json['basePath'] == self.proxy_api_base_path

            # validate that swagger UI still renders and has valid URL
            resp = self.testapp.get(api_swagger_ui_uri)
            assert 200 == resp.status_code
            assert "<title>{}</title>".format(API_TITLE) in resp.body

    def test_swagger_api_request_base_path_original(self):
        """
        Validates that Swagger JSON properly uses the original host/path to test live requests on Swagger UI
        when the app's URI results direct route access.
        """
        resp = self.testapp.get(api_swagger_ui_uri)
        assert 200 == resp.status_code
        assert "<title>{}</title>".format(API_TITLE) in resp.body

        # ensure that environment that would define the weaver location is not defined for local app
        with mock.patch.dict('os.environ'):
            os.environ.pop('WEAVER_URL', None)
            resp = self.testapp.get(self.proxy_api_base_path, headers=self.json_headers)
            resp = resp.follow()
            assert 200 == resp.status_code
            assert self.proxy_api_base_path not in resp.json['host']
            assert resp.json['basePath'] == api_frontpage_uri

            # validate that swagger UI still renders and has valid URL
            resp = self.testapp.get(api_swagger_ui_uri)
            assert 200 == resp.status_code
            assert "<title>{}</title>".format(API_TITLE) in resp.body
