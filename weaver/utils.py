import errno
import inspect
import logging
import os
import re
import shutil
import sys
import time
import types
import warnings
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING

import pytz
import requests
import six
from celery.app import Celery
from lxml import etree
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPError as PyramidHTTPError, HTTPGatewayTimeout, HTTPTooManyRequests
from pyramid.registry import Registry
from pyramid.request import Request
from pyramid.settings import asbool, aslist
from requests import HTTPError as RequestsHTTPError, Response
from requests.structures import CaseInsensitiveDict
from requests_file import FileAdapter
from six.moves.urllib.parse import ParseResult, parse_qs, urlparse, urlunsplit
from urlmatch import urlmatch
from webob.headers import EnvironHeaders, ResponseHeaders

from weaver.exceptions import InvalidIdentifierValue
from weaver.status import map_status
from weaver.warning import TimeZoneInfoAlreadySetWarning

if TYPE_CHECKING:
    from weaver.typedefs import (                                                               # noqa: F401
        AnyValue, AnyKey, AnySettingsContainer, AnyRegistryContainer, AnyHeadersContainer,
        AnyResponseType, HeadersType, SettingsType, JSON, XML, Number
    )
    from typing import Union, Any, Dict, List, AnyStr, Iterable, Optional, Type                 # noqa: F401

LOGGER = logging.getLogger(__name__)


class _Singleton(type):
    __instance__ = None  # type: Optional[_Singleton]

    def __call__(cls):
        if cls.__instance__ is None:
            cls.__instance__ = super(_Singleton, cls).__call__()
        return cls.__instance__


class _NullType(six.with_metaclass(_Singleton)):
    """Represents a ``null`` value to differentiate from ``None``."""

    # pylint: disable=E1101,no-member
    def __eq__(self, other):
        return (isinstance(other, _NullType)                                    # noqa: W503
                or other is null                                                # noqa: W503
                or other is self.__instance__                                   # noqa: W503
                or (inspect.isclass(other) and issubclass(other, _NullType)))   # noqa: W503

    def __repr__(self):
        return "<null>"

    @staticmethod
    def __nonzero__():
        return False

    __bool__ = __nonzero__
    __len__ = __nonzero__


# pylint: disable=C0103,invalid-name
null = _NullType()


def get_weaver_url(container):
    # type: (AnySettingsContainer) -> AnyStr
    """Retrieves the home URL of the `weaver` application."""
    value = get_settings(container).get("weaver.url", "") or ""  # handle explicit None
    return value.rstrip("/").strip()


def get_any_id(info):
    # type: (JSON) -> Union[AnyStr, None]
    """Retrieves a dictionary `id-like` key using multiple common variations ``[id, identifier, _id]``.
    :param info: dictionary that potentially contains an `id-like` key.
    :returns: value of the matched `id-like` key or ``None`` if not found."""
    return info.get("id", info.get("identifier", info.get("_id")))


def get_any_value(info):
    # type: (JSON) -> AnyValue
    """Retrieves a dictionary `value-like` key using multiple common variations ``[href, value, reference]``.
    :param info: dictionary that potentially contains a `value-like` key.
    :returns: value of the matched `value-like` key or ``None`` if not found."""
    return info.get("href", info.get("value", info.get("reference", info.get("data"))))


def get_any_message(info):
    # type: (JSON) -> AnyStr
    """Retrieves a dictionary 'value'-like key using multiple common variations [message].
    :param info: dictionary that potentially contains a 'message'-like key.
    :returns: value of the matched 'message'-like key or an empty string if not found. """
    return info.get("message", "").strip()


def get_registry(container):
    # type: (AnyRegistryContainer) -> Registry
    """Retrieves the application ``registry`` from various containers referencing to it."""
    if isinstance(container, Celery):
        return container.conf.get("PYRAMID_REGISTRY", {})
    if isinstance(container, (Configurator, Request)):
        return container.registry
    if isinstance(container, Registry):
        return container
    raise TypeError("Could not retrieve registry from container object of type [{}].".format(type(container)))


