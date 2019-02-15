"""
Based on unittests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

# noinspection PyPackageRequirements
import pytest
import unittest
from weaver.datatype import Service


# noinspection PyMethodMayBeStatic
class ServiceTestCase(unittest.TestCase):
    def test_service_with_url_only(self):
        with pytest.raises(TypeError):
            Service(url='http://nowhere/wps')

    def test_missing_url(self):
        with pytest.raises(TypeError):
            Service()

    def test_service_with_name(self):
        service = Service(url='http://nowhere/wps', name="test_wps")
        assert service.url == 'http://nowhere/wps'
        assert service.name == 'test_wps'

    def test_service_params(self):
        service = Service(url='http://nowhere/wps', name="test_wps")
        assert service.params == {'name': 'test_wps',
                                  'public': False,
                                  'auth': 'token',
                                  'type': 'WPS',
                                  'url': 'http://nowhere/wps'}
