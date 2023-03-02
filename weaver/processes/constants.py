import sys
from types import MappingProxyType
from typing import TYPE_CHECKING

from weaver.base import Constants

WPS_INPUT = "input"
WPS_OUTPUT = "output"
WPS_COMPLEX = "complex"
WPS_BOUNDINGBOX = "bbox"
WPS_LITERAL = "literal"
WPS_REFERENCE = "reference"
WPS_COMPLEX_DATA = "ComplexData"
WPS_LITERAL_DATA_BOOLEAN = frozenset(["bool", "boolean"])
WPS_LITERAL_DATA_DATETIME = frozenset(["date", "time", "dateTime"])
WPS_LITERAL_DATA_FLOAT = frozenset(["scale", "angle", "float", "double"])
WPS_LITERAL_DATA_INTEGER = frozenset(["int", "integer", "long", "positiveInteger", "nonNegativeInteger"])
WPS_LITERAL_DATA_STRING = frozenset({"anyURI", "string"} | WPS_LITERAL_DATA_DATETIME)
WPS_LITERAL_DATA_TYPES = frozenset(
    WPS_LITERAL_DATA_BOOLEAN |
    WPS_LITERAL_DATA_DATETIME |
    WPS_LITERAL_DATA_FLOAT |
    WPS_LITERAL_DATA_INTEGER |
    WPS_LITERAL_DATA_STRING
)

# WPS 'type' string variations employed to indicate a Complex (file) I/O by different libraries
# for literal types, see 'any2cwl_literal_datatype' and 'any2wps_literal_datatype' functions
WPS_COMPLEX_TYPES = frozenset([WPS_COMPLEX, WPS_COMPLEX_DATA, WPS_REFERENCE])

# WPS 'type' string of all combinations (type of data / library implementation)
WPS_DATA_TYPES = frozenset({WPS_LITERAL, WPS_BOUNDINGBOX} | WPS_COMPLEX_TYPES)


class OpenSearchField(Constants):
    START_DATE = "StartDate"
    END_DATE = "EndDate"
    AOI = "aoi"
    COLLECTION = "collection"
    # data source cache
    LOCAL_FILE_SCHEME = "opensearchfile"  # must be a valid url scheme parsable by urlparse


CWL_NAMESPACE_ID = "cwl"
CWL_NAMESPACE_URL = "https://w3id.org/cwl/cwl#"
CWL_NAMESPACE = MappingProxyType({CWL_NAMESPACE_ID: CWL_NAMESPACE_URL})

CWL_TOOL_NAMESPACE_ID = "cwltool"
CWL_TOOL_NAMESPACE_URL = "http://commonwl.org/cwltool#"
CWL_TOOL_NAMESPACE = MappingProxyType({CWL_TOOL_NAMESPACE_ID: CWL_TOOL_NAMESPACE_URL})

# FIXME: convert to 'Constants' class
# CWL package (requirements/hints) corresponding to `ProcessType.APPLICATION`
CWL_REQUIREMENT_APP_BUILTIN = "BuiltinRequirement"
CWL_REQUIREMENT_APP_DOCKER = "DockerRequirement"
CWL_REQUIREMENT_APP_DOCKER_GPU = "DockerGpuRequirement"  # backward compatibility
CWL_REQUIREMENT_APP_ESGF_CWT = "ESGF-CWTRequirement"
CWL_REQUIREMENT_APP_OGC_API = "OGCAPIRequirement"
CWL_REQUIREMENT_APP_WPS1 = "WPS1Requirement"

CWL_REQUIREMENT_APP_WEAVER = frozenset([
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
])
"""
Set of :term:`CWL` requirements defined by `Weaver` for an :term:`Application Package` implementation.
"""

CWL_NAMESPACE_WEAVER = {
    "weaver": "http://crim.ca/weaver#"
}
"""
Namespace used to reference :term:`CWL` definitions provided by `Weaver`. 
"""

CWL_REQUIREMENT_APP_TYPES = frozenset([
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,  # backward compatibility, use 'DockerRequirement+cwltool:CUDARequirement' instead
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
] + [
    f"{list(CWL_NAMESPACE_WEAVER)[0]}:{_req}"
    for _req in CWL_REQUIREMENT_APP_WEAVER
])
"""
Set of :term:`CWL` requirements consisting of known :term:`Application Package` by this `Weaver` instance.
"""

CWL_REQUIREMENT_APP_LOCAL = frozenset([
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
])
"""
Set of :term:`CWL` requirements that correspond to local execution of an :term:`Application Package`.
"""

# FIXME: convert to 'Constants' class
CWL_REQUIREMENT_APP_REMOTE = frozenset([
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
])
"""
Set of :term:`CWL` requirements that correspond to remote execution of an :term:`Application Package`.
"""

CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS = MappingProxyType({
    # use older minimal version/capability to allow more chances to match any available GPU
    # if this causes an issue for an actual application, it must provide it explicitly anyway
    "cudaVersionMin": "10.0",
    "cudaComputeCapability": "3.0",
    # use minimum defaults, single GPU
    "cudaDeviceCountMin": 1,
    "cudaDeviceCountMax": 1,
})
"""
Parameters employed by default for updating :data:`CWL_REQUIREMENT_APP_DOCKER_GPU` into :data:`CWL_REQUIREMENT_CUDA`.
"""

# FIXME: convert to 'Constants' class
# NOTE: depending on the 'cwlVersion' of the document, some items are extensions or native to the standard specification
CWL_REQUIREMENT_CUDA = f"{CWL_TOOL_NAMESPACE_ID}:CUDARequirement"
CWL_REQUIREMENT_CUDA_NAMESPACE = CWL_TOOL_NAMESPACE
CWL_REQUIREMENT_ENV_VAR = "EnvVarRequirement"
CWL_REQUIREMENT_INIT_WORKDIR = "InitialWorkDirRequirement"
CWL_REQUIREMENT_INLINE_JAVASCRIPT = "InlineJavascriptRequirement"
CWL_REQUIREMENT_INPLACE_UPDATE = "InplaceUpdateRequirement"
CWL_REQUIREMENT_LOAD_LISTING = "LoadListingRequirement"
CWL_REQUIREMENT_MPI = "MPIRequirement"  # no implication yet
CWL_REQUIREMENT_NETWORK_ACCESS = "NetworkAccess"
CWL_REQUIREMENT_PROCESS_GENERATOR = "ProcessGenerator"
CWL_REQUIREMENT_RESOURCE = "ResourceRequirement"
CWL_REQUIREMENT_SCATTER = "ScatterFeatureRequirement"
CWL_REQUIREMENT_SECRETS = "Secrets"
CWL_REQUIREMENT_TIME_LIMIT = "ToolTimeLimit"
CWL_REQUIREMENT_WORK_REUSE = "WorkReuse"  # default is to reuse, employed to explicitly disable

CWL_REQUIREMENT_FEATURES = frozenset([
    CWL_REQUIREMENT_CUDA,
    CWL_REQUIREMENT_ENV_VAR,
    CWL_REQUIREMENT_INIT_WORKDIR,
    CWL_REQUIREMENT_INPLACE_UPDATE,
    CWL_REQUIREMENT_INLINE_JAVASCRIPT,
    CWL_REQUIREMENT_LOAD_LISTING,
    # CWL_REQUIREMENT_MPI,  # no implication yet
    CWL_REQUIREMENT_NETWORK_ACCESS,
    # CWL_REQUIREMENT_PROCESS_GENERATOR,  # explicitly unsupported, works against Weaver's behavior
    CWL_REQUIREMENT_RESOURCE,  # FIXME: perform pre-check on job submit? (https://github.com/crim-ca/weaver/issues/138)
    CWL_REQUIREMENT_SCATTER,
    # CWL_REQUIREMENT_SECRETS,  # FIXME: support CWL Secrets (https://github.com/crim-ca/weaver/issues/511)
    CWL_REQUIREMENT_TIME_LIMIT,
    CWL_REQUIREMENT_WORK_REUSE,  # allow it, but makes sense only for Workflow steps if cwltool handles it by itself
])
"""
Set of :term:`CWL` requirements that corresponds to extra functionalities not completely defining
an :term:`Application Package` by themselves.
"""

CWL_REQUIREMENTS_SUPPORTED = frozenset(
    CWL_REQUIREMENT_APP_TYPES |
    CWL_REQUIREMENT_FEATURES
)
"""
Set of all :term:`CWL` requirements or hints that are supported for deployment of valid :term:`Application Package`.
"""

