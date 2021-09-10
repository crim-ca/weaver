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

    for test_schema_ref, test_value, test_expect in test_cases:
        if inspect.isclass(test_schema_ref):
            test_schema = test_schema_ref()
            test_schema_name = test_schema_ref.__name__
        else:
            test_schema = test_schema_ref
            test_schema_name = type(test_schema_ref).__name__
        try:
            result = test_schema.deserialize(test_value)
            if test_expect is colander.Invalid:
                pytest.fail("Expected invalid format from [{}] with: {}, but received: {}".format(
                    test_schema_name, test_value, result))
            assert result == test_expect, "Bad result from [{}] with: {}".format(test_schema_name, test_value)
        except colander.Invalid:
            if test_expect is colander.Invalid:
                pass
            else:
                pytest.fail("Expected valid format from [{}] with: {}".format(test_schema_name, test_value))


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
            pytest.fail("Should not fail deserialize of '{!s}' with {!s}"
                        .format(ce._get_node_name(test_schema), test_value))
    for test_schema, test_value in [
        (ObjOneOf, {"key": None}),
        (ObjOneOf, {"items": None}),
        (ObjOneOf, {"items": ["value"], "key": "value"}),  # cannot have both (oneOf)
    ]:
        try:
            result = ObjOneOf().deserialize(test_value)
        except colander.Invalid:
            pass
        except Exception:
            raise AssertionError("Incorrect exception raised from deserialize of '{!s}' with {!s}"
                                 .format(ce._get_node_name(test_schema), test_value))
        else:
            raise AssertionError("Should have raised invalid schema from deserialize of '{!s}' with {!s}, but got {!s}"
                                 .format(ce._get_node_name(test_schema), test_value, result))


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
    try:
        result = MappingWithoutType().deserialize(value)
    except colander.Invalid:
        pass
    except Exception:
        raise AssertionError("Incorrect exception raised from deserialize of '{!s}' with {!s}"
                             .format(ce._get_node_name(MappingWithoutType), value))
    else:
        raise AssertionError("Should have raised invalid schema from deserialize of '{!s}' with {!s}, but got {!s}"
                             .format(ce._get_node_name(MappingWithoutType), value, result))

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
        assert converted == schema.schema_expected, "Schema for [{}] not as expected".format(schema.__name__)


def test_dropable_variable_mapping():
    """
    Validate that sub-schema marked with ``missing=drop`` under a ``variable`` schema resolve without error.

    Also, ensure that the same ``variable`` sub-schemas without ``missing=drop`` raise for invalid data structure.

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
        var_map = SomeMap(variable="<var_list>", missing=colander.drop)

    class VarMapStrReq(ce.ExtendedMappingSchema):
        var_str = ce.ExtendedSchemaNode(colander.String(), variable="<var_str>")

    class VarMapListReq(ce.ExtendedMappingSchema):
        var_list = SomeList(variable="<var_list>")

    class VarMapMapReq(ce.ExtendedMappingSchema):
        var_map = SomeMap(variable="<var_list>")

    valid_var_str = {"dont-care": "value"}
    valid_var_list = {"dont-care": ["value"]}
    valid_var_map = {"dont-care": {"field": "value"}}  # 'field' exact name important, but not variable 'dont-care'
    # lowest sub-fields are string, int should raise
    invalid_var_str = {"dont-care": 1}
    invalid_var_list = {"dont-care": [1]}
    invalid_var_map = {"dont-care": {"field": 1}}

    test_schemas = [
        # whether required or missing variable sub-schema is allowed, result schema should all resolve correctly
        (VarMapStrDrop, valid_var_str, valid_var_str),
        (VarMapListDrop, valid_var_list, valid_var_list),
        (VarMapMapDrop, valid_var_map, valid_var_map),
        (VarMapStrReq, valid_var_str, valid_var_str),
        (VarMapListReq, valid_var_list, valid_var_list),
        (VarMapMapReq, valid_var_map, valid_var_map),
        # for invalid schemas, only the allowed missing (drop) variable sub-schema should succeed
        (VarMapStrDrop, invalid_var_str, {}),
        (VarMapListDrop, invalid_var_list, {}),
        (VarMapMapDrop, invalid_var_map, {}),
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
            pytest.fail("Expected valid format from [{}] with: '{}'".format(test_schema.__name__, test_value))