def get_settings(container):
    # type: (AnySettingsContainer) -> SettingsType
    """Retrieves the application ``settings`` from various containers referencing to it."""
    if isinstance(container, (Celery, Configurator, Request)):
        container = get_registry(container)
    if isinstance(container, Registry):
        return container.settings
    if isinstance(container, dict):
        return container
    raise TypeError("Could not retrieve settings from container object of type [{}]".format(type(container)))


def get_header(header_name, header_container):
    # type: (AnyStr, AnyHeadersContainer) -> Union[AnyStr, None]
    """
    Searches for the specified header by case/dash/underscore-insensitive ``header_name`` inside ``header_container``.
    """
    if header_container is None:
        return None
    headers = header_container
    if isinstance(headers, (ResponseHeaders, EnvironHeaders, CaseInsensitiveDict)):
        headers = dict(headers)
    if isinstance(headers, dict):
        headers = header_container.items()
    header_name = header_name.lower().replace("-", "_")
    for h, v in headers:
        if h.lower().replace("-", "_") == header_name:
            return v
    return None


def get_cookie_headers(header_container, cookie_header_name="Cookie"):
    # type: (AnyHeadersContainer, Optional[AnyStr]) -> HeadersType
    """
    Looks for ``cookie_header_name`` header within ``header_container``.
    :returns: new header container in the form ``{'Cookie': <found_cookie>}`` if it was matched, or empty otherwise.
    """
    try:
        cookie = get_header(cookie_header_name, header_container)
        if cookie:
            return dict(Cookie=get_header(cookie_header_name, header_container))
        return {}
    except KeyError:  # No cookie
        return {}


def get_url_without_query(url):
    # type: (Union[AnyStr, ParseResult]) -> AnyStr
    """Removes the query string part of an URL."""
    if isinstance(url, six.string_types):
        url = urlparse(url)
    if not isinstance(url, ParseResult):
        raise TypeError("Expected a parsed URL.")
    return urlunsplit(url[:4] + tuple([""]))


def is_valid_url(url):
    # type: (Union[AnyStr, None]) -> bool
    try:
        return bool(urlparse(url).scheme)
    except Exception:  # noqa: W0703 # nosec: B110
        return False


def parse_extra_options(option_str):
    """
    Parses the extra options parameter.

    The option_str is a string with coma separated ``opt=value`` pairs.
    Example::

        tempdir=/path/to/tempdir,archive_root=/path/to/archive

    :param option_str: A string parameter with the extra options.
    :return: A dict with the parsed extra options.
    """
    if option_str:
        try:
            # pylint: disable=R1717,consider-using-dict-comprehension
            extra_options = option_str.split(",")
            extra_options = dict([("=" in opt) and opt.split("=", 1) for opt in extra_options])
        except Exception:
            msg = "Can not parse extra-options: {}".format(option_str)
            from pyramid.exceptions import ConfigurationError
            raise ConfigurationError(msg)
    else:
        extra_options = {}
    return extra_options


def fully_qualified_name(obj):
    # type: (Union[Any, Type[Any]]) -> str
    """Obtains the ``'<module>.<name>'`` full path definition of the object to allow finding and importing it."""
    cls = obj if inspect.isclass(obj) or inspect.isfunction(obj) else type(obj)
    return ".".join([obj.__module__, cls.__name__])


def now():
    # type: (...) -> datetime
    return localize_datetime(datetime.utcnow())


def now_secs():
    # type: (...) -> int
    """
    Return the current time in seconds since the Epoch.
    """
    return int(time.time())


def wait_secs(run_step=-1):
    secs_list = (2, 2, 2, 2, 2, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 20, 20, 20, 20, 20, 30)
    if run_step >= len(secs_list):
        run_step = -1
    return secs_list[run_step]


def expires_at(hours=1):
    # type: (Optional[int]) -> int
    return now_secs() + hours * 3600


