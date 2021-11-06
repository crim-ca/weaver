import datetime

import contextlib
import json
import unittest
import warnings
from collections import OrderedDict
from datetime import date
from distutils.version import LooseVersion
from typing import TYPE_CHECKING

import mock
import pyramid.testing
import pytest
from dateutil import parser as date_parser

from tests.utils import (
    get_module_version,
    get_test_weaver_app,
    mocked_process_job_runner,
    mocked_remote_wps,
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
    JOB_STATUS_CATEGORY_FINISHED,
    JOB_STATUS_VALUES,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED
)
from weaver.utils import get_path_kvp
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.swagger_definitions import (
    DATETIME_INTERVAL_CLOSED_SYMBOL,
    DATETIME_INTERVAL_OPEN_END_SYMBOL,
    DATETIME_INTERVAL_OPEN_START_SYMBOL
)

if TYPE_CHECKING:
    from typing import Iterable, List, Tuple, Union


class WpsRestApiJobsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", TimeZoneInfoAlreadySetWarning)
        cls.settings = {
            "weaver.url": "https://localhost",
            "weaver.wps_email_encrypt_salt": "weaver-test",
        }
        cls.config = setup_config_with_mongodb(settings=cls.settings)
        cls.app = get_test_weaver_app(config=cls.config)
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
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
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_private = WpsTestProcess(identifier="process-private")
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)
        self.process_other = WpsTestProcess(identifier="process-other")
        self.process_store.save_process(self.process_other)
        self.process_store.set_visibility(self.process_other.identifier, VISIBILITY_PUBLIC)
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
        self.make_job(task_id="5555-5555-5555-5555", process=self.process_public.identifier,
                      service=self.service_public.name, created=self.datetime_interval[0], duration=20,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="6666-6666-6666-6666", process=self.process_private.identifier,
                      service=self.service_public.name, created=self.datetime_interval[1], duration=30,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="7777-7777-7777-7777", process=self.process_public.identifier,
                      service=self.service_private.name, created=self.datetime_interval[2], duration=40,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="8888-8888-8888-8888", process=self.process_private.identifier,
                      service=self.service_private.name, created=self.datetime_interval[3], duration=50,
                      user_id=self.user_editor1_id, status=STATUS_FAILED, progress=99, access=VISIBILITY_PUBLIC)
        # jobs with duplicate 'process' identifier, but under a different 'service' name
        self.make_job(task_id="9999-9999-9999-9999", process=self.process_other.identifier,
                      service=self.service_one.name, created=datetime.datetime.now(), duration=20,
                      user_id=self.user_editor1_id, status=STATUS_RUNNING, progress=99, access=VISIBILITY_PUBLIC)
        self.make_job(task_id="1010-1010-1010-1010", created=datetime.datetime.now(), duration=25,
                      process=self.process_other.identifier, service=self.service_two.name,
                      user_id=self.user_editor1_id, status=STATUS_RUNNING, progress=99, access=VISIBILITY_PUBLIC)

    def make_job(self, task_id, process, service, user_id, status, progress, access, created=None, duration=None):
        created = date_parser.parse(created) if created else None
        job = self.job_store.save_job(task_id=task_id, process=process, service=service, is_workflow=False,
                                      user_id=user_id, execute_async=True, access=access, created=created)
        job.status = status
        if status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_FINISHED]:
            job["finished"] = created + datetime.timedelta(seconds=duration if duration else 10)
        job.progress = progress
        job = self.job_store.update_job(job)
        self.job_info.append(job)
        return job

    def message_with_jobs_mapping(self, message="", indent=2):
        """
        For helping debugging of auto-generated job ids.
        """
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
        if LooseVersion(get_module_version("pyramid")) >= LooseVersion("2"):
            authn_policy_class = "pyramid.security.SecurityAPIMixin"
            authz_policy_class = "pyramid.security.SecurityAPIMixin"
        else:
            authn_policy_class = "pyramid.security.AuthenticationAPIMixin"
            authz_policy_class = "pyramid.security.AuthorizationAPIMixin"
        return tuple([
            mock.patch("{}.authenticated_userid".format(authn_policy_class), new_callable=lambda: user_id),
            mock.patch("{}.has_permission".format(authz_policy_class), return_value=is_admin),
        ])

    @staticmethod
    def generate_test_datetimes():
        # type: () -> List[str]
        """
        Generates a list of dummy datetimes for testing.
        """
        year = date.today().year + 1
        return ["{}-0{}-02T03:32:38.487000+00:00".format(year, month) for month in range(1, 5)]

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
        assert job["status"] in JOB_STATUS_VALUES
        if job["status"] == STATUS_SUCCEEDED:
            assert len([link for link in job["links"] if link["rel"].endswith("results")])
        elif job["status"] == STATUS_FAILED:
            assert len([link for link in job["links"] if link["rel"].endswith("exceptions")])

    @staticmethod
    def check_basic_jobs_info(response):
        assert response.status_code == 200
        assert response.content_type == CONTENT_TYPE_APP_JSON
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
            resp = self.app.get(path, headers=self.json_headers)
            self.check_basic_jobs_info(resp)
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
                assert len(grouped_jobs["jobs"]) == 3
                assert set(grouped_jobs["jobs"]) == {self.job_info[0].id, self.job_info[5].id, self.job_info[7].id}
            elif categories["process"] == self.process_private.identifier:
                assert len(grouped_jobs["jobs"]) == 3
                assert set(grouped_jobs["jobs"]) == {self.job_info[2].id, self.job_info[6].id, self.job_info[8].id}
            elif categories["process"] == self.process_unknown:
                assert len(grouped_jobs["jobs"]) == 1
                assert set(grouped_jobs["jobs"]) == {self.job_info[1].id}
            elif categories["process"] == self.process_other.identifier:
                assert len(grouped_jobs["jobs"]) == 2
                assert set(grouped_jobs["jobs"]) == {self.job_info[9].id, self.job_info[10].id}
            else:
                pytest.fail("Unknown job grouping 'process' value: {}".format(categories["process"]))

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
                assert len(grouped_jobs["jobs"]) == 3
                assert set(grouped_jobs["jobs"]) == {self.job_info[1].id, self.job_info[5].id, self.job_info[6].id}
            elif categories[service_or_provider] == self.service_private.name:
                assert len(grouped_jobs["jobs"]) == 2
                assert set(grouped_jobs["jobs"]) == {self.job_info[7].id, self.job_info[8].id}
            elif categories[service_or_provider] == self.service_one.name:
                assert len(grouped_jobs["jobs"]) == 1
                assert set(grouped_jobs["jobs"]) == {self.job_info[9].id}
            elif categories[service_or_provider] == self.service_two.name:
                assert len(grouped_jobs["jobs"]) == 1
                assert set(grouped_jobs["jobs"]) == {self.job_info[10].id}
            elif categories[service_or_provider] is None:
                assert len(grouped_jobs["jobs"]) == 2
                assert set(grouped_jobs["jobs"]) == {self.job_info[0].id, self.job_info[2].id}
            else:
                pytest.fail("Unknown job grouping 'service' value: {}".format(categories[service_or_provider]))

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
        def get_links(resp_links):
            nav_links = ["up", "current", "next", "prev", "first", "last", "search", "alternate", "collection"]
            link_dict = {rel: None for rel in nav_links}
            for _link in resp_links:
                if _link["rel"] in link_dict:
                    link_dict[_link["rel"]] = _link["href"]
            return link_dict

        expect_jobs_total = len(self.job_info)
        expect_jobs_visible = len(list(filter(lambda j: VISIBILITY_PUBLIC in j.access, self.job_info)))
        assert len(self.job_store.list_jobs()) == expect_jobs_total, (
            "expected number of jobs mismatch, following test might not work"
        )
        path = get_path_kvp(sd.jobs_service.path, limit=1000)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["jobs"]) == expect_jobs_visible, "unexpected number of visible jobs"

        base_url = self.settings["weaver.url"]
        jobs_url = base_url + sd.jobs_service.path
        limit = 2  # expect 9 jobs to be visible, making 5 pages of 2
        last = 4
        last_page = "page={}".format(last)
        prev_last_page = "page={}".format(last - 1)
        limit_kvp = "limit={}".format(limit)
        path = get_path_kvp(sd.jobs_service.path, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        links = get_links(resp.json["links"])
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
        p_kvp = "process={}".format(p_id)
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
        assert links["alternate"].startswith(jobs_url) and "process={}".format(p_id) in links["alternate"]
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

        over_limit = 10
        limit_kvp = "limit={}".format(over_limit)
        path = get_path_kvp(sd.jobs_service.path, limit=over_limit)
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

    def test_get_jobs_by_encrypted_email(self):
        """
        Verifies that literal email can be used as search criterion although not saved in plain text within db.
        """
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

        path = get_path_kvp(sd.jobs_service.path, detail="true", notification_email=email)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["total"] == 1, "Should match exactly 1 email with specified literal string as query param."
        assert resp.json["jobs"][0]["jobID"] == job_id

    def test_get_jobs_by_type_process(self):
        path = get_path_kvp(sd.jobs_service.path, type="process")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        expect_jobs = [self.job_info[i].id for i in [0, 2]]  # idx=2 & idx>4 have 'service', only 0,2 are public
        result_jobs = resp.json["jobs"]
        assert len(resp.json["jobs"]) == len(expect_jobs)
        assert resp.json["total"] == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs), self.message_with_jobs_diffs(result_jobs, expect_jobs)

    def test_get_jobs_by_type_process_and_specific_process_id(self):
        path = get_path_kvp(sd.jobs_service.path, type="process", process=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert len(resp.json["jobs"]) == 1
        expect_job = self.job_info[0].id
        assert resp.json["jobs"][0] == expect_job, self.message_with_jobs_mapping("expected only matching process")

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
        assert "cause" in resp.json and resp.json["cause"] == {"type": "process", "service": self.service_public.name}

    def template_get_jobs_by_type_service_provider(self, service_or_provider):
        path = get_path_kvp(sd.jobs_service.path, type=service_or_provider)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        expect_jobs = [self.job_info[i].id for i in [1, 5, 6, 7, 8, 9]]  # has 'service' & public access
        result_jobs = resp.json["jobs"]
        assert len(resp.json["jobs"]) == len(expect_jobs)
        assert resp.json["total"] == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs), self.message_with_jobs_diffs(result_jobs, expect_jobs)

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
        assert len(resp.json["jobs"]) == len(expect_jobs)
        assert resp.json["total"] == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs), self.message_with_jobs_diffs(result_jobs, expect_jobs)

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
        assert len(resp.json["jobs"]) == 2
        expect_jobs = [self.job_info[i].id for i in [9, 10]]
        result_jobs = [job["jobID"] for job in resp.json["jobs"]]
        assert len(result_jobs) == len(expect_jobs)
        assert resp.json["total"] == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs), self.message_with_jobs_diffs(result_jobs, expect_jobs)
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
        assert self.job_info[0].id in resp.json["jobs"], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json["jobs"], self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_query_detail(self):
        path = get_path_kvp(sd.jobs_service.path, process=self.job_info[0].process, detail="true")
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j["jobID"] for j in resp.json["jobs"]]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_path_normal(self):
        path = sd.process_jobs_service.path.format(process_id=self.job_info[0].process)
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        assert self.job_info[0].id in resp.json["jobs"], self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in resp.json["jobs"], self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_in_path_detail(self):
        path = sd.process_jobs_service.path.format(process_id=self.job_info[0].process) + "?detail=true"
        resp = self.app.get(path, headers=self.json_headers)
        self.check_basic_jobs_info(resp)
        job_ids = [j["jobID"] for j in resp.json["jobs"]]
        assert self.job_info[0].id in job_ids, self.message_with_jobs_mapping("expected in")
        assert self.job_info[1].id not in job_ids, self.message_with_jobs_mapping("expected not in")

    def test_get_jobs_process_unknown_in_path(self):
        path = sd.process_jobs_service.path.format(process_id="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_process_unknown_in_query(self):
        path = get_path_kvp(sd.jobs_service.path, process="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_process_unauthorized_in_path(self):
        path = sd.process_jobs_service.path.format(process_id=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_process_not_returned_in_query(self):
        path = get_path_kvp(sd.jobs_service.path, process=self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_service_and_process_unknown_in_path(self):
        path = sd.provider_jobs_service.path.format(provider_id="unknown-service-id", process_id="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_service_and_process_unknown_in_query(self):
        path = get_path_kvp(sd.jobs_service.path, service="unknown-service-id", process="unknown-process-id")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_service_public_process_unauthorized_in_path(self):
        path = sd.provider_jobs_service.path.format(provider_id=self.service_private.name,
                                                    process_id=self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_private_service_public_process_unauthorized_in_query(self):
        path = get_path_kvp(sd.jobs_service.path,
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
        path = get_path_kvp(sd.jobs_service.path,
                            service=self.service_public.name,
                            process=self.process_private.identifier)
        with contextlib.ExitStack() as stack:
            for runner in mocked_remote_wps([self.process_private]):  # process visible on remote
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
        path = get_path_kvp(sd.jobs_service.path,
                            service=self.service_public.name,
                            process=self.process_private.identifier)
        with contextlib.ExitStack() as stack:
            for patch in mocked_remote_wps([]):    # process invisible (not returned by remote)
                stack.enter_context(patch)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 404
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_jobs_public_with_access_and_request_user(self):
        """
        Verifies that corresponding processes are returned when proper access/user-id are respected.
        """
        uri_direct_jobs = sd.jobs_service.path
        uri_process_jobs = sd.process_jobs_service.path.format(process_id=self.process_public.identifier)
        uri_provider_jobs = sd.provider_jobs_service.path.format(
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
                for patch in mocked_remote_wps([self.process_public]):
                    stack.enter_context(patch)
                test = get_path_kvp(path, access=access, limit=1000) if access else path
                resp = self.app.get(test, headers=self.json_headers)
                self.check_basic_jobs_info(resp)
                job_ids = [job.id for job in expected_jobs]
                job_match = all(job in job_ids for job in resp.json["jobs"])
                test_values = dict(path=path, access=access, user_id=user_id)
                assert job_match, self.message_with_jobs_diffs(resp.json["jobs"], job_ids, test_values, index=i)

    def test_jobs_list_with_limit_api(self):
        """
        Test handling of ``limit`` query parameter when listing jobs.

        .. seealso::
            - `/req/collections/rc-limit-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-limit-response.adoc>`_
        """
        limit_parameter = 20
        path = get_path_kvp(sd.jobs_service.path, limit=limit_parameter)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "limit" in resp.json and isinstance(resp.json["limit"], int)
        assert resp.json["limit"] == limit_parameter
        assert len(resp.json["jobs"]) <= limit_parameter

    def test_jobs_list_schema_not_required_fields(self):
        """
        Test that job listing query parameters for filtering results are marked as optional in OpenAPI schema.

        .. seealso::
            - `/req/collections/rc-limit-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-limit-response.adoc>`_
        """
        uri = sd.openapi_json_service.path
        resp = self.app.get(uri, headers=self.json_headers)
        schema_prefix = sd.GetJobsQueries.__name__
        assert not resp.json["parameters"]["{}.page".format(schema_prefix)]["required"]
        assert not resp.json["parameters"]["{}.limit".format(schema_prefix)]["required"]

    def test_jobs_datetime_before(self):
        """
        Test that only filtered jobs before a certain time are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_
        """
        datetime_before = DATETIME_INTERVAL_OPEN_START_SYMBOL + self.datetime_interval[0]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_before)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        # generated datetime interval have an offset that makes all job in the future
        # anything created "recently" and publicly visible will be listed here
        assert len(resp.json["jobs"]) == 6
        for job in resp.json["jobs"]:
            base_uri = sd.jobs_service.path + "/{}".format(job)
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            assert date_parser.parse(resp.json["created"]) <= date_parser.parse(
                datetime_before.replace(DATETIME_INTERVAL_OPEN_START_SYMBOL, ""))

    def test_get_jobs_datetime_after(self):
        """
        Test that only filtered jobs after a certain time are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_
        """
        datetime_after = str(self.datetime_interval[2] + DATETIME_INTERVAL_OPEN_END_SYMBOL)
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_after)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert len(resp.json["jobs"]) == 2
        for job in resp.json["jobs"]:
            base_uri = sd.jobs_service.path + "/{}".format(job)
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            assert date_parser.parse(resp.json["created"]) >= date_parser.parse(
                datetime_after.replace(DATETIME_INTERVAL_OPEN_END_SYMBOL, ""))

    def test_get_jobs_datetime_interval(self):
        """
        Test that only filtered jobs in the time interval are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_
        """
        datetime_interval = self.datetime_interval[1] + DATETIME_INTERVAL_CLOSED_SYMBOL + self.datetime_interval[3]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_interval)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON

        datetime_after, datetime_before = datetime_interval.split(DATETIME_INTERVAL_CLOSED_SYMBOL)
        assert len(resp.json["jobs"]) == 3
        for job in resp.json["jobs"]:
            base_uri = sd.jobs_service.path + "/{}".format(job)
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            assert date_parser.parse(resp.json["created"]) >= date_parser.parse(datetime_after)
            assert date_parser.parse(resp.json["created"]) <= date_parser.parse(datetime_before)

    def test_get_jobs_datetime_match(self):
        """
        Test that only filtered jobs at a specific time are returned when ``datetime`` query parameter is provided.

        .. seealso::
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_
        """
        datetime_match = self.datetime_interval[1]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_match)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert len(resp.json["jobs"]) == 1
        for job in resp.json["jobs"]:
            base_uri = sd.jobs_service.path + "/{}".format(job)
            path = get_path_kvp(base_uri)
            resp = self.app.get(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            assert date_parser.parse(resp.json["created"]) == date_parser.parse(datetime_match)

    def test_get_jobs_datetime_invalid(self):
        """
        Test that incorrectly formatted ``datetime`` query parameter value is handled.

        .. seealso::
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_

        Value of ``datetime_invalid`` is not formatted against the RFC-3339 datetime format.
        For more details refer to https://datatracker.ietf.org/doc/html/rfc3339#section-5.6.
        """
        datetime_invalid = "2022-31-12 23:59:59"
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_invalid)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 422

    def test_get_jobs_datetime_interval_invalid(self):
        """
        Test that invalid ``datetime`` query parameter value is handled.

        .. seealso::
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_

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
            - `/req/collections/rc-time-collections-response
                <https://github.com/opengeospatial/ogcapi-common/blob/master/collections/requirements/collections/REQ_rc-time-collections-response.adoc>`_

        Value of ``datetime_before`` represents a bad open range datetime interval.
        """
        datetime_before = "./" + self.datetime_interval[3]
        path = get_path_kvp(sd.jobs_service.path, datetime=datetime_before)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 422

    def test_get_jobs_duration_min_only(self):
        path = get_path_kvp(sd.jobs_service.path, minDuration=40)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [8, 9]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

        path = get_path_kvp(sd.jobs_service.path, minDuration=24)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [6, 7, 8, 9, 10]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

    def test_get_jobs_duration_max_only(self):
        path = get_path_kvp(sd.jobs_service.path, maxDuration=30)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [5, 6, 10]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

        path = get_path_kvp(sd.jobs_service.path, maxDuration=49)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [8]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

    def test_get_jobs_duration_min_max(self):
        path = get_path_kvp(sd.jobs_service.path, minDuration=19, maxDuration=31)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [5, 6, 9, 10]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

        path = get_path_kvp(sd.jobs_service.path, minDuration=23, maxDuration=28)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [10]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

        path = get_path_kvp(sd.jobs_service.path, minDuration=35, maxDuration=37)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        assert len(result_jobs) == 0

    def test_get_jobs_duration_min_max_invalid(self):
        path = get_path_kvp(sd.jobs_service.path, minDuration=19, maxDuration=31)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [5, 6, 9, 10]]
        assert len(result_jobs) == len(expect_jobs)
        assert all(job in expect_jobs for job in result_jobs)

    def test_get_jobs_by_status_single(self):
        path = get_path_kvp(sd.jobs_service.path, status=STATUS_SUCCEEDED)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        assert len(result_jobs) == 1
        assert result_jobs[0] == self.job_info[0].id

        path = get_path_kvp(sd.jobs_service.path, status=STATUS_FAILED)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        expect_fail = 8
        expect_jobs = [self.job_info[i].id for i in range(1, expect_fail + 1)]
        result_jobs = resp.json["jobs"]
        assert len(result_jobs) == expect_fail
        assert all(job in expect_jobs for job in result_jobs)

    def test_get_jobs_by_status_multi(self):
        path = get_path_kvp(sd.jobs_service.path, status="{},{}".format(STATUS_SUCCEEDED, STATUS_RUNNING))
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        result_jobs = resp.json["jobs"]
        expect_jobs = [self.job_info[i].id for i in [0, 9, 10]]
        assert len(result_jobs) == 3
        assert all(job in expect_jobs for job in result_jobs)

    def test_get_jobs_by_status_invalid(self):
        path = get_path_kvp(sd.jobs_service.path, status="random")
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 422
        assert resp.json[""]

        path = get_path_kvp(sd.jobs_service.path, status="random,{}".format(STATUS_RUNNING))
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 422

    def test_get_job_status_response_process_id(self):
        """
        Verify the processID value in the job status response.
        """
        body = {
            "outputs": [],
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
        }
        with contextlib.ExitStack() as stack:
            for runner in mocked_process_job_runner():
                stack.enter_context(runner)
            path = "/processes/{}/jobs".format(self.process_public.identifier)
            resp = self.app.post_json(path, params=body, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == CONTENT_TYPE_APP_JSON

        assert resp.json["processID"] == "process-public"
