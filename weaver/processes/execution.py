import logging
import os
from time import sleep
from typing import TYPE_CHECKING

import colander
from celery.utils.log import get_task_logger
from owslib.util import clean_ows_url
from owslib.wps import ComplexDataInput
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotImplemented
from pyramid_celery import celery_app as app

from weaver.database import get_db
from weaver.datatype import Process, Service
from weaver.execute import (
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_AUTO,
    EXECUTE_MODE_SYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_OPTIONS
)
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.notify import encrypt_email, notify_job_complete
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes import wps_package
from weaver.processes.constants import WPS_COMPLEX_DATA
from weaver.processes.convert import ows2json_output_data
from weaver.processes.types import PROCESS_WORKFLOW
from weaver.status import STATUS_ACCEPTED, STATUS_FAILED, STATUS_STARTED, STATUS_SUCCEEDED, map_status
from weaver.store.base import StoreJobs
from weaver.utils import get_any_id, get_any_value, get_settings, now, raise_on_xml_exception, wait_secs
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.wps.utils import (
    check_wps_status,
    get_wps_client,
    get_wps_local_status_location,
    get_wps_output_path,
    get_wps_output_url,
    load_pywps_config
)
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import List, Optional, Union
    from pyramid.request import Request
    from weaver.datatype import Job
    from weaver.typedefs import HeaderCookiesType, JSON, SettingsType

# job process execution progress
JOB_PROGRESS_SETUP = 1
JOB_PROGRESS_DESCRIBE = 2
JOB_PROGRESS_GET_INPUTS = 3
JOB_PROGRESS_GET_OUTPUTS = 4
JOB_PROGRESS_EXECUTE_REQUEST = 5
JOB_PROGRESS_EXECUTE_STATUS_LOCATION = 6
JOB_PROGRESS_EXECUTE_MONITOR_START = 7
JOB_PROGRESS_EXECUTE_MONITOR_LOOP = 8
JOB_PROGRESS_EXECUTE_MONITOR_DONE = 96
JOB_PROGRESS_EXECUTE_MONITOR_ERROR = 97
JOB_PROGRESS_EXECUTE_MONITOR_END = 98
JOB_PROGRESS_NOTIFY = 99
JOB_PROGRESS_DONE = 100


