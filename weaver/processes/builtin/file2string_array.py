#!/usr/bin/env python
"""
Transforms a file input into JSON file containing an array of file references as value.
"""
import argparse
import json
import logging
import os
import sys

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.processes.builtin.utils import get_package_details, validate_reference  # isort:skip # noqa: E402

PACKAGE_NAME, PACKAGE_BASE, PACKAGE_MODULE = get_package_details(__file__)

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(PACKAGE_MODULE)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.3"
__title__ = "File to String-Array"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative

OUTPUT_CWL_JSON = "cwl.output.json"


def process(input_file, output_dir):
    # type: (str, str) -> None
    LOGGER.info("Got arguments: input_file=%s output_dir=%s", input_file, output_dir)
    validate_reference(input_file, is_file=True)
    output_data = {"output": [input_file]}
    with open(os.path.join(output_dir, OUTPUT_CWL_JSON), mode="w", encoding="utf-8") as file:
        return json.dump(output_data, file)


def main(*args):
    # type: (*str) -> None
    LOGGER.info("Parsing inputs of '%s' process.", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", help="CWL File")
    parser.add_argument(
        "-o",
        metavar="outdir",
        required=True,
        help="Output directory of the retrieved NetCDF files extracted by name from the JSON file.",
    )
    ns = parser.parse_args(*args)
    sys.exit(process(ns.i, ns.o))


if __name__ == "__main__":
    main()
