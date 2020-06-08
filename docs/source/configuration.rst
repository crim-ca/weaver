.. _configuration:

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
with default values to help in the configuration process.

.. todo:: complete docs



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

.. versionadded:: 1.8.0

.. todo:: complete docs


`request_options.yml.example`_

Starting the Application
=======================================

.. todo:: complete docs

``make start`` (or similar command)

- need to start ``gunicorn/pserve`` (example `Dockerfile-manager`_)
- need to start ``celery`` worker (example `Dockerfile-worker`_)


.. _weaver.config: ../../../config
.. _weaver.ini.example: ../../../config/weaver.ini.example
.. _data_sources.json.example: ../../../config/data_sources.json.example
.. _wps_processes.yml.example: ../../../config/wps_processes.yml.example
.. _request_options.yml.example: ../../../config/request_options.yml.example
.. _Dockerfile-manager: ../../../docker/Dockerfile-manager
.. _Dockerfile-worker: ../../../docker/Dockerfile-worker

