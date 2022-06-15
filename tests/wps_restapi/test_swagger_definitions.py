import uuid

import colander
import pytest

from weaver.wps_restapi import swagger_definitions as sd


def test_process_id_with_version_tag_deploy_invalid():
    """
    Validate process ID with version label is not allowed as definition during deployment or update.

    To take advantage of auto-resolution of unique :meth:`StoreProcesses.fetch_by_id` with version references injected
    in the process ID stored in the database, deployment and description of processes must not allow it to avoid
    conflicts. The storage should take care of replacing the ID value transparently after it was resolved.
    """
    test_id_version_invalid = [
        "process:1.2.3",
        "test-process:4.5.6",
        "other_process:1",
        "invalid-process:1_2_3",
        f"{uuid.uuid4()}:7.8.9",
    ]
    for test_id in test_id_version_invalid:
        with pytest.raises(colander.Invalid):
            sd.ProcessIdentifier().deserialize(test_id)
    for test_id in test_id_version_invalid:
        test_id = test_id.split(":", 1)[0]
        assert sd.ProcessIdentifier().deserialize(test_id) == test_id


def test_process_id_with_version_tag_get_valid():
    """
    Validate that process ID with tagged version is permitted for request path parameter to retrieve it.
    """
    test_id_version_valid = [
        "test-ok",
        "test-ok1",
        "test-ok:1",
        "test-ok:1.2.3",
        "also_ok:1.3",
    ]
    test_id_version_invalid = [
        "no-:1.2.3",
        "not-ok1.2.3",
        "no:",
        "not-ok:",
        "not-ok11:",
        "not-ok1.2.3:",
    ]
    for test_id in test_id_version_invalid:
        with pytest.raises(colander.Invalid):
            sd.ProcessIdentifierTag().deserialize(test_id)
    for test_id in test_id_version_valid:
        assert sd.ProcessIdentifierTag().deserialize(test_id) == test_id
