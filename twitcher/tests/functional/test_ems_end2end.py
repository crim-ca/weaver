from twitcher.tests.utils import get_settings_from_config_ini, get_settings_from_testapp, get_setting, Null
from twitcher.config import TWITCHER_CONFIGURATION_EMS
from twitcher.wps_restapi.utils import wps_restapi_base_url
from twitcher.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from twitcher.owsproxy import owsproxy_base_url
from twitcher.utils import get_twitcher_url
from twitcher.status import (
    STATUS_SUCCEEDED,
    STATUS_RUNNING,
    STATUS_FINISHED,
    job_status_values,
    job_status_categories,
)
from six.moves.urllib.parse import urlparse
from typing import Text, Dict, Optional, Any, Tuple, Union
from unittest import TestCase
from pyramid import testing
from pyramid.settings import asbool
from pyramid.httpexceptions import HTTPOk, HTTPCreated, HTTPBadRequest, HTTPUnauthorized, HTTPNotFound
# noinspection PyPackageRequirements
from webtest import TestApp, TestResponse
from copy import deepcopy
import unittest
# noinspection PyPackageRequirements
import pytest
import requests
import time
import json
import os


class ProcessInfo(object):
    def __init__(self, process_id, test_id=None, deploy_payload=None, execute_payload=None):
        # type: (Text, Optional[Text], Optional[Dict], Optional[Dict]) -> None
        self.id = process_id
        self.test_id = test_id
        self.deploy_payload = deploy_payload
        self.execute_payload = execute_payload


