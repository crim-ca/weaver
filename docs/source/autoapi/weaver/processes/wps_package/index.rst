:mod:`weaver.processes.wps_package`
===================================

.. py:module:: weaver.processes.wps_package

.. autoapi-nested-parse::

   Functions and classes that offer interoperability and conversion between corresponding elements defined as
   `CWL CommandLineTool/Workflow` and `WPS ProcessDescription` in order to generate `ADES/EMS Application Package`.

   .. seealso::
       - `CWL specification <https://www.commonwl.org/#Specification>`_
       - `WPS-1/2 schemas <http://schemas.opengis.net/wps/>`_
       - `WPS-REST schemas <https://github.com/opengeospatial/wps-rest-binding>`_
       - :mod:`weaver.wps_restapi.api` conformance details



Module Contents
---------------

.. data:: CWLRequirement
   

   

.. data:: LOGGER
   

   

.. data:: PACKAGE_DEFAULT_FILE_NAME
   :annotation: = package

   

.. data:: PACKAGE_EXTENSIONS
   

   

.. data:: PACKAGE_OUTPUT_HOOK_LOG_UUID
   :annotation: = PACKAGE_OUTPUT_HOOK_LOG_{}

   

.. data:: PACKAGE_PROGRESS_PREP_LOG
   :annotation: = 1

   

.. data:: PACKAGE_PROGRESS_LAUNCHING
   :annotation: = 2

   

.. data:: PACKAGE_PROGRESS_LOADING
   :annotation: = 5

   

.. data:: PACKAGE_PROGRESS_GET_INPUT
   :annotation: = 6

   

.. data:: PACKAGE_PROGRESS_ADD_EO_IMAGES
   :annotation: = 7

   

.. data:: PACKAGE_PROGRESS_CONVERT_INPUT
   :annotation: = 8

   

.. data:: PACKAGE_PROGRESS_CWL_RUN
   :annotation: = 10

   

.. data:: PACKAGE_PROGRESS_CWL_DONE
   :annotation: = 95

   

.. data:: PACKAGE_PROGRESS_PREP_OUT
   :annotation: = 98

   

.. data:: PACKAGE_PROGRESS_DONE
   :annotation: = 100

   

.. function:: get_status_location_log_path(status_location: str, out_dir: Optional[str] = None) -> str


.. function:: retrieve_package_job_log(execution: WPSExecution, job: Job) -> None

   Obtains the underlying WPS execution log from the status file to add them after existing job log entries.


.. function:: get_process_location(process_id_or_url: Union[Dict[str, Any], str], data_source: Optional[str] = None) -> str

   Obtains the URL of a WPS REST DescribeProcess given the specified information.

   :param process_id_or_url: process "identifier" or literal URL to DescribeProcess WPS-REST location.
   :param data_source: identifier of the data source to map to specific ADES, or map to localhost if ``None``.
   :return: URL of EMS or ADES WPS-REST DescribeProcess.


.. function:: get_package_workflow_steps(package_dict_or_url: Union[Dict[str, Any], str]) -> List[Dict[str, str]]

   :param package_dict_or_url: process package definition or literal URL to DescribeProcess WPS-REST location.
   :return: list of workflow steps as {"name": <name>, "reference": <reference>}
       where `name` is the generic package step name, and `reference` is the id/url of a registered WPS package.


.. function:: _fetch_process_info(process_info_url: str, fetch_error: Type[Exception]) -> JSON

   Fetches the JSON process information from the specified URL and validates that it contains something.

   :raises fetch_error: provided exception with URL message if the process information could not be retrieved.


.. function:: _get_process_package(process_url: str) -> Tuple[CWL, str]

   Retrieves the WPS process package content from given process ID or literal URL.

   :param process_url: process literal URL to DescribeProcess WPS-REST location.
   :return: tuple of package body as dictionary and package reference name.


.. function:: _get_process_payload(process_url: str) -> JSON

   Retrieves the WPS process payload content from given process ID or literal URL.

   :param process_url: process literal URL to DescribeProcess WPS-REST location.
   :return: payload body as dictionary.


