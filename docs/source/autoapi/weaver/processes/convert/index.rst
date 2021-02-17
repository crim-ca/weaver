:mod:`weaver.processes.convert`
===============================

.. py:module:: weaver.processes.convert


Module Contents
---------------

.. data:: WPS_Input_Type
   

   

.. data:: PACKAGE_BASE_TYPES
   

   

.. data:: PACKAGE_LITERAL_TYPES
   

   

.. data:: PACKAGE_COMPLEX_TYPES
   

   

.. data:: PACKAGE_ARRAY_BASE
   :annotation: = array

   

.. data:: PACKAGE_ARRAY_MAX_SIZE
   

   

.. data:: PACKAGE_CUSTOM_TYPES
   

   

.. data:: PACKAGE_ARRAY_ITEMS
   

   

.. data:: PACKAGE_ARRAY_TYPES
   

   

.. data:: WPS_FIELD_MAPPING
   

   

.. data:: WPS_FIELD_FORMAT
   :annotation: = ['formats', 'supported_formats', 'supported_values', 'default']

   

.. data:: WPS_COMPLEX_TYPES
   

   

.. data:: WPS_ALL_TYPES
   

   

.. data:: DEFAULT_FORMAT
   

   

.. data:: DEFAULT_FORMAT_MISSING
   :annotation: = __DEFAULT_FORMAT_MISSING__

   

.. data:: LOGGER
   

   

.. function:: complex2json(data: Union[ComplexData, Any]) -> Union[JSON, Any]

   Obtains the JSON representation of a :class:`ComplexData` or simply return the unmatched type.


.. function:: metadata2json(meta: Union[ANY_Metadata_Type, Any], force: bool = False) -> Union[JSON, Any]

   Obtains the JSON representation of a :class:`OWS_Metadata` or :class:`pywps.app.Common.Metadata`.
   Otherwise, simply return the unmatched type.
   If requested, can enforce parsing a dictionary for the corresponding keys.


.. function:: ows2json_field(ows_field: Union[ComplexData, OWS_Metadata, AnyValueType]) -> Union[JSON, AnyValueType]

   Obtains the JSON or raw value from an :mod:`owslib.wps` I/O field.


.. function:: ows2json_io(ows_io: OWS_IO_Type) -> JSON_IO_Type

   Converts I/O from :mod:`owslib.wps` to JSON.


.. function:: ows2json_io_FIXME(ows_io: OWS_IO_Type) -> JSON_IO_Type


.. function:: ows2json_output(output: OWS_Output_Type, process_description: ProcessOWS, container: Optional[AnySettingsContainer] = None) -> JSON

   Utility method to jsonify an output element from a WPS1 process description.

   In the case that a reference JSON output is specified and that it refers to a file that contains an array list of
   URL references to simulate a multiple-output, this specific output gets expanded to contain both the original
   URL ``reference`` field and the loaded URL list under ``data`` field for easier access from the response body.


.. function:: _get_multi_json_references(output: OWS_Output_Type, container: Optional[AnySettingsContainer]) -> Optional[List[JSON]]

   Since WPS standard does not allow to return multiple values for a single output,
   a lot of process actually return a JSON array containing references to these outputs.

   Because the multi-output references are contained within this JSON file, it is not very convenient to retrieve
   the list of URLs as one always needs to open and read the file to get them. This function goal is to detect this
   particular format and expand the references to make them quickly available in the job output response.

   :return:
       Array of HTTP(S) references if the specified output is effectively a JSON containing that, ``None`` otherwise.


.. function:: any2cwl_io(wps_io: Union[JSON_IO_Type, WPS_IO_Type, OWS_IO_Type], io_select: str) -> Tuple[CWL_IO_Type, Dict[str, str]]

   Converts a `WPS`-like I/O to `CWL` corresponding I/O.
   Because of `CWL` I/O of type `File` with `format` field, the applicable namespace is also returned.

   :returns: converted I/O and namespace dictionary with corresponding format references as required


