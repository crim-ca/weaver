"""
Testing the Twithcer XML-RPC interface.
"""
import pytest
import unittest
import webtest
import pyramid.testing

from twitcher._compat import PY2
from twitcher._compat import xmlrpclib

from twitcher.tests.functional.common import setup_with_mongodb, setup_mongodb_tokenstore


class XMLRPCInterfaceAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_with_mongodb()
        self.token = setup_mongodb_tokenstore(config)
        config.include('twitcher.rpcinterface')
        self.app = webtest.TestApp(config.make_wsgi_app())

    def tearDown(self):
        pyramid.testing.tearDown()

    def _callFUT(self, method, params):
        if PY2:
            xml = xmlrpclib.dumps(params, methodname=method)
        else:
            xml = xmlrpclib.dumps(params, methodname=method).encode('utf-8')
        resp = self.app.post('/RPC2', content_type='text/xml', params=xml)
        assert resp.status_int == 200
        assert resp.content_type == 'text/xml'
        return xmlrpclib.loads(resp.body)[0][0]

    @pytest.mark.online
    def test_generate_token(self):
        resp = self._callFUT('generate_token', (1, {}))
        assert 'access_token' in resp
        assert 'expires_at' in resp
