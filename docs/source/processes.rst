.. _processes:
.. include:: references.rst

**********
Processes
**********

Type of Processes
=====================

`Weaver` supports multiple type of processes, as listed below.
Each one of them are accessible through the same API interface, but they have different implications.

- `Builtin`_
- `WPS-1/2`_
- `WPS-REST`_ (a.k.a.: WPS-3, |ogc-proc-api|_)
- `ESGF-CWT`_
- `Workflow`_
- `Remote Provider`_

Builtin
-------

These processes come pre-packaged with `Weaver`. They will be available directly on startup of the application and
re-updated on each boot to make sure internal database references are updated with any source code changes.

Theses processes typically correspond to utility operations. They are specifically useful when employed as
`step` within a `Workflow`_ process that requires data-type conversion between input/output of similar, but not
perfectly, compatible definitions.

For example, process :py:mod:`weaver.processes.builtin.jsonarray2netcdf` takes a single input JSON file which its
content contains an array-list of NetCDF file references, and returns them directly as the corresponding list of output
files. These two different file formats (single JSON to multiple NetCDF) can then be used to map two processes with
these respective output and inputs.

As of the latest release, following `builtin` processes are available:

- :py:mod:`weaver.processes.builtin.jsonarray2netcdf`


All `builtin` processes are marked with :py:data:`weaver.processes.constants.CWL_REQUIREMENT_APP_BUILTIN` in the `CWL`
hints* section.

WPS-1/2
-------

This kind of process corresponds to a *traditional* WPS XML or JSON endpoint (depending of supported version) prior to
WPS-REST specification. When the `WPS-REST`_ process is deployed in `Weaver` using an URL reference to an WPS-1/2
process, `Weaver` parses and converts the XML or JSON body of the response and registers the process locally using this
definition. This allows a remote server offering limited functionalities (e.g.: no REST bindings supported) to provide
them through `Weaver`.

A minimal `Deploy`_ request body for this kind of process could be as follows:

.. code-block:: json

    {
      "processDescription": {
        "process": {
          "id": "my-process-reference"
        }
      },
      "executionUnit": [
        {
          "href": "https://example.com/wps?service=WPS&request=DescribeProcess&identifier=my-process&version=1.0.0"
        }
      ]
    }

This would tell `Weaver` to locally deploy the ``my-process-reference`` process using the WPS-1 URL reference that is
expected to return a ``DescribeProcess`` XML schema. Provided that this endpoint can be resolved and parsed according
to typical WPS specification, this should result into a successful process registration. The deployed process would
then be accessible with `DescribeProcess`_  requests.

The above deployment procedure can be automated on startup using `Weaver`'s ``wps_processes.yml`` configuration file.
Please refer to `Configuration of WPS Processes`_ section for more details on this matter.

.. warning::

    Because `Weaver` creates a *snapshot* of the reference process at the moment it was deployed, the local process
    definition could become out-of-sync with the remote reference where the `Execute`_ request will be sent. Refer to
    `Remote Provider`_ section for more details to work around this issue.

.. seealso::
    - `Remote Provider`_


WPS-REST
--------

This process type is the main component of `Weaver`. All other process types are converted to this one either
through some parsing (e.g.: `WPS-1/2`_) or with some requirement indicators (e.g.: `Builtin`_, `Workflow`_) for
special handling.

When deploying one such process directly, it is expected to have a reference to a CWL `Application Package`_. This is
most of the time employed to wrap a reference docker image process. The reference package can be provided in multiple
ways as presented below.

.. note::

    When a process is deployed with any of the below supported `Application Package` formats, additional parsing of
    this `CWL` as well as complementary details directly within the `WPS` deployment body is accomplished.
    See `Correspondance between CWL and WPS fields`_ section for more details.


Package as Literal Unit Block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In this situation, the `CWL` definition is provided as is using tje JSON-formatted package embedded within the
|deploy-req|_ request. The request payload would take the following shape:

.. code-block:: json

    {
      "processDescription": {
        "process": {
          "id": "my-process-reference"
        }
      },
      "executionUnit": [
        {
          "unit": {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [<...>],
            "outputs": [<...>],
            [<...>]
          }
        }
      ]
    }


ESGF-CWT
----------

.. todo:: esgf-cwt process doc


Workflow
----------

.. todo:: workflow process doc


Remote Provider
--------------------

Remote provider correspond to a remote service that provides similar interfaces as supported by `Weaver` (WPS-like).
For example, a remote WPS-1 XML endpoint can be referenced as a provider. When an API `Providers`_-scoped request is
executed, for example to list is processes capabilities (see `GetCapabilities`_), `Weaver` will send the corresponding
request using the registered reference URL to access the remote server and reply with parsed response, as if they
its processes were registered locally.

