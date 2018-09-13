import json
import logging
import os
from time import sleep
import requests
from twitcher.cwl_wps_workflows import status
from twitcher.cwl_wps_workflows.status import status_categories


LOGGER_LEVEL = os.getenv('TWITCHER_LOGGER_LEVEL', logging.INFO)
logging.basicConfig(format='%(levelname)s:%(message)s', level=LOGGER_LEVEL)
LOGGER = logging.getLogger(__name__)
DEFAULT_TMP_PREFIX = "tmp"


class WpsProcess(object):
    def __init__(self, url, process_id, deploy_body, cookies):
        self.url = url
        self.process_id = process_id
        self.deploy_body = deploy_body
        self.cookies = cookies

    def is_deployed(self):
        return self.describe_process() is not None

    def describe_process(self):
        response = requests.get(self.url + self.process_id, headers={'Accept': 'application/json'},
                                cookies=self.cookies)
        if response.status_code == 200:
            return response.json()
        return None

    def deploy(self):
        response = requests.post(self.url, json=self.deploy_body,
                                 headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                                 cookies=self.cookies)
        if response.status_code != 201:
            raise Exception

    def execute(self, workflow_inputs):
        execute_body = json.loads('{"inputs": []}')
        for workflow_input_key, workflow_input_value in workflow_inputs.items():
            json_input = json.loads('{}');
            json_input['identifier'] = workflow_input_key;
            if type(workflow_input_value) is list:
                json_input['value'] = []
                for workflow_input_value_item in workflow_input_value:
                    json_input['value'].append(workflow_input_value_item['location'])
            else:
                json_input['value'] = workflow_input_value
            execute_body['inputs'].append(json_input)

        response = requests.post(self.url + self.process_id + '/jobs', json=execute_body,
                                 headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                                 cookies=self.cookies)
        if response.status_code != 201:
            raise Exception
        job_id = response.json()['jobID']
        job_status = response.json()['status']

        while job_status not in status_categories[status.STATUS_FINISHED]:
            LOGGER.info("Waiting")
            sleep(5)
            job_status = self.get_job_status(job_id)

        if job_status == status.STATUS_FAILED:
            raise Exception(job_status)

        return self.get_job_results(job_id)

    def get_job_status(self, job_id):
        response = requests.get(self.url + self.process_id + '/jobs/' + job_id, headers={'Accept': 'application/json'})
        if response.status_code != 200:
            raise Exception
        return response.json()['status']

    def get_job_results(self, job_id):
        # don't know the format of the output
        response = requests.get(self.url + self.process_id + '/jobs/' + job_id + '/results',
                                headers={'Accept': 'application/json'})
        if response.status_code != 200:
            raise Exception
        return response.json()

if __name__ == "__main__":
    cookie = {'auth_tkt': 'd7890d6644880ae5ca30c6663b345694b5b90073d3dec2a6925e888b37d3211aa10168d15b441ef2d2cd8f70064519fda06fb526a26f1d8740a5496c07233c505b8715e536!userid_type:int;',
              'path': '/;', 'domain': '.ogc-ems.crim.ca;', 'Expires': 'Tue, 19 Jan 2038 03:14:07 GMT;'}
    with open('example/SFS-graph-deploy.json') as json_file:
        deploy_json_body = json.load(json_file)

    wps_process = WpsProcess('https://ogc-ades.crim.ca/twitcher/processes/', 'sfs_graph',
                             deploy_body=deploy_json_body, cookies=cookie)
    if wps_process.is_deployed():
        print('OK')
    print(json.dumps(wps_process.describe_process(), indent=4, sort_keys=True))
