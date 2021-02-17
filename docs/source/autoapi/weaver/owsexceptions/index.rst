:mod:`weaver.owsexceptions`
===========================

.. py:module:: weaver.owsexceptions

.. autoapi-nested-parse::

   Exceptions are based on :mod:`pyramid.httpexceptions` and :mod:`pywps.exceptions` to handle more cases where they can
   be caught whether the running process is via :mod:`weaver` or through :mod:`pywps` service.

   Furthermore, interrelation with :mod:`weaver.exceptions` classes (with base
   :exception:`weaver.exceptions.WeaverException`) also employ specific :exception:`OWSExceptions` definitions to provide
   specific error details.



Module Contents
---------------

.. py:exception:: OWSException(detail=None, value=None, **kw)



   Represents a WSGI response.

   If no arguments are passed, creates a :class:`~Response` that uses a
   variety of defaults. The defaults may be changed by sub-classing the
   :class:`~Response`. See the :ref:`sub-classing notes
   <response_subclassing_notes>`.

   :cvar ~Response.body: If ``body`` is a ``text_type``, then it will be
       encoded using either ``charset`` when provided or ``default_encoding``
       when ``charset`` is not provided if the ``content_type`` allows for a
       ``charset``. This argument is mutually  exclusive with ``app_iter``.

   :vartype ~Response.body: bytes or text_type

   :cvar ~Response.status: Either an :class:`int` or a string that is
       an integer followed by the status text. If it is an integer, it will be
       converted to a proper status that also includes the status text.  Any
       existing status text will be kept. Non-standard values are allowed.

   :vartype ~Response.status: int or str

   :cvar ~Response.headerlist: A list of HTTP headers for the response.

   :vartype ~Response.headerlist: list

   :cvar ~Response.app_iter: An iterator that is used as the body of the
       response. Should conform to the WSGI requirements and should provide
       bytes. This argument is mutually exclusive with ``body``.

   :vartype ~Response.app_iter: iterable

   :cvar ~Response.content_type: Sets the ``Content-Type`` header. If no
       ``content_type`` is provided, and there is no ``headerlist``, the
       ``default_content_type`` will be automatically set. If ``headerlist``
       is provided then this value is ignored.

   :vartype ~Response.content_type: str or None

   :cvar conditional_response: Used to change the behavior of the
       :class:`~Response` to check the original request for conditional
       response headers. See :meth:`~Response.conditional_response_app` for
       more information.

   :vartype conditional_response: bool

   :cvar ~Response.charset: Adds a ``charset`` ``Content-Type`` parameter. If
       no ``charset`` is provided and the ``Content-Type`` is text, then the
       ``default_charset`` will automatically be added.  Currently the only
       ``Content-Type``'s that allow for a ``charset`` are defined to be
       ``text/*``, ``application/xml``, and ``*/*+xml``. Any other
       ``Content-Type``'s will not have a ``charset`` added. If a
       ``headerlist`` is provided this value is ignored.

   :vartype ~Response.charset: str or None

   All other response attributes may be set on the response by providing them
   as keyword arguments. A :exc:`TypeError` will be raised for any unexpected
   keywords.

   .. _response_subclassing_notes:

   **Sub-classing notes:**

   * The ``default_content_type`` is used as the default for the
     ``Content-Type`` header that is returned on the response. It is
     ``text/html``.

   * The ``default_charset`` is used as the default character set to return on
     the ``Content-Type`` header, if the ``Content-Type`` allows for a
     ``charset`` parameter. Currently the only ``Content-Type``'s that allow
     for a ``charset`` are defined to be: ``text/*``, ``application/xml``, and
     ``*/*+xml``. Any other ``Content-Type``'s will not have a ``charset``
     added.

   * The ``unicode_errors`` is set to ``strict``, and access on a
     :attr:`~Response.text` will raise an error if it fails to decode the
     :attr:`~Response.body`.

   * ``default_conditional_response`` is set to ``False``. This flag may be
     set to ``True`` so that all ``Response`` objects will attempt to check
     the original request for conditional response headers. See
     :meth:`~Response.conditional_response_app` for more information.

   * ``default_body_encoding`` is set to 'UTF-8' by default. It exists to
     allow users to get/set the ``Response`` object using ``.text``, even if
     no ``charset`` has been set for the ``Content-Type``.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = NoApplicableCode

      

   .. attribute:: value
      

      

   .. attribute:: locator
      :annotation: = NoApplicableCode

      

   .. attribute:: explanation
      :annotation: = Unknown Error

      

   .. attribute:: page_template
      

      

   .. attribute:: exception
      

      

   .. method:: json_formatter(status: str, body: str, title: str, environ: SettingsType) -> JSON
      :staticmethod:


   .. method:: prepare(self, environ)


   .. method:: wsgi_response(self)
      :property:



