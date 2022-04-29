import json
import logging
import os
import re
import socket
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.request import urlopen

import yaml
from json2xml.json2xml import Json2xml
from pyramid.httpexceptions import HTTPNotFound, HTTPOk
from pyramid_storage.extensions import resolve_extensions
from pywps.inout.formats import FORMATS, Format
from requests.exceptions import ConnectionError

from weaver.base import Constants, classproperty

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Union

    from weaver.typedefs import JSON, AnyRequestType

LOGGER = logging.getLogger(__name__)


class AcceptLanguage(Constants):
    """
    Supported languages.
    """
    EN_CA = "en-CA"
    FR_CA = "fr-CA"
    EN_US = "en-US"


class ContentType(Constants):
    """
    Supported Content-Types.

    Media-type nomenclature::

        <type> "/" [x- | <tree> "."] <subtype> ["+" suffix] *[";" parameter=value]
    """

    APP_CWL = "application/x-cwl"
    APP_FORM = "application/x-www-form-urlencoded"
    APP_GEOJSON = "application/geo+json"
    APP_GZIP = "application/gzip"
    APP_HDF5 = "application/x-hdf5"
    APP_JSON = "application/json"
    APP_NETCDF = "application/x-netcdf"
    APP_OCTET_STREAM = "application/octet-stream"
    APP_PDF = "application/pdf"
    APP_TAR = "application/x-tar"          # map to existing gzip for CWL
    APP_TAR_GZ = "application/tar+gzip"    # map to existing gzip for CWL
    APP_VDN_GEOJSON = "application/vnd.geo+json"
    APP_XML = "application/xml"
    APP_YAML = "application/x-yaml"
    APP_ZIP = "application/zip"
    IMAGE_GEOTIFF = "image/tiff; subtype=geotiff"
    IMAGE_JPEG = "image/jpeg"
    IMAGE_GIF = "image/gif"
    IMAGE_PNG = "image/png"
    IMAGE_TIFF = "image/tiff"
    MULTI_PART_FORM = "multipart/form-data"
    TEXT_ENRICHED = "text/enriched"
    TEXT_HTML = "text/html"
    TEXT_PLAIN = "text/plain"
    TEXT_RICHTEXT = "text/richtext"
    TEXT_XML = "text/xml"
    VIDEO_MPEG = "video/mpeg"

    # special handling
    ANY_XML = {APP_XML, TEXT_XML}
    ANY = "*/*"


