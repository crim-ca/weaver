=============================================
Weaver
=============================================

\| `Summary`_
\| `Features`_
\| `Links`_
\| `Installation`_
\| `Configuration`_
\| `Documentation`_
\| `Agent Skills`_
\| `Extra Details & Sponsors`_
\|

**Implementations**

* |ogc-api-proc-long|
    - |ogc-api-proc-part1-v1|_
    - |ogc-api-proc-part1-v2|_
    - |ogc-api-proc-part2|_
    - |ogc-api-proc-part3|_
    - |ogc-api-proc-part4|_ (including Provenance)
* |wps-long|
* |esgf| processes
* |cwl-long| for |ogc-apppkg|_
* |w3c-prov|_ for provenance metadata tracking through |ogc-api-proc| and |cwl|
* |jupyter-nb-app|_ deployment as |ogc-apppkg|_
* |ems-long| for dispatching distributed workflow processing
* |ades-long| for processing close to the data

Weaver (the nest-builder)
  *Weaver birds build exquisite and elaborate nest structures that are a rival to any human feat of engineering.
  Some of these nests are the largest structures to be built by birds.*
  [`Eden <http://web.archive.org/web/20240416100924/https://eden.uktv.co.uk/animals/birds/article/weaver-birds/>`_].

  *Although weavers are named for their elaborately woven nests, some are notable for their selective parasitic
  nesting habits instead.*
  [`Wikipedia <https://en.wikipedia.org/wiki/Ploceidae>`_]

`Weaver` is an OGC-API flavored |ems| that allows the execution of workflows chaining various
applications and |wps| inputs and outputs. Remote execution is deferred by the `EMS` to one or many
|ades| or remote service providers, and employs |cwl-long| configurations to define an |ogc-apppkg|_ deployed
for each process.


.. start-badges

.. list-table::
    :stub-columns: 1
    :widths: 20,80

    * - dependencies
      - | |py_ver| |deps| |pyup|
    * - license
      - | |license| |license_scan|
    * - citation
      - | |citation-zenodo| |citation-cff|
    * - build status
      - | |readthedocs_build_status| |docker_build_mode| |docker_build_status|
    * - tests status
      - | |github_latest| |github_tagged| |coverage| |codacy|
    * - releases
      - | |version| |commits-since| |docker_image|

.. |py_ver| image:: https://img.shields.io/badge/python-3.10%2B-blue.svg?logo=python
    :alt: Requires Python 3.10+
    :target: https://www.python.org/getit

.. |commits-since| image:: https://img.shields.io/github/commits-since/crim-ca/weaver/6.8.3.svg?logo=github
    :alt: Commits since latest release
    :target: https://github.com/crim-ca/weaver/compare/6.8.3...master

.. |version| image:: https://img.shields.io/badge/latest%20version-6.8.3-blue?logo=github
    :alt: Latest Tagged Version
    :target: https://github.com/crim-ca/weaver/tree/6.8.3

.. |deps| image:: https://img.shields.io/librariesio/github/crim-ca/weaver?logo=librariesdotio&logoColor=white
    :alt: Libraries.io Dependencies Status
    :target: https://libraries.io/github/crim-ca/weaver

.. |pyup| image:: https://pyup.io/repos/github/crim-ca/weaver/shield.svg?logo=pyup
    :alt: PyUp Dependencies Status
    :target: https://pyup.io/account/repos/github/crim-ca/weaver/

.. |github_latest| image:: https://img.shields.io/github/actions/workflow/status/crim-ca/weaver/tests.yml?label=master&branch=master&logo=github
    :alt: Github Actions CI Build Status (master branch)
    :target: https://github.com/crim-ca/weaver/actions?query=workflow%3ATests+branch%3Amaster

.. |github_tagged| image:: https://img.shields.io/github/actions/workflow/status/crim-ca/weaver/tests.yml?label=6.8.3&branch=6.8.3&logo=github
    :alt: Github Actions CI Build Status (latest tag)
    :target: https://github.com/crim-ca/weaver/actions?query=workflow%3ATests+branch%3A6.8.3

.. |readthedocs_build_status| image:: https://img.shields.io/readthedocs/pavics-weaver?logo=readthedocs
    :alt: ReadTheDocs Build Status (master branch)
    :target: `ReadTheDocs`_

