import json
import time
import unittest
from copy import deepcopy
from typing import TYPE_CHECKING

import pyramid.testing
import pytest

from tests.utils import (
    get_test_weaver_app,
    get_test_weaver_config,
    mocked_sub_requests,
    setup_config_with_celery,
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_mongodb_jobstore,
    setup_mongodb_processstore
)
from weaver.database import get_db
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.processes.constants import PROCESS_SCHEMA_OLD
from weaver.status import STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED
from weaver.utils import fully_qualified_name
from weaver.visibility import VISIBILITY_PUBLIC

if TYPE_CHECKING:
    from typing import Dict, Optional
    from weaver.typedefs import JSON, SettingsType


@pytest.mark.functional
class WpsConfigBase(unittest.TestCase):
    json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
    monitor_timeout = 30
    monitor_delta = 1
    settings = {}  # type: SettingsType

    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is WpsConfigBase)
        super(WpsConfigBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        config = setup_config_with_mongodb(settings=cls.settings)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        config = get_test_weaver_config(config)
        cls.process_store = setup_mongodb_processstore(config)  # force reset
        cls.job_store = setup_mongodb_jobstore(config)
        cls.app = get_test_weaver_app(config=config, settings=cls.settings)
        cls.db = get_db(config)
        cls.config = config
        cls.settings.update(cls.config.registry.settings)  # back propagate changes

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    @classmethod
    def describe_process(cls, process_id, describe_schema=PROCESS_SCHEMA_OGC):
        path = "/processes/{}?schema={}".format(process_id, describe_schema)
        resp = cls.app.get(path, headers=cls.json_headers)
        assert resp.status_code == 200
        return deepcopy(resp.json)

    @classmethod
    def deploy_process(cls, payload, describe_schema=PROCESS_SCHEMA_OGC):
        # type: (JSON, str) -> JSON
        """
        Deploys a process with :paramref:`payload`.

        :returns: resulting tuple of ``(process-description, package)`` JSON responses.
        """
        resp = mocked_sub_requests(cls.app, "post_json", "/processes", data=payload, headers=cls.json_headers)
        assert resp.status_code == 201, "Expected successful deployment.\nError:\n{}".format(resp.text)
        path = resp.json["processSummary"]["processDescriptionURL"]
        body = {"value": VISIBILITY_PUBLIC}
        resp = cls.app.put_json("{}/visibility".format(path), params=body, headers=cls.json_headers)
        assert resp.status_code == 200, "Expected successful visibility.\nError:\n{}".format(resp.text)
        info = []
        for info_path in ["{}?schema={}".format(path, describe_schema), "{}/package".format(path)]:
            resp = cls.app.get(info_path, headers=cls.json_headers)
            assert resp.status_code == 200
            info.append(deepcopy(resp.json))
        return info

    def _try_get_logs(self, status_url):
        _resp = self.app.get("{}/logs".format(status_url), headers=self.json_headers)
        if _resp.status_code == 200:
            return "Error logs:\n{}".format("\n".join(_resp.json))
        return ""

    def fully_qualified_test_process_name(self):
        return fully_qualified_name(self).replace(".", "-")

    def monitor_job(self, status_url, timeout=None, delta=None, return_status=False, wait_for_status=STATUS_SUCCEEDED):
        # type: (str, Optional[int], Optional[int], bool, str) -> Dict[str, JSON]
        """
        Job polling of status URL until completion or timeout.

        :param status_url: URL with job ID where to monitor execution.
        :param timeout: timeout of monitoring until completion or abort.
        :param delta: interval (seconds) between polling monitor requests.
        :param return_status: return final status body instead of results once job completed.
        :param wait_for_status: monitor until the requested status is reached (default: when job is completed)
        :return: result of the successful job, or the status body if requested.
        :raises AssertionError: when job fails or took too long to complete.
        """

        def check_job_status(_resp, running=False):
            body = _resp.json
            pretty = json.dumps(body, indent=2, ensure_ascii=False)
            statuses = [STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED] if running else [STATUS_SUCCEEDED]
            assert _resp.status_code == 200, "Execution failed:\n{}\n{}".format(pretty, self._try_get_logs(status_url))
            assert body["status"] in statuses, "Error job info:\n{}\n{}".format(pretty, self._try_get_logs(status_url))
            return body["status"] == wait_for_status

        time.sleep(1)  # small delay to ensure process execution had a change to start before monitoring
        left = timeout or self.monitor_timeout
        delta = delta or self.monitor_delta
        once = True
        resp = None
        while left >= 0 or once:
            resp = self.app.get(status_url, headers=self.json_headers)
            if check_job_status(resp, running=True):
                break
            time.sleep(delta)
            once = False
            left -= delta
        check_job_status(resp)
        if return_status:
            return resp.json
        resp = self.app.get("{}/results".format(status_url), headers=self.json_headers)
        assert resp.status_code == 200, "Error job info:\n{}".format(resp.json)
        return resp.json

    def get_outputs(self, status_url):
        resp = self.app.get(status_url + "/outputs", headers=self.json_headers)
        body = resp.json
        pretty = json.dumps(body, indent=2, ensure_ascii=False)
        assert resp.status_code == 200, "Get outputs failed:\n{}\n{}".format(pretty, self._try_get_logs(status_url))
        return body
