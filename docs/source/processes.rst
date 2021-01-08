
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


.. seealso::
    Section |examples|_ provides multiple concrete use cases of `Deploy`_ and `Execute`_ request payloads
    for diverse set of applications.


Builtin
-------

These processes come pre-packaged with `Weaver`. They will be available directly on startup of the application and
re-updated on each boot to make sure internal database references are updated with any source code changes.

Theses processes typically correspond to utility operations. They are specifically useful when employed as
``step`` within a `Workflow`_ process that requires data-type conversion between input/output of similar, but not
perfectly, compatible definitions.

For example, process :py:mod:`weaver.processes.builtin.jsonarray2netcdf` takes a single input JSON file which its
content contains an array-list of NetCDF file references, and returns them directly as the corresponding list of output
files. These two different file formats (single JSON to multiple NetCDF) can then be used to map two processes with
these respective output and inputs.

As of the latest release, following `builtin` processes are available:

- :py:mod:`weaver.processes.builtin.file2string_array`
- :py:mod:`weaver.processes.builtin.jsonarray2netcdf`
- :py:mod:`weaver.processes.builtin.metalink2netcdf`


All `builtin` processes are marked with :py:data:`weaver.processes.constants.CWL_REQUIREMENT_APP_BUILTIN` in the
:term:`CWL` ``hints`` section and are all defined in :py:mod:`weaver.processes.builtin`.

WPS-1/2
-------

This kind of process corresponds to a *traditional* WPS XML or JSON endpoint (depending of supported version) prior to
WPS-REST specification. When the `WPS-REST`_ process is deployed in `Weaver` using an URL reference to an WPS-1/2
process, `Weaver` parses and converts the XML or JSON body of the response and registers the process locally using this
definition. This allows a remote server offering limited functionalities (e.g.: no REST bindings supported) to provide
them through `Weaver`.

A minimal `Deploy`_ request body for this kind of process could be as follows:

.. code-block:: JSON

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
Please refer to :ref:`Configuration of WPS Processes` section for more details on this matter.

.. warning::

    Because `Weaver` creates a *snapshot* of the reference process at the moment it was deployed, the local process
    definition could become out-of-sync with the remote reference where the `Execute`_ request will be sent. Refer to
    `Remote Provider`_ section for more details to work around this issue.

.. seealso::
    - `Remote Provider`_

.. _process-wps-rest:

WPS-REST
--------

This process type is the main component of `Weaver`. All other process types are converted to this one either
through some parsing (e.g.: `WPS-1/2`_) or with some requirement indicators (e.g.: `Builtin`_, `Workflow`_) for
special handling.

When deploying one such process directly, it is expected to have a reference to a CWL `Application Package`_. This is
most of the time employed to wrap a reference docker image process. The reference package can be provided in multiple
ways as presented below.

.. note::

    When a process is deployed with any of the below supported :term:`Application Package` formats, additional parsing
    of this :term:`CWL` as well as complementary details directly within the :term:`WPS` deployment body is
    accomplished. See :ref:`Correspondance between CWL and WPS fields` section for more details.


Package as Literal Unit Block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In this situation, the :term:`CWL` definition is provided as is using JSON-formatted package embedded within the
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
            "inputs": ["<...>"],
            "outputs": ["<...>"],
            "<...>": "<...>"
          }
        }
      ]
    }

.. _process-esgf-cwt:

ESGF-CWT
----------

For *traditional* WPS-1 process type, Weaver adds default values to :term:`CWL` definition. As we can see in
:mod:`weaver/processes/wps_package.py`, the following default values for the :term:`CWL` package are:

.. code-block:: python

    cwl_package = OrderedDict([
        ("cwlVersion", "v1.0"),
        ("class", "CommandLineTool"),
        ("hints", {
            CWL_REQUIREMENT_APP_WPS1: {
                "provider": get_url_without_query(wps_service_url),
                "process": process_id,
            }}),
    ])

In :term:`ESGF-CWT` processes, ``ESGF-CWTRequirement`` hint must be used instead of usual ``WPS1Requirement``, contained
in the :py:data:`weaver.processes.constants.CWL_REQUIREMENT_APP_WPS1` variable. The handling of this technicality is
handled in :mod:`weaver/processes/wps_package.py`. We can define :term:`ESGF-CWT` processes using this syntax:

.. code-block:: json

    {
      "cwlVersion": "v1.0",
      "class": "CommandLineTool",
      "hints": {
        "ESGF-CWTRequirement": {
          "provider": "https://edas.nccs.nasa.gov/wps/cwt",
          "process": "xarray.subset"
        }
      }
    }

Workflow
----------

Processes categorized as ``Workflow`` are very similar to `WPS-REST`_ processes. From the API standpoint, they
actually look exactly the same as an atomic process when calling `DescribeProcess`_ or `Execute`_ requests.
The difference lies within the referenced :ref:`Application Package` which uses a :ref:`CWL Workflow` instead of
typical :ref:`CWL CommandLineTool`, and therefore, modifies how the process is internally executed.

For ``Workflow`` processes to be deploy-able and executable, it is **mandatory** that `Weaver` is configured as
:term:`EMS` (see: :ref:`Configuration Settings`). This requirement is due to the nature of workflows that chain
processes that need to be dispatched to known remote :term:`ADES` servers (see: :ref:`Configuration of Data Sources`
and `Workflow Operations`_).

Given that a ``Workflow`` process was successfully deployed and that all process steps can be resolved, calling
its `Execute`_ request will tell `Weaver` to parse the chain of operations and send step process execution requests
to relevant :term:`ADES` picked according to data sources. Each step's job will then gradually be monitored from the
remote :term:`ADES` until completion, and upon successful result, the :term:`EMS` will retrieve the data references to
pass it down to the following step. When the complete chain succeeds, the final results of the last step will be
provided as ``Workflow`` output as for atomic processes. In case of failure, the error will be indicated in the log
with the appropriate step and message where the error occurred.

.. note::

    Although chaining sub-workflow(s) within a bigger scoped workflow is technically possible, this have not yet
    been fully explored (tested) in `Weaver`. There is a chance that |data-source|_ resolution fails to identify where
    to dispatch the step in this situation. If this impacts you, please vote and indicate your concern on issue
    `#171 <https://github.com/crim-ca/weaver/issues/171>`_.

.. _remote-provider:

Remote Provider
--------------------

Remote provider correspond to a remote service that provides similar interfaces as supported by `Weaver`
(:term:`WPS`-like). For example, a remote WPS-1 XML endpoint can be referenced as a provider. When an API
`Providers`_-scoped request is executed, for example to list is processes capabilities (see `GetCapabilities`_),
`Weaver` will send the corresponding request using the registered reference URL to access the remote server and
reply with parsed response, as if they its processes were registered locally.

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
      "url": "https://example.com/wps",
      "public": true
    }


Then, processes of this registered `remote-provider`_ will be accessible. For example, if the referenced service by
the above URL add a WPS process identified by ``my-process``, its JSON description would be obtained with following
request (`DescribeProviderProcess`_):

.. code-block::

    GET {WEAVER_URL}/providers/my-service/processes/my-process

.. note::

    Process ``my-process`` in the example is not registered locally. From the point of view of `Weaver`'s processes
    (i.e.: route ``/processes/{id}``), it does **NOT** exist. You must absolutely use the provider-prefixed route
    ``/providers/{id}/processes/{id}`` to explicitly fetch and resolve this remote process definition.

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

- | ``processDescription``:
  | Defines the process identifier, metadata, inputs, outputs, and some execution specifications. This mostly
    corresponds to information that corresponds to a traditional :term:`WPS` definition.
- | ``executionUnit``:
  | Defines the core details of the `Application Package`_. This corresponds to the explicit :term:`CWL` definition
    that indicates how to execute the given application.

.. _Application Package: docs/source/package.rst

Upon deploy request, `Weaver` will either respond with a successful result, or with the appropriate error message,
whether caused by conflicting ID, invalid definitions or other parsing issues. A successful process deployment will
result in this process to become available for following steps.

.. warning::
    When a process is deployed, it is not necessarily available immediately. This is because process *visibility* also
    needs to be updated. The process must be made *public* to allow its discovery. For updating visibility, please
    refer to the |vis-req|_ request.

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

Execution of a process (Execute)
---------------------------------------------------------------------

