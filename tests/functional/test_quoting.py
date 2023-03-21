import contextlib
import os
import random
from typing import TYPE_CHECKING

import mock
import pytest
import yaml

from tests.functional import APP_PKG_ROOT
from tests.functional.utils import ResourcesUtil, WpsConfigBase
from tests.utils import mocked_execute_celery, mocked_sub_requests
from weaver.datatype import DockerAuthentication
from weaver.execute import ExecuteTransmissionMode
from weaver.processes.utils import pull_docker
from weaver.quotation.estimation import validate_quote_estimator_config
from weaver.quotation.status import QuoteStatus
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Dict, Optional

    from weaver.datatype import Process, Quote
    from weaver.typedefs import AnySettingsContainer, QuoteStepOutputParameters, SettingsType

    MockStepOutputs = Dict[
        str,        # process ID
        Dict[
            str,    # process input ID
            QuoteStepOutputParameters
        ]
    ]


def mocked_estimate_process_quote(quote, process, settings, mock_step_outputs=None):  # noqa
    # type: (Quote, Process, Optional[AnySettingsContainer], Optional[MockStepOutputs]) -> Quote
    """
    Mock :term:`Quote` estimation in the even that the real operation is updated.
    """
    # time min/max: [300, 3600]
    # cost min/max: [0.75, 450]
    quote.seconds = int(random.uniform(5, 60) * 59 + random.uniform(0, 60))  # nosec: B311
    quote.amount = float(random.uniform(0.0025, 0.125) * quote.seconds)      # nosec: B311
    quote.currency = "USD"
    quote.process = process.id
    if mock_step_outputs and process.id in mock_step_outputs:
        quote.outputs = mock_step_outputs[process.id]
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
            with open(path, mode="r", encoding="utf-8") as deploy_file:
                body = yaml.safe_load(deploy_file)
            path = os.path.join(APP_PKG_ROOT, name, app_pkg)
            with open(path, mode="r", encoding="utf-8") as pkg_file:
                pkg = yaml.safe_load(pkg_file)
            body["executionUnit"][0] = {"unit": pkg}
            cls.deploy_process(body, process_id=name)

    @mock.patch("weaver.quotation.estimation.get_quote_estimator_config", return_value={"ignore": {}})
    @mock.patch("weaver.quotation.estimation.validate_quote_estimator_config", return_value={"ignore": {}})
    def test_quotes_listing(self, *_):
        path = sd.process_quotes_service.path.format(process_id="Echo")
        data = {"inputs": {"message": "test quote"}}
        resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
        assert resp.status_code in [200, 201, 202]

        quote = resp.json["quoteID"]
        path = sd.quote_service.path.format(quote_id=quote)
        resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers, only_local=True)
        assert resp.status_code == 200

        path = sd.quotes_service.path
        resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers, only_local=True)
        assert resp.status_code == 200
        assert quote in resp.json["quotations"]

    @mock.patch("weaver.quotation.estimation.get_quote_estimator_config", return_value={"ignore": {}})
    @mock.patch("weaver.quotation.estimation.validate_quote_estimator_config", return_value={"ignore": {}})
    def test_quote_bad_inputs(self, *_):
        path = sd.process_quotes_service.path.format(process_id="Echo")
        data = {"inputs": [1, 2, 3]}
        resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
        assert resp.status_code == 400

    def test_quote_no_estimator(self):
        path = sd.process_quotes_service.path.format(process_id="Echo")
        data = {"inputs": {"message": "test quote"}}
        resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
        assert resp.status_code == 422
        assert resp.json["title"] == "UnsupportedOperation"
        assert "estimator" in resp.json["detail"]

    @mock.patch("weaver.quotation.estimation.get_quote_estimator_config", return_value={"ignore": {}})
    @mock.patch("weaver.quotation.estimation.validate_quote_estimator_config", return_value={"ignore": {}})
    def test_quote_payment_required(self, *_):
        with contextlib.ExitStack() as stack_quote:
            for mock_quote in mocked_execute_celery(
                celery_task="weaver.quotation.estimation.execute_quote_estimator"
            ):
                stack_quote.enter_context(mock_quote)
            stack_quote.enter_context(mock.patch(
                "weaver.quotation.estimation.estimate_process_quote",
                side_effect=mocked_estimate_process_quote,
            ))
            path = sd.process_quotes_service.path.format(process_id="Echo")
            data = {"inputs": {"message": "test quote"}}
            resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201, 202]

        quote = resp.json["quoteID"]
        path = sd.quote_service.path.format(quote_id=quote)
        resp = mocked_sub_requests(self.app, "GET", path, json=data, headers=self.json_headers, only_local=True)
        assert resp.status_code == 200
        assert resp.json["status"] == QuoteStatus.COMPLETED

        resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
        assert resp.status_code == 402
        assert resp.json["title"] == "Payment Required"

    @mock.patch("weaver.quotation.estimation.get_quote_estimator_config", return_value={"ignore": {}})
    @mock.patch("weaver.quotation.estimation.validate_quote_estimator_config", return_value={"ignore": {}})
    def test_quote_atomic_process(self, *_):
        with contextlib.ExitStack() as stack_quote:
            for mock_quote in mocked_execute_celery(
                celery_task="weaver.quotation.estimation.execute_quote_estimator"
            ):
                stack_quote.enter_context(mock_quote)
            mocked_estimate = stack_quote.enter_context(mock.patch(
                "weaver.quotation.estimation.estimate_process_quote",
                side_effect=mocked_estimate_process_quote,
            ))

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

            path = sd.process_quote_service.path.format(process_id="Echo", quote_id=body["quoteID"])
            resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers, only_local=True)
            assert resp.status_code == 200
            body = resp.json
            assert body["status"] == QuoteStatus.COMPLETED
            assert isinstance(body["price"]["amount"], float) and 0.75 <= body["price"]["amount"] <= 450
            assert isinstance(body["price"]["currency"], str) and body["price"]["currency"] == "USD"
            assert isinstance(body["estimatedSeconds"], int) and 300 <= body["estimatedSeconds"] <= 3600

    # FIXME: pass around pseudo-inputs to intermediate steps (?)
    #        see 'weaver.quotation.estimation.estimate_workflow_quote'
    # FIXME: early-failing quote for now, no estimator provided (consider whole Workflow as unit black-box)
    @pytest.mark.xfail(reason="missing step inputs fails sub-process quotations")
    @mock.patch("weaver.quotation.estimation.get_quote_estimator_config", return_value={"ignore": {}})
    @mock.patch("weaver.quotation.estimation.validate_quote_estimator_config", return_value={"ignore": {}})
    def test_quote_workflow_process(self, *_):
        with contextlib.ExitStack() as stack_quote:
            for mock_quote in mocked_execute_celery(
                celery_task="weaver.quotation.estimation.execute_quote_estimator"
            ):
                stack_quote.enter_context(mock_quote)
            mocked_estimate = stack_quote.enter_context(mock.patch(
                "weaver.quotation.estimation.estimate_process_quote",
                side_effect=lambda *_, **__: mocked_estimate_process_quote(*_, **__, mock_step_outputs={
                    "Echo": {  # first process in workflow chain
                        "file": {"size": 123456}  # expected inputs of ReadFile chained to Echo outputs
                    }
                })
            ))

            path = os.path.join(APP_PKG_ROOT, "WorkflowChainStrings", "execute.json")
            with open(path, mode="r", encoding="utf-8") as exec_file:
                data = yaml.safe_load(exec_file)
            path = sd.process_quotes_service.path.format(process_id="WorkflowChainStrings")
            resp = mocked_sub_requests(self.app, "POST", path, json=data, headers=self.json_headers, only_local=True)
            assert resp.status_code == 202  # 'Accepted' async task, but already finished by skipping celery
            assert mocked_estimate.called
            body = resp.json
            assert body["status"] == QuoteStatus.SUBMITTED

            path = sd.process_quote_service.path.format(process_id="Echo", quote_id=body["quoteID"])
            resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers, only_local=True)
            assert resp.status_code == 200
            body = resp.json
            assert body["status"] == QuoteStatus.COMPLETED
            assert isinstance(body["price"]["amount"], float) and 0.75 <= body["price"]["amount"] <= 450
            assert isinstance(body["price"]["currency"], str) and body["price"]["currency"] == "USD"
            assert isinstance(body["estimatedSeconds"], int) and 300 <= body["estimatedSeconds"] <= 3600


