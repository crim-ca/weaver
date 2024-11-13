#!/usr/bin/env python
"""
Generates properties contents using the specified input definitions.
"""
import argparse
import functools
import json
import logging
import os
import sys
import uuid
from typing import TYPE_CHECKING

from pyparsing import (
    Combine,
    Literal,
    OpAssoc,
    ParserElement,
    Word,
    ZeroOrMore,
    alphanums,
    alphas,
    infix_notation,
    nums,
    one_of
)

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.formats import ContentType, get_cwl_file_format  # isort:skip # noqa: E402
from weaver.processes.builtin.utils import get_package_details  # isort:skip # noqa: E402)
from weaver.utils import Lazify, load_file, repr_json  # isort:skip # noqa: E402

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, TypeAlias

    from weaver.typedefs import (
        CWL_IO_ValueMap,
        FieldModifierFilterCRS,
        FieldModifierFilterExpression,
        FieldModifierFilterLang,
        FieldModifierProperties,
        FieldModifierSortBy,
        JSON,
        Number,
        Path
    )
    from weaver.utils import LoggerHandler

    PropertyGetter: TypeAlias = Callable[[object, str], Any]
    PropertySetter: TypeAlias = Callable[[object, str, Any], None]

PACKAGE_NAME, PACKAGE_BASE, PACKAGE_MODULE = get_package_details(__file__)

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(PACKAGE_MODULE)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.0"
__title__ = "Field Modifier Processor"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative

OUTPUT_CWL_JSON = "cwl.output.json"


@functools.lru_cache(1024)
def create_expression_parser():
    # type: () -> ParserElement
    """
    Creates a parser that can safely evaluate the underlying arithmetic expression with variable substitutions.

    .. seealso::
        A mixture of the following examples serve as reference for the expression implementation:

        - https://github.com/pyparsing/pyparsing/blob/master/examples/simpleArith.py
        - https://github.com/pyparsing/pyparsing/blob/master/examples/eval_arith.py
        - https://github.com/pyparsing/pyparsing/blob/master/examples/excel_expr.py
    """

    ParserElement.enablePackrat()

    class EvalConstant:
        """
        Class to evaluate a parsed constant or variable.
        """
        def __init__(self, tokens):
            self.value = tokens[0]

        def eval(self, variables, getter):
            # type: (Dict[str, Number], PropertyGetter) -> Number
            if self.value in variables:
                return getter(variables, self.value)
            else:
                return float(self.value)

    class EvalSignOp:
        """
        Class to evaluate expressions with a leading ``+`` or ``-`` sign.
        """

        def __init__(self, tokens):
            self.sign, self.value = tokens[0]

        def eval(self, variables, getter):
            # type: (Dict[str, Number], PropertyGetter) -> Number
            mult = {"+": 1, "-": -1}[self.sign]
            return mult * self.value.eval(variables, getter)

    def operator_operands(tokens):
        """
        Generator to extract operators and operands in pairs.
        """
        it = iter(tokens)
        while 1:
            try:
                yield next(it), next(it)
            except StopIteration:
                break

    class EvalPowerOp:
        """
        Class to evaluate power expressions.
        """

        def __init__(self, tokens):
            self.value = tokens[0]

        def eval(self, variables, getter):
            # type: (Dict[str, Number], PropertyGetter) -> Number
            res = self.value[-1].eval(variables, getter)
            for val in self.value[-3::-2]:
                res = val.eval(variables, getter) ** res
            return res

    class EvalMultOp:
        """
        Class to evaluate multiplication and division expressions.
        """

        def __init__(self, tokens):
            self.value = tokens[0]

        def eval(self, variables, getter):
            # type: (Dict[str, Number], PropertyGetter) -> Number
            prod = self.value[0].eval(variables, getter)
            for op, val in operator_operands(self.value[1:]):
                if op == "*":
                    prod *= val.eval(variables, getter)
                if op == "/":
                    prod /= val.eval(variables, getter)
            return prod

    class EvalAddOp:
        """
        Class to evaluate addition and subtraction expressions.
        """

        def __init__(self, tokens):
            self.value = tokens[0]

        def eval(self, variables, getter):
            # type: (Dict[str, Number], PropertyGetter) -> Number
            _sum = self.value[0].eval(variables, getter)
            for op, val in operator_operands(self.value[1:]):
                if op == "+":
                    _sum += val.eval(variables, getter)
                if op == "-":
                    _sum -= val.eval(variables, getter)
            return _sum

    class EvalComparisonOp:
        """
        Class to evaluate comparison expressions.
        """
        opMap = {
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "!=": lambda a, b: a != b,
            "=": lambda a, b: a == b,
            "LT": lambda a, b: a < b,
            "LE": lambda a, b: a <= b,
            "GT": lambda a, b: a > b,
            "GE": lambda a, b: a >= b,
            "NE": lambda a, b: a != b,
            "EQ": lambda a, b: a == b,
            "<>": lambda a, b: a != b,
        }

        def __init__(self, tokens):
            self.value = tokens[0]

        def eval(self, variables, getter):
            # type: (Dict[str, Number], PropertyGetter) -> Number
            val1 = self.value[0].eval(variables, getter)
            for op, val in operator_operands(self.value[1:]):
                fn = EvalComparisonOp.opMap[op]
                val2 = val.eval(variables, getter)
                if not fn(val1, val2):
                    break
                val1 = val2
            else:
                return True
            return False

    # define the parser
    integer = Word(nums)
    real = Combine(Word(nums) + "." + Word(nums))
    ident = Word(alphas, alphanums + "_", min=1)
    variable = Combine(ident + ZeroOrMore((Literal(":") | Literal(".")) + ident))
    operand = real | integer | variable

    sign_op = one_of("+ -")
    mult_op = one_of("* /")
    plus_op = one_of("+ -")
    exp_op = one_of("** ^")

    # use parse actions to attach EvalXXX constructors to sub-expressions
    operand.setParseAction(EvalConstant)
    arith_expr = infix_notation(
        operand,
        [
            (sign_op, 1, OpAssoc.RIGHT, EvalSignOp),
            (exp_op, 2, OpAssoc.LEFT, EvalPowerOp),
            (mult_op, 2, OpAssoc.LEFT, EvalMultOp),
            (plus_op, 2, OpAssoc.LEFT, EvalAddOp),
        ],
    )

    comparison_op = one_of("< <= > >= != = <> LT GT LE GE EQ NE")
    comp_expr = infix_notation(
        arith_expr,
        [
            (comparison_op, 2, OpAssoc.LEFT, EvalComparisonOp),
        ],
    )
    return comp_expr


