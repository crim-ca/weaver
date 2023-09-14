#!/usr/bin/env python
"""
Run operations specifically within the built Docker container to ensure JavaScript runtime dependencies are available.
"""

import pytest
from cwl_utils import expression
from cwltool.process import get_schema
from cwltool.validate_js import validate_js_expressions

from weaver.processes.constants import CWL_REQUIREMENT_INLINE_JAVASCRIPT


def test_cwl_nodejs(caplog: pytest.LogCaptureFixture) -> None:
    """
    Run a CWL operation that requires Node.js to be evaluated.

    If JavaScript cannot be parsed and executed in the Docker container, then some requirements are missing.
    """
    tool = {
        "cwlVersion": "v1.0",
        "class": "CommandLineTool",
        "baseCommand": "echo",
        "requirements": [
            {
                "class": CWL_REQUIREMENT_INLINE_JAVASCRIPT,
            }
        ],
        "inputs": [
            {
                "id": "test",
                "inputBinding": {
                    "valueFrom": "${ let x = self + 1; return x; }"
                }
            }
        ],
        "outputs": {"output": "stdout"}
    }
    schema = get_schema(tool["cwlVersion"])[1]
    clt_schema = schema.names["org.w3id.cwl.cwl.CommandLineTool"]
    validate_js_expressions(tool, clt_schema)  # type: ignore

    out = expression.do_eval(
        tool["inputs"][0]["inputBinding"]["valueFrom"],
        {tool["inputs"][0]["id"]: tool["inputs"][0]},
        tool["requirements"],
        None,
        None,
        {},
        context=1,  # value passed as input
    )

    assert "JSHINT" in caplog.text
    assert out == 2  # JS 'self + 1'
