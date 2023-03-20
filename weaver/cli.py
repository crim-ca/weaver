import abc
import argparse
import base64
import copy
import inspect
import logging
import os
import re
import sys
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import yaml
from pyramid.httpexceptions import HTTPNotImplemented
from requests.auth import AuthBase, HTTPBasicAuth
from requests.structures import CaseInsensitiveDict
from webob.headers import ResponseHeaders
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
from weaver.processes.utils import get_process_information
from weaver.processes.wps_package import get_process_definition
from weaver.sort import Sort, SortMethods
from weaver.status import JOB_STATUS_CATEGORIES, Status, StatusCategory, map_status
from weaver.utils import (
    OutputMethod,
    copy_doc,
    fetch_reference,
    fully_qualified_name,
    get_any_id,
    get_any_value,
    get_header,
    get_href_headers,
    get_sane_name,
    import_target,
    load_file,
    null,
    parse_kvp,
    request_extra,
    setup_loggers
)
from weaver.visibility import Visibility
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Type, Union

    from requests import Response

    # avoid failing sphinx-argparse documentation
    # https://github.com/ashb/sphinx-argparse/issues/7
    try:
        from weaver.typedefs import (
            AnyHeadersContainer,
            AnyRequestMethod,
            AnyRequestType,
            AnyResponseType,
            CWL,
            JSON,
            ExecutionInputsMap,
            ExecutionResults,
            HeadersType
        )
    except ImportError:
        # avoid linter issue
        AnyRequestMethod = str
        AnyHeadersContainer = AnyRequestType = AnyResponseType = Any
        CWL = JSON = ExecutionInputsMap = ExecutionResults = HeadersType = Any
    try:
        from weaver.formats import AnyOutputFormat
        from weaver.processes.constants import ProcessSchemaType
        from weaver.status import AnyStatusSearch
    except ImportError:
        AnyOutputFormat = str
        AnyStatusSearch = str
        ProcessSchemaType = str

    ConditionalGroup = Tuple[argparse._ActionsContainer, bool, bool]  # noqa
    PostHelpFormatter = Callable[[str], str]
    ArgumentParserRule = Tuple[argparse._ActionsContainer, Callable[[argparse.Namespace], Optional[bool]], str]  # noqa

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
    headers = {}        # type: Optional[AnyHeadersContainer]
    body = {}           # type: Optional[Union[JSON, str]]
    code = None         # type: Optional[int]

    def __init__(self,
                 success=None,  # type: Optional[bool]
                 message=None,  # type: Optional[str]
                 body=None,     # type: Optional[Union[str, JSON]]
                 headers=None,  # type: Optional[AnyHeadersContainer]
                 text=None,     # type: Optional[str]
                 code=None,     # type: Optional[int]
                 **kwargs,      # type: Any
                 ):             # type: (...) -> None
        super(OperationResult, self).__init__(**kwargs)
        self.success = success
        self.message = message
        self.headers = ResponseHeaders(headers) if headers is not None else None
        self.body = body
        self.text = text
        self.code = code

    def __repr__(self):
        # type: () -> str
        params = ["success", "code", "message"]
        quotes = [False, False, True]
        quoted = lambda q, v: f"\"{v}\"" if q and v is not None else v  # noqa: E731  # pylint: disable=C3001
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

    def links(self, header_names=None):
        # type: (Optional[List[str]]) -> ResponseHeaders
        """
        Obtain HTTP headers sorted in the result that corresponds to any link reference.

        :param header_names:
            Limit link names to be considered.
            By default, considered headers are ``Link``, ``Content-Location`` and ``Location``.
        """
        if not self.headers:
            return ResponseHeaders([])
        if not isinstance(self.headers, ResponseHeaders):
            self.headers = ResponseHeaders(self.headers)
        if not header_names:
            header_names = ["Link", "Content-Location", "Location"]
        header_names = [hdr.lower() for hdr in header_names]
        link_headers = ResponseHeaders()
        for hdr_n, hdr_v in self.headers.items():
            if hdr_n.lower() in header_names:
                link_headers.add(hdr_n, hdr_v)
        return link_headers


class AuthHandler(AuthBase):
    url = None       # type: Optional[str]
    method = "GET"   # type: AnyRequestMethod
    headers = {}     # type: Optional[AnyHeadersContainer]
    identity = None  # type: Optional[str]
    password = None  # type: Optional[str]  # nosec

    def __init__(self, identity=None, password=None, url=None, method="GET", headers=None):
        # type: (Optional[str], Optional[str], Optional[str], AnyRequestMethod, Optional[AnyHeadersContainer]) -> None
        if identity is not None:
            self.identity = identity
        if password is not None:
            self.password = password
        if url is not None:
            self.url = url
        if method is not None:
            self.method = method
        if headers:
            self.headers = headers

    @abc.abstractmethod
    def __call__(self, request):
        # type: (AnyRequestType) -> AnyRequestType
        """
        Operation that performs inline authentication retrieval prior to sending the request.
        """
        raise NotImplementedError


class BasicAuthHandler(AuthHandler, HTTPBasicAuth):
    """
    Adds the ``Authorization`` header formed from basic authentication encoding of username and password to the request.

    Authentication URL and method are not needed for this handler.
    """

    def __init__(self, username, password, **kwargs):
        # type: (str, str, Any) -> None
        AuthHandler.__init__(self, identity=username, password=password, **kwargs)
        HTTPBasicAuth.__init__(self, username=username, password=password)

    @property
    def username(self):
        # type: () -> str
        return self.identity

    @username.setter
    def username(self, username):
        # type: (str) -> None
        self.identity = username

    def __call__(self, request):
        # type: (AnyRequestType) -> AnyRequestType
        return HTTPBasicAuth.__call__(self, request)


class RequestAuthHandler(AuthHandler, HTTPBasicAuth):
    """
    Base class to send a request in order to retrieve an authorization token.
    """
    @property
    def auth_token_name(self):
        # type: () -> str
        """
        Override token name to retrieve in response authentication handler implementation.

        Default looks amongst common names: [auth, access_token, token]
        """
        return ""

    @abc.abstractmethod
    def auth_header(self, token):
        # type: (str) -> AnyHeadersContainer
        """
        Obtain the header definition with the provided authorization token.
        """
        raise NotImplementedError

    def request_auth(self):
        # type: () -> Optional[str]
        """
        Performs a request using authentication parameters to retrieve the authorization token.
        """
        auth_headers = {"Accept": ContentType.APP_JSON}
        auth_headers.update(self.headers)
        resp = request_extra(self.method, self.url, headers=auth_headers)
        if resp.status_code != 200:
            return None
        return self.response_parser(resp)

    def response_parser(self, response):
        # type: (Response) -> Optional[str]
        """
        Parses a valid authentication response to extract the received authorization token.
        """
        ctype = get_header("Content-Type", response.headers)
        auth = None
        if ContentType.APP_JSON in ctype:
            body = response.json()
            if self.auth_token_name:
                auth = body.get(self.auth_token_name)
            else:
                auth = body.get("auth") or body.get("access_token") or body.get("token")
        return auth

    def __call__(self, request):
        # type: (AnyRequestType) -> AnyRequestType
        auth_token = self.request_auth()
        if not auth_token:
            LOGGER.warning("Expected authorization token could not be retrieved from: [%s] in [%s]",
                           self.url, fully_qualified_name(self))
        else:
            auth_header = self.auth_header(auth_token)
            request.headers.update(auth_header)
        return request


class BearerAuthHandler(RequestAuthHandler):
    """
    Adds the ``Authorization`` header formed of the authentication bearer token from the underlying request.
    """

    def auth_header(self, token):
        # type: (str) -> AnyHeadersContainer
        return {"Authorization": f"Bearer {token}"}


class CookieAuthHandler(RequestAuthHandler):
    """
    Adds the ``Authorization`` header formed of the authentication bearer token from the underlying request.
    """

    def auth_header(self, token):
        # type: (str) -> AnyHeadersContainer
        return {"Cookie": token}


