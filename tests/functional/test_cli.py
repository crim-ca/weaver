"""
Functional tests for :mod:`weaver.cli`.
"""
import base64
import contextlib
import copy
import json
import logging
import os
import shutil
import tempfile
import uuid
from typing import TYPE_CHECKING

import mock
import pytest
from owslib.ows import DEFAULT_OWS_NAMESPACE
from owslib.wps import WPSException
from pyramid.httpexceptions import HTTPForbidden, HTTPOk, HTTPUnauthorized
from webtest import TestApp as WebTestApp

from tests import resources
from tests.functional.utils import JobUtils, ResourcesUtil, WpsConfigBase
from tests.utils import (
    get_weaver_url,
    mocked_dismiss_process,
    mocked_execute_celery,
    mocked_remote_server_requests_wps1,
    mocked_sub_requests,
    mocked_wps_output,
    run_command,
    setup_config_from_settings
)
from weaver.base import classproperty
from weaver.cli import AuthHandler, BearerAuthHandler, WeaverClient, main as weaver_cli
from weaver.datatype import DockerAuthentication, Service
from weaver.formats import ContentType, OutputFormat, get_cwl_file_format, repr_json
from weaver.processes.constants import CWL_REQUIREMENT_APP_DOCKER, ProcessSchema
from weaver.processes.types import ProcessType
from weaver.status import Status, StatusCategory
from weaver.utils import fully_qualified_name
from weaver.visibility import Visibility
from weaver.wps.utils import map_wps_output_location

if TYPE_CHECKING:
    from typing import Dict, Optional

    from weaver.typedefs import AnyRequestType, AnyResponseType, CWL


class FakeAuthHandler(object):
    def __call__(self, *_, **__):
        return None


@pytest.mark.cli
@pytest.mark.functional
class TestWeaverClientBase(WpsConfigBase, ResourcesUtil, JobUtils):
    test_process_prefix = "test-client-"

    @classmethod
    def setUpClass(cls):
        settings = copy.deepcopy(cls.settings or {})
        settings.update({
            "weaver.vault_dir": tempfile.mkdtemp(prefix="weaver-test-"),
            "weaver.wps_output_dir": tempfile.mkdtemp(prefix="weaver-test-"),
            "weaver.wps_output_url": "http://random-file-server.com/wps-outputs"
        })
        cls.settings = settings
        super(TestWeaverClientBase, cls).setUpClass()
        cls.url = get_weaver_url(cls.app.app.registry)
        cls.client = WeaverClient(cls.url)
        cli_logger = logging.getLogger("weaver.cli")
        cli_logger.setLevel(logging.DEBUG)

    def setUp(self):
        self.job_store.clear_jobs()
        self.service_store.clear_services()

        processes = self.process_store.list_processes()
        test_processes = filter(lambda _proc: _proc.id.startswith(self.test_process_prefix), processes)
        for proc in test_processes:
            self.process_store.delete_process(proc.id)

        # make one process available for testing features
        self.test_process = {}
        self.test_payload = {}
        for process in ["Echo", "CatFile"]:
            self.test_process[process] = f"{self.test_process_prefix}{process}"
            self.test_payload[process] = self.retrieve_payload(process, "deploy", local=True)
            self.deploy_process(self.test_payload[process], process_id=self.test_process[process])

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClientBase, cls).tearDownClass()
        for tmp_dir_cfg in ["weaver.vault_dir", "weaver.wps_output_dir"]:
            tmp_wps_out = cls.settings.get(tmp_dir_cfg, "")
            if os.path.isdir(tmp_wps_out):
                shutil.rmtree(tmp_wps_out, ignore_errors=True)


