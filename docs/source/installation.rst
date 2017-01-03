.. _installation:

************
Installation
************

The installation is using the Python distribution system `Anaconda`_ to maintain software dependencies. `Buildout`_ is used to setup the application with all services and configuration files.

Requirements
============

The installation works on Linux 64 bit distributions (tested on Ubuntu 14.04) and also on MacOS (tested on Sierra).

From GitHub Sources
===================

Install twitcher as normal user from GitHub sources:

.. code-block:: sh

   $ git clone https://github.com/bird-house/twitcher.git
   $ cd twitcher
   $ make clean install
   $ make test

The installation process setups a conda environment named *twitcher* with all dependent conda (and pip) packages. The installation folder (for configuration files, database etc) is by default ``~/birdhouse``. Configuration options can be overriden in the buildout ``custom.cfg`` file.

Starting Twitcher Service
=========================

Twitcher is run as `Gunicorn <http://gunicorn.org/>`_ WSGI application server behind the `Nginx <http://nginx.org/>`_ HTTP server. Starting/Stopping the services is controlled by `Supervisor <http://supervisord.org/>`_. This is described in the `Birdhouse documenation <http://birdhouse.readthedocs.io/en/latest/installation.html#nginx-gunicorn-and-supervisor>`_.

Start the twitcher service (using supervisor):

.. code-block:: sh

   $ make start  # or make restart

Check the status of the twitcher service:

.. code-block:: sh

    $ make status
    Supervisor status ...
    mongodb                          RUNNING   pid 6863, uptime 0:00:19
    nginx                            RUNNING   pid 6865, uptime 0:00:19
    twitcher                         RUNNING   pid 6864, uptime 0:00:19


You will find more information about the installation in the `Makefile documentation <http://birdhousebuilderbootstrap.readthedocs.io/en/latest/>`_.
