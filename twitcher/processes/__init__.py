from .wps_hello import Hello
from .wps_workflow import Workflow


default_processes = [
    Hello()
]

process_mapping = {
    'hello': Hello,
    'workflow': Workflow
}


def includeme(config):
    pass
    #config.registry.processes = processstore_defaultfactory(config.registry, init_processes=default_processes)
