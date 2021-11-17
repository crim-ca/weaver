import os
from copy import deepcopy
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import pytest
from pyramid.httpexceptions import HTTPCreated, HTTPNotFound, HTTPOk, HTTPUnauthorized
from pyramid.settings import asbool

from tests.utils import get_setting
from tests.functional.test_workflow import WorkflowProcesses, WorkflowTestRunnerBase
from weaver.config import WEAVER_CONFIGURATION_EMS
from weaver.formats import CONTENT_TYPE_APP_FORM, CONTENT_TYPE_APP_JSON
from weaver.processes.sources import fetch_data_sources
from weaver.status import JOB_STATUS_CATEGORIES, JOB_STATUS_CATEGORY_RUNNING
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC

if TYPE_CHECKING:
    from typing import Iterable, Tuple

    from weaver.typedefs import CookiesType, HeadersType, SettingsType


@pytest.mark.functional
@pytest.mark.remote
@pytest.mark.slow
@pytest.mark.workflow
@pytest.mark.skipif(condition=not len(str(os.getenv("WEAVER_TEST_SERVER_HOSTNAME", ""))),
                    reason="Test server not defined!")
class WorkflowTestRunnerRemoteWithAuth(WorkflowTestRunnerBase):
    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is WorkflowTestRunnerBase)
        super(WorkflowTestRunnerRemoteWithAuth, self).__init__(*args, **kwargs)

    @classmethod
    def setup_test_processes_before(cls):
        # security configs if enabled
        cls.WEAVER_TEST_PROTECTED_ENABLED = asbool(cls.get_option("WEAVER_TEST_PROTECTED_ENABLED", False))
        cls.WEAVER_TEST_WSO2_CLIENT_HOSTNAME = cls.get_option("WEAVER_TEST_WSO2_CLIENT_HOSTNAME", "")
        cls.WEAVER_TEST_WSO2_CLIENT_ID = cls.get_option("WEAVER_TEST_WSO2_CLIENT_ID", "")
        cls.WEAVER_TEST_WSO2_CLIENT_SECRET = cls.get_option("WEAVER_TEST_WSO2_CLIENT_SECRET", "")
        cls.WEAVER_TEST_WSO2_URL = cls.get_option("WEAVER_TEST_WSO2_URL", "")
        cls.WEAVER_TEST_MAGPIE_URL = cls.get_option("WEAVER_TEST_MAGPIE_URL", "")
        cls.WEAVER_TEST_ADMIN_CREDENTIALS = {"username": get_setting("ADMIN_USERNAME", cls.app),
                                             "password": get_setting("ADMIN_PASSWORD", cls.app)}
        cls.WEAVER_TEST_ALICE_CREDENTIALS = {"username": get_setting("ALICE_USERNAME", cls.app),
                                             "password": get_setting("ALICE_PASSWORD", cls.app)}
        cls.WEAVER_TEST_BOB_CREDENTIALS = {"username": get_setting("BOD_USERNAME", cls.app),
                                           "password": get_setting("BOB_PASSWORD", cls.app)}

        # verify that servers are up and ready
        servers = [cls.WEAVER_URL]
        if cls.WEAVER_TEST_PROTECTED_ENABLED:
            servers.append(cls.WEAVER_TEST_WSO2_URL)
            servers.append(cls.WEAVER_TEST_MAGPIE_URL)
        for server_url in servers:
            cls.request("GET", server_url, headers=cls.headers, status=HTTPOk.code)
        # verify that EMS configuration requirement is met
        resp = cls.request("GET", cls.WEAVER_RESTAPI_URL, headers=cls.headers, status=HTTPOk.code)
        cls.assert_test(lambda: resp.json.get("configuration") == WEAVER_CONFIGURATION_EMS,
                        message="weaver must be configured as EMS.")

    @classmethod
    def clean_test_processes_before(cls):
        cls.headers, cls.cookies = cls.user_headers_cookies(cls.WEAVER_TEST_ADMIN_CREDENTIALS, force_magpie=True)

    @classmethod
    def clean_test_processes(cls, allowed_codes=None):
        allowed_codes = [HTTPOk.code, HTTPNotFound.code]
        if cls.WEAVER_TEST_PROTECTED_ENABLED:
            allowed_codes.append(HTTPUnauthorized.code)
        super(WorkflowTestRunnerRemoteWithAuth, cls).clean_test_processes(allowed_codes)

    @classmethod
    def clean_test_processes_iter_before(cls, process_info):
        path = "/processes/{}".format(process_info.test_id)

        # unauthorized when using Weaver directly means visibility is not public, but process definitively exists
        # update it to allow following delete
        if not cls.WEAVER_TEST_PROTECTED_ENABLED:
            resp = cls.request("GET", path,
                               headers=cls.headers, cookies=cls.cookies,
                               ignore_errors=True, log_enabled=False)
            if resp.status_code == HTTPUnauthorized.code:
                visibility_path = "{}/visibility".format(path)
                visibility_body = {"value": VISIBILITY_PUBLIC}
                resp = cls.request("PUT", visibility_path, json=visibility_body,
                                   headers=cls.headers, cookies=cls.cookies,
                                   ignore_errors=True, log_enabled=False)
                cls.assert_response(resp, HTTPOk.code, message="Failed cleanup of test processes!")

    @classmethod
    def get_http_auth_code(cls, unprotected_code=HTTPOk.code):
        # type: (int) -> int
        return HTTPUnauthorized.code if cls.WEAVER_TEST_PROTECTED_ENABLED else unprotected_code

    @classmethod
    def login(cls, username, password, force_magpie=False):
        # type: (str, str, bool) -> Tuple[HeadersType, CookiesType]
        """
        Login using WSO2 or Magpie according to ``WEAVER_TEST_PROTECTED_ENABLED`` to retrieve session cookies.

        WSO2:
            Retrieves the cookie packaged as `{"Authorization": "Bearer <access_token>"}` header, and lets the
            Magpie external provider login procedure complete the Authorization header => Cookie conversion.

        Magpie:
            Retrieves the cookie using a simple local user login.

        :returns: (Headers, Cookies) respectively to WSO2/Magpie login procedures.
        """
        if cls.WEAVER_TEST_PROTECTED_ENABLED:
            if force_magpie:
                data = {
                    "grant_type": "password",
                    "scope": "openid",
                    "client_id": cls.WEAVER_TEST_WSO2_CLIENT_ID,
                    "client_secret": cls.WEAVER_TEST_WSO2_CLIENT_SECRET,
                    "username": username,
                    "password": password
                }
                headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_FORM}
                path = "{}/oauth2/token".format(cls.WEAVER_TEST_WSO2_URL)
                resp = cls.request("POST", path, data=data, headers=headers, force_requests=True)
                if resp.status_code == HTTPOk.code:
                    access_token = resp.json().get("access_token")
                    cls.assert_test(lambda: access_token is not None, message="Failed login!")
                    return {"Authorization": "Bearer {}".format(access_token)}, {}
                cls.assert_response(resp, status=HTTPOk.code, message="Failed token retrieval from login!")
            else:
                data = {"user_name": username, "password": password}
                headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
                path = "{}/signin".format(cls.WEAVER_TEST_MAGPIE_URL)
                resp = cls.request("POST", path, json=data, headers=headers, force_requests=True)
                if resp.status_code == HTTPOk.code:
                    return {}, dict(resp.cookies)
                cls.assert_response(resp, status=HTTPOk.code, message="Failed token retrieval from login!")
        return {}, {}

    @classmethod
    def user_headers_cookies(cls, credentials, force_magpie=False):
        # type: (SettingsType, bool) -> Tuple[HeadersType, CookiesType]
        header_tokens, cookie_tokens = cls.login(force_magpie=force_magpie, **credentials)
        headers = deepcopy(cls.headers)
        cookies = deepcopy(cls.cookies)
        headers.update(header_tokens)
        cookies.update(cookie_tokens)
        return headers, cookies

    def workflow_runner_end2end_with_auth(self, test_workflow_id, test_application_ids, log_full_trace=False):
        # type: (WorkflowProcesses, Iterable[WorkflowProcesses], bool) -> None
        """
        Full workflow execution procedure with authentication enabled.
        """
        # End to end test will log everything
        self.__class__.log_full_trace = log_full_trace

        headers_a, cookies_a = self.user_headers_cookies(self.WEAVER_TEST_ALICE_CREDENTIALS)
        headers_b, cookies_b = self.user_headers_cookies(self.WEAVER_TEST_BOB_CREDENTIALS)

        # this test's set of processes
        test_processes_ids = list(test_application_ids) + [test_workflow_id]
        end2_end_test_processes = [self.get_test_process(process_id) for process_id in test_processes_ids]

        # list processes (none of tests)
        path = "/processes"
        resp = self.request("GET", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
        proc = resp.json.get("processes")
        test_processes = list(filter(lambda p: p["id"] in [tp.test_id for tp in end2_end_test_processes], proc))
        self.assert_test(lambda: len(test_processes) == 0, message="Test processes shouldn't exist!")

        # intermediate process deployment working
        # intermediate workflow deployment should fail because of missing last process
        last_proc_id = list(test_application_ids)[-1]
        for proc_id in test_application_ids[:-1]:
            self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code,
                         json=self.test_processes_info[proc_id].deploy_payload,
                         message="Expect deployed application process.")
            self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPNotFound.code,
                         json=self.test_processes_info[test_workflow_id].deploy_payload,
                         message="Expect deploy failure of workflow process with missing step.")
        # final process and workflow deployment should now succeed
        self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code,
                     json=self.test_processes_info[last_proc_id].deploy_payload,
                     message="Expect deployed application process.")
        self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code,
                     json=self.test_processes_info[test_workflow_id].deploy_payload,
                     message="Expect deployed workflow process.")

        # processes visible by alice
        resp = self.request("GET", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
        proc = resp.json.get("processes")
        test_processes = list(filter(lambda p: p["id"] in [tp.test_id for tp in end2_end_test_processes], proc))
        self.assert_test(lambda: len(test_processes) == len(end2_end_test_processes),
                         message="Test processes should exist.")

        # processes not yet visible by bob
        resp = self.request("GET", path, headers=headers_b, cookies=cookies_b, status=HTTPOk.code)
        proc = resp.json.get("processes")
        test_processes = list(filter(lambda p: p["id"] in [tp.test_id for tp in end2_end_test_processes], proc))
        self.assert_test(lambda: len(test_processes) == 0, message="Test processes shouldn't be visible by bob.")

        # processes visibility
        visible = {"value": VISIBILITY_PUBLIC}
        for process_info in self.test_processes_info.values():
            # get private visibility initially
            process_path = "/processes/{}".format(process_info.test_id)
            visible_path = "{}/visibility".format(process_path)
            execute_path = "{}/jobs".format(process_path)
            execute_body = process_info.execute_payload
            resp = self.request("GET", visible_path,
                                headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
            self.assert_test(lambda: resp.json.get("value") == VISIBILITY_PRIVATE, message="Process should be private.")

            # bob cannot edit, view or execute the process
            self.request("GET", process_path,
                         headers=headers_b, cookies=cookies_b, status=self.get_http_auth_code(HTTPOk.code))
            self.request("PUT", visible_path, json=visible,
                         headers=headers_b, cookies=cookies_b, status=self.get_http_auth_code(HTTPOk.code))
            self.request("POST", execute_path, json=execute_body,
                         headers=headers_b, cookies=cookies_b, status=self.get_http_auth_code(HTTPCreated.code))

            # make process visible
            resp = self.request("PUT", visible_path, json=visible,
                                headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
            self.assert_test(lambda: resp.json.get("value") == VISIBILITY_PUBLIC, message="Process should be public.")

            # bob still cannot edit, but can now view and execute the process
            self.request("PUT", visible_path, json=visible,
                         headers=headers_b, cookies=cookies_b, status=self.get_http_auth_code(HTTPOk.code))
            resp = self.request("GET", process_path, headers=headers_b, cookies=cookies_b, status=HTTPOk.code)
            self.assert_test(lambda: resp.json.get("process").get("id") == process_info.test_id,
                             message="Response process ID should match specified test process id.")
            resp = self.request("POST", execute_path, json=execute_body,
                                headers=headers_b, cookies=cookies_b, status=HTTPCreated.code)
            self.assert_test(lambda: resp.json.get("status") in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_RUNNING],
                             message="Response process execution job status should be one of running category values.")
            job_location = resp.json.get("location")
            job_id = resp.json.get("jobID")
            self.assert_test(lambda: job_id and job_location and job_location.endswith(job_id),
                             message="Response process execution job ID must match expected value to validate results.")
            self.validate_test_job_execution(job_location, headers_b, cookies_b)


# pylint: disable=C0103,invalid-name
@pytest.mark.functional
@pytest.mark.slow
@pytest.mark.workflow
class End2EndEMSTestCase(WorkflowTestRunnerRemoteWithAuth):
    """
    Runs an end-2-end test procedure on weaver configured as EMS located on specified `WEAVER_TEST_SERVER_HOSTNAME`.
    """
    WEAVER_TEST_APPLICATION_SET = {
        WorkflowProcesses.APP_STACKER,
        WorkflowProcesses.APP_SFS,
        WorkflowProcesses.APP_FLOOD_DETECTION,
        WorkflowProcesses.APP_ICE_DAYS,
        WorkflowProcesses.APP_SUBSET_BBOX,
        WorkflowProcesses.APP_SUBSET_ESGF,
        WorkflowProcesses.APP_SUBSET_NASA_ESGF
    }
    WEAVER_TEST_WORKFLOW_SET = {
        WorkflowProcesses.WORKFLOW_STACKER_SFS,
        WorkflowProcesses.WORKFLOW_SC,
        WorkflowProcesses.WORKFLOW_S2P,
        WorkflowProcesses.WORKFLOW_CUSTOM,
        WorkflowProcesses.WORKFLOW_FLOOD_DETECTION,
        WorkflowProcesses.WORKFLOW_SUBSET_ICE_DAYS,
        WorkflowProcesses.WORKFLOW_SUBSET_PICKER,
        WorkflowProcesses.WORKFLOW_SUBSET_LLNL_SUBSET_CRIM,
        WorkflowProcesses.WORKFLOW_SUBSET_NASA_ESGF_SUBSET_CRIM,
        WorkflowProcesses.WORKFLOW_FILE_TO_SUBSET_CRIM
    }

    @staticmethod
    def mock_get_data_source_from_url(data_url):
        forbidden_data_source = ["probav-l1-ades.vgt.vito.be",
                                 "probav-l2-ades.vgt.vito.be",
                                 "deimos-cubewerx"]
        data_sources = fetch_data_sources()
        try:
            parsed = urlparse(data_url)
            netloc, _, _ = parsed.netloc, parsed.path, parsed.scheme
            if netloc:
                for src, val in data_sources.items():
                    if src not in forbidden_data_source and val["netloc"] == netloc:
                        return src
        except Exception:  # noqa: W0703 # nosec: B110
            pass
        # Default mocked data source
        return "ipt-poland"

    @staticmethod
    def swap_data_collection():
        return [
            # Swap because Spacebel cannot retrieve probav images and Geomatys ADES is not ready
            # Geomatys ADES should be ready now!
            # ("EOP:VITO:PROBAV_S1-TOA_1KM_V001", "EOP:IPT:Sentinel2"),
        ]

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_original(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_STACKER_SFS,
                             [WorkflowProcesses.APP_STACKER, WorkflowProcesses.APP_SFS],
                             log_full_trace=True)

    def test_workflow_subset_picker(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_SUBSET_PICKER,
                             [WorkflowProcesses.APP_SUBSET_BBOX],  # other step is builtin
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_ice_days(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_SUBSET_ICE_DAYS,
                             [WorkflowProcesses.APP_SUBSET_BBOX, WorkflowProcesses.APP_ICE_DAYS],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_llnl_subset_esgf(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_SUBSET_LLNL_SUBSET_CRIM,
                             [WorkflowProcesses.APP_SUBSET_ESGF, WorkflowProcesses.APP_SUBSET_BBOX],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_esgf_requirements(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_SUBSET_NASA_ESGF_SUBSET_CRIM,
                             [WorkflowProcesses.APP_SUBSET_NASA_ESGF, WorkflowProcesses.APP_SUBSET_BBOX],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_file_to_string_array(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_FILE_TO_SUBSET_CRIM,
                             [WorkflowProcesses.APP_SUBSET_BBOX],  # other step is builtin
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_simple_chain(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_SC,
                             [WorkflowProcesses.APP_STACKER, WorkflowProcesses.APP_SFS])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_S2_and_ProbaV(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_S2P,
                             [WorkflowProcesses.APP_STACKER, WorkflowProcesses.APP_SFS])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_custom(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_CUSTOM,
                             [WorkflowProcesses.APP_STACKER, WorkflowProcesses.APP_SFS])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_flood_detection(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_FLOOD_DETECTION,
                             [WorkflowProcesses.APP_STACKER, WorkflowProcesses.APP_FLOOD_DETECTION])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_end2end_with_auth(self):
        self.workflow_runner_end2end_with_auth(WorkflowProcesses.WORKFLOW_STACKER_SFS,
                                               [WorkflowProcesses.APP_STACKER, WorkflowProcesses.APP_SFS])
