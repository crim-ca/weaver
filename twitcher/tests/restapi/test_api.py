# noinspection PyPackageRequirements
import pytest
import unittest
import colander
from twitcher.wps_restapi.swagger_definitions import (
    api_frontpage_uri,
    api_versions_uri,
    FrontpageSchema,
    VersionsSchema,
)
from twitcher.tests.utils import get_test_twitcher_app


class GenericApiRoutesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}
        cls.testapp = get_test_twitcher_app()

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
