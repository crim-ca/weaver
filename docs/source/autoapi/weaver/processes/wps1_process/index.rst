:mod:`weaver.processes.wps1_process`
====================================

.. py:module:: weaver.processes.wps1_process


Module Contents
---------------

.. data:: LOGGER
   

   

.. data:: REMOTE_JOB_PROGRESS_REQ_PREP
   :annotation: = 2

   

.. data:: REMOTE_JOB_PROGRESS_EXECUTION
   :annotation: = 5

   

.. data:: REMOTE_JOB_PROGRESS_MONITORING
   :annotation: = 10

   

.. data:: REMOTE_JOB_PROGRESS_FETCH_OUT
   :annotation: = 90

   

.. data:: REMOTE_JOB_PROGRESS_COMPLETED
   :annotation: = 100

   

.. py:class:: Wps1Process(provider: str, process: str, request: WPSRequest, update_status: UpdateStatusPartialFunction)



   Common interface for WpsProcess to be used is cwl jobs

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: execute(self, workflow_inputs, out_dir, expected_outputs)

      Execute a remote process using the given inputs.
      The function is expected to monitor the process and update the status.
      Retrieve the expected outputs and store them in the ``out_dir``.

      :param workflow_inputs: `CWL` job dict
      :param out_dir: directory where the outputs must be written
      :param expected_outputs: expected value outputs as `{'id': 'value'}`



