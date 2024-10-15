import base64
import datetime
import json
import logging
import os
import re
import socket
from typing import TYPE_CHECKING, cast, overload
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml
from json2xml.json2xml import Json2xml
from pyramid.httpexceptions import HTTPNotFound, HTTPOk
from pyramid_storage.extensions import resolve_extensions
from pywps.inout.formats import FORMATS, Format
from requests.exceptions import ConnectionError

from weaver.base import Constants, classproperty
from weaver.compat import cache

if TYPE_CHECKING:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, TypeAlias, TypeVar, Union
    from typing_extensions import Literal

    from weaver.base import PropertyDataTypeT
    from weaver.typedefs import AnyRequestType, JSON, ProcessInputOutputItem

    FileModeSteamType = Literal["r", "w", "a", "r+", "w+"]
    FileModeEncoding = Literal["r", "w", "a", "rb", "wb", "ab", "r+", "w+", "a+", "r+b", "w+b", "a+b"]
    DataStrT = TypeVar("DataStrT")

    FormatSource = Literal["header", "query", "default"]

    _ContentType = "ContentType"  # type: TypeAlias  # pylint: disable=C0103
    AnyContentType = Union[str, _ContentType]
    _ContentEncoding = "ContentEncoding"  # type: TypeAlias  # pylint: disable=C0103
    AnyContentEncoding = Union[
        Literal["UTF-8", "binary", "base16", "base32", "base64"],
        _ContentEncoding,
    ]
    AnyOutputFormat = Literal[
        "JSON", "json",
        "JSON+RAW", "json+str",
        "JSON+RAW", "json+raw",
        "XML", "xml",
        "XML+STR", "xml+str",
        "XML+RAW", "xml+raw",
        "HTML", "html",
        "HTML+STR", "html+str",
        "HTML+RAW", "html+raw",
        "TXT", "txt",
        "TEXT", "text",
        "YML", "yml",
        "YAML", "yaml",
    ]

LOGGER = logging.getLogger(__name__)


class AcceptLanguage(Constants):
    """
    Supported languages.
    """
    EN_CA = "en-CA"
    FR_CA = "fr-CA"
    EN_US = "en-US"

    @classmethod
    def offers(cls):
        # type: () -> List[str]
        """
        Languages offered by the application.
        """
        languages = AcceptLanguage.values()
        languages += list({lang.split("-")[0] for lang in languages})
        return languages


class ContentType(Constants):
    """
    Supported ``Content-Type`` values.

    Media-Type nomenclature::

        <type> "/" [x- | <tree> "."] <subtype> ["+" suffix] *[";" parameter=value]
    """

    APP_DIR = "application/directory"
    APP_CWL = "application/cwl"
    APP_CWL_JSON = "application/cwl+json"
    APP_CWL_YAML = "application/cwl+yaml"
    APP_CWL_X = "application/x-cwl"  # backward compatible format, others are official
    APP_FORM = "application/x-www-form-urlencoded"
    APP_GEOJSON = "application/geo+json"
    APP_GZIP = "application/gzip"
    APP_HDF5 = "application/x-hdf5"
    APP_JSON = "application/json"
    APP_RAW_JSON = "application/raw+json"
    APP_OAS_JSON = "application/vnd.oai.openapi+json; version=3.0"
    APP_OGC_PKG_JSON = "application/ogcapppkg+json"
    APP_OGC_PKG_YAML = "application/ogcapppkg+yaml"
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
    IMAGE_OGC_GEOTIFF = "image/tiff; application=geotiff"
    IMAGE_COG = "image/tiff; application=geotiff; profile=cloud-optimized"
    IMAGE_JPEG = "image/jpeg"
    IMAGE_GIF = "image/gif"
    IMAGE_PNG = "image/png"
    IMAGE_TIFF = "image/tiff"
    IMAGE_SVG_XML = "image/svg+xml"
    MULTIPART_ANY = "multipart/*"
    MULTIPART_FORM = "multipart/form-data"      # data/file upload
    MULTIPART_MIXED = "multipart/mixed"         # content of various types
    MULTIPART_RELATED = "multipart/related"     # content that contain cross-references with Content-ID (CID)
    TEXT_ENRICHED = "text/enriched"
    TEXT_HTML = "text/html"
    TEXT_PLAIN = "text/plain"
    TEXT_RICHTEXT = "text/richtext"
    TEXT_XML = "text/xml"
    VIDEO_MPEG = "video/mpeg"

    # special handling
    ANY_JSON = {
        APP_JSON, APP_YAML,
        APP_GEOJSON, APP_VDN_GEOJSON,
        APP_CWL, APP_CWL_JSON, APP_CWL_X, APP_CWL_YAML,
        APP_OAS_JSON,
        APP_OGC_PKG_JSON, APP_OGC_PKG_YAML,
    }
    ANY_CWL = {APP_CWL, APP_CWL_JSON, APP_CWL_YAML, APP_CWL_X}
    ANY_XML = {APP_XML, TEXT_XML}
    ANY_MULTIPART = {MULTIPART_ANY, MULTIPART_FORM, MULTIPART_MIXED, MULTIPART_RELATED}
    ANY = "*/*"


