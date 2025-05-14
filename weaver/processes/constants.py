import itertools
import sys
from types import MappingProxyType
from typing import TYPE_CHECKING, Union
from typing_extensions import Literal, get_args

from weaver.base import Constants

if TYPE_CHECKING:
    from typing import Dict, TypeAlias

    from weaver.typedefs import CWL_NamespaceDefinition

IO_SelectInput_Type = Literal["input"]
IO_SelectOutput_Type = Literal["output"]
IO_Select_Type = Literal[IO_SelectInput_Type, IO_SelectOutput_Type]
IO_INPUT = get_args(IO_SelectInput_Type)[0]
IO_OUTPUT = get_args(IO_SelectOutput_Type)[0]

WPS_Literal_Type = Literal["literal"]
WPS_Reference_Type = Literal["reference"]
WPS_Complex_Type = Literal["complex"]
WPS_COMPLEX = get_args(WPS_Complex_Type)[0]
WPS_ComplexData_Type = Literal["ComplexData"]
WPS_BoundingBoxData_Type = Literal["BoundingBoxData"]
WPS_BoundingBox_Type = Literal["bbox"]
WPS_BOUNDINGBOX = get_args(WPS_BoundingBox_Type)[0]
WPS_CategoryType = Union[
    WPS_Literal_Type,
    WPS_Reference_Type,
    WPS_ComplexData_Type,
    WPS_BoundingBoxData_Type,
]
WPS_LITERAL = get_args(WPS_Literal_Type)[0]
WPS_REFERENCE = get_args(WPS_Reference_Type)[0]
WPS_COMPLEX_DATA = get_args(WPS_ComplexData_Type)[0]
WPS_BOUNDINGBOX_DATA = get_args(WPS_BoundingBoxData_Type)[0]

WPS_LiteralDataBoolean_Type = Literal["bool", "boolean"]
WPS_LITERAL_DATA_BOOLEAN = frozenset(get_args(WPS_LiteralDataBoolean_Type))
WPS_LiteralDataDateTime_Type = Literal["date", "time", "dateTime"]
WPS_LITERAL_DATA_DATETIME = frozenset(get_args(WPS_LiteralDataDateTime_Type))
WPS_LiteralDataFloat_Type = Literal["scale", "angle", "float", "double"]
WPS_LITERAL_DATA_FLOAT = frozenset(get_args(WPS_LiteralDataFloat_Type))
WPS_LiteralDataInteger_Type = Literal[
    "int", "integer", "long", "positiveInteger", "nonNegativeInteger"
]
WPS_LITERAL_DATA_INTEGER = frozenset(get_args(WPS_LiteralDataInteger_Type))
WPS_LiteralDataString_Type = Literal["anyURI", "string"]
WPS_LITERAL_DATA_STRING = frozenset(get_args(WPS_LiteralDataString_Type))
WPS_LiteralData_Type = Literal[
    WPS_LiteralDataBoolean_Type,
    WPS_LiteralDataDateTime_Type,
    WPS_LiteralDataFloat_Type,
    WPS_LiteralDataInteger_Type,
    WPS_LiteralDataString_Type,
]
WPS_LITERAL_DATA_TYPES = frozenset(get_args(WPS_LiteralData_Type))

# WPS 'type' string variations employed to indicate a Complex (file) I/O by different libraries
# for literal types, see 'any2cwl_literal_datatype' and 'any2wps_literal_datatype' functions
WPS_ComplexType = Literal[WPS_Complex_Type, WPS_ComplexData_Type, WPS_Reference_Type]
WPS_COMPLEX_TYPES = frozenset(get_args(WPS_ComplexType))

# WPS 'type' string of all combinations (type of data / library implementation)
WPS_DataType = Literal[WPS_Literal_Type, WPS_BoundingBox_Type, WPS_ComplexType]
WPS_DATA_TYPES = frozenset(get_args(WPS_DataType))


class OpenSearchField(Constants):
    START_DATE = "StartDate"
    END_DATE = "EndDate"
    AOI = "aoi"
    COLLECTION = "collection"
    # data source cache
    LOCAL_FILE_SCHEME = "opensearchfile"  # must be a valid url scheme parsable by urlparse