@pytest.mark.online
@pytest.mark.skipif(not len(str(os.getenv('TEST_SERVER_HOSTNAME', ''))), reason="Test server not defined!")
@unittest.skipIf(not len(str(os.getenv('TEST_SERVER_HOSTNAME', ''))), reason="Test server not defined!")
class End2EndEMSTestCase(TestCase):
    __settings__ = None
    test_processes_info = dict()
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    cookies = dict()
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
        cls.TEST_SERVER_MAGPIE_PATH = os.getenv('TEST_SERVER_MAGPIE_PATH', '/magpie')
        cls.TEST_SERVER_TWITCHER_PATH = os.getenv('TEST_SERVER_TWITCHER_PATH', '/twitcher')
        cls.app = TestApp(cls.TEST_SERVER_HOSTNAME)

        cls.MAGPIE_URL = cls.settings().get('magpie.url')
        cls.TWITCHER_URL = get_twitcher_url(cls.settings())
        cls.TWITCHER_RESTAPI_URL = wps_restapi_base_url(cls.settings())
        cls.TWITCHER_PROTECTED_URL = owsproxy_base_url(cls.settings())
        cls.TWITCHER_PROTECTED_EMS_URL = os.getenv('TWITCHER_PROTECTED_EMS_URL',
                                                   '{}/ems'.format(cls.TWITCHER_PROTECTED_URL))

        # if enabled, login uses WSO2 external provider, otherwise use Magpie with same credentials
        # NOTE: this will correspond to two different users (WSO2 external user will have `_wso2` appended)
        cls.WSO2_ENABLED = asbool(os.getenv('WSO2_ENABLED', True))

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
            'MAGPIE_URL':               cls.MAGPIE_URL,
            'TWITCHER_URL':             cls.TWITCHER_URL,
            'TWITCHER_RESTAPI_URL':     cls.TWITCHER_RESTAPI_URL,
            'TWITCHER_PROTECTED_URL':   cls.TWITCHER_PROTECTED_URL,
            'ALICE_USERNAME':           cls.ALICE_USERNAME,
            'ALICE_PASSWORD':           cls.ALICE_PASSWORD,
            'BOB_USERNAME':             cls.BOB_USERNAME,
            'BOB_PASSWORD':             cls.BOB_PASSWORD,
        }
        if cls.WSO2_ENABLED:
            required_params.update({
                'WSO2_HOSTNAME':        cls.WSO2_HOSTNAME,
                'WSO2_CLIENT_ID':       cls.WSO2_CLIENT_ID,
                'WSO2_CLIENT_SECRET':   cls.WSO2_CLIENT_SECRET,
            })
        for param in required_params:
            assert not isinstance(required_params[param], Null), \
                "Missing required parameter `{}` to run end-2-end EMS tests!".format(param)

        cls.validate_test_server()
        cls.setup_test_processes()

    @classmethod
    def tearDownClass(cls):
        cls.clear_test_processes()
        testing.tearDown()

    @classmethod
    def settings(cls):
        # type: (...) -> Dict[Text, Text]
        """Provide basic settings that must be defined to use various Twitcher utility functions."""
        if not cls.__settings__:
            magpie_url = os.getenv('MAGPIE_URL',
                                   '{}{}'.format(cls.TEST_SERVER_HOSTNAME, cls.TEST_SERVER_MAGPIE_PATH))
            twitcher_url = os.getenv('TWITCHER_URL',
                                     '{}{}'.format(cls.TEST_SERVER_HOSTNAME, cls.TEST_SERVER_TWITCHER_PATH))
            cls.__settings__ = get_settings_from_testapp(cls.app)
            cls.__settings__.update(get_settings_from_config_ini())
            cls.__settings__.update({
                'magpie.url': magpie_url,
                'twitcher.url': twitcher_url,
                'twitcher.configuration': TWITCHER_CONFIGURATION_EMS,
            })
        return cls.__settings__

    @classmethod
    def get_test_process(cls, process_id):
        # type: (Text) -> ProcessInfo
        return cls.test_processes_info.get(process_id)

    @classmethod
    def setup_test_processes(cls):
        # type: (...) -> None
        cls.PROCESS_STACKER_ID = 'Stacker'
        cls.PROCESS_SFS_ID = 'SFS'
        cls.PROCESS_WORKFLOW_ID = 'Workflow'
        for process in [cls.PROCESS_STACKER_ID, cls.PROCESS_SFS_ID, cls.PROCESS_WORKFLOW_ID]:
            cls.test_processes_info.update({process: cls.retrieve_process_info(process)})

    @classmethod
    def retrieve_process_info(cls, process_id):
        # type: (Text) -> ProcessInfo
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
        # type: (Text) -> Dict
        resp = requests.get(url)
        cls.assert_response(resp, message="Invalid payload not retrieved.")
        return resp.json()

    @classmethod
    def get_test_process_id(cls, real_process_id):
        # type: (Text) -> Text
        return '{}_{}'.format(cls.__name__, real_process_id)

    @classmethod
    def clear_test_processes(cls):
        for process_id, process_info in cls.test_processes_info.items():
            path = '{}/processes/{}'.format(cls.TWITCHER_PROTECTED_EMS_URL, process_info.test_id)
            headers, cookies = cls.user_headers_cookies(cls.ALICE_CREDENTIALS)
            resp = cls.request('DELETE', path, headers=headers, cookies=cookies, expect_errors=True)
            # unauthorized also would mean the process doesn't exist since Alice should have permissions on it
            if resp.status_code not in (HTTPOk.code, HTTPUnauthorized.code, HTTPNotFound.code):
                raise Exception("Failed cleanup of test processes! " +
                                "Unexpected HTTP code: `{}`.".format(resp.status_code))

    @classmethod
    def login(cls, username, password):
        # type: (Text, Text) -> Tuple[Dict[str, str], bool]
        """
        Login using WSO2 or Magpie according to `WSO2_ENABLED` to retrieve session cookies.

        WSO2:
            Retrieves the cookie packaged as `{'Authorization': 'Bearer <access_token>'}` header, and lets the
            Magpie external provider login procedure complete the Authorization header => Cookie conversion.

        Magpie:
            Retrieves the cookie using a simple local user login.

        :returns: (Headers/Cookies, False/True) respectively to WSO2/Magpie login.
        """
        if cls.WSO2_ENABLED:
            data = {
                'grant_type': 'password',
                'scope': 'openid',
                'client_id': cls.WSO2_CLIENT_ID,
                'client_secret': cls.WSO2_CLIENT_SECRET,
                'username': username,
                'password': password
            }
            headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
            resp = requests.post('{}/oauth2/token'.format(cls.WSO2_HOSTNAME), json=data, headers=headers)
            if resp.status_code == HTTPOk.code:
                access_token = resp.json().get('access_token')
                assert access_token is not None, "Failed login!"
                return {'Authorization': 'Bearer {}'.format(access_token)}, False
            cls.assert_response(resp)
        else:
            data = {'user_name': username, 'password': password}
            headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
            resp = requests.post('{}/signin'.format(cls.MAGPIE_URL), json=data, headers=headers)
            if resp.status_code == HTTPOk.code:
                return dict(resp.cookies), False
            cls.assert_response(resp)

    @classmethod
    def user_headers_cookies(cls, credentials):
        # type: (Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]
        tokens, are_cookies = cls.login(**credentials)
        headers = deepcopy(cls.headers)
        cookies = deepcopy(cls.cookies)
        if are_cookies:
            cookies.update(tokens)
        else:
            headers.update(tokens)
        return headers, cookies

    @classmethod
    def request(cls, method, url, **kw):
        # type: (Text, Text, Optional[Any]) -> TestResponse
        """
        Executes the request, but following any server prior redirects as needed.
        Also prepares JSON body and obvious error handling according to a given status code.
        """
        status = kw.pop('status', None)
        json_body = kw.pop('json', None)
        method = method.upper()

        # use `requests.Request` with cases that doesn't work well with `webtest.TestApp`
        url_parsed = urlparse(url)
        is_localhost = url_parsed.hostname == 'localhost'
        has_port = url_parsed.port is not None
        is_remote = hasattr(cls.app.app, 'net_loc') and cls.app.app.net_loc != url_parsed.hostname
        if is_localhost and has_port or is_remote:
            kw.update({'verify': False})
            resp = requests.request(method, url, **kw)
            if resp.headers.get('Content-Type') == 'application/json':
                setattr(resp, 'json', resp.json())

        else:
            max_redirects = kw.pop('max_redirects', 5)

            if json_body is not None:
                kw.update({'params': json.dumps(json_body, cls=json.JSONEncoder)})
            if status and status >= 300:
                kw.update({'expect_errors': True})
            cookies = kw.pop('cookies', dict())
            for cookie_name, cookie_value in cookies.items():
                cls.app.set_cookie(cookie_name, cookie_value)
            resp = cls.app._gen_request(method, url, **kw)

            while 300 <= resp.status_code < 400 and max_redirects > 0:
                resp = resp.follow()
                max_redirects -= 1
            assert max_redirects >= 0
            cls.app.reset()  # reset cookies as required

        cls.assert_response(resp, status)
        return resp

    @classmethod
    def assert_response(cls, response, status=None, message=''):
        # type: (Union[TestResponse, requests.Response], Optional[int], Optional[str]) -> None
        rs = response.status_code
        reason = getattr(response, 'reason', '')
        content = getattr(response, 'content', '')
        msg = "HTTPError: {} {} [{}, {}]".format(response.status_code, reason, message, content)
        assert (status is not None and status == rs) or (status is None and rs < 400), msg

    @classmethod
    def validate_test_server(cls):
        # verify that servers are up and ready
        for server_url in [cls.MAGPIE_URL, cls.TWITCHER_URL, cls.WSO2_HOSTNAME]:
            cls.request('GET', server_url, headers=cls.headers, status=HTTPOk.code)
        # verify that EMS configuration requirement is met
        resp = cls.request('GET', cls.TWITCHER_RESTAPI_URL, headers=cls.headers, status=HTTPOk.code)
        assert resp.json.get('configuration') == TWITCHER_CONFIGURATION_EMS, "Twitcher must be configured as EMS."

    def test_end2end(self):
        """The actual test!"""
        self.clear_test_processes()

        headers_a, cookies_a = self.user_headers_cookies(self.ALICE_CREDENTIALS)
        headers_b, cookies_b = self.user_headers_cookies(self.BOB_CREDENTIALS)

        # list processes (none of tests)
        path = '{}/processes'.format(self.TWITCHER_PROTECTED_EMS_URL)
        resp = self.request('GET', path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
        proc = resp.json.get('processes')
        assert isinstance(proc, list)
        assert len(filter(lambda p: p['id'] in self.test_processes_info, proc)) == 0, "Test processes shouldn't exist!"

        # deploy process application
        self.request('POST', path, headers=headers_a, cookies=cookies_a, status=HTTPCreated.code,
                     json=self.test_processes_info[self.PROCESS_STACKER_ID].deploy_payload)
        # deploy process workflow with missing step
        self.request('POST', path, headers=headers_a, cookies=cookies_a, status=HTTPBadRequest.code,
                     json=self.test_processes_info[self.PROCESS_WORKFLOW_ID].deploy_payload)
        # deploy other process step
        self.request('POST', path, headers=headers_a, cookies=cookies_a, status=HTTPCreated.code,
                     json=self.test_processes_info[self.PROCESS_SFS_ID].deploy_payload)
        # deploy process workflow with all steps available
        self.request('POST', path, headers=headers_a, cookies=cookies_a, status=HTTPCreated.code,
                     json=self.test_processes_info[self.PROCESS_WORKFLOW_ID].deploy_payload)

        # processes visible by alice
        resp = self.request('GET', path, headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
        proc = resp.json.get('processes')
        found_processes = filter(lambda p: p['id'] in self.test_processes_info, proc)
        assert len(found_processes) == len(self.test_processes_info), "Test processes should exist."

        # processes not yet visible by bob
        resp = self.request('GET', path, headers=headers_b, cookies=cookies_b, status=HTTPOk.code)
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
            resp = self.request('GET', visible_path,
                                headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
            assert resp.json.get('value') == VISIBILITY_PRIVATE, "Process should be private."

            # bob cannot edit, view or execute the process
            self.request('GET', process_path,
                         headers=headers_b, cookies=cookies_b, status=HTTPUnauthorized.code)
            self.request('PUT', visible_path, json=visible,
                         headers=headers_b, cookies=cookies_b, status=HTTPUnauthorized.code)
            self.request('POST', execute_path, json=execute_body,
                         headers=headers_b, cookies=cookies_b, status=HTTPUnauthorized.code)

            # make process visible
            resp = self.request('PUT', visible_path, json=visible,
                                headers=headers_a, cookies=cookies_a, status=HTTPOk.code)
            assert resp.json.get('value') == VISIBILITY_PUBLIC, "Process should be public."

            # bob still cannot edit, but can now view and execute the process
            self.request('PUT', visible_path,  json=visible,
                         headers=headers_b, cookies=cookies_b, status=HTTPUnauthorized.code)
            resp = self.request('GET', process_path,
                                headers=headers_b, cookies=cookies_b, status=HTTPOk.code)
            assert resp.json.get('process').get('id') == process_id
            resp = self.request('POST', execute_path, json=execute_body,
                                headers=headers_b, cookies=cookies_b, status=HTTPCreated.code)
            assert resp.json.get('status') in job_status_categories[STATUS_RUNNING]
            job_location = resp.json.get('location')
            job_id = resp.json.get('jobID')
            assert job_id and job_location and job_location.endswith(job_id)
            self.validate_test_job_execution(job_location, headers_b, cookies_b)

    def validate_test_job_execution(self, job_location_url, user_headers, user_cookies):
        # type: (str, Dict[str, str], Dict[str, str]) -> None
        """
        Validates that the job is stated, running, and pools it until completed successfully.
        Then validates that results are accessible (no data integrity check).
        """
        timeout = 600
        while True:
            assert timeout > 0, "Maximum time reached for job execution test."
            resp = self.request('GET', job_location_url,
                                headers=user_headers, cookies=user_cookies, status=HTTPOk.code)
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
        self.request('GET', '{}/result'.format(job_location_url),
                     headers=user_headers, cookies=user_cookies, status=HTTPOk.code)