class TestWeaverClient(TestWeaverClientBase):
    @classmethod
    def setUpClass(cls):
        super(TestWeaverClient, cls).setUpClass()
        cls.test_tmp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClient, cls).tearDownClass()
        shutil.rmtree(cls.test_tmp_dir, ignore_errors=True)

    def setup_test_file(self, original_file, substitutions):
        # type: (str, Dict[str, str]) -> str
        path = os.path.join(self.test_tmp_dir, str(uuid.uuid4()))
        os.makedirs(path, exist_ok=True)
        test_file_path = os.path.join(path, os.path.split(original_file)[-1])
        with open(original_file, mode="r", encoding="utf-8") as real_file:
            data = real_file.read()
            for sub, new in substitutions.items():
                data = data.replace(sub, new)
        with open(test_file_path, mode="w", encoding="utf-8") as test_file:
            test_file.write(data)
        return test_file_path

    def process_listing_op(self, operation, **op_kwargs):
        result = mocked_sub_requests(self.app, operation, only_local=True, **op_kwargs)
        assert result.success
        assert "processes" in result.body
        assert "undefined" not in result.message
        return result

    def test_capabilities(self):
        result = self.process_listing_op(self.client.capabilities)
        assert set(result.body["processes"]) == {
            # builtin
            "file2string_array",
            "file_index_selector",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process["CatFile"],
            self.test_process["Echo"],
        }

    def test_processes(self):
        result = self.process_listing_op(self.client.processes)
        assert set(result.body["processes"]) == {
            # builtin
            "file2string_array",
            "file_index_selector",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process["CatFile"],
            self.test_process["Echo"],
        }

    def test_processes_with_details(self):
        result = self.process_listing_op(self.client.processes, detail=True)
        assert all(isinstance(proc, dict) for proc in result.body["processes"])
        expect_ids = [proc["id"] for proc in result.body["processes"]]
        assert set(expect_ids) == {
            # builtin
            "file2string_array",
            "file_index_selector",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process["CatFile"],
            self.test_process["Echo"],
        }

    @mocked_remote_server_requests_wps1([
        (resources.TEST_REMOTE_SERVER_URL, resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, [
            resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML
        ]),
        (resources.TEST_HUMMINGBIRD_WPS1_URL, resources.TEST_HUMMINGBIRD_WPS1_GETCAP_XML, []),
        (resources.TEST_EMU_WPS1_GETCAP_URL, resources.TEST_EMU_WPS1_GETCAP_XML, []),
    ])
    def test_processes_with_providers(self):
        prov1 = Service(name="emu", url=resources.TEST_EMU_WPS1_GETCAP_URL, public=True)
        prov2 = Service(name="hummingbird", url=resources.TEST_HUMMINGBIRD_WPS1_URL, public=True)
        prov3 = Service(name="test-service", url=resources.TEST_REMOTE_SERVER_URL, public=True)
        self.service_store.save_service(prov1)
        self.service_store.save_service(prov2)
        self.service_store.save_service(prov3)

        result = self.process_listing_op(self.client.processes, with_providers=True)
        assert len(result.body["processes"]) > 0, "Local processes should be reported as well along with providers."
        assert "providers" in result.body
        assert result.body["providers"] == [
            {"id": prov1.name, "processes": resources.TEST_EMU_WPS1_PROCESSES},
            {"id": prov2.name, "processes": resources.TEST_HUMMINGBIRD_WPS1_PROCESSES},
            {"id": prov3.name, "processes": resources.TEST_REMOTE_SERVER_WPS1_PROCESSES},
        ]

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML]
    ])
    def test_register_provider(self):
        prov_id = "test-server"
        prov_url = resources.TEST_REMOTE_SERVER_URL
        result = mocked_sub_requests(self.app, self.client.register, prov_id, prov_url, only_local=True)
        assert result.success
        assert result.body["id"] == "test-server"
        assert result.body["title"] == "Mock Remote Server"
        assert result.body["description"] == "Testing"
        assert result.body["type"] == ProcessType.WPS_REMOTE
        assert "links" in result.body
        for link in result.body["links"]:
            if link["rel"] != "service-desc":
                continue
            assert "request=GetCapabilities" in link["href"]
            assert link["type"] == ContentType.APP_XML
            break
        else:
            self.fail("Could not find expected remote WPS link reference.")
        for link in result.body["links"]:
            if link["rel"] != "service":
                continue
            assert link["href"] == f"{self.url}/providers/{prov_id}"
            assert link["type"] == ContentType.APP_JSON
            break
        else:
            self.fail("Could not find expected provider JSON link reference.")
        for link in result.body["links"]:
            if link["rel"] != "http://www.opengis.net/def/rel/ogc/1.0/processes":
                continue
            assert link["href"] == f"{self.url}/providers/{prov_id}/processes"
            assert link["type"] == ContentType.APP_JSON
            break
        else:
            self.fail("Could not find expected provider sub-processes link reference.")

    def test_unregister_provider(self):
        prov = Service(name="test-service", url=resources.TEST_REMOTE_SERVER_URL, public=True)
        self.service_store.save_service(prov)

        result = mocked_sub_requests(self.app, self.client.unregister, prov.name, only_local=True)
        assert result.success
        assert result.message == "Successfully unregistered provider."
        assert result.code == 204
        assert result.body is None

    def test_custom_auth_handler(self):
        """
        Validate use of custom authentication handler works.

        Called operation does not matter.
        """
        token = str(uuid.uuid4())

        class CustomAuthHandler(AuthHandler):
            def __call__(self, request):
                request.headers["Custom-Authorization"] = f"token={token}&user={self.identity}"
                return request

        auth = CustomAuthHandler(identity="test")  # insert an auth property that should be used by prepared request
        # skip result parsing to return obtained response directly, which contains a reference to the prepared request
        with mock.patch.object(WeaverClient, "_parse_result", side_effect=lambda r, *_, **__: r):
            resp = mocked_sub_requests(self.app, self.client.describe, self.test_process["Echo"], auth=auth)
        assert resp.status_code == 200, "Operation should have been called successfully"
        assert resp.json["id"] == self.test_process["Echo"], "Operation should have been called successfully"
        assert "Custom-Authorization" in resp.request.headers
        assert resp.request.headers["Custom-Authorization"] == f"token={token}&user=test"

    def test_deploy_payload_body_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}deploy-body-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload["executionUnit"][0] = {"unit": package}

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_file_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}deploy-file-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload["executionUnit"][0] = {"href": package}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cwl") as body_file:
            json.dump(payload, body_file)
            body_file.flush()
            body_file.seek(0)
            result = mocked_sub_requests(self.app, self.client.deploy, test_id, body_file.name)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_inject_cwl_body(self):
        test_id = f"{self.test_process_prefix}deploy-body-with-cwl-body"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload.pop("executionUnit", None)

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload, package)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_inject_cwl_file(self):
        test_id = f"{self.test_process_prefix}deploy-body-with-cwl-file"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload.pop("executionUnit", None)

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload, package)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_with_undeploy(self):
        test_id = f"{self.test_process_prefix}deploy-undeploy-flag"
        deploy = self.test_payload["Echo"]
        result = mocked_sub_requests(self.app, self.client.deploy, test_id, deploy)
        assert result.success
        result = mocked_sub_requests(self.app, self.client.deploy, test_id, deploy, undeploy=True)
        assert result.success
        assert "undefined" not in result.message

    def test_undeploy(self):
        # deploy a new process to leave the test one available
        other_payload = copy.deepcopy(self.test_payload["Echo"])
        other_process = self.test_process["Echo"] + "-other"
        self.deploy_process(other_payload, process_id=other_process)

        result = mocked_sub_requests(self.app, self.client.undeploy, other_process)
        assert result.success
        assert result.body.get("undeploymentDone", None) is True
        assert "undefined" not in result.message

        path = f"/processes/{other_process}"
        resp = mocked_sub_requests(self.app, "get", path, expect_errors=True)
        assert resp.status_code == 404

    def test_describe(self):
        result = mocked_sub_requests(self.app, self.client.describe, self.test_process["Echo"])
        assert self.test_payload["Echo"]["processDescription"]["process"]["version"] == "1.0", (
            "Original version submitted should be partial."
        )

        assert result.success
        # see deployment file for details that are expected here
        assert result.body["id"] == self.test_process["Echo"]
        assert result.body["version"] == "1.0"
        assert result.body["keywords"] == ["test", "application"]  # app is added by Weaver since not CWL Workflow
        assert "message" in result.body["inputs"]
        assert result.body["inputs"]["message"]["title"] == "message"
        assert result.body["inputs"]["message"]["description"] == "Message to echo."
        assert result.body["inputs"]["message"]["minOccurs"] == 1
        assert result.body["inputs"]["message"]["maxOccurs"] == 1
        assert result.body["inputs"]["message"]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert "output" in result.body["outputs"]
        assert result.body["outputs"]["output"]["title"] == "output"
        assert result.body["outputs"]["output"]["description"] == "Output file with echo message."
        assert result.body["outputs"]["output"]["formats"] == [{"default": True, "mediaType": ContentType.TEXT_PLAIN}]
        assert "undefined" not in result.message, "CLI should not have confused process description as response detail."
        assert result.body["description"] == (
            "Dummy process that simply echo's back the input message for testing purposes."
        ), "CLI should not have overridden the process description field."

    def run_execute_inputs_schema_variant(self, inputs_param, process="Echo",
                                          preload=False, location=False, expect_success=True, mock_exec=True):
        if isinstance(inputs_param, str):
            ref = {"location": inputs_param} if location else {"ref_name": inputs_param}
            if preload:
                inputs_param = self.retrieve_payload(process=process, local=True, **ref)
            else:
                inputs_param = self.retrieve_payload(process=process, local=True, **ref)
        with contextlib.ExitStack() as stack_exec:
            # use pass-through function because don't care about execution result here, only the parsing of I/O
            if mock_exec:
                mock_exec_func = lambda *_, **__: None  # noqa: E731
            else:
                mock_exec_func = None
            for mock_exec_proc in mocked_execute_celery(func_execute_task=mock_exec_func):
                stack_exec.enter_context(mock_exec_proc)
            result = mocked_sub_requests(self.app, self.client.execute, self.test_process[process], inputs=inputs_param)
        if expect_success:
            assert result.success, result.message + (result.text if result.text else "")
            assert "jobID" in result.body
            assert "processID" in result.body
            assert "status" in result.body
            assert "location" in result.body
            assert result.body["processID"] == self.test_process[process]
            assert result.body["status"] == Status.ACCEPTED
            assert result.body["location"] == result.headers["Location"]
            assert "undefined" not in result.message
        else:
            assert not result.success, result.text
        return result

    def test_execute_inputs_cwl_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", preload=False)

    def test_execute_inputs_ogc_value_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml", preload=False)

    def test_execute_inputs_ogc_mapping_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml", preload=False)

    def test_execute_inputs_old_listing_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml", preload=False)

    def test_execute_inputs_cwl_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", preload=True)

    def test_execute_inputs_ogc_value_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml", preload=True)

    def test_execute_inputs_ogc_mapping_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml", preload=True)

    def test_execute_inputs_old_listing_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml", preload=True)

    def test_execute_inputs_representation_literal_schema(self):
        self.run_execute_inputs_schema_variant(["message='hello world'"], preload=True)

    def test_execute_inputs_invalid(self):
        """
        Mostly check that errors don't raise an error in the client, but are handled and gracefully return a result.
        """
        for invalid_inputs_schema in [
            [1, 2, 3, 4],  # missing the ID
            [{"id": "message"}],  # missing the value
            {}  # valid schema, but missing inputs of process
        ]:
            self.run_execute_inputs_schema_variant(invalid_inputs_schema, expect_success=False)

    def test_execute_manual_monitor_status_and_download_results(self):
        """
        Test a typical case of :term:`Job` execution, result retrieval and download, but with manual monitoring.

        Manual monitoring can be valid in cases where a *very* long :term:`Job` must be executed, and the user does
        not intend to wait after it. This avoids leaving some shell/notebook/etc. open of a long time and provide a
        massive ``timeout`` value. Instead, the user can simply re-call :meth:`WeaverClient.monitor` at a later time
        to resume monitoring. Other situation can be if the connection was dropped or script runner crashed, and the
        want to pick up monitoring again.

        .. note::
            The :meth:`WeaverClient.execute` is accomplished synchronously during this test because of the mock.
            The :meth:`WeaverClient.monitor` step can therefore only return ``success``/``failed`` directly
            without any intermediate and asynchronous pooling of ``running`` status.
            The first status result from  :meth:`WeaverClient.execute` is ``accept`` because this is the
            default status that is generated by the HTTP response from the :term:`Job` creation.
            Any following GET status will directly return the final :term:`Job` result.
        """
        result = self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", mock_exec=False)
        job_id = result.body["jobID"]
        result = mocked_sub_requests(self.app, self.client.monitor, job_id, timeout=1, interval=1)
        assert result.success, result.text
        assert "undefined" not in result.message
        assert result.body.get("status") == Status.SUCCEEDED
        links = result.body.get("links")
        assert isinstance(links, list)
        assert len(list(filter(lambda _link: _link["rel"].endswith("results"), links))) == 1

        # first test to get job results details, but not downloading yet
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.text
        assert "undefined" not in result.message
        outputs_body = result.body
        assert isinstance(outputs_body, dict) and len(outputs_body) == 1
        output = outputs_body.get("output")  # single of this process
        assert isinstance(output, dict) and "href" in output, "Output named 'output' should be a 'File' reference."
        output_href = output.get("href")
        assert isinstance(output_href, str) and output_href.startswith(self.settings["weaver.wps_output_url"])

        # test download feature
        with contextlib.ExitStack() as stack:
            server_mock = stack.enter_context(mocked_wps_output(self.settings))
            target_dir = stack.enter_context(tempfile.TemporaryDirectory())
            result = mocked_sub_requests(self.app, self.client.results,
                                         job_id, download=True, out_dir=target_dir,  # 'client.results' parameters
                                         only_local=True)  # mock parameter (avoid download HTTP redirect to TestApp)
            assert result.success, result.text
            assert "undefined" not in result.message
            assert result.body != outputs_body, "Download operation should modify the original outputs body."
            output = result.body.get("output", {})
            assert output.get("href") == output_href
            output_path = output.get("path")  # inserted by download
            assert isinstance(output_path, str) and output_path.startswith(target_dir)
            output_name = output_href.split(job_id)[-1][1:]  # everything after jobID, and without the first '/'
            output_file = os.path.join(target_dir, output_name)
            assert output_path == output_file
            assert os.path.isfile(output_file) and not os.path.islink(output_file)
            assert len(server_mock.calls) == 1  # list of (PreparedRequest, Response)
            assert server_mock.calls[0][0].url == output_href

    @pytest.mark.xfail(reason="not implemented")
    def test_execute_with_auto_monitor(self):
        """
        Test case where monitoring is accomplished automatically and inline to the execution before result download.
        """
        # FIXME: Properly test execute+monitor,
        #   Need an actual (longer) async call because 'mocked_execute_celery' blocks until complete.
        #   Therefore, no pooling monitoring actually occurs (only single get status with final result).
        #   Test should wrap 'get_job' in 'get_job_status' view (or similar wrapping approach) to validate that
        #   status was periodically pooled and returned 'running' until the final 'succeeded' resumes to download.
        raise NotImplementedError

    # NOTE:
    #   For all below '<>_auto_resolve_vault' test cases, the local file referenced in the Execute request body
    #   should be automatically handled by uploading to the Vault and forwarding the relevant X-Auth-Vault header.
    def run_execute_inputs_with_vault_file(self, test_input_file, process="CatFile", preload=False, embed=False):
        test_data = "DUMMY DATA"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as tmp_file:
            tmp_file.write(test_data)
            tmp_file.flush()
            tmp_file.seek(0)
            if embed:
                test_file = [test_input_file.format(test_file=tmp_file.name)]
            else:
                exec_file = self.retrieve_payload(process=process, ref_name=test_input_file, local=True, ref_found=True)
                test_file = self.setup_test_file(exec_file, {"<TEST_FILE>": tmp_file.name})
            result = self.run_execute_inputs_schema_variant(test_file, process=process,
                                                            preload=preload, location=True, mock_exec=False)
        job_id = result.body["jobID"]
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.message
        output = result.body["output"]["href"]
        output = map_wps_output_location(output, self.settings, exists=True)
        assert os.path.isfile(output)
        with open(output, mode="r", encoding="utf-8") as out_file:
            out_data = out_file.read()
        assert out_data == test_data

    @pytest.mark.vault
    def test_execute_inputs_cwl_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_cwl_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_ogc_mapping_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_ogc_mapping_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_old_listing_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_old_listing_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_cwl_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_cwl_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_ogc_mapping_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_ogc_mapping_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_old_listing_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_old_listing_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_representation_literal_schema_auto_resolve_vault(self):
        # 1st 'file' is the name of the process input
        # 2nd 'File' is the type (CWL) to ensure proper detection/conversion to href URL
        # 'test_file' will be replaced by the actual temp file instantiated with dummy data
        for input_data in [
            "file:File={test_file}",
            "file:File='{test_file}'",
            "file:File=\"{test_file}\"",
        ]:
            self.run_execute_inputs_with_vault_file(input_data, "CatFile", preload=False, embed=True)

    @mocked_dismiss_process()
    def test_dismiss(self):
        for status in [Status.ACCEPTED, Status.FAILED, Status.RUNNING, Status.SUCCEEDED]:
            proc = self.test_process["Echo"]
            job = self.job_store.save_job(task_id="12345678-1111-2222-3333-111122223333", process=proc)
            job.status = status
            job = self.job_store.update_job(job)
            result = mocked_sub_requests(self.app, self.client.dismiss, str(job.id))
            assert result.success
            assert "undefined" not in result.message

    def test_jobs_search_multi_status(self):
        self.job_store.clear_jobs()
        proc = self.test_process["Echo"]
        job1 = self.job_store.save_job(task_id=uuid.uuid4(), process=proc, access=Visibility.PUBLIC)
        job2 = self.job_store.save_job(task_id=uuid.uuid4(), process=proc, access=Visibility.PUBLIC)
        job3 = self.job_store.save_job(task_id=uuid.uuid4(), process=proc, access=Visibility.PUBLIC)
        job1.status = Status.SUCCEEDED
        job2.status = Status.FAILED
        job3.status = Status.RUNNING
        job1 = self.job_store.update_job(job1)
        job2 = self.job_store.update_job(job2)
        job3 = self.job_store.update_job(job3)
        jobs = [job1, job2, job3]

        for test_status, job_expect in [
            (Status.SUCCEEDED, [job1]),
            ([Status.SUCCEEDED], [job1]),
            ([Status.SUCCEEDED, Status.RUNNING], [job1, job3]),
            (f"{Status.SUCCEEDED},{Status.RUNNING}", [job1, job3]),
            (StatusCategory.FINISHED, [job1, job2]),
            (StatusCategory.FINISHED.value, [job1, job2]),
            ([StatusCategory.FINISHED], [job1, job2]),
            ([StatusCategory.FINISHED.value], [job1, job2]),
            (f"{StatusCategory.FINISHED.value},{Status.FAILED}", [job1, job2]),  # failed within finished, nothing added
            ([StatusCategory.FINISHED.value, Status.RUNNING], [job1, job2, job3]),
            ([StatusCategory.FINISHED, Status.RUNNING], [job1, job2, job3]),
            (f"{StatusCategory.FINISHED.value},{Status.RUNNING}", [job1, job2, job3]),
        ]:
            result = mocked_sub_requests(self.app, self.client.jobs, status=test_status, detail=False)
            expect = [job.id for job in job_expect]
            assert result.success
            self.assert_equal_with_jobs_diffs(result.body["jobs"], expect, test_status, jobs=jobs)