CWL_NAMESPACE_CWL_SPEC_ID = "cwl"
CWL_NAMESPACE_CWL_SPEC_URL = "https://w3id.org/cwl/cwl#"
CWL_NAMESPACE_CWL_SPEC_DEFINITION = MappingProxyType({
    CWL_NAMESPACE_CWL_SPEC_ID: CWL_NAMESPACE_CWL_SPEC_URL
})  # type: CWL_NamespaceDefinition
"""
Namespace used to reference :term:`CWL` definitions provided the common specification.
"""

CWL_NAMESPACE_CWLTOOL_ID = "cwltool"
CWL_NAMESPACE_CWLTOOL_URL = "http://commonwl.org/cwltool#"
CWL_NAMESPACE_CWLTOOL_DEFINITION = MappingProxyType({
    CWL_NAMESPACE_CWLTOOL_ID: CWL_NAMESPACE_CWLTOOL_URL
})  # type: CWL_NamespaceDefinition
"""
Namespace used to reference :term:`CWL` definitions provided by mod:`cwltool`.
"""

CWL_NAMESPACE_SCHEMA_ID = "s"
CWL_NAMESPACE_SCHEMA_URL = "https://schema.org/"
CWL_NAMESPACE_SCHEMA_DEFINITION = MappingProxyType({
    CWL_NAMESPACE_SCHEMA_ID: CWL_NAMESPACE_SCHEMA_URL
})  # type: CWL_NamespaceDefinition
"""
Namespace used to reference :term:`CWL` definitions provided by ``schema.org`` typically used for additional metadata.
"""
CWL_NAMESPACE_SCHEMA_METADATA_NAME = f"{CWL_NAMESPACE_SCHEMA_ID}:name"
CWL_NAMESPACE_SCHEMA_METADATA_EMAIL = f"{CWL_NAMESPACE_SCHEMA_ID}:email"
CWL_NAMESPACE_SCHEMA_METADATA_IDENTIFIER = f"{CWL_NAMESPACE_SCHEMA_ID}:identifier"
CWL_NAMESPACE_SCHEMA_METADATA_PERSON = f"{CWL_NAMESPACE_SCHEMA_ID}:Person"
CWL_NAMESPACE_SCHEMA_METADATA_AUTHOR = f"{CWL_NAMESPACE_SCHEMA_ID}:author"
CWL_NAMESPACE_SCHEMA_METADATA_CITATION = f"{CWL_NAMESPACE_SCHEMA_ID}:citation"
CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS = f"{CWL_NAMESPACE_SCHEMA_ID}:keywords"
CWL_NAMESPACE_SCHEMA_METADATA_CODE_REPOSITORY = f"{CWL_NAMESPACE_SCHEMA_ID}:codeRepository"
CWL_NAMESPACE_SCHEMA_METADATA_CONTRIBUTOR = f"{CWL_NAMESPACE_SCHEMA_ID}:contributor"
CWL_NAMESPACE_SCHEMA_METADATA_DATE_CREATED = f"{CWL_NAMESPACE_SCHEMA_ID}:dateCreated"
CWL_NAMESPACE_SCHEMA_METADATA_LICENSE = f"{CWL_NAMESPACE_SCHEMA_ID}:license"
CWL_NAMESPACE_SCHEMA_METADATA_RELEASE_NOTES = f"{CWL_NAMESPACE_SCHEMA_ID}:releaseNotes"
CWL_NAMESPACE_SCHEMA_METADATA_VERSION = f"{CWL_NAMESPACE_SCHEMA_ID}:version"
CWL_NAMESPACE_SCHEMA_METADATA_SOFTWARE_VERSION = f"{CWL_NAMESPACE_SCHEMA_ID}:softwareVersion"
CWL_NAMESPACE_SCHEMA_METADATA_SUPPORTED = [
    CWL_NAMESPACE_SCHEMA_METADATA_AUTHOR,
    CWL_NAMESPACE_SCHEMA_METADATA_CITATION,
    CWL_NAMESPACE_SCHEMA_METADATA_CODE_REPOSITORY,
    CWL_NAMESPACE_SCHEMA_METADATA_CONTRIBUTOR,
    CWL_NAMESPACE_SCHEMA_METADATA_DATE_CREATED,
    CWL_NAMESPACE_SCHEMA_METADATA_LICENSE,
    CWL_NAMESPACE_SCHEMA_METADATA_RELEASE_NOTES,
    CWL_NAMESPACE_SCHEMA_METADATA_KEYWORDS,
    CWL_NAMESPACE_SCHEMA_METADATA_VERSION,
    CWL_NAMESPACE_SCHEMA_METADATA_SOFTWARE_VERSION,
]
"""
Fields that can be directly in the :term:`CWL` contents.
"""

