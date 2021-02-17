:mod:`weaver.processes.wps_workflow`
====================================

.. py:module:: weaver.processes.wps_workflow


Module Contents
---------------

.. data:: LOGGER
   

   

.. data:: DEFAULT_TMP_PREFIX
   :annotation: = tmp

   

.. function:: default_make_tool(toolpath_object: ToolPathObjectType, loading_context: LoadingContext, get_job_process_definition: GetJobProcessDefinitionFunction) -> ProcessCWL


.. py:class:: CallbackJob(: WpsWorkflow, job: Callable[[Any, Any], Any], output_callback: Builder, cachebuilder: Text, jobcache)



   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: run(self: RuntimeContext, loading_context) -> None



.. py:class:: WpsWorkflow(: Dict[Text, Any], toolpath_object: LoadingContext, loading_context: GetJobProcessDefinitionFunction, get_job_process_definition)



   Build a Process object from the provided dictionary.

   .. method:: job(self, joborder: Dict[Text, AnyValue], output_callbacks: Callable[[Any, Any], Any], runtime_context: RuntimeContext) -> Generator[Union[JobBase, CallbackJob], None, None]

      Workflow job generator.

      :param joborder: inputs of the job submission
      :param output_callbacks: method to fetch step outputs and corresponding step details
      :param runtime_context: configs about execution environment
      :return:


   .. method:: collect_output_ports(self, ports: Set[Dict[Text, Any]], builder: Builder, outdir: Text, compute_checksum: bool = True, jobname: Text = '', readers: Dict[Text, Any] = None) -> OutputPorts


   .. method:: collect_output(self, schema: Dict[Text, Any], builder: Builder, outdir: Text, fs_access: StdFsAccess, compute_checksum: bool = True) -> Optional[Union[Dict[Text, Any], List[Union[Dict[Text, Any], Text]]]]



.. py:class:: WpsWorkflowJob(builder: Builder, joborder: Dict[Text, Union[Dict[Text, Any], List, Text, None]], requirements: List[Dict[Text, Text]], hints: List[Dict[Text, Text]], name: Text, wps_process: WpsProcessInterface, expected_outputs: List[ExpectedOutputType])



   Initialize the job object.

   .. method:: run(self, runtimeContext: RuntimeContext, tmpdir_lock: Optional[ThreadLock] = None) -> None


   .. method:: execute(self: List[Text], runtime: MutableMapping[Text, Text], env: RuntimeContext, runtime_context) -> None



