"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import webtest
import unittest
import pyramid.testing
from twitcher.tests.functional.common import setup_with_mongodb, setup_mongodb_tokenstore
from twitcher.tests.utils import get_default_config_ini_path


class WpsAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_with_mongodb()
        self.token = setup_mongodb_tokenstore(config)
        self.protected_path = '/ows'
        self.wps_path = '/wps'
        config.registry.settings['twitcher.wps'] = True
        config.registry.settings['twitcher.wps_path'] = '{}{}'.format(self.protected_path, self.wps_path)
        config.include('twitcher.wps')
        config.include('twitcher.tweens')
        config.include('pyramid_celery')
        config.configure_celery(get_default_config_ini_path())
        self.app = webtest.TestApp(config.make_wsgi_app())

    def tearDown(self):
        pyramid.testing.tearDown()

    def make_url(self, params, token=None):
        return '{}{}?{}&access_token={}'.format(self.protected_path, self.wps_path, params, token or self.token)

    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_getcaps_with_invalid_token(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities", token='invalid'))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_describeprocess(self):
        resp = self.app.get(self.make_url("service=wps&request=describeprocess&version=1.0.0&identifier=hello"))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_describeprocess_with_invalid_token(self):
        url = self.make_url("service=wps&request=describeprocess&version=1.0.0&identifier=hello", token='invalid')
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_execute_not_allowed(self):
        url = self.make_url("service=wps&request=execute&version=1.0.0&identifier=hello&datainputs=name=tux")
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print(resp.body)
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')

    @pytest.mark.online
    def test_execute_allowed(self):
        url = self.make_url("service=wps&request=execute&version=1.0.0&identifier=hello&datainputs=name=tux")
        url += "&access_token={}".format(self.token)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print(resp.body)
        resp.mustcontain('<wps:ProcessSucceeded>PyWPS Process Say Hello finished</wps:ProcessSucceeded>')
