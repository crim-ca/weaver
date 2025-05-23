"""
Test processes consisting of a Workflow of sub-processes defining Application Package.
"""
import contextlib
import enum
import json
import logging
import os
import re
import tempfile
import time
from typing import TYPE_CHECKING, cast, overload
from unittest import TestCase
from urllib.parse import urlparse

import mock
import pytest
from pyramid import testing
from pyramid.httpexceptions import HTTPConflict, HTTPCreated, HTTPNotFound, HTTPOk
from pyramid.settings import asbool

# use 'Web' prefix to avoid pytest to pick up these classes and throw warnings
from webtest import TestApp as WebTestApp

from tests.functional.utils import ResourcesUtil
from tests.utils import (
    FileServer,
    get_settings_from_config_ini,
    get_settings_from_testapp,
    get_test_weaver_app,
    mocked_dismiss_process,
    mocked_execute_celery,
    mocked_file_server,
    mocked_sub_requests,
    mocked_wps_output,
    setup_config_with_mongodb
)
from weaver import WEAVER_ROOT_DIR
from weaver.config import WeaverConfiguration
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteReturnPreference, ExecuteTransmissionMode
from weaver.formats import ContentType
from weaver.processes.constants import (
    CWL_REQUIREMENT_MULTIPLE_INPUT,
    CWL_REQUIREMENT_STEP_INPUT_EXPRESSION,
    CWL_REQUIREMENT_SUBWORKFLOW,
    JobInputsOutputsSchema
)
from weaver.processes.types import ProcessType
from weaver.processes.utils import get_process_information
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory
from weaver.utils import fetch_file, generate_diff, get_any_id, get_weaver_url, make_dirs, now, repr_json, request_extra
from weaver.visibility import Visibility
from weaver.wps.utils import map_wps_output_location
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Iterable, Optional, Set, Tuple, Union
    from typing_extensions import Literal, TypedDict

    from responses import RequestsMock

    from weaver.typedefs import (
        AnyLogLevel,
        AnyRequestMethod,
        AnyResponseType,
        AnyUUID,
        CookiesType,
        CWL,
        CWL_RequirementsList,
        ExecutionInputsMap,
        ExecutionResults,
        HeadersType,
        JSON,
        ProcessDeployment,
        ProcessExecution,
        SettingsType
    )

    DetailedExecutionResultObject = TypedDict(
        "DetailedExecutionResultObject",
        {
            "job": AnyUUID,
            "process": str,
            "inputs": ExecutionInputsMap,
            "outputs": ExecutionResults,
            "logs": str,
        },
        total=True,
    )
    DetailedExecutionResults = Dict[
        AnyUUID,
        DetailedExecutionResultObject
    ]


# pylint: disable=E1135,E1136  # false positives about return value of 'workflow_runner' depending on 'detailed_results'


class WorkflowProcesses(enum.Enum):
    """
    Known process ID definitions for tests.

    .. note::
        Make sure to name processes accordingly if one depends on another (e.g.: `WPS-1` pointing at `WPS-REST`).
        They will be loaded by :class:`WorkflowTestRunnerBase` derived classes in alphabetical order.
        All atomic :term:`Application Package` will be loaded before :term:`Workflow` definitions.
    """

    # https://github.com/crim-ca/testbed14/tree/master/application-packages
    APP_STACKER = "Stacker"
    APP_SFS = "SFS"
    APP_FLOOD_DETECTION = "FloodDetection"
    WORKFLOW_CUSTOM = "CustomWorkflow"
    WORKFLOW_FLOOD_DETECTION = "WorkflowFloodDetection"
    WORKFLOW_STACKER_SFS = "Workflow"
    WORKFLOW_SC = "WorkflowSimpleChain"
    WORKFLOW_S2P = "WorkflowS2ProbaV"

    # local in 'tests/functional/application-packages'
    APP_ECHO = "Echo"
    APP_ECHO_OPTIONAL = "EchoOptional"
    APP_ECHO_SECRETS = "EchoSecrets"
    APP_ECHO_RESULTS_TESTER = "EchoResultsTester"
    APP_ICE_DAYS = "Finch_IceDays"
    APP_READ_FILE = "ReadFile"
    APP_SUBSET_BBOX = "ColibriFlyingpigeon_SubsetBbox"
    APP_SUBSET_ESGF = "SubsetESGF"
    APP_SUBSET_NASA_ESGF = "SubsetNASAESGF"
    APP_DOCKER_STAGE_IMAGES = "DockerStageImages"
    APP_DOCKER_COPY_IMAGES = "DockerCopyImages"
    APP_DOCKER_COPY_NESTED_OUTDIR = "DockerCopyNestedOutDir"
    APP_DOCKER_NETCDF_2_TEXT = "DockerNetCDF2Text"
    APP_DIRECTORY_LISTING_PROCESS = "DirectoryListingProcess"
    APP_DIRECTORY_MERGING_PROCESS = "DirectoryMergingProcess"
    APP_PASSTHROUGH_EXPRESSIONS = "PassthroughExpressions"
    APP_WPS1_DOCKER_NETCDF_2_TEXT = "WPS1DockerNetCDF2Text"
    APP_WPS1_JSON_ARRAY_2_NETCDF = "WPS1JsonArray2NetCDF"
    WORKFLOW_CHAIN_COPY = "WorkflowChainCopy"
    WORKFLOW_CHAIN_STRINGS = "WorkflowChainStrings"
    WORKFLOW_DIRECTORY_LISTING = "WorkflowDirectoryListing"
    WORKFLOW_ECHO = "WorkflowEcho"
    WORKFLOW_ECHO_OPTIONAL = "WorkflowEchoOptional"
    WORKFLOW_ECHO_SECRETS = "WorkflowEchoSecrets"
    WORKFLOW_PASSTHROUGH_EXPRESSIONS = "WorkflowPassthroughExpressions"
    WORKFLOW_STEP_MERGE = "WorkflowStepMerge"
    WORKFLOW_SUBSET_ICE_DAYS = "WorkflowSubsetIceDays"
    WORKFLOW_SUBSET_PICKER = "WorkflowSubsetPicker"
    WORKFLOW_SUBSET_LLNL_SUBSET_CRIM = "WorkflowSubsetLLNL_SubsetCRIM"
    WORKFLOW_SUBSET_NASA_ESGF_SUBSET_CRIM = "WorkflowSubsetNASAESGF_SubsetCRIM"
    WORKFLOW_FILE_TO_SUBSET_CRIM = "WorkflowFileToSubsetCRIM"
    WORKFLOW_REST_SCATTER_COPY_NETCDF = "WorkflowRESTScatterCopyNetCDF"
    WORKFLOW_REST_SELECT_COPY_NETCDF = "WorkflowRESTSelectCopyNetCDF"
    WORKFLOW_STAGE_COPY_IMAGES = "WorkflowStageCopyImages"
    WORKFLOW_WPS1_SCATTER_COPY_NETCDF = "WorkflowWPS1ScatterCopyNetCDF"
    WORKFLOW_WPS1_SELECT_COPY_NETCDF = "WorkflowWPS1SelectCopyNetCDF"


class ProcessInfo(object):
    """
    Container to preserve details loaded from 'application-packages' definitions.
    """

    def __init__(self,
                 process_id,                # type: Union[str, WorkflowProcesses]
                 test_id=None,              # type: Optional[str]
                 deploy_payload=None,       # type: Optional[ProcessDeployment]
                 execute_payload=None,      # type: Optional[ProcessExecution]
                 application_package=None,  # type: Optional[CWL]
                 ):                         # type: (...) -> None
        self.pid = WorkflowProcesses(process_id)        # type: WorkflowProcesses
        self.id = self.pid.value                        # type: str
        self.path = f"/processes/{self.id}"             # type: str
        self.test_id = test_id                          # type: Optional[str]
        self.deploy_payload = deploy_payload            # type: Optional[ProcessDeployment]
        self.execute_payload = execute_payload          # type: Optional[ProcessExecution]
        self.application_package = application_package  # type: Optional[CWL]


