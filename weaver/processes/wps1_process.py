import logging
from time import sleep
from typing import TYPE_CHECKING, AnyStr

from owslib.wps import ComplexDataInput, WebProcessingService

from weaver import status
from weaver.execute import EXECUTE_MODE_ASYNC
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes.constants import WPS_COMPLEX_DATA
from weaver.processes.utils import jsonify_output, map_progress
from weaver.processes.wps_process_base import WpsProcessInterface
from weaver.utils import (
    get_any_id,
    get_any_value,
    get_job_log_msg,
    get_log_monitor_msg,
    raise_on_xml_exception,
    request_extra,
    wait_secs
)
from weaver.wps import check_wps_status

if TYPE_CHECKING:
    from weaver.typedefs import UpdateStatusPartialFunction     # noqa: F401
    from pywps.app import WPSRequest                            # noqa: F401

LOGGER = logging.getLogger(__name__)

REMOTE_JOB_PROGRESS_REQ_PREP = 2
REMOTE_JOB_PROGRESS_EXECUTION = 5
REMOTE_JOB_PROGRESS_MONITORING = 10
REMOTE_JOB_PROGRESS_FETCH_OUT = 90
REMOTE_JOB_PROGRESS_COMPLETED = 100


class Wps1Process(WpsProcessInterface):
    def __init__(self,
                 provider,          # type: AnyStr
                 process,           # type: AnyStr
                 request,           # type: WPSRequest
                 update_status,     # type: UpdateStatusPartialFunction
                 ):
        super(Wps1Process, self).__init__(request)
        self.provider = provider
        self.process = process
        self.update_status = lambda _message, _progress, _status: update_status(
            self.provider, _message, _progress, _status)

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        self.update_status("Preparing execute request for remote WPS1 provider.",
                           REMOTE_JOB_PROGRESS_REQ_PREP, status.STATUS_RUNNING)
        LOGGER.debug("Execute process WPS request for %s", self.process)
        try:
            try:
                wps = WebProcessingService(url=self.provider, headers=self.cookies, verify=self.verify)
                raise_on_xml_exception(wps._capabilities)  # noqa: W0212
            except Exception as ex:
                raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
            try:
                process = wps.describeprocess(self.process)
            except Exception as ex:
                raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))

            # prepare inputs
            complex_inputs = []
            for process_input in process.dataInputs:
                if WPS_COMPLEX_DATA in process_input.dataType:
                    complex_inputs.append(process_input.identifier)

            # remove any 'null' input, should employ the 'default' of the remote WPS process
            workflow_inputs_provided_keys = filter(lambda i: workflow_inputs[i] != "null", workflow_inputs)

            wps_inputs = []
            for workflow_input_key in workflow_inputs_provided_keys:
                workflow_input_val = workflow_inputs[workflow_input_key]
                # in case of array inputs, must repeat (id,value)
                # in case of complex input (File), obtain location, otherwise get data value
                if not isinstance(workflow_input_val, list):
                    workflow_input_val = [workflow_input_val]

                input_values = []
                for val in workflow_input_val:
                    if isinstance(val, dict):
                        val = val["location"]

                    # owslib only accepts strings, not numbers directly
                    if isinstance(val, (int, float)):
                        val = str(val)

                    if val.startswith("file://"):
                        # we need to host file starting with file:// scheme
                        val = self.host_file(val)

                    input_values.append(val)

                # need to use ComplexDataInput structure for complex input
                # TODO: BoundingBox not supported
                for input_value in input_values:
                    if workflow_input_key in complex_inputs:
                        input_value = ComplexDataInput(input_value)

                    wps_inputs.append((workflow_input_key, input_value))

            # prepare outputs
            outputs = [(o.identifier, o.dataType == WPS_COMPLEX_DATA) for o in process.processOutputs
                       if o.identifier in expected_outputs]

            self.update_status("Executing job on remote WPS1 provider.",
                               REMOTE_JOB_PROGRESS_EXECUTION, status.STATUS_RUNNING)

            mode = EXECUTE_MODE_ASYNC
            execution = wps.execute(self.process, inputs=wps_inputs, output=outputs, mode=mode, lineage=True)
            if not execution.process and execution.errors:
                raise execution.errors[0]

            self.update_status("Monitoring job on remote WPS1 provider : [{0}]".format(self.provider),
                               REMOTE_JOB_PROGRESS_MONITORING, status.STATUS_RUNNING)

            max_retries = 5
            num_retries = 0
            run_step = 0
            job_id = "<undefined>"
            while execution.isNotComplete() or run_step == 0:
                if num_retries >= max_retries:
                    raise Exception("Could not read status document after {} retries. Giving up.".format(max_retries))
                try:
                    execution = check_wps_status(url=execution.statusLocation, verify=self.verify,
                                                 sleep_secs=wait_secs(run_step))
                    job_id = execution.statusLocation.replace(".xml", "").split("/")[-1]
                    LOGGER.debug(get_log_monitor_msg(job_id, status.map_status(execution.getStatus()),
                                                     execution.percentCompleted, execution.statusMessage,
                                                     execution.statusLocation))
                    self.update_status(get_job_log_msg(status=status.map_status(execution.getStatus()),
                                                       message=execution.statusMessage,
                                                       progress=execution.percentCompleted,
                                                       duration=None),  # get if available
                                       map_progress(execution.percentCompleted,
                                                    REMOTE_JOB_PROGRESS_MONITORING, REMOTE_JOB_PROGRESS_FETCH_OUT),
                                       status.STATUS_RUNNING)
                except Exception as exc:
                    num_retries += 1
                    LOGGER.debug("Exception raised: %r", exc)
                    sleep(1)
                else:
                    num_retries = 0
                    run_step += 1

            if not execution.isSucceded():
                exec_msg = execution.statusMessage or "Job failed."
                LOGGER.debug(get_log_monitor_msg(job_id, status.map_status(execution.getStatus()),
                                                 execution.percentCompleted, exec_msg, execution.statusLocation))
                raise Exception(execution.statusMessage or "Job failed.")

            self.update_status("Fetching job outputs from remote WPS1 provider.",
                               REMOTE_JOB_PROGRESS_FETCH_OUT, status.STATUS_RUNNING)

            results = [jsonify_output(output, process) for output in execution.processOutputs]
            for result in results:
                result_id = get_any_id(result)
                result_val = get_any_value(result)
                if result_id in expected_outputs:
                    # This is where cwl expect the output file to be written
                    # TODO We will probably need to handle multiple output value...
                    dst_fn = "/".join([out_dir.rstrip("/"), expected_outputs[result_id]])

                    # TODO Should we handle other type than File reference?

                    resp = request_extra("get", result_val, allow_redirects=True, settings=self.settings)
                    LOGGER.debug("Fetching result output from [%s] to cwl output destination: [%s]", result_val, dst_fn)
                    with open(dst_fn, mode="wb") as dst_fh:
                        dst_fh.write(resp.content)

        except Exception as exc:
            exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
            errors = "{0}: {1!s}".format(exception_class, exc)
            LOGGER.exception(exc)
            raise Exception(errors)

        self.update_status("Execution on remote WPS1 provider completed.",
                           REMOTE_JOB_PROGRESS_COMPLETED, status.STATUS_SUCCEEDED)
