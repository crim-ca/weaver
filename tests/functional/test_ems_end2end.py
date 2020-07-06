import json
import logging
import os
import time
from copy import deepcopy
from typing import TYPE_CHECKING
from unittest import TestCase
from urllib.parse import urlparse

import mock
import pytest
import six
from pyramid import testing
from pyramid.httpexceptions import HTTPCreated, HTTPNotFound, HTTPOk, HTTPUnauthorized
from pyramid.settings import asbool
# use 'Web' prefix to avoid pytest to pick up these classes and throw warnings
from webtest import TestApp as WebTestApp

from tests.utils import get_setting, get_settings_from_config_ini, get_settings_from_testapp
from weaver import WEAVER_ROOT_DIR
from weaver.config import WEAVER_CONFIGURATION_EMS
from weaver.formats import CONTENT_TYPE_APP_FORM, CONTENT_TYPE_APP_JSON
from weaver.processes.sources import fetch_data_sources
from weaver.status import (
    JOB_STATUS_CATEGORIES,
    JOB_STATUS_VALUES,
    STATUS_ACCEPTED,
    STATUS_CATEGORY_FINISHED,
    STATUS_CATEGORY_RUNNING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED
)
from weaver.utils import get_weaver_url, make_dirs, now, request_extra
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from weaver.typedefs import AnyResponseType, CookiesType, HeadersType, JSON, SettingsType
    from typing import Dict, Optional, Any, Tuple, Iterable, Callable, Union


class ProcessInfo(object):
    def __init__(self, process_id, test_id=None, deploy_payload=None, execute_payload=None):
        # type: (str, Optional[str], Optional[JSON], Optional[JSON]) -> None
        self.id = process_id
        self.test_id = test_id
        self.deploy_payload = deploy_payload
        self.execute_payload = execute_payload


# pylint: disable=C0103,invalid-name
@pytest.mark.slow
@pytest.mark.functional
@pytest.mark.workflow
@pytest.mark.skipif(condition=not len(str(os.getenv("WEAVER_TEST_SERVER_HOSTNAME", ""))),
                    reason="Test server not defined!")
