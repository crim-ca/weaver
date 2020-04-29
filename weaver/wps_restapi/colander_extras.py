import inspect
from typing import TYPE_CHECKING
from abc import abstractmethod

import colander
from cornice_swagger.converters import schema
from cornice_swagger.converters.exceptions import ConversionError, NoSuchConverter
from cornice_swagger.converters.schema import TypeConversionDispatcher

if TYPE_CHECKING:
    from typing import Iterable


class ConversionTypeError(ConversionError, TypeError):
    """Conversion error due to invalid type."""


class ConversionValueError(ConversionError, ValueError):
    """Conversion error due to invalid value."""


class DropableSchemaNode(colander.SchemaNode):
    """
    Drops the underlying schema node if ``missing=drop`` was specified and that the value
    representing it is ``None``.

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
        if self.default is colander.null and self.missing is colander.drop and cstruct is None:
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
        result = super(DefaultSchemaNode, self).deserialize(cstruct)
        if not isinstance(self.default, type(colander.null)) and result is colander.drop:
            result = self.default
        return result


class ExtendedSchemaNode(DefaultSchemaNode, DropableSchemaNode):
    """
    Combines :class:`DefaultSchemaNode` and :class:`DropableSchemaNode` extensions so that
    ``default`` keyword is used first to resolve a missing field value during :meth:`deserialize`
    call, and then removes the node completely if no ``default`` was provided.

    .. seealso::
        - :class:`ExtendedMappingSchema`
        - :class:`ExtendedSequenceSchema`
    """
    @staticmethod
    def schema_type():
        raise NotImplementedError("Using SchemaNode for a field requires 'schema_type' definition.")

    def __int__(self, *args, **kwargs):
        colander.SchemaNode.__init__(*args, **kwargs)


class VariableMappingSchema(colander.Mapping):
    """
    Mapping schema that will allow **any** *unknown* field to remain present in the resulting deserialization.

    This definition is useful for defining a dictionary where some field names are not known in advance.
    Other fields that are explicitly specified with sub-schema nodes will be validated as per usual behaviour.

    When doing schema deserialization to validate it, unknown keys would normally be dropped without this class.

    Example::

        class AnyKeyObject(VariableMappingSchema):
            known_key = SchemaNode(String())

        AnyKeyObject().deserialize({"unknown": "kept", "known_key": "requirement"}))
        # result: dictionary returned as is instead of removing 'unknown' entry
        #         'known_key' is still looked for to validate the schema

    """
    def __new__(cls, *args, **kwargs):
        return colander.SchemaNode(colander.Mapping(unknown="preserve"), *args, **kwargs)


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


class ExtendedMappingSchema(DefaultSchemaNode, DropableSchemaNode, colander.MappingSchema):
    """
    Combines :class:`DefaultMappingSchema` and :class:`DropableMappingSchema` extensions so that
    ``default`` keyword is used first to resolve a missing object during :meth:`deserialize`
    call, and then removes the node completely if no ``default`` was provided.

    .. seealso::
        - :class:`ExtendedSequenceSchema`
        - :class:`ExtendedMappingSchema`
    """
    schema_type = colander.MappingSchema.schema_type


class OneOfCaseInsensitive(colander.OneOf):
    """
    Validator that ensures the given value matches one of the available choices, but allowing case insensitve values.
    """
    def __call__(self, node, value):
        if str(value).lower() not in (choice.lower() for choice in self.choices):
            return super(OneOfCaseInsensitive, self).__call__(node, value)


class KeywordMapper(colander.MappingSchema):
    """
    Allows specifying multiple combinations of schemas variants for an underlying schema definition.

    Each implementer must provide the corresponding ``keyword`` it defines amongst `OpenAPI` specification keywords.
    """
    _keywords = frozenset(['_one_of', '_all_of', '_any_of', '_not'])
    _keyword_map = {_kw: _kw.replace('_of', 'Of').replace('_', '') for _kw in _keywords}  # kw->name
    _keyword_inv = {_kn: _kw for _kw, _kn in _keyword_map.items()}                        # name->kw
    _keyword = None  # type: str

    def __init__(self, *args, **kwargs):
        super(KeywordMapper, self).__init__(*args, **kwargs)
        if not hasattr(self, self._keyword):
            # try retrieving from a kwarg definition (either as literal keyword or pretty name)
            if kwargs:
                maybe_kwargs = [_kw for _kw in kwargs
                                if _kw in self._keyword_map or _kw in self._keyword_inv]
                if len(maybe_kwargs) == 1:
                    self._keyword = self._keyword_inv.get(maybe_kwargs[0], maybe_kwargs[0])
                    setattr(self, self._keyword, kwargs.get(maybe_kwargs[0]))
            if not self._keyword:
                raise ConversionTypeError("Type '{}' must define a keyword element.".format(self))
        self._validate_keyword()

    @classmethod
    def get_keyword_name(cls):
        return cls._keyword_map[cls._keyword]

    def get_keyword_items(self):
        return getattr(self, self._keyword)

    def _validate_keyword(self):
        kw_items = self.get_keyword_items()
        if not hasattr(kw_items, '__iter__') or not len(kw_items):  # noqa
            raise ConversionValueError("Element '{}' of '{!s}' must be iterable with at least 1 value. "
                                       "Instead it was '{!s}'".format(self._keyword, self, kw_items))
        total = 0
        for kw in self._keywords:
            if hasattr(self, kw):
                total += 1
            if total > 1:
                raise ConversionTypeError("Multiple keywords '{}' not permitted for '{!s}'".format(
                    list(self._keywords), self
                ))
        if not total == 1:
            raise ConversionTypeError("Missing one of keywords '{}' for '{!s}'".format(
                list(self._keywords), self
            ))

    @abstractmethod
    def _deserialize_keyword(self, cstruct):
        raise NotImplementedError

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
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
        When calling :meth:`deserialize`, because the validation process requires only at least
        one of the variants to succeed to consider the whole object to evaluate as valid, it is
        important to insert *more permissive* validators later in the ``_one_of`` iterator (or
        ``validator`` keyword). For example, having a variant with all fields defined as optional
        (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
        succeed regardless of following variants. This would have as side effect to never validate
        the other variants explicitly for specific field types and formats since the first option
        would always consist as a valid input fulfilling the first specified definition
        (ie: an empty ``{}`` schema with all fields missing).

    .. seealso::
        - :class:`AllOfKeywordSchema`
        - :class:`AnyOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword = '_one_of'

    @classmethod
    @abstractmethod
    def _one_of(cls):
        # type: () -> Iterable[colander._SchemaMeta]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise ConversionTypeError("Missing '{}' keyword.".format(cls._keyword))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return all corresponding errors if
        none of the possibilities is valid including all sub-dependencies.
        """
        invalid_one_of = dict()
        valid_one_of = []
        for schema_class in self._one_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                valid_one_of.append(schema_class.deserialize(cstruct))
            except colander.Invalid as invalid:
                invalid_one_of.update({type(invalid.node).__name__: str(invalid)})

        if valid_one_of:
            # Try to return the format which didn't change the input data
            for valid in valid_one_of:
                if _dict_nested_contained(cstruct, valid):
                    return valid
            # If that fails, return the first valid deserialization
            return valid_one_of[0]

        message = "Incorrect type, must be one of: {}. Errors for each case: {}" \
                  .format(list(invalid_one_of), invalid_one_of)
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
    _keyword = '_all_of'

    @classmethod
    @abstractmethod
    def _all_of(cls):
        # type: () -> Iterable[colander._SchemaMeta]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise ConversionTypeError("Missing '{}' keyword.".format(cls._keyword))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return all corresponding errors if
        any of the possibilities is invalid.
        """
        required_all_of = dict()
        missing_all_of = dict()
        merged_all_of = dict()
        for schema_class in self._one_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                required_all_of.update({type(schema_class).__name__: str(schema_class)})
                merged_all_of.update({schema_class.deserialize(cstruct)})
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

    Contrary to :class:`OneOfKeywordSchema` that stops on the first validated schema, this
    definition will continue parsing all possibilities and apply validate sub-schemas on top
    of each other. Not all schemas have to be valid like in the case of :class:`AllOfKeywordSchema`
    to succeed, as long as at least one of them is valid.

    Example::

        .. todo:: example

    .. seealso::
        - :class:`OneOfKeywordSchema`
        - :class:`AllOfKeywordSchema`
        - :class:`NotKeywordSchema`
    """
    _keyword = '_any_of'

    @classmethod
    @abstractmethod
    def _any_of(cls):
        # type: () -> Iterable[colander._SchemaMeta]  # noqa: W0212
        """This must be overridden in the schema definition using it."""
        raise ConversionTypeError("Missing '{}' keyword.".format(cls._keyword))

    def _deserialize_keyword(self, cstruct):
        """
        Test each possible case, return if no corresponding schema was found.
        """
        option_any_of = dict()
        merged_any_of = dict()
        for schema_class in self._one_of:  # noqa
            try:
                schema_class = _make_node_instance(schema_class)
                # update items with new ones
                option_any_of.update({type(schema_class).__name__: str(schema_class)})
                merged_any_of.update({schema_class.deserialize(cstruct)})
            except colander.Invalid:
                pass

        if not merged_any_of:
            # nothing succeeded, the whole definition is invalid in this case
            message = "Incorrect type, must represent any of: {}. All missing from: {}" \
                .format(list(option_any_of), dict(cstruct))
            raise colander.Invalid(node=self, msg=message)

        return merged_any_of


