.. include:: references.rst
.. _package:
.. _application-package:

*************************
Application Package
*************************

.. contents::
    :local:
    :depth: 3

The :term:`Application Package` defines the internal script definition and configuration that will be executed by a
:term:`Process`. This package is based on |CWL|_ (:term:`CWL`). Using the extensive |cwl-spec|_ as backbone for
internal execution of the process allows it to run multiple type of applications, whether they are referenced to
by :term:`Docker` image, scripts (`bash`, `python`, etc.), some remote :term:`Process` and more.

.. note::
    The large community and use cases covered by :term:`CWL` makes it extremely versatile. If you encounter any issue
    running your :term:`Application Package` in `Weaver` (such as file permissions for example), chances are that there
    exists a workaround somewhere in the |cwl-spec|_. Most typical problems are usually handled by some flag or argument
    in the :term:`CWL` definition, so this reference should be explored first. Please also refer to :ref:`FAQ` section
    as well as existing |Weaver-issues|_. Ultimately if no solution can be found, open an new issue about your specific
    problem.


All processes deployed locally into `Weaver` using a :term:`CWL` package definition will have their full package
definition available with |pkg-req|_ request.

.. note::

    The package request is a `Weaver`-specific implementation, and therefore, is not necessarily available on other
    :term:`ADES`/:term:`EMS` implementation as this feature is not part of |ogc-api-proc|_ specification.

.. _app_pkg_types:

Typical CWL Package Definition
===========================================

.. _app_pkg_cmd:

CWL CommandLineTool
------------------------

Following :term:`CWL` package definition represents the :py:mod:`weaver.processes.builtin.jsonarray2netcdf` process.

.. literalinclude:: ../../weaver/processes/builtin/jsonarray2netcdf.cwl
    :language: YAML
    :linenos:

The first main components is the ``class: CommandLineTool`` that tells `Weaver` it will be an *atomic* process
(contrarily to :ref:`app_pkg_workflow` presented later).

The other important sections are ``inputs`` and ``outputs``. These define which parameters will be expected and
produced by the described application. `Weaver` supports most formats and types as specified by |cwl-spec|_.
See :ref:`cwl-io-types` for more details.


.. _app_pkg_script:

Script Application
~~~~~~~~~~~~~~~~~~~~~~~~

When deploying a ``CommandLineTool`` that only needs to execute script or shell commands, it is recommended
to define an appropriate |cwl-docker-req|_ to containerize the :term:`Process`, even though no *advanced*
operation is needed. The reason for this is because there is no way for `Weaver` to otherwise know for sure
how to provide all appropriate dependencies that this operation might need. In order to preserve processing
environment and results separate between any :term:`Process` and `Weaver` itself, the executions will either be
automatically containerized (with some default image), or blocked entirely when `Weaver` cannot resolve the
appropriate execution environment. Therefore, it is recommended that the :term:`Application Package` provider
defines a specific image to avoid unexpected failures if this auto-resolution changes across versions.

Below are minimalistic :term:`Application Package` samples that make use of a shell command
and a custom Python script for quickly running some operations, without actually needing to package any
specialized :term:`Docker` image.

The first example simply outputs the contents of a ``file`` input using the ``cat`` command.
Because the :term:`Docker` image ``debian:stretch-slim`` is specified, we can guarantee that the command will be
available within its containerized environment. In this case, we also take advantage of the ``stdout.log`` which
is always collected by `Weaver` (along with the ``stderr``) in order to obtain traces produced by any
:term:`Application Package` when performing :term:`Job` executions.

.. literalinclude:: ../examples/docker-shell-script-cat.cwl
    :language: yaml
    :caption: Sample CWL definition of a shell script

The second example takes advantage of the |cwl-workdir-req|_ to generate a Python script dynamically
(i.e.: ``script.py``), prior to executing it for processing the received inputs and produce the output file.
Because a Python runner is required, the |cwl-docker-req|_ specification defines a basic :term:`Docker` image that
meets our needs. Note that in this case, special interpretation of ``$(...)`` entries within the definition can be
provided to tell :term:`CWL` how to map :term:`Job` input values to the dynamically created script.

.. literalinclude:: ../examples/docker-python-script-report.cwl
    :language: yaml
    :caption: Sample CWL definition of a Python script
    :name: example_app_pkg_script

.. seealso::
    See the :ref:`app_pkg_python` section for more utilities to help create an :term:`Application Package` from Python.

.. seealso::
    For other programing languages, see |cwl-dev-tools|_ for a list of related utilities that helps working
    with :term:`CWL`, some of which offering convertion capabilities.

.. _app_pkg_python:

Python Applications
~~~~~~~~~~~~~~~~~~~~~~~~

When the :term:`Application Package` to be generated consists of a Python script, which happens to make use of
the builtin |python-argparse|_ package, it is possible to employ the |argparse2tool|_ utility, which will automatically
generate a corresponding :term:`CWL` definition using the specified :term:`CLI` arguments and their types.

The |argparse2tool|_ utility can help quickly generate a valid :term:`CWL` definition, but it is the responsibility
of the user to validate that converted arguments have the appropriate types, or any additional metadata required to
properly describe the intended :term:`Process`. Notably, users might find the need to add appropriate ``format``
definitions to the :term:`I/O`, since those will generally be missing descriptive :term:`Media-Types`.

.. note::
    Although |argparse2tool|_ can help in the initial :term:`CWL` generation procedure, it is recommended to apply
    additional containerization best-practices, such as described in :ref:`app_pkg_script`, to increase chances to
    obtain a replicable and reusable :term:`Application Package` definition.

.. seealso::
    For pure Python scripts not using |python-argparse|_, the |scriptcwl|_ utility can be considered instead.

.. seealso::
    For Python code embedded in |jupyter-notebooks|_, refer to :ref:`app_pkg_jupyter_notebook` for more details.

.. |python-argparse| replace:: ``argparse``
.. _python-argparse: https://docs.python.org/3/library/argparse.html

.. |argparse2tool| replace:: ``argparse2tool``
.. _argparse2tool: https://github.com/hexylena/argparse2tool

.. |scriptcwl| replace:: ``scriptcwl``
.. _scriptcwl: https://github.com/NLeSC/scriptcwl

.. _app_pkg_jupyter_notebook:

Jupyter Notebook Applications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When working on experimental or research applications, a |jupyter-notebook|_ is a popular development environment,
due to its convenient interface for displaying results, interacting with visualization tools, or the larger plugin
ecosystem that it can offer. However, a |jupyter-notebook|_ is typically insufficient by itself to describe a complete
application. To help developers transition from a |jupyter-notebook|_ to :ref:`app_pkg_docker`, which ensures the
:term:`Application Package` can be deployed and reused, the |jupyter-ipython2cwl|_ utility can be employed.

Using |jupyter-repo2cwl| (after installing |jupyter-ipython2cwl|_ in the Python environment), it is possible to
directly convert a Git repository reference containing a |jupyter-notebook|_ into deployable :term:`CWL` leveraging
a :term:`Docker` container. To do this, the utility uses two strategies under the hood:

1. |jupyterhub-repo2docker|_ is employed to convert a Git repository into a :term:`Docker` container, with any
   applicable package requirements, project metadata, and advanced configuration details.
2. Python typing annotations provided by |jupyter-ipython2cwl|_ define the :term:`CWL` :term:`I/O`
   from variables and results located within the |jupyter-notebook|_.

.. note::
    Because |jupyterhub-repo2docker|_ is employed, which is highly adaptable to many use cases, all typical Python
    project `Configuration Files <https://repo2docker.readthedocs.io/en/latest/config_files.html>`_,
    such as ``requirements.txt``, ``environment.yml``, ``setup.py``, ``pyproject.toml``, etc. can be employed.
    The :term:`Docker` container dependencies can be provided with an explicit ``Dockerfile`` as well.
    Please refer to the official documentation for all advanced configuration options.

Because Python type annotations are employed with |jupyter-repo2cwl|
to indicate which variables will contain the :term:`CWL` :term:`I/O` references, it is actually possible
to annotate a |jupyter-notebook|_ *without any additional package dependencies*. To do so, one only needs
to employ *string annotations* as follows.

.. literalinclude:: ../examples/jupyter_repo2cwl_python.py
    :language: python
    :caption: Sample CWL annotations of Python code in Jupyter Notebook
    :name: example_app_pkg_jupyter_repo2cwl_python

.. seealso::
    See `IPython2CWL Supported Types <https://ipython2cwl.readthedocs.io/en/latest/#module-ipython2cwl.iotypes>`_
    for more details about the mapping from a Python annotation to the resulting :term:`CWL` :ref:`cwl-io-types`.

When the above code is saved in a |jupyter-notebook|_ and committed to a Git repository, the |jupyterhub-repo2docker|_
utility can automatically clone the repository, parse the Python code, extract the :term:`CWL` annotations, and
generate the :term:`Application Package` with a :term:`Docker` container containing all of their respective definitions.
All of this is accomplished with a single call to obtain a deployable :term:`CWL` in `Weaver`, which can then take over
from the :ref:`Process Deployment <proc_op_deploy>` to obtain an :term:`OGC API - Process` definition.

