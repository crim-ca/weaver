"""
This module offers multiple utility schema definitions to be employed with :mod:`colander` and :mod:`cornice_swagger`.

The :class:`colander.SchemaNode` provided here can be used in-place of :mod:`colander`
ones, but giving you extended behaviour according to provided keywords. You can therefore
do the following and all will be applied without modifying your code base.

.. code-block:: python

    # same applies for Mapping and Sequence schemas
    from colander_extras import ExtendedSchemaNode as SchemaNode
    from colander import SchemaNode     # instead of this

The schemas support extended :mod:`cornice_swagger` type converters so that you
can generate OpenAPI-3 specifications. The original package support is limited
to Swagger-2. You will also need additional in-place modifications provided
`here <https://github.com/fmigneault/cornice.ext.swagger/tree/openapi-3>`_.

Since the intended usage is to generate JSON-deserialized data structures, the
base :class:`colander.SchemaNode` have some additional patches needed to handle
JSON-native type conversion that are not directly offered by :mod:`colander`

.. seealso::
    - https://github.com/Pylons/colander/issues/80

The main classes extensions are:
 - :class:`ExtendedSchemaNode`
 - :class:`ExtendedSequenceSchema`
 - :class:`ExtendedMappingSchema`

Multiple ``<ExtensionType>SchemaNode`` variants are provided. You can use them
as building blocks, gaining each of their respective feature, to make specific
schema that meets your desired behaviour. The ``Extended``-prefixed classes
combined all available ``<ExtensionType>``. Note that it is preferable to use
the full ``Extended``-prefixed classes over individual ones as they add
complementary support of one-another features.

.. warning::
    All node extensions assume that they are used for JSON data. Deserialization
    of unknown types *could* result in invalid result. Most of the time, Python
    native iterators such as tuples and generators *could* work and be converted
    to the corresponding sequence array (ie: list), but this is not guaranteed.

.. warning::
    When defining schema nodes, **DO NOT** use the ``name`` keyword otherwise
    most mapping will fail validation as they cannot retrieve the same key-name
    from the passed dictionary for ``deserialize`` validation. Let the API
    figure out the name of the field automatically. Instead, use the keyword
    or field ``title`` for adjusting the displayed name in the Swagger UI.
    The same value will also be used to generate the ``$ref`` reference names
    of generated OpenAPI model definitions. If not explicitly provided, the
    value of ``title`` **WILL** default to the name of the schema node class.
"""

# pylint: disable=E0241,duplicate-bases
# pylint: disable=C0209,consider-using-f-string

import copy
import inspect
import re
import uuid
from abc import abstractmethod
from typing import TYPE_CHECKING

import colander
from cornice_swagger.converters.exceptions import ConversionError, NoSuchConverter
from cornice_swagger.converters.parameters import (
    BodyParameterConverter,
    HeaderParameterConverter,
    ParameterConversionDispatcher,
    ParameterConverter,
    PathParameterConverter,
    QueryParameterConverter
)
from cornice_swagger.converters.schema import (
    STRING_FORMATTERS,
    BaseStringTypeConverter,
    BooleanTypeConverter,
    DateTimeTypeConverter,
    DateTypeConverter,
    IntegerTypeConverter,
    NumberTypeConverter,
    ObjectTypeConverter,
    StringTypeConverter,
    TimeTypeConverter,
    TypeConversionDispatcher,
    TypeConverter,
    ValidatorConversionDispatcher,
    convert_oneof_validator_factory,
    convert_range_validator,
    convert_regex_validator
)
from cornice_swagger.swagger import CorniceSwagger, DefinitionHandler, ParameterHandler, ResponseHandler
from jsonschema.validators import Draft7Validator

if TYPE_CHECKING:
    from typing import Any, Dict, Iterable, List, Optional, Sequence, Type, TypeVar, Union
    from typing_extensions import Literal, TypedDict

    from cornice import Service as CorniceService
    from pyramid.registry import Registry

    from weaver.typedefs import (
        JSON,
        OpenAPISchema,
        OpenAPISchemaAllOf,
        OpenAPISchemaAnyOf,
        OpenAPISchemaKeyword,
        OpenAPISchemaNot,
        OpenAPISchemaOneOf,
        OpenAPISpecification,
        OpenAPISpecInfo,
        OpenAPISpecParameter
    )

    DataT = TypeVar("DataT")
    VariableSchemaNodeMapped = TypedDict("VariableSchemaNodeMapped", {
        "node": str,  # variable schema-node that was mapped
        "name": str,  # property name in cstruct that was mapped
        "cstruct": Optional[JSON],  # child-cstruct content that was mapped
    }, total=True)
    VariableSchemaNodeMapping = Dict[str, List[VariableSchemaNodeMapped]]

try:
    RegexPattern = re.Pattern
except AttributeError:  # Python 3.6 backport  # pragma: no cover
    RegexPattern = type(re.compile("_"))


class MetadataTypeConverter(TypeConverter):
    """
    Converter that applies :term:`OpenAPI` schema metadata properties defined in the schema node.
    """
    def convert_type(self, schema_node):
        result = super(MetadataTypeConverter, self).convert_type(schema_node)
        deprecated = getattr(schema_node, "deprecated", False)
        if deprecated:
            result["deprecated"] = True
        return result


class ExtendedStringTypeConverter(MetadataTypeConverter, StringTypeConverter):
    pass


class ExtendedDateTypeConverter(MetadataTypeConverter, DateTypeConverter):
    pass


class ExtendedTimeTypeConverter(MetadataTypeConverter, TimeTypeConverter):
    pass


class ExtendedDateTimeTypeConverter(MetadataTypeConverter, DateTimeTypeConverter):
    pass


class ExtendedBooleanTypeConverter(MetadataTypeConverter, BooleanTypeConverter):
    pass


class ExtendedIntegerTypeConverter(MetadataTypeConverter, IntegerTypeConverter):
    pass


class ExtendedNumberTypeConverter(MetadataTypeConverter, NumberTypeConverter):
    pass


class ExtendedFloatTypeConverter(ExtendedNumberTypeConverter):
    format = "float"


class ExtendedDecimalTypeConverter(ExtendedNumberTypeConverter):
    format = "decimal"


class ExtendedMoneyTypeConverter(ExtendedDecimalTypeConverter):
    pass


LITERAL_SCHEMA_TYPES = frozenset([
    colander.Boolean,
    colander.Number,  # int, float, etc.
    colander.String,
    colander.Time,
    colander.Date,
    colander.DateTime,
    # colander.Enum,  # not supported but could be (literal int/str inferred from Python Enum object)
])

# patch URL with negative look-ahead to invalidate following // after scheme
NO_DOUBLE_SLASH_PATTERN = r"(?!.*//.*$)"
URL_REGEX = colander.URL_REGEX.replace(r"://)?", rf"://)?{NO_DOUBLE_SLASH_PATTERN}")
URL = colander.Regex(URL_REGEX, msg=colander._("Must be a URL"), flags=re.IGNORECASE)
FILE_URL_REGEX = colander.URI_REGEX.replace(r"://", r"://(?!//)")
FILE_URI = colander.Regex(FILE_URL_REGEX, msg=colander._("Must be a file:// URI scheme"), flags=re.IGNORECASE)
URI_REGEX = rf"{URL_REGEX[:-1]}(?:#?|[#?]\S+)$"
URI = colander.Regex(URI_REGEX, msg=colander._("Must be a URI"), flags=re.IGNORECASE)
STRING_FORMATTERS.update({
    # following MUST NOT use the 'StringTypeConverter' or 'ExtendedStringTypeConverter'
    # otherwise, it causes a recursion error when 'StringTypeConverter' tries to dispatch their parameter handling
    "uri": {"converter": BaseStringTypeConverter, "validator": URI},
    "url": {"converter": BaseStringTypeConverter, "validator": URL},
    "file": {"converter": BaseStringTypeConverter, "validator": FILE_URI},
})


def _make_node_instance(schema_node_or_class):
    # type: (Union[colander.SchemaNode, Type[colander.SchemaNode]]) -> colander.SchemaNode
    """
    Obtains a schema node instance in case it was specified only by type reference.

    This helps being more permissive of provided definitions while handling situations
    like presented in the example below:

    .. code-block:: python

        class Map(OneOfMappingSchema):
            # uses types instead of instances like 'SubMap1([...])' and 'SubMap2([...])'
            _one_of = (SubMap1, SubMap2)
    """
    if isinstance(schema_node_or_class, colander._SchemaMeta):  # noqa: W0212
        schema_node_or_class = schema_node_or_class()
    if not isinstance(schema_node_or_class, colander.SchemaNode):  # refer to original class to support non-extended
        raise ConversionTypeError(
            f"Invalid item should be a SchemaNode, got: {type(schema_node_or_class)!s}")
    return schema_node_or_class


def _get_schema_type(schema_node, check=False):
    # type: (Union[colander.SchemaNode, Type[colander.SchemaNode]], bool) -> Optional[colander.SchemaType]
    """
    Obtains the schema-type from the provided node, supporting various initialization methods.

    - ``typ`` is set by an instantiated node from specific schema (e.g.: ``colander.SchemaNode(colander.String())``)
    - ``schema_type`` can also be provided, either by type or instance if using class definition with property

    :param schema_node: item to analyse
    :param check: only attempt to retrieve the schema type, and if failing return ``None``
    :returns: found schema type
    :raises ConversionTypeError: if no ``check`` requested and schema type cannot be found (invalid schema node)
    """
    schema_node = _make_node_instance(schema_node)
    schema_type = getattr(schema_node, "typ", getattr(schema_node, "schema_type"))
    if isinstance(schema_type, type):
        schema_type = schema_type()  # only type instead of object, instantiate with default since no parameters anyway
    if not isinstance(schema_type, colander.SchemaType):
        if check:
            return None
        raise ConversionTypeError(f"Invalid schema type could not be detected: {type(schema_type)!s}")
    return schema_type


def _get_node_name(schema_node, schema_name=False):
    # type: (colander.SchemaNode, bool) -> str
    """
    Obtains the name of the node with the best available value.

    :param schema_node: node for which to retrieve the name.
    :param schema_name:
        - If ``True``, prefer the schema definition (class) name over the instance or field name.
        - Otherwise, return the field name, the title or as last result the class name.
    :returns: node name
    """
    title = getattr(schema_node, "title", None)
    if title in ["", colander.required]:
        title = None
    if schema_name:
        return title or type(schema_node).__name__
    return getattr(schema_node, "name", None) or title or type(schema_node).__name__


class SchemaNodeTypeError(TypeError):
    """
    Generic error indicating that the definition of a SchemaNode is invalid.

    This usually means the user forgot to specify a required element for schema creation,
    or that a provided combination of keywords, sub-nodes and/or schema type don't make
    any sense together, that they are erroneous, or that they cannot be resolved because
    of some kind of ambiguous definitions leading to multiple conflicting choices.
    """


class ConversionTypeError(ConversionError, TypeError):
    """
    Conversion error due to invalid type.
    """


class ConversionValueError(ConversionError, ValueError):
    """
    Conversion error due to invalid value.
    """


class OneOfCaseInsensitive(colander.OneOf):
    """
    Validator that ensures the given value matches one of the available choices, but allowing case-insensitive values.
    """

    def __init__(self, choices, *args, **kwargs):
        # type: (Iterable[str], Any, Any) -> None
        insensitive_choices = {}  # set with kept order
        for choice in choices:
            insensitive_choices.setdefault(choice, None)
            if isinstance(choice, str):
                # add common combinations (not technically all possible ones)
                insensitive_choices.setdefault(choice.lower(), None)
                insensitive_choices.setdefault(choice.upper(), None)
        insensitive_choices = list(insensitive_choices)
        super(OneOfCaseInsensitive, self).__init__(insensitive_choices, *args, **kwargs)

    def __call__(self, node, value):
        # type: (colander.SchemaNode, Any) -> None
        if str(value).lower() not in (choice.lower() for choice in self.choices):
            return super(OneOfCaseInsensitive, self).__call__(node, value)


class StringOneOf(colander.OneOf):
    """
    Validator that ensures the given value matches one of the available choices, but defined by string delimited values.
    """

    def __init__(self, choices, delimiter=",", case_sensitive=True, **kwargs):
        # type: (Iterable[str], str, bool, Any) -> None
        self.delimiter = delimiter
        if not case_sensitive:
            choices = OneOfCaseInsensitive(choices).choices
        super(StringOneOf, self).__init__(choices, **kwargs)

    def __call__(self, node, value):
        # type: (colander.SchemaNode, Any) -> None
        if not isinstance(value, str):
            super(StringOneOf, self).__call__(node, value)  # raise accordingly
        for val in value.split(self.delimiter):
            super(StringOneOf, self).__call__(node, val)  # raise accordingly


class BoundedRange(colander.Range):
    """
    Validator of value within range with added ``exclusive`` bounds support.
    """

    def __init__(self, min=None, max=None, exclusive_min=False, exclusive_max=False, **kwargs):
        # type: (Optional[Union[float, int]], Optional[Union[float, int]], bool, bool, Any) -> None
        self.min_excl = exclusive_min
        self.max_excl = exclusive_max
        super(BoundedRange, self).__init__(min=min, max=max, **kwargs)

    def __call__(self, node, value):
        super(BoundedRange, self).__call__(node, value)
        if self.min_excl and self.min is not None:
            if value <= self.min:
                min_err = colander._(
                    self.min_err, mapping={"val": value, "min": self.min, "exclusive": True}
                )
                raise colander.Invalid(node, min_err)

        if self.max_excl and self.max is not None:
            if value >= self.max:
                max_err = colander._(
                    self.max_err, mapping={"val": value, "max": self.max, "exclusive": True}
                )
                raise colander.Invalid(node, max_err)


class StringRange(BoundedRange):
    """
    Validator that provides the same functionalities as :class:`colander.Range` for a numerical string value.
    """

    def __init__(self, min=None, max=None, exclusive_min=False, exclusive_max=False, **kwargs):
        # type: (Optional[Union[float, int, str]], Optional[Union[float, int, str]], bool, bool, Any) -> None
        try:
            if isinstance(min, str):
                min = float(min) if "." in min or "e" in min else int(min)
            if isinstance(max, str):
                max = float(max) if "." in max or "e" in max else int(max)
        except (TypeError, ValueError):
            raise SchemaNodeTypeError("StringRange validator created with invalid min/max non-numeric string.")
        super(StringRange, self).__init__(
            min=min, max=max, exclusive_min=exclusive_min, exclusive_max=exclusive_max, **kwargs
        )

    def __call__(self, node, value):
        # type: (colander.SchemaNode, str) -> Union[float, int]
        if not isinstance(value, str):
            raise colander.Invalid(node=node, value=value, msg="Value is not a string.")
        if not str.isnumeric(value):
            raise colander.Invalid(node=node, value=value, msg="Value is not a numeric string.")
        return super(StringRange, self).__call__(node, float(value) if "." in value or "e" in value else int(value))


