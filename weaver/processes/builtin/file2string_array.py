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

PACKAGE_NAME = os.path.split(os.path.splitext(__file__)[0])[-1]

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.2"
__title__ = "File to String-Array"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative

OUTPUT_CWL_JSON = "cwl.output.json"


def process(input_file, output_dir):
    # type: (argparse.FileType, str) -> None
    LOGGER.info("Got arguments: input_file=%s output_dir=%s", input_file, output_dir)
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
