from nose.tools import ok_, assert_raises
import unittest
import mock

from pyramid.testing import DummyRequest

from twitcher.owssecurity import OWSSecurity
from twitcher.owsexceptions import OWSAccessForbidden


class OWSSecurityTestCase(unittest.TestCase):
    def setUp(self):
        store_mock = mock.Mock(spec=["fetch_by_token"])
        self.security = OWSSecurity(tokenstore=store_mock)

    def test_get_token_by_param(self):
        params = dict(request="Execute", service="WPS", access_token="abcdef")
        request = DummyRequest(params=params)
        token = self.security.get_token(request)
        ok_(token == "abcdef")


    def test_get_token_by_path(self):
        params = dict(request="Execute", service="WPS")
        request = DummyRequest(params=params, path="/ows/emu/12345")
        token = self.security.get_token(request)
        ok_(token == "12345")


    def test_get_token_by_header(self):
        params = dict(request="Execute", service="WPS")
        headers = {'Access-Token': '54321'}
        request = DummyRequest(params=params, headers=headers)
        token = self.security.get_token(request)
        ok_(token == "54321")


    def test_get_token_forbidden(self):
        params = dict(request="Execute", service="WPS")
        request = DummyRequest(params=params)
        with assert_raises(OWSAccessForbidden):
            self.security.get_token(request)




