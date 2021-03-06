from typing import TYPE_CHECKING

import lxml.etree

# define this type here so that code can use it for actual logic without repeating 'noqa'
XML = lxml.etree._Element  # noqa

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

    from celery.app import Celery
    from owslib.wps import Process as ProcessOWS
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

    # CWL definition
    CWL_IO_EnumType = TypedDict("CWL_IO_EnumType", {"type": str, "symbols": List[str]})  # "symbols" => allowed values
    CWL_IO_ArrayType = TypedDict("CWL_IO_ArrayType", {"type": str, "items": str})  # "items" => type of every item
    CWL_IO_MultiType = List[str, CWL_IO_ArrayType, CWL_IO_EnumType]  # single string allowed for "null"
    CWL_IO_DataType = Union[str, CWL_IO_ArrayType, CWL_IO_EnumType, CWL_IO_MultiType]
    CWL_Input_Type = TypedDict("CWL_Input_Type", {"id": str, "type": CWL_IO_DataType}, total=False)
    CWL_Output_Type = TypedDict("CWL_Output_Type", {"id": str, "type": CWL_IO_DataType}, total=False)
    CWL_Inputs = Union[List[CWL_Input_Type], Dict[str, CWL_Input_Type]]
    CWL_Outputs = Union[List[CWL_Output_Type], Dict[str, CWL_Output_Type]]
    CWL = TypedDict("CWL", {"cwlVersion": str, "class": str, "inputs": CWL_Inputs, "outputs": CWL_Outputs,
                            "requirements": JSON, "hints": JSON, "label": str, "doc": str, "s:keywords": str,
                            "$namespaces": Dict[str, str], "$schemas": Dict[str, str]}, total=False)

    # CWL loading
    GlobType = TypedDict("GlobType", {"glob": str})
    ExpectedOutputType = TypedDict("ExpectedOutputType",
                                   {"type": str, "id": str, "outputBinding": GlobType}, total=False)
    GetJobProcessDefinitionFunction = Callable[[str, Dict[str, str], Dict[str, Any]], WpsProcessInterface]
    ToolPathObjectType = Dict[str, Any]

    # CWL runtime
    CWL_RuntimeLiteral = Union[str, float, int]
    CWL_RuntimeInputFile = TypedDict("CWL_RuntimeInputFile",
                                     {"class": str, "location": str, "format": Optional[str],
                                      "basename": str, "nameroot": str, "nameext": str}, total=False)
    CWL_RuntimeOutputFile = TypedDict("CWL_RuntimeOutputFile",
                                      {"class": str, "location": str, "format": Optional[str],
                                       "basename": str, "nameroot": str, "nameext": str,
                                       "checksum": Optional[str], "size": Optional[str]}, total=False)
    CWL_RuntimeInput = Union[CWL_RuntimeLiteral, CWL_RuntimeInputFile]
    CWL_RuntimeOutput = Union[CWL_RuntimeLiteral, CWL_RuntimeOutputFile]

    KVP_Item = Union[ValueType, Sequence[ValueType]]
    KVP = Union[Sequence[Tuple[str, KVP_Item]], Dict[str, KVP_Item]]
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

    AnyProcess = Union[Process, ProcessOWS, ProcessWPS, JSON]
    AnyProcessType = Union[Type[Process], Type[ProcessWPS]]

    # update_status(provider, message, progress, status)
    UpdateStatusPartialFunction = Callable[[str, str, int, AnyStatusType], None]
