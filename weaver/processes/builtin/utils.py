import os
import tempfile
from typing import Any
from urllib.parse import urlparse

from weaver.formats import ContentType, get_extension


def is_netcdf_url(url):
    # type: (Any) -> bool
    """
    Validates that the reference is a remote NetCDF file reference.
    """
    try:
        validate_reference(url, is_file=True)
    except (TypeError, ValueError):
        return False
    return os.path.splitext(url)[-1] == get_extension(ContentType.APP_NETCDF)


def validate_reference(url, is_file):
    # type: (str, bool) -> None
    """
    Ensures that the provided reference points to a valid remote file or a temporary intermediate file.

    In order to avoid bypassing security validation of server file access between jobs, remote locations must be
    enforced. However, :term:`CWL` temporary files must be allowed through for intermediate locations passed around
    between :term:`Workflow` steps or employed as temporary writing locations for file extraction purposes.
    """
    if not isinstance(url, str):
        raise TypeError(f"Not a valid URL: [{url!s}]")
    if (is_file and url.endswith("/")) or (not is_file and not url.endswith("/")):
        dir_msg = "not supported" if is_file else "required"
        raise ValueError(f"Not a valid file URL reference [{url}]. Directory path {dir_msg}.")
    # When in a CWL step, tempdir will return the `/tmp/cwltool_tmp_...' path (since enforced by the tool).
    # When executed in other situations, it will map to the environment variable or platform-specific tmp path.
    # Although CWL will set TMPDIR for the current step, the source file could be coming from a previous step.
    # Therefore, the random part of the path after 'cwltool_tmp_'/'cwltool_out_' could differ from the current ones.
    tmp_dir = tempfile.gettempdir()
    tmp_paths = [
        f"file://{tmp_dir}/",
        f"{tmp_dir}/",
        "file:///tmp/cwltool_out_",
        "file:///tmp/cwltool_tmp_",
        "/tmp/cwltool_out_",  # nosec: B108
        "/tmp/cwltool_tmp_",  # nosec: B108
    ]
    if any(url.startswith(path) for path in tmp_paths):
        return
    if urlparse(url).scheme not in ["http", "https", "s3"]:
        raise ValueError(f"Not a valid file URL reference [{url}]. Scheme not supported.")
