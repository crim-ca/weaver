import unittest

import colander
import mock
from pyramid.httpexceptions import HTTPForbidden, HTTPFound, HTTPUnauthorized

from tests.utils import get_test_weaver_app, get_test_weaver_config
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.wps_restapi import swagger_definitions as sd


class GenericApiRoutesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.testapp = get_test_weaver_app(settings=None)
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}

    def test_frontpage_format(self):
        resp = self.testapp.get(sd.api_frontpage_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        try:
            sd.FrontpageSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))

    def test_version_format(self):
        resp = self.testapp.get(sd.api_versions_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        try:
            sd.VersionsSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))

    def test_conformance_format(self):
        resp = self.testapp.get(sd.api_conformance_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        try:
            sd.ConformanceSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))

    def test_swagger_api_format(self):
        resp = self.testapp.get(sd.api_swagger_ui_service.path)
        assert resp.status_code == 200
        assert "<title>{}</title>".format(sd.API_TITLE) in resp.text

        resp = self.testapp.get(sd.api_swagger_json_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        assert "tags" in resp.json
        assert "info" in resp.json
        assert "host" in resp.json
        assert "paths" in resp.json
        assert "swagger" in resp.json
        assert "basePath" in resp.json

    def test_status_unauthorized_and_forbidden(self):
        """
        Validates that 401/403 status codes are correctly handled and that the appropriate one is returned.
        Shouldn't be the default behaviour to employ 403 on both cases.
        """
        with mock.patch("weaver.wps_restapi.api.get_weaver_url", side_effect=HTTPUnauthorized):
            resp = self.testapp.get(sd.api_frontpage_service.path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 401
        with mock.patch("weaver.wps_restapi.api.get_weaver_url", side_effect=HTTPForbidden):
            resp = self.testapp.get(sd.api_frontpage_service.path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 403

    def test_status_not_found_and_method_not_allowed(self):
        """
        Validates that 404/405 status codes are correctly handled and that the appropriate one is returned.
        Shouldn't be the default behaviour to employ 404 on both cases.
        """
        resp = self.testapp.post("/random", headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404

        # test an existing route with wrong method, shouldn't be the default '404' on both cases
        resp = self.testapp.post(sd.api_frontpage_service.path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 405


class RebasedApiRoutesTestCase(unittest.TestCase):
    @classmethod
    def redirect_api_view(cls, request):
        path = request.url.replace(cls.proxy_path, "")  # noqa
        return HTTPFound(location=path)

    @classmethod
    def setUpClass(cls):
        cls.proxy_path = "/weaver-proxy"
        cls.app_host = "localhost"
        cls.app_base_url = "http://" + cls.app_host
        cls.app_proxy_url = cls.app_base_url + cls.proxy_path
        cls.app_proxy_json = cls.proxy_path + sd.api_swagger_json_service.path
        cls.app_proxy_ui = cls.proxy_path + sd.api_swagger_ui_service.path
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON}

    def test_swagger_api_request_base_path_proxied(self):
        """
        Validates that Swagger JSON properly redefines the host/path to test live requests on Swagger UI
        when the app's URI resides behind a proxy pass redirect path as specified by setting ``weaver.url``.
        """

        # fake "proxy" derived path for testing simulated server proxy pass
        # create redirect views to simulate the server proxy pass
        config = get_test_weaver_config(settings={"weaver.url": self.app_proxy_url})  # real access proxy path in config
        for service in [sd.api_swagger_json_service, sd.api_swagger_ui_service]:
            name = service.name + "_proxy"
            config.add_route(name=name, path=self.proxy_path + service.path)
            config.add_view(self.redirect_api_view, route_name=name)
        testapp = get_test_weaver_app(config)

        # setup environment that would define the new weaver location for the proxy pass
        resp = testapp.get(self.app_proxy_json, headers=self.json_headers)
        assert resp.status_code == 302, "Request should be at proxy level at this point."
        resp = resp.follow()
        assert resp.status_code == 200
        assert resp.json["host"] == self.app_host
        assert resp.json["basePath"] == self.proxy_path, \
            "Proxy path specified by setting 'weaver.url' should be used in API definition to allow live requests."

        # validate that swagger UI still renders and has valid URL
        resp = testapp.get(self.app_proxy_ui)
        assert resp.status_code == 302, "Request should be at proxy level at this point."
        resp = resp.follow()
        assert resp.status_code == 200
        assert "<title>{}</title>".format(sd.API_TITLE) in resp.text

    def test_swagger_api_request_base_path_original(self):
        """
        Validates that Swagger JSON properly uses the original host/path to test live requests on Swagger UI
        when the app's URI results direct route access.
        """
        # base app without proxy pass
        # ensure that setting that would define the weaver's location is not defined for local app
        config = get_test_weaver_config(settings={"weaver.url": None})
        testapp = get_test_weaver_app(config)

        resp = testapp.get(sd.api_swagger_json_service.path, headers=self.json_headers)
        assert resp.status_code == 200, "API definition should be accessed directly"
        assert resp.json["host"] in [self.app_host, "{}:80".format(self.app_host)]
        assert resp.json["basePath"] == sd.api_frontpage_service.path

        resp = testapp.get(sd.api_swagger_ui_service.path)
        assert resp.status_code == 200, "API definition should be accessed directly"
        assert "<title>{}</title>".format(sd.API_TITLE) in resp.text
