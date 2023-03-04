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


- | ``weaver.configuration = ADES|EMS|HYBRID|DEFAULT``
  | (default: ``DEFAULT``)
  |
  | Tells the application in which mode to run.
  |
  | Enabling ``ADES`` for instance will disable some ``EMS``-specific operations such as dispatching :ref:`Workflow`
    process steps to known remote ``ADES`` servers. ``ADES`` should be used to *only* run processes locally
    (as the working unit). ``EMS`` will *always* dispatch execution of jobs to other ``ADES`` except for :ref:`Workflow`
    processes that chains them.
  | When ``HYBRID`` is specified, `Weaver` will assume both ``ADES`` and ``EMS`` roles simultaneously, meaning it will
    be able to execute local processes by itself and monitor dispatched execution of registered remote providers.
  | Finally, ``DEFAULT`` configuration will provide very minimalistic operations as all other modes will be unavailable.

- | ``weaver.url = <url>``
  | (default: ``http://localhost:4001``)
  |
  | Defines the full URL (including HTTP protocol/scheme, hostname and optionally additional path suffix) that will
    be used as base URL for all other URL settings of `Weaver`.

.. note::

    This is the URL that you want displayed in responses (e.g.: ``processDescriptionURL`` or job ``location``).
    For the effective URL employed by the WSGI HTTP server, refer to ``[server:main]`` section of `weaver.ini.example`_.

- | ``weaver.schema_url = <url>``
  | (default: ``${weaver.url}/json#/definitions``)
  |
  | Defines the base URL of schemas to be reported in responses.
  |
  | When not provided, the running Web Application instance OpenAPI JSON path will be employed to refer to the
    schema ``definitions`` section. The configuration setting is available to override this endpoint by another
    static URL location where the corresponding schemas can be found if desired.

.. versionadded:: 4.0

- | ``weaver.cwl_euid = <int>`` [:class:`int`, *experimental*]
  | (default: ``None``, auto-resolved by :term:`CWL` with effective machine user)
  |
  | Define the effective machine user ID to be used for running the :term:`Application Package`.

.. versionadded:: 1.9

- | ``weaver.cwl_egid = <int>`` [:class:`int`, *experimental*]
  | (default: ``None``, auto-resolved by :term:`CWL` with the group of the effective user)
  |
  | Define the effective machine group ID to be used for running the :term:`Application Package`.

.. versionadded:: 1.9

- | ``weaver.wps = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enables the WPS-1/2 endpoint.

.. seealso::
    :ref:`wps_endpoint`

.. warning::

     At the moment, this setting must be ``true`` to allow :term:`Job` execution as the worker monitors this endpoint.
     This could change with future developments (see issue `#21 <https://github.com/crim-ca/weaver/issues/21>`_).

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

- | ``weaver.wps_workdir = <directory-path>``
  | (default: uses automatically generated temporary directory if none specified)
  |
  | Prefix where process :term:`Job` worker should execute the :term:`Process` from.

- | ``weaver.wps_restapi = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enable the WPS-REST endpoint.

.. warning::

    `Weaver` looses most, if not all, of its useful features without this, and there won't be much point in using
    it without REST endpoint, but it should technically be possible to run it as WPS-1/2 only if desired.

- | ``weaver.wps_restapi_path = <url-path>``
  | ``weaver.wps_restapi_url = <full-url>``
  | (default: *path* ``/``)
  |
  | Endpoint that will be employed as prefix to refer to WPS-REST requests
  | (including but not limited to |ogc-api-proc|_ schemas).
  |
  | It can either be the explicit *full URL* to use or the *path* relative to ``weaver.url``.
  | Setting ``weaver.wps_restapi_path`` is ignored if its URL equivalent is defined.
  | The *path* variant **SHOULD** start with ``/`` for appropriate concatenation with ``weaver.url``, although this is
    not strictly enforced.

- | ``weaver.wps_metadata_[...]`` (multiple settings)
  |
  | Metadata fields that will be rendered by either or both the WPS-1/2 and WPS-REST endpoints
    (:ref:`GetCapabilities <proc_op_getcap>`).

- | ``weaver.wps_email_[...]`` (multiple settings)
  |
  | Defines configuration of email notification functionality on job completion.
  |
  | Encryption settings as well as custom email templates are available. Default email template defined in
    `email-template`_ is employed if none is provided. Email notifications are sent only on job
    completion if an email was provided in the :ref:`Execute <proc_op_execute>` request body
    (see also: :ref:`Email Notification`).

.. versionadded:: 4.15

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


- | ``weaver.request_options = <file-path>``
  | (default: ``None``)
  |
  | Path of the :term:`Request Options` definitions to employ.


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

- | ``weaver.quotation = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Enable support of |ogc-proc-ext-quotation|_.
  |
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_docker_image = <image-reference>`` [:class:`str`]
  |
  | Specifies the :term:`Docker` image used as |quote-estimator|_ to evaluate a :term:`Quote`
    for the eventual :term:`Process` execution.
  |
  | Required if ``weaver.quotation`` is enabled.
  |
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_docker_username = <username>`` [:class:`str`]
  |
  | Username to employ for authentication when retrieving the :term:`Docker` image used as |quote-estimator|_.
  |
  | Only required if the :term:`Docker` image is not accessible publicly or already
    provided through some other means when requested by the :term:`Docker` daemon.
    Should be combined with ``weaver.quotation_docker_password``.
  |
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_docker_password = <username>`` [:class:`str`]
  |
  | Password to employ for authentication when retrieving the :term:`Docker` image used as |quote-estimator|_.
  |
  | Only required if the :term:`Docker` image is not accessible publicly or already
    provided through some other means when requested by the :term:`Docker` daemon.
    Should be combined with ``weaver.quotation_docker_username``.
  |
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_currency_default = <CURRENCY>`` [:class:`str`]
  | (default: ``USD``)
  |
  | Currency code in `ISO-4217 <https://www.iso.org/iso-4217-currency-codes.html>`_ format used by default.
  |
  | It is up to the specified |quote-estimator|_ algorithm defined by ``weaver.quotation_docker_image`` to ensure
    that the returned :term:`Quote` estimation cost makes sense according to the specified default currency.
  |
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_currency_converter = <converter>`` [:class:`str`]
  |
  | Reference currency converter to employ to retrieve conversion rates.
  |
  | Valid values are:
  | - `openexchangerates <https://docs.openexchangerates.org/reference/convert>`_
  | - `currencylayer <https://currencylayer.com/documentation>`_
  | - `exchangeratesapi <https://exchangeratesapi.io/documentation/>`_
  | - `fixer <https://fixer.io/documentation>`_
  | - ``<custom URL>``
  |
  | In each case, requests will be attempted using ``weaver.quotation_currency_token`` to authenticate with the API.
    Request caching of 1 hour will be used by default to limit chances of rate-limiting, but converter-specific plans
    could block request at any moment depending on the amount of :ref:`quotation` requests accomplished.
    In such case, the conversion will not be performed and will remain in the default currency.
  |
  | If a ``<custom URL>`` is provided, it will be used instead to perform a ``GET`` request.
    The query parameter ``access_key`` with ``weaver.quotation_currency_token`` will be used for this request.
    The specified API should also expect the query parameters ``from``, ``to`` and ``amount`` to perform conversion.
    The response body should be in :term:`JSON` with minimally the conversion ``result`` field located at the root.
    The same caching policy will be applied as for the other API references.
  |
  | If none is provided, conversion rates will not be applied and currencies
    will always use ``weaver.quotation_currency_default``.
  |
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_currency_token = <API access token>`` [:class:`str`]
  |
  | Password to employ for authentication when retrieving the :term:`Docker` image used as |quote-estimator|_.
  |
  | Only required if the :term:`Docker` image is not accessible publicly or already
    provided through some other means when requested by the :term:`Docker` daemon.
    Should be combined with ``weaver.quotation_docker_username``.
  | See :ref:`quotation` for more details on the feature.

.. versionadded:: 4.30

- | ``weaver.quotation_sync_max_wait = <int>`` [:class:`int`, seconds]
  | (default: ``20``)
  |
  | Defines the maximum duration allowed for running a :term:`Quote` estimation in `synchronous` mode.
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

- | ``weaver.vault = true|false`` [:class:`bool`-like]
  | (default: ``true``)
  |
  | Toggles the :term:`Vault` feature.

- | ``weaver.vault_dir = <dir-path>``
  | (default: ``/tmp/vault``)
  |
  | Defines the default location where to write :ref:`files uploaded to the Vault <vault_upload>`.
  |
  | If the directory does not exist, it is created on demand by the feature making use of it.


Starting the Application
=======================================

.. todo:: complete docs

``make start`` (or similar command)

- need to start ``gunicorn/pserve`` (example `Dockerfile-manager`_)
- need to start ``celery`` worker (example `Dockerfile-worker`_)
