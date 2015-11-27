"""
Based on unitests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

from nose.tools import ok_, assert_raises
import unittest
import mock

from datetime import timedelta

from twitcher.utils import now
from twitcher.tokens import AccessToken, UuidGenerator, MongodbAccessTokenStore


class MongodbAccessTokenStoreTestCase(unittest.TestCase):
    def setUp(self):
        creation_time = now()
        self.access_token = AccessToken(token="abcdef", creation_time=creation_time)

    def test_fetch_by_token(self):
        collection_mock = mock.Mock(spec=["find_one"])
        collection_mock.find_one.return_value = self.access_token
        
        store = MongodbAccessTokenStore(collection=collection_mock)
        access_token = store.fetch_by_token(token=self.access_token.token)

        collection_mock.find_one.assert_called_with({"token": self.access_token.token})
        ok_(isinstance(access_token, AccessToken))

    
    def test_save_token(self):
        collection_mock = mock.Mock(spec=["insert_one"])
        
        store = MongodbAccessTokenStore(collection=collection_mock)
        store.save_token(self.access_token)

        collection_mock.insert_one.assert_called_with(self.access_token)

        
class UuidGeneratorTestCase(unittest.TestCase):
    def test_generate(self):
        generator = UuidGenerator()
        token = generator.generate()
        ok_(len(token) == 32)

    def test_create_access_token_default(self):
        generator = UuidGenerator()
        access_token = generator.create_access_token()
        ok_(len( access_token.token ) == 32)
        ok_(access_token.valid_in_hours == 1)

    def test_create_access_non_default_hours(self):
        generator = UuidGenerator()
        access_token = generator.create_access_token(valid_in_hours=2)
        ok_(len( access_token.token ) == 32)
        ok_(access_token.valid_in_hours == 2)
        

class AccessTokenTestCase(unittest.TestCase):

    def test_access_token(self):
        creation_time = now()

        access_token = AccessToken(token='abcdef', creation_time=creation_time)
        ok_(access_token.not_before() == creation_time)
        ok_(access_token.not_after() > creation_time)
        ok_(access_token.is_valid() == True)

    def test_bad_access_token(self):
        with assert_raises(TypeError) as e:
            AccessToken()
        with assert_raises(TypeError) as e:
            AccessToken(token='12345')

    def test_invalid_access_token(self):
        creation_time = now() - timedelta(hours=2)

        access_token = AccessToken(token='abcdef', creation_time=creation_time)
        ok_(access_token.not_before() == creation_time)
        ok_(access_token.not_after() > creation_time)
        ok_(access_token.is_valid() == False)


    def test_access_token_with_user_environ(self):
        creation_time = now()
        access_token = AccessToken(token='12345', creation_time=creation_time,
                            user_environ={'oauth_token': 'bfghk'})
        ok_(access_token.user_environ == {'oauth_token': 'bfghk'})
