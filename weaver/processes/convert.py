"""
Conversion functions between corresponding data structures.
"""
import json
import logging
from collections import Hashable, OrderedDict  # pylint: disable=E0611,no-name-in-module   # moved to .abc in Python 3
from copy import deepcopy
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import lxml.etree
from owslib.wps import (
    ComplexData,
    Input as OWS_Input_Type,
    Metadata as OWS_Metadata,
    Output as OWS_Output_Type,
    is_reference
)
from pywps import Process as ProcessWPS
from pywps.app.Common import Metadata as WPS_Metadata
from pywps.inout import BoundingBoxInput, BoundingBoxOutput, ComplexInput, ComplexOutput, LiteralInput, LiteralOutput
from pywps.inout.basic import BasicIO
from pywps.inout.formats import Format
from pywps.inout.literaltypes import ALLOWEDVALUETYPE, AllowedValue, AnyValue
# FIXME: #211 (range): pywps.inout.literaltypes.RANGECLOSURETYPE
from pywps.validator.mode import MODE

from weaver.exceptions import PackageTypeError
from weaver.execute import (
    EXECUTE_MODE_ASYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
    EXECUTE_TRANSMISSION_MODE_VALUE
)
from weaver.formats import (
    CONTENT_TYPE_ANY,
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_TEXT_PLAIN,
    get_cwl_file_format,
    get_extension,
    get_format
)
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_WPS1,
    PACKAGE_ARRAY_BASE,
    PACKAGE_ARRAY_ITEMS,
    PACKAGE_ARRAY_MAX_SIZE,
    PACKAGE_ARRAY_TYPES,
    PACKAGE_CUSTOM_TYPES,
    PACKAGE_ENUM_BASE,
    PACKAGE_LITERAL_TYPES,
    WPS_BOUNDINGBOX,
    WPS_COMPLEX,
    WPS_COMPLEX_DATA,
    WPS_INPUT,
    WPS_LITERAL,
    WPS_LITERAL_DATA_TYPE_NAMES,
    WPS_OUTPUT,
    WPS_REFERENCE
)
from weaver.utils import bytes2str, fetch_file, get_any_id, get_sane_name, get_url_without_query, null, str2bytes
from weaver.wps.utils import get_wps_client

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
    from urllib.parse import ParseResult

    from pywps.app import WPSRequest
    from owslib.wps import Process as ProcessOWS
    from requests.models import Response

    from weaver.typedefs import (
        AnyKey,
        AnySettingsContainer,
        AnyValueType,
        CWL,
        CWL_Input_Type,
        CWL_Output_Type,
        JSON,
        XML
    )

    # typing shortcuts
    # pylint: disable=C0103,invalid-name
    WPS_Input_Type = Union[LiteralInput, ComplexInput, BoundingBoxInput]
    WPS_Output_Type = Union[LiteralOutput, ComplexOutput, BoundingBoxOutput]
    WPS_IO_Type = Union[WPS_Input_Type, WPS_Output_Type]
    OWS_IO_Type = Union[OWS_Input_Type, OWS_Output_Type]
    JSON_IO_Type = JSON
    CWL_IO_Type = Union[CWL_Input_Type, CWL_Output_Type]
    PKG_IO_Type = Union[JSON_IO_Type, WPS_IO_Type]
    ANY_IO_Type = Union[CWL_IO_Type, JSON_IO_Type, WPS_IO_Type, OWS_IO_Type]
    ANY_Format_Type = Union[Dict[str, Optional[str]], Format]
    ANY_Metadata_Type = Union[OWS_Metadata, WPS_Metadata, Dict[str, str]]


# WPS object attribute -> all possible *other* naming variations
WPS_FIELD_MAPPING = {
    "identifier": ["id", "ID", "Id", "Identifier"],
    "title": ["Title", "Label", "label"],
    "abstract": ["description", "Description", "Abstract"],
    "metadata": ["Metadata"],
    "keywords": ["Keywords"],
    "allowed_values": ["AllowedValues", "allowedValues", "allowedvalues", "Allowed_Values", "Allowedvalues"],
    "allowed_collections": ["AllowedCollections", "allowedCollections", "allowedcollections", "Allowed_Collections",
                            "Allowedcollections"],
    "default": ["default_value", "defaultValue", "DefaultValue", "Default", "data_format"],
    "supported_values": ["SupportedValues", "supportedValues", "supportedvalues", "Supported_Values"],
    "supported_formats": ["SupportedFormats", "supportedFormats", "supportedformats", "Supported_Formats", "formats"],
    "additional_parameters": ["AdditionalParameters", "additionalParameters", "additionalparameters",
                              "Additional_Parameters"],
    "type": ["Type", "data_type", "dataType", "DataType", "Data_Type"],
    "min_occurs": ["minOccurs", "MinOccurs", "Min_Occurs", "minoccurs"],
    "max_occurs": ["maxOccurs", "MaxOccurs", "Max_Occurs", "maxoccurs"],
    "mime_type": ["mimeType", "MimeType", "mime-type", "Mime-Type", "mimetype",
                  "mediaType", "MediaType", "media-type", "Media-Type", "mediatype"],
    "encoding": ["Encoding"],
    "href": ["url", "link", "reference"],
}
# WPS fields that contain a structure corresponding to `Format` object
#   - keys must match `WPS_FIELD_MAPPING` keys
#   - fields are placed in order of relevance (prefer explicit format, then supported, and defaults as last resort)
WPS_FIELD_FORMAT = ["formats", "supported_formats", "supported_values", "default"]

# WPS 'type' string variations employed to indicate a Complex (file) I/O by different libraries
# for literal types, see 'any2cwl_literal_datatype' and 'any2wps_literal_datatype' functions
WPS_COMPLEX_TYPES = [WPS_COMPLEX, WPS_COMPLEX_DATA, WPS_REFERENCE]

# WPS 'type' string of all combinations (type of data / library implementation)
WPS_ALL_TYPES = [WPS_LITERAL, WPS_BOUNDINGBOX] + WPS_COMPLEX_TYPES

# default format if missing (minimal requirement of one)
DEFAULT_FORMAT = Format(mime_type=CONTENT_TYPE_TEXT_PLAIN)
DEFAULT_FORMAT_MISSING = "__DEFAULT_FORMAT_MISSING__"
setattr(DEFAULT_FORMAT, DEFAULT_FORMAT_MISSING, True)

LOGGER = logging.getLogger(__name__)


