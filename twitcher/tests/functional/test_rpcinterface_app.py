"""
Testing the Twitcher XML-RPC interface.
"""
# noinspection PyPackageRequirements
import pytest
import unittest
import pyramid.testing

from twitcher._compat import PY2
from twitcher._compat import xmlrpclib

from twitcher.tests.utils import (
    setup_config_with_mongodb,
    setup_mongodb_tokenstore,
    setup_mongodb_servicestore,
    get_test_twitcher_app,
)


@pytest.mark.functional
class XMLRPCInterfaceAppTest(unittest.TestCase):

    def setUp(self):
        config = setup_config_with_mongodb()
        self.token = setup_mongodb_tokenstore(config)
        self.service_store = setup_mongodb_servicestore(config)
        self.app = get_test_twitcher_app(config=config, settings_override={'twitcher.rpcinterface': True})

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
    def test_generate_token_and_revoke_it(self):
        # gentoken
        resp = self._callFUT('generate_token', (1, {}))
        assert 'access_token' in resp
        assert 'expires_at' in resp
        # revoke
        resp = self._callFUT('revoke_token', (resp['access_token'],))
        assert resp is True
        # revoke all
        resp = self._callFUT('revoke_all_tokens', ())
        assert resp is True

    @pytest.mark.online
    def test_register_service_and_unregister_it(self):
        service = {'url': 'http://localhost/wps', 'name': 'test_emu',
                   'type': 'wps', 'public': False, 'auth': 'token'}
        # register
        resp = self._callFUT('register_service', (
            service['url'],
            service,
            False))
        assert resp == service

        # get by name
        resp = self._callFUT('get_service_by_name', (service['name'],))
        assert resp == service

        # get by url
        resp = self._callFUT('get_service_by_url', (service['url'],))
        assert resp == service

        # list
        resp = self._callFUT('list_services', ())
        assert resp == [service]

        # unregister
        resp = self._callFUT('unregister_service', (service['name'],))
        assert resp is True

        # clear
        resp = self._callFUT('clear_services', ())
        assert resp is True
