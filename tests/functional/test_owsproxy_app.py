import unittest
from nose.plugins.attrib import attr
from webtest import TestApp
from pyramid import testing

from twitcher.registry import service_registry_factory

class OWSProxyAppTest(unittest.TestCase):

    def setUp(self):
        settings = {'mongodb.host':'localhost', 'mongodb.port':'27027', 'mongodb.db_name': 'twitcher_test'}
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
        registry.register_service(url="http://not.on.earth/wps", name="earth")

    @attr('online')
    def test_execute_not_allowed(self):
        resp = self.app.get('/ows/proxy/earth?service=wps&request=execute&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print resp.body
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')

