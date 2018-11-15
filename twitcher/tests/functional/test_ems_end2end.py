from twitcher.tests.utils import get_test_twitcher_app, get_settings_from_testapp, get_setting, Null
from twitcher.config import TWITCHER_CONFIGURATION_EMS
from twitcher.wps_restapi.utils import wps_restapi_base_url
from twitcher.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from twitcher.owsproxy import owsproxy_url
from twitcher.utils import get_twitcher_url
from twitcher.status import (
    STATUS_SUCCEEDED,
    STATUS_RUNNING,
    STATUS_FINISHED,
    job_status_values,
    job_status_categories,
)
from typing import Text, Dict, Optional
from unittest import TestCase
from pyramid import testing
from pyramid.httpexceptions import HTTPOk, HTTPCreated, HTTPBadRequest, HTTPUnauthorized, HTTPNotFound
# noinspection PyPackageRequirements
from webtest import TestApp
from copy import deepcopy
import unittest
# noinspection PyPackageRequirements
import pytest
import requests
import time
import os


class ProcessInfo(object):
    def __init__(self, process_id, test_id=None, deploy_payload=None, execute_payload=None):
        # type: (Text, Optional[Text], Optional[Dict], Optional[Dict]) -> None
        self.id = process_id
        self.test_id = test_id
        self.deploy_payload = deploy_payload
        self.execute_payload = execute_payload


