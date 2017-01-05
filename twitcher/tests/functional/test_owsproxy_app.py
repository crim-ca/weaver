import pytest
import unittest
import webtest
from pyramid import testing
from .common import setup_with_mongodb

from twitcher.store import servicestore_factory


class OWSProxyAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_with_mongodb()
        self._setup_registry(config)
        config.include('twitcher.owsproxy')
        config.include('twitcher.tweens')
        self.app = webtest.TestApp(config.make_wsgi_app())

    def tearDown(self):
        testing.tearDown()

    def _setup_registry(self, config):
        registry = servicestore_factory(config.registry)
        registry.clear_services()
        # TODO: testing against ourselfs ... not so good
        url = "https://localhost:5000/ows/wps"
        registry.register_service(url=url, name="twitcher")

    @pytest.mark.skip(reason="no way of currently testing this")
    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get('/ows/proxy/twitcher?service=wps&request=getcapabilities')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.skip(reason="no way of currently testing this")
    @pytest.mark.online
    def test_describeprocess(self):
        resp = self.app.get(
            '/ows/proxy/twitcher?service=wps&request=describeprocess&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.skip(reason="no way of currently testing this")
    @pytest.mark.online
    def test_execute_not_allowed(self):
        resp = self.app.get('/ows/proxy/twitcher?service=wps&request=execute&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print resp.body
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')
