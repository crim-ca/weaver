=======================================
Welcome to pywps-proxy's documentation!
=======================================

.. image:: https://travis-ci.org/bird-house/pywps-proxy.svg?branch=master
   :target: https://travis-ci.org/bird-house/pywps-proxy
   :alt: Travis Build

.. _introduction:

Introduction
============

pywps-proxy is a security proxy for Web Processing Services (WPS). The execution of a WPS process is blocked by the proxy. The proxy service provides access tokens (uuid) which needs to be used to run a WPS process. The access tokens are valid only for a short period of time.

pywps-proxy is a prototype implemented in Python with the Pyramid web framework.

pywps-proxy comes in two flavours:

* *A security proxy for Web Processing Services implemented in Python*
* *A security proxy for PyWPS with WSGI application layers*

pywps-proxy is a working title. It's not a *bird* yet. It may become a candidate for the `GeoPython <http://geopython.github.io/>`_ project. 

pywps-proxy is part of the `Birdhouse <http://bird-house.github.io>`_ project.

Contents:

.. toctree::
   :maxdepth: 1

   appendix

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
