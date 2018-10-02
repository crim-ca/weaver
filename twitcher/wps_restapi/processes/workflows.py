import json
import cwltool
from cwltool import factory
from cwltool.context import LoadingContext
from owslib.wps import ComplexDataInput
from twitcher.cwl_wps_workflows.wps_process import WpsProcess
from twitcher.cwl_wps_workflows.wps_workflow import default_make_tool
from twitcher.utils import get_any_id
from twitcher.adapter import processstore_factory
from pyramid_celery import celery_app as app


def get_step_process_definition(step_id, data_source):
    cookie = {
        'auth_tkt': 'd7890d6644880ae5ca30c6663b345694b5b90073d3dec2a6925e888b37d3211aa10168d15b441ef2d2cd8f70064519fda06fb526a26f1d8740a5496c07233c505b8715e536!userid_type:int;',
        'path': '/;', 'domain': '.ogc-ems.crim.ca;', 'Expires': 'Tue, 19 Jan 2038 03:14:07 GMT;'}
    url = 'https://ogc-ades.crim.ca/twitcher/processes/'
    if step_id == 'stack_creation':
        with open('example/StackCreation-graph-deploy.json') as json_file:
            deploy_json_body = json.load(json_file)
        return WpsProcess(url=url, process_id='stack_creation_graph', deploy_body=deploy_json_body, cookies=cookie)
    if step_id == 'sfs':
        with open('example/SFS-graph-deploy.json') as json_file:
            deploy_json_body = json.load(json_file)
        return WpsProcess(url=url, process_id='sfs_graph', deploy_body=deploy_json_body, cookies=cookie)
        # raise exception or handle undefined step?


def make_tool(toolpath_object,  # type: Dict[Text, Any]
              loadingContext  # type: LoadingContext
              ):  # type: (...) -> Process
    return default_make_tool(toolpath_object, loadingContext, get_step_process_definition)


def execute_workflow(job, url, process_id, inputs, headers):
    try:
        jsonInput = {}
        for process_input in inputs:
            input_id = get_any_id(process_input)
            process_value = process_input['value']
            # in case of array inputs, must repeat (id,value)
            input_values = process_value if isinstance(process_value, list) else [process_value]
            # need to use ComplexDataInput structure for complex input
            jsonInput.extend(
                [(input_id, ComplexDataInput(input_value) if input_id in complex_inputs else input_value)
                 for input_value in input_values])

        wps_inputs = list()
        for process_input in inputs:
            input_id = get_any_id(process_input)
            process_value = process_input['value']
            # in case of array inputs, must repeat (id,value)
            input_values = process_value if isinstance(process_value, list) else [process_value]
            # need to use ComplexDataInput structure for complex input
            wps_inputs.extend(
                [(input_id, ComplexDataInput(input_value) if input_id in complex_inputs else input_value)
                 for input_value in input_values])

    except KeyError:
        jsonInput = {}

    registry = app.conf['PYRAMID_REGISTRY']
    store = processstore_factory(registry)
    process = store.fetch_by_id(process_id)


    loading_context = LoadingContext()
    loading_context.construct_tool_object = make_tool
    factory = cwltool.factory.Factory(loading_context=loading_context)

    #with open('example/Workflow-json-zip.job') as json_file:
    #    jsonInput = json.load(json_file)

    # cwlFile = "example/workflow_stacker_sfs.cwl"
    #workflow = factory.make(cwlFile)
    workflow = factory.make(process.package)
    workflow(input_files=jsonInput['files'], output_name=jsonInput['output_name'],
             output_type=jsonInput['output_file_type'])
