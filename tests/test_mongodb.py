"""
Based on unittests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

from weaver.store.mongodb import MongodbServiceStore
from weaver.datatype import Service
from pymongo.collection import Collection
import unittest
import mock


class MongodbServiceStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.service = dict(name="loving_flamingo", url="http://somewhere.over.the/ocean", type="wps",
                            public=False, auth='token')
        self.service_public = dict(name="open_pingu", url="http://somewhere.in.the/deep_ocean", type="wps",
                                   public=True, auth='token')
        self.service_special = dict(url="http://wonderload", name="A special Name", type="wps", auth="token")
        self.sane_name_config = {"assert_invalid": False}

    def test_fetch_by_name(self):
        collection_mock = mock.Mock(spec=Collection)
        collection_mock.find_one.return_value = self.service
        store = MongodbServiceStore(collection=collection_mock, sane_name_config=self.sane_name_config)
        service = store.fetch_by_name(name=self.service["name"])

        collection_mock.find_one.assert_called_with({"name": self.service["name"]})
        assert isinstance(service, dict)

    def test_save_service_default(self):
        collection_mock = mock.Mock(spec=Collection)
        collection_mock.count_documents.return_value = 0
        collection_mock.find_one.return_value = self.service
        store = MongodbServiceStore(collection=collection_mock, sane_name_config=self.sane_name_config)
        store.save_service(Service(self.service))

        collection_mock.insert_one.assert_called_with(self.service)

    def test_save_service_with_special_name(self):
        collection_mock = mock.Mock(spec=Collection)
        collection_mock.count_documents.return_value = 0
        collection_mock.find_one.return_value = self.service_special
        store = MongodbServiceStore(collection=collection_mock, sane_name_config=self.sane_name_config)
        store.save_service(Service(self.service_special))

        collection_mock.insert_one.assert_called_with({
            "url": "http://wonderload", "type": "wps", "name": "A_special_Name", "public": False, "auth": "token"})

    def test_save_service_public(self):
        collection_mock = mock.Mock(spec=Collection)
        collection_mock.count_documents.return_value = 0
        collection_mock.find_one.return_value = self.service_public
        store = MongodbServiceStore(collection=collection_mock, sane_name_config=self.sane_name_config)
        store.save_service(Service(self.service_public))

        collection_mock.insert_one.assert_called_with(self.service_public)
