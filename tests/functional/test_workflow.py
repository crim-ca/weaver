"""
Test processes consisting of a Workflow of sub-processes defining Application Package.
"""

import contextlib
import enum
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING
from unittest import TestCase
from urllib.parse import urlparse

import mock
import pytest
import yaml
from pyramid import testing
from pyramid.httpexceptions import HTTPCreated, HTTPNotFound, HTTPOk
from pyramid.settings import asbool
# use 'Web' prefix to avoid pytest to pick up these classes and throw warnings
from webtest import TestApp as WebTestApp

from tests.utils import (
    get_settings_from_config_ini,
    get_settings_from_testapp,
    get_test_weaver_app,
    mocked_execute_process,
    mocked_sub_requests,
    mocked_wps_output,
    setup_config_with_mongodb
)
from weaver import WEAVER_ROOT_DIR
from weaver.config import WEAVER_CONFIGURATION_EMS, WEAVER_CONFIGURATION_HYBRID
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.status import (
    JOB_STATUS_CATEGORIES,
    JOB_STATUS_CATEGORY_FINISHED,
    JOB_STATUS_CATEGORY_RUNNING,
    JOB_STATUS_VALUES,
    STATUS_ACCEPTED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED
)
from weaver.utils import get_weaver_url, make_dirs, now, request_extra
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Iterable, Optional, Set, Union

    from weaver.typedefs import AnyResponseType, CookiesType, HeadersType, JSON, SettingsType


class WorkflowProcesses(enum.Enum):
    """
    Known process ID definitions for tests.
    """
    APP_STACKER = "Stacker"
    APP_SFS = "SFS"
    APP_FLOOD_DETECTION = "FloodDetection"
    APP_ICE_DAYS = "Finch_IceDays"
    APP_SUBSET_BBOX = "ColibriFlyingpigeon_SubsetBbox"
    APP_SUBSET_ESGF = "SubsetESGF"
    APP_SUBSET_NASA_ESGF = "SubsetNASAESGF"
    APP_DOCKER_STAGE_IMAGES = "DockerStageImages"
    APP_DOCKER_COPY_IMAGES = "DockerCopyImages"
    WORKFLOW_STACKER_SFS = "Workflow"
    WORKFLOW_SC = "WorkflowSimpleChain"
    WORKFLOW_S2P = "WorkflowS2ProbaV"
    WORKFLOW_CUSTOM = "CustomWorkflow"
    WORKFLOW_FLOOD_DETECTION = "WorkflowFloodDetection"
    WORKFLOW_SUBSET_ICE_DAYS = "WorkflowSubsetIceDays"
    WORKFLOW_SUBSET_PICKER = "WorkflowSubsetPicker"
    WORKFLOW_SUBSET_LLNL_SUBSET_CRIM = "WorkflowSubsetLLNL_SubsetCRIM"
    WORKFLOW_SUBSET_NASA_ESGF_SUBSET_CRIM = "WorkflowSubsetNASAESGF_SubsetCRIM"
    WORKFLOW_FILE_TO_SUBSET_CRIM = "WorkflowFile_To_SubsetCRIM"
    WORKFLOW_STAGE_COPY_IMAGES = "WorkflowStageCopyImages"


class ProcessInfo(object):
    """
    Container to preserve details loaded from 'application-packages' definitions.
    """
    def __init__(self, process_id, test_id=None, deploy_payload=None, execute_payload=None):
        # type: (Union[str, WorkflowProcesses], Optional[str], Optional[JSON], Optional[JSON]) -> None
        self.pid = WorkflowProcesses(process_id)
        self.id = self.pid.value
        self.test_id = test_id
        self.deploy_payload = deploy_payload
        self.execute_payload = execute_payload