class CommaSeparated(colander.Regex):
    """
    Validator that ensures the given value is a comma-separated string.
    """
    _MSG_ERR = colander._("Must be a comma-separated string of tags with characters [${allow_chars}].")

    def __init__(self, allow_chars=r"A-Za-z0-9_-", msg=_MSG_ERR, flags=re.IGNORECASE):
        # type: (str, str, re.RegexFlag) -> None
        if "," in allow_chars:
            raise ValueError("Cannot have comma character for item in comma-separated string!")
        self.allow_chars = allow_chars
        msg = colander._(msg, mapping={"allow_chars": allow_chars})
        regex = rf"^[{allow_chars}]+(,[{allow_chars}]+)*$"
        super(CommaSeparated, self).__init__(regex=regex, msg=msg, flags=flags)


class SchemeURL(colander.Regex):
    """
    String representation of an URL with extended set of allowed URI schemes.

    .. seealso::
        :class:`colander.url` [remote http(s)/ftp(s)]
        :class:`colander.file_uri` [local file://]
        :data:`URL`
    """

    def __init__(self, schemes=None, path_pattern=None, msg=None, flags=re.IGNORECASE):
        # type: (Optional[Iterable[str]], Union[None, str, RegexPattern], Optional[str], Optional[re.RegexFlag]) -> None
        if not schemes:
            schemes = [""]
        if not msg:
            msg = colander._(f"Must be a URL matching one of schemes {schemes}")  # noqa
        regex_schemes = f"(?:{'|'.join(schemes)})"
        regex = URL_REGEX.replace(r"(?:http|ftp)s?", regex_schemes)

        if path_pattern:
            if isinstance(path_pattern, RegexPattern):
                path_pattern = path_pattern.pattern
            # depending colander version: $ end-of-line, \Z end-of-string (before \n if any), or \z end-of-string (\0)
            index = -2 if regex.lower().endswith(r"\z") else -1 if regex.endswith("$") else 0
            regex = rf"{regex[:index] + path_pattern}\Z"
        super(SchemeURL, self).__init__(regex, msg=msg, flags=flags)


class SemanticVersion(colander.Regex):
    """
    String representation that is valid against Semantic Versioning specification.

    .. seealso::
        https://semver.org/
    """

    def __init__(self, *args, v_prefix=False, rc_suffix=True, **kwargs):
        # type: (Any, bool, bool, Any) -> None
        if "regex" in kwargs:
            self.pattern = kwargs.pop("regex")
        else:
            v_prefix = "v" if v_prefix else ""
            rc_suffix = r"(\.[a-zA-Z0-9\-_]+)*" if rc_suffix else ""
            self.pattern = (
                f"^{v_prefix}\\d+(\\.\\d+(\\.\\d+{rc_suffix})*)*$"
            )
        super(SemanticVersion, self).__init__(regex=self.pattern, *args, **kwargs)


class ExtendedBoolean(colander.Boolean):
    def __init__(self, *args, true_choices=None, false_choices=None, allow_string=False, **kwargs):
        # type: (Any, Optional[Iterable[str]], Optional[Iterable[str]], bool, Any) -> None
        """
        Initializes the extended boolean schema node.

        When arguments :paramref:`true_choices` or :paramref:`false_choices` are provided, the corresponding string
        values are respectively considered as valid `truthy`/`falsy` values. Otherwise (default), ``strict`` values
        only of explicit type :class:`bool` will be considered valid.

        When values are specified :mod:`colander` converts them to string lowercase to compare against `truthy`/`falsy`
        values it should accept. For real `OpenAPI` typing validation, do **NOT** add other values like ``"1"`` to
        avoid conflict with :class:`ExtendedInteger` type for schemas that support both variants.  If an `OpenAPI`
        field is expected to support `truthy`/`falsy` values, it is recommended to explicitly define its schema using
        a ``oneOf`` keyword of all relevant schemas it supports, an any applicable validators for explicit values.
        This is the safest way to ensure the generated `OpenAPI` schema corresponds to expected type validation.
        """
        if not allow_string and true_choices is None and false_choices is None:
            # use strict variant
            self.true_choices = ()
            self.false_choices = ()
            self.true_val = "true"
            self.false_val = "false"
            self.false_reprs = [str(False)]
            self.true_reprs = [str(True)]
        else:
            # use normal variant (bool-like values)
            true_choices = true_choices if true_choices else ("true", )
            false_choices = false_choices if false_choices else ("false", )
            super(ExtendedBoolean, self).__init__(
                *args, true_choices=true_choices, false_choices=false_choices, **kwargs
            )

    def deserialize(self, node, cstruct):
        # type: (colander.SchemaNode, Any) -> Union[Type[colander.null, bool]]
        if cstruct is colander.null:
            return cstruct

        # strict type variant
        if not self.true_choices and not self.false_choices:
            # note: cannot compare with literal 'True' and 'False' since '0' and '1' are equivalent (implicit convert)
            if isinstance(cstruct, bool):
                return cstruct
            raise colander.Invalid(node, colander._("\"${val}\" is neither True or False.", mapping={"val": cstruct}))

        # normal type variant
        return super(ExtendedBoolean, self).deserialize(node, cstruct)


class ExtendedNumber(colander.Number):
    """
    Definition of a numeric value, either explicitly or implicit with permissive :class:`str` representation.

    Behaviour in each case:
        - ``strict=True`` and ``allow_string=False``:
          Value can only be explicit numeric type that matches exactly the base ``num`` type (default).
          All implicit conversion between :class:`float`, :class:`int` or :class:`str` are disallowed.
        - ``strict=True`` and ``allow_string=True``:
          Value can be the explicit numeric type (:class:`int` or :class:`float`) or a numeric :class:`str` value
          representing the corresponding base numeric type.
          Implicit conversion between :class:`float` and :class:`int` is still disallowed.
        - ``strict=False`` (``allow_string`` doesn't matter):
          Value can be anything as long as it can be converted to the expected numeric type
          (:class:`int` or :class:`float`).

    Recommended usage:
        - When making `OpenAPI` schema definitions for JSON body elements within a request or response object, default
          parameters ``strict=True`` and ``allow_string=False`` should be used to ensure the numeric type is respected.
          As for other literal data `Extended` schema types, keyword `oneOf` should be used when multiple similar value
          types are permitted for a field in order to document in `OpenAPI` the specific type definitions of expected
          data, which is automatically converted by ``json`` properties of request and response classes.
        - When defining `OpenAPI` query parameters, ``strict=True`` and ``allow_string=True`` should be used. This
          ensures that documented schemas still indicate only the numeric type as expected data format, although
          technically the ``path`` of the request will contain a :class:`str` representing the number. Queries are not
          automatically converted by request objects, but will be converted and validated as the explicit number
          following deserialization when using those configuration parameters.
    """

    def __init__(self, *_, allow_string=False, strict=True, **__):
        # default applied based on 'strict' in kwargs
        # then, make even stricter number validation if requested
        super(ExtendedNumber, self).__init__(*_, **__)
        if strict:
            self.num = self.number if allow_string else self.strict

    @staticmethod
    @abstractmethod
    def number(num):
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def strict(num):
        raise NotImplementedError


class ExtendedFloat(ExtendedNumber, colander.Float):
    """
    Float definition with strict typing validation by default.

    This is to distinguish it from explicit definitions of ``float``-like numbers or strings.
    By default, values such as ``"1"``, ``1.0``, ``True`` will not be automatically converted to equivalent ``1.0``.
    """

    def __init__(self, *_, allow_string=False, strict=True, **__):
        # type: (Any, bool, bool, Any) -> None
        colander.Float.__init__(self)
        ExtendedNumber.__init__(self, *_, strict=strict, allow_string=allow_string, **__)

    @staticmethod
    def number(num):
        if (isinstance(num, str) and "." in num) or isinstance(num, float):
            return float(num)
        raise ValueError("Value is not a Floating point number (Integer not allowed).")

    @staticmethod
    def strict(num):
        if not isinstance(num, float):
            raise ValueError("Value is not a Floating point number (Boolean, Integer and String not allowed).")
        return num

    def serialize(self, node, appstruct):
        result = super(ExtendedFloat, self).serialize(node, appstruct)
        if result is not colander.null:
            result = float(result)
        return result


class ExtendedInteger(ExtendedNumber, colander.Integer):
    """
    Integer definition with strict typing validation by default.

    This is to distinguish it from explicit definitions of ``integer``-like numbers or strings.
    By default, values such as ``"1"``, ``1.0``, ``True`` will not be automatically converted to equivalent ``1``.
    """

    def __init__(self, *_, allow_string=False, strict=True, **__):
        # type: (Any, bool, bool, Any) -> None
        colander.Integer.__init__(self)
        ExtendedNumber.__init__(self, *_, strict=strict, allow_string=allow_string, **__)

    @staticmethod
    def number(num):
        if not float(num).is_integer() or isinstance(num, bool):
            raise ValueError("Value is not an Integer number (Float not allowed).")
        return int(num)

    @staticmethod
    def strict(num):
        # note:
        #  - original colander function does not handle all cases
        #    (e.g.: float("1.23").is_integer() -> False, but still not a float)
        #  - furthermore, True/False are considered 'int', so must double check for 'bool'
        if not isinstance(num, int) or isinstance(num, bool):
            raise ValueError("Value is not an Integer number (Boolean, Float and String not allowed).")
        return num

    def serialize(self, node, appstruct):
        result = super(ExtendedInteger, self).serialize(node, appstruct)
        if result is not colander.null:
            result = int(result)
        return result


class ExtendedString(colander.String):
    """
    String with auto-conversion for known OpenAPI ``format`` field where no direct :mod:`colander` type exist.

    Converts :class:`uuid.UUID` to corresponding string when detected in the node if it defined ``format="uuid"``.

    For ``format="date"`` and ``format="date-time"``, consider instead using :class:`colander.Date`
    and :class:`colander.DateTime` respectively since more advanced support and features are provided with them.
    """

    def deserialize(self, node, cstruct):
        # type: (colander.SchemaNode, Any) -> str
        try:
            if str(getattr(node, "format", "")).lower() == "uuid":
                if isinstance(cstruct, str):
                    return str(uuid.UUID(cstruct))
                if isinstance(cstruct, uuid.UUID):
                    return str(cstruct)
        except ValueError:
            raise colander.Invalid(node, msg="Not a valid UUID string.", value=str(cstruct))
        return super(ExtendedString, self).deserialize(node, cstruct)


class NoneType(colander.SchemaType):
    """
    Type representing an explicit :term:`JSON` ``null`` value.
    """
    def serialize(self, node, appstruct):  # noqa
        # type: (colander.SchemaNode, Any) -> Union[None, colander.null, colander.drop]
        if appstruct in (colander.null, colander.drop):
            return appstruct
        if appstruct is None:
            return None
        raise colander.Invalid(
            node,
            colander._(
                "${val} cannot be processed: ${err}",
                mapping={"val": appstruct, "err": "Not 'null'."},
            ),
        )

    def deserialize(self, node, cstruct):
        # type: (colander.SchemaNode, Any) -> Union[None, colander.null, colander.drop]
        return self.serialize(node, cstruct)


class AnyType(colander.SchemaType):
    """
    Type representing any :term:`JSON` structure.
    """
    def serialize(self, node, appstruct):  # noqa
        # type: (colander.SchemaNode, Any) -> Any
        return appstruct

    def deserialize(self, node, cstruct):  # noqa
        # type: (colander.SchemaNode, Any) -> Any
        return cstruct


class XMLObject(object):
    """
    Object that provides mapping to known XML extensions for OpenAPI schema definition.

    Name of the schema definition in the OpenAPI will use :attr:`prefix` and the schema class name.
    Prefix can be omitted from the schema definition name by setting it to :class:`colander.drop`.
    The value of ``title`` provided as option or

    .. seealso::
        - https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.0.3.md#xml-object
        - https://swagger.io/docs/specification/data-models/representing-xml/
    """
    attribute = None    # define the corresponding node object as attribute instead of field
    name = None         # name of the attribute, or default to the class name of the object
    namespace = None    # location of "xmlns:<prefix> <location>" specification
    prefix = None       # prefix of the namespace
    wrapped = None      # used to wrap array elements called "<name>" within a block called "<name>s"

    @property
    def xml(self):
        spec = {}
        if isinstance(self.attribute, bool):
            spec["attribute"] = self.attribute
        if isinstance(self.name, str):
            spec["name"] = self.name
        if isinstance(self.namespace, str):
            spec["namespace"] = self.namespace
        if isinstance(self.prefix, str):
            spec["prefix"] = self.prefix
        if self.wrapped:  # only add if True to avoid over-populate spec, default is False
            spec["wrapped"] = self.wrapped
        return spec or None


class ExtendedNodeInterface(object):
    _extension = None  # type: str

    def _deserialize_impl(self, cstruct):
        raise NotImplementedError("ExtendedNodeInterface deserialize implementation missing")


class ExtendedSchemaMeta(colander._SchemaMeta):
    pass


class ExtendedSchemaBase(colander.SchemaNode, metaclass=ExtendedSchemaMeta):  # pylint: disable=E1139
    """
    Utility base node definition that initializes additional parameters at creation time of any other extended schema.

    When no explicit ``title`` is specified by either keyword argument or field definition within container class,
    default it to the literal name of the class defining the schema node. This title can then be employed by other
    extended schema implementations to define *cleaner* schema references, notably in the case of
    :class:`KeywordMapper` derived classes that do not necessarily have any explicit target ``name`` field.

    When the schema node is a simple field within a container schema (mapping, sequence, etc.), operation is skipped
    to avoid applying the generic ``SchemaNode`` or ``ExtendedSchemaNode`` name of the basic node class. In this case,
    converters already employ the target ``name`` of the class attribute of the container schema under which that node
    gets created.

    When the schema node is a generic :class:`colander.String` without explicit ``validator``, but that one can be
    inferred from either ``pattern`` or ``format`` OpenAPI definition, the corresponding ``validator`` gets
    automatically generated.
    """
    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def __init__(self, *args, **kwargs):
        # pylint: disable=E0203

        schema_name = _get_node_name(self, schema_name=True)
        schema_type = _get_schema_type(self, check=True)
        if isinstance(self, XMLObject):
            if isinstance(self.title, str):
                title = self.title
            else:
                title = kwargs.get("title", schema_name)
            # pylint: disable=no-member  # prefix added by XMLObject
            if self.prefix is not colander.drop:
                title = f"{self.prefix or 'xml'}:{title}"
            kwargs["title"] = title
        elif isinstance(schema_type, (colander.Mapping, colander.Sequence)):
            if self.title in ["", colander.required]:
                title = kwargs.get("title", schema_name)
                kwargs["title"] = title
                self.title = title

        if self.validator is None and isinstance(schema_type, colander.String):
            _format = kwargs.pop("format", getattr(self, "format", None))
            pattern = kwargs.pop("pattern", getattr(self, "pattern", None))
            if isinstance(pattern, (str, RegexPattern)):
                self.validator = colander.Regex(pattern)
            elif isinstance(pattern, colander.Regex):
                self.validator = pattern
            elif _format in STRING_FORMATTERS:
                self.validator = STRING_FORMATTERS[_format]["validator"]

        default = kwargs.get("default", colander.null)
        if self.default is colander.null and default is not colander.null:
            self.default = default
        if self.default is not colander.null and self.missing is not colander.drop:
            self.missing = self.default  # setting value makes 'self.required' return False, but doesn't drop it

        try:
            # if schema_type was defined with an instance instead of the class type,
            # we must pass it by "typ" keyword to avoid an error in base class calling 'schema_type()'
            # one case were using an instance is valid is for 'colander.Mapping(unknown="<handling-method>")'
            schema_type_def = getattr(self, "schema_type", None)
            if isinstance(schema_type_def, colander.SchemaType):
                kwargs["typ"] = schema_type_def
                kwargs["unknown"] = getattr(schema_type_def, "unknown", "ignore")
            super(ExtendedSchemaBase, self).__init__(*args, **kwargs)
            ExtendedSchemaBase._validate(self)
        except Exception as exc:
            raise SchemaNodeTypeError(f"Invalid schema definition for [{schema_name}]") from exc

    @staticmethod
    def _validate(node):
        if isinstance(node, colander.deferred):
            return
        if node.default and node.validator not in [colander.null, None]:
            try:
                node.validator(node, node.default)
            except (colander.Invalid, TypeError):
                if node.default is not colander.drop:
                    raise SchemaNodeTypeError(
                        "Default value [{!s}] of [{!s}] is not valid against its own validator.".format(
                            node.default, _get_node_name(node, schema_name=True))
                    )


