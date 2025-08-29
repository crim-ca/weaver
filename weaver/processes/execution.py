import copy
import logging
import os
from time import sleep
from typing import TYPE_CHECKING

import colander
import psutil
from celery.exceptions import TimeoutError as CeleryTaskTimeoutError
from celery.utils.debug import ps as get_celery_process
from celery.utils.log import get_task_logger
from owslib.util import clean_ows_url
from owslib.wps import BoundingBoxDataInput, ComplexDataInput
from pyramid.httpexceptions import (
    HTTPAccepted,
    HTTPBadRequest,
    HTTPCreated,
    HTTPNotAcceptable,
    HTTPUnprocessableEntity,
    HTTPUnsupportedMediaType
)
from pyramid_celery import celery_app as app
from werkzeug.wrappers.request import Request as WerkzeugRequest

from weaver.database import get_db
from weaver.datatype import Process, Service
from weaver.exceptions import JobExecutionError, WeaverExecutionError
from weaver.execute import (
    ExecuteControlOption,
    ExecuteMode,
    ExecuteResponse,
    ExecuteReturnPreference,
    parse_prefer_header_execute_mode,
    parse_prefer_header_return,
    update_preference_applied_return_header
)
from weaver.formats import AcceptLanguage, ContentType, clean_media_type_format, map_cwl_media_type, repr_json
from weaver.notify import map_job_subscribers, notify_job_subscribers
from weaver.owsexceptions import OWSInvalidParameterValue, OWSNoApplicableCode
from weaver.processes import wps_package
from weaver.processes.builtin.collection_processor import process_collection
from weaver.processes.constants import WPS_BOUNDINGBOX_DATA, WPS_COMPLEX_DATA, JobInputsOutputsSchema
from weaver.processes.convert import (
    convert_input_values_schema,
    convert_output_params_schema,
    get_field,
    ows2json_output_data
)
from weaver.processes.ogc_api_process import OGCAPIRemoteProcess
from weaver.processes.types import ProcessType
from weaver.processes.utils import get_process, map_progress
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.store.base import StoreJobs, StoreProcesses
from weaver.utils import (
    apply_number_with_unit,
    as_int,
    extend_instance,
    fully_qualified_name,
    get_any_id,
    get_any_value,
    get_header,
    get_path_kvp,
    get_registry,
    get_settings,
    now,
    parse_kvp,
    parse_number_with_unit,
    raise_on_xml_exception,
    wait_secs
)
from weaver.visibility import Visibility
from weaver.wps.service import get_pywps_service
from weaver.wps.utils import (
    check_wps_status,
    get_wps_client,
    get_wps_local_status_location,
    get_wps_output_context,
    get_wps_output_dir,
    get_wps_output_path,
    get_wps_output_url,
    get_wps_path,
    load_pywps_config
)
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs.utils import get_job_results_response, get_job_return, get_job_submission_response
from weaver.wps_restapi.processes.utils import resolve_process_tag

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
    from uuid import UUID

    from celery.app.task import Task
    from pyramid.request import Request
    from pywps.inout.inputs import BoundingBoxInput, ComplexInput

    from weaver.datatype import Job
    from weaver.execute import AnyExecuteControlOption, AnyExecuteMode
    from weaver.processes.convert import OWS_Input_Type, ProcessOWS
    from weaver.status import AnyStatusType, StatusType
    from weaver.typedefs import (
        AnyAcceptLanguageHeader,
        AnyDatabaseContainer,
        AnyHeadersContainer,
        AnyProcessRef,
        AnyRequestType,
        AnyResponseType,
        AnyServiceRef,
        AnySettingsContainer,
        AnyValueType,
        AnyViewResponse,
        CeleryResult,
        HeaderCookiesType,
        HeadersType,
        JobValueBbox,
        JSON,
        Number,
        ProcessExecution,
        SettingsType,
        Statistics,
        UpdateStatusPartialFunction
    )
    from weaver.visibility import AnyVisibility


class JobProgress(object):
    """
    Job process execution progress.
    """
    SETUP = 1
    DESCRIBE = 2
    GET_INPUTS = 3
    GET_OUTPUTS = 10  # extra delta from inputs retrieval for more granular range by nested processes and collections
    EXECUTE_REQUEST = 11
    EXECUTE_STATUS_LOCATION = 12
    EXECUTE_MONITOR_START = 13
    EXECUTE_MONITOR_LOOP = 14
    EXECUTE_MONITOR_DONE = 96
    EXECUTE_MONITOR_END = 98
    NOTIFY = 99
    DONE = 100


