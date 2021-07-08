import collections.abc
import hashlib
import json
import locale
import logging
import os
import shutil
import tempfile
from functools import cmp_to_key, partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, MutableMapping, Text, cast  # these are actually used in the code

from cwltool import command_line_tool
from cwltool.builder import CONTENT_LIMIT, Builder, substitute
from cwltool.context import LoadingContext, RuntimeContext, getdefault
from cwltool.errors import WorkflowException
from cwltool.job import JobBase, relink_initialworkdir
from cwltool.pathmapper import adjustDirObjs, adjustFileObjs, get_listing, trim_listing, visit_class
from cwltool.process import (
    Process as ProcessCWL,
    compute_checksums,
    normalizeFilesDirs,
    shortname,
    supportedProcessRequirements,
    uniquename
)
from cwltool.stdfsaccess import StdFsAccess
from cwltool.utils import aslist, bytes2str_in_dicts, onWindows
from cwltool.workflow import Workflow
from pyramid_celery import celery_app as app
from schema_salad import validate
from schema_salad.sourceline import SourceLine

from weaver.processes.builtin import BuiltinProcess
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1
)
from weaver.processes.convert import is_cwl_file_type
from weaver.utils import get_settings, make_dirs, now
from weaver.wps.utils import get_wps_output_dir

if TYPE_CHECKING:
    from typing import Any, Dict, Generator, List, Optional, Set, Union
    from cwltool.command_line_tool import OutputPorts
    from cwltool.provenance import ProvenanceProfile
    from threading import Lock as ThreadLock
    from weaver.typedefs import AnyValue, ExpectedOutputType, GetJobProcessDefinitionFunction, ToolPathObjectType
    from weaver.processes.wps_process_base import WpsProcessInterface

LOGGER = logging.getLogger(__name__)
DEFAULT_TMP_PREFIX = "tmp"

# TODO: The code started as a copy of the class cwltool/command_line_tool.py,
#       and still has useless code in the context of a WPS workflow

# Extend the supported process requirements
supportedProcessRequirements += [
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_APP_ESGF_CWT,
]


def default_make_tool(toolpath_object,              # type: ToolPathObjectType
                      loading_context,              # type: LoadingContext
                      get_job_process_definition,   # type: GetJobProcessDefinitionFunction
                      ):                            # type: (...) -> ProcessCWL
    if not isinstance(toolpath_object, collections.abc.MutableMapping):
        raise WorkflowException(u"Not a dict: '%s'" % toolpath_object)
    if "class" in toolpath_object:
        if toolpath_object["class"] == "CommandLineTool":
            builtin_process_hints = [h.get("process") for h in toolpath_object.get("hints")
                                     if h.get("class", "").endswith(CWL_REQUIREMENT_APP_BUILTIN)]
            if len(builtin_process_hints) == 1:
                return BuiltinProcess(toolpath_object, loading_context)
            return WpsWorkflow(toolpath_object, loading_context, get_job_process_definition)
        if toolpath_object["class"] == "ExpressionTool":
            return command_line_tool.ExpressionTool(toolpath_object, loading_context)
        if toolpath_object["class"] == "Workflow":
            return Workflow(toolpath_object, loading_context)

    raise WorkflowException(
        u"Missing or invalid 'class' field in %s, expecting one of: CommandLineTool, ExpressionTool, Workflow" %
        toolpath_object["id"])


class CallbackJob(object):
    def __init__(self, job, output_callback, cachebuilder, jobcache):
        # type: (WpsWorkflow, Callable[[Any, Any], Any], Builder, Text) -> None
        self.job = job
        self.output_callback = output_callback
        self.cache_builder = cachebuilder
        self.output_dir = jobcache
        self.prov_obj = None  # type: Optional[ProvenanceProfile]

    def run(self, loading_context):
        # type: (RuntimeContext) -> None
        self.output_callback(self.job.collect_output_ports(
            self.job.tool["outputs"],
            self.cache_builder,
            self.output_dir,
            getdefault(loading_context.compute_checksum, True)), "success")


