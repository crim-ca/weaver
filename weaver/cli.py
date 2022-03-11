import re

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
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentType, OutputFormat, get_content_type, get_format
from weaver.processes.constants import ProcessSchema
from weaver.processes.convert import (
    convert_input_values_schema,
    cwl2json_input_values,
    get_field,
    repr2json_input_values
)
from weaver.processes.wps_package import get_process_definition
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory
from weaver.utils import (
    fetch_file,
    fully_qualified_name,
    get_any_id,
    get_any_value,
    get_file_headers,
    load_file,
    null,
    request_extra,
    setup_loggers
)
from weaver.visibility import Visibility
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Dict, Optional, Tuple, Union

    from requests import Response

    # avoid failing sphinx-argparse documentation
    # https://github.com/ashb/sphinx-argparse/issues/7
    try:
        from weaver.typedefs import CWL, JSON, ExecutionInputsMap, HeadersType
    except ImportError:
        CWL = JSON = ExecutionInputsMap = HeadersType = Any  # avoid linter issue
    try:
        from weaver.formats import AnyOutputFormat
        from weaver.processes.constants import ProcessSchemaType
        from weaver.status import StatusType
    except ImportError:
        AnyOutputFormat = str
        ProcessSchemaType = str
        StatusType = str

LOGGER = logging.getLogger(__name__)

