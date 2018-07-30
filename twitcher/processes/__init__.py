from .wps_hello import Hello
from twitcher.store import processstore_defaultfactory

default_processes = [
    Hello()
]


def includeme(config):
    config.registry.processes = processstore_defaultfactory(config.registry, init_processes=default_processes)
