.. Listing of all useful references for the documentation
.. Don't place any 'visible/rendered' documentation here (only links), or it will appear everywhere it is included

.. Util text/reference replace
.. |ades| replace:: Application Deployment and Execution Service
.. |aws-credentials| replace:: AWS Credentials
.. _aws-credentials: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
.. |aws-config| replace:: AWS Configuration
.. _aws-config: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html
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
.. |cwl-io-map| replace:: CWL Mapping
.. _cwl-io-map: https://www.commonwl.org/v1.1/CommandLineTool.html#map
.. |cwl-io-type| replace:: CWLType Symbols
.. _cwl-io-type: https://www.commonwl.org/v1.1/CommandLineTool.html#CWLType
.. _cwl-metadata: https://www.commonwl.org/user_guide/17-metadata/index.html
.. _docker: https://docs.docker.com/develop/
.. |docker| replace:: Docker
.. |ems| replace:: Execution Management Service
.. |esgf| replace:: Earth System Grid Federation
.. _esgf: https://esgf.llnl.gov/
.. |esgf-cwt| replace:: ESGF Compute API
.. _esgf-cwt: https://github.com/ESGF/esgf-compute-api
.. |edam-link| replace:: EDAM media types
.. _edam-link: http://edamontology.org/
.. |iana-link| replace:: IANA media types
.. _iana-link: https://www.iana.org/assignments/media-types/media-types.xhtml
.. |metalink| replace:: Metalink
.. _metalink: https://tools.ietf.org/html/rfc5854
.. |oas| replace:: OpenAPI Specification
.. _oas: https://pavics-weaver.readthedocs.io/en/latest/api.html
.. |ogc| replace:: Open Geospatial Consortium
.. _ogc: https://www.ogc.org/
.. |ogc-home| replace:: |ogc| Homepage
.. _ogc-home: `ogc`_
.. |ogc-proc-api| replace:: OGC API - Processes
.. _ogc-proc-api: https://github.com/opengeospatial/wps-rest-binding
.. |pywps| replace:: PyWPS
.. _pywps: https://github.com/geopython/pywps/
.. |pywps-status| replace:: Progress and Status Report
.. _pywps-status: https://pywps.readthedocs.io/en/master/process.html#progress-and-status-report
.. |pywps-multi-output| replace:: PyWPS Multiple Outputs
.. _pywps-multi-output: https://pywps.readthedocs.io/en/master/process.html#returning-multiple-files
.. _wkt-example: https://en.wikipedia.org/wiki/Well-known_text_representation_of_geometry
.. _wkt-format: https://docs.geotools.org/stable/javadocs/org/opengis/referencing/doc-files/WKT.html
.. |weaver-issues| replace:: Weaver issues
.. _weaver-issues: https://github.com/crim-ca/weaver/issues
.. |submit-issue| replace:: submit a new issue
.. _submit-issue: https://github.com/crim-ca/weaver/issues/new/choose

.. External references
.. _Celery: https://docs.celeryproject.org/en/latest/
.. _Gunicorn: https://gunicorn.org/
.. _Miniconda: https://docs.conda.io/en/latest/miniconda.html
.. _MongoDB: https://www.mongodb.com/

.. Weaver Configurations
.. |weaver-config| replace:: ``weaver/config``
.. _weaver-config: ../../../config
.. _weaver.ini.example: ../../../config/weaver.ini.example
.. _data_sources.json.example: ../../../config/data_sources.json.example
.. _wps_processes.yml.example: ../../../config/wps_processes.yml.example
.. _request_options.yml.example: ../../../config/request_options.yml.example
.. _Dockerfile-manager: ../../../docker/Dockerfile-manager
.. _Dockerfile-worker: ../../../docker/Dockerfile-worker
.. _email-template: ../../../weaver/wps_restapi/templates/notification_email_example.mako

.. API requests
.. |deploy-req| replace:: ``POST {WEAVER_URL}/processes`` (Deploy)
.. _deploy-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes%2Fpost
.. |getcap-req| replace:: ``GET {WEAVER_URL}/processes`` (GetCapabilities)
.. _getcap-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes%2Fget
.. |describe-req| replace:: ``GET {WEAVER_URL}/processes/{id}`` (DescribeProcess)
.. _describe-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget
.. |exec-req| replace:: ``POST {WEAVER_URL}/processes/{id}/jobs`` (Execute)
.. _exec-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1{process_id}~1jobs%2Fpost
.. |vis-req| replace:: ``PUT {WEAVER_URL}/processes/{id}/visibility`` (Visibility)
.. _vis-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1visibility%2Fput
.. |pkg-req| replace:: ``GET {WEAVER_URL}/processes/{id}/package`` (Package)
.. _pkg-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Processes%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1package%2Fget
.. |log-req| replace:: ``GET {WEAVER_URL}/processes/{id}/jobs/{id}/logs`` (GetLogs)
.. _log-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Logs%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1jobs~1%7Bjob_id%7D~1logs%2Fget
.. |except-req| replace:: ``GET {WEAVER_URL}/processes/{id}/jobs/{id}/exceptions`` (GetLogs)
.. _except-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Logs%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1jobs~1%7Bjob_id%7D~1logs%2Fget
.. |status-req| replace:: ``GET {WEAVER_URL}/processes/{id}/jobs/{id}`` (GetStatus)
.. _status-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Status%2Fpaths%2F~1processes~1{process_id}~1jobs~1{job_id}%2Fget
.. |result-req| replace:: ``GET {WEAVER_URL}/processes/{id}/jobs/{id}/result`` (GetResult)
.. _result-req: https://pavics-weaver.readthedocs.io/en/latest/api.html#tag/Results%2Fpaths%2F~1processes~1%7Bprocess_id%7D~1jobs~1%7Bjob_id%7D~1result%2Fget
