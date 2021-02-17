:mod:`weaver.store.base`
========================

.. py:module:: weaver.store.base


Module Contents
---------------

.. data:: JobListAndCount
   

   

.. py:class:: StoreInterface



   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: type
      

      


.. py:class:: StoreServices



   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: type
      :annotation: = services

      

   .. method:: save_service(self: Service, service: bool, overwrite=True) -> Service
      :abstractmethod:


   .. method:: delete_service(self: str, name) -> bool
      :abstractmethod:


   .. method:: list_services(self) -> List[Service]
      :abstractmethod:


   .. method:: fetch_by_name(self: str, name: Optional[str], visibility=None) -> Service
      :abstractmethod:


   .. method:: fetch_by_url(self: str, url) -> Service
      :abstractmethod:


   .. method:: clear_services(self) -> bool
      :abstractmethod:



.. py:class:: StoreProcesses



   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: type
      :annotation: = processes

      

   .. method:: save_process(self: Union[Process, ProcessWPS], process: bool, overwrite=True) -> Process
      :abstractmethod:


   .. method:: delete_process(self: str, process_id: Optional[str], visibility=None) -> bool
      :abstractmethod:


   .. method:: list_processes(self: Optional[str], visibility=None) -> List[Process]
      :abstractmethod:


   .. method:: fetch_by_id(self: str, process_id: Optional[str], visibility=None) -> Process
      :abstractmethod:


   .. method:: get_visibility(self: str, process_id) -> str
      :abstractmethod:


   .. method:: set_visibility(self: str, process_id: str, visibility) -> None
      :abstractmethod:


   .. method:: clear_processes(self) -> bool
      :abstractmethod:



.. py:class:: StoreJobs



   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: type
      :annotation: = jobs

      

   .. method:: save_job(self, task_id: str, process: str, service: Optional[str] = None, inputs: Optional[List[Any]] = None, is_workflow: bool = False, is_local: bool = False, user_id: Optional[int] = None, execute_async: bool = True, custom_tags: Optional[List[str]] = None, access: Optional[str] = None, notification_email: Optional[str] = None, accept_language: Optional[str] = None) -> Job
      :abstractmethod:


   .. method:: update_job(self: Job, job) -> Job
      :abstractmethod:


   .. method:: delete_job(self: str, job_id) -> bool
      :abstractmethod:


   .. method:: fetch_by_id(self: str, job_id) -> Job
      :abstractmethod:


   .. method:: list_jobs(self) -> List[Job]
      :abstractmethod:


   .. method:: find_jobs(self, process: Optional[str] = None, service: Optional[str] = None, tags: Optional[List[str]] = None, access: Optional[str] = None, notification_email: Optional[str] = None, status: Optional[str] = None, sort: Optional[str] = None, page: int = 0, limit: int = 10, group_by: Optional[Union[str, List[str]]] = None, request: Optional[Request] = None) -> Union[JobListAndCount, JobCategoriesAndCount]
      :abstractmethod:


   .. method:: clear_jobs(self) -> bool
      :abstractmethod:



.. py:class:: StoreQuotes



   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: type
      :annotation: = quotes

      

   .. method:: save_quote(self: Quote, quote) -> Quote
      :abstractmethod:


   .. method:: fetch_by_id(self: str, quote_id) -> Quote
      :abstractmethod:


   .. method:: list_quotes(self) -> List[Quote]
      :abstractmethod:


   .. method:: find_quotes(self: Optional[str], process_id: int = None, page: int = 0, limit: Optional[str] = 10, sort=None) -> Tuple[List[Quote], int]
      :abstractmethod:



.. py:class:: StoreBills



   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: type
      :annotation: = bills

      

   .. method:: save_bill(self: Bill, bill) -> Bill
      :abstractmethod:


   .. method:: fetch_by_id(self: str, bill_id) -> Bill
      :abstractmethod:


   .. method:: list_bills(self) -> List[Bill]
      :abstractmethod:


   .. method:: find_bills(self: Optional[str], quote_id: int = None, page: int = 0, limit: Optional[str] = 10, sort=None) -> Tuple[List[Bill], int]
      :abstractmethod:



