import os
from typing import TYPE_CHECKING

from pywps.inout.formats import FORMATS, Format
from pyramid.httpexceptions import HTTPOk, HTTPNotFound
from requests.exceptions import ConnectionError
from six.moves.urllib.error import HTTPError
from six.moves.urllib.request import urlopen

from weaver.utils import request_retry

if TYPE_CHECKING:
    from weaver.typedefs import JSON                # noqa: F401
    from typing import AnyStr, Dict, Tuple, Union   # noqa: F401

# Content-Types
CONTENT_TYPE_APP_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_APP_NETCDF = "application/x-netcdf"
CONTENT_TYPE_APP_GZIP = "application/gzip"
CONTENT_TYPE_APP_HDF5 = "application/x-hdf5"
CONTENT_TYPE_APP_TAR = "application/x-tar"
CONTENT_TYPE_APP_ZIP = "application/zip"
CONTENT_TYPE_TEXT_HTML = "text/html"
CONTENT_TYPE_TEXT_PLAIN = "text/plain"
CONTENT_TYPE_APP_PDF = "application/pdf"
CONTENT_TYPE_APP_JSON = "application/json"
CONTENT_TYPE_APP_GEOJSON = "application/vnd.geo+json"
CONTENT_TYPE_APP_XML = "application/xml"
CONTENT_TYPE_IMAGE_GEOTIFF = "image/tiff; subtype=geotiff"
CONTENT_TYPE_TEXT_XML = "text/xml"
CONTENT_TYPE_ANY_XML = {CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_XML}
CONTENT_TYPE_ANY = "*/*"

_CONTENT_TYPE_EXTENSION_MAPPING = {
    CONTENT_TYPE_APP_NETCDF: ".nc",
    CONTENT_TYPE_APP_GZIP: ".gz",
    CONTENT_TYPE_ANY: ".*",   # any for glob
}  # type: Dict[AnyStr, AnyStr]
# extend with all known pywps formats
_CONTENT_TYPE_FORMATS = {
    # content-types here are fully defined with extra parameters (eg: geotiff as subtype of tiff)
    fmt.mime_type: fmt for _, fmt in FORMATS._asdict().items()  # noqa: W0212
}  # type: Dict[AnyStr, Format]
_CONTENT_TYPE_EXTENSION_MAPPING.update({
    ctype: fmt.extension for ctype, fmt in _CONTENT_TYPE_FORMATS.items()  # noqa: W0212
})


def get_format(mime_type):
    # type: (AnyStr) -> Format
    """Obtains a :class:`Format` with predefined extension and encoding details from known MIME-types."""
    ctype = clean_mime_type_format(mime_type, strip_parameters=True)
    return _CONTENT_TYPE_FORMATS.get(mime_type, Format(ctype, extension=get_extension(ctype)))


def get_extension(mime_type):
    # type: (AnyStr) -> AnyStr
    """Retrieves the extension corresponding to ``mime_type`` if explicitly defined, or by simple parsing otherwise."""
    fmt = _CONTENT_TYPE_FORMATS.get(mime_type)
    if fmt:
        return fmt.extension
    ext = _CONTENT_TYPE_EXTENSION_MAPPING.get(mime_type)
    if ext:
        return ext
    ctype = clean_mime_type_format(mime_type, strip_parameters=True)
    return _CONTENT_TYPE_EXTENSION_MAPPING.get(ctype, ".{}".format(ctype.split("/")[-1].replace("x-", "")))


# Mappings for "CWL->File->Format"
# IANA contains most standard MIME-types, but might not include special (application/x-hdf5, application/x-netcdf, etc.)
# search:
#   - IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
#   - EDAM: http://bioportal.bioontology.org/ontologies/EDAM/?p=classes (section 'Format')
IANA_NAMESPACE = "iana"
IANA_NAMESPACE_DEFINITION = {IANA_NAMESPACE: "https://www.iana.org/assignments/media-types/"}
EDAM_NAMESPACE = "edam"
EDAM_NAMESPACE_DEFINITION = {EDAM_NAMESPACE: "http://edamontology.org/"}
EDAM_SCHEMA = "http://edamontology.org/EDAM_1.21.owl"
EDAM_MAPPING = {
    CONTENT_TYPE_APP_HDF5: "format_3590",
    CONTENT_TYPE_APP_JSON: "format_3464",
    CONTENT_TYPE_APP_NETCDF: "format_3650",
    CONTENT_TYPE_TEXT_PLAIN: "format_1964",
}
FORMAT_NAMESPACES = frozenset([IANA_NAMESPACE, EDAM_NAMESPACE])


