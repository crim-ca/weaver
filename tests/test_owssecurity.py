from nose.tools import ok_, assert_raises
import unittest
import mock

from pyramid.testing import DummyRequest

from twitcher.utils import now
from twitcher.tokens import AccessToken
from twitcher.owssecurity import OWSSecurity
from twitcher.owsexceptions import OWSAccessForbidden


class OWSSecurityTestCase(unittest.TestCase):
    def setUp(self):
        creation_time = now()
        self.access_token = AccessToken(token="cdefg", creation_time=creation_time)
        
        store_mock = mock.Mock(spec=["fetch_by_token"])
        store_mock.fetch_by_token.return_value = self.access_token
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


    def test_validate_token(self):
        access_token = self.security.validate_token(token="cdefg")
        ok_(access_token.token == "cdefg")


    def test_validate_token_invalid(self):
        store_mock = mock.Mock(spec=["fetch_by_token"])
        store_mock.fetch_by_token.return_value = None
        security = OWSSecurity(tokenstore=store_mock)

        with assert_raises(OWSAccessForbidden):
            security.validate_token(token="klmnop")




