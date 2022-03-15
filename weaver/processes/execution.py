import logging
import os
from time import sleep
from typing import TYPE_CHECKING

import colander
from celery.utils.log import get_task_logger
from owslib.util import clean_ows_url
from owslib.wps import ComplexDataInput
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotAcceptable, HTTPNotImplemented
from pyramid_celery import celery_app as app

from weaver.database import get_db
from weaver.datatype import Process, Service
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import AcceptLanguage, ContentType
from weaver.notify import encrypt_email, notify_job_complete
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes import wps_package
from weaver.processes.constants import WPS_COMPLEX_DATA
from weaver.processes.convert import get_field, ows2json_output_data
from weaver.processes.types import ProcessType
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.store.base import StoreJobs, StoreProcesses
from weaver.utils import (
    get_any_id,
    get_any_value,
    get_header,
    get_registry,
    get_settings,
    now,
    parse_prefer_header_execute_mode,
    raise_on_xml_exception,
    wait_secs
)
from weaver.visibility import Visibility
from weaver.wps.utils import (
    check_wps_status,
    get_wps_client,
    get_wps_local_status_location,
    get_wps_output_context,
    get_wps_output_path,
    get_wps_output_url,
    load_pywps_config
)
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from uuid import UUID
    from typing import Dict, List, Optional, Tuple, Union

    from celery.task import Task
    from pyramid.request import Request
    from pywps.inout.inputs import ComplexInput

    from weaver.datatype import Job
    from weaver.processes.convert import OWS_Input_Type, ProcessOWS
    from weaver.status import StatusType
    from weaver.typedefs import HeadersType, HeaderCookiesType, JSON, SettingsType
    from weaver.visibility import AnyVisibility


class JobProgress(object):
    """
    Job process execution progress.
    """
    SETUP = 1
    DESCRIBE = 2
    GET_INPUTS = 3
    GET_OUTPUTS = 4
    EXECUTE_REQUEST = 5
    EXECUTE_STATUS_LOCATION = 6
    EXECUTE_MONITOR_START = 7
    EXECUTE_MONITOR_LOOP = 8
    EXECUTE_MONITOR_DONE = 96
    EXECUTE_MONITOR_END = 98
    NOTIFY = 99
    DONE = 100


