import contextlib
import datetime
import logging
import os
import shutil
import tempfile
import unittest
import warnings
from datetime import date
from distutils.version import LooseVersion
from typing import TYPE_CHECKING

import colander
import mock
import pyramid.testing
import pytest
from dateutil import parser as date_parser
from parameterized import parameterized

from tests.functional.utils import JobUtils
from tests.resources import load_example
from tests.utils import (
    get_links,
    get_module_version,
    get_test_weaver_app,
    mocked_dismiss_process,
    mocked_process_job_runner,
    mocked_remote_wps,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver.datatype import Job, Service
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentType
from weaver.processes.wps_testing import WpsTestProcess
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory
from weaver.utils import get_path_kvp, now
from weaver.visibility import Visibility
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.swagger_definitions import (
    DATETIME_INTERVAL_CLOSED_SYMBOL,
    DATETIME_INTERVAL_OPEN_END_SYMBOL,
    DATETIME_INTERVAL_OPEN_START_SYMBOL
)

if TYPE_CHECKING:
    from typing import Iterable, List, Optional, Tuple, Union

    from weaver.status import AnyStatusType
    from weaver.typedefs import JSON, AnyLogLevel, Number, Statistics
    from weaver.visibility import AnyVisibility


class WpsRestApiJobsTest(unittest.TestCase, JobUtils):
    settings = {}
    config = None

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", TimeZoneInfoAlreadySetWarning)
        cls.settings = {
            "weaver.url": "https://localhost",
            "weaver.wps_email_encrypt_salt": "weaver-test",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        cls.config = setup_config_with_mongodb(settings=cls.settings)
        cls.app = get_test_weaver_app(config=cls.config)
        cls.json_headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
        cls.datetime_interval = cls.generate_test_datetimes()

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
        self.process_store.set_visibility(self.process_public.identifier, Visibility.PUBLIC)
        self.process_private = WpsTestProcess(identifier="process-private")
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_private.identifier, Visibility.PRIVATE)
        self.process_other = WpsTestProcess(identifier="process-other")
        self.process_store.save_process(self.process_other)
        self.process_store.set_visibility(self.process_other.identifier, Visibility.PUBLIC)
        self.process_unknown = "process-unknown"

        self.service_public = Service(name="service-public", url="http://localhost/wps/service-public", public=True)
        self.service_store.save_service(self.service_public)
        self.service_private = Service(name="service-private", url="http://localhost/wps/service-private", public=False)
        self.service_store.save_service(self.service_private)

        self.service_one = Service(name="service-one", url="http://localhost/wps/service-one", public=True)
        self.service_store.save_service(self.service_one)
        self.service_two = Service(name="service-two", url="http://localhost/wps/service-two", public=True)
        self.service_store.save_service(self.service_two)

        # create jobs accessible by index
        self.job_info = []  # type: List[Job]
        self.make_job(task_id="0000-0000-0000-0000",
                      process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=Status.SUCCEEDED, progress=100, access=Visibility.PUBLIC,
                      tags=["unique"],
                      logs=[
                          ("Start", logging.INFO, Status.ACCEPTED, 1),
                          ("Process", logging.INFO, Status.RUNNING, 10),
                          ("Complete", logging.INFO, Status.SUCCEEDED, 100)
                      ])
        self.make_job(task_id="0000-0000-0000-1111",
                      process=self.process_unknown, service=self.service_public.name, tags=["test-two", "other"],
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-0000-2222",
                      process=self.process_private.identifier, service=None, tags=["test-two"],
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=55, access=Visibility.PUBLIC)
        # same process as job 0, but private (ex: job ran with private process, then process made public afterwards)
        self.make_job(task_id="0000-0000-0000-3333",
                      process=self.process_public.identifier, service=None,
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=55, access=Visibility.PRIVATE)
        # job ran by admin
        self.make_job(task_id="0000-0000-0000-4444",
                      process=self.process_public.identifier, service=None,
                      user_id=self.user_admin_id, status=Status.FAILED, progress=55, access=Visibility.PRIVATE)
        # job public/private service/process combinations
        self.make_job(task_id="0000-0000-0000-5555", created=self.datetime_interval[0], duration=20,
                      process=self.process_public.identifier, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-0000-6666", created=self.datetime_interval[1], duration=30,
                      process=self.process_private.identifier, service=self.service_public.name,
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-0000-7777", created=self.datetime_interval[2], duration=40,
                      process=self.process_public.identifier, service=self.service_private.name,
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-0000-8888", created=self.datetime_interval[3], duration=50,
                      process=self.process_private.identifier, service=self.service_private.name,
                      user_id=self.user_editor1_id, status=Status.FAILED, progress=99, access=Visibility.PUBLIC)
        # jobs with duplicate 'process' identifier, but under a different 'service' name
        # WARNING:
        #   For tests that use minDuration/maxDuration, following two jobs could 'eventually' become more/less than
        #   expected test values while debugging (code breakpoints) since their duration is dynamic (current - started)
        self.make_job(task_id="0000-0000-0000-9999", created=now(), duration=20,
                      process=self.process_other.identifier, service=self.service_one.name,
                      user_id=self.user_editor1_id, status=Status.RUNNING, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-1111-0000", created=now(), duration=25,
                      process=self.process_other.identifier, service=self.service_two.name,
                      user_id=self.user_editor1_id, status=Status.RUNNING, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-2222-0000", created=now(), duration=0,
                      process=self.process_other.identifier, service=self.service_two.name,
                      user_id=self.user_editor1_id, status=Status.ACCEPTED, progress=99, access=Visibility.PUBLIC)
        self.make_job(task_id="0000-0000-3333-0000", created=now(), duration=0,
                      process=self.process_other.identifier, service=self.service_two.name,
                      user_id=self.user_editor1_id, status=Status.STARTED, progress=99, access=Visibility.PUBLIC)

    def make_job(self,
                 task_id,           # type: str
                 process,           # type: str
                 service,           # type: Optional[str]
                 user_id,           # type: Optional[int]
                 status,            # type: AnyStatusType
                 progress,          # type: int
                 access,            # type: AnyVisibility
                 created=None,      # type: Optional[Union[datetime.datetime, str]]
                 offset=None,       # type: Optional[int]
                 duration=None,     # type: Optional[int]
                 exceptions=None,   # type: Optional[List[JSON]]
                 logs=None,         # type: Optional[List[Union[str, Tuple[str, AnyLogLevel, AnyStatusType, Number]]]]
                 statistics=None,   # type: Optional[Statistics]
                 tags=None,         # type: Optional[List[str]]
                 add_info=True,     # type: bool
                 ):                 # type: (...) -> Job
        if isinstance(created, str):
            created = date_parser.parse(created)
        job = self.job_store.save_job(task_id=task_id, process=process, service=service, is_workflow=False,
                                      user_id=user_id, execute_async=True, access=access, created=created)
        job.status = status
        if status != Status.ACCEPTED:
            job.started = job.created + datetime.timedelta(seconds=offset if offset is not None else 0)
        job.updated = job.created + datetime.timedelta(seconds=duration if duration is not None else 10)
        if status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            job["finished"] = job.updated
        job.progress = progress
        if logs is not None:
            for log_item in logs:
                if isinstance(log_item, tuple):
                    job.save_log(message=log_item[0], level=log_item[1], status=log_item[2], progress=log_item[3])
                else:
                    job.save_log(message=log_item)
        if exceptions is not None:
            job.exceptions = exceptions
        if statistics is not None:
            job.statistics = statistics
        if tags is not None:
            job.tags = tags
        job = self.job_store.update_job(job)
        if add_info:
            self.job_info.append(job)
        return job

    def get_job_request_auth_mock(self, user_id):
        is_admin = self.user_admin_id == user_id
        if LooseVersion(get_module_version("pyramid")) >= LooseVersion("2"):
            authn_policy_class = "pyramid.security.SecurityAPIMixin"
            authz_policy_class = "pyramid.security.SecurityAPIMixin"
        else:
            authn_policy_class = "pyramid.security.AuthenticationAPIMixin"
            authz_policy_class = "pyramid.security.AuthorizationAPIMixin"
        return tuple([
            mock.patch(f"{authn_policy_class}.authenticated_userid", new_callable=lambda: user_id),
            mock.patch(f"{authz_policy_class}.has_permission", return_value=is_admin),
        ])

    @staticmethod
    def generate_test_datetimes():
        # type: () -> List[str]
        """
        Generates a list of dummy datetimes for testing.
        """
        # tests create jobs with datetime auto-resolved relative to 'now' with local timezone-awareness
        # must apply the same UTC offset as the local machine timezone for proper search results with datetime filters
        local_iso_dt = datetime.datetime.now(datetime.datetime.now().astimezone().tzinfo).isoformat()
        local_offset = local_iso_dt[-6:]  # ±00:00
        year = date.today().year + 1
        return [f"{year}-0{month}-02T03:32:38.487000{local_offset}" for month in range(1, 5)]

    @staticmethod
    def check_job_format(job):
        assert isinstance(job, dict)
        assert "jobID" in job and isinstance(job["jobID"], str)
        assert "status" in job and isinstance(job["status"], str)
        assert "message" in job and isinstance(job["message"], str)
        assert "percentCompleted" in job and isinstance(job["percentCompleted"], int)
        assert "links" in job and isinstance(job["links"], list) and len(job["links"])
        assert all(isinstance(link_info, dict) for link_info in job["links"])
        assert all(any(link_info["rel"] == rel for link_info in job["links"]) for rel in ["self", "logs"])
        for link_info in job["links"]:
            assert "href" in link_info and isinstance(link_info["href"], str)
        assert job["status"] in Status.values()
        if job["status"] == Status.SUCCEEDED:
            assert len([link for link in job["links"] if link["rel"].endswith("results")])
        elif job["status"] == Status.FAILED:
            assert len([link for link in job["links"] if link["rel"].endswith("exceptions")])

    @staticmethod
    def check_basic_jobs_info(response, message=""):
        assert response.status_code == 200, message
        assert response.content_type == ContentType.APP_JSON
        assert "jobs" in response.json and isinstance(response.json["jobs"], list)
        assert "page" in response.json and isinstance(response.json["page"], int)
        assert "total" in response.json and isinstance(response.json["total"], int)
        assert "limit" in response.json and isinstance(response.json["limit"], int)
        assert len(response.json["jobs"]) <= response.json["limit"]

    @staticmethod
    def check_basic_jobs_grouped_info(response, groups):
        if isinstance(groups, str):
            groups = [groups]
        assert response.status_code == 200
        assert response.content_type == ContentType.APP_JSON
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
        resp = self.app.get(sd.jobs_service.path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        for job_id in resp.json["jobs"]:
            assert isinstance(job_id, str)

        for detail in ("false", 0, "False", "no", "None", "null", None, ""):
            path = get_path_kvp(sd.jobs_service.path, detail=detail)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
            for job_id in resp.json["jobs"]:
                assert isinstance(job_id, str)

    def test_get_jobs_detail_paged(self):
        for detail in ("true", 1, "True", "yes"):
            path = get_path_kvp(sd.jobs_service.path, detail=detail)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            self.check_basic_jobs_info(resp, f"Test: detail={detail}")
            for job in resp.json["jobs"]:
                self.check_job_format(job)

    def test_get_jobs_normal_grouped(self):
        for detail in ("false", 0, "False", "no"):
            groups = ["process", "service"]
            path = get_path_kvp(sd.jobs_service.path, detail=detail, groups=groups)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_grouped_info(resp, groups=groups)
            for grouped_jobs in resp.json["groups"]:
                for job in grouped_jobs["jobs"]:
                    assert isinstance(job, str)

    def test_get_jobs_detail_grouped(self):
        for detail in ("true", 1, "True", "yes"):
            groups = ["process", "service"]
            path = get_path_kvp(sd.jobs_service.path, detail=detail, groups=groups)
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_grouped_info(resp, groups=groups)
            for grouped_jobs in resp.json["groups"]:
                for job in grouped_jobs["jobs"]:
                    self.check_job_format(job)

    def test_get_jobs_valid_grouping_by_process(self):
        path = get_path_kvp(sd.jobs_service.path, detail="false", groups="process")
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
                expect = {self.job_info[0].id, self.job_info[5].id, self.job_info[7].id}
            elif categories["process"] == self.process_private.identifier:
                expect = {self.job_info[2].id, self.job_info[6].id, self.job_info[8].id}
            elif categories["process"] == self.process_unknown:
                expect = {self.job_info[1].id}
            elif categories["process"] == self.process_other.identifier:
                expect = {self.job_info[i].id for i in [9, 10, 11, 12]}
            else:
                cat = categories["process"]
                pytest.fail(f"Unknown job grouping 'process' value: {cat}")
            self.assert_equal_with_jobs_diffs(grouped_jobs["jobs"], expect)  # noqa

    def template_get_jobs_valid_grouping_by_service_provider(self, service_or_provider):
        path = get_path_kvp(sd.jobs_service.path, detail="false", groups=service_or_provider)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_grouped_info(resp, groups=service_or_provider)

        # ensure that group categories are distinct
        for i, grouped_jobs in enumerate(resp.json["groups"]):
            categories = grouped_jobs["category"]
            for j, grp_jobs in enumerate(resp.json["groups"]):
                compared = grp_jobs["category"]
                if i == j:
                    continue
                assert categories != compared

            # validate groups with expected jobs counts and ids (nb: only public jobs are returned)
            if categories[service_or_provider] == self.service_public.name:
                expect = {self.job_info[1].id, self.job_info[5].id, self.job_info[6].id}
            elif categories[service_or_provider] == self.service_private.name:
                expect = {self.job_info[7].id, self.job_info[8].id}
            elif categories[service_or_provider] == self.service_one.name:
                expect = {self.job_info[9].id}
            elif categories[service_or_provider] == self.service_two.name:
                expect = {self.job_info[10].id, self.job_info[11].id, self.job_info[12].id}
            elif categories[service_or_provider] is None:
                expect = {self.job_info[0].id, self.job_info[2].id}
            else:
                cat = categories[service_or_provider]
                pytest.fail(f"Unknown job grouping 'service' value: {cat}")
            self.assert_equal_with_jobs_diffs(grouped_jobs["jobs"], expect)  # noqa

    def test_get_jobs_valid_grouping_by_service(self):
        self.template_get_jobs_valid_grouping_by_service_provider("service")

    def test_get_jobs_valid_grouping_by_provider(self):
        """
        Grouping by ``provider`` must work as alias to ``service`` and must be adjusted inplace in response categories.
        """
        self.template_get_jobs_valid_grouping_by_service_provider("provider")

    def test_get_jobs_links_navigation(self):
        """
        Verifies that relation links update according to context in order to allow natural navigation between responses.
        """
        expect_jobs_total = len(self.job_info)
        expect_jobs_visible = len(list(filter(lambda j: Visibility.PUBLIC in j.access, self.job_info)))
        assert len(self.job_store.list_jobs()) == expect_jobs_total, (
            "expected number of jobs mismatch, following test might not work"
        )
        path = get_path_kvp(sd.jobs_service.path, limit=1000)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["jobs"]) == expect_jobs_visible, "unexpected number of visible jobs"

        base_url = self.settings["weaver.url"]
        jobs_url = base_url + sd.jobs_service.path
        limit = 2  # expect 11 jobs to be visible, making 6 pages of 2 each (except last that is 1)
        last = 5   # zero-based index of last page
        last_page = f"page={last}"
        prev_last_page = f"page={last - 1}"
        limit_kvp = f"limit={limit}"
        path = get_path_kvp(sd.jobs_service.path, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
        assert resp.json["total"] == expect_jobs_visible
        assert len(resp.json["jobs"]) == limit
        assert links["alternate"] is None
        assert links["collection"] == jobs_url
        assert links["search"] == jobs_url
        assert links["up"] is None, "generic jobs endpoint doesn't have any parent collection"
        assert links["current"].startswith(jobs_url) and limit_kvp in links["current"] and "page=0" in links["current"]
        assert links["prev"] is None, "no previous on first page (default page=0 used)"
        assert links["next"].startswith(jobs_url) and limit_kvp in links["next"] and "page=1" in links["next"]
        assert links["first"].startswith(jobs_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(jobs_url) and limit_kvp in links["last"] and last_page in links["last"]

        path = get_path_kvp(sd.jobs_service.path, limit=limit, page=2)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
        assert len(resp.json["jobs"]) == limit
        assert links["alternate"] is None
        assert links["collection"] == jobs_url
        assert links["search"] == jobs_url
        assert links["up"] is None, "generic jobs endpoint doesn't have any parent collection"
        assert links["current"].startswith(jobs_url) and limit_kvp in links["current"] and "page=2" in links["current"]
        assert links["prev"].startswith(jobs_url) and limit_kvp in links["prev"] and "page=1" in links["prev"]
        assert links["next"].startswith(jobs_url) and limit_kvp in links["next"] and "page=3" in links["next"]
        assert links["first"].startswith(jobs_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(jobs_url) and limit_kvp in links["last"] and last_page in links["last"]

        path = get_path_kvp(sd.jobs_service.path, limit=limit, page=last)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
        assert len(resp.json["jobs"]) == 1, "last page should show only remaining jobs within limit"
        assert links["alternate"] is None
        assert links["collection"] == jobs_url
        assert links["search"] == jobs_url
        assert links["up"] is None, "generic jobs endpoint doesn't have any parent collection"
        assert links["current"].startswith(jobs_url) and limit_kvp in links["current"] and last_page in links["current"]
        assert links["prev"].startswith(jobs_url) and limit_kvp in links["prev"] and prev_last_page in links["prev"]
        assert links["next"] is None, "no next page on last"
        assert links["first"].startswith(jobs_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(jobs_url) and limit_kvp in links["last"] and last_page in links["last"]

        p_id = self.process_public.identifier  # 5 jobs with this process, but only 3 visible
        p_j_url = base_url + sd.process_jobs_service.path.format(process_id=p_id)
        p_url = base_url + sd.process_service.path.format(process_id=p_id)
        p_kvp = f"process={p_id}"
        path = get_path_kvp(sd.jobs_service.path, limit=1000, process=p_id)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["jobs"]) == 3, "unexpected number of visible jobs for specific process"

        path = get_path_kvp(sd.jobs_service.path, limit=limit, page=1, process=p_id)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
        assert len(resp.json["jobs"]) == 1, "last page should show only remaining jobs within limit"
        assert links["alternate"].startswith(p_j_url) and p_kvp not in links["alternate"]
        assert limit_kvp in links["alternate"] and "page=1" in links["alternate"], "alt link should also have filters"
        assert links["collection"] == jobs_url
        assert links["search"] == jobs_url
        assert links["up"] == p_url, "parent path should be indirectly pointing at process description from alt link"
        assert links["current"].startswith(jobs_url) and limit_kvp in links["current"] and "page=1" in links["current"]
        assert links["prev"].startswith(jobs_url) and limit_kvp in links["prev"] and "page=0" in links["prev"]
        assert links["next"] is None
        assert links["first"].startswith(jobs_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(jobs_url) and limit_kvp in links["last"] and "page=1" in links["last"]
        assert all(p_kvp in links[rel] for rel in ["current", "next", "prev", "first", "last"] if links[rel])

        path = get_path_kvp(sd.process_jobs_service.path.format(process_id=p_id), limit=limit, page=0)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
        assert len(resp.json["jobs"]) == limit
        assert links["alternate"].startswith(jobs_url) and f"process={p_id}" in links["alternate"]
        assert limit_kvp in links["alternate"] and "page=0" in links["alternate"], "alt link should also have filters"
        assert links["collection"] == p_j_url, "collection endpoint should rebase according to context process"
        assert links["search"] == jobs_url, "search endpoint should remain generic jobs even with context process used"
        assert links["up"] == p_url, "parent path should be directly pointing at process description"
        assert links["current"].startswith(p_j_url) and limit_kvp in links["current"] and "page=0" in links["current"]
        assert links["prev"] is None
        assert links["next"].startswith(p_j_url) and limit_kvp in links["next"] and "page=1" in links["next"]
        assert links["first"].startswith(p_j_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(p_j_url) and limit_kvp in links["last"] and "page=1" in links["last"]
        assert all(p_kvp not in links[rel] for rel in ["current", "next", "prev", "first", "last"] if links[rel])

        limit_over_total = expect_jobs_visible * 2
        limit_kvp = f"limit={limit_over_total}"
        path = get_path_kvp(sd.jobs_service.path, limit=limit_over_total)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
        assert len(resp.json["jobs"]) == expect_jobs_visible
        assert links["alternate"] is None
        assert links["collection"] == jobs_url
        assert links["search"] == jobs_url
        assert links["up"] is None, "generic jobs endpoint doesn't have any parent collection"
        assert links["current"].startswith(jobs_url) and limit_kvp in links["current"] and "page=0" in links["current"]
        assert links["prev"] is None, "no previous on first page (default page=0 used)"
        assert links["next"] is None, "no next page on last"
        assert links["first"].startswith(jobs_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(jobs_url) and limit_kvp in links["last"] and "page=0" in links["last"]

    def test_get_jobs_page_out_of_range(self):
        resp = self.app.get(sd.jobs_service.path, headers=self.json_headers)
        total = resp.json["total"]
        limit = total // 2
        max_limit = 1 if 2 * limit == total else 2  # exact match or last page remainder
        bad_page = 4

        path = get_path_kvp(sd.jobs_service.path, page=bad_page, limit=limit)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "JobInvalidParameter"
        assert "IndexError" in resp.json["error"]
        assert f"[0,{max_limit}]" in resp.json["description"]
        assert "page" in resp.json["value"] and resp.json["value"]["page"] == bad_page

        # note:
        #   Following errors are generated by schema validators (page min=0, limit min=1) rather than above explicit
        #   checks. They don't provide the range because the error can apply to more than just paging failing value
        #   is still explicitly reported though. Because comparisons happen at query param level, it reports str values.

        path = get_path_kvp(sd.jobs_service.path, page=-1, limit=limit)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "JobInvalidParameter"
        assert "page" in str(resp.json["cause"]) and "less than minimum" in str(resp.json["cause"])
        assert "page" in resp.json["value"] and resp.json["value"]["page"] == str(-1)

        path = get_path_kvp(sd.jobs_service.path, page=0, limit=0)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "JobInvalidParameter"
        assert "limit" in str(resp.json["cause"]) and "less than minimum" in str(resp.json["cause"])
        assert "limit" in resp.json["value"] and resp.json["value"]["limit"] == str(0)

    def test_get_jobs_by_encrypted_email(self):
        """
        Verifies that literal email can be used as search criterion although not saved in plain text within db.
        """
        email = "some.test@crim.ca"
        body = {
            "inputs": [{"id": "test_input", "data": "test"}],
            "outputs": [{"id": "test_output", "transmissionMode": ExecuteTransmissionMode.VALUE}],
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "notification_email": email
        }
        with contextlib.ExitStack() as stack:
            for runner in mocked_process_job_runner():
                stack.enter_context(runner)
            path = f"/processes/{self.process_public.identifier}/jobs"
            resp = self.app.post_json(path, params=body, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == ContentType.APP_JSON
        job_id = resp.json["jobID"]

        # verify the email is not in plain text
        job = self.job_store.fetch_by_id(job_id)
        assert job.notification_email != email and job.notification_email is not None
        assert int(job.notification_email, 16) != 0  # email should be encrypted with hex string

        path = get_path_kvp(sd.jobs_service.path, detail="true", notification_email=email)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["total"] == 1, "Should match exactly 1 email with specified literal string as query param."
        assert resp.json["jobs"][0]["jobID"] == job_id

    def test_get_jobs_by_type_process(self):
        path = get_path_kvp(sd.jobs_service.path, type="process")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        expect_jobs = [self.job_info[i].id for i in [0, 2]]  # idx=2 & idx>4 have 'service', only 0,2 are public
        result_jobs = resp.json["jobs"]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        assert resp.json["total"] == len(expect_jobs)

    def test_get_jobs_by_type_process_and_specific_process_id(self):
        path = get_path_kvp(sd.jobs_service.path, type="process", process=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert len(resp.json["jobs"]) == 1
        expect_jobs = [self.job_info[0].id]
        result_jobs = resp.json["jobs"]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, message="expected only matching process")

    def test_get_jobs_by_type_process_and_specific_service_name(self):
        """
        Requesting provider ``type`` with a specific ``process`` identifier cannot yield any valid result (contradicts).

        .. seealso::
            Test :meth:`test_get_jobs_by_type_process_and_specific_process_id` that contains a valid match otherwise
            for the given process identifier.
        """
        path = get_path_kvp(sd.jobs_service.path, type="process", provider=self.service_public.name)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert "value" in resp.json and resp.json["value"] == {"type": "process", "service": self.service_public.name}

    def template_get_jobs_by_type_service_provider(self, service_or_provider):
        path = get_path_kvp(sd.jobs_service.path, type=service_or_provider)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        expect_jobs = [self.job_info[i].id for i in [1, 5, 6, 7, 8, 9]]  # has 'service' & public access
        result_jobs = resp.json["jobs"]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        assert resp.json["total"] == len(expect_jobs)

    def template_get_jobs_by_type_service(self):
        self.template_get_jobs_by_type_service_provider("service")

    def template_get_jobs_by_type_provider(self):
        self.template_get_jobs_by_type_service_provider("provider")

    def test_get_jobs_by_type_provider_and_specific_service_name(self):
        path = get_path_kvp(sd.jobs_service.path, type="provider", provider=self.service_public.name)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        expect_jobs = [self.job_info[i].id for i in [1, 5, 6]]  # has 'service' & public access, others not same name
        result_jobs = resp.json["jobs"]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        assert resp.json["total"] == len(expect_jobs)

    def test_get_jobs_by_type_provider_and_specific_process_id(self):
        """
        Requesting provider ``type`` with more specific ``process`` identifier further filters result.

        .. note::
            Technically, two distinct providers could employ the same sub-process identifier.
            Should not impact nor create a conflict here.

        Test :meth:`test_get_jobs_by_type_provider` should return more results since no sub-process filtering.

        Extra process from another provider than in :meth:`test_get_jobs_by_type_provider_and_specific_service_name`
        should now be returned as well.

        .. seealso::
            - :meth:`test_get_jobs_by_type_provider`
            - :meth:`test_get_jobs_by_type_provider_and_specific_service_name`
        """
        path = get_path_kvp(sd.jobs_service.path, type="provider", process=self.process_other.identifier, detail=True)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        expect_jobs = [self.job_info[i].id for i in [9, 10, 11, 12]]
        result_jobs = [job["jobID"] for job in resp.json["jobs"]]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        assert resp.json["total"] == len(expect_jobs)
        for job in resp.json["jobs"]:
            assert job["processID"] == self.process_other.identifier
            if job["jobID"] == self.job_info[9].id:
                assert job["providerID"] == self.service_one.name
            if job["jobID"] == self.job_info[10].id:
                assert job["providerID"] == self.service_two.name

    def test_get_jobs_process_in_query_normal(self):
        path = get_path_kvp(sd.jobs_service.path, process=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[0].id, self.job_info[5].id, self.job_info[7].id]
        invert_jobs = [self.job_info[1].id]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        self.assert_equal_with_jobs_diffs(invert_jobs, expect_jobs, invert=True)

    def test_get_jobs_process_in_query_detail(self):
        path = get_path_kvp(sd.jobs_service.path, process=self.job_info[0].process, detail="true")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        result_jobs = [job["jobID"] for job in resp.json["jobs"]]
        expect_jobs = [self.job_info[0].id, self.job_info[5].id, self.job_info[7].id]
        invert_jobs = [self.job_info[1].id]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        self.assert_equal_with_jobs_diffs(invert_jobs, expect_jobs, invert=True)

    def test_get_jobs_process_in_path_normal(self):
        path = sd.process_jobs_service.path.format(process_id=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[0].id, self.job_info[5].id, self.job_info[7].id]
        invert_jobs = [self.job_info[1].id]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        self.assert_equal_with_jobs_diffs(invert_jobs, expect_jobs, invert=True)

    def test_get_jobs_process_in_path_detail(self):
        path = sd.process_jobs_service.path.format(process_id=self.job_info[0].process) + "?detail=true"
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        result_jobs = [job["jobID"] for job in resp.json["jobs"]]
        expect_jobs = [self.job_info[0].id, self.job_info[5].id, self.job_info[7].id]
        invert_jobs = [self.job_info[1].id]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs)
        self.assert_equal_with_jobs_diffs(invert_jobs, expect_jobs, invert=True)

    def test_get_jobs_process_unknown_in_path(self):
        path = sd.process_jobs_service.path.format(process_id="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_process_unknown_in_query(self):
        path = get_path_kvp(sd.jobs_service.path, process="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON

    @parameterized.expand([
        get_path_kvp(
            sd.jobs_service.path,
            process="process-1", processID="process-2",
        ),
        get_path_kvp(
            sd.process_jobs_service.path.format(process_id="process-1"),
            process="process-2",
        ),
        get_path_kvp(
            sd.process_jobs_service.path.format(process_id="process-1"),
            process="process-1", processID="process-2",
        ),
        get_path_kvp(
            sd.process_jobs_service.path.format(process_id="process-2"),
            process="process-1", processID="process-1",
        ),
        get_path_kvp(
            sd.provider_jobs_service.path.format(provider_id="provider-1", process_id="process-1"),
            process="process-2",
        ),
        get_path_kvp(
            sd.provider_jobs_service.path.format(provider_id="provider-1", process_id="process-1"),
            process="process-1", processID="process-2",
        ),
        get_path_kvp(
            sd.provider_jobs_service.path.format(provider_id="provider-1", process_id="process-2"),
            process="process-1", processID="process-1",
        ),
        get_path_kvp(
            sd.provider_jobs_service.path.format(provider_id="provider-1", process_id="process-1"),
            provider="provider-2",
        ),
        get_path_kvp(
            sd.provider_jobs_service.path.format(provider_id="provider-1", process_id="process-1"),
            service="provider-2",
        ),
    ])
    def test_get_jobs_process_or_service_mismatch_in_path_or_query(self, path):
        # type: (str) -> None
        """
        Validate mismatching references.

        When :term:`Process` or :term:`Service` references are respectively provided in path/query simultaneously,
        but their values mismatch, an error should be raised immediately since we cannot resolve which one to use.
        """
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == ContentType.APP_JSON

    @parameterized.expand([
        get_path_kvp(sd.jobs_service.path, process="process-1:invalid!!!"),
        get_path_kvp(sd.jobs_service.path, process="process-1:not-valid"),
        get_path_kvp(sd.jobs_service.path, process="process 1:1.2.3"),
        get_path_kvp(sd.jobs_service.path, process="process!!:1.2.3"),
    ])
    def test_get_jobs_process_invalid_tag_in_path_or_query(self, path):
        # type: (str) -> None
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_private_process_forbidden_access_in_path(self):
        path = sd.process_jobs_service.path.format(process_id=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_private_process_not_returned_in_query(self):
        path = get_path_kvp(sd.jobs_service.path, process=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_service_and_process_unknown_in_path(self):
        path = sd.provider_jobs_service.path.format(provider_id="unknown-service-id", process_id="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_service_and_process_unknown_in_query(self):
        path = get_path_kvp(sd.jobs_service.path, service="unknown-service-id", process="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_private_service_public_process_forbidden_access_in_path(self):
        path = sd.provider_jobs_service.path.format(provider_id=self.service_private.name,
                                                    process_id=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_private_service_public_process_forbidden_access_in_query(self):
        path = get_path_kvp(sd.jobs_service.path,
                            service=self.service_private.name,
                            process=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_public_service_private_process_forbidden_access_in_query(self):
        """
        NOTE:
            it is up to the remote service to hide private processes
            if the process is visible, the a job can be executed and it is automatically considered public
        """
        path = get_path_kvp(sd.jobs_service.path,
                            service=self.service_public.name,
                            process=self.process_private.identifier)
        with contextlib.ExitStack() as stack:
            for runner in mocked_remote_wps([self.process_private]):  # process visible on remote
                stack.enter_context(runner)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 200
            assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_public_service_no_processes(self):
        """
        NOTE:
            it is up to the remote service to hide private processes
            if the process is invisible, no job should have been executed nor can be fetched
        """
        path = get_path_kvp(sd.jobs_service.path,
                            service=self.service_public.name,
                            process=self.process_private.identifier)
        with contextlib.ExitStack() as stack:
            for patch in mocked_remote_wps([]):    # process invisible (not returned by remote)
                stack.enter_context(patch)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 404
            assert resp.content_type == ContentType.APP_JSON

    def test_get_jobs_public_with_access_and_request_user(self):
        """
        Verifies that corresponding processes are returned when proper access/user-id are respected.
        """
        uri_direct_jobs = sd.jobs_service.path
        uri_process_jobs = sd.process_jobs_service.path.format(process_id=self.process_public.identifier)
        uri_provider_jobs = sd.provider_jobs_service.path.format(
            provider_id=self.service_public.name, process_id=self.process_public.identifier)

        admin_public_jobs = list(filter(lambda j: Visibility.PUBLIC in j.access, self.job_info))
        admin_private_jobs = list(filter(lambda j: Visibility.PRIVATE in j.access, self.job_info))
        editor1_all_jobs = list(filter(lambda j: j.user_id == self.user_editor1_id, self.job_info))
        editor1_public_jobs = list(filter(lambda j: Visibility.PUBLIC in j.access, editor1_all_jobs))
        editor1_private_jobs = list(filter(lambda j: Visibility.PRIVATE in j.access, editor1_all_jobs))
        public_jobs = list(filter(lambda j: Visibility.PUBLIC in j.access, self.job_info))

        def filter_process(jobs):  # type: (Iterable[Job]) -> List[Job]
            return list(filter(lambda j: j.process == self.process_public.identifier, jobs))

        def filter_service(jobs):  # type: (Iterable[Job]) -> List[Job]
            jobs = filter_process(jobs)  # nested process under service must also be public to be accessible
            return list(filter(lambda j: j.service == self.service_public.name, jobs))

        # test variations of [paths, query, user-id, expected-job-ids]
        path_jobs_user_req_tests = [
            # pylint: disable=C0301,line-too-long
            # URI               ACCESS              USER                    EXPECTED JOBS
            (uri_direct_jobs,   None,               None,                   public_jobs),                               # noqa: E241,E501
            (uri_direct_jobs,   None,               self.user_editor1_id,   editor1_all_jobs),                          # noqa: E241,E501
            (uri_direct_jobs,   None,               self.user_admin_id,     self.job_info),                             # noqa: E241,E501
            (uri_direct_jobs,   Visibility.PRIVATE, None,                   public_jobs),                               # noqa: E241,E501
            (uri_direct_jobs,   Visibility.PRIVATE, self.user_editor1_id,   editor1_private_jobs),                      # noqa: E241,E501
            (uri_direct_jobs,   Visibility.PRIVATE, self.user_admin_id,     admin_private_jobs),                        # noqa: E241,E501
            (uri_direct_jobs,   Visibility.PUBLIC,  None,                   public_jobs),                               # noqa: E241,E501
            (uri_direct_jobs,   Visibility.PUBLIC,  self.user_editor1_id,   editor1_public_jobs),                       # noqa: E241,E501
            (uri_direct_jobs,   Visibility.PUBLIC,  self.user_admin_id,     admin_public_jobs),                         # noqa: E241,E501
            # ---
            (uri_process_jobs,  None,               None,                   filter_process(public_jobs)),               # noqa: E241,E501
            (uri_process_jobs,  None,               self.user_editor1_id,   filter_process(editor1_all_jobs)),          # noqa: E241,E501
            (uri_process_jobs,  None,               self.user_admin_id,     filter_process(self.job_info)),             # noqa: E241,E501
            (uri_process_jobs,  Visibility.PRIVATE, None,                   filter_process(public_jobs)),               # noqa: E241,E501
            (uri_process_jobs,  Visibility.PRIVATE, self.user_editor1_id,   filter_process(editor1_private_jobs)),      # noqa: E241,E501
            (uri_process_jobs,  Visibility.PRIVATE, self.user_admin_id,     filter_process(admin_private_jobs)),        # noqa: E241,E501
            (uri_process_jobs,  Visibility.PUBLIC,  None,                   filter_process(public_jobs)),               # noqa: E241,E501
            (uri_process_jobs,  Visibility.PUBLIC,  self.user_editor1_id,   filter_process(editor1_public_jobs)),       # noqa: E241,E501
            (uri_process_jobs,  Visibility.PUBLIC,  self.user_admin_id,     filter_process(public_jobs)),               # noqa: E241,E501
            # ---
            (uri_provider_jobs, None,               None,                   filter_service(public_jobs)),               # noqa: E241,E501
            (uri_provider_jobs, None,               self.user_editor1_id,   filter_service(editor1_all_jobs)),          # noqa: E241,E501
            (uri_provider_jobs, None,               self.user_admin_id,     filter_service(self.job_info)),             # noqa: E241,E501
            (uri_provider_jobs, Visibility.PRIVATE, None,                   filter_service(public_jobs)),               # noqa: E241,E501
            (uri_provider_jobs, Visibility.PRIVATE, self.user_editor1_id,   filter_service(editor1_private_jobs)),      # noqa: E241,E501
            (uri_provider_jobs, Visibility.PRIVATE, self.user_admin_id,     filter_service(admin_private_jobs)),        # noqa: E241,E501
            (uri_provider_jobs, Visibility.PUBLIC,  None,                   filter_service(public_jobs)),               # noqa: E241,E501
            (uri_provider_jobs, Visibility.PUBLIC,  self.user_editor1_id,   filter_service(editor1_public_jobs)),       # noqa: E241,E501
            (uri_provider_jobs, Visibility.PUBLIC,  self.user_admin_id,     filter_service(public_jobs)),               # noqa: E241,E501

        ]   # type: List[Tuple[str, str, Union[None, int], List[Job]]]

        for i, (path, access, user_id, expected_jobs) in enumerate(path_jobs_user_req_tests):
            with contextlib.ExitStack() as stack:
                for patch in self.get_job_request_auth_mock(user_id):
                    stack.enter_context(patch)
                for patch in mocked_remote_wps([self.process_public]):
                    stack.enter_context(patch)
                test = get_path_kvp(path, access=access, limit=1000) if access else get_path_kvp(path, limit=1000)
                resp = self.app.get(test, headers=self.json_headers)
                self.check_basic_jobs_info(resp)
                job_expect = [job.id for job in expected_jobs]
                job_result = resp.json["jobs"]
                test_values = dict(path=path, access=access, user_id=user_id)
                self.assert_equal_with_jobs_diffs(job_result, job_expect, test_values, index=i)

    def test_jobs_list_with_limit_api(self):
        """
        Test handling of ``limit`` query parameter when listing jobs.

        .. seealso::
            - `/req/collections/rc-limit-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/limit/requirements/REQ_rc-limit-response.adoc>`_
        """
        limit_parameter = 20
        path = get_path_kvp(sd.jobs_service.path, limit=limit_parameter)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "limit" in resp.json and isinstance(resp.json["limit"], int)
        assert resp.json["limit"] == limit_parameter
        assert len(resp.json["jobs"]) <= limit_parameter

    def test_jobs_list_schema_not_required_fields(self):
        """
        Test that job listing query parameters for filtering results are marked as optional in OpenAPI schema.

        .. seealso::
            - `/req/collections/rc-limit-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/limit/requirements/REQ_rc-limit-response.adoc>`_
        """
        uri = sd.openapi_json_service.path
        resp = self.app.get(uri, headers=self.json_headers)
        schema_prefix = sd.GetProcessJobsQuery.__name__
        assert not resp.json["components"]["parameters"][f"{schema_prefix}.page"]["required"]
        assert not resp.json["components"]["parameters"][f"{schema_prefix}.limit"]["required"]

    def test_get_jobs_filter_by_tags_single(self):
        path = get_path_kvp(sd.jobs_service.path, tags="unique", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["total"] == 1
        assert resp.json["jobs"][0] == str(self.job_info[0].id)

        path = get_path_kvp(sd.jobs_service.path, tags="test-two", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["total"] == 2
        assert sorted(resp.json["jobs"]) == sorted([str(self.job_info[1].id), str(self.job_info[2].id)])

    def test_get_jobs_filter_by_tags_multi(self):
        path = get_path_kvp(sd.jobs_service.path, tags="unique,other", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["total"] == 0

        path = get_path_kvp(sd.jobs_service.path, tags="test-two,other", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["total"] == 1
        assert resp.json["jobs"][0] == str(self.job_info[1].id)

    def test_get_jobs_datetime_before(self):
        """
        Test that only filtered jobs before a certain time are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_
        """
        datetime_before = DATETIME_INTERVAL_OPEN_START_SYMBOL + self.datetime_interval[0]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_before)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        # generated datetime interval have an offset that makes all job in the future
        # anything created "recently" and publicly visible will be listed here
        job_result = resp.json["jobs"]
        job_expect = [self.job_info[i].id for i in [0, 1, 2, 5, 9, 10, 11, 12]]
        self.assert_equal_with_jobs_diffs(job_result, job_expect, {"datetime": datetime_before})
        for job in resp.json["jobs"]:
            base_uri = f"{sd.jobs_service.path}/{job}"
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == ContentType.APP_JSON
            interval = datetime_before.replace(DATETIME_INTERVAL_OPEN_START_SYMBOL, "")
            assert date_parser.parse(resp.json["created"]) <= date_parser.parse(interval)

    def test_get_jobs_datetime_after(self):
        """
        Test that only filtered jobs after a certain time are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_
        """
        datetime_after = str(self.datetime_interval[2] + DATETIME_INTERVAL_OPEN_END_SYMBOL)
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_after)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert len(resp.json["jobs"]) == 2
        for job in resp.json["jobs"]:
            base_uri = f"{sd.jobs_service.path}/{job}"
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == ContentType.APP_JSON
            interval = datetime_after.replace(DATETIME_INTERVAL_OPEN_END_SYMBOL, "")
            assert date_parser.parse(resp.json["created"]) >= date_parser.parse(interval)

    def test_get_jobs_datetime_interval(self):
        """
        Test that only filtered jobs in the time interval are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_
        """
        datetime_interval = self.datetime_interval[1] + DATETIME_INTERVAL_CLOSED_SYMBOL + self.datetime_interval[3]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_interval)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON

        datetime_after, datetime_before = datetime_interval.split(DATETIME_INTERVAL_CLOSED_SYMBOL)
        assert len(resp.json["jobs"]) == 3
        for job in resp.json["jobs"]:
            base_uri = f"{sd.jobs_service.path}/{job}"
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == ContentType.APP_JSON
            assert date_parser.parse(resp.json["created"]) >= date_parser.parse(datetime_after)
            assert date_parser.parse(resp.json["created"]) <= date_parser.parse(datetime_before)

    def test_get_jobs_datetime_match(self):
        """
        Test that only filtered jobs at a specific time are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_
        """
        datetime_match = self.datetime_interval[1]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_match)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert len(resp.json["jobs"]) == 1
        for job in resp.json["jobs"]:
            base_uri = f"{sd.jobs_service.path}/{job}"
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == ContentType.APP_JSON
            assert date_parser.parse(resp.json["created"]) == date_parser.parse(datetime_match)

    def test_get_jobs_datetime_invalid(self):
        """
        Test that incorrectly formatted ``datetime`` query parameter value is handled.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_

        Value of ``datetime_invalid`` is not formatted against the RFC-3339 datetime format.
        For more details refer to https://datatracker.ietf.org/doc/html/rfc3339#section-5.6.
        """
        datetime_invalid = "2022-31-12 23:59:59"
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_invalid)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400

    def test_get_jobs_datetime_interval_invalid(self):
        """
        Test that invalid ``datetime`` query parameter value is handled.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_

        Value of ``datetime_invalid`` represents a datetime interval where the limit dates are inverted.
        The minimum is greater than the maximum datetime limit.
        """
        datetime_interval = self.datetime_interval[3] + DATETIME_INTERVAL_CLOSED_SYMBOL + self.datetime_interval[1]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_interval)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 422

    def test_get_jobs_datetime_before_invalid(self):
        """
        Test that invalid ``datetime`` query parameter value with a range is handled.

        .. seealso::
            - `/req/collections/rc-datetime-response
              <https://github.com/opengeospatial/ogcapi-common/blob/master/
              api_modules/datetime/requirements/REQ_rc-datetime-response.adoc>`_

        Value of ``datetime_before`` represents a bad open range datetime interval.
        """
        datetime_before = "./" + self.datetime_interval[3]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_before)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400

    def test_get_jobs_duration_min_only(self):
        test = {"minDuration": 35}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [7, 8]]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

        test = {"minDuration": 25}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_idx = [6, 7, 8]  # although 10 has duration=25, it is dynamic. Delay until here is reached becomes >25
        expect_jobs = [self.job_info[i].id for i in expect_idx]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

        test = {"minDuration": 49}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [8]]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

    def test_get_jobs_duration_max_only(self):
        test = {"maxDuration": 30}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        # 3, 4 are private, >9 except 11 are dynamic since running (11 only accepted), others fixed duration <30s
        expect_idx = [0, 1, 2, 5, 6, 9, 10, 12]
        expect_jobs = [self.job_info[i].id for i in expect_idx]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

        test = {"maxDuration": 49}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        # same as previous for repeated indices except 7 == 40s now also < max duration, 8 is 50s just below range
        expect_idx = [0, 1, 2, 5, 6, 7, 9, 10, 12]
        expect_jobs = [self.job_info[i].id for i in expect_idx]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

    def test_get_jobs_duration_min_max(self):
        # note: avoid range <35s for this test to avoid sudden dynamic duration of 9, 10 becoming within min/max
        test = {"minDuration": 35, "maxDuration": 60}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [7, 8]]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

        test = {"minDuration": 38, "maxDuration": 42}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [7]]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

        test = {"minDuration": 35, "maxDuration": 37}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        assert len(result_jobs) == 0

    def test_get_jobs_duration_min_max_invalid(self):
        test = {"minDuration": 30, "maxDuration": 20}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in [400, 422]

        test = {"minDuration": -1}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in [400, 422]

        test = {"maxDuration": -20}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in [400, 422]

        test = {"minDuration": -10, "maxDuration": 10}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in [400, 422]

    def test_get_jobs_by_status_single(self):
        test = {"status": Status.SUCCEEDED}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[0].id]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

        test = {"status": Status.FAILED}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        expect_jobs = [self.job_info[i].id for i in [1, 2, 5, 6, 7, 8]]  # 8 total, but only 6 visible
        result_jobs = resp.json["jobs"]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

    def test_get_jobs_by_status_multi(self):
        test = {"status": f"{Status.SUCCEEDED},{Status.RUNNING}"}
        path = get_path_kvp(sd.jobs_service.path, **test)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [0, 9, 10]]
        self.assert_equal_with_jobs_diffs(result_jobs, expect_jobs, test)

    def test_get_jobs_by_status_invalid(self):
        path = get_path_kvp(sd.jobs_service.path, status="random")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "JobInvalidParameter"
        assert resp.json["value"]["status"] == "random"
        assert "status" in resp.json["cause"]

        status = f"random,{Status.RUNNING}"
        path = get_path_kvp(sd.jobs_service.path, status=status)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "JobInvalidParameter"
        assert resp.json["value"]["status"] == status
        assert "status" in resp.json["cause"]

    def test_get_job_status_response_process_id(self):
        """
        Verify the processID value in the job status response.
        """
        body = {
            "outputs": [],
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
        }
        with contextlib.ExitStack() as stack:
            for runner in mocked_process_job_runner():
                stack.enter_context(runner)
            path = f"/processes/{self.process_public.identifier}/jobs"
            resp = self.app.post_json(path, params=body, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == ContentType.APP_JSON

        assert resp.json["processID"] == "process-public"

    def test_get_job_invalid_uuid(self):
        """
        Test handling of invalid UUID reference to search job.

        .. versionchanged:: 4.6
            Jobs must explicitly use an :class:`uuid.UUID` object to search.
            Any value provided in path parameter that does not correspond to such definition raises a bad request.
        """
        # to make sure UUID is applied, use the "same format" (8-4-4-4-12), but with invalid definitions
        base_path = sd.job_service.path.format(job_id="thisisnt-some-real-uuid-allerrordata")
        for sub_path in ["", "/inputs", "/outputs", "/results", "/logs", "exceptions"]:
            path = f"{base_path}{sub_path}"
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 400
            assert resp.json["title"] == "NoSuchJob"
            assert resp.json["type"].endswith("no-such-job")
            assert "UUID" in resp.json["detail"]

    @mocked_dismiss_process()
    def test_job_dismiss_running_single(self):
        """
        Jobs that are in a valid *running* (or about to) state can be dismissed successfully.

        Subsequent calls to the same job dismiss operation must respond with HTTP Gone (410) status.

        .. seealso::
            OGC specification of dismiss operation: https://docs.ogc.org/is/18-062r2/18-062r2.html#toc53
        """
        job_running = self.job_info[10]
        assert job_running.status == Status.RUNNING, "Job must be in running state for test"
        job_accept = self.job_info[11]
        assert job_accept.status == Status.ACCEPTED, "Job must be in accepted state for test"
        job_started = self.job_info[12]
        assert job_started.status == Status.STARTED, "Job must be in started state for test"

        for job in [job_running, job_accept, job_started]:
            path = sd.job_service.path.format(job_id=job.id)
            resp = self.app.delete(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.json["status"] == Status.DISMISSED

            # job are not removed, only dismissed
            path = get_path_kvp(sd.jobs_service.path, status=Status.DISMISSED, limitt=1000)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert job.id in resp.json["jobs"], "Job HTTP DELETE should not have deleted it, but only dismissed it."

            path = sd.job_service.path.format(job_id=job.id)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200, "Job should still exist even after dismiss"
            assert resp.json["status"] == Status.DISMISSED

            resp = self.app.delete(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 410, "Job cannot be dismissed again."
            assert job.id in resp.json["value"]

    @mocked_dismiss_process()
    def test_job_dismiss_complete_single(self):
        """
        Jobs that are already *completed* (regardless of success/failure) state removes result artifacts.

        Subsequent calls to the same job dismiss operation must respond with HTTP Gone (410) status.

        .. seealso::
            OGC specification of dismiss operation: https://docs.ogc.org/is/18-062r2/18-062r2.html#toc5
        """
        job_success = self.job_info[0]
        job_failed = self.job_info[1]
        assert job_success.status == Status.SUCCEEDED, "Job must be in successful state for test"
        assert job_failed.status == Status.FAILED, "Job must be in failed state for test"

        # create dummy files to validate results flush of successful job
        wps_out_dir = self.settings["weaver.wps_output_dir"]
        job_id_str = str(job_success.id)
        job_out_dir = os.path.join(wps_out_dir, job_id_str)
        job_out_log = os.path.join(wps_out_dir, job_id_str + ".log")
        job_out_xml = os.path.join(wps_out_dir, job_id_str + ".xml")
        os.makedirs(job_out_dir, exist_ok=True)
        try:
            with contextlib.ExitStack() as stack:
                tmp_out1 = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", dir=job_out_dir, suffix=".yml"))
                tmp_out2 = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", dir=job_out_dir, suffix=".txt"))
                tmp_out3 = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", dir=job_out_dir, suffix=".tif"))
                tmp_log = stack.enter_context(open(job_out_log, mode="w", encoding="utf-8"))  # noqa
                tmp_xml = stack.enter_context(open(job_out_xml, mode="w", encoding="utf-8"))  # noqa
                for tmp_file in [tmp_out1, tmp_out2, tmp_out3, tmp_log, tmp_xml]:
                    assert os.path.isfile(tmp_file.name)

                job_path = sd.job_service.path.format(job_id=job_success.id)
                resp = self.app.delete(job_path, headers=self.json_headers)
                assert resp.status_code == 200
                assert resp.json["status"] == Status.DISMISSED

                for tmp_file in [tmp_out1, tmp_out2, tmp_out3, tmp_log, tmp_xml]:
                    assert not os.path.exists(tmp_file.name)
                assert not os.path.exists(job_out_dir)

                # subsequent operations returns Gone for sub-resources of the job execution
                for sub_path in ["", "/outputs", "/results", "/logs", "/exceptions"]:
                    path = job_path + sub_path
                    func = self.app.get if sub_path else self.app.delete
                    resp = func(path, headers=self.json_headers, expect_errors=True)
                    assert resp.status_code == 410, f"Dismissed job should return 'Gone' status for: [{path}]"
        except OSError:
            pass
        finally:
            shutil.rmtree(job_out_dir, ignore_errors=True)

        # test on failed job that could have no artifacts at all
        path = sd.job_service.path.format(job_id=job_failed.id)
        resp = self.app.delete(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["status"] == Status.DISMISSED
        resp = self.app.delete(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 410

    @mocked_dismiss_process()
    def test_job_dismiss_batch(self):
        path = sd.jobs_service.path
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        jobs = resp.json["jobs"]
        assert len(jobs) > 3

        resp = self.app.delete_json(path, params={"jobs": jobs[:2]}, headers=self.json_headers)
        assert resp.status_code == 200
        self.assert_equal_with_jobs_diffs(resp.json["jobs"], jobs[:2])

        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        self.assert_equal_with_jobs_diffs(resp.json["jobs"], jobs, message="All jobs should still exist after dismiss.")

        for job in jobs[:2]:
            path = sd.job_service.path.format(job_id=job)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.json["status"] == Status.DISMISSED, "Job status should have been updated to dismissed."

    def test_job_results_errors(self):
        """
        Validate errors returned for a incomplete, failed or dismissed job when requesting its results.
        """
        job_accepted = self.make_job(
            task_id="1111-0000-0000-0000", process=self.process_public.identifier, service=None,
            user_id=None, status=Status.ACCEPTED, progress=0, access=Visibility.PUBLIC
        )
        job_running = self.make_job(
            task_id="1111-0000-0000-1111", process=self.process_public.identifier, service=None,
            user_id=None, status=Status.RUNNING, progress=10, access=Visibility.PUBLIC
        )
        job_failed_str = self.make_job(
            task_id="1111-0000-0000-2222", process=self.process_public.identifier, service=None,
            user_id=None, status=Status.FAILED, progress=50, access=Visibility.PUBLIC,
            exceptions=[
                "random",
                "pywps.exceptions.MissingParameterValue: 400 MissingParameterValue: input",
                "ignore"
            ]
        )
        job_failed_json = self.make_job(
            task_id="1111-0000-0000-3333", process=self.process_public.identifier, service=None,
            user_id=None, status=Status.FAILED, progress=50, access=Visibility.PUBLIC,
            exceptions=[
                {},
                {"error": "bad"},
                {"Code": "InvalidParameterValue", "Locator": "None", "Text": "Input type invalid."}
            ]
        )
        job_failed_none = self.make_job(
            task_id="1111-0000-0000-4444", process=self.process_public.identifier, service=None,
            user_id=None, status=Status.FAILED, progress=50, access=Visibility.PUBLIC, exceptions=[]
        )
        job_dismissed = self.make_job(
            task_id="1111-0000-0000-5555", process=self.process_public.identifier, service=None,
            user_id=None, status=Status.DISMISSED, progress=50, access=Visibility.PUBLIC
        )

        for code, job, title, error_type, cause in [
            (404, job_accepted, "JobResultsNotReady", "result-not-ready", {"status": Status.ACCEPTED}),
            (404, job_running, "JobResultsNotReady", "result-not-ready", {"status": Status.RUNNING}),
            (400, job_failed_str, "JobResultsFailed", "MissingParameterValue", "400 MissingParameterValue: input"),
            (400, job_failed_json, "JobResultsFailed", "InvalidParameterValue", "Input type invalid."),
            (400, job_failed_none, "JobResultsFailed", "NoApplicableCode", "unknown"),
            (410, job_dismissed, "JobDismissed", "JobDismissed", {"status": Status.DISMISSED}),
        ]:
            for what in ["outputs", "results"]:
                path = f"/jobs/{job.id}/{what}"
                case = (
                    f"Failed using (Path: {path}, Status: {job.status}, Code: {code}, Job: {job}, "
                    f"Title: {title}, Error: {error_type}, Cause: {cause})"
                )
                resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
                assert resp.status_code == code, case
                assert resp.json["title"] == title, case
                assert resp.json["cause"] == cause, case
                assert resp.json["type"].endswith(error_type), case   # ignore http full reference, not always there
                assert "links" in resp.json

    def test_jobs_inputs_outputs_validations(self):
        """
        Ensure that inputs/outputs submitted or returned can be represented and validated across various formats.
        """
        default_trans_mode = {"transmissionMode": ExecuteTransmissionMode.VALUE}

        job_none = sd.Execute().deserialize({})
        assert job_none == {
            "inputs": {},
            "outputs": {},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_in_none = sd.Execute().deserialize({"outputs": {"random": default_trans_mode}})
        assert job_in_none == {
            "inputs": {},
            "outputs": {"random": default_trans_mode},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_in_empty_dict = sd.Execute().deserialize({"inputs": {}, "outputs": {"random": default_trans_mode}})
        assert job_in_empty_dict == {
            "inputs": {},
            "outputs": {"random": default_trans_mode},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_in_empty_list = sd.Execute().deserialize({"inputs": [], "outputs": {"random": default_trans_mode}})
        assert job_in_empty_list == {
            "inputs": [],
            "outputs": {"random": default_trans_mode},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_out_none = sd.Execute().deserialize({"inputs": {"random": "ok"}})
        assert job_out_none == {
            "inputs": {"random": "ok"},
            "outputs": {},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_out_empty_dict = sd.Execute().deserialize({"inputs": {"random": "ok"}, "outputs": {}})
        assert job_out_empty_dict == {
            "inputs": {"random": "ok"},
            "outputs": {},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_out_empty_list = sd.Execute().deserialize({"inputs": {"random": "ok"}, "outputs": []})
        assert job_out_empty_list == {
            "inputs": {"random": "ok"},
            "outputs": [],
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        job_out_defined = sd.Execute().deserialize({
            "inputs": {"random": "ok"},
            "outputs": {"random": {"transmissionMode": ExecuteTransmissionMode.REFERENCE}}
        })
        assert job_out_defined == {
            "inputs": {"random": "ok"},
            "outputs": {"random": {"transmissionMode": ExecuteTransmissionMode.REFERENCE}},
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT
        }

        with self.assertRaises(colander.Invalid):
            sd.Execute().deserialize({"inputs": "value"})

        with self.assertRaises(colander.Invalid):
            sd.Execute().deserialize({"outputs": "value"})

        with self.assertRaises(colander.Invalid):
            sd.Execute().deserialize({"outputs": {"random": "value"}})

        with self.assertRaises(colander.Invalid):
            sd.Execute().deserialize({"outputs": {"random": {"transmissionMode": "bad"}}})

    def test_job_logs_formats(self):
        path = f"/jobs/{self.job_info[0].id}/logs"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert ContentType.APP_JSON in resp.content_type
        assert isinstance(resp.json, list)
        lines = resp.json
        assert len(lines) == 3
        assert "Start" in lines[0]
        assert "Process" in lines[1]
        assert "Complete" in lines[2]

        resp = self.app.get(path, headers={"Accept": ContentType.TEXT_PLAIN})
        assert resp.status_code == 200
        assert ContentType.TEXT_PLAIN in resp.content_type
        assert isinstance(resp.text, str)
        assert not resp.text.startswith("[\"[")  # JSON list '[' followed by each string item with [<datetime>]
        with pytest.raises(AttributeError):
            resp.json  # noqa  # pylint: disable=pointless-statement
        lines = resp.text.split("\n")
        assert len(lines) == 3
        assert "Start" in lines[0]
        assert "Process" in lines[1]
        assert "Complete" in lines[2]

        resp = self.app.get(path, params={"f": "text"})
        assert resp.status_code == 200
        assert ContentType.TEXT_PLAIN in resp.content_type
        assert isinstance(resp.text, str)
        assert not resp.text.startswith("[\"[")  # JSON list '[' followed by each string item with [<datetime>]
        with pytest.raises(AttributeError):
            resp.json  # noqa  # pylint: disable=pointless-statement
        lines = resp.text.split("\n")
        assert len(lines) == 3
        assert "Start" in lines[0]
        assert "Process" in lines[1]
        assert "Complete" in lines[2]

        resp = self.app.get(path, params={"f": "xml"})
        assert resp.status_code == 200
        assert ContentType.APP_XML in resp.content_type
        assert isinstance(resp.text, str)
        assert resp.text.startswith("<?xml")
        assert "<logs>" in resp.text
        with pytest.raises(AttributeError):
            resp.json  # noqa  # pylint: disable=pointless-statement
        lines = resp.text.split("<logs>")[-1].split("</logs>")[0].split("<item")[1:]
        assert len(lines) == 3
        assert "Start" in lines[0]
        assert "Process" in lines[1]
        assert "Complete" in lines[2]

        resp = self.app.get(path, params={"f": "yaml"})
        assert resp.status_code == 200
        assert ContentType.APP_YAML in resp.content_type
        assert isinstance(resp.text, str)
        with pytest.raises(AttributeError):
            resp.json  # noqa  # pylint: disable=pointless-statement
        lines = resp.text.split("\n")
        lines = [line for line in lines if line]
        assert len(lines) == 3
        assert all(line.startswith("- ") for line in lines)
        assert "Start" in lines[0]
        assert "Process" in lines[1]
        assert "Complete" in lines[2]

    def test_job_statistics_missing(self):
        job = self.job_info[0]
        assert job.status == Status.SUCCEEDED, "invalid job status to run test"
        path = f"/jobs/{job.id}/statistics"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404, "even if job is successful, expects not found if no statistics are available"

    def test_job_statistics_response(self):
        stats = load_example("job_statistics.json")
        job = self.make_job(
            add_info=False,
            task_id="2222-0000-0000-0000", process=self.process_public.identifier, service=None,
            user_id=self.user_admin_id, status=Status.SUCCEEDED, progress=100, access=Visibility.PUBLIC,
            statistics=stats
        )
        try:
            path = f"/jobs/{job.id}/statistics"
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.json == stats
        finally:
            if job:
                self.job_store.delete_job(job.id)