@app.task(bind=True)
def execute_process(task, job_id, wps_url, headers=None):
    # type: (Task, UUID, str, Optional[HeaderCookiesType]) -> StatusType
    """
    Celery task that executes the WPS process job monitoring as status updates (local and remote).
    """
    LOGGER.debug("Job execute process called.")

    task_process = get_celery_process()
    rss_start = task_process.memory_info().rss
    registry = get_registry(app)  # local thread, whether locally or dispatched celery
    settings = get_settings(registry)
    db = get_db(registry, reset_connection=True)  # reset the connection because we are in a forked celery process
    store = db.get_store(StoreJobs)
    job = store.fetch_by_id(job_id)
    job.started = now()
    job.status = Status.STARTED  # will be mapped to 'RUNNING'
    job.status_message = f"Job {Status.STARTED}."  # will preserve detail of STARTED vs RUNNING
    job.save_log(message=job.status_message)
    task_logger = get_task_logger(__name__)
    notify_job_subscribers(job, task_logger, settings)

    job.save_log(logger=task_logger, message="Job task setup initiated.")
    load_pywps_config(settings)
    job.progress = JobProgress.SETUP
    job.task_id = task.request.id
    job.save_log(logger=task_logger, message="Job task setup completed.")
    job = store.update_job(job)

    # Flag to keep track if job is running in background (remote-WPS, CWL app, etc.).
    # If terminate signal is sent to worker task via API dismiss request while still running in background,
    # the raised exception within the task will switch the job to Status.FAILED, but this will not raise an
    # exception here. Since the task execution 'succeeds' without raising, it skips directly to the last 'finally'.
    # Patch it back to Status.DISMISSED in this case.
    task_terminated = True

    try:
        job.progress = JobProgress.DESCRIBE
        job.save_log(logger=task_logger, message=f"Employed WPS URL: [{wps_url!s}]", level=logging.DEBUG)
        job.save_log(logger=task_logger, message=f"Execute WPS request for process [{job.process!s}]")
        wps_process = fetch_wps_process(job, wps_url, headers, settings)

        # prepare inputs
        job.progress = JobProgress.GET_INPUTS
        job.save_log(logger=task_logger, message="Fetching job input definitions.")
        wps_inputs = parse_wps_inputs(wps_process, job, container=db)

        # prepare outputs
        job.progress = JobProgress.GET_OUTPUTS
        job.save_log(logger=task_logger, message="Fetching job output definitions.")
        wps_outputs = [(o.identifier, o.dataType == WPS_COMPLEX_DATA) for o in wps_process.processOutputs]

        # if process refers to a remote WPS provider, pass it down to avoid unnecessary re-fetch request
        if job.is_local:
            process = None  # already got all the information needed pre-loaded in PyWPS service
            local_process_id = wps_process.identifier
        else:
            service = Service(name=job.service, url=wps_url)
            process = Process.from_ows(wps_process, service, settings)
            local_process_id = None

        job.progress = JobProgress.EXECUTE_REQUEST
        job.save_log(logger=task_logger, message="Starting job process execution.")
        job.save_log(logger=task_logger,
                     message="Following updates could take a while until the Application Package answers...")

        wps_worker = get_pywps_service(environ=settings, is_worker=True, process_id=local_process_id)
        execution = wps_worker.execute_job(job,
                                           wps_inputs=wps_inputs, wps_outputs=wps_outputs,
                                           remote_process=process, headers=headers)
        if not execution.process and execution.errors:
            raise execution.errors[0]

        # adjust status location
        wps_status_path = get_wps_local_status_location(execution.statusLocation, settings)
        job.progress = JobProgress.EXECUTE_STATUS_LOCATION
        LOGGER.debug("WPS status location that will be queried: [%s]", wps_status_path)
        if not wps_status_path.startswith("http") and not os.path.isfile(wps_status_path):
            LOGGER.warning("WPS status location not resolved to local path: [%s]", wps_status_path)
        job.save_log(logger=task_logger, level=logging.DEBUG,
                     message=f"Updated job status location: [{wps_status_path}].")

        job.status = Status.RUNNING
        job.status_message = execution.statusMessage or f"{job!s} initiation done."
        job.status_location = wps_status_path
        job.request = execution.request
        job.response = execution.response
        job.progress = JobProgress.EXECUTE_MONITOR_START
        job.save_log(logger=task_logger, message="Starting monitoring of job execution.")
        job = store.update_job(job)

        max_retries = 5
        num_retries = 0
        run_step = 0
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= max_retries:
                job.save_log(errors=execution.errors, logger=task_logger)
                job = store.update_job(job)
                raise Exception(f"Could not read status document after {max_retries} retries. Giving up.")
            try:
                # NOTE:
                #   Don't actually log anything here until process is completed (success or fail) so that underlying
                #   WPS execution logs can be inserted within the current job log and appear continuously.
                #   Only update internal job fields in case they get referenced elsewhere.
                progress_min = JobProgress.EXECUTE_MONITOR_LOOP
                progress_max = JobProgress.EXECUTE_MONITOR_DONE
                job.progress = progress_min
                run_delay = wait_secs(run_step)
                execution = check_wps_status(location=wps_status_path, settings=settings, sleep_secs=run_delay)
                job_msg = (execution.statusMessage or "").strip()
                job.response = execution.response
                job.status = map_status(execution.getStatus())
                job_status_msg = job_msg or "n/a"
                job_percent = execution.percentCompleted
                job.status_message = f"Job execution monitoring (progress: {job_percent}%, status: {job_status_msg})."

                if execution.isComplete():
                    msg_progress = f" (status: {job_msg})" if job_msg else ""
                    if execution.isSucceeded():
                        wps_package.retrieve_package_job_log(execution, job, progress_min, progress_max)
                        job.status = map_status(Status.SUCCESSFUL)
                        job.status_message = f"Job {job.status}{msg_progress}."
                        job.progress = progress_max
                        job.save_log(logger=task_logger)
                        job_results = [
                            ows2json_output_data(output, process, settings)
                            for output in execution.processOutputs
                        ]
                        job.results = make_results_relative(job_results, settings)
                    else:
                        task_logger.debug("Job failed.")
                        wps_package.retrieve_package_job_log(execution, job, progress_min, progress_max)
                        job.status_message = f"Job failed{msg_progress}."
                        job.progress = progress_max
                        job.save_log(errors=execution.errors, logger=task_logger)
                    task_logger.debug("Mapping Job references with generated WPS locations.")
                    map_locations(job, settings)
                    job = store.update_job(job)

            except Exception as exc:
                num_retries += 1
                task_logger.debug("Exception raised: %s", repr(exc))
                job.status_message = f"Could not read status XML document for {job!s}. Trying again..."
                job.save_log(errors=execution.errors, logger=task_logger)
                job = store.update_job(job)
                sleep(1)
            else:
                num_retries = 0
                run_step += 1
            finally:
                task_terminated = False  # reached only if WPS execution completed (worker not terminated beforehand)
                job = store.update_job(job)

    except Exception as exc:
        # if 'execute_job' finishes quickly before even reaching the 'monitoring loop'
        # consider WPS execution produced an error (therefore Celery worker not terminated)
        task_terminated = False
        LOGGER.exception("Failed running [%s]", job)
        LOGGER.debug("Failed job [%s] raised an exception.", job, exc_info=exc)
        # note: don't update the progress here to preserve last one that was set
        job.status = map_status(Status.FAILED)
        if isinstance(exc, WeaverExecutionError):
            job.save_log(message=str(exc), logger=task_logger, level=logging.ERROR)
        job.status_message = f"Failed to run {job!s}."
        errors = f"{fully_qualified_name(exc)}: {exc!s}"
        job.save_log(errors=errors, logger=task_logger)
        job = store.update_job(job)
    finally:
        # WARNING: important to clean before re-fetching, otherwise we loose internal references needing cleanup
        job.cleanup()
        # NOTE:
        #   don't update the progress and status here except for 'success' to preserve last error that was set
        #   it is more relevant to return the latest step that worked properly to understand where it failed
        job = store.fetch_by_id(job.id)
        # if task worker terminated, local 'job' is out of date compared to remote/background runner last update
        if task_terminated and map_status(job.status) == Status.FAILED:
            job.status = Status.DISMISSED
        task_success = map_status(job.status) not in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]
        collect_statistics(task_process, settings, job, rss_start)
        if task_success:
            job.progress = JobProgress.EXECUTE_MONITOR_END
        job.status_message = f"Job {job.status}."
        job.save_log(logger=task_logger)

        if task_success:
            job.progress = JobProgress.NOTIFY
        notify_job_subscribers(job, task_logger, settings)

        if job.status not in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            job.status = Status.SUCCEEDED
        job.status_message = f"Job {job.status}."
        job.mark_finished()
        if task_success:
            job.progress = JobProgress.DONE
        job.save_log(logger=task_logger, message="Job task complete.")
        job = store.update_job(job)

    return job.status


def collect_statistics(process, settings=None, job=None, rss_start=None):
    # type: (Optional[psutil.Process], Optional[SettingsType], Optional[Job], Optional[int]) -> Optional[Statistics]
    """
    Collect any available execution statistics and store them in the :term:`Job` if provided.
    """
    try:
        mem_used = None
        if job:
            mem_info = list(filter(lambda line: "cwltool" in line and "memory used" in line, job.logs))
            mem_used = None
            if mem_info:
                mem_info = mem_info[0].split(":")[-1].strip()
                mem_used = parse_number_with_unit(mem_info, binary=True)

        stats = {}  # type: JSON
        if mem_used:
            stats["application"] = {
                # see: 'cwltool.job.JobBase.process_monitor', reported memory in logs uses 'rss'
                "usedMemory": apply_number_with_unit(mem_used, binary=True),
                "usedMemoryBytes": mem_used,
            }

        rss = None
        if process:
            proc_info = process.memory_full_info()
            rss = getattr(proc_info, "rss", 0)
            uss = getattr(proc_info, "uss", 0)
            vms = getattr(proc_info, "vms", 0)
            stats["process"] = {
                "rss": apply_number_with_unit(rss, binary=True),
                "rssBytes": rss,
                "uss": apply_number_with_unit(uss, binary=True),
                "ussBytes": uss,
                "vms": apply_number_with_unit(vms, binary=True),
                "vmsBytes": vms,
            }
            fields = [("usedThreads", "num_threads"), ("usedCPU", "cpu_num"), ("usedHandles", "num_handles")]
            for field, method in fields:
                func = getattr(process, method, None)
                stats["process"][field] = func() if func is not None else 0

        if rss_start and rss:
            # diff of RSS between start/end to consider only execution of the job steps
            # this more accurately reports used memory by the execution itself, omitting celery worker's base memory
            rss_diff = rss - rss_start
            stats["process"]["usedMemory"] = apply_number_with_unit(rss_diff, binary=True)
            stats["process"]["usedMemoryBytes"] = rss_diff

        total_size = 0
        if job:
            stats["outputs"] = {}
            for result in job.results:
                res_ref = get_any_value(result, file=True)
                if res_ref and isinstance(res_ref, str):
                    if res_ref.startswith(f"/{job.id}"):  # pseudo-relative reference
                        out_dir = get_wps_output_dir(settings)
                        res_ref = os.path.join(out_dir, res_ref.lstrip("/"))
                    if os.path.isfile(res_ref):
                        res_stat = os.stat(res_ref)
                        res_id = get_any_id(result)
                        res_size = res_stat.st_size
                        stats["outputs"][res_id] = {
                            "size": apply_number_with_unit(res_size, binary=True),
                            "sizeBytes": res_size,
                        }
                        total_size += res_size
            stats["process"]["totalSize"] = apply_number_with_unit(total_size, binary=True)
            stats["process"]["totalSizeBytes"] = total_size

        if stats and job:
            job.statistics = stats
        return stats or None
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Ignoring error that occurred during statistics collection [%s]", str(exc), exc_info=exc)


