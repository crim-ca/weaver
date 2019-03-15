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
    from celery import Celery
    from requests.structures import CaseInsensitiveDict
    # noinspection PyUnresolvedReferences
    from cwltool.factory import Callable as CWLFactoryCallable
    # noinspection PyPackageRequirements
    from webtest.response import TestResponse
    from pywps.app import WPSRequest
    # noinspection PyProtectedMember, PyUnresolvedReferences
    from logging import _loggerClass as LoggerType
    from typing import Any, AnyStr, Callable, Dict, List, Tuple, Union
    import lxml.etree
    import os
    if hasattr(os, 'PathLike'):
        FileSystemPathType = Union[os.PathLike, AnyStr]
    else:
        FileSystemPathType = AnyStr

    Number = Union[int, float]

    JsonKey = Union[AnyStr, int]
    JsonField = Union[AnyStr, Number, bool, None]
    JSON = Dict[JsonKey, Union[JsonField, Dict[JsonKey, 'JSON'], List['JSON']]]
    CWL = Dict[{"class": AnyStr, }]
    # noinspection PyProtectedMember
    XML = lxml.etree._Element

    AnyContainer = Union[Configurator, Registry, PyramidRequest, Celery]
    SettingValue = Union[AnyStr, Number, bool, None]
    SettingsType = Dict[AnyStr, SettingValue]
    AnySettingsContainer = Union[AnyContainer, SettingsType]
    AnyRegistryContainer = AnyContainer
    AnyDatabaseContainer = AnyContainer

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