.. |docker_build_mode| image:: https://img.shields.io/docker/automated/pavics/weaver.svg?label=build&logo=docker
    :alt: Docker Build Mode (latest version)
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. below shield will either indicate the targeted version or 'tag not found'
.. since docker tags are pushed following manual builds by CI, they are not automatic and no build artifact exists
.. |docker_build_status| image:: https://img.shields.io/docker/v/pavics/weaver/6.8.3?label=tag&logo=docker
    :alt: Docker Build Status (latest version)
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. |docker_image| image:: https://img.shields.io/badge/docker-pavics%2Fweaver-blue?logo=docker
    :alt: Docker Image
    :target: https://hub.docker.com/r/pavics/weaver/tags

.. |coverage| image:: https://img.shields.io/codecov/c/gh/crim-ca/weaver.svg?label=coverage&logo=codecov
    :alt: Code Coverage
    :target: https://codecov.io/gh/crim-ca/weaver

.. |codacy| image:: https://app.codacy.com/project/badge/Grade/2b340010b41b4401acc9618a437a43b8
    :alt: Codacy Badge
    :target: https://app.codacy.com/gh/crim-ca/weaver/dashboard

.. |license| image:: https://img.shields.io/github/license/crim-ca/weaver.svg#
    :target: https://github.com/crim-ca/weaver/blob/master/LICENSE.txt
    :alt: GitHub License

.. |license_scan| image:: https://app.fossa.com/api/projects/git%2Bgithub.com%2Fcrim-ca%2Fweaver.svg?type=shield&issueType=license
    :target: https://app.fossa.com/projects/git%2Bgithub.com%2Fcrim-ca%2Fweaver?ref=badge_shield&issueType=license
    :alt: FOSSA Status

.. |citation-zenodo| image:: https://zenodo.org/badge/DOI/10.5281/zenodo.14210717.svg#
    :alt: Zenodo DOI
    :target: https://zenodo.org/doi/10.5281/zenodo.14210717

.. |citation-cff| image:: https://img.shields.io/badge/citation-cff-blue
    :alt: CFF
    :target: https://github.com/crim-ca/weaver/blob/master/CITATION.cff

.. end-badges

----------------
Summary
----------------

`Weaver` is primarily an |ems| that allows the execution of workflows chaining various
applications and |wps| inputs and outputs. Remote execution of each process in a workflow
chain is dispatched by the *EMS* to one or many registered |ades| by
ensuring the transfer of files accordingly between instances when located across multiple remote locations.

`Weaver` can also accomplish the `ADES` role in order to perform application deployment at the data source using
the application definition provided by |cwl-long| configuration. It can then directly execute
a registered process |ogc-apppkg|_ with received inputs from a WPS request to expose output results for a
following `ADES` in a `EMS` workflow execution chain.

`Weaver` **extends** |ogc-api-proc|_ by providing additional functionalities such as more detailed job logs
endpoints, adding more process management and search request options than required by the standard, and supporting
*remote providers* registration for dynamic process definitions, to name a few.
Because of this, not all features offered in `Weaver` are guaranteed to be applicable on other similarly
behaving `ADES` and/or `EMS` instances. The reference specification is tracked to preserve the minimal conformance
requirements and provide feedback to |ogc-long|_ (OGC) in this effect.

`Weaver` can be launched either as an `EMS`, an `ADES` or an `HYBRID` of both according to its configuration.
For more details, see `Configuration`_ and `Documentation`_ sections.

----------------
Features
----------------

Following videos present some of the features and potential capabilities of servicing and executing processes
offered by |ades| and |ems| instances like `Weaver`.

.. list-table::
    :stub-columns: 1
    :widths: 20,80

    * - **Keywords**
      - |kw01| |kw02| |kw03| |kw04| |kw05| |kw06| |kw07| |kw08| |kw09| |kw10| |kw11| |kw12|

.. |kw01| image:: https://img.shields.io/badge/Software%20Architecture-blue
   :alt: Software Architecture
.. |kw02| image:: https://img.shields.io/badge/Cloud%20Computing-blue
   :alt: Cloud Computing
.. |kw03| image:: https://img.shields.io/badge/Earth%20Observation-blue
   :alt: Earth Observation
.. |kw04| image:: https://img.shields.io/badge/Big%20Data-blue
   :alt: Big Data
.. |kw05| image:: https://img.shields.io/badge/Satellite%20Data-blue
   :alt: Satellite Data
.. |kw06| image:: https://img.shields.io/badge/Data%20Processing-blue
   :alt: Data Processing
