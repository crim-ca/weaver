import base64
import copy
import json
import logging
import os
import sys
import time
from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from weaver import __meta__
from weaver.datatype import AutoBase
from weaver.exceptions import PackageRegistrationError
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_RESPONSE_DOCUMENT, EXECUTE_TRANSMISSION_MODE_VALUE
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.processes.convert import cwl2json_input_values
from weaver.processes.wps_package import get_process_definition
from weaver.status import JOB_STATUS_CATEGORIES, JOB_STATUS_CATEGORY_FINISHED, STATUS_SUCCEEDED
from weaver.utils import fetch_file, get_any_id, get_any_value, load_file, null, request_extra, setup_loggers
from weaver.visibility import VISIBILITY_PUBLIC

if TYPE_CHECKING:
    from typing import Any, Optional, Tuple, Union

    from requests import Response

    from weaver.typedefs import CWL, HeadersType, JSON

LOGGER = logging.getLogger(__name__)


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
    text = ""           # type: Optional[str]

    def __init__(self,
                 success=None,  # type: Optional[bool]
                 message=None,  # type: Optional[str]
                 body=None,     # type: Optional[Union[str, JSON]]
                 headers=None,  # type: Optional[HeadersType]
                 text=None,     # type: Optional[str]
                 **kwargs,      # type: Any
                 ):             # type: (...) -> None
        super(OperationResult, self).__init__(**kwargs)
        self.success = success
        self.message = message
        self.headers = headers
        self.body = body
        self.text = text


