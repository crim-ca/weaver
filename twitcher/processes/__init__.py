from .wps_hello import Hello
from .wps_package import Package


default_processes = [
    Hello()
]

process_mapping = {
    'hello': Hello,
    'application': Package,
    'workflow': Package
}


def includeme(config):
    pass
    #config.registry.processes = processstore_defaultfactory(config.registry, init_processes=default_processes)
