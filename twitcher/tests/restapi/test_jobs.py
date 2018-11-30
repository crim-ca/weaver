# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import webtest
import unittest
import pyramid.testing
import six
from typing import AnyStr, Tuple, List
from twitcher.tests.utils import setup_config_with_mongodb, setup_mongodb_processstore, setup_mongodb_jobstore
from twitcher.status import job_status_values, STATUS_SUCCEEDED, STATUS_FAILED
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE


class UserRequest(pyramid.testing.DummyRequest):
    def __init__(self, user_id=None, is_admin=False, **kw):
        super(UserRequest, self).__init__(**kw)
        self.user_id = user_id
        self.is_admin = is_admin

    @property
    def authenticated_userid(self):
        return self.user_id

    def has_permission(self, permission, context=None):
        return self.is_admin if permission == 'admin' else False


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

        self.test_job1_process_id = 'process-1'
        self.process_public = WpsTestProcess(identifier=self.test_job1_process_id)
        self.process_store.save_process(self.process_public)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.test_job1_service_id = None
        self.test_job1_task_id = '0123-4567-8910-1112'
        j1 = self.job_store.save_job(task_id=self.test_job1_task_id,
                                     process=self.test_job1_process_id, service=self.test_job1_service_id,
                                     is_workflow=False, user_id=None, execute_async=True)
        j1.status = STATUS_SUCCEEDED
        j1.mark_finished()
        j1.progress = 100
        j1.tags.append(VISIBILITY_PUBLIC)
        j1 = self.job_store.update_job(j1)
        self.test_job1_id = j1.id

        self.test_job2_process_id = 'process-2'
        self.test_job2_service_id = 'service-A'
        self.test_job2_task_id = '9998-9796-9594-9392'
        j2 = self.job_store.save_job(task_id=self.test_job2_task_id,
                                     process=self.test_job2_process_id, service=self.test_job2_service_id,
                                     is_workflow=True, user_id=1, execute_async=False)
        j2.status = STATUS_FAILED
        j2.mark_finished()
        j2.progress = 99
        j2.tags.append(VISIBILITY_PUBLIC)
        j2 = self.job_store.update_job(j2)
        self.test_job2_id = j2.id

        self.test_job3_process_id = 'process-3'
        self.process_private = WpsTestProcess(identifier=self.test_job3_process_id)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)
        self.test_job3_service_id = None
        self.test_job3_task_id = '1111-2222-3333-4444'
        j3 = self.job_store.save_job(task_id=self.test_job3_task_id,
                                     process=self.test_job3_process_id, service=self.test_job3_service_id,
                                     is_workflow=False, user_id=None, execute_async=True)
        j3.status = STATUS_FAILED
        j3.mark_finished()
        j3.progress = 55
        j3.tags.append(VISIBILITY_PUBLIC)
        j3 = self.job_store.update_job(j3)
        self.test_job3_id = j3.id

        # same process as Job 1, but job set to private with and editor instead
        # (ex: job ran with private process, then process made public afterwards)
        self.test_job4_process_id = self.test_job1_process_id
        self.test_job4_service_id = None
        self.test_job4_task_id = '9999-8888-7777-6666'
        j4 = self.job_store.save_job(task_id=self.test_job4_task_id,
                                     process=self.test_job4_process_id, service=self.test_job4_service_id,
                                     is_workflow=False, user_id=self.user_editor1_id, execute_async=True)
        j4.status = STATUS_FAILED
        j4.mark_finished()
        j4.progress = 55
        j4.tags.append(VISIBILITY_PRIVATE)
        j4 = self.job_store.update_job(j4)
        self.test_job4_id = j4.id

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
        path = "/jobs?process={}".format(self.test_job1_process_id)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.test_job1_id in resp.json['jobs']
        assert self.test_job2_id not in resp.json['jobs']

    def test_get_process_jobs_in_query_detail(self):
        path = "/jobs?process={}&detail=true".format(self.test_job1_process_id)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j['jobID'] for j in resp.json['jobs']]
        assert self.test_job1_id in job_ids
        assert self.test_job2_id not in job_ids

    def test_get_process_jobs_in_path_normal(self):
        path = "/processes/{}/jobs".format(self.test_job1_process_id)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.test_job1_id in resp.json['jobs']
        assert self.test_job2_id not in resp.json['jobs']

    def test_get_process_jobs_in_path_detail(self):
        path = "/processes/{}/jobs?detail=true".format(self.test_job1_process_id)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j['jobID'] for j in resp.json['jobs']]
        assert self.test_job1_id in job_ids
        assert self.test_job2_id not in job_ids

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

        # test variations of paths/user request, and expected job outputs
        path_jobs_user_req_tests = [
            ("/jobs", UserRequest(), [self.test_job1_id]),
            ("/processes/{}/jobs".format(self.process_public.identifier), UserRequest(), [self.test_job1_id]),
            ("/jobs", UserRequest(), [self.test_job1_id]),
            ("/processes/{}/jobs".format(self.process_public.identifier), UserRequest(), [self.test_job1_id]),
        ]   # type: List[Tuple[AnyStr, UserRequest, List[AnyStr]]]

        for path, expected_jobs in path_jobs_user_req_tests:
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
