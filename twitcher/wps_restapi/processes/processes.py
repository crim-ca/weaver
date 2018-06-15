from pyramid.view import view_config
from twitcher.store import servicestore_factory
from owslib.wps import WebProcessingService
from owslib.wps import ComplexData
from twitcher.wps_restapi.utils import restapi_base_url


@view_config(route_name='processes', request_method='GET', renderer='json')
def get_processes(request):
    """
    Retrieve available processes
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')

    service = store.fetch_by_name(provider_name)
    wps = WebProcessingService(url=service.url)
    processes = []
    for process in wps.processes:
        item = dict(
            id=process.identifier,
            label=getattr(process, 'title', ''),
            description=getattr(process, 'abstract', ''),
            url='{base_url}/providers/{provider_name}/processes/{process_id}'.format(
                base_url=restapi_base_url(request),
                provider_name=provider_name,
                process_id=process.identifier))
        processes.append(item)
    return processes


def jsonify(value):
    # ComplexData type
    if isinstance(value, ComplexData):
        return value.mimeType
    # other type
    else:
        return value


@view_config(route_name='process', request_method='GET', renderer='json')
def describe_process(request):
    """
    Retrieve a process description
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')

    service = store.fetch_by_name(provider_name)
    wps = WebProcessingService(url=service.url)
    process = wps.describeprocess(process_id)
    inputs = [dict(
        id=getattr(dataInput, 'identifier', ''),
        label=getattr(dataInput, 'title', ''),
        # TODO How should we handle type litteral versus complex
        type=[jsonify(value) for value in getattr(dataInput, 'supportedValues', [dataInput.dataType])],
        required=getattr(dataInput, 'minOccurs', 0) > 0,
        maxOccurs=getattr(dataInput, 'maxOccurs', 0),
        defaultValue=jsonify(getattr(dataInput, 'defaultValue', None)),
        allowedValues=[jsonify(value) for value in getattr(dataInput, 'allowedValues', [])]
    ) for dataInput in getattr(process, 'dataInputs', [])]
    outputs = [dict(
        id=getattr(processOutput, 'identifier', ''),
        label=getattr(processOutput, 'title', ''),
        # TODO How should we handle type litteral versus complex
        type=[processOutput.defaultValue.mimeType if processOutput.dataType == 'ComplexData'
              else processOutput.dataType]
    ) for processOutput in getattr(process, 'processOutputs', [])]
    return dict(
        id=process_id,
        label=getattr(process, 'title', ''),
        description=getattr(process, 'abstract', ''),
        inputs = inputs,
        outputs = outputs
    )


@view_config(route_name='process', request_method='POST')
def submit_job(request):
    """
    Execute a process. Parameters: ?sync-execute=true|false (false being the default value)
    """
    # TODO Validate param somehow
    provider_name = request.matchdict.get('provider_name')
    process_id = request.matchdict.get('process_id')
