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
@pytest.mark.oap_part5
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


@pytest.mark.job
@pytest.mark.prov
@pytest.mark.oap_part5
@pytest.mark.functional
class TestJobProvenance(TestJobProvenanceBase):
    """
    Tests to evaluate the various endpoints for :term:`Job` :term:`Provenance`.
    """
    @parameterized.expand([
        ({}, {}),  # default is JSON
        ({"f": OutputFormat.JSON}, {}),
        ({"f": ProvenanceFormat.PROV_JSON}, {}),
        ({"f": "prov+json"}, {}),
        ({"f": "prov%2Bjson"}, {}),
        ({"f": "provenance+json"}, {}),
        ({"f": "provenance%2Bjson"}, {}),
        ({}, {"Accept": ContentType.APP_JSON}),
        ({}, {"Accept": ContentType.APP_PROV_JSON}),
        ({}, {"Accept": f"{ContentType.APP_PROV_JSON}; charset=utf-8"}),
        ({}, {"Accept": f"{ContentType.APP_JSON}; profile=https://www.w3.org/ns/prov"}),
    ])
    def test_job_prov_json(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.APP_PROV_JSON
        prov = resp.json
        assert "prefix" in prov
        assert "wfprov" in prov["prefix"]

    @parameterized.expand([
        ({"f": "ld+json"}, {}),
        ({"f": "ld%2Bjson"}, {}),
        ({"f": "jsonld"}, {}),
        ({"f": ProvenanceFormat.PROV_JSONLD}, {}),
        ({}, {"Accept": ContentType.APP_JSONLD}),
        ({}, {"Accept": f"{ContentType.APP_JSONLD}; profile=https://www.w3.org/TR/prov-jsonld/"}),
    ])
    def test_job_prov_json_ld(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.APP_JSONLD
        prov = resp.json
        assert isinstance(prov, list)
        assert bool(prov), "Must not be an empty list."
        assert all(isinstance(obj, object) and "@id" in obj and "@type" in obj for obj in prov)

    @parameterized.expand([
        ({"f": OutputFormat.YAML}, {}),
        ({}, {"Accept": ContentType.APP_YAML}),
    ])
    def test_job_prov_yaml(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.APP_YAML
        prov = resp.text
        assert "prefix:" in prov

    @parameterized.expand([
        ({"f": OutputFormat.XML}, {}),
        ({"f": ProvenanceFormat.PROV_XML}, {}),
        ({"f": "prov+xml"}, {}),
        ({"f": "prov%2Bxml"}, {}),
        ({"f": "provenance+xml"}, {}),
        ({"f": "provenance%2Bxml"}, {}),
        ({}, {"Accept": ContentType.TEXT_XML}),
        ({}, {"Accept": ContentType.APP_XML}),
        ({}, {"Accept": ContentType.APP_PROV_XML}),
        ({}, {"Accept": f"{ContentType.APP_PROV_XML}; charset=utf-8"}),
    ])
    def test_job_prov_xml(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.APP_PROV_XML
        prov = resp.text
        assert "<prov:document xmlns:wfprov" in prov

    @parameterized.expand([
        ({"f": "turtle"}, {}),
        ({"f": ProvenanceFormat.PROV_TURTLE}, {}),
        ({}, {"Accept": ContentType.TEXT_TURTLE}),
    ])
    def test_job_prov_ttl(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.TEXT_TURTLE
        prov = resp.text
        assert "@prefix cwlprov: " in prov

    @parameterized.expand([
        ({"f": "nt"}, {}),
        ({"f": ProvenanceFormat.PROV_NT}, {}),
        ({}, {"Accept": ContentType.APP_NT}),
    ])
    def test_job_prov_nt(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.APP_NT
        prov = resp.text
        assert "_:N" in prov
        assert "wfprov" in prov

    @parameterized.expand([
        ({"f": "n"}, {}),
        ({"f": ProvenanceFormat.PROV_N}, {}),
        ({}, {"Accept": ContentType.TEXT_PROVN}),
        ({}, {"Accept": f"{ContentType.TEXT_PROVN}; version=1"}),
    ])
    def test_job_prov_provn(self, queries, headers):
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.TEXT_PROVN
        prov = resp.text
        assert "prov:type='wfprov:WorkflowEngine'" in prov

    @parameterized.expand([
        ({}, {"Accept": "application/unsupported"}),
        ({"f": "unsupported"}, {}),
        ({}, {"Accept": ContentType.APP_OCTET_STREAM}),
        ({"f": "binary"}, {}),
    ])
    def test_job_prov_unsupported_format(self, queries, headers):
        """
        Test unsupported PROV format returns 406 Not Acceptable with proper error type.
        """
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers, expect_errors=True)
        assert resp.status_code == 406, f"Expected 406, got {resp.status_code}"
        assert resp.content_type == ContentType.APP_JSON
        assert "type" in resp.json, "Error response must include 'type' field"
        assert resp.json["type"] == (
            "https://www.opengis.net/def/exceptions/ogcapi-processes-5/1.0/prov-unsupported-format"
        )
        assert "detail" in resp.json

    @parameterized.expand([
        ({}, {}),
        ({"f": OutputFormat.JSON}, {}),
        ({}, {"Accept": ContentType.APP_JSON}),
    ])
    def test_job_prov_missing_on_failed_job(self, queries, headers):
        """
        Test that provenance is not available for failed jobs (404 Not Found with proper error type).
        """
        job = self.job_store.save_job(
            "test",
            process=self.proc_id,
            status=Status.FAILED
        )
        prov_url = job.prov_url(self.settings)
        resp = self.app.get(prov_url, params=queries, headers=headers, expect_errors=True)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        assert resp.content_type == ContentType.APP_JSON
        assert "type" in resp.json, "Error response must include 'type' field"
        assert resp.json["type"] == "https://www.opengis.net/def/exceptions/ogcapi-processes-5/1.0/prov-missing"
        assert "detail" in resp.json

    @parameterized.expand([
        ({}, {}),
        ({"f": OutputFormat.JSON}, {}),
        ({}, {"Accept": ContentType.APP_JSON}),
    ])
    def test_job_prov_missing_on_pending_job(self, queries, headers):
        """
        Test that provenance is not available for pending jobs (404 Not Found with proper error type).
        """
        job = self.job_store.save_job(
            "test",
            process=self.proc_id,
            status=Status.ACCEPTED
        )
        prov_url = job.prov_url(self.settings)
        resp = self.app.get(prov_url, params=queries, headers=headers, expect_errors=True)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        assert resp.content_type == ContentType.APP_JSON
        assert "type" in resp.json, "Error response must include 'type' field"
        assert resp.json["type"] == "https://www.opengis.net/def/exceptions/ogcapi-processes-5/1.0/prov-missing"
        assert "detail" in resp.json

    @parameterized.expand([
        ({"f": ProvenanceFormat.PROV_TURTLE}, {"Accept": ContentType.APP_JSON}, ContentType.TEXT_TURTLE),
        ({"f": ProvenanceFormat.PROV_NT}, {"Accept": ContentType.TEXT_PLAIN}, ContentType.APP_NT),
    ])
    def test_job_prov_format_query_precedence(self, queries, headers, expected_content_type):
        """
        Test that format query parameter takes precedence over Accept header.
        """
        prov_url = f"{self.job_url}/prov"
        resp = self.app.get(prov_url, params=queries, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type == expected_content_type

    def test_job_prov_empty_accept_header(self):
        """
        Test that empty Accept header defaults to JSON.
        """
        prov_url = f"{self.job_url}/prov"
        headers = {"Accept": ""}
        resp = self.app.get(prov_url, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_PROV_JSON

    def test_job_prov_info_text(self):
        prov_url = f"{self.job_url}/prov/info"
        job_id = self.job_url.rsplit("/", 1)[-1]
        resp = self.app.get(prov_url, headers={"Accept": ContentType.TEXT_PLAIN})
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.TEXT_PLAIN
        prov = resp.text
        assert f"Workflow run ID: urn:uuid:{job_id}" in prov

    def test_job_prov_info_not_acceptable(self):
        """
        Check the unsupported format of job provenance info.

        The endpoint doesn't support JSON like most API endpoints, only plain text.
        """
        job = self.job_store.save_job(
            "test",
            process=self.proc_id,
            status=Status.SUCCESSFUL
        )
        prov_url = job.prov_url(self.settings)
        headers = self.json_headers  # note: this is the test, while only plain text is supported
        resp = self.app.get(f"{prov_url}/info", headers=headers, expect_errors=True)
        assert resp.status_code == 406, f"Expected 406, got {resp.status_code}"
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
        assert resp.content_type == ContentType.APP_JSON, (
            "error should be in JSON regardless of Accept header or the normal contents media-type"
        )

    def test_job_status_prov_links_all_supported_formats(self):
        """
        Ensure successful job status advertises PROV links for every supported PROV format.
        """
        resp = self.app.get(self.job_url, headers=self.json_headers)
        assert resp.status_code == 200
        links = resp.json.get("links", [])
        prov_links = [link for link in links if link.get("rel") == "https://www.w3.org/ns/prov"]
        assert prov_links, "Expected provenance links in successful job status response."

        expected_types = {
            ContentType.APP_PROV_JSON,
            ContentType.APP_JSONLD,
            ContentType.APP_PROV_XML,
            ContentType.TEXT_PROVN,
            ContentType.APP_NT,
            ContentType.TEXT_TURTLE,
        }
        prov_types = {link.get("type") for link in prov_links}
        missing_types = expected_types - prov_types
        assert not missing_types, f"Missing supported PROV link media-types: {sorted(missing_types)}"
        assert all(
            href_fmt[0].endswith("/prov") and href_fmt[1]
            for href_fmt in (link["href"].split("?", 1) for link in prov_links)
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
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
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
        assert resp.status_code == 200
        assert len(list(filter(lambda header: header[0] == "Content-Type", resp.headerlist))) == 1
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
            status=Status.SUCCESSFUL
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
            status=Status.SUCCESSFUL
        )
        prov_url = job.prov_url(self.settings)
        headers = {"Accept": ContentType.TEXT_PLAIN}
        resp = self.app.get(f"{prov_url}/info", headers=headers, expect_errors=True)
        assert resp.status_code == 410
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["detail"] == "Job provenance could not be retrieved for the specified job."


@pytest.mark.prov
@pytest.mark.oap_part5
@pytest.mark.functional
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