.. function:: _get_package_type(package_dict: CWL) -> Union[PROCESS_APPLICATION, PROCESS_WORKFLOW]


.. function:: _get_package_requirements_as_class_list(requirements: AnyCWLRequirements) -> ListCWLRequirements

   Converts `CWL` package ``requirements`` or ``hints`` sometime defined as ``Dict[<req>: {<params>}]`` to an
   explicit list of dictionary requirements with ``class`` key.


.. function:: _get_package_ordered_io(io_section: Union[List[JSON], OrderedDict[str, JSON]], order_hints: Optional[List[JSON]] = None) -> List[JSON]

   Converts `CWL` package I/O definitions defined as dictionary to an equivalent :class:`list` representation.
   The list representation ensures that I/O order is preserved when written to file and reloaded afterwards
   regardless of each server and/or library's implementation of :class:`dict` container.

   If this function fails to correctly order any I/O or cannot correctly guarantee such result because of the provided
   parameters (e.g.: no hints given when required), the result will not break nor change the final processing behaviour
   of the `CWL` engine. This is merely *cosmetic* adjustments to ease readability of I/O to avoid always shuffling
   their order across multiple application package reporting.

   The important result of this function is to provide the `CWL` I/O as a consistent list of objects so it is less
   cumbersome to compare/merge/iterate over the elements with all functions that will follow.

   .. note::
       When defined as a dictionary, an :class:`OrderedDict` is expected as input to ensure preserved field order.
       Prior to Python 3.7 or CPython 3.5, preserved order is not guaranteed for *builtin* :class:`dict`.
       In this case the :paramref:`order_hints` is required to ensure same order.

   :param io_section: Definition contained under the `CWL` ``inputs`` or ``outputs`` package fields.
   :param order_hints: Optional/partial list of WPS I/O definitions hinting an order to sort CWL unsorted-dict I/O.
   :returns: I/O specified as list of dictionary definitions with preserved order (as best as possible).


.. function:: _check_package_file(cwl_file_path_or_url: str) -> Tuple[str, bool]

   Validates that the specified CWL file path or URL points to an existing and allowed file format.

   :param cwl_file_path_or_url: one of allowed file types path on disk, or an URL pointing to one served somewhere.
   :return: absolute_path, is_url: absolute path or URL, and boolean indicating if it is a remote URL file.
   :raises PackageRegistrationError: in case of missing file, invalid format or invalid HTTP status code.


.. function:: _load_package_file(file_path: str) -> CWL

   Loads the package in YAML/JSON format specified by the file path.


.. function:: _load_package_content(package_dict: Dict, package_name: str = PACKAGE_DEFAULT_FILE_NAME, data_source: Optional[str] = None, only_dump_file: bool = False, tmp_dir: Optional[str] = None, loading_context: Optional[LoadingContext] = None, runtime_context: Optional[RuntimeContext] = None, process_offering: Optional[JSON] = None) -> Optional[Tuple[CWLFactoryCallable, str, Dict]]

   Loads the package content to file in a temporary directory.
   Recursively processes sub-packages steps if the parent is a `Workflow` (CWL class).

   :param package_dict: package content representation as a json dictionary.
   :param package_name: name to use to create the package file.
   :param data_source: identifier of the data source to map to specific ADES, or map to localhost if ``None``.
   :param only_dump_file: specify if the ``CWLFactoryCallable`` should be validated and returned.
   :param tmp_dir: location of the temporary directory to dump files (deleted on exit).
   :param loading_context: cwltool context used to create the cwl package (required if ``only_dump_file=False``)
   :param runtime_context: cwltool context used to execute the cwl package (required if ``only_dump_file=False``)
   :param process_offering: JSON body of the process description payload (used as I/O hint ordering)
   :return:
       if ``only_dump_file`` is ``True``: ``None``
       otherwise, tuple of:
           - instance of ``CWLFactoryCallable``
           - package type (``PROCESS_WORKFLOW`` or ``PROCESS_APPLICATION``)
           - dict of each step with their package name that must be run

   .. warning::
       Specified :paramref:`tmp_dir` will be deleted on exit.


