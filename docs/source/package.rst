.. _package:
.. _application-package:
.. include:: references.rst

*************************
Application Package
*************************

.. contents::
    :local:
    :depth: 2

The `Application Package` defines the internal script definition and configuration that will be executed by a process.
This package is based on |CWL|_ (`CWL`). Using the extensive |cwl-spec|_ as backbone
for internal execution of the process allows it to run multiple type of applications, whether they are referenced to by
`docker image`, `bash script` or more.

.. note::
    The large community and use cases covered by `CWL` makes it extremely versatile. If you encounter any issue running
    your `Application Package` in `Weaver` (such as file permissions for example), chances are that there exists a
    workaround somewhere in the |cwl-spec|_. Most typical problems are usually handled by some flag or argument in the
    `CWL` definition, so this reference should be explored first. Please also refer to :ref:`FAQ` section as well as
    existing |Weaver issues|_. Ultimately if no solution can be found, open an new issue about your specific problem.


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
See `Inputs/Outputs Type`_ for more details.


CWL Workflow
------------------------

`Weaver` also supports :term:`CWL` ``class: Workflow``. When an :term:`Application Package` is defined this way, the
|process-deploy-op|_ will attempt to resolve each ``step`` as another process. The reference to the :term:`CWL`
definition can be placed in any location supported as for the case of atomic processes
(see details about :ref:`supported package locations <WPS-REST>`).

.. |process-deploy-op| replace:: Process deployment operation
.. _process-deploy-op: :ref:`Deploy`

The following :term:`CWL` definition demonstrates an example ``Workflow`` process that would resolve each ``step`` with
local processes of match IDs.

.. literalinclude:: ../../tests/functional/application-packages/workflow_subset_ice_days.cwl
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
be available. This means that you cannot :ref:`Deploy` nor :ref:`Execute` a ``Workflow``-flavored
:term:`Application Package` until all referenced steps have themselves been deployed and made visible.

.. warning::

    Because `Weaver` needs to convert given :term:`CWL` documents into equivalent :term:`WPS` process definition,
    embedded :term:`CWL` processes within a ``Workflow`` step are not supported currently. This is a known limitation
    of the implementation, but not much can be done against it without major modifications to the code base.
    See also issue `#56 <https://github.com/crim-ca/weaver/issues/56>`_.

.. seealso::

    - :py:func:`weaver.processes.wps_package.get_package_workflow_steps`
    - :ref:`Deploy` request details.

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


Correspondance between CWL and WPS fields
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
variant, or using key-value pairs (see |cwl-io-map|_ for more details). Regardless of array or mapping format,
:term:`CWL` requires that all I/O have unique ``id``. On the :term:`WPS` side, a list of I/O is *always* expected.
This is because :term:`WPS` I/O with multiple values (array in :term:`CWL`) are specified by repeating the ``id`` with
each value instead of defining the value as a list of those values during :ref:`Execute` request (see also
:ref:`Multiple Inputs`).

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
distinguish it from a plain string. More details are available in `Inputs/Outputs Type`_ below about this requirement.

Finally, it is to be noted that above :term:`CWL` and :term:`WPS` definitions can be specified in the :ref:`Deploy`
request body with any of the following variations:

1. Both are simultaneously fully specified (valid although extremely verbose).
2. Both partially specified as long as sufficient complementary information is provided.
3. Only :term:`CWL` :term:`I/O` is fully provided
   (with empty or even unspecified ``inputs`` or ``outputs`` section from :term:`WPS`).

.. warning::
    `Weaver` assumes that its main purpose is to eventually execute an :term:`Application Package` and will therefore
    prioritize specification in :term:`CWL` over :term:`WPS`. Because of this, any unmatched ``id`` from the :term:`WPS`
    context against provided :term:`CWL` ``id``\s of the same I/O section **will be dropped**, as they ultimately would
    have no purpose during :term:`CWL` execution.

    This does not apply in the case of referenced :ref:`WPS-1/2` processes since no :term:`CWL` is available in the
    first place.


Inputs/Outputs Type
-----------------------

In the :term:`CWL` context, the ``type`` field indicates the type of I/O. Available types are presented in the
|cwl-io-type|_ portion of the specification.