class OutputFormat(Constants):
    """
    Renderer output formats for :term:`CLI`, `OpenAPI` and HTTP response content generation.
    """
    JSON = classproperty(fget=lambda self: "json", doc="""
    Representation as :term:`JSON` (object), which can still be manipulated in code.
    """)

    JSON_STR = classproperty(fget=lambda self: "json+str", doc="""
    Representation as :term:`JSON` content formatted as string with indentation and newlines.
    """)

    JSON_RAW = classproperty(fget=lambda self: "json+raw", doc="""
    Representation as :term:`JSON` content formatted as raw string without any indentation or newlines.
    """)

    YAML = classproperty(fget=lambda self: "yaml", doc="""
    Representation as :term:`YAML` content formatted as string with indentation and newlines.
    """)

    YML = classproperty(fget=lambda self: "yml", doc="""
    Alias to YAML.
    """)

    XML = classproperty(fget=lambda self: "xml", doc="""
    Representation as :term:`XML` content formatted as serialized string.
    """)

    XML_STR = classproperty(fget=lambda self: "xml+str", doc="""
    Representation as :term:`XML` content formatted as string with indentation and newlines.
    """)

    XML_RAW = classproperty(fget=lambda self: "xml+raw", doc="""
    Representation as :term:`XML` content formatted as raw string without indentation or newlines.
    """)

    TXT = classproperty(fget=lambda self: "txt", doc="""
    Representation as plain text content without any specific reformatting or validation.
    """)

    TEXT = classproperty(fget=lambda self: "text", doc="""
    Representation as plain text content without any specific reformatting or validation.
    """)

    @classmethod
    def get(cls, format_or_version, default=JSON, allow_version=True):  # pylint: disable=W0221,W0237
        # type: (Union[str, AnyOutputFormat], AnyOutputFormat, bool) -> AnyOutputFormat
        """
        Resolve the applicable output format.

        :param format_or_version:
            Either a :term:`WPS` version, a known value for a ``f``/``format`` query parameter, or an ``Accept`` header
            that can be mapped to one of the supported output formats.
        :param default: Default output format if none could be resolved.
        :param allow_version: Enable :term:`WPS` version specifiers to infer the corresponding output representation.
        :return: Resolved output format.
        """
        if allow_version and format_or_version == "1.0.0":
            return OutputFormat.XML
        if allow_version and format_or_version == "2.0.0":
            return OutputFormat.JSON
        if "/" in format_or_version:  # Media-Type to output format renderer
            format_or_version = get_extension(format_or_version, dot=False)
        return super(OutputFormat, cls).get(str(format_or_version), default=default)

    @classmethod
    def convert(cls, data, to, item_root="item"):
        # type: (JSON, Union[str, AnyOutputFormat], str) -> Union[str, JSON]
        """
        Converts the input data from :term:`JSON` to another known format.

        :param data: Input data to convert. Must be a literal :term:`JSON` object, not a :term:`JSON`-like string.
        :param to:
            Target format representation.
            If the output format is not :term:`JSON`, it is **ALWAYS** converted to the formatted string of the
            requested format to ensure the contents are properly represented as intended. In the case of :term:`JSON`
            as target format or unknown format, the original object is returned directly.
        :param item_root:
            When using :term:`XML` representations, defines the top-most item name. Unused for other representations.
        :return: Formatted output.
        """
        from weaver.utils import bytes2str

        fmt = cls.get(to)
        if fmt == OutputFormat.JSON:
            return data
        if fmt == OutputFormat.JSON_STR:
            return repr_json(data, indent=2, ensure_ascii=False)
        if fmt == OutputFormat.JSON_RAW:
            return repr_json(data, ensure_ascii=False)
        if fmt in [OutputFormat.XML, OutputFormat.XML_RAW, OutputFormat.XML_STR]:
            pretty = fmt == OutputFormat.XML_STR
            xml = Json2xml(data, item_wrap=True, pretty=pretty, wrapper=item_root).to_xml()
            if fmt == OutputFormat.XML_RAW:
                xml = bytes2str(xml)
            if isinstance(xml, str):
                xml = xml.strip()
            return xml
        if fmt in [OutputFormat.YML, OutputFormat.YAML]:
            yml = yaml.safe_dump(data, indent=2, sort_keys=False, width=float("inf"))
            if yml.endswith("\n...\n"):  # added when data is single literal or None instead of list/object
                yml = yml[:-4]
            return yml
        return data


# explicit mime-type to extension when not literally written in item after '/' (excluding 'x-' prefix)
_CONTENT_TYPE_EXTENSION_OVERRIDES = {
    ContentType.APP_VDN_GEOJSON: ".geojson",  # pywps 4.4 default extension without vdn prefix
    ContentType.APP_NETCDF: ".nc",
    ContentType.APP_GZIP: ".gz",
    ContentType.APP_TAR_GZ: ".tar.gz",
    ContentType.APP_YAML: ".yml",
    ContentType.IMAGE_TIFF: ".tif",  # common alternate to .tiff
    ContentType.ANY: ".*",   # any for glob
    ContentType.APP_OCTET_STREAM: "",
    ContentType.APP_FORM: "",
    ContentType.MULTI_PART_FORM: "",
}
_CONTENT_TYPE_EXCLUDE = [
    ContentType.APP_OCTET_STREAM,
    ContentType.APP_FORM,
    ContentType.MULTI_PART_FORM,
]
_EXTENSION_CONTENT_TYPES_OVERRIDES = {
    ".text": ContentType.TEXT_PLAIN,  # common alias to .txt, especially when using format query
    ".tiff": ContentType.IMAGE_TIFF,  # avoid defaulting to subtype geotiff
    ".yaml": ContentType.APP_YAML,  # common alternative to .yml
}

