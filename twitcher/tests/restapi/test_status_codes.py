from unittest import TestCase
from twitcher.tests.functional.common import setup_with_mongodb
from webtest import TestApp
from twitcher.wps_restapi.swagger_definitions import api_frontpage_uri, api_swagger_ui_uri, api_swagger_json_uri, \
    api_versions_uri, providers_uri, jobs_short_uri

public_routes = [
    api_frontpage_uri,
    api_swagger_ui_uri,
    api_swagger_json_uri,
    api_versions_uri,
]
forbidden_routes = [
    providers_uri,
    jobs_short_uri,
]
not_found_routes = [
    '/jobs/not-found',
    '/providers/not-found',
]


class StatusCodeTestCase(TestCase):

    def setUp(self):
        config = setup_with_mongodb()
        config.include('twitcher.wps_restapi')
        config.include('twitcher.tweens')
        config.get_settings()['twitcher.url'] = '/'
        self.app = TestApp(config.make_wsgi_app())

    def test_200(self):
        for uri in public_routes:
            resp = self.app.get(uri, expect_errors=True)
            self.assertEqual(resp.status_code, 200, 'route {} did not return 200'.format(uri))

    def test_401(self):
        for uri in forbidden_routes:
            resp = self.app.get(uri, expect_errors=True)
            self.assertEqual(resp.status_code, 401, 'route {} did not return 401'.format(uri))

    def test_404(self):
        for uri in not_found_routes:
            resp = self.app.get(uri, expect_errors=True)
            self.assertEqual(resp.status_code, 404, 'route {} did not return 404'.format(uri))
