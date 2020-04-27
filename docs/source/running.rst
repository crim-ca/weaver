.. _running:
.. include:: references.rst

****************
Running Weaver
****************

.. contents::
    :local:
    :depth: 2


Running Weaver Service
========================

Before running Weaver, you must make sure that the required `MongoDB`_ connection is accessible according to
specified connection settings in ``weaver/config/weaver.ini``.

.. seealso::
    - `weaver.ini.example`_

`Weaver` installation comes with a `Makefile`_ which provides a shortcut command to start the application with
`Gunicorn`_:

.. note::
    If using ``Windows``, make sure you have read the `Windows Installation <windows_install>`_ section.

.. code-block:: sh

    $ make start    # start Weaver WSGI application server


Weaver should be running after this operation.
It will be available under the configured URL endpoint in ``weaver.ini`` (see `example <weaver_config_example>`_).
If everything was configured correctly, calling this URL (default: ``http://localhost:4001``) should
provide a response containing a JSON body with basic information about Weaver.

Execution Details
----------------------

To execute, `Weaver` requires two type of application executed in parallel. First, it requires a WSGI HTTP server
that will run the application to provide API endpoints. This is referred to as ``weaver-manager`` in the provided
docker images. Second, `Weaver` requires a `Celery`_ task queue handler to execute submitted process jobs. This
is referred to as ``weaver-worker`` in built :term:`Docker` images.

For specific details about configuration of both applications, please refer to :ref:`Configuration` section.

The typical commands that need to be executed for the *manager* and *worker* applications should be similar to the
following calls. Obviously, additional arguments supported by the corresponding applications can be provided.

.. code-block:: sh

    # manager
    pserve <weaver-root>/config/weaver.ini

    # worker
    celery worker -A pyramid_celery.celery_app --ini <weaver-root>/config/weaver.ini


Using WPS Application
=====================

See :ref:`tutorial`.

.. _Makefile: ../../../Makefile