_CONTENT_TYPE_EXTENSION_MAPPING = {}  # type: Dict[str, str]
_CONTENT_TYPE_EXTENSION_MAPPING.update(_CONTENT_TYPE_EXTENSION_OVERRIDES)
# extend with all known pywps formats
_CONTENT_TYPE_FORMAT_MAPPING = {
    # content-types here are fully defined with extra parameters (e.g.: geotiff as subtype of tiff)
    fmt.mime_type: fmt
    for _, fmt in FORMATS._asdict().items()  # noqa: W0212
    if fmt.mime_type not in _CONTENT_TYPE_EXCLUDE
}  # type: Dict[str, Format]
# back-propagate changes from new formats
_CONTENT_TYPE_EXTENSION_MAPPING.update({
    ctype: fmt.extension
    for ctype, fmt in _CONTENT_TYPE_FORMAT_MAPPING.items()  # noqa: W0212
    if ctype not in _CONTENT_TYPE_EXTENSION_MAPPING
})
# apply any remaining local types not explicitly or indirectly added by FORMATS
_CONTENT_TYPE_EXT_PATTERN = re.compile(r"^[a-z]+/(x-)?(?P<ext>([a-z]+)).*$")
_CONTENT_TYPE_LOCALS_MISSING = [
    (ctype, _CONTENT_TYPE_EXT_PATTERN.match(ctype))
    for name, ctype in locals().items()
    if name.startswith("ContentType.")
    and isinstance(ctype, str)
    and ctype not in _CONTENT_TYPE_EXCLUDE
    and ctype not in _CONTENT_TYPE_FORMAT_MAPPING
    and ctype not in _CONTENT_TYPE_EXTENSION_MAPPING
]
_CONTENT_TYPE_LOCALS_MISSING = sorted(
    [
        (ctype, "." + re_ext["ext"])
        for ctype, re_ext in _CONTENT_TYPE_LOCALS_MISSING if re_ext
    ],
    key=lambda typ: typ[0]
)
# update and back-propagate generated local types
_CONTENT_TYPE_EXTENSION_MAPPING.update(_CONTENT_TYPE_LOCALS_MISSING)
# extend additional types
# FIXME: disabled for security reasons
# _CONTENT_TYPE_EXTENSION_MAPPING.update({
#     ctype: ext
#     for ext, ctype in mimetypes.types_map.items()
#     if ctype not in _CONTENT_TYPE_EXCLUDE
#     and ctype not in _CONTENT_TYPE_EXTENSION_MAPPING
# })
_CONTENT_TYPE_FORMAT_MAPPING.update({
    ctype: Format(ctype, extension=ext)
    for ctype, ext in _CONTENT_TYPE_LOCALS_MISSING
    if ctype not in _CONTENT_TYPE_EXCLUDE
})
_CONTENT_TYPE_FORMAT_MAPPING.update({
    ctype: Format(ctype, extension=ext)
    for ctype, ext in _CONTENT_TYPE_EXTENSION_MAPPING.items()
    if ctype not in _CONTENT_TYPE_EXCLUDE
    and ctype not in _CONTENT_TYPE_FORMAT_MAPPING
})
_EXTENSION_CONTENT_TYPES_MAPPING = {
    # because the same extension can represent multiple distinct Content-Types,
    # derive the simplest (shortest) one by default for guessing generic Content-Type
    ext: ctype for ctype, ext in reversed(sorted(
        _CONTENT_TYPE_EXTENSION_MAPPING.items(),
        key=lambda typ_ext: len(typ_ext[0])
    ))
}
_EXTENSION_CONTENT_TYPES_MAPPING.update(_EXTENSION_CONTENT_TYPES_OVERRIDES)

# file types that can contain textual characters
_CONTENT_TYPE_CHAR_TYPES = [
    "application",
    "multipart",
    "text",
]

# redirect type resolution semantically equivalent CWL validators
# should only be used to map CWL 'format' field if they are not already resolved through existing IANA/EDAM reference
_CONTENT_TYPE_SYNONYM_MAPPING = {
    ContentType.APP_TAR: ContentType.APP_GZIP,
    ContentType.APP_TAR_GZ: ContentType.APP_GZIP,
}