class TestWeaverCLI(TestWeaverClientBase):
    def setUp(self):
        super(TestWeaverCLI, self).setUp()
        job = self.job_store.save_job(task_id="12345678-1111-2222-3333-111122223333",
                                      process="fake-process", access=Visibility.PUBLIC)
        job.status = Status.SUCCEEDED
        self.test_job = self.job_store.update_job(job)

    def test_help_operations(self):
        lines = run_command(
            [
                "weaver",
                "--help",
            ],
            trim=False,
        )
        operations = [
            "deploy",
            "undeploy",
            "capabilities",
            "processes",
            "describe",
            "execute",
            "monitor",
            "dismiss",
            "results",
            "status",
        ]
        assert all(any(op in line for line in lines) for op in operations)

    def test_auth_handler_unresolved(self):
        """
        Validates some custom argument parser actions to validate special handling.
        """
        name = "random.HandlerDoesNotExist"
        args = ["processes", "-u", self.url, "-aC", name]
        lines = run_command(args, entrypoint=weaver_cli, trim=False, expect_error=True)
        assert lines
        assert "error: argument -aC" in lines[-1] and name in lines[-1]

    def test_auth_handler_bad_type(self):
        """
        Validate that even if authentication handler class is resolved, it must be of appropriate type.
        """
        name = fully_qualified_name(FakeAuthHandler)
        args = ["processes", "-u", self.url, "-aC", name]
        lines = run_command(args, entrypoint=weaver_cli, trim=False, expect_error=True)
        assert lines
        assert "error: argument -aC" in lines[-1] and name in lines[-1] and "oneOf[AuthHandler, AuthBase]" in lines[-1]

    def test_auth_headers_invalid(self):
        """
        Validates custom argument parser action to validate special handling.
        """
        args = ["processes", "-u", self.url, "-aH", "not-valid-header"]
        lines = run_command(args, entrypoint=weaver_cli, trim=False, expect_error=True)
        assert lines
        assert "error: argument -aH" in lines[-1]

    def test_auth_http_method_invalid(self):
        """
        Validates custom argument parser action to validate special handling.
        """
        args = ["processes", "-u", self.url, "-aM", "NOT_HTTP_METHOD"]
        lines = run_command(args, entrypoint=weaver_cli, trim=False, expect_error=True)
        assert lines
        assert "error: argument -aM" in lines[-1]

    def test_auth_options_many_headers_valid(self):
        """
        Validates headers appendable with custom argument parser action when multiple options are provided.
        """
        lines = mocked_sub_requests(
            self.app, run_command,
            ["processes", "-u", self.url, "-aH", "Accept:application/json", "-aH", "User-Agent:test"],
            entrypoint=weaver_cli,
            trim=False,
            only_local=True,
        )
        assert lines, "lines should be captured from successful execution"
        assert "processes" in "".join(lines)

    def test_log_options_any_level(self):
        """
        Logging parameters should be allowed at main parser level or under any operation subparser.
        """
        proc = self.test_process["Echo"]
        for options in [
            ["--verbose", "describe", "-u", self.url, "-p", proc],
            ["describe", "-u", self.url, "--verbose", "-p", proc],
            ["describe", "-u", self.url, "-p", proc, "--verbose"],
        ]:
            lines = mocked_sub_requests(
                self.app, run_command,
                options,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{proc}\"" in line for line in lines)

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML]
    ])
    def test_register_provider(self):
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "register",
                "-u", self.url,
                "-pI", "test-provider",
                "-pU", resources.TEST_REMOTE_SERVER_URL,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any("\"id\": \"test-provider\"" in line for line in lines)
        assert any(f"\"url\": \"{resources.TEST_REMOTE_SERVER_URL}\"" in line for line in lines)
        assert any(f"\"type\": \"{ProcessType.WPS_REMOTE}\"" in line for line in lines)

    def test_deploy_no_process_id_option(self):
        payload = self.retrieve_payload("Echo", "deploy", local=True, ref_found=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "--body", payload,  # no --process/--id, but available through --body
                "--cwl", package,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any("\"id\": \"Echo\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_docker_auth_help(self):
        """
        Validate some special handling to generate special combinations of help argument details.
        """
        lines = run_command(
            [
                # "weaver",
                "deploy",
                "--help",
            ],
            trim=False,
            entrypoint=weaver_cli,
        )
        args_help = "[-T TOKEN | ( -U USERNAME -P PASSWORD )]"
        err_help = f"Expression '{args_help}' not matched in:\n{repr_json(lines, indent=2)}"
        assert any(args_help in line for line in lines), err_help
        docker_auth_help = "Docker Authentication Arguments"
        docker_lines = []
        for i, line in enumerate(lines):
            if line.startswith(docker_auth_help):
                docker_lines = lines[i:]
                break
        assert docker_lines
        docker_opts = ["-T TOKEN", "-U USERNAME", "-P PASSWORD"]
        docker_help = f"Arguments {docker_opts} not found in {repr_json(docker_lines, indent=2)}"
        assert all(any(opt in line for line in docker_lines) for opt in docker_opts), docker_help

    @staticmethod
    def add_docker_pull_ref(cwl, ref):
        # type: (CWL, str) -> CWL
        cwl.setdefault("requirements", {})
        cwl["requirements"].setdefault(CWL_REQUIREMENT_APP_DOCKER, {})
        cwl["requirements"][CWL_REQUIREMENT_APP_DOCKER] = {"dockerPull": ref}
        return cwl

    def test_deploy_docker_auth_username_password_valid(self):
        """
        Test that username and password arguments can be provided simultaneously for docker login.

        .. note::
            Docker Authentication and corresponding deployment is not evaluated here, only arguments parsing.

        .. seealso::
            :meth:`tests.wps_restapi.test_processes.WpsRestApiProcessesTest.test_deploy_process_CWL_DockerRequirement_auth_header_format`
        """
        p_id = self.fully_qualified_test_process_name()
        docker_reg = "fake.repo"
        docker_img = "org/project/private-image:latest"
        docker_ref = f"{docker_reg}/{docker_img}"
        docker_usr = "random"
        docker_pwd = str(uuid.uuid4())
        package = self.retrieve_payload("Echo", "package", local=True)
        package = self.add_docker_pull_ref(package, docker_ref)
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-D",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-U", docker_usr,
                "-P", docker_pwd,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any("\"description\": \"Process successfully deployed.\"" in line for line in lines)
        assert any(f"\"id\": \"{p_id}\"" in line for line in lines)

        # validate saved process contains the appropriate credentials
        process = self.process_store.fetch_by_id(p_id)
        assert process.auth.type == DockerAuthentication.type
        assert process.auth.docker == docker_ref
        assert process.auth.image == docker_img
        assert process.auth.registry == docker_reg
        assert process.auth.credentials == {"registry": docker_reg, "username": docker_usr, "password": docker_pwd}

    def test_deploy_docker_auth_token_valid(self):
        """
        Test that token argument can be provided by itself for docker login.

        .. note::
            Docker Authentication and corresponding deployment is not evaluated here, only arguments parsing.

        .. seealso::
            :meth:`tests.wps_restapi.test_processes.WpsRestApiProcessesTest.test_deploy_process_CWL_DockerRequirement_auth_header_format`
        """
        p_id = self.fully_qualified_test_process_name()
        docker_reg = "fake.repo"
        docker_img = "org/project/private-image:latest"
        docker_ref = f"{docker_reg}/{docker_img}"
        docker_usr = "random"
        docker_pwd = str(uuid.uuid4())
        docker_tkt = base64.b64encode(f"{docker_usr}:{docker_pwd}".encode("utf-8")).decode("utf-8")
        package = self.retrieve_payload("Echo", "package", local=True)
        package = self.add_docker_pull_ref(package, docker_ref)
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-D",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-T", docker_tkt,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any("\"description\": \"Process successfully deployed.\"" in line for line in lines)
        assert any(f"\"id\": \"{p_id}\"" in line for line in lines)

        # validate saved process contains the appropriate credentials
        process = self.process_store.fetch_by_id(p_id)
        assert process.auth.type == DockerAuthentication.type
        assert process.auth.docker == docker_ref
        assert process.auth.image == docker_img
        assert process.auth.registry == docker_reg
        assert process.auth.token == docker_tkt
        assert process.auth.credentials == {"registry": docker_reg, "username": docker_usr, "password": docker_pwd}

    def test_deploy_docker_auth_username_or_password_with_token_invalid(self):
        """
        Test that username/password cannot be combined with token for docker login.

        All parameter values are themselves valid, only their combination that are not.
        """
        p_id = self.fully_qualified_test_process_name()
        docker_reg = "fake.repo"
        docker_img = "org/project/private-image:latest"
        docker_ref = f"{docker_reg}/{docker_img}"
        docker_usr = "random"
        docker_pwd = str(uuid.uuid4())
        docker_tkt = base64.b64encode(f"{docker_usr}:{docker_pwd}".encode("utf-8")).decode("utf-8")
        package = self.retrieve_payload("Echo", "package", local=True)
        package = self.add_docker_pull_ref(package, docker_ref)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-D",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-U", docker_usr,
                "-T", docker_tkt,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=True,
        )
        assert "usage: weaver deploy" in lines[0]
        assert lines[-1] == "weaver deploy: error: argument -T/--token: not allowed with argument -U/--username"

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-P", docker_pwd,
                "-T", docker_tkt,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=True,
        )
        assert "usage: weaver deploy" in lines[0]
        assert lines[-1] == "weaver deploy: error: argument -T/--token: not allowed with argument -P/--password"

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-U", docker_usr,
                "-P", docker_pwd,
                "-T", docker_tkt,  # should not pass this time as (username + password: valid) while ignoring token
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=True,
        )
        assert "usage: weaver deploy" in lines[0]
        assert (  # any first that disallows
            lines[-1] == "weaver deploy: error: argument -T/--token: not allowed with argument -U/--username" or
            lines[-1] == "weaver deploy: error: argument -T/--token: not allowed with argument -P/--password"
        )

    def test_deploy_docker_auth_username_or_password_missing_invalid(self):
        """
        Test that username/password cannot be used on their own for docker login, even if token is not provided.

        All parameter values are themselves valid, only their combination that are not.
        """
        p_id = self.fully_qualified_test_process_name()
        docker_reg = "fake.repo"
        docker_img = "org/project/private-image:latest"
        docker_ref = f"{docker_reg}/{docker_img}"
        docker_usr = "random"
        docker_pwd = str(uuid.uuid4())
        package = self.retrieve_payload("Echo", "package", local=True)
        package = self.add_docker_pull_ref(package, docker_ref)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-D",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-U", docker_usr,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=True,
        )
        assert "usage: weaver deploy" in lines[0]
        assert lines[-1] == "weaver deploy: error: argument -U/--username: must be combined with -P/--password"

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", p_id,
                "--cwl", package,
                "-P", docker_pwd,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=True,
        )
        assert "usage: weaver deploy" in lines[0]
        assert lines[-1] == "weaver deploy: error: argument -U/--username: must be combined with -P/--password"

    def test_deploy_payload_body_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}deploy-body-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload["executionUnit"][0] = {"unit": package}

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", test_id,
                "-b", json.dumps(payload),  # literal JSON string accepted for CLI
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_file_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}deploy-file-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload["executionUnit"][0] = {"href": package}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cwl") as body_file:
            json.dump(payload, body_file)
            body_file.flush()
            body_file.seek(0)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # weaver
                    "deploy",
                    "-u", self.url,
                    "-p", test_id,
                    "-b", body_file.name,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
            assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_inject_cwl_body(self):
        test_id = f"{self.test_process_prefix}deploy-body-with-cwl-body"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload.pop("executionUnit", None)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", test_id,
                "--body", json.dumps(payload),  # literal JSON string accepted for CLI
                "--cwl", json.dumps(package),   # literal JSON string accepted for CLI
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_inject_cwl_file(self):
        test_id = f"{self.test_process_prefix}deploy-body-with-cwl-file"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload.pop("executionUnit", None)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", test_id,
                "--body", json.dumps(payload),  # literal JSON string accepted for CLI
                "--cwl", package,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_process_info_merged(self):
        """
        Validate that both process information formats are detected and merged accordingly.

        Because OLD/OGC formats allow either ``processDescription.{info}`` or ``processDescription.process.{info}``,
        both structures must be considered if provided by the user. Failing to do so, the :term:`CLI` could inject the
        desired :term:`Process` ID (via ``-p``) in the wrong place, which would discard the rest of the user-provided
        information when performing the ``OneOf()`` schema validation of the body.
        """
        in_oas = {"type": "string", "format": "uri"}
        out_oas = {"type": "object", "properties": {"data": {"type": "object", "additionalProperties": True}}}
        io_fmt = ContentType.IMAGE_GEOTIFF
        cwl_ns, cwl_fmt = get_cwl_file_format(io_fmt)
        process = {
            "inputs": {"message": {"schema": in_oas}},
            "outputs": {"output": {"schema": out_oas}}
        }
        payload_direct = {"processDescription": process}
        payload_nested = {"processDescription": {"process": process}}

        # use both combination of process description to validate resolution
        for i, payload in enumerate([payload_direct, payload_nested]):
            test_id = f"{self.test_process_prefix}deploy-body-with-process-info-{i}"
            package = self.retrieve_payload("Echo", "package", local=True)
            package["outputs"]["output"]["format"] = cwl_fmt
            package["$namespaces"] = cwl_ns

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # weaver
                    "deploy",
                    "-u", self.url,
                    "-p", test_id,
                    "--body", json.dumps(payload),
                    "--cwl", json.dumps(package),
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
            assert any("\"deploymentDone\": true" in line for line in lines)

            # validate result
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # weaver
                    "describe",
                    "-u", self.url,
                    "-p", test_id,
                    "-F", OutputFormat.JSON_RAW,  # single line JSON literal
                    "-S", ProcessSchema.OGC,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            data = json.loads(lines[0])
            in_schema = data["inputs"]["message"]["schema"]
            out_schema = data["outputs"]["output"]["schema"]
            out_formats = data["outputs"]["output"]["formats"]
            out_cwl_type = {"contentMediaType": io_fmt, "contentEncoding": "base64",
                            "type": "string", "format": "binary"}
            out_json_type = {"contentMediaType": ContentType.APP_JSON, "type": "string"}
            out_oas_oneof = {"oneOf": [out_cwl_type, out_json_type, out_oas]}
            out_cwl_fmt = {"default": False, "mediaType": io_fmt}
            out_oas_fmt = {"default": True, "mediaType": ContentType.APP_JSON}
            out_any_fmt = [out_cwl_fmt, out_oas_fmt]
            # if any of the below definitions don't include user-provided information,
            # CLI did not combine it as intended prior to sending deployment request
            assert in_schema == in_oas  # injected by user provided process description
            assert out_schema == out_oas_oneof  # combined from user and auto-resolved definitions
            assert out_formats == out_any_fmt  # auto-resolved from CWL

    def test_describe(self):
        # prints formatted JSON ProcessDescription over many lines
        proc = self.test_process["Echo"]
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "describe",
                "-u", self.url,
                "-p", proc,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        # ignore indents of fields from formatted JSON content
        assert any(f"\"id\": \"{proc}\"" in line for line in lines)
        assert any("\"inputs\": {" in line for line in lines)
        assert any("\"outputs\": {" in line for line in lines)

    def test_describe_no_links(self):
        # prints formatted JSON ProcessDescription over many lines
        proc = self.test_process["Echo"]
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "describe",
                "-u", self.url,
                "-p", proc,
                "-nL",
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        # ignore indents of fields from formatted JSON content
        assert any(f"\"id\": \"{proc}\"" in line for line in lines)
        assert any("\"inputs\": {" in line for line in lines)
        assert any("\"outputs\": {" in line for line in lines)
        assert all("\"links\":" not in line for line in lines)

    def test_execute_inputs_capture(self):
        """
        Verify that specified inputs are captured for a limited number of 1 item per ``-I`` option.
        """
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'",  # if -I not capture as indented, URL after would be combined in it
                    "-M",
                    "-T", 10,
                    "-W", 1,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"status\": \"{Status.SUCCEEDED}\"" in line for line in lines)

    def test_execute_manual_monitor(self):
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'"
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            # ignore indents of fields from formatted JSON content
            assert any(f"\"processID\": \"{proc}\"" in line for line in lines)
            assert any("\"jobID\": \"" in line for line in lines)
            assert any("\"location\": \"" in line for line in lines)
            job_loc = [line for line in lines if "location" in line][0]
            job_ref = [line for line in job_loc.split("\"") if line][-1]
            job_id = str(job_ref).rsplit("/", 1)[-1]

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "monitor",
                    "-j", job_ref,
                    "-T", 10,
                    "-W", 1,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )

            assert any(f"\"jobID\": \"{job_id}\"" in line for line in lines)
            assert any(f"\"status\": \"{Status.SUCCEEDED}\"" in line for line in lines)
            assert any(f"\"href\": \"{job_ref}/results\"" in line for line in lines)
            assert any("\"rel\": \"http://www.opengis.net/def/rel/ogc/1.0/results\"" in line for line in lines)

    def test_execute_auto_monitor(self):
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'",
                    "-M",
                    "-T", 10,
                    "-W", 1
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any("\"jobID\": \"" in line for line in lines)  # don't care value, self-handled
            assert any(f"\"status\": \"{Status.SUCCEEDED}\"" in line for line in lines)
            assert any("\"rel\": \"http://www.opengis.net/def/rel/ogc/1.0/results\"" in line for line in lines)

    def test_execute_result_by_reference(self):
        """
        Validate option to obtain outputs by reference returned with ``Link`` header.

        Result obtained is validated both with API outputs and extended auto-download outputs.
        """
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            out_tmp = stack_exec.enter_context(tempfile.TemporaryDirectory())
            stack_exec.enter_context(mocked_wps_output(self.settings))
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)

            msg = "TEST MESSAGE!"
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", f"message='{msg}'",
                    "-R", "output",
                    "-M",
                    "-T", 10,
                    "-W", 1,
                    "-F", OutputFormat.YAML,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert "jobID: " in lines[0]  # don't care value, self-handled
            assert any(f"status: {Status.SUCCEEDED}" in line for line in lines)

            job_id = lines[0].split(":")[-1].strip()
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "results",
                    "-u", self.url,
                    "-j", job_id,
                    "-wH",   # must display header to get 'Link'
                    "-F", OutputFormat.YAML,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            sep = lines.index("---")
            headers = lines[:sep]
            content = lines[sep+1:-1]  # ignore final newline
            assert len(headers) and any("Link:" in hdr for hdr in headers)
            assert content == ["null"], "When no download involved, body should be the original no-content results."

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "results",
                    "-u", self.url,
                    "-j", job_id,
                    "-wH",   # must display header to get 'Link'
                    "-F", OutputFormat.YAML,
                    "-D",
                    "-O", out_tmp
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            sep = lines.index("---")
            headers = lines[:sep]
            content = lines[sep+1:]

            assert len(content), "Content should have been populated from download to provide downloaded file paths."
            link = None
            for header in headers:
                if "Link:" in header:
                    link = header.split(":", 1)[-1].strip()
                    break
            assert link
            link = link.split(";")[0].strip("<>")
            path = map_wps_output_location(link, self.settings, url=False)
            assert os.path.isfile(path), "Original file results should exist in job output dir."

            # path should be in contents as well, pre-resolved within download dir (not same as job output dir)
            assert len([line for line in content if "path:" in line]) == 1
            path = None
            for line in content:
                if "path:" in line:
                    path = line.split(":", 1)[-1].strip()
                    break
            assert path
            assert path.startswith(out_tmp)
            assert os.path.isfile(path)
            with open(path, mode="r", encoding="utf-8") as file:
                data = file.read()
            assert msg in data  # technically, output is log of echoed input message, so not exactly equal

    def test_execute_help_details(self):
        """
        Verify that formatting of the execute operation help provides multiple paragraphs with more details.
        """
        lines = run_command(
            [
                # "weaver",
                "execute",
                "--help",
            ],
            trim=False,
            entrypoint=weaver_cli,
        )
        start = -1
        end = -1
        for index, line in enumerate(lines):
            if "-I INPUTS, --inputs INPUTS" in line:
                start = index + 1
            if "Example:" in line:
                end = index
                break
        assert 0 < start < end
        indent = "  " * lines[start].count("  ")
        assert len(indent) > 4
        assert all(line.startswith(indent) for line in lines[start:end])
        assert len([line for line in lines[start:end] if line == indent]) > 3, "Inputs should have a few paragraphs."

    def test_execute_invalid_format(self):
        proc = self.test_process["Echo"]
        bad_input_value = "'this is my malformed message'"  # missing '<id>=' portion
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "execute",
                "-u", self.url,
                "-p", proc,
                "-I", bad_input_value,
                "-M",
                "-T", 10,
                "-W", 1
            ],
            trim=False,
            entrypoint=weaver_cli,
            expect_error=True,
            only_local=True,
        )
        assert any(bad_input_value in line for line in lines)

    def test_jobs(self):
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert any("jobs" in line for line in lines)
        assert any("total" in line for line in lines)
        assert any("limit" in line for line in lines)

    def test_jobs_no_links_limit_status_filters(self):
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
                "-S", Status.SUCCEEDED,
                "-N", 1,
                "-nL",
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert len(lines) > 1, "Should be automatically indented with readable format"
        text = "".join(lines)
        body = json.loads(text)
        assert isinstance(body["jobs"], list) and len(body["jobs"]) == 1
        assert isinstance(body["jobs"][0], str)  # JobID
        assert body["page"] == 0
        assert body["limit"] == 1
        assert "total" in body and isinstance(body["total"], int)  # ignore actual variable amount
        assert "links" not in body

    def test_jobs_no_links_nested_detail(self):
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
                "-S", Status.SUCCEEDED,
                "-D",   # when details active, each job lists its own links
                "-nL",  # unless links are requested to be removed (top-most and nested ones)
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert len(lines) > 1, "Should be automatically indented with readable format"
        text = "".join(lines)
        body = json.loads(text)
        assert isinstance(body["jobs"], list)
        assert all(isinstance(job, dict) for job in body["jobs"]), "Jobs should be JSON objects when details requested"
        assert all("links" not in job for job in body["jobs"])
        assert "links" not in body

    def test_jobs_filter_status_multi(self):
        self.job_store.clear_jobs()
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.status = Status.SUCCEEDED
        job_s = self.job_store.update_job(job)
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.status = Status.FAILED
        job_f = self.job_store.update_job(job)
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.status = Status.ACCEPTED
        job_a = self.job_store.update_job(job)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
                "-S", Status.SUCCEEDED, Status.ACCEPTED,
                "-D",
                "-nL",  # unless links are requested to be removed (top-most and nested ones)
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert len(lines) > 1, "Should be automatically indented with readable format"
        text = "".join(lines)
        body = json.loads(text)
        assert isinstance(body["jobs"], list)
        assert len(body["jobs"])
        assert not any(_job["jobID"] == str(job_f.uuid) for _job in body["jobs"])
        assert all(job["status"] in [Status.SUCCEEDED, Status.ACCEPTED] for job in body["jobs"])
        jobs_accept = list(filter(lambda _job: _job["status"] == Status.ACCEPTED, body["jobs"]))
        jobs_success = list(filter(lambda _job: _job["status"] == Status.SUCCEEDED, body["jobs"]))
        assert len(jobs_accept) == 1 and jobs_accept[0]["jobID"] == str(job_a.uuid)
        assert len(jobs_success) == 1 and jobs_success[0]["jobID"] == str(job_s.uuid)

    def test_jobs_filter_tags(self):
        self.job_store.clear_jobs()
        job1 = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job1.tags = ["test1", "test-share"]
        job1 = self.job_store.update_job(job1)
        job2 = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job2.tags = ["test2", "test-share"]
        job2 = self.job_store.update_job(job2)
        job3 = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job3.tags = ["test3"]
        job3 = self.job_store.update_job(job3)
        jobs = [job1, job2, job3]

        # note: tags are not 'oneOf', they are 'allOf'
        for test_tags, expect_jobs in [
            (["test1"], [job1]),
            (["test2"], [job2]),
            (["test3"], [job3]),
            (["test1,test2"], []),
            (["test1", "test2"], []),
            (["test-share"], [job1, job2]),
            (["test1,test-share"], [job1]),
            (["test1", "test-share"], [job1]),
            (["test1", "test3"], []),
            (["test-share,test3"], []),
            (["test-share", "test3"], []),
        ]:
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "jobs",
                    "-u", self.url,
                    "-fT", *test_tags,
                    "-nL",  # unless links are requested to be removed (top-most and nested ones)
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert lines
            assert len(lines) > 1, "Should be automatically indented with readable format"
            text = "".join(lines)
            body = json.loads(text)
            assert isinstance(body["jobs"], list)
            self.assert_equal_with_jobs_diffs(body["jobs"], expect_jobs, test_tags, jobs=jobs)

    @mocked_remote_server_requests_wps1([
        "https://random.com",
        resources.load_resource(resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML).replace(
            "<ows:Identifier>test-remote-process-wps1</ows:Identifier>",
            f"<ows:Identifier>{TestWeaverClientBase.test_process_prefix}Echo</ows:Identifier>",
        ),
        [
            resources.load_resource(resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML).replace(
                "<ows:Identifier>test-remote-process-wps1</ows:Identifier>",
                f"<ows:Identifier>{TestWeaverClientBase.test_process_prefix}Echo</ows:Identifier>",
            )
        ],
    ], data=True)
    def test_jobs_filter_process_provider(self):
        # process/provider references must be actual definitions in db, see setUp
        svc = self.service_store.save_service(Service(name="random", url="https://random.com", public=True))
        proc = self.test_process["Echo"]
        job1 = self.job_store.save_job(task_id=uuid.uuid4(), process=proc, access=Visibility.PUBLIC)
        job2 = self.job_store.save_job(task_id=uuid.uuid4(), process=proc, service=svc.name,
                                       access=Visibility.PUBLIC)
        self.job_store.save_job(task_id=uuid.uuid4(), process="CatFile", access=Visibility.PUBLIC)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
                "-fP", job1.process,
                "-nL",  # unless links are requested to be removed (top-most and nested ones)
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert len(lines) > 1, "Should be automatically indented with readable format"
        text = "".join(lines)
        body = json.loads(text)
        assert isinstance(body["jobs"], list)
        assert len(body["jobs"]) == 2
        assert sorted(body["jobs"]) == sorted([str(job1.uuid), str(job2.uuid)])

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
                "-fP", job1.process,
                "-fS", job2.service,
                "-nL",  # unless links are requested to be removed (top-most and nested ones)
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert len(lines) > 1, "Should be automatically indented with readable format"
        text = "".join(lines)
        body = json.loads(text)
        assert isinstance(body["jobs"], list)
        assert len(body["jobs"]) == 1
        assert body["jobs"] == [str(job2.uuid)]

    def test_output_format_json_pretty(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        for format_option in [[], ["-F", OutputFormat.JSON_STR]]:
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "status",
                    "-j", job_url,
                ] + format_option,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert len(lines) > 1, "should be indented, pretty printed"
            assert lines[0].startswith("{")
            assert lines[-1].endswith("}")
            assert any("jobID" in line for line in lines)

    def test_output_format_json_pretty_and_headers(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.JSON_STR,
                "-wH",
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0] == "Headers:"
        sep = "---"
        sep_pos = lines.index(sep)
        assert any("Content-Type:" in line for line in lines[1:sep_pos])
        result = lines[sep_pos+1:]
        assert len(result) > 1, "should be indented, pretty printed"
        assert result[0].startswith("{")
        assert result[-1].endswith("}")
        assert any("jobID" in line for line in result)

    def test_output_format_json_raw(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        for format_option in [["-F", OutputFormat.JSON], ["-F", OutputFormat.JSON_RAW]]:
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "status",
                    "-j", job_url,
                ] + format_option,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert len(lines) == 1, "should NOT be indented, raw data directly in one block"
            assert lines[0].startswith("{")
            assert lines[0].endswith("}")
            assert "jobID" in lines[0]

    def test_output_format_yaml_pretty(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.YAML,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0] == f"jobID: {self.test_job.id}"

    def test_output_format_xml_pretty(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.XML_STR
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0].startswith("<?xml")
        assert lines[1].startswith("<result>")
        assert lines[-1].endswith("</result>")
        assert any("jobID" in line for line in lines)

    def test_output_format_xml_pretty_and_headers(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.XML_STR,
                "-wH"
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0] == "Headers:"
        sep = "---"
        sep_pos = lines.index(sep)
        assert any("Content-Type:" in line for line in lines[1:sep_pos])
        result = lines[sep_pos+1:]
        assert len(result) > 1, "should be indented, pretty printed"
        assert result[0].startswith("<?xml")
        assert result[1].startswith("<result>")
        assert result[-1].endswith("</result>")
        assert any("jobID" in line for line in result)

    def test_output_format_xml_raw(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.XML_RAW
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) == 1, "should NOT be indented, raw data directly in one block"
        assert lines[0].startswith("<?xml")
        assert lines[0].endswith("</result>")

    def test_job_logs(self):
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.save_log(message="test start", progress=0, status=Status.ACCEPTED)
        job.save_log(message="test run", progress=50, status=Status.RUNNING)
        job.save_log(message="test done", progress=100, status=Status.SUCCEEDED)
        job = self.job_store.update_job(job)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "logs",
                "-u", self.url,
                "-j", str(job.id),
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) == 5
        assert lines[0] == "["
        assert f"0% {Status.ACCEPTED}" in lines[1]
        assert f"50% {Status.RUNNING}" in lines[2]
        assert f"100% {Status.SUCCEEDED}" in lines[3]
        assert lines[4] == "]"

    def test_job_exceptions(self):
        xml_error = resources.load_example("wps_access_forbidden_response.xml", xml=True)
        wps_error = WPSException(xml_error.xpath(".//ows:Exception", namespaces={"ows": DEFAULT_OWS_NAMESPACE})[0])
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.save_log(message="test start", progress=0, status=Status.ACCEPTED)
        job.save_log(message="test run", progress=50, status=Status.RUNNING)
        job.save_log(message="test error", progress=80, status=Status.FAILED, errors=ValueError("test-error"))
        job.save_log(message="test error", progress=80, status=Status.FAILED, errors=wps_error)
        job = self.job_store.update_job(job)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "exceptions",
                "-u", self.url,
                "-j", str(job.id),
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines)
        text = "".join(lines)
        body = json.loads(text)
        assert body == [
            "test-error",
            {"Code": "AccessForbidden", "Locator": "service", "Text": "Access to service is forbidden."}
        ]

    def test_job_statistics(self):
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.statistics = resources.load_example("job_statistics.json")
        job.status = Status.SUCCEEDED  # error if not completed
        job = self.job_store.update_job(job)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "statistics",
                "-u", self.url,
                "-j", str(job.id),
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines)
        text = "".join(lines)
        body = json.loads(text)
        assert body == job.statistics

    def test_job_info_wrong_status(self):
        # results/statistics must be in success status
        job = self.job_store.save_job(task_id=uuid.uuid4(), process="test-process", access=Visibility.PUBLIC)
        job.statistics = resources.load_example("job_statistics.json")
        job.save_log(message="Some info", status=Status.ACCEPTED, errors=ValueError("failed"))
        job = self.job_store.update_job(job)

        for operation, status, expect in [
            ("results", Status.FAILED, "JobResultsFailed"),
            ("statistics", Status.FAILED, "404 Not Found"),
            # ("exceptions", Status.SUCCEEDED, "404 Not Found"),  # no error, just irrelevant or empty
        ]:
            job.status = status
            job = self.job_store.update_job(job)
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    operation,
                    "-u", self.url,
                    "-j", str(job.id),
                    "-nL",
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
                expect_error=True,
            )
            assert len(lines)
            text = "".join(lines)
            assert expect in text


