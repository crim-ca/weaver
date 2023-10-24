"""
Conversion functions between corresponding data structures.
"""
import copy
import inspect
import json
import logging
import os
from collections import OrderedDict
from collections.abc import Hashable
from copy import deepcopy
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, overload
from urllib.parse import unquote, urlparse

import colander
import pint
from owslib.wps import ComplexData, Metadata as OWS_Metadata, is_reference
from pywps import OGCUNIT, Process as ProcessWPS
from pywps.app.Common import Metadata as WPS_Metadata
from pywps.inout import BoundingBoxInput, BoundingBoxOutput, ComplexInput, ComplexOutput, LiteralInput, LiteralOutput
from pywps.inout.basic import BasicBoundingBox, BasicComplex, BasicIO, UOM
from pywps.inout.formats import Format
from pywps.inout.literaltypes import ALLOWEDVALUETYPE, LITERAL_DATA_TYPES, RANGECLOSURETYPE, AllowedValue, AnyValue
from pywps.validator.mode import MODE

from weaver import xml_util
from weaver.exceptions import PackageTypeError
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import (
    ContentType,
    SchemaRole,
    get_content_type,
    get_cwl_file_format,
    get_extension,
    get_format,
    repr_json
)
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_INLINE_JAVASCRIPT,
    IO_INPUT,
    IO_OUTPUT,
    OAS_ARRAY_TYPES,
    OAS_COMPLEX_TYPES,
    OAS_KEYWORD_TYPES,
    OAS_LITERAL_BINARY_FORMATS,
    OAS_LITERAL_DATETIME_FORMATS,
    OAS_LITERAL_FLOAT_FORMATS,
    OAS_LITERAL_INTEGER_FORMATS,
    OAS_LITERAL_NUMERIC,
    OAS_LITERAL_NUMERIC_FORMATS,
    OAS_LITERAL_STRING_FORMATS,
    OAS_LITERAL_TYPES,
    PACKAGE_ARRAY_BASE,
    PACKAGE_ARRAY_ITEMS,
    PACKAGE_ARRAY_MAX_SIZE,
    PACKAGE_ARRAY_TYPES,
    PACKAGE_BASIC_TYPES,
    PACKAGE_COMPLEX_TYPES,
    PACKAGE_CUSTOM_TYPES,
    PACKAGE_DIRECTORY_TYPE,
    PACKAGE_ENUM_BASE,
    PACKAGE_FILE_TYPE,
    PACKAGE_FLOATING_TYPES,
    PACKAGE_INTEGER_TYPES,
    PACKAGE_LITERAL_TYPES,
    PACKAGE_NUMERIC_TYPES,
    WPS_BOUNDINGBOX,
    WPS_COMPLEX,
    WPS_COMPLEX_DATA,
    WPS_COMPLEX_TYPES,
    WPS_DATA_TYPES,
    WPS_LITERAL,
    WPS_LITERAL_DATA_BOOLEAN,
    WPS_LITERAL_DATA_DATETIME,
    WPS_LITERAL_DATA_FLOAT,
    WPS_LITERAL_DATA_INTEGER,
    WPS_LITERAL_DATA_STRING,
    WPS_LITERAL_DATA_TYPES,
    WPS_REFERENCE,
    IO_Select_Type,
    JobInputsOutputsSchema,
    ProcessSchema,
    WPS_Category_Type
)
from weaver.utils import (
    SchemaRefResolver,
    bytes2str,
    fetch_file,
    fully_qualified_name,
    get_any_id,
    get_any_value,
    get_sane_name,
    get_url_without_query,
    null,
    str2bytes,
    transform_json
)
from weaver.wps.utils import get_wps_client
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, Type, Union
    from typing_extensions import Literal, NotRequired, Required, TypedDict
    from urllib.parse import ParseResult

    from owslib.ows import BoundingBox
    from owslib.wps import (
        BoundingBoxDataInput,
        ComplexDataInput,
        Input as OWS_Input_Base,
        Output as OWS_Output_Base,
        Process as ProcessOWS
    )
    from pint._typing import Scalar
    from pywps.app import WPSRequest
    from requests.models import Response

    from weaver.processes.constants import JobInputsOutputsSchemaType, ProcessSchemaType, WPS_DataType
    from weaver.typedefs import (
        AnySettingsContainer,
        AnyValueType,
        CWL,
        CWL_IO_ComplexType,
        CWL_IO_DataType,
        CWL_IO_EnumSymbols,
        CWL_IO_FileValue,
        CWL_IO_LiteralType,
        CWL_IO_Type,
        CWL_IO_Value,
        CWL_SchemaNames,
        ExecutionInputs,
        ExecutionInputsList,
        ExecutionInputsMap,
        ExecutionOutputs,
        ExecutionOutputsList,
        ExecutionOutputsMap,
        JobValueFile,
        JSON,
        OpenAPISchema,
        OpenAPISchemaArray,
        OpenAPISchemaKeyword,
        OpenAPISchemaObject,
        OpenAPISchemaProperty,
        OpenAPISchemaReference
    )

    # typing shortcuts
    # pylint: disable=C0103,invalid-name
    WPS_Input_Type = Union[LiteralInput, ComplexInput, BoundingBoxInput]
    WPS_Output_Type = Union[LiteralOutput, ComplexOutput, BoundingBoxOutput]
    WPS_IO_Type = Union[WPS_Input_Type, WPS_Output_Type]
    OWS_Input_Type = Union[OWS_Input_Base, BoundingBox, BoundingBoxDataInput, ComplexDataInput]
    OWS_Output_Type = Union[OWS_Output_Base, BoundingBox, BoundingBoxDataInput, ComplexData]
    OWS_IO_Type = Union[OWS_Input_Type, OWS_Output_Type]
    JSON_Format = TypedDict("JSON_Format", {
        "mime_type": Required[str],
        "encoding": NotRequired[Optional[str]],
        "schema": NotRequired[Optional[str]],
        "maximumMegabytes": NotRequired[Optional[int]],
        "default": NotRequired[bool],
    }, total=True)
    JSON_UoM = TypedDict("JSON_UoM", {
        "uom": str,
        "reference": NotRequired[str],
    }, total=True)
    JSON_IO_TypeBase = TypedDict("JSON_IO_TypeBase", {
        "id": Required[str],
        "type": Required[str],
        "identifier": NotRequired[str],
    }, total=False)
    JSON_IO_Type = Union[JSON, JSON_IO_TypeBase]
    JSON_IO_TypedInfo = TypedDict("JSON_IO_TypedInfo", {
        "type": WPS_DataType,
        "data_type": NotRequired[Optional[str]],
        "data_uom": NotRequired[Optional[bool]],
        "minOccurs": NotRequired[int],
        "maxOccurs": NotRequired[int],
        "supported_formats": NotRequired[List[JSON_Format]],
        "uom": NotRequired[JSON_UoM],
        "uoms": NotRequired[List[JSON_UoM]],
    }, total=False)
    JSON_IO_ListOrMap = Union[List[JSON], Dict[str, Union[JSON, str]]]
    PKG_IO_Type = Union[JSON_IO_Type, WPS_IO_Type]
    ANY_IO_Type = Union[CWL_IO_Type, JSON_IO_Type, WPS_IO_Type, OWS_IO_Type]
    ANY_Format_Type = Union[Dict[str, Optional[str]], Format]
    ANY_Metadata_Type = Union[OWS_Metadata, WPS_Metadata, Dict[str, str]]
    DataInputType = TypedDict("DataInputType", {
        "data": Union[float, int, bool, str],
        "format": NotRequired[JSON_Format],
        # ** any other params
    }, total=False)


# WPS object attribute -> all possible *other* naming variations (no need to repeat key name)
WPS_FIELD_MAPPING = {
    "identifier": ["id", "ID", "Id", "Identifier"],
    "title": ["Title", "Label", "label"],
    "abstract": ["description", "Description", "Abstract"],
    "version": ["processVersion", "Version"],
    "metadata": ["Metadata"],
    "keywords": ["Keywords"],
    "allowed_values": ["AllowedValues", "allowedValues", "allowedvalues", "Allowed_Values", "Allowedvalues"],
    "allowed_collections": ["AllowedCollections", "allowedCollections", "allowedcollections", "Allowed_Collections",
                            "Allowedcollections"],
    "any_value": ["anyvalue", "anyValue", "AnyValue"],
    "literal_data_domains": ["literalDataDomains"],
    "default": ["default_value", "defaultValue", "DefaultValue", "Default", "_default", "data_format", "data"],
    "supported_values": ["SupportedValues", "supportedValues", "supportedvalues", "Supported_Values"],
    "supported_formats": ["SupportedFormats", "supportedFormats", "supportedformats", "Supported_Formats", "formats"],
    "supported_crs": ["SupportedCRS", "supportedCRS", "crss", "crs", "CRS"],
    "additional_parameters": ["AdditionalParameters", "additionalParameters", "additionalparameters",
                              "Additional_Parameters"],
    "type": ["Type", "data_type", "dataType", "DataType", "Data_Type"],
    "min_occurs": ["minOccurs", "MinOccurs", "Min_Occurs", "minoccurs"],
    "max_occurs": ["maxOccurs", "MaxOccurs", "Max_Occurs", "maxoccurs"],
    "max_megabytes": ["maximumMegabytes", "max_size"],
    "mime_type": ["mimeType", "MimeType", "mime-type", "Mime-Type", "mimetype",
                  "mediaType", "MediaType", "media-type", "Media-Type", "mediatype",
                  "content_type", "contentMediaType"],
    "range_minimum": ["minval", "minimum", "minimumValue"],
    "range_maximum": ["maxval", "maximum", "maximumValue"],
    "range_spacing": ["spacing"],
    "range_closure": ["closure", "rangeClosure"],
    "encoding": ["Encoding", "content_encoding", "contentEncoding"],
    "schema": ["Schema", "contentSchema"],
    "href": ["url", "link", "reference"],
    "uom": ["UoM", "unit", "default_uom"],
    "uoms": ["UOMs", "units", "supported_uoms"],
    "measure": ["value", "measurement"],
}
# WPS fields that contain a structure corresponding to `Format` object
#   - keys must match `WPS_FIELD_MAPPING` keys
#   - fields are placed in order of relevance (prefer explicit format, then supported, and defaults as last resort)
WPS_FIELD_FORMAT = ["formats", "supported_formats", "supported_values", "default"]

# default format if missing (minimal requirement of one)
DEFAULT_FORMAT = Format(mime_type=ContentType.TEXT_PLAIN)
DEFAULT_FORMAT_MISSING = "__DEFAULT_FORMAT_MISSING__"
setattr(DEFAULT_FORMAT, DEFAULT_FORMAT_MISSING, True)

INPUT_VALUE_TYPE_MAPPING = {
    "bool": bool,
    "boolean": bool,
    "file": unquote,
    PACKAGE_FILE_TYPE: unquote,
    "float": float,
    "int": int,
    "integer": int,
    "str": unquote,
    "string": unquote,
}

# setup unit registry and aliases
UNIT_REGISTRY = pint.UnitRegistry()
UNIT_REGISTRY.default_format = "~P"  # short-form symbols, pretty-format units
UNIT_OGC_REVERSED = {}  # type: Dict[str, List[str]]  # {URN: [shorthand-names]}
for plain_unit, ogc_unit in OGCUNIT.items():
    UNIT_OGC_REVERSED.setdefault(ogc_unit, [])
    UNIT_OGC_REVERSED[ogc_unit].append(plain_unit)

LOGGER = logging.getLogger(__name__)


def convert_unit(unit):
    # type: (str) -> pint.Unit
    """
    Convert units considering any known registry names and :term:`OGC` :term:`URN`.

    Since :term:`OGC` defines units using :term:`URN`, they cannot be registered as aliases in :data:`UNIT_REGISTRY`.
    This is a limitation from the naming format that requires valid Python identifier names, which is not possible
    due to the ``:`` characters in :term:`URN` references.
    """
    if unit in ["unity", OGCUNIT["unity"]]:
        return UNIT_REGISTRY.Unit("")  # dimensionless
    unit = UNIT_OGC_REVERSED.get(unit) or unit
    if isinstance(unit, list):
        unit = unit[0]
    return UNIT_REGISTRY.Unit(unit)


def convert_value_units(value, uom, to):
    # type: (Scalar, str, str) -> Scalar
    """
    Converts the provided value from one :term:`UoM` to another.
    """
    uom = convert_unit(uom)
    to = convert_unit(to)
    quantity = UNIT_REGISTRY.Quantity(value, uom)
    converted = quantity.to(to)
    return converted.magnitude


def complex2json(data):
    # type: (Union[ComplexData, Any]) -> Union[JSON, Any]
    """
    Obtains the JSON representation of a :class:`ComplexData` or simply return the unmatched type.
    """
    if not isinstance(data, ComplexData):
        return data
    # backward compat based on OWSLib version, field did not always exist
    max_mb = getattr(data, "maximumMegabytes", None)
    if isinstance(max_mb, str) and max_mb.isnumeric():
        max_mb = int(max_mb)
    return {
        "mimeType": data.mimeType,
        "encoding": data.encoding,
        "schema": data.schema,
        "maximumMegabytes": max_mb,
        "default": False,  # always assume it is a supported format/value, caller should override
    }


def metadata2json(meta, force=False):
    # type: (Union[ANY_Metadata_Type, Any], bool) -> Union[JSON, Any]
    """
    Retrieve metadata information and generate its JSON representation.

    Obtains the JSON representation of a :class:`OWS_Metadata` or :class:`pywps.app.Common.Metadata`.
    Otherwise, simply return the unmatched type.
    If requested, can enforce parsing a dictionary for the corresponding keys.
    """
    if not force and not isinstance(meta, (OWS_Metadata, WPS_Metadata)):
        return meta
    title = get_field(meta, "title", search_variations=True, default=None)
    ctype = get_field(meta, "type") or get_field(meta, "mime_type", search_variations=True, default=None)
    href = get_field(meta, "href", search_variations=True, default=None)
    role = get_field(meta, "role", search_variations=True, default=None)
    rel = get_field(meta, "rel", search_variations=True, default=None)
    # many remote servers do not provide the 'rel', but instead provide 'title' or 'role'
    # build one by default to avoid failing schemas that expect 'rel' to exist
    if not rel:
        href_rel = urlparse(href).hostname
        rel = str(title or role or href_rel).lower()  # fallback to first available
        rel = get_sane_name(rel, replace_character="-", assert_invalid=False)
    return {"href": href, "title": title, "role": role, "rel": rel, "type": ctype}


def uom2json(uom, ref=None):
    # type: (Union[str, UOM, JSON_UoM], Optional[str]) -> JSON_UoM
    """
    Convert an :term:`UoM` definition into corresponding :term:`JSON` representation.
    """
    if isinstance(uom, str):
        return UOM(
            str(convert_unit(uom)),  # compact form
            ref or "",  # FIXME: default string fix for https://github.com/geopython/pywps/issues/685
        ).json
    if isinstance(uom, UOM):
        uom.uom = str(convert_unit(uom.uom))  # compact from as needed
        return uom.json
    if isinstance(uom, dict) and "uom" in uom:
        uom["uom"] = str(convert_unit(uom["uom"]))  # compact from as needed
        return uom
    raise TypeError(f"Unable to convert JSON UoM definition from '{fully_qualified_name(uom)}'.")


def ows2json_io(ows_io):
    # type: (OWS_IO_Type) -> JSON_IO_Type
    """
    Converts :term:`I/O` definition from :mod:`owslib.wps` to :term:`JSON`.
    """
    json_io = {}
    for field in WPS_FIELD_MAPPING:
        value = get_field(ows_io, field, search_variations=True)
        # preserve numeric values (ex: "minOccurs"=0) as actual parameters
        # ignore undefined values represented by `null`, empty list, or empty string
        if value or value in [0, 0.0]:
            if isinstance(value, list):
                # complex data is converted as is
                # metadata converted and preserved if it results into a minimally valid definition (otherwise dropped)
                json_io[field] = [
                    complex2json(v) if isinstance(v, ComplexData) else
                    metadata2json(v) if isinstance(v, OWS_Metadata) else v
                    for v in value if not isinstance(v, OWS_Metadata) or v.url is not None
                ]
            elif isinstance(value, ComplexData):
                json_io[field] = complex2json(value)
            elif isinstance(value, OWS_Metadata):
                json_io[field] = metadata2json(value)
            else:
                json_io[field] = value
    json_io["id"] = get_field(json_io, "identifier", search_variations=True, pop_found=True)
    io_type = json_io.get("type")

    # add 'format' if missing, derived from other variants
    if io_type == WPS_COMPLEX_DATA:
        fmt_default = False
        if "default" in json_io and isinstance(json_io["default"], dict):
            json_io["default"]["default"] = True  # provide for workflow extension (internal), schema drops it (API)
            fmt_default = True

        # retrieve alternate format definitions
        if "formats" not in json_io:
            # correct complex data 'formats' from OWSLib from initial fields loop can get stored in 'supported_values'
            fmt_val = get_field(json_io, "supported_values", pop_found=True)
            if fmt_val:
                json_io["formats"] = fmt_val
            else:
                # search for format fields directly specified in I/O body
                for field in WPS_FIELD_FORMAT:
                    fmt = get_field(json_io, field, search_variations=True)
                    if not fmt:
                        continue
                    if isinstance(fmt, dict):
                        fmt = [fmt]
                    fmt = filter(lambda f: isinstance(f, dict), fmt)
                    if not isinstance(json_io.get("formats"), list):
                        json_io["formats"] = []
                    for var_fmt in fmt:
                        # add it only if not exclusively provided by a previous variant
                        json_fmt_items = [j_fmt.items() for j_fmt in json_io["formats"]]
                        if any(all(var_item in items for var_item in var_fmt.items()) for items in json_fmt_items):
                            continue
                        json_io["formats"].append(var_fmt)

            json_io.setdefault("formats", [])

        # apply the default flag
        for fmt in json_io["formats"]:
            fmt["default"] = fmt_default and is_equal_formats(json_io["default"], fmt)
            if fmt["default"]:
                break

        # NOTE:
        #   Don't apply 'minOccurs=0' as in below literal case because default 'format' does not imply that unspecified
        #   input is valid, but rather that given an input without explicit 'format' specified, that 'default' is used.
        return json_io

    # add value constraints in specifications
    elif io_type in WPS_LITERAL_DATA_TYPES:
        domains = any2json_literal_data_domains(ows_io)
        if domains:
            json_io["literalDataDomains"] = domains
            # fix inconsistencies of some process descriptions
            # WPS are allowed to report 'minOccurs=1' although 'defaultValue' can also be provided
            # (see https://github.com/geopython/pywps/issues/625)
            if "defaultValue" in domains[0]:
                json_io["min_occurs"] = 0

    return json_io


# FIXME: add option to control auto-fetch, disable during workflow by default to avoid double downloads?
#       (https://github.com/crim-ca/weaver/issues/183)
def ows2json_output_data(output, process_description, container=None):
    # type: (OWS_Output_Type, ProcessOWS, Optional[AnySettingsContainer]) -> JSON
    """
    Utility method to convert an :mod:`owslib.wps` process execution output data (result) to `JSON`.

    In the case that a ``reference`` output of `JSON` content-type is specified and that it refers to a file that
    contains an array list of URL references to simulate a multiple-output, this specific output gets expanded to
    contain both the original URL ``reference`` field and the loaded URL list under ``data`` field for easier access
    from the response body.

    Referenced file(s) are fetched in order to store them locally if executed on a remote process, such that they can
    become accessible as local job result for following reporting or use by other processes in a workflow chain.

    If the ``dataType`` details is missing from the data output (depending on servers that might omit it), the
    :paramref:`process_description` is employed to retrieve the original description with expected result details.

    :param output: output with data value or reference according to expected result for the corresponding process.
    :param process_description: definition of the process producing the specified output following execution.
    :param container: container to retrieve application settings (for request options during file retrieval as needed).
    :return: converted JSON result data and additional metadata as applicable based on data-type and content-type.
    """

    if not output.dataType:
        for process_output in getattr(process_description, "processOutputs", []):
            if getattr(process_output, "identifier", "") == output.identifier:
                output.dataType = process_output.dataType
                break

    json_output = {
        "identifier": output.identifier,
        "title": output.title,
        "dataType": output.dataType
    }

    # WPS standard v1.0.0 specify that either a reference or a data field has to be provided
    if output.reference:
        json_output["reference"] = output.reference

        # Handle special case where we have a reference to a json array containing dataset reference.
        # Avoid reference to reference by fetching directly the dataset references.
        json_array = _get_multi_json_references(output, container)
        if json_array and all(str(ref).startswith("http") for ref in json_array):
            json_output["data"] = json_array

    else:
        # WPS standard v1.0.0 specify that Output data field has Zero or one value
        json_output["data"] = output.data[0] if output.data else None

    if (json_output["dataType"] == WPS_COMPLEX_DATA or "reference" in json_output) and output.mimeType:
        json_output["mimeType"] = output.mimeType

    return json_output


