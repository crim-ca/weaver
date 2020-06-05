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

All settings are configured using a ``weaver.ini`` configuration file. An `weaver.ini.example`_ file is provided
with default values to help in the configuration process.

.. todo:: complete docs



Configuration of Data Sources
=======================================

.. todo:: complete docs

`data_sources.json.example`_


Configuration of WPS Processes
=======================================

.. todo:: complete docs


`wps_processes.yml.example`_

Configuration of Request Options
=======================================

.. todo:: complete docs


`request_options.yml.example`_

Starting the Application
=======================================

.. todo:: complete docs

``make start`` (or similar command)

- need to start ``gunicorn/pserve`` (example `Dockerfile-manager`_)
- need to start ``celery`` worker (example `Dockerfile-worker`_)



.. _weaver.ini.example: ../../../config/weaver.ini.example
.. _data_sources.json.example: ../../../config/data_sources.json.example
.. _wps_processes.yml.example: ../../../config/wps_processes.yml.example
.. _request_options.yml.example: ../../../config/request_options.yml.example
.. _Dockerfile-manager: ../../../docker/Dockerfile-manager
.. _Dockerfile-worker: ../../../docker/Dockerfile-worker