def localize_datetime(dt, tz_name="UTC"):
    # type: (datetime, Optional[AnyStr]) -> datetime
    """
    Provide a timezone-aware object for a given datetime and timezone name
    """
    tz_aware_dt = dt
    if dt.tzinfo is None:
        utc = pytz.timezone("UTC")
        aware = utc.localize(dt)
        timezone = pytz.timezone(tz_name)
        tz_aware_dt = aware.astimezone(timezone)
    else:
        warnings.warn("tzinfo already set", TimeZoneInfoAlreadySetWarning)
    return tz_aware_dt


def get_base_url(url):
    # type: (AnyStr) -> AnyStr
    """
    Obtains the base URL from the given ``url``.
    """
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        raise ValueError("bad url")
    service_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path.strip())
    return service_url


def xml_path_elements(path):
    # type: (AnyStr) -> List[AnyStr]
    elements = [el.strip() for el in path.split("/")]
    elements = [el for el in elements if len(el) > 0]
    return elements


def xml_strip_ns(tree):
    # type: (XML) -> None
    for node in tree.iter():
        try:
            has_namespace = node.tag.startswith("{")
        except AttributeError:
            continue  # node.tag is not a string (node is a comment or similar)
        if has_namespace:
            node.tag = node.tag.split("}", 1)[1]


def ows_context_href(href, partial=False):
    # type: (AnyStr, Optional[bool]) -> JSON
    """Returns the complete or partial dictionary defining an ``OWSContext`` from a reference."""
    context = {"offering": {"content": {"href": href}}}
    if partial:
        return context
    return {"owsContext": context}


def pass_http_error(exception, expected_http_error):
    # type: (Exception, Union[PyramidHTTPError, Iterable[PyramidHTTPError]]) -> None
    """
    Given an `HTTPError` of any type (pyramid, requests), ignores (pass) the exception if the actual
    error matches the status code. Other exceptions are re-raised.

    :param exception: any `Exception` instance ("object" from a `try..except exception as "object"` block).
    :param expected_http_error: single or list of specific pyramid `HTTPError` to handle and ignore.
    :raise exception: if it doesn't match the status code or is not an `HTTPError` of any module.
    """
    if not hasattr(expected_http_error, "__iter__"):
        expected_http_error = [expected_http_error]
    if isinstance(exception, (PyramidHTTPError, RequestsHTTPError)):
        try:
            status_code = exception.status_code
        except AttributeError:
            # exception may be a response raised for status in which case status code is here:
            status_code = exception.response.status_code

        if status_code in [e.code for e in expected_http_error]:
            return
    raise exception


def raise_on_xml_exception(xml_node):
    """
    Raises an exception with the description if the XML response document defines an ExceptionReport.
    :param xml_node: instance of :class:`etree.Element`
    :raise Exception: on found ExceptionReport document.
    """
    if not isinstance(xml_node, etree._Element):  # noqa: W0212
        raise TypeError("Invalid input, expecting XML element node.")
    if "ExceptionReport" in xml_node.tag:
        node = xml_node
        while len(node.getchildren()):
            node = node.getchildren()[0]
        raise Exception(node.text)


def str2bytes(string):
    # type: (Union[AnyStr, bytes]) -> bytes
    """Obtains the bytes representation of the string."""
    if not isinstance(string, (six.string_types, bytes)):
        raise TypeError("Cannot convert item to bytes: {!r}".format(type(string)))
    if isinstance(string, bytes):
        return string
    return string.encode()


def bytes2str(string):
    # type: (Union[AnyStr, bytes]) -> str
    """Obtains the unicode representation of the string."""
    if not isinstance(string, (six.string_types, bytes)):
        raise TypeError("Cannot convert item to unicode: {!r}".format(type(string)))
    if not isinstance(string, bytes):
        return string
    return string.decode()


def islambda(func):
    # type: (Any) -> bool
    return isinstance(func, types.LambdaType) and func.__name__ == (lambda: None).__name__


first_cap_re = re.compile(r"(.)([A-Z][a-z]+)")
all_cap_re = re.compile(r"([a-z0-9])([A-Z])")