Process execution (i.e.: submitting a :term:`Job`) is accomplished using the |exec-req|_ request. This section will
first describe the basics of this request format, and after go into details for specific use cases and parametrization
of various input/output combinations. Let's employ the following example of JSON body sent to the :term:`Job` execution
to better illustrate the requirements.

.. code-block:: json

    {
      "mode": "async",
      "response": "document",
      "inputs": [
        {
          "id": "input-file",
          "href": "<some-file-reference"
        },
        {
          "id": "input-value",
          "data": 1,
        }
      ],
      "outputs": [
        {
          "id": "output",
          "transmissionMode": "reference"
        }
      ]
    }

Basic Details
~~~~~~~~~~~~~~~~~

The first field is ``mode``, it basically tells whether to run the :term:`Process` in a blocking (``sync``) or
non-blocking (``async``) manner. Note that support is currently limited for mode ``sync`` as this use case is often more
cumbersome than ``async`` execution. Effectively, ``sync`` mode requires to have a task worker executor available
to run the :term:`Job` (otherwise it fails immediately due to lack of processing resource), and the requester must wait
for the *whole* execution to complete to obtain the result. Given that :term:`Process` could take a very long time to
complete, it is not practical to execute them in this manner and potentially have to wait hours to retrieve outputs.
Instead, the preferred and default approach is to request an ``async`` :term:`Job` execution. When doing so, `Weaver`
will add this to a task queue for processing, and will immediately return a :term:`Job` identifier and location where
the user can probe for its status, using `GetStatus`_ monitoring request. As soon as any task worker becomes available,
it will pick any leftover queued :term:`Job` to execute it.

The second field is ``response``. At the time being, `Weaver` only supports ``document`` value. This parameter is
present only for compatibility with other :term:`ADES` implementation, but does not actually affects `Weaver`'s
response.

Following are the ``inputs`` definition. This is the most important section of the request body. It defines which
parameters to forward to the referenced :term:`Process` to be executed. All ``id`` elements in this :term:`Job` request
body must correspond to valid ``inputs`` from the definition returned by `DescribeProcess`_ response. Obviously, all
formatting requirements (i.e.: proper file :term:`MIME-types`), data types (e.g.: ``int``, ``string``, etc.) and
validations rules (e.g.: ``minOccurs``, ``AllowedValues``, etc.) must also be fulfilled. When providing files as input,
multiple protocols are supported. See later section :ref:`File Reference Types` for details.

Finally, the ``outputs`` section defines, for each ``id`` corresponding to the :term:`Process` definition, how to
report the produced outputs from a successful :term:`Job` completion. Again, `Weaver` only implement the
``reference`` result for the time being as this is the most common variation. In this case, the produced file is
stored locally and exposed externally with returned reference URL. The other (unimplemented) mode ``value`` would
return the contents directly in the response instead of the URL.

.. note::
    Other parameters can be added to the request to provide further functionalities. Above fields are the minimum
    requirements to request a :term:`Job`. Please refer to the |exec-api|_ definition for all applicable features.

.. note::
    Since most of the time, returned files are not human readable or are simply too large to be displayed, the
    ``transmissionMode: value`` is rarely employed. Also, it is to be noted that outputs representing ``LiteralData``
    (which is even more uncommon) would automatically be represented as ``value`` without explicitly requesting it,
    as there would not be any file to return. If this poses problem or you encounter a valid use-case where ``value``
    would be useful for your needs, please |submit-issue|_ to request the feature.

.. |exec-api| replace:: OpenAPI Execute
.. _exec-api: `exec-req`_


Execution Steps
~~~~~~~~~~~~~~~~~~~~~

Once the :term:`Job` is submitted, its status should initially switch to ``accepted``. This effectively means that the
:term:`Job` is pending execution (task queued), but is not yet executing. When a worker retrieves it for execution, the
status will change to ``started`` for preparation steps (i.e.: allocation resources, retrieving required
parametrization details, etc.), followed by ``running`` when effectively reaching the execution step of the underlying
:term:`Application Package` operation. This status will remain as such until the operation completes, either with
``succeeded`` or ``failed`` status.

At any moment during ``async`` execution, the :term:`Job` status can be requested using |status-req|_. Note that
depending on the timing at which the user executes this request and the availability of task workers, it could be
possible that the :term:`Job` be already in ``running`` state, or even ``failed`` in case of early problem detected.

