.. include:: references.rst
.. _installation:

************
Installation
************

.. contents::
    :local:
    :depth: 2

.. _installation-docker:

Docker Installation
===================

The Docker installation is recommended to ensure reproducibility of the environment and `Weaver` dependencies.
It is the quickest way to get started with the application.

You can obtain the latest images (or a specific version of you choosing) as follows.
The base image contains the source code and all dependencies, while the ``manager`` and ``worker``
images define the commands used to run the :term:`API` and the `Celery`_ workers respectively.

.. code-block:: sh

    docker pull pavics/weaver:latest
    docker pull pavics/weaver:latest-manager
    docker pull pavics/weaver:latest-worker

To run :ref:`CLI <cli>` commands, you can run the following.

.. code-block:: sh

    docker run -it --rm pavics/weaver:latest weaver --help

To run the :term:`API` and worker services, it is recommended to use the *Docker Compose*
configuration because the service must employ a companion `MongoDB`_ container and a ``docker-proxy``
service to run :ref:`app_pkg_docker` per respective :term:`Process`.

.. seealso::
    - See :ref:`configuration` to modify application behaviour. A custom INI file should be mounted in the container.
    - `Example Configuration Files <https://github.com/crim-ca/weaver/tree/master/config>`_
    - `Example Docker-Compose YAML <https://github.com/crim-ca/weaver/blob/master/docker/docker-compose.yml.example>`_

.. _installation-python:

Python Installation
===================

Prerequisites
-------------------

The installation is using the Python distribution system `Miniconda`_ (default installation of no ``conda`` found)
to maintain software dependencies. Any ``conda``-based installation should work the same.
To use a pre-installed ``conda`` distribution, simply make sure that it can be found on the shell path.
If not auto-detected, you can hint ``make`` commands about its location using the ``CONDA_HOME`` variable.

You can also employ your own environment management system, by pre-activating it and running ``make`` commands
with the ``CONDA_CMD=""`` variable.

To avoid repeating variables on each command, you can define them in ``Makefile.config`` at the root of the repository.

.. seealso::
    Example `Makefile.config.example`_

The installation works on Linux 64 bit distributions (tested on all Ubuntu LTS versions since 16.04).

.. warning::
    :ref:`installation-windows` is *not officially supported*, but some patches have been applied to help using it.
    If you find some problems, please |submit-issue|_ or open a pull request with fixes.

.. _installation-github:

From GitHub Sources
-------------------

Install Weaver as normal user from GitHub sources:

.. code-block:: sh

   pip install https://github.com/crim-ca/weaver

Alternatively, you can also clone the repository and install it from there.
This is useful if you want to develop the code or contribute to the project.

.. code-block:: sh

   git clone https://github.com/crim-ca/weaver.git
   cd weaver
   make install

If no ``conda`` environment is activated, the ``install`` process will setup a new or reuse the conda environment
named ``weaver`` and install all dependency packages. If an environment is activated, `Weaver` will be installed in
that environment. You can also enforce a specific environment using:

.. code-block:: sh

   make CONDA_ENV=<my-env> install

You can then run the :term:`API` and worker services using the corresponding commands with
your custom `weaver.ini.example`_ configuration file (see :ref:`Configuration` section).

.. code-block:: sh

    # API service
    pserve config/weaver.ini

    # Celery worker service
    celery -A pyramid_celery.celery_app worker -B -E --ini config/weaver.ini

.. warning::
    `Weaver` typically relies (or expects) some files to be served online for inputs and outputs staging.
    To run locally, you might want to consider running a file server to make them look like HTTP resources.

    .. code-block:: sh

        python -m http.server 8000 -b 127.0.0.1 --directory <weaver.wps_output_dir>

.. _installation-windows:

Windows Installation
---------------------

*Minimal* support is provided to run the code on Windows. To do so, the ``Makefile`` assumes you are running in a
``MINGW`` environment, that ``conda`` is already installed, and that it is available from ``CONDA_HOME`` variable or
similar. If this is not the case, you will have to adjust the reference variables accordingly.

.. warning::
    Windows support is not official and any dependency could stop supporting it at any given time. Particularly,
    libraries for `Celery`_ task execution have a tendency to break between versions for Windows. The application
    is regularly evaluated on a Linux virtual machine. It is recommended to run it as so or using the existing
    Docker images.

.. _installation-windows-issues:

Known Issues
~~~~~~~~~~~~

* Package ``shapely.geos`` has C++ dependency to ``geos`` library. If the package was installed in a ``conda``
  environment, but through ``pip install`` call, the source path will not be found. You have to make sure to install
  it using ``conda install -c conda-forge shapely``.
* The example `weaver.ini.example`_ file uses ``gunicorn`` by default to take advantage of its performance features,
  but this package does not support Windows. Alternatively, you might need to use ``waitress`` by replacing it in the
  ``[server:main]`` section.

.. seealso::
    Please refer to :ref:`Configuration` and :ref:`Running` sections for following steps.

.. _database_migration:

Database Migration
=====================

.. versionadded:: 4.3

Previous versions of `Weaver` did not require any specific version of `MongoDB`_.
Features were working using version as early as ``mongo==3.4`` if not even older.
Due to more recent search capabilities, performance improvements and security fixes,
minimum requirement of ``mongo==5.0`` has been made mandatory.

In terms of data itself, there should be no difference, unless more advanced usage (e.g.: Replica Sets) were configured
on your side. See relevant |mongodb-docs|_ as needed in this case. Otherwise, employed ``mongodb`` instance simply needs
to be updated with the relevant versions.

To simplify to process, the following procedure is recommended to avoid installing `MongoDB` libraries.
Assuming the current version is ``3.4``, below operations must be executed iteratively for every migration step of
versions ``3.6``, ``4.0``, ``4.2``, ``4.4``, ``5.0``, etc., where ``VERSION`` is the new version above the current one.

.. code-block:: shell

    cmd=mongo  # if <6.0, otherwise 'mongosh'
    docker run --name mongo -v <DB_DATA_PATH>:/data/db -d mongo:<VERSION>
    docker exec -ti mongo ${cmd}

    # in docker, should answer with: { "ok" : 1 }
    db.adminCommand( { setFeatureCompatibilityVersion: "<VERSION>" } )
    exit

    # back in shell
    docker stop mongo && docker rm mongo

.. note::
   It is important to run the docker using use the *next* version to perform the migration
   from the *current* feature (iteratively) to the next one.

   The operation as been validated up to ``7.0``, but more recent version should be directly supported as well since
   the `MongoDB`_ features employed by `Weaver` are fairly core definitions.

.. warning::
   Prior to ``6.0``, the ``mongo`` command is employed, whereas ``mongosh`` is used for later versions.

.. warning::
   With version ``7.0``, the command must also include a confirmation, since downgrade will not be possible anymore.

   .. code-block:: shell

        db.adminCommand( { setFeatureCompatibilityVersion: "7.0", confirm: true } )
