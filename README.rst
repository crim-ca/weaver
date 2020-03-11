=============================================
Weaver
=============================================

* Workflow Execution Management Service (EMS)
* Application, Deployment and Execution Service (ADES)

Weaver (the nest-builder)
  *Weaver birds build exquisite and elaborate nest structures that are a rival to any human feat of engineering.
  Some of these nests are the largest structures to be built by birds.*
  (`Eden <https://eden.uktv.co.uk/animals/birds/article/weaver-birds/>`_).

  *Although weavers are named for their elaborately woven nests, some are notable for their selective parasitic
  nesting habits instead.*
  (`Wikipedia <https://en.wikipedia.org/wiki/Ploceidae>`_)

`Weaver` is an `Execution Management Service (EMS)` that allows the execution of workflows chaining various
applications and `Web Processing Services (WPS)` inputs and outputs. Remote execution is deferred by the `EMS` to an
`Application Deployment and Execution Service (ADES)`, as defined by `Common Workflow Language` (`CWL`_) configurations.

`Weaver` can be launched either as an `EMS` or an `ADES` according to configuration values it is deployed with.
For more details, see `Configuration`_ section.


.. start-badges

.. list-table::
    :stub-columns: 1

    * - dependencies
      - | |py_ver| |requires|
    * - build status
      - | |travis_latest| |travis_tagged| |readthedocs| |coverage| |codacy|
    * - releases
      - | |version| |commits-since| |license|

.. |py_ver| image:: https://img.shields.io/badge/python-2.7%2C%203.5%2B-blue.svg
    :alt: Requires Python 2.7, 3.5+
    :target: https://www.python.org/getit

.. |commits-since| image:: https://img.shields.io/github/commits-since/crim-ca/weaver/1.3.0.svg
    :alt: Commits since latest release
    :target: https://github.com/crim-ca/weaver/compare/1.3.0...master

.. |version| image:: https://img.shields.io/github/tag/crim-ca/weaver.svg?style=flat
    :alt: Latest Tag
    :target: https://github.com/crim-ca/weaver/tree/1.3.0

.. |requires| image:: https://requires.io/github/crim-ca/weaver/requirements.svg?branch=master
    :alt: Requirements Status
    :target: https://requires.io/github/crim-ca/weaver/requirements/?branch=master

.. |travis_latest| image:: https://img.shields.io/travis/com/crim-ca/weaver/master.svg?label=master
    :alt: Travis-CI Build Status (master branch)
    :target: https://travis-ci.com/crim-ca/weaver

.. |travis_tagged| image:: https://img.shields.io/travis/com/crim-ca/weaver/1.3.0.svg?label=1.3.0
    :alt: Travis-CI Build Status (latest tag)
    :target: https://github.com/crim-ca/weaver/tree/1.3.0

.. |readthedocs| image:: https://img.shields.io/readthedocs/pavics-weaver
    :alt: Readthedocs Build Status (master branch)
    :target: `readthedocs`_

.. |coverage| image:: https://img.shields.io/codecov/c/gh/crim-ca/weaver.svg?label=coverage
    :alt: Travis-CI CodeCov Coverage
    :target: https://codecov.io/gh/crim-ca/weaver

.. |codacy| image:: https://api.codacy.com/project/badge/Grade/4f29419c9c91458ea3f0aa6aff11692c
    :alt: Codacy Badge
    :target: https://app.codacy.com/app/fmigneault/weaver?utm_source=github.com&utm_medium=referral&utm_content=crim-ca/weaver&utm_campaign=Badge_Grade_Dashboard

.. |license| image:: https://img.shields.io/github/license/crim-ca/weaver.svg
    :target: https://github.com/crim-ca/weaver/blob/master/LICENSE.txt
    :alt: GitHub License

.. end-badges

----------------
Summary
----------------

Weaver is primarily an *Execution Management Service (EMS)* that allows the execution of workflows chaining various
applications and *Web Processing Services (WPS)* inputs and outputs. Remote execution of each process in a workflow
chain is dispatched by the *EMS* to one or many registered *Application Deployment and Execution Service (ADES)* by
ensuring the transfer of files accordingly between instances when located across multiple remote locations.

Weaver can also accomplish the *ADES* role in order to perform application deployment at the data source using
the application definition provided by *Common Workflow Language* (`CWL`_) configuration. It can then directly execute
a registered process execution with received inputs from a WPS request to expose output results for a following *ADES*
in a *EMS* workflow execution chain.

Weaver can be launched either as an *EMS* or an *ADES* according to configuration values it is deployed with.
For more details, see `Configuration`_ and `Documentation`_ sections.

----------------
Links
----------------

Docker image repositories: 

- CRIM registry: `ogc/weaver <https://docker-registry.crim.ca/repositories/3463>`_
- OGC processes: `ogc-public <https://docker-registry.crim.ca/namespaces/39>`_
- DockerHub: `pavics/weaver <https://hub.docker.com/r/pavics/weaver>`_

::

    $ docker pull pavics/weaver:1.3.0

For convenience, following tags are also available:

- ``weaver:1.3.0-manager``: `Weaver` image that will run the API for WPS process and job management.
- ``weaver:1.3.0-worker``: `Weaver` image that will run the process job runner application.

Following links correspond to existing servers with `Weaver` configured as *EMS*/*ADES* instances respectively.

- ADES Test server: https://ogc-ades.crim.ca/weaver/
- EMS Test server: https://ogc-ems.crim.ca/weaver/
- EMS Extra server: https://ogc.crim.ca/ems/

.. note::
    The test servers will **not** necessarily be up-to-date with the *latest* version.
    Request the ``${server}/weaver/versions`` route to verify the running version.

----------------
Configuration
----------------

All configuration settings can be overridden using a ``weaver.ini`` file that will be picked during
instantiation of the application. An example of such file is provided here: `weaver.ini.example`_.

Setting Weaver's operational mode (*EMS*/*ADES*) is accomplished using the
``weaver.configuration`` field of ``weaver.ini``.

For more configuration details, please refer to Documentation_.

.. _weaver.ini.example: ./config/weaver.ini.example

----------------
Documentation
----------------

The REST API documentation is auto-generated and served under ``{WEAVER_URL}/api/`` using
Swagger-UI with tag ``latest``.

More ample details about installation, configuration and usage are provided on `readthedocs`_.
These are generated from corresponding information provided in `docs`_.

.. _readthedocs: https://pavics-weaver.readthedocs.io
.. _docs: ./docs

----------------
Extra Details
----------------

The project is developed upon *OGC Testbed-14 – ESA Sponsored Threads – Exploitation Platform* findings and
following improvements. It is also advanced with sponsorship of *U.S. Department of Energy* to support common
API of the *Earth System Grid Federation* (`ESGF`_).

The project is furthermore developed through the *Data Analytics for Canadian Climate Services* (`DACCS`_) initiative.

Weaver is a **prototype** implemented in Python with the `Pyramid`_ web framework.
It is part of `PAVICS`_ and `Birdhouse`_ ecosystems.

.. _PAVICS: https://ouranosinc.github.io/pavics-sdi/index.html
.. _Birdhouse: http://bird-house.github.io/
.. _ESGF: https://esgf.llnl.gov/
.. _DACCS: https://app.dimensions.ai/details/grant/grant.8105745
.. _Pyramid: http://www.pylonsproject.org
.. _CWL: https://www.commonwl.org/
