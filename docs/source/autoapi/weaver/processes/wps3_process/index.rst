:mod:`weaver.processes.wps3_process`
====================================

.. py:module:: weaver.processes.wps3_process


Module Contents
---------------

.. data:: LOGGER
   

   

.. data:: REMOTE_JOB_PROGRESS_PROVIDER
   :annotation: = 1

   

.. data:: REMOTE_JOB_PROGRESS_DEPLOY
   :annotation: = 2

   

.. data:: REMOTE_JOB_PROGRESS_VISIBLE
   :annotation: = 3

   

.. data:: REMOTE_JOB_PROGRESS_REQ_PREP
   :annotation: = 5

   

.. data:: REMOTE_JOB_PROGRESS_EXECUTION
   :annotation: = 9

   

.. data:: REMOTE_JOB_PROGRESS_MONITORING
   :annotation: = 10

   

.. data:: REMOTE_JOB_PROGRESS_FETCH_OUT
   :annotation: = 90

   

.. data:: REMOTE_JOB_PROGRESS_COMPLETED
   :annotation: = 100

   

.. py:class:: Wps3Process(step_payload: JSON, joborder: JSON, process: str, request: WPSRequest, update_status: UpdateStatusPartialFunction)



   Common interface for WpsProcess to be used is cwl jobs

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: resolve_data_source(self, step_payload, joborder)


   .. method:: get_user_auth_header(self)


   .. method:: is_deployed(self)


   .. method:: is_visible(self) -> Union[bool, None]

      Gets the process visibility.

      :returns:
          True/False correspondingly for public/private if visibility is retrievable,
          False if authorized access but process cannot be found,
          None if forbidden access.


   .. method:: set_visibility(self, visibility)


   .. method:: describe_process(self)


   .. method:: deploy(self)


   .. method:: execute(self, workflow_inputs, out_dir, expected_outputs)

      Execute a remote process using the given inputs.
      The function is expected to monitor the process and update the status.
      Retrieve the expected outputs and store them in the ``out_dir``.

      :param workflow_inputs: `CWL` job dict
      :param out_dir: directory where the outputs must be written
      :param expected_outputs: expected value outputs as `{'id': 'value'}`


   .. method:: get_job_status(self, job_status_uri, retry=True)


   .. method:: get_job_results(self, job_id)



