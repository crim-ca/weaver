# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results
import base64
import contextlib
import copy
import json
import os
import re
import tempfile
import uuid
from copy import deepcopy
from typing import TYPE_CHECKING

import colander
import mock
import pyramid.testing
import pytest
import stopit
import webtest.app
import yaml
from parameterized import parameterized
from pywps.inout import LiteralInput

from tests import resources
from tests.functional.utils import WpsConfigBase
from tests.utils import (
    get_links,
    mocked_execute_celery,
    mocked_process_job_runner,
    mocked_process_package,
    mocked_remote_server_requests_wps1,
    mocked_sub_requests,
    mocked_wps_output
)
from weaver import WEAVER_ROOT_DIR
from weaver.datatype import AuthenticationTypes, Process, Service
from weaver.exceptions import JobNotFound, ProcessNotFound
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import AcceptLanguage, ContentType, OutputFormat, get_cwl_file_format
from weaver.processes.builtin import register_builtin_processes
from weaver.processes.constants import (
    CWL_NAMESPACE_WEAVER_ID,
    CWL_NAMESPACE_WEAVER_URL,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_CUDA_NAME,
    ProcessSchema
)
from weaver.processes.types import ProcessType
from weaver.processes.wps_testing import WpsTestProcess
from weaver.status import Status
from weaver.utils import fully_qualified_name, get_path_kvp, load_file, ows_context_href
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import List, Optional, Tuple, TypeAlias
    from typing_extensions import Literal

    import _pytest  # noqa: W0212

    from weaver.processes.constants import ProcessSchemaType
    from weaver.typedefs import AnyHeadersContainer, AnyVersion, CWL, JSON, ProcessExecution, SettingsType

    Marker: TypeAlias = "_pytest.mark.structures.Mark"  # noqa


# noinspection PyTypeHints
@pytest.fixture(name="assert_cwl_no_warn_unknown_hint")
def fixture_cwl_no_warn_unknown_hint(caplog, request) -> None:
    # type: (pytest.LogCaptureFixture, pytest.FixtureRequest) -> None
    """
    Looks for a warning related to unknown :term:`CWL` requirement thrown by :mod:`cwltool`.

    If the `Weaver`-specific requirement was properly registered in the :term:`CWL` schema extensions,
    this warning should not occur as it would be validated against a known definition.

    .. seealso::
        - Registered `Weaver` extensions schemas defined in
          `weaver-extensions.yml`<weaver/schemas/weaver-extensions.yml>`_.
        - Registered `Weaver` extensions schemas correspond to:
          - :data:`CWL_REQUIREMENT_APP_BUILTIN`
          - :data:`CWL_REQUIREMENT_APP_ESGF_CWT`
          - :data:`CWL_REQUIREMENT_APP_OGC_API`
          - :data:`CWL_REQUIREMENT_APP_WPS1`

    Usage:

    .. code-block:: python

        @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
        @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [<CWL_HINT_TO_CHECK>], indirect=True)
        def test_to_mark(): ...

    .. note::
        Because the fixture evaluates the warning logs after the test executed,
        a failing condition will be indicated as "teardown" of the marked test.
    """
    yield caplog  # run the test and collect logs from it

    def is_cwl_fixture(marker, fixture):  # pragma: no cover
        mark = marker.name
        if mark != "parametrize":
            return False
        name = getattr(fixture, "name", None)
        func = None
        if not name:
            func = getattr(fixture, "_fixture_function_marker", None)
        if not func:
            func = getattr(fixture, "_pytestfixturefunction", None)
        if func:
            name = func.name
        return name == marker.args[0]

    markers = list(
        filter(
            lambda _marker: is_cwl_fixture(_marker, fixture_cwl_no_warn_unknown_hint),
            request.keywords.get("pytestmark", [])
        )
    )  # type: List[Marker]
    cwl_hint = markers[0].args[1][0]

    log_records = caplog.get_records(when="call")
    warn_hint = re.compile(rf".*unknown hint .*{cwl_hint}.*", re.IGNORECASE)
    warn_records = list(filter(lambda _rec: isinstance(_rec.msg, str) and warn_hint.match(_rec.msg), log_records))
    warn_message = "\n".join([_rec.msg for _rec in warn_records])
    assert not warn_records, (
        f"Expected no warning from resolved Weaver-specific Application Package requirement, got:\n{warn_message}",
    )


