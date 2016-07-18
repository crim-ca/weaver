"""
based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_

pyramid testing:

* http://docs.pylonsproject.org/projects/pyramid/en/latest/quick_tutorial/routing.html
"""

import unittest
import mock
from nose import SkipTest
from nose.plugins.attrib import attr

from pyramid.httpexceptions import HTTPBadRequest
from pyramid import testing
from pyramid.testing import DummyRequest

from twitcher.owsproxy import owsproxy_view


class OWSProxyTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()
        from twitcher import owsproxy
        owsproxy.allowed_hosts = ()

    def test_badrequest_url(self):
        request = DummyRequest(scheme='http')
        response = owsproxy_view(request)
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badrequest_netloc(self):
        request = DummyRequest(scheme='http',
                               params={'url': 'http://'})
        response = owsproxy_view(request)
        self.assertTrue(isinstance(response, HTTPBadRequest))

   

   
   
