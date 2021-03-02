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
    :widths: 20,80

    * - dependencies
      - | |py_ver| |requires| |pyup|
    * - build status
      - | |readthedocs| |docker_build_mode| |docker_build_status|
    * - tests status
      - | |github_latest| |github_tagged| |coverage| |codacy|
    * - releases
      - | |version| |commits-since| |license|

.. |py_ver| image:: https://img.shields.io/badge/python-3.6%2B-blue.svg
    :alt: Requires Python 3.6+
    :target: https://www.python.org/getit

.. |commits-since| image:: https://img.shields.io/github/commits-since/crim-ca/weaver/2.1.0.svg
    :alt: Commits since latest release
    :target: https://github.com/crim-ca/weaver/compare/2.1.0...master

.. |version| image:: https://img.shields.io/badge/latest%20version-2.1.0-blue
    :alt: Latest Tagged Version
    :target: https://github.com/crim-ca/weaver/tree/2.1.0

.. |requires| image:: https://requires.io/github/crim-ca/weaver/requirements.svg?branch=master
    :alt: Requirements Status
    :target: https://requires.io/github/crim-ca/weaver/requirements/?branch=master

.. |pyup| image:: https://pyup.io/repos/github/crim-ca/weaver/shield.svg
    :alt: Dependencies Status
    :target: https://pyup.io/account/repos/github/crim-ca/weaver/

.. |github_latest| image:: https://img.shields.io/github/workflow/status/crim-ca/weaver/Tests/master?label=master
    :alt: Github Actions CI Build Status (master branch)
    :target: https://github.com/crim-ca/weaver/actions?query=workflow%3ATests+branch%3Amaster

.. |github_tagged| image:: https://img.shields.io/github/workflow/status/crim-ca/weaver/Tests/2.1.0?label=2.1.0
    :alt: Github Actions CI Build Status (latest tag)
    :target: https://github.com/crim-ca/weaver/actions?query=workflow%3ATests+branch%3A2.1.0

.. |readthedocs| image:: https://img.shields.io/readthedocs/pavics-weaver
    :alt: ReadTheDocs Build Status (master branch)
    :target: `ReadTheDocs`_

.. |docker_build_mode| image:: https://img.shields.io/docker/automated/pavics/weaver.svg?label=build
    :alt: Docker Build Mode (latest version)
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. below shield will either indicate the targeted version or 'tag not found'
.. since docker tags are pushed following manual builds by CI, they are not automatic and no build artifact exists
.. |docker_build_status| image:: https://img.shields.io/docker/v/pavics/weaver/2.1.0?label=tag%20status
    :alt: Docker Build Status (latest version)
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. |coverage| image:: https://img.shields.io/codecov/c/gh/crim-ca/weaver.svg?label=coverage
    :alt: Code Coverage
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

`Weaver` is primarily an *Execution Management Service (EMS)* that allows the execution of workflows chaining various
applications and *Web Processing Services (WPS)* inputs and outputs. Remote execution of each process in a workflow
chain is dispatched by the *EMS* to one or many registered *Application Deployment and Execution Service (ADES)* by
ensuring the transfer of files accordingly between instances when located across multiple remote locations.

`Weaver` can also accomplish the *ADES* role in order to perform application deployment at the data source using
the application definition provided by *Common Workflow Language* (`CWL`_) configuration. It can then directly execute
a registered process execution with received inputs from a WPS request to expose output results for a following *ADES*
in a *EMS* workflow execution chain.

`Weaver` **extends** the |ogc-proc-api|_ by providing additional functionalities such as more detailed job log routes,
adding more process management request options than required by the standard, and supporting *remote providers* to name
a few. Because of this, not all features offered in `Weaver` are guaranteed to be applicable on other similarly
behaving `ADES` and/or `EMS` instances. The reference specification is tracked to preserve the minimal conformance
requirements and provide feedback to |ogc|_ (OGC) in this effect.

Weaver can be launched either as an `EMS` or an `ADES` according to configuration values it is deployed with.
For more details, see `Configuration`_ and `Documentation`_ sections.

