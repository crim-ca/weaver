from weaver.config import get_weaver_configuration, WEAVER_CONFIGURATION_EMS
from weaver.database import get_db
from weaver.datatype import Process as ProcessDB, Service
from weaver.exceptions import (
    InvalidIdentifierValue,
    ProcessRegistrationError,
    ProcessNotFound,
    ProcessNotAccessible,
    PackageRegistrationError,
    PackageTypeError,
    PackageNotFound,
)
from weaver.execute import (
    EXECUTE_MODE_AUTO,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_SYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
)
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes import wps_package, opensearch
from weaver.processes.utils import jsonify_value, jsonify_output
from weaver.processes.types import PROCESS_WORKFLOW
from weaver.status import (
    map_status,
    STATUS_ACCEPTED,
    STATUS_STARTED,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
)
from weaver.store.base import StoreServices, StoreProcesses, StoreJobs
from weaver.utils import get_any_id, get_any_value, get_settings, raise_on_xml_exception, get_sane_name, wait_secs
from weaver.visibility import VISIBILITY_PUBLIC, visibility_values
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs.notify import notify_job
from weaver.wps_restapi.utils import get_cookie_headers, wps_restapi_base_url, parse_request_query
from weaver.wps_restapi.jobs.jobs import check_status, job_format_json
from weaver.wps import get_wps_output_path, load_pywps_cfg
from owslib.wps import WebProcessingService, WPSException, ComplexDataInput, Process as ProcessWPS
from owslib.util import clean_ows_url
from pyramid.httpexceptions import (
    HTTPOk,
    HTTPCreated,
    HTTPUnauthorized,
    HTTPNotFound,
    HTTPBadRequest,
    HTTPConflict,
    HTTPUnprocessableEntity,
    HTTPInternalServerError,
    HTTPNotImplemented,
    HTTPServiceUnavailable,
    HTTPSuccessful,
    HTTPException,
)
from time import sleep
from typing import Any, AnyStr, Dict, List, Tuple, Optional, Union, TYPE_CHECKING
from celery.utils.log import get_task_logger
from pyramid.settings import asbool
from pyramid_celery import celery_app as app
from pyramid.request import Request
from lxml import etree
from six import string_types
from copy import deepcopy
import requests
import colander
import logging
import os
if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


def retrieve_package_job_log(execution, job):
    # If the process is a weaver package this status xml should be available in the process output dir
    status_xml_fn = execution.statusLocation.split('/')[-1]
    try:
        registry = app.conf['PYRAMID_REGISTRY']
        output_path = get_wps_output_path(registry.settings)

        # weaver package log every status update into this file (we no longer rely on the http monitoring)
        log_fn = os.path.join(output_path, '{0}.log'.format(status_xml_fn))
        with open(log_fn, 'r') as log_file:
            # Keep the first log entry which is the real start time and replace the following ones with the file content
            job.logs = job.logs[:1]
            for line in log_file:
                job.logs.append(line.rstrip('\n'))
        os.remove(log_fn)
    except (KeyError, IOError):
        pass