class WeaverClient(object):
    """
    Client that handles common HTTP requests with a `Weaver` or similar :term:`OGC API - Processes` instance.
    """
    # default configuration parameters, overridable by corresponding method parameters
    monitor_timeout = 60    # maximum delay to wait for job completion
    monitor_interval = 5    # interval between monitor pooling job status requests
    auth = None  # type: AuthHandler

    def __init__(self, url=None, auth=None):
        # type: (Optional[str], Optional[AuthHandler]) -> None
        """
        Initialize the client with predefined parameters.

        :param url: Instance URL to employ for each method call. Must be provided each time if not defined here.
        :param auth:
            Instance authentication handler that will be applied for every request.
            For specific authentication method on per-request basis, parameter should be provided to respective methods.
            Should perform required adjustments to request to allow access control of protected contents.
        """
        if url:
            self._url = self._parse_url(url)
            LOGGER.debug("Using URL: [%s]", self._url)
        else:
            self._url = None
            LOGGER.warning("No URL provided. All operations must provide it directly or through another parameter!")
        self.auth = auth
        self._headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
        self._settings = {
            "weaver.request_options": {}
        }  # FIXME: load from INI, overrides as input (cumul arg '--setting weaver.x=value') ?

    def _request(self,
                 method,                # type: AnyRequestMethod
                 url,                   # type: str
                 *args,                 # type: Any
                 headers=None,          # type: Optional[AnyHeadersContainer]
                 x_headers=None,        # type: Optional[AnyHeadersContainer]
                 request_timeout=None,  # type: Optional[int]
                 request_retries=None,  # type: Optional[int]
                 **kwargs               # type: Any
                 ):                     # type: (...) -> AnyResponseType
        if self.auth is not None and kwargs.get("auth") is None:
            kwargs["auth"] = self.auth

        if not headers and x_headers:
            headers = x_headers
        elif headers:
            headers = CaseInsensitiveDict(headers)
            x_headers = CaseInsensitiveDict(x_headers)
            headers.update(x_headers)

        if isinstance(request_timeout, int) and request_timeout > 0:
            kwargs.setdefault("timeout", request_timeout)
        if isinstance(request_retries, int) and request_retries > 0:
            kwargs.setdefault("retries", request_retries)

        return request_extra(method, url, *args, headers=headers, **kwargs)

    def _get_url(self, url):
        # type: (Optional[str]) -> str
        if not self._url and not url:
            raise ValueError("No URL available. Client was not created with an URL and operation did not receive one.")
        return self._url or self._parse_url(url)

    @staticmethod
    def _parse_url(url):
        parsed = urlparse(f"http://{url}" if not url.startswith("http") else url)
        parsed_netloc_path = f"{parsed.netloc}{parsed.path}".replace("//", "/")
        parsed_url = f"{parsed.scheme}://{parsed_netloc_path}"
        return parsed_url.rsplit("/", 1)[0] if parsed_url.endswith("/") else parsed_url

    @staticmethod
    def _parse_result(response,             # type: Union[Response, OperationResult]
                      body=None,            # type: Optional[JSON]  # override response body
                      message=None,         # type: Optional[str]   # override message/description in contents
                      success=None,         # type: Optional[bool]  # override resolved success
                      with_headers=False,   # type: bool
                      with_links=True,      # type: bool
                      nested_links=None,    # type: Optional[str]
                      output_format=None,   # type: Optional[AnyOutputFormat]
                      content_type=None,    # type: Optional[ContentType]
                      ):                    # type: (...) -> OperationResult
        # multi-header of same name, for example to support many Link
        headers = ResponseHeaders(response.headers)
        code = getattr(response, "status_code", None) or getattr(response, "code", None)
        _success = False
        try:
            msg = None
            ctype = headers.get("Content-Type", content_type)
            content = getattr(response, "content", None) or getattr(response, "body", None)
            text = None
            if not body and content and ctype and ContentType.APP_JSON in ctype and hasattr(response, "json"):
                body = response.json()
            elif isinstance(response, OperationResult):
                body = response.body
            # Don't set text if no-content, since used by jobs header-only response. Explicit null will replace it.
            elif response.text and not body:
                msg = "Could not parse body."
                text = response.text
            if isinstance(body, dict):
                if not with_links:
                    if nested_links:
                        nested = body.get(nested_links, [])
                        if isinstance(nested, list):
                            for item in nested:
                                if isinstance(item, dict):
                                    item.pop("links", None)
                    body.pop("links", None)
                msg = body.get("description", body.get("message", "undefined"))
            if code >= 400:
                if not msg and isinstance(body, dict):
                    msg = body.get("error", body.get("exception", "unknown"))
            else:
                _success = True
            msg = message or getattr(response, "message", None) or msg or "undefined"
            text = text or OutputFormat.convert(body, output_format or OutputFormat.JSON_STR, item_root="result")
        except Exception as exc:  # noqa  # pragma: no cover  # ignore safeguard against error in implementation
            msg = "Could not parse body."
            text = body = response.text
            LOGGER.warning(msg, exc_info=exc)
        if with_headers:
            # convert potential multi-equal-key headers into a JSON/YAML serializable format
            hdr_l = [{hdr_name: hdr_val} for hdr_name, hdr_val in sorted(headers.items())]
            hdr_s = OutputFormat.convert({"Headers": hdr_l}, OutputFormat.YAML)
            text = f"{hdr_s}---\n{text}"
        if success is not None:
            _success = success
        return OperationResult(_success, msg, body, headers, text=text, code=code)

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
            desc = data.get("processDescription", {})
            if data and process_id:
                LOGGER.debug("Override provided process ID [%s] into provided/loaded body.", process_id)
                desc = data.get("processDescription", {}).get("process", {}) or data.get("processDescription", {})
                desc["id"] = process_id
            data.setdefault("processDescription", desc)  # already applied if description was found/updated at any level
            desc["visibility"] = Visibility.PUBLIC
        except (ValueError, TypeError, ScannerError) as exc:  # pragma: no cover
            return OperationResult(False, f"Failed resolution of body definition: [{exc!s}]", body)
        return OperationResult(True, "", data)

    @staticmethod
    def _parse_deploy_package(body, cwl, wps, process_id, headers):
        # type: (JSON, Optional[CWL], Optional[str], Optional[str], HeadersType) -> OperationResult
        try:
            p_desc = get_process_information(body)
            p_id = get_any_id(p_desc, default=process_id)
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
        except (PackageRegistrationError, ScannerError) as exc:  # pragma: no cover
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

    def register(self,
                 provider_id,           # type: str
                 provider_url,          # type: str
                 url=None,              # type: Optional[str]
                 auth=None,             # type: Optional[AuthHandler]
                 headers=None,          # type: Optional[AnyHeadersContainer]
                 with_links=True,       # type: bool
                 with_headers=False,    # type: bool
                 request_timeout=None,  # type: Optional[int]
                 request_retries=None,  # type: Optional[int]
                 output_format=None,    # type: Optional[AnyOutputFormat]
                 ):                     # type: (...) -> OperationResult
        """
        Registers a remote :term:`Provider` using specified references.

        :param provider_id: Identifier to employ for registering the new :term:`Provider`.
        :param provider_url: Endpoint location to register the new remote :term:`Provider`.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/providers"
        data = {"id": provider_id, "url": provider_url, "public": True}
        resp = self._request("POST", path, json=data,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)

    def unregister(self,
                   provider_id,             # type: str
                   url=None,                # type: Optional[str]
                   auth=None,               # type: Optional[AuthHandler]
                   headers=None,            # type: Optional[AnyHeadersContainer]
                   with_links=True,         # type: bool
                   with_headers=False,      # type: bool
                   request_timeout=None,    # type: Optional[int]
                   request_retries=None,    # type: Optional[int]
                   output_format=None,      # type: Optional[AnyOutputFormat]
                   ):                       # type: (...) -> OperationResult
        """
        Unregisters a remote :term:`Provider` using the specified identifier.

        :param provider_id: Identifier to employ for unregistering the :term:`Provider`.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/providers/{provider_id}"
        resp = self._request("DELETE", path,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format,
                                  message="Successfully unregistered provider.")

    def deploy(self,
               process_id=None,         # type: Optional[str]
               body=None,               # type: Optional[Union[JSON, str]]
               cwl=None,                # type: Optional[Union[CWL, str]]
               wps=None,                # type: Optional[str]
               token=None,              # type: Optional[str]
               username=None,           # type: Optional[str]
               password=None,           # type: Optional[str]
               undeploy=False,          # type: bool
               url=None,                # type: Optional[str]
               auth=None,               # type: Optional[AuthHandler]
               headers=None,            # type: Optional[AnyHeadersContainer]
               with_links=True,         # type: bool
               with_headers=False,      # type: bool
               request_timeout=None,    # type: Optional[int]
               request_retries=None,    # type: Optional[int]
               output_format=None,      # type: Optional[AnyOutputFormat]
               ):                       # type: (...) -> OperationResult
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
        :param username: Username to form the authentication token to a private :term:`Docker` registry.
        :param password: Password to form the authentication token to a private :term:`Docker` registry.
        :param undeploy: Perform undeploy as necessary before deployment to avoid conflict with exiting :term:`Process`.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
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
        LOGGER.debug("Deployment Body:\n%s", OutputFormat.convert(data, OutputFormat.JSON_STR))
        path = f"{base}/processes"
        resp = self._request("POST", path, json=data,
                             headers=req_headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)

    def undeploy(self,
                 process_id,            # type: str
                 url=None,              # type: Optional[str]
                 auth=None,             # type: Optional[AuthHandler]
                 headers=None,          # type: Optional[AnyHeadersContainer]
                 with_links=True,       # type: bool
                 with_headers=False,    # type: bool
                 request_timeout=None,  # type: Optional[int]
                 request_retries=None,  # type: Optional[int]
                 output_format=None,    # type: Optional[AnyOutputFormat]
                 ):                     # type: (...) -> OperationResult
        """
        Undeploy an existing :term:`Process`.

        :param process_id: Identifier of the process to undeploy.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/processes/{process_id}"
        resp = self._request("DELETE", path,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)

    def capabilities(self,
                     url=None,              # type: Optional[str]
                     auth=None,             # type: Optional[AuthHandler]
                     headers=None,          # type: Optional[AnyHeadersContainer]
                     with_links=True,       # type: bool
                     with_headers=False,    # type: bool
                     with_providers=False,  # type: bool
                     request_timeout=None,  # type: Optional[int]
                     request_retries=None,  # type: Optional[int]
                     output_format=None,    # type: Optional[AnyOutputFormat]
                     sort=None,             # type: Optional[Sort]
                     page=None,             # type: Optional[int]
                     limit=None,            # type: Optional[int]
                     detail=False,          # type: bool
                     ):                     # type: (...) -> OperationResult
        """
        List all available :term:`Process` on the instance.

        .. seealso::
            :ref:`proc_op_getcap`

        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param with_providers: Indicate if remote providers should be listed as well along with local processes.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :param sort: Sorting field to list processes. Name must be one of the fields supported by process objects.
        :param page: Paging index to list processes.
        :param limit: Amount of processes to list per page.
        :param detail: Obtain detailed process descriptions.
        :returns: Results of the operation.
        """
        base = self._get_url(url)
        path = f"{base}/processes"
        # queries not supported by non-Weaver, but default values save extra work if possible
        query = {"detail": detail, "providers": with_providers}
        query.update({
            name: param for name, param in [("sort", sort), ("page", page), ("limit", limit)] if param is not None
        })
        resp = self._request("GET", path, params=query,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        result = self._parse_result(resp)
        if not result.success:
            return result
        body = resp.json()
        processes = body.get("processes")
        providers = body.get("providers")
        # in case the instance does not support 'detail' query and returns full-detail process/provider descriptions,
        # generate the corresponding ID-only listing by extracting the relevant components
        if not detail and isinstance(processes, list) and all(isinstance(proc, dict) for proc in processes):
            body["processes"] = [get_any_id(proc) for proc in processes]
        if not detail and isinstance(providers, list) and all(isinstance(prov, dict) for prov in providers):
            if all(isinstance(proc, dict) for prov in providers for proc in prov.get("processes", [])):
                body["providers"] = [
                    {"id": get_any_id(prov), "processes": [get_any_id(proc) for proc in prov.get("processes", [])]}
                    for prov in providers
                ]
        return self._parse_result(resp, body=body, output_format=output_format,
                                  with_links=with_links, with_headers=with_headers)

    processes = capabilities  # alias
    """
    Alias of :meth:`capabilities` for :term:`Process` listing.
    """

    def describe(self,
                 process_id,                # type: str
                 provider_id=None,          # type: Optional[str]
                 url=None,                  # type: Optional[str]
                 auth=None,                 # type: Optional[AuthHandler]
                 headers=None,              # type: Optional[AnyHeadersContainer]
                 schema=ProcessSchema.OGC,  # type: Optional[ProcessSchemaType]
                 with_links=True,           # type: bool
                 with_headers=False,        # type: bool
                 request_timeout=None,      # type: Optional[int]
                 request_retries=None,      # type: Optional[int]
                 output_format=None,        # type: Optional[AnyOutputFormat]
                 ):                         # type: (...) -> OperationResult
        """
        Describe the specified :term:`Process`.

        .. seealso::
            :ref:`proc_op_describe`

        :param process_id: Identifier of the local or remote process to describe.
        :param provider_id: Identifier of the provider from which to locate a remote process to describe.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param schema: Representation schema of the returned process description.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Results of the operation.
        """
        path = self._get_process_url(url, process_id, provider_id)
        query = None
        schema = ProcessSchema.get(schema)
        if schema:
            query = {"schema": schema}
        resp = self._request("GET", path, params=query,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        # API response from this request can contain 'description' matching the process description
        # rather than a generic response 'description'. Enforce the provided message to avoid confusion.
        return self._parse_result(resp, message="Retrieving process description.", output_format=output_format,
                                  with_links=with_links, with_headers=with_headers)

    def _get_process_url(self, url, process_id, provider_id=None):
        # type: (str, str, Optional[str]) -> str
        base = self._get_url(url)
        if provider_id:
            path = f"{base}/providers/{provider_id}/processes/{process_id}"
        else:
            path = f"{base}/processes/{process_id}"
        return path

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
            #   unless 'value/href' (and also 'id' technically) are present
            values = inputs.get("inputs", null)
            if (
                values is null or
                values is not null and (
                    (isinstance(values, dict) and get_any_value(values) is null and "class" not in values) or
                    (isinstance(values, list) and all(isinstance(v, dict) and get_any_value(v) is null for v in values))
                )
            ):
                values = cwl2json_input_values(inputs, schema=ProcessSchema.OGC)
            if values is null:  # pragma: no cover  # ignore safeguard against error in implementation
                raise ValueError("Input values parsed as null. Could not properly detect employed schema.")
            values = convert_input_values_schema(values, schema=ProcessSchema.OGC)
        except Exception as exc:
            return OperationResult(False, f"Failed inputs parsing with error: [{exc!s}].", inputs)
        return values

    def _upload_files(self, inputs, url=None):
        # type: (ExecutionInputsMap, Optional[str]) -> Union[Tuple[ExecutionInputsMap, HeadersType], OperationResult]
        """
        Replaces local file paths by references uploaded to the :term:`Vault`.

        .. seealso::
            - Headers dictionary limitation by :mod:`requests`:
              https://requests.readthedocs.io/en/master/user/quickstart/#response-content
            - Headers formatting with multiple values must be provided by comma-separated values
              (:rfc:`7230#section-3.2.2`).
            - Multi Vault-Token parsing accomplished by :func:`weaver.vault.utils.parse_vault_token`.
            - More details about formats and operations related to :term:`Vault` are provided
              in :ref:`file_vault_token` and :ref:`vault_upload` chapters.

        :param inputs: Input values for submission of :term:`Process` execution.
        :return: Updated inputs or the result of a failing intermediate request.
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
                if os.path.isdir(href):
                    return OperationResult(
                        message=f"Cannot upload local directory to vault: [{file}]. Aborting operation.",
                        title="Directory upload not implemented.",
                        code=HTTPNotImplemented.code,
                    )
                if not os.path.isfile(href):  # Case for remote files (ex. http links)
                    if "://" not in href:
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

    def execute(self,
                process_id,             # type: str
                provider_id=None,       # type: Optional[str]
                inputs=None,            # type: Optional[Union[str, JSON]]
                monitor=False,          # type: bool
                timeout=None,           # type: Optional[int]
                interval=None,          # type: Optional[int]
                url=None,               # type: Optional[str]
                auth=None,              # type: Optional[AuthHandler]
                headers=None,           # type: Optional[AnyHeadersContainer]
                with_links=True,        # type: bool
                with_headers=False,     # type: bool
                request_timeout=None,   # type: Optional[int]
                request_retries=None,   # type: Optional[int]
                output_format=None,     # type: Optional[AnyOutputFormat]
                output_refs=None,       # type: Optional[Iterable[str]]
                ):                      # type: (...) -> OperationResult
        """
        Execute a :term:`Job` for the specified :term:`Process` with provided inputs.

        When submitting inputs with :term:`OGC API - Processes` schema, top-level ``inputs`` field is expected.
        Under this field, either the :term:`OGC` mapping (key-value) or listing (id,value) representations are accepted.

        If the top-level ``inputs`` field is not found, the alternative :term:`CWL` representation will be assumed.
        When submitting inputs with :term:`CWL` *job* schema, plain key-value(s) pairs are expected.
        All values should be provided directly under the key (including arrays), except for ``File`` type that must
        include details as the ``class: File`` and ``path`` with location.

        .. seealso::
            :ref:`proc_op_execute`

        .. note::
            Execution requests are always accomplished asynchronously. To obtain the final :term:`Job` status as if
            they were executed synchronously, provide the :paramref:`monitor` argument. This offers more flexibility
            over servers that could decide to ignore sync/async preferences, and avoids closing/timeout connection
            errors that could occur for long running processes, since status is pooled iteratively rather than waiting.

        :param process_id: Identifier of the local or remote process to execute.
        :param provider_id: Identifier of the provider from which to locate a remote process to execute.
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
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :param output_refs:
            Indicates which outputs by ID to be returned as HTTP Link header reference instead of body content value.
            With reference transmission mode, outputs that contain literal data will be linked by ``text/plain`` file
            containing the data. outputs that refer to a file reference will simply contain that URL reference as link.
            With value transmission mode (default behavior when outputs are not specified in this list), outputs are
            returned as direct values (literal or href) within the response content body.
        :returns: Results of the operation.
        """
        base = self._get_url(url)  # raise before inputs parsing if not available
        if isinstance(inputs, list) and all(isinstance(item, list) for item in inputs):
            inputs = [items for sub in inputs for items in sub]  # flatten 2D->1D list
        values = self._parse_inputs(inputs)
        if isinstance(values, OperationResult):
            return values
        result = self._upload_files(values, url=base)
        if isinstance(result, OperationResult):
            return result
        values, auth_headers = result
        data = {
            # NOTE: Backward compatibility for servers that only know ``mode`` and don't handle ``Prefer`` header.
            "mode": ExecuteMode.ASYNC,
            "inputs": values,
            "response": ExecuteResponse.DOCUMENT,
            # FIXME: allow filtering 'outputs' (https://github.com/crim-ca/weaver/issues/380)
            "outputs": {}
        }
        # omit x-headers on purpose for 'describe', assume they are intended for 'execute' operation only
        result = self.describe(process_id, provider_id=provider_id, url=base, auth=auth)
        if not result.success:
            return OperationResult(False, "Could not obtain process description for execution.",
                                   body=result.body, headers=result.headers, code=result.code, text=result.text)
        outputs = result.body.get("outputs")
        output_refs = set(output_refs or [])
        for output_id in outputs:
            if output_id in output_refs:
                # If any 'reference' is requested explicitly, must switch to 'response=raw'
                # since 'response=document' ignores 'transmissionMode' definitions.
                data["response"] = ExecuteResponse.RAW
                # Use 'value' to have all outputs reported in body as 'value/href' rather than 'Link' headers.
                out_mode = ExecuteTransmissionMode.REFERENCE
            else:
                # make sure to set value to outputs not requested as reference in case another one needs reference
                # mode doesn't matter if no output by reference requested since 'response=document' would be used
                out_mode = ExecuteTransmissionMode.VALUE
            data["outputs"][output_id] = {"transmissionMode": out_mode}

        LOGGER.info("Executing [%s] with inputs:\n%s", process_id, OutputFormat.convert(values, OutputFormat.JSON_STR))
        desc_url = self._get_process_url(base, process_id, provider_id)
        exec_url = f"{desc_url}/execution"  # use OGC-API compliant endpoint (not '/jobs')
        exec_headers = {"Prefer": "respond-async"}  # for more recent servers, OGC-API compliant async request
        exec_headers.update(self._headers)
        exec_headers.update(auth_headers)
        resp = self._request("POST", exec_url, json=data,
                             headers=exec_headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        result = self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)
        if not monitor or not result.success:
            return result
        # although Weaver returns "jobID" in the body for convenience,
        # employ the "Location" header to be OGC-API compliant
        job_url = resp.headers.get("Location", "")
        return self.monitor(job_url, timeout=timeout, interval=interval, auth=auth,  # omit x-headers on purpose
                            with_links=with_links, with_headers=with_headers, output_format=output_format)

    def upload(self,
               file_path,               # type: str
               content_type=None,       # type: Optional[str]
               url=None,                # type: Optional[str]
               auth=None,               # type: Optional[AuthHandler]
               headers=None,            # type: Optional[AnyHeadersContainer]
               with_links=True,         # type: bool
               with_headers=False,      # type: bool
               request_timeout=None,    # type: Optional[int]
               request_retries=None,    # type: Optional[int]
               output_format=None,      # type: Optional[AnyOutputFormat]
               ):                       # type: (...) -> OperationResult
        """
        Upload a local file to the :term:`Vault`.

        .. note::
            Feature only available for `Weaver` instances. Not available for standard :term:`OGC API - Processes`.

        .. seealso::
            More details about formats and operations related to :term:`Vault` are provided
            in :ref:`file_vault_token` and :ref:`vault_upload` chapters.

        :param file_path: Location of the file to be uploaded.
        :param content_type:
            Explicit Content-Type of the file.
            This should be an IANA Media-Type, optionally with additional parameters such as charset.
            If not provided, attempts to guess it based on the file extension.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
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
        if os.path.isdir(file_path):
            return OperationResult(
                message=f"Cannot upload local directory to vault: [{file_path}]. Aborting operation.",
                title="Directory upload not implemented.",
                code=HTTPNotImplemented.code,
            )
        if not os.path.isfile(file_path):
            return OperationResult(False, "Resolved local file reference does not exist.", {"file_path": file_path})
        LOGGER.debug("Processing file for vault upload: [%s]", file_path)
        file_headers = get_href_headers(
            file_path,
            download_headers=False,
            content_headers=True,
            content_type=content_type,
        )
        base = self._get_url(url)
        path = f"{base}/vault"
        files = {
            "file": (
                os.path.basename(file_path),
                open(file_path, "r", encoding="utf-8"),  # pylint: disable=R1732
                file_headers["Content-Type"]
            )
        }
        req_headers = {
            "Accept": ContentType.APP_JSON,  # no 'Content-Type' since auto generated with multipart boundary
            "Cache-Control": "no-cache",     # ensure the cache is not used to return a previously uploaded file
        }
        # allow retry to avoid some sporadic HTTP 403 errors
        resp = self._request("POST", path, files=files,
                             headers=req_headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries or 2)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)

    def jobs(self,
             url=None,              # type: Optional[str]
             auth=None,             # type: Optional[AuthHandler]
             headers=None,          # type: Optional[AnyHeadersContainer]
             with_links=True,       # type: bool
             with_headers=False,    # type: bool
             request_timeout=None,  # type: Optional[int]
             request_retries=None,  # type: Optional[int]
             output_format=None,    # type: Optional[AnyOutputFormat]
             sort=None,             # type: Optional[Sort]
             page=None,             # type: Optional[int]
             limit=None,            # type: Optional[int]
             status=None,           # type: Optional[Union[AnyStatusSearch, List[AnyStatusSearch]]]
             detail=False,          # type: bool
             groups=False,          # type: bool
             process=None,          # type: Optional[str]
             provider=None,         # type: Optional[str]
             tags=None,             # type: Optional[Union[str, List[str]]]
             ):                     # type: (...) -> OperationResult
        """
        Obtain a listing of :term:`Job`.

        .. seealso::
            :ref:`proc_op_status`

        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :param sort: Sorting field to list jobs. Name must be one of the fields supported by job objects.
        :param page: Paging index to list jobs.
        :param limit: Amount of jobs to list per page.
        :param status: Filter job listing only to matching status. If multiple are provided, must match one of them.
        :param detail: Obtain detailed job descriptions.
        :param groups: Obtain grouped representation of jobs per provider and process categories.
        :param process: Obtain jobs executed only by matching :term:`Process`.
        :param provider: Obtain jobs only matching remote :term:`Provider`.
        :param tags: Obtain jobs filtered by matching tags. Jobs must match all tags simultaneously, not one of them.
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
        if sort is not None:
            query["sort"] = sort
        if isinstance(status, (str, Status, StatusCategory)) and status:
            status = str(getattr(status, "value", status)).split(",")  # consider enum or plain single/multi string
        if isinstance(status, list) and status:
            status = [StatusCategory.get(_status, map_status(_status)) for _status in status]
            query["status"] = ",".join([str(getattr(_status, "value", _status)) for _status in status])
        if isinstance(detail, bool) and detail:
            query["detail"] = detail
        if isinstance(groups, bool) and groups:
            query["groups"] = groups
        if isinstance(process, str) and process:
            query["process"] = process
        if isinstance(provider, str) and provider:
            query["provider"] = provider
        if isinstance(tags, list):
            tags = ",".join(tags)
        if isinstance(tags, str) and tags:
            query["tags"] = tags
        resp = self._request("GET", jobs_url, params=query,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, output_format=output_format,
                                  nested_links="jobs", with_links=with_links, with_headers=with_headers)

    def status(self,
               job_reference,           # type: str
               url=None,                # type: Optional[str]
               auth=None,               # type: Optional[AuthHandler]
               headers=None,            # type: Optional[AnyHeadersContainer]
               with_links=True,         # type: bool
               with_headers=False,      # type: bool
               request_timeout=None,    # type: Optional[int]
               request_retries=None,    # type: Optional[int]
               output_format=None,      # type: Optional[AnyOutputFormat]
               ):                       # type: (...) -> OperationResult
        """
        Obtain the status of a :term:`Job`.

        .. seealso::
            :ref:`proc_op_status`

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Retrieved status of the :term:`Job`.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.info("Getting job status: [%s]", job_id)
        resp = self._request("GET", job_url,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)

    def _job_info(self,
                  x_path,                   # type: str
                  job_reference,            # type: str
                  url=None,                 # type: Optional[str]
                  auth=None,                # type: Optional[AuthHandler]
                  headers=None,             # type: Optional[AnyHeadersContainer]
                  with_links=True,          # type: bool
                  with_headers=False,       # type: bool
                  request_timeout=None,     # type: Optional[int]
                  request_retries=None,     # type: Optional[int]
                  output_format=None,       # type: Optional[AnyOutputFormat]
                  ):                        # type: (...) -> OperationResult
        """
        Obtain the information from a :term:`Job`.

        The :term:`Job` must be in the expected status to retrieve relevant information.

        .. seealso::
            :ref:`proc_op_result`

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Retrieved information from the :term:`Job`.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        job_path = f"{job_url}{x_path}"
        LOGGER.info("Getting job information (%s): [%s]", job_path.rsplit("/", 1)[-1], job_id)
        resp = self._request("GET", job_path,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)

    @copy_doc(_job_info)
    def logs(self, **kwargs):
        return self._job_info("/logs", **kwargs)

    @copy_doc(_job_info)
    def exceptions(self, **kwargs):
        return self._job_info("/exceptions", **kwargs)

    errors = exceptions  # alias

    @copy_doc(_job_info)
    def statistics(self, **kwargs):
        return self._job_info("/statistics", **kwargs)

    stats = statistics  # alias

    def monitor(self,
                job_reference,                      # type: str
                timeout=None,                       # type: Optional[int]
                interval=None,                      # type: Optional[int]
                wait_for_status=Status.SUCCEEDED,   # type: str
                url=None,                           # type: Optional[str]
                auth=None,                          # type: Optional[AuthHandler]
                headers=None,                       # type: Optional[AnyHeadersContainer]
                with_links=True,                    # type: bool
                with_headers=False,                 # type: bool
                request_timeout=None,               # type: Optional[int]
                request_retries=None,               # type: Optional[int]
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
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :return: Result of the successful or failed job, or timeout of monitoring process.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        remain = timeout = timeout or self.monitor_timeout
        delta = interval or self.monitor_interval
        LOGGER.info("Monitoring job [%s] for %ss at intervals of %ss.", job_id, timeout, delta)
        LOGGER.debug("Job URL: [%s]", job_url)
        once = True
        resp = None
        while remain >= 0 or once:
            resp = self._request("GET", job_url,
                                 headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                                 request_timeout=request_timeout, request_retries=request_retries)
            if resp.status_code != 200:
                return OperationResult(False, "Could not find job with specified reference.", {"job": job_reference})
            body = resp.json()
            status = body.get("status")
            if status == wait_for_status:
                msg = f"Requested job status reached [{wait_for_status}]."
                return self._parse_result(resp, success=True, message=msg, with_links=with_links,
                                          with_headers=with_headers, output_format=output_format)
            if status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
                msg = "Requested job status not reached, but job has finished."
                return self._parse_result(resp, success=False, message=msg, with_links=with_links,
                                          with_headers=with_headers, output_format=output_format)
            time.sleep(delta)
            remain -= delta
            once = False
        # parse the latest available status response to provide at least the reference to the incomplete job
        msg = f"Monitoring timeout reached ({timeout}s). Job [{job_id}] did not complete in time."
        if resp:
            return self._parse_result(resp, success=False, message=msg, with_links=with_links,
                                      with_headers=with_headers, output_format=output_format)
        return OperationResult(False, msg)

    def _download_references(self, outputs, out_links, out_dir, job_id, auth=None):
        # type: (ExecutionResults, AnyHeadersContainer, str, str, Optional[AuthHandler]) -> ExecutionResults
        """
        Download file references from results response contents and link headers.

        Downloaded files extend the results contents with ``path`` and ``source`` fields to indicate where the
        retrieved files have been saved and where they came from. When files are found by HTTP header links, they
        are added to the output contents to generate a combined representation in the operation result.
        """
        if not isinstance(outputs, dict):
            # default if links-only needed later (insert as content for printed output)
            outputs = {}  # type: ExecutionResults

        # download file results
        if not (any("href" in value for value in outputs.values()) or len(out_links)):
            return OperationResult(False, "Outputs were found but none are downloadable (only raw values?).", outputs)
        if not out_dir:
            out_dir = os.path.join(os.path.realpath(os.path.curdir), job_id)
        os.makedirs(out_dir, exist_ok=True)
        LOGGER.info("Will store job [%s] output results in [%s]", job_id, out_dir)

        # download outputs from body content
        LOGGER.debug("%s outputs in results content.", "Processing" if len(outputs) else "No")
        for output, value in outputs.items():
            # nest each output under its own directory to avoid conflicting names
            # in case of many files across outputs that do guarantee uniqueness
            out_id = get_sane_name(output, min_len=1, assert_invalid=False)
            out_path = os.path.join(out_dir, out_id)
            is_list = True
            if not isinstance(value, list):
                value = [value]
                is_list = False
            for i, item in enumerate(value):
                if "href" in item:
                    os.makedirs(out_path, exist_ok=True)
                    ref_path = fetch_reference(item["href"], out_path, auth=auth,
                                               out_method=OutputMethod.COPY, out_listing=False)
                    if is_list:
                        outputs[output][i]["path"] = ref_path
                        outputs[output][i]["source"] = "body"
                    else:
                        outputs[output]["path"] = ref_path
                        outputs[output]["source"] = "body"

        # download links from headers
        LOGGER.debug("%s outputs in results link headers.", "Processing" if len(out_links) else "No")
        for _, link_header in ResponseHeaders(out_links).items():
            link, params = link_header.split(";", 1)
            href = link.strip("<>")
            params = parse_kvp(params, multi_value_sep=None, accumulate_keys=False)
            ctype = (params.get("type") or [None])[0]
            rel = params["rel"][0].split(".")
            output = rel[0]
            is_array = len(rel) > 1 and str.isnumeric(rel[1])
            ref_path = fetch_reference(href, out_dir, auth=auth,
                                       out_method=OutputMethod.COPY, out_listing=False)
            value = {"href": href, "type": ctype, "path": ref_path, "source": "link"}
            if output in outputs:
                if isinstance(outputs[output], dict):  # in case 'rel="<output>.<index"' was not employed
                    outputs[output] = [outputs[output], value]
                else:
                    outputs[output].append(value)
            else:
                outputs[output] = [value] if is_array else value
        return outputs

    def results(self,
                job_reference,          # type: str
                out_dir=None,           # type: Optional[str]
                download=False,         # type: bool
                url=None,               # type: Optional[str]
                auth=None,              # type: Optional[AuthHandler]
                headers=None,           # type: Optional[AnyHeadersContainer]
                with_links=True,        # type: bool
                with_headers=False,     # type: bool
                request_timeout=None,   # type: Optional[int]
                request_retries=None,   # type: Optional[int]
                output_format=None,     # type: Optional[AnyOutputFormat]
                ):                      # type: (...) -> OperationResult
        """
        Obtain the results of a successful :term:`Job` execution.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param out_dir: Output directory where to store downloaded files if requested (default: CURDIR/JobID/<outputs>).
        :param download: Download any file reference found within results (CAUTION: could transfer lots of data!).
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Result details and local paths if downloaded.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        # omit x-headers on purpose for 'status', assume they are intended for 'results' operation only
        status = self.status(job_url, auth=auth)
        if not status.success:
            return OperationResult(False, "Cannot process results from incomplete or failed job.", status.body)
        # use results endpoint instead of outputs to be OGC-API compliant, should be able to target non-Weaver instance
        # with this endpoint, outputs IDs are directly at the root of the body
        result_url = f"{job_url}/results"
        LOGGER.info("Retrieving results from [%s]", result_url)
        resp = self._request("GET", result_url,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        res_out = self._parse_result(resp, output_format=output_format,
                                     with_links=with_links, with_headers=with_headers)

        outputs = res_out.body
        headers = res_out.headers
        out_links = res_out.links(["Link"])
        if not res_out.success or not (isinstance(res_out.body, dict) or len(out_links)):  # pragma: no cover
            return OperationResult(False, "Could not retrieve any output results from job.", outputs, headers)
        if not download:
            res_out.message = "Listing job results."
            return res_out
        outputs = self._download_references(outputs, out_links, out_dir, job_id, auth=auth)
        # rebuild result with modified outputs that contains downloaded paths
        result = OperationResult(True, "Retrieved job results.", outputs, headers, code=200)
        return self._parse_result(result, body=outputs, output_format=output_format,
                                  with_links=with_links, with_headers=with_headers, content_type=ContentType.APP_JSON)

    def dismiss(self,
                job_reference,          # type: str
                url=None,               # type: Optional[str]
                auth=None,              # type: Optional[AuthHandler]
                headers=None,           # type: Optional[AnyHeadersContainer]
                with_links=True,        # type: bool
                with_headers=False,     # type: bool
                request_timeout=None,   # type: Optional[int]
                request_retries=None,   # type: Optional[int]
                output_format=None,     # type: Optional[AnyOutputFormat]
                ):                      # type: (...) -> OperationResult
        """
        Dismiss pending or running :term:`Job`, or clear result artifacts from a completed :term:`Job`.

        :param job_reference: Either the full :term:`Job` status URL or only its UUID.
        :param url: Instance URL if not already provided during client creation.
        :param auth:
            Instance authentication handler if not already created during client creation.
            Should perform required adjustments to request to allow access control of protected contents.
        :param headers:
            Additional headers to employ when sending request.
            Note that this can break functionalities if expected headers are overridden. Use with care.
        :param with_links: Indicate if ``links`` section should be preserved in returned result body.
        :param with_headers: Indicate if response headers should be returned in result output.
        :param request_timeout: Maximum timout duration (seconds) to wait for a response when performing HTTP requests.
        :param request_retries: Amount of attempt to retry HTTP requests in case of failure.
        :param output_format: Select an alternate output representation of the result body contents.
        :returns: Obtained result from the operation.
        """
        job_id, job_url = self._parse_job_ref(job_reference, url)
        LOGGER.debug("Dismissing job: [%s]", job_id)
        resp = self._request("DELETE", job_url,
                             headers=self._headers, x_headers=headers, settings=self._settings, auth=auth,
                             request_timeout=request_timeout, request_retries=request_retries)
        return self._parse_result(resp, with_links=with_links, with_headers=with_headers, output_format=output_format)


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
    log_title = "Logging Arguments"
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
    lvl_names = ["DEBUG", "INFO", "WARN", "ERROR"]
    lvl_opts.add_argument("--log-level", "-l", dest="log_level",
                          choices=list(sorted(lvl_names)), type=str.upper,
                          help="Explicit log level to employ (default: %(default)s, case-insensitive).")


def add_url_param(parser, required=True):
    # type: (argparse.ArgumentParser, bool) -> None
    parser.add_argument("-u", "--url", metavar="URL", help="URL of the instance to run operations.", required=required)


def add_shared_options(parser):
    # type: (argparse.ArgumentParser) -> None
    links_grp = parser.add_mutually_exclusive_group()
    links_grp.add_argument("-nL", "--no-links", dest="with_links", action="store_false",
                           help="Remove \"links\" section from returned result body.")
    links_grp.add_argument("-wL", "--with-links", dest="with_links", action="store_true", default=True,
                           help="Preserve \"links\" section from returned result body (default).")
    headers_grp = parser.add_mutually_exclusive_group()
    headers_grp.add_argument("-nH", "--no-headers", dest="with_headers", action="store_false", default=False,
                             help="Omit response headers, only returning the result body (default).")
    headers_grp.add_argument("-wH", "--with-headers", dest="with_headers", action="store_true",
                             help="Return response headers additionally to the result body.")
    parser.add_argument(
        "-H", "--header", action=ValidateHeaderAction, nargs=1, dest="headers", metavar="HEADER",
        help=(
            "Additional headers to apply for sending requests toward the service. "
            "This option can be provided multiple times, each with a value formatted as:\n\n'Header-Name: value'\n\n"
            "Header names are case-insensitive. "
            "Quotes can be used in the <value> portion to delimit it. "
            "Surrounding spaces are trimmed. "
            "Note that overridden headers expected by requests and the service could break some functionalities."
        )
    )
    fmt_docs = "\n\n".join([
        re.sub(r"\:[a-z]+\:\`([A-Za-z0-9_\-]+)\`", r"\1", f"{getattr(OutputFormat, fmt).upper()}: {doc}")  # remove RST
        for fmt, doc in sorted(OutputFormat.docs().items()) if doc
    ])
    fmt_choices = [fmt.upper() for fmt in sorted(OutputFormat.values())]
    parser.add_argument(
        "-F", "--format", choices=fmt_choices, type=str.upper, dest="output_format",
        help=(
            f"Select an alternative output representation (default: {OutputFormat.JSON_STR.upper()}, case-insensitive)."
            f"\n\n{fmt_docs}"
        )
    )

    req_grp = parser.add_argument_group(
        title="Request Arguments",
        description="Parameters to control specific options related to HTTP request handling."
    )
    req_grp.add_argument(
        "-rT", "--request-timeout", dest="request_timeout", action=ValidateNonZeroPositiveNumberAction, type=int,
        default=5, help=(
            "Maximum timout duration (seconds) to wait for a response when "
            "performing HTTP requests (default: %(default)ss)."
        )
    )
    req_grp.add_argument(
        "-rR", "--request-retries", dest="request_retries", action=ValidateNonZeroPositiveNumberAction, type=int,
        help="Amount of attempt to retry HTTP requests in case of failure (default: no retry)."
    )

    auth_grp = parser.add_argument_group(
        title="Service Authentication Arguments",
        description="Parameters to obtain access to a protected service using a request authentication handler."
    )
    auth_handlers = "".join([
        f"{fully_qualified_name(handler)}\n"
        for handler in [BasicAuthHandler, BearerAuthHandler, CookieAuthHandler]
    ])
    auth_grp.add_argument(
        "-aC", "--auth-class", "--auth-handler", dest="auth_handler", metavar="AUTH_HANDLER_CLASS",
        action=ValidateAuthHandlerAction,
        help=(
            "Script or module path reference to class implementation to handle inline request authentication. "
            "Format [path/to/script.py:module.AuthHandlerClass] or [installed.module.AuthHandlerClass] is expected.\n\n"
            f"Utility definitions are available as:\n\n{auth_handlers}\n\n"
            "Custom implementations are allowed for more advanced use cases."
        )
    )
    auth_grp.add_argument(
        "-aI", "--auth-identity", "--auth-username", dest="auth_identity", metavar="IDENTITY",
        help="Authentication identity (or username) to be passed down to the specified Authentication Handler."
    )
    auth_grp.add_argument(
        "-aP", "--auth-password", dest="auth_password", metavar="PASSWORD",
        help="Authentication password to be passed down to the specified Authentication Handler."
    )
    auth_grp.add_argument(
        "-aU", "--auth-url",
        help="Authentication URL to be passed down to the specified Authentication Handler."
    )
    auth_grp.add_argument(
        "-aM", "--auth-method", dest="auth_method", metavar="HTTP_METHOD",
        action=ValidateMethodAction, choices=ValidateMethodAction.methods, type=str.upper,
        default=AuthHandler.method,
        help=(
            "Authentication HTTP request method to be passed down to the specified Authentication Handler "
            "(default: %(default)s, case-insensitive)."
        )
    )
    auth_grp.add_argument(
        "-aH", "--auth-header", action=ValidateHeaderAction, nargs=1, dest="auth_headers", metavar="HEADER",
        help=(
            "Additional headers to apply for sending requests when using the authentication handler. "
            "This option can be provided multiple times, each with a value formatted as:\n\n'Header-Name: value'\n\n"
            "Header names are case-insensitive. "
            "Quotes can be used in the <value> portion to delimit it. "
            "Surrounding spaces are trimmed."
        )
    )


def add_listing_options(parser, item):
    # type: (argparse.ArgumentParser, str) -> None
    parser.add_argument(
        "-P", "--page", dest="page", type=int,
        help=f"Specify the paging index for {item} listing."
    )
    parser.add_argument(
        "-N", "--number", "--limit", dest="limit", type=int,
        help=f"Specify the amount of {item} to list per page."
    )
    parser.add_argument(
        "-D", "--detail", dest="detail", action="store_true", default=False,
        help=f"Obtain detailed {item} descriptions instead of only their ID (default: %(default)s)."
    )
    sort_methods = SortMethods.get(item)
    if sort_methods:
        parser.add_argument(
            "-O", "--order", "--sort", dest="sort", choices=sort_methods, type=str.lower,
            help=f"Sorting field to list {item}. Name must be one of the fields supported by {item} objects."
        )


def parse_auth(kwargs):
    # type: (Dict[str, Union[Type[AuthHandler], str, None]]) -> Optional[AuthHandler]
    """
    Parses arguments that can define an authentication handler and remove them from dictionary for following calls.
    """
    auth_handler = kwargs.pop("auth_handler", None)
    auth_identity = kwargs.pop("auth_identity", None)
    auth_password = kwargs.pop("auth_password", None)
    auth_url = kwargs.pop("auth_url", None)
    auth_method = kwargs.pop("auth_method", None)
    auth_headers = kwargs.pop("auth_headers", {})
    if not (auth_handler and issubclass(auth_handler, (AuthHandler, AuthBase))):
        return None
    auth_handler_name = fully_qualified_name(auth_handler)
    auth_sign = inspect.signature(auth_handler)
    auth_opts = [
        ("username", auth_identity),
        ("identity", auth_identity),
        ("password", auth_password),
        ("url", auth_url),
        ("method", auth_method),
        ("headers", CaseInsensitiveDict(auth_headers)),
    ]
    if len(auth_sign.parameters) == 0:
        auth_handler = auth_handler()
        for auth_param, auth_option in auth_opts:
            if auth_option and hasattr(auth_handler, auth_param):
                setattr(auth_handler, auth_param, auth_option)
    else:
        auth_params = list(auth_sign.parameters)
        auth_kwargs = {opt: val for opt, val in auth_opts if opt in auth_params}
        # allow partial match of required parameters by name to better support custom implementations
        # (e.g.: 'MagpieAuth' using 'magpie_url' instead of plain 'url')
        for param_name, param in auth_sign.parameters.items():
            if param.kind not in [param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD]:
                continue
            if param_name not in auth_kwargs:
                for opt, val in auth_opts:
                    if param_name.endswith(opt):
                        LOGGER.debug("Using authentication partial match: [%s] -> [%s]", opt, param_name)
                        auth_kwargs[param_name] = val
                        break
        LOGGER.debug("Using authentication parameters: %s", auth_kwargs)
        auth_handler = auth_handler(**auth_kwargs)
    LOGGER.info("Will use specified Authentication Handler [%s] with provided options.", auth_handler_name)
    return auth_handler


def add_provider_param(parser, description=None, required=True):
    # type: (argparse.ArgumentParser, Optional[str], bool) -> None
    operation = parser.prog.split(" ")[-1]
    parser.add_argument(
        "-pI", "--provider", dest="provider_id", required=required,
        help=description if description else (
            "Identifier of a remote provider under which the referred process "
            f"can be found to run {operation} operation."
        )
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
        "-T", "--timeout", "--exec-timeout", dest="timeout", type=int, default=WeaverClient.monitor_timeout,
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


class ValidateAuthHandlerAction(argparse.Action):
    """
    Action that will validate that the input argument references an authentication handler that can be resolved.
    """
    def __call__(self, parser, namespace, auth_handler_ref, option_string=None):
        # type: (argparse.ArgumentParser, argparse.Namespace, Optional[str], Optional[str]) -> None
        """
        Validate the referenced authentication handler implementation.
        """
        if not (auth_handler_ref and isinstance(auth_handler_ref, str)):
            return None
        auth_handler = import_target(auth_handler_ref)
        if not auth_handler:
            error = f"Could not resolve class reference to specified Authentication Handler: [{auth_handler_ref}]."
            raise argparse.ArgumentError(self, error)
        auth_handler_name = fully_qualified_name(auth_handler)
        if not issubclass(auth_handler, (AuthHandler, AuthBase)):
            error = (
                f"Resolved Authentication Handler [{auth_handler_name}] is "
                "not of appropriate sub-type: oneOf[AuthHandler, AuthBase]."
            )
            raise argparse.ArgumentError(self, error)
        setattr(namespace, self.dest, auth_handler)


class ValidateMethodAction(argparse.Action):
    """
    Action that will validate that the input argument one of the accepted HTTP methods.
    """
    methods = ["GET", "HEAD", "POST", "PUT", "DELETE"]

    def __call__(self, parser, namespace, values, option_string=None):
        # type: (argparse.ArgumentParser, argparse.Namespace, Union[str, Sequence[Any], None], Optional[str]) -> None
        """
        Validate the method value.
        """
        if values not in self.methods:
            allow = ", ".join(self.methods)
            error = f"Value '{values}' is not a valid HTTP method, must be one of [{allow}]."
            raise argparse.ArgumentError(self, error)
        setattr(namespace, self.dest, values)


class ValidateHeaderAction(argparse._AppendAction):  # noqa: W0212
    """
    Action that will validate that the input argument is a correctly formed HTTP header name.

    Each header should be provided as a separate option using format:

    .. code-block:: text

        Header-Name: Header-Value
    """
    def __call__(self, parser, namespace, values, option_string=None):
        # type: (argparse.ArgumentParser, argparse.Namespace, Union[str, Sequence[Any], None], Optional[str]) -> None
        """
        Validate the header value.
        """
        # items are received one by one with successive calls to this method on each matched (repeated) option
        # gradually convert them to header representation
        super(ValidateHeaderAction, self).__call__(parser, namespace, values, option_string)
        values = getattr(namespace, self.dest, [])
        headers = []
        if values:
            for val in values:
                if isinstance(val, tuple):  # skip already processed
                    headers.append(val)
                    continue
                if isinstance(val, list) and len(val) == 1:  # if nargs=1
                    val = val[0]
                hdr = re.match(r"^\s*(?P<name>[\w+\-]+)\s*\:\s*(?P<value>.*)$", val)
                if not hdr:
                    error = f"Invalid header '{val}' is missing name or value separated by ':'."
                    raise argparse.ArgumentError(self, error)
                if len(hdr["value"]) >= 2 and hdr["value"][0] in ["\"'"] and hdr["value"][-1] in ["\"'"]:
                    value = hdr["value"][1:-1]
                else:
                    value = hdr["value"]
                name = hdr["name"].replace("_", "-")
                headers.append((name, value))
        setattr(namespace, self.dest, headers)


class ValidateNonZeroPositiveNumberAction(argparse.Action):
    """
    Action that will validate that the input argument is a positive number greater than zero.
    """
    def __call__(self, parser, namespace, values, option_string=None):
        # type: (argparse.ArgumentParser, argparse.Namespace, Union[str, Sequence[Any], None], Optional[str]) -> None
        """
        Validate the value.
        """
        if not isinstance(values, (float, int)):
            raise argparse.ArgumentError(self, f"Value '{values} is not numeric.")
        if not values >= 1:
            raise argparse.ArgumentError(self, f"Value '{values} is not greater than zero.")
        setattr(namespace, self.dest, values)


class ParagraphFormatter(argparse.HelpFormatter):
    @property
    def help_mode(self):
        parser = getattr(self, "parser", None)
        if isinstance(parser, WeaverArgumentParser):
            return parser.help_mode
        return False

    @help_mode.setter
    def help_mode(self, mode):
        parser = getattr(self, "parser", None)
        if isinstance(parser, WeaverArgumentParser):
            parser.help_mode = mode

    def format_help(self):
        # type: () -> str
        mode = self.help_mode
        self.help_mode = True
        text = super(ParagraphFormatter, self).format_help()
        if self.help_mode != mode:
            self.help_mode = mode
        return text

    def _format_usage(self, *args, **kwargs):  # type: ignore
        mode = self.help_mode
        self.help_mode = True
        text = super(ParagraphFormatter, self)._format_usage(*args, **kwargs)

        # patch invalid closing combinations of [()] caused by mutually exclusive group with nested inclusive group
        # (see docker auth parameters hacks)
        # depending on Python version, the erroneously generated options are slightly different:
        # - [ -X opt | (-Y opt | -z opt])
        # - [ -X opt | (-Y opt | -z opt)
        search = r"(\[[\-\w\s]+\|\s*)\((([\-\w\s]+)(\|([\-\w\s]+))+)\]?\)"

        def replace(match):
            # type: (re.Match) -> str
            grp = match.groups()
            found = []
            for i in range(2, len(grp), 2):
                found.append(grp[i].strip())
            return f"{grp[0]}( {' '.join(found)} )]"

        text = re.sub(search, replace, text)
        if self.help_mode != mode:
            self.help_mode = mode
        return text

    def _format_action(self, action):
        # type: (argparse.Action) -> str
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
            # process each paragraph individually, so it fills the available width space
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
            # following is like calling 'add_mutually_exclusive_group' but avoids enforced '_MutuallyExclusiveGroup'
            # use provided instance directly to preserve class implementation (an any added special handling)
            self._mutually_exclusive_groups.append(group)
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


class WeaverSubParserAction(argparse._SubParsersAction):  # noqa: W0212
    def add_parser(self, *args, **kwargs):  # type: ignore
        sub_parser = super(WeaverSubParserAction, self).add_parser(*args, **kwargs)
        parser = getattr(self, "parser", None)  # type: WeaverArgumentParser
        sub_parser._conditional_groups = parser._conditional_groups
        sub_parser._help_mode = parser._help_mode
        parent_parsers = kwargs.get("parents", [])
        for _parser in [parser] + parent_parsers:
            sub_parser._formatters.update(_parser._formatters)
            # propagate sub parser such that full '<main> <mode>' is used as program name if error
            for rule in _parser._rules:
                rule = (sub_parser, *rule[1:])
                sub_parser._rules.add(rule)  # type: ignore
        return sub_parser


class WeaverArgumentParser(ArgumentParserFixedRequiredArgs, SubArgumentParserFixedMutexGroups):
    """
    Parser that provides fixes for proper representation of `Weaver` :term:`CLI` arguments.
    """

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super(WeaverArgumentParser, self).__init__(*args, **kwargs)
        self._help_mode = False
        self._conditional_groups = set()    # type: Set[ConditionalGroup]
        self._formatters = set()            # type: Set[PostHelpFormatter]
        self._rules = set()                 # type: Set[ArgumentParserRule]

    def add_subparsers(self, *args, **kwargs):  # type: ignore
        self.register("action", "parsers", WeaverSubParserAction)
        group = super(WeaverArgumentParser, self).add_subparsers(*args, **kwargs)  # type: WeaverSubParserAction
        setattr(group, "parser", self)
        return group

    @property
    def help_mode(self):
        """
        Option enabled only during help formatting to generate different conditional evaluations.
        """
        return self._help_mode

    @help_mode.setter
    def help_mode(self, mode):
        if self._help_mode != mode:
            self._help_mode = mode
            for group, help_required, use_required in self._conditional_groups:
                group.required = help_required if self._help_mode else use_required

    def add_help_conditional(self, container, help_required=True, use_required=False):
        # type: (argparse._ActionsContainer, bool, bool) -> argparse._ActionsContainer  # noqa
        setattr(container, "required", use_required)
        self._conditional_groups.add((container, help_required, use_required))
        return container

    def add_formatter(self, formatter):
        # type: (Callable[[str], str]) -> None
        """
        Define a POST-help formatter.
        """
        self._formatters.add(formatter)

    def _get_formatter(self):
        # type: () -> argparse.HelpFormatter
        formatter = super(WeaverArgumentParser, self)._get_formatter()
        setattr(formatter, "parser", self)
        return formatter

    def format_help(self):
        # type: () -> str
        self.help_mode = True
        text = f"{super(WeaverArgumentParser, self).format_help()}\n"
        for fmt in self._formatters:
            text = fmt(text)
        self.help_mode = False
        return text

    def add_rule(self, rule, failure):
        # type: (Callable[[argparse.Namespace], Optional[bool]], str) -> None
        self._rules.add((self, rule, failure))

    def parse_known_args(self, args=None, namespace=None):
        # type: (Optional[Sequence[str]], Optional[argparse.Namespace]) -> Tuple[argparse.Namespace, Sequence[str]]
        """
        Parse argument actions with handling of additional rules if any were defined.

        .. note::
            It is important to derive and call :meth:`parse_known_args` rather than :meth:`parse_args` to ensure
            nested subparsers rules validation can also be invoked.
        """
        ns, args = super(WeaverArgumentParser, self).parse_known_args(args=args, namespace=namespace)
        for container, rule, failure in self._rules:
            if rule(ns) not in [None, True]:
                container.error(failure)
        return ns, args


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

    desc = f"Run {__meta__.__title__} operations."
    parser = WeaverArgumentParser(prog=__meta__.__name__, description=desc, parents=[log_parser])
    set_parser_sections(parser)
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__meta__.__version__}",
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
    docker_auth_title = "Docker Authentication Arguments"
    docker_auth_desc = "Parameters to obtain access to a protected Docker registry to retrieve the referenced image."
    op_deploy_group = op_deploy.add_argument_group(
        title=docker_auth_title,
        description=docker_auth_desc,
    )
    op_deploy_token = op_deploy_group.add_argument_group(title=docker_auth_title, description=docker_auth_desc)
    op_deploy_creds = op_deploy_token.add_argument_group(title=docker_auth_title, description=docker_auth_desc)
    op_deploy_tkt = op_deploy_token.add_argument(
        "-T", "--token", dest="token",
        help="Authentication token to retrieve a Docker image reference from a protected registry during execution."
    )
    op_deploy_usr = op_deploy_creds.add_argument(
        "-U", "--username", dest="username",
        help="Username to compute the authentication token for Docker image retrieval from a protected registry."
    )
    op_deploy_pwd = op_deploy_creds.add_argument(
        "-P", "--password", dest="password",
        help="Password to compute the authentication token for Docker image retrieval from a protected registry."
    )

    # when actions are evaluated for actual executions, conditional 'required' will consider them as options
    # when actions are printed in help, they will be considered required, causing ( ) to be added to form the
    # rendered group of *mutually required* arguments
    parser.add_help_conditional(op_deploy_creds)
    # following adjust references in order to make arguments appear within sections/groups as intended
    op_deploy_mutex_usr_tkt = op_deploy_group.add_mutually_exclusive_group()
    op_deploy_mutex_usr_tkt._group_actions.append(op_deploy_usr)
    op_deploy_mutex_usr_tkt._group_actions.append(op_deploy_tkt)
    op_deploy_mutex_pwd_tkt = op_deploy_group.add_mutually_exclusive_group()
    op_deploy_mutex_pwd_tkt._group_actions.append(op_deploy_pwd)
    op_deploy_mutex_pwd_tkt._group_actions.append(op_deploy_tkt)
    op_deploy_group._group_actions.append(op_deploy_usr)
    op_deploy_group._group_actions.append(op_deploy_pwd)
    op_deploy_group._group_actions.append(op_deploy_tkt)
    # force a specific representation and validation of arguments to better reflect expected combinations
    op_deploy.add_formatter(
        lambda _help: _help.replace(
            "[-T TOKEN] [-U USERNAME] [-P PASSWORD]",
            "[-T TOKEN | ( -U USERNAME -P PASSWORD )]"
        )
    )
    op_deploy.add_rule(
        lambda _ns: bool(_ns.username) == bool(_ns.password),
        "argument -U/--username: must be combined with -P/--password"
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

    op_register = WeaverArgumentParser(
        "register",
        description="Register a remote provider.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_register)
    add_url_param(op_register)
    add_shared_options(op_register)
    add_provider_param(op_register)
    op_register.add_argument(
        "-pU", "--provider-url", dest="provider_url", required=True,
        help="Endpoint URL of the remote provider to register."
    )

    op_unregister = WeaverArgumentParser(
        "unregister",
        description="Unregister a remote provider.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_unregister)
    add_url_param(op_unregister)
    add_shared_options(op_unregister)
    add_provider_param(op_unregister)

    op_capabilities = WeaverArgumentParser(
        "capabilities",
        description="List available processes.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_capabilities)
    add_url_param(op_capabilities)
    add_shared_options(op_capabilities)
    add_listing_options(op_capabilities, item="process")
    prov_args_grp = op_capabilities.add_argument_group(
        title="Remote Provider Arguments",
        description="Parameters related to remote providers reporting."
    )
    prov_show_grp = prov_args_grp.add_mutually_exclusive_group()
    prov_show_grp.add_argument("-nP", "--no-providers", dest="with_providers", action="store_false", default=False,
                               help="Omit \"providers\" listing from returned result body (default).")
    prov_show_grp.add_argument("-wP", "--with-providers", dest="with_providers", action="store_true",
                               help="Include \"providers\" listing in returned result body along with local processes.")

    op_describe = WeaverArgumentParser(
        "describe",
        description="Obtain an existing process description.",
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_describe)
    add_url_param(op_describe)
    add_shared_options(op_describe)
    add_process_param(op_describe)
    add_provider_param(op_describe, required=False)
    op_describe.add_argument(
        "-S", "--schema", dest="schema", choices=ProcessSchema.values(), type=str.upper, default=ProcessSchema.OGC,
        help="Representation schema of the returned process description (default: %(default)s, case-insensitive)."
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
    add_provider_param(op_execute, required=False)
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
            supply an explicit empty input (i.e.: ``-I ""`` or loaded from JSON/YAML file as ``{}``).

            To provide inputs using literal command-line definitions, inputs should be specified using ``<id>=<value>``
            convention, with distinct ``-I`` options for each applicable input value.

            Values that require other type than string to be converted for job submission can include the data type
            following the ID using a colon separator (i.e.: ``<id>:<type>=<value>``). For example, an integer could be
            specified as follows: ``number:int=1`` while a floating point number would be: ``number:float=1.23``.

            File references (``href``) should be specified using ``File`` as the type (i.e.: ``input:File=http://...``).
            Note that ``File`` in this case is expected to be an URL location where the file can be downloaded from.
            When a local file is supplied, Weaver will automatically convert it to a remote Vault File in order to
            upload it at the specified URL location and make it available for the remote process.

            Inputs with multiplicity (``maxOccurs > 1``) can be specified using semicolon (``;``) separated values
            after a single input ID. Note that this is not the same as a single-value array-like input, which should
            use comma (``,``) separated values instead.
            The type of an element-wise item of this input can also be provided (i.e.: ``multiInput:int=1;2;3``).
            Alternatively, the same input ID can be repeated over many ``-I`` options each providing an element of the
            multi-value input to be formed (i.e.: ``-I multiInput=1 -I multiInput=2 -I multiInput=3``).

            Additional parameters can be specified following any ``<value>`` using any amount of ``@<param>=<info>``
            specifiers. Those will be added to the inputs body submitted for execution. This can be used, amongst other
            things, to provide a file's ``mediaType`` or ``encoding`` details. When using multi-value inputs, each item
            value can take ``@`` parameters independently with distinct properties.

            Any value that contains special separator characters (``:;@``) to be used as literal entries
            must be URL-encoded (``%%XX``) to avoid invalid parsing.

            Example: ``-I message='Hello Weaver' -I value:int=1234 -I file:File=data.xml@mediaType=text/xml``
        """)
    )
    # FIXME: allow filtering 'outputs' (https://github.com/crim-ca/weaver/issues/380)
    #   Only specified ones are returned, if none specified, return all.
    # op_execute.add_argument(
    #    "-O", "--output",
    op_execute.add_argument(
        "-R", "--ref", "--reference", metavar="REFERENCE", dest="output_refs", action="append",
        help=inspect.cleandoc("""
            Indicates which outputs by ID to be returned as HTTP Link header reference instead of body content value.
            This defines the output transmission mode when submitting the execution request.

            With reference transmission mode,
            outputs that contain literal data will be linked by ``text/plain`` file containing the data.
            Outputs that refer to a file reference will simply contain that URL reference as link.

            With value transmission mode (default behavior when outputs are not specified in this list), outputs are
            returned as direct values (literal or href) within the response content body.

            When requesting any output to be returned by reference, option ``-H/--headers`` should be considered as
            well to return the provided ``Link`` headers for these outputs on the command line.

            Example: ``-R output-one -R output-two``
        """)
    )
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
    add_listing_options(op_jobs, item="job")
    op_jobs.add_argument(
        "-S", "--status", dest="status", choices=Status.values(), type=str.lower, nargs="+",
        help="Filter job listing only to matching status. If multiple are provided, must match one of them."
    )
    op_jobs.add_argument(
        "-G", "--groups", dest="groups", action="store_true",
        help="Obtain grouped representation of jobs per provider and process categories."
    )
    op_jobs.add_argument(
        "-fP", "--process", dest="process",
        help="Filter job listing only to matching process (local and/or remote whether combined with '-fS')."
    )
    op_jobs.add_argument(
        "-fS", "--provider", "--service", dest="provider",
        help="Filter job listing only to matching remote service provider."
    )
    op_jobs.add_argument(
        "-fT", "--tags", dest="tags", type=str.lower, nargs="+",
        help="Filter job listing only to matching tags. Jobs must match all tags simultaneously, not one of them."
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

    op_logs = WeaverArgumentParser(
        "logs",
        description=(
            "Obtain the logs of a job using a reference UUID or URL. "
            "Only guaranteed by Weaver instances. Pure 'OGC API - Processes' servers might not implement this feature."
        ),
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_logs)
    add_url_param(op_logs, required=False)
    add_job_ref_param(op_logs)
    add_shared_options(op_logs)

    op_exceptions = WeaverArgumentParser(
        "exceptions",
        description=(
            "Obtain the exceptions and error details of a failed job using a reference UUID or URL. "
            "If the job is not marked with failed status, this will return an error. "
            "Only guaranteed by Weaver instances. Pure 'OGC API - Processes' servers might not implement this feature."
        ),
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_exceptions)
    add_url_param(op_exceptions, required=False)
    add_job_ref_param(op_exceptions)
    add_shared_options(op_exceptions)

    op_statistics = WeaverArgumentParser(
        "statistics",
        description=(
            "Obtain the computation statistics details of a successful job using a reference UUID or URL. "
            "If the job is not marked with succeeded status, this will return an error. "
            "Only guaranteed by Weaver instances. Pure 'OGC API - Processes' servers might not implement this feature."
        ),
        formatter_class=ParagraphFormatter,
    )
    set_parser_sections(op_statistics)
    add_url_param(op_statistics, required=False)
    add_job_ref_param(op_statistics)
    add_shared_options(op_statistics)

    op_results = WeaverArgumentParser(
        "results",
        description=(
            "Obtain the output results from a job successfully executed. "
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
        op_register,
        op_unregister,
        op_capabilities,
        op_describe,
        op_execute,
        op_jobs,
        op_monitor,
        op_dismiss,
        op_status,
        op_logs,
        op_exceptions,
        op_statistics,
        op_results,
        op_upload,
    ]
    aliases = {
        "processes": op_capabilities,
        "errors": op_exceptions,
        "stats": op_statistics,
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
    # type: (*str) -> int
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
    auth = parse_auth(kwargs)
    client = WeaverClient(url, auth=auth)
    try:
        result = getattr(client, oper)(**kwargs)
    except Exception as exc:
        msg = "Operation failed due to exception."
        err = fully_qualified_name(exc)
        result = OperationResult(False, message=msg, body={"message": msg, "cause": str(exc), "error": err})
    if result.success:
        LOGGER.info("%s successful. %s\n", oper.title(), result.message)
        print(result.text)  # use print in case logger disabled or level error/warn
        return 0
    LOGGER.error("%s failed. %s\n---\nStatus Code: %s\n---", oper.title(), result.message, result.code)
    print(result.text)
    return -1


if __name__ == "__main__":
    sys.exit(main())