class TestWeaverClientAuthBase(TestWeaverClientBase):
    auth_app = None  # type: Optional[WebTestApp]
    auth_path = "/auth"
    proxy_path = "/proxy"
    auth_url = classproperty(fget=lambda self: self.url + self.auth_path)
    proxy_url = classproperty(fget=lambda self: self.url + self.proxy_path)

    @classmethod
    def setup_auth_app(cls):

        def auth_view(request):
            # type: (AnyRequestType) -> AnyResponseType
            token = str(uuid.uuid4())
            request.registry.settings.setdefault("auth", set())
            request.registry.settings["auth"].add(token)
            return HTTPOk(json={"access_token": token})

        def proxy_view(request):
            # type: (AnyRequestType) -> AnyResponseType
            auth = request.headers.get("Authorization")  # should be added by a auth-handler called inline of operation
            if not auth:
                return HTTPUnauthorized()
            token = auth.split(" ")[-1]
            allow = request.registry.settings.get("auth", set())
            if token not in allow:
                return HTTPForbidden()
            path = request.path_qs.split(cls.proxy_path, 1)[-1]
            resp = mocked_sub_requests(cls.app, request.method, path, only_local=True, headers=request.headers)
            return resp

        config = setup_config_from_settings(cls.settings)
        config.add_route(name="auth", pattern=cls.auth_path + "/")  # matcher requires extra slash auto-added
        config.add_route(name="proxy", pattern=cls.proxy_path + "/.*")
        config.add_view(auth_view, name="auth")
        config.add_view(proxy_view, name="proxy")
        cls.auth_app = WebTestApp(config.make_wsgi_app())

        # create client with proxied endpoint
        # do not add auth by default to test unauthorized/forbidden access
        # each CLI/Client operation should provided it explicitly to obtain access using auth token
        cls.client = WeaverClient(cls.proxy_url)

    @classmethod
    def setUpClass(cls):
        super(TestWeaverClientAuthBase, cls).setUpClass()
        cls.setup_auth_app()


class TestWeaverCLIAuthHandler(TestWeaverClientAuthBase):

    def test_describe_auth(self):
        # prints formatted JSON ProcessDescription over many lines
        proc = self.test_process["Echo"]
        desc_opts = [
            # "weaver",
            "describe",
            "-u", self.proxy_url,
            "-p", proc,
        ]
        auth_opts = [
            "--auth-handler", fully_qualified_name(BearerAuthHandler),
            "--auth-url", self.auth_url,
        ]

        # verify that service is 'protected', error to access it without auth parameters
        lines = mocked_sub_requests(
            self.auth_app, run_command, desc_opts,
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=True,
        )
        assert any("401 Unauthorized" in line for line in lines)

        # validate successful access when auth is added with handler
        lines = mocked_sub_requests(
            self.auth_app, run_command, desc_opts + auth_opts,
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
            expect_error=False,
        )
        # ignore indents of fields from formatted JSON content
        assert any(f"\"id\": \"{proc}\"" in line for line in lines)
        assert any("\"inputs\": {" in line for line in lines)
        assert any("\"outputs\": {" in line for line in lines)
