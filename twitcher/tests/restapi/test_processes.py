# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import mock
# noinspection PyPackageRequirements
import webtest
import unittest
import pyramid.testing
import six
from copy import deepcopy
from contextlib import nested
from twitcher.tests.functional.common import setup_with_mongodb, setup_mongodb_processstore, setup_mongodb_jobstore
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from twitcher.utils import fully_qualified_name


class WpsRestApiProcessesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = setup_with_mongodb()
        cls.config.registry.settings['twitcher.url'] = "localhost"
        cls.config.include('twitcher.wps')
        cls.config.include('twitcher.wps_restapi')
        cls.config.include('twitcher.tweens')
        cls.config.scan()
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)

        self.process_public = WpsTestProcess(identifier='process_public')
        self.process_private = WpsTestProcess(identifier='process_private')
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

    def test_get_processes(self):
        uri = '/processes'
        resp = self.app.get(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app
        assert 'processes' in resp.json and isinstance(resp.json['processes'], list) and len(resp.json['processes']) > 0
        for process in resp.json['processes']:
            assert 'id' in process and isinstance(process['id'], six.string_types)
            assert 'title' in process and isinstance(process['title'], six.string_types)
            assert 'version' in process and isinstance(process['version'], six.string_types)
            assert 'keywords' in process and isinstance(process['keywords'], list)
            assert 'metadata' in process and isinstance(process['metadata'], list)

        processes_id = [p['id'] for p in resp.json['processes']]
        assert self.process_public.identifier in processes_id
        assert self.process_private.identifier not in processes_id

    def test_describe_process_visibility_public(self):
        uri = "/processes/{}".format(self.process_public.identifier)
        resp = self.app.get(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app

    def test_describe_process_visibility_private(self):
        uri = "/processes/{}".format(self.process_private.identifier)
        resp = self.app.get(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == self.json_app

    @staticmethod
    def get_process_deploy_template(process_id):
        """
        Provides deploy process bare minimum template with undefined execution unit.
        To be used in conjunction with `get_process_package_mock` to avoid extra package content-specific validations.
        """
        return {
            "processDescription": {
                "process": {
                    "id": process_id,
                    "title": "Test process '{}'.".format(process_id),
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [
                # full definition not required with mock
                {"unit": {
                    'class': 'test'
                }}
            ]
        }

    @staticmethod
    def get_process_package_mock():
        return (
            mock.patch('twitcher.processes.wps_package._load_package_file', return_value={'class': 'test'}),
            mock.patch('twitcher.processes.wps_package._load_package_content', return_value=(None, 'test', None)),
            mock.patch('twitcher.processes.wps_package._get_package_inputs_outputs', return_value=(None, None)),
            mock.patch('twitcher.processes.wps_package._merge_package_inputs_outputs', return_value=([], [])),
        )

    def test_create_process_success(self):
        process_name = fully_qualified_name(self).replace('.', '-')
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        with nested(*package_mock):
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            # TODO: status should be 201 when properly modified to match API conformance
            assert resp.status_code == 200
            assert resp.content_type == self.json_app
            assert resp.json['processSummary']['id'] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

    def test_create_process_conflict(self):
        process_name = self.process_private.identifier
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        with nested(*package_mock):
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 409
            assert resp.content_type == self.json_app

    def test_create_process_missing_or_invalid_components(self):
        process_name = fully_qualified_name(self).replace('.', '-')
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        # remove components for testing different cases
        process_data_tests = [deepcopy(process_data) for _ in range(10)]
        process_data_tests[0].pop('processDescription')
        process_data_tests[1]['processDescription'].pop('process')
        process_data_tests[2]['processDescription']['process'].pop('id')
        process_data_tests[3].pop('deploymentProfileName')
        process_data_tests[4].pop('executionUnit')
        process_data_tests[5]['executionUnit'] = {}
        process_data_tests[6]['executionUnit'] = list()
        process_data_tests[7]['executionUnit'][0] = {"unit": "something"}       # unit as string instead of package
        process_data_tests[8]['executionUnit'][0] = {"href": {}}                # href as package instead of url
        process_data_tests[9]['executionUnit'][0] = {"unit": {}, "href": {}}    # both unit/href together not allowed

        with nested(*package_mock):
            uri = "/processes"
            for i, data in enumerate(process_data_tests):
                resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation `{}` with value `{}`."
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code)
                assert resp.content_type == self.json_app, msg.format(i, resp.content_type)

    def test_delete_process(self):
        pass

    def test_execute_process(self):
        pass

    def test_get_process_visibility(self):
        pass

    def test_set_process_visibility(self):
        pass
