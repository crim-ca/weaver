import colander


class SchemaNodeDefault(colander.SchemaNode):
    """
    If `default` keyword is provided during `colander.SchemaNode` creation, overrides the returned value by this
    default if missing from the structure during `deserialize` call.

    Original behaviour was to drop the missing value instead of replacing by the default.
    Executes all other `colander.SchemaNode` operations normally.
    """
    def deserialize(self, cstruct):
        result = super(SchemaNodeDefault, self).deserialize(cstruct)
        if not isinstance(self.default, type(colander.null)) and result is colander.drop:
            result = self.default
        return result
