import uuid
from copy import deepcopy

from weaver.datatype import Process
from weaver.execute import EXECUTE_CONTROL_OPTION_ASYNC, EXECUTE_CONTROL_OPTION_SYNC


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


def test_process_job_control_options_resolution():
    # invalid or matching default mode should be corrected to default async list
    for test_process in [
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=None),
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[None]),
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[]),
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[EXECUTE_CONTROL_OPTION_ASYNC]),
    ]:
        assert test_process.jobControlOptions == [EXECUTE_CONTROL_OPTION_ASYNC]
    # other valid definitions should be preserved as is
    p = Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[EXECUTE_CONTROL_OPTION_SYNC])
    assert p.jobControlOptions == [EXECUTE_CONTROL_OPTION_SYNC]
    p = Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[EXECUTE_CONTROL_OPTION_SYNC,
                                                                                  EXECUTE_CONTROL_OPTION_ASYNC])
    assert p.jobControlOptions == [EXECUTE_CONTROL_OPTION_SYNC, EXECUTE_CONTROL_OPTION_ASYNC]
