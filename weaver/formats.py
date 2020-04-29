import os
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.request import urlopen

from pyramid.httpexceptions import HTTPNotFound, HTTPOk
from pywps.inout.formats import FORMATS, Format
from requests.exceptions import ConnectionError

from weaver.utils import request_extra

if TYPE_CHECKING:
    from weaver.typedefs import JSON
    from typing import Dict, Optional, Tuple, Union

# Languages
ACCEPT_LANGUAGE_EN_CA = "en-CA"
ACCEPT_LANGUAGE_FR_CA = "fr-CA"
ACCEPT_LANGUAGE_EN_US = "en-US"

ACCEPT_LANGUAGES = frozenset([
    ACCEPT_LANGUAGE_EN_CA,
    ACCEPT_LANGUAGE_FR_CA,
    ACCEPT_LANGUAGE_EN_US,
])

# Content-Types
#   MIME-type nomenclature:
#       <type> "/" [x- | <tree> "."] <subtype> ["+" suffix] *[";" parameter=value]
CONTENT_TYPE_APP_CWL = "application/x-cwl"
CONTENT_TYPE_APP_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_APP_NETCDF = "application/x-netcdf"
CONTENT_TYPE_APP_GZIP = "application/gzip"
CONTENT_TYPE_APP_HDF5 = "application/x-hdf5"
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
CONTENT_TYPE_TEXT_XML = "text/xml"
CONTENT_TYPE_ANY_XML = {CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_XML}
CONTENT_TYPE_ANY = "*/*"

# explicit mime-type to extension when not literally written in item after '/' (excluding 'x-' prefix)
_CONTENT_TYPE_EXTENSION_MAPPING = {
    CONTENT_TYPE_APP_VDN_GEOJSON: ".geojson",  # pywps 4.4 default extension without vdn prefix
    CONTENT_TYPE_APP_NETCDF: ".nc",
    CONTENT_TYPE_APP_GZIP: ".gz",
    CONTENT_TYPE_APP_TAR_GZ: ".tar.gz",
    CONTENT_TYPE_APP_YAML: ".yml",
    CONTENT_TYPE_ANY: ".*",   # any for glob
}  # type: Dict[str, str]
# extend with all known pywps formats
_CONTENT_TYPE_FORMAT_MAPPING = {
    # content-types here are fully defined with extra parameters (e.g.: geotiff as subtype of tiff)
    fmt.mime_type: fmt for _, fmt in FORMATS._asdict().items()  # noqa: W0212
}  # type: Dict[str, Format]
_CONTENT_TYPE_EXTENSION_MAPPING.update({
    ctype: fmt.extension for ctype, fmt in _CONTENT_TYPE_FORMAT_MAPPING.items()  # noqa: W0212
})
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


def get_format(mime_type):
    # type: (str) -> Format
    """Obtains a :class:`Format` with predefined extension and encoding details from known MIME-types."""
    ctype = clean_mime_type_format(mime_type, strip_parameters=True)
    return _CONTENT_TYPE_FORMAT_MAPPING.get(mime_type, Format(ctype, extension=get_extension(ctype)))


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
    return _CONTENT_TYPE_EXTENSION_MAPPING.get(ctype, ".{}".format(ctype.split("/")[-1].replace("x-", "")))


def get_cwl_file_format(mime_type, make_reference=False, must_exist=True, allow_synonym=True):
    # type: (str, bool, bool, bool) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]
    """
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
        _mime_type_url = "{}{}".format(IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE], _mime_type)
        try:
            resp = request_extra("head", _mime_type_url, retries=3, allowed_codes=[HTTPOk.code, HTTPNotFound.code])
            if resp.status_code == HTTPOk.code:
                return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _mime_type)
        except ConnectionError:
            pass
        try:
            resp = urlopen(_mime_type_url)  # nosec: B310 # is hardcoded HTTP(S)
            if resp.code == HTTPOk.code:
                return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, _mime_type)
        except HTTPError:
            pass
        return None

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
    # type: (str, bool, bool) -> str
    """
    Removes any additional namespace key or URL from :paramref:`mime_type` so that it corresponds to the generic
    representation (e.g.: ``application/json``) instead of the ``<namespace-name>:<format>`` mapping variant used
    in `CWL->inputs/outputs->File->format` or the complete URL reference.

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