# FIXME: support metalink unwrapping / multi-output array (weaver https://github.com/crim-ca/weaver/issues/25)
def _get_multi_json_references(output, container):
    # type: (OWS_Output_Type, Optional[AnySettingsContainer]) -> Optional[List[JSON]]
    """
    Obtains the JSON contents of a single output corresponding to multi-file references.

    Since WPS standard does not allow to return multiple values for a single output,
    a lot of process actually return a JSON array containing references to these outputs.

    Because the multi-output references are contained within this JSON file, it is not very convenient to retrieve
    the list of URLs as one always needs to open and read the file to get them. This function goal is to detect this
    particular format and expand the references to make them quickly available in the job output response.

    :return:
        Array of HTTP(S) references if the specified output is effectively a JSON containing that, ``None`` otherwise.
    """
    # Check for the json datatype and mime-type
    if output.dataType == WPS_COMPLEX_DATA and output.mimeType == ContentType.APP_JSON:
        try:
            # If the json data is referenced read it's content
            if output.reference:
                with TemporaryDirectory() as tmp_dir:
                    file_path = fetch_file(output.reference, tmp_dir, settings=container)
                    with open(file_path, "r", encoding=output.encoding) as tmp_file:
                        json_data_str = tmp_file.read()
            # Else get the data directly
            else:
                # process output data are append into a list and
                # WPS standard v1.0.0 specify that Output data field has zero or one value
                if not output.data:
                    return None
                json_data_str = output.data[0]

            # Load the actual json dict
            json_data = json.loads(json_data_str)
        except Exception as exc:  # pylint: disable=W0703
            LOGGER.debug("Failed retrieval of JSON output file for multi-reference unwrapping", exc_info=exc)
            return None
        if isinstance(json_data, list):
            return None if any(not is_reference(data_value) for data_value in json_data) else json_data
    return None


def get_io_type_category(io_info):
    # type: (ANY_IO_Type) -> WPS_Category_Type
    """
    Guesses the applicable :term:`I/O` type with provided information from any known :term:`I/O` structure.
    """
    io_type = get_field(io_info, "type", search_variations=True)
    if isinstance(io_type, str):
        if io_type in WPS_DATA_TYPES:
            return WPS_COMPLEX if io_type in WPS_COMPLEX_TYPES else io_type
        io_type = any2cwl_literal_datatype(io_type) or any2wps_literal_datatype(io_type)
        return WPS_COMPLEX if io_type is null else WPS_LITERAL
    if isinstance(io_type, dict):
        io_info = copy.deepcopy(io_info)
        io_info.setdefault("name", "dontcare")
        io_def = get_cwl_io_type(io_info, strict=False)
        return WPS_COMPLEX if io_def.type in [null, PACKAGE_FILE_TYPE, PACKAGE_DIRECTORY_TYPE] else WPS_LITERAL
    io_fmt = get_field(io_info, "supported_formats", search_variations=True)
    return WPS_LITERAL if io_fmt is null else WPS_COMPLEX


def _get_cwl_fmt_details(wps_fmt):
    # type: (ANY_Format_Type) -> Union[Tuple[Tuple[str, str], str, str], Tuple[None, None, None]]
    _wps_io_fmt = get_field(wps_fmt, "mime_type", search_variations=True)
    if not _wps_io_fmt:
        return None, None, None
    _cwl_io_ext = get_extension(_wps_io_fmt)
    _cwl_io_ref, _cwl_io_fmt = get_cwl_file_format(_wps_io_fmt, must_exist=True, allow_synonym=False)
    return _cwl_io_ref, _cwl_io_fmt, _cwl_io_ext


def _convert_any2cwl_io_complex(cwl_io, cwl_ns, wps_io, io_select):
    # type: (CWL_IO_Type, Dict[str, str], Union[JSON_IO_Type, WPS_IO_Type, OWS_IO_Type], IO_Select_Type) -> None
    """
    Converts the :term:`WPS`-like :term:`I/O` definition and defines them inplace into the :term:`CWL` containers.

    .. seealso::
        See :meth:`weaver.processes.wps_process_base.WpsProcessInterface.stage_results` which closely interacts
        with the produced ``outputBinding.glob`` patterns generated here. Methodology should align between them.

    :param cwl_io: Basic :term:`CWL` :term:`I/O` container (only ID needed) where to write conversion results.
    :param cwl_ns: Namespaces to gradually update when encountering new format Media-Type definitions.
    :param wps_io: Original :term:`WPS`-like :term:`I/O` to be converted.
    :param io_select: Context of the :term:`I/O`.
    :return: Nothing. Changed inplace.
    """
    cwl_io_fmt = None
    cwl_io_ext = get_extension(ContentType.ANY)
    cwl_io["type"] = PACKAGE_FILE_TYPE
    cwl_id = cwl_io["id"]

    # inputs are allowed to define multiple 'supported' formats
    # outputs are allowed to define only one 'applied' format
    for field in WPS_FIELD_FORMAT:
        fmt = get_field(wps_io, field, search_variations=True)
        if not fmt:
            continue
        if isinstance(fmt, (list, tuple)) and len(fmt) == 1:
            fmt = fmt[0]
        if not isinstance(fmt, (list, tuple)):  # could be 'dict', 'Format' or any other 'object' holder
            cwl_io_ref, cwl_io_fmt, cwl_io_ext = _get_cwl_fmt_details(fmt)
            if cwl_io_ref and cwl_io_fmt:
                cwl_ns.update(cwl_io_ref)
            break
        if isinstance(fmt, (list, tuple)):
            cwl_ns_multi = {}
            cwl_fmt_multi = {}  # use dict as ordered set
            cwl_ext_multi = {}  # use dict as ordered set
            for fmt_i in fmt:
                # FIXME: (?)
                #   when multiple formats are specified, but at least one schema/namespace reference can't be found,
                #   we must drop all since that unknown format is still allowed but cannot be validated
                #   avoid potential validation error if that format was the one provided during execute...
                #   (see: https://github.com/crim-ca/weaver/issues/50)
                cwl_io_ref_i, cwl_io_fmt_i, cwl_io_ext = _get_cwl_fmt_details(fmt_i)
                if cwl_io_ref_i and cwl_io_fmt_i:  # if any known format was resolved
                    cwl_ns_multi.update(cwl_io_ref_i)
                    cwl_fmt_multi.update({cwl_io_fmt_i: None})
                    cwl_ext_multi.update({cwl_io_ext: None})
                else:
                    # reset all since at least one format could not be mapped to an official schema
                    cwl_ns_multi = {}
                    cwl_fmt_multi = None
                    break
            cwl_io_fmt = cwl_fmt_multi  # all formats or none of them
            cwl_io_ext = cwl_ext_multi
            cwl_ns.update(cwl_ns_multi)
            break

    cwl_io_ext = [cwl_io_ext] if isinstance(cwl_io_ext, str) else list(cwl_io_ext)
    if cwl_io_fmt:
        # don't use any format if more than one because we cannot enforce multiple formats
        # ('format' must be string: https://www.commonwl.org/v1.2/CommandLineTool.html#File)
        if not isinstance(cwl_io_fmt, str) and len(cwl_io_fmt) == 1:
            cwl_io["format"] = list(cwl_io_fmt)[0]
        if isinstance(cwl_io_fmt, str):
            cwl_io["format"] = cwl_io_fmt

    if io_select == IO_OUTPUT:
        # for backward compatibility with deployed processes, consider text/plan as 'any' for glob pattern
        cwl_io_txt = get_extension(ContentType.TEXT_PLAIN)
        if cwl_io_txt in cwl_io_ext:
            cwl_io_any = get_extension(ContentType.ANY)
            LOGGER.warning("Replacing '%s' [%s] to generic '%s' [%s] glob pattern from resolved formats %s. "
                           "More explicit format media-type should be considered for %s '%s'.",
                           ContentType.TEXT_PLAIN, cwl_io_txt, cwl_io_ext,
                           ContentType.ANY, cwl_io_any, io_select, cwl_id)
            cwl_io_ext = [cwl_io_any]

        # Method 'weaver.processes.wps_process_base.WpsProcessInterface.stage_results' uses the produced glob
        # pattern(s) below of generated output definitions from WPS items that don't offer any hint about the
        # expected file naming format or specification (because we cannot guess what will be produced as output
        # from the remote process definitions alone). We can only provide expected extension based on the file
        # format/schema/media-type of the output definition.
        # To avoid potential naming clashes or conflicting matching from generic patterns when CWL tries to resolve
        # paths, that staging operation stage outputs and adjust each glob pattern under a directory named by the
        # respective output ID.
        # However, it is very important **NOT** to add the output ID directory nesting approach here, otherwise it
        # will confuse the staging process between Workflow steps, since it won't be able to distinguish whether the
        # nesting was already applied by Weaver (here), or provided by an user-provided CWL Application Package, since
        # WPS-based. OGC-based, CWL-based, (or any future implementation) can be combined within a same Workflow.
        cwl_glob = [
            f"*{ext}" if ext != "/" else "./"  # handle special case of "extension" for 'Directory' type
            for ext in cwl_io_ext
        ]
        cwl_io["outputBinding"] = {
            "glob": cwl_glob[0] if len(cwl_glob) == 1 else cwl_glob
        }


def _get_cwl_js_value_from(cwl_io_symbols, allow_unique, allow_array):
    # type: (List[AnyValueType], bool, bool) -> str
    """
    Obtain the JavaScript ``valueFrom`` definition for a :term:`CWL` input of non-``string`` allowed values.
    """
    cwl_js_value_from_const = f"const values = {json.dumps(cwl_io_symbols)};"
    cwl_js_value_from_array = """
        if (self.every(item => values.includes(item))) {
            return self;
        }
        else {
            throw "invalid value(s) in [" + self + "] are not all allowed values from [" + values + "]";
        }
    """
    cwl_js_value_from_unique = """
        if (values.includes(self)) {
            return self;
        }
        else {
            throw "invalid value " + self + " is not an allowed value from [" + values + "]";
        }
    """

    if allow_unique and not allow_array:
        cwl_js_value_from = inspect.cleandoc(f"""
            ${{
                if (Array.isArray(self)) {{
                    throw "invalid value " + self + " does not match expected type";
                }}
                {cwl_js_value_from_const}
                {cwl_js_value_from_unique}
            }}
        """)
    elif not allow_unique and allow_array:
        cwl_js_value_from = f"""
            ${{
                if (!Array.isArray(self)) {{
                    throw "invalid value " + self + " does not match expected type";
                }}
                {cwl_js_value_from_const}
                {cwl_js_value_from_array}
            }}
        """
    else:
        cwl_js_value_from = f"""
            ${{
                {cwl_js_value_from_const}
                if (Array.isArray(self)) {{
                    {cwl_js_value_from_array}
                }}
                else {{
                    {cwl_js_value_from_unique}
                }}
            }}
        """
    return cwl_js_value_from


def _convert_cwl_io_enum(cwl_io_type, cwl_io_symbols, io_select, allow_unique, allow_array):
    # type: (Union[str, Type[null]], List[AnyValueType], IO_Select_Type, bool, bool) -> CWL_IO_Type
    """
    Converts the :term:`I/O` definition to a :term:`CWL` :term:`I/O` that allows ``Enum``-like functionality.

    In the event of an explicit ``string`` as base type, :term:`CWL` directly supports ``type: enum``. Other basic
    types are not directly supported, and must instead perform manual validation against the set of allowed values.

    .. seealso::
        - https://github.com/common-workflow-language/cwl-v1.2/issues/267
        - https://github.com/common-workflow-language/common-workflow-language/issues/764
        - https://github.com/common-workflow-language/common-workflow-language/issues/907

    .. warning::
        Because ``valueFrom`` can only be used with ``inputBinding``, any output providing a set of allowed values
        that are not ``string``-based will be ignored when converted to :term:`CWL` :term:`I/O`.

    :param cwl_io_type: Basic type for which allowed values should apply.
    :param cwl_io_symbols: Allowed values to restrict the :term:`I/O` definition.
    :return: Converted definition as CWL Enum or with relevant value validation as applicable for the type.
    """
    if cwl_io_type not in PACKAGE_BASIC_TYPES:
        return {}
    if cwl_io_type == "string":
        return {"type": {"type": PACKAGE_ENUM_BASE, "symbols": cwl_io_symbols}}
    if cwl_io_type not in PACKAGE_NUMERIC_TYPES:
        LOGGER.warning(
            "Could not resolve conversion of CWL I/O as Enum for type '%s'. "
            "Ignoring value validation against specified allowed values: %s.",
            cwl_io_type,
            cwl_io_symbols,
        )
        return {"type": cwl_io_type}

    if not (
        (all(isinstance(value, bool) for value in cwl_io_symbols) and cwl_io_type == "boolean") or
        (all(isinstance(value, int) for value in cwl_io_symbols) and cwl_io_type in PACKAGE_INTEGER_TYPES) or
        (all(isinstance(value, float) for value in cwl_io_symbols) and cwl_io_type in PACKAGE_FLOATING_TYPES)
    ):
        LOGGER.warning(
            "Incompatible CWL I/O type '%s' detected for specified allowed values: %s. "
            "Will use generic CWL 'Any' type instead.",
            cwl_io_type,
            cwl_io_symbols,
        )
        cwl_io_type = "Any"

    if io_select != IO_INPUT:
        return {"type": cwl_io_type}

    cwl_js_value_from = _get_cwl_js_value_from(cwl_io_symbols, allow_unique, allow_array)
    return {"type": cwl_io_type, "inputBinding": {"valueFrom": cwl_js_value_from}}


def any2cwl_io(wps_io, io_select):
    # type: (Union[JSON_IO_Type, WPS_IO_Type, OWS_IO_Type], IO_Select_Type) -> Tuple[CWL_IO_Type, Dict[str, str]]
    """
    Converts a :term:`WPS`-like :term:`I/O` from various :term:`WPS` library representations to :term:`CWL` :term:`I/O`.

    Conversion can be accomplished for :mod:`pywps` and :mod:`owslib` objects, as well as their :term:`JSON` equivalent.
    Because :term:`CWL` :term:`I/O` of type ``File`` with ``format`` field are namespaced, this is also returned if
    needed.

    :returns: converted :term:`I/O` and namespace dictionary with corresponding format references as required.
    """

    wps_io_cat = get_io_type_category(wps_io)
    wps_io_id = get_field(wps_io, "identifier", search_variations=True)
    cwl_ns = {}
    cwl_io = {"id": wps_io_id}  # type: CWL_IO_Type  # noqa

    # convert OAS format to JSON first to simplify following comparisons
    wps_io_type = get_field(wps_io, "type", search_variations=True)
    wps_io_schema = get_field(wps_io, "schema", search_variations=False)
    if wps_io_type is null and isinstance(wps_io_schema, dict):
        wps_io = oas2json_io(wps_io_schema)
        wps_io_cat = get_field(wps_io, "type", search_variations=False)
        wps_io_type = get_field(wps_io, "data_type", search_variations=False)

    wps_default = get_field(wps_io, "default", search_variations=True)
    wps_min_occ = get_field(wps_io, "min_occurs", search_variations=True, default=1)
    wps_max_occ = get_field(wps_io, "max_occurs", search_variations=True)
    is_min_null = wps_min_occ in [0, "0"]
    allow_unique = wps_min_occ in [0, "0", 1, "1"]
    allow_array = wps_max_occ != null and (wps_max_occ == "unbounded" or wps_max_occ > 1)

    if wps_io_cat not in list(WPS_COMPLEX_TYPES):
        cwl_io_type = any2cwl_literal_datatype(wps_io_type)
        if cwl_io_type is null:
            LOGGER.warning("Could not identify a CWL literal data type with [%s].", wps_io_type)
        wps_allow = get_field(wps_io, "allowed_values", search_variations=True)
        if isinstance(wps_allow, list) and len(wps_allow) > 0:
            cwl_io_enum = _convert_cwl_io_enum(cwl_io_type, wps_allow, io_select, allow_unique, allow_array)
            cwl_io.update(cwl_io_enum)
        else:
            cwl_io["type"] = cwl_io_type
    # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
    else:
        _convert_any2cwl_io_complex(cwl_io, cwl_ns, wps_io, io_select)

    # FIXME: multi-outputs (https://github.com/crim-ca/weaver/issues/25)
    # min/max occurs can only be in inputs, outputs are enforced min/max=1 by WPS
    if io_select == IO_INPUT:
        # field 'default' must correspond to a fallback "value", not a default "format"
        # NOTE:
        #   Don't set any 'default' field here (neither 'null' string or 'None' type) if no value was provided
        #   since those are interpreted by CWL as literal string 'null' (for 'string' type) or null object.
        #   Instead, 'null' string entry is added to 'type' to indicate drop/ignore missing input.
        if wps_default != null and not isinstance(wps_default, dict):
            cwl_io["default"] = wps_default

        if allow_array:
            cwl_array = {
                "type": PACKAGE_ARRAY_BASE,
                "items": cwl_io["type"]
            }
            # if single value still allowed, or explicitly multi-value array if min greater than one
            if wps_min_occ > 1:
                cwl_io["type"] = cwl_array
            else:
                cwl_io["type"] = [cwl_io["type"], cwl_array]

        # apply default null after handling literal/array/enum type variants
        # (easier to apply against their many different structures)
        if is_min_null:
            if isinstance(cwl_io["type"], list):
                cwl_io["type"].insert(0, "null")  # if min=0,max>1 (null, <type>, <array-type>)
            else:
                cwl_io["type"] = ["null", cwl_io["type"]]  # if min=0,max=1 (null, <type>)

    return cwl_io, cwl_ns


def _patch_cwl_enum_js_requirement(cwl_package):
    # type: (CWL) -> None
    """
    Applies the JavaScript requirement to validate a pseudo-``Enum`` applied to a :term:`CWL` input definition.

    .. seealso::
        - :func:`any2cwl_io`
        - :func:`_convert_cwl_io_enum`
        - :func:`_get_cwl_js_value_from`
    """
    cwl_items = cwl_package.get("inputs", [])
    if isinstance(cwl_items, dict):
        cwl_items = list(cwl_items.values())
    for cwl_input in cwl_items:
        cwl_value_from = cwl_input.get("inputBinding", {}).get("valueFrom", {})
        if isinstance(cwl_value_from, str):
            cwl_value_from = cwl_value_from.strip()
            if cwl_value_from.startswith("${") and cwl_value_from.endswith("}"):
                cwl_package.setdefault("requirements", {})
                cwl_package["requirements"].setdefault(CWL_REQUIREMENT_INLINE_JAVASCRIPT, {})
                return  # early exit, no need to check more


def wps2cwl_requirement(wps_service_url, wps_process_id):
    # type: (Union[str, ParseResult], str) -> JSON
    """
    Obtains the `CWL` requirements definition needed for parsing by a remote `WPS` provider as an `Application Package`.
    """
    return OrderedDict([
        ("cwlVersion", "v1.0"),
        ("class", "CommandLineTool"),
        ("hints", {
            CWL_REQUIREMENT_APP_WPS1: {
                "provider": get_url_without_query(wps_service_url),
                "process": wps_process_id,
            }}),
    ])


