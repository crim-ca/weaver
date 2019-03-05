from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from weaver.processes.wps_process_base import WpsProcessInterface
    from weaver.status import AnyStatusType
    from webob.headers import ResponseHeaders, EnvironHeaders
    from webob.response import Response as WebobResponse
    from pyramid.response import Response as PyramidResponse
    from pyramid.registry import Registry
    from pyramid.request import Request as PyramidRequest
    from pyramid.config import Configurator
    from requests.structures import CaseInsensitiveDict
    # noinspection PyPackageRequirements
    from webtest.response import TestResponse
    from pywps.app import WPSRequest
    from typing import Any, AnyStr, Callable, Dict, List, Tuple, Union

    JsonField = Union[AnyStr, int, float, bool, None]
    JsonBody = Dict[AnyStr, Union[JsonField, Dict[AnyStr, Any], List[Any]]]

    SettingValue = Union[AnyStr, int, float, bool, None]
    SettingsType = Dict[AnyStr, SettingValue]
    AnySettingsContainer = Union[Configurator, Registry, PyramidRequest, SettingsType]

    CookiesType = Dict[AnyStr, AnyStr]
    HeadersType = Dict[AnyStr, AnyStr]
    CookiesTupleType = List[Tuple[AnyStr, AnyStr]]
    HeadersTupleType = List[Tuple[AnyStr, AnyStr]]
    CookiesBaseType = Union[CookiesType, CookiesTupleType]
    HeadersBaseType = Union[HeadersType, HeadersTupleType]
    OptionalHeaderCookiesType = Union[Tuple[None, None], Tuple[HeadersBaseType, CookiesBaseType]]
    AnyHeadersContainer = Union[HeadersBaseType, ResponseHeaders, EnvironHeaders, CaseInsensitiveDict]
    AnyCookiesContainer = Union[CookiesBaseType, WPSRequest, PyramidRequest, AnyHeadersContainer]
    AnyResponseType = Union[WebobResponse, PyramidResponse, TestResponse]

    ExpectedOutputType = Dict[{'type': AnyStr, 'id': AnyStr, 'outputBinding': Dict['glob': AnyStr]}]
    GetJobProcessDefinitionFunction = Callable[[AnyStr, Dict[AnyStr, AnyStr], Dict[AnyStr, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[AnyStr, Any]

    UpdateStatusPartialFunction = Callable[[{'provider': AnyStr, 'message': AnyStr,
                                             'progress': int, 'status': AnyStatusType}], None]
