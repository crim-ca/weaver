import os
import cwltool
import cwltool.factory
from pywps import (
    Process,
    LiteralInput,
    LiteralOutput,
    ComplexInput,
    ComplexOutput,
    BoundingBoxInput,
    BoundingBoxOutput,
    Format,
)
from pywps.app.Common import Metadata
from six import string_types
from six.moves.urllib.parse import urlparse, parse_qs
import json
import yaml
import tempfile
import shutil

import logging
LOGGER = logging.getLogger("PYWPS")


def load_file(file_path):
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        raise Exception("missing file: {}".format(file_path))
    file_ext = os.path.splitext(file_path)[1].replace('.', '')
    if file_ext in ['yaml', 'yml', 'json', 'cwl', 'job']:
        # yaml properly loads json as well
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    raise Exception("unsupported file type: {}".format(file_ext))


def parse_request_query(request):
    queries = parse_qs(urlparse(request.url).query)
    queries_lower = dict()
    for q in queries:
        ql = q.lower()
        if ql in queries_lower:
            queries_lower[ql].extend(queries[q])
        else:
            queries_lower.update({ql: list(queries[q])})
    data_inputs = queries_lower.get('datainputs', {})
    if isinstance(data_inputs, dict):
        return data_inputs
    dict_data_inputs = dict()
    for di in data_inputs:
        k, v = di.split('=')
        dict_data_inputs.update({k: v})
    return dict_data_inputs


def cwl2wps_io(io_info):
    """Converts input/output parameters from CWL types to WPS types.
    :param io_info: parsed IO of a CWL file
    :return: corresponding IO in WPS format
    """
    return []


class Workflow(Process):
    workflow = None
    cwl_file = None
    job_file = None
    tmp_dir = None

    def __init__(self, **kw):
        package = kw.pop('package')
        reference = kw.pop('reference')
        if not (package or reference):
            raise Exception("missing required package/reference definition for workflow process")
        if isinstance(reference, string_types):
            self.cwl_file = self._check_cwl(reference)
            cwl_factory = cwltool.factory.Factory()
            self.workflow = cwl_factory.make(self.cwl_file)
        elif isinstance(package, dict):
            # TODO: find how to pass dict directly (?) instead of dump to tmp file
            self.tmp_dir = tempfile.mkdtemp()
            tmp_json_cwl = os.path.join(self.tmp_dir, 'cwl.cwl')
            with open(tmp_json_cwl, 'w') as f:
                json.dump(package, f)
            cwl_factory = cwltool.factory.Factory()
            self.workflow = cwl_factory.make(tmp_json_cwl)
            shutil.rmtree(self.tmp_dir)
        else:
            raise Exception("unknown parsing of package/reference definition for workflow process")

        # I/O are fetch from CWL definition
        kw.pop('inputs')
        kw.pop('outputs')
        super(Workflow, self).__init__(
            self._handler,
            inputs=self._get_inputs(),
            outputs=self._get_outputs(),
            store_supported=True,
            status_supported=True,
            **kw
        )

    def _check_cwl(self, cwl_file):
        cwl_path = os.path.abspath(cwl_file)
        if not cwl_path.endswith('.cwl'):
            raise Exception("Not a valid CWL file: {}".format(cwl_path))
        if not os.path.isfile(cwl_path):
            raise Exception("Cannot find CWL file at: {}".format(cwl_path))
        return cwl_path

    def _get_inputs(self):
        return [cwl2wps_io(i) for i in self.workflow.t.inputs_record_schema]

    def _get_outputs(self):
        return [cwl2wps_io(o) for o in self.workflow.t.outputs_record_schema]

    def _handler(self, request, response):
        response.update_status("Launching workflow ...", 0)
        LOGGER.debug("HOME=%s, Current Dir=%s", os.environ.get('HOME'), os.path.abspath(os.curdir))

        # input parameters from JSON body for WPS 2.0
        if request.content_type == 'application/json':
            data_inputs = request.json
        # input parameters from request query from WPS 1.0
        else:
            data_inputs = parse_request_query(request)
        self.workflow(**data_inputs)

        #response.outputs['output'].data = 'Workflow: {}'.format(self.cwl_file)
        return response