.. |ogc| replace:: Open Geospatial Consortium
.. _ogc: https://www.ogc.org/
.. |ogc-proc-api| replace:: `OGC API - Processes` (WPS-REST bindings)
.. _ogc-proc-api: https://github.com/opengeospatial/wps-rest-binding

----------------
Links
----------------

Docker image repositories:

- CRIM registry: `ogc/weaver <https://docker-registry.crim.ca/repositories/3463>`_
- OGC processes: `ogc-public <https://docker-registry.crim.ca/namespaces/39>`_
- DockerHub: `pavics/weaver <https://hub.docker.com/r/pavics/weaver>`_

::

    $ docker pull pavics/weaver:2.1.0

For convenience, following tags are also available:

- ``weaver:2.1.0-manager``: `Weaver` image that will run the API for WPS process and job management.
- ``weaver:2.1.0-worker``: `Weaver` image that will run the process job runner application.

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

The REST API documentation is auto-generated and served under any running `Weaver` application on route
``{WEAVER_URL}/api/``. This documentation will correspond to the version of the executed `Weaver` application.
For the latest documentation, you can refer to the `OpenAPI Specification`_ served directly on `ReadTheDocs`_.

More ample details about installation, configuration and usage are also provided on `ReadTheDocs`_.
These are generated from corresponding information provided in `docs`_ source directory.

.. _ReadTheDocs: https://pavics-weaver.readthedocs.io
.. _`OpenAPI Specification`: https://pavics-weaver.readthedocs.io/en/latest/api.html
.. _docs: ./docs

-------------------------
Extra Details & Sponsors
-------------------------

The project was initially developed upon *OGC Testbed-14 – ESA Sponsored Threads – Exploitation Platform* findings and
following improvements. It is also advanced with sponsorship of *U.S. Department of Energy* to support common
API of the *Earth System Grid Federation* (`ESGF`_). The findings are reported on the |ogc-tb14|_ thread, and more
explicitly in the |ogc-tb14-platform-er|_.

The project has been employed for |ogc-tb15-ml|_ to demonstrate the use of Machine Learning interactions with OGC web
standards in the context of natural resources applications. The advancements are reported through the |ogc-tb15-ml-er|_.

Developments are continued in |ogc-tb16|_ to improve methodologies in order to provide better
interoperable geospatial data processing in the areas of Earth Observation Application Packages.

The project is furthermore developed through the *Data Analytics for Canadian Climate Services* (`DACCS`_) initiative.

Weaver is a **prototype** implemented in Python with the `Pyramid`_ web framework.
It is part of `PAVICS`_ and `Birdhouse`_ ecosystems.

.. NOTE: all references in this file must remain local (instead of imported from 'references.rst')
..       to allow Github to directly referring to them from the repository HTML page.
.. |ogc-tb14| replace:: OGC Testbed-14
.. _ogc-tb14: https://www.ogc.org/projects/initiatives/testbed14
.. |ogc-tb14-platform-er| replace:: ADES & EMS Results and Best Practices Engineering Report
.. _ogc-tb14-platform-er: http://docs.opengeospatial.org/per/18-050r1.html
.. |ogc-tb15-ml| replace:: OGC Testbed-15 - ML Thread
.. _ogc-tb15-ml: https://www.ogc.org/projects/initiatives/testbed15#MachineLearning
.. |ogc-tb15-ml-er| replace:: OGC Testbed-15: Machine Learning Engineering Report
.. _ogc-tb15-ml-er: http://docs.opengeospatial.org/per/19-027r2.html
.. |ogc-tb16| replace:: OGC Testbed-16
.. _ogc-tb16: https://www.ogc.org/projects/initiatives/t-16
.. _PAVICS: https://ouranosinc.github.io/pavics-sdi/index.html
.. _Birdhouse: http://bird-house.github.io/
.. _ESGF: https://esgf.llnl.gov/
.. _DACCS: https://app.dimensions.ai/details/grant/grant.8105745
.. _Pyramid: http://www.pylonsproject.org
.. _CWL: https://www.commonwl.org/
