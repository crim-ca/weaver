.. _api:

*************************
XML-RPC API Documentation
*************************

.. contents::
    :local:
    :depth: 2


To use the XML-RPC interface, connect to twitcher’s HTTPS port with any XML-RPC client library and run commands against it. An example of doing this using Python’s ``xmlrpclib`` client library is as follows.

.. code-block:: python

   import xmlrpclib
   server = xmlrpclib.Server('https://localhost:38083/RPC2')

