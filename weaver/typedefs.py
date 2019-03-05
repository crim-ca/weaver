from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from weaver.processes.wps_process_base import WpsProcessInterface
    from weaver.status import AnyStatusType
    from typing import Any, AnyStr, Callable, Dict, List, Union

    JsonField = Union[AnyStr, int, float, bool, None]
    JsonBody = Dict[AnyStr, Union[JsonField, Dict[AnyStr, Any], List[Any]]]

    CookiesType = Dict[AnyStr, AnyStr]

    Settings = Dict[AnyStr, JsonField]

    ExpectedOutputType = Dict[{'type': AnyStr, 'id': AnyStr, 'outputBinding': Dict['glob': AnyStr]}]
    GetJobProcessDefinitionFunction = Callable[[AnyStr, Dict[AnyStr, AnyStr], Dict[AnyStr, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[AnyStr, Any]

    UpdateStatusPartialFunction = Callable[[{'provider': AnyStr, 'message': AnyStr,
                                             'progress': int, 'status': AnyStatusType}], None]
