from pyramid.httpexceptions import *
from pyramid.settings import asbool
from pyramid_celery import celery_app as app
from celery.utils.log import get_task_logger
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import URLError
from time import sleep
from twitcher.adapter import servicestore_factory, jobstore_factory, processstore_factory
from twitcher.config import get_twitcher_configuration, TWITCHER_CONFIGURATION_EMS
from twitcher.datatype import Process as ProcessDB, Job as JobDB
from twitcher.exceptions import ProcessNotFound, JobRegistrationError
from twitcher.store import processstore_defaultfactory
from twitcher.utils import get_any_id
from twitcher.processes import wps_workflow as wf
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.utils import *
from twitcher.wps_restapi.jobs.jobs import check_status
from twitcher.wps_restapi import status
from owslib.wps import WebProcessingService, WPSException, ComplexDataInput, is_reference
from lxml import etree
from six import string_types
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


def _map_status(wps_execution_status):
    job_status = wps_execution_status.lower().strip('process')
    if job_status in status.status_values:
        return job_status
    return 'unknown'


@app.task(bind=True)
def execute_process(self, url, service, process, inputs, outputs,
                    is_workflow=False, user_id=None, async=True, headers=None):
    registry = app.conf['PYRAMID_REGISTRY']
    store = jobstore_factory(registry)
    task_id = self.request.id
    job = JobDB({'task_id': task_id})  # default in case of error during registration to job store
    try:
        job = store.save_job(task_id=task_id, process=process, service=service, is_workflow=is_workflow,
                             user_id=user_id, async=async)

        wps = WebProcessingService(url=url, headers=get_cookie_headers(headers), skip_caps=False, verify=False)
        # execution = wps.execute(process, inputs=inputs, output=outputs, async=async, lineage=True)
        mode = 'async' if async else 'sync'
        execution = wps.execute(process, inputs=inputs, output=outputs, mode=mode, lineage=True)
        # job['service'] = wps.identification.title
        # job['title'] = getattr(execution.process, "title")
        if not execution.process and execution.errors:
            raise execution.errors[0]

        # job['abstract'] = getattr(execution.process, "abstract")
        job.status = status.STATUS_RUNNING
        job.status_location = execution.statusLocation
        job.request = execution.request
        job.response = etree.tostring(execution.response)
        job = store.update_job(job)

        task_logger.debug("Job init done %s ...", task_id)

        num_retries = 0
        run_step = 0
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= 5:
                raise Exception("Could not read status document after 5 retries. Giving up.")
            try:
                execution = check_status(url=execution.statusLocation, verify=False,
                                         sleep_secs=wait_secs(run_step))

                job.response = etree.tostring(execution.response)
                job.status = _map_status(execution.getStatus())
                job.status_message = execution.statusMessage
                job.progress = execution.percentCompleted

                if execution.isComplete():
                    job.is_finished()
                    if execution.isSucceded():
                        task_logger.debug("Job succeeded")
                        job.progress = 100
                        job.status = status.STATUS_FINISHED
                        job.status_message = execution.statusMessage

                        process = wps.describeprocess(job.process)

                        output_datatype = {
                            getattr(processOutput, 'identifier', ''): processOutput.dataType
                            for processOutput in getattr(process, 'processOutputs', [])}

                        job.results = [_jsonify_output(output, output_datatype[output.identifier])
                                       for output in execution.processOutputs]
                    else:
                        task_logger.debug("Job failed.")
                        job.status_message = '\n'.join(error.text for error in execution.errors)
                        job.save_log(errors=execution.errors, logger=task_logger)

            except Exception as exc:
                num_retries += 1
                task_logger.debug('Exception raised: {}'.format(repr(exc)))
                task_logger.exception("Could not read status xml document for job %s. Trying again ...", task_id)
                sleep(1)
            else:
                task_logger.debug("Update job %s ...", task_id)
                num_retries = 0
                run_step += 1
            finally:
                job.save_log(logger=task_logger)
                job = store.update_job(job)

    except (WPSException, Exception) as exc:
        task_logger.exception("Failed to run {}.".format(str(job)))
        job.status = status.STATUS_FAILED
        if isinstance(exc, WPSException):
            job.status_message = "Error: [{0}] {1}".format(exc.locator, exc.text)
        else:
            job.status_message = "Error: {0}".format(exc.message)

    finally:
        job.save_log(logger=task_logger)
        job = store.update_job(job)

    return job.status


