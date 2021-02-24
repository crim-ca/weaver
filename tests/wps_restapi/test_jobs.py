import contextlib
import json
import unittest
import warnings
from collections import OrderedDict
from typing import TYPE_CHECKING

import mock
import pyramid.testing
import pytest
import webtest
from owslib.wps import WebProcessingService

from tests.utils import (
    mocked_process_job_runner,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver.datatype import Job, Service
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_RESPONSE_DOCUMENT, EXECUTE_TRANSMISSION_MODE_REFERENCE
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.processes.wps_testing import WpsTestProcess
from weaver.status import (
    JOB_STATUS_CATEGORIES,
    JOB_STATUS_VALUES,
    STATUS_CATEGORY_FINISHED,
    STATUS_FAILED,
    STATUS_SUCCEEDED
)
from weaver.utils import get_path_kvp
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.wps_restapi.swagger_definitions import jobs_full_uri, jobs_short_uri, process_jobs_uri

if TYPE_CHECKING:
    from typing import Iterable, List, Tuple, Union

    from owslib.wps import Process as ProcessOWSWPS
    from pywps.app import Process as ProcessPyWPS

    # pylint: disable=C0103,invalid-name,E1101,no-member
    MockPatch = mock._patch  # noqa: W0212


class WpsRestApiJobsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", TimeZoneInfoAlreadySetWarning)
        cls.config = setup_config_with_mongodb()
        cls.config.include("weaver.wps")
        cls.config.include("weaver.wps_restapi")
        cls.config.include("weaver.tweens")
        cls.config.registry.settings.update({
            "weaver.url": "localhost",
            "weaver.wps_email_encrypt_salt": "weaver-test",
        })
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

        self.process_public = WpsTestProcess(identifier="process-public")
        self.process_store.save_process(self.process_public)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_private = WpsTestProcess(identifier="process-private")
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)
        self.process_unknown = "process-unknown"

        self.service_public = Service(name="service-public", url="http://localhost/wps/service-public", public=True)
        self.service_store.save_service(self.service_public)
        self.service_private = Service(name="service-private", url="http://localhost/wps/service-private", public=False)
        self.service_store.save_service(self.service_private)

        # create jobs accessible by index
        self.job_info = []  # type: List[Job]
        self.make_job(task_id="0000-0000-0000-0000", process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_SUCCEEDED, progress=100, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="1111-1111-1111-1111", process=self.process_unknown, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="2222-2222-2222-2222", process=self.process_private.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PUBLIC)
        # same process as job 0, but private (ex: job ran with private process, then process made public afterwards)
        self.make_job(task_id="3333-3333-3333-3333", process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PRIVATE)
        # job ran by admin
        self.make_job(task_id="4444-4444-4444-4444", process=self.process_public.identifier, service=None,
                      user_id=self.user_admin_id, status=STATUS_FAILED, progress=55, access=VISIBILITY_PRIVATE)
        # job public/private service/process combinations
        self.make_job(task_id="5555-5555-5555-5555",
                      process=self.process_public.identifier, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="6666-6666-6666-6666",
                      process=self.process_private.identifier, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="7777-7777-7777-7777",
                      process=self.process_public.identifier, service=self.service_private.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="8888-8888-8888-8888",
                      process=self.process_private.identifier, service=self.service_private.name,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)

    def make_job(self, task_id, process, service, user_id, status, progress, access):
        job = self.job_store.save_job(task_id=task_id, process=process, service=service, is_workflow=False,
                                      user_id=user_id, execute_async=True, access=access)
        job.status = status
        if status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_FINISHED]:
            job.mark_finished()
        job.progress = progress
        job = self.job_store.update_job(job)
        self.job_info.append(job)
        return job

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
            mock.patch("pyramid.security.AuthenticationAPIMixin.authenticated_userid", new_callable=lambda: user_id),
            mock.patch("pyramid.request.AuthorizationAPIMixin.has_permission", return_value=is_admin),
        ])

    @staticmethod
    def get_job_remote_service_mock(processes):
        # type: (List[Union[ProcessPyWPS, ProcessOWSWPS]]) -> Iterable[MockPatch]
        mock_processes = mock.PropertyMock
        mock_processes.return_value = processes
        return tuple([
            mock.patch.object(WebProcessingService, "getcapabilities", new=lambda *args, **kwargs: None),
            mock.patch.object(WebProcessingService, "processes", new_callable=mock_processes, create=True),
        ])

    @staticmethod
    def check_job_format(job):
        assert isinstance(job, dict)
        assert "jobID" in job and isinstance(job["jobID"], str)
        assert "status" in job and isinstance(job["status"], str)
        assert "message" in job and isinstance(job["message"], str)
        assert "percentCompleted" in job and isinstance(job["percentCompleted"], int)
        assert "logs" in job and isinstance(job["logs"], str)
        assert job["status"] in JOB_STATUS_VALUES
        if job["status"] == STATUS_SUCCEEDED:
            assert "result" in job and isinstance(job["result"], str)
        elif job["status"] == STATUS_FAILED:
            assert "exceptions" in job and isinstance(job["exceptions"], str)

    @staticmethod
    def check_basic_jobs_info(response):
        assert response.status_code == 200
        assert response.content_type == CONTENT_TYPE_APP_JSON
        assert "jobs" in response.json and isinstance(response.json["jobs"], list)
        assert "page" in response.json and isinstance(response.json["page"], int)
        assert "total" in response.json and isinstance(response.json["total"], int)
        assert "limit" in response.json and isinstance(response.json["limit"], int)
        assert len(response.json["jobs"]) <= response.json["limit"]
        assert response.json["page"] == response.json["total"] // response.json["limit"]

    @staticmethod
    def check_basic_jobs_grouped_info(response, groups):
        if isinstance(groups, str):
            groups = [groups]
        assert response.status_code == 200
        assert response.content_type == CONTENT_TYPE_APP_JSON
        assert "page" not in response.json
        assert "limit" not in response.json
        assert "total" in response.json and isinstance(response.json["total"], int)
        assert "groups" in response.json
        assert isinstance(response.json["groups"], list)
        total = 0
        for grouped_jobs in response.json["groups"]:
            assert "category" in grouped_jobs and isinstance(grouped_jobs["category"], dict)
            assert all(g in grouped_jobs["category"] for g in groups)
            assert len(set(groups) - set(grouped_jobs["category"])) == 0
            assert "jobs" in grouped_jobs and isinstance(grouped_jobs["jobs"], list)
            assert "count" in grouped_jobs and isinstance(grouped_jobs["count"], int)
            assert len(grouped_jobs["jobs"]) == grouped_jobs["count"]
            total += grouped_jobs["count"]
        assert total == response.json["total"]

    def test_get_jobs_normal_paged(self):
        resp = self.app.get(jobs_short_uri, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        for job_id in resp.json["jobs"]:
            assert isinstance(job_id, str)

        for detail in ("false", 0, "False", "no", "None", "null", None, ""):
            path = get_path_kvp(jobs_short_uri, detail=detail)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job_id in resp.json["jobs"]:
                assert isinstance(job_id, str)

    def test_get_jobs_detail_paged(self):
        for detail in ("true", 1, "True", "yes"):
            path = get_path_kvp(jobs_short_uri, detail=detail)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job in resp.json["jobs"]:
                self.check_job_format(job)

    def test_get_jobs_normal_grouped(self):
        for detail in ("false", 0, "False", "no"):
            groups = ["process", "service"]
            path = get_path_kvp(jobs_short_uri, detail=detail, groups=groups)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_grouped_info(resp, groups=groups)
            for grouped_jobs in resp.json["groups"]:
                for job in grouped_jobs["jobs"]:
                    assert isinstance(job, str)

    def test_get_jobs_detail_grouped(self):
        for detail in ("true", 1, "True", "yes"):
            groups = ["process", "service"]
            path = get_path_kvp(jobs_short_uri, detail=detail, groups=groups)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_grouped_info(resp, groups=groups)
            for grouped_jobs in resp.json["groups"]:
                for job in grouped_jobs["jobs"]:
                    self.check_job_format(job)

    def test_get_jobs_valid_grouping_by_process(self):
        path = get_path_kvp(jobs_short_uri, detail="false", groups="process")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_grouped_info(resp, groups="process")

        # ensure that group categories are distinct
        for i, grouped_jobs in enumerate(resp.json["groups"]):
            categories = grouped_jobs["category"]
            for j, grp_jobs in enumerate(resp.json["groups"]):
                compared = grp_jobs["category"]
                if i == j:
                    continue
                assert categories != compared

            # validate groups with expected jobs counts and ids (nb: only public jobs are returned)
            if categories["process"] == self.process_public.identifier:
                assert len(grouped_jobs["jobs"]) == 3
                assert set(grouped_jobs["jobs"]) == {self.job_info[0].id, self.job_info[5].id, self.job_info[7].id}
            elif categories["process"] == self.process_private.identifier:
                assert len(grouped_jobs["jobs"]) == 3
                assert set(grouped_jobs["jobs"]) == {self.job_info[2].id, self.job_info[6].id, self.job_info[8].id}
            elif categories["process"] == self.process_unknown:
                assert len(grouped_jobs["jobs"]) == 1
                assert set(grouped_jobs["jobs"]) == {self.job_info[1].id}
            else:
                pytest.fail("Unknown job grouping 'process' value not expected.")

    def test_get_jobs_valid_grouping_by_service(self):
        path = get_path_kvp(jobs_short_uri, detail="false", groups="service")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_grouped_info(resp, groups="service")

        # ensure that group categories are distinct
        for i, grouped_jobs in enumerate(resp.json["groups"]):
            categories = grouped_jobs["category"]
            for j, grp_jobs in enumerate(resp.json["groups"]):
                compared = grp_jobs["category"]
                if i == j:
                    continue
                assert categories != compared

            # validate groups with expected jobs counts and ids (nb: only public jobs are returned)
            if categories["service"] == self.service_public.name:
                assert len(grouped_jobs["jobs"]) == 3
                assert set(grouped_jobs["jobs"]) == {self.job_info[1].id, self.job_info[5].id, self.job_info[6].id}
            elif categories["service"] == self.service_private.name:
                assert len(grouped_jobs["jobs"]) == 2
                assert set(grouped_jobs["jobs"]) == {self.job_info[7].id, self.job_info[8].id}
            elif categories["service"] is None:
                assert len(grouped_jobs["jobs"]) == 2
                assert set(grouped_jobs["jobs"]) == {self.job_info[0].id, self.job_info[2].id}
            else:
                pytest.fail("Unknown job grouping 'service' value not expected.")

    def test_get_jobs_by_encrypted_email(self):
        """Verifies that literal email can be used as search criterion although not saved in plain text within db."""
        email = "some.test@crim.ca"
        body = {
            "inputs": [{"id": "test_input", "data": "test"}],
            "outputs": [{"id": "test_output", "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}],
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
            "notification_email": email
        }
        with contextlib.ExitStack() as stack:
            for runner in mocked_process_job_runner():
                stack.enter_context(runner)
            path = "/processes/{}/jobs".format(self.process_public.identifier)
            resp = self.app.post_json(path, params=body, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == CONTENT_TYPE_APP_JSON
        job_id = resp.json["jobID"]

        # verify the email is not in plain text
        job = self.job_store.fetch_by_id(job_id)
        assert job.notification_email != email and job.notification_email is not None
        assert int(job.notification_email, 16) != 0  # email should be encrypted with hex string

        path = get_path_kvp(jobs_short_uri, detail="true", notification_email=email)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["total"] == 1, "Should match exactly 1 email with specified literal string as query param."
        assert resp.json["jobs"][0]["jobID"] == job_id

    def test_get_jobs_process_in_query_normal(self):
        path = get_path_kvp(jobs_short_uri, process=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json["jobs"], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json["jobs"], self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_query_detail(self):
        path = get_path_kvp(jobs_short_uri, process=self.job_info[0].process, detail="true")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j["jobID"] for j in resp.json["jobs"]]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_path_normal(self):
        path = process_jobs_uri.format(process_id=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json["jobs"], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json["jobs"], self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_path_detail(self):
        path = process_jobs_uri.format(process_id=self.job_info[0].process) + "?detail=true"
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j["jobID"] for j in resp.json["jobs"]]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_unknown_in_path(self):
        path = process_jobs_uri.format(process_id="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_process_unknown_in_query(self):
        path = get_path_kvp(jobs_short_uri, process="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_process_unauthorized_in_path(self):
        path = process_jobs_uri.format(process_id=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_process_not_returned_in_query(self):
        path = get_path_kvp(jobs_short_uri, process=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_service_and_process_unknown_in_path(self):
        path = jobs_full_uri.format(provider_id="unknown-service-id", process_id="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_service_and_process_unknown_in_query(self):
        path = get_path_kvp(jobs_short_uri, service="unknown-service-id", process="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_service_public_process_unauthorized_in_path(self):
        path = jobs_full_uri.format(provider_id=self.service_private.name, process_id=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_service_public_process_unauthorized_in_query(self):
        path = get_path_kvp(jobs_short_uri,
                            service=self.service_private.name,
                            process=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_public_service_private_process_unauthorized_in_query(self):
        """
        NOTE:
            it is up to the remote service to hide private processes
            if the process is visible, the a job can be executed and it is automatically considered public
        """
        path = get_path_kvp(jobs_short_uri,
                            service=self.service_public.name,
                            process=self.process_private.identifier)
        with contextlib.ExitStack() as stack:
            for runner in self.get_job_remote_service_mock([self.process_private]):  # process visible on remote
                stack.enter_context(runner)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 200
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_public_service_no_processes(self):
        """
        NOTE:
            it is up to the remote service to hide private processes
            if the process is invisible, no job should have been executed nor can be fetched
        """
        path = get_path_kvp(jobs_short_uri,
                            service=self.service_public.name,
                            process=self.process_private.identifier)
        with contextlib.ExitStack() as stack:
            for job in self.get_job_remote_service_mock([]):    # process invisible (not returned by remote)
                stack.enter_context(job)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 404
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_public_with_access_and_request_user(self):
        """Verifies that corresponding processes are returned when proper access/user-id are respected."""
        uri_direct_jobs = jobs_short_uri
        uri_process_jobs = process_jobs_uri.format(process_id=self.process_public.identifier)
        uri_provider_jobs = jobs_full_uri.format(
            provider_id=self.service_public.name, process_id=self.process_public.identifier)

        admin_public_jobs = list(filter(lambda j: VISIBILITY_PUBLIC in j.access, self.job_info))
        admin_private_jobs = list(filter(lambda j: VISIBILITY_PRIVATE in j.access, self.job_info))
        editor1_all_jobs = list(filter(lambda j: j.user_id == self.user_editor1_id, self.job_info))
        editor1_public_jobs = list(filter(lambda j: VISIBILITY_PUBLIC in j.access, editor1_all_jobs))
        editor1_private_jobs = list(filter(lambda j: VISIBILITY_PRIVATE in j.access, editor1_all_jobs))
        public_jobs = list(filter(lambda j: VISIBILITY_PUBLIC in j.access, self.job_info))

        def filter_process(jobs):  # type: (Iterable[Job]) -> List[Job]
            return list(filter(lambda j: j.process == self.process_public.identifier, jobs))

        def filter_service(jobs):  # type: (Iterable[Job]) -> List[Job]
            return list(filter(lambda j: j.service == self.service_public.name, jobs))

        # test variations of [paths, query, user-id, expected-job-ids]
        path_jobs_user_req_tests = [
            # pylint: disable=C0301,line-too-long
            # URI               ACCESS              USER                    EXPECTED JOBS
            (uri_direct_jobs,   None,               None,                   public_jobs),                               # noqa: E241,E501
            (uri_direct_jobs,   None,               self.user_editor1_id,   editor1_all_jobs),                          # noqa: E241,E501
            (uri_direct_jobs,   None,               self.user_admin_id,     self.job_info),                             # noqa: E241,E501
            (uri_direct_jobs,   VISIBILITY_PRIVATE, None,                   public_jobs),                               # noqa: E241,E501
            (uri_direct_jobs,   VISIBILITY_PRIVATE, self.user_editor1_id,   editor1_private_jobs),                      # noqa: E241,E501
            (uri_direct_jobs,   VISIBILITY_PRIVATE, self.user_admin_id,     admin_private_jobs),                        # noqa: E241,E501
            (uri_direct_jobs,   VISIBILITY_PUBLIC,  None,                   public_jobs),                               # noqa: E241,E501
            (uri_direct_jobs,   VISIBILITY_PUBLIC,  self.user_editor1_id,   editor1_public_jobs),                       # noqa: E241,E501
            (uri_direct_jobs,   VISIBILITY_PUBLIC,  self.user_admin_id,     admin_public_jobs),                         # noqa: E241,E501
            # ---
            (uri_process_jobs,  None,               None,                   filter_process(public_jobs)),               # noqa: E241,E501
            (uri_process_jobs,  None,               self.user_editor1_id,   filter_process(editor1_all_jobs)),          # noqa: E241,E501
            (uri_process_jobs,  None,               self.user_admin_id,     filter_process(self.job_info)),             # noqa: E241,E501
            (uri_process_jobs,  VISIBILITY_PRIVATE, None,                   filter_process(public_jobs)),               # noqa: E241,E501
            (uri_process_jobs,  VISIBILITY_PRIVATE, self.user_editor1_id,   filter_process(editor1_private_jobs)),      # noqa: E241,E501
            (uri_process_jobs,  VISIBILITY_PRIVATE, self.user_admin_id,     filter_process(admin_private_jobs)),        # noqa: E241,E501
            (uri_process_jobs,  VISIBILITY_PUBLIC,  None,                   filter_process(public_jobs)),               # noqa: E241,E501
            (uri_process_jobs,  VISIBILITY_PUBLIC,  self.user_editor1_id,   filter_process(editor1_public_jobs)),       # noqa: E241,E501
            (uri_process_jobs,  VISIBILITY_PUBLIC,  self.user_admin_id,     filter_process(self.job_info)),             # noqa: E241,E501
            # ---
            (uri_provider_jobs, None,               None,                   filter_service(public_jobs)),               # noqa: E241,E501
            (uri_provider_jobs, None,               self.user_editor1_id,   filter_service(editor1_all_jobs)),          # noqa: E241,E501
            (uri_provider_jobs, None,               self.user_admin_id,     filter_service(self.job_info)),             # noqa: E241,E501
            (uri_provider_jobs, VISIBILITY_PRIVATE, None,                   filter_service(public_jobs)),               # noqa: E241,E501
            (uri_provider_jobs, VISIBILITY_PRIVATE, self.user_editor1_id,   filter_service(editor1_private_jobs)),      # noqa: E241,E501
            (uri_provider_jobs, VISIBILITY_PRIVATE, self.user_admin_id,     filter_service(admin_private_jobs)),        # noqa: E241,E501
            (uri_provider_jobs, VISIBILITY_PUBLIC,  None,                   filter_service(public_jobs)),               # noqa: E241,E501
            (uri_provider_jobs, VISIBILITY_PUBLIC,  self.user_editor1_id,   filter_service(editor1_public_jobs)),       # noqa: E241,E501
            (uri_provider_jobs, VISIBILITY_PUBLIC,  self.user_admin_id,     filter_service(self.job_info)),             # noqa: E241,E501

        ]   # type: List[Tuple[str, str, Union[None, int], List[Job]]]

        for i, (path, access, user_id, expected_jobs) in enumerate(path_jobs_user_req_tests):
            with contextlib.ExitStack() as stack:
                for patch in self.get_job_request_auth_mock(user_id):
                    stack.enter_context(patch)
                for patch in self.get_job_remote_service_mock([self.process_public]):
                    stack.enter_context(patch)
                test = get_path_kvp(path, access=access) if access else path
                resp = self.app.get(test, headers=self.json_headers)
                self.check_basic_jobs_info(resp)
                job_ids = [job.id for job in expected_jobs]
                job_match = all(job in job_ids for job in resp.json["jobs"])
                test_values = dict(path=path, access=access, user_id=user_id)
                assert job_match, self.message_with_jobs_diffs(resp.json["jobs"], job_ids, test_values, index=i)
