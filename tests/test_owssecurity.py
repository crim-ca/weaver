from nose.tools import ok_, assert_raises
import unittest
import mock

from pyramid.testing import DummyRequest

from twitcher.owssecurity import OWSSecurity


class OWSSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.security = OWSSecurity()

    def test_get_token_by_param(self):
        params = dict(request="Execute", service="WPS", access_token="abcdef")
        request = DummyRequest(params=params)
        self.security.get_token(request)

