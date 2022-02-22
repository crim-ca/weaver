from typing import TYPE_CHECKING

from weaver.base import Constants


class ProcessType(Constants):
    APPLICATION = "application"     # CWL package referencing an application (eg: Docker)
    BUILTIN = "builtin"             # Local scripts builtin Weaver for basic operations
    TEST = "test"                   # Same as local WPS, but specifically for testing
    WORKFLOW = "workflow"           # CWL package chaining multiple other process-types
    WPS_LOCAL = "wps"               # Local PyWPS process definitions
    WPS_REMOTE = "wps-remote"       # Remote WPS provider references (once instantiated from Service definition)

    @staticmethod
    def is_wps(process_type):
        # type: (AnyProcessType) -> bool
        return isinstance(process_type, str) and process_type.lower() in [ProcessType.WPS_LOCAL, ProcessType.WPS_REMOTE]


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyProcessType = Literal[
        ProcessType.APPLICATION,
        ProcessType.BUILTIN,
        ProcessType.TEST,
        ProcessType.WORKFLOW,
        ProcessType.WPS_LOCAL,
        ProcessType.WPS_REMOTE,
    ]
