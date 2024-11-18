import contextlib
import uuid
from copy import deepcopy
from datetime import datetime, timedelta

import mock
import pytest
from visibility import Visibility

from tests import resources
from tests.utils import setup_mongodb_processstore
from weaver.datatype import Authentication, AuthenticationTypes, DockerAuthentication, Job, Process, Service
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteReturnPreference
from weaver.formats import ContentType
from weaver.status import Status
from weaver.utils import localize_datetime, now

TEST_UUID = uuid.uuid4()


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
         "docker-registry.crim.ca/repo/image:latest", "docker-registry.crim.ca", "repo/image"),
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
         "registry.example.com/org/image-name:latest", "registry.example.com", "org/image-name"),
        ("registry.example.com/org/image-name:version",
         "registry.example.com/org/image-name:version", "registry.example.com", "org/image-name:version"),
        ("repository/image-name:version",
         "repository/image-name:version", docker_hub, "repository/image-name:version"),
        ("repository/image-name",
         "repository/image-name:latest", docker_hub, "repository/image-name"),
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
            auth = DockerAuthentication(docker_input, "Basic", token)
            assert auth.token == token, f"Testing: [{docker_input}]"
            assert auth.registry == docker_registry, f"Testing: [{docker_input}]"
            assert auth.image == docker_image, f"Testing: [{docker_input}]"
            assert auth.docker == docker_ref, f"Testing: [{docker_input}]"
            assert auth.link == docker_input, f"Testing: [{docker_input}]"
        except (TypeError, ValueError) as exc:
            pytest.fail(f"Unexpected failure when [{docker_input}] was expected to be valid: [{exc}]")
    for docker_input in invalid_references:
        try:
            DockerAuthentication(docker_input, "Basic", token)
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
    auth_docker = DockerAuthentication(link, scheme, token)
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


def test_process_outputs_alt():

    from weaver.processes.utils import get_settings as real_get_settings
    setup_mongodb_processstore()

    def _get_mocked(req=None):
        return req.registry.settings if req else real_get_settings(None)

    # mock db functions called by offering
    with contextlib.ExitStack() as stack:

        stack.enter_context(mock.patch("weaver.processes.utils.get_settings", side_effect=_get_mocked))

    process = Process(id=f"test-{uuid.uuid4()!s}", package={},
                      outputs=[{"identifier": "output1", "formats": [{"mediaType": ContentType.IMAGE_TIFF}]}],
                      inputs=[{"identifier": "input_1", "formats": [{"mediaType": ContentType.APP_ZIP}]}])
    offer = process.offering()

    # Assert that process outputs in offering contains alternate representation
    assert offer["outputs"]["output1"]["formats"] == [
        {
        "mediaType": ContentType.IMAGE_TIFF
        },
        {
        "mediaType": ContentType.IMAGE_PNG
        },
        {
        "mediaType": ContentType.IMAGE_GIF
        },
        {
        "mediaType": ContentType.IMAGE_JPEG
        },
        {
        "mediaType": ContentType.IMAGE_SVG_XML
        },
        {
        "mediaType": ContentType.APP_PDF
        }]

    # Assert that process outputs are unchanged
    assert process.outputs[0]["formats"] == [{"mediaType": ContentType.IMAGE_TIFF}]


