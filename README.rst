=============================================
Weaver: workflow execution management service
=============================================

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

.. start-badges

.. list-table::
    :stub-columns: 1

    * - dependencies
      - | |py_ver| |requires|
    * - build status
      - | |travis_latest| |travis_tag| |coverage|
    * - releases
      - | |version| |commits-since| |license|

.. |py_ver| image:: https://img.shields.io/badge/python-2.7%2C%203.5%2B-blue.svg
    :alt: Requires Python 2.7, 3.5+
    :target: https://www.python.org/getit

.. |commits-since| image:: https://img.shields.io/github/commits-since/crim-ca/weaver/0.1.3.svg
    :alt: Commits since latest release
    :target: https://github.com/crim-ca/weaver/compare/0.1.3...master

.. |version| image:: https://img.shields.io/github/tag/crim-ca/weaver.svg?style=flat
    :alt: Latest Tag
    :target: https://github.com/crim-ca/weaver/tree/0.1.3

.. |requires| image:: https://requires.io/github/crim-ca/weaver/requirements.svg?branch=master
    :alt: Requirements Status
    :target: https://requires.io/github/crim-ca/weaver/requirements/?branch=master

.. |travis_latest| image:: https://img.shields.io/travis/com/crim-ca/weaver/master.svg?label=master
    :alt: Travis-CI Build Status (master branch)
    :target: https://travis-ci.com/crim-ca/weaver

.. |travis_tag| image:: https://img.shields.io/travis/com/crim-ca/weaver/0.1.3.svg?label=0.1.3
    :alt: Travis-CI Build Status (latest tag)
    :target: https://github.com/crim-ca/weaver/tree/0.1.3

.. |coverage| image:: https://img.shields.io/codecov/c/gh/crim-ca/weaver.svg?label=coverage
    :alt: Travis-CI CodeCov Coverage
    :target: https://codecov.io/gh/crim-ca/weaver

.. |license| image:: https://img.shields.io/github/license/crim-ca/weaver.svg
   :target: https://github.com/crim-ca/weaver/blob/master/LICENSE.txt
   :alt: GitHub license

.. end-badges

----------------
Links
----------------

Docker image `repository <https://docker-registry.crim.ca/repositories/3463>`_.

::

    $ docker pull docker-registry.crim.ca/ogc/weaver:0.1.3

Test server: https://ogc-ems.crim.ca/weaver/

----------------
Extra Details
----------------

The project is developed and based of `OGC Testbed-14 – ESA Sponsored Threads – Exploitation Platform` findings and
following improvements.

`Weaver` is a **prototype** implemented in Python with the `Pyramid`_ web framework.

.. _Pyramid: http://www.pylonsproject.org
.. _PAVICS: https://ouranosinc.github.io/pavics-sdi/index.html


.. image:: https://api.codacy.com/project/badge/Grade/4f29419c9c91458ea3f0aa6aff11692c
   :alt: Codacy Badge
   :target: https://app.codacy.com/app/fmigneault/weaver?utm_source=github.com&utm_medium=referral&utm_content=crim-ca/weaver&utm_campaign=Badge_Grade_Dashboard