def fetch_wps_process(job, wps_url, headers, settings):
    # type: (Job, str, HeadersType, SettingsType) -> ProcessOWS
    """
    Retrieves the WPS process description from the local or remote WPS reference URL.
    """
    try:
        wps = get_wps_client(wps_url, settings, headers=headers, language=job.accept_language)
        raise_on_xml_exception(wps._capabilities)  # noqa: W0212
    except Exception as ex:
        job.save_log(errors=ex, message=f"Failed WPS client creation for process [{job.process!s}]")
        raise OWSNoApplicableCode(f"Failed to retrieve WPS capabilities. Error: [{ex!s}].")
    try:
        wps_process = wps.describeprocess(job.process)
    except Exception as ex:  # pragma: no cover
        raise OWSNoApplicableCode(f"Failed to retrieve WPS process description. Error: [{ex!s}].")
    return wps_process


def parse_wps_input_format(input_info, type_field="mime_type", search_variations=True):
    # type: (JSON, str, bool) -> Tuple[Optional[str], Optional[str]]
    ctype = get_field(input_info, type_field, search_variations=search_variations, default=None)
    c_enc = get_field(input_info, "encoding", search_variations=True, default=None)
    if not c_enc:
        ctype_params = parse_kvp(ctype)
        c_enc = ctype_params.get("charset")
        c_enc = c_enc[0] if c_enc and isinstance(c_enc, list) else None
    return ctype, c_enc


def parse_wps_input_complex(input_value, input_info):
    # type: (Union[str, JSON], JSON) -> ComplexDataInput
    """
    Parse the input data details into a complex input.
    """
    # if provided, pass down specified input format to allow validation against supported formats
    c_enc = ctype = schema = None
    schema_vars = ["reference", "$schema"]
    input_field = get_any_value(input_info, key=True)
    if isinstance(input_value, dict):
        if input_field is None:
            input_field = get_any_value(input_value, key=True)
        ctype, c_enc = parse_wps_input_format(input_value, "type", search_variations=False)
        if not ctype:
            ctype, c_enc = parse_wps_input_format(input_value)
        schema = get_field(input_value, "schema", search_variations=True, default=None, extra_variations=schema_vars)
        input_value = input_value[input_field]
        input_value = repr_json(input_value, indent=None, ensure_ascii=(c_enc in ["ASCII", "ascii"]))
    if not ctype:
        ctype, c_enc = parse_wps_input_format(input_info)
        media_format = get_field(input_info, "format", default=None)
        if not ctype and isinstance(media_format, dict):
            ctype, c_enc = parse_wps_input_format(media_format)
    if isinstance(schema, dict):
        schema = get_field(schema, "$ref", default=None, extra_variations=schema_vars)
    # need to support 'file://' scheme which could be omitted
    # to ensure owslib parses it has a link (asReference), add it if missing
    if input_field in ["href", "reference"] and "://" not in str(input_value):
        input_value = f"file://{input_value}"
    return ComplexDataInput(input_value, mimeType=ctype, encoding=c_enc, schema=schema)


def parse_wps_input_bbox(input_value, input_info):
    # type: (Union[str, JobValueBbox], JSON) -> BoundingBoxDataInput
    """
    Parse the input data details into a bounding box input.
    """
    bbox_crs = None
    bbox_val = input_value
    if isinstance(input_value, dict):
        bbox_crs = input_value.get("crs")
        bbox_val = input_value.get("bbox")
    if not bbox_crs:
        bbox_crs_def = input_info.get("bbox", {})
        if isinstance(bbox_crs_def, dict) and "default" in bbox_crs_def:
            bbox_crs = bbox_crs_def["default"] or None
    bbox_val = bbox_val.split(",") if isinstance(bbox_val, str) else bbox_val
    bbox_dim = len(bbox_val) // 2
    return BoundingBoxDataInput(bbox_val, crs=bbox_crs, dimensions=bbox_dim)


def parse_wps_input_literal(input_value):
    # type: (Union[AnyValueType, JSON]) -> Optional[str]
    """
    Parse the input data details into a literal input.
    """
    # if JSON 'null' was given, the execution content should simply omit the optional input
    # cannot distinguish directly between empty string and 'null' in XML representation
    if input_value is None:
        return None

    # measurement structure
    # however, owslib does not care about the UoM specified as input (no way to provide it)
    if isinstance(input_value, dict):
        val = get_any_value(input_value, file=False, default=input_value)  # in case it was nested twice under 'value'
        if isinstance(val, dict):
            val = get_field(val, "measure", search_variations=True, default=val)
        if val is not None:
            input_value = val

    # need to use literal string for any data type
    return str(input_value)


def log_and_save_update_status_handler(
    job,                    # type: Job
    container,              # type: AnyDatabaseContainer
    update_status=None,     # type: Callable[[AnyStatusType], StatusType]
    update_progress=None,   # type: Callable[[Number], Number]
):                          # type: (...) -> UpdateStatusPartialFunction
    """
    Creates a :term:`Job` status update function that will immediately reflect the log message in the database.

    When log messages are generated and saved in the :term:`Job`, those details are not persisted to the database
    until the updated :term:`Job` is entirely pushed to the database store. This causes clients querying the :term:`Job`
    endpoints to not receive any latest update from performed operations until the execution returns to the main worker
    monitoring loop, which will typically perform a :term:`Job` update "at some point".

    Using this handler, each time a message is pushed to the :term:`Job`, that update is also persisted by maintaining
    a local database connection handle. However, because updating the entire :term:`Job` each time can become costly
    and inefficient for multiple subsequent logs, this operation should be applied only on "important milestones" of
    the execution steps. Any intermediate/subsequent logs should use the usual :meth:`Job.save_log` to "accumulate" the
    log messages for a following "batch update" of the :term:`Job`.

    :param job: Reference :term:`Job` for which the status will be updated and saved with uncommitted log entries.
    :param container: Container to retrieve the database connection.
    :param update_status: Function to apply override status update operations. Skipped if omitted.
    :param update_progress: Function to apply override progress update operations. Skipped if omitted.
    """
    db = get_db(container)
    store = db.get_store(StoreJobs)

    def log_and_update_status(message, progress=None, status=None, *_, **kwargs):  # pylint: disable=W1113
        # type: (str, Optional[Number], Optional[AnyStatusType], Any, Any) -> None
        if update_status and status:
            status = update_status(status)
        if update_progress and progress is not None:
            progress = update_progress(progress)
        if "error" in kwargs:
            kwargs["errors"] = kwargs.pop("error")  # align with 'save_log' parameters
        job.save_log(message=message, progress=progress, status=status, **kwargs)
        store.update_job(job)
    return log_and_update_status


