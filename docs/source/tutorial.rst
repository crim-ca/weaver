.. _tutorial:

********
Tutorial
********

.. contents::
    :local:
    :depth: 2


Using the WPS application included in Twitcher
==============================================

See above on how to install twitcher and make sure it is started with ``make status``:

.. code-block:: sh

    $ cd twitcher
    $ make status
    Supervisor status ...
    mongodb                          RUNNING   pid 6863, uptime 0:00:19
    nginx                            RUNNING   pid 6865, uptime 0:00:19
    twitcher                         RUNNING   pid 6864, uptime 0:00:19

If twitcher (or nginx, mongodb) is not running then start it with ``make start``.

By default the twitcher WPS application is available at the URL https://localhost:38083/ows/wps.

Run a ``GetCapabilities`` request:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps?service=wps&request=getcapabilities"

Run a ``DescribeProcess`` request:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps?service=wps&request=describeprocess&identifier=dummyprocess&version=1.0.0"

Use token to run an execute request
-----------------------------------

By default the WPS service is protected by the ``OWSSecurity`` wsgi middleware. You need to provide an access token to run an execute request.

Run an ``Exceute`` request:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps?service=wps&request=execute&identifier=dummyprocess&version=1.0.0"

Now you should get an XML error response with a message that you need to provide an access token:

.. code-block:: xml

    <?xml version="1.0" encoding="utf-8"?>
    <ExceptionReport version="1.0.0" xmlns="http://www.opengis.net/ows/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd">
        <Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">
            <ExceptionText>Access token is required to access this service.</ExceptionText>
        </Exception>
    </ExceptionReport>

First we need to generate an access token with ``twitcherctl``:

.. code-block:: sh

    $ bin/twitcherctl -k gentoken
    abc123

There are three ways how you can provide the access token:

1. as ``access_token`` HTTP parameter

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps?service=wps&request=execute&identifier=dummyprocess&version=1.0.0&access_token=abc123"

2. as the last part of the HTTP path

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps/abc123?service=wps&request=execute&identifier=dummyprocess&version=1.0.0"

3. as ``Access-Token`` header variable

.. code-block:: sh

   $ curl -k -H Access-Token:abc123 "https://localhost:38083/ows/wps?service=wps&request=execute&identifier=dummyprocess&version=1.0.0"


Change the default WPS configuration
------------------------------------

To change the default WPS configuration edit the ``custom.cfg`` and set the ``wps-cfg`` option:

.. code-block:: sh

   $ vim custom.cfg
   [settings]
   wps-cfg = /path/to/my/default/pywps.cfg


After you have changed the configuration file you must update the installation and restart the twitcher service:

.. code-block:: sh

   $ make update
   $ make restart


Use tokens to set user environment
----------------------------------

When you generate an access token you can also set enviroment variables with the ``-e`` option. Currently only the environment variables used by the WPS component (PyWPS) are possible. These are:

PYWPS_CFG
   Configuration file location
PYWPS_PROCESSES
   Directory, where the processes are stored
PYWPS_TEMPLATES
   Templates directory (structure should be similar to file:pywps/Templates)

In the following we set a PyWPS configuration:

.. code-block:: sh

   $ bin/twitcherctl -k gentoken -e PYWPS_CFG=/path/to/my/pywps.cfg
   321bca


When you access the wps with the generated token you will get the capabilites corresponding to the provided PyWPS configuration:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps?service=wps&request=getcapabilities&access_token=321bca"

.. note::

   Without the access token you will get the default capabilities of the WPS service.


Using the OWSProxy with an external WPS application
===================================================


The ``OWSProxy`` is a proxy service for OWS services. Currently it only supports WPS.

First you need an external WPS. You can use `Emu WPS service <http://emu.readthedocs.org/en/latest/>`_ from Birdhouse. 
Get it from GitHub and run the installation:

.. code-block:: sh

    $ git clone https://github.com/bird-house/emu.git
    $ cd emu
    $ make install
    $ make start

The Emu WPS service is available by default at the URL: 
http://localhost:8094/wps?service=WPS&version=1.0.0&request=GetCapabilities


Make sure Twitcher is installed and running:

.. code-block:: sh

   $ cd ../twitcher
   $ make restart
   $ make status

Register a WPS service
----------------------

Register the Emu WPS service at the Twitcher ``OWSProxy``:

.. code-block:: sh

   $ bin/twitcherctl -k register --name emu http://localhost:8094/wps

If you don't provide a name with ``--name`` option then a nice name will be generated, for example ``sleepy_flamingo``.

Use the ``status`` command to see which WPS services are registered with OWSProxy:

.. code-block:: sh

   $ bin/twitcherctl -k status
   [{'url': 'http://localhost:8094/wps', 'proxy_url': 'https://localhost:38083/ows/proxy/emu', 'type': 'wps', 'name': 'emu'}]


Access a registred service
--------------------------

By default the registered service is available at the URL https://localhost:38083/ows/proxy/{service_name}. Replace the ``service_name`` with the registered name.

Run a ``GetCapabilities`` request for the registered Emu WPS service:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/proxy/emu?service=wps&request=getcapabilities"


Run a ``DescribeProcess`` request:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/proxy/emu?service=wps&request=describeprocess&identifier=dummyprocess&version=1.0.0"

Use tokens to run an execute request
------------------------------------

By default the WPS service is protected by the ``OWSSecurity`` wsgi middleware. You need to provide an access token to run an execute request.

Run an ``Exceute`` request:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/wps?service=wps&request=execute&identifier=dummyprocess&version=1.0.0"

Now you should get an XML error response with a message that you need to provide an access token (see section above).

We need to generate an access token with ``twitcherctl``:

.. code-block:: sh

    $ bin/twitcherctl -k gentoken -H 24
    def456

By default the token has a limited life time of one hour. With the option ``-H`` you can extend the life time in hours (24 hours in this example).

You can provide the access token in three ways (see section above):

* as HTTP parameter,
* as part of the HTTP header
* or as part of the url path.

In the following example we provide the token as HTTP parameter:

.. code-block:: sh

    $ curl -k "https://localhost:38083/ows/proxy/emu?service=wps&request=execute&identifier=dummyprocess&version=1.0.0&access_token=def456"