@pytest.mark.functional
@pytest.mark.workflow
class WorkflowTestRunnerBase(ResourcesUtil, TestCase):
    """
    Runs an end-2-end test procedure on weaver configured as EMS located on specified ``WEAVER_TEST_SERVER_HOSTNAME``.
    """
    __settings__ = None
    test_processes_info = {}        # type: Dict[WorkflowProcesses, ProcessInfo]
    headers = {
        "Accept": ContentType.APP_JSON,
        "Content-Type": ContentType.APP_JSON,
    }                               # type: HeadersType
    cookies = {}                    # type: CookiesType
    app = None                      # type: Optional[WebTestApp]
    logger_result_dir = None        # type: Optional[str]
    logger_character_calls = "-"    # type: str
    logger_character_steps = "="    # type: str
    logger_character_tests = "*"    # type: str
    logger_character_cases = "#"    # type: str
    logger_separator_calls = ""     # type: str
    """
    Used between function calls (same request or operation).
    """
    logger_separator_steps = ""     # type: str
    """
    Used between overall test steps (between requests).
    """
    logger_separator_tests = ""     # type: str
    """
    Used between various test runs (each test_* method).
    """
    logger_separator_cases = ""     # type: str
    """
    Used between various TestCase runs.
    """
    logger_level = logging.INFO     # type: AnyLogLevel
    logger_enabled = True           # type: bool
    logger = None                   # type: Optional[logging.Logger]
    # setting indent to `None` disables pretty-printing of JSON payload
    logger_json_indent = None       # type: Optional[int]
    logger_field_indent = 2         # type: int
    log_full_trace = True           # type: bool

    file_server = None              # type: FileServer
    """
    File server made available to tests for emulating a remote HTTP location.
    """

    WEAVER_URL = None               # type: Optional[str]
    WEAVER_RESTAPI_URL = None       # type: Optional[str]

    # application and workflow process identifiers to prepare using definitions in 'application-packages' directory
    # must be overridden by derived test classes
    WEAVER_TEST_APPLICATION_SET = set()     # type: Set[WorkflowProcesses]
    WEAVER_TEST_WORKFLOW_SET = set()        # type: Set[WorkflowProcesses]

    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is not WorkflowTestRunnerBase)
        super(WorkflowTestRunnerBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        # disable SSL warnings from logs
        try:
            import urllib3.exceptions  # noqa
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
        cls.logger_character_calls = cls.get_option("WEAVER_TEST_LOGGER_CHARACTER_CALLS", cls.logger_character_calls)
        cls.logger_character_steps = cls.get_option("WEAVER_TEST_LOGGER_CHARACTER_STEPS", cls.logger_character_steps)
        cls.logger_character_tests = cls.get_option("WEAVER_TEST_LOGGER_CHARACTER_TESTS", cls.logger_character_tests)
        cls.logger_character_cases = cls.get_option("WEAVER_TEST_LOGGER_CHARACTER_CASES", cls.logger_character_cases)
        cls.setup_logger()  # on top of other logging setup, defines default "line separators" using above characters
        cls.logger_separator_calls = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_CALLS", cls.logger_separator_calls)
        cls.logger_separator_steps = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_STEPS", cls.logger_separator_steps)
        cls.logger_separator_tests = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_TESTS", cls.logger_separator_tests)
        cls.logger_separator_cases = cls.get_option("WEAVER_TEST_LOGGER_SEPARATOR_CASES", cls.logger_separator_cases)
        cls.log("%sStart of '%s': %s\n%s",
                cls.logger_separator_cases, cls.current_case_name(), now(), cls.logger_separator_cases)

        # test execution configs
        cls.WEAVER_TEST_REQUEST_TIMEOUT = int(cls.get_option("WEAVER_TEST_REQUEST_TIMEOUT", 10))
        cls.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT = int(cls.get_option("WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT", 30))
        cls.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT = int(cls.get_option("WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT", 6000))
        cls.WEAVER_TEST_JOB_GET_STATUS_INTERVAL = int(cls.get_option("WEAVER_TEST_JOB_GET_STATUS_INTERVAL", 5))

        # server settings
        cls.WEAVER_TEST_CONFIGURATION = conf = cls.get_option("WEAVER_TEST_CONFIGURATION", WeaverConfiguration.EMS)
        cls.WEAVER_TEST_SERVER_HOSTNAME = host = cls.get_option("WEAVER_TEST_SERVER_HOSTNAME", "")
        cls.WEAVER_TEST_SERVER_BASE_PATH = cls.get_option("WEAVER_TEST_SERVER_BASE_PATH", "/weaver")
        cls.WEAVER_TEST_SERVER_API_PATH = cls.get_option("WEAVER_TEST_SERVER_API_PATH", "/")
        cls.WEAVER_TEST_CONFIG_INI_PATH = cls.get_option("WEAVER_TEST_CONFIG_INI_PATH")    # none uses default path
        if host in [None, ""]:
            # running with a local-only Web Test application
            config = setup_config_with_mongodb(settings={
                "weaver.configuration": conf,
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
            if host.startswith("http"):
                url = host
            else:
                url = f"http://{host}"
            cls.app = WebTestApp(url)
            cls.WEAVER_URL = get_weaver_url(cls.settings.fget(cls))
        cls.WEAVER_RESTAPI_URL = get_wps_restapi_base_url(cls.settings.fget(cls))

        # validation
        cls.setup_test_processes_before()
        cls.setup_test_processes()
        cls.setup_test_processes_after()

        cls.file_server = FileServer()
        cls.file_server.start()

    @property
    def settings(self):
        # type: (...) -> SettingsType
        """
        Provide basic settings that must be defined to use various weaver utility functions.
        """
        if not self.__settings__:
            weaver_url = os.getenv("WEAVER_URL", self.WEAVER_TEST_SERVER_HOSTNAME + self.WEAVER_TEST_SERVER_BASE_PATH)
            if not weaver_url.startswith("http"):
                if not weaver_url.startswith("/") and weaver_url != "":
                    weaver_url = f"http://{weaver_url}"
            self.__settings__ = get_settings_from_testapp(self.app)
            self.__settings__.update(get_settings_from_config_ini(self.WEAVER_TEST_CONFIG_INI_PATH))
            self.__settings__.update({
                "weaver.url": weaver_url,
                "weaver.configuration": self.WEAVER_TEST_CONFIGURATION,
                "weaver.wps_restapi_path": self.WEAVER_TEST_SERVER_API_PATH,
                "weaver.request_options": {},
            })
        return self.__settings__

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.clean_test_processes()
        cls.file_server.teardown()
        testing.tearDown()
        cls.log("%sEnd of '%s': %s\n%s",
                cls.logger_separator_cases, cls.current_case_name(), now(), cls.logger_separator_cases)

    def setUp(self):
        # reset in case it was modified during another test
        self.__class__.log_full_trace = True

        self.log("%sStart of '%s': %s\n%s",
                 self.logger_separator_tests, self.current_test_name(), now(), self.logger_separator_tests)

        # cleanup old processes as required
        self.clean_test_processes_before()
        self.clean_test_processes()
        self.clean_test_processes_after()

    def tearDown(self):
        self.log("%sEnd of '%s': %s\n%s",
                 self.logger_separator_tests, self.current_test_name(), now(), self.logger_separator_tests)

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
        for process in sorted(test_set, key=lambda proc: proc.value):
            cls.test_processes_info.update({process: cls.retrieve_process_info(process)})

        # replace max occur of processes to minimize data size during tests
        for process_id in test_set:
            process_deploy = cls.test_processes_info[process_id].deploy_payload
            process_deploy_inputs = process_deploy["processDescription"].get("process", {}).get("inputs")
            if process_deploy_inputs:
                for i_input, proc_input in enumerate(process_deploy_inputs):
                    if proc_input.get("maxOccurs") == "unbounded":
                        process_deploy_inputs[i_input]["maxOccurs"] = str(2)

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
            cls.logger_separator_calls = cls.logger_character_calls * 80 + "\n"
            cls.logger_separator_steps = cls.logger_character_steps * 80 + "\n"
            cls.logger_separator_tests = cls.logger_character_tests * 80 + "\n"
            cls.logger_separator_cases = cls.logger_character_cases * 80 + "\n"
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
    def log(cls, message, *args, level=None, exception=False, traceback=False):
        # type: (str, *Any, Optional[AnyLogLevel], bool, bool) -> None
        if cls.logger_enabled:
            if exception:
                # also prints traceback of the exception
                cls.logger.exception(message, *args, stack_info=traceback)
            else:
                if level is None:
                    level = cls.logger_level
                cls.logger.log(level, message, *args, stack_info=traceback)
        if exception:
            if "%" in message and args:
                try:
                    message = message % args
                except TypeError:  # error on insufficient/over-specified format string arguments
                    message += f"\nArguments could not be formatted into message: {args}"
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
        log_payload.replace("\n", f"\n{sub_indent}")
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
        return tab + tab.join([f"{k}: {dictionary[k]}" for k in sorted(dictionary)])

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

            # if any job is still pending in the database, it can cause process delete to fail (forbidden, in use)
            path = f"/processes/{process_info.id}/jobs"
            resp = cls.request("GET", path,
                               headers=cls.headers, cookies=cls.cookies,
                               ignore_errors=True, log_enabled=False)
            cls.assert_response(resp, allowed_codes, message="Failed cleanup of test processes jobs!")
            with contextlib.ExitStack() as stack:
                if cls.is_webtest():
                    stack.enter_context(mocked_dismiss_process())
                for job in resp.json.get("jobs", []):
                    cls.request("DELETE", f"{path}/{job}",
                                headers=cls.headers, cookies=cls.cookies,
                                ignore_errors=True, log_enabled=False)

            # then clean the actual process
            path = f"/processes/{process_info.id}"
            resp = cls.request("DELETE", path,
                               headers=cls.headers, cookies=cls.cookies,
                               ignore_errors=True, log_enabled=False)
            cls.clean_test_processes_iter_after(process_info)
            cls.assert_response(resp, allowed_codes, message="Failed cleanup of test processes!")

    @staticmethod
    def mock_get_data_source_from_url(data_url):
        # type: (str) -> Optional[str]
        """
        Hook available to subclasses to mock any data-source resolution to remote :term:`ADES` based on data reference.

        By default, nothing is returned, meaning that no :term:`Data Source` will be resolved.
        In the case of :term:`HYBRID` configuration, this will indicate that :term:`Process` is to be executed locally.
        In the case of alternate configurations, failing to provide an overridden configuration will most probably fail
        the :term:`Workflow` execution since it will not be possible to map references.

        .. seealso::
            - :ref:`data-source`
            - :ref:`conf_data_sources`
        """

    @staticmethod
    def swap_data_collection():
        # type: () -> Iterable[str]
        """
        Hook available to subclasses to substitute any known collection to data references during resolution.

        This feature mostly applies to :term:`EOImage` or :term:`OpenSearch` data sources.

        .. seealso::
            - :ref:`opensearch_data_source`
        """
        return []

    @classmethod
    def current_case_name(cls):
        return cls.__name__

    def current_test_name(self):
        return self.id().split(".")[-1]

    @classmethod
    def get_test_process(cls, process_id):
        # type: (WorkflowProcesses) -> ProcessInfo
        return cls.test_processes_info.get(process_id)

    @classmethod
    def retrieve_process_info(cls, process_id):
        # type: (WorkflowProcesses) -> ProcessInfo
        """
        Retrieves the deployment, execution and package contents for a process referenced by ID.

        The lookup procedure attempts multiple formats for historical reasons:

            1. Look in the local ``tests.functional`` directory.
            2. Look in remote repository:
                https://github.com/crim-ca/testbed14
                i.e.:  directory ``TB14`` under
                https://github.com/crim-ca/application-packages/tree/master/OGC
            3. Look in remote repository directory:
                https://github.com/crim-ca/application-packages/tree/master/OGC/TB16
            4. An extra URL defined by ``TEST_GITHUB_SOURCE_URL`` if provided.

        .. note::
            URL endpoints must be provided with 'raw' contents.
            In the case of GitHub references for example, ``https://raw.githubusercontent.com`` prefix must be used.

        For each location, content retrieval is attempted with the following file structures:

            1. Contents defined as flat list with type of content and process ID in name:
                - ``DeployProcess_<PROCESS_ID>.[json|yaml|yml]``
                - ``Execute_<PROCESS_ID>.[json|yaml|yml]``
                - ``<PROCESS_ID>.[cwl|json|yaml|yml]`` (package)

            2. Contents defined within a sub-directory named ``<PROCESS_ID>`` with either the previous names or simply:
                - ``deploy.[json|yaml|yml]``
                - ``execute.[json|yaml|yml]``
                - ``package.[cwl|json|yaml|yml]``

        For each group of content definitions, "deploy" and "execute" contents are mandatory.
        The "package" file can be omitted if it is already explicitly embedded within the "deploy" contents.

        .. note::
            Only when references are local (tests), the package can be referred by relative ``tests/...`` path
            within the "deploy" content's ``executionUnit`` using ``test`` key instead of ``unit`` or ``href``.
            In such case, the "package" contents will be loaded and injected dynamically as ``unit`` in the "deploy"
            body at the relevant location. Alternatively to the ``test`` key, ``href`` can also be used, but will be
            loaded only if using the ``tests/..`` relative path. This is to ensure cross-support with other test
            definitions using this format outside of "workflow" use cases.

        :param process_id: identifier of the process to retrieve contents.
        :return: found content definitions.
        """
        pid = process_id.value  # type: str  # noqa
        deploy_payload = cls.retrieve_payload(pid, "deploy")
        deploy_id = get_any_id(get_process_information(deploy_payload))
        test_process_id = f"{cls.__name__}_{deploy_id}"
        execute_payload = cls.retrieve_payload(pid, "execute")

        # replace derived reference (local only, remote must use the full 'href' references)
        test_exec_unit = deploy_payload.get("executionUnit", [{}])[0]
        unit_app_pkg = None
        test_app_pkg = test_exec_unit.pop("test", None)
        if test_app_pkg:
            unit_app_pkg = cls.retrieve_payload(pid, "package")
        elif "href" in test_exec_unit and str(test_exec_unit["href"]).startswith("tests/"):
            unit_app_pkg = cls.retrieve_payload(pid, "package", local=True, location=test_exec_unit["href"])
        if unit_app_pkg:
            deploy_payload["executionUnit"][0] = {"unit": unit_app_pkg}

        # Apply collection swapping
        for swap in cls.swap_data_collection():
            for i in execute_payload["inputs"]:
                if "data" in i and i["data"] == swap[0]:
                    i["data"] = swap[1]

        return ProcessInfo(process_id, test_process_id, deploy_payload, execute_payload, unit_app_pkg)

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
            message = f"{message}, {content}" if content else message
        status = [status] if status is not None and not hasattr(status, "__iter__") else status
        if status is not None:
            expect_msg = f"Expected status in: {status}"
            expect_code = code in status
        else:
            expect_msg = "Expected status: <= 400"
            expect_code = code <= 400
        msg = (
            f"Unexpected HTTP Status: {response.status_code} {reason}[{message}]\n{expect_msg}\n"
            f"From: [{req_method} {req_url} {req_body}]"
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
            cls.log("%s%s:\n%s\n", cls.logger_separator_calls, title, message,
                    level=logging.ERROR, exception=True, traceback=True)

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
    def request(cls,                    # pylint: disable=W0221
                method,                 # type: AnyRequestMethod
                url,                    # type: str
                ignore_errors=False,    # type: bool
                force_requests=False,   # type: bool
                log_enabled=True,       # type: bool
                **kw                    # type: Any
                ):                      # type: (...) -> AnyResponseType
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
            url = f"{cls.WEAVER_URL}{url}"

        if not json_body and data_body and headers and ContentType.APP_JSON in headers.get("Content-Type"):
            json_body = data_body
            data_body = None

        if log_enabled:
            if json_body:
                payload = cls.log_json_format(json_body, 2)
            else:
                payload = data_body
            trace = (f"{cls.logger_separator_steps}Request Details:\n" +
                     cls.indent(f"Request: {method} {url}\n", 1) +
                     cls.indent(f"Payload: {payload}", 1))
            if cls.log_full_trace:
                module_name = "requests" if with_requests else "webtest.TestApp"
                headers = cls.log_dict_format(headers, 2)
                cookies = cls.log_dict_format(cookies, 2)
                trace += ("\n" +
                          cls.indent(f"Headers: {headers}\n", 1) +
                          cls.indent(f"Cookies: {cookies}\n", 1) +
                          cls.indent(f"Status:  {status} (expected)\n", 1) +
                          cls.indent(f"Message: {message} (expected)\n", 1) +
                          cls.indent(f"Module:  {module_name}\n", 1))
            cls.log(trace)

        if with_requests:
            kw.update({"verify": False, "timeout": cls.WEAVER_TEST_REQUEST_TIMEOUT})
            # retry request if the error was caused by some connection error
            settings = cls.settings.fget(cls)  # pylint: disable=E1111,assignment-from-no-return
            resp = request_extra(method, url, json=json_body, data=data_body, retries=3, settings=settings, **kw)

            # add some properties similar to `webtest.TestApp`
            resp_body = getattr(resp, "body", None)  # if error is pyramid HTTPException, body is byte only
            if ContentType.APP_JSON in resp.headers.get("Content-Type", []):
                if resp_body is None:
                    setattr(resp, "body", resp.json)
                setattr(resp, "json", resp.json())
                setattr(resp, "content_type", ContentType.APP_JSON)
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
            if isinstance(status, int):
                status = [status]
            kw.update({"expect_errors": (status and any(code >= 400 for code in status)) or expect_errors})
            cookies = kw.pop("cookies", {}) or {}
            for cookie_name, cookie_value in cookies.items():
                cls.app.set_cookie(cookie_name, cookie_value)

            if with_mock_req:
                # NOTE:
                #  Very important to mock requests only matching local test application.
                #  Otherwise, mocks like 'mocked_wps_output' cannot do their job since real requests won't be sent.
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
            if ContentType.APP_JSON in resp.headers.get("Content-Type", []):
                payload = cls.log_json_format(resp.json, 2)  # noqa
            else:
                payload = resp.body
            if cls.log_full_trace:
                headers = resp.headers
            else:
                header_filter = ["Location"]
                headers = {k: v for k, v in resp.headers.items() if k in header_filter}
            headers = cls.log_dict_format(headers, 2)
            cls.log(f"{cls.logger_separator_calls}Response Details:\n" +
                    cls.indent(f"Status:  {resp.status_code} (received)\n", 1) +
                    cls.indent(f"Content: {resp.content_type}\n", 1) +
                    cls.indent(f"Payload: {payload}\n", 1) +
                    cls.indent(f"Headers: {headers}\n", 1))
        return resp

    @overload
    def workflow_runner(
        self,
        test_workflow_id,               # type: WorkflowProcesses
        test_application_ids,           # type: Iterable[WorkflowProcesses]
        log_full_trace,                 # type: bool
        requests_mock_callback=None,    # type: Optional[Callable[[RequestsMock], None]]
        override_execute_body=None,     # type: Optional[ProcessExecution]
        override_execute_path=None,     # type: Optional[str]
    ):                                  # type: (...) -> ExecutionResults
        ...

    @overload
    def workflow_runner(
        self,
        test_workflow_id,               # type: WorkflowProcesses
        test_application_ids,           # type: Iterable[WorkflowProcesses]
        log_full_trace=False,           # type: bool
        requests_mock_callback=None,    # type: Optional[Callable[[RequestsMock], None]]
        override_execute_body=None,     # type: Optional[ProcessExecution]
        override_execute_path=None,     # type: Optional[str]
        detailed_results=True,          # type: Literal[True]
    ):                                  # type: (...) -> DetailedExecutionResults
        ...

    def workflow_runner(
        self,
        test_workflow_id,               # type: WorkflowProcesses
        test_application_ids,           # type: Iterable[WorkflowProcesses]
        log_full_trace=False,           # type: bool
        requests_mock_callback=None,    # type: Optional[Callable[[RequestsMock], None]]
        override_execute_body=None,     # type: Optional[ProcessExecution]
        override_execute_path=None,     # type: Optional[str]
        detailed_results=False,         # type: bool
    ):                                  # type: (...) -> Union[ExecutionResults, DetailedExecutionResults]
        """
        Main runner method that prepares and evaluates the full :term:`Workflow` execution and its step dependencies.

        .. note::
            When running on a local :class:`WebTestApp`, mocks :func:`mocked_wps_output`
            (with sub-call to :func:`mocked_file_server`) and :func:`mocked_sub_requests` are already being applied.
            If further request methods/endpoints need to be added for a given test case, they should be defined using
            a function provided with :paramref:`mock_request_callback` to extend the existing response mock.
            This is because it is not possible to apply multiple responses mocks one on top of another due to the
            patching methodology to catch all sent requests that matches any criteria.

        :param test_workflow_id:
            Identifier of the :term:`Workflow` to test.
            Must be a member amongst preloaded :attr:`WEAVER_TEST_WORKFLOW_SET` definitions.
        :param test_application_ids:
            Identifiers of all intermediate :term:`Process` steps to be deployed prior to the tested :term:`Workflow`
            expecting them to exist. Must be members amongst preloaded :attr:`WEAVER_TEST_APPLICATION_SET` definitions.
        :param log_full_trace:
            Flag to provide extensive trace logs of all request and response details for each operation.
        :param requests_mock_callback:
            Function to add further requests mock specifications as needed by the calling test case.
        :param override_execute_body:
            Alternate execution request content from the default one loaded from the referenced Workflow location.
        :param override_execute_path:
            Alternate execution request path from the default one employed by the workflow runner.
            Must be a supported endpoints (``/jobs``, ``/processes/{pID}/jobs``, ``/processes/{pID}/execution``).
        :param detailed_results:
            If enabled, each step involved in the :term:`Workflow` chain will provide their respective details
            including the :term:`Process` ID, the :term:`Job` UUID, intermediate outputs and logs.
            Otherwise (default), only the final results of :term:`Workflow` chain are returned.
        :returns: Response contents of the final :term:`Workflow` results for further validations if needed.
        """

        # test will log basic information
        self.__class__.log_full_trace = log_full_trace

        # deploy processes and make them visible for workflow
        has_duplicate_apps = len(set(test_application_ids)) != len(list(test_application_ids))
        for process_id in test_application_ids:
            self.prepare_process(process_id, exists_ok=has_duplicate_apps)

        # deploy workflow process itself and make visible
        workflow_info = self.prepare_process(test_workflow_id)
        status_or_results = self.execute_monitor_process(
            workflow_info,
            detailed_results=detailed_results,
            override_execute_body=override_execute_body,
            override_execute_path=override_execute_path,
            requests_mock_callback=requests_mock_callback,
        )
        return status_or_results

    def prepare_process(self, process_id, exists_ok=False):
        # type: (WorkflowProcesses, bool) -> ProcessInfo
        """
        Deploys the process referenced by ID using the available :term:`Application Package` and makes it visible.
        """
        proc_info = self.test_processes_info[process_id]
        body_deploy = proc_info.deploy_payload
        path_deploy = "/processes"
        path_visible = f"{proc_info.path}/visibility"
        data_visible = {"value": Visibility.PUBLIC}
        allowed_status = [HTTPCreated.code, HTTPConflict.code] if exists_ok else HTTPCreated.code
        self.request("POST", path_deploy, status=allowed_status, headers=self.headers, json=body_deploy,
                     message="Expect deployed process.")
        self.request("PUT", path_visible, status=HTTPOk.code, headers=self.headers, json=data_visible,
                     message="Expect visible process.")
        return proc_info

    def execute_monitor_process(
        self,
        process_info,                   # type: ProcessInfo
        requests_mock_callback=None,    # type: Optional[Callable[[RequestsMock], None]]
        override_execute_body=None,     # type: Optional[ProcessExecution]
        override_execute_path=None,     # type: Optional[str]
        detailed_results=True,          # type: Literal[True]
    ):                                  # type: (...) -> Union[JSON, DetailedExecutionResults]
        with contextlib.ExitStack() as stack_exec:
            for data_source_use in [
                "weaver.processes.sources.get_data_source_from_url",
                "weaver.processes.wps3_process.get_data_source_from_url"
            ]:
                stack_exec.enter_context(mock.patch(data_source_use, side_effect=self.mock_get_data_source_from_url))
            if self.is_webtest():
                # mock execution when running on local Web Test app since no Celery runner is available
                for mock_exec in mocked_execute_celery(web_test_app=self.app):
                    stack_exec.enter_context(mock_exec)
                # mock HTTP HEAD request to validate WPS output access (see 'setUpClass' details)
                mock_req = stack_exec.enter_context(mocked_wps_output(self.settings, mock_head=True, mock_get=False))
                if requests_mock_callback:
                    requests_mock_callback(mock_req)

            # execute workflow
            execute_body = override_execute_body or process_info.execute_payload
            execute_body.setdefault("mode", ExecuteMode.ASYNC)
            execute_path = override_execute_path or f"{process_info.path}/jobs"
            self.assert_test(lambda: execute_body is not None,
                             message="Cannot execute workflow without a request body!")
            resp = self.request("POST", execute_path, status=HTTPCreated.code,
                                headers=self.headers, json=execute_body)
            self.assert_test(lambda: resp.json.get("status") in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING],
                             message="Response process execution job status should be one of running values.")
            job_location = resp.location
            job_id = resp.json.get("jobID")
            self.assert_test(lambda: job_id and job_location and job_location.endswith(job_id),
                             message="Response process execution job ID must match to validate results.")
            resp, details = self.validate_test_job_execution(job_location, None, None)
        if detailed_results:
            self.assert_test(
                lambda: bool(details) and len(details) > 1,  # minimally 1 workflow and 1 step
                message="Could not obtain execution result details when requested by test.",
            )
            return details
        return resp.json

    def validate_test_job_execution(self, job_location_url, user_headers=None, user_cookies=None):
        # type: (str, Optional[HeadersType], Optional[CookiesType]) -> Tuple[AnyResponseType, DetailedExecutionResults]
        """
        Validates that the job is stated, running, and polls it until completed successfully.

        Then validates that results are accessible (no data integrity check).
        """
        timeout_accept = self.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT
        timeout_running = self.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT
        details = {}  # type: DetailedExecutionResults
        while True:
            self.assert_test(
                lambda: timeout_accept > 0,
                message=(
                    "Maximum timeout reached for job execution test. "
                    f"Expected job status change from '{Status.ACCEPTED}' to '{Status.RUNNING}' "
                    f"within {self.WEAVER_TEST_JOB_ACCEPTED_MAX_TIMEOUT}s since first '{Status.ACCEPTED}'."
                )
            )
            self.assert_test(
                lambda: timeout_running > 0,
                message=(
                    "Maximum timeout reached for job execution test. "
                    f"Expected job status change from '{Status.RUNNING}' to '{Status.SUCCESSFUL}' "
                    f"within {self.WEAVER_TEST_JOB_RUNNING_MAX_TIMEOUT}s since first '{Status.RUNNING}'."
                )
            )
            resp = self.request("GET", job_location_url,
                                headers=user_headers, cookies=user_cookies, status=HTTPOk.code)
            status = resp.json.get("status")
            self.assert_test(lambda: status in Status.values(),
                             message="Cannot identify a valid job status for result validation.")
            if status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
                if status == Status.ACCEPTED:
                    timeout_accept -= self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL
                else:
                    timeout_running -= self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL
                time.sleep(self.WEAVER_TEST_JOB_GET_STATUS_INTERVAL)
                continue
            if status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
                failed = status not in JOB_STATUS_CATEGORIES[StatusCategory.SUCCESS]
                logs, details = self.try_retrieve_logs(job_location_url, detailed_results=not failed)
                self.assert_test(
                    lambda: not failed,
                    message=f"Job execution '{job_location_url}' failed, but expected to succeed.\n{logs}",
                )
                break
            self.assert_test(lambda: False, message=f"Unknown job execution status: '{status}'.")
        path = f"{job_location_url}/results"
        resp_headers = {"Accept": ContentType.APP_JSON, "Prefer": f"return={ExecuteReturnPreference.MINIMAL}"}
        resp_headers.update(user_headers or {})
        resp = self.request("GET", path, headers=resp_headers, cookies=user_cookies, status=HTTPOk.code)
        return resp, details

    def try_retrieve_logs(self, workflow_job_url, detailed_results):
        # type: (str, bool) -> Tuple[str, DetailedExecutionResults]
        """
        Attempt to retrieve the main workflow job logs and any underlying step process logs.

        Because jobs are dispatched by the Workflow execution itself, there are no handles to the actual step jobs here.
        Try to parse the workflow logs to guess output logs URLs. If not possible, skip silently.
        """
        details = {}  # type: DetailedExecutionResults
        try:
            msg = ""
            path = f"{workflow_job_url}/logs"
            resp = self.request("GET", path, ignore_errors=True)
            if resp.status_code == 200 and isinstance(resp.json, list):
                logs = resp.json
                job_id = workflow_job_url.split("/")[-1]
                tab_n = "\n" + self.indent("", 1)
                workflow_logs = tab_n.join(logs)
                msg += f"Workflow logs [JobID: {job_id}]" + tab_n + workflow_logs
                if detailed_results:
                    details[job_id] = self.extract_job_details(workflow_job_url, workflow_logs)
                log_matches = set(re.findall(r".*(https?://.+/jobs/.+(?:/logs)?).*", workflow_logs))
                log_matches = {url.strip("[]") for url in log_matches}
                log_matches -= {workflow_job_url}
                log_matches = {url if url.rstrip("/").endswith("/logs") else f"{url}/logs" for url in log_matches}
                for log_url in log_matches:
                    job_id = log_url.split("/")[-2]
                    resp = self.request("GET", log_url, ignore_errors=True)
                    if resp.status_code == 200 and isinstance(resp.json, list):
                        step_logs = tab_n.join(resp.json)
                        if detailed_results:
                            step_job_url = log_url.split("/logs", 1)[0]
                            details[job_id] = self.extract_job_details(step_job_url, step_logs)
                        msg += f"\nStep process logs [JobID: {job_id}]" + tab_n + step_logs
        except Exception:  # noqa
            return "Could not retrieve job logs.", {}
        return msg, details

    def extract_job_details(self, job_url, job_logs):
        # type: (str, str) -> DetailedExecutionResultObject
        """
        Extracts more details about a *successful* :term:`Job` execution using known endpoints.
        """
        proc_url, job_id = job_url.split("/jobs/", 1)
        proc_id = proc_url.rsplit("/", 1)[-1]
        path = f"{job_url}/inputs"
        resp = self.request("GET", path, params={"schema": JobInputsOutputsSchema.OGC}, ignore_errors=True)
        job_inputs = cast("ExecutionInputsMap", resp.json["inputs"])
        path = f"{job_url}/outputs"
        resp = self.request("GET", path, params={"schema": JobInputsOutputsSchema.OGC}, ignore_errors=True)
        job_outputs = cast("ExecutionResults", resp.json["outputs"])
        detail = {
            "job": job_id,
            "process": proc_id,
            "logs": job_logs,
            "inputs": job_inputs,
            "outputs": job_outputs,
        }
        return detail


class WorkflowTestCase(WorkflowTestRunnerBase):
    WEAVER_TEST_CONFIGURATION = WeaverConfiguration.HYBRID
    WEAVER_TEST_SERVER_BASE_PATH = ""

    WEAVER_TEST_APPLICATION_SET = {
        WorkflowProcesses.APP_DOCKER_COPY_IMAGES,
        WorkflowProcesses.APP_DOCKER_COPY_NESTED_OUTDIR,
        WorkflowProcesses.APP_DOCKER_NETCDF_2_TEXT,
        WorkflowProcesses.APP_DIRECTORY_LISTING_PROCESS,
        WorkflowProcesses.APP_DIRECTORY_MERGING_PROCESS,
        WorkflowProcesses.APP_DOCKER_STAGE_IMAGES,
        WorkflowProcesses.APP_ECHO,
        WorkflowProcesses.APP_ECHO_OPTIONAL,
        WorkflowProcesses.APP_ECHO_RESULTS_TESTER,
        WorkflowProcesses.APP_ECHO_SECRETS,
        WorkflowProcesses.APP_PASSTHROUGH_EXPRESSIONS,
        WorkflowProcesses.APP_READ_FILE,
        WorkflowProcesses.APP_WPS1_DOCKER_NETCDF_2_TEXT,
        WorkflowProcesses.APP_WPS1_JSON_ARRAY_2_NETCDF,
    }
    WEAVER_TEST_WORKFLOW_SET = {
        WorkflowProcesses.WORKFLOW_CHAIN_COPY,
        WorkflowProcesses.WORKFLOW_CHAIN_STRINGS,
        WorkflowProcesses.WORKFLOW_DIRECTORY_LISTING,
        WorkflowProcesses.WORKFLOW_ECHO,
        WorkflowProcesses.WORKFLOW_ECHO_OPTIONAL,
        WorkflowProcesses.WORKFLOW_ECHO_SECRETS,
        WorkflowProcesses.WORKFLOW_PASSTHROUGH_EXPRESSIONS,
        WorkflowProcesses.WORKFLOW_STAGE_COPY_IMAGES,
        WorkflowProcesses.WORKFLOW_STEP_MERGE,
        WorkflowProcesses.WORKFLOW_REST_SCATTER_COPY_NETCDF,
        WorkflowProcesses.WORKFLOW_REST_SELECT_COPY_NETCDF,
        WorkflowProcesses.WORKFLOW_WPS1_SCATTER_COPY_NETCDF,
        WorkflowProcesses.WORKFLOW_WPS1_SELECT_COPY_NETCDF,
    }

    # FIXME: https://github.com/crim-ca/weaver/issues/25
    @pytest.mark.xfail(reason="WPS-1 multiple outputs not supported (https://github.com/crim-ca/weaver/issues/25)")
    def test_workflow_mixed_wps1_builtin_rest_docker_select_requirements(self):
        """
        Test the use of multiple applications of different :term:`Process` type in a :term:`Workflow`.

        Steps:
            1. Convert JSON array of NetCDF references to corresponding NetCDF files
               (process registered with ``WPS1Requirement`` using WPS-1 interface of builtin ``jsonarray2netcdf``).
            2. Select only the first file within the list.
            3. Convert NetCDF file to raw text data dumps.

        .. note::
            Because ``jsonarray2netcdf`` is running in subprocess instantiated by :mod:`cwltool`, file-server
            location cannot be mocked by the test suite. Employ local test paths as if they were already fetched.
        """

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            nc_refs = []
            for i in range(3):
                nc_name = f"test-file-{i}.nc"
                nc_refs.append(os.path.join("file://" + tmp_dir, nc_name))
                with open(os.path.join(tmp_dir, nc_name), mode="w", encoding="utf-8") as tmp_file:
                    tmp_file.write(f"DUMMY NETCDF DATA #{i}")
            with open(os.path.join(tmp_dir, "netcdf-array.json"), mode="w", encoding="utf-8") as tmp_file:
                json.dump(nc_refs, tmp_file)  # must match execution body

            def mock_tmp_input(requests_mock):
                mocked_file_server(tmp_dir, tmp_host, self.settings, requests_mock=requests_mock)

            results = self.workflow_runner(WorkflowProcesses.WORKFLOW_WPS1_SELECT_COPY_NETCDF,
                                           [WorkflowProcesses.APP_WPS1_JSON_ARRAY_2_NETCDF,
                                            WorkflowProcesses.APP_DOCKER_NETCDF_2_TEXT],
                                           log_full_trace=True, requests_mock_callback=mock_tmp_input)

            stack.enter_context(mocked_wps_output(self.settings))  # allow retrieval of HTTP WPS output
            stage_out_tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # different dir to avoid override
            final_output = results.get("output", {}).get("href", "")
            expected_index = 1  # see 'Execute_WorkflowSelectCopyNestedOutDir.json'
            result_file = f"test-file-{expected_index}.txt"  # extension converted from NetCDF data dump
            self.assert_test(lambda: final_output.startswith("http") and final_output.endswith(result_file),
                             message="Workflow output file with nested directory globs should have been automatically"
                                     "mapped between steps until the final staging WPS output URL.")
            output_path = fetch_file(final_output, stage_out_tmp_dir, settings=self.settings)
            with open(output_path, mode="r", encoding="utf-8") as out_file:
                output_data = out_file.read()
            self.assert_test(lambda: output_data == f"DUMMY NETCDF DATA #{expected_index}",
                             message="Workflow output data should have made it through the "
                                     "workflow of different process types.")

    def test_workflow_mixed_rest_builtin_wps1_docker_select_requirements(self):
        """
        Test the use of multiple applications of different :term:`Process` type in a :term:`Workflow`.

        Steps:
            1. Convert JSON array of NetCDF references to corresponding NetCDF files (builtin ``jsonarray2netcdf``).
            2. Select only the first file within the list.
            3. Convert NetCDF file to raw text data dumps (using WPS-1 interface of process with ``DockerRequirement``).

        .. note::
            Because ``jsonarray2netcdf`` is running in subprocess instantiated by :mod:`cwltool`, file-server
            location cannot be mocked by the test suite. Employ local test paths as if they were already fetched.
        """

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
            # jsonarray2netcdf cannot use local paths anymore for nested NetCDF, provide them through tmp file server
            nc_dir = self.file_server.document_root
            nc_url = self.file_server.uri
            nc_refs = []
            for i in range(3):
                nc_name = f"test-file-{i}.nc"
                nc_path = os.path.join(nc_dir, nc_name)
                nc_href = f"{nc_url}/{nc_name}"
                nc_refs.append(nc_href)
                with open(nc_path, mode="w", encoding="utf-8") as tmp_file:
                    tmp_file.write(f"DUMMY NETCDF DATA #{i}")

            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            with open(os.path.join(tmp_dir, "netcdf-array.json"), mode="w", encoding="utf-8") as tmp_file:
                json.dump(nc_refs, tmp_file)  # must match execution body

            def mock_tmp_input(requests_mock):
                mocked_file_server(tmp_dir, tmp_host, self.settings, requests_mock=requests_mock)
                mocked_wps_output(self.settings, requests_mock=requests_mock)

            results = self.workflow_runner(WorkflowProcesses.WORKFLOW_REST_SELECT_COPY_NETCDF,
                                           [WorkflowProcesses.APP_DOCKER_NETCDF_2_TEXT,  # indirectly needed by WPS-1
                                            WorkflowProcesses.APP_WPS1_DOCKER_NETCDF_2_TEXT],
                                           log_full_trace=True, requests_mock_callback=mock_tmp_input)

            stack.enter_context(mocked_wps_output(self.settings))  # allow retrieval of HTTP WPS output
            stage_out_tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # different dir to avoid override
            final_output = results.get("output", {}).get("href", "")
            expected_index = 1  # see execute payload
            result_file = f"test-file-{expected_index}.txt"  # extension converted from NetCDF data dump
            self.assert_test(lambda: final_output.startswith("http") and final_output.endswith(result_file),
                             message="Workflow output file with nested directory globs should have been automatically"
                                     "mapped between steps until the final staging WPS output URL.")
            output_path = fetch_file(final_output, stage_out_tmp_dir, settings=self.settings)
            with open(output_path, mode="r", encoding="utf-8") as out_file:
                output_data = out_file.read()
            self.assert_test(lambda: output_data == f"DUMMY NETCDF DATA #{expected_index}",
                             message="Workflow output data should have made it through the "
                                     "workflow of different process types.")

    def test_workflow_mixed_rest_builtin_wps1_docker_scatter_requirements(self):
        """
        Test the use of multiple applications of different :term:`Process` type in a :term:`Workflow`.

        Steps:
            1. Convert JSON array of NetCDF references to corresponding NetCDF files
               (process registered with ``WPS1Requirement`` using WPS-1 interface of builtin ``jsonarray2netcdf``).
            2. Convert NetCDF file to raw text data dumps (using scattered applications per-file).

        .. note::
            Because ``jsonarray2netcdf`` is running in subprocess instantiated by :mod:`cwltool`, file-server
            location cannot be mocked by the test suite. With security checks, they cannot be locally defined either,
            since the :term:`CWL` temporary directory is not known in advance for respective ``CommandLineTool`` steps.
            Employ a *real* file-server for test paths to emulate a remote location to be fetched.

        .. seealso::
            Inverse :term:`WPS` / :term:`OGC API - Processes` process references from
            :meth:`test_workflow_mixed_wps1_builtin_rest_docker_scatter_requirements`.
        """

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"    # must match in 'WorkflowWPS1ScatterCopyNetCDF/execute.yml'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            nc_refs = []
            for i in range(3):
                nc_name = f"test-file-{i}.nc"
                nc_path = os.path.join(self.file_server.document_root, nc_name)
                nc_href = os.path.join(self.file_server.uri, nc_name)
                nc_refs.append(nc_href)
                with open(nc_path, mode="w", encoding="utf-8") as tmp_file:
                    tmp_file.write(f"DUMMY NETCDF DATA #{i}")
            with open(os.path.join(tmp_dir, "netcdf-array.json"), mode="w", encoding="utf-8") as tmp_file:
                json.dump(nc_refs, tmp_file)  # must match execution body

            def mock_tmp_input(requests_mock):
                mocked_file_server(tmp_dir, tmp_host, self.settings, requests_mock=requests_mock)
                mocked_wps_output(self.settings, requests_mock=requests_mock)

            self.workflow_runner(WorkflowProcesses.WORKFLOW_WPS1_SCATTER_COPY_NETCDF,
                                 [WorkflowProcesses.APP_DOCKER_NETCDF_2_TEXT,  # required for reference by WPS below
                                  WorkflowProcesses.APP_WPS1_DOCKER_NETCDF_2_TEXT],
                                 log_full_trace=True, requests_mock_callback=mock_tmp_input)

    def test_workflow_mixed_wps1_builtin_rest_docker_scatter_requirements(self):
        """
        Test the use of multiple applications of different :term:`Process` type in a :term:`Workflow`.

        Steps:
            1. Convert JSON array of NetCDF references to corresponding NetCDF files
               (process registered with ``WPS1Requirement`` using WPS-1 interface of builtin ``jsonarray2netcdf``).
            2. Convert NetCDF file to raw text data dumps (using scattered applications per-file).

        .. note::
            Because ``jsonarray2netcdf`` is running in subprocess instantiated by :mod:`cwltool`, file-server
            location cannot be mocked by the test suite. With security checks, they cannot be locally defined either,
            since the :term:`CWL` temporary directory is not known in advance for respective ``CommandLineTool`` steps.
            Employ a *real* file-server for test paths to emulate a remote location to be fetched.

        .. seealso::
            Inverse :term:`WPS` / :term:`OGC API - Processes` process references from
            :meth:`test_workflow_mixed_rest_builtin_wps1_docker_scatter_requirements`.
        """

        file_count = 3
        file_name_template = "test-file-{i}.nc"
        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'WorkflowRESTScatterCopyNetCDF/execute.yml'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            nc_refs = []
            for i in range(file_count):
                nc_name = file_name_template.format(i=i)
                nc_path = os.path.join(self.file_server.document_root, nc_name)
                nc_href = os.path.join(self.file_server.uri, nc_name)
                nc_refs.append(nc_href)
                with open(nc_path, mode="w", encoding="utf-8") as tmp_file:
                    tmp_file.write(f"DUMMY NETCDF DATA #{i}")
            with open(os.path.join(tmp_dir, "netcdf-array.json"), mode="w", encoding="utf-8") as tmp_file:
                json.dump(nc_refs, tmp_file)  # must match execution body

            def mock_tmp_input(requests_mock):
                mocked_file_server(tmp_dir, tmp_host, self.settings, requests_mock=requests_mock)
                mocked_wps_output(self.settings, requests_mock=requests_mock)

            result = self.workflow_runner(
                WorkflowProcesses.WORKFLOW_REST_SCATTER_COPY_NETCDF,
                [
                    WorkflowProcesses.APP_WPS1_JSON_ARRAY_2_NETCDF,  # no need to register its builtin ref
                    WorkflowProcesses.APP_DOCKER_NETCDF_2_TEXT,
                ],
                log_full_trace=True,
                requests_mock_callback=mock_tmp_input,
            )
            assert isinstance(result["output"], list)
            assert len(result["output"]) == file_count
            out_files = [os.path.split(file["href"])[-1] for file in result["output"]]
            assert out_files == [file_name_template.format(i=i).replace(".nc", ".txt") for i in range(file_count)]

    def test_workflow_docker_applications(self):
        self.workflow_runner(WorkflowProcesses.WORKFLOW_STAGE_COPY_IMAGES,
                             [WorkflowProcesses.APP_DOCKER_STAGE_IMAGES, WorkflowProcesses.APP_DOCKER_COPY_IMAGES],
                             log_full_trace=True)

    def test_workflow_subdir_output_glob(self):
        """
        Test that validates the retrieval of nested directory output files between workflow steps.

        Following the execution of a :term:`Workflow` step, an :term:`Application Package` using an ``outputBinding``
        with ``glob`` looking for the file to stage out within a sub-directory as follows are automatically generated
        under the output directory by :term:`CWL` within the same structure.

        .. code-block:: yaml
            outputs:
                text-output:
                    outputBinding:
                        glob": "sub/dir/to/*.txt"

        In other words, a file generated as ``/tmp/cwl-tmpXYZ/sub/dir/to/result.txt`` by the Docker application would
        be staged out in the output directory with the full path. This poses problem in the case of `Weaver` workflows
        because each of those files are then staged out to the :term:`WPS` output directory under the :term:`Job` UUID.
        Therefore, the following step in the workflow receives a nested-directory path that does not correspond to the
        expected non-nested location after mapping between :term:`WPS` output directory and URL.

        .. seealso::
            Handling of this behaviour to adjust nested directory within the application against staged-out non-nested
            directories is accomplished in :meth:`weaver.processes.wps_process_base.WpsProcessInterface.stage_results`.
        """
        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowCopyNestedOutDir.json'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            with open(os.path.join(tmp_dir, "test-file.txt"), mode="w", encoding="utf-8") as tmp_file:
                tmp_file.write("DUMMY DATA")  # must match execution body

            def mock_tmp_input(requests_mock):
                mocked_file_server(tmp_dir, tmp_host, self.settings, requests_mock=requests_mock)

            results = self.workflow_runner(WorkflowProcesses.WORKFLOW_CHAIN_COPY,
                                           [WorkflowProcesses.APP_DOCKER_COPY_NESTED_OUTDIR,
                                            WorkflowProcesses.APP_DOCKER_COPY_NESTED_OUTDIR],
                                           log_full_trace=True, requests_mock_callback=mock_tmp_input)

            stack.enter_context(mocked_wps_output(self.settings))  # allow retrieval of HTTP WPS output
            stage_out_tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # different dir to avoid override
            final_output = results.get("output", {}).get("href", "")
            self.assert_test(lambda: final_output.startswith("http") and final_output.endswith("test-file.txt"),
                             message="Workflow output file with nested directory globs should have been automatically"
                                     "mapped between steps until the final staging WPS output URL.")
            output_path = fetch_file(final_output, stage_out_tmp_dir, settings=self.settings)
            with open(output_path, mode="r", encoding="utf-8") as out_file:
                output_data = out_file.read()
            self.assert_test(lambda: output_data == "COPY:\nCOPY:\nDUMMY DATA",
                             message="Workflow output file with nested directory globs should contain "
                                     "two COPY prefixes, one added by each intermediate step of the Workflow.")

    def test_workflow_directory_input_output_chaining(self):
        """
        Validate support of CWL Directory type as I/O across the full Workflow procedure.
        """

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            expect_http_files = [
                "file1.txt",
                "dir/file2.txt",
                "dir/nested/file3.txt",
                "dir/sub/other/file4.txt",
            ]
            for file in expect_http_files:
                path = os.path.join(tmp_dir, file)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, mode="w", encoding="utf-8") as f:
                    f.write("test data")

            def mock_tmp_input(requests_mock):
                mocked_file_server(
                    tmp_dir, tmp_host, self.settings,
                    requests_mock=requests_mock,
                    mock_head=True,
                    mock_get=True,
                    mock_browse_index=True,
                )
                mocked_wps_output(
                    self.settings,
                    requests_mock=requests_mock,
                    mock_head=True,
                    mock_get=True,
                    mock_browse_index=True,
                )

            exec_body = {
                "inputs": {
                    "files": [
                        {"href": f"{tmp_host}/{tmp_file}", "format": ContentType.TEXT_PLAIN}
                        for tmp_file in expect_http_files
                    ]
                },
                "outputs": {"output": {"transmissionMode": ExecuteTransmissionMode.REFERENCE}},
                "response": ExecuteResponse.DOCUMENT,
            }
            results = self.workflow_runner(WorkflowProcesses.WORKFLOW_DIRECTORY_LISTING,
                                           [WorkflowProcesses.APP_DIRECTORY_LISTING_PROCESS,
                                            WorkflowProcesses.APP_DIRECTORY_MERGING_PROCESS],
                                           override_execute_body=exec_body,
                                           log_full_trace=True,
                                           requests_mock_callback=mock_tmp_input)

            stack.enter_context(mocked_wps_output(self.settings))  # allow retrieval of HTTP WPS output
            stage_out_tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # different dir to avoid override
            final_output = results.get("output", {}).get("href", "")
            self.assert_test(lambda: final_output.startswith("http") and final_output.endswith("output.txt"),
                             message="Could not find expected Workflow output file.")
            output_path = fetch_file(final_output, stage_out_tmp_dir, settings=self.settings)
            with open(output_path, mode="r", encoding="utf-8") as out_file:
                output_data = out_file.read()
            # data should be a sorted literal string listing for the files with permissions and other stat metadata
            # only the file names should remain (not nested dirs), as per the directory listing package definition
            # perform initial check that output from 'ls' is found
            output_lines = list(filter(lambda _line: bool(_line), output_data.split("\n")))
            pattern_perms = re.compile(r"^-rw-[r-][w-]-r-- .*$")  # group perms variable on different platforms
            self.assert_test(
                lambda: (
                    len(output_lines) == len(expect_http_files) and
                    all(re.match(pattern_perms, line) for line in output_lines) and
                    all(" /var/lib/cwl/stg" in line for line in output_lines)
                ),
                message="Workflow output file expected to contain single file with raw string listing of "
                        "input files chained from generated output directory listing of the first step."
                        "\nDiff:"
                        f"\n{self.logger_separator_calls}\n"
                        f"{generate_diff(output_lines, expect_http_files)}"
                        f"\n{self.logger_separator_calls}"
            )
            # check that all expected files made it through the listing/directory input/output chaining between steps
            output_files = "\n".join(os.path.join(*line.rsplit("/", 2)[-2:]) for line in output_lines)  # type: ignore
            expect_files = "\n".join(os.path.join("output_dir", os.path.split(file)[-1]) for file in expect_http_files)
            self.assert_test(lambda: output_files == expect_files,
                             message="Workflow output file expected to contain single file with raw string listing of "
                                     "input files chained from generated output directory listing of the first step.")

    def test_workflow_echo_step_expression(self):
        """
        Validate that a Workflow using 'StepInputExpressionRequirement' is supported.
        """
        pkg = self.test_processes_info[WorkflowProcesses.WORKFLOW_ECHO].application_package
        assert CWL_REQUIREMENT_STEP_INPUT_EXPRESSION in pkg["requirements"], "missing requirement for test"
        result = self.workflow_runner(
            WorkflowProcesses.WORKFLOW_ECHO,
            [WorkflowProcesses.APP_ECHO],
            log_full_trace=True,
        )
        assert "output" in result
        path = map_wps_output_location(result["output"]["href"], container=self.settings)
        with open(path, mode="r", encoding="utf-8") as out_file:
            data = out_file.read()
        out = data.strip()  # ignore newlines added by the echo steps, good enough to test the operations worked
        assert out == "test-workflow-echo", (
            f"Should match the input value from 'execute' body of '{WorkflowProcesses.WORKFLOW_ECHO}'"
        )

    def test_workflow_secrets(self):
        details = self.workflow_runner(
            WorkflowProcesses.WORKFLOW_ECHO_SECRETS,
            [WorkflowProcesses.APP_ECHO_SECRETS],
            log_full_trace=True,
            detailed_results=True,
        )
        result = [res for res in details.values() if res["process"] == WorkflowProcesses.WORKFLOW_ECHO_SECRETS.value]
        result = result[0]["outputs"]
        assert "output" in result
        path = map_wps_output_location(result["output"]["href"], container=self.settings)
        with open(path, mode="r", encoding="utf-8") as out_file:
            data = out_file.read()
        out = data.strip()  # ignore newlines added by the echo steps, good enough to test the operations worked
        expect_secret = "secret message"
        # the secret is valid within the file only because of the nature of the job that echoes it in the output
        # however, it should not be directly in the logs or output responses
        assert out == expect_secret, (
            f"Should match the input value from 'execute' body of '{WorkflowProcesses.WORKFLOW_ECHO_SECRETS}'"
        )

        # validate there are no 'secrets' in responses
        found_secrets = []
        for job_detail in details.values():
            for loc in ["inputs", "outputs"]:  # type: Literal["inputs", "outputs"]
                for loc_id, loc_data in job_detail[loc].items():
                    if expect_secret in str(loc_data):
                        found_secrets.append({
                            "where": loc,
                            "id": loc_id,
                            "data": loc_data,
                            "process": job_detail["process"],
                            "job": job_detail["job"],
                        })
            if expect_secret in str(job_detail["logs"]):
                found_secrets.append({
                    "where": "logs",
                    "data": job_detail["logs"],
                    "process": job_detail["process"],
                    "job": job_detail["job"],
                })
        assert not found_secrets, f"Found exposed secrets that should have been masked:\n{repr_json(found_secrets)}"

        # make sure the logs included stdout with expected output
        # (ie: check that the fact that secrets are omitted is not only because no logs were captured...)
        capture_regex = re.compile(
            # note: each line is prefixed by the loggers details including the job state
            r".*running\s+----- Captured Log \(stdout\) -----\n"
            r".*running\s+OK!\n"
            r".*running\s+----- End of Logs -----\n"
        )
        for job in details.values():
            if job["process"] == WorkflowProcesses.APP_ECHO_SECRETS.value:
                assert capture_regex.search(job["logs"])

    def test_workflow_passthrough_expressions(self):
        """
        Test that validate literal data passed between steps.

        Validates that values are propagated property without the need of intermediate ``File`` type explicitly
        within the :term:`Workflow` or any of its underlying application steps. Also, uses various combinations of
        expression formats (:term:`CWL` ``$(...)`` reference and pure JavaScript ``${ ... }`` reference) to ensure
        they are handled correctly when collecting outputs.
        """
        result = self.workflow_runner(
            WorkflowProcesses.WORKFLOW_PASSTHROUGH_EXPRESSIONS,
            [WorkflowProcesses.APP_PASSTHROUGH_EXPRESSIONS],
            log_full_trace=True,
        )
        assert result == {
            "code1": 123456,
            "code2": 123456,
            "integer1": 3,
            "integer2": 3,
            "message1": "msg",
            "message2": "msg",
            "number1": 3.1416,
            "number2": 3.1416,
        }

    def test_workflow_multi_input_and_subworkflow(self):
        """
        Workflow that evaluates :term:`CWL` features simultaneously.

        Features tested:
          - ``MultipleInputFeatureRequirement``
          - ``InlineJavascriptRequirement``
          - ``StepInputExpressionRequirement``
          - ``SubworkflowFeatureRequirement``
        """
        wf_pkg = self.test_processes_info[WorkflowProcesses.WORKFLOW_STEP_MERGE].application_package
        wf_req = cast("CWL_RequirementsList", wf_pkg["requirements"])  # type: CWL_RequirementsList
        wf_req_classes = [req["class"] for req in wf_req]
        assert all(
            req in wf_req_classes
            for req in [
                CWL_REQUIREMENT_MULTIPLE_INPUT,
                CWL_REQUIREMENT_STEP_INPUT_EXPRESSION,
                CWL_REQUIREMENT_SUBWORKFLOW,
            ]
        ), "missing pre-requirements for test"
        wf_step_ids = [wf_step["run"].split(".", 1)[0] for wf_step in wf_pkg["steps"].values()]
        wf_step_classes = [
            self.test_processes_info[WorkflowProcesses(step)].application_package["class"]
            for step in wf_step_ids
        ]
        assert len(
            [wf_step_cls == ProcessType.WORKFLOW for wf_step_cls in wf_step_classes]
        ), "missing sub-workflow pre-requirement for test"

        result = self.workflow_runner(
            WorkflowProcesses.WORKFLOW_STEP_MERGE,
            [
                WorkflowProcesses.APP_ECHO,
                WorkflowProcesses.APP_READ_FILE,
                WorkflowProcesses.WORKFLOW_CHAIN_STRINGS,
            ],
            log_full_trace=True,
        )
        assert len(result) == 1
        assert "output" in result
        path = map_wps_output_location(result["output"]["href"], container=self.settings)
        with open(path, mode="r", encoding="utf-8") as out_file:
            data = out_file.read().strip()
        assert data == "Hello,World"

    def test_workflow_optional_input_propagation(self):
        wf_exec = self.test_processes_info[WorkflowProcesses.WORKFLOW_ECHO_OPTIONAL].execute_payload
        assert not wf_exec, "inputs must be empty to evaluate this behavior properly"
        details = self.workflow_runner(
            WorkflowProcesses.WORKFLOW_ECHO_OPTIONAL,
            [
                WorkflowProcesses.APP_ECHO_OPTIONAL,
            ],
            log_full_trace=True,
            detailed_results=True,
        )
        result = [
            res for res in details.values()
            if res["process"] == WorkflowProcesses.WORKFLOW_ECHO_OPTIONAL.value
        ][0]["outputs"]
        assert len(result) == 1
        assert "output" in result
        path = map_wps_output_location(result["output"]["href"], container=self.settings)
        with open(path, mode="r", encoding="utf-8") as out_file:
            data = out_file.read().strip()
        assert data == "test-message", "output from workflow should match the default resolved from input omission"

    @pytest.mark.oap_part3
    def test_workflow_ad_hoc_nested_process_chaining(self):
        """
        Validate the execution of an ad-hoc workflow directly submitted for execution with nested process references.

        The test purposely uses two different processes that have different input requirements, but that happen to have
        similarly named inputs/outputs, such that we can validate nesting chains the correct parameters at each level.
        Similarly, the same process is reused more than once in a nested fashion to make sure they don't get mixed.
        Finally, output selection is defined using multi-output processes to make sure filtering is applied inline.
        """
        passthrough_process_info = self.prepare_process(WorkflowProcesses.APP_PASSTHROUGH_EXPRESSIONS)
        echo_result_process_info = self.prepare_process(WorkflowProcesses.APP_ECHO_RESULTS_TESTER)

        workflow_exec = {
            "process": f"{self.WEAVER_RESTAPI_URL}{passthrough_process_info.path}",
            "inputs": {
                "message": {
                    "process": f"{self.WEAVER_RESTAPI_URL}{passthrough_process_info.path}",
                    "inputs": {
                        "message": {
                            "process": f"{self.WEAVER_RESTAPI_URL}{echo_result_process_info.path}",
                            "inputs": {
                                "message": "test"
                            },
                            "outputs": {"output_data": {}}
                        },
                        "code": 123,
                    },
                    "outputs": {"message": {}}
                },
                "code": 456,
            }
        }
        details = self.execute_monitor_process(
            passthrough_process_info,
            override_execute_body=workflow_exec,
            override_execute_path="/jobs",
        )

        # note:
        #   Because we are running an ad-hoc nested chaining of processes rather than the typical 'workflow'
        #   approach that has all execution steps managed by CWL, each nested call is performed on its own.
        #   Therefore, the collected details will only contain the logs from the top-most process and its directly
        #   nested process. Further nested processes will not be embedded within those logs, as the entire nested
        #   operation is dispatched as a "single process". Retrieve the logs iteratively crawling into the nested jobs.
        details_to_process = list(details.values())
        while details_to_process:
            active_detail = details_to_process.pop(0)
            if active_detail["inputs"] == workflow_exec["inputs"]:
                continue  # top-most process, already got all logs
            nested_job_id = active_detail["job"]
            nested_job_proc = active_detail["process"]
            nested_job_url = f"/processes/{nested_job_proc}/jobs/{nested_job_id}"
            _, nested_details = self.try_retrieve_logs(nested_job_url, True)
            for job_id, job_detail in nested_details.items():
                if job_id not in details:
                    details[job_id] = job_detail
                    details_to_process.append(job_detail)

        self.assert_test(
            lambda: len(details) == 3,
            "Jobs amount should match the number of involved nested processes.",
        )

        # heuristic:
        # since all nested processes contain all other definitions as input, we can sort by size deepest->highest
        job_details = sorted(details.values(), key=lambda info: len(str(info["inputs"])))

        self.assert_test(
            lambda: job_details[0]["outputs"] == {
                "output_data": {"value": "test"}
            }
        )
        self.assert_test(
            lambda: job_details[1]["outputs"] == {
                "message": {"value": "test"},
            }
        )
        self.assert_test(
            lambda: job_details[2]["outputs"] == {
                "message": {"value": "test"},
                "code": {"value": 456},
                "number": {"value": 3.1416},
                "integer": {"value": 3},
            }
        )

        for job_detail in job_details:
            job_progresses = [
                float(progress) for progress in
                re.findall(
                    # Extra '.*\n' is to make sure we match only the first percent of the current job log per line.
                    # Because of nested processes and CWL operations, there can be sub-progress percentages as well.
                    r"([0-9]+(?:\.[0-9]+)?)%.*\n",
                    job_detail["logs"],
                )
            ]
            self.assert_test(
                lambda: sorted(job_progresses) == job_progresses,
                "Job log progress values should be in sequential order even when involving a nested process execution."
            )
