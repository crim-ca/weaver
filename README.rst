=================================
Twitcher: A simple OWS Security Proxy 
=================================

.. image:: https://travis-ci.org/bird-house/twitcher.svg?branch=master
   :target: https://travis-ci.org/bird-house/twitcher
   :alt: Travis Build

.. _introduction:

Introduction
============

Twitcher (the bird-watcher)
  *a birdwatcher mainly interested in catching sight of rare birds.* (`Leo <https://dict.leo.org/ende/index_en.html#/search=twitcher>`_).

Twitcher is a security proxy for Web Processing Services (WPS). The execution of a WPS process is blocked by the proxy. The proxy service provides access tokens (uuid, Macaroons) which needs to be used to run a WPS process. The access tokens are valid only for a short period of time.

The implementation is not restricted to WPS services. It will be extended to more OWS services like WMS (Web Map Service) and CSW (Catalogue Service for the Web) and might also be used for Thredds catalog services.

Twitcher is a **prototype** implemented in Python with the `Pyramid web framework <http://www.pylonsproject.org/>`_.

Twitcher is part of the `Birdhouse <http://bird-house.github.io>`_ project. The documentation is on `ReadTheDocs <http://twitcher.rtfd.org/>`_.

Contents
--------

.. toctree::
   :maxdepth: 1

   overview
   installation
   configuration
   running
   tutorial
   api
   appendix

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
