"""
Factories to create storage backends.
"""

# Factories
from weaver.database.base import get_database_factory
# Interfaces
from weaver.adapter.base import AdapterInterface
from weaver.store.base import (
    ServiceStore,
    ProcessStore,
    JobStore,
    QuoteStore,
    BillStore,
)
from typing import AnyStr, Dict
from pyramid.registry import Registry
from pyramid.config import Configurator


class DefaultAdapter(AdapterInterface):
    def describe_adapter(self):
        # type: (...) -> Dict[AnyStr, AnyStr]
        __doc__ = super(DefaultAdapter, self).__doc__
        from weaver.__meta__ import __version__
        return {"name": "default", "version": str(__version__)}

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

    def configurator_factory(self, settings):
        # type: (Dict[AnyStr, AnyStr]) -> Configurator
        __doc__ = super(DefaultAdapter, self).__doc__
        return Configurator(settings=settings)
