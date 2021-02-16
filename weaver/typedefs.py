from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    import typing
    from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, Union
    if hasattr(typing, "TypedDict"):
        from typing import TypedDict  # pylint: disable=E0611,no-name-in-module
    else:
        from typing_extensions import TypedDict
    if hasattr(os, "PathLike"):
        FileSystemPathType = Union[os.PathLike, str]
    else:
        FileSystemPathType = str

    import lxml.etree
    from celery.app import Celery
    from pyramid.httpexceptions import HTTPSuccessful, HTTPRedirection
    from pyramid.registry import Registry
    from pyramid.request import Request as PyramidRequest
    from pyramid.response import Response as PyramidResponse
    from pyramid.testing import DummyRequest
    from pyramid.config import Configurator
    from pywps.app import WPSRequest
    from pywps import Process as ProcessWPS
    from requests import Request as RequestsRequest
    from requests.structures import CaseInsensitiveDict
    from webob.headers import ResponseHeaders, EnvironHeaders
    from webob.response import Response as WebobResponse
    from webtest.response import TestResponse
    from werkzeug.wrappers import Request as WerkzeugRequest

    from weaver.processes.wps_process_base import WpsProcessInterface
    from weaver.datatype import Process
    from weaver.status import AnyStatusType

    # pylint: disable=C0103,invalid-name
    Number = Union[int, float]
    ValueType = Union[str, Number, bool]
    AnyValue = Optional[ValueType]
    AnyValueType = AnyValue  # alias
    AnyKey = Union[str, int]
    # add more levels of explicit definitions than necessary to simulate JSON recursive structure better than 'Any'
    # amount of repeated equivalent definition makes typing analysis 'work well enough' for most use cases
    _JsonObjectItem = Dict[str, Union["JSON", "_JsonListItem"]]
    _JsonListItem = List[Union[AnyValue, _JsonObjectItem, "_JsonListItem", "JSON"]]
    _JsonItem = Union[AnyValue, _JsonObjectItem, _JsonListItem]
    JSON = Union[Dict[str, _JsonItem], List[_JsonItem]]
    CWL = TypedDict("CWL", {"cwlVersion": str, "class": str, "inputs": JSON, "outputs": JSON,
                            "requirements": JSON, "hints": JSON, "label": str, "doc": str, "s:keywords": str,
                            "$namespaces": Dict[str, str], "$schemas": Dict[str, str]}, total=False)
    KVPType = Union[ValueType, Sequence[ValueType]]
    KVP = Union[Sequence[Tuple[str, KVPType]], Dict[str, KVPType]]
    XML = lxml.etree._Element  # noqa

    AnyContainer = Union[Configurator, Registry, PyramidRequest, Celery]
    SettingValue = Optional[Union[JSON, AnyValue]]
    SettingsType = Dict[str, SettingValue]
    AnySettingsContainer = Union[AnyContainer, SettingsType]
    AnyRegistryContainer = AnyContainer
    AnyDatabaseContainer = AnyContainer

    CookiesType = Dict[str, str]
    HeadersType = Dict[str, str]
    CookiesTupleType = List[Tuple[str, str]]
    HeadersTupleType = List[Tuple[str, str]]
    CookiesBaseType = Union[CookiesType, CookiesTupleType]
    HeadersBaseType = Union[HeadersType, HeadersTupleType]
    HeaderCookiesType = Union[HeadersBaseType, CookiesBaseType]
    HeaderCookiesTuple = Union[Tuple[None, None], Tuple[HeadersBaseType, CookiesBaseType]]
    AnyHeadersContainer = Union[HeadersBaseType, ResponseHeaders, EnvironHeaders, CaseInsensitiveDict]
    AnyCookiesContainer = Union[CookiesBaseType, WPSRequest, PyramidRequest, AnyHeadersContainer]
    AnyResponseType = Union[PyramidResponse, WebobResponse, TestResponse]
    AnyRequestType = Union[PyramidRequest, WerkzeugRequest, RequestsRequest, DummyRequest]
    HTTPValid = Union[HTTPSuccessful, HTTPRedirection]

    AnyProcess = Union[Process, ProcessWPS]
    AnyProcessType = Union[Type[Process], Type[ProcessWPS]]

    GlobType = TypedDict("GlobType", {"glob": str})
    ExpectedOutputType = TypedDict("ExpectedOutputType", {"type": str, "id": str, "outputBinding": GlobType})
    GetJobProcessDefinitionFunction = Callable[[str, Dict[str, str], Dict[str, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[str, Any]

    # update_status(provider, message, progress, status)
    UpdateStatusPartialFunction = Callable[[str, str, int, AnyStatusType], None]
