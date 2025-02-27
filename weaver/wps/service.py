import logging
import os
from configparser import ConfigParser
from typing import TYPE_CHECKING
from urllib.parse import urlparse, unquote

import colander
from owslib.wps import WPSExecution
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther
from pyramid.request import Request as PyramidRequest
from pywps.app import Process as ProcessWPS, WPSRequest
from pywps.app.Service import Service as ServiceWPS
from pywps.response.basic import WPSResponse
from pywps.response.execute import ExecuteResponse
from requests.structures import CaseInsensitiveDict
from werkzeug.datastructures import Headers
from werkzeug.wrappers.request import Request as WerkzeugRequest

from weaver.database import get_db
from weaver.datatype import Process
from weaver.exceptions import handle_known_exceptions
from weaver.formats import ContentType, get_format, guess_target_format
from weaver.owsexceptions import OWSException, OWSInvalidParameterValue, OWSNoApplicableCode
from weaver.processes.convert import get_field, wps2json_job_payload
from weaver.processes.types import ProcessType
from weaver.processes.utils import get_process
from weaver.store.base import StoreProcesses
from weaver.utils import (
    extend_instance,
    get_header,
    get_registry,
    get_request_args,
    get_settings,
    get_weaver_url,
    parse_kvp,
    repr_json
)
from weaver.visibility import Visibility
from weaver.wps.storage import ReferenceStatusLocationStorage
from weaver.wps.utils import (
    check_wps_status,
    get_wps_local_status_location,
    get_wps_output_context,
    get_wps_output_dir,
    get_wps_output_url,
    load_pywps_config
)
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs.utils import get_job_submission_response

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Deque, Dict, List, Optional, Union

    from pywps.inout.basic import ComplexInput
    from uuid import UUID

    from weaver.datatype import Job
    from weaver.typedefs import (
        AnyHeadersCookieContainer,
        AnyRequestType,
        HTTPValid,
        JSON,
        SettingsType,
        WPS_InputData,
        WPS_OutputRequested
    )


class WorkerRequest(WPSRequest):
    """
    Extended :mod:`pywps` request with additional handling provided by :mod:`weaver`.
    """
    _auth_headers = CaseInsensitiveDict({  # take advantage of case-insensitive only, value don't care
        "Authorization": None,
        "Proxy-Authorization": None,
        "X-Auth": None,
        "Cookie": None,
        "Set-Cookie": None,
        sd.XAuthVaultFileHeader.name: None,
    })

    def __init__(self, http_request=None, http_headers=None, **kwargs):
        # type: (Optional[AnyRequestType], Optional[AnyHeadersCookieContainer], **Any) -> None
        if http_request and not isinstance(http_request, WerkzeugRequest):
            http_request = extend_instance(http_request, WerkzeugRequest)
        super(WorkerRequest, self).__init__(http_request, **kwargs)
        self.auth_headers = Headers()
        if http_request:
            self.auth_headers.update(self.parse_auth_headers(http_request.headers))
        if http_headers:
            self.auth_headers.update(self.parse_auth_headers(http_headers))

    def parse_auth_headers(self, headers):
        # type: (Optional[AnyHeadersCookieContainer]) -> Headers
        if not headers:
            return Headers()
        if isinstance(headers, dict):
            headers = list(headers.items())
        auth_headers = Headers()
        for name, value in headers:
            if name in self._auth_headers:
                auth_headers.add(name, value)
        return auth_headers


class WorkerExecuteResponse(ExecuteResponse):
    """
    XML response generator from predefined job status URL and executed process definition.
    """

    def __init__(self, wps_request, uuid, process, job_url, settings, *_, **__):
        # type: (WorkerRequest, str, ProcessWPS, str, SettingsType, *Any, **Any) -> None

        super(WorkerExecuteResponse, self).__init__(wps_request, uuid, process=process)

        # extra setup
        self.process._status_store = ReferenceStatusLocationStorage(job_url, settings)
        self.store_status_file = True  # enforce storage to provide the status location URL
        self.wps_request.raw = None    # make sure doc gets generated by disabling alternate raw data mode
        self._update_status_doc()      # generate 'doc' property with XML content for response


