import errno
import functools
import inspect
import json
import logging
import os
import re
import shutil
import sys
import time
import warnings
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse, urlunsplit

import boto3
import colander
import pytz
import requests
from beaker.cache import cache_region, region_invalidate
from beaker.exceptions import BeakerException
from celery.app import Celery
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPError as PyramidHTTPError, HTTPGatewayTimeout, HTTPTooManyRequests
from pyramid.registry import Registry
from pyramid.request import Request as PyramidRequest
from pyramid.settings import asbool, aslist
from pyramid.threadlocal import get_current_registry
from pyramid_beaker import set_cache_regions_from_settings
from requests import HTTPError as RequestsHTTPError, Response
from requests.structures import CaseInsensitiveDict
from requests_file import FileAdapter
from urlmatch import urlmatch
from webob.headers import EnvironHeaders, ResponseHeaders
from werkzeug.wrappers import Request as WerkzeugRequest

from weaver.status import map_status
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.xml_util import XML

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Iterable, NoReturn, Optional, Type, Tuple, Union

    from weaver.typedefs import (
        AnyKey,
        AnyHeadersContainer,
        AnySettingsContainer,
        AnyRegistryContainer,
        AnyResponseType,
        AnyValue,
        HeadersType,
        JSON,
        KVP_Item,
        Number,
        SettingsType
    )

LOGGER = logging.getLogger(__name__)

SUPPORTED_FILE_SCHEMES = frozenset([
    "file",
    "http",
    "https",
    "s3"
])


class _Singleton(type):
    __instance__ = None  # type: Optional[_Singleton]

    def __call__(cls):
        if cls.__instance__ is None:
            cls.__instance__ = super(_Singleton, cls).__call__()
        return cls.__instance__


class NullType(metaclass=_Singleton):
    """
    Represents a ``null`` value to differentiate from ``None``.
    """

    # pylint: disable=E1101,no-member
    def __eq__(self, other):
        """
        Makes any instance of :class:`NullType` compare as the same (ie: Singleton).
        """
        return (isinstance(other, NullType)                                     # noqa: W503
                or other is null                                                # noqa: W503
                or other is self.__instance__                                   # noqa: W503
                or (inspect.isclass(other) and issubclass(other, NullType)))    # noqa: W503

    def __getattr__(self, item):
        # type: (Any) -> NullType
        """
        Makes any property getter return ``null`` to make any sub-item also look like ``null``.

        Useful for example in the case of type comparators that do not validate their
        own type before accessing a property that they expect to be there. Without this
        the get operation on ``null`` would raise an unknown key or attribute error.
        """
        return null

    def __repr__(self):
        return "<null>"

    @staticmethod
    def __nonzero__():
        return False

    __bool__ = __nonzero__
    __len__ = __nonzero__


# pylint: disable=C0103,invalid-name
null = NullType()


