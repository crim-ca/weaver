import unittest
import colander
from twitcher.wps_restapi.swagger_definitions import (
    api_frontpage_uri,
    api_versions_uri,
    FrontpageSchema,
    VersionsSchema,
)
from twitcher.tests.utils import get_test_twitcher_app
from twitcher.database.memory import MemoryDatabase
from twitcher.adapter import TWITCHER_ADAPTER_DEFAULT


class GenericApiRoutesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        settings = {'twitcher.adapter': TWITCHER_ADAPTER_DEFAULT, 'twitcher.db_factory': MemoryDatabase.type}
        cls.testapp = get_test_twitcher_app(settings_override=settings)
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}

    def test_frontpage_format(self):
        resp = self.testapp.get(api_frontpage_uri, expect_errors=True, headers=self.json_headers)
        assert 200 == resp.status_code
        try:
            FrontpageSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))

    def test_version_format(self):
        resp = self.testapp.get(api_versions_uri, expect_errors=True, headers=self.json_headers)
        assert 200 == resp.status_code
        try:
            VersionsSchema().deserialize(resp.json)
        except colander.Invalid as ex:
            self.fail("expected valid response format as defined in schema [{!s}]".format(ex))