@app.task(bind=True)
def execute_process(self, job_id, url, headers=None):
    from weaver.wps.service import get_pywps_service

    LOGGER.debug("Job execute process called.")
    settings = get_settings(app)
    task_logger = get_task_logger(__name__)
    load_pywps_config(settings)

    task_logger.debug("Job task setup.")

    # reset the connection because we are in a forked celery process
    db = get_db(app, reset_connection=True)
    store = db.get_store(StoreJobs)

    job = store.fetch_by_id(job_id)
    job.started = now()
    job.task_id = self.request.id
    job.progress = JOB_PROGRESS_SETUP
    job.save_log(logger=task_logger, message="Job task setup completed.")
    job = store.update_job(job)

    try:
        try:
            job.progress = JOB_PROGRESS_DESCRIBE
            job.save_log(logger=task_logger, message="Employed WPS URL: [{!s}]".format(url), level=logging.DEBUG)
            job.save_log(logger=task_logger, message="Execute WPS request for process [{!s}]".format(job.process))
            wps = get_wps_client(url, settings, headers=headers, language=job.accept_language)
            raise_on_xml_exception(wps._capabilities)   # noqa
        except Exception as ex:
            job.save_log(errors=ex, message="Failed WPS client creation for process [{!s}]".format(job.process))
            raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
        try:
            wps_process = wps.describeprocess(job.process)
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))

        # prepare inputs
        job.progress = JOB_PROGRESS_GET_INPUTS
        job.save_log(logger=task_logger, message="Fetching job input definitions.")
        complex_inputs = []
        for process_input in wps_process.dataInputs:
            if WPS_COMPLEX_DATA in process_input.dataType:
                complex_inputs.append(process_input.identifier)

        try:
            wps_inputs = list()
            # parse both dict and list type inputs
            job_inputs = job.inputs.items() if isinstance(job.inputs, dict) else job.get("inputs", [])
            for process_input in job_inputs:
                if isinstance(process_input, tuple):
                    input_id = process_input[0]
                    process_value = process_input[1]
                else:
                    input_id = get_any_id(process_input)
                    process_value = get_any_value(process_input)
                # in case of array inputs, must repeat (id,value)
                input_values = process_value if isinstance(process_value, list) else [process_value]

                # we need to support file:// scheme but PyWPS doesn't like them so remove the scheme file://
                input_values = [
                    # when value is an array of dict that each contain a file reference
                    (get_any_value(val)[7:] if str(get_any_value(val)).startswith("file://") else get_any_value(val))
                    if isinstance(val, dict) else
                    # when value is directly a single dict with file reference
                    (val[7:] if str(val).startswith("file://") else val)
                    for val in input_values
                ]

                # need to use ComplexDataInput structure for complex input
                # need to use literal String for anything else than complex
                # TODO: BoundingBox not supported
                wps_inputs.extend([
                    (input_id, ComplexDataInput(input_value) if input_id in complex_inputs else str(input_value))
                    for input_value in input_values])
        except KeyError:
            wps_inputs = []

        # prepare outputs
        job.progress = JOB_PROGRESS_GET_OUTPUTS
        job.save_log(logger=task_logger, message="Fetching job output definitions.")
        wps_outputs = [(o.identifier, o.dataType == WPS_COMPLEX_DATA) for o in wps_process.processOutputs]

        # if process refers to a remote WPS provider, pass it down to avoid unnecessary re-fetch request
        if job.is_local:
            process = None  # already got all the information needed pre-loaded in PyWPS service
        else:
            service = Service(name=job.service, url=url)
            process = Process.from_ows(wps_process, service, settings)

        mode = EXECUTE_MODE_ASYNC if job.execute_async else EXECUTE_MODE_SYNC
        job.progress = JOB_PROGRESS_EXECUTE_REQUEST
        job.save_log(logger=task_logger, message="Starting job process execution.")
        job.save_log(logger=task_logger,
                     message="Following updates could take a while until the Application Package answers...")

        wps_worker = get_pywps_service(environ=settings, is_worker=True)
        execution = wps_worker.execute_job(job.process, wps_inputs=wps_inputs, wps_outputs=wps_outputs,
                                           mode=mode, job_uuid=job.id, remote_process=process)
        if not execution.process and execution.errors:
            raise execution.errors[0]

        # adjust status location
        wps_status_path = get_wps_local_status_location(execution.statusLocation, settings)
        job.progress = JOB_PROGRESS_EXECUTE_STATUS_LOCATION
        LOGGER.debug("WPS status location that will be queried: [%s]", wps_status_path)
        if not wps_status_path.startswith("http") and not os.path.isfile(wps_status_path):
            LOGGER.warning("WPS status location not resolved to local path: [%s]", wps_status_path)
        job.save_log(logger=task_logger, level=logging.DEBUG,
                     message="Updated job status location: [{}].".format(wps_status_path))

        job.status = map_status(STATUS_STARTED)
        job.status_message = execution.statusMessage or "{} initiation done.".format(str(job))
        job.status_location = wps_status_path
        job.request = execution.request
        job.response = execution.response
        job.progress = JOB_PROGRESS_EXECUTE_MONITOR_START
        job.save_log(logger=task_logger, message="Starting monitoring of job execution.")
        job = store.update_job(job)

        max_retries = 5
        num_retries = 0
        run_step = 0
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= max_retries:
                raise Exception("Could not read status document after {} retries. Giving up.".format(max_retries))
            try:
                # NOTE:
                #   Don't actually log anything here until process is completed (success or fail) so that underlying
                #   WPS execution logs can be inserted within the current job log and appear continuously.
                #   Only update internal job fields in case they get referenced elsewhere.
                progress_min = JOB_PROGRESS_EXECUTE_MONITOR_LOOP
                progress_max = JOB_PROGRESS_EXECUTE_MONITOR_DONE
                job.progress = progress_min
                execution = check_wps_status(location=wps_status_path, settings=settings,
                                             sleep_secs=wait_secs(run_step))
                job_msg = (execution.statusMessage or "").strip()
                job.response = execution.response
                job.status = map_status(execution.getStatus())
                job.status_message = (
                    "Job execution monitoring (progress: {}%, status: {})."
                    .format(execution.percentCompleted, job_msg or "n/a")
                )
                # job.save_log(logger=task_logger)
                # job = store.update_job(job)

                if execution.isComplete():
                    msg_progress = " (status: {})".format(job_msg) if job_msg else ""
                    if execution.isSucceded():
                        wps_package.retrieve_package_job_log(execution, job, progress_min, progress_max)
                        job.status = map_status(STATUS_SUCCEEDED)
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

            except Exception as exc:
                num_retries += 1
                task_logger.debug("Exception raised: %s", repr(exc))
                job.status_message = "Could not read status XML document for {!s}. Trying again...".format(job)
                job.save_log(errors=execution.errors, logger=task_logger)
                sleep(1)
            else:
                # job.status_message = "Update {}...".format(str(job))
                # job.save_log(logger=task_logger)
                num_retries = 0
                run_step += 1
            finally:
                job = store.update_job(job)

    except Exception as exc:
        LOGGER.exception("Failed running [%s]", job)
        job.status = map_status(STATUS_FAILED)
        job.status_message = "Failed to run {!s}.".format(job)
        job.progress = JOB_PROGRESS_EXECUTE_MONITOR_ERROR
        exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
        errors = "{0}: {1!s}".format(exception_class, exc)
        job.save_log(errors=errors, logger=task_logger)
    finally:
        job.progress = JOB_PROGRESS_EXECUTE_MONITOR_END
        job.status_message = "Job {}.".format(job.status)
        job.save_log(logger=task_logger)

        # Send email if requested
        if job.notification_email is not None:
            job.progress = JOB_PROGRESS_NOTIFY
            try:
                notify_job_complete(job, job.notification_email, settings)
                message = "Notification email sent successfully."
                job.save_log(logger=task_logger, message=message)
            except Exception as exc:
                exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
                exception = "{0}: {1!s}".format(exception_class, exc)
                message = "Couldn't send notification email ({})".format(exception)
                job.save_log(errors=message, logger=task_logger, message=message)

        job.mark_finished()
        job.progress = JOB_PROGRESS_DONE
        job.save_log(logger=task_logger, message="Job task complete.")
        job = store.update_job(job)

    return job.status


