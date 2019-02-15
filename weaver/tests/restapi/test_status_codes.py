# noinspection PyPackageRequirements
import pytest
import unittest
# use 'Web' prefix to avoid pytest to pick up these classes and throw warnings
# noinspection PyPackageRequirements
from webtest import TestApp as WebTestApp
from weaver.wps_restapi.swagger_definitions import (
    api_frontpage_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_versions_uri,
    jobs_short_uri,
    jobs_full_uri,
)
from pyramid import testing
from weaver import main
from weaver.config import WEAVER_CONFIGURATION_DEFAULT
from weaver.tests.utils import get_test_weaver_app

public_routes = [
    api_frontpage_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_versions_uri,
]
forbidden_routes = [
    jobs_short_uri,  # should always be visible
    jobs_full_uri,  # could be 401
]
not_found_routes = [
    '/jobs/not-found',
    '/providers/not-found',
]


class StatusCodeTestCase(unittest.TestCase):
    """
    this routine should verify that the weaver app returns correct status codes for common cases, such as
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

    headers = {'accept': 'application/json'}

    def setUp_old(self):
        self.app = get_test_weaver_app()

    def setUp(self):
        config = testing.setUp()
        config.registry.settings['weaver.configuration'] = WEAVER_CONFIGURATION_DEFAULT
        config.registry.settings['weaver.url'] = 'https://localhost'
        app = main({}, **config.registry.settings)
        self.testapp = WebTestApp(app)

    def test_200(self):
        for uri in public_routes:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(200, resp.status_code, 'route {} did not return 200'.format(uri))

    @pytest.mark.xfail(reason="Not working if not behind proxy. Protected implementation to be done.")
    @unittest.expectedFailure
    def test_401(self):
        for uri in forbidden_routes:
            resp = self.app.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(401, resp.status_code, 'route {} did not return 401'.format(uri))

    def test_404(self):
        for uri in not_found_routes:
            resp = self.testapp.get(uri, expect_errors=True, headers=self.headers)
            self.assertEqual(404, resp.status_code, 'route {} did not return 404'.format(uri))


class CRUDTestCase(unittest.TestCase):
    """
    this routine should make sure that the services store jobs, processes and providers correctly,
      but directly from the services, and not only by status codes
    foreach of jobs, processes, providers
      save entity
      fetch entity and verify information
    """
    # create a store
    # instantiate wps_restapi with that store
    # test provider
    #   create provider
    #   create process in provider
    #   fetch process data
    #   submit job with dummy data
    #   fetch job and see its existence
    # sda
    pass
