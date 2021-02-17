:mod:`weaver.datatype`
======================

.. py:module:: weaver.datatype


Module Contents
---------------

.. data:: LOGGER
   

   

.. py:class:: Base



   Dictionary with extended attributes auto-``getter``/``setter`` for convenience.
   Explicitly overridden ``getter``/``setter`` attributes are called instead of ``dict``-key ``get``/``set``-item
   to ensure corresponding checks and/or value adjustments are executed before applying it to the sub-``dict``.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: id(self)
      :property:


   .. method:: uuid(self)
      :property:


   .. method:: json(self) -> JSON
      :abstractmethod:

      Obtain the JSON data representation for response body.

      .. note::
          This method implementation should validate the JSON schema against the API definition whenever
          applicable to ensure integrity between the represented data type and the expected API response.


   .. method:: params(self) -> Dict[str, Any]
      :abstractmethod:

      Obtain the internal data representation for storage.

      .. note::
          This method implementation should provide a JSON-serializable definition of all fields representing
          the object to store.



.. py:class:: Service(*args, **kwargs)



   Dictionary that contains OWS services. It always has ``url`` key.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: id(self)
      :property:


   .. method:: url(self)
      :property:

      Service URL.


   .. method:: name(self)
      :property:

      Service name.


   .. method:: type(self)
      :property:

      Service type.


   .. method:: public(self)
      :property:

      Flag if service has public access.


   .. method:: auth(self)
      :property:

      Authentication method: public, token, cert.


   .. method:: json(self) -> JSON

      Obtain the JSON data representation for response body.

      .. note::
          This method implementation should validate the JSON schema against the API definition whenever
          applicable to ensure integrity between the represented data type and the expected API response.


   .. method:: params(self)

      Obtain the internal data representation for storage.

      .. note::
          This method implementation should provide a JSON-serializable definition of all fields representing
          the object to store.