.. |kw07| image:: https://img.shields.io/badge/Workflow%20Processing-blue
   :alt: Workflow Processing
.. |kw08| image:: https://img.shields.io/badge/Climate%20Science-blue
   :alt: Climate Science
.. |kw09| image:: https://img.shields.io/badge/Climate%20Services-blue
   :alt: Climate Services
.. |kw10| image:: https://img.shields.io/badge/Application%20Package-blue
   :alt: Application Package
.. |kw11| image:: https://img.shields.io/badge/Machine%20Learning-blue
   :alt: Machine Learning
.. |kw12| image:: https://img.shields.io/badge/Open%20Science-blue
   :alt: Open Science

.. remove-pypi-start

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

.. note::
    See section `Extra Details & Sponsors`_ for further application examples and concrete demonstrations.

.. remove-pypi-end

.. remove-pypi-start

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

.. remove-pypi-end

----------------
Links
----------------

Docker image repositories:

.. list-table::
    :header-rows: 1

    * - Name
      - Reference
      - Access
    * - DockerHub
      - `pavics/weaver <https://hub.docker.com/r/pavics/weaver>`_
      - |public|
    * - CRIM registry
      - `ogc/weaver <https://docker-registry.crim.ca/repositories/3463>`_
      - |restricted|
    * - CRIM OGC Processes
      - `ogc-public <https://docker-registry.crim.ca/namespaces/39>`_
      - |restricted|

.. |public| image:: https://img.shields.io/badge/public-green
.. |restricted| image:: https://img.shields.io/badge/restricted-orange

For a prebuilt image, pull as follows:

.. code-block:: shell

    docker pull pavics/weaver:6.8.3

For convenience, following tags are also available:

- ``weaver:6.8.3-manager``: `Weaver` image that will run the API for WPS process and job management.
- ``weaver:6.8.3-worker``: `Weaver` image that will run the process job runner application.

Following links correspond to existing servers with `Weaver` configured as *EMS* or *ADES* instances respectively.

.. list-table::
    :widths: 15,35,10,50
    :header-rows: 1

    * - Institution & Partners
      - Project & Description
      - Version
      - Entrypoint
    * - `CRIM`_
      - `DACCS`_ / |ogc|_ - *Hirondelle* Development Instance
      - |crim-hirondelle-weaver-version|
      - `https://hirondelle.crim.ca/weaver <https://hirondelle.crim.ca/weaver>`_
    * - `CRIM`_
      - Demonstration Services Portal
      - |crim-services-weaver-version|
      - `https://services.crim.ca/weaver <https://services.crim.ca/weaver>`_
    * - `Ouranos`_
      - `PAVICS`_ Server
      - |ouranos-pavics-weaver-version|
      - `https://pavics.ouranos.ca/weaver/ <https://pavics.ouranos.ca/weaver/>`_
    * - |UofT|_
      - |marble|_ - `RedOak`_ Instance
      - |UofT-RedOak-weaver-version|
      - `https://redoak.cs.toronto.edu/weaver/ <https://redoak.cs.toronto.edu/weaver/>`_
    * - `CRIM`_, `ECCC`_, `CLIMAtlantic`_, `Ouranos`_, `PCIC`_, `PCC`_
      - `ClimateData.ca`_ / `DonneesClimatiques.ca`_ Portal
      - |climate-data-weaver-version|
      - `https://pavics.climatedata.ca/ <https://pavics.climatedata.ca/>`_

.. |crim-hirondelle-weaver-version| image:: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhirondelle.crim.ca%2Fweaver%2Fversions&query=%24.versions%5B0%5D.version&label=version
.. |crim-services-weaver-version| image:: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fservices.crim.ca%2Fweaver%2Fversions&query=%24.versions%5B0%5D.version&label=version
.. |ouranos-pavics-weaver-version| image:: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpavics.ouranos.ca%2Fweaver%2Fversions&query=%24.versions%5B0%5D.version&label=version
.. |UofT-RedOak-weaver-version| image:: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fredoak.cs.toronto.edu%2Fweaver%2Fversions&query=%24.versions[0].version&label=version
.. |climate-data-weaver-version| image:: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpavics.climatedata.ca%2Fversions&query=%24.versions[0].version&label=version

.. note::
    The test servers will **not** necessarily be up-to-date with the *latest* version.

----------------
Installation
----------------

Installation of `Weaver` from source can be performed instead of using the Docker containers.

