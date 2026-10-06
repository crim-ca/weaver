.. include:: references.rst

********
Tutorial
********

.. contents::
    :local:
    :depth: 2


Using the WPS application included in Weaver
==============================================

Install `Weaver` (see: `Installation`_) and make sure all required components
are started and running (see: `Configuration`_).

Then, execute the desired `WPS`_ or |ogc-proc-long| request according to desired operation mode and version.

For all following examples, ``${WEAVER_URL}`` is used to specify your application URL endpoint configuration.
By default, this value should be ``localhost:4001``.

.. _WPS: https://www.ogc.org/standard/wps/
.. _WPS-REST: https://github.com/opengeospatial/wps-rest-binding

.. note::
    This tutorial section is a minimal introduction to available requests and endpoints. Please refer to
    `processes`_ for further details, such as detailed request payload contents, types of processes and additional
    operations that compose a typical process execution workflow. Similarly, refer to
    :ref:`Application Package` for further details about the definition of the reference application executed
    by the deployed processes.

.. _configuration: docs/source/configuration.rst
.. _installation: docs/source/installation.rst
.. _processes: docs/source/processes.rst
.. _package: docs/source/package.rst

WPS-1/2 requests
--------------------

Specifying the appropriate ``version=<1.0.0|2.0.0>`` parameter in the URL as required.

Run a WPS-1/WPS-2 ``GetCapabilities`` request:

.. code-block:: shell

    curl -k "${WEAVER_URL}/ows/wps?service=wps&request=getcapabilities"

You should receive an XML response listing service details and available processes.

Run a WPS-1/WPS-2 ``DescribeProcess`` request (built-in process ``jsonarray2netcdf``):

.. code-block:: shell

    curl -k "${WEAVER_URL}/ows/wps?service=wps&request=describeprocess&identifier=jsonarray2netcdf&version=1.0.0"

This will provide you with an XML response listing the specific process details such and inputs/outputs and description.

We can now use the process to execute a WPS request. To do so, we will need some input data files to call it.
First, let's create a JSON file with some *dummy* NetCDF file reference for demonstration purpose.

The :ref:`Builtin Processes <proc_builtin>` only accept local files from `Weaver` and :term:`CWL` managed temporary
directories, or files served through a remote URL, for security reasons. Therefore, we will serve the example files
from a directory that is reachable by the Weaver instance:

.. code-block:: shell

    echo 'Test WPS' > /tmp/test.nc
    echo '["http://localhost:8000/test.nc"]' > /tmp/test.json
    python -m http.server 8000 --directory /tmp

The example assumes that `Weaver` can reach the file server at ``http://localhost:8000``. When it is running in a
container or on another host, replace ``localhost`` with a hostname or IP address reachable from that instance.

Then, run the WPS-1/WPS-2 ``Execute`` request (built-in process ``jsonarray2netcdf``) as follow:

.. code-block:: shell

    curl -k "${WEAVER_URL}/ows/wps?service=wps&request=execute&identifier=jsonarray2netcdf&version=1.0.0 \
        &DataInputs=input=http://localhost:8000/test.json"

The execution of the process should read the JSON list with our dummy NetCDF file and make it available (as a copy)
on the output parameter named ``output`` with a path matching the configured output WPS path of the application.

.. note::
    All above WPS-1/2 requests suppose that configuration setting ``weaver.wps_path = /ows/wps`` (default value).
    The request URL have to be adjusted accordingly if this parameter is modified.

OGC API - Processes requests
----------------------------

All previous operations for listing available processes (``GetCapabilities``), describing or executing a WPS-1/2
process can also be accomplished using the :term:`OGC API - Processes` REST JSON interface.

For instance, listing processes is done like so:

.. code-block:: shell

    curl -k "${WEAVER_URL}/processes"

Individual process details (``DescribeProcess``) can be obtained with the following method
(e.g.: built-in process ``jsonarray2netcdf`` in this case):

.. code-block:: shell

    curl -k "${WEAVER_URL}/processes/jsonarray2netcdf"


And execution of this process can be accomplished with the following request:

.. code-block:: shell

    curl -X POST "${WEAVER_URL}/processes/jsonarray2netcdf/jobs" \
           -H "Content-Type: application/json" \
           -d '{"inputs": [{"id": "input", "href": "http://localhost:8000/test.json"}],
                "outputs": [{"id": "output", "transmissionMode": "reference"}],
                "response": "document",
                "mode": "async"}'

The JSON response should provide a ``location`` field specifying where the job status can be verified.
Upon *successful* job completion, an ``output`` reference URL should have been generated just as with
the WPS-1/2 example.

The :term:`OGC API - Processes` interface allows further operations such as :term:`Job` monitoring,
specific output listing, log reporting, etc.
For all available operations and specific details about them, please refer to `OpenAPI schemas`_
(they will also be rendered on route ``${WEAVER_URL}/api`` when running `Weaver` application).

.. _`OpenAPI schemas`: https://pavics-weaver.readthedocs.io/en/latest/api.html

Next Steps
================================

Have a look to the :ref:`Processes`, :ref:`application-package` and :ref:`FAQ` sections.

The full |oas|_ is also available for request details to target a :ref:`running` service.
Alternatively, the :ref:`cli` can also be employed to facilitate interactions with a `Weaver` service.