def submit_job_handler(request, service_url, is_workflow=False):

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')  # None OK if local
    process_id = request.matchdict.get('process_id')
    async_execute = not request.params.getone('sync-execute') if 'sync-execute' in request.params else True

    wps = WebProcessingService(url=service_url, headers=get_cookie_headers(request.headers))
    process = wps.describeprocess(process_id)

    # prepare inputs
    complex_inputs = []
    for process_input in process.dataInputs:
        if 'ComplexData' in process_input.dataType:
            complex_inputs.append(process_input.identifier)

    try:
        # need to use ComplexDataInput structure for complex input
        inputs = [(get_any_id(inpt), ComplexDataInput(inpt['value'])
                  if get_any_id(inpt) in complex_inputs else inpt['value'])
                  for inpt in request.json_body['inputs']]
    except KeyError:
        inputs = []

    # prepare outputs
    outputs = []
    for output in process.processOutputs:
        outputs.append(
            (output.identifier, output.dataType == 'ComplexData'))

    result = execute_process.delay(
        url=wps.url,
        service=provider_id,
        process=process.identifier,
        inputs=inputs,
        outputs=outputs,
        is_workflow=is_workflow,
        user_id=request.authenticated_userid,
        async=async_execute,
        # Convert EnvironHeaders to a simple dict (should cherrypick the required headers)
        headers={k: v for k, v in request.headers.items()})

    # local/provider process location
    location_base = '/providers/{provider_id}'.format(provider_id=provider_id) if provider_id else ''
    location = '{base_url}{location_base}/processes/{process_id}/jobs/{job_id}'.format(
        base_url=wps_restapi_base_url(request.registry.settings),
        location_base=location_base,
        process_id=process.identifier,
        job_id=result.id)
    body_data = {
        'jobID': result.id,
        'status': status.STATUS_ACCEPTED,
        'location': location
    }
    headers = request.headers
    headers.update({'Location': location})
    return HTTPCreated(json=body_data, headers=headers)


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
                                 renderer='json', schema=sd.ProcessEndpoint(),
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
        store = processstore_defaultfactory(request.registry)
        processes = [process.summary() for process in store.list_processes()]
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
        raise HTTPInternalServerError(ex.message)


@sd.processes_service.post(tags=[sd.processes_tag, sd.deploy_tag], renderer='json',
                           schema=sd.ProcessesEndpoint(), response_schemas=sd.post_processes_responses)
def add_local_process(request):
    """
    Register a local process.
    """
    store = processstore_defaultfactory(request.registry)

    process_offering = request.json.get('processOffering')
    deployment_profile = request.json.get('deploymentProfile')
    if not isinstance(process_offering, dict):
        raise HTTPUnprocessableEntity("Invalid parameter 'processOffering'")
    if not isinstance(deployment_profile, dict):
        raise HTTPUnprocessableEntity("Invalid parameter 'deploymentProfile'")

    # validate minimum field requirements
    process_info = process_offering.get('process')
    if not isinstance(process_info, dict):
        raise HTTPUnprocessableEntity("Invalid parameter 'processOffering.process'")
    if not isinstance(process_info.get('identifier'), string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'processOffering.process.identifier'")

    process_type = request.json.get('type', 'workflow')
    if process_type == 'workflow':
        execution_unit = deployment_profile.get('executionUnit')
        if not isinstance(execution_unit, dict):
            raise HTTPUnprocessableEntity("Invalid parameter 'deploymentProfile.executionUnit'")
        package = execution_unit.get('package')
        reference = execution_unit.get('reference')
        if not (isinstance(package, dict) or isinstance(reference, string_types)):
            raise HTTPUnprocessableEntity(
                detail="Invalid parameters amongst one of [package,reference] in 'deploymentProfile.executionUnit'.")
        if package and reference:
            raise HTTPUnprocessableEntity(
                detail="Simultaneous parameters [package,reference] not allowed in 'deploymentProfile.executionUnit'.")

        # retrieve package information and validate them at the same time by loading/updating definitions to store in DB
        if reference:
            package = wf.load_workflow_file(reference)
        try:
            workflow = wf.load_workflow_content(package)
            workflow_inputs, workflow_outputs = wf.get_workflow_inputs_outputs(workflow)
            process_inputs = process_info.get('inputs', list())
            process_outputs = process_info.get('outputs', list())
            workflow_inputs, workflow_outputs = wf.merge_workflow_inputs_outputs(process_inputs, workflow_inputs,
                                                                                 process_outputs, workflow_outputs,
                                                                                 as_json=True)
            process_info.update({'package': package, 'inputs': workflow_inputs, 'outputs': workflow_outputs})
        except Exception as ex:
            raise HTTPBadRequest("Invalid package/reference definition. Loading generated error: `{}`".format(repr(ex)))

    # ensure that required 'executeEndpoint' in db is added, will be auto-fixed to localhost if not specified in body
    process_info.update({'type': process_type, 'executeEndpoint': process_info.get('executeEndpoint')})
    saved_process = store.save_process(ProcessDB(process_info))

    return HTTPOk(json={'deploymentDone': True, 'processSummary': saved_process.summary()})


@sd.process_service.get(tags=[sd.processes_tag, sd.describeprocess_tag], renderer='json',
                        schema=sd.ProcessEndpoint(), response_schemas=sd.get_process_responses)
def get_local_process(request):
    """
    Get a registered local process information (DescribeProcess).
    """
    process_id = request.matchdict.get('process_id')
    if not isinstance(process_id, string_types):
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'")
    try:
        store = processstore_defaultfactory(request.registry)
        process = store.fetch_by_id(process_id)
        return HTTPOk(json={'process': process.json()})
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound:
        raise HTTPNotFound("The process with id `{}` does not exist.".format(str(process_id)))
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
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'")
    try:
        store = processstore_defaultfactory(request.registry)
        if store.delete_process(process_id):
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
        raise HTTPUnprocessableEntity("Invalid parameter 'process_id'")
    try:
        store = processstore_defaultfactory(request.registry)
        process = store.fetch_by_id(process_id)
        return submit_job_handler(request, process.executeEndpoint, is_workflow=process.type == 'workflow')
    except HTTPException:
        raise  # re-throw already handled HTTPException
    except ProcessNotFound:
        raise HTTPNotFound("The process with id `{}` does not exist.".format(str(process_id)))
    except Exception as ex:
        raise HTTPInternalServerError(ex.message)
