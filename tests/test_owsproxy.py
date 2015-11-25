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

from twitcher.owsproxy import OWSProxy


class OWSProxyTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()
        from twitcher import owsproxy
        owsproxy.allowed_hosts = ()

    def test_badrequest_url(self):
        request = DummyRequest(scheme='http')
        inst = OWSProxy(request)
        response = inst.owsproxy()
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badrequest_netloc(self):
        request = DummyRequest(scheme='http',
                               params={'url': 'http://'})
        inst = OWSProxy(request)
        response = inst.owsproxy()
        self.assertTrue(isinstance(response, HTTPBadRequest))

   

   
   