def parse_wps_inputs(wps_process, job, container=None):
    # type: (ProcessOWS, Job, Optional[AnyDatabaseContainer]) -> List[Tuple[str, OWS_Input_Type]]
    """
    Parses expected :term:`WPS` process inputs against submitted job input values considering supported definitions.

    According to the structure of the job inputs, and notably their key arguments, perform the relevant parsing and
    data retrieval to prepare inputs in a native format that can be understood and employed by a :term:`WPS` worker
    (i.e.: :class:`weaver.wps.service.WorkerService` and its underlying :mod:`pywps` implementation).
    """
    complex_inputs = {}  # type: Dict[str, ComplexInput]
    bbox_inputs = {}  # type: Dict[str, BoundingBoxInput]
    for process_input in wps_process.dataInputs:
        if process_input.dataType == WPS_COMPLEX_DATA:
            complex_inputs[process_input.identifier] = process_input
        elif process_input.dataType == WPS_BOUNDINGBOX_DATA:
            bbox_inputs[process_input.identifier] = process_input

    job_log_update_status_func = log_and_save_update_status_handler(
        job,
        container,
        # Because the operations that will be executed with this status handler can involve a nested process execution,
        # successful execution of that nested process will log a 'succeeded' entry within this ongoing execution.
        # Because it is a nested process, it is expected that further operations from the 'parent' process using it will
        # log many more steps afterwards. Therefore, avoid the ambiguous entry within the context of the parent process.
        update_status=lambda _status: (
            Status.RUNNING if map_status(_status, category=True) == StatusCategory.SUCCESS else _status
        ),
        # Similarly, progress of the current job will be constraint within inputs retrieval and the following outputs
        # retrieval for the nested progress execution. Mapping the progress will ensure overall gradual percent values.
        update_progress=lambda _progress: map_progress(_progress, JobProgress.GET_INPUTS, JobProgress.GET_OUTPUTS),
    )
    try:
        wps_inputs = []
        # parse both dict and list type inputs
        job_inputs = job.inputs.items() if isinstance(job.inputs, dict) else job.get("inputs", [])
        for job_input in job_inputs:
            if isinstance(job_input, tuple):
                input_id = job_input[0]
                input_val = job_input[1]
                job_input = input_val
            else:
                input_id = get_any_id(job_input)
                input_val = get_any_value(job_input)
            if input_id in bbox_inputs and input_val is None:  # inline bbox
                input_val = job_input

            # FIXME: handle minOccurs>=2 vs single-value inputs
            #   - https://github.com/opengeospatial/ogcapi-processes/issues/373
            #   - https://github.com/crim-ca/weaver/issues/579
            # in case of array inputs, must repeat (id, value)
            if isinstance(input_val, list):
                input_values = input_val
                input_details = input_val  # each value has its own metadata
            else:
                input_values = [input_val]
                input_details = [job_input]  # metadata directly in definition, not nested per array value

            # Pre-check collection for resolution of the referenced data.
            # Because each collection input can result in either '1->1' or '1->N' file reference(s) mapping,
            # resolution must be performed before iterating through input value/definitions to parse them.
            # Whether sink input receiving this data can map to 1 or N is up to be validated by the execution later.
            resolved_inputs = []
            for input_value, input_info in zip(input_values, input_details):
                if isinstance(input_info, dict):
                    # copy to avoid overriding 'input_value' with an ID
                    # this could refer to the desired collection ID rather than the input ID being mapped
                    input_info = dict(input_info)  # not 'deepcopy' to avoid 'data' or 'value' copy that could be large
                    input_info["id"] = input_id

                # collection reference
                if isinstance(input_value, dict) and "collection" in input_value:
                    col_path = os.path.join(job.tmpdir, "inputs", input_id)
                    col_files = process_collection(input_value, input_info, col_path, logger=job)
                    resolved_input_values = [
                        (
                            {"href": col_file["path"], "type": map_cwl_media_type(col_file["format"])},
                            input_info
                        )
                        for col_file in col_files
                    ]

                # nested process reference
                elif isinstance(input_value, dict) and "process" in input_value:
                    proc_uri = input_value["process"]
                    job_log_update_status_func(
                        message=(
                            f"Dispatching execution of nested process [{proc_uri}] "
                            f"for input [{input_id}] of [{job.process}]."
                        ),
                        logger=LOGGER,
                        progress=JobProgress.GET_INPUTS,
                    )
                    inputs = copy.deepcopy(input_value.get("inputs", {}))
                    outputs = copy.deepcopy(input_value.get("outputs"))
                    out_ids = [get_any_id(out) for out in outputs] if isinstance(outputs, list) else (outputs or [])
                    if len(input_value.get("outputs", {})) > 1:  # preemptive check to avoid wasting time/resources
                        raise JobExecutionError(
                            f"Abort execution. Cannot map multiple outputs {list(out_ids)} "
                            f"from [{proc_uri}] to input [{input_id}] of [{job.process}]."
                        )
                    process = OGCAPIRemoteProcess(
                        input_value,
                        proc_uri,
                        request=None,
                        update_status=job_log_update_status_func,
                    )
                    out_dir = os.path.join(job.tmpdir, "inputs")
                    results = process.execute(inputs, out_dir, outputs)
                    if not results:
                        raise JobExecutionError(
                            f"Abort execution. Cannot map empty outputs from [{proc_uri}] "
                            f"to input [{input_id}] of [{job.process}]."
                        )
                    if len(results) != 1:  # post-execution check since no explicit output specified could lead to many
                        raise JobExecutionError(
                            f"Abort execution. Cannot map multiple outputs {list(out_ids)} "
                            f"from [{proc_uri}] to input [{input_id}] of [{job.process}]."
                        )
                    resolved_input_values = [(results[0], input_info)]

                # typical file/data
                else:
                    resolved_input_values = [(input_value, input_info)]

                resolved_inputs.extend(resolved_input_values)

            for input_value, input_info in resolved_inputs:
                # if already resolved, skip parsing
                # it is important to omit explicitly provided 'null', otherwise the WPS object could be misleading
                # for example, a 'ComplexData' with 'null' data will be auto-generated as text/plan with "null" string
                if input_value is None:
                    input_data = None
                else:
                    # resolve according to relevant data type parsing
                    # value could be an embedded or remote definition
                    if input_id in complex_inputs:
                        input_data = parse_wps_input_complex(input_value, input_info)
                    elif input_id in bbox_inputs:
                        input_data = parse_wps_input_bbox(input_value, input_info)
                    else:
                        input_data = parse_wps_input_literal(input_value)

                # re-validate the resolved data as applicable
                if input_data is None:
                    job_log_update_status_func(
                        message=f"Removing [{input_id}] data input from execution request, value was 'null'.",
                        logger=LOGGER,
                        level=logging.WARNING,
                        progress=JobProgress.GET_INPUTS,
                    )
                else:
                    wps_inputs.append((input_id, input_data))
    except KeyError:
        wps_inputs = []
    return wps_inputs


def make_results_relative(results, settings):
    # type: (List[JSON], SettingsType) -> List[JSON]
    """
    Converts file references to a pseudo-relative location to allow the application to dynamically generate paths.

    Redefines job results to be saved in database as pseudo-relative paths to configured WPS output directory.
    This allows the application to easily adjust the exposed result HTTP path according to the service configuration
    (i.e.: relative to ``weaver.wps_output_dir`` and/or ``weaver.wps_output_url``) and it also avoids rewriting
    the database job results entry if those settings are changed later on following reboot of the web application.

    Only references prefixed with ``weaver.wps_output_dir``, ``weaver.wps_output_url`` or a corresponding resolution
    from ``weaver.wps_output_path`` with ``weaver.url`` will be modified to pseudo-relative paths.
    Other references (file/URL endpoints that do not correspond to `Weaver`) will be left untouched for
    literal remote reference. Results that do not correspond to a reference are also unmodified.

    .. note::

        The references are not *real* relative paths (i.e.: starting with ``./``), as those could also be specified as
        input, and there would be no way to guarantee proper differentiation from paths already handled and stored in
        the database. Instead, *pseudo-relative* paths employ an explicit *absolute*-like path
        (i.e.: starting with ``/``) and are assumed to always require to be prefixed by the configured WPS locations
        (i.e.: ``weaver.wps_output_dir`` or ``weaver.wps_output_url`` based on local or HTTP response context).

        With this approach, data persistence with mapped volumes into the dockerized `Weaver` service can be placed
        anywhere at convenience. This is important because sibling docker execution require exact mappings such that
        volume mount ``/data/path:/data/path`` resolve correctly on both sides (host and image path must be identical).
        If volumes get remapped differently, ensuring that ``weaver.wps_output_dir`` setting follows the same remapping
        update will automatically resolve to the proper location for both local references and exposed URL endpoints.

    :param results: JSON mapping of data results as ``{"<id>": <definition>}`` entries where a reference can be found.
    :param settings: container to retrieve current application settings.
    """
    wps_url = get_wps_output_url(settings)
    wps_path = get_wps_output_path(settings)
    for res in results:
        if not isinstance(res, dict):
            continue
        ref = res.get("reference")
        if isinstance(ref, str) and ref:
            if ref.startswith(wps_url):
                ref = ref.replace(wps_url, "", 1)
            if ref.startswith(wps_path):
                ref = ref.replace(wps_path, "", 1)
            res["reference"] = ref
        data = res.get("data")
        if isinstance(data, list):
            make_results_relative(data, settings)
    return results