@pytest.mark.parametrize(
    ["attribute", "value", "result"],
    [
        ("user_id", TEST_UUID, TEST_UUID),
        ("user_id", str(TEST_UUID), str(TEST_UUID)),
        ("user_id", "not-a-uuid", "not-a-uuid"),
        ("user_id", 1234, 1234),
        ("user_id", 3.14, TypeError),
        ("task_id", TEST_UUID, TEST_UUID),
        ("task_id", str(TEST_UUID), TEST_UUID),
        ("task_id", "not-a-uuid", "not-a-uuid"),
        ("task_id", 1234, TypeError),
        ("wps_id", TEST_UUID, TEST_UUID),
        ("wps_id", str(TEST_UUID), TEST_UUID),
        ("wps_id", 1234, TypeError),
        ("wps_url", "https://example.com/wps", "https://example.com/wps"),
        ("wps_url", 1234, TypeError),
        ("execution_mode", ExecuteMode.ASYNC, ExecuteMode.ASYNC),
        ("execution_mode", None, ValueError),  # "auto" required if unspecified
        ("execution_mode", "abc", ValueError),
        ("execution_mode", 12345, ValueError),
        ("execution_response", ExecuteResponse.RAW, ExecuteResponse.RAW),
        ("execution_response", None, ExecuteResponse.DOCUMENT),  # weaver's default
        ("execution_response", "abc", ValueError),
        ("execution_response", 12345, ValueError),
        ("execution_return", ExecuteReturnPreference.REPRESENTATION, ExecuteReturnPreference.REPRESENTATION),
        ("execution_return", None, ExecuteReturnPreference.MINIMAL),  # weaver's default
        ("execution_return", "abc", ValueError),
        ("execution_return", 12345, ValueError),
        ("execution_wait", 1234, 1234),
        ("execution_wait", None, None),
        ("execution_wait", "abc", ValueError),
        ("is_local", True, True),
        ("is_local", 1, TypeError),
        ("is_local", None, TypeError),
        ("is_workflow", True, True),
        ("is_workflow", 1, TypeError),
        ("is_workflow", None, TypeError),
        ("created", "2024-01-02", localize_datetime(datetime(year=2024, month=1, day=2))),
        ("created", datetime(year=2024, month=1, day=2), localize_datetime(datetime(year=2024, month=1, day=2))),
        ("created", "abc", ValueError),
        ("created", 12345, TypeError),
        ("updated", "2024-01-02", localize_datetime(datetime(year=2024, month=1, day=2))),
        ("updated", datetime(year=2024, month=1, day=2), localize_datetime(datetime(year=2024, month=1, day=2))),
        ("updated", "abc", ValueError),
        ("updated", 12345, TypeError),
        ("service", Service(name="test", url="https://example.com/wps"), "test"),
        ("service", "test", "test"),
        ("service", 1234, TypeError),
        ("service", None, TypeError),
        ("process", Process(id="test", package={}), "test"),
        ("process", "test", "test"),
        ("process", 1234, TypeError),
        ("process", None, TypeError),
        ("progress", "test", TypeError),
        ("process", None, TypeError),
        ("progress", 123, ValueError),
        ("progress", -20, ValueError),
        ("progress", 50, 50),
        ("progress", 2.5, 2.5),
        ("statistics", {}, {}),
        ("statistics", None, TypeError),
        ("statistics", 1234, TypeError),
        ("exceptions", [], []),
        ("exceptions", {}, TypeError),
        ("exceptions", "error", TypeError),
        ("exceptions", None, TypeError),
        ("exceptions", 1234, TypeError),
        ("results", [], []),
        ("results", None, TypeError),
        ("results", 1234, TypeError),
        ("logs", [], []),
        ("logs", "info", TypeError),
        ("logs", None, TypeError),
        ("logs", 1234, TypeError),
        ("tags", [], []),
        ("tags", "test", TypeError),
        ("tags", None, TypeError),
        ("tags", 1234, TypeError),
        ("title", "test", "test"),
        ("title", None, None),
        ("title", TypeError, TypeError),
        ("title", 1234, TypeError),
        ("status", Status.SUCCEEDED, Status.SUCCEEDED),
        ("status", 12345678, ValueError),
        ("status", "random", ValueError),
        ("status_message", None, "no message"),
        ("status_message", "test", "test"),
        ("status_message", 123456, TypeError),
        ("status_location", f"https://example.com/jobs/{TEST_UUID}", f"https://example.com/jobs/{TEST_UUID}"),
        ("status_location", None, TypeError),
        ("status_location", 123456, TypeError),
        ("accept_type", None, TypeError),
        ("accept_type", 123456, TypeError),
        ("accept_type", ContentType.APP_JSON, ContentType.APP_JSON),
        ("accept_language", None, TypeError),
        ("accept_language", 123456, TypeError),
        ("accept_language", "en", "en"),
        ("access", Visibility.PRIVATE, Visibility.PRIVATE),
        ("access", 12345678, ValueError),
        ("access", "random", ValueError),
        ("access", None, ValueError),
        ("context", "test", "test"),
        ("context", None, None),
        ("context", 1234, TypeError),
    ]
)
def test_job_attribute_setter(attribute, value, result):
    job = Job(task_id="test")
    if isinstance(result, type) and issubclass(result, Exception):
        with pytest.raises(result):
            setattr(job, attribute, value)
    else:
        setattr(job, attribute, value)
        assert job[attribute] == result


@pytest.mark.parametrize(
    ["value", "result"],
    [
        (TEST_UUID, TEST_UUID),
        (str(TEST_UUID), TEST_UUID),
        ("not-a-uuid", ValueError),
        (12345, TypeError),

    ]
)
def test_job_id(value, result):
    if isinstance(result, type) and issubclass(result, Exception):
        with pytest.raises(result):
            Job(task_id="test", id=value)
    else:
        job = Job(task_id="test", id=value)
        assert job.id == result


def test_job_updated_auto():
    min_dt = now()
    job = Job(task_id="test")
    update_dt = job.updated
    assert isinstance(update_dt, datetime)
    assert update_dt > min_dt
    assert update_dt == job.updated, "Updated time auto generated should have been set to avoid always regenerating it."


def test_job_updated_status():
    created = now()
    started = now() + timedelta(seconds=1)
    finished = now() + timedelta(seconds=2)
    # date-times cannot be set in advance in job,
    # otherwise 'updated' detects and returns them automatically
    job = Job(task_id="test")
    job.created = created
    job.status = Status.ACCEPTED
    assert job.updated == created
    job["updated"] = None  # reset to test auto resolve
    job.started = started
    job.status = Status.STARTED
    assert job.updated == started
    job["updated"] = None  # reset to test auto resolve
    job.finished = finished
    job.status = Status.SUCCEEDED
    assert job.updated == finished


def test_job_execution_wait_ignored_async():
    job = Job(task_id="test", execution_wait=1234, execution_mode=ExecuteMode.ASYNC)
    assert job.execution_mode == ExecuteMode.ASYNC
    assert job.execution_wait is None, "Because of async explicitly set, wait time does not apply"


def test_job_display():
    job = Job(task_id=TEST_UUID, id=TEST_UUID)
    assert str(job) == f"Job <{TEST_UUID}>"
