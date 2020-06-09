.. _package:
.. _application-package:
.. include:: references.rst

*************************
Application Package
*************************

The `Application Package` defines the internal script definition and configuration that will be executed by a process.
This package is based on |CWL|_ (`CWL`) |cwl-spec|_. Using the extensive specification of `CWL` as backbone
for internal execution of the process allows it to run multiple type of applications, whether they are referenced to by
`docker image`, `bash script` or more.

.. note::
    The large community and use cases covered by `CWL` makes it extremely versatile. If you encounter any issue running
    your `Application Package` in `Weaver` (such as file permissions for example), chances are that there exists a
    workaround somewhere in the |cwl-spec|_. Most typical problems are usually handled by some flag or argument in the
    `CWL` definition, so this reference should be explored first. Please also refer to `Common Problems and Solutions`_
    section and existing `Weaver Issues`_. Ultimately if no solution can be found, open an new issue about your specific
    problem.


All processes deployed locally into `Weaver` using a `CWL` package definition will have their full package definition
available with ``GET /processes/{id}/package`` |pkg-req|_ request.

.. |pkg-req| replace:: Package
.. _pkg-req: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget

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



CWL Workflow
------------------------

`Weaver` also supports `CWL` ``class: Workflow``. When an `Application Package` is defined this way, the process
deployment operation will attempt to resolve each ``step`` as another process. The reference to the `CWL` definition
can be placed in any location supported as for the case of atomic processes
(see details about `supported package locations <wps-rest>`_).

The following `CWL` definition demonstrates an example ``Workflow`` process that would resolve each ``step`` with
local processes of match IDs.

.. literalinclude:: ../../tests/functional/application-packages/workflow_subset_ice_days.cwl
    :language: JSON
    :linenos:

For instance, the ``jsonarray2netcdf`` (`Builtin`_) middle step in this example corresponds to the
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
be available. This means that you cannot `Deploy`_ nor `Execute`_ a ``Workflow``-flavored `Application Package` until
all referenced steps have themselves been deployed and made visible.

.. warning::

    Because `Weaver` needs to convert given `CWL` documents into equivalent `WPS` process definition, embedded `CWL`
    processes within a ``Workflow`` step are not supported currently. This is a known limitation of the implementation,
    but not much can be done against it without major modifications to the code base.
    See also issue `#56 <https://github.com/crim-ca/weaver/issues/56>`_.

.. seealso::

    - :py:func:`weaver.processes.wps_package.get_package_workflow_steps`
    - `Deploy`_ request details.


Correspondance between CWL and WPS fields
===========================================

Because `CWL` definition and `WPS` process description inherently provide "duplicate" information, many fields can be
mapped between one another. In order to handle any provided metadata in the various supported location by both
specifications, as well as to extend details of deployed processes, each `Application Package` get its details merged
with complementary `WPS` description.

In some cases, complementary details are only documentation-related, but some information directly affect the format or
execution behaviour of some parameters. A common example is the ``maxOccurs`` field provided by `WPS` that does not
have a corresponding specification in `CWL` (any-sized array). On the other hand, `CWL` also provides data preparation
steps such as initial staging (i.e.: ``InitialWorkDirRequirement``) that doesn't have an equivalent under the `WPS`
process description. For this reason, complementary details are merged and reflected on both sides (as applicable),
when non-ambiguous resolution is possible.

In case of conflicting metadata, the `CWL` specification will most of the time prevail over the `WPS` metadata fields
simply because it is expected that a strict `CWL` specification is provided upon deployment. The only exceptions to this
situation are when `WPS` specification help resolve some ambiguity or when `WPS` reinforce the parametrisation of some
elements, such as with ``maxOccurs`` field.

.. note::

    Metadata merge operation between `CWL` and `WPS` is accomplished on *per-mapped-field* basis. In other words, more
    explicit details such as ``abstract`` could be obtained from `WPS` *while* an input file format could be obtained
    from the `CWL` side. Merge occurs bidirectionally for corresponding information.

In order to help understand the resolution methodology, following sub-section cover the supported mapping between the
two specifications, and more specifically, how each field impacts the mapped equivalent metadata.

Input / Outputs
-----------------------

.. todo:: mapping with 'id'
.. todo:: CWL Lit. <-> WPS Literal
.. todo:: CWL File <-> WPS Complex

File Format
-----------------------

.. todo:: demo docs

Allowed Values
-----------------------


.. todo:: cwl enum vs allowed/supported WPS


Multiple Values
-----------------------

.. todo:: minOccurs/maxOccurs + array + WPS repeats IDs vs CWL as list

Common Problems and Solutions
===========================================

This section present some commonly encountered use-cases and basic solutions.

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
.. _cwl-wd-ex: `cwl-workdir-req`_

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

