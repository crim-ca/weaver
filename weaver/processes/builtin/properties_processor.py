#!/usr/bin/env python
"""
Generates properties contents using the specified input definitions.
"""
import argparse
import ast
import json
import logging
import os
import sys
import uuid
from typing import TYPE_CHECKING

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.formats import ContentType, get_cwl_file_format  # isort:skip # noqa: E402
from weaver.processes.builtin.utils import get_package_details  # isort:skip # noqa: E402)
from weaver.utils import Lazify, load_file, repr_json, request_extra  # isort:skip # noqa: E402

if TYPE_CHECKING:
    from typing import Dict

    from weaver.typedefs import (
        CWL_IO_ValueMap,
        JSON,
        Path,
    )
    from weaver.utils import LoggerHandler

PACKAGE_NAME, PACKAGE_BASE, PACKAGE_MODULE = get_package_details(__file__)

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(PACKAGE_MODULE)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.0"
__title__ = "Properties Processor"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative

OUTPUT_CWL_JSON = "cwl.output.json"


def compute_property(property_name, calculation, properties):
    # type: (str, str, Dict[str, JSON]) -> None

    ...  # FIXME: ast to do eval safely - TBD: what about property pointing at file?
    calc = calculation.lower()  # handle 'Min()'->'min()' - names allowed by "well-known functions"
    result = ast.literal_eval(calc)
    properties.update({property_name: result})


def process_properties(input_properties, input_values, output_dir, logger=LOGGER):
    # type: (Dict[str, str], Dict[str, JSON], Path, LoggerHandler) -> JSON
    """
    Processor of a ``properties`` definition for an input or output.

    :param input_properties:
        Properties definition submitted to the process and to be generated from input values.
    :param input_values:
        Values available for properties generation.
    :param output_dir: Directory to write the output (provided by the :term:`CWL` definition).
    :param logger: Optional logger handler to employ.
    :return: File reference containing the resolved properties.
    """
    logger.log(  # pylint: disable=E1205 # false positive
        logging.INFO,
        "Process [{}] Got arguments: input_properties={}, input_values={} output_dir=[{}]",
        PACKAGE_NAME,
        Lazify(lambda: repr_json(input_properties, indent=2)),
        Lazify(lambda: repr_json(input_values, indent=2)),
        output_dir,
    )
    os.makedirs(output_dir, exist_ok=True)

    # sort properties later if they depend on other ones, the least dependencies to be computed first
    props_deps = {prop: 0 for prop in input_properties}
    for prop, calc in input_properties.items():
        for prop_dep in props_deps:
            if prop == prop_dep:
                if prop in calc:
                    raise ValueError(f"Invalid recursive property [{prop}] references itself.")
                continue
            if prop_dep in calc:
                props_deps[prop_dep] += 1
    if not filter(lambda dep: dep[-1] == 0, props_deps.items()):
        raise ValueError("Invalid properties all depend on another one. Impossible resolution order.")
    props = sorted(
        list(input_properties.items()),
        key=lambda p: props_deps[p[0]]
    )

    # compute the properties
    properties = {}
    for prop, calc in props:
        compute_property(prop, calc, properties)

    return properties


def process_cwl(input_properties, input_values, output_dir):
    # type: (Dict[str, str], Dict[str, JSON], Path) -> CWL_IO_ValueMap
    out_props = process_properties(input_properties, input_values, output_dir)
    prop_file_path = os.path.join(output_dir, f"{uuid.uuid4()}.json")
    with open(prop_file_path, mode="w", encoding="utf-8") as prop_file:
        json.dump(out_props, prop_file, indent=2)
    out_cwl_file = {
        "class": "File",
        "path": prop_file_path,
        "format": get_cwl_file_format(ContentType.APP_JSON),
    }
    cwl_outputs = {"referenceOutput": out_cwl_file}  # output ID must match the one used in CWL definition
    cwl_out_path = os.path.join(output_dir, OUTPUT_CWL_JSON)
    with open(cwl_out_path, mode="w", encoding="utf-8") as file:
        json.dump(cwl_outputs, file)
    return cwl_outputs


def main(*args):
    # type: (*str) -> None
    LOGGER.info("Process [%s] Parsing inputs...", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-P", "--properties",
        metavar="INPUT_PROPERTIES",
        required=True,
        help="Properties definition submitted to the process and to be generated from input values.",
    )
    parser.add_argument(
        "-V", "--values",
        metavar="INPUT_VALUES",
        required=True,
        help="Values available for properties generation.",
    )
    parser.add_argument(
        "-o", "--outdir",
        metavar="OUTDIR",
        required=True,
        help="Output directory of the retrieved data.",
    )
    ns = parser.parse_args(*args)
    LOGGER.info("Process [%s] Loading properties input from file '%s'.", PACKAGE_NAME, ns.properties)
    prop_in = load_file(ns.properties)
    LOGGER.info("Process [%s] Loading values input from file '%s'.", PACKAGE_NAME, ns.values)
    val_in = load_file(ns.values)
    sys.exit(process_cwl(prop_in, val_in, ns.outdir) is not None)


if __name__ == "__main__":
    main()
