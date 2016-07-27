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
        params = dict(request="GetCapabilities", service="WMS")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getcapabilities'
        assert ows_req.service == 'wms'

        

        