OPERATION_ARGS_TITLE = "Operation Arguments"
OPTIONAL_ARGS_TITLE = "Optional Arguments"
REQUIRED_ARGS_TITLE = "Required Arguments"


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
        # type: () -> str
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
            text = OutputFormat.convert(self.body, OutputFormat.JSON_STR)
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
        """
        Initialize the client with predefined parameters.

        :param url: Instance URL to employ for each method call. Must be provided each time if not defined here.
        """
        if url:
            self._url = self._parse_url(url)
            LOGGER.debug("Using URL: [%s]", self._url)
        else:
            self._url = None
            LOGGER.warning("No URL provided. All operations must provide it directly or through another parameter!")
        self._headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
        self._settings = {
            "weaver.request_options": {}
        }  # FIXME: load from INI, overrides as input (cumul arg '--setting weaver.x=value') ?

    def _get_url(self, url):
        # type: (Optional[str]) -> str
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
    def _parse_result(response,             # type: Response
                      body=None,            # type: Optional[JSON]  # override response body
                      message=None,         # type: Optional[str]   # override message/description in contents
                      success=None,         # type: Optional[bool]  # override resolved success
                      show_headers=False,   # type: bool
                      show_links=True,      # type: bool
                      nested_links=None,    # type: Optional[str]
                      output_format=None,   # type: Optional[AnyOutputFormat]
                      ):                    # type: (...) -> OperationResult
        hdr = dict(response.headers)
        _success = False
        try:
            body = body or response.json()
            if not show_links:
                if nested_links:
                    nested = body.get(nested_links, [])
                    if isinstance(nested, list):
                        for item in nested:
                            item.pop("links", None)
                body.pop("links", None)
            msg = message or body.get("description", body.get("message", "undefined"))
            if response.status_code >= 400:
                if not msg:
                    msg = body.get("error", body.get("exception", "unknown"))
            else:
                _success = True
            text = OutputFormat.convert(body, output_format or OutputFormat.JSON_STR, item_root="result")
        except Exception:  # noqa
            text = body = response.text
            msg = "Could not parse body."
        if show_headers:
            s_hdr = OutputFormat.convert({"Headers": hdr}, OutputFormat.YAML)
            text = f"{s_hdr}---\n{text}"
        if success is not None:
            _success = success
        return OperationResult(_success, msg, body, hdr, text=text, code=response.status_code)

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
            data["processDescription"]["process"]["visibility"] = Visibility.PUBLIC  # type: ignore
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
            return {sd.XAuthDockerHeader.name: f"Basic {token}"}
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
               show_links=True,     # type: bool
               show_headers=False,  # type: bool
               output_format=None,  # type: Optional[AnyOutputFormat]
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
        :param wps: URL to an existing :term:`WPS` process (WPS-1/2 or WPS-REST/OGC-API).
        :param token: Authentication token for accessing private Docker registry if :term:`CWL` refers to such image.
        :param username: Username to form the authentication token to a private Docker registry.
        :param password: Password to form the authentication token to a private Docker registry.
        :param undeploy: Perform undeploy as necessary before deployment to avoid conflict with exiting :term:`Process`.
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        result = self._parse_deploy_body(body, process_id)
        if not result.success:
            return result
        req_headers = copy.deepcopy(self._headers)
        req_headers.update(self._parse_auth_token(token, username, password))
        data = result.body
        result = self._parse_deploy_package(data, cwl, wps, process_id, req_headers)
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
        resp = request_extra("POST", path, json=data, show_headers=show_headers, settings=self._settings)
        return self._parse_result(resp, show_links=show_links, show_headers=show_headers, output_format=output_format)

    def undeploy(self, process_id, url=None, show_links=True, show_headers=False, output_format=None):
        # type: (str, Optional[str], bool, bool, Optional[AnyOutputFormat]) -> OperationResult
        """
        Undeploy an existing :term:`Process`.

        :param process_id: Identifier of the process to undeploy.
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/processes/{process_id}"
        resp = request_extra("DELETE", path, headers=self._headers, settings=self._settings)
        return self._parse_result(resp, show_links=show_links, show_headers=show_headers, output_format=output_format)

    def capabilities(self, url=None, show_links=True, show_headers=False, output_format=None):
        # type: (Optional[str], bool, bool, Optional[AnyOutputFormat]) -> OperationResult
        """
        List all available :term:`Process` on the instance.

        .. seealso::
            :ref:`proc_op_getcap`

        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/processes"
        query = {"detail": False}  # not supported by non-Weaver, but save the work if possible
        resp = request_extra("GET", path, params=query, headers=self._headers, settings=self._settings)
        body = resp.json()
        processes = body.get("processes")
        if isinstance(processes, list) and all(isinstance(proc, dict) for proc in processes):
            body = [get_any_id(proc) for proc in processes]
        return self._parse_result(resp, body=body, output_format=output_format,
                                  show_links=show_links, show_headers=show_headers)

    processes = capabilities  # alias
    """
    Alias of :meth:`capabilities` for :term:`Process` listing.
    """

    def describe(self,
                 process_id,                # type: str
                 url=None,                  # type: Optional[str]
                 schema=ProcessSchema.OGC,  # type: Optional[ProcessSchemaType]
                 show_links=True,           # type: bool
                 show_headers=False,        # type: bool
                 output_format=None,        # type: Optional[AnyOutputFormat]
                 ):                         # type: (...) -> OperationResult
        """
        Describe the specified :term:`Process`.

        .. seealso::
            :ref:`proc_op_describe`

        :param process_id: Identifier of the process to describe.
        :param url: Instance URL if not already provided during client creation.
        :param schema: Representation schema of the returned process description.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/processes/{process_id}"
        query = None
        if isinstance(schema, str) and schema.upper() in ProcessSchema.values():
            query = {"schema": schema.upper()}
        resp = request_extra("GET", path, params=query, headers=self._headers, settings=self._settings)
        # API response from this request can contain 'description' matching the process description
        # rather than a generic response 'description'. Enforce the provided message to avoid confusion.
        msg = "Process description successfully retrieved."
        return self._parse_result(resp, message=msg, output_format=output_format,
                                  show_links=show_links, show_headers=show_headers)

    @staticmethod
    def _parse_inputs(inputs):
        # type: (Optional[Union[str, JSON]]) -> Union[OperationResult, ExecutionInputsMap]
        """
        Parse multiple different representation formats and input sources into standard :term:`OGC` inputs.

        Schema :term:`OGC` is selected to increase compatibility coverage with potential non-`Weaver` servers
        only conforming to standard :term:`OGC API - Processes`.

        Inputs can be represented as :term:`CLI` option string arguments, file path to load contents from, or
        directly supported list or mapping of execution inputs definitions.
        """
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
                inputs = {"inputs": inputs}  # convert OLD format provided directly into OGC
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
                values = cwl2json_input_values(inputs, schema=ProcessSchema.OGC)
            if values is null:
                raise ValueError("Input values parsed as null. Could not properly detect employed schema.")
            values = convert_input_values_schema(values, schema=ProcessSchema.OGC)
        except Exception as exc:
            return OperationResult(False, f"Failed inputs parsing with error: [{exc!s}].", inputs)
        return values

    def _update_files(self, inputs, url=None):
        # type: (ExecutionInputsMap, Optional[str]) -> Tuple[ExecutionInputsMap, HeadersType]
        """
        Replaces local file paths by references uploaded to the :term:`Vault`.

        .. seealso::
            - Headers dictionary limitation by :mod:`requests`:
              https://docs.python-requests.org/en/latest/user/quickstart/#response-headers
            - Headers formatting with multiple values must be provided by comma-separated values
              (:rfc:`7230#section-3.2.2`).
            - Multi Vault-Token parsing accomplished by :func:`weaver.vault.utils.parse_vault_token`.
            - More details about formats and operations related to :term:`Vault` are provided
              in :ref:`file_vault_token` and :ref:`vault` chapters.

        :param inputs: Input values for submission of :term:`Process` execution.
        :return: Updated inputs.
        """
        auth_tokens = {}  # type: Dict[str, str]
        update_inputs = dict(inputs)
        for input_id, input_data in dict(inputs).items():
            if not isinstance(input_data, list):  # support array of files
                input_data = [input_data]
            for data in input_data:
                if not isinstance(data, dict):
                    continue
                file = href = get_any_value(data, default=null, data=False)
                if not isinstance(href, str):
                    continue
                if href.startswith("file://"):
                    href = href[7:]
                if "://" not in href and not os.path.isfile(href):
                    LOGGER.warning(
                        "Ignoring potential local file reference since it does not exist. "
                        "Cannot upload to vault: [%s]", file
                    )
                    continue
                fmt = data.get("format", {})
                ctype = get_field(fmt, "mime_type", search_variations=True)
                if not ctype:
                    ext = os.path.splitext(href)[-1]
                    ctype = get_content_type(ext)
                fmt = get_format(ctype, default=ContentType.TEXT_PLAIN)
                res = self.upload(href, content_type=fmt.mime_type, url=url)
                if res.code != 200:
                    return res
                vault_href = res.body["file_href"]
                vault_id = res.body["file_id"]
                token = res.body["access_token"]
                auth_tokens[vault_id] = token
                LOGGER.info("Converted (input: %s) [%s] -> [%s]", input_id, file, vault_href)
                update_inputs[input_id] = {"href": vault_href, "format": {"mediaType": ctype}}

        auth_headers = {}
        if auth_tokens:
            multi_tokens = ",".join([
                f"token {token}; id={input_id}"
                for input_id, token in auth_tokens.items()
            ])
            auth_headers = {sd.XAuthVaultFileHeader.name: multi_tokens}
        return update_inputs, auth_headers

    # FIXME: support sync (https://github.com/crim-ca/weaver/issues/247)
    # :param execute_async:
    #   Execute the process asynchronously (user must call :meth:`monitor` themselves,
    #   or synchronously where monitoring is done automatically until completion before returning.
    def execute(self,
                process_id,             # type: str
                inputs=None,            # type: Optional[Union[str, JSON]]
                monitor=False,          # type: bool
                timeout=None,           # type: Optional[int]
                interval=None,          # type: Optional[int]
                url=None,               # type: Optional[str]
                show_links=True,        # type: bool
                show_headers=False,     # type: bool
                output_format=None,     # type: Optional[AnyOutputFormat]
                ):                      # type: (...) -> OperationResult
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
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        if isinstance(inputs, list) and all(isinstance(item, list) for item in inputs):
            inputs = [items for sub in inputs for items in sub]  # flatten 2D->1D list
        values = self._parse_inputs(inputs)
        if isinstance(values, OperationResult):
            return values
        base = self._get_url(url)
        result = self._update_files(values, url=base)
        if isinstance(result, OperationResult):
            return result
        values, auth_headers = result
        data = {
            # NOTE: since sync is not yet properly implemented in Weaver, simulate with monitoring after if requested
            # FIXME: support 'sync' (https://github.com/crim-ca/weaver/issues/247)
            "mode": ExecuteMode.ASYNC,
            "inputs": values,
            # FIXME: support 'response: raw' (https://github.com/crim-ca/weaver/issues/376)
            "response": ExecuteResponse.DOCUMENT,
            # FIXME: allow omitting 'outputs' (https://github.com/crim-ca/weaver/issues/375)
            # FIXME: allow 'transmissionMode: value/reference' selection (https://github.com/crim-ca/weaver/issues/377)
            "outputs": {}
        }
        # FIXME: since (https://github.com/crim-ca/weaver/issues/375) not implemented, auto-populate all the outputs
        result = self.describe(process_id, url=base)
        if not result.success:
            return OperationResult(False, "Could not obtain process description for execution.",
                                   body=result.body, headers=result.headers, code=result.code, text=result.text)
        outputs = result.body.get("outputs")
        for output_id in outputs:
            # use 'value' to have all outputs reported in body as 'value/href' rather than 'Link' headers
            data["outputs"][output_id] = {"transmissionMode": ExecuteTransmissionMode.VALUE}

        LOGGER.info("Executing [%s] with inputs:\n%s", process_id, OutputFormat.convert(values, OutputFormat.JSON_STR))
        path = f"{base}/processes/{process_id}/execution"  # use OGC-API compliant endpoint (not '/jobs')
        headers = {}
        headers.update(self._headers)
        headers.update(auth_headers)
        resp = request_extra("POST", path, json=data, headers=headers, settings=self._settings)
        result = self._parse_result(resp, show_links=show_links, show_headers=show_headers, output_format=output_format)
        if not monitor or not result.success:
            return result
        # although Weaver returns "jobID" in the body for convenience,
        # employ the "Location" header to be OGC-API compliant
        job_url = resp.headers.get("Location", "")
        return self.monitor(job_url, timeout=timeout, interval=interval,
                            show_links=show_links, show_headers=show_headers, output_format=output_format)

    def upload(self, file_path, content_type=None, url=None, show_links=True, show_headers=False, output_format=None):
        # type: (str, Optional[str], Optional[str], bool, bool, Optional[AnyOutputFormat]) -> OperationResult
        """
        Upload a local file to the :term:`Vault`.

        .. note::
            Feature only available for `Weaver` instances. Not available for standard :term:`OGC API - Processes`.

        .. seealso::
            More details about formats and operations related to :term:`Vault` are provided
            in :ref:`file_vault_token` and :ref:`vault` chapters.

        :param file_path: Location of the file to be uploaded.
        :param content_type:
            Explicit Content-Type of the file.
            This should be an IANA Media-Type, optionally with additional parameters such as charset.
            If not provided, attempts to guess it based on the file extension.
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        if not isinstance(file_path, str):
            file_type = fully_qualified_name(file_path)
            return OperationResult(False, "Local file reference is not a string.", {"file_path": file_type})
        if file_path.startswith("file://"):
            file_path = file_path[7:]
        if "://" in file_path:
            scheme = file_path.split("://", 1)[0]
            return OperationResult(False, "Scheme not supported for local file reference.", {"file_scheme": scheme})
        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.isfile(file_path):
            return OperationResult(False, "Resolved local file reference does not exist.", {"file_path": file_path})
        LOGGER.debug("Processing file for vault upload: [%s]", file_path)
        file_headers = get_file_headers(file_path, content_headers=True, content_type=content_type)
        base = self._get_url(url)
        path = f"{base}/vault"
        files = {
            "file": (
                os.path.basename(file_path),
                open(file_path, "r", encoding="utf-8"),
                file_headers["Content-Type"]
            )
        }
        req_headers = {
            "Accept": ContentType.APP_JSON,  # no 'Content-Type' since auto generated with multipart boundary
            "Cache-Control": "no-cache",     # ensure the cache is not used to return a previously uploaded file
        }
        # allow retry to avoid some sporadic HTTP 403 errors
        resp = request_extra("POST", path, headers=req_headers, settings=self._settings, files=files, retry=2)
        return self._parse_result(resp, show_links=show_links, show_headers=show_headers, output_format=output_format)

    def jobs(self,
             url=None,              # type: Optional[str]
             show_links=True,       # type: bool
             show_headers=False,    # type: bool
             output_format=None,    # type: Optional[AnyOutputFormat]
             page=None,             # type: Optional[int]
             limit=None,            # type: Optional[int]
             status=None,           # type: Optional[StatusType]
             detail=False,          # type: bool
             groups=False,          # type: bool
             ):                     # type: (...) -> OperationResult
        """
        Obtain a listing of :term:`Job`.

        .. seealso::
            :ref:`proc_op_status`

        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :param page: Paging index to list jobs.
        :param limit: Amount of jobs to list per page.
        :param status: Filter job listing only to matching status.
        :param detail: Obtain detailed job descriptions.
        :param groups: Obtain grouped representation of jobs per provider and process categories.
        :returns: Retrieved status of the job.
        """
        base_url = self._get_url(url)
        jobs_url = f"{base_url}/jobs" if not base_url.endswith("/jobs") else base_url
        LOGGER.info("Getting job listing: [%s]", jobs_url)
        query = {}
        if isinstance(page, int) and page > 0:
            query["page"] = page
        if isinstance(limit, int) and limit > 0:
            query["limit"] = limit
        if isinstance(status, str) and status:
            query["status"] = status
        if isinstance(detail, bool) and detail:
            query["detail"] = detail
        if isinstance(groups, bool) and groups:
            query["groups"] = groups
        resp = request_extra("GET", jobs_url, params=query, headers=self._headers, settings=self._settings)
        return self._parse_result(resp, output_format=output_format,
                                  nested_links="jobs", show_links=show_links, show_headers=show_headers)

    def status(self, job_reference, url=None, show_links=True, show_headers=False, output_format=None):
        # type: (str, Optional[str], bool, bool, Optional[AnyOutputFormat]) -> OperationResult
        """
        Obtain the status of a :term:`Job`.

        .. seealso::
            :ref:`proc_op_status`

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Retrieved status of the job.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.info("Getting job status: [%s]", job_id)
        resp = request_extra("GET", job_url, headers=self._headers, settings=self._settings)
        return self._parse_result(resp, show_links=show_links, show_headers=show_headers, output_format=output_format)

    def monitor(self,
                job_reference,                      # type: str
                timeout=None,                       # type: Optional[int]
                interval=None,                      # type: Optional[int]
                wait_for_status=Status.SUCCEEDED,   # type: str
                url=None,                           # type: Optional[str]
                show_links=True,                    # type: bool
                show_headers=False,                 # type: bool
                output_format=None,                 # type: Optional[AnyOutputFormat]
                ):                                  # type: (...) -> OperationResult
        """
        Monitor the execution of a :term:`Job` until completion.

        .. seealso::
            :ref:`proc_op_monitor`

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param timeout: timeout (seconds) of maximum wait time for monitoring if completion is not reached.
        :param interval: wait interval (seconds) between polling monitor requests.
        :param wait_for_status: monitor until the requested status is reached (default: job failed or succeeded).
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :return: Result of the successful or failed job, or timeout of monitoring process.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        remain = timeout = timeout or self.monitor_timeout
        delta = interval or self.monitor_interval
        LOGGER.info("Monitoring job [%s] for %ss at intervals of %ss.", job_id, timeout, delta)
        once = True
        while remain >= 0 or once:
            resp = request_extra("GET", job_url, headers=self._headers, settings=self._settings)
            if resp.status_code != 200:
                return OperationResult(False, "Could not find job with specified reference.", {"job": job_reference})
            body = resp.json()
            status = body.get("status")
            if status == wait_for_status:
                msg = f"Requested job status reached [{wait_for_status}]."
                return self._parse_result(resp, success=True, message=msg, show_links=show_links,
                                          show_headers=show_headers, output_format=output_format)
            if status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
                msg = "Requested job status not reached, but job has finished."
                return self._parse_result(resp, success=False, message=msg, show_links=show_links,
                                          show_headers=show_headers, output_format=output_format)
            time.sleep(delta)
            remain -= delta
            once = False
        return OperationResult(False, f"Monitoring timeout reached ({timeout}s). Job did not complete in time.")

    def results(self,
                job_reference,          # type: str
                out_dir=None,           # type: Optional[str]
                download=False,         # type: bool
                url=None,               # type: Optional[str]
                show_links=True,        # type: bool
                show_headers=False,     # type: bool
                output_format=None,     # type: Optional[AnyOutputFormat]
                ):                      # type: (...) -> OperationResult
        """
        Obtain the results of a successful :term:`Job` execution.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param out_dir: Output directory where to store downloaded files if requested (default: CURDIR/JobID/<outputs>).
        :param download: Download any file reference found within results (CAUTION: could transfer lots of data!).
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Result details and local paths if downloaded.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        status = self.status(job_url)
        if not status.success:
            return OperationResult(False, "Cannot process results from incomplete or failed job.", status.body)
        # use results endpoint instead of outputs to be OGC-API compliant, should be able to target non-Weaver instance
        # with this endpoint, outputs IDs are directly at the root of the body
        result_url = f"{job_url}/results"
        LOGGER.info("Retrieving results from [%s]", result_url)
        resp = request_extra("GET", result_url, headers=self._headers, settings=self._settings)
        res_out = self._parse_result(resp, output_format=output_format,
                                     show_links=show_links, show_headers=show_headers)
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

    def dismiss(self, job_reference, url=None, show_links=True, show_headers=False, output_format=None):
        # type: (str, Optional[str], bool, bool, Optional[AnyOutputFormat]) -> OperationResult
        """
        Dismiss pending or running :term:`Job`, or clear result artifacts from a completed :term:`Job`.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :param show_links: Indicate if ``links`` section should be preserved in returned result body.
        :param show_headers: Indicate if response headers should be returned in result output.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Obtained result from the operation.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.debug("Dismissing job: [%s]", job_id)
        resp = request_extra("DELETE", job_url, headers=self._headers, settings=self._settings)
        return self._parse_result(resp, show_links=show_links, show_headers=show_headers, output_format=output_format)


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
    parser.add_argument("-u", "--url", metavar="URL", help="URL of the instance to run operations.", required=required)


