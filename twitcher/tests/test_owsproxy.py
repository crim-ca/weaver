"""
based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_

pyramid testing:

* http://docs.pylonsproject.org/projects/pyramid/en/latest/quick_tutorial/routing.html
"""

import unittest

from pyramid import testing
from pyramid.testing import DummyRequest

from twitcher.owsexceptions import OWSAccessFailed
from twitcher import owsproxy
from twitcher.owsproxy import owsproxy as owsproxy_view


class OWSProxyTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()
        owsproxy.allowed_hosts = ()

    def test_badrequest_url(self):
        request = DummyRequest(scheme='http')
        response = owsproxy_view(request)
        assert isinstance(response, OWSAccessFailed) is True

    def test_badrequest_netloc(self):
        request = DummyRequest(scheme='http',
                               params={'url': 'http://'})
        response = owsproxy_view(request)
        assert isinstance(response, OWSAccessFailed) is True
