import logging
import os
import shutil
import tempfile
from abc import abstractmethod
from typing import TYPE_CHECKING

from requests.structures import CaseInsensitiveDict

from weaver.base import Constants
from weaver.exceptions import PackageExecutionError
from weaver.formats import ContentType
from weaver.processes.constants import OpenSearchField
from weaver.status import Status
from weaver.utils import (
    fetch_file,
    fully_qualified_name,
    get_any_id,
    get_any_value,
    get_cookie_headers,
    get_settings,
    request_extra
)
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location

if TYPE_CHECKING:
    from typing import Any, Optional, Union

    from weaver.typedefs import (
        AnyCookiesContainer,
        AnyHeadersContainer,
        AnyResponseType,
        CookiesTupleType,
        CWL_RuntimeInputsMap,
        CWL_ExpectedOutputs,
        CWL_WorkflowInputs,
        JobInputs,
        JobOutputs,
        JobResults,
        JobMonitorReference,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest

LOGGER = logging.getLogger(__name__)


class WpsRemoteJobProgress(Constants):
    """
    Progress of a remotely monitored WPS-1 job process execution.

    .. note::
        Implementations can reuse same progress values or intermediate ones within the range of the relevant sections.
    """
    START = 1
    PREPARE = 2
    READY = 5
    STAGE_IN = 10
    FORMAT_IO = 12
    EXECUTE = 15
    MONITOR = 20
    RESULTS = 85
    STAGE_OUT = 90
    CLEANUP = 95
    COMPLETED = 100


class WpsProcessInterface(object):
    """
    Common interface for :term:`WPS` :term:`Process` to be used for dispatching :term:`CWL` jobs.

    Multiple convenience methods are provide.
    Processes inheriting from this base should provide abstract method implementation as needed or required.

    .. note::
        For expected operations details and their execution order, please refer to :ref:`proc_workflow_ops`.

    .. seealso::
        :meth:`execute` for complete details of the operations and ordering.
    """

    def __init__(self, request, update_status):
        # type: (WorkerRequest, UpdateStatusPartialFunction) -> None
        self.request = request
        self.headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
        self.settings = get_settings()
        self.update_status = update_status  # type: UpdateStatusPartialFunction
        self.temp_staging = set()

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        # type: (CWL_RuntimeInputsMap, str, CWL_ExpectedOutputs) -> None
        """
        Execute the core operation of the remote :term:`Process` using the given inputs.

        The function is expected to monitor the process and update the status.
        Retrieve the expected outputs and store them in the ``out_dir``.

        :param workflow_inputs: `CWL` job dict
        :param out_dir: directory where the outputs must be written
        :param expected_outputs: expected value outputs as `{'id': 'value'}`
        """
        self.update_status("Preparing process for remote execution.",
                           WpsRemoteJobProgress.PREPARE, Status.RUNNING)
        self.prepare()
        self.update_status("Process ready for execute remote process.",
                           WpsRemoteJobProgress.READY, Status.RUNNING)

        self.update_status("Staging inputs for remote execution.",
                           WpsRemoteJobProgress.STAGE_IN, Status.RUNNING)
        staged_inputs = self.stage_inputs(workflow_inputs)

        self.update_status("Preparing inputs/outputs for remote execution.",
                           WpsRemoteJobProgress.FORMAT_IO, Status.RUNNING)
        expect_outputs = [{"id": output} for output in expected_outputs]
        process_inputs = self.format_inputs(staged_inputs)
        process_outputs = self.format_outputs(expect_outputs)

        try:
            self.update_status("Executing remote process job.",
                               WpsRemoteJobProgress.EXECUTE, Status.RUNNING)
            monitor_ref = self.dispatch(process_inputs, process_outputs)
            self.update_status("Monitoring remote process job until completion.",
                               WpsRemoteJobProgress.MONITOR, Status.RUNNING)
            job_success = self.monitor(monitor_ref)
            if not job_success:
                raise PackageExecutionError("Failed dispatch and monitoring of remote process execution.")
        except Exception as exc:
            err_msg = "{0}: {1!s}".format(fully_qualified_name(exc), exc)
            err_ctx = "Dispatch and monitoring of remote process caused an unhandled error."
            LOGGER.exception("%s [%s]", err_ctx, err_msg, exc_info=exc)
            self.update_status("Running final cleanup operations following failed execution.",
                               WpsRemoteJobProgress.CLEANUP, Status.RUNNING)
            self.cleanup()
            raise PackageExecutionError(err_ctx) from exc

        self.update_status("Retrieving job results definitions.",
                           WpsRemoteJobProgress.RESULTS, Status.RUNNING)
        results = self.get_results(monitor_ref)
        self.update_status("Staging job outputs from remote process.",
                           WpsRemoteJobProgress.STAGE_OUT, Status.RUNNING)
        self.stage_results(results, expected_outputs, out_dir)

        self.update_status("Running final cleanup operations before completion.",
                           WpsRemoteJobProgress.CLEANUP, Status.RUNNING)
        self.cleanup()

        self.update_status("Execution of remote process execution completed successfully.",
                           WpsRemoteJobProgress.COMPLETED, Status.SUCCEEDED)

    def prepare(self):
        # type: () -> None
        """
        Implementation dependent operations to prepare the :term:`Process` for :term:`Job` execution.

        This is an optional step that can be omitted entirely if not needed.
        """

    def format_inputs(self, workflow_inputs):
        # type: (JobInputs) -> Union[JobInputs, Any]
        """
        Implementation dependent operations to configure input values for :term:`Job` execution.

        This is an optional step that will simply pass down the inputs as is if no formatting is required.
        Otherwise, the implementing :term:`Process` can override the step to reorganize workflow step inputs into the
        necessary format required for their :meth:`dispatch` call.
        """
        return workflow_inputs

    def format_outputs(self, workflow_outputs):
        # type: (JobOutputs) -> JobOutputs
        """
        Implementation dependent operations to configure expected outputs for :term:`Job` execution.

        This is an optional step that will simply pass down the outputs as is if no formatting is required.
        Otherwise, the implementing :term:`Process` can override the step to reorganize workflow step outputs into the
        necessary format required for their :meth:`dispatch` call.
        """
        return workflow_outputs

    @abstractmethod
    def dispatch(self, process_inputs, process_outputs):
        # type: (JobInputs, JobOutputs) -> JobMonitorReference
        """
        Implementation dependent operations to dispatch the :term:`Job` execution to the remote :term:`Process`.

        :returns: reference details that will be passed to :meth:`monitor`.
        """
        raise NotImplementedError

    @abstractmethod
    def monitor(self, monitor_reference):
        # type: (JobMonitorReference) -> bool
        """
        Implementation dependent operations to monitor the status of the :term:`Job` execution that was dispatched.

        This step should block :meth:`execute` until the final status of the remote :term:`Job` (failed/success)
        can be obtained.

        :returns: success status
        """
        raise NotImplementedError

    @abstractmethod
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
                LOGGER.warning("Ignore failure to cleanup temporary staging path: [%s]", path)

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
        return CaseInsensitiveDict(headers)

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
        cookies = CaseInsensitiveDict(cookies or {})
        headers = CaseInsensitiveDict(headers or {})
        cookies.update(self.get_auth_cookies())
        headers.update(self.headers.copy())
        headers.update(self.get_auth_headers())
        response = request_extra(method, url=url, settings=self.settings, retries=retries,
                                 headers=headers, cookies=cookies, **kwargs)
        return response

    def host_file(self, file_path):
        """
        Hosts an intermediate file between :term:`Workflow` steps for processes that require external or remote access.

        :param file_path: Intermediate file location (local path expected).
        :return: Hosted temporary HTTP file location.
        """
        wps_out_url = get_wps_output_url(self.settings)
        wps_out_dir = get_wps_output_dir(self.settings)
        file_path = os.path.realpath(file_path.replace("file://", ""))  # in case CWL->WPS outputs link was made
        if file_path.startswith(wps_out_dir):
            file_href = file_path.replace(wps_out_dir, wps_out_url, 1)
            LOGGER.debug("Hosting file [%s] skipped since already on WPS outputs as [%s]", file_path, file_href)
        else:
            tmp_out_dir = tempfile.mkdtemp(dir=wps_out_dir)
            file_link = fetch_file(file_path, tmp_out_dir, self.settings, link=True)
            file_href = file_link.replace(wps_out_dir, wps_out_url, 1)
            self.temp_staging.add(tmp_out_dir)
            LOGGER.debug("Hosting file [%s] as [%s] on [%s]", file_path, file_link, file_href)
        return file_href

    def stage_results(self, results, expected_outputs, out_dir):
        # type: (JobResults, CWL_ExpectedOutputs, str) -> None
        """
        Retrieves the remote execution :term:`Job` results for staging locally into the specified output directory.

        This operation should be called by the implementing remote :term:`Process` definition after :meth:`execute`.

        .. note::
            The :term:`CWL` runner expects the output file(s) to be written matching definition in ``expected_outputs``,
            but this definition could be a glob pattern to match multiple file and/or nested directories.
            We cannot rely on specific file names to be mapped, since glob can match many (eg: ``"*.txt"``).
        """
        for result in results:
            res_id = get_any_id(result)
            if res_id not in expected_outputs:
                continue

            # plan ahead when list of multiple output values could be supported
            result_values = get_any_value(result)
            if not isinstance(result_values, list):
                result_values = [result_values]
            cwl_out_dir = out_dir.rstrip("/")
            for value in result_values:
                src_name = value.split("/")[-1]
                dst_path = "/".join([cwl_out_dir, src_name])
                # performance improvement:
                #   Bypass download if file can be resolved as local resource (already fetched or same server).
                #   Because CWL expects the file to be in specified 'out_dir', make a link for it to be found
                #   even though the file is stored in the full job output location instead (already staged by step).
                map_path = map_wps_output_location(value, self.settings)
                as_link = False
                if map_path:
                    LOGGER.info("Detected result [%s] from [%s] as local reference to this instance. "
                                "Skipping fetch and using local copy in output destination: [%s]",
                                res_id, value, dst_path)
                    LOGGER.debug("Mapped result [%s] to local reference: [%s]", value, map_path)
                    src_path = map_path
                    as_link = True
                else:
                    LOGGER.info("Fetching result [%s] from [%s] to CWL output destination: [%s]",
                                res_id, value, dst_path)
                    src_path = value
                fetch_file(src_path, cwl_out_dir, settings=self.settings, link=as_link)

    def stage_inputs(self, workflow_inputs):
        # type: (CWL_WorkflowInputs) -> JobInputs
        """
        Retrieves inputs for local staging if required for the following :term:`Job` execution.
        """
        execute_body_inputs = []
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            if not isinstance(workflow_input_value, list):
                workflow_input_value = [workflow_input_value]
            for workflow_input_value_item in workflow_input_value:
                if isinstance(workflow_input_value_item, dict) and "location" in workflow_input_value_item:
                    location = workflow_input_value_item["location"]
                    execute_body_inputs.append({"id": workflow_input_key, "href": location})
                else:
                    execute_body_inputs.append({"id": workflow_input_key, "data": workflow_input_value_item})

        for exec_input in execute_body_inputs:
            if "href" in exec_input and isinstance(exec_input["href"], str):
                LOGGER.debug("Original input location [%s] : [%s]", exec_input["id"], exec_input["href"])
                if exec_input["href"].startswith("{0}://".format(OpenSearchField.LOCAL_FILE_SCHEME)):
                    exec_input["href"] = "file{0}".format(exec_input["href"][len(OpenSearchField.LOCAL_FILE_SCHEME):])
                    LOGGER.debug("OpenSearch intermediate input [%s] : [%s]", exec_input["id"], exec_input["href"])
                elif exec_input["href"].startswith("file://"):
                    exec_input["href"] = self.host_file(exec_input["href"])
                    LOGGER.debug("Hosting intermediate input [%s] : [%s]", exec_input["id"], exec_input["href"])
        return execute_body_inputs
