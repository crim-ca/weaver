import os
import six
import cwltool
import cwltool.factory
from cwltool.context import RuntimeContext
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
from pywps.response.status import WPS_STATUS
from pywps.inout.literaltypes import AnyValue, AllowedValue
from pywps.validator.mode import MODE
from pywps.validator.literalvalidator import validate_anyvalue, validate_allowed_values
from pywps.app.Common import Metadata
from twitcher.utils import parse_request_query, get_any_id
from twitcher.exceptions import PackageTypeError, PackageRegistrationError, PackageExecutionError
from collections import OrderedDict
import json
import yaml
import tempfile
import mimetypes
import shutil

import logging
LOGGER = logging.getLogger("PYWPS")


__all__ = ['Package', 'get_process_from_wps_request']


PACKAGE_EXTENSIONS = frozenset(['yaml', 'yml', 'json', 'cwl', 'job'])
PACKAGE_BASE_TYPES = frozenset(['string', 'boolean', 'float', 'int', 'integer', 'long', 'double'])
PACKAGE_LITERAL_TYPES = frozenset(list(PACKAGE_BASE_TYPES) + ['null', 'Any'])
PACKAGE_COMPLEX_TYPES = frozenset(['File', 'Directory'])
PACKAGE_ARRAY_BASE = 'array'
PACKAGE_ARRAY_MAX_SIZE = six.MAXSIZE   # pywps doesn't allow None, so use max size
PACKAGE_ARRAY_ITEMS = frozenset(list(PACKAGE_BASE_TYPES) + list(PACKAGE_COMPLEX_TYPES))
PACKAGE_ARRAY_TYPES = frozenset(['{}[]'.format(item) for item in PACKAGE_ARRAY_ITEMS])
PACKAGE_CUSTOM_TYPES = frozenset(['enum'])  # can be anything, but support 'enum' which is more common
PACKAGE_FILE_NAME = 'workflow.cwl'
PACKAGE_LOG_FILE = 'workflow_log_file'


def _check_package_file(cwl_file):
    cwl_path = os.path.abspath(cwl_file)
    file_ext = os.path.splitext(cwl_path)[1].replace('.', '')
    if file_ext not in PACKAGE_EXTENSIONS:
        raise PackageRegistrationError("Not a valid CWL file type: `{}`.".format(file_ext))
    if not os.path.isfile(cwl_path):
        raise PackageRegistrationError("Cannot find CWL file at: `{}`.".format(cwl_path))
    return cwl_path


def _load_package_file(file_path):
    file_path = _check_package_file(file_path)
    # yaml properly loads json as well
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


def _load_package_content(package_dict):
    # TODO: find how to pass dict directly (?) instead of dump to tmp file
    tmp_dir = tempfile.mkdtemp()
    tmp_json_cwl = os.path.join(tmp_dir, PACKAGE_FILE_NAME)
    with open(tmp_json_cwl, 'w') as f:
        json.dump(package_dict, f)
    cwl_factory = cwltool.factory.Factory(runtime_context=RuntimeContext(kwargs={'no_read_only': True}))
    package = cwl_factory.make(tmp_json_cwl)
    shutil.rmtree(tmp_dir)
    return package


def _is_cwl_array_type(io_info):
    """Verifies if the specified input/output corresponds to one of various CWL array type definitions.

    :return is_array: bool - specifies if the input/output is of array type
    :return io_type: str - array element type if ``is_array`` is True, type of ``io_info`` otherwise.
    :raise PackageTypeError: if the array element is not supported.
    """
    is_array = False
    io_type = io_info['type']
    # array type conversion when defined as dict of {'type': 'array', 'items': '<type>'}
    if isinstance(io_type, dict) and 'items' in io_type and 'type' in io_type:
        if not io_type['type'] == PACKAGE_ARRAY_BASE or io_type['items'] not in PACKAGE_ARRAY_ITEMS:
            raise PackageTypeError("Unsupported I/O 'array' definition: `{}`.".format(repr(io_info)))
        io_type = io_type['items']
        is_array = True
    # array type conversion when defined as string '<type>[]'
    elif isinstance(io_type, six.string_types) and io_type in PACKAGE_ARRAY_TYPES:
        io_type = io_type[:-2]  # remove []
        if io_type not in PACKAGE_ARRAY_ITEMS:
            raise PackageTypeError("Unsupported I/O 'array' definition: `{}`.".format(repr(io_info)))
        is_array = True
    return is_array, io_type


