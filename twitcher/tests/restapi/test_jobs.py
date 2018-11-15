import pytest
import unittest
import webtest
import pyramid.testing
import six
from twitcher.tests.functional.common import setup_with_mongodb, setup_mongodb_jobstore
from twitcher.status import job_status_values, STATUS_SUCCEEDED, STATUS_FAILED


class WpsRestApiJobsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = setup_with_mongodb()
        cls.config.include('twitcher.wps')
        cls.config.include('twitcher.wps_restapi')
        cls.config.include('twitcher.tweens')
        cls.config.scan()
        cls.json_headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.jobstore = setup_mongodb_jobstore(self.config)

    def setup_jobs(self):
        j1 = self.jobstore.save_job('0123-4567-8910-1112', 'process-1', service=None,
                                    is_workflow=False, user_id=None, async=True)
        j1.status = STATUS_SUCCEEDED

        self.jobstore.update_job(j1)
        j2 = self.jobstore.save_job('9998-9796-9594-9392', 'process-2', service='service-A',
                                    is_workflow=True, user_id=1, async=False)
        j2.status = STATUS_FAILED
        self.jobstore.update_job(j2)

    @staticmethod
    def check_job_format(job):
        assert job is dict
        assert 'id' in job and isinstance(job['id'], six.string_types)
        assert 'status' in job and isinstance(job['status'], six.string_types)
        assert 'message' in job and isinstance(job['message'], six.string_types)
        assert 'percentCompleted' in job and isinstance(job['percentCompleted'], int)
        assert 'logs' in job and isinstance(job['logs'], six.string_types)
        assert job['status'] in job_status_values
        if job['status'] == STATUS_SUCCEEDED:
            assert 'result' in job and isinstance(job['result'], six.string_types)
        elif job['status'] == STATUS_FAILED:
            assert 'exceptions' in job and isinstance(job['exceptions'], six.string_types)

    def test_get_jobs(self):
        self.setup_jobs()
        resp = self.app.get('/jobs', headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'
        assert 'jobs' in resp.json and isinstance(resp.json['jobs'], list)
        assert 'page' in resp.json and isinstance(resp.json['page'], int)
        assert 'count' in resp.json and isinstance(resp.json['count'], int)
        assert 'limit' in resp.json and isinstance(resp.json['limit'], int)
        for job_id in resp.json['jobs']:
            assert isinstance(job_id, six.string_types)

    def test_get_jobs_detail(self):
        self.setup_jobs()
        resp = self.app.get('/jobs?detail=true', headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'
        assert 'jobs' in resp.json and isinstance(resp.json['jobs'], list)
        assert 'page' in resp.json and isinstance(resp.json['page'], int)
        assert 'count' in resp.json and isinstance(resp.json['count'], int)
        assert 'limit' in resp.json and isinstance(resp.json['limit'], int)
        for job in resp.json['jobs']:
            self.check_job_format(job)
