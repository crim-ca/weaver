from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from weaver.processes.wps_process_base import WpsProcessInterface
    from typing import Any, AnyStr, Callable, Dict, List, Union

    JsonField = Union[AnyStr, int, float, bool, None]
    JsonBody = Dict[AnyStr, Union[JsonField, Dict[AnyStr, Any], List[Any]]]

    Settings = Dict[AnyStr, JsonField]

    ExpectedOutputType = Dict[{'type': AnyStr, 'id': AnyStr, 'outputBinding': Dict['glob': AnyStr]}]
    GetJobProcessDefinitionFunction = Callable[[AnyStr, Dict[AnyStr, AnyStr], Dict[AnyStr, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[AnyStr, Any]
