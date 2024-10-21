import itertools

import pytest
from pyramid.httpexceptions import HTTPBadRequest

from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteReturnPreference, parse_prefer_header_execute_mode


@pytest.mark.parametrize(
    ["headers", "support", "expected", "extra_prefer"],
    [
        ({}, [], (ExecuteMode.ASYNC, None, {}), ""),
        # both modes supported (sync attempted upto max/specified wait time, unless async requested explicitly)
        ({}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC], (ExecuteMode.SYNC, 10, {}), ""),
        # only supported async (enforced) - original behaviour
        ({}, [ExecuteControlOption.ASYNC], (ExecuteMode.ASYNC, None, {}), ""),
    ] +
    [
        (_headers, _support, _expected, _extra)
        for (_headers, _support, _expected), _extra
        in itertools.product(
            [
                # no mode (API-wide default async)
                ({"Prefer": "respond-async, wait=4"}, [],
                 (ExecuteMode.ASYNC, None, {})),
                # both modes supported (sync attempted upto max/specified wait time, unless async requested explicitly)
                ({"Prefer": ""}, None,  # explicit 'None' or omitting the parameter entirely means "any" mode
                 (ExecuteMode.SYNC, 10, {})),
                ({"Prefer": ""}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
                 (ExecuteMode.SYNC, 10, {})),
                ({"Prefer": "respond-async"}, None,
                 (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
                ({"Prefer": "respond-async"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
                 (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
                ({"Prefer": "respond-async, wait=4"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
                 (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
                ({"Prefer": "wait=4"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
                 (ExecuteMode.SYNC, 4, {"Preference-Applied": "wait=4"})),
                ({"Prefer": "wait=20"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
                 (ExecuteMode.ASYNC, None, {})),  # larger than max time
                # only supported async (enforced) - original behaviour
                ({"Prefer": ""}, [ExecuteControlOption.ASYNC],
                 (ExecuteMode.ASYNC, None, {})),
                ({"Prefer": "respond-async"}, [ExecuteControlOption.ASYNC],
                 (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
                ({"Prefer": "respond-async, wait=4"}, [ExecuteControlOption.ASYNC],
                 (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
                ({"Prefer": "wait=4"}, [ExecuteControlOption.ASYNC],
                 (ExecuteMode.ASYNC, None, {})),
                # only supported sync (enforced)
                ({"Prefer": "wait=4"}, [ExecuteControlOption.SYNC],
                 (ExecuteMode.SYNC, 4, {"Preference-Applied": "wait=4"})),
                ({"Prefer": "respond-async"}, [ExecuteControlOption.SYNC],
                 (ExecuteMode.SYNC, 10, {})),  # 10 is weaver default if not configured otherwise
            ],
            [
                "",
                f"return={ExecuteReturnPreference.MINIMAL}",
                f"return={ExecuteReturnPreference.REPRESENTATION}"
                # FIXME:
                #   Support with added ``Prefer: handling=strict`` or ``Prefer: handling=lenient``
                #   https://github.com/crim-ca/weaver/issues/701
            ]
        )
    ]
)
def test_prefer_header_execute_mode(headers, support, expected, extra_prefer):
    if extra_prefer and "Prefer" in headers:
        headers["Prefer"] += f", {extra_prefer}" if headers["Prefer"] else extra_prefer
    result = parse_prefer_header_execute_mode(headers, support)
    assert result == expected


@pytest.mark.parametrize(
    ["headers", "expected"],
    [
        # 1st variant is considered as 1 Prefer header with all values supplied simultaneously
        ({"Prefer": "respond-async; wait=4"}, (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
        # 2nd variant is considered as 2 Prefer headers, each with their respective value
        # (this is because urllib, under the hood, concatenates the list of header-values using ',' separator)
        ({"Prefer": "respond-async, wait=4"}, (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
    ]
)
def test_parse_prefer_header_execute_mode_flexible(headers, expected):
    """
    Ensure that the ``Prefer`` header supplied multiple times (allowed by :rfc:`7240`) is handled correctly.
    """
    result = parse_prefer_header_execute_mode(headers, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC])
    assert result == expected


@pytest.mark.parametrize("prefer_header", [
    "wait=10s",
    "wait=3.1416",
    "wait=yes",
    "wait=1,2,3",  # technically, gets parsed as 'wait=1' (valid) and other '2', '3' parameters on their own
    "wait=1;2;3",
    "wait=1, wait=2",
    "wait=1; wait=2",
])
def test_parse_prefer_header_execute_mode_invalid(prefer_header):
    headers = {"Prefer": prefer_header}
    with pytest.raises(HTTPBadRequest):
        parse_prefer_header_execute_mode(headers, [ExecuteControlOption.ASYNC])
