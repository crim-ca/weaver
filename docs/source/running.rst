.. _running:

****************
Running weaver
****************

.. contents::
    :local:
    :depth: 2


Running weaver service
========================

The weaver service is controlled by `supervisor <http://supervisord.org/>`_. The weaver installation comes with a Makefile which provides shortcut commands for supervisor:

.. code-block:: sh

    $ cd weaver   # cd into weaver installation directory
    $ make status   # show running supervisor services (incl. weaver)
    $ make start    # start all supervisor services (incl. weaver)
    $ make stop    # stop ...
    $ make restart    # restart ...



Running `weaverctl`
=====================


The ``weaverctl`` is a command line tool to control the weaver service. It uses the XML-RPC api of weaver to generate access tokens and to register OWS services.

``weaverctl`` is part of the weaver installation. When you have installed weaver from GitHub then start ``weaverctl`` with:

.. code-block:: sh

   $ cd weaver   # cd into weaver installation directory
   $ bin/weaverctl -h


`weaverctl` Commands and Options
------------------------------------------

``weaverctl`` has the following command line options:

-h, --help

   Print usage message and exit

-s, --serverurl

   URL on which weaver server is listening (default "https://localhost:38083/").

-u, --username

   Username to use for authentication with server

-p, --password

   Password to use for authentication with server

-k, --insecure

   Don't validate the server's certificate.

List of available commands:

gentoken
    Generates an access token.
revoke
    Removes given access token.
list
    Lists all registered OWS services used by OWS proxy.
clear
    Removes all OWS services from the registry.
register
   Adds OWS service to the registry to be used by the OWS proxy.
unregister
   Removes OWS service from the registry.


Generate an access token
------------------------

See the available options:

.. code-block:: sh

   $ bin/weaverctl -k gentoken -h

Generate an access token valid for 24 hours (use ``-k`` to avoid validation of HTTPS server certificate):

.. code-block:: sh

   $ bin/weaverctl -k gentoken -H 24


Generate an access token and set the ``PYWPS_CFG`` environment variable used by the PyWPS implementation via the *wsgi environ*:

.. code-block:: sh

   $ bin/weaverctl -k gentoken -H 12 -e PYWPS_CFG=/path/to/my/pywps.cfg


Register an OWS Service for the OWS Proxy
-----------------------------------------

See the available options:

.. code-block:: sh

   bin/weaverctl -k register -h

Register a local WPS service:

.. code-block:: sh

   $ bin/weaverctl -k register http://localhost:8094/wps
   tiny_buzzard

You can use the ``--name`` option to provide a name (used by the OWS proxy). Otherwise a nice name will be generated.


Show Status of weaver
-----------------------

Currently the ``status`` command shows only the registered OWS services:

.. code-block:: sh

   $ bin/weaverctl -k list
   [{'url': 'http://localhost:8094/wps', 'proxy_url': 'https://localhost:38083/ows/proxy/tiny_buzzard', 'type': 'wps', 'name': 'tiny_buzzard'}]

Using OWSProxy
==============

See the :ref:`tutorial`.


Using WPS Application
=====================

See the :ref:`tutorial`.

Use weaver components in your Pyramid Application
===================================================

Instead of running weaver as a service you can also include weaver components (OWS Security Middleware, OWS Proxy) in a Pyramid application.

Include OWS Security Middleware
-------------------------------

Use the Pyramid ``include`` statement. See the ``weaver/__init__py`` as an example. [..]


Include OWS Proxy
-----------------

Use the Pyramid ``include`` statement. See the ``weaver/__init__py`` as an example. [..]
