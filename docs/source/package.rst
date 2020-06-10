.. _package:
.. _application-package:
.. include:: references.rst

*************************
Application Package
*************************

The `Application Package` defines the internal script definition and configuration that will be executed by a process.
This package is based on |CWL|_ (`CWL`). Using the extensive |cwl-spec|_ as backbone
for internal execution of the process allows it to run multiple type of applications, whether they are referenced to by
`docker image`, `bash script` or more.

.. note::
    The large community and use cases covered by `CWL` makes it extremely versatile. If you encounter any issue running
    your `Application Package` in `Weaver` (such as file permissions for example), chances are that there exists a
    workaround somewhere in the |cwl-spec|_. Most typical problems are usually handled by some flag or argument in the
    `CWL` definition, so this reference should be explored first. Please also refer to `Common Use-Cases and Solutions`_
    section and existing `Weaver` `issues`_. Ultimately if no solution can be found, open an new issue about your specific
    problem.


All processes deployed locally into `Weaver` using a `CWL` package definition will have their full package definition
available with |pkg-req|_ request.

.. note::

    |pkg-req|_ is `Weaver`-specific implementation, and therefore, is not necessarily available on other `ADES`/`EMS`
    implementation as this feature is not part of |ogc-proc-api|_ specification.


Typical CWL Package Definition
===========================================

CWL CommandLineTool
------------------------

Following CWL package definition represents the :py:mod:`weaver.processes.builtin.jsonarray2netcdf` process.

.. literalinclude:: ../../weaver/processes/builtin/jsonarray2netcdf.cwl
    :language: YAML
    :linenos:

The first main components is the ``class: CommandLineTool`` that tells `Weaver` it will be a *base* process
(contrarily to `CWL Workflow`_ presented later).

The other important sections are ``inputs`` and ``outputs``. These define which parameters will be expected and
produced by the described application. `Weaver` supports most formats and types as specified by |cwl-spec|_.
See `Inputs / Outputs Type`_ for more details.


CWL Workflow
------------------------

`Weaver` also supports `CWL` ``class: Workflow``. When an `Application Package` is defined this way, the process
deployment operation will attempt to resolve each ``step`` as another process. The reference to the `CWL` definition
can be placed in any location supported as for the case of atomic processes
(see details about :ref:`supported package locations <WPS-REST>`).

The following `CWL` definition demonstrates an example ``Workflow`` process that would resolve each ``step`` with
local processes of match IDs.

.. literalinclude:: ../../tests/functional/application-packages/workflow_subset_ice_days.cwl
    :language: JSON
    :linenos:

For instance, the ``jsonarray2netcdf`` (:ref:`Builtin`) middle step in this example corresponds to the
`CWL CommandLineTool`_ process presented in previous section. Other processes referenced in this ``Workflow`` can be
found in |test-res|_. Steps are solved using the variations presented below.


.. |test-res| replace:: Weaver Test Resources
.. _test-res: https://github.com/crim-ca/weaver/tree/master/tests/functional/application-packages

Step Reference
~~~~~~~~~~~~~~~~~

In order to resolve referenced processes as steps, `Weaver` supports 3 formats.

1. Process ID explicitly given
   (e.g.: ``jsonarray2netcdf`` resolved to :py:mod:`weaver.processes.builtin.jsonarray2netcdf`).
   Any *visible* process from |getcap-req|_ response should be resolved this way.
2. Full URL to the process description endpoint, provided that it also offers a |pkg-req|_ endpoint (`Weaver`-specific).
3. Full URL to the explicit `CWL` file (usually corresponding to (2) or the ``href`` provided in deployment body).

When an URL to the `CWL` process "file" is provided with an extension, it must be one of the supported values defined
in :py:data:`weaver.processes.wps_package.PACKAGE_EXTENSIONS`. Otherwise, `Weaver` will refuse it as it cannot figure
out how to parse it.

Because `Weaver` and the underlying `CWL` executor need to resolve all steps in order to validate their input and
output definitions correspond (id, format, type, etc.) in order to chain them, all intermediate processes **MUST**
be available. This means that you cannot :ref:`Deploy` nor :ref:`Execute` a ``Workflow``-flavored `Application Package`
until all referenced steps have themselves been deployed and made visible.

.. warning::

    Because `Weaver` needs to convert given `CWL` documents into equivalent `WPS` process definition, embedded `CWL`
    processes within a ``Workflow`` step are not supported currently. This is a known limitation of the implementation,
    but not much can be done against it without major modifications to the code base.
    See also issue `#56 <https://github.com/crim-ca/weaver/issues/56>`_.

.. seealso::

    - :py:func:`weaver.processes.wps_package.get_package_workflow_steps`
    - :ref:`Deploy` request details.