@app.task(bind=True)
def execute_process(self, job_id, wps_url, headers=None):
    # type: (Task, UUID, str, Optional[HeadersType]) -> StatusType
    """
    Celery task that executes the WPS process job monitoring as status updates (local and remote).
    """
    from weaver.wps.service import get_pywps_service

    LOGGER.debug("Job execute process called.")

    # reset the connection because we are in a forked celery process
    registry = get_registry(None)  # local thread, whether locally or dispatched celery
    settings = get_settings(registry)
    db = get_db(registry, reset_connection=True)
    store = db.get_store(StoreJobs)
    job = store.fetch_by_id(job_id)
    job.started = now()
    job.status = Status.STARTED  # will be mapped to 'RUNNING'
    job.status_message = "Job {}.".format(Status.STARTED)  # will preserve detail of STARTED vs RUNNING
    job.save_log(message=job.status_message)

    task_logger = get_task_logger(__name__)
    job.save_log(logger=task_logger, message="Job task setup initiated.")
    load_pywps_config(settings)
    job.progress = JobProgress.SETUP
    job.task_id = self.request.id
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
        job.save_log(logger=task_logger, message="Employed WPS URL: [{!s}]".format(wps_url), level=logging.DEBUG)
        job.save_log(logger=task_logger, message="Execute WPS request for process [{!s}]".format(job.process))
        wps_process = fetch_wps_process(job, wps_url, headers, settings)

        # prepare inputs
        job.progress = JobProgress.GET_INPUTS
        job.save_log(logger=task_logger, message="Fetching job input definitions.")
        wps_inputs = parse_wps_inputs(wps_process, job)

        # prepare outputs
        job.progress = JobProgress.GET_OUTPUTS
        job.save_log(logger=task_logger, message="Fetching job output definitions.")
        wps_outputs = [(o.identifier, o.dataType == WPS_COMPLEX_DATA) for o in wps_process.processOutputs]

        # if process refers to a remote WPS provider, pass it down to avoid unnecessary re-fetch request
        if job.is_local:
            process = None  # already got all the information needed pre-loaded in PyWPS service
        else:
            service = Service(name=job.service, url=wps_url)
            process = Process.from_ows(wps_process, service, settings)

        job.progress = JobProgress.EXECUTE_REQUEST
        job.save_log(logger=task_logger, message="Starting job process execution.")
        job.save_log(logger=task_logger,
                     message="Following updates could take a while until the Application Package answers...")

        wps_worker = get_pywps_service(environ=settings, is_worker=True)
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
                     message="Updated job status location: [{}].".format(wps_status_path))

        job.status = Status.RUNNING
        job.status_message = execution.statusMessage or "{} initiation done.".format(str(job))
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
                raise Exception("Could not read status document after {} retries. Giving up.".format(max_retries))
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
                job.status_message = (
                    "Job execution monitoring (progress: {}%, status: {})."
                    .format(execution.percentCompleted, job_msg or "n/a")
                )

                if execution.isComplete():
                    msg_progress = " (status: {})".format(job_msg) if job_msg else ""
                    if execution.isSucceded():
                        wps_package.retrieve_package_job_log(execution, job, progress_min, progress_max)
                        job.status = map_status(Status.SUCCEEDED)
                        job.status_message = "Job succeeded{}.".format(msg_progress)
                        job.progress = progress_max
                        job.save_log(logger=task_logger)
                        job_results = [ows2json_output_data(output, process, settings)
                                       for output in execution.processOutputs]
                        job.results = make_results_relative(job_results, settings)
                    else:
                        task_logger.debug("Job failed.")
                        wps_package.retrieve_package_job_log(execution, job, progress_min, progress_max)
                        job.status_message = "Job failed{}.".format(msg_progress)
                        job.progress = progress_max
                        job.save_log(errors=execution.errors, logger=task_logger)
                    task_logger.debug("Mapping Job references with generated WPS locations.")
                    map_locations(job, settings)
                    job = store.update_job(job)

            except Exception as exc:
                num_retries += 1
                task_logger.debug("Exception raised: %s", repr(exc))
                job.status_message = "Could not read status XML document for {!s}. Trying again...".format(job)
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
        job.status_message = "Failed to run {!s}.".format(job)
        exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
        errors = "{0}: {1!s}".format(exception_class, exc)
        job.save_log(errors=errors, logger=task_logger)
        job = store.update_job(job)
    finally:
        # if task worker terminated, local 'job' is out of date compared to remote/background runner last update
        job = store.fetch_by_id(job.id)
        if task_terminated and map_status(job.status) == Status.FAILED:
            job.status = Status.DISMISSED
        task_success = map_status(job.status) not in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]
        if task_success:
            job.progress = JobProgress.EXECUTE_MONITOR_END
        job.status_message = "Job {}.".format(job.status)
        job.save_log(logger=task_logger)

        if task_success:
            job.progress = JobProgress.NOTIFY
        send_job_complete_notification_email(job, task_logger, settings)

        if job.status not in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            job.status = Status.SUCCEEDED
        job.status_message = "Job {}.".format(job.status)
        job.mark_finished()
        if task_success:
            job.progress = JobProgress.DONE
        job.save_log(logger=task_logger, message="Job task complete.")
        job = store.update_job(job)

    return job.status


def fetch_wps_process(job, wps_url, headers, settings):
    # type: (Job, str, HeadersType, SettingsType) -> ProcessOWS
    """
    Retrieves the WPS process description from the local or remote WPS reference URL.
    """
    try:
        wps = get_wps_client(wps_url, settings, headers=headers, language=job.accept_language)
        raise_on_xml_exception(wps._capabilities)  # noqa
    except Exception as ex:
        job.save_log(errors=ex, message="Failed WPS client creation for process [{!s}]".format(job.process))
        raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
    try:
        wps_process = wps.describeprocess(job.process)
    except Exception as ex:
        raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))
    return wps_process