def convert_snake_case(name):
    # type: (AnyStr) -> AnyStr
    s1 = first_cap_re.sub(r"\1_\2", name)
    return all_cap_re.sub(r"\1_\2", s1).lower()


def parse_request_query(request):
    # type: (Request) -> Dict[AnyStr, Dict[AnyKey, AnyStr]]
    """
    :param request:
    :return: dict of dict where k=v are accessible by d[k][0] == v and q=k=v are accessible by d[q][k] == v, lowercase
    """
    queries = parse_qs(request.query_string.lower())
    queries_dict = dict()
    for q in queries:
        queries_dict[q] = dict()
        for i, kv in enumerate(queries[q]):
            kvs = kv.split("=")
            if len(kvs) > 1:
                queries_dict[q][kvs[0]] = kvs[1]
            else:
                queries_dict[q][i] = kvs[0]
    return queries_dict


def get_log_fmt():
    # type: (...) -> AnyStr
    return "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"


def get_log_date_fmt():
    # type: (...) -> AnyStr
    return "%Y-%m-%d %H:%M:%S"


def get_log_monitor_msg(job_id, status, percent, message, location):
    # type: (AnyStr, AnyStr, Number, AnyStr, AnyStr) -> AnyStr
    return "Monitoring job {jobID} : [{status}] {percent} - {message} [{location}]".format(
        jobID=job_id, status=status, percent=percent, message=message, location=location
    )


def get_job_log_msg(status, message, progress=0, duration=None):
    # type: (AnyStr, AnyStr, Optional[Number], Optional[AnyStr]) -> AnyStr
    return "{d} {p:3d}% {s:10} {m}".format(d=duration or "", p=int(progress or 0), s=map_status(status), m=message)


def make_dirs(path, mode=0o755, exist_ok=False):
    """
    Alternative to ``os.makedirs`` with ``exists_ok`` parameter only available for ``python>3.5``.
    Also using a reduced set of permissions ``755`` instead of original default ``777``.

    .. note::
        The method employed in this function is safer then ``if os.pat.exists`` or ``if os.pat.isdir`` pre-check
        to calling ``os.makedirs`` as this can result in race condition (between evaluation and actual creation).
    """
    try:
        os.makedirs(path, mode=mode)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        if not exist_ok:
            raise


def get_caller_name(skip=2, base_class=False):
    """Returns the name of a caller in the format ``module.class.method``.

    :param skip: specifies how many levels of stack to skip while getting the caller.
    :param base_class:
        Specified if the base class should be returned or the top-most class in case of inheritance
        If the caller is not a class, this doesn't do anything.
    :returns: An empty string if skipped levels exceed stack height; otherwise, the requested caller name.
    """
    # reference: https://gist.github.com/techtonik/2151727

    def stack_(frame):
        frame_list = []
        while frame:
            frame_list.append(frame)
            frame = frame.f_back
        return frame_list

    stack = stack_(sys._getframe(1))  # noqa: W0212
    start = 0 + skip
    if len(stack) < start + 1:
        return ""
    parent_frame = stack[start]
    name = []
    module = inspect.getmodule(parent_frame)
    # `modname` can be None when frame is executed directly in console
    if module:
        # frame module in case of inherited classes will point to base class
        # but frame local will still refer to top-most class when checking for 'self'
        # (stack: top(mid).__init__ -> mid(base).__init__ -> base.__init__)
        name.append(module.__name__)
    # detect class name
    if "self" in parent_frame.f_locals:
        # I don't know any way to detect call from the object method
        # XXX: there seems to be no way to detect static method call - it will
        #      be just a function call
        cls = parent_frame.f_locals["self"].__class__
        if not base_class and module and inspect.isclass(cls):
            name[0] = cls.__module__
        name.append(cls.__name__)
    codename = parent_frame.f_code.co_name
    if codename != "<module>":  # top level usually
        name.append(codename)  # function or a method
    del parent_frame
    return ".".join(name)