.. code-block:: sh

    pip install https://github.com/crim.ca/weaver

.. using 'note' instead of 'seealso' because non-sphinx RST required by setup distribution
.. note::

    For more details, please refer to
    the `Installation <https://pavics-weaver.readthedocs.io/en/latest/installation.html>`_
    section of the documentation.

----------------
Configuration
----------------

All configuration settings can be overridden using a ``weaver.ini`` file that will be picked during
instantiation of the application. An example of such file is provided here: `weaver.ini.example`_.

Setting the operational mode of `Weaver` (`EMS`/`ADES`/`HYBRID`) is accomplished using the
``weaver.configuration`` field of ``weaver.ini``.

.. using 'note' instead of 'seealso' because non-sphinx RST required by setup distribution
.. note::

    For more details, please refer to
    the `Configuration <https://pavics-weaver.readthedocs.io/en/latest/configuration.html>`_
    section of the documentation.

.. _weaver.ini.example: ./config/weaver.ini.example

----------------
Documentation
----------------

The REST API documentation is auto-generated and served under any running `Weaver` application on route
``{WEAVER_URL}/api/``. This documentation will correspond to the version of the executed `Weaver` application.
For the latest documentation, you can refer to the `OpenAPI Specification`_ served directly on `ReadTheDocs`_.

For the |ogc-api-proc|_ compliant Python and Shell clients, please refer to
the `Weaver CLI and Client <https://pavics-weaver.readthedocs.io/en/latest/cli.html>`_ documentation.

More ample details about installation, configuration and usage are also provided on `ReadTheDocs`_.
These are generated from corresponding information provided in `docs`_ source directory.

.. _ReadTheDocs: https://pavics-weaver.readthedocs.io
.. _`OpenAPI Specification`: https://pavics-weaver.readthedocs.io/en/latest/api.html
.. _docs: ./docs

-------------------------
Agent Skills
-------------------------

Weaver provides **Agent Skills** (`.agents/skills/`_) - a standardized format following
the `Agent Skills Specification`_
for documenting capabilities that can be discovered and used by AI agents, IDEs, and automated systems.
See `.agents/README.md`_ for usage instructions and skill creation guidelines.

Each skill is self-contained with:

- **YAML frontmatter** describing metadata (name, description, compatibility)
- **Markdown documentation** with usage examples
- **Optional supporting files** (scripts, references, assets)

Each skill documents how to interact with Weaver:

- **REST API** endpoints (e.g., ``POST /processes/{id}/execution``)
- **CLI commands** (e.g., ``weaver execute -u $WEAVER_URL -p process-id``)
- **Python client** methods (e.g., ``WeaverClient.execute(process_id="...")``)

See also the configured `Context7 Documentation Updater for Weaver <https://context7.com/crim-ca/weaver>`_
that can be referenced for contextually-indexed documentation from the source code.

.. _.agents/skills/: ./.agents/skills/
.. _.agents/README.md: ./.agents/README.md
.. _Agent Skills Specification: https://agentskills.io/specification

-------------------------
Extra Details & Sponsors
-------------------------

The project was initially developed upon *OGC Testbed-14 – ESA Sponsored Threads – Exploitation Platform* findings and
improvements following from previous |ogc-tb13-cloud-er|_ architecture designs.
It was also built upon sponsorship from the *U.S. Department of Energy* to support common
API of the |esgf|. The findings are reported on the |ogc-tb14|_ thread, and more
explicitly in the |ogc-tb14-platform-er|_.

The project has been employed for |ogc-tb15-ml|_ to demonstrate the use of Machine Learning interactions with OGC web
standards in the context of natural resources applications. The advancements are reported through the |ogc-tb15-ml-er|_.
The combination of |cwl-long| with the |ogc-api-proc|_ standard in the context of Machine Learning and Geomatics
applications deployment was also presented at the |cwl-2021-conf|_ conference, with multiple example use case
demonstrating pretrained model inference for lake and river feature classification over satellite imagery,
land-cover mapping of raster imagery, and climate analysis leveraging preexisting |wps-long| servers.
The video recording of these demonstrations is available under the blog post |cwl-2021-video|_.

Developments are continued in |ogc-tb16|_ to improve methodologies in order to provide better
interoperable geospatial data processing in the areas of Earth Observation Application Packages.
Findings and recommendations are presented in the |ogc-tb16-data-access-proc-er|_.

