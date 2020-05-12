import logging
import os
from time import sleep
from typing import TYPE_CHECKING

import colander
import requests
import six
from celery.utils.log import get_task_logger
from lxml import etree
from owslib.util import clean_ows_url
from owslib.wps import ComplexDataInput, WebProcessingService
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPCreated,
    HTTPForbidden,
    HTTPNotFound,
    HTTPNotImplemented,
    HTTPOk,
    HTTPServiceUnavailable,
    HTTPSuccessful,
    HTTPUnauthorized,
    HTTPUnprocessableEntity
)
from pyramid.request import Request
from pyramid.settings import asbool
from pyramid_celery import celery_app as app

from weaver.config import WEAVER_CONFIGURATION_EMS, get_weaver_configuration
from weaver.database import get_db
from weaver.datatype import Service
from weaver.exceptions import InvalidIdentifierValue, ProcessNotAccessible, ProcessNotFound, log_unhandled_exceptions
from weaver.execute import (
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_AUTO,
    EXECUTE_MODE_SYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes import opensearch, wps_package
from weaver.processes.constants import WPS_COMPLEX_DATA
from weaver.processes.types import PROCESS_BUILTIN, PROCESS_WORKFLOW
from weaver.processes.utils import convert_process_wps_to_db, deploy_process_from_payload, jsonify_output
from weaver.status import STATUS_ACCEPTED, STATUS_FAILED, STATUS_STARTED, STATUS_SUCCEEDED, map_status
from weaver.store.base import StoreJobs, StoreProcesses, StoreServices
from weaver.utils import get_any_id, get_any_value, get_cookie_headers, get_settings, raise_on_xml_exception, wait_secs
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_VALUES
from weaver.wps import get_wps_output_dir, get_wps_output_path, get_wps_output_url, load_pywps_cfg
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs.jobs import check_status
from weaver.wps_restapi.jobs.notify import encrypt_email, notify_job_complete
from weaver.wps_restapi.utils import OUTPUT_FORMAT_JSON, get_wps_restapi_base_url, parse_request_query

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from weaver.datatype import Process as ProcessDB    # noqa: F401
    from weaver.typedefs import JSON, SettingsType      # noqa: F401
    from typing import AnyStr, List, Tuple, Optional    # noqa: F401

LOGGER = logging.getLogger(__name__)

# job process execution progress
JOB_PROGRESS_SETUP = 1
JOB_PROGRESS_DESCRIBE = 2
JOB_PROGRESS_GET_INPUTS = 4
JOB_PROGRESS_GET_OUTPUTS = 6
JOB_PROGRESS_EXECUTE_REQUEST = 8
JOB_PROGRESS_EXECUTE_STATUS_LOCATION = 10
JOB_PROGRESS_EXECUTE_MONITOR_START = 15
JOB_PROGRESS_EXECUTE_MONITOR_LOOP = 20
JOB_PROGRESS_EXECUTE_MONITOR_ERROR = 85
JOB_PROGRESS_EXECUTE_MONITOR_END = 90
JOB_PROGRESS_NOTIFY = 95
JOB_PROGRESS_DONE = 100


@app.task(bind=True)
def execute_process(self, job_id, url, headers=None, notification_email=None):
    LOGGER.debug("Job execute process called.")
    settings = get_settings(app)
    task_logger = get_task_logger(__name__)
    load_pywps_cfg(settings)
    ssl_verify = asbool(settings.get("weaver.ssl_verify", True))
    wps_out_dir = get_wps_output_dir(settings)

    task_logger.debug("Job task setup.")
    store = get_db(app).get_store(StoreJobs)
    job = store.fetch_by_id(job_id)
    job.task_id = self.request.id
    job.progress = JOB_PROGRESS_SETUP
    job.save_log(logger=task_logger, message="Job task setup completed.")
    job = store.update_job(job)

    try:
        try:
            job.progress = JOB_PROGRESS_DESCRIBE
            job.save_log(logger=task_logger, message="Execute WPS request for process [{!s}]".format(job.process))
            wps = WebProcessingService(url=url, headers=get_cookie_headers(headers), verify=ssl_verify)
            set_wps_language(wps, accept_language=job.accept_language)
            raise_on_xml_exception(wps._capabilities)   # noqa
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
        try:
            process = wps.describeprocess(job.process)
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))

        # prepare inputs
        job.progress = JOB_PROGRESS_GET_INPUTS
        job.save_log(logger=task_logger, message="Fetching job input definitions.")
        complex_inputs = []
        for process_input in process.dataInputs:
            if WPS_COMPLEX_DATA in process_input.dataType:
                complex_inputs.append(process_input.identifier)

        try:
            wps_inputs = list()
            for process_input in job.inputs:
                input_id = get_any_id(process_input)
                process_value = get_any_value(process_input)
                # in case of array inputs, must repeat (id,value)
                input_values = process_value if isinstance(process_value, list) else [process_value]

                # we need to support file:// scheme but PyWPS doesn't like them so remove the scheme file://
                input_values = [val[7:] if str(val).startswith("file://") else val for val in input_values]

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
        outputs = [(o.identifier, o.dataType == WPS_COMPLEX_DATA) for o in process.processOutputs]

        mode = EXECUTE_MODE_ASYNC if job.execute_async else EXECUTE_MODE_SYNC
        job.progress = JOB_PROGRESS_EXECUTE_REQUEST
        job.save_log(logger=task_logger, message="Starting job process execution")
        execution = wps.execute(job.process, inputs=wps_inputs, output=outputs, mode=mode, lineage=True)
        if not execution.process and execution.errors:
            raise execution.errors[0]

        # adjust status location
        wps_status_path = execution.statusLocation
        job.progress = JOB_PROGRESS_EXECUTE_STATUS_LOCATION
        job.save_log(logger=task_logger, message="Verifying job status location.")
        if not execution.statusLocation.startswith("http") and not os.path.isfile(execution.statusLocation):
            wps_status_path = "file://{}".format(os.path.join(wps_out_dir, execution.statusLocation))
            if os.path.isfile(wps_status_path):
                execution.statusLocation = wps_status_path
                job.save_log(logger=task_logger, level=logging.INFO,
                             message="WPS status location has been corrected using internal server location.")
            else:
                job.save_log(logger=task_logger, level=logging.WARNING,
                             message="WPS status location could not be found")
        LOGGER.debug("WPS status location that will be queried: [%s]", wps_status_path)

        job.status = map_status(STATUS_STARTED)
        job.status_message = execution.statusMessage or "{} initiation done.".format(str(job))
        job.status_location = wps_status_path
        job.request = execution.request
        job.response = etree.tostring(execution.response)
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
                job.progress = JOB_PROGRESS_EXECUTE_MONITOR_LOOP
                execution = check_status(url=wps_status_path, verify=ssl_verify, sleep_secs=wait_secs(run_step))
                job_msg = (execution.statusMessage or "").strip()
                job.response = etree.tostring(execution.response)
                job.status = map_status(execution.getStatus())
                job.status_message = "Job execution monitoring (progress: {}%, status: {})."\
                                     .format(execution.percentCompleted, job_msg or "n/a")
                # job.save_log(logger=task_logger)
                # job = store.update_job(job)

                if execution.isComplete():
                    job.mark_finished()
                    job.progress = JOB_PROGRESS_EXECUTE_MONITOR_END
                    msg_progress = " (status: {})".format(job_msg) if job_msg else ""
                    if execution.isSucceded():
                        job.status = map_status(STATUS_SUCCEEDED)
                        job.status_message = "Job succeeded{}.".format(msg_progress)
                        wps_package.retrieve_package_job_log(execution, job)
                        job.save_log(logger=task_logger)
                        job_results = [jsonify_output(output, process, settings)
                                       for output in execution.processOutputs]
                        job.results = make_results_relative(job_results, settings)
                    else:
                        task_logger.debug("Job failed.")
                        job.status_message = "Job failed{}.".format(msg_progress)
                        wps_package.retrieve_package_job_log(execution, job)
                        job.save_log(errors=execution.errors, logger=task_logger)

            except Exception as exc:
                num_retries += 1
                task_logger.debug("Exception raised: %s", repr(exc))
                job.status_message = "Could not read status xml document for {!s}. Trying again...".format(job)
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
        if notification_email is not None:
            job.progress = JOB_PROGRESS_NOTIFY
            try:
                notify_job_complete(job, notification_email, settings)
                message = "Notification email sent successfully."
                job.save_log(logger=task_logger, message=message)
            except Exception as exc:
                exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
                exception = "{0}: {1!s}".format(exception_class, exc)
                message = "Couldn't send notification email ({})".format(exception)
                job.save_log(errors=message, logger=task_logger, message=message)

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
        if isinstance(ref, six.string_types) and ref:
            if ref.startswith(wps_url):
                ref = ref.replace(wps_url, "", 1)
            if ref.startswith(wps_path):
                ref = ref.replace(wps_path, "", 1)
            res["reference"] = ref
    return results


