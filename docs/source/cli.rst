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

.. note::
    Technically, any :term:`OGC API - Processes` implementation could be supported using the provided :term:`CLI`
    and :py:class:`weaver.cli.WeaverClient`. There are however some operations such as :ref:`vault_upload` feature
    (and any utility that makes use of it) that are applicable only for `Weaver` instances.

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

.. note::
    Much more operations and option parameters are available.
    They are not all necessarily represented in below examples.
    Explore available arguments using ``weaver <operation> --help`` or
    using the above documentation for :ref:`client_commands` and `cli_commands`.

For each of the following examples, the client is created as follows:

.. code-block:: python

    client = WeaverClient(url="{WEAVER_URL}")


.. _cli_example_auth:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Authentication Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For any operation that requires authentication/authorization to access a protected service targeted by ``{WEAVER_URL}``,
it is possible to either provide the ``auth`` parameter during initialization of the :py:class:`weaver.cli.WeaverClient`
itself (the specific :py:class:`weaver.cli.AuthHandler` is reused for **all** operations), or as argument to individual
methods when calling the respective operation (handler only used for that step).

Any class implementation that derives from :py:class:`weaver.cli.AuthHandler` or :py:class:`requests.auth.AuthBase` can
be used for the ``auth`` argument. This class must implement the ``__call__`` method taking a single ``request``argument
and returning the adjusted ``request`` instance. The call should apply any relevant modifications to grant the necessary
authentication/authorization details. This ``__call__`` will be performed inline prior to sending the actual request
toward the service.

.. note::
    There are multiple predefined handlers available for use:

    - :py:class:`requests.auth.HTTPBasicAuth`
    - :py:class:`requests.auth.HTTPProxyAuth`
    - :py:class:`requests.auth.HTTPDigestAuth`
    - :py:class:`weaver.cli.BasicAuthHandler`
    - :py:class:`weaver.cli.BearerAuthHandler`
    - :py:class:`weaver.cli.CookieAuthHandler`
    - |requests-magpie-auth|_

.. |requests-magpie-auth| replace:: ``requests_magpie.MagpieAuth``
.. _requests-magpie-auth: https://github.com/Ouranosinc/requests-magpie/blob/master/requests_magpie.py

When using the :ref:`cli_commands`, the specific :py:class:`weaver.cli.AuthHandler` implementation to employ
must be provided using the ``--auth-handler`` (``-aH``) argument. This can be an importable (installed) class module
reference or a plain Python script path separated with a ``:`` character followed by the class name definition.
Other ``--auth`` prefixed arguments can also be supplied, but their actual use depend on the targeted authentication
handler implementation.

Below are examples of possible commands:

.. code-block:: shell

    weaver capabilities -u {WEAVER_URL} -aH requests_magpie.MagpieAuth -aU ${MAGPIE_URL} -aI <username> -aP <password>

When using the :ref:`Python Interface <client_commands>`, the desired implementation can be specified directly.

.. code-block:: python

    client.capabilities(auth=requests_magpie.MagpieAuth("${MAGPIE_URL]", "<username>", "<password>"))


.. _cli_example_deploy:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deploy Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`Deployment <proc_op_deploy>` request in order to subscribe a new :term:`Process` in the service.
Requires a `Weaver` or |ogc-api-proc-part2|_ compliant instance.

The :term:`Process` can correspond to an :ref:`application-package` using :term:`CWL` (i.e.: a script, a :term:`Docker`
application, etc.) or a :ref:`proc_remote_provider` using an external :term:`WPS` (:term:`XML`, :term:`JSON`) or another
:term:`OGC API - Processes` instance.
A :term:`Workflow` of multiple :term:`Process` references (possibly of distinct nature) can also be deployed.

.. seealso::
    Chapter :ref:`proc_types` covers supported definitions and further explain each type.

.. note::
    If the :ref:`application-package` being deployed employs a protected :term:`Docker` repository reference, access
    can be provided using the corresponding parameters. Those will be required for later execution of the application
    in order to retrieve the referenced :term:`Docker` image.

