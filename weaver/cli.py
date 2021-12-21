import argparse
import base64
import copy
import inspect
import logging
import os
import sys
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import yaml
from yaml.scanner import ScannerError

from weaver import __meta__
from weaver.datatype import AutoBase
from weaver.exceptions import PackageRegistrationError
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_RESPONSE_DOCUMENT, EXECUTE_TRANSMISSION_MODE_VALUE
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.processes.convert import cwl2json_input_values, repr2json_input_values
from weaver.processes.wps_package import get_process_definition
from weaver.status import JOB_STATUS_CATEGORIES, JOB_STATUS_CATEGORY_FINISHED, STATUS_SUCCEEDED
from weaver.utils import fetch_file, get_any_id, get_any_value, load_file, null, repr_json, request_extra, setup_loggers
from weaver.visibility import VISIBILITY_PUBLIC

if TYPE_CHECKING:
    from typing import Any, Optional, Tuple, Union

    from requests import Response

    # avoid failing sphinx-argparse documentation
    # https://github.com/ashb/sphinx-argparse/issues/7
    try:
        from weaver.typedefs import CWL, HeadersType, JSON
    except ImportError:
        CWL = HeadersType = JSON = Any  # avoid linter issue

LOGGER = logging.getLogger(__name__)

OPERATION_ARGS_TITLE = "Operation Arguments"
OPTIONAL_ARGS_TITLE = "Optional Arguments"
REQUIRED_ARGS_TITLE = "Required Arguments"


def _json2text(data):
    return repr_json(data, indent=2, ensure_ascii=False)


class OperationResult(AutoBase):
    """
    Data container for any :class:`WeaverClient` operation results.

    :param success: Success status of the operation.
    :param message: Detail extracted from response content if available.
    :param headers: Headers returned by the response for reference.
    :param body: Content of :term:`JSON` response or fallback in plain text.
    :param text: Pre-formatted text representation of :paramref:`body`.
    """
    success = False     # type: Optional[bool]
    message = ""        # type: Optional[str]
    headers = {}        # type: Optional[HeadersType]
    body = {}           # type: Optional[Union[JSON, str]]
    code = None         # type: Optional[int]

    def __init__(self,
                 success=None,  # type: Optional[bool]
                 message=None,  # type: Optional[str]
                 body=None,     # type: Optional[Union[str, JSON]]
                 headers=None,  # type: Optional[HeadersType]
                 text=None,     # type: Optional[str]
                 code=None,     # type: Optional[int]
                 **kwargs,      # type: Any
                 ):             # type: (...) -> None
        super(OperationResult, self).__init__(**kwargs)
        self.success = success
        self.message = message
        self.headers = headers
        self.body = body
        self.text = text
        self.code = code

    def __repr__(self):
        params = ["success", "code", "message"]
        quotes = [False, False, True]
        quoted = lambda q, v: f"\"{v}\"" if q and v is not None else v  # noqa: E731
        values = ", ".join([f"{param}={quoted(quote, getattr(self, param))}" for quote, param in zip(quotes, params)])
        return f"{type(self).__name__}({values})\n{self.text}"

    @property
    def text(self):
        # type: () -> str
        text = dict.get(self, "text", None)
        if not text and self.body:
            text = _json2text(self.body)
            self["text"] = text
        return text

    @text.setter
    def text(self, text):
        # type: (str) -> None
        self["text"] = text