def map_locations(job, settings):
    # type: (Job, SettingsType) -> None
    """
    Maps directory locations between :mod:`pywps` process execution and produced jobs storage.

    Generates symlink references from the Job UUID to PyWPS UUID results (outputs directory, status and log locations).
    Update the Job's WPS ID if applicable (job executed locally).
    Assumes that all results are located under the same reference UUID.
    """
    local_path = get_wps_local_status_location(job.status_location, settings)
    if not local_path:
        LOGGER.debug("Not possible to map Job to WPS locations.")
        return
    base_dir, status_xml = os.path.split(local_path)
    job.wps_id = os.path.splitext(status_xml)[0]
    wps_loc = os.path.join(base_dir, str(job.wps_id))
    job_loc = os.path.join(base_dir, str(job.id))
    if wps_loc == job_loc:
        LOGGER.debug("Job already refers to WPS locations.")
        return
    for loc_ext in ["", ".log", ".xml"]:
        wps_ref = wps_loc + loc_ext
        job_ref = job_loc + loc_ext
        if os.path.exists(wps_ref):  # possible that there are no results (e.g.: failed job)
            os.symlink(wps_ref, job_ref)


def submit_job_dispatch_wps(request, process):
    # type: (Request, Process) -> AnyViewResponse
    """
    Dispatch a :term:`XML` request to the relevant :term:`Process` handler using the :term:`WPS` endpoint.

    Sends the :term:`XML` request to the :term:`WPS` endpoint which knows how to parse it properly.
    Execution will end up in the same :func:`submit_job_handler` function as for :term:`OGC API - Processes`
    :term:`JSON` execution.

    .. warning::
        The function assumes that :term:`XML` was pre-validated as present in the :paramref:`request`.
    """
    service = get_pywps_service()
    wps_params = {"version": "1.0.0", "request": "Execute", "service": "WPS", "identifier": process.id}
    request.path_info = get_wps_path(request)
    request.query_string = get_path_kvp("", **wps_params)[1:]
    location = request.application_url + request.path_info + request.query_string
    LOGGER.warning("Route redirection [%s] -> [%s] for WPS-XML support.", request.url, location)
    http_request = extend_instance(request, WerkzeugRequest)
    http_request.shallow = False
    return service.call(http_request)


def submit_job(request, reference, tags=None, process_id=None):
    # type: (Request, Union[Service, Process], Optional[List[str]], Optional[str]) -> AnyResponseType
    """
    Generates the job submission from details retrieved in the request.

    .. seealso::
        :func:`submit_job_handler` to provide elements pre-extracted from requests or from other parsing.
    """
    # validate body with expected JSON content and schema
    json_body = validate_job_json(request)
    # validate context if needed later on by the job for early failure
    context = get_wps_output_context(request)

    prov_id = None  # None OK if local
    proc_id = None  # None OK if remote, but can be found as well if available from WPS-REST path  # noqa
    tags = tags or []
    lang = request.accept_language.header_value  # can only preemptively check if local process
    if isinstance(reference, Process):
        service_url = reference.processEndpointWPS1
        # use the request-provided reference (explicit 'id:version' process revision or simply 'id')
        # if the latest, it resolves the same, but use the one the user will be aware of for clearer reporting of URLs
        proc_id = process_id or resolve_process_tag(request)
        visibility = reference.visibility
        is_workflow = reference.type == ProcessType.WORKFLOW
        is_local = True
        tags.append("local")
        support_lang = AcceptLanguage.offers()
        accepts_lang = request.accept_language  # type: AnyAcceptLanguageHeader
        matched_lang = accepts_lang.lookup(support_lang, default="") or None
        if lang and not matched_lang:
            raise HTTPNotAcceptable(
                json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
                    "type": "NotAcceptable",
                    "title": "Execution request is not acceptable.",
                    "detail": f"Requested language [{lang}] not in supported languages [{sorted(support_lang)}].",
                    "status": HTTPNotAcceptable.code,
                    "cause": {"name": "Accept-Language", "in": "headers"},
                    "value": repr_json(lang, force_string=False),
                })
            )
        lang = matched_lang
    elif isinstance(reference, Service):
        service_url = reference.url
        prov_id = reference.id
        proc_id = process_id or resolve_process_tag(request)
        visibility = Visibility.PUBLIC
        is_workflow = False
        is_local = False
        tags.append("remote")
    else:  # pragma: no cover
        LOGGER.error("Expected process/service, got: %s", type(reference))
        raise TypeError("Invalid process or service reference to execute job.")
    queries = sd.LaunchJobQuerystring().deserialize(request.params)
    tags = queries.get("tags", "").split(",") + tags
    user = request.authenticated_userid  # FIXME: consider other methods to provide the user
    headers = dict(request.headers)
    settings = get_settings(request)
    return submit_job_handler(
        json_body, settings, service_url, prov_id, proc_id, is_workflow, is_local, visibility,
        language=lang, request=request, headers=headers, tags=tags, user=user, context=context
    )


