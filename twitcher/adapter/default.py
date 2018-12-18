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
from twitcher.owssecurity import OWSSecurity, OWSSecurityInterface
from typing import AnyStr, Dict
from pyramid.registry import Registry
from pyramid.config import Configurator


class DefaultAdapter(AdapterInterface):
    def describe_adapter(self):
        # type: (...) -> Dict[AnyStr, AnyStr]
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.__meta__ import __version__
        return {"name": "default", "version": str(__version__)}

    def tokenstore_factory(self, registry):
        # type: (Registry) -> AccessTokenStore
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(AccessTokenStore.type, registry=registry)

    def servicestore_factory(self, registry):
        # type: (Registry) -> ServiceStore
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(ServiceStore.type, registry=registry)

    def processstore_factory(self, registry):
        # type: (Registry) -> ProcessStore
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(ProcessStore.type, registry=registry)

    def jobstore_factory(self, registry):
        # type: (Registry) -> JobStore
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(JobStore.type, registry=registry)

    def quotestore_factory(self, registry):
        # type: (Registry) -> QuoteStore
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(QuoteStore.type, registry=registry)

    def billstore_factory(self, registry):
        # type: (Registry) -> BillStore
        __doc__ = super(DefaultAdapter, self).__doc__
        db = get_database_factory(registry)
        return db.get_store(BillStore.type, registry=registry)

    def owssecurity_factory(self, registry):
        # type: (Registry) -> OWSSecurityInterface
        __doc__ = super(DefaultAdapter, self).__doc__
        token_store = self.tokenstore_factory(registry)
        service_store = self.servicestore_factory(registry)
        return OWSSecurity(token_store, service_store)

    def configurator_factory(self, settings):
        # type: (Dict[AnyStr, AnyStr]) -> Configurator
        __doc__ = super(DefaultAdapter, self).__doc__
        return Configurator(settings=settings)

    def owsproxy_config(self, settings, config):
        # type: (Dict[AnyStr, AnyStr], Configurator) -> None
        __doc__ = super(DefaultAdapter, self).__doc__
        from twitcher.owsproxy import owsproxy_defaultconfig
        owsproxy_defaultconfig(settings, config)
