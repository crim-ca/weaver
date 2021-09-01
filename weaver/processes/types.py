PROCESS_APPLICATION = "application"     # CWL package referencing an application (eg: Docker)
PROCESS_BUILTIN = "builtin"             # Local scripts builtin Weaver for basic operations
PROCESS_TEST = "test"                   # Same as local WPS, but specifically for testing
PROCESS_WORKFLOW = "workflow"           # CWL package chaining multiple other process-types
PROCESS_WPS_LOCAL = "wps"               # Local PyWPS process definitions
PROCESS_WPS_REMOTE = "wps-remote"       # Remote WPS provider references (once instantiated from Service definition)
PROCESS_WPS_TYPES = frozenset([
    PROCESS_WPS_LOCAL,
    PROCESS_WPS_REMOTE
])
