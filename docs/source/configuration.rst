.. include:: references.rst
.. _configuration:

.. default location to quickly reference items without the explicit and long prefix
.. py:currentmodule:: weaver.config

******************
Configuration
******************

.. contents::
    :local:
    :depth: 2

After you have installed `Weaver`, you can customize its behaviour using multiple configuration settings.

.. _conf_settings:

Configuration Settings
=======================================

All settings are configured using a ``weaver.ini`` configuration file. A `weaver.ini.example`_ file is provided
with default values to help in the configuration process. Explanations of respective settings are also available in
this example file.

The configuration file tell the application runner (e.g. `Gunicorn`_, ``pserve`` or similar WSGI HTTP Server), how to
execute `Weaver` as well as all settings to provide in order to personalize the application. All settings specific to
`Weaver` employ the format ``weaver.<setting>``.

Most configuration parameters for the *manager* portion of `Weaver` (i.e.: WSGI HTTP server for API endpoints) are
defined in the ``[app:main]`` section of `weaver.ini.example`_, while parameters specific to the *worker* (task queue
handler) are within ``[celery]`` section. Note that multiple settings are shared between the two applications, such as
the ``mongodb.[...]`` configuration or ``weaver.configuration`` options. When parameters are shared, they are usually
expected to be placed in ``[app:main]`` section.

Following is a partial list of most predominant settings specific to `Weaver`. Many parameters provide alternative or
extended functionality when employed in conjunction with other settings. Others are sometimes not necessarily required
to be defined if *default* behaviour is desired. Refer to the relevant details that will describe in which condition
they are optional and which default value or operation is applied in each situation.

.. note::
    Refer to `weaver.ini.example`_ for the extended list of applicable settings.
    Some advanced configuration settings are also described in other sections of this page.

.. _weaver-configuration:

- | ``weaver.configuration = ADES|EMS|HYBRID|DEFAULT``
  | (default: ``DEFAULT``)
  |
  | Tells the application in which mode to run.
  |
  | Enabling ``ADES`` for instance will disable some ``EMS``-specific operations such as dispatching :ref:`Workflow`
    process steps to known remote ``ADES`` servers. ``ADES`` should be used to *only* run processes locally
    (as the working unit). ``EMS`` will *always* dispatch execution of jobs to other ``ADES`` except for :ref:`Workflow`
    processes that chains them.
  |
  | When ``HYBRID`` is specified, `Weaver` will assume both ``ADES`` and ``EMS`` roles simultaneously, meaning it will
    be able to execute local processes by itself and monitor dispatched execution of registered remote providers.
  |
  | Finally, ``DEFAULT`` configuration will provide very minimalistic operations as all other modes will be unavailable.