# pylint: disable=C0103,invalid-name
@pytest.mark.functional
class WpsRestApiProcessesTest(WpsConfigBase):
    remote_server = None    # type: str
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_path": "/ows/wps",
        "weaver.wps_output_url": "http://localhost/wpsoutputs",
    }  # type: SettingsType

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.service_store.clear_services()
        self.process_store.clear_processes()
        self.job_store.clear_jobs()

        self.process_remote_WPS1 = "process_remote_wps1"
        self.process_remote_WPS3 = "process_remote_wps3"
        self.process_public = WpsTestProcess(identifier="process_public", version="1.0.0")
        self.process_private = WpsTestProcess(identifier="process_private")
        weaver_api_url = get_wps_restapi_base_url(self.settings)
        weaver_wps_url = get_wps_url(self.settings)
        public_process = Process.convert(
            self.process_public,
            processDescriptionURL=f"{weaver_api_url}/processes/{self.process_public.identifier}",
            processEndpointWPS1=weaver_wps_url,
            jobControlOptions=ExecuteControlOption.values(),
        )
        self.process_store.save_process(public_process)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, Visibility.PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, Visibility.PRIVATE)

    def get_process_deploy_template(self, process_id=None, cwl=None, schema=ProcessSchema.OLD):
        # type: (Optional[str], Optional[CWL], ProcessSchemaType) -> JSON
        """
        Provides deploy process bare minimum template with undefined execution unit.

        To be used in conjunction with :meth:`get_application_package` and :meth:`validate_wps1_package`
        to avoid extra package content-specific validations.
        """
        if not process_id:
            process_id = self.fully_qualified_test_name()
        body = {
            "processDescription": {},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": []
        }
        meta = {
            "id": process_id,
            "title": f"Test process '{process_id}'.",
        }
        if schema == ProcessSchema.OLD:
            body["processDescription"]["process"] = meta
        else:
            body["processDescription"].update(meta)
        if cwl:
            body["executionUnit"].append({"unit": cwl})
        else:
            # full definition not required with mock
            # use 'href' variant to avoid invalid schema validation via more explicit 'unit'
            # note:
            #   hostname cannot have underscores according to [RFC-1123](https://www.ietf.org/rfc/rfc1123.txt)
            #   schema validator of Reference URL will appropriately raise such invalid string
            body["executionUnit"].append({"href": f"http://weaver.test/{process_id}.cwl"})
        return body

    @staticmethod
    def get_process_execute_template(test_input="not-specified"):
        # type: (str) -> ProcessExecution
        """
        Provides execute process bare minimum template definition.

        Contents correspond to required I/O for WPS process :class:`weaver.processes.wps_testing.WpsTestProcess`.
        """
        return {
            "inputs": [
                {"id": "test_input",
                 "data": test_input},
            ],
            "outputs": [
                {"id": "test_output",
                 "transmissionMode": ExecuteTransmissionMode.VALUE}
            ],
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
        }

    def test_get_processes(self):
        path = "/processes"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json
        assert isinstance(resp.json["processes"], list) and len(resp.json["processes"]) > 0
        for process in resp.json["processes"]:
            assert "id" in process and isinstance(process["id"], str)
            assert "title" in process and isinstance(process["title"], str)
            assert "version" in process and isinstance(process["version"], str)
            assert "keywords" in process and isinstance(process["keywords"], list)
            assert "metadata" in process and isinstance(process["metadata"], list)
            assert len(process["jobControlOptions"]) == 2
            assert ExecuteControlOption.ASYNC in process["jobControlOptions"]

        processes_id = [p["id"] for p in resp.json["processes"]]
        assert self.process_public.identifier in processes_id
        assert self.process_private.identifier not in processes_id

    def test_get_processes_summary_links(self):
        path = "/processes"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json
        assert len(resp.json["processes"])
        for process in resp.json["processes"]:
            self_link = [link for link in process["links"] if link["rel"] == "self"]
            alt_link = [link for link in process["links"] if link["rel"] == "alternate"]
            assert len(self_link) == 1
            assert len(alt_link) >= 1

        path = "/conformance"
        resp = self.app.get(path, headers=self.json_headers)
        conf = resp.json["conformsTo"]
        assert "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core/process-summary-links" in conf

    def test_get_processes_no_links(self):
        path = "/processes"
        resp = self.app.get(path, headers=self.json_headers, params={"links": False})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json
        assert len(resp.json["processes"])
        for process in resp.json["processes"]:
            assert "links" not in process

    def test_get_processes_with_paging(self):
        test_prefix = "test-proc-temp"
        for i in range(10):
            p_id = f"{test_prefix}-{i}"
            proc = self.process_private = Process(id=p_id, package={}, visibility=Visibility.PUBLIC)
            self.process_store.save_process(proc)
        _, total = self.process_store.list_processes(total=True, visibility=Visibility.PUBLIC)
        assert 10 < total < 15, "cannot run process paging test with current number of processes"
        limit = 5  # some value to get 3 pages, 2 full and the last partial
        remain = total - (2 * limit)
        limit_kvp = f"limit={limit}"

        path = get_path_kvp("/processes", page=1, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json
        processes = resp.json["processes"]
        assert isinstance(processes, list)
        assert resp.json["total"] == total

        base_url = self.settings["weaver.url"]
        proc_url = f"{base_url}/processes"
        assert len(resp.json["processes"]) == limit
        assert "links" in resp.json
        links = get_links(resp.json["links"])
        assert links["collection"] == proc_url
        assert links["search"] == proc_url
        assert links["up"] == base_url
        assert links["current"].startswith(proc_url) and limit_kvp in links["current"] and "page=1" in links["current"]
        assert links["prev"].startswith(proc_url) and limit_kvp in links["prev"] and "page=0" in links["prev"]
        assert links["next"].startswith(proc_url) and limit_kvp in links["next"] and "page=2" in links["next"]
        assert links["first"].startswith(proc_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(proc_url) and limit_kvp in links["last"] and "page=2" in links["last"]

        path = get_path_kvp("/processes", page=0, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["processes"]) == limit
        assert "links" in resp.json
        links = get_links(resp.json["links"])
        assert links["collection"] == proc_url
        assert links["search"] == proc_url
        assert links["up"] == base_url
        assert links["current"].startswith(proc_url) and limit_kvp in links["current"] and "page=0" in links["current"]
        assert links["prev"] is None
        assert links["next"].startswith(proc_url) and limit_kvp in links["next"] and "page=1" in links["next"]
        assert links["first"].startswith(proc_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(proc_url) and limit_kvp in links["last"] and "page=2" in links["last"]

        path = get_path_kvp("/processes", page=2, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["processes"]) == remain, "Last page should have only remaining processes."
        assert "links" in resp.json
        links = get_links(resp.json["links"])
        assert links["collection"] == proc_url
        assert links["search"] == proc_url
        assert links["up"] == base_url
        assert links["current"].startswith(proc_url) and limit_kvp in links["current"] and "page=2" in links["current"]
        assert links["prev"].startswith(proc_url) and limit_kvp in links["prev"] and "page=1" in links["prev"]
        assert links["next"] is None
        assert links["first"].startswith(proc_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(proc_url) and limit_kvp in links["last"] and "page=2" in links["last"]

    def test_get_processes_page_out_of_range(self):
        # ensure we have few items to list
        for i in range(10):
            proc = Process(id=f"test-process-paging-{i}", package={}, visibility=Visibility.PUBLIC)
            self.process_store.save_process(proc)
        resp = self.app.get(sd.processes_service.path, headers=self.json_headers)
        total = resp.json["total"]
        limit = total // 2
        max_limit = 1 if 2 * limit == total else 2  # exact match or last page remainder
        bad_page = 4

        path = get_path_kvp(sd.processes_service.path, page=bad_page, limit=limit)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert "IndexError" in resp.json["error"]
        assert f"[0,{max_limit}]" in resp.json["description"]
        assert "page" in resp.json["value"] and resp.json["value"]["page"] == bad_page

        # note:
        #   Following errors are generated by schema validators (page min=0, limit min=1) rather than above explicit
        #   checks. They don't provide the range because the error can apply to more than just paging failing value
        #   is still explicitly reported though. Because comparisons happen at query param level, it reports str values.

        path = get_path_kvp(sd.processes_service.path, page=-1, limit=limit)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "ProcessInvalidParameter"
        assert "page" in str(resp.json["cause"]) and "less than minimum" in str(resp.json["cause"])
        assert "page" in resp.json["value"] and resp.json["value"]["page"] == str(-1)

        path = get_path_kvp(sd.processes_service.path, page=0, limit=0)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "ProcessInvalidParameter"
        assert "limit" in str(resp.json["cause"]) and "less than minimum" in str(resp.json["cause"])
        assert "limit" in resp.json["value"] and resp.json["value"]["limit"] == str(0)

    def test_get_processes_bad_request_paging_providers(self):
        path = get_path_kvp("/processes", page=0, limit=10, providers=True)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert "ListingInvalidParameter" in resp.json["error"]

    def deploy_process_revisions(self, process_id):
        # type: (str) -> List[str]
        """
        Generates some revisions of a given process.
        """
        versions = ["1.2.0"]
        cwl, _ = self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=process_id, version=versions[0])
        data = {"title": "first revision", "version": "1.2.3"}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = {"title": "second revision", "version": "1.2.5"}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = {"title": "third revision", "version": "1.3.2", "jobControlOptions": [ExecuteControlOption.SYNC]}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = {"title": "fourth revision", "version": "1.3.4"}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = copy.deepcopy(cwl)  # type: JSON
        data.update({"version": "2.0.0", "inputs": {"message": {"type": "string"}}})
        resp = self.app.put_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 201
        versions.append(data["version"])
        data = {"value": Visibility.PUBLIC}  # must make visible otherwise will not be listed/retrievable
        resp = self.app.put_json(f"/processes/{process_id}/visibility", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        return sorted(versions)

    def test_get_processes_with_tagged_revisions(self):
        """
        Listing of mixed processes with and without revisions.

        .. versionadded:: 4.20
        """
        path = get_path_kvp("/processes", revisions=True, detail=False)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 200
        body = resp.json
        proc_no_revs = body["processes"]
        assert len(proc_no_revs) > 0, "cannot test mixed no-revision/with-revisions listing without prior processes"

        # create some processes with different combinations of revisions, no-version, single-version
        proc1_id = "first-process"
        proc1_versions = self.deploy_process_revisions(proc1_id)
        proc1_tags = [f"{proc1_id}:{ver}" for ver in proc1_versions]
        proc2_id = "other-process"
        proc2_versions = self.deploy_process_revisions(proc2_id)
        proc2_tags = [f"{proc2_id}:{ver}" for ver in proc2_versions]
        proc_total = len(proc_no_revs) + len(proc1_versions) + len(proc2_versions)

        path = get_path_kvp("/processes", revisions=True, detail=False)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 200
        body = resp.json
        assert len(body["processes"]) == proc_total
        assert body["processes"] == sorted(proc_no_revs + proc1_tags + proc2_tags)

        path = get_path_kvp("/processes", revisions=True, detail=True)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 200
        body = resp.json
        assert len(body["processes"]) == proc_total
        proc_result = [(proc["id"], proc["version"]) for proc in body["processes"]]
        proc_expect = [(proc_id, self.process_public.version) for proc_id in proc_no_revs]
        proc_expect += [(tag, ver) for tag, ver in zip(proc1_tags, proc1_versions)]
        proc_expect += [(tag, ver) for tag, ver in zip(proc2_tags, proc2_versions)]
        assert proc_result == sorted(proc_expect)

    def test_get_processes_with_history_revisions(self):
        """
        When requesting specific process ID with revisions, version history of this process is listed.

        .. versionadded:: 4.20
        """
        p_id = "test-process-history-revision"
        versions = self.deploy_process_revisions(p_id)
        revisions = [f"{p_id}:{ver}" for ver in versions]

        path = get_path_kvp("/processes", process=p_id, revisions=True, detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "processes" in body and len(body["processes"]) > 0
        assert body["processes"] == revisions, (
            "sorted processes by version with tagged representation expected when requesting revisions"
        )

        path = get_path_kvp("/processes", process=p_id, revisions=True, detail=True)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "processes" in body and len(body["processes"]) > 0
        result = [(proc["id"], proc["version"]) for proc in body["processes"]]
        expect = list(zip(revisions, versions))
        assert result == expect

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_get_processes_with_providers(self):
        test_svc_id = "test-provider-processes-listing"
        test_svc = Service(name=test_svc_id, url=resources.TEST_REMOTE_SERVER_URL)
        self.service_store.save_service(test_svc)
        _, total = self.process_store.list_processes(total=True, visibility=Visibility.PUBLIC)

        path = get_path_kvp("/processes", providers=True, detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert "processes" in resp.json and isinstance(resp.json["processes"], list)
        assert "providers" in resp.json and isinstance(resp.json["providers"], list)
        assert all(isinstance(proc, str) for proc in resp.json["processes"])
        assert all(isinstance(prov, dict) for prov in resp.json["providers"])
        assert len(resp.json["processes"]) == total
        assert len(resp.json["providers"]) == 1
        prov = resp.json["providers"][0]
        assert "id" in prov and prov["id"] == test_svc_id
        assert "processes" in prov and isinstance(prov["processes"], list)
        assert all(isinstance(proc, str) for proc in prov["processes"])
        assert len(prov["processes"]) == 2  # number of descriptions in TEST_REMOTE_SERVER_WPS1_GETCAP_XML
        assert set(prov["processes"]) == {"pavicstestdocs", "test-remote-process-wps1"}
        assert resp.json["total"] == total + 2, "Grand total of local+remote processes should be reported."

    @pytest.mark.filterwarnings("ignore::weaver.warning.NonBreakingExceptionWarning")  # unresponsive services
    @mocked_remote_server_requests_wps1([  # register valid server here, and another invalid within test
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_get_processes_with_providers_error_servers(self, mock_responses):
        # register service reachable but returning invalid XML
        invalid_id = "test-provider-process-listing-invalid"
        invalid_url = f"{resources.TEST_REMOTE_SERVER_URL}/invalid"
        invalid_data = "<xml> not a wps </xml>"
        mocked_remote_server_requests_wps1((invalid_url, invalid_data, []), mock_responses, data=True)

        # register a provider that doesn't have any responding server
        missing_id = "test-provider-process-listing-missing"
        missing_url = f"{resources.TEST_REMOTE_SERVER_URL}/does-not-exist"

        valid_id = "test-provider-process-listing-valid"
        self.service_store.clear_services()
        self.service_store.save_service(Service(name=valid_id, url=resources.TEST_REMOTE_SERVER_URL))
        self.service_store.save_service(Service(name=invalid_id, url=invalid_url))
        self.service_store.save_service(Service(name=missing_id, url=missing_url))

        # with ignore flag and no detail, failing providers are not validated and operation returns successfully
        # - servers that respond successfully with any content are kept (even if not valid WPS)
        # - servers without responses (cannot ping) are dropped from response
        path = get_path_kvp("/processes", providers=True, detail=False, ignore=True)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert "providers" in resp.json
        assert len(resp.json["providers"]) == 2
        providers = [prov["id"] for prov in resp.json["providers"]]
        assert set(providers) == {valid_id, invalid_id}
        valid_processes = resp.json["providers"][providers.index(valid_id)]["processes"]
        invalid_processes = resp.json["providers"][providers.index(invalid_id)]["processes"]
        assert set(valid_processes) == {"pavicstestdocs", "test-remote-process-wps1"}
        assert invalid_processes == []

        # with ignore and detail requested, providers must be parsed to obtain the extra metadata
        # invalid parsing should now also be dropped and return successfully with only the valid provider
        path = get_path_kvp("/processes", providers=True, detail=True, ignore=True)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert len(resp.json["providers"]) == 1
        assert resp.json["providers"][0]["id"] == valid_id
        prov_proc_info = resp.json["providers"][0]["processes"]
        assert all(isinstance(proc, dict) for proc in prov_proc_info)
        expected_fields = ["id", "title", "version", "description", "keywords", "metadata", "executeEndpoint"]
        assert all([all([field in proc for field in expected_fields]) for proc in prov_proc_info])
        prov_proc_id = [proc["id"] for proc in prov_proc_info]
        assert set(prov_proc_id) == {"pavicstestdocs", "test-remote-process-wps1"}

        # with ignore disabled, regardless of detail flag, error should be raised instead
        # whole listing fails because at least one provider cannot be generated properly
        for detail in [True, False]:
            path = get_path_kvp("/processes", providers=True, detail=detail, ignore=False)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 503, "Parsing error should mark service as unavailable."

    def test_set_jobControlOptions_async_execute(self):
        path = "/processes"
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name)
        process_data["processDescription"]["jobControlOptions"] = [ExecuteControlOption.ASYNC]
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        process = self.process_store.fetch_by_id(process_name)
        assert ExecuteControlOption.ASYNC in process["jobControlOptions"]

    def test_set_jobControlOptions_sync_execute(self):
        path = "/processes"
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name)
        process_data["processDescription"]["jobControlOptions"] = [ExecuteControlOption.SYNC]
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        process = self.process_store.fetch_by_id(process_name)
        assert ExecuteControlOption.SYNC in process["jobControlOptions"]

    def test_get_processes_invalid_schemas_handled(self):
        path = "/processes"
        # deploy valid test process
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        # change value that will trigger schema error on check
        process = self.process_store.fetch_by_id(process_name)
        process["version"] = "random"  # invalid (cannot use any property that executes in-place fixes)
        process["visibility"] = Visibility.PUBLIC
        self.process_store.save_process(process, overwrite=True)

        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 503
        assert resp.content_type == ContentType.APP_JSON
        assert process_name in resp.json.get("description")

    def test_get_processes_html_accept_header(self):
        path = "/processes"
        resp = self.app.get(path, headers=self.html_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_HTML
        assert "</html>" in resp.text
        assert "</body>" in resp.text
        assert "Processes" in resp.text

    def test_get_processes_html_format_query(self):
        path = "/processes"
        resp = self.app.get(path, params={"f": OutputFormat.HTML})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_HTML
        assert "</html>" in resp.text
        assert "</body>" in resp.text
        assert "Processes" in resp.text

    def test_describe_process_html_accept_header(self):
        path = f"/processes/{self.process_public.identifier}"
        resp = self.app.get(path, headers=self.html_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_HTML
        assert "</html>" in resp.text
        assert "</body>" in resp.text
        assert "Process:" in resp.text
        assert self.process_public.identifier in resp.text

    def test_describe_process_html_format_query(self):
        path = f"/processes/{self.process_public.identifier}"
        resp = self.app.get(path, params={"f": OutputFormat.HTML})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_HTML
        assert "</html>" in resp.text
        assert "</body>" in resp.text
        assert "Process:" in resp.text
        assert self.process_public.identifier in resp.text

    def test_get_processes_html_accept_header_user_agent_browser_disabled(self):
        path = "/processes"
        headers = copy.deepcopy(dict(self.html_headers))
        headers["User-Agent"] = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
        resp = self.app.get(path, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_HTML
        assert "</html>" in resp.text
        assert "</body>" in resp.text
        assert "Processes" in resp.text

    def test_get_processes_html_accept_header_user_agent_browser_override(self):
        path = "/processes"
        headers = copy.deepcopy(dict(self.html_headers))
        headers["User-Agent"] = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
        settings = copy.deepcopy(self.config.registry.settings)
        settings["weaver.wps_restapi_html_override_user_agent"] = True
        with mock.patch("weaver.tweens.get_settings", return_value=settings):
            resp = self.app.get(path, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json

    def test_describe_process_visibility_public(self):
        path = f"/processes/{self.process_public.identifier}"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON

    def test_describe_process_visibility_private(self):
        path = f"/processes/{self.process_private.identifier}"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_deploy_process_success(self):
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=False)
            assert resp.status_code == 201
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["processSummary"]["id"] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

    def test_deploy_process_ogc_schema(self):
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name, schema=ProcessSchema.OGC)
        process_desc = process_data["processDescription"]
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            assert "process" not in process_desc
            assert "id" in process_desc
            process_desc["visibility"] = Visibility.PUBLIC  # save ourself an update request
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["processSummary"]["id"] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

    def test_deploy_process_short_name(self):
        process_name = "x"
        process_data = self.get_process_deploy_template(process_name, schema=ProcessSchema.OGC)
        process_data["processDescription"]["visibility"] = Visibility.PUBLIC
        process_data["processDescription"]["outputs"] = {"output": {"schema": {"type": "string"}}}
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=False)
            assert resp.status_code == 201
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["processSummary"]["id"] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

            # perform get to make sure all name checks in the chain, going through db save/load, are validated
            path = f"{path}/{process_name}"
            query = {"schema": ProcessSchema.OLD}
            resp = self.app.get(path, headers=self.json_headers, params=query, expect_errors=False)
            assert resp.status_code == 200
            assert resp.json["process"]["id"] == process_name

    def test_deploy_process_bad_name(self):
        process_name = f"{self.fully_qualified_test_name()}..."
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 400
            assert resp.content_type == ContentType.APP_JSON

    def test_deploy_process_conflict(self):
        process_name = self.process_private.identifier
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 409
            assert resp.content_type == ContentType.APP_JSON

    def test_deploy_process_missing_or_invalid_components(self):
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        # remove components for testing different cases
        process_data_tests = [deepcopy(process_data) for _ in range(13)]
        process_data_tests[0].pop("processDescription")
        process_data_tests[1]["processDescription"].pop("process")
        process_data_tests[2]["processDescription"]["process"].pop("id")  # noqa
        process_data_tests[3]["processDescription"]["jobControlOptions"] = ExecuteControlOption.ASYNC
        process_data_tests[4]["processDescription"]["jobControlOptions"] = [ExecuteMode.ASYNC]  # noqa
        process_data_tests[5]["deploymentProfileName"] = "random"  # can be omitted, but if provided, must be valid
        process_data_tests[6].pop("executionUnit")
        process_data_tests[7]["executionUnit"] = {}
        process_data_tests[8]["executionUnit"] = []
        process_data_tests[9]["executionUnit"][0] = {"unit": "something"}  # unit as string instead of package
        process_data_tests[10]["executionUnit"][0] = {"href": {}}  # noqa  # href as package instead of URL
        process_data_tests[11]["executionUnit"][0] = {"unit": {}, "href": ""}  # can't have both unit/href together
        process_data_tests[12]["executionUnit"][0] = {"href": ""}  # href correct type, but missing link reference

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            for i, data in enumerate(process_data_tests):
                resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation '{}' with value '{}' using data:\n{}"
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code, json.dumps(data, indent=2))
                assert resp.content_type == ContentType.APP_JSON, msg.format(i, resp.content_type, "")

    def test_deploy_process_default_endpoint_wps1(self):
        """
        Validates that the default (localhost) endpoint to execute WPS requests are saved during deployment.
        """
        process_name = self.fully_qualified_test_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201

        weaver_wps_path = get_wps_url(self.config.registry.settings)
        process_wps_endpoint = self.process_store.fetch_by_id(process_name).processEndpointWPS1
        assert isinstance(process_wps_endpoint, str) and len(process_wps_endpoint)
        assert process_wps_endpoint == weaver_wps_path

    @staticmethod
    def assert_deployed_wps3(response_json, expected_process_id, assert_io=True):
        proc = response_json["process"]
        assert expected_process_id in proc["id"]
        if assert_io:
            assert len(proc["inputs"]) == 1
            assert proc["inputs"][0]["id"] == "input-1"
            assert proc["inputs"][0]["minOccurs"] == 1
            assert proc["inputs"][0]["maxOccurs"] == 1
            assert "formats" not in proc["inputs"][0]   # literal data doesn't have "formats"
            assert len(proc["outputs"]) == 1
            assert proc["outputs"][0]["id"] == "output"
            assert "minOccurs" not in proc["outputs"][0]
            assert "maxOccurs" not in proc["outputs"][0]
            # TODO: handling multiple outputs (https://github.com/crim-ca/weaver/issues/25)
            # assert proc["outputs"][0]["minOccurs"] == "1"
            # assert proc["outputs"][0]["maxOccurs"] == "1"
            assert isinstance(proc["outputs"][0]["formats"], list)
            assert len(proc["outputs"][0]["formats"]) == 1
            assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON

    def deploy_process_make_visible_and_fetch_deployed(self,
                                                       deploy_payload,          # type: JSON
                                                       expected_process_id,     # type: str
                                                       headers=None,            # type: Optional[AnyHeadersContainer]
                                                       assert_io=True,          # type: bool
                                                       ):                       # type: (...) -> JSON
        """
        Deploy, make visible and obtain process description.

        Attempts to deploy the process using the provided deployment payload, then makes it visible and finally
        fetches the deployed process to validate the resulting WPS-3 REST JSON description.
        Any failure along the way is raised, ensuring that returned data corresponds to a process ready for execution.

        .. note::
            This is a shortcut method for all ``test_deploy_process_<>`` cases.
        """
        deploy_headers = copy.deepcopy(dict(self.json_headers))
        deploy_headers.update(headers or {})
        resp = mocked_sub_requests(self.app, "post", "/processes",  # mock in case of TestApp self-reference URLs
                                   data=deploy_payload, headers=deploy_headers, only_local=True)
        assert resp.status_code == 201, f"{resp!s}\n{resp.text}"
        assert resp.content_type == ContentType.APP_JSON

        # apply visibility to allow retrieval
        proc_id = resp.json["processSummary"]["id"]  # process id could have been cleaned up
        proc_url = f"/processes/{proc_id}"
        vis_url = f"{proc_url}/visibility"
        body = {"value": Visibility.PUBLIC}
        resp = self.app.put_json(vis_url, params=body, headers=self.json_headers)
        assert resp.status_code == 200

        body = self.get_process_description(proc_id)
        self.assert_deployed_wps3(body, expected_process_id, assert_io=assert_io)
        return body

    def get_process_description(self, process_id, schema=ProcessSchema.OLD):
        # type: (str, ProcessSchema) -> JSON
        proc_query = {"schema": schema}
        proc_url = f"/processes/{process_id}"
        resp = self.app.get(proc_url, params=proc_query, headers=self.json_headers)
        assert resp.status_code == 200
        return resp.json

    def get_application_package(self, process_id):
        # type: (str) -> CWL
        resp = self.app.get(f"/processes/{process_id}/package", headers=self.json_headers)
        assert resp.status_code == 200
        return resp.json

    def validate_wps1_package(
            self,
            process_id,                     # type: str
            provider_url,                   # type: str
            requirement_location="hints",   # type: Literal["hints", "requirements"]
    ):                                      # type: (...) -> None
        cwl = self.get_application_package(process_id)
        assert requirement_location in cwl
        assert any(hint.endswith(CWL_REQUIREMENT_APP_WPS1) for hint in cwl[requirement_location])
        req_hint = (
            cwl[requirement_location].get(CWL_REQUIREMENT_APP_WPS1) or
            cwl[requirement_location].get(f"weaver:{CWL_REQUIREMENT_APP_WPS1}")
        )
        assert "process" in req_hint
        assert "provider" in req_hint
        assert req_hint["process"] == process_id
        if provider_url.endswith("/"):
            valid_urls = [provider_url, provider_url[:-1]]
        else:
            valid_urls = [provider_url, f"{provider_url}/"]
        assert req_hint["provider"] in valid_urls

    def test_deploy_process_CWL_DockerRequirement_auth_header_format(self):
        """
        Test deployment of a process with authentication to access the referenced repository.

        .. note::
            Use same definition as the one provided in :ref:`app_pkg_script` documentation.
        """
        cwl = load_file(os.path.join(WEAVER_ROOT_DIR, "docs/examples/docker-shell-script-cat.cwl"))  # type: CWL
        docker = "fake.repo/org/private-image:latest"
        cwl["requirements"][CWL_REQUIREMENT_APP_DOCKER]["dockerPull"] = docker
        body = self.get_process_deploy_template(cwl=cwl)
        headers = copy.deepcopy(dict(self.json_headers))

        for bad_token in ["0123456789", "Basic:0123456789", "Bearer fake:0123456789"]:  # nosec
            headers.update({"X-Auth-Docker": bad_token})
            resp = self.app.post_json("/processes", params=body, headers=headers, expect_errors=True)
            assert resp.status_code == 422
            assert resp.content_type == ContentType.APP_JSON
            assert "authentication header" in resp.json["description"]

        token = base64.b64encode(b"fake:0123456789").decode("utf-8")  # nosec
        headers.update({"X-Auth-Docker": f"Basic {token}"})  # nosec
        resp = self.app.post_json("/processes", params=body, headers=headers)
        assert resp.status_code == 201
        proc_id = body["processDescription"]["process"]["id"]  # noqa
        process = self.process_store.fetch_by_id(proc_id)
        assert process.auth is not None
        assert process.auth.type == AuthenticationTypes.DOCKER
        assert process.auth.token == token  # noqa
        assert process.auth.docker == docker

    def test_deploy_process_CWL_direct_raised_missing_id(self):
        # normally valid CWL, but not when submitted directly due to missing ID for the process
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3", "-V"],
            "inputs": {},
            "outputs": {
                "output": {
                    "type": "File",
                    "outputBinding": {
                        "glob": "stdout.log"
                    },
                }
            },
        }
        headers = {"Content-Type": ContentType.APP_CWL_JSON, "Accept": ContentType.APP_JSON}
        resp = self.app.post_json("/processes", params=cwl, headers=headers, expect_errors=True)
        assert resp.status_code == 400
        assert "DeployCWL.id" in resp.json["cause"]
        assert "Missing required field." in resp.json["cause"]["DeployCWL.id"]

    def deploy_process_CWL_direct(self,
                                  content_type,                         # type: ContentType
                                  graph_count=0,                        # type: int
                                  process_id="test-direct-cwl-json",    # type: str
                                  version=None,                         # type: Optional[AnyVersion]
                                  ):                                    # type: (...) -> Tuple[CWL, JSON]
        cwl = {}
        cwl_core = self.get_cwl_docker_python_version(cwl_version=None, process_id=process_id)
        cwl_base = {"cwlVersion": "v1.0"}
        cwl.update(cwl_base)
        if version:
            cwl["version"] = version
        if graph_count:
            cwl["$graph"] = [cwl_core] * graph_count
        else:
            cwl.update(cwl_core)
        if "yaml" in content_type:
            cwl = yaml.safe_dump(cwl, sort_keys=False)
        headers = {"Content-Type": content_type}
        desc = self.deploy_process_make_visible_and_fetch_deployed(cwl, process_id, headers=headers, assert_io=False)
        pkg = self.get_application_package(process_id)
        assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"

        # once parsed, CWL I/O are converted to listing form
        # rest should remain intact with the original definition
        expect_cwl = copy.deepcopy(cwl_base)  # type: CWL
        expect_cwl.update(cwl_core)
        expect_cwl["inputs"] = []
        cwl_out = cwl_core["outputs"]["output"]
        cwl_out["id"] = "output"
        expect_cwl["outputs"] = [cwl_out]
        assert pkg == expect_cwl

        # process description should have been generated with relevant I/O
        proc = desc["process"]
        assert proc["id"] == process_id
        assert proc["inputs"] == []
        assert proc["outputs"] == [{
            "id": "output",
            "title": "output",
            "schema": {"type": "string", "contentMediaType": "text/plain"},
            "formats": [{"default": True, "mediaType": "text/plain"}]
        }]
        return cwl, desc  # type: ignore

    def test_deploy_process_CWL_direct_JSON(self):
        self.deploy_process_CWL_direct(ContentType.APP_CWL_JSON)

    def test_deploy_process_CWL_direct_YAML(self):
        self.deploy_process_CWL_direct(ContentType.APP_CWL_YAML)

    def test_deploy_process_CWL_direct_graph_JSON(self):
        self.deploy_process_CWL_direct(ContentType.APP_CWL_JSON, graph_count=1)

    def test_deploy_process_CWL_direct_graph_YAML(self):
        self.deploy_process_CWL_direct(ContentType.APP_CWL_YAML, graph_count=1)

    # FIXME: make xfail once nested CWL definitions implemented (https://github.com/crim-ca/weaver/issues/56)
    def test_deploy_process_CWL_direct_graph_multi_invalid(self):
        with pytest.raises((webtest.app.AppError, AssertionError)) as exc:  # noqa
            self.deploy_process_CWL_direct(ContentType.APP_CWL_JSON, graph_count=2)
        error = str(exc.value)
        assert "400 Bad Request" in error
        assert "Invalid schema" in error
        assert "Longer than maximum length 1" in error

    @staticmethod
    def get_cwl_docker_python_version(cwl_version="v1.0", process_id=None):
        # type: (Optional[str], Optional[str]) -> CWL
        cwl = {}
        if cwl_version:
            cwl["cwlVersion"] = cwl_version
        if process_id:
            cwl["id"] = process_id
        cwl.update({
            "class": "CommandLineTool",
            "requirements": {
                CWL_REQUIREMENT_APP_DOCKER: {
                    "dockerPull": "python:3.7-alpine"
                }
            },
            "baseCommand": ["python3", "-V"],
            "inputs": {},
            "outputs": {
                "output": {
                    "type": "File",
                    "outputBinding": {
                        "glob": "stdout.log"
                    },
                }
            },
        })
        return cwl

    @parameterized.expand([
        ("mapping", ),
        ("listing", ),
    ])
    @pytest.mark.oap_part2
    def test_deploy_process_CWL_DockerRequirement_href(self, exec_unit_style):
        # type: (Literal["mapping", "listing"]) -> None
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            out_dir = self.settings["weaver.wps_output_dir"]
            out_url = self.settings["weaver.wps_output_url"]
            assert out_url.startswith("http"), "test can run only if reference is an HTTP reference"  # sanity check
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory(dir=out_dir))
            tmp_file = os.path.join(tmp_dir, "docker-python.cwl")
            tmp_href = tmp_file.replace(out_dir, out_url, 1)
            cwl = self.get_cwl_docker_python_version()
            with open(tmp_file, mode="w", encoding="utf-8") as cwl_file:
                json.dump(cwl, cwl_file)

            p_id = "test-docker-python-version"
            unit = [{"href": tmp_href}] if exec_unit_style == "listing" else {"href": tmp_href}
            body = {
                "processDescription": {"process": {"id": p_id}},
                "executionUnit": unit,
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            }
            desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
            pkg = self.get_application_package(p_id)
            assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"

            # once parsed, CWL I/O are converted to listing form
            # rest should remain intact with the original definition
            cwl["inputs"] = []
            cwl_out = cwl["outputs"]["output"]
            cwl_out["id"] = "output"
            cwl["outputs"] = [cwl_out]
            assert pkg == cwl

            # process description should have been generated with relevant I/O
            proc = desc["process"]
            assert proc["id"] == p_id
            assert proc["inputs"] == []
            assert proc["outputs"] == [{
                "id": "output",
                "title": "output",
                "schema": {"type": "string", "contentMediaType": "text/plain"},
                "formats": [{"default": True, "mediaType": "text/plain"}]
            }]

    def test_deploy_process_CWL_DockerRequirement_owsContext(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            out_dir = self.settings["weaver.wps_output_dir"]
            out_url = self.settings["weaver.wps_output_url"]
            assert out_url.startswith("http"), "test can run only if reference is an HTTP reference"  # sanity check
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory(dir=out_dir))
            tmp_file = os.path.join(tmp_dir, "docker-python.cwl")
            tmp_href = tmp_file.replace(out_dir, out_url, 1)
            cwl = self.get_cwl_docker_python_version()
            with open(tmp_file, mode="w", encoding="utf-8") as cwl_file:
                json.dump(cwl, cwl_file)

            ows_ctx = ows_context_href(tmp_href)
            p_id = "test-docker-python-version"
            ows_ctx.update({"id": p_id})
            body = {"processDescription": {"process": ows_ctx}}  # optional 'executionUnit' since 'owsContext' has href
            desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
            pkg = self.get_application_package(p_id)
            assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"

            # once parsed, CWL I/O are converted to listing form
            # rest should remain intact with the original definition
            cwl["inputs"] = []
            cwl_out = cwl["outputs"]["output"]
            cwl_out["id"] = "output"
            cwl["outputs"] = [cwl_out]
            assert pkg == cwl

            # process description should have been generated with relevant I/O
            proc = desc["process"]
            assert proc["id"] == p_id
            assert proc["inputs"] == []
            assert proc["outputs"] == [{
                "id": "output",
                "title": "output",
                "schema": {"type": "string", "contentMediaType": "text/plain"},
                "formats": [{"default": True, "mediaType": "text/plain"}]
            }]

    def test_deploy_process_CWL_DockerRequirement_executionUnit(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            cwl = self.get_cwl_docker_python_version()

            p_id = "test-docker-python-version"
            body = {
                "processDescription": {"process": {"id": p_id}},
                "executionUnit": [{"unit": cwl}],
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            }
            desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
            pkg = self.get_application_package(p_id)
            assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"

            # once parsed, CWL I/O are converted to listing form
            # rest should remain intact with the original definition
            cwl["inputs"] = []
            cwl_out = cwl["outputs"]["output"]
            cwl_out["id"] = "output"
            cwl["outputs"] = [cwl_out]
            cwl.pop("$schema", None)
            cwl.pop("$id", None)
            pkg.pop("$schema", None)
            pkg.pop("$id", None)
            assert pkg == cwl

            # process description should have been generated with relevant I/O
            proc = desc["process"]
            assert proc["id"] == p_id
            assert proc["inputs"] == []
            assert proc["outputs"] == [{
                "id": "output",
                "title": "output",
                "schema": {"type": "string", "contentMediaType": "text/plain"},
                "formats": [{"default": True, "mediaType": "text/plain"}]
            }]

    def test_deploy_process_CWL_DockerRequirement_executionUnit_DirectUnit(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            cwl = self.get_cwl_docker_python_version()

            p_id = "test-docker-python-version"
            body = {
                "processDescription": {"process": {"id": p_id}},
                "executionUnit": cwl,
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            }
            desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
            pkg = self.get_application_package(p_id)
            assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"

            # once parsed, CWL I/O are converted to listing form
            # rest should remain intact with the original definition
            cwl["inputs"] = []
            cwl_out = cwl["outputs"]["output"]
            cwl_out["id"] = "output"
            cwl["outputs"] = [cwl_out]
            cwl.pop("$schema", None)
            cwl.pop("$id", None)
            pkg.pop("$schema", None)
            pkg.pop("$id", None)
            assert pkg == cwl

            # process description should have been generated with relevant I/O
            proc = desc["process"]
            assert proc["id"] == p_id
            assert proc["inputs"] == []
            assert proc["outputs"] == [{
                "id": "output",
                "title": "output",
                "schema": {"type": "string", "contentMediaType": "text/plain"},
                "formats": [{"default": True, "mediaType": "text/plain"}]
            }]

    def test_deploy_process_CWL_DockerRequirement_executionUnit_UnitWithMediaType(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            cwl = self.get_cwl_docker_python_version()

            p_id = "test-docker-python-version"
            body = {
                "processDescription": {"process": {"id": p_id}},
                "executionUnit": {"unit": cwl, "type": ContentType.APP_CWL_JSON},
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            }
            desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
            pkg = self.get_application_package(p_id)
            assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"

            # once parsed, CWL I/O are converted to listing form
            # rest should remain intact with the original definition
            cwl["inputs"] = []
            cwl_out = cwl["outputs"]["output"]
            cwl_out["id"] = "output"
            cwl["outputs"] = [cwl_out]
            cwl.pop("$schema", None)
            cwl.pop("$id", None)
            pkg.pop("$schema", None)
            pkg.pop("$id", None)
            assert pkg == cwl

            # process description should have been generated with relevant I/O
            proc = desc["process"]
            assert proc["id"] == p_id
            assert proc["inputs"] == []
            assert proc["outputs"] == [{
                "id": "output",
                "title": "output",
                "schema": {"type": "string", "contentMediaType": "text/plain"},
                "formats": [{"default": True, "mediaType": "text/plain"}]
            }]

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_CUDA_NAME], indirect=True)
    def test_deploy_process_CWL_CudaRequirement_executionUnit(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            cuda_requirements = {
                "cudaVersionMin": "11.4",
                "cudaComputeCapability": "3.0",
                "cudaDeviceCountMin": 1,
                "cudaDeviceCountMax": 8
            }
            docker_requirement = {"dockerPull": "python:3.7-alpine"}
            cwl = {
                "class": "CommandLineTool",
                "cwlVersion": "v1.2",
                "hints": {
                    "cwltool:CUDARequirement": cuda_requirements,
                    "DockerRequirement": docker_requirement
                },
                "$namespaces": {
                    "cwltool": "http://commonwl.org/cwltool#"
                },
                "inputs": {},
                "outputs": {
                    "output": {
                        "type": "File",
                        "outputBinding": {
                            "glob": "stdout.log"
                        },
                    }
                }
            }

            p_id = "test-cuda"
            body = {
                "processDescription": {"process": {"id": p_id}},
                "executionUnit": [{"unit": cwl}],
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            }
            desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
            pkg = self.get_application_package(p_id)
            assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"
            assert desc["process"]["id"] == p_id
            assert pkg["hints"]["cwltool:CUDARequirement"] == cuda_requirements
            assert pkg["hints"]["DockerRequirement"] == docker_requirement

    def test_deploy_process_CWL_NetworkRequirement_executionUnit(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            network_access_requirement = {"networkAccess": True}
            docker_requirement = {"dockerPull": "python:3.7-alpine"}
            for req_type in ["hints", "requirements"]:  # type: Literal["hints", "requirements"]
                cwl = {
                    "class": "CommandLineTool",
                    "cwlVersion": "v1.2",
                    req_type: {
                        "NetworkAccess": network_access_requirement,
                        "DockerRequirement": docker_requirement
                    },
                    "inputs": {},
                    "outputs": {
                        "output": {
                            "type": "File",
                            "outputBinding": {
                                "glob": "stdout.log"
                            },
                        }
                    }
                }

                p_id = f"test-network-access-{req_type}"
                body = {
                    "processDescription": {"process": {"id": p_id}},
                    "executionUnit": [{"unit": cwl}],
                    "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
                }
                desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
                pkg = self.get_application_package(p_id)
                assert desc["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/dockerizedApplication"
                assert desc["process"]["id"] == p_id
                assert pkg[req_type]["NetworkAccess"] == network_access_requirement
                assert pkg[req_type]["DockerRequirement"] == docker_requirement

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_executionUnit_requirements(self):
        """
        Ensures that :term:`CWL` ``requirements`` directly resolves with a namespaced ``weaver`` requirement schema.
        """
        ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
        ns.update({CWL_NAMESPACE_WEAVER_ID: CWL_NAMESPACE_WEAVER_URL})
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            # note: this is the main difference from other 'hints' cases
            "requirements": {
                f"{CWL_NAMESPACE_WEAVER_ID}:{CWL_REQUIREMENT_APP_WPS1}": {
                    "process": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                    "provider": resources.TEST_REMOTE_SERVER_URL
                }
            },
            # FIXME: must provide inputs/outputs since CWL provided explicitly.
            #   Update from CWL->WPS complementary details is supported.
            #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
            # following are based on expected results for I/O defined in XML
            "inputs": {
                "input-1": {
                    "type": "string"
                },
            },
            "outputs": {
                "output": {
                    "type": "File",
                    "format": fmt,
                    "outputBinding": {
                        "glob": "*.json"
                    },
                }
            },
            "$namespaces": ns
        }
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}},
            "executionUnit": [{"unit": cwl}],
            # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
            resources.TEST_REMOTE_SERVER_URL,
            requirement_location="requirements",
        )

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_href(self):
        ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "hints": {
                CWL_REQUIREMENT_APP_WPS1: {
                    "process": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                    "provider": resources.TEST_REMOTE_SERVER_URL
                }
            },
            # FIXME: must provide inputs/outputs since CWL provided explicitly.
            #   Update from CWL->WPS complementary details is supported.
            #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
            # following are based on expected results for I/O defined in XML
            "inputs": {
                "input-1": {
                    "type": "string"
                },
            },
            "outputs": {
                "output": {
                    "type": "File",
                    "format": fmt,
                    "outputBinding": {
                        "glob": "*.json"
                    },
                }
            },
            "$namespaces": ns
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            out_dir = self.settings["weaver.wps_output_dir"]
            out_url = self.settings["weaver.wps_output_url"]
            assert out_url.startswith("http"), "test can run only if reference is an HTTP reference"  # sanity check
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory(dir=out_dir))
            tmp_file = os.path.join(tmp_dir, "wps1.cwl")
            tmp_href = tmp_file.replace(out_dir, out_url, 1)
            with open(tmp_file, mode="w", encoding="utf-8") as cwl_file:
                json.dump(cwl, cwl_file)

            body = {
                "processDescription": {"process": {"id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}},
                "executionUnit": [{"href": tmp_href}],
                # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            }
            self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)
            self.validate_wps1_package(
                resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                resources.TEST_REMOTE_SERVER_URL
            )

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_owsContext(self):
        ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "hints": {
                CWL_REQUIREMENT_APP_WPS1: {
                    "process": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                    "provider": resources.TEST_REMOTE_SERVER_URL
                }
            },
            # FIXME: must provide inputs/outputs since CWL provided explicitly.
            #   Update from CWL->WPS complementary details is supported.
            #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
            # following are based on expected results for I/O defined in XML
            "inputs": {
                "input-1": {
                    "type": "string"
                },
            },
            "outputs": {
                "output": {
                    "type": "File",
                    "format": fmt,
                    "outputBinding": {
                        "glob": "*.json"
                    },
                }
            },
            "$namespaces": ns
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            wps_dir = self.settings["weaver.wps_output_dir"]
            wps_url = self.settings["weaver.wps_output_url"]
            assert wps_url.startswith("http"), "test can run only if reference is an HTTP reference"  # sanity check
            tmp_file = stack.enter_context(tempfile.NamedTemporaryFile(dir=wps_dir, mode="w", suffix=".cwl"))
            tmp_http = tmp_file.name.replace(wps_dir, wps_url, 1)
            json.dump(cwl, tmp_file)
            tmp_file.flush()
            tmp_file.seek(0)

            body = {
                "processDescription": {"process": {
                    "id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                }},
                "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}],  # just to fulfill schema validation
                # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            }
            ows_ctx = ows_context_href(tmp_http)
            body["processDescription"]["process"].update(ows_ctx)
            self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)
            self.validate_wps1_package(
                resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                resources.TEST_REMOTE_SERVER_URL
            )

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_executionUnit(self):
        ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "hints": {
                CWL_REQUIREMENT_APP_WPS1: {
                    "process": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
                    "provider": resources.TEST_REMOTE_SERVER_URL
                }
            },
            # FIXME: must provide inputs/outputs since CWL provided explicitly.
            #   Update from CWL->WPS complementary details is supported.
            #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
            # following are based on expected results for I/O defined in XML
            "inputs": {
                "input-1": {
                    "type": "string"
                },
            },
            "outputs": {
                "output": {
                    "type": "File",
                    "format": fmt,
                    "outputBinding": {
                        "glob": "*.json"
                    },
                }
            },
            "$namespaces": ns
        }
        body = {
            "processDescription": {"process": {
                "id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
            }},
            "executionUnit": [{"unit": cwl}],
            # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
            resources.TEST_REMOTE_SERVER_URL
        )

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_WPS1_DescribeProcess_href(self):
        body = {
            "processDescription": {
                "href": resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_URL  # this one should be used
            },
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
            resources.TEST_REMOTE_SERVER_URL
        )

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_WPS1_DescribeProcess_owsContext(self):
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        desc_url = ows_context_href(resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_URL)
        body["processDescription"]["process"].update(desc_url)
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_WPS1_DescribeProcess_executionUnit(self):
        """
        Test process deployment using a WPS-1 DescribeProcess URL specified as an execution unit reference.
        """
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,
            resources.TEST_REMOTE_SERVER_URL
        )

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_WPS1_GetCapabilities_href(self):
        """
        Test process deployment using a WPS-1 GetCapabilities URL specified as process description reference.
        """
        body = {
            "processDescription": {
                "id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID,    # must tell which process from GetCapabilities
                "href": resources.TEST_REMOTE_SERVER_WPS1_GETCAP_URL,  # this one should be used
            },
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_WPS1_GetCapabilities_owsContext(self):
        """
        Test process deployment using a WPS-1 GetCapabilities URL specified through the OwsContext definition.
        """
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(resources.TEST_REMOTE_SERVER_WPS1_GETCAP_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_WPS1], indirect=True)
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_deploy_process_WPS1_GetCapabilities_executionUnit(self):
        """
        Test process deployment using a WPS-1 GetCapabilities URL specified through the ExecutionUnit parameter.
        """
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_WPS1_GETCAP_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID)

    def validate_ogcapi_process_description(
            self,
            process_description,            # type: JSON
            process_id,                     # type: str
            remote_process,                 # type: str
            requirement_location="hints",   # type: Literal["hints", "requirements"]
    ):                                      # type: (...) -> None
        assert process_id != remote_process
        assert process_description["deploymentProfile"] == "http://www.opengis.net/profiles/eoc/ogcapiApplication"

        # process description should have been generated with relevant I/O
        proc = process_description["process"]
        ref_desc = self.get_process_description(remote_process)
        ref_proc = ref_desc["process"]
        ref_url = ref_proc["processDescriptionURL"]
        assert proc["id"] == process_id
        assert proc["inputs"] == ref_proc["inputs"]
        assert proc["outputs"] == ref_proc["outputs"]

        # package should have been generated with corresponding I/O from "remote process"
        ref = self.get_application_package(remote_process)
        pkg = self.get_application_package(process_id)
        assert pkg[requirement_location] == {
            f"{CWL_NAMESPACE_WEAVER_ID}:{CWL_REQUIREMENT_APP_OGC_API}": {
                "process": ref_url
            }
        }
        for io_select in ["input", "output"]:
            io_section = f"{io_select}s"
            for io_pkg, io_ref in zip(pkg[io_section], ref[io_section]):
                assert io_pkg["id"] == io_ref["id"]
                assert io_pkg["format"] == io_ref["format"]

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_OGC_API], indirect=True)
    def test_deploy_process_OGC_API_DescribeProcess_href(self):
        """
        Use the basic :term:`Process` URL format for referencing remote OGC API definition.

        This will be helpful to support `Part 3 - Workflow` nested definitions.

        .. note::
            This does not support nested OGC Workflows by itself.
            Only sets up the required parsing of the body to eventually deploy them.

        .. seealso::
            - https://github.com/opengeospatial/ogcapi-processes/issues/279
            - https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/workflows
            - https://github.com/crim-ca/weaver/issues/412
        """
        register_builtin_processes(self.app.app.registry)  # must register since collection reset in 'setUp'
        remote_process = "jsonarray2netcdf"  # use builtin, re-deploy as "remote process"
        href = f"{self.url}/processes/{remote_process}"
        p_id = "new-test-ogc-api"
        body = {
            "id": p_id,  # normally optional, but since an existing process is re-deployed, conflict ID is raised
            "process": href
        }
        desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
        self.validate_ogcapi_process_description(desc, p_id, remote_process)

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_OGC_API], indirect=True)
    def test_deploy_process_OGC_API_DescribeProcess_owsContext(self):
        register_builtin_processes(self.app.app.registry)  # must register since collection reset in 'setUp'
        remote_process = "jsonarray2netcdf"  # use builtin, re-deploy as "remote process"
        href = f"{self.url}/processes/{remote_process}"
        p_id = "new-test-ogc-api"
        ows_ctx = ows_context_href(href)
        ows_ctx.update({"id": p_id})
        body = {
            "processDescription": {"process": ows_ctx}
        }
        desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
        self.validate_ogcapi_process_description(desc, p_id, remote_process)

    @pytest.mark.usefixtures("assert_cwl_no_warn_unknown_hint")
    @pytest.mark.parametrize("assert_cwl_no_warn_unknown_hint", [CWL_REQUIREMENT_APP_OGC_API], indirect=True)
    def test_deploy_process_OGC_API_DescribeProcess_executionUnit(self):
        register_builtin_processes(self.app.app.registry)  # must register since collection reset in 'setUp'
        remote_process = "jsonarray2netcdf"  # use builtin, re-deploy as "remote process"
        href = f"{self.url}/processes/{remote_process}"
        p_id = "new-test-ogc-api"
        body = {
            "processDescription": {"process": {"id": p_id}},
            "executionUnit": [{"href": href}],
        }
        desc = self.deploy_process_make_visible_and_fetch_deployed(body, p_id, assert_io=False)
        self.validate_ogcapi_process_description(desc, p_id, remote_process)

    def test_deploy_process_with_revision_invalid(self):
        """
        Ensure that new deployment directly using a ``{processID}:{version}`` reference is not allowed.

        This nomenclature is reserved for revisions accomplished with PUT or PATCH requests with controlled versioning.

        .. versionadded:: 4.20
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3", "-V"],
            "inputs": {},
            "outputs": {
                "output": {
                    "type": "File",
                    "outputBinding": {
                        "glob": "stdout.log"
                    },
                }
            },
        }

        headers = {"Content-Type": ContentType.APP_CWL_JSON, "Accept": ContentType.APP_JSON}
        data = copy.deepcopy(cwl)
        data["id"] = "invalid-process:1.2.3"
        resp = self.app.post_json("/processes", params=cwl, headers=headers, expect_errors=True)
        assert resp.status_code in [400, 422]
        assert "Invalid" in resp.json["error"]

        data = {
            "processDescription": {"process": {"id": "invalid-process:1.2.3"}},
            "executionUnit": [{"unit": cwl}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
        }
        resp = self.app.post_json("/processes", params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code in [400, 422]
        assert "Invalid" in resp.json["error"]

    def test_update_process_not_found(self):
        resp = self.app.patch_json("/processes/not-found", params={}, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404

    def test_update_process_no_data(self):
        """
        Error expected if no data is provided for an update request.

        .. versionadded:: 4.20
        """
        p_id = "test-update-no-data"
        self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=p_id)
        resp = self.app.patch_json(f"/processes/{p_id}", params={}, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["title"] == "Failed process parameter update."

        data = {"description": None, "title": None}
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["title"] == "Failed process parameter update."

        data = {"unknown-field": "new content"}
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["title"] == "Failed process parameter update."

    def test_update_process_latest_valid(self):
        """
        Update the current process revision with new metadata (making it an older revision and new one becomes latest).

        Change should be marked as PATCH revision.

        .. versionadded:: 4.20
        """
        p_id = "test-update-cwl-json"
        _, desc = self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=p_id)
        assert desc["process"]["version"] is None, "No version provided should be reported as such."
        data = {
            "description": "New description",
            "title": "Another title",
        }
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processSummary"]["title"] == data["title"]
        assert body["processSummary"]["description"] == data["description"]

        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["title"] == data["title"]
        assert body["description"] == data["description"]
        assert body["version"] == "0.0.1", (
            "PATCH revision expected. Since previous did not have a version, "
            "it should be assumed 0.0.0, making this revision 0.0.1."
        )

    def test_update_process_older_valid(self):
        """
        Update an older process (already a previous revision) with new metadata.

        The older and updated process references must then be adjusted to ensure that fetching by process name only
        returns the new latest definition, while specific process tag returns the expected revision.

        .. versionadded:: 4.20
        """
        p_id = "test-update-cwl-json"
        version = "1.2.3"
        self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=p_id, version=version)
        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["version"] == version
        assert "description" not in resp.json

        data = {
            "description": "New description",
            "title": "Another title",
        }
        resp = self.app.patch_json(f"/processes/{p_id}:{version}", params=data, headers=self.json_headers)
        assert resp.status_code == 200

        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == "1.2.4", "Patch update expected"
        assert body["title"] == data["title"]
        assert body["description"] == data["description"]

        data = {
            "title": "Another change with version",
            "version": "1.2.7",  # doesn't have to be the one right after latest (as long as greater than 1.2.4)
        }
        resp = self.app.patch_json(f"/processes/{p_id}:{version}", params=data, headers=self.json_headers)
        assert resp.status_code == 200

        # check that previous 'latest' can be fetched by specific version
        resp = self.app.get(f"/processes/{p_id}:{version}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["id"] == f"{p_id}:{version}"
        assert body["version"] == version
        assert "description" not in body

        # check final result with both explicit '1.2.7' version and new 'latest'
        for p_ref in [p_id, f"{p_id}:1.2.7"]:
            resp = self.app.get(f"/processes/{p_ref}", headers=self.json_headers)
            assert resp.status_code == 200
            body = resp.json
            assert body["version"] == data["version"], "Specific version update expected"
            assert body["title"] == data["title"]
            assert "description" not in body, (
                "Not modified since no new value, value from reference process must be used. "
                "Must not make use of the intermediate '1.2.4' version, since '1.2.3' explicitly requested for update."
            )

    def test_update_process_auto_revision(self):
        """
        When updating a process, if not version is explicitly provided, the next one is automatically applied.

        Next version depends on the level of changes implied. Proper semantic level should be bumped using corresponding
        information that gets updated.
        """
        p_id = "test-process-auto-revision"
        cwl, _ = self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=p_id, version="1.0")

        data = {"title": "new title"}
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processSummary"]["title"] == data["title"]
        assert body["processSummary"]["version"] == "1.0.1", "only metadata updated, PATCH auto-revision expected"

        old_title = data["title"]
        data = {"description": "modify description"}
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processSummary"]["title"] == old_title
        assert body["processSummary"]["version"] == "1.0.2", "only metadata updated, PATCH auto-revision expected"
        assert body["processSummary"]["description"] == data["description"]
        assert body["processSummary"]["jobControlOptions"] == [ExecuteControlOption.ASYNC]  # default, validate for next

        old_desc = data["description"]
        data = {"jobControlOptions": ExecuteControlOption.values(), "title": "any exec control"}
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processSummary"]["title"] == data["title"]
        assert body["processSummary"]["version"] == "1.1.0", "MINOR revision expected for change that affects execute"
        assert body["processSummary"]["description"] == old_desc
        assert body["processSummary"]["jobControlOptions"] == data["jobControlOptions"]

        old_title = data["title"]
        old_jco = data["jobControlOptions"]
        data = {"outputs": {"output": {"title": "the output"}}}
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processSummary"]["title"] == old_title
        assert body["processSummary"]["version"] == "1.1.1", "only metadata updated, PATCH auto-revision expected"
        assert body["processSummary"]["description"] == old_desc
        assert body["processSummary"]["jobControlOptions"] == old_jco
        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["outputs"]["output"]["title"] == data["outputs"]["output"]["title"]

        cwl["inputs"] = {"message": {"type": "string"}}
        cwl.pop("version", None)  # make sure none specified, let MAJOR auto-revision with latest
        data = {
            "processDescription": {"process": {"id": p_id, "visibility": Visibility.PUBLIC}},
            "executionUnit": [{"unit": cwl}]
        }
        resp = self.app.put_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 201
        body = resp.json
        assert "title" not in body["processSummary"]  # everything resets because PUT replaces, not updated like PATCH
        assert "description" not in body["processSummary"]
        assert body["processSummary"]["version"] == "2.0.0", "full process updated, MAJOR auto-revision expected"
        assert body["processSummary"]["jobControlOptions"] == ExecuteControlOption.values()
        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "message" in body["inputs"]
        assert "description" not in body["outputs"]["output"]
        assert body["outputs"]["output"]["title"] == "output", "default title generated from ID since none provided"

        data = {  # validate mixed format use and distinct PATCH/MINOR level changes
            "title": "mixed format",
            "outputs": [{"id": "output", "title": "updated output title", "description": "new description added"}],
            "inputs": {"message": {"description": "message input"}},
        }
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processSummary"]["title"] == data["title"]
        assert body["processSummary"]["version"] == "2.0.1", "only metadata updated, PATCH auto-revision expected"
        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == "2.0.1", "only metadata updated, PATCH auto-revision expected"
        assert body["inputs"]["message"]["description"] == data["inputs"]["message"]["description"]
        assert body["outputs"]["output"]["title"] == data["outputs"][0]["title"]
        assert body["outputs"]["output"]["description"] == data["outputs"][0]["description"]

    def test_update_process_jobs_adjusted(self):
        """
        Validate that given a valid process update, associated jobs update their references to preserve links.

        If links were not updated with the new tagged revision, older jobs would refer to the updated (latest) process,
        which might not make sense according to the level of modifications applied for this process.

        .. versionadded:: 4.20
        """
        p_id = "test-update-job-refs"
        self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=p_id)
        job = self.job_store.save_job(task_id=uuid.uuid4(), process=p_id, access=Visibility.PUBLIC)

        # verify that job initially refers to "latest" process
        path = f"/jobs/{job.id}"
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert "processID" in body and body["processID"] == p_id
        path = get_path_kvp(f"/processes/{p_id}/jobs", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert len(body["jobs"]) == 1 and str(job.id) in body["jobs"]

        # update process
        data = {
            "description": "New description",
            "title": "Another title",
        }
        resp = self.app.patch_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "version" in body["processSummary"] and body["processSummary"]["version"] not in [None, "0.0.0"]

        # verify job was updated with new reference
        path = f"/jobs/{job.id}"
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert "processID" in body and body["processID"] == f"{p_id}:0.0.0"

        path = get_path_kvp(f"/processes/{p_id}/jobs", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert len(body["jobs"]) == 0
        path = get_path_kvp(f"/processes/{p_id}:0.0.0/jobs", detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert len(body["jobs"]) == 1 and str(job.id) in body["jobs"]

    def test_replace_process_valid(self):
        """
        Redeploy a process by replacing its definition (MAJOR revision update).

        Validate both different deploy formats (CWL, OAS, OGC) and different resolution methods of target version based
        auto-resolved latest process when omitted or using an explicit version specification in the payload.

        .. versionadded:: 4.20
        """
        # first deploy uses direct CWL, following update uses OGC-AppPackage schema, and last used OpenAPI schema
        # validate that distinct deployment schema does not pose a problem to parse update contents
        p_id = "test-replace-cwl"
        v1 = "1.2.3"
        cwl_v1, desc_v1 = self.deploy_process_CWL_direct(ContentType.APP_JSON, process_id=p_id, version=v1)
        assert desc_v1["process"]["version"] == v1
        assert desc_v1["process"]["inputs"] == []

        cwl_v2 = copy.deepcopy(cwl_v1)
        cwl_v2.pop("id", None)  # ensure no reference
        cwl_v2.pop("version", None)  # avoid conflict
        cwl_v2["inputs"]["test"] = {"type": "string"}  # type: ignore
        data = {
            "processDescription": {"process": {
                # must include ID in deploy payload for counter validation against updated process
                # (error otherwise since reusing same Deploy schema that requires it)
                "id": p_id,
                # make public to allow retrieving the process
                # since we "override" the revision with PUT, omitting this would make the new version private
                "visibility": Visibility.PUBLIC,
                # new information to apply, validate that it is also considered, not just the package redefinition
                "title": "Updated CWL"
            }},
            "executionUnit": [{"unit": cwl_v2}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
        }
        v2 = "2.0.0"  # not explicitly provided, expected resolved MAJOR update for revision
        resp = self.app.put_json(f"/processes/{p_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 201
        body = resp.json
        assert body["processSummary"]["title"] == data["processDescription"]["process"]["title"], (
            "Even though MAJOR update for CWL is accomplished, other fields that usually correspond to MINOR changes "
            "should also be applied at the same time since the operation replaces the new process definition (PUT)."
        )
        assert (
            "description" not in body["processSummary"] or  # if undefined, dropped from body
            body["processSummary"]["description"] != desc_v1["description"]  # just in case, check otherwise
        ), (
            "Description should not have remained from previous version since this is a replacement (PUT),"
            "not a revision update (PATCH)."
        )

        path = get_path_kvp(f"/processes/{p_id}:{v1}", schema=ProcessSchema.OGC)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "title" not in body, "should be missing as in original definition"
        assert "description" not in body, "should be missing as in original definition"
        assert body["version"] == v1
        assert body["inputs"] == {}, "empty mapping due to OGC schema, no input as in original definition"

        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["title"] == data["processDescription"]["process"]["title"]
        assert "description" not in body
        assert body["version"] == v2, f"Since no version was specified, next MAJOR version after {v1} was expected."
        assert len(body["inputs"]) == 1 and "test" in body["inputs"]

        # redeploy with explicit version
        cwl_v3 = copy.deepcopy(cwl_v2)
        cwl_v3.pop("version", None)  # avoid conflict
        # need to provide basic input definition in CWL to avoid dropping it when checked against payload definitions
        # add extra literal data domain information in OAS structure
        cwl_v3["inputs"]["number"] = {"type": "int"}  # type: ignore
        v3 = "4.3.2"  # does not necessarily need to be the next one
        data = {
            "processDescription": {
                "id": p_id,  # required to fulfill schema validation, must omit 'version' part and match request path ID
                "version": "4.3.2",  # explicitly provided to avoid auto-bump to '3.0.0'
                # use OAS representation in this case to validate it is still valid using update request
                "inputs": {"number": {"schema": {"type": "integer", "minimum": 1, "maximum": 3}}},
                "visibility": Visibility.PUBLIC,  # ensure we can retrieve the description later
            },
            "executionUnit": [{"unit": cwl_v3}],
        }
        # don't need to refer to "latest" process since we provide an explicit version that is available
        resp = self.app.put_json(f"/processes/{p_id}:{v1}", params=data, headers=self.json_headers)
        assert resp.status_code == 201

        # check all versions are properly resolved
        resp = self.app.get(f"/processes/{p_id}:{v1}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == v1
        assert body["id"] == f"{p_id}:{v1}"
        resp = self.app.get(f"/processes/{p_id}:{v2}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == v2
        assert body["id"] == f"{p_id}:{v2}"
        resp = self.app.get(f"/processes/{p_id}:{v3}", headers=self.json_headers)  # explicitly the latest by version
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == v3
        assert body["id"] == p_id
        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)  # latest implicitly
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == v3
        assert body["id"] == p_id

    def test_delete_process_revision(self):
        """
        Process revisions can be deleted (undeployed) just like any other process.

        In the event that the revision to delete happens to be the active latest, the next one by semantic version
        should become the new latest revision.

        .. versionadded:: 4.20
        """
        p_id = "test-delete-process-revision"
        versions = self.deploy_process_revisions(p_id)

        # delete a process revision
        del_ver = versions[3]  # pick any not latest
        path = f"/processes/{p_id}:{del_ver}"
        resp = self.app.delete_json(path, headers=self.json_headers)
        assert resp.status_code == 200

        # check that revision was properly removed
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        path = get_path_kvp("/processes", detail=False, revisions=True, process=p_id)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["processes"] == [f"{p_id}:{ver}" for ver in versions if ver != del_ver]

        # check that latest version was not affected since it wasn't the latest that was deleted
        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == versions[-1]

        # delete latest to valide it gets updated with the version before it
        latest_ver = versions[-1]
        path = f"/processes/{p_id}:{latest_ver}"
        resp = self.app.delete_json(path, headers=self.json_headers)
        assert resp.status_code == 200

        resp = self.app.get(f"/processes/{p_id}", headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert body["version"] == versions[-2], "new latest should be the version before the previously removed latest"

    def test_delete_process_success(self):
        path = f"/processes/{self.process_public.identifier}"
        resp = self.app.delete_json(path, headers=self.json_headers)
        assert resp.status_code == 200, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["identifier"] == self.process_public.identifier
        assert isinstance(resp.json["undeploymentDone"], bool) and resp.json["undeploymentDone"]
        with pytest.raises(ProcessNotFound):
            self.process_store.fetch_by_id(self.process_public.identifier)

    def test_delete_process_not_accessible(self):
        path = f"/processes/{self.process_private.identifier}"
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON

    def test_delete_process_not_found(self):
        name = self.fully_qualified_test_name()
        path = f"/processes/{name}"
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON

    def test_delete_process_bad_name(self):
        name = f"{self.fully_qualified_test_name()}..."
        path = f"/processes/{name}"
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON

    def test_execute_process_success(self):
        path = f"/processes/{self.process_public.identifier}/jobs"
        data = self.get_process_execute_template()
        task = f"job-{fully_qualified_name(self)}"
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            resp = self.app.post_json(path, params=data, headers=self.json_headers)
            assert resp.status_code == 201, f"Error: {resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["location"].endswith(resp.json["jobID"])
            assert resp.headers["Location"] == resp.json["location"]
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert str(job.id) == resp.json["jobID"]
            assert job.task_id == Status.ACCEPTED  # temporary value until processed by celery

    def test_execute_process_language(self):
        path = f"/processes/{self.process_public.identifier}/jobs"
        data = self.get_process_execute_template()
        task = f"job-{fully_qualified_name(self)}"
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            headers = self.json_headers.copy()
            headers["Accept-Language"] = AcceptLanguage.FR_CA
            resp = self.app.post_json(path, params=data, headers=headers)
            assert resp.status_code == 201, f"Error: {resp.text}"
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert str(job.id) == resp.json["jobID"]
            assert job.accept_language == AcceptLanguage.FR_CA

    def test_execute_process_no_json_body(self):
        path = f"/processes/{self.process_public.identifier}/jobs"
        resp = self.app.post_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == ContentType.APP_JSON

    def test_execute_process_valid_empty_string(self):
        """
        Ensure that a process expecting an input string parameter can be provided as empty (not resolved as "missing").
        """
        path = f"/processes/{self.process_public.identifier}/jobs"
        data = self.get_process_execute_template(test_input="")

        with contextlib.ExitStack() as stack:
            for exe in mocked_process_job_runner():
                stack.enter_context(exe)
            resp = self.app.post_json(path, params=data, headers=self.json_headers)
            assert resp.status_code == 201, "Expected job submission without inputs created without error."
            job = self.job_store.fetch_by_id(resp.json["jobID"])
            assert job.inputs[0]["data"] == "", "Input value should be an empty string."

    def test_execute_process_missing_required_params(self):
        """
        Validate execution against missing parameters.

        .. versionchanged:: 4.15
            Multiple parameters are not **required** anymore because the alternative with ``Prefer`` header
            for :term:`OGC API - Processes` compliance is permitted. When the values are specified through,
            they should still be validated to provide relevant error details to the user.
        """
        execute_data = self.get_process_execute_template(fully_qualified_name(self))

        # remove components for testing different cases
        execute_data_tests = [[True, deepcopy(execute_data)] for _ in range(7)]
        execute_data_tests[0][0] = False
        execute_data_tests[0][1].pop("outputs")
        execute_data_tests[1][0] = False
        execute_data_tests[1][1].pop("mode")
        execute_data_tests[2][0] = False
        execute_data_tests[2][1].pop("response")
        execute_data_tests[3][1]["mode"] = "random"
        execute_data_tests[4][1]["response"] = "random"
        execute_data_tests[5][1]["inputs"] = [{"test_input": "test_value"}]  # noqa  # bad format on purpose
        execute_data_tests[6][1]["outputs"] = [{"id": "test_output", "transmissionMode": "random"}]

        def no_op(*_, **__):
            return Status.SUCCESSFUL

        path = f"/processes/{self.process_public.identifier}/jobs"
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery(func_execute_task=no_op):
                stack_exec.enter_context(mock_exec)
            for i, (is_invalid, exec_data) in enumerate(execute_data_tests):
                data_json = json.dumps(exec_data, indent=2)
                try:
                    # timeout to kill execution if schema validation did not raise
                    with stopit.ThreadingTimeout(3) as timeout:
                        resp = self.app.post_json(path, params=exec_data, headers=self.json_headers, expect_errors=True)
                        msg = "Failed with test variation '{}' with status '{}' using:\n{}"
                        code = [400, 422] if is_invalid else [201]
                        assert resp.status_code in code, msg.format(i, resp.status_code, data_json)
                        assert resp.content_type == ContentType.APP_JSON, msg.format(i, resp.content_type)
                except stopit.TimeoutException:
                    # if required, not normal to have passed validation
                    # if optional, valid since omitting field does not raise missing field in schema
                    if is_invalid:
                        msg = f"Killed test '{i}' request taking too long using:\n{data_json}"
                        assert timeout.state == timeout.EXECUTED, msg  # pylint: disable=E0601

    def test_execute_process_dont_cast_one_of(self):
        """
        When validating the schema for OneOf values, don't cast the result to the first valid schema.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)
        execute_mock_data_tests = []

        mock_execute = mocked_process_job_runner(f"job-{name}")
        data_execute = self.get_process_execute_template("100")
        execute_mock_data_tests.append((mock_execute, data_execute))

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            path = f"/processes/{self.process_public.identifier}/jobs"
            resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
            assert resp.status_code == 201, "Expected job submission without inputs created without error."
            job = self.job_store.fetch_by_id(resp.json["jobID"])
            assert job.inputs[0]["data"] == "100", "Input value should remain string and not be cast to float/integer"

    def test_execute_process_no_error_not_required_params(self):
        """
        Test that optional parameters not provided during execute request do not fail.

        Optional parameters for execute job shouldn't raise an error if omitted, and should resolve to default
        values if any was explicitly specified during deployment, or inferred from it.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)

        # define a process without inputs
        process_no_inputs = WpsTestProcess(identifier="process_no_inputs", inputs=[])
        self.process_store.save_process(process_no_inputs)
        self.process_store.set_visibility(process_no_inputs.identifier, Visibility.PUBLIC)
        execute_no_inputs = self.get_process_execute_template()
        execute_no_inputs.pop("inputs")

        # define a process with default input
        default_inputs = [
            LiteralInput("test_input", "Input Required", data_type="string"),
            LiteralInput("other_input", "Input Optional", data_type="string", default="omitted", min_occurs=0)
        ]
        process_default_input = WpsTestProcess(identifier="process_default_input", inputs=default_inputs)
        self.process_store.save_process(process_default_input)
        self.process_store.set_visibility(process_default_input.identifier, Visibility.PUBLIC)
        execute_default_input = self.get_process_execute_template("input-required")  # other input omitted
        assert len(execute_default_input["inputs"]) == 1
        assert not any("input_default" in input_exec for input_exec in execute_default_input["inputs"])

        execute_no_outputs = self.get_process_execute_template()
        execute_no_outputs.pop("outputs")

        execute_no_out_mode = self.get_process_execute_template()
        execute_no_out_mode["outputs"][0].pop("transmissionMode")  # should resolve to default value

        # define and run tests
        execute_mock_data_tests = [
            (process_no_inputs.identifier, execute_no_inputs),
            (process_default_input.identifier, execute_default_input),
            (self.process_public.identifier, execute_no_outputs),
            (self.process_public.identifier, execute_no_out_mode),
        ]
        for i, (proc_execute, data_execute) in enumerate(execute_mock_data_tests):
            mock_execute = mocked_process_job_runner(f"job-{name}-{i}")
            with contextlib.ExitStack() as stack:
                for exe in mock_execute:
                    stack.enter_context(exe)
                path = f"/processes/{proc_execute}/jobs"
                resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
                assert resp.status_code == 201, "Expected job submission without inputs created without error."

    def test_execute_process_not_visible(self):
        path = f"/processes/{self.process_private.identifier}/jobs"
        data = self.get_process_execute_template()
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_execute_process_revision(self):
        rev = "1.1.0"
        proc = self.process_public.identifier
        path = f"/processes/{proc}"
        data = {"version": rev, "title": "updated", "jobControlOptions": [ExecuteControlOption.ASYNC]}
        resp = self.app.patch_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 200

        data = self.get_process_execute_template()
        task = f"job-{fully_qualified_name(self)}"
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            for proc_id in [
                f"{proc}:{self.process_public.version}",
                f"{proc}:{rev}",
            ]:
                path = f"/processes/{proc_id}/jobs"
                resp = self.app.post_json(path, params=data, headers=self.json_headers)
                assert resp.status_code == 201, f"Error: {resp.text}"
                assert resp.content_type == ContentType.APP_JSON
                assert resp.json["location"].endswith(resp.json["jobID"])
                assert resp.headers["Location"] == resp.json["location"]
                assert proc_id in resp.headers["Location"]
                try:
                    job = self.job_store.fetch_by_id(resp.json["jobID"])
                except JobNotFound:
                    self.fail("Job should have been created and be retrievable.")
                assert str(job.id) == resp.json["jobID"]
                assert job.task_id == Status.ACCEPTED  # temporary value until processed by celery
                assert job.process == proc_id

    def test_get_process_visibility_expected_response(self):
        for http_code, wps_process in [(403, self.process_private), (200, self.process_public)]:
            process = self.process_store.fetch_by_id(wps_process.identifier)
            path = f"/processes/{process.identifier}/visibility"
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == http_code
            assert resp.content_type == ContentType.APP_JSON
            if http_code == 200:
                assert resp.json["value"] == process.visibility
            else:
                assert "value" not in resp.json

    def test_get_process_visibility_not_found(self):
        path = f"/processes/{self.fully_qualified_test_name()}/visibility"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON

    def test_set_process_visibility_success(self):
        test_process = self.process_private.identifier
        proc_schema = {"schema": ProcessSchema.OLD}
        path_describe = f"/processes/{test_process}"
        path_visibility = f"{path_describe}/visibility"

        # validate cannot be found before
        resp = self.app.get(path_describe, params=proc_schema, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

        # make public
        data = {"value": Visibility.PUBLIC}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["value"] == Visibility.PUBLIC

        # validate now visible and found
        resp = self.app.get(path_describe, params=proc_schema, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["process"]["id"] == test_process

        # make private
        data = {"value": Visibility.PRIVATE}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["value"] == Visibility.PRIVATE

        # validate cannot be found anymore
        resp = self.app.get(path_describe, params=proc_schema, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

    def test_set_process_visibility_immutable(self):
        test_process = self.process_public.identifier
        path_describe = f"/processes/{test_process}"
        path_visibility = f"{path_describe}/visibility"

        process = self.process_store.fetch_by_id(test_process)
        process["type"] = ProcessType.BUILTIN  # this defines an immutable process
        self.process_store.save_process(process, overwrite=True)

        # self-check accessible
        resp = self.app.get(path_describe, headers=self.json_headers)
        assert resp.status_code == 200
        assert not resp.json["mutable"]

        # try to make private
        data = {"value": Visibility.PRIVATE}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

    def test_set_process_visibility_bad_formats(self):
        path = f"/processes/{self.process_private.identifier}/visibility"
        test_data = [
            {"visibility": Visibility.PUBLIC},
            {"visibility": True},
            {"visibility": None},
            {"visibility": 1},
            {"value": True},
            {"value": None},
            {"value": 1}
        ]

        # bad body format or types
        for data in test_data:
            resp = self.app.put_json(path, params=data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code in [400, 422]
            assert resp.content_type == ContentType.APP_JSON

        # bad method POST
        data = {"value": Visibility.PUBLIC}
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 405
        assert resp.content_type == ContentType.APP_JSON

    def test_process_description_metadata_href_or_value_valid(self):
        """
        Validates that metadata is accepted as either hyperlink reference or literal string value.
        """
        process = {
            "id": self._testMethodName,
            "metadata": [
                {"role": "http://example.com/value-typed", "value": "some-value", "lang": "en-US"},
                {"type": ContentType.TEXT_PLAIN, "href": "https://example.com", "hreflang": "en-US", "rel": "example"}
            ],
            "inputs": [],
            "outputs": [],
        }
        result = sd.Process().deserialize(process)
        assert process["metadata"] == result["metadata"]

    def test_process_description_metadata_href_or_value_invalid(self):
        """
        Validates that various invalid metadata definitions are indicated as such.
        """
        test_meta = [
            [{"type": "value", "lang": "en-US"}],  # missing 'value'
            [{"href": "https://example.com", "hreflang": "en-US"}],  # missing 'rel'
            [{"value": "https://example.com", "rel": "value-type"}],  # incorrect 'rel' with 'value' type
            [{"href": "https://example.com", "lang": "en-US"}],  # incorrect 'lang' instead of 'hreflang' with 'href'
            [{"value": "https://example.com", "hreflang": "en-US"}],  # incorrect 'hreflang' with 'value'
        ]
        for i, meta in enumerate(test_meta):
            try:
                sd.Process().deserialize({
                    "id": f"{self._testMethodName}_meta_{i}",
                    "metadata": meta,
                })
            except colander.Invalid:
                pass
            else:
                self.fail(f"Metadata is expected to be raised as invalid: (test: {i}, metadata: {meta})")

    @parameterized.expand([
        ({}, {}, True),  # no outputs returned
        ({}, {"result1": "data", "result2": 123}, True),  # too many outputs returned (not explicitly requested)
        ({"result1": {}, "result2": {}}, {"result1": "data", "result2": 123}, False),  # too many outputs requested
    ])
    @pytest.mark.oap_part3
    def test_execute_process_nested_invalid_results_amount(self, test_outputs, mock_result, expect_execute):
        proc_path = f"/processes/{self.process_public.identifier}"
        exec_path = f"{proc_path}/jobs"
        exec_body = self.get_process_execute_template()
        exec_body["process"] = f"{self.url}{proc_path}"
        exec_body["mode"] = ExecuteMode.SYNC
        exec_inputs = exec_body["inputs"]
        exec_body["inputs"] = {
            "test_input": {
                "process": exec_body["process"],
                "inputs": exec_inputs,
                "outputs": test_outputs,
            }
        }

        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)

            # mock only the nested process monitoring (contrary to the usual strategy that mocks the entire execution)
            # this way, we ensure parsing of the nested inputs/outputs is performed within 'execute_process' task
            # that calls 'parse_wps_inputs', but we still avoid the nested execution to fail due to no actual workers
            nested_monitor = stack.enter_context(
                mock.patch(
                    "weaver.processes.wps_process_base.OGCAPIRemoteProcessBase.monitor",
                    return_Value=True,
                ),
            )
            nested_results = stack.enter_context(
                mock.patch(
                    "weaver.processes.wps_process_base.OGCAPIRemoteProcessBase.get_results",
                    return_value=mock_result,
                ),
            )

            resp = mocked_sub_requests(self.app, "post", exec_path, json=exec_body, headers=self.json_headers)
            assert resp.status_code == 400, f"Error: {resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["location"].endswith(resp.json["jobID"])
            assert resp.headers["Location"] == resp.json["location"]
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert str(job.id) == resp.json["jobID"]

            assert nested_monitor.called if expect_execute else not nested_monitor.called
            assert nested_results.called if expect_execute else not nested_results.called

        resp = self.app.get(f"/jobs/{job.id}/logs", headers={"Accept": ContentType.TEXT_PLAIN})
        assert resp.status_code == 200
        logs = resp.text
        assert "Dispatching execution of nested process" in logs
        assert "Abort execution." in logs


# pylint: disable=C0103,invalid-name
@pytest.mark.functional
class WpsRestApiProcessesNoHTMLTest(WpsConfigBase):
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_restapi_html": False,
    }

    def test_not_acceptable_html_format_query(self):
        resp = self.app.get("/processes", params={"f": "html"}, expect_errors=True)
        assert resp.status_code == 406

    def test_not_acceptable_html_accept_header(self):
        resp = self.app.get("/processes", headers={"Accept": ContentType.TEXT_HTML}, expect_errors=True)
        assert resp.status_code == 406
