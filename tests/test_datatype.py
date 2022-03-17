import uuid
from copy import deepcopy

import pytest

from weaver.datatype import Authentication, AuthenticationTypes, DockerAuthentication, Process
from weaver.execute import ExecuteControlOption


def test_package_encode_decode():
    package = {
        "cwl.Version": "v1.0",
        "class": "CommandLineTool",
        "inputs": {"$url": {"type": "string"}},
        "outputs": {"output": {"$format": "iana:random", "type": "File"}},
        "$namespaces": {"iana": "ref"},
        "$schemas": {"iana": "ref"},
        "executionUnit": [{"unit": {
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
    assert "$namespace" not in process_package_encoded["executionUnit"][0]["unit"]
    assert _replace_specials("$namespace") in process_package_encoded["executionUnit"][0]["unit"]
    assert package == process.package, "package obtained from the process method should be the original decoded version"


def test_process_job_control_options_resolution():
    # invalid or matching default mode should be corrected to default async list
    for test_process in [
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=None),
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[None]),
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[]),
        Process(id="test-{}".format(uuid.uuid4()), package={}, jobControlOptions=[ExecuteControlOption.ASYNC]),
    ]:
        assert test_process.jobControlOptions == [ExecuteControlOption.ASYNC]
    # other valid definitions should be preserved as is
    proc = Process(id="test-{}".format(uuid.uuid4()), package={},
                   jobControlOptions=[ExecuteControlOption.SYNC])
    assert proc.jobControlOptions == [ExecuteControlOption.SYNC]
    # See ordering note in 'jobControlOptions' property
    proc = Process(id="test-{}".format(uuid.uuid4()), package={},
                   jobControlOptions=[ExecuteControlOption.SYNC, ExecuteControlOption.ASYNC])
    assert proc.jobControlOptions == [ExecuteControlOption.SYNC, ExecuteControlOption.ASYNC]


def test_auth_docker_image_registry_format():
    docker_hub = DockerAuthentication.DOCKER_REGISTRY_DEFAULT_URI
    valid_references = [
        ("docker-registry.crim.ca/repo/image",
         "docker-registry.crim.ca/repo/image", "docker-registry.crim.ca", "repo/image"),
        ("docker-registry.crim.ca/repo/image:latest",
         "docker-registry.crim.ca/repo/image:latest", "docker-registry.crim.ca", "repo/image:latest"),
        ("docker-registry.crim.ca/repo/image:1.0.0",
         "docker-registry.crim.ca/repo/image:1.0.0", "docker-registry.crim.ca", "repo/image:1.0.0"),
        ("quay.io/prometheus/node-exporter:v1.0.0",
         "quay.io/prometheus/node-exporter:v1.0.0", "quay.io", "prometheus/node-exporter:v1.0.0"),
        ("pavics/jupyterhub:1.3.0-20201211",
         "pavics/jupyterhub:1.3.0-20201211", docker_hub, "pavics/jupyterhub:1.3.0-20201211"),
        ("registry.gitlab.com/crim.ca/category/group/project:1.2.3",
         "registry.gitlab.com/crim.ca/category/group/project:1.2.3",
         "registry.gitlab.com", "crim.ca/category/group/project:1.2.3"),
        ("https://index.docker.io/v1/repo/image:test",
         "repo/image:test", docker_hub, "repo/image:test"),
        ("registry.example.com/org/image-name",
         "registry.example.com/org/image-name", "registry.example.com", "org/image-name"),
        ("registry.example.com/org/image-name:version",
         "registry.example.com/org/image-name:version", "registry.example.com", "org/image-name:version"),
        ("repository/image-name:version",
         "repository/image-name:version", docker_hub, "repository/image-name:version"),
        ("repository/image-name",
         "repository/image-name", docker_hub, "repository/image-name"),
    ]
    invalid_references = [
        # missing repo part, not allowed local/public images
        "debian:stretch-slim",  # valid image, but public so no reason to have auth applied for it
        "image-name:version",
        "image-name",
        # not a URI repository (nowhere to send Auth token since not default DockerHub)
        "repository/org/image-name",
        "repository/org/image-name:version",
    ]
    token = str(uuid.uuid4())
    for docker_input, docker_ref, docker_registry, docker_image in valid_references:
        try:
            auth = DockerAuthentication("Basic", token, docker_input)
            assert auth.token == token, f"Testing: [{docker_input}]"
            assert auth.registry == docker_registry, f"Testing: [{docker_input}]"
            assert auth.image == docker_image, f"Testing: [{docker_input}]"
            assert auth.docker == docker_ref, f"Testing: [{docker_input}]"
            assert auth.link == docker_input, f"Testing: [{docker_input}]"
        except (TypeError, ValueError) as exc:
            pytest.fail(f"Unexpected failure when [{docker_input}] was expected to be valid: [{exc}]")
    for docker_input in invalid_references:
        try:
            DockerAuthentication("Basic", token, docker_input)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"Testing [{docker_input}] did not raise invalid format when expected to raise.")


def test_auth_docker_image_from_parent_params():
    """
    Using the base class, it is still possible to generate the full implementation if all parameters are present.

    This is employed mostly for reload from database.
    """

    registry = "registry.gitlab.com"
    image = "crim.ca/category/group/project:1.2.3"
    link = f"{registry}/{image}"
    token = "12345"  # nosec
    scheme = "Basic"
    auth = Authentication.from_params(type="docker", scheme=scheme, token=token,
                                      link=link, image=image, registry=registry)

    # pylint: disable=E1101,no-member  # that's what we want to test!
    assert isinstance(auth, DockerAuthentication)
    assert auth.type == AuthenticationTypes.DOCKER
    assert auth.image == image
    assert auth.link == link

    # convenience methods also should work
    assert auth.docker == link
    assert auth.registry == registry

    # not extra fields remaining
    auth_docker = DockerAuthentication(scheme, token, link)
    auth_docker.id = auth.id  # noqa  # randomly generated for both, must be passed down
    assert auth == auth_docker
    assert dict(auth_docker) == dict(auth_docker)
    for field in ["auth_link", "auth_token", "auth_type", "auth_image"]:
        assert field not in auth