class ContentEncoding(Constants):
    """
    Supported ``Content-Encoding`` values.

    .. note::
        Value ``binary`` is kept for convenience and backward compatibility with older definitions.
        It will default to the same encoding strategy as if ``base64`` was specified explicitly.
        Value ``binary`` is not part of :rfc:`4648`, but remains a common occurrence that dates from
        when ``format: binary`` was the approach employed to represent binary (JSON-schema Draft-04 and prior)
        instead of what is now recommended using ``contentEncoding: base64`` (JSON-schema Draft-07).

    .. seealso::
        - https://github.com/json-schema-org/json-schema-spec/issues/803
        - https://github.com/json-schema-org/json-schema-spec/pull/862
    """
    UTF_8 = "UTF-8"    # type: Literal["UTF-8"]
    BINARY = "binary"  # type: Literal["binary"]
    BASE16 = "base16"  # type: Literal["base16"]
    BASE32 = "base32"  # type: Literal["base32"]
    BASE64 = "base64"  # type: Literal["base64"]

    @staticmethod
    def is_text(encoding):
        # type: (Any) -> bool
        """
        Indicates if the ``Content-Encoding`` value can be categorized as textual data.
        """
        return ContentEncoding.get(encoding) in [ContentEncoding.UTF_8, None]

    @staticmethod
    def is_binary(encoding):
        # type: (Any) -> bool
        """
        Indicates if the ``Content-Encoding`` value can be categorized as binary data.
        """
        return not ContentEncoding.is_text(encoding)

    @staticmethod
    def open_parameters(encoding, mode="r"):
        # type: (Any, FileModeSteamType) -> Tuple[FileModeEncoding, Literal["UTF-8", None]]
        """
        Obtains relevant ``mode`` and ``encoding`` parameters for :func:`open` using the specified ``Content-Encoding``.
        """
        if ContentEncoding.is_binary(encoding):
            mode = cast("FileModeEncoding", f"{mode}b")
            return mode, None
        return mode, ContentEncoding.UTF_8

    @staticmethod
    @overload
    def encode(data, encoding=BASE64, binary=True):
        # type: (AnyStr, AnyContentEncoding, Literal[True]) -> bytes
        ...

    @staticmethod
    @overload
    def encode(data, encoding=BASE64, binary=False):
        # type: (AnyStr, AnyContentEncoding, Literal[False]) -> str
        ...

    @staticmethod
    @overload
    def encode(data, encoding=BASE64, binary=None):
        # type: (DataStrT, AnyContentEncoding, Literal[None]) -> DataStrT
        ...

    @staticmethod
    def encode(data, encoding=BASE64, binary=None):
        # type: (AnyStr, AnyContentEncoding, Optional[bool]) -> AnyStr
        """
        Encodes the data to the requested encoding and convert it to the string-like data type representation.

        :param data: Data to encode.
        :param encoding: Target encoding method.
        :param binary:
            If unspecified, the string-like type will be the same as the input data.
            Otherwise, convert the encoded data to :class:`str` or :class:`bytes` accordingly.
        :return: Encoded and converted data.
        """
        data_type = type(data)
        out_type = data_type if binary is None else (bytes if binary else str)
        enc_type = ContentEncoding.get(encoding, default=ContentEncoding.UTF_8)
        enc_func = {
            (str, str, ContentEncoding.UTF_8): lambda _: _,
            (str, bytes, ContentEncoding.UTF_8): lambda s: s.encode(),
            (bytes, bytes, ContentEncoding.UTF_8): lambda _: _,
            (bytes, str, ContentEncoding.UTF_8): lambda s: s.decode(),
            (str, str, ContentEncoding.BASE16): lambda s: base64.b16encode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BASE16): lambda s: base64.b16encode(s.encode()),
            (bytes, str, ContentEncoding.BASE16): lambda s: base64.b16encode(s).decode(),
            (bytes, bytes, ContentEncoding.BASE16): lambda s: base64.b16encode(s),
            (str, str, ContentEncoding.BASE32): lambda s: base64.b32encode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BASE32): lambda s: base64.b32encode(s.encode()),
            (bytes, str, ContentEncoding.BASE32): lambda s: base64.b32encode(s).decode(),
            (bytes, bytes, ContentEncoding.BASE32): lambda s: base64.b32encode(s),
            (str, str, ContentEncoding.BASE64): lambda s: base64.b64encode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BASE64): lambda s: base64.b64encode(s.encode()),
            (bytes, str, ContentEncoding.BASE64): lambda s: base64.b64encode(s).decode(),
            (bytes, bytes, ContentEncoding.BASE64): lambda s: base64.b64encode(s),
            (str, str, ContentEncoding.BINARY): lambda s: base64.b64encode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BINARY): lambda s: base64.b64encode(s.encode()),
            (bytes, str, ContentEncoding.BINARY): lambda s: base64.b64encode(s).decode(),
            (bytes, bytes, ContentEncoding.BINARY): lambda s: base64.b64encode(s),
        }
        return enc_func[(data_type, out_type, enc_type)](data)

    @staticmethod
    @overload
    def decode(data, encoding=BASE64, binary=True):
        # type: (AnyStr, AnyContentEncoding, Literal[True]) -> bytes
        ...

    @staticmethod
    @overload
    def decode(data, encoding=BASE64, binary=False):
        # type: (AnyStr, AnyContentEncoding, Literal[False]) -> str
        ...

    @staticmethod
    @overload
    def decode(data, encoding=BASE64, binary=None):
        # type: (DataStrT, AnyContentEncoding, Literal[None]) -> DataStrT
        ...

    @staticmethod
    def decode(data, encoding=BASE64, binary=None):
        # type: (AnyStr, AnyContentEncoding, Optional[bool]) -> AnyStr
        """
        Decodes the data from the specified encoding and convert it to the string-like data type representation.

        :param data: Data to decode.
        :param encoding: Expected source encoding.
        :param binary:
            If unspecified, the string-like type will be the same as the input data.
            Otherwise, convert the decoded data to :class:`str` or :class:`bytes` accordingly.
        :return: Decoded and converted data.
        """
        data_type = type(data)
        out_type = data_type if binary is None else (bytes if binary else str)
        enc_type = ContentEncoding.get(encoding, default=ContentEncoding.UTF_8)
        dec_func = {
            (str, str, ContentEncoding.UTF_8): lambda _: _,
            (str, bytes, ContentEncoding.UTF_8): lambda s: s.encode(),
            (bytes, bytes, ContentEncoding.UTF_8): lambda _: _,
            (bytes, str, ContentEncoding.UTF_8): lambda s: s.decode(),
            (str, str, ContentEncoding.BASE16): lambda s: base64.b16decode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BASE16): lambda s: base64.b16decode(s.encode()),
            (bytes, str, ContentEncoding.BASE16): lambda s: base64.b16decode(s).decode(),
            (bytes, bytes, ContentEncoding.BASE16): lambda s: base64.b16decode(s),
            (str, str, ContentEncoding.BASE32): lambda s: base64.b32decode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BASE32): lambda s: base64.b32decode(s.encode()),
            (bytes, str, ContentEncoding.BASE32): lambda s: base64.b32decode(s).decode(),
            (bytes, bytes, ContentEncoding.BASE32): lambda s: base64.b32decode(s),
            (str, str, ContentEncoding.BASE64): lambda s: base64.b64decode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BASE64): lambda s: base64.b64decode(s.encode()),
            (bytes, str, ContentEncoding.BASE64): lambda s: base64.b64decode(s).decode(),
            (bytes, bytes, ContentEncoding.BASE64): lambda s: base64.b64decode(s),
            (str, str, ContentEncoding.BINARY): lambda s: base64.b64decode(s.encode()).decode(),
            (str, bytes, ContentEncoding.BINARY): lambda s: base64.b64decode(s.encode()),
            (bytes, str, ContentEncoding.BINARY): lambda s: base64.b64decode(s).decode(),
            (bytes, bytes, ContentEncoding.BINARY): lambda s: base64.b64decode(s),
        }
        return dec_func[(data_type, out_type, enc_type)](data)


