import base64
import copy
import json
import logging
import os
import sys
from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from weaver import __meta__
from weaver.exceptions import PackageRegistrationError
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.processes.convert import cwl2json_input_values
from weaver.processes.wps_package import get_process_definition
from weaver.utils import load_file, request_extra, setup_loggers

if TYPE_CHECKING:
    from typing import Optional, Tuple, Union

    from requests import Response

    from weaver.typedefs import CWL, HeadersType, JSON

    OperationResult = Tuple[bool, str, Union[str, JSON]]

LOGGER = logging.getLogger(__name__)


class WeaverClient(object):
    def __init__(self, url):
        # type: (str) -> None
        parsed = urlparse("http://" + url if not url.startswith("http") else url)
        parsed_netloc_path = f"{parsed.netloc}{parsed.path}".replace("//", "/")
        parsed_url = f"{parsed.scheme}://{parsed_netloc_path}"
        self._url = parsed_url.rsplit("/", 1)[0] if parsed_url.endswith("/") else parsed_url
        LOGGER.debug("Using URL: [%s]", self._url)
        self._headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        self._settings = {}  # FIXME: load from INI, overrides as input (cumul '--setting weaver.x=value') ?

    @staticmethod
    def _parse_result(response):
        # type: (Response) -> OperationResult
        try:
            body = response.json()
            msg = body.get("description", body.get("message", "undefined"))
            if response.status_code >= 400 and not msg:
                msg = body.get("error", body.get("exception", "unknown"))
            body = WeaverClient._json2text(body)
        except Exception:  # noqa
            body = response.text
            msg = "Could not parse body."
        return True, msg, body

    @staticmethod
    def _json2text(data):
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _parse_deploy_body(self, body, process_id):
        # type: (Optional[Union[JSON, str]], Optional[str]) -> OperationResult
        data = {}  # type: JSON
        try:
            if body:
                if isinstance(body, str) and (body.startswith("http") or os.path.isfile(body)):
                    data = load_file(body)
                elif isinstance(body, dict):
                    data = body
                else:
                    return False, "Cannot load badly formed body. Deploy JSON object or file reference expected.", body
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
        except (ValueError, TypeError) as exc:
            return False, "Failed resolution of body definition: [{exc!s}]", body
        return True, "", data

    def _parse_auth_token(self, token, username, password):
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
        :returns: results of the operation.
        """
        ok, msg, data = self._parse_deploy_body()
        if not ok:
            return False, msg, data
        headers = copy.deepcopy(self._headers)
        headers.update(self._parse_auth_token(token, username, password))
        try:
            if isinstance(cwl, str) or isinstance(wps, str):
                LOGGER.debug("Override loaded CWL into provided/loaded body.", process_id)
                proc = get_process_definition({}, reference=cwl or wps, headers=headers)  # validate
                data["executionUnit"] = [{"unit": proc["package"]}]
            elif isinstance(cwl, dict):
                LOGGER.debug("Override provided CWL into provided/loaded body.", process_id)
                get_process_definition({}, package=cwl, headers=headers)  # validate
                data["executionUnit"] = [{"unit": cwl}]
        except PackageRegistrationError as exc:
            message = f"Failed resolution of package definition: [{exc!s}]"
            return False, message, cwl
        path = f"{self._url}/processes"
        resp = request_extra("POST", path, data=data, headers=headers, settings=self._settings)
        return self._parse_result(resp)

    def describe(self, process_id):
        """
        Describe the specified :term:`Process`.
        """
        path = f"{self._url}/processes/{process_id}"
        resp = request_extra("GET", path, headers=self._headers, settings=self._settings)
        return self._parse_result(resp)

    def execute(self, process_id, inputs=None, inputs_file=None, inputs_cwl=False, execute_async=True):
        """
        Execute a :term:`Job` for the specified :term:`Process` with provided inputs.

        :param process_id: Desired process identifier.xxx
        :param inputs: Literal :term:`JSON` contents of the inputs inputs submitted in the execution body.
        :param inputs_file: Path to :term:`YAML` or :term:`JSON` file of inputs submitted in the execution body.
        :param inputs_cwl: Indicate if the inputs are formatted as :term:`CWL`. Otherwise, OGC-API schema is expected.
        :param execute_async:
            Execute the process asynchronously (user must call :meth:`monitor` themselves,
            or synchronously were monitoring is done automatically until completion before returning.
        :returns: results of the operation.
        """
        if inputs_file:
            inputs = load_file(inputs_file)
        if not inputs:
            return False, "No inputs provided.", {}
        if inputs_cwl:
            inputs = cwl2json_input_values(inputs)

        data = {
            "inputs": inputs
        }

        LOGGER.info("Executing [%s] with inputs:\n%s", self._json2text(inputs))
        path = f"{self._url}/processes/{process_id}"
        resp = request_extra("GET", path, data=data, headers=self._headers, settings=self._settings)
        success, _, _ = self._parse_result(resp)

        return

    def status(self, job_id):
        """
        Obtain the status of a :term:`Job`.
        """

    def monitor(self):
        """
        Monitor the execution of a :term:`Job` until completion.
        """


def setup_logger_from_options(logger, args):  # pragma: no cover
    # type: (logging.Logger, Namespace) -> None
    """
    Uses argument parser options to setup logging level from specified flags.

    Setup both the specific CLI logger that is provided and the generic `magpie` logger.
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
    if logger.name != "magpie":
        setup_logger_from_options(logging.getLogger("magpie"), args)


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


def make_parser():
    # type: () -> ArgumentParser
    """
    Generate the CLI parser.
    """
    parser = ArgumentParser(description="Execute {} operations.".format(__meta__.__title__))
    parser.add_argument("--version", "-V", action="version", version="%(prog)s {}".format(__meta__.__version__),
                        help="Display the version of the package.")
    parser.add_argument("url", help="URL of the instance to run operations.")
    ops_parsers = parser.add_subparsers(title="Operation", dest="operation",
                                        description="Name of the operation to execute.")

    op_deploy = ops_parsers.add_parser("deploy", help="Deploy a process.")
    op_deploy.add_argument("--cwl", "--package", help="File or URL of the CWL Application Package to deploy.")
    op_deploy_proc = op_deploy.add_mutually_exclusive_group()
    op_deploy_proc.add_argument("--id", "--name", dest="process_id", help="Process identifier for deployment.")
    op_deploy_proc.add_argument("-b", "--body", help="")

    op_describe = ops_parsers.add_parser("describe")
    # FIXME: params
    op_execute = ops_parsers.add_parser("execute")
    # FIXME: params
    op_status = ops_parsers.add_parser("status")
    # FIXME: params
    op_result = ops_parsers.add_parser("result")
    # FIXME: params

    make_logging_options(parser)
    return parser


def main(*args):
    parser = make_parser()
    ns = parser.parse_args(args=args)
    setup_logger_from_options(LOGGER, ns)
    args = vars(ns)
    op = args.pop("operation", None)
    if not op or op not in dir(WeaverClient):
        parser.print_help()
        return 0
    url = args.pop("url", None)
    client = WeaverClient(url)
    result = getattr(client, op)(*args)
    status, message, data = result
    if status:
        LOGGER.info("%s successful. %s", op.title(), message)
        print(data)
        return 0
    LOGGER.error("%s failed. %s\n%s", op.title(), message, data)
    return -1


if __name__ == "__main__":
    sys.exit(main())
