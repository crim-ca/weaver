:mod:`weaver.exceptions`
========================

.. py:module:: weaver.exceptions

.. autoapi-nested-parse::

   Some of these error inherit from :class:`weaver.owsexceptions.OWSException` and their derived classes to allow
   :mod:`pywps` to automatically understand and render those exception if raised by an underlying :mod:`weaver` operation.



Module Contents
---------------

.. data:: LOGGER
   

   

.. py:exception:: WeaverException



   Base class of exceptions defined by :mod:`weaver` package.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = 500

      

   .. attribute:: title
      :annotation: = Internal Server Error

      


.. py:exception:: InvalidIdentifierValue



   Error indicating that an ID to be employed for following operations
   is not considered as valid to allow further processed or usage.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = 400

      

   .. attribute:: locator
      :annotation: = identifier

      


.. py:exception:: MissingIdentifierValue



   Error indicating that an ID to be employed for following operations
   was missing and cannot continue further processing or usage.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = 400

      

   .. attribute:: locator
      :annotation: = identifier

      


.. py:exception:: ServiceException



   Base exception related to a :class:`weaver.datatype.Service`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: locator
      :annotation: = service

      


.. py:exception:: ServiceNotAccessible



   Error indicating that a WPS service exists but is not visible to retrieve
   from the storage backend of an instance of :class:`weaver.store.ServiceStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: ServiceNotFound



   Error indicating that an OWS service could not be read from the
   storage backend by an instance of :class:`weaver.store.ServiceStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: ServiceRegistrationError



   Error indicating that an OWS service could not be registered in the
   storage backend by an instance of :class:`weaver.store.ServiceStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: ProcessException



   Base exception related to a :class:`weaver.datatype.Process`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: locator
      :annotation: = process

      


.. py:exception:: ProcessNotAccessible



   Error indicating that a local WPS process exists but is not visible to retrieve
   from the storage backend of an instance of :class:`weaver.store.ProcessStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: ProcessNotFound



   Error indicating that a local WPS process could not be read from the
   storage backend by an instance of :class:`weaver.store.ProcessStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: ProcessRegistrationError



   Error indicating that a WPS process could not be registered in the
   storage backend by an instance of :class:`weaver.store.ProcessStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: ProcessInstanceError



   Error indicating that the process instance passed is not supported with
   storage backend by an instance of :class:`weaver.store.ProcessStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: JobException



   Base exception related to a :class:`weaver.datatype.Job`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: locator
      :annotation: = job

      


.. py:exception:: JobNotFound



   Error indicating that a job could not be read from the
   storage backend by an instance of :class:`weaver.store.JobStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: JobRegistrationError



   Error indicating that a job could not be registered in the
   storage backend by an instance of :class:`weaver.store.JobStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: JobUpdateError



   Error indicating that a job could not be updated in the
   storage backend by an instance of :class:`weaver.store.JobStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: PackageException



   Base exception related to a :class:`weaver.processes.wps_package.Package`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: locator
      :annotation: = package

      


.. py:exception:: PackageTypeError



   Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
   could not properly parse input/output type(s) for package deployment or execution.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: PackageRegistrationError



   Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
   could not properly be registered for package deployment because of invalid prerequisite.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: PackageExecutionError



   Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
   could not properly execute the package using provided inputs and package definition.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: PackageNotFound



   Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
   could not properly retrieve the package definition using provided references.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: PayloadNotFound



   Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
   could not properly retrieve the package deploy payload using provided references.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: QuoteException



   Base exception related to a :class:`weaver.datatype.Quote`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: locator
      :annotation: = quote

      


.. py:exception:: QuoteNotFound



   Error indicating that a quote could not be read from the
   storage backend by an instance of :class:`weaver.store.QuoteStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: QuoteRegistrationError



   Error indicating that a quote could not be registered in the
   storage backend by an instance of :class:`weaver.store.QuoteStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: QuoteInstanceError



   Error indicating that a given object doesn't correspond to an expected
   instance of :class:`weaver.datatype.Quote`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: BillException



   Base exception related to a :class:`weaver.datatype.Bill`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: locator
      :annotation: = bill

      


.. py:exception:: BillNotFound



   Error indicating that a bill could not be read from the
   storage backend by an instance of :class:`weaver.store.BillStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: BillRegistrationError



   Error indicating that a bill could not be registered in the
   storage backend by an instance of :class:`weaver.store.BillStore`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:exception:: BillInstanceError



   Error indicating that a given object doesn't correspond to an expected
   instance of :class:`weaver.datatype.Bill`.

   Initialize self.  See help(type(self)) for accurate signature.


.. function:: handle_known_exceptions(function: Callable[[Any, Any], Any]) -> Callable

   Decorator that catches lower-level raised exception that are known to :mod:`weaver` but not by :mod:`pywps`.

   .. seealso::
       :class:`weaver.wps.service.WorkerService`

       Without prior handling of known internal exception, :mod:`pywps` generates by default ``500`` internal server
       error response since it doesn't know how to interpret more specific exceptions defined in :mod:`weaver`.

   The decorator simply returns the known exception such that :func:`weaver.tweens.ows_response_tween` can later
   handle it appropriately. Exceptions derived from :exception:`weaver.owsexceptions.OWSException` are employed since
   they themselves have base references to :mod:`pywps.exceptions` classes that the service can understand.

   .. warning::
       In :mod:`pywps`, ``HTTPException`` refers to :exception:`werkzeug.exceptions.HTTPException` while in
       :mod:`weaver`, it is :exception:`pyramid.httpexceptions.HTTPException`. They both offer similar interfaces and
       functionalities (headers, body, status-code, etc.), but they are not intercepted in the same try/except blocks.


.. function:: log_unhandled_exceptions(logger: logging.Logger = LOGGER, message: str = 'Unhandled exception occurred.', exception: Type[Exception] = Exception, force: bool = False, require_http: bool = True, is_request: bool = True) -> Callable

   Decorator that will raise ``exception`` with specified ``message`` if an exception is caught while execution the
   wrapped function, after logging relevant details about the caught exception with ``logger``.

   :param logger: logger to use for logging (default: use :data:`weaver.exception.LOGGER`).
   :param message: message that will be logged with details and then raised with ``exception``.
   :param exception: exception type to be raised instead of the caught exception.
   :param force: force handling of any raised exception (default: only *known* unhandled exceptions are logged).
   :param require_http:
       consider non HTTP-like exceptions as *unknown* and raise one instead
       (default: ``True`` and raises :class:`HTTPInternalServerError`, unless ``exception`` is HTTP-like).
   :param is_request: specifies if the decorator is applied onto a registered request function to handle its inputs.
   :raises exception: if an *unknown* exception was caught (or forced) during the decorated function's execution.
   :raises Exception: original exception if it is *known*.


