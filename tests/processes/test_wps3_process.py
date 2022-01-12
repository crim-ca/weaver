import json

import mock
import pytest
from pywps.app import WPSRequest
from requests.models import Request, Response

from weaver.exceptions import PackageExecutionError
from weaver.formats import CONTENT_TYPE_APP_NETCDF
from weaver.processes.wps3_process import Wps3Process
from weaver.visibility import VISIBILITY_PUBLIC


def test_wps3_process_step_io_data_or_href():
    """
    Validates that 'data' literal values and 'href' file references are both handled as input for workflow steps
    corresponding to a WPS-3 process.
    """
    test_process = "test-wps3-process-step-io-data-or-href"
    test_reached_parse_inputs = False  # toggle at operation just before what is being tested here
    test_cwl_inputs = {
        "single-data-value": 1,
        "multi-data-values": [2, 3],
        "single-href-file": {"location": "https://random-place"},
        "multi-href-files": [{"location": "https://random-place"}, {"location": "https://another-place"}]
    }
    expected_wps_inputs = [
        {"id": "single-data-value", "data": 1},
        {"id": "multi-data-values", "data": 2},
        {"id": "multi-data-values", "data": 3},
        {"id": "single-href-file", "href": "https://random-place"},
        {"id": "multi-href-files", "href": "https://random-place"},
        {"id": "multi-href-files", "href": "https://another-place"},
    ]

    class TestDoneEarlyExit(Exception):
        """
        Dummy exception to raise to skip further processing steps after the portion to evaluate was reached.
        """

    def mock_wps_request(method, url, *_, **kwargs):
        nonlocal test_reached_parse_inputs

        method = method.upper()
        if url.endswith("/visibility"):
            resp = Response()
            resp.status_code = 200
            resp._content = json.dumps({"value": VISIBILITY_PUBLIC}, ensure_ascii=False).encode()
            resp.headers = {"Content-Type": CONTENT_TYPE_APP_NETCDF}
            resp.encoding = None
            if method == "PUT":
                test_reached_parse_inputs = True  # last operation before parsing I/O is setting visibility
            return resp
        if method == "POST" and url.endswith(test_process + "/jobs"):
            # actual evaluation of intended handling of CWL inputs conversion to WPS-3 execute request
            assert kwargs.get("json", {}).get("inputs") == expected_wps_inputs
            raise TestDoneEarlyExit("Expected exception raised to skip executed job status monitoring")
        raise AssertionError("unhandled mocked 'make_request' call")

    def mock_update_status(*_, **__):
        return None

    mock_data_sources = {"localhost": {"netloc": "localhost", "ades": "https://localhost:4001", "default": True}}
    with mock.patch("weaver.processes.wps_process_base.WpsProcessInterface.make_request", side_effect=mock_wps_request):
        with mock.patch("weaver.processes.sources.fetch_data_sources", return_value=mock_data_sources):
            wps_params = {"service": "wps", "request": "execute", "identifier": test_process, "version": "1.0.0"}
            req = Request(method="GET", params=wps_params)
            setattr(req, "args", wps_params)
            setattr(req, "path", "/wps")
            req = WPSRequest(req)
            wps = Wps3Process({}, {}, test_process, req, mock_update_status)  # noqa
            try:
                wps.execute(test_cwl_inputs, "", {})
            except TestDoneEarlyExit:
                pass  # successful test / expected handling
            except PackageExecutionError as exc:
                if isinstance(exc.__cause__, TestDoneEarlyExit):
                    return  # successful test / expected handling
                msg = "Other error was raised [{}], inputs where not correctly handled somewhere".format(exc)
                pytest.fail(msg)
            except Exception as exc:  # noqa
                if not test_reached_parse_inputs:
                    msg = "Prior error was raised [{}], could not evaluate intended handling of inputs".format(exc)
                    pytest.fail(msg)
                msg = "Other error was raised [{}], inputs where not correctly handled somewhere".format(exc)
                pytest.fail(msg)
