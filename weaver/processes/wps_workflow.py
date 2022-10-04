import collections.abc
import logging
import os
import tempfile
from functools import partial
from typing import TYPE_CHECKING, cast  # these are actually used in the code

from cwltool import command_line_tool
from cwltool.context import LoadingContext, RuntimeContext, getdefault
from cwltool.errors import WorkflowException
from cwltool.job import CommandLineJob
from cwltool.process import Process as ProcessCWL, shortname, supportedProcessRequirements, uniquename
from cwltool.stdfsaccess import StdFsAccess
from cwltool.workflow import Workflow

from weaver.processes.builtin import BuiltinProcess
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1
)
from weaver.processes.convert import is_cwl_file_type
from weaver.utils import get_settings
from weaver.wps.utils import get_wps_output_dir

if TYPE_CHECKING:
    from subprocess import Popen  # nosec: B404
    from typing import Any, Callable, Generator, List, MutableMapping, Optional

    from cwltool.builder import Builder
    from cwltool.pathmapper import PathMapper
    from cwltool.utils import CWLObjectType, CWLOutputType, JobsGeneratorType

    from weaver.typedefs import (
        CWL_ExpectedOutputs,
        CWL_Output_Type,
        CWL_RequirementsList,
        CWL_ToolPathObject,
        JobProcessDefinitionCallback,
    )
    from weaver.processes.wps_process_base import WpsProcessInterface

    MonitorFunction = Optional[Callable[[Popen[str]], None]]

LOGGER = logging.getLogger(__name__)
DEFAULT_TMP_PREFIX = "tmp"

# Extend the supported process requirements
supportedProcessRequirements += [
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_APP_ESGF_CWT,
]


def default_make_tool(toolpath_object,              # type: CWL_ToolPathObject
                      loading_context,              # type: LoadingContext
                      get_job_process_definition,   # type: JobProcessDefinitionCallback
                      ):                            # type: (...) -> ProcessCWL
    """
    Generate the tool class object from the :term:`CWL` definition to handle its execution.

    .. warning::
        Package :mod:`cwltool` introduces explicit typing definitions with :mod:`mypy_extensions`.
        This can cause ``TypeError("interpreted classes cannot inherit from compiled")`` when using
        :class:`cwltool.process.Process` as base class for our custom definitions below.
        To avoid the error, we must enforce the type using :func:`cast`.
    """
    if not isinstance(toolpath_object, collections.abc.MutableMapping):
        raise WorkflowException(f"Not a dict: '{toolpath_object}'")
    if "class" in toolpath_object:
        if toolpath_object["class"] == "CommandLineTool":
            builtin_process_hints = [h.get("process") for h in toolpath_object.get("hints")
                                     if h.get("class", "").endswith(CWL_REQUIREMENT_APP_BUILTIN)]
            if len(builtin_process_hints) == 1:
                return cast(BuiltinProcess, BuiltinProcess(toolpath_object, loading_context))
            return cast(WpsWorkflow, WpsWorkflow(toolpath_object, loading_context, get_job_process_definition))
        if toolpath_object["class"] == "ExpressionTool":
            return command_line_tool.ExpressionTool(toolpath_object, loading_context)
        if toolpath_object["class"] == "Workflow":
            return Workflow(toolpath_object, loading_context)

    tool = toolpath_object["id"]
    raise WorkflowException(
        f"Missing or invalid 'class' field in {tool}, expecting one of: CommandLineTool, ExpressionTool, Workflow"
    )


