.. Listing of all useful references for the documentation
.. Don't place any 'visible/rendered' documentation here (only links), or it will appear everywhere it is included

.. Util text/reference replace
.. |cwl| replace:: Common Workflow Language
.. _cwl: `cwl-home`_
.. |cwl-home| replace:: CWL Homepage
.. _cwl-home: https://www.commonwl.org/
.. |cwl-spec| replace:: CWL Specification
.. _cwl-spec: https://www.commonwl.org/#Specification
.. |cwl-guide| replace:: CWL User Guide
.. _cwl-guide: http://www.commonwl.org/user_guide/
.. |cwl-cmdtool| replace:: CWL CommandLineTool
.. _cwl-cmdtool: https://www.commonwl.org/v1.1/CommandLineTool.html
.. |cwl-workflow| replace:: CWL Workflow
.. _cwl-workflow: https://www.commonwl.org/v1.1/Workflow.html
.. _cwl-workdir-req: https://www.commonwl.org/v1.1/CommandLineTool.html#InitialWorkDirRequirement
.. _cwl-workdir-ex: https://www.commonwl.org/user_guide/15-staging/
.. _cwl-docker-req: https://www.commonwl.org/v1.1/CommandLineTool.html#DockerRequirement
.. _`Weaver Issues`: https://github.com/crim-ca/weaver/issues
.. |oas| replace:: OpenAPI Specification
.. _oas: https://pavics-weaver.readthedocs.io/en/latest/api.html
.. |ogc| replace:: Open Geospatial Consortium (OGC)
.. _ogc: https://www.ogc.org/
.. |ogc-home| replace:: |ogc| Homepage
.. _ogc-home: `ogc`_
.. |ogc-proc-api| replace:: OGC API - Processes
.. _ogc-proc-api: https://github.com/opengeospatial/wps-rest-binding

.. External references
.. _Celery: https://docs.celeryproject.org/en/latest/
.. _Gunicorn: https://gunicorn.org/
.. _MongoDB: https://www.mongodb.com/

.. Weaver Configurations
.. _weaver.config: ../../../config
.. _weaver.ini.example: ../../../config/weaver.ini.example
.. _data_sources.json.example: ../../../config/data_sources.json.example
.. _wps_processes.yml.example: ../../../config/wps_processes.yml.example
.. _request_options.yml.example: ../../../config/request_options.yml.example
.. _Dockerfile-manager: ../../../docker/Dockerfile-manager
.. _Dockerfile-worker: ../../../docker/Dockerfile-worker

.. API requests
.. |deploy-req| replace:: ``POST {WEAVER_URL}/processes`` (Deploy)
.. _deploy-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes%2Fpost
.. |getcap-req| replace:: ``GET {WEAVER_URL}/processes`` (GetCapabilities)
.. _getcap-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes%2Fget
.. |describe-req| replace:: ``GET {WEAVER_URL}/processes/{id}`` (DescribeProcess)
.. _describe-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget
.. |vis-req| replace:: ``PUT {WEAVER_URL}/processes/{id}/visibility`` (Visibility)
.. _vis-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1visibility%2Fput

