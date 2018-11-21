import os
from pyramid.httpexceptions import *
from pyramid.settings import asbool
from pyramid_celery import celery_app as app
from pyramid.request import Request
from celery.utils.log import get_task_logger
from six.moves.urllib.parse import urlparse
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import URLError
from time import sleep

from twitcher.wps import load_pywps_cfg
from twitcher.adapter import servicestore_factory, jobstore_factory, processstore_factory
from twitcher.config import get_twitcher_configuration, TWITCHER_CONFIGURATION_EMS
from twitcher.datatype import Process as ProcessDB, Job as JobDB, Input, Output
from twitcher.exceptions import (
    ProcessRegistrationError,
    ProcessNotFound,
    PackageRegistrationError,
    PackageTypeError,
    PackageNotFound,
)
from twitcher.processes import wps_package, opensearch
from twitcher.processes.types import PROCESS_WORKFLOW
from twitcher.store import processstore_defaultfactory
from twitcher.utils import get_any_id, get_any_value, raise_on_xml_exception
from twitcher.namesgenerator import get_sane_name
from twitcher.utils import get_any_id, raise_on_xml_exception
from twitcher.owsexceptions import OWSNoApplicableCode
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.utils import *
from twitcher.wps_restapi.jobs.jobs import check_status
from twitcher.visibility import VISIBILITY_PUBLIC, visibility_values
from twitcher.status import (
    map_status,
    STATUS_ACCEPTED,
    STATUS_STARTED,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    STATUS_PENDING,
)
from twitcher.sync import EXECUTE_AUTO, EXECUTE_ASYNC, EXECUTE_SYNC
from owslib.wps import WebProcessingService, WPSException, ComplexDataInput, is_reference
from owslib.util import clean_ows_url
from lxml import etree
from six import string_types
from copy import deepcopy
import requests

task_logger = get_task_logger(__name__)


def wait_secs(run_step=-1):
    secs_list = (2, 2, 2, 2, 2, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 20, 20, 20, 20, 20, 30)
    if run_step >= len(secs_list):
        run_step = -1
    return secs_list[run_step]


def _get_data(input_value):
    """
    Extract the data from the input value
    """
    # process output data are append into a list and
    # WPS standard v1.0.0 specify that Output data field has zero or one value
    if input_value.data:
        return input_value.data[0]
    else:
        return None


def _read_reference(input_value):
    """
    Read a WPS reference and return the content
    """
    try:
        return urlopen(input_value.reference).read()
    except URLError:
        # Don't raise exceptions coming from that.
        return None


def _get_json_multiple_inputs(input_value):
    """
    Since WPS standard does not allow to return multiple values for a single output,
    a lot of process actually return a json array containing references to these outputs.
    This function goal is to detect this particular format
    :return: An array of references if the input_value is effectively a json containing that,
             None otherwise
    """

    # Check for the json datatype and mimetype
    if input_value.dataType == 'ComplexData' and input_value.mimeType == 'application/json':

        # If the json data is referenced read it's content
        if input_value.reference:
            json_data_str = _read_reference(input_value)
        # Else get the data directly
        else:
            json_data_str = _get_data(input_value)

        # Load the actual json dict
        json_data = json.loads(json_data_str)

        if isinstance(json_data, list):
            for data_value in json_data:
                if not is_reference(data_value):
                    return None
            return json_data
    return None


def _jsonify_output(output, datatype):
    """
    Utility method to jsonify an output element.
    :param output An owslib.wps.Output to jsonify
    """
    json_output = dict(identifier=output.identifier,
                       title=output.title,
                       dataType=output.dataType or datatype)

    if not output.dataType:
        output.dataType = datatype

    # WPS standard v1.0.0 specify that either a reference or a data field has to be provided
    if output.reference:
        json_output['reference'] = output.reference

        # Handle special case where we have a reference to a json array containing dataset reference
        # Avoid reference to reference by fetching directly the dataset references
        json_array = _get_json_multiple_inputs(output)
        if json_array and all(str(ref).startswith('http') for ref in json_array):
            json_output['data'] = json_array
    else:
        # WPS standard v1.0.0 specify that Output data field has Zero or one value
        json_output['data'] = output.data[0] if output.data else None

    if json_output['dataType'] == 'ComplexData':
        json_output['mimeType'] = output.mimeType

    return json_output