def ows2json(wps_process, wps_service_name, wps_service_url, wps_provider_name=None):
    # type: (ProcessOWS, str, Union[str, ParseResult], Optional[str]) -> Tuple[CWL, JSON]
    """
    Generates the `CWL` package and process definitions from a :class:`owslib.wps.Process` hosted under `WPS` location.
    """
    process_info = OrderedDict([
        ("id", wps_process.identifier),
        ("keywords", [wps_service_name] if wps_service_name else []),
    ])
    if wps_provider_name and wps_provider_name not in process_info["keywords"]:
        process_info["keywords"].append(wps_provider_name)
    default_title = wps_process.identifier.capitalize()
    process_info["title"] = get_field(wps_process, "title", default=default_title, search_variations=True)
    process_info["description"] = get_field(wps_process, "abstract", default=None, search_variations=True)
    process_info["version"] = get_field(wps_process, "version", default=None, search_variations=True)
    process_info["metadata"] = []
    if wps_process.metadata:
        for meta in wps_process.metadata:
            metadata = metadata2json(meta)
            if metadata:
                process_info["metadata"].append(metadata)
    process_info["inputs"] = []                 # type: List[JSON]
    process_info["outputs"] = []                # type: List[JSON]
    for wps_in in wps_process.dataInputs:       # type: OWS_Input_Type
        process_info["inputs"].append(ows2json_io(wps_in))
    for wps_out in wps_process.processOutputs:  # type: OWS_Output_Type
        process_info["outputs"].append(ows2json_io(wps_out))

    # generate CWL for WPS-1 using parsed WPS-3
    cwl_package = wps2cwl_requirement(wps_service_url, wps_process.identifier)
    for io_select in [IO_INPUT, IO_OUTPUT]:
        io_section = f"{io_select}s"
        cwl_package[io_section] = []
        for wps_io in process_info[io_section]:
            cwl_io, cwl_ns = any2cwl_io(wps_io, io_select)
            cwl_package[io_section].append(cwl_io)
            if cwl_ns:
                if "$namespaces" not in cwl_package:
                    cwl_package["$namespaces"] = {}
                cwl_package["$namespaces"].update(cwl_ns)
    _patch_cwl_enum_js_requirement(cwl_package)
    return cwl_package, process_info


def xml_wps2cwl(wps_process_response, settings):
    # type: (Response, AnySettingsContainer) -> Tuple[CWL, JSON]
    """
    Obtains the :term:`CWL` definition that corresponds to an :term:`XML` :term:`WPS` process.

    Converts a `WPS-1 ProcessDescription XML` tree structure to an equivalent `WPS-3 Process JSON`, and builds the
    associated :term:`CWL` package in conformance to :data:`weaver.processes.wps_package.CWL_REQUIREMENT_APP_WPS1`.

    :param wps_process_response: Valid response (XML, 200) from a `WPS-1 ProcessDescription`.
    :param settings: Application settings to retrieve additional request options.
    """
    def _tag_name(_xml):
        # type: (Union[xml_util.XML, str]) -> str
        """
        Obtains ``tag`` from a ``{namespace}Tag`` `XML` element.
        """
        if hasattr(_xml, "tag"):
            _xml = _xml.tag
        return _xml.split("}")[-1].lower()

    # look for `XML` structure starting at `ProcessDescription` (WPS-1)
    xml_resp = xml_util.fromstring(str2bytes(wps_process_response.content))
    xml_wps_process = xml_resp.xpath("//ProcessDescription")  # type: List[xml_util.XML]
    if not len(xml_wps_process) == 1:
        raise ValueError("Could not retrieve a valid 'ProcessDescription' from WPS-1 response.")
    process_id = None
    for sub_xml in xml_wps_process[0]:
        tag = _tag_name(sub_xml)
        if tag == "identifier":
            process_id = sub_xml.text
            break
    if not process_id:
        raise ValueError("Could not find a match for 'ProcessDescription.identifier' from WPS-1 response.")

    # transform WPS-1 -> WPS-3
    wps = get_wps_client(wps_process_response.url, settings)
    wps_service_url = urlparse(wps_process_response.url)
    if wps.provider:
        wps_service_name = wps.provider.name
    else:
        wps_service_name = wps_service_url.hostname
    wps_process = wps.describeprocess(process_id, xml=wps_process_response.content)
    cwl_package, process_info = ows2json(wps_process, wps_service_name, wps_service_url)
    return cwl_package, process_info


def ogcapi2cwl_process(payload, reference):
    # type: (JSON, str) -> Tuple[CWL, JSON]
    """
    Generate a :term:`CWL` for a remote :term:`OGC API - Processes` description to dispatch :term:`Process` execution.

    .. seealso::
        - :class:`weaver.processes.wps3_process.Wps3Process`

    :param payload: :term:`JSON` :term:`Process` description in :term:`OGC API - Processes` format.
    :param reference: URL where the :term:`Process` is located.
    :returns: Updated :term:`CWL` package with the reference to the :term:`Process`.
    """
    from weaver.processes.utils import is_cwl_package, load_package_file  # pylint: disable=C0415  # circular import

    payload_copy = copy.deepcopy(payload)
    process_info = payload_copy.get("process", payload)  # type: JSON  # OLD/OGC schemas nested process or at root

    # the process information is sufficient to define the process by itself,
    # but attempt retrieval of further details to generate better CWL references if it can be located
    ows_ref = process_info.get("owsContext", {}).get("offering", {}).get("content", {}).get("href")
    proc_ref = process_info.get("href")
    cwl_ref = proc_ref or ows_ref  # type: Optional[str]
    cwl_pkg = {}  # type: CWL
    if cwl_ref:
        cwl_pkg = load_package_file(cwl_ref)
    else:
        exec_unit = payload_copy.get("executionUnit")
        try:
            if sd.ExecutionUnitList(missing=colander.drop).deserialize(exec_unit) is not colander.drop:
                for unit in exec_unit:
                    unit_ref = unit.get("href")
                    unit_pkg = unit.get("unit")
                    if unit_ref:
                        cwl_pkg = load_package_file(unit_ref)
                        break
                    if is_cwl_package(unit_pkg):
                        cwl_pkg = unit_pkg
                        break
        except colander.Invalid:
            pass

    if cwl_pkg:
        # CWL resolved with most amount of metadata available
        # remove fields that would cause conflicting specification of the local CWL for its remote counterpart
        for drop_field in ["baseCommand", "arguments", "hints", "requirements"]:
            cwl_pkg.pop(drop_field, None)
    else:
        # if no CWL could be resolved, generate I/O from process
        io_ns = {}  # type: Dict[str, str]
        for io_select in [IO_INPUT, IO_OUTPUT]:
            io_holder = f"{io_select}s"  # type: Literal["inputs", "outputs"]  # noqa
            io_struct = copy.deepcopy(process_info.get(io_holder, {}))
            io_struct = normalize_ordered_io(io_struct)
            cwl_pkg[io_holder] = {}  # type: Dict[str, CWL_IO_Type]  # noqa
            for io_def in io_struct:
                io_id = get_field(io_def, "identifier", search_variations=True)
                cwl_io, cwl_ns = any2cwl_io(io_def, io_select)
                cwl_io.pop("id", None)  # remove duplicate since provided as key
                cwl_pkg[io_holder][io_id] = cwl_io  # type: ignore
                io_ns.update(cwl_ns)
        cwl_pkg.update({"$namespaces": io_ns} if io_ns else {})

    # even if the remote process is actually a Workflow on the target server,
    # dispatched execution from Weaver will consider it as a single application
    cwl_package = {
        "cwlVersion": "v1.0",
        "class": "CommandLineTool",
        "hints": {
            CWL_REQUIREMENT_APP_OGC_API: {
                "process": reference
            }
        }
    }
    cwl_package.update(cwl_pkg)  # type: ignore
    _patch_cwl_enum_js_requirement(cwl_package)
    payload_copy["executionUnit"] = [{"unit": cwl_package}]
    payload_copy["deploymentProfile"] = "http://www.opengis.net/profiles/eoc/ogcapiApplication"
    return cwl_package, payload_copy


def is_cwl_complex_type(io_info, complex_types=PACKAGE_COMPLEX_TYPES):
    # type: (CWL_IO_Type, Iterable[CWL_IO_ComplexType]) -> bool
    """
    Identifies if the provided :term:`CWL` input/output corresponds to one, many or a potential `Complex` type(s).

    When multiple distinct *atomic* types are allowed for a given I/O (e.g.: ``type: [string, File]``) and that one
    of them is one of the considered `Complex` type, the result will be ``True`` even if other types are not `Complex`.
    Similarly, optional `Complex` types combined with ``"null"`` will also return ``True``.

    :param io_info: :term:`I/O` to verify for complex type.
    :param complex_types:
        Complex types to consider.
        By default, any type between :term:`CWL` ``File`` and ``Directory`` are valid.
        The operation can be limited to one or the other if needed to identify a specific one.
    """
    io_type = io_info.get("type")
    if not io_type:
        raise ValueError(f"Missing CWL 'type' definition: [{io_info!s}]")
    if isinstance(io_type, str):
        return io_type in complex_types
    if isinstance(io_type, dict):
        if io_type["type"] == PACKAGE_ARRAY_BASE:
            return io_type["items"] in complex_types
        return io_type["type"] in complex_types
    if isinstance(io_type, list):
        return any(
            (isinstance(typ, str) and typ in complex_types) or
            is_cwl_complex_type({"type": typ}, complex_types)
            for typ in io_type
        )
    raise ValueError(f"Unknown parsing of CWL 'type' format ({type(io_type)!s}) [{io_type!s}] in [{io_info}]")


def parse_cwl_array_type(io_info, strict=True):
    # type: (CWL_IO_Type, bool) -> CWLIODefinition
    """
    Parses the specified I/O for one of the various potential CWL array definitions.

    :param io_info: :term:`CWL` I/O definition to parse.
    :param strict: Indicates if only pure :term:`CWL` definition is allowed, or allow implicit data-type conversions.
    :returns: Updated :term:`CWL` I/O definition with applicable properties.
    :raises PackageTypeError: if the array element doesn't have the required values and valid format.
    """
    # use mapping to allow sub-function updates
    io_return = CWLIODefinition(
        array=False,
        symbols=AnyValue,
        type=get_cwl_io_type_name(io_info["type"]),
        mode=MODE.NONE,
    )

    def _update_if_sub_enum(_io_item):
        # type: (CWL_IO_Type) -> bool
        """
        Updates the ``io_return`` parameters if ``io_item`` evaluates to a valid ``enum`` type.

        Parameter ``io_item`` should correspond to field ``items`` of an array I/O definition.
        Simple pass-through if the array item is not an ``enum``.
        """
        _def = parse_cwl_enum_type({"type": _io_item})
        if _def.enum:
            LOGGER.debug("I/O [%s] parsed as 'array' with sub-item as 'enum'", io_info["name"])
            io_return.enum = True
            io_return.type = _def.type
            io_return.mode = _def.mode
            io_return.symbols = _def.symbols
        return _def.enum

    # optional I/O could be an array of '["null", "<type>"]' with "<type>" being any of the formats parsed after
    # is it the literal representation instead of the shorthand with '?'
    if isinstance(io_info["type"], list) and any(sub_type == "null" for sub_type in io_info["type"]):
        # we can ignore the optional indication in this case because it doesn't impact following parsing
        io_return.type = list(filter(lambda sub_type: sub_type != "null", io_info["type"]))[0]

    # array type conversion when defined as '{"type": "array", "items": "<type>"}'
    # validate against 'Hashable' instead of 'dict' since 'OrderedDict'/'CommentedMap' can fail 'isinstance()'
    if (
        not isinstance(io_return.type, str)
        and not isinstance(io_return.type, Hashable)
        and "items" in io_return.type
        and "type" in io_return.type
    ):
        io_type = dict(io_return.type)  # make hashable to allow comparison
        if io_type["type"] != PACKAGE_ARRAY_BASE:
            raise PackageTypeError(f"Unsupported I/O 'array' definition: '{io_info!r}'.")
        # parse enum in case we got an array of allowed symbols
        io_items = get_cwl_io_type_name(io_type["items"])
        is_enum = _update_if_sub_enum(io_items)
        if not is_enum:
            io_return.type = io_items
        io_type = get_cwl_io_type_name(io_return.type)
        if io_type not in PACKAGE_ARRAY_ITEMS:  # includes Complex, so implicit literal-only check possible
            io_type = any2cwl_literal_datatype(io_type)
            if strict or io_type not in PACKAGE_ARRAY_ITEMS:
                raise PackageTypeError(f"Unsupported I/O 'array' definition: '{io_info!r}'.")
            io_return.type = io_type
        LOGGER.debug("I/O [%s] parsed as 'array' with nested dict notation", io_info["name"])
        io_return.array = True
    # array type conversion when defined as string '<type>[]'
    elif isinstance(io_return.type, str) and get_cwl_io_type_name(io_return.type) in PACKAGE_ARRAY_TYPES:
        io_return.type = get_cwl_io_type_name(io_return.type[:-2])  # remove '[]'
        if io_return.type in PACKAGE_CUSTOM_TYPES:
            # parse 'enum[]' for array of allowed symbols, provide expected structure for sub-item parsing
            io_item = deepcopy(io_info)
            io_item["type"] = io_return.type  # override corrected type without '[]'
            _update_if_sub_enum(io_item)
        if io_return.type not in PACKAGE_ARRAY_ITEMS:
            raise PackageTypeError(f"Unsupported I/O 'array' definition: '{io_info!r}'.")
        LOGGER.debug("I/O [%s] parsed as 'array' with shorthand '[]' notation", io_info["name"])
        io_return.array = True

    # in case the I/O was not an array parsed with one of the above conditions,
    # still check for enum to be consistant in returned definition if one was provided
    try:
        _update_if_sub_enum(io_info)
    except PackageTypeError:
        pass
    return io_return


def parse_cwl_enum_type(io_info):
    # type: (CWL_IO_Type) -> CWLIODefinition
    """
    Parses the specified I/O for potential CWL enum definition.

    :returns: Updated :term:`CWL` I/O definition with applicable properties.
    :raises PackageTypeError: if the enum doesn't have the required parameters and valid format.
    """
    io_type = get_cwl_io_type_name(io_info["type"])
    if not isinstance(io_type, dict) or "type" not in io_type:
        io_def = CWLIODefinition(
            type=io_type,
            enum=False,
            mode=MODE.NONE,
        )
        return io_def
    if isinstance(io_type, dict) and "type" in io_type and (
        isinstance(io_type["type"], str) and io_type["type"] not in PACKAGE_CUSTOM_TYPES or
        isinstance(io_type["type"], list)
    ):
        io_type = io_type["type"] if isinstance(io_type["type"], str) else PACKAGE_ARRAY_BASE
        io_def = CWLIODefinition(
            type=io_type,
            enum=False,
            mode=MODE.NONE,
        )
        return io_def

    if "symbols" not in io_type:
        raise PackageTypeError(f"Unsupported I/O 'enum' definition missing 'symbols': '{io_info!r}'.")
    io_allow = io_type["symbols"]
    if not isinstance(io_allow, list) or len(io_allow) < 1:
        raise PackageTypeError(f"Invalid I/O 'enum.symbols' definition: '{io_info!r}'.")

    # validate matching types in allowed symbols and convert to supported CWL type
    first_allow = io_allow[0]
    for io_i in io_allow:
        if type(io_i) is not type(first_allow):
            raise PackageTypeError(f"Ambiguous types in I/O 'enum.symbols' definition: '{io_info!r}'.")
    if isinstance(first_allow, str):
        io_type = "string"
    elif isinstance(first_allow, float):
        io_type = "float"
    elif isinstance(first_allow, int):
        io_type = "int"
    else:
        raise PackageTypeError(
            f"Unsupported I/O 'enum' base type: `{type(first_allow)!s}`, from definition: `{io_info!r}`."
        )

    io_def = CWLIODefinition(
        type=io_type,  # type: ignore
        enum=True,
        mode=MODE.SIMPLE,  # allowed value validator mode must be set for input
        symbols=io_allow,
    )
    return io_def


def get_cwl_io_type_name(io_type):
    # type: (Any) -> Any
    """
    Obtain the simple type-name representation of a :term:`CWL` I/O.

    Depending on :mod:`cwltool` version, types are represented with or without an extended prefix, and using an
    explicit quoted class representation rather than plain strings.
    """
    if isinstance(io_type, str):
        return str(io_type.replace("org.w3id.cwl.cwl.", ""))
    return io_type


def resolve_cwl_io_type_schema(io_info, cwl_schema_names=None):
    # type: (CWL_IO_Type, Optional[CWL_SchemaNames]) -> CWL_IO_Type
    """
    Reverse :term:`CWL` schema references by name back to their full :term:`CWL` I/O definition.

    .. seealso::
        - :meth:`weaver.processes.wps_package.WpsPackage.make_inputs`
        - :meth:`weaver.processes.wps_package.WpsPackage.update_cwl_schema_names`
    """
    if not isinstance(io_info, dict) or not cwl_schema_names:
        return get_cwl_io_type_name(io_info)
    io_type = io_info.get("type")
    io_item = io_info.get("items")
    if io_type == PACKAGE_ARRAY_BASE and isinstance(io_item, str):
        io_info = io_info.copy()  # avoid undoing CWL tool parsing/resolution
        io_name = get_cwl_io_type_name(io_item)  # avoid mapping back to File/Directory records in CWL schema names
        if io_name in cwl_schema_names:
            io_name = cwl_schema_names[io_item]._props
        io_info["items"] = io_name
    elif isinstance(io_type, str):
        io_info = io_info.copy()  # avoid undoing CWL tool parsing/resolution
        io_name = get_cwl_io_type_name(io_type)  # avoid mapping back to File/Directory records in CWL schema names
        if io_name in cwl_schema_names:
            io_name = cwl_schema_names[io_type]._props
        io_info["type"] = io_name
    return io_info


@dataclass
class CWLIODefinition(object):
    """
    Utility :term:`CWL` I/O definition to contain metadata from parsing results.

    .. seealso::
        :func:`weaver.processes.convert.get_cwl_io_type`
    """

    # provide dataclass conversions for 'tuple()', 'list()', 'dict()'

    def keys(self):
        # type: () -> List[str]
        fields = getattr(self, "__dataclass_fields__")
        return list(fields)

    def __getitem__(self, key):
        # type: (str) -> Any
        return getattr(self, key)

    def __iter__(self):
        # type: () -> Iterator[Any]
        for key in self.keys():
            value = self[key]
            yield value

    # --- FIELDS ---

    name: str = ""
    """
    Name (or identifier) or the I/O.
    """

    type: "Union[CWL_IO_LiteralType, CWL_IO_ComplexType, CWL_IO_DataType]" = None
    """
    Type of the :term:`CWL` I/O.

    If :attr:`enum` is ``True``, represents the enum base type.
    If :attr:`array` is ``True``, represents the item type.

    .. note::
        Before resolution with :func:`parse_cwl_array_type`, this attribute can temporarily hold any :term:`CWL` type
        structure (list, dict, nested types, etc.). After parsing, it will be resolved to the basic string type.
    """

    null: bool = False
    """
    Indicates if the I/O is nullable.

    This is obtained from a type composed of ``"null"`` and something else,
    or using the shorthand ``{type}?`` notation.
    """

    min_occurs: int = 1
    """
    Minimum number of occurrences allowed.

    When :attr:`null` is ``True``, it is equal to ``0``.
    Otherwise, it is greater or equal to ``1``.
    If greater than ``1``, :attr:`array` should be ``True``.
    """

    max_occurs: int = 1
    """
    Maximum number of occurrences allowed.

    Applies only when :attr:`array` is ``True``. Otherwise, always equal to ``1``.
    Can take the value :data:`PACKAGE_ARRAY_MAX_SIZE` to represent ``"unbounded"`` occurrences.
    """

    array: bool = False
    """
    Specifies if the I/O is of array type.
    """

    enum: bool = False
    """
    Specifies if the I/O is of enum type.
    """

    symbols: "Union[CWL_IO_EnumSymbols, AnyValue, Type[AnyValue]]" = AnyValue
    """
    Specifies the allowed values when the definition is marked as :attr:`enum`.

    When not overriden by literal values, it uses the default :class:`AnyValue`.
    """

    mode: MODE = MODE.NONE
    """
    Validation mode to be applied if I/O requires it.

    Defaults to :attr:`MODE.NONE`. Indicates how strict the validation must be.
    Usually applies when an enum must only allow a specific set of symbols.
    Can also be used with Media-Types in more advanced validation use case with :mod:`pywps`.
    """