@pytest.mark.functional
@pytest.mark.quotation
class WpsQuotationRealEstimatorTest(ResourcesUtil, WpsConfigBase):
    @classmethod
    def setup_docker(cls):
        # type: () -> SettingsType
        image = os.getenv("WEAVER_TEST_QUOTATION_DOCKER_IMAGE")
        usr = os.getenv("WEAVER_TEST_QUOTATION_DOCKER_USERNAME") or None
        pwd = os.getenv("WEAVER_TEST_QUOTATION_DOCKER_PASSWORD") or None
        if not image:
            pytest.xfail("Cannot run test without quotation estimator docker image.")
        auth = DockerAuthentication(image, auth_username=usr, auth_password=pwd)
        if not pull_docker(auth):
            pytest.xfail("Cannot run test without quotation estimator docker image.")
        settings = {
            "weaver.quotation_docker_image": image,
            "weaver.quotation_docker_username": usr,
            "weaver.quotation_docker_password": pwd,
        }
        return settings

    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        cls.settings.update(cls.setup_docker())
        super(WpsQuotationRealEstimatorTest, cls).setUpClass()
        cls.deploy_test_processes()

    @classmethod
    def deploy_test_processes(cls):
        for name in ["Echo", "ReadFile"]:
            deploy = cls.retrieve_payload(name, "deploy", local=True)
            package = cls.retrieve_payload(name, "package", local=True)
            estimator = cls.retrieve_payload(name, "estimator", local=True)
            deploy["executionUnit"][0] = {"unit": package}
            cls.deploy_process(deploy, process_id=name)
            path = sd.process_estimator_service.path.format(process_id=name)
            resp = mocked_sub_requests(cls.app, "PUT", path, json=estimator, headers=cls.json_headers, only_local=True)
            assert resp.status_code == 200

    def test_quotation_literal_input(self):
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery("weaver.quotation.estimation.execute_quote_estimator"):
                stack_exec.enter_context(mock_exec_proc)
            body = {"inputs": {"message": "123456789"}}
            path = sd.process_quotes_service.path.format(process_id="Echo")
            resp = mocked_sub_requests(self.app, "POST", path, json=body, headers=self.json_headers, only_local=True)
            assert resp.status_code == 201

        quote = resp.json["QuoteID"]
        path = sd.quote_service.path.format(process_id="Echo", quote_id=quote)
        resp = mocked_sub_requests(self.app, "GET", path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["status"] == QuoteStatus.COMPLETED
        assert resp.json["total"] == 1

    def test_quotation_complex_input(self):
        raise


def test_validate_quote_estimator_config():
    estimator = {
        "config": {
            "flat_rate": 1.0,
            "gpu_rate": 123.45,
            "gpu_estimator": 0.05,
        },
        "inputs": {
            "x": {"weight": 3.1416},
            "y": {"random": 12.345},
            "z": {},
        }
    }
    result = validate_quote_estimator_config(estimator)
    assert result["config"] == estimator["config"]
    assert result["inputs"] == {
        "x": {"weight": 3.1416},
        "y": {"weight": 1.0},
    }
