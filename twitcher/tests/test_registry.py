import unittest
import mock

from twitcher.registry import ServiceRegistry


class ServiceRegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.service = dict(name="loving_flamingo", url="http://somewhere.over.the/ocean", type="wps", public=False)
        self.service_public = dict(name="open_pingu", url="http://somewhere.in.the/deep_ocean", type="wps", public=True)

    def test_get_service(self):
        collection_mock = mock.Mock(spec=["find_one"])
        collection_mock.find_one.return_value = self.service
        
        registry = ServiceRegistry(collection=collection_mock)
        service = registry.get_service(name=self.service['name'])

        collection_mock.find_one.assert_called_with({"name": self.service['name']})
        assert isinstance(service, dict)

    def test_register_service_default(self):
        collection_mock = mock.Mock(spec=["insert_one", "find_one"])
        collection_mock.find_one.return_value = None
        
        store = ServiceRegistry(collection=collection_mock)
        store.register_service(url=self.service['url'], name=self.service['name'])

        collection_mock.insert_one.assert_called_with(self.service)

    def test_register_service_with_special_name(self):
        collection_mock = mock.Mock(spec=["insert_one", "find_one"])
        collection_mock.find_one.return_value = None
        
        store = ServiceRegistry(collection=collection_mock)
        store.register_service(url="http://wonderload", name="A special Name")

        collection_mock.insert_one.assert_called_with({
            'url': 'http://wonderload', 'type': 'wps', 'name': 'a_special_name', 'public': False})

    def test_register_service_public(self):
        collection_mock = mock.Mock(spec=["insert_one", "find_one"])
        collection_mock.find_one.return_value = None
        
        store = ServiceRegistry(collection=collection_mock)
        store.register_service(url=self.service_public['url'], name=self.service_public['name'], public=True)

        collection_mock.insert_one.assert_called_with(self.service_public)