def get_cwl_io_type(io_info, strict=True, cwl_schema_names=None):
    # type: (CWL_IO_Type, bool, Optional[CWL_SchemaNames]) -> CWLIODefinition
    """
    Obtains the basic type of the CWL input and identity if it is optional.

    CWL allows multiple shorthand representation or combined types definition.
    The *base* type must be extracted in order to identify the expected data format and supported values.

    Obtains real type if ``"default"`` or shorthand ``"<type>?"`` was in CWL, which
    can also be defined as type ``["null", <type>]``.

    CWL allows multiple distinct types (e.g.: ``string`` and ``int`` simultaneously), but not WPS inputs.
    WPS allows only different amount of *same type* through ``minOccurs`` and ``maxOccurs``.
    Considering WPS conversion, we can also have the following definition ``["null", <type>, <array-type>]`` will all
    basic types matching exactly. Whether single or array-like type, the base type can be extracted.

    :param io_info: :term:`CWL` definition to parse.
    :param strict: Indicates if only pure :term:`CWL` definition is allowed, or allow implicit data-type conversions.
    :param cwl_schema_names: Mapping of CWL type schema references to resolve in long form if used in a definition.
    :return: tuple of guessed base type and flag indicating if it can be null (optional input).
    """
    io_type = get_cwl_io_type_name(io_info["type"])
    is_null = False
    io_mode = MODE.NONE
    io_allow = AnyValue

    # parse multi-definition
    if isinstance(io_type, list):
        if not len(io_type) > 1:
            raise PackageTypeError(f"Unsupported I/O type as list cannot have only one base type: '{io_info}'")
        if "null" in io_type:
            if len(io_type) == 1:
                raise PackageTypeError(f"Unsupported I/O cannot be only 'null' type: '{io_info}'")
            LOGGER.debug("I/O parsed for 'default'")
            is_null = True  # I/O can be omitted since default value exists
            io_type = [typ for typ in io_type if typ != "null"]

        if len(io_type) == 1:  # valid if other was "null" now removed
            io_type = io_type[0]
        else:
            # check that many sub-type definitions all match same base type (no conflicting literals)
            io_type_many = set()
            io_base_type = None
            for i, typ in enumerate(io_type, start=int(is_null)):
                typ = resolve_cwl_io_type_schema(typ, cwl_schema_names)
                io_name = io_info["name"]
                sub_type = {"type": typ, "name": f"{io_name}[{i}]"}  # type: CWL_IO_Type
                array_io_def = parse_cwl_array_type(sub_type, strict=strict)
                enum_io_def = parse_cwl_enum_type(sub_type)
                # array base type more important than enum because later array conversion also handles allowed values
                if array_io_def.array:
                    io_base_type = typ  # highest priority (can have sub-literal or sub-enum)
                    io_type_many.add(array_io_def.type)
                elif enum_io_def.enum:
                    io_base_type = io_base_type if io_base_type is not None else enum_io_def.type  # less priority
                    io_type_many.add(enum_io_def.type)
                else:
                    io_base_type = io_base_type if io_base_type is not None else typ  # less priority
                    io_type_many.add(typ)  # literal base type by itself (not array/enum)
            if len(io_type_many) != 1:
                raise PackageTypeError(f"Unsupported I/O with many distinct base types for info: '{io_info!s}'")
            io_type = io_base_type

        LOGGER.debug("I/O parsed for multiple base types")

    # parse single-definition
    io_info = io_info.copy()
    io_info["type"] = io_type  # override resolved multi-type base for more parsing
    io_name = io_info["name"]
    io_min_occurs = 0 if is_null else 1
    io_max_occurs = 1  # unless array after

    # convert array types
    array_io_def = parse_cwl_array_type(io_info, strict=strict)
    if array_io_def.array:
        LOGGER.debug("I/O parsed for 'array'")
        io_type = array_io_def.type
        io_max_occurs = PACKAGE_ARRAY_MAX_SIZE

    # convert enum types
    enum_io_def = parse_cwl_enum_type(io_info)
    is_enum = False
    if enum_io_def.enum:
        LOGGER.debug("I/O parsed for 'enum' from base")
        io_type = enum_io_def.type
        io_allow = enum_io_def.symbols
        io_mode = enum_io_def.mode
        is_enum = True
    elif array_io_def.enum:
        LOGGER.debug("I/O parsed for 'enum' from array")
        io_type = array_io_def.type
        io_allow = array_io_def.symbols
        io_mode = array_io_def.mode
        is_enum = True

    # debug info for unhandled types conversion
    if not isinstance(io_type, str):
        LOGGER.debug("is_array:      [%s]", repr(array_io_def.array))
        LOGGER.debug("array_elem:    [%s]", repr(array_io_def.type))
        LOGGER.debug("is_enum:       [%s]", repr(enum_io_def.enum))
        LOGGER.debug("enum_type:     [%s]", repr(enum_io_def.type))
        LOGGER.debug("enum_allow:    [%s]", repr(enum_io_def.symbols))
        LOGGER.debug("io_info:       [%s]", repr(io_info))
        LOGGER.debug("io_type:       [%s]", repr(io_type))
        LOGGER.debug("type(io_type): [%s]", type(io_type))
        raise TypeError(f"I/O type has not been properly decoded. Should be a string, got: '{io_type!r}'")

    io_type = get_cwl_io_type_name(io_type)

    # parse shorthand notation for nullable
    if io_type.endswith("?"):
        io_type = io_type[:-1]
        io_min_occurs = 0
        is_null = True

    if io_type not in PACKAGE_COMPLEX_TYPES:
        io_type = any2cwl_literal_datatype(io_type)
    io_def = CWLIODefinition(
        name=io_name,
        type=io_type,
        null=is_null,
        min_occurs=io_min_occurs,
        max_occurs=io_max_occurs,
        array=array_io_def.array,
        enum=is_enum,
        symbols=io_allow,
        mode=io_mode,
    )
    return io_def


def cwl2wps_io(io_info, io_select):
    # type:(CWL_IO_Type, IO_Select_Type) -> WPS_IO_Type
    """
    Converts input/output parameters from CWL types to WPS types.

    :param io_info: parsed IO of a CWL file
    :param io_select: :py:data:`IO_INPUT` or :py:data:`IO_OUTPUT` to specify desired WPS type conversion.
    :returns: corresponding IO in WPS format
    """
    is_input = False
    is_output = False
    # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
    if io_select == IO_INPUT:
        is_input = True
        io_literal = LiteralInput       # type: Union[Type[LiteralInput], Type[LiteralOutput]]
        io_complex = ComplexInput       # type: Union[Type[ComplexInput], Type[ComplexOutput]]
        # io_bbox = BoundingBoxInput      # type: Union[Type[BoundingBoxInput], Type[BoundingBoxOutput]]
    elif io_select == IO_OUTPUT:
        is_output = True
        io_literal = LiteralOutput      # type: Union[Type[LiteralInput], Type[LiteralOutput]]
        io_complex = ComplexOutput      # type: Union[Type[ComplexInput], Type[ComplexOutput]]
        # io_bbox = BoundingBoxOutput     # type: Union[Type[BoundingBoxInput], Type[BoundingBoxOutput]]
    else:
        raise PackageTypeError(f"Unsupported I/O info definition: '{io_info!r}' with '{io_select}'.")

    # obtain base type considering possible CWL type representations
    io_def = get_cwl_io_type(io_info)

    # literal types
    if io_def.enum or (isinstance(io_def.type, str) and io_def.type in PACKAGE_LITERAL_TYPES):
        if io_def.type == "Any":
            io_def.type = "anyvalue"
        if io_def.type == "null":
            io_def.type = "novalue"
        if io_def.type in ["int", "integer", "long"]:
            io_def.type = "integer"
        if io_def.type in ["float", "double"]:
            io_def.type = "float"
        # keywords commonly used by I/O
        kw = {
            "identifier": io_def.name,
            "title": io_info.get("label", ""),
            "abstract": io_info.get("doc", ""),
            "data_type": io_def.type,
            "mode": io_def.mode,
        }
        if is_input:
            # avoid storing 'AnyValue' which become more problematic than
            # anything later on when CWL/WPS merging is attempted
            if io_def.symbols is not AnyValue:
                kw["allowed_values"] = io_def.symbols
            kw["default"] = io_info.get("default", None)
            kw["min_occurs"] = io_def.min_occurs
            kw["max_occurs"] = io_def.max_occurs
        return io_literal(**kw)
    # complex types
    else:
        # keywords commonly used by I/O
        kw = {
            "identifier": io_def.name,
            "title": io_info.get("label", io_def.name),
            "abstract": io_info.get("doc", ""),
        }
        # format can represent either a Media-Type or a schema reference
        # - format as Media-Type is useful for WPS Complex
        # - format as schema is useful for WPS BoundingBox JSON/YAML structure
        if "format" in io_info:
            io_fmt = io_info["format"]
            io_formats = [io_fmt] if isinstance(io_fmt, str) else io_fmt
            io_formats = [get_format(fmt) for fmt in io_formats]
            for i, io_format in enumerate(list(io_formats)):
                # when CWL namespaced format are not resolved, full path URI to schema is expected
                # because of full URI, should have lots of '/' (including protocol separator),
                # use this to detect content schema reference vs content media-type reference
                if io_format and len(io_format.mime_type.split("/")) > 2:
                    io_ext = os.path.splitext(io_format.mime_type)[-1]
                    io_typ = get_content_type(io_ext)
                    io_format = Format(io_typ, extension=io_ext, schema=io_format.mime_type)
                    io_formats[i] = io_format
            kw["supported_formats"] = io_formats
            kw["mode"] = MODE.SIMPLE  # only validate the extension (not file contents)
        else:
            # we need to minimally add 1 format, otherwise empty list is evaluated as None by pywps
            # when "supported_formats" is None, the process's json property raises because of it cannot iterate formats
            if io_def.type == PACKAGE_FILE_TYPE:
                kw["supported_formats"] = [DEFAULT_FORMAT]
            if io_def.type == PACKAGE_DIRECTORY_TYPE:
                kw["supported_formats"] = [get_format(ContentType.APP_DIR)]
            kw["mode"] = MODE.NONE  # don't validate anything as default is only raw text
        if is_output:
            if io_def.type == PACKAGE_DIRECTORY_TYPE:
                kw["as_reference"] = True
            if io_def.type == PACKAGE_FILE_TYPE:
                has_contents = io_info.get("contents") is not None
                kw["as_reference"] = not has_contents
        else:
            # note:
            #   value of 'data_format' is identified as 'default' input format if specified with `Format`
            #   otherwise, `None` makes it automatically use the first one available in 'supported_formats'
            kw["data_format"] = get_field(io_info, "data_format")
            kw["data_format"] = json2wps_field(kw["data_format"], "supported_formats") if kw["data_format"] else None
            kw.update({
                "min_occurs": io_def.min_occurs,
                "max_occurs": io_def.max_occurs,
            })
        return io_complex(**kw)


def cwl2json_input_values(data, schema=ProcessSchema.OGC):
    # type: (Dict[str, CWL_IO_Value], ProcessSchemaType) -> ExecutionInputs
    """
    Converts :term:`CWL` formatted :term:`Job` inputs to corresponding :term:`OGC API - Processes` format.

    :param data: dictionary with inputs formatted as key-value pairs with relevant structure based on :term:`CWL` types.
    :param schema: either ``OGC`` or ``OLD`` format respectively for mapping/listing representations.
    :raises TypeError: if input data is invalid.
    :raises ValueError: if any input value could not be parsed with expected schema.
    :returns: converted inputs for :term:`Job` submission either in ``OGC`` or ``OLD`` format.
    """
    def _get_file_input(input_data):
        # type: (CWL_IO_FileValue) -> JobValueFile
        input_file = {"href": input_data.get("path")}
        cwl_fmt_type = input_data.get("format")
        if isinstance(cwl_fmt_type, str):
            fmt = get_format(cwl_fmt_type)
            if "encoding" in input_data:
                fmt.encoding = input_data["encoding"]
            input_file["format"] = fmt.json
        return input_file

    if not isinstance(data, dict):
        data_type = fully_qualified_name(data)
        raise TypeError(f"Invalid CWL input values format must be a dictionary of keys to values. Got [{data_type}].")
    inputs = {}
    for input_id, input_value in data.items():
        # single file
        if isinstance(input_value, dict) and input_value.get("class") == PACKAGE_FILE_TYPE:
            inputs[input_id] = _get_file_input(input_value)
        # single literal value
        elif isinstance(input_value, (str, int, float, bool)):
            inputs[input_id] = {"value": input_value}
        # multiple files
        elif isinstance(input_value, list) and all(
            isinstance(val, dict) and val.get("class") == PACKAGE_FILE_TYPE for val in input_value
        ):
            inputs[input_id] = [_get_file_input(val) for val in input_value]
        # multiple literal values
        elif isinstance(input_value, list) and all(
            isinstance(val, (str, int, float, bool)) for val in input_value
        ):
            inputs[input_id] = [{"value": val} for val in input_value]
        else:
            raise ValueError(f"Input [{input_id}] value definition could not be parsed: {input_value!s}")
    schema = schema.upper()
    if schema == ProcessSchema.OGC:
        return inputs
    if schema != ProcessSchema.OLD:
        raise NotImplementedError(f"Unknown conversion format of input values for schema: [{schema}]")
    return convert_input_values_schema(inputs, ProcessSchema.OLD)


@overload
def convert_input_values_schema(inputs, schema):
    # type: (ExecutionInputs, JobInputsOutputsSchema.OGC) -> ExecutionInputsMap
    ...


@overload
def convert_input_values_schema(inputs, schema):
    # type: (ExecutionInputs, JobInputsOutputsSchema.OLD) -> ExecutionInputsList
    ...


def convert_input_values_schema(inputs, schema):
    # type: (ExecutionInputs, JobInputsOutputsSchemaType) -> ExecutionInputs
    """
    Convert execution input values between equivalent formats.

    .. seealso::
        - :func:`convert_output_params_schema`
        - :func:`normalize_ordered_io` for I/O definitions.

    :param inputs: Inputs to convert.
    :param schema: Desired schema.
    :return: Converted inputs.
    """
    if isinstance(schema, str):
        schema = schema.lower().split("+", 1)[0]
    if (
        (schema == JobInputsOutputsSchema.OGC and isinstance(inputs, dict)) or
        (schema == JobInputsOutputsSchema.OLD and isinstance(inputs, list))
    ):
        return inputs
    if (
        (schema == JobInputsOutputsSchema.OGC and not isinstance(inputs, list)) or
        (schema == JobInputsOutputsSchema.OLD and not isinstance(inputs, dict))
    ):
        name = fully_qualified_name(inputs)
        raise ValueError(f"Unknown conversion method to schema [{schema}] for inputs of type [{name}]: {inputs}")
    if schema == JobInputsOutputsSchema.OGC:
        input_dict = {}
        for input_item in inputs:
            input_id = get_any_id(input_item, pop=True)
            input_val = get_any_value(input_item)
            input_key = get_any_value(input_item, key=True, data=True, file=False)
            # if the input type is data, values are grouped directly (inline values)
            # if the input type is file, {reference + format} must both be regrouped
            input_data = input_val if input_key else input_item
            if input_id not in input_dict:
                input_dict[input_id] = input_data
            else:
                # when repeated input ID are found, they must be regrouped as list under that ID
                input_prev = input_dict[input_id]
                if not isinstance(input_prev, list):
                    input_prev = [input_prev]
                input_prev.append(input_data)
                input_dict[input_id] = input_prev
        return input_dict
    if schema == JobInputsOutputsSchema.OLD:
        input_list = []
        for input_id, input_value in inputs.items():
            # list must be flattened with repeating ID
            if isinstance(input_value, list):
                for input_data in input_value:
                    if isinstance(input_data, dict):
                        # can be either nested {value: literal} or {file + format} items
                        # either way, those are already in the desired format
                        input_item = {"id": input_id}
                        input_item.update(input_data)
                    else:
                        # otherwise only literals are accepted inline
                        input_item = {"id": input_id, "value": input_data}
                    input_list.append(input_item)
            elif isinstance(input_value, dict):
                input_key = list(input_value)[0]
                input_value = input_value[input_key]
                input_list.append({"id": input_id, input_key: input_value})
            else:
                input_list.append({"id": input_id, "value": input_value})
        return input_list
    raise NotImplementedError(f"Unknown conversion format of input values for schema: [{schema}]")


@overload
def convert_output_params_schema(inputs, schema):
    # type: (ExecutionOutputs, JobInputsOutputsSchema.OGC) -> ExecutionOutputsMap
    ...


@overload
def convert_output_params_schema(inputs, schema):
    # type: (ExecutionOutputs, JobInputsOutputsSchema.OLD) -> ExecutionOutputsList
    ...


def convert_output_params_schema(outputs, schema):
    # type: (ExecutionOutputs, JobInputsOutputsSchemaType) -> ExecutionOutputs
    """
    Convert execution output parameters between equivalent formats.

    .. warning::
        These outputs are not *values* (i.e.: *results*), but *submitted* :term:`Job` outputs for return definitions.
        Contents are transferred as-is without any consideration of ``value`` or ``href`` fields.

    .. seealso::
        - :func:`convert_input_values_schema`
        - :func:`normalize_ordered_io` for I/O definitions.

    :param outputs: Outputs to convert.
    :param schema: Desired schema.
    :return: Converted outputs.
    """
    if isinstance(schema, str):
        schema = schema.lower().split("+")[0]
    if (
        (schema == JobInputsOutputsSchema.OGC and isinstance(outputs, dict)) or
        (schema == JobInputsOutputsSchema.OLD and isinstance(outputs, list))
    ):
        return outputs
    if (
        (schema == JobInputsOutputsSchema.OGC and not isinstance(outputs, list)) or
        (schema == JobInputsOutputsSchema.OLD and not isinstance(outputs, dict))
    ):
        name = fully_qualified_name(outputs)
        raise ValueError(f"Unknown conversion method to schema [{schema}] for outputs of type [{name}]: {outputs}")
    if schema == JobInputsOutputsSchema.OGC:
        out_dict = {}
        for out in outputs:
            out_id = get_any_id(out, pop=True)
            out_dict[out_id] = out
        return out_dict
    if schema == JobInputsOutputsSchema.OLD:
        out_list = [{"id": out} for out in outputs]
        for out in out_list:
            out.update(outputs[out["id"]])
        return out_list
    raise NotImplementedError(f"Unknown conversion format of outputs definitions for schema: [{schema}]")


def repr2json_input_params(value, converter=None):
    # type: (str, Optional[Callable[[str], Any]]) -> DataInputType
    """
    Extracts and converts the value and its associated parameters from a :term:`KVP` string representation.

    This function only interprets a pre-extracted single-value definition (i.e.: without the input ID) from a parent
    :term:`KVP` string.

    .. seealso::
        Use :func:`repr2json_input_values` For parsing multi-value arrays and the full :term:`KVP` including the ID.

    :param value: String representation of the value to be interpreted.
    :param converter: Conversion function of the value after parsing.
    :return: Converted value and additional parameters if applicable.
    """
    params = value.split("@")
    value = params[0]
    if converter is not None:
        value = converter(value)
    params = params[1:]
    parameters = {}
    for param in params:
        param_key, param_val = param.split("=", 1)
        parameters[param_key] = unquote(param_val)
    return {"data": value, **parameters}


