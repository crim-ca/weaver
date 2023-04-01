import os
from typing import Any
from urllib.parse import urlparse

from weaver.formats import ContentType, get_extension


def is_netcdf_url(url):
    # type: (Any) -> bool
    """
    Validates that the reference is a remote NetCDF file reference.
    """
    try:
        validate_file_reference(url)
    except (TypeError, ValueError):
        return False
    return os.path.splitext(url)[-1] == get_extension(ContentType.APP_NETCDF)


def validate_file_reference(url):
    # type: (str) -> None
    """
    Ensures that the provided reference points to a valide remote file or a temporary :term:`CWL` intermediate file.

    In order to avoid bypassing security validation of server file access between jobs, remote locations must be
    enforced. However, :term:`CWL` temporary files must be allowed through for intermediate locations passed around
    between :term:`Workflow` steps.
    """
    if not isinstance(url, str):
        raise TypeError(f"Not a valid URL: [{url!s}]")
    if url.endswith("/"):
        raise ValueError(f"Not a valid file URL reference [{url}]. Directory not supported.")
    cwl_files = [
        "file:///tmp/cwltool_out_",
        "file:///tmp/cwltool_tmp_",
        "/tmp/cwltool_out_",
        "/tmp/cwltool_tmp_",
    ]
    if any(url.startswith(path) for path in cwl_files):
        return
    if urlparse(url).scheme not in ["http", "https", "s3"]:
        raise ValueError(f"Not a valid file URL reference [{url}]. Scheme not supported.")
