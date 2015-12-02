.. _installing:

**********
Installing
**********

The installation is using the Python distribution system `Anaconda <http://www.continuum.io/>`_ to maintain software dependencies. 

The installation works on Linux 64 bit distributions (tested on Ubuntu 14.04) and also on MacOSX (tested on El Capitan).

Install twitcher as normal user from GitHub sources:

.. code-block:: sh

   $ git clone https://github.com/bird-house/twitcher.git
   $ cd twitcher
   $ make install
   $ make test

The installation process setups a conda environment named birdhouse. All additional packages and configuration files are going into this conda environment. The location is ``~/.conda/envs/birdhouse``.

Start the twitcher service (supervisor):

.. code-block:: sh

   $ make start  # or make restart
  
Check the status of the twitcher service:

.. code-block:: sh

    $ make status
    Supervisor status ...
    mongodb                          RUNNING   pid 6863, uptime 0:00:19
    nginx                            RUNNING   pid 6865, uptime 0:00:19
    twitcher                         RUNNING   pid 6864, uptime 0:00:19


You will find more information about the installation in the `Makefile documentation <http://birdhousebuilderbootstrap.readthedocs.org/en/latest/>`_.
