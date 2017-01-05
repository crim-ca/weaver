"""
Based on unitests in https://github.com/wndhydrnt/python-oauth2/tree/master/oauth2/test
"""

import pytest
import unittest
import mock

from twitcher.tokengenerator import UuidTokenGenerator


class UuidTokenGeneratorTestCase(unittest.TestCase):
    def setUp(self):
        self.generator = UuidTokenGenerator()

    def test_generate(self):
        token = self.generator.generate()
        assert len(token) == 32

    def test_create_access_token_default(self):
        access_token = self.generator.create_access_token()
        assert len(access_token.token) == 32
        assert access_token.expires_in <= 3600

    def test_create_access_non_default_hours(self):
        access_token = self.generator.create_access_token(valid_in_hours=2)
        assert len(access_token.token) == 32
        assert access_token.expires_in <= 3600 * 2
