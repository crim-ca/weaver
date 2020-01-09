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
    from cwltool.factory import Callable as CWLFactoryCallable  # noqa
    from webtest.response import TestResponse
    from pywps.app import WPSRequest
    from logging import Logger as LoggerType  # noqa
    from typing import Any, AnyStr, Callable, Dict, List, Optional, Tuple, Type, Union  # noqa: F401
    import lxml.etree
    import os
    if hasattr(os, "PathLike"):
        FileSystemPathType = Union[os.PathLike, AnyStr]
    else:
        FileSystemPathType = AnyStr

    Number = Union[int, float]
    AnyValue = Optional[Union[AnyStr, Number, bool]]
    AnyKey = Union[AnyStr, int]
    JSON = Dict[AnyKey, Union[AnyValue, Dict[AnyKey, "JSON"], List["JSON"]]]
    CWL = Dict[{"cwlVersion": AnyStr, "class": AnyStr, "inputs": JSON, "outputs": JSON}]
    XML = lxml.etree._Element  # noqa: W0212

    AnyContainer = Union[Configurator, Registry, PyramidRequest, Celery]
    SettingValue = AnyValue
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

    ExpectedOutputType = Dict[{"type": AnyStr, "id": AnyStr, "outputBinding": Dict["glob": AnyStr]}]
    GetJobProcessDefinitionFunction = Callable[[AnyStr, Dict[AnyStr, AnyStr], Dict[AnyStr, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[AnyStr, Any]

    UpdateStatusPartialFunction = Callable[[{"provider": AnyStr, "message": AnyStr,
                                             "progress": int, "status": AnyStatusType}], None]