def evaluate_property(
    properties,             # type: Dict[str, JSON]
    property_name,          # type: str
    property_expression,    # type: str
    property_getter=None,   # type: PropertyGetter
    property_setter=None,   # type: PropertySetter
):                          # type: (...) -> None
    """
    Evaluates the applicable property expression with variable retrieval and insertion in the destination object.

    :param properties: Mapping of available property variables and expressions.
    :param property_name: Target property to evaluate.
    :param property_expression: Calculation to be evaluated for the property, possibly referring to other properties.
    :param property_getter: Function that knows how to retrieve a variable property from the properties' destination.
    :param property_setter: Function that knows how to insert the evaluated property into the properties' destination.
    """
    property_getter = property_getter or dict.__getitem__
    property_setter = property_setter or dict.__setitem__

    ...  # FIXME: ast to do eval safely - TBD: what about property pointing at file?
    expr = create_expression_parser()
    result = expr.parse_string(property_expression)[0].eval(properties, getter=property_getter)
    property_setter(properties, property_name, result)


def process_field_modifiers(
    values,                 # type: Dict[str, JSON]
    *,                      # force named keyword arguments after
    filter_expr=None,       # type: FieldModifierFilterExpression,
    filter_crs=None,        # type: FieldModifierFilterCRS,
    filter_lang=None,       # type: FieldModifierFilterLang,
    properties=None,        # type: FieldModifierProperties,
    property_getter=None,   # type: PropertyGetter
    property_setter=None,   # type: PropertySetter
    sortby=None,            # type: FieldModifierSortBy,
    logger=LOGGER,          # type: LoggerHandler
):                          # type: (...) -> JSON
    """
    Processor of field modifiers for an input or output.

    .. note::
        Modifications are applied inline to the specified :paramref:`values` to allow integration
        with various interfaces that have such expectations. For convenience, modified contents are
        also returned for interfaces that expect the result as output.

    :param values: Values available for properties modification.
    :param filter_expr: Filter expression submitted to the process and to be generated from input values.
    :param filter_lang: Filter language to interpret the filter expression.
    :param filter_crs: Filter Coordinate Reference System (CRS) to employ with the filter expression.
    :param properties: Properties definition submitted to the process and to be generated from input values.
    :param property_getter: Function that knows how to retrieve a variable property from the properties' destination.
    :param property_setter: Function that knows how to insert the evaluated property into the properties' destination.
    :param sortby: Sorting definition with relevant field names and ordering direction.
    :param logger: Optional logger handler to employ.
    :return: File reference containing the resolved properties.
    """
    logger.log(  # pylint: disable=E1205 # false positive
        logging.INFO,
        (
            "Process [%s] got arguments:\n"
            "  filter_expr=%s\n"
            "  filter_crs=%s\n"
            "  filter_lang=%s\n"
            "  properties=%s\n"
            "  sortby=%s\n"
            "  values=%s"
        ),
        PACKAGE_NAME,
        Lazify(lambda: repr_json(filter_expr, indent=2)),
        Lazify(lambda: repr_json(filter_crs, indent=2)),
        Lazify(lambda: repr_json(filter_lang, indent=2)),
        Lazify(lambda: repr_json(properties, indent=2)),
        Lazify(lambda: repr_json(sortby, indent=2)),
        Lazify(lambda: repr_json(values, indent=2)),
    )
    properties = properties or {}

    # sort properties later if they depend on other ones, the least dependencies to be computed first
    props_deps = {prop: 0 for prop in properties}
    for prop, calc in properties.items():
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
        list(properties.items()),
        key=lambda p: props_deps[p[0]]
    )

    # compute the properties
    for prop, calc in props:
        evaluate_property(properties, prop, calc, property_getter=property_getter, property_setter=property_setter)

    # FIXME: handle filtering and sorting

    return properties


