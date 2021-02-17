:mod:`weaver.wps.utils`
=======================

.. py:module:: weaver.wps.utils


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: _get_settings_or_wps_config(container: AnySettingsContainer, weaver_setting_name: str, config_setting_section: str, config_setting_name: str, default_not_found: str, message_not_found: str) -> str


.. function:: get_wps_path(container: AnySettingsContainer) -> str

   Retrieves the WPS path (without hostname).

   Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.


.. function:: get_wps_url(container: AnySettingsContainer) -> str

   Retrieves the full WPS URL (hostname + WPS path)

   Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.


.. function:: get_wps_output_dir(container: AnySettingsContainer) -> str

   Retrieves the WPS output directory path where to write XML and result files.
   Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.


.. function:: get_wps_output_path(container: AnySettingsContainer) -> str

   Retrieves the WPS output path (without hostname) for staging XML status, logs and process outputs.
   Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.


.. function:: get_wps_output_url(container: AnySettingsContainer) -> str

   Retrieves the WPS output URL that maps to WPS output directory path.
   Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.


.. function:: get_wps_local_status_location(url_status_location: str, container: AnySettingsContainer, must_exist: bool = True) -> Optional[str]

   Attempts to retrieve the local XML file path corresponding to the WPS status location as URL.

   :param url_status_location: URL reference pointing to some WPS status location XML.
   :param container: any settings container to map configured local paths.
   :param must_exist: return only existing path if enabled, otherwise return the parsed value without validation.
   :returns: found local file path if it exists, ``None`` otherwise.


.. function:: check_wps_status(location: Optional[str] = None, response: Optional[XML] = None, sleep_secs: int = 2, verify: bool = True, settings: Optional[AnySettingsContainer] = None) -> WPSExecution

   Run :func:`owslib.wps.WPSExecution.checkStatus` with additional exception handling.

   :param location: job URL or file path where to look for job status.
   :param response: WPS response document of job status.
   :param sleep_secs: number of seconds to sleep before returning control to the caller.
   :param verify: Flag to enable SSL verification.
   :param settings: Application settings to retrieve any additional request parameters as applicable.
   :return: OWSLib.wps.WPSExecution object.


.. function:: load_pywps_config(container: AnySettingsContainer, config: Optional[Union[str, Dict[str, str]]] = None) -> ConfigParser

   Loads and updates the PyWPS configuration using Weaver settings.


.. function:: set_wps_language(wps: WebProcessingService, accept_language: Optional[str] = None, request: Optional[Request] = None) -> None

   Set the :attr:`language` property on the :class:`WebProcessingService` object.

   Given the `Accept-Language` header value, match the best language
   to the supported languages.

   By default, and if no match is found, the :attr:`WebProcessingService.language`
   property is set to None.

   https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
   (q-factor weighting is ignored, only order is considered)

   :param wps: process for which to set the language header if it is accepted
   :param str accept_language: the value of the Accept-Language header
   :param request: request from which to extract Accept-Language header if not provided directly