.. function:: _merge_package_inputs_outputs(wps_inputs_list: List[ANY_IO_Type], cwl_inputs_list: List[WPS_Input_Type], wps_outputs_list: List[ANY_IO_Type], cwl_outputs_list: List[WPS_Output_Type]) -> Tuple[List[JSON_IO_Type], List[JSON_IO_Type]]

   Merges I/O definitions to use for process creation and returned by ``GetCapabilities``, ``DescribeProcess``
   using the `WPS` specifications (from request ``POST``) and `CWL` specifications (extracted from file).

   Note:
       parameters ``cwl_inputs_list`` and ``cwl_outputs_list`` are expected to be in `WPS`-like format
       (ie: `CWL` I/O converted to corresponding `WPS` I/O)


.. function:: _get_package_io(package_factory: CWLFactoryCallable, io_select: str, as_json: bool) -> List[PKG_IO_Type]

   Retrieves I/O definitions from a validated ``CWLFactoryCallable``. Returned I/O format depends on value ``as_json``.


.. function:: _get_package_inputs_outputs(package_factory: CWLFactoryCallable, as_json: bool = False) -> Tuple[List[PKG_IO_Type], List[PKG_IO_Type]]

   Generates `WPS-like` ``(inputs, outputs)`` tuple using parsed CWL package definitions.


.. function:: _update_package_metadata(wps_package_metadata: JSON, cwl_package_package: CWL) -> None

   Updates the package `WPS` metadata dictionary from extractable `CWL` package definition.


.. function:: _generate_process_with_cwl_from_reference(reference: str) -> Tuple[CWL, JSON]

   Resolves the ``reference`` type (`CWL`, `WPS-1`, `WPS-2`, `WPS-3`) and generates a `CWL` ``package`` from it.
   Additionally provides minimal process details retrieved from the ``reference``.


.. function:: get_process_definition(process_offering: JSON, reference: Optional[str] = None, package: Optional[CWL] = None, data_source: Optional[str] = None) -> JSON

   Returns an updated process definition dictionary ready for storage using provided `WPS` ``process_offering``
   and a package definition passed by ``reference`` or ``package`` `CWL` content.
   The returned process information can be used later on to load an instance of :class:`weaver.wps_package.WpsPackage`.

   :param process_offering: `WPS REST-API` (`WPS-3`) process offering as `JSON`.
   :param reference: URL to `CWL` package definition, `WPS-1 DescribeProcess` endpoint or `WPS-3 Process` endpoint.
   :param package: literal `CWL` package definition (`YAML` or `JSON` format).
   :param data_source: where to resolve process IDs (default: localhost if ``None``).
   :return: updated process definition with resolved/merged information from ``package``/``reference``.


