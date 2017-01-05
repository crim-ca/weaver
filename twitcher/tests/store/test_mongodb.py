"""
Based on unitests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

import pytest
import unittest
import mock

from twitcher.datatype import AccessToken
from twitcher.utils import expires_at
from twitcher.store.mongodb import MongodbTokenStore


class MongodbTokenStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.access_token = AccessToken(token="abcdef", expires_at=expires_at(hours=1))

    def test_fetch_by_token(self):
        collection_mock = mock.Mock(spec=["find_one"])
        collection_mock.find_one.return_value = self.access_token

        store = MongodbTokenStore(collection=collection_mock)
        access_token = store.fetch_by_token(token=self.access_token.token)

        collection_mock.find_one.assert_called_with({"token": self.access_token.token})
        assert isinstance(access_token, AccessToken)

    def test_save_token(self):
        collection_mock = mock.Mock(spec=["insert_one"])

        store = MongodbTokenStore(collection=collection_mock)
        store.save_token(self.access_token)

        collection_mock.insert_one.assert_called_with(self.access_token)
