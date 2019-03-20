WPS_INPUT = "input"
WPS_OUTPUT = "output"
WPS_COMPLEX = "complex"
WPS_BOUNDINGBOX = "bbox"
WPS_LITERAL = "literal"
WPS_REFERENCE = "reference"

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
CWL_REQUIREMENT_APP_ESGF_CWT = "ESGF-CWTRequirement"
CWL_REQUIREMENT_APP_WPS1 = "WPS1Requirement"
CWL_REQUIREMENT_APP_TYPES = frozenset([
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1,
])