.. py:class:: Job(*args, **kwargs)



   Dictionary that contains OWS service jobs. It always has ``id`` and ``task_id`` keys.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: inputs
      

      

   .. attribute:: results
      

      

   .. attribute:: exceptions
      

      

   .. attribute:: logs
      

      

   .. attribute:: tags
      

      

   .. method:: _get_log_msg(self: Optional[str], msg=None) -> str


   .. method:: save_log(self, errors: Optional[Union[str, List[WPSException]]] = None, logger: Optional[Logger] = None, message: Optional[str] = None, level: int = INFO) -> None

      Logs the specified error and/or message, and adds the log entry to the complete job log.

      For each new log entry, additional :class:`Job` properties are added according to :meth:`Job._get_log_msg`
      and the format defined by :func:`get_job_log_msg`.

      :param errors:
          An error message or a list of WPS exceptions from which to log and save generated message stack.
      :param logger:
          An additional :class:`Logger` for which to propagate logged messages on top saving them to the job.
      :param message:
          Explicit string to be logged, otherwise use the current :py:attr:`Job.status_message` is used.
      :param level:
          Logging level to apply to the logged ``message``. This parameter is ignored if ``errors`` are logged.

      .. note::
          The job object is updated with the log but still requires to be pushed to database to actually persist it.


   .. method:: id(self) -> str
      :property:

      Job UUID to retrieve the details from storage.


   .. method:: task_id(self) -> Optional[str]
      :property:

      Reference Task UUID attributed by the ``Celery`` worker that monitors and executes this job.


   .. method:: wps_id(self) -> Optional[str]
      :property:

      Reference WPS Request/Response UUID attributed by the executed ``PyWPS`` process.

      This UUID matches the status-location, log and output directory of the WPS process.
      This parameter is only available when the process is executed on this local instance.

      .. seealso::
          - :attr:`Job.request`
          - :attr:`Job.response`


   .. method:: service(self) -> Optional[str]
      :property:

      Service identifier of the corresponding remote process.

      .. seealso::
          - :attr:`Service.id`


   .. method:: process(self) -> Optional[str]
      :property:

      Process identifier of the corresponding remote process.

      .. seealso::
          - :attr:`Process.id`


   .. method:: _get_inputs(self) -> List[Optional[Dict[str, Any]]]


   .. method:: _set_inputs(self: List[Optional[Dict[str, Any]]], inputs) -> None


   .. method:: user_id(self) -> Optional[str]
      :property:


   .. method:: status(self) -> str
      :property:


   .. method:: status_message(self) -> str
      :property:


   .. method:: status_location(self) -> Optional[str]
      :property:


   .. method:: notification_email(self) -> Optional[str]
      :property:


   .. method:: accept_language(self) -> Optional[str]
      :property:


   .. method:: execute_async(self) -> bool
      :property:


   .. method:: is_workflow(self) -> bool
      :property:


   .. method:: created(self) -> datetime
      :property:


   .. method:: finished(self) -> Optional[datetime]
      :property:


   .. method:: is_finished(self) -> bool


   .. method:: mark_finished(self) -> None


   .. method:: duration(self) -> timedelta
      :property:


   .. method:: duration_str(self) -> str
      :property:


   .. method:: progress(self) -> Number
      :property:


   .. method:: _get_results(self) -> List[Optional[Dict[str, Any]]]


   .. method:: _set_results(self: List[Optional[Dict[str, Any]]], results) -> None


   .. method:: _get_exceptions(self) -> List[Optional[Dict[str, str]]]


   .. method:: _set_exceptions(self: List[Optional[Dict[str, str]]], exceptions) -> None


   .. method:: _get_logs(self) -> List[Dict[str, str]]


   .. method:: _set_logs(self: List[Dict[str, str]], logs) -> None


   .. method:: _get_tags(self) -> List[Optional[str]]


   .. method:: _set_tags(self: List[Optional[str]], tags) -> None


   .. method:: access(self) -> str
      :property:

      Job visibility access from execution.


   .. method:: request(self) -> Optional[str]
      :property:

      XML request for WPS execution submission as string (binary).


   .. method:: response(self) -> Optional[str]
      :property:

      XML status response from WPS execution submission as string (binary).


   .. method:: _job_url(self, settings)


   .. method:: json(self: Optional[AnySettingsContainer], container=None) -> JSON

      Obtain the JSON data representation for response body.

      .. note::
          Settings are required to update API shortcut URLs to job additional information.
          Without them, paths will not include the API host, which will not resolve to full URI.


   .. method:: params(self) -> Dict[str, Any]

      Obtain the internal data representation for storage.

      .. note::
          This method implementation should provide a JSON-serializable definition of all fields representing
          the object to store.



.. py:class:: Process(*args, **kwargs)



   Dictionary that contains a process description for db storage.
   It always has ``identifier`` and ``processEndpointWPS1`` keys.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _character_codes
      :annotation: = [['$', '＄'], ['.', '．']]

      

   .. method:: id(self) -> str
      :property:


   .. method:: identifier(self) -> str
      :property:


   .. method:: title(self) -> str
      :property:


   .. method:: abstract(self) -> str
      :property:


   .. method:: keywords(self) -> List[str]
      :property:


   .. method:: metadata(self) -> List[str]
      :property:


   .. method:: version(self) -> Optional[str]
      :property:


   .. method:: inputs(self) -> Optional[List[Dict[str, Any]]]
      :property:


   .. method:: outputs(self) -> Optional[List[Dict[str, Any]]]
      :property:


   .. method:: jobControlOptions(self) -> Optional[List[str]]
      :property:


   .. method:: outputTransmission(self) -> Optional[List[str]]
      :property:


   .. method:: processDescriptionURL(self) -> Optional[str]
      :property:


   .. method:: processEndpointWPS1(self) -> Optional[str]
      :property:


   .. method:: executeEndpoint(self) -> Optional[str]
      :property:


   .. method:: owsContext(self) -> Optional[JSON]
      :property:


   .. method:: type(self) -> str
      :property:


   .. method:: package(self) -> Optional[CWL]
      :property:

      Package CWL definition as JSON.


   .. method:: payload(self) -> JSON
      :property:

      Deployment specification as JSON body.


   .. method:: _recursive_replace(pkg: JSON, index_from: int, index_to: int) -> JSON
      :staticmethod:


   .. method:: _encode(obj: Optional[JSON]) -> Optional[JSON]
      :staticmethod:


   .. method:: _decode(obj: Optional[JSON]) -> Optional[JSON]
      :staticmethod:


   .. method:: visibility(self) -> str
      :property:


   .. method:: params(self) -> Dict[str, Any]

      Obtain the internal data representation for storage.

      .. note::
          This method implementation should provide a JSON-serializable definition of all fields representing
          the object to store.


   .. method:: params_wps(self) -> Dict[str, Any]
      :property:

      Values applicable to PyWPS Process ``__init__``


   .. method:: json(self) -> JSON

      Obtain the JSON data representation for response body.

      .. note::
          This method implementation should validate the JSON schema against the API definition whenever
          applicable to ensure integrity between the represented data type and the expected API response.


   .. method:: process_offering(self) -> JSON


   .. method:: process_summary(self) -> JSON


   .. method:: from_wps(wps_process: ProcessWPS, **extra_params: Any) -> Process
      :staticmethod:

      Converts a :mod:`pywps` Process into a :class:`weaver.datatype.Process` using provided parameters.


   .. method:: from_ows(service: Service, process: ProcessWPS, container: AnySettingsContainer) -> Process
      :staticmethod:

      Converts a :mod:`owslib.wps` Process to local storage :class:`weaver.datatype.Process`.


   .. method:: wps(self) -> ProcessWPS