def parse_wps_inputs(wps_process, job):
    # type: (ProcessOWS, Job) -> List[Tuple[str, OWS_Input_Type]]
    """
    Parses expected WPS process inputs against submitted job input values considering supported process definitions.
    """
    complex_inputs = {}  # type: Dict[str, ComplexInput]
    for process_input in wps_process.dataInputs:
        if WPS_COMPLEX_DATA in process_input.dataType:
            complex_inputs[process_input.identifier] = process_input

    try:
        wps_inputs = list()
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
            # in case of array inputs, must repeat (id,value)
            if isinstance(input_val, list):
                input_values = input_val
                input_details = input_val  # each value has its own metadata
            else:
                input_values = [input_val]
                input_details = [job_input]  # metadata directly in definition, not nested per array value

            # we need to support file:// scheme but PyWPS doesn't like them so remove the scheme file://
            input_values = [
                # when value is an array of dict that each contain a file reference
                (get_any_value(val)[7:] if str(get_any_value(val)).startswith("file://") else get_any_value(val))
                if isinstance(val, dict) else
                # when value is directly a single dict with file reference
                (val[7:] if str(val).startswith("file://") else val)
                for val in input_values
            ]

            for input_value, input_detail in zip(input_values, input_details):
                # need to use ComplexDataInput structure for complex input
                if input_id in complex_inputs:
                    # if provided, pass down specified data input format to allow validation against supported formats
                    ctype = get_field(input_detail, "type", default=None)
                    encoding = None
                    if not ctype:
                        media_format = get_field(input_detail, "format", default=None)
                        if isinstance(media_format, dict):
                            ctype = get_field(input_detail, "mime_type", search_variations=True, default=None)
                            encoding = get_field(input_detail, "encoding", search_variations=True, default=None)
                    wps_inputs.append((input_id, ComplexDataInput(input_value, mimeType=ctype, encoding=encoding)))
                # need to use literal String for anything else than complex
                # FIXME: pre-validate allowed literal values?
                # TODO: BoundingBox not supported
                else:
                    wps_inputs.append((input_id, str(input_value)))
    except KeyError:
        wps_inputs = []
    return wps_inputs


def send_job_complete_notification_email(job, task_logger, settings):
    # type: (Job, logging.Logger, SettingsType) -> None
    """
    Sends the notification email of completed execution if it was requested during job submission.
    """
    if job.notification_email is not None:
        try:
            notify_job_complete(job, job.notification_email, settings)
            message = "Notification email sent successfully."
            job.save_log(logger=task_logger, message=message)
        except Exception as exc:
            exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
            exception = "{0}: {1!s}".format(exception_class, exc)
            message = "Couldn't send notification email ({})".format(exception)
            job.save_log(errors=message, logger=task_logger, message=message)


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
        ref = res.get("reference")
        if isinstance(ref, str) and ref:
            if ref.startswith(wps_url):
                ref = ref.replace(wps_url, "", 1)
            if ref.startswith(wps_path):
                ref = ref.replace(wps_path, "", 1)
            res["reference"] = ref
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


def submit_job(request, reference, tags=None):
    # type: (Request, Union[Service, Process], Optional[List[str]]) -> JSON
    """
    Generates the job submission from details retrieved in the request.

    .. seealso::
        :func:`submit_job_handler` to provide elements pre-extracted from requests or from other parsing.
    """
    # validate body with expected JSON content and schema
    if ContentType.APP_JSON not in request.content_type:
        raise HTTPBadRequest(json={
            "code": "InvalidHeaderValue",
            "name": "Content-Type",
            "description": "Request 'Content-Type' header other than '{}' not supported.".format(ContentType.APP_JSON),
            "value": str(request.content_type)
        })
    try:
        json_body = request.json_body
    except Exception as ex:
        raise HTTPBadRequest("Invalid JSON body cannot be decoded for job submission. [{}]".format(ex))
    # validate context if needed later on by the job for early failure
    context = get_wps_output_context(request)

    provider_id = None  # None OK if local
    process_id = None   # None OK if remote, but can be found as well if available from WPS-REST path  # noqa
    tags = tags or []
    lang = request.accept_language.header_value  # can only preemptively check if local process
    if isinstance(reference, Process):
        service_url = reference.processEndpointWPS1
        process_id = reference.id
        visibility = reference.visibility
        is_workflow = reference.type == ProcessType.WORKFLOW
        is_local = True
        tags += "local"
        if lang and request.accept_language.best_match(AcceptLanguage.values()) is None:
            raise HTTPNotAcceptable("Requested language [{}] is not in supported languages [{}].".format(
                lang, ", ".join(AcceptLanguage.values())
            ))
    elif isinstance(reference, Service):
        service_url = reference.url
        provider_id = reference.id
        process_id = request.matchdict.get("process_id")
        visibility = Visibility.PUBLIC
        is_workflow = False
        is_local = False
        tags += "remote"
    else:
        LOGGER.error("Expected process/service, got: %s", type(reference))
        raise TypeError("Invalid process or service reference to execute job.")
    tags = request.params.get("tags", "").split(",") + tags
    user = request.authenticated_userid
    headers = dict(request.headers)
    settings = get_settings(request)
    return submit_job_handler(json_body, settings, service_url, provider_id, process_id, is_workflow, is_local,
                              visibility, language=lang, headers=headers, tags=tags, user=user, context=context)