class DropableSchemaNode(ExtendedNodeInterface, ExtendedSchemaBase):
    """
    Schema that can be dropped if the value is missing.

    Drops the underlying schema node if ``missing=drop`` was specified and that the value
    representing it represents an *empty* value instead of raising a invalid schema error.

    In the case of nodes corresponding to literal schema type (i.e.: Integer, String, etc.),
    the *empty* value looked for is ``None``. This is to make sure that ``0`` or ``""`` are
    preserved unless explicitly representing *no-data*. In the case of container
    schema types (i.e.: list, dict, etc.), it is simply considered *empty* if there are no
    element in it, without any more explicit verification.

    Original behaviour of schema classes that can have children nodes such as
    :class:`colander.MappingSchema` and :class:`colander.SequenceSchema` are to drop the sub-node
    only if its value is resolved as :class:`colander.null` or :class:`colander.drop`. This results
    in *optional* field definitions replaced by ``None`` in many implementations to raise
    :py:exc:`colander.Invalid` during deserialization. Inheriting this class in a schema definition
    will handle this situation automatically.

    Required schemas (without ``missing=drop``, defaulting to :class:`colander.required`) will
    still raise for undefined nodes.

    The following snippet shows the result that can be achieved using this schema class:

    .. code-block:: python

        class SchemaA(DropableSchemaNode, MappingSchema):
            field = SchemaNode(String())

        class SchemaB(MappingSchema):
            s1 = SchemaA(missing=drop)   # optional
            s2 = SchemaA()               # required

        SchemaB().deserialize({"s1": None, "s2": {"field": "ok"}})
        # results: {'s2': {'field': 'ok'}}

    .. seealso::
        - https://github.com/Pylons/colander/issues/276
        - https://github.com/Pylons/colander/issues/299

    .. seealso::
        - :class:`DropableMappingSchema`
        - :class:`DropableSequenceSchema`
    """
    _extension = "_ext_dropable"

    def __init__(self, *args, **kwargs):
        super(DropableSchemaNode, self).__init__(*args, **kwargs)
        setattr(self, DropableSchemaNode._extension, True)

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def deserialize(self, cstruct):  # pylint: disable=W0222,signature-differs
        return ExtendedSchemaNode.deserialize(self, cstruct)  # noqa

    def _deserialize_impl(self, cstruct):
        if not getattr(self, DropableSchemaNode._extension, False):
            return cstruct
        if self.default is colander.null and self.missing is colander.drop:
            if cstruct is colander.drop:
                return colander.drop
            containers = (colander.SequenceSchema.schema_type,
                          colander.MappingSchema.schema_type,
                          colander.TupleSchema.schema_type)
            if self.schema_type in containers and not cstruct:
                return colander.drop
            elif cstruct in (None, colander.null):
                return colander.drop
        return cstruct


class DefaultSchemaNode(ExtendedNodeInterface, ExtendedSchemaBase):
    """
    Schema that will return the provided default value when the corresponding value is missing or invalid.

    If ``default`` keyword is provided during :class:`colander.SchemaNode` creation, overrides the
    returned value by this default if missing from the structure during :meth:`deserialize` call.

    Original behaviour was to drop the missing value instead of replacing by ``default``.
    Executes all other :class:`colander.SchemaNode` operations normally.

    .. seealso::
        - :class:`DefaultMappingSchema`
        - :class:`DefaultSequenceSchema`
    """

    _extension = "_ext_default"

    def __init__(self, *args, **kwargs):
        super(DefaultSchemaNode, self).__init__(*args, **kwargs)
        setattr(self, DefaultSequenceSchema._extension, True)

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def deserialize(self, cstruct):  # pylint: disable=W0222,signature-differs
        return ExtendedSchemaNode.deserialize(self, cstruct)  # noqa

    def _deserialize_impl(self, cstruct):
        if not getattr(self, DefaultSchemaNode._extension, False):
            return cstruct
        if cstruct is colander.null and self.required and self.default in (colander.null, colander.drop):
            raise colander.Invalid(node=self, msg="Missing value for required field without any default.")
        # if nothing to process in structure, ask to remove (unless picked by default)
        result = colander.drop
        if cstruct is not colander.null:
            result = cstruct
        if not isinstance(self.default, type(colander.null)) and result is colander.drop:
            result = self.default
        return result


class VariableSchemaNode(ExtendedNodeInterface, ExtendedSchemaBase):
    """
    Object schema that allows defining a field key as *variable* by name supporting deserialization validation.

    This definition is useful for defining a dictionary where the key name can be any string value but contains
    an underlying schema that has a very specific structure to be validated, such as in the following example.

    .. code-block:: json

        {
            "<any-key-id>": {
                "name": "required",
                "value": "something"
            },
            "<another-key-id>": {
                "name": "other required",
                "value": "same schema"
            }
        }

    This is accomplished using the following definition::

        class RequiredDict(ExtendedMappingSchema):
            name = ExtendedSchemaNode(String())
            value = ExtendedSchemaNode(String())

        class ContainerAnyKey(ExtendedMappingSchema):
            var = RequiredDict(variable="{id}")

    In the above example, the ``var`` node name that would normally be
    automatically generated and used to define the dictionary key will be
    replaced by ``{id}`` (any string provided by ``variable`` keyword).
    The actual attribute name ``var`` could be replaced by anything.

    .. warning::
        Since ``variable`` tells the deserialization converter to try matching any valid
        children node schema with the provided structure regardless of key name, you
        should ensure that the variable child node has at least one :class:`colander.required`
        field (either directly or much deeper in the structure) to ensure it has something
        to validate against. Otherwise, anything will be matched (ie: drop all for empty
        structure would be considered as valid).

        The above statement also applies in case you provide more than one variable
        schema node under a mapping where both underlying schema are different. Without any
        required child node to distinguish between them, the sub-structure under each variable
        node *could* end up interchanged.

    .. note::
        It is recommended to use variable names that include invalid characters for
        class/attribute names (e.g.: ``{}`` or ``<>``) in order to ensure that any substitution
        when attempting to find the schema matching the variable doesn't result in overrides.
        As presented in the following example, ``const`` *could* get overridden if there was a
        structure to parse that contained both the ``const`` sub-structure and another one with
        an arbitrary key matched against ``<var>``.

    .. note::
        In order to avoid invalid rendering of ``<>`` strings (interpreted as HTML tags by Swagger-UI),
        it is recommended to employ ``{}`` notation for representing variable names.

        .. code-block:: python

            class ContainerAnyKeyWithName(ExtendedMappingSchema):
                var = RequiredDict(variable="const")  # 'const' could clash with other below
                const = RequiredDict(String())

        Using ``{const}`` instead would ensure that no override occurs as it is a syntax error
        to write ``{const} = RequiredDict(String())`` in the class definition, but this value
        can still be used to create the internal mapping to evaluate sub-schemas without name
        clashes. As a plus, it also helps indicating that *any key* is accepted.

    .. seealso::
        - :class:`ExtendedSchemaNode`
        - :class:`ExtendedMappingSchema`
    """

    _extension = "_ext_variable"
    _variable = "variable"          # name of property containing variable name
    _variable_map = "variable_map"  # name of property containing variable => real node/key matched

    @classmethod
    def is_variable(cls, node):
        # type: (colander.SchemaNode) -> bool
        """
        If current node is the variable field definition.
        """
        return getattr(node, cls._variable, None) is not None

    def has_variables(self):
        """
        If the current container schema node has sub-node variables.
        """
        if isinstance(_get_schema_type(self), colander.Mapping):
            return any(VariableSchemaNode.is_variable(node) for node in self.children)
        return False

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def __init__(self, *args, **kwargs):
        # define node with provided variable by keyword or within a SchemaNode class definition
        var = kwargs.pop(self._variable, getattr(self, self._variable, None))
        super(VariableSchemaNode, self).__init__(*args, **kwargs)
        if var:
            # note: literal type allowed only for shorthand notation, normally not allowed
            schema_type = _get_schema_type(self)
            if not isinstance(schema_type, tuple(list(LITERAL_SCHEMA_TYPES) + [colander.Mapping])):  # noqa
                raise SchemaNodeTypeError(
                    "Keyword 'variable' can only be applied to Mapping and literal-type schema nodes. "
                    "Got: {!s} ({!s})".format(type(self), schema_type))
            node_name = _get_node_name(self, schema_name=True)
            var_title = kwargs.get("name", var)
            self.name = f"{node_name}<{var_title}>"
            if not self.title:
                self.title = var
                self.raw_title = var
            setattr(self, self._variable, var)
        self._mark_variable_children()
        setattr(self, VariableSchemaNode._extension, True)

    def _mark_variable_children(self):
        """
        Ensures that any immediate children schema with variable key are detected.

        Verifies if a :class:`colander.MappingSchema` (or any of its extensions)
        contains children :class:`VariableSchemaNode` schema nodes for adequate
        :meth:`deserialize` result later on.

        If children nodes are detected as *variable*, this schema is marked for
        special processing of the children nodes so they don't get removed from the result
        (in case of optional field specified by ``missing=drop``) nor raise
        :class:`colander.Invalid` because they are supposed to be :class:`colander.required`.

        .. note::
            Because mapping schema deserialization is normally processed by validating the
            content of a sub-node according to its ``name``, it is not possible to use
            the normal approach (i.e.: get dictionary value under matching key-name and validate
            it against the sub-schema of same name). We must verify against every *variable* node
            available in the mapping (also ignoring constants nodes with explicitly named keys),
            then guess a valid match and finally return it with modified name corresponding to
            the expected ``variable`` value in the parent mapping schema. Returning this modified
            ``name`` with ``variable`` makes the value/sub-schema correspondence transparent to
            the parent mapping when dictionary get-by-key is called during the mapping validation.

        .. warning::
            Because of the above reversed-processing method, all *mapping* nodes must derive from
            :class:`VariableSchemaNode` to ensure they pre-process potential *variable* candidates.
        """
        typ = type(_get_schema_type(self))
        if typ is colander.Mapping:
            # FIXME: handle 'patternProperties' along 'additionalProperties' (detect 'variable' + 'pattern' arguments?)
            #   This would allow mapping to more than only one list-item in 'var_full_search'
            #   (ie: 1 for 'additionalProperties' + N * patterns nested in 'patternProperties')
            var_children = self._get_sub_variable(self.children)
            var_full_search = [var_children]
            for var_subnodes in var_full_search:
                if len(var_subnodes):
                    var_names = [child.name for child in var_subnodes]
                    for var in var_names:
                        if len([v for v in var_names if v == var]) == 1:
                            continue
                        raise SchemaNodeTypeError("Invalid node '{}' defines multiple schema nodes "
                                                  "with name 'variable={}'.".format(type(self), var))
                    var_map = {getattr(child, self._variable, None): child for child in var_subnodes}
                    setattr(self, self._variable_map, var_map)

    def _get_sub_variable(self, subnodes):
        # type: (Iterable[colander.SchemaNode]) -> List[VariableSchemaNode]
        return [child for child in subnodes if getattr(child, self._variable, None)]

    def deserialize(self, cstruct):  # pylint: disable=W0222,signature-differs
        return ExtendedSchemaNode.deserialize(self, cstruct)  # noqa

    @staticmethod
    def _check_deserialize(node, cstruct):
        if not getattr(node, VariableSchemaNode._extension, False):
            return False
        if cstruct in (colander.drop, colander.null):
            return False
        # skip step in case operation was called as sub-node from another schema but doesn't
        # correspond to a valid variable map container (e.g.: SequenceSchema)
        if not isinstance(node, VariableSchemaNode):
            return False
        var_map = getattr(node, node._variable_map, {})
        if not isinstance(var_map, dict) or not len(var_map):
            return False
        # value must be a dictionary map object to allow variable key
        if not isinstance(cstruct, dict):
            msg = f"Variable key not allowed for non-mapping data: {type(cstruct).__name__}"
            raise colander.Invalid(node=node, msg=msg, value=cstruct)
        return True

    @staticmethod
    def _deserialize_remap(node, cstruct, var_map, var_name, has_const_child):
        invalid_var = colander.Invalid(node, value=var_map)
        try:
            # ensure to use a copy to avoid modifying a structure passed down to here since we pop variable-mapped keys
            cstruct = copy.deepcopy(cstruct)

            # Substitute real keys with matched variables to run full deserialize so
            # that mapping can find nodes name against attribute names, then re-apply originals.
            # We must do this as non-variable sub-schemas could be present, and we must also
            # validate them against full schema.
            if not has_const_child:
                result = node.default or {}
            else:
                remapped = {}
                var_value = None
                for mapped in var_map.values():
                    if not mapped:
                        continue  # ignore missing for now, raise after as needed if required
                    # Temporarily remove pre-validated/mapped variable schema nodes to validate constants.
                    # If we happen to remove the same property twice, it means two variable schema node were
                    # in use at the same time (valid), but they were not sufficiently strict to distinguish to
                    # which one the property should be mapped (e.g.: two generic strings with no validators).
                    for var_mapped in mapped:
                        var_prop = var_mapped["name"]
                        var_node = var_mapped["node"]
                        try:
                            var_value = cstruct.pop(var_prop)
                            remapped[var_prop] = {"node": var_node, "value": var_value}
                        except KeyError:
                            var_prev = remapped[var_prop]["node"]
                            raise colander.Invalid(
                                node,
                                msg=(
                                    f"Two distinct variable schema nodes named ['{var_prev}', '{var_node}'] "
                                    f"under '{_get_node_name(node)}' were simultaneously mapped as valid matches "
                                    f"for field '{var_prop}' resolution. "
                                    "Ambiguous children schema definitions cannot be resolved. "
                                    "Consider defining more strict schema types, validators, keywords, "
                                    "or by modifying the parent variable schema to resolve the ambiguity."
                                ),
                                value={var_prop: var_value},
                            )
                # temporarily bypass variable to avoid recursively calling this extension deserialization
                # perform the 'normal' mapping deserialization to obtain explicit properties
                mapping = ExtendedMappingSchema(name=node.name, missing=node.missing, default=node.default)
                var_children = node._get_sub_variable(node.children)
                mapping.children = [child for child in node.children if child not in var_children]
                result = mapping.deserialize(cstruct)  # noqa
            for mapped in var_map.values():
                # invalid if no variable match was found, unless optional
                if mapped is None and node.missing is colander.required:
                    raise colander.Invalid(node, value=cstruct)
                for var_mapped in mapped:
                    # variable schema validation failed, but it is not marked as 'required'
                    if var_mapped["cstruct"] not in [colander.drop, colander.null]:
                        result[var_mapped["name"]] = var_mapped["cstruct"]
        except colander.Invalid as invalid:
            if invalid.msg:
                invalid_var.msg = invalid.msg
                invalid_var.value = invalid.value
            else:
                invalid_var.msg = f"Tried matching variable '{var_name}' sub-schemas but no match found."
            invalid_var.add(invalid)
            raise invalid_var
        except KeyError:
            invalid_var.msg = f"Tried matching variable '{var_name}' sub-schemas but mapping failed."
            raise invalid_var
        if not isinstance(result, dict):
            raise TypeError("Variable result must be of mapping schema type. Got [{}] value {}".format(
                _get_node_name(node, schema_name=True), result
            ))
        return result

    def _deserialize_impl(self, cstruct):
        if not VariableSchemaNode._check_deserialize(self, cstruct):
            return cstruct
        var_children = self._get_sub_variable(self.children)
        const_child_keys = [child.name for child in self.children if child not in var_children]
        var = None
        var_map = {}  # type: VariableSchemaNodeMapping
        var_map_invalid = {}  # type: Dict[str, colander.Invalid]
        for var_child in var_children:
            var = getattr(var_child, self._variable, None)
            var_map.setdefault(var, [])
            var_msg = f"Requirement not met under variable: {var}."
            var_map_invalid[var] = colander.Invalid(node=self, msg=var_msg, value=cstruct)
            # attempt to find any sub-node matching the sub-schema under variable
            for child_key, child_cstruct in cstruct.items():
                # skip explicit nodes (combined use of properties and additionalProperties)
                if child_key in const_child_keys:
                    continue
                schema_class = _make_node_instance(var_child)
                try:
                    var_cstruct = schema_class.deserialize(child_cstruct)
                    if var_cstruct in [colander.drop, colander.null]:
                        if var_child.missing is colander.drop:
                            continue
                        if var_child.default not in [colander.drop, colander.null]:
                            var_cstruct = var_child.default
                    # not reached if previous raised invalid
                    var_map[var].append({
                        "node": schema_class.name,
                        "name": child_key,
                        "cstruct": var_cstruct
                    })
                except colander.Invalid as invalid:
                    if var_child.missing is colander.drop:
                        continue
                    if var_child.missing is not colander.required:
                        var_map[var].append({
                            "node": schema_class.name,
                            "name": child_key,
                            "cstruct": var_child.default
                        })
                    else:
                        # use position as tested child field name for later reference by invalid schema
                        var_map_invalid[var].add(invalid, pos=child_key)

            var_mapped = var_map.get(var, [])
            if not var_mapped:
                # allow unmatched/unprovided variable item under mapping if it is not required
                if var_child.missing in [colander.drop, colander.null]:
                    continue
                # if required, don't waste more time doing lookup
                # fail immediately since this variable schema is missing
                raise var_map_invalid[var]

            # invalid if no variable match was found, unless optional
            for mapped in var_map.values():
                if len(mapped) < 1 and var_child.missing is colander.required:
                    raise var_map_invalid[var]

        self._validate_cross_variable_mapping(var_map)
        self._validate_unmatched_variable_mapping(var_map, var_map_invalid, const_child_keys, cstruct)
        return VariableSchemaNode._deserialize_remap(self, cstruct, var_map, var, bool(const_child_keys))

    def _validate_cross_variable_mapping(self, variable_mapping):
        # type: (VariableSchemaNodeMapping) -> None
        """
        Ensure there are no matches of the same child-property across multiple variable child-schema.

        In such case, the evaluated variable mapping is ambiguous, and cannot discriminate which property validates
        the schema. Therefore, the full mapping schema containing the variables would be invalid.

        There are 2 possible situations where there could be multiple variable child-schema.
        Either ``additionalProperties`` and ``patternProperties`` capability is supported and employed simultaneously,
        or the schema class definition is invalid. It is not allowed to have 2 generic ``additionalProperties``
        assigned simultaneously to 2 distinct child-schema. A single child-schema using a keyword mapping should
        be used instead to define such combinations.
        """
        if len(variable_mapping) > 1:
            var_cross_matches = {}
            for var, var_mapped in variable_mapping.items():
                for other_var in set(variable_mapping) - {var}:
                    other_mapped = variable_mapping[other_var]
                    for mapped in var_mapped:
                        for other in other_mapped:
                            if mapped["name"] == other["name"]:
                                var_cross_matches.setdefault(var, [])
                                var_cross_matches[var].append((var, other, mapped["name"], mapped["cstruct"]))
            if var_cross_matches:
                err_msg = (
                    "Mapping with multiple variable schema node is ambiguous. "
                    "More than one variable schema matched against multiple child properties. "
                    "Schema validation cannot disambiguate property mapping."
                )
                var_cross_invalid = colander.Invalid(self, msg=err_msg)
                for match in var_cross_matches:
                    match_msg = (
                        f"Schemas with variables '{match[0]}' and '{match[1]}' are both valid "
                        f"against property '{match[2]}' with value {match[3]}."
                    )
                    var_cross_invalid.add(colander.Invalid(self, msg=match_msg))
                raise var_cross_invalid

    def _validate_unmatched_variable_mapping(
        self,
        variable_mapping,                   # type: VariableSchemaNodeMapping
        invalid_mapping,                    # type: Dict[str, colander.Invalid]
        constant_children_schema_names,     # type: List[str]
        cstruct,                            # type: JSON
    ):                                      # type: (...) -> None
        """
        Validate if any additional properties that could not be mapped by variables are permitted in the mapping schema.
        """
        if self.typ.unknown == "raise":
            mapped_child_names = {mapped["name"] for var in variable_mapping for mapped in variable_mapping[var]}
            missing_child_names = set(cstruct) - set(constant_children_schema_names) - mapped_child_names
            if missing_child_names:
                var_invalid = colander.Invalid(
                    self,
                    msg="Unknown properties or invalid additional property schema in mapping.",
                    value=cstruct,
                )
                for child_name in missing_child_names:
                    for var_unmapped_invalid in invalid_mapping.values():
                        for var_child_instance_invalid in var_unmapped_invalid.children:
                            if var_child_instance_invalid.pos == child_name:
                                var_child_instance_invalid.pos = f"{var_child_instance_invalid.node.name}({child_name})"
                                var_child_instance_invalid.positional = True  # force "pos" name instead of schema name
                                var_invalid.add(var_child_instance_invalid)
                                break
                raise var_invalid


