from nose.tools import ok_, assert_raises
import unittest

from datetime import timedelta

from twitcher.utils import now
from twitcher.tokens import AccessToken, UuidGenerator


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

        token = AccessToken(token='abcdef', creation_time=creation_time)
        ok_(token.not_before() == creation_time)
        ok_(token.not_after() > creation_time)
        ok_(token.is_valid() == True)

    def test_bad_access_token(self):
        with assert_raises(TypeError) as e:
            AccessToken()
        with assert_raises(TypeError) as e:
            AccessToken(token='12345')

    def test_invalid_access_token(self):
        creation_time = now() - timedelta(hours=2)

        token = AccessToken(token='abcdef', creation_time=creation_time)
        ok_(token.not_before() == creation_time)
        ok_(token.not_after() > creation_time)
        ok_(token.is_valid() == False)


    def test_access_token_with_user_environ(self):
        creation_time = now()
        token = AccessToken(token='12345', creation_time=creation_time,
                            user_environ={'oauth_token': 'bfghk'})
        ok_(token.user_environ == {'oauth_token': 'bfghk'})