# FIXME: this should not be necessary if schema validators correctly implement OneOf(values)
def _validate_job_parameters(json_body):
    # type: (JSON) -> None
    """
    Tests supported parameters not automatically validated by colander deserialize.
    """
    if json_body["mode"] not in [ExecuteMode.ASYNC, ExecuteMode.AUTO]:
        raise HTTPNotImplemented(detail="Execution mode '{}' not supported.".format(json_body["mode"]))

    if json_body["response"] != ExecuteResponse.DOCUMENT:
        raise HTTPNotImplemented(detail="Execution response type '{}' not supported.".format(json_body["response"]))

    outputs = json_body.get("outputs", [])
    if isinstance(outputs, dict):
        outputs = [dict(id=out, **keys) for out, keys in outputs.items()]
    for job_output in outputs:
        mode = job_output["transmissionMode"]
        if mode not in ExecuteTransmissionMode.values():
            raise HTTPNotImplemented(detail="Execute transmissionMode '{}' not supported.".format(mode))


def submit_job_handler(payload,             # type: JSON
                       settings,            # type: SettingsType
                       service_url,         # type: str
                       provider_id=None,    # type: Optional[str]
                       process_id=None,     # type: str
                       is_workflow=False,   # type: bool
                       is_local=True,       # type: bool
                       visibility=None,     # type: Optional[AnyVisibility]
                       language=None,       # type: Optional[str]
                       headers=None,        # type: Optional[HeaderCookiesType]
                       tags=None,           # type: Optional[List[str]]
                       user=None,           # type: Optional[int]
                       context=None,        # type: Optional[str]
                       ):                   # type: (...) -> JSON
    """
    Submits the job to the Celery worker with provided parameters.

    Assumes that parameters have been pre-fetched and validated, except for the input payload.
    """
    try:
        json_body = sd.Execute().deserialize(payload)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))

    # TODO: remove when all parameter variations are supported
    # FIXME:
    #   - support 'response: raw' (https://github.com/crim-ca/weaver/issues/376)
    #   - allow omitting 'outputs' (https://github.com/crim-ca/weaver/issues/375)
    _validate_job_parameters(json_body)
    db = get_db(settings)
    headers = headers or {}
    if is_local:
        proc_store = db.get_store(StoreProcesses)
        process = proc_store.fetch_by_id(process_id)
        job_ctl_opts = process.jobControlOptions
    else:
        job_ctl_opts = ExecuteControlOption.values()
    mode, wait, applied = parse_prefer_header_execute_mode(headers, job_ctl_opts)
    get_header("prefer", headers, pop=True)

    is_execute_async = ExecuteMode.get(json_body["mode"]) != ExecuteMode.SYNC   # convert auto to async
    notification_email = json_body.get("notification_email")
    encrypted_email = encrypt_email(notification_email, settings) if notification_email else None

    store = db.get_store(StoreJobs)  # type: StoreJobs
    job = store.save_job(task_id=Status.ACCEPTED, process=process_id, service=provider_id,
                         inputs=json_body.get("inputs"), is_local=is_local, is_workflow=is_workflow,
                         access=visibility, user_id=user, execute_async=is_execute_async, custom_tags=tags,
                         notification_email=encrypted_email, accept_language=language, context=context)
    job.save_log(logger=LOGGER, message="Job task submitted for execution.", status=Status.ACCEPTED, progress=0)
    job = store.update_job(job)
    location_base = "/providers/{provider_id}".format(provider_id=provider_id) if provider_id else ""
    location_url = "{base_url}{location_base}/processes/{process_id}/jobs/{job_id}".format(
        base_url=get_wps_restapi_base_url(settings),
        location_base=location_base,
        process_id=process_id,
        job_id=job.id
    )

    result = execute_process.delay(job_id=job.id, wps_url=clean_ows_url(service_url), headers=headers)
    LOGGER.debug("Celery pending task [%s] for job [%s].", result.id, job.id)
    if mode == ExecuteMode.SYNC and wait:
        LOGGER.debug("Celery task requested as sync if it completes before (wait=%ss)", wait)
        result.wait(timeout=wait)
        if result.ready():
            job = store.fetch_by_id(job.id)
            body = job.json(container=settings, self_link="status")
            body["location"] = location_url
            return body
        else:
            LOGGER.debug("Celery task requested as sync took too long to complete (wait=%ss). Continue in async.", wait)

    LOGGER.debug("Celery task submitted to run async.", wait)
    body = {
        "jobID": job.id,
        "processID": job.process,
        "providerID": provider_id,  # dropped by validator if not applicable
        "status": map_status(Status.ACCEPTED),
        "location": location_url
    }
    return body