def complex2json(data):
    # type: (Union[ComplexData, Any]) -> Union[JSON, Any]
    """
    Obtains the JSON representation of a :class:`ComplexData` or simply return the unmatched type.
    """
    if not isinstance(data, ComplexData):
        return data
    return {
        "mimeType": data.mimeType,
        "encoding": data.encoding,
        "schema": data.schema,
    }


def metadata2json(meta, force=False):
    # type: (Union[ANY_Metadata_Type, Any], bool) -> Union[JSON, Any]
    """
    Obtains the JSON representation of a :class:`OWS_Metadata` or :class:`pywps.app.Common.Metadata`.
    Otherwise, simply return the unmatched type.
    If requested, can enforce parsing a dictionary for the corresponding keys.
    """
    if not force and not isinstance(meta, (OWS_Metadata, WPS_Metadata)):
        return meta
    title = get_field(meta, "title", search_variations=True, default=None)
    href = get_field(meta, "href", search_variations=True, default=None)
    role = get_field(meta, "role", search_variations=True, default=None)
    rel = get_field(meta, "rel", search_variations=True, default=None)
    # many remote servers do not provide the 'rel', but instead provide 'title' or 'role'
    # build one by default to avoid failing schemas that expect 'rel' to exist
    if not rel:
        href_rel = urlparse(href).hostname
        rel = str(title or role or href_rel).lower()  # fallback to first available
        rel = get_sane_name(rel, replace_character="-", assert_invalid=False)
    return {"href": href, "title": title, "role": role, "rel": rel}


def ows2json_field(ows_field):
    # type: (Union[ComplexData, OWS_Metadata, AnyValueType]) -> Union[JSON, AnyValueType]
    """
    Obtains the JSON or raw value from an :mod:`owslib.wps` I/O field.
    """
    if isinstance(ows_field, ComplexData):
        return complex2json(ows_field)
    if isinstance(ows_field, OWS_Metadata):
        return metadata2json(ows_field)
    return ows_field


def ows2json_io(ows_io):
    # type: (OWS_IO_Type) -> JSON_IO_Type
    """
    Converts I/O definition from :mod:`owslib.wps` to JSON.
    """

    json_io = dict()
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

    # add 'format' if missing, derived from other variants
    if "formats" not in json_io:
        fmt_val = get_field(json_io, "supported_values")
        if fmt_val and json_io.get("type") == WPS_COMPLEX_DATA:
            json_io["formats"] = json_io.pop("supported_values")
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
                    json_io["formats"] = list()
                for var_fmt in fmt:
                    # add it only if not exclusively provided by a previous variant
                    json_fmt_items = [j_fmt.items() for j_fmt in json_io["formats"]]
                    if any(all(var_item in items for var_item in var_fmt.items()) for items in json_fmt_items):
                        continue
                    json_io["formats"].append(var_fmt)

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

        # Handle special case where we have a reference to a json array containing dataset reference
        # Avoid reference to reference by fetching directly the dataset references
        json_array = _get_multi_json_references(output, container)
        if json_array and all(str(ref).startswith("http") for ref in json_array):
            json_output["data"] = json_array

    else:
        # WPS standard v1.0.0 specify that Output data field has Zero or one value
        json_output["data"] = output.data[0] if output.data else None

    if (json_output["dataType"] == WPS_COMPLEX_DATA or "reference" in json_output) and output.mimeType:
        json_output["mimeType"] = output.mimeType

    return json_output


# FIXME: support metalink unwrapping (weaver #25)
# FIXME: reuse functions
#   definitely can be improved and simplified with 'fetch_file' function
#   then return parsed contents from that file
def _get_multi_json_references(output, container):
    # type: (OWS_Output_Type, Optional[AnySettingsContainer]) -> Optional[List[JSON]]
    """
    Since WPS standard does not allow to return multiple values for a single output,
    a lot of process actually return a JSON array containing references to these outputs.

    Because the multi-output references are contained within this JSON file, it is not very convenient to retrieve
    the list of URLs as one always needs to open and read the file to get them. This function goal is to detect this
    particular format and expand the references to make them quickly available in the job output response.

    :return:
        Array of HTTP(S) references if the specified output is effectively a JSON containing that, ``None`` otherwise.
    """
    # Check for the json datatype and mime-type
    if output.dataType == WPS_COMPLEX_DATA and output.mimeType == CONTENT_TYPE_APP_JSON:
        try:
            # If the json data is referenced read it's content
            if output.reference:
                with TemporaryDirectory() as tmp_dir:
                    file_path = fetch_file(output.reference, tmp_dir, settings=container)
                    with open(file_path, "r") as tmp_file:
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


