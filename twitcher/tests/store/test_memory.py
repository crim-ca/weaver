import unittest

from twitcher.tokens import AccessToken

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
