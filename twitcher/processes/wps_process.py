import logging
import requests
from copy import deepcopy
from time import sleep
from typing import Union
from twitcher import status
from twitcher.status import job_status_categories
from twitcher.visibility import VISIBILITY_PUBLIC
from twitcher.utils import get_any_id, get_any_value, get_any_message, get_job_log_msg
from twitcher.wps_restapi.swagger_definitions import (
    processes_uri,
    process_uri,
    process_jobs_uri,
    process_results_uri,
    process_visibility_uri,
)
from pyramid_celery import celery_app as app
from pyramid.settings import asbool
from pyramid.httpexceptions import HTTPOk, HTTPUnauthorized, HTTPNotFound, HTTPForbidden, HTTPInternalServerError

LOGGER = logging.getLogger(__name__)

OPENSEARCH_LOCAL_FILE_SCHEME = 'opensearchfile'  # must be a valid url scheme parsable by urlparse

REMOTE_JOB_PROGRESS_DEPLOY = 1
REMOTE_JOB_PROGRESS_VISIBLE = 3
REMOTE_JOB_PROGRESS_REQ_PREP = 5
REMOTE_JOB_PROGRESS_EXECUTION = 9
REMOTE_JOB_PROGRESS_MONITORING = 10
REMOTE_JOB_PROGRESS_FETCH_OUT = 90
REMOTE_JOB_PROGRESS_COMPLETED = 100