def set_wps_language(wps, accept_language=None, request=None):
    # type: (WebProcessingService, Optional[str], Optional[Request]) -> None
    """Set the :attr:`language` property on the :class:`WebProcessingService` object.

    Given the `Accept-Language` header value, match the best language
    to the supported languages.

    By default, and if no match is found, the :attr:`WebProcessingService.language`
    property is set to None.

    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
    (q-factor weighting is ignored, only order is considered)

    :param wps: process for which to set the language header if it is accepted
    :param str accept_language: the value of the Accept-Language header
    :param request: request from which to extract Accept-Language header if not provided directly
    """
    if not accept_language and request:
        accept_language = request.accept_language.header_value

    if not accept_language:
        return

    if not hasattr(wps, "languages"):
        # owslib version doesn't support setting a language
        return

    accepted_languages = [lang.strip().split(";")[0] for lang in accept_language.lower().split(",")]

    for accept in accepted_languages:
        for language in wps.languages.supported:    # noqa
            # Accept-Language header could be only 'fr' instead of 'fr-CA'
            if language.lower().startswith(accept):
                wps.language = language
                return


def validate_supported_submit_job_handler_parameters(json_body):
    """
    Tests supported parameters not automatically validated by colander deserialize.
    """
    if json_body["mode"] not in [EXECUTE_MODE_ASYNC, EXECUTE_MODE_AUTO]:
        raise HTTPNotImplemented(detail="Execution mode '{}' not supported.".format(json_body["mode"]))

    if json_body["response"] != EXECUTE_RESPONSE_DOCUMENT:
        raise HTTPNotImplemented(detail="Execution response type '{}' not supported.".format(json_body["response"]))

    for job_output in json_body["outputs"]:
        if job_output["transmissionMode"] != EXECUTE_TRANSMISSION_MODE_REFERENCE:
            raise HTTPNotImplemented(detail="Execute transmissionMode '{}' not supported."
                                     .format(job_output["transmissionMode"]))