When the :term:`Job` reaches its final state, multiple parameters will be adjusted in the status response to
indicate its completion, notably the completed percentage, time it finished execution and full duration. At that
moment, the requests for retrieving either error details or produced outputs become accessible. Examples are presented
in `GetResult`_ section.


Process Operations
~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: detail 'operations' accomplished (stage-in, exec-cwl, stage-out)


Workflow Operations
~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: same as prev + 'operations' (deploy based on data-source, visibility, exec-remote for each step, pull-result)


File Reference Types
~~~~~~~~~~~~~~~~~~~~~~~~~~

Most inputs can be categorized into two of the most commonly employed types, namely ``LiteralData`` and ``ComplexData``.
The former represents basic values such as integers or strings, while the other represents a file reference.
Files in `Weaver` (and :term:`WPS` in general) can be specified with any ``formats`` as MIME-type.

.. seealso::
    - :ref:`Correspondance between CWL and WPS fields`

As for *standard* :term:`WPS`, remote file references are *usually* limited to ``http(s)`` scheme, unless the process
takes an input string and parses the unusual reference from the literal data to process it by itself. On the other hand,
`Weaver` supports all following reference schemes.

- |http_scheme|
- |file_scheme|
- |os_scheme| [experimental]
- |s3_scheme| [experimental]

The method in which `Weaver` will handle such references depends on its configuration, in other words, whether it is
running as :term:`ADES` or :term:`EMS` (see: :ref:`Configuration`), as well as depending on some other :term:`CWL`
package requirements. These use-cases are described below.

.. warning::
    Missing schemes in URL reference are considered identical as if ``file://`` was used. In most cases, if not always,
    an execution request should not employ this scheme unless the file is ensured to be at the specific location where
    the running `Weaver` application can find it. This scheme is usually only employed as byproduct of the fetch
    operation that `Weaver` uses to provide the file locally to underlying :term:`CWL` application package to be
    executed.

When `Weaver` is able to figure out that the process needs to be executed locally in :term:`ADES` mode, it will fetch
all necessary files prior to process execution in order to make them available to the :term:`CWL` package. When `Weaver`
is in :term:`EMS` configuration, it will **always** forward remote references (regardless of scheme) exactly as provided
as input of the process execution request, since it assumes it needs to dispatch the execution to another :term:`ADES`
remote server, and therefore only needs to verify that the file reference is reachable remotely. In this case, it
becomes the responsibility of this remote instance to handle the reference appropriately. This also avoids potential
problems such as if `Weaver` as :term:`EMS` doesn't have authorized access to a link that only the target :term:`ADES`
would have access to.

When :term:`CWL` package defines ``WPS1Requirement`` under ``hints`` for corresponding `WPS-1/2`_ remote processes being
monitored by `Weaver`, it will skip fetching of ``http(s)``-based references since that would otherwise lead to useless
double downloads (one on `Weaver` and the other on the :term:`WPS` side). It is the same in case of
``ESGF-CWTRequirement`` employed for `ESGF-CWT`_ processes. Because these processes do not always support :term:`S3`
buckets, and because `Weaver` supports many variants of :term:`S3` reference formats, it will first fetch the :term:`S3`
reference using its internal |aws-config|_, and then expose this downloaded file as ``https(s)`` reference
accessible by the remote :term:`WPS` process.

.. note::
    When `Weaver` is fetching remote files with |http_scheme|, it can take advantage of additional request options to
    support unusual or server-specific handling of remote reference as necessary. This could be employed for instance
    to attribute access permissions only to some given :term:`ADES` server by providing additional authorization tokens
    to the requests. Please refer to :ref:`Configuration of Request Options` for this matter.

When using :term:`S3` references, `Weaver` will attempt to retrieve the file using server |aws-config|_ and
|aws-credentials|_. Provided that the corresponding :term:`S3` bucket can be accessed by the running `Weaver`
application, it will fetch the file and store it locally temporarily for :term:`CWL` execution.

