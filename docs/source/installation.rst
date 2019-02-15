.. _installation:

************
Installation
************

The installation is using the Python distribution system `Anaconda`_ to maintain software dependencies. `Buildout`_
is used to setup the application with all services and configuration files.

Requirements
============

The installation works on Linux 64 bit distributions (tested on Ubuntu 14.04) and also on MacOS (tested on Sierra).

From GitHub Sources
===================

Install weaver as normal user from GitHub sources:

.. code-block:: sh

   $ git clone https://github.com/bird-house/weaver.git
   $ cd weaver
   $ make clean install
   $ make test

The installation process setups a conda environment named *weaver* with all dependent conda (and pip) packages.
The installation folder (for configuration files, database etc) is by default ``~/birdhouse``.
Configuration options can be overridden in the buildout ``custom.cfg`` file.

Starting weaver Service
=========================

weaver is run as `Gunicorn`_ WSGI application server behind the `Nginx`_ HTTP server. Starting/Stopping the
services is controlled by `Supervisor`_. This is described in the `Birdhouse documentation`_.

Start the weaver service (using supervisor):

.. code-block:: sh

   $ make start  # or make restart

Check the status of the weaver service:

.. code-block:: sh

    $ make status
    Supervisor status ...
    mongodb                          RUNNING   pid 6863, uptime 0:00:19
    nginx                            RUNNING   pid 6865, uptime 0:00:19
    weaver                         RUNNING   pid 6864, uptime 0:00:19


You will find more information about the installation in the `Makefile documentation`_.


.. _Anaconda: https://www.anaconda.com/
.. _Birdhouse documentation: http://birdhouse.readthedocs.io/en/latest/installation.html#nginx-gunicorn-and-supervisor
.. _Buildout: https://github.com/buildout/buildout
.. _Gunicorn: http://gunicorn.org/
.. _Makefile documentation: http://birdhousebuilderbootstrap.readthedocs.io/en/latest/
.. _Nginx: http://nginx.org/
.. _Supervisor: http://supervisord.org/