class NotKeywordSchema(KeywordMapper):
    def __int__(self):
        raise NotImplementedError  # TODO


class KeywordTypeConverter(schema.TypeConverter):
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
            if len(getattr(schema_node, 'children', [])):
                obj_no_one_of = item_obj.clone()  # type: OneOfKeywordSchema
                # un-specialize the keyword schema to base schema (otherwise we recurse)
                if isinstance(obj_no_one_of, colander.MappingSchema):
                    obj_no_one_of = colander.MappingSchema(obj_no_one_of)
                elif isinstance(obj_no_one_of, colander.SequenceSchema):
                    obj_no_one_of = colander.SequenceSchema(obj_no_one_of)
                else:
                    raise ConversionTypeError(
                        'Unknown base type to convert oneOf schema item: {}'.format(type(obj_no_one_of)))
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


# TODO: replace directly in original
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

        custom_converters = custom_converters or {}
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
                    converted = self(keyword_schema)
                    return converted

        if converter_class is None:
            converter_class = self.converters.get(schema_type)
            if converter_class is None:
                if self.default_converter:
                    converter_class = self.default_converter
                else:
                    raise NoSuchConverter

        converter = converter_class(self)
        converted = converter(schema_node)

        return converted


def _dict_nested_contained(parent, child):
    """Tests that a dict is 'contained' within a parent dict

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