def make_results_relative(results, settings):
    # type: (List[JSON], SettingsType) -> List[JSON]
    """
    Redefines job results to be saved in database as relative paths to output directory configured in PyWPS
    (i.e.: relative to ``weaver.wps_output_dir``).

    This allows us to easily adjust the exposed result HTTP path according to server configuration
    (i.e.: relative to ``weaver.wps_output_path`` and/or ``weaver.wps_output_url``) and it also avoid rewriting
    the whole database job results if the setting is changed later on.
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
    wps_loc = os.path.join(base_dir, job.wps_id)
    job_loc = os.path.join(base_dir, job.id)
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
    if CONTENT_TYPE_APP_JSON not in request.content_type:
        raise HTTPBadRequest("Request 'Content-Type' header other than '{}' not supported."
                             .format(CONTENT_TYPE_APP_JSON))
    try:
        json_body = request.json_body
    except Exception as ex:
        raise HTTPBadRequest("Invalid JSON body cannot be decoded for job submission. [{}]".format(ex))
    provider_id = None  # None OK if local
    process_id = None   # None OK if remote, but can be found as well if available from WPS-REST path
    tags = tags or []
    if isinstance(reference, Process):
        service_url = reference.processEndpointWPS1
        process_id = reference.id
        visibility = reference.visibility
        is_workflow = reference.type == PROCESS_WORKFLOW
        is_local = True
        tags += "local"
    elif isinstance(reference, Service):
        service_url = reference.url
        provider_id = reference.id
        process_id = request.matchdict.get("process_id")
        visibility = VISIBILITY_PUBLIC
        is_workflow = False
        is_local = False
        tags += "remote"
    else:
        LOGGER.error("Expected process/service, got: %s", type(reference))
        raise TypeError("Invalid process or service reference to execute job.")
    tags = request.params.get("tags", "").split(",") + tags
    user = request.authenticated_userid
    lang = request.accept_language.header_value
    headers = dict(request.headers)
    settings = get_settings(request)
    return submit_job_handler(json_body, settings, service_url, provider_id, process_id, is_workflow, is_local,
                              visibility, language=lang, auth=headers, tags=tags, user=user)


# FIXME: this should not be necessary if schema validators correctly implement OneOf(values)
def _validate_job_parameters(json_body):
    """
    Tests supported parameters not automatically validated by colander deserialize.
    """
    if json_body["mode"] not in [EXECUTE_MODE_ASYNC, EXECUTE_MODE_AUTO]:
        raise HTTPNotImplemented(detail="Execution mode '{}' not supported.".format(json_body["mode"]))

    if json_body["response"] != EXECUTE_RESPONSE_DOCUMENT:
        raise HTTPNotImplemented(detail="Execution response type '{}' not supported.".format(json_body["response"]))

    for job_output in json_body["outputs"]:
        mode = job_output["transmissionMode"]
        if mode not in EXECUTE_TRANSMISSION_MODE_OPTIONS:
            raise HTTPNotImplemented(detail="Execute transmissionMode '{}' not supported.".format(mode))


def submit_job_handler(payload,             # type: JSON
                       settings,            # type: SettingsType
                       service_url,         # type: str
                       provider_id=None,    # type: Optional[str]
                       process_id=None,     # type: str
                       is_workflow=False,   # type: bool
                       is_local=True,       # type: bool
                       visibility=None,     # type: Optional[str]
                       language=None,       # type: Optional[str]
                       auth=None,           # type: Optional[HeaderCookiesType]
                       tags=None,           # type: Optional[List[str]]
                       user=None,           # type: Optional[int]
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
    _validate_job_parameters(json_body)

    is_execute_async = json_body["mode"] != EXECUTE_MODE_SYNC   # convert auto to async
    notification_email = json_body.get("notification_email")
    encrypted_email = encrypt_email(notification_email, settings) if notification_email else None

    store = get_db(settings).get_store(StoreJobs)
    job = store.save_job(task_id=STATUS_ACCEPTED, process=process_id, service=provider_id,
                         inputs=json_body.get("inputs"), is_local=is_local, is_workflow=is_workflow,
                         access=visibility, user_id=user, execute_async=is_execute_async, custom_tags=tags,
                         notification_email=encrypted_email, accept_language=language)
    result = execute_process.delay(job_id=job.id, url=clean_ows_url(service_url), headers=auth)
    LOGGER.debug("Celery pending task [%s] for job [%s].", result.id, job.id)

    # local/provider process location
    location_base = "/providers/{provider_id}".format(provider_id=provider_id) if provider_id else ""
    location = "{base_url}{location_base}/processes/{process_id}/jobs/{job_id}".format(
        base_url=get_wps_restapi_base_url(settings),
        location_base=location_base,
        process_id=process_id,
        job_id=job.id)
    body_data = {
        "jobID": job.id,
        "status": map_status(STATUS_ACCEPTED),
        "location": location
    }
    return body_data
