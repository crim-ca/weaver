:mod:`weaver.processes.esgf_process`
====================================

.. py:module:: weaver.processes.esgf_process


Module Contents
---------------

.. data:: LAST_PERCENT_REGEX
   

   

.. py:class:: Percent



   .. attribute:: PREPARING
      :annotation: = 2

      

   .. attribute:: SENDING
      :annotation: = 3

      

   .. attribute:: COMPUTE_DONE
      :annotation: = 98

      

   .. attribute:: FINISHED
      :annotation: = 100

      


.. py:class:: InputNames



   .. attribute:: FILES
      :annotation: = files

      

   .. attribute:: VARIABLE
      :annotation: = variable

      

   .. attribute:: API_KEY
      :annotation: = api_key

      

   .. attribute:: TIME
      :annotation: = time

      

   .. attribute:: LAT
      :annotation: = lat

      

   .. attribute:: LON
      :annotation: = lon

      


.. py:class:: InputArguments



   .. attribute:: START
      :annotation: = start

      

   .. attribute:: END
      :annotation: = end

      

   .. attribute:: CRS
      :annotation: = crs

      


.. py:class:: ESGFProcess(provider: str, process: str, request: WPSRequest, update_status: UpdateStatusPartialFunction)



   Common interface for WpsProcess to be used is cwl jobs

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: required_inputs
      

      

   .. method:: execute(self: JSON, workflow_inputs: str, out_dir: Dict[str, str], expected_outputs) -> None

      Execute an ESGF process from cwl inputs


   .. method:: _prepare_inputs(self: JSON, workflow_inputs) -> List[cwt.Variable]

      Convert inputs from cwl inputs to ESGF format


   .. method:: _get_domain(workflow_inputs: JSON) -> Optional[cwt.Domain]
      :staticmethod:


   .. method:: _check_required_inputs(self, workflow_inputs)


   .. method:: _get_files_urls(workflow_inputs: JSON) -> List[Tuple[str, str]]
      :staticmethod:

      Get all netcdf files from the cwl inputs


   .. method:: _get_variable(workflow_inputs: JSON) -> str
      :staticmethod:

      Get all netcdf files from the cwl inputs


   .. method:: _run_process(self: str, api_key: List[cwt.Variable], inputs: Optional[cwt.Domain], domain=None) -> cwt.Process

      Run an ESGF process


   .. method:: _wait(self: cwt.Process, esgf_process: float, sleep_time=2) -> bool

      Wait for an ESGF process to finish, while reporting its status


   .. method:: _process_results(self: cwt.Process, esgf_process: str, output_dir: Dict[str, str], expected_outputs) -> None

      Process the result of the execution


   .. method:: _write_outputs(self, url, output_dir, expected_outputs)

      Write the output netcdf url to a local drive