def repr2json_input_values(inputs):
    # type: (List[str]) -> ExecutionInputsList
    """
    Converts inputs in string :term:`KVP` representation to corresponding :term:`JSON` values.

    Expected format of the input is as follows:

    .. code-block:: text

        input_id[:input_type]=input_value[@input_parameter][;input_array[@input_parameter]][;...]

    Where:
        - ``input_id`` represents the target identifier of the input
        - ``input_type`` represents the conversion type, as required
          (includes ``File`` for ``href`` instead of ``value`` key in resulting object)
        - ``input_value`` represents the desired value subject to conversion by ``input_type``
        - ``input_array`` represents any additional values for array-like inputs (``maxOccurs > 1``)
        - ``input_parameter`` represents additional :term:`KVP` details associated to each
          ``input_value``/``input_array`` part (i.e.: per array element if applicable)

    The separator character for representing array-like values is ``;`` because the full :term:`KVP`
    (already split into a list as argument to this function), could be formed of multiple comma (``,``) or
    ampersand (``&``) separated input definitions, depending on where the definition came from (e.g.: URI).

    The ``input_parameter`` portion can combine multiple parameters each separated by ``@`` and themselves formed with
    :term:`KVP` representation of the corresponding parameter names and values. Parameter names do not need to be
    consistent between distinct array elements. For example, a multi-parameters input could be formatted as follows:

    .. code-block:: text

        input_id=item_value1@param1=value1@param2=value2;item_value2@other1=value1

    .. note::
        - Any character that matches one of the separators that should be interpreted literally should be URL-encoded.
        - Single (``'``) and double (``"``) quotes are removed if they delimit a ``File`` reference.

    :param inputs: list of string inputs to parse.
    :return: parsed inputs if successful.
    """
    values = []
    for str_input in inputs:
        str_id, str_val = str_input.split("=", 1)
        str_id_typ = str_id.split(":")
        if len(str_id_typ) == 2:
            str_id, str_typ = str_id_typ
        elif len(str_id_typ) != 1:
            raise ValueError(f"Invalid input value ID representation. Must be 'ID[:TYPE]' for '{str_id!s}'.")
        else:
            str_typ = "string"
        val_typ = any2cwl_literal_datatype(str_typ)
        if not str_id or (val_typ is null and str_typ not in INPUT_VALUE_TYPE_MAPPING):
            if str_id and val_typ is null:
                LOGGER.warning("Could not identify a CWL literal data type with [%s].", str_id)
            raise ValueError(f"Invalid input value ID representation. "
                             f"Missing or unknown 'ID[:TYPE]' parts after resolution as '{str_id!s}:{str_typ!s}'.")
        map_typ = val_typ if val_typ is not null else str_typ
        arr_val = str_val.split(";")
        convert = INPUT_VALUE_TYPE_MAPPING[map_typ]
        arr_val = [repr2json_input_params(val, convert) for val in arr_val]
        if map_typ.capitalize() == PACKAGE_FILE_TYPE:
            val_key = "href"
            for val in arr_val:
                ref = val["data"]
                if (ref.startswith("'") and ref.endswith("'")) or (ref.startswith("\"") and ref.endswith("\"")):
                    val["data"] = ref[1:-1]
                fmt = {}  # transfer parameters matching format fields that must be nested in value definition
                for field, target in [("mime_type", "mediaType"), ("encoding", "encoding"), ("schema", "schema")]:
                    val_field = get_field(val, field, search_variations=True, pop_found=True)
                    if val_field is not null:
                        fmt[target] = val_field
                if fmt:
                    val["format"] = fmt
        else:
            val_key = "value"
        values.extend([{"id": str_id, val_key: val.pop("data"), **val} for val in arr_val])
    return values  # type: ignore


def any2cwl_literal_datatype(io_type):
    # type: (str) -> Union[str, Type[null]]
    """
    Solves common literal data-type names to supported ones for `CWL`.
    """
    if io_type in WPS_LITERAL_DATA_STRING | OAS_LITERAL_STRING_FORMATS:
        return "string"
    if io_type in WPS_LITERAL_DATA_INTEGER | OAS_LITERAL_INTEGER_FORMATS:
        return "int"
    if io_type in WPS_LITERAL_DATA_FLOAT | OAS_LITERAL_FLOAT_FORMATS | OAS_LITERAL_NUMERIC:
        return "float"
    if io_type in WPS_LITERAL_DATA_BOOLEAN:
        return "boolean"
    return null


def any2wps_literal_datatype(io_type, is_value=False, pywps=False):
    # type: (AnyValueType, bool, bool) -> Union[str, Type[null]]
    """
    Solves common literal data-type names to supported ones for `WPS`.

    Verification is accomplished by name when ``is_value=False``, otherwise with python ``type`` when ``is_value=True``.

    :param io_type: Type to convert to :term:`WPS` supported literal data type.
    :param is_value: If enabled, consider :paramref:`io_type` literal data itself to attempt detection of the type.
    :param pywps: If enabled, restrict only to types supported by :mod:`pywps` (subset of full :term:`WPS`).
    """
    if isinstance(io_type, str):
        if not is_value:
            if io_type in WPS_LITERAL_DATA_STRING | OAS_LITERAL_STRING_FORMATS:
                if io_type in WPS_LITERAL_DATA_DATETIME | OAS_LITERAL_DATETIME_FORMATS:
                    return io_type if io_type in WPS_LITERAL_DATA_DATETIME else "dateTime"
                return "string"
            if io_type in WPS_LITERAL_DATA_INTEGER | OAS_LITERAL_INTEGER_FORMATS:
                return "integer"
            if io_type in WPS_LITERAL_DATA_FLOAT | OAS_LITERAL_FLOAT_FORMATS | OAS_LITERAL_NUMERIC:
                return "float" if pywps or io_type not in WPS_LITERAL_DATA_FLOAT else io_type
            if io_type in WPS_LITERAL_DATA_BOOLEAN:
                return "boolean"
        LOGGER.warning("Unknown named literal data type: '%s', using default 'string'. Should be one of: %s",
                       io_type, list(WPS_LITERAL_DATA_TYPES))
        return "string"
    if is_value and isinstance(io_type, bool):
        return "boolean"
    if is_value and isinstance(io_type, int):
        return "integer"
    if is_value and isinstance(io_type, float):
        return "float"
    return null


def any2json_literal_allowed_value(io_allow):
    # type: (Union[AllowedValue, JSON, str, float, int, bool]) -> Union[JSON, str, str, float, int, bool, Type[null]]
    """
    Converts an ``AllowedValues`` definition from different packages into standardized JSON representation of `OGC-API`.
    """
    if isinstance(io_allow, AllowedValue):
        io_allow = io_allow.json
    if isinstance(io_allow, dict):
        wps_range = {}
        for field, dest in [
            ("range_minimum", "minimumValue"),
            ("range_maximum", "maximumValue"),
            ("range_spacing", "spacing"),
            ("range_closure", "rangeClosure")
        ]:
            wps_range_value = get_field(io_allow, field, search_variations=True, pop_found=True)
            if wps_range_value is not null:
                wps_range[dest] = wps_range_value
        # in case input was a PyWPS AllowedValue object converted to JSON,
        # extra metadata must be removed/transformed accordingly for literal value
        basic_type = io_allow.pop("type", None)
        allowed_type = io_allow.pop("allowed_type", None)
        allowed_type = allowed_type or basic_type
        allowed_value = io_allow.pop("value", None)
        if allowed_value is not None:
            # note: closure must be ignored for range compare because it defaults to 'close' even for a 'value' type
            range_fields = ["minimumValue", "maximumValue", "spacing"]
            if allowed_type == "value" or not any(field in io_allow for field in range_fields):
                return allowed_value
        io_allow = wps_range
        if not io_allow:  # empty container
            return null
    return io_allow


def any2json_literal_data_domains(io_info):
    # type: (ANY_IO_Type) -> Union[Type[null], List[JSON]]
    """
    Extracts allowed value constrains from the input definition and generate the expected literal data domains.

    The generated result, if applicable, corresponds to a list of a single instance of
    schema definition :class:`weaver.wps_restapi.swagger_definitions.LiteralDataDomainList` with following structure.

    .. code-block:: yaml

        default: bool
        defaultValue: float, int, bool, str
        dataType: {name: string, <reference: url: string>}
        UOMs:
          - default: {uom: string, reference: url-string}
          - supported: [{uom: string, reference: url-string}]
        valueDefinition:
          oneOf:
          - string
          - url-string
          - {anyValue: bool}
          - [float, int, bool, str]
          - [{minimum: number/none, maximum: number/none, spacing: number/none, closure: str open/close variations}]
    """
    io_type = get_field(io_info, "type", search_variations=False)
    if io_type in [WPS_BOUNDINGBOX, WPS_COMPLEX]:
        return null

    io_data_type = get_field(io_info, "type", search_variations=True, only_variations=True)
    domain = {
        "default": True,  # since it is generated from convert, only one is available anyway
        "dataType": {
            "name": any2wps_literal_datatype(io_data_type, is_value=False),  # just to make sure, simplify type
            # reference:  # FIXME: unsupported named-reference data-type (need example to test it)
        }
    }
    wps_allowed_values = get_field(io_info, "allowed_values", search_variations=True)
    wps_default_value = get_field(io_info, "default", search_variations=True)
    wps_value_definition = {"anyValue": get_field(io_info, "any_value", search_variations=True, default=False)}
    if wps_default_value not in [null, None]:
        domain["defaultValue"] = wps_default_value
    if isinstance(wps_allowed_values, list) and len(wps_allowed_values) > 0:
        wps_allowed_values = [any2json_literal_allowed_value(io_value) for io_value in wps_allowed_values]
        wps_allowed_values = [io_value for io_value in wps_allowed_values if io_value is not null]
        if wps_allowed_values:
            wps_value_definition = wps_allowed_values
    domain["valueDefinition"] = wps_value_definition

    wps_support_uom = get_field(io_info, "uoms", search_variations=True)
    wps_default_uom = get_field(io_info, "uom", search_variations=True)
    if wps_support_uom:
        domain["UOMs"] = {
            "supported": [uom2json(uom) for uom in wps_support_uom],
        }
        if wps_default_uom:
            domain["UOMs"]["default"] = uom2json(wps_default_uom)

    return [domain]


def json2oas_io_complex(io_info, io_hint=null):
    # type: (JSON_IO_Type, Union[OpenAPISchema, Type[null]]) -> OpenAPISchema
    """
    Convert a single-dimension complex :term:`JSON` I/O definition into corresponding :term:`OpenAPI` schema.
    """
    item_types = []
    item_formats = get_field(io_info, "supported_formats", search_variations=True)
    if isinstance(item_formats, list) and item_formats:
        json_schema_refs = set()
        json_schema_any = None
        for fmt in item_formats:
            fmt_media = get_field(fmt, "mime_type", search_variations=True)
            fmt_encode = get_field(fmt, "encoding", search_variations=True)
            fmt_schema = get_field(fmt, "schema", search_variations=False)
            # heuristic to guess more specific encoding
            fmt_type_as_text = ["multipart/", "application/"]  # others always binary (eg: image)
            fmt_subtype_as_text = ["+xml", "/json", "yaml"]
            if not fmt_encode:
                if fmt_media.startswith("text/") or (
                    any(fmt_media.startswith(fmt_sub) for fmt_sub in fmt_type_as_text) and
                    any(fmt_enc in fmt_media for fmt_enc in fmt_subtype_as_text)
                ):
                    fmt_encode = None
                else:
                    fmt_encode = "base64"
            if fmt_encode:
                # format/contentEncoding somewhat redundant,
                # but providing both allows using "preferred" approach by either OpenAPI 3.0/3.1
                item_types.append({
                    "type": "string",
                    "format": "binary",
                    "contentMediaType": fmt_media,
                    "contentEncoding": fmt_encode,
                })
            else:
                item_types.append({
                    "type": "string",
                    "contentMediaType": fmt_media,
                })
            if fmt_schema:  # could be non-JSON, just a reference
                item_types[-1]["contentSchema"] = fmt_schema
            if ContentType.APP_JSON in fmt_media:
                json_schema_any = True
                if fmt_schema:  # got an explicit JSON
                    json_schema_any = False
                    item_types[-1]["contentSchema"] = fmt_schema
                    json_schema_refs.add(fmt_schema)
        json_objects = []
        if json_schema_any:
            # if no ref schema, best we can do is 'any JSON' since cannot guess applicable schema not provided by user
            json_objects = [{"type": "object", "additionalProperties": True}]
        elif json_schema_refs:
            json_objects = [{"$ref": ref} for ref in json_schema_refs]
        # if we have a hint of the raw-data schema originally submitted during deploy, use it instead
        if isinstance(io_hint, dict):
            # consider that submitted schema could already have contained 'content[...]' definitions
            # remove them in this case since they should have already been processed during first conversion/merge
            io_hint = oas_resolve_remote(io_hint)
            json_objects = []
            if "oneOf" in io_hint or "anyOf" in io_hint:
                for item in io_hint.get("oneOf", io_hint.get("anyOf", [])):
                    if item.get("type") == "object" or "allOf" in item:
                        json_objects.append(item)
            elif "allOf" in io_hint:
                json_objects = [io_hint]
            elif io_hint.get("type") == "object":
                json_objects = [io_hint]
        item_types.extend(json_objects)
    else:
        # complex by reference or encoded data
        item_types = [{"type": "string", "format": "binary"}]
    item_schema = {"oneOf": item_types} if len(item_types) > 1 else item_types[0]
    return item_schema


def json2oas_io_bbox(io_info, io_hint=null):
    # type: (JSON_IO_Type, Union[OpenAPISchema, Type[null]]) -> OpenAPISchema
    """
    Convert a single-dimension bounding box :term:`JSON` I/O definition into corresponding :term:`OpenAPI` schema.

    .. seealso::
        https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/d5257/core/openapi/schemas/bbox.yaml
    """
    # don't add the 'enum' of CRS as defined in the reference schema since this is auto-generated
    # and could mismatch the intended CRS by the user, unless available explicitly
    crs_schema = {"type": "string", "format": "uri", "default": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}
    supported_crs = get_field(io_info, "supported_crs", search_variations=True)
    if isinstance(supported_crs, list) and all(isinstance(crs, str) for crs in supported_crs):
        crs_schema["enum"] = supported_crs
    item_schema = {
        "type": "object",
        "format": "ogc-bbox",
        "required": ["bbox"],
        "properties": {
            "crs": crs_schema,
            "bbox": {
                "type": PACKAGE_ARRAY_BASE,
                "items": "number",
                "oneOf": [
                    {"minItems": 4, "maxItems": 4},
                    {"minItems": 6, "maxItems": 6},
                ]
            },
        }
    }  # type: OpenAPISchemaObject
    if isinstance(io_hint, dict):
        if "$ref" in io_hint:
            item_schema["$id"] = io_hint["$ref"]
        elif "allOf" in io_hint:
            for item in io_hint["allOf"]:
                if "$ref" in item:
                    item_schema["$id"] = item["$ref"]
                    break
    return item_schema


def json2oas_io_literal_data_type(io_type):
    # type: (str) -> JSON
    """
    Converts various literal data types into corresponding :term:`OpenAPI` fields.

    .. seealso::
        - https://spec.openapis.org/oas/v3.1.0#data-types
        - https://swagger.io/specification/#data-types
    """
    data_info = {"type": "string"}
    if io_type in OAS_LITERAL_FLOAT_FORMATS | WPS_LITERAL_DATA_FLOAT:
        data_info["type"] = "number"
        data_info["format"] = io_type
    if io_type in OAS_LITERAL_INTEGER_FORMATS | WPS_LITERAL_DATA_INTEGER:
        data_info["type"] = "integer"
        if io_type != "integer":
            data_info["format"] = io_type
    if io_type in WPS_LITERAL_DATA_BOOLEAN:
        data_info["type"] = "boolean"
    if io_type in OAS_LITERAL_STRING_FORMATS | WPS_LITERAL_DATA_STRING:
        data_info["type"] = "string"
        if "time" in io_type.lower():
            data_info["format"] = "date-time"
        elif "date" in io_type.lower():
            data_info["format"] = "date"
        elif io_type != "string":
            data_info["format"] = io_type
    if io_type in OAS_LITERAL_BINARY_FORMATS:
        data_info["type"] = "string"
        data_info["format"] = "binary"
    return data_info


def json2oas_io_allowed_values(io_base, io_allowed):
    # type: (JSON, JSON) -> List[JSON]
    """
    Converts literal data allowed values :term:`JSON` definitions ino :term:`OpenAPI` equivalent variations.

    :param io_base: Base value definitions that can be shared across variations (e.g.: default values).
    :param io_allowed: Allowed values definitions (enum, ranges) extracted from :term:`JSON` literal data domains.
    :return: List of converted :term:`OpenAPI` definitions applicable to represent the allowed values.
    """

    item_variation = []
    if isinstance(io_allowed, dict):
        # anyValue
        # nothing to do since regardless of true/false, nothing can be applied as OpenAPI schema definition
        return [io_base]
    if isinstance(io_allowed, list) and all(isinstance(val_def, (int, float, str)) for val_def in io_allowed):
        # allowed values
        # need to split the different types if a mix is used (e.g.: 1, 2, "A", "B")
        data_val_types = {
            "string": [val for val in io_allowed if isinstance(val, str)],
            "number": [val for val in io_allowed if isinstance(val, (float, int))],
        }
        for _typ, vals in data_val_types.items():
            if vals:
                data_enum = {"type": _typ, "enum": vals}
                data_enum.update(io_base)
                if _typ == "number" and all(val for val in io_allowed if isinstance(val, int)):
                    data_enum.update(json2oas_io_literal_data_type("integer"))
                elif _typ == "number" and all(val for val in io_allowed if isinstance(val, float)):
                    data_enum.update(json2oas_io_literal_data_type("double"))
                item_variation.append(data_enum)
        return item_variation
    if isinstance(io_allowed, list) and all(isinstance(val_def, dict) for val_def in io_allowed):
        # allowed ranges
        for val in io_allowed:
            min_val = get_field(val, "range_minimum", search_variations=True, default=None)
            max_val = get_field(val, "range_maximum", search_variations=True, default=None)
            spacing = get_field(val, "range_spacing", search_variations=True, default=None)
            closure = get_field(val, "range_closure", search_variations=True, default=RANGECLOSURETYPE.CLOSED)
            data_range = {}
            data_range.update(io_base)
            if min_val is not None:
                data_range["minimum"] = min_val
            if max_val is not None:
                data_range["maximum"] = max_val
            if spacing is not None:
                data_range["multipleOf"] = spacing
            if closure == RANGECLOSURETYPE.OPEN:  # ]min, max[
                data_range.update({"exclusiveMinimum": True, "exclusiveMaximum": True})
            elif closure == RANGECLOSURETYPE.OPENCLOSED:  # ]min, max]
                data_range.update({"exclusiveMinimum": True})
            elif closure == RANGECLOSURETYPE.CLOSEDOPEN:  # [min, max[
                data_range.update({"exclusiveMaximum": True})
            item_variation.append(data_range)
        return item_variation
    return [io_base]


def json2oas_io_literal(io_info, io_hint=null):
    # type: (JSON_IO_Type, Union[OpenAPISchema, Type[null]]) -> OpenAPISchema
    """
    Convert a single-dimension literal value :term:`JSON` I/O definition into corresponding :term:`OpenAPI` schema.
    """
    item_variation = []
    domains = get_field(io_info, "literal_data_domains", search_variations=True, default=[])
    for data_info in domains:
        data_fmt = {}
        data_type = get_field(data_info, "type", search_variations=True)
        if isinstance(data_type, dict) and "name" in data_type:
            data_type = data_type["name"]
            data_href = get_field(data_type, "href", search_variations=True)
        else:
            data_type = None
            data_href = None
        if io_hint:
            # if original data type is available in hint OAS I/O definition, use it since it should be more specific
            # because of conversions between type/format of different scopes, some types could be less precise
            # (eg: 'double' transformed to 'float')
            data_hint = oas2json_io(io_hint)
            data_hint = (data_hint or {}).get("data_type")
            # ignore 'string' type which is the fallback type to avoid undoing proper detection
            data_hint = null if data_hint == "string" and data_type is not null else data_hint
            data_type = data_hint or data_type
            data_fmt = get_field(io_hint, "format", search_variations=False)
            data_fmt = {"format": data_fmt} if data_fmt is not null else {}
        if not data_type:
            continue
        data_var = json2oas_io_literal_data_type(data_type)
        data_var.update(data_fmt)
        if data_href:
            data_var["contentSchema"] = data_href
        data_default = get_field(io_info, "default", search_variations=True)
        if data_default is not null:
            data_var["default"] = data_default
        data_def = get_field(data_info, "valueDefinition")
        # extend definition with relevant value definitions
        # basic definition if no special enum/range handling was applied
        data_var = json2oas_io_allowed_values(data_var, data_def)
        item_variation.extend(data_var)

    if not domains:
        return {"type": "string"}
    if len(item_variation) > 1:
        item_schema = {"oneOf": item_variation}
    else:
        item_schema = item_variation[0]
    if isinstance(io_hint, dict):
        if "$ref" in io_hint:
            item_schema["$id"] = io_hint["$ref"]
    return item_schema


