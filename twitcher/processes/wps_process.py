import json
import logging
import os
import shutil
import urlparse
from time import sleep
import requests
from twitcher import status
from twitcher.status import job_status_categories
from pyramid_celery import celery_app as app
from pyramid.settings import asbool


# TODO The logger log twice ?
LOGGER = logging.getLogger(__name__)

OPENSEARCH_LOCAL_FILE_SCHEME = 'opensearch_file'

class WpsProcess(object):
    def __init__(self, url, process_id, deploy_body, cookies):
        self.url = url.rstrip('/')
        self.process_id = process_id
        self.deploy_body = deploy_body
        self.cookies = cookies

        registry = app.conf['PYRAMID_REGISTRY']
        self.verify = asbool(registry.settings.get('twitcher.ows_proxy_ssl_verify', True))

    def is_deployed(self):
        return self.describe_process() is not None

    def describe_process(self):
        LOGGER.debug("Describe process WPS request for {0}".format(self.process_id))
        response = requests.get(self.url + '/processes/' + self.process_id,
                                headers={'Accept': 'application/json'},
                                cookies=self.cookies,
                                verify=self.verify)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        response.raise_for_status()

    def deploy(self):
        LOGGER.debug("Deploy process WPS request for {0}".format(self.process_id))
        response = requests.post(self.url + '/processes',
                                 json=self.deploy_body,
                                 headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                                 cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        LOGGER.debug("Execute process WPS request for {0}".format(self.process_id))

        execute_body_inputs = []
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            json_input = dict(identifier=workflow_input_key)
            if isinstance(workflow_input_value, list):
                for workflow_input_value_item in workflow_input_value:
                    execute_body_inputs.append(dict(identifier=workflow_input_key,
                                                    value=workflow_input_value_item['location']))
            else:
                execute_body_inputs.append(dict(identifier=workflow_input_key,
                                                value=workflow_input_value['location']))
        for input in execute_body_inputs:
            if input['value'].startswith('{0}://'.format(OPENSEARCH_LOCAL_FILE_SCHEME)):
                input['value'] = 'file{0}'.format(input['value'][len(OPENSEARCH_LOCAL_FILE_SCHEME):])
            elif input['value'].startswith('file://'):
                input['value'] = self.host_file(input['value'])
                LOGGER.debug("Hosting intermediate input {0} : {1}".format(input['identifier'], input['value']))


        execute_body = dict(inputs=execute_body_inputs)
        response = requests.post(self.url + '/processes/' + self.process_id + '/jobs',
                                 json=execute_body,
                                 headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                                 cookies=self.cookies,
                                 verify=self.verify)
        response.raise_for_status()
        if response.status_code != 201:
            response.raise_for_status()
        job_id = response.json()['jobID']
        job_status = response.json()

        while job_status['status'] not in job_status_categories[status.STATUS_FINISHED]:
            sleep(5)
            job_status = self.get_job_status(job_id)
            LOGGER.debug("Monitoring job {job} : [{status}] {progress} - {message}".format(job=job_id, **job_status))

        if job_status == status.STATUS_FAILED:
            LOGGER.exception("Monitoring job {job} : [{status}] {message}".format(job=job_id, **job_status))
            raise Exception(job_status)

        results = self.get_job_results(job_id)

        for result in results:
            if result['identifier'] in expected_outputs:
                # This is where cwl expect the output file to be written
                dst_fn = '/'.join([out_dir.rstrip('/'), expected_outputs[result['identifier']]])

                # TODO Should we handle other type than File reference?
                r = requests.get(result['reference'], allow_redirects=True)
                LOGGER.debug('Fetching result output from {0} to cwl output destination : {1}'.format(
                    result['reference'],
                    dst_fn
                ))
                with open(dst_fn, mode='wb') as dst_fh:
                    dst_fh.write(r.content)

    def get_job_status(self, job_id):
        response = requests.get(self.url + '/processes/' + self.process_id + '/jobs/' + job_id,
                                headers={'Accept': 'application/json'},
                                cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()
        return response.json()

    def get_job_results(self, job_id):
        response = requests.get(self.url + '/processes/' + self.process_id + '/jobs/' + job_id + '/results',
                                headers={'Accept': 'application/json'},
                                cookies=self.cookies,
                                verify=self.verify)
        response.raise_for_status()
        return response.json()

    def host_file(self, fn):
        registry = app.conf['PYRAMID_REGISTRY']
        twitcher_output_url = registry.settings.get('twitcher.wps_output_url')
        twitcher_output_path = registry.settings.get('twitcher.wps_output_path')
        fn = fn.replace('file://', '')

        if not fn.startswith(twitcher_output_path):
            raise Exception('Cannot host files outside of the output path : {0}'.format(fn))
        return fn.replace(twitcher_output_path, twitcher_output_url)