@unittest.skipIf(not len(str(os.getenv('TEST_SERVER_HOSTNAME', ''))), reason="Test server not defined!")
@pytest.mark.skipif(not len(str(os.getenv('TEST_SERVER_HOSTNAME', ''))), reason="Test server not defined!")
class End2EndEMSTestCase(TestCase):
    __settings__ = None
    test_processes_info = dict()
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    app = None  # type: TestApp

    TWITCHER_URL = None
    TWITCHER_RESTAPI_URL = None
    TWITCHER_PROTECTED_URL = None
    WSO2_HOSTNAME = None
    WSO2_CLIENT_ID = None
    WSO2_CLIENT_SECRET = None
    ALICE_USERNAME = None
    ALICE_PASSWORD = None
    BOB_USERNAME = None
    BOB_PASSWORD = None

    @classmethod
    def setUpClass(cls):
        # TODO: adjust environment variables accordingly to the server to be tested
        cls.TEST_SERVER_HOSTNAME = os.getenv('TEST_SERVER_HOSTNAME')
        cls.app = TestApp(cls.TEST_SERVER_HOSTNAME)

        cls.MAGPIE_URL = '{}/magpie'.format(cls.TEST_SERVER_HOSTNAME)
        cls.TWITCHER_URL = get_twitcher_url(cls.settings())
        cls.TWITCHER_RESTAPI_URL = wps_restapi_base_url(cls.settings())
        cls.TWITCHER_PROTECTED_URL = owsproxy_url(cls.settings())
        cls.TWITCHER_PROTECTED_EMS_URL = cls.TWITCHER_URL + cls.TWITCHER_PROTECTED_URL + '/ems'
        cls.WSO2_HOSTNAME = get_setting('WSO2_HOSTNAME', cls.app)
        cls.WSO2_CLIENT_ID = get_setting('WSO2_CLIENT_ID', cls.app)
        cls.WSO2_CLIENT_SECRET = get_setting('WSO2_CLIENT_SECRET', cls.app)
        cls.ALICE_USERNAME = get_setting('ALICE_USERNAME', cls.app)
        cls.ALICE_PASSWORD = get_setting('ALICE_PASSWORD', cls.app)
        cls.ALICE_CREDENTIALS = {'username': cls.ALICE_USERNAME, 'password': cls.ALICE_PASSWORD}
        cls.BOB_USERNAME = get_setting('BOB_USERNAME', cls.app)
        cls.BOB_PASSWORD = get_setting('BOB_PASSWORD', cls.app)
        cls.BOB_CREDENTIALS = {'username': cls.BOB_USERNAME, 'password': cls.BOB_PASSWORD}

        required_params = {
            'TWITCHER_URL':             cls.TWITCHER_URL,
            'TWITCHER_RESTAPI_URL':     cls.TWITCHER_RESTAPI_PATH,
            'TWITCHER_PROTECTED_PATH':  cls.TWITCHER_PROTECTED_PATH,
            'WSO2_HOSTNAME':            cls.WSO2_HOSTNAME,
            'WSO2_CLIENT_ID':           cls.WSO2_CLIENT_ID,
            'WSO2_CLIENT_SECRET':       cls.WSO2_CLIENT_SECRET,
            'ALICE_USERNAME':           cls.ALICE_USERNAME,
            'ALICE_PASSWORD':           cls.ALICE_PASSWORD,
            'BOB_USERNAME':             cls.BOB_USERNAME,
            'BOB_PASSWORD':             cls.BOB_PASSWORD,
        }
        for param in required_params:
            assert not isinstance(required_params[param], Null), \
                "Missing required parameter `{}` to run end-2-end EMS tests!".format(param)

        cls.validate_test_server()
        cls.setup_processes_payloads()

    @classmethod
    def tearDownClass(cls):
        cls.clear_test_processes()
        testing.tearDown()

    @classmethod
    def settings(cls):
        """Provide basic settings that must be defined to use various Twitcher utility functions."""
        def update_non_override(dict_settings, dict_parameters):
            [dict_settings.update({k: v}) for k, v in dict_parameters.items()
             if k not in dict_settings or (v is not None and dict_settings[k] is None)]

        if not cls.__settings__:
            cls.__settings__ = get_settings_from_testapp(cls.app)
            update_non_override(cls.__settings__, {
                'magpie.url': cls.TEST_SERVER_HOSTNAME + '/magpie',
                'twitcher.url': cls.TEST_SERVER_HOSTNAME + '/twitcher',
                'twitcher.configuration': TWITCHER_CONFIGURATION_EMS,
                'twitcher.wps_restapi_path': get_setting('TWITCHER_RESTAPI_PATH', cls.app),
                'twitcher.ows_proxy_protected_path': get_setting('TWITCHER_PROTECTED_URL', cls.app),
            })
        return cls.__settings__

    @staticmethod
    def get_test_processes(cls, process_id):
        return cls.test_processes_info.get(process_id)

    @classmethod
    def setup_test_processes(cls):
        cls.PROCESS_STACKER_ID = 'Stacker'
        cls.PROCESS_SFS_ID = 'SFS'
        cls.PROCESS_WORKFLOW_ID = 'Workflow'
        for process in [cls.PROCESS_STACKER_ID, cls.PROCESS_SFS_ID, cls.PROCESS_WORKFLOW_ID]:
            cls.test_processes_info.update({process: cls.retrieve_process_info(process)})

    @classmethod
    def retrieve_process_info(cls, process_id):
        base = 'https://raw.githubusercontent.com/crim-ca/testbed14/master/application-packages'
        deploy_path = '{base}/{proc}/DeployProcess_{proc}.json'.format(base=base, proc=process_id)
        execute_path = '{base}/{proc}/Execute_{proc}.json'.format(base=base, proc=process_id)
        deploy_payload = cls.retrieve_payload(deploy_path)
        new_process_id = cls.get_test_process_id(deploy_payload['processDescription']['process']['id'])
        deploy_payload['processDescription']['process']['id'] = new_process_id
        execute_payload = cls.retrieve_payload(execute_path)
        return ProcessInfo(process_id, new_process_id, deploy_payload, execute_payload)

    @classmethod
    def retrieve_payload(cls, url):
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def get_test_process_id(cls, real_process_id):
        return '{}_{}'.format(cls.__name__, real_process_id)

    @classmethod
    def clear_test_processes(cls):
        for process_id in cls.test_processes_info:
            proc_test_id = cls.test_processes_info[process_id]['test_id']
            path = '{}/processes/{}'.format(cls.TWITCHER_PROTECTED_EMS_URL, proc_test_id)
            resp = cls.app.delete(path, headers=cls.headers)
            if resp.status_code not in (HTTPOk.code, HTTPNotFound.code):
                resp.raise_for_status()

    @classmethod
    def login(cls, username, password):
        """Login using WSO2 and retrieve the cookie packaged as `{'Authorization': 'Bearer <access_token>'}` header."""
        data = {
            'grant_type': 'password',
            'scope': 'openid',
            'client_id': cls.WSO2_CLIENT_ID,
            'client_secret': cls.WSO2_CLIENT_SECRET,
            'username': username,
            'password': password
        }
        headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
        resp = requests.post('{}/oauth2/token'.format(cls.WSO2_HOSTNAME), data=data, headers=headers)
        if resp.status_code == HTTPOk.code:
            access_token = resp.json().get('access_token')
            assert access_token is not None, "Failed login!"
            return {'Authorization': 'Bearer {}'.format(access_token)}
        resp.raise_for_status()

    @classmethod
    def validate_test_server(cls):
        cls.app.get(cls.MAGPIE_URL, headers=cls.headers, status=HTTPOk.code)
        cls.app.get(cls.WSO2_HOSTNAME, headers=cls.headers, status=HTTPOk.code)
        resp = cls.app.get(cls.TWITCHER_RESTAPI_URL, headers=cls.headers, status=HTTPOk.code)
        assert resp.json.get('configuration') == TWITCHER_CONFIGURATION_EMS, "Twitcher must be configured as EMS."

    def test_end2end(self):
        self.clear_test_processes()

        token_a = self.login(**self.ALICE_CREDENTIALS)
        token_b = self.login(**self.ALICE_CREDENTIALS)
        headers_a = deepcopy(self.headers)
        headers_a.update(token_a)
        headers_b = deepcopy(self.headers)
        headers_b.update(token_b)

        # list processes (none of tests)
        path = '{}/processes'.format(self.TWITCHER_PROTECTED_EMS_URL)
        resp = self.app.get(path, headers=headers_a, status=HTTPOk.code)
        proc = resp.json.get('processes')
        assert isinstance(proc, list)
        assert len(filter(lambda p: p['id'] in self.test_processes_info, proc)) == 0, "Test processes shouldn't exist!"

        # deploy process application
        self.app.post_json(path, headers=headers_a, status=HTTPCreated.code,
                           params=self.test_processes_info[self.PROCESS_STACKER_ID].deploy_payload)
        # deploy process workflow with missing step
        self.app.post_json(path, headers=headers_a, status=HTTPBadRequest.code,
                           params=self.test_processes_info[self.PROCESS_WORKFLOW_ID].deploy_payload)
        # deploy other process step
        self.app.post_json(path, headers=headers_a, status=HTTPCreated.code,
                           params=self.test_processes_info[self.PROCESS_SFS_ID].deploy_payload)
        # deploy process workflow with all steps available
        self.app.post_json(path, headers=headers_a, status=HTTPCreated.code,
                           params=self.test_processes_info[self.PROCESS_WORKFLOW_ID].deploy_payload)

        # processes visible by alice
        resp = self.app.get(path, headers=headers_a, status=HTTPOk.code)
        proc = resp.json.get('processes')
        found_processes = filter(lambda p: p['id'] in self.test_processes_info, proc)
        assert len(found_processes) == len(self.test_processes_info), "Test processes should exist."

        # processes not yet visible by bob
        resp = self.app.get(path, headers=headers_b, status=HTTPOk.code)
        proc = resp.json.get('processes')
        found_processes = filter(lambda p: p['id'] in self.test_processes_info, proc)
        assert len(found_processes) == 0, "Test processes shouldn't be visible by bob."

        # processes visibility
        visible = {'value': VISIBILITY_PUBLIC}
        for process_id, process_info in self.test_processes_info.items():
            # get private visibility initially
            process_path = '{}/processes/{}'.format(self.TWITCHER_PROTECTED_EMS_URL, process_info.test_id)
            visible_path = '{}/visibility'.format(process_path)
            execute_path = '{}/jobs'.format(process_path)
            execute_body = process_info.execute_payload
            resp = self.app.get(visible_path, headers=headers_a, status=HTTPOk.code)
            assert resp.json.get('value') == VISIBILITY_PRIVATE, "Process should be private."

            # bob cannot edit, view or execute the process
            self.app.get(process_path, headers=headers_b, status=HTTPUnauthorized.code)
            self.app.put_json(visible_path, headers=headers_b, status=HTTPUnauthorized.code, params=visible)
            self.app.post_json(execute_path, headers=headers_b, status=HTTPUnauthorized.code, params=execute_body)

            # make process visible
            resp = self.app.put_json(visible_path, params=visible, headers=headers_a, status=HTTPOk.code)
            assert resp.json.get('value') == VISIBILITY_PUBLIC, "Process should be public."

            # bob still cannot edit, but can now view and execute the process
            self.app.put_json(visible_path, headers=headers_b, status=HTTPUnauthorized.code, params=visible)
            resp = self.app.get(process_path, headers=headers_b, status=HTTPOk.code)
            assert resp.json.get('process').get('id') == process_id
            resp = self.app.post_json(execute_path, headers=headers_b, status=HTTPCreated.code, params=execute_body)
            assert resp.json.get('status') in job_status_categories[STATUS_RUNNING]
            job_location = resp.json.get('location')
            job_id = resp.json.get('jobID')
            assert job_id and job_location and job_location.endswith(job_id)
            self.validate_test_job_execution(job_location, headers_b)

    def validate_test_job_execution(self, job_location_url, user_headers):
        """
        Validates that the job is stated, running, and pools it until completed successfully.
        Then validates that results are accessible (no data integrity check).
        """
        timeout = 600
        while True:
            assert timeout > 0, "Maximum time reached for job execution test."
            resp = self.app.get(job_location_url, headers=user_headers, status=HTTPOk.code)
            status = resp.json.get('status')
            assert status in job_status_values
            if status in job_status_categories[STATUS_RUNNING]:
                timeout -= 5
                time.sleep(5)
                continue
            elif status in job_status_categories[STATUS_FINISHED]:
                self.assertEquals(status, STATUS_SUCCEEDED, "Job execution `{}` failed.".format(job_location_url))
                break
            self.fail("Unknown job execution status: `{}`.".format(status))
        self.app.get('{}/result'.format(job_location_url), headers=user_headers, status=HTTPOk.code)