def get_ssl_verify_option(method, url, settings, request_options=None):
    # type: (AnyStr, AnyStr, AnySettingsContainer, Optional[SettingsType]) -> bool
    """
    Obtains the SSL verification option from combined settings from ``weaver.ssl_verify`` and parsed
    ``weaver.request_options`` file for the corresponding request.

    :param method: request method (GET, POST, etc.).
    :param url: request URL.
    :param settings: application setting container with pre-loaded *request options* specifications.
    :param request_options: pre-processed *request options* for method/URL to avoid re-parsing the settings.
    :returns: SSL ``verify`` option to be passed down to some ``request`` function.
    """
    if not settings:
        return True
    settings = get_settings(settings)
    if not asbool(settings.get("weaver.ssl_verify", True)):
        return False
    req_opts = request_options or get_request_options(method, url, settings)
    if not req_opts.get("ssl_verify", req_opts.get("verify", True)):
        return False
    return True


def get_request_options(method, url, settings):
    # type: (AnyStr, AnyStr, AnySettingsContainer) -> SettingsType
    """
    Obtains the *request options* corresponding to the request according to configuration file specified by pre-loaded
    setting ``weaver.request_options``.

    If no file was pre-loaded or no match is found for the request, an empty options dictionary is returned.

    .. seealso::
        - :func:`get_ssl_verify_option`
        - `config/request_options.yml.example <../../config/config/request_options.yml.example>`_

    :param method: request method (GET, POST, etc.).
    :param url: request URL.
    :param settings: application setting container with pre-loaded *request options* specifications.
    :returns: dictionary with keyword options to be applied to the corresponding request if matched.
    """
    if not settings:
        LOGGER.warning("No settings container provided by [%s], request options might not be applied as expected.",
                       get_caller_name(skip=2))
        return {}
    settings = get_settings(settings)  # ensure settings, could be any container
    req_opts_specs = settings.get("weaver.request_options", None)
    if not isinstance(req_opts_specs, dict):
        # empty request options is valid (no file specified),
        # but none pre-processed by app means the settings come from unexpected source
        LOGGER.warning("Settings container provided by [%s] missing request options specification. "
                       "Request might not be executed with expected configuration.", get_caller_name(skip=2))
        return {}
    request_options = {}
    request_entries = req_opts_specs.get("requests", []) or []
    for req_opts in request_entries:
        req_meth = req_opts.get("method", "")
        if req_meth:
            methods = req_meth if isinstance(req_meth, list) else [req_meth]
            methods = [meth.upper() for meth in methods]
            if method.upper() not in methods:
                continue
        req_urls = req_opts.get("url")
        req_urls = [req_urls] if not isinstance(req_urls, list) else req_urls
        req_regex = []
        for req_url in req_urls:
            req_regex.extend(aslist(req_url))
        req_regex = ",".join(req_regex)
        if not url.endswith("/"):
            url = url + "/"  # allow 'domain.com' match since 'urlmatch' requires slash in 'domain.com/*'
        if not urlmatch(req_regex, url, path_required=False):
            continue
        req_opts = deepcopy(req_opts)
        req_opts.pop("url", None)
        req_opts.pop("method", None)
        return req_opts
    return request_options


