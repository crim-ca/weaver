===================
Welcome to Twitcher 
===================

.. image:: https://travis-ci.org/bird-house/twitcher.svg?branch=master
   :target: https://travis-ci.org/bird-house/twitcher
   :alt: Travis Build

.. _introduction:

Introduction
============

Twitcher (the bird-watcher)
  *a birdwatcher mainly interested in catching sight of rare birds.* (`Leo <https://dict.leo.org/ende/index_en.html#/search=twitcher>`_).

Twitcher is a security proxy for Web Processing Services (WPS). The execution of a WPS process is blocked by the proxy. The proxy service provides access tokens (uuid, Macaroons) which needs to be used to run a WPS process. The access tokens are valid only for a short period of time.

Twitcher is a prototype implemented in Python with the Pyramid web framework.

Twitcher comes in two flavours:

* *A security proxy for Web Processing Services implemented in Python*
* *A security proxy for PyWPS with WSGI application layers*

Twitcher may become a candidate for the `GeoPython <http://geopython.github.io/>`_ project. 

Twitcher is part of the `Birdhouse <http://bird-house.github.io>`_ project.

The documentation is on `ReadTheDocs <http://twitcher.rtfd.org/>`_.

Contents:

.. toctree::
   :maxdepth: 1

   installation
   configuration
   tutorial
   appendix

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
