from weaver.processes.types import PROCESS_APPLICATION, PROCESS_BUILTIN, PROCESS_TEST, PROCESS_WORKFLOW
from weaver.processes.wps_default import HelloWPS
from weaver.processes.wps_package import WpsPackage
from weaver.processes.wps_testing import WpsTestProcess

default_processes = [
    HelloWPS()
]

process_mapping = {
    HelloWPS.identifier:    HelloWPS,             # noqa: E241
    PROCESS_TEST:        WpsTestProcess,    # noqa: E241
    PROCESS_APPLICATION: WpsPackage,        # noqa: E241
    PROCESS_WORKFLOW:    WpsPackage,        # noqa: E241
    PROCESS_BUILTIN:     WpsPackage,        # noqa: E241
}


# noinspection PyUnusedLocal
def includeme(config):
    pass
