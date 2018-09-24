class AdapterInterface(object):
    """
    Common interface allowing some functionalities overriding using an adapter
    """

    def describe_adapter(self):
        """
        Returns a dictionary describing the adapter implementation.
        """
        raise NotImplementedError

    def servicestore_factory(self, registry):
        """
        Returns the 'servicestore' implementation of the adapter.
        """
        raise NotImplementedError

    def jobstore_factory(self, registry):
        """
        Returns the 'jobstore' implementation of the adapter.
        """
        raise NotImplementedError

    def quotestore_factory(self, registry):
        """
        Returns the 'quotestore' implementation of the adapter.
        """
        raise NotImplementedError

    def billstore_factory(self, registry):
        """
        Returns the 'billstore' implementation of the adapter.
        """
        raise NotImplementedError

    def owssecurity_factory(self, registry):
        """
        Returns the 'owssecurity' implementation of the adapter.
        """
        raise NotImplementedError

    def configurator_factory(self, settings):
        """
        Returns the 'configurator' implementation of the adapter.
        """
        raise NotImplementedError

    def owsproxy_config(self, settings, config):
        """
        Returns the 'owsproxy' implementation of the adapter.
        """
        raise NotImplementedError

    def processstore_factory(self, registry):
        raise NotImplementedError
