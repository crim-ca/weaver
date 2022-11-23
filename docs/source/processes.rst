.. include:: references.rst
.. _processes:

**********
Processes
**********

.. contents::
    :local:
    :depth: 3

.. _proc_types:

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
    Section |examples|_ provides multiple concrete use cases of :ref:`Deploy <proc_op_deploy>`
    and :ref:`Execute <proc_op_execute>` request payloads for diverse set of applications.


.. _proc_builtin:

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

.. _proc_wps_12:

WPS-1/2
-------

This kind of process corresponds to a *traditional* :term:`WPS` :term:`XML` or :term:`JSON` endpoint
(depending of supported version) prior to `WPS-REST`_ specification. When the `WPS-REST`_ process is deployed
in `Weaver` using an URL reference to an WPS-1/2 process, `Weaver` parses and converts the :term:`XML` or :term:`JSON`
body of the response and registers the process locally using this definition. This allows a remote server offering
limited functionalities (e.g.: no REST bindings supported) to provide them through `Weaver`.

A minimal :ref:`Deploy <proc_op_deploy>` request body for this kind of process could be as follows:

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


This would tell `Weaver` to locally :ref:`Deploy <proc_op_deploy>` the ``my-process-reference`` process using the WPS-1
URL reference that is expected to return a ``DescribeProcess`` :term:`XML` schema. Provided that this endpoint can be
resolved and parsed according to typical WPS specification, this should result into a successful process registration.
The deployed :term:`Process` would then be accessible with :ref:`DescribeProcess <proc_op_describe>`  requests.

The above deployment procedure can be automated on startup using `Weaver`'s ``wps_processes.yml`` configuration file.
Please refer to :ref:`Configuration of WPS Processes` section for more details on this matter.

.. warning::

    Because `Weaver` creates a *snapshot* of the reference process at the moment it was deployed, the local process
    definition could become out-of-sync with the remote reference where the :ref:`Execute <proc_op_execute>` request
    will be sent. Refer to `Remote Provider`_ section for more details to work around this issue.

.. seealso::
    - `Remote Provider`_

.. _proc_wps_rest:

WPS-REST
--------

This :term:`Process` type is the main component of `Weaver`. All other types are converted to this one either
through some parsing (e.g.: `WPS-1/2`_) or with some requirement indicators (e.g.: `Builtin`_, `Workflow`_) for
special handling.

When deploying one such :term:`Process` directly, it is expected to have a definition specified
with a :term:`CWL` `Application Package`_.
This is most of the time employed to wrap an operations packaged in a reference :term:`Docker` image.
The reference package can be provided in multiple ways as presented below.

.. note::

    When a process is deployed with any of the below supported :term:`Application Package` formats, additional parsing
    of this :term:`CWL` as well as complementary details directly within the :term:`WPS` deployment body is
    accomplished. See :ref:`cwl-wps-mapping` section for more details.


.. _app_pkg_exec_unit_literal:

Package as Literal Execution Unit Block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In this situation, the :term:`CWL` definition is provided as is using :term:`JSON`-formatted package embedded within the
|deploy-req|_ request. The request payload would take the following shape:

