import logging
import os
import sys
from importlib import import_module
from string import Template
from typing import TYPE_CHECKING

import yaml
from cwltool.command_line_tool import CommandLineTool
from cwltool.docker import DockerCommandLineJob
from cwltool.job import CommandLineJob, JobBase
from cwltool.singularity import SingularityCommandLineJob

from weaver import WEAVER_ROOT_DIR
from weaver.database import get_db
from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError, PackageNotFound, ProcessNotAccessible, ProcessNotFound
from weaver.execute import ExecuteControlOption
from weaver.processes.constants import CWL_REQUIREMENT_APP_BUILTIN
from weaver.processes.types import ProcessType
from weaver.processes.wps_package import get_process_definition
from weaver.store.base import StoreProcesses
from weaver.utils import clean_json_text_body, get_registry, ows_context_href
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Type, Union

    from cwltool.builder import Builder
    from cwltool.context import RuntimeContext
    from cwltool.pathmapper import PathMapper

    from weaver.typedefs import CWL, JSON, AnyRegistryContainer, CWL_RequirementsList, TypedDict

    BuiltinResourceMap = TypedDict("BuiltinResourceMap", {
        "package": str,
        "payload": JSON
    }, total=True)

LOGGER = logging.getLogger(__name__)


__all__ = [
    "BuiltinProcess",
    "register_builtin_processes"
]


def _get_builtin_reference_mapping(root):
    # type: (str) -> Dict[str, BuiltinResourceMap]
    """
    Generates a mapping of `reference` to actual ``builtin`` package file path.
    """
    builtin_names = [_pkg for _pkg in os.listdir(root) if os.path.splitext(_pkg)[-1] == ".cwl"]
    refs = {
        os.path.splitext(_pkg)[0]: {"package": os.path.join(root, _pkg), "payload": {}}
        for _pkg in builtin_names
    }
    for builtin_ref in refs.values():
        for ext in [".yml", ".yaml", ".json"]:
            payload_ref = os.path.splitext(builtin_ref["package"])[0] + ext
            if os.path.isfile(payload_ref):
                with open(payload_ref, mode="r", encoding="utf-8") as f_payload:
                    builtin_ref["payload"] = yaml.safe_load(f_payload) or {}
                break
    return refs


def _get_builtin_metadata(process_id, process_path, meta_field, clean=False):
    # type: (str, str, str, bool) -> Union[str, None]
    """
    Retrieves the ``builtin`` process ``meta_field`` from its definition if it exists.
    """
    py_file = os.path.splitext(process_path)[0] + ".py"
    if os.path.isfile(py_file):
        try:
            mod = import_module(f"{__name__}.{process_id}")
            meta = getattr(mod, meta_field, None)
            if meta and isinstance(meta, str):
                return clean_json_text_body(meta) if clean else meta
        except ImportError:
            pass
    return None


def _replace_template(pkg, var, val):
    # type: (Union[CWL, str], str, str) -> CWL
    if isinstance(pkg, str):
        return Template(pkg).safe_substitute({var: val})  # type: ignore
    for key in pkg:  # type: str
        field = pkg[key]  # type: ignore
        if isinstance(field, list):
            for i, _ in enumerate(field):
                field[i] = _replace_template(field[i], var, val)
        elif isinstance(field, (dict, str)):
            pkg[key] = _replace_template(field, var, val)  # type: ignore
    return pkg


def _get_builtin_package(process_id, package):
    # type: (str, CWL) -> CWL
    """
    Updates the `CWL` with requirements to allow running a :data:`ProcessType.BUILTIN` process.

    Following modifications are applied:

    - Add `hints` section with :data:`CWL_REQUIREMENT_APP_BUILTIN`.
    - Replace references to environment variable :data:`WEAVER_ROOT_DIR` as needed.

    The `CWL` ``hints`` are employed to avoid error from the runner that doesn't know this requirement definition.
    The ``hints`` can be directly in the package definition without triggering validation errors.
    """
    if "hints" not in package:
        package["hints"] = {}
    package["hints"].update({CWL_REQUIREMENT_APP_BUILTIN: {"process": process_id}})

    # FIXME:
    #   fix base directory of command until bug fixed:
    #   https://github.com/common-workflow-language/cwltool/issues/668
    return _replace_template(package, "WEAVER_ROOT_DIR", WEAVER_ROOT_DIR)