CWL_NAMESPACE_OGC_API_PROC_PART1_ID = "ogcapi-processes-1"
CWL_NAMESPACE_OGC_API_PROC_PART1_URL = "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/"
# CWL_NAMESPACE_OGC_API_PROC_PART2_ID = "ogcapi-processes-2"
# CWL_NAMESPACE_OGC_API_PROC_PART2_URL = "https://schemas.opengis.net/ogcapi/processes/part2/1.0/openapi/"
CWL_NAMESPACE_OGC_API_PROC_DEFINITION = MappingProxyType({
    CWL_NAMESPACE_OGC_API_PROC_PART1_ID: CWL_NAMESPACE_OGC_API_PROC_PART1_URL,
    # CWL_NAMESPACE_OGC_API_PROC_PART2_ID: CWL_NAMESPACE_OGC_API_PROC_PART2_URL,
})  # type: CWL_NamespaceDefinition
"""
Namespaces used to reference :term:`OGC API - Processes` schema definitions.
"""

# weaver-specific requirements, but non-namespaced for backward support
CWL_NAMESPACES = {}  # type: Dict[str, str]
CWL_NAMESPACES.update(CWL_NAMESPACE_CWL_SPEC_DEFINITION)
CWL_NAMESPACES.update(CWL_NAMESPACE_CWLTOOL_DEFINITION)
CWL_NAMESPACES.update(CWL_NAMESPACE_SCHEMA_DEFINITION)
CWL_NAMESPACES.update(CWL_NAMESPACE_OGC_API_PROC_DEFINITION)
CWL_NAMESPACES = MappingProxyType(CWL_NAMESPACES)  # type: CWL_NamespaceDefinition
CWL_NAMESPACES_REVERSED = MappingProxyType({
    _urn: _ns for _ns, _urn in CWL_NAMESPACES.items()
})  # type: CWL_NamespaceDefinition

CWL_RequirementBuiltinType = Literal["BuiltinRequirement"]
CWL_RequirementESGFCWTType = Literal["ESGF-CWTRequirement"]
CWL_RequirementOGCAPIType = Literal["OGCAPIRequirement"]
CWL_RequirementWPS1Type = Literal["WPS1Requirement"]

# weaver-specific requirements with namespace
CWL_RequirementWeaverBuiltinType = Literal["weaver:BuiltinRequirement"]
CWL_RequirementWeaverESGFCWTType = Literal["weaver:ESGF-CWTRequirement"]
CWL_RequirementWeaverOGCAPIType = Literal["weaver:OGCAPIRequirement"]
CWL_RequirementWeaverWPS1Type = Literal["weaver:WPS1Requirement"]

