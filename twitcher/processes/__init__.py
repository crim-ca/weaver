from twitcher.processes.wps_default import Hello
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.processes.wps_package import Package
from twitcher.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW


default_processes = [
    Hello()
]

process_mapping = {
    'hello': Hello,
    'test': WpsTestProcess,
    PROCESS_APPLICATION: Package,
    PROCESS_WORKFLOW: Package
}


def includeme(config):
    pass