Correspondance between CWL and WPS fields
===========================================

Because `CWL` definition and `WPS` process description inherently provide "duplicate" information, many fields can be
mapped between one another. In order to handle any provided metadata in the various supported locations by both
specifications, as well as to extend details of deployed processes, each `Application Package` get its details merged
with complementary `WPS` description.

In some cases, complementary details are only documentation-related, but some information directly affect the format or
execution behaviour of some parameters. A common example is the ``maxOccurs`` field provided by `WPS` that does not
have an exactly corresponding specification in `CWL` (any-sized array). On the other hand, `CWL` also provides data
preparation steps such as initial staging (i.e.: ``InitialWorkDirRequirement``) that doesn't have an equivalent under
the `WPS` process description. For this reason, complementary details are merged and reflected on both sides
(as applicable), when non-ambiguous resolution is possible.

In case of conflicting metadata, the `CWL` specification will most of the time prevail over the `WPS` metadata fields
simply because it is expected that a strict `CWL` specification is provided upon deployment. The only exceptions to this
situation are when `WPS` specification help resolve some ambiguity or when `WPS` reinforce the parametrisation of some
elements, such as with ``maxOccurs`` field.

.. note::

    Metadata merge operation between `CWL` and `WPS` is accomplished on *per-mapped-field* basis. In other words, more
    explicit details such as ``maxOccurs`` could be obtained from `WPS` and **simultaneously** the same input's
    ``format`` could be obtained from the `CWL` side. Merge occurs bidirectionally for corresponding information.

The merging strategy of process specifications also implies that some details can be omitted from one context if they
can be inferred from corresponding elements in the other. For example, the `CWL` and `WPS` context both define
``keywords`` (with minor naming variation) as a list of strings. Specifying this metadata in both locations is redundant
and only makes the process description longer. Therefore, the user is allowed to provide only one of the two and
`Weaver` will take care to propagate the information to the lacking location.

In order to help understand the resolution methodology between the contexts, following sub-section will cover supported
mapping between the two specifications, and more specifically, how each field impacts the mapped equivalent metadata.

.. warning::

    Merging of corresponding fields between `CWL` and `WPS` is a `Weaver`-specific implementation. The same behaviour
    is not necessarily supported by other implementations. For this reason, any converted information between the two
    contexts will be transferred to the other context if missing in order for both specification to reflect the similar
    details as closely as possible, wherever context the metadata originated from.


Inputs / Outputs ID
-----------------------

Inputs and outputs (I/O) ``id`` from the `CWL` context will be respectively matched against corresponding ``id`` or
``identifier`` field from the I/O of `WPS` context. In the `CWL` definition, all of the allowed I/O structures are
supported, whether they are specified using an array list with explicit definitions, using "shortcut" variant, or using
key-value pairs (see `CWL Mapping <cwl-io-map>`_ for more details). Regardless of array or mapping format, `CWL`
requires that all I/O have unique ``id``. On the `WPS` side, a list of I/O is *always* expected. This is because
`WPS` I/O with multiple values (array in `CWL`) are specified by repeating the ``id`` with each value instead of
defining the value as a list of those values during :ref:`Execute` request (see also :ref:`Multiple Inputs`).

To summarize, the following `CWL` and `WPS` I/O definitions are all equivalent and will result into the same process
definition after deployment. For simplification purpose, below examples omit all but mandatory fields to produce the
same result and only list the I/O portion of the full deployment body. Other fields are discussed afterward.

.. code-block::
    :title: CWL I/O as array
    :language: JSON
    :linenos:

    {
      "inputs": [
        {
          "id": "single-str",
          "type": "string"
        },
        {
          "id": "multi-file",
          "type": "File[]"
        }
      ],
      "outputs": [
        {
          "id": "process-output-1",
          "type": "File"
        },
        {
          "id": "process-output-2",
          "type": "File"
        }
      ]
    }

.. code-block::
    :title: CWL I/O as mapping
    :language: JSON
    :linenos:

    {
      "inputs": {
        "single-str": {
          "type": "string"
        },
        "multi-file": {
          "type": "File[]"
        }
      },
      "outputs": {
        "process-output-1": {
          "type": "File"
        },
        "process-output-2": {
          "type": "File"
        }
      }
    }

.. code-block::
    :title: WPS I/O repeating
    :language: JSON
    :linenos:

    {
      "inputs": [
        {
          "id": "single-str"
        },
        {
          "id": "multi-file",
          "formats": []
        }
      ],
      "outputs": [
        {
          "id": "process-output-1",
          "formats": []
        },
        {
          "id": "process-output-2",
          "formats": []
        }
      ]
    }


