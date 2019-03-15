__doc__ = """
Extracts and fetches NetCDF files from a JSON file containing an URL string array,
and provides them on the output directory.
"""
from six.moves.urllib.parse import urlparse
from typing import AnyStr
import requests
import argparse
import json
import six
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
from weaver.formats import CONTENT_TYPE_EXTENSION_MAPPING, CONTENT_TYPE_APP_NETCDF  # noqa


def _is_netcdf_url(url):
    # type: (AnyStr) -> bool
    return urlparse(url).scheme != "" and \
           os.path.splitext(url)[-1].replace('.', '') == CONTENT_TYPE_EXTENSION_MAPPING[CONTENT_TYPE_APP_NETCDF]


def j2n(json_file, output_dir):
    # type: (AnyStr, AnyStr) -> None
    if not os.path.isdir(output_dir):
        raise ValueError("Output dir [{}] does not exist.".format(output_dir))
    with open(json_file, 'r') as f:
        json_content = json.load(f)
    if not isinstance(json_content, list) or \
            any(not isinstance(f, six.string_types) or not _is_netcdf_url(f) for f in json_content):
        raise ValueError("Invalid JSON file format, expected a plain array of NetCDF file URL strings.")
    for file_url in json_content:
        file_name = os.path.split(file_url)[-1]
        file_path = os.path.join(output_dir, file_name)
        with open(file_path, 'wb') as f:
            r = requests.get(file_url)
            r.raise_for_status()
            f.write(r.content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", metavar="json", type=argparse.FileType('r'),
                        help="JSON file to be parsed for NetCDF file names.")
    parser.add_argument("output_dir", metavar="outdir",
                        help="Output directory of the retrieved NetCDF files extracted by name from the JSON file.")
    args = parser.parse_args()
    sys.exit(j2n(args.json, args.outdir))