def submit_job_handler(
    payload,            # type: ProcessExecution
    settings,           # type: SettingsType
    wps_url,            # type: str
    provider=None,      # type: Optional[AnyServiceRef]
    process=None,       # type: AnyProcessRef
    is_workflow=False,  # type: bool
    is_local=True,      # type: bool
    visibility=None,    # type: Optional[AnyVisibility]
    language=None,      # type: Optional[str]
    request=None,       # type: Optional[AnyRequestType]
    headers=None,       # type: Optional[HeaderCookiesType]
    tags=None,          # type: Optional[List[str]]
    user=None,          # type: Optional[int]
    context=None,       # type: Optional[str]
):                      # type: (...) -> AnyResponseType
    """
    Parses parameters that defines the submitted :term:`Job`, and responds accordingly with the selected execution mode.

    Assumes that parameters have been pre-fetched and validated, except for the :paramref:`payload` containing the
    desired inputs and outputs from the :term:`Job`. The selected execution mode looks up the various combinations
    of headers and body parameters available across :term:`API` implementations and revisions.
    """
    json_body = validate_job_schema(payload, headers)
    db = get_db(settings)

    # non-local is only a reference, no actual process object to validate
    provider_id = provider.id if isinstance(provider, Service) else provider
    process_id = None
    if process and not isinstance(process, Process):
        process_id = process
        if is_local:
            proc_store = db.get_store(StoreProcesses)
            process = proc_store.fetch_by_id(process)
    if process and is_local:
        validate_process_io(process, json_body)
        validate_process_id(process, json_body)
    else:
        LOGGER.warning(
            "Skipping validation of execution parameters for remote process [%s] on provider [%s]",
            process, provider_id
        )
    # pass down the specified or resolved reference (possibly with revision tag)
    process_id = process_id or process.id

    headers = headers or {}
    if is_local:
        job_ctl_opts = process.jobControlOptions
    else:
        job_ctl_opts = ExecuteControlOption.values()
    exec_max_wait = settings.get("weaver.execute_sync_max_wait", settings.get("weaver.exec_sync_max_wait"))
    exec_max_wait = as_int(exec_max_wait, default=20)
    mode, wait, applied = parse_prefer_header_execute_mode(headers, job_ctl_opts, exec_max_wait, return_auto=True)
    if not applied:  # whatever returned is a default, consider 'mode' in body as alternative
        execute_mode = ExecuteMode.get(json_body.get("mode"), default=ExecuteMode.AUTO)
    else:
        # as per https://datatracker.ietf.org/doc/html/rfc7240#section-2
        # Prefer header not resolved with a valid value should still resume without error
        execute_mode = mode
    validate_process_exec_mode(job_ctl_opts, execute_mode)

    accept_type = validate_job_accept_header(headers, execute_mode)
    accept_profile = validate_job_accept_profile(headers, execute_mode)
    exec_resp, exec_return = get_job_return(job=None, body=json_body, headers=headers)  # job 'None' since still parsing
    req_headers = copy.deepcopy(headers or {})
    get_header("prefer", headers, pop=True)  # don't care about value, just ensure removed with any header container

    job_pending_created = json_body.get("status") == "create"
    if job_pending_created:
        job_status = Status.CREATED
        job_message = "Job created with pending trigger."
    else:
        job_status = Status.ACCEPTED
        job_message = "Job task submitted for execution."

    subscribers = map_job_subscribers(json_body, settings)
    job_inputs = json_body.get("inputs")
    job_outputs = json_body.get("outputs")
    store = db.get_store(StoreJobs)  # type: StoreJobs
    job = store.save_job(task_id=job_status, process=process_id, service=provider_id, status=job_status,
                         inputs=job_inputs, outputs=job_outputs, is_workflow=is_workflow, is_local=is_local,
                         execute_mode=execute_mode, execute_wait=wait,
                         execute_response=exec_resp, execute_return=exec_return,
                         custom_tags=tags, user_id=user, access=visibility, context=context, subscribers=subscribers,
                         accept_type=accept_type, accept_language=language, accept_profile=accept_profile)
    job.save_log(logger=LOGGER, message=job_message, status=job_status, progress=0)
    job.wps_url = wps_url
    job = store.update_job(job)

    return submit_job_dispatch_task(job, request=request, headers=req_headers, container=settings)


def submit_job_dispatch_task(
    job,                    # type: Job
    *,                      # force named keyword arguments after
    container,              # type: AnySettingsContainer
    request=None,           # type: Optional[AnyRequestType]
    headers=None,           # type: AnyHeadersContainer
    force_submit=False,     # type: bool
):                          # type: (...) -> AnyResponseType
    """
    Submits the :term:`Job` to the :mod:`celery` worker with provided parameters.

    Assumes that parameters have been pre-fetched, validated, and can be resolved from the :term:`Job`.

    .. note::
        Both the :paramref:`container` and :paramref:`request` parameters are provided, although they could contain the
        same nested setting references in certain cases, because other implementations (e.g.: dispatch via :term:`WPS`)
        might recreate their own :term:`HTTP` request object that doesn't include the application settings.
    """
    db = get_db(container)
    store = db.get_store(StoreJobs)

    location_url = job.status_url(container)
    resp_headers = {"Location": location_url}
    req_headers = copy.deepcopy(headers or {})

    task_result = None  # type: Optional[CeleryResult]
    job_pending_created = job.status == Status.CREATED
    if job_pending_created and force_submit:
        # preemptively update job status to avoid next
        # dispatch steps ignoring submission to the worker
        job.status = Status.ACCEPTED
        job = store.update_job(job)
        job_pending_created = False
        response_class = HTTPAccepted
    else:
        response_class = HTTPCreated

    if not job_pending_created:
        wps_url = clean_ows_url(job.wps_url)
        task_result = execute_process.delay(job_id=job.id, wps_url=wps_url, headers=headers)
        LOGGER.debug("Celery pending task [%s] for job [%s].", task_result.id, job.id)

    execute_sync = not job_pending_created and not job.execute_async
    if execute_sync:
        LOGGER.debug("Celery task requested as sync if it completes before (wait=%ss)", job.execution_wait)
        try:
            task_result.wait(timeout=job.execution_wait)
        except CeleryTaskTimeoutError:
            pass
        if task_result.ready():
            job = store.fetch_by_id(job.id)
            # when sync is successful, it must return the results direct instead of status info
            # see: https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execute_response
            if job.success:
                _, _, sync_applied = parse_prefer_header_execute_mode(req_headers, [ExecuteControlOption.SYNC])
                if sync_applied:
                    resp_headers.update(sync_applied)
                return get_job_results_response(
                    job,
                    request=request,
                    request_headers=req_headers,
                    response_headers=resp_headers,
                    container=container,
                )
            # otherwise return the error status
            body = job.json(container=container)
            body["location"] = location_url
            resp = get_job_submission_response(body, resp_headers, error=True)
            return resp
        else:
            job.save_log(
                logger=LOGGER,
                level=logging.WARNING,
                message=(
                    f"Job requested as synchronous execution took too long to complete (wait={job.execution_wait}s). "
                    "Will resume with asynchronous execution."
                )
            )
            job = store.update_job(job)
            execute_sync = False

    if not execute_sync:
        # either sync was not respected, therefore must drop it, or it was not requested at all
        # since both could be provided as alternative preferences, drop only sync with limited subset
        _, _, async_applied = parse_prefer_header_execute_mode(req_headers, [ExecuteControlOption.ASYNC])
        if async_applied:
            resp_headers.update(async_applied)

    LOGGER.debug("Celery task submitted to run async.")
    body = {
        "jobID": job.id,
        "processID": job.process,
        "providerID": job.service,  # dropped by validator if not applicable
        "status": map_status(job.status),
        "location": location_url,   # for convenience/backward compatibility, but official is Location *header*
    }
    resp_headers = update_preference_applied_return_header(job, req_headers, resp_headers)
    resp = get_job_submission_response(body, resp_headers, response_class=response_class)
    return resp


