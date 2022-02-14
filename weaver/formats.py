import logging
import os
import re
import socket
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.request import urlopen

from pyramid.httpexceptions import HTTPNotFound, HTTPOk
from pywps.inout.formats import FORMATS, Format
from requests.exceptions import ConnectionError

if TYPE_CHECKING:
    from typing import Dict, Optional, Tuple, Union

    from weaver.typedefs import JSON


# Languages
ACCEPT_LANGUAGE_EN_CA = "en-CA"
ACCEPT_LANGUAGE_FR_CA = "fr-CA"
ACCEPT_LANGUAGE_EN_US = "en-US"

ACCEPT_LANGUAGES = frozenset([
    ACCEPT_LANGUAGE_EN_US,  # place first to match default of PyWPS and most existing remote servers
    ACCEPT_LANGUAGE_EN_CA,
    ACCEPT_LANGUAGE_FR_CA,
])

# Content-Types
#   MIME-type nomenclature:
#       <type> "/" [x- | <tree> "."] <subtype> ["+" suffix] *[";" parameter=value]
CONTENT_TYPE_APP_CWL = "application/x-cwl"
CONTENT_TYPE_APP_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_APP_NETCDF = "application/x-netcdf"
CONTENT_TYPE_APP_GZIP = "application/gzip"
CONTENT_TYPE_APP_HDF5 = "application/x-hdf5"
CONTENT_TYPE_APP_OCTET_STREAM = "application/octet-stream"
CONTENT_TYPE_APP_TAR = "application/x-tar"          # map to existing gzip for CWL
CONTENT_TYPE_APP_TAR_GZ = "application/tar+gzip"    # map to existing gzip for CWL
CONTENT_TYPE_APP_YAML = "application/x-yaml"
CONTENT_TYPE_APP_ZIP = "application/zip"
CONTENT_TYPE_TEXT_HTML = "text/html"
CONTENT_TYPE_TEXT_PLAIN = "text/plain"
CONTENT_TYPE_APP_PDF = "application/pdf"
CONTENT_TYPE_APP_JSON = "application/json"
CONTENT_TYPE_APP_GEOJSON = "application/geo+json"
CONTENT_TYPE_APP_VDN_GEOJSON = "application/vnd.geo+json"
CONTENT_TYPE_APP_XML = "application/xml"
CONTENT_TYPE_IMAGE_GEOTIFF = "image/tiff; subtype=geotiff"
CONTENT_TYPE_IMAGE_JPEG = "image/jpeg"
CONTENT_TYPE_IMAGE_PNG = "image/png"
CONTENT_TYPE_IMAGE_TIFF = "image/tiff"
CONTENT_TYPE_MULTI_PART_FORM = "multipart/form-data"
CONTENT_TYPE_TEXT_XML = "text/xml"
CONTENT_TYPE_ANY_XML = {CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_XML}
CONTENT_TYPE_ANY = "*/*"

# explicit mime-type to extension when not literally written in item after '/' (excluding 'x-' prefix)
_CONTENT_TYPE_EXTENSION_OVERRIDES = {
    CONTENT_TYPE_APP_VDN_GEOJSON: ".geojson",  # pywps 4.4 default extension without vdn prefix
    CONTENT_TYPE_APP_NETCDF: ".nc",
    CONTENT_TYPE_APP_GZIP: ".gz",
    CONTENT_TYPE_APP_TAR_GZ: ".tar.gz",
    CONTENT_TYPE_APP_YAML: ".yml",
    CONTENT_TYPE_IMAGE_TIFF: ".tif",  # common alternate to .tiff
    CONTENT_TYPE_ANY: ".*",   # any for glob
    CONTENT_TYPE_APP_OCTET_STREAM: "",
    CONTENT_TYPE_APP_FORM: "",
    CONTENT_TYPE_MULTI_PART_FORM: "",
}
_CONTENT_TYPE_EXCLUDE = [
    CONTENT_TYPE_APP_OCTET_STREAM,
    CONTENT_TYPE_APP_FORM,
    CONTENT_TYPE_MULTI_PART_FORM,
]
_EXTENSION_CONTENT_TYPES_OVERRIDES = {
    ".tiff": CONTENT_TYPE_IMAGE_TIFF,  # avoid defaulting to subtype geotiff
    ".yaml": CONTENT_TYPE_APP_YAML,  # common alternative to .yml
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
    if name.startswith("CONTENT_TYPE_")
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
    CONTENT_TYPE_APP_TAR: CONTENT_TYPE_APP_GZIP,
    CONTENT_TYPE_APP_TAR_GZ: CONTENT_TYPE_APP_GZIP,
}

