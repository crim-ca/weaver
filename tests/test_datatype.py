import uuid
from copy import deepcopy

import pytest

from tests import resources
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
            "$namespaces": {"iana": "ref"}
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
    assert "$namespaces" not in process_package_encoded["executionUnit"][0]["unit"]
    assert _replace_specials("$namespaces") in process_package_encoded["executionUnit"][0]["unit"]
    assert package == process.package, "package obtained from the process method should be the original decoded version"


def test_process_job_control_options_resolution():
    # invalid or matching default mode should be corrected to default modes list
    for i, test_process in enumerate([
        Process(id=f"test-{uuid.uuid4()!s}", package={}, jobControlOptions=None),
        Process(id=f"test-{uuid.uuid4()!s}", package={}, jobControlOptions=[None]),
        Process(id=f"test-{uuid.uuid4()!s}", package={}, jobControlOptions=[]),
    ]):
        assert test_process.jobControlOptions == [ExecuteControlOption.ASYNC], f"Test {i}"
    # explicitly provided modes are used as is, especially if partial (allow disabling some modes)
    proc = Process(id=f"test-{uuid.uuid4()!s}", package={}, jobControlOptions=[ExecuteControlOption.ASYNC])
    assert proc.jobControlOptions == [ExecuteControlOption.ASYNC]
    # other valid definitions should be preserved as is
    proc = Process(id=f"test-{uuid.uuid4()!s}", package={},
                   jobControlOptions=[ExecuteControlOption.SYNC])
    assert proc.jobControlOptions == [ExecuteControlOption.SYNC]
    # See ordering note in 'jobControlOptions' property
    proc = Process(id=f"test-{uuid.uuid4()!s}", package={},
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


def test_auth_docker_image_from_credentials():
    registry = "registry.gitlab.com"
    image = "crim.ca/category/group/project:1.2.3"
    link = f"{registry}/{image}"
    usr, pwd = "random", "12345"  # nosec
    auth_docker = DockerAuthentication(link, auth_username=usr, auth_password=pwd)
    assert auth_docker.link == link
    assert auth_docker.token
    assert usr not in auth_docker.token and pwd not in auth_docker.token
    assert auth_docker.credentials["username"] == usr
    assert auth_docker.credentials["password"] == pwd
    assert auth_docker.credentials["registry"] == registry


def test_auth_docker_image_public():
    registry = "registry.gitlab.com"
    image = "crim.ca/category/group/project:1.2.3"
    link = f"{registry}/{image}"
    auth_docker = DockerAuthentication(link)
    assert auth_docker.link == link
    assert auth_docker.registry == registry
    assert not auth_docker.token
    assert not auth_docker.credentials


def test_process_io_schema_ignore_uri():
    """
    Process with ``schema`` field under I/O definition that is not an :term:`OAS` object must not fail I/O resolution.
    """
    wps_data = resources.load_resource("wps_colibri_flyingpigeon_subset_storage.json")
    assert any(isinstance(out.get("schema"), str) for out in wps_data["outputs"])
    proc_obj = Process(wps_data)
    # following convert JSON items to pywps definitions, but also generate OAS inline
    # if 'default format' "schema" exists, it must not cause an error when parsing the object
    wps_proc = proc_obj.wps()
    assert any(isinstance(out.json.get("schema"), str) for out in wps_proc.outputs)


@pytest.mark.parametrize("process_id,result", [
    ("urn:test:1.2.3", ("urn:test", "1.2.3")),
    ("urn:uuid:process:test", ("urn:uuid:process:test", None)),
    ("urn:test:random-test:1.3.4", ("urn:test:random-test", "1.3.4")),
    ("random-test:1", ("random-test", "1")),
    ("random-test:1.3.4", ("random-test", "1.3.4")),
    ("random-test:not.a.version", ("random-test:not.a.version", None)),
])
def test_process_split_version(process_id, result):
    assert Process.split_version(process_id) == result
