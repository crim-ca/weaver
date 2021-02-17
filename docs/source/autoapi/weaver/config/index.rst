:mod:`weaver.config`
====================

.. py:module:: weaver.config


Module Contents
---------------

.. data:: LOGGER
   

   

.. data:: WEAVER_CONFIGURATION_DEFAULT
   :annotation: = DEFAULT

   

.. data:: WEAVER_CONFIGURATION_ADES
   :annotation: = ADES

   

.. data:: WEAVER_CONFIGURATION_EMS
   :annotation: = EMS

   

.. data:: WEAVER_CONFIGURATIONS
   

   

.. data:: WEAVER_DEFAULT_INI_CONFIG
   :annotation: = weaver.ini

   

.. data:: WEAVER_DEFAULT_DATA_SOURCES_CONFIG
   :annotation: = data_sources.yml

   

.. data:: WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG
   :annotation: = request_options.yml

   

.. data:: WEAVER_DEFAULT_WPS_PROCESSES_CONFIG
   :annotation: = wps_processes.yml

   

.. data:: WEAVER_DEFAULT_CONFIGS
   

   

.. function:: get_weaver_configuration(container: AnySettingsContainer) -> str

   Obtains the defined operation configuration mode.

   :returns: one value amongst :py:data:`weaver.config.WEAVER_CONFIGURATIONS`.


.. function:: get_weaver_config_file(file_path: str, default_config_file: str, generate_default_from_example: bool = True) -> str

   Validates that the specified configuration file can be found, or falls back to the default one.

   Handles 'relative' paths for settings in ``WEAVER_DEFAULT_INI_CONFIG`` referring to other configuration files.
   Default file must be one of ``WEAVER_DEFAULT_CONFIGS``.

   If both the specified file and the default file cannot be found, default file under ``WEAVER_DEFAULT_INI_CONFIG`` is
   auto-generated from the corresponding ``.example`` file if :paramref:`generate_default_from_example` is ``True``.
   If it is ``False``, an empty string is returned instead without generation since no existing file can be guaranteed,
   and it is up to the caller to handle this situation as it explicitly disabled generation.

   :param file_path: path to a configuration file (can be relative if resolvable or matching a default file name)
   :param default_config_file: one of :py:data:`WEAVER_DEFAULT_CONFIGS`.
   :param generate_default_from_example: enable fallback copy of default configuration file from corresponding example.
   :returns: absolue path of the resolved file.


.. function:: includeme(config)