- | ``weaver.url = <url>``
  | (default: ``http://localhost:4001``)
  |
  | Defines the full URL (including HTTP protocol/scheme, hostname and optionally additional path suffix) that will
    be used as base URL for all other URL settings of `Weaver`.

  .. note::

    This is the URL that you want displayed in responses (e.g.: ``processDescriptionURL`` or job ``location``).
    For the effective URL employed by the WSGI HTTP server, refer to ``[server:main]`` section of `weaver.ini.example`_.

.. _weaver-schema-url:

- | ``weaver.schema_url = <url>``
  | (default: ``${weaver.url}/json#/definitions``)
  |
  | Defines the base URL of schemas to be reported in responses.
  |
  | When not provided, the running Web Application instance OpenAPI JSON path will be employed to refer to the
    schema ``definitions`` section. The configuration setting is available to override this endpoint by another
    static URL location where the corresponding schemas can be found if desired.

  .. versionadded:: 4.0

.. _weaver-cwl-euid:

- | ``weaver.cwl_euid = <int>`` [:class:`int`, *experimental*]
  | (default: ``None``, auto-resolved by :term:`CWL` with effective machine user)
  |
  | Define the effective machine user ID to be used for running the :term:`Application Package`.

  .. versionadded:: 1.9

.. _weaver-cwl-egid:

- | ``weaver.cwl_egid = <int>`` [:class:`int`, *experimental*]
  | (default: ``None``, auto-resolved by :term:`CWL` with the group of the effective user)
  |
  | Define the effective machine group ID to be used for running the :term:`Application Package`.

  .. versionadded:: 1.9

.. _weaver-wps:

- | ``weaver.wps = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enables the WPS-1/2 endpoint.

  .. seealso::
    :ref:`wps_endpoint`

  .. warning::

     At the moment, this setting must be ``true`` to allow :term:`Job` execution as the worker monitors this endpoint.
     This could change with future developments (see issue `#21 <https://github.com/crim-ca/weaver/issues/21>`_).

.. _weaver-wps-path:

- | ``weaver.wps_path = <url-path>``
  | ``weaver.wps_url = <full-url>``
  | (default: *path* ``/ows/wps``)
  |
  | Defines the URL to employ as WPS-1/2 endpoint.
  |
  | It can either be the explicit *full URL* to use or the *path* relative to ``weaver.url``.
  | Setting ``weaver.wps_path`` is ignored if its URL equivalent is defined.
  | The *path* variant **SHOULD** start with ``/`` for appropriate concatenation with ``weaver.url``, although this is
    not strictly enforced.

.. _weaver-wps-output-s3-bucket:

- | ``weaver.wps_output_s3_bucket = <s3-bucket-name>``
  | (default: ``None``)
  |
  | AWS S3 bucket where to store WPS outputs. Used in conjunction with ``weaver.wps_output_s3_region``.
  |
  | When this parameter is defined, any job result generated by a process execution will be stored (uploaded)
    to that location. If no bucket is specified, the outputs fall back to using the location specified by
    ``weaver.wps_output_dir``.

  .. versionadded:: 1.13
  .. seealso::
    :ref:`conf_s3_buckets`

.. _weaver-wps-output-s3-region:

- | ``weaver.wps_output_s3_region = <s3-region-name>``
  | (default: ``None``, any :term:`S3` |region| amongst :data:`mypy_boto3_s3.literals.RegionName`)
  |
  | AWS S3 region to employ for storing WPS outputs. Used in conjunction with ``weaver.wps_output_s3_bucket``.
  |
  | When this parameter is defined as well as ``weaver.wps_output_s3_bucket``, it is employed to define which :term:`S3`
    to write output files to. If not defined but ``weaver.wps_output_s3_bucket`` is specified, `Weaver` attempt to
    retrieve the region from the profile defined in :term:`AWS` configuration files or environment variables.

  .. versionadded:: 1.13
  .. seealso::
    :ref:`conf_s3_buckets`

.. _weaver-wps-output-dir:

- | ``weaver.wps_output_dir = <directory-path>``
  | (default: *path* ``/tmp``)
  |
  | Location where WPS outputs (results from :term:`Job`) will be stored for stage-out.
  |
  | When ``weaver.wps_output_s3_bucket`` is specified, only :term:`WPS` :term:`XML` status and log files are stored
    under this path. Otherwise, :term:`Job` results are also located under this directory with a sub-directory named
    with the :term:`Job` ID.
  | This directory should be mapped to `Weaver`'s :term:`WPS` output URL to serve them externally as needed.

  .. versionchanged:: 4.3
    The output directory could be nested under a *contextual directory* if requested during :term:`Job` submission.
    See :ref:`exec_output_location` and below ``weaver.wps_output_context`` parameter for more details.

.. _weaver-wps-output-context:

- | ``weaver.wps_output_context = <sub-directory-path>``
  | (default: ``None``)
  |
  | Default sub-directory hierarchy location to nest :term:`WPS` outputs (:term:`Job` results) under.
  |
  | If defined, this parameter is used as substitute *context* when ``X-WPS-Output-Context`` header is omitted.
    When not defined, ``X-WPS-Output-Context`` header can still take effect, but omitting it will store results
    directly under ``weaver.wps_output_dir`` instead of default *context* location.

  .. versionadded:: 4.3

  .. versionchanged:: 4.27
    Nesting of the *context* directory from ``X-WPS-Output-Context`` or ``weaver.wps_output_dir`` will
    also take effect when storing :term:`Job` results under :term:`S3` when ``weaver.wps_output_s3_bucket``
    and ``weaver.wps_output_s3_region`` are also defined. Previous versions applied the *context* directory
    only for local storage using the other :term:`WPS` output settings.

  .. seealso::
    See :ref:`exec_output_location` for more details about this feature and implications of this setting.

.. _weaver-wps-output-path:
.. _weaver-wps-output-url:

- | ``weaver.wps_output_path = <url-path>``
  | ``weaver.wps_output_url = <full-url>``
  | (default: *path* ``/wpsoutputs``)
  |
  | Endpoint that will be employed as prefix to refer to :term:`WPS` outputs (:term:`Job` results).
  |
  | It can either be the explicit *full URL* to use or the *path* relative to ``weaver.url``.
  | Setting ``weaver.wps_output_path`` is ignored if its URL equivalent is defined.
  | The *path* variant **SHOULD** start with ``/`` for appropriate concatenation with ``weaver.url``, although this is
    not strictly enforced.

  .. note::
    The resulting ``weaver.wps_output_url`` endpoint, whether directly provided or indirectly
    resolved by ``weaver.url`` and ``weaver.wps_output_path`` will not be served by `Weaver` itself.
    This location is returned for reference in API responses, but it is up to the infrastructure that
    hosts `Weaver` service to make this location available online as deemed necessary.

.. _weaver-wps-workdir:

- | ``weaver.wps_workdir = <directory-path>``
  | (default: uses automatically generated temporary directory if none specified)
  |
  | Prefix where process :term:`Job` worker should execute the :term:`Process` from.

.. _weaver-wps-max-request-size:

- | ``weaver.wps_max_request_size = <number-bytes>``
  | (default: ``30MB``)
  |
  | Indicates the maximum allowed size for the contents of a :term:`WPS` request.
  |
  | The value can be indicated with ``xB``, ``xKB``, ``xMB``, ``xGB``, where ``x`` is an integer value.

  .. note::
    The value applies for :term:`OGC API - Processes` requests as well when are they are transferred to the :term:`WPS`
    context. However, the limit will be applied only when executing the :term:`Job` through the :term:`WPS` server.

  .. versionadded:: 5.6

.. _weaver-wps-max-single-input-size:

- | ``weaver.wps_max_single_input_size = <number-bytes>``
  | (default: ``30MB``)
  |
  | Indicates the maximum allowed size for any given input's contents within a :term:`WPS` request.
  |
  | The value can be indicated with ``xB``, ``xKB``, ``xMB``, ``xGB``, where ``x`` is an integer value.

  .. note::
    The value applies for :term:`OGC API - Processes` requests as well when are they are transferred to the :term:`WPS`
    context. However, the limit will be applied only when executing the :term:`Job` through the :term:`WPS` server.

  .. versionadded:: 5.6

.. _weaver-wps-client-headers-filter:

- | ``weaver.wps_client_headers_filter = <headers>``
  | (default: ``Host,``)
  |
  | List of comma-separated case-insensitive headers that will be removed from incoming requests before
  | passing them down to invoke an operation with the corresponding :term:`WPS` provider through the :term:`WPS` client.

  .. versionadded:: 5.1.0

  .. seealso::
    - :func:`weaver.wps.utils.get_wps_client_filtered_headers`
    - :func:`weaver.wps.utils.get_wps_client`

.. _weaver-wps-restapi:

- | ``weaver.wps_restapi = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enable the :term:`WPS-REST` (:term:`OGC API - Processes`) endpoint.

  .. warning::

    `Weaver` looses most, if not all, of its useful features without this, and there won't be much point in using
    it without REST endpoint, but it should technically be possible to run it as :term:`WPS`-1/2 only if desired.

.. |weaver-wps-restapi-html| replace:: ``weaver.wps_restapi_html``
.. _weaver-wps-restapi-html:

- | ``weaver.wps_restapi_html = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enable support of :term:`HTML` responses for :term:`WPS-REST` (:term:`OGC API - Processes`) endpoints.
  |
  | When enabled, endpoints will support ``Accept: text/html`` header and ``?f=html`` query to return contents
    in :term:`HTML` instead of the default :term:`JSON` responses. Otherwise, HTTP ``406 Not Acceptable`` code
    will be returned instead.

  .. versionadded:: 5.7.0

.. _weaver-wps-restapi-html-override-user-agent:

- | ``weaver.wps_restapi_html_override_user_agent = true|false`` [:class:`bool`-like]
  | (default: ``false``)
  |
  | Allows override of the ``Accept`` header with "*visualization formats*" (:term:`HTML`, CSS, images, etc.) when the
    request is detected to originate from a web browser ``User-Agent``.
  |
  | When enabled, requests toward the :term:`WPS-REST` (:term:`OGC API - Processes`) endpoints that support :term:`HTML`
    rendering will still return :term:`JSON` (effectively ignoring the ``Accept`` header) when the request corresponds
    to a web browser ``User-Agent`` (e.g.: Chrome, Firefox, Safari). This feature is provided to allow the :term:`API`
    to respond using the default :term:`JSON` even when the request is performed through web browsers (rather than
    terminals, servers, or programmatic clients). Since web browsers typically specify an ``Accept`` header with
    visualization media-types that combines :term:`HTML` and a fallback ``*/*`` media-type, the responses obtained by
    the :term:`API` can seemingly vary between :term:`JSON` and :term:`HTML` depending on which types each endpoint
    supports. Since not all endpoints support :term:`HTML`, but all support :term:`JSON` which is employed by default
    when both the ``Accept``/``f`` are omitted, the results might appear inconsistent depending from where the request
    was sent from.
  |
  | Note that, when the ``f`` format query parameter is provided, it takes precedence over the ``Accept`` header
    regardless of the ``User-Agent`` value. Therefore, enabling this functionality can still obtain the :term:`HTML`
    rendering by explicitly requesting ``f=html`` in the request. Similarly, another ``User-Agent`` than one
    corresponding to a web browser can also be employed in combination to ``Accept: text/html`` to obtain the
    :term:`HTML` representation when this option is enabled.
  |
  | When this option is disabled (default), no special handling of ``User-Agent`` will be performed. Therefore, a
    request performed through a web browser will typically respond by default in :term:`HTML` for rendering (provided
    that browser indicated the relevant ``Accept: text/html``), whereas other clients will respond in :term:`JSON` by
    default. Explicit response media-types can be requested in both cases using either an explicit ``Accept`` header
    of the desired media-type, or their corresponding ``f`` query format.
  |
  | This option is only applicable when |weaver-wps-restapi-html|_ is enabled. Otherwise, :term:`JSON` responses are
    always employed by default.

  .. versionadded:: 5.7.0

.. _weaver-wps-restapi-path:
.. _weaver-wps-restapi-url:

- | ``weaver.wps_restapi_path = <url-path>``
  | ``weaver.wps_restapi_url = <full-url>``
  | (default: *path* ``/``)
  |
  | Endpoint that will be employed as prefix to refer to :term:`WPS-REST` requests
  | (including but not limited to |ogc-api-proc|_ schemas).
  |
  | It can either be the explicit *full URL* to use or the *path* relative to ``weaver.url``.
  | Setting ``weaver.wps_restapi_path`` is ignored if its URL equivalent is defined.
  | The *path* variant **SHOULD** start with ``/`` for appropriate concatenation with ``weaver.url``, although this is
    not strictly enforced.

.. _weaver-wps-restapi-doc:

- | ``weaver.wps_restapi_doc = <full-url>``
  | (default: ``None``)
  |
  | Location that will be displayed as reference specification document for the service.
  |
  | Typically, this value would be set to a reference similar
    to |ogc-api-proc-part1-spec-html|_ or |ogc-api-proc-part1-spec-pdf|_.
    However, this value is left by default empty to let maintainers chose which specification document is more relevant
    for their own deployment, considering that they might want to support different parts of the extended specification.

.. _weaver-wps-restapi-ref:

- | ``weaver.wps_restapi_ref = <full-url>``
  | (default: ``None``)
  |
  | Location that will be displayed as reference specification :term:`JSON` schema for the service.
  |
  | Typically, this value would be set to a reference similar to |ogc-api-proc-part1-spec-json|_.
    However, this value is left by default empty to let maintainers chose which specification schema is more relevant
    for their own deployment, considering that they might want to support different parts of the extended specification.

.. _weaver-wps-metadata:

- | ``weaver.wps_metadata_[...]`` (multiple settings) [:class:`str`]
  |
  | Metadata fields that will be rendered by either or both the :term:`WPS`-1/2 and :term:`WPS-REST` endpoints
    (:ref:`GetCapabilities <proc_op_getcap>`).

.. _weaver-wps-email:

- | ``weaver.wps_email_[...]`` (multiple settings)
  |
  | Defines configuration of email notification functionality on :term:`Job` status milestones.
  |
  | Encryption settings as well as custom email template locations are available.
    The |default-notify-email-template|_ is employed if none is provided or when specified template
    files or directory cannot be resolved.
  |
  | When looking up for templates within ``weaver.wps_email_notify_template_dir``, the following resolution order is
    followed to attempt matching files. The first one that is found will be employed for the notification email.
  |
  | 1. file ``{TEMPLATE_DIR}/{PROCESS_ID}/{STATUS}.mako`` used for a specific :term:`Process` and :term:`Job` status
  | 2. file ``{TEMPLATE_DIR}/{PROCESS_ID}.mako`` used for a specific :term:`Process` but any :term:`Job` status
  | 3. file ``{TEMPLATE_DIR}/{weaver.wps_email_notify_template_default}`` used for any combination if specified
  | 4. file ``{TEMPLATE_DIR}/default.mako`` used for any combination if an alternate default name was not specified
  | 5. file |default-notify-email-template|_ as last resort
  |
  | Email notifications are sent only when corresponding :term:`Job` status milestones are reached and when
    email(s) were provided in the :ref:`Execute <proc_op_execute>` request body. Emails will not be sent if
    the request body did not include a subscription to those notifications, even if the templates were configured.

  .. seealso::
    See :ref:`Notification Subscribers <proc_op_execute_subscribers>` for more details.

  .. versionadded:: 4.15
  .. versionchanged:: 4.34

.. _weaver-execute-sync-max-wait:

- | ``weaver.execute_sync_max_wait = <int>`` [:class:`int`, seconds]
  | (default: ``20``)
  |
  | Defines the maximum duration allowed for running a :term:`Job` execution in `synchronous` mode.
  |
  | See :ref:`proc_exec_mode` for more details on the feature and how to employ it.
  | Ensure `Celery`_ worker is configured as specified in :ref:`conf_celery`.

  .. versionadded:: 4.15
  .. versionchanged:: 4.30
    Renamed from ``weaver.exec_sync_max_wait`` to ``weaver.execute_sync_max_wait``.

.. _conf_celery:

Configuration of Celery with MongoDB Backend
============================================

Since `Weaver` employs `Celery`_ as task queue manager and `MongoDB`_ as backend, relevant settings for the
|celery-config|_ and the |celery-mongo|_ should be employed. Processing of task jobs and results reporting
is accomplished according to the specific implementation of these services. Therefore, all applicable settings
and extensions should be available for custom server configuration and scaling as needed.

.. warning::
    In order to support `synchronous` execution, the ``RESULT_BACKEND`` setting **MUST** be defined.

.. |celery-config| replace:: configuration of Celery
.. _celery-config: https://docs.celeryq.dev/en/latest/userguide/configuration.html#configuration
.. |celery-mongo| replace:: configuration of MongoDB Backend
.. _celery-mongo: https://docs.celeryq.dev/en/latest/userguide/configuration.html#mongodb-backend-settings

.. _conf_s3_buckets:

Configuration of AWS S3 Buckets
=======================================

Any :term:`AWS` :term:`S3` |bucket| provided to `Weaver` needs to be accessible by the application, whether it is to
fetch input files or to store output results. This can require from the server administrator to specify credentials
by one of reference supported |aws-credentials|_ methodologies to provide necessary role and/or permissions. See also
reference |aws-config|_ which list various options that will be considered when working with :term:`S3` buckets.

Note that `Weaver` expects the |aws-config|_ to define a *default profile* from which the :term:`AWS`
client can infer which |region| it needs to connect to. The :term:`S3` bucket to store files should be
defined with ``weaver.wps_output_s3_bucket`` setting as presented in the previous section.

The :term:`S3` file and directory references for input and output in `Weaver` are expected to be formatted as one of
the methods described in |aws_s3_bucket_access|_ (more details about supported formats in :ref:`aws_s3_ref`).
The easiest and most common approach is to use a reference using the ``s3://`` scheme as follows:

.. code-block:: text

    s3://<bucket>/<file-key>

This implicitly tells `Weaver` to employ the specified :term:`S3` bucket it was configured with as well as the
automatically retrieved location (using the region from the *default profile*) in the |aws-config|_ of the application.

Alternatively, the reference can be provided as input more explicitly with any of the supported :ref:`aws_s3_ref`.
For example, the :term:`AWS` :term:`S3` link could be specified as follows.

.. code-block:: text

    https://s3.{Region}.amazonaws.com/{Bucket}/{file-key}

In this situation, `Weaver` will parse it as equivalent to the prior shorthand ``s3://`` reference format, by
substituting any appropriate details retrieved from the |aws-config|_ as needed to form the above HTTP URL variant.
For example, an alternative |region| from the default could be specified. After resolution, `Weaver`
will still attempt to fetch the file as *standard* HTTP reference by following the relevant |aws_s3_bucket_access|_.
In each case, read access should be granted accordingly to the corresponding bucket, files and/or directories such
that `Weaver` can stage them locally. For produced outputs, the write access must be granted.

In the above references, ``file-key`` is used as *anything after* the |bucket| name. In other words, this
value can contain any amount of ``/`` separators and path elements. For example, if ``weaver.wps_output_s3_bucket`` is
defined in the configuration, `Weaver` will store process output results to :term:`S3` using ``file-key`` as a
combination of ``{WPS-UUID}/{output-id.ext}``, therefore forming the full :term:`Job` result file references as:

.. code-block:: text

    https://s3.{Region}.amazonaws.com/{Bucket}/{WPS-UUID}/{output-id.ext}

    Region ::= weaver.wps_output_s3_region
    Bucket ::= weaver.wps_output_s3_bucket

.. note::
    Value of ``WPS-UUID`` can be retrieved from `Weaver` internal :term:`Job` storage
    from :meth:`weaver.datatypes.Job.wps_id`. It refers to the :ref:`Process Execution <proc_op_execute>` identifier
    that accomplished the :term:`WPS` request to run the :term:`Application Package`.

.. note::
    The value of ``file-key`` also applies for :ref:`cwl-dir` references.

.. |region| replace:: *Region*
.. |bucket| replace:: *Bucket*

.. _conf_data_sources:

Configuration of Data Sources
=======================================

A typical :term:`Data Source` file is presented below. This sample is also provided in `data_sources.yml.example`_.

.. literalinclude:: ../../config/data_sources.yml.example
    :language: yaml

Both ``JSON`` and ``YAML`` are equivalent and supported. The ``data_sources.yml`` file is generated by default in the
configuration folder based on the default example (if missing).
Custom configurations can be placed in the expected location or can also be provide with an alternative path
using the ``Weaver.data_sources`` configuration setting.

.. note::
    As presented in the above example, the :term:`Data Source` file can also refer to :ref:`opensearch_data_source`
    which imply additional pre-processing steps.

.. seealso::
    More details about the implication of :term:`Data Source` are provided in :ref:`data-source`.

.. _conf_wps_processes:

Configuration of WPS Processes
=======================================

`Weaver` allows the configuration of services or processes auto-deployment using definitions from a file formatted
as `wps_processes.yml.example`_. On application startup, provided references in ``processes`` list will be employed
to attempt deployment of corresponding processes locally. Given that the resources can be correctly resolved, they
will immediately be available from `Weaver`'s API without further request needed.

For convenience, every reference URL in the configuration file can either refer to explicit process definition
(i.e.: endpoint and query parameters that resolve to :ref:`DescribeProcess <proc_op_describe>` response), or a group
of processes under a common WPS server to iteratively register, using a :ref:`GetCapabilities <proc_op_getcap>` WPS
endpoint.
Please refer to `wps_processes.yml.example`_ for explicit format, keywords supported, and their resulting behaviour.

.. note::
    Processes defined under ``processes`` section registered into `Weaver` will correspond to a local snapshot of
    the remote resource at that point in time, and will not update if the reference changes. On the other hand, their
    listing and description offering will not require the remote service to be available at all time until execution.

.. versionadded:: 1.14
    When references are specified using ``providers`` section instead of ``processes``, the registration
    only saves the remote WPS provider endpoint to dynamically populate WPS processes on demand.

    Using this registration method, the processes will always reflect the latest modification from the
    remote WPS provider.

.. _weaver-wps-processes-file:

- | ``weaver.wps_processes_file = <file-path>``
  | (default: :py:data:`WEAVER_DEFAULT_WPS_PROCESSES_CONFIG` located in :py:data:`WEAVER_CONFIG_DIR`)
  |
  | Defines a custom :term:`YAML` file corresponding to `wps_processes.yml.example`_ schema to pre-load :term:`WPS`
    processes and/or providers for registration at application startup.
  |
  | The value defined by this setting will look for the provided path as absolute location, then will attempt to
    resolve relative path (corresponding to where the application is started from), and will also look within
    the |weaver-config|_ directory. If none of the files can be found, the operation is skipped.
  |
  | To ensure that this feature is disabled and to avoid any unexpected auto-deployment provided by this functionality,
    simply set setting ``weaver.wps_processes_file`` as *undefined* (i.e.: nothing after ``=`` in ``weaver.ini``).
    The default value is employed if the setting is not defined at all.

  .. seealso::
    - `weaver.ini.example`_
    - `wps_processes.yml.example`_

.. _conf_cwl_processes:

Configuration of CWL Processes
=======================================

.. versionadded:: 4.19

Although `Weaver` supports :ref:`Deployment <proc_op_deploy>` and dynamic management of :term:`Process` definitions
while the web application is running, it is sometime more convenient for service providers to offer a set of predefined
:ref:`application-package` definitions. In order to automatically register such definitions (or update them if changed),
without having to repeat any deployment requests after the application was started, it is possible to employ the
configuration setting ``weaver.cwl_processes_dir``. Registration of a :term:`Process` using this approach will result
in an identical definition as if it was :ref:`Deployed <proc_op_deploy>` using :term:`API` requests or using the
:ref:`cli` interfaces.

.. _weaver-cwl-processes-dir:

- | ``weaver.cwl_processes_dir = <dir-path>``
  | (default: :py:data:`WEAVER_CONFIG_DIR`)
  |
  | Defines the root directory where to *recursively* and *alphabetically* load any :term:`CWL` file
    to deploy the corresponding :term:`Process` definitions. Files at higher levels are loaded first before moving
    down into lower directories of the structure.
  |
  | Any failed deployment from a seemingly valid :term:`CWL` will be logged with the corresponding error message.
    Loading will proceed by ignoring failing cases according to ``weaver.cwl_processes_register_error`` setting.
    The number of successful :term:`Process` deployments will also be reported if any should occur.
  |
  | The value defined by this setting will look for the provided path as absolute location, then will attempt to
    resolve relative path (corresponding to where the application is started from). If no :term:`CWL` file could be
    found, the operation is skipped.
  |
  | To ensure that this feature is disabled and to avoid any unexpected auto-deployment provided by this functionality,
    simply set setting ``weaver.cwl_processes_dir`` as *undefined* (i.e.: nothing after ``=`` in ``weaver.ini``).
    The default value is employed if the setting is not defined at all.

  .. note::
    When registering processes using :term:`CWL`, it is mandatory for those definitions to provide an ``id`` within
    the file along other :term:`CWL` details to let `Weaver` know which :term:`Process` reference to use for deployment.

  .. warning::
    If a :term:`Process` depends on another definition, such as in the case of a :ref:`proc_workflow` definition, all
    dependencies must be registered prior to this :term:`Process`. Consider naming your :term:`CWL` files to take
    advantage of loading order to resolve such situations.

.. _weaver-cwl-processes-register-error:

- | ``weaver.cwl_processes_register_error = true|false`` [:class:`bool`]
  | (default: ``false``, *ignore failures*)
  |
  | Indicate if `Weaver` should ignore failing :term:`Process` deployments (when ``false``), due to unsuccessful
    registration of :term:`CWL` files found within any sub-directory of ``weaver.cwl_processes_dir`` path, or
    immediately fail (when ``true``) when an issue is raised during :term:`Process` deployment.

  .. seealso::
    - `weaver.ini.example`_

.. _conf_request_options:

Configuration of Request Options
=======================================

.. versionadded:: 1.8

It is possible to define :term:`Request Options` that consist of additional arguments that will be passed down to
:func:`weaver.utils.request_extra`, which essentially call a traditional request using :mod:`requests` module, but
with extended handling capabilities such as caching, retrying, and file reference support. The specific parameters
that are passed down for individual requests depend whether a match based on URL (optionally with regex rules) and
method definitions can be found in the :term:`Request Options` file. This file should be provided using
the ``weaver.request_options`` configuration setting. Using this definition, it is possible to provide specific
requests handling options, such as extended timeout, authentication arguments, SSL certification verification setting,
etc. on a per-request basis, leave other requests unaffected and generally more secure.

.. seealso::
    File `request_options.yml.example`_ provides more details and sample :term:`YAML` format of the expected contents
    for :term:`Request Options` feature.

.. seealso::
    Please refer to :func:`weaver.utils.request_extra` documentation directly for supported parameters and capabilities.

.. _weaver-request-options:

- | ``weaver.request_options = <file-path>``
  | (default: ``None``)
  |
  | Path of the :term:`Request Options` definitions to employ.

.. _weaver-ssl-verify:

- | ``weaver.ssl_verify = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Toggle the SSL certificate verification across all requests.

  .. warning::
    It is **NOT** recommended to disable SSL verification across all requests for security reasons
    (avoid man-in-the-middle attacks). This is crucial for requests that involve any form of authentication, secured
    access or personal user data references. This should be employed only for quickly resolving issues during
    development. Consider fixing SSL certificates on problematic servers, or disable the verification on a per-request
    basis using :term:`Request Options` for acceptable cases.

.. _conf_quotation:

Configuration of Quotation Estimation
============================================

.. versionadded:: 4.30

Following parameters are relevant when using |ogc-proc-ext-quotation|_.
If this feature is not desired, simply provide ``weaver.quotation = false`` in the ``weaver.ini`` configuration file,
and all corresponding functionalities, including `API` endpoints, will be disabled.

.. _weaver-quotation:

- | ``weaver.quotation = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enable support of |ogc-proc-ext-quotation|_.
  |
  | See :ref:`quotation` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-docker-image:

- | ``weaver.quotation_docker_image = <image-reference>`` [:class:`str`]
  |
  | Specifies the :term:`Docker` image used for :ref:`quote_estimation` to evaluate a :term:`Quote`
    for the eventual :term:`Process` execution.
  |
  | Required if ``weaver.quotation`` is enabled.
  |
  | See :ref:`quote_estimation` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-docker-username:

- | ``weaver.quotation_docker_username = <username>`` [:class:`str`]
  |
  | Username to employ for authentication when retrieving the :term:`Docker` image used as :ref:`quote_estimation`.
  |
  | Only required if the :term:`Docker` image is not accessible publicly or already
    provided through some other means when requested by the :term:`Docker` daemon.
    Should be combined with ``weaver.quotation_docker_password``.
  |
  | See :ref:`quotation_currency_conversion` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-docker-password:

- | ``weaver.quotation_docker_password = <username>`` [:class:`str`]
  |
  | Password to employ for authentication when retrieving the :term:`Docker` image used as :ref:`quote_estimation`.
  |
  | Only required if the :term:`Docker` image is not accessible publicly or already
    provided through some other means when requested by the :term:`Docker` daemon.
    Should be combined with ``weaver.quotation_docker_username``.
  |
  | See :ref:`quotation_currency_conversion` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-currency-default:

- | ``weaver.quotation_currency_default = <CURRENCY>`` [:class:`str`]
  | (default: ``USD``)
  |
  | Currency code in `ISO-4217 <https://www.iso.org/iso-4217-currency-codes.html>`_ format used by default.
  |
  | It is up to the specified :ref:`quote_estimation` algorithm defined by ``weaver.quotation_docker_image`` and
    employed by the various :term:`Process` to ensure that the returned :ref:`quote_estimation` cost makes
    sense according to the specified default currency.
  |
  | See :ref:`quotation_currency_conversion` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-currency-converter:

- | ``weaver.quotation_currency_converter = <converter>`` [:class:`str`]
  |
  | Reference currency converter to employ for retrieving conversion rates.
  |
  | Valid values are:
  | - `openexchangerates <https://docs.openexchangerates.org/reference/convert>`_
  | - `currencylayer <https://currencylayer.com/documentation>`_
  | - `exchangeratesapi <https://exchangeratesapi.io/documentation/>`_
  | - `fixer <https://fixer.io/documentation>`_
  | - `scrapper <https://www.x-rates.com/table/?from=USD&amount=1>`_
  | - ``custom``
  |
  | In each case, requests will be attempted using ``weaver.quotation_currency_token`` to authenticate with the API.
    Request caching of 1 hour will be used by default to limit chances of rate-limiting, but converter-specific plans
    could block request at any moment depending on the amount of :ref:`quotation` requests accomplished.
    In such case, the conversion will not be performed and will remain in the default currency.
  |
  | If a ``custom`` URL is desired, the ``weaver.quotation_currency_custom_url`` parameter should also be provided.
  |
  | If none is provided, conversion rates will not be applied and currencies
    will always use ``weaver.quotation_currency_default``.
  |
  | See :ref:`quotation` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-currency-custom-url:

- | ``weaver.quotation_currency_custom_url = <URL>`` [:class:`str`]
  |
  | Reference ``custom`` currency converter URL pattern to employ for retrieving conversion rates.
  |
  | This applies only when using ``weaver.quotation_currency_converter = custom``
  |
  | The specified URL will be used to perform a ``GET`` request.
    This URL should contain the relevant query or path parameters to perform the request.
    Parameters can be specified using templating (``{<param>}``), with parameters
    names ``token``, ``from``, ``to`` and ``amount`` to perform the conversion.
    The query parameter ``token`` will be filled by ``weaver.quotation_currency_token``, while remaining values will
    be provided based on the source and target currency conversion requirements.
    The response body should be in :term:`JSON` with minimally the conversion ``result`` field located at the root.
    The same caching policy will be applied as for the other API references.
  |
  | If none is provided, conversion rates will not be applied and currencies
    will always use ``weaver.quotation_currency_default``.
  |
  | See :ref:`quotation` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-currency-token:

- | ``weaver.quotation_currency_token = <API access token>`` [:class:`str`]
  |
  | Password to employ for authentication when retrieving the :term:`Docker` image used as :ref:`quote_estimation`.
  |
  | Only required if the :term:`Docker` image is not accessible publicly or already
    provided through some other means when requested by the :term:`Docker` daemon.
    Should be combined with ``weaver.quotation_docker_username``.
  | See :ref:`quotation` for more details on the feature.

  .. versionadded:: 4.30

.. _weaver-quotation-sync-max-wait:

- | ``weaver.quotation_sync_max_wait = <int>`` [:class:`int`, seconds]
  | (default: ``20``)
  |
  | Defines the maximum duration allowed for running a :ref:`quote_estimation` in `synchronous` mode.
  |
  | See :ref:`proc_exec_mode` for more details on the feature and how to employ it.
  | Ensure `Celery`_ worker is configured as specified in :ref:`conf_celery`.

  .. versionchanged:: 4.30
    Renamed from ``weaver.quote_sync_max_wait`` to ``weaver.quotation_sync_max_wait``.

.. _conf_vault:

Configuration of File Vault
=======================================

.. versionadded:: 4.9

Configuration of the :term:`Vault` is required in order to obtain access to its functionalities
and to enable its :term:`API` endpoints. This feature is notably employed to push local files to a remote `Weaver`
instance when using the :ref:`cli` utilities, in order to use them for the :term:`Job` execution. Please refer to
below references for more details.

.. seealso::
    - :ref:`vault_upload`
    - :ref:`file_vault_inputs`

.. _weaver-vault:

- | ``weaver.vault = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Toggles the :term:`Vault` feature.

.. _weaver-vault-dir:

- | ``weaver.vault_dir = <dir-path>``
  | (default: ``/tmp/vault``)
  |
  | Defines the default location where to write :ref:`files uploaded to the Vault <vault_upload>`.
  |
  | If the directory does not exist, it is created on demand by the feature making use of it.


Starting the Application
=======================================

``make start`` (or similar command) to start locally

The following examples provided more details:

- use ``gunicorn/pserve`` to start the Web :term:`API` (example `Dockerfile-manager`_)
- use ``celery`` to start :term:`Job` Workers (example `Dockerfile-worker`_)
- see `docker-compose.yml.example`_ for a complete stack including database dependencies