def get_cwl_file_format(mime_type, make_reference=False, must_exist=False):
    # type: (AnyStr, bool, bool) -> Union[Tuple[Union[JSON, None], Union[AnyStr, None]], Union[AnyStr, None]]
    """
    Obtains the corresponding `IANA`/`EDAM` ``format`` value to be applied under a `CWL` I/O ``File`` from
    the ``mime_type`` (`Content-Type` header) using the first matched one.

    If ``make_reference=False``:
        - If there is a match, returns ``tuple({<namespace-name: namespace-url>}, <format>)``:
            1) corresponding namespace mapping to be applied under ``$namespaces`` in the `CWL`.
            2) value of ``format`` adjusted according to the namespace to be applied to ``File`` in the `CWL`.
        - If there is no match but ``must_exist=False``:
            returns a literal and non-existing definition as ``tuple({"iana": <iana-url>}, <format>)``
        - Otherwise, returns ``(None, None)``

    If ``make_reference=True``:
        - If there is a match, returns the explicit format reference as ``<namespace-url>/<format>``.
        - If there is no match but ``must_exist=False``, returns the literal reference as ``<iana-url>/<format>``.
        - Otherwise, returns a single ``None``.

    Note:
        In situations where ``must_exist=False`` and the default non-existing namespace is returned, the `CWL`
        behaviour is to evaluate corresponding ``format`` for literal matching strings.
    """
    def _make_if_ref(_map, _key, _fmt):
        return os.path.join(_map[_key], _fmt) if make_reference else (_map, "{}:{}".format(_key, _fmt))

    def _request_retry_various(_mime_type):
        """
        Attempts multiple request-retry variants to be as permissive as possible to sporadic temporary failures.
        """
        _mime_type_url = "{}{}".format(IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE], _mime_type)
        try:
            resp = request_retry("get", _mime_type_url, retries=3, allowed_codes=[HTTPOk.code, HTTPNotFound.code])
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
    result = _request_retry_various(mime_type)
    if result is not None:
        return result
    if mime_type in EDAM_MAPPING:
        return _make_if_ref(EDAM_NAMESPACE_DEFINITION, EDAM_NAMESPACE, EDAM_MAPPING[mime_type])
    if not must_exist:
        return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, mime_type)
    return None if make_reference else (None, None)


def clean_mime_type_format(mime_type, base_subtype=False, strip_parameters=False):
    # type: (AnyStr, bool, bool) -> AnyStr
    """
    Removes any additional namespace key or URL from :paramref:`mime_type` so that it corresponds to the generic
    representation (e.g.: ``application/json``) instead of the ``<namespace-name>:<format>`` mapping variant used
    in `CWL->inputs/outputs->File->format` or the complete URL reference.

    According to provided arguments, it also cleans up additional parameters or extracts sub-type suffixes.

    :param mime_type:
        MIME-type string that must be cleaned up.
    :param base_subtype:
        remove additional sub-type specializations details marked by ``+`` symbol such that an explicit format like
        ``application/vnd.api+json`` returns only its base format defined as``application/json``.
    :param strip_parameters:
        removes additional MIME-type parameters such that only the leading part defining the ``type/subtype`` are
        returned. For example, this will get rid of ``; charset=UTF-8`` or ``; version=4.0`` parameters.

    .. note::
        Parameters :paramref:`base_subtype` and :paramref:`strip_parameters` are not necessarily exclusive.
    """
    if strip_parameters:
        mime_type = mime_type.split(";")[0]
    if base_subtype and "+" in mime_type:
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