class WeaverClient(object):
    """
    Client that handles common HTTP requests with a `Weaver` or similar :term:`OGC API - Processes` instance.
    """
    # default configuration parameters, overridable by corresponding method parameters
    monitor_timeout = 60    # maximum delay to wait for job completion
    monitor_interval = 5    # interval between monitor pooling job status requests

    def __init__(self, url=None):
        # type: (Optional[str]) -> None
        if url:
            self._url = self._parse_url(url)
            LOGGER.debug("Using URL: [%s]", self._url)
        else:
            self._url = None
            LOGGER.warning("No URL provided. All operations must provide it directly or through another parameter!")
        self._headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        self._settings = {
            "weaver.request_options": {}
        }  # FIXME: load from INI, overrides as input (cumul arg '--setting weaver.x=value') ?

    def _get_url(self, url):
        if not self._url and not url:
            raise ValueError("No URL available. Client was not created with an URL and operation did not receive one.")
        return self._url or self._parse_url(url)

    @staticmethod
    def _parse_url(url):
        parsed = urlparse("http://" + url if not url.startswith("http") else url)
        parsed_netloc_path = f"{parsed.netloc}{parsed.path}".replace("//", "/")
        parsed_url = f"{parsed.scheme}://{parsed_netloc_path}"
        return parsed_url.rsplit("/", 1)[0] if parsed_url.endswith("/") else parsed_url

    @staticmethod
    def _parse_result(response, message=None):
        # type: (Response, Optional[str]) -> OperationResult
        hdr = dict(response.headers)
        success = False
        try:
            body = response.json()
            msg = message or body.get("description", body.get("message", "undefined"))
            if response.status_code >= 400:
                if not msg:
                    msg = body.get("error", body.get("exception", "unknown"))
            else:
                success = True
            text = _json2text(body)
        except Exception:  # noqa
            text = body = response.text
            msg = "Could not parse body."
        return OperationResult(success, msg, body, hdr, text=text, code=response.status_code)

    @staticmethod
    def _parse_deploy_body(body, process_id):
        # type: (Optional[Union[JSON, str]], Optional[str]) -> OperationResult
        data = {}  # type: JSON
        try:
            if body:
                if isinstance(body, str) and (body.startswith("http") or os.path.isfile(body)):
                    data = load_file(body)
                elif isinstance(body, str) and body.startswith("{") and body.endswith("}"):
                    data = yaml.safe_load(body)
                elif isinstance(body, dict):
                    data = body
                else:
                    msg = "Cannot load badly formed body. Deploy JSON object or file reference expected."
                    return OperationResult(False, msg, body, {})
            elif not body:
                data = {
                    "processDescription": {
                        "process": {"id": process_id}
                    }
                }
            if body and process_id:
                LOGGER.debug("Override provided process ID [%s] into provided/loaded body.", process_id)
                data.setdefault("processDescription", {})
                data["processDescription"].setdefault("process", {})
                data["processDescription"]["process"]["id"] = process_id  # type: ignore
            # for convenience, always set visibility by default
            data.setdefault("processDescription", {})
            data["processDescription"].setdefault("process", {})
            data["processDescription"]["process"]["visibility"] = VISIBILITY_PUBLIC  # type: ignore
        except (ValueError, TypeError, ScannerError) as exc:
            return OperationResult(False, f"Failed resolution of body definition: [{exc!s}]", body)
        return OperationResult(True, "", data)

    @staticmethod
    def _parse_deploy_package(body, cwl, wps, process_id, headers):
        # type: (JSON, Optional[CWL], Optional[str], Optional[str], HeadersType) -> OperationResult
        try:
            p_id = body.get("processDescription", {}).get("process", {}).get("id", process_id)
            info = {"id": p_id}  # minimum requirement for process offering validation
            if (isinstance(cwl, str) and not cwl.startswith("{")) or isinstance(wps, str):
                LOGGER.debug("Override loaded CWL into provided/loaded body for process: [%s]", p_id)
                proc = get_process_definition(info, reference=cwl or wps, headers=headers)  # validate
                body["executionUnit"] = [{"unit": proc["package"]}]
            elif isinstance(cwl, str) and cwl.startswith("{") and cwl.endswith("}"):
                LOGGER.debug("Override parsed CWL into provided/loaded body for process: [%s]", p_id)
                pkg = yaml.safe_load(cwl)
                if not isinstance(pkg, dict) or pkg.get("cwlVersion") is None:
                    raise PackageRegistrationError("Failed parsing or invalid CWL from expected literal JSON string.")
                proc = get_process_definition(info, package=pkg, headers=headers)  # validate
                body["executionUnit"] = [{"unit": proc["package"]}]
            elif isinstance(cwl, dict):
                LOGGER.debug("Override provided CWL into provided/loaded body for process: [%s]", p_id)
                get_process_definition(info, package=cwl, headers=headers)  # validate
                body["executionUnit"] = [{"unit": cwl}]
        except (PackageRegistrationError, ScannerError) as exc:
            message = f"Failed resolution of package definition: [{exc!s}]"
            return OperationResult(False, message, cwl)
        return OperationResult(True, p_id, body)

    def _parse_job_ref(self, job_reference, url=None):
        # type: (str, Optional[str]) -> Tuple[Optional[str], Optional[str]]
        if job_reference.startswith("http"):
            job_url = job_reference
            job_parts = [part for part in job_url.split("/") if part.strip()]
            job_id = job_parts[-1]
        else:
            url = self._get_url(url)
            job_id = job_reference
            job_url = f"{url}/jobs/{job_id}"
        return job_id, job_url

    @staticmethod
    def _parse_auth_token(token, username, password):
        # type: (Optional[str], Optional[str], Optional[str]) -> HeadersType
        if token or (username and password):
            if not token:
                token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
            return {"X-Auth-Docker": f"Basic {token}"}
        return {}

    def deploy(self,
               process_id=None,     # type: Optional[str]
               body=None,           # type: Optional[Union[JSON, str]]
               cwl=None,            # type: Optional[Union[CWL, str]]
               wps=None,            # type: Optional[str]
               token=None,          # type: Optional[str]
               username=None,       # type: Optional[str]
               password=None,       # type: Optional[str]
               undeploy=False,      # type: bool
               url=None,            # type: Optional[str]
               ):                   # type: (...) -> OperationResult
        """
        Deploy a new :term:`Process` with specified metadata and reference to an :term:`Application Package`.

        The referenced :term:`Application Package` must be one of:
        - :term:`CWL` body, local file or URL in :term:`JSON` or :term:`YAML` format
        - :term:`WPS` process URL with :term:`XML` response
        - :term:`WPS-REST` process URL with :term:`JSON` response
        - :term:`OGC API - Processes` process URL with :term:`JSON` response

        If the reference is resolved to be a :term:`Workflow`, all its underlying :term:`Process` steps must be
        available under the same URL that this client was initialized with.

        .. seealso::
            :ref:`proc_op_deploy`

        :param process_id:
            Desired process identifier.
            Can be omitted if already provided in body contents or file.
        :param body:
            Literal :term:`JSON` contents, either using string representation of actual Python objects forming the
            request body, or file path/URL to :term:`YAML` or :term:`JSON` contents of the request body.
            Other parameters (:paramref:`process_id`, :paramref:`cwl`) can override corresponding fields within the
            provided body.
        :param cwl:
            Literal :term:`JSON` or :term:`YAML` contents, either using string representation of actual Python objects,
            or file path/URL with contents of the :term:`CWL` definition of the :term:`Application package` to be
            inserted into the body.
        :param wps:
            URL to an existing :term:`WPS` process (WPS-1/2 or WPS-REST/OGC-API).
        :param token:
            Authentication token for accessing private Docker registry if :term:`CWL` refers to such image.
        :param username:
            Username to form the authentication token to a private Docker registry.
        :param password:
            Password to form the authentication token to a private Docker registry.
        :param undeploy:
            Perform undeploy step as applicable prior to deployment to avoid conflict with exiting :term:`Process`.
        :param url:
            Instance URL if not already provided during client creation.
        :returns: results of the operation.
        """
        result = self._parse_deploy_body(body, process_id)
        if not result.success:
            return result
        headers = copy.deepcopy(self._headers)
        headers.update(self._parse_auth_token(token, username, password))
        data = result.body
        result = self._parse_deploy_package(data, cwl, wps, process_id, headers)
        if not result.success:
            return result
        p_id = result.message
        data = result.body
        base = self._get_url(url)
        if undeploy:
            LOGGER.debug("Performing requested undeploy of process: [%s]", p_id)
            result = self.undeploy(process_id=p_id, url=base)
            if result.code not in [200, 404]:
                return OperationResult(False, "Failed requested undeployment prior deployment.",
                                       body=result.body, text=result.text, code=result.code, headers=result.headers)
        path = f"{base}/processes"
        resp = request_extra("POST", path, json=data, headers=headers, settings=self._settings)
        return self._parse_result(resp)

    def undeploy(self, process_id, url=None):
        # type: (str, Optional[str]) -> OperationResult
        """
        Undeploy an existing :term:`Process`.

        :param process_id: Identifier of the process to undeploy.
        :param url: Instance URL if not already provided during client creation.
        """
        base = self._get_url(url)
        path = f"{base}/processes/{process_id}"
        resp = request_extra("DELETE", path, headers=self._headers, settings=self._settings)
        return self._parse_result(resp)

    def capabilities(self, url=None):
        # type: (Optional[str]) -> OperationResult
        """
        List all available :term:`Process` on the instance.

        .. seealso::
            :ref:`proc_op_getcap`

        :param url: Instance URL if not already provided during client creation.
        """
        base = self._get_url(url)
        path = f"{base}/processes"
        query = {"detail": False}  # not supported by non-Weaver, but save the work if possible
        resp = request_extra("GET", path, params=query, headers=self._headers, settings=self._settings)
        result = self._parse_result(resp)
        processes = result.body.get("processes")
        if isinstance(processes, list) and all(isinstance(proc, dict) for proc in processes):
            processes = [get_any_id(proc) for proc in processes]
            result.body = processes
        return result

    processes = capabilities  # alias
    """
    Alias of :meth:`capabilities` for :term:`Process` listing.
    """

    def describe(self, process_id, url=None):
        # type: (str, Optional[str]) -> OperationResult
        """
        Describe the specified :term:`Process`.

        .. seealso::
            :ref:`proc_op_describe`

        :param process_id: Identifier of the process to describe.
        :param url: Instance URL if not already provided during client creation.
        """
        base = self._get_url(url)
        path = f"{base}/processes/{process_id}"
        resp = request_extra("GET", path, headers=self._headers, settings=self._settings)
        # API response from this request can contain 'description' matching the process description
        # rather than a generic response 'description'. Enforce the provided message to avoid confusion.
        return self._parse_result(resp, message="Process description successfully retrieved.")

    @staticmethod
    def _parse_inputs(inputs):
        # type: (Optional[Union[str, JSON]]) -> Union[OperationResult, JSON]
        try:
            if isinstance(inputs, str):
                # loaded inputs could be mapping or listing format (any schema: CWL, OGC, OLD)
                inputs = load_file(inputs) if inputs != "" else []
            if not inputs or not isinstance(inputs, (dict, list)):
                return OperationResult(False, "No inputs or invalid schema provided.", inputs)
            if isinstance(inputs, list):
                # list of literals from CLI
                if any("=" in value for value in inputs):
                    inputs = repr2json_input_values(inputs)
                # list of single file from CLI (because of 'nargs')
                elif len(inputs) == 1 and "=" not in inputs[0]:
                    inputs = load_file(inputs[0])
                elif len(inputs) == 1 and inputs[0] == "":
                    inputs = []
            if isinstance(inputs, list):
                inputs = {"inputs": inputs}  # OLD format provided directly
            # consider possible ambiguity if literal CWL input is named 'inputs'
            # - if value of 'inputs' is an object, it can collide with 'OGC' schema,
            #   unless 'value/href' are present or their sub-dict don't have CWL 'class'
            # - if value of 'inputs' is an array, it can collide with 'OLD' schema,
            #   unless 'value/href' (and 'id' technically) are present
            values = inputs.get("inputs", null)
            if (
                values is null or
                values is not null and (
                    (isinstance(values, dict) and get_any_value(values) is null and "class" not in values) or
                    (isinstance(values, list) and all(isinstance(v, dict) and get_any_value(v) is null for v in values))
                )
            ):
                values = cwl2json_input_values(inputs)
            if values is null:
                raise ValueError("Input values parsed as null. Could not properly detect employed schema.")
        except Exception as exc:
            return OperationResult(False, f"Failed inputs parsing with error: [{exc!s}].", inputs)
        return values

    # FIXME: support sync (https://github.com/crim-ca/weaver/issues/247)
    # :param execute_async:
    #   Execute the process asynchronously (user must call :meth:`monitor` themselves,
    #   or synchronously where monitoring is done automatically until completion before returning.
    def execute(self, process_id, inputs=None, monitor=False, timeout=None, interval=None, url=None):
        # type: (str, Optional[Union[str, JSON]], bool, Optional[int], Optional[int], Optional[str]) -> OperationResult
        """
        Execute a :term:`Job` for the specified :term:`Process` with provided inputs.

        When submitting inputs with :term:`OGC API - Processes` schema, top-level ``inputs`` key is expected.
        Under it, either the mapping (key-value) or listing (id,value) representation are accepted.
        If ``inputs`` is not found, the alternative :term:`CWL` will be assumed.

        When submitting inputs with :term:`CWL` *job* schema, plain key-value(s) pairs are expected.
        All values should be provided directly under the key (including arrays), except for ``File``
        type that must include the ``class`` and ``path`` details.

        .. seealso::
            :ref:`proc_op_execute`

        :param process_id: Identifier of the process to execute.
        :param inputs:
            Literal :term:`JSON` or :term:`YAML` contents of the inputs submitted and inserted into the execution body,
            using either the :term:`OGC API - Processes` or :term:`CWL` format, or a file path/URL referring to them.
        :param monitor:
            Automatically perform :term:`Job` execution monitoring until completion or timeout to obtain final results.
            If requested, this operation will become blocking until either the completed status or timeout is reached.
        :param timeout:
            Monitoring timeout (seconds) if requested.
        :param interval:
            Monitoring interval (seconds) between job status polling requests.
        :param url: Instance URL if not already provided during client creation.
        :returns: results of the operation.
        """
        if isinstance(inputs, list) and all(isinstance(item, list) for item in inputs):
            inputs = [items for sub in inputs for items in sub]  # flatten 2D->1D list
        values = self._parse_inputs(inputs)
        if isinstance(values, OperationResult):
            return values
        data = {
            # NOTE: since sync is not yet properly implemented in Weaver, simulate with monitoring after if requested
            # FIXME: support 'sync' (https://github.com/crim-ca/weaver/issues/247)
            "mode": EXECUTE_MODE_ASYNC,
            "inputs": values,
            # FIXME: support 'response: raw' (https://github.com/crim-ca/weaver/issues/376)
            "response": EXECUTE_RESPONSE_DOCUMENT,
            # FIXME: allow omitting 'outputs' (https://github.com/crim-ca/weaver/issues/375)
            # FIXME: allow 'transmissionMode: value/reference' selection (https://github.com/crim-ca/weaver/issues/377)
            "outputs": {}
        }
        # FIXME: since (https://github.com/crim-ca/weaver/issues/375) not implemented, auto-populate all the outputs
        base = self._get_url(url)
        result = self.describe(process_id, url=base)
        if not result.success:
            return OperationResult(False, "Could not obtain process description for execution.",
                                   body=result.body, headers=result.headers, code=result.code, text=result.text)
        outputs = result.body.get("outputs")
        for output_id in outputs:
            # use 'value' to have all outputs reported in body as 'value/href' rather than 'Link' headers
            data["outputs"][output_id] = {"transmissionMode": EXECUTE_TRANSMISSION_MODE_VALUE}

        LOGGER.info("Executing [%s] with inputs:\n%s", process_id, _json2text(inputs))
        path = f"{base}/processes/{process_id}/execution"  # use OGC-API compliant endpoint (not '/jobs')
        resp = request_extra("POST", path, json=data, headers=self._headers, settings=self._settings)
        result = self._parse_result(resp)
        if not monitor or not result.success:
            return result
        # although Weaver returns "jobID" in the body for convenience,
        # employ the "Location" header to be OGC-API compliant
        job_url = resp.headers.get("Location", "")
        time.sleep(1)  # small delay to ensure process execution had a chance to start before monitoring
        return self.monitor(job_url, timeout=timeout, interval=interval)

    def status(self, job_reference, url=None):
        """
        Obtain the status of a :term:`Job`.

        .. seealso::
            :ref:`proc_op_status`

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :returns: retrieved status of the job.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.info("Getting job status: [%s]", job_id)
        resp = request_extra("GET", job_url, headers=self._headers, settings=self._settings)
        return self._parse_result(resp)

    def monitor(self, job_reference, timeout=None, interval=None, wait_for_status=STATUS_SUCCEEDED, url=None):
        # type: (str, Optional[int], Optional[int], str, Optional[str]) -> OperationResult
        """
        Monitor the execution of a :term:`Job` until completion.

        .. seealso::
            :ref:`proc_op_monitor`

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param timeout: timeout (seconds) of maximum wait time for monitoring if completion is not reached.
        :param interval: wait interval (seconds) between polling monitor requests.
        :param wait_for_status: monitor until the requested status is reached (default: job failed or succeeded).
        :param url: Instance URL if not already provided during client creation.
        :return: result of the successful or failed job, or timeout of monitoring process.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        remain = timeout = timeout or self.monitor_timeout
        delta = interval or self.monitor_interval
        LOGGER.info("Monitoring job [%s] for %ss at intervals of %ss.", job_id, timeout, delta)
        once = True
        body = None
        while remain >= 0 or once:
            resp = request_extra("GET", job_url, headers=self._headers, settings=self._settings)
            if resp.status_code != 200:
                return OperationResult(False, "Could not find job with specified reference.", {"job": job_reference})
            body = resp.json()
            status = body.get("status")
            if status == wait_for_status:
                return OperationResult(True, f"Requested job status reached [{wait_for_status}].", body)
            if status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_FINISHED]:
                return OperationResult(False, "Requested job status not reached, but job has finished.", body)
            time.sleep(delta)
            remain -= delta
            once = False
        return OperationResult(False, f"Monitoring timeout reached ({timeout}s). Job did not complete in time.", body)

    def results(self, job_reference, out_dir=None, download=False, url=None):
        # type: (str, Optional[str], bool, Optional[str]) -> OperationResult
        """
        Obtain the results of a successful :term:`Job` execution.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param out_dir: Output directory where to store downloaded files if requested (default: CURDIR/JobID/<outputs>).
        :param download: Download any file reference found within results (CAUTION: could transfer lots of data!).
        :param url: Instance URL if not already provided during client creation.
        :returns: Result details and local paths if downloaded.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        status = self.status(job_url)
        if not status.success:
            return OperationResult(False, "Cannot process results from incomplete or failed job.", status.body)
        # use results endpoint instead of outputs to be OGC-API compliant, should be able to target non-Weaver instance
        # with this endpoint, outputs IDs are directly at the root of the body
        result_url = f"{job_url}/results"
        resp = request_extra("GET", result_url, headers=self._headers, settings=self._settings)
        res_out = self._parse_result(resp)
        outputs = res_out.body
        if not res_out.success or not isinstance(res_out.body, dict):
            return OperationResult(False, "Could not retrieve any output results from job.", outputs)
        if not download:
            return OperationResult(True, "Listing job results.", outputs)

        # download file results
        if not any("href" in value for value in outputs.values()):
            return OperationResult(False, "Outputs were found but none are downloadable (only raw values?).", outputs)
        if not out_dir:
            out_dir = os.path.join(os.path.realpath(os.path.curdir), job_id)
        os.makedirs(out_dir, exist_ok=True)
        LOGGER.info("Will store job [%s] output results in [%s]", job_id, out_dir)
        for output, value in outputs.items():
            is_list = True
            if not isinstance(value, list):
                value = [value]
                is_list = False
            for i, item in enumerate(value):
                if "href" in item:
                    file_path = fetch_file(item["href"], out_dir, link=False)
                    if is_list:
                        outputs[output][i]["path"] = file_path
                    else:
                        outputs[output]["path"] = file_path
        return OperationResult(True, "Retrieved job results.", outputs)

    def dismiss(self, job_reference, url=None):
        """
        Dismiss pending or running :term:`Job`, or clear result artifacts from a completed :term:`Job`.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :returns: Obtained result from the operation.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.debug("Dismissing job: [%s]", job_id)
        resp = request_extra("DELETE", job_url, headers=self._headers, settings=self._settings)
        return self._parse_result(resp)


