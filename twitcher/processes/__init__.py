from .wps_hello import Hello
from .wps_package import Package
from .types import PROCESS_APPLICATION, PROCESS_WORKFLOW


default_processes = [
    Hello()
]

process_mapping = {
    'hello': Hello,
    PROCESS_APPLICATION: Package,
    PROCESS_WORKFLOW: Package
}


def includeme(config):
    pass
    #config.registry.processes = processstore_defaultfactory(config.registry, init_processes=default_processes)