class WpsWorkflow(ProcessCWL):
    """
    Definition of a ``CWL`` ``workflow`` that can execute ``WPS`` application packages as defined by
    :class:`weaver.processes.wps_package.WpsPackage` as job steps.
    """

    def __init__(self, toolpath_object, loading_context, get_job_process_definition):
        # type: (Dict[Text, Any], LoadingContext, GetJobProcessDefinitionFunction) -> None
        super(WpsWorkflow, self).__init__(toolpath_object, loading_context)
        self.prov_obj = loading_context.prov_obj
        self.get_job_process_definition = get_job_process_definition

        # DockerRequirement is removed because we use our custom job which dispatch the processing to an ADES instead
        self.requirements = list(filter(lambda req: req["class"] != CWL_REQUIREMENT_APP_DOCKER, self.requirements))
        self.hints = list(filter(lambda req: req["class"] != CWL_REQUIREMENT_APP_DOCKER, self.hints))

    # pylint: disable=W0221,arguments-differ    # naming using python like arguments
    def job(self,
            joborder,           # type: Dict[Text, AnyValue]
            output_callbacks,   # type: Callable[[Any, Any], Any]
            runtime_context,    # type: RuntimeContext
            ):                  # type: (...) -> Generator[Union[JobBase, CallbackJob], None, None]
        """
        Workflow job generator.

        :param joborder: inputs of the job submission
        :param output_callbacks: method to fetch step outputs and corresponding step details
        :param runtime_context: configs about execution environment
        :return:
        """
        require_prefix = ""
        if self.metadata["cwlVersion"] == "v1.0":
            require_prefix = "http://commonwl.org/cwltool#"

        jobname = uniquename(runtime_context.name or shortname(self.tool.get("id", "job")))

        # outdir must be served by the EMS because downstream step will need access to upstream steps output
        weaver_out_dir = get_wps_output_dir(get_settings(app))
        runtime_context.outdir = tempfile.mkdtemp(
            prefix=getdefault(runtime_context.tmp_outdir_prefix, DEFAULT_TMP_PREFIX),
            dir=weaver_out_dir)
        builder = self._init_job(joborder, runtime_context)

        # `jobname` is the step name and `joborder` is the actual step inputs
        wps_workflow_job = WpsWorkflowJob(builder, builder.job, self.requirements, self.hints, jobname,
                                          self.get_job_process_definition(jobname, joborder, self.tool),
                                          self.tool["outputs"])
        wps_workflow_job.prov_obj = self.prov_obj
        wps_workflow_job.successCodes = self.tool.get("successCodes")
        wps_workflow_job.temporaryFailCodes = self.tool.get("temporaryFailCodes")
        wps_workflow_job.permanentFailCodes = self.tool.get("permanentFailCodes")

        # TODO Taken from command_line_tool.py maybe this could let us use the revmap if required at all
        # reffiles = copy.deepcopy(builder.files)
        # builder.pathmapper = self.make_path_mapper(
        #     reffiles, builder.stagedir, runtimeContext, True)
        # builder.requirements = wps_workflow_job.requirements

        wps_workflow_job.outdir = builder.outdir
        wps_workflow_job.tmpdir = builder.tmpdir
        wps_workflow_job.stagedir = builder.stagedir

        readers = {}  # type: Dict[Text, Any]
        timelimit = self.get_requirement(require_prefix + "TimeLimit")[0]
        if timelimit:
            with SourceLine(timelimit, "timelimit", validate.ValidationException):
                wps_workflow_job.timelimit = builder.do_eval(timelimit["timelimit"])
                if not isinstance(wps_workflow_job.timelimit, int) or wps_workflow_job.timelimit < 0:
                    raise Exception("timelimit must be an integer >= 0, got: %s" % wps_workflow_job.timelimit)

        wps_workflow_job.collect_outputs = partial(
            self.collect_output_ports, self.tool["outputs"], builder,
            compute_checksum=getdefault(runtime_context.compute_checksum, True),
            jobname=jobname,
            readers=readers)
        wps_workflow_job.output_callback = output_callbacks

        yield wps_workflow_job

    def collect_output_ports(self,
                             ports,                  # type: Set[Dict[Text, Any]]
                             builder,                # type: Builder
                             outdir,                 # type: Text
                             compute_checksum=True,  # type: bool
                             jobname="",             # type: Text
                             readers=None            # type: Dict[Text, Any]
                             ):                      # type: (...) -> OutputPorts
        ret = {}  # type: OutputPorts
        debug = LOGGER.isEnabledFor(logging.DEBUG)
        try:
            fs_access = builder.make_fs_access(outdir)
            custom_output = fs_access.join(outdir, "cwl.output.json")
            if fs_access.exists(custom_output):
                with fs_access.open(custom_output, "r") as f:
                    ret = json.load(f)
                if debug:
                    LOGGER.debug(u"Raw output from %s: %s", custom_output, json.dumps(ret, indent=4))
            else:
                for i, port in enumerate(ports):
                    def make_workflow_exception(msg):
                        return WorkflowException(
                            u"Error collecting output for parameter '%s':\n%s"
                            % (shortname(port["id"]), msg))
                    with SourceLine(ports, i, make_workflow_exception, debug):
                        fragment = shortname(port["id"])
                        ret[fragment] = self.collect_output(port, builder, outdir, fs_access,
                                                            compute_checksum=compute_checksum)
            if ret:
                # revmap = partial(command_line_tool.revmap_file, builder, outdir)
                adjustDirObjs(ret, trim_listing)

                # TODO: Attempt to avoid a crash because the revmap fct is not functional
                #       (intend for a docker usage only?)
                # visit_class(ret, ("File", "Directory"), cast(Callable[[Any], Any], revmap))
                visit_class(ret, ("File", "Directory"), command_line_tool.remove_path)
                normalizeFilesDirs(ret)
                visit_class(ret, ("File", "Directory"), partial(command_line_tool.check_valid_locations, fs_access))

                if compute_checksum:
                    adjustFileObjs(ret, partial(compute_checksums, fs_access))

            validate.validate_ex(
                self.names.get_name("outputs_record_schema", ""), ret,
                strict=False, logger=LOGGER)
            if ret is not None and builder.mutation_manager is not None:
                adjustFileObjs(ret, builder.mutation_manager.set_generation)
            return ret if ret is not None else {}
        except validate.ValidationException as exc:
            raise WorkflowException("Error validating output record: {!s}\nIn:\n{}"
                                    .format(exc, json.dumps(ret, indent=4)))
        finally:
            if builder.mutation_manager and readers:
                for reader in readers.values():
                    builder.mutation_manager.release_reader(jobname, reader)

    def collect_output(self,
                       schema,                # type: Dict[Text, Any]
                       builder,               # type: Builder
                       outdir,                # type: Text
                       fs_access,             # type: StdFsAccess
                       compute_checksum=True  # type: bool
                       ):
        # type: (...) -> Optional[Union[Dict[Text, Any], List[Union[Dict[Text, Any], Text]]]]
        result = []  # type: List[Any]
        empty_and_optional = False
        debug = LOGGER.isEnabledFor(logging.DEBUG)
        if "outputBinding" in schema:
            binding = schema["outputBinding"]
            globpatterns = []  # type: List[Text]

            revmap = partial(command_line_tool.revmap_file, builder, outdir)

            if "glob" in binding:
                with SourceLine(binding, "glob", WorkflowException, debug):
                    for glob in aslist(binding["glob"]):
                        glob = builder.do_eval(glob)
                        if glob:
                            globpatterns.extend(aslist(glob))

                    for glob in globpatterns:
                        if glob.startswith(outdir):
                            glob = glob[len(outdir) + 1:]
                        elif glob == ".":
                            glob = outdir
                        elif glob.startswith("/"):
                            raise WorkflowException("glob patterns must not start with '/'")
                        try:
                            prefix = fs_access.glob(outdir)
                            key = cmp_to_key(cast(Callable[[Text, Text], int], locale.strcoll))

                            # In case of stdout.log or stderr.log file not created
                            if "stdout" in self.tool and "stderr" in self.tool \
                                    and glob in (self.tool["stdout"], self.tool["stderr"]):
                                filepath = Path(fs_access.join(outdir, glob))
                                if not filepath.is_file():
                                    Path(filepath).touch()

                            result.extend([{
                                "location": g,
                                "path": fs_access.join(builder.outdir, g[len(prefix[0])+1:]),
                                "basename": os.path.basename(g),
                                "nameroot": os.path.splitext(os.path.basename(g))[0],
                                "nameext": os.path.splitext(os.path.basename(g))[1],
                                "class": "File" if fs_access.isfile(g) else "Directory"
                            } for g in sorted(fs_access.glob(fs_access.join(outdir, glob)), key=key)])
                        except (OSError, IOError) as exc:
                            LOGGER.warning(Text(exc))
                        except Exception:
                            LOGGER.exception("Unexpected error from fs_access")
                            raise

                for files in result:
                    rfile = files.copy()
                    # TODO This function raise an exception and seems to be related to docker (which is not used here)
                    # revmap(rfile)
                    if files["class"] == "Directory":
                        load_listing = builder.loadListing or (binding and binding.get("loadListing"))
                        if load_listing and load_listing != "no_listing":
                            get_listing(fs_access, files, (load_listing == "deep_listing"))
                    else:
                        with fs_access.open(rfile["location"], "rb") as f:
                            contents = b""
                            if binding.get("loadContents") or compute_checksum:
                                contents = f.read(CONTENT_LIMIT)
                            if binding.get("loadContents"):
                                files["contents"] = contents.decode("utf-8")
                            if compute_checksum:
                                checksum = hashlib.sha1()   # nosec: B303
                                while contents != b"":
                                    checksum.update(contents)
                                    contents = f.read(1024 * 1024)
                                files["checksum"] = "sha1$%s" % checksum.hexdigest()
                            f.seek(0, 2)
                            file_size = f.tell()
                        files["size"] = file_size

            optional = False
            single = False
            if isinstance(schema["type"], list):
                if "null" in schema["type"]:
                    optional = True
                if "File" in schema["type"] or "Directory" in schema["type"]:
                    single = True
            elif schema["type"] == "File" or schema["type"] == "Directory":
                single = True

            if "outputEval" in binding:
                with SourceLine(binding, "outputEval", WorkflowException, debug):
                    result = builder.do_eval(binding["outputEval"], context=result)

            if single:
                if not result and not optional:
                    with SourceLine(binding, "glob", WorkflowException, debug):
                        raise WorkflowException("Did not find output file with glob pattern: '{}'".format(globpatterns))
                elif not result and optional:
                    pass
                elif isinstance(result, list):
                    if len(result) > 1:
                        raise WorkflowException("Multiple matches for output item that is a single file.")
                    result = result[0]

            if "secondaryFiles" in schema:
                with SourceLine(schema, "secondaryFiles", WorkflowException, debug):
                    for primary in aslist(result):
                        if isinstance(primary, dict):
                            primary.setdefault("secondaryFiles", [])
                            pathprefix = primary["path"][0:primary["path"].rindex("/")+1]
                            for file in aslist(schema["secondaryFiles"]):
                                if isinstance(file, dict) or "$(" in file or "${" in file:
                                    sfpath = builder.do_eval(file, context=primary)
                                    subst = False
                                else:
                                    sfpath = file
                                    subst = True
                                for sfitem in aslist(sfpath):
                                    if isinstance(sfitem, str):
                                        if subst:
                                            sfitem = {"path": substitute(primary["path"], sfitem)}
                                        else:
                                            sfitem = {"path": pathprefix+sfitem}
                                    if "path" in sfitem and "location" not in sfitem:
                                        revmap(sfitem)
                                    if fs_access.isfile(sfitem["location"]):
                                        sfitem["class"] = "File"
                                        primary["secondaryFiles"].append(sfitem)
                                    elif fs_access.isdir(sfitem["location"]):
                                        sfitem["class"] = "Directory"
                                        primary["secondaryFiles"].append(sfitem)

            if "format" in schema:
                for primary in aslist(result):
                    primary["format"] = builder.do_eval(schema["format"], context=primary)

            # Ensure files point to local references outside of the run environment
            # TODO: Again removing revmap....
            # adjustFileObjs(result, revmap)

            if not result and optional:
                return None

        if not empty_and_optional and isinstance(schema["type"], dict) and schema["type"]["type"] == "record":
            out = {}
            for f in schema["type"]["fields"]:
                out[shortname(f["name"])] = self.collect_output(  # type: ignore
                    f, builder, outdir, fs_access,
                    compute_checksum=compute_checksum)
            return out
        return result


class WpsWorkflowJob(JobBase):  # noqa: N802
    def __init__(self,
                 builder,           # type: Builder
                 joborder,          # type: Dict[Text, Union[Dict[Text, Any], List, Text, None]]
                 requirements,      # type: List[Dict[Text, Text]]
                 hints,             # type: List[Dict[Text, Text]]
                 name,              # type: Text
                 wps_process,       # type: WpsProcessInterface
                 expected_outputs,  # type: List[ExpectedOutputType]
                 ):                 # type: (...) -> None
        super(WpsWorkflowJob, self).__init__(builder, joborder, None, requirements, hints, name)
        self.wps_process = wps_process
        self.results = None
        self.expected_outputs = {}  # type: Dict[str, str]  # {id: file-pattern}
        for output in expected_outputs:
            # TODO Should we support something else?
            if is_cwl_file_type(output):
                # Expecting output to look like this
                # output = {"id": "file:///tmp/random_path/process_name#output_id,
                #           "type": "File",
                #           "outputBinding": {"glob": output_name }
                #          }
                output_id = shortname(output["id"])
                self.expected_outputs[output_id] = output["outputBinding"]["glob"]

    def run(self,
            runtimeContext,     # type: RuntimeContext
            tmpdir_lock=None,   # type: Optional[ThreadLock]
            ):                  # type: (...) -> None

        make_dirs(self.tmpdir, exist_ok=True)
        env = self.environment
        vars_to_preserve = runtimeContext.preserve_environment
        if runtimeContext.preserve_entire_environment:
            vars_to_preserve = os.environ
        if vars_to_preserve is not None:
            for key, value in os.environ.items():
                if key in vars_to_preserve and key not in env:
                    # On Windows, subprocess env can't handle unicode.
                    env[key] = str(value) if onWindows() else value
        env["HOME"] = str(self.outdir) if onWindows() else self.outdir
        env["TMPDIR"] = str(self.tmpdir) if onWindows() else self.tmpdir
        if "PATH" not in env:
            env["PATH"] = str(os.environ["PATH"]) if onWindows() else os.environ["PATH"]
        if "SYSTEMROOT" not in env and "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = str(os.environ["SYSTEMROOT"]) if onWindows() else os.environ["SYSTEMROOT"]

        # stageFiles(self.pathmapper, ignoreWritable=True, symLink=True, secret_store=runtimeContext.secret_store)
        if self.generatemapper:
            # FIXME: see if this is needed... func doesn't exist anymore in cwltool 2.x
            # stageFiles(self.generatemapper, ignoreWritable=self.inplace_update,
            #            symLink=True, secret_store=runtimeContext.secret_store)
            relink_initialworkdir(self.generatemapper, self.outdir,
                                  self.builder.outdir, inplace_update=self.inplace_update)

        self.execute([], env, runtimeContext)

    # pylint: disable=W0221,arguments-differ    # naming using python like arguments
    def execute(self, runtime, env, runtime_context):   # noqa: E811
        # type: (List[Text], MutableMapping[Text, Text], RuntimeContext) -> None

        self.results = self.wps_process.execute(self.builder.job, self.outdir, self.expected_outputs)

        if self.joborder and runtime_context.research_obj:
            job_order = self.joborder
            assert runtime_context.prov_obj
            assert runtime_context.process_run_id
            runtime_context.prov_obj.used_artefacts(job_order, runtime_context.process_run_id, str(self.name))
        outputs = {}  # type: Dict[Text, Text]
        try:
            rcode = 0

            if self.successCodes:
                process_status = "success"
            elif self.temporaryFailCodes:
                process_status = "temporaryFail"
            elif self.permanentFailCodes:
                process_status = "permanentFail"
            elif rcode == 0:
                process_status = "success"
            else:
                process_status = "permanentFail"

            if self.generatefiles["listing"]:
                assert self.generatemapper is not None
                relink_initialworkdir(
                    self.generatemapper, self.outdir, self.builder.outdir,
                    inplace_update=self.inplace_update)

            outputs = self.collect_outputs(self.outdir)
            outputs = bytes2str_in_dicts(outputs)  # type: ignore
        except OSError as exc:
            if exc.errno == 2:
                if runtime:
                    LOGGER.exception(u"'%s' not found", runtime[0])
                else:
                    LOGGER.exception(u"'%s' not found", self.command_line[0])
            else:
                LOGGER.exception("Exception while running job")
            process_status = "permanentFail"
        except WorkflowException as err:
            LOGGER.exception(u"[job %s] Job error:\n%s", self.name, err)
            process_status = "permanentFail"
        except Exception:  # noqa: W0703 # nosec: B110
            LOGGER.exception("Exception while running job")
            process_status = "permanentFail"
        if runtime_context.research_obj and self.prov_obj and \
                runtime_context.process_run_id:
            # creating entities for the outputs produced by each step (in the provenance document)
            self.prov_obj.generate_output_prov(
                outputs, runtime_context.process_run_id, str(self.name))
            self.prov_obj.document.wasEndedBy(
                runtime_context.process_run_id, None, self.prov_obj.workflow_run_uri,
                now())
        if process_status != "success":
            LOGGER.warning(u"[job %s] completed %s", self.name, process_status)
        else:
            LOGGER.info(u"[job %s] completed %s", self.name, process_status)

        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug(u"[job %s] %s", self.name, json.dumps(outputs, indent=4))

        if self.generatemapper and runtime_context.secret_store:
            # Delete any runtime-generated files containing secrets.
            for _, path_item in self.generatemapper.items():
                if path_item.type == "CreateFile":
                    if runtime_context.secret_store.has_secret(path_item.resolved):
                        host_outdir = self.outdir
                        container_outdir = self.builder.outdir
                        host_outdir_tgt = path_item.target
                        if path_item.target.startswith(container_outdir + "/"):
                            host_outdir_tgt = os.path.join(
                                host_outdir, path_item.target[len(container_outdir)+1:])
                        os.remove(host_outdir_tgt)

        if runtime_context.workflow_eval_lock is None:
            raise WorkflowException("runtime_context.workflow_eval_lock must not be None")

        with runtime_context.workflow_eval_lock:
            self.output_callback(outputs, process_status)

        if self.stagedir and os.path.exists(self.stagedir):
            LOGGER.debug(u"[job %s] Removing input staging directory %s", self.name, self.stagedir)
            shutil.rmtree(self.stagedir, True)

        if runtime_context.rm_tmpdir:
            LOGGER.debug(u"[job %s] Removing temporary directory %s", self.name, self.tmpdir)
            shutil.rmtree(self.tmpdir, True)