class WpsProcess(object):
    def __init__(self, url, process_id, deploy_body, cookies, update_status=None):
        self.url = url.rstrip('/')
        self.process_id = process_id
        self.deploy_body = deploy_body
        self.cookies = cookies
        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        registry = app.conf['PYRAMID_REGISTRY']
        self.settings = registry.settings
        self.verify = asbool(self.settings.get('twitcher.ows_proxy_ssl_verify', True))
        self.update_status = update_status

    def get_user_auth_header(self):
        # TODO: find a better way to generalize this to Magpie credentials?
        ades_usr = self.settings.get('ades.username', None)
        ades_pwd = self.settings.get('ades.password', None)
        ades_url = self.settings.get('ades.wso2_hostname', None)
        ades_client = self.settings.get('ades.wso2_client_id', None)
        ades_secret = self.settings.get('ades.wso2_client_secret', None)
        access_token = None
        if ades_usr and ades_pwd and ades_url and ades_client and ades_secret:
            ades_body = {
                'grant_type': 'password',
                'client_id': ades_client,
                'client_secret': ades_secret,
                'username': ades_usr,
                'password': ades_pwd,
                'scope': 'openid',
            }
            ades_headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}
            cred_resp = requests.post(ades_url, data=ades_body, headers=ades_headers)
            cred_resp.raise_for_status()
            access_token = cred_resp.json().get('access_token', None)
        else:
            LOGGER.warn(
                "Could not retrieve at least one of required login parameters: "
                "[ades.username, ades.password, ades.wso2_hostname, ades.wso2_client_id, ades.wso2_client_secret]"
            )
        return {'Authorization': 'Bearer {}'.format(access_token) if access_token else None}

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
        LOGGER.debug("Get process WPS visibility request for {0}".format(self.process_id))
        response = requests.get(self.url + process_visibility_uri.format(process_id=self.process_id),
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)
        if response.status_code in (HTTPUnauthorized.code, HTTPForbidden.code):
            return None
        elif response.status_code == HTTPNotFound.code:
            return False
        elif response.status_code == HTTPOk.code:
            json_body = response.json()
            # TODO: support for Spacebel, always returns dummy visibility response, enforce deploy with `False`
            if json_body.get('message') == "magic!" or json_body.get('type') == "ok" or json_body.get('code') == 4:
                return False
            return json_body.get('value') == VISIBILITY_PUBLIC
        response.raise_for_status()

    def set_visibility(self, visibility):
        self.update_status('Updating process visibility on remote ADES.', REMOTE_JOB_PROGRESS_VISIBLE)
        LOGGER.debug("Update process WPS visibility request for {0}".format(self.process_id))
        user_headers = deepcopy(self.headers)
        user_headers.update(self.get_user_auth_header())
        response = requests.put(self.url + process_visibility_uri.format(process_id=self.process_id),
                                json={'value': visibility},
                                headers=user_headers,
                                cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()

    def describe_process(self):
        LOGGER.debug("Describe process WPS request for {0}".format(self.process_id))
        response = requests.get(self.url + process_uri.format(process_id=self.process_id),
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)

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

    def deploy(self):
        self.update_status('Deploying process on remote ADES.', REMOTE_JOB_PROGRESS_DEPLOY)
        LOGGER.debug("Deploy process WPS request for {0}".format(self.process_id))
        user_headers = deepcopy(self.headers)
        user_headers.update(self.get_user_auth_header())
        response = requests.post(self.url + processes_uri,
                                 json=self.deploy_body,
                                 headers=user_headers,
                                 cookies=self.cookies,
                                 verify=self.verify)
        response.raise_for_status()

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        self.update_status('Preparing execute request for remote ADES.', REMOTE_JOB_PROGRESS_REQ_PREP)
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
            if exec_input[execute_req_inpt_val].startswith('{0}://'.format(OPENSEARCH_LOCAL_FILE_SCHEME)):
                exec_input[execute_req_inpt_val] = 'file{0}'.format(
                    exec_input[execute_req_inpt_val][len(OPENSEARCH_LOCAL_FILE_SCHEME):])
            elif exec_input[execute_req_inpt_val].startswith('file://'):
                exec_input[execute_req_inpt_val] = self.host_file(exec_input[execute_req_inpt_val])
                LOGGER.debug("Hosting intermediate input {0} : {1}".format(
                    exec_input[execute_req_id],
                    exec_input[execute_req_inpt_val]))

        execute_body_outputs = [{execute_req_id: output,
                                 execute_req_out_trans_mode: 'reference'} for output in expected_outputs]
        self.update_status('Executing job on remote ADES.', REMOTE_JOB_PROGRESS_EXECUTION)

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

        self.update_status('Monitoring job on remote ADES : {0}'.format(job_status_uri), REMOTE_JOB_PROGRESS_MONITORING)
        while job_status['status'] not in job_status_categories[status.STATUS_FINISHED]:
            sleep(5)
            job_status = self.get_job_status(job_status_uri)

            LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                jobID=job_status['jobID'],
                status=job_status['status'],
                percentCompleted=job_status.get('percentCompleted', ''),
                message=get_any_message(job_status)
            ))
            self.update_status(get_job_log_msg(status=job_status['status'],
                                               msg=get_any_message(job_status),
                                               progress=job_status.get('percentCompleted', 0)),
                               self.map_progress(job_status.get('percentCompleted', 0),
                                                 REMOTE_JOB_PROGRESS_MONITORING, REMOTE_JOB_PROGRESS_FETCH_OUT))

        if job_status['status'] != status.STATUS_SUCCEEDED:
            LOGGER.debug("Monitoring job {jobID} : [{status}] {percentCompleted}  {message}".format(
                jobID=job_status['jobID'],
                status=job_status['status'],
                percentCompleted=job_status.get('percentCompleted', ''),
                message=get_any_message(job_status)
            ))
            raise Exception(job_status)

        self.update_status('Fetching job outputs from remote ADES.', REMOTE_JOB_PROGRESS_FETCH_OUT)
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

        self.update_status('Execution on remote ADES completed.', REMOTE_JOB_PROGRESS_COMPLETED)

    def get_job_status(self, job_status_uri, retry=True):
        response = requests.get(job_status_uri,
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)

        # Retry on 404 since job may not be fully ready
        if retry and response.status_code == HTTPNotFound.code:
            sleep(5)
            return self.get_job_status(job_status_uri, retry=False)

        response.raise_for_status()
        job_status = response.json()

        # TODO Remove patch for Geomatys not conforming to the status schema
        # (jobID is missing, status are upper cases and succeeded process are indicated as successful)
        job_id = job_status_uri.split('/')[-1]
        if 'jobID' not in job_status:
            job_status['jobID'] = job_id
        job_status['status'] = job_status['status'].lower()
        if job_status['status'] == 'successful':
            job_status['status'] = status.STATUS_SUCCEEDED
        return job_status

    def get_job_results(self, job_id):
        response = requests.get(self.url + process_results_uri.format(process_id=self.process_id, job_id=job_id),
                                headers=self.headers,
                                cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()
        return response.json().get('outputs', {})

    @staticmethod
    def host_file(fn):
        registry = app.conf['PYRAMID_REGISTRY']
        twitcher_output_url = registry.settings.get('twitcher.wps_output_url')
        twitcher_output_path = registry.settings.get('twitcher.wps_output_path')
        fn = fn.replace('file://', '')

        if not fn.startswith(twitcher_output_path):
            raise Exception('Cannot host files outside of the output path : {0}'.format(fn))
        return fn.replace(twitcher_output_path, twitcher_output_url)

    @staticmethod
    def map_progress(progress, range_min, range_max):
        return range_min + (progress * (range_max - range_min)) / 100
