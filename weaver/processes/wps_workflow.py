import collections.abc
import json
import logging
import os
import pathlib
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
from weaver.processes.convert import is_cwl_complex_type
from weaver.utils import get_any_id, get_any_value
from weaver.wps.utils import get_wps_output_dir

if TYPE_CHECKING:
    from subprocess import Popen  # nosec: B404
    from typing import Any, Callable, List, MutableMapping, Optional

    from cwltool.builder import Builder
    from cwltool.pathmapper import PathMapper
    from cwltool.utils import CWLObjectType, CWLOutputType, JobsGeneratorType

    from weaver.processes.wps_package import WpsPackage
    from weaver.processes.wps_process_base import WpsProcessInterface
    from weaver.typedefs import (
        CWL_ExpectedOutputs,
        CWL_Output_Type,
        CWL_RequirementsList,
        CWL_Results,
        CWL_RuntimeInputsMap,
        CWL_ToolPathObject,
        JobResults
    )

    MonitorFunction = Optional[Callable[[Popen[str]], None]]

LOGGER = logging.getLogger(__name__)
DEFAULT_TMP_PREFIX = "tmp"

# Extend the supported process requirements
supportedProcessRequirements += [
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_APP_ESGF_CWT,
]


def default_make_tool(toolpath_object,  # type: CWL_ToolPathObject
                      loading_context,  # type: LoadingContext
                      package_process,  # type: WpsPackage
                      ):                # type: (...) -> ProcessCWL
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
            builtin_process_hints = [
                h.get("process") for h in toolpath_object.get("hints") or []
                if h.get("class", "").endswith(CWL_REQUIREMENT_APP_BUILTIN)
            ]
            if len(builtin_process_hints) == 1:
                return cast(BuiltinProcess, BuiltinProcess(toolpath_object, loading_context))
            return cast(WpsWorkflow, WpsWorkflow(toolpath_object, loading_context, package_process))
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
    # pylint: disable=W0201,attribute-defined-outside-init

    def __init__(self, toolpath_object, loading_context, package_process):
        # type: (CWL_ToolPathObject, LoadingContext, WpsPackage) -> None
        super(WpsWorkflow, self).__init__(toolpath_object, loading_context)
        self.prov_obj = loading_context.prov_obj
        self.package_process = package_process
        self.get_job_process_definition = self.package_process.get_job_process_definition

        # DockerRequirement is removed because we use our custom job which dispatch the processing to an ADES instead
        self.requirements = list(filter(lambda req: req["class"] != CWL_REQUIREMENT_APP_DOCKER, self.requirements))
        self.hints = list(filter(lambda req: req["class"] != CWL_REQUIREMENT_APP_DOCKER, self.hints))

    # pylint: disable=W0221,W0237 # naming using python like arguments
    def job(
        self,
        job_order,          # type: CWLObjectType
        output_callbacks,   # type: Callable[[Any, Any], Any]
        runtime_context,    # type: RuntimeContext
    ):                      # type: (...) -> JobsGeneratorType
        """
        Workflow job generator.

        :param job_order: inputs of the job submission
        :param output_callbacks: method to fetch step outputs and corresponding step details
        :param runtime_context: configs about execution environment
        :return:
        """
        job_name = uniquename(runtime_context.name or shortname(self.tool.get("id", "job")))

        # outdir must be served by the EMS because downstream step will need access to upstream steps output
        weaver_out_dir = get_wps_output_dir(self.package_process.settings)
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
            self.get_job_process_definition(job_name, job_order),
            self.tool["outputs"]
        )
        wps_workflow_job.prov_obj = self.prov_obj
        wps_workflow_job.successCodes = self.tool.get("successCodes")
        wps_workflow_job.temporaryFailCodes = self.tool.get("temporaryFailCodes")
        wps_workflow_job.permanentFailCodes = self.tool.get("permanentFailCodes")
        wps_workflow_job.outdir = builder.outdir
        wps_workflow_job.tmpdir = builder.tmpdir
        wps_workflow_job.stagedir = builder.stagedir

        # NOTE:
        #   Filter outputs to collect by leaving only 'complex' types, since the underlying step implemented by
        #   a "normal" 'CommandLineTool' doesn't know how to collect literals obtained from the remote process response.
        #   The literals will be collected by 'WpsWorkflowJob.collect_literal_outputs' to fill missing
        #   data values before resolving 'WpsWorkflowJob.collect_outputs' operations for File/Directory types.
        collectable_outputs = [
            out for out in self.tool["outputs"]
            if shortname(out["id"]) in wps_workflow_job.expected_outputs
        ]

        wps_workflow_job.collect_outputs = partial(
            self.collect_output_ports,
            collectable_outputs,
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

        .. note::
            Because the staging operation following remote :term:`Process` execution nests each output under a directory
            name matching respective output IDs, globs must be update with that modified nested directory as well.

        .. seealso::
            :meth:`weaver.processes.wps_process_base.WpsProcessInterface.stage_results`
        """
        if "outputBinding" in schema and "glob" in schema["outputBinding"]:
            glob = schema["outputBinding"]["glob"]
            glob_list = isinstance(glob, list)
            glob = glob if isinstance(glob, list) else [glob]
            out_id = shortname(schema["id"])
            glob_spec = []
            for glob_item in glob:
                if glob_item.startswith(outdir):
                    # CWL allows outputBinding to have relative or absolute starting with outdir.
                    # Anything else should be forbidden by the validator.
                    # (see ``glob`` under https://www.commonwl.org/v1.2/CommandLineTool.html#CommandOutputBinding)
                    # glob = outdir -> '.', which is identical to what CWL '<outdir>/<out_id>/.' expects for a dir entry
                    glob_item = os.path.relpath(glob_item, outdir)
                # if the glob had additional directory nesting, we must remove them, because the staging result
                # operation would have brought output file/dir back under the respective dir named by output ID
                glob_item = os.path.split(glob_item)[-1] or "."
                glob_spec.append(os.path.join(out_id, glob_item))
            schema["outputBinding"]["glob"] = glob_spec if glob_list else glob_spec[0]
        output = super(WpsWorkflow, self).collect_output(
            schema,
            builder,
            outdir,
            fs_access,
            compute_checksum=compute_checksum,
        )
        return output


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
        self.expected_outputs = {}      # type: CWL_ExpectedOutputs  # {id: glob-pattern}  # only File/Directory
        self._resolve_expected_output_files(expected_outputs)

    def _resolve_expected_output_files(self, expected_outputs):
        # type: (List[CWL_Output_Type]) -> None
        """
        Finds the ``{id: glob-pattern}`` for any eventual output files to collect from the :term:`Workflow` step.

        :param expected_outputs: All potential output definitions the step defines.
        :return: Resolved output locations to look for result files, considering the nested `Output-ID` path.
        """
        for output in expected_outputs:
            # There are 2 cases where an output must be collected from a path reference
            # 1. the output is itself a complex type (ie: CWL 'type: File|Directory')
            # 2. the output is a literal string with 'loadContents' and some evaluation from a file
            #    (e.g.: 'outputEval: $(self[0].contents)' or '$(inputs.<input_id>.contents')
            # In this 2nd case, the underlying "normal" 'CommandLineTool' step will have done the job for us.
            # Therefore, only need to worry about "real" File/Directory references to remap to WPS output dir.
            if is_cwl_complex_type(output):
                output_id = shortname(output["id"])
                glob_spec = output["outputBinding"]["glob"]
                glob_list = isinstance(glob_spec, list)
                out_globs = set()
                # When applications run by themselves, their output glob could be very
                # deeply nested to retrieve files under specific directory structures.
                # However, as Workflow step, those outputs would already have been collected
                # on the step output dir. The Workflow only needs the last part of the glob
                # to collect the staged out files without the nested directory hierarchy.
                for glob in glob_spec if glob_list else [glob_spec]:
                    # in case of Directory collection with '<dir>/', use '.' because cwltool replaces it by the outdir
                    out_glob = glob.split("/")[-1] or "."
                    out_glob = f"{output_id}/{out_glob}"
                    out_globs.add(out_glob)
                self.expected_outputs[output_id] = {
                    "type": output["type"],
                    "glob": out_globs if glob_list else list(out_globs)[0],
                }

    def _retrieve_secret_inputs(self, runtime_context):
        # type: (RuntimeContext) -> CWL_RuntimeInputsMap
        """
        Retrieve the job inputs with reverse resolution of any secrets defined in the store.

        Because the remote :term:`Process` (of any type) will not have the local runtime store definition,
        they cannot themselves resolve the original values.

        .. warning::
            Any following steps after this call must be mindful of what they log to avoid leaking secrets.
        """
        inputs = self.builder.job
        if not runtime_context.secret_store:
            return inputs
        for name in list(inputs):
            inputs[name] = runtime_context.secret_store.retrieve(inputs[name])
        return inputs

    def collect_literal_outputs(self, results):
        # type: (JobResults) -> CWL_Results
        """
        Collects the literal values provided as output.

        Typical :term:`CWL` applications (i.e: the ones not implemented by derived :class:`WpsProcessInterface`)
        will only return outputs from ``File``/``Directory``, or a *literal* inferred by some JavaScript expression
        or loaded by contents from another source. Because of this, *literal* never needs to be collected in these
        cases. Since a :term:`Process` derived from :class:`WpsProcessInterface` can directly return literal data,
        their values must be explicit chained for following :term:`Workflow` steps.

        :param results: The original :term:`Job` results obtained from the remote :term:`Process`.
        :return: Collected literal outputs.
        """
        outputs = {}  # type: CWL_Results
        for res in results:
            res_id = get_any_id(res)
            if res_id not in self.expected_outputs:
                outputs[res_id] = get_any_value(res)
        return outputs

    # pylint: disable=W0221,W0237 # naming using python like arguments
    def _execute(
        self,
        runtime,                # type: List[str]
        env,                    # type: MutableMapping[str, str]
        runtime_context,        # type: RuntimeContext
        monitor_function=None,  # type: MonitorFunction
    ):                          # type: (...) -> None
        """
        Execute the :term:`WPS` :term:`Process` defined as :term:`Workflow` step and chains their intermediate results.
        """
        cwl_inputs = self._retrieve_secret_inputs(runtime_context)
        results = self.wps_process.execute(cwl_inputs, self.outdir, self.expected_outputs)
        outputs = self.collect_literal_outputs(results)

        # NOTE:
        #   Use the 'cwl.output.json' for custom outputs to pass the literal data.
        #   Since 'collect_outputs -> partial(collect_output_ports, ...)' will raise if required outputs are missing
        #   after collecting all 'expected_outputs' of 'File/Directory' type, they must be injected before calling it.
        #   However, we cannot pass the literal data directly as input because of the partial definition implemented
        #   by the other class.
        cwl_output_file = pathlib.Path(self.outdir, "cwl.output.json")
        try:
            if outputs:
                with open(cwl_output_file, mode="w", encoding="utf-8") as out_file:
                    json.dump(outputs, out_file)
            outputs = self.collect_outputs(self.outdir, 0)
        finally:
            cwl_output_file.unlink(missing_ok=True)

        self.output_callback(outputs, "success")
