import os
import cwltool
import cwltool.factory
from pywps import Process, LiteralInput, LiteralOutput, ComplexInput, ComplexOutput, Format
from pywps.app.Common import Metadata
from six import string_types
import json
import yaml

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


class Workflow(Process):
    workflow = None
    cwl_file = None
    job_file = None

    def __init__(self, **kw):
        package = kw.pop('package')
        if not package:
            raise Exception("missing required package definition for workflow process")
        if isinstance(package, string_types):
            self.cwl_file = self._check_cwl(package)
            cwl_factory = cwltool.factory.Factory()
            self.workflow = cwl_factory.make(self.cwl_file)
        elif isinstance(package, dict):
            raise NotImplementedError("workflow.dict")  # TODO
        else:
            raise Exception("unkwown parsing of package definition for workflow process")

        kw.pop('type')
        kw.pop('inputs')
        kw.pop('outputs')
        super(Workflow, self).__init__(
            self._handler,
            #identifier='workflow',
            #title='Runs a workflow from a CWL definition',
            #version='0.1',
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
        return []

    def _get_outputs(self):
        return []

    def _handler(self, request, response):
        response.update_status("Launching workflow ...", 0)
        LOGGER.debug("HOME=%s, Current Dir=%s", os.environ.get('HOME'), os.path.abspath(os.curdir))
        LOGGER.debug("Workflow Path=%s", self.cwl_file)
        #response.outputs['output'].data = 'Workflow: {}'.format(self.cwl_file)
        return response