.. py:exception:: OWSAccessForbidden(*args, **kwargs)



   Represents a WSGI response.

   If no arguments are passed, creates a :class:`~Response` that uses a
   variety of defaults. The defaults may be changed by sub-classing the
   :class:`~Response`. See the :ref:`sub-classing notes
   <response_subclassing_notes>`.

   :cvar ~Response.body: If ``body`` is a ``text_type``, then it will be
       encoded using either ``charset`` when provided or ``default_encoding``
       when ``charset`` is not provided if the ``content_type`` allows for a
       ``charset``. This argument is mutually  exclusive with ``app_iter``.

   :vartype ~Response.body: bytes or text_type

   :cvar ~Response.status: Either an :class:`int` or a string that is
       an integer followed by the status text. If it is an integer, it will be
       converted to a proper status that also includes the status text.  Any
       existing status text will be kept. Non-standard values are allowed.

   :vartype ~Response.status: int or str

   :cvar ~Response.headerlist: A list of HTTP headers for the response.

   :vartype ~Response.headerlist: list

   :cvar ~Response.app_iter: An iterator that is used as the body of the
       response. Should conform to the WSGI requirements and should provide
       bytes. This argument is mutually exclusive with ``body``.

   :vartype ~Response.app_iter: iterable

   :cvar ~Response.content_type: Sets the ``Content-Type`` header. If no
       ``content_type`` is provided, and there is no ``headerlist``, the
       ``default_content_type`` will be automatically set. If ``headerlist``
       is provided then this value is ignored.

   :vartype ~Response.content_type: str or None

   :cvar conditional_response: Used to change the behavior of the
       :class:`~Response` to check the original request for conditional
       response headers. See :meth:`~Response.conditional_response_app` for
       more information.

   :vartype conditional_response: bool

   :cvar ~Response.charset: Adds a ``charset`` ``Content-Type`` parameter. If
       no ``charset`` is provided and the ``Content-Type`` is text, then the
       ``default_charset`` will automatically be added.  Currently the only
       ``Content-Type``'s that allow for a ``charset`` are defined to be
       ``text/*``, ``application/xml``, and ``*/*+xml``. Any other
       ``Content-Type``'s will not have a ``charset`` added. If a
       ``headerlist`` is provided this value is ignored.

   :vartype ~Response.charset: str or None

   All other response attributes may be set on the response by providing them
   as keyword arguments. A :exc:`TypeError` will be raised for any unexpected
   keywords.

   .. _response_subclassing_notes:

   **Sub-classing notes:**

   * The ``default_content_type`` is used as the default for the
     ``Content-Type`` header that is returned on the response. It is
     ``text/html``.

   * The ``default_charset`` is used as the default character set to return on
     the ``Content-Type`` header, if the ``Content-Type`` allows for a
     ``charset`` parameter. Currently the only ``Content-Type``'s that allow
     for a ``charset`` are defined to be: ``text/*``, ``application/xml``, and
     ``*/*+xml``. Any other ``Content-Type``'s will not have a ``charset``
     added.

   * The ``unicode_errors`` is set to ``strict``, and access on a
     :attr:`~Response.text` will raise an error if it fails to decode the
     :attr:`~Response.body`.

   * ``default_conditional_response`` is set to ``False``. This flag may be
     set to ``True`` so that all ``Response`` objects will attempt to check
     the original request for conditional response headers. See
     :meth:`~Response.conditional_response_app` for more information.

   * ``default_body_encoding`` is set to 'UTF-8' by default. It exists to
     allow users to get/set the ``Response`` object using ``.text``, even if
     no ``charset`` has been set for the ``Content-Type``.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = AccessForbidden

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Access to this service is forbidden.

      


