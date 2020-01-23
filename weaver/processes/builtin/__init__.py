import logging
import os
from importlib import import_module
from string import Template
from typing import TYPE_CHECKING

import six
from cwltool.command_line_tool import CommandLineTool
from cwltool.docker import DockerCommandLineJob
from cwltool.job import CommandLineJob, JobBase
from cwltool.singularity import SingularityCommandLineJob
from pyramid_celery import celery_app as app

from weaver import WEAVER_ROOT_DIR
from weaver.database import get_db
from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError, PackageNotFound, ProcessNotAccessible, ProcessNotFound
from weaver.processes.constants import CWL_REQUIREMENT_APP_BUILTIN
from weaver.processes.types import PROCESS_BUILTIN
from weaver.processes.wps_package import PACKAGE_EXTENSIONS, get_process_definition
from weaver.store.base import StoreProcesses
from weaver.utils import clean_json_text_body, ows_context_href
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps import get_wps_url
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from weaver.typedefs import AnyDatabaseContainer, CWL   # noqa: F401
    from cwltool.context import RuntimeContext              # noqa: F401
    from typing import AnyStr, Dict, Type, Union            # noqa: F401

LOGGER = logging.getLogger(__name__)


__all__ = [
    "BuiltinProcess",
    "register_builtin_processes"
]


def _get_builtin_reference_mapping(root):
    # type: (AnyStr) -> Dict[AnyStr, AnyStr]
    """Generates a mapping of `reference` to actual ``builtin`` package file path."""
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


def _replace_template(pkg, var, val):
    # type: (CWL, AnyStr, AnyStr) -> CWL
    if isinstance(pkg, six.string_types):
        return Template(pkg).safe_substitute({var: val})
    for k in pkg:
        if isinstance(pkg[k], list):
            for i, pkg_i in enumerate(pkg[k]):
                pkg[k][i] = _replace_template(pkg[k][i], var, val)
        elif isinstance(pkg[k], (dict, six.string_types)):
            pkg[k] = _replace_template(pkg[k], var, val)
    return pkg


def _get_builtin_package(process_id, package):
    # type: (AnyStr, CWL) -> CWL
    """
    Updates the `CWL` with following requirements to allow running a ``PROCESS_BUILTIN``:
        - add `hints` section with ``CWL_REQUIREMENT_APP_BUILTIN``
        - replace ``WEAVER_ROOT_DIR`` as needed
    """
    if "hints" not in package:
        package["hints"] = dict()
    package["hints"].update({CWL_REQUIREMENT_APP_BUILTIN: {"process": process_id}})

    # FIXME:
    #   fix base directory of command until bug fixed:
    #   https://github.com/common-workflow-language/cwltool/issues/668
    return _replace_template(package, "WEAVER_ROOT_DIR", WEAVER_ROOT_DIR)


def register_builtin_processes(container):
    # type: (AnyDatabaseContainer) -> None
    """Registers every ``builtin`` CWL package to the processes database.

    CWL definitions must be located within the :py:mod:``weaver.processes.builtin`` module.
    """
    restapi_url = get_wps_restapi_base_url(container)
    builtin_apps_mapping = _get_builtin_reference_mapping(os.path.abspath(os.path.dirname(__file__)))
    builtin_processes = []
    for process_id, process_path in builtin_apps_mapping.items():
        process_info = get_process_definition({}, package=None, reference=process_path)
        process_url = "/".join([restapi_url, "processes", process_id])
        process_package = _get_builtin_package(process_id, process_info["package"])
        process_abstract = _get_builtin_abstract(process_id, process_path)
        process_payload = {
            "processDescription": {
                "process": {
                    "id": process_id,
                    "type": PROCESS_BUILTIN,
                    "abstract": process_abstract,
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/builtinApplication",
            "executionUnit": [{"unit": process_package}],
        }
        process_payload["processDescription"]["process"].update(ows_context_href(process_url))
        builtin_processes.append(Process(
            id=process_id,
            type=PROCESS_BUILTIN,
            abstract=process_abstract,
            payload=process_payload,
            package=process_package,
            inputs=process_info["inputs"],
            outputs=process_info["outputs"],
            processDescriptionURL=process_url,
            processEndpointWPS1=get_wps_url(container),
            executeEndpoint="/".join([process_url, "jobs"]),
            visibility=VISIBILITY_PUBLIC,
        ))

    # registration of missing/updated apps automatically applied with 'default_processes'
    get_db(container).get_store(StoreProcesses, default_processes=builtin_processes)


class BuiltinProcessJobBase(CommandLineJob):
    # noinspection PyUnusedLocal
    def __init__(self, builder, joborder, make_path_mapper, requirements, hints, name):
        self.process = [h.get("process") for h in hints][0]
        super(BuiltinProcessJobBase, self).__init__(builder, joborder, make_path_mapper, requirements, hints, name)

    def _validate_process(self):
        try:
            store = get_db(app).get_store(StoreProcesses)
            process = store.fetch_by_id(self.process)  # raise if not found
        except (ProcessNotAccessible, ProcessNotFound):
            raise PackageNotFound("Cannot find '{}' package for process '{}'".format(PROCESS_BUILTIN, self.process))
        if process.type != PROCESS_BUILTIN:
            raise PackageExecutionError("Invalid package is not of type '{}'".format(PROCESS_BUILTIN))

    def run(self, runtime_context):  # type: (RuntimeContext) -> None
        try:
            self._validate_process()
            super(BuiltinProcessJobBase, self).run(runtime_context)
        except Exception as err:
            LOGGER.warning(u"Failed to run process:\n%s", err, exc_info=runtime_context.debug)
            self.output_callback({}, "permanentFail")


class BuiltinProcessJobDocker(BuiltinProcessJobBase, DockerCommandLineJob):
    pass


class BuiltinProcessJobSingularity(BuiltinProcessJobBase, SingularityCommandLineJob):
    pass


class BuiltinProcess(CommandLineTool):
    def make_job_runner(self, runtime_context):
        # type: (RuntimeContext) -> Type[JobBase]
        job = super(BuiltinProcess, self).make_job_runner(runtime_context)
        if issubclass(job, DockerCommandLineJob):
            return BuiltinProcessJobDocker
        if issubclass(job, SingularityCommandLineJob):
            return BuiltinProcessJobSingularity
        return BuiltinProcessJobBase
