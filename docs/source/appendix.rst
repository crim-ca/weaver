.. include:: references.rst
.. _appendix:

************
Glossary
************

.. glossary::
    :sorted:

    ADES
        | |ades|
        | See :ref:`processes` section for details.
          Alternative operation modes are described in :ref:`Configuration Settings`.

    AOI
        | Area of Interest.
        | Corresponds to a region, often provided by :term:`OGC` :term:`WKT` definition, employed for :term:`OpenSearch`
          queries in the context of :term:`EOImage` inputs.

    Application Package
        General term that refers to *"what and how the :term:`Process` will execute"*. Application Packages provide
        the core details about the execution methodology of the underlying operation the :term:`Process` provides, and
        are therefore always contained within a :term:`Process` definition. This is more specifically represented
        by a :term:`CWL` specification in the case of `Weaver` implementation, but could technically be defined by
        another similar approach. See :ref:`Application Package` section for all relevant details.

    AWS
        Amazon Web Services

    CLI
        | Command Line Interface
        | Script that offers interactions through shell commands or Python scripts to execute any described operations.
          Details of the provided `Weaver` commands are described in :ref:`cli` chapter.

    CWL
        | |cwl|_
        | Representation of the internal :term:`Application Package` of the :term:`Process` to provide execution
          methodology of the referenced :term:`Docker` image or other supported definitions.
          A |cwl|_ file can be represented both in :term:`JSON` or :term:`YAML` format, but is often represented
          in :term:`JSON` in the context of `Weaver` for its easier inclusion within HTTP request contents.
          See :ref:`application-package` section for further details.

    Data Source
        Known locations of remote servers where an :term:`ADES` or :term:`EMS`
        (either `Weaver` or other implementation) can accept :term:`Process` deployment,
        or any other server supporting :term:`OGC API - Processes` with pre-deployed :term:`Process`, where
        executions can be dispatched according to the source of the data.

        .. seealso::
            Refer to :ref:`conf_data_sources` and :ref:`data-source` sections for more details.

    Docker
        Containerized and isolated environment platform that allows all required dependencies of an application or
        software to be packaged in a single image in order to correctly execute the virtualized application.

    EDAM
        Ontology that regroups multiple definitions, amongst which `Weaver` looks up some of its known and supported
        :term:`MIME-types` (|edam-link|_) when resolving file formats. It is used as extension to :term:`IANA` media
        types by providing additional formats that are more specifics to some data domains.

    EMS
        | |ems|
        | See :ref:`processes` section for details.
          Alternative operation modes are described in :ref:`Configuration Settings`.

    EOImage
        | Earth Observation Image
        | Input that interprets additional parameters in order to infer specific images applicable with filters
          following search results within a remote catalog.

        .. seealso::
            :ref:`opensearch_data_source` section.

    ESGF
        |esgf|_

    ESGF-CWT
        |esgf-cwt-git|_

    HREF
        | Hyperlink Reference
        | Often shortened to simply `reference`. Represents either a locally or remotely accessible item, such as a
          file or a :term:`Process` depending on context, that uses explicit ``<protocol>://<host/path>``
          representation to define its location. See also :ref:`File Reference Types` for typical examples.

    HYBRID
        | Combination of :term:`ADES` and :term:`EMS` operation modes.
        | See :ref:`processes` section for details.
          Alternative operation modes are described in :ref:`Configuration Settings`.

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

    Provider
        Entity that offers an ensemble of :term:`Process` under it. It is typically a reference to a remote service,
        where any :term:`Process` it provides is fetched dynamically on demand.

    Request Options
        Configuration settings that can be defined for `Weaver` in order to automatically insert additional
        HTTP request parameters, authentication or other any relevant rules when target URLs are matched.
        See also :ref:`conf_request_options`.

    S3
        Simple Storage Service (:term:`AWS` S3), bucket file storage.

    TOI
        | Time of Interest.
        | Corresponds to a date/time interval employed for :term:`OpenSearch` queries in the context
          of :term:`EOImage` inputs.

    Vault
        Secured storage employed to upload files that should be temporarily stored on the `Weaver` server for
        later retrieval using an access token.

        .. seealso::
            :ref:`vault`

    WKT
        Well-Known Text geometry representation.

    Workflow
        A specific variant of :term:`Process` where the execution consists of nested :term:`Process` executions with
        input/output chaining between operations.

        .. seealso::
            Refer to :ref:`proc_workflow`, :ref:`proc_workflow_ops` and :ref:`CWL Workflow` sections for more details.

    WPS
        | Web Processing Service.
        | From a formal standpoint, this is the previous :term:`OGC` standard iteration that was employed prior to
          :term:`OGC API - Processes` to represent a server that host one or more :term:`Process` for execution.
          When compared against :term:`CWL` context or generally across `Weaver` documentation and code, this term
          refers to attributes that are specific to typical :term:`Process` description, in contrast to specialized
          attributes introduced by other concepts, such as for example :term:`CWL`-specific implementation details.

    WPS-REST
        Alias employed to refer to :term:`OGC API - Processes` endpoints for corresponding :term:`WPS` definitions.

    XML
        | Extensible Markup Language
        | Alternative representation of some data object provided by the application. Requires appropriate ``Accept``
          header to return this format. See :ref:`OpenAPI Specification` for details.

    YAML
        | YAML Ain't Markup Language
        | YAML is a human-friendly data serialization language for all programming languages.
          It is employed in `Weaver` as an alternative and equivalent representation of :term:`JSON` format, mostly
          in cases where configuration files are defined to allow the insertion of additional documentation details.

************
Useful Links
************

- |cwl-home|_
- |cwl-spec|_
- |cwl-guide|_
- |cwl-cmdtool|_
- |cwl-workflow|_
- |esgf-cwt-git|_
- |edam-link|_
- |iana-link|_
- |oas|_
- |ogc|_ (:term:`OGC`)
- |ogc-proc-api|_
- |weaver-issues|_
