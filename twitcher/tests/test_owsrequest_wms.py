import pytest
import unittest
import mock

from pyramid import testing
from pyramid.testing import DummyRequest

from twitcher.owsrequest import OWSRequest
from twitcher.owsexceptions import OWSInvalidParameterValue, OWSMissingParameterValue


class OWSRequestWmsTestCase(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

        
    def tearDown(self):
        testing.tearDown()


    def test_get_getcaps_request(self):
        params = dict(request="GetCapabilities", service="WMS", version="1.1.1")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getcapabilities'
        assert ows_req.service == 'wms'
        assert ows_req.version == '1.1.1'
        assert ows_req.public_access
        assert ows_req.service_allowed

    def test_get_getcaps_request_upcase(self):
        params = dict(REQUEST="GetCapabilities", SERVICE="WMS", VERSION="1.3.0")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getcapabilities'
        assert ows_req.service == 'wms'
        assert ows_req.version == '1.3.0'


        

        
