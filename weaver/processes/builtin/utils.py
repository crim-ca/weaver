import os
from typing import Any
from urllib.parse import urlparse

from weaver.formats import ContentType, get_extension


def is_netcdf_url(url):
    # type: (Any) -> bool
    if not isinstance(url, str):
        return False
    if urlparse(url).scheme == "":
        return False
    return os.path.splitext(url)[-1] == get_extension(ContentType.APP_NETCDF)
