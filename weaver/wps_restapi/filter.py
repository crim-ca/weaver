"""
Parsing and schema definitions for API filter expressions.
"""
# pylint: disable=E0241,duplicate-bases
import re
import shlex
from functools import cache
from typing import TYPE_CHECKING

import colander
from colander import Length, OneOf, drop, null
from lark.exceptions import LarkError
from pygeofilter.backends.cql2_json import to_cql2
from pygeofilter.parsers import cql2_json, cql2_text, cql_json, ecql, fes, jfe

from weaver import ogc_definitions as ogc_def
from weaver.formats import repr_json
from weaver.utils import json_hashable
from weaver.wps_restapi.colander_extras import (
    AnyOfKeywordSchema,
    ExtendedMappingSchema,
    ExtendedSchemaNode,
    ExtendedString as String,
    OneOfCaseInsensitive,
    PermissiveMappingSchema,
    PermissiveSequenceSchema
)

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Union

    from pygeofilter.ast import AstType as FilterAstType

    from weaver.typedefs import JSON


FILTER_LANGUAGES = (
    "cql2-json",
    "cql2-text",
    "cql",
    "cql-text",
    "cql-json",
    "ecql",
    "simple-cql",
    "fes",
    "jfe",
)

PROCESS_FILTER_FIELDS = {
    "id": "identifier",
    "title": "title",
    "description": "description",
    "keywords": "keywords",
    "version": "version",
    "type": "type",
    "license": "license",
    "created": "created",
}

JOB_FILTER_FIELDS = {
    "id": "id",
    "status": "status",
    "processID": "process",
    "provider": "service",
    "created": "created",
    "started": "started",
    "finished": "finished",
}


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


class AnyCRS(AnyOfKeywordSchema):
    # note:
    #   other CRS exist (EGM, NAVD, NAD, etc.)
    #   however, only support EPSG (short form, normative from, or URI) that are supported by 'owslib.crs'
    #   handle equivalent representations of EPSG:4326 that are also supported by 'owslib.crs'
    _any_of = [
        ExtendedSchemaNode(String(), pattern=re.compile(r"^urn:ogc:def:crs:EPSG::?[0-9]{4,5}$")),
        ExtendedSchemaNode(String(), pattern=re.compile(r"^\[?EPSG::?[0-9]{4,5}\]?$")),
        ExtendedSchemaNode(String(), pattern=re.compile(r"^https?://www\.opengis\.net/def/crs/EPSG/0/[0-9]{4,5}$")),
        ExtendedSchemaNode(String(), validator=OneOf(ogc_def.OGC_DEF_CRS_ANY_EPSG4326)),
    ]
    default = ogc_def.OGC_DEF_CRS_EPSG4326_SHORT


class AnyFilterExpression(AnyOfKeywordSchema):
    _any_of = [
        PermissiveMappingSchema(),
        PermissiveSequenceSchema(validator=Length(min=1)),
        ExtendedSchemaNode(String(), validator=Length(min=1)),
    ]


class AnyFilterLanguage(ExtendedSchemaNode):
    schema_type = String
    name = "filter-lang"
    default = "cql2-json"
    validator = OneOfCaseInsensitive(FILTER_LANGUAGES)
    summary = "Filter expression language to use for parsing."
    description = (
        "Filter expression language to use for parsing. "
        "Supports multiple variants of OGC Common Query Language (CQL), "
        "Filter Expression Standard (FES), or JSON Filter Expression (JFE). "
        "Values are case-insensitive."
    )

    def deserialize(self, cstruct):
        # type: (Any) -> Union[str, colander.null]
        if isinstance(cstruct, str):
            cstruct = cstruct.lower()
        return super().deserialize(cstruct)


