"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
import pytest
import unittest
import webtest
import pyramid.testing
from twitcher.tests.functional.common import setup_with_mongodb, setup_mongodb_tokenstore


class WpsAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_with_mongodb()
        self.token = setup_mongodb_tokenstore(config)
        config.include('twitcher.wps')
        config.include('twitcher.tweens')
        self.app = webtest.TestApp(config.make_wsgi_app())

    def tearDown(self):
        pyramid.testing.tearDown()

    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get('/ows/wps?service=wps&request=getcapabilities')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_getcaps_with_invalid_token(self):
        resp = self.app.get('/ows/wps?service=wps&request=getcapabilities&access_token=invalid')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_describeprocess(self):
        resp = self.app.get('/ows/wps?service=wps&request=describeprocess&version=1.0.0&identifier=hello')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_describeprocess_with_invalid_token(self):
        resp = self.app.get(
            '/ows/wps?service=wps&request=describeprocess&version=1.0.0&identifier=hello&access_token=invalid')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_execute_not_allowed(self):
        resp = self.app.get('/ows/wps?service=wps&request=execute&version=1.0.0&identifier=hello&datainputs=name=tux')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print resp.body
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')

    @pytest.mark.online
    def test_execute_allowed(self):
        url = "/ows/wps?service=wps&request=execute&version=1.0.0&identifier=hello&datainputs=name=tux"
        url += "&access_token={}".format(self.token)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print resp.body
        resp.mustcontain(
            '<wps:ProcessSucceeded>PyWPS Process Say Hello finished</wps:ProcessSucceeded>')
