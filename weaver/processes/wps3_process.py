import logging
import warnings
from time import sleep
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPConflict, HTTPForbidden, HTTPNotFound, HTTPOk, HTTPUnauthorized
from pyramid.settings import asbool

from weaver.exceptions import PackageExecutionError
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentType
from weaver.processes import opensearch
from weaver.processes.sources import get_data_source_from_url, retrieve_data_source_url
from weaver.processes.utils import map_progress
from weaver.processes.wps_process_base import WpsProcessInterface, WpsRemoteJobProgress
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.utils import (
    get_any_id,
    get_any_message,
    get_any_value,
    get_job_log_msg,
    get_log_monitor_msg,
    pass_http_error,
    repr_json,
    request_extra
)
from weaver.visibility import Visibility
from weaver.warning import MissingParameterWarning
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Union

    from weaver.typedefs import (
        AnyHeadersContainer,
        JSON,
        JobInputs,
        JobMonitorReference,
        JobOutputs,
        JobResults,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest


LOGGER = logging.getLogger(__name__)


class Wps3RemoteJobProgress(WpsRemoteJobProgress):
    PROVIDER = 1
    # PREPARE = 2
    DEPLOY = 3
    VISIBLE = 4
    # READY = 5
    EXECUTION = 9
    MONITORING = 10
    FETCH_OUT = 90
    # COMPLETED = 100


class Wps3Process(WpsProcessInterface):
    def __init__(self,
                 step_payload,      # type: JSON
                 joborder,          # type: JSON
                 process,           # type: str
                 request,           # type: WorkerRequest
                 update_status,     # type: UpdateStatusPartialFunction
                 ):
        super(Wps3Process, self).__init__(
            request,
            lambda _message, _progress, _status: update_status(_message, _progress, _status, self.provider or "local")
        )
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
            LOGGER.error("Error during WPS-3 process data source resolution: [%s]", exc, exc_info=exc)
            raise PackageExecutionError("Failed resolution of WPS-3 process data source: [{!r}]".format(exc))

        self.provider = data_source  # fix immediately for below `update_status` call
        self.update_status("Provider {provider} is selected {reason}.".format(provider=data_source, reason=reason),
                           Wps3RemoteJobProgress.PROVIDER, Status.RUNNING)

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
            ades_headers = {"Content-Type": ContentType.APP_FORM, "Accept": ContentType.APP_JSON}
            ades_access_token_url = "{}/oauth2/token".format(ades_url)
            cred_resp = request_extra("post", ades_access_token_url,
                                      data=ades_body, headers=ades_headers, settings=self.settings)
            cred_resp.raise_for_status()
            if ContentType.APP_JSON not in cred_resp.headers.get("Content-Type"):
                raise HTTPUnauthorized("Cannot retrieve valid access token using credential or ADES configurations.")
            access_token = cred_resp.json().get("access_token", None)
            if not access_token:
                warnings.warn("Could not retrieve valid access token although response is expected to contain one.",
                              MissingParameterWarning)
        elif self.request and self.request.auth_headers and "Authorization" in self.request.auth_headers:
            # FIXME: consider X-Auth-ADES in case of conflict with Authorization for server that hosts this EMS?
            LOGGER.debug("Detected Authorization header directly specified in request for ADES.")
            access_token = self.request.auth_headers.get("Authorization")
        else:
            warnings.warn(
                "Could not retrieve at least one of required login parameters: "
                "[ades.username, ades.password, ades.wso2_hostname, ades.wso2_client_id, ades.wso2_client_secret]",
                MissingParameterWarning
            )
        return {"Authorization": "Bearer {}".format(access_token)} if access_token else {}

    def get_auth_headers(self):
        # type: () -> AnyHeadersContainer
        """
        Add specific user access headers for :term:`ADES` if provided in :ref:`Configuration Settings`.
        """
        headers = super(Wps3Process, self).get_auth_headers()
        auth = headers.get("Authorization")
        if not auth:
            headers.update(self.get_user_auth_header())
        return headers

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
                                     retry=False)
        if response.status_code in (HTTPUnauthorized.code, HTTPForbidden.code):
            return None
        if response.status_code == HTTPNotFound.code:
            return False
        if response.status_code == HTTPOk.code:
            json_body = response.json()
            return json_body.get("value") == Visibility.PUBLIC
        response.raise_for_status()

    def set_visibility(self, visibility):
        self.update_status("Updating process visibility on remote ADES.",
                           Wps3RemoteJobProgress.VISIBLE, Status.RUNNING)
        path = self.url + sd.process_visibility_service.path.format(process_id=self.process)
        LOGGER.debug("Update process WPS visibility request for [%s] at [%s]", self.process, path)
        response = self.make_request(method="PUT",
                                     url=path,
                                     json={"value": visibility},
                                     retry=False,
                                     swap_error_status_code=HTTPOk.code)
        response.raise_for_status()

    def describe_process(self):
        path = self.url + sd.process_service.path.format(process_id=self.process)
        LOGGER.debug("Describe process WPS request for [%s] at [%s]", self.process, path)
        response = self.make_request(method="GET",
                                     url=path,
                                     retry=False,
                                     swap_error_status_code=HTTPOk.code)

        if response.status_code == HTTPOk.code:
            return response.json()
        elif response.status_code == HTTPNotFound.code:
            return None
        response.raise_for_status()

    def deploy(self):
        self.update_status("Deploying process on remote ADES.",
                           Wps3RemoteJobProgress.DEPLOY, Status.RUNNING)
        path = self.url + sd.processes_service.path
        LOGGER.debug("Deploy process WPS request for [%s] at [%s]", self.process, path)
        response = self.make_request(method="POST", url=path, json=self.deploy_body, retry=True)
        response.raise_for_status()

    def prepare(self):
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
                pass_http_error(exc, [HTTPConflict])

        if visible:
            LOGGER.info("Process [%s] already deployed and visible on [%s] - executing.", self.process, self.url)
        else:
            LOGGER.info("Process [%s] enforcing to public visibility.", self.process)
            try:
                self.set_visibility(visibility=Visibility.PUBLIC)
            except Exception as exc:
                pass_http_error(exc, HTTPNotFound)
                LOGGER.warning("Process [%s] failed setting public visibility. "
                               "Assuming feature is not supported by ADES and process is already public.", self.process)

    def format_outputs(self, workflow_outputs):
        # type: (JobOutputs) -> JobOutputs
        for output in workflow_outputs:
            output.update({"transmissionMode": ExecuteTransmissionMode.REFERENCE})
        return workflow_outputs

    def dispatch(self, process_inputs, process_outputs):
        # type: (JobInputs, JobOutputs) -> Any
        LOGGER.debug("Execute process WPS request for [%s]", self.process)
        execute_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": process_inputs,
            "outputs": process_outputs
        }
        LOGGER.debug("Execute process WPS body for [%s]:\n%s", self.process, repr_json(execute_body))
        request_url = self.url + sd.process_jobs_service.path.format(process_id=self.process)
        response = self.make_request(method="POST", url=request_url, json=execute_body, retry=True)
        if response.status_code != 201:
            LOGGER.error("Request [POST %s] failed with: [%s]", request_url, response.status_code)
            raise Exception("Was expecting a 201 status code from the execute request : {0}".format(request_url))

        job_status_uri = response.headers["Location"]
        return job_status_uri

    def monitor(self, monitor_reference):
        # type: (str) -> bool
        job_status_uri = monitor_reference
        job_status_data = self.get_job_status(job_status_uri)
        job_status_value = map_status(job_status_data["status"])
        job_id = job_status_data["jobID"]

        self.update_status("Monitoring job on remote ADES : {0}".format(job_status_uri),
                           Wps3RemoteJobProgress.MONITORING, Status.RUNNING)

        while job_status_value not in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            sleep(5)
            job_status_data = self.get_job_status(job_status_uri)
            job_status_value = map_status(job_status_data["status"])

            LOGGER.debug(get_log_monitor_msg(job_id, job_status_value,
                                             job_status_data.get("percentCompleted", 0),
                                             get_any_message(job_status_data), job_status_data.get("statusLocation")))
            self.update_status(get_job_log_msg(status=job_status_value,
                                               message=get_any_message(job_status_data),
                                               progress=job_status_data.get("percentCompleted", 0),
                                               duration=job_status_data.get("duration", None)),  # get if available
                               map_progress(job_status_data.get("percentCompleted", 0),
                                            Wps3RemoteJobProgress.MONITORING, Wps3RemoteJobProgress.FETCH_OUT),
                               Status.RUNNING)

        if job_status_value != Status.SUCCEEDED:
            LOGGER.debug(get_log_monitor_msg(job_id, job_status_value,
                                             job_status_data.get("percentCompleted", 0),
                                             get_any_message(job_status_data), job_status_data.get("statusLocation")))
            raise PackageExecutionError(job_status_data)
        return True

    def get_job_status(self, job_status_uri, retry=True):
        # type: (JobMonitorReference, Union[bool, int]) -> JSON
        """
        Obtains the contents from the :term:`Job` status response.
        """
        response = self.make_request(method="GET", url=job_status_uri, retry=retry)  # retry in case not yet ready
        response.raise_for_status()
        job_status = response.json()
        job_id = job_status_uri.split("/")[-1]
        if "jobID" not in job_status:
            job_status["jobID"] = job_id  # provide if not implemented by ADES
        job_status["status"] = map_status(job_status["status"])
        return job_status

    def get_results(self, monitor_reference):
        # type: (str) -> JobResults
        """
        Obtains produced output results from successful job status ID.
        """
        # use '/results' endpoint instead of '/outputs' to ensure support with other
        result_url = monitor_reference + "/results"
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