class OutputFormat(Constants):
    """
    Renderer output formats for :term:`CLI`, `OpenAPI` and HTTP response content generation.
    """
    JSON = classproperty(fget=lambda self: "json", doc="""
    Representation as :term:`JSON` (object), which can still be manipulated in code.
    """)  # type: Literal["JSON", "json"]  # noqa: F811  # false-positive redefinition of JSON typing

    JSON_STR = classproperty(fget=lambda self: "json+str", doc="""
    Representation as :term:`JSON` content formatted as string with indentation and newlines.
    """)  # type: Literal["JSON+STR", "json+str"]

    JSON_RAW = classproperty(fget=lambda self: "json+raw", doc="""
    Representation as :term:`JSON` content formatted as raw string without any indentation or newlines.
    """)  # type: Literal["JSON+RAW", "json+raw"]

    YAML = classproperty(fget=lambda self: "yaml", doc="""
    Representation as :term:`YAML` content formatted as string with indentation and newlines.
    """)  # type: Literal["YAML", "yaml"]

    YML = classproperty(fget=lambda self: "yml", doc="""
    Alias to YAML.
    """)  # type: Literal["YML", "yml"]

    XML = classproperty(fget=lambda self: "xml", doc="""
    Representation as :term:`XML` content formatted as serialized string.
    """)  # type: Literal["XML", "xml"]

    XML_STR = classproperty(fget=lambda self: "xml+str", doc="""
    Representation as :term:`XML` content formatted as string with indentation and newlines.
    """)  # type: Literal["XML+STR", "xml+str"]

    XML_RAW = classproperty(fget=lambda self: "xml+raw", doc="""
    Representation as :term:`XML` content formatted as raw string without indentation or newlines.
    """)  # type: Literal["XML+RAW", "xml+raw"]

    TXT = classproperty(fget=lambda self: "txt", doc="""
    Representation as plain text content without any specific reformatting or validation.
    """)  # type: Literal["TXT", "txt"]

    TEXT = classproperty(fget=lambda self: "text", doc="""
    Representation as plain text content without any specific reformatting or validation.
    """)  # type: Literal["TEXT", "text"]

    HTML = classproperty(fget=lambda self: "html", doc="""
    Representation as HTML content formatted as serialized string.
    """)  # type: Literal["HTML", "html"]

    HTML_STR = classproperty(fget=lambda self: "html+str", doc="""
    Representation as HTML content formatted as string with indentation and newlines.
    """)  # type: Literal["HTML+STR", "html+str"]

    HTML_RAW = classproperty(fget=lambda self: "html+raw", doc="""
    Representation as HTML content formatted as raw string without indentation or newlines.
    """)  # type: Literal["HTML+RAW", "html+raw"]

    @classmethod
    def get(cls,                    # pylint: disable=W0221,W0237  # arguments differ/renamed
            format_or_version,      # type: Union[str, AnyOutputFormat, AnyContentType, PropertyDataTypeT]
            default=None,           # type: Optional[AnyOutputFormat]
            allow_version=True,     # type: bool
            ):                      # type: (...) ->  Union[AnyOutputFormat, PropertyDataTypeT]
        """
        Resolve the applicable output format.

        :param format_or_version:
            Either a :term:`WPS` version, a known value for a ``f``/``format`` query parameter, or an ``Accept`` header
            that can be mapped to one of the supported output formats.
        :param default:
            Default output format if none could be resolved.
            If no explicit default is specified as default in case of unresolved format, ``JSON`` is used by default.
        :param allow_version: Enable :term:`WPS` version specifiers to infer the corresponding output representation.
        :return: Resolved output format.
        """
        if allow_version and format_or_version == "1.0.0":
            return OutputFormat.XML
        if allow_version and format_or_version == "2.0.0":
            return OutputFormat.JSON
        if not isinstance(format_or_version, str):
            return default or OutputFormat.JSON
        if "/" in format_or_version:  # Media-Type to output format renderer
            format_or_version = get_extension(format_or_version, dot=False)
        return super(OutputFormat, cls).get(str(format_or_version), default=default) or OutputFormat.JSON

    @classmethod
    def convert(cls, data, to, item_root="item"):
        # type: (JSON, Union[AnyOutputFormat, AnyContentType, None], str) -> Union[str, JSON]
        """
        Converts the input data from :term:`JSON` to another known format.

        :param data: Input data to convert. Must be a literal :term:`JSON` object, not a :term:`JSON`-like string.
        :param to:
            Target format representation.
            If the output format is not :term:`JSON`, it is **ALWAYS** converted to the formatted string of the
            requested format to ensure the contents are properly represented as intended. In the case of :term:`JSON`
            as target format or unknown format, the original object is returned directly.
        :param item_root:
            When using :term:`XML` or HTML representations, defines the top-most item name.
            Unused for other representations.
        :return: Formatted output.
        """
        from weaver.utils import bytes2str

        fmt = cls.get(to)
        if fmt == OutputFormat.JSON:
            return data
        if fmt == OutputFormat.JSON_STR:
            return repr_json(data, indent=2, ensure_ascii=False)
        if fmt in [OutputFormat.JSON_RAW, OutputFormat.TEXT, OutputFormat.TXT]:
            return repr_json(data, indent=None, ensure_ascii=False)
        if fmt in [
            OutputFormat.XML, OutputFormat.XML_RAW, OutputFormat.XML_STR,
            OutputFormat.HTML, OutputFormat.HTML_RAW, OutputFormat.HTML_STR,
        ]:
            pretty = fmt in [OutputFormat.XML_STR, OutputFormat.HTML_STR]
            xml = Json2xml(data, item_wrap=True, pretty=pretty, wrapper=item_root).to_xml()
            if fmt in [OutputFormat.XML_RAW, OutputFormat.HTML_RAW]:
                xml = bytes2str(xml)
            if isinstance(xml, str):
                xml = xml.strip()
            return xml
        if fmt in [OutputFormat.YML, OutputFormat.YAML]:
            yml = yaml.safe_dump(data, indent=2, sort_keys=False, width=float("inf"))  # type: ignore
            if yml.endswith("\n...\n"):  # added when data is single literal or None instead of list/object
                yml = yml[:-4]
            return yml
        return data  # pragma: no cover  # last resort if new output format unhandled


