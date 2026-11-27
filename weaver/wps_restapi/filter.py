"""
Parsing and constants for API filter expressions.
"""
import re
import shlex
from typing import TYPE_CHECKING

from weaver.base import Constants

if TYPE_CHECKING:
    from typing import List, Optional, Tuple


class FilterLanguage(Constants):
    CQL2_JSON = "cql2-json"
    CQL2_TEXT = "cql2-text"
    CQL = "cql"
    CQL_TEXT = "cql-text"
    CQL_JSON = "cql-json"
    ECQL = "ecql"
    SIMPLE_CQL = "simple-cql"
    FES = "fes"
    JFE = "jfe"


def parse_keyword_query(value):
    # type: (str) -> List[List[Tuple[str, bool]]]
    """
    Parses keyword alternatives grouped by comma-separated AND terms.

    Terms separated by ``|`` are alternatives. Prefix a term with ``!`` or ``~`` to exclude it.
    """
    groups = []
    for group in value.split(","):
        terms = []
        for term in group.split("|"):
            term = term.strip()
            negative = term.startswith(("!", "~"))
            term = term[1:].strip() if negative else term
            if not term or term.startswith(("!", "~")):
                raise ValueError("A keyword or negated keyword is required for every alternative.")
            terms.append((term, negative))
        groups.append(terms)
    return groups


def parse_search_query(value):
    # type: (str) -> List[List[Tuple[str, bool]]]
    """
    Parses a process search expression into phrase groups.

    Commas separate alternatives. At a term boundary, ``+`` requires a term and ``-`` excludes it.
    Signs elsewhere are literal. Whitespace joins ordered phrases, and quoted punctuation is preserved.
    """
    pattern = r'"(?:\\.|[^"\\])*"|(?P<operator>,|(?<![^\s,])[+-])|[^\s,"]+|\s+|"'
    groups = [[]]  # type: List[List[Tuple[str, bool]]]
    parts = []
    negative = pending = False
    for match in re.finditer(pattern, f"{value},"):
        lexeme = match.group()
        if match.group("operator"):
            text = "".join(parts).strip()
            if text:
                groups[-1].append((text, negative))
            elif pending or lexeme == ",":
                raise ValueError("Missing search query term.")
            if lexeme == ",":
                groups.append([])
            parts = []
            negative, pending = lexeme == "-", lexeme != ","
        elif lexeme.startswith('"'):
            parts.extend(shlex.split(lexeme))
        else:
            parts.append(lexeme)
    return groups[:-1]


def parse_version_range(value):
    # type: (str) -> Tuple[Optional[Tuple[int, int, int]], Optional[Tuple[int, int, int]]]
    """
    Parses an exact version or an inclusive ``lower/upper`` range with optional ``..`` open bounds.
    """
    bounds = value.split("/")
    if len(bounds) not in [1, 2]:
        raise ValueError("Expected an exact version or a lower/upper version interval.")
    versions = []  # type: List[Optional[Tuple[int, int, int]]]
    for bound in bounds:
        if bound == ".." and len(bounds) == 2:
            versions.append(None)
        elif re.fullmatch(r"\d+(?:\.\d+){0,2}", bound):
            version_parts = tuple(int(component) for component in bound.split("."))
            versions.append(version_parts + (0,) * (3 - len(version_parts)))
        else:
            raise ValueError("Version interval bounds must be numeric semantic versions or '..'.")
    if not any(version is not None for version in versions):
        raise ValueError("At least one version bound is required.")
    if len(versions) == 1:
        return versions[0], versions[0]
    lower, upper = versions[0], versions[1]
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("The lower version bound exceeds the upper bound.")
    return lower, upper