Jupyter Notebook to CWL Example: NCML to STAC Application
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For a more concrete example of a |jupyter-notebook|_ convertion to :term:`CWL`, see the |ncml2stac-repo|_ GitHub
repository, which contains a sample |ncml2stac-notebook|_.
This script, as indicated by its name, converts *NCML XML metadata with CMIP6 attributes* into the
corresponding *SpatioTemporal Asset Catalog* (STAC) definition and extensions.
It uses the same `IPython2CWL <jupyter-repo2cwl>`_ type annotation strategy as presented
:ref:`above <example_app_pkg_jupyter_repo2cwl_python>` to indicate which NCML ``File`` variable is to be employed as
as the :term:`CWL` input reference, and the expected STAC ``File`` as output to be collected by :term:`CWL`.

Using |jupyter-repo2cwl| and the :ref:`Weaver CLI <cli_commands>` in combination, as shown below,
it is possible to automatically convert the |jupyter-notebook|_ script into a Dockerized :term:`CWL` and
deploy it to a :term:`OGC API - Processes` server supporting :term:`Application Package` such as `Weaver`.

.. code-block:: shell
    :caption: |jupyter-notebook|_ conversion to :term:`CWL` and deployment as :term:`OGC API - Processes`

    jupyter-repo2cwl "https://github.com/crim-ca/ncml2stac" -o /tmp
    weaver deploy -u http://example.com/weaver -i ncml2stac --cwl /tmp/notebooks_ncml2stac.cwl

.. seealso::
    - Refer to the |ncml2stac-repo|_ repository's README for more details about the utilities.
    - Refer to the |ncml2stac-notebook|_ for the implementation of the :term:`Application Package` script.

.. |jupyter-notebook| replace:: Jupyter Notebook
.. _jupyter-notebook: https://jupyter.org/

.. |jupyterhub-repo2docker| replace:: ``jupyterhub/repo2docker``
.. _jupyterhub-repo2docker: https://github.com/jupyterhub/repo2docker

.. |jupyter-repo2cwl| replace:: ``jupyter repo2cwl``

.. |jupyter-ipython2cwl| replace:: ``IPython2CWL``
.. _jupyter-ipython2cwl: https://github.com/common-workflow-lab/ipython2cwl

.. |ncml2stac-repo| replace:: ``crim-ca/ncml2stac``
.. _ncml2stac-repo: https://github.com/crim-ca/ncml2stac/tree/main#ncml-to-stac

.. |ncml2stac-notebook| replace:: NCML to STAC Jupyter Notebook
.. _ncml2stac-notebook: https://github.com/crim-ca/ncml2stac/blob/main/notebooks/ncml2stac.ipynb

.. _app_pkg_docker:

Dockerized Applications
~~~~~~~~~~~~~~~~~~~~~~~~

When advanced processing capabilities and more complicated environment preparation are required, it is recommended
to package and push pre-built :term:`Docker` images to a remote registry. In this situation, just like
for :ref:`app_pkg_script` examples, the |cwl-docker-req|_ is needed. The definitions would also be essentially the
same as previous examples, but with more complicated operations and possibly larger amount of inputs or outputs.

Whenever a :term:`Docker` image reference is detected, `Weaver` will ensure that the application will be pulled
using :term:`CWL` capabilities in order to run it.

Because :term:`Application Package` providers could desire to make use of :term:`Docker` images hosted on private
registries, `Weaver` offers the capability to specify an authorization token through HTTP request headers during
the :term:`Process` deployment. More specifically, the following definition can be provided during a
:ref:`Deploy <proc_op_deploy>` request.

.. code-block:: http

    POST /processes HTTP/1.1
    Host: weaver.example.com
    Content-Type: application/json;charset=UTF-8
    X-Auth-Docker: Basic <base64_token>

    { "processDescription": { }, "executionUnit": { } }


The ``X-Auth-Docker`` header should be defined exactly like any typical ``Authorization`` headers (|auth-schemes|_).
The name ``X-Auth-Docker`` is inspired from existing implementations that employ ``X-Auth-Token`` in a similar fashion.
The reason why ``Authorization`` and ``X-Auth-Token`` headers are not themselves employed in this case is to ensure
that they do not interfere with any proxy or server authentication mechanism, which `Weaver` could be located behind.

For the moment, only ``Basic`` (:rfc:`7617`) authentication is supported.
To generate the base64 token, following methods can be used:

.. code-block:: shell
    :caption: Command Line

    echo -n "<username>:<password>" | base64

.. code-block:: python
    :caption: Python

    import base64
    base64.b64encode(b"<username>:<password>")


When the HTTP ``X-Auth-Docker`` header is detected in combination of a |cwl-docker-req|_ entry within
the :term:`Application Package` of the :term:`Process` being deployed, `Weaver` will parse the targeted :term:`Docker`
registry defined in ``dockerPull`` and will attempt to identify it for later authentication towards it with the
provided token. Given a successful authentication, `Weaver` should then be able to pull the :term:`Docker` image
whenever required for launching new :term:`Job` executions.

.. note::
    `Weaver` only attempts to authenticate itself temporarily at the moment when the :term:`Job` is submitted to
    retrieve the :term:`Docker` image, and only if the image is not already available locally. Because of this, the
    provided authentication token should have a sufficient lifetime to run the :term:`Job` at later times, considering
    any retention time of cached :term:`Docker` images on the server. If the cache is cleaned, and the :term:`Docker`
    image is made unavailable, `Weaver` will attempt to authenticate itself again when receiving the new :term:`Job`.
    It is left up to the developer and :term:`Application Package` provider to manage expired tokens in `Weaver`
    according to their needs. To resolve such cases, the |update-token-req|_ request or an entire re-deployment
    of the :term:`Process` could be accomplished, whichever is more convenient for them.

.. versionadded:: 4.5
    Specification and handling of the ``X-Auth-Docker`` header for providing an authentication token.

.. _app_pkg_resources:

GPU and Resource dependant Applications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When an :term:`Application Package` requires GPU or any other minimal set of hardware capabilities, such as in the
case of machine learning or high-performance computing tasks, the submitted :term:`CWL` must explicitly indicate
those requirements to ensure they can be met for performing its execution. Similarly, an :term:`Application Package`
that must obtain external access to remote contents must not assume that the connection would be available, and
must therefore request network access. Below are examples where such requirements are demonstrated and how to
define them.

.. literalinclude:: ../examples/requirement-cuda.cwl
    :language: yaml
    :caption: Sample CWL definition with CUDA capabilities
    :name: example_app_pkg_cuda

.. literalinclude:: ../examples/requirement-resources.cwl
    :language: yaml
    :caption: Sample CWL definition with computing resources
    :name: example_app_pkg_resources

.. literalinclude:: ../examples/requirement-network.cwl
    :language: yaml
    :caption: Sample CWL definition with network access
    :name: example_app_pkg_network

Above requirements can be combined in any fashion as needed. They can also be combined with any other requirements
employed to define the core components of the application.

Whenever possible, requirements should be provided with values that best match the minimum and maximum amount of
resources that the :term:`Application Package` operation requires. More precisely, over-requesting resources should
be avoided as this could lead to failing :term:`Job` execution if the server or worker node processing it deems it
cannot fulfill the requirements because they are too broad to obtain proper resource assignation, because it has
insufficient computing resources, or simply for rate-limiting/fair-share reasons.

Although definitions such as |cwl-resource-req|_ and |cwl-cuda-req|_ are usually applied for atomic operations,
they can also become relevant in the context of :ref:`app_pkg_workflow` execution. Effectively, providing the
required hardware capabilities for each atomic application can allow the :term:`Workflow` engine to better schedule
:term:`Job` steps. For example, if two computationally heavy steps happened to have no restriction for parallelization
based on the :term:`Workflow` steps definition alone, but that running both of them simultaneously on the same machine
would necessarily end up causing an ``OutOfMemory`` error due to insufficient resources, those requirements could help
preemptively let the engine know to wait until *reserved* resources become available. As a result, execution of the
second task could be delayed until the first task is completed, therefore avoiding the error.

.. versionadded:: 4.17
    Support of |cwl-resource-req|_.

.. versionadded:: 4.27
    Support of |cwl-network-req|_ and |cwl-cuda-req|_.

.. versionchanged::
    Deprecated ``DockerGpuRequirement``.

.. warning::
    Any :term:`Application Package` that was making use of ``DockerGpuRequirement`` should be updated to employ
    the official |cwl-docker-req|_ in combination with |cwl-cuda-req|_. For backward compatibility, any detected
    ``DockerGpuRequirement`` definition will be updated automatically with a minimalistic |cwl-cuda-req|_ definition
    using a very lax set of CUDA capabilities. It is recommended to provide specific configurations for your needs.

.. _app_pkg_remote:
.. _app_pkg_wps1:
.. _app_pkg_ogc_api:
.. _app_pkg_esgf_cwt:

Remote Applications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To define an application that refers to a :ref:`proc_remote_provider`, an :ref:`proc_wps_12`, an :ref:`proc_ogc_api`
or an :ref:`proc_esgf_cwt` endpoint, the corresponding `Weaver`-specific :term:`CWL`-like requirements must be employed
to indicate the URL where that remote resource is accessible. Once deployed, the contained :term:`CWL`
package and the resulting :term:`Process` will be exposed as a :ref:`proc_ogc_api` resource.

Upon reception of a :ref:`Process Execution <proc_op_execute>` request, `Weaver` will take care of resolving
the indicated process URL from the :term:`CWL` requirement and will dispatch the execution to the resource
after applying any relevant I/O, parameter and Media-Type conversion to align with the target server standard
for submitting the :term:`Job` requests.

Below are examples of the corresponding :term:`CWL` requirements employed for each type of remote application.