class SchemaRole(Constants):
    JSON_SCHEMA = "https://www.w3.org/2019/wot/json-schema"


# explicit media-type to extension when not literally written in item after '/' (excluding 'x-' prefix)
_CONTENT_TYPE_EXTENSION_OVERRIDES = {
    ContentType.APP_VDN_GEOJSON: ".geojson",  # pywps 4.4 default extension without vdn prefix
    ContentType.APP_NETCDF: ".nc",
    ContentType.APP_GZIP: ".gz",
    ContentType.APP_TAR_GZ: ".tar.gz",
    ContentType.APP_YAML: ".yml",
    ContentType.IMAGE_TIFF: ".tif",  # common alternate to .tiff
    ContentType.ANY: ".*",      # any for glob
    ContentType.APP_DIR: "/",   # force href to finish with explicit '/' to mark directory
    ContentType.APP_OCTET_STREAM: ".bin",
    ContentType.APP_FORM: "",
    ContentType.MULTIPART_FORM: "",
    ContentType.IMAGE_SVG_XML: ".svg",
}
_CONTENT_TYPE_EXCLUDE = [
    ContentType.APP_OCTET_STREAM,
    ContentType.APP_FORM,
    ContentType.MULTIPART_FORM,
]
_EXTENSION_CONTENT_TYPES_OVERRIDES = {
    ".text": ContentType.TEXT_PLAIN,  # common alias to .txt, especially when using format query
    ".tiff": ContentType.IMAGE_TIFF,  # avoid defaulting to subtype geotiff
    ".yaml": ContentType.APP_YAML,    # common alternative to .yml
    ".html": ContentType.TEXT_HTML,   # missing extension, needed for 'f=html' check
    ".xsd": ContentType.APP_XML,
}
# well-known schema URI that should resolve to an alternate media-type than the auto-resolution
_CONTENT_TYPE_SCHEMA_OVERRIDES = {
    re.compile(r"https://geojson\.org/schema/.*\.json"): ContentType.APP_GEOJSON,
    re.compile(r"https?://(www.)?opengis\.net/def/glossary/term/FeatureCollection"): ContentType.APP_GEOJSON,
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
        (ctype, f".{re_ext['ext']}")
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
# - IANA contains most standard media-types, but some special/vendor-specific types are missing
#   (application/x-hdf5, application/x-netcdf, etc.).
# - EDAM contains many field-specific schemas, but don't have an implicit URL definition (uses 'format_<id>' instead).
# - OpenGIS contains many OGC/Geospatial Media-Types and glossary of related terms, but since it includes many items
#   that are not necessarily Media-Types, URI resolutions are not attempted at random to avoid invalid references.
# search:
#   - IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
#   - EDAM-classes: http://bioportal.bioontology.org/ontologies/EDAM/?p=classes (section 'Format')
#   - EDAM-browser: https://ifb-elixirfr.github.io/edam-browser/
#   - OpenGIS vocabulary: https://defs.opengis.net/vocprez/object?uri=http://www.opengis.net/def/glossary
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
# types to enforce to IANA in case another equivalent is known in other following mappings
# duplicates in other mappings are left defined in case they are employed by a user to ensure their detection
# but prefer the IANA resolution with is the primary reference for Media-Types
IANA_MAPPING = {
    ContentType.APP_JSON: ContentType.APP_JSON,
    # CWL now has an official IANA definition:
    # https://www.iana.org/assignments/media-types/application/cwl
    ContentType.APP_CWL: ContentType.APP_CWL,
    ContentType.APP_CWL_JSON: ContentType.APP_CWL,
    ContentType.APP_CWL_YAML: ContentType.APP_CWL,
    ContentType.APP_CWL_X: ContentType.APP_CWL,
}
EDAM_NAMESPACE = "edam"
EDAM_NAMESPACE_URL = "http://edamontology.org/"
EDAM_NAMESPACE_DEFINITION = {EDAM_NAMESPACE: EDAM_NAMESPACE_URL}
EDAM_SCHEMA = "http://edamontology.org/EDAM_1.24.owl"
EDAM_MAPPING = {
    # preserve CWL EDAM definitions for backward compatibility in case they were used in deployed processes
    ContentType.APP_CWL: "format_3857",
    ContentType.APP_CWL_JSON: "format_3857",
    ContentType.APP_CWL_YAML: "format_3857",
    ContentType.APP_CWL_X: "format_3857",
    ContentType.IMAGE_GIF: "format_3467",
    ContentType.IMAGE_JPEG: "format_3579",
    ContentType.APP_HDF5: "format_3590",
    ContentType.APP_JSON: "format_3464",
    ContentType.APP_YAML: "format_3750",
    ContentType.TEXT_PLAIN: "format_1964",
}
# Official links to be employed in definitions must be formed as:
#   http://www.opengis.net/def/...
# But they should be redirected to full definitions as:
#   https://defs.opengis.net/vocprez/object?uri=http://www.opengis.net/def/...
# See common locations:
#   https://www.opengis.net/def/media-type
OPENGIS_NAMESPACE = "opengis"
OPENGIS_NAMESPACE_URL = "http://www.opengis.net/"
OPENGIS_NAMESPACE_DEFINITION = {OPENGIS_NAMESPACE: OPENGIS_NAMESPACE_URL}
OPENGIS_MAPPING = {}
# shorthand notation directly scoped under OGC Media-Types to allow: 'ogc:<media-type-id>'
OGC_NAMESPACE = "ogc"
OGC_NAMESPACE_URL = f"{OPENGIS_NAMESPACE_URL}def/media-type/ogc/1.0/"
OGC_NAMESPACE_DEFINITION = {OGC_NAMESPACE: OGC_NAMESPACE_URL}
OGC_MAPPING = {
    ContentType.IMAGE_GEOTIFF: "geotiff",
    ContentType.IMAGE_OGC_GEOTIFF: "geotiff",
    ContentType.IMAGE_COG: "geotiff",
    ContentType.APP_NETCDF: "netcdf",
}
FORMAT_NAMESPACE_MAPPINGS = {
    IANA_NAMESPACE: IANA_MAPPING,
    EDAM_NAMESPACE: EDAM_MAPPING,
    OGC_NAMESPACE: OGC_MAPPING,
    OPENGIS_NAMESPACE: OPENGIS_MAPPING,
}
FORMAT_NAMESPACE_DEFINITIONS = {
    **IANA_NAMESPACE_DEFINITION,
    **EDAM_NAMESPACE_DEFINITION,
    **OGC_NAMESPACE_DEFINITION,
    **OPENGIS_NAMESPACE_DEFINITION
}
FORMAT_NAMESPACE_PREFIXES = [
    f"{_ns}:" for _ns in FORMAT_NAMESPACE_DEFINITIONS
] + list(FORMAT_NAMESPACE_DEFINITIONS.values())
FORMAT_NAMESPACES = frozenset(FORMAT_NAMESPACE_DEFINITIONS)

# default format if missing (minimal requirement of one)
DEFAULT_FORMAT = Format(mime_type=ContentType.TEXT_PLAIN)
DEFAULT_FORMAT_MISSING = "__DEFAULT_FORMAT_MISSING__"
setattr(DEFAULT_FORMAT, DEFAULT_FORMAT_MISSING, True)


@cache
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


@cache
def get_format(media_type, default=None):
    # type: (str, Optional[str]) -> Optional[Format]
    """
    Obtains a :class:`Format` with predefined extension and encoding details from known media-types.
    """
    fmt = _CONTENT_TYPE_FORMAT_MAPPING.get(media_type)
    if fmt is not None:
        return fmt
    if default is not None:
        ctype = default
    else:
        ctype = clean_media_type_format(media_type, strip_parameters=True)
    if not ctype:
        return None
    ext = get_extension(ctype)
    if ctype.startswith("http") and ctype.endswith(ext.strip(".")):
        for uri, typ in _CONTENT_TYPE_SCHEMA_OVERRIDES.items():
            if re.match(uri, ctype):
                schema_ctype = typ
                break
        else:
            schema_ctype = get_content_type(os.path.splitext(ctype)[-1], default=DEFAULT_FORMAT.mime_type)
        schema_ext = get_extension(schema_ctype)
        fmt = Format(schema_ctype, extension=schema_ext, schema=ctype)
    else:
        fmt = Format(ctype, extension=ext)
    return fmt


@cache
def get_extension(media_type, dot=True):
    # type: (str, bool) -> str
    """
    Retrieves the extension corresponding to :paramref:`media_type` if explicitly defined, or by parsing it.
    """
    def _handle_dot(_ext):
        # type: (str) -> str
        if dot and not _ext.startswith(".") and _ext:  # don't add for empty extension
            return f".{_ext}"
        if not dot and _ext.startswith("."):
            return _ext[1:]
        return _ext

    fmt = _CONTENT_TYPE_FORMAT_MAPPING.get(media_type)
    if fmt:
        if not fmt.extension.startswith("."):
            return fmt.extension
        return _handle_dot(fmt.extension)
    ctype = clean_media_type_format(media_type, strip_parameters=True)
    if not ctype:
        return ""
    ext_default = f"{ctype.split('/')[-1].replace('x-', '')}"
    ext = _CONTENT_TYPE_EXTENSION_MAPPING.get(ctype, ext_default)
    return _handle_dot(ext)


@cache
def get_content_type(extension, charset=None, default=None):
    # type: (str, Optional[str], Optional[str]) -> Optional[str]
    """
    Retrieves the Content-Type corresponding to the specified extension if it can be matched.

    :param extension: Extension for which to attempt finding a known Content-Type.
    :param charset: Charset to apply to the Content-Type as needed if extension was matched.
    :param default: Default Content-Type to return if no extension is matched.
    :return: Matched or default Content-Type.
    """
    ctype = None
    if not extension:
        return default
    if not extension.startswith("."):
        ctype = _EXTENSION_CONTENT_TYPES_MAPPING.get(extension)
        if not ctype:
            extension = f".{extension}"
    if not ctype:
        ctype = _EXTENSION_CONTENT_TYPES_MAPPING.get(extension)
    if not ctype:
        return default
    return add_content_type_charset(ctype, charset)


@cache
def add_content_type_charset(content_type, charset):
    # type: (Union[str, ContentType], Optional[str]) -> str
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
    if charset and any(content_type.startswith(f"{_type}/") for _type in _CONTENT_TYPE_CHAR_TYPES):
        return f"{content_type}; charset={charset}"
    return content_type


@overload
def get_cwl_file_format(media_type):
    # type: (str) -> Tuple[Optional[JSON], Optional[str]]
    ...


@overload
def get_cwl_file_format(media_type, make_reference=False, **__):
    # type: (str, Literal[False], **bool) -> Tuple[Optional[JSON], Optional[str]]
    ...


@overload
def get_cwl_file_format(media_type, make_reference=False, **__):
    # type: (str, Literal[True], **bool) -> Optional[str]
    ...


@cache
def get_cwl_file_format(media_type, make_reference=False, must_exist=True, allow_synonym=True):  # pylint: disable=R1260
    # type: (str, bool, bool, bool) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
    """
    Obtains the extended schema reference from the media-type identifier.

    Obtains the corresponding `IANA`/`EDAM`/etc. ``format`` value to be applied under a :term:`CWL` :term:`I/O` ``File``
    from the :paramref:`media_type` (``Content-Type`` header) using the first matched one.

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
          (N.B.: literal non-official media-type reference will be returned even if an official synonym exists).
        - If there is no match but ``must_exist=True`` **AND** ``allow_synonym=True``, retry the call with the
          synonym if available, or move to next step. Skip this step if ``allow_synonym=False``.
        - Returns a single ``None`` as there is no match (directly or synonym).

    Note:
        In situations where ``must_exist=False`` is used and that the namespace and/or full format URL cannot be
        resolved to an existing reference, `CWL` will raise a validation error as it cannot confirm the ``format``.
        You must therefore make sure that the returned reference (or a synonym format) really exists when using
        ``must_exist=False`` before providing it to the `CWL` I/O definition. Setting ``must_exist=False`` should be
        used only for literal string comparison or pre-processing steps to evaluate formats.

    :param media_type: Some reference, namespace'd or literal (possibly extended) media-type string.
    :param make_reference: Construct the full URL reference to the resolved media-type. Otherwise, return tuple details.
    :param must_exist:
        Return result only if it can be resolved to an official media-type (or synonym if enabled), otherwise ``None``.
        Non-official media-type can be enforced if disabled, in which case `IANA` namespace/URL is used as it preserves
        the original ``<type>/<subtype>`` format.
    :param allow_synonym:
        Allow resolution of non-official media-type to an official media-type synonym if available.
        Types defined as *synonym* have semantically the same format validation/resolution for :term:`CWL`.
        Requires ``must_exist=True``, otherwise the non-official media-type is employed directly as result.
    :returns: Resolved media-type format for `CWL` usage, accordingly to specified arguments (see description details).
    """
    def _make_if_ref(_map, _key, _fmt):
        # type: (Dict[str, str], str, str) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
        return os.path.join(_map[_key], _fmt) if make_reference else (_map, f"{_key}:{_fmt}")

    def _search_explicit_mappings(_media_type):
        # type: (str) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
        if _media_type in IANA_MAPPING:
            return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, IANA_MAPPING[_media_type])
        if _media_type in EDAM_MAPPING:  # prefer real reference if available
            return _make_if_ref(EDAM_NAMESPACE_DEFINITION, EDAM_NAMESPACE, EDAM_MAPPING[_media_type])
        if _media_type in OGC_MAPPING:  # prefer real reference if available
            return _make_if_ref(OGC_NAMESPACE_DEFINITION, OGC_NAMESPACE, OGC_MAPPING[_media_type])
        if _media_type in OPENGIS_MAPPING:  # prefer real reference if available
            return _make_if_ref(OPENGIS_NAMESPACE_DEFINITION, OPENGIS_NAMESPACE, OPENGIS_MAPPING[_media_type])
        return None

    def _request_extra_various(_media_type):
        # type: (str) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
        """
        Attempts multiple request-retry variants to be as permissive as possible to sporadic/temporary failures.
        """
        from weaver.utils import request_extra

        _media_type = clean_media_type_format(_media_type, strip_parameters=True)
        _media_type_url = f"{IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE]}{_media_type}"
        if _media_type in IANA_KNOWN_MEDIA_TYPES:  # avoid HTTP NotFound
            # prefer real reference if available
            _found = _search_explicit_mappings(_media_type)
            if _found is not None:
                return _found
            return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _media_type)

        retries = 3
        try:
            resp = request_extra("head", _media_type_url, retries=retries, timeout=2,
                                 allow_redirects=True, allowed_codes=[HTTPOk.code, HTTPNotFound.code])
            if resp.status_code == HTTPOk.code:
                return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _media_type)
        except ConnectionError as exc:
            LOGGER.debug("Format request [%s] connection error: [%s]", _media_type_url, exc)
        try:
            for _ in range(retries):
                try:
                    with urlopen(_media_type_url, timeout=2) as resp:  # nosec: B310  # IANA scheme guaranteed HTTP
                        if resp.code == HTTPOk.code:
                            return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _media_type)
                except socket.timeout:  # pragma: no cover
                    continue
                break      # pragma: no cover  # don't keep retrying if the cause is not timeout/ssl, but not resolved
        except HTTPError:  # pragma: no cover  # same as above, but for cases where the HTTP code raised directly
            pass
        except URLError as exc:
            # if error is caused by a sporadic SSL error
            # allow temporary HTTP resolution given IANA is a well-known URI
            # however, ensure the cause is in fact related to SSL, and still a resolvable referenced
            http_err = str(exc.args[0]).lower()
            http_url = f"http://{_media_type_url.split('://', 1)[-1]}"
            if (
                _media_type_url.startswith(IANA_NAMESPACE_URL) and
                any(err in http_err for err in ["ssl", "handshake"]) and
                any(err in http_err for err in ["timeout", "timed out"])
            ):
                try:
                    resp = request_extra("head", http_url, retries=0, timeout=2,
                                         allow_redirects=True, allowed_codes=[HTTPOk.code, HTTPNotFound.code])
                    if resp.status_code == HTTPOk.code:
                        return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _media_type)
                except ConnectionError:  # pragma: no cover
                    LOGGER.debug("Format request [%s] connection error: [%s] (last resort no-SSL check)", http_url, exc)
                    return None
        return None

    if not media_type:
        return None if make_reference else (None, None)
    # attempt search without cleanup in case of explicit definition that needs the extra parameters
    found = _search_explicit_mappings(media_type)
    if found:
        return found
    media_type = clean_media_type_format(media_type, strip_parameters=True)
    result = _request_extra_various(media_type)
    if result is not None:
        return result
    found = _search_explicit_mappings(media_type)
    if found:
        return found
    if not must_exist:
        return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, media_type)
    if result is None and allow_synonym and media_type in _CONTENT_TYPE_SYNONYM_MAPPING:
        media_type = _CONTENT_TYPE_SYNONYM_MAPPING.get(media_type)
        return get_cwl_file_format(media_type, make_reference=make_reference, must_exist=True, allow_synonym=False)
    return None if make_reference else (None, None)


