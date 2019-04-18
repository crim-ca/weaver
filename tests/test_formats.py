from weaver.formats import (
    get_cwl_file_format, clean_mime_type_format,
    CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF, FORMAT_NAMESPACES,
    EDAM_NAMESPACE, EDAM_NAMESPACE_DEFINITION, EDAM_MAPPING, IANA_NAMESPACE, IANA_NAMESPACE_DEFINITION
)
import six
import os


def test_get_cwl_file_format_tuple():
    tested = set(FORMAT_NAMESPACES)
    for mime_type in [CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF]:
        res = get_cwl_file_format(mime_type, make_reference=False)
        assert isinstance(res, tuple) and len(res) == 2
        ns, fmt = res
        assert isinstance(ns, dict) and len(ns) == 1
        assert any(f in ns for f in FORMAT_NAMESPACES)
        assert ns.values()[0].startswith("http")
        ns_name = ns.keys()[0]
        assert fmt.startswith("{}:".format(ns_name))
        tested.remove(ns_name)
    assert len(tested) == 0, "test did not evaluate every namespace variation"


def test_get_cwl_file_format_reference():
    tested = set(FORMAT_NAMESPACES)
    tests = [(IANA_NAMESPACE_DEFINITION, CONTENT_TYPE_APP_JSON), (EDAM_NAMESPACE_DEFINITION, CONTENT_TYPE_APP_NETCDF)]
    for ns, mime_type in tests:
        res = get_cwl_file_format(mime_type, make_reference=True)
        ns_name, ns_url = ns.items()[0]
        assert isinstance(res, six.string_types)
        assert res.startswith(ns_url)
        tested.remove(ns_name)
    assert len(tested) == 0, "test did not evaluate every namespace variation"


def test_get_cwl_file_format_unknown():
    res = get_cwl_file_format("application/unknown", make_reference=False, must_exist=True)
    assert isinstance(res, tuple)
    assert res == (None, None)
    res = get_cwl_file_format("application/unknown", make_reference=True, must_exist=True)
    assert res is None


def test_get_cwl_file_format_default():
    fmt = "application/unknown"
    iana_url = IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE]
    iana_fmt = "{}:{}".format(IANA_NAMESPACE, fmt)
    res = get_cwl_file_format("application/unknown", make_reference=False, must_exist=False)
    assert isinstance(res, tuple)
    assert res[0] == {IANA_NAMESPACE: iana_url}
    assert res[1] == iana_fmt
    res = get_cwl_file_format("application/unknown", make_reference=True, must_exist=False)
    assert res == iana_url + fmt


def test_clean_mime_type_format_iana():
    iana_fmt = "{}:{}".format(IANA_NAMESPACE, CONTENT_TYPE_APP_JSON)  # "iana:mime_type"
    res_type = clean_mime_type_format(iana_fmt)
    assert res_type == CONTENT_TYPE_APP_JSON
    iana_fmt = os.path.join(IANA_NAMESPACE_DEFINITION.values()[0], CONTENT_TYPE_APP_JSON)  # "iana-url/mime_type"
    res_type = clean_mime_type_format(iana_fmt)
    assert res_type == CONTENT_TYPE_APP_JSON  # application/json


def test_clean_mime_type_format_edam():
    mime_type, fmt = EDAM_MAPPING.items()[0]
    edam_fmt = "{}:{}".format(EDAM_NAMESPACE, fmt)  # "edam:format_####"
    res_type = clean_mime_type_format(edam_fmt)
    assert res_type == mime_type
    edam_fmt = os.path.join(EDAM_NAMESPACE_DEFINITION.values()[0], fmt)  # "edam-url/format_####"
    res_type = clean_mime_type_format(edam_fmt)
    assert res_type == mime_type  # application/x-type