class WeaverClient(object):
    """
    Client that handles common HTTP requests with a `Weaver` or similar :term:`OGC-API - Processes` instance.
    """
    # default configuration parameters, overridable by corresponding method parameters
    monitor_timeout = 60    # maximum delay to wait for job completion
    monitor_delta = 5       # interval between monitor pooling job status requests

    def __init__(self, url=None):
        # type: (Optional[str]) -> None
        if url:
            self._url = self._parse_url(url)
            LOGGER.debug("Using URL: [%s]", self._url)
        else:
            self._url = None
            LOGGER.warning("No URL provided. All operations must provide it directly or through another parameter!")
        self._headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        self._settings = {}  # FIXME: load from INI, overrides as input (cumul arg '--setting weaver.x=value') ?

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
    def _parse_result(response):
        # type: (Response) -> OperationResult
        hdr = dict(response.headers)
        success = False
        try:
            body = response.json()
            msg = body.get("description", body.get("message", "undefined"))
            if response.status_code >= 400:
                if not msg:
                    msg = body.get("error", body.get("exception", "unknown"))
            else:
                success = True
            text = WeaverClient._json2text(body)
        except Exception:  # noqa
            text = body = response.text
            msg = "Could not parse body."
        return OperationResult(success, msg, body, hdr, text=text)

    @staticmethod
    def _json2text(data):
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def _parse_deploy_body(body, process_id):
        # type: (Optional[Union[JSON, str]], Optional[str]) -> OperationResult
        data = {}  # type: JSON
        try:
            if body:
                if isinstance(body, str) and (body.startswith("http") or os.path.isfile(body)):
                    data = load_file(body)
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
        except (ValueError, TypeError) as exc:
            return OperationResult(False, f"Failed resolution of body definition: [{exc!s}]", body)
        return OperationResult(True, "", data)

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
               url=None,            # type: Optional[str]
               ):                   # type: (...) -> OperationResult
        """
        Deploy a new :term:`Process` with specified metadata and reference to an :term:`Application Package`.

        The referenced :term:`Application Package` must be one of:
        - :term:`CWL` body, local file or URL in :term:`JSON` or :term:`YAML` format
        - :term:`WPS` process URL with :term:`XML` response
        - :term:`WPS-REST` process URL with :term:`JSON` response
        - :term:`OGC-API - Processes` process URL with :term:`JSON` response

        If the reference is resolved to be a :term:`Workflow`, all its underlying :term:`Process` steps must be
        available under the same URL that this client was initialized with.

        :param process_id:
            Desired process identifier.
            Can be omitted if already provided in body contents or file.
        :param body:
            Literal :term:`JSON` contents forming the request body, or file path/URL to :term:`YAML` or :term:`JSON`
            contents of the request body. Can be updated with other provided parameters.
        :param cwl:
            Literal :term:`JSON` or :term:`YAML` contents, or file path/URL with contents of the :term:`CWL` definition
            of the :term:`Application package` to be inserted into the body.
        :param wps:
            URL to an existing :term:`WPS` process (WPS-1/2 or WPS-REST/OGC-API).
        :param token:
            Authentication token for accessing private Docker registry if :term:`CWL` refers to such image.
        :param username:
            Username to form the authentication token to a private Docker registry.
        :param password:
            Password to form the authentication token to a private Docker registry.
        :param url:
            Instance URL if not already provided during client creation.
        :returns: results of the operation.
        """
        success, msg, data = self._parse_deploy_body(body, process_id)
        if not success:
            return OperationResult(False, msg, data)
        headers = copy.deepcopy(self._headers)
        headers.update(self._parse_auth_token(token, username, password))
        try:
            if isinstance(cwl, str) or isinstance(wps, str):
                LOGGER.debug("Override loaded CWL into provided/loaded body for process: [%s]", process_id)
                proc = get_process_definition({}, reference=cwl or wps, headers=headers)  # validate
                data["executionUnit"] = [{"unit": proc["package"]}]
            elif isinstance(cwl, dict):
                LOGGER.debug("Override provided CWL into provided/loaded body for process: [%s]", process_id)
                get_process_definition({}, package=cwl, headers=headers)  # validate
                data["executionUnit"] = [{"unit": cwl}]
        except PackageRegistrationError as exc:
            message = f"Failed resolution of package definition: [{exc!s}]"
            return OperationResult(False, message, cwl)
        base = self._get_url(url)
        path = f"{base}/processes"
        resp = request_extra("POST", path, data=data, headers=headers, settings=self._settings)
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

    def describe(self, process_id, url=None):
        # type: (str, Optional[str]) -> OperationResult
        """
        Describe the specified :term:`Process`.

        :param process_id: Identifier of the process to describe.
        :param url: Instance URL if not already provided during client creation.
        """
        base = self._get_url(url)
        path = f"{base}/processes/{process_id}"
        resp = request_extra("GET", path, headers=self._headers, settings=self._settings)
        return self._parse_result(resp)

    # FIXME: support sync (https://github.com/crim-ca/weaver/issues/247)
    # :param execute_async:
    #   Execute the process asynchronously (user must call :meth:`monitor` themselves,
    #   or synchronously were monitoring is done automatically until completion before returning.
    def execute(self, process_id, inputs=None, monitor=False, timeout=None, url=None):
        # type: (str, Optional[Union[str, JSON]], bool, Optional[int], Optional[str]) -> OperationResult
        """
        Execute a :term:`Job` for the specified :term:`Process` with provided inputs.

        When submitting inputs with :term:`OGC-API - Processes` schema, top-level ``inputs`` key is expected.
        Under it, either the mapping (key-value) or listing (id,value) representation are accepted.
        If ``inputs`` is not found, the alternative :term:`CWL` will be assumed.

        When submitting inputs with :term:`CWL` *job* schema, plain key-value(s) pairs are expected.
        All values should be provided directly under the key (including arrays), except for ``File``
        type that must include the ``class`` and ``path`` details.

        :param process_id: Identifier of the process to execute.
        :param inputs:
            Literal :term:`JSON` or :term:`YAML` contents of the inputs submitted and inserted into the execution body,
            using either the :term:`OGC-API - Processes` or :term:`CWL` format, or a file path/URL referring to them.
        :param monitor:
            Automatically perform :term:`Job` execution monitoring until completion or timeout to obtain final results.
            If requested, this operation will become blocking until either the completed status or timeout is reached.
        :param timeout:
            Monitoring timeout (seconds) if requested.
        :param url: Instance URL if not already provided during client creation.
        :returns: results of the operation.
        """
        if isinstance(inputs, str):
            inputs = load_file(inputs)
        if not inputs or not isinstance(inputs, (dict, list)):
            return OperationResult(False, "No inputs or invalid schema provided.", inputs)
        if isinstance(inputs, list):  # OLD format provided directly
            inputs = {"inputs": inputs}
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
            return result
        outputs = result.body.get("outputs")
        for output_id in outputs:
            # use 'value' to have all outputs reported in body as 'value/href' rather than 'Link' headers
            data["outputs"][output_id] = {"transmissionMode": EXECUTE_TRANSMISSION_MODE_VALUE}

        LOGGER.info("Executing [%s] with inputs:\n%s", process_id, self._json2text(inputs))
        path = f"{base}/processes/{process_id}/execution"  # use OGC-API compliant endpoint (not '/jobs')
        resp = request_extra("POST", path, data=data, headers=self._headers, settings=self._settings)
        result = self._parse_result(resp)
        if not monitor or not result.success:
            return result
        # although Weaver returns "jobID" in the body for convenience,
        # employ the "Location" header to be OGC-API compliant
        job_url = resp.headers.get("Location", "")
        time.sleep(1)  # small delay to ensure process execution had a chance to start before monitoring
        return self.monitor(job_url, timeout=timeout)

    def status(self, job_reference, url=None):
        """
        Obtain the status of a :term:`Job`.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :returns: retrieved status of the job.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.info("Getting job status: [%s]", job_id)
        resp = request_extra("GET", job_url, headers=self._headers)
        return self._parse_result(resp)

    def monitor(self, job_reference, timeout=None, delta=None, wait_for_status=STATUS_SUCCEEDED, url=None):
        # type: (str, Optional[int], Optional[int], str, Optional[str]) -> OperationResult
        """
        Monitor the execution of a :term:`Job` until completion.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param timeout: timeout (seconds) of monitoring until completion or abort.
        :param delta: interval (seconds) between polling monitor requests.
        :param wait_for_status: monitor until the requested status is reached (default: job failed or succeeded).
        :param url: Instance URL if not already provided during client creation.
        :return: result of the successful or failed job, or timeout of monitoring process.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        remain = timeout = timeout or self.monitor_timeout
        delta = delta or self.monitor_delta
        LOGGER.info("Monitoring job [%s] for %ss at intervals of %ss.", job_id, timeout, delta)
        once = True
        body = None
        while remain >= 0 or once:
            resp = request_extra("GET", job_url, headers=self._headers)
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
        resp = request_extra("GET", result_url, headers=self._headers)
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


