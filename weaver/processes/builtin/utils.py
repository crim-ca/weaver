import os
from urllib.parse import urlparse

import six

from weaver.formats import CONTENT_TYPE_APP_NETCDF, get_extension


def _is_netcdf_url(url):
    # type: (Any) -> bool
    if not isinstance(url, six.string_types):
        return False
    if urlparse(url).scheme == "":
        return False
    return os.path.splitext(url)[-1] == get_extension(CONTENT_TYPE_APP_NETCDF)
