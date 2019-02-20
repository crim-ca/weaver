import unittest
from weaver.datatype import Service
from weaver.store.memory import MemoryServiceStore


class MemoryServiceStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.service_data = {'url': 'http://localhost:8094/wps',
                             'name': 'emu',
                             'public': False,
                             'auth': 'token',
                             'type': 'WPS',
                             }
        self.test_store = MemoryServiceStore()

    def test_save_service_and_fetch_service(self):
        service = Service(**self.service_data)

        assert self.test_store.save_service(service)
        assert self.test_store.fetch_by_url(service.url) == service
        assert self.test_store.fetch_by_name(service.name) == service
