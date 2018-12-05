import colander
from cornice_swagger.converters import schema
from cornice_swagger.converters.exceptions import NoSuchConverter


class OneOfMappingSchema(colander.MappingSchema):

    def __init__(self, *args, **kwargs):
        super(OneOfMappingSchema, self).__init__(*args, **kwargs)
        if not hasattr(self, '_one_of'):
            raise TypeError("Type '{}' must define '_one_of' element.".format(self))
        if not hasattr(self._one_of, '__iter__') or not len(self._one_of):
            raise ValueError("Element '_one_of' of '{}' must be an iterable of at least 1 value.".format(self))

    def __str__(self):
        return self.__name__

    def deserialize_one_of(self, cstruct):
        # test each possible case, return all corresponding errors if
        # none of the '_one_of' possibilities is valid including all sub-dependencies
        invalid_one_of = dict()
        for c in self._one_of:
            try:
                return c().deserialize(cstruct)
            except colander.Invalid as invalid:
                invalid_one_of.update({type(invalid.node).__name__: str(invalid)})
                pass
        else:
            message = 'Incorrect type, must be one of: {}. Errors for each case: {}' \
                      .format(list(invalid_one_of), invalid_one_of)
            raise colander.Invalid(node=self, msg=message)

    def deserialize(self, cstruct):
        result = self.deserialize_one_of(cstruct)
        mapping_data = super(OneOfMappingSchema, self).deserialize(cstruct)

        result.update(mapping_data)
        return result


class CustomTypeConversionDispatcher(object):

    def __init__(self, custom_converters={}, default_converter=None):

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

        self.converters.update(custom_converters)
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