class FilterSchema(ExtendedMappingSchema):
    # note:
    #   defer format and parsing to 'pygeofilter'
    #   to accommodate all filter expression representations, string, array and object must be allowed
    filter = AnyFilterExpression(
        description="Filter expression according to the specified parsing language.",
        missing=drop,  # optional since combined within other JSON schema definitions
    )
    filter_crs = AnyCRS(
        name="filter-crs",
        missing=drop,
        default=drop,  # override to avoid injecting it by default, remote server could use a different default
        description="Coordinate Reference System for provided spatial properties.",
    )
    filter_lang = AnyFilterLanguage(
        name="filter-lang",
        missing=drop,
        default=drop,  # override to avoid injecting it by default, remote server could use a different default
        description=AnyFilterLanguage.description + (
            " If unspecified, the filter language will default to CQL2-Text if a string was provided,"
            " or CQL2-JSON if a JSON object or array structure is detected as the filter."
            " For any other language, or to resolve ambiguous cases such as a CQL2-JSON encoded as literal string,"
            " the filter language must be specified explicitly."
        )
    )

    @staticmethod
    @json_hashable
    @cache
    def parse(filter_expr, filter_lang):
        # type: (Union[JSON, str], str) -> FilterAstType
        parsed_expr = None
        if filter_lang == "cql2-json":
            parsed_expr = cql2_json.parse(filter_expr)
        elif filter_lang == "cql2-text":
            parsed_expr = cql2_text.parse(filter_expr)
        elif filter_lang == "cql-json":
            parsed_expr = cql_json.parse(filter_expr)
        elif filter_lang in ["cql", "cql-text", "ecql", "simple-cql"]:
            parsed_expr = ecql.parse(filter_expr)
        elif filter_lang == "fes":
            parsed_expr = fes.parse(filter_expr)
        elif filter_lang == "jfe":
            parsed_expr = jfe.parse(filter_expr)
        if not parsed_expr:
            raise colander.Invalid(
                node=AnyFilterLanguage(),
                msg="Unresolved filter expression language.",
                value={"filter-lang": filter_lang},
            )
        return parsed_expr

    def validate(self, filter_expr, filter_lang):
        # type: (Union[JSON, str], str) -> FilterAstType
        try:
            return self.parse(filter_expr, filter_lang)
        except (TypeError, ValueError, LarkError) as exc:
            raise colander.Invalid(
                node=self,
                msg="Invalid filter expression could not be parsed against specified language.",
                value={"filter": filter_expr, "filter-lang": filter_lang},
            ) from exc

    def convert(self, filter_expr, filter_lang):
        # type: (Union[JSON, str], str) -> JSON
        try:
            parsed_expr = self.validate(filter_expr, filter_lang)
            return to_cql2(parsed_expr)
        except (TypeError, ValueError, NotImplementedError) as exc:
            raise colander.Invalid(
                node=self,
                msg="Invalid filter expression could not be interpreted.",
                value={"filter": filter_expr, "filter-lang": filter_lang},
            ) from exc

    def deserialize(self, cstruct):
        # type: (JSON) -> Union[JSON, colander.null]
        result = super().deserialize(cstruct)
        if not result:
            return result
        filter_expr = result.get("filter")
        filter_lang = result.get("filter-lang")
        if filter_expr in [null, drop, None]:  # explicit "", {}, [] should be raised as invalid since dropped
            if "filter" in cstruct:
                raise colander.Invalid(
                    node=self,
                    msg="Invalid filter expression could not be interpreted.",
                    value={"filter": repr_json(cstruct["filter"]), "filter-lang": filter_lang},
                )
            filter_crs = cstruct.get("filter-crs")
            filter_lang = cstruct.get("filter-lang")
            if filter_crs or filter_lang:
                raise colander.Invalid(
                    node=self,
                    msg="Missing filter expression provided with CRS and/or language parameters.",
                    value={"filter-crs": filter_crs, "filter-lang": filter_lang},
                )
            return result
        if not filter_lang:
            filter_lang = "cql2-text" if isinstance(filter_expr, str) else "cql2-json"
        # perform conversion to validate
        # but don't return the converted CQL2-JSON to preserve the original definition where called (storage/dispatch)
        # conversion can be done as needed to obtain a uniform representation locally
        self.convert(filter_expr, filter_lang)
        return result