CWL_RequirementDockerType = Literal["DockerRequirement"]
CWL_RequirementDockerGpuType = Literal["DockerGpuRequirement"]
CWL_RequirementCUDANameType = Literal["CUDARequirement"]
CWL_RequirementCUDAType = Literal["cwltool:CUDARequirement"]
CWL_RequirementEnvVarType = Literal["EnvVarRequirement"]
CWL_RequirementInitialWorkDirType = Literal["InitialWorkDirRequirement"]
CWL_RequirementInlineJavascriptType = Literal["InlineJavascriptRequirement"]
CWL_RequirementInplaceUpdateType = Literal["InplaceUpdateRequirement"]
CWL_RequirementLoadListingType = Literal["LoadListingRequirement"]
CWL_RequirementMPIType = Literal["MPIRequirement"]
CWL_RequirementMultipleInputFeatureType = Literal["MultipleInputFeatureRequirement"]
CWL_RequirementNetworkAccessType = Literal["NetworkAccess"]
CWL_RequirementProcessGeneratorType = Literal["ProcessGenerator"]
CWL_RequirementResourceType = Literal["ResourceRequirement"]
CWL_RequirementScatterFeatureType = Literal["ScatterFeatureRequirement"]
CWL_RequirementSecretsType = Literal["cwltool:Secrets"]
CWL_RequirementStepInputExpressionType = Literal["StepInputExpressionRequirement"]
CWL_RequirementSubworkflowFeatureType = Literal["SubworkflowFeatureRequirement"]
CWL_RequirementToolTimeLimitType = Literal["ToolTimeLimit"]
CWL_RequirementWorkReuseType = Literal["WorkReuse"]

# FIXME: convert to 'Constants' class
# CWL package (requirements/hints) corresponding to `ProcessType.APPLICATION`
CWL_REQUIREMENT_APP_BUILTIN = get_args(CWL_RequirementBuiltinType)[0]
CWL_REQUIREMENT_APP_DOCKER = get_args(CWL_RequirementDockerType)[0]
# backward compatibility, instead use ('DockerRequirement' + 'cwltool:CUDARequirement')
CWL_REQUIREMENT_APP_DOCKER_GPU = get_args(CWL_RequirementDockerGpuType)[0]
CWL_REQUIREMENT_APP_ESGF_CWT = get_args(CWL_RequirementESGFCWTType)[0]
CWL_REQUIREMENT_APP_OGC_API = get_args(CWL_RequirementOGCAPIType)[0]
CWL_REQUIREMENT_APP_WPS1 = get_args(CWL_RequirementWPS1Type)[0]

CWL_REQUIREMENT_APP_WEAVER_CLASSES = frozenset([
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
])
"""
Set of :term:`CWL` requirements defined by `Weaver` for an :term:`Application Package` implementation.
"""

CWL_NAMESPACE_WEAVER_ID = "weaver"
CWL_NAMESPACE_WEAVER_URL = "https://schemas.crim.ca/cwl/weaver#"
CWL_NAMESPACE_WEAVER_DEFINITION = MappingProxyType({CWL_NAMESPACE_WEAVER_ID: CWL_NAMESPACE_WEAVER_URL})
"""
Namespace used to reference :term:`CWL` definitions provided by `Weaver`.
"""

CWL_REQUIREMENT_APP_WEAVER_DEFINITION = MappingProxyType({
    f"{CWL_NAMESPACE_WEAVER_ID}:{_req}": f"{CWL_NAMESPACE_WEAVER_URL}{_req}"
    for _req in CWL_REQUIREMENT_APP_WEAVER_CLASSES
})

CWL_RequirementAppTypes = Literal[
    CWL_RequirementBuiltinType,
    CWL_RequirementDockerType,
    CWL_RequirementDockerGpuType,
    CWL_RequirementESGFCWTType,
    CWL_RequirementOGCAPIType,
    CWL_RequirementWPS1Type,
]
CWL_REQUIREMENT_APP_TYPES = frozenset(
    list(get_args(CWL_RequirementAppTypes))
    + list(CWL_REQUIREMENT_APP_WEAVER_DEFINITION)
)
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

