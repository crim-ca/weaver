import sys

WPS_INPUT = "input"
WPS_OUTPUT = "output"
WPS_COMPLEX = "complex"
WPS_BOUNDINGBOX = "bbox"
WPS_LITERAL = "literal"
WPS_REFERENCE = "reference"
WPS_COMPLEX_DATA = "ComplexData"
WPS_LITERAL_DATA_TYPE_NAMES = frozenset([
    "date", "time", "dateTime", "anyURI", "scale", "angle", "float", "double",
    "int", "integer", "long", "positiveInteger", "nonNegativeInteger", "bool", "boolean", "string"
])

# opensearch
OPENSEARCH_START_DATE = "StartDate"
OPENSEARCH_END_DATE = "EndDate"
OPENSEARCH_AOI = "aoi"
OPENSEARCH_COLLECTION = "collection"
# data source cache
OPENSEARCH_LOCAL_FILE_SCHEME = "opensearchfile"  # must be a valid url scheme parsable by urlparse

# CWL package (requirements/hints) corresponding to `PROCESS_APPLICATION`
CWL_REQUIREMENT_APP_BUILTIN = "BuiltinRequirement"
CWL_REQUIREMENT_APP_DOCKER = "DockerRequirement"
CWL_REQUIREMENT_APP_DOCKER_GPU = "DockerGpuRequirement"
CWL_REQUIREMENT_APP_ESGF_CWT = "ESGF-CWTRequirement"
CWL_REQUIREMENT_APP_WPS1 = "WPS1Requirement"

CWL_REQUIREMENT_APP_TYPES = frozenset([
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    # FIXME: properly support GPU execution
    #   - https://github.com/crim-ca/weaver/issues/104
    #   - https://github.com/crim-ca/weaver/issues/138
    # CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1,
])
"""
Set of :term:`CWL` requirements consisting of known :term:`Application Package` by this `Weaver` instance.
"""

CWL_REQUIREMENT_APP_REMOTE = frozenset([
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1,
])
"""
Set of :term:`CWL` requirements that correspond to remote execution of an :term:`Application Package`.
"""

CWL_REQUIREMENT_ENV_VAR = "EnvVarRequirement"
CWL_REQUIREMENT_INIT_WORKDIR = "InitialWorkDirRequirement"

# CWL package types and extensions
PACKAGE_SIMPLE_TYPES = frozenset(["string", "boolean", "float", "int", "integer", "long", "double"])
PACKAGE_LITERAL_TYPES = frozenset(list(PACKAGE_SIMPLE_TYPES) + ["null", "Any"])
PACKAGE_COMPLEX_TYPES = frozenset(["File"])  # FIXME: type "Directory" not supported
PACKAGE_ENUM_BASE = "enum"
PACKAGE_CUSTOM_TYPES = frozenset([PACKAGE_ENUM_BASE])  # can be anything, but support "enum" which is more common
PACKAGE_ARRAY_BASE = "array"
PACKAGE_ARRAY_MAX_SIZE = sys.maxsize  # pywps doesn't allow None, so use max size  # FIXME: unbounded (weaver #165)
PACKAGE_ARRAY_ITEMS = frozenset(list(PACKAGE_SIMPLE_TYPES) + list(PACKAGE_COMPLEX_TYPES) + list(PACKAGE_CUSTOM_TYPES))
PACKAGE_ARRAY_TYPES = frozenset(["{}[]".format(item) for item in PACKAGE_ARRAY_ITEMS])
# string values the lowest 'type' field can have by itself (as simple mapping {type: <type-string>})
PACKAGE_TYPE_NULLABLE = frozenset(list(PACKAGE_SIMPLE_TYPES) + list(PACKAGE_CUSTOM_TYPES) + list(PACKAGE_COMPLEX_TYPES))
# shortcut notations that can be employed to convert basic types into corresponding array or nullable variants
PACKAGE_SHORTCUTS = frozenset(["{}?".format(typ) for typ in PACKAGE_TYPE_NULLABLE] +
                              list(PACKAGE_ARRAY_TYPES) +
                              ["{}?".format(typ) for typ in PACKAGE_ARRAY_TYPES])
PACKAGE_TYPE_POSSIBLE_VALUES = frozenset(
    list(PACKAGE_LITERAL_TYPES) +
    list(PACKAGE_COMPLEX_TYPES) +
    list(PACKAGE_SHORTCUTS)
)