.. py:exception:: OWSNotFound(*args, **kwargs)



   Represents a WSGI response.

   If no arguments are passed, creates a :class:`~Response` that uses a
   variety of defaults. The defaults may be changed by sub-classing the
   :class:`~Response`. See the :ref:`sub-classing notes
   <response_subclassing_notes>`.

   :cvar ~Response.body: If ``body`` is a ``text_type``, then it will be
       encoded using either ``charset`` when provided or ``default_encoding``
       when ``charset`` is not provided if the ``content_type`` allows for a
       ``charset``. This argument is mutually  exclusive with ``app_iter``.

   :vartype ~Response.body: bytes or text_type

   :cvar ~Response.status: Either an :class:`int` or a string that is
       an integer followed by the status text. If it is an integer, it will be
       converted to a proper status that also includes the status text.  Any
       existing status text will be kept. Non-standard values are allowed.

   :vartype ~Response.status: int or str

   :cvar ~Response.headerlist: A list of HTTP headers for the response.

   :vartype ~Response.headerlist: list

   :cvar ~Response.app_iter: An iterator that is used as the body of the
       response. Should conform to the WSGI requirements and should provide
       bytes. This argument is mutually exclusive with ``body``.

   :vartype ~Response.app_iter: iterable

   :cvar ~Response.content_type: Sets the ``Content-Type`` header. If no
       ``content_type`` is provided, and there is no ``headerlist``, the
       ``default_content_type`` will be automatically set. If ``headerlist``
       is provided then this value is ignored.

   :vartype ~Response.content_type: str or None

   :cvar conditional_response: Used to change the behavior of the
       :class:`~Response` to check the original request for conditional
       response headers. See :meth:`~Response.conditional_response_app` for
       more information.

   :vartype conditional_response: bool

   :cvar ~Response.charset: Adds a ``charset`` ``Content-Type`` parameter. If
       no ``charset`` is provided and the ``Content-Type`` is text, then the
       ``default_charset`` will automatically be added.  Currently the only
       ``Content-Type``'s that allow for a ``charset`` are defined to be
       ``text/*``, ``application/xml``, and ``*/*+xml``. Any other
       ``Content-Type``'s will not have a ``charset`` added. If a
       ``headerlist`` is provided this value is ignored.

   :vartype ~Response.charset: str or None

   All other response attributes may be set on the response by providing them
   as keyword arguments. A :exc:`TypeError` will be raised for any unexpected
   keywords.

   .. _response_subclassing_notes:

   **Sub-classing notes:**

   * The ``default_content_type`` is used as the default for the
     ``Content-Type`` header that is returned on the response. It is
     ``text/html``.

   * The ``default_charset`` is used as the default character set to return on
     the ``Content-Type`` header, if the ``Content-Type`` allows for a
     ``charset`` parameter. Currently the only ``Content-Type``'s that allow
     for a ``charset`` are defined to be: ``text/*``, ``application/xml``, and
     ``*/*+xml``. Any other ``Content-Type``'s will not have a ``charset``
     added.

   * The ``unicode_errors`` is set to ``strict``, and access on a
     :attr:`~Response.text` will raise an error if it fails to decode the
     :attr:`~Response.body`.

   * ``default_conditional_response`` is set to ``False``. This flag may be
     set to ``True`` so that all ``Response`` objects will attempt to check
     the original request for conditional response headers. See
     :meth:`~Response.conditional_response_app` for more information.

   * ``default_body_encoding`` is set to 'UTF-8' by default. It exists to
     allow users to get/set the ``Response`` object using ``.text``, even if
     no ``charset`` has been set for the ``Content-Type``.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = NotFound

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Resource does not exist.

      