class WorkerService(ServiceWPS):
    """
    Dispatches PyWPS requests from WPS-1/2 XML endpoint to WPS-REST as appropriate.

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
        # type: (*Any, bool, SettingsType, **Any) -> None
        super(WorkerService, self).__init__(*_, **__)
        self.is_worker = is_worker
        self.settings = settings or get_settings()
        self.dispatched_processes = {}  # type: Dict[str, Process]

    @handle_known_exceptions
    def _get_capabilities_redirect(self, wps_request, *_, **__):
        # type: (WPSRequest, *Any, **Any) -> Optional[Union[WPSResponse, HTTPValid]]
        """
        Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON.
        """
        req = wps_request.http_request
        accept_type = get_header("Accept", req.headers)
        if accept_type == ContentType.APP_JSON:
            url = get_weaver_url(self.settings)
            resp = HTTPSeeOther(location=f"{url}{sd.processes_service.path}")  # redirect
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp
        return None

    def get_capabilities(self, wps_request, *_, **__):
        # type: (WPSRequest, *Any, **Any) -> Union[WPSResponse, HTTPValid]
        """
        Handles the ``GetCapabilities`` KVP/XML request submitted on the WPS endpoint.

        Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON or handle ``GetCapabilities`` normally.
        """
        resp = self._get_capabilities_redirect(wps_request, *_, **__)
        return resp or super(WorkerService, self).get_capabilities(wps_request, *_, **__)

    @handle_known_exceptions
    def _describe_process_redirect(self, wps_request, *_, **__):
        # type: (WPSRequest, *Any, **Any) -> Optional[Union[WPSResponse, HTTPValid]]
        """
        Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON.
        """
        req = wps_request.http_request
        req = extend_instance(req, PyramidRequest)  # apply query 'params' method
        accept_type = guess_target_format(req, default=ContentType.APP_XML)
        if accept_type == ContentType.APP_JSON:
            url = get_weaver_url(self.settings)
            proc = wps_request.identifiers
            if not proc:
                raise HTTPBadRequest(sd.BadRequestGetProcessInfoResponse.description)
            if len(proc) > 1:
                raise HTTPBadRequest("Unsupported multi-process ID for description. Only provide one.")
            path = sd.process_service.path.format(process_id=proc[0])
            resp = HTTPSeeOther(location=f"{url}{path}")  # redirect
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp
        return None

    def describe(self, wps_request, uuid, identifiers, *_, **__):
        # type: (WPSRequest, UUID, List[str], *Any, **Any) -> Union[WPSResponse, HTTPValid]
        """
        Handles the ``DescribeProcess`` KVP/XML request submitted on the WPS endpoint.

        Redirect to WPS-REST endpoint if requested ``Content-Type`` is JSON or handle ``DescribeProcess`` normally.
        """
        # patch exact duplicate (ID/Revisions) to avoid redundant listing (PyWPS does not consider it)
        # use list/dict trick to get unique IDs with preserved ordering in case others are specified
        wps_request.identifiers = list({p_id: None for p_id in wps_request.identifiers})
        if identifiers:
            identifiers = wps_request.identifiers

        resp = self._describe_process_redirect(wps_request, *_, **__)
        return resp or super(WorkerService, self).describe(wps_request, uuid, identifiers, *_, **__)

    @handle_known_exceptions
    def _submit_job(self, wps_request):
        # type: (WPSRequest) -> Union[WPSResponse, HTTPValid, JSON]
        """
        Dispatch operation to WPS-REST endpoint, which in turn should call back the real Celery Worker for execution.

        Returns the status response as is if XML, or convert it to JSON, according to request ``Accept`` header.
        """
        from weaver.processes.execution import submit_job_handler  # pylint: disable=C0415  # circular import error

        req = wps_request.http_request  # type: Union[PyramidRequest, WerkzeugRequest]
        pid = wps_request.identifier
        ctx = get_wps_output_context(req)  # re-validate here in case submitted via WPS endpoint instead of REST-API
        proc = get_process(process_id=pid, settings=self.settings)  # raises if invalid or missing
        wps_process = self.processes.get(pid)

        # create the JSON payload from the XML content and submit job
        is_workflow = proc.type == ProcessType.WORKFLOW
        args = get_request_args(req)
        tags = args.get("tags", "").split(",") + ["xml", f"wps-{wps_request.version}"]
        data = wps2json_job_payload(wps_request, wps_process)
        headers = dict(req.headers)
        headers.update({
            "Accept": ContentType.APP_JSON,
            "Content-Type": ContentType.APP_JSON,
        })
        resp = submit_job_handler(
            data, self.settings, proc.processEndpointWPS1,
            process=proc, is_local=True, is_workflow=is_workflow, visibility=Visibility.PUBLIC,
            language=wps_request.language, tags=tags, headers=headers, context=ctx
        )
        # enforced JSON results with submitted data that includes 'response=document'
        # use 'json_body' to work with any 'response' implementation
        body = resp.json_body

        # if Accept was JSON, provide response content as is
        # if anything else (even */*), return as XML
        # NOTE:
        #   It is very important to respect default XML since 'owslib.wps.WebProcessingService' does not provide any
        #   way to provide explicitly Accept header. Even our Wps1Process as Workflow step depends on this behaviour.
        accept_type = get_header("Accept", req.headers)
        if accept_type == ContentType.APP_JSON:
            resp = get_job_submission_response(body, resp.headers)
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp

        return body

    @handle_known_exceptions
    def create_complex_inputs(self, source, inputs):
        # type: (ComplexInput, List[Dict[str, str]]) -> Deque[ComplexInput]
        """
        Dynamically adjust process input definitions to align with unrestricted format as applicable.

        Due to how :meth:`create_complex_inputs` of :mod:`pywps` is implemented
        (check of format by ``[0]`` index), a ``supported_formats`` property must always contain at least 1 format.
        However, that restriction erroneously rejects an "any" :term:`Media-Type` input that does not enforce
        a specific format (i.e.: ``text/plain`` and ``*/*`` by default). Therefore, update the input dynamically
        to inject the missing formats matching submitted inputs to make them succeed the validation transparently.

        Without this patch, a submitted input trying to be more informative about its content by advertising its
        actual :term:`Media-Type`, schema, encoding, etc. gets penalized over an input "just" submitting the
        complex data/file reference.
        """
        input_def = source.clone()
        input_use_default_format = (
            len(input_def.supported_formats) == 1 and
            input_def.supported_formats[0].default and
            input_def.supported_formats[0].mime_type in [ContentType.TEXT_PLAIN, ContentType.ANY]
        )
        if input_use_default_format:
            patched_formats = [input_def.supported_formats[0]]
            patched_media_types = [patched_formats[0].mime_type]
            for input_data in inputs:
                data_ctype = get_field(input_data, "mimeType", search_variations=True)
                if data_ctype and data_ctype not in patched_media_types:
                    patched_media_types.append(data_ctype)
                    data_format = get_format(data_ctype)
                    data_format.encoding = get_field(input_data, "encoding", default=data_format.encoding)
                    data_format.schema = get_field(input_data, "schema", default=data_format.schema)
                    patched_formats.append(data_format)
            input_def.supported_formats = tuple(patched_formats)

        return super(WorkerService, self).create_complex_inputs(input_def, inputs)

    @handle_known_exceptions
    def prepare_process_for_execution(self, identifier):
        # type: (str) -> ProcessWPS
        """
        Handles dispatched remote provider process preparation during execution request.
        """
        # remote provider processes to instantiate
        dispatch_process = self.dispatched_processes.get(identifier)
        if dispatch_process:
            LOGGER.debug("Preparing dispatched remote provider process definition for execution: [%s]", identifier)
            try:
                self.processes[identifier] = dispatch_process.wps()  # prepare operation looks within this mapping
                process_wps = super(WorkerService, self).prepare_process_for_execution(identifier)
            except Exception as exc:
                LOGGER.error("Error occurred during remote provider process creation for execution.", exc_info=exc)
                raise
            finally:
                # cleanup temporary references
                self.dispatched_processes.pop(identifier, None)
                self.processes.pop(identifier, None)
            return process_wps

        # local processes already loaded by the service
        return super(WorkerService, self).prepare_process_for_execution(identifier)

    def execute(self, identifier, wps_request, uuid):
        # type: (str, Union[WPSRequest, WorkerRequest], str) -> Union[WPSResponse, HTTPValid]
        """
        Handles the ``Execute`` :term:`KVP`/:term:`XML` request submitted on the :term:`WPS` endpoint.

        Submit :term:`WPS` request to corresponding :term:`WPS-REST` endpoint and convert back for
        requested ``Accept`` content-type.

        Overrides the original execute operation, that will instead be handled by :meth:`execute_job`
        following callback from :mod:`celery` worker, which handles :term:`Job` creation and monitoring.

        If ``Accept`` is :term:`JSON`, the result is directly returned from :meth:`_submit_job`.
        If ``Accept`` is :term:`XML` or undefined, :class:`WorkerExecuteResponse` converts the
        received :term:`JSON` with :term:`XML` template.
        """
        result = self._submit_job(wps_request)
        if not isinstance(result, dict):
            return result  # pre-built HTTP response with JSON contents when requested

        # otherwise, recreate the equivalent content with expected XML template format
        job_id = result["jobID"]
        wps_process = self.processes.get(wps_request.identifier)

        # because we are building the XML response (and JSON not explicitly requested)
        # caller is probably a WPS-1 client also expecting a status XML file
        # remap the status location accordingly from the current REST endpoint
        job_url = result["location"]
        if urlparse(job_url).path.endswith(f"/jobs/{job_id}"):
            # file status does not exist yet since client calling this method is waiting for it
            # pywps will generate it once the WorkerExecuteResponse is returned
            status_path = get_wps_local_status_location(job_url, self.settings, must_exist=False)
            wps_dir = get_wps_output_dir(self.settings)
            wps_url = get_wps_output_url(self.settings)
            job_url = status_path.replace(wps_dir, wps_url, 1)

        # when called by the WSGI app, 'WorkerExecuteResponse.__call__' will generate the XML from 'doc' property,
        # which itself is generated by template substitution of data from above 'json' property
        try:
            return WorkerExecuteResponse(wps_request, job_id, wps_process, job_url, settings=self.settings)
        except Exception as ex:  # noqa
            LOGGER.exception("Error building XML response by PyWPS Service during WPS Execute result from worker.")
            message = f"Failed building XML response from WPS Execute result. Error [{ex!r}]"
            raise OWSNoApplicableCode(message, locator=job_id)

    def execute_job(self,
                    job,                # type: Job
                    wps_inputs,         # type: List[WPS_InputData]
                    wps_outputs,        # type: List[WPS_OutputRequested]
                    remote_process,     # type: Optional[Process]
                    headers,            # type: Optional[AnyHeadersCookieContainer]
                    ):                  # type: (...) -> WPSExecution
        """
        Real execution of the process by active Celery Worker.
        """
        process_id = job.process
        execution = WPSExecution(version="2.0", url="localhost")
        xml_request = execution.buildRequest(process_id, wps_inputs, wps_outputs, mode=job.execution_mode, lineage=True)
        wps_request = WorkerRequest(http_headers=headers)
        wps_request.identifier = process_id  # pylint: disable=W0201
        wps_request.check_and_set_language(job.accept_language)
        wps_request.set_version("2.0.0")
        request_parser = wps_request._post_request_parser(wps_request.WPS.Execute().tag)  # noqa: W0212
        request_parser(xml_request)  # parses the submitted inputs/outputs data and request parameters

        # NOTE:
        #  Setting 'status = false' will disable async execution of 'pywps.app.Process.Process'
        #  but this is needed since this job is running within Celery worker already async
        #  (daemon process can't have children processes).
        wps_request.status = "false"  # pylint: disable=W0201

        # When 'execute' is called, pywps will in turn call 'prepare_process_for_execution',
        # which then setups and retrieves currently loaded 'local' processes.
        # Since only local processes were defined by 'get_pywps_service',
        # a temporary process must be added for remote providers execution.
        if not remote_process:
            worker_process_id = process_id
        else:
            worker_process_id = f"wps_package-{process_id}-{job.uuid}"
            self.dispatched_processes[worker_process_id] = remote_process

        wps_response = super(WorkerService, self).execute(worker_process_id, wps_request, job.uuid)
        # re-enable creation of status file, so we can find it since we disabled 'status' earlier for sync execution
        wps_response.store_status_file = True
        # update execution status with actual status file and apply required references
        execution = check_wps_status(location=wps_response.process.status_location, settings=self.settings)
        execution.request = xml_request
        return execution


def check_invalid_ids(identifiers, content_type):
    # type: (List[str], Optional[str]) -> None
    try:
        sd.ProcessNamesList().deserialize(identifiers)
    except colander.Invalid as exc:
        invalid_ids = [invalid.value for invalid in exc.children]
        body = None
        desc = "Invalid identifiers use disallowed characters."
        if ContentType.APP_JSON in str(content_type):
            body = {
                "code": OWSInvalidParameterValue.code,
                "name": "identifier",
                "description": desc,
                "value": repr_json(invalid_ids, force_string=False)
            }
        else:
            desc = f"{desc} {repr_json(invalid_ids, force_string=True, indent=None)}"
        raise OWSInvalidParameterValue(desc, locator="identifier", json=body)


def get_pywps_service(environ=None, is_worker=False):
    # type: (SettingsType, bool) -> WorkerService
    """
    Generates the PyWPS Service that provides WPS-1/2 XML endpoint.
    """
    environ = environ or {}
    try:
        # get config file
        registry = get_registry()
        settings = get_settings(registry)
        pywps_cfg = environ.get("PYWPS_CFG") or settings.get("PYWPS_CFG") or os.getenv("PYWPS_CFG")
        if not isinstance(pywps_cfg, ConfigParser) or not settings.get("weaver.wps_configured"):
            load_pywps_config(settings, config=pywps_cfg)

        # resolve pre-filtered list of process(es), and whether they require any explicit revision tag
        # do this dynamically in advance since a lot of processes could require listing + conversion
        # avoid unnecessary resolution of processes that will not be employed otherwise
        query = unquote(environ.get("QUERY_STRING") or "")
        proc_ids = parse_kvp(query, pair_sep="&").get("identifier") or None
        if proc_ids and not is_worker:
            # pre-validate in case WPS endpoint invoked directly (non-worker, IDs not already validated)
            # to avoid illegal search characters with DB
            check_invalid_ids(proc_ids, environ.get("HTTP_ACCEPT"))

        # call pywps application with processes filtered according to the adapter's definition
        process_store = get_db(registry).get_store(StoreProcesses)  # type: StoreProcesses
        processes_wps = [
            process.wps() for process in
            process_store.list_processes(visibility=Visibility.PUBLIC, identifiers=proc_ids)
        ]
        service = WorkerService(processes_wps, is_worker=is_worker, settings=settings)
    except OWSException:
        raise  # handled
    except Exception as ex:
        LOGGER.exception("Error occurred during PyWPS Service and/or Processes setup.")
        raise OWSNoApplicableCode(f"Failed setup of PyWPS Service and/or Processes. Error [{ex!r}]")
    return service
