import contextlib
import os
import tempfile

import pytest
from owslib.wps import ComplexDataInput, WPSExecution

from tests.functional.utils import WpsConfigBase
from tests.utils import mocked_execute_process, mocked_sub_requests
from weaver import xml_util
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_RESPONSE_DOCUMENT, EXECUTE_TRANSMISSION_MODE_REFERENCE
from weaver.formats import CONTENT_TYPE_ANY_XML, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_PLAIN
from weaver.processes.wps_package import CWL_REQUIREMENT_APP_DOCKER
from weaver.utils import get_any_value, str2bytes
from weaver.wps.utils import get_wps_url


@pytest.mark.functional
class WpsPackageDockerAppTest(WpsConfigBase):
    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.url": "http://localhost",
            "weaver.wps": True,
            "weaver.wps_output": True,
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_dir": "/tmp",  # nosec: B108 # don't care hardcoded for test
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
        }
        super(WpsPackageDockerAppTest, cls).setUpClass()
        cls.out_key = "output"
        # use default file generated by Weaver/CWL
        # command 'cat' within docker application will dump file contents to standard output captured by it
        cls.out_file = "stdout.log"
        cls.process_id = cls.__name__
        cls.deploy_docker_process()

    @classmethod
    def get_package(cls):
        return {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "cat",
            "requirements": {
                CWL_REQUIREMENT_APP_DOCKER: {
                    "dockerPull": "debian:stretch-slim"
                }
            },
            "inputs": [
                {"id": "file", "type": "File", "inputBinding": {"position": 1}},
            ],
            "outputs": [
                {"id": cls.out_key, "type": "File", "outputBinding": {"glob": cls.out_file}},
            ]
        }

    @classmethod
    def get_deploy_body(cls):
        cwl = cls.get_package()
        body = {
            "processDescription": {
                "process": {"id": cls.process_id}
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [{"unit": cwl}],
        }
        return body

    @classmethod
    def deploy_docker_process(cls):
        body = cls.get_deploy_body()
        info = cls.deploy_process(body)
        return info

    def validate_outputs(self, job_id, result_payload, outputs_payload, result_file_content):
        # get generic details
        wps_uuid = str(self.job_store.fetch_by_id(job_id).wps_id)
        wps_out_path = "{}{}".format(self.settings["weaver.url"], self.settings["weaver.wps_output_path"])
        wps_output = "{}/{}/{}".format(wps_out_path, wps_uuid, self.out_file)

        # --- validate /results path format ---
        assert len(result_payload) == 1
        assert isinstance(result_payload, dict)
        assert isinstance(result_payload[self.out_key], dict)
        result_values = {out_id: get_any_value(result_payload[out_id]) for out_id in result_payload}
        assert result_values[self.out_key] == wps_output

        # --- validate /outputs path format ---

        # check that output is HTTP reference to file
        output_values = {out["id"]: get_any_value(out) for out in outputs_payload["outputs"]}
        assert len(output_values) == 1
        assert output_values[self.out_key] == wps_output

        # check that actual output file was created in expected location along with XML job status
        wps_outdir = self.settings["weaver.wps_output_dir"]
        wps_out_file = os.path.join(wps_outdir, job_id, self.out_file)
        assert not os.path.exists(os.path.join(wps_outdir, self.out_file)), \
            "File is expected to be created in sub-directory of Job ID, not directly in WPS output directory."
        # job log, XML status and output directory can be retrieved with both Job UUID and underlying WPS UUID reference
        assert os.path.isfile(os.path.join(wps_outdir, "{}.log".format(wps_uuid)))
        assert os.path.isfile(os.path.join(wps_outdir, "{}.xml".format(wps_uuid)))
        assert os.path.isfile(os.path.join(wps_outdir, wps_uuid, self.out_file))
        assert os.path.isfile(os.path.join(wps_outdir, "{}.log".format(job_id)))
        assert os.path.isfile(os.path.join(wps_outdir, "{}.xml".format(job_id)))
        assert os.path.isfile(wps_out_file)

        # validate content
        with open(wps_out_file) as res_file:
            assert res_file.read() == result_file_content

    def test_deployed_process_schemas(self):
        """
        Validate that resulting schemas from deserialization correspond to original package and process definitions.
        """
        # process already deployed by setUpClass
        body = self.get_deploy_body()
        process = self.process_store.fetch_by_id(self.process_id)
        assert process.package == body["executionUnit"][0]["unit"]
        assert process.payload == body

    def test_execute_wps_rest_resp_json(self):
        """
        Test validates that basic Docker application runs successfully, fetching the reference as needed.

        The job execution is launched using the WPS-REST endpoint for this test.
        Both the request body and response content are JSON.

        .. seealso::
            - :meth:`test_execute_wps_kvp_get_resp_xml`
            - :meth:`test_execute_wps_kvp_get_resp_json`
            - :meth:`test_execute_wps_xml_post_resp_xml`
            - :meth:`test_execute_wps_xml_post_resp_json`
        """

        test_content = "Test file in Docker - WPS-REST job endpoint"
        with contextlib.ExitStack() as stack_exec:
            # setup
            dir_name = tempfile.gettempdir()
            tmp_path = tempfile.NamedTemporaryFile(dir=dir_name, mode="w", suffix=".txt")
            tmp_file = stack_exec.enter_context(tmp_path)  # noqa
            tmp_file.write(test_content)
            tmp_file.seek(0)
            exec_body = {
                "mode": EXECUTE_MODE_ASYNC,
                "response": EXECUTE_RESPONSE_DOCUMENT,
                "inputs": [
                    {"id": "file", "href": tmp_file.name},
                ],
                "outputs": [
                    {"id": self.out_key, "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE},
                ]
            }
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)

            # execute
            proc_url = "/processes/{}/jobs".format(self.process_id)
            resp = mocked_sub_requests(self.app, "post_json", proc_url,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], "Failed with: [{}]\nReason:\n{}".format(resp.status_code, resp.json)
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

            # job monitoring
            results = self.monitor_job(status_url)
            outputs = self.get_outputs(status_url)

        self.validate_outputs(job_id, results, outputs, test_content)

    def wps_execute(self, version, accept):
        wps_url = get_wps_url(self.settings)
        if version == "1.0.0":
            test_content = "Test file in Docker - WPS KVP"
            wps_method = "GET"
        elif version == "2.0.0":
            test_content = "Test file in Docker - WPS XML"
            wps_method = "POST"
        else:
            raise ValueError("Invalid WPS version: {}".format(version))
        test_content += " {} request - Accept {}".format(wps_method, accept.split("/")[-1].upper())

        with contextlib.ExitStack() as stack_exec:
            # setup
            dir_name = tempfile.gettempdir()
            tmp_path = tempfile.NamedTemporaryFile(dir=dir_name, mode="w", suffix=".txt")
            tmp_file = stack_exec.enter_context(tmp_path)  # noqa
            tmp_file.write(test_content)
            tmp_file.seek(0)
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)

            # execute
            if version == "1.0.0":
                wps_inputs = ["file={}@mimeType={}".format(tmp_file.name, CONTENT_TYPE_TEXT_PLAIN)]
                wps_params = {
                    "service": "WPS",
                    "request": "Execute",
                    "version": version,
                    "identifier": self.process_id,
                    "DataInputs": wps_inputs,
                }
                wps_headers = {"Accept": accept}
                wps_data = None
            else:
                wps_inputs = [("file", ComplexDataInput(tmp_file.name, mimeType=CONTENT_TYPE_TEXT_PLAIN))]
                wps_outputs = [(self.out_key, True)]  # as reference
                wps_exec = WPSExecution(version=version, url=wps_url)
                wps_req = wps_exec.buildRequest(self.process_id, wps_inputs, wps_outputs)
                wps_data = xml_util.tostring(wps_req)
                wps_headers = {"Accept": accept, "Content-Type": CONTENT_TYPE_APP_XML}
                wps_params = None
            resp = mocked_sub_requests(self.app, wps_method, wps_url,
                                       params=wps_params, data=wps_data, headers=wps_headers, only_local=True)
            assert resp.status_code in [200, 201], \
                "Failed with: [{}]\nTest: [{}]\nReason:\n{}".format(resp.status_code, test_content, resp.text)

            # parse response status
            if accept == CONTENT_TYPE_APP_XML:
                assert resp.content_type in CONTENT_TYPE_ANY_XML, test_content
                xml_body = xml_util.fromstring(str2bytes(resp.text))
                status_url = xml_body.get("statusLocation")
                job_id = status_url.split("/")[-1]
            elif accept == CONTENT_TYPE_APP_JSON:
                assert resp.content_type == CONTENT_TYPE_APP_JSON, test_content
                status_url = resp.json["location"]
                job_id = resp.json["jobID"]
            assert status_url
            assert job_id

            # job monitoring
            results = self.monitor_job(status_url)
            outputs = self.get_outputs(status_url)

        self.validate_outputs(job_id, results, outputs, test_content)

    def test_execute_wps_kvp_get_resp_xml(self):
        """
        Test validates that basic Docker application runs successfully, fetching the reference as needed.

        The job is launched using the WPS Execute request with Key-Value Pairs (KVP) and GET method.
        The request is done with query parameters, and replies by default with response XML content.

        .. seealso::
            - :meth:`test_execute_wps_rest_resp_json`
            - :meth:`test_execute_wps_kvp_get_resp_json`
            - :meth:`test_execute_wps_xml_post_resp_xml`
            - :meth:`test_execute_wps_xml_post_resp_json`
        """
        self.wps_execute("1.0.0", CONTENT_TYPE_APP_XML)

    def test_execute_wps_kvp_get_resp_json(self):
        """
        Test validates that basic Docker application runs successfully, fetching the reference as needed.

        Does the same operation as :meth:`test_execute_wps_kvp_get_resp_xml`, but use ``Accept`` header of JSON
        which should return a response with the same contents as if called directly via WPS-REST endpoint.

        .. seealso::
            - :meth:`test_execute_wps_rest_resp_json`
            - :meth:`test_execute_wps_kvp_get_resp_xml`
            - :meth:`test_execute_wps_xml_post_resp_xml`
            - :meth:`test_execute_wps_xml_post_resp_json`
        """
        self.wps_execute("1.0.0", CONTENT_TYPE_APP_JSON)

    def test_execute_wps_xml_post_resp_xml(self):
        """
        Test validates that basic Docker application runs successfully, fetching the reference as needed.

        The job is launched using the WPS Execute request with POST request method and XML content.

        .. seealso::
            - :meth:`test_execute_wps_rest_resp_json`
            - :meth:`test_execute_wps_kvp_get_resp_xml`
            - :meth:`test_execute_wps_kvp_get_resp_json`
            - :meth:`test_execute_wps_xml_post_resp_json`
        """
        self.wps_execute("2.0.0", CONTENT_TYPE_APP_XML)

    def test_execute_wps_xml_post_resp_json(self):
        """
        Test validates that basic Docker application runs successfully, fetching the reference as needed.

        Does the same operation as :meth:`test_execute_wps_xml_post_resp_xml`, but use ``Accept`` header of JSON
        which should return a response with the same contents as if called directly via WPS-REST endpoint.

        .. seealso::
            - :meth:`test_execute_wps_rest_resp_json`
            - :meth:`test_execute_wps_kvp_get_resp_xml`
            - :meth:`test_execute_wps_kvp_get_resp_json`
            - :meth:`test_execute_wps_xml_post_resp_json`
        """
        self.wps_execute("2.0.0", CONTENT_TYPE_APP_JSON)
