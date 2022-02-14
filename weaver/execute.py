from typing import TYPE_CHECKING

from weaver.base import Constants


class ExecuteMode(Constants):
    AUTO = "auto"
    ASYNC = "async"
    SYNC = "sync"


class ExecuteControlOption(Constants):
    ASYNC = "async-execute"
    SYNC = "sync-execute"


class ExecuteResponse(Constants):
    RAW = "raw"
    DOCUMENT = "document"


class ExecuteTransmissionMode(Constants):
    VALUE = "value"
    REFERENCE = "reference"


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