@app.task(bind=True)
def execute_process(self, job_id, url, headers=None, notification_email=None):
    registry = app.conf['PYRAMID_REGISTRY']
    task_logger = get_task_logger(__name__)
    load_pywps_cfg(registry)

    ssl_verify = asbool(registry.settings.get('weaver.ssl_verify', True))
    store = get_db(registry).get_store(StoreJobs)
    job = store.fetch_by_id(job_id)
    job.task_id = self.request.id
    job = store.update_job(job)

    try:
        try:
            wps = WebProcessingService(url=url, headers=get_cookie_headers(headers), verify=ssl_verify)
            # noinspection PyProtectedMember
            raise_on_xml_exception(wps._capabilities)
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS capabilities. Error: [{}].".format(str(ex)))
        try:
            process = wps.describeprocess(job.process)
        except Exception as ex:
            raise OWSNoApplicableCode("Failed to retrieve WPS process description. Error: [{}].".format(str(ex)))

        # prepare inputs
        complex_inputs = []
        for process_input in process.dataInputs:
            if 'ComplexData' in process_input.dataType:
                complex_inputs.append(process_input.identifier)

        try:
            wps_inputs = list()
            for process_input in job.inputs:
                input_id = get_any_id(process_input)
                process_value = get_any_value(process_input)
                # in case of array inputs, must repeat (id,value)
                input_values = process_value if isinstance(process_value, list) else [process_value]

                # we need to support file:// scheme but PyWPS doesn't like them so remove the scheme file://
                input_values = [val[7:] if val.startswith('file://') else val for val in input_values]

                # need to use ComplexDataInput structure for complex input
                wps_inputs.extend([(input_id,
                                    ComplexDataInput(input_value) if input_id in complex_inputs else input_value)
                                   for input_value in input_values])
        except KeyError:
            wps_inputs = []

        # prepare outputs
        outputs = [(o.identifier, o.dataType == 'ComplexData') for o in process.processOutputs]

        mode = EXECUTE_MODE_ASYNC if job.execute_async else EXECUTE_MODE_SYNC
        execution = wps.execute(job.process, inputs=wps_inputs, output=outputs, mode=mode, lineage=True)
        if not execution.process and execution.errors:
            raise execution.errors[0]

        job.status = map_status(STATUS_STARTED)
        job.status_message = execution.statusMessage or "{} initiation done.".format(str(job))
        job.status_location = execution.statusLocation
        job.request = execution.request
        job.response = etree.tostring(execution.response)
        job.save_log(logger=task_logger)
        job = store.update_job(job)

        max_retries = 5
        num_retries = 0
        run_step = 0
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= max_retries:
                raise Exception("Could not read status document after {} retries. Giving up.".format(max_retries))
            try:
                execution = check_status(url=execution.statusLocation, verify=ssl_verify,
                                         sleep_secs=wait_secs(run_step))

                job.response = etree.tostring(execution.response)
                job.status = map_status(execution.getStatus())
                job.status_message = execution.statusMessage
                job.progress = execution.percentCompleted
                job.save_log(logger=task_logger)

                if execution.isComplete():
                    job.mark_finished()
                    if execution.isSucceded():
                        job.progress = 100
                        job.status = map_status(STATUS_SUCCEEDED)
                        job.status_message = execution.statusMessage or "Job succeeded."
                        retrieve_package_job_log(execution, job)
                        job.save_log(logger=task_logger)
                        job.results = [jsonify_output(output, process) for output in execution.processOutputs]
                    else:
                        task_logger.debug("Job failed.")
                        job.status_message = execution.statusMessage or "Job failed."
                        retrieve_package_job_log(execution, job)
                        job.save_log(errors=execution.errors, logger=task_logger)

            except Exception as exc:
                num_retries += 1
                task_logger.debug('Exception raised: {}'.format(repr(exc)))
                job.status_message = "Could not read status xml document for {}. Trying again ...".format(str(job))
                job.save_log(errors=execution.errors, logger=task_logger)
                sleep(1)
            else:
                # job.status_message = "Update {} ...".format(str(job))
                # job.save_log(logger=task_logger)
                num_retries = 0
                run_step += 1
            finally:
                job = store.update_job(job)

    except (WPSException, Exception) as exc:
        job.status = map_status(STATUS_FAILED)
        job.status_message = "Failed to run {}.".format(str(job))
        if isinstance(exc, WPSException):
            errors = "[{0}] {1}".format(exc.locator, exc.text)
        else:
            exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
            errors = "{0}: {1}".format(exception_class, exc.message)
        job.save_log(errors=errors, logger=task_logger)
    finally:
        job.status_message = "Job {}.".format(job.status)
        job.save_log(logger=task_logger)

        # Send email if requested
        if notification_email is not None:
            try:
                job_json = job_format_json(registry.settings, job)
                notify_job(job, job_json, notification_email, registry.settings)
                message = "Sent email to: {}".format(notification_email)
                job.save_log(logger=task_logger, message=message)
            except Exception as exc:
                exception_class = "{}.{}".format(type(exc).__module__, type(exc).__name__)
                exception = "{0}: {1}".format(exception_class, exc.message)
                message = "Couldn't send email to: {} ({})".format(notification_email, exception)
                job.save_log(errors=message, logger=task_logger, message=message)

        job = store.update_job(job)

    return job.status


