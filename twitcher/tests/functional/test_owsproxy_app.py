# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import webtest
import unittest
from pyramid import testing
from twitcher.tests.utils import setup_config_with_mongodb
from twitcher.adapter import servicestore_factory
from twitcher.datatype import Service


@pytest.mark.functional
class OWSProxyAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_config_with_mongodb()
        self.ows_path = '/ows'
        self.proxy_path = '/proxy'
        self.service_name = 'twitcher'
        self.setup_registry(config)
        config.include('twitcher.owsproxy')
        config.include('twitcher.tweens')
        self.app = webtest.TestApp(config.make_wsgi_app())

    def tearDown(self):
        testing.tearDown()

    def setup_registry(self, config):
        self.registry = servicestore_factory(config.registry)
        self.registry.clear_services()
        # TODO: testing against self ... not so good
        url = "https://localhost:5000/ows/wps"
        self.registry.save_service(Service(url=url, name=self.service_name))

    def make_url(self, params):
        return '{}{}{}?{}'.format(self.ows_path, self.proxy_path, self.service_name, params)

    @pytest.mark.skip(reason="no way of currently testing this")
    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get(self.make_url('service=wps&request=getcapabilities'))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.skip(reason="no way of currently testing this")
    @pytest.mark.online
    def test_describeprocess(self):
        resp = self.app.get(self.make_url('service=wps&request=describeprocess&version=1.0.0&identifier=dummyprocess'))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.skip(reason="no way of currently testing this")
    @pytest.mark.online
    def test_execute_not_allowed(self):
        resp = self.app.get(self.make_url('service=wps&request=execute&version=1.0.0&identifier=dummyprocess'))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')
