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
    store = servicestore_factory(request.registry, headers=request.headers)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')

    service = store.fetch_by_name(provider_id)
    wps = WebProcessingService(url=service.url, headers=request.headers)
    processes = []
    for process in wps.processes:
        item = dict(
            id=process.identifier,
            title=getattr(process, 'title', ''),
            abstract=getattr(process, 'abstract', ''),
            url='{base_url}/providers/{provider_id}/processes/{process_id}'.format(
                base_url=restapi_base_url(request),
                provider_id=provider_id,
                process_id=process.identifier))
        processes.append(item)
    return processes


def jsonify(value):
    # ComplexData type
    if isinstance(value, ComplexData):
        return {'mimeType': value.mimeType, 'encoding': value.encoding, 'schema': value.schema}
    # other type
    else:
        return value


@view_config(route_name='process', request_method='GET', renderer='json')
def describe_process(request):
    """
    Retrieve a process description
    """
    store = servicestore_factory(request.registry, headers=request.headers)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')

    service = store.fetch_by_name(provider_id)
    wps = WebProcessingService(url=service.url, headers=request.headers)
    process = wps.describeprocess(process_id)

    inputs = [dict(
        id=getattr(dataInput, 'identifier', ''),
        title=getattr(dataInput, 'title', ''),
        abstract=getattr(dataInput, 'abstract', ''),
        minOccurs=getattr(dataInput, 'minOccurs', 0),
        maxOccurs=getattr(dataInput, 'maxOccurs', 0),
        dataType=dataInput.dataType,
        defaultValue=jsonify(getattr(dataInput, 'defaultValue', None)),
        allowedValues=[jsonify(value) for value in getattr(dataInput, 'allowedValues', [])],
        supportedValues=[jsonify(value) for value in getattr(dataInput, 'supportedValues', [])],
    ) for dataInput in getattr(process, 'dataInputs', [])]
    outputs = [dict(
        id=getattr(processOutput, 'identifier', ''),
        title=getattr(processOutput, 'title', ''),
        abstract=getattr(processOutput, 'abstract', ''),
        dataType=processOutput.dataType,
        defaultValue=jsonify(getattr(processOutput, 'defaultValue', None))
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
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
