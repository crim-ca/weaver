"""
Based on unitests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

from nose.tools import ok_, assert_raises
import unittest
import mock

from twitcher.tokens import AccessToken, UuidGenerator, MongodbAccessTokenStore, expires_at


class MongodbAccessTokenStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.access_token = AccessToken(token="abcdef", expires_at=expires_at(hours=1))

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
    def setUp(self):
        self.generator = UuidGenerator()
    
    def test_generate(self):
        token = self.generator.generate()
        ok_(len(token) == 32)

    def test_create_access_token_default(self):
        access_token = self.generator.create_access_token()
        ok_(len( access_token.token ) == 32)
        ok_(access_token.expires_in <= 3600)

    def test_create_access_non_default_hours(self):
        access_token = self.generator.create_access_token(valid_in_hours=2)
        ok_(len( access_token.token ) == 32)
        ok_(access_token.expires_in <= 3600 * 2)
        

class AccessTokenTestCase(unittest.TestCase):

    def test_access_token(self):
        access_token = AccessToken(token='abcdef', expires_at=expires_at(hours=1))
        ok_(access_token.expires_in <= 3600)
        ok_(access_token.is_expired() == False)

    def test_missing_token(self):
        with assert_raises(TypeError) as e:
            AccessToken()

    def test_invalid_access_token(self):
        access_token = AccessToken(token='abcdef', expires_at=expires_at(hours=-1))
        ok_(access_token.expires_in == 0)
        ok_(access_token.is_expired() == True)


    def test_access_token_with_user_environ(self):
        access_token = AccessToken(token='12345', expires_at=expires_at(hours=1),
                            user_environ={'data_token': 'bfghk'})
        ok_(access_token.user_environ == {'data_token': 'bfghk'})