def update_job_parameters(job, request):
    # type: (Job, Request) -> None
    """
    Updates an existing :term:`Job` with new request parameters.
    """
    body = validate_job_json(request)
    body = validate_job_schema(body, request.headers, sd.PatchJobBodySchema)

    value = field = loc = None
    job_process = get_process(job.process)
    validate_process_id(job_process, body)
    try:
        loc = "body"

        # used to avoid possible attribute name conflict
        # (e.g.: 'job.response' vs 'job.execution_response')
        execution_fields = ["response", "mode"]

        for node in sd.PatchJobBodySchema().children:
            field = node.name
            if not field or field not in body:
                continue
            if field in ["subscribers", "notification_email"]:
                continue  # will be handled simultaneously after

            value = body[field]  # type: ignore
            if field not in execution_fields and field in job:
                setattr(job, field, value)
            elif field in execution_fields:
                field = f"execution_{field}"
                if field == "execution_mode":
                    if value == ExecuteMode.AUTO:
                        continue  # don't override previously set value that resolved with default value by omission
                    if value in [ExecuteMode.ASYNC, ExecuteMode.SYNC]:
                        job_ctrl_exec = ExecuteControlOption.from_mode(value)
                        if job_ctrl_exec not in job_process.jobControlOptions:
                            raise HTTPBadRequest(
                                json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
                                    "type": "InvalidJobUpdate",
                                    "title": "Invalid Job Execution Update",
                                    "detail": (
                                        "Update of the job execution mode is not permitted "
                                        "by supported jobControlOptions of the process description."
                                    ),
                                    "status": HTTPBadRequest.code,
                                    "cause": {"name": "mode", "in": loc},
                                    "value": repr_json(
                                        {
                                            "process.jobControlOptions": job_process.jobControlOptions,
                                            "job.mode": job_ctrl_exec,
                                        }, force_string=False
                                    ),
                                })
                            )

                # 'response' will take precedence, but (somewhat) align 'Prefer: return' value to match intention
                # they are not 100% compatible because output 'transmissionMode' must be considered when
                # resolving 'response', but given both 'response' and 'transmissionMode' override 'Prefer',
                # this is an "acceptable" compromise (see docs 'Execution Response' section for more details)
                if field == "execution_response":
                    if value == ExecuteResponse.RAW:
                        job.execution_return = ExecuteReturnPreference.REPRESENTATION
                    else:
                        job.execution_return = ExecuteReturnPreference.MINIMAL

                setattr(job, field, value)

        settings = get_settings(request)
        subscribers = map_job_subscribers(body, settings=settings)
        if not subscribers and body.get("subscribers") == {}:
            subscribers = {}  # asking to remove all subscribers explicitly
        if subscribers is not None:
            job.subscribers = subscribers

        # for both 'mode' and 'response'
        # if provided both in body and corresponding 'Prefer' header parameter,
        # the body parameter takes precedence (set in code above)
        # however, if provided only in header, allow override of the body parameter considered as "higher priority"
        loc = "header"
        if ExecuteMode.get(body.get("mode"), default=ExecuteMode.AUTO) == ExecuteMode.AUTO:
            mode, wait, _ = parse_prefer_header_execute_mode(
                request.headers,
                job_process.jobControlOptions,
                return_auto=True,
            )
            job.execution_mode = mode
            job.execution_wait = wait if mode == ExecuteMode.SYNC else job.execution_wait
        if "response" not in body:
            job_return = parse_prefer_header_return(request.headers)
            if job_return:
                job.execution_return = job_return
                if job_return == ExecuteReturnPreference.REPRESENTATION:
                    job.execution_response = ExecuteResponse.RAW
                else:
                    job.execution_response = ExecuteResponse.DOCUMENT

    except ValueError as exc:
        raise HTTPUnprocessableEntity(
            json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
                "type": "InvalidJobUpdate",
                "title": "Invalid Job Execution Update",
                "detail": "Could not update the job execution definition using specified parameters.",
                "status": HTTPUnprocessableEntity.code,
                "error": type(exc),
                "cause": {"name": field, "in": loc},
                "value": repr_json(value, force_string=False),
            })
        )

    LOGGER.info("Updating %s", job)
    db = get_db(request)
    store = db.get_store(StoreJobs)
    store.update_job(job)


def validate_job_json(request):
    # type: (Request) -> JSON
    """
    Validates that the request contains valid :term:`JSON` contents, but not necessary valid against expected schema.

    .. seealso::
        :func:`validate_job_schema`
    """
    if ContentType.APP_JSON not in request.content_type:
        raise HTTPUnsupportedMediaType(json={
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-4/1.0/unsupported-media-type",
            "title": "Unsupported Media-Type",
            "detail": f"Request 'Content-Type' header other than '{ContentType.APP_JSON}' is not supported.",
            "code": "InvalidHeaderValue",
            "name": "Content-Type",
            "value": str(request.content_type)
        })
    try:
        json_body = request.json_body
    except Exception as ex:
        raise HTTPBadRequest(json={
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-4/1.0/unsupported-media-type",
            "title": "Bad Request",
            "detail": f"Invalid JSON body cannot be decoded for job submission. [{ex}]",
        })
    return json_body


def validate_job_schema(
    payload,                    # type: Any
    headers,                    # type: Optional[AnyHeadersContainer]
    body_schema=sd.Execute,     # type: Union[Type[sd.Execute], Type[sd.PatchJobBodySchema]]
):                              # type: (...) -> ProcessExecution
    """
    Validates that the input :term:`Job` payload is valid :term:`JSON` for an execution request.
    """
    if headers:
        schema = get_header("Content-Schema", headers)
        if schema not in [None, body_schema._schema]:
            raise HTTPUnprocessableEntity(
                json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
                    "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-4/1.0/unsupported-schema",
                    "title": "Invalid Job Execution Schema",
                    "detail": "Specified Content-Schema reference is unsupported for job creation.",
                    "status": HTTPUnprocessableEntity.code,
                    "error": "Unsupported content schema.",
                    "cause": {
                        "name": "Content-Schema",
                        "in": "headers",
                        "schema": {"const": body_schema._schema}
                    },
                    "value": repr_json(schema),
                })
            )

    try:
        json_body = body_schema().deserialize(payload)
    except colander.Invalid as ex:
        raise HTTPUnprocessableEntity(
            json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
                "type": "InvalidSchema",
                "title": "Invalid Job Execution Schema",
                "detail": "Execution body failed schema validation.",
                "status": HTTPUnprocessableEntity.code,
                "error": ex.msg,
                "cause": ex.asdict(),
                "value": repr_json(ex.value),
            })
        )
    return json_body


def validate_job_accept_header(headers, execution_mode):
    # type: (AnyHeadersContainer, AnyExecuteMode) -> Optional[str]
    """
    Validate that the submitted ``Accept`` header is permitted.
    """
    accept = get_header("accept", headers)
    if not accept:
        return
    # compare with 'in' to allow alternate types, one of which must be JSON for async
    if ContentType.APP_JSON in accept:
        return ContentType.APP_JSON
    # anything always allowed in sync, since results returned directly
    if execution_mode in [ExecuteMode.SYNC, ExecuteMode.AUTO]:
        return accept
    if ContentType.ANY in accept:
        return
    raise HTTPNotAcceptable(
        json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize({
            "type": "NotAcceptable",
            "title": "Execution request is not acceptable.",
            "detail": (
                "When running asynchronously, the Accept header must correspond "
                "to the Job Status response instead of the desired Result response "
                "returned when executing synchronously."
            ),
            "status": HTTPNotAcceptable.code,
            "cause": {"name": "Accept", "in": "headers"},
            "value": repr_json(accept, force_string=False),
        })
    )


def validate_job_accept_profile(headers, execution_mode):
    # type: (AnyHeadersContainer, AnyExecuteMode) -> Optional[str]
    """
    Validate the ``Accept-Profile`` header against known :term:`Job` execution results if any is provided.
    """
    profile = get_header("Accept-Profile", headers)
    if not profile:
        return
    profile_allowed_sync = [sd.OGC_API_PROC_PROFILE_RESULTS, sd.OGC_API_PROC_PROFILE_RESULTS_REL]
    profile_allowed_async = [sd.OGC_API_PROC_PROFILE_JOB_DESC]
    if (
        execution_mode in [ExecuteMode.SYNC, ExecuteMode.AUTO, None] and
        profile not in profile_allowed_sync
    ):
        raise HTTPNotAcceptable(
            json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize(
                {
                    "type": "NotAcceptable",
                    "title": "Execution request is not acceptable.",
                    "detail": (
                        "When running synchronously, the Accept-Profile header must correspond "
                        "to the desired Results response to be returned directly or be omitted "
                        "for automatic resolution of the relevant Results representation."
                    ),
                    "status": HTTPNotAcceptable.code,
                    "cause": {
                        "name": "Accept-Profile",
                        "in": "headers",
                        "schema": {"type": "string", "enum": profile_allowed_sync},
                    },
                    "value": repr_json(profile, force_string=False),
                }
            )
        )
    if (
        execution_mode == ExecuteMode.ASYNC and
        profile not in profile_allowed_async
    ):
        raise HTTPNotAcceptable(
            json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize(
                {
                    "type": "NotAcceptable",
                    "title": "Execution request is not acceptable.",
                    "detail": (
                        "When running asynchronously, the Accept-Profile header must correspond "
                        "to the Job Status response from the submission instead of the desired "
                        "Result response returned when executing synchronously."
                    ),
                    "status": HTTPNotAcceptable.code,
                    "cause": {
                        "name": "Accept-Profile",
                        "in": "headers",
                        "schema": {"type": "string", "enum": profile_allowed_async},
                    },
                    "value": repr_json(profile, force_string=False),
                }
            )
        )
    return profile


