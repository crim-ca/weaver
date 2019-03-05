from weaver import status
from weaver.utils import get_any_id, get_any_value, get_job_log_msg, raise_on_xml_exception
from weaver.wps_restapi.utils import get_cookie_headers
from weaver.execute import EXECUTE_MODE_ASYNC
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes.wps_process_base import WpsProcessInterface
from weaver.wps_restapi.processes.processes import wait_secs, _jsonify_output
from weaver.wps_restapi.jobs.jobs import check_status
from owslib.wps import WebProcessingService, ComplexDataInput, WPSException
from typing import AnyStr, Callable
from time import sleep
import logging
import requests

LOGGER = logging.getLogger(__name__)

REMOTE_JOB_PROGRESS_REQ_PREP = 2
REMOTE_JOB_PROGRESS_EXECUTION = 5
REMOTE_JOB_PROGRESS_MONITORING = 10
REMOTE_JOB_PROGRESS_FETCH_OUT = 90
REMOTE_JOB_PROGRESS_COMPLETED = 100


class Wps1Process(WpsProcessInterface):
    def __init__(self, provider, process_id, cookies, update_status=None):
        super(Wps1Process, self).__init__(cookies)
        self.provider = provider
        self.process_id = process_id

        # type: Callable[[AnyStr, int, AnyStr], None]
        self.update_status = update_status

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        # TODO Toute cette fonction est inspiree de la job celery du rest_api mais n'a pas ete testee

        self.update_status("Preparing execute request for remote WPS1 provider.",
                           REMOTE_JOB_PROGRESS_REQ_PREP, status.STATUS_RUNNING)
        LOGGER.debug("Execute process WPS request for {0}".format(self.process_id))
        try:
            try:
                wps = WebProcessingService(url=self.provider, headers=get_cookie_headers(self.headers),
                                           verify=self.verify)
                # noinspection PyProtectedMember
                raise_on_xml_exception(wps._capabilities)
            except Exception as ex:
                raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
            try:
                process = wps.describeprocess(self.process_id)
            except Exception as ex:
                raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))

            # prepare inputs
            complex_inputs = []
            for process_input in process.dataInputs:
                if 'ComplexData' in process_input.dataType:
                    complex_inputs.append(process_input.identifier)

            try:
                wps_inputs = list()
                for workflow_input_key, workflow_input_value in workflow_inputs.items():
                    # TODO limited to file type right now (location key, hosting file based on scheme, etc.)!!!
                    # in case of array inputs, must repeat (id,value)
                    input_values = [val['location'] for val in workflow_input_value] \
                        if isinstance(workflow_input_value, list) \
                        else [workflow_input_value['location']]

                    # we need to host file starting with file:// scheme
                    input_values = [self.host_file(val)
                                    if val.startswith('file://')
                                    else val for val in input_values]

                    # need to use ComplexDataInput structure for complex input
                    wps_inputs.extend([(workflow_input_key,
                                        ComplexDataInput(input_value) if workflow_input_key in complex_inputs
                                        else input_value) for input_value in input_values])
            except KeyError:
                wps_inputs = []

            # prepare outputs
            outputs = [(o.identifier, o.dataType == 'ComplexData') for o in process.processOutputs
                       if o.identifier in expected_outputs]

            self.update_status('Executing job on remote WPS1 provider.',
                               REMOTE_JOB_PROGRESS_EXECUTION, status.STATUS_RUNNING)

            mode = EXECUTE_MODE_ASYNC
            execution = wps.execute(self.process_id, inputs=wps_inputs, output=outputs, mode=mode, lineage=True)
            if not execution.process and execution.errors:
                raise execution.errors[0]

            self.update_status('Monitoring job on remote WPS1 provider : {0}'.format(self.provider),
                               REMOTE_JOB_PROGRESS_MONITORING, status.STATUS_RUNNING)

            max_retries = 5
            num_retries = 0
            run_step = 0
            while execution.isNotComplete() or run_step == 0:
                if num_retries >= max_retries:
                    raise Exception("Could not read status document after {} retries. Giving up.".format(max_retries))
                try:
                    execution = check_status(url=execution.statusLocation, verify=self.verify,
                                             sleep_secs=wait_secs(run_step))

                    LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                        jobID=execution.jobID,
                        status=status.map_status(execution.getStatus()),
                        percentCompleted=execution.percentCompleted,
                        message=execution.statusMessage
                    ))
                    self.update_status(get_job_log_msg(status=status.map_status(execution.getStatus()),
                                                       message=execution.statusMessage,
                                                       progress=execution.percentCompleted,
                                                       duration=None),  # get if available
                                       self.map_progress(execution.percentCompleted,
                                                         REMOTE_JOB_PROGRESS_MONITORING, REMOTE_JOB_PROGRESS_FETCH_OUT),
                                       status.STATUS_RUNNING)
                except Exception as exc:
                    num_retries += 1
                    LOGGER.debug('Exception raised: {}'.format(repr(exc)))
                    sleep(1)
                else:
                    num_retries = 0
                    run_step += 1

            if not execution.isSucceded():
                LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                    jobID=execution.jobID,
                    status=status.map_status(execution.getStatus()),
                    percentCompleted=execution.percentCompleted,
                    message=execution.statusMessage or "Job failed."
                ))
                raise Exception(execution.statusMessage or "Job failed.")

            self.update_status('Fetching job outputs from remote WPS1 provider.',
                               REMOTE_JOB_PROGRESS_FETCH_OUT, status.STATUS_RUNNING)

            process = wps.describeprocess(self.process_id)
            output_datatype = {
                getattr(processOutput, 'identifier', ''): processOutput.dataType
                for processOutput in getattr(process, 'processOutputs', [])
            }
            results = [_jsonify_output(output, output_datatype[output.identifier])
                       for output in execution.processOutputs]
            for result in results:
                if get_any_id(result) in expected_outputs:
                    # This is where cwl expect the output file to be written
                    # TODO We will probably need to handle multiple output value...
                    dst_fn = '/'.join([out_dir.rstrip('/'), expected_outputs[get_any_id(result)]])

                    # TODO Should we handle other type than File reference?
                    r = requests.get(get_any_value(result), allow_redirects=True)
                    LOGGER.debug('Fetching result output from {0} to cwl output destination : {1}'.format(
                        get_any_value(result),
                        dst_fn
                    ))
                    with open(dst_fn, mode='wb') as dst_fh:
                        dst_fh.write(r.content)

        except (WPSException, Exception) as exc:
            if isinstance(exc, WPSException):
                errors = "[{0}] {1}".format(exc.locator, exc.text)
            else:
                exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
                errors = "{0}: {1}".format(exception_class, exc.message)
            raise Exception(errors)

        self.update_status('Execution on remote WPS1 provider completed.',
                           REMOTE_JOB_PROGRESS_COMPLETED, status.STATUS_SUCCEEDED)
