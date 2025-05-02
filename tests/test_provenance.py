import itertools

import pytest

from weaver.formats import ContentType, OutputFormat
from weaver.provenance import ProvenanceFormat, ProvenancePathType


@pytest.mark.prov
@pytest.mark.parametrize(
    ["prov_method", "kwargs", "expected"],
    [
        (ProvenancePathType.as_type, {}, None),
        (ProvenancePathType.get, {}, None),
        (ProvenancePathType.get, {"default": None}, None),
        (ProvenancePathType.get, {"default": "default"}, "default"),
        (ProvenancePathType.get, {"run_id": "1234"}, None),
        (ProvenancePathType.get, {"run_id": "1234", "default": "default"}, "default"),
    ]
)
def test_provenance_path_type_unresolved(prov_method, kwargs, expected):
    result = prov_method("random", **kwargs)
    assert result == expected


@pytest.mark.prov
@pytest.mark.parametrize(
    ["provenance", "prov_run_id", "expect_path", "expect_type"],
    [
        ("prov", None, ProvenancePathType.PROV, "prov"),
        ("/prov", None, ProvenancePathType.PROV, "prov"),
        ("info", None, ProvenancePathType.PROV_INFO, "info"),
        ("/info", None, ProvenancePathType.PROV_INFO, "info"),
        ("/prov/info", None, ProvenancePathType.PROV_INFO, "info"),
        ("run", None, ProvenancePathType.PROV_RUN, "run"),
        ("/run", None, ProvenancePathType.PROV_RUN, "run"),
        ("/prov/run", None, ProvenancePathType.PROV_RUN, "run"),
        ("run", "run-id", f"{ProvenancePathType.PROV_RUN}/run-id", "run"),
        ("/run", "run-id", f"{ProvenancePathType.PROV_RUN}/run-id", "run"),
        ("/prov/run", "run-id", f"{ProvenancePathType.PROV_RUN}/run-id", "run"),
    ]
)
def test_provenance_path_type_resolution(provenance, prov_run_id, expect_path, expect_type):
    result = ProvenancePathType.get(provenance, run_id=prov_run_id)
    assert result == expect_path
    result = ProvenancePathType.as_type(provenance)
    assert result == expect_type


@pytest.mark.prov
def test_provenance_formats():
    result = ProvenanceFormat.formats()
    expect = [
        ProvenanceFormat.PROV_JSON,
        ProvenanceFormat.PROV_JSONLD,
        ProvenanceFormat.PROV_TURTLE,
        ProvenanceFormat.PROV_N,
        ProvenanceFormat.PROV_XML,
        ProvenanceFormat.PROV_XML,
        ProvenanceFormat.PROV_NT,
    ]
    assert set(result) == set(expect)


@pytest.mark.prov
def test_provenance_media_types():
    result = ProvenanceFormat.media_types()
    expect = [
        ContentType.APP_JSON,
        ContentType.APP_JSONLD,
        ContentType.APP_YAML,
        ContentType.TEXT_TURTLE,
        ContentType.TEXT_PROVN,
        ContentType.TEXT_XML,
        ContentType.APP_XML,
        ContentType.APP_NT,
    ]
    assert set(result) == set(expect)


@pytest.mark.prov
@pytest.mark.parametrize(
    ["provenance", "expect"],
    [
        (None, None),
        ("prov-json", ProvenanceFormat.PROV_JSON),
        ("PROV-JSON", ProvenanceFormat.PROV_JSON),
        ("PROV-JSONLD", ProvenanceFormat.PROV_JSONLD),
    ]
)
def test_provenance_format(provenance, expect):
    result = ProvenanceFormat.get(provenance)
    assert result == expect


@pytest.mark.prov
@pytest.mark.parametrize(
    ["provenance", "expect"],
    [
        (None, None),
        (ProvenanceFormat.PROV_JSON, ContentType.APP_JSON),
        (ProvenanceFormat.PROV_JSONLD, ContentType.APP_JSONLD),
        (ProvenanceFormat.PROV_XML, ContentType.APP_XML),
        (ProvenanceFormat.PROV_NT, ContentType.APP_NT),
        (ProvenanceFormat.PROV_N, ContentType.TEXT_PROVN),
        (ProvenanceFormat.PROV_TURTLE, ContentType.TEXT_TURTLE),
    ]
)
def test_provenance_as_media_type(provenance, expect):
    result = ProvenanceFormat.as_media_type(provenance)
    assert result == expect


