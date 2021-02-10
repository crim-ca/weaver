import time
import unittest
from copy import deepcopy

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
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.status import STATUS_RUNNING, STATUS_SUCCEEDED
from weaver.visibility import VISIBILITY_PUBLIC


@pytest.mark.functional
class WpsPackageConfigBase(unittest.TestCase):
    json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
    monitor_timeout = 30
    monitor_delta = 1
    settings = {}

    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is WpsPackageConfigBase)
        super(WpsPackageConfigBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        config = setup_config_with_mongodb(settings=cls.settings)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        config = get_test_weaver_config(config)
        setup_mongodb_processstore(config)  # force reset
        cls.job_store = setup_mongodb_jobstore(config)
        cls.app = get_test_weaver_app(config=config, settings=cls.settings)

    @classmethod
    def deploy_process(cls, payload):
        """
        Deploys a process with :paramref:`payload`.

        :returns: resulting tuple of ``(process-description, package)`` JSON responses.
        """
        resp = mocked_sub_requests(cls.app, "post_json", "/processes", data=payload, headers=cls.json_headers)
        assert resp.status_code == 200  # TODO: status should be 201 when properly modified to match API conformance
        path = resp.json["processSummary"]["processDescriptionURL"]
        body = {"value": VISIBILITY_PUBLIC}
        resp = cls.app.put_json("{}/visibility".format(path), params=body, headers=cls.json_headers)
        assert resp.status_code == 200
        info = []
        for pkg_url in [path, "{}/package".format(path)]:
            resp = cls.app.get(pkg_url, headers=cls.json_headers)
            assert resp.status_code == 200
            info.append(deepcopy(resp.json))
        return info

    def monitor_job(self, status_url, timeout=None, delta=None):
        """
        Job polling of status URL until completion or timeout.

        :return: result of the successful job
        :raises AssertionError: when job fails or took too long to complete.
        """
        time.sleep(1)  # small delay to ensure process execution had a change to start before monitoring
        left = timeout or self.monitor_timeout
        delta = delta or self.monitor_delta
        once = True
        resp = None
        while left >= 0 or once:
            resp = self.app.get(status_url, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.json["status"] in [STATUS_RUNNING, STATUS_SUCCEEDED]
            if resp.json["status"] == STATUS_SUCCEEDED:
                break
            time.sleep(delta)
            once = False
            left -= delta
        assert resp.json["status"] == STATUS_SUCCEEDED
        resp = self.app.get("{}/result".format(status_url), headers=self.json_headers)
        assert resp.status_code == 200
        return resp.json