def retrieve_package_job_log(execution, job):
    # If the process is a twitcher package this status xml should be available in the process output dir
    status_xml_fn = execution.statusLocation.split('/')[-1]
    try:
        registry = app.conf['PYRAMID_REGISTRY']
        output_path = registry.settings['twitcher.wps_output_path']

        # twitcher package log every status update into this file (we no longer rely on the http monitoring)
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
def execute_process(self, job_id, url, headers=None):
    registry = app.conf['PYRAMID_REGISTRY']
    load_pywps_cfg(registry)

    ssl_verify = asbool(registry.settings.get('twitcher.ows_proxy_ssl_verify', True))
    store = jobstore_factory(registry)
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
        outputs = [
            (o.identifier, o.dataType == 'ComplexData') for o in process.processOutputs
        ]

        mode = EXECUTE_ASYNC if job.execute_async else EXECUTE_SYNC
        execution = wps.execute(job.process, inputs=wps_inputs, output=outputs, mode=mode, lineage=True)

        if not execution.process and execution.errors:
            raise execution.errors[0]

        job.status = STATUS_STARTED
        job.status_message = execution.statusMessage or "{} initiation done.".format(str(job))
        job.status_location = execution.statusLocation
        job.request = execution.request
        job.response = etree.tostring(execution.response)
        job.save_log(logger=task_logger)
        job = store.update_job(job)

        num_retries = 0
        run_step = 0
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= 5:
                raise Exception("Could not read status document after 5 retries. Giving up.")
            try:
                execution = check_status(url=execution.statusLocation, verify=ssl_verify,
                                         sleep_secs=wait_secs(run_step))

                job.response = etree.tostring(execution.response)
                job.status = map_status(execution.getStatus())
                job.status_message = execution.statusMessage
                job.progress = execution.percentCompleted
                job.save_log(logger=task_logger)

                if execution.isComplete():
                    job.is_finished()
                    if execution.isSucceded():
                        job.progress = 100
                        job.status = STATUS_SUCCEEDED
                        job.status_message = execution.statusMessage or "Job succeeded."
                        retrieve_package_job_log(execution, job)
                        job.save_log(logger=task_logger)

                        process = wps.describeprocess(job.process)
                        output_datatype = {
                            getattr(processOutput, 'identifier', ''): processOutput.dataType
                            for processOutput in getattr(process, 'processOutputs', [])}

                        job.results = [_jsonify_output(output, output_datatype[output.identifier])
                                       for output in execution.processOutputs]
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
        job.status = STATUS_FAILED
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
        job = store.update_job(job)

    return job.status


