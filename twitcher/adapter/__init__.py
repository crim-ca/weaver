import logging
from twitcher.adapter.default import DefaultAdapter

LOGGER = logging.getLogger("TWITCHER")


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
    """
    Creates an adapter with the interface of :class:`twitcher.adapter.AdapterInterface`.
    By default the twitcher.adapter.DefaultAdapter implementation will be used.

    :return: An instance of :class:`twitcher.adapter.AdapterInterface`.
    """
    if settings.get('twitcher.adapter', 'default') != 'default':
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
    except AttributeError:
        LOGGER.warn("Adapter `{0!r}` doesn't implement `{1!r}`, falling back to `DefaultAdapter` implementation."
                    .format(adapter, store_name))
        adapter = DefaultAdapter()
        store = getattr(adapter, store_name)
    except Exception as e:
        LOGGER.error("Adapter `{0!r}` raised an exception while getting `{1!r}` : `{2!r}`"
                     .format(adapter, store_name, e))
        raise
    try:
        return store(registry)
    except Exception as e:
        LOGGER.error("Adapter `{0!r}` raised an exception while instantiating `{1!r}` : {2!r}"
                     .format(adapter, store_name, e))
        raise


def servicestore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'servicestore_factory', registry)


def jobstore_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'jobstore_factory', registry)


def owssecurity_factory(registry):
    adapter = adapter_factory(registry.settings)
    return get_adapter_store_factory(adapter, 'owssecurity_factory', registry)
