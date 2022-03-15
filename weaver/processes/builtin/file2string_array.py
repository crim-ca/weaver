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
__version__ = "1.1"
__title__ = "File to String-Array"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative

OUTPUT_CWL_JSON = "cwl.output.json"


def main(input_file, output_dir):
    # type: (argparse.FileType, str) -> None
    LOGGER.info(
        "Got arguments: input_file=%s output_dir=%s", input_file, output_dir
    )
    output_data = {"output": [input_file]}
    json.dump(output_data, open(os.path.join(output_dir, OUTPUT_CWL_JSON), "w"))


if __name__ == "__main__":
    LOGGER.info("Parsing inputs of '%s' process.", PACKAGE_NAME)
    PARSER = argparse.ArgumentParser(description=__doc__)
    PARSER.add_argument("-i", help="CWL File")
    PARSER.add_argument(
        "-o",
        metavar="outdir",
        required=True,
        help="Output directory of the retrieved NetCDF files extracted by name from the JSON file.",
    )
    ARGS = PARSER.parse_args()
    sys.exit(main(ARGS.i, ARGS.o))