.. py:exception:: OWSNotAcceptable(*args, **kwargs)



   Represents a WSGI response.

   If no arguments are passed, creates a :class:`~Response` that uses a
   variety of defaults. The defaults may be changed by sub-classing the
   :class:`~Response`. See the :ref:`sub-classing notes
   <response_subclassing_notes>`.

   :cvar ~Response.body: If ``body`` is a ``text_type``, then it will be
       encoded using either ``charset`` when provided or ``default_encoding``
       when ``charset`` is not provided if the ``content_type`` allows for a
       ``charset``. This argument is mutually  exclusive with ``app_iter``.

   :vartype ~Response.body: bytes or text_type

   :cvar ~Response.status: Either an :class:`int` or a string that is
       an integer followed by the status text. If it is an integer, it will be
       converted to a proper status that also includes the status text.  Any
       existing status text will be kept. Non-standard values are allowed.

   :vartype ~Response.status: int or str

   :cvar ~Response.headerlist: A list of HTTP headers for the response.

   :vartype ~Response.headerlist: list

   :cvar ~Response.app_iter: An iterator that is used as the body of the
       response. Should conform to the WSGI requirements and should provide
       bytes. This argument is mutually exclusive with ``body``.

   :vartype ~Response.app_iter: iterable

   :cvar ~Response.content_type: Sets the ``Content-Type`` header. If no
       ``content_type`` is provided, and there is no ``headerlist``, the
       ``default_content_type`` will be automatically set. If ``headerlist``
       is provided then this value is ignored.

   :vartype ~Response.content_type: str or None

   :cvar conditional_response: Used to change the behavior of the
       :class:`~Response` to check the original request for conditional
       response headers. See :meth:`~Response.conditional_response_app` for
       more information.

   :vartype conditional_response: bool

   :cvar ~Response.charset: Adds a ``charset`` ``Content-Type`` parameter. If
       no ``charset`` is provided and the ``Content-Type`` is text, then the
       ``default_charset`` will automatically be added.  Currently the only
       ``Content-Type``'s that allow for a ``charset`` are defined to be
       ``text/*``, ``application/xml``, and ``*/*+xml``. Any other
       ``Content-Type``'s will not have a ``charset`` added. If a
       ``headerlist`` is provided this value is ignored.

   :vartype ~Response.charset: str or None

   All other response attributes may be set on the response by providing them
   as keyword arguments. A :exc:`TypeError` will be raised for any unexpected
   keywords.

   .. _response_subclassing_notes:

   **Sub-classing notes:**

   * The ``default_content_type`` is used as the default for the
     ``Content-Type`` header that is returned on the response. It is
     ``text/html``.

   * The ``default_charset`` is used as the default character set to return on
     the ``Content-Type`` header, if the ``Content-Type`` allows for a
     ``charset`` parameter. Currently the only ``Content-Type``'s that allow
     for a ``charset`` are defined to be: ``text/*``, ``application/xml``, and
     ``*/*+xml``. Any other ``Content-Type``'s will not have a ``charset``
     added.

   * The ``unicode_errors`` is set to ``strict``, and access on a
     :attr:`~Response.text` will raise an error if it fails to decode the
     :attr:`~Response.body`.

   * ``default_conditional_response`` is set to ``False``. This flag may be
     set to ``True`` so that all ``Response`` objects will attempt to check
     the original request for conditional response headers. See
     :meth:`~Response.conditional_response_app` for more information.

   * ``default_body_encoding`` is set to 'UTF-8' by default. It exists to
     allow users to get/set the ``Response`` object using ``.text``, even if
     no ``charset`` has been set for the ``Content-Type``.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = NotAcceptable

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Cannot produce requested Accept format.

      


.. py:exception:: OWSNoApplicableCode(*args, **kwargs)



   WPS Bad Request Exception

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = NoApplicableCode

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Undefined error

      


.. py:exception:: OWSMissingParameterValue(*args, **kwargs)



   MissingParameterValue WPS Exception

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = MissingParameterValue

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Parameter value is missing

      


