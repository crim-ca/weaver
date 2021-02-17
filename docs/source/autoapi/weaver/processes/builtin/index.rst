:mod:`weaver.processes.builtin`
===============================

.. py:module:: weaver.processes.builtin


Submodules
----------
.. toctree::
   :titlesonly:
   :maxdepth: 1

   file2string_array/index.rst
   jsonarray2netcdf/index.rst
   metalink2netcdf/index.rst
   utils/index.rst


Package Contents
----------------

.. function:: register_builtin_processes(container: AnySettingsContainer) -> None

   Registers every ``builtin`` CWL package to the processes database.

   CWL definitions must be located within the :mod:`weaver.processes.builtin` module.


.. py:class:: BuiltinProcess(toolpath_object: MutableMapping[str, Any], loadingContext: LoadingContext)



   Initialize this CommandLineTool.

   .. method:: make_job_runner(self: RuntimeContext, runtime_context) -> Type[JobBase]



