#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for :mod:`weaver.wps_restapi.colander_extras` operations applied on :mod:`weaver.wps_restapi.swagger_definitions`
objects.
"""
import inspect
from typing import TYPE_CHECKING

import colander
import pytest

from weaver.wps_restapi import colander_extras as ce, swagger_definitions as sd

if TYPE_CHECKING:
    from typing import List, Tuple, Type, Union

    from weaver.typedefs import JSON

    TestSchema = Union[colander.SchemaNode, Type[colander.SchemaNode]]
    TestValue = JSON
    TestExpect = Union[JSON, colander.Invalid]


def evaluate_test_cases(test_cases):
    # type: (List[Tuple[TestSchema, TestValue, TestExpect]]) -> None
    """
    Evaluate a list of tuple of (SchemaType, Test-Value, Expected-Result).

    If ``Expected-Result`` is :class:`colander.Invalid``, the ``SchemaType`` deserialization should raise when
    evaluating ``Test-Value``. Otherwise, the result from deserialization should equal exactly ``Expected-Result``.
    """

    for i, (test_schema_ref, test_value, test_expect) in enumerate(test_cases):
        if inspect.isclass(test_schema_ref):
            test_schema = test_schema_ref()
            test_schema_name = test_schema_ref.__name__
        else:
            test_schema = test_schema_ref
            test_schema_name = type(test_schema_ref).__name__
        try:
            result = test_schema.deserialize(test_value)
            if test_expect is colander.Invalid:
                pytest.fail(f"Test [{i}]: Expected invalid format from [{test_schema_name}] "
                            f"with: {test_value}, but received: {result}")
            assert result == test_expect, f"Test [{i}]: Bad result from [{test_schema_name}] with: {test_value}"
        except colander.Invalid:
            if test_expect is colander.Invalid:
                pass
            else:
                pytest.fail(f"Test [{i}]: Expected valid format from [{test_schema_name}] "
                            f"with: {test_value}, but invalid instead of: {test_expect}")


def test_oneof_io_formats_deserialize_as_mapping():
    """
    Evaluates ``oneOf`` deserialization for inputs/outputs CWL definition specified as key-mapping of objects.

    Should work simultaneously with the listing variation using the same deserializer.

    .. seealso::
        - :func:`test_cwl_deploy_io_deserialize_listing`
    """
    data = {
        "input-1": {"type": "float"},
        "input-2": {"type": "File"},
        "input-3": {"type": {"type": "array", "items": "string"}}
    }

    result = sd.CWLInputsDefinition(name=__name__).deserialize(data)
    assert isinstance(result, dict)
    assert all(input_key in result for input_key in ["input-1", "input-2", "input-3"])
    assert result["input-1"]["type"] == "float"
    assert result["input-2"]["type"] == "File"
    assert isinstance(result["input-3"]["type"], dict)
    assert result["input-3"]["type"]["type"] == "array"
    assert result["input-3"]["type"]["items"] == "string"


def test_oneof_io_formats_deserialize_as_listing():
    """
    Evaluates ``oneOf`` deserialization for inputs/outputs CWL definition specified as list of objects.

    Should work simultaneously with the mapping variation using the same deserializer.

    .. seealso::
        - :func:`test_cwl_deploy_io_deserialize_mapping`
    """
    data = [
        {"id": "input-1", "type": "float"},
        {"id": "input-2", "type": "File"},
        {"id": "input-3", "type": {"type": "array", "items": "string"}}
    ]

    result = sd.CWLInputsDefinition(name=__name__).deserialize(data)
    assert isinstance(result, list)
    assert all(result[i]["id"] == input_key for i, input_key in enumerate(["input-1", "input-2", "input-3"]))
    assert result[0]["type"] == "float"
    assert result[1]["type"] == "File"
    assert isinstance(result[2]["type"], dict)
    assert result[2]["type"]["type"] == "array"
    assert result[2]["type"]["items"] == "string"


def test_any_of_under_variable():
    key = "this-variable-key-does-not-matter"
    result = sd.CWLInputMap(name=__name__).deserialize({key: {"type": "float"}})
    assert isinstance(result, dict)
    assert key in result
    assert result[key] == {"type": "float"}


def test_oneof_variable_dict_or_list():
    """
    Test the common representation of item listing (with ID) and corresponding ID to content mapping representations.
    """

    class DataMap(ce.ExtendedMappingSchema):
        field = ce.ExtendedSchemaNode(ce.ExtendedInteger())

    class DataItem(DataMap):
        id = ce.ExtendedSchemaNode(ce.ExtendedString())

    class DataSeq(ce.ExtendedSequenceSchema):
        item = DataItem()

    class DataVarMap(ce.ExtendedMappingSchema):
        var_id = DataMap(variable="<var_id>")

    class DataOneOf(ce.OneOfKeywordSchema):
        _one_of = [DataVarMap, DataSeq]

    class DataMapDrop(ce.ExtendedMappingSchema):
        field = ce.ExtendedSchemaNode(ce.ExtendedInteger(), missing=colander.drop)

    class DataItemDrop(DataMapDrop):
        id = ce.ExtendedSchemaNode(ce.ExtendedString())

    class DataSeqDrop(ce.ExtendedSequenceSchema):
        item = DataItemDrop()

    class DataVarMapDrop(ce.ExtendedMappingSchema):
        var_id = DataMapDrop(variable="<var_id>")

    class DataOneOfDrop(ce.OneOfKeywordSchema):
        _one_of = [DataVarMapDrop, DataSeqDrop]

    valid_map = {"id-1": {"field": 1}, "id-2": {"field": 2}}
    valid_list = [{"id": "id-1", "field": 1}, {"id": "id-2", "field": 2}]

    evaluate_test_cases([
        (DataOneOf, valid_map, valid_map),
        (DataOneOf, valid_list, valid_list),
        (DataOneOf, {}, colander.Invalid),  # missing 'field', so empty is not valid because we check sub-schemas
        (DataOneOf, [], []),  # missing 'field'+'id' so empty is not valid
        (DataOneOfDrop, {}, colander.Invalid),  # valid now because 'field' can be omitted
        (DataOneOfDrop, [], []),  # valid because empty list is allowed
        (DataOneOf(default={}), "bad-format", colander.Invalid),  # not drop, default only if not provided
        (DataOneOf(default={}), None, colander.Invalid),  # value 'None' (JSON 'null') is still "providing" the field
        (DataOneOf(missing=colander.drop), "bad-format", colander.drop),  # would be dropped by higher level schema
        (DataOneOf(default={}, missing=colander.drop), colander.null, {}),  # result if value not "provided" use default
        (DataOneOfDrop(default={}), colander.null, {}),  # value not provided uses default
        (DataOneOf, {"id-1": {"field": "ok"}, "id-2": {"field": "123"}}, colander.Invalid),
        (DataOneOf, [{"id": 1, "field": "ok"}, {"id": "id-2", "field": 123}], colander.Invalid),
        (DataOneOf, {"id-1": [1, 2, 3]}, colander.Invalid),
        (DataOneOf, [{"id": "id-1"}], colander.Invalid),
    ])


def test_oneof_nested_dict_list():
    class Seq(ce.ExtendedSequenceSchema):
        item = ce.ExtendedSchemaNode(colander.String())

    class Obj(ce.ExtendedMappingSchema):
        key = ce.ExtendedSchemaNode(colander.String())

    class ObjSeq(ce.ExtendedMappingSchema):
        items = Seq()

    class ObjOneOf(ce.OneOfKeywordSchema):
        _one_of = (Obj, ObjSeq)

    for test_schema, test_value in [
        (ObjOneOf, {"key": "value"}),
        (ObjOneOf, {"items": ["value"]})
    ]:
        try:
            assert test_schema().deserialize(test_value) == test_value
        except colander.Invalid:
            node_name = ce._get_node_name(test_schema)
            pytest.fail(f"Should not fail deserialize of '{node_name!s}' with {test_value!s}")
    for test_schema, test_value in [
        (ObjOneOf, {"key": None}),
        (ObjOneOf, {"items": None}),
        (ObjOneOf, {"items": ["value"], "key": "value"}),  # cannot have both (oneOf)
    ]:
        node_name = ce._get_node_name(test_schema)
        try:
            result = ObjOneOf().deserialize(test_value)
        except colander.Invalid:
            pass
        except Exception:
            raise AssertionError("Incorrect exception raised from deserialize "
                                 f"of '{node_name!s}' with {test_value!s}")
        else:
            raise AssertionError("Should have raised invalid schema from deserialize "
                                 f"of '{node_name!s}' with {test_value!s}, but got {result!s}")


def test_oneof_dropable():
    """
    Using optional (dropable) ``oneOf`` with required sub-schema, failing deserialization should drop it entirely.

    Keyword ``oneOf`` must still be respected regardless of optional status, as in, it must only allow a single
    valid schema amongst allowed cases if value matches one of the definitions. Adding the drop option only *also*
    allows it to match none of them.
    """

    class AnyMap(ce.PermissiveMappingSchema):
        pass  # any field is ok

    class OneOfStrMap(ce.OneOfKeywordSchema):
        _one_of = [
            ce.ExtendedSchemaNode(colander.String()),  # note: 'allow_empty=False' by default
            AnyMap()
        ]

    schema = OneOfStrMap(missing=colander.drop)
    evaluate_test_cases([
        (schema, [], colander.drop),  # not a string nor mapping, but don't raise since drop allowed
        (schema, "ok", "ok"),
        (schema, {}, {}),   # since mapping is permissive, empty is valid
        (schema, {"any": 123}, {"any": 123}),  # unknown field is also valid
        # since OneOf[str,map], it is not possible to combine them
    ])

    class Map1(ce.ExtendedMappingSchema):
        field1 = ce.ExtendedSchemaNode(colander.String())

    class Map2(ce.ExtendedMappingSchema):
        field2 = ce.ExtendedSchemaNode(colander.String())

    class OneOfTwoMap(ce.OneOfKeywordSchema):
        _one_of = [
            Map1(),
            Map2()
        ]

    schema = OneOfTwoMap(missing=colander.drop)
    evaluate_test_cases([
        (schema, [], colander.drop),  # not mapping, but don't raise since drop allowed
        (schema, "", colander.drop),  # not mapping, but don't raise since drop allowed
        (schema, {}, colander.drop),  # mapping, but not respecting sub-fields, don't raise since drop allowed
        (schema, {"field1": 1}, colander.drop),  # mapping with good field name, but wrong type, drop since allowed
        (schema, {"field1": "1", "field2": "2"}, colander.drop),  # cannot have both, don't raise since drop allowed
        (schema, {"field1": "1"}, {"field1": "1"}),
        (schema, {"field2": "2"}, {"field2": "2"}),
    ])

    # validate that the same definition above behaves normally (raise Invalid) when not dropable
    schema = OneOfTwoMap()
    evaluate_test_cases([
        (schema, [], colander.Invalid),  # not mapping
        (schema, "", colander.Invalid),  # not mapping
        (schema, {}, colander.Invalid),  # mapping, but not respecting sub-fields
        (schema, {"field1": 1}, colander.Invalid),  # mapping with good field name, but wrong type
        (schema, {"field1": "1", "field2": "2"}, colander.Invalid),  # cannot have both mappings at the same time
        (schema, {"field1": "1"}, {"field1": "1"}),
        (schema, {"field2": "2"}, {"field2": "2"}),
    ])


def test_oneof_optional_default_with_nested_required():
    """
    Using ``oneOf`` keyword that is optional with default, its required subnodes must resolve to the provided default.

    The resolution of default in this case is particular because the nested schemas of ``oneOf`` are not necessarily
    mappings themselves (as is ``oneOf`` schema). Default resolution must take this into account when the corresponding
    schema-fields are invalid or omitted. Not only that, nested schemas can each be composed of distinct schema types.
    """
    class MappingSchema(ce.ExtendedMappingSchema):
        value = ce.ExtendedSchemaNode(ce.ExtendedInteger())  # strict int, no auto convert to str

    class OneOfDifferentNested(ce.OneOfKeywordSchema):
        _one_of = [
            ce.ExtendedSchemaNode(ce.ExtendedString()),  # strict string, no auto convert from int
            MappingSchema()
        ]

    class OneOfRequiredDefaultStr(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default="1")  # match first schema of OneOf

    class OneOfRequiredDefaultMap(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default={"value": 1})  # match second schema of OneOf

    class OneOfMissingDropDefaultStr(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default="1", missing=colander.drop)

    class OneOfMissingDropDefaultMap(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default={"value": 1}, missing=colander.drop)

    class OneOfMissingNullDefaultStr(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default="1", missing=colander.null)

    class OneOfMissingNullDefaultMap(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default={"value": 1}, missing=colander.null)

    class OneOfMissingNullDefaultNull(ce.ExtendedMappingSchema):
        field = OneOfDifferentNested(default=colander.null, missing=colander.null)

    evaluate_test_cases([
        (OneOfRequiredDefaultStr, {}, {"field": "1"}),
        (OneOfRequiredDefaultStr, None, colander.Invalid),  # oneOf itself is required
        (OneOfRequiredDefaultStr, {"field": True}, colander.Invalid),  # raise because provided is wrong format
        (OneOfRequiredDefaultStr, {"field": {}}, colander.Invalid),
        (OneOfRequiredDefaultStr, {"field": {"value": "1"}}, colander.Invalid),
        (OneOfRequiredDefaultStr, {"field": {"value": 1}}, {"field": {"value": 1}}),
        (OneOfMissingDropDefaultStr, {"field": True}, {}),
        (OneOfMissingDropDefaultStr, {"field": 1}, {}),
        (OneOfMissingNullDefaultStr, {}, {"field": "1"}),
        (OneOfMissingNullDefaultStr, {"field": True}, colander.Invalid),
        (OneOfMissingNullDefaultStr, {"field": {"value": "1"}}, colander.Invalid),
        (OneOfMissingNullDefaultStr, {"field": {"value": 1}}, {"field": {"value": 1}}),
        (OneOfRequiredDefaultMap, {}, {"field": {"value": 1}}),  # default
        (OneOfRequiredDefaultMap, None, colander.Invalid),
        (OneOfRequiredDefaultMap, {"field": True}, colander.Invalid),
        (OneOfRequiredDefaultMap, {"field": {}}, colander.Invalid),
        (OneOfRequiredDefaultMap, {"field": {"value": "1"}}, colander.Invalid),
        (OneOfRequiredDefaultMap, {"field": {"value": 1}}, {"field": {"value": 1}}),
        (OneOfRequiredDefaultMap, {}, {"field": {"value": 1}}),  # default
        (OneOfMissingDropDefaultMap, {"field": True}, {}),
        (OneOfMissingDropDefaultMap, {"field": 1}, {}),
        (OneOfMissingNullDefaultMap, {}, {"field": {"value": 1}}),
        (OneOfMissingNullDefaultMap, {"field": True}, colander.Invalid),
        (OneOfMissingNullDefaultMap, {"field": {"value": "1"}}, colander.Invalid),
        (OneOfMissingNullDefaultMap, {"field": {"value": 1}}, {"field": {"value": 1}}),
        (OneOfMissingNullDefaultNull, {}, {}),
        (OneOfMissingNullDefaultNull, {"field": True}, colander.Invalid),
        (OneOfMissingNullDefaultNull, {"field": {"value": "1"}}, colander.Invalid),
        (OneOfMissingNullDefaultNull, {"field": "1"}, {"field": "1"}),
        (OneOfMissingNullDefaultNull, {"field": {"value": 1}}, {"field": {"value": 1}}),
    ])


def test_not_keyword_extra_fields_handling():
    """
    Using ``not`` keyword without any other schemas must return an empty mapping with additional fields dropped.

    When providing other schemas, only fields in those inherited definitions should remain.
    In should raise when matching the ``not`` conditions regardless.
    """

    class RequiredItem(ce.ExtendedMappingSchema):
        item = ce.ExtendedSchemaNode(colander.String())

    class MappingWithType(ce.ExtendedMappingSchema):
        type = ce.ExtendedSchemaNode(colander.String())

    class MappingWithoutType(ce.NotKeywordSchema, RequiredItem):
        _not = [MappingWithType()]

    class MappingOnlyNotType(ce.NotKeywordSchema):
        _not = [MappingWithType()]

    value = {"type": "invalid", "item": "valid"}
    node_name = ce._get_node_name(MappingWithoutType)
    try:
        result = MappingWithoutType().deserialize(value)
    except colander.Invalid:
        pass
    except Exception:
        raise AssertionError("Incorrect exception raised from deserialize "
                             f"of '{node_name!s}' with {value!s}")
    else:
        raise AssertionError("Should have raised invalid schema from deserialize "
                             f"of '{node_name!s}' with {value!s}, but got {result!s}")

    test_cases = [
        (MappingWithoutType, {"item": "valid", "value": "ignore"}, {"item": "valid"}),
        (MappingOnlyNotType, {"item": "valid", "value": "ignore"}, {})
    ]
    evaluate_test_cases(test_cases)


def test_preserve_mapping():
    class NormalMap(ce.ExtendedMappingSchema):
        known = ce.ExtendedSchemaNode(ce.ExtendedInteger())

    class PreserveMap(ce.PermissiveMappingSchema, NormalMap):  # inherit above 'known' field
        pass

    class Seq(ce.ExtendedSequenceSchema):
        item = ce.ExtendedSchemaNode(ce.ExtendedFloat())

    class ExtendMap(ce.PermissiveMappingSchema, NormalMap):  # inherit above 'known' field
        other = Seq()

    evaluate_test_cases([
        (PreserveMap, {}, colander.Invalid),  # missing 'known' field
        (PreserveMap, {"known": "str"}, colander.Invalid),  # invalid type for 'known' field
        (PreserveMap, {"known": 1}, {"known": 1}),  # ok by itself
        (PreserveMap, {"known": 1, "extra": 2}, {"known": 1, "extra": 2}),  # ok with extra unknown field to preserve
        (NormalMap, {"known": 1, "extra": 2}, {"known": 1}),  # unknown field is drop in normal schema
        (NormalMap, {"known": "A"}, colander.Invalid),
        (ExtendMap, {"known": 1}, colander.Invalid),  # missing 'other' list
        (ExtendMap, {"known": 1, "other": []}, {"known": 1, "other": []}),
        (ExtendMap, {"known": 1, "other": [1.2, 3.4]}, {"known": 1, "other": [1.2, 3.4]}),
        (ExtendMap, {"known": 1, "other": ["1.2"]}, colander.Invalid),
        (ExtendMap, {"known": 1, "other": [1.2], "extra": "ok"}, {"known": 1, "other": [1.2], "extra": "ok"}),
    ])


def test_strict_float():
    class FloatMap(ce.ExtendedMappingSchema):
        num = ce.ExtendedSchemaNode(ce.ExtendedFloat())

    evaluate_test_cases([
        (FloatMap, {"num": 1}, colander.Invalid),
        (FloatMap, {"num": "1"}, colander.Invalid),
        (FloatMap, {"num": "1.23"}, colander.Invalid),
        (FloatMap, {"num": None}, colander.Invalid),
        (FloatMap, {"num": True}, colander.Invalid),
        (FloatMap, {"num": False}, colander.Invalid),
        (FloatMap, {"num": "None"}, colander.Invalid),
        (FloatMap, {"num": "True"}, colander.Invalid),
        (FloatMap, {"num": "False"}, colander.Invalid),
        (FloatMap, {"num": "true"}, colander.Invalid),
        (FloatMap, {"num": "false"}, colander.Invalid),
        (FloatMap, {"num": 1.23}, {"num": 1.23}),
        (FloatMap, {"num": 1.}, {"num": 1.0}),
    ])


def test_strict_float_allowed_str():
    class FloatMap(ce.ExtendedMappingSchema):
        num = ce.ExtendedSchemaNode(ce.ExtendedFloat(allow_string=True))

    evaluate_test_cases([
        (FloatMap, {"num": 1}, colander.Invalid),
        (FloatMap, {"num": "1"}, colander.Invalid),
        (FloatMap, {"num": None}, colander.Invalid),
        (FloatMap, {"num": True}, colander.Invalid),
        (FloatMap, {"num": False}, colander.Invalid),
        (FloatMap, {"num": "None"}, colander.Invalid),
        (FloatMap, {"num": "True"}, colander.Invalid),
        (FloatMap, {"num": "False"}, colander.Invalid),
        (FloatMap, {"num": "true"}, colander.Invalid),
        (FloatMap, {"num": "false"}, colander.Invalid),
        (FloatMap, {"num": 1.23}, {"num": 1.23}),
        (FloatMap, {"num": "1.23"}, {"num": 1.23}),  # only convert from str is also allowed compared to 'strict' test
        (FloatMap, {"num": 1.}, {"num": 1.0}),
        (FloatMap, {"num": "1."}, {"num": 1.0}),  # only convert from str is also allowed compared to 'strict' test
    ])


def test_strict_int():
    class IntMap(ce.ExtendedMappingSchema):
        num = ce.ExtendedSchemaNode(ce.ExtendedInteger())

    evaluate_test_cases([
        (IntMap, {"num": 1.23}, colander.Invalid),
        (IntMap, {"num": "1"}, colander.Invalid),
        (IntMap, {"num": "1.23"}, colander.Invalid),
        (IntMap, {"num": None}, colander.Invalid),
        (IntMap, {"num": True}, colander.Invalid),
        (IntMap, {"num": False}, colander.Invalid),
        (IntMap, {"num": "None"}, colander.Invalid),
        (IntMap, {"num": "True"}, colander.Invalid),
        (IntMap, {"num": "False"}, colander.Invalid),
        (IntMap, {"num": "true"}, colander.Invalid),
        (IntMap, {"num": "false"}, colander.Invalid),
        (IntMap, {"num": 1}, {"num": 1}),
    ])


def test_strict_int_allowed_str():
    class IntMap(ce.ExtendedMappingSchema):
        num = ce.ExtendedSchemaNode(ce.ExtendedInteger(allow_string=True))

    evaluate_test_cases([
        (IntMap, {"num": 1.23}, colander.Invalid),
        (IntMap, {"num": "1.23"}, colander.Invalid),
        (IntMap, {"num": None}, colander.Invalid),
        (IntMap, {"num": True}, colander.Invalid),
        (IntMap, {"num": False}, colander.Invalid),
        (IntMap, {"num": "None"}, colander.Invalid),
        (IntMap, {"num": "True"}, colander.Invalid),
        (IntMap, {"num": "False"}, colander.Invalid),
        (IntMap, {"num": "true"}, colander.Invalid),
        (IntMap, {"num": "false"}, colander.Invalid),
        (IntMap, {"num": 1}, {"num": 1}),
        (IntMap, {"num": "1"}, {"num": 1}),  # only this is also allowed compared to 'strict' test
    ])


def test_strict_bool():
    class BoolMap(ce.ExtendedMappingSchema):
        num = ce.ExtendedSchemaNode(ce.ExtendedBoolean())

    evaluate_test_cases([
        (BoolMap, {"num": 1.23}, colander.Invalid),
        (BoolMap, {"num": "1.23"}, colander.Invalid),
        (BoolMap, {"num": "1"}, colander.Invalid),
        (BoolMap, {"num": "0"}, colander.Invalid),
        (BoolMap, {"num": 1}, colander.Invalid),
        (BoolMap, {"num": 0}, colander.Invalid),
        (BoolMap, {"num": "on"}, colander.Invalid),
        (BoolMap, {"num": "off"}, colander.Invalid),
        (BoolMap, {"num": "true"}, colander.Invalid),
        (BoolMap, {"num": "false"}, colander.Invalid),
        (BoolMap, {"num": "True"}, colander.Invalid),
        (BoolMap, {"num": "False"}, colander.Invalid),
        (BoolMap, {"num": "Yes"}, colander.Invalid),
        (BoolMap, {"num": "No"}, colander.Invalid),
        (BoolMap, {"num": None}, colander.Invalid),
        (BoolMap, {"num": True}, {"num": True}),
        (BoolMap, {"num": False}, {"num": False}),
    ])


def test_strict_literal_convert():
    """
    Test that literals are adequately interpreted and validated with respective representations..

    Given a schema that allows multiple similar types that could be implicitly or explicitly converted from one to
    another with proper format, validate that such conversion do not occur to ensure explicit schema definitions.
    """

    # Schemas below could fail appropriate resolution if implicit conversion occurs (because >1 in oneOf succeeds).
    # With correct validation and type handling, only one case is possible each time.
    class Literal(ce.OneOfKeywordSchema):
        _one_of = [
            ce.ExtendedSchemaNode(ce.ExtendedFloat()),
            ce.ExtendedSchemaNode(ce.ExtendedInteger()),
            ce.ExtendedSchemaNode(ce.ExtendedString()),
            ce.ExtendedSchemaNode(ce.ExtendedBoolean()),
        ]

    evaluate_test_cases([
        (Literal, 1, 1),
        (Literal, 0, 0),
        (Literal, "1", "1"),
        (Literal, "0", "0"),
        (Literal, True, True),
        (Literal, False, False),
        (Literal, "true", "true"),
        (Literal, "false", "false"),
        (Literal, "True", "True"),
        (Literal, "False", "False"),
        (Literal, 1.23, 1.23),
    ])


class FieldTestString(ce.ExtendedSchemaNode):
    schema_type = colander.String


class Mapping(ce.ExtendedMappingSchema):
    test = FieldTestString()
    schema_expected = {
        "type": "object",
        "title": "Mapping",
        "required": ["test"],
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
            }
        }
    }


class Default(ce.ExtendedMappingSchema):
    test = FieldTestString(default="test")
    schema_expected = {
        "type": "object",
        "title": "Default",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
            }
        }
    }


class Missing(ce.ExtendedMappingSchema):
    test = FieldTestString(missing=colander.drop)
    schema_expected = {
        "type": "object",
        "title": "Missing",
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
            }
        }
    }


class DefaultMissing(ce.ExtendedMappingSchema):
    test = FieldTestString(default="test", missing=colander.drop)
    schema_expected = {
        "type": "object",
        "title": "DefaultMissing",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
            }
        }
    }


class DefaultMissingValidator(ce.ExtendedMappingSchema):
    test = FieldTestString(default="test", missing=colander.drop, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultMissingValidator",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class Validator(ce.ExtendedMappingSchema):
    test = FieldTestString(validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "Validator",
        "required": ["test"],
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class DefaultDropValidator(ce.ExtendedMappingSchema):
    """
    Definition that will allow only the specific validator values, or drops the content silently.
    """
    test = FieldTestString(default=colander.drop, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultDropValidator",
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class DefaultDropRequired(ce.ExtendedMappingSchema):
    """
    Mapping to evaluate handling of deserialization when both ``missing`` and ``default`` arguments are specified.

    Definition that will allow only the specific validator values, or drops the full content silently.
    One top of that, ensures that the resulting OpenAPI schema defines it as required instead of optional
    when default is usually specified.

    This allows dropping invalid values that failed validation and not employ any default, while letting know
    in the OpenAPI specification that for a nested definition of required elements, they will be used only if
    correctly provided, or completely ignored as optional.
    """
    test = FieldTestString(default=colander.drop, missing=colander.required, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultDropRequired",
        "required": ["test"],
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class DefaultValidator(ce.ExtendedMappingSchema):
    """
    Functionality that we want most of the time to make an 'optional' but validated value.

    When value is explicitly provided, raise if invalid according to condition.
    Otherwise, use default if omitted.
    """
    test = FieldTestString(default="test", validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultValidator",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class MissingValidator(ce.ExtendedMappingSchema):
    test = FieldTestString(missing=colander.drop, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "MissingValidator",
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


def test_invalid_schema_mismatch_default_validator():
    try:
        class TestBad(ce.ExtendedSchemaNode):
            schema_type = colander.String
            default = "bad-value-not-in-one-of"
            validator = colander.OneOf(["test"])

        TestBad()
    except ce.SchemaNodeTypeError:
        pass
    else:
        pytest.fail("Erroneous schema must raise immediately if default doesn't conform to its own validator.")
    try:
        class DefaultValidatorBad(ce.ExtendedMappingSchema):
            test = FieldTestString(default="bad-value-not-in-one-of", validator=colander.OneOf(["test"]))

        DefaultValidatorBad()
    except ce.SchemaNodeTypeError:
        pass
    else:
        pytest.fail("Erroneous schema must raise immediately if default doesn't conform to its own validator.")


def test_schema_default_missing_validator_combinations():
    """
    Validate resulting deserialization of mappings according to parameter combinations and parsed data.

    .. seealso::
        :func:`test_schema_default_missing_validator_openapi`
    """
    test_schemas = [
        (Mapping, {}, colander.Invalid),                    # required but missing
        (Mapping, {"test": None}, colander.Invalid),        # wrong value schema-type
        (Mapping, {"test": "random"}, {"test": "random"}),  # uses the value as is if provided because no validator
        (Default, {}, {"test": "test"}),                    # default+required adds the value if omitted
        (Default, {"test": None}, {"test": "test"}),        # default+required sets the value if null
        (Default, {"test": "random"}, {"test": "random"}),  # default+required uses the value as is if provided
        (Missing, {}, {}),                                  # missing only drops the value if omitted
        (Missing, {"test": None}, {}),
        (Missing, {"test": "random"}, {"test": "random"}),
        (DefaultMissing, {}, {"test": "test"}),             # default+missing ignores drops and sets omitted value
        (DefaultMissing, {"test": None}, {}),
        (DefaultMissing, {"test": "random"}, {"test": "random"}),
        (Validator, {}, colander.Invalid),
        (Validator, {"test": None}, colander.Invalid),
        (Validator, {"test": "bad"}, colander.Invalid),
        (Validator, {"test": "test"}, {"test": "test"}),
        (DefaultValidator, {}, {"test": "test"}),
        (DefaultValidator, {"test": None}, {"test": "test"}),
        (DefaultValidator, {"test": "bad"}, colander.Invalid),
        (DefaultValidator, {"test": "test"}, {"test": "test"}),
        (DefaultMissingValidator, {}, {"test": "test"}),    # default+missing ignores drop and sets default if omitted
        (DefaultMissingValidator, {"test": None}, {}),
        # (DefaultMissingValidator, {"test": "bad"}, {}),
        (DefaultMissingValidator, {"test": "bad"}, colander.Invalid),
        (DefaultMissingValidator, {"test": "test"}, {"test": "test"}),
        (MissingValidator, {}, {}),
        (MissingValidator, {"test": None}, {}),
        # (MissingValidator, {"test": "bad"}, {}),
        (MissingValidator, {"test": "bad"}, colander.Invalid),
        (MissingValidator, {"test": "test"}, {"test": "test"}),
        (DefaultDropRequired, {}, {}),
        (DefaultDropRequired, {"test": None}, {}),
        (DefaultDropRequired, {"test": "bad"}, {}),
        (DefaultDropRequired, {"test": "test"}, {"test": "test"}),
        (DefaultDropValidator, {}, {}),
        (DefaultDropValidator, {"test": None}, {}),
        (DefaultDropValidator, {"test": "bad"}, {}),
        (DefaultDropValidator, {"test": "test"}, {"test": "test"}),
    ]
    evaluate_test_cases(test_schemas)


def test_schema_default_missing_validator_openapi():
    """
    Validate that resulting OpenAPI schema are as expected while still providing advanced deserialization features.

    Resulting schema are very similar can often cannot be distinguished for some variants, but the various combination
    of values for ``default``, ``missing`` and ``validator`` will provide very distinct behavior during parsing.

    .. seealso::
        :func:`test_schema_default_missing_validator_combinations`
    """
    converter = ce.ObjectTypeConverter(ce.OAS3TypeConversionDispatcher())
    test_schemas = [
        Mapping,
        Missing,
        Default,
        Validator,
        DefaultMissing,
        DefaultValidator,
        MissingValidator,
        DefaultMissingValidator,
        DefaultDropValidator,
        DefaultDropRequired,
    ]
    for schema in test_schemas:
        converted = converter.convert_type(schema())
        assert converted == schema.schema_expected, f"Schema for [{schema.__name__}] not as expected"


def test_dropable_variable_mapping():
    """
    Validate that optional sub-schema using different parameters under ``variable`` schema resolve without error.

    Variable schemas with as sub-schema marked as ``missing=drop`` should allow it to be omitted and drop it.
    Similarly, omitted sub-value matching a schema with a ``default`` should allow it to be omitted and use the default.

    Also, ensure that the same ``variable`` sub-schemas without ``missing=drop`` nor ``default`` (i.e.: required) raise
    for data structure that could not be resolved to a variable sub-schema (either because it is missing or invalid).

    .. seealso::
        - :class:`weaver.wps_restapi.colander_extras.VariableSchemaNode`
    """

    class SomeList(ce.ExtendedSequenceSchema):
        item = ce.ExtendedSchemaNode(colander.String())

    class SomeMap(ce.ExtendedMappingSchema):
        field = ce.ExtendedSchemaNode(colander.String())

    class VarMapStrDrop(ce.ExtendedMappingSchema):
        var_str = ce.ExtendedSchemaNode(colander.String(), variable="<var_str>", missing=colander.drop)

    class VarMapListDrop(ce.ExtendedMappingSchema):
        var_list = SomeList(variable="<var_list>", missing=colander.drop)

    class VarMapMapDrop(ce.ExtendedMappingSchema):
        var_map = SomeMap(variable="<var_map>", missing=colander.drop)

    class VarMapStrDefault(ce.ExtendedMappingSchema):
        var_str = ce.ExtendedSchemaNode(colander.String(), variable="<var_str>", default="default")

    class VarMapListDefault(ce.ExtendedMappingSchema):
        var_list = SomeList(variable="<var_list>", default=["default"])

    class VarMapMapDefault(ce.ExtendedMappingSchema):
        var_map = SomeMap(variable="<var_map>", default={"field": "default"})

    class VarMapStrReq(ce.ExtendedMappingSchema):
        var_str = ce.ExtendedSchemaNode(colander.String(), variable="<var_str>")

    class VarMapListReq(ce.ExtendedMappingSchema):
        var_list = SomeList(variable="<var_list>")

    class VarMapMapReq(ce.ExtendedMappingSchema):
        var_map = SomeMap(variable="<var_map>")

    valid_var_str = {"dont-care": "value"}
    valid_var_list = {"dont-care": ["value"]}
    valid_var_map = {"dont-care": {"field": "value"}}  # 'field' exact name important, but not variable 'dont-care'
    # lowest sub-fields are string, int should raise
    invalid_var_str = {"dont-care": 1}
    invalid_var_list = {"dont-care": [1]}
    invalid_var_map = {"dont-care": {"field": 1}}
    missing_var = {}
    missing_var_list = {"dont-care": []}
    missing_var_map = {"dont-care": {}}

    test_schemas = [
        # whether required or missing variable sub-schema is allowed, result schema should all resolve correctly
        (VarMapStrDrop, valid_var_str, valid_var_str),
        (VarMapListDrop, valid_var_list, valid_var_list),
        (VarMapMapDrop, valid_var_map, valid_var_map),
        (VarMapStrDrop, missing_var, {}),
        (VarMapListDrop, missing_var, {}),
        (VarMapMapDrop, missing_var, {}),
        (VarMapListDrop, missing_var_list, {}),
        (VarMapMapDrop, missing_var_map, {}),
        (VarMapStrDefault, valid_var_str, valid_var_str),
        (VarMapListDefault, valid_var_list, valid_var_list),
        (VarMapMapDefault, valid_var_map, valid_var_map),
        (VarMapStrReq, valid_var_str, valid_var_str),
        (VarMapListReq, valid_var_list, valid_var_list),
        (VarMapMapReq, valid_var_map, valid_var_map),
        # for invalid schemas, only the allowed missing (drop) variable sub-schema should succeed
        (VarMapStrDrop, invalid_var_str, {}),
        (VarMapListDrop, invalid_var_list, {}),
        (VarMapMapDrop, invalid_var_map, {}),
        (VarMapStrDefault, invalid_var_str, {"dont-care": "default"}),
        (VarMapListDefault, invalid_var_list, {"dont-care": ["default"]}),
        (VarMapMapDefault, invalid_var_map, {"dont-care": {"field": "default"}}),
        (VarMapStrReq, invalid_var_str, colander.Invalid),
        (VarMapListReq, invalid_var_list, colander.Invalid),
        (VarMapMapReq, invalid_var_map, colander.Invalid),
    ]
    evaluate_test_cases(test_schemas)


def test_media_type_pattern():
    test_schema = sd.MediaType
    test_cases = [
        "application/atom+xml",
        "application/EDI-X12",
        "application/xml-dtd",
        "application/zip",
        "application/vnd.api+json",
        "application/json; indent=4",
        "video/mp4",
        "plain/text;charset=UTF-8",
        "plain/text; charset=UTF-8",
        "plain/text;    charset=UTF-8",
        "plain/text; charset=UTF-8; boundary=10"
    ]
    for test_value in test_cases:
        assert test_schema().deserialize(test_value) == test_value
    test_cases = [
        "random",
        "bad\\value",
        "; missing=type"
    ]
    for test_value in test_cases:
        try:
            test_schema().deserialize(test_value)
        except colander.Invalid:
            pass
        else:
            pytest.fail(f"Expected valid format from [{test_schema.__name__}] with: '{test_value}'")
