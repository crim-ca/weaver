#!/usr/bin/env python
__doc__ = """
Extracts and fetches NetCDF files from a JSON file containing an URL string array,
and provides them on the output directory.
"""
import argparse
import json
import logging
import os
import sys
from tempfile import TemporaryDirectory

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.processes.builtin.utils import is_netcdf_url  # isort:skip # noqa: E402
from weaver.utils import fetch_file  # isort:skip # noqa: E402

PACKAGE_NAME = os.path.split(os.path.splitext(__file__)[0])[-1]

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(PACKAGE_NAME)
_handler = logging.StreamHandler(sys.stdout)  # noqa
_handler.setFormatter(logging.Formatter(fmt="[%(name)s] %(levelname)-8s %(message)s"))
LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.DEBUG)

# process details
__version__ = "2.2"
__title__ = "JSON array to NetCDF"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative


def j2n(json_reference, output_dir):
    # type: (str, str) -> None
    LOGGER.info("Process '%s' execution starting...", PACKAGE_NAME)
    LOGGER.debug("Process '%s' output directory: [%s].", PACKAGE_NAME, output_dir)
    try:
        if not os.path.isdir(output_dir):
            raise ValueError(f"Output dir [{output_dir}] does not exist.")
        with TemporaryDirectory(prefix=f"wps_process_{PACKAGE_NAME}_") as tmp_dir:
            LOGGER.debug("Fetching JSON file: [%s]", json_reference)
            json_path = fetch_file(json_reference, tmp_dir, timeout=10, retry=3)
            LOGGER.debug("Reading JSON file: [%s]", json_path)
            with open(json_path, mode="r", encoding="utf-8") as json_file:
                json_content = json.load(json_file)
            if not isinstance(json_content, list) or any(not is_netcdf_url(f) for f in json_content):
                LOGGER.error("Invalid JSON: [%s]", json_content)
                raise ValueError("Invalid JSON file format, expected a plain array of NetCDF file URL strings.")
            LOGGER.debug("Parsing JSON file references.")
            for file_url in json_content:
                LOGGER.debug("Fetching NetCDF reference from JSON file: [%s]", file_url)
                fetched_nc = fetch_file(file_url, output_dir, timeout=10, retry=3)
                LOGGER.debug("Fetched NetCDF output location: [%s]", fetched_nc)
    except Exception as exc:
        LOGGER.error("Process '%s' raised an exception: [%s]", PACKAGE_NAME, exc)
        raise
    LOGGER.info("Process '%s' execution completed.", PACKAGE_NAME)


def main(*args):
    # type: (*str) -> None
    LOGGER.info("Parsing inputs of '%s' process.", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", metavar="json", type=str,
                        help="JSON file to be parsed for NetCDF file names.")
    parser.add_argument("-o", metavar="outdir", default=CUR_DIR,
                        help="Output directory of the retrieved NetCDF files extracted by name from the JSON file.")
    ns = parser.parse_args(*args)
    sys.exit(j2n(ns.i, ns.o))


if __name__ == "__main__":
    main()
