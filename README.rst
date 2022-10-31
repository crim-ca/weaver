=============================================
Weaver
=============================================

**Implementations**

* |ogc-proc-long|
* |ems| for Workflows
* |ades|

Weaver (the nest-builder)
  *Weaver birds build exquisite and elaborate nest structures that are a rival to any human feat of engineering.
  Some of these nests are the largest structures to be built by birds.*
  (`Eden <https://eden.uktv.co.uk/animals/birds/article/weaver-birds/>`_).

  *Although weavers are named for their elaborately woven nests, some are notable for their selective parasitic
  nesting habits instead.*
  (`Wikipedia <https://en.wikipedia.org/wiki/Ploceidae>`_)

`Weaver` is an OGC-API flavored |ems| that allows the execution of workflows chaining various
applications and |wps| inputs and outputs. Remote execution is deferred by the `EMS` to one or many
|ades| or remote service providers, and employs |cwl| configurations to define an |ogc-apppkg|_ deployed
for each process.


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

.. |commits-since| image:: https://img.shields.io/github/commits-since/crim-ca/weaver/4.26.0.svg
    :alt: Commits since latest release
    :target: https://github.com/crim-ca/weaver/compare/4.26.0...master

.. |version| image:: https://img.shields.io/badge/latest%20version-4.26.0-blue
    :alt: Latest Tagged Version
    :target: https://github.com/crim-ca/weaver/tree/4.26.0

.. |requires| image:: https://requires.io/github/crim-ca/weaver/requirements.svg?branch=master
    :alt: Requirements Status
    :target: https://requires.io/github/crim-ca/weaver/requirements/?branch=master

.. |pyup| image:: https://pyup.io/repos/github/crim-ca/weaver/shield.svg
    :alt: Dependencies Status
    :target: https://pyup.io/account/repos/github/crim-ca/weaver/

.. |github_latest| image:: https://img.shields.io/github/workflow/status/crim-ca/weaver/Tests/master?label=master
    :alt: Github Actions CI Build Status (master branch)
    :target: https://github.com/crim-ca/weaver/actions?query=workflow%3ATests+branch%3Amaster

.. |github_tagged| image:: https://img.shields.io/github/workflow/status/crim-ca/weaver/Tests/4.26.0?label=4.26.0
    :alt: Github Actions CI Build Status (latest tag)
    :target: https://github.com/crim-ca/weaver/actions?query=workflow%3ATests+branch%3A4.26.0

.. |readthedocs| image:: https://img.shields.io/readthedocs/pavics-weaver
    :alt: ReadTheDocs Build Status (master branch)
    :target: `ReadTheDocs`_

.. |docker_build_mode| image:: https://img.shields.io/docker/automated/pavics/weaver.svg?label=build
    :alt: Docker Build Mode (latest version)
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. below shield will either indicate the targeted version or 'tag not found'
.. since docker tags are pushed following manual builds by CI, they are not automatic and no build artifact exists
.. |docker_build_status| image:: https://img.shields.io/docker/v/pavics/weaver/4.26.0?label=tag%20status
    :alt: Docker Build Status (latest version)
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. |coverage| image:: https://img.shields.io/codecov/c/gh/crim-ca/weaver.svg?label=coverage
    :alt: Code Coverage
    :target: https://codecov.io/gh/crim-ca/weaver

.. |codacy| image:: https://app.codacy.com/project/badge/Grade/2b340010b41b4401acc9618a437a43b8
    :alt: Codacy Badge
    :target: https://app.codacy.com/gh/crim-ca/weaver/dashboard

.. |license| image:: https://img.shields.io/github/license/crim-ca/weaver.svg
    :target: https://github.com/crim-ca/weaver/blob/master/LICENSE.txt
    :alt: GitHub License

.. end-badges

----------------
Summary
----------------

`Weaver` is primarily an |ems| that allows the execution of workflows chaining various
applications and |wps| inputs and outputs. Remote execution of each process in a workflow
chain is dispatched by the *EMS* to one or many registered |ades| by
ensuring the transfer of files accordingly between instances when located across multiple remote locations.

`Weaver` can also accomplish the `ADES` role in order to perform application deployment at the data source using
the application definition provided by |cwl| configuration. It can then directly execute
a registered process |ogc-apppkg|_ with received inputs from a WPS request to expose output results for a
following `ADES` in a `EMS` workflow execution chain.

