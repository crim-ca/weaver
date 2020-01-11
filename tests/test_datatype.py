from weaver.datatype import Process
from copy import deepcopy


def test_package_encode_decode():
    package = {
        "cwl.Version": "v1.0",
        "class": "CommandLineTool",
        "inputs": {"$url": {"type": "string"}},
        "outputs": {"output": {"$format": "iana:random", "type": "File"}},
        "$namespaces": {"iana": "ref"},
        "$schemas": {"iana": "ref"},
        "executionUnits": [{"unit": {
            "class": "CommandLineTool",
            "$namespace": {"iana": "ref"}
        }}]
    }

    process = Process(id="test-package-encode-decode",  # required param
                      processEndpointWPS1="blah",       # required param
                      package=deepcopy(package))        # gets encoded

    def _replace_specials(value):
        for old, new in Process._character_codes:
            value = value.replace(old, new)
        return value

    process_package_encoded = process.params()["package"]
    assert "cwl.Version" not in process_package_encoded
    assert _replace_specials("cwl.Version") in process_package_encoded
    assert "$namespaces" not in process_package_encoded
    assert _replace_specials("$namespaces") in process_package_encoded
    assert "$schemas" not in process_package_encoded
    assert _replace_specials("$schemas") in process_package_encoded
    assert "$url" not in process_package_encoded["inputs"]
    assert _replace_specials("$url") in process_package_encoded["inputs"]
    assert "$format" not in process_package_encoded["outputs"]["output"]
    assert _replace_specials("$format") in process_package_encoded["outputs"]["output"]
    assert "$namespace" not in process_package_encoded["executionUnits"][0]["unit"]
    assert _replace_specials("$namespace") in process_package_encoded["executionUnits"][0]["unit"]
    assert package == process.package, "package obtained from the process method should be the original decoded version"
