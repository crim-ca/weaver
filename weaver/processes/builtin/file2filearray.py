"""
Transforms a CWL NetCDF file input into a NetCDF cwl output of a list of File
"""
import argparse
import logging
import os
import sys
from typing import Any, AnyStr

import six
from six.moves.urllib.parse import urlparse

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.formats import get_extension, CONTENT_TYPE_APP_NETCDF  # isort:skip # noqa: E402
from weaver.utils import fetch_file  # isort:skip # noqa: E402

PACKAGE_NAME = os.path.split(os.path.splitext(__file__)[0])[-1]

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.0"
__title__ = "NetCDF file to file array"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative


def _is_netcdf_url(url):
    # type: (Any) -> bool
    if not isinstance(url, six.string_types):
        return False
    if urlparse(url).scheme == "":
        return False
    return os.path.splitext(url)[-1] == get_extension(CONTENT_TYPE_APP_NETCDF)


def f2fa(input_file, output_dir):
    # type: (AnyStr, AnyStr) -> None
    LOGGER.info(
        "Got arguments: input_file=%s output_dir=%s", input_file, output_dir
    )
    LOGGER.info("Process '%s' execution starting...", PACKAGE_NAME)
    LOGGER.debug("Process '%s' output directory: [%s].", PACKAGE_NAME, output_dir)
    try:
        if not os.path.isdir(output_dir):
            raise ValueError("Output dir [{}] does not exist.".format(output_dir))
        fetch_file(input_file, output_dir, timeout=10, retry=3)
    except Exception as exc:
        # log only debug for tracking, re-raise and actual error wil be logged by top process monitor
        LOGGER.debug("Process '%s' raised an exception: [%s]", PACKAGE_NAME, exc)
        raise
    LOGGER.info("Process '%s' execution completed.", PACKAGE_NAME)


def main():
    LOGGER.info("Parsing inputs of '%s' process.", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", metavar="input", type=str,
                        help="NetCDF input file.")
    parser.add_argument("-o", metavar="outdir", default=CUR_DIR,
                        help="Output directory of the retrieved NetCDF file.")
    args = parser.parse_args()
    sys.exit(f2fa(args.i, args.o))


if __name__ == "__main__":
    main()
