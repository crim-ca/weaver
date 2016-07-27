import pytest
import unittest
import mock

from pyramid import testing
from pyramid.testing import DummyRequest

from twitcher.owsrequest import OWSRequest
from twitcher.owsexceptions import OWSInvalidParameterValue, OWSMissingParameterValue


class OWSRequestWpsTestCase(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

        
    def tearDown(self):
        testing.tearDown()


    def test_get_getcaps_request(self):
        params = dict(request="GetCapabilities", service="WPS")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getcapabilities'
        assert ows_req.service == 'wps'

        
    def test_get_describeprocess_request(self):
        params = dict(request="DescribeProcess", service="wps", version="1.0.0")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'describeprocess'
        assert ows_req.service == 'wps'
        assert ows_req.version == '1.0.0'


    def test_get_execute_request(self):
        params = dict(request="execute", service="Wps", version="1.0.0")
        request = DummyRequest(params=params)
        ows_req = OWSRequest(request)
        assert ows_req.request == 'execute'
        assert ows_req.service == 'wps'
        assert ows_req.version == '1.0.0'


    def test_get_false_request(self):
        params = dict(request="tellmemore", service="Wps", version="1.0.0")
        request = DummyRequest(params=params)
        with pytest.raises(OWSInvalidParameterValue) as e_info:
            ows_req = OWSRequest(request)

            
    def test_get_missing_request(self):
        params = dict(service="wps", version="1.0.0")
        request = DummyRequest(params=params)
        with pytest.raises(OWSMissingParameterValue) as e_info:
            ows_req = OWSRequest(request)

            
    def test_get_false_service(self):
        params = dict(request="execute", service="ATM", version="1.0.0")
        request = DummyRequest(params=params)
        with pytest.raises(OWSInvalidParameterValue) as e_info:
            ows_req = OWSRequest(request)


    def test_get_missing_service(self):
        params = dict(request="Execute", version="1.0.0")
        request = DummyRequest(params=params)
        with pytest.raises(OWSMissingParameterValue) as e_info:
            ows_req = OWSRequest(request)


    def test_post_getcaps_request(self):
        request = DummyRequest(post={})
        request.body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <GetCapabilities service="WPS" acceptVersions="1.0.0" language="en-CA"/>"""
        ows_req = OWSRequest(request)
        assert ows_req.request == 'getcapabilities'
        assert ows_req.service == 'wps'


    def test_post_false_request(self):
        request = DummyRequest(post={})
        request.body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <MyCaps service="WPS" acceptVersions="1.0.0" language="en-CA"/>"""
        with pytest.raises(OWSInvalidParameterValue) as e_info:
            ows_req = OWSRequest(request)


    def test_post_false_service(self):
        request = DummyRequest(post={})
        request.body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <GetCapabilities service="ATM" acceptVersions="1.0.0" language="en-CA"/>"""
        with pytest.raises(OWSInvalidParameterValue) as e_info:
            ows_req = OWSRequest(request)

        
    def test_post_describeprocess_request(self):
        request = DummyRequest(post={})
        request.body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <DescribeProcess service="WPS" version="1.0.0" language="en" xmlns:ows="http://www.opengis.net/ows/1.1">
          <ows:Identifier>intersection</ows:Identifier>
          <ows:Identifier>union</ows:Identifier>
        </DescribeProcess>""" 
        ows_req = OWSRequest(request)
        assert ows_req.request == 'describeprocess'
        assert ows_req.service == 'wps'
        assert ows_req.version == '1.0.0'
        

    def test_post_execute_request(self):
        request = DummyRequest(post={})
        request.body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <wps:Execute service="WPS" version="1.0.0" xmlns:wps="http://www.opengis.net/wps/1.0.0" xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/wps/1.0.0/../wpsExecute_request.xsd">
    <ows:Identifier>Buffer</ows:Identifier>
    <wps:DataInputs>
        <wps:Input>
            <ows:Identifier>InputPolygon</ows:Identifier>
            <ows:Title>Playground area</ows:Title>
            <wps:Reference xlink:href="http://foo.bar/some_WFS_request.xml"/>
        </wps:Input>
        <wps:Input>
            <ows:Identifier>BufferDistance</ows:Identifier>
            <ows:Title>Distance which people will walk to get to a playground.</ows:Title>
            <wps:Data>
                <wps:LiteralData>400</wps:LiteralData>
            </wps:Data>
        </wps:Input>
    </wps:DataInputs>
    <wps:ResponseForm>
        <wps:ResponseDocument storeExecuteResponse="true">
            <wps:Output asReference="true">
                <ows:Identifier>BufferedPolygon</ows:Identifier>
                <ows:Title>Area serviced by playground.</ows:Title>
                <ows:Abstract>Area within which most users of this playground will live.</ows:Abstract>
            </wps:Output>
        </wps:ResponseDocument>
    </wps:ResponseForm>
</wps:Execute>"""
        ows_req = OWSRequest(request)
        assert ows_req.request == 'execute'
        assert ows_req.service == 'wps'
        assert ows_req.version == '1.0.0'

        
