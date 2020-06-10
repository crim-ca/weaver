.. _installation:
.. include:: references.rst

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
    If you find some problems, please submit an `issue <weaver-issues`_ or open a pull request with fixes.

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

Please refer to :ref:`Configuration` and :ref:`Running` sections for following steps.