class SortableMappingSchema(ExtendedNodeInterface, ExtendedSchemaBase):
    """
    Adds sorting capabilities to mapping schema.

    Extended schema nodes that inherit from :class:`colander.Mapping` schema-type such that they can request
    ordering of resulting fields by overriding properties :attr:`_sort_first` and :attr:`_sort_after` within
    the schema definition with lists of fields names to sort.

    .. seealso::
        - :func:`_order_deserialize`
    """

    _extension = "_ext_sortable"
    _sort_first = []  # type: Sequence[str]
    _sort_after = []  # type: Sequence[str]

    def __init__(self, *args, **kwargs):
        super(SortableMappingSchema, self).__init__(*args, **kwargs)
        setattr(self, SortableMappingSchema._extension, True)

    def deserialize(self, cstruct):  # pylint: disable=W0222,signature-differs
        return ExtendedSchemaNode.deserialize(self, cstruct)  # noqa

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def _deserialize_impl(self, cstruct):
        if not getattr(self, SortableMappingSchema._extension, False):
            return cstruct
        if not isinstance(cstruct, dict):
            return cstruct

        sort_first = getattr(self, "_sort_first", [])
        sort_after = getattr(self, "_sort_after", [])
        if sort_first or sort_after:
            return self._order_deserialize(cstruct, sort_first, sort_after)
        return cstruct

    @staticmethod
    def _order_deserialize(cstruct, sort_first=None, sort_after=None):
        # type: (Dict[str, Any], Optional[Sequence[str]], Optional[Sequence[str]]) -> Dict[str, Any]
        """
        Enforces ordering of expected fields in deserialized result, regardless of specified children/inherited schema.

        This function takes care of moving back items in a consistent order for better readability from API responses
        against different loaded definitions field order from remote servers, local database, pre-defined objects, etc.

        This way, any field insertion order from both the input ``cstruct`` following deserialization operation, the
        internal mechanics that :mod:`colander` (and extended OpenAPI schema definitions) employ to process this
        deserialization, and the ``result`` dictionary fields order obtained from it all don't matter.

        Using this, the order of inheritance of schema children classes also doesn't matter, removing the need to worry
        about placing classes in any specific order when editing and joining the already complicated structures of
        inherited schemas.

        :param cstruct: JSON structure to be sorted that has already been processed by a schema's ``deserialize`` call.
        :param sort_first: ordered list of fields to place first in the result.
        :param sort_after: ordered list of fields to place last in the result.
        :returns: results formed from cstruct following order: (<fields_firsts> + <other_fields> + <fields_after>)
        """
        sort_first = sort_first if sort_first else []
        sort_after = sort_after if sort_after else []
        result = {field: cstruct.pop(field, None) for field in sort_first if field in cstruct}
        remain = {field: cstruct.pop(field, None) for field in sort_after if field in cstruct}
        result.update(cstruct)
        result.update(remain)
        return result


class SchemaRefMappingSchema(ExtendedNodeInterface, ExtendedSchemaBase):
    """
    Mapping schema that supports auto-insertion of JSON-schema references provided in the definition.

    Schema references are resolved under two distinct contexts:

    1. When generating the :term:`JSON` schema representation of the current schema node, for :term:`OpenAPI`
       representation, the ``_schema`` attribute will indicate the ``$id`` value that identifies this schema,
       while the ``_schema_meta`` will provide the ``$schema`` property that refers to the :term:`JSON` meta-schema
       used by default to define it.

    2. When deserializing :term:`JSON` data that should be validated against the current schema node, the generated
       :term:`JSON` data will include the ``$schema`` property using the ``_schema`` attribute. In this case,
       the ``$id`` is omitted as that :term:`JSON` represents an instance of the schema, but not its identity.

    Alternatively, the parameters ``schema`` and ``schema_meta`` can be passed as keyword arguments when instantiating
    the schema node. The references injection in the :term:`JSON` schema and data can be disabled with parameters
    ``schema_include`` and ``schema_meta_include``, or the corresponding class attributes. Furthermore, options
    ``schema_include_deserialize``, ``schema_include_convert_type`` and ``schema_meta_include_convert_type`` can be
    used to control individually each schema inclusion during either the type conversion context (:term:`JSON` schema)
    or the deserialization context (:term:`JSON` data validation).

    Additionally, the ``_schema_extra`` attribute and the corresponding ``schema_extra`` initialization parameter can
    be specified to inject further :term:`OpenAPI` schema definitions into the generated schema. Note that duplicate
    properties specified by this extra definition will override any automatically generated schema properties.
    """
    _extension = "_ext_schema_ref"
    _ext_schema_options = [
        "_schema_meta",
        "_schema_meta_include",
        "_schema_meta_include_convert_type",
        "_schema",
        "_schema_include",
        "_schema_include_deserialize",
        "_schema_include_convert_type",
        "_schema_extra",
    ]
    _ext_schema_fields = ["_id", "_schema", "_schema_extra"]

    # typings and attributes to help IDEs flag that the field is available/overridable

    _schema_meta = Draft7Validator.META_SCHEMA["$schema"]  # type: str
    _schema_meta_include = True                 # type: bool
    _schema_meta_include_convert_type = True    # type: bool

    _schema = None                              # type: str
    _schema_include = True                      # type: bool
    _schema_include_deserialize = True          # type: bool
    _schema_include_convert_type = True         # type: bool

    _schema_extra = None  # type: Optional[OpenAPISchema]

    def __init__(self, *args, **kwargs):
        for schema_key in self._schema_options:
            schema_field = schema_key[1:]
            schema_value = kwargs.pop(schema_field, object)
            if schema_value is not object:
                setattr(self, schema_key, schema_value)
        super(SchemaRefMappingSchema, self).__init__(*args, **kwargs)
        setattr(self, SchemaRefMappingSchema._extension, True)

        for schema_key in self._schema_fields:
            schema_field = f"${schema_key[1:]}"
            sort_first = getattr(self, "_sort_first", [])
            sort_after = getattr(self, "_sort_after", [])
            if schema_field not in sort_first + sort_after:
                setattr(self, "_sort_first", [schema_field] + list(sort_first))

    @staticmethod
    def _is_schema_ref(schema_ref):
        # type: (Any) -> bool
        return isinstance(schema_ref, str) and URI.match_object.match(schema_ref)

    @property
    def _schema_options(self):
        return getattr(self, "_ext_schema_options", SchemaRefMappingSchema._ext_schema_options)

    @property
    def _schema_fields(self):
        return getattr(self, "_ext_schema_fields", SchemaRefMappingSchema._ext_schema_fields)

    def _schema_deserialize(self, cstruct, schema_meta=None, schema_id=None, schema_extra=None):
        # type: (OpenAPISchema, Optional[str], Optional[str], Optional[OpenAPISchema]) -> OpenAPISchema
        """
        Applies the relevant schema references and properties depending on :term:`JSON` schema/data conversion context.
        """
        if not isinstance(cstruct, dict):
            return cstruct
        if not getattr(self, SchemaRefMappingSchema._extension, False):
            return cstruct

        schema_result = {}
        schema_fields = [("schema", schema_meta), ("id", schema_id)]
        for schema_key, schema_ref in schema_fields:
            if self._is_schema_ref(schema_ref):
                schema_field = f"${schema_key}"
                schema = ExtendedSchemaNode(
                    colander.String(),
                    name=schema_field,
                    title=schema_field,
                    missing=schema_ref,
                    default=schema_ref,
                    validator=colander.OneOf([schema_ref])
                )
                schema_result[schema_field] = schema.deserialize(cstruct.get(schema_field))

        schema_result.update(cstruct)
        schema_result.update(schema_extra or {})
        return schema_result

    def _deserialize_impl(self, cstruct):  # pylint: disable=W0222,signature-differs
        # type: (DataT) -> DataT
        """
        Converts the data using validation against the :term:`JSON` schema definition.
        """
        # don't inject the schema meta/id if the mapping is empty
        # this is to avoid creating a non-empty mapping, which often as a "special" meaning
        # furthermore, when the mapping is empty, there is no data to ensuring this schema is actually applied
        if not cstruct:
            return cstruct
        # meta-schema always disabled in this context since irrelevant
        # refer to the "id" of the parent schema representing this data using "$schema"
        # this is not "official" JSON requirement, but very common in practice
        schema_id = None
        schema_id_include = getattr(self, "_schema_include", False)
        schema_id_include_deserialize = getattr(self, "_schema_include_deserialize", False)
        if schema_id_include and schema_id_include_deserialize:
            schema_id = getattr(self, "_schema", None)
        if schema_id:
            return self._schema_deserialize(cstruct, schema_id, None)
        return cstruct

    def convert_type(self, cstruct, dispatcher=None):  # noqa  # parameter to allow forwarding ref for override schemas
        # type: (OpenAPISchema, Optional[TypeConversionDispatcher]) -> OpenAPISchema
        """
        Converts the node to obtain the :term:`JSON` schema definition.
        """
        schema_id = schema_meta = None
        schema_id_include = getattr(self, "_schema_include", False)
        schema_id_include_convert_type = getattr(self, "_schema_include_convert_type", False)
        schema_meta_include = getattr(self, "_schema_meta_include", False)
        schema_meta_include_convert_type = getattr(self, "_schema_meta_include_convert_type", False)
        schema_extra = getattr(self, "_schema_extra", None)
        if schema_id_include and schema_id_include_convert_type:
            schema_id = getattr(self, "_schema", None)
        if schema_meta_include and schema_meta_include_convert_type:
            schema_meta = getattr(self, "_schema_meta", None)
        if schema_id or schema_meta or schema_extra:
            return self._schema_deserialize(cstruct, schema_meta, schema_id, schema_extra)
        return cstruct

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")