.. code-block:: yaml
    :caption: WPS-1/2 Package Definition

    cwlVersion: "v1.0"
    class: CommandLineTool
    hints:
      WPS1Requirement:
        provider: "https://example.com/ows/wps/catalog"
        process: "getpoint"

.. code-block:: yaml
    :caption: OGC API Package Definition

    cwlVersion: "v1.0"
    class: CommandLineTool
    hints:
      OGCAPIRequirement:
        process: "https://example.com/ogcapi/processes/getpoint"

.. code-block:: json
    :caption: ESGF-CWT Package Definition

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


.. seealso::
    - :ref:`proc_remote_provider`
    - :ref:`proc_wps_12`
    - :ref:`proc_ogc_api`
    - :ref:`proc_esgf_cwt`

.. _app_pkg_workflow:

CWL Workflow
------------------------

`Weaver` also supports :term:`CWL` ``class: Workflow``. When an :term:`Application Package` is defined this way, the
|process-deploy-op|_ will attempt to resolve each ``step`` as another process. The reference to the :term:`CWL`
definition can be placed in any location supported as for the case of atomic processes
(see details about :ref:`supported package locations <proc_ogc_api>`).

The following :term:`CWL` definition demonstrates an example ``Workflow`` process that would resolve each ``step`` with
local processes of match IDs.

.. literalinclude:: ../../tests/functional/application-packages/WorkflowSubsetIceDays/package.cwl
    :language: JSON
    :linenos:

For instance, the ``jsonarray2netcdf`` (:ref:`Builtin`) middle step in this example corresponds to the
`CWL CommandLineTool`_ process presented in previous section. Other processes referenced in this ``Workflow`` can be
found in |test-res|_.

Steps processes names are resolved using the variations presented below. Important care also needs to be given to
inputs and outputs definitions between each step.


.. |test-res| replace:: Weaver Test Resources
.. _test-res: https://github.com/crim-ca/weaver/tree/master/tests/functional/application-packages

Step Reference
~~~~~~~~~~~~~~~~~

In order to resolve referenced processes as steps, `Weaver` supports 3 formats.

1. | Process ID explicitly given.
   | Any *visible* process from |getcap-req|_ response should be resolved this way.
   | (e.g.: ``jsonarray2netcdf`` resolves to pre-deployed :py:mod:`weaver.processes.builtin.jsonarray2netcdf`).
2. Full URL to the process description endpoint, provided that it also offers a |pkg-req|_ endpoint (`Weaver`-specific).
3. Full URL to the explicit `CWL` file (usually corresponding to (2) or the ``href`` provided in deployment body).

When an URL to the :term:`CWL` process "file" is provided with an extension, it must be one of the supported values
defined in :py:data:`weaver.processes.wps_package.PACKAGE_EXTENSIONS`. Otherwise, `Weaver` will refuse it as it cannot
figure out how to parse it.

Because `Weaver` and the underlying `CWL` executor need to resolve all steps in order to validate their input and
output definitions correspond (id, format, type, etc.) in order to chain them, all intermediate processes **MUST**
be available. This means that you cannot :ref:`Deploy <proc_op_deploy>` nor :ref:`Execute <proc_op_execute>`
a ``Workflow``-flavored :term:`Application Package` until all referenced steps have themselves been deployed and
made visible.

.. warning::

    Because `Weaver` needs to convert given :term:`CWL` documents into equivalent :term:`WPS` process definition,
    embedded :term:`CWL` processes within a ``Workflow`` step are not supported currently. This is a known limitation
    of the implementation, but not much can be done against it without major modifications to the code base.
    See also issue `#56 <https://github.com/crim-ca/weaver/issues/56>`_.

.. seealso::

    - :py:func:`weaver.processes.wps_package.get_package_workflow_steps`
    - :ref:`Deploy <proc_op_deploy>` request details.

Step Inputs/Outputs
~~~~~~~~~~~~~~~~~~~~~

Inputs and outputs of connected steps are required to match types and formats in order for the workflow to be valid.
This means that a process that produces an output of type ``String`` cannot be directly chained to a process that takes
as input a ``File``, even if the ``String`` of the first process represents an URL that could be resolved to a valid
file reference. In order to chain two such processes, an intermediate operation would need to be defined to explicitly
convert the ``String`` input to the corresponding ``File`` output. This is usually accomplished using :ref:`Builtin`
processes, such as in the previous example.

Since formats must also match (e.g.: a process producing ``application/json`` cannot be mapped to one producing
``application/x-netcdf``), all mismatching formats must also be converted with an intermediate step if such operation
is desired. This ensures that workflow definitions are always explicit and that as little interpretation, variation or
assumptions are possible between each execution. Because of this, all application generated by `Weaver` will attempt to
preserve and enforce matching input/output ``format`` definition in both :term:`CWL` and :term:`WPS` as long as it does
not introduce ambiguous results (see :ref:`File Format` for more details).


.. _cwl-wps-mapping:

Correspondence between CWL and WPS fields
===========================================

Because :term:`CWL` definition and :term:`WPS` process description inherently provide "duplicate" information, many
fields can be mapped between one another. In order to handle any provided metadata in the various supported locations
by both specifications, as well as to extend details of deployed processes, each :term:`Application Package` get its
details merged with complementary :term:`WPS` description.

In some cases, complementary details are only documentation-related, but some information directly affect the format or
execution behaviour of some parameters. A common example is the ``maxOccurs`` field provided by :term:`WPS` that does
not have an exactly corresponding specification in :term:`CWL` (any-sized array). On the other hand, :term:`CWL` also
provides data preparation steps such as initial staging (i.e.: ``InitialWorkDirRequirement``) that doesn't have an
equivalent under the :term:`WPS` process description. For this reason, complementary details are merged and reflected
on both sides (as applicable), when non-ambiguous resolution is possible.

In case of conflicting metadata, the :term:`CWL` specification will most of the time prevail over the :term:`WPS`
metadata fields simply because it is expected that a strict `CWL` specification is provided upon deployment.
The only exceptions to this situation are when :term:`WPS` specification help resolve some ambiguity or when
:term:`WPS` enforces the parametrisation of some elements, such as with ``maxOccurs`` field.

.. note::

    Metadata merge operation between :term:`CWL` and :term:`WPS` is accomplished on *per-mapped-field* basis. In other
    words, more explicit details such as ``maxOccurs`` could be obtained from :term:`WPS` and **simultaneously** the
    same input's ``format`` could be obtained from the :term:`CWL` side. Merge occurs bidirectionally for corresponding
    information.

The merging strategy of process specifications also implies that some details can be omitted from one context if they
can be inferred from corresponding elements in the other. For example, the :term:`CWL` and :term:`WPS` context both
define ``keywords`` (with minor naming variation) as a list of strings. Specifying this metadata in both locations
is redundant and only makes the process description longer. Therefore, the user is allowed to provide only one of the
two and `Weaver` will take care to propagate the information to the lacking location.

In order to help understand the resolution methodology between the contexts, following sub-section will cover supported
mapping between the two specifications, and more specifically, how each field impacts the mapped equivalent metadata.

.. warning::

    Merging of corresponding fields between :term:`CWL` and :term:`WPS` is a `Weaver`-specific implementation.
    The same behaviour is not necessarily supported by other implementations. For this reason, any converted
    information between the two contexts will be transferred to the other context if missing in order for both
    specification to reflect the similar details as closely as possible, wherever context the metadata originated from.


Inputs/Outputs ID
-----------------------

Inputs and outputs (:term:`I/O`) ``id`` from the :term:`CWL` context will be respectively matched against corresponding
``id`` or ``identifier`` field from I/O of :term:`WPS` context. In the :term:`CWL` definition, all of the allowed I/O
structures are supported, whether they are specified using an array list with explicit definitions, using "shortcut"
variant (i.e.: ``<type>[]``), or using key-value pairs (see |cwl-io-map|_ for more details). Regardless of array or
mapping format, :term:`CWL` requires that all I/O have unique ``id``.
On the :term:`WPS` side, either a mapping or list of I/O are also expected with unique ``id``.

.. versionchanged:: 4.0
    Previous versions only supported :term:`WPS` I/O using the listing format. Both can be used interchangeably in
    both :term:`CWL` and :term:`WPS` contexts as of this version.

To summarize, the following :term:`CWL` and :term:`WPS` I/O definitions are all equivalent and will result into the
same process definition after deployment. For simplification purpose, below examples omit all but mandatory fields
(only of the ``inputs`` and ``outputs`` portion of the full deployment body) to produce the same result.
Other fields are discussed afterward in specific sections.