def setup_logger_from_options(logger, args):  # pragma: no cover
    # type: (logging.Logger, argparse.Namespace) -> None
    """
    Uses argument parser options to setup logging level from specified flags.

    Setup both the specific CLI logger that is provided and the top-level package logger.
    """
    if args.log_level:
        logger.setLevel(logging.getLevelName(args.log_level.upper()))
    elif args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.verbose:
        logger.setLevel(logging.INFO)
    elif args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)
    setup_loggers({}, force_stdout=args.stdout)
    if logger.name != __meta__.__name__:
        setup_logger_from_options(logging.getLogger(__meta__.__name__), args)


def make_logging_options(parser):
    # type: (argparse.ArgumentParser) -> None
    """
    Defines argument parser options for logging operations.
    """
    log_title = "Logging Options"
    log_desc = "Options that configure output logging."
    log_opts = parser.add_argument_group(title=log_title, description=log_desc)
    log_opts.add_argument("--stdout", action="store_true", help="Enforce logging to stdout for display in console.")
    log_opts.add_argument("--log", "--log-file", help="Output file to write generated logs.")
    lvl_opts = log_opts.add_mutually_exclusive_group()
    lvl_opts.title = log_title
    lvl_opts.description = log_desc
    lvl_opts.add_argument("--quiet", "-q", action="store_true", help="Do not output anything else than error.")
    lvl_opts.add_argument("--debug", "-d", action="store_true", help="Enable extra debug logging.")
    lvl_opts.add_argument("--verbose", "-v", action="store_true", help="Output informative logging details.")
    lvl_names = ["debug", "info", "warn", "error"]
    lvl_opts.add_argument("--log-level", "-l", dest="log_level",
                          choices=list(sorted(lvl_names + [lvl.upper() for lvl in lvl_names])),
                          help="Explicit log level to employ (default: %(default)s).")