def process_cwl(
    input_filter_expr,  # type: FieldModifierFilterExpression,
    input_filter_crs,   # type: FieldModifierFilterCRS,
    input_filter_lang,  # type: FieldModifierFilterLang,
    input_properties,   # type: FieldModifierProperties,
    input_sortby,       # type: FieldModifierSortBy,
    input_values,       # type: Dict[str, JSON]
    output_dir,         # type: Path
):                      # type: (...) -> CWL_IO_ValueMap
    result = process_field_modifiers(
        values=input_values,
        filter_expr=input_filter_expr,
        filter_crs=input_filter_crs,
        filter_lang=input_filter_lang,
        properties=input_properties,
        sortby=input_sortby,
    )
    file_path = os.path.join(output_dir, f"{uuid.uuid4()}.json")
    with open(file_path, mode="w", encoding="utf-8") as mod_file:
        json.dump(result, mod_file, indent=2)
    out_cwl_file = {
        "class": "File",
        "path": file_path,
        "format": get_cwl_file_format(ContentType.APP_JSON, make_reference=True),
    }
    cwl_outputs = {"referenceOutput": out_cwl_file}  # output ID must match the one used in CWL definition
    cwl_out_path = os.path.join(output_dir, OUTPUT_CWL_JSON)
    with open(cwl_out_path, mode="w", encoding="utf-8") as cwl_out_file:
        json.dump(cwl_outputs, cwl_out_file)
    return cwl_outputs


def main(*args):
    # type: (*str) -> None
    LOGGER.info("Process [%s] Parsing inputs...", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-F", "--filter",
        dest="input_filter_expr",
        metavar="INPUT_FILTER_EXPRESSION",
        required=False,
        help="Filter definition submitted to the process and to be generated from input values.",
    )
    parser.add_argument(
        "--filter-crs",
        dest="input_filter_crs",
        metavar="INPUT_FILTER_CRS",
        required=False,
        help="Filter Coordinate Reference System (CRS) to employ with the 'filter' parameter.",
    )
    parser.add_argument(
        "--filter-lang",
        dest="input_filter_lang",
        metavar="INPUT_FILTER_LANGUAGE",
        required=False,
        help="Filter language to interpret the 'filter' parameter.",
    )
    parser.add_argument(
        "-P", "--properties",
        dest="input_properties",
        metavar="INPUT_PROPERTIES",
        required=False,
        help="Properties definition submitted to the process and to be generated from input values.",
    )
    parser.add_argument(
        "-S", "--sortby", "--sortBy", "--sort-by",
        dest="input_sortby",
        metavar="INPUT_SORTBY",
        required=False,
        help="Sorting definition with relevant field names and ordering direction.",
    )
    parser.add_argument(
        "-V", "--values",
        dest="input_values",
        metavar="INPUT_VALUES",
        required=True,
        help="Values available for properties generation.",
    )
    parser.add_argument(
        "-o", "--outdir",
        dest="output_dir",
        metavar="OUTDIR",
        required=True,
        help="Output directory of the retrieved data.",
    )
    ns = parser.parse_args(*args)
    LOGGER.info("Process [%s] Loading properties input from file '%s'.", PACKAGE_NAME, ns.properties)
    prop_in = load_file(ns.input_properties)
    LOGGER.info("Process [%s] Loading values input from file '%s'.", PACKAGE_NAME, ns.values)
    val_in = load_file(ns.input_values)
    params = dict(**vars(ns))
    params.update({"input_properties": prop_in, "input_values": val_in})
    sys.exit(process_cwl(**params) is not None)


if __name__ == "__main__":
    main()
