:mod:`weaver.processes.wps_default`
===================================

.. py:module:: weaver.processes.wps_default


Module Contents
---------------

.. data:: LOGGER
   

   

.. py:class:: HelloWPS(*_, **__)



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

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: identifier
      :annotation: = hello

      

   .. attribute:: title
      :annotation: = Say Hello

      

   .. attribute:: type
      

      

   .. method:: _handler(self, request, response)



