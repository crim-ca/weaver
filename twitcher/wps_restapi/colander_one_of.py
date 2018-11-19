import colander
from cornice_swagger.converters import schema
from cornice_swagger.converters.exceptions import NoSuchConverter


class OneOfMappingSchema(colander.MappingSchema):
    def deserialize_one_of(self, cstruct):
        if cstruct is colander.null:
            return colander.null
        if not hasattr(self, "_one_of"):
            return {}

        for c in self._one_of:
            try:
                return c().deserialize(cstruct)
            except colander.Invalid:
                pass
        else:
            message = 'Incorrect type, must be one of: ' + self._schema_names()
            raise colander.Invalid(message)

    def deserialize(self, cstruct):
        if cstruct is colander.null:
            return colander.null

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
