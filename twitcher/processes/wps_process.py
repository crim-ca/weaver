import logging
from time import sleep
import requests
from twitcher import status
from twitcher.status import job_status_categories
from twitcher.utils import get_any_id, get_any_value
from twitcher.wps_restapi.swagger_definitions import (
processes_uri,
process_uri,
process_jobs_uri,
process_job_uri,
process_results_uri
)
from pyramid_celery import celery_app as app
from pyramid.settings import asbool


# TODO The logger log twice ?
LOGGER = logging.getLogger(__name__)

OPENSEARCH_LOCAL_FILE_SCHEME = 'opensearchfile'  # must be a valid url scheme parsable by urlparse

class WpsProcess(object):
    def __init__(self, url, process_id, deploy_body, cookies):
        self.url = url.rstrip('/')
        self.process_id = process_id
        self.deploy_body = deploy_body
        self.cookies = cookies
        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        registry = app.conf['PYRAMID_REGISTRY']
        self.verify = asbool(registry.settings.get('twitcher.ows_proxy_ssl_verify', True))

    def is_deployed(self):
        return self.describe_process() is not None

    def describe_process(self):
        LOGGER.debug("Describe process WPS request for {0}".format(self.process_id))
        response = requests.get(self.url + process_uri.format(process_id=self.process_id),
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)

        if response.status_code == 200:
            # TODO Remove patch for Geomatys ADES (Missing process return a 200 InvalidParameterValue error !)
            if response.content.lower().find('InvalidParameterValue') >= 0:
                return None
            return response.json()
        elif response.status_code == 404:
            return None
        response.raise_for_status()

    def deploy(self):
        LOGGER.debug("Deploy process WPS request for {0}".format(self.process_id))
        response = requests.post(self.url + processes_uri,
                                 json=self.deploy_body,
                                 headers=self.headers,
                                 cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        LOGGER.debug("Execute process WPS request for {0}".format(self.process_id))

        execute_body_inputs = []
        execute_req_id = 'id'
        execute_req_inpt_val = 'href'
        execute_req_out_trans_mode = 'transmissionMode'
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            json_input = dict(identifier=workflow_input_key)
            if isinstance(workflow_input_value, list):
                for workflow_input_value_item in workflow_input_value:
                    execute_body_inputs.append({execute_req_id: workflow_input_key,
                                                execute_req_inpt_val: workflow_input_value_item['location']})
            else:
                execute_body_inputs.append({execute_req_id: workflow_input_key,
                                            execute_req_inpt_val: workflow_input_value['location']})
        for input in execute_body_inputs:
            if input[execute_req_inpt_val].startswith('{0}://'.format(OPENSEARCH_LOCAL_FILE_SCHEME)):
                input[execute_req_inpt_val] = 'file{0}'.format(
                    input[execute_req_inpt_val][len(OPENSEARCH_LOCAL_FILE_SCHEME):])
            elif input[execute_req_inpt_val].startswith('file://'):
                input[execute_req_inpt_val] = self.host_file(input[execute_req_inpt_val])
                LOGGER.debug("Hosting intermediate input {0} : {1}".format(
                    input[execute_req_id],
                    input[execute_req_inpt_val]))

        execute_body_outputs = [{execute_req_id: output,
                                 execute_req_out_trans_mode: 'reference'} for output in expected_outputs]

        execute_body = dict(mode='async',
                            response='document',
                            inputs=execute_body_inputs,
                            outputs=execute_body_outputs)
        request_url = self.url + process_jobs_uri.format(process_id=self.process_id)
        response = requests.post(request_url,
                                 json=execute_body,
                                 headers=self.headers,
                                 cookies=self.cookies,
                                 verify=self.verify)
        response.raise_for_status()
        if response.status_code != 201:
            raise Exception('Was expecting a 201 status code from the execute request : {0}'.format(request_url))
        job_status_uri = response.headers['Location']
        job_status = self.get_job_status(job_status_uri)

        while job_status['status'] not in job_status_categories[status.STATUS_FINISHED]:
            sleep(5)
            job_status = self.get_job_status(job_status_uri)

            LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                jobID=job_status['jobID'],
                status=job_status['status'],
                percentCompleted=job_status.get('percentCompleted', ''),
                message=job_status.get('message', '')
            ))

        if job_status['status'] != status.STATUS_SUCCEEDED:
            LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                jobID=job_status['jobID'],
                status=job_status['status'],
                percentCompleted=job_status.get('percentCompleted', ''),
                message=job_status.get('message', '')
            ))
            raise Exception(job_status)

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


    def get_job_status(self, job_status_uri):
        response = requests.get(job_status_uri,
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()
        status = response.json()

        # TODO Remove patch for Geomatys not conforming to the status schema
        # (jobID is missing, status are upper cases and succeeded process are indicated as successful)
        job_id = job_status_uri.split('/')[-1]
        if 'jobID' not in status:
            status['jobID'] = job_id
        status['status'] = status['status'].lower()
        if status['status'] == 'successful':
            status['status'] = 'succeeded'

        return status

    def get_job_results(self, job_id):
        response = requests.get(self.url + process_results_uri.format(process_id=self.process_id, job_id=job_id),
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()
        return response.json().get('outputs', {})

    def host_file(self, fn):
        registry = app.conf['PYRAMID_REGISTRY']
        twitcher_output_url = registry.settings.get('twitcher.wps_output_url')
        twitcher_output_path = registry.settings.get('twitcher.wps_output_path')
        fn = fn.replace('file://', '')

        if not fn.startswith(twitcher_output_path):
            raise Exception('Cannot host files outside of the output path : {0}'.format(fn))
        return fn.replace(twitcher_output_path, twitcher_output_url)

