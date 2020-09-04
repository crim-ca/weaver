.. _appendix:
.. include:: references.rst

************
Glossary
************

.. glossary::
    :sorted:

    ADES
        | |ades|
        | See :ref:`processes` section for details, as well as :term:`EMS` for alternative operation mode.

    Application Package
        General term that refers to *"what and how the :term:`Process` will execute"*. Application Packages provide
        the core details about the execution methodology of the underlying operation the :term:`Process` provides, and
        are therefore always contained within a :term:`Process` definition. This is more specifically represented
        by a :term:`CWL` specification in the case of `Weaver` implementation, but could technically be defined by
        another similar approach. See :ref:`Application Package` section for all relevant details.

    AWS
        Amazon Web Services

    CWL
        | |cwl|_
        | Representation of the internal :term:`Application Package` of the :term:`Process` to provide execution
          methodology of the referenced :term:`Docker` image or other supported definitions. See
          :ref:`application-package` section for further details.

    Docker
        Image that packages all required dependencies of an application or software in order to correctly execute it
        in a containerized and isolated virtualized environment.

    EDAM
        Ontology that regroups multiple definitions, amongst which `Weaver` looks up some of its known and supported
        :term:`MIME-types` (|edam-link|_) when resolving file formats. It is used as extension to :term:`IANA` media
        types by providing additional formats that are more specifics to some data domains.

    EMS
        | |ems|
        | See :ref:`processes` section for details. Alternative mode is :term:`ADES`, which can be selected as defined
          by the appropriate :ref:`Configuration` parameter.

    ESGF
        |esgf|_

    ESGF-CWT
        |esgf-cwt|_

    HREF
        | Hyperlink Reference
        | Often shortened to simply `reference`. Represents either a locally or remotely accessible item, such as a
          file or a :term:`Process` depending on context, that uses explicit ``<protocol>://<host/path>``
          representation to define its location. See also :ref:`File Reference Types` for typical examples.

    I/O
        Inputs and/or Outputs of CWL and/or WPS depending on context.

    IANA
        Ontology that regroups multiple definitions, amongst which `Weaver` looks up most of its known and supported
        :term:`MIME-types` (|iana-link|_) when resolving file formats.

    JSON
        | JavaScript Object Notation
        | Default data representation of all objects contained in the application or for their creation.

    Job
        Definition of a :term:`Process` execution state with applicable operation metadata.

    MIME-types
        | Multipurpose Internet Mail Extensions
        | Format representation of the referenced element, often represented by :term:`IANA` or :term:`EDAM` ontologies.

    OGC
        |ogc|_

    OGC API - Processes
        The new API that defines JSON REST-binding representation of :term:`WPS` :term:`Process` collection.

    OpenSearch
        Protocol of lookup and retrieval of remotely stored files.
        Please refer to :ref:`OpenSearch Data Source` for details.

    Process
        Entity that describes the required inputs, produced outputs, and any applicable metadata for the execution of
        the defined script, calculation, or operation.

    S3
        Simple Storage Service (:term:`AWS` S3), bucket file storage.

    WKT
        Well-Known Text geometry representation.

    WPS
        | Web Processing Service.
        | From a formal standpoint, this is the previous :term:`OGC` standard iteration that was employed prior to
          :term:`OGC API - Processes` to represent a server that host one or more :term:`Process` for execution.
          When compared against :term:`CWL` context or generally across `Weaver` documentation and code, this term
          refers to attributes that are specific to typical :term:`Process` description, in contrast to specialized
          attributes introduced by other concepts, such as for example :term:`CWL`-specific implementation details.

    XML
        | Extensible Markup Language
        | Alternative representation of some data object provided by the application. Requires appropriate ``Accept``
          header to return this format. See :ref:`OpenAPI Specification` for details.

************
Useful Links
************

- |cwl-home|_
- |cwl-spec|_
- |cwl-guide|_
- |cwl-cmdtool|_
- |cwl-workflow|_
- |esgf-cwt|_
- |edam-link|_
- |iana-link|_
- |oas|_
- |ogc|_ (:term:`OGC`)
- |ogc-proc-api|_
- |weaver-issues|_
