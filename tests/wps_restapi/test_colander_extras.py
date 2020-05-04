#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for :mod:`weaver.wps_restapi.colander_extras` operations applied
on :mod:`weaver.wps_restapi.swagger_definitions` objects.
"""
from weaver.wps_restapi import swagger_definitions as sd


def test_cwl_deploy_io_deserialize_mapping():
    """
    Evaluates OneOf deserialization for inputs/outputs CWL definition specified as key-mapping of objects.
    Should work simultaneously with the listing variation using the same deserializer.

    .. seealso::
        - :func:`test_cwl_deploy_io_deserialize_listing`
    """
    data = {
        "inputs": {
            "input-1": {"type": "float"},
            "input-2": {"type": "File"},
            "input-3": {"type": {"type": "array", "items": "string"}}
        }
    }

    result = sd.CWLInputsDefinition().deserialize(data)
    assert isinstance(result, dict)
    assert all(input_key in result for input_key in ["input-1", "input-2", "input-3"])
    assert result["input-1"]["type"] == "float"
    assert result["input-2"]["type"] == "File"
    assert isinstance(result["input-2"]["type"], dict)
    assert result["input-3"]["type"]["type"] == "array"
    assert result["input-3"]["type"]["items"] == "string"


def test_cwl_deploy_io_deserialize_listing():
    """
    Evaluates OneOf deserialization for inputs/outputs CWL definition specified as list of objects.
    Should work simultaneously with the mapping variation using the same deserializer.

    .. seealso::
        - :func:`test_cwl_deploy_io_deserialize_mapping`
    """
    data = [
        {"id": "input-1", "type": "float"},
        {"id": "input-2", "type": "File"},
        {"id": "input-3", "type": {"type": "array", "items": "string"}}
    ]

    result = sd.CWLInputsDefinition().deserialize(data)
    assert isinstance(result, list)
    assert all(result[i]["id"] == input_key for i, input_key in enumerate(["input-1", "input-2", "input-3"]))
    assert result[0]["type"] == "float"
    assert result[1]["type"] == "File"
    assert isinstance(result[2]["type"], dict)
    assert result[2]["type"]["type"] == "array"
    assert result[2]["type"]["items"] == "string"


def test_any_of_under_variable():
    key = "this-variable-key-does-not-matter"
    result = sd.CWLInputMap().deserialize({key: {"type": "float"}})
    assert isinstance(result, dict)
    assert key in result
    assert result[key] == {"type": "float"}
