:mod:`weaver.processes.utils`
=============================

.. py:module:: weaver.processes.utils


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: get_process(process_id: Optional[str] = None, request: Optional[Request] = None, settings: Optional[SettingsType] = None, store: Optional[StoreProcesses] = None) -> Process

   Obtain the specified process and validate information, returning appropriate HTTP error if invalid.

   Process identifier must be provided from either the request path definition or literal ID.
   Database must be retrievable from either the request, underlying settings, or direct store reference.

   Different parameter combinations are intended to be used as needed or more appropriate, such that redundant
   operations can be reduced where some objects are already fetched from previous operations.


.. function:: get_job_submission_response(body: JSON) -> HTTPCreated

   Generates the successful response from contents returned by job submission process.

   .. seealso::
       :func:`weaver.processes.execution.submit_job`


.. function:: map_progress(progress: Number, range_min: Number, range_max: Number) -> Number

   Calculates the relative progression of the percentage process within min/max values.


.. function:: _check_deploy(payload)

   Validate minimum deploy payload field requirements with exception handling.


.. function:: _get_deploy_process_info(process_info, reference, package)

   Obtain the process definition from deploy payload with exception handling.


.. function:: deploy_process_from_payload(payload: JSON, container: AnyContainer) -> HTTPException

   Adds a :class:`weaver.datatype.Process` instance to storage using the provided JSON ``payload`` matching
   :class:`weaver.wps_restapi.swagger_definitions.ProcessDescription`.

   :returns: HTTPOk if the process registration was successful
   :raises HTTPException: otherwise


.. function:: parse_wps_process_config(config_entry: Union[JSON, str]) -> Tuple[str, str, List[str], bool]

   Parses the available WPS provider or process entry to retrieve its relevant information.

   :return: WPS provider name, WPS service URL, and list of process identifier(s).
   :raise ValueError: if the entry cannot be parsed correctly.


.. function:: register_wps_processes_from_config(wps_processes_file_path: Optional[FileSystemPathType], container: AnySettingsContainer) -> None

   Loads a `wps_processes.yml` file and registers `WPS-1` providers processes to the
   current `Weaver` instance as equivalent `WPS-2` processes.

   References listed under ``processes`` are registered.
   When the reference is a service (provider), registration of each WPS process is done individually
   for each of the specified providers with ID ``[service]_[process]`` per listed process by ``GetCapabilities``.

   .. versionadded:: 1.14.0
       When references are specified using ``providers`` section instead of ``processes``, the registration
       only saves the remote WPS provider endpoint to dynamically populate WPS processes on demand.

   .. seealso::
       - `weaver.wps_processes.yml.example` for additional file format details


