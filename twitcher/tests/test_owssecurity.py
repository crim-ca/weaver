import pytest
import unittest
import mock

from pyramid.testing import DummyRequest

from twitcher.tokens import AccessToken, expires_at
from twitcher.owssecurity import OWSSecurity
from twitcher.owsexceptions import OWSAccessForbidden


class OWSSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.access_token = AccessToken(token="cdefg", expires_at=expires_at(hours=1))
        
        self.store_mock = mock.Mock(spec=["fetch_by_token"])
        self.store_mock.fetch_by_token.return_value = self.access_token

        self.registry_mock = mock.Mock(spec=["is_public"])
        self.registry_mock.is_public.return_value = False 
        
        self.security = OWSSecurity(tokenstore=self.store_mock, service_registry=self.registry_mock)

    def test_get_token_by_param(self):
        params = dict(request="Execute", service="WPS", access_token="abcdef")
        request = DummyRequest(params=params)
        token = self.security.get_token_param(request)
        assert token == "abcdef"


    def test_get_token_by_path(self):
        params = dict(request="Execute", service="WPS")
        request = DummyRequest(params=params, path="/ows/proxy/emu/12345")
        token = self.security.get_token_param(request)
        assert token == "12345"


    def test_get_token_by_header(self):
        params = dict(request="Execute", service="WPS")
        headers = {'Access-Token': '54321'}
        request = DummyRequest(params=params, headers=headers)
        token = self.security.get_token_param(request)
        assert token == "54321"


    def test_check_request(self):
        params = dict(request="Execute", service="WPS", version="1.0.0",  access_token="cdefg")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        self.security.check_request(request)

        
    def test_check_request_invalid(self):
        store_mock = mock.Mock(spec=["fetch_by_token"])
        store_mock.fetch_by_token.return_value = None
        security = OWSSecurity(tokenstore=store_mock, service_registry=self.registry_mock)
        
        params = dict(request="Execute", service="WPS", version="1.0.0", access_token="xyz")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        with pytest.raises(OWSAccessForbidden) as e_info:
            security.check_request(request)


    def test_check_request_allowed_caps(self):
        store_mock = mock.Mock(spec=["fetch_by_token"])
        store_mock.fetch_by_token.return_value = None
        security = OWSSecurity(tokenstore=store_mock, service_registry=self.registry_mock)
        
        params = dict(request="GetCapabilities", service="WPS", version="1.0.0")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        security.check_request(request)

    def test_check_request_allowed_describeprocess(self):
        store_mock = mock.Mock(spec=["fetch_by_token"])
        store_mock.fetch_by_token.return_value = None
        security = OWSSecurity(tokenstore=store_mock, service_registry=self.registry_mock)
        
        params = dict(request="DescribeProcess", service="WPS", version="1.0.0")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        security.check_request(request)

    def test_check_request_public_access(self):
        registry_mock = mock.Mock(spec=["is_public"])
        registry_mock.is_public.return_value = True
        security = OWSSecurity(tokenstore=self.store_mock, service_registry=registry_mock)

        params = dict(request="Execute", service="WPS", version="1.0.0")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        security.check_request(request)


    



