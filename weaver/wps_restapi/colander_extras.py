"""
This module offers multiple utility schema definitions to be employed with
:mod:`colander` and :mod:`cornice_swagger`.

The SchemaNodes provided here can be used in-place of :mod:`colander` ones, but
giving you extended behaviour according to provided keywords. You can therefore
do the following and all will be applied without modifying your code base.

.. code-block:: python

    # same applies for Mapping and Sequence schemas
    from colander_extras import ExtendedSchemaNode as SchemaNode
    from colander import SchemaNode     # instead of this

The schemas support extended :mod:`cornice_swagger` type converters so that you
can generate OpenAPI-3 specifications. The original package support is limited
to Swagger-2. You will also need additional in-place modifications provided
`here <https://github.com/fmigneault/cornice.ext.swagger/tree/openapi-3>`_.

The main classes are:
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
    ``title`` for adjusting the displayed name in the Swagger UI.

"""
import inspect
from abc import abstractmethod
from typing import TYPE_CHECKING

import colander

from cornice_swagger.converters.exceptions import ConversionError, NoSuchConverter
from cornice_swagger.converters.schema import ObjectTypeConverter, TypeConversionDispatcher, TypeConverter

if TYPE_CHECKING:
    from typing import Iterable


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


class DropableSchemaNode(colander.SchemaNode):
    """
    Drops the underlying schema node if ``missing=drop`` was specified and that the value
    representing it represents an *empty* value.

    In the case of nodes corresponding to literal schema type (i.e.: Integer, String, etc.),
    the *empty* value looked for is ``None``. This is to make sure that ``0`` or ``""`` are
    preserved unless unless explicitly representing *no-data*. In the case of container
    schema types (i.e.: list, dict, etc.), it is simply considered *empty* if there are no
    element in it, without any more explicit verification.

    Original behaviour of schema classes that can have children nodes such as
    :class:`colander.MappingSchema` and :class:`colander.SequenceSchema` are to drop the sub-node
    only if its value is resolved as :class:`colander.null` or :class:`colander.drop`. This results
    in *optional* field definitions replaced by ``None`` in many implementations to raise
    :py:exc:`colander.Invalid` during deserialization. Inheriting this class in a schema definition
    will handle this situation automatically.

    Required schemas (without ``missing=drop``, i.e.: :class:`colander.required`) will still raise
    for undefined nodes.

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
    @staticmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
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
        return super(DropableSchemaNode, self).deserialize(cstruct)


class DefaultSchemaNode(colander.SchemaNode):
    """
    If ``default`` keyword is provided during :class:`colander.SchemaNode` creation, overrides the
    returned value by this default if missing from the structure during :meth:`deserialize` call.

    Original behaviour was to drop the missing value instead of replacing by ``default``.
    Executes all other :class:`colander.SchemaNode` operations normally.

    .. seealso::
        - :class:`DefaultMappingSchema`
        - :class:`DefaultSequenceSchema`
    """

    @staticmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        # if nothing to process in structure, ask to remove (unless picked by default)
        result = colander.drop
        if cstruct is not colander.null:
            result = super(DefaultSchemaNode, self).deserialize(cstruct)
        if not isinstance(self.default, type(colander.null)) and result is colander.drop:
            result = self.default
        return result


class VariableSchemaNode(colander.SchemaNode):
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
            id = ExtendedSchemaNode(String())
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

    _variable = "variable"          # name of property containing variable name
    _variable_map = "variable_map"  # name of property containing variable => real node/key matched

    @classmethod
    def is_variable(cls, node):
        return getattr(node, cls._variable, None) is not None

    @staticmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def __init__(self, *args, **kwargs):
        # define node with provided variable by keyword or within a SchemaNode class definition
        var = kwargs.pop(self._variable, getattr(self, self._variable, None))
        super(VariableSchemaNode, self).__init__(*args, **kwargs)
        if var:
            # note: literal type allowed only for shorthand notation, normally not allowed
            if self.schema_type not in [colander.SchemaNode, colander.Mapping]:
                raise SchemaNodeTypeError(
                    "Keyword 'variable' can only be applied to Mapping and literal-type schema nodes. "
                    "Got: {!s} ({!s})".format(type(self), self.schema_type))
            self.name = var
            if not self.title:
                self.title = var
                self.raw_title = var
            setattr(self, self._variable, var)
        self._mark_variable_children()

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
            ``name`` with ``variable`` makes the value/sub-schema correspondance transparent to
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
        if cstruct in (colander.drop, colander.null):
            return cstruct
        var_map = getattr(self, self._variable_map, {})
        if not isinstance(var_map, dict) or not len(var_map):
            return super(VariableSchemaNode, self).deserialize(cstruct)

        var_children = self._get_sub_variable(self.children)
        const_child_keys = [child.name for child in self.children if child not in var_children]
        for var_child in var_children:
            var = getattr(var_child, self._variable, None)
            var_map[var] = []
            var_invalid = colander.Invalid(
                node=self, msg="Requirement not met under variable: {}.".format(var))
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

        result = colander.null
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
                result = super(VariableSchemaNode, self).deserialize(cstruct)
            for var, mapped in var_map.items():
                for var_mapped in mapped:
                    result[var_mapped["name"]] = var_mapped["cstruct"]
        except colander.Invalid as invalid:
            invalid_var.msg = "Tried matching variable '{}' sub-schemas " \
                              "but no match found.".format(var)  # noqa
            invalid_var.add(invalid)
            raise invalid_var
        except KeyError:
            invalid_var.msg = "Tried matching variable '{}' sub-schemas " \
                              "but mapping failed.".format(var)  # noqa
            raise invalid_var
        return result


class ExtendedSchemaNode(DefaultSchemaNode, DropableSchemaNode, VariableSchemaNode, colander.SchemaNode):
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
    @staticmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def deserialize(self, cstruct):
        result = DropableSchemaNode.deserialize(self, cstruct)
        result = DefaultSchemaNode.deserialize(self, result)
        result = VariableSchemaNode.deserialize(self, result)
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


class KeywordMapper(colander.MappingSchema):
    """
    Generic keyword mapper for any sub-implementers.

    Allows specifying multiple combinations of schemas variants for an underlying schema definition.
    Each implementer must provide the corresponding ``keyword`` it defines amongst `OpenAPI` specification keywords.
    """
    schema_type = colander.MappingSchema.schema_type
    _keyword_objects_only = False   # override validation as needed
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
        self._validate_keyword_objects()
        self._validate_keyword_schemas()

    @classmethod
    def get_keyword_name(cls):
        return cls._keyword_map[cls._keyword]

    def get_keyword_items(self):
        return getattr(self, self._keyword, [])

    def _validate_keyword_unique(self):
        kw_items = self.get_keyword_items()
        if not hasattr(kw_items, "__iter__") or not len(kw_items):  # noqa
            raise ConversionValueError("Element '{}' of '{!s}' must be iterable with at least 1 value. "
                                       "Instead it was '{!s}'".format(self._keyword, type(self).__name__, kw_items))
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

    def _validate_keyword_objects(self):
        """
        Validation of keyword sub-nodes to be only defined as schema *objects*
        (i.e.: any node that defines its schema type as :class:`Mapping`).

        This validation is executed only if the class inheriting from :class:`KeywordMapper`
        defines ``_keyword_objects_only = True``.
        """
        if getattr(self, "_keyword_objects_only", False):
            for child in self.get_keyword_items():
                if child.schema_type is not colander.Mapping:
                    key = self.get_keyword_name()
                    raise SchemaNodeTypeError(
                        "Keyword schema '{}' of type '{}' can only have object children, "
                        "but '{}' is '{}'.".format(type(self), key, type(child), child.schema_type))

    def _validate_keyword_schemas(self):
        """
        Additional convenience method that can be overridden by a keyword implementer
        to validate the integrity of sub-node schemas with specific requirements.
        If integrity is invalid, this method should raise :exc:`SchemaNodeTypeError`.

        By default, nothing is executed here, it is meant purely as external extension.
        This validation will be executed last after other validations.

        .. seealso::
            - :meth:`_validate_keyword_unique`
            - :meth:`_validate_keyword_objects`
        """

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
        node.name = self.name  # pass down the parent name
        if isinstance(node, KeywordMapper):
            return KeywordMapper.deserialize(node, cstruct)
        return ExtendedSchemaNode.deserialize(node, cstruct)

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        if cstruct is colander.null:
            return colander.null
        result = self._deserialize_keyword(cstruct)
        if isinstance(result, dict):
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

    In the above example, the validation (ie: ``deserialize``) process will succeed if any of
    the ``_one_of`` variants' validator completely succeed, and will fail if every variant fails
    validation execution.

    .. note::
        Class ``OneOfWithRequiredFields`` in the example is a shortcut variant to generate a
        specification that represents the pseudo-code ``oneOf([<list-of-objects-with-same-base>])``.

    The real OpenAPI method to implement the above very commonly occurring situation is as
    presented by the following pseudo-code::

        oneOf[allOf[RequiredByBoth, Variant1], allOf[RequiredByBoth, Variant2]]

    This is both painful to read and is a lot of extra code to write when you actually expand it
    all into classes (each ``oneOf/allOf`` is another class). Class :class:`OneOfKeywordSchema`
    will actually simplify this by automatically making the ``allOf`` definitions for you if it
    detects other schema nodes than ``oneOf`` specified in the class. You can still do the full
    ``oneOf/allOf`` classes expansion manually though, it will result into the same specification.

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
    (e.g.: field ``type`` defining the type of object), consider adding a validator to that
    schema node with explicit values to solve the discrimination problem. As a shorcut, the keyword
    ``discriminator = {"field-name": "value"}`` can be provided to try matching as a last resort.
    For example::

        class Animal(ExtendedMappingSchema):
            name = ExtendedSchemaNode(String())
            type = ExtendedSchemaNode(String())  # with explicit definition, this shouldn't be here

            ## With explicit definitions, each below 'Animal' class should define as follows
            ## type = ExtendedSchemaNode(String(), validator=colander.OneOf(['<animal>']))

        class Cat(Animal):
            [...]   # many **OPTIONAL** fields

        class Dog(Animal):
            [...]   # many **OPTIONAL** fields

        # With the discriminator keyword, following is possible
        class SomeAnimal(OneOfMappingSchema):
            _one_of = [
                Cat(discriminator={"type": "cat"}),
                Dog(discriminator={"type": "dog"}),
            ]

    .. note::
        ``discriminator`` keyword only supports a map of key-string to some literal value
        as in the example, and the key must be located at the top level of the mapping.
        If this is not the case, you probably need to redesign your schema and/or class
        hierarchy slightly. Your use case is probably resolvable in some other way.
        Class :class:`PermissiveMappingSchema` can also be considered if validation of
        the sub-schemas is not strictly required.

    When multiple valid schemas are matched against, the error will be raised and returned with
    corresponding elements (fully listed).

    .. seealso::
        - :class:`AllOfKeywordSchema`
        - :class:`AnyOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword_objects_only = False
    _keyword = "_one_of"
    _discriminator = "discriminator"

    @classmethod
    @abstractmethod
    def _one_of(cls):
        # type: () -> Iterable[colander._SchemaMeta]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise SchemaNodeTypeError("Missing '{}' keyword for schema '{}'.".format(cls._keyword, cls))

    def __init__(self, *args, **kwargs):
        discriminator = getattr(self, self._discriminator, None)
        discriminator = kwargs.pop(self._discriminator, discriminator)
        setattr(self, self._discriminator, discriminator)
        super(OneOfKeywordSchema, self).__init__(*args, **kwargs)

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
                valid_one_of.append(self._deserialize_subnode(schema_class, cstruct))
                valid_nodes.append(schema_class)
            except colander.Invalid as invalid:
                invalid_one_of.update({type(invalid.node).__name__: invalid.asdict()})

        if valid_one_of:
            # if found only one, return it, otherwise try to discriminate
            if len(valid_one_of) == 1:
                return valid_one_of[0]

            # return the format which didn't change the input data
            # ##keep_valid = []
            # ##for valid in valid_one_of:
            # ## if _dict_nested_contained(cstruct, valid):
            # ##     keep_valid.append(valid)
            # ##if len(keep_valid) == 1:
            # ##   return keep_valid[0]
            discriminator = getattr(self, self._discriminator, None)
            if isinstance(discriminator, dict):
                # try last resort solve
                valid_discriminated = []
                error_discriminated = {}
                for i, obj in enumerate(valid_one_of):
                    node = valid_nodes[i]
                    node_name = getattr(node, "name", None) or \
                                getattr(node, "title", None) or \
                                type(node).__name__  # noqa: E127
                    if all(getattr(obj, d_key, None) == d_val
                           for d_key, d_val in discriminator.items()):
                        valid_discriminated.append(obj)
                        error_discriminated.update({node_name: obj})
                    else:
                        invalid_one_of = {}  # reset, at least one was matched
                if len(valid_discriminated) == 1:
                    return valid_discriminated[0]
                elif len(valid_discriminated) > 1:
                    invalid_one_of = error_discriminated
            message = "Incorrect type, cannot discriminate between multiple valid schemas." \
                      "Must be only one of: {}.".format(list(invalid_one_of.keys()))
            raise colander.Invalid(node=self, msg=message, value=discriminator)

        message = "Incorrect type, must be one of: {}. Errors for each case: {}" \
                  .format(list(invalid_one_of.keys()), invalid_one_of)
        raise colander.Invalid(node=self, msg=message)


class AllOfKeywordSchema(KeywordMapper):
    """
    Allows specifying all the required partial mapping schemas for an underlying complete schema
    definition. Corresponds to the ``allOf`` specifier of `OpenAPI` specification.

    Example::

        .. todo:: example

    .. seealso::
        - :class:`OneOfKeywordSchema`
        - :class:`AnyOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword_objects_only = True
    _keyword = "_all_of"

    @classmethod
    @abstractmethod
    def _all_of(cls):
        # type: () -> Iterable[colander._SchemaMeta]  # noqa: W0212
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
                required_all_of.update({type(schema_class).__name__: str(schema_class)})
                merged_all_of.update(self._deserialize_subnode(schema_class, cstruct))
            except colander.Invalid as invalid:
                missing_all_of.update({type(invalid.node).__name__: str(invalid)})

        if missing_all_of:
            # if anything failed, the whole definition is invalid in this case
            message = "Incorrect type, must represent all of: {}. Missing following cases: {}" \
                .format(list(required_all_of), list(missing_all_of))
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

        .. todo:: example

    .. seealso::
        - :class:`OneOfKeywordSchema`
        - :class:`AllOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword_objects_only = True
    _keyword = "_any_of"

    @classmethod
    @abstractmethod
    def _any_of(cls):
        # type: () -> Iterable[colander._SchemaMeta]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise SchemaNodeTypeError("Missing '{}' keyword for schema '{}'.".format(cls._keyword, cls))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return if no corresponding schema was found.
        """
        option_any_of = dict()
        merged_any_of = dict()
        invalid_any_of = colander.Invalid(node=self)
        for schema_class in self._any_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                option_any_of.update({type(schema_class).__name__: str(schema_class)})
                merged_any_of.update(self._deserialize_subnode(schema_class, cstruct))
            except colander.Invalid as invalid:
                invalid_any_of.add(invalid)

        if not merged_any_of:
            # nothing succeeded, the whole definition is invalid in this case
            invalid_any_of.msg = "Incorrect type, must represent any of: {}. " \
                                 "All missing from: {}" .format(list(option_any_of), dict(cstruct))
            raise invalid_any_of
        return merged_any_of


class NotKeywordSchema(KeywordMapper):
    def __init__(self):  # noqa: W0231
        raise NotImplementedError  # TODO


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
        keyword = schema_node.get_keyword_name()
        one_of_obj = {
            keyword: []
        }

        for item_schema in schema_node.get_keyword_items():
            item_obj = _make_node_instance(item_schema)
            # shortcut definition of oneOf/allOf mix, see OneOfKeywordSchema docstring)
            # (eg: other schema fields always needed regardless of additional ones by oneOf)
            if len(getattr(schema_node, "children", [])):
                obj_no_one_of = item_obj.clone()  # type: OneOfKeywordSchema
                # un-specialize the keyword schema to base schema (otherwise we recurse)
                # other item can only be an object, otherwise something wrong happened
                if isinstance(obj_no_one_of, colander.MappingSchema):
                    obj_no_one_of = colander.MappingSchema(obj_no_one_of)
                else:
                    raise ConversionTypeError(
                        "Unknown base type to convert oneOf schema item: {}".format(type(obj_no_one_of)))
                all_of = AllOfKeywordSchema(_all_of=[obj_no_one_of, item_obj])
                obj_converted = self.dispatcher(all_of)
            else:
                obj_converted = self.dispatcher(item_obj)
            one_of_obj[keyword].append(obj_converted)

        return one_of_obj


class AllOfKeywordTypeConverter(KeywordTypeConverter):
    """Object converter that generates the ``allOf`` keyword definition."""


class AnyOfKeywordTypeConverter(KeywordTypeConverter):
    """Object converter that generates the ``anyOf`` keyword definition."""


class NotKeywordTypeConverter(KeywordTypeConverter):
    """Object converter that generates the ``not`` keyword definition."""


class VariableObjectTypeConverter(ObjectTypeConverter):
    """
    Updates the mapping object's ``additionalProperties`` for each ``properties``
    that a marked as :class:`VariableSchemaNode`.
    """
    def convert_type(self, schema_node):
        converted = super(VariableObjectTypeConverter, self).convert_type(schema_node)
        converted.setdefault("additionalProperties", {})
        if self.openapi_spec == 3:
            for sub_node in schema_node.children:
                if VariableSchemaNode.is_variable(sub_node):
                    converted["additionalProperties"].update(
                        {sub_node.name: converted["properties"].pop(sub_node.name)}
                    )
                    if sub_node.name in converted.get("required", []):
                        converted["required"].remove(sub_node.name)
        return converted


# TODO: replace directly in original cornice_swagger
#  (see: https://github.com/Cornices/cornice.ext.swagger/issues/133)
class CustomTypeConversionDispatcher(TypeConversionDispatcher):
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
        # NOTE: we enforce some items to inherit variable functionality,
        #   when merging in original cornice_swagger, it should be the 'default' behaviour of object converter
        custom_converters = custom_converters or {}
        extra_converters = {
            colander.Mapping: VariableObjectTypeConverter
        }
        custom_converters.update(extra_converters)

        custom_converters.update(self.keyword_converters)
        super(CustomTypeConversionDispatcher, self).__init__(custom_converters, default_converter)

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
            # (eg: MappingSchema(validator=colander.OneOf[Obj1, Obj2]) )
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
                if self.default_converter:
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

        return converted


def _dict_nested_contained(parent, child):
    """Tests that a dict is 'contained' within a parent dict

    .. code-block:: python

        >>> parent = {"other": 2, "test": [{"inside": 1, "other_nested": 2}]}
        >>> child = {"test": [{"inside": 1}]}
        >>> _dict_nested_contained(parent, child)
        True

    :param dict parent: The dict that could contain the child
    :param dict child: The dict that could be nested inside the parent
    """

    if not isinstance(parent, dict) or not isinstance(child, dict):
        return parent == child

    for key, value in child.items():
        if key not in parent:
            return False
        if isinstance(value, list):
            if len(parent[key]) != len(value):
                return False
            return all(_dict_nested_contained(p, c) for p, c in zip(parent[key], value))
        return _dict_nested_contained(parent[key], value)

    return True


def _make_node_instance(schema_node_or_class):
    """Obtains a schema node instance in case it was specified only by type reference.

    This helps being more permissive of provided definitions while handling situations
    like presented in the example below::

        class Map(OneOfMappingSchema):
            # uses types instead of instances like 'SubMap1([...])' and 'SubMap2([...])'
            _one_of = (SubMap1, SubMap2)

    """
    if isinstance(schema_node_or_class, colander._SchemaMeta):  # noqa: W0212
        schema_node_or_class = schema_node_or_class()
    if not isinstance(schema_node_or_class, colander.SchemaNode):
        raise ConversionTypeError(
            "Invalid item should be a SchemaNode, got: {!s}".format(type(schema_node_or_class)))
    return schema_node_or_class