class End2EndEMSTestCase(TestCase):
    """
    Runs an end-2-end test procedure on weaver configured as EMS located on specified `WEAVER_TEST_SERVER_HOSTNAME`.
    """
    __settings__ = None
    test_processes_info = dict()    # type: Dict[str, ProcessInfo]
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
    def get_collection_swapping():
        return [
            # Swap because Spacebel cannot retrieve probav images and Geomatys ADES is not ready
            # Geomatys ADES should be ready now!
            # ("EOP:VITO:PROBAV_S1-TOA_1KM_V001", "EOP:IPT:Sentinel2"),
        ]

    @classmethod
    def setUpClass(cls):
        # disable SSL warnings from logs
        try:
            import urllib3  # noqa
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass

        # logging parameter overrides
        cls.logger_level = os.getenv("WEAVER_TEST_LOGGER_LEVEL", cls.logger_level) or cls.logger_level
        if isinstance(cls.logger_level, six.string_types):
            cls.logger_level = logging.getLevelName(cls.logger_level)
        cls.logger_enabled = asbool(os.getenv("WEAVER_TEST_LOGGER_ENABLED", cls.logger_enabled))
        cls.logger_result_dir = os.getenv("WEAVER_TEST_LOGGER_RESULT_DIR", os.path.join(WEAVER_ROOT_DIR))
        cls.logger_json_indent = os.getenv("WEAVER_TEST_LOGGER_JSON_INDENT", cls.logger_json_indent)
        cls.logger_field_indent = os.getenv("WEAVER_TEST_LOGGER_FIELD_INDENT", cls.logger_field_indent)
        cls.logger_separator_calls = os.getenv("WEAVER_TEST_LOGGER_SEPARATOR_CALLS", cls.logger_separator_calls)
        cls.logger_separator_steps = os.getenv("WEAVER_TEST_LOGGER_SEPARATOR_STEPS", cls.logger_separator_steps)
        cls.logger_separator_tests = os.getenv("WEAVER_TEST_LOGGER_SEPARATOR_TESTS", cls.logger_separator_tests)
        cls.logger_separator_cases = os.getenv("WEAVER_TEST_LOGGER_SEPARATOR_CASES", cls.logger_separator_cases)
        cls.setup_logger()
        cls.log("{}Start of '{}': {}\n{}"
                .format(cls.logger_separator_cases, cls.current_case_name(), now(), cls.logger_separator_cases))

        # test execution configs
        cls.WEAVER_TEST_REQUEST_TIMEOUT = int(os.getenv("WEAVER_TEST_REQUEST_TIMEOUT", 10))
        cls.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT = int(os.getenv("WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT", 30))
        cls.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT = int(os.getenv("WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT", 6000))
        cls.WEAVER_TEST_JOB_GET_STATUS_INTERVAL = int(os.getenv("WEAVER_TEST_JOB_GET_STATUS_INTERVAL", 5))

        # security configs if enabled
        cls.WEAVER_TEST_PROTECTED_ENABLED = asbool(os.getenv("WEAVER_TEST_PROTECTED_ENABLED", False))
        cls.WEAVER_TEST_WSO2_CLIENT_HOSTNAME = os.getenv("WEAVER_TEST_WSO2_CLIENT_HOSTNAME", "")
        cls.WEAVER_TEST_WSO2_CLIENT_ID = os.getenv("WEAVER_TEST_WSO2_CLIENT_ID", "")
        cls.WEAVER_TEST_WSO2_CLIENT_SECRET = os.getenv("WEAVER_TEST_WSO2_CLIENT_SECRET", "")
        cls.WEAVER_TEST_WSO2_URL = os.getenv("WEAVER_TEST_WSO2_URL", "")
        cls.WEAVER_TEST_MAGPIE_URL = os.getenv("WEAVER_TEST_MAGPIE_URL", "")
        cls.WEAVER_TEST_ADMIN_CREDENTIALS = {"username": get_setting("ADMIN_USERNAME", cls.app),
                                             "password": get_setting("ADMIN_PASSWORD", cls.app)}
        cls.WEAVER_TEST_ALICE_CREDENTIALS = {"username": get_setting("ALICE_USERNAME", cls.app),
                                             "password": get_setting("ALICE_PASSWORD", cls.app)}
        cls.WEAVER_TEST_BOB_CREDENTIALS = {"username": get_setting("BOD_USERNAME", cls.app),
                                           "password": get_setting("BOB_PASSWORD", cls.app)}

        # server settings
        cls.WEAVER_TEST_SERVER_HOSTNAME = os.getenv("WEAVER_TEST_SERVER_HOSTNAME")
        cls.WEAVER_TEST_SERVER_BASE_PATH = os.getenv("WEAVER_TEST_SERVER_BASE_PATH", "/weaver")
        cls.WEAVER_TEST_SERVER_API_PATH = os.getenv("WEAVER_TEST_SERVER_API_PATH", "/")
        cls.WEAVER_TEST_CONFIG_INI_PATH = os.getenv("WEAVER_TEST_CONFIG_INI_PATH")    # none uses default path
        cls.app = WebTestApp(cls.WEAVER_TEST_SERVER_HOSTNAME)
        cls.WEAVER_URL = get_weaver_url(cls.settings())
        cls.WEAVER_RESTAPI_URL = get_wps_restapi_base_url(cls.settings())

        # validation
        cls.validate_test_server()
        cls.setup_test_processes()

    @classmethod
    def tearDownClass(cls):
        cls.clear_test_processes()
        testing.tearDown()
        cls.log("{}End of '{}': {}\n{}"
                .format(cls.logger_separator_cases, cls.current_case_name(), now(), cls.logger_separator_cases))

    def setUp(self):
        # reset in case it was modified during another test
        self.__class__.log_full_trace = True

        self.log("{}Start of '{}': {}\n{}"
                 .format(self.logger_separator_tests, self.current_test_name(), now(), self.logger_separator_tests))

        # cleanup old processes as required
        headers, cookies = self.user_headers_cookies(self.WEAVER_TEST_ADMIN_CREDENTIALS, force_magpie=True)
        self.clear_test_processes(headers, cookies)

    def tearDown(self):
        self.log("{}End of '{}': {}\n{}"
                 .format(self.logger_separator_tests, self.current_test_name(), now(), self.logger_separator_tests))

    @classmethod
    def current_case_name(cls):
        return cls.__name__

    def current_test_name(self):
        return self.id().split(".")[-1]

    @classmethod
    def settings(cls):
        # type: (...) -> SettingsType
        """Provide basic settings that must be defined to use various weaver utility functions."""
        if not cls.__settings__:
            weaver_url = os.getenv("WEAVER_URL", "{}{}".format(cls.WEAVER_TEST_SERVER_HOSTNAME,
                                                               cls.WEAVER_TEST_SERVER_BASE_PATH))
            cls.__settings__ = get_settings_from_testapp(cls.app)
            cls.__settings__.update(get_settings_from_config_ini(cls.WEAVER_TEST_CONFIG_INI_PATH))
            cls.__settings__.update({
                "weaver.url": weaver_url,
                "weaver.configuration": WEAVER_CONFIGURATION_EMS,
                "weaver.wps_restapi_path": cls.WEAVER_TEST_SERVER_API_PATH,
                "weaver.request_options": {},
            })
        return cls.__settings__

    @classmethod
    def get_http_auth_code(cls, unprotected_code=HTTPOk.code):
        # type: (int) -> int
        return HTTPUnauthorized.code if cls.WEAVER_TEST_PROTECTED_ENABLED else unprotected_code

    @classmethod
    def get_test_process(cls, process_id):
        # type: (str) -> ProcessInfo
        return cls.test_processes_info.get(process_id)

    @classmethod
    def setup_test_processes(cls):
        # type: (...) -> None
        cls.PROCESS_STACKER_ID = "Stacker"
        cls.PROCESS_SFS_ID = "SFS"
        cls.PROCESS_FLOOD_DETECTION_ID = "FloodDetection"
        cls.PROCESS_ICE_DAYS_ID = "Finch_IceDays"
        cls.PROCESS_SUBSET_BBOX_ID = "ColibriFlyingpigeon_SubsetBbox"
        cls.PROCESS_SUBSET_ESGF = "SubsetESGF"
        cls.PROCESS_SUBSET_NASAESGF = "SubsetNASAESGF"
        cls.PROCESS_WORKFLOW_ID = "Workflow"
        cls.PROCESS_WORKFLOW_SC_ID = "WorkflowSimpleChain"
        cls.PROCESS_WORKFLOW_S2P_ID = "WorkflowS2ProbaV"
        cls.PROCESS_WORKFLOW_CUSTOM_ID = "CustomWorkflow"
        cls.PROCESS_WORKFLOW_FLOOD_DETECTION_ID = "WorkflowFloodDetection"
        cls.PROCESS_WORKFLOW_SUBSET_ICE_DAYS = "WorkflowSubsetIceDays"
        cls.PROCESS_WORKFLOW_SUBSET_PICKER = "WorkflowSubsetPicker"
        cls.PROCESS_WORKFLOW_SUBSETLLNL_SUBSETCRIM = "WorkflowSubsetLLNL_SubsetCRIM"
        cls.PROCESS_WORKFLOW_SUBSETNASAESGF_SUBSETCRIM = "WorkflowSubsetNASAESGF_SubsetCRIM"
        cls.PROCESS_WORKFLOW_FILE_TO_SUBSETCRIM = "WorkflowFile_To_SubsetCRIM"
        application_set = {cls.PROCESS_STACKER_ID,
                           cls.PROCESS_SFS_ID,
                           cls.PROCESS_FLOOD_DETECTION_ID,
                           cls.PROCESS_ICE_DAYS_ID,
                           cls.PROCESS_SUBSET_BBOX_ID,
                           cls.PROCESS_SUBSET_ESGF,
                           cls.PROCESS_SUBSET_NASAESGF}
        workflow_set = {cls.PROCESS_WORKFLOW_ID,
                        cls.PROCESS_WORKFLOW_SC_ID,
                        cls.PROCESS_WORKFLOW_S2P_ID,
                        cls.PROCESS_WORKFLOW_CUSTOM_ID,
                        cls.PROCESS_WORKFLOW_FLOOD_DETECTION_ID,
                        cls.PROCESS_WORKFLOW_SUBSET_ICE_DAYS,
                        cls.PROCESS_WORKFLOW_SUBSET_PICKER,
                        cls.PROCESS_WORKFLOW_SUBSETLLNL_SUBSETCRIM,
                        cls.PROCESS_WORKFLOW_SUBSETNASAESGF_SUBSETCRIM,
                        cls.PROCESS_WORKFLOW_FILE_TO_SUBSETCRIM}
        test_set = application_set | workflow_set
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
        for workflow_id in workflow_set:
            workflow_deploy = cls.test_processes_info[workflow_id].deploy_payload
            for exec_unit in range(len(workflow_deploy["executionUnit"])):
                try:
                    workflow_cwl_ref = workflow_deploy["executionUnit"][exec_unit].pop("href")
                    workflow_cwl_raw = cls.retrieve_payload(workflow_cwl_ref)
                except KeyError:
                    workflow_cwl_raw = workflow_deploy["executionUnit"][exec_unit].pop("unit")
                for step in workflow_cwl_raw.get("steps"):
                    step_id = workflow_cwl_raw["steps"][step]["run"].strip(".cwl")
                    for app_id in application_set:
                        if app_id == step_id:
                            test_id = cls.test_processes_info[app_id].test_id
                            real_id = workflow_cwl_raw["steps"][step]["run"]
                            workflow_cwl_raw["steps"][step]["run"] = real_id.replace(app_id, test_id)
                workflow_deploy["executionUnit"][exec_unit]["unit"] = workflow_cwl_raw

    @classmethod
    def retrieve_process_info(cls, process_id):
        # type: (str) -> ProcessInfo
        base = os.getenv("TEST_GITHUB_SOURCE_URL",
                         "https://raw.githubusercontent.com/crim-ca/testbed14/master/application-packages")
        deploy_path = "{base}/{proc}/DeployProcess_{proc}.json".format(base=base, proc=process_id)
        execute_path = "{base}/{proc}/Execute_{proc}.json".format(base=base, proc=process_id)
        deploy_payload = cls.retrieve_payload(deploy_path)
        new_process_id = cls.get_test_process_id(deploy_payload["processDescription"]["process"]["id"])
        deploy_payload["processDescription"]["process"]["id"] = new_process_id
        execute_payload = cls.retrieve_payload(execute_path)

        # Apply collection swapping
        for swap in cls.get_collection_swapping():
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
                    json_payload = json.load(f)
                    return json_payload
            if urlparse(url).scheme != "":
                resp = cls.request("GET", url, force_requests=True, ignore_errors=True)
                if resp.status_code == HTTPOk.code:
                    return resp.json()
        except (IOError, ValueError):
            pass
        cls.log("{}Cannot find payload from either references:\n[{}]\n[{}]\n"
                .format(cls.logger_separator_calls, url, local_path), exception=True)

    @classmethod
    def get_test_process_id(cls, real_process_id):
        # type: (str) -> str
        return "{}_{}".format(cls.__name__, real_process_id)

    @classmethod
    def clear_test_processes(cls, headers=None, cookies=None):
        for process_info in cls.test_processes_info.values():
            path = "{}/processes/{}".format(cls.WEAVER_URL, process_info.test_id)

            # unauthorized when using Weaver directly means visibility is not public, but process definitively exists
            # update it to allow following delete
            if not cls.WEAVER_TEST_PROTECTED_ENABLED:
                resp = cls.request("GET", path, headers=headers, cookies=cookies, ignore_errors=True, log_enabled=False)
                if resp.status_code == HTTPUnauthorized.code:
                    visibility_path = "{}/visibility".format(path)
                    visibility_body = {"value": VISIBILITY_PUBLIC}
                    resp = cls.request("PUT", visibility_path, json=visibility_body, headers=headers, cookies=cookies,
                                       ignore_errors=True, log_enabled=False)
                    cls.assert_response(resp, HTTPOk.code, message="Failed cleanup of test processes!")

            resp = cls.request("DELETE", path, headers=headers, cookies=cookies, ignore_errors=True, log_enabled=False)

            # unauthorized can mean the process doesn't exist if user from headers doesn't have permissions on it
            # to even know if it exists (only if protected server it employed)
            codes = [HTTPOk.code, HTTPNotFound.code]
            if cls.WEAVER_TEST_PROTECTED_ENABLED:
                codes.append(HTTPUnauthorized.code)

            cls.assert_response(resp, codes, message="Failed cleanup of test processes!")

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
        """Logs an indented string representation of a JSON payload according to settings."""
        sub_indent = cls.get_indent(indent_level if cls.logger_json_indent else 0)
        log_payload = "\n" if cls.logger_json_indent else "" + json.dumps(payload, indent=cls.logger_json_indent)
        log_payload.replace("\n", "\n{}".format(sub_indent))
        if log_payload.endswith("\n"):
            return log_payload[:-1]  # remove extra line, let logger message generation add it explicitly
        return log_payload

    @classmethod
    def log_dict_format(cls, dictionary, indent_level):
        """Logs dictionary (key, value) pairs in a YAML-like format."""
        if dictionary is None:
            return None

        tab = "\n" + cls.get_indent(indent_level)
        return tab + "{tab}".format(tab=tab).join(["{}: {}".format(k, dictionary[k]) for k in sorted(dictionary)])

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
        is_localhost = url_parsed.hostname == "localhost"
        has_port = url_parsed.port is not None
        is_remote = hasattr(cls.app.app, "net_loc") and cls.app.app.net_loc != "localhost" and not is_localhost
        with_requests = is_localhost and has_port or is_remote or force_requests
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
            if json_body is not None:
                kw.update({"params": json.dumps(json_body, cls=json.JSONEncoder)})
            kw.update({"expect_errors": status and status >= 400 or expect_errors})
            cookies = kw.pop("cookies", dict())
            for cookie_name, cookie_value in cookies.items():
                cls.app.set_cookie(cookie_name, cookie_value)
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

    @classmethod
    def assert_response(cls, response, status=None, message=""):
        # type: (AnyResponseType, Optional[Union[int, Iterable[int]]], str) -> None
        """Tests a response for expected status and raises an error if not matching."""
        code = response.status_code
        reason = getattr(response, "reason", "")
        content = getattr(response, "content", "")
        req_url = ""
        req_body = ""
        req_method = ""
        if hasattr(response, "request"):
            req_url = getattr(response.request, "url", "")
            req_body = getattr(response.request, "body", "")
            req_method = getattr(response.request, "method", "")
        msg = "Unexpected HTTP Status: {} {} [{}, {}] from [{} {} {}]" \
              .format(response.status_code, reason, message, content, req_method, req_url, req_body)
        status = [status] if status is not None and not hasattr(status, "__iter__") else status
        cls.assert_test(lambda: (status is not None and code in status) or (status is None and code <= 400),
                        message=msg, title="Response Assertion Failed")

    @classmethod
    def assert_test(cls, assert_test, message=None, title="Test Assertion Failed"):
        # type: (Callable[[], bool], Optional[str], str) -> None
        """Tests a callable for assertion and logs the message if it fails, then re-raises to terminate execution."""
        try:
            assert assert_test(), message
        except AssertionError:
            cls.log("{}{}:\n{}\n".format(cls.logger_separator_calls, title, message), exception=True)

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
    def setup_logger(cls):
        if cls.logger_enabled:
            if not isinstance(cls.logger_level, int):
                cls.logger_level = logging.getLevelName(cls.logger_level)
            make_dirs(cls.logger_result_dir, exist_ok=True)
            log_path = os.path.abspath(os.path.join(cls.logger_result_dir, cls.__name__ + ".log"))
            log_fmt = logging.Formatter("%(message)s")      # only message to avoid 'log-name INFO' offsetting outputs
            log_file = logging.FileHandler(log_path)
            log_file.setFormatter(log_fmt)
            log_term = logging.StreamHandler()
            log_term.setFormatter(log_fmt)
            cls.logger_separator_calls = "-" * 80 + "\n"    # used between function calls (of same request)
            cls.logger_separator_steps = "=" * 80 + "\n"    # used between overall test steps (between requests)
            cls.logger_separator_tests = "*" * 80 + "\n"    # used between various test runs (each test_* method)
            cls.logger_separator_cases = "#" * 80 + "\n"    # used between various TestCase runs
            cls.logger = logging.getLogger(cls.__name__)
            cls.logger.setLevel(cls.logger_level)
            cls.logger.addHandler(log_file)
            cls.logger.addHandler(log_term)

    @classmethod
    def validate_test_server(cls):
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

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_wps1_requirements(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_SUBSET_ICE_DAYS,
                             [self.PROCESS_SUBSET_BBOX_ID, self.PROCESS_ICE_DAYS_ID],
                             log_full_trace=True)

    def test_workflow_subset_picker(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_SUBSET_PICKER,
                             [self.PROCESS_SUBSET_BBOX_ID],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_llnl_subset_esgf(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_SUBSETLLNL_SUBSETCRIM,
                             [self.PROCESS_SUBSET_ESGF, self.PROCESS_SUBSET_BBOX_ID],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_esgf_requirements(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_SUBSETNASAESGF_SUBSETCRIM,
                             [self.PROCESS_SUBSET_NASAESGF, self.PROCESS_SUBSET_BBOX_ID],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_file_to_string_array(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_FILE_TO_SUBSETCRIM,
                             [self.PROCESS_SUBSET_BBOX_ID],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Workflow not working anymore. IO to be repaired.")
    def test_workflow_wps3_requirements(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_ID,
                             [self.PROCESS_STACKER_ID, self.PROCESS_SFS_ID],
                             log_full_trace=True)

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_end2end_with_auth(self):
        """Full workflow execution procedure with authentication enabled."""
        # End to end test will log everything
        self.__class__.log_full_trace = True

        headers_a, cookies_a = self.user_headers_cookies(self.WEAVER_TEST_ALICE_CREDENTIALS)
        headers_b, cookies_b = self.user_headers_cookies(self.WEAVER_TEST_BOB_CREDENTIALS)

        # this test's set of processes
        end2_end_test_processes = [self.get_test_process(process_id) for process_id in
                                   (self.PROCESS_STACKER_ID, self.PROCESS_SFS_ID, self.PROCESS_WORKFLOW_ID)]

        # list processes (none of tests)
        path = "{}/processes".format(self.WEAVER_URL)
        resp = self.request("GET", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
        proc = resp.json.get("processes")
        test_processes = list(filter(lambda p: p["id"] in [tp.test_id for tp in end2_end_test_processes], proc))
        self.assert_test(lambda: len(test_processes) == 0, message="Test processes shouldn't exist!")

        self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code,
                     json=self.test_processes_info[self.PROCESS_STACKER_ID].deploy_payload,
                     message="Expect deployed application process.")
        self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPNotFound.code,
                     json=self.test_processes_info[self.PROCESS_WORKFLOW_ID].deploy_payload,
                     message="Expect deploy failure of workflow process with missing step.")
        self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code,
                     json=self.test_processes_info[self.PROCESS_SFS_ID].deploy_payload,
                     message="Expect deployed application process.")
        self.request("POST", path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code,
                     json=self.test_processes_info[self.PROCESS_WORKFLOW_ID].deploy_payload,
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
            process_path = "{}/processes/{}".format(self.WEAVER_URL, process_info.test_id)
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
            self.assert_test(lambda: resp.json.get("status") in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_RUNNING],
                             message="Response process execution job status should be one of running category values.")
            job_location = resp.json.get("location")
            job_id = resp.json.get("jobID")
            self.assert_test(lambda: job_id and job_location and job_location.endswith(job_id),
                             message="Response process execution job ID must match expected value to validate results.")
            self.validate_test_job_execution(job_location, headers_b, cookies_b)

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_simple_chain(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_SC_ID,
                             [self.PROCESS_STACKER_ID, self.PROCESS_SFS_ID])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_S2_and_ProbaV(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_S2P_ID,
                             [self.PROCESS_STACKER_ID, self.PROCESS_SFS_ID])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_custom(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_CUSTOM_ID,
                             [self.PROCESS_STACKER_ID, self.PROCESS_SFS_ID])

    @pytest.mark.xfail(reason="Interoperability of remote servers not guaranteed.")
    @pytest.mark.testbed14
    def test_workflow_flood_detection(self):
        self.workflow_runner(self.PROCESS_WORKFLOW_FLOOD_DETECTION_ID,
                             [self.PROCESS_STACKER_ID, self.PROCESS_SFS_ID])

    def workflow_runner(self, test_workflow_id, test_application_ids, log_full_trace=False):
        # type: (str, Iterable[str], bool) -> None
        """Simplify test for demonstration purpose"""

        # test will log basic information
        self.__class__.log_full_trace = log_full_trace

        # deploy processes and make them visible for workflows
        path_deploy = "{}/processes".format(self.WEAVER_URL)
        for process_id in test_application_ids:
            path_visible = "{}/{}/visibility".format(path_deploy, self.test_processes_info[process_id].test_id)
            data_visible = {"value": VISIBILITY_PUBLIC}
            self.request("POST", path_deploy, status=HTTPOk.code, headers=self.headers,
                         json=self.test_processes_info[process_id].deploy_payload,
                         message="Expect deployed application process.")
            self.request("PUT", path_visible, status=HTTPOk.code, headers=self.headers, json=data_visible,
                         message="Expect visible application process.")

        with mock.patch("weaver.processes.sources.get_data_source_from_url",
                        side_effect=End2EndEMSTestCase.mock_get_data_source_from_url):
            workflow_info = self.test_processes_info[test_workflow_id]

            self.request("POST", path_deploy, status=HTTPOk.code, headers=self.headers,
                         json=workflow_info.deploy_payload,
                         message="Expect deployed workflow process.")

            # make process visible
            process_path = "{}/{}".format(path_deploy, workflow_info.test_id)
            visible_path = "{}/visibility".format(process_path)
            visible = {"value": VISIBILITY_PUBLIC}
            resp = self.request("PUT", visible_path, json=visible, status=HTTPOk.code, headers=self.headers)
            self.assert_test(lambda: resp.json.get("value") == VISIBILITY_PUBLIC,
                             message="Process should be public.")

            # execute workflow
            execute_body = workflow_info.execute_payload
            execute_path = "{}/jobs".format(process_path)
            resp = self.request("POST", execute_path, status=HTTPCreated.code,
                                headers=self.headers, json=execute_body)
            self.assert_test(lambda: resp.json.get("status") in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_RUNNING],
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
            if status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_RUNNING]:
                if status == STATUS_ACCEPTED:
                    timeout_accept -= self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL
                else:
                    timeout_running -= self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL
                time.sleep(self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL)
                continue
            if status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_FINISHED]:
                self.assert_test(lambda: status == STATUS_SUCCEEDED,
                                 message="Job execution '{}' failed, but expected to succeed.".format(job_location_url))
                break
            self.assert_test(lambda: False, message="Unknown job execution status: '{}'.".format(status))
        self.request("GET", "{}/result".format(job_location_url),
                     headers=user_headers, cookies=user_cookies, status=HTTPOk.code)
