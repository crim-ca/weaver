import pytest
import unittest

from pyramid import testing
from pyramid.testing import DummyRequest

from twitcher.owsrequest import OWSRequest
from twitcher.owsexceptions import OWSInvalidParameterValue


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

    def test_get_getcaps_request_downcase(self):
        params = dict(REQUEST="getcapabilities", SERVICE="WMS", VERSION="1.3.0")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getcapabilities'
        assert ows_req.service == 'wms'
        assert ows_req.version == '1.3.0'

    def test_get_invalid_request(self):
        params = dict(REQUEST="givememore", SERVICE="WMS", VERSION="1.3.0")
        request = DummyRequest(params=params)

        with pytest.raises(OWSInvalidParameterValue):
            OWSRequest(request)

    def test_get_getmetadata_request(self):
        params = dict(REQUEST="GetMetadata", SERVICE="WMS", VERSION="1.3.0")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getmetadata'
        assert ows_req.service == 'wms'
        assert ows_req.version == '1.3.0'