def any2cwl_io(wps_io, io_select):
    # type: (Union[JSON_IO_Type, WPS_IO_Type, OWS_IO_Type], str) -> Tuple[CWL_IO_Type, Dict[str, str]]
    """
    Converts a `WPS`-like I/O to `CWL` corresponding I/O.
    Because of `CWL` I/O of type `File` with `format` field, the applicable namespace is also returned.

    :returns: converted I/O and namespace dictionary with corresponding format references as required
    """
    def _get_cwl_fmt_details(wps_fmt):
        # type: (ANY_Format_Type) -> Union[Tuple[Tuple[str, str], str, str], Tuple[None, None, None]]
        _wps_io_fmt = get_field(wps_fmt, "mime_type", search_variations=True)
        if not _wps_io_fmt:
            return None, None, None
        _cwl_io_ext = get_extension(_wps_io_fmt)
        _cwl_io_ref, _cwl_io_fmt = get_cwl_file_format(_wps_io_fmt, must_exist=True, allow_synonym=False)
        return _cwl_io_ref, _cwl_io_fmt, _cwl_io_ext

    wps_io_type = get_field(wps_io, "type", search_variations=True)
    wps_io_id = get_field(wps_io, "identifier", search_variations=True)
    cwl_ns = dict()
    cwl_io = {"id": wps_io_id}  # type: CWL_IO_Type
    if wps_io_type not in WPS_COMPLEX_TYPES:
        cwl_io_type = any2cwl_literal_datatype(wps_io_type)
        wps_allow = get_field(wps_io, "allowed_values", search_variations=True)
        if isinstance(wps_allow, list) and len(wps_allow) > 0:
            cwl_io["type"] = {"type": PACKAGE_ENUM_BASE, "symbols": wps_allow}
        else:
            cwl_io["type"] = cwl_io_type
    # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
    else:
        cwl_io_fmt = None
        cwl_io_ext = CONTENT_TYPE_ANY
        cwl_io["type"] = "File"

        # inputs are allowed to define multiple 'supported' formats
        # outputs are allowed to define only one 'applied' format
        for field in WPS_FIELD_FORMAT:
            fmt = get_field(wps_io, field, search_variations=True)
            if isinstance(fmt, dict):
                cwl_io_ref, cwl_io_fmt, cwl_io_ext = _get_cwl_fmt_details(fmt)
                if cwl_io_ref and cwl_io_fmt:
                    cwl_ns.update(cwl_io_ref)
                break
            if isinstance(fmt, list):
                if len(fmt) == 1:
                    cwl_io_ref, cwl_io_fmt, cwl_io_ext = _get_cwl_fmt_details(fmt[0])
                    if cwl_io_ref and cwl_io_fmt:
                        cwl_ns.update(cwl_io_ref)
                    break
                if io_select == WPS_OUTPUT and len(fmt) > 1:
                    break  # don't use any format because we cannot enforce one
                cwl_ns_multi = {}
                cwl_fmt_multi = []
                for fmt_i in fmt:
                    # FIXME: (?)
                    #   when multiple formats are specified, but at least one schema/namespace reference can't be found,
                    #   we must drop all since that unknown format is still allowed but cannot be validated
                    #   avoid potential validation error if that format was the one provided during execute...
                    #   (see: https://github.com/crim-ca/weaver/issues/50)
                    cwl_io_ref_i, cwl_io_fmt_i, _ = _get_cwl_fmt_details(fmt_i)
                    if cwl_io_ref_i and cwl_io_fmt_i:
                        cwl_ns_multi.update(cwl_io_ref_i)
                        cwl_fmt_multi.append(cwl_io_fmt_i)
                    else:
                        # reset all since at least one format could not be mapped to an official schema
                        cwl_ns_multi = {}
                        cwl_fmt_multi = None
                        break
                cwl_io_fmt = cwl_fmt_multi  # all formats or none of them
                cwl_ns.update(cwl_ns_multi)
                break
        if cwl_io_fmt:
            cwl_io["format"] = cwl_io_fmt
        # for backward compatibility with deployed processes, consider text/plan as 'any' for glob pattern
        cwl_io_txt = get_extension(CONTENT_TYPE_TEXT_PLAIN)
        if cwl_io_ext == cwl_io_txt:
            cwl_io_any = get_extension(CONTENT_TYPE_ANY)
            LOGGER.warning("Replacing '%s' [%s] to generic '%s' [%s] glob pattern. "
                           "More explicit format could be considered for %s '%s'.",
                           CONTENT_TYPE_TEXT_PLAIN, cwl_io_txt, CONTENT_TYPE_ANY, cwl_io_any, io_select, wps_io_id)
            cwl_io_ext = cwl_io_any
        if io_select == WPS_OUTPUT:
            # FIXME: (?) how to specify the 'name' part of the glob (using the "id" value for now)
            cwl_io["outputBinding"] = {
                "glob": "{}{}".format(wps_io_id, cwl_io_ext)
            }

    # FIXME: multi-outputs (https://github.com/crim-ca/weaver/issues/25)
    # min/max occurs can only be in inputs, outputs are enforced min/max=1 by WPS
    if io_select == WPS_INPUT:
        wps_default = get_field(wps_io, "default", search_variations=True)
        wps_min_occ = get_field(wps_io, "min_occurs", search_variations=True, default=1)
        # field 'default' must correspond to a fallback "value", not a default "format"
        is_min_null = wps_min_occ in [0, "0"]
        if wps_default != null and not isinstance(wps_default, dict):
            cwl_io["default"] = wps_default
        elif is_min_null:
            cwl_io["default"] = "null"

        wps_max_occ = get_field(wps_io, "max_occurs", search_variations=True)
        if wps_max_occ != null and (wps_max_occ == "unbounded" or wps_max_occ > 1):
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


def ows2json(wps_process, wps_service_name, wps_service_url):
    # type: (ProcessOWS, str, Union[str, ParseResult]) -> Tuple[CWL, JSON]
    """
    Generates the `CWL` package and process definitions from a :class:`owslib.wps.Process` hosted under `WPS` location.
    """
    process_info = OrderedDict([
        ("id", wps_process.identifier),
        ("keywords", [wps_service_name] if wps_service_name else []),
    ])
    default_title = wps_process.identifier.capitalize()
    process_info["title"] = get_field(wps_process, "title", default=default_title, search_variations=True)
    process_info["abstract"] = get_field(wps_process, "abstract", default=None, search_variations=True)
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
    for io_select in [WPS_INPUT, WPS_OUTPUT]:
        io_section = "{}s".format(io_select)
        cwl_package[io_section] = list()
        for wps_io in process_info[io_section]:
            cwl_io, cwl_ns = any2cwl_io(wps_io, io_select)
            cwl_package[io_section].append(cwl_io)
            if cwl_ns:
                if "$namespaces" not in cwl_package:
                    cwl_package["$namespaces"] = dict()
                cwl_package["$namespaces"].update(cwl_ns)
    return cwl_package, process_info


def xml_wps2cwl(wps_process_response, settings):
    # type: (Response, AnySettingsContainer) -> Tuple[CWL, JSON]
    """
    Converts a `WPS-1 ProcessDescription XML` tree structure to an equivalent `WPS-3 Process JSON` and builds the
    associated `CWL` package in conformance to :ref:`weaver.processes.wps_package.CWL_REQUIREMENT_APP_WPS1`.

    :param wps_process_response: valid response (XML, 200) from a `WPS-1 ProcessDescription`.
    :param settings: application settings to retrieve additional request options.
    """
    def _tag_name(_xml):
        # type: (Union[XML, str]) -> str
        """Obtains ``tag`` from a ``{namespace}Tag`` `XML` element."""
        if hasattr(_xml, "tag"):
            _xml = _xml.tag
        return _xml.split("}")[-1].lower()

    # look for `XML` structure starting at `ProcessDescription` (WPS-1)
    xml_resp = lxml.etree.fromstring(str2bytes(wps_process_response.content))
    xml_wps_process = xml_resp.xpath("//ProcessDescription")  # type: List[XML]
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


