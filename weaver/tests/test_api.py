"""
Testing the weaver API.
"""
import unittest
from weaver.api import Registry
from weaver.store.memory import MemoryServiceStore


class RegistryTest(unittest.TestCase):

    def setUp(self):
        self.reg = Registry(servicestore=MemoryServiceStore())

    def test_register_service_and_unregister_it(self):
        service = {'url': 'http://localhost/wps', 'name': 'test_emu',
                   'type': 'wps', 'public': False, 'auth': 'token'}
        # register
        resp = self.reg.register_service(
            service['url'],
            service,
            False)
        assert resp == service

        # get by name
        resp = self.reg.get_service_by_name(service['name'])
        assert resp == service

        # get by url
        resp = self.reg.get_service_by_url(service['url'])
        assert resp == service

        # list
        resp = self.reg.list_services()
        assert resp == [service]

        # unregister
        resp = self.reg.unregister_service(service['name'])
        assert resp is True

        # clear
        resp = self.reg.clear_services()
        assert resp is True
