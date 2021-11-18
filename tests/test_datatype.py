import pytest
import uuid
from copy import deepcopy

from weaver.datatype import DockerAuthentication, Process
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
    proc = Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[EXECUTE_CONTROL_OPTION_SYNC])
    assert proc.jobControlOptions == [EXECUTE_CONTROL_OPTION_SYNC]
    proc = Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[EXECUTE_CONTROL_OPTION_SYNC,
                                                                                     EXECUTE_CONTROL_OPTION_ASYNC])
    assert proc.jobControlOptions == [EXECUTE_CONTROL_OPTION_SYNC, EXECUTE_CONTROL_OPTION_ASYNC]


def test_auth_docker_image_registry_format():
    docker_hub = DockerAuthentication.DOCKER_REGISTRY_DEFAULT_URI
    valid_references = [
        ("docker-registry.crim.ca/repo/image",
         "docker-registry.crim.ca", "repo/image"),
        ("docker-registry.crim.ca/repo/image:latest",
         "docker-registry.crim.ca", "repo/image:latest"),
        ("docker-registry.crim.ca/repo/image:1.0.0",
         "docker-registry.crim.ca", "repo/image:1.0.0"),
        ("quay.io/prometheus/node-exporter:v1.0.0",
         "quay.io", "prometheus/node-exporter:v1.0.0"),
        ("pavics/jupyterhub:1.3.0-20201211", docker_hub,
         "pavics/jupyterhub:1.3.0-20201211"),
        ("registry.gitlab.com/crim.ca/category/group/project:1.2.3",
         "registry.gitlab.com", "crim.ca/category/group/project:1.2.3"),
        ("https://index.docker.io/v1/repo/image:test",
         docker_hub, "repo/image:test"),
        ("registry.example.com/org/image-name",
         "registry.example.com", "org/image-name"),
        ("registry.example.com/org/image-name:version",
         "registry.example.com", "org/image-name:version"),
        ("repository/image-name:version",
         docker_hub, "repository/image-name:version"),
        ("repository/image-name",
         docker_hub, "repository/image-name"),
    ]
    invalid_references = [
        # missing repo part, not allowed local images
        "image-name:version",
        "image-name",
        # not a URI repository (nowhere to send Auth token since not default DockerHub)
        "repository/org/image-name",
        "repository/org/image-name:version",
    ]
    token = str(uuid.uuid4())
    for docker_ref, docker_registry, docker_image in valid_references:
        try:
            auth = DockerAuthentication(token, docker_ref)
            assert auth.token == token, f"Testing: [{docker_ref}]"
            assert auth.link == docker_registry, f"Testing: [{docker_ref}]"
            assert auth.image == docker_image, f"Testing: [{docker_ref}]"
        except (TypeError, ValueError) as exc:
            pytest.fail(f"Unexpected failure when [{docker_ref}] was expected to be valid: [{exc}]")
    for docker_ref in invalid_references:
        with pytest.raises((TypeError, ValueError)):  # noqa
            result = DockerAuthentication(token, docker_ref)
            assert result