def request_extra(method,                       # type: AnyStr
                  url,                          # type: AnyStr
                  retries=None,                 # type: Optional[int]
                  backoff=None,                 # type: Optional[Number]
                  intervals=None,               # type: Optional[List[Number]]
                  retry_after=True,             # type: bool
                  allowed_codes=None,           # type: Optional[List[int]]
                  only_server_errors=True,      # type: bool
                  ssl_verify=None,              # type: Optional[bool]
                  settings=None,                # type: Optional[AnySettingsContainer]
                  **request_kwargs,             # type: Any
                  ):                            # type: (...) -> AnyResponseType
    """
    Standard library :mod:`requests` with additional functional utilities.

    Retry operation
    ---------------

    Implements request retry if the previous request failed, up to the specified number of retries.
    Using :paramref:`backoff` factor, you can control the interval between request attempts such as::

        delay = backoff * (2 ^ retry)

    Alternatively, you can explicitly define ``intervals=[...]`` with the list values being the number of seconds to
    wait between each request attempt. In this case, :paramref:`backoff` is ignored and :paramref:`retries` is
    overridden accordingly with the number of items specified in the list.

    Furthermore, :paramref:`retry_after` (default: ``True``) indicates if HTTP status code ``429 (Too Many Requests)``
    should be automatically handled during retries. If enabled and provided in the previously failed request response
    through the ``Retry-After`` header, the next request attempt will be executed only after the server-specified delay
    instead of following the calculated delay from :paramref:`retries` and :paramref:`backoff`, or from corresponding
    index of :paramref:`interval`, accordingly to specified parameters. This will avoid uselessly calling the server and
    automatically receive a denied response. You can disable this feature by passing ``False``, which will result into
    requests being retried blindly without consideration of the called server instruction.

    Because different request implementations use different parameter naming conventions, all following keywords are
    looked for:
        - Both variants of ``backoff`` and ``backoff_factor`` are accepted.
        - All variants of ``retires``, ``retry`` and ``max_retries`` are accepted.

    .. note::
        Total amount of executed request attempts will be +1 the number of :paramref:`retries` or :paramref:`intervals`
        items as first request is done immediately, and following attempts are done with the appropriate delay.

    File Transport Scheme
    ---------------------

    Any request with ``file://`` scheme or empty scheme (no scheme specified) will be automatically handled as potential
    local file path. The path should be absolute to ensure it to be correctly resolved.

    All access errors due to file permissions return 403 status code, and missing file returns 404.
    Any other :py:exc:`IOError` types are converted to a 400 responses.

    .. seealso::
        - :class:`FileAdapter`

    SSL Verification
    ----------------

    Allows SSL verify option to be enabled or disabled according to configuration settings or explicit parameters.
    Any variation of ``verify`` or ``ssl_verify`` keyword arguments are considered. If they all resolve to ``True``,
    then application settings are retrieved from ``weaver.ini`` to parse additional SSL options that could disable it.

    Following :mod:`weaver` settings are considered :
        - `weaver.ssl_verify = True|False`
        - `weaver.request_options = request_options.yml`

    .. note::
        Argument :paramref:`settings` must also be provided through any supported container by :func:`get_settings`
        to retrieve and apply any :mod:`weaver`-specific configurations.

    .. seealso::
        - :func:`get_request_options`
        - :func:`get_ssl_verify_option`

    :param method: HTTP method to set request.
    :param url: URL of the request to execute.
    :param retries: Number of request retries to attempt if first attempt failed (according to allowed codes or error).
    :param backoff: Factor by which to multiply delays between retries.
    :param intervals: Explicit intervals in seconds between retries.
    :param allowed_codes: HTTP status codes that are considered valid to stop retrying (default: any non-4xx/5xx code).
    :param ssl_verify: Explicit parameter to disable SSL verification (overrides any settings, default: True).
    :param settings: Additional settings from which to retrieve configuration details for requests.
    :param only_server_errors:
        Only HTTP status codes in the 5xx values will be considered for retrying the request (default: True).
        This catches sporadic server timeout, connection error, etc., but 4xx errors are still considered valid results.
        This parameter is ignored if allowed codes are explicitly specified.
    :param request_kwargs: All other keyword arguments are passed down to the request call.
    """
    # obtain file request-options arguments, then override any explicitly provided source-code keywords
    settings = get_settings(settings) if settings else {}
    request_options = get_request_options(method, url, settings)
    request_options.update(request_kwargs)
    # catch kw passed to request corresponding to retries parameters
    kw_retries = request_options.pop("retries", request_options.pop("retry", request_options.pop("max_retries", None)))
    kw_backoff = request_options.pop("backoff", request_options.pop("backoff_factor", None))
    kw_intervals = request_options.pop("intervals", None)
    retries = retries or kw_retries or 0
    backoff = backoff or kw_backoff or 0.3
    intervals = intervals or kw_intervals
    if intervals and len(intervals) and all(isinstance(i, (int, float)) for i in intervals):
        intervals = [0] + intervals
        retries = list(range(len(intervals)))
        backoff = 0  # disable first part of delay calculation
    else:
        retries = [0] + list(range(retries))
    no_retries = len(retries) == 1
    # SSL verification settings
    # ON by default, disable accordingly with any variant if matched
    kw_ssl_verify = get_ssl_verify_option(method, url, settings, request_options=request_options)
    ssl_verify = False if not kw_ssl_verify or not ssl_verify else True  # pylint: disable=R1719
    request_options.update({"verify": ssl_verify})
    # process request
    resp = None
    failures = []
    for retry in retries:
        if retry:
            delay = 0
            if retry_after and resp and resp.status_code in [HTTPTooManyRequests.code]:
                after = resp.headers.get("Retry-After", "")
                delay = int(after) if str(after).isdigit() else 0
                LOGGER.debug("Received header [Retry-After=%ss] for [%s %s]", after, method, url)
            if not delay:
                delay = (backoff * (2 ** (retry + 1))) or intervals[retry]
            LOGGER.debug("Retrying failed request after delay=%s for [%s %s]", delay, method, url)
            time.sleep(delay)
        try:
            with requests.Session() as request_session:
                if urlparse(url).scheme in ["", "file"]:
                    url = "file://{}".format(os.path.abspath(url)) if not url.startswith("file://") else url
                    request_session.mount("file://", FileAdapter())
                resp = request_session.request(method, url, **request_kwargs)
            if allowed_codes and len(allowed_codes):
                if resp.status_code in allowed_codes:
                    return resp
            elif resp.status_code < (500 if only_server_errors else 400):
                return resp
            failures.append("{} ({})".format(getattr(resp, "reason", type(resp).__name__),
                                             getattr(resp, "status_code", getattr(resp, "code", 500))))
        # function called without retries raises original error
        # as if calling requests module directly
        except requests.ConnectionError as exc:
            if no_retries:
                raise
            failures.append(type(exc).__name__)
    # also pass-through here if no retries
    if no_retries and resp:
        return resp
    detail = "Request ran out of retries. Attempts generated following errors: {}".format(failures)
    err = HTTPGatewayTimeout(detail=detail)
    # make 'raise_for_status' method available for convenience
    setattr(err, "url", url)
    setattr(err, "reason", err.explanation)
    setattr(err, "raise_for_status", lambda: Response.raise_for_status(err))  # noqa
    return err


