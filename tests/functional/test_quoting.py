import contextlib
import os
import random
from typing import TYPE_CHECKING

import mock
import pytest
import yaml

from tests.functional import APP_PKG_ROOT
from tests.functional.utils import WpsConfigBase
from tests.utils import mocked_execute_celery, mocked_sub_requests
from weaver.execute import ExecuteTransmissionMode
from weaver.quotation.status import QuoteStatus
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from weaver.datatype import Process, Quote


def mocked_estimate_process_quote(quote, process):  # noqa
    # type: (Quote, Process) -> Quote
    """
    Mock :term:`Quote` estimation in the even that the real operation is updated.
    """
    quote.seconds = int(random.uniform(5, 60) * 60 + random.uniform(5, 60))  # nosec: B311
    quote.price = float(random.uniform(0, 100) * quote.seconds)              # nosec: B311
    quote.currency = "CAD"
    return quote


@pytest.mark.functional
@pytest.mark.quotation
class WpsQuotationTest(WpsConfigBase):
    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        super(WpsQuotationTest, cls).setUpClass()
        cls.test_processes = set()
        cls.deploy_test_processes()

    @classmethod
    def get_process_id(cls, name):
        return f"test_quotation_{name}"

    @classmethod
    def deploy_test_processes(cls):
        for name, deploy, app_pkg in [
            ("Echo", "DeployProcess_Echo.yml", "echo.cwl"),
            ("ReadFile", "deploy.yml", "package.cwl"),
            ("WorkflowChainStrings", "deploy.json", "package.cwl"),
        ]:
            path = os.path.join(APP_PKG_ROOT, name, deploy)
            with open(path, "r") as deploy_file:
                body = yaml.safe_load(deploy_file)
            path = os.path.join(APP_PKG_ROOT, name, app_pkg)
            with open(path, "r") as pkg_file:
                pkg = yaml.safe_load(pkg_file)
            body["executionUnit"][0] = {"unit": pkg}
            cls.deploy_process(body, process_id=name)

    def test_quote_bad_inputs(self):
        path = sd.process_quotes_service.path.format(process_id="Echo")
        data = {"inputs": [1, 2, 3]}
        resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
        assert resp.status_code == 400

    @mock.patch("weaver.quotation.estimation.estimate_process_quote", side_effect=mocked_estimate_process_quote)
    def test_quote_atomic_process(self, mocked_estimate):
        with contextlib.ExitStack() as stack_quote:
            for mock_quote in mocked_execute_celery(
                celery_task="weaver.quotation.estimation.process_quote_estimator"
            ):
                stack_quote.enter_context(mock_quote)

            data = {
                "inputs": {
                    "message": "test quote"
                },
                "outputs": {
                    "output": {
                        "transmissionMode": ExecuteTransmissionMode.VALUE
                    }
                }
            }
            path = sd.process_quotes_service.path.format(process_id="Echo")
            resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
            assert resp.status_code == 202  # 'Accepted' async task, but already finished by skipping celery
            assert mocked_estimate.called
            body = resp.json
            assert body["status"] == QuoteStatus.SUBMITTED

            path = sd.process_quote_service.path.format(process_id="Echo", quote_id=body["id"])
            resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers, only_local=True)
            assert resp.status_code == 200
            body = resp.json
            assert body["status"] == QuoteStatus.COMPLETED
            assert isinstance(body["price"], float) and body["price"] > 0
            assert isinstance(body["currency"], str) and body["currency"] == "CAD"
            assert isinstance(body["estimatedSeconds"], int) and body["estimatedSeconds"] > 0

    # FIXME: pass around pseudo-inputs to intermediate steps (?)
    #        see 'weaver.quotation.estimation.estimate_workflow_quote'
    @pytest.mark.xfail(reason="missing step inputs fails sub-process quotations")
    @mock.patch("weaver.quotation.estimation.estimate_process_quote", side_effect=mocked_estimate_process_quote)
    def test_quote_workflow_process(self, mocked_estimate):
        with contextlib.ExitStack() as stack_quote:
            for mock_quote in mocked_execute_celery(
                celery_task="weaver.quotation.estimation.process_quote_estimator"
            ):
                stack_quote.enter_context(mock_quote)

            with open(os.path.join(APP_PKG_ROOT, "WorkflowChainStrings", "execute.json"), "r") as exec_file:
                data = yaml.safe_load(exec_file)
            path = sd.process_quotes_service.path.format(process_id="WorkflowChainStrings")
            resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
            assert resp.status_code == 202  # 'Accepted' async task, but already finished by skipping celery
            assert mocked_estimate.called
            body = resp.json
            assert body["status"] == QuoteStatus.SUBMITTED

            path = sd.process_quote_service.path.format(process_id="Echo", quote_id=body["id"])
            resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers, only_local=True)
            assert resp.status_code == 200
            body = resp.json
            assert body["status"] == QuoteStatus.COMPLETED
            assert isinstance(body["price"], float) and body["price"] > 0
            assert isinstance(body["currency"], str) and body["currency"] == "CAD"
            assert isinstance(body["estimatedSeconds"], int) and body["estimatedSeconds"] > 0
