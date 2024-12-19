import contextlib
import copy
import itertools
import os
import uuid
from typing import TYPE_CHECKING

import pytest
from parameterized import parameterized

from tests.functional.utils import ResourcesUtil, WpsConfigBase
from tests.utils import mocked_execute_celery, mocked_sub_requests, mocked_wps_output
from weaver.formats import ContentType, OutputFormat
from weaver.provenance import ProvenanceFormat, ProvenancePathType
from weaver.status import Status

if TYPE_CHECKING:
    from typing import Optional

    from weaver.typedefs import AnyUUID


@pytest.mark.prov
class TestJobProvenanceBase(WpsConfigBase, ResourcesUtil):
    job_id = None   # type: Optional[AnyUUID]
    job_url = None  # type: Optional[str]
    proc_id = None  # type: Optional[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = copy.deepcopy(cls.settings or {})
        settings = {
            "weaver.cwl_prov": True,
            "weaver.wps_metadata_provider_name": "TestJobProvenanceBase",  # metadata employed by PROV
            "weaver.wps_metadata_provider_url": "http://localhost/",  # metadata employed by PROV
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_url": "http://localhost/wpsoutputs",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        cls.settings.update(settings)
        super(TestJobProvenanceBase, cls).setUpClass()
        cls.setup_test_job()

    @classmethod
    def tearDownClass(cls):
        cls.process_store.clear_processes()
        cls.job_store.clear_jobs()
        super(TestJobProvenanceBase, cls).tearDownClass()

    @classmethod
    def setup_test_job(cls):
        cls.proc_id = cls.fully_qualified_test_name(cls, "Echo")
        cwl = cls.retrieve_payload("Echo", "package", local=True)
        body = {
            "processDescription": {
                "id": cls.proc_id,
            },
            "executionUnit": [{"unit": cwl}],
        }
        cls.deploy_process(body)
        data = {
            "inputs": {"message": "0123456789"},
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            stack_exec.enter_context(mocked_wps_output(cls.settings))
            proc_url = f"/processes/{cls.proc_id}/execution"
            headers = {"Prefer": "respond-async"}
            headers.update(cls.json_headers)
            resp = mocked_sub_requests(
                cls.app, "post_json", proc_url,
                data=data, headers=headers,
                timeout=5, only_local=True
            )
            assert resp.status_code == 201, resp.text
            status_url = resp.headers.get("location")
            cls.monitor_job(status_url, return_status=True)
        cls.job_url = status_url
        cls.job_id = status_url.rsplit("/", 1)[-1]


@pytest.mark.prov
@pytest.mark.oap_part4
@pytest.mark.functional
class TestJobProvenance(TestJobProvenanceBase):
    """
    Tests to evaluate the various endpoints for :term:`Job` :term:`Provenance`.
    """
    @parameterized.expand([
        ({}, {}),  # default is JSON
        ({"f": OutputFormat.JSON}, {}),
        ({}, {"Accept": ContentType.APP_JSON}),
    ])
    def test_job_prov_json(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        prov = resp.json
        assert "prefix" in prov
        assert "wfprov" in prov["prefix"]

    @parameterized.expand([
        ({"f": OutputFormat.XML}, {}),
        ({}, {"Accept": ContentType.TEXT_XML}),
        ({}, {"Accept": ContentType.APP_XML}),
    ])
    def test_job_prov_xml(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        prov = resp.text
        assert "<prov:document xmlns:wfprov" in prov

    def test_job_prov_ttl(self):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_TURTLE})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_TURTLE
        prov = resp.text
        assert "@prefix cwlprov: " in prov

    def test_job_prov_nt(self):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, headers={"Accept": ContentType.APP_NT})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_NT
        prov = resp.text
        assert "_:N" in prov
        assert "wfprov" in prov

    def test_job_prov_provn(self):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_PROVN})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_PROVN
        prov = resp.text
        assert "prov:type='wfprov:WorkflowEngine'" in prov

    def test_job_prov_info_text(self):
        prov_url = f"{self.job_url}/prov/info"
        job_id = self.job_url.rsplit("/", 1)[-1]
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_PLAIN})
        assert resp.status_code == 200
        assert resp.content_type == ContentType.TEXT_PLAIN
        prov = resp.text
        assert f"Workflow run ID: urn:uuid:{job_id}" in prov

    def test_job_prov_info_not_acceptable(self):
        job = self.job_store.save_job(
            "test",
            process=self.proc_id,
            status=Status.SUCCEEDED
        )
        prov_url = job.prov_url(self.settings)
        headers = self.json_headers  # note: this is the test, while only plain text is supported
        resp = self.app.get(f"{prov_url}/info", headers=headers, expect_errors=True)
        assert resp.status_code == 406
        assert resp.content_type == ContentType.APP_JSON, (
            "error should be in JSON regardless of Accept header or the normal contents media-type"
        )

    @parameterized.expand(
        itertools.product(
            ["processes", "jobs"],
            ["info", "who", "inputs", "outputs", "run"],
        )
    )
    def test_job_prov_commands(self, path, cmd):
        job_id = self.job_url.rsplit("/", 1)[-1]
        proc_url = f"/{path}/{self.proc_id}" if path == "processes" else ""
        prov_url = f"{proc_url}/jobs/{job_id}/prov/{cmd}"
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_PLAIN})
        assert resp.content_type == ContentType.TEXT_PLAIN
        assert resp.text != ""

    @parameterized.expand(
        ["inputs", "outputs", "run"]
    )
    def test_job_prov_run_id(self, path):
        """
        Validate retrieval of :term:`Provenance` nested ``runID``.

        .. note::
            In this case, the ``runID`` is somewhat redundant to the ``jobID`` that is applied identically for
            the "main" :term:`Process` at the root of the :term:`Job`, since only an atomic operation is executed.
            In the case of a :term:`Workflow` however, each step could be retrieved respectively by their ``runID``.
        """
        job_id = self.job_url.rsplit("/", 1)[-1]
        prov_url = f"{self.job_url}/prov/{path}/{job_id}"
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_PLAIN})
        assert resp.content_type == ContentType.TEXT_PLAIN
        assert resp.text != ""

    def test_job_prov_run_id_invalid(self):
        run_id = str(uuid.uuid4())
        prov_url = f"{self.job_url}/prov/run/{run_id}"
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_PLAIN}, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON, (
            "Custom JSON error contents are expected to be returned. "
            "If plain text is returned (as requested by Accept header), "
            "this most probably means an error is raised and caught by "
            "pyramid's \"not found view\" utility instead of our \"not found run\" error"
        )
        assert resp.json["error"] == "No such run ID for specified job provenance."
        assert resp.json["value"] == {"run_id": run_id}

    def test_job_prov_data_generated_missing(self):
        """
        Test that data directly obtained from pre-generated files is handled when no :term:`Provenance` exists.
        """
        job = self.job_store.save_job(
            "test",
            process=self.proc_id,
            status=Status.SUCCEEDED
        )
        prov_url = job.prov_url(self.settings)
        resp = self.app.get(prov_url, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 410
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["detail"] == "Job provenance could not be retrieved for the specified job."

    def test_job_prov_data_dynamic_missing(self):
        """
        Test that data generated dynamically by invoking :mod:`cwlprov` is handled when no :term:`Provenance` exists.
        """
        job = self.job_store.save_job(
            "test",
            process=self.proc_id,
            status=Status.SUCCEEDED
        )
        prov_url = job.prov_url(self.settings)
        headers = {"Accept": ContentType.TEXT_PLAIN}
        resp = self.app.get(f"{prov_url}/info", headers=headers, expect_errors=True)
        assert resp.status_code == 410
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["detail"] == "Job provenance could not be retrieved for the specified job."


class TestJobProvenanceDisabled(TestJobProvenanceBase):
    """
    Test handling of the application when :term:`Provenance` feature is disabled.
    """
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = copy.deepcopy(cls.settings or {})
        settings = {
            "weaver.cwl_prov": False,  # NOTE: this is the test
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_url": "http://localhost/wpsoutputs",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        cls.settings.update(settings)

        # don't call 'TestJobProvenanceBase.setUpClass', but it's parents 'setUpClass' instead
        # to configure the web test application the same way with above settings,
        # while making sure to avoid re-enabling 'weaver.cwl_prov = true'
        super(TestJobProvenanceBase, cls).setUpClass()

        # NOTE:
        #   by doing the execution embedded in job setup
        #   most of the code paths without provenance will already be validated
        #   only need to validate the remaining results to match expectations
        cls.setup_test_job()

    @parameterized.expand(
        itertools.product(
            [None, ProvenancePathType.PROV],
            ProvenanceFormat.formats(),
        )
    )
    def test_prov_not_created(self, prov_endpoint, prov_fmt):
        """
        Validate that disabled :term:`Provenance` feature works and that none is generated from an execution.
        """
        job = self.job_store.fetch_by_id(self.job_id)
        prov_path = job.prov_path(extra_path=prov_endpoint, prov_format=prov_fmt, container=self.settings)
        if prov_path is None:
            pytest.skip("Ignore invalid combination of PROV path/format.")
        assert not os.path.exists(prov_path)

    @parameterized.expand(ProvenancePathType.values())
    def test_prov_not_found(self, prov_endpoint):
        """
        Validate that disabled :term:`Provenance` feature works and that endpoints are not available.
        """
        prov_url = f"/jobs/{self.job_id}{prov_endpoint}"
        resp = self.app.get(prov_url, expect_errors=True)
        assert resp.status_code == 404
