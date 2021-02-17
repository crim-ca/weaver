:mod:`weaver.wps_restapi.providers.providers`
=============================================

.. py:module:: weaver.wps_restapi.providers.providers


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: get_providers(request)

   Lists registered providers.


.. function:: get_capabilities(service, request)

   GetCapabilities of a wps provider.


.. function:: get_service(request)

   Get the request service using provider_id from the service store.


.. function:: add_provider(request)

   Add a provider.


.. function:: remove_provider(request)

   Remove a provider.


.. function:: get_provider(request)

   Get a provider definition (GetCapabilities).