@pytest.mark.prov
@pytest.mark.parametrize(
    ["prov", "prov_format", "output_format", "expect", "is_error"],
    [
        (None, None, None, ProvenanceFormat.PROV_JSON, False),
        # only main PROV path allow format variants
        (ProvenancePathType.PROV, None, None, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_JSON, None, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_JSONLD, None, ProvenanceFormat.PROV_JSONLD, False),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_XML, None, ProvenanceFormat.PROV_XML, False),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_NT, None, ProvenanceFormat.PROV_NT, False),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_N, None, ProvenanceFormat.PROV_N, False),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_TURTLE, None, ProvenanceFormat.PROV_TURTLE, False),
        # validate implicit mapping via output format
        (ProvenancePathType.PROV, None, OutputFormat.JSON, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, None, OutputFormat.JSON_RAW, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, None, OutputFormat.JSON_STR, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, None, OutputFormat.YAML, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, None, OutputFormat.YML, ProvenanceFormat.PROV_JSON, False),
        (ProvenancePathType.PROV, None, OutputFormat.XML, ProvenanceFormat.PROV_XML, False),
        (ProvenancePathType.PROV, None, OutputFormat.TEXT, ProvenanceFormat.PROV_N, False),
        (ProvenancePathType.PROV, None, OutputFormat.TXT, ProvenanceFormat.PROV_N, False),
        # check some combinations considered invalid
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_N, OutputFormat.JSON, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_N, OutputFormat.XML, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_NT, OutputFormat.JSON, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_NT, OutputFormat.XML, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_XML, OutputFormat.JSON_RAW, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_JSON, OutputFormat.XML, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_TURTLE, OutputFormat.JSON, None, True),
        (ProvenancePathType.PROV, None, OutputFormat.HTML, None, True),
        (ProvenancePathType.PROV, ProvenanceFormat.PROV_JSON, OutputFormat.TEXT, None, True),
        (ProvenancePathType.PROV_INFO, None, OutputFormat.JSON, None, True),
        (ProvenancePathType.PROV_INFO, ProvenanceFormat.PROV_JSON, OutputFormat.JSON, None, True),
    ]
    +
    [
        # all but the main PROV paths are text-only
        # no output format, so it default to None resolved, and no error
        (_prov, _prov_fmt, None, None, False)
        for _prov, _prov_fmt
        in itertools.product(
            set(ProvenancePathType.types()) - {ProvenancePathType.as_type(ProvenancePathType.PROV)},
            ProvenanceFormat.values(),
        )
    ]
    +
    [
        # all but the main PROV paths are text-only
        # if anything is specified other than text, it's an error
        (_prov, _prov_fmt, _out_fmt, None, True)
        for _prov, _prov_fmt, _out_fmt
        in itertools.product(
            set(ProvenancePathType.types()) - {ProvenancePathType.as_type(ProvenancePathType.PROV)},
            ProvenanceFormat.values(),
            set(OutputFormat.values()) - {OutputFormat.TEXT, OutputFormat.TXT},
        )
    ]
    +
    [
        # all but the main PROV paths are text-only
        # valid if the output format is text
        (_prov, _prov_fmt, _out_fmt, None, False)
        for _prov, _prov_fmt, _out_fmt
        in itertools.product(
            set(ProvenancePathType.types()) - {ProvenancePathType.as_type(ProvenancePathType.PROV)},
            ProvenanceFormat.values(),
            [OutputFormat.TEXT, OutputFormat.TXT],
        )
    ]
)
def test_provenance_format_compatible(prov, prov_format, output_format, expect, is_error):
    result, error = ProvenanceFormat.resolve_compatible_formats(prov, prov_format, output_format)
    assert result == expect
    assert error if is_error else error is None, "When an error is expected, a string detailing it should be returned."
