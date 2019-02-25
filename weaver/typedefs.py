from typing import Any, AnyStr, Dict, List, Union

JsonField = Union[AnyStr, int, float, bool, None]
JsonBody = Dict[AnyStr, Union[JsonField, Dict[AnyStr, Any], List[Any]]]

Settings = Dict[AnyStr, JsonField]
