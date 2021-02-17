:mod:`weaver.wps_restapi.jobs.jobs`
===================================

.. py:module:: weaver.wps_restapi.jobs.jobs


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: get_job(request: Request) -> Job

   Obtain a job from request parameters.

   :returns: Job information if found.
   :raise HTTPNotFound: with JSON body details on missing/non-matching job, process, provider IDs.


.. function:: validate_service_process(request: Request) -> Tuple[Optional[str], Optional[str]]

   Verifies that service or process specified by path or query will raise the appropriate error if applicable.


.. function:: get_queried_jobs(request)

   Retrieve the list of jobs which can be filtered, sorted, paged and categorized using query parameters.


.. function:: get_job_status(request)

   Retrieve the status of a job.


.. function:: cancel_job(request)

   Dismiss a job.

   Note: Will only stop tracking this particular process (WPS 1.0 doesn't allow to stop a process)


.. function:: get_results(job: Job, container: AnySettingsContainer) -> JSON

   Obtains the results with extended full WPS output URL as applicable and according to configuration settings.


.. function:: get_job_results(request)

   Retrieve the results of a job.


.. function:: get_job_exceptions(request)

   Retrieve the exceptions of a job.


.. function:: get_job_logs(request)

   Retrieve the logs of a job.


.. function:: get_job_output(request)


