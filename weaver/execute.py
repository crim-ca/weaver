import logging
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPBadRequest

from weaver.base import Constants
from weaver.utils import get_header, parse_kvp

if TYPE_CHECKING:
    from typing import List, Optional, Union, Tuple

    from weaver.typedefs import AnyHeadersContainer, HeadersType, Literal

    ExecutionModeAutoType = Literal["auto"]
    ExecutionModeAsyncType = Literal["async"]
    ExecutionModeSyncType = Literal["sync"]
    AnyExecuteMode = Union[
        ExecutionModeAutoType,
        ExecutionModeAsyncType,
        ExecutionModeSyncType,
    ]
    ExecuteControlOptionAsyncType = Literal["async-execute"]
    ExecuteControlOptionSyncType = Literal["sync-execute"]
    AnyExecuteControlOption = Union[
        ExecuteControlOptionAsyncType,
        ExecuteControlOptionSyncType,
    ]
    ExecuteReturnPreferenceMinimalType = Literal["minimal"]
    ExecuteReturnPreferenceRepresentationType = Literal["representation"]
    AnyExecuteReturnPreference = Union[
        ExecuteReturnPreferenceMinimalType,
        ExecuteReturnPreferenceRepresentationType,
    ]
    ExecuteResponseDocumentType = Literal["document"]
    ExecuteResponseRawType = Literal["raw"]
    AnyExecuteResponse = Union[
        ExecuteResponseDocumentType,
        ExecuteResponseRawType,
    ]
    ExecuteTransmissionModeReferenceType = Literal["reference"]
    ExecuteTransmissionModeValueType = Literal["value"]
    AnyExecuteTransmissionMode = Union[
        ExecuteTransmissionModeReferenceType,
        ExecuteTransmissionModeValueType,
    ]
    ExecuteCollectionFormatType_STAC = Literal["stac-collection"]
    ExecuteCollectionFormatType_OGC_COVERAGE = Literal["ogc-coverage-collection"]
    ExecuteCollectionFormatType_OGC_FEATURES = Literal["ogc-features-collection"]
    ExecuteCollectionFormatType_OGC_MAP = Literal["ogc-map-collection"]
    ExecuteCollectionFormatType_GEOJSON = Literal["geojson-feature-collection"]
    AnyExecuteCollectionFormat = Union[
        ExecuteCollectionFormatType_STAC,
        ExecuteCollectionFormatType_OGC_COVERAGE,
        ExecuteCollectionFormatType_OGC_FEATURES,
        ExecuteCollectionFormatType_OGC_MAP,
        ExecuteCollectionFormatType_GEOJSON,
    ]

LOGGER = logging.getLogger(__name__)


class ExecuteMode(Constants):
    AUTO = "auto"       # type: ExecutionModeAutoType
    ASYNC = "async"     # type: ExecutionModeAsyncType
    SYNC = "sync"       # type: ExecutionModeSyncType


class ExecuteControlOption(Constants):
    ASYNC = "async-execute"     # type: ExecuteControlOptionAsyncType
    SYNC = "sync-execute"       # type: ExecuteControlOptionSyncType

    @classmethod
    def values(cls):
        # type: () -> List[AnyExecuteControlOption]
        """
        Return default control options in specific order according to preferred modes for execution by `Weaver`.
        """
        return [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC]


class ExecuteReturnPreference(Constants):
    MINIMAL = "minimal"                 # type: ExecuteReturnPreferenceMinimalType
    REPRESENTATION = "representation"   # type: ExecuteReturnPreferenceRepresentationType


class ExecuteResponse(Constants):
    RAW = "raw"             # type: ExecuteResponseRawType
    DOCUMENT = "document"   # type: ExecuteResponseDocumentType


class ExecuteTransmissionMode(Constants):
    VALUE = "value"             # type: ExecuteTransmissionModeValueType
    REFERENCE = "reference"     # type: ExecuteTransmissionModeReferenceType


class ExecuteCollectionFormat(Constants):
    STAC = "stac-collection"                    # type: ExecuteCollectionFormatType_STAC
    OGC_COVERAGE = "ogc-coverage-collection"    # type: ExecuteCollectionFormatType_OGC_COVERAGE
    OGC_FEATURES = "ogc-features-collection"    # type: ExecuteCollectionFormatType_OGC_FEATURES
    OGC_MAP = "ogc-map-collection"              # type: ExecuteCollectionFormatType_OGC_MAP
    GEOJSON = "geojson-feature-collection"      # type: ExecuteCollectionFormatType_GEOJSON


def parse_prefer_header_return(headers):
    # type: (AnyHeadersContainer) -> Optional[AnyExecuteReturnPreference]
    """
    Get the return preference if specified.
    """
    prefer_header = get_header("prefer", headers)
    prefer_params = parse_kvp(prefer_header)
    prefer_return = prefer_params.get("return")
    if prefer_return:
        return ExecuteReturnPreference.get(prefer_return[0])


