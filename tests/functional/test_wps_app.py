"""
Based on test from:

* https://github.com/jachym/pywps-4/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""


import unittest
from webtest import TestApp
import pyramid.testing

class WpsAppTest(unittest.TestCase):

    def setUp(self):
        config = pyramid.testing.setUp()
        config.include('twitcher.wps')
        #config.include('twitcher.tweens')
        self.app= TestApp(config.make_wsgi_app())

    def tearDown(self):
        pyramid.testing.tearDown()

    def test_getcaps(self):
        resp = self.app.get('/ows/wps?service=wps&request=getcapabilities')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    def test_describeprocess(self):
        resp = self.app.get('/ows/wps?service=wps&request=describeprocess&version=1.0.0&identifier=dummyprocess')
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