.. py:class:: WpsPackage(**kw)



   :param handler: A callable that gets invoked for each incoming
                   request. It should accept a single
                   :class:`pywps.app.WPSRequest` argument and return a
                   :class:`pywps.app.WPSResponse` object.
   :param string identifier: Name of this process.
   :param string title: Human readable title of process.
   :param string abstract: Brief narrative description of the process.
   :param list keywords: Keywords that characterize a process.
   :param inputs: List of inputs accepted by this process. They
                  should be :class:`~LiteralInput` and :class:`~ComplexInput`
                  and :class:`~BoundingBoxInput`
                  objects.
   :param outputs: List of outputs returned by this process. They
                  should be :class:`~LiteralOutput` and :class:`~ComplexOutput`
                  and :class:`~BoundingBoxOutput`
                  objects.
   :param metadata: List of metadata advertised by this process. They
                    should be :class:`pywps.app.Common.Metadata` objects.
   :param dict[str,dict[str,str]] translations: The first key is the RFC 4646 language code,
       and the nested mapping contains translated strings accessible by a string property.
       e.g. {"fr-CA": {"title": "Mon titre", "abstract": "Une description"}}

   Creates a `WPS-3 Process` instance to execute a `CWL` package definition.

   Process parameters should be loaded from an existing :class:`weaver.datatype.Process`
   instance generated using :func:`weaver.wps_package.get_process_definition`.

   Provided ``kw`` should correspond to :meth:`weaver.datatype.Process.params_wps`

   .. attribute:: package
      :annotation: :Optional[CWL]

      

   .. attribute:: package_id
      :annotation: :Optional[str]

      

   .. attribute:: package_type
      :annotation: :Optional[str]

      

   .. attribute:: package_log_hook_stderr
      :annotation: :Optional[str]

      

   .. attribute:: package_log_hook_stdout
      :annotation: :Optional[str]

      

   .. attribute:: percent
      :annotation: :Optional[Number]

      

   .. attribute:: is_ems
      :annotation: :Optional[bool]

      

   .. attribute:: log_file
      :annotation: :Optional[str]

      

   .. attribute:: log_level
      :annotation: :Optional[int]

      

   .. attribute:: logger
      :annotation: :Optional[logging.Logger]

      

   .. attribute:: step_packages
      :annotation: :Optional[List[CWL]]

      

   .. attribute:: step_launched
      :annotation: :Optional[List[str]]

      

   .. attribute:: request
      :annotation: :Optional[WPSRequest]

      

   .. attribute:: response
      :annotation: :Optional[ExecuteResponse]

      

   .. method:: setup_loggers(self: bool, log_stdout_stderr=True) -> None

      Configures useful loggers to catch most of the common output and/or error messages during package execution.

      .. seealso::
          :meth:`insert_package_log`
          :func:`retrieve_package_job_log`


   .. method:: insert_package_log(self: Union[CWLResults, CWLException], result) -> List[str]

      Retrieves additional `CWL` sub-process logs captures to retrieve internal application output and/or errors.

      After execution of this method, the `WPS` output log (which can be obtained by :func:`retrieve_package_job_log`)
      will have additional ``stderr/stdout`` entries extracted from the underlying application package tool execution.

      The outputs and errors are inserted *as best as possible* in the logical order to make reading of the merged
      logs appear as a natural and chronological order. In the event that both output and errors are available, they
      are appended one after another as merging in an orderly fashion cannot be guaranteed by outside `CWL` runner.

      .. note::
          In case of any exception, log reporting is aborted and ignored.

      .. todo::
          Improve for realtime updates when using async routine (https://github.com/crim-ca/weaver/issues/131)

      .. seealso::
          :meth:`setup_loggers`
          :func:`retrieve_package_job_log`

      :param result: output results returned by successful `CWL` package instance execution or raised CWL exception.
      :returns:  captured execution log lines retrieved from files


   .. method:: update_requirements(self)

      Inplace modification of :attr:`package` to adjust invalid items that would break behaviour we must enforce.


   .. method:: update_effective_user(self)

      Update effective user/group for the `Application Package` to be executed.

      FIXME: (experimental) update user/group permissions

      Reducing permissions is safer inside docker application since weaver/cwltool could be running as root
      but this requires that mounted volumes have the required permissions so euid:egid can use them.

      Overrides :mod:`cwltool`'s function to retrieve user/group id for ones we enforce.


   .. method:: update_status(self: str, message: Number, progress: AnyStatusType, status) -> None

      Updates the `PyWPS` real job status from a specified parameters.


   .. method:: step_update_status(self: str, message: Number, progress: Number, start_step_progress: Number, end_step_progress: str, step_name: AnyValue, target_host: str, status) -> None


   .. method:: log_message(self: AnyStatusType, status: str, message: Optional[Number], progress: int = None, level=logging.INFO) -> None


   .. method:: exception_message(self: Type[Exception], exception_type: Optional[Exception], exception: str = None, message: AnyStatusType = 'no message', status: int = STATUS_EXCEPTION, level=logging.ERROR) -> Exception

      Logs to the job the specified error message with the provided exception type.

      :returns: formatted exception with message to be raised by calling function.


   .. method:: map_step_progress(cls: int, step_index: int, steps_total) -> Number
      :classmethod:

      Calculates the percentage progression of a single step of the full process.

      .. note::
          The step procession is adjusted according to delimited start/end of the underlying `CWL` execution to
          provide a continuous progress percentage over the complete execution. Otherwise, we would have values
          that jump around according to whichever progress the underlying remote `WPS` or monitored `CWL` employs,
          if any is provided.


   .. method:: _handler(self: WPSRequest, request: ExecuteResponse, response) -> ExecuteResponse

      Method called when process receives the WPS execution request.


   .. method:: must_fetch(self: str, input_ref) -> bool

      Figures out if file reference should be fetched immediately for local execution.
      If anything else than local script/docker, remote ADES/WPS process will fetch it.
      S3 are handled here to avoid error on remote WPS not supporting it.

      .. seealso::
          - :ref:`File Reference Types`


   .. method:: make_inputs(self, wps_inputs: Dict[str, Deque[WPS_Input_Type]], cwl_inputs_info: Dict[str, CWL_Input_Type]) -> Dict[str, ValueType]

      Converts WPS input values to corresponding CWL input values for processing by CWL package instance.

      The WPS inputs must correspond to :mod:`pywps` definitions.
      Multiple values are adapted to arrays as needed.
      WPS ``Complex`` types (files) are converted to appropriate locations based on data or reference specification.

      :param wps_inputs: actual WPS inputs parsed from execution request
      :param cwl_inputs_info: expected CWL input definitions for mapping
      :return: CWL input values


   .. method:: make_location_input(self: str, input_type: ComplexInput, input_definition) -> JSON

      Generates the JSON content required to specify a `CWL` ``File`` input definition from a location.

      .. note::
          If the process requires ``OpenSearch`` references that should be preserved as is, use scheme defined by
          :py:data:`weaver.processes.constants.OPENSEARCH_LOCAL_FILE_SCHEME` prefix instead of ``http(s)://``.


   .. method:: make_outputs(self: CWLResults, cwl_result) -> None

      Maps `CWL` result outputs to corresponding `WPS` outputs.


   .. method:: make_location_output(self: CWLResults, cwl_result: str, output_id) -> None

      Rewrite the `WPS` output with required location using result path from `CWL` execution.

      Configures the parameters such that `PyWPS` will either auto-resolve the local paths to match with URL
      defined by ``weaver.wps_output_url`` or upload it to `S3` bucket from ``weaver.wps_output_s3_bucket`` and
      provide reference directly.

      .. seealso::
          - :func:`weaver.wps.load_pywps_config`


   .. method:: make_tool(self: ToolPathObjectType, toolpath_object: LoadingContext, loading_context) -> ProcessCWL


   .. method:: get_application_requirement(self) -> Dict[str, Any]

      Obtains the first item in `CWL` package ``requirements`` or ``hints`` that corresponds to a `Weaver`-specific
      application type as defined in :py:data:`CWL_REQUIREMENT_APP_TYPES`.

      :returns: dictionary that minimally has ``class`` field, and optionally other parameters from that requirement.


   .. method:: get_job_process_definition(self: str, jobname: JSON, joborder: CWL, tool) -> WpsPackage

      This function is called before running an ADES job (either from a workflow step or a simple EMS dispatch).
      It must return a WpsProcess instance configured with the proper package, ADES target and cookies.

      :param jobname: The workflow step or the package id that must be launch on an ADES :class:`string`
      :param joborder: The params for the job :class:`dict {input_name: input_value}`
                       input_value is one of `input_object` or `array [input_object]`
                       input_object is one of `string` or `dict {class: File, location: string}`
                       in our case input are expected to be File object
      :param tool: Whole `CWL` config including hints requirement



