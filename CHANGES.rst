.. :changelog:

Changes
*******

.. **REPLACE AND/OR ADD SECTION ENTRIES ACCORDINGLY WITH APPLIED CHANGES**

.. _changes_latest:

`Unreleased <https://github.com/crim-ca/weaver/tree/master>`_ (latest)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix missing link in `Job` status `HTML` page for ``inputs`` and ``links`` references.
- Fix invalid link in `Job` status `HTML` page for ``logs`` reference.
- Fix consistency between link names between `Job` status and `Process` description `HTML` pages.

.. _changes_6.6.0:

`6.6.0 <https://github.com/crim-ca/weaver/tree/6.6.0>`_ (2025-05-08)
========================================================================

Changes:
--------
- Update Docker builds and CI tests to use Python 3.12 by default.
- Add ``f=xml`` support for `Job` status endpoints to directly retrieve the corresponding `WPS` `XML` status content.
- Add ``schema=wps`` and ``profile=wps`` query parameter support for `Job` status endpoints.
  If used by themselves, these query parameter values will return the same `WPS` `XML` content as when using ``f=xml``.
  If combined with `JSON` format (i.e.: ``?f=json&profile=wps``), the `OGC API - Processes` `Job` status information
  will be returned instead, but using the corresponding `WPS` ``status`` values. Specifically, this allows returning
  the previous `WPS`  ``succeeded`` and ``started`` status values instead of the `OGC API - Processes` ``successful``
  and ``running`` values respectively. This is provided to help clients that have to deal with the mixture of
  properties until the standard is properly stabilized and released. However, the default status values returned
  by ``profile=ogc`` should be preferred and employed whenever possible.
- Enable Docker `Provenance <https://docs.docker.com/build/metadata/attestations/slsa-provenance>`_
  and `Software Bill of Materials (SBOM) <https://docs.docker.com/build/metadata/attestations/sbom>`_
  within the CI to release |pavics_weaver|_ images including this tracking information by default for
  improved security and trust toward the software runtime, as observed through
  the `Docker Scout Health Score <https://docs.docker.com/scout/policy/>`_.
  Running ``make docker-build`` without arguments will build the images without these features by default.
  They can be enabled using ``DOCKER_PROV=true make docker-build``. Building the images with these features
  requires an intermediate step to setup a `builder` with
  the `docker-container <https://docs.docker.com/build/builders/drivers/docker-container>`_ driver.

Fixes:
------
- Add missing ``f`` and ``format`` query parameters for `Job` status endpoints in `OpenAPI` schema.

.. _changes_6.5.0:

`6.5.0 <https://github.com/crim-ca/weaver/tree/6.5.0>`_ (2025-05-02)
========================================================================

Changes:
--------
- Add `Job` status `HTML` response (resolves `#779 <https://github.com/crim-ca/weaver/issues/779>`_).
- Add the ``process`` property to `Job` status response when requesting ``profile=openEO``,
  with a direct reference to the underlying `CWL` `Application Package` of the main `Process` ran by the `Job`.