def submit_job_handler(request, service_url, is_workflow=False, visibility=None):
    # type: (Request, AnyStr, bool, Optional[AnyStr]) -> HTTPSuccessful

    # validate body with expected JSON content and schema
    if CONTENT_TYPE_APP_JSON not in request.content_type:
        raise HTTPBadRequest("Request 'Content-Type' header other than '{}' not supported."
                             .format(CONTENT_TYPE_APP_JSON))
    try:
        json_body = request.json_body
    except Exception as ex:
        raise HTTPBadRequest("Invalid JSON body cannot be decoded for job submission. [{}]".format(ex))
    try:
        json_body = sd.Execute().deserialize(json_body)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))

    # TODO: remove when all parameter variations are supported
    validate_supported_submit_job_handler_parameters(json_body)

    settings = get_settings(request)
    provider_id = request.matchdict.get("provider_id")          # None OK if local
    process_id = request.matchdict.get("process_id")
    tags = request.params.get("tags", "").split(",")
    is_execute_async = json_body["mode"] != EXECUTE_MODE_SYNC   # convert auto to async
    notification_email = json_body.get("notification_email")
    encrypted_email = encrypt_email(notification_email, settings) if notification_email else None

    store = get_db(request).get_store(StoreJobs)
    job = store.save_job(task_id=STATUS_ACCEPTED, process=process_id, service=provider_id,
                         inputs=json_body.get("inputs"), is_workflow=is_workflow, access=visibility,
                         user_id=request.authenticated_userid, execute_async=is_execute_async, custom_tags=tags,
                         notification_email=encrypted_email, accept_language=request.accept_language.header_value)
    result = execute_process.delay(
        job_id=job.id,
        url=clean_ows_url(service_url),
        # Convert EnvironHeaders to a simple dict (should cherrypick the required headers)
        headers={k: v for k, v in request.headers.items()},
        notification_email=notification_email)
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
    return HTTPCreated(location=location, json=body_data)


@sd.jobs_full_service.post(tags=[sd.TAG_PROVIDER_PROCESS, sd.TAG_PROVIDERS, sd.TAG_EXECUTE, sd.TAG_JOBS],
                           renderer=OUTPUT_FORMAT_JSON, schema=sd.PostProviderProcessJobRequest(),
                           response_schemas=sd.post_provider_process_job_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorPostProviderProcessJobResponse.description)
