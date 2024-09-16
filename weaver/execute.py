from typing import TYPE_CHECKING

from weaver.base import Constants

if TYPE_CHECKING:
    from typing import List


class ExecuteMode(Constants):
    AUTO = "auto"
    ASYNC = "async"
    SYNC = "sync"


class ExecuteControlOption(Constants):
    ASYNC = "async-execute"
    SYNC = "sync-execute"

    @classmethod
    def values(cls):
        # type: () -> List[AnyExecuteControlOption]
        """
        Return default control options in specific order according to preferred modes for execution by `Weaver`.
        """
        return [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC]


class ExecuteReturnPreference(Constants):
    MINIMAL = "minimal"
    REPRESENTATION = "representation"


class ExecuteResponse(Constants):
    RAW = "raw"
    DOCUMENT = "document"


class ExecuteTransmissionMode(Constants):
    VALUE = "value"
    REFERENCE = "reference"


class ExecuteCollectionFormat(Constants):
    STAC = "stac-collection"
    OGC_COVERAGE = "ogc-coverage-collection"
    OGC_FEATURES = "ogc-features-collection"
    OGC_MAP = "ogc-map-collection"
    GEOJSON = "geojson-feature-collection"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyExecuteMode = Literal[
        ExecuteMode.ASYNC,
        ExecuteMode.SYNC,
    ]
    AnyExecuteControlOption = Literal[
        ExecuteControlOption.ASYNC,
        ExecuteControlOption.SYNC,
    ]
    AnyExecuteResponse = Literal[
        ExecuteResponse.DOCUMENT,
        ExecuteResponse.RAW,
    ]
    AnyExecuteTransmissionMode = Literal[
        ExecuteTransmissionMode.REFERENCE,
        ExecuteTransmissionMode.VALUE,
    ]
    AnyExecuteCollectionFormat = Literal[
        ExecuteCollectionFormat.STAC,
        ExecuteCollectionFormat.OGC_COVERAGE,
        ExecuteCollectionFormat.OGC_FEATURES,
        ExecuteCollectionFormat.OGC_MAP,
        ExecuteCollectionFormat.GEOJSON,
    ]
