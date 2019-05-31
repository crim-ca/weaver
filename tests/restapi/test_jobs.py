from weaver.wps_restapi.swagger_definitions import (
    jobs_short_uri,
    jobs_full_uri,
    process_jobs_uri,
)
from weaver.datatype import Service, Job
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.processes.wps_testing import WpsTestProcess
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.status import (
    job_status_values,
    job_status_categories,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CATEGORY_FINISHED,
)
from tests.utils import (
    ignore_deprecated_nested_warnings,
    setup_config_with_mongodb,
    setup_mongodb_servicestore,
    setup_mongodb_processstore,
    setup_mongodb_jobstore,
)
from collections import OrderedDict
# noinspection PyDeprecation
from contextlib import nested
from typing import AnyStr, Tuple, List, Union
from owslib.wps import WebProcessingService, Process as ProcessOWSWPS
from pywps.app import Process as ProcessPyWPS
import mock
import webtest
import unittest
import warnings
import json
import pyramid.testing
import six


class WpsRestApiJobsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.simplefilter('ignore', TimeZoneInfoAlreadySetWarning)
        cls.config = setup_config_with_mongodb()
        cls.config.include('weaver.wps')
        cls.config.include('weaver.wps_restapi')
        cls.config.include('weaver.tweens')
        cls.config.registry.settings['weaver.url'] = "localhost"
        cls.config.scan()
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.job_store = setup_mongodb_jobstore(self.config)
        self.process_store = setup_mongodb_processstore(self.config)
        self.service_store = setup_mongodb_servicestore(self.config)

        self.user_admin_id = 100
        self.user_editor1_id = 1
        self.user_editor2_id = 2

        self.process_public = WpsTestProcess(identifier='process-public')
        self.process_store.save_process(self.process_public)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_private = WpsTestProcess(identifier='process-private')
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

        self.service_public = Service(name='service-public', url='http://localhost/wps/service-public', public=True)
        self.service_store.save_service(self.service_public)
        self.service_private = Service(name='service-private', url='http://localhost/wps/service-private', public=False)
        self.service_store.save_service(self.service_private)

        # create jobs accessible by index
        self.job_info = []  # type: List[Job]
        self.make_job(task_id='0000-0000-0000-0000', process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_SUCCEEDED, progress=100, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='1111-1111-1111-1111', process='process-unknown', service=self.service_public.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='2222-2222-2222-2222', process=self.process_private.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PUBLIC)
        # same process as job 0, but private (ex: job ran with private process, then process made public afterwards)
        self.make_job(task_id='3333-3333-3333-3333', process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PRIVATE)
        # job ran by admin
        self.make_job(task_id='4444-4444-4444-4444', process=self.process_public.identifier, service=None,
                      user_id=self.user_admin_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PRIVATE)
        # job public/private service/process combinations
        self.make_job(task_id='5555-5555-5555-5555',
                      process=self.process_public.identifier, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='6666-6666-6666-6666',
                      process=self.process_private.identifier, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='7777-7777-7777-7777',
                      process=self.process_public.identifier, service=self.service_private.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='8888-8888-8888-8888',
                      process=self.process_private.identifier, service=self.service_private.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)

    def make_job(self, task_id, process, service, user_id, status, progress, access):
        job = self.job_store.save_job(task_id=task_id, process=process, service=service, is_workflow=False,
                                      user_id=user_id, execute_async=True, access=access)
        job.status = status
        if status in job_status_categories[STATUS_CATEGORY_FINISHED]:
            job.mark_finished()
        job.progress = progress
        job = self.job_store.update_job(job)
        self.job_info.append(job)

    def message_with_jobs_mapping(self, message="", indent=2):
        """For helping debugging of auto-generated job ids"""
        mapping = OrderedDict(sorted((j.task_id, j.id) for j in self.job_store.list_jobs()))
        return message + "\nMapping Task-ID/Job-ID:\n{}".format(json.dumps(mapping, indent=indent))

    def message_with_jobs_diffs(self, jobs_result, jobs_expect, test_values=None, message="", indent=2, index=None):
        return (message if message else "Different jobs returned than expected") + \
               (" (index: {})".format(index) if index is not None else "") + \
               ("\nResponse: {}".format(json.dumps(sorted(jobs_result), indent=indent))) + \
               ("\nExpected: {}".format(json.dumps(sorted(jobs_expect), indent=indent))) + \
               ("\nTesting: {}".format(test_values) if test_values else "") + \
               (self.message_with_jobs_mapping())

    def get_job_request_auth_mock(self, user_id):
        is_admin = self.user_admin_id == user_id
        return tuple([
            mock.patch('pyramid.security.AuthenticationAPIMixin.authenticated_userid', new_callable=lambda: user_id),
            mock.patch('pyramid.request.AuthorizationAPIMixin.has_permission', return_value=is_admin),
        ])

    # noinspection PyProtectedMember
    @staticmethod
    def get_job_remote_service_mock(processes):
        # type: (List[Union[ProcessPyWPS, ProcessOWSWPS]]) -> Tuple[mock._patch]
        mock_processes = mock.PropertyMock
        mock_processes.return_value = processes
        return tuple([
            mock.patch.object(WebProcessingService, 'getcapabilities', new=lambda *args, **kwargs: None),
            mock.patch.object(WebProcessingService, 'processes', new_callable=mock_processes, create=True),
        ])

    @staticmethod
    def check_job_format(job):
        assert isinstance(job, dict)
        assert 'jobID' in job and isinstance(job['jobID'], six.string_types)
        assert 'status' in job and isinstance(job['status'], six.string_types)
        assert 'message' in job and isinstance(job['message'], six.string_types)
        assert 'percentCompleted' in job and isinstance(job['percentCompleted'], int)
        assert 'logs' in job and isinstance(job['logs'], six.string_types)
        assert job['status'] in job_status_values
        if job['status'] == STATUS_SUCCEEDED:
            assert 'result' in job and isinstance(job['result'], six.string_types)
        elif job['status'] == STATUS_FAILED:
            assert 'exceptions' in job and isinstance(job['exceptions'], six.string_types)

    @staticmethod
    def check_basic_jobs_info(response):
        assert response.status_code == 200
        assert response.content_type == CONTENT_TYPE_APP_JSON
        assert 'jobs' in response.json and isinstance(response.json['jobs'], list)
        assert 'page' in response.json and isinstance(response.json['page'], int)
        assert 'count' in response.json and isinstance(response.json['count'], int)
        assert 'limit' in response.json and isinstance(response.json['limit'], int)
        assert len(response.json['jobs']) <= response.json['limit']
        assert response.json['page'] == response.json['count'] // response.json['limit']

    @staticmethod
    def add_params(path, **kwargs):
        return path + "?" + "&".join("{}={}".format(k, v) for k, v in kwargs.items())

    def test_get_jobs_normal(self):
        resp = self.app.get(jobs_short_uri, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        for job_id in resp.json['jobs']:
            assert isinstance(job_id, six.string_types)

        for detail in ('false', 0, 'False', 'no', 'None', 'null', None, ''):
            path = self.add_params(jobs_short_uri, detail=detail)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job_id in resp.json['jobs']:
                assert isinstance(job_id, six.string_types)

    def test_get_jobs_detail(self):
        for detail in ('true', 1, 'True', 'yes'):
            path = self.add_params(jobs_short_uri, detail=detail)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job in resp.json['jobs']:
                self.check_job_format(job)

    def test_get_jobs_process_in_query_normal(self):
        path = self.add_params(jobs_short_uri, process=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json['jobs'], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json['jobs'], self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_query_detail(self):
        path = self.add_params(jobs_short_uri, process=self.job_info[0].process, detail='true')
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j['jobID'] for j in resp.json['jobs']]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_path_normal(self):
        path = process_jobs_uri.format(process_id=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json['jobs'], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json['jobs'], self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_path_detail(self):
        path = process_jobs_uri.format(process_id=self.job_info[0].process) + "?detail=true"
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j['jobID'] for j in resp.json['jobs']]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_unknown_in_path(self):
        path = process_jobs_uri.format(process_id='unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_process_unknown_in_query(self):
        path = self.add_params(jobs_short_uri, process='unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_process_unauthorized_in_path(self):
        path = process_jobs_uri.format(process_id=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_process_not_returned_in_query(self):
        path = self.add_params(jobs_short_uri, process=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_service_and_process_unknown_in_path(self):
        path = jobs_full_uri.format(provider_id='unknown-service-id', process_id='unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_service_and_process_unknown_in_query(self):
        path = self.add_params(jobs_short_uri, service='unknown-service-id', process='unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_service_public_process_unauthorized_in_path(self):
        path = jobs_full_uri.format(provider_id=self.service_private.name, process_id=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_service_public_process_unauthorized_in_query(self):
        path = self.add_params(jobs_short_uri,
                               service=self.service_private.name,
                               process=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    @ignore_deprecated_nested_warnings
    def test_get_jobs_public_service_private_process_unauthorized_in_query(self):
        """
        NOTE:
            it is up to the remote service to hide private processes
            if the process is visible, the a job can be executed and it is automatically considered public
        """
        path = self.add_params(jobs_short_uri,
                               service=self.service_public.name,
                               process=self.process_private.identifier)
        # noinspection PyDeprecation
        with nested(*self.get_job_remote_service_mock([self.process_private])):     # process visible on remote
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 200
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    @ignore_deprecated_nested_warnings
    def test_get_jobs_public_service_no_processes(self):
        """
        NOTE:
            it is up to the remote service to hide private processes
            if the process is invisible, no job should have been executed nor can be fetched
        """
        path = self.add_params(jobs_short_uri,
                               service=self.service_public.name,
                               process=self.process_private.identifier)
        # noinspection PyDeprecation
        with nested(*self.get_job_remote_service_mock([])):         # process invisible (not returned by remote)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 404
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    @ignore_deprecated_nested_warnings
    def test_get_jobs_public_with_access_and_request_user(self):
        """Verifies that corresponding processes are returned when proper access/user-id are respected."""
        uri_direct_jobs = jobs_short_uri
        uri_process_jobs = process_jobs_uri.format(process_id=self.process_public.identifier)
        uri_provider_jobs = jobs_full_uri.format(
            provider_id=self.service_public.name, process_id=self.process_public.identifier)

        admin_public_jobs = filter(lambda j: VISIBILITY_PUBLIC in j.access, self.job_info)
        admin_private_jobs = filter(lambda j: VISIBILITY_PRIVATE in j.access, self.job_info)
        editor1_all_jobs = filter(lambda j: j.user_id == self.user_editor1_id, self.job_info)
        editor1_public_jobs = filter(lambda j: VISIBILITY_PUBLIC in j.access, editor1_all_jobs)
        editor1_private_jobs = filter(lambda j: VISIBILITY_PRIVATE in j.access, editor1_all_jobs)
        public_jobs = filter(lambda j: VISIBILITY_PUBLIC in j.access, self.job_info)

        def filter_process(jobs):
            return filter(lambda j: j.process == self.process_public.identifier, jobs)

        def filter_service(jobs):
            return filter(lambda j: j.service == self.service_public.name, jobs)

        # test variations of [paths, query, user-id, expected-job-ids]
        path_jobs_user_req_tests = [
            # URI               ACCESS              USER                    EXPECTED JOBS
            (uri_direct_jobs,   None,               None,                   public_jobs),                               # noqa: E241, E501
            (uri_direct_jobs,   None,               self.user_editor1_id,   editor1_all_jobs),                          # noqa: E241, E501
            (uri_direct_jobs,   None,               self.user_admin_id,     self.job_info),                             # noqa: E241, E501
            (uri_direct_jobs,   VISIBILITY_PRIVATE, None,                   public_jobs),                               # noqa: E241, E501
            (uri_direct_jobs,   VISIBILITY_PRIVATE, self.user_editor1_id,   editor1_private_jobs),                      # noqa: E241, E501
            (uri_direct_jobs,   VISIBILITY_PRIVATE, self.user_admin_id,     admin_private_jobs),                        # noqa: E241, E501
            (uri_direct_jobs,   VISIBILITY_PUBLIC,  None,                   public_jobs),                               # noqa: E241, E501
            (uri_direct_jobs,   VISIBILITY_PUBLIC,  self.user_editor1_id,   editor1_public_jobs),                       # noqa: E241, E501
            (uri_direct_jobs,   VISIBILITY_PUBLIC,  self.user_admin_id,     admin_public_jobs),                         # noqa: E241, E501
            # ---
            (uri_process_jobs,  None,               None,                   filter_process(public_jobs)),               # noqa: E241, E501
            (uri_process_jobs,  None,               self.user_editor1_id,   filter_process(editor1_all_jobs)),          # noqa: E241, E501
            (uri_process_jobs,  None,               self.user_admin_id,     filter_process(self.job_info)),             # noqa: E241, E501
            (uri_process_jobs,  VISIBILITY_PRIVATE, None,                   filter_process(public_jobs)),               # noqa: E241, E501
            (uri_process_jobs,  VISIBILITY_PRIVATE, self.user_editor1_id,   filter_process(editor1_private_jobs)),      # noqa: E241, E501
            (uri_process_jobs,  VISIBILITY_PRIVATE, self.user_admin_id,     filter_process(admin_private_jobs)),        # noqa: E241, E501
            (uri_process_jobs,  VISIBILITY_PUBLIC,  None,                   filter_process(public_jobs)),               # noqa: E241, E501
            (uri_process_jobs,  VISIBILITY_PUBLIC,  self.user_editor1_id,   filter_process(editor1_public_jobs)),       # noqa: E241, E501
            (uri_process_jobs,  VISIBILITY_PUBLIC,  self.user_admin_id,     filter_process(self.job_info)),             # noqa: E241, E501
            # ---
            (uri_provider_jobs, None,               None,                   filter_service(public_jobs)),               # noqa: E241, E501
            (uri_provider_jobs, None,               self.user_editor1_id,   filter_service(editor1_all_jobs)),          # noqa: E241, E501
            (uri_provider_jobs, None,               self.user_admin_id,     filter_service(self.job_info)),             # noqa: E241, E501
            (uri_provider_jobs, VISIBILITY_PRIVATE, None,                   filter_service(public_jobs)),               # noqa: E241, E501
            (uri_provider_jobs, VISIBILITY_PRIVATE, self.user_editor1_id,   filter_service(editor1_private_jobs)),      # noqa: E241, E501
            (uri_provider_jobs, VISIBILITY_PRIVATE, self.user_admin_id,     filter_service(admin_private_jobs)),        # noqa: E241, E501
            (uri_provider_jobs, VISIBILITY_PUBLIC,  None,                   filter_service(public_jobs)),               # noqa: E241, E501
            (uri_provider_jobs, VISIBILITY_PUBLIC,  self.user_editor1_id,   filter_service(editor1_public_jobs)),       # noqa: E241, E501
            (uri_provider_jobs, VISIBILITY_PUBLIC,  self.user_admin_id,     filter_service(self.job_info)),             # noqa: E241, E501

        ]   # type: List[Tuple[AnyStr, AnyStr, Union[None, int], List[AnyStr]]]

        for i, (path, access, user_id, expected_jobs) in enumerate(path_jobs_user_req_tests):
            patches = self.get_job_request_auth_mock(user_id) + self.get_job_remote_service_mock([self.process_public])
            # noinspection PyDeprecation
            with nested(*patches):
                test = self.add_params(path, access=access) if access else path
                resp = self.app.get(test, headers=self.json_headers)
                self.check_basic_jobs_info(resp)
                job_ids = [job.id for job in expected_jobs]
                job_match = all(job in job_ids for job in resp.json['jobs'])
                test_values = dict(path=path, access=access, user_id=user_id)
                assert job_match, self.message_with_jobs_diffs(resp.json['jobs'], job_ids, test_values, index=i)
