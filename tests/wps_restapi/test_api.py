import json
import unittest
from urllib.parse import urlparse

import colander
import mock
import pyramid.testing
from pyramid.httpexceptions import HTTPForbidden, HTTPFound, HTTPUnauthorized
from webtest import TestApp as WebTestApp

from tests.utils import get_test_weaver_app, get_test_weaver_config
from weaver.formats import ContentType
from weaver.utils import get_header, request_extra
from weaver.wps_restapi import swagger_definitions as sd


class GenericApiRoutesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.testapp = get_test_weaver_app(settings={"weaver.wps": True, "weaver.wps_restapi": True})
        cls.json_headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}

    def test_frontpage_format(self):
        resp = self.testapp.get(sd.api_frontpage_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        try:
            sd.FrontpageSchema().deserialize(body)
        except colander.Invalid as ex:
            body = json.dumps(body, indent=2, ensure_ascii=False)
            self.fail(f"expected valid response format as defined in schema [{ex!s}] in\n{body}")
        refs = [link["rel"] for link in body["links"]]
        assert len(body["links"]) == len(set(refs)), "Link relationships must all be unique"
        for link in body["links"]:
            path = link["href"]
            rtype = link["type"]
            if rtype in ContentType.ANY_XML:
                rtype = ContentType.ANY_XML
            else:
                rtype = [rtype]
            rel = link["rel"]

            # request endpoint to validate it is accessible
            if "localhost" in path:
                resp = self.testapp.get(urlparse(path).path, expect_errors=True)  # allow error for wps without queries
            else:
                resp = request_extra("GET", path, retries=3, retry_after=True, ssl_verify=False, allow_redirects=True)
            user_agent = get_header("user-agent", resp.request.headers)
            if resp.status_code == 403 and "python" in user_agent:
                # some sites will explicitly block bots, retry with mocked user-agent simulating human user access
                resp = request_extra("GET", path, headers={"User-Agent": "Mozilla"},
                                     retries=3, retry_after=True, ssl_verify=False, allow_redirects=True)

            # validate contents and expected media-type
            code = resp.status_code
            test = f"({rel}) [{path}]"
            assert code in [200, 400], f"Reference link expected to be found, got [{code}] for {test}"

            # FIXME: patch broken content-type from reference websites
            #  (see https://github.com/opengeospatial/NamingAuthority/issues/183)
            ctype_header_links = {
                "http://schemas.opengis.net/wps/": ContentType.APP_XML
            }
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if not ctype:
                for ref_link in ctype_header_links:
                    if path.startswith(ref_link):
                        ctype = ctype_header_links[ref_link]
                        break
            assert ctype in rtype, f"Reference link content does not match [{ctype}]!=[{rtype}] for {test}"

    def test_version_format(self):
        resp = self.testapp.get(sd.api_versions_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        try:
            sd.VersionsSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail(f"expected valid response format as defined in schema [{ex!s}]")

    def test_conformance_format(self):
        resp = self.testapp.get(sd.api_conformance_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        try:
            sd.ConformanceSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail(f"expected valid response format as defined in schema [{ex!s}]")

    def test_swagger_api_format(self):
        resp = self.testapp.get(sd.api_swagger_ui_service.path)
        assert resp.status_code == 200
        assert f"<title>{sd.API_TITLE}</title>" in resp.text

        resp = self.testapp.get(sd.openapi_json_service.path, headers=self.json_headers)
        assert resp.status_code == 200
        assert "tags" in resp.json
        assert "info" in resp.json
        assert "host" in resp.json
        assert "paths" in resp.json
        assert "openapi" in resp.json
        assert "basePath" in resp.json

    def test_status_unauthorized_and_forbidden(self):
        """
        Validates that 401/403 status codes are correctly handled and that the appropriate one is returned.

        Shouldn't be the default behaviour to employ 403 on both cases.
        """
        # mock any function called inside the corresponding views just so that the exception is raised
        # check for the resulting status code to see if that raised HTTP exception was correctly handled
        with mock.patch("weaver.wps_restapi.api.api_frontpage_body", side_effect=HTTPUnauthorized):
            resp = self.testapp.get(sd.api_frontpage_service.path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 401
        with mock.patch("weaver.wps_restapi.api.api_frontpage_body", side_effect=HTTPForbidden):
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
    proxy_calls = []

    @classmethod
    def redirect_api_view(cls, request):
        path = request.url.replace(cls.proxy_path, "")  # noqa
        cls.proxy_calls.append((request.url, path))
        return HTTPFound(location=path)

    @classmethod
    def setUpClass(cls):
        cls.proxy_path = "/weaver-proxy"
        cls.app_host = "localhost"
        cls.app_base_url = "http://" + cls.app_host
        cls.app_proxy_url = cls.app_base_url + cls.proxy_path
        cls.app_proxy_json = cls.proxy_path + sd.openapi_json_service.path
        cls.app_proxy_ui = cls.proxy_path + sd.api_swagger_ui_service.path
        cls.json_headers = {"Accept": ContentType.APP_JSON}

    def setUp(self):
        self.proxy_calls = []

    def test_swagger_api_request_base_path_proxied(self):
        """
        Validates that Swagger JSON properly redefines the host/path to test live requests on Swagger UI when the app's
        URI resides behind a proxy pass redirect path as specified by setting ``weaver.url``.
        """

        # fake "proxy" derived path for testing simulated server proxy pass
        # create redirect views to simulate the server proxy pass
        config = get_test_weaver_config(settings={"weaver.url": self.app_proxy_url})  # real access proxy path in config
        test_app = get_test_weaver_app(config=config)

        config = pyramid.testing.setUp(settings={})
        config.add_route(name="proxy", path=self.proxy_path, pattern=self.proxy_path + "/{remain:.*}")
        config.add_view(self.redirect_api_view, route_name="proxy")
        redirect_app = WebTestApp(config.make_wsgi_app())

        # setup environment that would define the new weaver location for the proxy pass
        resp = redirect_app.get(self.app_proxy_json, headers=self.json_headers)
        assert resp.status_code == 302, "Request should be at proxy level at this point."
        resp.test_app = test_app  # replace object to let follow redirect correctly
        resp = resp.follow()
        assert resp.status_code == 200
        assert resp.json["host"] == self.app_host
        assert resp.json["basePath"] == self.proxy_path, \
            "Proxy path specified by setting 'weaver.url' should be used in API definition to allow live requests."

        # validate that swagger UI still renders and has valid URL
        resp = redirect_app.get(self.app_proxy_ui)
        assert resp.status_code == 302, "Request should be at proxy level at this point."
        resp.test_app = test_app  # replace object to let follow redirect correctly
        resp = resp.follow()
        assert resp.status_code == 200
        assert f"<title>{sd.API_TITLE}</title>" in resp.text

    def test_swagger_api_request_base_path_original(self):
        """
        Validates that Swagger JSON properly uses the original host/path to test live requests on Swagger UI when the
        app's URI results direct route access.
        """
        # base app without proxy pass
        # ensure that setting that would define the weaver's location is not defined for local app
        config = get_test_weaver_config(settings={"weaver.url": None})
        testapp = get_test_weaver_app(config)

        resp = testapp.get(sd.openapi_json_service.path, headers=self.json_headers)
        assert resp.status_code == 200, "API definition should be accessed directly"
        assert resp.json["host"] in [self.app_host, f"{self.app_host}:80"]
        assert resp.json["basePath"] == sd.api_frontpage_service.path

        resp = testapp.get(sd.api_swagger_ui_service.path)
        assert resp.status_code == 200, "API definition should be accessed directly"
        assert f"<title>{sd.API_TITLE}</title>" in resp.text