def is_cwl_file_type(io_info):
    # type: (CWL_IO_Type) -> bool
    """
    Identifies if the provided `CWL` input/output corresponds to one, many or potentially a ``File`` type(s).

    When multiple distinct *atomic* types are allowed for a given I/O (e.g.: ``[string, File]``) and that one of them
    is a ``File``, the result will be ``True`` even if other types are not ``Files``.
    Potential ``File`` when other base type is ``"null"`` will also return ``True``.
    """
    io_type = io_info.get("type")
    if not io_type:
        raise ValueError("Missing CWL 'type' definition: [{!s}]".format(io_info))
    if isinstance(io_type, str):
        return io_type == "File"
    if isinstance(io_type, dict):
        if io_type["type"] == PACKAGE_ARRAY_BASE:
            return io_type["items"] == "File"
        return io_type["type"] == "File"
    if isinstance(io_type, list):
        return any(typ == "File" or is_cwl_file_type({"type": typ}) for typ in io_type)
    msg = "Unknown parsing of CWL 'type' format ({!s}) [{!s}] in [{}]".format(type(io_type), io_type, io_info)
    raise ValueError(msg)


def is_cwl_array_type(io_info):
    # type: (CWL_IO_Type) -> Tuple[bool, str, MODE, Union[AnyValue, List[Any]]]
    """Verifies if the specified I/O corresponds to one of various CWL array type definitions.

    returns ``tuple(is_array, io_type, io_mode, io_allow)`` where:
        - ``is_array``: specifies if the I/O is of array type.
        - ``io_type``: array element type if ``is_array`` is True, type of ``io_info`` otherwise.
        - ``io_mode``: validation mode to be applied if sub-element requires it, defaults to ``MODE.NONE``.
        - ``io_allow``: validation values to be applied if sub-element requires it, defaults to ``AnyValue``.
    :raises PackageTypeError: if the array element doesn't have the required values and valid format.
    """
    # use mapping to allow sub-function updates
    io_return = {
        "array": False,
        "allow": AnyValue,
        "type": io_info["type"],
        "mode": MODE.NONE,
    }

    def _update_if_sub_enum(_io_item):
        # type: (CWL_IO_Type) -> bool
        """
        Updates the ``io_return`` parameters if ``io_item`` evaluates to a valid ``enum`` type.
        Parameter ``io_item`` should correspond to the ``items`` field of an array I/O definition.
        Simple pass-through if the array item is not an ``enum``.
        """
        _is_enum, _enum_type, _enum_mode, _enum_allow = is_cwl_enum_type({"type": _io_item})
        if _is_enum:
            LOGGER.debug("I/O [%s] parsed as 'array' with sub-item as 'enum'", io_info["name"])
            io_return["type"] = _enum_type
            io_return["mode"] = _enum_mode
            io_return["allow"] = _enum_allow
        return _is_enum

    # optional I/O could be an array of '["null", "<type>"]' with "<type>" being any of the formats parsed after
    # is it the literal representation instead of the shorthand with '?'
    if isinstance(io_info["type"], list) and any(sub_type == "null" for sub_type in io_info["type"]):
        # we can ignore the optional indication in this case because it doesn't impact following parsing
        io_return["type"] = list(filter(lambda sub_type: sub_type != "null", io_info["type"]))[0]

    # array type conversion when defined as '{"type": "array", "items": "<type>"}'
    # validate against 'Hashable' instead of 'dict' since 'OrderedDict'/'CommentedMap' can fail 'isinstance()'
    if not isinstance(io_return["type"], str) and not isinstance(io_return["type"], Hashable) \
            and "items" in io_return["type"] and "type" in io_return["type"]:
        io_type = dict(io_return["type"])  # make hashable to allow comparison
        if io_type["type"] != PACKAGE_ARRAY_BASE:
            raise PackageTypeError("Unsupported I/O 'array' definition: '{}'.".format(repr(io_info)))
        # parse enum in case we got an array of allowed symbols
        is_enum = _update_if_sub_enum(io_type["items"])
        if not is_enum:
            io_return["type"] = io_type["items"]
        if io_return["type"] not in PACKAGE_ARRAY_ITEMS:
            raise PackageTypeError("Unsupported I/O 'array' definition: '{}'.".format(repr(io_info)))
        LOGGER.debug("I/O [%s] parsed as 'array' with nested dict notation", io_info["name"])
        io_return["array"] = True
    # array type conversion when defined as string '<type>[]'
    elif isinstance(io_return["type"], str) and io_return["type"] in PACKAGE_ARRAY_TYPES:
        io_return["type"] = io_return["type"][:-2]  # remove '[]'
        if io_return["type"] in PACKAGE_CUSTOM_TYPES:
            # parse 'enum[]' for array of allowed symbols, provide expected structure for sub-item parsing
            io_item = deepcopy(io_info)
            io_item["type"] = io_return["type"]  # override corrected type without '[]'
            _update_if_sub_enum(io_item)
        if io_return["type"] not in PACKAGE_ARRAY_ITEMS:
            raise PackageTypeError("Unsupported I/O 'array' definition: '{}'.".format(repr(io_info)))
        LOGGER.debug("I/O [%s] parsed as 'array' with shorthand '[]' notation", io_info["name"])
        io_return["array"] = True
    return io_return["array"], io_return["type"], io_return["mode"], io_return["allow"]


def is_cwl_enum_type(io_info):
    # type: (CWL_IO_Type) -> Tuple[bool, str, int, Union[List[str], None]]
    """Verifies if the specified I/O corresponds to a CWL enum definition.

    returns ``tuple(is_enum, io_type, io_allow)`` where:
        - ``is_enum``: specifies if the I/O is of enum type.
        - ``io_type``: enum base type if ``is_enum=True``, type of ``io_info`` otherwise.
        - ``io_mode``: validation mode to be applied if input requires it, defaults to ``MODE.NONE``.
        - ``io_allow``: validation values of the enum.
    :raises PackageTypeError: if the enum doesn't have the required parameters and valid format.
    """
    io_type = io_info["type"]
    if not isinstance(io_type, dict) or "type" not in io_type or io_type["type"] not in PACKAGE_CUSTOM_TYPES:
        return False, io_type, MODE.NONE, None

    if "symbols" not in io_type:
        raise PackageTypeError("Unsupported I/O 'enum' definition: '{!r}'.".format(io_info))
    io_allow = io_type["symbols"]
    if not isinstance(io_allow, list) or len(io_allow) < 1:
        raise PackageTypeError("Invalid I/O 'enum.symbols' definition: '{!r}'.".format(io_info))

    # validate matching types in allowed symbols and convert to supported CWL type
    first_allow = io_allow[0]
    for io_i in io_allow:
        if type(io_i) is not type(first_allow):
            raise PackageTypeError("Ambiguous types in I/O 'enum.symbols' definition: '{!r}'.".format(io_info))
    if isinstance(first_allow, str):
        io_type = "string"
    elif isinstance(first_allow, float):
        io_type = "float"
    elif isinstance(first_allow, int):
        io_type = "int"
    else:
        raise PackageTypeError("Unsupported I/O 'enum' base type: `{!s}`, from definition: `{!r}`."
                               .format(type(first_allow), io_info))

    # allowed value validator mode must be set for input
    return True, io_type, MODE.SIMPLE, io_allow