# Mappings for "CWL->File->Format"
# IANA contains most standard MIME-types, but might not include special (application/x-hdf5, application/x-netcdf, etc.)
# EDAM contains many field-specific schemas, but don't have an implicit URL definition (uses 'format_<id>' instead)
# search:
#   - IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
#   - EDAM-classes: http://bioportal.bioontology.org/ontologies/EDAM/?p=classes (section 'Format')
#   - EDAM-browser: https://ifb-elixirfr.github.io/edam-browser/
IANA_NAMESPACE = "iana"
IANA_NAMESPACE_URL = "https://www.iana.org/assignments/media-types/"
IANA_NAMESPACE_DEFINITION = {IANA_NAMESPACE: IANA_NAMESPACE_URL}
# Generic entries in IANA Media-Type namespace registry that don't have an explicit endpoint,
# but are defined regardless. Avoid unnecessary HTTP NotFound toward those missing endpoints.
# (see items that don't have a link in 'Template' column in lists under 'IANA_NAMESPACE_URL')
IANA_KNOWN_MEDIA_TYPES = {
    ContentType.IMAGE_JPEG,
    ContentType.IMAGE_GIF,
    ContentType.TEXT_ENRICHED,
    ContentType.TEXT_PLAIN,
    ContentType.TEXT_RICHTEXT,
    ContentType.VIDEO_MPEG,
}
EDAM_NAMESPACE = "edam"
EDAM_NAMESPACE_URL = "http://edamontology.org/"
EDAM_NAMESPACE_DEFINITION = {EDAM_NAMESPACE: EDAM_NAMESPACE_URL}
EDAM_SCHEMA = "http://edamontology.org/EDAM_1.24.owl"
EDAM_MAPPING = {
    ContentType.APP_CWL: "format_3857",
    ContentType.IMAGE_GIF: "format_3467",
    ContentType.IMAGE_JPEG: "format_3579",
    ContentType.APP_HDF5: "format_3590",
    ContentType.APP_JSON: "format_3464",
    ContentType.APP_NETCDF: "format_3650",
    ContentType.APP_YAML: "format_3750",
    ContentType.TEXT_PLAIN: "format_1964",
}
FORMAT_NAMESPACES = frozenset([IANA_NAMESPACE, EDAM_NAMESPACE])


def get_allowed_extensions():
    # type: () -> List[str]
    """
    Obtain the complete list of extensions that are permitted for processing by the application.

    .. note::
        This is employed for security reasons. Files can still be specified with another allowed extension, but
        it will not automatically inherit properties applicable to scripts and executables.
        If a specific file type is refused due to its extension, a PR can be submitted to add it explicitly.
    """
    groups = [
        "archives",
        "audio",
        "data",
        "documents",
        # "executables",
        "images",
        # "scripts",
        "text",
        "video",
    ]
    base = set(resolve_extensions("+".join(groups)))
    extra = {ext[1:] for ext in _EXTENSION_CONTENT_TYPES_MAPPING if ext and "*" not in ext}
    return list(base | extra)


def get_format(mime_type, default=None):
    # type: (str, Optional[str]) -> Optional[Format]
    """
    Obtains a :class:`Format` with predefined extension and encoding details from known MIME-types.
    """
    fmt = _CONTENT_TYPE_FORMAT_MAPPING.get(mime_type)
    if fmt is not None:
        return fmt
    if default is not None:
        ctype = default
    else:
        ctype = clean_mime_type_format(mime_type, strip_parameters=True)
    if not ctype:
        return None
    ext = get_extension(ctype)
    fmt = Format(ctype, extension=ext)
    return fmt


def get_extension(mime_type, dot=True):
    # type: (str, bool) -> str
    """
    Retrieves the extension corresponding to :paramref:`mime_type` if explicitly defined, or by parsing it.
    """
    def _handle_dot(_ext):
        # type: (str) -> str
        if dot and not _ext.startswith(".") and _ext:  # don't add for empty extension
            return f".{_ext}"
        if not dot and _ext.startswith("."):
            return _ext[1:]
        return _ext

    fmt = _CONTENT_TYPE_FORMAT_MAPPING.get(mime_type)
    if fmt:
        return _handle_dot(fmt.extension)
    ext = _CONTENT_TYPE_EXTENSION_MAPPING.get(mime_type)
    if ext:
        return _handle_dot(ext)
    ctype = clean_mime_type_format(mime_type, strip_parameters=True)
    if not ctype:
        return ""
    ext_default = "." + ctype.split("/")[-1].replace("x-", "")
    ext = _CONTENT_TYPE_EXTENSION_MAPPING.get(ctype, ext_default)
    return _handle_dot(ext)


