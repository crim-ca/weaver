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
   server = xmlrpclib.Server('https://localhost:5000/RPC2')

.. warning::

   When accessing the default HTTPS service you need to deactivate SSL verfication. See ``twitcher/client.py`` how this can be done. You may also use the following code::

   >> from twitcher import client
   >> server = client._create_server('https://localhost:5000/RPC2', verify_ssl=False)

The `XML-RPC <http://xmlrpc.scripting.com/>`_ interface can also be accessed from Java and other languages.

See the ``twitcher/rpcinterface.py`` module for the available xmlrpc methods.