def parse_prefer_header_execute_mode(
    header_container,       # type: AnyHeadersContainer
    supported_modes=None,   # type: Optional[List[AnyExecuteControlOption]]
    wait_max=10,            # type: int
):                          # type: (...) -> Tuple[AnyExecuteMode, Optional[int], HeadersType]
    """
    Obtain execution preference if provided in request headers.

    .. seealso::
        - :term:`OGC API - Processes`: Core, Execution mode <
          https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execution_mode>`_.
          This defines all conditions how to handle ``Prefer`` against applicable :term:`Process` description.
        - :rfc:`7240#section-4.1` HTTP Prefer header ``respond-async``

    .. seealso::
        If ``Prefer`` format is valid, but server decides it cannot be respected, it can be transparently ignored
        (:rfc:`7240#section-2`). The server must respond with ``Preference-Applied`` indicating preserved preferences
        it decided to respect.

    :param header_container: Request headers to retrieve preference, if any available.
    :param supported_modes:
        Execute modes that are permitted for the operation that received the ``Prefer`` header.
        Resolved mode will respect this constraint following specification requirements of :term:`OGC API - Processes`.
    :param wait_max:
        Maximum wait time enforced by the server. If requested wait time is greater, ``wait`` preference will not be
        applied and will fall back to asynchronous response.
    :return:
        Tuple of resolved execution mode, wait time if specified, and header of applied preferences if possible.
        Maximum wait time indicates duration until synchronous response should fall back to asynchronous response.
    :raises HTTPBadRequest: If contents of ``Prefer`` are not valid.
    """

    prefer = get_header("prefer", header_container)
    relevant_modes = {ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC}
    supported_modes = list(set(supported_modes or []).intersection(relevant_modes))

    if not prefer:
        # /req/core/process-execute-default-execution-mode (A & B)
        if not supported_modes:
            return ExecuteMode.ASYNC, None, {}  # Weaver's default
        if len(supported_modes) == 1:
            mode = ExecuteMode.ASYNC if supported_modes[0] == ExecuteControlOption.ASYNC else ExecuteMode.SYNC
            wait = None if mode == ExecuteMode.ASYNC else wait_max
            return mode, wait, {}
        # /req/core/process-execute-default-execution-mode (C)
        return ExecuteMode.SYNC, wait_max, {}

    params = parse_kvp(prefer, pair_sep=",", multi_value_sep=None)
    wait = wait_max
    if "wait" in params:
        try:
            if any(param.isnumeric() for param in params):
                # 'wait=x,y,z' parsed as 'wait=x' and 'y' / 'z' parameters on their own
                # since 'wait' is the only referenced that users integers, it is guaranteed to be a misuse
                raise ValueError("Invalid 'wait' with comma-separated values.")
            if not len(params["wait"]) == 1:
                raise ValueError("Too many values.")
            wait = params["wait"][0]
            if not str.isnumeric(wait) or "." in wait or wait.startswith("-"):
                raise ValueError("Invalid integer for 'wait' in seconds.")
            wait = int(wait)
        except (TypeError, ValueError) as exc:
            raise HTTPBadRequest(json={
                "code": "InvalidParameterValue",
                "description": "HTTP Prefer header contains invalid 'wait' definition.",
                "error": type(exc).__name__,
                "cause": str(exc),
                "value": str(params["wait"]),
            })

    if wait > wait_max:
        LOGGER.info("Requested Prefer wait header too large (%ss > %ss), revert to async execution.", wait, wait_max)
        return ExecuteMode.ASYNC, None, {}

    auto = ExecuteMode.ASYNC if "respond-async" in params else ExecuteMode.SYNC
    applied_preferences = []
    # /req/core/process-execute-auto-execution-mode (A & B)
    if len(supported_modes) == 1:
        # supported mode is enforced, only indicate if it matches preferences to honour them
        # otherwise, server is allowed to discard preference since it cannot be honoured
        mode = ExecuteMode.ASYNC if supported_modes[0] == ExecuteControlOption.ASYNC else ExecuteMode.SYNC
        wait = None if mode == ExecuteMode.ASYNC else wait_max
        if auto == mode:
            if auto == ExecuteMode.ASYNC:
                applied_preferences.append("respond-async")
            if wait and "wait" in params:
                applied_preferences.append(f"wait={wait}")
        # /rec/core/process-execute-honor-prefer (A: async & B: wait)
        # https://datatracker.ietf.org/doc/html/rfc7240#section-3
        applied = {}
        if applied_preferences:
            applied = {"Preference-Applied": ", ".join(applied_preferences)}
        return mode, wait, applied

    # Weaver's default, at server's discretion when both mode are supported
    # /req/core/process-execute-auto-execution-mode (C)
    if len(supported_modes) == 2:
        if auto == ExecuteMode.ASYNC:
            return ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"}
        if wait and "wait" in params:
            return ExecuteMode.SYNC, wait, {"Preference-Applied": f"wait={wait}"}
        if wait:  # default used, not a supplied preference
            return ExecuteMode.SYNC, wait, {}
    return ExecuteMode.ASYNC, None, {}