.. code-block:: json

    {
      "processDescription": {
        "process": {
          "id": "my-process-literal-package"
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

.. _app_pkg_exec_unit_reference:

Package as External Execution Unit Reference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In this situation, the :term:`CWL` is provided indirectly using an external file reference which is expected to have
contents describing the :term:`Application Package` (as presented in the :ref:`app_pkg_exec_unit_literal` case).
Because an external file is employed instead of embedding the package within the :term:`JSON` HTTP request contents,
it is possible to employ both :term:`JSON` and :term:`YAML` definitions.

An example is presented below:

.. code-block:: json

    {
      "processDescription": {
        "process": {
          "id": "my-process-reference-package"
        }
      },
      "executionUnit": [
        {
          "href": "https://remote-file-server.com/my-package.cwl"
        }
      ]
    }

Where the referenced file hosted at ``"https://remote-file-server.com/my-package.cwl"`` could contain:

.. code-block:: yaml

    cwlVersion: "v1.0"
    class: CommandLineTool
    inputs:
      - "<...>"
    outputs:
      - "<...>"
    "<...>": "<...>"


.. _proc_esgf_cwt:

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

.. _proc_workflow:

Workflow
----------

Processes categorized as :term:`Workflow` are very similar to `WPS-REST`_ processes. From the API standpoint, they
actually look exactly the same as an atomic process when calling :ref:`DescribeProcess <proc_op_describe>`
or :ref:`Execute <proc_op_execute>` requests.
The difference lies within the referenced :ref:`Application Package` which uses a :ref:`CWL Workflow` instead of
typical :ref:`CWL CommandLineTool`, and therefore, modifies how the :term:`Process` is internally executed.

For :term:`Workflow` processes to be deploy-able and executable, it is **mandatory** that `Weaver` is configured as
:term:`EMS` or :term:`HYBRID` (see: :ref:`Configuration Settings`). This requirement is due to the nature
of :term:`Workflow` that chain processes that need to be dispatched to known remote :term:`ADES` servers
(see: :ref:`conf_data_sources` and :ref:`proc_workflow_ops`) according to defined :term:`Data Source` configuration.

Given that a :term:`Workflow` process was successfully deployed and that all process steps can be resolved, calling
its :ref:`Execute <proc_op_execute>` request will tell `Weaver` to parse the chain of operations and send step process
execution requests to relevant :term:`ADES` picked according to :term:`Data Source`. Each step's job will then gradually
be monitored from the relevant :term:`ADES` until completion.

Upon successful intermediate result, the :term:`EMS` (or :term:`HYBRID` acting as such) will stage the data references
locally to chain them to the following step. When the complete chain succeeds, the final results of the last step will
be provided as :term:`Workflow` output in the same manner as for atomic processes. In case of failure, the error will
be indicated in the logs with the appropriate step and message where the error occurred.

.. note::

    Although chaining sub-workflow(s) within a bigger scoped :term:`Workflow` is technically possible, this have not yet
    been fully explored (tested) in `Weaver`. There is a chance that |data-source|_ resolution fails to identify where
    to dispatch the step in this situation. If this impacts you, please vote and indicate your concern on issue
    `#171 <https://github.com/crim-ca/weaver/issues/171>`_.

.. seealso::
    :ref:`proc_workflow_ops` provides more details on each of the internal operations accomplished by
    individual step :term:`Process` chained in a :term:`Workflow`.

.. _proc_remote_provider:

Remote Provider
--------------------

A remote :term:`Provider` corresponds to a service hosted remotely that provides similar or compatible
(:term:`WPS`-like) interfaces supported by `Weaver`. For example, a remote :term:`WPS`-1 :term:`XML` endpoint
can be referenced as a :term:`Provider`. When an API `Providers`_-scoped request is executed, for example to list its
process capabilities (see :ref:`GetCapabilities <proc_op_getcap>`), `Weaver` will send the corresponding request using
the reference URL from the registered :term:`Provider` to access the remote server and reply with the parsed response,
as if its processes were registered locally.

Since remote providers obviously require access to the remote service, `Weaver` will only be able to provide results
if the service is accessible with respect to standard implementation features and supported specifications.

The main advantage of using `Weaver`'s endpoint rather than directly accessing the referenced remote :term:`Provider`
processes is to palliate the limited functionalities offered by the service. For instance, :term:`WPS`-1 do not always
offer :ref:`proc_op_status` feature, and there is no extensive :term:`Job` monitoring capabilities. Since `Weaver`
effectively *wraps* the referenced :term:`Provider` with its own endpoints, these features indirectly become employable
through an extended :term:`OGC API - Processes` interface. Similarly, although many :term:`WPS`-1 offer :term:`XML`-only
responses, the parsing operation accomplished by `Weaver` makes theses services available as :term:`WPS-REST`
:term:`JSON` endpoints with automatic conversion. On top of that, registering a remote :term:`Provider` into `Weaver`
allows the user to use it as a central hub to keep references to all his remotely accessible services and dispatch
:term:`Job` executions from a common location.

A *remote provider* differs from previously presented `WPS-1/2`_ processes such that the underlying processes of the
service are not registered locally. For example, if a remote service has two WPS processes, only top-level service URL
will be registered locally (in `Weaver`'s database) and the application will have no explicit knowledge of these remote
processes until requested. When calling :term:`Process`-specific requests
(e.g.: :ref:`DescribeProcess <proc_op_describe>` or :ref:`Execute <proc_op_execute>`), `Weaver` will re-send the
corresponding request (with appropriate interface conversion) directly to the remote :term:`Provider` each time and
return the result accordingly. On the other hand, a `WPS-1/2`_ reference would be parsed and saved locally with the
response *at the time of deployment*. This means that a deployed `WPS-1/2`_ reference would act as a *snapshot* of the
reference :term:`Process` (which could become out-of-sync), while `Remote Provider`_ will dynamically update according
to the re-fetched response from the remote service each time, always keeping the obtained description in sync with the
remote :term:`Provider`. If our example remote service was extended to have a third :term:`WPS` process, it would
immediately and transparently be reflected in :ref:`GetCapabilities <proc_op_getcap>`
and :ref:`DescribeProcess <proc_op_describe>` retrieved by `Weaver` on `Providers`_-scoped requests without any change
to the registered :term:`Provider` definition. This would not be the case for the `WPS-1/2`_ reference that would need
a manual update (i.e.: deploy the third :term:`Process` to register it in `Weaver`).


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


Then, processes of this registered :ref:`proc_remote_provider` will be accessible. For example, if the referenced
service by the above URL add a WPS process identified by ``my-process``, its JSON description would be obtained with
following request (`DescribeProviderProcess`_):

.. code-block::

    GET {WEAVER_URL}/providers/my-service/processes/my-process

.. note::

    Process ``my-process`` in the example is not registered locally. From the point of view of `Weaver`'s processes
    (i.e.: route ``/processes/{id}``), it does **NOT** exist. You must absolutely use the provider-prefixed route
    ``/providers/{id}/processes/{id}`` to explicitly fetch and resolve this remote process definition.

.. warning::

    API requests scoped under `Providers`_ are `Weaver`-specific implementation. These are not part of |ogc-proc-api|_
    specification.


.. _proc_operations:

Managing processes included in Weaver ADES/EMS
==================================================

Following steps represent the typical steps applied to deploy a process, execute it and retrieve the results.

.. _proc_op_deploy:

Register a new process (Deploy)
-----------------------------------------

Deployment of a new process is accomplished through the ``POST {WEAVER_URL}/processes`` |deploy-req|_ request.

The request body requires mainly two components:

- | ``processDescription``:
  | Defines the process identifier, metadata, inputs, outputs, and some execution specifications. This mostly
    corresponds to information that is provided by traditional :term:`WPS` definition.
- | ``executionUnit``:
  | Defines the core details of the `Application Package`_. This corresponds to the explicit :term:`CWL` definition
    that indicates how to execute the given application.

.. _Application Package: docs/source/package.rst

Upon deploy request, `Weaver` will either respond with a successful result, or with the appropriate error message,
whether caused by conflicting ID, invalid definitions or other parsing issues. A successful process deployment will
result in this process to become available for following steps.

.. warning::
    When a process is deployed, it is not necessarily available immediately. This is because process *visibility* also
    needs to be updated. The process must be made *public* to allow its discovery. Alternatively, the visibility can
    be directly provided within the body of the deploy request to skip this extra step.
    For specifying or updating visibility, please refer to corresponding |deploy-req|_ and |vis-req|_ requests.

After deployment and visibility preconditions have been met, the corresponding process should become available
through :ref:`DescribeProcess <proc_op_describe>` requests and other routes that depend on an existing process.

Note that when a process is deployed using the `WPS-REST`_ interface, it also becomes available through the `WPS-1/2`_
interface with the same identifier and definition. Because of compatibility limitations, some parameters in the
`WPS-1/2`_ side might not be perfectly mapped to the equivalent or adjusted `WPS-REST`_ interface, although this
concerns mostly only new features such as :term:`Job` status monitoring. For most traditional use cases, properties
are mapped between the two interfaces, but it is recommended to use the `WPS-REST`_ one because of the added features.

.. seealso::
    Please refer to :ref:`application-package` chapter for any additional parameters that can be
    provided for specific types of :term:`Application Package` and :term:`Process` definitions.

.. _proc_op_getcap:
.. _proc_op_describe:

Access registered processes (GetCapabilities, DescribeProcess)
------------------------------------------------------------------------

Available processes can all be listed using |getcap-req|_ request. This request will return all locally registered
process summaries. Other return formats and filters are also available according to provided request query parameters.
Note that processes not marked with *public visibility* will not be listed in this result.

For more specific process details, the |describe-req|_ request should be used. This will return all information
that define the process references and expected inputs/outputs.

.. note::
    For *remote processes* (see: `Remote Provider`_), `Provider requests`_ are also available for more fine-grained
    search of underlying processes. These processes are not necessarily listed as local processes, and will therefore
    sometime not yield any result if using the typical ``DescribeProcess`` request on `wps_endpoint`.

    All routes listed under `Process requests`_ should normally be applicable for *remote processes* by prefixing
    them with ``/providers/{id}``.

.. _`Provider requests`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Providers
.. _`Process requests`: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes

.. versionchanged:: 4.20

With the addition of :term:`Process` revisions (see :ref:`Update Operation <proc_op_update` below), a registered
:term:`Process` specified only by ``{processID}`` will retrieve the latest revision of that :term:`Process`.
A specific older revision can be obtained by adding the tagged version in the path (``{processID}:{version}``) or
adding the request query parameter ``version``.

Using revisions provided through ``PUT`` and ``PATCH`` requests, it is also possible to list specific or all existing
revisions of a given or multiple processes simultaneously using the ``revisions`` and ``version`` query parameters with
the |getcap-req|_ request.


.. _proc_op_undeploy:
.. _proc_op_update:

Update, replace or remove an existing process (Update, Replace, Undeploy)
-----------------------------------------------------------------------------

Since `Weaver` supports |ogc-api-proc-part2|_, it is able to remove a previously registered :term:`Process` using
the :ref:`Deployment <proc_op_deploy>` request. The undeploy operation consist of a ``DELETE`` request targeting the
specific ``{WEAVER_URL}/processes/{processID}`` to be removed.

.. note::
    The :term:`Process` must be accessible by the user considering any visibility configuration to perform this step.
    See :ref:`proc_op_deploy` section for details.

.. versionadded:: 4.20

Starting from version `4.20 <https://github.com/crim-ca/weaver/tree/4.20.0>`_, a :term:`Process` can be replaced or
updated using respectively the ``PUT`` and ``PATCH`` requests onto the specific ``{WEAVER_URL}/processes/{processID}``
location of the reference to modify.

.. note::
    The :term:`Process` partial update operation (using ``PATCH``) is specific to `Weaver` only.
    |ogc-api-proc-part2|_ only mandates the definition of ``PUT`` request for full override of a :term:`Process`.

When a :term:`Process` is modified using the ``PATCH`` operation, only the new definitions need to be provided, and
unspecified items are transferred over from the referenced :term:`Process` (i.e.: the previous revision). Using either
the ``PUT`` or ``PATCH`` requests, previous revisions can be referenced using two formats:

- ``{processID}:{version}`` as request path parameters (instead of usual ``{processID}`` only)
- ``{processID}`` in the request path combined with ``?version={version}`` query parameter

`Weaver` employs ``MAJOR.MINOR.PATCH`` semantic versioning to maintain revisions of updated or replaced :term:`Process`
definitions. The next revision number to employ for update or replacement can either be provided explicitly in the
request body using a ``version``, or be omitted. When omitted, the next revision will be guessed automatically based
on the previous available revision according to the level of changes required. In either cases, the resolved ``version``
will have to be available and respect the expected update level to be accepted as a new valid :term:`Process` revision.
The applicable revision level depends on the contents being modified using submitted request body fields according
to the following table. When a combination of the below items occur, the higher update level is required.

+-------------+-----------+------------------------------------+------------------------------------------------------+
| HTTP Method | Level     | Change                             | Examples                                             |
+=============+===========+====================================+======================================================+
| ``PATCH``   | ``PATCH`` | Modifications to metadata          | - :term:`Process` ``description``, ``title`` strings |
|             |           | not impacting the :term:`Process`  | - :term:`Process` ``keywords``, ``metadata`` lists   |
|             |           | execution or definition.           | - inputs/outputs ``description``, ``title`` strings  |
|             |           |                                    | - inputs/outputs ``keywords``, ``metadata`` lists    |
+-------------+-----------+------------------------------------+------------------------------------------------------+
| ``PATCH``   | ``MINOR`` | Modification that impacts *how*    | - :term:`Process` ``jobControlOptions`` (async/sync) |
|             |           | the :term:`Process` could be       | - :term:`Process` ``outputTransmission`` (ref/value) |
|             |           | executed, but not its definition.  | - :term:`Process` ``visibility``                     |
+-------------+-----------+------------------------------------+------------------------------------------------------+
| ``PUT``     | ``MAJOR`` | Modification that impacts *what*   | - Any :term:`Application Package` modification       |
|             |           | the :term:`Process` executes.      | - Any inputs/outputs change (formats, occurs, type)  |
|             |           |                                    | - Any inputs/outputs addition or removal             |
+-------------+-----------+------------------------------------+------------------------------------------------------+

.. note::
    For all applicable fields of updating a :term:`Process`, refer to the schema of |update-req|_.
    For replacing a :term:`Process`, refer instead to the schema of |replace-req|_. The replacement request contents
    are extremely similar to the :ref:`Deploy <proc_op_deploy>` schema since the full :term:`Process` definition must
    be provided.

For example, if the ``test-process:1.2.3`` was previously deployed, and is the active latest revision of that
:term:`Process`, submitting the below request body will produce a ``PATCH`` revision as ``test-process:1.2.4``.

.. literalinclude:: ../examples/update-process-patch.http
    :language: http
    :caption: Sample request for ``PATCH`` revision

Here, only metadata is adjusted and there is no risk to impact produced results or execution methods of the
:term:`Process`. An external user would probably not even notice the :term:`Process` changed, which is why ``PATCH``
is reasonable in this case. Notice that the ``version`` is not explicitly provided in the body. It is guessed
automatically from the modified contents. Also, the example displays how :term:`Process`-level and
inputs/outputs-level metadata can be updated.

Similarly, the following request would produce a ``MINOR`` revision of ``test-process``. Since both ``PATCH`` and
``MINOR`` level contents are defined for update, the higher ``MINOR`` revision is required. In this case ``MINOR`` is
required because ``jobControlOptions`` (forced to asynchronous execution for following versions) would break any future
request made by users that would expect the :term:`Process` to run (or support) synchronous execution.

Notice that this time, the :term:`Process` reference does not indicate the revision in the path (no ``:1.2.4`` part).
This automatically resolves to the updated revision ``test-process:1.2.4`` that became the new latest revision following
our previous ``PATCH`` request.

.. literalinclude:: ../examples/update-process-minor.http
    :language: http
    :caption: Sample request for ``MINOR`` revision

In this case, the desired ``version`` (``1.4.0``) is also specified explicitly in the body. Since the updated number
(``MINOR = 4``) matches the expected update level from the above table and respects an higher level than the reference
``1.2.4`` :term:`Process`, this revision value will be accepted (instead of auto-resolved ``1.3.0`` otherwise). Note
that if ``2.4.0`` was specified instead, the version would be refused, as `Weaver` does not consider this modification
to be worth a ``MAJOR`` revision, and tries to keep version levels consistent. Skipping numbers (i.e.: ``1.3.0`` in this
case), is permitted as long as there are no other versions above of the same level (i.e.: ``1.4.0`` would be refused if
``1.5.0`` existed). This allows some level of flexibility with revisions in case users want to use specific numbering
values that have more meaning to them. It is recommended to let `Weaver` auto-update version values between updates if
this level of fined-grained control is not required.

.. note::
    To avoid conflicting definitions, a :term:`Process` cannot be :ref:`Deployed <proc_op_deploy>` directly using a
    ``{processID}:{version}`` reference. Deployments are expected as the *first revision* and should only include the
    ``{processID}`` portion as their identifier.

If the user desires a specific version to deploy, the ``PUT`` request should be used with the appropriate ``version``
within the request body. It is although up to the user to provide the full definition of that :term:`Process`,
as ``PUT`` request will completely replace the previous definition rather than transfer over previous updates
(i.e: ``PATCH`` requests).

Even when a :term:`Process` is *"replaced"* using ``PUT``, the older revision is not actually removed and undeployed
(``DELETE`` request). It is therefore still possible to refer to the old revision using explicit references with the
corresponding ``version``. `Weaver` keeps track of revisions by corresponding ``{processID}`` entries such that if
the latest revision is undeployed, the previous revision will automatically become the latest once again. For complete
replacement, the user should instead perform a ``DELETE`` of all existing revisions (to avoid conflicts) followed by a
new :ref:`Deploy <proc_op_deploy>` request.

.. _proc_op_execute:

Execution of a process (Execute)
---------------------------------------------------------------------

:term:`Process` execution (i.e.: submitting a :term:`Job`) is accomplished using the |exec-req|_ request.

.. note::
    For backward compatibility, the |exec-req-job|_ request is also supported as alias to the above
    :term:`OGC API - Processes` compliant endpoint.

This section will first describe the basics of this request format, and after go into details for specific use cases
and parametrization of various input/output combinations. Let's employ the following example of JSON body sent to the
:term:`Job` execution to better illustrate the requirements.

.. table::
    :class: code-table
    :align: center

    +-----------------------------------------------+-----------------------------------------------+
    | .. code-block:: json                          | .. code-block:: json                          |
    |   :caption: Job Execution Payload as Listing  |   :caption: Job Execution Payload as Mapping  |
    |                                               |                                               |
    |   {                                           |   {                                           |
    |     "mode": "async",                          |     "mode": "async",                          |
    |     "response": "document",                   |     "response": "document",                   |
    |     "inputs": [                               |     "inputs": {                               |
    |       {                                       |       "input-file": {                         |
    |         "id": "input-file",                   |         "href": "<some-file-reference"        |
    |         "href": "<some-file-reference"        |       },                                      |
    |       },                                      |       "input-value": {                        |
    |       {                                       |         "value": 1                            |
    |         "id": "input-value",                  |       }                                       |
    |         "data": 1,                            |     },                                        |
    |       }                                       |     "outputs": {                              |
    |     ],                                        |       "output": {                             |
    |     "outputs": [                              |         "transmissionMode": "reference"       |
    |       {                                       |       }                                       |
    |         "id": "output",                       |     }                                         |
    |         "transmissionMode": "reference"       |   }                                           |
    |       }                                       |                                               |
    |     ]                                         |                                               |
    |   }                                           |                                               |
    +-----------------------------------------------+-----------------------------------------------+

.. note::
    For backward compatibility, the execution payload ``inputs`` and ``outputs`` can be provided either as mapping
    (keys are the IDs, values are the content), or as listing (each item has content and ``"id"`` field)
    interchangeably. When working with :term:`OGC API - Processes` compliant services, the mapping representation
    should be preferred as it is the official schema, is more compact, and it allows inline specification of literal
    data (values provided without the nested ``value`` field). The listing representation is the older format employed
    during previous :term:`OGC` testbed developments.

.. note::
    Other parameters can be added to the request to provide further functionalities. Above fields are the minimum
    requirements to request a :term:`Job`. Please refer to the |exec-api|_ definition for all applicable features.

.. seealso::
    - :ref:`proc_exec_body` and :ref:`proc_exec_mode` details applicable for `Weaver` specifically.
    - `OGC API - Processes, Process Outputs <https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_process_outputs>`_
      for more general details on ``transmissionMode`` parameter.
    - `OGC API - Processes, Execution Mode <https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execution_mode>`_
      for more general details on the execution negotiation (formerly with ``mode`` parameter) and more recently
      with ``Prefer`` header.
    - |ogc-exec-sync-responses|_ and |ogc-exec-async-responses|_
      for a complete listing of available ``response`` formats considering all other parameters.

.. |exec-api| replace:: OpenAPI Execute
.. _exec-api: `exec-req`_


.. versionchanged:: 4.20

With the addition of :term:`Process` revisions (see :ref:`Update Operation <proc_op_update` section), a registered
:term:`Process` specified only by ``{processID}`` will execute the latest revision of that :term:`Process`. An older
revision can be executed by adding the tagged version in the path (``{processID}:{version}``) or adding the request
query parameter ``version``.

.. _proc_exec_body:

Execution Body
~~~~~~~~~~~~~~~~~~

The ``inputs`` definition is the most important section of the request body. It is also the only one that is completely
required when submitting the execution request, even for a no-input process (an empty mapping is needed in such case).
It defines which parameters
to forward to the referenced :term:`Process` to be executed. All ``id`` elements in this :term:`Job` request
body must correspond to valid ``inputs`` from the definition returned by :ref:`DescribeProcess <proc_op_describe>`
response. Obviously, all formatting requirements (i.e.: proper file :term:`MIME-types`),
data types (e.g.: ``int``, ``string``, etc.) and validations rules (e.g.: ``minOccurs``, ``AllowedValues``, etc.)
must also be fulfilled. When providing files as input,
multiple protocols are supported. See later section :ref:`File Reference Types` for details.

The ``outputs`` section defines, for each ``id`` corresponding to the :term:`Process` definition, how to
report the produced outputs from a successful :term:`Job` completion. For the time being, `Weaver` only implement the
``reference`` result as this is the most common variation. In this case, the produced file is
stored locally and exposed externally with returned reference URL. The other mode ``value`` returns the contents
directly in the response instead of the URL.

When ``outputs`` section is omitted, it simply means that the :term:`Process` to be executed should return all
outputs it offers in the created :ref:`Job Results <proc_op_result>`. In such case, because no representation modes
is specified for individual outputs, `Weaver` automatically selects ``reference`` as it makes all outputs more easily
accessible with distinct URL afterwards. If the ``outputs`` section is specified, but that one of the outputs defined
in the :ref:`Process Description <proc_op_describe>` is not specified, that output should be omitted from the produced
results. For the time being, because only ``reference`` representation is offered for produced output files, this
filtering is not implemented as it offers no additional advantage for files accessed directly with their distinct URLs.
This could be added later if ``Multipart`` raw data representation is required.
Please |submit-issue|_ to request this feature if it is relevant for your use-cases.

.. fixme:
.. todo::
    Filtering of ``outputs`` not implemented (everything always available).
    https://github.com/crim-ca/weaver/issues/380

Other parameters presented in the above examples, namely ``mode`` and ``response`` are further detailed in
the following :ref:`proc_exec_mode` section.

.. _proc_exec_mode:

Execution Mode
~~~~~~~~~~~~~~~~~~~~~

In order to select how to execute a :term:`Process`, either `synchronously` or `asynchronously`, the ``Prefer`` header
should be specified. If omitted, `Weaver` defaults to `asynchronous` execution. To execute `asynchronously` explicitly,
``Prefer: respond-async`` should be used. Otherwise, the `synchronous` execution can be requested
with ``Prefer: wait=X`` where ``X`` is the duration in seconds to wait for a response. If no worker becomes available
within that time, or if this value is greater than ``weaver.exec_sync_max_wait``, the :term:`Job` will resume
`asynchronously` and the response will be returned. Furthermore, `synchronous` and `asynchronous` execution of
a :term:`Process` can only be requested for corresponding ``jobControlOptions`` it reports as supported in
its :ref:`Process Description <proc_op_describe>`. It is important to provide the ``jobControlOptions`` parameter with
applicable modes when :ref:`Deploying a Process <proc_op_deploy>` to allow it to run as desired. By default, `Weaver`
will assume that deployed processes are only `asynchronous` to handle longer operations.

.. versionchanged:: 4.15
    By default, every :ref:`proc_builtin` :term:`Process` can accept both modes.
    All previously deployed processes will only allow `asynchronous` execution, as only this one was supported.
    This should be reported in their ``jobControlOptions``.

.. warning::
    It is important to remember that the ``Prefer`` header is indeed a *preference*. If `Weaver` deems it cannot
    allocate a worker to execute the task `synchronously` within a reasonable delay, it can enforce the `asynchronous`
    execution. The `asynchronous` mode is also *prioritized* for running longer :term:`Job` submitted over the task
    queue, as this allows `Weaver` to offer better availability for all requests submitted by its users.
    The `synchronous` mode should be reserved only for very quick and relatively low computation intensive operations.

The ``mode`` field displayed in the body is another method to tell whether to run the :term:`Process` in a blocking
(``sync``) or non-blocking (``async``) manner. Note that support is limited for mode ``sync`` as this use case is often
more cumbersome than ``async`` execution. Effectively, ``sync`` mode requires to have a task worker executor available
to run the :term:`Job` (otherwise it fails immediately due to lack of processing resource), and the requester must wait
for the *whole* execution to complete to obtain the result. Given that :term:`Process` could take a very long time to
complete, it is not practical to execute them in this manner and potentially have to wait hours to retrieve outputs.
Instead, the preferred and default approach is to request an ``async`` :term:`Job` execution. When doing so, `Weaver`
will add this to a task queue for processing, and will immediately return a :term:`Job` identifier and ``Location``
where the user can probe for its status, using :ref:`Monitoring <proc_op_monitor>` request. As soon as any task worker
becomes available, it will pick any leftover queued :term:`Job` to execute it.

.. note::
    The ``mode`` field is an older methodology that precedes the official :term:`OGC API - Processes` method using
    the ``Prefer`` header. It is recommended to employ the ``Prefer`` header that ensures higher interoperability
    with other services using the same standard. The ``mode`` field is deprecated and preserved only for backward
    compatibility purpose.

When requesting a `synchronous` execution, and provided a worker was available to pick and complete the task before
the maximum ``wait`` time was reached, the final status will be directly returned. Therefore, the contents obtained this
way will be identical to any following :ref:`Job Status <proc_op_status>` request. If no worker is available, or if
the worker that picked the :term:`Job` cannot complete it in time (either because it takes too long to execute or had
to wait on resources for too long), the :term:`Job` execution will automatically switch to `asynchronous` mode.

The distinction between an `asynchronous` or `synchronous` response when executing a :term:`Job` can be
observed in multiple ways. The easiest is with the HTTP status code of the response, 200 being for
a :term:`Job` *entirely completed* synchronously, and 201 for a created :term:`Job` that should be
:ref:`monitored <proc_op_monitor>` asynchronously. Another method is to observe the ``"status"`` value.
Effectively, a :term:`Job` that is executed `asynchronously` will return status information contents, while
a `synchronous` :term:`Job` will return the results directly, along a ``Location`` header referring to the
equivalent contents returned by :ref:`GetStatus <proc_op_status>` as in the case of `asynchronous` :term:`Job`.
It is also possible to extract the ``Preference-Applied`` response header which will clearly indicate if the
submitted ``Prefer`` header was respected (because it could be with available worker resources) or not.
In general, this means that if the :term:`Job` submission request was not provided with ``Prefer: wait=X`` **AND**
replied with the same ``Preference-Applied`` value, it is safe to assume `Weaver` decided to queue the :term:`Job`
for `asynchronous` execution. That :term:`Job` could be executed immediately, or at a later time, according to
worker availability.

It is also possible that a ``failed`` :term:`Job`, even when `synchronous`, will respond with equivalent contents
to the status location instead of results. This is because it is impossible for `Weaver` to return
the result(s) as outputs would not be generated by the incomplete :term:`Job`.

Finally, the ``response`` parameter defines how to return the results produced by the :term:`Process`.
When ``response=document``, regardless of ``mode=async`` or ``mode=sync``, and regardless of requested
outputs ``transmissionMode=value`` or ``transmissionMode=reference``, the results will be returned in
a :term:`JSON` format containing either literal values or URL references to produced files. If ``mode=async``,
this results *document* is obtained with |results-req|_ request, while ``mode=sync`` returns it directly.
When ``response=raw``, the specific contents (type and quantity), HTTP ``Link`` headers or a mix of those components
depends both on the number of available :term:`Process` outputs, which ones were requested, and how they were
requested (i.e.: ``transmissionMode``). It is also possible that further content negotiation gets involved
accordingly to the ``Accept`` header and available ``Content-Type`` of the outputs if multiple formats are supported
by the :term:`Process`. For more details regarding those combination, the official
|ogc-exec-sync-responses|_ and |ogc-exec-async-responses|_ should be employed as reference.

For any of the previous combinations, it is always possible to obtain :term:`Job` outputs, along with logs, exceptions
and other details using the :ref:`proc_op_result` endpoints.


.. _proc_exec_steps:

Execution Steps
~~~~~~~~~~~~~~~~~~~~~

Once the :term:`Job` is submitted, its status should initially switch to ``accepted``. This effectively means that the
:term:`Job` is pending execution (task queued), but is not yet executing. When a worker retrieves it for execution, the
status will change to ``started`` for preparation steps (i.e.: allocation resources, retrieving required
parametrization details, etc.), followed by ``running`` when effectively reaching the execution step of the underlying
:term:`Application Package` operation. This status will remain as such until the operation completes, either with
``succeeded`` or ``failed`` status.

At any moment during `asynchronous` execution, the :term:`Job` status can be requested using |status-req|_. Note that
depending on the timing at which the user executes this request and the availability of task workers, it could be
possible that the :term:`Job` be already in ``running`` state, or even ``failed`` in case of early problem detected.

When the :term:`Job` reaches its final state, multiple parameters will be adjusted in the status response to
indicate its completion, notably the completed percentage, time it finished execution and full duration. At that
moment, the requests for retrieving either error details or produced outputs become accessible. Examples are presented
in :ref:`Result <proc_op_result>` section.


Process Operations
~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: detail 'operations' accomplished (stage-in, exec-cwl, stage-out)


.. _proc_workflow_ops:

Workflow Step Operations
~~~~~~~~~~~~~~~~~~~~~~~~~

For each :ref:`proc_types` known by `Weaver`, specific :term:`Workflow` step implementations must be provided.

In order to simplify the chaining procedure of file references, step implementations are only required to provide
the relevant methodology for their :ref:`Deploy <proc_op_deploy>`, :ref:`Execute <proc_op_execute>`,
:ref:`Monitor <proc_op_monitor>` and ref:`Result <proc_op_result>` operations.
Operations related to staging of files, :term:`Process` preparation and cleanup are abstracted away from specific
implementations to ensure consistent functionalities between each type.

Operations are accomplished in the following order for each individual step:

.. list-table::
    :header-rows: 1

    * - Step Method
      - Requirements
      - Description
    * - ``prepare``
      - I*
      - Setup any prerequisites for the :term:`Process` or :term:`Job`.
    * - ``stage_inputs``
      - R
      - Retrieve input locations (considering remote files and :term:`Workflow` previous-step staging).
    * - ``format_inputs``
      - I*
      - Perform operations on staged inputs to obtain desired format expected by the target :term:`Process`.
    * - ``format_outputs``
      - I*
      - Perform operations on expected outputs to obtain desired format expected by the target :term:`Process`.
    * - ``dispatch``
      - R,I
      - Perform request for remote execution of the :term:`Process`.
    * - ``monitor``
      - R,I
      - Perform monitoring of the :term:`Job` status until completion.
    * - ``get_results``
      - R,I
      - Perform operations to obtain results location in the expected format from the target :term:`Process`.
    * - ``stage_results``
      - R
      - Retrieve results from remote :term:`Job` for local storage using output locations.
    * - ``cleanup``
      - I*
      - Perform any final steps before completing the execution or after failed execution.

.. note::
    - All methods are defined within :class:`weaver.processes.wps_process_base.WpsProcessInterface`.
    - Steps marked by ``*`` are optional.
    - Steps marked by ``R`` are required.
    - Steps marked by ``I`` are implementation dependant.

.. seealso::
    :meth:`weaver.processes.wps_process_base.WpsProcessInterface.execute` for the implementation of operations order.

.. _file_ref_types:

File Reference Types
~~~~~~~~~~~~~~~~~~~~~~~~~~

Most inputs can be categorized into two of the most commonly employed types, namely ``LiteralData`` and ``ComplexData``.
The former represents basic values such as integers or strings, while the other represents a ``File`` or ``Directory``
reference. Files in `Weaver` (and :term:`WPS` in general) can be specified with any ``formats`` as |media-types|_.

.. seealso::
    - :ref:`cwl-wps-mapping`

As for *standard* :term:`WPS`, only remote ``File`` references are *usually* handled and limited to ``http(s)`` scheme,
unless the process takes a ``LiteralData`` input string and parses the unusual reference from its value to process it
by itself. On the other hand, `Weaver` supports all following reference schemes.

- |http_scheme|
- |file_scheme|
- |s3_scheme|
- |os_scheme| [experimental]

.. note::
    Handling of ``Directory`` type for above references is specific to `Weaver`.
    Directories require specific ``formats`` and naming conditions as described in :ref:`cwl-dir`.
    Remote :term:`WPS` could support it but their expected behaviour is undefined.

The method in which `Weaver` will handle such references depends on its configuration, in other words, whether it is
running as :term:`ADES`, :term:`EMS` or :term:`HYBRID` (see: :ref:`Configuration`), as well as depending on some other
:term:`CWL` package requirements. These use-cases are described below.

.. warning::
    Missing schemes in URL reference are considered identical as if ``file://`` was used. In most cases, if not always,
    an execution request should not employ this scheme unless the file is ensured to be at the specific location where
    the running `Weaver` application can find it. This scheme is usually only employed as byproduct of the fetch
    operation that `Weaver` uses to provide the file locally to underlying :term:`CWL` application package to be
    executed.

When `Weaver` is able to figure out that the :term:`Process` needs to be executed locally in :term:`ADES` mode, it
will fetch all necessary files prior to process execution in order to make them available to the :term:`CWL` package.
When `Weaver` is in :term:`EMS` configuration, it will **always** forward remote references (regardless of scheme)
exactly as provided as input of the process execution request, since it assumes it needs to dispatch the execution
to another :term:`ADES` remote server, and therefore only needs to verify that the file reference is reachable remotely.
In this case, it becomes the responsibility of this remote instance to handle the reference appropriately. This also
avoids potential problems such as if `Weaver` as :term:`EMS` doesn't have authorized access to a link that only the
target :term:`ADES` would have access to.

When :term:`CWL` package defines ``WPS1Requirement`` under ``hints`` for corresponding `WPS-1/2`_ remote processes
being monitored by `Weaver`, it will skip fetching of |http_scheme|-based references since that would otherwise lead
to useless double downloads (one on `Weaver` and the other on the :term:`WPS` side). It is the same in situation for
``ESGF-CWTRequirement`` employed for `ESGF-CWT`_ processes. Because these processes do not always support :term:`S3`
buckets, and because `Weaver` supports many variants of :term:`S3` reference formats, it will first fetch the :term:`S3`
reference using its internal |aws-config|_, and then expose this downloaded file as |http_scheme| reference
accessible by the remote :term:`WPS` process.

.. note::
    When `Weaver` is fetching remote files with |http_scheme|, it can take advantage of additional
    :term:`Request Options` to support unusual or server-specific handling of remote reference as necessary.
    This could be employed for instance to attribute access permissions only to some given :term:`ADES` server by
    providing additional authorization tokens to the requests. Please refer to :ref:`Configuration of Request Options`
    for this matter.

.. note::
    An exception to above mentioned skipped fetching of |http_scheme| files is when the corresponding :term:`Process`
    types are intermediate steps within a `Workflow`_. In this case, local staging of remote results occurs between
    each step because `Weaver` cannot assume any of the remote :term:`Provider` is able to communicate with each other,
    according to potential :term:`Request Options` or :term:`Data Source` only configured for access by `Weaver`.

When using :term:`AWS` :term:`S3` references, `Weaver` will attempt to retrieve the files using server |aws-config|_
and |aws-credentials|_. Provided that the corresponding :term:`S3` bucket can be accessed by the running `Weaver`
application, it will fetch the files and stage them locally temporarily for :term:`CWL` execution.

.. note::
    When using :term:`S3` buckets, authorization are handled through typical :term:`AWS` credentials and role
    permissions. This means that :term:`AWS` access must be granted to the application in order to allow it
    fetching files. Please refer to :ref:`Configuration of AWS S3 Buckets` for more details.

.. important::
    Different formats for :term:`AWS` :term:`S3` references are handled by `Weaver` (see :ref:`aws_s3_ref`).
    They can be formed with generic |s3_scheme| and specific |http_scheme| with some reference to *Amazon AWS* endpoint.
    When a reference with |http_scheme|-like scheme refers to an :term:`S3` bucket, it will be converted accordingly and
    handled as any other |s3_scheme| reference. In the below :ref:`table-file-type-handling`, these special HTTP-like
    URLs should be understood as part of the |s3_scheme| category.

When using :term:`OpenSearch` references, additional parameters are necessary to handle retrieval of specific file URL.
Please refer to :ref:`OpenSearch Data Source` for more details.

Following table summarize the default behaviour of input file reference handling of different situations when received
as input argument of process execution. For simplification, keyword |any| is used to indicate that any other value in
the corresponding column can be substituted for a given row when applied with conditions of other columns, which results
to same operational behaviour. Elements that behave similarly are also presented together in rows to reduce displayed
combinations.

.. table:: Summary of File Type Handling Methods
    :name: table-file-type-handling
    :align: center

    +-----------+-----------------------------------------+---------------+-------------------------------------------+
    | |cfg|     | Process Type                            | File Scheme   | Applied Operation                         |
    +===========+=========================================+===============+===========================================+
    | |any|     | |any|                                   | |os_scheme|   | Query and re-process [#openseach]_        |
    +-----------+-----------------------------------------+---------------+-------------------------------------------+
    | |ADES|    | - `WPS-1/2`_                            | |file_scheme| | Convert to |http_scheme| [#file2http]_    |
    |           | - `ESGF-CWT`_                           +---------------+-------------------------------------------+
    |           | - `WPS-REST`_ (remote) [#wps3]_         | |http_scheme| | Nothing (unmodified)                      |
    |           | - :ref:`proc_remote_provider`           +---------------+-------------------------------------------+
    |           |                                         | |s3_scheme|   | Fetch and convert to |http_scheme| [#s3]_ |
    |           |                                         +---------------+-------------------------------------------+
    |           |                                         | |vault_ref|   | Convert to |http_scheme| [#vault2http]_   |
    |           +-----------------------------------------+---------------+-------------------------------------------+
    |           | - `WPS-REST`_ (`CWL`) [#wps3]_          | |file_scheme| | Nothing (file already local)              |
    |           |                                         +---------------+-------------------------------------------+
    |           |                                         | |http_scheme| | Fetch and convert to |file_scheme|        |
    |           |                                         +---------------+                                           |
    |           |                                         | |s3_scheme|   |                                           |
    |           |                                         +---------------+-------------------------------------------+
    |           |                                         | |vault_ref|   | Convert to |file_scheme|                  |
    +-----------+-----------------------------------------+---------------+-------------------------------------------+
    | |EMS|     | - |any| (types listed above for |ADES|) | |file_scheme| | Convert to |http_scheme| [#file2http]_    |
    |           | - `Workflow`_ (`CWL`) [#wf]_            +---------------+-------------------------------------------+
    |           |                                         | |http_scheme| | Nothing (unmodified, step will handle it) |
    |           |                                         +---------------+                                           |
    |           |                                         | |s3_scheme|   |                                           |
    |           |                                         +---------------+                                           |
    |           |                                         | |vault_ref|   |                                           |
    +-----------+-----------------------------------------+---------------+-------------------------------------------+
    | |HYBRID|  | - `WPS-1/2`_                            | |file_scheme| | Convert to |http_scheme| [#file2http]_    |
    |           | - `ESGF-CWT`_                           +---------------+-------------------------------------------+
    |           | - `WPS-REST`_ (remote) [#wps3]_         | |http_scheme| | Nothing (unmodified)                      |
    |           | - :ref:`proc_remote_provider`           +---------------+-------------------------------------------+
    |           |                                         | |s3_scheme|   | Fetch and convert to |http_scheme| [#s3]_ |
    |           | *Note*: |HYBRID| assumes |ADES| role    +---------------+-------------------------------------------+
    |           | (remote processes)                      | |vault_ref|   | Convert to |http_scheme| [#vault2http]_   |
    |           +-----------------------------------------+---------------+-------------------------------------------+
    |           | - `WPS-REST`_ (`CWL`) [#wps3]_          | |file_scheme| | Nothing (unmodified)                      |
    |           |                                         +---------------+-------------------------------------------+
    |           |                                         | |http_scheme| | Fetch and convert to |file_scheme|        |
    |           | *Note*: |HYBRID| assumes |ADES| role    +---------------+-------------------------------------------+
    |           | (local processes)                       | |vault_ref|   | Convert to |file_scheme| [#vault2file]_   |
    |           +-----------------------------------------+---------------+-------------------------------------------+
    |           | - `Workflow`_ (`CWL`) [#wf]_            | |file_scheme| | Convert to |http_scheme| [#file2http]_    |
    |           |                                         +---------------+-------------------------------------------+
    |           |                                         | |http_scheme| | Nothing (unmodified, step will handle it) |
    |           |                                         +---------------+                                           |
    |           |                                         | |s3_scheme|   |                                           |
    |           |                                         +---------------+                                           |
    |           | *Note*: |HYBRID| assumes |EMS| role     | |vault_ref|   |                                           |
    +-----------+-----------------------------------------+---------------+-------------------------------------------+

.. |any| replace:: *<any>*
.. |cfg| replace:: Configuration
.. |os_scheme| replace:: ``opensearchfile://``
.. |http_scheme| replace:: ``http(s)://``
.. |s3_scheme| replace:: ``s3://``
.. |file_scheme| replace:: ``file://``
.. |vault_ref| replace:: ``vault://<UUID>``
.. |ADES| replace:: :term:`ADES`
.. |EMS| replace:: :term:`EMS`
.. |HYBRID| replace:: :term:`HYBRID`

.. |br| raw:: html

    <br>

.. rubric:: Footnotes

.. [#openseach]
    References defined by |os_scheme| will trigger an :term:`OpenSearch` query using the provided URL as
    well as other input additional parameters (see :ref:`OpenSearch Data Source`). After processing of this query,
    retrieved file references will be re-processed using the summarized logic in the table for the given use case.

.. [#file2http]
    When a |file_scheme| (or empty scheme) maps to a local file that needs to be exposed externally for
    another remote process, the conversion to |http_scheme| scheme employs setting ``weaver.wps_output_url`` to form
    the result URL reference. The file is placed in ``weaver.wps_output_dir`` to expose it as HTTP(S) endpoint.
    Note that the HTTP(S) servicing of the file is not handled by `Weaver` itself. It is assumed that the server
    where `Weaver` is hosted or another service takes care of this task.

.. [#wps3]
    When the process refers to a remote :ref:`WPS-REST` process (i.e.: remote :term:`WPS` instance that supports
    REST bindings but that is not necessarily an :term:`ADES`), `Weaver` simply *wraps* and monitors its remote
    execution, therefore files are handled just as for any other type of remote :term:`WPS`-like servers. When the
    process contains an actual :term:`CWL` :ref:`Application Package` that defines a ``CommandLineTool`` class
    (including applications with :term:`Docker` image requirement), files are fetched as it will be executed locally.
    See :ref:`CWL CommandLineTool`, :ref:`WPS-REST` and :ref:`Remote Provider` for further details.

.. [#s3]
    When an |s3_scheme| file is fetched, is gets downloaded to a temporary |file_scheme| location, which is **NOT**
    necessarily exposed as |http_scheme|. If execution is transferred to a remove process that is expected to not
    support :term:`S3` references, only then the file gets converted as in [#file2http]_.

.. [#vault2file]
    When a |vault_ref| file is specified, the local :ref:`WPS-REST` process can make use of it directly. The file is
    therefore retrieved from the :term:`Vault` using the provided UUID and access token to be passed to the application.
    See :ref:`file_vault_inputs` and :ref:`vault_upload` for more details.

.. [#vault2http]
    When a |vault_ref| file is specified, the remote process needs to access it using the hosted :term:`Vault` endpoint.
    Therefore, `Weaver` converts any vault reference to the corresponding location and inserts the access token in the
    requests headers to authorize download from the remote server. See :ref:`file_vault_inputs` and :ref:`vault_upload`
    for more details.

.. [#wf]
    Workflows are only available on :term:`EMS` and :term:`HYBRID` instances. Since they chain processes,
    no fetch is needed as the sub-step process will do it instead as needed. See :ref:`Workflow` process as well
    as :ref:`CWL Workflow` for more details.

.. todo::
    method to indicate explicit fetch to override these? (https://github.com/crim-ca/weaver/issues/183)

.. todo::
    add tests that validate each combination of operation

.. _file_reference_names:

File Reference Names
~~~~~~~~~~~~~~~~~~~~~~~~~~

When processing any of the previous :ref:`file_ref_types`, the resulting name of the file after retrieval can
depend on the applicable scheme. In most cases, the file name is simply the last fragment of the path, whether it is
an URL, an :term:`S3` bucket or plainly a file directory path. The following cases are exceptions.

.. versionchanged:: 4.4
    When using |http_scheme| references, the ``Content-Disposition`` header can be provided with ``filename``
    and/or ``filename*`` as specified by :rfc:`2183`, :rfc:`5987` and :rfc:`6266` specifications in order to define a
    staging file name. Note that `Weaver` takes this name only as a suggestion as will ignore the preferred name if it
    does not conform to basic naming conventions for security reasons. As a general rule of thumb, common alphanumeric
    characters and separators such as dash (``-``), underscores (``_``) or dots (``.``) should be employed to limit
    chances of errors. If none of the suggested names are valid, `Weaver` falls back to the typical last fragment of
    the URL as file name.

.. versionadded:: 4.27
    References using any scheme can refer to a ``Directory``. Do do so, they must respect definitions in :ref:`cwl-dir`.
    When provided, all retrievable contents under that directory will be recursively staged.

When using |s3_scheme| references (or equivalent |http_scheme| referring to :term:`S3` bucket), the staged file names
will depend on the stored object names within the bucket. In that regard, naming conventions from :term:`AWS` should be
respected.

.. seealso::
    - |aws_s3_bucket_names|_
    - |aws_s3_obj_key_names|_

When using |vault_ref| references, the resulting file name will be obtained from the ``filename`` specified in
the ``Content-Disposition`` within the uploaded content of the ``multipart/form-data`` request.

.. seealso::
    - :ref:`vault_upload`

.. _file_vault_token:
.. _file_vault_inputs:

File Vault Inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. seealso::
    Refer to :ref:`vault_upload` section for general details about the :term:`Vault` feature.

Stored files in the :term:`Vault` can be employed as input for :ref:`proc_op_execute` operation using the
provided |vault_ref| reference from the response following upload. The :ref:`Execute <proc_op_execute>`
request must also include the ``X-Auth-Vault`` header to obtain access to the file.

.. warning::
    Avoid using the :term:`Vault` HTTP location as ``href`` input. Prefer the |vault_ref| representation.

The direct :term:`Vault` HTTP location **SHOULD NOT** be employed as input reference to a :term:`Process` to
ensure its proper interpretation during execution. There are two main reasons for this.

Firstly, using the plain HTTP endpoint will not provide any hint to `Weaver` about whether the input link
is a generic remote file or one hosted in the :term:`Vault`. With the lack of this information, `Weaver` could attempt
to download the file to retrieve it for its local :term:`Process` execution, creating unnecessary operations and wasting
bandwidth since it is already available locally. Furthermore, the :term:`Vault` behaviour that deletes the file after
its download would cause it to become unavailable upon subsequent access attempts, as it could be the case during
handling and forwarding of references during intermediate :ref:`Workflow` step operations. This could inadvertently
break the :ref:`Workflow` execution.

Secondly, without the explicit :term:`Vault` reference, `Weaver` cannot be aware of the necessary ``X-Auth-Vault``
authorization needed to download it. Using the |vault_ref| not only tells `Weaver` that it must forward any relevant
access token to obtain the file, but it also ensures that those tokens are not inadvertently sent to other locations.
Effectively, because the :term:`Vault` can be used to temporarily host sensitive data for :term:`Process` execution,
`Weaver` can better control and avoid leaking the access token to irrelevant resource locations such that only the
intended :term:`Job` and specific input can access it. This is even more important in situations where multiple
:term:`Vault` references are required, to make sure each input forwards the respective access token for retrieving
its file.

When submitting the :ref:`Execute <proc_op_execute>` request, it is important to provide the ``X-Auth-Vault`` header
with additional reference to the :term:`Vault` parameter when multiple files are involved. Each token should be
provided using a comma to separated them, as detailed below. When only one file refers to the :term:`Vault` the
parameters can be omitted since there is no need to map between tokens and distinct |vault_ref| entries.

.. literalinclude:: ../examples/vault-execute.http
    :language: http
    :caption: Sample request contents to execute process with vault files

The notation (:rfc:`5234`, :rfc:`7230#section-1.2`) of the ``X-Auth-Vault`` header is presented below.

.. parsed-literal::

    X-Auth-Vault = vault-unique / vault-multi

    vault-unique = credentials [ BWS ";" OWS auth-param ]
    vault-multi  = credentials BWS ";" OWS auth-param 1*( "," OWS credentials BWS ";" OWS auth-param )
    credentials  = auth-scheme RWS access-token
    auth-scheme  = "token"
    auth-param   = "id" "=" vault-id
    vault-id     = UUID / ( DQUOTE UUID DQUOTE )
    access-token = base64
    base64       = <base64, see :rfc:`4648#section-4`>
    DQUOTE       = <DQUOTE, see :rfc:`7230#section-1.2`>
    UUID         = <UUID, see :rfc:`4122#section-3`>
    BWS          = <BWS, see :rfc:`7230#section-3.2.3`>
    OWS          = <OWS, see :rfc:`7230#section-3.2.3`>
    RWS          = <RWS, see :rfc:`7230#section-3.2.3`>

In summary, the access token can be provided by itself by omitting the :term:`Vault` UUID parameter only
if a single file is referenced across all inputs within the :ref:`Execute <proc_op_execute>` request.
Otherwise, multiple :term:`Vault` references all require to specify both their respective access token
and UUID in a comma separated list.

.. _aws_s3_ref:

AWS S3 Bucket References
~~~~~~~~~~~~~~~~~~~~~~~~~~

File and directory references to :term:`AWS` :term:`S3` items can be defined using one of the below formats.
They can either use the |http_scheme| or |s3_scheme|, whichever one is deemed more appropriate by the user.
The relevant reference format according to the location where the |bucket| is hosted and can be accessed from
must be employed.

.. code-block:: text
    :caption: HTTP Path-style URI

    https://s3.{Region}.amazonaws.com/{Bucket}/[{dirs}/][{file-key}]

.. code-block:: text
    :caption: HTTP Virtual-hosted–style URI

    https://{Bucket}.s3.{Region}.amazonaws.com/[{dirs}/][{file-key}]

.. code-block:: text
    :caption: HTTP Access-Point-style URI

    https://{AccessPointName}-{AccountId}.s3-accesspoint.{Region}.amazonaws.com/[{dirs}/][{file-key}]

.. code-block:: text
    :caption: HTTP Outposts-style URI

    https://{AccessPointName}-{AccountId}.{outpostID}.s3-outposts.{Region}.amazonaws.com/[{dirs}/][{file-key}]

.. code-block:: text
    :caption: S3 Default Region URI

    s3://{Bucket}/[{dirs}/][{file-key}]

.. code-block:: text
    :caption: S3 Access-Point-style ARN

    arn:aws:s3:{Region}:{AccountId}:accesspoint/{AccessPointName}/[{dirs}/][{file-key}]

.. code-block:: text
    :caption: S3 Outposts-style ARN

    arn:aws:s3-outposts:{Region}:{AccountId}:outpost/{OutpostId}/accesspoint/{AccessPointName}/[{dirs}/][{file-key}]

.. warning::
    Using the |s3_scheme| with a |bucket| name directly (without |arn|) implies that the *default profile* from
    the configuration will be used (see :ref:`conf_s3_buckets`).

.. seealso::
    Following external resources can be employed for more details on the :term:`AWS` :term:`S3` service,
    nomenclature and requirements.

    - |aws_s3_bucket_names|_
    - |aws_s3_bucket_access|_
    - |aws_s3_access_points|_
    - |aws_s3_outposts|_

.. |arn| replace:: *ARN*
.. |bucket| replace:: *Bucket*

.. _opensearch_data_source:

OpenSearch Data Source
~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to provide :term:`OpenSearch` query results as input to :term:`Process` for execution, the
corresponding :ref:`Deploy <proc_op_deploy>` request body must be provided with ``additionalParameters`` in order
to indicate how to interpret any specified metadata. The appropriate :term:`OpenSearch` queries can then be applied
prior the execution to retrieve the explicit file reference(s) of :term:`EOImage` elements that have
been found and to be submitted to the :term:`Job`.

Depending on the desired context (application or per-input) over which the :term:`AOI`, :term:`TOI`, :term:`EOImage` and
multiple other metadata search filters are to be applied, their definition can be provided in the following locations
within the :ref:`Deploy <proc_op_deploy>` body.

.. list-table::
    :header-rows: 1
    :widths: 20,40,40

    * - Context
      - Location
      - Role
    * - Application
      - ``processDescription.process.additionalParameters``
      - ``http://www.opengis.net/eoc/applicationContext``
    * - Input
      - ``processDescription.process.inputs[*].additionalParameters``
      - ``http://www.opengis.net/eoc/applicationContext/inputMetadata``


The distinction between application or per-input contexts is entirely dependent of whatever is the intended processing
operation of the underlying :term:`Process`, which is why they must be defined by the user deploying the process since
there is no way for `Weaver` to automatically infer how to employ provided search parameters.

In each case, the structure of ``additionalParameters`` should be similar to the following definition:

.. code-block:: json

    {
      "additionalParameters": [
        {
          "role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
          "parameters": [
            {
              "name": "EOImage",
              "values": [
                "true"
              ]
            },
            {
              "name": "AllowedCollections",
              "values": "s2-collection-1,s2-collection-2,s2-sentinel2,s2-landsat8"
            }
          ]
        }
      ]
    }

In each case, it is also expected that the ``role`` should correspond to the location where the definition is provided
accordingly to their context from the above table.

For each deployment, processes using :term:`EOImage` to be processed into :term:`OpenSearch` query results can
interpret the following field definitions for mapping against respective inputs or application context.

.. list-table::
    :header-rows: 1
    :widths: 10,10,20,60

    * - Name
      - Values
      - Context
      - Description
    * - ``EOImage``
      - ``["true"]``
      - Input
      - Indicates that the nested parameters within the current ``additionalParameters`` section where it is located
        defines an :term:`EOImage`. This is to avoid misinterpretation by similar names that could be employed
        by other kind of definitions. The :term:`Process` input's ``id`` where this parameter is defined is the name
        that will be employed to pass down :term:`OpenSearch` results.
    * - ``AllowedCollections``
      - String of comma-separated list of collection IDs.
      - Input (same one as ``EOImage``)
      - Provides a subset of collection identifiers that are supported. During execution any specified input not
        respecting one of the defined values will fail :term:`OpenSearch` query resolution.
    * - ``CatalogSearchField``
      - ``["<name>"]``
      - Input (other one than ``EOImage``)
      - String with the relevant :term:`OpenSearch` query filter name according to the described input.
        Defines a given :term:`Process` input ``id`` to be mapped against the specified query name.
    * - ``UniqueAOI``
      - ``["true"]``
      - Application
      - Indicates that provided ``CatalogSearchField`` (typically ``bbox``) corresponds to a global :term:`AOI` that
        should be respected across multiple ``EOImage`` inputs. Otherwise, (default values: ``["false"]``)
        each ``EOImage`` should be accompanied with its respective :term:`AOI` definition.
    * - ``UniqueTOI``
      - ``["true"]``
      - Application
      - Indicates that provided ``CatalogSearchField`` (typically ``StartDate`` and ``EndDate``) corresponds to a
        global :term:`TOI` that should be respected across multiple ``EOImage`` inputs. Otherwise, (default
        values: ``["false"]``) each ``EOImage`` should be accompanied with its respective :term:`TOI` definition.

When an :term:`EOImage` is detected for a given :term:`Process`, any submitted :term:`Job` execution will expect the
defined inputs in the :term:`Process` description to indicate which images to retrieve for the application. Using
inputs defined with corresponding ``CatalogSearchField`` filters, a specific :term:`OpenSearch` query will be sent to
obtain the relevant images. The inputs corresponding to search fields will then be discarded following
:term:`OpenSearch` resolution. The resolved link(s) for to :term:`EOImage` will be substituted within the ``id`` of the
input where ``EOImage`` was specified and will be forwarded to the underlying :term:`Application Package` for execution.

.. note::
    Collection identifiers are mapped against URL endpoints defined in configuration to execute the
    appropriate :term:`OpenSearch` requests. See :ref:`conf_data_sources` for more details.

.. seealso::
    Definitions in |opensearch-deploy|_ request body provides a more detailed example of the expected structure and
    relevant ``additionalParameters`` locations.

.. seealso::
    Definitions in |opensearch-examples|_ providing different combinations of inputs, notably for using distinct
    :term:`AOI`, term:`TOI` and collections, with or without ``UniqueAOI`` and ``UniqueTOI`` specifiers.

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

.. _exec_output_location:

Outputs Location
~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, :term:`Job` results will be hosted under the endpoint configured by ``weaver.wps_output_url`` and
``weaver.wps_output_path``, and will be stored under directory defined by ``weaver.wps_output_dir`` setting.

.. warning::
    Hosting of results from the file system is **NOT** handled by `Weaver` itself. The API will only *report* the
    expected endpoints using configured ``weaver.wps_output_url``. It is up to an alternate service or the platform
    provider that serves the `Weaver` application to provide the external hosting and availability of files online
    as desired.

Each :term:`Job` will have its specific UUID employed for all of the outputs files, logs and status in order to
avoid conflicts. Therefore, outputs will be available with the following location:

.. code-block::

    {WPS_OUTPUT_URL}/{JOB_UUID}.xml             # status location
    {WPS_OUTPUT_URL}/{JOB_UUID}.log             # execution logs
    {WPS_OUTPUT_URL}/{JOB_UUID}/{output.ext}    # results of the job if successful

.. note::
    Value ``WPS_OUTPUT_URL`` in above example is resolved accordingly with ``weaver.wps_output_url``,
    ``weaver.wps_output_path`` and ``weaver.url``, as per :ref:`conf_settings` details.

When submitting a :term:`Job` for execution, it is possible to provide the ``X-WPS-Output-Context`` header.
This modifies the output location to be nested under the specified directory or sub-directories.

For example, providing ``X-WPS-Output-Context: project/test-1`` will result in outputs located at:

.. code-block::

    {WPS_OUTPUT_URL}/project/test-1/{JOB_UUID}/{output.ext}

.. note::
    Values provided by ``X-WPS-Output-Context`` can only contain alphanumeric, hyphens, underscores and path
    separators that will result in a valid directory and URL locations. The path is assumed relative by design to be
    resolved under the :term:`WPS` output directory, and will therefore reject any ``.`` or ``..`` path references.
    The path also **CANNOT** start by ``/``. In such cases, an HTTP error will be immediately raised indicating
    the symbols that where rejected when detected within ``X-WPS-Output-Context`` header.

If desired, parameter ``weaver.wps_output_context`` can also be defined in the :ref:`conf_settings` in order to employ
a default directory location nested under ``weaver.wps_output_dir`` when ``X-WPS-Output-Context`` header is omitted
from the request. By default, this parameter is not defined (empty) in order to store :term:`Job` results directly under
the configured :term:`WPS` output directory.

.. note::
    Header ``X-WPS-Output-Context`` is ignored when using `S3` buckets for output location since they are stored
    individually per :term:`Job` UUID, and hold no relevant *context* location. See also :ref:`conf_s3_buckets`.

.. versionadded:: 4.3
    Addition of the ``X-WPS-Output-Context`` header.

Email Notification
~~~~~~~~~~~~~~~~~~~~~~~~~~

When submitting a :term:`Job` for execution, it is possible to provide the ``notification_email`` field.
Doing so will tell `Weaver` to send an email to the specified address with successful or failure details
upon :term:`Job` completion. The format of the email is configurable from `weaver.ini.example`_ file with
email-specific settings (see: :ref:`Configuration`).

.. _proc_op_status:
.. _proc_op_monitor:

Monitoring of a process execution (GetStatus)
---------------------------------------------------------------------

Monitoring the execution of a :term:`Job` consists of polling the status ``Location`` provided from the :ref:`Execute`
operation and verifying the indicated ``status`` for the expected result. The ``status`` can correspond to any of the
value defined by :data:`weaver.status.JOB_STATUS_VALUES` accordingly to the internal state of the workers processing
their execution.

When targeting a :term:`Job` submitted to a `Weaver` instance, monitoring is usually accomplished through
the :term:`OGC API - Processes` endpoint using |status-req|_, which will return a :term:`JSON` body.
Alternatively, the :term:`XML` status location document returned by the :ref:`wps_endpoint` could also be
employed to monitor the execution.

In general, both endpoints should be interchangeable, using below mapping. The :term:`Job` monitoring process
keeps both contents equivalent according to their standard. For convenience, requesting the :ref:`Execute` with
``Accept: <content-type>`` header corresponding to either :term:`JSON` or :term:`XML` should redirect to the response
of the relevant endpoint, regardless of where the original request was submitted. Otherwise, the default contents
format is employed according to the chosen location.

.. list-table::
    :header-rows: 1
    :widths: 20,20,60

    * - Standard
      - Contents
      - Location
    * - :term:`OGC API - Processes`
      - JSON
      - ``{WEAVER_URL}/jobs/{JobUUID}``
    * - :term:`WPS`
      - :term:`XML`
      - ``{WEAVER_WPS_OUTPUTS}/{JobUUID}.xml``

.. seealso::
    For the :term:`WPS` endpoint, refer to :ref:`conf_settings`.

.. _proc_op_result:

Obtaining results, outputs, logs or errors
---------------------------------------------------------------------

In the case of successful :term:`Job` execution, the *outputs* can be retrieved with |outputs-req|_ request to list
each corresponding output ``id`` with the generated file reference URL. Keep in mind that the purpose of those URLs are
only to fetch the results (not persistent storage), and could therefore be purged after some reasonable amount of time.
The format should be similar to the following example, with minor variations according to :ref:`Configuration`
parameters for the base :term:`WPS` output location:

.. code-block:: json

    {
      "outputs": [
        {
          "id": "output",
          "href": "{WEAVER_URL}/wpsoutputs/f93a15be-6e16-11ea-b667-08002752172a/output_netcdf.nc"
        }
      ]
    }

For the :term:`OGC` compliant endpoint, the |results-req| request can be employed instead.
In the event of a :term:`Job` executed with ``response=document``, the contents will be very similar.
On the other hand, a :term:`Job` submitted with ``response=raw`` can produce many alternative variations according
to :term:`OGC` requirements. For this reason, the *outputs* endpoint will always provide all data and file references
in the response body as :term:`Job`, no matter the original ``response`` format. The *outputs* endpoint can also
receive additional query parameters, such as ``schema``, to return contents formatted similarly to *results*, but
enforcing a :term:`JSON` body as if ``response=document`` was specified during submission of the :term:`Process`
execution.

In order to better understand the parameters that where submitted during :term:`Job` creation, the |inputs-req|_
can be employed. This will return both the data and reference inputs that were submitted, as well as
the *requested outputs* to retrieve any relevant ``transmissionMode`` definition.

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

.. literalinclude:: ../../weaver/wps_restapi/examples/job_logs.json
    :language: json


.. note::
    All endpoints to retrieve any of the above information about a :term:`Job` can either be requested directly
    (i.e.: ``/jobs/{jobID}/...``) or with  equivalent :term:`Provider` and/or :term:`Process` prefixed endpoints,
    if the requested :term:`Job` did refer to those :term:`Provider` and/or :term:`Process`.
    A *local* :term:`Process` would have its :term:`Job` references as ``/processes/{processId}/jobs/{jobID}/...``
    while a :ref:`proc_remote_provider` will use ``/provider/{providerName}/processes/{processId}/jobs/{jobID}/...``.

.. _vault_upload:

Uploading File to the Vault
-----------------------------

The :term:`Vault` is available as secured storage for uploading files to be employed later for :term:`Process`
execution (see also :ref:`file_vault_inputs`).

.. note::
    The :term:`Vault` is a specific feature of `Weaver`. Other :term:`ADES`, :term:`EMS` and :term:`OGC API - Processes`
    servers are not expected to provide this endpoint nor support the |vault_ref| reference format.

.. seealso::
    Refer to :ref:`conf_vault` for applicable settings for this feature.

When upload succeeds, the response will return a :term:`Vault` UUID and an ``access_token`` to access the file.
Uploaded files cannot be accessed unless the proper credentials are provided. Requests toward the :term:`Vault` should
therefore include a ``X-Auth-Vault: token {access_token]`` header in combination to the provided :term:`Vault` UUID in
the request path to retrieve the file contents. The upload response will also include a ``file_href`` field formatted
with a |vault_ref| reference to be used for :ref:`file_vault_inputs`, as well as a ``Content-Location`` header of the
contextual :term:`Vault` endpoint for that file.

Download of the file is accomplished using the |vault-download-req|_ request.
In order to either obtain the file metadata without downloading it, or simply to validate its existence,
the |vault-detail-req|_ request can be used. This HEAD request can be queried any number of times without affecting
the file from the :term:`Vault`. For both HTTP methods, the ``X-Auth-Vault`` header is required.

.. note::
    The :term:`Vault` acts only as temporary file storage. For this reason, once the file has been downloaded, it is
    *immediately deleted*. Download can only occur once. It is assumed that the resource that must employ it will have
    created a local copy from the download and the :term:`Vault` doesn't require to preserve it anymore. This behaviour
    intends to limit the duration for which potentially sensitive data remains available in the :term:`Vault` as well
    as performing cleanup to limit storage space.

Using the :ref:`Weaver CLI or Python client <cli>`, it is possible to upload local files automatically to the
:term:`Vault` of a remote `Weaver` server. This can help users host their local file for remote :term:`Process`
execution. By default, the :ref:`cli` will automatically convert any local file path provided as execution input into
a |vault_ref| reference to make use of the :term:`Vault` self-hosting from the target `Weaver` instance. It will also
update the provided inputs or execution body to apply any transformed |vault_ref| references transparently. This will
allow the executed :term:`Process` to securely retrieve the files using :ref:`file_vault_inputs` behaviour. Transmission
of any required authorization headers is also handled automatically when using this approach.

It is also possible to manually provide |vault_ref| references or endpoints if those were uploaded beforehand using
the ``upload`` operation, but the user must also generate the ``X-Auth-Vault`` header manually in such case.

.. seealso::
    Section :ref:`file_vault_inputs` provides more details about the format of ``X-Auth-Vault`` for submission
    of multiple inputs.

In order to manually upload files, the below code snippet can be employed.

.. literalinclude:: ../examples/vault_upload.py
    :language: python
    :caption: Sample Python request call to upload file to Vault

This should automatically generate a *similar* request to the result below.

.. literalinclude:: ../examples/vault-upload.http
    :language: http
    :caption: Sample request contents to upload file to Vault

.. warning::
    When providing literal HTTP request contents as above, make sure to employ ``CRLF`` instead of plain ``LF`` for
    separating the data using the *boundary*. Also, make sure to omit any additional ``LF`` between the data and each
    *boundary* if this could impact parsing of the data itself (e.g.: as in the case of non-text readable base64 data)
    to avoid modifying the file contents during upload. Some additional newlines are presented in the above example
    only for readability purpose. It is recommended to use utilities like the Python example or
    the :ref:`Weaver CLI <cli>` so avoid such issues during request content generation.
    Please refer to :rfc:`7578#section-4.1` for more details regarding multipart content separators.

Note that the ``Content-Type`` embedded within the multipart content in the above example (not to be confused with the
actual ``Content-Type`` header of the request for uploading the file) can be important if the destination input of
the :term:`Process` that will consume that :term:`Vault` file for execution must provide a specific choice of
Media-Type if multiple are supported. This value could be employed to generate the explicit ``format`` portion of the
input, in case it cannot be resolved automatically from the file contents, or unless it is explicitly provided once
again for that input within the :ref:`Execute <proc_op_execute>` request body.


.. _wps_endpoint:

WPS Endpoint
---------------

This endpoint is available if ``weaver.wps`` setting was enabled (``true`` by default).
The specific location where :term:`WPS` requests it will be accessible depends on the resolution
of relevant :ref:`conf_settings`, namely ``weaver.wps_path`` and ``weaver.wps_url``.

Details regarding contents for each request is provided in schemas under |wps-req|_.

.. note::
    Using the :term:`WPS` endpoint allows fewer control over functionalities than the
    corresponding :term:`OGC API - Processes` (:term:`WPS-REST`) endpoints since it is the preceding standard.

Special Weaver EMS use-cases
==================================================

This section highlight the additional behaviour available only through an :term:`EMS`-configured `Weaver` instance.
Some other points are already described in other sections, but are briefly indicated here for conciseness.

.. |data-source| replace:: Data Source
.. _data-source:

ADES dispatching using Data Sources
--------------------------------------

When using either the :term:`EMS` or :term:`HYBRID` [#notedatasource]_ configurations, :term:`Process`
executions are dispatched to the relevant :term:`ADES` or another :term:`HYBRID` server supporting |process-deploy-op|_
when inputs are matched against one of the configured :term:`Data Source`. Minimal implementations
of :term:`OGC API - Processes` can also work as external :term:`Provider` where to dispatch executions, but in
the case of *core* implementations, the :term:`Process` should be already available since it cannot be deployed.

In more details, when an |exec-req-name|_ request is received, `Weaver` will analyse any file references in the
specified inputs and try to match them against specified :term:`Data Source` configuration. When a match is found
and that the corresponding :ref:`file_ref_types` indicates that the reference is located remotely in a known
:term:`Data Source` provider that should take care of its processing, `Weaver` will attempt to |deploy-req-name|_
the targeted :term:`Process` (and the underlying :term:`Application Package`) followed by its remote execution.
It will then monitor the :term:`Job` until completion and retrieve results if the full operation was successful.

The :term:`Data Source` configuration therefore indicates to `Weaver` how to map a given data reference to a specific
instance or server where that data is expected to reside. This procedure effectively allows `Weaver` to deliver
applications *close to the data* which can be extremely more efficient (both in terms of time and quantity) than
pulling the data locally when :term:`Data Source` become substantial. Furthermore, it allows :term:`Data Source`
providers to define custom or private data retrieval mechanisms, where data cannot be exposed or offered externally,
but are still available for use when requested.

.. rubric:: Footnotes

.. [#notedatasource]
    Configuration :term:`HYBRID` applies here in cases where `Weaver` acts as an :term:`EMS` for remote dispatch
    of :term:`Process` execution based on applicable :ref:`file_ref_types`.

.. seealso::
    Specific details about configuration of :term:`Data Source` are provided in the :ref:`conf_data_sources` section.

.. seealso::
    Details regarding :ref:`opensearch_data_source` are also relevant when resolving possible matches
    of :term:`Data Source` provider when the applicable :ref:`file_ref_types` are detected.


Workflow (Chaining Step Processes)
--------------------------------------

.. todo:: add details, explanation done in below reference

.. seealso::

    - :ref:`CWL Workflow`
    - :ref:`proc_workflow_ops`
    - :ref:`Workflow` process type