.. warning::

    `Weaver` has two unsupported :term:`CWL` ``type``, namely ``Any`` and ``Directory``. This limitation is
    **intentional** as :term:`WPS` does not offer equivalents. Furthermore, both of these types make the process
    description too ambiguous. For instance, most processes expect remote file references, and providing a
    ``Directory`` doesn't indicate an explicit reference to which files to retrieve during stage-in operation of
    a job execution.


In the :term:`WPS` context, three data types exist, namely ``Literal``, ``BoundingBox`` and ``Complex`` data.

As presented in the example of the previous section, :term:`I/O` in the :term:`WPS` context does not require an explicit
indication of the type from one of ``Literal``, ``BoundingBox`` and ``Complex`` data. Instead, :term:`WPS` type is
inferred using the matched API schema of the I/O. For instance, ``Complex`` I/O (i.e.: file reference) requires the
``formats`` field to distinguish it from a plain ``string``. Therefore, specifying either ``format`` in :term:`CWL`
or ``formats`` in :term:`WPS` immediately provides all needed information for `Weaver` to understand that this I/O is
expected to be a file reference. A ``crs`` field would otherwise indicate a ``BoundingBox`` I/O
(see :ref:`note <bbox-note>`). If none of the two previous schemas are matched, the I/O type resolution falls back
to ``Literal`` data of ``string`` type. To employ another primitive data type such as ``Integer``, an explicit
indication needs to be provided as follows.

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
It is therefore *recommended* to take advantage of `Weaver`'s merging strategy in this case by providing only the
details through the :term:`CWL` definition and have the corresponding :term:`WPS` I/O type automatically deduced by
the generated process. If desired, ``literalDataDomains`` can still be explicitly provided as above to ensure that
it gets parsed as intended type.

