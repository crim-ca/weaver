"""
Translation of parsed `CQL2` filter expressions into `MongoDB` aggregation expressions.

The resulting expression is meant to be combined with the existing search conditions of the listing operations.
"""
import re
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from pygeofilter import ast
from pygeofilter.values import Interval

from weaver.exceptions import ListingInvalidParameter

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Optional, Tuple

    from pygeofilter.ast import AstType

    from weaver.typedefs import JSON

    FilterFields = Dict[str, Tuple[Any, str]]

FIELD_SCALAR = "scalar"
FIELD_ARRAY = "array"
FIELD_DATETIME = "datetime"

_COMPARISONS = {
    ast.Equal: "$eq",
    ast.NotEqual: "$ne",
    ast.LessThan: "$lt",
    ast.LessEqual: "$lte",
    ast.GreaterThan: "$gt",
    ast.GreaterEqual: "$gte",
}


def _invalid(description, value=None):
    # type: (str, Optional[Any]) -> ListingInvalidParameter
    return ListingInvalidParameter(json={
        "description": description,
        "cause": "filter",
        "value": str(value),
    })


def _to_datetime(value):
    # type: (Any) -> datetime
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    raise _invalid("Filter value is not a valid datetime.", value)


def _like_to_regex(node):
    # type: (ast.Like) -> str
    regex = ""
    chars = iter(node.pattern)
    for char in chars:
        if char == node.escapechar:
            regex += re.escape(next(chars, ""))
        elif char == node.wildcard:
            regex += ".*"
        elif char == node.singlechar:
            regex += "."
        else:
            regex += re.escape(char)
    return f"^{regex}$"


class FilterTranslator(object):
    """
    Converts `CQL2` AST nodes to equivalent aggregation expressions using the supported queryable fields.
    """

    def __init__(self, fields, resolvers=None):
        # type: (FilterFields, Optional[Dict[str, Callable[[Any], List[Any]]]]) -> None
        """
        Initializes the translator.

        :param fields: Mapping of queryable names to their aggregation expression and kind of value.
        :param resolvers: Mapping of queryable names to a function that expands a value into all equivalent values.
        """
        self.fields = fields
        self.resolvers = resolvers or {}

    def translate(self, node):
        # type: (AstType) -> JSON
        """
        Translates the filter expression.

        :raises ListingInvalidParameter: If the expression refers to unsupported properties or operators.
        """
        if isinstance(node, ast.And):
            return {"$and": [self.translate(node.lhs), self.translate(node.rhs)]}
        if isinstance(node, ast.Or):
            return {"$or": [self.translate(node.lhs), self.translate(node.rhs)]}
        if isinstance(node, ast.Not):
            return {"$not": [self.translate(node.sub_node)]}
        if isinstance(node, ast.Include):
            return {"$literal": True}
        if isinstance(node, tuple(_COMPARISONS)):
            return self._compare(node)
        if isinstance(node, ast.Between):
            expr, kind = self._field(node.lhs)
            result = {"$and": [
                {"$gte": [expr, self._value(node.low, kind)]},
                {"$lte": [expr, self._value(node.high, kind)]},
            ]}
            return {"$not": [result]} if node.not_ else result
        if isinstance(node, ast.Like):
            expr, _ = self._field(node.lhs)
            result = {"$regexMatch": {
                "input": {"$ifNull": [expr, ""]},
                "regex": _like_to_regex(node),
                "options": "i" if node.nocase else "",
            }}
            return {"$not": [result]} if node.not_ else result
        if isinstance(node, ast.In):
            return self._contain(node)
        if isinstance(node, ast.IsNull):
            expr, _ = self._field(node.lhs)
            result = {"$eq": [{"$ifNull": [expr, None]}, None]}
            return {"$not": [result]} if node.not_ else result
        if isinstance(node, ast.TemporalPredicate):
            return self._temporal(node)
        raise _invalid("Unsupported filter operation.", type(node).__name__)

    def _field(self, node):
        # type: (AstType) -> Tuple[Any, str]
        if not isinstance(node, ast.Attribute) or node.name not in self.fields:
            raise _invalid("Unsupported filter property.", getattr(node, "name", node))
        return self.fields[node.name]

    def _values(self, name, value):
        # type: (str, Any) -> List[Any]
        resolver = self.resolvers.get(name)
        return resolver(value) if resolver else [value]

    @staticmethod
    def _value(value, kind):
        # type: (Any, str) -> Any
        if isinstance(value, ast.Node):
            raise _invalid("Filter comparison between properties is not supported.", value)
        if kind == FIELD_DATETIME:
            return _to_datetime(value)
        return value

    def _compare(self, node):
        # type: (ast.Comparison) -> JSON
        name = getattr(node.lhs, "name", None)
        expr, kind = self._field(node.lhs)
        operator = _COMPARISONS[type(node)]
        if kind == FIELD_ARRAY:
            if operator not in ["$eq", "$ne"]:
                raise _invalid("Unsupported filter operation for array property.", name)
            result = {"$in": [self._value(node.rhs, kind), {"$ifNull": [expr, []]}]}
            return result if operator == "$eq" else {"$not": [result]}
        values = self._values(name, node.rhs)
        if len(values) > 1 and operator in ["$eq", "$ne"]:
            result = {"$in": [expr, values]}
            return result if operator == "$eq" else {"$not": [result]}
        return {operator: [expr, self._value(values[0], kind)]}

    def _contain(self, node):
        # type: (ast.In) -> JSON
        name = getattr(node.lhs, "name", None)
        expr, kind = self._field(node.lhs)
        values = [value for item in node.sub_nodes for value in self._values(name, item)]
        values = [self._value(value, kind) for value in values]
        if kind == FIELD_ARRAY:
            result = {"$gt": [{"$size": {"$setIntersection": [{"$ifNull": [expr, []]}, values]}}, 0]}
        else:
            result = {"$in": [expr, values]}
        return {"$not": [result]} if node.not_ else result

    def _temporal(self, node):
        # type: (ast.TemporalPredicate) -> JSON
        expr, kind = self._field(node.lhs)
        if kind != FIELD_DATETIME:
            raise _invalid("Temporal filter operation requires a datetime property.", getattr(node.lhs, "name", None))
        rhs = node.rhs
        start, end = (rhs.start, rhs.end) if isinstance(rhs, Interval) else (rhs, rhs)
        start = _to_datetime(start) if start is not None else None
        end = _to_datetime(end) if end is not None else None
        within = [{"$gte": [expr, start]}] if start else []
        within += [{"$lte": [expr, end]}] if end else []
        if isinstance(node, ast.TimeAfter):
            return {"$gt": [expr, end or start]}
        if isinstance(node, ast.TimeBefore):
            return {"$lt": [expr, start or end]}
        if isinstance(node, ast.TimeEquals):
            return {"$eq": [expr, start]}
        if isinstance(node, ast.TimeDisjoint):
            return {"$not": [{"$and": within}]} if within else {"$literal": False}
        if isinstance(node, (ast.TimeDuring, ast.TimeOverlaps, ast.TimeOverlappedBy)):
            return {"$and": within} if within else {"$literal": True}
        raise _invalid("Unsupported temporal filter operation.", type(node).__name__)