# CWL package types and extensions
PACKAGE_EXTENSIONS = frozenset(["yaml", "yml", "json", "cwl", "job"])
PACKAGE_SIMPLE_TYPES = frozenset(["string", "boolean", "float", "int", "integer", "long", "double"])
PACKAGE_LITERAL_TYPES = frozenset(PACKAGE_SIMPLE_TYPES | {"null", "Any"})
PACKAGE_FILE_TYPE = "File"
PACKAGE_DIRECTORY_TYPE = "Directory"
PACKAGE_COMPLEX_TYPES = frozenset([PACKAGE_FILE_TYPE, PACKAGE_DIRECTORY_TYPE])
PACKAGE_ENUM_BASE = "enum"
PACKAGE_CUSTOM_TYPES = frozenset([PACKAGE_ENUM_BASE])  # can be anything, but support "enum" which is more common
PACKAGE_ARRAY_BASE = "array"
PACKAGE_ARRAY_MAX_SIZE = sys.maxsize  # pywps doesn't allow None, so use max size  # FIXME: unbounded (weaver #165)
PACKAGE_ARRAY_ITEMS = frozenset(PACKAGE_SIMPLE_TYPES | PACKAGE_CUSTOM_TYPES | PACKAGE_COMPLEX_TYPES)
PACKAGE_ARRAY_TYPES = frozenset([f"{item}[]" for item in PACKAGE_ARRAY_ITEMS])
# string values the lowest 'type' field can have by itself (as simple mapping {type: <type-string>})
PACKAGE_TYPE_NULLABLE = frozenset(PACKAGE_SIMPLE_TYPES | PACKAGE_CUSTOM_TYPES | PACKAGE_COMPLEX_TYPES)
# shortcut notations that can be employed to convert basic types into corresponding array or nullable variants
PACKAGE_SHORTCUTS = frozenset(
    {f"{typ}?" for typ in PACKAGE_TYPE_NULLABLE} |
    PACKAGE_ARRAY_TYPES |
    {f"{typ}?" for typ in PACKAGE_ARRAY_TYPES}
)
PACKAGE_TYPE_POSSIBLE_VALUES = frozenset(
    PACKAGE_LITERAL_TYPES |
    PACKAGE_COMPLEX_TYPES |
    PACKAGE_SHORTCUTS
)

# OpenAPI definitions
OAS_COMPLEX_TYPES = frozenset(["object"])
OAS_ARRAY_TYPES = frozenset(["array"])
OAS_LITERAL_TYPES = frozenset(["boolean", "integer", "number", "string"])
OAS_LITERAL_NUMERIC = frozenset(["integer", "number"])
OAS_LITERAL_FLOAT_FORMATS = frozenset(["float", "double"])
OAS_LITERAL_INTEGER_FORMATS = frozenset(["int32", "int64"])
OAS_LITERAL_NUMERIC_FORMATS = frozenset(OAS_LITERAL_FLOAT_FORMATS | OAS_LITERAL_INTEGER_FORMATS)
OAS_LITERAL_DATETIME_FORMATS = frozenset(["date", "datetime", "date-time", "full-date", "time"])
OAS_LITERAL_STRING_FORMATS = frozenset(
    OAS_LITERAL_DATETIME_FORMATS |
    {"password", "uri", "url"}
)
OAS_LITERAL_BINARY_FORMATS = frozenset(["base64", "binary", "byte"])
OAS_KEYWORD_TYPES = frozenset(["allOf", "anyOf", "oneOf", "not"])
OAS_DATA_TYPES = frozenset(
    OAS_COMPLEX_TYPES |
    OAS_ARRAY_TYPES |
    OAS_LITERAL_TYPES
)


class ProcessSchema(Constants):
    """
    Schema selector to represent a :term:`Process` description.
    """
    OGC = "OGC"
    OLD = "OLD"
    WPS = "WPS"


if TYPE_CHECKING:
    from typing import Union

    from weaver.typedefs import Literal

    # pylint: disable=invalid-name
    CWL_RequirementNames = Literal[
        CWL_REQUIREMENT_APP_BUILTIN,
        CWL_REQUIREMENT_APP_DOCKER,
        CWL_REQUIREMENT_APP_DOCKER_GPU,
        CWL_REQUIREMENT_APP_ESGF_CWT,
        CWL_REQUIREMENT_APP_OGC_API,
        CWL_REQUIREMENT_APP_WPS1,
        CWL_REQUIREMENT_CUDA,
        CWL_REQUIREMENT_ENV_VAR,
        CWL_REQUIREMENT_INIT_WORKDIR,
        CWL_REQUIREMENT_INLINE_JAVASCRIPT,
        CWL_REQUIREMENT_INPLACE_UPDATE,
        CWL_REQUIREMENT_LOAD_LISTING,
        CWL_REQUIREMENT_MPI,
        CWL_REQUIREMENT_NETWORK_ACCESS,
        CWL_REQUIREMENT_RESOURCE,
        CWL_REQUIREMENT_SCATTER,
        CWL_REQUIREMENT_SECRETS,
        CWL_REQUIREMENT_TIME_LIMIT,
        CWL_REQUIREMENT_WORK_REUSE,
    ]
    ProcessSchemaType = Literal[ProcessSchema.OGC, ProcessSchema.OLD]
    WPS_ComplexType = Literal[WPS_COMPLEX, WPS_COMPLEX_DATA, WPS_REFERENCE]
    WPS_DataType = Union[Literal[WPS_LITERAL, WPS_BOUNDINGBOX], WPS_ComplexType]