@cache
def map_cwl_media_type(cwl_format):
    # type: (Optional[str]) -> Optional[str]
    """
    Obtains the Media-Type that corresponds to the specified :term:`CWL` ``format``.

    :param cwl_format: Long form URL or namespaced variant of a :term:`CWL` format referring to an ontology Media-Type.
    :return: Resolved Media-Type.
    """
    if not cwl_format:
        return None
    ns, ns_fmt = get_cwl_file_format(cwl_format)  # normalize and split components
    if not ns or not ns_fmt:
        ns = IANA_NAMESPACE_DEFINITION
        ns_fmt = cwl_format
    ns_name = list(ns)[0]
    ns_fmt = ns_fmt.split(":", 1)[-1] if "://" not in ns_fmt else ns_fmt
    ctype = [_ctype for _ctype, _fmt in FORMAT_NAMESPACE_MAPPINGS[ns_name].items() if _fmt == ns_fmt]
    if not ctype:
        fmt = get_format(ns_fmt)
        ctype = fmt.mime_type if fmt else None
        if not isinstance(ctype, str) or not ctype:
            return None
        for ns_prefix in FORMAT_NAMESPACE_PREFIXES:
            if ctype.startswith(ns_prefix):
                ctype = ctype.split(ns_prefix, 1)[-1]
                break
        if "/" not in ctype:
            return None
    if ctype and isinstance(ctype, list):
        ctype = ctype[0]
    return ctype