def json2oas_io(io_info, io_hint=null):
    # type: (JSON_IO_Type, Union[OpenAPISchema, Type[null]]) -> OpenAPISchema
    """
    Converts definitions from a :term:`JSON` :term:`Process` I/O definition into corresponding :term:`OpenAPI` schema.

    :param io_info: :term:`WPS` I/O definition to generate a corresponding :term:`OpenAPI` schema.
    :param io_hint: Reference :term:`OpenAPI` definition that can improve more explicit object definitions.
    """
    io_type = get_field(io_info, "type")
    if io_type == WPS_COMPLEX:
        item_schema = json2oas_io_complex(io_info, io_hint)
    elif io_type == WPS_BOUNDINGBOX:
        item_schema = json2oas_io_bbox(io_info, io_hint)
    else:
        item_schema = json2oas_io_literal(io_info, io_hint)

    min_occurs = get_field(io_info, "min_occurs", search_variations=True)
    max_occurs = get_field(io_info, "max_occurs", search_variations=True)
    # backward support of values as strings
    if isinstance(min_occurs, str) and str.isnumeric(min_occurs):
        min_occurs = int(min_occurs)
    if isinstance(max_occurs, str) and str.isnumeric(max_occurs):
        max_occurs = int(max_occurs)
    # resolve a single/multi/both value cardinality
    # because specified single-value/objects *MUST* be provided, optional can be represented only by zero-length array
    if isinstance(min_occurs, int) and (min_occurs == 0 or min_occurs > 1):
        io_schema = {
            "type": PACKAGE_ARRAY_BASE,
            "items": item_schema,
            "minItems": min_occurs,
        }
        if isinstance(max_occurs, int):
            io_schema["maxItems"] = max_occurs
    elif max_occurs == 1 or max_occurs is null:  # assume unspecified is default=1
        io_schema = item_schema
    else:
        array_schema = {"type": PACKAGE_ARRAY_BASE, "items": item_schema}
        if isinstance(min_occurs, int):
            array_schema["minItems"] = min_occurs
        if isinstance(max_occurs, int):
            array_schema["maxItems"] = max_occurs
        # if item schema was itself 'oneOf', combine them to make it easier to read
        if len(item_schema) == 1 and "oneOf" in item_schema:
            io_schema = deepcopy(item_schema)  # avoid recursion by dict references
            io_schema["oneOf"].append(array_schema)  # noqa
        # otherwise simply stack (still valid, just slightly more confusing to read)
        else:
            io_schema = {
                "oneOf": [
                    item_schema,
                    array_schema,
                ]
            }
    return io_schema


def oas2json_io_literal(io_info):
    # type: (OpenAPISchemaProperty) -> Union[JSON_IO_TypedInfo, Type[null]]
    """
    Converts a literal value I/O definition by :term:`OpenAPI` schema into the equivalent :term:`JSON` representation.

    :param io_info: :term:`OpenAPI` schema of the I/O.
    :return: Converted :term:`JSON` I/O definition, or :data:`null` if definition could not be resolved.
    """
    io_type = get_field(io_info, "type", search_variations=False)
    io_fmt = get_field(io_info, "format", search_variations=False)
    if io_fmt is not null:
        if io_type in OAS_LITERAL_NUMERIC:
            if io_fmt in OAS_LITERAL_FLOAT_FORMATS:
                io_type = "double"
            elif io_fmt in OAS_LITERAL_INTEGER_FORMATS:
                io_type = "integer"
        elif io_fmt in OAS_LITERAL_STRING_FORMATS:
            io_type = io_fmt
    data_type = any2wps_literal_datatype(io_type, False)
    io_json = {"type": WPS_LITERAL, "data_type": data_type}
    io_enum = get_field(io_info, "enum", search_variations=False)
    min_val = get_field(io_info, "minimum", search_variations=False)
    max_val = get_field(io_info, "maximum", search_variations=False)
    min_exc = get_field(io_info, "exclusiveMinimum", search_variations=False, default=False)
    max_exc = get_field(io_info, "exclusiveMaximum", search_variations=False, default=False)
    mult_of = get_field(io_info, "multipleOf", search_variations=False, default=None)
    io_allow = null
    if io_enum is not null:
        io_allow = {"allowed_values": io_enum}
    elif min_val is not null or max_val is not null:
        if min_exc and max_exc:
            closure = RANGECLOSURETYPE.OPEN
        elif min_exc:
            closure = RANGECLOSURETYPE.OPENCLOSED
        elif max_exc:
            closure = RANGECLOSURETYPE.CLOSEDOPEN
        else:
            closure = RANGECLOSURETYPE.CLOSED
        io_allow = {
            "allowed_values": [{
                "minimum": min_val,
                "maximum": max_val,
                "spacing": mult_of,
                "closure": closure
            }]
        }
    if io_allow is not null:
        io_allow.update(io_info)  # noqa
        io_allow["data_type"] = data_type
        domains = any2json_literal_data_domains(io_allow)
        io_json["allowed_values"] = io_allow["allowed_values"]  # propagate to help CWL resolution of enum later on
        io_json["literalDataDomains"] = domains
    return io_json


def oas2json_io_array(io_info):
    # type: (OpenAPISchemaArray) -> Union[JSON_IO_TypedInfo, Type[null]]
    """
    Converts an array I/O definition by :term:`OpenAPI` schema into the equivalent :term:`JSON` representation.

    :param io_info: :term:`OpenAPI` schema of the I/O.
    :return: Converted :term:`JSON` I/O definition, or :data:`null` if definition could not be resolved.
    """
    io_items = get_field(io_info, "items", search_variations=False)
    io_json = oas2json_io(io_items)
    min_items = get_field(io_info, "minItems")
    max_items = get_field(io_info, "maxItems")
    if isinstance(min_items, int):
        io_json["minOccurs"] = min_items
    if isinstance(max_items, int):
        io_json["maxOccurs"] = max_items
    return io_json


def oas2json_io_object(io_info, io_href=null):
    # type: (OpenAPISchemaObject, str) -> Union[JSON_IO_TypedInfo, Type[null]]
    """
    Converts an object I/O definition by :term:`OpenAPI` schema into the equivalent :term:`JSON` representation.

    An explicit :term:`OpenAPI` schema with ``object`` type can represent any of the following I/O:

      - Bounding Box as GeoJSON feature
      - Complex JSON structure

    .. seealso::
        :func:`oas2json_io_file` is used for file reference to be parsed as other Complex I/O.

    :param io_info: :term:`OpenAPI` schema of the I/O.
    :param io_href: Alternate schema reference for the type.
    :return: Converted :term:`JSON` I/O definition, or :data:`null` if definition could not be resolved.
    """
    io_fmt = get_field(io_info, "format", search_variations=False)
    io_props = get_field(io_info, "properties", search_variations=False) or {}
    if ("bbox" in io_props and "crs" in io_props) or io_fmt == "ogc-bbox":
        io_json = {"type": WPS_BOUNDINGBOX}
        io_crs = get_field(io_props, "crs", search_variations=False)
        if isinstance(io_crs, dict):
            io_crs_allow = get_field(io_crs, "enum", search_variations=False)
            if isinstance(io_crs_allow, list) and all(isinstance(crs, str) for crs in io_crs_allow):
                io_json["supported_crs"] = io_crs_allow
        if io_href is not null:
            io_meta = {"href": io_href, "role": SchemaRole.JSON_SCHEMA, "title": "Schema"}
            io_ext = os.path.splitext(io_href)[-1]
            io_ctype = io_ext and get_content_type(io_ext)
            if io_ctype:
                io_meta["type"] = io_ctype
            io_json["metadata"] = [io_meta]
    else:
        # note:
        #  In this case we are dealing only with literal OAS objects, therefore JSON content.
        #  Complex I/O provided by file reference are done by other methods.
        obj_fmt = {"mime_type": ContentType.APP_JSON}
        if io_href is not null:
            obj_fmt["schema"] = io_href
        io_json = {"type": WPS_COMPLEX, "supported_formats": [obj_fmt]}
    return io_json


def oas2json_io_keyword(io_info):
    # type: (OpenAPISchemaKeyword) -> Union[JSON_IO_TypedInfo, Type[null]]
    """
    Converts a keyword I/O definition by :term:`OpenAPI` schema into the equivalent :term:`JSON` representation.

    Keywords are defined as a list of combinations of :term:`OpenAPI` schema representing how to combine them
    according to the keyword value, being one of :data:`OAS_KEYWORD_TYPES`.

    :param io_info: :term:`OpenAPI` schema of the I/O.
    :return: Converted :term:`JSON` I/O definition, or :data:`null` if definition could not be resolved.
    """
    # if it cannot be resolved, must be too ambiguous, so assume complex data dump
    io_json = {"type": WPS_COMPLEX, "supported_formats": [{"mime_type": ContentType.APP_JSON}]}
    kw_key_val = {key: val for key, val in io_info.items() if key in OAS_KEYWORD_TYPES}
    if len(kw_key_val) != 1:
        return null
    keyword = list(kw_key_val)[0]
    keyword_schemas = io_info[keyword]
    if keyword == "not":
        keyword_objects = [oas2json_io(keyword_schemas)]  # noqa
    elif keyword == "allOf":
        merged_schema = {}  # type: OpenAPISchema
        for schema in keyword_schemas:
            merged_schema.update(schema)
        keyword_objects = [oas2json_io(merged_schema)]
    else:
        keyword_objects = [oas2json_io(schema) for schema in keyword_schemas]
    keyword_types = [get_field(obj, "type", search_variations=False) for obj in keyword_objects]
    keyword_types = set(filter(lambda obj: isinstance(obj, str), keyword_types))
    keyword_dtypes = [get_field(obj, "data_type", search_variations=False) for obj in keyword_objects]
    keyword_dtypes = set(filter(lambda obj: isinstance(obj, str), keyword_dtypes))
    if keyword_types:
        # literals are all or nothing, but can allow different 'data format'
        # any mixed type with literal must be elevated to complex since there is no way to handle both as literals
        if all(typ == WPS_LITERAL for typ in keyword_types):
            io_json = {"type": WPS_LITERAL}
            if keyword_dtypes and len(keyword_dtypes) == 1:
                io_json["data_type"] = list(keyword_dtypes)[0]
            elif all(dtype in OAS_LITERAL_FLOAT_FORMATS for dtype in keyword_dtypes):
                io_json["data_type"] = "double"
            elif all(dtype in OAS_LITERAL_INTEGER_FORMATS for dtype in keyword_dtypes):
                io_json["data_type"] = "integer"
            # acceptable to use 'numeric' for either integers or floats
            elif all(dtype in OAS_LITERAL_NUMERIC | OAS_LITERAL_NUMERIC_FORMATS for dtype in keyword_dtypes):
                io_json["data_type"] = "numeric"
            else:
                io_json["data_type"] = "string"
        # since some variations can be an external reference or a partial definition,
        # anything matching a bbox marks the whole definition as one, falling back to complex otherwise
        elif any(typ == WPS_BOUNDINGBOX for typ in keyword_types):
            for obj_json in keyword_objects:
                io_type = get_field(obj_json, "type")
                if io_type == WPS_BOUNDINGBOX:
                    io_json = obj_json
                    break
        elif all(typ == WPS_COMPLEX for typ in keyword_types):
            # improve definition of complex type of multiple distinct supported formats
            formats = []
            for obj_json in keyword_objects:
                obj_fmt = get_field(obj_json, "supported_formats", default=[])
                formats.extend([fmt for fmt in obj_fmt if fmt not in formats])
            io_json = {"type": WPS_COMPLEX, "supported_formats": formats}
    return io_json


def oas2json_io_file(io_info, io_href=null):
    # type: (OpenAPISchemaObject, str) -> JSON_IO_TypedInfo
    """
    Converts a file reference I/O definition by :term:`OpenAPI` schema into the equivalent :term:`JSON` representation.

    :param io_info: :term:`OpenAPI` schema of the I/O.
    :param io_href: Alternate schema reference for the type.
    :return: Converted :term:`JSON` I/O definition, or :data:`null` if definition could not be resolved.
    """
    io_json = {"type": WPS_COMPLEX}
    io_ctype = get_field(io_info, "contentMediaType", search_variations=False)
    io_encode = get_field(io_info, "contentEncoding", search_variations=False)
    io_schema = get_field(io_info, "contentSchema", search_variations=False, default=io_href)
    io_format = {}
    if isinstance(io_encode, str):
        io_format["encoding"] = io_encode
    if isinstance(io_schema, str):
        io_format["schema"] = io_schema
    if isinstance(io_ctype, str):
        io_format["mime_type"] = io_ctype
        # other fields don't matter if required media-type is omitted
        io_json["supported_formats"] = [io_format]
    return io_json


def oas2json_io_measure(io_info):
    # type: (OpenAPISchemaObject) -> Union[JSON_IO_TypedInfo, Type[null]]
    """
    Convert a unit of measure (``UoM``) I/O definition by :term:`OpenAPI` schema into :term:`JSON` representation.

    This conversion projects an object (normally complex type) into a literal type, considering that other provided
    parameters are all metadata information.

    :param io_info: Potential :term:`OpenAPI` schema of an UoM I/O.
    :return: Converted I/O if it matched the UoM format, or null otherwise.
    """
    io_type = get_field(io_info, "type", search_variations=False)
    if io_type == "object":
        io_prop = get_field(io_info, "properties", search_variations=False)
        if isinstance(io_prop, dict):
            io_uom = get_field(io_prop, "uom", search_variations=True)
            io_val = get_field(io_prop, "measure", search_variations=True)
            io_uom_ref = get_field(io_prop, "reference", search_variations=False, default={})
            if isinstance(io_uom, dict) and isinstance(io_val, dict):
                io_key = get_field(io_prop, "measure", search_variations=True, key=True)
                io_req = get_field(io_info, "required", search_variations=False)
                if not isinstance(io_req, list) or io_key not in io_req:
                    io_err = repr_json(io_info, force_string=True, indent=None)
                    raise ValueError(
                        f"Detected UoM I/O schema but missing 'required' field entry for the measure value: {io_err}"
                    )
                # detect if any number, int/float explicit, or any min/max constraints
                io_json = oas2json_io_literal(io_val)
                uom_enum = io_uom.get("enum")
                uom_const = io_uom.get("const")
                if isinstance(uom_enum, list) or isinstance(uom_const, str):
                    # although WPS can support many UoM, OGC-API schema representation can use oneOf to refer
                    # to multiple variations of UoM with their respective combinations of unit/references
                    # they can also use a single UoM definition with a list of units
                    uom_enum = uom_enum or ([uom_const] if uom_const else [])
                    if len(uom_enum) < 1:
                        raise ValueError(
                            "Detected UoM I/O schema with invalid units enum/const. "
                            f"At least 1 unit must be specified. Got: {io_uom}."
                        )
                    ref_enum = io_uom_ref.get("enum") or ([""] * len(uom_enum))
                    ref_const = io_uom_ref.get("const") or []
                    ref_enum = ref_enum or ([ref_const] if ref_const else [])
                    if isinstance(ref_enum, list) and len(ref_enum) != len(uom_enum):
                        raise ValueError(
                            "Detected UoM I/O schema with invalid unit/reference enums/const."
                            "When UoM reference are provided, they must be of equal quantity with units. "
                            f"Got: (units: {io_uom}, references: {io_uom_ref})."
                        )
                    io_json["uoms"] = [uom2json(unit, ref) for unit, ref in zip(uom_enum, ref_enum)]
                io_uom_default = io_uom.get("default")
                io_uom_ref_default = io_uom_ref.get("default")
                if isinstance(io_uom_default, str) and io_uom_default:
                    io_json["uom"] = uom2json(io_uom_default, io_uom_ref_default)
                return io_json
    return null


def oas2json_io(io_info):
    # type: (OpenAPISchema) -> Union[JSON_IO_TypedInfo, Type[null]]
    """
    Converts an :term:`I/O` definition by :term:`OpenAPI` schema into the equivalent :term:`JSON` representation.

    :param io_info: :term:`OpenAPI` schema of the :term:`I/O`.
    :return: Converted :term:`JSON` :term:`I/O` definition, or :data:`null` if definition could not be resolved.
    """
    io_href = get_field(io_info, "$ref")
    io_info = oas_resolve_remote(io_info)
    io_type = get_field(io_info, "type", search_variations=False)
    io_json = null

    # File I/O can be defined with raw-data string type, but must be associated with content information to
    # help distinguish them from plain string value. Try to detect this to avoid literal data interpretation.
    # NOTE:
    #   Don't include "{type: string, format: uri}" as complex type.
    #   Leave this as the method to indicate that a process uses a plain URL reference that must not be fetched.
    if io_type == "string":
        io_ctype = get_field(io_info, "contentMediaType", search_variations=False)
        io_encode = get_field(io_info, "contentEncoding", search_variations=False)
        # io_schema = get_field(io_info, "contentSchema", search_variations=False)  # ignore since possible in literal
        if any(io_field is not null for io_field in [io_ctype, io_encode]):
            io_type = WPS_COMPLEX  # set value to avoid null return below, but no parsing after since not OAS type
            io_json = oas2json_io_file(io_info, io_href)

    else:
        # known special case of extended OAS object representing a literal (unit of measure)
        io_json = oas2json_io_measure(io_info)
        if io_json:
            io_type = WPS_LITERAL  # set value to avoid null return below, but no parsing after since not OAS type

    if io_type is not null:
        if io_type in OAS_LITERAL_TYPES:
            io_json = oas2json_io_literal(io_info)
        elif io_type in OAS_COMPLEX_TYPES:
            io_json = oas2json_io_object(io_info, io_href)
        elif io_type in OAS_ARRAY_TYPES:
            io_json = oas2json_io_array(io_info)
    elif any(key in OAS_KEYWORD_TYPES for key in io_info):
        io_json = oas2json_io_keyword(io_info)
        # in case this keyword was a large combination of multiple complex JSON variants with a reference schema
        # forward the reference in the supported type since this is a special case that we extend with contentSchema
        io_type = get_field(io_json, "type", default="keyword")  # ensure not null value to skip return null
        if io_type == WPS_COMPLEX:
            io_formats = get_field(io_json, "supported_formats", default=[])
            if "$id" in io_info and len(io_formats) == 1:
                io_ctype = get_field(io_formats[0], "mime_type", search_variations=True)
                if io_ctype and ContentType.APP_JSON in io_ctype:
                    io_formats[0]["schema"] = io_info["$id"]
    if io_type is null or io_json is null:
        LOGGER.debug("Unknown OpenAPI to JSON I/O resolution for schema:\n%s", repr_json(io_info))
        return null

    # default literal value can help resolve as last resort if specific type cannot be inferred
    io_default = get_field(io_info, "default", search_variations=False)
    if io_default is not null:
        io_json["default"] = io_default
    return io_json


def oas_resolve_remote(io_info):
    # type: (OpenAPISchema) -> OpenAPISchema
    """
    Perform remote :term:`OpenAPI` schema ``$ref`` resolution.

    Resolution is performed only sufficiently to provide enough context for following :term:`JSON` :term:`I/O`
    conversion. Remote references are not resolved further than required to speedup loading time and avoid recursive
    error on self-referring schema. Passed sufficient levels of schema definitions, the specific contents is not
    important nor needs to be resolved as there is they cannot be mapped to anything else than :data:`WPS_COMPLEX`
    :term:`I/O` type.

    :param io_info: :term:`I/O` :term:`OpenAPI` schema to attempt resolution as applicable.
    :return: Resolved :term:`I/O` schema or directly the provided schema returned unmodified if no references need resolution.
    """
    # retrieve external schema reference (possibly nested)
    io_href = get_field(io_info, "$ref", search_variations=False, pop_found=True)
    if isinstance(io_href, str):
        # first encountered reference should be full-uri to allow us knowing where to look for
        if not any(io_href.startswith(f"{scheme}://") for scheme in ["http", "https", "s3"]):
            raise ValueError(f"External OpenAPI schema reference [{io_href}] must be absolue.")
        if not any(io_href.endswith(extension) for extension in [".yaml", ".yml", ".json"]):
            raise ValueError(f"External OpenAPI schema reference [{io_href}] must be formatted as JSON or YAML.")
        try:
            # use resolver which will handle all intricacies of loading remote schema into a local dict definition
            # this way, no need to handle other external, relative, absolute, etc. nested '$ref' locations
            # note: '$ref' are still loaded on the first level only to avoid recursive schemas breaking on load
            io_base = f"{io_href.rsplit('/', 1)[0]}/"
            resolver = SchemaRefResolver(base_uri=io_base, referrer=io_info)
            io_resolved = resolver.resolve_from_url(io_href)
            # In case the input schema was the result of a 'allOf' merge,
            # update with other fields that forms a whole object
            # This way, there is more chance we can detect a combined form that matches a known conversion type.
            io_info.update(io_resolved)
            io_info["$id"] = io_href
            # If the remote $ref schema itself was a combination of $ref schemas (e.g.: it contained 'oneOf').
            # Then update the first level of references that we can potentially work with to resolve conversion type.
            # No need to resolve more since this is guaranteed to be 'complex' type.
            # We must use the resolver right away in case the remote $ref are relative to the same root $ref.
            for keyword in OAS_KEYWORD_TYPES:  # type: Literal["oneOf", "anyOf", "allOf", "not"]
                if keyword in io_info:
                    if isinstance(io_info[keyword], list):  # all keywords except 'not'
                        for i, schema in enumerate(list(io_info[keyword])):
                            if "$ref" in schema:
                                ref_id, schema = resolver.resolve(schema["$ref"])
                                schema["$id"] = ref_id
                                io_info[keyword][i] = schema  # noqa
                    elif "$ref" in io_info[keyword]:  # only 'not' keyword
                        io_keyword = io_info[keyword]  # type: OpenAPISchemaReference  # noqa
                        ref_schema = io_keyword["$ref"]
                        ref_id, schema = resolver.resolve(ref_schema)
                        schema["$id"] = ref_id
                        io_info[keyword] = schema
        except Exception as exc:
            raise ValueError(f"External OpenAPI schema reference [{io_href}] could not be loaded.") from exc
    return io_info