.. note::
    Content definitions for :term:`CWL` :ref:`application-package` and/or the literal :term:`Process` body
    can be submitted using either a local file reference, an URL, or a literal string formatted as :term:`JSON`
    or :temr:`YAML`. With the :ref:`Python Interface <client_commands>`, the definition can also be provided
    with a :class:`dict` directly.

Below is a sample :term:`Process` deployment using a basic Python script wrapped in a :term:`Docker` image to ensure
all requirements are met. The :term:`CWL` definition provides all necessary inputs and outputs definition to run the
desired :ref:`application-package`.
The contents of below URL definition is also available in :ref:`example_app_pkg_script`.

.. code-block:: shell

    weaver deploy -u {WEAVER_URL} \
        -p docker-python-script-report \
        --cwl https://raw.githubusercontent.com/crim-ca/weaver/master/docs/examples/docker-python-script-report.cwl

.. code-block:: python

    client.deploy(
        process_id="docker-python-script-report",
        cwl="https://raw.githubusercontent.com/crim-ca/weaver/master/docs/examples/docker-python-script-report.cwl",
    )

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/local_process_deploy_success.json
    :language: json


.. _cli_undeploy:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Undeploy Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the *Undeployment* request to remove a previously :ref:`Deployed <proc_op_deploy>` :term:`Process`
from the service. Requires a `Weaver` or |ogc-api-proc-part2|_ compliant instance.

.. code-block:: shell

    weaver undeploy -u {WEAVER_URL} -p docker-python-script-report

.. code-block:: python

    client.undeploy("docker-python-script-report")

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/local_process_undeploy_success.json
    :language: json

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

.. code-block:: shell

    weaver describe -u {WEAVER_URL} -p jsonarray2netcdf

.. code-block:: python

    client.describe("jsonarray2netcdf")

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/local_process_description_ogc_api.json
    :language: json

.. _cli_example_execute:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Execute Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`Execute <proc_op_execute>` request to launch a :term:`Job` execution with the
specified :term:`Process` and provided inputs. Execution can also take multiple execution control parameters
such as requesting outputs by reference, selecting the (a)synchronous mode to be employed and much more.

.. seealso::
    Please refer to :meth:`weaver.cli.WeaverClient.execute` arguments, :term:`CLI` :ref:`execute` operation and chapter
    :ref:`Execute <proc_op_execute>` documentation for more details regarding all implications of :term:`Job` execution.
    File reference types, request contents, execution modes and other advanced use cases are covered in greater extent.

.. note::
    Parameters available for :ref:`Status Monitoring <cli_example_monitor>` can also be provided directly during this
    operation. This has the effect of executing the :term:`Job` and immediately monitor the obtained status until the
    completed status is obtained, or timeout is reached, whichever occurs first.

.. note::
    Any valid *local* file path given as input for the :term:`Job` execution will be automatically uploaded toward
    the service (`Weaver` required) in order to make it available for the underlying application defined by
    the :term:`Process`.
    The same procedure as the :ref:`Manual Upload <cli_example_upload>` operation is employed to temporarily place the
    file(s) in the :term:`Vault` and make it accessible only for the submitted :term:`Job`. The file(s) submitted this
    way will be deleted once retrieved by the :term:`Process` for execution.

In order to use the :ref:`cli_commands`, the :term:`Job` inputs definition has been made extremely versatile.
Arguments can be provided using literal string entries by repeating ``-I`` options followed by their desired
:term:`KVP` definitions. Additional properties can also be supplied in order to specify precisely what needs
to be submitted to the :term:`Process`. Please refer to :term:`CLI` :ref:`execute` help message for more explanations.

.. code-block:: shell

    weaver execute -u {WEAVER_URL} -p Echo \
        -I "message='Hello World!'" \
        -I value:int=123456 \
        -I array:float=1.23,4.56 \
        -I multi:File=http://example.com/data.json;=http://other.com/catalog.json \
        -I multi:File=http://another.com/data.json \
        -I single:File=/workspace/data.xml@mediaType=text/xml

Inputs can also be provided using a :term:`JSON` or :term:`YAML` :term:`Job` document (as when running :term:`CWL`)
or using a :term:`JSON` document matching the schema normally submitted by HTTP request for :term:`OGC APi - Processes`
execution.

When using the :ref:`Python Interface <client_commands>`, the inputs can be provided in the same manner as for the
above :term:`CLI` variations, but it is usually more intuitive to use a Python :class:`dict` directly.

