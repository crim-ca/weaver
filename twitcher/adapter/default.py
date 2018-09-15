from twitcher.adapter.base import AdapterInterface


class DefaultAdapter(AdapterInterface):
    def describe_adapter(self):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher import __version__
        return {"name": "default", "version": str(__version__)}

    def servicestore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.store import servicestore_defaultfactory
        return servicestore_defaultfactory(registry)

    def jobstore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.store import jobstore_defaultfactory
        return jobstore_defaultfactory(registry)

    def quotestore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.store import quotestore_defaultfactory
        return quotestore_defaultfactory(registry)

    def billstore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.store import billstore_defaultfactory
        return billstore_defaultfactory(registry)

    def owssecurity_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.owssecurity import owssecurity_defaultfactory
        return owssecurity_defaultfactory(registry)

    def configurator_factory(self, settings):
        __doc__ = super(DefaultAdapter, self).__doc__
        from pyramid.config import Configurator
        return Configurator(settings=settings)

    def owsproxy_config(self, settings, config):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.owsproxy import owsproxy_defaultconfig
        owsproxy_defaultconfig(settings, config)

    def processstore_factory(self, registry):
        from twitcher.store import processstore_defaultfactory
        return processstore_defaultfactory(registry)
