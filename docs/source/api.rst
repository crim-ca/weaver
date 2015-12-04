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

.. warning::

   When accessing the default HTTPS service you need to deactivate SSL verfication. See ``twitcher/twitcherctl.py`` how this can be done. You may also use the following code::
   
   >> from twitcher import twitcherctl
   >> server = twitcherctl._create_server('https://localhost:38083/RPC2', verify_ssl=False)

The `XML-RPC <http://xmlrpc.scripting.com/>`_ interface can also be accessed from Java and other languages.


Manage Access Tokens
====================

Generate Token
--------------

.. code-block:: python

    server.gentoken(valid_in_hours, user_environ)


Remove Token
------------

.. code-block:: python

    server.revoke(token)


Remove all Tokens
-----------------

.. code-block:: python

    server.clean()

Manage OWS Service Registry
===========================

Register Service
----------------

.. code-block:: python

    server.register(url, name)

Unregister Service
----------------

.. code-block:: python

    server.unregister(name)

Remove all Services
-------------------

.. code-block:: python

    server.purge()


List registered Services
-------------------

.. code-block:: python

    server.status()


