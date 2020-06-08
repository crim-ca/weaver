.. package:
.. application-package:
.. include:: references.rst

*************************
Application Package
*************************

The `Application Package` defines the internal script definition and configuration that will be executed by a process.
This package is based on |CWL|_ (`CWL`) |cwl-spec|_. Using the extensive specification of `CWL` as backbone for
internal execution of the process allows it to run multiple type of applications, whether they are referenced to by
`docker image`, `bash script` or more.

.. note::
    The large community and use cases covered by `CWL` makes it extremely versatile. If you encounter any issue running
    your `Application Package` in `Weaver` (such as file permissions for example), chances are that there exists a
    workaround somewhere in the |cwl-spec|_. Most typical problems are usually handled by some flag or argument in the
    `CWL` definition, so this reference should be explored first. Please also refer to `Common Problems and Solutions`_
    section and existing `Weaver Issues`_. Ultimately if no solution can be found, open an new issue about your specific
    problem.

.. |pkg-req| replace:: ``GET /processes/{id}/package``
.. _pkg-req: https://pavics-weaver.readthedocs.io/en/setup-docs/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget

Typical CWL Package Definition
===========================================

.. todo:: CommandLineTool

Correspondance between CWL and WPS fields
===========================================

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

