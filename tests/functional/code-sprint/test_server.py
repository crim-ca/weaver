#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for verifying the functionality of a web server implementing a *OGC API - Processes*.

Definitions are based off the Test Suite Strawman located at:
https://github.com/opengeospatial/developer-events/wiki/Test-Suite-Strawman
"""

import os
import pytest
import requests
import yaml
import uuid
import jsonschema
import warnings
from functools import cached_property
from typing import TYPE_CHECKING, cast

from weaver.cli import WeaverClient
from weaver.formats import OutputFormat

from pytest_dependency import depends

if TYPE_CHECKING:
    from weaver.typedefs import CWL


TEST_SERVER_BASE_URL = os.getenv("TEST_SERVER_BASE_URL", "http://localhost:4002")
TEST_OAP_CORE_VERSION = os.getenv("TEST_OAP_CORE_VERSION", "2.0")  # i.e.: "1.0" or "2.0"
TEST_OAP_CORE_PROCESS_ID = os.getenv("TEST_OAP_CORE_PROCESS_ID", "echo")
TEST_OAP_DRU_PROCESS_ID = os.getenv("TEST_OAP_DRU_PROCESS_ID", "test-echo")


@pytest.fixture(scope="module")
def client():
    return WeaverClient(url=TEST_SERVER_BASE_URL)


@pytest.fixture(scope="module", autouse=True)
def openapi_job_status():
    schema_url = "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/statusInfo.yaml"
    response = requests.get(schema_url)
    response.raise_for_status()
    schema_yaml = yaml.safe_load(response.text)
    # The relevant definition is the root schema itself
    return schema_yaml


def depends_or(request, other, scope='module'):
    item = request.node
    for o in other:
        try:
            depends(request, [o], scope)
        except pytest.skip.Exception:
            continue
        else:
            return
    pytest.skip("%s depends on any of %s" % (item.name, ", ".join(other)))


class ServerOGCAPIProcessesBase:

    @classmethod
    def setup_class(cls):
        cls.client = WeaverClient(url=TEST_SERVER_BASE_URL)

    @cached_property
    def conforms_to(self):
        result = self.client.conformance()
        assert result.code == 200
        return result.body.get("conformsTo", [])

    @cached_property
    def processes(self):
        result = self.client.processes(detail=True, output_format=OutputFormat.JSON)
        assert result.code == 200
        assert result.headers.get("Content-Type", "").startswith("application/json")
        return result.body.get("conformsTo", [])


@pytest.mark.functional
@pytest.mark.remote
@pytest.mark.oap_part1
class TestServerOGCAPIProcessesCore(ServerOGCAPIProcessesBase):

    def test_landing_page_links(self):
        result = self.client.info()
        assert result.code == 200
        links = result.body.get("links", [])
        rel_by_name = {link.get("rel"): link for link in links}
        assert f"http://www.opengis.net/def/rel/ogc/1.0/conformance" in rel_by_name
        assert f"http://www.opengis.net/def/rel/ogc/1.0/processes" in rel_by_name

    @pytest.mark.dependency(name="test_conformance_classes_core")
    def test_conformance_classes_core(self):
        assert f"http://www.opengis.net/spec/ogcapi-processes-1/{TEST_OAP_CORE_VERSION}/conf/core" in self.conforms_to
        assert f"http://www.opengis.net/spec/ogcapi-processes-1/{TEST_OAP_CORE_VERSION}/conf/json" in self.conforms_to

    @pytest.mark.dependency(depends=["test_conformance_classes_core"])
    def test_service_desc_link_and_oas_validation(self):
        oas_conformance_uri = f"http://www.opengis.net/spec/ogcapi-processes-1/{TEST_OAP_CORE_VERSION}/conf/oas30"
        conforms_oas = [uri for uri in self.conforms_to if uri == oas_conformance_uri]
        assert conforms_oas, f"Server does not declare conformance to OAS 3.0 ({oas_conformance_uri})"

        result = self.client.info()
        assert result.code == 200
        links = result.body.get("links", [])
        service_desc_links = [link for link in links if link.get("rel") == "service-desc"]
        assert service_desc_links, "No service-desc link found"
        # Minimal OAS verification for each service-desc link
        for service_desc_link in service_desc_links:
            oas_response = self.client._request("GET", service_desc_link["href"])
            assert oas_response.status_code == 200
            try:
                oas_json = oas_response.json()
            except Exception:
                pytest.fail(f"service-desc href {service_desc_link['href']} did not return valid JSON")
            assert isinstance(
                oas_json, dict
            ), f"service-desc href {service_desc_link['href']} did not return a JSON object"
            assert (
                "openapi" in oas_json
            ), f"service-desc href {service_desc_link['href']} is not an OAS 3.x definition (missing 'openapi' key)"
            assert str(oas_json["openapi"]).startswith(
                "3."
            ), f"service-desc href {service_desc_link['href']} is not OAS 3.x (openapi={oas_json['openapi']})"

    @pytest.mark.dependency(depends=["test_service_desc_link_and_oas_validation"])
    def test_process_list_schema_and_links(self):
        result = self.client.processes(detail=True)
        assert result.code == 200
        process_list_data = result.body
        assert "processes" in process_list_data
        process_list_links = process_list_data.get("links", [])
        process_list_rels = [link.get("rel") for link in process_list_links]
        assert "self" in process_list_rels
        for process_summary in process_list_data["processes"]:
            process_summary_links = process_summary.get("links", [])
            process_summary_rels = [link.get("rel") for link in process_summary_links]
            assert "self" in process_summary_rels
        result_paged = self.client.processes(limit=1)
        assert result_paged.code == 200
        paged_data = result_paged.body
        paged_links = paged_data.get("links", [])
        paged_rels = [link.get("rel") for link in paged_links]
        assert any(rel in paged_rels for rel in ["next", "prev", "self"])

    @pytest.mark.dependency(depends=["test_process_list_schema_and_links"])
    def test_process_description_and_profile_link(self):
        if not self.processes:
            pytest.skip("No processes available to test description.")
        process_id = self.processes[0].get("id")
        assert process_id
        desc_result = self.client.describe(process_id, with_headers=True)
        assert desc_result.code == 200
        process_description = desc_result.body
        assert "id" in process_description and process_description["id"] == process_id

        profile_rel = "http://www.opengis.net/def/profile/OGC/0/ogc-process-description"
        profile = desc_result.headers.get("Profile") or desc_result.headers.get("Content-Profile")
        assert profile == profile_rel

    @pytest.mark.dependency(depends=["test_process_description"])
    def test_sync_execute_all_outputs(self):
        process_echo = [
            proc for proc in self.processes
            if proc.get("id") in [TEST_OAP_CORE_PROCESS_ID, "echo", "Echo", "EchoProcess"]
        ]
        assert process_echo, "No process available to test execution."
        process_id = process_echo[0].get("id")

        # Build minimal execute request
        execute_result = self.client.execute(process_id, inputs={})
        assert execute_result.code in (200, 201)
        # If outputs omitted, verify all outputs present
        # If outputs empty, verify response is empty
        # More tests for async, preferences, etc. can be added as stubs

    @pytest.mark.dependency(depends=["test_process_description"])
    def test_job_status(self, openapi_job_status):
        result = self.client.jobs(limit=1)
        assert result.code == 200
        jobs_list = result.body.get("jobs", [])
        assert jobs_list, "No jobs available to test job status."
        job_id = jobs_list[0].get("id")
        status_result = self.client.status(job_id)
        assert status_result.code == 200
        # Validate against the statusInfo.yaml schema
        jsonschema.validate(instance=status_result.body, schema=openapi_job_status)
        assert "status" in status_result.body
        assert "jobId" in status_result.body and status_result.body["jobId"] == job_id

    @pytest.mark.dependency(depends=["test_process_description"])
    def test_job_results_async(self):
        result = self.client.processes()
        process_list = result.body.get("processes", [])
        if not process_list:
            pytest.skip("No processes available to test job results.")
        process_id = process_list[0].get("id")
        result = self.client.describe(process_id)
        process_description = result.body
        process_outputs = process_description.get("outputs", [])
        # Async execute (no outputs/prefer args)
        execute_result = self.client.execute(process_id, inputs={})
        assert execute_result.code in (200, 201)
        job_location = execute_result.headers.get("Location")
        if not job_location:
            job_location = execute_result.body.get("location")
        assert job_location, "No job location provided in async response."
        job_id = job_location.rstrip("/").split("/")[-1]
        # Get job results (no public method, use _request)
        results_url = f"{TEST_SERVER_BASE_URL}/jobs/{job_id}/results"
        results_result = self.client.results(results_url)
        assert results_result.code == 200
        job_results_data = results_result.body
        assert "outputs" in job_results_data

        # FIXME: no public method to get individual output, use _request
        output_id = process_outputs[0].get("id")
        path = f"{results_url}/{output_id}"
        resp = self.client._request("GET", path)
        assert resp.status_code == 200


@pytest.mark.functional
@pytest.mark.remote
@pytest.mark.oap_part2
class TestServerOGCAPIProcessesDRU(ServerOGCAPIProcessesBase):

    @classmethod
    def setup_class(cls):
        cls.cleanup_processes = set()

    @classmethod
    def teardown_class(cls):
        for process_id in cls.cleanup_processes:
            result = cls.client.undeploy(process_id)
            if result.code not in (200, 204, 404):
                warnings.warn(f"Warning: failed to undeploy process [{process_id}] during teardown.")

    @pytest.mark.dependency(name="test_conformance_classes_dru")
    def test_conformance_classes_dru(self):
        assert "http://www.opengis.net/spec/ogcapi-processes-2/1.0/conf/deploy-replace-undeploy" in self.conforms_to

    @pytest.mark.dependency(depends=["test_conformance_classes_dru"])
    def test_conformance_classes_dru_ogcapppkg(self):
        assert "http://www.opengis.net/spec/ogcapi-processes-2/1.0/conf/ogcapppkg" in self.conforms_to

    @pytest.mark.dependency(depends=["test_conformance_classes_dru"])
    def test_conformance_classes_dru_cwl(self):
        assert "http://www.opengis.net/spec/ogcapi-processes-2/1.0/conf/cwl" in self.conforms_to

    @pytest.mark.dependency(depends=["test_conformance_classes_dru_ogcapppkg"])
    def test_deploy_process_ogcapppkg(self):
        process_id = f"{TEST_OAP_DRU_PROCESS_ID}-{uuid.uuid4().hex[:8]}"
        self.cleanup_processes.add(process_id)
        ogc_app_pkg = {
            "id": process_id,
            "version": "1.0.0",
            "inputs": [{"id": "input", "type": "string"}],
            "outputs": [{"id": "output", "type": "string"}],
            "jobControlOptions": ["sync-execute"],
            "executionUnit": [{"href": "https://example.com/echo-script.py", "type": "text/plain"}]
        }
        result = self.client.deploy(process_id=process_id, body=ogc_app_pkg)
        assert result.code == 200
        location = result.headers.get("Location")
        assert location
        assert location.endswith(f"/processes/{process_id}")
        result = self.client.describe(process_id)
        assert result.code == 200
        desc_json = result.body
        assert desc_json["id"] == process_id
        assert desc_json["inputs"][0]["id"] == ogc_app_pkg["inputs"][0]["id"]
        assert desc_json["outputs"][0]["id"] == ogc_app_pkg["outputs"][0]["id"]

    @pytest.mark.dependency(depends=["test_conformance_classes_dru_cwl"])
    def test_deploy_process_cwl(self):
        process_id = f"{TEST_OAP_DRU_PROCESS_ID}-{uuid.uuid4().hex[:8]}"
        self.cleanup_processes.add(process_id)
        cwl_app_pkg = cast(
            "CWL",
            {
                "cwlVersion": "v1.0",
                "class": "CommandLineTool",
                "id": process_id,
                "baseCommand": "echo",
                "inputs": {"input": "string"},
                "outputs": {"output": {"type": "stdout"}}
            }
        )
        result = self.client.deploy(process_id=process_id, cwl=cwl_app_pkg)
        assert result.code == 200
        location = result.headers.get("Location")
        assert location
        assert location.endswith(f"/processes/{process_id}")
        result = self.client.describe(process_id)
        assert result.code == 200
        desc_json = result.body
        assert desc_json["id"] == process_id
        assert "inputs" in desc_json and "outputs" in desc_json

    @pytest.mark.dependency(depends=["test_deploy_process_ogcapppkg"])
    def test_retrieve_application_package_ogcapppkg(self):
        mutable_proc = next((p for p in self.processes if p.get("id", "").startswith(TEST_OAP_DRU_PROCESS_ID)), None)
        assert mutable_proc, "No mutable process found."
        process_id = mutable_proc["id"]
        pkg_response = self.client.package(process_id)
        assert pkg_response.code == 200
        content_type = pkg_response.headers.get("Content-Type", "")
        assert content_type == "application/ogcapppkg+json"
        pkg_json = pkg_response.body
        desc_response = self.client.describe(process_id)
        assert desc_response.code == 200
        desc_json = desc_response.body
        assert desc_json["id"] == pkg_json.get("id", process_id)
        pkg_inputs = pkg_json.get("inputs", [])
        oap_inputs = desc_json.get("inputs", [])
        pkg_outputs = pkg_json.get("outputs", [])
        oap_outputs = desc_json.get("outputs", [])
        assert set(pkg_inputs) == set(oap_inputs)
        assert set(pkg_outputs) == set(oap_outputs)

    @pytest.mark.dependency(depends=["test_deploy_process_cwl"])
    def test_retrieve_application_package_cwl(self):
        mutable_proc = next((p for p in self.processes if p.get("id", "").startswith(TEST_OAP_DRU_PROCESS_ID)), None)
        assert mutable_proc, "No mutable process found."
        process_id = mutable_proc["id"]
        pkg_response = self.client.package(process_id)
        assert pkg_response.code == 200
        content_type = pkg_response.headers.get("Content-Type", "")
        assert content_type in ["application/cwl+json", "application/cwl+yaml", "application/cwl"]
        pkg_json = pkg_response.body
        desc_response = self.client.describe(process_id)
        assert desc_response.code == 200
        desc_json = desc_response.body
        assert desc_json["id"] == pkg_json.get("id", process_id)
        pkg_inputs = pkg_json.get("inputs", [])
        oap_inputs = desc_json.get("inputs", [])
        pkg_outputs = pkg_json.get("outputs", [])
        oap_outputs = desc_json.get("outputs", [])
        assert set(pkg_inputs) == set(oap_inputs)
        assert set(pkg_outputs) == set(oap_outputs)

    @pytest.mark.dependency(depends=["test_deploy_process_ogcapppkg"])
    def test_replace_process_ogcapppkg(self):
        result = self.client.package(TEST_OAP_DRU_PROCESS_ID)
        assert result.code == 200

        pkg = result.body
        new_id = f"{TEST_OAP_DRU_PROCESS_ID}-{uuid.uuid4().hex[:8]}"
        self.cleanup_processes.add(new_id)
        result = self.client.deploy(process_id=new_id, cwl=pkg)
        assert result.code == 200

        replace_id = f"{TEST_OAP_DRU_PROCESS_ID}-{uuid.uuid4().hex[:8]}"
        self.cleanup_processes.add(replace_id)
        revised_pkg = pkg.copy()
        revised_pkg["inputs"].append({"id": "additional_input", "type": "string"})

        # FIXME: facing method not implemented in client
        body = {
            "id": replace_id,
            "version": "2.0.0",
            "executionUnit": [{"unit": revised_pkg}]
        }
        headers = {"Content-Type": "application/ogcapppkg+json"}
        replace_path = f"{TEST_SERVER_BASE_URL}/processes/{replace_id}"
        result = self.client._request("PUT", replace_path, json=body, headers=headers)
        assert result.status_code in [202, 204]

        result = self.client.describe(replace_id)
        assert result.code == 200
        desc_json = result.body
        assert desc_json["version"] == "2.0.0"

        result = self.client.package(replace_id)
        assert result.code == 200
        pkg_replaced = result.body
        assert pkg_replaced == revised_pkg

    @pytest.mark.dependency(depends=["test_deploy_process_cwl"])
    def test_replace_process_cwl(self):
        result = self.client.package(TEST_OAP_DRU_PROCESS_ID)
        assert result.code == 200

        pkg = result.body
        new_id = f"{TEST_OAP_DRU_PROCESS_ID}-{uuid.uuid4().hex[:8]}"
        self.cleanup_processes.add(new_id)
        result = self.client.deploy(process_id=new_id, cwl=pkg)
        assert result.code == 200

        replace_id = f"{TEST_OAP_DRU_PROCESS_ID}-{uuid.uuid4().hex[:8]}"
        self.cleanup_processes.add(replace_id)
        revised_pkg = pkg.copy()
        revised_pkg["inputs"].append({"id": "additional_input", "type": "string"})

        # FIXME: facing method not implemented in client
        headers = {"Content-Type": "application/cwl+json"}
        replace_path = f"{TEST_SERVER_BASE_URL}/processes/{replace_id}"
        result = self.client._request("PUT", replace_path, json=revised_pkg, headers=headers)
        assert result.status_code in [202, 204]

        result = self.client.describe(replace_id)
        assert result.code == 200
        desc_json = result.body
        assert desc_json["version"] == "2.0.0"

        result = self.client.package(replace_id)
        assert result.code == 200
        pkg_replaced = result.body
        assert pkg_replaced == revised_pkg

    @pytest.mark.dependency()
    def test_delete_process(self, request):
        depends_or(request, ["test_deploy_process_ogcapppkg", "test_deploy_process_cwl"])

        result = self.client.processes()
        processes = result.body.get("processes", [])
        mutable_proc = next((p for p in processes if p.get("id", "").startswith("test-echo")), None)
        assert mutable_proc, "No mutable process found."
        process_id = mutable_proc["id"]
        result = self.client._request("DELETE", f"{TEST_SERVER_BASE_URL}/processes/{process_id}")
        assert result.status_code == 204
        result = self.client.describe(process_id)
        assert result.code == 404
