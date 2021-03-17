"""
This module offers multiple utility schema definitions to be employed with
:mod:`colander` and :mod:`cornice_swagger`.

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
import inspect
import re
from abc import abstractmethod
from typing import TYPE_CHECKING

import colander
from cornice_swagger.converters.exceptions import ConversionError, NoSuchConverter
from cornice_swagger.converters.schema import (
    STRING_FORMATTERS,
    ObjectTypeConverter,
    TypeConversionDispatcher,
    TypeConverter
)

if TYPE_CHECKING:
    from typing import Dict, Iterable, Optional, Type, Union


LITERAL_SCHEMA_TYPES = frozenset([
    colander.Boolean,
    colander.Number,  # int, float, etc.
    colander.String,
    colander.Time,
    colander.Date,
    colander.DateTime,
    # colander.Enum,  # not supported but could be (literal int/str inferred from Python Enum object)
])


class SchemaNodeTypeError(TypeError):
    """Generic error indicating that the definition of a SchemaNode is invalid.

    This usually means the user forgot to specify a required element for schema creation,
    or that a provided combination of keywords, sub-nodes and/or schema type don't make
    any sense together, that they are erroneous, or that they cannot be resolved because
    of some kind of ambiguous definitions leading to multiple conflicting choices.
    """


class ConversionTypeError(ConversionError, TypeError):
    """Conversion error due to invalid type."""


class ConversionValueError(ConversionError, ValueError):
    """Conversion error due to invalid value."""


class OneOfCaseInsensitive(colander.OneOf):
    """
    Validator that ensures the given value matches one of the available choices, but allowing case insensitive values.
    """
    def __call__(self, node, value):
        if str(value).lower() not in (choice.lower() for choice in self.choices):
            return super(OneOfCaseInsensitive, self).__call__(node, value)


class StringRange(colander.Range):
    """
    Validator that provides the same functionalities as :class:`colander.Range` for a numerical string value.
    """
    def __init__(self, min=None, max=None, **kwargs):
        try:
            if isinstance(min, str):
                min = int(min)
            if isinstance(max, str):
                max = int(max)
        except ValueError:
            raise SchemaNodeTypeError("StringRange validator created with invalid min/max non-numeric string.")
        super(StringRange, self).__init__(min=min, max=max, **kwargs)

    def __call__(self, node, value):
        if not isinstance(value, str):
            raise colander.Invalid(node=node, value=value, msg="Value is not a string.")
        if not str.isnumeric(value):
            raise colander.Invalid(node=node, value=value, msg="Value is not a numeric string.")
        return super(StringRange, self).__call__(node, int(value))


class SchemeURL(colander.Regex):
    """
    String representation of an URL with extended set of allowed URI schemes.

    .. seealso::
        :class:`colander.url` [remote http(s)/ftp(s)]
        :class:`colander.file_uri` [local file://]
    """
    def __init__(self, schemes=None, msg=None, flags=re.IGNORECASE):
        if not schemes:
            schemes = [""]
        if not msg:
            msg = colander._("Must be a URL matching one of schemes {}".format(schemes))  # noqa
        regex_schemes = r"(?:" + "|".join(schemes) + r")"
        regex = colander.URL_REGEX.replace(r"(?:http|ftp)s?", regex_schemes)
        super(SchemeURL, self).__init__(regex, msg=msg, flags=flags)


class SemanticVersion(colander.Regex):
    """
    String representation that is valid against Semantic Versioning specification.

    .. seealso::
        https://semver.org/
    """

    def __init__(self, *args, v_prefix=False, rc_suffix=True, **kwargs):
        if "regex" in kwargs:
            self.pattern = kwargs.pop("regex")
        else:
            v_prefix = "v" if v_prefix else ""
            rc_suffix = r"(\.[a-zA-Z0-9\-_]+)*" if rc_suffix else ""
            self.pattern = (
                r"^"
                + v_prefix +
                r"\d+"      # major
                r"(\.\d+"   # minor
                r"(\.\d+"   # patch
                + rc_suffix +
                r")*)*$"
            )
        super(SemanticVersion, self).__init__(regex=self.pattern, *args, **kwargs)


class ExtendedBoolean(colander.Boolean):
    def serialize(self, node, cstruct):  # pylint: disable=W0221
        result = super(ExtendedBoolean, self).serialize(node, cstruct)
        if result is not colander.null:
            result = result == "true"
        return result


class ExtendedFloat(colander.Float):
    def serialize(self, node, cstruct):  # pylint: disable=W0221
        result = super(ExtendedFloat, self).serialize(node, cstruct)
        if result is not colander.null:
            result = float(result)
        return result


class ExtendedInteger(colander.Integer):
    def serialize(self, node, cstruct):  # pylint: disable=W0221
        result = super(ExtendedInteger, self).serialize(node, cstruct)
        if result is not colander.null:
            result = int(result)
        return result


class ExtendedString(colander.String):
    pass


class XMLObject(object):
    """
    Object that provides mapping to known XML extensions for OpenAPI schema definition.

    .. seealso::
        - https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.3.md#xmlObject
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


class ExtendedSchemaBase(colander.SchemaNode, metaclass=ExtendedSchemaMeta):
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
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def __init__(self, *args, **kwargs):
        schema_type = _get_schema_type(self, check=True)
        if isinstance(schema_type, (colander.Mapping, colander.Sequence)):
            if self.title in ["", colander.required] and not kwargs.get("title"):
                kwargs["title"] = _get_node_name(self, schema_name=True)

        if self.validator is None and isinstance(schema_type, colander.String):
            _format = kwargs.pop("format", getattr(self, "format", None))
            pattern = kwargs.pop("pattern", getattr(self, "pattern", None))
            if isinstance(pattern, str):
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

        super(ExtendedSchemaBase, self).__init__(*args, **kwargs)
        ExtendedSchemaBase._validate(self)

    @staticmethod
    def _validate(node):
        if node.default and node.validator not in [colander.null, None]:
            try:
                node.validator(node, node.default)
            except (colander.Invalid, TypeError):
                raise SchemaNodeTypeError(
                    "Default value [{!s}] of [{!s}] is not valid against its own validator.".format(
                        node.default, _get_node_name(node, schema_name=True))
                )


class DropableSchemaNode(ExtendedNodeInterface, ExtendedSchemaBase):
    """
    Drops the underlying schema node if ``missing=drop`` was specified and that the value
    representing it represents an *empty* value.

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

    .. seealso:
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
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
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
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
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

        .. code-block:: python

            class ContainerAnyKeyWithName(ExtendedMappingSchema):
                var = RequiredDict(variable="const")  # 'const' could clash with other below
                const = RequiredDict(String())

        Using ``<const>`` instead would ensure that no override occurs as it is a syntax error
        to write ``<const> = RequiredDict(String())`` in the class definition, but this value
        can still be used to create the internal mapping to evaluate sub-schemas without name
        clashes. As a plus, it also helps giving an indication that *any key* is accepted.

    .. seealso::
        - :class:`ExtendedSchemaNode`
        - :class:`ExtendedMappingSchema`
    """

    _extension = "_ext_variable"
    _variable = "variable"          # name of property containing variable name
    _variable_map = "variable_map"  # name of property containing variable => real node/key matched

    @classmethod
    def is_variable(cls, node):
        """If current node is the variable field definition."""
        return getattr(node, cls._variable, None) is not None

    def has_variables(self):
        """If the current container schema node has sub-node variables."""
        if isinstance(_get_schema_type(self), colander.Mapping):
            return any(VariableSchemaNode.is_variable(node) for node in self.children)
        return False

    @staticmethod
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
            self.name = kwargs.get("name", var)
            if not self.title:
                self.title = var
                self.raw_title = var
            setattr(self, self._variable, var)
        self._mark_variable_children()
        setattr(self, VariableSchemaNode._extension, True)

    def _mark_variable_children(self):
        """
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
        if self.schema_type is colander.Mapping:
            var_children = self._get_sub_variable(self.children)
            var_full_search = [var_children]
            if isinstance(_make_node_instance(self), KeywordMapper):
                keyword_objects = KeywordMapper.get_keyword_items(self)  # noqa
                var_full_search.extend(
                    [self._get_sub_variable(_make_node_instance(var_obj).children)
                     for var_obj in keyword_objects if var_obj.schema_type is colander.Mapping]
                )
            for var_subnodes in var_full_search:
                if len(var_subnodes):
                    var_names = [child.name for child in var_subnodes]
                    for var in var_names:
                        if len([v for v in var_names if v == var]) == 1:
                            continue
                        raise SchemaNodeTypeError("Invalid node '{}' defines multiple schema nodes "
                                                  "with name 'variable={}'.".format(type(self), var))
                    var_names = [getattr(child, self._variable, None) for child in var_subnodes]
                    setattr(self, self._variable_map, {var: None for var in var_names})

    def _get_sub_variable(self, subnodes):
        return [child for child in subnodes if getattr(child, self._variable, None)]

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        return ExtendedSchemaNode.deserialize(self, cstruct)  # noqa

    def _deserialize_impl(self, cstruct):
        if not getattr(self, VariableSchemaNode._extension, False):
            return cstruct
        if cstruct in (colander.drop, colander.null):
            return cstruct
        # skip step in case operation was called as sub-node from another schema but doesn't
        # correspond to a valid variable map container (e.g.: SequenceSchema)
        if not isinstance(self, VariableSchemaNode):
            return cstruct
        var_map = getattr(self, self._variable_map, {})
        if not isinstance(var_map, dict) or not len(var_map):
            return cstruct

        var_children = self._get_sub_variable(self.children)
        const_child_keys = [child.name for child in self.children if child not in var_children]
        for var_child in var_children:
            var = getattr(var_child, self._variable, None)
            var_map[var] = []
            # value must be a dictionary map object to allow variable key
            if not isinstance(cstruct, dict):
                raise colander.Invalid(
                    node=self, msg="Variable key not allowed for non-mapping data: {}".format(type(cstruct).__name__)
                )

            var_invalid = colander.Invalid(
                node=self, msg="Requirement not met under variable: {}.".format(var), value=cstruct,
            )
            # attempt to find any sub-node matching the sub-schema under variable
            for child_key, child_cstruct in cstruct.items():
                # skip explicit nodes as well as other variables already matched
                # cannot match the same child-cstruct again with another variable
                if child_key in const_child_keys or child_key in var_map:
                    continue
                try:
                    schema_class = _make_node_instance(var_child)
                    var_cstruct = schema_class.deserialize(child_cstruct)
                    # not reached if previous raised invalid
                    var_map[var].append({
                        "node": schema_class.name,
                        "name": child_key,
                        "cstruct": var_cstruct
                    })
                except colander.Invalid as invalid:
                    var_invalid.add(invalid)
            if not var_map.get(var, None):
                raise var_invalid

        invalid_var = colander.Invalid(self, value=var_map)
        try:
            # Substitute real keys with matched variables to run full deserialize so
            # that mapping can find nodes name against attribute names, then re-apply originals.
            # We must do this as non-variable sub-schemas could be present and we must also
            # validate them against full schema.
            if not const_child_keys:
                result = {}
            else:
                for var, mapped in var_map.items():
                    # if multiple objects corresponding to a variable sub-schema where provided,
                    # we only give one as this is what is expected for normal-mapping deserialize
                    cstruct[mapped[0]["node"]] = cstruct.pop(mapped[0]["name"])
                result = super(VariableSchemaNode, self).deserialize(cstruct)  # noqa
            for var, mapped in var_map.items():
                for var_mapped in mapped:
                    result[var_mapped["name"]] = var_mapped["cstruct"]
        except colander.Invalid as invalid:
            invalid_var.msg = "Tried matching variable '{}' sub-schemas but no match found.".format(var)  # noqa
            invalid_var.add(invalid)
            raise invalid_var
        except KeyError:
            invalid_var.msg = "Tried matching variable '{}' sub-schemas but mapping failed.".format(var)  # noqa
            raise invalid_var
        return result


class ExtendedSchemaNode(DefaultSchemaNode, DropableSchemaNode, VariableSchemaNode, ExtendedSchemaBase):
    """
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

    @staticmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def _deserialize_extensions(self, cstruct):
        result = cstruct
        # process extensions to infer alternative parameter/property values
        # node extensions order is important as they can impact the following ones
        for node in [DropableSchemaNode, DefaultSchemaNode, VariableSchemaNode]:  # type: Type[ExtendedNodeInterface]
            # important not to break if result is 'colander.null' since Dropable and Default
            # schema node implementations can substitute it with their appropriate value
            if result is colander.drop:
                # if result is to drop though, we are sure that nothing else must be done
                break
            result = node._deserialize_impl(self, result)
        return result

    def deserialize(self, cstruct):
        schema_type = _get_schema_type(self)
        result = ExtendedSchemaNode._deserialize_extensions(self, cstruct)

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

        if result is colander.null and self.missing is colander.required:
            raise colander.Invalid(node=self, msg=self.missing_msg)

        return result


class DropableSequenceSchema(DropableSchemaNode, colander.SequenceSchema):
    """
    Extends :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
    when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.
    """
    schema_type = colander.SequenceSchema.schema_type


class DefaultSequenceSchema(DefaultSchemaNode, colander.SequenceSchema):
    """
    Extends :class:`colander.SequenceSchema` to auto-handle replacing the result using the provided
    ``default`` value when the deserialization results into a sequence that should normally be dropped.
    """
    schema_type = colander.SequenceSchema.schema_type


class ExtendedSequenceSchema(DefaultSchemaNode, DropableSchemaNode, colander.SequenceSchema):
    """
    Combines :class:`DefaultSequenceSchema` and :class:`DefaultSequenceSchema` extensions so that
    ``default`` keyword is used first to resolve a missing sequence during :meth:`deserialize`
    call, and then removes the node completely if no ``default`` was provided.

    .. seealso::
        - :class:`ExtendedSchemaNode`
        - :class:`ExtendedMappingSchema`
    """
    schema_type = colander.SequenceSchema.schema_type

    def __init__(self, *args, **kwargs):
        super(ExtendedSequenceSchema, self).__init__(*args, **kwargs)
        self._validate()

    def _validate(self):
        ExtendedSchemaBase._validate(self.children[0])


class DropableMappingSchema(DropableSchemaNode, colander.MappingSchema):
    """
    Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
    when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.
    """
    schema_type = colander.MappingSchema.schema_type


class DefaultMappingSchema(DefaultSchemaNode, colander.MappingSchema):
    """
    Override the default :class:`colander.MappingSchema` to auto-handle replacing missing entries by
    their specified ``default`` during deserialization.
    """
    schema_type = colander.MappingSchema.schema_type


class VariableMappingSchema(VariableSchemaNode, colander.MappingSchema):
    """
    Override the default :class:`colander.MappingSchema` to auto-handle replacing missing entries by
    their specified ``variable`` during deserialization.
    """
    schema_type = colander.MappingSchema.schema_type


class ExtendedMappingSchema(
    DefaultSchemaNode,
    DropableSchemaNode,
    VariableSchemaNode,
    colander.MappingSchema
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
        - :class:`PermissiveMappingSchema`
    """
    schema_type = colander.MappingSchema.schema_type

    def __init__(self, *args, **kwargs):
        super(ExtendedMappingSchema, self).__init__(*args, **kwargs)
        self._validate_nodes()

    def _validate_nodes(self):
        for node in self.children:
            ExtendedSchemaBase._validate(node)


class PermissiveMappingSchema(ExtendedMappingSchema):
    """
    Object schema that will allow *any unknown* field to remain present in the resulting deserialization.

    This type is useful for defining a dictionary where some field names are not known in advance, or
    when more optional keys that don't need to all be exhaustively provided in the schema are acceptable.

    When doing schema deserialization to validate it, unknown keys would normally be removed without this class
    (default behaviour is to ``ignore`` them). With this schema, content under an unknown key is ``preserved``
    as it was received without any validation. Other fields that are explicitly specified with sub-schema nodes
    will still be validated as per usual behaviour.

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
        kwargs["unknown"] = "preserve"
        super(PermissiveMappingSchema, self).__init__(*args, **kwargs)


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

    def __init__(self, *args, **kwargs):
        super(KeywordMapper, self).__init__(*args, **kwargs)
        if not hasattr(self, self._keyword):
            # try retrieving from a kwarg definition (either as literal keyword or OpenAPI name)
            if kwargs:
                maybe_kwargs = [_kw for _kw in kwargs
                                if _kw in self._keyword_map or _kw in self._keyword_inv]
                if len(maybe_kwargs) == 1:
                    self._keyword = self._keyword_inv.get(maybe_kwargs[0], maybe_kwargs[0])
                    setattr(self, self._keyword, kwargs.get(maybe_kwargs[0]))
            if not self._keyword:
                raise SchemaNodeTypeError("Type '{}' must define a keyword element.".format(self))
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
                raise SchemaNodeTypeError("Multiple keywords '{}' not permitted for '{!s}'".format(
                    list(self._keywords), self
                ))
        if not total == 1:
            raise SchemaNodeTypeError("Missing one of keywords '{}' for '{!s}'".format(
                list(self._keywords), self
            ))

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

    @abstractmethod
    def _deserialize_keyword(self, cstruct):
        """
        This method must be implemented by the specific keyword to handle
        invalid subnodes according to the behaviour it offers.

        .. seealso::
            - :meth:`_deserialize_subnode`
        """
        raise NotImplementedError

    def _deserialize_subnode(self, node, cstruct):
        """
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
            node.name = _get_node_name(self, schema_name=True)  # pass down the parent name
        if isinstance(node, KeywordMapper):
            return KeywordMapper.deserialize(node, cstruct)
        return ExtendedSchemaNode.deserialize(node, cstruct)

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        if cstruct is colander.null:
            if self.required and not VariableSchemaNode.is_variable(self):
                raise colander.Invalid(self, "Missing required field.")
            return ExtendedSchemaNode.deserialize(self, colander.null)
        # first process the keyword subnodes
        result = self._deserialize_keyword(cstruct)
        # if further fields where explicitly added next to the keyword schemas,
        # validate and apply them as well
        if isinstance(result, dict) and self.children:
            mapping_data = super(KeywordMapper, self).deserialize(cstruct)
            result.update(mapping_data)
        return result


class OneOfKeywordSchema(KeywordMapper):
    """
    Allows specifying multiple supported mapping schemas variants for an underlying schema
    definition. Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

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

    For example::

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

    @classmethod
    @abstractmethod
    def _one_of(cls):
        # type: () -> Iterable[Union[colander.SchemaNode, Type[colander.SchemaNode]]]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise SchemaNodeTypeError("Missing '{}' keyword for schema '{}'.".format(cls._keyword, cls))

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
                    node_fields = [getattr(field, "example", colander.null) for field in node.children
                                   if field.name == discriminator_spec["propertyName"]]
                    if len(node_fields) != 1:
                        continue
                    example = node_fields[0]
                    if example is not colander.null:
                        if example in mapping:
                            raise SchemaNodeTypeError(
                                "Keyword schema '{}' of type '{}' specification with 'discriminator' attempts "
                                "to refer to duplicate example values '{}' between '{}' and '{}'".format(
                                    schema_name, keyword, example,
                                    _get_node_name(mapping[example], schema_name=True),
                                    _get_node_name(node, schema_name=True),
                                )
                            )
                        mapping[example] = node
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
        Test each possible case, return all corresponding errors if
        none of the possibilities is valid including all sub-dependencies.
        """
        invalid_one_of = dict()
        valid_one_of = []
        valid_nodes = []
        for schema_class in self._one_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                result = self._deserialize_subnode(schema_class, cstruct)
                valid_one_of.append(result)
                valid_nodes.append(schema_class)
            except colander.Invalid as invalid:
                invalid_one_of.update({_get_node_name(invalid.node, schema_name=True): invalid.asdict()})
        message = (
            "Incorrect type must be one of: {}. Errors for each case: {}"
            .format(list(invalid_one_of), invalid_one_of)
        )
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
                valid_values = list(filter(lambda c: c == cstruct and type(c) == type(cstruct), valid_one_of))
                if len(valid_values) == 1:
                    return valid_values[0]
                message = (
                    "Incorrect type cannot differentiate between multiple base-type valid schemas. "
                    "Must be only one of: {}.".format(valid_values)
                )

        raise colander.Invalid(node=self, msg=message, value=cstruct)


class AllOfKeywordSchema(KeywordMapper):
    """
    Allows specifying all the required partial mapping schemas for an underlying complete schema
    definition. Corresponds to the ``allOf`` specifier of `OpenAPI` specification.

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
        """This must be overridden in the schema definition using it."""
        raise SchemaNodeTypeError("Missing '{}' keyword for schema '{}'.".format(cls._keyword, cls))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return all corresponding errors if
        any of the possibilities is invalid.
        """
        required_all_of = dict()
        missing_all_of = dict()
        merged_all_of = dict()
        for schema_class in self._all_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                required_all_of.update({_get_node_name(schema_class, schema_name=True): str(schema_class)})
                merged_all_of.update(self._deserialize_subnode(schema_class, cstruct))
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
    _keyword_schemas_same_struct = True
    _keyword = "_any_of"

    @classmethod
    @abstractmethod
    def _any_of(cls):
        # type: () -> Iterable[Union[colander.SchemaNode, Type[colander.SchemaNode]]]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise SchemaNodeTypeError("Missing '{}' keyword for schema '{}'.".format(cls._keyword, cls))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return if no corresponding schema was found.
        """
        option_any_of = dict()
        merged_any_of = colander.null
        invalid_any_of = colander.Invalid(node=self)
        for schema_class in self._any_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                option_any_of.update({_get_node_name(schema_class, schema_name=True): str(schema_class)})
                result = self._deserialize_subnode(schema_class, cstruct)
                if result not in (colander.drop, colander.null):
                    # technically not supposed to have 'Sequence' type since they can only have one child
                    # only possibility is all similar objects or all literals because of '_keyword_schemas_same_struct'
                    if schema_class.schema_type is colander.Mapping:
                        if merged_any_of is colander.null:
                            merged_any_of = dict()
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
        if merged_any_of is colander.null:
            invalid_any_of.msg = (
                "Incorrect type must represent any of: {}. "
                "All missing from: {}".format(list(option_any_of), cstruct)
            )
            raise invalid_any_of
        return merged_any_of


class NotKeywordSchema(KeywordMapper):
    """
    Allows specifying specific schema conditions that fails underlying schema definition validation if present.

    This is equivalent to OpenAPI object mapping with ``additionalProperties: false``, but is more explicit in
    the definition of invalid or conflicting field names with explicit definitions during deserialization.

    Example::

        class RequiredItem(ExtendedMappingSchema):
            item = ExtendedSchemaNode(String())

        class MappingWithType(ExtendedMappingSchema):
            type = ExtendedSchemaNode(String())

        class MappingWithoutType(NotKeywordSchema, RequiredItem):
            _not = [MappingWithType()]

        # following will raise invalid error even if 'item' is valid because 'type' is also present
        MappingWithoutType().deserialize({"type": "invalid", "item": "valid"})

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
        """This must be overridden in the schema definition using it."""
        raise SchemaNodeTypeError("Missing '{}' keyword for schema '{}'.".format(cls._keyword, cls))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, raise if any corresponding schema was successfully validated.
        """
        invalid_not = dict()
        for schema_class in self._not:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                result = self._deserialize_subnode(schema_class, cstruct)
                if isinstance(result, dict) and not len(result):
                    continue  # allow empty result meaning every item was missing and dropped
                invalid_names = [node.name for node in schema_class.children]
                invalid_not.update({_get_node_name(schema_class, schema_name=True): invalid_names})
            except colander.Invalid:
                pass  # error raised as intended when missing field is not present
        if invalid_not:
            message = "Value contains not allowed fields from schema conditions: {}".format(invalid_not)
            raise colander.Invalid(node=self, msg=message, value=cstruct)
        return cstruct


class KeywordTypeConverter(TypeConverter):
    """Generic keyword converter that builds schema with a list of sub-schemas under the keyword."""
    def convert_type(self, schema_node):
        keyword = schema_node.get_keyword_name()
        keyword_schema = {
            keyword: []
        }

        for item_schema in schema_node.get_keyword_items():
            obj_instance = _make_node_instance(item_schema)
            obj_converted = self.dispatcher(obj_instance)
            keyword_schema[keyword].append(obj_converted)
        return keyword_schema


class OneOfKeywordTypeConverter(KeywordTypeConverter):
    """Object converter that generates the ``oneOf`` keyword definition.

    This object does a bit more work than other :class:`KeywordTypeConverter` as it
    handles the shorthand definition as described in :class:`OneOfKeywordSchema`

    .. seealso::
        - :class:`OneOfKeywordSchema`
    """
    def convert_type(self, schema_node):
        # type: (OneOfKeywordSchema) -> Dict
        keyword = schema_node.get_keyword_name()
        one_of_obj = {
            keyword: []
        }

        for item_schema in schema_node.get_keyword_items():
            item_obj = _make_node_instance(item_schema)
            # shortcut definition of oneOf[allOf[],allOf[]] mix, see OneOfKeywordSchema docstring
            # (eg: schema fields always needed regardless of other fields supplied by each oneOf schema)
            if len(getattr(schema_node, "children", [])):
                if not isinstance(schema_node, colander.MappingSchema):
                    raise ConversionTypeError(
                        "Unknown base type to convert oneOf schema item is no a mapping: {}".format(type(schema_node))
                    )
                # specific oneOf sub-item, will be processed by itself during dispatch of sub-item of allOf
                # rewrite the title of that new sub-item schema from the original title to avoid conflict
                schema_title = _get_node_name(schema_node, schema_name=True)
                # generate the new nested definition of keywords using schema node bases and children
                item_title = _get_node_name(item_obj, schema_name=True)
                # NOTE: to avoid potential conflict of schema reference definitions with other existing ones,
                #       use an invalid character that cannot exist in Python class name defining the schema titles
                one_of_title = schema_title + "." + item_title
                shared_title = schema_title + ".Shared"
                obj_req_title = item_title + ".AllOf"
                # fields that are shared across all the oneOf sub-items
                # pass down the original title of that object to refer to that schema reference
                obj_shared = ExtendedMappingSchema(title=shared_title)
                obj_shared.children = schema_node.children
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
    """Object converter that generates the ``allOf`` keyword definition."""


class AnyOfKeywordTypeConverter(KeywordTypeConverter):
    """Object converter that generates the ``anyOf`` keyword definition."""


class NotKeywordTypeConverter(KeywordTypeConverter):
    """Object converter that generates the ``not`` keyword definition."""

    def convert_type(self, schema_node):
        result = ObjectTypeConverter(self.dispatcher).convert_type(schema_node)
        result["additionalProperties"] = False
        return result


class VariableObjectTypeConverter(ObjectTypeConverter):
    """
    Updates the mapping object's ``additionalProperties`` for each ``properties``
    that a marked as :class:`VariableSchemaNode`.
    """
    def convert_type(self, schema_node):
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


# TODO: replace directly in original cornice_swagger
#  (see: https://github.com/Cornices/cornice.ext.swagger/issues/133)
class OAS3TypeConversionDispatcher(TypeConversionDispatcher):
    openapi_spec = 3

    def __init__(self, custom_converters=None, default_converter=None):
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
            colander.Mapping: VariableObjectTypeConverter
        }
        extended_converters.update(self.keyword_converters)
        if custom_converters:
            extended_converters.update(custom_converters)
        super(OAS3TypeConversionDispatcher, self).__init__(extended_converters, default_converter)

    def __call__(self, schema_node):
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
                    raise NoSuchConverter

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

        xml = getattr(schema_node, "xml", None)
        if isinstance(xml, dict):
            converted["xml"] = xml

        return converted


def _make_node_instance(schema_node_or_class):
    # type: (Union[colander.SchemaNode, Type[colander.SchemaNode]]) -> colander.SchemaNode
    """Obtains a schema node instance in case it was specified only by type reference.

    This helps being more permissive of provided definitions while handling situations
    like presented in the example below::

        class Map(OneOfMappingSchema):
            # uses types instead of instances like 'SubMap1([...])' and 'SubMap2([...])'
            _one_of = (SubMap1, SubMap2)

    """
    if isinstance(schema_node_or_class, colander._SchemaMeta):  # noqa: W0212
        schema_node_or_class = schema_node_or_class()
    if not isinstance(schema_node_or_class, colander.SchemaNode):  # refer to original class to support non-extended
        raise ConversionTypeError(
            "Invalid item should be a SchemaNode, got: {!s}".format(type(schema_node_or_class)))
    return schema_node_or_class


def _get_schema_type(schema_node, check=False):
    # type: (Union[colander.SchemaNode, Type[colander.SchemaNode]], bool) -> Optional[colander.SchemaType]
    """Obtains the schema-type from the provided node, supporting various initialization methods.

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
        raise ConversionTypeError("Invalid schema type could not be detected: {!s}".format(type(schema_type)))
    return schema_type


def _get_node_name(schema_node, schema_name=False):
    # type: (colander.SchemaNode, bool) -> str
    """
    Obtains the name of the node with best available value.

    :param schema_node: node for which to retrieve the name.
    :param schema_name:
        - If ``True``, prefer the schema definition (class) name over the instance or field name.
        - Otherwise, return the field name, the title or as last result the class name.
    :returns: node name
    """
    if schema_name:
        return type(schema_node).__name__
    return getattr(schema_node, "name", None) or getattr(schema_node, "title", None) or type(schema_node).__name__