class ExtendedSchemaNode(DefaultSchemaNode, DropableSchemaNode, VariableSchemaNode, ExtendedSchemaBase):
    """
    Base schema node with support of extended functionalities.

    Combines all :class:`colander.SchemaNode` extensions so that ``default`` keyword is used first to
    resolve a missing field value during :meth:`deserialize` call, and then removes the node completely
    if no ``default`` was provided, and evaluate variables as needed.

    .. seealso::
        - :class:`ExtendedMappingSchema`
        - :class:`ExtendedSequenceSchema`
        - :class:`DefaultSchemaNode`
        - :class:`DropableSchemaNode`
        - :class:`VariableSchemaNode`
    """
    _extension = "_ext_combined"
    _ext_first = [
        DropableSchemaNode,
        DefaultSchemaNode,
        VariableSchemaNode,
    ]  # type: Iterable[Type[ExtendedNodeInterface]]
    _ext_after = [
        SchemaRefMappingSchema,
        SortableMappingSchema,
    ]  # type: Iterable[Type[ExtendedNodeInterface]]

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def _deserialize_extensions(self, cstruct, extensions):
        # type: (DataT, Iterable[Type[ExtendedNodeInterface]]) -> DataT
        result = cstruct
        # process extensions to infer alternative parameter/property values
        # node extensions order is important as they can impact the following ones
        for node in extensions:  # type: Type[ExtendedNodeInterface]
            # important not to break if result is 'colander.null' since Dropable and Default
            # schema node implementations can substitute it with their appropriate value
            if result is colander.drop:
                # if result is to drop though, we are sure that nothing else must be done
                break
            result = node._deserialize_impl(self, result)
        return result

    def deserialize(self, cstruct):
        # type: (DataT) -> DataT
        schema_type = _get_schema_type(self)
        result = ExtendedSchemaNode._deserialize_extensions(self, cstruct, ExtendedSchemaNode._ext_first)

        try:
            # process usual base operation with extended result
            if result not in (colander.drop, colander.null):
                # when processing mapping/sequence, if the result is an empty container, return the default instead
                # this is to avoid returning many empty containers in case upper level keywords (oneOf, anyOf, etc.)
                # need to discriminate between them
                # empty container means that none of the sub-schemas/fields where matched against input structure
                if isinstance(schema_type, colander.Mapping):
                    # skip already preprocessed variable mapping from above VariableSchemaNode deserialize
                    # otherwise, following 'normal' schema deserialize could convert valid structure into null
                    if self.has_variables():
                        return result
                    result = colander.MappingSchema.deserialize(self, result)
                elif isinstance(schema_type, colander.Sequence):
                    result = colander.SequenceSchema.deserialize(self, result)
                else:
                    # special cases for JSON conversion and string dump, serialize parsable string timestamps
                    #   deserialize causes Date/DateTime/Time to become Python datetime, and result raises if not string
                    #   employ serialize instead which provides the desired conversion from datetime objects to string
                    if isinstance(schema_type, (colander.Date, colander.DateTime, colander.Time)):
                        if not isinstance(result, str):
                            result = colander.SchemaNode.serialize(self, result)
                    else:
                        result = colander.SchemaNode.deserialize(self, result)
                result = self.default if result is colander.null else result
        except colander.Invalid:
            # if children schema raised invalid but parent specifically requested
            # to be dropped by default and is not required, silently discard the whole structure
            if self.default is colander.drop:
                return colander.drop
            raise

        if result is colander.null and self.missing is colander.required:
            raise colander.Invalid(node=self, msg=self.missing_msg)

        result = ExtendedSchemaNode._deserialize_extensions(self, result, ExtendedSchemaNode._ext_after)
        return result


class ExpandStringList(colander.SchemaNode):
    """
    Utility that will automatically deserialize a string to its list representation using the validator delimiter.

    .. seealso::
        - :class:`CommaSeparated`
        - :class:`StringOneOf`

    In order to use this utility, it is important to place it first in the schema node class definition.

    .. code-block::

        class NewNodeSchema(ExpandStringList, ExtendedSchemaNode):
            schema_type = String
            validator = CommaSeparated()
    """
    DEFAULT_DELIMITER = ","

    @staticmethod
    @abstractmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def deserialize(self, cstruct):  # pylint: disable=W0222,signature-differs
        # type: (DataT) -> DataT
        result = super(ExpandStringList, self).deserialize(cstruct)
        if not isinstance(result, str) and result:
            return result
        validator = getattr(self, "validator", None)
        if not validator:
            return result
        delimiter = getattr(validator, "delimiter", self.DEFAULT_DELIMITER)
        result = list(filter(lambda _res: bool(_res), result.split(delimiter)))
        return result


class DropableSequenceSchema(DropableSchemaNode, colander.SequenceSchema):
    """
    Sequence schema that supports the dropable functionality.

    Extends :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
    when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.
    """
    schema_type = colander.SequenceSchema.schema_type


class DefaultSequenceSchema(DefaultSchemaNode, colander.SequenceSchema):
    """
    Sequence schema that supports the default value functionality.

    Extends :class:`colander.SequenceSchema` to auto-handle replacing the result using the provided
    ``default`` value when the deserialization results into a sequence that should normally be dropped.
    """
    schema_type = colander.SequenceSchema.schema_type


class ExtendedSequenceSchema(DefaultSchemaNode, DropableSchemaNode, colander.SequenceSchema):
    """
    Sequence schema that supports all applicable extended schema node functionalities.

    Combines :class:`DefaultSequenceSchema` and :class:`DefaultSequenceSchema` extensions
    so that ``default`` keyword is used first to resolve a missing sequence during :meth:`deserialize`
    call, and then removes the node completely if no ``default`` was provided.

    .. seealso::
        - :class:`ExtendedSchemaNode`
        - :class:`ExtendedMappingSchema`
    """
    schema_type = colander.SequenceSchema.schema_type

    def __init__(self, *args, **kwargs):
        super(ExtendedSequenceSchema, self).__init__(*args, **kwargs)
        self._validate()

    def _validate(self):  # pylint: disable=arguments-differ,arguments-renamed
        ExtendedSchemaBase._validate(self.children[0])


class DropableMappingSchema(DropableSchemaNode, SortableMappingSchema, colander.MappingSchema):
    """
    Mapping schema that supports the dropable functionality.

    Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
    when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.
    """
    schema_type = colander.MappingSchema.schema_type


class DefaultMappingSchema(DefaultSchemaNode, SortableMappingSchema, colander.MappingSchema):
    """
    Mapping schema that supports the default value functionality.

    Override the default :class:`colander.MappingSchema` to auto-handle replacing missing entries by
    their specified ``default`` during deserialization.
    """
    schema_type = colander.MappingSchema.schema_type


class VariableMappingSchema(VariableSchemaNode, colander.MappingSchema):
    """
    Mapping schema that supports the variable functionality.

    Override the default :class:`colander.MappingSchema` to auto-handle replacing missing entries by
    their specified ``variable`` during deserialization.
    """
    schema_type = colander.MappingSchema.schema_type


class ExtendedMappingSchema(
    DefaultSchemaNode,
    DropableSchemaNode,
    VariableSchemaNode,
    SchemaRefMappingSchema,
    SortableMappingSchema,
    colander.MappingSchema,
):
    """
    Combines multiple extensions of :class:`colander.MappingSchema` handle their corresponding keywords.

    Resolution is done so that ``default`` keyword is used first to resolve a missing object
    during :meth:`deserialize` call, and then removes the node completely if no ``default`` was provided.

    .. seealso::
        - :class:`DefaultSchemaNode`
        - :class:`DropableSchemaNode`
        - :class:`VariableSchemaNode`
        - :class:`ExtendedSchemaNode`
        - :class:`ExtendedSequenceSchema`
        - :class:`SchemaRefMappingSchema`
        - :class:`SortableMappingSchema`
        - :class:`PermissiveMappingSchema`
    """
    schema_type = colander.MappingSchema.schema_type

    def __init__(self, *args, **kwargs):
        super(ExtendedMappingSchema, self).__init__(*args, **kwargs)
        self._validate_nodes()
        unknown = getattr(self, "unknown", None)
        if unknown and isinstance(unknown, str):
            self.typ.unknown = unknown

    def _validate_nodes(self):
        for node in self.children:
            ExtendedSchemaBase._validate(node)


class StrictMappingSchema(ExtendedMappingSchema):
    """
    Object schema that will ``raise`` any unknown field not represented by children schema.

    This is equivalent to `OpenAPI` object mapping with ``additionalProperties: false``.
    This type is useful for defining a dictionary that matches *exactly* a specific set of values and children schema.

    ..note::
        When doing schema deserialization to validate it, unknown keys would normally be removed without this class
        (default behaviour is to ``ignore`` them). With this schema, content under an unknown key is fails validation.

    .. seealso::
        :class:`PermissiveMappingSchema`
    """

    def __init__(self, *args, **kwargs):
        kwargs["unknown"] = "raise"
        super(StrictMappingSchema, self).__init__(*args, **kwargs)


class EmptyMappingSchema(StrictMappingSchema):
    """
    Mapping that guarantees it is completely empty for validation during deserialization.

    Any children added to this schema are removed automatically.
    """

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super(EmptyMappingSchema, self).__init__(*args, **kwargs)
        self.children = []


class PermissiveMappingSchema(ExtendedMappingSchema):
    """
    Object schema that will ``preserve`` any unknown field to remain present in the resulting deserialization.

    This type is useful for defining a dictionary where some field names are not known in advance, or
    when more optional keys that don't need to all be exhaustively provided in the schema are acceptable.

    ..note::
        When doing schema deserialization to validate it, unknown keys would normally be removed without this class
        (default behaviour is to ``ignore`` them). With this schema, content under an unknown key using ``preserve``
        are passed down without any validation. Other fields that are explicitly specified with sub-schema nodes
        will still be validated as per usual behaviour.

    .. seealso::
        :class:`StrictMappingSchema`

    Example::

        class AnyKeyObject(PermissiveMappingSchema):
            known_key = SchemaNode(String())

        AnyKeyObject().deserialize({"unknown": "kept", "known_key": "requirement"}))
        # result: dictionary returned as is instead of removing 'unknown' entry
        #         'known_key' is still validated with its string schema

    .. note::
        This class is only a shorthand definition of ``unknown`` keyword for convenience.
        All :class:`colander.MappingSchema` support this natively.
    """

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        kwargs["unknown"] = "preserve"
        super(PermissiveMappingSchema, self).__init__(*args, **kwargs)


class PermissiveSequenceSchema(ExtendedSequenceSchema):
    """
    Array schema that allows *any* item type.

    This is equivalent to the any of the following :term:`JSON` schema definitions.

    .. code-block:: json

        {
            "type": "array",
            "items": {}
        }

    .. code-block:: json

        {
            "type": "array",
            "items": true
        }

    .. code-block:: json

        {
            "type": "array"
        }
    """
    item = ExtendedSchemaNode(AnyType(), default=colander.null, missing=colander.null)


