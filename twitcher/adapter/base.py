class AdapterInterface(object):
    """
    Common interface allowing some functionalities overriding using an adapter
    """

    def servicestore_factory(self, registry, database=None, headers=None):
        """
        """
        raise NotImplementedError

    def owssecurity_factory(self, registry):
        raise NotImplementedError

    def configurator_factory(self, settings):
        raise NotImplementedError

    def owsproxy_config(self, settings, config):
        raise NotImplementedError
