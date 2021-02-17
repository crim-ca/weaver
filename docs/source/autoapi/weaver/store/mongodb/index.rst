:mod:`weaver.store.mongodb`
===========================

.. py:module:: weaver.store.mongodb

.. autoapi-nested-parse::

   Stores to read/write data to from/to `MongoDB` using pymongo.



Module Contents
---------------

.. data:: LOGGER
   

   

.. py:class:: MongodbStore(: Collection, collection: Optional[Dict[str, Any]], sane_name_config=None)



   Base class extended by all concrete store implementations.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: get_args_kwargs(cls: Any, *args: Any, **kwargs) -> Tuple[Tuple, Dict]
      :classmethod:

      Filters :class:`MongodbStore`-specific arguments to safely pass them down its ``__init__``.



.. py:class:: MongodbServiceStore(*args, **kwargs)



   Registry for OWS services. Uses `MongoDB` to store service url and attributes.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: save_service(self: Service, service: bool, overwrite=True) -> Service

      Stores an OWS service in mongodb.


   .. method:: delete_service(self: str, name) -> bool

      Removes service from `MongoDB` storage.


   .. method:: list_services(self) -> List[Service]

      Lists all services in `MongoDB` storage.


   .. method:: fetch_by_name(self: str, name: Optional[str], visibility=None) -> Service

      Gets service for given ``name`` from `MongoDB` storage.


   .. method:: fetch_by_url(self: str, url) -> Service

      Gets service for given ``url`` from `MongoDB` storage.


   .. method:: clear_services(self) -> bool

      Removes all OWS services from `MongoDB` storage.



.. py:class:: MongodbProcessStore(*args, **kwargs)



   Registry for processes. Uses `MongoDB` to store processes and attributes.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: _add_process(self: AnyProcess, process) -> None


   .. method:: _get_process_field(process: AnyProcess, function_dict: Union[Dict[AnyProcessType, Callable[[], Any]], Callable[[], Any]]) -> Any
      :staticmethod:

      Takes a lambda expression or a dict of process-specific lambda expressions to retrieve a field.
      Validates that the passed process object is one of the supported types.

      :param process: process to retrieve the field from.
      :param function_dict: lambda or dict of lambda of process type
      :return: retrieved field if the type was supported
      :raises ProcessInstanceError: invalid process type


   .. method:: _get_process_id(self: AnyProcess, process) -> str


   .. method:: _get_process_type(self: AnyProcess, process) -> str


   .. method:: _get_process_endpoint_wps1(self: AnyProcess, process) -> str


   .. method:: save_process(self: Union[Process, ProcessWPS], process: bool, overwrite=True) -> Process

      Stores a process in storage.

      :param process: An instance of :class:`weaver.datatype.Process`.
      :param overwrite: Overwrite the matching process instance by name if conflicting.


   .. method:: delete_process(self: str, process_id: Optional[str], visibility=None) -> bool

      Removes process from database, optionally filtered by visibility.
      If ``visibility=None``, the process is deleted (if existing) regardless of its visibility value.


   .. method:: list_processes(self: Optional[str], visibility=None) -> List[Process]

      Lists all processes in database, optionally filtered by `visibility`.

      :param visibility: One value amongst `weaver.visibility`.


   .. method:: fetch_by_id(self: str, process_id: Optional[str], visibility=None) -> Process

      Get process for given `process_id` from storage, optionally filtered by `visibility`.
      If ``visibility=None``, the process is retrieved (if existing) regardless of its visibility value.

      :param process_id: process identifier
      :param visibility: one value amongst `weaver.visibility`.
      :return: An instance of :class:`weaver.datatype.Process`.


   .. method:: get_visibility(self: str, process_id) -> str

      Get `visibility` of a process.

      :return: One value amongst `weaver.visibility`.


   .. method:: set_visibility(self: str, process_id: str, visibility) -> None

      Set `visibility` of a process.

      :param visibility: One value amongst `weaver.visibility`.
      :param process_id:
      :raises TypeError: when :paramref:`visibility` is not :class:`str`.
      :raises ValueError: when :paramref:`visibility` is not one of :py:data:`weaver.visibility.VISIBILITY_VALUES`.


   .. method:: clear_processes(self) -> bool

      Clears all processes from the store.