def cwl2wps_io(io_info, io_select):
    # type:(CWL_IO_Type, str) -> WPS_IO_Type
    """Converts input/output parameters from CWL types to WPS types.

    :param io_info: parsed IO of a CWL file
    :param io_select: :py:data:`WPS_INPUT` or :py:data:`WPS_OUTPUT` to specify desired WPS type conversion.
    :returns: corresponding IO in WPS format
    """
    is_input = False
    is_output = False
    # FIXME: BoundingBox not implemented (https://github.com/crim-ca/weaver/issues/51)
    if io_select == WPS_INPUT:
        is_input = True
        io_literal = LiteralInput       # type: Union[Type[LiteralInput], Type[LiteralOutput]]
        io_complex = ComplexInput       # type: Union[Type[ComplexInput], Type[ComplexOutput]]
        # io_bbox = BoundingBoxInput      # type: Union[Type[BoundingBoxInput], Type[BoundingBoxOutput]]
    elif io_select == WPS_OUTPUT:
        is_output = True
        io_literal = LiteralOutput      # type: Union[Type[LiteralInput], Type[LiteralOutput]]
        io_complex = ComplexOutput      # type: Union[Type[ComplexInput], Type[ComplexOutput]]
        # io_bbox = BoundingBoxOutput     # type: Union[Type[BoundingBoxInput], Type[BoundingBoxOutput]]
    else:
        raise PackageTypeError("Unsupported I/O info definition: '{!r}' with '{}'.".format(io_info, io_select))

    io_name = io_info["name"]
    io_type = io_info["type"]
    io_min_occurs = 1
    io_max_occurs = 1

    # obtain real type if "default" or shorthand "<type>?" was in CWL, which defines "type" as `["null", <type>]`
    # CWL allows multiple distinct types (e.g.: `string` and `int` simultaneously), but not WPS inputs
    # WPS allows only different amount of same type through min/max occurs
    # considering WPS conversion, we can also have following definition `["null", <type>, <array-type>]` (same type)
    if isinstance(io_type, list):
        if not len(io_type) > 1:
            raise PackageTypeError("Unsupported I/O type as list cannot have only one base type: '{}'".format(io_info))
        if "null" in io_type:
            if len(io_type) == 1:
                raise PackageTypeError("Unsupported I/O cannot be only 'null' type: '{}'".format(io_info))
            LOGGER.debug("I/O parsed for 'default'")
            io_min_occurs = 0  # I/O can be omitted since default value exists
            io_type = [typ for typ in io_type if typ != "null"]

        if len(io_type) == 1:  # valid if other was "null" now removed
            io_type = io_type[0]
        else:
            # check that many sub-type definitions all match same base type (no conflicting literals)
            io_type_many = set()
            io_base_type = None
            for i, typ in enumerate(io_type):
                sub_type = {"type": typ, "name": "{}[{}]".format(io_name, i)}
                is_array, array_elem, _, io_allow = is_cwl_array_type(sub_type)
                is_enum, enum_type, _, _ = is_cwl_enum_type(sub_type)
                # array base type more important than enum because later array conversion also handles allowed values
                if is_array:
                    io_base_type = typ  # highest priority (can have sub-literal or sub-enum)
                    io_type_many.add(array_elem)
                elif is_enum:
                    io_base_type = io_base_type if io_base_type is not None else enum_type  # less priority
                    io_type_many.add(enum_type)
                else:
                    io_base_type = io_base_type if io_base_type is not None else typ  # less priority
                    io_type_many.add(typ)  # literal base type by itself (not array/enum)
            if len(io_type_many) != 1:
                raise PackageTypeError("Unsupported I/O with many distinct base types for info: '{!s}'".format(io_info))
            io_type = io_base_type

        LOGGER.debug("I/O parsed for multiple base types")
        io_info["type"] = io_type  # override resolved multi-type base for more parsing

    # convert array types
    is_array, array_elem, io_mode, io_allow = is_cwl_array_type(io_info)
    if is_array:
        LOGGER.debug("I/O parsed for 'array'")
        io_type = array_elem
        io_max_occurs = PACKAGE_ARRAY_MAX_SIZE

    # convert enum types
    is_enum, enum_type, enum_mode, enum_allow = is_cwl_enum_type(io_info)
    if is_enum:
        LOGGER.debug("I/O parsed for 'enum'")
        io_type = enum_type
        io_allow = enum_allow
        io_mode = enum_mode

    # debug info for unhandled types conversion
    if not isinstance(io_type, str):
        LOGGER.debug("is_array:      [%s]", repr(is_array))
        LOGGER.debug("array_elem:    [%s]", repr(array_elem))
        LOGGER.debug("is_enum:       [%s]", repr(is_enum))
        LOGGER.debug("enum_type:     [%s]", repr(enum_type))
        LOGGER.debug("enum_allow:    [%s]", repr(enum_allow))
        LOGGER.debug("io_info:       [%s]", repr(io_info))
        LOGGER.debug("io_type:       [%s]", repr(io_type))
        LOGGER.debug("type(io_type): [%s]", type(io_type))
        raise TypeError("I/O type has not been properly decoded. Should be a string, got: '{!r}'".format(io_type))

    # literal types
    if is_enum or io_type in PACKAGE_LITERAL_TYPES:
        if io_type == "Any":
            io_type = "anyvalue"
        if io_type == "null":
            io_type = "novalue"
        if io_type in ["int", "integer", "long"]:
            io_type = "integer"
        if io_type in ["float", "double"]:
            io_type = "float"
        # keywords commonly used by I/O
        kw = {
            "identifier": io_name,
            "title": io_info.get("label", ""),
            "abstract": io_info.get("doc", ""),
            "data_type": io_type,
            "mode": io_mode,
        }
        if is_input:
            # avoid storing 'AnyValue' which become more problematic than
            # anything later on when CWL/WPS merging is attempted
            if io_allow is not AnyValue:
                kw["allowed_values"] = io_allow
            kw["default"] = io_info.get("default", None)
            kw["min_occurs"] = io_min_occurs
            kw["max_occurs"] = io_max_occurs
        return io_literal(**kw)
    # complex types
    else:
        # keywords commonly used by I/O
        kw = {
            "identifier": io_name,
            "title": io_info.get("label", io_name),
            "abstract": io_info.get("doc", ""),
        }
        if "format" in io_info:
            io_formats = [io_info["format"]] if isinstance(io_info["format"], str) else io_info["format"]
            kw["supported_formats"] = [get_format(fmt) for fmt in io_formats]
            kw["mode"] = MODE.SIMPLE  # only validate the extension (not file contents)
        else:
            # we need to minimally add 1 format, otherwise empty list is evaluated as None by pywps
            # when "supported_formats" is None, the process's json property raises because of it cannot iterate formats
            kw["supported_formats"] = [DEFAULT_FORMAT]
            kw["mode"] = MODE.NONE  # don't validate anything as default is only raw text
        if is_output:
            if io_type == "Directory":
                kw["as_reference"] = True
            if io_type == "File":
                has_contents = io_info.get("contents") is not None
                kw["as_reference"] = not has_contents
        else:
            # note:
            #   value of 'data_format' is identified as 'default' input format if specified with `Format`
            #   otherwise, `None` makes it automatically use the first one available in 'supported_formats'
            kw["data_format"] = get_field(io_info, "data_format")
            kw["data_format"] = json2wps_field(kw["data_format"], "supported_formats") if kw["data_format"] else None
            kw.update({
                "min_occurs": io_min_occurs,
                "max_occurs": io_max_occurs,
            })
        return io_complex(**kw)


