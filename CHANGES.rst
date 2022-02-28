.. :changelog:

Changes
*******

.. **REPLACE AND/OR ADD SECTION ENTRIES ACCORDINGLY WITH APPLIED CHANGES**

.. _changes_latest:

`Unreleased <https://github.com/crim-ca/weaver/tree/master>`_ (latest)
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
.. _ogc-app-pkg: https://github.com/opengeospatial/ogcapi-processes/blob/master/extensions/deploy_replace_undeploy/standard/openapi/schemas/ogcapppkg.yaml

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
  resolves `DAC-198 <https://www.crim.ca/jira/browse/DAC-198>`_,
  relates to `DAC-203 <https://www.crim.ca/jira/browse/DAC-203>`_).
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
  and incorrectly anchored as following ``process-esgf-cwt`` section.

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
  of ``minDuration`` and ``maxDuration``. Please refer to :ref:`database_migration`
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
  specified by OGP-API instead of old listing format ``[{"id": "<id-value>", <key:val parameters>}]``. The old
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
  (relates to `#211  <https://github.com/crim-ca/weaver/issues/211>`_).
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
  <https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/format.yaml>`_) such that only
  URL formatted strings are allowed, or alternatively an explicit JSON definition. Previous definitions that would
  indicate an empty string schema are dropped since ``schema`` is optional.
- Block unknown and ``builtin`` process types during deployment from the API
  (fixes `#276  <https://github.com/crim-ca/weaver/issues/276>`_).
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
  (relates to `#263  <https://github.com/crim-ca/weaver/issues/263>`_).
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
  (fixes `#263  <https://github.com/crim-ca/weaver/issues/263>`_).
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
  `#602 <https://github.com/geopython/pywps/pull/602>`_
  (specifically `commit 343d825 <https://github.com/geopython/pywps/commit/343d82539576b1e73eee3102654749c3d3137cff>`_),
  which broke the ``ComplexInput`` work-around to avoid useless of file URLs
  (see issue `#526 <https://github.com/geopython/pywps/issues/526>`_).
- Fix default execution mode specification in process job control options
  (fixes `#182 <https://github.com/opengeospatial/ogcapi-processes/pull/182>`_).
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
  patch on ``null`` since fix `#507 <https://github.com/geopython/pywps/pull/507>`_ not released at this point).
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
  (see: `example <https://www.commonwl.org/user_guide/15-staging/>`_). Addresses some issues listed in
  `#155 <https://github.com/crim-ca/weaver/issues/155>`_.
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
- Change doc to point to DockerHub `pavics/weaver <https://hub.docker.com/r/pavics/weaver>`_ images.
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
