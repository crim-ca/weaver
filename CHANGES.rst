.. :changelog:

Changes
*******

.. **REPLACE AND/OR ADD SECTION ENTRIES ACCORDINGLY WITH APPLIED CHANGES**

`Unreleased <https://github.com/crim-ca/weaver/tree/master>`_ (latest)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix copy of headers when generating the WPS clients created for listing providers capabilities and processes.
- Fix ``weaver.datatype`` objects auto-resolution of fields using either attributes (accessed as ``dict``)
  or properties (accessed as ``class``) to ensure correct handling of additional operations on them.

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
- No change.

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

`3.2.1 <https://github.com/crim-ca/weaver/tree/3.2.1>`_ (2021-06-08)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Fix backward compatibility of pre-deployed processes that did not define ``jobControlOptions`` that is now required.
  Missing definition are substituted in-place by default ``["execute-async"]`` mode.

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

`2.2.0 <https://github.com/crim-ca/weaver/tree/2.2.0>`_ (2021-03-03)
========================================================================

Changes:
--------
- Add ``weaver.wps.utils.get_wps_client`` function to handle the creation of ``owslib.wps.WebProcessingService`` client
  with appropriate request options configuration from application settings.

Fixes:
------
- Fix job percent progress reported in logs to be more consistent with actual execution of the process
  (fixes `#90 <https://github.com/crim-ca/weaver/issues/90>`_).
- Fix `Job` duration not stopped incrementing when its execution failed due to raised error
  (fixes `#222 <https://github.com/crim-ca/weaver/issues/222>`_).
- Improve race condition handling of ``builtin`` process registration at application startup.

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

`1.13.1 <https://github.com/crim-ca/weaver/tree/1.13.1>`_ (2020-07-17)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Create an ``stdout.log`` or ``stderr.log`` file in case ``cwltool`` hasn't created it.

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

`1.10.1 <https://github.com/crim-ca/weaver/tree/1.10.1>`_ (2020-06-03)
========================================================================

Changes:
--------
- No change.

Fixes:
------
- Pin ``celery==4.4.2`` to avoid import error on missing ``futures.utils`` called internally in following versions.

`1.10.0 <https://github.com/crim-ca/weaver/tree/1.10.0>`_ (2020-06-03)
========================================================================

Changes:
--------
- Add support of value-typed metadata fields for process description.
- Enforce ``rel`` field when specifying an ``href`` JSON link to match corresponding XML requirement.

Fixes:
------
- Add more examples of supported WPS endpoint metadata (fixes `#84 <https://github.com/crim-ca/weaver/issues/84>`_).

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

`1.5.1 <https://github.com/crim-ca/weaver/tree/1.5.1>`_ (2020-03-26)
========================================================================

Changes:
--------

- Add unittest of utility function ``fetch_file``.
- Split some unittest utility functions to allow more reuse.

Fixes:
------

- Fix invalid ``retry`` parameter not handled automatically by request.

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

`1.4.0 <https://github.com/crim-ca/weaver/tree/1.4.0>`_ (2020-03-18)
========================================================================

Changes:
--------

- Update owslib to 0.19.2
- Drop support for python 3.5

`1.3.0 <https://github.com/crim-ca/weaver/tree/1.3.0>`_ (2020-03-10)
========================================================================

Changes:
--------

- Provide a way to override the external URL reported by `WPS-1/2` and `WPS-REST` via configuration settings allowing
  for more advanced server-side results in response bodies.

`1.2.0 <https://github.com/crim-ca/weaver/tree/1.2.0>`_ (2020-03-06)
========================================================================

Changes:
--------

- Add `WPS` languages for other wps requests types: ``DescribeProcess`` and ``GetCapabilities``.

Fixes:
------

- Fix a bug where the validation of ``OneOf`` items was casting the value to the first valid possibility.

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

`0.2.2 <https://github.com/crim-ca/weaver/tree/0.2.2>`_ (2019-05-31)
========================================================================

- Support notification email subject template.

`0.2.1 <https://github.com/crim-ca/weaver/tree/0.2.1>`_ (2019-05-29)
========================================================================

- Add per-process email notification template.

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

`0.1.3 <https://github.com/crim-ca/weaver/tree/0.1.3>`_ (2019-03-07)
=============================================================================

- Add useful `Makefile` targets for deployment.
- Add badges indications in ``README.rst`` for tracking from repo landing page.
- Fix security issue of PyYAML requirement.
- Fix some execution issues for ``Wps1Process``.
- Fix some API schema erroneous definitions.
- Additional logging of unhandled errors.
- Improve some typing definitions.

`0.1.2 <https://github.com/crim-ca/weaver/tree/0.1.2>`_ (2019-03-05)
=============================================================================

- Introduce ``WPS1Requirement`` and corresponding ``Wps1Process`` to run a `WPS-1` process under `CWL`.
- Remove `mongodb` requirement, assume it is running on an external service or docker image.
- Add some typing definitions.
- Fix some problematic imports.
- Fix some PEP8 issues and PyCharm warnings.

`0.1.1 <https://github.com/crim-ca/weaver/tree/0.1.1>`_ (2019-03-04)
=============================================================================

- Modify `Dockerfile` to use lighter ``debian:latest`` instead of ``birdhouse/bird-base:latest``.
- Modify `Dockerfile` to reduce build time by reusing built image layers (requirements installation mostly).
- Make some `buildout` dependencies optional to also reduce build time and image size.
- Some additional striping of deprecated or invalid items from `Twitcher`_.

`0.1.0 <https://github.com/crim-ca/weaver/tree/0.1.0>`_ (2019-02-26)
=============================================================================

- Initial Release. Based off `Twitcher`_ tag `ogc-0.4.7`.

.. _Twitcher: https://github.com/Ouranosinc/Twitcher