Videos and more functionalities were introduced in `Weaver` following |ogc-eo-apps-pilot|_.
Corresponding developments are reported in the |ogc-eo-apps-pilot-er|_. See `Features`_ for demonstrations.

`Weaver` has been used to participate in interoperability testing effort that lead to |ogc-best-practices-eo-apppkg|_
technical report. This resulted, along with previous efforts, in the definition of |ogc-api-proc-part2|_ backed by
validated test cases using |cwl-long| as the representation method for the deployment and execution of |ogc-apppkg|_
close to the data.

`Weaver` is employed in the |ogc-ospd|_ initiative to demonstrate reusability, portability, and transparency
in the context of open science in Earth Observation, using |ogc-apppkg|_ encoded as |cwl|_ for interoperability
and distributed processing workflows. Its related developments and demonstrations were presented at
the |ogc-129th-mm|_ (2024, Montréal) and the |ESIP-2024|_ during the |ESIP-2024-panel|_.
Video recordings and related outcomes are available under the following links:

- **Report**: |ogc-ospd-er|_
- **Video**: |ogc-ospd-demo-video|_
- **Video**: |ogc-ospd-crim-video|_
- **Video**: ESIP presentation |ESIP-2024-presentation|_

`Weaver` is employed in |ogc-tb20-gdc|_ to improve and work on the integration of multiple
community standards involved in workflow design, such as |cwl|_, `openEO`_, |ogc-api-proc-part3|_
and |ogc-api-proc-part4|_, for processing of multidimensional data involved through *GeoDataCube* interactions.
Support of extended traceability and provenance metadata using |w3c-prov|_ over executed processing jobs has also
been implemented during this effort to provide data lineage and better integrity, provenance and trust (IPT)
of derived products resulting from processing workflows.
Outcomes were presented during the |ogc-tb20-demo-days|_ and the |ogc-131st-mm|_ events.
Corresponding reports are available online at the following locations:

- |ogc-tb20-gdc-api-file-report|_
- |ogc-tb20-gdc-prov-demo-report|_
- |ogc-tb20-gdc-usage-test-report|_

