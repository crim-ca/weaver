import importlib
import os
import re
from typing import TYPE_CHECKING

import pytest

from weaver.processes.builtin import WEAVER_BUILTIN_DIR, get_builtin_reference_mapping

# pylint: disable=redefined-outer-name  # avoid issue between fixture name and its variable within test

if TYPE_CHECKING:
    from types import ModuleType
    from typing import List

pytestmark = pytest.mark.builtin


def _get_builtin_processes():
    # type: () -> List[ModuleType]
    mapping = get_builtin_reference_mapping(WEAVER_BUILTIN_DIR)
    processes = []
    for process_id, process_data in mapping.items():
        py_file = f"{os.path.splitext(process_data['package'])[0]}.py"
        if os.path.isfile(py_file):
            mod = importlib.import_module(f"weaver.processes.builtin.{process_id}")
            processes.append(mod)
    return processes


@pytest.fixture(
    scope="module",
    params=_get_builtin_processes(),
    ids=lambda mod: getattr(mod, "__name__", str(mod)).split(".")[-1],
)
def builtin_process(request):
    # type: (pytest.FixtureRequest) -> ModuleType
    """
    Parametrized fixture providing each builtin process module one at a time.
    """
    return request.param


def test_versions(builtin_process):
    # type: (ModuleType) -> None
    """
    Ensure all builtin processes have the ``__version__`` field with ``MAJOR.MINOR.PATCH`` format.
    """
    name = getattr(builtin_process, "__name__", str(builtin_process))
    assert hasattr(builtin_process, "__version__"), f"Process '{name}' is missing '__version__'."
    version = getattr(builtin_process, "__version__")
    assert isinstance(version, str), f"Process '{name}' '__version__' must be a string."
    assert re.match(r"^\d+\.\d+\.\d+$", version), (
        f"Process '{name}' '__version__' [{version}] is not in MAJOR.MINOR.PATCH format."
    )


def test_title_and_doc(builtin_process):
    # type: (ModuleType) -> None
    """
    Ensure all builtin processes have the ``__title__`` and ``__doc__`` fields set.
    """
    name = getattr(builtin_process, "__name__", str(builtin_process))
    assert hasattr(builtin_process, "__title__"), f"Process '{name}' is missing '__title__'."
    title = getattr(builtin_process, "__title__")
    assert isinstance(title, str) and title.strip(), (
        f"Process '{name}' '__title__' must be a non-empty string."
    )
    assert hasattr(builtin_process, "__doc__"), f"Process '{name}' is missing '__doc__'."
    doc = getattr(builtin_process, "__doc__")
    assert isinstance(doc, str) and doc.strip(), (
        f"Process '{name}' '__doc__' must be a non-empty string."
    )
