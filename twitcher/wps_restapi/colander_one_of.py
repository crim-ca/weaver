import colander
from cornice_swagger.converters import schema
from cornice_swagger.converters.exceptions import NoSuchConverter


class OneOfType(colander.SchemaType):
    _one_of = ()

    def _schema_names(self):
        return ", ".join(c.__name__ for c in self._one_of)

    def serialize(self, node, appstruct):
        if appstruct is colander.null:
            return colander.null

        for c in self._one_of:
            try:
                return c().serialize(appstruct)
            except colander.Invalid:
                pass
        else:
            message = 'Incorrect type, must be one of: ' + self._schema_names()
            raise colander.Invalid(node, message)

    def deserialize(self, node, cstruct):
        if cstruct is colander.null:
            return colander.null

        for c in self._one_of:
            try:
                return c().deserialize(cstruct)
            except colander.Invalid:
                pass
        else:
            message = 'Incorrect type, must be one of: ' + self._schema_names()
            raise colander.Invalid(node, message)


class OneOfMappingType(OneOfType):
    _mapping = None

    def __init__(self, unknown='ignore'):
        self.unknown = unknown

    @property
    def unknown(self):
        return self._unknown

    @unknown.setter
    def unknown(self, value):
        if value not in ('ignore', 'raise', 'preserve'):
            raise ValueError(
                'unknown attribute must be one of "ignore", "raise", '
                'or "preserve"')
        self._unknown = value

    def deserialize(self, node, cstruct):
        one_of_result = super(OneOfMappingType, self).deserialize(node, cstruct)
        one_of_result.update(self._mapping().deserialize(cstruct))
        return one_of_result


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
            OneOfMappingType: schema.ObjectTypeConverter,
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
