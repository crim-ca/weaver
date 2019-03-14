from weaver.datatype import Process


def test_package_encode_decode():
    package = {
        "cwl.Version": "v1.0",
        "class": "CommandLineTool",
        "inputs": {"$url": {"type": "string"}},
        "outputs": {"output": {"$format": "iana:random", "type": "File"}},
        "$namespaces": {"iana": "ref"},
        "$schemas": {"iana": "ref"}
    }
    # noinspection PyProtectedMember
    process = Process(id="test-package-encode-decode", processEndpointWPS1="blah",  # required params
                      package=package)  # gets encoded

    def _assert_equal_recursive(d1, d2):
        for k1, k2 in zip(d1, d2):  # gets decoded
            assert k1 == k2
            if isinstance(k1, dict):
                _assert_equal_recursive(d1[k1], d2[k2])
            else:
                assert d1[k1] == d2[k2]

    def _replace_many_encode(value, items):
        for old, new in items:
            value = value.replace(new, old)
        return value

    process_package_encoded = dict(process)["package"]
    assert "cwl.Version" not in process_package_encoded
    assert _replace_many_encode("cwl.Version", Process._package_codes) in process_package_encoded
    assert "$namespaces" not in process_package_encoded
    assert _replace_many_encode("$namespaces", Process._package_codes) in process_package_encoded
    assert "$schemas" not in process_package_encoded
    assert _replace_many_encode("$schemas", Process._package_codes) in process_package_encoded
    assert "$url" not in process_package_encoded["inputs"]
    assert _replace_many_encode("$url", Process._package_codes) in process_package_encoded["inputs"]
    assert "$format" not in process_package_encoded["outputs"]["output"]
    assert _replace_many_encode("$format", Process._package_codes) in process_package_encoded["outputs"]["output"]
    _assert_equal_recursive(package, process.package)  # gets decoded
