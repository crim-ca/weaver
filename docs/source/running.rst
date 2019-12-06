.. _running:

****************
Running weaver
****************

.. contents::
    :local:
    :depth: 2


Running Weaver Service
========================

Before running Weaver, you must make sure that the required ``MongoDB`_ connection is accessible (according to
specified connection settings in ``weaver/config/weaver.ini``).

The Weaver installation comes with a ``Makefile`` which provides a shortcut command to start the application with
`Gunicorn`_:

.. code-block:: sh

    $ cd weaver     # cd into weaver installation directory
    $ make start    # start weaver WSGI application server


Weaver should be running after this operation.
It will be available under the configured URL endpoint in ``weaver/config/weaver.ini``.
If everything was configured correctly, calling this URL (default: ``http://localhost:4001``) should
provide a response containing a JSON body with basic information about Weaver.

.. _Gunicorn: http://gunicorn.org/
.. _MongoDB: https://www.mongodb.com/

Using WPS Application
=====================

See the :ref:`tutorial`.