def fetch_file(file_reference, file_outdir, settings=None, **request_kwargs):
    # type: (AnyStr, AnyStr, Optional[AnySettingsContainer], **Any) -> AnyStr
    """
    Fetches a file from a local path or remote URL and dumps it's content to the specified output directory.

    The output directory is expected to exist prior to this function call.

    :param file_reference: Local filesystem path or remote URL file reference.
    :param file_outdir: Output directory path of the fetched file.
    :param settings: Additional request setting details from the application configuration.
    :param request_kwargs: Additional keywords to forward to request call (if needed).
    :return: Path of the local copy of the fetched file.
    """
    file_href = file_reference
    file_path = os.path.join(file_outdir, os.path.basename(file_reference))
    if file_reference.startswith("file://"):
        file_reference = file_reference[7:]
    LOGGER.debug("Fetch file resolved:\n"
                 "  Reference: [%s]\n"
                 "  File Path: [%s]", file_href, file_path)
    if os.path.isfile(file_reference):
        # NOTE:
        #   If file is available locally and referenced as a system link, disabling follow symlink
        #   creates a copy of the symlink instead of an extra hard-copy of the linked file.
        #   PyWPS will tend to generate symlink to pre-fetched files to avoid this kind of extra hard-copy.
        #   Do symlink operation by hand instead of with argument to have Python-2 compatibility.
        if os.path.islink(file_reference):
            os.symlink(os.readlink(file_reference), file_path)
        else:
            shutil.copyfile(file_reference, file_path)
    else:
        request_kwargs.pop("stream", None)
        with open(file_path, "wb") as file:
            resp = request_extra("get", file_reference, stream=True, retries=3, settings=settings, **request_kwargs)
            if resp.status_code >= 400:
                raise resp
            # NOTE:
            #   Setting 'chunk_size=None' lets the request find a suitable size according to
            #   available memory. Without this, it defaults to 1 which is extremely slow.
            for chunk in resp.iter_content(chunk_size=None):
                file.write(chunk)
    LOGGER.debug("Fetch file written")
    return file_path


