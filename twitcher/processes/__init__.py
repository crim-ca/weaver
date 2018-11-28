from twitcher.processes.wps_default import Hello
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.processes.wps_package import WpsPackage
from twitcher.processes.types import PROCESS_TEST, PROCESS_APPLICATION, PROCESS_WORKFLOW


default_processes = [
    Hello()
]

process_mapping = {
    'hello': Hello,
    PROCESS_TEST:        WpsTestProcess,
    PROCESS_APPLICATION: WpsPackage,
    PROCESS_WORKFLOW:    WpsPackage,
}


# noinspection PyUnusedLocal
def includeme(config):
    pass
