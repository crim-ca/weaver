import unittest
from nose.plugins.attrib import attr
from webtest import TestApp
from pyramid import testing

from twitcher.registry import service_registry_factory

class OWSProxyAppTest(unittest.TestCase):

    def setUp(self):
        settings = {'mongodb.host':'127.0.0.1', 'mongodb.port':'27027', 'mongodb.db_name': 'twitcher_test'}
        config = testing.setUp(settings=settings)
        config.include('twitcher.owsproxy')
        config.include('twitcher.tweens')
        self._setup_db(config)
        self.app= TestApp(config.make_wsgi_app())
        
    def tearDown(self):
        testing.tearDown()

    def _setup_db(self, config):
        registry = service_registry_factory(config.registry)
        registry.clear_services()
        # TODO: testing against ourselfs ... not so good
        registry.register_service(url="https://localhost:38083/ows/wps", name="twitcher")

    @attr('online')
    def test_getcaps(self):
        resp = self.app.get('/ows/proxy/twitcher?service=wps&request=getcapabilities')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @attr('online')
    def test_describeprocess(self):
        resp = self.app.get('/ows/proxy/twitcher?service=wps&request=describeprocess&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @attr('online')
    def test_execute_not_allowed(self):
        resp = self.app.get('/ows/proxy/twitcher?service=wps&request=execute&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print resp.body
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')

