import logging
import requests
from time import sleep
from typing import AnyStr, Callable
from weaver import status
from weaver.utils import get_any_id, get_any_value, get_any_message, get_job_log_msg, pass_http_error
from weaver.wps_restapi.swagger_definitions import (
    process_uri,
    process_jobs_uri,
    process_results_uri
)
from weaver.processes.wps_process_base import WpsProcessInterface
from pyramid.httpexceptions import (
    HTTPOk,
    HTTPNotFound,
    HTTPInternalServerError,
)


LOGGER = logging.getLogger(__name__)

REMOTE_JOB_PROGRESS_PROVIDER = 1
REMOTE_JOB_PROGRESS_DEPLOY = 2
REMOTE_JOB_PROGRESS_VISIBLE = 3
REMOTE_JOB_PROGRESS_REQ_PREP = 5
REMOTE_JOB_PROGRESS_EXECUTION = 9
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

    def describe_process(self):
        path = self.url + process_uri.format(process_id=self.process_id)
        LOGGER.debug("Describe process WPS request for {0} at {1}".format(self.process_id, path))
        response = self.make_request(method='GET',
                                     url=path,
                                     retry=False,
                                     status_code_mock=HTTPOk.code)

        if response.status_code == HTTPOk.code:
            # TODO Remove patch for Geomatys ADES (Missing process return a 200 InvalidParameterValue error !)
            if response.content.lower().find('InvalidParameterValue') >= 0:
                return None
            return response.json()
        elif response.status_code == HTTPNotFound.code:
            return None
        # TODO Remove patch for Spacebel ADES (Missing process return a 500 error)
        elif response.status_code == HTTPInternalServerError.code:
            return None
        response.raise_for_status()

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        self.update_status("Preparing execute request for remote ADES.",
                           REMOTE_JOB_PROGRESS_REQ_PREP, status.STATUS_RUNNING)
        LOGGER.debug("Execute process WPS request for {0}".format(self.process_id))

        execute_body_inputs = []
        execute_req_id = 'id'
        execute_req_inpt_val = 'href'
        execute_req_out_trans_mode = 'transmissionMode'
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            if isinstance(workflow_input_value, list):
                for workflow_input_value_item in workflow_input_value:
                    execute_body_inputs.append({execute_req_id: workflow_input_key,
                                                execute_req_inpt_val: workflow_input_value_item['location']})
            else:
                execute_body_inputs.append({execute_req_id: workflow_input_key,
                                            execute_req_inpt_val: workflow_input_value['location']})
        for exec_input in execute_body_inputs:
            if exec_input[execute_req_inpt_val].startswith('file://'):
                exec_input[execute_req_inpt_val] = self.host_file(exec_input[execute_req_inpt_val])
                LOGGER.debug("Hosting intermediate input {0} : {1}".format(
                    exec_input[execute_req_id],
                    exec_input[execute_req_inpt_val]))

        execute_body_outputs = [{execute_req_id: output,
                                 execute_req_out_trans_mode: 'reference'} for output in expected_outputs]
        self.update_status('Executing job on remote ADES.', REMOTE_JOB_PROGRESS_EXECUTION, status.STATUS_RUNNING)

        execute_body = dict(mode='async',
                            response='document',
                            inputs=execute_body_inputs,
                            outputs=execute_body_outputs)
        request_url = self.url + process_jobs_uri.format(process_id=self.process_id)
        response = self.make_request(method='POST',
                                     url=request_url,
                                     json=execute_body,
                                     retry=True)
        if response.status_code != 201:
            raise Exception('Was expecting a 201 status code from the execute request : {0}'.format(request_url))

        job_status_uri = response.headers['Location']
        job_status = self.get_job_status(job_status_uri)
        job_status_value = status.map_status(job_status['status'])

        self.update_status('Monitoring job on remote ADES : {0}'.format(job_status_uri),
                           REMOTE_JOB_PROGRESS_MONITORING, status.STATUS_RUNNING)

        while job_status_value not in status.job_status_categories[status.STATUS_CATEGORY_FINISHED]:
            sleep(5)
            job_status = self.get_job_status(job_status_uri)
            job_status_value = status.map_status(job_status['status'])

            LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                jobID=job_status['jobID'],
                status=job_status_value,
                percentCompleted=job_status.get('percentCompleted', ''),
                message=get_any_message(job_status)
            ))
            self.update_status(get_job_log_msg(status=job_status_value,
                                               message=get_any_message(job_status),
                                               progress=job_status.get('percentCompleted', 0),
                                               duration=job_status.get('duration', None)),  # get if available
                               self.map_progress(job_status.get('percentCompleted', 0),
                                                 REMOTE_JOB_PROGRESS_MONITORING, REMOTE_JOB_PROGRESS_FETCH_OUT),
                               status.STATUS_RUNNING)

        if job_status_value != status.STATUS_SUCCEEDED:
            LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                jobID=job_status['jobID'],
                status=job_status_value,
                percentCompleted=job_status.get('percentCompleted', ''),
                message=get_any_message(job_status)
            ))
            raise Exception(job_status)

        self.update_status('Fetching job outputs from remote ADES.',
                           REMOTE_JOB_PROGRESS_FETCH_OUT, status.STATUS_RUNNING)
        results = self.get_job_results(job_status['jobID'])
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

        self.update_status('Execution on remote ADES completed.',
                           REMOTE_JOB_PROGRESS_COMPLETED, status.STATUS_SUCCEEDED)

    def get_job_status(self, job_status_uri, retry=True):
        response = self.make_request(method='GET',
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
        job_id = job_status_uri.split('/')[-1]
        if 'jobID' not in job_status:
            job_status['jobID'] = job_id
        job_status['status'] = status.map_status(job_status['status'])
        return job_status

    def get_job_results(self, job_id):
        result_url = self.url + process_results_uri.format(process_id=self.process_id, job_id=job_id)
        response = self.make_request(method='GET',
                                     url=result_url,
                                     retry=True)
        response.raise_for_status()
        return response.json().get('outputs', {})