def add_url_param(parser, required=True):
    # type: (argparse.ArgumentParser, bool) -> None
    args = ["url"] if required else ["-u", "--url"]
    parser.add_argument(*args, metavar="URL", help="URL of the instance to run operations.")


def add_process_param(parser, description=None, required=True):
    # type: (argparse.ArgumentParser, Optional[str], bool) -> None
    operation = parser.prog.split(" ")[-1]
    parser.add_argument(
        "-p", "--id", "--process", dest="process_id", required=required,
        help=description if description else f"Identifier of the process to run {operation} operation."
    )


def add_job_ref_param(parser):
    # type: (argparse.ArgumentParser) -> None
    operation = parser.prog.split(" ")[-1]
    parser.add_argument(
        "-j", "--job", dest="job_reference", required=True,
        help=f"Job URL or UUID to run {operation} operation. "
             "If full Job URL is provided, the instance ``--url`` parameter can be omitted."
    )


def add_timeout_param(parser):
    # type: (argparse.ArgumentParser) -> None
    parser.add_argument(
        "-T", "--timeout", dest="timeout", type=int, default=WeaverClient.monitor_timeout,
        help="Wait timeout (seconds) of the maximum monitoring duration of the job execution (default: %(default)ss). "
             "If this timeout is reached but job is still running, another call directly to the monitoring operation "
             "can be done to resume monitoring. The job execution itself will not stop in case of timeout."
    )
    parser.add_argument(
        "-W", "--wait", "--interval", dest="interval", type=int, default=WeaverClient.monitor_interval,
        help="Wait interval (seconds) between each job status polling during monitoring (default: %(default)ss)."
    )


