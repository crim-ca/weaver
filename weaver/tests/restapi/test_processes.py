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
# noinspection PyDeprecation
from contextlib import nested
from weaver.tests.utils import (
    setup_config_with_mongodb,
    setup_mongodb_processstore,
    setup_mongodb_jobstore,
    get_test_weaver_app,
)
from weaver.wps import get_wps_url
from weaver.processes.wps_testing import WpsTestProcess
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from weaver.exceptions import ProcessNotFound, JobNotFound
from weaver.status import STATUS_ACCEPTED
from weaver.utils import fully_qualified_name
from weaver.execute import (
    EXECUTE_MODE_SYNC,
    EXECUTE_MODE_ASYNC,
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_VALUE,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
)


class WpsRestApiProcessesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = setup_config_with_mongodb()
        cls.app = get_test_weaver_app(config=cls.config)
        cls.config.registry.settings['weaver.url'] = "https://localhost"
        cls.config.registry.settings['weaver.wps_path'] = "/ows/wps"
        cls.config.include('weaver.wps')
        cls.config.include('weaver.wps_restapi')
        cls.config.include('weaver.tweens')
        cls.config.scan()
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type': cls.json_app}
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def fully_qualified_test_process_name(self):
        return fully_qualified_name(self).replace('.', '-')

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
    def get_process_execute_template(test_input='not-specified'):
        """
        Provides execute process bare minimum template corresponding to
        WPS process `weaver.processes.wps_testing.WpsTestProcess`.
        """
        return {
            "inputs": [
                {"id": "test_input",
                 "data": test_input},
            ],
            "outputs": [
                {"id": "test_output",
                 "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}
            ],
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
        }

    @staticmethod
    def get_process_package_mock():
        return (
            mock.patch('weaver.processes.wps_package._load_package_file', return_value={'class': 'test'}),
            mock.patch('weaver.processes.wps_package._load_package_content', return_value=(None, 'test', None)),
            mock.patch('weaver.processes.wps_package._get_package_inputs_outputs', return_value=(None, None)),
            mock.patch('weaver.processes.wps_package._merge_package_inputs_outputs', return_value=([], [])),
        )

    @staticmethod
    def get_process_job_runner_mock(job_task_id="mocked-job-id"):
        result = mock.MagicMock()
        result.id = job_task_id
        return (
            mock.patch('weaver.wps_restapi.processes.processes.execute_process.delay', return_value=result),
        )

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

    def test_get_processes_invalid_schemas_handled(self):
        path = "/processes"
        # deploy valid test process
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()
        # noinspection PyDeprecation
        with nested(*package_mock):
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            # TODO: status should be 201 when properly modified to match API conformance
            assert resp.status_code == 200
            assert resp.json['processSummary']['id'] == process_name

        # change value that will trigger schema error on check
        process = self.process_store.fetch_by_id(process_name)
        process['jobControlOptions'] = "random"     # invalid
        process['visibility'] = VISIBILITY_PUBLIC
        self.process_store.save_process(process, overwrite=True)

        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 503
        assert resp.content_type == self.json_app
        assert process_name in resp.json.get('description')

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

    def test_deploy_process_success(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        # noinspection PyDeprecation
        with nested(*package_mock):
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            # TODO: status should be 201 when properly modified to match API conformance
            assert resp.status_code == 200
            assert resp.content_type == self.json_app
            assert resp.json['processSummary']['id'] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

    def test_deploy_process_bad_name(self):
        process_name = self.fully_qualified_test_process_name() + "..."
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        # noinspection PyDeprecation
        with nested(*package_mock):
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 400
            assert resp.content_type == self.json_app

    def test_deploy_process_conflict(self):
        process_name = self.process_private.identifier
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        # noinspection PyDeprecation
        with nested(*package_mock):
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 409
            assert resp.content_type == self.json_app

    # noinspection PyTypeChecker
    def test_deploy_process_missing_or_invalid_components(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        # remove components for testing different cases
        process_data_tests = [deepcopy(process_data) for _ in range(12)]
        process_data_tests[0].pop('processDescription')
        process_data_tests[1]['processDescription'].pop('process')
        process_data_tests[2]['processDescription']['process'].pop('id')
        process_data_tests[3]['processDescription']['jobControlOptions'] = EXECUTE_CONTROL_OPTION_ASYNC
        process_data_tests[4]['processDescription']['jobControlOptions'] = [EXECUTE_MODE_ASYNC]
        process_data_tests[5].pop('deploymentProfileName')
        process_data_tests[6].pop('executionUnit')
        process_data_tests[7]['executionUnit'] = {}
        process_data_tests[8]['executionUnit'] = list()
        process_data_tests[9]['executionUnit'][0] = {"unit": "something"}       # unit as string instead of package
        process_data_tests[10]['executionUnit'][0] = {"href": {}}               # href as package instead of url
        process_data_tests[11]['executionUnit'][0] = {"unit": {}, "href": ""}   # can't have both unit/href together

        # noinspection PyDeprecation
        with nested(*package_mock):
            uri = "/processes"
            for i, data in enumerate(process_data_tests):
                resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation `{}` with value `{}`."
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code)
                assert resp.content_type == self.json_app, msg.format(i, resp.content_type)

    def test_deploy_process_default_endpoint_wps1(self):
        """Validates that the default (localhost) endpoint to execute WPS requests are saved during deployment."""
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = self.get_process_package_mock()

        # noinspection PyDeprecation
        with nested(*package_mock):
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            # TODO: status should be 201 when properly modified to match API conformance
            assert resp.status_code == 200

        weaver_wps_path = get_wps_url(self.config.registry.settings)
        process_wps_endpoint = self.process_store.fetch_by_id(process_name).processEndpointWPS1
        assert isinstance(process_wps_endpoint, six.string_types) and len(process_wps_endpoint)
        assert process_wps_endpoint == weaver_wps_path

    def test_delete_process_success(self):
        uri = "/processes/{}".format(self.process_public.identifier)
        resp = self.app.delete_json(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app
        assert resp.json['identifier'] == self.process_public.identifier
        assert isinstance(resp.json['undeploymentDone'], bool) and resp.json['undeploymentDone']
        with pytest.raises(ProcessNotFound):
            self.process_store.fetch_by_id(self.process_public.identifier)

    def test_delete_process_not_accessible(self):
        uri = "/processes/{}".format(self.process_private.identifier)
        resp = self.app.delete_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == self.json_app

    def test_delete_process_not_found(self):
        uri = "/processes/{}".format(self.fully_qualified_test_process_name())
        resp = self.app.delete_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == self.json_app

    def test_delete_process_bad_name(self):
        uri = "/processes/{}".format(self.fully_qualified_test_process_name() + "...")
        resp = self.app.delete_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == self.json_app

    def test_execute_process_success(self):
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        data = self.get_process_execute_template()
        task = "job-{}".format(fully_qualified_name(self))
        mock_execute = self.get_process_job_runner_mock(task)

        # noinspection PyDeprecation
        with nested(*mock_execute):
            resp = self.app.post_json(uri, params=data, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == self.json_app
            assert resp.json['location'].endswith(resp.json['jobID'])
            assert resp.headers['Location'] == resp.json['location']
            try:
                job = self.job_store.fetch_by_id(resp.json['jobID'])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert job.id == resp.json['jobID']
            assert job.task_id == STATUS_ACCEPTED   # temporary value until processed by celery

    def test_execute_process_no_json_body(self):
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == self.json_app

    def test_execute_process_missing_required_params(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))

        # remove components for testing different cases
        execute_data_tests = [deepcopy(execute_data) for _ in range(7)]
        execute_data_tests[0].pop('outputs')
        execute_data_tests[1].pop('mode')
        execute_data_tests[2].pop('response')
        execute_data_tests[3]['mode'] = "random"
        execute_data_tests[4]['response'] = "random"
        execute_data_tests[5]['inputs'] = [{"test_input": "test_value"}]    # bad format
        execute_data_tests[6]['outputs'] = [{"id": "test_output", "transmissionMode": "random"}]

        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        for i, exec_data in enumerate(execute_data_tests):
            resp = self.app.post_json(uri, params=exec_data, headers=self.json_headers, expect_errors=True)
            msg = "Failed with test variation `{}` with value `{}`."
            assert resp.status_code in [400, 422], msg.format(i, resp.status_code)
            assert resp.content_type == self.json_app, msg.format(i, resp.content_type)

    def test_execute_process_no_error_not_required_params(self):
        """
        Optional parameters for execute job shouldn't raise an error if omitted,
        and should resolve to default values if any was specified.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)
        execute_mock_data_tests = list()
        for i in range(2):
            mock_execute = self.get_process_job_runner_mock("job-{}-{}".format(name, i))
            data_execute = self.get_process_execute_template("{}-{}".format(name, i))
            execute_mock_data_tests.append((mock_execute, data_execute))

        # apply modifications for testing
        execute_mock_data_tests[0][1].pop('inputs')     # no inputs is valid (although can be required for WPS process)
        execute_mock_data_tests[0][1]['outputs'][0].pop('transmissionMode')     # should resolve to default value

        for mock_execute, data_execute in execute_mock_data_tests:
            # noinspection PyDeprecation
            with nested(*mock_execute):
                path = "/processes/{}/jobs".format(self.process_public.identifier)
                resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
                assert resp.status_code == 201, "Expected job submission without inputs created without error."

    @pytest.mark.xfail(reason="Mode '{}' not supported for job execution.".format(EXECUTE_MODE_SYNC))
    @unittest.expectedFailure
    def test_execute_process_mode_sync_not_supported(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))
        execute_data['mode'] = EXECUTE_MODE_SYNC
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(uri, params=execute_data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in 501
        assert resp.content_type == self.json_app

    @pytest.mark.xfail(reason="Mode '{}' not supported for job execution.".format(EXECUTE_TRANSMISSION_MODE_VALUE))
    @unittest.expectedFailure
    def test_execute_process_transmission_mode_value_not_supported(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))
        execute_data['outputs'][0]['transmissionMode'] = EXECUTE_TRANSMISSION_MODE_VALUE
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(uri, params=execute_data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in 501
        assert resp.content_type == self.json_app

    def test_execute_process_not_visible(self):
        uri = "/processes/{}/jobs".format(self.process_private.identifier)
        data = self.get_process_execute_template()
        resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == self.json_app

    def test_get_process_visibility_success(self):
        for wps_process in [self.process_private, self.process_public]:
            process = self.process_store.fetch_by_id(wps_process.identifier)
            uri = "/processes/{}/visibility".format(process.identifier)
            resp = self.app.get(uri, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == self.json_app
            assert resp.json['value'] == process.visibility

    def test_get_process_visibility_not_found(self):
        uri = "/processes/{}/visibility".format(self.fully_qualified_test_process_name())
        resp = self.app.get(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == self.json_app

    def test_set_process_visibility_success(self):
        test_process = self.process_private.identifier
        uri_describe = "/processes/{}".format(test_process)
        uri_visibility = "{}/visibility".format(uri_describe)

        # validate cannot be found before
        resp = self.app.get(uri_describe, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401

        # make public
        data = {'value': VISIBILITY_PUBLIC}
        resp = self.app.put_json(uri_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app
        assert resp.json['value'] == VISIBILITY_PUBLIC

        # validate now visible and found
        resp = self.app.get(uri_describe, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json['process']['id'] == test_process

        # make private
        data = {'value': VISIBILITY_PRIVATE}
        resp = self.app.put_json(uri_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app
        assert resp.json['value'] == VISIBILITY_PRIVATE

        # validate cannot be found anymore
        resp = self.app.get(uri_describe, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401

    def test_set_process_visibility_bad_formats(self):
        uri = "/processes/{}/visibility".format(self.process_private.identifier)
        test_data = [
            {'visibility': VISIBILITY_PUBLIC},
            {'visibility': True},
            {'visibility': None},
            {'visibility': 1},
            {'value': True},
            {'value': None},
            {'value': 1}
        ]

        # bad body format or types
        for data in test_data:
            resp = self.app.put_json(uri, params=data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code in [400, 422]
            assert resp.content_type == self.json_app

        # bad method POST
        data = {'value': VISIBILITY_PUBLIC}
        resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 405
        assert resp.content_type == self.json_app
