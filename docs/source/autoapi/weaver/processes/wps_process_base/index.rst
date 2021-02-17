:mod:`weaver.processes.wps_process_base`
========================================

.. py:module:: weaver.processes.wps_process_base


Module Contents
---------------

.. py:class:: WpsProcessInterface(: WPSRequest, request)



   Common interface for WpsProcess to be used is cwl jobs

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: execute(self, workflow_inputs: CWL, out_dir: str, expected_outputs: Dict[str, str])
      :abstractmethod:

      Execute a remote process using the given inputs.
      The function is expected to monitor the process and update the status.
      Retrieve the expected outputs and store them in the ``out_dir``.

      :param workflow_inputs: `CWL` job dict
      :param out_dir: directory where the outputs must be written
      :param expected_outputs: expected value outputs as `{'id': 'value'}`


   .. method:: make_request(self, method, url, retry, status_code_mock=None, **kwargs)


   .. method:: host_file(file_name)
      :staticmethod:



