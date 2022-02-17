import logging
from time import sleep
from typing import TYPE_CHECKING

from owslib.wps import ComplexDataInput

from weaver import status
from weaver.execute import EXECUTE_MODE_ASYNC
from weaver.formats import get_format
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes.constants import WPS_COMPLEX_DATA
from weaver.processes.convert import ows2json_output_data
from weaver.processes.utils import map_progress
from weaver.processes.wps_process_base import (
    REMOTE_JOB_PROGRESS_MONITOR,
    REMOTE_JOB_PROGRESS_RESULTS,
    WpsProcessInterface
)
from weaver.utils import (
    get_any_id,
    get_any_value,
    get_job_log_msg,
    get_log_monitor_msg,
    raise_on_xml_exception,
    wait_secs
)
from weaver.wps.utils import check_wps_status, get_wps_client

if TYPE_CHECKING:
    from typing import Optional

    from owslib.wps import WebProcessingService

    from weaver.typedefs import (
        CWL_RuntimeInputsMap,
        JobExecution,
        JobInputs,
        JobOutputs,
        JobResults,
        OWS_InputDataValues,
        ProcessOWS,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest

LOGGER = logging.getLogger(__name__)


class Wps1Process(WpsProcessInterface):
    def __init__(self,
                 provider,          # type: str
                 process,           # type: str
                 request,           # type: WorkerRequest
                 update_status,     # type: UpdateStatusPartialFunction
                 ):
        self.provider = provider
        self.process = process
        # following are defined after 'prepare' step
        self.wps_provider = None    # type: Optional[WebProcessingService]
        self.wps_process = None     # type: Optional[ProcessOWS]
        super(Wps1Process, self).__init__(
            request,
            lambda _message, _progress, _status: update_status(_message, _progress, _status, self.provider)
        )

    def format_inputs(self, workflow_inputs):
        # type: (CWL_RuntimeInputsMap) -> OWS_InputDataValues
        """
        Convert submitted :term:`CWL` workflow inputs into corresponding :mod:`OWSLib.wps` representation for execution.

        :param workflow_inputs: mapping of input IDs and values submitted to the workflow.
        :returns: converted OWS inputs ready for submission to remote WPS process.
        """
        # prepare inputs
        complex_inputs = []
        for process_input in self.wps_process.dataInputs:
            if WPS_COMPLEX_DATA in process_input.dataType:
                complex_inputs.append(process_input.identifier)

        wps_inputs = []
        for input_item in workflow_inputs:
            input_key = get_any_id(input_item)
            input_val = get_any_value(input_item)

            # ignore optional inputs resolved as omitted
            if input_val is None:
                continue

            # in case of array inputs, must repeat (id,value)
            # in case of complex input (File), obtain location, otherwise get data value
            if not isinstance(input_val, list):
                input_val = [input_val]

            input_values = []
            for val in input_val:
                mime_type = None
                encoding = None
                if isinstance(val, dict):
                    fmt = val.get("format")  # format as namespace:link
                    val = val["location"]
                    if fmt:
                        fmt = get_format(workflow_inputs[input_key]["format"])  # format as content-type
                        mime_type = fmt.mime_type or None
                        encoding = fmt.encoding or None  # avoid empty string

                # owslib only accepts strings, not numbers directly
                if isinstance(val, (int, float)):
                    val = str(val)

                input_values.append((val, mime_type, encoding))

            # need to use ComplexDataInput structure for complex input
            # TODO: BoundingBox not supported
            for input_value, mime_type, encoding in input_values:
                if input_key in complex_inputs:
                    input_value = ComplexDataInput(input_value, mimeType=mime_type, encoding=encoding)

                wps_inputs.append((input_key, input_value))
        return wps_inputs

    def format_outputs(self, workflow_outputs):
        # type: (JobOutputs) -> JobOutputs
        expected_outputs = {get_any_id(out) for out in workflow_outputs}
        provided_outputs = self.wps_process.processOutputs
        outputs_as_ref = [
            {"id": out.identifier, "as_ref": out.dataType == WPS_COMPLEX_DATA}
            for out in provided_outputs if out.identifier in expected_outputs
        ]
        if not outputs_as_ref:
            provided_outputs = {out.identifier for out in provided_outputs}
            LOGGER.warning("No matching outputs between intersect of WPS-1 expected and provided outputs.\n"
                           "Provided: %s\nExpected: %s", list(expected_outputs), list(provided_outputs))
        return outputs_as_ref

    def prepare(self):
        LOGGER.debug("Execute WPS-1 provider: [%s]", self.provider)
        LOGGER.debug("Execute WPS-1 process: [%s]", self.process)
        try:
            headers = {}
            headers.update(self.get_auth_cookies())
            headers.update(self.get_auth_headers())
            self.wps_provider = get_wps_client(self.provider, headers=headers)
            raise_on_xml_exception(self.wps_provider._capabilities)  # noqa: W0212
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
        try:
            self.wps_process = self.wps_provider.describeprocess(self.process)
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))

    def dispatch(self, process_inputs, process_outputs):
        # type: (JobInputs, JobOutputs) -> JobExecution
        wps_outputs = [(output["id"], output["as_ref"]) for output in process_outputs]
        execution = self.wps_provider.execute(
            self.process,
            inputs=process_inputs,
            output=wps_outputs,
            mode=EXECUTE_MODE_ASYNC,
            lineage=True
        )
        if not execution.process and execution.errors:
            raise execution.errors[0]
        return {"execution": execution}  # return a dict to allow update by reference

    def monitor(self, monitor_reference):
        # type: (JobExecution) -> bool
        execution = monitor_reference["execution"]
        max_retries = 20  # using 'wait_secs' incremental delays, this is ~3min of retry attempts
        num_retries = 0
        run_step = 0
        job_id = "<undefined>"
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= max_retries:
                raise Exception("Could not read status document after {} retries. Giving up.".format(max_retries))
            try:
                execution = check_wps_status(location=execution.statusLocation,
                                             sleep_secs=wait_secs(run_step), settings=self.settings)
                monitor_reference["execution"] = execution  # update reference for later stages
                job_id = execution.statusLocation.split("/")[-1].replace(".xml", "")
                exec_status = status.map_status(execution.getStatus())
                LOGGER.debug(get_log_monitor_msg(job_id,
                                                 exec_status,
                                                 execution.percentCompleted,
                                                 execution.statusMessage,
                                                 execution.statusLocation))
                log_msg = get_job_log_msg(status=exec_status,
                                          message=execution.statusMessage,
                                          progress=execution.percentCompleted,
                                          duration=None)  # get if available
                log_progress = map_progress(execution.percentCompleted,
                                            REMOTE_JOB_PROGRESS_MONITOR,
                                            REMOTE_JOB_PROGRESS_RESULTS)
                self.update_status(log_msg, log_progress, status.STATUS_RUNNING)
            except Exception as exc:
                num_retries += 1
                LOGGER.debug("Exception raised: %r", exc)
                sleep(1)
            else:
                num_retries = 0
                run_step += 1

        if not execution.isSucceded():
            exec_msg = execution.statusMessage or "Job failed."
            exec_status = status.map_status(execution.getStatus())
            LOGGER.debug(get_log_monitor_msg(job_id,
                                             exec_status,
                                             execution.percentCompleted,
                                             exec_msg,
                                             execution.statusLocation))
            return False
        return True

    def get_results(self, monitor_reference):
        # type: (JobExecution) -> JobResults
        self.update_status("Retrieving job output definitions from remote WPS-1 provider.",
                           REMOTE_JOB_PROGRESS_RESULTS, status.STATUS_RUNNING)
        execution = monitor_reference["execution"]
        ows_results = [
            ows2json_output_data(output, self.wps_process, self.settings)
            for output in execution.processOutputs
        ]
        return ows_results
