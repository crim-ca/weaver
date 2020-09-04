.. _faq:
.. include:: references.rst

*************************
FAQ
*************************

This section present some commonly encountered use-cases and basic solutions regarding `ADES`/`EMS` operation or
more specifically related to `CWL` specification.

.. contents::
    :local:
    :depth: 2


How to specify the Docker image reference?
==================================================

In most situations, the ``CommonLineTool`` process will need to run a docker image. Doing so is as simple as adding the
``DockerRequirement`` (|cwl_docker-req-ref|_) as follows to the `Application Package` definition:

.. |cwl_docker-req-ref| replace:: reference
.. _cwl_docker-req-ref: `cwl-docker-req`_

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

The `Application Package` can be provided during process deployment. Please refer to below references for more details.

.. seealso::

    - :ref:`supported package locations <WPS-REST>`
    - :ref:`Deploy` request


Fixing permission error on input files
==========================================

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

Note that ``$(inputs.input_file)`` within ``InitialWorkDirRequirement`` tells which input to resolve for staging using
the ``"writable": True`` parameter. All files listed there will be mounted with write permissions into working runtime
directory of the executed docker container.


Problem connecting workflow steps together
==================================================


.. seealso::

    - :ref:`CWL Workflow`
    - :ref:`Output File Format`


Where can I find references to CWL specification and examples?
================================================================

There exist multiple sources, but official ones provided below have a create amount of examples and are being
continuously improved by the developers (including being updated according to changes).

- |cwl-guide|_
- |cwl-cmdtool|_
- |cwl-workflow|_