def any2cwl_literal_datatype(io_type):
    # type: (str) -> Union[str, Type[null]]
    """
    Solves common literal data-type names to supported ones for `CWL`.
    """
    if io_type in ["string", "date", "time", "dateTime", "anyURI"]:
        return "string"
    if io_type in ["scale", "angle", "float", "double"]:
        return "float"
    if io_type in ["integer", "long", "positiveInteger", "nonNegativeInteger"]:
        return "int"
    if io_type in ["bool", "boolean"]:
        return "boolean"
    LOGGER.warning("Could not identify a CWL literal data type with [%s].", io_type)
    return null


def any2wps_literal_datatype(io_type, is_value):
    # type: (AnyValueType, bool) -> Union[str, Type[null]]
    """
    Solves common literal data-type names to supported ones for `WPS`.
    Verification is accomplished by name when ``is_value=False``, otherwise with python ``type`` when ``is_value=True``.
    """
    if isinstance(io_type, str):
        if not is_value:
            if io_type in ["string", "date", "time", "dateTime", "anyURI"]:
                return "string"
            if io_type in ["scale", "angle", "float", "double"]:
                return "float"
            if io_type in ["int", "integer", "long", "positiveInteger", "nonNegativeInteger"]:
                return "integer"
            if io_type in ["bool", "boolean"]:
                return "boolean"
        LOGGER.warning("Unknown named literal data type: '%s', using default 'string'. Should be one of: %s",
                       io_type, list(WPS_LITERAL_DATA_TYPE_NAMES))
        return "string"
    if is_value and isinstance(io_type, bool):
        return "boolean"
    if is_value and isinstance(io_type, int):
        return "integer"
    if is_value and isinstance(io_type, float):
        return "float"
    return null