.. _bbox-note:
.. note::
    As of the current version of `Weaver`, :term:`WPS` data type ``BoundingBox`` is not supported. The schema definition
    exists in :term:`WPS` context but is not handled by any :term:`CWL` type conversion yet. This feature is reflected
    by issue `#51 <https://github.com/crim-ca/weaver/issues/51>`_. It is possible to use a ``Literal`` data of
    type ``string`` corresponding to :term:`WKT` [#]_, [#]_ in the meantime.

.. [#] `WKT Examples <wkt-example>`_
.. [#] `WKT Formats <wkt-format>`_

File Format
-----------------------

An input or output resolved as :term:`CWL` ``File`` type, equivalent to a :term:`WPS` ``ComplexData``, supports
``format`` specification. Every ``mimeType`` field nested under ``formats`` entries of the :term:`WPS` definition
will be mapped against corresponding *namespaced* ``format`` of :term:`CWL`.

For example, the following input definitions are equivalent in both contexts.

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
the underlying application. The two :term:`MIME-types` selected for this example are chosen specifically to demonstrate
how :term:`CWL` formats must be specified. More precisely, :term:`CWL` requires a real schema definition referencing to
an existing ontology to validate formats, specified through the ``$namespaces`` section. Each format entry is then
defined as a mapping of the appropriate namespace to the identifier of the ontology. Alternatively, you can also provide
the full URL of the ontology reference in the format string.

Like many other fields, this information can become quite rapidly redundant and difficult to maintain. For this reason,
`Weaver` will automatically fill the missing detail if only one of the two corresponding information between :term:`CWL`
and :term:`WPS` is provided. In other words, an application developer could only specify the :term:`I/O`'s ``formats``
in the :term:`WPS` portion during process deployment, and `Weaver` will take care to update the matching :term:`CWL`
definition without any user intervention. This makes it also easier for the user to specify supported formats since it
is generally easier to remember names of :term:`MIME-types` than full ontology references. `Weaver` has a large set of
commonly employed :term:`MIME-types` that it knows how to convert to corresponding ontologies. Also, `Weaver` will look
for new :term:`MIME-types` it doesn't explicitly know about onto either the :term:`IANA` or the :term:`EDAM` ontologies
in order to attempt automatically resolving them.

When formats are resolved between the two contexts, `Weaver` applies information in a complimentary fashion. This means
for example that if the user provided ``application/x-netcdf`` on the :term:`WPS` side and ``iana:application/json`` on
the :term:`CWL` side, both resulting contexts will have both of those formats combined. `Weaver` will not favour one
location over the other, but will rather merge them if they can be resolved into different and valid entities.

Since ``format`` is a required field for :term:`WPS` ``ComplexData`` definitions (see :ref:`Inputs/Outputs Type`) and
that :term:`MIME-types` are easier to provide in this context, it is *recommended* to provide all of them in the
:term:`WPS` definition.


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
format will have its ``format`` field dropped in the corresponding :term:`CWL` definition. Without any ``format`` on
the :term:`CWL` side, the validation process will ignore this specification and will effectively accept any type of
file. This will not break any execution operation with :term:`CWL`, but it will remove the additional validation layer
of the format (which especially deteriorates process resolution when chaining processes inside a :ref:`CWL Workflow`).

If the :term:`WPS` output only specifies a single MIME-type, then the equivalent format (after being resolved to a valid
ontology) will be preserved on the :term:`CWL` side since the result is ensured to be the unique one provided. For this
reason, processes with specific single-format output are be preferred whenever possible. This also removes ambiguity
in the expected output format, which usually requires a *toggle* input specifying the desired type for processes
providing a multi-format output. It is instead recommended to produce multiple processes with a fixed output format for
each case.


Allowed Values
-----------------------

Allowed values in the context of :term:`WPS` ``LiteralData`` provides a mean for the application developer to restrict
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


Multiple and Optional Values
--------------------------------------------

Inputs that take *multiple* values or references can be specified using ``minOccurs`` and ``maxOccurs`` in :term:`WPS`
context, while they are specified using the ``array`` type in `CWL`. While the same ``minOccurs`` parameter with a
value of zero (``0``) can be employed to indicate an *optional* input, :term:`CWL` requires the type to specify ``null``
or to use the shortcut ``?`` character suffixed to the base type to indicate optional input. Resolution between
:term:`WPS` and :term:`CWL` for the merging strategy implies all corresponding parameter combinations and checks in
this case.

Because :term:`CWL` does not take an explicit amount of maximum occurrences, information in this case are not
necessarily completely interchangeable. In fact, :term:`WPS` is slightly more verbose and easier to define in this case
than :term:`CWL` because all details are contained within the same two parameters. Because of this, it is often
preferable to provide the ``minOccurs`` and ``maxOccurs`` in the :term:`WPS` context, and let `Weaver` infer the
``array`` and/or ``null`` type requirements automatically. Also, because of all implied parameters in this situation to
specify the similar details, it is important to avoid providing contradicting specifications as `Weaver` will have
trouble guessing the intended result when merging specifications. If unambiguous guess can be made, :term:`CWL` will be
employed as deciding definition to resolve erroneous mismatches (as for any other corresponding fields).

.. todo:: update warning according to Weaver issue #25

.. warning::
    Parameters ``minOccurs`` and ``maxOccurs`` are not permitted for outputs in the :term:`WPS` context. Native
    :term:`WPS` therefore does not permit multiple output reference files. This can be worked around using a
    |metalink|_ file, but this use case is not covered by `Weaver` yet as it requires special mapping with :term:`CWL`
    that does support ``array`` type as output (see issue `#25 <https://github.com/crim-ca/weaver/issues/25>`_).

.. note::
    Although :term:`WPS` multi-value inputs are defined as a single entity during deployment, special care must be taken
    to the format in which to specify these values during execution. Please refer to :ref:`Multiple Inputs` section
    of :ref:`Execute` request.

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


.. todo:: minOccurs/maxOccurs + array + WPS repeats IDs vs CWL as list


.. todo:: example multi-value + enum

It can be noted from the examples that ``minOccurs`` and ``maxOccurs`` can be either an ``integer`` or a ``string``
representing one. This is to support backward compatibility of older :term:`WPS` specification that always employed
strings although representing numbers. `Weaver` understands and handles both cases. Also, ``maxOccurs`` can have the
special string value ``"unbounded"``, in which case the input is considered to be allowed an unlimited amount if
entries (although often capped by another implicit machine-level limitation such as memory capacity). In the case of
:term:`CWL`, an ``array`` is always considered as *unbounded*, therefore :term:`WPS` is the only context that can limit
this amount.


Metadata
-----------------------

.. todo:: (s:)keywords field, doc/label vs abstract/title per-I/O and overall process, etc?

Example: `cwl-metadata`_
