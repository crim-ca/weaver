.. _tutorial:

********
Tutorial
********

.. contents::
    :local:
    :depth: 2


Using the WPS application included in Weaver
==============================================

Install Weaver (see: :ref:`installation`) and make sure all required components
are started and running (see: :ref:`configuration`).

Then, execute the desired `WPS`_ request according to desired operation mode and version.

For all following examples, ``${WEAVER_URL}`` is used to specify your application URL endpoint configuration.
By default, this value should be ``localhost:4001``.

.. _`WPS`: https://www.opengeospatial.org/standards/wps

WPS-1/2 requests
--------------------

Specifying the appropriate ``version=<1.0.0|2.0.0>`` parameter in the URL as required.

Run a WPS-1/WPS-2 ``GetCapabilities`` request:

.. code-block:: sh

    $ curl -k "${WEAVER_URL}/ows/wps?service=wps&request=getcapabilities"

You should receive an XML response listing service details and available processes.

Run a WPS-1/WPS-2 ``DescribeProcess`` request (built-in process ``jsonarray2netcdf``):

.. code-block:: sh

    $ curl -k "${WEAVER_URL}/ows/wps?service=wps&request=describeprocess&identifier=jsonarray2netcdf&version=1.0.0"

This will provide you with an XML response listing the specific process details such and inputs/outputs and description.

We can now use the process to execute a WPS request. To do so, we will need some input data files to call it.
First, let's create a JSON file with some *dummy* NetCDF file reference for demonstration purpose.

.. code-block:: sh

    $ echo 'Test WPS' > /tmp/test.nc
    $ echo '["file:///tmp/test.nc"]' > /tmp/test.json

Then, run the WPS-1/WPS-2 ``Execute`` request (built-in process ``jsonarray2netcdf``) as follow:

.. code-block:: sh

    $ curl -k "${WEAVER_URL}/ows/wps?service=wps&request=execute&identifier=jsonarray2netcdf&version=1.0.0 \
        &DataInputs=input=file:///tmp/test.json"

The execution of the process should read the JSON list with our dummy NetCDF file and make it available (as a copy)
on the output parameter named ``output`` with a path matching the configured output WPS path of the application.

WPS-3 requests
--------------

All previous operations for listing available processes (``GetCapabilities``), describing or executing a WPS-1/2
process can also be accomplished using the WPS-3 REST JSON interface. For instance, listing processes is done like so:

.. code-block:: sh

    $ curl -k "${WEAVER_URL}/processes"

Individual process details (``DescribeProcess``) can be obtained with the following method
(e.g.: built-in process ``jsonarray2netcdf`` in this case):

.. code-block:: sh

    $ curl -k "${WEAVER_URL}/processes/jsonarray2netcdf"


And execution of this process can be accomplished with the following request:

.. code-block:: sh

    $ curl -X POST "${WEAVER_URL}/processes/jsonarray2netcdf/jobs" \
           -H "Content-Type: application/json" \
           -d '{"inputs": [{"id": "input", "href": "file:///tmp/test.json"}],
                "outputs": [{"id": "output", "transmissionMode": "reference"}],
                "response": "document",
                "mode": "async"}'


The JSON response should provide a ``location`` field specifying where the job status can be verified.
Upon *successful* job completion, an ``output`` reference URL should have been generated just as with
the WPS-1/2 example.


The WPS-3 interface allows further operations such as job monitoring, specific output listing, log reporting, etc.
For all available operations and specific details about them, please refer to the *OpenAPI* schemas that will be
rendered on route ``${WEAVER_URL}/api`` when running `Weaver` application.


Managing WPS processes included in Weaver ADES/EMS
==================================================

Register a new WPS process
--------------------------

.. todo:: complete demo docs


Access a registered process
---------------------------

.. todo:: complete demo docs, stuff about process visibility