def json2wps_datatype(io_info):
    # type: (JSON_IO_Type) -> str
    """
    Guesses the literal data-type from I/O JSON information in order to allow creation of the corresponding I/O WPS.
    Defaults to ``string`` if no suitable guess can be accomplished.
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
    # type: (JSON_IO_Type, str) -> Any
    """
    Converts an I/O field from a JSON literal data, list, or dictionary to corresponding WPS types.

    :param field_info: literal data or information container describing the type to be generated.
    :param field_category: one of ``WPS_FIELD_MAPPING`` keys to indicate how to parse ``field_info``.
    """
    if field_category == "allowed_values":
        if isinstance(field_info, AllowedValue):
            return field_info
        if isinstance(field_info, dict):
            field_info.pop("type", None)
            return AllowedValue(**field_info)
        if isinstance(field_info, str):
            return AllowedValue(value=field_info, allowed_type=ALLOWEDVALUETYPE.VALUE)
        if isinstance(field_info, list):
            return AllowedValue(minval=min(field_info), maxval=max(field_info), allowed_type=ALLOWEDVALUETYPE.RANGE)
    elif field_category == "supported_formats":
        if isinstance(field_info, dict):
            return Format(**field_info)
        if isinstance(field_info, str):
            return Format(field_info)
    elif field_category == "metadata":
        if isinstance(field_info, WPS_Metadata):
            return field_info
        if isinstance(field_info, dict):
            meta = metadata2json(field_info, force=True)
            meta.pop("rel", None)
            return WPS_Metadata(**meta)
        if isinstance(field_info, str):
            return WPS_Metadata(field_info)
    elif field_category == "keywords" and isinstance(field_info, list):
        return field_info
    elif field_category in ["identifier", "title", "abstract"] and isinstance(field_info, str):
        return field_info
    LOGGER.warning("Field of type '%s' not handled as known WPS field.", field_category)
    return None


def json2wps_io(io_info, io_select):
    # type: (JSON_IO_Type, str) -> WPS_IO_Type
    """Converts an I/O from a JSON dict to PyWPS types.

    :param io_info: I/O in JSON dict format.
    :param io_select: :py:data:`WPS_INPUT` or :py:data:`WPS_OUTPUT` to specify desired WPS type conversion.
    :return: corresponding I/O in WPS format.
    """

    io_info["identifier"] = get_field(io_info, "identifier", search_variations=True, pop_found=True)

    rename = {
        "formats": "supported_formats",
        "minOccurs": "min_occurs",
        "maxOccurs": "max_occurs",
        "dataType": "data_type",
        "defaultValue": "default",
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
    ]
    replace_values = {"unbounded": PACKAGE_ARRAY_MAX_SIZE}

    transform_json(io_info, rename=rename, remove=remove, replace_values=replace_values)

    # convert allowed value objects
    values = get_field(io_info, "allowed_values", search_variations=True, pop_found=True)
    if values is not null:
        if isinstance(values, list) and len(values) > 0:
            io_info["allowed_values"] = list()
            for allow_value in values:
                io_info["allowed_values"].append(json2wps_field(allow_value, "allowed_values"))
        else:
            io_info["allowed_values"] = AnyValue  # noqa

    # convert supported format objects
    formats = get_field(io_info, "supported_formats", search_variations=True, pop_found=True)
    if formats is not null:
        for fmt in formats:
            fmt["mime_type"] = get_field(fmt, "mime_type", search_variations=True, pop_found=True)
            fmt.pop("maximumMegabytes", None)
            # define the 'default' with 'data_format' to be used if explicitly specified from the payload
            if fmt.pop("default", None) is True:
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
    if io_type not in WPS_ALL_TYPES:
        io_type_guess = any2wps_literal_datatype(io_type, is_value=False)
        if io_type_guess is not null:
            io_type = WPS_LITERAL
            io_info["data_type"] = io_type_guess
    if io_select == WPS_INPUT:
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
            io_info.pop("supportedCRS", None)
            return BoundingBoxInput(**io_info)
        if io_type == WPS_LITERAL:
            io_info.pop("data_format", None)
            io_info.pop("supported_formats", None)
            io_info.pop("literalDataDomains", None)  # FIXME: https://github.com/crim-ca/weaver/issues/211
            io_info["data_type"] = json2wps_datatype(io_info)
            return LiteralInput(**io_info)
    elif io_select == WPS_OUTPUT:
        io_info.pop("min_occurs", None)
        io_info.pop("max_occurs", None)
        io_info.pop("allowed_values", None)
        io_info.pop("data_format", None)
        io_info.pop("default", None)
        if io_type in WPS_COMPLEX_TYPES:
            io_info.pop("supported_values", None)
            return ComplexOutput(**io_info)
        if io_type == WPS_BOUNDINGBOX:
            io_info.pop("supported_formats", None)
            return BoundingBoxOutput(**io_info)
        if io_type == WPS_LITERAL:
            io_info.pop("supported_formats", None)
            io_info["data_type"] = json2wps_datatype(io_info)
            return LiteralOutput(**io_info)
    raise PackageTypeError("Unknown conversion from dict to WPS type (type={0}, mode={1}).".format(io_type, io_select))


def wps2json_io(io_wps):
    # type: (WPS_IO_Type) -> JSON_IO_Type
    """Converts a PyWPS I/O into a dictionary based version with keys corresponding to standard names (WPS 2.0)."""

    if not isinstance(io_wps, BasicIO):
        raise PackageTypeError("Invalid type, expected 'BasicIO', got: [{0!r}] '{1!r}'".format(type(io_wps), io_wps))
    if not hasattr(io_wps, "json"):
        raise PackageTypeError("Invalid type definition expected to have a 'json' property.")

    io_wps_json = io_wps.json   # noqa

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
    }

    transform_json(io_wps_json, rename=rename, replace_values=replace_values, replace_func=replace_func)

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

        # set 'default' format if it matches perfectly, or if only mime-type matches and it is the only available one
        # (this avoid 'encoding' possibly not matching due to CWL not providing this information)
        io_default = get_field(io_wps_json, "default", search_variations=True)
        for io_format in io_wps_json["formats"]:
            io_format["default"] = (io_default != null and is_equal_formats(io_format, io_default))
        if io_default and len(io_wps_json["formats"]) == 1 and not io_wps_json["formats"][0]["default"]:
            io_default_mime_type = get_field(io_default, "mime_type", search_variations=True)
            io_single_fmt_mime_type = get_field(io_wps_json["formats"][0], "mime_type", search_variations=True)
            io_wps_json["formats"][0]["default"] = (io_default_mime_type == io_single_fmt_mime_type)

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
        "response": EXECUTE_RESPONSE_DOCUMENT,
        "mode": EXECUTE_MODE_ASYNC,
    }
    multi_inputs = list(wps_request.inputs.values())
    for input_list in multi_inputs:
        iid = get_any_id(input_list[0])
        for input_value in input_list:
            input_data = input_value.get("data")
            input_href = input_value.get("href")
            if input_data:
                data["inputs"].append({"id": iid, "data": input_data})
            elif input_href:
                data["inputs"].append({"id": iid, "href": input_href})
    output_ids = list(wps_request.outputs)
    for output in wps_process.outputs:
        oid = output.identifier
        as_ref = isinstance(output, ComplexOutput)
        if oid not in output_ids:
            data_output = {"identifier": oid, "asReference": str(as_ref).lower()}
        else:
            data_output = wps_request.outputs[oid]
        if as_ref:
            data_output["transmissionMode"] = EXECUTE_TRANSMISSION_MODE_REFERENCE
        else:
            data_output["transmissionMode"] = EXECUTE_TRANSMISSION_MODE_VALUE
        data_output["id"] = oid
        data["outputs"].append(data_output)
    return data


def get_field(io_object, field, search_variations=False, pop_found=False, default=null):
    # type: (Any, str, bool, bool, Any) -> Any
    """
    Gets a field by name from various I/O object types.

    Default value is :py:data:`null` used for most situations to differentiate from
    literal ``None`` which is often used as default for parameters. The :class:`NullType`
    allows to explicitly tell that there was 'no field' and not 'no value' in existing
    field. If you provided another value, it will be returned if not found within
    the input object.

    :returns: matched value (including search variations if enabled), or ``default``.
    """
    if isinstance(io_object, dict):
        value = io_object.get(field, null)
        if value is not null:
            if pop_found:
                io_object.pop(field)
            return value
    else:
        value = getattr(io_object, field, null)
        if value is not null:
            return value
    if search_variations and field in WPS_FIELD_MAPPING:
        for var in WPS_FIELD_MAPPING[field]:
            value = get_field(io_object, var, pop_found=pop_found)
            if value is not null:
                return value
    return default


def set_field(io_object, field, value, force=False):
    # type: (Union[ANY_IO_Type, ANY_Format_Type], str, Any, bool) -> None
    """
    Sets a field by name into various I/O object types.
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
    Compares two value representations and returns ``True`` only if both are not ``null``, are of same ``type`` and
    of different representative value. By "representative", we consider here the visual representation of byte/unicode
    strings to support XML/JSON and Python 2/3 implementations. Other non string-like types are verified with
    literal (usual) equality method.
    """
    if item1 is null or item2 is null:
        return False
    try:
        # Note:
        #   Calling ``==`` will result in one defined item's type ``__eq__`` method calling a property to validate
        #   equality with the second. When compared to a ``null``, ``None`` or differently type'd second item, the
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
    """Verifies for matching formats."""
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


def merge_io_formats(wps_formats, cwl_formats):
    # type: (List[ANY_Format_Type], List[ANY_Format_Type]) -> List[ANY_Format_Type]
    """
    Merges I/O format definitions by matching ``mime-type`` field.
    In case of conflict, preserve the WPS version which can be more detailed (for example, by specifying ``encoding``).

    Verifies if ``DEFAULT_FORMAT_MISSING`` was written to a single `CWL` format caused by a lack of any value
    provided as input. In this case, *only* `WPS` formats are kept.

    In the event that ``DEFAULT_FORMAT_MISSING`` was written to the `CWL` formats and that no `WPS` format was
    specified, the :py:data:`DEFAULT_FORMAT` is returned.

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


