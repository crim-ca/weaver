import logging
import warnings
from copy import deepcopy
from time import sleep
from typing import TYPE_CHECKING

from pyramid.httpexceptions import (
    HTTPConflict,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPOk,
    HTTPUnauthorized
)
from pyramid.settings import asbool

from weaver import status
from weaver.exceptions import PackageExecutionError
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_RESPONSE_DOCUMENT, EXECUTE_TRANSMISSION_MODE_REFERENCE
from weaver.formats import CONTENT_TYPE_APP_FORM, CONTENT_TYPE_APP_JSON
from weaver.processes import opensearch
from weaver.processes.constants import OPENSEARCH_LOCAL_FILE_SCHEME
from weaver.processes.sources import get_data_source_from_url, retrieve_data_source_url
from weaver.processes.utils import map_progress
from weaver.processes.wps_process_base import WpsProcessInterface
from weaver.utils import (
    fetch_file,
    get_any_id,
    get_any_message,
    get_any_value,
    get_job_log_msg,
    get_log_monitor_msg,
    pass_http_error,
    request_extra
)
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.warning import MissingParameterWarning
from weaver.wps.utils import map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import List, Union

    from pywps.app import WPSRequest

    from weaver.typedefs import JSON, UpdateStatusPartialFunction

LOGGER = logging.getLogger(__name__)

REMOTE_JOB_PROGRESS_PROVIDER = 1
REMOTE_JOB_PROGRESS_DEPLOY = 2
REMOTE_JOB_PROGRESS_VISIBLE = 3
REMOTE_JOB_PROGRESS_REQ_PREP = 5
REMOTE_JOB_PROGRESS_EXECUTION = 9
REMOTE_JOB_PROGRESS_MONITORING = 10
REMOTE_JOB_PROGRESS_FETCH_OUT = 90
REMOTE_JOB_PROGRESS_COMPLETED = 100