def add_shared_options(parser):
    # type: (argparse.ArgumentParser) -> None
    parser.add_argument("-L", "--no-links", dest="show_links", action="store_false",
                        help="Remove \"links\" section from returned result body.")
    parser.add_argument("-H", "--headers", dest="show_headers", action="store_true",
                        help="Return response headers additionally to the result body.")
    fmt_docs = "\n\n".join([
        re.sub(r"\:[a-z]+\:\`([A-Za-z0-9_\-]+)\`", r"\1", f"{getattr(OutputFormat, fmt)}: {doc}")  # remove RST
        for fmt, doc in sorted(OutputFormat.docs().items()) if doc
    ])
    parser.add_argument(
        "-F", "--format", choices=sorted(OutputFormat.values()), dest="output_format",
        help=f"Select an alternative output representation (default: {OutputFormat.JSON_STR}).\n\n{fmt_docs}"
    )


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


class ParagraphFormatter(argparse.HelpFormatter):
    # pragma: no cover  # somehow marked not covered, but functionality covered by 'test_execute_help_details'
    def _format_action(self, action):
        """
        Override the returned help message with available options and shortcuts for description paragraphs.

        This ensures that paragraphs defined the argument's help remain separated and properly formatted.
        """
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
            help_block = super(ParagraphFormatter, self)._format_action(action)
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