def _is_cwl_enum_type(io_info):
    """Verifies if the specified input/output corresponds to a CWL enum definition.

    :return is_enum: bool - specifies if the input/output is of enum type
    :return io_type: str - enum base type if ``is_enum`` is True, type of ``io_info`` otherwise.
    :return io_allow: list - permitted values of the enum
    :raise PackageTypeError: if the enum doesn't have required parameters to be valid.
    """
    io_type = io_info['type']
    if not isinstance(io_type, dict) or 'type' not in io_type or io_type['type'] not in PACKAGE_CUSTOM_TYPES:
        return False, io_type, None

    if 'symbols' not in io_type:
        raise PackageTypeError("Unsupported I/O 'enum' definition: `{}`.".format(repr(io_info)))
    io_allow = io_type['symbols']
    if not isinstance(io_allow, list) or len(io_allow) < 1:
        raise PackageTypeError("Invalid I/O 'enum.symbols' definition: `{}`.".format(repr(io_info)))

    # validate matching types in allowed symbols and convert to supported CWL type
    first_allow = io_allow[0]
    for e in io_allow:
        if type(e) is not type(first_allow):
            raise PackageTypeError("Ambiguous types in I/O 'enum.symbols' definition: `{}`.".format(repr(io_info)))
    if isinstance(first_allow, six.string_types):
        io_type = 'string'
    elif isinstance(first_allow, float):
        io_type = 'float'
    elif isinstance(first_allow, six.integer_types):
        io_type = 'int'
    else:
        raise PackageTypeError("Unsupported I/O 'enum' base type: `{0}`, from definition: `{1}`."
                               .format(str(type(first_allow)), repr(io_info)))

    return True, io_type, io_allow