.. table::
    :class: code-table
    :align: center

    +-----------------------------------+----------------------------------------+----------------------------------+
    | .. code-block:: json              | .. code-block:: json                   | .. code-block:: json             |
    |   :caption: CWL I/O objects array |   :caption: CWL I/O key-value mapping  |   :caption: WPS I/O definition   |
    |   :linenos:                       |   :linenos:                            |   :linenos:                      |
    |                                   |                                        |                                  |
    |   {                               |   {                                    |   {                              |
    |     "inputs": [                   |     "inputs": {                        |     "inputs": [                  |
    |       {                           |       "single-str": {                  |       {                          |
    |         "id": "single-str",       |         "type": "string"               |         "id": "single-str"       |
    |         "type": "string"          |       },                               |       },                         |
    |       },                          |       "multi-file": {                  |       {                          |
    |       {                           |         "type": "File[]"               |         "id": "multi-file",      |
    |         "id": "multi-file",       |       }                                |         "formats": []            |
    |         "type": "File[]"          |     },                                 |       }                          |
    |       }                           |     "outputs": {                       |     ],                           |
    |     ],                            |       "output-1": {                    |     "outputs": [                 |
    |     "outputs": [                  |         "type": "File"                 |       {                          |
    |       {                           |       },                               |         "id": "output-1",        |
    |         "id": "output-1",         |       "output-2": {                    |         "formats": []            |
    |         "type": "File"            |         "type": "File"                 |       },                         |
    |       },                          |       }                                |       {                          |
    |       {                           |     }                                  |         "id": "output-2",        |
    |         "id": "output-2",         |   }                                    |         "formats": []            |
    |         "type": "File"            |                                        |       }                          |
    |       }                           |                                        |     ]                            |
    |     ]                             |                                        |   }                              |
    |   }                               |                                        |                                  |
    +-----------------------------------+----------------------------------------+----------------------------------+

The :term:`WPS` example above requires a ``format`` field for the corresponding :term:`CWL` ``File`` type in order to
distinguish it from a plain string. More details are available in :ref:`cwl-io-types` below about this requirement.

Finally, it is to be noted that above :term:`CWL` and :term:`WPS` definitions can be specified in
the :ref:`Deploy <proc_op_deploy>` request body with any of the following variations:

1. Both are simultaneously fully specified (valid although extremely verbose).
2. Both partially specified as long as sufficient complementary information is provided.
3. Only :term:`CWL` :term:`I/O` is fully provided
   (with empty or even unspecified ``inputs`` or ``outputs`` section from :term:`WPS`).

.. warning::
    `Weaver` assumes that its main purpose is to eventually execute an :term:`Application Package` and will therefore
    prioritize specification in :term:`CWL` over :term:`WPS` to infer types. Because of this, any unmatched ``id`` from
    the :term:`WPS` context against provided :term:`CWL` ``id``\s of the same I/O section **will be dropped**, as they
    ultimately would have no purpose during :term:`CWL` execution.

    This does not apply in the case of referenced :ref:`proc_wps_12` processes since no :term:`CWL` is available in the
    first place.

.. _cwl-io-types:

Inputs/Outputs Type
-----------------------

In the :term:`CWL` context, the ``type`` field indicates the type of :term:`I/O`.
Available types are presented in the |cwl-io-type|_ portion of the :term:`CWL` specification.

.. _warn-any:
.. warning::

    `Weaver` does not support :term:`CWL` ``type: Any``. This limitation is **intentional** in order to guarantee
    proper resolution of :term:`CWL` types to their corresponding :term:`WPS` definitions. Furthermore, the ``Any``
    type would make the :term:`Process` description too ambiguous.

Type Correspondance
~~~~~~~~~~~~~~~~~~~~

A summary of applicable types is presented below.

Those :term:`CWL` types can be mapped to :term:`WPS` and/or :term:`OAS` contexts in order to obtain corresponding
:term:`I/O` definitions. However, not every type exists in each of those contexts. Therefore, some types will
necessarily be simplified or converted to their best corresponding match when exact mapping cannot be accomplished.
The simplification of types can happen when converting in any direction
(:term:`CWL` |nbsp| |<=>| |nbsp| :term:`WPS` |nbsp| |<=>| |nbsp| :term:`OAS`).
It all depends on which definitions that were provided are the more specific. For example, a :term:`WPS` ``dateTime``
will be simplified to a generic :term:`CWL` ``string``, and into an :term:`OAS` ``string`` with ``format: "date-time"``.
In this example, it would be important to provide the :term:`WPS` or :term:`OAS` definitions if the *date-time* portion
was critical, since it could not be inferred only from :term:`CWL` ``string``.

Further details regarding handling methods or important considerations for
specific types will be presented in :ref:`cwl-type` and :ref:`cwl-dir` sections.

+----------------------+-------------------------+------------------------+--------------------------------------------+
| :term:`CWL` ``type`` | :term:`WPS` data type   | :term:`OAS` type       | Description                                |
|                      | and sub-type :sup:`(1)` |                        |                                            |
+======================+=========================+========================+============================================+
| ``Any``              | |na|                    | |na|                   | Not supported. See :ref:`note <warn-any>`. |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``null``             | |na|                    | |na|                   | Cannot be used by itself. |br|             |
|                      |                         |                        | Represents optional :term:`I/O` when       |
|                      |                         |                        | combined with other types :sup:`(2)`.      |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``boolean``          | ``Literal`` |br|        | ``boolean``            | Binary value.                              |
|                      | (``bool``, ``boolean``) |                        |                                            |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``int``,             | ``Literal`` |br|        | ``integer``,           | Numeric whole value. |br|                  |
| ``long``             | (``int``, ``integer``,  | ``number`` |br|        | Unless when explicit conversion between    |
|                      | ``long``,               | (format: ``int32``,    | contextes can accomplished, the generic    |
|                      | ``positiveInteger``,    | ``int64``) :sup:`(3)`  | ``integer`` will be employed.              |
|                      | ``nonNegativeInteger``) |                        |                                            |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``float``,           | ``Literal`` |br|        | ``number`` |br|        | Numeric floating-point value.              |
| ``double``           | (``float``, ``double``, | (format: ``float``,    | By default, ``float`` is used unless more  |
|                      | ``scale``, ``angle``)   | ``double``) :sup:`(3)` | explicit context conversion can be         |
|                      |                         |                        | accomplished :sup:`(4)`.                   |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``string``           | ``Literal`` |br|        | ``string`` |br|        | Generic string. Default employed if        |
|                      | (``string``,  ``date``, | (format: ``date``,     | nothing more specific is resolved. |br|    |
|                      | ``time``, ``dateTime``, | ``time``,              |                                            |
|                      | ``anyURI``)             | ``datetime``,          | This type can be used to represent any     |
|                      |                         | ``date-time``,         | :ref:`File Reference <file_ref_types>`     |
|                      |                         | ``full-date``,         | as plain URL string without resolution.    |
|                      |                         | ``uri``, ``url``,      |                                            |
|                      |                         | etc.) :sup:`(5)`       |                                            |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``File``             | ``BoundingBox``         | :term:`JSON`           | Partial support available. |br|            |
|                      |                         | :sup:`(6)`             | See :ref:`note <bbox-note>`.               |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``File``             | ``Complex``             | :term:`JSON`           | :ref:`File Reference <file_ref_types>`     |
|                      |                         | :sup:`(6)`             | with Media-Type validation and staging     |
|                      |                         |                        | according to the applicable scheme.        |
+----------------------+-------------------------+------------------------+--------------------------------------------+
| ``Directory``        | ``Complex``             | :term:`JSON`           | :ref:`Directory Reference <cwl-dir>`       |
|                      |                         | :sup:`(6)`             | handled as nested ``Files`` to stage.      |
+----------------------+-------------------------+------------------------+--------------------------------------------+

| :sup:`(1)` Resolution method according to critical fields defined in :ref:`cwl-type`.
| :sup:`(2)` More details in :ref:`oas_basic_types` and :ref:`cwl-array-null-values` sections.
| :sup:`(3)` Number is used in combination with ``format`` to find best match between integer and floating point values.
  If not provided, it defaults to ``float`` to handle both cases.
| :sup:`(4)` The ``float`` name is employed loosely to represent any *floating-point* value rather than
  *single-precision* (16-bits). Its internal representation is *double-precision* (32-bits) given that the
  implementation is in Python.
| :sup:`(5)` Because ``string`` is the default, any ``format`` and ``pattern`` can be specified.
  More specific types with these items can help apply additional validation, although not strictly enforced.
| :sup:`(6)` Specific schema required as described in :ref:`oas_json_types`.

