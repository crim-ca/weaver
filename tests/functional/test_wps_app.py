"""
Based on tests from:

* https://github.com/jachym/pywps-4/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""

import unittest
from nose.plugins.attrib import attr
from webtest import TestApp
import pyramid.testing
from tests.functional.common import setup_with_db

class WpsAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_with_db()
        config.include('twitcher.wps')
        config.include('twitcher.tweens')
        self.app= TestApp(config.make_wsgi_app())

    def tearDown(self):
        pyramid.testing.tearDown()

    @attr('online')
    def test_getcaps(self):
        resp = self.app.get('/ows/wps?service=wps&request=getcapabilities')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @attr('online')
    def test_describeprocess(self):
        resp = self.app.get('/ows/wps?service=wps&request=describeprocess&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @attr('online')
    def test_execute_not_allowed(self):
        resp = self.app.get('/ows/wps?service=wps&request=execute&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        print resp.body
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')