def _cwl2wps_io(io_info):
    """Converts input/output parameters from CWL types to WPS types.
    :param io_info: parsed IO of a CWL file
    :returns: corresponding IO in WPS format
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
        raise PackageTypeError("Unsupported I/O info definition: `{}`.".format(repr(io_info)))

    io_name = io_info['name']
    io_type = io_info['type']
    io_min_occurs = 1
    io_max_occurs = 1
    io_allow = AnyValue
    io_mode = MODE.NONE

    # convert array types
    is_array, array_elem = _is_cwl_array_type(io_info)
    if is_array:
        io_type = array_elem
        io_max_occurs = PACKAGE_ARRAY_MAX_SIZE

    # convert enum types
    is_enum, enum_type, enum_allow = _is_cwl_enum_type(io_info)
    if is_enum:
        io_type = enum_type
        io_allow = enum_allow
        io_mode = MODE.SIMPLE   # allowed value validator must be set for input

    # literal types
    if io_type in PACKAGE_LITERAL_TYPES or is_enum:
        if io_type == 'Any':
            io_type = 'anyvalue'
        if io_type == 'null':
            io_type = 'novalue'
        if io_type in ['int', 'integer', 'long']:
            io_type = 'integer'
        if io_type in ['float', 'double']:
            io_type = 'float'
        return io_literal(identifier=io_name,
                          title=io_info.get('label', io_name),
                          abstract=io_info.get('doc', ''),
                          data_type=io_type,
                          default=io_info.get('default', None),
                          min_occurs=io_min_occurs, max_occurs=io_max_occurs,
                          # unless extended by custom types, no value validation for literals
                          mode=io_mode,
                          allowed_values=io_allow)
    # complex types
    else:
        kw = {
            'identifier': io_name,
            'title': io_info.get('label', io_name),
            'abstract': io_info.get('doc', ''),
        }
        if 'format' in io_info:
            kw['supported_formats'] = [Format(io_info['format'])]
            kw['mode'] = MODE.SIMPLE
        else:
            # we need to minimally add 1 format, otherwise empty list is evaluated as None by pywps
            # when 'supported_formats' is None, the process's json property raises because of it cannot iterate formats
            kw['supported_formats'] = [Format('text/plain')]
            kw['mode'] = MODE.NONE
        if is_output:
            if io_type == 'Directory':
                kw['as_reference'] = True
            if io_type == 'File':
                has_contents = io_info.get('contents') is not None
                kw['as_reference'] = False if has_contents else True
        else:
            kw.update({
                'min_occurs': io_min_occurs,
                'max_occurs': io_max_occurs,
            })
        return io_complex(**kw)


def _dict2wps_io(io_info, input_or_output):
    """Converts input/output parameters from a JSON dict to WPS types.
    :param io_info: IO in JSON dict format
    :param input_or_output: 'input' or 'output' to specified desired WPS type conversion.
    :return: corresponding IO in WPS format
    """
    # remove extra fields added by pywps
    io_info.pop('workdir', None)
    io_info.pop('any_value', None)
    io_info.pop('data_format', None)
    io_info.pop('data', None)
    io_info.pop('file', None)

    # convert allowed value objects
    values = io_info.pop('allowed_values', None)
    if values is not None:
        if isinstance(values, list) and len(values) > 0:
            io_info['allowed_values'] = list()
            for allow_value_dict in values:
                allow_value_dict.pop('type', None)
                io_info['allowed_values'].append(AllowedValue(**allow_value_dict))
        else:
            io_info['allowed_values'] = AnyValue

    # convert supported format objects
    formats = io_info.pop('supported_formats', None)
    if formats is not None:
        io_info['supported_formats'] = [Format(**fmt) for fmt in formats]

    # convert by type
    io_type = io_info.pop('type', 'complex')    # only ComplexData doesn't have 'type'
    if input_or_output == 'input':
        if io_type == 'complex':
            return ComplexInput(**io_info)
        if io_type == 'bbox':
            return BoundingBoxInput(**io_info)
        if io_type == 'literal':
            return LiteralInput(**io_info)
    elif input_or_output == 'output':
        # extra params to remove for outputs
        io_info.pop('min_occurs', None)
        io_info.pop('max_occurs', None)
        if io_type == 'complex':
            return ComplexOutput(**io_info)
        if io_type == 'bbox':
            return BoundingBoxOutput(**io_info)
        if io_type == 'literal':
            return LiteralOutput(**io_info)
    raise PackageTypeError("Unknown conversion from dict to WPS type (type={0}, mode={1})."
                           .format(io_type, input_or_output))


def _get_field(io_object, field):
    if isinstance(io_object, dict):
        return io_object.get(field, None)
    return getattr(io_object, field, None)


def _set_field(io_object, field, value):
    if isinstance(io_object, dict):
        io_object[field] = value
        return
    setattr(io_object, field, None)


def _merge_package_io(wps_io_list, cwl_io_list):
    """
    Update I/O definitions to use for process creation and returned by GetCapabilities, DescribeProcess.
    If WPS I/O definitions where provided during deployment, update them with CWL-to-WPS converted I/O and
    preserve their optional WPS fields. Otherwise, provided minimum field requirements from CWL.
    Adds and removes any deployment WPS I/O definitions that don't match any CWL I/O by id.

    :param wps_io_list: list of WPS I/O passed during process deployment.
    :param cwl_io_list: list of CWL I/O converted to WPS-like I/O for counter-validation.
    :returns: list of validated/updated WPS I/O for the process.
    """
    if not isinstance(cwl_io_list, list):
        raise PackageTypeError("CWL I/O definitions must be provided, empty list if none required.")
    if not wps_io_list:
        wps_io_list = list()
    wps_io_dict = OrderedDict((_get_field(wps_io, 'identifier'), wps_io) for wps_io in wps_io_list)
    cwl_io_dict = OrderedDict((_get_field(cwl_io, 'identifier'), cwl_io) for cwl_io in cwl_io_list)
    missing_io_list = set(cwl_io_dict) - set(wps_io_dict)
    updated_io_list = list()
    for cwl_id in missing_io_list:
        updated_io_list.append(cwl_io_dict[cwl_id])
    for wps_io in wps_io_list:
        wps_id = _get_field(wps_io, 'identifier')
        # WPS I/O by id not matching CWL I/O are discarded
        if wps_id in wps_io_dict:
            # retrieve any additional fields (metadata, keywords, etc.) passed as input,
            # but override CWL-converted types and formats
            if _get_field(wps_io, 'data_type') is not None:
                _set_field(wps_io, 'data_type', _get_field(cwl_io_dict[wps_id], 'data_type'))
            # update value and format validation already defined parameters during CWL package import
            allowed_values = _get_field(wps_io, 'allowed_values')
            if isinstance(allowed_values, list) and len(allowed_values) > 0:
                _set_field(wps_io, 'allowed_values', _get_field(cwl_io_dict[wps_id], 'allowed_values'))
            supported_formats = _get_field(wps_io, 'supported_formats')
            if isinstance(supported_formats, list) and len(supported_formats) > 0:
                _set_field(wps_io, 'supported_formats', _get_field(cwl_io_dict[wps_id], 'supported_formats'))
            updated_io_list.append(wps_io)
    return updated_io_list


def _merge_package_inputs_outputs(wps_inputs_list, cwl_inputs_list, wps_outputs_list, cwl_outputs_list, as_json=False):
    """Merges I/O definitions to use for process creation and returned by GetCapabilities, DescribeProcess
    using the WPS specifications (from request POST) and CWL specifications (extracted from file)."""
    wps_inputs = _merge_package_io(wps_inputs_list, cwl_inputs_list)
    wps_outputs = _merge_package_io(wps_outputs_list, cwl_outputs_list)
    if as_json:
        return [i.json for i in wps_inputs], [o.json for o in wps_outputs]
    return wps_inputs, wps_outputs


def _get_package_io(package, io_attrib, as_json):
    cwl_package_io = getattr(package.t, io_attrib)
    wps_package_io = [_cwl2wps_io(io) for io in cwl_package_io['fields']]
    if as_json:
        return [io.json for io in wps_package_io]
    return wps_package_io


def _get_package_inputs(package, as_json=False):
    """Generates WPS-like inputs using parsed CWL package input definitions."""
    return _get_package_io(package, io_attrib='inputs_record_schema', as_json=as_json)


def _get_package_outputs(package, as_json=False):
    """Generates WPS-like outputs using parsed CWL package output definitions."""
    return _get_package_io(package, io_attrib='outputs_record_schema', as_json=as_json)


def _get_package_inputs_outputs(package, as_json=False):
    """Generates WPS-like (inputs,outputs) tuple using parsed CWL package output definitions."""
    return _get_package_io(package, io_attrib='inputs_record_schema', as_json=as_json), \
           _get_package_io(package, io_attrib='outputs_record_schema', as_json=as_json)


def _update_package_metadata(wps_package_metadata, cwl_package_package):
    """Updates the package WPS metadata dictionary from extractable CWL package definition."""
    wps_package_metadata['title'] = wps_package_metadata.get('title', cwl_package_package.get('label', ''))
    wps_package_metadata['abstract'] = wps_package_metadata.get('abstract', cwl_package_package.get('doc', ''))

    if '$schemas' in cwl_package_package and isinstance(cwl_package_package['$schemas'], list) \
    and '$namespaces' in cwl_package_package and isinstance(cwl_package_package['$namespaces'], dict):
        metadata = wps_package_metadata.get('metadata', list())
        namespaces_inv = {v: k for k, v in cwl_package_package['$namespaces']}
        for schema in cwl_package_package['$schemas']:
            for namespace_url in namespaces_inv:
                if schema.startswith(namespace_url):
                    metadata.append({'title': namespaces_inv[namespace_url], 'href': schema})
        wps_package_metadata['metadata'] = metadata

    if 's:keywords' in cwl_package_package and isinstance(cwl_package_package['s:keywords'], list):
        wps_package_metadata['keywords'] = list(set(wps_package_metadata.get('keywords', list)) |
                                                set(cwl_package_package.get('s:keywords')))


def get_process_from_wps_request(process_offering, reference=None, package=None):
    if not (isinstance(package, dict) or isinstance(reference, six.string_types)):
        raise PackageRegistrationError(
            "Invalid parameters amongst one of [package,reference].")
    if package and reference:
        raise PackageRegistrationError(
            "Simultaneous parameters [package,reference] not allowed.")

    if reference:
        package = _load_package_file(reference)
    try:
        package = _load_package_content(package)
        package_inputs, package_outputs = _get_package_inputs_outputs(package)
        process_inputs = process_offering.get('inputs', list())
        process_outputs = process_offering.get('outputs', list())
        _update_package_metadata(process_offering, package)
        package_inputs, package_outputs = _merge_package_inputs_outputs(process_inputs, package_inputs,
                                                                        process_outputs, package_outputs, as_json=True)
        process_offering.update({'package': package, 'inputs': package_inputs, 'outputs': package_outputs})
        return process_offering
    except Exception as ex:
        msg = "Invalid package/reference definition. Loading generated error: `{}`".format(repr(ex))
        raise PackageRegistrationError(msg)


class Package(Process):
    package = None
    job_file = None
    log_file = None
    log_level = logging.INFO
    logger = None
    tmp_dir = None
    percent = None

    def __init__(self, **kw):
        """
        Creates a WPS Process instance to execute a CWL package definition.
        Process parameters should be loaded from an existing `twitcher.datatype.Process`
        instance generated using method `get_process_from_wps_request`.

        :param kw: dictionary corresponding to method `twitcher.datatype.Process.params_wps`
        """
        package = kw.pop('package')
        if not package:
            raise PackageRegistrationError("Missing required package definition for package process.")
        if not isinstance(package, dict):
            raise PackageRegistrationError("Unknown parsing of package definition for package process.")
        try:
            self.package = _load_package_content(package)
        except Exception as ex:
            raise PackageRegistrationError("Exception occurred on package instantiation: `{}`".format(repr(ex)))

        inputs = [_dict2wps_io(i, 'input') for i in kw.pop('inputs', list())]
        outputs = [_dict2wps_io(o, 'output') for o in kw.pop('outputs', list())]
        metadata = [Metadata(**meta_kw) for meta_kw in kw.pop('metadata', list())]

        # append a log output
        #outputs.append(ComplexOutput(PACKAGE_LOG_FILE, 'Package log file',
        #                             as_reference=True, supported_formats=[Format('text/plain')]))

        super(Package, self).__init__(
            self._handler,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            store_supported=True,
            status_supported=True,
            **kw
        )

    def setup_logger(self):
        # file logger for output
        self.log_file = os.path.abspath(os.path.join(tempfile.mkdtemp(), '{}.log'.format(self.package_id)))
        log_file_handler = logging.FileHandler(self.log_file)
        log_file_formatter = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s %(message)s')
        log_file_handler.setFormatter(log_file_formatter)

        # prepare package logger
        self.logger = logging.getLogger('wps_package.{}'.format(self.package_id))
        self.logger.addHandler(log_file_handler)
        self.logger.setLevel(self.log_level)

        # add CWL job and CWL runner logging to current package logger
        job_logger = logging.getLogger('job {}'.format(PACKAGE_FILE_NAME))
        job_logger.addHandler(log_file_handler)
        job_logger.setLevel(self.log_level)
        cwl_logger = logging.getLogger('cwltool')
        cwl_logger.addHandler(log_file_handler)
        cwl_logger.setLevel(self.log_level)

    def update_status(self, message, progress=None, status=WPS_STATUS.STARTED):
        self.percent = progress or self.percent or 0
        # pywps overrides 'status' by 'accepted' in 'update_status', so use the '_update_status' to enforce the status
        # using the protected method also avoids weird overrides of progress % on failure and final 'success' status
        self.response._update_status(status, message, self.percent)
        self.log_message(message)

    def log_message(self, message, level=logging.INFO):
        self.logger.log(level, message, exc_info=level > logging.INFO)

    def exception_message(self, exception_type, exception=None, message='no message'):
        exception_msg = ' [{}]'.format(repr(exception)) if isinstance(exception, Exception) else ''
        self.log_message('{0}: {1}{2}'.format(exception_type.__name__, message, exception_msg), logging.ERROR)
        return exception_type('{0}{1}'.format(message, exception_msg))

    def _handler(self, request, response):
        LOGGER.debug("HOME=%s, Current Dir=%s", os.environ.get('HOME'), os.path.abspath(os.curdir))
        self.request = request
        self.response = response
        self.package_id = self.request.identifier

        try:
            try:
                self.setup_logger()
                #self.response.outputs[PACKAGE_LOG_FILE].file = self.log_file
                #self.response.outputs[PACKAGE_LOG_FILE].as_reference = True
                self.update_status("Preparing package logs done.", 1)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed preparing package logging.")

            self.log_message("Package: {}".format(request.identifier))
            self.update_status("Launching package ...", 2)

            try:
                cwl_input_info = dict([(i['name'], i) for i in self.package.t.inputs_record_schema['fields']])
                self.update_status("Retrieve package inputs done.", 3)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed retrieving package input types.")
            try:
                cwl_inputs = dict()
                for i in request.inputs.values():
                    # at least 1 input since obtained from request body
                    input_id = i[0].identifier
                    input_data = i[0].data
                    input_type = cwl_input_info[input_id]['type']
                    is_array, elem_type = _is_cwl_array_type(cwl_input_info[input_id])
                    if is_array:
                        # array allow max_occur > 1
                        input_data = [j.data for j in i]
                        input_type = elem_type
                    if isinstance(i[0], (LiteralInput, BoundingBoxInput)):
                        cwl_inputs[input_id] = input_data
                    elif isinstance(i[0], ComplexInput):
                        if isinstance(input_data, list):
                            cwl_inputs[input_id] = [{'location': data, 'class': input_type} for data in input_data]
                        else:
                            cwl_inputs[input_id] = {'location': input_data, 'class': input_type}
                    else:
                        raise self.exception_message(PackageTypeError, None,
                                                     "Undefined package input for execution: {}.".format(type(i)))
                self.update_status("Convert package inputs done.", 4)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed to load package inputs.")
            try:
                self.update_status("Running package ...", 6)
                result = self.package(**cwl_inputs)
                self.update_status("Package execution done.", 95)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed package execution.")
            try:
                self.update_status("Package execution done.", 96)
                for output in request.outputs:
                    if 'location' in result[output]:
                        self.response.outputs[output].as_reference = True
                        self.response.outputs[output].file = result[output]['location'].replace('file://', '')
                    else:
                        self.response.outputs[output].data = result[output]
                self.update_status("Generate package outputs done.", 99)
            except Exception as exc:
                raise self.exception_message(PackageExecutionError, exc, "Failed to save package outputs.")
        except:
            # return log file location by status message since outputs are not obtained by WPS failed process
            error_msg = "Package completed with errors. Server logs: {}".format(self.log_file)
            self.update_status(error_msg, status=WPS_STATUS.FAILED)
            raise
        else:
            self.update_status("Package complete.", 100, status=WPS_STATUS.SUCCEEDED)
        return self.response