def submit_job_handler(request, service_url, is_workflow=False):
    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')  # None OK if local
    process_id = request.matchdict.get('process_id')
    tags = request.params.get('tags', '').split(',')

    if not all(k in request.json_body for k in ('inputs', 'outputs', 'mode', 'response')):
        raise HTTPBadRequest("Missing one of required parameters [inputs, outputs, mode, response].")

    if request.json_body['mode'] not in [EXECUTE_ASYNC, EXECUTE_AUTO]:
        raise HTTPNotImplemented(detail='{0} mode not supported.'.format(request.json_body['mode']))
    execute_async = request.json_body['mode'] != EXECUTE_SYNC

    if request.json_body['response'] != 'document':
        raise HTTPNotImplemented(detail='{0} response not supported.'.format(request.json_body['response']))

    for job_input in request.json_body['inputs']:
        if not ('id' in job_input and any(k in job_input for k in ('data', 'href'))):
            raise HTTPBadRequest("Missing one of required output parameters [id, data|href].")

    for job_output in request.json_body['outputs']:
        if not all(k in job_output for k in ('id', 'transmissionMode')):
            raise HTTPBadRequest(detail="Missing one of required output parameters [id, transmissionMode].")
        if job_output['transmissionMode'] != 'reference':
            raise HTTPNotImplemented(detail='{0} transmissionMode not supported.'
                                     .format(job_output['transmissionMode']))

    store = jobstore_factory(request.registry)
    job = store.save_job(task_id=STATUS_PENDING, process=process_id, service=provider_id,
                         inputs=request.json_body['inputs'], is_workflow=is_workflow,
                         user_id=request.authenticated_userid, execute_async=execute_async, custom_tags=tags)
    result = execute_process.delay(
        job_id=job.id,
        url=clean_ows_url(service_url),
        # Convert EnvironHeaders to a simple dict (should cherrypick the required headers)
        headers={k: v for k, v in request.headers.items()})
    LOGGER.debug("Celery pending task `{}` for job `{}`.", result.id, job.id)

    # local/provider process location
    location_base = '/providers/{provider_id}'.format(provider_id=provider_id) if provider_id else ''
    location = '{base_url}{location_base}/processes/{process_id}/jobs/{job_id}'.format(
        base_url=wps_restapi_base_url(request.registry.settings),
        location_base=location_base,
        process_id=process_id,
        job_id=job.id)
    body_data = {
        'jobID': job.id,
        'status': STATUS_ACCEPTED,
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
    store = servicestore_factory(request.registry)
    provider_id = request.matchdict.get('provider_id')
    service = store.fetch_by_name(provider_id, request=request)
    return submit_job_handler(request, service.url)


@sd.provider_processes_service.get(tags=[sd.provider_processes_tag, sd.providers_tag, sd.getcapabilities_tag],
                                   renderer='json', schema=sd.ProviderEndpoint(),
                                   response_schemas=sd.get_provider_processes_responses)
def get_provider_processes(request):
    """
    Retrieve available provider processes (GetCapabilities).
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')

    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    processes = []
    for process in wps.processes:
        item = dict(
            id=process.identifier,
            title=getattr(process, 'title', ''),
            abstract=getattr(process, 'abstract', ''),
            url='{base_url}/providers/{provider_id}/processes/{process_id}'.format(
                base_url=wps_restapi_base_url(request.registry.settings),
                provider_id=provider_id,
                process_id=process.identifier))
        processes.append(item)
    return HTTPOk(json=processes)


@sd.provider_process_service.get(tags=[sd.provider_processes_tag, sd.providers_tag, sd.describeprocess_tag],
                                 renderer='json', schema=sd.ProviderProcessEndpoint(),
                                 response_schemas=sd.get_provider_process_description_responses)
def describe_provider_process(request):
    """
    Retrieve a process description (DescribeProcess).
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')

    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    process = wps.describeprocess(process_id)

    inputs = [dict(
        id=getattr(dataInput, 'identifier', ''),
        title=getattr(dataInput, 'title', ''),
        abstract=getattr(dataInput, 'abstract', ''),
        minOccurs=getattr(dataInput, 'minOccurs', 0),
        maxOccurs=getattr(dataInput, 'maxOccurs', 0),
        dataType=dataInput.dataType,
        defaultValue=jsonify(getattr(dataInput, 'defaultValue', None)),
        allowedValues=[jsonify(dataValue) for dataValue in getattr(dataInput, 'allowedValues', [])],
        supportedValues=[jsonify(dataValue) for dataValue in getattr(dataInput, 'supportedValues', [])],
    ) for dataInput in getattr(process, 'dataInputs', [])]

    outputs = [dict(
        id=getattr(processOutput, 'identifier', ''),
        title=getattr(processOutput, 'title', ''),
        abstract=getattr(processOutput, 'abstract', ''),
        dataType=processOutput.dataType,
        defaultValue=jsonify(getattr(processOutput, 'defaultValue', None))
    ) for processOutput in getattr(process, 'processOutputs', [])]

    body_data = dict(
        id=process_id,
        label=getattr(process, 'title', ''),
        description=getattr(process, 'abstract', ''),
        inputs=inputs,
        outputs=outputs
    )
    return HTTPOk(json=body_data)


@sd.processes_service.get(schema=sd.GetProcessesRequest(), tags=[sd.processes_tag, sd.getcapabilities_tag],
                          response_schemas=sd.get_processes_responses)
def get_processes(request):
    """
    List registered processes (GetCapabilities). Optionally list both local and provider processes.
    """
    try:
        # get local processes
        store = processstore_factory(request.registry)
        processes = [process.summary() for process in
                     store.list_processes(visibility=VISIBILITY_PUBLIC, request=request)]
        response_body = {'processes': processes}

        # if EMS and ?providers=True, also fetch each provider's processes
        if get_twitcher_configuration(request.registry.settings) == TWITCHER_CONFIGURATION_EMS:
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
    except Exception as ex:
        LOGGER.exception(ex.message, exc_info=True)
        raise HTTPInternalServerError(ex.message)


@sd.processes_service.post(tags=[sd.processes_tag, sd.deploy_tag], renderer='json',
                           schema=sd.ProcessesEndpoint(), response_schemas=sd.post_processes_responses)
def add_local_process(request):
    """
    Register a local process.
    """
    # validate minimum field requirements
    body = request.json

    # use deepcopy of body payload to avoid circular dependencies when writing to mongodb
    # and before parsing it because the body is altered by some pop operations
    payload = deepcopy(body)

    if 'processDescription' not in body:
        raise HTTPBadRequest("Missing required parameter 'processDescription'.")
    process_description = body.get('processDescription')
    if not isinstance(process_description, dict):
        raise HTTPUnprocessableEntity("Invalid parameter 'processDescription'.")
    process_info = process_description.get('process')
    if not isinstance(process_info, dict):
        raise HTTPUnprocessableEntity("Invalid parameter 'processDescription.process'.")
    if not isinstance(get_any_id(process_info), string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'processDescription.process.identifier'.")
    process_info['identifier'] = get_sane_name(get_any_id(process_info))

    # retrieve CWL package definition, either via owsContext or executionUnit package/reference
    deployment_profile = body.get('deploymentProfileName')
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
    elif deployment_profile.endswith('workflow'):
        execution_units = body.get('executionUnit')
        if not isinstance(execution_units, list):
            raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")
        for execution_unit in execution_units:
            if not isinstance(execution_unit, dict):
                raise HTTPUnprocessableEntity("Invalid parameter 'executionUnit'.")
            package = execution_unit.get('unit')
            reference = execution_unit.get('href')
    else:
        raise HTTPBadRequest("Missing one of required parameters [owsContext, deploymentProfileName being a workflow].")

    # obtain updated process information using WPS process offering and CWL package definition
    try:
        # data_source `None` forces workflow process to search locally for deployed step applications
        process_info = wps_package.get_process_from_wps_request(process_info, reference, package, data_source=None)
    except PackageNotFound as ex:
        # raised when a workflow sub-process is not found (not deployed locally)
        raise HTTPNotFound(detail=ex.message)
    except (PackageRegistrationError, PackageTypeError) as ex:
        raise HTTPUnprocessableEntity(detail=ex.message)
    except Exception as ex:
        raise HTTPBadRequest("Invalid package/reference definition. Loading generated error: `{}`".format(repr(ex)))

    # convert inputs and outputs to be compliant with schema
    process_info['inputs'] = [Input.from_wps_names(i) for i in process_info['inputs']]
    process_info['outputs'] = [Output.from_wps_names(i) for i in process_info['outputs']]

    # validate process type against twitcher configuration
    settings = request.registry.settings
    process_type = process_info['type']
    if process_type == PROCESS_WORKFLOW:
        twitcher_config = get_twitcher_configuration(settings)
        if twitcher_config != TWITCHER_CONFIGURATION_EMS:
            raise HTTPBadRequest("Invalid `{0}` package deployment on `{1}`.".format(process_type, twitcher_config))

    restapi_url = wps_restapi_base_url(settings)
    description_url = "/".join([restapi_url, 'processes', process_info['identifier']])
    execute_endpoint = "/".join([description_url, "jobs"])

    # ensure that required 'executeWPSEndpoint' in db is added, will be auto-fixed to localhost if not specified in body
    process_info['executeWPSEndpoint'] = process_description.get('executeWPSEndpoint')
    process_info['executeEndpoint'] = execute_endpoint
    process_info['payload'] = payload
    process_info['jobControlOptions'] = process_description.get('jobControlOptions', [])
    process_info['outputTransmission'] = process_description.get('outputTransmission', [])
    process_info['owsContext'] = ows_context
    process_info['processDescriptionURL'] = description_url

    try:
        store = processstore_factory(request.registry)
        saved_process = store.save_process(ProcessDB(process_info), overwrite=False, request=request)
    except ProcessRegistrationError as ex:
        raise HTTPConflict(detail=ex.message)
    except ValueError as ex:
        # raised on invalid process name
        raise HTTPBadRequest(detail=ex.message)

    return HTTPOk(json={'deploymentDone': True, 'processSummary': saved_process.summary()})


@sd.process_service.get(tags=[sd.processes_tag, sd.describeprocess_tag], renderer='json',
                        schema=sd.ProcessEndpoint(), response_schemas=sd.get_process_responses)
def get_local_process(request):
    """
    Get a registered local process information (DescribeProcess).
    """

    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = processstore_factory(request.registry)
        process = store.fetch_by_id(process_id, request=request)
        offering = process.process_offering()

        try:
            inputs, payload = process.inputs, process["payload"]
            new_inputs = opensearch.replace_inputs_describe_process(inputs, payload)
            new_inputs = [Input(i).inputType() for i in new_inputs]
            offering["process"]["inputs"] = new_inputs
        except KeyError:
            # Process may not have a payload... in this case no eoimage inputs anyway
            pass
        return HTTPOk(json=offering)
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound:
        raise HTTPNotFound("The process with id `{}` does not exist.".format(str(process_id)))
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)


def get_process(request):
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'.")
    try:
        store = processstore_factory(request.registry)
        process = store.fetch_by_id(process_id, request=request)
        return process
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound:
        raise HTTPNotFound("The process with id `{}` does not exist.".format(str(process_id)))
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)


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
        store = processstore_factory(request.registry)
        visibility_value = store.get_visibility(process_id, request=request)
        return HTTPOk(json={u'value': visibility_value})
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound as ex:
        raise HTTPNotFound(ex.message)
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)


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

    try:
        store = processstore_factory(request.registry)
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
        raise HTTPNotFound(ex.message)
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)


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
        store = processstore_factory(request.registry)
        if store.delete_process(process_id, request=request):
            return HTTPOk(json={'undeploymentDone': True, 'identifier': process_id})
        raise HTTPInternalServerError("Delete process failed.")
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound:
        description = "The process with process_id `{}` does not exist.".format(str(process_id))
        raise HTTPNotFound(description)
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)


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
        store = processstore_factory(request.registry)
        process = store.fetch_by_id(process_id, request=request)
        resp = submit_job_handler(request, process.executeWPSEndpoint, is_workflow=process.type == 'workflow')
        return resp
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound:
        raise HTTPNotFound("The process with id `{}` does not exist.".format(str(process_id)))
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)