def get_weaver_url(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the home URL of the `Weaver` application.
    """
    value = get_settings(container).get("weaver.url", "") or ""  # handle explicit None
    return value.rstrip("/").strip()


def get_any_id(info):
    # type: (JSON) -> Union[str, None]
    """
    Retrieves a dictionary `id-like` key using multiple common variations ``[id, identifier, _id]``.

    :param info: dictionary that potentially contains an `id-like` key.
    :returns: value of the matched `id-like` key or ``None`` if not found.
    """
    return info.get("id", info.get("identifier", info.get("_id")))


def get_any_value(info):
    # type: (JSON) -> AnyValue
    """
    Retrieves a dictionary `value-like` key using multiple common variations ``[href, value, reference]``.

    :param info: dictionary that potentially contains a `value-like` key.
    :returns: value of the matched `value-like` key or ``None`` if not found.
    """
    return info.get("href", info.get("value", info.get("reference", info.get("data"))))


def get_any_message(info):
    # type: (JSON) -> str
    """
    Retrieves a dictionary 'value'-like key using multiple common variations [message].

    :param info: dictionary that potentially contains a 'message'-like key.
    :returns: value of the matched 'message'-like key or an empty string if not found.
    """
    return info.get("message", "").strip()


def get_registry(container, nothrow=False):
    # type: (Optional[AnyRegistryContainer], bool) -> Optional[Registry]
    """
    Retrieves the application ``registry`` from various containers referencing to it.
    """
    if isinstance(container, Celery):
        return container.conf.get("PYRAMID_REGISTRY", {})
    if isinstance(container, (Configurator, PyramidRequest)):
        return container.registry
    if isinstance(container, Registry):
        return container
    if isinstance(container, WerkzeugRequest) or container is None:
        return get_current_registry()
    if nothrow:
        return None
    raise TypeError("Could not retrieve registry from container object of type [{}].".format(type(container)))


def get_settings(container=None):
    # type: (Optional[AnySettingsContainer]) -> SettingsType
    """
    Retrieves the application ``settings`` from various containers referencing to it.
    """
    if isinstance(container, (Celery, Configurator, PyramidRequest, WerkzeugRequest)) or container is None:
        container = get_registry(container)
    if isinstance(container, Registry):
        return container.settings
    if isinstance(container, dict):
        return container
    raise TypeError("Could not retrieve settings from container object of type [{}]".format(type(container)))


def get_header(header_name, header_container):
    # type: (str, AnyHeadersContainer) -> Union[str, None]
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
    # type: (AnyHeadersContainer, Optional[str]) -> HeadersType
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
    # type: (Union[str, ParseResult]) -> str
    """
    Removes the query string part of an URL.
    """
    if isinstance(url, str):
        url = urlparse(url)
    if not isinstance(url, ParseResult):
        raise TypeError("Expected a parsed URL.")
    return urlunsplit(url[:4] + tuple([""]))


def is_valid_url(url):
    # type: (Optional[str]) -> bool
    try:
        return bool(urlparse(url).scheme)
    except Exception:  # noqa: W0703 # nosec: B110
        return False


UUID_PATTERN = re.compile(colander.UUID_REGEX, re.IGNORECASE)


def is_uuid(maybe_uuid):
    # type: (Any) -> bool
    """
    Evaluates if the provided input is a UUID-like string.
    """
    if not isinstance(maybe_uuid, str):
        return False
    return re.match(UUID_PATTERN, str(maybe_uuid)) is not None


def parse_extra_options(option_str):
    # type: (str) -> Dict[str, str]
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
            extra_options = dict([("=" in opt) and opt.split("=", 1) for opt in extra_options])  # noqa
        except Exception:
            msg = "Can not parse extra-options: {}".format(option_str)
            from pyramid.exceptions import ConfigurationError
            raise ConfigurationError(msg)
    else:
        extra_options = {}
    return extra_options


def fully_qualified_name(obj):
    # type: (Union[Any, Type[Any]]) -> str
    """
    Obtains the ``'<module>.<name>'`` full path definition of the object to allow finding and importing it.
    """
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


def repr_json(data, force_str=True, **kwargs):
    # type: (Any, bool, Any) -> Union[JSON, str, None]
    """
    Ensure that the input data can be serialized as JSON to return it formatted representation as such.

    If formatting as JSON fails, returns the data as string representation or ``None`` accordingly.
    """
    if data is None:
        return None
    try:
        data_str = json.dumps(data, **kwargs)
        return data_str if force_str else data
    except Exception:  # noqa: W0703 # nosec: B110
        return str(data)


def wait_secs(run_step=-1):
    secs_list = (2, 2, 2, 2, 2, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 20, 20, 20, 20, 20, 30)
    if run_step >= len(secs_list):
        run_step = -1
    return secs_list[run_step]


def expires_at(hours=1):
    # type: (Optional[int]) -> int
    return now_secs() + hours * 3600


def localize_datetime(dt, tz_name="UTC"):
    # type: (datetime, Optional[str]) -> datetime
    """
    Provide a timezone-aware object for a given datetime and timezone name.
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
    # type: (str) -> str
    """
    Obtains the base URL from the given ``url``.
    """
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        raise ValueError("bad url")
    service_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path.strip())
    return service_url


