import pytest
import unittest
import mock

from twitcher.esgf import ESGFAccessManager


class ESGFTestCase(unittest.TestCase):
    def setUp(self):
        self.mgr = ESGFAccessManager(slcs_service_url="https://localhost:5000")
        self.mgr.retrieve_certificate = mock.MagicMock(return_value=True)

    def test_logon_with_token(self):
        assert self.mgr.logon(access_token="abcdef") is True
