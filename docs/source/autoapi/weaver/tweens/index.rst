:mod:`weaver.tweens`
====================

.. py:module:: weaver.tweens


Module Contents
---------------

.. data:: LOGGER
   

   

.. data:: OWS_TWEEN_HANDLED
   :annotation: = OWS_TWEEN_HANDLED

   

.. function:: ows_response_tween(request, handler)

   Tween that wraps any API request with appropriate dispatch of error conversion to handle formatting.


.. function:: ows_response_tween_factory_excview(handler, registry)

   A tween factory which produces a tween which transforms common exceptions into OWS specific exceptions.


.. function:: ows_response_tween_factory_ingress(handler, registry)

   A tween factory which produces a tween which transforms common exceptions into OWS specific exceptions.


.. data:: OWS_RESPONSE_EXCVIEW
   

   

.. data:: OWS_RESPONSE_INGRESS
   

   

.. function:: includeme(config)