def xml_path_elements(path):
    # type: (str) -> List[str]
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
    # type: (str, Optional[bool]) -> JSON
    """
    Retrieves the complete or partial dictionary defining an ``OWSContext`` from a reference.
    """
    context = {"offering": {"content": {"href": href}}}
    if partial:
        return context
    return {"owsContext": context}


def pass_http_error(exception, expected_http_error):
    # type: (Exception, Union[Type[PyramidHTTPError], Iterable[Type[PyramidHTTPError]]]) -> None
    """
    Silently ignore a raised HTTP error that matches the specified error code of the reference exception class.

    Given an `HTTPError` of any type (:mod:`pyramid`, :mod:`requests`), ignores the exception if the actual
    error matches the status code. Other exceptions are re-raised.
    This is equivalent to capturing a specific ``Exception`` within an ``except`` block and calling ``pass`` to drop it.

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
    # type: (XML) -> Optional[NoReturn]
    """
    Raises an exception with the description if the XML response document defines an ExceptionReport.

    :param xml_node: instance of :class:`XML`
    :raise Exception: on found ExceptionReport document.
    """
    if not isinstance(xml_node, XML):
        raise TypeError("Invalid input, expecting XML element node.")
    if "ExceptionReport" in xml_node.tag:
        node = xml_node
        while len(node.getchildren()):
            node = node.getchildren()[0]
        raise Exception(node.text)


def str2bytes(string):
    # type: (Union[str, bytes]) -> bytes
    """
    Obtains the bytes representation of the string.
    """
    if not isinstance(string, (str, bytes)):
        raise TypeError("Cannot convert item to bytes: {!r}".format(type(string)))
    if isinstance(string, bytes):
        return string
    return string.encode()


def bytes2str(string):
    # type: (Union[str, bytes]) -> str
    """
    Obtains the unicode representation of the string.
    """
    if not isinstance(string, (str, bytes)):
        raise TypeError("Cannot convert item to unicode: {!r}".format(type(string)))
    if not isinstance(string, bytes):
        return string
    return string.decode()


def islambda(func):
    # type: (Any) -> bool
    return isinstance(func, type(lambda: None)) and func.__name__ == (lambda: None).__name__


first_cap_re = re.compile(r"(.)([A-Z][a-z]+)")
all_cap_re = re.compile(r"([a-z0-9])([A-Z])")


def get_path_kvp(path, sep=",", **params):
    # type: (str, str, **KVP_Item) -> str
    """
    Generates the URL with Key-Value-Pairs (KVP) query parameters.

    :param path: WPS URL or Path
    :param sep: separator to employ when multiple values are provided.
    :param params: keyword parameters and their corresponding single or multi values to generate KVP.
    :return: combined path and query parameters as KVP.
    """

    def _value(_v):
        if isinstance(_v, (list, set, tuple)):
            return sep.join([str(_) for _ in _v])
        return str(_v)

    kvp = ["{}={}".format(k, _value(v)) for k, v in params.items()]
    return path + "?" + "&".join(kvp)


def get_log_fmt():
    # type: (...) -> str
    """
    Logging format employed for job output reporting.
    """
    return "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"


def get_log_date_fmt():
    # type: (...) -> str
    """
    Logging date format employed for job output reporting.
    """
    return "%Y-%m-%d %H:%M:%S"


def get_log_monitor_msg(job_id, status, percent, message, location):
    # type: (str, str, Number, str, str) -> str
    return "Monitoring job {jobID} : [{status}] {percent} - {message} [{location}]".format(
        jobID=job_id, status=status, percent=percent, message=message, location=location
    )


def get_job_log_msg(status, message, progress=0, duration=None):
    # type: (str, str, Optional[Number], Optional[str]) -> str
    return "{d} {p:3d}% {s:10} {m}".format(d=duration or "", p=int(progress or 0), s=map_status(status), m=message)


def setup_loggers(settings, level=None):
    # type: (AnySettingsContainer, Optional[Union[int, str]]) -> None
    """
    Update logging configuration known loggers based on application settings.

    When ``weaver.log_level`` exists in settings, it **overrides** any other INI configuration logging levels.
    Otherwise, undefined logger levels will be set according to whichever is found first between ``weaver.log_level``,
    the :paramref:`level` parameter or default :py:data:`logging.INFO`.
    """
    log_level = settings.get("weaver.log_level")
    override = False
    if log_level:
        override = True
    else:
        log_level = level or logging.INFO
    if not isinstance(log_level, int):
        log_level = logging.getLevelName(log_level.upper())
    for logger_name in ["weaver", "cwltool"]:
        logger = logging.getLogger(logger_name)
        if override or logger.level == logging.NOTSET:
            logger.setLevel(log_level)
        # define basic formatter/handler if config INI did not provide it
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(get_log_fmt())
            handler.setFormatter(formatter)
            logger.addHandler(handler)


def make_dirs(path, mode=0o755, exist_ok=False):
    """
    Backward compatible ``make_dirs`` with reduced set of default mode flags.

    Alternative to ``os.makedirs`` with ``exists_ok`` parameter only available for ``python>3.5``.
    Also, using a reduced set of permissions ``755`` instead of original default ``777``.

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
    """
    Find the name of a parent caller function or method.

    The name is returned with respective formats ``module.class.method`` or ``module.function``.

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


def setup_cache(settings):
    # type: (SettingsType) -> None
    """
    Prepares the settings with default caching options.
    """
    # handle other naming variant supported by 'pyramid_beaker',
    # unify only with 'cache.' prefix but ignore if duplicate
    for key in list(settings):
        if key.startswith("beaker.cache."):
            cache_key = key.replace("beaker.cache.", "cache.")
            cache_val = settings.get(key)
            settings.setdefault(cache_key, cache_val)
    # apply defaults to avoid missing items during runtime
    settings.setdefault("cache.regions", "doc, request, result")
    settings.setdefault("cache.type", "memory")
    settings.setdefault("cache.doc.enable", "false")
    settings.setdefault("cache.doc.expired", "3600")
    settings.setdefault("cache.request.enabled", "false")
    settings.setdefault("cache.request.expire", "60")
    settings.setdefault("cache.result.enabled", "false")
    settings.setdefault("cache.result.expire", "3600")
    set_cache_regions_from_settings(settings)


def invalidate_region(caching_args):
    # type: (Tuple[Callable, str, Tuple[Any]]) -> None
    """
    Caching region invalidation with handling to ignore errors generated by of unknown regions.

    :param caching_args: tuple of ``(function, region, *function-args)`` representing caching key to invalidate.
    """
    func, region, *args = caching_args
    try:
        region_invalidate(func, region, *args)
    except BeakerException:
        pass


def get_ssl_verify_option(method, url, settings, request_options=None):
    # type: (str, str, AnySettingsContainer, Optional[SettingsType]) -> bool
    """
    Obtains the SSL verification option considering multiple setting definitions and the provided request context.

    Obtains the SSL verification option from combined settings from ``weaver.ssl_verify``
    and parsed ``weaver.request_options`` file for the corresponding request.

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


