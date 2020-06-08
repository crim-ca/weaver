.. _configuration:
.. include:: references.rst

******************
Configuration
******************

.. contents::
    :local:
    :depth: 2

After you have installed `Weaver`, you can customize its behaviour using multiple configuration settings.


Configuration Settings
=======================================

All settings are configured using a ``weaver.ini`` configuration file. A `weaver.ini.example`_ file is provided
with default values to help in the configuration process. Explanations of respective settings are also available in
this example file.

The configuration file tell the application runner (e.g. `Gunicorn`_, ``pserve`` or similar WSGI HTTP Server), how to
execute `Weaver` as well as all settings to provide in order to personalize the application. All settings specific to
`Weaver` employ the format ``weaver.<setting>``.

Following is a partial list of most predominant settings. Note that all following settings should be applied under
section ``[app:main]`` of `weaver.ini.example`_ for the application to resolve them.

- | ``weaver.configuration = ADES|EMS``
  |
  | Tells the application in which mode to run. Enabling `ADES` for instance will disable some `EMS`-specific
  | operations such as dispatching `Workflow`_ process steps to known remote `ADES` servers.

- | ``weaver.url = <url>``
  |
  | Defines the full URL (including HTTP protocol/scheme, hostname and optionally additional path suffix) that will
  | be used as base URL for all other URL settings of `Weaver`.

.. note::

    This is the URL that you want displayed in responses (e.g.: ``processDescriptionURL`` or job ``location``).
    For the effective URL employed by the WSGI HTTP server, refer to ``[server:main]`` section of `weaver.ini.example`_.

- | ``weaver.wps = true|false``
  |
  | Enables the WPS-1/2 endpoint.

 .. warning::

     At the moment, this setting must be ``true`` to allow job execution as the worker monitors this endpoint.
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
  | not strictly enforced.

- | ``weaver.wps_output_dir = <directory-path>``
  | (default: ``/tmp``)
  |
  | Location where WPS outputs (results from jobs) will be stored for stage-out. This directory should be mapped to
  | `Weaver`'s WPS output URL to serve them externally as needed.

- | ``weaver.wps_output_path = <url-path>``
  | ``weaver.wps_output_url = <full-url>``
  | (default: *path* ``/wpsoutputs``)
  |
  | Endpoint that will be employed as prefix to refer to WPS outputs (job results).
  |
  | It can either be the explicit *full URL* to use or the *path* relative to ``weaver.url``.
  | Setting ``weaver.wps_output_path`` is ignored if its URL equivalent is defined.
  | The *path* variant **SHOULD** start with ``/`` for appropriate concatenation with ``weaver.url``, although this is
  | not strictly enforced.

- | ``weaver.wps_workdir = <directory-path>``
  | (default: uses automatically generated temporary directory if none specified)
  |
  | Prefix where process job worker should execute the process from.

- | ``weaver.wps_restapi = true|false``
  | (default: ``true``)
  |
  | Enable the WPS-REST endpoint.

.. note::

    `Weaver` looses most, if not all, of its useful features without this, and there won't be much point in using
    it without REST endpoint, but it should technically be possible to run it as WPS-1/2 only if desired.

- | ``weaver.wps_restapi_path = <url-path>``
  | ``weaver.wps_restapi_url = <full-url>``
  | (default: *path* ``/``)
  |
  | Endpoint that will be employed as prefix to refer to WPS-REST requests
  | (including but not limited to |ogc-proc-api|_ schemas).
  |
  | It can either be the explicit *full URL* to use or the *path* relative to ``weaver.url``.
  | Setting ``weaver.wps_restapi_path`` is ignored if its URL equivalent is defined.
  | The *path* variant **SHOULD** start with ``/`` for appropriate concatenation with ``weaver.url``, although this is
  | not strictly enforced.

- | ``weaver.wps_metadata_[...]`` settings group
  |
  | Metadata fields that will be rendered by either or both the WPS-1/2 and WPS-REST endpoints (`GetCapabilities`_).

- | ``weaver.wps_email_[...]`` settings group
  |
  | Defines configuration email notification functionality on job completion.
  |
  | Encryption settings as well as custom email templates are available. Email notifications are sent only on job
  | completion if an email was provided in the `Execute`_ request body.

.. seealso::
    - `Execute`_ request details.


.. note::

    Refer to `weaver.ini.example`_ for the extended list of applicable settings.
    Some advanced configuration settings are also described in the below sections.


Configuration of Data Sources
=======================================

.. todo:: complete docs

`data_sources.json.example`_


Configuration of WPS Processes
=======================================

`Weaver` allows the configuration of services or processes auto-deployment using definitions from a file formatted
as `wps_processes.yml.example`_. On application startup, provided references will be employed to attempt deployment
of corresponding processes locally. Given that the resources can be correctly resolved, they will immediately be
available from `Weaver`'s API without further request needed.

For convenience, every reference URL in the configuration file can either refer to explicit process definition
(i.e.: endpoint and query parameters that resolve to `DescribeProcess`_ response), or a group of processes under a
common WPS server to iteratively deploy, using a `GetCapabilities`_ WPS endpoint. Please refer to
`wps_processes.yml.example`_ for explicit format, keywords supported, and their resulting behaviour.

To specify a custom YAML file, you can define the setting named ``weaver.wps_processes_file`` with the appropriate path
within the employed ``weaver.ini`` file that starts your application. By default, this setting will look for the
provided path as absolute location, then will attempt to resolve relative path (corresponding to where the application
is started from), and will also look within the `weaver.config`_ directory. If none of the files can be found, it will
try to use a copy of `wps_processes.yml.example`_.

To disable this feature and avoid any auto-deployment provided by this functionality, simply set setting
``weaver.wps_processes_file`` as *undefined* (i.e.: nothing after ``=`` in ``weaver.ini``).

.. seealso::
    - `weaver.ini.example`_
    - `wps_processes.yml.example`_


Configuration of Request Options
=======================================

.. todo:: complete docs

``weaver.ssl_verify``


.. versionadded:: 1.8.0

`request_options.yml.example`_


Starting the Application
=======================================

.. todo:: complete docs

``make start`` (or similar command)

- need to start ``gunicorn/pserve`` (example `Dockerfile-manager`_)
- need to start ``celery`` worker (example `Dockerfile-worker`_)

