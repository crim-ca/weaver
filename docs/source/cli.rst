.. include:: references.rst
.. _cli:

*********************
Weaver CLI and Client
*********************

Once `Weaver` package is installed (see :ref:`installation`), it provides a command line interface (:term:`CLI`)
as well as a Python :py:class:`weaver.cli.WeaverClient` to allow simplified interactions through shell calls or
Python scripts.

This offers to the user methods to use file references (e.g.: local :term:`CWL` :term:`Application Package` definition)
to rapidly operate with functionalities such as :ref:`Deploy <proc_op_deploy>`, :ref:`Describe <proc_op_describe>`,
:ref:`Execute <proc_op_execute>` and any other operation described in :ref:`proc_operations` section.

Please refer to following sections for more details.

.. _client_commands:

------------------------
Python Client Commands
------------------------

For details about using the Python :py:class:`weaver.cli.WeaverClient`, please refer directly to its class
documentation and its underlying methods.

.. _cli_commands:

------------------------
Shell CLI Commands
------------------------

Following are the detail for the shell :term:`CLI` which provides the same features.

.. https://sphinx-argparse.readthedocs.io/en/stable/usage.html
.. function must return an 'argparse.ArgumentParser' instance
.. argparse::
    :module: weaver.cli
    :func: make_parser
    :prog: weaver

.. _cli_examples:

------------------------
CLI and Client Examples
------------------------

Following sections present different typical usage of the :ref:`cli_commands` and :ref:`client_commands`.
Operations are equivalent between the :term:`CLI` and Python client.

Note that more operations and option parameters are available,
and are not all necessarily represented in below examples.


.. _cli_deploy:

~~~~~~~~~~~~~~~~~
Deploy
~~~~~~~~~~~~~~~~~

.. todo:: example

.. _cli_undeploy:

~~~~~~~~~~~~~~~~~
Undeploy
~~~~~~~~~~~~~~~~~

.. todo:: example


.. _cli_getcap:

~~~~~~~~~~~~~~~~~
GetCapabilities
~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`GetCapabilities <proc_op_getcap>` request to obtain a list of available :term:`Process`.

.. code-block:: shell

    weaver capabilities -u {WEAVER_URL}

.. code-block:: python

    WeaverClient(url="{WEAVER_URL}").capabilities()

Sample Output:

.. code-block:: json

    {
      "description": "Listing of available processes successful.",
      "processes": [
        "docker-demo-cat",
        "docker-python-script",
        "Echo",
        "file_index_selector",
        "file2string_array",
        "image-utils",
        "jsonarray2netcdf",
        "las2tif",
        "metalink2netcdf",
        "sleep",
      ],
      "page": 0,
      "total": 25,
    }


.. _cli_describe:

~~~~~~~~~~~~~~~~~
DescribeProcess
~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`DescribeProcess <proc_op_describe>` request to obtain the :term:`Process` definition.

.. todo:: example

.. _cli_execute:

~~~~~~~~~~~~~~~~~
Execute
~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`Execute <proc_op_execute>` request to obtain launch a :term:`Job`
with the specified :term:`Process` and provided inputs.

.. todo:: example

.. _cli_dismiss:

~~~~~~~~~~~~~~~~~
Dismiss
~~~~~~~~~~~~~~~~~

.. todo:: example


.. _cli_status:

~~~~~~~~~~~~~~~~~
GetStatus
~~~~~~~~~~~~~~~~~


.. todo:: example

.. _cli_monitor:

~~~~~~~~~~~~~~~~~
Monitor
~~~~~~~~~~~~~~~~~

.. todo:: example


.. _cli_results:

~~~~~~~~~~~~~~~~~
Results
~~~~~~~~~~~~~~~~~


.. todo:: example

.. _cli_upload:

~~~~~~~~~~~~~~~~~
Upload
~~~~~~~~~~~~~~~~~

This operation allows manual upload of a local file to the :term:`Vault`.

.. note::
    When running the :ref:`cli_execute` operation, any detected local file reference will be automatically uploaded
    as :term:`Vault` file in order to make it available for the remote `Weaver` server for :term:`Process` execution.

.. seealso::
    :ref:`file_vault_inputs` and :ref:`vault` provide more details about this feature.

.. todo:: example
