__doc__ = """
Transforms a CWL file input into a cwl output of a list of strings
"""
from typing import AnyStr
import argparse
import logging
import json
import sys
import os

CUR_DIR = os.path.abspath(os.path.dirname(__file__))

PACKAGE_NAME = os.path.split(os.path.splitext(__file__)[0])[-1]

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

output_cwl_json = "cwl.output.json"


def main(input_file, output_dir):
    # type: (argparse.FileType, AnyStr) -> None
    LOGGER.info(
        "Got arguments: input_file={} output_dir={}".format(input_file, output_dir)
    )
    output_data = {"output": [input_file]}
    json.dump(output_data, open(os.path.join(output_dir, output_cwl_json), "w"))


if __name__ == "__main__":
    LOGGER.info("Parsing inputs of '{}' process.".format(PACKAGE_NAME))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", help="CWL File")
    parser.add_argument(
        "-o",
        metavar="outdir",
        required=True,
        help="Output directory of the retrieved NetCDF files extracted by name from the JSON file.",
    )
    args = parser.parse_args()
    sys.exit(main(args.i, args.o))