def validate_supported_submit_job_handler_parameters(json_body):
    """
    Tests supported parameters not automatically validated by colander deserialize.
    """
    if json_body['mode'] not in [EXECUTE_MODE_ASYNC, EXECUTE_MODE_AUTO]:
        raise HTTPNotImplemented(detail="Execution mode `{0}` not supported.".format(json_body['mode']))

    if json_body['response'] != EXECUTE_RESPONSE_DOCUMENT:
        raise HTTPNotImplemented(detail="Execution response type `{0}` not supported.".format(json_body['response']))

    for job_output in json_body['outputs']:
        if job_output['transmissionMode'] != EXECUTE_TRANSMISSION_MODE_REFERENCE:
            raise HTTPNotImplemented(detail="Execute transmissionMode `{0}` not supported."
                                     .format(job_output['transmissionMode']))


def submit_job_handler(request, service_url, is_workflow=False, visibility=None):
    # type: (Request, AnyStr, bool, Optional[AnyStr]) -> HTTPSuccessful

    # validate body with expected JSON content and schema
    if 'application/json' not in request.content_type:
        raise HTTPBadRequest("Request 'Content-Type' header other than 'application/json' not supported.")
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

    provider_id = request.matchdict.get('provider_id')          # None OK if local
    process_id = request.matchdict.get('process_id')
    tags = request.params.get('tags', '').split(',')
    is_execute_async = json_body['mode'] != EXECUTE_MODE_SYNC   # convert auto to async

    notification_email = json_body.get('notification_email')

    store = get_db(request).get_store(StoreJobs)
    job = store.save_job(task_id=STATUS_ACCEPTED, process=process_id, service=provider_id,
                         inputs=json_body.get('inputs'), is_workflow=is_workflow, access=visibility,
                         user_id=request.authenticated_userid, execute_async=is_execute_async, custom_tags=tags)
    result = execute_process.delay(
        job_id=job.id,
        url=clean_ows_url(service_url),
        # Convert EnvironHeaders to a simple dict (should cherrypick the required headers)
        headers={k: v for k, v in request.headers.items()},
        notification_email=notification_email)
    LOGGER.debug("Celery pending task `{}` for job `{}`.".format(result.id, job.id))

    # local/provider process location
    location_base = '/providers/{provider_id}'.format(provider_id=provider_id) if provider_id else ''
    location = '{base_url}{location_base}/processes/{process_id}/jobs/{job_id}'.format(
        base_url=wps_restapi_base_url(get_settings(request)),
        location_base=location_base,
        process_id=process_id,
        job_id=job.id)
    body_data = {
        'jobID': job.id,
        'status': map_status(STATUS_ACCEPTED),
        'location': location
    }
    return HTTPCreated(location=location, json=body_data)


@sd.jobs_full_service.post(tags=[sd.provider_processes_tag, sd.providers_tag, sd.execute_tag, sd.jobs_tag],
                           renderer='json', schema=sd.PostProviderProcessJobRequest(),
                           response_schemas=sd.post_provider_process_job_responses)
