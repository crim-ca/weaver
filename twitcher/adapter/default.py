"""
Factories to create storage backends.
"""

# Factories
from twitcher.database.base import get_database_factory
# Interfaces
from twitcher.adapter.base import AdapterInterface
from twitcher.store.base import (
    AccessTokenStore,
    ServiceStore,
    ProcessStore,
    JobStore,
    QuoteStore,
    BillStore,
)
from twitcher.owssecurity import OWSSecurity


class DefaultAdapter(AdapterInterface):
    def describe_adapter(self):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.__meta__ import __version__
        return {"name": "default", "version": str(__version__)}

    def tokenstore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(AccessTokenStore.type)

    def servicestore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(ServiceStore.type)

    def processstore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(ProcessStore.type)

    def jobstore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(JobStore.type)

    def quotestore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(QuoteStore.type)

    def billstore_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(BillStore.type)

    def owssecurity_factory(self, registry):
        __doc__ = super(DefaultAdapter, self).__doc__
        token_store = self.tokenstore_factory(registry)
        service_store = self.servicestore_factory(registry)
        return OWSSecurity(token_store, service_store)

    def configurator_factory(self, settings):
        __doc__ = super(DefaultAdapter, self).__doc__
        from pyramid.config import Configurator
        return Configurator(settings=settings)

    def owsproxy_config(self, settings, config):
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.owsproxy import owsproxy_defaultconfig
        owsproxy_defaultconfig(settings, config)
