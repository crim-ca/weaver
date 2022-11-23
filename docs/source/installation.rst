.. include:: references.rst
.. _installation:

************
Installation
************

.. contents::
    :local:
    :depth: 2

The installation is using the Python distribution system `Miniconda`_ (default installation of no ``conda`` found)
to maintain software dependencies. Any ``conda`` installation should work the same. To use a pre-installed ``conda``
distribution, simply make sure that it can be found on the shell path.

Requirements
============

The installation works on Linux 64 bit distributions (tested on Ubuntu 16.04).

.. note::
    Windows is *not officially supported*, but some patches have been applied to help using it.
    If you find some problems, please |submit-issue|_ or open a pull request with fixes.

From GitHub Sources
===================

Install weaver as normal user from GitHub sources:

.. code-block:: sh

   git clone https://github.com/crim-ca/weaver.git
   cd weaver
   make install

If no ``conda`` environment is activated, the ``install`` process will setup a new or reuse the conda environment
named ``weaver`` and install all dependency packages. If an environment is activated, `Weaver` will be installed in
that environment. You can also enforce a specific environment using:

.. code-block:: sh

   make CONDA_ENV=<my-env> install


.. _windows_install:

Windows Installation
=====================

*Minimal* support is provided to run the code on Windows. To do so, the ``Makefile`` assumes you are running in a
``MINGW`` environment, that ``conda`` is already installed, and that it is available from ``CONDA_HOME`` variable or
similar. If this is not the case, you will have to adjust the reference variables accordingly.

.. note::
    Windows support is not official and any dependency could stop supporting it at any given time. Particularly,
    libraries for `Celery`_ task execution have a tendency to break between versions for Windows. The application
    is regularly evaluated on a Linux virtual machine. It is recommended to run it as so or using the existing
    Docker images.

Known issues
------------

* Package ``shapely.geos`` has C++ dependency to ``geos`` library. If the package was installed in a ``conda``
  environment, but through ``pip install`` call, the source path will not be found. You have to make sure to install
  it using ``conda install -c conda-forge shapely``.
* The example `weaver.ini.example`_ file uses ``gunicorn`` by default to take advantage of its performance features,
  but this package does not support Windows. Alternatively, you might need to use ``waitress`` by replacing it in the
  ``[server:main]`` section.


Please refer to :ref:`Configuration` and :ref:`Running` sections for following steps.

.. _database_migration:

=====================
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
versions ``3.6``, ``4.0``, ``4.2``, ``4.4`` and ``5.0``, where ``VERSION`` is the new version above the current one.

.. code-block:: shell

    docker run --name mongo -v <DB_DATA_PATH>:/data/db -d mongo:<VERSION>
    docker exec -ti mongo mongo

    # in docker, should answer with: { "ok" : 1 }
    db.adminCommand( { setFeatureCompatibilityVersion: "<VERSION>" } )
    exit

    # back in shell
    docker stop mongo && docker rm mongo
