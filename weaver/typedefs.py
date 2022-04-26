from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    import typing
    import uuid
    from datetime import datetime
    from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, Union
    if hasattr(typing, "TypedDict"):
        from typing import TypedDict  # pylint: disable=E0611,no-name-in-module  # Python >= 3.8
    else:
        from typing_extensions import TypedDict
    if hasattr(typing, "Literal"):
        from typing import Literal  # pylint: disable=E0611,no-name-in-module  # Python >= 3.8
    else:
        from typing_extensions import Literal
    if hasattr(typing, "Protocol"):
        from typing import Protocol  # pylint: disable=E0611,no-name-in-module  # Python >= 3.8
    else:
        from typing_extensions import Protocol
    if hasattr(typing, "TypeAlias"):
        from typing import TypeAlias  # pylint: disable=E0611,no-name-in-module  # Python >= 3.10
    else:
        from typing_extensions import TypeAlias
    if hasattr(os, "PathLike"):
        FileSystemPathType = Union[os.PathLike, str]
    else:
        FileSystemPathType = str

    from celery.app import Celery
    from celery.result import AsyncResult, EagerResult, GroupResult, ResultSet
    from owslib.wps import BoundingBoxDataInput, ComplexDataInput, Process as ProcessOWS, WPSExecution
    from pyramid.httpexceptions import HTTPSuccessful, HTTPRedirection
    from pyramid.registry import Registry
    from pyramid.request import Request as PyramidRequest
    from pyramid.response import Response as PyramidResponse
    from pyramid.testing import DummyRequest
    from pyramid.config import Configurator
    from pywps import Process as ProcessWPS
    from pywps.app import WPSRequest
    from pywps.inout import BoundingBoxInput, ComplexInput, LiteralInput
    from requests import PreparedRequest, Request as RequestsRequest
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
    AnyValueType = Optional[ValueType]  # avoid naming ambiguity with PyWPS AnyValue
    AnyKey = Union[str, int]
    AnyUUID = Union[str, uuid.UUID]
    # add more levels of explicit definitions than necessary to simulate JSON recursive structure better than 'Any'
    # amount of repeated equivalent definition makes typing analysis 'work well enough' for most use cases
    _JSON: TypeAlias = "JSON"
    _JsonObjectItemAlias: TypeAlias = "_JsonObjectItem"
    _JsonListItemAlias: TypeAlias = "_JsonListItem"
    _JsonObjectItem = Dict[str, Union[_JSON, _JsonListItemAlias]]
    _JsonListItem = List[Union[AnyValueType, _JsonObjectItem, _JsonListItemAlias, _JSON]]
    _JsonItem = Union[AnyValueType, _JsonObjectItem, _JsonListItem]
    JSON = Union[Dict[str, _JsonItem], List[_JsonItem], AnyValueType]

    Link = TypedDict("Link", {
        "rel": str,
        "title": str,
        "href": str,
        "hreflang": Optional[str],
        "type": Optional[str],  # IANA Media-Type
    }, total=False)
    Metadata = TypedDict("Metadata", {
        "title": str,
        "role": str,  # URL
        "value": str,
        "lang": str,
        "type": str,  # FIXME: relevant?
    }, total=False)

    LogLevelStr = Literal[
        "CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG",
        "critical", "fatal", "error", "warn", "warning", "info", "debug"
    ]
    AnyLogLevel = Union[LogLevelStr, int]

    # CWL definition
    GlobType = TypedDict("GlobType", {"glob": Union[str, List[str]]}, total=False)
    CWL_IO_FileValue = TypedDict("CWL_IO_FileValue", {"class": str, "path": str, "format": Optional[str]}, total=True)
    CWL_IO_Value = Union[AnyValueType, List[AnyValueType], CWL_IO_FileValue, List[CWL_IO_FileValue]]
    CWL_IO_NullableType = Union[str, List[str]]  # "<type>?" or ["<type>", "null"]
    CWL_IO_NestedType = TypedDict("CWL_IO_NestedType", {"type": CWL_IO_NullableType}, total=True)
    CWL_IO_EnumSymbols = Union[List[str], List[int], List[float]]
    CWL_IO_EnumType = TypedDict("CWL_IO_EnumType", {
        "type": str,
        "symbols": CWL_IO_EnumSymbols,
    })
    CWL_IO_ArrayType = TypedDict("CWL_IO_ArrayType", {
        "type": str,
        "items": Union[str, CWL_IO_EnumType],  # "items" => type of every item
    })
    CWL_IO_TypeItem = Union[str, CWL_IO_NestedType, CWL_IO_ArrayType, CWL_IO_EnumType]
    CWL_IO_DataType = Union[CWL_IO_TypeItem, List[CWL_IO_TypeItem]]
    CWL_Input_Type = TypedDict("CWL_Input_Type", {
        "id": Optional[str],    # representation used by plain CWL definition
        "name": Optional[str],  # representation used by parsed tool instance
        "type": CWL_IO_DataType,
        "items": Union[str, CWL_IO_EnumType],
        "symbols": Optional[CWL_IO_EnumSymbols],
        "format": Optional[Union[str, List[str]]],
        "inputBinding": Optional[Any],
        "default": Optional[AnyValueType],
    }, total=False)
    CWL_Output_Type = TypedDict("CWL_Output_Type", {
        "id": Optional[str],    # representation used by plain CWL definition
        "name": Optional[str],  # representation used by parsed tool instance
        "type": CWL_IO_DataType,
        "format": Optional[Union[str, List[str]]],
        "outputBinding": Optional[GlobType]
    }, total=False)
    CWL_Inputs = Union[List[CWL_Input_Type], Dict[str, CWL_Input_Type]]
    CWL_Outputs = Union[List[CWL_Output_Type], Dict[str, CWL_Output_Type]]
    CWL_Requirement = TypedDict("CWL_Requirement", {"class": str}, total=False)  # includes 'hints'
    CWL_RequirementsDict = Dict[str, Dict[str, str]]   # {'<req>': {<param>: <val>}}
    CWL_RequirementsList = List[CWL_Requirement]       # [{'class': <req>, <param>: <val>}]
    CWL_AnyRequirements = Union[CWL_RequirementsDict, CWL_RequirementsList]
    # results from CWL execution
    CWL_ResultFile = TypedDict("CWL_ResultFile", {"location": str}, total=False)
    CWL_ResultValue = Union[AnyValueType, List[AnyValueType]]
    CWL_ResultEntry = Union[Dict[str, CWL_ResultValue], CWL_ResultFile, List[CWL_ResultFile]]
    CWL_Results = Dict[str, CWL_ResultEntry]
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
    CWL = TypedDict("CWL", {
        "cwlVersion": str,
        "class": CWL_Class,
        "label": str,
        "doc": str,
        "s:keywords": List[str],
        "baseCommand": Optional[Union[str, List[str]]],
        "parameters": Optional[List[str]],
        "requirements": CWL_AnyRequirements,
        "hints": CWL_AnyRequirements,
        "inputs": CWL_Inputs,
        "outputs": CWL_Outputs,
        "steps": Dict[CWL_WorkflowStepID, CWL_WorkflowStep],
        "$namespaces": Dict[str, str],
        "$schemas": Dict[str, str]
    }, total=False)
    CWL_WorkflowStepPackage = TypedDict("CWL_WorkflowStepPackage", {
        "id": str,          # reference ID of the package
        "package": CWL      # definition of the package as sub-step of a Workflow
    })
    CWL_WorkflowStepPackageMap = Dict[CWL_WorkflowStepID, CWL_WorkflowStepPackage]

    # CWL loading
    CWL_WorkflowInputs = Dict[str, AnyValueType]   # mapping of ID:value
    CWL_ExpectedOutputs = Dict[str, AnyValueType]  # mapping of ID:value
    CWL_ToolPathObjectType = Dict[str, Any]
    JobProcessDefinitionCallback = Callable[[str, Dict[str, str], Dict[str, Any]], WpsProcessInterface]

    # CWL runtime
    CWL_RuntimeLiteral = Union[str, float, int]
    CWL_RuntimeInputFile = TypedDict("CWL_RuntimeInputFile", {
        "class": str,
        "location": str,
        "format": Optional[str],
        "basename": str,
        "nameroot": str,
        "nameext": str
    }, total=False)
    CWL_RuntimeOutputFile = TypedDict("CWL_RuntimeOutputFile", {
        "class": str,
        "location": str,
        "format": Optional[str],
        "basename": str,
        "nameroot": str,
        "nameext": str,
        "checksum": Optional[str],
        "size": Optional[str]
    }, total=False)
    CWL_RuntimeInput = Union[CWL_RuntimeLiteral, CWL_RuntimeInputFile]
    CWL_RuntimeInputsMap = Dict[str, CWL_RuntimeInput]
    CWL_RuntimeOutput = Union[CWL_RuntimeLiteral, CWL_RuntimeOutputFile]

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
    AnyResponseType = Union[PyramidResponse, WebobResponse, TestResponse]
    AnyRequestType = Union[PyramidRequest, WerkzeugRequest, PreparedRequest, RequestsRequest, DummyRequest]
    HTTPValid = Union[HTTPSuccessful, HTTPRedirection]

    AnyProcess = Union[Process, ProcessOWS, ProcessWPS, JSON]
    AnyProcessClass = Union[Type[Process], Type[ProcessWPS]]

    # update_status(message, progress, status, *args, **kwargs)
    class UpdateStatusPartialFunction(Protocol):
        def __call__(self, message: str, progress: Number, status: AnyStatusType, *args: Any, **kwargs: Any) -> None:
            pass

    DatetimeIntervalType = TypedDict("DatetimeIntervalType", {
        "before": datetime,
        "after": datetime,
        "match": datetime
    }, total=False)

    # data source configuration
    DataSourceFileRef = TypedDict("DataSourceFileRef", {
        "ades": str,                # target ADES to dispatch
        "netloc": str,              # definition to match file references against
        "default": Optional[bool],  # default ADES when no match was possible (single one allowed in config)
    }, total=True)
    DataSourceOpenSearch = TypedDict("DataSourceOpenSearch", {
        "ades": str,                     # target ADES to dispatch
        "netloc": str,                   # where to send OpenSearch request
        "collection_id": Optional[str],  # OpenSearch collection ID to match against
        "default": Optional[bool],       # default ADES when no match was possible (single one allowed)
        "accept_schemes": Optional[List[str]],     # allowed URL schemes (http, https, etc.)
        "mime_types": Optional[List[str]],         # allowed Media-Types (text/xml, application/json, etc.)
        "rootdir": str,                  # root position of the data to retrieve
        "osdd_url": str,                 # global OpenSearch description document to employ
    }, total=True)
    DataSource = Union[DataSourceFileRef, DataSourceOpenSearch]
    DataSourceConfig = Dict[str, DataSource]  # JSON/YAML file contents

    JobValueFormat = TypedDict("JobValueFormat", {
        "mime_type": Optional[str],
        "media_type": Optional[str],
        "encoding": Optional[str],
        "schema": Optional[str],
        "extension": Optional[str],
    }, total=False)
    JobValueFile = TypedDict("JobValueFile", {
        "href": Optional[str],
        "format": Optional[JobValueFormat],
    }, total=False)
    JobValueData = TypedDict("JobValueData", {
        "data": Optional[AnyValueType],
        "value": Optional[AnyValueType],
    }, total=False)
    JobValueObject = Union[JobValueData, JobValueFile]
    JobValueFileItem = TypedDict("JobValueFileItem", {
        "id": str,
        "href": Optional[str],
        "format": Optional[JobValueFormat],
    }, total=False)
    JobValueDataItem = TypedDict("JobValueDataItem", {
        "id": str,
        "data": Optional[AnyValueType],
        "value": Optional[AnyValueType],
    }, total=False)
    JobValueItem = Union[JobValueDataItem, JobValueFileItem]
    JobExpectItem = TypedDict("JobExpectItem", {"id": str}, total=True)
    JobInputs = List[Union[JobValueItem, Dict[str, AnyValueType]]]
    JobOutputs = List[Union[JobExpectItem, Dict[str, AnyValueType]]]
    JobResults = List[JobValueItem]
    JobMonitorReference = Any  # typically an URI of the remote job status or an execution object/handler

    ExecutionInputsMap = Dict[str, JobValueObject]  # when schema='weaver.processes.constants.ProcessSchema.OGC'
    ExecutionInputsList = List[JobValueItem]        # when schema='weaver.processes.constants.ProcessSchema.OLD'
    ExecutionInputs = Union[ExecutionInputsList, ExecutionInputsMap]

    ExecutionOutputObject = TypedDict("ExecutionOutputObject", {
        "transmissionMode": str
    }, total=False)
    ExecutionOutputItem = TypedDict("ExecutionOutputItem", {
        "id": str,
        "transmissionMode": str
    }, total=False)
    ExecutionOutputsList = List[ExecutionOutputItem]
    ExecutionOutputsMap = Dict[str, ExecutionOutputObject]
    ExecutionOutputs = Union[ExecutionOutputsList, ExecutionOutputsMap]
    ExecutionResultObject = TypedDict("ExecutionResultObject", {
        "value": Optional[AnyValueType],
        "href": Optional[str],
        "type": Optional[str],
    }, total=False)
    ExecutionResultArray = List[ExecutionResultObject]
    ExecutionResults = Dict[str, Union[ExecutionResultObject, ExecutionResultArray]]

    # reference employed as 'JobMonitorReference' by 'WPS1Process'
    JobExecution = TypedDict("JobExecution", {"execution": WPSExecution})

    # quoting
    QuoteProcessParameters = TypedDict("QuoteProcessParameters", {
        "inputs": JobInputs,
        "outputs": JobOutputs,
    })

    CeleryResult = Union[AsyncResult, EagerResult, GroupResult, ResultSet]

    # simple/partial definitions of OpenAPI schema
    OpenAPISchemaTypes = Literal["object", "array", "boolean", "integer", "number", "string"]
    _OpenAPISchema: TypeAlias = "OpenAPISchema"
    _OpenAPISchemaProperties: TypeAlias = "OpenAPISchemaProperties"
    OpenAPISchemaProperties = TypedDict("OpenAPISchemaProperties", {
        "type": OpenAPISchemaTypes,
        "format": str,
        "default": Any,
        "example": Any,
        "title": str,
        "description": str,
        "enum": List[Union[str, Number]],
        "items": List[str, _OpenAPISchema],
        "required": List[str],
        "nullable": bool,
        "deprecated": bool,
        "readOnly": bool,
        "writeOnly": bool,
        "multipleOf": Number,
        "minimum": Number,
        "maximum": Number,
        "exclusiveMinimum": bool,
        "exclusiveMaximum": bool,
        "minLength": Number,
        "maxLength": Number,
        "pattern": str,
        "minItems": Number,
        "maxItems": Number,
        "uniqueItems": bool,
        "minProperties": Number,
        "maxProperties": Number,
        "contentMediaType": str,
        "contentEncoding": str,
        "contentSchema": str,
        "not": Union[_OpenAPISchema, str],
        "allOf": List[Union[_OpenAPISchema, str]],
        "anyOf": List[Union[_OpenAPISchema, str]],
        "oneOf": List[Union[_OpenAPISchema, str]],
        "properties": Dict[str, _OpenAPISchemaProperties],
        "additionalProperties": Union[bool, Dict[str, Union[str, _OpenAPISchema]]],
    }, total=False)
    OpenAPISchemaObject = TypedDict("OpenAPISchemaObject", {
        "type": Literal["object"],
        "properties": OpenAPISchemaProperties
    }, total=False)
    OpenAPISchemaList = TypedDict("OpenAPISchemaList", {
        "type": Literal["array"],
        "items": _OpenAPISchema
    }, total=False)
    OpenAPISchema = Union[OpenAPISchemaObject, OpenAPISchemaList, OpenAPISchemaProperties]