@pytest.mark.functional
@pytest.mark.workflow
class WorkflowTestRunnerBase(TestCase):
    """
    Runs an end-2-end test procedure on weaver configured as EMS located on specified `WEAVER_TEST_SERVER_HOSTNAME`.
    """
    __settings__ = None
    test_processes_info = dict()    # type: Dict[WorkflowProcesses, ProcessInfo]
    headers = {
        "Accept": CONTENT_TYPE_APP_JSON,
        "Content-Type": CONTENT_TYPE_APP_JSON,
    }                               # type: HeadersType
    cookies = dict()                # type: CookiesType
    app = None                      # type: Optional[WebTestApp]
    logger_result_dir = None        # type: Optional[str]
    logger_separator_calls = ""     # type: str
    logger_separator_steps = ""     # type: str
    logger_separator_tests = ""     # type: str
    logger_separator_cases = ""     # type: str
    logger_level = logging.INFO     # type: int
    logger_enabled = True           # type: bool
    logger = None                   # type: Optional[logging.Logger]
    # setting indent to `None` disables pretty-printing of JSON payload
    logger_json_indent = None       # type: Optional[int]
    logger_field_indent = 2         # type: int
    log_full_trace = True           # type: bool

    WEAVER_URL = None               # type: Optional[str]
    WEAVER_RESTAPI_URL = None       # type: Optional[str]

    # application and workflow process identifiers to prepare using definitions in 'application-packages' directory
    # must be overridden by derived test classes
    WEAVER_TEST_APPLICATION_SET = set()     # type: Set[WorkflowProcesses]
    WEAVER_TEST_WORKFLOW_SET = set()        # type: Set[WorkflowProcesses]

    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is WorkflowTestRunnerBase)
        super(WorkflowTestRunnerBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        # disable SSL warnings from logs
        try:
            import urllib3  # noqa
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass

        # logging parameter overrides
        cls.logger_level = cls.get_option("WEAVER_TEST_LOGGER_LEVEL", cls.logger_level) or cls.logger_level
        if isinstance(cls.logger_level, str):
            cls.logger_level = logging.getLevelName(cls.logger_level)
        cls.logger_enabled = asbool(cls.get_option("WEAVER_TEST_LOGGER_ENABLED", cls.logger_enabled))
        cls.logger_result_dir = cls.get_option("WEAVER_TEST_LOGGER_RESULT_DIR", os.path.join(WEAVER_ROOT_DIR))
        cls.logger_json_indent = cls.get_option("WEAVER_TEST_LOGGER_JSON_INDENT", cls.logger_json_indent)
        cls.logger_field_indent = cls.get_option("WEAVER_TEST_LOGGER_FIELD_INDENT", cls.logger_field_indent)
        cls.logger_separator_calls = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_CALLS", cls.logger_separator_calls)
        cls.logger_separator_steps = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_STEPS", cls.logger_separator_steps)
        cls.logger_separator_tests = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_TESTS", cls.logger_separator_tests)
        cls.logger_separator_cases = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_CASES", cls.logger_separator_cases)
        cls.setup_logger()
        cls.log("{}Start of '{}': {}\n{}"
                .format(cls.logger_separator_cases, cls.current_case_name(), now(), cls.logger_separator_cases))

        # test execution configs
        cls.WEAVER_TEST_REQUEST_TIMEOUT = int(cls.get_option("WEAVER_TEST_REQUEST_TIMEOUT", 10))
        cls.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT = int(cls.get_option("WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT", 30))
        cls.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT = int(cls.get_option("WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT", 6000))
        cls.WEAVER_TEST_JOB_GET_STATUS_INTERVAL = int(cls.get_option("WEAVER_TEST_JOB_GET_STATUS_INTERVAL", 5))

        # server settings
        cls.WEAVER_TEST_CONFIGURATION = cls.get_option("WEAVER_TEST_CONFIGURATION", WEAVER_CONFIGURATION_EMS)
        cls.WEAVER_TEST_SERVER_HOSTNAME = cls.get_option("WEAVER_TEST_SERVER_HOSTNAME", "")
        cls.WEAVER_TEST_SERVER_BASE_PATH = cls.get_option("WEAVER_TEST_SERVER_BASE_PATH", "/weaver")
        cls.WEAVER_TEST_SERVER_API_PATH = cls.get_option("WEAVER_TEST_SERVER_API_PATH", "/")
        cls.WEAVER_TEST_CONFIG_INI_PATH = cls.get_option("WEAVER_TEST_CONFIG_INI_PATH")    # none uses default path
        if cls.WEAVER_TEST_SERVER_HOSTNAME in [None, ""]:
            # running with a local-only Web Test application
            config = setup_config_with_mongodb(settings={
                "weaver.configuration": cls.WEAVER_TEST_CONFIGURATION,
                # NOTE:
                #   Because everything is running locally in this case, all processes should automatically map between
                #   the two following dir/URL as equivalents locations, accordingly to what they require for execution.
                #   Because of this, there is no need to mock any file servicing for WPS output URL for local test app.
                #   The only exception is the HEAD request that validates accessibility of intermediate files. If any
                #   other HTTP 404 errors arise with this WPS output URL endpoint, it is most probably because file path
                #   or mapping was incorrectly handled at some point when passing references between Workflow steps.
                "weaver.wps_output_url": "http://localhost/wps-outputs",
                "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
            })
            cls.app = get_test_weaver_app(config=config)
            cls.__settings__ = get_settings_from_testapp(cls.app)  # override settings to avoid re-setup by method
            os.makedirs(cls.__settings__["weaver.wps_output_dir"], exist_ok=True)
        else:
            # running on a remote service (remote server or can be "localhost", but in parallel application)
            if cls.WEAVER_TEST_SERVER_HOSTNAME.startswith("http"):
                url = cls.WEAVER_TEST_SERVER_HOSTNAME
            else:
                url = "http://{}".format(cls.WEAVER_TEST_SERVER_HOSTNAME)
            cls.app = WebTestApp(url)
            cls.WEAVER_URL = get_weaver_url(cls.settings())
        cls.WEAVER_RESTAPI_URL = get_wps_restapi_base_url(cls.settings())

        # validation
        cls.setup_test_processes_before()
        cls.setup_test_processes()
        cls.setup_test_processes_after()

    @classmethod
    def tearDownClass(cls):
        cls.clean_test_processes()
        testing.tearDown()
        cls.log("{}End of '{}': {}\n{}"
                .format(cls.logger_separator_cases, cls.current_case_name(), now(), cls.logger_separator_cases))

    def setUp(self):
        # reset in case it was modified during another test
        self.__class__.log_full_trace = True

        self.log("{}Start of '{}': {}\n{}"
                 .format(self.logger_separator_tests, self.current_test_name(), now(), self.logger_separator_tests))

        # cleanup old processes as required
        self.clean_test_processes_before()
        self.clean_test_processes()
        self.clean_test_processes_after()

    def tearDown(self):
        self.log("{}End of '{}': {}\n{}"
                 .format(self.logger_separator_tests, self.current_test_name(), now(), self.logger_separator_tests))

    @classmethod
    def setup_test_processes_before(cls):
        """
        Hook available to subclasses for any operation required before configuring test processes.
        """

    @classmethod
    def setup_test_processes_after(cls):
        """
        Hook available to subclasses for any operation required after configuring test processes.
        """

    @classmethod
    def setup_test_processes(cls):
        # type: (...) -> None
        test_set = cls.WEAVER_TEST_APPLICATION_SET | cls.WEAVER_TEST_WORKFLOW_SET
        for process in test_set:
            cls.test_processes_info.update({process: cls.retrieve_process_info(process)})

        # replace max occur of processes to minimize data size during tests
        for process_id in test_set:
            process_deploy = cls.test_processes_info[process_id].deploy_payload
            process_deploy_inputs = process_deploy["processDescription"].get("process", {}).get("inputs")
            if process_deploy_inputs:
                for i_input, proc_input in enumerate(process_deploy_inputs):
                    if proc_input.get("maxOccurs") == "unbounded":
                        process_deploy_inputs[i_input]["maxOccurs"] = str(2)

        # update workflows to use "test_id" instead of originals
        raw_app_ids = [app.value for app in cls.WEAVER_TEST_APPLICATION_SET]
        for workflow_id in cls.WEAVER_TEST_WORKFLOW_SET:
            workflow_deploy = cls.test_processes_info[workflow_id].deploy_payload
            for exec_unit in range(len(workflow_deploy["executionUnit"])):
                try:
                    workflow_cwl_ref = workflow_deploy["executionUnit"][exec_unit].pop("href")
                    workflow_cwl_raw = cls.retrieve_payload(workflow_cwl_ref)
                except KeyError:
                    workflow_cwl_raw = workflow_deploy["executionUnit"][exec_unit].pop("unit")
                for step in workflow_cwl_raw.get("steps"):
                    step_id = workflow_cwl_raw["steps"][step]["run"].strip(".cwl")
                    for raw_app_id in raw_app_ids:
                        if raw_app_id == step_id:
                            app_id = WorkflowProcesses(raw_app_id)
                            test_id = cls.test_processes_info[app_id].test_id
                            real_id = workflow_cwl_raw["steps"][step]["run"]
                            workflow_cwl_raw["steps"][step]["run"] = real_id.replace(raw_app_id, test_id)
                workflow_deploy["executionUnit"][exec_unit]["unit"] = workflow_cwl_raw

    @classmethod
    def setup_logger(cls):
        if cls.logger_enabled:
            if not isinstance(cls.logger_level, int):
                cls.logger_level = logging.getLevelName(cls.logger_level)
            make_dirs(cls.logger_result_dir, exist_ok=True)
            log_path = os.path.abspath(os.path.join(cls.logger_result_dir, cls.__name__ + ".log"))
            log_fmt = logging.Formatter("%(message)s")  # only message to avoid 'log-name INFO' offsetting outputs
            log_file = logging.FileHandler(log_path)
            log_file.setFormatter(log_fmt)
            log_term = logging.StreamHandler()
            log_term.setFormatter(log_fmt)
            cls.logger_separator_calls = "-" * 80 + "\n"  # used between function calls (of same request)
            cls.logger_separator_steps = "=" * 80 + "\n"  # used between overall test steps (between requests)
            cls.logger_separator_tests = "*" * 80 + "\n"  # used between various test runs (each test_* method)
            cls.logger_separator_cases = "#" * 80 + "\n"  # used between various TestCase runs
            cls.logger = logging.getLogger(cls.__name__)
            cls.logger.setLevel(cls.logger_level)
            cls.logger.addHandler(log_file)
            cls.logger.addHandler(log_term)

    @classmethod
    def get_option(cls, env, default=None):
        val = getattr(cls, env, None)
        if val is None:
            return os.getenv(env, default)
        return val

    @classmethod
    def log(cls, message, exception=False):
        if cls.logger_enabled:
            if exception:
                # also prints traceback of the exception
                cls.logger.exception(message)
            else:
                cls.logger.log(cls.logger_level, message)
        if exception:
            raise RuntimeError(message)

    @classmethod
    def get_indent(cls, indent_level):
        # type: (int) -> str
        return " " * cls.logger_field_indent * indent_level

    @classmethod
    def indent(cls, field, indent_level):
        # type: (str, int) -> str
        return cls.get_indent(indent_level) + field

    @classmethod
    def log_json_format(cls, payload, indent_level):
        # type: (str, int) -> str
        """
        Logs an indented string representation of a JSON payload according to settings.
        """
        sub_indent = cls.get_indent(indent_level if cls.logger_json_indent else 0)
        log_payload = "\n" if cls.logger_json_indent else "" + json.dumps(payload, indent=cls.logger_json_indent)
        log_payload.replace("\n", "\n{}".format(sub_indent))
        if log_payload.endswith("\n"):
            return log_payload[:-1]  # remove extra line, let logger message generation add it explicitly
        return log_payload

    @classmethod
    def log_dict_format(cls, dictionary, indent_level):
        """
        Logs dictionary (key, value) pairs in a YAML-like format.
        """
        if dictionary is None:
            return None

        tab = "\n" + cls.get_indent(indent_level)
        return tab + "{tab}".format(tab=tab).join(["{}: {}".format(k, dictionary[k]) for k in sorted(dictionary)])

    @classmethod
    def clean_test_processes_before(cls):
        """
        Hook available to subclasses for any operation required before cleanup of all test processes.
        """

    @classmethod
    def clean_test_processes_after(cls):
        """
        Hook available to subclasses for any operation required after cleanup of all test processes.
        """

    @classmethod
    def clean_test_processes_iter_before(cls, process_info):
        # type: (ProcessInfo) -> None
        """
        Hook available to subclasses for any operation required before cleanup of each individual process.
        """

    @classmethod
    def clean_test_processes_iter_after(cls, process_info):
        # type: (ProcessInfo) -> None
        """
        Hook available to subclasses for any operation required after cleanup of each individual process.
        """

    @classmethod
    def clean_test_processes(cls, allowed_codes=frozenset([HTTPOk.code, HTTPNotFound.code])):
        for process_info in cls.test_processes_info.values():
            cls.clean_test_processes_iter_before(process_info)
            path = "/processes/{}".format(process_info.test_id)
            resp = cls.request("DELETE", path,
                               headers=cls.headers, cookies=cls.cookies,
                               ignore_errors=True, log_enabled=False)
            cls.clean_test_processes_iter_after(process_info)
            cls.assert_response(resp, allowed_codes, message="Failed cleanup of test processes!")

    @staticmethod
    def mock_get_data_source_from_url(data_url):
        # type: (str) -> str
        """
        Hook available to subclasses to mock any data-source resolution to remote ADES based on data reference URL.
        """

    @staticmethod
    def swap_data_collection():
        # type: () -> Iterable[str]
        """
        Hook available to subclasses to substitute any known collection to data references during resolution.
        """
        return []

    @classmethod
    def current_case_name(cls):
        return cls.__name__

    def current_test_name(self):
        return self.id().split(".")[-1]

    @classmethod
    def settings(cls):
        # type: (...) -> SettingsType
        """
        Provide basic settings that must be defined to use various weaver utility functions.
        """
        if not cls.__settings__:
            weaver_url = os.getenv("WEAVER_URL", "{}{}".format(cls.WEAVER_TEST_SERVER_HOSTNAME,
                                                               cls.WEAVER_TEST_SERVER_BASE_PATH))
            if not weaver_url.startswith("http"):
                if not weaver_url.startswith("/") and weaver_url != "":
                    weaver_url = "http://{}".format(weaver_url)
            cls.__settings__ = get_settings_from_testapp(cls.app)
            cls.__settings__.update(get_settings_from_config_ini(cls.WEAVER_TEST_CONFIG_INI_PATH))
            cls.__settings__.update({
                "weaver.url": weaver_url,
                "weaver.configuration": cls.WEAVER_TEST_CONFIGURATION,
                "weaver.wps_restapi_path": cls.WEAVER_TEST_SERVER_API_PATH,
                "weaver.request_options": {},
            })
        return cls.__settings__

    @classmethod
    def get_test_process(cls, process_id):
        # type: (WorkflowProcesses) -> ProcessInfo
        return cls.test_processes_info.get(process_id)

    @classmethod
    def retrieve_process_info(cls, process_id):
        # type: (WorkflowProcesses) -> ProcessInfo
        base = os.getenv("TEST_GITHUB_SOURCE_URL",
                         "https://raw.githubusercontent.com/crim-ca/testbed14/master/application-packages")
        pid = process_id.value
        deploy_path = "{base}/{proc}/DeployProcess_{proc}.json".format(base=base, proc=pid)
        execute_path = "{base}/{proc}/Execute_{proc}.json".format(base=base, proc=pid)
        deploy_payload = cls.retrieve_payload(deploy_path)
        new_process_id = cls.get_test_process_id(deploy_payload["processDescription"]["process"]["id"])
        deploy_payload["processDescription"]["process"]["id"] = new_process_id
        execute_payload = cls.retrieve_payload(execute_path)

        # Apply collection swapping
        for swap in cls.swap_data_collection():
            for i in execute_payload["inputs"]:
                if "data" in i and i["data"] == swap[0]:
                    i["data"] = swap[1]

        return ProcessInfo(process_id, new_process_id, deploy_payload, execute_payload)

    @classmethod
    def retrieve_payload(cls, url):
        # type: (str) -> Dict
        local_path = os.path.join(os.path.dirname(__file__), "application-packages", url.split("/")[-1])
        try:
            # Try to find it locally, then fallback to remote
            if os.path.isfile(local_path):
                with open(local_path, "r") as f:
                    json_payload = yaml.safe_load(f)  # both JSON/YAML
                    return json_payload
            if urlparse(url).scheme != "":
                resp = cls.request("GET", url, force_requests=True, ignore_errors=True)
                if resp.status_code == HTTPOk.code:
                    return yaml.safe_load(resp.text)  # both JSON/YAML
        except (IOError, ValueError):
            pass
        cls.log("{}Cannot find payload from either references:\n[{}]\n[{}]\n"
                .format(cls.logger_separator_calls, url, local_path), exception=True)

    @classmethod
    def get_test_process_id(cls, real_process_id):
        # type: (str) -> str
        return "{}_{}".format(cls.__name__, real_process_id)

    @classmethod
    def assert_response(cls, response, status=None, message=""):
        # type: (AnyResponseType, Optional[Union[int, Iterable[int]]], str) -> None
        """
        Tests a response for expected status and raises an error if not matching.
        """
        code = response.status_code
        reason = getattr(response, "reason", "")
        reason = str(reason) + " " if reason else ""
        content = getattr(response, "content", "")
        req_url = ""
        req_body = ""
        req_method = ""
        if hasattr(response, "request"):
            req_url = getattr(response.request, "url", "")
            req_body = getattr(response.request, "body", "")
            req_method = getattr(response.request, "method", "")
            message = "{}, {}".format(message, content) if content else message
        status = [status] if status is not None and not hasattr(status, "__iter__") else status
        if status is not None:
            expect_msg = "Expected status in: {}".format(status)
            expect_code = code in status
        else:
            expect_msg = "Expected status: <= 400"
            expect_code = code <= 400
        msg = "Unexpected HTTP Status: {} {}[{}]\n{}\nFrom: [{} {} {}]".format(
            response.status_code, reason, message, expect_msg, req_method, req_url, req_body
        )
        cls.assert_test(lambda: expect_code, message=msg, title="Response Assertion Failed")

    @classmethod
    def assert_test(cls, assert_test, message=None, title="Test Assertion Failed"):
        # type: (Callable[[], bool], Optional[str], str) -> None
        """
        Tests a callable for assertion and logs the message if it fails, then re-raises to terminate execution.
        """
        try:
            assert assert_test(), message
        except AssertionError:
            cls.log("{}{}:\n{}\n".format(cls.logger_separator_calls, title, message), exception=True)

    @classmethod
    def is_local(cls):
        if not cls.WEAVER_URL:
            return False
        url_parsed = urlparse(cls.WEAVER_URL)
        return url_parsed.hostname in ["localhost", "127.0.0.1"]  # not Web TestApp, literal debug instance

    @classmethod
    def is_remote(cls):
        test_app = cls.app.app
        return hasattr(test_app, "net_loc") and test_app.net_loc not in ["", "localhost"] and not cls.is_local()

    @classmethod
    def is_webtest(cls):
        return not cls.is_local() and not cls.is_remote()

    @classmethod
    def request(cls, method, url, ignore_errors=False, force_requests=False, log_enabled=True, **kw):
        # type: (str, str, bool, bool, bool, Optional[Any]) -> AnyResponseType
        """
        Executes the request, but following any server prior redirects as needed.

        Also prepares JSON body and obvious error handling according to a given status code.
        """
        expect_errors = kw.pop("expect_errors", ignore_errors)
        message = kw.pop("message", None)
        json_body = kw.pop("json", None)
        data_body = kw.pop("data", None)
        status = kw.pop("status", None)
        method = method.upper()
        headers = kw.get("headers", {})
        cookies = kw.get("cookies", {})

        # use `requests.Request` with cases that doesn't work well with `webtest.TestApp`
        url_parsed = urlparse(url)
        has_port = url_parsed.port is not None
        with_requests = cls.is_local() and has_port or cls.is_remote() or force_requests
        with_mock_req = cls.is_webtest()

        if cls.WEAVER_URL and url.startswith("/") or url == "" and not with_mock_req:
            url = "{}{}".format(cls.WEAVER_URL, url)

        if not json_body and data_body and headers and CONTENT_TYPE_APP_JSON in headers.get("Content-Type"):
            json_body = data_body
            data_body = None

        if log_enabled:
            if json_body:
                payload = cls.log_json_format(json_body, 2)
            else:
                payload = data_body
            trace = ("{}Request Details:\n".format(cls.logger_separator_steps) +
                     cls.indent("Request: {method} {url}\n".format(method=method, url=url), 1) +
                     cls.indent("Payload: {payload}".format(payload=payload), 1))
            if cls.log_full_trace:
                module_name = "requests" if with_requests else "webtest.TestApp"
                headers = cls.log_dict_format(headers, 2)
                cookies = cls.log_dict_format(cookies, 2)
                trace += ("\n" +
                          cls.indent("Headers: {headers}\n".format(headers=headers), 1) +
                          cls.indent("Cookies: {cookies}\n".format(cookies=cookies), 1) +
                          cls.indent("Status:  {status} (expected)\n".format(status=status), 1) +
                          cls.indent("Message: {message} (expected)\n".format(message=message), 1) +
                          cls.indent("Module:  {module}\n".format(module=module_name), 1))
            cls.log(trace)

        if with_requests:
            kw.update({"verify": False, "timeout": cls.WEAVER_TEST_REQUEST_TIMEOUT})
            # retry request if the error was caused by some connection error
            resp = request_extra(method, url, json=json_body, data=data_body, retries=3, settings=cls.settings(), **kw)

            # add some properties similar to `webtest.TestApp`
            resp_body = getattr(resp, "body", None)  # if error is pyramid HTTPException, body is byte only
            if CONTENT_TYPE_APP_JSON in resp.headers.get("Content-Type", []):
                if resp_body is None:
                    setattr(resp, "body", resp.json)
                setattr(resp, "json", resp.json())
                setattr(resp, "content_type", CONTENT_TYPE_APP_JSON)
            else:
                if resp_body is None:
                    setattr(resp, "body", resp.text)
                setattr(resp, "content_type", resp.headers.get("Content-Type"))

        else:
            max_redirects = kw.pop("max_redirects", 5)
            # 'mocked_sub_requests' detects 'params' as query and converts 'data' to 'params'
            body_key = "data" if with_mock_req else "params"
            if json_body is not None:
                kw.update({body_key: json.dumps(json_body, cls=json.JSONEncoder)})
            kw.update({"expect_errors": status and status >= 400 or expect_errors})
            cookies = kw.pop("cookies", dict()) or {}
            for cookie_name, cookie_value in cookies.items():
                cls.app.set_cookie(cookie_name, cookie_value)

            if with_mock_req:
                # NOTE:
                #  Very important to mock requests only matching local test application.
                #  Otherwise, other mocks like 'mock_wps_output' cannot do their job since no real request gets fired.
                resp = mocked_sub_requests(cls.app, method, url, only_local=True, **kw)
            else:
                resp = cls.app._gen_request(method, url, **kw)

            while 300 <= resp.status_code < 400 and max_redirects > 0:
                resp = resp.follow()
                max_redirects -= 1
            cls.assert_test(lambda: max_redirects >= 0, message="Maximum redirects reached for request.")
            cls.app.reset()  # reset cookies as required

        if not ignore_errors:
            cls.assert_response(resp, status, message)

        if log_enabled:
            if CONTENT_TYPE_APP_JSON in resp.headers.get("Content-Type", []):
                payload = cls.log_json_format(resp.json, 2)  # noqa
            else:
                payload = resp.body
            if cls.log_full_trace:
                headers = resp.headers
            else:
                header_filter = ["Location"]
                headers = {k: v for k, v in resp.headers.items() if k in header_filter}
            headers = cls.log_dict_format(headers, 2)
            cls.log("{}Response Details:\n".format(cls.logger_separator_calls) +
                    cls.indent("Status:  {status} (received)\n".format(status=resp.status_code), 1) +
                    cls.indent("Content: {content}\n".format(content=resp.content_type), 1) +
                    cls.indent("Payload: {payload}\n".format(payload=payload), 1) +
                    cls.indent("Headers: {headers}\n".format(headers=headers), 1))
        return resp

    def workflow_runner(self, test_workflow_id, test_application_ids, log_full_trace=False):
        # type: (WorkflowProcesses, Iterable[WorkflowProcesses], bool) -> None
        """
        Simplify test for demonstration purpose.
        """

        # test will log basic information
        self.__class__.log_full_trace = log_full_trace

        # deploy processes and make them visible for workflow
        path_deploy = "/processes"
        for process_id in test_application_ids:
            path_visible = "{}/{}/visibility".format(path_deploy, self.test_processes_info[process_id].test_id)
            data_visible = {"value": VISIBILITY_PUBLIC}
            self.request("POST", path_deploy, status=HTTPCreated.code, headers=self.headers,
                         json=self.test_processes_info[process_id].deploy_payload,
                         message="Expect deployed application process.")
            self.request("PUT", path_visible, status=HTTPOk.code, headers=self.headers, json=data_visible,
                         message="Expect visible application process.")

        # deploy workflow process itself and make visible
        workflow_info = self.test_processes_info[test_workflow_id]
        self.request("POST", path_deploy, status=HTTPCreated.code, headers=self.headers,
                     json=workflow_info.deploy_payload,
                     message="Expect deployed workflow process.")
        process_path = "{}/{}".format(path_deploy, workflow_info.test_id)
        visible_path = "{}/visibility".format(process_path)
        visible = {"value": VISIBILITY_PUBLIC}
        resp = self.request("PUT", visible_path, json=visible, status=HTTPOk.code, headers=self.headers)
        self.assert_test(lambda: resp.json.get("value") == VISIBILITY_PUBLIC,
                         message="Process should be public.")

        with contextlib.ExitStack() as stack_exec:
            stack_exec.enter_context(mock.patch("weaver.processes.sources.get_data_source_from_url",
                                                side_effect=self.mock_get_data_source_from_url))
            if self.is_webtest():
                # mock execution when running on local Web Test app since no Celery runner is available
                for mock_exec in mocked_execute_process():
                    stack_exec.enter_context(mock_exec)
                # mock HTTP HEAD request to validate WPS output access (see 'setUpClass' details)
                stack_exec.enter_context(mocked_wps_output(self.settings(), mock_head=True, mock_get=False))

            # execute workflow
            execute_body = workflow_info.execute_payload
            execute_path = "{}/jobs".format(process_path)
            resp = self.request("POST", execute_path, status=HTTPCreated.code,
                                headers=self.headers, json=execute_body)
            self.assert_test(lambda: resp.json.get("status") in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_RUNNING],
                             message="Response process execution job status should be one of running values.")
            job_location = resp.json.get("location")
            job_id = resp.json.get("jobID")
            self.assert_test(lambda: job_id and job_location and job_location.endswith(job_id),
                             message="Response process execution job ID must match to validate results.")
            self.validate_test_job_execution(job_location, None, None)

    def validate_test_job_execution(self, job_location_url, user_headers=None, user_cookies=None):
        # type: (str, Optional[HeadersType], Optional[CookiesType]) -> None
        """
        Validates that the job is stated, running, and polls it until completed successfully.

        Then validates that results are accessible (no data integrity check).
        """
        timeout_accept = self.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT
        timeout_running = self.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT
        while True:
            self.assert_test(
                lambda: timeout_accept > 0,
                message="Maximum timeout reached for job execution test. " +
                        "Expected job status change from '{0}' to '{1}' within {2}s since first '{0}'."
                        .format(STATUS_ACCEPTED, STATUS_RUNNING, self.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT))
            self.assert_test(
                lambda: timeout_running > 0,
                message="Maximum timeout reached for job execution test. " +
                        "Expected job status change from '{0}' to '{1}' within {2}s since first '{0}'."
                        .format(STATUS_RUNNING, STATUS_SUCCEEDED, self.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT))
            resp = self.request("GET", job_location_url,
                                headers=user_headers, cookies=user_cookies, status=HTTPOk.code)
            status = resp.json.get("status")
            self.assert_test(lambda: status in JOB_STATUS_VALUES,
                             message="Cannot identify a valid job status for result validation.")
            if status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_RUNNING]:
                if status == STATUS_ACCEPTED:
                    timeout_accept -= self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL
                else:
                    timeout_running -= self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL
                time.sleep(self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL)
                continue
            if status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_FINISHED]:
                msg = "Job execution '{}' failed, but expected to succeed.".format(job_location_url)
                failed = status != STATUS_SUCCEEDED
                if failed:
                    msg += "\n" + self.try_retrieve_logs(job_location_url)
                self.assert_test(lambda: not failed, message=msg)
                break
            self.assert_test(lambda: False, message="Unknown job execution status: '{}'.".format(status))
        self.request("GET", "{}/result".format(job_location_url),
                     headers=user_headers, cookies=user_cookies, status=HTTPOk.code)

    def try_retrieve_logs(self, workflow_job_url):
        """
        Attempt to retrieve the main workflow job logs and any underlying step process logs.

        Because jobs are dispatched by the Workflow execution itself, there are no handles to the actual step jobs here.
        Try to parse the workflow logs to guess output logs URLs. If not possible, skip silently.
        """
        try:
            msg = ""
            path = workflow_job_url + "/logs"
            resp = self.request("GET", path, ignore_errors=True)
            if resp.status_code == 200 and isinstance(resp.json, list):
                logs = resp.json
                job_id = workflow_job_url.split("/")[-1]
                tab_n = "\n" + self.indent("", 1)
                workflow_logs = tab_n.join(logs)
                msg += "Workflow logs [JobID: {}]".format(job_id) + tab_n + workflow_logs
                log_matches = set(re.findall(r".*(https?://.+/logs).*", workflow_logs)) - {workflow_job_url}
                log_refs = {}
                for log_url in log_matches:
                    job_id = log_url.split("/")[-2]
                    log_refs[job_id] = log_url
                for job_id, log_url in log_refs.items():
                    resp = self.request("GET", log_url, ignore_errors=True)
                    if resp.status_code == 200 and isinstance(resp.json, list):
                        step_logs = tab_n.join(resp.json)
                        msg += "\nStep process logs [JobID: {}]".format(job_id) + tab_n + step_logs
        except Exception:
            return "Could not retrieve job logs."
        return msg


class WorkflowTestCase(WorkflowTestRunnerBase):
    WEAVER_TEST_CONFIGURATION = WEAVER_CONFIGURATION_HYBRID
    WEAVER_TEST_SERVER_BASE_PATH = ""

    WEAVER_TEST_APPLICATION_SET = {
        WorkflowProcesses.APP_DOCKER_STAGE_IMAGES,
        WorkflowProcesses.APP_DOCKER_COPY_IMAGES
    }
    WEAVER_TEST_WORKFLOW_SET = {
        WorkflowProcesses.WORKFLOW_STAGE_COPY_IMAGES
    }

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_wps1_requirements(self):
        raise NotImplementedError()

    def test_workflow_docker_applications(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_STAGE_COPY_IMAGES,
                             [WorkflowProcesses.APP_DOCKER_STAGE_IMAGES, WorkflowProcesses.APP_DOCKER_COPY_IMAGES],
                             log_full_trace=True)
