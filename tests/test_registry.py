from nose.tools import ok_, assert_raises
import unittest
import mock

from twitcher.registry import ServiceRegistry


class ServiceRegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.service = dict(name="loving_flamingo", url="http://somewhere.over.the/ocean")

    def test_get_service(self):
        collection_mock = mock.Mock(spec=["find_one"])
        collection_mock.find_one.return_value = self.service
        
        registry = ServiceRegistry(collection=collection_mock)
        service = registry.get_service(service_name=self.service['name'])

        collection_mock.find_one.assert_called_with({"name": self.service['name']})
        ok_(isinstance(service, dict))
