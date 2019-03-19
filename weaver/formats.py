from typing import TYPE_CHECKING
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import HTTPError
if TYPE_CHECKING:
    from weaver.typedefs import JSON
    from typing import AnyStr, Union, Tuple

# Content-Types
CONTENT_TYPE_APP_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_APP_NETCDF = "application/x-netcdf"
CONTENT_TYPE_APP_HDF5 = "application/x-hdf5"
CONTENT_TYPE_TEXT_HTML = "text/html"
CONTENT_TYPE_TEXT_PLAIN = "text/plain"
CONTENT_TYPE_APP_JSON = "application/json"
CONTENT_TYPE_APP_XML = "application/xml"
CONTENT_TYPE_TEXT_XML = "text/xml"
CONTENT_TYPE_ANY_XML = {CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_XML}

CONTENT_TYPE_EXTENSION_MAPPING = {
    CONTENT_TYPE_APP_NETCDF: "nc",
    CONTENT_TYPE_APP_HDF5: "hdf5",
    CONTENT_TYPE_TEXT_PLAIN: "*",   # any for glob
}


def get_extension(mime_type):
    # type: (AnyStr) -> AnyStr
    """Retrieves the extension corresponding to ``mime_type`` if explicitly defined, or bt simple parsing otherwise."""
    return CONTENT_TYPE_EXTENSION_MAPPING.get(mime_type, mime_type.split('/')[-1])


# Mappings for "CWL->File->Format" (IANA corresponding Content-Type)
# search:
#   - IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
#   - EDAM: https://www.ebi.ac.uk/ols/search
# IANA contains most standard MIME-types, but might not include special (application/x-hdf5, application/x-netcdf, etc.)
IANA_NAMESPACE = {"iana": "https://www.iana.org/assignments/media-types/"}
EDAM_NAMESPACE = {"edam": "http://edamontology.org/"}
EDAM_SCHEMA = "http://edamontology.org/EDAM_1.21.owl"
EDAM_MAPPING = {
    CONTENT_TYPE_APP_HDF5: "edam:format_3590",
    CONTENT_TYPE_APP_JSON: "edam:format_3464",
    CONTENT_TYPE_APP_NETCDF: "edam:format_3650",
    CONTENT_TYPE_TEXT_PLAIN: "edam:format_1964",
}


def get_cwl_file_format(mime_type):
    # type: (AnyStr) -> Tuple[Union[JSON, None], Union[AnyStr, None]]
    """
    Obtains the corresponding IANA/EDAM ``format`` value to be applied under a CWL I/O ``File`` from the
    ``mime_type`` (`Content-Type` header) using the first matched one.

    If there is a match, returns:
        - corresponding namespace reference to be applied under ``$namespaces`` in the CWL.
        - value of ``format`` adjusted according to the namespace to be applied to ``File`` in the CWL.
    Otherwise, returns ``(None, None)``
    """
    mime_type_url = "{}{}".format(IANA_NAMESPACE["iana"], mime_type)
    # FIXME: ConnectionRefused with `requests.get`, using `urllib` instead
    try:
        resp = urlopen(mime_type_url)   # 404 on not implemented/referenced mime-type
        if resp.code == 200:
            return IANA_NAMESPACE, "iana:{}".format(mime_type)
    except HTTPError:
        pass
    if mime_type in EDAM_MAPPING:
        return EDAM_NAMESPACE, EDAM_MAPPING[mime_type]
    return None, None


def clean_mime_type_format(mime_type):
    # type: (AnyStr) -> AnyStr
    """
    Removes any additional namespace key or URL from ``mime_type`` so that it corresponds to the generic
    representation (ex: `application/json`) instead of the `CWL->File->format` variant.
    """
    for v in IANA_NAMESPACE.values() + IANA_NAMESPACE.keys() + EDAM_NAMESPACE.values():
        if v in mime_type:
            mime_type = mime_type.replace(v, "")
            break
    for v in EDAM_MAPPING.values():
        if v.endswith(mime_type):
            mime_type = [k for k in EDAM_MAPPING if v.endswith(EDAM_MAPPING[k])][0]
            break
    return mime_type
