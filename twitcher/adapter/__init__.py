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


def servicestore_factory(registry, database=None):
    try:
        return adapter_factory(registry.settings).servicestore_factory(registry, database)
    except Exception as e:
        LOGGER.error('Adapter raised an exception while getting servicestore_factory : {!r}'.format(e))
        raise


def owssecurity_factory(registry):
    try:
        return adapter_factory(registry.settings).owssecurity_factory(registry)
    except Exception as e:
        LOGGER.error('Adapter raised an exception while getting owssecurity_factory : {!r}'.format(e))
        raise
