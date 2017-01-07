"""
Based on unitests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

import pytest
import unittest
import mock

from twitcher.datatype import AccessToken
from twitcher.datatype import Service
from twitcher.utils import expires_at


class AccessTokenTestCase(unittest.TestCase):

    def test_access_token(self):
        access_token = AccessToken(token='abcdef', expires_at=expires_at(hours=1))
        assert access_token.token == 'abcdef'
        assert access_token.expires_in > 0
        assert access_token.expires_in <= 3600
        assert access_token.is_expired() is False
        assert access_token.params['access_token'] == 'abcdef'
        assert 'expires_at' in access_token.params

    def test_missing_token(self):
        with pytest.raises(TypeError) as e_info:
            AccessToken()

    def test_invalid_access_token(self):
        access_token = AccessToken(token='abcdef', expires_at=expires_at(hours=-1))
        assert access_token.expires_in == 0
        assert access_token.is_expired() is True

    def test_access_token_with_data(self):
        access_token = AccessToken(token='12345', expires_at=expires_at(hours=1),
                                   data={'esgf_token': 'bfghk'})
        assert access_token.data == {'esgf_token': 'bfghk'}


class ServiceTestCase(unittest.TestCase):
    def test_service_with_url_only(self):
        service = Service(url='http://nowhere/wps')
        assert service.url == 'http://nowhere/wps'
        assert service.name == 'unknown'

    def test_missing_url(self):
        with pytest.raises(TypeError) as e_info:
            Service()

    def test_service_with_name(self):
        service = Service(url='http://nowhere/wps', name="test_wps")
        assert service.url == 'http://nowhere/wps'
        assert service.name == 'test_wps'

    def test_service_params(self):
        service = Service(url='http://nowhere/wps', name="test_wps")
        assert service.params == {'c4i': False,
                                  'name': 'test_wps',
                                  'public': False,
                                  'type': 'WPS',
                                  'url': 'http://nowhere/wps'}