class KeywordMapper(ExtendedMappingSchema):
    """
    Generic keyword mapper for any sub-implementers.

    Allows specifying multiple combinations of schemas variants for an underlying schema definition.
    Each implementer must provide the corresponding ``keyword`` it defines amongst `OpenAPI` specification keywords.
    """
    schema_type = colander.MappingSchema.schema_type
    _keyword_schemas_only_object = False    # override validation as needed
    _keyword_schemas_same_struct = False    # override validation as needed
    _keywords = frozenset(["_one_of", "_all_of", "_any_of", "_not"])
    _keyword_map = {_kw: _kw.replace("_of", "Of").replace("_", "") for _kw in _keywords}  # kw->name
    _keyword_inv = {_kn: _kw for _kw, _kn in _keyword_map.items()}                        # name->kw
    _keyword = None  # type: str
    keywords = frozenset(_keyword_map.values())

    def __init__(self, *args, **kwargs):
        super(KeywordMapper, self).__init__(*args, **kwargs)
        if not hasattr(self, self._keyword):
            # try retrieving from a kwarg definition (either as literal keyword or OpenAPI name)
            if kwargs:
                maybe_kwargs = [_kw for _kw in kwargs if _kw in self._keyword_map or _kw in self._keyword_inv]
                if len(maybe_kwargs) == 1:
                    self._keyword = self._keyword_inv.get(maybe_kwargs[0], maybe_kwargs[0])
                    setattr(self, self._keyword, kwargs.get(maybe_kwargs[0]))
            if not self._keyword:
                raise SchemaNodeTypeError(f"Type '{self}' must define a keyword element.")
        self._validate_keyword_unique()
        self._validate_keyword_schemas()

    @classmethod
    def get_keyword_name(cls):
        return cls._keyword_map[cls._keyword]

    def get_keyword_items(self):
        return getattr(self, self._keyword, [])

    def _validate_keyword_unique(self):
        kw_items = self.get_keyword_items()
        if not hasattr(kw_items, "__iter__") or not len(kw_items):  # noqa
            raise ConversionValueError(
                "Element '{}' of '{!s}' must be iterable with at least 1 value. "
                "Instead it was '{!s}'".format(self._keyword, _get_node_name(self, schema_name=True), kw_items)
            )
        total = 0
        for kw in self._keywords:
            if hasattr(self, kw):
                total += 1
            if total > 1:
                raise SchemaNodeTypeError(f"Multiple keywords '{list(self._keywords)}' not permitted for '{self!s}'")
        if not total == 1:
            raise SchemaNodeTypeError(f"Missing one of keywords '{list(self._keywords)}' for '{self!s}'")

    def _validate_keyword_schemas(self):
        """
        Validation of children schemas under keyword.

        Validation of keyword sub-nodes to be only defined as schema *objects* if property
        ``_keyword_schemas_only_object = True`` (i.e.: any node that defines its schema type as :class:`Mapping`).

        Validation of keyword sub-nodes to all have matching structure of container if
        ``_keyword_schemas_same_struct = True`` (i.e.: all :class:`colander.Mapping`, all literal schema-types, etc.).
        """
        children = self.get_keyword_items()
        keyword = self.get_keyword_name()
        schema_name = _get_node_name(self, schema_name=True)
        if getattr(self, "_keyword_schemas_only_object", False):
            for child in children:
                if child.schema_type is not colander.Mapping:
                    raise SchemaNodeTypeError(
                        "Keyword schema '{}' of type '{}' can only have object children, "
                        "but '{}' is '{}'.".format(schema_name, keyword, type(child), child.schema_type)
                    )
        if getattr(self, "_keyword_schemas_same_struct", False):
            node_types = {child.name: _get_schema_type(child) for child in children}
            if not (
                all(isinstance(typ, colander.Mapping) for _, typ in node_types.items())
                or all(isinstance(typ, colander.Sequence) for _, typ in node_types.items())
                or all(isinstance(typ, tuple(LITERAL_SCHEMA_TYPES)) for _, typ in node_types.items())
            ):
                raise SchemaNodeTypeError(
                    "Keyword schema '{}' of type '{}' can only have children of same schemas-type structure, "
                    "but different ones were found '{}'.".format(schema_name, keyword, node_types)
                )

        ExtendedMappingSchema._validate_nodes(self)
        for node in children:
            ExtendedSchemaBase._validate(node)

    def _bind(self, kw):
        # type: (Dict[str, Any]) -> None
        """
        Applies the bindings to the children nodes.

        Based on :meth:`colander._SchemaNode._bind` except that `children` are obtained from the keyword.
        """
        self.bindings = kw  # pylint: disable=W0201  # false-positive - property exists in colander SchemaNode meta-type
        children = self.get_keyword_items()
        for idx, child in enumerate(list(children)):
            if hasattr(child, "_bind"):
                child._bind(kw)
            elif isinstance(child, colander.deferred):
                v = child(self, kw)
                if isinstance(v, colander.SchemaNode):
                    children[idx] = v
        names = dir(self)
        for k in names:
            v = getattr(self, k)
            if isinstance(v, colander.deferred):
                v = v(self, kw)
                setattr(self, k, v)
        if getattr(self, "after_bind", None):
            self.after_bind(self, kw)  # pylint: disable=E1102  # defined as colander SchemaNode attribute in meta-type

    @abstractmethod
    def _deserialize_keyword(self, cstruct):
        """
        Deserialization and validation of a keyword-based schema definition.

        This method must be implemented by the specific keyword to handle
        invalid subnodes according to the behaviour it offers.

        .. seealso::
            - :meth:`_deserialize_subnode`
        """
        raise NotImplementedError

    def _deserialize_subnode(self, node, cstruct, index):
        """
        Deserialization and validation of sub-nodes under a keyword-based schema definition.

        This method must be called by keyword deserialization implementers
        for deserialization of every sub-node in order to apply extended behaviour
        operations accordingly. The original ``deserialize`` method of
        :mod:`colander` schema nodes should not be called directly, otherwise
        extensions will not be handled. This method will call it after resolving
        any applicable extension.

        .. note::
            Because sub-nodes are within a non-schema node iterable, the SchemaMeta will
            not have extracted the destination name for us (ie: map key to compare against).
            Furthermore, the destination is not directly in the KeywordMapper class, but
            in its parent where its instance will be dumped according to the keyword resolution.
            Therefore, regardless of the child, they all have the same parent destination.

        .. seealso::
            - :meth:`_deserialize_keyword`
            - :class:`ExtendedSchemaNode`
        """
        if not node.name:
            node.name = _get_node_name(node, schema_name=True) or str(index)
        if isinstance(node, KeywordMapper):
            return KeywordMapper.deserialize(node, cstruct)

        # call the specific method defined by the schema if overridden
        # this is to allow the nested schema under the keyword to apply additional logic
        # it is up to that schema to do the 'super().deserialize()' call to run the usual logic
        deserialize_override = getattr(type(node), "deserialize", None)
        if deserialize_override not in [
            ExtendedMappingSchema.deserialize,
            ExtendedSequenceSchema.deserialize,
            ExtendedSchemaNode.deserialize,
        ]:
            return deserialize_override(node, cstruct)
        return ExtendedSchemaNode.deserialize(node, cstruct)

    def deserialize(self, cstruct):  # pylint: disable=W0222,signature-differs
        if cstruct is colander.null:
            if self.required and not VariableSchemaNode.is_variable(self):
                raise colander.Invalid(self, "Missing required field.")
            # keyword schema has additional members other than nested in keyword, mapping is required
            # process any deserialization as mapping schema
            if self.children:
                return ExtendedSchemaNode.deserialize(self, colander.null)
            # otherwise, only null/drop/default are to be processed
            # since nested keyword schemas are not necessarily mappings, deserialize only extended features
            # using 'ExtendedSchemaNode.deserialize' would raise "not a mapping" if nested schemas is something else
            cstruct = ExtendedSchemaNode._deserialize_extensions(self, cstruct, ExtendedSchemaNode._ext_first)
            cstruct = ExtendedSchemaNode._deserialize_extensions(self, cstruct, ExtendedSchemaNode._ext_after)
            return cstruct

        # first process the keyword subnodes
        result = self._deserialize_keyword(cstruct)
        # if further fields where explicitly added next to the keyword schemas,
        # validate and apply them as well
        if isinstance(result, dict) and self.children:
            mapping_data = super(KeywordMapper, self).deserialize(cstruct)
            result.update(mapping_data)
        result = SortableMappingSchema._deserialize_impl(self, result)
        return result


class OneOfKeywordSchema(KeywordMapper):
    """
    Allows specifying multiple supported mapping schemas variants for an underlying schema definition.

    Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

    Example::

        class Variant1(MappingSchema):
            [...fields of Variant1...]

        class Variant2(MappingSchema):
            [...fields of Variant2...]

        class RequiredByBoth(MappingSchema):
            [...fields required by both Variant1 and Variant2...]

        class OneOfWithRequiredFields(OneOfKeywordSchema, RequiredByBoth):
            _one_of = (Variant1, Variant2)
            [...alternatively, field required by all variants here...]

    In the above example, the validation (ie: ``deserialize``) process will succeed if only one of
    the ``_one_of`` variants' validator completely succeed, and will fail if every variant fails
    validation execution. The operation will also fail if more than one validation succeeds.

    .. note::
        Class ``OneOfWithRequiredFields`` in the example is a shortcut variant to generate a
        specification that represents the pseudo-code ``oneOf([<list-of-objects-with-same-base>])``.

    The real OpenAPI method to implement the above very commonly occurring situation is as
    presented by the following pseudo-code::

        oneOf[allOf[RequiredByBoth, Variant1], allOf[RequiredByBoth, Variant2]]

    This is both painful to read and is a lot of extra code to write when you actually expand it
    all into classes (each ``oneOf/allOf`` is another class). Class :class:`OneOfKeywordSchema`
    will actually simplify this by automatically making the ``allOf`` definitions for you if it
    detects other schema nodes than ``oneOf`` specified in the class bases. You can still do the full
    ``oneOf/allOf`` classes expansion manually though, it will result into the same specification.

    .. warning::
        When ``oneOf/allOf`` automatic expansion occurs during schema generation

    .. warning::
        When calling :meth:`deserialize`, because the validation process requires **exactly one**
        of the variants to succeed to consider the whole object to evaluate as valid, it is
        important to insert *more permissive* validators later in the ``_one_of`` iterator (or
        ``validator`` keyword). For example, having a variant with all fields defined as optional
        (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
        succeed regardless of following variants (since an empty schema with everything dropped is
        valid for optional-only elements). This would have as side effect of potentially failing
        the validation if other object are also valid depending on the received schema because
        the schema cannot be discriminated between many. If this occurs, it means the your schemas
        are too permissive.

    In the event that you have very similar schemas that can sometime match except one identifier
    (e.g.: field ``type`` defining the type of object), consider adding a ``validator`` to each sub-node
    with explicit values to solve the discrimination problem.

    As a shortcut, the OpenAPI keyword ``discriminator`` can be provided to try matching as a last resort.

    For example:

    .. code-block:: python

        class Animal(ExtendedMappingSchema):
            name = ExtendedSchemaNode(String())
            type = ExtendedSchemaNode(String())  # with explicit definition, this shouldn't be here

            ## With explicit definitions, each below 'Animal' class should be defined as follows
            ## type = ExtendedSchemaNode(String(), validator=colander.OneOf(['<animal>']))

        class Cat(Animal):
            [...]   # many **OPTIONAL** fields

        class Dog(Animal):
            [...]   # many **OPTIONAL** fields

        # With the discriminator keyword, following is possible
        # (each schema must provide the same property name)
        class SomeAnimal(OneOfMappingSchema):
            discriminator = "type"
            _one_of = [
                Cat(),
                Dog(),
            ]

        # If more specific mapping resolutions than 1-to-1 by name are needed,
        # an explicit dictionary can be specified instead.
        class SomeAnimal(OneOfMappingSchema):
            discriminator = {
                "propertyName": "type",     # correspond to 'type' of 'Animal'
                "mapping": {
                    "cat": Cat, "dog": Dog  # map expected values to target schemas
                }
            }
            _one_of = [
                Cat(),
                Dog(),
            ]

    .. note::
        Keyword ``discriminator`` supports a map of key-string to schemas-type as presented
        in the example, and the key must be located at the top level of the mapping.
        If only ``discriminator = "<field>"`` is provided, the definition will be created
        automatically using the ``example`` (which should be only the matching value) of the
        corresponding field of each node within the ``_one_of`` mapping.

    When multiple valid schemas are matched against the input data, the error will be
    raised and returned with corresponding erroneous elements for each sub-schema (fully listed).

    .. seealso::
        - :class:`AllOfKeywordSchema`
        - :class:`AnyOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword_schemas_only_object = False
    _keyword = "_one_of"
    _discriminator = "discriminator"
    discriminator = None

    @classmethod
    @abstractmethod
    def _one_of(cls):
        # type: () -> Iterable[Union[colander.SchemaNode, Type[colander.SchemaNode]]]  # noqa: W0212
        """
        Sequence of applicable schema nested under the ``oneOf`` keyword.

        Must be overridden in the schema definition using it.
        """
        raise SchemaNodeTypeError(f"Missing '{cls._keyword}' keyword for schema '{cls}'.")

    def __init__(self, *args, **kwargs):
        discriminator = getattr(self, self._discriminator, None)
        discriminator = kwargs.pop(self._discriminator, discriminator)
        super(OneOfKeywordSchema, self).__init__(*args, **kwargs)
        discriminator_spec = None
        if discriminator:
            schema_name = _get_node_name(self, schema_name=True)
            keyword = self.get_keyword_name()
            discriminator_spec = discriminator
            if isinstance(discriminator, str):
                discriminator_spec = {"propertyName": discriminator}
            if isinstance(discriminator_spec, dict) and "mapping" not in discriminator_spec:
                mapping = {}
                for node in self.get_keyword_items():
                    node_fields = [
                        field for field in node.children
                        if field.name == discriminator_spec["propertyName"]
                    ]
                    if len(node_fields) != 1:
                        continue
                    example = getattr(node_fields[0], "example", colander.null)
                    values = getattr(node_fields[0], "validator", StringOneOf([colander.null]))
                    discriminator_value = colander.null
                    if example is not colander.null:
                        discriminator_value = example
                    elif (
                        isinstance(values, colander.OneOf)
                        and len(values.choices) == 1
                        and isinstance(values.choices[0], str)
                    ):
                        discriminator_value = values.choices[0]
                    if not discriminator_value:
                        raise SchemaNodeTypeError(
                            "Keyword schema '{}' of type '{}' specification with 'discriminator' "
                            "could not resolve any value defining the discriminator for nested "
                            "field '{}' in schema '{}'.".format(
                                schema_name, keyword,
                                discriminator_spec["propertyName"],
                                _get_node_name(node_fields[0], schema_name=True),
                            )
                        )
                    if discriminator_value in mapping:
                        raise SchemaNodeTypeError(
                            "Keyword schema '{}' of type '{}' specification with 'discriminator' attempts "
                            "to refer to duplicate example values '{}' between '{}' and '{}'".format(
                                schema_name, keyword, discriminator_value,
                                _get_node_name(mapping[discriminator_value], schema_name=True),
                                _get_node_name(node, schema_name=True),
                            )
                        )
                    mapping[discriminator_value] = node
                discriminator_spec["mapping"] = mapping
            if not (
                isinstance(discriminator_spec, dict)
                and all(prop in discriminator_spec for prop in ["propertyName", "mapping"])
                and isinstance(discriminator_spec["propertyName"], str)
                and isinstance(discriminator_spec["mapping"], dict)
                and len(discriminator_spec["mapping"])
                and all(isinstance(node, colander.SchemaNode) and node.schema_type is colander.Mapping
                        for name, node in discriminator_spec["mapping"].items())
            ):
                raise SchemaNodeTypeError(
                    "Keyword schema '{}' of type '{}' specification with 'discriminator' must be a string "
                    "or dictionary with 'propertyName' and 'mapping' of target value to schema nodes, "
                    "but was specified as '{!s}".format(schema_name, keyword, discriminator))
        setattr(self, self._discriminator, discriminator_spec)

    @property
    def discriminator_spec(self):
        return getattr(self, self._discriminator, None)

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return all corresponding errors if not exactly one of the possibilities is valid.
        """
        invalid_one_of = {}  # type: Dict[str, colander.Invalid]
        valid_one_of = []
        valid_nodes = []
        for index, schema_class in enumerate(self._one_of):  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                result = self._deserialize_subnode(schema_class, cstruct, index)
                if result is colander.drop:
                    continue
                valid_one_of.append(result)
                valid_nodes.append(schema_class)
            except colander.Invalid as invalid:
                invalid_node_name = _get_node_name(invalid.node, schema_name=True)
                invalid_one_of.update({invalid_node_name: invalid})
        message = f"Incorrect type must be one of: {list(invalid_one_of)}."
        if valid_one_of:
            # if found only one, return it, otherwise try to discriminate
            if len(valid_one_of) == 1:
                return valid_one_of[0]
            message = (
                "Incorrect type cannot distinguish between multiple valid schemas. "
                "Must be only one of: {}.".format([_get_node_name(node, schema_name=True) for node in valid_nodes])
            )

            discriminator = self.discriminator_spec
            if discriminator:
                # try last resort solve
                valid_discriminated = []
                error_discriminated = {}
                for i, obj in enumerate(valid_one_of):
                    node = valid_nodes[i]
                    node_name = _get_node_name(node)
                    node_field = [child for child in node.children if child.name == discriminator["propertyName"]]
                    if len(node_field) == 1:
                        error_discriminated.update({node_name: obj})
                        node_value = node_field[0].example
                        node_discriminated = discriminator["mapping"].get(node_value)
                        if node_discriminated and isinstance(obj, type(node_discriminated)):
                            valid_discriminated.append(obj)
                if len(valid_discriminated) == 1:
                    return valid_discriminated[0]
                elif len(valid_discriminated) > 1:
                    invalid_one_of = error_discriminated
                message = (
                    "Incorrect type cannot discriminate between multiple valid schemas. "
                    "Must be only one of: {}.".format(list(invalid_one_of))
                )
                raise colander.Invalid(node=self, msg=message, value=discriminator)

            # because some schema nodes will convert types during deserialize without error,
            # attempt to discriminate base-type values compared with tested value
            # (e.g.: discriminate between float vs numerical string allowed schema variations)
            if not isinstance(cstruct, (dict, set, list, tuple)):
                # pylint: disable=C0123
                valid_values = list(filter(
                    lambda c: c == cstruct and type(c) == type(cstruct),  # noqa: E721
                    valid_one_of
                ))
                if len(valid_values) == 1:
                    return valid_values[0]
                message = (
                    "Incorrect type cannot differentiate between multiple base-type valid schemas. "
                    "Must be only one of: {}.".format(valid_values)
                )

        # not a single valid sub-node was found
        if self.missing is colander.drop:
            return colander.drop
        if self.missing is None and cstruct in [None, colander.null]:
            return None

        # add the invalid sub-errors to the parent oneOf for reporting each error case individually
        invalid = colander.Invalid(node=self, msg=message, value=cstruct)
        for inv in invalid_one_of.values():
            invalid.add(inv)
        raise invalid


