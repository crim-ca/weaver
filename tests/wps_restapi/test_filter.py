# pylint: disable=C0103,invalid-name
from typing import List, Optional, Tuple

import pytest

from weaver.wps_restapi import swagger_definitions as sd


@pytest.mark.ogc_records
@pytest.mark.parametrize("value, expected", [
    ("climate +netcdf -grib,subset", [[("climate", False), ("netcdf", False), ("grib", True)], [("subset", False)]]),
    ("climate+netcdf-grib", [[("climate+netcdf-grib", False)]]),
    ("climate,-grib", [[("climate", False)], [("grib", True)]]),
    ("climate,+subset", [[("climate", False)], [("subset", False)]]),
    ("x+,y", [[("x+", False)], [("y", False)]]),
    ("x+", [[("x+", False)]]),
    ("x-", [[("x-", False)]]),
    ("data-", [[("data-", False)]]),
    ("+A B +C", [[("A B", False), ("C", False)]]),
    ("+A B", [[("A B", False)]]),
    ("+A-B", [[("A-B", False)]]),
    ("+A+B", [[("A+B", False)]]),
    ("+-A", [[("-A", False)]]),
    ('"+"', [[("+", False)]]),
    ('"data"-', [[("data-", False)]]),
    ('"regional subset" -"out of date"', [[("regional subset", False), ("out of date", True)]]),
    ('"net-cdf" + "a+b" -"x,y"', [[("net-cdf", False), ("a+b", False), ("x,y", True)]]),
])
def test_parse_search_query(value, expected):
    # type: (str, List[List[Tuple[str, bool]]]) -> None
    """
    Tests text query grouping, negation and quoted literal operators.
    """
    assert sd.ProcessQueryExpression.parse(value) == expected


@pytest.mark.ogc_records
@pytest.mark.parametrize("value", ["", ",", "x,,y", "+", "-", "x +", "x -", "x +,y", 'x "unfinished'])
def test_parse_search_query_invalid(value):
    # type: (str) -> None
    """
    Tests that incomplete expressions cannot silently alter search semantics.
    """
    with pytest.raises(ValueError):
        sd.ProcessQueryExpression.parse(value)


@pytest.mark.ogc_records
def test_parse_keyword_query():
    # type: () -> None
    """
    Tests keyword AND groups with OR alternatives and either negation prefix.
    """
    assert sd.ProcessKeywordExpression.parse(" climate , !grib|~netcdf ") == [
        [("climate", False)], [("grib", True), ("netcdf", True)],
    ]


@pytest.mark.ogc_records
@pytest.mark.parametrize("value, expected", [
    ("1.2", ((1, 2, 0), (1, 2, 0))),
    ("1.2.3/1.10.0", ((1, 2, 3), (1, 10, 0))),
    ("../1.0", (None, (1, 0, 0))),
    ("1/..", ((1, 0, 0), None)),
])
def test_parse_version_range(value, expected):
    # type: (str, Tuple[Optional[Tuple[int, int, int]], Optional[Tuple[int, int, int]]]) -> None
    """
    Tests numeric interval bounds and normalization of abbreviated versions.
    """
    assert sd.ProcessVersionExpression.parse(value) == expected