# Mappings for "CWL->File->Format"
# IANA contains most standard MIME-types, but might not include special (application/x-hdf5, application/x-netcdf, etc.)
# EDAM contains many field-specific schemas, but don't have an implicit URL definition (uses 'format_<id>' instead)
# search:
#   - IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
#   - EDAM-classes: http://bioportal.bioontology.org/ontologies/EDAM/?p=classes (section 'Format')
#   - EDAM-browser: https://ifb-elixirfr.github.io/edam-browser/
IANA_NAMESPACE = "iana"
IANA_NAMESPACE_DEFINITION = {IANA_NAMESPACE: "https://www.iana.org/assignments/media-types/"}
EDAM_NAMESPACE = "edam"
EDAM_NAMESPACE_DEFINITION = {EDAM_NAMESPACE: "http://edamontology.org/"}
EDAM_SCHEMA = "http://edamontology.org/EDAM_1.24.owl"
EDAM_MAPPING = {
    CONTENT_TYPE_APP_CWL: "format_3857",
    CONTENT_TYPE_APP_HDF5: "format_3590",
    CONTENT_TYPE_APP_JSON: "format_3464",
    CONTENT_TYPE_APP_NETCDF: "format_3650",
    CONTENT_TYPE_APP_YAML: "format_3750",
    CONTENT_TYPE_TEXT_PLAIN: "format_1964",
}
FORMAT_NAMESPACES = frozenset([IANA_NAMESPACE, EDAM_NAMESPACE])

# renderers output formats for OpenAPI generation
WPS_VERSION_100 = "1.0.0"
WPS_VERSION_200 = "2.0.0"
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_XML = "xml"
OUTPUT_FORMATS = {
    WPS_VERSION_100: OUTPUT_FORMAT_XML,
    WPS_VERSION_200: OUTPUT_FORMAT_JSON,
    CONTENT_TYPE_APP_XML: OUTPUT_FORMAT_XML,
    CONTENT_TYPE_APP_JSON: OUTPUT_FORMAT_JSON,
}

LOGGER = logging.getLogger(__name__)


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


def get_extension(mime_type):
    # type: (str) -> str
    """
    Retrieves the extension corresponding to :paramref:`mime_type` if explicitly defined, or by parsing it.
    """
    fmt = _CONTENT_TYPE_FORMAT_MAPPING.get(mime_type)
    if fmt:
        return fmt.extension
    ext = _CONTENT_TYPE_EXTENSION_MAPPING.get(mime_type)
    if ext:
        return ext
    ctype = clean_mime_type_format(mime_type, strip_parameters=True)
    if not ctype:
        return ""
    return _CONTENT_TYPE_EXTENSION_MAPPING.get(ctype, ".{}".format(ctype.split("/")[-1].replace("x-", "")))


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
    # no parameters in Media-Type, but explicit Content-Type with charset could exist as needed
    if charset and "charset=" in ctype:
        return re.sub(r"charset\=[A-Za-z0-9\_\-]+", f"charset={charset}", ctype)
    # make sure to never include by mistake if the represented type cannot be characters
    if charset and any(ctype.startswith(_type + "/") for _type in _CONTENT_TYPE_CHAR_TYPES):
        return f"{ctype}; charset={charset}"
    return ctype


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
        return os.path.join(_map[_key], _fmt) if make_reference else (_map, "{}:{}".format(_key, _fmt))

    def _request_extra_various(_mime_type):
        """
        Attempts multiple request-retry variants to be as permissive as possible to sporadic/temporary failures.
        """
        from weaver.utils import request_extra

        _mime_type_url = "{}{}".format(IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE], _mime_type)
        retries = 3
        try:
            resp = request_extra("head", _mime_type_url, retries=retries, timeout=2,
                                 allow_redirects=True, allowed_codes=[HTTPOk.code, HTTPNotFound.code])
            if resp.status_code == HTTPOk.code:
                return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _mime_type)
        except ConnectionError as exc:
            LOGGER.debug("Format request [%s] connection error: [%s]", _mime_type_url, exc)
        try:
            for i in range(retries):
                try:
                    resp = urlopen(_mime_type_url, timeout=2)  # nosec: B310 # is hardcoded HTTP(S)
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
            parts[1] = ";{}".format(parts[1])
        typ, sub = parts[0].split("/")
        sub = sub.split("+")[-1]
        mime_type = "{}/{}{}".format(typ, sub, parts[1])
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