Since remote providers obviously require access to the remote service, `Weaver` will only be able to provide results
if the service is accessible with respect to standard implementation features and supported specifications.

The main advantage of using `Weaver`'s endpoint rather than directly accessing the referenced remote provider processes
is in the case of limited functionality offered by the service. For instance, WPS-1 do not always offer `GetStatus`_
feature, and there is no extensive job monitoring availability. Since `Weaver` *wraps* the original reference with its
own endpoints, these features indirectly become employable. Similarly, although WPS-1 offer XML-only endpoints, the
parsing operation accomplished by `Weaver` makes theses services available as WPS-REST JSON endpoints. On top of that,
registering remote providers into `Weaver` allows the user to use it as a central hub to keep references to all his
accessible services and dispatch jobs from a common location.

A *remote provider* differs from previously presented `WPS-1/2`_ processes such that the underlying processes of the
service are not registered locally. For example, if a remote service has two WPS processes, only top-level service URL
will be registered locally (in `Weaver`'s database) and the application will have no explicit knowledge of these remote
processes. When calling process-specific requests (e.g.: `DescribeProcess`_ or `Execute`_), `Weaver` will re-send the
corresponding request directly to the remote provider each time and return the result accordingly. On the other hand,
a `WPS-1/2`_ reference would be parsed and saved locally with the response *at the time of deployment*. This means that
a deployed `WPS-1/2`_ reference would act as a *snapshot* of the reference (which could become out-of-sync), while
`Remote Provider`_ will dynamically update according to the re-fetched response from the remote service. If our example
remote service was extended to have a third WPS process, it would immediately be reflected in `GetCapabilities`_ and
`DescribeProcess`_ retrieved via `Weaver` `Providers`_-scoped requests. This would not be the case for the `WPS-1/2`_
reference that would need manual update (deploy the third process to register it in `Weaver`).


.. _`Providers`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Providers
.. _`register provider`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Providers%2Fpaths%2F~1providers%2Fpost
.. _`DescribeProviderProcess`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Provider-Processes%2Fpaths%2F~1providers~1%7Bprovider_id%7D~1processes~1%7Bprocess_id%7D%2Fget

An example body of the `register provider`_ request could be as follows:

.. code-block:: json

    {
      "id": "my-service",
      "url": "https://example.com/wps,
      "public": true
    }


Then, processes of this registered *remote provider* will be accessible. For example, if the referenced service by the
above URL add a WPS process identified by `my-process`, its JSON description would be obtained with following
request (`DescribeProviderProcess`_):

.. code-block::

    GET {WEAVER_URL}/providers/my-service/processes/my-process

.. note::

    Process `my-process` in the example is not registered locally. From the point of view of `Weaver`'s processes
    (i.e.: route `/processes/{id}`), it does **NOT** exist. You must absolutely use the prefixed ``/providers/{id}``
    route.

.. warning::

    API requests scoped under `Providers`_ are `Weaver`-specific implementation. These are not part of |ogc-proc-api|_
    specification.


Managing processes included in Weaver ADES/EMS
==================================================

Following steps represent the typical steps applied to deploy a process, execute it and retrieve the results.

.. _Deploy:

Register a new process (Deploy)
-----------------------------------------

Deployment of a new process is accomplished through the ``POST {WEAVER_URL}/processes`` |deploy-req|_ request.
The request body requires mainly two components:

- ``processDescription``: defines the process identifier, metadata, inputs, outputs, and some execution specifications.
- ``executionUnit``: defines the main core details of the `Application Package`_.

.. |deploy-req| replace:: Deploy
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
.. _vis-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1visibility%2Fput

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
.. _getcap-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes%2Fget
.. |describe-req| replace:: ``GET /processes/{id}`` (``DescribeProcess``)
.. _describe-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget

For more specific process details, the |describe-req|_ request should be used. This will return all information
that define the process references and expected inputs/outputs.

.. note::
    For *remote processes* (see: `Remote Provider`_), `Provider requests`_ are also available for more fine-grained
    search of underlying processes. These processes are not necessarily listed as local processes, and will therefore
    sometime not yield any result if using the typical ``DescribeProcess`` endpoint.

    All routes listed under `Process requests`_ should normally be applicable for *remote processes* by prefixing
    them with ``/providers/{id}``.

.. _`Provider requests`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Providers
.. _`Process requests`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes

.. _Execute:

Execution of a process (Execute, Job)
---------------------------------------------------------------------

.. todo::



When a job is executed by specifying the ``notification_email`` field, the resulting process execution will send an
email to the specified address with successful or failure details. The format of the email is configurable from
`weaver.ini.example`_ file

.. _exec-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1{process_id}~1jobs%2Fpost

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

