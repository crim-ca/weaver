__doc__ = """
Extracts and fetches NetCDF files from a JSON file containing an URL string array,
and provides them on the output directory.
"""
from six.moves.urllib.parse import urlparse
from typing import AnyStr
import requests
import argparse
import logging
import shutil
import json
import six
import sys
import os
CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
from weaver.formats import CONTENT_TYPE_EXTENSION_MAPPING, CONTENT_TYPE_APP_NETCDF  # noqa

PACKAGE_NAME = os.path.split(os.path.splitext(__file__)[0])[-1]

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)


def _is_netcdf_url(url):
    # type: (AnyStr) -> bool
    return urlparse(url).scheme != "" and \
           os.path.splitext(url)[-1].replace('.', '') == CONTENT_TYPE_EXTENSION_MAPPING[CONTENT_TYPE_APP_NETCDF]


def j2n(json_file, output_dir):
    # type: (argparse.FileType, AnyStr) -> None
    LOGGER.info("Process '{}' execution starting...".format(PACKAGE_NAME))
    if not os.path.isdir(output_dir):
        raise ValueError("Output dir [{}] does not exist.".format(output_dir))
    json_content = json.load(json_file)
    if not isinstance(json_content, list) or \
            any(not isinstance(f, six.string_types) or not _is_netcdf_url(f) for f in json_content):
        LOGGER.error("Invalid JSON: [{!s}]".format(json_content))
        raise ValueError("Invalid JSON file format, expected a plain array of NetCDF file URL strings.")
    for file_url in json_content:
        file_name = os.path.split(file_url)[-1]
        file_path = os.path.join(output_dir, file_name)
        if file_url.startswith("file://"):
            shutil.copyfile(file_url[7:], file_path)
        else:
            with open(file_path, 'wb') as f:
                r = requests.get(file_url)
                r.raise_for_status()
                f.write(r.content)
    LOGGER.info("Process '{}' execution completed.".format(PACKAGE_NAME))


if __name__ == "__main__":
    LOGGER.info("Parsing inputs of '{}' process.".format(PACKAGE_NAME))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", metavar="json", type=argparse.FileType('r'),
                        help="JSON file to be parsed for NetCDF file names.")
    parser.add_argument("-o", metavar="outdir", default=CUR_DIR,
                        help="Output directory of the retrieved NetCDF files extracted by name from the JSON file.")
    args = parser.parse_args()
    sys.exit(j2n(args.i, args.o))