class Wps3Process(WpsProcessInterface):
    def __init__(self,
                 step_payload,      # type: JSON
                 joborder,          # type: JSON
                 process,           # type: str
                 request,           # type: WPSRequest
                 update_status,     # type: UpdateStatusPartialFunction
                 ):
        super(Wps3Process, self).__init__(request)
        self.provider = None    # overridden if data source properly resolved
        self.update_status = lambda _message, _progress, _status: update_status(
            self.provider, _message, _progress, _status)
        self.provider, self.url, self.deploy_body = self.resolve_data_source(step_payload, joborder)
        self.process = process

    def resolve_data_source(self, step_payload, joborder):
        try:
            # Presume that all EOImage given as input can be resolved to the same ADES
            # So if we got multiple inputs or multiple values for an input, we take the first one as reference
            eodata_inputs = opensearch.get_eo_images_ids_from_payload(step_payload)
            data_url = ""  # data_source will be set to the default ADES if no EOImages (anything but `None`)
            if eodata_inputs:
                step_payload = opensearch.alter_payload_after_query(step_payload)
                value = joborder[eodata_inputs[0]]
                if isinstance(value, list):
                    value = value[0]  # Use the first value to determine the data source
                data_url = value["location"]
                reason = "(ADES based on {0})".format(data_url)
            else:
                reason = "(No EOImage -> Default ADES)"
            data_source = get_data_source_from_url(data_url)
            deploy_body = step_payload
            url = retrieve_data_source_url(data_source)
        except (IndexError, KeyError) as exc:
            raise PackageExecutionError("Failed to save package outputs. [{!r}]".format(exc))

        self.provider = data_source  # fix immediately for `update_status`
        self.update_status("{provider} is selected {reason}.".format(provider=data_source, reason=reason),
                           REMOTE_JOB_PROGRESS_PROVIDER, status.STATUS_RUNNING)

        return data_source, url, deploy_body

    def get_user_auth_header(self):
        # TODO: find a better way to generalize this to Magpie credentials?
        if not asbool(self.settings.get("ades.use_auth_token", True)):
            return {}

        ades_usr = self.settings.get("ades.username", None)
        ades_pwd = self.settings.get("ades.password", None)
        ades_url = self.settings.get("ades.wso2_hostname", None)
        ades_client = self.settings.get("ades.wso2_client_id", None)
        ades_secret = self.settings.get("ades.wso2_client_secret", None)
        access_token = None
        if ades_usr and ades_pwd and ades_url and ades_client and ades_secret:
            ades_body = {
                "grant_type": "password",
                "client_id": ades_client,
                "client_secret": ades_secret,
                "username": ades_usr,
                "password": ades_pwd,
                "scope": "openid",
            }
            ades_headers = {"Content-Type": CONTENT_TYPE_APP_FORM, "Accept": CONTENT_TYPE_APP_JSON}
            ades_access_token_url = "{}/oauth2/token".format(ades_url)
            cred_resp = request_extra("post", ades_access_token_url,
                                      data=ades_body, headers=ades_headers, settings=self.settings)
            cred_resp.raise_for_status()
            if CONTENT_TYPE_APP_JSON not in cred_resp.headers.get("Content-Type"):
                raise HTTPUnauthorized("Cannot retrieve valid access token using credential or ADES configurations.")
            access_token = cred_resp.json().get("access_token", None)
            if not access_token:
                warnings.warn("Could not retrieve valid access token although response is expected to contain one.",
                              MissingParameterWarning)
        else:
            warnings.warn(
                "Could not retrieve at least one of required login parameters: "
                "[ades.username, ades.password, ades.wso2_hostname, ades.wso2_client_id, ades.wso2_client_secret]",
                MissingParameterWarning
            )
        return {"Authorization": "Bearer {}".format(access_token) if access_token else None}

    def is_deployed(self):
        return self.describe_process() is not None

    def is_visible(self):
        # type: (...) -> Union[bool, None]
        """
        Gets the process visibility.

        :returns:
            True/False correspondingly for public/private if visibility is retrievable,
            False if authorized access but process cannot be found,
            None if forbidden access.
        """
        LOGGER.debug("Get process WPS visibility request for [%s]", self.process)
        response = self.make_request(method="GET",
                                     url=self.url + sd.process_visibility_service.path.format(process_id=self.process),
                                     retry=False,
                                     status_code_mock=HTTPUnauthorized.code)
        if response.status_code in (HTTPUnauthorized.code, HTTPForbidden.code):
            return None
        if response.status_code == HTTPNotFound.code:
            return False
        if response.status_code == HTTPOk.code:
            json_body = response.json()
            # FIXME: support for Spacebel, always returns dummy visibility response, enforce deploy with `False`
            if json_body.get("message") == "magic!" or json_body.get("type") == "ok" or json_body.get("code") == 4:
                return False
            return json_body.get("value") == VISIBILITY_PUBLIC
        response.raise_for_status()

    def set_visibility(self, visibility):
        self.update_status("Updating process visibility on remote ADES.",
                           REMOTE_JOB_PROGRESS_VISIBLE, status.STATUS_RUNNING)
        path = self.url + sd.process_visibility_service.path.format(process_id=self.process)
        user_headers = deepcopy(self.headers)
        user_headers.update(self.get_user_auth_header())

        LOGGER.debug("Update process WPS visibility request for [%s] at [%s]", self.process, path)
        response = self.make_request(method="PUT",
                                     url=path,
                                     json={"value": visibility},
                                     retry=False,
                                     status_code_mock=HTTPOk.code)
        response.raise_for_status()

    def describe_process(self):
        path = self.url + sd.process_service.path.format(process_id=self.process)
        LOGGER.debug("Describe process WPS request for [%s] at [%s]", self.process, path)
        response = self.make_request(method="GET",
                                     url=path,
                                     retry=False,
                                     status_code_mock=HTTPOk.code)

        if response.status_code == HTTPOk.code:
            # FIXME: Remove patch for Geomatys ADES (Missing process return a 200 InvalidParameterValue error !)
            if response.content.lower().find("InvalidParameterValue") >= 0:
                return None
            return response.json()
        elif response.status_code == HTTPNotFound.code:
            return None
        # FIXME: Remove patch for Spacebel ADES (Missing process return a 500 error)
        elif response.status_code == HTTPInternalServerError.code:
            return None
        response.raise_for_status()

    def deploy(self):
        self.update_status("Deploying process on remote ADES.",
                           REMOTE_JOB_PROGRESS_DEPLOY, status.STATUS_RUNNING)
        path = self.url + sd.processes_service.path
        user_headers = deepcopy(self.headers)
        user_headers.update(self.get_user_auth_header())

        LOGGER.debug("Deploy process WPS request for [%s] at [%s]", self.process, path)
        response = self.make_request(method="POST", url=path, json=self.deploy_body, retry=True,
                                     status_code_mock=HTTPOk.code)
        response.raise_for_status()

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        # TODO: test
        visible = self.is_visible()
        if not visible:  # includes private visibility and non-existing cases
            if visible is None:
                LOGGER.info("Process [%s] access is unauthorized on [%s] - deploying as admin.", self.process, self.url)
            elif visible is False:
                LOGGER.info("Process [%s] is not deployed on [%s] - deploying.", self.process, self.url)
            # TODO: Maybe always redeploy? What about cases of outdated deployed process?
            try:
                self.deploy()
            except Exception as exc:
                # FIXME: support for Spacebel, avoid conflict error incorrectly handled, remove 500 when fixed
                pass_http_error(exc, [HTTPConflict, HTTPInternalServerError])

        LOGGER.info("Process [%s] enforced to public visibility.", self.process)
        try:
            self.set_visibility(visibility=VISIBILITY_PUBLIC)
        # TODO: support for Spacebel, remove when visibility route properly implemented on ADES
        except Exception as exc:
            pass_http_error(exc, HTTPNotFound)

        self.update_status("Preparing execute request for remote ADES.",
                           REMOTE_JOB_PROGRESS_REQ_PREP, status.STATUS_RUNNING)
        LOGGER.debug("Execute process WPS request for [%s]", self.process)

        execute_body_inputs = []
        execute_req_id = "id"
        execute_req_input_val_href = "href"
        execute_req_input_val_data = "data"
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            if isinstance(workflow_input_value, list):
                for workflow_input_value_item in workflow_input_value:
                    if isinstance(workflow_input_value_item, dict) and "location" in workflow_input_value_item:
                        execute_body_inputs.append({execute_req_id: workflow_input_key,
                                                    execute_req_input_val_href: workflow_input_value_item["location"]})
                    else:
                        execute_body_inputs.append({execute_req_id: workflow_input_key,
                                                    execute_req_input_val_data: workflow_input_value_item})
            else:
                if isinstance(workflow_input_value, dict) and "location" in workflow_input_value:
                    execute_body_inputs.append({execute_req_id: workflow_input_key,
                                                execute_req_input_val_href: workflow_input_value["location"]})
                else:
                    execute_body_inputs.append({execute_req_id: workflow_input_key,
                                                execute_req_input_val_data: workflow_input_value})
        for exec_input in execute_body_inputs:
            if execute_req_input_val_href in exec_input and isinstance(exec_input[execute_req_input_val_href], str):
                if exec_input[execute_req_input_val_href].startswith("{0}://".format(OPENSEARCH_LOCAL_FILE_SCHEME)):
                    exec_input[execute_req_input_val_href] = "file{0}".format(
                        exec_input[execute_req_input_val_href][len(OPENSEARCH_LOCAL_FILE_SCHEME):])
                elif exec_input[execute_req_input_val_href].startswith("file://"):
                    exec_input[execute_req_input_val_href] = self.host_file(exec_input[execute_req_input_val_href])
                    LOGGER.debug("Hosting intermediate input [%s] : [%s]",
                                 exec_input[execute_req_id], exec_input[execute_req_input_val_href])

        execute_body_outputs = [{execute_req_id: output, "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}
                                for output in expected_outputs]
        self.update_status("Executing job on remote ADES.", REMOTE_JOB_PROGRESS_EXECUTION, status.STATUS_RUNNING)

        execute_body = dict(mode=EXECUTE_MODE_ASYNC,
                            response=EXECUTE_RESPONSE_DOCUMENT,
                            inputs=execute_body_inputs,
                            outputs=execute_body_outputs)
        request_url = self.url + sd.process_jobs_service.path.format(process_id=self.process)
        response = self.make_request(method="POST",
                                     url=request_url,
                                     json=execute_body,
                                     retry=True)
        if response.status_code != 201:
            raise Exception("Was expecting a 201 status code from the execute request : {0}".format(request_url))

        job_status_uri = response.headers["Location"]
        job_status = self.get_job_status(job_status_uri)
        job_status_value = status.map_status(job_status["status"])

        self.update_status("Monitoring job on remote ADES : {0}".format(job_status_uri),
                           REMOTE_JOB_PROGRESS_MONITORING, status.STATUS_RUNNING)

        while job_status_value not in status.JOB_STATUS_CATEGORIES[status.JOB_STATUS_CATEGORY_FINISHED]:
            sleep(5)
            job_status = self.get_job_status(job_status_uri)
            job_status_value = status.map_status(job_status["status"])

            LOGGER.debug(get_log_monitor_msg(job_status["jobID"], job_status_value,
                                             job_status.get("percentCompleted", 0),
                                             get_any_message(job_status), job_status.get("statusLocation")))
            self.update_status(get_job_log_msg(status=job_status_value,
                                               message=get_any_message(job_status),
                                               progress=job_status.get("percentCompleted", 0),
                                               duration=job_status.get("duration", None)),  # get if available
                               map_progress(job_status.get("percentCompleted", 0),
                                            REMOTE_JOB_PROGRESS_MONITORING, REMOTE_JOB_PROGRESS_FETCH_OUT),
                               status.STATUS_RUNNING)

        if job_status_value != status.STATUS_SUCCEEDED:
            LOGGER.debug(get_log_monitor_msg(job_status["jobID"], job_status_value,
                                             job_status.get("percentCompleted", 0),
                                             get_any_message(job_status), job_status.get("statusLocation")))
            raise Exception(job_status)

        self.update_status("Fetching job outputs from remote ADES.",
                           REMOTE_JOB_PROGRESS_FETCH_OUT, status.STATUS_RUNNING)
        results = self.get_job_results(job_status["jobID"])
        for result in results:
            res_id = get_any_id(result)
            # CWL expect the output file to be written matching definition in 'expected_outputs',
            # but this definition could be a glob pattern to match multiple file.
            # Therefore, we cannot rely on a specific name from it.
            # Furthermore, a glob pattern could match multiple files.
            if res_id in expected_outputs:
                # plan ahead when list of multiple output values could be supported
                result_values = get_any_value(result)
                if not isinstance(result_values, list):
                    result_values = [result_values]
                cwl_out_dir = out_dir.rstrip("/")
                for value in result_values:
                    src_name = value.split("/")[-1]
                    dst_path = "/".join([cwl_out_dir, src_name])
                    # performance improvement: bypass download if file can be resolved as local
                    map_path = map_wps_output_location(value, self.settings)
                    if map_path:
                        LOGGER.info("Detected result [%s] from [%s] as local reference to this instance. "
                                    "Skipping fetch and using local copy in output destination: [%s]",
                                    res_id, value, dst_path)
                        LOGGER.debug("Mapped result [%s] to local reference: [%s]", value, map_path)
                        src_path = map_path
                    else:
                        LOGGER.info("Fetching result [%s] from [%s] to CWL output destination: [%s]",
                                    res_id, value, dst_path)
                        src_path = value
                    fetch_file(src_path, cwl_out_dir, settings=self.settings)

        self.update_status("Execution on remote ADES completed.",
                           REMOTE_JOB_PROGRESS_COMPLETED, status.STATUS_SUCCEEDED)

    def get_job_status(self, job_status_uri, retry=True):
        response = self.make_request(method="GET",
                                     url=job_status_uri,
                                     retry=True,
                                     status_code_mock=HTTPNotFound.code)
        # Retry on 404 since job may not be fully ready
        if retry and response.status_code == HTTPNotFound.code:
            sleep(5)
            return self.get_job_status(job_status_uri, retry=False)

        response.raise_for_status()
        job_status = response.json()

        # TODO Remove patch for Geomatys not conforming to the status schema
        #  - jobID is missing
        #  - handled by 'map_status': status are upper cases and succeeded process are indicated as successful
        job_id = job_status_uri.split("/")[-1]
        if "jobID" not in job_status:
            job_status["jobID"] = job_id
        job_status["status"] = status.map_status(job_status["status"])
        return job_status

    def get_job_results(self, job_id):
        # type: (str) -> List[JSON]
        """
        Obtains produced output results from successful job status ID.
        """
        # use results endpoint instead of '/outputs' to ensure support with other
        result_url = self.url + sd.process_results_service.path.format(process_id=self.process, job_id=job_id)
        response = self.make_request(method="GET", url=result_url, retry=True)
        response.raise_for_status()
        contents = response.json()

        # backward compatibility for ADES that returns output IDs nested under 'outputs'
        if "outputs" in contents:
            # ensure that we don't incorrectly pick a specific output ID named 'outputs'
            maybe_outputs = contents["outputs"]
            if isinstance(maybe_outputs, dict) and get_any_id(maybe_outputs) is None:
                contents = maybe_outputs
            # backward compatibility for ADES that returns list of outputs nested under 'outputs'
            # (i.e.: as Weaver-specific '/outputs' endpoint)
            elif isinstance(maybe_outputs, list) and all(get_any_id(out) is not None for out in maybe_outputs):
                contents = maybe_outputs

        # rebuild the expected (old) list format for calling method
        if isinstance(contents, dict) and all(get_any_value(out) is not None for out in contents.values()):
            outputs = []
            for out_id, out_val in contents.items():
                out_val.update({"id": out_id})
                outputs.append(out_val)
            contents = outputs
        return contents