@cache
def clean_media_type_format(media_type, suffix_subtype=False, strip_parameters=False):
    # type: (str, bool, bool) -> Optional[str]
    """
    Obtains a generic media-type identifier by cleaning up any additional parameters.

    Removes any additional namespace key or URL from :paramref:`media_type` so that it corresponds to the generic
    representation (e.g.: ``application/json``) instead of the ``<namespace-name>:<format>`` mapping variant used
    in `CWL->inputs/outputs->File->format` or the complete URL reference.

    Removes any leading temporary local file prefix inserted by :term:`CWL` when resolving namespace mapping.
    This transforms ``file:///tmp/dir/path/package#application/json`` to plain ``application/json``.

    According to provided arguments, it also cleans up additional parameters or extracts sub-type suffixes.

    :param media_type:
        Media-Type, full URL to media-type or namespace-formatted string that must be cleaned up.
    :param suffix_subtype:
        Remove additional sub-type specializations details separated by ``+`` symbol such that an explicit format like
        ``application/vnd.api+json`` returns only its most basic suffix format defined as``application/json``.
    :param strip_parameters:
        Removes additional media-type parameters such that only the leading part defining the ``type/subtype`` are
        returned. For example, this will get rid of ``; charset=UTF-8`` or ``; version=4.0`` parameters.

    .. note::
        Parameters :paramref:`suffix_subtype` and :paramref:`strip_parameters` are not necessarily exclusive.
    """
    if not media_type:  # avoid mismatching empty string with random type
        return None
    # when 'format' comes from parsed CWL tool instance, the input/output record sets the value
    # using a temporary local file path after resolution against remote namespace ontology
    if media_type.startswith("file://") and "#" in media_type:
        media_type = media_type.split("#")[-1]
    if strip_parameters:
        media_type = media_type.split(";")[0]
    if suffix_subtype and "+" in media_type:
        # parameters are not necessarily stripped, need to re-append them after if any
        parts = media_type.split(";", 1)
        if len(parts) < 2:
            parts.append("")
        else:
            parts[1] = f";{parts[1]}"
        typ, sub = parts[0].split("/")
        sub = sub.split("+")[-1]
        media_type = f"{typ}/{sub}{parts[1]}"
    for v in FORMAT_NAMESPACE_DEFINITIONS.values():
        if v in media_type:
            maybe_type = media_type.replace(v, "").strip("/")
            # ignore if URI was partial prefix match, not sufficiently specific
            # allow 1 '/' for '<type>/<subtype>', or 0 for an explicit named schema reference
            if maybe_type.count("/") < 2:
                media_type = maybe_type
                break
    for v in FORMAT_NAMESPACE_DEFINITIONS:
        if media_type.startswith(f"{v}:"):
            maybe_type = media_type.replace(f"{v}:", "")
            if maybe_type.count("/") < 2:
                media_type = maybe_type
                break
    search = True
    for _map in FORMAT_NAMESPACE_MAPPINGS.values():
        if not search:
            break
        for ctype, fmt in _map.items():
            if fmt.endswith(media_type):
                media_type = ctype
                search = False
                break
    return media_type


