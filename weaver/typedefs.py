from typing import TYPE_CHECKING  # pragma: no cover

# FIXME:
#  replace invalid 'Optional' (type or None) used instead of 'NotRequired' (optional key) when better supported
#  https://youtrack.jetbrains.com/issue/PY-53611/Support-PEP-655-typingRequiredtypingNotRequired-for-TypedDicts
if TYPE_CHECKING:
    import os
    import sys
    import typing
    import uuid
    from datetime import datetime
    from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, TypeVar, Union

    import psutil
    from typing_extensions import Literal, NotRequired, ParamSpec, Protocol, Required, TypeAlias, TypedDict

    from weaver.compat import Version

    if hasattr(os, "PathLike"):
        FileSystemPathType = Union[os.PathLike, str]
    else:
        FileSystemPathType = str

    MemoryInfo = Any
    if sys.platform == "win32":
        try:
            MemoryInfo = psutil._psutil_windows._pfullmem  # noqa: W0212
        except (AttributeError, ImportError, NameError):
            pass
    if MemoryInfo is Any:
        try:
            MemoryInfo = psutil._pslinux.pfullmem  # noqa: W0212
        except (AttributeError, ImportError, NameError):
            pass
    if MemoryInfo is Any:
        if TypedDict is Dict:
            MemoryInfo = Dict[str, int]
        else:
            MemoryInfo = TypedDict("MemoryInfo", {
                "rss": int,
                "uss": int,
                "vms": int,
            }, total=False)
    TimesCPU = psutil._common.pcputimes  # noqa: W0212

    from celery.app import Celery
    from celery.result import AsyncResult, EagerResult, GroupResult, ResultSet
    from owslib.wps import BoundingBoxDataInput, ComplexDataInput, Process as ProcessOWS, WPSExecution
    from pyramid.httpexceptions import HTTPException, HTTPSuccessful, HTTPRedirection
    from pyramid.registry import Registry
    from pyramid.request import Request as PyramidRequest
    from pyramid.response import Response as PyramidResponse
    from pyramid.testing import DummyRequest
    from pyramid.config import Configurator
    from pywps import Process as ProcessWPS
    from pywps.app import WPSRequest
    from pywps.inout import BoundingBoxInput, ComplexInput, LiteralInput
    from requests import PreparedRequest, Request as RequestsRequest
    from requests.models import Response as RequestsResponse
    from requests.structures import CaseInsensitiveDict
    from webob.acceptparse import AcceptLanguageNoHeader, AcceptLanguageValidHeader, AcceptLanguageInvalidHeader
    from webob.headers import ResponseHeaders, EnvironHeaders
    from webob.response import Response as WebobResponse
    from webtest.response import TestResponse
    from werkzeug.wrappers import Request as WerkzeugRequest

    from weaver.execute import AnyExecuteControlOption, AnyExecuteMode, AnyExecuteResponse, AnyExecuteTransmissionMode
    from weaver.processes.constants import CWL_RequirementNames
    from weaver.processes.wps_process_base import WpsProcessInterface
    from weaver.datatype import Process
    from weaver.status import AnyStatusType
    from weaver.visibility import AnyVisibility

    Path = Union[os.PathLike, str, bytes]

    Default = TypeVar("Default")  # used for return value that is employed from a provided default value
    Params = ParamSpec("Params")  # use with 'Callable[Params, Return]', 'Params.args' and 'Params.kwargs'
    Return = TypeVar("Return")    # alias to identify the same return value as a decorated/wrapped function
    AnyCallable = TypeVar("AnyCallable", bound=Callable[..., Any])  # callable used for decorated/wrapped functions
    AnyCallableWrapped = Callable[Params, Return]
    AnyCallableAnyArgs = Union[Callable[[], Return], Callable[[..., Any], Return]]

    # pylint: disable=C0103,invalid-name
    Number = Union[int, float]
    ValueType = Union[str, Number, bool]
    AnyValueType = Optional[ValueType]  # avoid naming ambiguity with PyWPS AnyValue
    AnyKey = Union[str, int]
    AnyUUID = Union[str, uuid.UUID]
    AnyVersion = Union[Version, Number, str, Tuple[int, ...], List[int]]
    # add more levels of explicit definitions than necessary to simulate JSON recursive structure better than 'Any'
    # amount of repeated equivalent definition makes typing analysis 'work well enough' for most use cases
    _JSON: TypeAlias = "JSON"
    _JsonObjectItemAlias: TypeAlias = "_JsonObjectItem"
    _JsonListItemAlias: TypeAlias = "_JsonListItem"
    _JsonObjectItem = Dict[str, Union[AnyValueType, _JSON, _JsonObjectItemAlias, _JsonListItemAlias]]
    _JsonListItem = List[Union[AnyValueType, _JSON, _JsonObjectItem, _JsonListItemAlias]]
    _JsonItem = Union[AnyValueType, _JSON, _JsonObjectItem, _JsonListItem]
    JSON = Union[Dict[str, Union[_JSON, _JsonItem]], List[Union[_JSON, _JsonItem]], AnyValueType]

    Link = TypedDict("Link", {
        "title": str,
        "rel": Required[str],
        "href": Required[str],
        "hreflang": NotRequired[str],
        "type": NotRequired[str],  # IANA Media-Type
    }, total=False)
    Metadata = TypedDict("Metadata", {
        "title": str,
        "role": str,  # URL
        "href": str,
        "hreflang": str,
        "rel": str,
        "value": str,
        "lang": NotRequired[str],
        "type": NotRequired[str],
    }, total=False)

    LogLevelStr = Literal[
        "CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG",
        "critical", "fatal", "error", "warn", "warning", "info", "debug"
    ]
    AnyLogLevel = Union[LogLevelStr, int]

    # CWL definition
    GlobType = TypedDict("GlobType", {"glob": Union[str, List[str]]}, total=False)
    CWL_IO_FileValue = TypedDict("CWL_IO_FileValue", {
        "class": str,
        "path": str,
        "format": NotRequired[Optional[str]],
    }, total=True)
    CWL_IO_Value = Union[AnyValueType, List[AnyValueType], CWL_IO_FileValue, List[CWL_IO_FileValue]]
    CWL_IO_LiteralType = Literal["string", "boolean", "float", "int", "integer", "long", "double"]
    CWL_IO_ComplexType = Literal["File", "Directory"]
    CWL_IO_SpecialType = Literal["null", "Any"]
    CWL_IO_ArrayBaseType = Literal["array"]
    CWL_IO_BaseType = Union[CWL_IO_LiteralType, CWL_IO_ComplexType, CWL_IO_ArrayBaseType, CWL_IO_SpecialType]
    CWL_IO_NullableType = Union[str, List[CWL_IO_BaseType]]  # "<type>?" or ["<type>", "null"]
    CWL_IO_NestedType = TypedDict("CWL_IO_NestedType", {"type": CWL_IO_NullableType}, total=True)
    CWL_IO_EnumSymbols = Union[List[str], List[int], List[float]]
    CWL_IO_EnumType = TypedDict("CWL_IO_EnumType", {
        "type": Literal["enum"],
        "symbols": CWL_IO_EnumSymbols,
    })
    CWL_IO_ArrayType = TypedDict("CWL_IO_ArrayType", {
        "type": CWL_IO_ArrayBaseType,
        "items": Union[str, CWL_IO_EnumType],  # "items" => type of every item
    })
    CWL_IO_TypeItem = Union[str, CWL_IO_NestedType, CWL_IO_ArrayType, CWL_IO_EnumType]
    CWL_IO_DataType = Union[CWL_IO_TypeItem, List[CWL_IO_TypeItem]]
    CWL_Input_Type = TypedDict("CWL_Input_Type", {
        "id": NotRequired[str],     # representation used by plain CWL definition
        "name": NotRequired[str],   # representation used by parsed tool instance
        "type": CWL_IO_DataType,
        "items": NotRequired[Union[str, CWL_IO_EnumType]],
        "symbols": NotRequired[CWL_IO_EnumSymbols],
        "format": NotRequired[Optional[Union[str, List[str]]]],
        "inputBinding": NotRequired[Any],
        "default": NotRequired[Optional[AnyValueType]],
    }, total=False)
    CWL_Output_Type = TypedDict("CWL_Output_Type", {
        "id": NotRequired[str],    # representation used by plain CWL definition
        "name": NotRequired[str],  # representation used by parsed tool instance
        "type": CWL_IO_DataType,
        "format": NotRequired[Optional[Union[str, List[str]]]],
        "outputBinding": NotRequired[GlobType]
    }, total=False)
    CWL_Inputs = Union[List[CWL_Input_Type], Dict[str, CWL_Input_Type]]
    CWL_Outputs = Union[List[CWL_Output_Type], Dict[str, CWL_Output_Type]]

    # 'requirements' includes 'hints'
    CWL_Requirement = TypedDict("CWL_Requirement", {
        "class": Required[CWL_RequirementNames],
        "provider": NotRequired[str],
        "process": NotRequired[str],
    }, total=False)
    CWL_RequirementsDict = Dict[CWL_RequirementNames, Dict[str, ValueType]]   # {'<req>': {<param>: <val>}}
    CWL_RequirementsList = List[CWL_Requirement]       # [{'class': <req>, <param>: <val>}]
    CWL_AnyRequirements = Union[CWL_RequirementsDict, CWL_RequirementsList]
    CWL_Class = Literal["CommandLineTool", "ExpressionTool", "Workflow"]
    CWL_WorkflowStep = TypedDict("CWL_WorkflowStep", {
        "run": str,
        "in": Dict[str, str],   # mapping of <step input: workflow input | other-step output>
        "out": List[str],       # output to retrieve from step, for mapping with other steps
    })
    CWL_WorkflowStepID = str
    CWL_WorkflowStepReference = TypedDict("CWL_WorkflowStepReference", {
        "name": CWL_WorkflowStepID,
        "reference": str,  # URL
    })
    _CWL = "CWL"  # type: TypeAlias
    CWL_Graph = List[_CWL]
    CWL = TypedDict("CWL", {
        "cwlVersion": Required[str],
        "class": Required[CWL_Class],
        "label": str,
        "doc": str,
        "id": NotRequired[str],
        "intent": NotRequired[str],
        "s:keywords": List[str],
        "baseCommand": NotRequired[Optional[Union[str, List[str]]]],
        "parameters": NotRequired[List[str]],
        "requirements": NotRequired[CWL_AnyRequirements],
        "hints": NotRequired[CWL_AnyRequirements],
        "inputs": CWL_Inputs,
        "outputs": CWL_Outputs,
        "steps": NotRequired[Dict[CWL_WorkflowStepID, CWL_WorkflowStep]],
        "stderr": NotRequired[str],
        "stdout": NotRequired[str],
        "$namespaces": NotRequired[Dict[str, str]],
        "$schemas": NotRequired[Dict[str, str]],
        "$graph": NotRequired[CWL_Graph],
    }, total=False)
    CWL_WorkflowStepPackage = TypedDict("CWL_WorkflowStepPackage", {
        "id": str,          # reference ID of the package
        "package": CWL      # definition of the package as sub-step of a Workflow
    })
    CWL_WorkflowStepPackageMap = Dict[CWL_WorkflowStepID, CWL_WorkflowStepPackage]

    # JSON-like CWL definition employed by cwltool
    try:
        from ruamel.yaml.comments import CommentedMap

        CWL_ToolPathObject = CommentedMap
    except (AttributeError, ImportError, NameError):
        CWL_ToolPathObject = CWL

    # CWL runtime
    CWL_RuntimeLiteral = AnyValueType
    CWL_RuntimeLiteralItem = Union[CWL_RuntimeLiteral, List[CWL_RuntimeLiteral]]
    CWL_RuntimeLiteralObject = TypedDict("CWL_RuntimeLiteralObject", {
        "id": str,
        "value": CWL_RuntimeLiteralItem,
    }, total=False)
    CWL_RuntimeInputFile = TypedDict("CWL_RuntimeInputFile", {
        "id": NotRequired[str],
        "class": Required[Literal["File"]],
        "location": Required[str],
        "format": NotRequired[Optional[str]],
        "basename": NotRequired[str],
        "nameroot": NotRequired[str],
        "nameext": NotRequired[str],
    }, total=False)
    CWL_RuntimeOutputFile = TypedDict("CWL_RuntimeOutputFile", {
        "class": Required[Literal["File"]],
        "location": Required[str],
        "format": NotRequired[Optional[str]],
        "basename": NotRequired[str],
        "nameroot": NotRequired[str],
        "nameext": NotRequired[str],
        "checksum": NotRequired[str],
        "size": NotRequired[int],
    }, total=False)
    CWL_RuntimeInputDirectory = TypedDict("CWL_RuntimeInputDirectory", {
        "id": NotRequired[str],
        "class": Required[Literal["Directory"]],
        "location": Required[str],
        "format": NotRequired[Optional[str]],
        "nameroot": NotRequired[str],
        "nameext": NotRequired[str],
        "basename": NotRequired[str],
        "listing": List[CWL_RuntimeInputFile],
    }, total=False)
    CWL_RuntimeOutputDirectory = TypedDict("CWL_RuntimeOutputDirectory", {
        "class": Required[Literal["Directory"]],
        "location": Required[str],
        "format": NotRequired[Optional[str]],
        "basename": NotRequired[str],
        "nameroot": NotRequired[str],
        "nameext": NotRequired[str],
        "checksum": NotRequired[str],
        "size": NotRequired[Literal[0]],
        "listing": List[CWL_RuntimeOutputFile],
    }, total=False)
    CWL_RuntimeInput = Union[CWL_RuntimeLiteralItem, CWL_RuntimeInputFile, CWL_RuntimeInputDirectory]
    CWL_RuntimeInputsMap = Dict[str, CWL_RuntimeInput]
    CWL_RuntimeInputList = List[Union[CWL_RuntimeLiteralObject, CWL_RuntimeInputFile, CWL_RuntimeInputDirectory]]
    CWL_RuntimeOutput = Union[CWL_RuntimeLiteral, CWL_RuntimeOutputFile, CWL_RuntimeOutputDirectory]
    CWL_Results = Dict[str, CWL_RuntimeOutput]

    # CWL loading
    CWL_WorkflowInputs = CWL_RuntimeInputsMap   # mapping of ID:value (any type)
    CWL_ExpectedOutputs = Dict[str, str]        # mapping of ID:glob-pattern (File/Directory only)
    JobProcessDefinitionCallback = Callable[[str, Dict[str, str], Dict[str, Any]], WpsProcessInterface]

    # OWSLib Execution
    # inputs of OWSLib are either a string (any literal type, bbox or complex file)
    OWS_InputData = Union[str, BoundingBoxDataInput, ComplexDataInput]
    OWS_InputDataValues = List[Tuple[str, OWS_InputData]]

    AnyInputData = Union[OWS_InputData, BoundingBoxInput, ComplexInput, LiteralInput]

    # PyWPS Execution
    WPS_InputData = Tuple[str, AnyInputData]
    WPS_OutputAsRef = Tuple[str, Optional[bool]]                            # (output_id, as_ref)
    WPS_OutputAsRefMimeType = Tuple[str, Optional[bool], Optional[str]]     # (output_id, as_ref, mime_type)
    WPS_OutputRequested = Union[WPS_OutputAsRef, WPS_OutputAsRefMimeType]

    KVP_Item = Union[ValueType, Sequence[ValueType]]
    KVP_Container = Union[Sequence[Tuple[str, KVP_Item]], Dict[str, KVP_Item]]
    KVP = Dict[str, List[KVP_Item]]

    AnyContainer = Union[Configurator, Registry, PyramidRequest, WerkzeugRequest, Celery]
    SettingValue = Optional[Union[JSON, AnyValueType]]
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
    AnyRequestType = Union[PyramidRequest, WerkzeugRequest, PreparedRequest, RequestsRequest, DummyRequest]
    AnyResponseType = Union[PyramidResponse, WebobResponse, RequestsResponse, TestResponse]
    AnyViewResponse = Union[PyramidResponse, WebobResponse, HTTPException]
    RequestMethod = Literal[
        "HEAD", "GET", "POST", "PUT", "PATCH", "DELETE",
        "head", "get", "post", "put", "patch", "delete",
    ]
    AnyRequestMethod = Union[RequestMethod, str]
    HTTPValid = Union[HTTPSuccessful, HTTPRedirection]

    AnyAcceptLanguageHeader = Union[AcceptLanguageNoHeader, AcceptLanguageValidHeader, AcceptLanguageInvalidHeader]

    AnyProcess = Union[Process, ProcessOWS, ProcessWPS, JSON]
    AnyProcessRef = Union[Process, str]
    AnyProcessClass = Union[Type[Process], Type[ProcessWPS], Type[str]]

    # update_status(message, progress, status, *args, **kwargs)
    UpdateStatusPartialFunction = TypeVar(
        "UpdateStatusPartialFunction",
        bound=Callable[[str, Number, AnyStatusType, ..., Any], None]
    )

    DatetimeIntervalType = TypedDict("DatetimeIntervalType", {
        "before": datetime,
        "after": datetime,
        "match": datetime
    }, total=False)

    # data source configuration
    DataSourceFileRef = TypedDict("DataSourceFileRef", {
        "ades": str,                    # target ADES to dispatch
        "netloc": str,                  # definition to match file references against
        "default": NotRequired[bool],   # default ADES when no match was possible (single one allowed in config)
    }, total=True)
    DataSourceOpenSearch = TypedDict("DataSourceOpenSearch", {
        "ades": str,                                # target ADES to dispatch
        "netloc": str,                              # where to send OpenSearch request
        "collection_id": NotRequired[str],          # OpenSearch collection ID to match against
        "default": NotRequired[bool],               # default ADES when no match was possible (single one allowed)
        "accept_schemes": NotRequired[List[str]],   # allowed URL schemes (http, https, etc.)
        "mime_types": NotRequired[List[str]],       # allowed Media-Types (text/xml, application/json, etc.)
        "rootdir": str,                             # root position of the data to retrieve
        "osdd_url": str,                            # global OpenSearch description document to employ
    }, total=True)
    DataSource = Union[DataSourceFileRef, DataSourceOpenSearch]
    DataSourceConfig = Dict[str, DataSource]  # JSON/YAML file contents

    JobValueFormat = TypedDict("JobValueFormat", {
        "mime_type": NotRequired[str],
        "media_type": NotRequired[str],
        "mimeType": NotRequired[str],
        "mediaType": NotRequired[str],
        "encoding": NotRequired[str],
        "schema": NotRequired[str],
        "extension": NotRequired[str],
    }, total=False)
    JobValueFile = TypedDict("JobValueFile", {
        "href": str,
        "format": NotRequired[JobValueFormat],
    }, total=False)
    JobValueData = TypedDict("JobValueData", {
        "data": AnyValueType,
    }, total=False)
    JobValueValue = TypedDict("JobValueValue", {
        "value": AnyValueType,
    }, total=False)
    JobValueObject = Union[JobValueData, JobValueValue, JobValueFile]
    JobValueFileItem = TypedDict("JobValueFileItem", {
        "id": Required[str],
        "href": Required[str],
        "format": NotRequired[JobValueFormat],
    }, total=False)
    JobValueDataItem = TypedDict("JobValueDataItem", {
        "id": Required[str],
        "data": Required[AnyValueType],
    }, total=False)
    JobValueValueItem = TypedDict("JobValueValueItem", {
        "id": Required[str],
        "value": Required[AnyValueType],
    }, total=False)
    JobValueItem = Union[JobValueDataItem, JobValueFileItem, JobValueValueItem]
    JobExpectItem = TypedDict("JobExpectItem", {"id": str}, total=True)
    JobInputItem = Union[JobValueItem, Dict[str, AnyValueType]]
    JobInputs = List[JobInputItem]
    JobOutputItem = Union[JobExpectItem, Dict[str, AnyValueType]]
    JobOutputs = List[JobOutputItem]
    JobResults = List[JobValueItem]
    JobMonitorReference = Any  # typically a URI of the remote job status or an execution object/handler

    # when schema='weaver.processes.constants.ProcessSchema.OGC'
    ExecutionInputsMap = Dict[str, Union[JobValueObject, List[JobValueObject]]]
    # when schema='weaver.processes.constants.ProcessSchema.OLD'
    ExecutionInputsList = List[JobValueItem]
    ExecutionInputs = Union[ExecutionInputsList, ExecutionInputsMap]

    ExecutionOutputObject = TypedDict("ExecutionOutputObject", {
        "transmissionMode": str
    }, total=False)
    ExecutionOutputItem = TypedDict("ExecutionOutputItem", {
        "id": str,
        "transmissionMode": AnyExecuteTransmissionMode,
        "format": NotRequired[JobValueFormat],
    }, total=False)
    ExecutionOutputsList = List[ExecutionOutputItem]
    ExecutionOutputsMap = Dict[str, ExecutionOutputObject]
    ExecutionOutputs = Union[ExecutionOutputsList, ExecutionOutputsMap]
    ExecutionResultObjectRef = TypedDict("ExecutionResultObjectRef", {
        "href": Optional[str],
        "type": NotRequired[str],
    }, total=False)
    ExecutionResultObjectValue = TypedDict("ExecutionResultObjectValue", {
        "value": Optional[AnyValueType],
        "type": NotRequired[str],
    }, total=False)
    ExecutionResultObject = Union[ExecutionResultObjectRef, ExecutionResultObjectValue]
    ExecutionResultArray = List[ExecutionResultObject]
    ExecutionResultValue = Union[ExecutionResultObject, ExecutionResultArray]
    ExecutionResults = Dict[str, ExecutionResultValue]

    # reference employed as 'JobMonitorReference' by 'WPS1Process'
    JobExecution = TypedDict("JobExecution", {"execution": WPSExecution})

    # quoting
    QuoteProcessParameters = TypedDict("QuoteProcessParameters", {
        "inputs": JobInputs,
        "outputs": JobOutputs,
    })

    # job execution statistics
    ApplicationStatistics = TypedDict("ApplicationStatistics", {
        "usedMemory": str,
        "usedMemoryBytes": int,
    }, total=True)
    ProcessStatistics = TypedDict("ProcessStatistics", {
        "rss": str,
        "rssBytes": int,
        "uss": str,
        "ussBytes": int,
        "vms": str,
        "vmsBytes": int,
        "usedThreads": int,
        "usedCPU": int,
        "usedHandles": int,
        "usedMemory": str,
        "usedMemoryBytes": int,
        "totalSize": str,
        "totalSizeBytes": int,
    }, total=False)
    OutputStatistics = TypedDict("OutputStatistics", {
        "size": str,
        "sizeBytes": int,
    }, total=True)
    Statistics = TypedDict("Statistics", {
        "application": NotRequired[ApplicationStatistics],
        "process": NotRequired[ProcessStatistics],
        "outputs": Dict[str, OutputStatistics],
    }, total=False)

    CeleryResult = Union[AsyncResult, EagerResult, GroupResult, ResultSet]

    # simple/partial definitions of OpenAPI schema
    _OpenAPISchema: TypeAlias = "OpenAPISchema"
    _OpenAPISchemaProperty: TypeAlias = "OpenAPISchemaProperty"
    OpenAPISchemaTypes = Literal["object", "array", "boolean", "integer", "number", "string"]
    OpenAPISchemaReference = TypedDict("OpenAPISchemaReference", {
        "$ref": str
    }, total=True)
    OpenAPISchemaMetadata = TypedDict("OpenAPISchemaMetadata", {
        "$id": NotRequired[str],        # reference to external '$ref' after local resolution for tracking
        "$schema": NotRequired[str],    # how to parse schema (usually: 'https://json-schema.org/draft/2020-12/schema')
        "@context": NotRequired[str],   # extra details or JSON-LD references
    }, total=False)
    OpenAPISchemaProperty = TypedDict("OpenAPISchemaProperty", {
        "type": OpenAPISchemaTypes,
        "format": NotRequired[str],
        "default": NotRequired[Any],
        "example": NotRequired[Any],
        "title": NotRequired[str],
        "description": NotRequired[str],
        "enum": NotRequired[List[Union[str, Number]]],
        "items": NotRequired[List[_OpenAPISchema, OpenAPISchemaReference]],
        "required": NotRequired[List[str]],
        "nullable": NotRequired[bool],
        "deprecated": NotRequired[bool],
        "readOnly": NotRequired[bool],
        "writeOnly": NotRequired[bool],
        "multipleOf": NotRequired[Number],
        "minimum": NotRequired[Number],
        "maximum": NotRequired[Number],
        "exclusiveMinimum": NotRequired[bool],
        "exclusiveMaximum": NotRequired[bool],
        "minLength": NotRequired[Number],
        "maxLength": NotRequired[Number],
        "pattern": NotRequired[str],
        "minItems": NotRequired[Number],
        "maxItems": NotRequired[Number],
        "uniqueItems": NotRequired[bool],
        "minProperties": NotRequired[Number],
        "maxProperties": NotRequired[Number],
        "contentMediaType": NotRequired[str],
        "contentEncoding": NotRequired[str],
        "contentSchema": NotRequired[str],
        "properties": NotRequired[Dict[str, _OpenAPISchemaProperty]],
        "additionalProperties": NotRequired[Union[bool, Dict[str, Union[_OpenAPISchema, OpenAPISchemaReference]]]],
    }, total=False)
    _OpenAPISchemaObject = TypedDict("_OpenAPISchemaObject", {
        "type": Literal["object"],
        "properties": Dict[str, OpenAPISchemaProperty],
    }, total=False)
    OpenAPISchemaObject = Union[_OpenAPISchemaObject, OpenAPISchemaProperty]
    OpenAPISchemaArray = TypedDict("OpenAPISchemaArray", {
        "type": Literal["array"],
        "items": _OpenAPISchema,
    }, total=False)
    OpenAPISchemaAllOf = TypedDict("OpenAPISchemaAllOf", {
        "allOf": List[Union[_OpenAPISchema, OpenAPISchemaReference]],
    }, total=False)
    OpenAPISchemaAnyOf = TypedDict("OpenAPISchemaAnyOf", {
        "anyOf": List[Union[_OpenAPISchema, OpenAPISchemaReference]],
    }, total=False)
    OpenAPISchemaOneOf = TypedDict("OpenAPISchemaOneOf", {
        "oneOf": List[Union[_OpenAPISchema, OpenAPISchemaReference]],
    }, total=False)
    OpenAPISchemaNot = TypedDict("OpenAPISchemaNot", {
        "not": Union[_OpenAPISchema, OpenAPISchemaReference],
    }, total=False)
    OpenAPISchemaKeyword = Union[
        OpenAPISchemaAllOf,
        OpenAPISchemaAnyOf,
        OpenAPISchemaOneOf,
        OpenAPISchemaNot,
    ]
    OpenAPISchema = Union[
        OpenAPISchemaMetadata,
        OpenAPISchemaObject,
        OpenAPISchemaArray,
        OpenAPISchemaKeyword,
        OpenAPISchemaProperty,
        OpenAPISchemaReference,
    ]
    OpenAPISpecLicence = TypedDict("OpenAPISpecLicence", {
        "name": str,
        "url": str,
    }, total=True)
    OpenAPISpecContact = TypedDict("OpenAPISpecContact", {
        "name": str,
        "email": str,
        "url": str,
    }, total=True)
    OpenAPISpecInfo = TypedDict("OpenAPISpecInfo", {
        "description": NotRequired[str],
        "licence": OpenAPISpecLicence,
        "contact": OpenAPISpecContact,
        "title": str,
        "version": str,
    }, total=True)
    OpenAPISpecContent = TypedDict("OpenAPISpecContent", {
        "schema": OpenAPISchema,
    }, total=True)
    OpenAPISpecResponse = TypedDict("OpenAPISpecResponse", {
        "summary": NotRequired[str],
        "description": NotRequired[str],
        "content": Dict[str, Union[OpenAPISpecContent, OpenAPISchemaReference]],  # Media-Type keys
    }, total=True)
    OpenAPISpecRequestBody = TypedDict("OpenAPISpecRequestBody", {
        "summary": NotRequired[str],
        "description": NotRequired[str],
        "content": Dict[str, Union[OpenAPISpecContent, OpenAPISchemaReference]],  # Media-Type keys
    }, total=True)
    OpenAPISpecPath = TypedDict("OpenAPISpecPath", {
        "responses": Dict[str, OpenAPISpecResponse],  # HTTP code keys
        "parameters": List[Union[OpenAPISchema, OpenAPISchemaReference]],
        "summary": str,
        "description": str,
        "tags": List[str],
    }, total=True)
    OpenAPISpecPathMethods = TypedDict("OpenAPISpecPathMethods", {
        "head": NotRequired[OpenAPISpecPath],
        "get": NotRequired[OpenAPISpecPath],
        "post": NotRequired[OpenAPISpecPath],
        "put": NotRequired[OpenAPISpecPath],
        "patch": NotRequired[OpenAPISpecPath],
        "delete": NotRequired[OpenAPISpecPath],
        "options": NotRequired[OpenAPISpecPath],
    }, total=True)
    OpenAPISpecExample = TypedDict("OpenAPISpecExample", {
        "description": NotRequired[str],
        "summary": str,
        "value": JSON,
        "externalValue": NotRequired[str],
    }, total=True)
    OpenAPISpecParamStyle = Literal[
        # path
        "matrix",
        "label",
        "simple",  # header also
        # query
        "form",    # cookie also
        "spaceDelimited",
        "pipeDelimited",
        "deepObject",
    ]
    OpenAPISpecParameter = TypedDict("OpenAPISpecParameter", {
        "name": str,
        "in": Literal["header", "cookie", "query", "path", "body"],
        "required": bool,
        "style": NotRequired[OpenAPISpecParamStyle],
        "allowReserved": NotRequired[bool],
        "default": NotRequired[JSON],   # Swagger 2.0, OpenAPI 3.0: nest under 'schema'
        "summary": NotRequired[str],
        "description": NotRequired[str],
        "type": NotRequired[str],  # Swagger 2.0
        "schema": OpenAPISchema,   # OpenAPI 3.0, 'content' alternative available
        "content": NotRequired[Dict[str, OpenAPISchema]],  # Media-Type keys
        "example": NotRequired[JSON],
        "examples": NotRequired[Dict[str, Union[OpenAPISpecExample, OpenAPISchemaReference]]],
    }, total=True)
    OpenAPISpecHeader = TypedDict("OpenAPISpecHeader", {
        "summary": NotRequired[str],
        "description": NotRequired[str],
        "required": NotRequired[bool],
        "deprecated": NotRequired[bool],
        "allowEmptyValue": NotRequired[bool],
        "allowReserved": NotRequired[bool],
        "style": NotRequired[Literal["simple"]],
        "explode": NotRequired[bool],
        "schema": OpenAPISchema,
        "content": NotRequired[Dict[str, Union[OpenAPISpecContent, OpenAPISchemaReference]]],  # Media-Type keys
        "example": NotRequired[JSON],
        "examples": NotRequired[Dict[str, Union[OpenAPISpecExample, OpenAPISchemaReference]]],
    }, total=True)
    OpenAPISpecOAuthFlowItem = TypedDict("OpenAPISpecOAuthFlowItem", {
        "authorizationUrl": str,
        "tokenUrl": str,
        "refreshUrl": str,
        "scopes": Dict[str, str],
    }, total=True)
    OpenAPISpecOAuthFlows = TypedDict("OpenAPISpecOAuthFlows", {
        "implicit": OpenAPISpecOAuthFlowItem,
        "password": OpenAPISpecOAuthFlowItem,
        "clientCredentials": OpenAPISpecOAuthFlowItem,
        "authorizationCode": OpenAPISpecOAuthFlowItem,
    }, total=True)
    OpenAPISpecSecurityScheme = TypedDict("OpenAPISpecSecurityScheme", {
        "type": Literal["apiKey", "http", "oauth2", "openIdConnect"],
        "name": str,
        "in": Literal["header", "query", "cookie"],
        "description": NotRequired[str],
        "scheme": NotRequired[str],
        "bearerFormat": NotRequired[str],
        "flows": NotRequired[OpenAPISpecOAuthFlows],
        "openIdConnectUrl": NotRequired[str],
    }, total=True)
    OpenAPISpecServerVariable = TypedDict("OpenAPISpecServerVariable", {
        "description": NotRequired[str],
        "default": str,
        "enum": List[str],
    }, total=True)
    OpenAPISpecServer = TypedDict("OpenAPISpecServer", {
        "description": NotRequired[str],
        "url": str,
        "variables": NotRequired[Dict[str, OpenAPISpecServerVariable]],
    }, total=True)
    OpenAPISpecLink = TypedDict("OpenAPISpecLink", {
        "description": NotRequired[str],
        "operationId": str,
        "operationRef": str,
        "parameters": Dict[str, OpenAPISpecParameter],
        "requestBody": Dict[str, OpenAPISpecRequestBody],
        "server": NotRequired[OpenAPISpecServer],
    }, total=True)
    OpenAPISpecPathItem = TypedDict("OpenAPISpecPathItem", {
        "$ref": str,
        "summary": NotRequired[str],
        "description": NotRequired[str],
        "parameters": List[Union[OpenAPISpecParameter, OpenAPISchemaReference]],
        "requestBody": Dict[str, OpenAPISpecRequestBody],
        "server": NotRequired[OpenAPISpecServer],
    }, total=True)
    OpenAPISpecCallback = Dict[str, OpenAPISpecPathItem]
    OpenAPISpecComponents = TypedDict("OpenAPISpecComponents", {
        # for each dict, keys are $ref object name
        "schemas": NotRequired[Dict[str, Union[OpenAPISchema, OpenAPISchemaReference]]],
        "parameters": NotRequired[Dict[str, Union[OpenAPISpecParameter, OpenAPISchemaReference]]],
        "responses": NotRequired[Dict[str, Union[OpenAPISpecResponse, OpenAPISchemaReference]]],
        "requestBodies": NotRequired[Dict[str, Union[OpenAPISpecRequestBody, OpenAPISchemaReference]]],
        "examples": NotRequired[Dict[str, Union[OpenAPISpecExample, OpenAPISchemaReference]]],
        "headers": NotRequired[Dict[str, Union[OpenAPISpecHeader, OpenAPISchemaReference]]],
        "securitySchemes": NotRequired[Dict[str, Union[OpenAPISpecSecurityScheme, OpenAPISchemaReference]]],
        "links": NotRequired[Dict[str, Union[OpenAPISpecLink, OpenAPISchemaReference]]],
        "callbacks": NotRequired[Dict[str, Union[OpenAPISpecCallback, OpenAPISchemaReference]]],
    }, total=True)
    OpenAPISpecExternalDocs = TypedDict("OpenAPISpecExternalDocs", {
        "description": NotRequired[str],
        "url": str,
    }, total=True)
    OpenAPISpecification = TypedDict("OpenAPISpecification", {
        "openapi": Literal["3.0.0", "3.0.1", "3.0.2", "3.0.3", "3.1.0"],
        "info": OpenAPISpecInfo,
        "basePath": str,
        "host": str,
        "schemes": List[str],
        "tags": List[str],
        "paths": Dict[str, OpenAPISpecPathMethods],     # API path keys nested with HTTP methods
        "components": OpenAPISpecComponents,            # OpenAPI 3.0, nested sections with $ref object name as keys
        "definitions": NotRequired[Dict[str, OpenAPISchema]],        # Swagger 2.0, OpenAPI 3.0: 'components/schemas'
        "parameters": NotRequired[Dict[str, OpenAPISpecParameter]],  # Swagger 2.0, OpenAPI 3.0: 'components/parameters'
        "responses": NotRequired[Dict[str, OpenAPISpecResponse]],    # Swagger 2.0, OpenAPI 3.0: 'components/responses'
        "externalDocs": NotRequired[OpenAPISpecExternalDocs],
    }, total=True)

    FormatMediaType = TypedDict("FormatMediaType", {
        "mediaType": Required[str],
        "encoding": NotRequired[Optional[str]],
        "schema": NotRequired[Union[str, OpenAPISchema]],
        "default": NotRequired[bool],
    }, total=False)
    ProcessInputOutputItem = TypedDict("ProcessInputOutputItem", {
        "id": str,
        "title": NotRequired[str],
        "description": NotRequired[str],
        "keywords": NotRequired[List[str]],
        "metadata": NotRequired[List[Metadata]],
        "schema": NotRequired[OpenAPISchema],
        "formats": NotRequired[List[FormatMediaType]],
        "minOccurs": int,
        "maxOccurs": Union[int, Literal["unbounded"]],
    }, total=False)
    ProcessInputOutputMap = Dict[str, ProcessInputOutputItem]
    ProcessInputOutputList = List[ProcessInputOutputItem]
    # Provide distinct types with mapping/listing representation of I/O to help annotation
    # checkers resolve them more easily using less nested fields if specified explicitly
    ProcessOfferingMapping = TypedDict("ProcessOfferingMapping", {
        "id": Required[str],
        "version": Optional[str],
        "title": NotRequired[str],
        "description": NotRequired[str],
        "keywords": NotRequired[List[str]],
        "metadata": NotRequired[List[Metadata]],
        "inputs": Required[ProcessInputOutputMap],
        "outputs": Required[ProcessInputOutputMap],
        "jobControlOptions": List[AnyExecuteControlOption],
        "outputTransmission": List[AnyExecuteControlOption],
        "deploymentProfile": str,
        "processDescriptionURL": NotRequired[str],
        "processEndpointWPS1": NotRequired[str],
        "executeEndpoint": NotRequired[str],
        "links": List[Link],
        "visibility": NotRequired[AnyVisibility],
    }, total=False)
    ProcessOfferingListing = TypedDict("ProcessOfferingListing", {
        "id": Required[str],
        "version": Optional[str],
        "title": NotRequired[str],
        "description": NotRequired[str],
        "keywords": NotRequired[List[str]],
        "metadata": NotRequired[List[Metadata]],
        "inputs": Required[ProcessInputOutputList],
        "outputs": Required[ProcessInputOutputList],
        "jobControlOptions": List[AnyExecuteControlOption],
        "outputTransmission": List[AnyExecuteControlOption],
        "deploymentProfile": str,
        "processDescriptionURL": NotRequired[str],
        "processEndpointWPS1": NotRequired[str],
        "executeEndpoint": NotRequired[str],
        "links": List[Link],
        "visibility": NotRequired[AnyVisibility],
    }, total=False)
    ProcessOffering = Union[ProcessOfferingMapping, ProcessOfferingListing]
    ProcessDescriptionNestedMapping = TypedDict("ProcessDescriptionNestedMapping", {
        "process": ProcessOfferingMapping,
    }, total=False)
    ProcessDescriptionNestedListing = TypedDict("ProcessDescriptionNestedListing", {
        "process": ProcessOfferingListing,
    }, total=False)
    ProcessDescriptionNested = TypedDict("ProcessDescriptionNested", {
        "process": ProcessOffering,
    }, total=False)
    ProcessDescriptionMapping = Union[ProcessOfferingMapping, ProcessDescriptionNestedMapping]
    ProcessDescriptionListing = Union[ProcessOfferingListing, ProcessDescriptionNestedListing]
    ProcessDescription = Union[ProcessDescriptionMapping, ProcessDescriptionListing]

    ExecutionUnitItem = TypedDict("ExecutionUnitItem", {
        "unit": CWL
    }, total=True)
    ProcessDeployment = TypedDict("ProcessDeployment", {
        "processDescription": ProcessDescription,
        "executionUnit": List[Union[ExecutionUnitItem, Link]],
        "immediateDeployment": NotRequired[bool],
        "deploymentProfileName": str,
    }, total=True)

    ProcessExecution = TypedDict("ProcessExecution", {
        "mode": NotRequired[AnyExecuteMode],
        "response": NotRequired[AnyExecuteResponse],
        "inputs": Required[ExecutionInputs],
        "outputs": Required[ExecutionOutputs],
    }, total=False)
