"""
Unit test for :mod:`weaver.cli` utilities.
"""
import inspect

import pytest

from weaver.cli import OperationResult


@pytest.mark.cli
def test_operation_result_repr():
    result = OperationResult(True, code=200, message="This is a test.", body={"field": "data", "list": [1, 2, 3]})
    assert repr(result) == inspect.cleandoc("""
        OperationResult(success=True, code=200, message="This is a test.")
        {
          "field": "data",
          "list": [
            1,
            2,
            3
          ]
        }
    """)
