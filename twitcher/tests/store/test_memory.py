import unittest

from twitcher.datatype import AccessToken
from twitcher.store.memory import MemoryTokenStore


class MemoryTokenStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.access_token_data = {"token": "xyz",
                                  "data": {"name": "test"},
                                  }
        self.test_store = MemoryTokenStore()

    def test_save_token_and_fetch_by_token(self):
        access_token = AccessToken(**self.access_token_data)

        assert self.test_store.save_token(access_token)
        assert self.test_store.fetch_by_token(access_token.token) == access_token


from twitcher.datatype import Service
from twitcher.store.memory import MemoryServiceStore


class MemoryServiceStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.service_data = {'url': 'http://localhost:8094/wps',
                             'name': 'emu',
                             'c4i': False,
                             'public': False,
                             'type': 'WPS',
                             }
        self.test_store = MemoryServiceStore()

    def test_save_service_and_fetch_service(self):
        service = Service(**self.service_data)

        assert self.test_store.save_service(service)
        assert self.test_store.fetch_by_url(service.url) == service
        assert self.test_store.fetch_by_name(service.name) == service
