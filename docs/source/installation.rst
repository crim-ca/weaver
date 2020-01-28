.. _installation:

************
Installation
************

The installation is using the Python distribution system `Anaconda`_ to maintain software dependencies.

Requirements
============

The installation works on Linux 64 bit distributions (tested on Ubuntu 16.04).

From GitHub Sources
===================

Install weaver as normal user from GitHub sources:

.. code-block:: sh

   $ git clone https://github.com/crim-ca/weaver.git
   $ cd weaver
   $ make clean install
   $ make test

The installation process setups a conda environment named *weaver* with all dependent conda (and pip) packages.
Configuration options can be overridden with files located in ``weaver/config`` directory.


.. _Anaconda: https://www.anaconda.com/