.. py:class:: MongodbJobStore(*args, **kwargs)



   Registry for process jobs tracking. Uses `MongoDB` to store job attributes.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: save_job(self, task_id: str, process: str, service: Optional[str] = None, inputs: Optional[List[Any]] = None, is_workflow: bool = False, is_local: bool = False, user_id: Optional[int] = None, execute_async: bool = True, custom_tags: Optional[List[str]] = None, access: Optional[str] = None, notification_email: Optional[str] = None, accept_language: Optional[str] = None) -> Job

      Stores a job in mongodb.


   .. method:: update_job(self: Job, job) -> Job

      Updates a job parameters in `MongoDB` storage.
      :param job: instance of ``weaver.datatype.Job``.


   .. method:: delete_job(self: str, job_id) -> bool

      Removes job from `MongoDB` storage.


   .. method:: fetch_by_id(self: str, job_id) -> Job

      Gets job for given ``job_id`` from `MongoDB` storage.


   .. method:: list_jobs(self) -> List[Job]

      Lists all jobs in `MongoDB` storage.
      For user-specific access to available jobs, use :meth:`MongodbJobStore.find_jobs` instead.


   .. method:: find_jobs(self, process: Optional[str] = None, service: Optional[str] = None, tags: Optional[List[str]] = None, access: Optional[str] = None, notification_email: Optional[str] = None, status: Optional[str] = None, sort: Optional[str] = None, page: int = 0, limit: int = 10, group_by: Optional[Union[str, List[str]]] = None, request: Optional[Request] = None) -> Union[JobListAndCount, JobCategoriesAndCount]

      Finds all jobs in `MongoDB` storage matching search filters to obtain results with requested paging or grouping.

      :param request: request that lead to this call to obtain permissions and user id.
      :param process: process name to filter matching jobs.
      :param service: service name to filter matching jobs.
      :param tags: list of tags to filter matching jobs.
      :param access: access visibility to filter matching jobs (default: :py:data:`VISIBILITY_PUBLIC`).
      :param notification_email: notification email to filter matching jobs.
      :param status: status to filter matching jobs.
      :param sort: field which is used for sorting results (default: creation date, descending).
      :param page: page number to return when using result paging (only when not using ``group_by``).
      :param limit: number of jobs per page when using result paging (only when not using ``group_by``).
      :param group_by: one or many fields specifying categories to form matching groups of jobs (paging disabled).

      :returns: (list of jobs matching paging OR list of {categories, list of jobs, count}) AND total of matched job

      Example:

          Using paging (default), result will be in the form::

              (
                  [Job(1), Job(2), Job(3), ...],
                  <total>
              )

          Where ``<total>`` will indicate the complete count of matched jobs with filters, but the list of jobs
          will be limited only to ``page`` index and ``limit`` specified.

          Using grouping with a list of field specified with ``group_by``, results will be in the form::

              (
                  [{category: {field1: valueA, field2: valueB, ...}, [Job(1), Job(2), ...], count: <count>},
                   {category: {field1: valueC, field2: valueD, ...}, [Job(x), Job(y), ...], count: <count>},
                   ...
                  ],
                  <total>
              )

          Where ``<total>`` will again indicate all matched jobs by every category combined, and ``<count>`` will
          indicate the amount of jobs matched for each individual category. Also, ``category`` will indicate values
          of specified fields (from ``group_by``) that compose corresponding jobs with matching values.


   .. method:: clear_jobs(self) -> bool

      Removes all jobs from `MongoDB` storage.



.. py:class:: MongodbQuoteStore(*args, **kwargs)



   Registry for quotes. Uses `MongoDB` to store quote attributes.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: save_quote(self: Quote, quote) -> Quote

      Stores a quote in mongodb.


   .. method:: fetch_by_id(self: str, quote_id) -> Quote

      Gets quote for given ``quote_id`` from `MongoDB` storage.


   .. method:: list_quotes(self) -> List[Quote]

      Lists all quotes in `MongoDB` storage.


   .. method:: find_quotes(self: Optional[str], process_id: int = None, page: int = 0, limit: Optional[str] = 10, sort=None) -> Tuple[List[Quote], int]

      Finds all quotes in `MongoDB` storage matching search filters.

      Returns a tuple of filtered ``items`` and their ``count``, where ``items`` can have paging and be limited
      to a maximum per page, but ``count`` always indicate the `total` number of matches.



.. py:class:: MongodbBillStore(*args, **kwargs)



   Registry for bills. Uses `MongoDB` to store bill attributes.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: save_bill(self: Bill, bill) -> Bill

      Stores a bill in mongodb.


   .. method:: fetch_by_id(self: str, bill_id) -> Bill

      Gets bill for given ``bill_id`` from `MongoDB` storage.


   .. method:: list_bills(self) -> List[Bill]

      Lists all bills in `MongoDB` storage.


   .. method:: find_bills(self: Optional[str], quote_id: int = None, page: int = 0, limit: Optional[str] = 10, sort=None) -> Tuple[List[Bill], int]

      Finds all bills in `MongoDB` storage matching search filters.

      Returns a tuple of filtered ``items`` and their ``count``, where ``items`` can have paging and be limited
      to a maximum per page, but ``count`` always indicate the `total` number of matches.