def validate_process_exec_mode(job_control_options, execution_mode):
    # type: (List[AnyExecuteControlOption], Optional[AnyExecuteMode]) -> None
    """
    Verify that a certain :term:`Job` execution mode fulfills the :term:`Process` ``jobControlOptions`` prerequisite.

    Assumes that any applicable resolution of the :term:`Job` execution mode (header, query, body, etc.)
    and the relevant control options was already performed by any applicable upstream operations.

    .. seealso::
        - :ref:`proc_exec_mode`
        - :func:`parse_prefer_header_execute_mode`

    :raises HTTPUnprocessableEntity: If the execution mode is not permitted by the :term:`Process`.
    """
    job_ctrl_exec = ExecuteControlOption.from_mode(execution_mode)
    if not (job_ctrl_exec in job_control_options or execution_mode in [ExecuteMode.AUTO, None]):
        raise HTTPUnprocessableEntity(
            json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize(
                {
                    "type": "InvalidJobControlOptions",
                    "title": "Invalid Job Execution Mode specified against permitted Process Job Control Options.",
                    "detail": "Any hint of a job execution strategy must respect the process prerequisites.",
                    "status": HTTPUnprocessableEntity.code,
                    "cause": {"name": "process.jobControlOptions"},
                    "value": repr_json(
                        {
                            "process.jobControlOptions": job_control_options,
                            "job.mode": execution_mode,
                        },
                        force_string=False,
                    ),
                }
            )
        )


def validate_process_id(job_process, payload):
    # type: (Process, ProcessExecution) -> None
    """
    Validates that the specified ``process`` in the payload corresponds to the referenced :term:`Job` :term:`Process`.

    If not ``process```is specified, no check is performed. The :term:`Job` is assumed to have pre-validated that
    the :term:`Process` is appropriate from another reference, such as using the ID from the path or a query parameter.

    :raises HTTPException: Corresponding error for detected invalid combination of process references.
    """
    if "process" in payload:
        # note: don't use 'get_process' for input process, as it might not even exist!
        req_process_url = payload["process"]
        req_process_id = payload["process"].rsplit("/processes/", 1)[-1]
        if req_process_id != job_process.id or req_process_url != job_process.processDescriptionURL:
            raise HTTPBadRequest(
                json=sd.ErrorJsonResponseBodySchema(schema_include=True).deserialize(
                    {
                        "type": "InvalidJobUpdate",
                        "title": "Invalid Job Execution Update",
                        "detail": "Update of the reference process for the job execution is not permitted.",
                        "status": HTTPBadRequest.code,
                        "cause": {"name": "process", "in": "body"},
                        "value": repr_json(
                            {
                                "body.process": payload["process"],
                                "job.process": job_process.processDescriptionURL,
                            }, force_string=False
                        ),
                    }
                )
            )


def validate_process_io(process, payload):
    # type: (Process, ProcessExecution) -> None
    """
    Preemptively verify submitted parameters for execution against expected process definition.

    Verify missing inputs or obvious type mismatches, but nothing too over-complicated. The ideas behind this
    function is to avoid unnecessary assignation of :mod:`celery` worker and :term:`Docker` resources that would
    be guaranteed to fail as soon as the process execution started.

    This function is **NOT** intended to catch all erroneous inputs, nor validate their values.
    For example, out-of-range values or unreachable file reference URLs are not guaranteed.
    However, basic checks such as unacceptable types or cardinality can be performed.
    Assumes that schema pre-validation was accomplished to minimally guarantee that the structure is valid.

    :param process: Process description that provides expected inputs and outputs.
    :param payload: Submitted job execution body.
    :raises HTTPException: Corresponding error for detected invalid combination of inputs or outputs.
    """
    payload_inputs = convert_input_values_schema(payload.get("inputs", {}), JobInputsOutputsSchema.OLD) or []
    payload_outputs = convert_output_params_schema(payload.get("outputs", {}), JobInputsOutputsSchema.OLD) or []

    for io_type, io_payload, io_process in [
        ("inputs", payload_inputs, process.inputs),
        ("outputs", payload_outputs, process.outputs),
    ]:
        io_payload_set = {get_any_id(io_info) for io_info in io_payload}  # can have repeated IDs (list representation)
        io_process_map = {get_any_id(io_info): io_info for io_info in io_process}  # guaranteed unique IDs
        unknown_ids = set(io_payload_set) - set(io_process_map)
        if unknown_ids:
            raise OWSInvalidParameterValue(json={
                "code": "InvalidParameterValue",
                "name": io_type,
                "description": (
                    f"Submitted execution {io_type} contain unknown identifiers to the process description. "
                    f"Valid {io_type} identifiers are: {sorted(list(io_process_map))}."
                ),
                "value": list(unknown_ids),
            })
        for io_id, io_proc in io_process_map.items():
            io_name = f"{io_type}.{io_id}"
            io_exec = list(filter(lambda _io: get_any_id(_io) == io_id, io_payload))
            io_format = io_proc.get("formats", [])
            # validate format if more strict supported Media-Types are specified
            # requested format must match with the supported ones by the process
            # ignore explict any or default plain text representation always available
            if io_format:
                io_ctypes = {
                    # field 'type' as Content-Type is only valid in execute payload
                    # during process description, it is used as the data/value type
                    get_field(io_fmt, "mime_type", extra_variations=["type"], default="")
                    for io_fmt in io_exec
                }
                io_ctypes = [ctype for ctype in io_ctypes if ctype]
                io_accept = {
                    get_field(io_fmt, "mime_type", search_variations=True, default="")
                    for io_fmt in io_format
                }
                io_accept = [clean_media_type_format(ctype) for ctype in io_accept if ctype]
                # no format specified explicitly must ensure that the process description has one by default
                if not io_ctypes:
                    io_default = any(get_field(io_fmt, "default", default=False) for io_fmt in io_format)
                    if not io_default:
                        raise OWSInvalidParameterValue(json={
                            "code": "InvalidParameterValue",
                            "name": io_name,
                            "description": (
                                f"Submitted '{io_name}' requires explicit Content-Type specification to"
                                "respect process description that defines no default format."
                            ),
                            "value": {
                                "supportedFormats": list(io_accept),
                                "executionFormats": None,
                            }
                        })
                # if a media-type was specified, allow it even if not
                # within "allowed" when they are the default 'any' types
                any_types = [ContentType.ANY, ContentType.TEXT_PLAIN]
                if not all(io_fmt in any_types for io_fmt in io_accept):
                    # otherwise, all formats must be within allowed ones
                    io_accept += any_types
                    if not all(io_fmt in io_accept for io_fmt in io_ctypes):
                        raise OWSInvalidParameterValue(json={
                            "code": "InvalidParameterValue",
                            "name": io_name,
                            "description": (
                                f"Submitted '{io_name}' requested Content-Types that do not respect "
                                "supported formats specified by the process description."
                            ),
                            "value": {
                                "supportedFormats": list(io_accept),
                                "executionFormats": list(io_ctypes),
                            }
                        })

            if io_type == "inputs":
                io_min = io_proc["minOccurs"]
                io_max = io_proc["maxOccurs"]
                io_len = len(io_exec)
                if io_len < io_min or (isinstance(io_max, int) and io_len > io_max):
                    raise OWSInvalidParameterValue(json={
                        "code": "InvalidParameterValue",
                        "name": io_name,
                        "description": f"Submitted '{io_name}' does not respect process description cardinality.",
                        "value": {
                            "minOccurs": io_min,
                            "maxOccurs": io_max,
                            "occurrences": io_len,
                        }
                    })