def json2wps_datatype(io_info):
    # type: (JSON_IO_Type) -> str
    """
    Converts a JSON input definition into the corresponding :mod:`pywps` parameters.

    Guesses the literal data-type from :term:`JSON` :term:`I/O` information in order to allow creation of the
    corresponding :term:`WPS` :term:`I/O`. Defaults to ``string`` if no suitable guess can be accomplished.
    """
    io_type = get_field(io_info, "type", search_variations=False, pop_found=True)
    if str(io_type).lower() == WPS_LITERAL:
        io_type = null
    io_guesses = [
        (io_type, False),
        (get_field(io_info, "type", search_variations=True), False),
        (get_field(io_info, "default", search_variations=True), True),
        (get_field(io_info, "allowed_values", search_variations=True), True),
        (get_field(io_info, "supported_values", search_variations=True), True)
    ]
    for io_guess, is_value in io_guesses:
        if io_type:
            break
        if isinstance(io_guess, list) and len(io_guess):
            io_guess = io_guess[0]
        io_type = any2wps_literal_datatype(io_guess, is_value)
    if not isinstance(io_type, str):
        LOGGER.warning("Failed literal data-type guess, using default 'string' for I/O [%s].",
                       get_field(io_info, "identifier", search_variations=True))
        return "string"
    return io_type


def json2wps_field(field_info, field_category):
    # type: (JSON, str) -> Any
    """
    Converts an :term:`I/O` field from :term:`JSON` literal, list, or dictionary to corresponding :term:`WPS` types.

    :param field_info: literal data or information container describing the type to be generated.
    :param field_category: one of :data:`WPS_FIELD_MAPPING` keys to indicate how to parse ``field_info``.
    """
    if field_category == "allowed_values":
        return json2wps_allowed_values({"allowed_values": field_info})
    elif field_category == "supported_formats":
        fmt = None
        field_info = field_info.copy()
        field_info.pop("$schema", None)
        # pywps doesn't allow 'default' field in init, remove if found, but preserve it indirectly
        default = get_field(field_info, "default", search_variations=False, pop_found=True)
        if isinstance(field_info, dict):
            fmt = Format(**field_info)
        if isinstance(field_info, str):
            fmt = Format(field_info)
        if fmt:
            # consider any explicit 'default' format specification to allow resolution against many supported formats
            # set a temporary additional attribute in PyWPS Format object that can be found later
            if isinstance(default, bool):
                set_field(fmt, "default", default)
            return fmt
    elif field_category == "metadata":
        if isinstance(field_info, WPS_Metadata):
            return field_info
        if isinstance(field_info, dict):
            meta = metadata2json(field_info, force=True)
            rel = meta.pop("rel", None)
            ctype = meta.pop("type", None)
            meta = WPS_Metadata(**meta)
            if isinstance(rel, str):
                set_field(meta, "rel", rel)
            if isinstance(ctype, str):
                set_field(meta, "type", ctype)
            return meta
        if isinstance(field_info, str):
            return WPS_Metadata(field_info)
    elif field_category == "keywords" and isinstance(field_info, list):
        return field_info
    elif field_category == "uom" and isinstance(field_info, str):
        return
    elif field_category in ["identifier", "title", "abstract"] and isinstance(field_info, str):
        return field_info
    LOGGER.warning("Field of type '%s' not handled as known WPS field.", field_category)
    return None


def json2wps_allowed_values(io_info):
    # type: (JSON_IO_Type) -> Union[Type[null], List[AllowedValue]]
    """
    Obtains the allowed values constrains for the literal data type from a :term:`JSON` :term:`I/O` definition.

    Converts the ``literalDataDomains`` definition into ``allowed_values`` understood by :mod:`pywps`.
    Handles explicit ``allowed_values`` if available and not previously defined by ``literalDataDomains``.

    .. seealso::
        Function :func:`any2json_literal_data_domains` defines generated ``literalDataDomains`` JSON definition.
    """
    domains = get_field(io_info, "literal_data_domains", search_variations=True)
    allowed = get_field(io_info, "allowed_values", search_variations=True)
    if not domains and isinstance(allowed, list):
        if all(isinstance(value, AllowedValue) for value in allowed):
            return allowed
        if all(isinstance(value, (float, int, str)) for value in allowed):
            return [AllowedValue(value=value) for value in allowed]
        if all(isinstance(value, dict) for value in allowed):
            allowed_values = []
            for value in allowed:
                min_val = get_field(value, "range_minimum", search_variations=True, default=None)
                max_val = get_field(value, "range_maximum", search_variations=True, default=None)
                spacing = get_field(value, "range_spacing", search_variations=True, default=None)
                closure = get_field(value, "range_closure", search_variations=True, default=RANGECLOSURETYPE.CLOSED)
                literal = get_field(value, "value", search_variations=False, default=None)
                if min_val or max_val or spacing:
                    allowed_values.append(AllowedValue(ALLOWEDVALUETYPE.RANGE,
                                                       minval=min_val, maxval=max_val,
                                                       spacing=spacing, range_closure=closure))
                elif literal:
                    allowed_values.append(AllowedValue(ALLOWEDVALUETYPE.VALUE, value=literal))
                # literalDataDomains could be 'anyValue', which is to be ignored here
            return allowed_values
        LOGGER.debug("Cannot parse literal I/O AllowedValues: %s", allowed)
        raise ValueError(f"Unknown parsing of 'AllowedValues' for value: {allowed!s}")
    if domains:
        for domain in domains:
            values = domain.get("valueDefinition")
            if values:
                allowed = json2wps_allowed_values({"allowed_values": values})
            # stop on first because undefined how to combine multiple
            # no multiple definitions by 'any2json_literal_data_domains' regardless, and not directly handled by pywps
            if allowed:
                return allowed
    return null


def json2wps_io(io_info, io_select):  # pylint: disable=R1260
    # type: (JSON_IO_Type, IO_Select_Type) -> WPS_IO_Type
    """
    Converts an :term:`I/O` from a :term:`JSON` dict to :mod:`pywps` types.

    :param io_info: :term:`I/O` in :term:`JSON` dict format.
    :param io_select: :data:`IO_INPUT` or :data:`IO_OUTPUT` to specify desired :term:`WPS` type conversion.
    :return: corresponding :term:`I/O` in :term:`WPS` format.
    """

    io_info["identifier"] = get_field(io_info, "identifier", search_variations=True, pop_found=True)

    rename = {
        "formats": "supported_formats",
        "minOccurs": "min_occurs",
        "maxOccurs": "max_occurs",
        "dataType": "data_type",
        "defaultValue": "default",
        "crs": "default",
        "supportedValues": "supported_values",
    }
    remove = [
        "id",
        "workdir",
        "any_value",
        "data_format",
        "data",
        "file",
        "mimetype",
        "mediaType",
        "encoding",
        "schema",
        "asreference",
        "additionalParameters",
        "ll",
        "ur",
        "bbox",
    ]
    replace_values = {"unbounded": PACKAGE_ARRAY_MAX_SIZE}

    transform_json(io_info, rename=rename, remove=remove, replace_values=replace_values)

    # convert allowed value objects
    values = json2wps_allowed_values(io_info)
    if values is not null:
        if isinstance(values, list) and len(values) > 0:
            io_info["allowed_values"] = values
        else:
            io_info["allowed_values"] = AnyValue  # noqa

    # convert supported format objects
    formats = get_field(io_info, "supported_formats", search_variations=True, pop_found=True)
    if formats is not null:
        for fmt in formats:
            fmt["mime_type"] = get_field(fmt, "mime_type", search_variations=True, pop_found=True)
            fmt.pop("maximumMegabytes", None)
            # define the 'default' with 'data_format' to be used if explicitly specified from the payload
            if fmt.get("default", None) is True:
                if get_field(io_info, "data_format") != null:  # if set by previous 'fmt'
                    raise PackageTypeError("Cannot have multiple 'default' formats simultaneously.")
                # use 'data_format' instead of 'default' to avoid overwriting a potential 'default' value
                # field 'data_format' is mapped as 'default' format
                io_info["data_format"] = json2wps_field(fmt, "supported_formats")
        io_info["supported_formats"] = [json2wps_field(fmt, "supported_formats") for fmt in formats]

    # convert metadata objects
    metadata = get_field(io_info, "metadata", search_variations=True, pop_found=True)
    if metadata is not null:
        io_info["metadata"] = [json2wps_field(meta, "metadata") for meta in metadata]

    # convert literal fields specified as is
    for field in ["identifier", "title", "abstract", "keywords"]:
        value = get_field(io_info, field, search_variations=True, pop_found=True)
        if value is not null:
            io_info[field] = json2wps_field(value, field)

    # convert by type, add missing required arguments and
    # remove additional arguments according to each case
    io_type = io_info.pop("type", WPS_COMPLEX)  # only ComplexData doesn't have "type"
    # attempt to identify defined data-type directly in 'type' field instead of 'data_type'
    if io_type not in WPS_DATA_TYPES:
        io_type_guess = any2wps_literal_datatype(io_type, is_value=False)
        if io_type_guess is not null:
            io_type = WPS_LITERAL
            io_info["data_type"] = io_type_guess
    if io_type == WPS_LITERAL:
        data_type = json2wps_datatype(io_info)
        # pywps literals subset is more restrictive than all possible standard WPS
        # make use of some non-pywps compatible types since other valid WPS types are easier to match with OAS
        if data_type in WPS_LITERAL_DATA_TYPES and data_type not in LITERAL_DATA_TYPES:
            data_type = any2wps_literal_datatype(data_type, is_value=False, pywps=True)
        io_info["data_type"] = data_type
    if io_select == IO_INPUT:
        if ("max_occurs", "unbounded") in io_info.items():
            io_info["max_occurs"] = PACKAGE_ARRAY_MAX_SIZE
        if io_type in WPS_COMPLEX_TYPES:
            if "supported_formats" not in io_info:
                io_info["supported_formats"] = [DEFAULT_FORMAT]
            io_info.pop("data_type", None)
            io_info.pop("allowed_values", None)
            io_info.pop("supported_values", None)
            return ComplexInput(**io_info)
        if io_type == WPS_BOUNDINGBOX:
            io_info.pop("supported_formats", None)
            io_info["crss"] = get_field(io_info, "supported_crs", search_variations=True, pop_found=True, default=None)
            return BoundingBoxInput(**io_info)
        if io_type == WPS_LITERAL:
            io_info.pop("data_format", None)
            io_info.pop("supported_formats", None)
            allowed_values = json2wps_allowed_values(io_info)
            if allowed_values:
                io_info["allowed_values"] = allowed_values
            else:
                io_info.pop("allowed_values", None)
            io_info.pop("literalDataDomains", None)
            return LiteralInput(**io_info)
    elif io_select == IO_OUTPUT:
        # following not allowed for PyWPS instance creation,
        # but they are useful for other steps, so forward them afterward
        io_min = io_info.pop("min_occurs", null)
        io_max = io_info.pop("max_occurs", null)
        io_allow = io_info.pop("allowed_values", null)
        io_default = io_info.pop("default", null)
        io_wps = null
        if io_type in WPS_COMPLEX_TYPES:
            io_info.pop("supported_values", None)
            io_wps = ComplexOutput(**io_info)
        elif io_type == WPS_BOUNDINGBOX:
            io_info.pop("supported_formats", None)
            io_info["crss"] = get_field(io_info, "supported_crs", search_variations=True, pop_found=True, default=None)
            io_wps = BoundingBoxOutput(**io_info)
        elif io_type == WPS_LITERAL:
            io_info.pop("supported_formats", None)
            io_info.pop("literalDataDomains", None)
            io_wps = LiteralOutput(**io_info)
            set_field(io_wps, "allowed_values", io_allow)
        if io_wps:
            set_field(io_wps, "min_occurs", io_min)
            set_field(io_wps, "max_occurs", io_max)
            set_field(io_wps, "default", io_default)
            return io_wps
    raise PackageTypeError(f"Unknown conversion from dict to WPS type (type={io_type}, mode={io_select}).")


def wps2json_io(io_wps, forced_fields=False):
    # type: (WPS_IO_Type, bool) -> JSON_IO_Type
    """
    Converts a :mod:`pywps` :term:`I/O` into a :term:`JSON` dictionary with corresponding standard keys names.

    Employs standard key names as defined by :term:`WPS` 2.0.

    :param io_wps: Any :mod:`pywps` :term:`I/O` definition to be converted to :term:`JSON` representation.
    :param forced_fields:
        Request transfer of additional fields normally undefined for outputs if they are available by being forcefully
        inserted in the objects after their creation (i.e.: using :func:`set_field`). These fields can be useful for
        obtaining mandatory details for further processing operations (e.g.: :term:`OpenAPI` schema conversion).
    """

    if not isinstance(io_wps, BasicIO):
        raise PackageTypeError(f"Invalid type, expected 'BasicIO', got: [{type(io_wps)!r}] '{io_wps!r}'")
    if not hasattr(io_wps, "json"):
        raise PackageTypeError("Invalid type definition expected to have a 'json' property.")

    io_wps_json = io_wps.json

    # transfer additional fields normally undefined for outputs if available in original object (forcefully added)
    # when they are requested for further processing operations (eg: later OAS conversion)
    if forced_fields:
        for field in ["min_occurs", "max_occurs"]:
            if field not in io_wps_json:
                io_field = get_field(io_wps, field, search_variations=True)
                if io_field is not null:
                    io_wps_json[field] = io_field

    rename = {
        "identifier": "id",
        "abstract": "description",
        "supported_formats": "formats",
        "mime_type": "mediaType",
        "min_occurs": "minOccurs",
        "max_occurs": "maxOccurs",
    }
    replace_values = {
        PACKAGE_ARRAY_MAX_SIZE: "unbounded",
    }
    replace_func = {
        "maxOccurs": str,
        "minOccurs": str,
        "metadata": lambda metadata: [metadata2json(meta) for meta in metadata]
    }
    remove = [
        "data"  # string encoded value can cause confusion with default
    ]

    transform_json(io_wps_json, rename=rename, remove=remove, replace_values=replace_values, replace_func=replace_func)

    # in some cases (Complex I/O), 'as_reference=True' causes "type" to be overwritten, revert it back
    if "type" in io_wps_json and io_wps_json["type"] == WPS_REFERENCE:
        io_wps_json["type"] = WPS_COMPLEX

    # minimum requirement of 1 format object which defines mime-type
    if io_wps_json["type"] == WPS_COMPLEX:
        # FIXME: should we store 'None' in db instead of empty string when missing "encoding", "schema", etc. ?
        if "formats" not in io_wps_json or not len(io_wps_json["formats"]):
            io_wps_json["formats"] = [DEFAULT_FORMAT.json]
        for io_format in io_wps_json["formats"]:
            transform_json(io_format, rename=rename, replace_values=replace_values, replace_func=replace_func)

        # set 'default' format if it matches perfectly, or if only mime-type matches, and it is the only available one
        # (this avoids 'encoding' possibly not matching due to CWL not providing this information)
        io_default = get_field(io_wps_json, "default", search_variations=True)
        for io_format in io_wps_json["formats"]:
            io_format["default"] = (io_default != null and is_equal_formats(io_format, io_default))
        if len(io_wps_json["formats"]) == 1 and not io_wps_json["formats"][0]["default"]:
            io_single_fmt_mime_type = get_field(io_wps_json["formats"][0], "mime_type", search_variations=True)
            if io_default:
                io_default_mime_type = get_field(io_default, "mime_type", search_variations=True)
                io_fmt_is_default = (io_default_mime_type == io_single_fmt_mime_type)  # pylint: disable=C0325
                io_wps_json["formats"][0]["default"] = io_fmt_is_default
            elif DEFAULT_FORMAT.mime_type == io_single_fmt_mime_type:
                io_supported = get_field(io_wps, "supported_formats", default=[DEFAULT_FORMAT])
                io_missing = get_field(io_supported[0], DEFAULT_FORMAT_MISSING, default=False)
                io_wps_json["formats"][0]["default"] = io_missing

    elif io_wps_json["type"] == WPS_BOUNDINGBOX:
        pass  # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)

    else:  # literal
        # retrieve the default definition with original value type (default 'data' is string encoded with it)
        io_wps_default = get_field(io_wps, "default", search_variations=True)
        if io_wps_default not in [null, None]:
            io_wps_json["default"] = io_wps_default
        if "allowed_values" not in io_wps_json:
            io_field = get_field(io_wps, "allowed_values", search_variations=False)
            if io_field is not null:
                io_wps_json["allowed_values"] = [
                    io_allow.json if not isinstance(io_allow, dict) else io_allow
                    for io_allow in io_field
                ]
        domains = any2json_literal_data_domains(io_wps_json)
        if domains:
            io_wps_json["literalDataDomains"] = domains

    return io_wps_json


def wps2json_job_payload(wps_request, wps_process):
    # type: (WPSRequest, ProcessWPS) -> JSON
    """
    Converts the input and output values of a :mod:`pywps` WPS ``Execute`` request to corresponding WPS-REST job.

    The inputs and outputs must be parsed from XML POST payload or KVP GET query parameters, and converted to data
    container defined by :mod:`pywps` based on the process definition.
    """
    data = {
        "inputs": [],
        "outputs": [],
        "response": ExecuteResponse.DOCUMENT,
        "mode": ExecuteMode.ASYNC,
    }
    multi_inputs = list(wps_request.inputs.values())
    for input_list in multi_inputs:
        iid = get_any_id(input_list[0])
        for input_value in input_list:
            input_data = input_value.get("data")
            input_href = input_value.get("href")
            if input_href:  # when href is provided, it must always be non-empty
                data["inputs"].append({"id": iid, "href": input_href})
            else:  # no check if value to allow possible empty string, numeric zero or explicit null
                data["inputs"].append({"id": iid, "data": input_data})
    output_ids = list(wps_request.outputs)
    for output in wps_process.outputs:
        oid = output.identifier
        as_ref = isinstance(output, ComplexOutput)
        if oid not in output_ids:
            data_output = {"identifier": oid, "asReference": str(as_ref).lower()}
        else:
            data_output = wps_request.outputs[oid]
        if as_ref:
            data_output["transmissionMode"] = ExecuteTransmissionMode.VALUE
        else:
            data_output["transmissionMode"] = ExecuteTransmissionMode.VALUE
        data_output["id"] = oid
        data["outputs"].append(data_output)
    return data


