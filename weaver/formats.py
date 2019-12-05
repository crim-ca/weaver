from typing import TYPE_CHECKING
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import HTTPError
import os
if TYPE_CHECKING:
    from weaver.typedefs import JSON            # noqa: F401
    from typing import AnyStr, Tuple, Union     # noqa: F401

# Content-Types
CONTENT_TYPE_APP_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_APP_NETCDF = "application/x-netcdf"
CONTENT_TYPE_APP_GZIP = "application/gzip"
CONTENT_TYPE_APP_HDF5 = "application/x-hdf5"
CONTENT_TYPE_APP_TAR = "application/x-tar"
CONTENT_TYPE_APP_ZIP = "application/zip"
CONTENT_TYPE_TEXT_HTML = "text/html"
CONTENT_TYPE_TEXT_PLAIN = "text/plain"
CONTENT_TYPE_APP_JSON = "application/json"
CONTENT_TYPE_APP_XML = "application/xml"
CONTENT_TYPE_TEXT_XML = "text/xml"
CONTENT_TYPE_ANY_XML = {CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_XML}

_CONTENT_TYPE_EXTENSION_MAPPING = {
    CONTENT_TYPE_APP_NETCDF: "nc",
    CONTENT_TYPE_APP_GZIP: "gz",
    CONTENT_TYPE_TEXT_PLAIN: "*",   # any for glob
}


def get_extension(mime_type):
    # type: (AnyStr) -> AnyStr
    """Retrieves the extension corresponding to ``mime_type`` if explicitly defined, or by simple parsing otherwise."""
    return _CONTENT_TYPE_EXTENSION_MAPPING.get(mime_type, mime_type.split('/')[-1].replace("x-", ""))


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

    # FIXME: ConnectionRefused with `requests.get`, using `urllib` instead
    try:
        mime_type_url = "{}{}".format(IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE], mime_type)
        resp = urlopen(mime_type_url)   # 404 on not implemented/referenced mime-type
        if resp.code == 200:
            return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, mime_type)
    except HTTPError:
        pass
    if mime_type in EDAM_MAPPING:
        return _make_if_ref(EDAM_NAMESPACE_DEFINITION, EDAM_NAMESPACE, EDAM_MAPPING[mime_type])
    if not must_exist:
        return _make_if_ref(IANA_NAMESPACE_DEFINITION, IANA_NAMESPACE, mime_type)
    return None if make_reference else (None, None)


def clean_mime_type_format(mime_type):
    # type: (AnyStr) -> AnyStr
    """
    Removes any additional namespace key or URL from ``mime_type`` so that it corresponds to the generic
    representation (ex: `application/json`) instead of the ``<namespace-name>:<format>`` variant used
    in `CWL->inputs/outputs->File->format`.
    """
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
