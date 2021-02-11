import logging
import os
from typing import TYPE_CHECKING

from configparser import ConfigParser
from owslib.wps import WPSExecution
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther
from pyramid.threadlocal import get_current_request
from pyramid_celery import celery_app as app
from pywps.app import WPSRequest
from pywps.app.Service import Service
from pywps.response import WPSResponse
from pywps.response.execute import ExecuteResponse

from weaver.database import get_db
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes.convert import wps2json_job_payload
from weaver.processes.execution import submit_job_handler
from weaver.processes.types import PROCESS_WORKFLOW
from weaver.processes.utils import get_job_submission_response, get_process
from weaver.store.base import StoreProcesses
from weaver.utils import get_header, get_settings, get_weaver_url
from weaver.wps.utils import check_wps_status, load_pywps_config
from weaver.wps_restapi import swagger_definitions as sd
from weaver.visibility import VISIBILITY_PUBLIC

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Union
    from weaver.typedefs import HTTPValid


class WorkerService(Service):
    """
    Dispatches PyWPS requests from *older* WPS-1/2 XML endpoint to WPS-REST as appropriate.

    .. note::
        For every WPS-Request type, the parsing of XML content is already handled by the PyWPS service for GET/POST.
        All data must be retrieved from parsed :class:`WPSRequest` to avoid managing argument location and WPS versions.

    When ``GetCapabilities`` or ``DescribeProcess`` requests are received, directly return to result as XML based
    on content (no need to subprocess as Celery task that gets resolved quickly with only the process(es) details).
    When JSON content is requested, instead return the redirect link to corresponding WPS-REST API endpoint.

    When receiving ``Execute`` request, convert the XML payload to corresponding JSON and
    dispatch it to the Celery Worker to actually process it after job setup for monitoring.
    """
    def __init__(self, *_, is_worker=False, settings=None, **__):
        super(WorkerService, self).__init__(*_, **__)
        self.is_worker = is_worker
        self.settings = settings or get_settings(app)

    def get_capabilities(self, wps_request, *_, **__):
        # type: (WPSRequest, Any, Any) -> Union[WPSResponse, HTTPValid]
        """
        Redirect to WPS-REST endpoint if requested ``Content-Type`` is JSON, or handle ``GetCapabilities`` normally.
        """
        req = wps_request.http_request
        accept_type = get_header("Accept", req.headers)
        if accept_type == CONTENT_TYPE_APP_JSON:
            url = get_weaver_url(self.settings)
            resp = HTTPSeeOther(location="{}{}".format(url, sd.processes_uri))  # redirect
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp
        return super(WorkerService, self).get_capabilities(wps_request, *_, **__)

    def describe(self, wps_request, *_, **__):
        # type: (WPSRequest, Any, Any) -> Union[WPSResponse, HTTPValid]
        """
        Redirect to WPS-REST endpoint if requested ``Content-Type`` is JSON, or handle ``DescribeProcess`` normally.
        """
        req = wps_request.http_request
        accept_type = get_header("Accept", req.headers)
        if accept_type == CONTENT_TYPE_APP_JSON:
            url = get_weaver_url(self.settings)
            proc = wps_request.identifiers
            if not proc:
                raise HTTPBadRequest(sd.BadRequestGetProcessInfoResponse.description)
            if len(proc) > 1:
                raise HTTPBadRequest("Unsupported multi-process ID for description. Only provide one.")
            path = sd.process_uri.format(process_id=proc[0])
            resp = HTTPSeeOther(location="{}{}".format(url, path))  # redirect
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp
        return super(WorkerService, self).describe(wps_request, *_, **__)

    def execute(self, identifier, wps_request, uuid):
        # type: (str, WPSRequest, str) -> Union[WPSResponse, HTTPValid]
        """
        Dispatch operation to WPS-REST endpoint, which in turn should call back the real Celery Worker for execution.

        Overrides the original execute operation, that instead will get handled by :meth:`execute_job` following
        callback from Celery Worker that will handle process job creation and monitoring.
        """

        req = wps_request.http_request
        pid = wps_request.identifier
        proc = get_process(process_id=pid, settings=self.settings)  # raises if invalid or missing
        wps_process = self.processes.get(pid)

        # create the JSON payload from the XML content and submit job
        is_workflow = proc.type == PROCESS_WORKFLOW
        tags = req.args.get("tags", "").split(",") + ["xml", "wps-{}".format(wps_request.version)]
        data = wps2json_job_payload(wps_request, wps_process)
        body = submit_job_handler(data, self.settings, proc.processEndpointWPS1,
                                  process_id=pid, is_local=True, is_workflow=is_workflow, visibility=VISIBILITY_PUBLIC,
                                  language=wps_request.language, tags=tags, auth=dict(req.headers))

        # if accept was JSON, provide response content as is
        accept_type = get_header("Accept", req.headers)
        if accept_type == CONTENT_TYPE_APP_JSON:
            resp = get_job_submission_response(body)
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp

        # otherwise, recreate the equivalent content with expected XML template format
        job_id = body["jobID"]
        job_url = body["location"]
        wps_url = job_url.split("/jobs")[0]

        class WorkerExecuteResponse(ExecuteResponse):
            def __init__(self, *_, **__):
                super(WorkerExecuteResponse, self).__init__(wps_request, job_id, process=wps_process)
                self.wps_request = wps_request
                self.wps_request.raw = None  # make sure the doc gets generated
                self.message = "Process {} accepted".format(pid)

            @property
            def json(self):
                data.update({
                    "language": self.wps_request.language,
                    "service_instance": wps_url,
                    "status": self._process_accepted(),
                    "status_location": job_url,
                })
                return data

        # when called by the WSGI app, '__call__' will generate the XML from 'doc' property,
        # which itself is generated by template substitution of data from above 'json' property
        return WorkerExecuteResponse()

    def execute_job(self, process_id, wps_inputs, wps_outputs, mode, job_uuid):
        """
        Real execution of the process by active Celery Worker.
        """
        execution = WPSExecution(version="2.0", url="localhost")
        xml_request = execution.buildRequest(process_id, wps_inputs, wps_outputs, mode=mode, lineage=True)
        wps_request = WPSRequest()
        wps_request.identifier = process_id
        wps_request.set_version("2.0.0")
        request_parser = wps_request._post_request_parser(wps_request.WPS.Execute().tag)
        request_parser(xml_request)
        # NOTE:
        #  Setting 'status = false' will disable async execution of 'pywps.app.Process.Process'
        #  but this is needed since this job is running within Celery already async
        #  (daemon process can't have children processes)
        #  Because if how the code in PyWPS is made, we have to re-enable creation of status file
        wps_request.status = "false"
        wps_response = super(WorkerService, self).execute(process_id, wps_request, job_uuid)
        wps_response.store_status_file = True
        # update execution status with actual status file and apply required references
        execution = check_wps_status(location=wps_response.process.status_location, settings=self.settings)
        execution.request = xml_request
        return execution


def get_pywps_service(environ=None, is_worker=False):
    """
    Generates the PyWPS Service that provides *older* WPS-1/2 XML endpoint.
    """
    environ = environ or {}
    try:
        # get config file
        settings = get_settings(app)
        pywps_cfg = environ.get("PYWPS_CFG") or settings.get("PYWPS_CFG") or os.getenv("PYWPS_CFG")
        if not isinstance(pywps_cfg, ConfigParser) or not settings.get("weaver.wps_configured"):
            load_pywps_config(app, config=pywps_cfg)

        # call pywps application with processes filtered according to the adapter's definition
        process_store = get_db(app).get_store(StoreProcesses)
        processes_wps = [process.wps() for process in
                         process_store.list_processes(visibility=VISIBILITY_PUBLIC)]
        service = WorkerService(processes_wps, is_worker=is_worker, settings=settings)
    except Exception as ex:
        LOGGER.exception("Error occurred during PyWPS Service and/or Processes setup.")
        raise OWSNoApplicableCode("Failed setup of PyWPS Service and/or Processes. Error [{!r}]".format(ex))
    return service