Fixes:
------
- Fix `W3C PROV` endpoints not returning contents in appropriate type when using ``f`` or ``format`` query parameter.
  On top of the supported explicit ``Accept`` header, the endpoints will now also allow either explicit ``Content-Type``
  passed by ``f`` / ``format`` query parameter, their shorthand representations (e.g.: ``json`` for ``application/json``
  and their more verbose ``PROV``-specific representation (e.g.: ``f=prov-n``), all case-insensitive.
- Fix ``/prov`` endpoint not correctly allowing the `YAML` equivalent representation of ``PROV-JSON`` contents.
- Fix reported ``$schema`` to point at the `openEO` *Batch Job* `OenAPI` definition when requesting ``profile=openEO``.
- Fix reported ``type`` of the `openEO` *Batch Job* `OenAPI` definition as alternate to `OGC API - Processes` `Job`
  status using new ``weaver.processes.constants.JobStatusType`` definition that includes previous
  the ``process`` and ``provider`` values applied by ``weaver.datatype.Job.type``.
- Fix `Job` statistics not reported by the API in case of execution failure, although they might be partially available.

.. _changes_6.4.1:

`6.4.1 <https://github.com/crim-ca/weaver/tree/6.4.1>`_ (2025-03-14)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix resolution of the static endpoint when requesting CSS styles and favicon for `HTML` rendering
  to employ the configured ``weaver.wps_restapi_url`` (or other settings to obtain it) instead of the
  potentially unresolvable request URI, such as when behind a proxy.
- Pin ``cryptography>=44.0.1`` to address vulnerabilities
  `CVE-2023-50782 <https://nvd.nist.gov/vuln/detail/CVE-2023-50782>`_,
  `CVE-2024-6119 <https://nvd.nist.gov/vuln/detail/CVE-2024-6119>`_,
  `CVE-2024-26130 <https://nvd.nist.gov/vuln/detail/CVE-2024-26130>`_,
  `CVE-2023-49083 <https://nvd.nist.gov/vuln/detail/CVE-2023-49083>`_.

.. _changes_6.4.0:

`6.4.0 <https://github.com/crim-ca/weaver/tree/6.4.0>`_ (2025-03-04)
========================================================================

Changes:
--------
- Add resilient handling of `I/O` literal ``default`` values when parsing remote `OGC API - Processes` descriptions.
  Due to varying definitions from the standard revisions, some implementations could indicate a single literal default
  value as an array representation (e.g.: ``default: [1.23]``), leading to parsing "errors" in `Weaver` that expects a
  strict match between the ``default`` value and its ``type``.

Fixes:
------
- Fix resolution of `Process` revisions by ``{processID}:{version}`` when queried on the `WPS` endpoint.
- Fix resolution of `Process` revisions when queried by multiple ID and/or version combinations on the `WPS` endpoint.
- Fix resolution of `Process` revisions by ``{processID}:{version}`` for execution by `OGC API - Processes` endpoint
  (fixes `#799 <https://github.com/crim-ca/weaver/issues/799>`_).
- Fix ``jobControlOptions`` not respected in cases where resolution occurs against a restricted set of capabilities
  for a given `Process` when the submitted `Job` requests an invalid combination by execution ``mode`` body parameter.
- Fix ``remote`` and ``local`` tags incorrectly applied to `Job` definition.

.. _changes_6.3.0:

`6.3.0 <https://github.com/crim-ca/weaver/tree/6.3.0>`_ (2025-02-18)
========================================================================

Changes:
--------
- Update ``owslib==0.32.1`` for parameters fixes employed by *Collection Input* with ``format=ogc-coverage-collection``.
- Drop support of Python 3.9 (required for ``owslib==0.32.1`` dependency).

Fixes:
------
- Fix parsing of *Collection Input* ``format=ogc-coverage-collection`` and ``format=ogc-map-collection``
  to provide additional parameters to the remote collection request.
- Update ``pygeofilter>=0.3.1`` to resolve ``filter-lang=FES`` parser as per other filters
  (relates to `geopython/pygeofilter#102 <https://github.com/geopython/pygeofilter/pull/102>`_).

.. _changes_6.2.0:

`6.2.0 <https://github.com/crim-ca/weaver/tree/6.2.0>`_ (2025-02-06)
========================================================================

Changes:
--------
- Replace ``succeeded`` status by ``successful`` everywhere where applicable (as originally defined by OGC API v1),
  to align with reversal of the proposed draft name, aligning between both v1 and v2 of `OGC API - Processes`
  (relates to `opengeospatial/ogcapi-processes#483 <https://github.com/opengeospatial/ogcapi-processes/pull/483>`_).
- Modify `Job` ``subscribers`` definition to employ the normalized ``weaver.status.StatusCategory`` instead
  of ``weaver.status.Status`` as mapping keys, such that email and callback notifications are unified under
  a common naming convention regardless of the resolved ``weaver.status.StatusCompliant`` representation.

Fixes:
------
- Fix ``weaver.cli.RequestAuthHandler`` and its derived classes erroneously invoking ``request_auth`` method when
  both the ``url`` and ``token`` are omitted, leading to invalid ``requests`` call under ``weaver.utils.request_extra``.

.. _changes_6.1.1:

`6.1.1 <https://github.com/crim-ca/weaver/tree/6.1.1>`_ (2024-12-20)
========================================================================

Changes:
--------
- Update Docker image Python from 3.10 to 3.11 for performance improvements.

Fixes:
------
- Fix ``PROV`` endpoints returning multiple ``Content-Type`` headers
  (default ``text/html`` inserted by ``webob.response.Response`` class onto top of the explicit one specified)
  leading to inconsistent responses parsing and rendering across clients.

.. _changes_6.1.0:

`6.1.0 <https://github.com/crim-ca/weaver/tree/6.1.0>`_ (2024-12-18)
========================================================================

Changes:
--------
- Add support of Python 3.13.
- Drop support of Python 3.8.
- Add support of *OGC API - Processes - Part 4: Job Management* related to ``PROV`` requirement and conformance classes.
- Add support of `W3C PROV <https://www.w3.org/TR/prov-overview/>`_ to provide ``GET /jobs/{jobId}/prov`` endpoints
  and all underlying paths (``/info``, ``/who``, ``/run``, ``/inputs``, ``/outputs``, and ``../{runId}`` variants)
  to retrieve provenance metadata from a `Job` execution and its corresponding `Process` and `Workflow` definitions,
  as processed by ``cwltool``/``cwlprov`` and extended by `Weaver`-specific server metadata.
  Supported ``PROV`` representations are ``PROV-N``, ``PROV-NT``, ``PROV-JSON``, ``PROV-JSONLD``, ``PROV-XML``
  and ``PROV-TURTLE``, each of which can be obtained by providing the corresponding ``Accept`` headers.
- Add ``weaver.cwl_prov`` configuration option to control the new ``PROV`` metadata collection feature.
- Add ``prov`` and ``provenance`` CLI and ``WeaverClient`` operations.
- Extend ``weaver.cli.WeaverArgumentParser`` "*rules*" to allow returning an error message providing better
  case-by-case details about the specific cause of failure handled by the *rule* callable.
- Update certain ``cornice`` service definitions that were using "``prov``" as referencing to `Providers` to avoid
  confusion with the multiple ``PROV``/`Provenance` related terminology and services added for the new feature.
- Pin ``cwltool==3.1.20241217163858`` to employ the official release including
  ``PROV`` configuration provided to easily configured `Weaver`
  (relates to `common-workflow-language/cwltool#2082 <https://github.com/common-workflow-language/cwltool/pull/2082>_)
  and integrate previously provided fixes
  (relates to `common-workflow-language/cwltool#2082 <https://github.com/common-workflow-language/cwltool/pull/2036>_)
  that were applied by a forked backport ``https://github.com/fmigneault/cwltool`` repository.

Fixes:
------
- Fix missing documentation about certain ``WeaverClient`` operations.
- Fix ``weaver.cli.OperationResult`` not setting its ``text`` property when a valid non-`JSON` response is obtained.
- Fix the `API` frontpage `HTML` rendering to returning enabled features and corresponding ``doc``/``url``/``api``
  endpoints for quick referencing the capabilities activated for a `Weaver` instance.

.. _changes_6.0.0:

`6.0.0 <https://github.com/crim-ca/weaver/tree/6.0.0>`_ (2024-12-03)
========================================================================

Changes:
--------
- Add support of *OGC API - Processes - Part 3: Workflows and Chaining* with *Nested Process* ad-hoc workflow
  definitions directly submitted for execution (fixes `#747 <https://github.com/crim-ca/weaver/issues/747>`_,
  relates to `#412 <https://github.com/crim-ca/weaver/issues/412>`_).
- Add support of *OGC API - Processes - Part 4: Job Management* endpoints for `Job` creation and execution
  (fixes `#716 <https://github.com/crim-ca/weaver/issues/716>`_).
- Add ``format: stac-items`` support to the ``ExecuteCollectionInput`` definition allowing a ``collection`` input
  explicitly requesting for the STAC Items themselves rather than contained Assets. This avoids the ambiguity between
  Items and Assets that could both represent the same ``application/geo+json`` media-type.
- Add `CLI` operations ``info``, ``version`` and ``conformance`` to retrieve the metadata details of the server.
- Add `CLI` operations ``update_job``, ``trigger_job`` and ``inputs`` corresponding to the required `Job` operations
  defined by *OGC API - Processes - Part 4: Job Management*.
- Add `CLI` support of the ``collection`` and ``process`` inputs respectively for *Collection Input*
  and *Nested Process* submission within the execution body of another `Process`.
  Only forwarding of the input parameters is performed by the `CLI`. Validation is performed server-side.
- Add ``headers``, ``mode`` and ``response`` parameters along the ``inputs`` and ``outputs`` returned by
  the ``GET /jobs/{jobID}/inputs`` endpoint to better describe the expected resolution strategy of the
  multiple `Job` execution options according to submitted request parameters.
- Increase flexible auto-resolution of *synchronous* vs *asynchronous* `Job` execution when no explicit strategy
  is specified by ``mode`` body parameter or ``Prefer`` header. Situations where such flexible resolution can occur
  will be reflected by a ``mode: auto`` and the absence of ``wait``/``respond-async`` in the ``Prefer`` header
  within the response of the ``GET /jobs/{jobID}/inputs`` endpoint.
- Add support "on-trigger" `Job` submission using the ``status: create`` request body parameter.
  Such a `Job` will be pending, and can be modified by ``PATCH /jobs/{jobID}`` requests, until execution is triggered
  by a subsequent ``POST /jobs/{jobID}/results`` request.
- Align ``GET /jobs/{jobID}/outputs`` with requirements of *OGC API - Processes - Part 4: Job Management* endpoints
  such that omitting the ``schema`` query parameter will automatically apply the `OGC` mapping representation by
  default. Previous behavior was to return whichever representation that was used by the internal `Process` interface.
- Align `Job` status and update operations with some of the `openEO` behaviors, such as supporting a `Job` ``title``
  and allowing ``status`` to return `openEO` values when using ``profile=openeo`` in the ``Content-Type`` or using
  the query parameter ``profile``/``schema``. The ``Content-Schema`` will also reflect the resolved representation
  in the `Job` status response.
- Add support of ``response: raw`` execution request body parameter as alternative to ``response: document``,
  which allows directly returning the result contents or ``Link`` headers rather then embedding them in a `JSON`
  response (fixes `#376 <https://github.com/crim-ca/weaver/issues/376>`_).
- Add support of ``Prefer: return=minimal`` and ``Prefer: return=representation`` header as alternative method
  to request the ``response: document`` and ``response: raw`` parameters
  (fixes `#414 <https://github.com/crim-ca/weaver/issues/414>`_).
  Minor differences exist according to supplied ``transmissionMode`` and the original data/link results.
  See `Process Execution <file:///home/francis/dev/weaver/docs/build/html/processes.html#proc-op-execute>`_
  documentation for details.
- Add support of ``outputs`` execution request body parameter to filter returned outputs from
  the ``GET /jobs/{jobId}/results`` (async) or returned directly (sync) from ``POST /processes/{processId}/execution``
  (fixes `#380 <https://github.com/crim-ca/weaver/issues/380>_`).
- Add support of ``Accept: multipart/*`` and ``Accept: multipart/mixed`` when submitting an execution to obtain
  the results as multiple parts embedded within the response contents. Parts are represented with their default
  data/link representation, unless overridden by corresponding ``transmissionMode`` per output ID.
- Add ``output_links``/``-oL``/``--output-link`` parameter to Python client and CLI to retrieve ``Link`` headers
  as `Job` results. Due to the multiple ``Link`` headers returned by `Job` results, this cannot be performed
  automatically without the assumption of which ``rel`` links correspond to actual output IDs to extract.
- Add ``output_filter``/``--oF``/``--output-filter`` parameter to Python client and CLI to indicate
  any ``outputs`` to be filtered when submitting the `Process` execution.
- Update ``Preference-Applied`` header reported by execution responses to
  include ``return=minimal`` or ``return=representation`` as applicable by the requested ``Prefer`` header.
- Update documentation with a mapping of *Process Execution Results* according to
  submitted ``response`` body parameter (*OGC API - Processes v1.0*),
  the ``Prefer: return`` header (*OGC API - Processes v2.0*), the requested ``Accept`` header,
  and any relevant ``transmissionMode`` request body overrides per filtered ``outputs``.
- Modify the mapping and generation of `WPS`/`OGC API` metadata against `CWL` corresponding fields using
  the namespaced ``schema.org`` to *always* employ the full `URI` as ``rel`` or ``role`` according to the
  provided metadata link or value to allow explicit identification of the ``schema.org`` concept origin.
- Add mapping of metadata from `CWL` to `WPS`/`OGC API` ``metadata`` field for additional ``schema.org`` concepts.

Fixes:
------
- Fix `CLI` failing to parse additional ``Link`` headers when they are all combined into a single comma-separated value.
- Fix `STAC` ``collection`` incorrectly resolving the API endpoint to perform the Item Search operation.
- Fix resolution of input/output media-types against the unspecified defaults to allow more descriptive results.
- Fix race condition between workflow step early input staging cleanup on successful step status update.
  Due to the ``_update_status`` method of ``pywps`` performing cleanup when propagating a successful completion of
  a step within a workflow, the parent workflow was marked as succeeded (`XML` status document), and any step executed
  after the successful one that were depending on the workflow inputs could result in not-found file references if it
  was staged by the previous step.
- Fix optional ``title`` in metadata causing failing HTML rendering of the `Process` description if omitted.
- Fix HTML ``Content-Type`` header erroneously set for JSON-only (for now) ``GET /jobs/{jobId}`` as similar endpoints.
- Fix `CWL` ``enum`` type mishandling ``symbols`` containing a colon (``:``) character (e.g.: a list of allowed times)
  leading to their invalid interpretation as namespaced strings (i.e.: ``<ns>:<value>``), in turn failing validation
  and breaking the resulting `CWL`. Such ``enum`` will be patched with updated ``symbols`` prefixed by ``#`` to respect
  the expected URI representation of ``enum`` values by the `CWL` parser (relates to
  `common-workflow-language/cwltool#2071 <https://github.com/common-workflow-language/cwltool/issues/2071>`_).
- Fix `CWL` conversion from a `OGC API - Processes` definition specifying an `I/O` with ``schema`` explicitly
  indicating a ``type: array`` and nested ``enum``, even if ``minOccurs: 1`` is omitted or explicitly set.
- Fix ``url`` parameter to override the `CLI` internal ``url`` when passed explicitly to the invoked operation.
- Fix ``href`` detection when provided directly as mapping within the ``executionUnit`` of the deployment body.
- Fix definition of `CWL` ``schema.org`` namespaced fields (i.e.: ``s:author`` and ``s:dateCreated``) causing
  schema deserialization error when validating the submitted request body against typical examples provided in
  `CWL Metadata and Authorship <https://www.commonwl.org/user_guide/topics/metadata-and-authorship.html>`_.
- Fix mapping of `CWL` ``schema.org`` metadata to `WPS`/`OGC API` equivalent metadata defining invalid ``role``
  not respecting the `URI` schema validation constraint.
- Fix ``GET /jobs/{jobId}/inputs`` contents to correctly return the submitted ``outputs`` definition
  for `Process` execution (fixes `#715 <https://github.com/crim-ca/weaver/issues/715>`_).
- Fix missing ``Link`` header with ``rel: monitor`` relationship in the created `Job` responses
  (fixes `#596 <https://github.com/crim-ca/weaver/issues/596>`_).
- Fix missing ``/rec/core/link-header`` definition in ``GET /conformance`` response reporting
  that ``Link`` headers are returned for corresponding references of a given request
  (fixes `#378 <https://github.com/crim-ca/weaver/issues/378>`_).
- Fix ``transmissionMode: value`` that was ignored for ``response: document`` if the output was represented by default
  as a *complex*  file URL, and ``transmissionMode: reference`` that was ignored if the output was *literal*  data.
  The ``transmissionMode`` will now return the appropriate inline data or URL as requested.
- Add missing conformance and requirement references for *OGC API - Processes - Part 2: DRU*
  (fixes `##620 <https://github.com/crim-ca/weaver/issues/620>`_).
- Add the appropriate HTTP error type to respect ``/conf/dru/deploy/unsupported-content-type``
  (fixes `#624 <https://github.com/crim-ca/weaver/issues/624>`_).
- Fix S3 bucket storage for result file missing the output ID in the path to match local WPS output storage structure.
- Fix rendering of the ``deprecated`` property in `OpenAPI` representation.

.. _changes_5.9.0:

`5.9.0 <https://github.com/crim-ca/weaver/tree/5.9.0>`_ (2024-09-12)
========================================================================

Changes:
--------
- Add `CWL` schema definitions with ``weaver`` namespace
  (see `weaver/schemas/cwl <https://github.com/crim-ca/weaver/tree/master/weaver/schemas/cwl>`_)
  that provide explicit requirement classes
  for ``weaver:BuiltinRequirement``, ``weaver:WPS1Requirement``, ``weaver:OGCAPIRequirement``
  and ``weaver:ESGF-CWTRequirement`` to avoid missing reference warnings that were previously raised by ``cwltool``
  due to `Application Packages` using their non-``weaver`` namespaced classes in ``hints``. These new `CWL`
  definitions can be reported directly in the ``requirements`` section, better describing the required dependencies
  of the referenced `Process` and/or `Provider` in the workflow steps.
- Add hosted `CWL` schema definitions for ``weaver`` accessible at the ``https://schemas.crim.ca/cwl/weaver#`` endpoint.
- Add support of ``weaver`` namespaced ``requirements`` to the ``cwltool`` runner.
- Add better validation off well-known `CWL` ``$namespaces`` as reserved keywords when deploying a `Process` to ensure
  better interoperability between implementations and adequate metadata resolution
  (relates to `#463 <https://github.com/crim-ca/weaver/issues/463>`_).
- Add documentation about *Jupyter Notebook* to `CWL` conversion
  utility `ipython2cwl <https://github.com/common-workflow-lab/ipython2cwl>`_
  and a sample `crim-ca/ncml2stac <https://github.com/crim-ca/ncml2stac/tree/main#ncml-to-stac>`_ repository
  making use of it with the `Weaver` `CLI` to generate a deployed `OGC API - Processes` definition
  (fixes `#63 <https://github.com/crim-ca/weaver/issues/63>`_).
- Add parsing of additional metadata from ``schema.org`` in CWL document to convert into process fields
  (fixes `#463 <https://github.com/crim-ca/weaver/issues/463>`_).
- Add more metadata mapping details in documentation (fixes `#613 <https://github.com/crim-ca/weaver/issues/613>`_).

Fixes:
------
- Fix ``VariableSchemaNode`` resolution of child nodes with complex mixture of ``StrictMappingSchema`` or when
  using the equivalent ``unknown = "raise"`` parameter for a ``colander.Mapping`` schema type to
  disallow ``additionalProperties`` that cannot be mapped to a particular child `JSON` schema definition.
- Fix ``VariableSchemaNode`` resolution to allow mapping against multiple ``variable`` sub-nodes representing
  different nested `JSON` schema nodes permitted under the ``additionalProperties`` mapping.
- Fix ``GET /jobs`` endpoint failing to return the rendered `HTML` listing when ``detail=true`` was omitted or
  set to any non-detailed value. The ``detail`` query parameter is ignored for `HTML` since details are always
  required to populate the `Job` table.
- Pin ``pymongo>=4.3`` and remove ``celery[mongodb]`` extra requirement to avoid incompatible resolution
  of ``pymongo[srv]>=4.8.0`` (relates to `celery/celery#9254 <https://github.com/celery/celery/issues/9254>`_
  and `MongoDB PYTHON-4756 <https://jira.mongodb.org/browse/PYTHON-4756>`_).

.. _changes_5.8.0:

`5.8.0 <https://github.com/crim-ca/weaver/tree/5.8.0>`_ (2024-09-05)
========================================================================

Changes:
--------
- Add support of *OGC API - Processes: Part 3* ``collection`` as input to a `Process`
  (fixes `#682 <https://github.com/crim-ca/weaver/issues/682>`_).
- Add ``AnyCRS`` schema definition with improved validation of allowed values.
- Use ``AnyCRS`` schema for ``SupportedCRS``, ``XMLStringCRS``, ``BoundingBoxValue`` and ``ExecuteCollectionInput``
  instead of a generic ``URL`` schema definition for better reference validation, while allowing alternate short forms.
- Add auto-resolution of media-type for cases where it can reasonably be inferred from a ``schema`` reference,
  such as an URI referring to a ``.json`` or ``.xsd`` respectively representing `JSON` and `XML` data.
- Update ``cwltool`` with fork
  `fmigneault/cwltool @ fix-load-contents-array <https://github.com/fmigneault/cwltool/tree/fix-load-contents-array>`_
  until ``loadContents`` behavior is resolved for ``type: File[]``
  (relates to `common-workflow-language/cwltool#2036 <https://github.com/common-workflow-language/cwltool/pull/2036>`_).

Fixes:
------
- Fix `CWL` I/O with ``format`` defined as a `JavaScript Expression` to be incorrectly parsed by the convertion
  operations to extract applicable media-types. These cases will be ignored, since media-types cannot be inferred
  from them. The `WPS` or `OAS` I/O definitions should instead provide the applicable media-types
  (relates to `common-workflow-language/cwl-v1.3#52 <https://github.com/common-workflow-language/cwl-v1.3/issues/52>`_).
- Fix ``format`` parsing when trying to infer media-types from various I/O definition representations using a
  reference provided as an URI schema from an ontology. Parsing caused the URI to be split, causing an invalid
  resolution. If no appropriate media-type is provided, JSON will be used by default, while preserving the submitted
  schema URI.
- Fix invalid resolution of ``weaver.formats.ContentEncoding.open_parameters``.
- Fix minor resolution combinations or redundant checks for multiple ``weaver.formats`` utilities.
- Fix `CWL` ``format`` resolution check against `IANA` media-types if the reference ontology happens to be
  temporarily/sporadically unresponsive to SSL handshake check, allowing temporary HTTP resolution of media-type.

.. _changes_5.7.0:

`5.7.0 <https://github.com/crim-ca/weaver/tree/5.7.0>`_ (2024-07-16)
========================================================================

Changes:
--------
- Add support of `HTML` responses for `OGC API - Processes` endpoints
  (fixes `#210 <https://github.com/crim-ca/weaver/issues/210>`_).
- Add ``weaver.wps_restapi_html`` configuration setting to control support of `HTML` responses.
- Add ``weaver.wps_restapi_html_override_user_agent`` configuration setting for control of default `HTML` or `JSON`
  rendering by requests from web browsers.
- Refactor ``pyramid`` configuration to employ ``Configurator.add_cornice_service``
  utility instead of ``Configurator.add_route`` and ``Configurator.add_view`` handlers that were causing a lot of
  duplication between the ``cornice.Service`` parametrization and their corresponding view decorators. All metadata
  is now embedded within the same decorator operation.
- Add missing documentation for ``weaver.wps_restapi_doc`` and ``weaver.wps_restapi_ref`` configuration settings.
- Modified the base path/URL resolution of the `OpenAPI` endpoint to be located at the application root instead of being
  nested under ``weaver.wps_restapi_path`` or ``weaver.wps_restapi_url``, since the OpenAPI `JSON` and `HTML` responses
  are employed for representing supported requests and responses of both the `REST` and the `OWS` `WPS` interfaces.
- Update `Swagger-UI` version for latest rendering fixes of `OpenAPI` definitions.
- Add automatic redirect from ``/api?f=json`` to ``/json`` response to allow `OpenAPI` schema access directly
  from the same endpoint as the `Swagger-UI` rendering of the schemas. The ``Accept`` header
  for ``application/json`` or explicitly ``application/vnd.oai.openapi+json; version=3.0`` are also supported
  (fixes `#623 <https://github.com/crim-ca/weaver/issues/623>`_)
- Add `OpenAPI` response rendering as `YAML` using ``/api?f=yaml`` or ``Accept: application/yaml``
  (relates to `#456 <https://github.com/crim-ca/weaver/issues/456>`_).

Fixes:
------
- Fix ``weaver.wps_restapi_path`` incorrectly resolved when populating `Process` paging links.
- Fix invalid resolution of reported API endpoints in the `OpenAPI` and frontpage response when
  ``weaver.wps_restapi_path``, ``weaver.wps_restapi_url``, ``weaver.wps_path`` or ``weaver.wps_url``
  were set to other prefix path values than the default root base URL.
- Fix ``weaver.formats.OutputFormat`` to return ``JSON`` by default when an invalid format could not be resolved.

.. _changes_5.6.1:

`5.6.1 <https://github.com/crim-ca/weaver/tree/5.6.1>`_ (2024-06-14)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix invalid ``default`` attribute resolution of an optional `WPS` ``ComplexData`` (i.e.: ``minOccurs: 0``) that also
  provides a ``Default/Format`` in the `XML` process description. When that input was omitted (as permitted) from the
  execution request, parsing of the `XML` would incorrectly inject the `JSON` representation of the ``Default/Format``
  as a substitute for the ``default`` value. See ``weaver.processes.convert.ows2json_io`` implementation for details.

.. _changes_5.6.0:

`5.6.0 <https://github.com/crim-ca/weaver/tree/5.6.0>`_ (2024-06-11)
========================================================================

Changes:
--------
- Increase default ``pywps`` configuration values using new settings
  ``weaver.wps_max_request_size = 30MB`` and ``weaver.wps_max_single_input_size = 3GB``.
  Defaults are selected to allow larger files that are more in line with common occurrences
  when dealing with Earth Observation data.

Fixes:
------
- Fix resolution of ``null`` value explicitly provided or implicitly resolved by `CWL` between ``Workflow`` steps
  and the `Process` execution context transfer between `OGC API - Processes` and `WPS`, in the case of ``ComplexData``
  and ``BoundingBoxData`` structures. Inputs will now be omitted from execution request to obtain the intended behavior
  instead of submitting empty data structures, leading to inconsistent parsing results and behaviors.
- Fix resolution of the `CWL` ``outputBinding.glob`` for staging the output by ID within a ``Workflow`` that uses
  recurring `Process` references across steps. To disambiguate between common output ID between steps, `CWL` uses the
  step ID as prefix to the output long-name. This caused a mismatch with the output collection strategy for staging
  the `Job` result, as the expected directory location does not contain the nested step ID.

.. _changes_5.5.0:

`5.5.0 <https://github.com/crim-ca/weaver/tree/5.5.0>`_ (2024-06-06)
========================================================================

Changes:
--------
- Add support of multiple-value array outputs to allow `CWL` `Application Package` that can make use of such definitions
  (fixes `#25 <https://github.com/crim-ca/weaver/issues/25>`_).
- Add ``weaver.wps_restapi.colander_extras.AnyType`` and ``weaver.wps_restapi.colander_extras.NoneType`` with their
  corresponding `JSON`/`OpenAPI` schema converters to allow the definition of ``null`` and ``{}`` type definitions.

Fixes:
------
- Fix ``weaver.wps_restapi.colander_extras.ExtendedSequenceSchema`` not allowing other item types than a mapping.

.. _changes_5.4.2:

`5.4.2 <https://github.com/crim-ca/weaver/tree/5.4.2>`_ (2024-06-05)
========================================================================

Changes:
--------
- Add ``POST /processes/{processId}/execution`` as fallback endpoint for ``POST /processes/{processId}/jobs`` to submit
  the `Job` execution within a  `CWL` ``Workflow`` using a remote `OGC API - Processes` step to accommodate for varying
  versions of the standard and implementations.
- Add error status update of the response from a failed step ``Job`` request to allow investigating the cause from logs.

Fixes:
------
- Fix ``Cookie`` header not propagated to every underlying `CWL` ``Workflow`` step causing authorization failure
  midway during an authorized `Process` execution.

.. _changes_5.4.1:

`5.4.1 <https://github.com/crim-ca/weaver/tree/5.4.1>`_ (2024-06-03)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix `Process` ID resolution from `CWL` ``Workflow`` step package from long-form URL reference included as fragment.

.. _changes_5.4.0:

`5.4.0 <https://github.com/crim-ca/weaver/tree/5.4.0>`_ (2024-05-27)
========================================================================

Changes:
--------
- Use ``requests.auth.AuthBase`` type for ``auth`` parameter of ``weaver.cli.WeaverClient`` methods to allow
  any ``requests`` compatible package to use their own implementation of the authentication mechanism without
  explicitly deriving from ``weaver.cli.AuthHandler`` (fixes `#628 <https://github.com/crim-ca/weaver/issues/628>`_).
- Add `CWL` ``MultipleInputFeatureRequirement`` support.
- Add `CWL` ``SubworkflowFeatureRequirement`` support.
- Add `CWL` ``Workflow`` explicit schema validation of its ``steps``.
- Remove "unknown" definitions in `CWL` ``requirements``. Only fully defined and resolved definitions will be allowed.
  If an unsupported `CWL` requirement by `Weaver` must be provided (but is a valid definition supported by ``cwltool``),
  it must now be provided through ``hints`` to succeed schema validation.
- Improve support of `CWL` output definition using ``loadContents`` to an ``outputBinding.glob`` reference to
  load the ``File`` contents into a ``string`` output.
- Improve support of `CWL` JavaScript expressions within intermediate steps of a ``Workflow`` to collect output results
  from relevant sources with better data manipulation flexibility.
- Modify signature of ``weaver.processes.wps_process_base.WpsProcessInterface`` to allow better reuse of the
  common operations shared by derived `CWL` ``Workflow`` steps implemented by ``ESGFProcess``, ``Wps1Process``,
  ``Wps3Process`` and ``OGCAPIRemoteProcessBase``.
- Refactor ``ESGFProcess`` to use the common operations of `CWL` ``Workflow`` steps defined by ``WpsProcessInterface``.

Fixes:
------
- Fix ``pywps.inout.basic.BasicComplex`` using default ``emptyvalidator`` when the expected output format does not
  provide an explicit implementation, leading to failure of the `Job` due to ``MODE.SIMPLE`` validation level being set.
  A basic validator will instead be set to check that the expected file extension minimally matches the expected type.
- Fix `CLI` incorrectly parsing inputs when provided directly as `OGC` style mapping with ``href``.
- Fix invalid `CWL` schema definition for ``ScatterFeatureRequirement`` that directly
  contained the corresponding fields ``scatter`` and ``scatterMethod``, instead of the expected
  definition within a `Workflow Step <https://www.commonwl.org/v1.2/Workflow.html#WorkflowStep>`_.
- Fix `CWL` ``requirements`` schema definition using ``OneOf`` and the ``discriminator`` property that could sometime
  drop a definition when it only contained an empty mapping ``{}``, and that the corresponding requirement allows it.
- Fix ``weaver.wps_restapi.colander_extras.AnyOfKeywordSchema`` not allowing distinct `JSON` structure ``type`` to be
  combined simultaneously.
- Fix `CWL` ``Workflow`` not retrieving output results when returned directly as literal data from a remote `Process`.
- Fix `CWL` ``Workflow`` potentially failing tool resolution for a local step `Process` if ``hints`` where omitted.
- Fix `CWL` ``Workflow`` resolution of step ``requirements`` from one of the `Weaver` application types
  (i.e.: ``builtin``, ``docker``, ``ESGF-CWT``, ``OGCAPI``, ``WPS1``) due to ``cwltool`` namespace adding a
  prefixed URI.
- Pin ``requests>=2.32`` and ``docker>=7.1`` (Python Package) to address
  `CVE-2024-35195 <https://nvd.nist.gov/vuln/detail/CVE-2024-35195>`_ to avoid inconsistent ``verify``
  option over multiple requests when using a session
  (relates to `psf/requests#6710 <https://github.com/psf/requests/pull/6710>`_
  and `docker/docker-py#3257 <https://github.com/docker/docker-py/pull/3257>`_).

.. _changes_5.3.0:

`5.3.0 <https://github.com/crim-ca/weaver/tree/5.3.0>`_ (2024-05-13)
========================================================================

Changes:
--------
- Add `CWL` ``cwltool:Secrets`` support (fixes `#511 <https://github.com/crim-ca/weaver/issues/511>`_).
- Add `CWL` ``StepInputExpressionRequirement`` support.

Fixes:
------
- Pin ``json2xml==4.1.0`` to fix major release breaking older Python typings without any actual change to functionality.

.. _changes_5.2.0:

`5.2.0 <https://github.com/crim-ca/weaver/tree/5.2.0>`_ (2024-05-08)
========================================================================

Changes:
--------
- Add multiple missing `OGC API - Processes` conformance references.
- Modify default query parameter value ``links=true`` for ``/processes`` summary listing to conform with
  conformance class ``/conf/core/process-summary-links`` as default behavior
  (relates to `opengeospatial/ogcapi-processes#406 <https://github.com/opengeospatial/ogcapi-processes/pull/406>`_,
  fixes `crim-ca/weaver#622 <https://github.com/crim-ca/weaver/issues/622>`_).

Fixes:
------
- Adjust ``weaver.utils.get_caller_name`` to better handle decorated functions, and apply more precise warning messages
  to hunt down places were ``weaver.utils.get_request_options`` might still be causing inconsistent HTTP requests due
  to missing *request options* for certain use cases.
- Fix passing down of application settings for `WPS` requests of `Provider`/`Service` operations
  potentially making use of *request options*, which could not obtain the relevant configuration.
- Fix `CLI` failing to resolve a `CWL` Workflow step local reference to a `Process` using ``run: {process}.cwl``
  definition due to the local `CLI` context not having the same URL resolution as the remote `Weaver` server
  (fixes `#630 <https://github.com/crim-ca/weaver/issues/630>`_).
- Fix `CWL` JSON schema reference pointing at older ``1.2.1_proposed`` branch in favor of ``v1.2.1`` tag (relates
  to `common-workflow-language/cwl-v1.2#278 <https://github.com/common-workflow-language/cwl-v1.2/issues/278>`_).
- Pin ``gunicorn>=22`` to address `CVE-2024-1135 <https://nvd.nist.gov/vuln/detail/CVE-2024-1135>`_.
- Pin ``werkzeug>=3.0.3,<3.1`` to address `CVE-2024-34069 <https://nvd.nist.gov/vuln/detail/CVE-2024-34069>`_.

.. _changes_5.1.1:

`5.1.1 <https://github.com/crim-ca/weaver/tree/5.1.1>`_ (2024-03-19)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Use ``typing_extensions.Unpack`` to correctly represent expected types
  for respective ``request-options`` keywords parameters.
- Fix ``linkcheck`` failing due to inconsistent HTTP responses
  (relates to `sphinx-doc/sphinx#12030 <https://github.com/sphinx-doc/sphinx/issues/12030>`_).

.. _changes_5.1.0:

`5.1.0 <https://github.com/crim-ca/weaver/tree/5.1.0>`_ (2024-03-19)
========================================================================

Changes:
--------
- Add ``weaver.wps_client_headers_filter`` setting that allows filtering of specific `WPS` request headers from the
  incoming request to be passed down to the `WPS` client employed to interact with the `WPS` provider
  (fixes `#600 <https://github.com/crim-ca/weaver/issues/600>`_).
- Add ``token`` optional argument to the ``weaver.cli.RequestAuthHandler`` class. If specified, the handler will use
  this token instead of making an authentication request to obtain the token.

Fixes:
------
- Fix ``moto>=5`` used in tests to mock AWS S3 operations that replaced ``mock_s3`` context manager by ``mock_aws``.

.. _changes_5.0.0:

`5.0.0 <https://github.com/crim-ca/weaver/tree/5.0.0>`_ (2023-12-12)
========================================================================

Changes:
--------
- Add ``weaver.formats.ContentEncoding`` with handlers for common encoding manipulation from input values.
- Add |oap_echo|_ to the list of ``weaver.processes.builtin`` definitions with its `CWL` representation and
  complementary `OGC API - Processes` reference implementation details. This `Process` will be automatically deployed
  at `API` startup, and is employed to validate multiple parsing combinations of execution I/O values and encodings
  (fixes `#379 <https://github.com/crim-ca/weaver/issues/379>`_).
- Add support of `OGC` `BoundingBox` definition (``bbox`` and ``crs`` fields) as `Process` execution input value
  with appropriate schema validation (fixes `#51 <https://github.com/crim-ca/weaver/issues/51>`_).
- Add support of `Unit of Measure` (`UoM`) definition (``measurement`` and ``uom`` fields) as `Process` execution
  input value with appropriate schema validation (fixes `#430 <https://github.com/crim-ca/weaver/issues/430>`_).
- Add ``create_metalink`` utility function to facilitate generation of a ``.meta4`` or ``.metalink`` file definition
  from a list of file link references (relates to `#25 <https://github.com/crim-ca/weaver/issues/25>`_).

Fixes:
------
- Fix ``weaver.wps_restapi.swagger_definitions.ExecuteInputValues`` deserialization that sometimes silently dropped
  invalid `JSON`-formatted inputs that did not fulfill schema validation. This was caused by a side effect regarding
  how ``weaver.wps_restapi.colander_extras.VariableSchemaNode`` handled "unknown" `JSON` ``properties`` from submitted
  content. In cases where *required* `Process` inputs were causing the invalid schema, `Job` execution would be aborted
  and the error would be reported due to "missing" inputs. However, if the `JSON` failing schema validation happened to
  be nested under an *optional* input definition, the `Job` execution could have resumed silently by omitting this
  input's value propagation to the downstream `CWL`, `WPS` or `OGC API - Processes` implementation, which could make
  it use an alternative default value than the real input that was submitted for the `Job`.
- Fix schema name representation employed in generated ``colander.Invalid`` error when a schema validation failed, in
  order to better represent deeply nested schema using multiple ``oneOf``, ``anyOf``, ``allOf`` schema nodes.
  Using ``colander.Invalid.asdict``, each dictionary key now properly indicates the specific path of sub-nodes with
  their relevant schema validation error.
- Fix ``variable`` schema node names to provide a ``{SchemaName}<{VariableName}>`` representation, such that it can be
  more easily identified. Schema nodes with a ``variable`` (i.e.: schema under ``additionalProperties``) previously only
  indicated ``{VariableName}``, which made it complicated to follow reference schema classes that formed the error path.
  Each of the evaluated fields against each possible ``variable`` schema will now report their corresponding nested
  schema validation error as ``{SchemaName}<{VariableName}>({field})`` such that results can be understood.
- Fix execution input reference (i.e.: using ``href``) dropping a ``schema`` URL reference if provided explicitly.
  This parameter now remains within the produced content passed to the `Job`, and forwarded to a remote `Process` if
  applicable, but no further schema validation is accomplished with the value in ``schema`` for the moment.
- Fix ``ContentType.IMAGE_OGC_GEOTIFF`` using invalid media-type name (missing ``i`` in ``image``).
- Fix `Job` input validation stripping additional parameters from provided Media-Type, potentially causing mismatching
  Content-Type validation against the corresponding `Process` description inputs. Types should now match exactly the
  original `Process` definition, including any additional parameters and sub-types.
- Fix resolution of ``anyOf`` schema raising ``colander.Invalid`` even when the property was marked as optional
  using ``missing=colander.drop``.
- Fix ``$schema`` of `OGC` ``nameReferenceType`` being reported under every ``dataType`` of ``literalDataDomains`` for
  literal `I/O` of `Process` descriptions. The reference is not only included in the `OpenAPI` definition as intended.
- Fix override of `CWL` ``stderr`` and ``stdout`` definitions if specified by the original *Application Package* for
  its own implementation. These stream handles are added to the `CWL` by Weaver to provide more contextual debugging
  and traceability details of the internal application executed by the `Process`. However, a package making use of this
  functionality of `CWL` to capture an output file would be broken unless naming the file exactly as ``stderr.log`` and
  ``stdout.log``. Weaver will now employ the parameters provided by the *Application Package* if specified.

.. _changes_4.38.0:

`4.38.0 <https://github.com/crim-ca/weaver/tree/4.38.0>`_ (2023-11-24)
========================================================================

Changes:
--------
- Add Python 3.12 support (fixes `#587 <https://github.com/crim-ca/weaver/issues/587>`_).

  * Depends on ``PasteDeploy==3.1.0``
    (relates to `Pylons/pastedeploy#43 <https://github.com/Pylons/pastedeploy/pull/43>`_).
  * Depends on ``pyramid_celery==5.0.0a`` [`crim-ca/pyramid_celery <https://github.com/crim-ca/pyramid_celery>`_ fork]
    (relates to `sontek/pyramid_celery#102 <https://github.com/sontek/pyramid_celery/pull/102>`_).

Fixes:
------
- No change.

.. _changes_4.37.0:

`4.37.0 <https://github.com/crim-ca/weaver/tree/4.37.0>`_ (2023-11-22)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix default `XML` format resolution for `WPS` endpoint when no ``Accept`` header or ``format``/``f`` query parameter
  is provided and that the request is submitted from a Web Browser, which involves additional control logic to select
  the applicable ``Content-Type`` for the response.
- Fix pre-forked ``celery`` worker process inconsistently resolving the ``pyramid`` registry applied
  by ``pyramid_celery`` after worker restart.

.. _changes_4.36.0:

`4.36.0 <https://github.com/crim-ca/weaver/tree/4.36.0>`_ (2023-11-06)
========================================================================

Changes:
--------
- Drop Python 3.7 support.
- Add Python 3.12 to GitHub CI experimental builds.
- Bump ``werkzeug>=3.0.1`` to resolve security vulnerability from the package.

Fixes:
------
- No change.

.. _changes_4.35.0:

`4.35.0 <https://github.com/crim-ca/weaver/tree/4.35.0>`_ (2023-11-03)
========================================================================

Changes:
--------
- Add more secure path validations steps before fetching contents.
- Disallow ``builtin`` processes expecting a user-provided input path to run with local file references such that
  they must respect any configured server-side remote file access rules instead of bypassing security validations
  through resolved local paths.
- Add multiple validation checks for more secure file paths handling when retrieving contents from remote locations.
- Add more tests to validate core code paths of ``builtin`` `Process` ``jsonarray2netcdf``, ``metalink2netcdf`` and
  ``file_index_selector`` with validation of happy path and error handling conditions.

.. _oap_echo: https://schemas.opengis.net/ogcapi/processes/part1/1.0/examples/json/ProcessDescription.json
.. |oap_echo| replace:: ``EchoProcess``

Fixes:
------
- Fix invalid parsing of `XML` Metalink files in ``metalink2netcdf``. Metalink V3 and V4 will now properly consider the
  namespace and specific content structure to extract the NetCDF URL reference, and the `Process` will validate that the
  extracted reference respects the NetCDF extension.

.. _changes_4.34.0:

`4.34.0 <https://github.com/crim-ca/weaver/tree/4.34.0>`_ (2023-10-16)
========================================================================

Changes:
--------
- Add ``alternate`` references, as ``Link`` header and within the `JSON` content ``links`` property when applicable, in
  the returned `Process` description response to refer between the `XML` and the corresponding `JSON` representations.
- Support alternative representations from `OGC API - Processes` schemas for ``executionUnit`` definition
  during `Process` deployment. The *unit* does not need to be nested under ``unit`` or a list anymore, and can instead
  be directly provided as `JSON` mapping. For backward compatibility, the previous list representation is still allowed
  (fixes `#507 <https://github.com/crim-ca/weaver/issues/507>`_).
- Support an additional ``type`` property along a ``unit`` item describing an ``executionUnit`` to specify an IANA
  Media-Type that categories the ``unit`` contents, similarly to how it could be provided for its ``href`` counterpart.
  For the moment, only `CWL`-based ``unit`` are supported, but this could allow future extensions to provide alternate
  representations of an `Application Package`.
- Add schema validation and reference to the `API` landing page, with additional parameters to respect `OGC` schema.
- Add multiple `JSON` schema references for schema classes that are represented by corresponding `OGC` definitions.
- Add `Job` ``subscribers`` support to define `OGC`-compliant callback URLs where HTTP(S) requests will be sent upon
  reaching certain `Job` status milestones (resolves `#230 <https://github.com/crim-ca/weaver/issues/230>`_).
- Add email notification support to the new ``subscribers`` definition (extension over `OGC` minimal requirements).
- Deprecate `Job` ``notification_email`` in the `OpenAPI` specification in favor of ``subscribers``, but preserve
  parsing of its value if provided in the `JSON` body during `Job` submission for backward compatibility support of
  existing servers. The ``Job.notification_email`` attribute is removed to avoid duplicate references.
- Add notification email for `Job` ``started`` status, only available through the ``subscribers`` property.
- Add `CLI` and ``WeaverClient`` options to support ``subscribers`` specification for submitted `Job` execution.
- Add ``{PROCESS_ID}/{STATUS}.mako`` template detection under the ``weaver.wps_email_notify_template_dir`` location
  to allow per-`Process` and per-`Job` status email customization.
- Refactor ``weaver/notify.py`` and ``weaver/processes/execution.py`` to avoid mixed references to the
  encryption/decryption logic employed for notification emails. All notifications including emails and
  callback requests are now completely handled and contained in the ``weaver/notify.py`` module.
- Remove partially duplicate Mako Template definition as hardcoded string and separate file for email notification.

Fixes:
------
- Fix inconsistent or missing schema references to updated `OGC` schema locations, and align their based URL locations
  for corresponding ``/conformance`` endpoint reporting.
- Fix auto-insertion of ``$schema`` and ``$id`` URI references into `JSON` schema and their data content representation.
  When in `OpenAPI` context, schemas now correctly report their ``$id`` as the reference schema they represent (usually
  from external `OGC` schema references), and ``$schema`` as the `JSON` meta-schema. When representing `JSON` data
  contents validated against a `JSON` schema, the ``$schema`` property is used instead to refer to that schema.
  All auto-insertions of these references can be enabled or disabled with options depending on what is more sensible
  for presenting results from various `API` responses.
- Fix ``weaver.cli`` logger not properly configured when executed from `CLI` causing log messages to not be reported.

.. _changes_4.33.0:

`4.33.0 <https://github.com/crim-ca/weaver/tree/4.33.0>`_ (2023-10-06)
========================================================================

Changes:
--------
- Add utility methods for `Job` to easily retrieve its various URLs.
- Add ``weaver.wps_email_notify_timeout`` setting (default 10s) to avoid SMTP server deadlock on failing connection.
- Modify the ``encrypt_email`` function to use an alternate strategy allowing ``decrypt_email`` on `Job` completed.
- Remove ``notification_email`` from ``GET /jobs`` query parameters.
  Due to the nature of the encryption strategy, this cannot be supported anymore.
- Add `CLI` ``execute`` options ``--output-public/-oP`` and ``--output-context/-oC OUTPUT_CONTEXT`` that add the
  specified ``X-WPS-Output-Context`` header to request the relevant output storage location of `Job` results.

Fixes:
------
- Fix `Job` submitted with a ``notification_email`` not reversible from its encrypted value to retrieve the original
  email on `Job` completion to send the notification (fixes `#568 <https://github.com/crim-ca/weaver/issues/568>`_).
- Fix example Mako Template for email notification using an unavailable property ``${logs}``.
  Instead, the new utility methods ``job.[...]_url`` should be used to retrieve relevant locations.

.. _changes_4.32.0:

`4.32.0 <https://github.com/crim-ca/weaver/tree/4.32.0>`_ (2023-09-25)
========================================================================

Changes:
--------
- Add ``GET /providers/{provider_id}/processes/{process_id}/package`` endpoint that allows retrieval of the `CWL`
  `Application Package` definition generated for the specific `Provider`'s `Process` definition.
- Add `CLI` ``package`` operation to request the remote `Provider` or local `Process` `CWL` `Application Package`.
- Add `CLI` output reporting of performed HTTP requests details when using the ``--debug/-d`` option.
- Modify default behavior of ``visibility`` field (under ``processDescription`` or ``processDescription.process``)
  to employ the expected functionality by native `OGC API - Processes` clients that do not support this option
  (i.e.: ``public`` by default), and to align resolution strategy with deployments by direct `CWL` payload which do not
  include this feature either. A `Process` deployment that desires to employ this feature (``visibility: private``) will
  have to provide the value explicitly, or update the deployed `Process` definition afterwards with the relevant
  ``PUT`` request. Since ``public`` will now be used by default, the `CLI` will not automatically inject the value
  in the payload anymore when omitted.
- Remove attribute ``WpsProcessInterface.stage_output_id_nested`` and enforce the behavior of nesting output by ID
  under corresponding directories for all remote `Process` execution when resolving `CWL` `Workflow` steps. This
  ensures a more consistent file and directory resolution between steps of different nature (`CWL`, `WPS`, `OGC` based)
  using multiple combinations of ``glob`` patterns and expected media-types.

Fixes:
------
- Fix missing Node.js requirement in built Docker image in order to evaluate definitions that employ
  `CWL` ``InlineJavascriptRequirement``, such as ``valueFrom`` employed for numeric ``Enum`` input type validation.
- Fix ``processes.wps_package.WpsPackage.make_inputs`` unable to parse multi-type `CWL` definitions due parsing
  as single-type element with ``parse_cwl_array_type``. Function ``get_cwl_io_type`` is used instead to resolve any
  `CWL` type combination properly.
- Fix ``get_cwl_io_type`` function that would modify the I/O definition passed as argument, which could lead to failing
  `CWL` ``class`` reference resolutions later on due to different ``type`` with ``org.w3id.cwl.cwl`` prefix simplified
  before ``cwltool`` had the chance to resolve them.
- Fix ``links`` listing duplicated in response from `Process` deployment.
  Links will only be listed within the returned ``processSummary`` to respect the `OGC API - Processes` schema.
- Fix `CLI` not removing embedded ``links`` in ``processSummary`` from ``deploy`` operation response
  when ``-nL``/``--no-links`` option is specified.
- Fix `CWL` definitions combining nested ``enum`` types as ``["null", <enum>, {type: array, items: <enum>]`` without an
  explicit ``name`` or ``SchemaDefRequirement`` causing failing ``schema_salad`` resolution under ``cwltool``. A patch
  is applied for the moment to inject a temporary ``name`` to let the `CWL` engine succeed schema validation (relates
  to `common-workflow-language/cwltool#1908 <https://github.com/common-workflow-language/cwltool/issues/1908>`_).

.. _changes_4.31.0:

`4.31.0 <https://github.com/crim-ca/weaver/tree/4.31.0>`_ (2023-09-14)
========================================================================

Changes:
--------
- Add the official `CWL` `JSON` schema reference
  (`common-workflow-language/cwl-v1.2#256 <https://github.com/common-workflow-language/cwl-v1.2/pull/256>`_)
  as ``$schema`` parameter returned in under the `OpenAPI` schema for the `CWL` component employed by `Weaver`
  (fixes `#547 <https://github.com/crim-ca/weaver/issues/547>`_).
- Add ``$schema`` field auto-insertion into the generated `OpenAPI` schema definition by ``CorniceSwagger`` when
  corresponding ``colander.SchemaNode`` definitions contain a ``_schema = "<URL>"`` attribute
  (fixes `#157 <https://github.com/crim-ca/weaver/issues/157>`_).
- Drop Python 3.6 support.

Fixes:
------
- Fix broken `OpenAPI` schema link references to `OGC API - Processes` repository.
- Fix ``GET /providers/{provider_id}`` response using ``$schema`` instead of ``$id`` to provide its content schema.
- Fix `Job` creation failing when submitting an empty string as input for a `Process` that allows it due
  to schema validation incorrectly preventing it.
- Fix human-readable `JSON`-like content cleanup to preserve sequences of quotes corresponding to valid empty strings.
- Fix `WPS` I/O ``integer`` literal data conversion to `OpenAPI` I/O ``schema`` definition injecting an
  invalid ``format: double`` property due to type checking with ``float`` succeeding against ``int`` values.
- Fix `CWL` I/O value validation for ``enum``-like definitions from corresponding `OpenAPI` and `WPS` I/O.
  Since `CWL` I/O do not allow ``Enum`` type for values other than basic ``string`` type, ``valueFrom`` attribute is
  used to handle ``int``, ``float`` and ``bool`` types, using an embedded JavaScript validation against allowed values.
  Because of this validation strategy, `CWL` packages must now include ``InlineJavascriptRequirement`` when allowed
  values for these basic types must be performed in order for the `CWL` engine to parse I/O contents of ``valueFrom``
  (relates to `cwl-v1.2#267 <https://github.com/common-workflow-language/cwl-v1.2/issues/267>`_,
  `common-workflow-language#764 <https://github.com/common-workflow-language/common-workflow-language/issues/764>`_ and
  `common-workflow-language#907 <https://github.com/common-workflow-language/common-workflow-language/issues/907>`_).
- Fix typing definitions for certain ``Literal`` references for proper resolution involving values stored in constants.
- Fix ``get_sane_name`` checks performed on `Process` ID and `Service` name to use ``min_len=1`` in order to allow
  valid `WPS` process definition on existing servers to resolve references that are shorter than the previous default
  of 3 characters.

.. _changes_4.30.1:

`4.30.1 <https://github.com/crim-ca/weaver/tree/4.30.1>`_ (2023-07-07)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix broken Docker build of ``weaver-worker`` image due to unresolved ``docker-ce-cli`` package.
  Installation is updated according to the reference documentation (https://docs.docker.com/engine/install/debian/).
- Fix incorrect stream reader type (``bytes`` instead of ``str``) for some handlers in ``open_module_resource_file``.
- Fix invalid ``jsonschema.validators.RefResolver`` reference in ``jsonschema>=4.18.0`` caused by refactor
  (see https://github.com/python-jsonschema/jsonschema/blob/main/CHANGELOG.rst#v4180,
  https://python-jsonschema.readthedocs.io/en/v4.18.0/api/jsonschema/validators/#jsonschema.validators._RefResolver
  and `python-jsonschema/jsonschema#1049 <https://github.com/python-jsonschema/jsonschema/pull/1049>`_).
- Fix multiple linting checks, documentation dependencies and link references.

.. _changes_4.30.0:

`4.30.0 <https://github.com/crim-ca/weaver/tree/4.30.0>`_ (2023-03-24)
========================================================================

Changes:
--------
- Add ``weaver.quotation = true|false`` setting that allows control over the activation of all endpoints and operations
  related to the `OGC API - Processes` |ogc-proc-ext-billing-short|_ and |ogc-proc-ext-quotation-short|_ extensions.
- Add support to configure a quotation estimation algorithm for each respective `Process` with new requests
  using ``GET``, ``PUT``, ``DELETE`` methods on ``/processes/{processID}/estimator`` endpoint. The configured
  algorithm is provided by a reference `Docker` image defined by ``weaver.quotation_docker_[...]`` settings.
  The algorithm itself expects a highly customizable configuration to estimate quotation parameters based on
  conceptual categories, as defined by the |quote-estimator-config|_ schema optionally using versatile `ONNX`_
  definitions. The `Docker` operation should return a JSON matching the |quote-estimation-result|_ schema, which is
  parsed and included in the produced `Quote` based on provided `Process` execution parameters.
- Add `Process` execution I/O pre-validation against the `Process` description before submitting the `Job` to avoid
  unnecessary allocation of computing resources for erroneous cases that can easily be detected in advance.
- Add ``$schema`` references to source `OGC API - Processes` or other schema registries for applicable content
  definitions in responses.
- Add missing `OGC API - Processes` schema references with published definitions
  under ``https://schemas.opengis.net/ogcapi/processes/part1/1.0/`` when applicable.
- Add ``links`` request query parameter to ``/processes`` and ``/providers/{providerID}/processes`` listing to
  provide control over reporting of ``links`` for each `Process` summary item. By default, ``link=true`` and
  automatically disable it when ``detail=false`` is specified.
- Add missing ``405`` response schema for all `OpenAPI` endpoints as handled by the API when the requested HTTP method
  is not applicable for the given path.
- Renamed ``weaver.quote_sync_max_wait`` to ``weaver.quotation_sync_max_wait`` to better align with new configuration
  settings for the |ogc-proc-ext-quotation-short| extension. Old value will still be checked for backward compatibility.
- Renamed ``weaver.exec_sync_max_wait`` to ``weaver.execute_sync_max_wait`` to better align with the corresponding
  parameter for quotation. Old value will still be checked for backward compatibility.
- Add ``Lazify`` utility class for holding a string with delayed computation and caching that returns its representation
  on-demand during formatting or other string operations to reduce the impact of its long generation. This can be used
  with a callable returning a string representation that can be discarded without invocation on inactive logging levels.
- Add ``count`` field to `JSON` output of endpoints that support paging to provide the number of items returned within
  the paged result. Adjust the ``/quotations`` endpoint that was using it instead of ``total`` like it was done on other
  listing endpoints.
- Add ``detail`` query parameter for the ``/quotations`` endpoint to allow listing of `Quote` summary details instead
  of only IDs by default, similarly to the ``/jobs`` endpoint.

.. |ogc-proc-ext-billing-short| replace:: Billing
.. _ogc-proc-ext-billing-short: https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/billing
.. |ogc-proc-ext-quotation-short| replace:: Quotation
.. _ogc-proc-ext-quotation-short: https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/quotation
.. |quote-estimator-config| replace:: *Quote Estimator Configuration*
.. _quote-estimator-config: weaver/schemas/quotation/quote-estimator.yaml
.. |quote-estimation-result| replace:: *Quote Estimation Result*
.. _quote-estimation-result: weaver/schemas/quotation/quote-estimation-result.yaml
.. _ONNX: https://onnx.ai/

Fixes:
------
- Fix schema meta fields (``title``, ``summary``, ``description``, etc.) not being rendered in `OpenAPI` output for
  keyword schemas (``allOf``, ``anyOf``, ``oneOf``, ``not``).
- Fix schema definitions not being rendered in `OpenAPI` into the requested order
  by ``_sort_first`` and ``_sort_after`` control attributes.
- Fix request cache always invalidated when no explicit ``allowed_codes`` where provided in ``request_extra``, although
  the request succeeded, causing caching optimization to never actually be used on following requests in this case.
- Fix cached requests misbehaving when combined with ``stream=True`` argument due to contents not being stored in the
  object for following requests, causing them to raise ``StreamConsumedError`` when calling the chunk iterator again.
- Fix execution payloads for functional tests using ``WorkflowRESTScatterCopyNetCDF``, ``WorkflowRESTSelectCopyNetCDF``,
  ``WorkflowWPS1ScatterCopyNetCDF`` and``WorkflowWPS1SelectCopyNetCDF`` processes, which requested invalid output
  identifiers. Those erroneous definitions were detected using the new `Process` execution I/O pre-validation against
  the corresponding `Process` descriptions on `Job` submission.

.. _changes_4.29.0:

`4.29.0 <https://github.com/crim-ca/weaver/tree/4.29.0>`_ (2023-03-07)
========================================================================

Changes:
--------
- Replace deprecated ``best_match`` methods for ``Accept`` and ``Accept-Language`` HTTP headers by their respective
  implementation with ``acceptable_offers`` and ``lookup`` methods better aligned with :rfc:`7231` specification.

Fixes:
------
- Fix missing ``sphinx_autodoc_typehints[type_comment]`` extras due to renamed definition without leading ``s`` by
  pinning ``1.19`` as the minimum version
  (relates to `tox-dev/sphinx-autodoc-typehints#263 <https://github.com/tox-dev/sphinx-autodoc-typehints/issues/263>`_).
- Fix dynamic regex definitions for schema validation with ``colander>=2`` that modifies ``URL_REGEX`` pattern
  (relates to `Pylons/colander#352 <https://github.com/Pylons/colander/pull/352>`_).
- Fix invalid default results from ``colander`` schemas with ``missing=drop|required`` and ``default`` parameters when
  combined with ``cornice`` OpenAPI schemas. Pin ``colander<2`` to avoid problems with latest changes.
- Fix ``secure_filename`` causing valid names with leading or trailing underscores to be incorrectly unresolved
  because they get stripped out by the operation.
- Fix ``input-location`` definition for ``PACKAGE_DIRECTORY_TYPE`` input in
  ``weaver.processes.wps_package.WpsPackage.make_location_input``, which caused the wrong directory being given to
  the `CWL` application.
- Fix ``http`` directory download to match implemented `AWS S3` directory download in ``weaver.utils.fetch_directory``,
  so both types replicate the input directory's top level folder, which is necessary when downloading
  multiple directories for the same input source.
- Fix deprecation warnings from ``webob`` and ``owslib``.
- Fix filtered warnings for expected cases during tests.
- Fix a problem with ``convert_input_values_schema`` under the `OGC` schema, that caused the conversion to malfunction
  when the function built lists for repeated input IDs of more than two elements.
- Fix `XML` security vulnerability from ``owslib<0.28.1``.

.. _changes_4.28.0:

`4.28.0 <https://github.com/crim-ca/weaver/tree/4.28.0>`_ (2022-12-06)
========================================================================

Changes:
--------
- Update Docker images to use more recent Python 3.10 by default instead of Python 3.7.
  All CI pipeline, tests and validation checks are also performed with Python 3.10.
  Unit and functional tests remain evaluated for all Python versions since 3.6 (legacy) up to 3.11 (experimental).
- Update to latest ``cwltool==3.1.20221201130942`` to provide ``v1.2`` extension definitions.
- Add `CWL` extensions activation for specific features supported by `Weaver` for more adequate schema validation.
- Add `Job` log message size checks to better control what gets logged during the `Application Package` execution to
  avoid large documents causing problems when attempting save them to storage database.
- Update documentation with examples for ``cwltool:CUDARequirement``, ``ResourceRequirement`` and ``NetworkAccess``.
- Improve schema definition of ``ResourceRequirement``.
- Deprecate ``DockerGpuRequirement``, with attempts to auto-convert it into corresponding ``DockerRequirement``
  combined with  ``cwltool:CUDARequirement`` definitions. If this conversion does not work transparently for the user,
  explicit `CWL` updates with those definitions should be made.
- Ensure that validation check finds exactly one provided `CWL` requirement or hint to represent the application type.
  In case of missing requirement, the `Process` deployment will fail with a reported error that contains a documentation
  link to guide the user in adjusting its `Application Package` accordingly.

Fixes:
------
- Fix CI failing setup of Python 3.6 not available on Ubuntu 22.04 (latest).
- Fix ``distutils.version.LooseVersion`` marked for deprecation for upcoming versions.
  Use ``packaging.version.Version`` substitute whenever possible, but preserve backward
  compatibility with ``distutils`` in case of older Python not supporting it.
- Fix ``cli._update_files`` so there are no attempts to upload remote references to the `Vault`.

.. _changes_4.27.0:

`4.27.0 <https://github.com/crim-ca/weaver/tree/4.27.0>`_ (2022-11-22)
========================================================================

Changes:
--------
- Support `CWL` ``InlineJavascriptRequirement`` for `Process` deployment to allow successful schema validation.
- Support `CWL` ``Directory`` type references (resolves `#466 <https://github.com/crim-ca/weaver/issues/466>`_).
  Those references correspond to `WPS` and `OGC API - Processes` ``href``
  using the ``Content-Type: application/directory`` Media-Type and must hava a trailing slash (``/``) character.
- Support `S3` file or directory references using *Access Point*, *Virtual-hosted–style* and *Outposts* URLs
  (see AWS documentation
  `Methods for accessing a bucket <https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-bucket-intro.html>`_).
- Apply more validation rules against expected `S3` file or directory reference formats.
- Update documentation regarding handling of `S3` references (more formats supported) and ``Directory`` type references.
- Support ``weaver.wps_output_context`` setting and ``X-WPS-Output-Context`` request header resolution in combination
  with `S3` bucket location employed for storing `Job` outputs.
- Nest every complex `Job` output (regardless if stored on local `WPS` outputs or on `S3`, and whether the output is
  of ``File`` or ``Directory`` type) under its corresponding output ID collected from the `Process` definition to avoid
  potential name conflicts in storage location, especially in the case of multiple output IDs that could be aggregated
  with various files and listing of directory contents.
- Allow ``colander.SchemaNode`` (with extensions for `OpenAPI` schema converters) to provide validation ``pattern``
  field directly with a compiled ``re.Pattern`` object.
- Support `CWL` definition for ``cwltool:CUDARequirement`` to request the use of a GPU, including support for using
  Docker with a GPU (resolves `#104 <https://github.com/crim-ca/weaver/issues/104>`_).
- Support `CWL` definition for ``NetworkAccess`` to indicate whether a process requires outgoing IPv4/IPv6 network
  access.

Fixes:
------
- Fix ``cli._update_files`` so there are no attempts to upload remote references to the vault.

.. _changes_4.26.0:

`4.26.0 <https://github.com/crim-ca/weaver/tree/4.26.0>`_ (2022-10-31)
========================================================================

Changes:
--------
- Add more explicit ``PackageException`` error messages with contextual details when a `CWL` file reference cannot be
  resolved correctly.
- Return ``Content-Type: application/vnd.oai.openapi+json; version=3.0`` for OpenAPI endpoint response referenced
  by ``service-desc`` in the API conformance details, as specified by
  `OGC API - Processes - OpenAPI 3.0 requirement class <https://docs.ogc.org/is/18-062r2/18-062r2.html#toc43>`_.
- Support the generation of external schema references (``$ref``) using the ``schema_ref`` attribute if provided
  in a ``colander.SchemaNode`` that does not provide an explicit object schema definition with properties.
- Add Python typing definitions related to OpenAPI specification.
- Add more validation of request arguments for improved security.

Fixes:
------
- Fix invalid generation of OpenAPI 3.0 specification for `Weaver` API using ``cornice_swagger``.
  The generated schema structure used to return a mix of Swagger 2.0 and OpenAPI 3.0 definitions.
  The provided contents are now defined completely with OpenAPI 3.0 specification format.
- Remove hard requirement ``shapely==1.8.2`` to obtain latest fixes.
- Update ``json2xml>=3.20.0`` requirement to allow more recent ``certifi``, ``requests`` and ``urllib3`` dependencies to
  be used by all packages (relates to `vinitkumar/json2xml#157 <https://github.com/vinitkumar/json2xml/issues/157>`_).
- Fix resolution of `CWL` file from references that do not provide a known ``Content-Type`` that can represent `CWL`
  contents. This can occur when deploying a ``builtin`` `Process` from the local file reference, which does not generate
  a request and, therefore, no ``Content-Type``. This can occur also for servers that incorrectly or simply do not
  report their response ``Content-Type`` header.
- Fix resolution of file reference with explicit `CWL` or `YAML` extensions when ``Content-Type`` is not reported or is
  indicated as ``plain/text``.
- Fix invalid resolution of ``builtin`` `Process` that could load the optional `JSON` or `YAML` payload file intended
  to provide additional `Process` definition details, instead of the expected `CWL` for the package definition.
- Fix ``kombu`` package requirement to employ ``celery>=5.2`` with ``pymongo>=4``
  (fixes `#386 <https://github.com/crim-ca/weaver/issues/386>`_,
  relates to `celery/celery#7834 <https://github.com/celery/celery/pull/7834>`_,
  relates to `celery/kombu#1536 <https://github.com/celery/kombu/pull/1536>`_).
- Fix deprecated ``Cursor.count()`` call for ``Quote`` and ``Bill`` search with ``pymongo>=4``.
- Fix unsupported `Process`-related queries including a tagged version when searching for `Job` items.

.. _changes_4.25.0:

`4.25.0 <https://github.com/crim-ca/weaver/tree/4.25.0>`_ (2022-10-05)
========================================================================

Changes:
--------
- Refactor ``weaver.processes.wps_workflow`` definitions to delegate implementation to ``cwltool`` core classes,
  removing code duplication and allowing update to latest revisions
  (resolves `#154 <https://github.com/crim-ca/weaver/issues/154>`_).

Fixes:
------
- No change.

.. _changes_4.24.0:

`4.24.0 <https://github.com/crim-ca/weaver/tree/4.24.0>`_ (2022-09-29)
========================================================================

Changes:
--------
- Support deployment of a local `Process` using a remote `OGC API - Processes` reference
  (resolves `#11 <https://github.com/crim-ca/weaver/issues/11>`_).
- Support `CWL` definition for ``ScatterFeatureRequirement`` for `Workflow` parallel step distribution of an
  input array (resolves `#105 <https://github.com/crim-ca/weaver/issues/105>`_
  and relates to `#462 <https://github.com/crim-ca/weaver/issues/462>`_).
- Add formatter and better logging details when executing ``builtin`` `Process` ``jsonarray2netcdf``.
- Add `OGC` Media-Type ontology for ``File`` format references within `CWL` definition.
- Replace `EDAM` NetCDF format reference by `OGC` NetCDF Media-Type with expected ontology definitions by processes
  For backward compatibility, corresponding `EDAM` references will be converted to `OGC` Media-Type whenever possible.
- Adjust ``builtin`` process ``jsonarray2netcdf`` (version ``2.0``) to employ `OGC` Media-Type for NetCDF.
- Adjust ``schema`` input of ``jsonarray2netcdf`` to avoid erroneous definition exposing a JSON ``object`` structure
  as a valid format, although a JSON ``array`` type is directly expected in the submitted JSON file.
- Add support of ``builtin`` `Process` description overrides if provided along their `CWL` package definition.
  Overrides can be specified as JSON or YAML, and follow the same merging strategies of fields as normal deployments.
- Refactor ``weaver.processes.wps_[...]`` definitions to reuse operations for communicating with `OGC API - Processes`
  servers across implementation for monitored `Job` with a remote `Process` type of `OGC API`, `ADES` and `Workflow`
  with other step `Process` references.

Fixes:
------
- Fix implementation of various functional test cases for `Workflow` execution.
- Fix ``owslib`` version with enforced ``pyproj`` dependency failing in Python 3.10
  (resolves `#459 <https://github.com/crim-ca/weaver/issues/459>`_).

.. _changes_4.23.0:

`4.23.0 <https://github.com/crim-ca/weaver/tree/4.23.0>`_ (2022-09-12)
========================================================================

Changes:
--------
- Add `CLI` and `WeaverClient` support of ``logs``, ``exceptions`` and ``statistics`` retrieval.
- Add `CLI` and `WeaverClient` support of `Job` search filtered by ``tags``, ``process`` and ``providers`` queries.
- Add `CLI`, `WeaverClient` and `API` support of `Job` search filtered by multiple ``status`` values.
- Adjust OpenAPI schema definitions for `Process` deployment to allow ``owsContext`` by itself without duplicated
  information that was required by mandatory ``executionUnit`` definition.

Fixes:
------
- Fix ``tags`` query parameter not applied to filter `Job` search requests.
- Fix implementation of functional ``DockerRequirement`` test cases for `Process` deployment when references are
  provided by ``href`` within the ``executionUnit`` or ``owsContext``
  (relates to `#11 <https://github.com/crim-ca/weaver/issues/11>`_).
- Fix ``weaver.wps_output_context`` sub-directory resolved from default settings or ``X-WPS-Output-Context`` request
  header not employed for storing the `XML` status location and `Job` log files next to the `Job` outputs directory.

.. _changes_4.22.0:

`4.22.0 <https://github.com/crim-ca/weaver/tree/4.22.0>`_ (2022-08-18)
========================================================================

Changes:
--------
- Add `WPS` remote `Provider` retry conditions to handle known problematic cases during `Process` execution (on remote)
  that can lead to sporadic failures of the monitored `Job`. When possible, retried submission leading to successful
  execution will result in the monitored `Job` to complete successfully and transparently to the user. Relevant errors
  and retry attempts are provided in the `Job` logs.
- Add `WPS` remote `Provider` status exception response as `XML` message from the failed remote execution within the
  monitored local `Job` logs to help users understand how to resolve any encountered issue on the remote service.

Fixes:
------
- Bump version ``OWSLib==0.26.0`` to fix ``processVersion`` attribute resolution from `WPS` remote `Provider` definition
  to populate ``Process.version`` property employed in converted `Process` description to `OGC API - Process` schema
  (relates to `geopython/OWSLib#794 <https://github.com/geopython/OWSLib/pull/794>`_).
- Fixes and improvements for typing definitions.

.. _changes_4.21.0:

`4.21.0 <https://github.com/crim-ca/weaver/tree/4.21.0>`_ (2022-08-15)
========================================================================

Changes:
--------
- Add `CLI` support for `Process` listing, `Job` execution, service registration and un-registration in the context
  of a `Process` offered by a remote `Provider` reference.
- Add `CLI` options for `Process` listing with detailed descriptions, paging, limit and sorting queries.
- Add `CLI` options for HTTP request timeout and retry control when required for specific use cases.
  For example, a `Weaver` instance with many registered `Provider` references could take longer than default
  timeout of 5s to populate the full list of remotely accessible processes retrieved from each `WPS` service.
- Add `CLI` output of most recently retrieved `Job` status during ``execute`` operation in combination of monitoring
  flag to report the produced `Job` reference ID and URL in case monitoring timeout is reached before its completion.
- Add support of `XML` content for `Process` description response from the REST API endpoint based on the `WPS`
  definition when any query between ``schema=WPS``, ``f=xml``, ``format=xml`` or the ``Accept`` header referring
  to `XML` Media-Type is identified in the request (resolves `#125 <https://github.com/crim-ca/weaver/issues/125>`_).
- Add support of ``f`` and ``format`` query parameters to describe a `Process` with `JSON` when requested from
  the `WPS` endpoint with redirect to REST API URL (resolves `#125 <https://github.com/crim-ca/weaver/issues/125>`_).
- Add support of `Job` submission with `WPS`-like `XML` content and HTTP ``POST`` request directly submitted through
  the `OGC APi - Processes` REST endpoint. Response is returned in `JSON` regardless of `WPS`-like `Job` submission
  in order to provide the status response (resolves `#125 <https://github.com/crim-ca/weaver/issues/125>`_).

Fixes:
------
- Fix invalid ``POST /providers/{provider_id}/processes/{process_id}/execution`` endpoint that was missing
  the `Process` portion to mimic the `OGC API - Processes` execution endpoint of a `Job` for a remote `Provider`.
- Fix result file names resolution for staging outputs retrieved from the `Job` execution on a remote `Provider` where
  the `Process` outputs files are not generated using the same glob naming convention as expected by the `CWL` outputs
  of the corresponding `Process`.
- Fix `Job` submission response generation potentially duplicating ``Content-Type`` and ``Content-Length`` headers.

.. _changes_4.20.0:

`4.20.0 <https://github.com/crim-ca/weaver/tree/4.20.0>`_ (2022-07-15)
========================================================================

Changes:
--------
- Add support of `Process` revisions (resolves `#107 <https://github.com/crim-ca/weaver/issues/107>`_).
- Add ``PATCH /processes/{processID}`` request, allowing ``MINOR`` and ``PATCH`` level modifications that can be
  applied to an existing `Process` in order to revise non-execution critical information. Level ``PATCH`` is used to
  identify changes with no impact on execution whatsoever, only affecting metadata such as its documented description.
  Level ``MINOR`` is used to update components that affect only execution *methodology* (e.g.: sync/async) or `Process`
  retrieval, but that do not directly impact *what* is executed (i.e.: the `Application Package` does not change).
- Add ``PUT /processes/{processID}`` request, allowing ``MAJOR`` revision to essentially redeploy a new `Process`,
  but leaving some form of relationship with older versions by reusing the same `Process` ID. This ``MAJOR`` update
  level implies a relatively critical change to execute the `Process`, such as the addition, removal or modification
  of an input or output, directly impacting the `Application Package` definition and parameters the `Process` offers.
- Add support of ``{processID}:{version}`` representation in request path and ``processID`` of the `Job` definition
  to reference the specific `Process` revisions when fetching a `Process` description or a `Job` status.
- Add search query ``version`` and ``revisions`` parameters to allow description of a specific `Process` revision, or
  listing all its versions history.
- Add more entries in ``links`` referring to `Process` revisions whenever applicable.

Fixes:
------
- Fix `CLI` not allowing expected combination of ``--username`` and ``--password`` for Docker authentication when
  deploying a `Process` that needs it to retrieve the referenced repository and image in its `CWL` definition.
- Fix invalid ``minimum`` and ``maximum`` OpenAPI fields that were defined as ``minLength`` and ``maxLength``
  (duplicates definitions) for `Process` description and deployment schema validation.

.. _changes_4.19.0:

`4.19.0 <https://github.com/crim-ca/weaver/tree/4.19.0>`_ (2022-07-05)
========================================================================

Changes:
--------
- Add support of official `CWL` IANA types to allow `Process` deployment with the relevant ``Content-Type`` header
  for the submitted payload (see `common-workflow-language/common-workflow-language#421 (comment)
  <https://github.com/common-workflow-language/common-workflow-language/issues/421#issuecomment-1122010820>`_,
  relates to `opengeospatial/NamingAuthority#169 <https://github.com/opengeospatial/NamingAuthority/issues/169>`_,
  resolves `#434 <https://github.com/crim-ca/weaver/issues/434>`_).
- Support `Process` deployment using only `CWL` content provided it contains an ``id`` field representing the target
  `Process` ID as per recommendation in `OGC Best Practice for Earth Observation Application Package, CWL Document
  <https://docs.ogc.org/bp/20-089r1.html#toc26>`_ (resolves `#434 <https://github.com/crim-ca/weaver/issues/434>`_).
- Support `Process` deployment with a payload using ``YAML`` content instead of ``JSON``. This ``YAML`` content
  **MUST** be submitted in the request with a ``Content-Type`` header either equal to ``application/x-yaml`` or
  ``application/ogcapppkg+yaml`` for the |ogc-app-pkg|_ schema, or using ``application/cwl+yaml`` for
  a `CWL`-only definition. The definition will be loaded and converted to ``JSON`` for schema validation. Otherwise,
  ``JSON`` contents is assumed to be directly provided in the request payload for validation as previously accomplished.
- Add partial support of `CWL` with ``$graph`` representation for the special case where the graph is composed of a list
  of exactly one `Application Package`. Multi/nested-`CWL` definitions are **NOT** supported
  (relates to `#56 <https://github.com/crim-ca/weaver/issues/56>`_).
- Add ``weaver.cwl_processes_dir`` configuration setting for preloading, registering or updating a set of
  known `Process` definitions from `CWL` files stored in a nested directory structure. This allows a service provider
  that uses `Weaver` to offer their `Processes` to directly maintain their definitions from the set of `CWL` files and
  upload changes in the web application at startup without need to manually undeploy and redeploy each `Process`.
- Add ``weaver.cwl_processes_register_error`` to fail fast any `Process` registration error from `CWL` when loading
  files at startup.

Fixes:
------
- Fix `Process` deployment using a `WPS-1/2` URL reference defining a ``GetCapabilities`` request to resolve
  the corresponding ``DescribeProcess`` request if the `Process` ID can be inferred from other known locations
  (relates to `#11 <https://github.com/crim-ca/weaver/issues/11>`_).
- Move ``WpsPackage`` properties to instance level to avoid potential referencing of attributes across same class
  used by distinct running `Process`.

.. _changes_4.18.0:

`4.18.0 <https://github.com/crim-ca/weaver/tree/4.18.0>`_ (2022-06-09)
========================================================================

Changes:
--------
- Add `CLI` *Authentication Handler* parameters and corresponding ``auth`` argument of instantiated classes for
  ``WeaverClient`` methods that allows inline request authentication and authorization resolution to access a
  protected service. Any *Authentication Handler* implementation can be used to fulfill required server functionalities.
- Add `CLI` handling of uncaught exceptions to gracefully report message and error instead of exception traceback.
- Replaced `CLI` option ``-t`` by ``-T`` (`Docker` token) during ``deploy`` operation to match naming convention of
  other options (resolves `#400 <https://github.com/crim-ca/weaver/issues/400>`_).
- Replaced `CLI` option ``-H`` by ``nH`` (``--no-headers``) and ``wH`` (``--with-headers``) to respectively
  enable or (explicitly) disable return of headers from response of the executed operation.
- Replaced `CLI` option ``-L`` by ``nL`` (``--no-links``) and ``wL`` (``--with-links``) to respectively
  enable (explicitly) or disable return of links from response of the executed operation.
- Replaced previously defined ``-H`` option by new ``-H/--header`` argument allowing insertion of explicitly provided
  request headers for relevant requests called by the executed operation.
- Add case insensitive support of values for common `API`, `CLI`, and ``WeaverClient`` parameter choices.
- Add all missing `CLI` and ``WeaverClient`` examples in the documentation.

Fixes:
------
- Fix ``Process.payload`` improperly encoded in case of special characters where allowed such as in `CWL` definition.
- Fix `CLI` operations assuming valid JSON response to instead return error response content and status code.
- Fix `CLI` rendering of various optional arguments and groups when displaying help messages.
- Fix invalid handling of ``Constants`` definitions mixed with ``classproperty`` such as in ``OutputFormat`` causing
  returned value to be the ``classproperty`` itself instead of the retrieved value from its getter definition.
- Fix minor typing definitions that were incorrect.

.. _changes_4.17.0:

`4.17.0 <https://github.com/crim-ca/weaver/tree/4.17.0>`_ (2022-05-30)
========================================================================

Changes:
--------
- Add statistics collection at the end of `Job` execution to obtain used memory from ``celery`` process and spaced
  used by produced results.
- Add ``/jobs/{jobID}/statistics`` endpoint (and corresponding locations for ``/providers`` and ``/processes``) to
  report any collected statistics following a `Job` execution.

Fixes:
------
- Fix `Job` ``Location`` header injected twice in ``get_job_submission_response`` causing header to have comma-separated
  list of URI values failing retrieval by `CLI` when attempting to perform auto-monitoring of the submitted `Job`.
- Fix `CWL` runtime context setup to return monitored maximum RAM used by application under the `Process` if possible.
- Fix failing `Service` provider summary response in case of unresponsive (not accessible or parsable) URL endpoint
  contents due to different errors raised by distinct versions of ``requests`` package.

.. _changes_4.16.1:

`4.16.1 <https://github.com/crim-ca/weaver/tree/4.16.1>`_ (2022-05-12)
========================================================================

Changes:
--------
- Add `OpenGIS <https://defs.opengis.net/vocprez/object?uri=http://www.opengis.net/def/glossary>`_ as a potential
  namespace resolver for common geospatial Media-Types such as ``image/tiff; subtype=geotiff`` that must be
  distinguished from generic IANA formats.

Fixes:
------
- Fix invalid interpretation of stored `Process` I/O with ``schema`` with Media-Type reference not representing a
  pre-resolved OpenAPI schema object, but rather an expected URI ``contentSchema`` reference for *default* format.
- Fix `CLI` combination of user-provided `Process` description and inserted `Process` ID by option argument considering
  alternative ``OGC``/``OLD`` representations.
- Fix `OAS` ``format`` field dropped for literal type when resolving ``schema`` provided during `Process` deployment.
- Fix Media-Type resolution dropping important sub-type parameters to distinguish between specific
  type context (e.g. ``image/tiff`` vs ``image/tiff; subtype=geotiff``).

.. _changes_4.16.0:

`4.16.0 <https://github.com/crim-ca/weaver/tree/4.16.0>`_ (2022-05-11)
========================================================================

Changes:
--------
- Add support of OpenAPI ``schema`` field for I/O definitions within `Process` description responses as required
  by `OGC API - Processes` specification (resolves `#245 <https://github.com/crim-ca/weaver/issues/245>`_).
  Existing and deployed processes using legacy I/O definitions will be parsed for corresponding fields employed in
  OpenAPI to generate the missing ``schema`` field. Inversely, processes directly deployed with ``schema`` definitions
  are ported back to legacy I/O representation by padding them with corresponding fields. Conversion between the
  two representations is unidirectional according to whether ``schema`` is specified or not. Nevertheless, the final
  I/O definitions can try to make use of both representations simultaneously and in combination with I/O definitions
  extracted from the `CWL Application Package` to resolve additional details during I/O merging strategy.
- Add support of ``Accept`` header, ``f`` and ``format`` request queries for ``GET /jobs/{jobID}/logs`` retrieval
  using ``text``, ``json``, ``yaml`` and ``xml`` (and their corresponding Media-Type definitions) to list `Job` logs.
- Add partial support of literals with unit of measure (``UoM``) specified during `Process` deployment using the
  I/O ``schema`` field (relates to `#430 <https://github.com/crim-ca/weaver/issues/430>`_).
- Add partial support of bounding box parsing specified during `Process` deployment using the
  I/O ``schema`` field (relates to `#51 <https://github.com/crim-ca/weaver/issues/51>`_).
- Add encoding/decoding of JSON I/O definitions for saving to database in order to support OpenAPI ``schema`` that can
  contain conflicting key names with MongoDB functionalities (e.g.: ``$ref``).
- Add parsing of `CLI` inputs with ``@parameter=value`` additional properties to be passed for the `Process`
  execution. This can be used for specifying the ``mediaType`` and ``encoding`` of a ``File`` reference input.
- Remove ``deploymentProfileName`` requirement during `Process` deployment. The corresponding ``deploymentProfile``
  property is instead automatically generated from resolved `CWL` package/reference or remote `WPS` reference. This
  further simplifies deployment using the `CLI` to its bare minimum components as only the `CWL` or `WPS` reference
  needs to be provided along the desired `Process` ID without any further details.

Fixes:
------
- Remove ``VaultReference`` from ``ReferenceURL`` schema employed to reference external resources that are not intended
  to be used with temporary `Vault` definitions. Only inputs for `Process` execution will allow `Vault` references.
- Fix ``LiteralOutput`` creation not removing ``allowed_values`` not available with `PyWPS` class.
- Fix failing `Process` deployment caused by ``links`` if explicitly specified in the payload by the user.
  Additional links that don't conflict with dynamically generated ones are added to the deployed `Process` definition.
- Fix missing ``deploymentProfile`` property in `Process` description
  (resolves `#319 <https://github.com/crim-ca/weaver/issues/319>`_).

.. _changes_4.15.0:

`4.15.0 <https://github.com/crim-ca/weaver/tree/4.15.0>`_ (2022-04-20)
========================================================================

Important:
----------
- In order to support *synchronous* execution, setting ``RESULT_BACKEND`` **MUST** be specified in
  the ``weaver.ini`` configuration file.
  See `Weaver INI Configuration Example <https://github.com/crim-ca/weaver/blob/master/config/weaver.ini.example>`_
  in section ``[celery]`` for more details.
- With resolution and added support of ``transmissionMode`` handling according to `OGC API - Processes` specification,
  requests that where submitted with ``reference`` outputs will produce results in a different format than previously
  since this parameter was ignored and always returned ``value`` representation.
- Due to ``celery>=5.2`` migration, any call to ``celery`` `CLI` must be updated accordingly by moving the global
  options before the *mode*, namely ``worker``, ``inspect`` and so on. Specifically for `Weaver`, this means
  the ``weaver-worker`` command line option `-A` must be moved *before* ``worker`` as follows:

  .. code-block:: shell

    celery -A pyramid_celery.celery_app worker -B -E --ini weaver.ini [...]

Changes:
--------
- Support ``Prefer`` header with ``wait`` or ``respond-async`` directives to select ``Job`` execution mode either
  as *synchronous* or *asynchronous* task, according to supported ``jobControlOptions`` of the relevant ``Process``
  being executed (resolves `#247 <https://github.com/crim-ca/weaver/issues/247>`_).
- Increase minor version of all ``builtin`` processes that will now be executable in wither (a)synchronous modes.
- Add ``weaver.exec_sync_max_wait`` and ``weaver.quote_sync_max_wait`` settings allowing custom definition for the
  maximum duration that can be specified to wait for a `synchronous` response from task workers.
- Add ``-B`` (``celery beat``) option to Docker command of ``weaver-worker`` to run scheduled task in parallel
  to ``celery worker`` in order to periodically cleanup task results introduced by *synchronous* execution.
- Add support of ``transmissionMode`` handling as ``reference`` to generate HTTP ``Link`` references for results
  requested this way (resolves `#377 <https://github.com/crim-ca/weaver/issues/377>`_).
- Updated every ``Process`` to report that they support ``outputTransmission`` both as ``reference`` and ``value``,
  since handling of results is accomplished by `Weaver` itself, regardless of the application being executed.
- Add partial support of ``response=raw`` parameter for execution request submission in order to handle results to
  be returned accordingly to specified ``outputTransmission`` by ``reference`` or ``value``.
  Multipart contents for multi-output results are not yet supported
  (relates to `#376 <https://github.com/crim-ca/weaver/issues/376>`_).
- Add `CLI` option ``-R/--ref/--reference`` for ``execute`` operation allowing to request corresponding ``outputs``
  by ID to be returned using the ``transmissionMode: reference`` method, producing HTTP ``Link`` headers for those
  entries rather than inserting values in the response content body.
- Add requested ``outputs`` into response of ``GET /jobs/{jobId}/inputs`` to obtain submitted ``Job`` definitions.
- Add query parameter ``schema`` for ``GET /jobs/{jobId}/inputs`` (and corresponding endpoints under ``/processes``
  and ``/providers``) allowing to retrieve submitted input values and requested outputs with either ``OGC``/``OLD``
  formats.
- Improve conformance for returned status codes and error messages when requesting results for an unfinished,
  failed, or dismissed ``Job``.
- Adjust conformance item references to correspond with `OGC API - Processes: Part 2` renamed from `Transactions` to
  `Deploy, Replace, Undeploy`.
- Add ``mutable`` field to ``Process`` summary listing and detailed descriptions for conformance
  (resolves `#180 <https://github.com/crim-ca/weaver/issues/180>`_).
- Improve ``Process`` undeployment to consider running ``Job`` to block its removal while in use.
- Add ``category`` query parameter to ``/conformance`` endpoint allowing to filter items
  by ``conf`` (conformance), ``rec`` (recommendation), ``req`` (requirement), ``per`` (permission) or ``all``
  references. By default, return the ``conf`` representation which is the expected definitions by `OGC API`
  conformance validators.
- Add multiple conformance items related to `CWL`
  and `OGC Best Practice for Earth Observation Application Package <https://docs.ogc.org/bp/20-089r1.html>`_
  definitions (relates to
  `#56 <https://github.com/crim-ca/weaver/issues/56>`_,
  `#103 <https://github.com/crim-ca/weaver/issues/103>`_,
  `#105 <https://github.com/crim-ca/weaver/issues/105>`_,
  `#294 <https://github.com/crim-ca/weaver/issues/294>`_,
  `#399 <https://github.com/crim-ca/weaver/issues/399>`_).
- Phase out ``Python 3.6`` support to better resolve package dependencies
  (could still work, but not explicitly supported nor officially guaranteed to work).

Fixes:
------
- Fix ``outputs`` permitted to be completely omitted from the execution request
  (resolves `#375 <https://github.com/crim-ca/weaver/issues/375>`_).
- Fix ``outputs`` permitted as explicit empty mapping or list as equivalent to omitting them, defining by default
  that all ``outputs`` should be returned with ``transmissionMode: value`` for ``Job`` execution.
- Fix all instances of ``outputTransmission`` reported as ``reference`` in ``Process`` descriptions, although `Weaver`
  behaved with the ``value`` method, which is to return values and file references in content body, instead of
  HTTP ``Link`` header references.
- Fix `WPS 1/2` endpoint not reporting the appropriate instance URL
  (fixes `#83 <https://github.com/crim-ca/weaver/issues/83>`_).
- Fix `CLI` ``deploy`` operation headers incorrectly passed down to the deployment request.
- Fix many linting issues with latest ``pylint`` definitions.
- Fix temporary ``pywps`` patches that have been integrated
  (relates to `#352 <https://github.com/crim-ca/weaver/issues/352>`_
  addressing issues `geopython/pywps#578 <https://github.com/geopython/pywps/pull/578>`_
  and `geopython/pywps#623 <https://github.com/geopython/pywps/pull/623>`_).
- Fix ``celery`` security vulnerability with update to latest recommended version
  (resolves `#386 <https://github.com/crim-ca/weaver/issues/386>`_).

.. _changes_4.14.0:

`4.14.0 <https://github.com/crim-ca/weaver/tree/4.14.0>`_ (2022-03-14)
========================================================================

Changes:
--------
- Add `CLI` option ``-L/--no-links`` that drops the ``links`` section of any response to make the printed result more
  concise and specific to relevant details of the called operation.
- Add `CLI` option ``-F/--format`` that allows output of contents in an alternative format.
  Available formatters include JSON, YAML and XML representations, with either pretty indentation and newlines or not.
  This allows `CLI` calls that can return contents in the preferred format of a such that might need to parse the
  relevant details. Alternative until the API itself can return similar formatted responses
  (relates to `#125 <https://github.com/crim-ca/weaver/issues/125>`_).
- Add `CLI` option ``-H/--headers`` that allows output of response headers as well as the response contents.
  This can be useful for endpoints that can return critical information, such as ``Location`` header for the `Job`
  status endpoint of an `OGC` compliant service, or the ``Preference-Applied`` header for services that support multiple
  execution modes (i.e.: ``wait`` for ``sync-execute`` or ``respond-async`` for ``async-execute`` control options).
- Add `CLI` operation ``jobs`` to obtain listing with some options similar to the corresponding `API` endpoint queries.

Fixes:
------
- No change.

.. _changes_4.13.0:

`4.13.0 <https://github.com/crim-ca/weaver/tree/4.13.0>`_ (2022-03-09)
========================================================================

Changes:
--------
- Add ``schema`` query parameter to ``GET /jobs/{jobID}/outputs`` request allowing to select between ``OGC``, ``OLD``
  ``OGC+strict`` and ``OLD+strict`` representations (case insensitive), each with different combinations
  of ``format.mimeType``, ``format.mediaType`` and/or directly ``type`` field to provide the Content-Type of an
  output with ``href`` file.
  By default, both the ``format`` (i.e.: ``OLD`` schema) and the ``type`` (i.e.: ``OGC`` schema) are simultaneously
  reported for backward and forward compatibility, and for `OGC` compliance, to return the IANA Media-Type of the
  associated file reference (relates to `#401 <https://github.com/crim-ca/weaver/issues/401>`_).
- Add support of ``type`` as alias to the Media-Type under the ``format`` for file references when submitted
  for ``Job`` execution inputs, in accordance to the reported inputs/outputs endpoints, and for `OGC` compliance
  (resolves `#401 <https://github.com/crim-ca/weaver/issues/401>`_).
- Drop ``type`` field for ``metadata`` items in process description that correspond to a ``value`` with a ``role``.
- Enforce pattern validation of ``type`` as IANA Content-Type for ``metadata`` items in process description that
  correspond to a ``Link`` with ``href``. Invalid ``type`` are now rejected to adhere to `OGC` requirement classes.
- Clarify schema employed by `Weaver` to use naming that is as close as possible to `OGC` schemas to facilitate their
  comprehension and external references.

Fixes:
------
- Fix ``GET /jobs/{jobID}/inputs`` endpoint failing to return submitted ``inputs`` for ``Job`` execution when they
  were specified using the mapping representation (i.e.: ``OGC`` schema) instead of the listing representation
  (i.e.: ``OLD`` schema).
- Fix Media-Type provided as ``Job`` file reference input not forwarded to underlying WPS execution for validation
  against supported formats for corresponding inputs. Specified format handles both the ``OLD`` definition with
  ``format`` field (and nested ``mimeType`` or ``mediaType``), and the more recent ``OGC`` format with ``type`` field.

.. _changes_4.12.0:

`4.12.0 <https://github.com/crim-ca/weaver/tree/4.12.0>`_ (2022-02-28)
========================================================================

Changes:
--------
- Updates related to |ogc-api-proc-quote|_.
- Move estimator portion of the quoting operation into separate files and bind them with `Celery` task to allow the
  same kind of dispatched processing as normal `Process` execution.
- Update `Quote` data type to contain status similarly to `Job` considering dispatched ``async`` processing.
- Define ``LocalizedDateTimeProperty`` for reuse by data types avoiding issues about handling datetime localization.
- Update OpenAPI schemas regarding `Quote` (partial/complete) and other datetime related fields.
- Add parsing of ``Prefer`` header allowing ``sync`` processing
  (relates to `#247 <https://github.com/crim-ca/weaver/issues/247>`_).
  This is not yet integrated for `Jobs` execution themselves on ``processes/{id}/execution`` endpoint.

.. |ogc-api-proc-quote| replace:: `OGC API - Processes`: Quotation Extension
.. _ogc-api-proc-quote: https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/quotation

Fixes:
------
- No change.

.. _changes_4.11.0:

`4.11.0 <https://github.com/crim-ca/weaver/tree/4.11.0>`_ (2022-02-24)
========================================================================

Changes:
--------
- Support `Process` deployment using `OGC` schema (i.e.: `Process` metadata can be provided directly under
  ``processDescription`` instead of being nested under ``processDescription.process``).
  This aligns the deployment schema with reference `OGC API - Processes: Deploy, Replace, Undeploy` extension
  (see |ogc-app-pkg|_ schema).
  The previous schema for deployment with nested ``process`` field remains supported for backward compatibility.

.. |ogc-app-pkg| replace:: OGC Application Package
.. _ogc-app-pkg: https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-dru/ogcapppkg.yaml

Fixes:
------
- Fix resolution of the ``default`` field specifier under a list of supported ``formats`` during deployment.
  For various combinations such as when ``default: True`` format is omitted, or when the default is not ordered first,
  resolved ``default`` specifically for ``outputs`` definitions would be incorrect.

.. _changes_4.10.0:

`4.10.0 <https://github.com/crim-ca/weaver/tree/4.10.0>`_ (2022-02-22)
========================================================================

Changes:
--------
- Refactor all constants of similar concept into classes to facilitate reuse and avoid omitting entries when iterating
  over all members of a corresponding constant group (fixes `#33 <https://github.com/crim-ca/weaver/issues/33>`_).

Fixes:
------
- Fix resolution of common IANA Media-Types (e.g.: ``text/plain``, ``image/jpeg``, etc.) that technically do not provide
  and explicit entry when accessing the namespace (i.e.: ``{IANA_NAMESPACE_URL}/{mediaType}``), but are known in IANA
  registry through various RFC specifications. The missing endpoints caused many recurring and unnecessary HTTP 404 that
  needed a second validation against EDAM namespace each time. These common Media-Types, along with new definitions in
  ``weaver.formats``, will immediately return a IANA/EDAM references without explicit validation on their registries.

.. _changes_4.9.1:

`4.9.1 <https://github.com/crim-ca/weaver/tree/4.9.1>`_ (2022-02-21)
========================================================================

Changes:
--------
- Add encryption of stored `Vault` file contents until retrieved for usage by the executed ``Process`` application.

Fixes:
------
- Fix auto-resolution of `Vault` file ``Content-Type`` when not explicitly provided.

.. _changes_4.9.0:

`4.9.0 <https://github.com/crim-ca/weaver/tree/4.9.0>`_ (2022-02-17)
========================================================================

Changes:
--------
- Add `Vault` endpoints providing a secured self-hosted file storage to upload local files for execution input.
- Add ``upload`` CLI operation for uploading local files to `Vault`.
- Add CLI automatic detection of local files during ``execute`` call to upload to `Vault` and retrieve them from it
  on the remote `Weaver` instance.
- Add ``-S``/``--schema`` option to CLI ``describe`` operation.
- Add more documentation examples and references related to CLI and ``WeaverClient`` usage.
- Improve Media-Type/Content-Type guesses based on known local definitions and extensions in ``weaver.formats``.
- Extend ``PyWPS`` ``WPSRequest`` to support more authorization header forwarding for inputs that could need it.

Fixes:
------
- Fix rendering of CLI *required* arguments under the appropriate argument group section when those arguments can be
  specified using prefixed ``-`` and ``--`` optional arguments format.
- Fix CLI ``url`` parameter to be provided using ``-u`` or ``--url`` without specific argument position needed.
- Fix CLI parsing of ``File`` inputs for ``execute`` operation when provided with quotes to capture full paths.
- Fix rendering of OpenAPI variable names (``additionalParameters``) employed to represent for example ``{input-id}``
  as the key within the mapping representation of inputs/outputs. The previous notation employed was incorrectly
  interpreted as HTML tags, making them partially hidden in Swagger UI.
- Fix reload of ``DockerAuthentication`` reference from database failing due to mismatched parameter names.
- Fix invalid generation and interpretation of timezone-aware datetime between local objects and loaded from database.
  Jobs created or reported without any timezone UTC offset were assumed as UTC+00:00 although corresponding datetimes
  were generated based on the local machine timezone information. Once reloaded from database, the missing timezone
  awareness made datetime stored in ISO-8601 format to be interpreted as already localized datetime.
- Fix invalid setup of generic CLI options headers for other operations than ``dismiss``.
- Fix ``weaver.request-options`` handling that always ignored ``timeout`` and ``verify`` entries from the configuration
  file by overriding them with default values.

.. _changes_4.8.0:

`4.8.0 <https://github.com/crim-ca/weaver/tree/4.8.0>`_ (2022-01-11)
========================================================================

Changes:
--------
- Refactor Workflow operation flow to reuse shared input and output staging operations between implementations.
  Each new step process implementation now only requires to implement the specific operations related to deployment,
  execution, monitoring and result retrieval for their process, without need to consider Workflow intermediate staging
  operations to transfer files between steps.
- Refactor ``Wps1Process`` and ``Wps3Process`` step processes to follow new workflow operation flow.
- Add ``builtin`` process ``file_index_selector`` that allows the selection of a specific file within an array of files.
- Add tests to validate chaining of Workflow steps using different combinations of process types
  including `WPS-1`, `OGC-API` and ``builtin`` implementations.
- Move `CWL` script examples in documentation to separate package files in order to directly reference them in
  tests validating their deployment and execution requests.
- Move all ``tests/functional/application-packages`` definitions into distinct directories to facilitate categorization
  of corresponding deployment, execution and package contents, and better support the various Workflow testing location
  of those files with backward compatibility.
- Add logs final entry after retrieved internal `CWL` application logs to help highlight delimitation with following
  entries from the parent `Process`.

Fixes:
------
- Fix handling of `CWL` Workflow outputs between steps when nested glob output binding are employed
  (resolves `#371 <https://github.com/crim-ca/weaver/issues/371>`_).
- Fix resolution of ``builtin`` process Python reference when executed locally within a Workflow step.
- Fix resolution of process type `WPS-1` from its package within a Workflow step executed as `OGC-API` process.
- Fix resolution of ``WPS1Requirement`` directly provided as `CWL` execution unit within the deployment body.
- Fix deployment body partially dropping invalid ``executionUnit`` sub-fields causing potential misinterpretation
  of the intended application package.
- Fix resolution of package or `WPS-1` reference provided by ``href`` with erroneous ``Content-Type`` reported by the
  returned response. Attempts auto-resolution of detected `CWL` (as `JSON` or `YAML`) and `WPS-1` (as `XML`) contents.
- Fix resolution of ``format`` reference within `CWL` I/O record after interpretation of the loaded application package.
- Fix missing `WPS` endpoint responses in generated `OpenAPI` for `ReadTheDocs` documentation.
- Fix reporting of `WPS-1` status location as the `XML` file URL instead of the `JSON` `OGC-API` endpoint when `Job`
  was originally submitted through the `WPS-1` interface.
- Fix and improve multiple typing definitions.

.. _changes_4.7.0:

`4.7.0 <https://github.com/crim-ca/weaver/tree/4.7.0>`_ (2021-12-21)
========================================================================

Changes:
--------
- Add CLI ``--body`` and ``--cwl`` arguments support of literal JSON string for ``deploy`` operation.

Fixes:
------
- Fix help message of CLI arguments not properly grouped within intended sections.
- Fix handling of mutually exclusive CLI arguments in distinct operation sub-parsers.
- Fix CLI requirement of ``--process`` and ``--job`` arguments.

.. _changes_4.6.0:

`4.6.0 <https://github.com/crim-ca/weaver/tree/4.6.0>`_ (2021-12-15)
========================================================================

Changes:
--------
- Add ``WeaverClient`` and ``weaver`` `CLI` as new utilities to interact with `Weaver` instead of using the HTTP `API`.
  This provides both shell and Python script interfaces to run operations toward `Weaver` instances
  (or any other `OGC API - Processes` compliant instance *except for deployment operations*).
  It also facilitates new `Process` deployments by helping with the integration of a local `CWL` file into
  a full-fledged ``Deploy`` HTTP request, and other recurrent tasks such as ``Execute`` requests followed by `Job`
  monitoring and results retrieval once completed successfully
  (resolves `#363 <https://github.com/crim-ca/weaver/issues/363>`_,
  resolves `DAC-198 <https://crim-ca.atlassian.net/jira/software/c/projects/DAC/issues/DAC-198>`_,
  relates to `DAC-203 <https://crim-ca.atlassian.net/jira/software/c/projects/DAC/issues/DAC-203>`_).
- Added ``weaver`` command installation to ``setup.py`` script.
- Added auto-documentation utilities for new ``weaver`` CLI (argparse parameter definitions) and provide relevant
  references in new chapter in Sphinx documentation.
- Added ``cwl2json_input_values`` function to help converting between `CWL` *parameters* and `OGC API - Processes`
  input value definitions for `Job` submission.
- Added ``weaver.datatype.AutoBase`` that allows quick definition of data containers with fields accessible both as
  properties and dictionary keys, simply by detecting predefined class attributes, avoiding a lot of boilerplate code.
- Split multiple file loading, remote validation and resolution procedures into distinct functions in order for the
  new `CLI` to make use of the same methodologies as needed.
- Updated documentation with new details relevant to the added `CLI` and corresponding references.
- Updated some tests utilities to facilitate definitions of new tests for ``WeaverClient`` feature validation.
- Replaced literal string ``"OGC"`` and ``"OLD"`` used for schema selection by properly defined constants.
- Add database revision number for traceability of migration procedures as needed.
- Add first database revision with conversion of UUID-like strings to literal UUID objects.
- Add ``links`` to ``/processes`` and ``/providers/{id}/processes`` listings
  (resolves `#269 <https://github.com/crim-ca/weaver/issues/269>`_).
- Add ``limit``, ``page`` and ``sort`` query parameters for ``/processes`` listing
  (resolves `#269 <https://github.com/crim-ca/weaver/issues/269>`_).
- Add ``ignore`` parameter to ``/processes`` listing when combined with ``providers=true`` to allow the similar
  behaviour supported by ``ignore`` on ``/providers`` endpoint, to effectively ignore services that cause parsing
  errors or failure to retrieve details from the remote reference.
- Add schema validation of contents returned on ``/processes`` endpoint.
- Add more validation of paging applicable index ranges and produce ``HTTPBadRequest [400]`` when values are invalid.

Fixes:
------
- Fix some typing definitions related to `CWL` function parameters.
- Fix multiple typing inconsistencies or ambiguities between ``AnyValue`` (as Python typing for any literal value)
  against the actual class ``AnyValue`` of ``PyWPS``. Typing definitions now all use ``AnyValueType`` instead.
- Fix resolution of ``owsContext`` location in the payload of remote `Process` provided by ``href`` link in
  the ``executionUnit`` due to `OGC API - Processes` (``"OGC"`` schema) not nested under ``process`` key
  (in contrast to ``"OLD"`` schema).
- Fix resolution of ``outputs`` submitted as mapping (`OGC API - Processes` schema) during `Job` execution
  to provide desired filtered outputs in results and their ``transmissionMode``. Note that filtering and handling of
  all ``transmissionMode`` variants are themselves not yet supported (relates to
  `#377 <https://github.com/crim-ca/weaver/issues/377>`_ and `#380 <https://github.com/crim-ca/weaver/issues/380>`_).
- Fix resolution of unspecified UUID representation format in `MongoDB`.
- Fix conformance with error type reporting of missing `Job` or `Process`
  (resolves `#320 <https://github.com/crim-ca/weaver/issues/320>`_).
- Fix sorting of text fields using alphabetical case-insensitive ordering.
- Fix search with paging reporting invalid ``total`` when out of range.
- Pin ``pymongo<4`` until ``celery>=5`` gets resolved
  (relates to `#386 <https://github.com/crim-ca/weaver/issues/386>`_).

.. _changes_4.5.0:

`4.5.0 <https://github.com/crim-ca/weaver/tree/4.5.0>`_ (2021-11-25)
========================================================================

Changes:
--------
- Add support of ``X-Auth-Docker`` request header that can be specified during `Process` deployment as
  authentication token that `Weaver` can use to obtain access and retrieve the `Docker` image referenced
  by the `Application Package` (`CWL`) located on a private registry.
- Add more documentation details about sample `CWL` definitions to execute script, Python and Dockerized applications.

Fixes:
------
- Fix parsing of inputs for `OpenSearch` parameters lookup that was assuming inputs were always provided as
  listing definition, not considering possible mapping definition.
- Fix incorrect documentation section ``Package as External Execution Unit Reference`` where content was omitted
  and incorrectly anchored as following ``ESGF-CWT`` section.

.. _changes_4.4.0:

`4.4.0 <https://github.com/crim-ca/weaver/tree/4.4.0>`_ (2021-11-19)
========================================================================

Changes:
--------
- Add ``map_wps_output_location`` utility function to handle recurrent mapping of ``weaver.wps_output_dir`` back and
  forth with resolved ``weaver.wps_output_url``.
- Add more detection of map-able WPS output location to avoid fetching files unnecessarily. Common cases
  are ``Workflow`` running multiple steps on the same server or `Application Package` ``Process`` that reuses an output
  produced by a previous execution. Relates to `#183 <https://github.com/crim-ca/weaver/issues/183>`_.
- Add pre-validation of file accessibility using HTTP HEAD request when a subsequent ``Workflow`` step
  employs an automatically mapped WPS output location from a previous step to verify that the file would otherwise
  be downloadable if it could not have been mapped. This is to ensure consistency and security validation of the
  reference WPS output location, although the unnecessary file download operation can be avoided.
- Add functional ``Workflow`` tests to validate execution without the need of remote `Weaver` test application
  (relates to `#141 <https://github.com/crim-ca/weaver/issues/141>`_,
  relates to `#281 <https://github.com/crim-ca/weaver/issues/281>`_).
- Add missing documentation details about `Data Source` and connect chapters with other relevant
  documentation details and updated ``Workflow`` tests.
- Add handling of ``Content-Disposition`` header providing preferred ``filename`` or ``filename*`` parameters when
  fetching file references instead of the last URL fragment employed by default
  (resolves `#364 <https://github.com/crim-ca/weaver/issues/364>`_).
- Add more security validation of the obtained file name from HTTP reference, whether generated from URL path fragment
  or other header specification.

Fixes:
------
- Fix incorrect resolution of ``Process`` results endpoint to pass contents from one step to another
  during ``Workflow`` execution (resolves `#358 <https://github.com/crim-ca/weaver/issues/358>`_).
- Fix logic of remotely and locally executed applications based on `CWL` requirements when attempting to resolve
  whether an input file reference should be fetched.
- Fix resolution of `WPS` I/O provided as mapping instead of listing during deployment in order to properly parse
  them and merge their metadata with corresponding `CWL` I/O definitions.
- Fix `DataSource` and `OpenSearch` typing definitions to more rapidly detect incorrect data structures during parsing.

.. _changes_4.3.0:

`4.3.0 <https://github.com/crim-ca/weaver/tree/4.3.0>`_ (2021-11-16)
========================================================================

Changes:
--------
- Add support of ``type`` and ``processID`` query parameters for ``Job`` listing
  (resolves some tasks in `#268 <https://github.com/crim-ca/weaver/issues/268>`_).
- Add ``type`` field to ``Job`` status information
  (resolves `#351 <https://github.com/crim-ca/weaver/issues/351>`_).
- Add `OGC API - Processes` conformance references regarding supported operations for ``Job`` listing and filtering.
- Add ``minDuration`` and ``maxDuration`` parameters to query ``Job`` listing filtered by specific execution time range
  (resolves `#268 <https://github.com/crim-ca/weaver/issues/268>`_).
  Range duration parameters are limited to single values each
  (relates to `opengeospatial/ogcapi-processes#261 <https://github.com/opengeospatial/ogcapi-processes/issues/261>`_).
- Require minimally ``pymongo==3.12.0`` and corresponding `MongoDB` ``5.0`` instance to process new filtering queries
  of ``minDuration`` and ``maxDuration``. Please refer
  to `Database Migration <https://pavics-weaver.readthedocs.io/en/latest/installation.html#database-migration>`_
  and `MongoDB official documentation <https://docs.mongodb.com/manual>`_ for migration methods.
- Refactor ``Job`` search method to facilitate its extension in the event of future filter parameters.
- Support contextual WPS output location using ``X-WPS-Output-Context`` header to store ``Job`` results.
  When a ``Job`` is executed by providing this header with a sub-directory, the resulting outputs of the ``Job``
  will be placed and reported under the corresponding location relative to WPS outputs (path and URL).
- Add ``weaver.wps_output_context`` setting as default contextual WPS output location when header is omitted.
- Replace ``Job.execute_async`` getter/setter by simple property using more generic ``Job.execution_mode``
  for storage in database. Provide ``Job.execute_async`` and ``Job.execute_sync`` properties based on stored mode.
- Simplify ``execute_process`` function executed by `Celery` task into sub-step functions where applicable.
- Simplify forwarding of ``Job`` parameters between ``PyWPS`` service ``WorkerService.execute_job`` method
  and `Celery` task instantiating it by reusing the ``Job`` object.
- Provide corresponding ``Job`` log URL along already reported log file path to facilitate retrieval from server side.
- Avoid ``Job.progress`` updates following ``failed`` or ``dismissed`` statuses to keep track of the last real progress
  percentage that was reached when that status was set.
- Improve typing of database and store getter functions to infer correct types and facilitate code auto-complete.
- Implement ``Job`` `dismiss operation <https://docs.ogc.org/is/18-062r2/18-062r2.html#toc53>`_ ensuring
  pending or running tasks are removed and output result artifacts are removed from disk.
- Implement HTTP Gone (410) status from already dismissed ``Job`` when requested again or when fetching its artifacts.

Fixes:
------
- Removes the need for specific configuration to handle public/private output directory settings using
  provided ``X-WPS-Output-Context`` header (fixes `#110 <https://github.com/crim-ca/weaver/issues/110>`_).
- Fix retrieval of `Pyramid` ``Registry`` and application settings when available *container* is `Werkzeug` ``Request``
  instead of `Pyramid` ``Request``, as employed by underlying HTTP requests in `PyWPS` service.
- Allow ``group`` query parameter to handle ``Job`` category listing with ``provider`` as ``service`` alias.
- Improve typing of database and store getter functions to infer correct types and facilitate code auto-complete.
- Fix incorrectly configured API views for batch ``Job`` dismiss operation with ``DELETE /jobs`` and corresponding
  endpoints for ``Process`` and ``Provider`` paths.
- Fix invalid ``Job`` links sometimes containing duplicate ``/`` occurrences.
- Fix invalid ``Job`` link URL for ``alternate`` relationship.

.. _changes_4.2.1:

`4.2.1 <https://github.com/crim-ca/weaver/tree/4.2.1>`_ (2021-10-20)
========================================================================

Changes:
--------
- Add more frequent ``Job`` updates of execution checkpoint pushed to database in order to avoid inconsistent statuses
  between the parent ``Celery`` task and the underlying `Application Package` being executed, since both can update the
  same ``Job`` entry at different moments.
- Add a ``Job`` log entry as ``"accepted"`` on the API side before calling the ``Celery`` task submission
  (``Job`` not yet picked by a worker) in order to provide more detail between the submission time and initial
  execution time. This allows to have the first log entry not immediately set to ``"running"`` since both ``"started"``
  and ``"running"`` statues are remapped to ``"running"`` within the task to be compliant with `OGC` status codes.

Fixes:
------
- Fix an inconsistency between the final ``Job`` status and the reported "completed" message in logs due to missing
  push of a newer state prior re-fetch of the latest ``Job`` from the database.

.. _changes_4.2.0:

`4.2.0 <https://github.com/crim-ca/weaver/tree/4.2.0>`_ (2021-10-19)
========================================================================

Changes:
--------
- Add execution endpoint ``POST /provider/{id}/process/{id}/execution`` corresponding to the OGC-API compliant endpoint
  for local ``Process`` definitions.
- Add multiple additional relation ``links`` for ``Process`` and ``Job`` responses
  (resolves `#234 <https://github.com/crim-ca/weaver/issues/234>`_
  and `#267 <https://github.com/crim-ca/weaver/issues/267>`_).
- Add convenience ``DELETE /jobs`` endpoint with input list of ``Job`` UUIDs in order to ``dismiss`` multiple entries
  simultaneously. This is useful for quickly removing a set of ``Job`` returned by filtered ``GET /jobs`` contents.
- Update conformance link list for ``dismiss`` and relevant relation ``links`` definitions
  (relates to `#53 <https://github.com/crim-ca/weaver/issues/53>`_
  and `#267 <https://github.com/crim-ca/weaver/issues/267>`_).
- Add better support and reporting of ``Job`` status ``dismissed`` when operation is called from API on running task.
- Use explicit ``started`` status when ``Job`` has been picked up by a `Celery` worker instead of leaving it
  to ``accepted`` (same status that indicates the ``Job`` "pending", although a worker is processing it).
  Early modification of status is done in case setup operations (send `WPS` request, prepare files, etc.) take some
  time which would leave users under the impression the ``Job`` is not getting picked up.
  Report explicit ``running`` status in ``Job`` once it has been sent to the remote `WPS` endpoint.
  The API will report ``running`` in both cases in order to support `OGC API - Processes` naming conventions, but
  internal ``Job`` status will have more detail.
- Add ``updated`` timestamp to ``Job`` response to better track latest milestones saved to database
  (resolves `#249 <https://github.com/crim-ca/weaver/issues/249>`_).
  This avoids users having to compare many fields (``created``, ``started``, ``finished``) depending on latest status.
- Apply stricter ``Deploy`` body schema validation and employ deserialized result directly.
  This ensures that preserved fields in the submitted content for deployment contain only known data elements with
  expected structures for respective schemas. Existing deployment body that contain invalid formats could start to
  fail or might generate inconsistent ``Process`` descriptions if not adjusted.
- Add improved reporting of erroneous inputs during ``Process`` deployment whenever possible to identify the cause.
- Add more documentation details about missing features such as ``EOImage`` inputs handled by `OpenSearch` requests.
- Add ``weaver.celery`` flag to internal application settings when auto-detecting that current runner is ``celery``.
  This bypasses redundant API-only operations during application setup and startup not needed by ``celery`` worker.

Fixes:
------
- Fix OGC-API compliant execution endpoint ``POST /process/{id}/execution`` not registered in API.
- Fix missing status for cancelled ``Jobs`` in order to properly support ``dismiss`` operation
  (resolves `#145 <https://github.com/crim-ca/weaver/issues/145>`_
  and `#228 <https://github.com/crim-ca/weaver/issues/228>`_).
- Fix all known `OGC`-specific link relationships with URI prefix
  (resolves `#266 <https://github.com/crim-ca/weaver/issues/266>`_).
- Fix incorrect rendering of some table cells in the documentation.

.. _changes_4.1.2:

`4.1.2 <https://github.com/crim-ca/weaver/tree/4.1.2>`_ (2021-10-13)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Add ``celery worker`` task events flag (``-E``) to Docker command (``weaver-worker``) to help detect submitted
  delayed tasks when requesting job executions.

.. _changes_4.1.1:

`4.1.1 <https://github.com/crim-ca/weaver/tree/4.1.1>`_ (2021-10-12)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix handling of default *format* field of `WPS` input definition incorrectly resolved as default *data* by ``PyWPS``
  for `Process` that allows optional (``minOccurs=0``) inputs of ``Complex`` type. Specific case is detected with
  relevant erroneous data and dropped silently because it should not be present (since omitted in `WPS` request) and
  should not generate a `WPS` input (relates to `geopython/pywps#633 <https://github.com/geopython/pywps/issues/633>`_).
- Fix resolution of `CWL` field ``default`` value erroneously inserted as ``"null"`` literal string for inputs generated
  from `WPS` definition to avoid potential confusion with valid ``"null"`` input or default string. Default behaviour to
  drop or ignore *omitted* inputs are handled by ``"null"`` within ``type`` field in `CWL` definitions.
- Fix ``Wps1Process`` job runner for dispatched execution of `WPS-1 Process` assuming all provided inputs contain data
  or reference. Skip omitted optional inputs that are resolved with ``None`` value following above fixes.
- Resolve execution failure of `WPS-1 Process` ``ncdump`` under ``hummingbird`` `Provider`
  (fixes issue identified in output logs from notebook in
  `PR pavics-sdi#230 <https://github.com/Ouranosinc/pavics-sdi/pull/230>`_).

.. _changes_4.1.0:

`4.1.0 <https://github.com/crim-ca/weaver/tree/4.1.0>`_ (2021-09-29)
========================================================================

Changes:
--------
- Improve reporting of mismatching `Weaver` configuration for `Process` and `Application Package` definitions that
  always require remote execution. Invalid combinations will be raised during execution with detailed problem.
- Forbid `Provider` and applicable `Process` definitions to be deployed, executed or queried when corresponding remote
  execution is not supported according to `Weaver` instance configuration since `Provider` must be accessed remotely.
- Refactor endpoint views and utilities referring to `Provider` operations into appropriate modules.
- Apply ``weaver.configuration = HYBRID`` by default in example INI configuration since it is the most common use case.
  Apply same configuration by default in tests. Default resolution still employs ``DEFAULT`` for backward compatibility
  in case the setting was omitted completely from a custom INI file.
- Add query parameter ``ignore`` to ``GET /providers`` listing in order to obtain full validation of
  remote providers (including XML contents parsing) to return ``200``. Invalid definitions will raise
  and return a ``[422] Unprocessable Entity`` HTTP error.
- Add more explicit messages about the problem that produced an error (XML parsing, unreachable WPS, etc.) and which
  caused request failure when attempting registration of a remote `Provider`.

Fixes:
------
- Fix reported ``links`` by processes nested under a provider ``Service``.
  Generated URL references were omitting the ``/providers/{id}`` portion.
- Fix documentation referring to incorrect setting name in some cases for WPS outputs configuration.
- Fix strict XML parsing failing resolution of some remote WPS providers with invalid characters such as ``<``, ``<=``
  within process description fields. Although invalid, those easily recoverable errors will be handled by the parser.
- Fix resolution and execution of WPS-1 remote `Provider` and validate it against end-to-end test procedure from
  scratch `Service` registration down to results retrieval
  (fixes `#340 <https://github.com/crim-ca/weaver/issues/340>`_).
- Fix resolution of applicable `Provider` listing schema validation when none have been registered
  (fixes `#339 <https://github.com/crim-ca/weaver/issues/339>`_).
- Fix incorrect schema definition of `Process` items for ``GET /processes`` response that did not report the
  alternative identifier-only listing when ``detail=false`` query is employed.
- Fix incorrect reporting of documented OpenAPI reference definitions for ``query`` parameters with same names shared
  across multiple endpoints. Fix is directly applied on relevant reference repository that generates OpenAPI schemas
  (see `fmigneault/cornice.ext.swagger@70eb702 <https://github.com/fmigneault/cornice.ext.swagger/commit/70eb702>`_).
- Fix ``weaver.exception`` definitions such that raising them directly will employ the corresponding ``HTTPException``
  code (if applicable) to generate the appropriate error response automatically when raising them directly without
  further handling. The order of class inheritance were always using ``500`` due to ``WeaverException`` definition.

.. _changes_4.0.0:

`4.0.0 <https://github.com/crim-ca/weaver/tree/4.0.0>`_ (2021-09-21)
========================================================================

Changes:
--------
- Apply conformance updates to better align with expected ``ProcessDescription`` schema from
  `OGC API - Processes v1.0-draft6 <https://github.com/opengeospatial/ogcapi-processes/tree/1.0-draft.6>`_.
  The principal change introduced in this case is that process description contents will be directly at the root
  of the object returned by ``/processes/{id}`` response instead of being nested under ``"process"`` field.
  Furthermore, ``inputs`` and ``outputs`` definitions are reported as mapping of ``{"<id>": {<parameters>}}`` as
  specified by `OGC-API` instead of old listing format ``[{"id": "<id-value>", <key:val parameters>}]``. The old
  nested and listing format can still be obtained using request query parameter ``schema=OLD``, and will otherwise use
  `OGC-API` by default or when ``schema=OGC``. Note that some duplicated metadata fields are dropped regardless of
  selected format in favor of `OGC-API` names. Some examples are ``abstract`` that becomes ``description``,
  ``processVersion`` that simply becomes ``version``, ``mimeType`` that becomes ``mediaType``, etc.
  Some of those changes are also reflected by ``ProcessSummary`` during listing of processes, as well as for
  corresponding provider-related endpoints (relates to `#200 <https://github.com/crim-ca/weaver/issues/200>`_).
- Add backward compatibility support of some metadata fields (``abstract``, ``mimeType``, etc.) for ``Deploy``
  operation of pre-existing processes. When those fields are detected, they are converted inplace in favor of their
  corresponding new names aligned with `OGC-API`.
- Update ``mimeType`` to ``mediaType`` as format type representation according to `OGC-API`
  (relates to `#211 <https://github.com/crim-ca/weaver/issues/211>`_).
- Add explicit pattern validation (``type/subtype``) of format string definitions with ``MediaType`` schema.
- Add sorting capability to generate mapping schemas for API responses using overrides of
  properties ``_sort_first`` and ``_sort_after`` using lists of desired ordered field names.
- Improved naming of many ambiguous and repeated words across schema definitions that did not necessarily interact
  with each other although making use of similar naming convention, making their interpretation and debugging much
  more complicated. A stricter naming convention has been applied for consistent Deploy/Describe/Execute-related
  and Input/Output-related references.
- Replace ``list_remote_processes`` function by method ``processes`` under the ``Service`` instance.
- Replace ``get_capabilities`` function by reusing and extending method ``summary`` under the ``Service`` instance.
- Improve generation of metadata and content validation of ``Service`` provider responses
  (relates to OGC `#200 <https://github.com/crim-ca/weaver/issues/200>`_
  and `#266 <https://github.com/crim-ca/weaver/issues/266>`_).
- Add query parameter ``detail`` to providers listing request to allow listing of names instead of their summary
  (similarly to the processes endpoint query parameter).
- Add query parameter ``check`` to providers listing request to retrieve all registered ``Service`` regardless of
  their URL endpoint availability at the moment the request is executed (less metadata is retrieved in that case).
- Add ``weaver.schema_url`` configuration parameter and ``weaver.wps_restapi.utils.get_schema_ref`` function to help
  generate ``$schema`` definition and return reference to expected/provided schema in responses
  (relates to `#157 <https://github.com/crim-ca/weaver/issues/157>`_)
  Only utilities are added, not all routes provide the information yet.
- Add validation of ``schema`` field under ``Format`` schema (as per `opengeospatial/ogcapi-processes schema format.yml
  <https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/format.yaml>`_) such that only
  URL formatted strings are allowed, or alternatively an explicit JSON definition. Previous definitions that would
  indicate an empty string schema are dropped since ``schema`` is optional.
- Block unknown and ``builtin`` process types during deployment from the API
  (fixes `#276 <https://github.com/crim-ca/weaver/issues/276>`_).
  Type ``builtin`` can only be registered by `Weaver` itself at startup. Other unknown types that have
  no indication for mapping to an appropriate ``Process`` implementation are preemptively validated.
- Add parsing and generation of additional ``literalDataDomains`` for specification of WPS I/O data constrains and
  provide corresponding definitions in process description responses
  (fixes `#41 <https://github.com/crim-ca/weaver/issues/41>`_,
  `#211 <https://github.com/crim-ca/weaver/issues/211>`_,
  `#297 <https://github.com/crim-ca/weaver/issues/297>`_).
- Add additional ``maximumMegabyte`` metadata detail to ``formats`` of WPS I/O of ``complex`` type whenever available
  (requires `geopython/OWSLib#796 <https://github.com/geopython/OWSLib/pull/796>`_, future ``OWSLIB==0.26.0`` release).

Fixes:
------
- Revert an incorrectly removed schema deserialization operation during generation of the ``ProcessSummary`` employed
  for populating process listing.
- Revert an incorrectly modified schema reference that erroneously replaced service provider ``ProcessSummary`` items
  during their listing by a single ``ProcessInputDescriptionSchema`` (introduced since ``3.0.0``).
- Fix `#203 <https://github.com/crim-ca/weaver/issues/203>`_ with explicit validation test of ``ProcessSummary``
  schema for providers response.
- Fix failing ``minOccurs`` and ``maxOccurs`` generation from a remote provider ``Process`` to support `OGC-API` format
  (relates to `#263 <https://github.com/crim-ca/weaver/issues/263>`_).
- Fix schemas references and apply deserialization to providers listing request.
- Fix failing deserialization of ``variable`` children schema under mapping when this variable element is allowed
  to be undefined (i.e.: defined with ``missing=drop``). Allows support of empty ``inputs`` mapping of `OGC-API`
  representation of ``ProcessDescription`` that permits such processes (constant or random output generator).
- Fix some invalid definitions of execution inputs schemas under mapping with ``value`` sub-schema where key-based
  input IDs (using ``additionalProperties``) where replaced by the *variable* ``<input-id>`` name instead of their
  original names in the request body (from `#265 <https://github.com/crim-ca/weaver/issues/265>`_ since ``3.4.0``).
- Fix parsing error raised from ``wps_processes.yml`` configuration file when it can be found but contains neither
  a ``processes`` nor ``providers`` section. Also, apply more validation of specified ``name`` values.
- Fix parsing of ``request_extra`` function/setting parameters for specifically zero values corresponding
  to ``retries`` and ``backoff`` options that were be ignored.
- Fix incorrect parsing of ``default`` field within WPS input when ``literal`` data type is present and was assumed
  as ``complex`` (fixes `#297 <https://github.com/crim-ca/weaver/issues/297>`_).
- Fix and test various invalid schema deserialization validation issues, notably regarding ``PermissiveMappingSchema``,
  schema nodes ``ExtendedFloat``, ``ExtendedInt`` and their handling strategies when combined in mappings or keywords.
- Fix resolution of similar values that could be implicitly converted between ``ExtendedString``, ``ExtendedFloat``,
  ``ExtendedInt`` and ``ExtendedBool`` schema types to guarantee original data type explicitly defined are preserved.
- Fix ``runningSeconds`` field reporting to be of ``float`` type although implicit ``int`` type conversion could occur.
- Fix validation of ``Execute`` inputs schemas to adequately distinguish between optional inputs and incorrect formats.
- Fix resolution of ``Accept-Language`` negotiation forwarded to local or remote WPS process execution.
- Fix XML security issue flagged within dependencies to ``PyWPS`` and ``OWSLib`` by pinning requirements to
  versions ``pywps==4.5.0`` and ``owslib==0.25.0``, and apply the same fix in `Weaver` code (see following for details:
  `geopython/pywps#616 <https://github.com/geopython/pywps/pull/616>`_,
  `geopython/pywps#618 <https://github.com/geopython/pywps/pull/618>`_,
  `geopython/pywps#624 <https://github.com/geopython/pywps/issues/624>`_,
  `CVE-2021-39371 <https://nvd.nist.gov/vuln/detail/CVE-2021-39371>`_).

.. _changes_3.5.0:

`3.5.0 <https://github.com/crim-ca/weaver/tree/3.5.0>`_ (2021-08-19)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix ``weaver.datatype`` objects auto-resolution of fields using either attributes (accessed as ``dict``)
  or properties (accessed as ``class``) to ensure correct handling of additional operations on them.
- Fix ``DuplicateKeyError`` that could sporadically arise during initial ``processes`` storage creation
  when ``builtin`` processes get inserted/updated on launch by parallel worker/threads running the application.
  Operation is relaxed only for default ``builtin`` to allow equivalent process replacement (``upsert``) instead
  of only explicit inserts, as they should be pre-validated for duplicate entries, and only new definitions should
  be registered during this operation (fixes `#246 <https://github.com/crim-ca/weaver/issues/246>`_).

.. _changes_3.4.0:

`3.4.0 <https://github.com/crim-ca/weaver/tree/3.4.0>`_ (2021-08-11)
========================================================================

Changes:
--------
- Add missing processID detail in job status info response
  (relates to `#270 <https://github.com/crim-ca/weaver/issues/270>`_).
- Add support for inputs under mapping for inline values and arrays in process execution
  (relates to `#265 <https://github.com/crim-ca/weaver/issues/265>`_).

Fixes:
------
- Fix copy of headers when generating the WPS clients created for listing providers capabilities and processes.

.. _changes_3.3.0:

`3.3.0 <https://github.com/crim-ca/weaver/tree/3.3.0>`_ (2021-07-16)
========================================================================

Changes:
--------
- Add support for array type as job inputs
  (relates to `#233 <https://github.com/crim-ca/weaver/issues/233>`_).
- Remove automatic conversion of falsy/truthy ``string`` and ``integer`` type definitions to ``boolean`` type
  to align with OpenAPI ``boolean`` type definitions. Non explicit ``boolean`` values will not be automatically
  converted to ``bool`` anymore. They will require explicit ``false|true`` values.

Fixes:
------
- Fix ``minOccurs`` and ``maxOccurs`` representation according to `OGC-API`
  (fixes `#263 <https://github.com/crim-ca/weaver/issues/263>`_).
- Fixed the format of the output file URL. When the prefix ``/`` was not present,
  URL was incorrectly handled by not prepending the required base URL location.

.. _changes_3.2.1:

`3.2.1 <https://github.com/crim-ca/weaver/tree/3.2.1>`_ (2021-06-08)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix backward compatibility of pre-deployed processes that did not define ``jobControlOptions`` that is now required.
  Missing definition are substituted in-place by default ``["execute-async"]`` mode.

.. _changes_3.2.0:

`3.2.0 <https://github.com/crim-ca/weaver/tree/3.2.0>`_ (2021-06-08)
========================================================================

Changes:
--------
- Add reference link to ReadTheDocs URL of `Weaver` in API landing page.
- Add references to `OGC-API Processes` requirements and recommendations for eventual conformance listing
  (relates to `#231 <https://github.com/crim-ca/weaver/issues/231>`_).
- Add ``datetime`` query parameter for job searches queries
  (relates to `#236 <https://github.com/crim-ca/weaver/issues/236>`_).
- Add ``limit`` query parameter validation and integration for jobs in retrieve queries
  (relates to `#237 <https://github.com/crim-ca/weaver/issues/237>`_).

Fixes:
------
- Pin ``pywps==4.4.3`` and fix incompatibility introduced by its refactor of I/O base classes in
  `geopython/pywps#602 <https://github.com/geopython/pywps/pull/602>`_
  (specifically `commit 343d825 <https://github.com/geopython/pywps/commit/343d82539576b1e73eee3102654749c3d3137cff>`_),
  which broke the ``ComplexInput`` work-around to avoid useless of file URLs
  (see issue `geopython/pywps#526 <https://github.com/geopython/pywps/issues/526>`_).
- Fix default execution mode specification in process job control options
  (fixes `opengeospatial/ogcapi-processes#182 <https://github.com/opengeospatial/ogcapi-processes/pull/182>`_).
- Fix old OGC-API WPS REST bindings link in landing page for the more recent `OGC-API Processes` specification.
- Fix invalid deserialization of schemas using ``not`` keyword that would result in all fields returned instead of
  limiting them to the expected fields from the schema definitions for ``LiteralInputType`` in process description.
- Adjust ``InputType`` and ``OutputType`` schemas to use ``allOf`` instead of ``anyOf`` definition since all sub-schemas
  that define them must be combined, with their respectively required or optional fields.

.. _changes_3.1.0:

`3.1.0 <https://github.com/crim-ca/weaver/tree/3.1.0>`_ (2021-04-23)
========================================================================

Changes:
--------
- Add caching of remote WPS requests according to ``request-options.yml`` and request header ``Cache-Control`` to allow
  reduced query of pre-fetched WPS client definition.
- Add ``POST /processes/{}/execution`` endpoint that mimics its jobs counterpart to respect `OGC-API Processes` updates
  (see issue `opengeospatial/ogcapi-processes#124 <https://github.com/opengeospatial/ogcapi-processes/issues/124>`_ and
  PR `opengeospatial/ogcapi-processes#159 <https://github.com/opengeospatial/ogcapi-processes/pull/159>`_, resolves
  `#235 <https://github.com/crim-ca/weaver/issues/235>`_).
- Add OpenAPI schema examples for some of the most common responses.
- Add missing schema definitions for WPS XML requests and responses.
- Improve schema self-validation with their specified default values.
- Add explicit options usage and expected parsing results for all test variations of OpenAPI schemas generation and
  ``colander`` object arguments for future reference in ``tests.wps_restapi.test_colander_extras``.

Fixes:
------
- Fix erroneous tags in job inputs schemas.
- Fix handling of deeply nested schema validator raising for invalid format within optional parent schema.
- Fix retrieval of database connection from registry reference.
- Fix test mock according to installed ``pyramid`` version to avoid error with modified mixin implementations.

.. _changes_3.0.0:

`3.0.0 <https://github.com/crim-ca/weaver/tree/3.0.0>`_ (2021-03-16)
========================================================================

Changes:
--------
- Provide HTTP links to corresponding items of job in JSON body of status, inputs and outputs routes
  (`#58 <https://github.com/crim-ca/weaver/issues/58>`_, `#86 <https://github.com/crim-ca/weaver/issues/86>`_).
- Provide ``Job.started`` datetime and calculate ``Job.duration`` from it to indicate the duration of the process
  execution instead of counting from the time the job was submitted (i.e.: ``Job.created``).
- Provide OGC compliant ``<job-uri>/results`` response schema as well as some expected ``code``/``description``
  fields in case where the request fails.
- Add ``<job-uri>/outputs`` providing the ``data``/``href`` formatted job results as well as ``<job-uri>/inputs`` to
  retrieve the inputs that were provided during job submission
  (`#86 <https://github.com/crim-ca/weaver/issues/86>`_).
- Deprecate ``<job-uri>/result`` paths (indicated in OpenAPI schemas and UI) in favor of ``<job-uri>/outputs`` which
  provides the same structure with additional ``links`` references
  (`#58 <https://github.com/crim-ca/weaver/issues/58>`_). Result path requests are redirected automatically to outputs.
- Add more reference/documentation links to `WPS-1/2` and update conformance references
  (`#53 <https://github.com/crim-ca/weaver/issues/53>`_).
- Add some minimal caching support of routes.
- Adjust job creation route to return ``201`` (created) as it is now correctly defined by the OGC API specification
  (`#14 <https://github.com/crim-ca/weaver/issues/14>`_).
- Add ``Job.link`` method that auto-generates all applicable links (inputs, outputs, logs, etc.).
- Add ``image/jpeg``, ``image/png``, ``image/tiff`` formats to supported ``weaver.formats``
  (relates to `#100 <https://github.com/crim-ca/weaver/issues/100>`_).
- Handle additional trailing slash resulting in ``HTTPNotFound [404]`` to automatically resolve to corresponding
  valid route without the slash when applicable.
- Provide basic conda environment setup through ``Makefile`` for Windows bash-like shell (ie: ``MINGW``/``MINGW64``).
- Update documentation for minimal adjustments needed to run under Windows.
- Update OpenAPI template to not render the useless version selector since we only provide the current version.
- Update Swagger definitions to reflect changes and better reuse existing schemas.
- Update Swagger UI to provide the `ReadTheDocs` URL.
- Add `crim-ca/cwltool@docker-gpu <https://github.com/crim-ca/cwltool/tree/docker-gpu>`_ as ``cwltool`` requirement
  to allow processing of GPU-enabled dockers with `nvidia-docker <https://github.com/NVIDIA/nvidia-docker>`_.
- Add `fmigneault/cornice.ext.swagger@openapi-3 <https://github.com/fmigneault/cornice.ext.swagger/tree/openapi-3>`_
  as ``cornice_swagger`` requirement to allow OpenAPI-3 definitions support of schema generation and deserialization
  validation of JSON payloads.
- Disable default auto-generation of ``request-options.yml`` and ``wps_processes.yml`` configuration files from a copy
  of their respective ``.example`` files as these have many demo (and invalid values) that fail real execution of tests
  when no actual file was provided.
- Add per-request caching support when using ``request_extra`` function, and caching control according to request
  headers and ``request-options.yml`` configuration.

Fixes:
------
- Fix ``weaver.config.get_weaver_config_file`` called with empty path to be resolved just as requesting the default
  file path explicitly instead of returning an invalid directory.
- Fix `CWL` package path resolution under Windows incorrectly parsed partition as URL protocol.
- Fix ``AttributeError`` of ``pywps.inout.formats.Format`` equality check compared to ``null`` object (using getter
  patch on ``null`` since fix `geopython/pywps#507 <https://github.com/geopython/pywps/pull/507>`_ not released at
  this point).
- Fix potential invalid database state that could have saved an invalid process although the following
  ``ProcessSummary`` schema validation would fail and return ``HTTPBadRequest [400]``. The process is now saved only
  after complete and successful schema validation.

.. _changes_2.2.0:

`2.2.0 <https://github.com/crim-ca/weaver/tree/2.2.0>`_ (2021-03-03)
========================================================================

Changes:
--------
- Add ``weaver.wps.utils.get_wps_client`` function to handle the creation of ``owslib.wps.WebProcessingService`` client
  with appropriate *request options* configuration from application settings.

Fixes:
------
- Fix job percent progress reported in logs to be more consistent with actual execution of the process
  (fixes `#90 <https://github.com/crim-ca/weaver/issues/90>`_).
- Fix `Job` duration not stopped incrementing when its execution failed due to raised error
  (fixes `#222 <https://github.com/crim-ca/weaver/issues/222>`_).
- Improve race condition handling of ``builtin`` process registration at application startup.

.. _changes_2.1.0:

`2.1.0 <https://github.com/crim-ca/weaver/tree/2.1.0>`_ (2021-02-26)
========================================================================

Changes:
--------
- Ensure that configuration file definitions specified in ``processes`` and ``providers`` will override older database
  definitions respectively matched by ``id`` and ``name`` when starting `Weaver` if other parameters were modified.
- Support dynamic instantiation of `WPS-1/2` processes from remote `WPS` providers to accomplish job execution.
- Remove previously flagged duplicate code to handle ``OWSLib`` processes conversion to ``JSON`` for `OGC-API`.
- Replace ``GET`` HTTP request by ``HEAD`` for MIME-type check against ``IANA`` definitions (speed up).
- Improve handling of `CWL` input generation in combination with ``minOccurs``, ``maxOccurs``, ``allowedValues``
  and ``default`` empty (``"null"``) value from `WPS` process from remote provider
  (fix `#17 <https://github.com/crim-ca/weaver/issues/17>`_).
- Add ``HYBRID`` mode that allows `Weaver` to simultaneously run local `Application Packages` and remote WPS providers.
- Rename ``ows2json_output`` to ``ows2json_output_data`` to emphasise its usage for parsing job result data rather than
  simple output definition as accomplished by ``ows2json_io``.
- Remove function duplicating operations accomplished by ``ows2json_io`` (previously marked with FIXME).
- Improve typing definitions for `CWL` elements to help identify invalid parsing methods during development.
- Improve listing speed of remote providers that require data fetch when some of them might have become unreachable.

Fixes:
------
- Avoid failing `WPS-1/2` processes conversion to corresponding `OGC-API` process if metadata fields are omitted.
- Fix invalid function employed for ``GET /providers/{prov}/processes/{proc}`` route (some error handling was bypassed).

.. _changes_2.0.0:

`2.0.0 <https://github.com/crim-ca/weaver/tree/2.0.0>`_ (2021-02-22)
========================================================================

Changes:
--------
- Add support of YAML format for loading ``weaver.data_sources`` definition.
- Pre-install ``Docker`` CLI in ``worker`` image to avoid bad practice of mounting it from the host.
- Adjust WPS request dispatching such that process jobs get executed by ``Celery`` worker as intended
  (see `#21 <https://github.com/crim-ca/weaver/issues/21>`_ and `#126 <https://github.com/crim-ca/weaver/issues/126>`_).
- Move WPS XML endpoint functions under separate ``weaver.wps.utils`` and ``weaver.wps.views`` to remove the need to
  constantly handle circular imports issues due to processing related operations that share some code.
- Move core processing of job operation by ``Celery`` worker under ``weaver.processes.execution`` in order to separate
  those components from functions specific for producing WPS-REST API responses.
- Handle WPS-1/2 requests submitted by GET KVP or POST XML request with ``application/json`` in ``Accept`` header to
  return the same body content as if directly calling their corresponding WPS-REST endpoints.
- Remove ``request`` parameter of every database store methods since they were not used nor provided most of the time.
- Changed all forbidden access responses related to visibility status to return ``403`` instead of ``401``.
- Add more tests for Docker applications and test suite execution with Github Actions.
- Add more details in sample configurations and provide an example ``docker-compose.yml`` configuration that defines a
  *typical* `Weaver` API / Worker combination with ``docker-proxy`` for sibling container execution.
- Add captured ``stdout`` and ``stderr`` details in job log following CWL execution error when retrievable.
- Document the `WPS` KVP/XML endpoint within the generated OpenAPI specification.
- Disable auto-generation of ``request_options.yml`` file from corresponding empty example file and allow application
  to start if no such configuration was provided.
- Remove every Python 2 backward compatibility references and operations.
- Drop Python 2 and Python 3.5 support.

Fixes:
------
- Target ``PyWPS-4.4`` to resolve multiple invalid dependency requirements breaking installed packages over builtin
  Python packages and other compatibility fixes
  (see `geopython/pywps #568 <https://github.com/geopython/pywps/issues/568>`_).
- Fix retrieval of database connexion to avoid warning of ``MongoClient`` opened before fork of processes.
- Fix indirect dependency ``oauthlib`` missing from ``esgf-compute-api`` (``cwt``) package.
- Fix inconsistent ``python`` reference resolution of ``builtin`` applications when executed locally and in tests
  (using virtual/conda environment) compared to within Weaver Docker image (using OS python).
- Fix many typing definitions.

.. _changes_1.14.0:

`1.14.0 <https://github.com/crim-ca/weaver/tree/1.14.0>`_ (2021-01-11)
========================================================================

Changes:
--------
- Add ``data`` input support for `CWL` `Workflow` step referring to `WPS-3 Process`.
- Add documentation example references to `Application Package` and `Process` ``Deploy``/``Execute`` repositories.
- Add parsing of ``providers`` in ``wps_processes.yml`` to directly register remote WPS providers that will dynamically
  fetch underlying WPS processes, instead of static per-service processes stored locally.
- Add field ``visible`` to ``wps_processes.yml`` entries to allow directly defining the registered processes visibility.
- Adjust response of remote provider processes to return the same format as local processes.

Fixes:
------
- Fix ``stdout``/``stderr`` log file not permitted directly within `CWL` `Workflow` (must be inside intermediate steps).
- Fix missing `S3` bucket location constraint within unittests.

.. _changes_1.13.1:

`1.13.1 <https://github.com/crim-ca/weaver/tree/1.13.1>`_ (2020-07-17)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Create an ``stdout.log`` or ``stderr.log`` file in case ``cwltool`` hasn't created it.

.. _changes_1.13.0:

`1.13.0 <https://github.com/crim-ca/weaver/tree/1.13.0>`_ (2020-07-15)
========================================================================

Changes:
--------
- Add `AWS` `S3` bucket support for process input reference files.
- Add ``weaver.wps_output_s3_bucket`` setting to upload results to AWS S3 bucket instead of local directory.
- Add ``weaver.wps_output_s3_region`` setting to allow override parameter extracted from `AWS` profile otherwise.
- Add more documentation about supported file reference schemes.
- Add documentation references to `ESGF-CWT Compute API`.
- Add conditional input file reference fetching (depending on `ADES`/`EMS`, process *type*  from `CWL` ``hints``)
  to take advantage of *request-options* and all supported scheme formats by `Weaver`, instead of relying on `PyWPS`
  and/or `CWL` wherever how far downstream the URL reference was reaching.

Fixes:
------
- Adjust some docstrings to better indicate raised errors.
- Adjust ``weaver.processes.wps_package.WpsPackage`` to use its internal logger when running the process in order to
  preserve log entries under its job execution. They were otherwise lost over time across all process executions.

.. _changes_1.12.0:

`1.12.0 <https://github.com/crim-ca/weaver/tree/1.12.0>`_ (2020-07-03)
========================================================================

Changes:
--------
- Add multiple `CWL` `ESGF` processes and workflows, namely ``SubsetNASAESGF``, ``SubsetNASAESGF`` and many more.
- Add tests for `ESGF` processes and workflows.
- Add documentation for ``ESGF-CWTRequirement`` processes.
- Add ``file2string_array`` and ``metalink2netcdf`` builtins.
- Add ``esgf_process`` ``Wps1Process`` extension, to handle ``ESGF-CWTRequirement`` processes and workflows.

Fixes:
------
- Reset ``MongoDatabase`` connection when we are in a forked process.

.. _changes_1.11.0:

`1.11.0 <https://github.com/crim-ca/weaver/tree/1.11.0>`_ (2020-07-02)
========================================================================

Changes:
--------
- Generate Weaver OpenAPI specification for readthedocs publication.
- Add some sections for documentation (`#61 <https://github.com/crim-ca/weaver/issues/61>`_).
- Add support of documentation RST file redirection to generated HTML for reference resolution in both Github source
  and Readthedocs served pages.
- Improve documentation links, ReadTheDocs format and TOC references.
- Avoid logging ``stdout/stderr`` in workflows.
- Add tests to make sure processes ``stdout/stderr`` are logged.
- Remove Python 2.7 version as not *officially* supported.
- Move and update WPS status location and status check functions into ``weaver.wps`` module.

Fixes:
------
- Fix reported WPS status location to handle when starting with ``/`` although not representing an absolute path.

.. _changes_1.10.1:

`1.10.1 <https://github.com/crim-ca/weaver/tree/1.10.1>`_ (2020-06-03)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Pin ``celery==4.4.2`` to avoid import error on missing ``futures.utils`` called internally in following versions.

.. _changes_1.10.0:

`1.10.0 <https://github.com/crim-ca/weaver/tree/1.10.0>`_ (2020-06-03)
========================================================================

Changes:
--------
- Add support of value-typed metadata fields for process description.
- Enforce ``rel`` field when specifying an ``href`` JSON link to match corresponding XML requirement.

Fixes:
------
- Add more examples of supported WPS endpoint metadata (fixes `#84 <https://github.com/crim-ca/weaver/issues/84>`_).

.. _changes_1.9.0:

`1.9.0 <https://github.com/crim-ca/weaver/tree/1.9.0>`_ (2020-06-01)
========================================================================

Changes:
--------

- Add ``weaver.wps_workdir`` configuration setting to define the location where the underlying ``cwltool`` application
  should be executed under. This can allow more control over the scope of the mounted volumes for *Application Package*
  running a docker image.
- Add mapping of WPS results from the ``Job``'s UUID to generated `PyWPS` UUID for outputs, status and log locations.
- Add *experimental* configuration settings ``weaver.cwl_euid`` and ``weaver.cwl_egid`` to provide effective user/group
  identifiers to employ when running the CWL *Application Package*. Using these require good control of the directory
  and process I/O locations as invalid permissions could break a previously working job execution.
- Add more logging configuration and apply them to ``cwltool`` before execution of *Application Package*.
- Enforce ``no_match_user=False`` and ``no_read_only=False`` of ``cwltool``'s ``RuntimeContext`` to ensure that docker
  application is executed with same user as ``weaver`` and that process input files are not modified inplace (readonly)
  where potentially inaccessible (according to settings). Definition of `CWL` package will need to add
  `InitialWorkDirRequirement <https://www.commonwl.org/v1.0/CommandLineTool.html#InitialWorkDirRequirement>`_ as per
  defined by reference specification to stage those files if they need to be accessed with write permissions
  (see: `example <https://www.commonwl.org/user_guide/topics/staging-input-files.html>`_).
  Addresses some issues listed in `#155 <https://github.com/crim-ca/weaver/issues/155>`_.
- Enforce removal of some invalid `CWL` hints/requirements that would break the behaviour offered by ``Weaver``.
- Use ``weaver.request_options`` for `WPS GetCapabilities` and `WPS Check Status` requests under the running job.
- Change default ``DOCKER_REPO`` value defined in ``Makefile`` to point to reference mentioned in ``README.md`` and
  considered as official deployment location.
- Add ``application/x-cwl`` MIME-type supported with updated ``EDAM 1.24`` ontology.
- Add ``application/x-yaml``  MIME-type to known formats.
- Add ``application/x-tar`` and ``application/tar+gzip`` MIME-type (not official) but resolved as *synonym*
  ``application/gzip`` (official) to preserve compressed file support during `CWL` format validation.

Fixes:
------

- Set ``get_cwl_file_format`` default argument ``must_exist=True`` instead of ``False`` to retrieve original default
  behaviour of the function. Since `CWL` usually doesn't need to add ``File.format`` field when no corresponding
  reference actually exists, this default also makes more sense.

.. _changes_1.8.1:

`1.8.1 <https://github.com/crim-ca/weaver/tree/1.8.1>`_ (2020-05-22)
========================================================================

Changes:
--------

- Add `Travis-CI` smoke test of built docker images for early detection of invalid setup or breaking code to boot them.
- Add `Travis-CI` checks for imports. This check was not validated previously although available.
- Adjust ``weaver.ini.example`` to reflect working demo server configuration (employed by smoke test).
- Move ``weaver`` web application to ``weaver.app`` to reduce chances of breaking ``setup.py`` installation from import
  errors due to ``weaver`` dependencies not yet installed. Redirect to new location makes this change transparent when
  loaded with the usual ``weaver.ini`` configuration.

Fixes:
------

- Fix base docker image to install Python 3 development dependencies in order to compile requirements with expected
  environment Python version. Package ``python-dev`` for Python 2 was being installed instead.
- Fix failing docker image boot due to incorrectly placed ``yaml`` import during setup installation.
- Fix imports according to ``Makefile`` targets ``check-imports`` and ``fix-imports``.
- Fix parsing of ``PyWPS`` metadata to correctly employ values provided by ``weaver.ini``.

.. _changes_1.8.0:

`1.8.0 <https://github.com/crim-ca/weaver/tree/1.8.0>`_ (2020-05-21)
========================================================================

Changes:
--------

- Modify ``weaver.utils.request_retry`` to ``weaver.utils.request_extra`` to include more requests functionality and
  reuse it across the whole code base.
- Add ``requests_extra`` SSL verification option using specific URL regex(es) matches from configuration settings.
- Add ``file://`` transport scheme support directly to utility ``requests_extra`` to handle local file paths.
- Add file ``weaver.request_options`` INI configuration setting to specify per-request method/URL options.
- Add ``requests_extra`` support of ``Retry-After`` response header (if any available on ``429`` status) which indicates
  how long to wait until next request to avoid automatically defined response right after.
- Add ``weaver.wps_workdir`` configuration setting with allow setting corresponding ``pywps.workdir`` directory.

Fixes:
------

- Modify ``Dockerfile-manager`` to run web application using ``pserve`` as ``gunicorn`` doesn't correctly handles
  worker options anymore when loaded form ``weaver.ini`` with ``--paste`` argument. Also simplifies the command which
  already required multiple patches such as reapplying the host/port binding from INI file.
- Fix handling of Literal Data I/O ``type`` when retrieved from ``OWSLib.wps`` object with remote WPS XML body.
- Adjust ``make start`` target to use new ``make install-run`` target which installs the dependencies and package in
  edition mode so that configuration files present locally can be employed for running the application.
  Previously, one would have to move their configurations to the ``site-package`` install location of the active Python.
- Fix ``celery>4.2`` not found because of application path modification.
- Fix invalid handling of ``wps_processes.yml`` reference in ``weaver.ini`` when specified as relative path to
  configuration directory.
- Fix handling of ``WPS<->CWL`` I/O merge of ``data_format`` field against ``supported_formats`` with ``pywps>=4.2.4``.
- Fix installation of ``yaml``-related packages for Python 2 backward compatibility.

.. _changes_1.7.0:

`1.7.0 <https://github.com/crim-ca/weaver/tree/1.7.0>`_ (2020-05-15)
========================================================================

Changes:
--------

- Add additional status log for ``EOImage`` input modification with `OpenSearch` during process execution.
- Add captured ``stderr/stdout`` logging of underlying `CWL` application being executed to resulting ``Job`` logs
  (addresses first step of `#131 <https://github.com/crim-ca/weaver/issues/131>`_).
- Use ``weaver.utils.request_retry`` in even more places and extend convenience arguments offered by it to adapt it to
  specific use cases.

Fixes:
------

- Fix handling of WPS-REST output matching a JSON file for multiple-output format specified with a relative local path
  as specified by job output location. Only remote HTTP references where correctly parsed. Also avoid failing the job if
  the reference JSON parsing fails. It will simply return the original reference URL in this case without expanded data
  (relates to `#25 <https://github.com/crim-ca/weaver/issues/25>`_).
- Fix `CWL` job logs to be timezone aware, just like most other logs that will report UTC time.
- Fix JSON response parsing of remote provider processes.
- Fix parsing of `CWL` ordered parsing when I/O is specified as shorthand ``"<id>":"<type>"`` directly under the
  ``inputs`` or ``outputs`` dictionary instead of extended JSON object variant such as
  ``{"input": {"type:" "<type>", "format": [...]}}`` (fixes `#137 <https://github.com/crim-ca/weaver/issues/137>`_).

.. _changes_1.6.0:

`1.6.0 <https://github.com/crim-ca/weaver/tree/1.6.0>`_ (2020-05-07)
========================================================================

Changes:
--------

- Reuse ``weaver.utils.request_retry`` function across a few locations that where essentially reimplementing
  the core functionality.
- Add even more failure-permissive request attempts when validating a MIME-type against IANA website.
- Add auto-resolution of common extensions known under `PyWPS` as well as employing their specific encoding.
- Add ``geotiff`` format type support via `PyWPS` (`#100 <https://github.com/crim-ca/weaver/issues/100>`_).
- Make WPS status check more resilient to failing WPS outputs location not found in case the directory path can be
  resolved to a valid local file representing the XML status (i.e.: don't depend as much on the HTTP WPS output route).
- Ensure backward support of generic/default ``text/plain`` I/O when extracted from a referenced WPS-1/2 XML remote
  process which provides insufficient format details. For CWL output generated from it, replace the glob pattern to
  match anything (``<id>.*``) instead of ``<id>.txt`` extracted from ``text/plain`` to simulate MIME-type as ``*/*``.
  Issue log warning message for future use cases.

Fixes:
------

- Fix invalid ``AllowedValue`` parsing when using ``LiteralData`` inputs that resulted in ``AnyValue`` being parsed
  as a ``"None"`` string. This was transparent in case of string inputs and breaking for other types like integer when
  they attempted conversion.
- Fix erroneous ``Metadata`` keywords passed down to ``owslib.wps.Metadata`` objects in case of more verbose detailed
  not allowed by this implementation.
- Fix parsing of explicitly-typed optional array CWL I/O notation that was not considered
  (i.e.: using ``type`` as list with additional ``"null"`` instead of ``type: "<type>?"`` shorthand).
- Fix parsing of MIME-type from ``format`` field to exclude additional parameters (e.g.: ``; charset=UTF-8`` for
  remote IANA validation.

.. _changes_1.5.1:

`1.5.1 <https://github.com/crim-ca/weaver/tree/1.5.1>`_ (2020-03-26)
========================================================================

Changes:
--------

- Add unittest of utility function ``fetch_file``.
- Split some unittest utility functions to allow more reuse.

Fixes:
------

- Fix invalid ``retry`` parameter not handled automatically by request.

.. _changes_1.5.0:

`1.5.0 <https://github.com/crim-ca/weaver/tree/1.5.0>`_ (2020-03-25)
========================================================================

Changes:
--------

- Adjust incorrectly parsed href file reference as WPS complex input which resulted in failing location retrieval.
- Partially address unnecessary fetch of file that has to be passed down to CWL, which will in turn request the file
  as required. Need update from PyWPS to resolve completely
  (`#91 <https://github.com/crim-ca/weaver/issues/91>`_,
  `geopython/pywps#526 <https://github.com/geopython/pywps/issues/526>`_).
- Adjust WPS output results to use relative HTTP path in order to recompose the output URL if server settings change.
- Support WPS output results as value (WPS literal data). Everything was considered an href file beforehand.
- Add additional ``timeout`` and ``retry`` during fetching of remote file for process ``jsonarray2netcdf`` to avoid
  unnecessary failures during edge case connexion problems.
- Add support of ``title`` and ``version`` field of ``builtin`` processes.

Fixes:
------

- Patch ``builtin`` process execution failing since ``cwltool 2.x`` update.
- Avoid long fetch operation using streamed request that defaulted to chuck size of 1.
  Now, we use an appropriate size according to available memory.

.. _changes_1.4.0:

`1.4.0 <https://github.com/crim-ca/weaver/tree/1.4.0>`_ (2020-03-18)
========================================================================

Changes:
--------

- Update owslib to 0.19.2
- Drop support for python 3.5

.. _changes_1.3.0:

`1.3.0 <https://github.com/crim-ca/weaver/tree/1.3.0>`_ (2020-03-10)
========================================================================

Changes:
--------

- Provide a way to override the external URL reported by `WPS-1/2` and `WPS-REST` via configuration settings allowing
  for more advanced server-side results in response bodies.

.. _changes_1.2.0:

`1.2.0 <https://github.com/crim-ca/weaver/tree/1.2.0>`_ (2020-03-06)
========================================================================

Changes:
--------

- Add `WPS` languages for other wps requests types: ``DescribeProcess`` and ``GetCapabilities``.

Fixes:
------

- Fix a bug where the validation of ``OneOf`` items was casting the value to the first valid possibility.

.. _changes_1.1.0:

`1.1.0 <https://github.com/crim-ca/weaver/tree/1.1.0>`_ (2020-02-17)
========================================================================

Changes:
-------------

- Simplify docker image generation and make base/manager/worker variants all available under the same docker
  repo `docker-registry.crim.ca/ogc/weaver <docker-registry.crim.ca/ogc/weaver>`_  with different tags
  (`#5 <https://github.com/crim-ca/weaver/issues/5>`_).
- Add *planned future support* of ``Accept-Language`` header for `WPS-1/2` (``geopython/OWSLib 0.20.0``)
  (`#74 <https://github.com/crim-ca/weaver/issues/74>`_).
- Improved job logs update with message and progress to allow better tracking of internal operations and/or problems.
- Allow WPS builtin process ``jsonarray2netcdf`` to fetch a remote file.
- Change doc to point to DockerHub |pavics_weaver|_ images.
- Adjust CI rule long-lasting failures until it gets patched by original reference
  (`gitleaks-actions#3 <https://github.com/eshork/gitleaks-action/issues/3>`_).

Fixes:
-------------

- Fix `readthedocs <https://img.shields.io/readthedocs/pavics-weaver>`_ documentation generation.
- Fix ``.travis`` docker image build condition.
- Fix ``geopython/OWSLib>=0.19.1`` requirement for Python 3.8 support
  (`#62 <https://github.com/crim-ca/weaver/issues/62>`_).
- Fix job update filling due to status location incorrectly resolved according to configured PyWPS output path.

.. _changes_1.0.0:

`1.0.0 <https://github.com/crim-ca/weaver/tree/1.0.0>`_ (2020-01-28)
========================================================================

New Features:
-------------

- Add ``notification_email`` field to ``Job`` datatype that stores an encrypted email (according to settings) when
  provided in the job submission body (`#44 <https://github.com/crim-ca/weaver/issues/44>`_).
- Add ability to filter jobs with ``notification_email`` query parameter
  (`#44 <https://github.com/crim-ca/weaver/issues/44>`_).
- Add jobs statistics grouping by specific fields using comma-separated list ``groups`` query parameter
  (`#46 <https://github.com/crim-ca/weaver/issues/46>`_).
- Add some tests to evaluate new job search methods / grouping results and responses
  (`#44 <https://github.com/crim-ca/weaver/issues/44>`_, `#46 <https://github.com/crim-ca/weaver/issues/46>`_).
- Add handling of multiple `CWL` field ``format`` for ``File`` type.
- Add missing ontology reference support for `CWL` field ``format`` by defaulting to `IANA` namespace.
- Add support for I/O ``array`` of ``enum`` (ie: multiple values of ``AllowedValues`` for a given input)
  (`#30 <https://github.com/crim-ca/weaver/issues/30>`_).
- Add support of ``label`` synonym as ``title`` for inputs and process description
  (`CWL` specifying a ``label`` will set it in `WPS` process)
  (`#31 <https://github.com/crim-ca/weaver/issues/31>`_)
- Add support of input ``minOccurs`` and ``maxOccurs`` as ``int`` while maintaining ``str`` support
  (`#14 <https://github.com/crim-ca/weaver/issues/14>`_).
- Add conformance route with implementation links (`#53 <https://github.com/crim-ca/weaver/issues/53>`_).
- Add additional landing page link details (`#54 <https://github.com/crim-ca/weaver/issues/54>`_).
- Add ``weaver.wps_restapi.colander_extras.DropableNoneSchema`` to auto-handle some schema JSON deserialization.
- Add ``weaver.wps_restapi.colander_extras.VariableMappingSchema`` to auto-handle some schema JSON deserialization.
- Add more functional tests
  (`#11 <https://github.com/crim-ca/weaver/issues/11>`_, `#17 <https://github.com/crim-ca/weaver/issues/17>`_).

Changes:
-------------

- Use ``bump2version`` and move all config under ``setup.cfg``.
- Remove enforced ``text/plain`` for `CWL` ``File`` when missing ``format`` field.
- Replace bubbling up of too verbose unhandled exceptions (500 Internal Server Error) by summary message and additional
  internal logging for debugging the cause using an utility exception log decorator.
- Use the same exception log decorator to simplify function definitions when HTTP exceptions are already handled.
- Make ``null`` reference a singleton so that multiple instantiation calls all refer to the same instance and produce
  the expected behaviour of ``<x> is null`` instead of hard-to-identify errors because of english syntax.
- Remove unused function ``weaver.utils.replace_caps_url`` and corresponding tests.
- Remove ``weaver.processes.utils.jsonify_value`` duplicated by ``weaver.processes.wps_package.complex2json``.
- Use more JSON body schema validation using API schema definitions deserialization defined by ``weaver.datatype``.
- Enforce ``builtin`` processes registration on startup to receive applicable updates.
- Provide 2 separate docker images for `Weaver` *manager* and *worker*, corresponding to the `EMS/ADES` API and the
  ``celery`` job runner respectively.
- Update Apache license.

Fixes:
-------------

- Adjust some typing definitions incorrectly specified.
- Fix some failing functionality tests
  (`#11 <https://github.com/crim-ca/weaver/issues/11>`_, `#17 <https://github.com/crim-ca/weaver/issues/17>`_).
- Fix I/O field ordering preserved as specified in payload or loaded reference file.
- Fix setting ``minOccurs=0`` when a ``default`` is specified in the corresponding `CWL` I/O
  (`#17 <https://github.com/crim-ca/weaver/issues/17>`_, `#25 <https://github.com/crim-ca/weaver/issues/25>`_).
- Fix incorrectly overridden ``maxOccurs="unbounded"`` by ``maxOccurs="1"`` when a partial array input definition
  is specified without explicit ``maxOccurs`` in `WPS` payload
  (`#17 <https://github.com/crim-ca/weaver/issues/17>`_, `#25 <https://github.com/crim-ca/weaver/issues/25>`_).
- Fix case where omitted ``format[s]`` in both `CWL` and `WPS` deploy bodies generated a process description with
  complex I/O (file) without required ``formats`` field. Default ``text/plain`` format is now automatically added.
- Fix case where ``format[s]`` lists between `CWL` and `WPS` where incorrectly merged.
- Fix ``metadata`` field within a WPS I/O incorrectly parsed when provided by a WPS-1/2 `XML` process definition.
- Fix invalid JSON response formatting on failing schema validation of process deployment body.
- Fix docker images to support ``pserve`` when using ``gunicorn>=20.x`` dropping support of ``--paste`` config feature.
- Fix multiple Python 2/3 compatibility issues.

.. _changes_0.2.2:

`0.2.2 <https://github.com/crim-ca/weaver/tree/0.2.2>`_ (2019-05-31)
========================================================================

- Support notification email subject template.

.. _changes_0.2.1:

`0.2.1 <https://github.com/crim-ca/weaver/tree/0.2.1>`_ (2019-05-29)
========================================================================

- Add per-process email notification template.

.. _changes_0.2.0:

`0.2.0 <https://github.com/crim-ca/weaver/tree/0.2.0>`_ (2019-03-26)
========================================================================

- Fixes to handle invalid key characters ``"$"`` and ``"."`` during `CWL` package read/write operations to database.
- Fixes some invalid `CWL` package generation from `WPS-1` references.
- More cases handled for `WPS-1` to `CWL` ``WPS1Requirement`` conversion
  (``AllowedValues``, ``Default``, ``SupportedFormats``, ``minOccurs``, ``maxOccurs``).
- Add file format validation to generated `CWL` package from `WPS-1` `MIME-types`.
- Allow auto-deployment of `WPS-REST` processes from `WPS-1` references specified by configuration.
- Add many deployment and execution validation tests for ``WPS1Requirement``.
- Add ``builtin`` application packages support for common operations.

.. _changes_0.1.3:

`0.1.3 <https://github.com/crim-ca/weaver/tree/0.1.3>`_ (2019-03-07)
=============================================================================

- Add useful `Makefile` targets for deployment.
- Add badges indications in ``README.rst`` for tracking from repo landing page.
- Fix security issue of PyYAML requirement.
- Fix some execution issues for ``Wps1Process``.
- Fix some API schema erroneous definitions.
- Additional logging of unhandled errors.
- Improve some typing definitions.

.. _changes_0.1.2:

`0.1.2 <https://github.com/crim-ca/weaver/tree/0.1.2>`_ (2019-03-05)
=============================================================================

- Introduce ``WPS1Requirement`` and corresponding ``Wps1Process`` to run a `WPS-1` process under `CWL`.
- Remove `mongodb` requirement, assume it is running on an external service or docker image.
- Add some typing definitions.
- Fix some problematic imports.
- Fix some PEP8 issues and PyCharm warnings.

.. _changes_0.1.1:

`0.1.1 <https://github.com/crim-ca/weaver/tree/0.1.1>`_ (2019-03-04)
=============================================================================

- Modify `Dockerfile` to use lighter ``debian:latest`` instead of ``birdhouse/bird-base:latest``.
- Modify `Dockerfile` to reduce build time by reusing built image layers (requirements installation mostly).
- Make some `buildout` dependencies optional to also reduce build time and image size.
- Some additional striping of deprecated or invalid items from `Twitcher`_.

.. _changes_0.1.0:

`0.1.0 <https://github.com/crim-ca/weaver/tree/0.1.0>`_ (2019-02-26)
=============================================================================

- Initial Release. Based off `Twitcher`_ tag `ogc-0.4.7`.

.. _Twitcher: https://github.com/Ouranosinc/Twitcher

.. |pavics_weaver| replace:: pavics/weaver
.. _pavics_weaver: https://hub.docker.com/r/pavics/weaver/tags