def get_content_type(extension, charset=None, default=None):
    # type: (str, Optional[str], Optional[str]) -> Optional[str]
    """
    Retrieves the Content-Type corresponding to the specified extension if it can be matched.

    :param extension: Extension for which to attempt finding a known Content-Type.
    :param charset: Charset to apply to the Content-Type as needed if extension was matched.
    :param default: Default Content-Type to return if no extension is matched.
    :return: Matched or default Content-Type.
    """
    if not extension:
        return default
    if not extension.startswith("."):
        extension = f".{extension}"
    ctype = _EXTENSION_CONTENT_TYPES_MAPPING.get(extension)
    if not ctype:
        return default
    return add_content_type_charset(ctype, charset)


def add_content_type_charset(content_type, charset):
    # type: (str, Optional[str]) -> str
    """
    Apply the specific charset to the content-type with some validation in case of conflicting definitions.

    :param content_type: Desired Content-Type.
    :param charset: Desired charset parameter.
    :return: updated content-type with charset.
    """
    # no parameters in Media-Type, but explicit Content-Type with charset could exist as needed
    if charset and "charset=" in content_type:
        return re.sub(r"charset\=[A-Za-z0-9\_\-]+", f"charset={charset}", content_type)
    # make sure to never include by mistake if the represented type cannot be characters
    if charset and any(content_type.startswith(_type + "/") for _type in _CONTENT_TYPE_CHAR_TYPES):
        return f"{content_type}; charset={charset}"
    return content_type