class WpsWorkflow(command_line_tool.CommandLineTool):
    """
    Definition of a `CWL` ``workflow`` that can execute ``WPS`` application packages as intermediate job steps.

    Steps are expected to be defined as individual :class:`weaver.processes.wps_package.WpsPackage` references.
    """

    # imposed by original CWL implementation
    # pylint: disable=C0103,invalid-name
    # pylint: disable=W0201,attribute-defined-outside-init

    def __init__(self, toolpath_object, loading_context, get_job_process_definition):
        # type: (CWL_ToolPathObject, LoadingContext, JobProcessDefinitionCallback) -> None
        super(WpsWorkflow, self).__init__(toolpath_object, loading_context)
        self.prov_obj = loading_context.prov_obj
        self.get_job_process_definition = get_job_process_definition

        # DockerRequirement is removed because we use our custom job which dispatch the processing to an ADES instead
        self.requirements = list(filter(lambda req: req["class"] != CWL_REQUIREMENT_APP_DOCKER, self.requirements))
        self.hints = list(filter(lambda req: req["class"] != CWL_REQUIREMENT_APP_DOCKER, self.hints))

    # pylint: disable=W0221,W0237 # naming using python like arguments
    def job(self,
            job_order,          # type: CWLObjectType
            output_callbacks,   # type: Callable[[Any, Any], Any]
            runtime_context,    # type: RuntimeContext
            ):                  # type: (...) -> JobsGeneratorType
        """
        Workflow job generator.

        :param job_order: inputs of the job submission
        :param output_callbacks: method to fetch step outputs and corresponding step details
        :param runtime_context: configs about execution environment
        :return:
        """
        job_name = uniquename(runtime_context.name or shortname(self.tool.get("id", "job")))

        # outdir must be served by the EMS because downstream step will need access to upstream steps output
        weaver_out_dir = get_wps_output_dir(get_settings())
        runtime_context.outdir = tempfile.mkdtemp(
            prefix=getdefault(runtime_context.tmp_outdir_prefix, DEFAULT_TMP_PREFIX),
            dir=weaver_out_dir
        )
        builder = self._init_job(job_order, runtime_context)

        # `job_name` is the step name and `job_order` is the actual step inputs
        wps_workflow_job = WpsWorkflowJob(
            builder,
            builder.job,
            self.make_path_mapper,
            self.requirements,
            self.hints,
            job_name,
            self.get_job_process_definition(job_name, job_order, self.tool),
            self.tool["outputs"]
        )
        wps_workflow_job.prov_obj = self.prov_obj
        wps_workflow_job.successCodes = self.tool.get("successCodes")
        wps_workflow_job.temporaryFailCodes = self.tool.get("temporaryFailCodes")
        wps_workflow_job.permanentFailCodes = self.tool.get("permanentFailCodes")
        wps_workflow_job.outdir = builder.outdir
        wps_workflow_job.tmpdir = builder.tmpdir
        wps_workflow_job.stagedir = builder.stagedir
        wps_workflow_job.collect_outputs = partial(
            self.collect_output_ports,
            self.tool["outputs"],
            builder,
            compute_checksum=getdefault(runtime_context.compute_checksum, True),
            jobname=job_name,
            readers={}
        )
        wps_workflow_job.output_callback = output_callbacks

        yield wps_workflow_job

    def collect_output(
        self,
        schema,                 # type: CWLObjectType
        builder,                # type: Builder
        outdir,                 # type: str
        fs_access,              # type: StdFsAccess
        compute_checksum=True,  # type: bool
    ):                          # type: (...) -> Optional[CWLOutputType]
        """
        Collect outputs from the step :term:`Process` following its execution.

        .. note:
            When :term:`CWL` runner tries to forward ``step(i) outputs -> step(i+1) inputs``
            using :meth:`collect_outputs`, it expects exact ``outputBindings`` locations to be matched.
            In other words, a definition like ``outputBindings: {glob: outputs/*.txt}`` will generate results located
            in ``step(i)`` as ``"<tmp-workdir>/outputs/file.txt"`` and ``step(i+1)`` will look explicitly
            in ``"<tmp-workdir>/outputs`` using the ``glob`` pattern. Because each of our :term:`Process` in
            the workflow are distinct/remote entities, each one stages its outputs at different URL locations,
            not sharing the same *root directory*. When we stage intermediate results locally, the sub-dirs are lost.
            Therefore, they act like individual :term:`CWL` runner calls where the *final results* are moved back
            to the local directory for convenient access, but our *local directory* is the URL WPS-outputs location.
            To let :term:`CWL` :term:`Workflow` inter-steps mapping work as intended, we must remap the locations
            ignoring any nested dirs where the modified *outputBindings* definition will be able to match as if each
            step :term:`Process` outputs were generated locally.
        """
        if "outputBinding" in schema and "glob" in schema["outputBinding"]:
            glob = schema["outputBinding"]["glob"]
            glob = os.path.split(glob)[-1]
            schema["outputBinding"]["glob"] = glob
        output = super(WpsWorkflow, self).collect_output(
            schema,
            builder,
            outdir,
            fs_access,
            compute_checksum=compute_checksum,
        )
        return output or {}


class WpsWorkflowJob(CommandLineJob):
    def __init__(self,
                 builder,           # type: Builder
                 job_order,         # type: CWLObjectType
                 make_path_mapper,  # type: Callable[..., PathMapper]
                 requirements,      # type: CWL_RequirementsList
                 hints,             # type: CWL_RequirementsList
                 name,              # type: str
                 wps_process,       # type: WpsProcessInterface
                 expected_outputs,  # type: List[CWL_Output_Type]
                 ):                 # type: (...) -> None
        super(WpsWorkflowJob, self).__init__(builder, job_order, make_path_mapper, requirements, hints, name)

        # avoid error on builder 'revmap' when 'WpsWorkflow.collect_output' gets called
        builder.pathmapper = self.pathmapper

        self.wps_process = wps_process  # type: WpsProcessInterface
        self.expected_outputs = {}      # type: CWL_ExpectedOutputs  # {id: file-pattern}
        for output in expected_outputs:
            # TODO Should we support something else?
            if is_cwl_file_type(output):
                # Expecting output to look like this
                # output = {"id": "file:///tmp/random_path/process_name#output_id,
                #           "type": "File",
                #           "outputBinding": {"glob": output_name }
                #          }
                output_id = shortname(output["id"])
                output_glob = output["outputBinding"]["glob"].split("/")[-1]
                self.expected_outputs[output_id] = (
                    output_id + "/" + output_glob
                    if self.wps_process.stage_output_id_nested else
                    output_glob
                )

    # pylint: disable=W0221,W0237 # naming using python like arguments
    def _execute(self,
                 runtime,                   # type: List[str]
                 env,                       # type: MutableMapping[str, str]
                 runtime_context,           # type: RuntimeContext
                 monitor_function=None,     # type: MonitorFunction
                 ):                         # type: (...) -> None
        """
        Execute the :term:`WPS` :term:`Process` defined as :term:`Workflow` step and chains their intermediate results.
        """
        self.wps_process.execute(self.builder.job, self.outdir, self.expected_outputs)
        outputs = self.collect_outputs(self.outdir, 0)
        self.output_callback(outputs, "success")