class AllOfKeywordSchema(KeywordMapper):
    """
    Allows specifying all the required partial mapping schemas for an underlying complete schema definition.

    Corresponds to the ``allOf`` specifier of `OpenAPI` specification.

    Example::

        class RequiredItem(ExtendedMappingSchema):
            item = ExtendedSchemaNode(String())

        class RequiredType(ExtendedMappingSchema):
            type = ExtendedSchemaNode(String())

        class AllRequired(AnyKeywordSchema):
            _all_of = [RequiredItem(), RequiredType()]


    Value parsed with schema this definition will be valid only when every since one of the sub-schemas is valid.
    Any sub-schema raising an invalid error for any reason with make the whole schema validation fail.

    .. seealso::
        - :class:`OneOfKeywordSchema`
        - :class:`AnyOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword_schemas_only_object = True
    _keyword_schemas_same_struct = True
    _keyword = "_all_of"

    @classmethod
    @abstractmethod
    def _all_of(cls):
        # type: () -> Iterable[Union[colander.SchemaNode, Type[colander.SchemaNode]]]  # noqa: W0212
        """
        Sequence of applicable schema nested under the ``allOf`` keyword.

        Must be overridden in the schema definition using it.
        """
        raise SchemaNodeTypeError(f"Missing '{cls._keyword}' keyword for schema '{cls}'.")

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return all corresponding errors if any of the possibilities is invalid.
        """
        required_all_of = {}
        missing_all_of = {}
        merged_all_of = {}
        for index, schema_class in enumerate(self._all_of):  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                required_all_of.update({_get_node_name(schema_class, schema_name=True): str(schema_class)})
                result = self._deserialize_subnode(schema_class, cstruct, index)
                if result is colander.drop:
                    if schema_class.missing is colander.drop:
                        continue
                    if isinstance(schema_class.default, dict):
                        result = schema_class.default
                    else:
                        raise colander.Invalid(node=schema_class, msg="Schema is missing when required.", value=result)
                merged_all_of.update(result)
            except colander.Invalid as invalid:
                missing_all_of.update({_get_node_name(invalid.node, schema_name=True): str(invalid)})

        if missing_all_of:
            # if anything failed, the whole definition is invalid in this case
            message = (
                "Incorrect type must represent all of: {}. Missing following cases: {}"
                .format(list(required_all_of), list(missing_all_of))
            )
            raise colander.Invalid(node=self, msg=message)

        return merged_all_of


class AnyOfKeywordSchema(KeywordMapper):
    """
    Allows specifying all mapping schemas that can be matched for an underlying schema definition.

    Corresponds to the ``anyOf`` specifier of `OpenAPI` specification.

    Contrary to :class:`OneOfKeywordSchema` that MUST be validated with exactly one schema, this
    definition will continue parsing all possibilities and apply validated sub-schemas on top
    of each other. Not all schemas have to be valid like in the case of :class:`AllOfKeywordSchema`
    to succeed, as long as at least one of them is valid.

    Example::

        class RequiredItem(ExtendedMappingSchema):
            item = ExtendedSchemaNode(String())

        class RequiredType(ExtendedMappingSchema):
            type = ExtendedSchemaNode(String())

        class RequiredFields(ExtendedMappingSchema):
            field_str = ExtendedSchemaNode(String())
            field_int = ExtendedSchemaNode(Integer())

        class AnyRequired(AnyKeywordSchema):
            _any_of = [RequiredItem(), RequiredType(), RequiredFields()]

        # following is valid because their individual parts have all required sub-fields, result is their composition
        AnyRequired().deserialize({"type": "test", "item": "valid"})     # result: {"type": "test", "item": "valid"}

        # following is also valid because even though 'item' is missing, the 'type' is present
        AnyRequired().deserialize({"type": "test"})                      # result: {"type": "test"}

        # following is invalid because every one of the sub-field of individual parts are missing
        AnyRequired().deserialize({"type": "test"})

        # following is invalid because fields of 'RequiredFields' are only partially fulfilled
        AnyRequired().deserialize({"field_str": "str"})

        # following is valid because although fields of 'RequiredFields' are not all fulfilled, 'RequiredType' is valid
        AnyRequired().deserialize({"field_str": "str", "type": "str"})  # result: {"type": "test"}

        # following is invalid because 'RequiredFields' field 'field_int' is incorrect schema type
        AnyRequired().deserialize({"field_str": "str", "field_int": "str"})

        # following is valid, but result omits 'type' because its schema-type is incorrect, while others are valid
        AnyRequired().deserialize({"field_str": "str", "field_int": 1, "items": "fields", "type": 1})
        # result: {"field_str": "str", "field_int": 1, "items": "fields"}

    .. warning::
        Because valid items are applied on top of each other by merging fields during combinations,
        conflicting field names of any valid schema will contain only the final valid parsing during deserialization.

    .. seealso::
        - :class:`OneOfKeywordSchema`
        - :class:`AllOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword_schemas_only_object = False
    _keyword_schemas_same_struct = False
    _keyword = "_any_of"

    @classmethod
    @abstractmethod
    def _any_of(cls):
        # type: () -> Iterable[Union[colander.SchemaNode, Type[colander.SchemaNode]]]  # noqa: W0212
        """
        Sequence of applicable schema nested under the ``anyOf`` keyword.

        Must be overridden in the schema definition using it.
        """
        raise SchemaNodeTypeError(f"Missing '{cls._keyword}' keyword for schema '{cls}'.")

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return if no corresponding schema was found.
        """
        option_any_of = {}
        merged_any_of = colander.null
        invalid_any_of = colander.Invalid(node=self, value=cstruct)
        for index, schema_class in enumerate(self._any_of):  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                option_any_of.update({_get_node_name(schema_class, schema_name=True): str(schema_class)})
                result = self._deserialize_subnode(schema_class, cstruct, index)
                if result not in (colander.drop, colander.null):
                    # technically not supposed to have 'Sequence' type since they can only have one child
                    # only possibility is all similar objects or all literals because of '_keyword_schemas_same_struct'
                    if schema_class.schema_type is colander.Mapping:
                        if merged_any_of is colander.null:
                            merged_any_of = {}
                        merged_any_of.update(result)
                    else:
                        # schema nodes override one another if valid for multiple schemas
                        merged_any_of = result
            except colander.Invalid as invalid:
                invalid_any_of.add(invalid)

        # if nothing could be resolved, verify for a default value
        if merged_any_of is colander.null:
            merged_any_of = self.default

        # nothing succeeded, the whole definition is invalid in this case
        if merged_any_of is colander.null and self.missing is colander.required:
            invalid_any_of.msg = (
                f"Incorrect type must represent any of: {list(option_any_of)}. "
                f"All missing from input data."
            )
            raise invalid_any_of
        if merged_any_of is colander.null:
            return self.missing
        return merged_any_of


class NotKeywordSchema(KeywordMapper):
    """
    Allows specifying specific schema conditions that fails underlying schema definition validation if present.

    Corresponds to the ``not`` specifier of `OpenAPI` specification.

    Example::

        class RequiredItem(ExtendedMappingSchema):
            item = ExtendedSchemaNode(String())

        class MappingWithType(ExtendedMappingSchema):
            type = ExtendedSchemaNode(String())

        class MappingWithoutType(NotKeywordSchema, RequiredItem):
            _not = [MappingWithType()]

        class MappingOnlyNotType(NotKeywordSchema):
            _not = [MappingWithType()]

        # following will raise invalid error even if 'item' is valid because 'type' is also present
        MappingWithoutType().deserialize({"type": "invalid", "item": "valid"})

        # following will return successfully with only 'item' because 'type' was not present
        MappingWithoutType().deserialize({"item": "valid", "value": "ignore"})
        # result: {"item": "valid"}

        # following will return an empty mapping dropping 'item' since it only needs to ensure 'type' was not present,
        # but did not provide any additional fields requirement from other class inheritances
        MappingOnlyNotType().deserialize({"item": "valid"})
        # result: {}

    .. seealso::
        - :class:`OneOfKeywordSchema`
        - :class:`AllOfKeywordSchema`
        - :class:`AnyOfKeywordSchema`
    """
    _keyword_schemas_only_object = True
    _keyword_schemas_same_struct = True
    _keyword = "_not"

    @classmethod
    @abstractmethod
    def _not(cls):
        # type: () -> Iterable[Union[colander.SchemaNode, Type[colander.SchemaNode]]]  # noqa: W0212
        """
        Sequence of applicable schema nested under the ``not`` keyword.

        Must be overridden in the schema definition using it.
        """
        raise SchemaNodeTypeError(f"Missing '{cls._keyword}' keyword for schema '{cls}'.")

    def _deserialize_keyword(self, cstruct):
        """
        Raise if any sub-node schema that should NOT be present was successfully validated.
        """
        invalid_not = {}
        for index, schema_class in enumerate(self._not):  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                result = self._deserialize_subnode(schema_class, cstruct, index)
                if isinstance(result, dict) and not len(result):
                    continue  # allow empty result meaning every item was missing and dropped
                invalid_names = [node.name for node in schema_class.children]
                invalid_not.update({_get_node_name(schema_class, schema_name=True): invalid_names})
            except colander.Invalid:
                pass  # error raised as intended when missing field is not present
        if invalid_not:
            message = f"Value contains not allowed fields from schema conditions: {invalid_not}"
            raise colander.Invalid(node=self, msg=message, value=cstruct)
        # If schema was a plain NotKeywordSchema, the result will be empty as it serves only to validate
        # that the subnodes are not present. Otherwise, if it derives from other mapping classes, apply them.
        # If deserialization was not applied here, everything in the original cstruct would bubble up.
        return ExtendedMappingSchema.deserialize(self, cstruct)