def merge_package_io(wps_io_list, cwl_io_list, io_select):
    # type: (List[ANY_IO_Type], List[WPS_IO_Type], str) -> List[WPS_IO_Type]
    """
    Update I/O definitions to use for process creation and returned by GetCapabilities, DescribeProcess.
    If WPS I/O definitions where provided during deployment, update `CWL-to-WPS` converted I/O with the WPS I/O
    complementary details. Otherwise, provide minimum field requirements that can be retrieved from CWL definitions.

    Removes any deployment WPS I/O definitions that don't match any CWL I/O by ID.
    Adds missing deployment WPS I/O definitions using expected CWL I/O IDs.

    :param wps_io_list: list of WPS I/O (as json) passed during process deployment.
    :param cwl_io_list: list of CWL I/O converted to WPS-like I/O for counter-validation.
    :param io_select: :py:data:`WPS_INPUT` or :py:data:`WPS_OUTPUT` to specify desired WPS type conversion.
    :returns: list of validated/updated WPS I/O for the process matching CWL I/O requirements.
    """
    if not isinstance(cwl_io_list, list):
        raise PackageTypeError("CWL I/O definitions must be provided, empty list if none required.")
    if not wps_io_list:
        wps_io_list = list()
    wps_io_dict = OrderedDict((get_field(wps_io, "identifier", search_variations=True), deepcopy(wps_io))
                              for wps_io in wps_io_list)
    cwl_io_dict = OrderedDict((get_field(cwl_io, "identifier", search_variations=True), deepcopy(cwl_io))
                              for cwl_io in cwl_io_list)
    missing_io_list = [cwl_io for cwl_io in cwl_io_dict if cwl_io not in wps_io_dict]  # preserve ordering
    updated_io_list = list()

    # WPS I/O by id not matching any converted CWL->WPS I/O are discarded
    # otherwise, evaluate provided WPS I/O definitions and find potential new information to be merged
    for cwl_id in cwl_io_dict:
        cwl_io = cwl_io_dict[cwl_id]
        updated_io_list.append(cwl_io)
        if cwl_id in missing_io_list:
            continue  # missing WPS I/O are inferred only using CWL->WPS definitions

        # enforce expected CWL->WPS I/O required parameters
        cwl_io_json = cwl_io.json
        wps_io_json = wps_io_dict[cwl_id]
        cwl_identifier = get_field(cwl_io_json, "identifier", search_variations=True)
        cwl_title = get_field(wps_io_json, "title", search_variations=True)
        wps_io_json.update({
            "identifier": cwl_identifier,
            "title": cwl_title if cwl_title is not null else cwl_identifier
        })
        # apply type if WPS deploy definition was partial but can be retrieved from CWL
        wps_io_json.setdefault("type", get_field(cwl_io_json, "type", search_variations=True))

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

        # retrieve any complementing fields (metadata, keywords, etc.) passed as WPS input
        # additionally enforce 'default' format defined by 'data_format' to keep value specified by WPS if applicable
        # (see function 'json2wps_io' for detail)
        for field_type in list(WPS_FIELD_MAPPING) + ["data_format"]:
            cwl_field = get_field(cwl_io, field_type)
            wps_field = get_field(wps_io, field_type)
            # override provided formats if different (keep WPS), or if CWL->WPS was missing but is provided by WPS
            if _are_different_and_set(wps_field, cwl_field) or (wps_field is not null and cwl_field is null):
                # list of formats are updated by comparing format items since information can be partially complementary
                if field_type in ["supported_formats"]:
                    wps_field = merge_io_formats(wps_field, cwl_field)
                # default 'data_format' must be one of the 'supported_formats'
                # avoid setting something invalid in this case, or it will cause problem after
                # note: 'supported_formats' must have been processed before
                if field_type == "data_format":
                    wps_fmts = get_field(updated_io_list[-1], "supported_formats", search_variations=False, default=[])
                    if wps_field not in wps_fmts:
                        continue
                set_field(updated_io_list[-1], field_type, wps_field)
    return updated_io_list


def transform_json(json_data,               # type: ANY_IO_Type
                   rename=None,             # type: Optional[Dict[AnyKey, Any]]
                   remove=None,             # type: Optional[List[AnyKey]]
                   add=None,                # type: Optional[Dict[AnyKey, Any]]
                   replace_values=None,     # type: Optional[Dict[AnyKey, Any]]
                   replace_func=None,       # type: Optional[Dict[AnyKey, Callable[[Any], Any]]]
                   ):                       # type: (...) -> ANY_IO_Type
    """
    Transforms the input json_data with different methods.
    The transformations are applied in the same order as the arguments.
    """
    rename = rename or {}
    remove = remove or []
    add = add or {}
    replace_values = replace_values or {}
    replace_func = replace_func or {}

    # rename
    for k, v in rename.items():
        if k in json_data:
            json_data[v] = json_data.pop(k)

    # remove
    for r_k in remove:
        json_data.pop(r_k, None)

    # add
    for k, v in add.items():
        json_data[k] = v

    # replace values
    for key, value in json_data.items():
        for old_value, new_value in replace_values.items():
            if value == old_value:
                json_data[key] = new_value

    # replace with function call
    for k, func in replace_func.items():
        if k in json_data:
            json_data[k] = func(json_data[k])

    # also rename if the type of the value is a list of dicts
    for key, value in json_data.items():
        if isinstance(value, list):
            for nested_item in value:
                if isinstance(nested_item, dict):
                    for k, v in rename.items():
                        if k in nested_item:
                            nested_item[v] = nested_item.pop(k)
                    for k, func in replace_func.items():
                        if k in nested_item:
                            nested_item[k] = func(nested_item[k])
    return json_data