.. note::
    When using :term:`S3` buckets, authorization are handled through typical :term:`AWS` credentials and role
    permissions. This means that :term:`AWS` access must be granted to the application in order to allow it fetching
    the file. There are also different formats of :term:`S3` reference formats handled by `Weaver`.
    Please refer to :ref:`Configuration of AWS S3 Buckets` for more details.

When using :term:`OpenSearch` references, additional parameters are necessary to handle retrieval of specific file URL.
Please refer to :ref:`OpenSearch Data Source` for more details.

Following table summarize the default behaviour of input file reference handling of different situations when received
as input argument of process execution. For simplification, keyword *<any>* is used to indicate that any other value in
the corresponding column can be substituted for a given row when applied with conditions of other columns, which results
to same operational behaviour. Elements that behave similarly are also presented together in rows to reduce displayed
combinations.

+-----------+-------------------------------+---------------+-------------------------------------------+
| |cfg|     | Process Type                  | File Scheme   | Applied Operation                         |
+===========+===============================+===============+===========================================+
| *<any>*   | *<any>*                       | |os_scheme|   | Query and re-process [#openseach]_        |
+-----------+-------------------------------+---------------+-------------------------------------------+
| `ADES`    | - `WPS-1/2`_                  | |file_scheme| | Convert to |http_scheme| [#file2http]_    |
|           | - `ESGF-CWT`_                 +---------------+-------------------------------------------+
|           | - `WPS-REST`_ [#wps3]_        | |http_scheme| | Nothing (left unmodified)                 |
|           | - `remote-provider`_          +---------------+-------------------------------------------+
|           |                               | |s3_scheme|   | Fetch and convert to |http_scheme| [#s3]_ |
|           +-------------------------------+---------------+-------------------------------------------+
|           | `WPS-REST`_ (`CWL`) [#wps3]_  | |file_scheme| | Nothing (file already local)              |
|           |                               +---------------+-------------------------------------------+
|           |                               | |http_scheme| | Fetch and convert to |file_scheme|        |
|           |                               +---------------+                                           |
|           |                               | |s3_scheme|   |                                           |
+-----------+-------------------------------+---------------+-------------------------------------------+
| `EMS`     | - *<any>*                     | |file_scheme| | Convert to |http_scheme| [#file2http]_    |
|           | - `Workflow`_ (`CWL`) [#wf]_  +---------------+-------------------------------------------+
|           |                               | |http_scheme| | Nothing (left unmodified)                 |
|           |                               +---------------+                                           |
|           |                               | |s3_scheme|   |                                           |
+-----------+-------------------------------+---------------+-------------------------------------------+

.. |cfg| replace:: Configuration
.. |os_scheme| replace:: ``opensearchfile://``
.. |http_scheme| replace:: ``http(s)://``
.. |s3_scheme| replace:: ``s3://``
.. |file_scheme| replace:: ``file://``

.. rubric:: Footnotes

.. [#openseach]
    References defined by ``opensearch://`` will trigger an :term:`OpenSearch` query using the provided URL as
    well as other input additional parameters (see :ref:`OpenSearch Data Source`). After processing of this query,
    retrieved file references will be re-processed using the summarized logic in the table for the given use case.

.. [#file2http]
    When a ``file://`` (or empty scheme) maps to a local file that needs to be exposed externally for
    another remote process, the conversion to ``http(s)://`` scheme employs setting ``weaver.wps_outputs_url`` to form
    the result URL reference. The file is placed in ``weaver.wps_outputs_dir`` to expose it as HTTP(S) endpoint.

.. [#wps3]
    When the process refers to a remote :ref:`WPS-REST` process (i.e.: remote :term:`WPS` instance that supports
    REST bindings but that is not necessarily an :term:`ADES`), `Weaver` simply *wraps* and monitor its remote
    execution, therefore files are handled just as for any other type of remote :term:`WPS`-like servers. When the
    process contains an actual :term:`CWL` :ref:`Application Package` that defines a ``CommandLineTool``
    (including :term:`Docker` images), files are fetched as it will be executed locally. See :ref:`CWL CommandLineTool`,
    :ref:`WPS-REST` and :ref:`Remote Providers` for further details.

.. [#s3]
    When an ``s3://`` file is fetched, is gets downloaded to a temporary ``file://`` location, which is **NOT**
    necessarily exposed as ``http(s)://``. If execution is transferred to a remove process that is expected to not
    support :term:`S3` references, only then the file gets converted as in [#file2http]_.

.. [#wf]
    Workflows are only available on :term:`EMS` instances. Since they chain processes, no fetch is needed as the first
    sub-step process will do it instead. See :ref:`Workflow` process as well as :ref:`CWL Workflow` for more details.

.. todo::
    method to indicate explicit fetch to override these? (https://github.com/crim-ca/weaver/issues/183)

.. todo::
    add tests that validate each combination of operation


OpenSearch Data Source
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: EOImage with AOI/TOI/CollectionId for OpenSearch

Multiple Inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: repeating IDs example for WPS multi-inputs

.. seealso::
    - :ref:`Multiple and Optional Values`

Multiple Outputs
~~~~~~~~~~~~~~~~~~~~~~~~~~

Although :term:`CWL` allows output arrays, :term:`WPS` does not support it directly, as only single values are allowed
for :term:`WPS` outputs according to original specification. To work around this, |metalink|_ files can be used to
provide a single output reference that embeds other references. This approach is also employed and preferred as
described in |pywps-multi-output|_.

.. todo:: fix doc when Multiple Output is supported with metalink (https://github.com/crim-ca/weaver/issues/25)
.. todo:: add example of multi-output process definition
.. todo:: and how CWL maps them with WPS

.. warning::
    This feature is being worked on (`Weaver Issue #25 <https://github.com/crim-ca/weaver/issues/25>`_).
    Direct support between

.. seealso::
    - :ref:`Multiple and Optional Values`

Email Notification
~~~~~~~~~~~~~~~~~~~~~~~~~~

When submitting a job for execution, it is possible to provide the ``notification_email`` field.
Doing so will tell `Weaver` to send an email to the specified address with successful or failure details upon job
completion. The format of the email is configurable from `weaver.ini.example`_ file with email-specific settings
(see: :ref:`Configuration`).


.. _GetStatus:

Monitoring of a process (GetStatus)
---------------------------------------------------------------------

.. todo::
    job status body example (success vs fail)

.. _GetResult:

Obtaining output results, logs or errors
---------------------------------------------------------------------

In the case of successful :term:`Job` execution, the outputs can be retrieved with |result-req|_ request to list
each corresponding output ``id`` with the generated file reference URL. Keep in mind that those URL's purpose are
only to fetch the results (not persistent storage), and could therefore be purged after some reasonable amount of time.
The format should be similar to the following example, with minor variations according to :ref:`Configurations`:

.. code-block:: json

    {
      "outputs": [
        {
          "id": "output",
          "href": "{WEAVER_URL}/wpsoutputs/f93a15be-6e16-11ea-b667-08002752172a/output_netcdf.nc"
        }
      ]
    }

In situations where the :term:`Job` resulted into ``failed`` status, the |except-req|_ can be use to retrieve
the potential cause of failure, by capturing any raised exception. Below is an example of such exception details.

.. code-block:: json

    [
      "builtins.Exception: Could not read status document after 5 retries. Giving up."
    ]

The returned exception are often better understood when compared against, or in conjunction with, the logs that
provide details over each step of the operation.

Any :term:`Job` executed by `Weaver` will provide minimal information log, such as operation setup, the moment
when it started execution and latest status. The extent of other log entries will more often than not depend on the
verbosity of the underlying process being executed. When executing an :ref:`Application Package`, `Weaver` tries as
best as possible to collect standard output and error steams to report them through log and exception lists.

Since `Weaver` can only report as much details as provided by the running application, it is recommended by
:term:`Application Package` implementers to provide progressive status updates when developing their package
in order to help understand problematic steps in event of process execution failures. In the case of remote :term:`WPS`
processes monitored by `Weaver` for example, this means gradually reporting process status updates
(e.g.: calling ``WPSResponse.update_status`` if you are using |pywps|_, see: |pywps-status|_), while using ``print``
and/or ``logging`` operation for scripts or :term:`Docker` images executed through :term:`CWL` ``CommandLineTool``.

.. note::
    :term:`Job` logs and exceptions are a `Weaver`-specific implementation.
    They are not part of traditional |ogc-proc-api|_.

A minimalistic example of logging output is presented below. This can be retrieved using |log-req|_ request, at any
moment during :term:`Job` execution (with logs up to that point in time) or after its completion (for full output).
Note again that the more the :term:`Process` is verbose, the more tracking will be provided here.

.. code-block:: json

    [
      "[2020-03-24 21:32:32] INFO     [weaver.datatype.Job] 0:00:00   1% accepted   Job task setup completed.",
      "[2020-03-24 21:32:32] INFO     [weaver.datatype.Job] 0:00:00   2% accepted   Execute WPS request for process [jsonarray2netcdf]",
      "[2020-03-24 21:32:33] INFO     [weaver.datatype.Job] 0:00:01   4% accepted   Fetching job input definitions.",
      "[2020-03-24 21:32:33] INFO     [weaver.datatype.Job] 0:00:01   6% accepted   Fetching job output definitions.",
      "[2020-03-24 21:32:33] INFO     [weaver.datatype.Job] 0:00:01   8% accepted   Starting job process execution",
      "[2020-03-24 21:32:34] INFO     [weaver.datatype.Job] 0:00:01  10% accepted   Verifying job status location.",
      "[2020-03-24 21:32:34] WARNING  [weaver.datatype.Job] 0:00:01  10% accepted   WPS status location could not be found",
      "[2020-03-24 21:32:34] INFO     [weaver.datatype.Job] 0:00:01  20% running    Starting monitoring of job execution.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [wps_package.jsonarray2netcdf]    1% running    Preparing package logs done.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [wps_package.jsonarray2netcdf]    2% running    Launching package...",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [cwltool] Resolved '/tmp/tmpse3pi1gj/jsonarray2netcdf' to 'file:///tmp/tmpse3pi1gj/jsonarray2netcdf'",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [cwltool] ../../../../../tmp/tmpse3pi1gj/jsonarray2netcdf:1:1: Unknown hint",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded                                                       file:///tmp/tmpse3pi1gj/BuiltinRequirement",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [wps_package.jsonarray2netcdf]    5% running    Loading package content done.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [wps_package.jsonarray2netcdf]    6% running    Retrieve package inputs done.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [wps_package.jsonarray2netcdf]    8% running    Convert package inputs done.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [wps_package.jsonarray2netcdf]   10% running    Running package...",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:34] INFO     [cwltool] [job jsonarray2netcdf] /tmp/tmpqy1t8dp3$ python \\",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded      /opt/weaver/processes/builtin/jsonarray2netcdf.py \\",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded      -o \\",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded      /tmp/tmpqy1t8dp3 \\",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded      -i \\",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded      /tmp/tmpla2utn2c/stgb5787338-4a34-4771-88c0-cae95f4d82dd/test_nc_array.json",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:41] INFO     [cwltool] [job jsonarray2netcdf] Max memory used: 36MiB",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:41] INFO     [cwltool] [job jsonarray2netcdf] completed success",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:32:41] INFO     [wps_package.jsonarray2netcdf]   95% running    Package execution done.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:33:53] INFO     [wps_package.jsonarray2netcdf]   98% running    Generate package outputs done.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  [2020-03-24 17:33:55] INFO     [wps_package.jsonarray2netcdf]  100% succeeded  Package complete.",
      "[2020-03-24 21:33:59] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  Job succeeded (status: Package complete.).",
      "[2020-03-24 21:34:45] INFO     [weaver.datatype.Job] 0:01:26  90% succeeded  Job succeeded.",
      "[2020-03-24 21:34:45] INFO     [weaver.datatype.Job] 0:01:26 100% succeeded  Job task complete."
    ]


Special Weaver EMS use-cases
==================================================

This section highlight the additional behaviour available only through an :term:`EMS`-configured `Weaver` instance.
Some other points are already described in other sections, but are briefly indicated here for conciseness.

.. |data-source| replace:: Data-Source
.. _data-source:

ADES dispatching using Data-Sources
--------------------------------------


.. todo:: add details, data-source defines where to send request of *known* ADES
.. todo:: reference config ``weaver.data_sources``


Workflow (Chaining Step Processes)
--------------------------------------

.. todo:: add details, explanation done in below reference

.. seealso::

    - :ref:`CWL Workflow`
    - :ref:`Workflow` process type