@overload
def guess_target_format(request):
    # type: (AnyRequestType) -> ContentType
    ...


@overload
def guess_target_format(request, default):
    # type: (AnyRequestType, Optional[Union[ContentType, str]]) -> ContentType
    ...


@overload
def guess_target_format(request, return_source, override_user_agent):
    # type: (AnyRequestType, Literal[True], bool) -> Tuple[ContentType, FormatSource]
    ...


@overload
def guess_target_format(request, default, return_source, override_user_agent):
    # type: (AnyRequestType, Optional[Union[ContentType, str]], Literal[True], bool) -> Tuple[ContentType, FormatSource]
    ...


def guess_target_format(
    request,                        # type: AnyRequestType
    default=ContentType.APP_JSON,   # type: Optional[Union[ContentType, str]]
    return_source=False,            # type: bool
    override_user_agent=False,      # type: bool
):                                  # type: (...) -> Union[AnyContentType, Tuple[AnyContentType, FormatSource]]
    """
    Guess the best applicable response ``Content-Type`` header from the request.

    Considers the request ``Accept`` header, ``format`` query and alternatively ``f`` query to parse possible formats.
    Full Media-Type are expected in the header. Query parameters can use both the full Media-Type, or only the sub-type
    (i.e.: :term:`JSON`, :term:`XML`, etc.), with case-insensitive names.

    Defaults to :py:data:`ContentType.APP_JSON` if none was specified as :paramref:`default` explicitly and that no
    ``Accept` header or ``format``/``f`` queries were provided. Otherwise, applies the specified :paramref:`default`
    format specifiers were not provided in the request.

    Can apply ``User-Agent`` specific logic to override automatically added ``Accept`` headers by many browsers such
    that sending requests to the :term:`API` using them will not automatically default back to typical :term:`XML` or
    :term:`HTML` representations. If browsers are used to send requests, but that ``format``/``f`` queries are used
    directly in the URL, those will be applied since this is a very intuitive (and easier) approach to request different
    formats when using browsers. Option :paramref:`override_user_agent` must be enabled to apply this behavior.

    When ``User-Agent`` clients are identified as another source, such as sending requests from a server or from code,
    both headers and query parameters are applied directly without question.

    :returns: Matched media-type or default, and optionally, the source of resolution.
    """
    from weaver.utils import get_header

    format_query = request.params.get("format") or request.params.get("f")
    format_source = "default"  # type: FormatSource
    content_type = None  # type: Optional[str]
    if format_query:
        content_type = OutputFormat.get(format_query, default=None, allow_version=False)
        if content_type:
            content_type = get_content_type(content_type)
            format_source = "query"
    if not content_type:
        content_type = get_header("accept", request.headers, default=None)
        if content_type:
            format_source = "header"
        else:
            content_type = default or ""
        for ctype in content_type.split(","):
            ctype = clean_media_type_format(ctype, suffix_subtype=True, strip_parameters=True)
            if override_user_agent and (ctype != default or not default):
                # Because most browsers enforce a 'visual rendering' list of accept header, revert to JSON if detected.
                # Request set by another client (e.g.: using 'requests') will have full control over desired content.
                # Since browsers add '*/*' as any content fallback, use it as extra detection of undetected user-agent.
                user_agent = get_header("user-agent", request.headers)
                if (
                    user_agent
                    and any(browser in user_agent for browser in ["Mozilla", "Chrome", "Safari"])
                    or "*/*" in content_type
                ):
                    content_type = default or ContentType.APP_JSON
                    format_source = "default"
                    break
    if not content_type or content_type == ContentType.ANY:
        content_type = default or ContentType.APP_JSON
        format_source = "default"
    if return_source:
        return content_type, format_source
    return content_type