def get_no_cache_option(request_headers, request_options):
    # type: (HeadersType, SettingsType) -> bool
    """
    Obtains the No-Cache result from request headers and configured request options.

    .. seealso::
        - :meth:`Request.headers`
        - :func:`get_request_options`

    :param request_headers: specific request headers that could indicate ``Cache-Control: no-cache``
    :param request_options: specific request options that could define ``cache: True|False``
    :return: whether to disable cache or not
    """
    no_cache_header = str(get_header("Cache-Control", request_headers)).lower().replace(" ", "")
    no_cache = no_cache_header in ["no-cache", "max-age=0", "max-age=0,must-revalidate"]
    no_cache = no_cache is True or request_options.get("cache", True) is False
    return no_cache


def get_request_options(method, url, settings):
    # type: (str, str, AnySettingsContainer) -> SettingsType
    """
    Obtains the *request options* corresponding to the request from the configuration file.

    The configuration file specified is expected to be pre-loaded within setting ``weaver.request_options``.
    If no file was pre-loaded or no match is found for the request, an empty options dictionary is returned.

    .. seealso::
        - :func:`get_ssl_verify_option`
        - `config/request_options.yml.example <../../../config/request_options.yml.example>`_

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


def retry_on_cache_error(func):
    # type: (Callable[[...], Any]) -> Callable
    """
    Decorator to handle invalid cache setup.

    Any function wrapped with this decorator will retry execution once if missing cache setup was the cause of error.
    """
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BeakerException as exc:
            if "Cache region not configured" in str(exc):
                LOGGER.debug("Invalid cache region setup detected, retrying operation after setup...")
                setup_cache(get_settings() or {})
            else:
                raise  # if not the expected cache exception, ignore retry attempt
        try:
            return func(*args, **kwargs)
        except BeakerException as exc:
            LOGGER.error("Invalid cache region setup could not be resolved: [%s]", exc)
            raise
    return wrapped


def _request_call(method, url, kwargs):
    # type: (str, str, Dict[str, AnyValue]) -> Response
    """
    Request operation employed by :func:`request_extra` without caching.
    """
    with requests.Session() as request_session:
        if urlparse(url).scheme in ["", "file"]:
            url = "file://{}".format(os.path.abspath(url)) if not url.startswith("file://") else url
            request_session.mount("file://", FileAdapter())
        resp = request_session.request(method, url, **kwargs)
    return resp


@cache_region("request")
def _request_cached(method, url, kwargs):
    # type: (str, str, Dict[str, AnyValue]) -> Response
    """
    Cached-enabled request operation employed by :func:`request_extra`.
    """
    return _request_call(method, url, kwargs)


@retry_on_cache_error
def request_extra(method,                       # type: str
                  url,                          # type: str
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
    ~~~~~~~~~~~~~~~~~~~~~~

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
    ~~~~~~~~~~~~~~~~~~~~~~

    Any request with ``file://`` scheme or empty scheme (no scheme specified) will be automatically handled as potential
    local file path. The path should be absolute to ensure it to be correctly resolved.

    All access errors due to file permissions return 403 status code, and missing file returns 404.
    Any other :py:exc:`IOError` types are converted to a 400 responses.

    .. seealso::
        - :class:`FileAdapter`

    SSL Verification
    ~~~~~~~~~~~~~~~~~~~~~~

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
    :param retry_after: If enabled, honor ``Retry-After`` response header of provided by a failing request attempt.
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
    settings = get_settings(settings) or {}
    request_options = get_request_options(method, url, settings)
    request_options.update(request_kwargs)
    # catch kw passed to request corresponding to retries parameters
    # it is safe top pop items because 'get_request_options' creates a copy each time
    kw_retries = request_options.pop("retries", request_options.pop("retry", request_options.pop("max_retries", None)))
    kw_backoff = request_options.pop("backoff", request_options.pop("backoff_factor", None))
    kw_intervals = request_options.pop("intervals", None)
    retries = retries if retries is not None else kw_retries if kw_retries is not None else 0
    backoff = backoff if backoff is not None else kw_backoff if kw_backoff is not None else 0.3
    intervals = intervals or kw_intervals
    if intervals and len(intervals) and all(isinstance(i, (int, float)) for i in intervals):
        request_delta = [0] + intervals
    else:
        request_delta = [0] + [(backoff * (2 ** (retry + 1))) for retry in range(retries)]
    no_retries = len(request_delta) == 1
    # SSL verification settings
    # ON by default, disable accordingly with any variant if matched
    kw_ssl_verify = get_ssl_verify_option(method, url, settings, request_options=request_options)
    ssl_verify = False if not kw_ssl_verify or not ssl_verify else True  # pylint: disable=R1719
    request_kwargs.setdefault("timeout", 5)
    request_kwargs.setdefault("verify", ssl_verify)
    # process request
    resp = None
    failures = []
    no_cache = get_no_cache_option(request_kwargs.get("headers", {}), request_options)
    region = "request"
    request_args = (method, url, request_kwargs)
    caching_args = (_request_cached, region, *request_args)
    for retry, delay in enumerate(request_delta):
        if retry:
            code = resp.status_code if resp else None
            if retry_after and resp and code in [HTTPTooManyRequests.code]:
                after = resp.headers.get("Retry-After", "")
                delay = int(after) if str(after).isdigit() else 0
                LOGGER.debug("Received header [Retry-After=%ss] (code=%s) for [%s %s]", after, code, method, url)
            LOGGER.debug("Retrying failed request after delay=%ss (code=%s) for [%s %s]", delay, code, method, url)
            time.sleep(delay)
        try:
            if no_cache:
                resp = _request_call(*request_args)
            else:
                resp = _request_cached(*request_args)
            if allowed_codes and len(allowed_codes):
                if resp.status_code in allowed_codes:
                    return resp
            elif resp.status_code < (500 if only_server_errors else 400):
                invalidate_region(caching_args)
                return resp
            invalidate_region(caching_args)
            failures.append("{} ({})".format(getattr(resp, "reason", type(resp).__name__),
                                             getattr(resp, "status_code", getattr(resp, "code", 500))))
        # function called without retries raises original error as if calling requests module directly
        except (requests.ConnectionError, requests.Timeout) as exc:
            if no_retries:
                raise
            invalidate_region(caching_args)
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
    # type: (str, str, Optional[AnySettingsContainer], **Any) -> str
    """
    Fetches a file from local path, AWS-S3 bucket or remote URL, and dumps it's content to the output directory.

    The output directory is expected to exist prior to this function call.
    The file reference scheme (protocol) determines from where to fetch the content.
    Output file name and extension will be the same as the original.
    Requests will consider ``weaver.request_options`` when using ``http(s)://`` scheme.

    :param file_reference:
        Local filesystem path (optionally prefixed with ``file://``), ``s3://`` bucket location or ``http(s)://``
        remote URL file reference. Reference ``https://s3.[...]`` are also considered as ``s3://``.
    :param file_outdir: Output local directory path under which to place the fetched file.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param request_kwargs: Additional keywords to forward to request call (if needed).
    :return: Path of the local copy of the fetched file.
    :raises HTTPException: applicable HTTP-based exception if any occurred during the operation.
    :raises ValueError: when the reference scheme cannot be identified.
    """
    file_href = file_reference
    file_name = os.path.basename(file_reference)
    file_path = os.path.join(file_outdir, file_name)
    if file_reference.startswith("file://"):
        file_reference = file_reference[7:]
    LOGGER.debug("Fetching file reference: [%s]", file_href)
    if os.path.isfile(file_reference):
        LOGGER.debug("Fetch file resolved as local reference.")
        # NOTE:
        #   If file is available locally and referenced as a system link, disabling follow symlink
        #   creates a copy of the symlink instead of an extra hard-copy of the linked file.
        #   PyWPS will tend to generate symlink to pre-fetched files to avoid this kind of extra hard-copy.
        #   Do symlink operation by hand instead of with argument to have Python-2 compatibility.
        if os.path.islink(file_reference):
            os.symlink(os.readlink(file_reference), file_path)
        # otherwise copy the file if not already available
        elif not os.path.isfile(file_path) or os.path.realpath(file_path) != os.path.realpath(file_reference):
            shutil.copyfile(file_reference, file_path)
    elif file_reference.startswith("s3://"):
        LOGGER.debug("Fetch file resolved as S3 bucket reference.")
        s3 = boto3.resource("s3")
        bucket_name, file_key = file_reference[5:].split("/", 1)
        bucket = s3.Bucket(bucket_name)
        bucket.download_file(file_key, file_path)
    elif file_reference.startswith("http"):
        if file_reference.startswith("https://s3."):
            s3 = boto3.resource("s3")
            # endpoint in the form: "https://s3.[region-name.]amazonaws.com/<bucket>/<file-key>"
            if not file_reference.startswith(s3.meta.endpoint_url):
                LOGGER.warning("Detected HTTP file reference to AWS S3 bucket that mismatches server configuration. "
                               "Will consider it as plain HTTP with read access.")
            else:
                file_ref_updated = "s3://{}".format(file_reference.replace(s3.meta.endpoint_url, ""))
                LOGGER.debug("Adjusting file reference to S3 shorthand for further parsing:\n"
                             "  Initial: [%s]\n"
                             "  Updated: [%s]", file_reference, file_ref_updated)
                return fetch_file(file_ref_updated, file_outdir, settings=settings, **request_kwargs)

        LOGGER.debug("Fetch file resolved as remote URL reference.")
        request_kwargs.pop("stream", None)
        with open(file_path, "wb") as file:
            resp = request_extra("get", file_reference, stream=True, retries=3, settings=settings, **request_kwargs)
            if resp.status_code >= 400:
                # use method since response object does not derive from Exception, therefore cannot be raised directly
                if hasattr(resp, "raise_for_status"):
                    resp.raise_for_status()
                raise resp
            # NOTE:
            #   Setting 'chunk_size=None' lets the request find a suitable size according to
            #   available memory. Without this, it defaults to 1 which is extremely slow.
            for chunk in resp.iter_content(chunk_size=None):
                file.write(chunk)
    else:
        scheme = file_reference.split("://")
        scheme = "<none>" if len(scheme) < 2 else scheme[0]
        raise ValueError("Unresolved fetch file scheme: '{!s}', supported: {}"
                         .format(scheme, list(SUPPORTED_FILE_SCHEMES)))
    LOGGER.debug("Fetch file resolved:\n"
                 "  Reference: [%s]\n"
                 "  File Path: [%s]", file_href, file_path)
    return file_path


REGEX_SEARCH_INVALID_CHARACTERS = re.compile(r"[^a-zA-Z0-9_\-]")
REGEX_ASSERT_INVALID_CHARACTERS = re.compile(r"^[a-zA-Z0-9_\-]+$")


def get_sane_name(name, min_len=3, max_len=None, assert_invalid=True, replace_character="_"):
    # type: (str, Optional[int], Optional[Union[int, None]], Optional[bool], str) -> Union[str, None]
    """
    Cleans up the name to allow only specified characters and conditions.

    Returns a cleaned-up version of the :paramref:`name`, replacing invalid characters not
    matched with :py:data:`REGEX_SEARCH_INVALID_CHARACTERS` by :paramref:`replace_character`.
    Also, ensure that the resulting name respects specified length conditions.

    .. seealso::
        :class:`weaver.wps_restapi.swagger_definitions.SLUG`

    :param name:
        Value to clean.
    :param min_len:
        Minimal length of :paramref:`name`` to be respected, raises or returns ``None`` on fail according
        to :paramref:`assert_invalid`.
    :param max_len:
        Maximum length of :paramref:`name` to be respected, raises or returns trimmed :paramref:`name` on fail
        according to :paramref:`assert_invalid`. If ``None``, condition is ignored for assertion or full
        :paramref:`name` is returned respectively.
    :param assert_invalid:
        If ``True``, fail conditions or invalid characters will raise an error instead of replacing.
    :param replace_character:
        Single character to use for replacement of invalid ones if :paramref:`assert_invalid` is ``False``.
    """
    if not isinstance(replace_character, str) or not len(replace_character) == 1:
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
    """
    Asserts that the sane name respects conditions.

    .. seealso::
        - argument details in :func:`get_sane_name`
    """
    from weaver.exceptions import InvalidIdentifierValue, MissingIdentifierValue

    if name is None or len(name) == 0:
        raise MissingIdentifierValue("Invalid name : {0}".format(name))
    name = name.strip()
    if "--" in name \
       or name.startswith("-") \
       or name.endswith("-") \
       or len(name) < min_len \
       or (max_len is not None and len(name) > max_len) \
       or not re.match(REGEX_ASSERT_INVALID_CHARACTERS, name):
        raise InvalidIdentifierValue("Invalid name : {0}".format(name))


def clean_json_text_body(body, remove_newlines=True, remove_indents=True):
    # type: (str, bool, bool) -> str
    """
    Cleans a textual body field of superfluous characters to provide a better human-readable text in a JSON response.
    """
    # cleanup various escape characters and u'' stings
    replaces = [(",\n", ", "), ("\\n", " "), (" \n", " "), ("\n'", "'"), ("\"", "\'"),
                ("u\'", "\'"), ("u\"", "\'"), ("\'\'", "\'"), ("'. ", ""), ("'. '", ""),
                ("}'", "}"), ("'{", "{")]
    if remove_indents:
        replaces.extend([("\\", " "), ("  ", " ")])
    else:
        replaces.extend([("\\", ""), ])
    if not remove_newlines:
        replaces.extend([("'\n  ", "'\n "), ("'\n '", "'\n'"), ("'\n'", "\n'")])

    replaces_from = [r[0] for r in replaces]
    while any(rf in body for rf in replaces_from):
        for _from, _to in replaces:
            body = body.replace(_from, _to)

    if remove_newlines:
        body_parts = [p.strip() for p in body.split("\n") if p != ""]               # remove new line and extra spaces
        body_parts = [p + "." if not p.endswith(".") else p for p in body_parts]    # add terminating dot per sentence
        body_parts = [p[0].upper() + p[1:] for p in body_parts if len(p)]           # capitalize first word
        body_clean = " ".join(p for p in body_parts if p)
    else:
        body_clean = body

    # re-process without newlines to remove escapes created by concat of lines
    if any(rf in body_clean for rf in replaces_from):
        body_clean = clean_json_text_body(body_clean, remove_newlines=remove_newlines, remove_indents=remove_indents)
    return body_clean


def transform_json(json_data,               # type: Dict[str, JSON]
                   rename=None,             # type: Optional[Dict[AnyKey, Any]]
                   remove=None,             # type: Optional[List[AnyKey]]
                   add=None,                # type: Optional[Dict[AnyKey, Any]]
                   replace_values=None,     # type: Optional[Dict[AnyKey, Any]]
                   replace_func=None,       # type: Optional[Dict[AnyKey, Callable[[Any], Any]]]
                   ):                       # type: (...) -> Dict[str, JSON]
    """
    Transforms the input JSON with different methods.

    The transformations are applied in-place and in the same order as the arguments (rename, remove, add, etc.).
    All operations are applied onto the top-level fields of the mapping.
    No nested operations are applied, unless handled by replace functions.

    .. note::
        Because fields and values are iterated over the provided mappings, replacements of previous iterations
        could be re-replaced by following ones if the renamed item corresponds to a following item to match.
        For example, renaming ``field1 -> field2`` and ``field2 -> field3` within the same operation type would
        result in successive replacements with ``field3`` as result. The parameter order is important in this case
        as swapping the definitions would not find ``field2`` on the first iteration (not in mapping *yet*), and
        then find ``field1``, making the result to be ``field2``.

    :param json_data: JSON mapping structure to transform.
    :param rename: rename matched fields key name to the associated value name.
    :param remove: remove matched fields by name.
    :param add: add or override the fields names with associated values.
    :param replace_values: replace matched values by the associated new values regardless of field names.
    :param replace_func:
        Replace values under matched fields by name with the returned value from the associated function.
        Mapping functions will receive the original value as input.
        If the result is to be serialized to JSON, they should return a valid JSON-serializable value.
    :returns: transformed JSON (same as modified in-place input JSON).
    """
    rename = rename or {}
    remove = remove or []
    add = add or {}
    replace_values = replace_values or {}
    replace_func = replace_func or {}

    # rename
    for k, v in rename.items():
        if k in json_data:
            json_data[v] = json_data.pop(k)

    # remove
    for r_k in remove:
        json_data.pop(r_k, None)

    # add
    for k, v in add.items():
        json_data[k] = v

    # replace values
    for key, value in json_data.items():
        for old_value, new_value in replace_values.items():
            if value == old_value:
                json_data[key] = new_value

    # replace with function call
    for k, func in replace_func.items():
        if k in json_data:
            json_data[k] = func(json_data[k])

    # also rename if the type of the value is a list of dicts
    for key, value in json_data.items():
        if isinstance(value, list):
            for nested_item in value:
                if isinstance(nested_item, dict):
                    for k, v in rename.items():
                        if k in nested_item:
                            nested_item[v] = nested_item.pop(k)
                    for k, func in replace_func.items():
                        if k in nested_item:
                            nested_item[k] = func(nested_item[k])
    return json_data