.. py:class:: Quote(*args, **kwargs)



   Dictionary that contains quote information.
   It always has ``id`` and ``process`` keys.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: id(self)
      :property:

      Quote ID.


   .. method:: title(self)
      :property:

      Quote title.


   .. method:: description(self)
      :property:

      Quote description.


   .. method:: details(self)
      :property:

      Quote details.


   .. method:: user(self)
      :property:

      User ID requesting the quote


   .. method:: process(self)
      :property:

      WPS Process ID.


   .. method:: estimatedTime(self)
      :property:

      Process estimated time.


   .. method:: processParameters(self)
      :property:

      Process execution parameters for quote.


   .. method:: location(self)
      :property:

      WPS Process URL.


   .. method:: price(self)
      :property:

      Price of the current quote


   .. method:: currency(self)
      :property:

      Currency of the quote price


   .. method:: expire(self)
      :property:

      Quote expiration datetime.


   .. method:: created(self)
      :property:

      Quote creation datetime.


   .. method:: steps(self)
      :property:

      Sub-quote IDs if applicable


   .. method:: params(self) -> Dict[str, Any]

      Obtain the internal data representation for storage.

      .. note::
          This method implementation should provide a JSON-serializable definition of all fields representing
          the object to store.


   .. method:: json(self) -> JSON

      Obtain the JSON data representation for response body.

      .. note::
          This method implementation should validate the JSON schema against the API definition whenever
          applicable to ensure integrity between the represented data type and the expected API response.



.. py:class:: Bill(*args, **kwargs)



   Dictionary that contains bill information.
   It always has ``id``, ``user``, ``quote`` and ``job`` keys.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: id(self)
      :property:

      Bill ID.


   .. method:: user(self)
      :property:

      User ID


   .. method:: quote(self)
      :property:

      Quote ID.


   .. method:: job(self)
      :property:

      Job ID.


   .. method:: price(self)
      :property:

      Price of the current quote


   .. method:: currency(self)
      :property:

      Currency of the quote price


   .. method:: created(self)
      :property:

      Quote creation datetime.


   .. method:: title(self)
      :property:

      Quote title.


   .. method:: description(self)
      :property:

      Quote description.


   .. method:: params(self) -> Dict[str, Any]

      Obtain the internal data representation for storage.

      .. note::
          This method implementation should provide a JSON-serializable definition of all fields representing
          the object to store.


   .. method:: json(self) -> JSON

      Obtain the JSON data representation for response body.

      .. note::
          This method implementation should validate the JSON schema against the API definition whenever
          applicable to ensure integrity between the represented data type and the expected API response.