def get_cwl_file_format(mime_type, make_reference=False, must_exist=True, allow_synonym=True):
    # type: (str, bool, bool, bool) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
    """
    Obtains the extended schema reference from the media-type identifier.

    Obtains the corresponding `IANA`/`EDAM` ``format`` value to be applied under a `CWL` I/O ``File`` from
    the :paramref:`mime_type` (`Content-Type` header) using the first matched one.

    Lookup procedure is as follows:

    - If ``make_reference=False``:
        - If there is a match, returns ``tuple({<namespace-name: namespace-url>}, <format>)`` with:
            1) corresponding namespace mapping to be applied under ``$namespaces`` in the `CWL`.
            2) value of ``format`` adjusted according to the namespace to be applied to ``File`` in the `CWL`.
        - If there is no match but ``must_exist=False``, returns a literal and non-existing definition as
          ``tuple({"iana": <iana-url>}, <format>)``.
        - If there is no match but ``must_exist=True`` **AND** ``allow_synonym=True``, retry the call with the
          synonym if available, or move to next step. Skip this step if ``allow_synonym=False``.
        - Otherwise, returns ``(None, None)``

    - If ``make_reference=True``:
        - If there is a match, returns the explicit format reference as ``<namespace-url>/<format>``.
        - If there is no match but ``must_exist=False``, returns the literal reference as ``<iana-url>/<format>``
          (N.B.: literal non-official MIME-type reference will be returned even if an official synonym exists).
        - If there is no match but ``must_exist=True`` **AND** ``allow_synonym=True``, retry the call with the
          synonym if available, or move to next step. Skip this step if ``allow_synonym=False``.
        - Returns a single ``None`` as there is not match (directly or synonym).

    Note:
        In situations where ``must_exist=False`` is used and that the namespace and/or full format URL cannot be
        resolved to an existing reference, `CWL` will raise a validation error as it cannot confirm the ``format``.
        You must therefore make sure that the returned reference (or a synonym format) really exists when using
        ``must_exist=False`` before providing it to the `CWL` I/O definition. Setting ``must_exist=False`` should be
        used only for literal string comparison or pre-processing steps to evaluate formats.

    :param mime_type: Some reference, namespace'd or literal (possibly extended) MIME-type string.
    :param make_reference: Construct the full URL reference to the resolved MIME-type. Otherwise return tuple details.
    :param must_exist:
        Return result only if it can be resolved to an official MIME-type (or synonym if enabled), otherwise ``None``.
        Non-official MIME-type can be enforced if disabled, in which case `IANA` namespace/URL is used as it preserves
        the original ``<type>/<subtype>`` format.
    :param allow_synonym:
        Allow resolution of non-official MIME-type to an official MIME-type synonym if available.
        Types defined as *synonym* have semantically the same format validation/resolution for `CWL`.
        Requires ``must_exist=True``, otherwise the non-official MIME-type is employed directly as result.
    :returns: Resolved MIME-type format for `CWL` usage, accordingly to specified arguments (see description details).
    """
    def _make_if_ref(_map, _key, _fmt):
        # type: (Dict[str, str], str, str) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
        return os.path.join(_map[_key], _fmt) if make_reference else (_map, f"{_key}:{_fmt}")

    def _request_extra_various(_mime_type):
        # type: (str) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
        """
        Attempts multiple request-retry variants to be as permissive as possible to sporadic/temporary failures.
        """
        from weaver.utils import request_extra

        _mime_type_url = f"{IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE]}{_mime_type}"
        if _mime_type in IANA_KNOWN_MEDIA_TYPES:  # avoid HTTP NotFound
            if _mime_type in EDAM_MAPPING:  # prefer real reference if available
                return _make_if_ref(EDAM_NAMESPACE_DEFINITION, EDAM_NAMESPACE, EDAM_MAPPING[_mime_type])
            return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _mime_type)

        retries = 3
        try:
            resp = request_extra("head", _mime_type_url, retries=retries, timeout=2,
                                 allow_redirects=True, allowed_codes=[HTTPOk.code, HTTPNotFound.code])
            if resp.status_code == HTTPOk.code:
                return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _mime_type)
        except ConnectionError as exc:
            LOGGER.debug("Format request [%s] connection error: [%s]", _mime_type_url, exc)
        try:
            for _ in range(retries):
                try:
                    resp = urlopen(_mime_type_url, timeout=2)  # nosec: B310 # hardcoded HTTP(S) # pylint: disable=R1732
                except socket.timeout:
                    continue
                if resp.code == HTTPOk.code:
                    return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _mime_type)
                break
        except HTTPError:
            pass
        return None

    if not mime_type:
        return None if make_reference else (None, None)
    mime_type = clean_mime_type_format(mime_type, strip_parameters=True)
    result = _request_extra_various(mime_type)
    if result is not None:
        return result
    if mime_type in EDAM_MAPPING:
        return _make_if_ref(EDAM_NAMESPACE_DEFINITION, EDAM_NAMESPACE, EDAM_MAPPING[mime_type])
    if not must_exist:
        return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, mime_type)
    if result is None and allow_synonym and mime_type in _CONTENT_TYPE_SYNONYM_MAPPING:
        mime_type = _CONTENT_TYPE_SYNONYM_MAPPING.get(mime_type)
        return get_cwl_file_format(mime_type, make_reference=make_reference, must_exist=True, allow_synonym=False)
    return None if make_reference else (None, None)


