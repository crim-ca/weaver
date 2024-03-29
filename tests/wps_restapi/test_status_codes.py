import unittest
import uuid

import pytest

from tests.utils import get_test_weaver_app, setup_config_with_mongodb
from weaver.formats import ContentType
from weaver.wps_restapi import swagger_definitions as sd

TEST_PUBLIC_ROUTES = [
    sd.api_frontpage_service.path,
    sd.api_swagger_ui_service.path,
    sd.openapi_json_service.path,
    sd.api_versions_service.path,
]
TEST_FORBIDDEN_ROUTES = [
    sd.jobs_service.path,  # should always be visible
    sd.provider_jobs_service.path,  # could be 401
]
TEST_NOTFOUND_ROUTES = [
    sd.job_service.path.format(job_id=str(uuid.uuid4())),  # if not UUID, 400 instead
    sd.provider_service.path.format(provider_id="not-found"),
]


class StatusCodeTestCase(unittest.TestCase):
    """
    Verify that the Weaver Web Application returns correct status codes for common cases.

    Common cases are:
    - not found
    - forbidden (possibly with a difference between unauthorized and unauthenticated
    - resource added
    - ok
    """
    # create a weaver app using configuration
    # invoke request on app:
    #   not found provider, job and process
    #   private resource
    #   login, then private resource
    #   add job
    #   fetch job and find it
    #   search features
    # receive response and assert that status codes match

    headers = {"Accept": ContentType.APP_JSON}

    def setUp(self):
        config = setup_config_with_mongodb()
        self.testapp = get_test_weaver_app(config)

    def test_200(self):
        for uri in TEST_PUBLIC_ROUTES:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(200, resp.status_code, f"route {uri} did not return 200")

    @pytest.mark.xfail(reason="Not working if not behind proxy. Protected implementation to be done.")
    @unittest.expectedFailure
    def test_401(self):
        for uri in TEST_FORBIDDEN_ROUTES:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(401, resp.status_code, f"route {uri} did not return 401")

    def test_404(self):
        for uri in TEST_NOTFOUND_ROUTES:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(404, resp.status_code, f"route {uri} did not return 404")