def get_field(io_object,
              field,
              search_variations=False,
              extra_variations=None,
              only_variations=False,
              pop_found=False,
              key=False,
              default=null,
              ):
    # type: (Union[JSON, object], str, bool, Optional[List[str]], bool, bool, bool, Any) -> Any
    """
    Gets a field by name from various :term:`I/O` object types.

    Default value is :py:data:`null` used for most situations to differentiate from literal ``None`` which is often
    used as default for parameters. The :class:`NullType` allows to explicitly tell that there was 'no field' and
    not 'no value' in existing field. If you provided another value, it will be returned if not found within the
    input object.

    When :paramref:`search_variation` is enabled and that :paramref:`field` could not be found within the object,
    field lookup will employ the values under the :paramref:`field` entry within :data:`WPS_FIELD_MAPPING` as
    additional field names to search for an existing property or key. Search continues until the first match is found,
    respecting order within the variations listing, and finally uses :paramref:`default` if no match was found.

    :param io_object: Any :term:`I/O` representation, either as a class instance or :term:`JSON` container.
    :param field: Name of the field to look for, either as property or key name based on input object type.
    :param search_variations: If enabled, search for all variations to the field name to attempt search until matched.
    :param extra_variations: Additional field names to consider as search variations, with priority over field mapping.
    :param only_variations: If enabled, skip the first 'basic' field and start search directly with field variations.
    :param pop_found: If enabled, whenever a match is found by field or variations, remove that entry from the object.
    :param key: If enabled, whenever a match is found by field or variations, return matched key instead of the value.
    :param default: Alternative default value to return if no match could be found.
    :returns: Matched value (including search variations if enabled), or ``default``.
    """
    if not (search_variations and only_variations):
        if isinstance(io_object, dict):
            value = io_object.get(field, null)
            if value is not null:
                if pop_found:
                    io_object.pop(field)
                return field if key else value
        else:
            value = getattr(io_object, field, null)
            if value is not null:
                return field if key else value
    variations = extra_variations or []
    if search_variations or variations:
        variations += WPS_FIELD_MAPPING.get(field, [])
        for var in variations:
            value = get_field(io_object, var, search_variations=False, only_variations=False, pop_found=pop_found)
            if value is not null:
                return var if key else value
    return default


def set_field(io_object, field, value, force=False):
    # type: (Union[JSON, object], str, Any, bool) -> None
    """
    Sets a field by name into various :term:`I/O` object types.

    Field value is set only if not ``null`` to avoid inserting data considered `invalid`.
    If ``force=True``, verification of ``null`` value is ignored.
    """
    if value is not null or force:
        if isinstance(io_object, dict):
            io_object[field] = value
            return
        setattr(io_object, field, value)


def _are_different_and_set(item1, item2):
    # type: (Any, Any) -> bool
    """
    Verifies if two items are set and are different of different "representative" value.

    Compares two value representations and returns ``True`` only if both are not ``null``, are of same ``type`` and
    of different representative value. By "representative", we consider here the visual representation of byte/unicode
    strings rather than literal values to support XML/JSON and Python 2/3 implementations.
    Other non-string-like types are verified with literal (usual) equality method.
    """
    if item1 is null or item2 is null:
        return False
    try:
        # Note:
        #   Calling ``==`` will result in one defined item's type ``__eq__`` method calling a property to validate
        #   equality with the second. When compared to a ``null``, ``None`` or differently typed second item, the
        #   missing property on the second item could raise and ``AssertionError`` depending on the ``__eq__``
        #   implementation (eg: ``Format`` checking for ``item.mime_type``,  etc.).
        equal = item1 == item2
    except AttributeError:
        return False
    if equal:
        return False
    # Note: check for both (str, bytes) for any python implementation that modifies its value
    type1 = str if isinstance(item1, (str, bytes)) else type(item1)
    type2 = str if isinstance(item2, (str, bytes)) else type(item2)
    if type1 is str and type2 is str:
        return bytes2str(item1) != bytes2str(item2)
    return True


def is_equal_formats(format1, format2):
    # type: (Union[Format, JSON], Union[Format, JSON]) -> bool
    """
    Verifies for matching formats.
    """
    mime_type1 = get_field(format1, "mime_type", search_variations=True)
    mime_type2 = get_field(format2, "mime_type", search_variations=True)
    encoding1 = get_field(format1, "encoding", search_variations=True)
    encoding2 = get_field(format2, "encoding", search_variations=True)
    if (
        mime_type1 == mime_type2 and encoding1 == encoding2
        and all(f != null for f in [mime_type1, mime_type2, encoding1, encoding2])
    ):
        return True
    return False


def normalize_ordered_io(io_section, order_hints=None):
    # type: (JSON_IO_ListOrMap, Optional[JSON_IO_ListOrMap]) -> List[JSON]
    """
    Reorders and converts :term:`I/O` from any representation (:class:`dict` or :class:`list`) using ordering hints.

    First, converts :term:`I/O` definitions defined as dictionary to an equivalent :class:`list` representation,
    in order to work only with a single representation method. The :class:`list` is chosen over :class:`dict` because
    sequences can enforce a specific order, while mapping (when saved as :term:`JSON` or :term:`YAML`) have no specific
    order. The list representation ensures that :term:`I/O` order is preserved when written to file and reloaded
    afterwards regardless of server and/or library's implementation of the mapping container.

    If this function fails to correctly order any :term:`I/O` or cannot correctly guarantee such result because of
    the provided parameters (e.g.: no hints given when required), the result will not break nor change the final
    processing behaviour of parsers. This is merely *cosmetic* adjustments to ease readability of :term:`I/O` to avoid
    always shuffling their order across multiple :term:`Application Package` and :term:`Process` reporting formats.

    The important result of this function is to provide the :term:`I/O` as a consistent list of objects, so it is less
    cumbersome to compare/merge/iterate over the elements with all functions that will follow.

    .. note::
        When defined as a dictionary, an :class:`OrderedDict` is expected as input to ensure preserved field order.
        Prior to Python 3.7 or CPython 3.5, preserved order is not guaranteed for *builtin* :class:`dict`.
        In this case the :paramref:`order_hints` is required to ensure same order.

    This function is intended for parsing :term:`I/O` from :term:`Process` descriptions, :term:`Application Package`
    and other definitions that employ a ``"type"`` field. For submitted execution :term:`I/O` values, refer to other
    relevant functions.

    .. seealso::
        - :func:`convert_input_values_schema`
        - :func:`convert_output_params_schema`

    :param io_section: Definition contained under the ``inputs`` or ``outputs`` fields.
    :param order_hints: Optional/partial :term:`I/O` definitions hinting an order to sort unsorted-dict I/O.
    :returns: :term:`I/O` specified as list of dictionary definitions with preserved order (as good as possible).
    """
    if isinstance(io_section, list):
        return io_section
    io_list = []  # type: List[JSON]
    io_dict = OrderedDict()
    if isinstance(io_section, dict) and not isinstance(io_section, OrderedDict) and order_hints and len(order_hints):
        # convert the hints themselves to list if they are provided as mapping
        if isinstance(order_hints, dict):
            order_list = []
            for key, values in order_hints.items():
                values["id"] = key
                order_list.append(values)
            order_hints = order_list

        # pre-order I/O that can be resolved with hint when the specified I/O section is not ordered
        io_section = deepcopy(io_section)
        for hint in order_hints:
            hint_id = get_field(hint, "identifier", search_variations=True)
            if hint_id and hint_id in io_section:  # ignore hint where ID could not be resolved
                io_dict[hint_id] = io_section.pop(hint_id)
        for hint in io_section:
            io_dict[hint] = io_section[hint]
    else:
        io_dict = io_section
    for io_id, io_value in io_dict.items():
        # I/O value can be a literal type string or dictionary with more details at this point
        # make it always detailed dictionary to avoid problems for later parsing
        # this is also required to make the list, since all list items must have a matching type
        if isinstance(io_value, str):
            io_list.append({"type": io_value})
        else:
            io_list.append(io_value)
        io_list[-1]["id"] = io_id
    return io_list


def merge_io_formats(wps_formats, cwl_formats):
    # type: (List[ANY_Format_Type], List[ANY_Format_Type]) -> List[ANY_Format_Type]
    """
    Merges :term:`I/O` format definitions by matching ``mime-type`` field.

    In case of conflict, preserve the :term:`WPS` version which can be more detailed
    (for example, by specifying ``encoding``).

    Verifies if :data:`DEFAULT_FORMAT_MISSING` was written to a single :term:`CWL` format caused by a lack of any value
    provided as input. In this case, *only* :term:`WPS` formats are kept.

    In the event that :data:`DEFAULT_FORMAT_MISSING` was written to the :term:`CWL` formats and that no :term:`WPS`
    format was specified, the :data:`DEFAULT_FORMAT` is returned.

    :raises PackageTypeError: if inputs are invalid format lists
    """
    if not (isinstance(wps_formats, (list, tuple, set)) and isinstance(cwl_formats, (list, tuple, set))):
        raise PackageTypeError("Cannot merge formats definitions with invalid lists.")
    if not len(wps_formats):
        wps_formats = [DEFAULT_FORMAT]
    if len(cwl_formats) == 1 and get_field(cwl_formats[0], DEFAULT_FORMAT_MISSING) is True:
        return wps_formats

    formats = []
    cwl_fmt_dict = OrderedDict((get_field(fmt, "mime_type", search_variations=True), fmt) for fmt in cwl_formats)
    wps_fmt_dict = OrderedDict((get_field(fmt, "mime_type", search_variations=True), fmt) for fmt in wps_formats)
    for cwl_fmt in cwl_fmt_dict:
        if cwl_fmt in wps_fmt_dict:
            formats.append(wps_fmt_dict[cwl_fmt])
        else:
            formats.append(cwl_fmt_dict[cwl_fmt])
    wps_fmt_only = set(wps_fmt_dict) - set(cwl_fmt_dict)
    for wps_fmt in wps_fmt_only:
        formats.append(wps_fmt_dict[wps_fmt])
    return formats


def merge_io_fields(wps_io, cwl_io):
    # type: (WPS_IO_Type, WPS_IO_Type) -> WPS_IO_Type
    """
    Combines corresponding :term:`I/O` fields from :term:`WPS` and :term:`CWL` definitions.

    .. seealso::
        :func:`cwl2wps_io` for conversion of :term:`CWL` to :term:`WPS` representation.

    :param wps_io: Original :term:`WPS` :term:`I/O` provided in the process definition during deployment.
    :param cwl_io: Converted :term:`CWL` :term:`I/O` into :term:`WPS` representation for matching similar details.
    :return: Merged :term:`I/O` definition.
    """
    # Retrieve any complementing fields (metadata, keywords, etc.) passed in CWL/WPS inputs
    # Enforce some additional fields to keep value specified by WPS if applicable.
    # These are only added here rather that 'WPS_FIELD_MAPPING' to avoid erroneous detection by other functions.
    #   - Literal: 'default' value defined by 'data' (forced converted to string) or '_default' with original value
    #   - Complex: 'default' format defined by 'data_format'
    # (see function 'json2wps_io' for detail)
    # Important to have 'data_format' after, as it depends on 'supported_formats' processed an interation before.
    # Important to have 'metadata' before 'supported_formats' that interact together during mixed typed exchanges.
    wps_field_list = ["metadata"] + list(set(WPS_FIELD_MAPPING) - {"metadata"}) + ["_default", "data_format"]
    for field_type in wps_field_list:
        cwl_field = get_field(cwl_io, field_type)
        wps_field = get_field(wps_io, field_type)
        # employ provided formats if different (keep WPS), or if CWL offers more that were missing in WPS
        # because 'updated_io_list' contains the WPS I/O already, only need to push differences found in CWL
        if _are_different_and_set(wps_field, cwl_field) or (wps_field is null and cwl_field is not null):
            # because WPS Bbox is mapped against CWL Complex, adjust format to metadata in that case
            # WPS expected to have no formats, since not a complex
            # CWL expected to have only 1 because 'format' field is unique (see also 'cwl2wps_io' schema handling)
            if (
                field_type in ["supported_formats", "data_format"] and
                isinstance(wps_io, BasicBoundingBox) and isinstance(cwl_io, BasicComplex)
            ):
                cwl_field = cwl_field[0] if isinstance(cwl_field, (list, tuple)) else cwl_field
                wps_field = get_field(wps_io, "metadata", default=[])
                if not any(meta.href == cwl_field.schema for meta in wps_field):
                    wps_field.append(WPS_Metadata(
                        title="Schema",
                        href=cwl_field.schema,
                        role=SchemaRole.JSON_SCHEMA,
                        type_=cwl_field.mime_type
                    ))
                    set_field(wps_io, "metadata", wps_field)
                continue
            if field_type == "supported_formats" and cwl_field is not null:
                wps_field = merge_io_formats(wps_field, cwl_field)
            # default 'data_format' must be one of the 'supported_formats'
            # avoid setting something invalid in this case, or it will cause problem after
            # note: 'supported_formats' must have been processed before
            elif field_type == "data_format":
                wps_fmts = get_field(wps_io, "supported_formats", search_variations=False, default=[])
                if wps_field not in wps_fmts:
                    continue
            set_field(wps_io, field_type, wps_field)
    return wps_io


def merge_package_io(wps_io_list, cwl_io_list, io_select):
    # type: (List[ANY_IO_Type], List[WPS_IO_Type], IO_Select_Type) -> List[JSON_IO_Type]
    """
    Merges corresponding parameters of different :term:`I/O` definition sources.

    Handled definition formats include :term:`I/O` representation for :term:`CWL`, :term:`OpenAPI`, :term:`WPS` and
    generic :term:`JSON` using properties resembling :mod:`pywps` or :mod:`owslib` objects.

    Update :term:`I/O` definitions to use for :term:`Process` creation and returned
    by ``GetCapabilities``/``DescribeProcess``.
    If :term:`WPS` :term:`I/O` definitions where provided during deployment, update `CWL-to-WPS`
    converted :term:`I/O` with the :term:`WPS` :term:`I/O` complementary details. If an :term:`OpenAPI` ``schema``
    definition was provided to define the :term:`I/O`, infer the corresponding :term:`WPS` :term:`I/O` details.
    Then, considering those resolved definitions and any missing information that could be inferred,
    extend field requirements that can be retrieved from :term:`CWL` definitions.

    Removes any deployment :term:`WPS` :term:`I/O` definitions that don't match any :term:`CWL` :term:`I/O` by ID,
    since they will be of no use for the underlying :term:`Application Package`.
    Adds missing deployment :term:`WPS` :term:`I/O` definitions using expected :term:`CWL` :term:`I/O` IDs.

    .. seealso::
        :func:`cwl2wps_io` for conversion of :term:`CWL` to :term:`WPS` representation.

    :param wps_io_list: List of :term:`WPS` :term:`I/O` (as json) passed during process deployment.
    :param cwl_io_list:
        List of :term:`CWL` :term:`I/O` converted to :term:`WPS`-like :term:`I/O` for counter-validation.
    :param io_select: :data:`IO_INPUT` or :data:`IO_OUTPUT` to specify desired WPS type conversion.
    :returns:
        List of updated :term:`JSON` :term:`I/O` combing :term:`CWL`, :term:`WPS` and :term:`OpenAPI` specifications.
    """
    if not isinstance(cwl_io_list, list):
        raise PackageTypeError("CWL I/O definitions must be provided, empty list if none required.")
    if not wps_io_list:
        wps_io_list = []
    wps_io_dict = OrderedDict((get_field(wps_io, "identifier", search_variations=True), deepcopy(wps_io))
                              for wps_io in wps_io_list)
    cwl_io_dict = OrderedDict((get_field(cwl_io, "identifier", search_variations=True), deepcopy(cwl_io))
                              for cwl_io in cwl_io_list)
    missing_io_list = [cwl_io for cwl_io in cwl_io_dict if cwl_io not in wps_io_dict]  # preserve ordering
    updated_io_list = []

    # WPS I/O by id not matching any converted CWL->WPS I/O are discarded
    # otherwise, evaluate provided WPS I/O definitions and find potential new information to be merged
    for cwl_id in cwl_io_dict:
        cwl_io = cwl_io_dict[cwl_id]
        if cwl_id in missing_io_list:
            json_io = wps2json_io(cwl_io)
            updated_io_list.append(json_io)
            continue  # missing WPS I/O can only be inferred using CWL->WPS definitions

        # enforce expected CWL->WPS I/O required parameters
        cwl_io_json = cwl_io.json
        wps_io_json = wps_io_dict[cwl_id]
        cwl_identifier = get_field(cwl_io_json, "identifier", search_variations=True)
        cwl_title = get_field(wps_io_json, "title", search_variations=True)
        wps_io_json.update({
            "identifier": cwl_identifier,
            "title": cwl_title if cwl_title is not null else cwl_identifier
        })
        # attempt to infer additional typing or constraints from OpenAPI schema if available
        wps_io_schema = get_field(wps_io_json, "schema")
        if wps_io_schema:
            json_io_schema = oas2json_io(wps_io_schema)
            if json_io_schema and isinstance(json_io_schema, dict):
                wps_io_json.update(json_io_schema)

        # check if WPS I/O resolves to default literal string due to missing detection of details for explicit type
        # this is permitted if the corresponding CWL I/O can provide the remaining details of the partial WPS I/O
        if "type" not in wps_io_json and "data_type" not in wps_io_json:
            cwl_io_type = get_field(cwl_io_json, "type", search_variations=False)
            wps_io_json["type"] = cwl_io_type
            # preemptively transfer the specific data-type as well, otherwise we might need to deal with different ones
            if cwl_io_type == WPS_LITERAL:
                wps_io_json["data_type"] = get_field(cwl_io_json, "data_type", search_variations=False)

        # fill missing WPS min/max occurs in 'provided' json to avoid overwriting resolved CWL values by WPS default '1'
        #   with 'default' field, this default '1' causes erroneous result when 'min_occurs' should be "0"
        #   with 'array' type, this default '1' causes erroneous result when 'max_occurs' should be "unbounded"
        cwl_min_occurs = get_field(cwl_io_json, "min_occurs", search_variations=True)
        cwl_max_occurs = get_field(cwl_io_json, "max_occurs", search_variations=True)
        wps_min_occurs = get_field(wps_io_json, "min_occurs", search_variations=True)
        wps_max_occurs = get_field(wps_io_json, "max_occurs", search_variations=True)
        if wps_min_occurs == null and cwl_min_occurs != null:
            wps_io_json["min_occurs"] = cwl_min_occurs
        if wps_max_occurs == null and cwl_max_occurs != null:
            wps_io_json["max_occurs"] = cwl_max_occurs

        wps_io = json2wps_io(wps_io_json, io_select)
        check_io_compatible(wps_io, cwl_io, cwl_id)
        wps_io = merge_io_fields(wps_io, cwl_io)

        # Given OpenAPI schema provided during WPS deployment, generate its extended I/O definition.
        #   This extension allows the user to provide only 'raw' or '$ref' complex object schema, while Weaver can
        #   receive it during execution either as raw data or file reference. This provides a more precise schema
        #   to what would actually be accepted/produced as input/output for the process.
        # Otherwise, generate one that best represents available details using only available WPS/CWL fields.
        json_io = wps2json_io(wps_io, forced_fields=True)
        oas_io = json2oas_io(json_io, wps_io_schema)
        json_io["schema"] = oas_io
        updated_io_list.append(json_io)

    return updated_io_list


def check_io_compatible(wps_io, cwl_io, io_id):
    # type: (WPS_IO_Type, WPS_IO_Type, str) -> None
    """
    Validate types to ensure they match categories, otherwise merging will cause more confusion.

    For `Literal`/`Complex` :term:`I/O` coming from :term:`WPS` side, they should be matched exactly
    with `Literal`/`Complex` :term:`I/O` on the :term:`CWL` side.

    .. note::
        The :term`CWL` :term:`I/O` in this case is expected to be a :mod:`pywps` converted :term:`I/O`
        from the :term`CWL` definition, and not a direct :term`CWL` :term:`I/O` definition.

    .. warning::
        When BoundingBox for :term:`WPS`, it should be mapped to ComplexInput on :term:`CWL` side (since no equivalent).

    :raises PackageTypeError: If :term:`I/O` are not compatible.
    """
    cwl_io_type = type(cwl_io)
    wps_io_type = type(wps_io)
    if not (
        (wps_io_type in [LiteralInput, LiteralOutput] and cwl_io_type in [LiteralInput, LiteralOutput]) or
        (wps_io_type in [BoundingBoxInput, BoundingBoxOutput] and cwl_io_type in [ComplexInput, ComplexOutput]) or
        (wps_io_type in [ComplexInput, ComplexOutput] and cwl_io_type in [ComplexInput, ComplexOutput])
    ):
        msg_err = f"Mismatching CWL/WPS types for merge of I/O ID: [{io_id}] "
        msg_typ = f" (CWL: {fully_qualified_name(cwl_io_type)}, WPS: {fully_qualified_name(wps_io_type)})."
        LOGGER.error("%s.\n  CWL: %s\n  WPS: %s", msg_err, cwl_io_type, wps_io_type)
        raise PackageTypeError(msg_err + msg_typ)
