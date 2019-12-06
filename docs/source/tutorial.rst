.. _tutorial:

********
Tutorial
********

.. contents::
    :local:
    :depth: 2


Using the WPS application included in Weaver
==============================================

Install Weaver (see: :ref:`installation`) and make sure it is started with ``make start`` (or similar command).

Then, execute the desired `WPS`_ request according to desired operation mode and version.

.. _`WPS`: https://www.opengeospatial.org/standards/wps

WPS-1/WSP-2 requests
--------------------

Specifying the appropriate ``version=<1.0.0|2.0.0>`` parameter in the URL as required.

Run a WPS-1/WPS-2 ``GetCapabilities`` request:

.. code-block:: sh

    $ curl -k "<WEAVER_URL>/ows/wps?service=wps&request=getcapabilities"

You should receive an XML response listing service details and available processes.

Run a WPS-1/WPS-2 ``DescribeProcess`` request (built-in process ``jsonarray2netcdf``):

.. code-block:: sh

    $ curl -k "<WEAVER_URL>/ows/wps?service=wps&request=describeprocess&identifier=jsonarray2netcdf&version=1.0.0"

This will provide you with an XML response listing the specific process details such and inputs/outputs and description.

Run a WPS-1/WPS-2 ``Execute`` request (built-in process ``jsonarray2netcdf``):


# TODO: complete this demo


.. code-block:: sh

    $ curl -k "<WEAVER_URL>/ows/wps?service=wps&request=execute&identifier=jsonarray2netcdf&version=1.0.0"


WPS-3 requests
--------------

# TODO: demo

.. code-block:: sh


Managing WPS processes included in Weaver ADES/EMS
==================================================

Register a WPS service
----------------------

# TODO: demo


Access a registered service
---------------------------

# TODO: demo