class SchemaRefConverter(TypeConverter):
    """
    Converter that will add :term:`OpenAPI` ``$schema`` and ``$id`` references if they are provided in the schema node.
    """
    def convert_type(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchema
        result = super(SchemaRefConverter, self).convert_type(schema_node)
        if isinstance(schema_node, SchemaRefMappingSchema):
            # apply any resolved schema references at the top of the definition
            converter = getattr(type(schema_node), "convert_type", SchemaRefMappingSchema.convert_type)
            result_ref = converter(schema_node, {}, dispatcher=self.dispatcher)
            result_ref.update(result)
            result = result_ref
        return result


class ExtendedTypeConverter(SchemaRefConverter):
    """
    Base converter with support of `Extended` schema type definitions.
    """
    def convert_type(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchema
        # base type converters expect raw pattern string
        # undo the compiled pattern to allow conversion
        pattern = getattr(schema_node, "pattern", None)
        if isinstance(pattern, RegexPattern):
            setattr(schema_node, "pattern", pattern.pattern)
        result = super(ExtendedTypeConverter, self).convert_type(schema_node)
        if isinstance(schema_node, SortableMappingSchema) and result.get("type") == "object":
            props = result.get("properties", {})
            if props:
                props = schema_node._order_deserialize(props, schema_node._sort_first, schema_node._sort_after)
                result["properties"] = props
        return result


class KeywordTypeConverter(SchemaRefConverter):
    """
    Generic keyword converter that builds schema with a list of sub-schemas under the keyword.
    """

    def convert_type(self, schema_node):
        keyword = schema_node.get_keyword_name()
        keyword_schema = super(KeywordTypeConverter, self).convert_type(schema_node)  # type: OpenAPISchemaKeyword
        keyword_schema.pop("type", None)
        keyword_schema.update({
            keyword: []
        })

        for item_schema in schema_node.get_keyword_items():
            obj_instance = _make_node_instance(item_schema)
            obj_converted = self.dispatcher(obj_instance)
            keyword_schema[keyword].append(obj_converted)
        return keyword_schema


class OneOfKeywordTypeConverter(KeywordTypeConverter):
    """
    Object converter that generates the ``oneOf`` keyword definition.

    This object does a bit more work than other :class:`KeywordTypeConverter` as it
    handles the shorthand definition as described in :class:`OneOfKeywordSchema`

    .. seealso::
        - :class:`OneOfKeywordSchema`
    """

    def convert_type(self, schema_node):
        # type: (OneOfKeywordSchema) -> OpenAPISchemaOneOf
        keyword = schema_node.get_keyword_name()
        one_of_obj = super(KeywordTypeConverter, self).convert_type(schema_node)
        one_of_obj.pop("type", None)
        one_of_obj.update({
            keyword: []
        })

        for item_schema in schema_node.get_keyword_items():
            item_obj = _make_node_instance(item_schema)
            # shortcut definition of oneOf[allOf[],allOf[]] mix, see OneOfKeywordSchema docstring
            # (eg: schema fields always needed regardless of other fields supplied by each oneOf schema)
            if len(getattr(schema_node, "children", [])):
                if not isinstance(schema_node, colander.MappingSchema):
                    raise ConversionTypeError(
                        f"Unknown base type to convert oneOf schema item is no a mapping: {type(schema_node)}"
                    )
                # specific oneOf sub-item, will be processed by itself during dispatch of sub-item of allOf
                # rewrite the title of that new sub-item schema from the original title to avoid conflict
                schema_title = _get_node_name(schema_node, schema_name=True)
                # generate the new nested definition of keywords using schema node bases and children
                item_title = _get_node_name(item_obj, schema_name=True)
                # NOTE: to avoid potential conflict of schema reference definitions with other existing ones,
                #       use an invalid character that cannot exist in Python class name defining the schema titles
                one_of_title = f"{schema_title}.{item_title}"
                shared_title = f"{schema_title}.Shared"
                obj_req_title = f"{item_title}.AllOf"
                # fields that are shared across all the oneOf sub-items
                # pass down the original title of that object to refer to that schema reference
                obj_shared = ExtendedMappingSchema(title=shared_title)
                obj_shared.children = schema_node.children  # pylint: disable=W0201
                obj_one_of = item_obj.clone()
                obj_one_of.title = one_of_title
                all_of = AllOfKeywordSchema(title=obj_req_title, _all_of=[obj_shared, obj_one_of])
                obj_converted = self.dispatcher(all_of)
            else:
                obj_converted = self.dispatcher(item_obj)
            one_of_obj[keyword].append(obj_converted)
        discriminator = schema_node.discriminator_spec
        if schema_node.discriminator:
            discriminator_spec = {"propertyName": discriminator["propertyName"], "mapping": {}}
            for value, node in discriminator["mapping"].items():
                discriminator_spec["mapping"][value] = node.title
            one_of_obj["discriminator"] = discriminator_spec
        return one_of_obj


class AllOfKeywordTypeConverter(KeywordTypeConverter):
    """
    Object converter that generates the ``allOf`` keyword definition.
    """

    def convert_type(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchemaAllOf
        return super(AllOfKeywordTypeConverter, self).convert_type(schema_node)


class AnyOfKeywordTypeConverter(KeywordTypeConverter):
    """
    Object converter that generates the ``anyOf`` keyword definition.
    """

    def convert_type(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchemaAnyOf
        return super(AnyOfKeywordTypeConverter, self).convert_type(schema_node)


class NotKeywordTypeConverter(KeywordTypeConverter):
    """
    Object converter that generates the ``not`` keyword definition.
    """

    def convert_type(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchemaNot
        result = ExtendedObjectTypeConverter(self.dispatcher).convert_type(schema_node)
        result["additionalProperties"] = False  # type: ignore
        return result


class ExtendedObjectTypeConverter(ExtendedTypeConverter, ObjectTypeConverter):
    """
    Object convert for mapping type with extended capabilities.
    """


class VariableObjectTypeConverter(ExtendedObjectTypeConverter):
    """
    Object convertor with ``additionalProperties`` for each ``properties`` marked as :class:`VariableSchemaNode`.
    """

    def convert_type(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchema
        converted = super(VariableObjectTypeConverter, self).convert_type(schema_node)
        converted.setdefault("additionalProperties", {})
        if self.dispatcher.openapi_spec == 3:
            for sub_node in schema_node.children:
                if VariableSchemaNode.is_variable(sub_node):
                    if isinstance(sub_node, KeywordMapper):
                        # keyword mapping
                        properties = converted["properties"].pop(sub_node.name)
                        keyword = sub_node.get_keyword_name()
                        kw_props = properties.pop(keyword)
                        converted["additionalProperties"].update({keyword: kw_props})
                        for prop in properties:
                            # re-add other fields like title if not already defined in keyword container
                            converted.setdefault(prop, properties[prop])
                    else:
                        # normal mapping
                        converted["additionalProperties"].update(
                            {sub_node.name: converted["properties"].pop(sub_node.name)}
                        )
                    if sub_node.name in converted.get("required", []):
                        converted["required"].remove(sub_node.name)
        return converted


class DecimalTypeConverter(MetadataTypeConverter, NumberTypeConverter):
    format = "decimal"

    def convert_type(self, schema_node):
        result = super(DecimalTypeConverter, self).convert_type(schema_node)
        result.setdefault("format", DecimalTypeConverter.format)
        return result


class MoneyTypeConverter(DecimalTypeConverter):
    convert_validator = ValidatorConversionDispatcher(
        convert_range_validator,
        convert_regex_validator,
        convert_oneof_validator_factory(),
    )


class NoneTypeConverter(ExtendedTypeConverter):
    type = "null"


class AnyTypeConverter(ExtendedTypeConverter):
    def convert_type(self, schema_node):
        converted = super().convert_type(schema_node)
        converted.pop("type", None)
        return converted


# TODO: replace directly in original cornice_swagger
#  (see: https://github.com/Cornices/cornice.ext.swagger/issues/133)
class OAS3TypeConversionDispatcher(TypeConversionDispatcher):
    openapi_spec = 3

    def __init__(self, custom_converters=None, default_converter=None):
        # type: (Optional[Dict[colander.SchemaType, TypeConverter]], Optional[TypeConverter]) -> None
        self.keyword_converters = {
            OneOfKeywordSchema: OneOfKeywordTypeConverter,
            AllOfKeywordSchema: AllOfKeywordTypeConverter,
            AnyOfKeywordSchema: AnyOfKeywordTypeConverter,
            NotKeywordSchema: NotKeywordTypeConverter,
        }
        self.keyword_validators = {
            colander.OneOf: OneOfKeywordSchema,
            colander.Any: AnyOfKeywordSchema,
            colander.All: AllOfKeywordSchema,
            colander.NoneOf: NotKeywordSchema,
        }
        # NOTE: define items to inherit variable/extended functionalities,
        #   when merging in original cornice_swagger, it should be the 'default' behaviour of object converter
        #   user custom converters can override everything, but they must use extended classes to use extra features
        extended_converters = {
            colander.Mapping: VariableObjectTypeConverter,
            colander.Decimal: ExtendedDecimalTypeConverter,
            colander.Money: ExtendedMoneyTypeConverter,
            colander.Float: ExtendedFloatTypeConverter,
            colander.Number: ExtendedNumberTypeConverter,
            colander.Integer: ExtendedIntegerTypeConverter,
            colander.Boolean: ExtendedBooleanTypeConverter,
            colander.DateTime: ExtendedDateTimeTypeConverter,
            colander.Date: ExtendedDateTypeConverter,
            colander.Time: ExtendedTimeTypeConverter,
            colander.String: ExtendedStringTypeConverter,
            NoneType: NoneTypeConverter,
            AnyType: AnyTypeConverter,
        }
        extended_converters.update(self.keyword_converters)
        if custom_converters:
            extended_converters.update(custom_converters)
        super(OAS3TypeConversionDispatcher, self).__init__(extended_converters, default_converter)
        self.extend_converters()

    def extend_converters(self):
        # type: () -> None
        """
        Extend base :class:`TypeConverter` derived classes to provide additional capabilities seamlessly.
        """
        for typ, cvt in self.converters.items():
            if issubclass(cvt, TypeConverter) and not issubclass(cvt, ExtendedTypeConverter):
                class Extended(ExtendedTypeConverter, cvt):
                    __name__ = f"Extended{cvt}"
                self.converters[typ] = Extended

    def __call__(self, schema_node):
        # type: (colander.SchemaNode) -> OpenAPISchema
        schema_type = schema_node.typ
        schema_type = type(schema_type)

        # dispatch direct reference to keyword schemas
        converter_class = None
        for base_class in self.keyword_converters:
            if base_class in inspect.getmro(type(schema_node)):
                converter_class = self.keyword_converters.get(base_class)
                break

        if converter_class is None and self.openapi_spec == 3:
            # dispatch indirect conversions specified by MappingSchema/SequenceSchema
            # using a colander validator as argument matching keyword schemas
            # (eg: MappingSchema(validator=colander.OneOf([Obj1, Obj2])) )
            if isinstance(schema_node, (colander.MappingSchema, colander.SequenceSchema)):
                if isinstance(schema_node.validator, tuple(self.keyword_validators)):
                    keyword_class = self.keyword_validators[type(schema_node.validator)]
                    keyword_items = getattr(schema_node.validator, "choices",
                                            getattr(schema_node.validator, "validators"))
                    keyword_kwargs = {keyword_class.get_keyword_name(): keyword_items}
                    keyword_schema = keyword_class(**keyword_kwargs)
                    converted = self(keyword_schema)  # noqa
                    return converted

        if converter_class is None:
            converter_class = self.converters.get(schema_type)
            if converter_class is None:
                # find derived extended schema type
                if any(issubclass(schema_type, s_type) for s_type in self.converters):
                    for sub_type in inspect.getmro(schema_type)[1:]:
                        converter_class = self.converters.get(sub_type)
                        if converter_class is not None:
                            break
                elif self.default_converter:
                    converter_class = self.default_converter
                else:
                    raise NoSuchConverter(f"schema_type: {schema_type}")

        converter = converter_class(self)
        converted = converter(schema_node)  # noqa

        # TODO: only this part is actually 'custom' for our use
        #   rest on top is to be integrated in original 'cornice_swagger'
        if schema_node.title:
            # ignore the names key use as useful keywords to define location
            if schema_node.name in ["header", "body", "querystring", "path"]:
                converted["title"] = schema_node.title
            else:
                # otherwise use either the explicitly provided title or name
                # colander capitalizes the title, which makes it wrong most of the time
                # when using CamelCase or camelBack schema definitions
                if isinstance(schema_node.raw_title, str):
                    converted["title"] = schema_node.title
                else:
                    converted["title"] = schema_node.name

        if converted.get("default") is colander.drop:
            converted.pop("default")

        xml = getattr(schema_node, "xml", None)
        if isinstance(xml, dict):
            converted["xml"] = xml

        return converted


class OAS3ParameterConverter(ParameterConverter):
    reserved_params = [
        "name",
        "in",
        "required",
        "allowReserved",
        "summary",
        "description",
        "schema",
        "content",
    ]

    def convert(self, schema_node, definition_handler):
        # type: (colander.SchemaNode, DefinitionHandler) -> OpenAPISpecParameter
        param_spec = super(OAS3ParameterConverter, self).convert(schema_node, definition_handler)
        if "schema" not in param_spec:
            param_schema = {}
            for param in list(param_spec):
                if param not in self.reserved_params:
                    param_schema[param] = param_spec.pop(param)
            param_spec["schema"] = param_schema
        return param_spec


class OAS3BodyParameterConverter(BodyParameterConverter, OAS3ParameterConverter):
    pass


class OAS3PathParameterConverter(PathParameterConverter, OAS3ParameterConverter):
    pass


class OAS3QueryParameterConverter(QueryParameterConverter, OAS3ParameterConverter):
    pass


class OAS3HeaderParameterConverter(HeaderParameterConverter, OAS3ParameterConverter):
    pass


class OAS3CookieParameterConverter(OAS3ParameterConverter):
    _in = "cookie"


class OAS3ParameterConversionDispatcher(ParameterConversionDispatcher):
    converters = {
        "body": OAS3BodyParameterConverter,
        "path": OAS3PathParameterConverter,
        "querystring": OAS3QueryParameterConverter,
        "GET": OAS3QueryParameterConverter,
        "header": OAS3HeaderParameterConverter,
        "headers": OAS3HeaderParameterConverter,
        "cookie": OAS3CookieParameterConverter,  # Not available in Swagger 2.0
    }


class OAS3DefinitionHandler(DefinitionHandler):
    json_pointer = "#/components/schemas/"

    def from_schema(self, schema_node, base_name=None):
        # type: (colander.SchemaNode, Optional[str]) -> OpenAPISchema
        """
        Convert the schema node to an :term:`OAS` schema.

        If the schema node provided ``schema_ref`` URL and that the object is not defined,
        use it instead as an external reference.
        """
        schema_ret = super(OAS3DefinitionHandler, self).from_schema(schema_node, base_name=base_name)
        schema_ref = getattr(schema_node, "schema_ref", None)
        if schema_ref and isinstance(schema_ref, str):
            name = self._get_schema_name(schema_node, base_name)
            schema = schema_ret
            if "$ref" in schema_ret:
                schema = self.definition_registry[name]  # ["schema"]
            if schema.get("type") == "object" and "properties" not in schema and "$ref" not in schema:
                for param in list(schema):
                    schema.pop(param)
                schema["$ref"] = schema_ref
        return schema_ret

    def _ref_recursive(self, schema, depth, base_name=None):
        # avoid key error if dealing with "any" type
        # note:
        #   It is important to consider that keyword mappings will not have a 'type',
        #   but their child nodes must be iterated to generate '$ref'. We only want to
        #   avoid the error if the 'type' happens to be explicitly set to an 'any' value, or
        #   that it is omitted for a generic JSON schema object that does not have a keyword.
        if not schema or (not schema.get("type") and not any(kw in schema for kw in KeywordMapper.keywords)):
            return schema or {}
        return super()._ref_recursive(schema, depth, base_name=base_name)

    def _process_items(self,
                       schema,      # type: Dict[str, Any]
                       list_type,   # type: Literal["oneOf", "allOf", "anyOf", "not"]
                       item_list,   # type: List[Dict[str, Any]]
                       depth,       # type: int
                       base_name,   # type: str
                       ):           # type: (...) -> Dict[str, Any]
        """
        Generates recursive schema definitions with JSON ref pointers for nested keyword objects.

        Contrary to the original implementation, preserves additional metadata like the object title, description, etc.
        """
        schema_ref = super(OAS3DefinitionHandler, self)._process_items(schema, list_type, item_list, depth, base_name)
        schema_def = self.definition_registry[base_name]
        schema_meta = schema.copy()
        schema_meta.pop(list_type)  # don't undo refs generated by processing
        schema_def.update(schema_meta)
        return schema_ref


class OAS3ParameterHandler(ParameterHandler):
    json_pointer = "#/components/parameters/"


class OAS3ResponseHandler(ResponseHandler):
    json_pointer = "#/components/responses/"


class CorniceOpenAPI(CorniceSwagger):
    openapi_spec = 3

    def __init__(self,
                 services=None,             # type: Optional[Sequence[CorniceService]]
                 def_ref_depth=0,           # type: int
                 param_ref=False,           # type: bool
                 resp_ref=False,            # type: bool
                 pyramid_registry=None,     # type: Optional[Registry]
                 ):                         # type: (...) -> None
        if self.openapi_spec == 3:
            self.definitions = OAS3DefinitionHandler
            self.parameters = OAS3ParameterHandler
            self.responses = OAS3ResponseHandler
            self.type_converter = OAS3TypeConversionDispatcher
            self.parameter_converter = OAS3ParameterConversionDispatcher
        super(CorniceOpenAPI, self).__init__(
            services=services,
            def_ref_depth=def_ref_depth,
            param_ref=param_ref,
            resp_ref=resp_ref,
            pyramid_registry=pyramid_registry,
        )

    def generate(self,
                 title=None,        # type: Optional[str]
                 version=None,      # type: Optional[str]
                 base_path=None,    # type: Optional[str]
                 info=None,         # type: Optional[OpenAPISpecInfo]
                 swagger=None,      # type: Optional[JSON]
                 openapi_spec=2,    # type: Literal[2, 3]
                 **kwargs           # type: Any
                 ):                 # type: (...) -> OpenAPISpecification
        spec = super(CorniceOpenAPI, self).generate(
            title=title,
            version=version,
            base_path=base_path,
            info=info,
            swagger=swagger,
            openapi_spec=openapi_spec,
            **kwargs
        )
        if self.openapi_spec == 3:
            definitions = spec.pop("definitions", {})
            parameters = spec.pop("parameters", {})
            responses = spec.pop("responses", {})
            spec.setdefault("components", {})
            spec["components"].setdefault("schemas", definitions)
            spec["components"].setdefault("parameters", parameters)
            spec["components"].setdefault("responses", responses)
        return spec
