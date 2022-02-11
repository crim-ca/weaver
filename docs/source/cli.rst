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

.. contents::
    :local:
    :depth: 3

.. _client_commands:

------------------------
Python Client Commands
------------------------

For details about using the Python :py:class:`weaver.cli.WeaverClient`, please refer directly to its class
documentation and its underlying methods.

* :py:meth:`weaver.cli.WeaverClient.deploy`
* :py:meth:`weaver.cli.WeaverClient.undeploy`
* :py:meth:`weaver.cli.WeaverClient.capabilities`
* :py:meth:`weaver.cli.WeaverClient.describe`
* :py:meth:`weaver.cli.WeaverClient.execute`
* :py:meth:`weaver.cli.WeaverClient.monitor`
* :py:meth:`weaver.cli.WeaverClient.dismiss`
* :py:meth:`weaver.cli.WeaverClient.status`
* :py:meth:`weaver.cli.WeaverClient.results`
* :py:meth:`weaver.cli.WeaverClient.upload`


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

.. IMPORTANT:
..  Avoid using titles with only 'deploy', 'execute', etc., as they will conflict with auto-generated ones from CLI
.. _cli_examples:

------------------------
CLI and Client Examples
------------------------

Following sections present different typical usage of the :ref:`cli_commands` and :ref:`client_commands`.
Operations are equivalent between the :term:`CLI` and Python client.

Note that more operations and option parameters are available,
and are not all necessarily represented in below examples.

For each of the following examples, the client is created as follows:

.. code-block:: python

    client = WeaverClient(url="{WEAVER_URL}")


.. _cli_example_deploy:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deploy Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: example

.. _cli_undeploy:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Undeploy Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: example


.. _cli_example_getcap:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GetCapabilities Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`GetCapabilities <proc_op_getcap>` request to obtain a list of available :term:`Process`.

.. code-block:: shell

    weaver capabilities -u {WEAVER_URL}

.. code-block:: python

    client.capabilities()

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/local_process_listing.json
    :language: json


.. _cli_example_describe:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DescribeProcess Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`DescribeProcess <proc_op_describe>` request to obtain the :term:`Process` definition.

.. todo:: example

.. _cli_example_execute:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Execute Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`Execute <proc_op_execute>` request to obtain launch a :term:`Job`
with the specified :term:`Process` and provided inputs.

.. todo:: example

.. _cli_example_dismiss:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Dismiss Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: example


.. _cli_example_status:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GetStatus Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


.. todo:: example

.. _cli_example_monitor:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Monitor Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. todo:: example


.. _cli_example_results:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Results Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


.. todo:: example

.. _cli_example_upload:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upload Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This operation allows manual upload of a local file to the :term:`Vault`.

.. note::
    When running the :ref:`execute` operation, any detected local file reference will be automatically uploaded
    as :term:`Vault` file in order to make it available for the remote `Weaver` server for :term:`Process` execution.

.. seealso::
    :ref:`file_vault_inputs` and :ref:`vault` provide more details about this feature.

.. code-block:: shell

    weaver upload -u {WEAVER_URL} -f /path/to/file.txt

.. code-block:: python

    client.upload("/path/to/file.txt")

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/vault_file_uploaded.json
    :language: json