class ArgumentParserFixedRequiredArgs(argparse.ArgumentParser):
    """
    Override action grouping under 'required' section to consider explicit flag even if action has option prefix.

    Default behaviour places option prefixed (``-``, ``--``) arguments into optionals even if ``required`` is defined.
    Help string correctly considers this flag and doesn't place those arguments in brackets (``[--<optional-arg>]``).
    """
    def _add_action(self, action):
        if action.option_strings and not action.required:
            self._optionals._add_action(action)
        else:
            self._positionals._add_action(action)
        return action


class WeaverArgumentParser(ArgumentParserFixedRequiredArgs, SubArgumentParserFixedMutexGroups):
    """
    Parser that provides fixes for proper representation of `Weaver` :term:`CLI` arguments.
    """
    def format_help(self):
        # type: () -> str
        return super(WeaverArgumentParser, self).format_help() + "\n"


def make_parser():
    # type: () -> argparse.ArgumentParser
    """
    Generate the :term:`CLI` parser.

    .. note::
        Instead of employing :class:`argparse.ArgumentParser` instances returned
        by :meth:`argparse._SubParsersAction.add_parser`, distinct :class:`argparse.ArgumentParser` instances are
        created for each operation and then merged back by ourselves as subparsers under the main parser.
        This provides more flexibility in arguments passed down and resolves, amongst other things, incorrect
        handling of exclusive argument groups and their grouping under corresponding section titles.
    """
    # generic logging parser to pass down to each operation
    # this allows providing logging options to any of them
    log_parser = WeaverArgumentParser(add_help=False)
    make_logging_options(log_parser)

    desc = "Run {} operations.".format(__meta__.__title__)
    parser = WeaverArgumentParser(prog=__meta__.__name__, description=desc, parents=[log_parser])
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

    op_deploy = WeaverArgumentParser(
        "deploy",
        description="Deploy a process.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_deploy)
    add_url_param(op_deploy)
    add_shared_options(op_deploy)
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

    op_undeploy = WeaverArgumentParser(
        "undeploy",
        description="Undeploy an existing process.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_undeploy)
    add_url_param(op_undeploy)
    add_shared_options(op_undeploy)
    add_process_param(op_undeploy)

    op_capabilities = WeaverArgumentParser(
        "capabilities",
        description="List available processes.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_capabilities)
    add_url_param(op_capabilities)
    add_shared_options(op_capabilities)

    op_describe = WeaverArgumentParser(
        "describe",
        description="Obtain an existing process description.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_describe)
    add_url_param(op_describe)
    add_shared_options(op_describe)
    add_process_param(op_describe)
    op_describe.add_argument(
        "-S", "--schema", dest="schema", choices=ProcessSchema.values(), default=ProcessSchema.OGC,
        help="Representation schema of the returned process description."
    )

    op_execute = WeaverArgumentParser(
        "execute",
        description="Submit a job execution for an existing process.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_execute)
    add_url_param(op_execute)
    add_shared_options(op_execute)
    add_process_param(op_execute)
    op_execute.add_argument(
        "-I", "--inputs", dest="inputs",
        required=True, nargs=1, action="append",  # collect max 1 item per '-I', but allow many '-I'
        # note: below is formatted using 'ParagraphFormatter' with detected paragraphs
        help=inspect.cleandoc("""
            Literal input definitions, or a file path or URL reference to JSON or YAML
            contents defining job inputs with OGC-API or CWL schema. This parameter is required.

            To provide inputs using a file reference, refer to relevant CWL Job schema or API request schema
            for selected format. Both mapping and listing formats are supported.

            To execute a process without any inputs (e.g.: using its defaults),
            supply an explicit empty input (i.e.: ``-I ""`` or loaded from file as ``{}``).

            To provide inputs using literal command-line definitions, inputs should be specified using ``<id>=<value>``
            convention, with distinct ``-I`` options for each applicable input value.

            Values that require other type than string to be converted for job submission can include the type
            following the ID using a colon separator (i.e.: ``<id>:<type>=<value>``). For example, an integer could be
            specified as follows: ``number:int=1`` while a floating point number would be: ``number:float=1.23``.

            File references (``href``) should be specified using ``File`` as the type (i.e.: ``input:File=http://...``).
            Note that ``File`` in this case is expected to be an URL location where the file can be download from.
            When a local file is supplied, Weaver will automatically convert it to a remote Vault File in order to
            upload it and make it available for the remote process.

            Array input (``maxOccurs > 1``) should be specified using semicolon (;) separated values.
            The type of an item of this array can also be provided (i.e.: ``array:int=1;2;3``).

            Example: ``-I message='Hello Weaver' -I value:int=1234``
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

    op_jobs = WeaverArgumentParser(
        "jobs",
        description="Obtain listing of registered jobs.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_jobs)
    add_url_param(op_jobs, required=True)
    add_shared_options(op_jobs)
    op_jobs.add_argument(
        "-P", "--page", dest="page", type=int,
        help="Specify the paging index for listing jobs."
    )
    op_jobs.add_argument(
        "-N", "--number", "--limit", dest="limit", type=int,
        help="Specify the amount of jobs to list per page."
    )
    op_jobs.add_argument(
        "-S", "--status", dest="status", choices=Status.values(),
        help="Filter job listing only to matching status."
    )
    op_jobs.add_argument(
        "-D", "--detail", dest="detail", action="store_true",
        help="Obtain detailed job descriptions."
    )
    op_jobs.add_argument(
        "-G", "--groups", dest="groups", action="store_true",
        help="Obtain grouped representation of jobs per provider and process categories."
    )

    op_dismiss = WeaverArgumentParser(
        "dismiss",
        description="Dismiss a pending or running job, or wipe any finished job results.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_dismiss)
    add_url_param(op_dismiss, required=False)
    add_job_ref_param(op_dismiss)
    add_shared_options(op_dismiss)

    op_monitor = WeaverArgumentParser(
        "monitor",
        description="Monitor a pending or running job execution until completion or up to a maximum wait time.",
        formatter_class=ParagraphFormatter,
    )
    add_url_param(op_monitor, required=False)
    add_job_ref_param(op_monitor)
    add_timeout_param(op_monitor)
    add_shared_options(op_monitor)

    op_status = WeaverArgumentParser(
        "status",
        description=(
            "Obtain the status of a job using a reference UUID or URL. "
            "This is equivalent to doing a single-shot 'monitor' operation without any pooling or retries."
        ),
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_status)
    add_url_param(op_status, required=False)
    add_job_ref_param(op_status)
    add_shared_options(op_status)

    op_results = WeaverArgumentParser(
        "results",
        description=(
            "Obtain the output results description of a job. "
            "This operation can also download them from the remote server if requested."
        ),
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_results)
    add_url_param(op_results, required=False)
    add_job_ref_param(op_results)
    add_shared_options(op_results)
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

    op_upload = WeaverArgumentParser(
        "upload",
        description=(
            "Upload a local file to the remote server vault for reference in process execution inputs. "
            "This operation is accomplished automatically for all execution inputs submitted using local files. "
            "[note: feature only available for Weaver instances]"
        ),
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_upload)
    add_url_param(op_upload, required=True)
    add_shared_options(op_upload)
    op_upload.add_argument(
        "-c", "--content-type", dest="content_type",
        help="Content-Type of the file to apply. "
             "This should be an IANA Media-Type, optionally with additional parameters such as charset. "
             "If not provided, attempts to guess it based on the file extension."
    )
    op_upload.add_argument(
        "-f", "--file", dest="file_path", metavar="FILE", required=True,
        help="Local file path to upload to the vault."
    )

    operations = [
        op_deploy,
        op_undeploy,
        op_capabilities,
        op_describe,
        op_execute,
        op_jobs,
        op_monitor,
        op_dismiss,
        op_status,
        op_results,
        op_upload,
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
    # type: (Any) -> int
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