def clean_mime_type_format(mime_type, suffix_subtype=False, strip_parameters=False):
    # type: (str, bool, bool) -> Optional[str]
    """
    Obtains a generic media-type identifier by cleaning up any additional parameters.

    Removes any additional namespace key or URL from :paramref:`mime_type` so that it corresponds to the generic
    representation (e.g.: ``application/json``) instead of the ``<namespace-name>:<format>`` mapping variant used
    in `CWL->inputs/outputs->File->format` or the complete URL reference.

    Removes any leading temporary local file prefix inserted by :term:`CWL` when resolving namespace mapping.
    This transforms ``file:///tmp/dir/path/package#application/json`` to plain ``application/json``.

    According to provided arguments, it also cleans up additional parameters or extracts sub-type suffixes.

    :param mime_type:
        MIME-type, full URL to MIME-type or namespace-formatted string that must be cleaned up.
    :param suffix_subtype:
        Remove additional sub-type specializations details separated by ``+`` symbol such that an explicit format like
        ``application/vnd.api+json`` returns only its most basic suffix format defined as``application/json``.
    :param strip_parameters:
        Removes additional MIME-type parameters such that only the leading part defining the ``type/subtype`` are
        returned. For example, this will get rid of ``; charset=UTF-8`` or ``; version=4.0`` parameters.

    .. note::
        Parameters :paramref:`suffix_subtype` and :paramref:`strip_parameters` are not necessarily exclusive.
    """
    if not mime_type:  # avoid mismatching empty string with random type
        return None
    # when 'format' comes from parsed CWL tool instance, the input/output record sets the value
    # using a temporary local file path after resolution against remote namespace ontology
    if mime_type.startswith("file://") and "#" in mime_type:
        mime_type = mime_type.split("#")[-1]
    if strip_parameters:
        mime_type = mime_type.split(";")[0]
    if suffix_subtype and "+" in mime_type:
        # parameters are not necessarily stripped, need to re-append them after if any
        parts = mime_type.split(";", 1)
        if len(parts) < 2:
            parts.append("")
        else:
            parts[1] = f";{parts[1]}"
        typ, sub = parts[0].split("/")
        sub = sub.split("+")[-1]
        mime_type = f"{typ}/{sub}{parts[1]}"
    for v in list(IANA_NAMESPACE_DEFINITION.values()) + list(EDAM_NAMESPACE_DEFINITION.values()):
        if v in mime_type:
            mime_type = mime_type.replace(v, "")
    for v in list(IANA_NAMESPACE_DEFINITION.keys()) + list(EDAM_NAMESPACE_DEFINITION.keys()):
        if mime_type.startswith(v + ":"):
            mime_type = mime_type.replace(v + ":", "")
    for v in EDAM_MAPPING.values():
        if v.endswith(mime_type):
            mime_type = [k for k in EDAM_MAPPING if v.endswith(EDAM_MAPPING[k])][0]
    return mime_type


def guess_target_format(request, default=ContentType.APP_JSON):
    # type: (AnyRequestType, str) -> str
    """
    Guess the best applicable response ``Content-Type`` header from the request.

    Considers the request ``Accept`` header, ``format`` query and alternatively ``f`` query to parse possible formats.
    Full Media-Type are expected in the header. Query parameters can use both the full type, or only the sub-type
    (i.e.: :term:`JSON`, :term:`XML`, etc.), with case-insensitive names.
    Defaults to :py:data:`ContentType.APP_JSON` if none was specified.

    Applies some specific logic to handle automatically added ``Accept`` headers by many browsers such that sending
    requests to the API using them will not automatically default back to :term:`XML` or similar `HTML` representations.
    If browsers are used to send requests, but that ``format``/``f`` queries are used directly in the URL, those will
    be applied since this is a very intuitive (and easier) approach to request different formats when using browsers.

    When user-agent clients are identified as another source, such as sending requests from a server or from code, both
    headers and query parameters are applied directly without question.

    :returns: Matched MIME-type or default.
    """
    from weaver.utils import get_header

    format_query = request.params.get("format") or request.params.get("f")
    content_type = None
    if format_query:
        content_type = OutputFormat.get(format_query, default=None, allow_version=False)
        if content_type:
            content_type = get_content_type(content_type)
    if not content_type:
        content_type = get_header("accept", request.headers, default=default)
        for ctype in content_type.split(","):
            ctype = clean_mime_type_format(ctype, suffix_subtype=True, strip_parameters=True)
            if ctype != default:
                # because most browsers enforce some 'visual' list of accept header, revert to JSON if detected
                # explicit request set by client (e.g.: using 'requests') will have full control over desired content
                user_agent = get_header("user-agent", request.headers)
                if user_agent and any(browser in user_agent for browser in ["Mozilla", "Chrome", "Safari"]):
                    content_type = ContentType.APP_JSON
    if not content_type or content_type == ContentType.ANY:
        content_type = default
    return content_type


def repr_json(data, force_string=True, ensure_ascii=False, indent=2, **kwargs):
    # type: (Any, bool, bool, Optional[int], **Any) -> Union[JSON, str, None]
    """
    Ensure that the input data can be serialized as JSON to return it formatted representation as such.

    If formatting as JSON fails, returns the data as string representation or ``None`` accordingly.
    """
    if data is None:
        return None
    try:
        data_str = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, **kwargs)
        return data_str if force_string else data
    except Exception:  # noqa: W0703 # nosec: B110
        return str(data)


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyOutputFormat = Literal[
        OutputFormat.JSON,
        OutputFormat.XML,
        OutputFormat.YAML,
        OutputFormat.YML,
    ]