Inputs / Outputs Type
-----------------------

In the `CWL` context, the ``type`` field indicates the type of I/O. Available types are presented in the
`CWLType Symbols <cwl-io-type>`_ portion of the specification.

.. warning::

    `Weaver` has two unsupported `CWL` ``type``, namely ``Any`` and ``Directory``. This limitation is intentional
    as `WPS` does not offer equivalents. Furthermore, both of these types make the process description too ambiguous.
    For instance, most processes expect remote file references, and providing a ``Directory`` doesn't indicate an
    explicit reference to which files to retrieve during stage-in operation.


In the `WPS` context, three data types exist, namely, ``Literal``, ``BoundingBox`` and ``Complex`` data.


.. todo:: CWL Lit. <-> WPS Literal
.. todo:: CWL File <-> WPS Complex


As presented in the example of the previous section, I/O in the `WPS` context does not require an explicit indication
of the type from one of ``Literal``, ``BoundingBox`` and ``Complex`` data. Instead, `WPS` type is inferred using the
matching schema of the I/O. For ``Complex`` I/O (i.e. a file reference), the ``format`` field is needed to distinguish
it from a plain ``string``. Otherwise,

.. note::
    As of the current version of `Weaver`, `WPS` data type ``BoundingBox`` is not supported. This feature is reflected
    by issue `#51 <https://github.com/crim-ca/weaver/issues/51>`_. It is possible to use a ``Literal`` data of
    type ``string`` in the meantime.


File Format
-----------------------

.. todo:: demo docs

.. todo:: WPS 'formats' required to infer 'ComplexData' == CWL File

Allowed Values
-----------------------


.. todo:: cwl enum vs allowed/supported WPS


Multiple Values
-----------------------

.. todo:: minOccurs/maxOccurs + array + WPS repeats IDs vs CWL as list

Metadata
-----------------------

.. todo:: (s:)keywords field, doc/label vs abstract/title per-I/O and overall process, etc?

Example: `cwl-metadata`_


Common Use-Cases and Solutions
===========================================

This section present some commonly encountered use-cases and basic solutions.


How to tell the Docker image reference
----------------------------------------------

In most situations, the ``CommonLineTool`` process will need to run a docker image. Doing so is as simple as adding the
``DockerRequirement`` (`reference <cwl-docker-req>`_) as follows to the `Application Package` definition:

.. code-block:: json

    {
      "cwlVersion": "v1.0",
      "requirements": {
        "DockerRequirement": {
          "dockerPull": "<docker-url>"
        }
      },
      "inputs": ["<...>"],
      "outputs": ["<...>"],
    }


.. note::
    The docker image reference must be publicly accessible to allow `CWL` to pull it. Alternatively, a private
    docker reference can be used if the image is locally available. The process will fail to execute if it cannot
    resolve the reference.


Permission error on input files
----------------------------------------------

Some processes expect their inputs to be writable (e.g.: ZIP files). When running an *Application Package* based on a
`docker image`, `Weaver` mounts the input files as `volumes` in read-only mode for security reasons. This causes these
processes to immediately fail as the running user cannot override nor write temporary files in the same directory
(where the volume was mounted to), as it is marked with read permissions.

To resolve this issue, the application developer should add the ``InitialWorkDirRequirement``
(|cwl-wd-ref|_, |cwl-wd-ex|_) to his CWL package definition. This tells CWL to stage the files into the docker image
into the running directory where the user will be allowed to generate outputs, and therefore, also allow edition of the
inputs or generation of temporary files as when unpacking a compressed file.

.. |cwl-wd-ref| replace:: reference
.. _cwl-wd-ref: `cwl-workdir-req`_
.. |cwl-wd-ex| replace:: example
.. _cwl-wd-ex: `cwl-workdir-ex`_

As example, the CWL definition could be similar to the following:

.. code-block:: json

    {
      "cwlVersion": "v1.0",
      "class": "CommandLineTool",
      "requirements": {
        "DockerRequirement": {
          "dockerPull": "<docker-url>"
        },
        "InitialWorkDirRequirement": {
          "listing": [{
             "entry": "$(inputs.input_file)",
             "writable": true
            }
          ]
        }
      },
      "arguments": ["$(runtime.outdir)"],
      "inputs": {
        "input_file": {
        "type": "File"
      }
    }

Note that ``$(inputs.input_file)`` is tells which input to resolve for staging in ``InitialWorkDirRequirement`` using
the ``"writable": True`` parameter. This file will be mounted with write permissions into working runtime directory.


Links
-----------------------

- |cwl-guide|_
- |cwl-cmdtool|_
- |cwl-workflow|_

