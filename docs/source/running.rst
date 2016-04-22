.. _running:

****************
Running Twitcher
****************

.. contents::
    :local:
    :depth: 2


Running twitcher service
========================

The twitcher service is controlled by `supervisor <http://supervisord.org/>`_. The twitcher installation comes with a Makefile which provides shortcut commands for supervisor:

.. code-block:: sh

    $ cd twitcher   # cd into twitcher installation directory
    $ make status   # show running supervisor services (incl. twitcher)
    $ make start    # start all supervisor services (incl. twitcher)
    $ make stop    # stop ...
    $ make restart    # restart ...



Running `twitcherctl`
=====================


The ``twitcherctl`` is a command line tool to control the twitcher service. It uses the XML-RPC api of twitcher to generate access tokens and to register OWS services.

``twitcherctl`` is part of the twitcher installation. When you have installed twitcher from GitHub then start ``twitcherctl`` with:

.. code-block:: sh

   $ cd twitcher   # cd into twitcher installation directory
   $ bin/twitcherctl -h


`twitcherctl` Commands and Options
------------------------------------------

``twitcherctl`` has the following command line options:

-h, --help

   Print usage message and exit

-s, --serverurl

   URL on which twitcher server is listening (default "https://localhost:38083/").

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
clean               
    Removes all access tokens.
status              
    Lists all registered OWS services used by OWS proxy.
purge               
    Removes all OWS services from the registry.
register            
   Adds OWS service to the registry to be used by the OWS proxy.
unregister          
   Removes OWS service from the registry.


Generate an access token
------------------------

See the available options:

.. code-block:: sh

   $ bin/twitcherctl -k gentoken -h

Generate an access token valid for 24 hours (use ``-k`` to avoid validation of HTTPS server certificate):

.. code-block:: sh
  
   $ bin/twitcherctl -k gentoken -H 24


Generate an access token and set the ``PYWPS_CFG`` environment variable used by the PyWPS implementation via the *wsgi environ*:

.. code-block:: sh
  
   $ bin/twitcherctl -k gentoken -H 12 -e PYWPS_CFG=/path/to/my/pywps.cfg


Register an OWS Service for the OWS Proxy
-----------------------------------------

See the available options:

.. code-block:: sh

   bin/twitcherctl -k register -h

Register a local WPS service:

.. code-block:: sh

   $ bin/twitcherctl -k register http://localhost:8094/wps
   tiny_buzzard

You can use the ``--name`` option to provide a name (used by the OWS proxy). Otherwise a nice name will be generated.


Show Status of Twitcher
-----------------------

Currently the ``status`` command shows only the registered OWS services:

.. code-block:: sh

   $ bin/twitcherctl -k status
   [{'url': 'http://localhost:8094/wps', 'proxy_url': 'https://localhost:38083/ows/proxy/tiny_buzzard', 'type': 'wps', 'name': 'tiny_buzzard'}]

Using OWSProxy
==============

See the :ref:`tutorial`.


Using WPS Application
=====================

See the :ref:`tutorial`.   

Use Twitcher components in your Pyramid Application
===================================================

Instead of running twitcher as a service you can also include twitcher components (OWS Security Middleware, OWS Proxy) in a Pyramid application.

Include OWS Security Middleware
-------------------------------

Use the Pyramid ``include`` statement. See the ``twitcher/__init__py`` as an example. [..]


Include OWS Proxy
-----------------

Use the Pyramid ``include`` statement. See the ``twitcher/__init__py`` as an example. [..]
