import pytest
import unittest
import mock

from pyramid.testing import DummyRequest

from twitcher.datatype import AccessToken
from twitcher.datatype import Service
from twitcher.utils import expires_at
from twitcher.owssecurity import OWSSecurity
from twitcher.owsexceptions import OWSAccessForbidden
from twitcher.store.memory import MemoryTokenStore
from twitcher.store.memory import MemoryServiceStore


class OWSSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.access_token = AccessToken(token="cdefg", expires_at=expires_at(hours=1))

        self.tokenstore = MemoryTokenStore()
        self.tokenstore.save_token(self.access_token)
        self.empty_tokenstore = MemoryTokenStore()

        self.service = Service(url='http://nowhere/wps', name='test_wps', public=False)
        self.servicestore = MemoryServiceStore()
        self.servicestore.save_service(self.service)

        self.security = OWSSecurity(tokenstore=self.tokenstore, servicestore=self.servicestore)

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
        params = dict(request="Execute", service="WPS", version="1.0.0", token="cdefg")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        self.security.check_request(request)

    def test_check_request_invalid(self):
        security = OWSSecurity(tokenstore=self.empty_tokenstore, servicestore=self.servicestore)

        params = dict(request="Execute", service="WPS", version="1.0.0", token="xyz")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        with pytest.raises(OWSAccessForbidden) as e_info:
            security.check_request(request)

    def test_check_request_allowed_caps(self):
        security = OWSSecurity(tokenstore=self.empty_tokenstore, servicestore=self.servicestore)

        params = dict(request="GetCapabilities", service="WPS", version="1.0.0")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        security.check_request(request)

    def test_check_request_allowed_describeprocess(self):
        security = OWSSecurity(tokenstore=self.empty_tokenstore, servicestore=self.servicestore)

        params = dict(request="DescribeProcess", service="WPS", version="1.0.0")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        security.check_request(request)

    def test_check_request_public_access(self):
        servicestore = MemoryServiceStore()
        servicestore.save_service(Service(
            url='http://nowhere/wps', name='test_wps', public=True))
        security = OWSSecurity(tokenstore=self.tokenstore, servicestore=servicestore)

        params = dict(request="Execute", service="WPS", version="1.0.0", token="cdefg")
        request = DummyRequest(params=params, path='/ows/proxy/emu')
        security.check_request(request)