def submit_provider_job(request):
    """
    Execute a provider process.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get("provider_id")
    service = store.fetch_by_name(provider_id, request=request)
    return submit_job_handler(request, service.url)


def list_remote_processes(service, request):
    # type: (Service, Request) -> List[ProcessDB]
    """
    Obtains a list of remote service processes in a compatible :class:`weaver.datatype.Process` format.

    Note: remote processes won't be stored to the local process storage.
    """
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    set_wps_language(wps, request=request)
    settings = get_settings(request)
    return [convert_process_wps_to_db(service, process, settings) for process in wps.processes]


@sd.provider_processes_service.get(tags=[sd.TAG_PROVIDER_PROCESS, sd.TAG_PROVIDERS, sd.TAG_GETCAPABILITIES],
                                   renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderEndpoint(),
                                   response_schemas=sd.get_provider_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProviderProcessesListResponse.description)
def get_provider_processes(request):
    """
    Retrieve available provider processes (GetCapabilities).
    """
    provider_id = request.matchdict.get("provider_id")
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id, request=request)
    processes = list_remote_processes(service, request=request)
    return HTTPOk(json=[p.json() for p in processes])


def describe_provider_process(request):
    # type: (Request) -> ProcessDB
    """
    Obtains a remote service process description in a compatible local process format.

    Note: this processes won't be stored to the local process storage.
    """
    provider_id = request.matchdict.get("provider_id")
    process_id = request.matchdict.get("process_id")
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    set_wps_language(wps, request=request)
    process = wps.describeprocess(process_id)
    return convert_process_wps_to_db(service, process, get_settings(request))


@sd.provider_process_service.get(tags=[sd.TAG_PROVIDER_PROCESS, sd.TAG_PROVIDERS, sd.TAG_DESCRIBEPROCESS],
                                 renderer=OUTPUT_FORMAT_JSON, schema=sd.ProviderProcessEndpoint(),
                                 response_schemas=sd.get_provider_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProviderProcessResponse.description)
def get_provider_process(request):
    """
    Retrieve a process description (DescribeProcess).
    """
    try:
        process = describe_provider_process(request)
        process_offering = process.process_offering()
        return HTTPOk(json=process_offering)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


def get_processes_filtered_by_valid_schemas(request):
    # type: (Request) -> Tuple[List[JSON], List[AnyStr]]
    """
    Validates the processes summary schemas and returns them into valid/invalid lists.
    :returns: list of valid process summaries and invalid processes IDs for manual cleanup.
    """
    store = get_db(request).get_store(StoreProcesses)
    processes = store.list_processes(visibility=VISIBILITY_PUBLIC, request=request)
    valid_processes = list()
    invalid_processes_ids = list()
    for process in processes:
        try:
            valid_processes.append(process.process_summary())
        except colander.Invalid:
            invalid_processes_ids.append(process.identifier)
    return valid_processes, invalid_processes_ids


@sd.processes_service.get(schema=sd.GetProcessesEndpoint(), tags=[sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
                          response_schemas=sd.get_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProcessesListResponse.description)
def get_processes(request):
    """
    List registered processes (GetCapabilities). Optionally list both local and provider processes.
    """
    detail = asbool(request.params.get("detail", True))
    try:
        # get local processes and filter according to schema validity
        # (previously deployed process schemas can become invalid because of modified schema definitions
        processes, invalid_processes = get_processes_filtered_by_valid_schemas(request)
        if invalid_processes:
            raise HTTPServiceUnavailable(
                "Previously deployed processes are causing invalid schema integrity errors. "
                "Manual cleanup of following processes is required: {}".format(invalid_processes))
        response_body = {"processes": processes if detail else [get_any_id(p) for p in processes]}

        # if 'EMS' and '?providers=True', also fetch each provider's processes
        if get_weaver_configuration(get_settings(request)) == WEAVER_CONFIGURATION_EMS:
            queries = parse_request_query(request)
            if "providers" in queries and asbool(queries["providers"][0]) is True:
                providers_response = requests.request("GET", "{host}/providers".format(host=request.host_url),
                                                      headers=request.headers, cookies=request.cookies)
                providers = providers_response.json()
                response_body.update({"providers": providers})
                for i, provider in enumerate(providers):
                    provider_id = get_any_id(provider)
                    response = requests.request("GET", "{host}/providers/{provider_id}/processes"
                                                .format(host=request.host_url, provider_id=provider_id),
                                                headers=request.headers, cookies=request.cookies)
                    processes = response.json().get("processes", [])
                    response_body["providers"][i].update({
                        "processes": processes if detail else [get_any_id(p) for p in processes]
                    })
        return HTTPOk(json=response_body)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@sd.processes_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.PostProcessesEndpoint(), response_schemas=sd.post_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorPostProcessesResponse.description)
def add_local_process(request):
    """
    Register a local process.
    """
    return deploy_process_from_payload(request.json, request)


def get_process(request):
    # type: (Request) -> ProcessDB
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, six.string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id, visibility=VISIBILITY_PUBLIC, request=request)
        return process
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("Process with id '{!s}' is not accessible.".format(process_id))
    except ProcessNotFound:
        raise HTTPNotFound("Process with id '{!s}' does not exist.".format(process_id))
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema:\n[{0!r}].".format(ex))


@sd.process_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OUTPUT_FORMAT_JSON,
                        schema=sd.ProcessEndpoint(), response_schemas=sd.get_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProcessResponse.description)
def get_local_process(request):
    """
    Get a registered local process information (DescribeProcess).
    """
    try:
        process = get_process(request)
        process["inputs"] = opensearch.replace_inputs_describe_process(process.inputs, process.payload)
        process_offering = process.process_offering()
        return HTTPOk(json=process_offering)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{!s}]".format(ex))


@sd.process_package_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessPackageEndpoint(), response_schemas=sd.get_process_package_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProcessPackageResponse.description)
def get_local_process_package(request):
    """
    Get a registered local process package definition.
    """
    process = get_process(request)
    return HTTPOk(json=process.package or {})


@sd.process_payload_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OUTPUT_FORMAT_JSON,
                                schema=sd.ProcessPayloadEndpoint(), response_schemas=sd.get_process_payload_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProcessPayloadResponse.description)
def get_local_process_payload(request):
    """
    Get a registered local process payload definition.
    """
    process = get_process(request)
    return HTTPOk(json=process.payload or {})


@sd.process_visibility_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.ProcessVisibilityGetEndpoint(),
                                   response_schemas=sd.get_process_visibility_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorGetProcessVisibilityResponse.description)
def get_process_visibility(request):
    """
    Get the visibility of a registered local process.
    """
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, six.string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        visibility_value = store.get_visibility(process_id, request=request)
        return HTTPOk(json={u"value": visibility_value})
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))


@sd.process_visibility_service.put(tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY], renderer=OUTPUT_FORMAT_JSON,
                                   schema=sd.ProcessVisibilityPutEndpoint(),
                                   response_schemas=sd.put_process_visibility_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorPutProcessVisibilityResponse.description)
def set_process_visibility(request):
    """
    Set the visibility of a registered local process.
    """
    visibility_value = request.json.get("value")
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, six.string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    if not isinstance(visibility_value, six.string_types):
        raise HTTPUnprocessableEntity("Invalid visibility value specified.")
    if visibility_value not in VISIBILITY_VALUES:
        raise HTTPBadRequest("Invalid visibility value specified.")

    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id)
        if process.type == PROCESS_BUILTIN:
            raise HTTPForbidden("Cannot change the visibility of builtin process.")
        store.set_visibility(process_id, visibility_value, request=request)
        return HTTPOk(json={u"value": visibility_value})
    except TypeError:
        raise HTTPBadRequest("Value of visibility must be a string.")
    except ValueError:
        raise HTTPUnprocessableEntity("Value of visibility must be one of : {!s}".format(list(VISIBILITY_VALUES)))
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))


@sd.process_service.delete(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OUTPUT_FORMAT_JSON,
                           schema=sd.ProcessEndpoint(), response_schemas=sd.delete_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorDeleteProcessResponse.description)
def delete_local_process(request):
    """
    Unregister a local process.
    """
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, six.string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id)
        if process.type == PROCESS_BUILTIN:
            raise HTTPForbidden("Cannot delete a builtin process.")
        if store.delete_process(process_id, visibility=VISIBILITY_PUBLIC, request=request):
            return HTTPOk(json={"undeploymentDone": True, "identifier": process_id})
        LOGGER.error("Existing process [%s] should have been deleted with success status.", process_id)
        raise HTTPForbidden("Deletion of process has been refused by the database or could not have been validated.")
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("Process with id '{!s}' is not accessible.".format(process_id))
    except ProcessNotFound:
        description = "Process with id '{!s}' does not exist.".format(process_id)
        raise HTTPNotFound(description)


@sd.process_jobs_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS], renderer=OUTPUT_FORMAT_JSON,
                              schema=sd.PostProcessJobsEndpoint(), response_schemas=sd.post_process_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorPostProcessJobResponse.description)
def submit_local_job(request):
    """
    Execute a local process.
    """
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, six.string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id, visibility=VISIBILITY_PUBLIC, request=request)
        resp = submit_job_handler(request, process.processEndpointWPS1,
                                  is_workflow=process.type == PROCESS_WORKFLOW,
                                  visibility=process.visibility)
        return resp
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("Process with id '{!s}' is not accessible.".format(process_id))
    except ProcessNotFound:
        raise HTTPNotFound("The process with id '{!s}' does not exist.".format(process_id))
