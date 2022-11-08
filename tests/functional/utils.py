import json
import os
import time
import unittest
from collections import OrderedDict
from copy import deepcopy
from typing import TYPE_CHECKING, overload
from urllib.parse import urlparse

import pyramid.testing
import pytest
import yaml
from pyramid.httpexceptions import HTTPOk

from tests.functional import APP_PKG_ROOT
from tests.utils import (
    get_test_weaver_app,
    get_test_weaver_config,
    mocked_sub_requests,
    setup_config_with_celery,
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver import WEAVER_ROOT_DIR
from weaver.database import get_db
from weaver.datatype import Job
from weaver.formats import ContentType
from weaver.processes.constants import ProcessSchema
from weaver.status import Status
from weaver.utils import fully_qualified_name, load_file
from weaver.visibility import Visibility

if TYPE_CHECKING:
    from typing import Any, Dict, Iterable, Optional, Tuple, Union
    from typing_extensions import Literal

    from weaver.typedefs import (
        AnyRequestMethod,
        AnyResponseType,
        AnyUUID,
        CWL,
        JSON,
        ProcessDeployment,
        ProcessDescription,
        ProcessExecution,
        SettingsType
    )

    ReferenceType = Literal["deploy", "describe", "execute", "package"]


class ResourcesUtil(object):
    @classmethod
    def request(cls, method, url, *args, **kwargs):
        # type: (AnyRequestMethod, str, *Any, **Any) -> AnyResponseType
        """
        Request operation to retrieve remote payload definitions.

        Can be left undefined (not overridden) if ``local=True`` is used.
        """

    @classmethod
    @overload
    def retrieve_payload(cls,
                         process,           # type: str
                         ref_type=None,     # type: Literal["deploy"]
                         ref_name=None,     # type: Optional[str]
                         ref_found=False,   # type: Literal[False]
                         location=None,     # type: Optional[str]
                         local=False,       # type: bool
                         ):                 # type: (...) -> Union[ProcessDeployment, Dict[str, JSON]]
        ...

    @classmethod
    @overload
    def retrieve_payload(cls,
                         process,           # type: str
                         ref_type=None,     # type: Literal["describe"]
                         ref_name=None,     # type: Optional[str]
                         ref_found=False,   # type: Literal[False]
                         location=None,     # type: Optional[str]
                         local=False,       # type: bool
                         ):                 # type: (...) -> Union[ProcessDescription, Dict[str, JSON]]
        ...

    @classmethod
    @overload
    def retrieve_payload(cls,
                         process,           # type: str
                         ref_type=None,     # type: Literal["execute"]
                         ref_name=None,     # type: Optional[str]
                         ref_found=False,   # type: Literal[False]
                         location=None,     # type: Optional[str]
                         local=False,       # type: bool
                         ):                 # type: (...) -> Union[ProcessExecution, Dict[str, JSON]]
        ...

    @classmethod
    @overload
    def retrieve_payload(cls,
                         process,           # type: str
                         ref_type=None,     # type: Literal["package"]
                         ref_name=None,     # type: Optional[str]
                         ref_found=False,   # type: Literal[False]
                         location=None,     # type: Optional[str]
                         local=False,       # type: bool
                         ):                 # type: (...) -> CWL
        ...

    @classmethod
    @overload
    def retrieve_payload(cls,
                         process,           # type: str
                         ref_type=None,     # type: ReferenceType
                         ref_name=None,     # type: Optional[str]
                         ref_found=False,   # type: Literal[True]
                         location=None,     # type: Optional[str]
                         local=False,       # type: bool
                         ):                 # type: (...) -> str
        ...

    @classmethod
    def retrieve_payload(cls, process, ref_type=None, ref_name=None, ref_found=False, location=None, local=False):
        # type: (str, Optional[ReferenceType], Optional[str], bool, Optional[str], bool) -> Union[Dict[str, JSON], str]
        """
        Retrieve content using known structures and locations.

        .. seealso::
            :meth:`retrieve_process_info`

        :param process: Process identifier.
        :param ref_type:
            Content reference type to retrieve {deploy, execute, package}.
            Required if no name or location provided.
        :param ref_name:
            Explicit name to look for. Can be just the name or with extension.
            Can be omitted if type or location is specified instead.
        :param ref_found: Return the first matched reference itself instead of its contents.
        :param location: Override location (unique location with exact lookup instead of variations).
        :param local: Consider only local application packages, but still use name variations lookup.
        :return: First matched contents.
        """
        if location:
            locations = [location]
        else:
            if local:
                var_locations = [APP_PKG_ROOT]
            else:
                base_url = "https://raw.githubusercontent.com/"
                var_locations = list(dict.fromkeys([  # don't use set to preserve this prioritized order
                    APP_PKG_ROOT,
                    os.getenv("TEST_GITHUB_SOURCE_URL"),
                    f"{base_url}/crim-ca/testbed14/master/application-packages",
                    f"{base_url}/crim-ca/application-packages/master/OGC/TB16/application-packages",
                ]))
                var_locations = [url for url in var_locations if url]

            locations = []
            if ref_name:
                for var_loc in var_locations:
                    if "." not in ref_name:
                        ref_name = ref_name + ".json"  # will still retry extensions
                    locations.extend([
                        f"{var_loc}/{ref_name}",
                        f"{var_loc}/{process}/{ref_name}",
                    ])
            else:
                if ref_type == "deploy":
                    ref_search = [
                        f"DeployProcess_{process}.json",
                        f"{process}/deploy.json",
                        f"{process}/DeployProcess_{process}.json",
                    ]
                elif ref_type == "describe":
                    ref_search = [
                        f"Describe_{process}.json",
                        f"{process}/describe.json",
                        f"{process}/Describe_{process}.json",
                    ]
                elif ref_type == "execute":
                    ref_search = [
                        f"Execute_{process}.json",
                        f"{process}/execute.json",
                        f"{process}/Execute_{process}.json",
                    ]
                elif ref_type == "package":
                    ref_search = [
                        f"{process}.cwl",
                        f"{process}/package.cwl",
                        f"{process}/{process}.cwl",
                        f"{process}/{process.lower()}.cwl",
                        f"{process}/{process.title()}.cwl",
                    ]
                else:
                    raise ValueError(f"unknown reference type: {ref_type}")

                for var_loc in var_locations:
                    for var_ref in ref_search:
                        locations.append(f"{var_loc}/{var_ref}")

        tested_ref = []
        try:
            for path in locations:
                extension = os.path.splitext(path)[-1]
                retry_extensions = [".json", ".yaml", ".yml"]
                if extension not in retry_extensions:
                    retry_extensions = [extension]
                # Try to find it locally, then fallback to remote
                for ext in retry_extensions:
                    path_ext = os.path.splitext(path)[0] + ext
                    if os.path.isfile(path_ext):
                        if ref_found:
                            return path_ext
                        with open(path_ext, mode="r", encoding="utf-8") as f:
                            json_payload = yaml.safe_load(f)  # both JSON/YAML
                            return json_payload
                    if urlparse(path_ext).scheme != "":
                        if ref_found:
                            return path
                        resp = cls.request("GET", path, force_requests=True, ignore_errors=True)
                        if resp and resp.status_code == HTTPOk.code:
                            return yaml.safe_load(resp.text)  # both JSON/YAML
                    tested_ref.append(path)
        except (IOError, ValueError):
            pass


class JobUtils(object):
    job_store = None
    job_info = None  # type: Iterable[Job]

    def message_with_jobs_mapping(self, message="", indent=2):
        # type: (str, int) -> str
        """
        For helping debugging of auto-generated job ids.
        """
        mapping = OrderedDict(sorted((str(j.task_id), str(j.id)) for j in self.job_store.list_jobs()))
        return f"{message}\nMapping Task-ID/Job-ID:\n{json.dumps(mapping, indent=indent)}"

    def assert_equal_with_jobs_diffs(self,
                                     jobs_result,           # type: Iterable[Union[AnyUUID, Job]]
                                     jobs_expect,           # type: Iterable[Union[AnyUUID, Job]]
                                     test_values=None,      # type: Union[JSON, str]
                                     message="",            # type: str
                                     indent=2,              # type: int
                                     index=None,            # type: Optional[int]
                                     invert=False,          # type: bool
                                     jobs=None,             # type: Iterable[Job]
                                     ):                     # type: (...) -> None
        jobs_result = [str(job.id) if isinstance(job, Job) else str(job) for job in jobs_result]
        jobs_expect = [str(job.id) if isinstance(job, Job) else str(job) for job in jobs_expect]
        mapping = {str(job.id): str(job.task_id) for job in (jobs or self.job_info)}
        missing = set(jobs_expect) - set(jobs_result)
        unknown = set(jobs_result) - set(jobs_expect)
        assert (
            (invert or len(jobs_result) == len(jobs_expect)) and
            all((job not in jobs_expect if invert else job in jobs_expect) for job in jobs_result)
        ), (
            (message if message else "Different jobs returned than expected") +
            (f" (index: {index})" if index is not None else "") +
            ("\nResponse: " + json.dumps(sorted(jobs_result), indent=indent)) +
            ("\nExpected: " + json.dumps(sorted(jobs_expect), indent=indent)) +
            ("\nMissing: " + json.dumps(sorted(f"{job} ({mapping[job]})" for job in missing), indent=indent)) +
            ("\nUnknown: " + json.dumps(sorted(f"{job} ({mapping[job]})" for job in unknown), indent=indent)) +
            ("\nTesting: " + (
                (json.dumps(test_values, indent=indent) if isinstance(test_values, (dict, list)) else str(test_values))
                if test_values else ""
            )) +
            (self.message_with_jobs_mapping())
        )


@pytest.mark.functional
class WpsConfigBase(unittest.TestCase):
    json_headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
    monitor_timeout = 30
    monitor_interval = 1
    settings = {}  # type: SettingsType

    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is not WpsConfigBase)
        super(WpsConfigBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        config = get_test_weaver_config(settings=cls.settings)
        config = setup_config_with_mongodb(config)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        cls.service_store = setup_mongodb_servicestore(config)  # force reset
        cls.process_store = setup_mongodb_processstore(config)  # force reset
        cls.job_store = setup_mongodb_jobstore(config)
        cls.app = get_test_weaver_app(config=config, settings=cls.settings)
        cls.db = get_db(config)
        cls.config = config
        cls.settings.update(cls.config.registry.settings)  # back propagate changes

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    @classmethod
    def describe_process(cls, process_id, describe_schema=ProcessSchema.OGC):
        path = f"/processes/{process_id}?schema={describe_schema}"
        resp = cls.app.get(path, headers=cls.json_headers)
        assert resp.status_code == 200
        return deepcopy(resp.json)

    @classmethod
    def deploy_process(cls, payload, process_id=None, describe_schema=ProcessSchema.OGC, mock_requests_only_local=True):
        # type: (JSON, Optional[str], str, bool) -> Tuple[ProcessDescription, CWL]
        """
        Deploys a process with :paramref:`payload`.

        :returns: resulting tuple of ``(process-description, package)`` JSON responses.
        """
        if process_id:
            if "process" in payload["processDescription"]:
                proc_desc = payload["processDescription"]["process"]
            else:
                proc_desc = payload["processDescription"]
            proc_desc["id"] = process_id  # type: ignore
        exec_list = payload.get("executionUnit", [])
        if len(exec_list):
            # test-only feature:
            #   substitute 'href' starting by 'tests/' by the corresponding file in test resources
            #   this allows clean separation of deploy payload from CWL to allow reuse and test CWL locally beforehand
            exec_href = exec_list[0].get("href", "")
            if exec_href.startswith("tests/"):
                exec_unit = load_file(os.path.join(WEAVER_ROOT_DIR, exec_href))
                exec_list[0]["unit"] = exec_unit
                exec_list[0].pop("href")
        resp = mocked_sub_requests(cls.app, "post_json", "/processes",
                                   data=payload, headers=cls.json_headers, only_local=mock_requests_only_local)
        assert resp.status_code == 201, f"Expected successful deployment.\nError:\n{resp.text}"
        path = resp.json["processSummary"]["processDescriptionURL"]
        body = {"value": Visibility.PUBLIC}
        resp = cls.app.put_json(f"{path}/visibility", params=body, headers=cls.json_headers)
        assert resp.status_code == 200, f"Expected successful visibility.\nError:\n{resp.text}"
        info = []
        for info_path in [f"{path}?schema={describe_schema}", f"{path}/package"]:
            resp = cls.app.get(info_path, headers=cls.json_headers)
            assert resp.status_code == 200
            info.append(deepcopy(resp.json))
        return info  # type: ignore

    def _try_get_logs(self, status_url):
        _resp = self.app.get(f"{status_url}/logs", headers=self.json_headers)
        if _resp.status_code == 200:
            _text = "\n".join(_resp.json)
            return f"Error logs:\n{_text}"
        return ""

    def fully_qualified_test_process_name(self):
        return fully_qualified_name(self).replace(".", "-")

    def monitor_job(self,
                    status_url,                         # type: str
                    timeout=None,                       # type: Optional[int]
                    interval=None,                      # type: Optional[int]
                    return_status=False,                # type: bool
                    wait_for_status=None,               # type: Optional[str]
                    expect_failed=False,                # type: bool
                    ):                                  # type: (...) -> Dict[str, JSON]
        """
        Job polling of status URL until completion or timeout.

        :param status_url: URL with job ID where to monitor execution.
        :param timeout: timeout of monitoring until completion or abort.
        :param interval: wait interval (seconds) between polling monitor requests.
        :param return_status: return final status body instead of results once job completed.
        :param wait_for_status:
            Monitor until the requested status is reached (default: when job is completed).
            If no value is specified and :paramref:`expect_failed` is enabled, completion status will be a failure.
            Otherwise, the successful status is used instead. Explicit intermediate status can be requested instead.
            Whichever status is specified or defaulted, failed/succeeded statuses will break-out of the monitoring loop,
            since no more status change is possible.
        :param expect_failed:
            If enabled, allow failing status to during status validation.
            If the final status is successful when failure is expected, status check will fail.
            Enforces :paramref:`return_status` to ``True`` since no result can be obtained.
        :return: result of the successful job, or the status body if requested.
        :raises AssertionError: when job fails or took too long to complete.
        """
        wait_for_status = wait_for_status or Status.SUCCEEDED

        def check_job_status(_resp, running=False):
            # type: (AnyResponseType, bool) -> bool
            body = _resp.json
            pretty = json.dumps(body, indent=2, ensure_ascii=False)
            final = Status.FAILED if expect_failed else Status.SUCCEEDED
            statuses = [Status.ACCEPTED, Status.RUNNING, final] if running else [final]
            assert _resp.status_code == 200, f"Execution failed:\n{pretty}\n{self._try_get_logs(status_url)}"
            assert body["status"] in statuses, f"Error job info:\n{pretty}\n{self._try_get_logs(status_url)}"
            return body["status"] in {wait_for_status, Status.SUCCEEDED, Status.FAILED}  # break condition

        time.sleep(1)  # small delay to ensure process execution had a chance to start before monitoring
        left = timeout or self.monitor_timeout
        delta = interval or self.monitor_interval
        once = True
        resp = None
        while left >= 0 or once:
            resp = self.app.get(status_url, headers=self.json_headers)
            if check_job_status(resp, running=True):
                break
            time.sleep(delta)
            once = False
            left -= delta
        check_job_status(resp)
        if return_status or expect_failed:
            return resp.json
        resp = self.app.get(f"{status_url}/results", headers=self.json_headers)
        assert resp.status_code == 200, f"Error job info:\n{resp.text}"
        return resp.json

    def get_outputs(self, status_url):
        resp = self.app.get(f"{status_url}/outputs", headers=self.json_headers)
        body = resp.json
        pretty = json.dumps(body, indent=2, ensure_ascii=False)
        assert resp.status_code == 200, f"Get outputs failed:\n{pretty}\n{self._try_get_logs(status_url)}"
        return body


@pytest.mark.functional
class AuthTokenApp(WpsConfigBase):
    @classmethod
    def setUpClass(cls):
        config = get_test_weaver_config(settings=cls.settings)
        config = setup_config_with_mongodb(config)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        cls.service_store = setup_mongodb_servicestore(config)  # force reset
        cls.process_store = setup_mongodb_processstore(config)  # force reset
        cls.job_store = setup_mongodb_jobstore(config)
        cls.app = get_test_weaver_app(config=config, settings=cls.settings)
        cls.db = get_db(config)
        cls.config = config
        cls.settings.update(cls.config.registry.settings)  # back propagate changes