.. _bbox-note:
.. note::
    The :term:`WPS` data type ``BoundingBox`` has a schema definition in :term:`WPS` and :term:`OAS` contexts,
    but is not handled natively by :term:`CWL` types. When the conversion to a :term:`CWL` job occurs, an equivalent
    ``Complex`` type using a :term:`CWL` ``File`` with ``format: ogc-bbox`` and the contents stored as :term:`JSON` is
    employed. It is up to the :term:`Application Package` to parse this :term:`JSON` content as necessary.
    Alternatively, it is possible to use a ``Literal`` data of type ``string`` corresponding to :term:`WKT` [#]_ if it
    is deemed preferable that the :term:`CWL` script receives the data directly without intermediate interpretation.

.. [#] |wkt-example|_

.. _cwl-type:

Type Resolution
~~~~~~~~~~~~~~~

In the :term:`WPS` context, three data types exist, namely ``Literal``, ``BoundingBox`` and ``Complex`` data.

As presented in previous examples, :term:`I/O` in the :term:`WPS` context does not require an explicit indication of
which data type from one of ``Literal``, ``BoundingBox`` and ``Complex`` to apply. Instead, :term:`WPS` type can be
inferred using the matched API schema of the I/O. For instance, ``Complex`` I/O (e.g.: file reference) requires the
``formats`` field to distinguish it from a plain ``string``. Therefore, specifying either ``format`` in :term:`CWL`
or ``formats`` in :term:`WPS` immediately provides all needed information for `Weaver` to understand that this I/O is
expected to be a file reference.

.. code-block:: json
    :caption: WPS Complex Data Type
    :linenos:

    {
      "id": "input",
      "formats": [
        {"mediaType": "application/json", "default": true}
      ]
    }

A combination of ``supportedCRS`` objects providing ``crs`` references would
otherwise indicate a ``BoundingBox`` :term:`I/O` (see :ref:`note <bbox-note>`).

.. code-block:: json
    :caption: WPS BoundingBox Data Type
    :linenos:

    {
      "id": "input",
      "supportedCRS": [
        {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84", "default": true}
      ]
    }

If none of the two previous schemas are matched, the :term:`I/O` type resolution falls back
to ``Literal`` data of ``string`` type. To employ another primitive data type such as ``Integer``,
an explicit indication needs to be provided as follows.

.. code-block:: json
    :caption: WPS Literal Data Type
    :linenos:

    {
      "id": "input",
      "literalDataDomains": [
        {"dataType": {"name": "integer"}}
      ]
    }

Obviously, the equivalent :term:`CWL` definition is simpler in this case (i.e.: only ``type: int`` is required).
It is therefore *recommended* to take advantage of `Weaver`'s merging strategy during
:ref:`Process Deployment <proc_op_deploy>` in this case by providing only the details through
the :term:`CWL` definition and have the corresponding :term:`WPS` I/O type automatically deduced by
the generated process. If desired, ``literalDataDomains`` can still be explicitly provided as above to ensure that
it gets parsed as intended type.

.. versionadded:: 4.16

With more recent versions of `Weaver`, it is also possible to employ :term:`OpenAPI` schema (:term:`OAS`) definitions
provided in the I/O to specify the explicit structure that applies to ``Literal``, ``BoundingBox`` and ``Complex``
data types. When :term:`OpenAPI` schema are detected, they are also considered in the merging strategy along with
other specifications provided in :term:`CWL` and :term:`WPS` contexts. More details about :term:`OAS` context is
provided in :ref:`oas_io_schema` section.

.. _dir_ref_type:
.. _cwl-dir:

Directory Type
~~~~~~~~~~~~~~

.. versionchanged:: 4.27
    Support of :term:`CWL` ``type: Directory`` added to `Weaver`.

In order to map a ``Directory`` to the underlying :term:`WPS` :term:`Process` that do not natively offer this
type of reference, a ``Complex`` "*pseudo-file*" using Media-Type ``application/directory`` is employed. For further
validation that a ``Directory`` is properly parsed by `Weaver`, provided URL references must also end with a trailing
slash (``/``) character.

.. warning::
    Note that, when using ``Directory`` type, very few format and content validation can be accomplished for individual
    files contained in that directory. The contents must therefore match the definitions expected by the application
    receiving it. No explicit validation is accomplished by `Weaver` to ensure if expected contents are available.

When a ``Directory`` type is specified in the :term:`Process` definition, and that
a :ref:`File Reference <file_ref_types>` is provided during :ref:`Execution <proc_op_execute>`, the reference
pointed to as ``Directory`` must provide a listing of files. Those files can either be relative to the ``Directory``
or other absolute :ref:`File Reference <file_ref_types>` locations. The applicable scheme to stage those files will
be applied as needed based on resolved references. It is therefore possible to mix URL schemes between the listed
references. For example, a ``Directory`` listing as :term:`JSON` obtained from a ``https://`` endpoint could provide
multiple ``File`` locations from ``s3://`` buckets to stage for :ref:`Process Execution <proc_op_execute>`.

The following ``Directory`` listing formats are supported.

.. table::
    :class: code-table
    :align: center
    :widths: 70,30

    +-----------------------------------------------------------+------------------------------------------------------+
    | Listing Format                                            | Description                                          |
    +===========================================================+======================================================+
    | .. literalinclude:: ../examples/directory-listing.html    | A file index where each reference to be staged       |
    |    :caption: HTML File Index                              | should be contained in a ``<a href="{ref}"/>`` tag.  |
    |    :language: yaml                                        |                                                      |
    |                                                           | The structure can be contained in a ``<table>``,     |
    |                                                           | an HTML list (``<ol>``, ``<ul>``), plain list of     |
    |                                                           | ``<a>`` hyperlinks, and can contain any amount of    |
    |                                                           | CSS or nested HTML tags.                             |
    +-----------------------------------------------------------+------------------------------------------------------+
    | .. literalinclude:: ../examples/directory-listing.json    | A :term:`JSON` body returned from an endpoint        |
    |    :caption: JSON File List                               | obtained by ``GET`` request, which advertises the    |
    |    :language: json                                        | corresponding ``Content-Type: application/json``     |
    |                                                           | header. Each listed file to be staged should also    |
    |                                                           | be accessible on provided endpoints.                 |
    +-----------------------------------------------------------+------------------------------------------------------+
    | .. literalinclude:: ../examples/directory-listing-s3.json | Any supported :term:`S3` endpoint as detailed in     |
    |    :caption: AWS S3 Bucket                                | |aws_s3_bucket_access|_ that provides a listing      |
    |    :language: json                                        | of file objects to be staged. Proper access must be  |
    |                                                           | granted as per :ref:`conf_s3_buckets` if the bucket  |
    |                                                           | contents are not publicly accessible.                |
    |                                                           | More details about supported references can be found |
    |                                                           | in :ref:`aws_s3_ref`.                                |
    +-----------------------------------------------------------+------------------------------------------------------+

.. _cwl-file-format:

File Format
-----------------------

An input or output resolved as :term:`CWL` ``File`` type, equivalent to a :term:`WPS` ``ComplexData``, supports
``format`` specification. Every ``mimeType`` field nested under ``formats`` entries of the :term:`WPS` definition
will be mapped against corresponding *namespaced* ``format`` of :term:`CWL`.

.. note::
    For :term:`OGC API - Processes` conformance and backward compatible support, both ``mimeType`` and ``mediaType``
    can be used interchangeably for :ref:`Process Deployment <proc_op_deploy>`.
    For :ref:`Process Description <proc_op_describe>`, the employed name depends on the requested ``schema`` as query
    parameter, defaulting to :term:`OGC API - Processes` ``mediaType`` representation if unspecified.

Following is an example where input definitions are equivalent in both :term:`CWL` and :term:`WPS` contexts.

.. table::
    :class: code-table
    :align: center
    :widths: 50,50

    +-----------------------------------------------+-----------------------------------------------------------------+
    | .. code-block:: json                          | .. code-block:: json                                            |
    |    :caption: WPS Format with MIME-type        |    :caption: CWL Format with Namespace                          |
    |    :linenos:                                  |    :linenos:                                                    |
    |                                               |                                                                 |
    |    {                                          |    {                                                            |
    |      "id": "input",                           |      "inputs": [                                                |
    |      "formats": [                             |        {                                                        |
    |        {"mimeType": "application/x-netcdf"},  |          "id": "input",                                         |
    |        {"mimeType": "application/json"}       |          "format": [                                            |
    |      ]                                        |            "edam:format_3650",                                  |
    |    }                                          |            "iana:application/json"                              |
    |                                               |          ]                                                      |
    |                                               |        }                                                        |
    |                                               |      ],                                                         |
    |                                               |      "$namespaces": {                                           |
    |                                               |        "edam": "http://edamontology.org/",                      |
    |                                               |        "iana": "https://www.iana.org/assignments/media-types/"  |
    |                                               |      }                                                          |
    |                                               |    }                                                            |
    +-----------------------------------------------+-----------------------------------------------------------------+


As demonstrated, both contexts accept multiple formats for inputs. These effectively represent *supported formats* by
the underlying application. The two :term:`Media-Types` selected for this example are chosen specifically to demonstrate
how :term:`CWL` formats must be specified. More precisely, :term:`CWL` requires a real schema definition referencing to
an existing ontology to validate formats, specified through the ``$namespaces`` section. Each format entry is then
defined as a mapping of the appropriate namespace to the identifier of the ontology. Alternatively, you can also provide
the full URL of the ontology reference in the format string.

Like many other fields, this information can become quite rapidly redundant and difficult to maintain. For this reason,
`Weaver` will automatically fill the missing detail if only one of the two corresponding information between :term:`CWL`
and :term:`WPS` is provided. In other words, an application developer could only specify the :term:`I/O`'s ``formats``
in the :term:`WPS` portion during process deployment, and `Weaver` will take care to update the matching :term:`CWL`
definition without any user intervention. This makes it also easier for the user to specify supported formats since it
is generally easier to remember names of :term:`Media-types` than full ontology references. `Weaver` has a large set of
commonly employed :term:`Media-Types` that it knows how to convert to corresponding ontologies. Also, `Weaver` will look
for new :term:`Media-Types` it doesn't explicitly know about onto either the :term:`IANA` or the :term:`EDAM` ontologies
in order to attempt automatically resolving them.

When formats are resolved between the two contexts, `Weaver` applies information in a complimentary fashion. This means
for example that if the user provided ``application/x-netcdf`` on the :term:`WPS` side and ``iana:application/json`` on
the :term:`CWL` side, both resulting contexts will have both of those formats combined. `Weaver` will not favour one
location over the other, but will rather merge them if they can be resolved into different and valid entities.

Since ``formats`` is a required field for :term:`WPS` ``ComplexData`` definitions (see :ref:`cwl-io-types`) and
that :term:`Media-Types` are easier to provide in this context, it is *recommended* to provide all of them in the
:term:`WPS` definition. Alternatively, the :ref:`oas_io_schema` representation also located within the
:term:`WPS` I/O definitions can be used to provide ``contentMediaType``.

Above examples present the minimal content of ``formats`` :term:`JSON` objects
(i.e.: ``mimeType`` or ``mediaType`` value), but other fields, such as ``encoding`` and ``schema``
can be provided as well to further refine the specific format supported by the corresponding :term:`I/O` definition.
These fields are directly mapped, merged and combined against complementary details provided with ``contentMediaType``,
and ``contentEncoding`` and ``contentSchema`` within an :term:`OAS` schema (see :ref:`oas_io_schema`).

.. _cwl-file-format-output:

Output File Format
~~~~~~~~~~~~~~~~~~~~~~

.. warning::
    Format specification differs between :term:`CWL` and :term:`WPS` in the case of outputs.

Although :term:`WPS` definition allows multiple *supported formats* for output that are later resolved to the *applied*
one onto the produced result of the job, :term:`CWL` only considers the output ``format`` that directly indicates the
*applied* schema. There is no concept of *supported format* in the :term:`CWL` world. This is simply because :term:`CWL`
cannot predict nor reliably determine which output will be produced by a given application execution without running it,
and therefore cannot expose consistent output specification before running the process. Because :term:`CWL` requires to
validate the full process integrity before it can be executed, this means that only a **single** output format is
permitted in its context (providing many will raise a validation error when parsing the :term:`CWL` definition).

To ensure compatibility with multiple *supported formats* outputs of :term:`WPS`, any output that has more that one
format will have its ``format`` field dropped in the corresponding :term:`CWL` definition. Without any ``format`` on the
:term:`CWL` side, the validation process will ignore this specification and will effectively accept any type of file.
This will not break any execution operation with :term:`CWL`, but it will remove the additional validation layer of the
format (which especially deteriorates process resolution when chaining processes inside a :ref:`app_pkg_workflow`).

If the :term:`WPS` output only specifies a single MIME-type, then the equivalent format (after being resolved to a valid
ontology) will be preserved on the :term:`CWL` side since the result is ensured to be the unique one provided. For this
reason, processes with specific single-format output are be preferred whenever possible. This also removes ambiguity
in the expected output format, which usually requires a *toggle* input specifying the desired type for processes
providing a multi-format output. It is instead recommended to produce multiple processes with a fixed output format for
each case.

.. _cwl-allowed-values:

Allowed Values
-----------------------

Allowed values in the context of :term:`WPS` ``Literal`` data provides a mean for the application developer to restrict
inputs to a specific set of values. In :term:`CWL`, the same can be achieved using an ``enum`` definition. Therefore,
the following two variants are equivalent and completely interchangeable.

.. table::
    :class: code-table
    :align: center
    :widths: 50,50

    +---------------------------------------------------+-----------------------------------------------+
    | .. code-block:: json                              | .. code-block:: json                          |
    |    :caption: WPS AllowedValues Input              |    :caption: CWL Enum Values                  |
    |    :linenos:                                      |    :linenos:                                  |
    |                                                   |                                               |
    |    {                                              |    {                                          |
    |      "id": "input",                               |      "id": "input",                           |
    |      "literalDataDomains": [                      |      "type": {                                |
    |        {"allowedValues": ["value-1", "value-2"]}  |        "type": "enum",                        |
    |      ]                                            |        "symbols": ["value-1", "value-2"]      |
    |    }                                              |      }                                        |
    |                                                   |    }                                          |
    +---------------------------------------------------+-----------------------------------------------+

`Weaver` will ensure to propagate such definitions bidirectionally in order to update the :term:`CWL` or :term:`WPS`
correspondingly with the provided information in the other context if missing. The primitive type to apply to a missing
:term:`WPS` specification when resolving it from a :term:`CWL` definition is automatically inferred with the best
matching type from provided values in the ``enum`` list.

Note that ``enum`` such as these will also be applied on top of :ref:`Multiple and Optional Values` definitions
presented next.

.. _cwl-array-null-values:

Multiple and Optional Values
--------------------------------------------

Inputs that take *multiple* values or references can be specified using ``minOccurs`` and ``maxOccurs`` in :term:`WPS`
context, while they are specified using the ``array`` type in `CWL`. While the same ``minOccurs`` parameter with a
value of zero (``0``) can be employed to indicate an *optional* input, :term:`CWL` requires the type to specify
``"null"`` or to use the shortcut ``?`` character suffixed to the base type to indicate optional input.
Resolution between :term:`WPS` and :term:`CWL` for the merging strategy implies all corresponding parameter
combinations and checks in this case.

.. warning::
    Ensure to specify ``"null"`` with quotes when working with :term:`JSON`, :term:`YAML` and :term:`CWL` file formats
    and/or contents submitted to :term:`API` requests or with the :term:`CLI`. Using an unquoted ``null`` will result
    into a parsed ``None`` value which will not be detected as *nullable* :term:`CWL` type.

Because :term:`CWL` does not take an explicit amount of maximum occurrences, information in this case are not
necessarily completely interchangeable. In fact, :term:`WPS` is slightly more verbose and easier to define in this case
than :term:`CWL` because all details are contained within the same two parameters. Because of this, it is often
preferable to provide the ``minOccurs`` and ``maxOccurs`` in the :term:`WPS` context, and let `Weaver` infer the
``array`` and/or ``"null"`` type requirements automatically. Also, because of all implied parameters in this situation
to specify the similar details, it is important to avoid providing contradicting specifications as `Weaver` will have
trouble guessing the intended result when merging specifications. If unambiguous guess can be made, :term:`CWL` will be
employed as the overruling definition to resolve erroneous mismatches (as for any other corresponding fields).

.. warning::
    Parameters ``minOccurs`` and ``maxOccurs`` are not permitted for outputs in the :term:`WPS` context. Native
    :term:`WPS` therefore does not permit multiple output reference files or data values under a same output ID.
    To see potential workarounds, refer to :ref:`Multiple Outputs` section.

.. note::
    Although :term:`WPS` multi-value inputs are defined as a single entity during deployment, special care must be taken
    to the format in which to specify these values during execution. Please refer to :ref:`Multiple Inputs` section
    of :ref:`Execute <proc_op_execute>` request.

Following are a few examples of equivalent :term:`WPS` and :term:`CWL` definitions to represent multiple values under
a given input. Some parts of the following definitions are purposely omitted to better highlight the concise details
of *multiple* and *optional* information.

.. table::
    :class: code-table
    :align: center
    :widths: 50,50

    +---------------------------------------------------+-----------------------------------------------------------+
    | .. code-block:: json                              | .. code-block:: json                                      |
    |    :caption: WPS Multi-Value Input (required)     |    :caption: CWL Multi-Value Input (required)             |
    |    :linenos:                                      |    :linenos:                                              |
    |                                                   |                                                           |
    |    {                                              |    {                                                      |
    |      "id": "input-multi-required",                |      "id": "input-multi-required",                        |
    |      "format": "application/json",                |      "format": "iana:application/json",                   |
    |      "minOccurs": 1,                              |      "type": {                                            |
    |      "maxOccurs": "unbounded"                     |        "type": "array", "items": "File"                   |
    |    }                                              |      }                                                    |
    |                                                   |    }                                                      |
    |                                                   |                                                           |
    +---------------------------------------------------+-----------------------------------------------------------+


It can be noted from the examples that ``minOccurs`` and ``maxOccurs`` can be either an ``integer`` or a ``string``
representing one. This is to support backward compatibility of older :term:`WPS` specification that always employed
strings although representing numbers. `Weaver` understands and handles both cases. Also, ``maxOccurs`` can have the
special string value ``"unbounded"``, in which case the input is considered to be allowed an unlimited amount if
entries (although often capped by another implicit machine-level limitation such as memory capacity). In the case of
:term:`CWL`, an ``array`` is always considered as *unbounded*, therefore :term:`WPS` is the only context that can limit
this amount.

.. _oas_io_schema:

Inputs/Outputs OpenAPI Schema
------------------------------

.. versionadded:: 4.16

.. _oas_basic_types:

Basic Type Definitions
~~~~~~~~~~~~~~~~~~~~~~

Alternatively to parameters presented in previous sections, and employed for representing
:ref:`Multiple and Optional Values`, :ref:`Allowed Values` specifications, supported :ref:`File Format` definitions
and/or :ref:`cwl-io-types` identification, the :term:`OpenAPI` specification can be employed to entirely
define the :term:`I/O` schema. More specifically, this is accomplished by providing an :term:`OAS`-compliant structure
under the ``schema`` field of each corresponding :term:`I/O`. This capability allows each :term:`Process` to be
compliant with :term:`OGC API - Processes` specification that requires this detail in
the :ref:`Process Description <proc_op_describe>`. The same kind of ``schema`` definitions can be used
for the :ref:`Deploy <proc_op_deploy>` operation.

For example, the below representations are equivalent between :term:`WPS`, :term:`OAS` and :term:`CWL` definitions.
Obviously, corresponding definitions can become more or less complicated with multiple combinations of corresponding
parameters presented later in this section. Some definitions are also not completely portable between contexts.

.. table::
    :class: code-table
    :align: center
    :widths: 33,34,33

    +-------------------------------+------------------------------+-----------------------------+
    | .. code-block:: json          | .. code-block:: json         | .. code-block:: json        |
    |    :caption: WPS Input        |    :caption: OAS Input       |    :caption: CWL Input      |
    |    :linenos:                  |    :linenos:                 |    :linenos:                |
    |                               |                              |                             |
    |    {                          |    {                         |    {                        |
    |      "id": "input",           |      "id": "input",          |      "id": "input",         |
    |      "literalDataDomains": [  |      "schema": {             |      "type": {              |
    |        {                      |        "type": "array",      |        "type": "array",     |
    |           "allowedValues": [  |        "items": {            |        "items": {           |
    |             "value-1",        |          "type": "string",   |          "type": "enum",    |
    |             "value-2"         |          "enum": [           |          "symbols": [       |
    |           ]                   |            "value-1",        |            "value-1",       |
    |        }                      |            "value-2"         |            "value-2"        |
    |      ],                       |          ]                   |          ]                  |
    |      "minOccurs": 2,          |        },                    |        }                    |
    |      "maxOccurs": 4           |        "minItems": 2,        |      }                      |
    |    }                          |        "maxItems": 4         |    }                        |
    |                               |      }                       |                             |
    |                               |    }                         |                             |
    +-------------------------------+------------------------------+-----------------------------+

.. seealso::
    An example with extensive variations of supported :term:`I/O` definitions with :term:`OAS` is
    available in |test-oas|_. This is also the corresponding example provided by :term:`OGC API - Processes`
    standard to ensure `Weaver` complies to its specification.

.. |test-oas| replace:: tests/functional/application-packages/EchoProcess/describe.yml
.. _test-oas: https://github.com/crim-ca/weaver/tree/master/tests/functional/application-packages/EchoProcess/describe.yml

As per all previous parameters in :term:`CWL` and :term:`WPS` contexts, details provided in :term:`OAS` schema are
complementary and `Weaver` will attempt to infer, combine and convert between the various representations as best
as possible according to the level of details provided.

Furthermore, `Weaver` will *extend* (as needed) any provided ``schema`` during
:ref:`Process Deployment <proc_op_deploy>` if it can identify that the specific :term:`OAS` definition is inconsistent
with other parameters. For example, if ``minOccurs``/``maxOccurs`` were provided by indicating that the :term:`I/O` must
have exactly between [2-4] elements, but only a single :term:`OAS` object was defined under ``schema``, that :term:`OAS`
definition would be converted to the corresponding array, as single values are not permitted in this case. Similarly, if
the range of items was instead [1-4], the :term:`OAS` definition would be adjusted with ``oneOf`` keyword, allowing both
single value and array representation of those values, when submitted for :ref:`Process Execution <proc_op_execute>`.

Below is a summary of fields that are equivalent or considered to identify similar specifications
(corresponding fields are aligned in the table).
Note that all :term:`OAS` elements are always nested under the ``schema`` field of an :term:`I/O`, with parameters
located where appropriate as per :term:`OpenAPI` specification. Other :term:`OAS` fields are still permitted, but
are not explicitly handled to search for corresponding definitions in :term:`WPS` and :term:`CWL` contexts.

+-------------------------------------+---------------------------------------+-------------------------------------+
| Parameters in :term:`WPS` Context   | Parameters in :term:`OAS` Context     | Parameters in :term:`CWL` Context   |
+=====================================+=======================================+=====================================+
| ``minOccurs``/``maxOccurs`` |br|    | ``type``/``oneOf`` combination |br|   | ``type`` modifiers: |br|            |
|                                     |                                       |                                     |
| - ``minOccurs=0``                   | - single type unless ``minItems=0``   | - ``?``/``"null"`` if ``min*=0``    |
| - ``maxOccurs>1`` or ``unbounded``  | - ``minItems``/``maxItems`` (array)   | - ``[]``/``array`` if ``max*>1``    |
+-------------------------------------+---------------------------------------+-------------------------------------+
| ``formats`` |br|                    | ``oneOf`` (for each format) |br|      | ``format`` |br|                     |
|                                     |                                       |                                     |
| - ``mimeType``/``mediaType``        | - ``contentMediaType``                | - *namespaced* ``mediaType``        |
| - ``encoding``                      | - ``contentEncoding``                 | - |na|                              |
| - ``schema``                        | - ``contentSchema``                   | - full-URI ``format``/``$schema``   |
+-------------------------------------+---------------------------------------+-------------------------------------+
| ``literalDataDomains``              | |br|                                  | |br|                                |
|                                     |                                       |                                     |
| - ``allowedValues`` (int/float/str) | - ``enum`` array of values            | - ``enum`` type with ``symbols``    |
|                                     |   |br| |br| |br|                      |   |br| |br| |br|                    |
| - ``allowedValues`` (range) |br|    |                                       |                                     |
|     - ``minimumValue``              | - ``minimum`` value                   | - |na| |br|                         |
|     - ``maximumValue``              | - ``maximum`` value                   | - |na| |br|                         |
|     - ``spacing``                   | - ``multipleOf`` value                | - |na| |br|                         |
|     - ``rangeClosure`` |br|         | - ``exclusiveMinimum``/               | - |na| |br|                         |
|       (combination of open, closed, |   ``exclusiveMaximum`` |br| (set      |   |br| |br|                         |
|       open-closed, closed-open)     |   ``true`` for corresponding "open")  |   |br| |br|                         |
|                                     |   |br| |br| |br|                      |                                     |
| - ``valueDefinition`` (name)        | - ``type``/``format`` combination     | - ``type`` (simplified as needed)   |
| - ``default``                       | - ``default``                         | - ``default`` and ``?``/``"null"``  |
+-------------------------------------+---------------------------------------+-------------------------------------+

In order to be :term:`OGC`-compliant, any previously deployed :term:`Process` will automatically generate any missing
``schema`` specification for all :term:`I/O` it employs when calling its :ref:`Process Description <proc_op_describe>`.
Similarly, a deployed :term:`Process` that did not make use of the ``schema`` representation method to define its
:term:`I/O` will also generate the corresponding :term:`OAS` definitions from other :term:`WPS` and :term:`CWL`
contexts, provided those definitions offered sufficiently descriptive and valid :term:`I/O` parameters for deployment.

.. _oas_json_types:

JSON Types
~~~~~~~~~~~~~~~~~~~

Along above parameter combinations, :term:`OAS` context also accomplishes the auto-detection of common :term:`JSON`
structures to convert between raw-data string formatted as :term:`JSON`, literal :term:`JSON` object embedded in the
body, and ``application/json`` file references toward the corresponding ``Complex`` :term:`WPS` input or output.
When any of those three :term:`JSON` definition is detected, other equivalent representations will be added using
a ``oneOf`` keyword if they were not already explicitly provided in ``schema``. When analyzing and combining those
definitions, any :term:`OAS` ``$ref`` or ``contentSchema`` specifications will be used to resolve the corresponding
``type: object`` with the most explicit ``schema`` definition available. If this cannot be achieved, a generic
``object`` allowing any ``additionalProperties`` (i.e.: no :term:`JSON` schema variation) will be used instead.
External URIs pointing to an :term:`OAS` schema formatted either as :term:`JSON` or :term:`YAML` are resolved and
fetched inline as needed during :term:`I/O` merging strategy to interpret specified references.

Following is a sample representation of equivalent variants :term:`JSON` definitions, which would be
automatically expended using the ``oneOf`` structure with other missing components if applicable.

.. table::
    :class: code-table
    :align: center
    :widths: 50,50

    +-----------------------------------------------------------+---------------------------------------------------+
    | .. code-block:: json                                      | .. code-block:: json                              |
    |   :caption: JSON Complex Input with schema reference      |   :caption: Generic JSON Complex Input            |
    |                                                           |                                                   |
    |    {                                                      |    {                                              |
    |      "id:" "input",                                       |      "id:" "input",                               |
    |      "schema": {                                          |      "schema": {                                  |
    |        "oneOf": [                                         |        "oneOf": [                                 |
    |          {                                                |          {                                        |
    |            "type": "string",                              |            "type": "string",                      |
    |            "contentMediaType": "application/json"         |            "contentMediaType": "application/json" |
    |            "contentSchema": "http://host.com/schema.json" |          },                                       |
    |          },                                               |          {                                        |
    |          {                                                |            "type": "object",                      |
    |            "$ref": "http://host.com/schema.json"          |            "additionalProperties": true           |
    |          }                                                |          }                                        |
    |        ]                                                  |        ]                                          |
    |      }                                                    |      }                                            |
    |    }                                                      |    }                                              |
    +-----------------------------------------------------------+---------------------------------------------------+


Special handling of well-known :term:`OAS` ``type: object`` structures is also performed to convert them to more
specific and appropriate :term:`WPS` types intended for their purpose. For instance, a *measurement* value provided
along with an `Unit of Measure` (:term:`UoM`) is converted to a :term:`WPS` ``Literal``. An object containing ``bbox``
and ``crs`` fields with the correct schema are converted to :term:`WPS` ``BoundingBox`` type. Except for these special
cases, all other :term:`OAS` ``type: object`` are otherwise converted to :term:`WPS` ``Complex`` type, which in turn is
communicated to the :term:`CWL` application using a ``File`` :term:`I/O`. Other non-:term:`JSON` definitions are also
converted using the same :term:`WPS` ``Complex``/:term:`CWL` ``File``, but their values cannot be submitted with literal
:term:`JSON` structures during :ref:`Process Execution <proc_op_execute>`, only using raw-data (i.e: encoding string)
or a file reference.

.. seealso::
    File |test-oas|_ provides example :term:`I/O` definitions for mentioned special :term:`OAS` interpretations
    and more advanced :term:`JSON` schemas with nested :term:`OAS` keywords.

.. _oas_file_references:

File References
~~~~~~~~~~~~~~~~~~~

It is important to consider that all :term:`OAS` ``schema`` that can be provided during a :ref:`Deploy <proc_op_deploy>`
request or retrieved from a :ref:`Process Description <proc_op_describe>` only define the *expected value*
representations of the :term:`I/O` data to be submitted for :ref:`Execution <proc_op_execute>` request.
In other words, an :term:`I/O` typed as ``Complex`` that can be submitted using any of the supported
:ref:`file_ref_types` to be forwarded to :term:`CWL` **SHOULD NOT** add any URI-related definition in ``schema``.
It is implicit for every :term:`Process` that an :term:`I/O` of given supported :term:`Media-Types` can be submitted by
reference using a link pointing to contents of such types. This implicit file reference interpretation serves multiple
purposes.

1. Using only *expected value* definition and leaving out the by-reference equivalent greatly simplifies the ``schema``
   definitions since every single ``Complex`` :term:`I/O` does not need to provide a very verbose ``schema``
   containing a ``oneOf(file-ref,raw-data)`` representation to indicate that data can be submitted both by value or
   by reference.

2. Using a generic ``{"type": "string", "format": "uri"}`` :term:`OAS` schema does not convey the :term:`Media-Types`
   requirements as well as inferring them "link-to" ``{"type": "string", "contentMediaType: <format>}``. It is therefore
   better to omit them entirely as they do not add any :term:`I/O` descriptive value.

3. Because the above string-formatted ``uri`` are left out from definitions, it can instead be used explicitly in an
   :term:`I/O` specification to indicate to `Weaver` that the :term:`Process` uses a ``Literal`` URI string, that must
   not be fetched by `Weaver`, and must be passed down as plain string URI directly without modification or
   interpretation to the underlying :term:`CWL` :term:`Application Package`.

To summarize, strings with ``format: uri`` will **NOT** be considered as ``Complex`` :term:`I/O` by `Weaver`. They will
be seen as any other string ``Literal``, but this allows a :term:`Process` describing its :term:`I/O` as an external URI
reference. This can be useful for an application that handles itself the retrieval of the resource referred to by this
URI. To represent supported formats of ``Complex`` file references, the ``schema`` should be represented using the
following structures. If the ``contentMediaType`` happens to be :term:`JSON`, then the explicit :term:`OAS` ``object``
schema can be added as well, as presented in :ref:`oas_json_types` section.

.. table::
    :class: code-table
    :align: center
    :widths: 50,50

    +-------------------------------------------+-------------------------------------------------------+
    | .. code-block:: json                      | .. code-block:: json                                  |
    |    :caption: Single Format Complex Input  |    :caption: Multiple Supported Format Complex Input  |
    |                                           |                                                       |
    |    {                                      |    {                                                  |
    |      "id:" "input",                       |      "id:" "input",                                   |
    |      "schema": {                          |      "schema": {                                      |
    |        "type": "string",                  |        "oneOf": [                                     |
    |        "contentMediaType": "image/png",   |          {                                            |
    |        "contentEncoding": "base64"        |            "type": "string",                          |
    |      }                                    |            "contentMediaType": "application/gml+xml"  |
    |    }                                      |          },                                           |
    |                                           |          {                                            |
    |                                           |            "type": "string",                          |
    |                                           |            "contentMediaType": "application/kml+xml"  |
    |                                           |          }                                            |
    |                                           |        ]                                              |
    |                                           |      }                                                |
    |                                           |    }                                                  |
    +-------------------------------------------+-------------------------------------------------------+

Metadata
-----------------------

Metadata fields are transferred between :term:`WPS` (from :term:`Process` description) and :term:`CWL`
(from :term:`Application Package`) when match is possible. Per :term:`I/O` definition that support certain
metadata fields (notably descriptions), are also transferred.

.. note::
    Because the ``schema`` (:term:`OAS`) definitions are embedded within :term:`WPS` I/O definitions, corresponding
    metadata fields **ARE NOT** transferred. This choice is made in order to keep ``schema`` succinct such that they
    only describe the structure of the expected data type and format, and to avoid too much metadata duplication for
    each :term:`I/O` in the resulting :term:`Process` description.

Below is a list of compatible elements.

+-----------------------------------------+----------------------------------------------------------+
| Parameters in :term:`WPS` Context       | Parameters in :term:`CWL` Context                        |
+=========================================+==========================================================+
| ``keywords``                            | ``s:keywords`` (expecting ``s`` in ``$namespace``        |
|                                         | referring to http://schema.org [#cwl_schemaorg]_)        |
+-----------------------------------------+----------------------------------------------------------+
| ``metadata``                            | ``$schemas``/``$namespace``                              |
| (using ``title`` and ``href`` fields)   | (using namespace name and HTTP references)               |
+-----------------------------------------+----------------------------------------------------------+
| ``title``                               | ``label``                                                |
+-----------------------------------------+----------------------------------------------------------+
| ``abstract``/``description``            | ``doc``                                                  |
+-----------------------------------------+----------------------------------------------------------+

.. rubric:: Footnotes

.. [#cwl_schemaorg]
    See example: `cwl-metadata`_

.. |br| raw:: html

    <br>

.. |na| replace:: *n/a*

.. |nbsp| unicode:: 0xA0
   :trim:

.. |<=>| unicode:: 0x21D4

.. _app_pkg_secret_parameters:

Using Secret Parameters
=======================

Under some circumstances, input parameters to a :term:`Job` must be hidden, whether to avoid leaking credentials
required by the underlying application, or for using sensible information that should not be easily accessible.
In such cases, typical :term:`CWL` ``string`` inputs should not be directly employed.

There are 2 strategies available to employ *secrets* when working with `Weaver`:

1. Using the :term:`Vault` feature
2. Using ``cwltool:Secrets`` hint

.. _app_pkg_secret_vault:

Secrets using the File Vault
----------------------------

Using :ref:`file_vault_inputs` essentially consists of wrapping any sensible data within an input of type ``File``,
which will be :ref:`Uploaded to the Vault <vault_upload>` for :term:`Job` execution. Once the file is accessed and
staged by the relevant :term:`Job`, its contents are automatically deleted from the :term:`Vault`. This offers a
secured single access endpoint only available by the client that uploaded the file, for a short period of time,
which decides for which :term:`Process` it should be summited to with the corresponding authentication token and
:term:`Vault` ID. Since the sensible data is contained within a file, its contents are only available by the targeted
:term:`Job` for the selected :term:`Process`, while logs will only display a temporary path.

However, the :term:`Vault` approach as potential drawbacks.

1. It is a feature specific to `Weaver`, which will not be available an easily interoperable when involving
   other :term:`OGC API - Processes` servers.

2. It forces the :term:`CWL` to be implemented using a ``File`` input. While this is not necessarily an issue
   in some cases, it becomes the responsibility of the :term:`Application Package` developer to figure out how
   to propagate the contained data to the relevant piece of code if a plain string is needed. To do so, the
   developer must also avoid outputting any information to ``stdout``. Otherwise, the data would be captured
   in :term:`Job` logs and defeating the purpose of using the :term:`Vault`.

.. note::
    For more details about the :term:`Vault`, refer to sections :ref:`file_vault_inputs`, :ref:`vault_upload`,
    and the corresponding capabilities in :term:`cli_example_upload`.

.. _app_pkg_secret_cwltool:

Secrets using the CWL Hints
---------------------------

An alternative approach is to use the :term:`CWL` hints as follows:

.. code-block:: json
    :caption: CWL Secrets Definition

    {
        "cwlVersion": "v1.2",
        "inputs": {
            "<input-name>": {
                "type": "string"
            }
        },
        "hints": {
            "cwltool:Secrets": {
                "secrets": [
                    "<input-name>"
                ]
            }
        },
        "$namespaces": {
            "cwltool": "http://commonwl.org/cwltool#"
        }
    }

Using this definition either in a ``class: CommandLineTool`` (see :ref:`app_pkg_cmd`)
or a ``class: Workflow`` (see :ref:`app_pkg_workflow`) will instruct the underlying :term:`Job` execution
to replace all specified inputs (i.e.: ``<input-name>`` in the above example) to be masked in commands and logs.
Looking at :term:`Job` logs, all sensible inputs will be replaced by a representation similar to ``(secret-<UUID>)``
The original data identified by this masked definition will be substituted back only at the last possible moment,
when the underlying operation accessed it to perform its processing.

A few notable considerations must be taken when using the ``cwltool:Secrets`` definition.

1. It is limited to ``string`` inputs. Any other literal data type and intermediate conversions would need
   to be handled explicitly by the :term:`Application Package` maintainer.

2. The secrets definition can only be provided in the ``hints`` section of the :term:`CWL` document, meaning
   that any remote server supporting :term:`CWL` are not required to support this feature.
   If the :term:`Application Package` is expected to be deployed remotely, it is up to the client to
   determine whether the remote server will perform the necessary actions to mask sensible data.
   If unsupported, secrets could become visible in the :term:`Job` logs as if they were submitted using
   typical ``string`` inputs.

3. The feature does not avoid any misuse of underlying commands that could expose the sensible data due
   to manipulation errors or the use of operations that are redirected to ``stdout``. For example, if the
   shell ``echo`` command is used within the :term:`CWL` with an input listed in ``cwltool:Secrets``, its
   value will still be displayed in plain text in the :term:`Job` logs.