CWL_REQUIREMENT_APP_REMOTE = frozenset(
    f"{_prefix}{_req}"
    for _prefix, _req in itertools.product(
        ["", f"{CWL_NAMESPACE_WEAVER_ID}:", CWL_NAMESPACE_WEAVER_URL],
        [
            CWL_REQUIREMENT_APP_ESGF_CWT,
            CWL_REQUIREMENT_APP_OGC_API,
            CWL_REQUIREMENT_APP_WPS1,
        ]
    )
)
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
CWL_REQUIREMENT_CUDA = get_args(CWL_RequirementCUDAType)[0]
CWL_REQUIREMENT_CUDA_NAME = get_args(CWL_RequirementCUDANameType)[0]
CWL_REQUIREMENT_CUDA_NAMESPACE = CWL_NAMESPACE_CWLTOOL_DEFINITION
CWL_REQUIREMENT_ENV_VAR = get_args(CWL_RequirementEnvVarType)[0]
CWL_REQUIREMENT_INIT_WORKDIR = get_args(CWL_RequirementInitialWorkDirType)[0]
CWL_REQUIREMENT_INLINE_JAVASCRIPT = get_args(CWL_RequirementInlineJavascriptType)[0]
CWL_REQUIREMENT_INPLACE_UPDATE = get_args(CWL_RequirementInplaceUpdateType)[0]
CWL_REQUIREMENT_LOAD_LISTING = get_args(CWL_RequirementLoadListingType)[0]
CWL_REQUIREMENT_MPI = get_args(CWL_RequirementMPIType)[0]  # no implication yet
CWL_REQUIREMENT_MULTIPLE_INPUT = get_args(CWL_RequirementMultipleInputFeatureType)[0]
CWL_REQUIREMENT_NETWORK_ACCESS = get_args(CWL_RequirementNetworkAccessType)[0]
CWL_REQUIREMENT_PROCESS_GENERATOR = get_args(CWL_RequirementProcessGeneratorType)[0]
CWL_REQUIREMENT_RESOURCE = get_args(CWL_RequirementResourceType)[0]
CWL_REQUIREMENT_SCATTER = get_args(CWL_RequirementScatterFeatureType)[0]
CWL_REQUIREMENT_SECRETS = get_args(CWL_RequirementSecretsType)[0]
CWL_REQUIREMENT_STEP_INPUT_EXPRESSION = get_args(CWL_RequirementStepInputExpressionType)[0]
CWL_REQUIREMENT_SUBWORKFLOW = get_args(CWL_RequirementSubworkflowFeatureType)[0]
CWL_REQUIREMENT_TIME_LIMIT = get_args(CWL_RequirementToolTimeLimitType)[0]
# default is to reuse, employed to explicitly disable
CWL_REQUIREMENT_WORK_REUSE = get_args(CWL_RequirementWorkReuseType)[0]

