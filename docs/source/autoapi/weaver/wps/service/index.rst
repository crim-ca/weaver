:mod:`weaver.wps.service`
=========================

.. py:module:: weaver.wps.service


Module Contents
---------------

.. data:: LOGGER
   

   

.. py:class:: ReferenceStatusLocationStorage(: str, url_location: SettingsType, settings)



   Simple storage that simply redirects to a pre-existing status location.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: url(self, *_, **__)

      :param destination: the name of the output to calculate
                          the url for
      :returns: URL where file_name can be reached


   .. method:: location(self, *_, **__)

      Provides a location for the specified destination.
      This may be any path, pathlike object, db connection string, URL, etc
      and it is not guaranteed to be accessible on the local file system
      :param destination: the name of the output to calculate
                          the location for
      :returns: location where file_name can be found


   .. method:: store(self, *_, **__)

      :param output: of type IOHandler
      :returns: (type, store, url) where
          type - is type of STORE_TYPE - number
          store - string describing storage - file name, database connection
          url - url, where the data can be downloaded


   .. method:: write(self, *_, **__)

      :param data: data to write to storage
      :param destination: identifies the destination to write to storage
                          generally a file name which can be interpreted
                          by the implemented Storage class in a manner of
                          its choosing
      :param data_format: Optional parameter of type pywps.inout.formats.FORMAT
                     describing the format of the data to write.
      :returns: url where the data can be downloaded



.. py:class:: WorkerExecuteResponse(: WPSRequest, wps_request: str, uuid: ProcessWPS, process: str, job_url: SettingsType, settings: Any, *_: Any, **__)



   XML response generator from predefined job status URL and executed process definition.

   constructor

   :param pywps.app.WPSRequest.WPSRequest wps_request:
   :param pywps.app.Process.Process process:
   :param uuid: string this request uuid


.. py:class:: WorkerService(*_, is_worker=False, settings=None, **__)



   Dispatches PyWPS requests from *older* WPS-1/2 XML endpoint to WPS-REST as appropriate.

   .. note::
       For every WPS-Request type, the parsing of XML content is already handled by the PyWPS service for GET/POST.
       All data must be retrieved from parsed :class:`WPSRequest` to avoid managing argument location and WPS versions.

   When ``GetCapabilities`` or ``DescribeProcess`` requests are received, directly return to result as XML based
   on content (no need to subprocess as Celery task that gets resolved quickly with only the process(es) details).
   When JSON content is requested, instead return the redirect link to corresponding WPS-REST API endpoint.

   When receiving ``Execute`` request, convert the XML payload to corresponding JSON and
   dispatch it to the Celery Worker to actually process it after job setup for monitoring.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: _get_capabilities_redirect(self: WPSRequest, wps_request: Any, *_: Any, **__) -> Optional[Union[WPSResponse, HTTPValid]]

      Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON.


   .. method:: get_capabilities(self: WPSRequest, wps_request: Any, *_: Any, **__) -> Union[WPSResponse, HTTPValid]

      Redirect to WPS-REST endpoint if requested ``Content-Type`` is JSON or handle ``GetCapabilities`` normally.


   .. method:: _describe_process_redirect(self: WPSRequest, wps_request: Any, *_: Any, **__) -> Optional[Union[WPSResponse, HTTPValid]]

      Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON.


   .. method:: describe(self: WPSRequest, wps_request: Any, *_: Any, **__) -> Union[WPSResponse, HTTPValid]

      Redirect to WPS-REST endpoint if requested ``Content-Type`` is JSON or handle ``DescribeProcess`` normally.


   .. method:: _submit_job(self: WPSRequest, wps_request) -> Union[WPSResponse, HTTPValid, JSON]

      Dispatch operation to WPS-REST endpoint, which in turn should call back the real Celery Worker for execution.


   .. method:: execute(self: str, identifier: WPSRequest, wps_request: str, uuid) -> Union[WPSResponse, HTTPValid]

      Submit WPS request to corresponding WPS-REST endpoint and convert back for requested ``Accept`` content-type.

      Overrides the original execute operation, that instead will get handled by :meth:`execute_job` following
      callback from Celery Worker that handles process job creation and monitoring.

      If ``Accept`` is JSON, the result is directly returned from :meth:`_submit_job`.
      If ``Accept`` is XML or undefined, :class:`WorkerExecuteResponse` converts the received JSON with XML template.


   .. method:: execute_job(self, process_id, wps_inputs, wps_outputs, mode, job_uuid)

      Real execution of the process by active Celery Worker.



.. function:: get_pywps_service(environ=None, is_worker=False)

   Generates the PyWPS Service that provides *older* WPS-1/2 XML endpoint.