.. function:: xml_wps2cwl(wps_process_response: Response) -> Tuple[CWL, JSON]

   Converts a `WPS-1 ProcessDescription XML` tree structure to an equivalent `WPS-3 Process JSON` and builds the
   associated `CWL` package in conformance to :ref:`weaver.processes.wps_package.CWL_REQUIREMENT_APP_WPS1`.

   :param wps_process_response: valid response (XML, 200) from a `WPS-1 ProcessDescription`.


.. function:: is_cwl_array_type(io_info: CWL_IO_Type) -> Tuple[bool, str, MODE, Union[AnyValue, List[Any]]]

   Verifies if the specified I/O corresponds to one of various CWL array type definitions.

   returns ``tuple(is_array, io_type, io_mode, io_allow)`` where:
       - ``is_array``: specifies if the I/O is of array type.
       - ``io_type``: array element type if ``is_array`` is True, type of ``io_info`` otherwise.
       - ``io_mode``: validation mode to be applied if sub-element requires it, defaults to ``MODE.NONE``.
       - ``io_allow``: validation values to be applied if sub-element requires it, defaults to ``AnyValue``.
   :raises PackageTypeError: if the array element doesn't have the required values and valid format.


.. function:: is_cwl_enum_type(io_info: CWL_IO_Type) -> Tuple[bool, str, int, Union[List[str], None]]

   Verifies if the specified I/O corresponds to a CWL enum definition.

   returns ``tuple(is_enum, io_type, io_allow)`` where:
       - ``is_enum``: specifies if the I/O is of enum type.
       - ``io_type``: enum base type if ``is_enum=True``, type of ``io_info`` otherwise.
       - ``io_mode``: validation mode to be applied if input requires it, defaults to ``MODE.NONE``.
       - ``io_allow``: validation values of the enum.
   :raises PackageTypeError: if the enum doesn't have the required parameters and valid format.


.. function:: cwl2wps_io(io_info: CWL_IO_Type, io_select: str) -> WPS_IO_Type

   Converts input/output parameters from CWL types to WPS types.

   :param io_info: parsed IO of a CWL file
   :param io_select: ``WPS_INPUT`` or ``WPS_OUTPUT`` to specify desired WPS type conversion.
   :returns: corresponding IO in WPS format


.. function:: any2cwl_literal_datatype(io_type: str) -> Union[str, Type[null]]

   Solves common literal data-type names to supported ones for `CWL`.


.. function:: any2wps_literal_datatype(io_type: AnyValueType, is_value: bool) -> Union[str, Type[null]]

   Solves common literal data-type names to supported ones for `WPS`.
   Verification is accomplished by name when ``is_value=False``, otherwise with python ``type`` when ``is_value=True``.


.. function:: json2wps_datatype(io_info: JSON_IO_Type) -> str

   Guesses the literal data-type from I/O JSON information in order to allow creation of the corresponding I/O WPS.
   Defaults to ``string`` if no suitable guess can be accomplished.


.. function:: json2wps_field(field_info: JSON_IO_Type, field_category: str) -> Any

   Converts an I/O field from a JSON literal data, list, or dictionary to corresponding WPS types.

   :param field_info: literal data or information container describing the type to be generated.
   :param field_category: one of ``WPS_FIELD_MAPPING`` keys to indicate how to parse ``field_info``.


.. function:: json2wps_io(io_info: JSON_IO_Type, io_select: Union[WPS_INPUT, WPS_OUTPUT]) -> WPS_IO_Type

   Converts an I/O from a JSON dict to PyWPS types.

   :param io_info: I/O in JSON dict format.
   :param io_select: ``WPS_INPUT`` or ``WPS_OUTPUT`` to specify desired WPS type conversion.
   :return: corresponding I/O in WPS format.


.. function:: wps2json_io(io_wps: WPS_IO_Type) -> JSON_IO_Type

   Converts a PyWPS I/O into a dictionary based version with keys corresponding to standard names (WPS 2.0).