def setup_logger_from_options(logger, args):  # pragma: no cover
    # type: (logging.Logger, Namespace) -> None
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
    # type: (ArgumentParser) -> None
    """
    Defines argument parser options for logging operations.
    """
    log_opts = parser.add_argument_group(title="Logging Options", description="Options that configure output logging.")
    log_opts.add_argument("--stdout", action="store_true", help="Enforce logging to stdout for display in console.")
    log_opts.add_argument("--log", "--log-file", help="Output file to write generated logs.")
    lvl_opts = log_opts.add_mutually_exclusive_group()
    lvl_opts.add_argument("--quiet", "-q", action="store_true", help="Do not output anything else than error.")
    lvl_opts.add_argument("--debug", "-d", action="store_true", help="Enable extra debug logging.")
    lvl_opts.add_argument("--verbose", "-v", action="store_true", help="Output informative logging details.")
    lvl_names = ["debug", "info", "warn", "error"]
    lvl_opts.add_argument("--log-level", "-l", dest="log_level",
                          choices=list(sorted(lvl_names + [lvl.upper() for lvl in lvl_names])),
                          help="Explicit log level to employ (default: %(default)s).")


def add_url_param(parser, required=True):
    args = ["url"] if required else ["-u", "--url"]
    parser.add_argument(*args, help="URL of the instance to run operations.")


def add_process_param(parser, description=None):
    operation = parser.prog.split(" ")[-1]
    parser.add_argument(
        "-p", "--id", "--process", dest="process_id",
        help=description if description else f"Identifier of the process to run {operation} operation."
    )


def add_job_ref_param(parser):
    operation = parser.prog.split(" ")[-1]
    parser.add_argument(
        "-j", "--job", dest="job_reference",
        help=f"Job URL or UUID to run {operation} operation. "
             "If full URL is provided, the '--url' parameter can be omitted."
    )


