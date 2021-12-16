#!/usr/bin/env python
__doc__ = """
Selects the single file at the provided index within an array of files.
"""

import argparse
import logging
import os
import shutil
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

PACKAGE_NAME = os.path.split(os.path.splitext(__file__)[0])[-1]

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.0"
__title__ = "File Index Selector"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative


def select(files, index, output_dir):
    # type: (List[str], int, str) -> None
    LOGGER.info("Process '%s' execution starting...", PACKAGE_NAME)
    LOGGER.debug("Process '%s' output directory: [%s].", PACKAGE_NAME, output_dir)
    try:
        if not os.path.isdir(output_dir):
            raise ValueError("Output dir [{}] does not exist.".format(output_dir))
        shutil.copy(files[index], output_dir)
    except Exception as exc:
        # log only debug for tracking, re-raise and actual error wil be logged by top process monitor
        LOGGER.debug("Process '%s' raised an exception: [%s]", PACKAGE_NAME, exc)
        raise
    LOGGER.info("Process '%s' execution completed.", PACKAGE_NAME)


def main():
    LOGGER.info("Parsing inputs of '%s' process.", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-f", "--files", type=str, help="Files from which to select.")
    parser.add_argument("-i", "--index", type=int, help="Index of the file to select.")
    parser.add_argument("-o", "--outdir", default=CUR_DIR, help="Output directory of the selected file.")
    args = parser.parse_args()
    sys.exit(select(args.files, args.index, args.outdir))


if __name__ == "__main__":
    main()
