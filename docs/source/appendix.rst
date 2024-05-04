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

    API
        | Application Programming Interface
        | Most typically, referring to the use of HTTP(S) requests following an :term:`OpenAPI` specification.
        |
        | In the context of this project, it is also used in some occasion to refer to the RESTful interface
          of :term:`OGC API - Processes`, in contrast to the :term:`OWS` :term:`WPS` interface.

    Application Package
        General term that refers to *"what and how to execute"* the :term:`Process`. Application Packages provide the
        core details about the execution methodology of the underlying operation that defines the :term:`Process`, and
        are therefore always contained within a :ref:`Process Description <proc_op_describe>`. This is more specifically
        represented by a :term:`CWL` specification in the case of `Weaver` implementation, but could technically be
        defined by another similar approach. See the :ref:`Application Package` section for all relevant details.

    AWS
        | Amazon Web Services
        | In the context of `Weaver`, most often referring specifically to the use of :term:`S3` buckets.

    Bill
    Billing
        Result from :ref:`quotation_billing` following :ref:`quote_estimation` when enabled on the `Weaver` instance.

        .. seealso::
            - :ref:`quotation`
            - :ref:`conf_quotation`

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
        Inputs and/or Outputs of :term:`CWL`, :term:`OAP`, :term:`WPS` or :term:`OAS` representation
        depending on context.

    IANA
        Ontology that regroups multiple definitions, amongst which `Weaver` looks up most of its known and supported
        :term:`MIME-types` (|iana-link|_) when resolving file formats.

    HTML
        | HyperText Markup Language
        | Alternative representation of some endpoints provided by the application.
          Requires appropriate ``Accept`` header or ``f``/``format`` query to return this format.

        .. seealso::
            See :ref:`OpenAPI Specification` for details.

    JSON
        | JavaScript Object Notation
        | Default data representation of all objects contained in the application or for their creation
          when using the :term:`API`, except for the :term:`OWS` :term:`WPS` endpoint.

    Job
        Definition of a :term:`Process` execution state with applicable operation metadata.

    KVP
        | Key-Value Pairs
        | String representation of a set of key-value pairs, usually but not limited to, ``=`` character
          separating keys from their values, ``,`` for multi-value (array) definitions, and another separator
          such as ``&`` or ``;`` to distinguish between distinct pairs. Specific separators, and any applicable
          escaping methods, depend on context, such as in URL query, HTTP header, :term:`CLI` parameter, etc.

    Media-Types
    MIME-types
        | Multipurpose Internet Mail Extensions
        | Format representation of the referenced element, often represented by :term:`IANA` or :term:`EDAM` ontologies.
          More recent `Media-Type` naming is employed for the general use of ``Content-Type`` data representation in
          multiple situations and contexts.

    OAS
    OpenAPI
        OpenAPI Specification (`OAS`) defines a standard, programming language-agnostic interface description for
        HTTP APIs. It is used in `Weaver` and :term:`OGC API - Processes` to represent API definitions for requests
        and responses, as well as :term:`I/O` definitions for :term:`Process` description.

        .. seealso::
            |OpenAPI-spec|_

    OGC
        |ogc|_

    OAP
    OGC API - Processes
        The new :term:`API` that defines :term:`JSON` REST-binding representation
        of :term:`WPS` :term:`Process` collection.

    ONNX
        The |ONNX-long|_ standard is an open format employed for sharing machine learning model representations
        with an agnostic approach across frameworks, tools, runtimes, and compilers.

        .. seealso::
            :ref:`quotation_estimator_model`

    OpenSearch
        Protocol of lookup and retrieval of remotely stored files.
        Please refer to :ref:`OpenSearch Data Source` for details.

    OWS
        | :term:`OGC` Web Services
        | Family of services including :term:`WPS`, defined prior to the family of :term:`OGC` :term:`API` standards.

    Process
        Entity that describes the required inputs, produced outputs, and any applicable metadata for the execution of
        the defined script, calculation, or operation.

    Provider
        Entity that offers an ensemble of :term:`Process` under it. It is typically a reference to a remote service,
        where any :term:`Process` it provides is fetched dynamically on demand.

    Quote
    Quotation
        Result from :ref:`quote_estimation` when enabled on the `Weaver` instance.

        .. seealso::
            - :ref:`quotation`
            - :ref:`conf_quotation`

    Quote Estimator
    Quotation Estimator
        A model that can provide cost estimations regarding the execution of a :term:`Process` to form a term:`Quote`.

        .. seealso::
            - :ref:`quotation_estimator_model`
            - :ref:`conf_quotation`

    Request Options
        Configuration settings that can be defined for `Weaver` in order to automatically insert additional
        HTTP request parameters, authentication or other any relevant rules when target URLs are matched.
        See also :ref:`conf_request_options`.

    S3
        Simple Storage Service (:term:`AWS` S3), bucket file storage.

    TOI
        | Time of Interest
        | Corresponds to a date/time interval employed for :term:`OpenSearch` queries in the context
          of :term:`EOImage` inputs.

    UoM
        | Unit of Measure
        | Represents a measurement defined as literal value associated with a specific unit that could take advantage
          of known conversion methods with other compatible units to obtain the equivalent value. These values are
          transferred to the :term:`Process` as specified, and it is up to the underlying :term:`Application Package`
          definition to interpret it as deemed fit.

    URI
        | Uniform Resource Identifier
        | Superset of :term:`URL` and :term:`URN` that uses a specific string format to identify a resource.

    URL
        | Uniform Resource Locator
        | Subset of :term:`URI` that follows the ``<scheme>://<scheme-specific-part>`` format, as per :rfc:`1738`.
          Specifies where an identified resource is available and the protocol mechanism employed for retrieving it.
          This is employed in `Weaver` for ``http(s)://``, ``s3://`` and ``file://`` locations by :term:`I/O`, or in
          general to refer to :term:`API` locations.

    URN
        | Uniform Resource Name
        | Subset of :term:`URI` that follows the ``urn:<namespace>:<specific-part>`` format, as per :rfc:`8141`.
          It is used to register a unique reference to a named entity such as a :term:`UoM` or other common definitions.

        .. seealso::
            - `IANA URN Namespaces <https://www.iana.org/assignments/urn-namespaces/urn-namespaces.xhtml>`_

    Vault
        Secured storage employed to upload files that should be temporarily stored on the `Weaver` server for
        later retrieval using an access token.

        .. seealso::
            - :ref:`vault_upload`
            - :ref:`file_vault_inputs`

    WKT
        Well-Known Text geometry representation.

    Workflow
        A specific variant of :term:`Process` where the execution consists of nested :term:`Process` executions with
        input/output chaining between operations.

        .. seealso::
            Refer to :ref:`proc_workflow`, :ref:`proc_workflow_ops` and :ref:`app_pkg_workflow`
            sections for more details.

    WPS
        | Web Processing Service.
        | From a formal standpoint, this is the previous :term:`OGC` standard iteration that was employed prior to
          :term:`OGC API - Processes` to represent a server that host one or more :term:`Process` for execution.
          When compared against :term:`CWL` context or generally across `Weaver` documentation and code, this term
          refers to attributes that are specific to typical :term:`Process` description, in contrast to specialized
          attributes introduced by other concepts, such as for example :term:`CWL`-specific implementation details.

    WPS-REST
        Alias employed to refer to :term:`OGC API - Processes` endpoints for corresponding :term:`WPS` definitions.

    WPS-T
        Alias employed to refer to older revisions of :term:`OGC API - Processes` standard.
        The name referred to :term:`WPS` *Transactional* operations introduced by the RESTful API.

    XML
        | Extensible Markup Language
        | Alternative representation of some data object provided by the application.
          Requires appropriate ``Accept`` header or ``f``/``format`` query to return this format.
          For the :term:`OWS` :term:`WPS` endpoint, this is the default representation instead of :term:`JSON`.

        .. seealso::
            See :ref:`OpenAPI Specification` for details.

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
- |ogc-api-proc|_
- |weaver-issues|_
