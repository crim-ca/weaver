from pyramid.httpexceptions import *
from pyramid_celery import celery_app as app
from celery.utils.log import get_task_logger
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import URLError
from time import sleep
from twitcher.adapter import servicestore_factory, jobstore_factory
from twitcher.datatype import Job as JobDB
from twitcher.exceptions import JobRegistrationError
from twitcher.utils import get_any_id
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.utils import *
from twitcher.wps_restapi.jobs.jobs import check_status
from twitcher.wps_restapi import status as job_status
from owslib.wps import WebProcessingService, WPSException, ComplexDataInput, is_reference
from lxml import etree

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
        job.status = job_status.STATUS_RUNNING
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
                job.status = execution.getStatus()
                job.status_message = execution.statusMessage
                job.progress = execution.percentCompleted

                if execution.isComplete():
                    job.is_finished()
                    if execution.isSucceded():
                        task_logger.debug("Job succeeded")
                        job.progress = 100
                        job.status = job_status.STATUS_FINISHED
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

    except (WPSException, JobRegistrationError, Exception) as exc:
        task_logger.exception("Failed to run {}.".format(str(job)))
        job.status = job_status.STATUS_FAILED
        if isinstance(exc, WPSException):
            job.status_message = "Error: [{0}] {1}".format(exc.locator, exc.text)
        else:
            job.status_message = "Error: {0}".format(exc.message)

    finally:
        job.save_log(logger=task_logger)
        job = store.update_job(job)

    return job.status


def submit_job_handler(request, service_url):

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
        userid=request.unauthenticated_userid,
        url=wps.url,
        service_name=process_id,
        identifier=process.identifier,
        provider=provider_id,
        inputs=inputs,
        outputs=outputs,
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
        'status': job_status.STATUS_ACCEPTED,
        'location': location
    }
    headers = request.headers
    headers.update({'Location': location})
    return HTTPCreated(json=body_data, headers=headers)


#############
# EXAMPLE
#############
#   Parameters: ?sync-execute=true|false (false being the default value)
#
#   Content-Type: application/json;
#
# {
#     "inputs": [
#         {
#             "id": "sosInputNiederschlag",
#             "value": "http://www.fluggs.de/sos2/sos?service%3DSOS&version%3D2.0.0&request%3DGetObservation&responseformat%3Dhttp://www.opengis.net/om/2.0&observedProperty%3DNiederschlagshoehe&procedure%3DTagessumme&featureOfInterest%3DBever-Talsperre&&namespaces%3Dxmlns%28sams%2Chttp%3A%2F%2Fwww.opengis.net%2FsamplingSpatial%2F2.0%29%2Cxmlns%28om%2Chttp%3A%2F%2Fwww.opengis.net%2Fom%2F2.0%29&temporalFilter%3Dom%3AphenomenonTime%2C2016-01-01T10:00:00.00Z%2F2016-04-30T23:59:00.000Z",
# 			"type" : "text/plain"
#         },
#         {
#             "id": "sosInputFuellstand",
#             "value": "http://www.fluggs.de/sos2/sos?service%3DSOS&version%3D2.0.0&request%3DGetObservation&responseformat%3Dhttp://www.opengis.net/om/2.0&observedProperty%3DSpeicherfuellstand&procedure%3DEinzelwert&featureOfInterest%3DBever-Talsperre_Windenhaus&namespaces%3Dxmlns%28sams%2Chttp%3A%2F%2Fwww.opengis.net%2FsamplingSpatial%2F2.0%29%2Cxmlns%28om%2Chttp%3A%2F%2Fwww.opengis.net%2Fom%2F2.0%29&temporalFilter%3Dom%3AphenomenonTime%2C2016-01-01T10:00:00.00Z%2F2016-04-30T23:59:00.000Z",
# 			"type" : "text/plain"
#         },
#         {
#             "id": "sosInputTarget",
#             "value": "http://fluggs.wupperverband.de/sos2-tamis/service?service%3DSOS&version%3D2.0.0&request%3DGetObservation&responseformat%3Dhttp://www.opengis.net/om/2.0&observedProperty%3DWasserstand_im_Damm&procedure%3DHandeingabe&featureOfInterest%3DBever-Talsperre_MQA7_Piezometer_Kalkzone&namespaces%3Dxmlns%28sams%2Chttp%3A%2F%2Fwww.opengis.net%2FsamplingSpati-al%2F2.0%29%2Cxmlns%28om%2Chttp%3A%2F%2Fwww.opengis.net%2Fom%2F2.0%29&temporalFilter%3Dom%3AphenomenonTime%2C2016-01-01T00:01:00.00Z%2F2016-04-30T23:59:00.000Z",
# 			"type" : "text/plain"
#         }
#     ],
#     "outputs": [
#       {
#               "id": "targetObs_plot",
#               "type": "image/png"
#        },
#       {
#               "id": "model_diagnostics",
#               "type": "image/png"
#        },
#       {
#               "id": "relations",
#               "type": "image/png"
#        },
#       {
#               "id": "model_prediction",
#               "type": "text/csv"
#        },
#       {
#               "id": "metaJson",
#               "type": "application/json"
#        },
#       {
#               "id": "dataJson",
#               "type": "application/json"
#        }
#     ]
# }
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
    Retrieve available processes (GetCapabilities).
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
