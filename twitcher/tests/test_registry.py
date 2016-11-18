import pytest
import unittest
import mock

from twitcher.registry import ServiceRegistry
from twitcher.registry import parse_service_name


class ServiceRegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.service = dict(name="loving_flamingo", url="http://somewhere.over.the/ocean", type="wps",
                            public=False, c4i=False)
        self.service_public = dict(name="open_pingu", url="http://somewhere.in.the/deep_ocean", type="wps",
                                   public=True, c4i=False)

    def test_get_service_by_name(self):
        collection_mock = mock.Mock(spec=["find_one"])
        collection_mock.find_one.return_value = self.service

        registry = ServiceRegistry(collection=collection_mock)
        service = registry.get_service_by_name(name=self.service['name'])

        collection_mock.find_one.assert_called_with({"name": self.service['name']})
        assert isinstance(service, dict)

    def test_register_service_default(self):
        collection_mock = mock.Mock(spec=["insert_one", "find_one", "count"])
        collection_mock.count.return_value = 0

        store = ServiceRegistry(collection=collection_mock)
        store.register_service(url=self.service['url'], name=self.service['name'])

        collection_mock.insert_one.assert_called_with(self.service)

    def test_register_service_with_special_name(self):
        collection_mock = mock.Mock(spec=["insert_one", "find_one", "count"])
        collection_mock.count.return_value = 0

        store = ServiceRegistry(collection=collection_mock)
        store.register_service(url="http://wonderload", name="A special Name")

        collection_mock.insert_one.assert_called_with({
            'url': 'http://wonderload', 'type': 'wps', 'name': 'a_special_name', 'public': False, 'c4i': False})

    def test_register_service_public(self):
        collection_mock = mock.Mock(spec=["insert_one", "find_one", "count"])
        collection_mock.count.return_value = 0

        store = ServiceRegistry(collection=collection_mock)
        store.register_service(url=self.service_public['url'], name=self.service_public['name'], public=True)

        collection_mock.insert_one.assert_called_with(self.service_public)

    def test_parse_service_name(self):
        assert 'emu' == parse_service_name("/ows/proxy/emu")
        assert 'emu' == parse_service_name("/ows/proxy/emu/foo/bar")
        assert 'emu' == parse_service_name("/ows/proxy/emu/")
        with pytest.raises(ValueError) as e_info:
            assert 'emu' == parse_service_name("/ows/proxy/")
        with pytest.raises(ValueError) as e_info:
            assert 'emu' == parse_service_name("/ows/nowhere/emu")
