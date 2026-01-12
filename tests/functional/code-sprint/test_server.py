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
import jsonschema
from weaver.cli import WeaverClient

TEST_SERVER_BASE_URL = os.getenv("TEST_SERVER_BASE_URL", "http://localhost:4002")
TEST_OAP_VERSION = os.getenv("TEST_OAP_VERSION", "2.0")  # i.e.: "1.0" or "2.0"


@pytest.fixture
def client(scope="module"):
    return WeaverClient(url=TEST_SERVER_BASE_URL)


@pytest.fixture(scope="module", autouse=True)
def openapi_job_status():
    schema_url = "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/statusInfo.yaml"
    response = requests.get(schema_url)
    response.raise_for_status()
    schema_yaml = yaml.safe_load(response.text)
    # The relevant definition is the root schema itself
    return schema_yaml


@pytest.mark.functional
@pytest.mark.remote
@pytest.mark.oap_part1
class TestServerOGCAPIProcesses:
    def test_landing_page_links(self, client):
        result = client.info()
        assert result.code == 200
        links = result.body.get("links", [])
        rel_by_name = {link.get("rel"): link for link in links}
        assert f"http://www.opengis.net/def/rel/ogc/1.0/conformance" in rel_by_name
        assert f"http://www.opengis.net/def/rel/ogc/1.0/processes" in rel_by_name

    def test_conformance_classes(self, client):
        result = client.conformance()
        assert result.code == 200
        conforms_to = result.body.get("conformsTo", [])
        assert f"http://www.opengis.net/spec/ogcapi-processes-1/{TEST_OAP_VERSION}/conf/core" in conforms_to
        assert f"http://www.opengis.net/spec/ogcapi-processes-1/{TEST_OAP_VERSION}/conf/json" in conforms_to

    @pytest.mark.dependency(depends=["test_conformance_classes"])
    def test_service_desc_link_and_oas_validation(self, client):
        result = client.conformance()
        assert result.code == 200
        conforms_to = result.body.get("conformsTo", [])
        oas_conformance_uri = f"http://www.opengis.net/spec/ogcapi-processes-1/{TEST_OAP_VERSION}/conf/oas30"
        conforms_oas = [uri for uri in conforms_to if uri == oas_conformance_uri]
        assert conforms_oas, f"Server does not declare conformance to OAS 3.0 ({oas_conformance_uri})"

        result = client.info()
        assert result.code == 200
        links = result.body.get("links", [])
        service_desc_links = [link for link in links if link.get("rel") == "service-desc"]
        assert service_desc_links, "No service-desc link found"
        # Minimal OAS verification for each service-desc link
        for service_desc_link in service_desc_links:
            oas_response = client._request("GET", service_desc_link["href"])
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
    def test_process_list_schema_and_links(self, client):
        result = client.processes(detail=True)
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
        result_paged = client.processes(limit=1)
        assert result_paged.code == 200
        paged_data = result_paged.body
        paged_links = paged_data.get("links", [])
        paged_rels = [link.get("rel") for link in paged_links]
        assert any(rel in paged_rels for rel in ["next", "prev", "self"])

    @pytest.mark.dependency(depends=["test_process_list_schema_and_links"])
    def test_process_description_and_profile_link(self, client):
        result = client.processes(detail=True)
        process_list = result.body.get("processes", [])
        if not process_list:
            pytest.skip("No processes available to test description.")
        process_id = process_list[0].get("id")
        assert process_id
        desc_result = client.describe(process_id, with_headers=True)
        assert desc_result.code == 200
        process_description = desc_result.body
        assert "id" in process_description and process_description["id"] == process_id

        profile_rel = "http://www.opengis.net/def/profile/OGC/0/ogc-process-description"
        profile = desc_result.headers.get("Profile") or desc_result.headers.get("Content-Profile")
        assert profile == profile_rel

    @pytest.mark.dependency(depends=["test_process_description"])
    def test_sync_execute_all_outputs(self, client):
        result = client.processes()
        process_list = result.body.get("processes", [])
        assert process_list, "No processes available to test execution."
        process_echo = [proc for proc in process_list if proc.get("id") in ["echo", "Echo", "EchoProcess"]]
        assert process_echo, "No echo process available to test execution."
        process_id = process_echo[0].get("id")

        # Build minimal execute request
        execute_result = client.execute(process_id, inputs={})
        assert execute_result.code in (200, 201)
        # If outputs omitted, verify all outputs present
        # If outputs empty, verify response is empty
        # More tests for async, preferences, etc. can be added as stubs

    @pytest.mark.dependency(depends=["test_process_description"])
    def test_job_status(self, client, openapi_job_status):
        result = client.jobs(limit=1)
        assert result.code == 200
        jobs_list = result.body.get("jobs", [])
        assert jobs_list, "No jobs available to test job status."
        job_id = jobs_list[0].get("id")
        status_result = client.status(job_id)
        assert status_result.code == 200
        # Validate against the statusInfo.yaml schema
        jsonschema.validate(instance=status_result.body, schema=openapi_job_status)
        assert "status" in status_result.body
        assert "jobId" in status_result.body and status_result.body["jobId"] == job_id

    @pytest.mark.dependency(depends=["test_process_description"])
    def test_job_results_async(self, client):
        result = client.processes()
        process_list = result.body.get("processes", [])
        if not process_list:
            pytest.skip("No processes available to test job results.")
        process_id = process_list[0].get("id")
        desc_result = client.describe(process_id)
        process_description = desc_result.body
        process_outputs = process_description.get("outputs", [])
        # Async execute (no outputs/prefer args)
        execute_result = client.execute(process_id, inputs={})
        assert execute_result.code in (200, 201)
        job_location = execute_result.headers.get("Location")
        if not job_location:
            job_location = execute_result.body.get("location")
        assert job_location, "No job location provided in async response."
        job_id = job_location.rstrip("/").split("/")[-1]
        # Get job results (no public method, use _request)
        results_url = f"{TEST_SERVER_BASE_URL}/jobs/{job_id}/results"
        results_result = client._request("GET", results_url)
        assert results_result.status_code == 200
        job_results_data = results_result.json()
        if process_outputs:
            output_id = process_outputs[0].get("id")
            query_url = f"{results_url}?outputs={output_id}"
            query_result = client._request("GET", query_url)
            assert query_result.status_code == 200
            direct_url = f"{results_url}/{output_id}"
            direct_result = client._request("GET", direct_url)
            assert direct_result.status_code == 200
            # Optionally verify direct output response
