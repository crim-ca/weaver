import uuid

import colander
import pytest

from weaver.wps_restapi import swagger_definitions as sd


def test_process_id_with_version_invalid():
    """
    Validate process ID with version label is not allowed.

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
        sd.ProcessIdentifier().deserialize(test_id)