.. py:exception:: OWSInvalidParameterValue(*args, **kwargs)



   InvalidParameterValue WPS Exception

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = InvalidParameterValue

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Parameter value is not acceptable.

      


.. py:exception:: OWSNotImplemented(*args, **kwargs)



   Represents a WSGI response.

   If no arguments are passed, creates a :class:`~Response` that uses a
   variety of defaults. The defaults may be changed by sub-classing the
   :class:`~Response`. See the :ref:`sub-classing notes
   <response_subclassing_notes>`.

   :cvar ~Response.body: If ``body`` is a ``text_type``, then it will be
       encoded using either ``charset`` when provided or ``default_encoding``
       when ``charset`` is not provided if the ``content_type`` allows for a
       ``charset``. This argument is mutually  exclusive with ``app_iter``.

   :vartype ~Response.body: bytes or text_type

   :cvar ~Response.status: Either an :class:`int` or a string that is
       an integer followed by the status text. If it is an integer, it will be
       converted to a proper status that also includes the status text.  Any
       existing status text will be kept. Non-standard values are allowed.

   :vartype ~Response.status: int or str

   :cvar ~Response.headerlist: A list of HTTP headers for the response.

   :vartype ~Response.headerlist: list

   :cvar ~Response.app_iter: An iterator that is used as the body of the
       response. Should conform to the WSGI requirements and should provide
       bytes. This argument is mutually exclusive with ``body``.

   :vartype ~Response.app_iter: iterable

   :cvar ~Response.content_type: Sets the ``Content-Type`` header. If no
       ``content_type`` is provided, and there is no ``headerlist``, the
       ``default_content_type`` will be automatically set. If ``headerlist``
       is provided then this value is ignored.

   :vartype ~Response.content_type: str or None

   :cvar conditional_response: Used to change the behavior of the
       :class:`~Response` to check the original request for conditional
       response headers. See :meth:`~Response.conditional_response_app` for
       more information.

   :vartype conditional_response: bool

   :cvar ~Response.charset: Adds a ``charset`` ``Content-Type`` parameter. If
       no ``charset`` is provided and the ``Content-Type`` is text, then the
       ``default_charset`` will automatically be added.  Currently the only
       ``Content-Type``'s that allow for a ``charset`` are defined to be
       ``text/*``, ``application/xml``, and ``*/*+xml``. Any other
       ``Content-Type``'s will not have a ``charset`` added. If a
       ``headerlist`` is provided this value is ignored.

   :vartype ~Response.charset: str or None

   All other response attributes may be set on the response by providing them
   as keyword arguments. A :exc:`TypeError` will be raised for any unexpected
   keywords.

   .. _response_subclassing_notes:

   **Sub-classing notes:**

   * The ``default_content_type`` is used as the default for the
     ``Content-Type`` header that is returned on the response. It is
     ``text/html``.

   * The ``default_charset`` is used as the default character set to return on
     the ``Content-Type`` header, if the ``Content-Type`` allows for a
     ``charset`` parameter. Currently the only ``Content-Type``'s that allow
     for a ``charset`` are defined to be: ``text/*``, ``application/xml``, and
     ``*/*+xml``. Any other ``Content-Type``'s will not have a ``charset``
     added.

   * The ``unicode_errors`` is set to ``strict``, and access on a
     :attr:`~Response.text` will raise an error if it fails to decode the
     :attr:`~Response.body`.

   * ``default_conditional_response`` is set to ``False``. This flag may be
     set to ``True`` so that all ``Response`` objects will attempt to check
     the original request for conditional response headers. See
     :meth:`~Response.conditional_response_app` for more information.

   * ``default_body_encoding`` is set to 'UTF-8' by default. It exists to
     allow users to get/set the ``Response`` object using ``.text``, even if
     no ``charset`` has been set for the ``Content-Type``.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      :annotation: = NotImplemented

      

   .. attribute:: locator
      :annotation: = 

      

   .. attribute:: explanation
      :annotation: = Operation is not implemented.

      