def add_timeout_param(parser):
    parser.add_argument(
        "-T", "--timeout", dest="timeout",
        help="Timeout (seconds) of the job execution monitoring. "
             "If this timeout is reached but job is still running, another call directly to the monitoring operation "
             "can be done to resume monitoring. The job execution itself will not stop in case of timeout."
    )


def make_parser():
    # type: () -> ArgumentParser
    """
    Generate the CLI parser.
    """
    parser = ArgumentParser(prog=__meta__.__name__, description="Run {} operations.".format(__meta__.__title__))
    parser._optionals.title = "Optional Arguments"
    parser.add_argument(
        "--version", "-V",
        action="version",
        version="%(prog)s {}".format(__meta__.__version__),
        help="Display the version of the package."
    )
    ops_parsers = parser.add_subparsers(
        title="Operation", dest="operation",
        description="Name of the operation to run."
    )

    op_deploy = ops_parsers.add_parser("deploy", help="Deploy a process.")
    add_url_param(op_deploy)
    add_process_param(op_deploy, description=(
        "Process identifier for deployment. If no body is provided, this is required. "
        "Otherwise, provided value overrides the corresponding ID in the body."
    ))
    op_deploy.add_argument(
        "-b", "--body", dest="body",
        help="Deployment body directly provided. Allows both JSON and YAML format. "
             "If provided in combination with process ID or CWL, they will override the corresponding content."
    )
    op_deploy_app_pkg = op_deploy.add_mutually_exclusive_group()
    op_deploy_app_pkg.add_argument(
        "--cwl", dest="cwl",
        help="Application Package of the process defined using Common Workflow Language (CWL) as JSON or YAML format. "
             "It will be inserted into an automatically generated request deploy body or into the provided one."
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

    op_capabilities = ops_parsers.add_parser("capabilities", aliases=["processes"], help="List available processes.")
    add_url_param(op_capabilities)

    op_describe = ops_parsers.add_parser("describe", help="Obtain an existing process description.")
    add_url_param(op_describe)
    add_process_param(op_describe)

    op_execute = ops_parsers.add_parser("execute", help="Submit a job execution for an existing process.")
    add_url_param(op_execute)
    add_process_param(op_execute)
    # FIXME: support cumulative inputs for convenience? (ex: '-I input=value -I array=1,2 -I other=http://file')
    op_execute.add_argument(
        "-I", "--inputs", dest="inputs",
        help="File path or URL reference to JSON or YAML contents defining job inputs with OGC-API or CWL schema."
    )
    # FIXME: support sync (https://github.com/crim-ca/weaver/issues/247)
    # op_execute.add_argument(
    #     "-A", "--async", dest="execute_async",
    #     help=""
    # )
    op_execute.add_argument(
        "-M", "--monitor", dest="monitor",
        help="Automatically perform the monitoring operation following job submission to retrieve final results. "
             "If not requested, the created job status location is directly returned."
    )
    add_timeout_param(op_execute)

    op_dismiss = ops_parsers.add_parser(
        "dismiss", help="Dismiss a pending or running job, or wipe any finished job results."
    )
    add_url_param(op_dismiss, required=False)
    add_job_ref_param(op_dismiss)

    op_monitor = ops_parsers.add_parser(
        "monitor", help="Monitor a pending or running job execution until completion or timeout is reached."
    )
    add_url_param(op_monitor, required=False)
    add_job_ref_param(op_monitor)
    add_timeout_param(op_monitor)

    op_status = ops_parsers.add_parser("status")
    add_url_param(op_status, required=False)
    add_job_ref_param(op_status)

    op_results = ops_parsers.add_parser("results")
    add_url_param(op_results, required=False)
    add_job_ref_param(op_results)
    op_results.add_argument(
        "-D", "--download", dest="download", default=False,
        help="Download all found job results file references to output location. "
             "If not requested, the operation simply displays the job results (default: %(default)s)."
    )
    op_results.add_argument(
        "-O", "--outdir", dest="out_dir",
        help="Output directory where to store downloaded files from job results if requested "
             "(default: ${CURDIR}/{JobID}/<outputs.files>)."
    )

    make_logging_options(parser)
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
    LOGGER.error("%s failed. %s\n%s", oper.title(), result.message, result.text)
    return -1


if __name__ == "__main__":
    sys.exit(main())