.. fixme: Add the OGC Testbed-20 report references when published (https://github.com/crim-ca/weaver/issues/812).

The project is furthermore developed through the |DACCS-long| (|DACCS-grant|_)
initiative and is employed by the `ClimateData.ca`_ / `DonneesClimatiques.ca`_ portal.

`Weaver` is implemented in Python with the `Pyramid`_ web framework.
It is part of `PAVICS`_ and `Birdhouse`_ ecosystems and is available within the `birdhouse-deploy`_ server stack.

.. NOTE: all references in this file must remain local (instead of imported from 'references.rst')
..       to allow Github to directly referring to them from the repository HTML page.
.. |cwl-long| replace:: `Common Workflow Language`_ (CWL)
.. _`Common Workflow Language`: https://www.commonwl.org/
.. |cwl| replace:: CWL
.. _cwl: https://www.commonwl.org/
.. |cwl-2021-conf| replace:: CWLcon 2021
.. _cwl-2021-conf: https://cwl.discourse.group/c/cwlcon-2021/
.. |cwl-2021-video| replace:: ML Processing Pipelines using CWL, Deployment in Context of Research Teams and OGC-API Integration
.. _cwl-2021-video: https://cwl.discourse.group/t/ml-processing-pipelines-using-cwl-deployment-in-context-of-research-teams-and-ogc-api-integration/269
.. _openEO: https://openeo.org/
.. |jupyter-nb-app| replace:: Jupyter Notebook Applications
.. _jupyter-nb-app: https://pavics-weaver.readthedocs.io/en/latest/package.html#jupyter-notebook-applications
.. |esgf| replace:: `Earth System Grid Federation`_ (ESGF)
.. _`Earth System Grid Federation`: https://esgf.llnl.gov/
.. |ems| replace:: Execution Management Service
.. _ems: https://docs.ogc.org/per/18-050r1.html#_crim
.. |ems-long| replace:: |ems|_ (EMS)
.. |ades| replace:: Application, Deployment and Execution Service
.. _ades: https://docs.ogc.org/per/18-050r1.html#_application_deployment_and_execution_service
.. |ades-long| replace:: |ades|_ (ADES)
.. |wps| replace:: `Web Processing Services`
.. _wps: https://www.ogc.org/standard/wps/
.. |wps-long| replace:: |wps|_ (WPS)
.. |ogc| replace:: OGC
.. _ogc: https://www.ogc.org/
.. |ogc-long| replace:: *Open Geospatial Consortium*
.. _ogc-long: https://www.ogc.org/
.. |ogc-api-proc| replace:: *OGC API - Processes*
.. _ogc-api-proc: https://github.com/opengeospatial/ogcapi-processes
.. |ogc-api-proc-long| replace:: |ogc-api-proc|_
.. |ogc-api-proc-part1-v1| replace:: *OGC API - Processes - Part 1: Core (v1.0)*
.. _ogc-api-proc-part1-v1: https://docs.ogc.org/is/18-062r2/18-062r2.html
.. |ogc-api-proc-part1-v2| replace:: *OGC API - Processes - Part 1: Core (v2.0)*
.. _ogc-api-proc-part1-v2: https://docs.ogc.org/DRAFTS/18-062r3.html
.. |ogc-api-proc-part2| replace:: *OGC API - Processes - Part 2: Deploy, Replace, Undeploy (DRU)*
.. _ogc-api-proc-part2: https://docs.ogc.org/DRAFTS/20-044.html
.. |ogc-api-proc-part3| replace:: *OGC API - Processes - Part 3: Workflows and Chaining*
.. _ogc-api-proc-part3: https://docs.ogc.org/DRAFTS/21-009.html
.. |ogc-api-proc-part4| replace:: *OGC API - Processes - Part 4: Job Management*
.. _ogc-api-proc-part4: https://docs.ogc.org/DRAFTS/24-051.html
.. |ogc-tb13-cloud-er| replace:: *OGC Testbed-13 - Cloud Engineering Report*
.. _ogc-tb13-cloud-er: https://docs.ogc.org/per/17-035.html
.. |ogc-tb14| replace:: *OGC Testbed-14*
.. _ogc-tb14: https://www.ogc.org/initiatives/testbed-14/
.. |ogc-tb14-platform-er| replace:: *ADES & EMS Results and Best Practices Engineering Report*
.. _ogc-tb14-platform-er: http://docs.opengeospatial.org/per/18-050r1.html
.. |ogc-tb15-ml| replace:: *OGC Testbed-15 - Machine Learning Thread*
.. _ogc-tb15-ml: https://www.ogc.org/initiatives/testbed-15/#MachineLearning
.. |ogc-tb15-ml-er| replace:: *OGC Testbed-15: Machine Learning Engineering Report*
.. _ogc-tb15-ml-er: http://docs.opengeospatial.org/per/19-027r2.html
.. |ogc-tb16| replace:: *OGC Testbed-16*
.. _ogc-tb16: https://www.ogc.org/initiatives/t-16/
.. |ogc-tb16-data-access-proc-er| replace:: *OGC Testbed-16: Data Access and Processing Engineering Report*
.. _ogc-tb16-data-access-proc-er: http://docs.opengeospatial.org/per/20-016.html
.. |ogc-tb16-ipynb-er| replace:: *OGC Testbed-16: Earth Observation Application Packages with Jupyter Notebooks Engineering Report*
.. _ogc-tb16-ipynb-er: http://docs.opengeospatial.org/per/20-035.html
.. |ogc-tb20-gdc| replace:: *OGC Testbed-20 - GeoDataCubes*
.. _ogc-tb20-gdc: https://www.ogc.org/initiatives/ogc-testbed-20/
.. |ogc-tb20-demo-days| replace:: OGC Testbed-20 Demonstration Days
.. _ogc-tb20-demo-days: https://www.ogc.org/event/t20-demo-days/
.. |ogc-tb20-gdc-api-file-report| replace:: OGC Testbed 20 GeoDataCube (GDC) API Profile Report
.. _ogc-tb20-gdc-api-file-report: https://docs.ogc.org/per/24-035.html
.. |ogc-tb20-gdc-prov-demo-report| replace:: OGC Testbed 20 GDC Provenance Demonstration Report
.. _ogc-tb20-gdc-prov-demo-report: https://docs.ogc.org/per/24-036.html
.. |ogc-tb20-gdc-usage-test-report| replace:: OGC Testbed 20 GDC Usability Testing Report
.. _ogc-tb20-gdc-usage-test-report: https://docs.ogc.org/per/24-037.html
.. |ogc-ospd| replace:: *OGC Open Science Persistent Demonstrator*
.. _ogc-ospd: https://www.ogc.org/initiatives/open-science/
.. |ogc-ospd-demo-video| replace:: OGC Open Science Demonstrations - Part 1
.. _ogc-ospd-demo-video: https://www.youtube.com/watch?v=CB_-Gn3eruM
.. |ogc-ospd-crim-video| replace:: OGC OSPD CRIM Workflow Demonstration in Galaxy
.. _ogc-ospd-crim-video: https://www.youtube.com/watch?v=68glSbzRIQI
.. |ogc-ospd-er| replace:: OGC Open Science Persistent Demonstrator (OSPD) Report
.. _ogc-ospd-er: http://docs.opengeospatial.org/per/24-022.html
.. |ogc-eo-apps-pilot| replace:: *OGC Earth Observation Applications Pilot*
.. _ogc-eo-apps-pilot: https://www.ogc.org/initiatives/eoa-pilot/
.. |ogc-eo-apps-pilot-er| replace:: *OGC Earth Observation Applications Pilot: CRIM Engineering Report*
.. _ogc-eo-apps-pilot-er: http://docs.opengeospatial.org/per/20-045.html
.. |ogc-best-practices-eo-apppkg| replace:: *OGC Best Practice for Earth Observation Application Package*
.. _ogc-best-practices-eo-apppkg: https://docs.ogc.org/bp/20-089r1.html
.. |ogc-129th-mm| replace:: *OGC 129th Member's Meeting*
.. _ogc-129th-mm: https://portal.ogc.org/meet/?p=default&mid=95
.. |ogc-131st-mm| replace:: *OGC 131st Member's Meeting*
.. _ogc-131st-mm: https://events.ogc.org/131MM#/agenda?day=3&lang=en&sessionId=126498000002166220
.. |ogc-apppkg| replace:: *OGC Application Package*
.. _ogc-apppkg: https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-dru/ogcapppkg.yaml
.. |ESIP| replace:: *Earth Science Information Partners*
.. _ESIP: https://www.esipfed.org/
.. |ESIP-2024| replace:: *Earth Science Information Partners* (ESIP) 2024 Meeting
.. _ESIP-2024: https://2024julyesipmeeting.sched.com/
.. |ESIP-2024-panel| replace:: *Cross-Platform Interoperability for Scalable Computing in Open Science Analysis and Algorithm Development*
.. _ESIP-2024-panel: https://2024julyesipmeeting.sched.com/
.. |ESIP-2024-presentation| replace:: *Perspectives on the integration of OGC standards to improve interoperability of open science data processing workflows*
.. _ESIP-2024-presentation: https://www.youtube.com/watch?v=7gqkdRuy2AE&list=PL8X9E6I5_i8iIFrualb2PriPQoF52aIPh&index=36
.. _CRIM: https://crim.ca/
.. _Ouranos: https://www.ouranos.ca/
.. _PAVICS: https://pavics.ouranos.ca/index.html
.. _Birdhouse: http://bird-house.github.io/
.. _birdhouse-deploy: https://github.com/bird-house/birdhouse-deploy
.. |DACCS-long| replace:: *Data Analytics for Canadian Climate Services*
.. _DACCS: https://github.com/DACCS-Climate
.. |DACCS-grant| replace:: DACCS
.. _DACCS-grant: https://app.dimensions.ai/details/grant/grant.8105745
.. _ClimateData.ca: https://ClimateData.ca
.. _DonneesClimatiques.ca: https://DonneesClimatiques.ca
.. |UofT| replace:: University of Toronto
.. _UofT: https://utoronto.ca
.. _RedOak: https://redoak.cs.toronto.edu/
.. |marble| replace:: Marble Climate
.. _marble: https://marbleclimate.com/
.. |CLIMAtlantic| replace:: CLIMAtlantic
.. _CLIMAtlantic: https://climatlantic.ca/
.. |ECCC| replace:: Environment and Climate Change Canada (ECCC)
.. _ECCC: https://www.canada.ca/en/environment-climate-change.html
.. |PCIC| replace:: Pacific Climate Impacts Consortium (PCIC)
.. _PCIC: https://www.pacificclimate.org/
.. |PCC| replace:: Prairie Climate Centre (PCC)
.. _PCC: https://prairieclimatecentre.ca/
.. _Pyramid: http://www.pylonsproject.org
.. |w3c-prov| replace:: W3C PROV
.. _w3c-prov: https://www.w3.org/TR/prov-overview
