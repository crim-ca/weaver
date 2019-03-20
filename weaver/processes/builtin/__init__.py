from weaver.database import get_db
from weaver.datatype import Process
from weaver.store.base import StoreProcesses
from weaver.processes.types import PROCESS_BUILTIN
from weaver.processes.wps_package import PACKAGE_EXTENSIONS, get_process_definition
from weaver.utils import clean_json_text_body, ows_context_href
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps_restapi.utils import get_wps_restapi_base_url
from cwltool.process import Process as ProcessCWL
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
            "executionUnit": [{"unit": process_info["package"]}],
        }
        process_payload["processDescription"]["process"].update(ows_context_href(process_url))
        builtin_processes.append(Process(
            id=process_id,
            type=PROCESS_BUILTIN,
            abstract=process_abstract,
            payload=process_payload,
            package=process_info["package"],
            inputs=process_info["inputs"],
            outputs=process_info["outputs"],
            processDescriptionURL=process_url,
            executeEndpoint="/".join([process_url, "jobs"]),
            visibility=VISIBILITY_PUBLIC,
        ))

    # registration of missing apps automatically applied with 'default_processes'
    get_db(container).get_store(StoreProcesses, default_processes=builtin_processes)


class BuiltinProcess(ProcessCWL):
    class BuiltinProcessJob(object):
        def __init__(self,
                     builder,          # type: Builder
                     script,           # type: Dict[Text, Text]
                     output_callback,  # type: Callable[[Any, Any], Any]
                     requirements,     # type: Dict[Text, Text]
                     hints,            # type: Dict[Text, Text]
                     outdir=None,      # type: Optional[Text]
                     tmpdir=None,      # type: Optional[Text]
                    ):  # type: (...) -> None
            self.builder = builder
            self.requirements = requirements
            self.hints = hints
            self.collect_outputs = None  # type: Optional[Callable[[Any], Any]]
            self.output_callback = output_callback
            self.outdir = outdir
            self.tmpdir = tmpdir
            self.script = script
            self.prov_obj = None  # type: Optional[CreateProvProfile]

        def run(self, runtimeContext):  # type: (RuntimeContext) -> None
            try:
                ev = self.builder.do_eval(self.script)
                normalizeFilesDirs(ev)
                self.output_callback(ev, "success")
            except Exception as err:
                _logger.warning(u"Failed to evaluate expression:\n%s",
                                err, exc_info=runtimeContext.debug)
                self.output_callback({}, "permanentFail")

    def job(self,
            job_order,         # type: Dict[Text, Text]
            output_callbacks,  # type: Callable[[Any, Any], Any]
            runtimeContext     # type: RuntimeContext
           ):
        # type: (...) -> Generator[ExpressionTool.ExpressionJob, None, None]
        builder = self._init_job(job_order, runtimeContext)

        job = ExpressionTool.ExpressionJob(
            builder, self.tool["expression"], output_callbacks,
            self.requirements, self.hints)
        job.prov_obj = runtimeContext.prov_obj
        yield job
