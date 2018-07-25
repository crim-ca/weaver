from twitcher.adapter.base import AdapterInterface


class DefaultAdapter(AdapterInterface):

    def servicestore_factory(self, registry, database=None):
        from twitcher.store import servicestore_defaultfactory
        return servicestore_defaultfactory(registry, database)

    def owssecurity_factory(self, registry):
        from twitcher.owssecurity import owssecurity_defaultfactory
        return owssecurity_defaultfactory(registry)

    def configurator_factory(self, settings):
        from pyramid.config import Configurator
        return Configurator(settings=settings)

    def owsproxy_config(self, settings, config):
        from twitcher.owsproxy import owsproxy_defaultconfig
        owsproxy_defaultconfig(settings, config)