def set_parser_sections(parser):
    # type: (argparse.ArgumentParser) -> None
    parser._optionals.title = OPTIONAL_ARGS_TITLE
    parser._positionals.title = REQUIRED_ARGS_TITLE


class InputsFormatter(argparse.HelpFormatter):
    # pragma: no cover  # somehow marked not covered, but functionality covered by 'test_execute_help_details'
    def _format_action(self, action):
        """
        Override the returned help message with available options and shortcuts for email template selection.
        """
        if action.dest != "inputs":
            return super(InputsFormatter, self)._format_action(action)
        indent_size = min(self._action_max_length + 2, self._max_help_position)  # see _format_action
        indent_text = indent_size * " "
        sep = "\n\n"
        paragraphs = action.help.split(sep)
        last_index = len(paragraphs) - 1
        help_text = ""
        for i, block in enumerate(paragraphs):
            # process each paragraph individually so it fills the available width space
            # then remove option information line to keep only formatted text and indent the line for next one
            action.help = block
            help_block = super(InputsFormatter, self)._format_action(action)
            option_idx = help_block.find("\n") if i else 0  # leave option detail on first paragraph
            help_space = (indent_text if i != last_index else sep)  # don't indent last, next param has it already
            help_text += help_block[option_idx:] + help_space
        return help_text