def submit_provider_job(request):
    """
    Execute a provider process.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get('provider_id')
    service = store.fetch_by_name(provider_id, request=request)
    return submit_job_handler(request, service.url)


def convert_process_wps_to_db(service, process, settings):
    # type: (Service, ProcessWPS, Dict[AnyStr, Union[int, float, bool, None]]) -> ProcessDB
    """
    Converts an owslib WPS Process to local storage Process.
    """
    describe_process_url = '{base_url}/providers/{provider_id}/processes/{process_id}'.format(
        base_url=wps_restapi_base_url(settings),
        provider_id=service.name,
        process_id=process.identifier)
    execute_process_url = '{describe_url}/jobs'.format(describe_url=describe_process_url)

    default_format = {'mimeType': 'text/plain'}
    inputs = [dict(
        id=getattr(dataInput, 'identifier', ''),
        title=getattr(dataInput, 'title', ''),
        abstract=getattr(dataInput, 'abstract', ''),
        minOccurs=str(getattr(dataInput, 'minOccurs', 0)),  # FIXME: str applied to match OGC REST-API definition
        maxOccurs=str(getattr(dataInput, 'maxOccurs', 0)),  # FIXME: str applied to match OGC REST-API definition
        dataType=dataInput.dataType,
        defaultValue=jsonify_value(getattr(dataInput, 'defaultValue', None)),
        allowedValues=[jsonify_value(dataValue) for dataValue in getattr(dataInput, 'allowedValues', [])],
        supportedValues=[jsonify_value(dataValue) for dataValue in getattr(dataInput, 'supportedValues', [])],
        formats=[jsonify_value(dataValue) for dataValue in getattr(dataInput, 'supportedValues', [default_format])],
    ) for dataInput in getattr(process, 'dataInputs', [])]

    outputs = [dict(
        id=getattr(processOutput, 'identifier', ''),
        title=getattr(processOutput, 'title', ''),
        abstract=getattr(processOutput, 'abstract', ''),
        dataType=processOutput.dataType,
        defaultValue=jsonify_value(getattr(processOutput, 'defaultValue', None)),
        formats=[jsonify_value(dataValue) for dataValue in getattr(processOutput, 'supportedValues', [default_format])],
    ) for processOutput in getattr(process, 'processOutputs', [])]

    return ProcessDB(
        id=process.identifier,
        label=getattr(process, 'title', ''),
        title=getattr(process, 'title', ''),
        abstract=getattr(process, 'abstract', ''),
        inputs=inputs,
        outputs=outputs,
        url=describe_process_url,
        processEndpointWPS1=service.url,
        processDescriptionURL=describe_process_url,
        executeEndpoint=execute_process_url,
        package=None,
    )


def list_remote_processes(service, request):
    # type: (Service, Request) -> List[ProcessDB]
    """
    Obtains a list of remote service processes in a compatible :class:`weaver.datatype.Process` format.
    Note: those processes won't be stored to the local process storage.
    """
    if not isinstance(service, Service):
        return list()
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    return [convert_process_wps_to_db(service, process, get_settings(request)) for process in wps.processes]


@sd.provider_processes_service.get(tags=[sd.provider_processes_tag, sd.providers_tag, sd.getcapabilities_tag],
                                   renderer='json', schema=sd.ProviderEndpoint(),
                                   response_schemas=sd.get_provider_processes_responses)
def get_provider_processes(request):
    """
    Retrieve available provider processes (GetCapabilities).
    """
    provider_id = request.matchdict.get('provider_id')
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id, request=request)
    processes = list_remote_processes(service, request=request)
    return HTTPOk(json=[p.json() for p in processes])


def get_provider_process(request):
    # type: (Request) -> ProcessDB
    """
    Obtains a remote service process description in a compatible local process format.
    Note: this processes won't be stored to the local process storage.
    """
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    store = get_db(request).get_store(StoreServices)
    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    process = wps.describeprocess(process_id)
    return convert_process_wps_to_db(service, process, get_settings(request))


@sd.provider_process_service.get(tags=[sd.provider_processes_tag, sd.providers_tag, sd.describeprocess_tag],
                                 renderer='json', schema=sd.ProviderProcessEndpoint(),
                                 response_schemas=sd.get_provider_process_description_responses)
def describe_provider_process(request):
    """
    Retrieve a process description (DescribeProcess).
    """
    try:
        process = get_provider_process(request)
        process_offering = process.process_offering()
        return HTTPOk(json=process_offering)
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))


def get_processes_filtered_by_valid_schemas(request):
    # type: (Request) -> Tuple[List[Dict[AnyStr, Any]], List[AnyStr]]
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
            pass
    return valid_processes, invalid_processes_ids


@sd.processes_service.get(schema=sd.GetProcessesRequest(), tags=[sd.processes_tag, sd.getcapabilities_tag],
                          response_schemas=sd.get_processes_responses)
def get_processes(request):
    """
    List registered processes (GetCapabilities). Optionally list both local and provider processes.
    """
    try:
        # get local processes and filter according to schema validity
        # (previously deployed process schemas can become invalid because of modified schema definitions
        processes, invalid_processes = get_processes_filtered_by_valid_schemas(request)
        if invalid_processes:
            raise HTTPServiceUnavailable(
                "Previously deployed processes are causing invalid schema integrity errors. "
                "Manual cleanup of following processes is required: {}".format(invalid_processes))
        response_body = {'processes': processes}

        # if EMS and ?providers=True, also fetch each provider's processes
        if get_weaver_configuration(get_settings(request)) == WEAVER_CONFIGURATION_EMS:
            queries = parse_request_query(request)
            if 'providers' in queries and asbool(queries['providers'][0]) is True:
                providers_response = requests.request('GET', '{host}/providers'.format(host=request.host_url),
                                                      headers=request.headers, cookies=request.cookies)
                providers = providers_response.json()
                response_body.update({'providers': providers})
                for i, provider in enumerate(providers):
                    provider_id = get_any_id(provider)
                    processes = requests.request('GET', '{host}/providers/{provider_id}/processes'
                                                 .format(host=request.host_url, provider_id=provider_id),
                                                 headers=request.headers, cookies=request.cookies)
                    response_body['providers'][i].update({'processes': processes})
        return HTTPOk(json=response_body)
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))
    except Exception as ex:
        LOGGER.exception(str(ex), exc_info=True)
        raise HTTPInternalServerError(str(ex))


@sd.processes_service.post(tags=[sd.processes_tag, sd.deploy_tag], renderer='json',
                           schema=sd.PostProcessEndpoint(), response_schemas=sd.post_processes_responses)
def add_local_process(request):
    """
    Register a local process.
    """
    # use deepcopy of body payload to avoid circular dependencies when writing to mongodb
    # and before parsing it because the body is altered by some pop operations
    body = request.json
    payload = deepcopy(body)

    # validate minimum field requirements
    try:
        sd.Deploy().deserialize(body)
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))
    except Exception as ex:
        raise HTTPInternalServerError("Unhandled error when parsing 'processDescription': [{}]".format(str(ex)))

    # validate identifier naming for unsupported characters
    process_description = body.get('processDescription')
    process_info = process_description.get('process')
    try:
        process_info['identifier'] = get_sane_name(get_any_id(process_info))
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))

    # retrieve CWL package definition, either via owsContext or executionUnit package/reference
    deployment_profile_name = body.get('deploymentProfileName', '').lower()
    ows_context = process_info.pop('owsContext', None)
    reference = None
    package = None
    if isinstance(ows_context, dict):
        offering = ows_context.get('offering')
        if not isinstance(offering, dict):
            raise HTTPUnprocessableEntity("Invalid parameter 'processDescription.process.owsContext.offering'.")
        content = offering.get('content')
        if not isinstance(content, dict):
            raise HTTPUnprocessableEntity("Invalid parameter 'processDescription.process.owsContext.offering.content'.")
        package = None
        reference = content.get('href')
    elif deployment_profile_name.endswith('workflow') or deployment_profile_name.endswith('application'):
        execution_units = body.get('executionUnit')
        if not isinstance(execution_units, list):
            raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")
        for execution_unit in execution_units:
            if not isinstance(execution_unit, dict):
                raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")
            package = execution_unit.get('unit')
            reference = execution_unit.get('href')
            # stop on first package/reference found, simultaneous usage will raise during package retrieval
            if package or reference:
                break
    else:
        raise HTTPBadRequest("Missing one of required parameters [owsContext, deploymentProfileName].")

    # obtain updated process information using WPS process offering and CWL package definition
    try:
        # data_source `None` forces workflow process to search locally for deployed step applications
        process_info = wps_package.get_process_from_wps_request(process_info, reference, package, data_source=None)
    except PackageNotFound as ex:
        # raised when a workflow sub-process is not found (not deployed locally)
        raise HTTPNotFound(detail=str(ex))
    except (PackageRegistrationError, PackageTypeError) as ex:
        raise HTTPUnprocessableEntity(detail=str(ex))
    except Exception as ex:
        raise HTTPBadRequest("Invalid package/reference definition. Loading generated error: `{}`".format(repr(ex)))

    # validate process type against weaver configuration
    settings = get_settings(request)
    process_type = process_info['type']
    if process_type == PROCESS_WORKFLOW:
        weaver_config = get_weaver_configuration(settings)
        if weaver_config != WEAVER_CONFIGURATION_EMS:
            raise HTTPBadRequest("Invalid `{0}` package deployment on `{1}`.".format(process_type, weaver_config))

    restapi_url = wps_restapi_base_url(settings)
    description_url = "/".join([restapi_url, 'processes', process_info['identifier']])
    execute_endpoint = "/".join([description_url, "jobs"])

    # ensure that required 'processEndpointWPS1' in db is added,
    # will be auto-fixed to localhost if not specified in body
    process_info['processEndpointWPS1'] = process_description.get('processEndpointWPS1')
    process_info['executeEndpoint'] = execute_endpoint
    process_info['payload'] = payload
    process_info['jobControlOptions'] = process_description.get('jobControlOptions', [])
    process_info['outputTransmission'] = process_description.get('outputTransmission', [])
    if ows_context:
        process_info['owsContext'] = ows_context
    process_info['processDescriptionURL'] = description_url

    try:
        store = get_db(request).get_store(StoreProcesses)
        saved_process = store.save_process(ProcessDB(process_info), overwrite=False, request=request)
    except ProcessRegistrationError as ex:
        raise HTTPConflict(detail=str(ex))
    except ValueError as ex:
        # raised on invalid process name
        raise HTTPBadRequest(detail=str(ex))

    json_response = {'processSummary': saved_process.process_summary(), 'deploymentDone': True}
    return HTTPOk(json=json_response)


def get_process(request):
    # type: (Request) -> ProcessDB
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id, visibility=VISIBILITY_PUBLIC, request=request)
        return process
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("Process with id `{}` is not accessible.".format(str(process_id)))
    except ProcessNotFound:
        raise HTTPNotFound("Process with id `{}` does not exist.".format(str(process_id)))
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema:\n[{0!r}]\n[{0!s}].".format(ex))
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))


@sd.process_service.get(tags=[sd.processes_tag, sd.describeprocess_tag], renderer='json',
                        schema=sd.ProcessEndpoint(), response_schemas=sd.get_process_responses)
def get_local_process(request):
    """
    Get a registered local process information (DescribeProcess).
    """
    try:
        process = get_process(request)
        process['inputs'] = opensearch.replace_inputs_describe_process(process.inputs, process.payload)
        process_offering = process.process_offering()
        return HTTPOk(json=process_offering)
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except colander.Invalid as ex:
        raise HTTPBadRequest("Invalid schema: [{}]".format(str(ex)))
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))


@sd.process_package_service.get(tags=[sd.processes_tag, sd.describeprocess_tag], renderer='json',
                                schema=sd.ProcessPackageEndpoint(), response_schemas=sd.get_process_package_responses)
def get_local_process_package(request):
    """
    Get a registered local process package definition.
    """
    process = get_process(request)
    return HTTPOk(json=process.package or {})


@sd.process_payload_service.get(tags=[sd.processes_tag, sd.describeprocess_tag], renderer='json',
                                schema=sd.ProcessPayloadEndpoint(), response_schemas=sd.get_process_payload_responses)
def get_local_process_payload(request):
    """
    Get a registered local process payload definition.
    """
    process = get_process(request)
    return HTTPOk(json=process.payload or {})


@sd.process_visibility_service.get(tags=[sd.processes_tag, sd.visibility_tag], renderer='json',
                                   schema=sd.ProcessVisibilityGetEndpoint(),
                                   response_schemas=sd.get_process_visibility_responses)
def get_process_visibility(request):
    """
    Get the visibility of a registered local process.
    """
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        visibility_value = store.get_visibility(process_id, request=request)
        return HTTPOk(json={u'value': visibility_value})
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))


@sd.process_visibility_service.put(tags=[sd.processes_tag, sd.visibility_tag], renderer='json',
                                   schema=sd.ProcessVisibilityPutEndpoint(),
                                   response_schemas=sd.put_process_visibility_responses)
def set_process_visibility(request):
    """
    Set the visibility of a registered local process.
    """
    visibility_value = request.json.get('value')
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    if not isinstance(visibility_value, string_types):
        raise HTTPUnprocessableEntity("Invalid visibility value specified.")
    if visibility_value not in visibility_values:
        raise HTTPBadRequest("Invalid visibility value specified.")

    try:
        store = get_db(request).get_store(StoreProcesses)
        store.set_visibility(process_id, visibility_value, request=request)
        return HTTPOk(json={u'value': visibility_value})
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except TypeError:
        raise HTTPBadRequest('Value of visibility must be a string.')
    except ValueError:
        raise HTTPUnprocessableEntity('Value of visibility must be one of : {!s}'
                                      .format(list(visibility_values)))
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))


@sd.process_service.delete(tags=[sd.processes_tag, sd.deploy_tag], renderer='json',
                           schema=sd.ProcessEndpoint(), response_schemas=sd.delete_process_responses)
def delete_local_process(request):
    """
    Unregister a local process.
    """
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        if store.delete_process(process_id, visibility=VISIBILITY_PUBLIC, request=request):
            return HTTPOk(json={'undeploymentDone': True, 'identifier': process_id})
        raise HTTPInternalServerError("Delete process failed for unhandled reason.")
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("Process with id `{}` is not accessible.".format(str(process_id)))
    except ProcessNotFound:
        description = "Process with id `{}` does not exist.".format(str(process_id))
        raise HTTPNotFound(description)
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))


@sd.process_jobs_service.post(tags=[sd.processes_tag, sd.execute_tag, sd.jobs_tag], renderer='json',
                              schema=sd.PostProcessJobsEndpoint(), response_schemas=sd.post_process_jobs_responses)
def submit_local_job(request):
    """
    Execute a local process.
    """
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id, visibility=VISIBILITY_PUBLIC, request=request)
        resp = submit_job_handler(request, process.processEndpointWPS1,
                                  is_workflow=process.type == PROCESS_WORKFLOW,
                                  visibility=process.visibility)
        return resp
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except InvalidIdentifierValue as ex:
        raise HTTPBadRequest(str(ex))
    except ProcessNotAccessible:
        raise HTTPUnauthorized("Process with id `{}` is not accessible.".format(str(process_id)))
    except ProcessNotFound:
        raise HTTPNotFound("The process with id `{}` does not exist.".format(str(process_id)))
    except Exception as ex:
        raise HTTPInternalServerError(str(ex))
