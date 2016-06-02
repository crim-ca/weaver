=====================================
Twitcher: A simple OWS Security Proxy 
=====================================

.. image:: https://travis-ci.org/bird-house/twitcher.svg?branch=master
   :target: https://travis-ci.org/bird-house/twitcher
   :alt: Travis Build

Twitcher (the bird-watcher)
  *a birdwatcher mainly interested in catching sight of rare birds.* (`Leo <https://dict.leo.org/ende/index_en.html>`_).

Twitcher is a security proxy for Web Processing Services (WPS). The execution of a WPS process is blocked by the proxy. The proxy service provides access tokens (uuid, Macaroons) which needs to be used to run a WPS process. The access tokens are valid only for a short period of time.

The implementation is not restricted to WPS services. It will be extended to more OWS services like WMS (Web Map Service) and CSW (Catalogue Service for the Web) and might also be used for Thredds catalog services.

Twitcher is a **prototype** implemented in Python with the `Pyramid`_ web framework.

Twitcher is part of the `Birdhouse`_ project. The documentation is on `ReadTheDocs`_.

.. _Pyramid: http://www.pylonsproject.org
.. _Birdhouse: http://bird-house.github.io
.. _ReadTheDocs: http://twitcher.readthedocs.io/en/latest/
