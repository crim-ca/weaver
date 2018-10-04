import json
from twitcher.cwl_wps_workflows.wps_process import WpsProcess
from twitcher.cwl_wps_workflows.wps_workflow import default_make_tool
from cwltool.context import LoadingContext

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