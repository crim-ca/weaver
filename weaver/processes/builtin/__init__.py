from weaver.database import get_db
from weaver.datatype import Process
from weaver.store.base import StoreProcesses
from weaver.processes.types import PROCESS_BUILTIN
from weaver.processes.wps_package import PACKAGE_EXTENSIONS, get_process_definition
from weaver.utils import clean_json_text_body
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps_restapi.utils import get_wps_restapi_base_url
from typing import TYPE_CHECKING
from importlib import import_module
import six
import os
if TYPE_CHECKING:
    from weaver.typedefs import AnyDatabaseContainer
    from typing import AnyStr, Dict, Union


__all__ = ["register_builtin_processes"]


def _get_builtin_reference_mapping(root):
    # type: (AnyStr) -> Dict[AnyStr, AnyStr]
    """Generates a mapping of `reference` to actual ``builtin`` package file path."""
    # noinspection PyProtectedMember
    builtin_names = [_pkg for _pkg in os.listdir(root)
                     if os.path.splitext(_pkg)[-1].replace('.', '') in PACKAGE_EXTENSIONS]
    return {os.path.splitext(_pkg)[0]: os.path.join(root, _pkg) for _pkg in builtin_names}


def _get_builtin_abstract(process_id, process_path):
    # type: (AnyStr, AnyStr) -> Union[AnyStr, None]
    """Retrieves the ``builtin`` process ``abstract`` from its `docstring` (``__doc__``) if it exists."""
    py_file = os.path.splitext(process_path)[0] + ".py"
    if os.path.isfile(py_file):
        try:
            mod = import_module("{}.{}".format(__name__, process_id))
            if hasattr(mod, "__doc__") and isinstance(mod.__doc__, six.string_types) and len(mod.__doc__):
                return clean_json_text_body(mod.__doc__)
        except ImportError:
            pass
    return None


def register_builtin_processes(container):
    # type: (AnyDatabaseContainer) -> None
    """Registers every ``builtin`` package to the processes database."""
    restapi_url = get_wps_restapi_base_url(container)
    builtin_apps_mapping = _get_builtin_reference_mapping(os.path.abspath(os.path.dirname(__file__)))
    builtin_processes = []
    for process_id, process_path in builtin_apps_mapping.items():
        process_info = get_process_definition({}, package=None, reference=process_path)
        process_url = "/".join([restapi_url, "processes", process_id])
        builtin_processes.append(Process(
            id=process_id,
            type=PROCESS_BUILTIN,
            abstract=_get_builtin_abstract(process_id, process_path),
            payload={"type": PROCESS_BUILTIN},
            package=process_info["package"],
            inputs=process_info["inputs"],
            outputs=process_info["outputs"],
            processDescriptionURL=process_url,
            executeEndpoint="/".join([process_url, "jobs"]),
            visibility=VISIBILITY_PUBLIC,
        ))

    # registration of missing apps automatically applied with 'default_processes'
    get_db(container).get_store(StoreProcesses, default_processes=builtin_processes)