REGEX_SEARCH_INVALID_CHARACTERS = re.compile(r"[^a-zA-Z0-9_\-]")
REGEX_ASSERT_INVALID_CHARACTERS = re.compile(r"^[a-zA-Z0-9_\-]+$")


def get_sane_name(name, min_len=3, max_len=None, assert_invalid=True, replace_character="_"):
    # type: (AnyStr, Optional[int], Optional[Union[int, None]], Optional[bool], Optional[AnyStr]) -> Union[AnyStr, None]
    """
    Returns a cleaned-up version of the input name, replacing invalid characters matched with
    ``REGEX_SEARCH_INVALID_CHARACTERS`` by ``replace_character``.

    :param name: value to clean
    :param min_len:
        Minimal length of ``name`` to be respected, raises or returns ``None`` on fail according to ``assert_invalid``.
    :param max_len:
        Maximum length of ``name`` to be respected, raises or returns trimmed ``name`` on fail according to
        ``assert_invalid``. If ``None``, condition is ignored for assertion or full ``name`` is returned respectively.
    :param assert_invalid: If ``True``, fail conditions or invalid characters will raise an error instead of replacing.
    :param replace_character: Single character to use for replacement of invalid ones if ``assert_invalid=False``.
    """
    if not isinstance(replace_character, six.string_types) and not len(replace_character) == 1:
        raise ValueError("Single replace character is expected, got invalid [{!s}]".format(replace_character))
    max_len = max_len or len(name)
    if assert_invalid:
        assert_sane_name(name, min_len, max_len)
    if name is None:
        return None
    name = name.strip()
    if len(name) < min_len:
        return None
    name = re.sub(REGEX_SEARCH_INVALID_CHARACTERS, replace_character, name[:max_len])
    return name


def assert_sane_name(name, min_len=3, max_len=None):
    """Asserts that the sane name respects conditions.

    .. seealso::
        - argument details in :func:`get_sane_name`
    """
    if name is None:
        raise InvalidIdentifierValue("Invalid name : {0}".format(name))
    name = name.strip()
    if "--" in name \
       or name.startswith("-") \
       or name.endswith("-") \
       or len(name) < min_len \
       or (max_len is not None and len(name) > max_len) \
       or not re.match(REGEX_ASSERT_INVALID_CHARACTERS, name):
        raise InvalidIdentifierValue("Invalid name : {0}".format(name))


def clean_json_text_body(body):
    # type: (AnyStr) -> AnyStr
    """
    Cleans a textual body field of superfluous characters to provide a better human-readable text in a JSON response.
    """
    # cleanup various escape characters and u'' stings
    replaces = [(",\n", ", "), ("\\n", " "), (" \n", " "), ("\"", "\'"), ("\\", ""),
                ("u\'", "\'"), ("u\"", "\'"), ("\'\'", "\'"), ("  ", " ")]
    replaces_from = [r[0] for r in replaces]
    while any(rf in body for rf in replaces_from):
        for _from, _to in replaces:
            body = body.replace(_from, _to)

    body_parts = [p.strip() for p in body.split("\n") if p != ""]               # remove new line and extra spaces
    body_parts = [p + "." if not p.endswith(".") else p for p in body_parts]    # add terminating dot per sentence
    body_parts = [p[0].upper() + p[1:] for p in body_parts if len(p)]           # capitalize first word
    body_parts = " ".join(p for p in body_parts if p)
    return body_parts