.. function:: wps2json_job_payload(wps_request: WPSRequest, wps_process: ProcessWPS) -> JSON

   Converts the input and output values of a :mod:`pywps` WPS ``Execute`` request to corresponding WPS-REST job.

   The inputs and outputs must be parsed from XML POST payload or KVP GET query parameters, and converted to data
   container defined by :mod:`pywps` based on the process definition.


.. function:: get_field(io_object: Union[ANY_IO_Type, ANY_Format_Type], field: str, search_variations: bool = False, pop_found: bool = False, default: Any = null) -> Any

   Gets a field by name from various I/O object types.

   Default value is :py:data:`null` used for most situations to differentiate from
   literal ``None`` which is often used as default for parameters. The :class:`NullType`
   allows to explicitly tell that there was 'no field' and not 'no value' in existing
   field. If you provided another value, it will be returned if not found within
   the input object.

   :returns: matched value (including search variations if enabled), or ``default``.


.. function:: set_field(io_object: Union[ANY_IO_Type, ANY_Format_Type], field: str, value: Any, force: bool = False) -> None

   Sets a field by name into various I/O object types.
   Field value is set only if not ``null`` to avoid inserting data considered `invalid`.
   If ``force=True``, verification of ``null`` value is ignored.


.. function:: _are_different_and_set(item1: Any, item2: Any) -> bool

   Compares two value representations and returns ``True`` only if both are not ``null``, are of same ``type`` and
   of different representative value. By "representative", we consider here the visual representation of byte/unicode
   strings to support XML/JSON and Python 2/3 implementations. Other non string-like types are verified with
   literal (usual) equality method.


.. function:: is_equal_formats(format1: Union[Format, JSON], format2: Union[Format, JSON]) -> bool

   Verifies for matching formats.


.. function:: merge_io_formats(wps_formats: List[ANY_Format_Type], cwl_formats: List[ANY_Format_Type]) -> List[ANY_Format_Type]

   Merges I/O format definitions by matching ``mime-type`` field.
   In case of conflict, preserve the WPS version which can be more detailed (for example, by specifying ``encoding``).

   Verifies if ``DEFAULT_FORMAT_MISSING`` was written to a single `CWL` format caused by a lack of any value
   provided as input. In this case, *only* `WPS` formats are kept.

   In the event that ``DEFAULT_FORMAT_MISSING`` was written to the `CWL` formats and that no `WPS` format was
   specified, the :py:data:`DEFAULT_FORMAT` is returned.

   :raises PackageTypeError: if inputs are invalid format lists


.. function:: merge_package_io(wps_io_list: List[ANY_IO_Type], cwl_io_list: List[WPS_IO_Type], io_select: Union[WPS_INPUT, WPS_OUTPUT]) -> List[WPS_IO_Type]

   Update I/O definitions to use for process creation and returned by GetCapabilities, DescribeProcess.
   If WPS I/O definitions where provided during deployment, update `CWL-to-WPS` converted I/O with the WPS I/O
   complementary details. Otherwise, provide minimum field requirements that can be retrieved from CWL definitions.

   Removes any deployment WPS I/O definitions that don't match any CWL I/O by ID.
   Adds missing deployment WPS I/O definitions using expected CWL I/O IDs.

   :param wps_io_list: list of WPS I/O (as json) passed during process deployment.
   :param cwl_io_list: list of CWL I/O converted to WPS-like I/O for counter-validation.
   :param io_select: ``WPS_INPUT`` or ``WPS_OUTPUT`` to specify desired WPS type conversion.
   :returns: list of validated/updated WPS I/O for the process matching CWL I/O requirements.


.. function:: transform_json(json_data: ANY_IO_Type, rename: Optional[Dict[AnyKey, Any]] = None, remove: Optional[List[AnyKey]] = None, add: Optional[Dict[AnyKey, Any]] = None, replace_values: Optional[Dict[AnyKey, Any]] = None, replace_func: Optional[Dict[AnyKey, Callable[[Any], Any]]] = None) -> ANY_IO_Type

   Transforms the input json_data with different methods.
   The transformations are applied in the same order as the arguments.