.. code-block:: python

    client.execute("Echo", {
        "message": "Hello World!",
        "value": 123456,
        "array": [1.23, 4.56],
        "multi": [
            {"href": "http://example.com/data.json"},
            {"href": "http://other.com/catalog.json"},
            {"href": "http://another.com/data.json"},
        ],
        "single": {
            "href": "/workspace/data.xml@mediaType",  # note: uploaded to vault automatically before execution
            "type": "text/xml",
        }
    })

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/job_status_accepted.json
    :language: json

.. _cli_example_dismiss:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Dismiss Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :term:`Job` dismiss request to either cancel an accepted or running :term:`Job` or to remove
any stored results from a successful execution.

.. code-block:: shell

    weaver dismiss -u {WEAVER_URL} -j "29af3a33-0a3e-477d-863e-efccc97e0b02"

.. code-block:: python

    client.dismiss("29af3a33-0a3e-477d-863e-efccc97e0b02")

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/job_dismiss_success.json
    :language: json

.. _cli_example_status:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GetStatus Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :ref:`GetStatus <proc_op_status>` operation to request the current status of a :term:`Job`.

.. code-block:: shell

    weaver status -u {WEAVER_URL} -j "797c0c5e-9bc2-4bf3-ab73-5f3df32044a8"

.. code-block:: python

    client.status("797c0c5e-9bc2-4bf3-ab73-5f3df32044a8")


Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/job_status_success.json
    :language: json

.. _cli_example_jobs:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Jobs Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Accomplishes the :term:`Job` listing request to obtain known :term:`Job` definitions using filter search queries.

.. code-block:: shell

    weaver jobs -u {WEAVER_URL} -nL

.. code-block:: python

    client.jobs(with_links=False)

.. note::
    Option ``-nL`` and argument ``with_links`` are used to omit ``links`` section in sample output.

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/job_listing.json
    :language: json

.. _cli_example_monitor:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Monitor Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a :term:`Job` was summited for execution, it is possible to perform :ref:`Status Monitoring <proc_op_monitor>` of
this :term:`Job` until completion or until the specified timeout is reached. This can be performed at any moment on
a pending or running :term:`Job`.

.. seealso::
    It is possible to directly perform monitoring when calling the :ref:`Job Execution <cli_example_execute>` operation.
    Simply provide the relevant arguments and options applicable to the monitoring step during the ``execute`` call.


.. code-block:: shell

    # assuming job is 'running'
    weaver monitor -u {WEAVER_URL} -j "14c68477-c3ed-4784-9c0f-a4c9e1344db5"

.. code-block:: python

    client.results("14c68477-c3ed-4784-9c0f-a4c9e1344db5")


Monitor output should be in as similar format as :ref:`cli_example_status` with the latest :term:`Job` status retrieved.

.. _cli_example_results:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Results Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retrieves the :ref:`Job Results <proc_op_result>` from a successful :term:`Job` execution.

.. note::
    It is possible to employ the ``download`` argument to retrieve ``File`` outputs from a :term:`Job`. If this is
    enabled, files will be downloaded using the URL references specified in the :term:`Job` results and store them
    in the specified local output directory.

.. code-block:: shell

    weaver results -u {WEAVER_URL} -j "14c68477-c3ed-4784-9c0f-a4c9e1344db5"

.. code-block:: python

    client.results("14c68477-c3ed-4784-9c0f-a4c9e1344db5")


Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/job_results.json
    :language: json

.. _cli_example_upload:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upload Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This operation allows manual upload of a local file to the :term:`Vault`.

.. note::
    When running the :ref:`execute` operation, any detected local file reference will be automatically uploaded
    as :term:`Vault` file in order to make it available for the remote `Weaver` server for :term:`Process` execution.

.. seealso::
    :ref:`file_vault_inputs` and :ref:`vault_upload` provide more details about this feature.

.. code-block:: shell

    weaver upload -u {WEAVER_URL} -f /path/to/file.txt

.. code-block:: python

    client.upload("/path/to/file.txt")

Sample Output:

.. literalinclude:: ../../weaver/wps_restapi/examples/vault_file_uploaded.json
    :language: json
