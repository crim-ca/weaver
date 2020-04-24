from typing import TYPE_CHECKING

import colander
from cornice_swagger.converters import schema
from cornice_swagger.converters.exceptions import NoSuchConverter

if TYPE_CHECKING:
    from typing import Iterable


class DropableNoneSchema(colander.SchemaNode):
    """
    Drops the underlying schema node if ``missing=drop`` was specified and that the value representing it is ``None``.

    Original behaviour of schema classes that can have children nodes such as :class:`colander.MappingSchema` and
    :class:`colander.SequenceSchema` are to drop the sub-node only if its value is resolved as :class:`colander.null`
    or :class:`colander.drop`. This results in "missing" definitions replaced by ``None`` in many implementations to
    raise :py:exc:`colander.Invalid` during deserialization. Inheriting this class in a schema definition
    will handle this situation automatically.

    Required schemas (without ``missing=drop``, i.e.: :class:`colander.required`) will still raise for undefined nodes.

    The following snippet shows the result that can be achieved using this schema class:

    .. code-block:: python

        class SchemaA(DropableNoneSchema, MappingSchema):
            field = SchemaNode(String())

        class SchemaB(MappingSchema):
            s1 = SchemaA(missing=drop)   # optional
            s2 = SchemaA()               # required

        SchemaB().deserialize({"s1": None, "s2": {"field": "ok"}})
        # >> {'s2': {'field': 'ok'}}

    .. seealso:
        - https://github.com/Pylons/colander/issues/276
        - https://github.com/Pylons/colander/issues/299
    """
    @staticmethod
    def schema_type():
        raise NotImplementedError

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        if self.default is colander.null and self.missing is colander.drop and cstruct is None:
            return colander.drop
        return super(DropableNoneSchema, self).deserialize(cstruct)


class VariableMappingSchema(colander.Mapping):
    """
    Mapping schema that will allow **any** *unknown* field to remain present in the resulting deserialization.

    This definition is useful for defining a dictionary where some field names are not known in advance.
    Other fields that are explicitly specified with sub-schema nodes will be validated as per usual behaviour.
    """
    def __new__(cls, *args, **kwargs):
        return colander.SchemaNode(colander.Mapping(unknown="preserve"), *args, **kwargs)


class SchemaNodeDefault(colander.SchemaNode):
    """
    If ``default`` keyword is provided during :class:`colander.SchemaNode` creation, overrides the
    returned value by this default if missing from the structure during :func:`deserialize` call.

    Original behaviour was to drop the missing value instead of replacing by the default.
    Executes all other :class:`colander.SchemaNode` operations normally.
    """
    @staticmethod
    def schema_type():
        raise NotImplementedError

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        result = super(SchemaNodeDefault, self).deserialize(cstruct)
        if not isinstance(self.default, type(colander.null)) and result is colander.drop:
            result = self.default
        return result


class OneOfCaseInsensitive(colander.OneOf):
    """
    Validator that ensures the given value matches one of the available choices, but allowing case insensitve values.
    """
    def __call__(self, node, value):
        if str(value).lower() not in (choice.lower() for choice in self.choices):
            return super(OneOfCaseInsensitive, self).__call__(node, value)


class OneOfMappingSchema(colander.MappingSchema):
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

        class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
            _one_of = (Variant1, Variant2)
            [...alternatively, field required by all variants here...]

    In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
    variants' validator completely succeed, and will fail if every variant fails validation execution.

    .. warning::
        Because the validation process requires only at least one of the variants to succeed, it is important to insert
        more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
        defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
        succeed regardless of following variants. This would have as side effect to never validate the other variants
        explicitly for specific field types and formats since the first option would always consist as a valid input
        fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).
    """
    @staticmethod
    def _one_of():
        # type: () -> Iterable[colander._SchemaMeta]
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        super(OneOfMappingSchema, self).__init__(*args, **kwargs)
        if not hasattr(self, "_one_of"):
            raise TypeError("Type '{}' must define '_one_of' element.".format(self))
        if not hasattr(self._one_of, "__iter__") or not len(self._one_of):  # noqa
            raise ValueError("Element '_one_of' of '{}' must be an iterable of at least 1 value.".format(self))

    def deserialize_one_of(self, cstruct):
        # test each possible case, return all corresponding errors if
        # none of the '_one_of' possibilities is valid including all sub-dependencies
        invalid_one_of = dict()
        valid_one_of = []
        for schema_class in self._one_of:  # noqa
            try:
                # instantiate the class if specified with simple reference, other use pre-instantiated schema object
                if isinstance(schema_class, colander._SchemaMeta):  # noqa: W0212
                    schema_class = schema_class()
                valid_one_of.append(schema_class.deserialize(cstruct))
            except colander.Invalid as invalid:
                invalid_one_of.update({type(invalid.node).__name__: str(invalid)})

        if valid_one_of:
            # Try to return the format which didn't change the input data
            for valid in valid_one_of:
                if _dict_nested_equals(cstruct, valid):
                    return valid
            # If that fails, return the first valid deserialization
            return valid_one_of[0]

        message = "Incorrect type, must be one of: {}. Errors for each case: {}" \
                  .format(list(invalid_one_of), invalid_one_of)
        raise colander.Invalid(node=self, msg=message)

    # pylint: disable=W0222,signature-differs
    def deserialize(self, cstruct):
        result = self.deserialize_one_of(cstruct)
        if isinstance(result, dict):
            mapping_data = super(OneOfMappingSchema, self).deserialize(cstruct)
            result.update(mapping_data)
        return result


class CustomTypeConversionDispatcher(object):

    def __init__(self, custom_converters=None, default_converter=None):

        self.converters = {
            colander.Boolean: schema.BooleanTypeConverter,
            colander.Date: schema.DateTypeConverter,
            colander.DateTime: schema.DateTimeTypeConverter,
            colander.Float: schema.NumberTypeConverter,
            colander.Integer: schema.IntegerTypeConverter,
            colander.Mapping: schema.ObjectTypeConverter,
            colander.Sequence: schema.ArrayTypeConverter,
            colander.String: schema.StringTypeConverter,
            colander.Time: schema.TimeTypeConverter,
        }

        self.converters_base_classes = {
            OneOfMappingSchema: schema.ObjectTypeConverter,
        }

        self.converters.update(custom_converters or {})
        self.default_converter = default_converter

    def __call__(self, schema_node):
        schema_instance = schema_node.typ
        schema_type = type(schema_instance)

        converter_class = self.converters.get(schema_type)
        if converter_class is None:
            for base in self.converters_base_classes:
                if isinstance(schema_instance, base):
                    converter_class = self.converters_base_classes[base]
                    break
            else:
                if self.default_converter:
                    converter_class = self.default_converter
                else:
                    raise NoSuchConverter

        converter = converter_class(self)
        converted = converter(schema_node)

        return converted


def _dict_nested_equals(parent, child):
    """Tests that a dict is 'contained' within a parent dict

    >>> parent = {"other": 2, "test": [{"inside": 1, "other_nested": 2}]}
    >>> child = {"test": [{"inside": 1}]}
    >>> _dict_nested_equals(parent, child)
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
            return all(_dict_nested_equals(p, c) for p, c in zip(parent[key], value))
        return _dict_nested_equals(parent[key], value)

    return True
