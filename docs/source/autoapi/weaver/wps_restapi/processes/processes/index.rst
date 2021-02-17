:mod:`weaver.wps_restapi.processes.processes`
=============================================

.. py:module:: weaver.wps_restapi.processes.processes


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: submit_provider_job(request)

   Execute a provider process.


.. function:: list_remote_processes(service: Service, request: Request) -> List[Process]

   Obtains a list of remote service processes in a compatible :class:`weaver.datatype.Process` format.

   Note: remote processes won't be stored to the local process storage.


.. function:: get_provider_processes(request)

   Retrieve available provider processes (GetCapabilities).


.. function:: describe_provider_process(request: Request) -> Process

   Obtains a remote service process description in a compatible local process format.

   Note: this processes won't be stored to the local process storage.


.. function:: get_provider_process(request)

   Retrieve a process description (DescribeProcess).


.. function:: get_processes_filtered_by_valid_schemas(request: Request) -> Tuple[List[JSON], List[str]]

   Validates the processes summary schemas and returns them into valid/invalid lists.
   :returns: list of valid process summaries and invalid processes IDs for manual cleanup.


.. function:: get_processes(request)

   List registered processes (GetCapabilities). Optionally list both local and provider processes.


.. function:: add_local_process(request)

   Register a local process.


.. function:: get_local_process(request)

   Get a registered local process information (DescribeProcess).


.. function:: get_local_process_package(request)

   Get a registered local process package definition.


.. function:: get_local_process_payload(request)

   Get a registered local process payload definition.


.. function:: get_process_visibility(request)

   Get the visibility of a registered local process.


.. function:: set_process_visibility(request)

   Set the visibility of a registered local process.


.. function:: delete_local_process(request)

   Unregister a local process.


.. function:: submit_local_job(request)

   Execute a local process.


