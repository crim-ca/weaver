:mod:`weaver.wps_restapi.quotation.quotes`
==========================================

.. py:module:: weaver.wps_restapi.quotation.quotes


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: process_quote_estimator(process)

   :param process: instance of :class:`weaver.datatype.Process` for which to evaluate the quote.
   :return: dict of {price, currency, estimatedTime} values for the process quote.


.. function:: request_quote(request)

   Request a quotation for a process.


.. function:: get_quote_list(request)

   Get list of quotes IDs.


.. function:: get_quote_info(request)

   Get quote information.


.. function:: execute_quote(request)

   Execute a quoted process.