def register_builtin_processes(container):
    # type: (AnyRegistryContainer) -> None
    """
    Registers every ``builtin`` CWL package to the processes database.

    CWL definitions must be located within the :mod:`weaver.processes.builtin` module.
    """
    restapi_url = get_wps_restapi_base_url(container)
    builtin_apps_mapping = _get_builtin_reference_mapping(os.path.abspath(os.path.dirname(__file__)))
    builtin_processes = []
    for process_id, process_data in builtin_apps_mapping.items():
        process_path = process_data["package"]
        process_desc = process_data["payload"]
        process_info = get_process_definition(process_desc, package=None, reference=process_path)
        process_url = "/".join([restapi_url, "processes", process_id])
        process_package = _get_builtin_package(process_id, process_info["package"])
        process_abstract = _get_builtin_metadata(process_id, process_path, "__doc__", clean=True)
        process_version = _get_builtin_metadata(process_id, process_path, "__version__")
        process_title = _get_builtin_metadata(process_id, process_path, "__title__")
        process_payload = {
            "processDescription": {
                "process": {
                    "id": process_id,
                    "type": ProcessType.BUILTIN,
                    "title": process_title,
                    "version": process_version,
                    "abstract": process_abstract,
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/builtinApplication",
            "executionUnit": [{"unit": process_package}],
        }
        process_payload["processDescription"]["process"].update(ows_context_href(process_url))
        builtin_processes.append(Process(
            id=process_id,
            type=ProcessType.BUILTIN,
            title=process_title,
            version=process_version,
            abstract=process_abstract,
            payload=process_payload,
            package=process_package,
            inputs=process_info["inputs"],
            outputs=process_info["outputs"],
            processDescriptionURL=process_url,
            processEndpointWPS1=get_wps_url(container),
            executeEndpoint="/".join([process_url, "jobs"]),
            jobControlOptions=ExecuteControlOption.values(),
            visibility=Visibility.PUBLIC,
        ))

    # registration of missing/updated apps automatically applied with 'default_processes'
    get_db(container).get_store(StoreProcesses, default_processes=builtin_processes)


class BuiltinProcessJobBase(CommandLineJob):
    def __init__(self, builder, joborder, make_path_mapper, requirements, hints, name):
        # type: (Builder, JSON, Callable[..., PathMapper], CWL_RequirementsList, CWL_RequirementsList, str) -> None
        process_hints = [h for h in hints if "process" in h]
        if not process_hints or len(process_hints) != 1:
            raise PackageNotFound("Could not extract referenced process in job.")
        self.process = process_hints[0]["process"]
        super(BuiltinProcessJobBase, self).__init__(builder, joborder, make_path_mapper, requirements, hints, name)

    def _validate_process(self):
        # type: () -> None
        try:
            registry = get_registry()
            store = get_db(registry).get_store(StoreProcesses)
            process = store.fetch_by_id(self.process)  # raise if not found
        except (ProcessNotAccessible, ProcessNotFound):
            raise PackageNotFound(f"Cannot find '{ProcessType.BUILTIN}' package for process '{self.process}'")
        if process.type != ProcessType.BUILTIN:
            raise PackageExecutionError(f"Invalid package is not of type '{ProcessType.BUILTIN}'")

    def _update_command(self):
        # type: () -> None
        if len(self.command_line) and self.command_line[0] == "python":
            LOGGER.debug("Mapping generic builtin Python command to environment: [python] => [%s]", sys.executable)
            self.command_line[0] = sys.executable

    # pylint: disable=W0221,W0237  # naming using python like arguments
    def run(self, runtime_context, **kwargs):
        # type: (RuntimeContext, **Any) -> None
        try:
            self._validate_process()
            self._update_command()
            super(BuiltinProcessJobBase, self).run(runtime_context, **kwargs)
        except Exception as err:
            LOGGER.warning(u"Failed to run process:\n%s", err, exc_info=runtime_context.debug)
            self.output_callback({}, "permanentFail")


class BuiltinProcessJobDocker(BuiltinProcessJobBase, DockerCommandLineJob):
    pass


class BuiltinProcessJobSingularity(BuiltinProcessJobBase, SingularityCommandLineJob):
    pass


# pylint: disable=W0221,W0237 # naming using python like arguments
class BuiltinProcess(CommandLineTool):
    def make_job_runner(self, runtime_context):
        # type: (RuntimeContext) -> Type[JobBase]
        job = super(BuiltinProcess, self).make_job_runner(runtime_context)
        if issubclass(job, DockerCommandLineJob):
            return BuiltinProcessJobDocker
        if issubclass(job, SingularityCommandLineJob):
            return BuiltinProcessJobSingularity
        return BuiltinProcessJobBase
