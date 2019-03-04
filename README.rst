=============================================
Weaver: workflow execution management service
=============================================

.. # TODO: adjust references

.. image:: https://img.shields.io/badge/docs-latest-brightgreen.svg
   :target: http://weaver.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

.. image:: https://travis-ci.org/bird-house/weaver.svg?branch=master
   :target: https://travis-ci.org/bird-house/weaver
   :alt: Travis Build

.. image:: https://img.shields.io/github/license/bird-house/weaver.svg
   :target: https://github.com/bird-house/weaver/blob/master/LICENSE.txt
   :alt: GitHub license

.. image:: https://badges.gitter.im/bird-house/birdhouse.svg
   :target: https://gitter.im/bird-house/birdhouse?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge
   :alt: Join the chat at https://gitter.im/bird-house/birdhouse


Weaver (the nest-builder)
  *Weaver birds build exquisite and elaborate nest structures that are a rival to any human feat of engineering.
  Some of these nests are the largest structures to be built by birds.*
  (`Eden <https://eden.uktv.co.uk/animals/birds/article/weaver-birds/>`_).

  *Although weavers are named for their elaborately woven nests, some are notable for their selective parasitic nesting habits instead.*
  (`Wikipedia <https://en.wikipedia.org/wiki/Ploceidae>`_)

`Weaver` is an `Execution Management Service (EMS)` that allows the execution of workflows chaining various
application and `Web Processing Services (WPS)` inputs and outputs. It allows using remote
`Application Deployment and Execution Services (ADES)` to dispatch application executions as defined by
`Common Workflow Language (CWL)` configuration.

The project is developed and based of `OGC Testbed-14 – ESA Sponsored Threads – Exploitation Platform` findings and
following improvements.

`Weaver` is a **prototype** implemented in Python with the `Pyramid`_ web framework.

`Weaver` is part of the `Birdhouse`_ project.

.. _Birdhouse: http://birdhouse.readthedocs.io/en/latest/
.. _Pyramid: http://www.pylonsproject.org
.. _PAVICS: https://ouranosinc.github.io/pavics-sdi/index.html
