import logging
from twitcher.adapter.default import DefaultAdapter

LOGGER = logging.getLogger("TWITCHER")

def import_adapter(name):
    components = name.split('.')
    mod = __import__(components[0])
    for comp in components[1:]:
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
            return adapter_class()
        except Exception as e:
            LOGGER.warn('Adapter raise an exception will instanciating : {!r}'.format(e))
    return DefaultAdapter()


def servicestore_factory(registry, database=None, headers=None):
    return adapter_factory(registry.settings).servicestore_factory(registry, database, headers)

def owssecurity_factory(registry):
    return adapter_factory(registry.settings).owssecurity_factory(registry)