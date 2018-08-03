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
from twitcher.utils import parse_request_query
from collections import OrderedDict
import json
import yaml
import tempfile
import shutil

import logging
LOGGER = logging.getLogger("PYWPS")


WORKFLOW_EXTENSIONS = frozenset(['yaml', 'yml', 'json', 'cwl', 'job'])


def check_workflow_file(cwl_file):
    cwl_path = os.path.abspath(cwl_file)
    file_ext = os.path.splitext(cwl_path)[1].replace('.', '')
    if file_ext not in WORKFLOW_EXTENSIONS:
        raise Exception("Not a valid CWL file type: `{}`.".format(file_ext))
    if not os.path.isfile(cwl_path):
        raise Exception("Cannot find CWL file at: `{}`.".format(cwl_path))
    return cwl_path


def load_workflow_file(file_path):
    file_path = check_workflow_file(file_path)
    # yaml properly loads json as well
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


def load_workflow_content(workflow_dict):
    # TODO: find how to pass dict directly (?) instead of dump to tmp file
    tmp_dir = tempfile.mkdtemp()
    tmp_json_cwl = os.path.join(tmp_dir, 'cwl.cwl')
    with open(tmp_json_cwl, 'w') as f:
        json.dump(workflow_dict, f)
    cwl_factory = cwltool.factory.Factory()
    workflow = cwl_factory.make(tmp_json_cwl)
    shutil.rmtree(tmp_dir)
    return workflow


class Workflow(Process):
    workflow = None
    job_file = None
    tmp_dir = None

    def __init__(self, **kw):
        package = kw.pop('package')
        if not package:
            raise Exception("Missing required package definition for workflow process.")
        if isinstance(package, dict):
            self.workflow = load_workflow_content(package)
        else:
            raise TypeError("Unknown parsing of package definition for workflow process.")

        wps_inputs = kw.pop('inputs')
        wps_outputs = kw.pop('outputs')
        cwl_inputs = self._get_workflow_inputs()
        cwl_outputs = self._get_workflow_outputs()

        super(Workflow, self).__init__(
            self._handler,
            inputs=self._update_workflow_io(wps_inputs, cwl_inputs),
            outputs=self._update_workflow_io(wps_outputs, cwl_outputs),
            store_supported=True,
            status_supported=True,
            **kw
        )

    @staticmethod
    def _cwl2wps_io(io_info):
        """Converts input/output parameters from CWL types to WPS types.
        :param io_info: parsed IO of a CWL file
        :return: corresponding IO in WPS format
        """
        is_input = False
        is_output = False
        if 'inputBinding' in io_info:
            is_input = True
            io_literal = LiteralInput
            io_complex = ComplexInput
            io_bbox = BoundingBoxInput
        elif 'outputBinding' in io_info:
            is_output = True
            io_literal = LiteralOutput
            io_complex = ComplexOutput
            io_bbox = BoundingBoxOutput
        else:
            raise Exception("Unsupported I/O info definition: `{}`.".format(repr(io_info)))

        io_name = io_info['name']
        io_type = io_info['type']

        # literal types
        if io_type in ['string', 'boolean', 'float', 'int', 'long', 'double', 'null', 'Any']:
            if io_type == 'Any':
                io_type = 'anyvalue'
            if io_type == 'null':
                io_type = 'novalue'
            if io_type == 'int':
                io_type = 'integer'
            if io_type in ['float', 'long', 'double']:
                io_type = 'float'
            return io_literal(identifier=io_name,
                              title=io_info.get('label', io_name),
                              abstract=io_info.get('doc', ''),
                              data_type=io_type,
                              default=io_info.get('default', None),
                              min_occurs=1, max_occurs=1)
        # complex types
        else:
            kw = {
                'identifier': io_name,
                'title': io_info.get('label', io_name),
                'abstract': io_info.get('doc', ''),
                'supported_formats': [Format(io_info.get('format', 'text/plain'))]
            }
            if is_output:
                if io_type == 'Directory':
                    kw['as_reference'] = True
                if io_type == 'File':
                    has_contents = io_info.get('contents') is not None
                    kw['as_reference'] = False if has_contents else True
            return io_complex(**kw)

    @staticmethod
    def _update_workflow_io(wps_io_list, cwl_io_list):
        """
        Update I/O definitions to use for process creation and returned by GetCapabilities, DescribeProcess.
        If WPS I/O definitions where provided during deployment, update them with CWL-to-WPS converted I/O and
        preserve their optional WPS fields. Otherwise, provided minimum field requirements from CWL.
        Adds and removes any deployment WPS I/O definitions that don't match any CWL I/O by id.

        :param wps_io_list: list of WPS I/O passed during process deployment.
        :param cwl_io_list: list of CWL I/O converted to WPS-like I/O for counter-validation.
        :returns: list of validated/updated WPS I/O for the process.
        """
        if not cwl_io_list:
            raise Exception("CWL I/O definitions must be provided, empty list if none required.")
        if not wps_io_list:
            wps_io_list = list()
        wps_io_dict = OrderedDict((wps_io.identifier, wps_io) for wps_io in wps_io_list)
        cwl_io_dict = OrderedDict((cwl_io.identifier, cwl_io) for cwl_io in cwl_io_list)
        missing_io_list = set(cwl_io_dict) - set(wps_io_dict)
        updated_io_list = list()
        for cwl_id in missing_io_list:
            updated_io_list.append(cwl_io_dict[cwl_id])
        for wps_io in wps_io_list:
            wps_id = wps_io.identifier
            # WPS I/O by id not matching CWL I/O are discarded
            if wps_id in wps_io_dict:
                # retrieve any additional fields (metadata, keywords, etc.) passed as input,
                # but override CWL-converted types and formats
                if hasattr(wps_io, 'data_type'):
                    wps_io.data_type = cwl_io_dict[wps_id].data_type
                updated_io_list.append(wps_io)
        return updated_io_list

    def _get_workflow_inputs(self):
        """Generates WPS-like inputs using parsed CWL workflow input definitions."""
        return [self._cwl2wps_io(i) for i in self.workflow.t.inputs_record_schema['fields']]

    def _get_workflow_outputs(self):
        """Generates WPS-like outputs using parsed CWL workflow output definitions."""
        return [self._cwl2wps_io(o) for o in self.workflow.t.outputs_record_schema['fields']]

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