def find_supported_media_types(io_definition):
    # type: (ProcessInputOutputItem) -> Optional[List[str]]
    """
    Finds all supported media-types indicated by an :term:`I/O`.

    .. note::
        Assumes that media-types are indicated under ``formats``, which should have been obtained either by direct
        submission when using :term:`WPS` deployment, generated from ``schema`` using :term:`OGC` deployment, or using
        the nested ``format`` of ``File`` types from :term:`CWL` deployment.

    :param io_definition:
    :return: supported media-types
    """
    io_formats = io_definition.get("formats")
    if not io_formats:
        return None
    media_types = set()
    for fmt in io_formats:  # type: Dict[str, str]
        if "type" in fmt:
            media_types.add(fmt["type"])
    return list(media_types)


def json_default_handler(obj):
    # type: (Any) -> Union[JSON, str, None]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable.")


def repr_json(data, force_string=True, ensure_ascii=False, indent=2, separators=None, **kwargs):
    # type: (Any, bool, bool, Optional[int], Optional[Tuple[str, str]], **Any) -> Union[JSON, str, None]
    """
    Ensure that the input data can be serialized as JSON to return it formatted representation as such.

    If formatting as JSON fails, returns the data as string representation or ``None`` accordingly.
    """
    if data is None:
        return None
    default = kwargs.pop("default", None)
    if default is None:
        default = json_default_handler
    try:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return data.strip()  # avoid adding additional quotes
        data_str = json.dumps(
            data,
            indent=indent,
            ensure_ascii=ensure_ascii,
            separators=separators,
            default=default,
            **kwargs,
        )
        return data_str.strip() if force_string else data
    except Exception:  # noqa: W0703 # nosec: B110
        return str(data)