CWL_REQUIREMENT_FEATURES = frozenset([
    CWL_REQUIREMENT_CUDA,  # note: only allowed in 'hints' because of 'cwltool:' namespace
    CWL_REQUIREMENT_CUDA_NAME,  # extension import does not have namespace, but it requires it during execution
    CWL_REQUIREMENT_ENV_VAR,
    CWL_REQUIREMENT_INIT_WORKDIR,
    CWL_REQUIREMENT_INPLACE_UPDATE,
    CWL_REQUIREMENT_INLINE_JAVASCRIPT,
    CWL_REQUIREMENT_LOAD_LISTING,
    # CWL_REQUIREMENT_MPI,  # no implication yet
    CWL_REQUIREMENT_MULTIPLE_INPUT,
    CWL_REQUIREMENT_NETWORK_ACCESS,
    # CWL_REQUIREMENT_PROCESS_GENERATOR,  # explicitly unsupported, works against Weaver's behavior
    CWL_REQUIREMENT_RESOURCE,  # FIXME: perform pre-check on job submit? (https://github.com/crim-ca/weaver/issues/138)
    CWL_REQUIREMENT_SCATTER,
    CWL_REQUIREMENT_STEP_INPUT_EXPRESSION,
    CWL_REQUIREMENT_SECRETS,  # note: only allowed in 'hints' because of 'cwltool:' namespace
    CWL_REQUIREMENT_SUBWORKFLOW,
    CWL_REQUIREMENT_TIME_LIMIT,
    CWL_REQUIREMENT_WORK_REUSE,  # allow it, but makes sense only for Workflow steps if cwltool handles it by itself
])
"""
Set of :term:`CWL` requirements that corresponds to extra functionalities.

An :term:`Application Package` that only contains these requirements by themselves would not be considered complete.
These extra requirements must be accompanied by another one from :data:`CWL_REQUIREMENT_APP_TYPES` to be considered
a complete definition.
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
PACKAGE_INTEGER_TYPES = frozenset(["int", "integer", "long"])
PACKAGE_FLOATING_TYPES = frozenset(["float", "double"])
PACKAGE_NUMERIC_TYPES = frozenset(PACKAGE_INTEGER_TYPES | PACKAGE_FLOATING_TYPES)
PACKAGE_BASIC_TYPES = frozenset({"string", "boolean"} | PACKAGE_NUMERIC_TYPES)
PACKAGE_LITERAL_TYPES = frozenset(PACKAGE_BASIC_TYPES | {"null", "Any"})
PACKAGE_FILE_TYPE = "File"
PACKAGE_DIRECTORY_TYPE = "Directory"
PACKAGE_COMPLEX_TYPES = frozenset([PACKAGE_FILE_TYPE, PACKAGE_DIRECTORY_TYPE])
PACKAGE_ENUM_BASE = "enum"
PACKAGE_CUSTOM_TYPES = frozenset([PACKAGE_ENUM_BASE])  # can be anything, but support "enum" which is more common
PACKAGE_ARRAY_BASE = "array"
PACKAGE_ARRAY_MAX_SIZE = sys.maxsize  # pywps doesn't allow None, so use max size  # FIXME: unbounded (weaver #165)
PACKAGE_ARRAY_ITEMS = frozenset(PACKAGE_BASIC_TYPES | PACKAGE_CUSTOM_TYPES | PACKAGE_COMPLEX_TYPES)
PACKAGE_ARRAY_TYPES = frozenset([f"{item}[]" for item in PACKAGE_ARRAY_ITEMS])
# string values the lowest 'type' field can have by itself (as simple mapping {type: <type-string>})
PACKAGE_TYPE_NULLABLE = frozenset(PACKAGE_BASIC_TYPES | PACKAGE_CUSTOM_TYPES | PACKAGE_COMPLEX_TYPES)
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

# pylint: disable=C0103,invalid-name
ProcessSchemaOGCType = Literal["OGC", "ogc"]
ProcessSchemaOLDType = Literal["OLD", "old"]
ProcessSchemaWPSType = Literal["WPS", "wps"]
ProcessSchemaConstType = "ProcessSchema"  # type: TypeAlias
ProcessSchemaType = Union[
    ProcessSchemaOGCType,
    ProcessSchemaOLDType,
    ProcessSchemaWPSType,
    ProcessSchemaConstType,
]
JobStatusTypeProcess = Literal["process"]
JobStatusTypeService = Literal["service"]
JobStatusTypeProvider = Literal["provider"]
JobStatusConstType = "JobStatusType"  # type: TypeAlias
JobStatusPropertyType = Union[
    JobStatusTypeProcess,
    JobStatusTypeService,
    JobStatusTypeProvider,
    JobStatusConstType,
]
JobInputsOutputsSchemaType_OGC = Literal["OGC", "ogc"]
JobInputsOutputsSchemaType_OLD = Literal["OLD", "old"]
JobInputsOutputsSchemaType_OGC_STRICT = Literal["OGC+STRICT", "ogc+strict"]
JobInputsOutputsSchemaType_OLD_STRICT = Literal["OLD+STRICT", "old+strict"]
JobInputsOutputsSchemaAnyOGCType = Union[JobInputsOutputsSchemaType_OGC, JobInputsOutputsSchemaType_OGC_STRICT]
JobInputsOutputsSchemaAnyOLDType = Union[JobInputsOutputsSchemaType_OLD, JobInputsOutputsSchemaType_OLD_STRICT]
JobInputsOutputsSchemaConstType = "JobInputsOutputsSchema"  # type: TypeAlias
JobInputsOutputsSchemaType = Union[
    JobInputsOutputsSchemaAnyOGCType,
    JobInputsOutputsSchemaAnyOLDType,
    JobInputsOutputsSchemaConstType,
]
JobStatusProfileSchemaType_OGC = Literal["OGC", "ogc"]
JobStatusProfileSchemaType_OpenEO = Literal["OPENEO", "openeo", "openEO", "OpenEO"]
JobStatusProfileSchemaType_WPS = Literal["WPS", "wps"]
JobStatusProfileSchemaConstType = "JobStatusProfileSchema"  # type: TypeAlias
JobStatusProfileSchemaType = Union[
    JobStatusProfileSchemaType_OGC,
    JobStatusProfileSchemaType_OpenEO,
    JobStatusProfileSchemaType_WPS,
    JobStatusProfileSchemaConstType,
]


class ProcessSchema(Constants):
    """
    Schema selector to represent a :term:`Process` description.
    """
    OGC = "OGC"  # type: ProcessSchemaOGCType
    OLD = "OLD"  # type: ProcessSchemaOLDType
    WPS = "WPS"  # type: ProcessSchemaWPSType


class JobInputsOutputsSchema(Constants):
    """
    Schema selector to represent a :term:`Job` output results.
    """
    OGC_STRICT = "ogc+strict"   # type: JobInputsOutputsSchemaType_OGC_STRICT
    OLD_STRICT = "old+strict"   # type: JobInputsOutputsSchemaType_OLD_STRICT
    OGC = "ogc"                 # type: JobInputsOutputsSchemaType_OGC
    OLD = "old"                 # type: JobInputsOutputsSchemaType_OLD


class JobStatusProfileSchema(Constants):
    """
    Schema :term:`Profile` selector to represent a :term:`Job` status response.
    """
    OGC = "ogc"         # type: JobStatusProfileSchemaType_OGC
    OPENEO = "openeo"   # type: JobStatusProfileSchemaType_OpenEO
    WPS = "wps"         # type: JobStatusProfileSchemaType_WPS


class JobStatusType(Constants):
    """
    Type of :term:`Job` status response being represented.

    The values consider teh originally submitted :term:`Process`, :term:`Provider` or :term:`Profile` representations.

    .. seealso::
        - https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/statusInfo.yaml
    """
    # backward compatibility
    PROCESS = "process"     # type: JobStatusTypeProcess  # happens to be the same as newer 'OGC API - Processes' type
    PROVIDER = "provider"   # type: JobStatusTypeProvider
    # previous name used instead of 'provider', reflecting 'weaver.datatype.Service' explicitly
    SERVICE = "service"     # type: JobStatusTypeService
    # additional values as more specific variants of 'provider' or alternate 'profile' representations
    WPS = "wps"             # type: ProcessSchemaWPSType
    OPENEO = "openeo"       # type: JobStatusProfileSchemaType_OpenEO


if TYPE_CHECKING:
    # pylint: disable=invalid-name
    CWL_RequirementNames = Literal[
        CWL_RequirementBuiltinType,
        CWL_RequirementESGFCWTType,
        CWL_RequirementOGCAPIType,
        CWL_RequirementWPS1Type,
        CWL_RequirementWeaverBuiltinType,
        CWL_RequirementWeaverESGFCWTType,
        CWL_RequirementWeaverOGCAPIType,
        CWL_RequirementWeaverWPS1Type,
        CWL_RequirementDockerType,
        CWL_RequirementDockerGpuType,
        CWL_RequirementCUDAType,
        CWL_RequirementEnvVarType,
        CWL_RequirementInitialWorkDirType,
        CWL_RequirementInlineJavascriptType,
        CWL_RequirementInplaceUpdateType,
        CWL_RequirementLoadListingType,
        CWL_RequirementMPIType,
        CWL_RequirementMultipleInputFeatureType,
        CWL_RequirementNetworkAccessType,
        CWL_RequirementResourceType,
        CWL_RequirementScatterFeatureType,
        CWL_RequirementSecretsType,
        CWL_RequirementStepInputExpressionType,
        CWL_RequirementSubworkflowFeatureType,
        CWL_RequirementToolTimeLimitType,
        CWL_RequirementWorkReuseType,
    ]