class SubArgumentParserFixedMutexGroups(argparse.ArgumentParser):
    """
    Patch incorrectly handled mutually exclusive groups sections in subparsers.

    .. seealso::
        - https://bugs.python.org/issue43259
        - https://bugs.python.org/issue16807
    """
    def _add_container_actions(self, container):
        # pylint: disable=W0212
        groups = container._mutually_exclusive_groups
        tmp_mutex_groups = container._mutually_exclusive_groups
        container._mutually_exclusive_groups = []
        super(SubArgumentParserFixedMutexGroups, self)._add_container_actions(container)
        for group in groups:
            mutex_group = self.add_mutually_exclusive_group(required=group.required)
            for action in group._group_actions:
                mutex_group._group_actions.append(action)
        container._mutually_exclusive_groups = tmp_mutex_groups


def make_parser():
    # type: () -> argparse.ArgumentParser
    """
    Generate the CLI parser.

    .. note::
        Instead of employing :class:`argparse.ArgumentParser` instances returned
        by :meth:`argparse._SubParsersAction.add_parser`, distinct :class:`argparse.ArgumentParser` instances are
        created for each operation an then  merged back by ourselves as subparsers under the main parser.
        This provides more flexibility in arguments passed down and resolves, amongst other things, incorrect
        handling of exclusive argument groups and their grouping under corresponding section titles.
    """
    # generic logging parser to pass down to each operation
    # this allows providing logging options to any of them
    log_parser = argparse.ArgumentParser(add_help=False)
    make_logging_options(log_parser)

    desc = "Run {} operations.".format(__meta__.__title__)
    parser = SubArgumentParserFixedMutexGroups(prog=__meta__.__name__, description=desc, parents=[log_parser])
    set_parser_sections(parser)
    parser.add_argument(
        "--version", "-V",
        action="version",
        version="%(prog)s {}".format(__meta__.__version__),
        help="Display the version of the package."
    )
    ops_parsers = parser.add_subparsers(
        title="Operations", dest="operation",
        description="Name of the operation to run."
    )

    op_deploy = argparse.ArgumentParser(
        "deploy",
        description="Deploy a process.",
    )
    set_parser_sections(op_deploy)
    add_url_param(op_deploy)
    add_process_param(op_deploy, required=False, description=(
        "Process identifier for deployment. If no ``--body`` is provided, this is required. "
        "Otherwise, provided value overrides the corresponding ID in the body."
    ))
    op_deploy.add_argument(
        "-b", "--body", dest="body",
        help="Deployment body directly provided. Allows both JSON and YAML format when using file reference. "
             "If provided in combination with process ID or CWL, they will override the corresponding content. "
             "Can be provided either with a local file, an URL or literal string contents formatted as JSON."
    )
    op_deploy_app_pkg = op_deploy.add_mutually_exclusive_group()
    op_deploy_app_pkg.add_argument(
        "--cwl", dest="cwl",
        help="Application Package of the process defined using Common Workflow Language (CWL) as JSON or YAML "
             "format when provided by file reference. File reference can be a local file or URL location. "
             "Can also be provided as literal string contents formatted as JSON. "
             "Provided contents will be inserted into an automatically generated request deploy body if none was "
             "specified with ``--body`` option (note: ``--process`` must be specified instead in that case). "
             "Otherwise, it will override the appropriate execution unit section within the provided deploy body."
    )
    op_deploy_app_pkg.add_argument(
        "--wps", dest="wps",
        help="Reference URL to a specific process under a Web Processing Service (WPS) to package as OGC-API Process."
    )
    op_deploy_token = op_deploy.add_mutually_exclusive_group()
    op_deploy_token.add_argument(
        "-t", "--token", dest="token",
        help="Authentication token to retrieve a Docker image reference from a private registry during execution."
    )
    op_deploy_creds = op_deploy_token.add_argument_group("Credentials")
    op_deploy_creds.add_argument(
        "-U", "--username", dest="username",
        help="Username to compute the authentication token for Docker image retrieval from a private registry."
    )
    op_deploy_creds.add_argument(
        "-P", "--password", dest="password",
        help="Password to compute the authentication token for Docker image retrieval from a private registry."
    )
    op_deploy.add_argument(
        "-D", "--delete", "--undeploy", dest="undeploy", action="store_true",
        help="Perform undeploy step as applicable prior to deployment to avoid conflict with exiting process."
    )

    op_undeploy = argparse.ArgumentParser(
        "undeploy",
        description="Undeploy an existing process.",
    )
    set_parser_sections(op_deploy)
    add_url_param(op_undeploy)
    add_process_param(op_undeploy)

    op_capabilities = argparse.ArgumentParser(
        "capabilities",
        description="List available processes.",
    )
    set_parser_sections(op_deploy)
    add_url_param(op_capabilities)

    op_describe = argparse.ArgumentParser(
        "describe",
        description="Obtain an existing process description.",
    )
    set_parser_sections(op_deploy)
    add_url_param(op_describe)
    add_process_param(op_describe)

    op_execute = argparse.ArgumentParser(
        "execute",
        description="Submit a job execution for an existing process.",
        formatter_class=InputsFormatter,
    )
    set_parser_sections(op_deploy)
    add_url_param(op_execute)
    add_process_param(op_execute)
    op_execute.add_argument(
        "-I", "--inputs", dest="inputs",
        required=True, nargs=1, action="append",  # collect max 1 item per '-I', but allow many '-I'
        # note: below is formatted using 'InputsFormatter' with detected paragraphs
        help=inspect.cleandoc("""
            Literal input definitions, or a file path or URL reference to JSON or YAML
            contents defining job inputs with OGC-API or CWL schema. This parameter is required.

            To provide inputs using a file reference, refer to relevant CWL Job schema or API request schema
            for selected format. Both mapping and listing formats are supported.

            To execute a process without any inputs (e.g.: using its defaults),
            supply an explicit empty input (i.e.: -I "" or loaded from file as {}).

            To provide inputs using literal command-line definitions, inputs should be specified using '<id>=<value>'
            convention, with distinct -I options for each applicable input value.

            Values that require other type than string to be converted for job submission can include the type
            following the ID using a colon separator (i.e.: '<id>:<type>=<value>'). For example, an integer could be
            specified as follows: 'number:int=1' while a floating point would be: 'number:float=1.23'.

            File references (href) should be specified using 'File' as the type (i.e.: 'input:File=http://...').

            Array input (maxOccurs > 1) should be specified using semicolon (;) separated values.
            The type of an item of this array can also be provided (i.e.: 'array:int=1;2;3').

            Example: -I message='Hello Weaver' -I value:int=1234
        """)
    )
    # FIXME: support sync (https://github.com/crim-ca/weaver/issues/247)
    # op_execute.add_argument(
    #     "-A", "--async", dest="execute_async",
    #     help=""
    # )
    op_execute.add_argument(
        "-M", "--monitor", dest="monitor", action="store_true",
        help="Automatically perform the monitoring operation following job submission to retrieve final results. "
             "If not requested, the created job status location is directly returned."
    )
    add_timeout_param(op_execute)

    op_dismiss = argparse.ArgumentParser(
        "dismiss",
        description="Dismiss a pending or running job, or wipe any finished job results.",
    )
    set_parser_sections(op_deploy)
    add_url_param(op_dismiss, required=False)
    add_job_ref_param(op_dismiss)

    op_monitor = argparse.ArgumentParser(
        "monitor",
        description="Monitor a pending or running job execution until completion or up to a maximum wait time."
    )
    add_url_param(op_monitor, required=False)
    add_job_ref_param(op_monitor)
    add_timeout_param(op_monitor)

    op_status = argparse.ArgumentParser(
        "status",
        description=(
            "Obtain the status of a job using a reference UUID or URL. "
            "This is equivalent to doing a single-shot 'monitor' operation without any pooling or retries."
        ),
    )
    set_parser_sections(op_deploy)
    add_url_param(op_status, required=False)
    add_job_ref_param(op_status)

    op_results = argparse.ArgumentParser(
        "results",
        description=(
            "Obtain the output results description of a job. "
            "This operation can also download them from the remote server if requested."
        ),
    )
    set_parser_sections(op_deploy)
    add_url_param(op_results, required=False)
    add_job_ref_param(op_results)
    op_results.add_argument(
        "-D", "--download", dest="download", action="store_true",
        help="Download all found job results file references to output location. "
             "If not requested, the operation simply displays the job results (default: %(default)s)."
    )
    op_results.add_argument(
        "-O", "--outdir", dest="out_dir",
        help="Output directory where to store downloaded files from job results if requested "
             "(default: ${CURDIR}/{JobID}/<outputs.files>)."
    )

    operations = [
        op_deploy,
        op_undeploy,
        op_capabilities,
        op_describe,
        op_execute,
        op_monitor,
        op_dismiss,
        op_results,
        op_status,
    ]
    aliases = {
        "processes": op_capabilities
    }
    for op_parser in operations:
        op_aliases = [alias for alias, op_alias in aliases.items() if op_alias is op_parser]
        # add help disabled otherwise conflicts with main parser help
        sub_op_parser = ops_parsers.add_parser(
            op_parser.prog, aliases=op_aliases, parents=[log_parser, op_parser],
            add_help=False, help=op_parser.description,
            formatter_class=op_parser.formatter_class,
            description=op_parser.description, usage=op_parser.usage
        )
        set_parser_sections(sub_op_parser)
    return parser


def main(*args):
    parser = make_parser()
    ns = parser.parse_args(args=args or None)
    setup_logger_from_options(LOGGER, ns)
    kwargs = vars(ns)
    # remove logging params not known by operations
    for param in ["stdout", "log", "log_level", "quiet", "debug", "verbose"]:
        kwargs.pop(param, None)
    oper = kwargs.pop("operation", None)
    LOGGER.debug("Requested operation: [%s]", oper)
    if not oper or oper not in dir(WeaverClient):
        parser.print_help()
        return 0
    url = kwargs.pop("url", None)
    client = WeaverClient(url)
    result = getattr(client, oper)(**kwargs)
    if result.success:
        LOGGER.info("%s successful. %s", oper.title(), result.message)
        print(result.text)  # use print in case logger disabled or level error/warn
        return 0
    LOGGER.error("%s failed. %s", oper.title(), result.message)
    print(result.text)
    return -1


if __name__ == "__main__":
    sys.exit(main())
