from weaver.processes.wps_default import Hello
from weaver.processes.wps_testing import WpsTestProcess
from weaver.processes.wps_package import WpsPackage
from weaver.processes.types import PROCESS_TEST, PROCESS_APPLICATION, PROCESS_WORKFLOW, PROCESS_BUILTIN


default_processes = [
    Hello()
]

process_mapping = {
    Hello.identifier:    Hello,             # noqa: E241
    PROCESS_TEST:        WpsTestProcess,    # noqa: E241
    PROCESS_APPLICATION: WpsPackage,        # noqa: E241
    PROCESS_WORKFLOW:    WpsPackage,        # noqa: E241
    PROCESS_BUILTIN:     WpsPackage,        # noqa: E241
}


# noinspection PyUnusedLocal
def includeme(config):
    pass
