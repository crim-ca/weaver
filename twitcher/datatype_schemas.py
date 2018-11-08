from twitcher.processes.wps_package import PACKAGE_ARRAY_MAX_SIZE


class DescriptionType(dict):
    """
    Base class for the descriptionType schema
    """

    def __init__(self, *args, **kwargs):
        super(DescriptionType, self).__init__(*args, **kwargs)
        # use both 'id' and 'identifier' to support any call (WPS and recurrent 'id')
        if 'id' not in self and 'identifier' not in self:
            raise TypeError("'id' OR 'identifier' is required")
        if 'id' not in self:
            self['id'] = self.pop('identifier')

    @property
    def id(self):
        return self['id']

    @property
    def identifier(self):
        return self.id

    def description(self):
        properties = [
            "id",
            "title",
            "abstract",
            "keywords",
            "owsContext",
            "metadata",
            "additionalParameters",
            "links",
        ]
        return {p: self[p] for p in properties if p in self}


class DataDescriptionType(DescriptionType):
    """
    Dictionary that contains a process description for db storage.
    It always has ``'identifier'`` and ``executeWPSEndpoint`` keys.
    """

    def __init__(self, *args, **kwargs):
        super(DataDescriptionType, self).__init__(*args, **kwargs)
        if 'formats' not in self:
            # raise TypeError("'formats' is required")
            # TODO: Temporary patch to avoid error with static wps process like hello
            self['formats'] = [{"mimeType": "text/plain",
                                "default": True}]
        if 'type' not in self:
            raise TypeError("'type' is required")

    @property
    def type(self):
        """The WPS IO type of this object (LiteralType,
        ComplexType, BoundingBox, etc."""
        return self.get("type")

    def data_description(self):
        description = self.description()
        properties = [
            "minOccurs",
            "maxOccurs",
            "formats",
        ]
        description.update({p: self[p] for p in properties if p in self})
        return description

    def inputTypeChoice(self):
        properties = [
            "literalDataDomains",  # literalInputType
            "supportedCRS"  # boundingBoxInputType
            # complexInputType not defined
        ]
        input_type_choice = {p: self[p] for p in properties if p in self}
        return input_type_choice

    def inputType(self):
        input_type = self.inputTypeChoice()
        input_type.update(self.data_description())
        return input_type

    @classmethod
    def from_wps_names(cls, io_data):
        """
        Transform input and output from owslib format to the RestAPI compliant schema
        :param io_data: input or output as json
        :return:
            """
        replace = {
            u"identifier": u"id",
            u"supported_formats": u"formats",
            u"mime_type": u"mimeType",
            u"min_occurs": u"minOccurs",
            u"max_occurs": u"maxOccurs",
        }
        remove = []
        add = {}
        replace_values = {
            PACKAGE_ARRAY_MAX_SIZE: "unbounded",
        }

        for k, v in replace.items():
            if k in io_data:
                io_data[v] = io_data.pop(k)
        for r in remove:
            io_data.pop(r, None)
        for k, v in add.items():
            io_data[k] = v

        for key, value in io_data.items():
            for old_value, new_value in replace_values.items():
                if value == old_value:
                    io_data[key] = new_value
            # also replace if the type of the value is a list of dicts
            if isinstance(value, list):
                for nested_item in value:
                    if isinstance(nested_item, dict):
                        for k, v in replace.items():
                            if k in nested_item:
                                nested_item[v] = nested_item.pop(k)
        return cls(**io_data)
