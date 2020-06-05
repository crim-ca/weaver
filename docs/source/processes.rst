.. _processes:

**********
Processes
**********

Type of Processes
=====================

`Weaver` supports multiple type of processes, as listed below.
Each one of them are accessible through the same API interface, but they have different implications.

- Builtin
- WPS-1/2
- WPS-3 (WPS-REST)
- ESGF-CWT
- Workflow
- Remote Provider

Builtin
-------

These processes come pre-packaged with `Weaver`. They will be available directly on startup of the application and
re-updated on each boot to make sure internal database references are updated with any source code changes.

Theses processes typically correspond to utility operations. They are specifically useful when employed as
`step` within a `Workflow`_ process that requires data-type conversion between input/output of similar, but not
perfectly, compatible definitions.

For example, the process :py:mod:`weaver.processes.builtin.jsonarray2netcdf` takes a single input JSON file which
contains an array-list of NetCDF file references, and returns them directly as the corresponding list of output files.
These two different file formats (single JSON to multiple NetCDF) can then be used to map two processes with these
respective output and inputs.

WPS-1/2
-------

This kind of process corresponds to


Workflow
----------


Remote Provider
--------------------

Remote provider processes correspond to a remote service that provides similar interfaces as supported by `Weaver`.
For example, a remote WPS-1 XML endpoint can be referenced as a provider. When a `registered provider`_ is accessed,
for example to list is processes capabilities (see `GetCapabilities`_), `Weaver` will send the corresponding request
to the remote server and reply with parsed results, as if they were registered locally.

Since remote providers obviously require access to the remote service, `Weaver` will only be able to provide results
if the service is accessible with respect to standard implementation features.

The main advantage of using `Weaver`'s endpoint rather than directly accessing the referenced remote provider processes
is in the case of limited functionality offered by the service. For instance, WPS-1 do not always offer `GetStatus`_
feature, and there is no extensive job monitoring availability. Since `Weaver` *wraps* the original reference with its
own endpoints, these features indirectly become employable. On top of this, registering remote providers into `Weaver`
allows the user to use it as a central hub to keep references to all his accessible services and dispatch jobs from a
common location.

.. _`registered provider`: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Providers%2Fpaths%2F~1providers%2Fpost


Managing processes included in Weaver ADES/EMS
==================================================

Following steps represent the typical steps applied to deploy a process, execute it and retrieve the results.

.. _Deploy:
Register a new process (Deploy)
-----------------------------------------

Deployment of a new process is accomplished through the ``POST {WEAVER_URL}/processes`` |deploy-req|_.
The request body requires mainly two components:

- ``processDescription``: defines the process identifier, metadata, inputs, outputs, and some execution specifications.
- ``executionUnit``: defines the main core details of the `Application Package`_.

.. |deploy-req| replace:: request
.. _deploy-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes%2Fpost
.. _Application Package: docs/source/package.rst

Upon deploy request, `Weaver` will either respond with a successful result, or with the appropriate error message,
whether caused by conflicting ID, invalid definitions or other parsing issues. A successful process deployment will
result in this process to become available for following steps.

.. warning::
    When a process is deployed, it is not necessarily available immediately. This is because process *visibility* also
    needs to be updated. The process must be made *public* to allow its discovery. For updating visibility, please
    refer to the ``PUT {WEAVER_URL}/processes/{id}/visibility`` |vis-req|_.

.. |vis-req| replace:: request
.. _vis-req: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1visibility%2Fput

After deployment and visibility preconditions have been met, the corresponding process should become available
through `DescribeProcess`_ requests and other routes that depend on an existing process.

Note that when a process is deployed using the WPS-REST interface, it also becomes available through the WPS-1/2
interface with the same identifier and definition. Because of compatibility limitations, some parameters in the
WPS-1/2 might not be perfectly mapped to the equivalent or adjusted WPS-REST interface, although this concerns mostly
only new features such as status monitoring. For most traditional use cases, properties are mapped between the two
interfaces, but it is recommended to use the WPS-REST one because of the added features.

.. _GetCapabilities:
.. _DescribeProcess:
Access registered process(es) (GetCapabilities, DescribeProcess)
------------------------------------------------------------------------

Available processes can all be listed using |getcap-req|_ request. This request will return all locally registered
process summaries. Other return formats and filters are also available according to provided request query parameters.
Note that processes not marked with *public visibility* will not be listed in this result.

.. |getcap-req| replace:: ``GET /processes`` (``GetCapabilities``)
.. _getcap-req: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Processes%2Fpaths%2F~1processes%2Fget
.. |describe-req| replace:: ``GET /processes/{id}`` (``DescribeProcess``)
.. _describe-req: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget

For more specific process details, the |describe-req|_ request should be used. This will return all information
that define the process references and expected inputs/outputs.

.. note::
    For *remote processes* (see: `Remote Provider`_), `Provider requests`_ are also available for more fine-grained
    search of underlying processes. These processes are not necessarily listed as local processes, and will therefore
    sometime not yield any result if using the typical ``DescribeProcess`` endpoint.

    All routes listed under `Process requests`_ should normally be applicable for *remote processes* by prefixing
    them with ``/providers/{id}``.

.. _`Provider requests`: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Providers
.. _`Process requests`: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Processes

.. _Execute:
Execution of a process (Execute, Job)
---------------------------------------------------------------------

.. todo::

.. _GetStatus:
Monitoring of a process (GetStatus)
---------------------------------------------------------------------

.. todo::

.. _GetResult:
Obtaining output results, logs or errors
---------------------------------------------------------------------

.. todo::



Special Weaver EMS use-cases
==================================================

OpenSearch data source
--------------------------------------

.. todo:: EOImage with AOI/TOI/CollectionId for OpenSearch

Workflow (Chaining Step Processes)
--------------------------------------

.. todo:: reference IDs of steps

