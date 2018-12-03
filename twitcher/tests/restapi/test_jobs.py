# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import mock
# noinspection PyPackageRequirements
import webtest
import unittest
import json
import pyramid.testing
import six
from contextlib import nested
from typing import AnyStr, Tuple, List, Union
from twitcher.tests.utils import setup_config_with_mongodb, setup_mongodb_processstore, setup_mongodb_jobstore
from twitcher.datatype import Job
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from twitcher.status import (
    job_status_values,
    job_status_categories,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CATEGORY_FINISHED,
)


class WpsRestApiJobsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = setup_config_with_mongodb()
        cls.config.include('twitcher.wps')
        cls.config.include('twitcher.wps_restapi')
        cls.config.include('twitcher.tweens')
        cls.config.registry.settings['twitcher.url'] = "localhost"
        cls.config.scan()
        cls.json_headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.job_store = setup_mongodb_jobstore(self.config)
        self.process_store = setup_mongodb_processstore(self.config)

        self.user_admin_id = 100
        self.user_editor1_id = 1
        self.user_editor2_id = 2

        self.process_public = WpsTestProcess(identifier='process-public')
        self.process_store.save_process(self.process_public)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_private = WpsTestProcess(identifier='process-private')
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

        # create jobs accessible by index
        self.job_info = []  # type: List[Job]
        self.make_job(task_id='1111-1111-1111-1111', process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_SUCCEEDED, progress=100, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='2222-2222-2222-2222', process='process-unknown', service='service-A',
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id='3333-3333-3333-3333', process=self.process_private.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PUBLIC)
        # same process as Job 1, but private (ex: job ran with private process, then process made public afterwards)
        self.make_job(task_id='4444-4444-4444-4444', process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PRIVATE)
        # job ran by admin
        self.make_job(task_id='5555-5555-5555-5555', process=self.process_public.identifier, service=None,
                      user_id=self.user_admin_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PRIVATE)

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
        return message + "\nMapping Job-ID/Task-ID:\n{}".format(
            json.dumps(sorted(dict((j.id, j.task_id) for j in self.job_store.list_jobs())), indent=indent))

    def message_with_jobs_diffs(self, jobs_result, jobs_expect, test_values=None, message="", indent=2):
        return (message if message else "Different jobs returned than expected") + \
               ("\nResponse: {}".format(json.dumps(sorted(jobs_result), indent=indent))) + \
               ("\nExpected: {}".format(json.dumps(sorted(jobs_expect), indent=indent))) + \
               ("\nTesting: {}".format(test_values) if test_values else "") + \
               (self.message_with_jobs_mapping())

    def get_job_request_auth_mock(self, user_id):
        is_admin = self.user_admin_id == user_id
        return (
            mock.patch('pyramid.security.AuthenticationAPIMixin.authenticated_userid', new_callable=lambda: user_id),
            mock.patch('pyramid.request.AuthorizationAPIMixin.has_permission', return_value=lambda x: is_admin),
        )

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
        assert response.content_type == 'application/json'
        assert 'jobs' in response.json and isinstance(response.json['jobs'], list)
        assert 'page' in response.json and isinstance(response.json['page'], int)
        assert 'count' in response.json and isinstance(response.json['count'], int)
        assert 'limit' in response.json and isinstance(response.json['limit'], int)
        assert len(response.json['jobs']) <= response.json['limit']
        assert response.json['page'] == response.json['count'] // response.json['limit']

    def test_get_jobs_normal(self):
        resp = self.app.get("/jobs", headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        for job_id in resp.json['jobs']:
            assert isinstance(job_id, six.string_types)

        for var in ('false', 0, 'False', 'no', 'None', 'null', None, ''):
            path = "/jobs?detail={}".format(var)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job_id in resp.json['jobs']:
                assert isinstance(job_id, six.string_types)

    def test_get_jobs_detail(self):
        for var in ('true', 1, 'True', 'yes'):
            path = "/jobs?detail={}".format(var)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job in resp.json['jobs']:
                self.check_job_format(job)

    def test_get_process_jobs_in_query_normal(self):
        path = "/jobs?process={}".format(self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json['jobs'], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json['jobs'], self.message_with_jobs_mapping("expected not in")

    def test_get_process_jobs_in_query_detail(self):
        path = "/jobs?process={}&detail=true".format(self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j['jobID'] for j in resp.json['jobs']]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_process_jobs_in_path_normal(self):
        path = "/processes/{}/jobs".format(self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json['jobs'], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json['jobs'], self.message_with_jobs_mapping("expected not in")

    def test_get_process_jobs_in_path_detail(self):
        path = "/processes/{}/jobs?detail=true".format(self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j['jobID'] for j in resp.json['jobs']]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_process_jobs_unknown_in_path(self):
        # path must validate each object, so error on not found process
        path = "/processes/{}/jobs".format('unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == 'application/json'

    def test_get_process_jobs_unknown_in_query(self):
        # query acts as a filter, so no error on not found process
        path = "/jobs?process={}".format('unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert len(resp.json['jobs']) == 0

    def test_get_service_and_process_jobs_unknown_in_path(self):
        # path must validate each object, so error on not found process
        path = "/service/{}/processes/{}/jobs".format('unknown-service-id', 'unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == 'application/json'

    def test_get_service_and_process_jobs_unknown_in_query(self):
        # query acts as a filter, so no error on not found process
        path = "/jobs?service={}&process={}".format('unknown-service-id', 'unknown-process-id')
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert len(resp.json['jobs']) == 0

    def test_get_jobs_with_access(self):
        # Job 1 should have public visibility to all,
        # Job 4 only with private access (same editor or any admin)

        uri_direct_jobs = "/jobs"
        uri_process_job = "/processes/{}/jobs".format(self.process_private.identifier)

        def filter_process(jobs):
            return filter(lambda j: j.process == self.process_private.identifier, jobs)

        access_none = ""
        access_private = "?access={}".format(VISIBILITY_PRIVATE)
        access_public = "?access={}".format(VISIBILITY_PUBLIC)

        admin_public_jobs = filter(lambda j: VISIBILITY_PUBLIC in j.tags, self.job_info)
        admin_private_jobs = filter(lambda j: VISIBILITY_PRIVATE in j.tags, self.job_info)
        editor1_all_jobs = filter(lambda j: j.user_id == self.user_editor1_id, self.job_info)
        editor1_public_jobs = filter(lambda j: VISIBILITY_PUBLIC in j.tags, editor1_all_jobs)
        editor1_private_jobs = filter(lambda j: VISIBILITY_PRIVATE in j.tags, editor1_all_jobs)
        public_jobs = filter(lambda j: VISIBILITY_PUBLIC in j.tags, self.job_info)

        # test variations of [paths, query, user-id, expected-job-ids]
        path_jobs_user_req_tests = [
            (uri_direct_jobs, access_none,      None,                   public_jobs),
            (uri_direct_jobs, access_none,      self.user_editor1_id,   editor1_all_jobs),
            (uri_direct_jobs, access_none,      self.user_admin_id,     self.job_info),
            (uri_direct_jobs, access_private,   None,                   []),
            (uri_direct_jobs, access_private,   self.user_editor1_id,   editor1_private_jobs),
            (uri_direct_jobs, access_private,   self.user_admin_id,     admin_private_jobs),
            (uri_direct_jobs, access_public,    None,                   public_jobs),
            (uri_direct_jobs, access_public,    self.user_editor1_id,   editor1_public_jobs),
            (uri_direct_jobs, access_public,    self.user_admin_id,     admin_public_jobs),
            # ---
            (uri_process_job, access_none,      None,                   filter_process(public_jobs)),
            (uri_process_job, access_none,      self.user_editor1_id,   filter_process(editor1_all_jobs)),
            (uri_process_job, access_none,      self.user_admin_id,     filter_process(self.job_info)),
            (uri_process_job, access_private,   None,                   filter_process([])),
            (uri_process_job, access_private,   self.user_editor1_id,   filter_process(editor1_private_jobs)),
            (uri_process_job, access_private,   self.user_admin_id,     filter_process(admin_private_jobs)),
            (uri_process_job, access_public,    None,                   filter_process(public_jobs)),
            (uri_process_job, access_public,    self.user_editor1_id,   filter_process(editor1_public_jobs)),
            (uri_process_job, access_public,    self.user_admin_id,     filter_process(self.job_info)),

        ]   # type: List[Tuple[AnyStr, AnyStr, Union[None, int], List[AnyStr]]]

        for i, (path, query, user_id, expected_jobs) in enumerate(path_jobs_user_req_tests):
            # noinspection PyDeprecation
            with nested(*self.get_job_request_auth_mock(user_id)):
                test = "{}{}".format(path, query)
                resp = self.app.get(test, headers=self.json_headers)
                self.check_basic_jobs_info(resp)
                job_ids = [job.id for job in expected_jobs]
                job_match = all(job in job_ids for job in resp.json['jobs'])
                test_values = dict(path=path, query=query, user_id=user_id)
                assert job_match, self.message_with_jobs_diffs(resp.json['jobs'], job_ids, test_values)
