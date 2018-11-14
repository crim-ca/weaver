from twitcher.tests.utils import get_test_twitcher_app, get_settings_from_testapp, get_setting
from twitcher.config import TWITCHER_CONFIGURATION_EMS
from twitcher.wps_restapi.utils import wps_restapi_base_path
from twitcher.owsproxy import owsproxy_path
from twitcher.utils import get_twitcher_url
from unittest import TestCase
from pyramid import testing
from pyramid.httpexceptions import HTTPOk
from copy import deepcopy
import requests


class End2EndEMSTestCase(TestCase):
    headers = {'Accept': 'application/json'}
    app = None
    TWITCHER_URL = None
    TWITCHER_RESTAPI_PATH = None
    TWITCHER_PROTECTED_PATH = None
    WSO2_HOSTNAME = None
    WSO2_CLIENT_ID = None
    WSO2_CLIENT_SECRET = None
    ALICE_USERNAME = None
    ALICE_PASSWORD = None
    BOB_USERNAME = None
    BOB_PASSWORD = None

    def __init__(self):
        super(End2EndEMSTestCase, self).__init__()
        base_url = 'https://github.com/crim-ca/testbed14/blob/master/application-packages'
        self.CWL_PROCESS_STACKER_DEPLOY = '{}/Stacker/DeployProcess_Stacker.json'.format(base_url)
        self.CWL_PROCESS_STACKER_EXECUTE = '{}/Stacker/Execute_Stacker.json'.format(base_url)
        self.CWL_PROCESS_SFS_DEPLOY = '{}/SFS/DeployProcess_SFS.json'.format(base_url)
        self.CWL_PROCESS_SFS_EXECUTE = '{}/SFS/Execute_SFS.json'.format(base_url)
        self.CWL_PROCESS_WORKFLOW_DEPLOY = '{}/Workflow/DeployProcess_Workflow.json'.format(base_url)
        self.CWL_PROCESS_WORKFLOW_EXECUTE = '{}/Workflow/Execute_Workflow.json'.format(base_url)

    @classmethod
    def setUpClass(cls):
        cls.app = get_test_twitcher_app(TWITCHER_CONFIGURATION_EMS)
        cls.TWITCHER_URL = get_twitcher_url(cls.settings())
        cls.TWITCHER_RESTAPI_PATH = wps_restapi_base_path(cls.settings())
        cls.TWITCHER_PROTECTED_PATH = owsproxy_path(cls.settings())
        cls.WSO2_HOSTNAME = get_setting(cls.app, 'WSO2_HOSTNAME')
        cls.WSO2_CLIENT_ID = get_setting(cls.app, 'WSO2_CLIENT_ID')
        cls.WSO2_CLIENT_SECRET = get_setting(cls.app, 'WSO2_CLIENT_SECRET')
        cls.ALICE_USERNAME = get_setting(cls.app, 'ALICE_USERNAME')
        cls.ALICE_PASSWORD = get_setting(cls.app, 'ALICE_PASSWORD')
        cls.ALICE_CREDENTIALS = {'username': cls.ALICE_USERNAME, 'password': cls.ALICE_PASSWORD}
        cls.BOB_USERNAME = get_setting(cls.app, 'BOB_USERNAME')
        cls.BOB_PASSWORD = get_setting(cls.app, 'BOB_PASSWORD')
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
            assert required_params[param] is not None, \
                "Missing required parameter `{}` to run end-2-end EMS tests!".format(param)

    @classmethod
    def tearDownClass(cls):
        testing.tearDown()

    @classmethod
    def settings(cls):
        return get_settings_from_testapp(cls.app)

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
    def check_up(cls):
        cls.app.get(cls.TWITCHER_RESTAPI_PATH, headers=cls.headers, status=HTTPOk.code)

    def test_end2end(self):
        self.check_up()

        token = self.login(**self.ALICE_CREDENTIALS)
        headers = deepcopy(self.headers).update(token)
        path = '{}/ems/processes'.format(self.TWITCHER_RESTAPI_PATH)
        self.app.get(path, headers, status=HTTPOk.code)

        print(self.GITHUB_CWL_PROCESS_STACKER_DEPLOY)
