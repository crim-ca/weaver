import logging
from typing import Dict, AnyStr
from twitcher.adapter.default import DefaultAdapter, AdapterInterface

LOGGER = logging.getLogger("TWITCHER")

TWITCHER_ADAPTER_DEFAULT = 'default'


def import_adapter(name):
    components = name.split('.')
    mod_name = components[0]
    mod = __import__(mod_name)
    for comp in components[1:]:
        if not hasattr(mod, comp):
            mod_name = '{mod}.{sub}'.format(mod=mod_name, sub=comp)
            mod = __import__(mod_name, fromlist=[mod_name])
            continue
        mod = getattr(mod, comp)
    return mod


def adapter_factory(settings):
    # type: (Dict[AnyStr, AnyStr]) -> AdapterInterface
    """
    Creates an adapter with the interface of :class:`twitcher.adapter.AdapterInterface`.
    By default the twitcher.adapter.DefaultAdapter implementation will be used.

    :return: An instance of :class:`twitcher.adapter.AdapterInterface`.
    """
    if str(settings.get('twitcher.adapter', TWITCHER_ADAPTER_DEFAULT)).lower() != TWITCHER_ADAPTER_DEFAULT:
        try:
            adapter_class = import_adapter(settings.get('twitcher.adapter'))
            LOGGER.info('Using adapter: {!r}'.format(adapter_class))
            return adapter_class()
        except Exception as e:
            LOGGER.error('Adapter raised an exception while instantiating : {!r}'.format(e))
            raise
    return DefaultAdapter()


def get_adapter_store_factory(adapter, store_name, registry):
    try:
        store = getattr(adapter, store_name)
        return store(registry)
    except NotImplementedError:
        if isinstance(adapter, DefaultAdapter):
            LOGGER.exception("DefaultAdapter doesn't implement `{1!r}`, no way to recover.".format(adapter, store_name))
            raise
        LOGGER.warn("Adapter `{0!r}` doesn't implement `{1!r}`, falling back to `DefaultAdapter` implementation."
                    .format(adapter, store_name))
        return get_adapter_store_factory(DefaultAdapter(), store_name, registry)
    except Exception as e:
        LOGGER.error("Adapter `{0!r}` raised an exception while instantiating `{1!r}` : `{2!r}`"
                     .format(adapter, store_name, e))
        raise


def processstore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'processstore_factory', registry)


def servicestore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'servicestore_factory', registry)


def jobstore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'jobstore_factory', registry)


def quotestore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'quotestore_factory', registry)


def billstore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'billstore_factory', registry)


def owssecurity_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'owssecurity_factory', registry)
