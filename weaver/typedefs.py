from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from weaver.processes.wps_process_base import WpsProcessInterface
    from weaver.datatype import Process
    from weaver.status import AnyStatusType
    from webob.headers import ResponseHeaders, EnvironHeaders
    from webob.response import Response as WebobResponse
    from pyramid.response import Response as PyramidResponse
    from pyramid.registry import Registry
    from pyramid.request import Request as PyramidRequest
    from pyramid.config import Configurator
    from celery.app import Celery
    from requests.structures import CaseInsensitiveDict
    from cwltool.factory import Callable as CWLFactoryCallable  # noqa: F401  # provide alias name, not used here
    from webtest.response import TestResponse
    from pywps.app import WPSRequest
    from pywps import Process as ProcessWPS
    from typing import Any, AnyStr, Callable, Dict, List, Optional, Tuple, Type, Union
    import typing
    if hasattr(typing, "TypedDict"):
        from typing import TypedDict  # pylint: disable=E0611,no-name-in-module
    else:
        from typing_extensions import TypedDict
    import lxml.etree
    import os
    if hasattr(os, "PathLike"):
        FileSystemPathType = Union[os.PathLike, AnyStr]
    else:
        FileSystemPathType = AnyStr

    Number = Union[int, float]
    ValueType = Union[AnyStr, Number, bool]
    AnyValue = Optional[ValueType]
    AnyKey = Union[AnyStr, int]
    JsonList = List["JSON"]
    JsonObject = Dict[AnyStr, "JSON"]
    JSON = Union[AnyValue, JsonObject, JsonList]
    CWL = TypedDict("CWL", {"cwlVersion": AnyStr, "class": AnyStr, "inputs": JSON, "outputs": JSON})
    XML = lxml.etree._Element  # noqa: W0212

    AnyContainer = Union[Configurator, Registry, PyramidRequest, Celery]
    SettingValue = Optional[JSON]
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

    AnyProcess = Union[Process, ProcessWPS]
    AnyProcessType = Union[Type[Process], Type[ProcessWPS]]

    GlobType = TypedDict("GlobType", {"glob": AnyStr})
    ExpectedOutputType = TypedDict("ExpectedOutputType", {"type": AnyStr, "id": AnyStr, "outputBinding": GlobType})
    GetJobProcessDefinitionFunction = Callable[[AnyStr, Dict[AnyStr, AnyStr], Dict[AnyStr, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[AnyStr, Any]

    # update_status(provider, message, progress, status)
    UpdateStatusPartialFunction = Callable[[AnyStr, AnyStr, int, AnyStatusType], None]