`Weaver` **extends** |ogc-proc-api|_ by providing additional functionalities such as more detailed job logs
endpoints, adding more process management and search request options than required by the standard, and supporting
*remote providers* registration for dynamic process definitions, to name a few.
Because of this, not all features offered in `Weaver` are guaranteed to be applicable on other similarly
behaving `ADES` and/or `EMS` instances. The reference specification is tracked to preserve the minimal conformance
requirements and provide feedback to |ogc|_ (OGC) in this effect.

`Weaver` can be launched either as an `EMS`, an `ADES` or an `HYBRID` of both according to its configuration.
For more details, see `Configuration`_ and `Documentation`_ sections.

----------------
Features Preview
----------------

Following videos present some of the features and potential capabilities of servicing and executing processes
offered by |ades| and |ems| instances like `Weaver`.

**Keywords**:
Big Data, software architecture, Earth Observation, satellite data, processing, climate change, machine learning,
climate services.

Applications
~~~~~~~~~~~~~~~~

The video shares the fundamental ideas behind the architecture, illustrates how application stores for Earth
Observation data processing can evolve, and illustrates the advantages with applications based on machine learning.

.. Tag iframe renders the embedded video in ReadTheDocs/Sphinx generated build,
   but it is filtered out by GitHub (https://github.github.com/gfm/#disallowed-raw-html-extension-).
   The following div displays instead video thumbnail with an external link only for GitHub.
   When iframe properly renders, the image/link div is masked under it to avoid seeing two "video displays".
.. raw:: html

    <div style="position: relative; padding-bottom: 21.5%; height: 0; overflow: hidden; height: auto; max-width: 50em;"
    >
        <iframe src="https://www.youtube.com/embed/no3REyoxE38" frameborder="0" allowfullscreen
                alt="Watch the Application video: http://www.youtube.com/watch?v=v=no3REyoxE3"
                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">

        </iframe>
        <div style="max-width: 50em;"> <!-- alternate view for GitHub -->
            <b>Watch the Application video on YouTube</b>
            <br>
            <a href="https://www.youtube.com/watch?v=no3REyoxE38">
                <img src="https://img.youtube.com/vi/no3REyoxE38/mqdefault.jpg"
                     alt="Watch the Application video: http://www.youtube.com/watch?v=v=no3REyoxE3"
                />
            </a>
        </div>
    </div>
    <br>

Platform
~~~~~~~~~~~~~~~~

The video shares the fundamental ideas behind the architecture, illustrates how platform managers can benefit from
application stores, and shows the potential for multidisciplinary workflows in thematic platforms.

.. see other video comment
.. raw:: html

    <div style="position: relative; padding-bottom: 21.5%; height: 0; overflow: hidden; height: auto; max-width: 50em;"
    >
        <iframe src="https://www.youtube.com/embed/QkdDFGEfIAY" frameborder="0" allowfullscreen
                alt="Watch the Platform video: http://www.youtube.com/watch?v=v=QkdDFGEfIAY"
                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
        </iframe>
        <div style="max-width: 50em;"> <!-- alternate view for GitHub -->
            <b>Watch the Platform video on YouTube</b>
            <br>
            <a href="https://www.youtube.com/watch?v=QkdDFGEfIAY">
                <img src="https://img.youtube.com/vi/QkdDFGEfIAY/mqdefault.jpg"
                     alt="Watch the Platform video: http://www.youtube.com/watch?v=v=QkdDFGEfIAY"
                />
            </a>
        </div>
    </div>
    <br>

----------------
Links
----------------

Docker image repositories:

- CRIM registry: `ogc/weaver <https://docker-registry.crim.ca/repositories/3463>`_
- OGC processes: `ogc-public <https://docker-registry.crim.ca/namespaces/39>`_
- DockerHub: `pavics/weaver <https://hub.docker.com/r/pavics/weaver>`_

::

    $ docker pull pavics/weaver:4.26.0

For convenience, following tags are also available:

- ``weaver:4.26.0-manager``: `Weaver` image that will run the API for WPS process and job management.
- ``weaver:4.26.0-worker``: `Weaver` image that will run the process job runner application.

Following links correspond to existing servers with `Weaver` configured as *EMS*/*ADES* instances respectively.

- HYBRID Server: https://service.crim.ca/
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

Setting the operational mode of `Weaver` (`EMS`/`ADES`/`HYBRID`) is accomplished using the
``weaver.configuration`` field of ``weaver.ini``. For more configuration details, please refer to Documentation_.

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

The project was initially developed upon `OGC Testbed-14 – ESA Sponsored Threads – Exploitation Platform` findings and
following improvements. It is also advanced with sponsorship from the `U.S. Department of Energy` to support common
API of the |esgf|. The findings are reported on the |ogc-tb14|_ thread, and more
explicitly in the |ogc-tb14-platform-er|_.

The project has been employed for |ogc-tb15-ml|_ to demonstrate the use of Machine Learning interactions with OGC web
standards in the context of natural resources applications. The advancements are reported through the |ogc-tb15-ml-er|_.

Developments are continued in |ogc-tb16|_ to improve methodologies in order to provide better
interoperable geospatial data processing in the areas of Earth Observation Application Packages.

Videos and more functionalities were introduced in `Weaver` following |ogc-eo-apps-pilot|_.
Corresponding developments are reported in the |ogc-eo-apps-pilot-er|_.

`Weaver` has been used to participate in interoperability testing effort that lead to |ogc-best-practices-eo-apppkg|_
technical report. This resulted, along with previous efforts, in the definition of |ogc-api-proc-part2| backed by
validated test cases using |cwl| as the representation method for the deployment and execution of |ogc-apppkg|_ close
to the data.

The project is furthermore developed through the *Data Analytics for Canadian Climate Services* (`DACCS`_) initiative.

`Weaver` is implemented in Python with the `Pyramid`_ web framework.
It is part of `PAVICS`_ and `Birdhouse`_ ecosystems and is available within the `birdhouse-deploy`_ server stack.

.. NOTE: all references in this file must remain local (instead of imported from 'references.rst')
..       to allow Github to directly referring to them from the repository HTML page.
.. |cwl| replace:: `Common Workflow Language`_ (CWL)
.. _`Common Workflow Language`: https://www.commonwl.org/
.. |esgf| replace:: `Earth System Grid Federation`_ (ESGF)
.. _`Earth System Grid Federation`: https://esgf.llnl.gov/
.. |ems| replace:: `Execution Management Service` (EMS)
.. |ades| replace:: `Application, Deployment and Execution Service` (ADES)
.. |wps| replace:: `Web Processing Services` (WPS)
.. |ogc| replace:: Open Geospatial Consortium
.. _ogc: https://www.ogc.org/
.. |ogc-proc-api| replace:: `OGC API - Processes`
.. _ogc-proc-api: https://github.com/opengeospatial/ogcapi-processes
.. |ogc-proc-long| replace:: |ogc-proc-api|_ (WPS-REST bindings)
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
.. |ogc-eo-apps-pilot| replace:: OGC Earth Observation Applications Pilot
.. _ogc-eo-apps-pilot: https://www.ogc.org/eoapps
.. |ogc-eo-apps-pilot-er| replace:: OGC Earth Observation Applications Pilot: CRIM Engineering Report
.. _ogc-eo-apps-pilot-er: http://docs.opengeospatial.org/per/20-045.html
.. |ogc-best-practices-eo-apppkg| replace:: OGC Best Practice for Earth Observation Application Package
.. _ogc-best-practices-eo-apppkg: https://docs.ogc.org/bp/20-089r1.html
.. |ogc-api-proc-part2| replace:: `OGC API - Processes - Part 2: Deploy, Replace, Undeploy`_ (DRU) extension
.. _`OGC API - Processes - Part 2: Deploy, Replace, Undeploy`: https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/deploy_replace_undeploy
.. |ogc-apppkg| replace:: `OGC Application Package`
.. _ogc-apppkg: https://github.com/opengeospatial/ogcapi-processes/blob/master/extensions/deploy_replace_undeploy/standard/openapi/schemas/ogcapppkg.yaml
.. _PAVICS: https://ouranosinc.github.io/pavics-sdi/index.html
.. _Birdhouse: http://bird-house.github.io/
.. _birdhouse-deploy: https://github.com/bird-house/birdhouse-deploy
.. _DACCS: https://app.dimensions.ai/details/grant/grant.8105745
.. _Pyramid: http://www.pylonsproject.org
