import abc
import logging
import os
import shutil
import tempfile
import time
from typing import TYPE_CHECKING

from werkzeug.datastructures import Headers

from weaver.base import Constants
from weaver.exceptions import PackageExecutionError
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteReturnPreference
from weaver.formats import ContentType, repr_json
from weaver.processes.constants import (
    PACKAGE_COMPLEX_TYPES,
    PACKAGE_DIRECTORY_TYPE,
    PACKAGE_FILE_TYPE,
    JobInputsOutputsSchema,
    OpenSearchField
)
from weaver.processes.convert import convert_input_values_schema, get_cwl_io_type
from weaver.processes.utils import map_progress
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.utils import (
    OutputMethod,
    fetch_reference,
    fully_qualified_name,
    get_any_id,
    get_any_message,
    get_any_value,
    get_cookie_headers,
    get_job_log_msg,
    get_log_monitor_msg,
    get_settings,
    request_extra,
    wait_secs
)
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Optional, Union

    from weaver.typedefs import (
        AnyCookiesContainer,
        AnyHeadersContainer,
        AnyResponseType,
        CookiesTupleType,
        CWL_ExpectedOutputs,
        CWL_Output_Type,
        CWL_WorkflowInputs,
        JobCustomInputs,
        JobCustomOutputs,
        JobInputs,
        JobMonitorReference,
        JobOutputs,
        JobResults,
        JSON,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest

LOGGER = logging.getLogger(__name__)


class RemoteJobProgress(Constants):
    """
    Progress of a remotely monitored job process execution.

    .. note::
        Implementations can reuse same progress values or intermediate ones within the range of the relevant sections.
    """
    SETUP = 1
    PREPARE = 2
    READY = 5
    STAGE_IN = 10
    FORMAT_IO = 12
    EXECUTION = 15
    MONITORING = 20
    RESULTS = 85
    STAGE_OUT = 90
    CLEANUP = 95
    COMPLETED = 100


class WpsProcessInterface(abc.ABC):
    """
    Common interface for :term:`WPS` :term:`Process` to be used for dispatching :term:`CWL` jobs.

    Multiple convenience methods are provided.
    Processes inheriting from this base should implement required abstract methods and override operations as needed.

    .. note::
        For expected operations details and their execution order, please refer to :ref:`proc_workflow_ops`.

    .. seealso::
        :meth:`execute` for complete details of the operations and ordering.
    """

    def __init__(self, request, update_status):
        # type: (Optional[WorkerRequest], UpdateStatusPartialFunction) -> None
        self.request = request
        self.headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
        self.settings = get_settings()
        self.update_status = update_status  # type: UpdateStatusPartialFunction
        self.temp_staging = set()

    def execute(
        self,
        workflow_inputs,    # type: Union[CWL_WorkflowInputs, JobCustomInputs]
        out_dir,            # type: str
        expected_outputs,   # type: Union[CWL_ExpectedOutputs, JobCustomOutputs]
    ):                      # type: (...) -> JobOutputs
        """
        Execute the core operation of the remote :term:`Process` using the given inputs.

        The function is expected to monitor the process and update the status.
        Retrieve the expected outputs and store them in the ``out_dir``.

        :param workflow_inputs: :term:`CWL` job dictionary.
        :param out_dir: directory where the outputs must be written.
        :param expected_outputs: expected outputs to collect from complex references.
        """
        self.update_status("Preparing process for remote execution.",
                           RemoteJobProgress.PREPARE, Status.RUNNING)
        self.prepare(workflow_inputs, expected_outputs)
        self.update_status("Process ready for execute remote process.",
                           RemoteJobProgress.READY, Status.RUNNING)

        self.update_status("Staging inputs for remote execution.",
                           RemoteJobProgress.STAGE_IN, Status.RUNNING)
        staged_inputs = self.stage_inputs(workflow_inputs)

        self.update_status("Preparing inputs/outputs for remote execution.",
                           RemoteJobProgress.FORMAT_IO, Status.RUNNING)
        expect_outputs = [{"id": out_id, **out_info} for out_id, out_info in expected_outputs.items()]
        process_inputs = self.format_inputs(staged_inputs)
        process_outputs = self.format_outputs(expect_outputs)

        try:
            self.update_status("Executing remote process job.",
                               RemoteJobProgress.EXECUTION, Status.RUNNING)
            monitor_ref = self.dispatch(process_inputs, process_outputs)
            self.update_status("Monitoring remote process job until completion.",
                               RemoteJobProgress.MONITORING, Status.RUNNING)
            job_success = self.monitor(monitor_ref)
            if not job_success:
                raise PackageExecutionError("Failed dispatch and monitoring of remote process execution.")
        except Exception as exc:
            err_msg = f"{fully_qualified_name(exc)}: {exc!s}"
            err_ctx = "Dispatch and monitoring of remote process caused an unhandled error."
            LOGGER.exception("%s [%s]", err_ctx, err_msg, exc_info=exc)
            self.update_status(err_msg, RemoteJobProgress.CLEANUP, Status.RUNNING, error=exc)
            self.update_status("Running final cleanup operations following failed execution.",
                               RemoteJobProgress.CLEANUP, Status.RUNNING)
            self.cleanup()
            raise PackageExecutionError(err_ctx) from exc

        self.update_status("Retrieving job results definitions.",
                           RemoteJobProgress.RESULTS, Status.RUNNING)
        results = self.get_results(monitor_ref)
        self.update_status("Staging job outputs from remote process.",
                           RemoteJobProgress.STAGE_OUT, Status.RUNNING)
        self.stage_results(results, expected_outputs, out_dir)

        self.update_status("Running final cleanup operations before completion.",
                           RemoteJobProgress.CLEANUP, Status.RUNNING)
        self.cleanup()

        self.update_status("Execution of remote process execution completed successfully.",
                           RemoteJobProgress.COMPLETED, Status.SUCCEEDED)
        return results

    def prepare(  # noqa: B027  # intentionally not an abstract method to allow no-op
        self,
        workflow_inputs,    # type: Union[CWL_WorkflowInputs, JobCustomInputs]
        expected_outputs,   # type: Union[CWL_ExpectedOutputs, JobCustomOutputs]
    ):                      # type: (...) -> None
        """
        Implementation dependent operations to prepare the :term:`Process` for :term:`Job` execution.

        This is an optional step that can be omitted entirely if not needed.
        This step should be considered for the creation of a reusable client or object handler that does not need to be
        recreated on any subsequent steps, such as for :meth:`dispatch` and :meth:`monitor` calls.
        """

    def format_inputs(self, job_inputs):
        # type: (JobInputs) -> Union[JobInputs, JobCustomInputs]
        """
        Implementation dependent operations to configure input values for :term:`Job` execution.

        This is an optional step that will simply pass down the inputs as is if no formatting is required.
        Otherwise, the implementing :term:`Process` can override the step to reorganize workflow step inputs into the
        necessary format required for their :meth:`dispatch` call.
        """
        return job_inputs

    def format_outputs(self, job_outputs):
        # type: (JobOutputs) -> Optional[Union[JobOutputs, JobCustomOutputs]]
        """
        Implementation dependent operations to configure expected outputs for :term:`Job` execution.

        This is an optional step that will simply pass down the outputs as is if no formatting is required.
        Otherwise, the implementing :term:`Process` can override the step to reorganize workflow step outputs into the
        necessary format required for their :meth:`dispatch` call.
        """
        return job_outputs

    @abc.abstractmethod
    def dispatch(
        self,
        process_inputs,     # type: Union[JobInputs, JobCustomInputs]
        process_outputs,    # type: Optional[Union[JobOutputs, JobCustomOutputs]]
    ):                      # type: (...) -> JobMonitorReference
        """
        Implementation dependent operations to dispatch the :term:`Job` execution to the remote :term:`Process`.

        :returns: reference details that will be passed to :meth:`monitor`.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def monitor(self, monitor_reference):
        # type: (JobMonitorReference) -> bool
        """
        Implementation dependent operations to monitor the status of the :term:`Job` execution that was dispatched.

        This step should block :meth:`execute` until the final status of the remote :term:`Job` (failed/success)
        can be obtained.

        :returns: success status
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_results(self, monitor_reference):
        # type: (JobMonitorReference) -> JobResults
        """
        Implementation dependent operations to retrieve the results following a successful :term:`Job` execution.

        The operation should **NOT** fetch (stage) results, but only obtain the locations where they can be retrieved,
        based on the monitoring reference that was generated from the execution.

        :returns: results locations
        """
        raise NotImplementedError

    def cleanup(self):
        # type: () -> None
        """
        Implementation dependent operations to clean the :term:`Process` or :term:`Job` execution.

        This is an optional step that doesn't require any override if not needed by derived classes.
        """
        for path in self.temp_staging:
            try:
                if os.path.isfile(path):
                    LOGGER.debug("Removing temporary staging file: [%s]", path)
                    os.remove(path)
                elif os.path.isdir(path):
                    LOGGER.debug("Removing temporary staging directory: [%s]", path)
                    shutil.rmtree(path)
            except OSError:
                LOGGER.warning("Ignore failure to clean up temporary staging path: [%s]", path)

    def get_auth_headers(self):
        # type: () -> AnyHeadersContainer
        """
        Implementation dependent operation to retrieve applicable authorization headers.

        This method is employed for every :meth:`make_request` call to avoid manually providing them each time.
        Any overriding method should consider calling this method to retrieve authorization headers from WPS request.
        """
        headers = {}
        if self.request and self.request.auth_headers:
            headers = self.request.auth_headers.copy()
        return Headers(headers)

    def get_auth_cookies(self):
        # type: () -> CookiesTupleType
        """
        Implementation dependent operation to retrieve applicable authorization cookies.

        This method is employed for every :meth:`make_request` call to avoid manually providing them each time.
        Any overriding method should consider calling this method to retrieve authorization cookies from WPS request.
        """
        cookies = []
        if self.request and self.request.http_request:
            for name in ["Cookie", "Set-Cookie"]:
                headers = get_cookie_headers(self.request.http_request, name)
                cookies.extend([(key, value) for key, value in headers.items()])
        return cookies

    def make_request(self,
                     method,        # type: str
                     url,           # type: str
                     retry=False,   # type: Union[bool, int]
                     cookies=None,  # type: Optional[AnyCookiesContainer]
                     headers=None,  # type: Optional[AnyHeadersContainer]
                     **kwargs,      # type: Any
                     ):             # type: (...) -> AnyResponseType
        """
        Sends the request with additional parameter handling for the current process definition.
        """
        retries = int(retry) if retry is not None else 0
        cookies = Headers(cookies or {})
        headers = Headers(headers or {})
        cookies.update(self.get_auth_cookies())
        headers.update(self.headers.copy())
        headers.update(self.get_auth_headers())
        response = request_extra(method, url=url, settings=self.settings, retries=retries,
                                 headers=headers, cookies=cookies, **kwargs)
        return response

    def host_reference(self, reference):
        # type: (str) -> str
        """
        Hosts an intermediate reference between :term:`Workflow` steps for processes that require remote access.

        :param reference: Intermediate file or directory location (local path expected).
        :return: Hosted temporary HTTP file or directory location.
        """
        wps_out_url = get_wps_output_url(self.settings)
        wps_out_dir = get_wps_output_dir(self.settings)
        ref_path = os.path.realpath(reference.replace("file://", ""))  # in case CWL->WPS outputs link was made
        ref_path += "/" if reference.endswith("/") else ""
        if reference.startswith(wps_out_dir):
            ref_href = ref_path.replace(wps_out_dir, wps_out_url, 1)
            LOGGER.debug("Hosting file [%s] skipped since already on WPS outputs as [%s]", reference, ref_href)
        else:
            tmp_out_dir = tempfile.mkdtemp(dir=wps_out_dir)
            ref_link = fetch_reference(ref_path, tmp_out_dir, out_listing=False,
                                       settings=self.settings, out_method=OutputMethod.LINK)
            ref_href = ref_link.replace(wps_out_dir, wps_out_url, 1)
            self.temp_staging.add(tmp_out_dir)
            LOGGER.debug("Hosting file [%s] as [%s] on [%s]", reference, ref_link, ref_href)
        return ref_href

    def stage_results(self, results, expected_outputs, out_dir):
        # type: (JobResults, CWL_ExpectedOutputs, str) -> None
        """
        Retrieves the remote execution :term:`Job` results for staging locally into the specified output directory.

        This operation should be called by the implementing remote :term:`Process` definition after :meth:`execute`.

        .. note::
            The :term:`CWL` runner expects the output file(s) to be written matching definition in ``expected_outputs``,
            but this definition could be a glob pattern to match multiple file and/or nested directories.
            We cannot rely on specific file names to be mapped, since glob can match many (eg: ``"*.txt"``).

        .. seealso::
            Function :func:`weaver.processes.convert._convert_any2cwl_io_complex` defines a generic glob pattern from
            the expected file extension based on Content-Type format. Since the remote :term:`WPS` :term:`Process`
            doesn't necessarily produce file names with the output ID as expected to find them (could be anything),
            staging must patch locations to let :term:`CWL` runtime resolve the files according to glob definitions.
        """
        if not expected_outputs:
            return
        for result in results:
            res_id = get_any_id(result)
            if res_id not in expected_outputs:
                continue

            # Ignore outputs 'collected' by CWL tool to allow a 'string' value to resolve 'loadContent' operation.
            # However, the reference file used to load contents from an expression, does not (and should not)
            # itself need staging or fetching from the remote process. The resulting 'string' value only is used.
            res_def = {"name": res_id, "type": expected_outputs[res_id]["type"]}  # type: CWL_Output_Type
            res_type = get_cwl_io_type(res_def).type  # resolve atomic type in case of nested/array/nullable definition
            if res_type not in PACKAGE_COMPLEX_TYPES:
                continue

            cwl_out_dir = "/".join([out_dir.rstrip("/"), res_id])
            os.makedirs(cwl_out_dir, mode=0o700, exist_ok=True)

            # handle list in case of multiple output values
            result_values = get_any_value(result)
            if not isinstance(result_values, list):
                result_values = [result_values]
            for value in result_values:
                if isinstance(value, dict):
                    value = get_any_value(value, file=True, data=False)
                src_name = value.split("/")[-1]
                dst_path = "/".join([cwl_out_dir, src_name])
                # performance improvement:
                #   Bypass download if file can be resolved as local resource (already fetched or same server).
                #   Because CWL expects the file to be in specified 'out_dir', make a link for it to be found
                #   even though the file is stored in the full job output location instead (already staged by step).
                map_path = map_wps_output_location(value, self.settings)
                out_method = OutputMethod.COPY
                if map_path:
                    LOGGER.info("Detected result [%s] from [%s] as local reference to this instance. "
                                "Skipping fetch and using local copy in output destination: [%s]",
                                res_id, value, dst_path)
                    LOGGER.debug("Mapped result [%s] to local reference: [%s]", value, map_path)
                    src_path = map_path
                    out_method = OutputMethod.LINK
                else:
                    LOGGER.info("Fetching result [%s] from [%s] to CWL output destination: [%s]",
                                res_id, value, dst_path)
                    src_path = value
                fetch_reference(src_path, cwl_out_dir, out_method=out_method, settings=self.settings)

    def stage_inputs(self, workflow_inputs):
        # type: (CWL_WorkflowInputs) -> JobInputs
        """
        Retrieves inputs for local staging if required for the following :term:`Job` execution.
        """
        execute_body_inputs = []
        workflow_inputs = convert_input_values_schema(workflow_inputs, JobInputsOutputsSchema.OGC)
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            if not isinstance(workflow_input_value, list):
                workflow_input_value = [workflow_input_value]
            for workflow_input_value_item in workflow_input_value:
                if isinstance(workflow_input_value_item, dict) and "location" in workflow_input_value_item:
                    location = workflow_input_value_item["location"]
                    # if the location came from a collected output resolved by cwltool from a previous Workflow step
                    # obtained directory type does not contain the expected trailing slash for Weaver reference checks
                    input_class = workflow_input_value_item.get("class", PACKAGE_FILE_TYPE)
                    if input_class == PACKAGE_DIRECTORY_TYPE:
                        location = f"{location.rstrip('/')}/"
                    execute_body_inputs.append({"id": workflow_input_key, "href": location})
                else:
                    execute_body_inputs.append({"id": workflow_input_key, "data": workflow_input_value_item})

        for exec_input in execute_body_inputs:
            if "href" in exec_input and isinstance(exec_input["href"], str):
                LOGGER.debug("Original input location [%s] : [%s]", exec_input["id"], exec_input["href"])
                if exec_input["href"].startswith(f"{OpenSearchField.LOCAL_FILE_SCHEME}://"):
                    exec_href = exec_input["href"][len(OpenSearchField.LOCAL_FILE_SCHEME):]
                    exec_input["href"] = f"file{exec_href}"
                    LOGGER.debug("OpenSearch intermediate input [%s] : [%s]", exec_input["id"], exec_input["href"])
                elif exec_input["href"].startswith("file://"):
                    exec_input["href"] = self.host_reference(exec_input["href"])
                    LOGGER.debug("Hosting intermediate input [%s] : [%s]", exec_input["id"], exec_input["href"])
        return execute_body_inputs


class OGCAPIRemoteProcessBase(WpsProcessInterface, abc.ABC):
    # items to be specified by specialized class
    process_type = NotImplemented   # type: str
    provider = NotImplemented       # type: str
    url = NotImplemented            # type: str

    def __init__(self,
                 step_payload,      # type: JSON
                 process,           # type: str
                 request,           # type: Optional[WorkerRequest]
                 update_status,     # type: UpdateStatusPartialFunction
                 ):                 # type: (...) -> None
        super(OGCAPIRemoteProcessBase, self).__init__(
            request,
            lambda _message, _progress, _status, *args, **kwargs: update_status(
                _message, _progress, _status, self.provider, *args, **kwargs
            )
        )
        self.deploy_body = step_payload
        self.process = process

    def format_outputs(self, job_outputs):
        # type: (JobOutputs) -> Optional[JobOutputs]
        # note:
        #   - Because OGC-API will be requested with 'document'/'minimal' response,
        #     output transmission mode will auto-resolve as data/link according to type.
        #   - Because 'job_outputs' originate from CWL 'expected_outputs' in this case,
        #     only the 'type: File' outputs are listed. Providing these outputs explicitly
        #     will cause the filter-output mechanism to omit all literals from results.
        #     Therefore, omit any output indication entirely.
        #   - Use 'None' instead of '{}' or '[]' to avoid "no output" request.
        return None

    def dispatch(self, process_inputs, process_outputs):
        # type: (JobInputs, Optional[JobOutputs]) -> str
        LOGGER.debug("Execute process %s request for [%s]", self.process_type, self.process)
        execute_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": process_inputs,
        }
        execute_headers = {
            "Prefer": "respond-async",
            "Accept": ContentType.APP_JSON,
            "Content-Type": ContentType.APP_JSON,
        }
        if process_outputs is not None:  # don't insert to avoid filter-output by explicit empty dict/list
            execute_body["outputs"] = process_outputs
        LOGGER.debug("Execute process %s body for [%s]:\n%s", self.process_type, self.process, repr_json(execute_body))
        request_url = self.url + sd.process_execution_service.path.format(process_id=self.process)
        response = self.make_request(
            method="POST",
            url=request_url,
            json=execute_body,
            headers=execute_headers,
            timeout=10,
            retry=True,
        )
        if response.status_code in [404, 405]:
            # backward compatibility endpoint
            request_url = self.url + sd.process_jobs_service.path.format(process_id=self.process)
            response = self.make_request(
                method="POST",
                url=request_url,
                json=execute_body,
                headers=execute_headers,
                timeout=10,
                retry=True,
            )
        if response.status_code != 201:
            LOGGER.error("Request [POST %s] failed with: [%s]", request_url, response.status_code)
            self.update_status(
                (
                    f"Request [POST {request_url}] failed with: [{response.status_code}]\n"
                    f"{repr_json(response.text, indent=2)}"
                ),
                RemoteJobProgress.EXECUTION,
                Status.FAILED,
                level=logging.ERROR,
            )
            raise Exception(f"Was expecting a 201 status code from the execute request: [{request_url}]")

        job_status_uri = response.headers["Location"]
        return job_status_uri

    def monitor(self, monitor_reference):
        # type: (str) -> bool
        job_status_uri = monitor_reference
        job_status_data = self.get_job_status(job_status_uri)
        job_status_value = map_status(job_status_data["status"])
        job_id = job_status_data["jobID"]

        self.update_status(f"Monitoring job on remote ADES: [{job_status_uri}]",
                           RemoteJobProgress.MONITORING, Status.RUNNING)

        retry = 0
        while job_status_value not in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            wait = wait_secs(retry)
            time.sleep(wait)
            retry += 1

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
                                            RemoteJobProgress.MONITORING, RemoteJobProgress.STAGE_OUT),
                               Status.RUNNING)

        if job_status_value not in JOB_STATUS_CATEGORIES[StatusCategory.SUCCESS]:
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
        result_url = f"{monitor_reference}/results"
        result_headers = {
            "Accept": ContentType.APP_JSON,
            "Prefer": f"return={ExecuteReturnPreference.MINIMAL}",
        }
        response = self.make_request(method="GET", url=result_url, headers=result_headers, retry=True)
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
        if isinstance(contents, dict) and all(
            (get_any_value(out) if isinstance(out, dict) else out) is not None
            for out in contents.values()
        ):
            outputs = []
            for out_id, out_val in contents.items():
                if not isinstance(out_val, dict):
                    out_val = {"value": out_val}
                out_val.update({"id": out_id})
                outputs.append(out_val)
            contents = outputs
        return contents
