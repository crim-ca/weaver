:mod:`weaver.processes.execution`
=================================

.. py:module:: weaver.processes.execution


Module Contents
---------------

.. data:: LOGGER
   

   

.. data:: JOB_PROGRESS_SETUP
   :annotation: = 1

   

.. data:: JOB_PROGRESS_DESCRIBE
   :annotation: = 2

   

.. data:: JOB_PROGRESS_GET_INPUTS
   :annotation: = 4

   

.. data:: JOB_PROGRESS_GET_OUTPUTS
   :annotation: = 6

   

.. data:: JOB_PROGRESS_EXECUTE_REQUEST
   :annotation: = 8

   

.. data:: JOB_PROGRESS_EXECUTE_STATUS_LOCATION
   :annotation: = 10

   

.. data:: JOB_PROGRESS_EXECUTE_MONITOR_START
   :annotation: = 15

   

.. data:: JOB_PROGRESS_EXECUTE_MONITOR_LOOP
   :annotation: = 20

   

.. data:: JOB_PROGRESS_EXECUTE_MONITOR_ERROR
   :annotation: = 85

   

.. data:: JOB_PROGRESS_EXECUTE_MONITOR_END
   :annotation: = 90

   

.. data:: JOB_PROGRESS_NOTIFY
   :annotation: = 95

   

.. data:: JOB_PROGRESS_DONE
   :annotation: = 100

   

.. function:: execute_process(self, job_id, url, headers=None)


.. function:: make_results_relative(results: List[JSON], settings: SettingsType) -> List[JSON]

   Redefines job results to be saved in database as relative paths to output directory configured in PyWPS
   (i.e.: relative to ``weaver.wps_output_dir``).

   This allows us to easily adjust the exposed result HTTP path according to server configuration
   (i.e.: relative to ``weaver.wps_output_path`` and/or ``weaver.wps_output_url``) and it also avoid rewriting
   the whole database job results if the setting is changed later on.


.. function:: map_locations(job: Job, settings: SettingsType) -> None

   Generates symlink references from the Job UUID to PyWPS UUID results (outputs directory, status and log locations).
   Update the Job's WPS ID if applicable (job executed locally).
   Assumes that all results are located under the same reference UUID.


.. function:: submit_job(request: Request, reference: Union[Service, Process], tags: Optional[List[str]] = None) -> JSON

   Generates the job submission from details retrieved in the request.

   .. seealso::
       :func:`submit_job_handler` to provide elements pre-extracted from requests or from other parsing.


.. function:: _validate_job_parameters(json_body)

   Tests supported parameters not automatically validated by colander deserialize.


.. function:: submit_job_handler(payload: JSON, settings: SettingsType, service_url: str, provider_id: Optional[str] = None, process_id: str = None, is_workflow: bool = False, is_local: bool = True, visibility: Optional[str] = None, language: Optional[str] = None, auth: Optional[HeaderCookiesType] = None, tags: Optional[List[str]] = None, user: Optional[int] = None) -> JSON

   Submits the job to the Celery worker with provided parameters.

   Assumes that parameters have been pre-fetched and validated, except for the input payload.


