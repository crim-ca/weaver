import difflib
import errno
import fnmatch
import functools
import importlib.util
import inspect
import io
import logging
import os
import posixpath
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
import warnings
from concurrent.futures import ALL_COMPLETED, CancelledError, ThreadPoolExecutor, as_completed, wait as wait_until
from copy import deepcopy
from datetime import datetime
from pkgutil import get_loader
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterable, Protocol, overload
from urllib.parse import ParseResult, parse_qsl, unquote, urlparse, urlunsplit

import boto3
import colander
import pytz
import requests
import yaml
from beaker.cache import Cache, cache_managers, cache_region, cache_regions, region_invalidate
from beaker.container import MemoryNamespaceManager
from beaker.exceptions import BeakerException
from botocore.config import Config as S3Config
from botocore.exceptions import ClientError, HTTPClientError
from bs4 import BeautifulSoup
from celery.app import Celery
from dateutil.parser import parse as parse_dt
from mypy_boto3_s3.literals import RegionName
from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPError as PyramidHTTPError,
    HTTPGatewayTimeout,
    HTTPTooManyRequests
)
from pyramid.registry import Registry
from pyramid.request import Request as PyramidRequest
from pyramid.response import _guess_type as guess_file_contents  # noqa: W0212
from pyramid.settings import asbool, aslist
from pyramid.threadlocal import get_current_registry
from pyramid_beaker import set_cache_regions_from_settings
from pyramid_celery import celery_app as app
from pywps.inout.basic import UrlHandler
from pywps.inout.outputs import MetaFile, MetaLink, MetaLink4
from requests import HTTPError as RequestsHTTPError, Response
from requests.structures import CaseInsensitiveDict
from requests_file import FileAdapter
from urlmatch import urlmatch
from webob.headers import EnvironHeaders, ResponseHeaders
from werkzeug.utils import secure_filename
from werkzeug.wrappers import Request as WerkzeugRequest
from yaml.scanner import ScannerError

from weaver.base import Constants, ExtendedEnum
from weaver.compat import Version
from weaver.exceptions import WeaverException
from weaver.formats import ContentType, get_content_type, get_extension, get_format, repr_json
from weaver.status import map_status
from weaver.warning import TimeZoneInfoAlreadySetWarning, UndefinedContainerWarning
from weaver.xml_util import HTML_TREE_BUILDER, XML

try:  # refactor in jsonschema==4.18.0
    from jsonschema.validators import _RefResolver as JsonSchemaRefResolver  # pylint: disable=E0611
except ImportError:  # pragma: no cover
    from jsonschema.validators import RefResolver as JsonSchemaRefResolver  # pylint: disable=E0611

if TYPE_CHECKING:
    import importlib.abc
    from types import FrameType, ModuleType
    from typing import (
        AnyStr,
        Callable,
        Dict,
        IO,
        Iterator,
        List,
        MutableMapping,
        NoReturn,
        Optional,
        Tuple,
        Type,
        TypeVar,
        Union
    )
    from typing_extensions import NotRequired, Required, TypeAlias, TypedDict, TypeGuard, Unpack

    from mypy_boto3_s3.client import S3Client

    from weaver.status import Status
    from weaver.typedefs import (
        AnyCallable,
        AnyCallableAnyArgs,
        AnyCookiesContainer,
        AnyHeadersContainer,
        AnyKey,
        AnyRegistryContainer,
        AnyRequestMethod,
        AnyRequestQueryMultiDict,
        AnyRequestType,
        AnyResponseType,
        AnySettingsContainer,
        AnyUUID,
        AnyValueType,
        AnyVersion,
        Default,
        HeadersType,
        JSON,
        KVP,
        Link,
        Literal,
        Number,
        OpenAPISchema,
        Params,
        Path,
        Return,
        SettingsType
    )

    RetryCondition = Union[Type[Exception], Iterable[Type[Exception]], Callable[[Exception], bool]]
    SchemeOptions = TypedDict("SchemeOptions", {
        "file": Dict[str, JSON],
        "http": Dict[str, JSON],   # includes/duplicates HTTPS
        "https": Dict[str, JSON],  # includes/duplicates HTTP
        "s3": Dict[str, JSON],
        "vault": Dict[str, JSON],
    }, total=True)
    RequestOptions = TypedDict("RequestOptions", {
        "timeout": NotRequired[int],
        "connect_timeout": NotRequired[int],
        "read_timeout": NotRequired[int],
        "retry": NotRequired[int],
        "retries": NotRequired[int],
        "max_retries": NotRequired[int],
        "backoff": NotRequired[Number],
        "backoff_factor": NotRequired[Number],
        "headers": NotRequired[AnyHeadersContainer],
        "cookies": NotRequired[AnyCookiesContainer],
        "stream": NotRequired[bool],
        "cache": NotRequired[bool],
        "cache_enabled": NotRequired[bool],
    }, total=False)
    RequestCachingKeywords = Dict[str, AnyValueType]
    RequestCachingFunction = Callable[[AnyRequestMethod, str, RequestCachingKeywords], Response]

    MetadataResult = TypedDict("MetadataResult", {
        "Date": str,
        "Last-Modified": str,
        "Content-ID": NotRequired[str],
        "Content-Type": Required[str],
        "Content-Length": NotRequired[str],
        "Content-Encoding": NotRequired[str],
        "Content-Location": str,
        "Content-Disposition": NotRequired[str],
    }, total=False)
    _OutputMethod = "OutputMethod"  # type: TypeAlias  # pylint: disable=C0103,invalid-name
    AnyMetadataOutputMethod = Literal[
        _OutputMethod.META,
    ]
    DownloadResult = Path
    AnyDownloadOutputMethod = Literal[
        _OutputMethod.AUTO,
        _OutputMethod.COPY,
        _OutputMethod.LINK,
        _OutputMethod.MOVE,
    ]
    AnyOutputMethod = Union[AnyMetadataOutputMethod, AnyDownloadOutputMethod]
    AnyOutputResult = Union[MetadataResult, DownloadResult]

    AnyMetalink = Union[MetaLink, MetaLink4]
    FileLink = TypedDict("FileLink", {
        "href": str,
        "file": NotRequired[Optional[str]],
        "name": NotRequired[Optional[str]],
        "type": NotRequired[Optional[str]],         # mediaType equivalent
        "mediaType": NotRequired[Optional[str]],    # for convenience
        "encoding": NotRequired[Optional[str]],
    }, total=True)

    FilterType = TypeVar("FilterType")  # pylint: disable=C0103,invalid-name

    OriginalClass = TypeVar("OriginalClass")
    ExtenderMixin = TypeVar("ExtenderMixin")

    class ExtendedClass(OriginalClass, ExtenderMixin):
        ...


LOGGER = logging.getLogger(__name__)


class LoggerHandler(Protocol):
    """
    Minimalistic logger interface (typically :class:`logging.Logger`) intended to be used only with ``log`` method.
    """

    def log(self, level, message, *args, **kwargs):
        # type: (int, str, *Any, **Any) -> None
        ...


SUPPORTED_FILE_SCHEMES = frozenset([
    "file",
    "http",
    "https",
    "s3",
    "vault"
])

# note: word characters also match unicode in this case
FILE_NAME_LOOSE_PATTERN = re.compile(
    r"^"
    r"(?P<filename>[\w\-.]+)"
    r"(?<!\.$)$"  # extension optional, but not only a dot if provided
)
FILE_NAME_QUOTE_PATTERN = re.compile(
    r"^(?P<quote>\"?)"  # optional quotes allowed [...]
    rf"({FILE_NAME_LOOSE_PATTERN.pattern[1:-1]})"
    r"(?P=quote)$"      # [...] but must be balanced

)

if sys.version_info >= (3, 7):
    _LITERAL_VALUES_ATTRIBUTE = "__args__"
else:
    _LITERAL_VALUES_ATTRIBUTE = "__values__"  # pragma: no cover
AWS_S3_REGIONS = list(getattr(RegionName, _LITERAL_VALUES_ATTRIBUTE))  # type: List[RegionName]
AWS_S3_REGIONS_REGEX = f"({'|'.join(AWS_S3_REGIONS)})"
# https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html
AWS_S3_ARN = "arn:aws:s3"
# https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
# https://stackoverflow.com/questions/50480924/regex-for-s3-bucket-name
AWS_S3_BUCKET_NAME_PATTERN = re.compile(
    r"^"
    r"(?!(^xn--|.+-s3alias$))"  # prefix/suffix disallowed by reserved AWS use for other bucket access point variations
    # lowercase only allowed, in range (min=3, max=63) characters
    r"[a-z0-9]"  # only alphanumeric start
    r"(?:(\.(?!\.))|[a-z0-9-]){1,61}"  # alphanumeric with dash/dot allowed, but repeated dots disallowed
    r"[a-z0-9]"  # only alphanumeric end
    r"$"
)
# Bucket ARN =
# - arn:aws:s3:{Region}:{AccountId}:accesspoint/{AccessPointName}[/file-key]
# - arn:aws:s3-outposts:{Region}:{AccountId}:outpost/{OutpostId}/bucket/{Bucket}[/file-key]
# - arn:aws:s3-outposts:{Region}:{AccountId}:outpost/{OutpostId}/accesspoint/{AccessPointName}[/file-key]
AWS_S3_BUCKET_ARN_PATTERN = re.compile(
    r"^"
    rf"(?P<arn>{AWS_S3_ARN}(?:-outposts)?):"
    rf"(?P<region>{AWS_S3_REGIONS_REGEX}):"
    r"(?P<account_id>[a-z0-9]+):"
    r"(?P<type_name>accesspoint|outpost)/"
    r"(?P<type_id>[a-z0-9][a-z0-9-]+[a-z0-9])"
    r"$"
)
AWS_S3_BUCKET_REFERENCE_PATTERN = re.compile(
    r"^(?P<scheme>s3://)"
    rf"(?P<bucket>{AWS_S3_BUCKET_NAME_PATTERN.pattern[1:-1]}|{AWS_S3_BUCKET_ARN_PATTERN.pattern[1:-1]})"
    r"(?P<path>(?:/$|/[\w.-]+)+)"  # sub-dir and file-key path, minimally only dir trailing slash
    r"$"
)


class Lazify(str):
    """
    Wraps the callable for evaluation only on explicit call or string formatting.

    Once string representation has been computed, it will be cached to avoid regenerating it on following calls.
    """

    def __init__(self, func):
        # type: (Callable[[], Return]) -> None
        """
        Initialize the lazy-string representation.

        :param func: Callable that should return the computed string formatting.
        """
        if not callable(func):
            raise ValueError("Invalid lazify operation. Input must be a callable.")
        self.func = func
        self._str = None

    def __getattribute__(self, item):
        # type: (str) -> Any
        if item in ["__str__", "__repr__", "__call__"]:
            return str.__getattribute__(self, item)
        if item in ["__class__", "_str", "func"]:
            return object.__getattribute__(self, item)
        _str = self.__call__()
        return str.__getattribute__(_str, item)

    def __call__(self):
        # type: () -> Return
        if self._str is None:
            self._str = self.func()
        return self._str

    def __str__(self):
        # type: () -> str
        return f"{self.__call__()!s}"

    def __repr__(self):
        # type: () -> str
        func_name = fully_qualified_name(self.func)
        str_status = "<lazy>" if self._str is None else "<computed>"
        return f"{self.__class__.__name__}({func_name}) {str_status}"


class CaseInsensitive(str):
    __str = None

    def __init__(self, _str):
        # type: (str) -> None
        self.__str = _str
        super(CaseInsensitive, self).__init__()

    def __hash__(self):
        return hash(self.__str)

    def __str__(self):
        # type: () -> str
        return self.__str

    def __repr__(self):
        return f"CaseInsensitive({self.__str})"

    def __eq__(self, other):
        # type: (Any) -> bool
        return self.__str.casefold() == str(other).casefold()


class HashJSON(Iterable[Any]):
    def __hash__(self):
        # type: () -> int
        return hash(frozenset([
            HashDict(item.items()).__hash__() if isinstance(item, dict) else
            HashList(item).__hash__() if isinstance(item, list) else
            item
            for item in self
        ]))

    def __iter__(self):
        return super().__iter__()


class HashList(HashJSON, list):
    ...


class HashDict(HashJSON, dict):
    ...


def json_hashable(func):
    # type: (AnyCallableAnyArgs) -> Callable[[AnyCallableAnyArgs], Return]
    """
    Decorator that will transform :term:`JSON`-like dictionary and list arguments to an hashable variant.

    By making the structure hashable, it can safely be cached with :func:`functools.lru_cache`
    or :func:`functools.cache`. The decorator ignores other argument types expected to be already hashable.

    .. code-block:: python

        @json_hashable
        @functools.cache
        def function(json_data): ...

    .. seealso::
        Original inspiration: https://stackoverflow.com/a/44776960
        The code is extended to allow recursively supporting JSON-like structures.
    """

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        # type: (*Any, **Any) -> Any
        args = tuple(
            HashDict(arg) if isinstance(arg, dict) else
            HashList(arg) if isinstance(arg, list) else
            arg
            for arg in args
        )
        kwargs = {
            k: (
                HashDict(v) if isinstance(v, dict) else
                HashList(v) if isinstance(v, list) else
                v
            )
            for k, v in kwargs.items()
        }
        return func(*args, **kwargs)

    # forward caching handles
    if hasattr(func, "cache_info"):
        wrapped.cache_info = func.cache_info
    if hasattr(func, "cache_clear"):
        wrapped.cache_clear = func.cache_clear
    return wrapped


NUMBER_PATTERN = re.compile(r"^(?P<number>[+-]?[0-9]+[.]?[0-9]*(e[+-]?[0-9]+)?)\s*(?P<unit>.*)$")
UNIT_SI_POWER_UP = [CaseInsensitive("k"), "M", "G", "T", "P", "E", "Z", "Y"]  # allow upper 'K' often used
UNIT_SI_POWER_DOWN = ["m", "µ", "n", "p", "f", "a", "z", "y"]
UNIT_BIN_POWER = ["Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi"]

UUID_PATTERN = re.compile(colander.UUID_REGEX, re.IGNORECASE)


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
        # type: (Any) -> bool
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
        # type: () -> str
        return "<null>"

    @staticmethod
    def __nonzero__():
        return False

    __bool__ = __nonzero__
    __len__ = __nonzero__


# pylint: disable=C0103,invalid-name
null = NullType()


class SchemaRefResolver(JsonSchemaRefResolver):
    """
    Reference resolver that supports both :term:`JSON` and :term:`YAML` files from a remote location.
    """
    # only need to override the remote resolution to add YAML support
    # init overload used to patch invalid typing definition

    def __init__(self, base_uri, referrer, *_, **__):
        # type: (str, OpenAPISchema, *Any, **Any) -> None
        super(SchemaRefResolver, self).__init__(base_uri, referrer, *_, **__)  # type: ignore

    def resolve_remote(self, uri):
        # type: (str) -> OpenAPISchema
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                schema_file = fetch_file(uri, tmp_dir, headers={"Accept": ContentType.APP_JSON})
                with open(schema_file, mode="r", encoding="utf-8") as io_f:
                    result = yaml.safe_load(io_f)
        except Exception as exc:
            raise ValueError(f"External OpenAPI schema reference [{uri}] could not be loaded.") from exc

        if self.cache_remote:
            self.store[uri] = result
        return result


def get_weaver_url(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the home URL of the `Weaver` application.
    """
    value = get_settings(container).get("weaver.url", "") or ""  # handle explicit None
    return value.rstrip("/").strip()


def get_any_id(info, default=None, pop=False, key=False):
    # type: (MutableMapping[str, Any], Default, bool, bool) -> Union[str, Default]
    """
    Retrieves a dictionary `id-like` key using multiple common variations ``[id, identifier, _id]``.

    :param info: dictionary that potentially contains an `id-like` key.
    :param default: Default identifier to be returned if none of the known keys were matched.
    :param pop: If enabled, remove the matched key from the input mapping.
    :param key: If enabled, return the matched key instead of the value.
    :returns: value of the matched `id-like` key or ``None`` if not found.
    """
    for field in ["id", "identifier", "_id"]:
        if field in info:
            value = info.pop(field) if pop else info.get(field)
            return field if key else value
    return default


def get_any_value(info, default=None, file=True, data=True, pop=False, key=False):
    # type: (MutableMapping[str, Any], Any, bool, bool, bool, bool) -> AnyValueType
    """
    Retrieves a dictionary `value-like` key using multiple common variations ``[href, value, reference, data]``.

    :param info: Dictionary that potentially contains a `value-like` key.
    :param default: Default value to be returned if none of the known keys were matched.
    :param file: If enabled, file-related key names will be considered.
    :param data: If enabled, data-related key names will be considered.
    :param pop: If enabled, remove the matched key from the input mapping.
    :param key: If enabled, return the matched key instead of the value.
    :returns: Value (or key if requested) of the matched `value-like` key or ``None`` if not found.
    """
    for check, field in [(file, "href"), (data, "value"), (file, "reference"), (data, "data")]:
        if check:
            value = info.pop(field, null) if pop else info.get(field, null)
            if value is not null:
                return field if key else value
    return default


def get_any_message(info, default=""):
    # type: (JSON, str) -> str
    """
    Retrieves a dictionary 'value'-like key using multiple common variations [message, description, detail].

    :param info: Dictionary that potentially contains a 'message'-like key.
    :param default: Default message if no variation could be matched.
    :returns: value of the matched 'message'-like key or the default string if not found.
    """
    return (info.get("message") or info.get("description") or info.get("detail") or default).strip()


def is_celery():
    # type: () -> bool
    """
    Detect if the current application was executed as a :mod:`celery` command.
    """
    return sys.argv[0].rsplit("/", 1)[-1] == "celery"


def get_registry(container=None, nothrow=False):
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
    if container is None:
        # find 2 parents since 'get_settings' calls 'get_registry' to provide better context
        warnings.warn(
            f"Function [{get_caller_name()}] called from [{get_caller_name(skip=2)}] "
            "did not provide a settings container. Consider providing it explicitly.",
            UndefinedContainerWarning,
        )
    # preemptively check registry in celery if applicable
    # avoids error related to forked processes when restarting workers
    if container is None and is_celery():
        return app.conf.get("PYRAMID_REGISTRY", {})
    if isinstance(container, WerkzeugRequest) or container is None:
        return get_current_registry()
    if nothrow:
        return None
    raise TypeError(f"Could not retrieve registry from container object of type [{fully_qualified_name(container)}].")


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
    raise TypeError(f"Could not retrieve settings from container object of type [{fully_qualified_name(container)}]")


def get_header(header_name,         # type: str
               header_container,    # type: AnyHeadersContainer
               default=None,        # type: Optional[str], Optional[Union[str, List[str]]], bool
               pop=False,           # type: bool
               concat=False,        # type: bool
               ):                   # type: (...) -> Optional[Union[str, List[str]]]
    """
    Find the specified header within a header container.

    Retrieves :paramref:`header_name` by fuzzy match (independently of upper/lower-case and underscore/dash) from
    various framework implementations of *Headers*.

    :param header_name: Header to find.
    :param header_container: Where to look for :paramref:`header_name`.
    :param default: Returned value if :paramref:`header_container` is invalid or :paramref:`header_name` is not found.
    :param pop: Remove the matched header(s) by name from the input container.
    :param concat:
        Allow parts of the header name to be concatenated without hyphens/underscores.
        This can be the case in some :term:`S3` responses.
        Disabled by default to avoid unexpected mismatches, notably for shorter named headers.
    :returns: Found header if applicable, or the default value.
    """
    def fuzzy_name(_name):
        # type: (str) -> str
        return _name.lower().replace("-", "_")

    def concat_name(_name):
        # type: (str) -> str
        return _name.replace("-", " ").replace("_", " ").capitalize().replace(" ", "")

    if header_container is None:
        return default
    headers = header_container
    if isinstance(headers, (ResponseHeaders, EnvironHeaders, CaseInsensitiveDict, MappingProxyType)):
        headers = dict(headers)
    if isinstance(headers, dict):
        headers = header_container.items()
    header_name = fuzzy_name(header_name)
    for i, (h, v) in enumerate(list(headers)):
        if fuzzy_name(h) == header_name or (concat and concat_name(h) == concat_name(header_name)):
            if pop:
                if isinstance(header_container, dict):
                    del header_container[h]
                else:
                    del header_container[i]
            return v
    return default


def get_cookie_headers(header_container, cookie_header_name="Cookie"):
    # type: (AnyHeadersContainer, Optional[str]) -> HeadersType
    """
    Looks for ``cookie_header_name`` header within ``header_container``.

    :returns: new header container in the form ``{'Cookie': <found_cookie>}`` if it was matched, or empty otherwise.
    """
    try:
        cookie = get_header(cookie_header_name, header_container)
        if cookie:
            return {"Cookie": get_header(cookie_header_name, header_container)}
        return {}
    except KeyError:  # No cookie
        return {}


def get_request_args(request):
    # type: (AnyRequestType) -> AnyRequestQueryMultiDict
    """
    Extracts the parsed query string arguments from the appropriate request object strategy.

    Depending on the request implementation, attribute ``query_string`` are expected as :class:`bytes` (:mod:`werkzeug`)
    or :class:`str` (:mod:`pyramid`, :mod:`webob`). The ``query_string`` attribute is then used by ``args`` and
    ``params`` for respective implementations, but assuming their string-like formats are respected.

    .. seealso::
        https://github.com/pallets/werkzeug/issues/2710
    """
    try:
        # cannot assume/check only by object type, since they are sometimes extended with both (see 'extend_instance')
        # instead, rely on the expected 'query_string' type by each implementation
        if isinstance(request.query_string, bytes) and hasattr(request, "args"):
            return request.args
        if isinstance(request.query_string, str) and hasattr(request, "params"):
            return request.params
    except (AttributeError, TypeError):  # pragma: no cover
        LOGGER.warning(
            "Could not resolve expected query string parameter parser in request of type: [%s]. Using default parsing.",
            type(request)
        )
    # perform essentially what both implementations do
    params = parse_qsl(bytes2str(request.query_string), keep_blank_values=True)
    return dict(params)


def parse_kvp(query,                    # type: str
              key_value_sep="=",        # type: str
              pair_sep=";",             # type: str
              nested_pair_sep="",       # type: Optional[str]
              multi_value_sep=",",      # type: Optional[str]
              accumulate_keys=True,     # type: bool
              unescape_quotes=True,     # type: bool
              strip_spaces=True,        # type: bool
              case_insensitive=True,    # type: bool
              ):                        # type: (...) -> KVP
    """
    Parse key-value pairs using specified separators.

    All values are normalized under a list, whether they have a unique or multi-value definition.
    When a key is by itself (without separator and value), the resulting value will be an empty list.

    When :paramref:`accumulate_keys` is enabled, entries such as ``{key}={val};{key}={val}`` will be joined together
    under the same list as if they were specified using directly ``{key}={val},{val}`` (default separators employed
    only for demonstration purpose). Both nomenclatures can also be employed simultaneously.

    When :paramref:`nested_pair_sep` is provided, definitions that contain nested :paramref:`key_value_sep` character
    within an already established :term:`KVP` will be parsed once again.
    This will parse ``{key}={subkey1}={val1},{subkey2}={val2}`` into a nested :term:`KVP` dictionary as value under
    the top level :term:`KVP` entry ``{key}``. Separators are passed down for nested parsing,
    except :paramref:`pair_sep` that is replaced by :paramref:`nested_pair_sep`.

    .. code-blocK:: python

        >> parse_kvp("format=json&inputs=key1=value1;key2=val2,val3", pair_sep="&", nested_pair_sep=";")
        {
            'format': ['json'],
            'inputs': {
                'key1': ['value1'],
                'key2': ['val2', 'val3']
            }
        }

    :param query: Definition to be parsed as :term:`KVP`.
    :param key_value_sep: Separator that delimits the keys from their values.
    :param pair_sep: Separator that distinguish between different ``(key, value)`` entries.
    :param nested_pair_sep: Separator to parse values of pairs containing nested :term:`KVP` definition.
    :param multi_value_sep:
        Separator that delimits multiple values associated to the same key.
        If empty or ``None``, values will be left as a single entry in the list under the key.
    :param accumulate_keys: Whether replicated keys should be considered equivalent to multi-value entries.
    :param unescape_quotes: Whether to remove single and double quotes around values.
    :param strip_spaces: Whether to remove spaces around values after splitting them.
    :param case_insensitive:
        Whether to consider keys as case-insensitive.
        If ``True``, resulting keys will be normalized to lowercase. Otherwise, original keys are employed.
    :return: Parsed KVP.
    :raises HTTPBadRequest: If parsing cannot be accomplished based on parsing conditions.
    """
    if not query:
        return {}
    kvp_items = query.split(pair_sep)
    kvp = {}
    for item in kvp_items:
        k_v = item.split(key_value_sep, 1)
        if len(k_v) < 2:
            key = k_v[0]
            val = []
        else:
            key, val = k_v
            if key_value_sep in val and nested_pair_sep:
                val = parse_kvp(val, key_value_sep=key_value_sep, multi_value_sep=multi_value_sep,
                                pair_sep=nested_pair_sep, nested_pair_sep=None,
                                accumulate_keys=accumulate_keys, unescape_quotes=unescape_quotes,
                                strip_spaces=strip_spaces, case_insensitive=case_insensitive)
        if isinstance(val, str):  # in case nested KVP already processed
            arr = val.split(multi_value_sep) if multi_value_sep else [val]
            for i, val_item in enumerate(list(arr)):
                if strip_spaces:
                    val_item = val_item.strip()
                if unescape_quotes and (
                    (val_item.startswith("'") and val_item.endswith("'")) or
                    (val_item.startswith("\"") and val_item.endswith("\""))
                ):
                    val_item = val_item[1:-1]
                arr[i] = val_item
            val = arr
        if case_insensitive:
            key = key.lower()
        if strip_spaces:
            key = key.strip()
        if key in kvp:
            if not accumulate_keys:
                raise HTTPBadRequest(json={
                    "code": "InvalidParameterValue",
                    "description": f"Accumulation of replicated key {key} is not permitted for this query.",
                    "value": str(query),
                })
            if isinstance(val, dict) or isinstance(kvp[key], dict):
                raise HTTPBadRequest(json={
                    "code": "InvalidParameterValue",
                    "description": f"Accumulation of replicated key {key} is not permitted for nested definitions.",
                    "value": str(query),
                })
            kvp[key].extend(val)
        else:
            kvp[key] = val
    return kvp


def get_url_without_query(url):
    # type: (Union[str, ParseResult]) -> str
    """
    Removes the query string part of an URL.
    """
    if isinstance(url, str):
        url = urlparse(url)
    if not isinstance(url, ParseResult):
        raise TypeError("Expected a parsed URL.")
    return str(urlunsplit(url[:4] + tuple([""])))


def is_valid_url(url):
    # type: (Optional[str]) -> TypeGuard[str]
    try:
        return bool(urlparse(url).scheme)
    except (TypeError, ValueError):
        return False


class VersionLevel(Constants):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class VersionFormat(Constants):
    OBJECT = "object"  # Version
    STRING = "string"  # "x.y.z"
    PARTS = "parts"    # tuple/list


@overload
def as_version_major_minor_patch(version, version_format):
    # type: (AnyVersion, Literal[VersionFormat.OBJECT]) -> Version
    ...


@overload
def as_version_major_minor_patch(version, version_format):
    # type: (AnyVersion, Literal[VersionFormat.STRING]) -> str
    ...


@overload
def as_version_major_minor_patch(version, version_format):
    # type: (AnyVersion, Literal[VersionFormat.PARTS]) -> Tuple[int, int, int]
    ...


@overload
def as_version_major_minor_patch(version):
    # type: (AnyVersion) -> Tuple[int, int, int]
    ...


def as_version_major_minor_patch(version, version_format=VersionFormat.PARTS):
    # type: (Optional[AnyVersion], VersionFormat) -> AnyVersion
    """
    Generates a ``MAJOR.MINOR.PATCH`` version with padded zeros for any missing parts.
    """
    if isinstance(version, (str, float, int)):
        ver_parts = list(Version(str(version)).version)
    elif isinstance(version, (list, tuple)):
        ver_parts = [int(part) for part in version]
    else:
        ver_parts = []  # default "0.0.0" for backward compatibility
    ver_parts = ver_parts[:3]
    ver_tuple = tuple(ver_parts + [0] * max(0, 3 - len(ver_parts)))
    if version_format in [VersionFormat.STRING, VersionFormat.OBJECT]:
        ver_str = ".".join(str(part) for part in ver_tuple)
        if version_format == VersionFormat.STRING:
            return ver_str
        return Version(ver_str)
    return ver_tuple


def is_update_version(version, taken_versions, version_level=VersionLevel.PATCH):
    # type: (AnyVersion, Iterable[AnyVersion], VersionLevel) -> TypeGuard[AnyVersion]
    """
    Determines if the version corresponds to an available update version of specified level compared to existing ones.

    If the specified version corresponds to an older version compared to available ones (i.e.: a taken more recent
    version also exists), the specified version will have to fit within the version level range to be considered valid.
    For example, requesting ``PATCH`` level will require that the specified version is greater than the last available
    version against other existing versions with equivalent ``MAJOR.MINOR`` parts. If ``1.2.0`` and ``2.0.0`` were
    taken versions, and ``1.2.3`` has to be verified as the update version, it will be considered valid since its
    ``PATCH`` number ``3`` is greater than all other ``1.2.x`` versions (it falls within the ``[1.2.x, 1.3.x[`` range).
    Requesting instead ``MINOR`` level will require that the specified version is greater than the last available
    version against existing versions of same  ``MAJOR`` part only. Using again the same example values, ``1.3.0``
    would be valid since its ``MINOR`` part ``3`` is greater than any other ``1.x`` taken versions. On the other hand,
    version ``1.2.4`` would not be valid as ``x = 2`` is already taken by other versions considering same ``1.x``
    portion (``PATCH`` part is ignored in this case since ``MINOR`` is requested, and ``2.0.0`` is ignored as not the
    same ``MAJOR`` portion of ``1`` as the tested version). Finally, requesting a ``MAJOR`` level will require
    necessarily that the specified version is greater than all other existing versions for update, since ``MAJOR`` is
    the highest possible semantic part, and higher parts are not available to define an upper version bound.

    .. note::
        As long as the version level is respected, the actual number of this level and all following ones can be
        anything as long as they are not taken. For example, ``PATCH`` with existing ``1.2.3`` does not require that
        the update version be ``1.2.4``. It can be ``1.2.5``, ``1.2.24``, etc. as long as ``1.2.x`` is respected.
        Similarly, ``MINOR`` update can provide any ``PATCH`` number, since ``1.x`` only must be respected. From
        existing ``1.2.3``, ``MINOR`` update could specify ``1.4.99`` as valid version. The ``PATCH`` part does not
        need to start back at ``0``.

    :param version: Version to validate as potential update revision.
    :param taken_versions: Existing versions that cannot be reused.
    :param version_level: Minimum level to consider availability of versions as valid revision number for update.
    :return: Status of availability of the version.
    """

    def _pad_incr(_parts, _index=None):  # type: (Tuple[int, ...], Optional[int]) -> Tuple[int, ...]
        """
        Pads versions to always have 3 parts in case some were omitted, then increment part index if requested.
        """
        _parts = list(_parts) + [0] * max(0, 3 - len(_parts))
        if _index is not None:
            _parts[_index] += 1
        return tuple(_parts)

    if not taken_versions:
        return True

    version = as_version_major_minor_patch(version)
    other_versions = sorted([as_version_major_minor_patch(ver) for ver in taken_versions])
    ver_min = other_versions[0]
    for ver in other_versions:  # find versions just above and below specified
        if ver == version:
            return False
        if version < ver:
            # if next versions are at the same semantic level as requested one,
            # then not an update version since another higher one is already defined
            # handle MAJOR separately since it can only be the most recent one
            if version_level == VersionLevel.MINOR:
                if _pad_incr(version[:1]) == _pad_incr(ver[:1]):
                    return False
            elif version_level == VersionLevel.PATCH:
                if _pad_incr(version[:2]) == _pad_incr(ver[:2]):
                    return False
            break
        ver_min = ver
    else:
        # major update must be necessarily the last version,
        # so no lower version found to break out of loop
        if version_level == VersionLevel.MAJOR:
            return _pad_incr(version[:1]) > _pad_incr(other_versions[-1][:1])

    # if found previous version and next version was not already taken
    # the requested one must be one above previous one at same semantic level,
    # and must be one below the upper semantic level to be an available version
    # (eg: if PATCH requested and found min=1.3.4, then max=1.4.0, version can be anything in between)
    if version_level == VersionLevel.MAJOR:
        min_version = _pad_incr(ver_min[:1], 0)
        max_version = (float("inf"), float("inf"), float("inf"))
    elif version_level == VersionLevel.MINOR:
        min_version = _pad_incr(ver_min[:2], 1)
        max_version = _pad_incr(ver_min[:1], 0)
    elif version_level == VersionLevel.PATCH:
        min_version = _pad_incr(ver_min[:3], 2)
        max_version = _pad_incr(ver_min[:2], 1)
    else:
        raise NotImplementedError(f"Unknown version level: {version_level!s}")
    return min_version <= tuple(version) < max_version


def is_uuid(maybe_uuid):
    # type: (Any) -> TypeGuard[AnyUUID]
    """
    Evaluates if the provided input is a UUID-like string.
    """
    if not isinstance(maybe_uuid, str):
        return False
    return re.match(UUID_PATTERN, str(maybe_uuid)) is not None


def as_int(value, default):
    # type: (Any, int) -> int
    """
    Ensures a value is converted to :class:`int`.
    """
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        pass
    return default


def parse_extra_options(option_str, sep=","):
    # type: (str, str) -> Dict[str, Optional[str]]
    """
    Parses the extra options parameter.

    The :paramref:`option_str` is a string with coma separated ``opt=value`` pairs.

    .. code-block:: text

        tempdir=/path/to/tempdir,archive_root=/path/to/archive

    :param option_str: A string parameter with the extra options.
    :param sep: separator to employ in order to split the multiple values within the option string.
    :return: A dict with the parsed extra options.
    """
    if option_str:
        try:
            extra_options = [opt.split("=", 1) for opt in option_str.split(sep)]
            extra_options = {opt[0].strip(): (opt[1].strip() if len(opt) > 1 else None) for opt in extra_options}
        except Exception as exc:
            msg = f"Can not parse extra-options: [{option_str}]. Caused by: [{exc}]"
            raise ConfigurationError(msg)
    else:
        extra_options = {}
    return extra_options


def extend_instance(obj, cls):
    # type: (OriginalClass, Type[ExtenderMixin]) -> ExtendedClass
    """
    Extend an existing instance of a given class by applying new definitions from the specified mixin class type.
    """
    base_cls = obj.__class__
    obj.__class__ = type(obj.__class__.__name__, (base_cls, cls), {})
    return obj


def fully_qualified_name(obj):
    # type: (Union[Any, Type[Any]]) -> str
    """
    Obtains the full path definition of the object to allow finding and importing it.

    For classes, functions and exceptions, the following format is returned:

    .. code-block:: python

        module.name

    The ``module`` is omitted if it is a builtin object or type.

    For methods, the class is also represented, resulting in the following format:

    .. code-block:: python

        module.class.name
    """
    if inspect.ismethod(obj):
        return ".".join([obj.__module__, obj.__qualname__])
    cls = obj if inspect.isclass(obj) or inspect.isfunction(obj) else type(obj)
    if "builtins" in getattr(cls, "__module__", "builtins"):  # sometimes '_sitebuiltins'
        return cls.__name__
    return ".".join([cls.__module__, cls.__name__])


def import_target(target, default_root=None):
    # type: (str, Optional[str]) -> Optional[Any]
    """
    Imports a target resource class or function from a Python script as module or directly from a module reference.

    The Python script does not need to be defined within a module directory (i.e.: with ``__init__.py``).
    Files can be imported from virtually anywhere. To avoid name conflicts in generated module references,
    each imported target employs its full escaped file path as module name.

    Formats expected as follows:

    .. code-block:: text

        "path/to/script.py:function"
        "path/to/script.py:Class"
        "module.path.function"
        "module.path.Class"

    :param target: Resource to be imported.
    :param default_root: Root directory to employ if target is relative (default :data:`magpie.constants.MAGPIE_ROOT`).
    :return: Found and imported resource or None.
    """
    if ":" in target:
        mod_path, target = target.rsplit(":", 1)
        if not mod_path.startswith("/"):
            if default_root:
                mod_root = default_root
            else:
                mod_root = os.path.abspath(os.path.curdir)
            if not os.path.isdir(mod_root):
                LOGGER.warning("Cannot import relative target, root directory not found: [%s]", mod_root)
                return None
            mod_path = os.path.join(mod_root, mod_path)
        mod_path = os.path.abspath(mod_path)
        if not os.path.isfile(mod_path):
            LOGGER.warning("Cannot import target reference, file not found: [%s]", mod_path)
            return None
        mod_name = re.sub(r"\W", "_", mod_path)
        mod_spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    else:
        mod_name = target
        mod_path, target = target.rsplit(".", 1)
        mod_spec = importlib.util.find_spec(mod_path)
    if not mod_spec:
        LOGGER.warning("Cannot import target reference [%s], not found in file: [%s]", mod_name, mod_path)
        return None

    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    return getattr(mod, target, None)


def open_module_resource_file(module, file_path):
    # type: (Union[str, ModuleType], str) -> IO[str]
    """
    Opens a resource (data file) from an installed module.

    :returns: File stream handler to read contents as needed.
    """
    loader = get_loader(module)
    # Python <=3.6, no 'get_resource_reader' or 'open_resource' on loader/reader
    # Python >=3.10, no 'open_resource' directly on loader
    # Python 3.7-3.9, both permitted in combination
    try:
        try:
            reader = loader.get_resource_reader()  # type: importlib.abc.ResourceReader  # noqa
        except AttributeError:
            reader = loader  # noqa
        buffer = reader.open_resource(file_path)
        return io.TextIOWrapper(buffer, encoding="utf-8")
    except AttributeError:
        path = os.path.join(module.__path__[0], file_path)
        return open(path, mode="r", encoding="utf-8")


def now(tz_name=None):
    # type: (Optional[str]) -> datetime
    """
    Obtain the current time with timezone-awareness.

    :param tz_name: If specified, returned current time will be localized to specified timezone.
    """
    return localize_datetime(datetime.now().astimezone(), tz_name=tz_name)


def wait_secs(run_step=-1):
    # type: (int) -> int
    """
    Obtain a wait time in seconds within increasing delta intervals based on iteration index.
    """
    secs_list = (2, 2, 2, 2, 2, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 20, 20, 20, 20, 20, 30)
    if run_step >= len(secs_list):
        run_step = -1
    return secs_list[run_step]


def localize_datetime(dt, tz_name=None):
    # type: (datetime, Optional[str]) -> datetime
    """
    Provide a timezone-aware datetime for a given datetime and timezone name.

    .. warning::
        Any datetime provided as input that is not already timezone-aware will be assumed to be relative to the
        current locale timezone. This is the default returned by naive :class:`datetime.datetime` instances.

    If no timezone name is provided, the timezone-aware datatime will be localized with locale timezone offset.
    Otherwise, the desired localization will be applied with the specified timezone offset.
    """
    tz_aware_dt = dt
    if dt.tzinfo is None:
        tz_aware_dt = dt.astimezone()  # guess local timezone
    if tz_name is None:
        return tz_aware_dt
    timezone = pytz.timezone(tz_name)
    if tz_aware_dt.tzinfo == timezone:
        warnings.warn("tzinfo already set", TimeZoneInfoAlreadySetWarning)
    else:
        tz_aware_dt = tz_aware_dt.astimezone(timezone)
    return tz_aware_dt


def get_file_header_datetime(dt):
    # type: (datetime) -> str
    """
    Obtains the standard header datetime representation.

    .. seealso::
        Format of the date defined in :rfc:`5322#section-3.3`.
    """
    dt_gmt = localize_datetime(dt, "GMT")
    dt_str = dt_gmt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    return dt_str


def create_content_id(first_id, second_id):
    # type: (AnyUUID, AnyUUID) -> str
    """
    Generate a unique content id from passed ids.

    Both ids can be strings or UUIDs.
    """
    return f"<{first_id}@{second_id}>"


def get_href_headers(
    path,                                   # type: str
    download_headers=False,                 # type: bool
    location_headers=True,                  # type: bool
    content_headers=False,                  # type: bool
    content_type=None,                      # type: Optional[str]
    content_disposition_type="attachment",  # type: Literal["attachment", "inline"]
    content_location=None,                  # type: Optional[str]
    content_name=None,                      # type: Optional[str]
    content_id=None,                        # type: Optional[str]
    missing_ok=False,                       # type: bool
    settings=None,                          # type: Optional[SettingsType]
    **option_kwargs,                        # type: Unpack[Union[SchemeOptions, RequestOptions]]
):                                          # type: (...) -> MetadataResult
    """
    Obtain headers applicable for the provided file or directory reference.

    :rtype: object
    :param path: File to describe. Either a local path or remote URL.
    :param download_headers:
        If enabled, add the ``Content-Disposition`` header with attachment/inline filename for downloading the file.
        If the reference is a directory, this parameter is ignored, since files must be retrieved individually.
    :param location_headers:
        If enabled, add the ``Content-Location`` header referring to the input location.
    :param content_headers: If enabled, add other relevant ``Content-`` prefixed headers.
    :param content_type:
        Explicit ``Content-Type`` to provide.
        Otherwise, use default guessed by file system (often ``application/octet-stream``).
        If the reference is a directory, this parameter is ignored and ``application/directory`` will be enforced.
        Requires that :paramref:`content_headers` is enabled.
    :param content_disposition_type:
        Whether ``inline`` or ``attachment`` should be used.
        Requires that :paramref:`content_headers` and :paramref:`download_headers` are enabled.
    :param content_location:
        Override ``Content-Location`` to include in headers. Otherwise, defaults to the :paramref:`path`.
        Requires that :paramref:`location_headers` and :paramref:`content_headers` are enabled in each case.
    :param content_name:
        Optional ``name`` parameter to assign in the ``Content-Disposition`` header.
        Requires that :paramref:`content_headers` and :paramref:`download_headers` are enabled.
    :param content_id:
        Optional ``Content-ID`` to include in the headers.
        Requires that :paramref:`content_headers` is enabled.
        This should be a uniquely identifiable reference *across the server* (not just within a specific response),
        which can be used for cross-referencing by ``{cid:<>}`` within and between multipart document contents.
        For a generic ID or field name, employ :paramref:`content_name` instead.
    :param missing_ok:
        If the referenced resource does not exist (locally or remotely as applicable), and that content information
        to describe it cannot be retrieved, either raise an error (default) or resume with the minimal information
        details that could be resolved.
    :param settings: Application settings to pass down to relevant utility functions.
    :return: Headers for the reference.
    """
    href = path
    if not any(href.startswith(proto) for proto in ["file", "http", "https", "s3"]):
        href = f"file://{os.path.abspath(path)}"
        href += "/" if (path.endswith("/") and not href.endswith("/")) else ""
    f_enc = None
    f_size = None
    f_type = None
    f_modified = None

    # handle directory
    if path.endswith("/"):
        download_headers = False
        dir_path = path[7:] if path.startswith("file://") else path
        listing = fetch_directory(
            href,
            # files will not be "fetched" under the director since using 'META' output method,
            # but the actual path is needed to get the file os.stats, to obtain their metadata
            out_dir=dir_path,
            out_method=OutputMethod.META,
            settings=settings,
            **option_kwargs,
        )
        if listing:
            f_modified = parse_dt(sorted([get_header("Last-Modified", meta, concat=True) for meta in listing])[-1])
            f_size = sum(int(get_header("Content-Length", meta, default=0)) for meta in listing)
        else:  # either empty directory, filtered contents, or failed to retrieve listing
            f_size = "0"
        f_type = ContentType.APP_DIR

    # handle single file
    else:
        options, kwargs = resolve_scheme_options(**option_kwargs)
        configs = get_request_options("HEAD", href, settings)
        options["http"].update(**configs)

        if path.startswith("s3://") or path.startswith("https://s3."):
            try:
                s3_region = None
                if path.startswith("https://s3."):
                    path, s3_region = resolve_s3_from_http(path)
                s3_params = resolve_s3_http_options(**options["http"], **kwargs)
                s3_region = s3_region or options["s3"].pop("region_name", None)
                s3_client = boto3.client("s3", region_name=s3_region, **s3_params)  # type: S3Client
                s3_bucket, file_key = path[5:].split("/", 1)
                s3_file = s3_client.head_object(Bucket=s3_bucket, Key=file_key)
                f_type = content_type or s3_file["ContentType"]
                f_size = s3_file["ContentLength"]
                f_modified = s3_file["LastModified"]
            except (ClientError, HTTPClientError):
                if not missing_ok:
                    raise

        elif path.startswith("http://") or path.startswith("https://"):
            resp = request_extra("HEAD", href, **options["http"])
            if resp.status_code != 200 and not missing_ok:
                raise ValueError(f"Could not obtain file reference metadata from [{href}]")
            if resp.status_code == 200:
                f_modified = parse_dt(resp.last_modified)
                f_type = content_type or resp.content_type
                f_size = resp.content_length
                f_enc = resp.content_encoding

        else:
            try:
                path = path.split("file://", 1)[-1]
                stat = os.stat(path)
                f_type = content_type
                f_size = stat.st_size
                f_modified = datetime.fromtimestamp(stat.st_mtime)
            except OSError:
                if not missing_ok:
                    raise

    headers = {}
    if content_headers:
        if content_id:
            headers["Content-ID"] = content_id
        if location_headers:
            headers["Content-Location"] = content_location or href
        c_type, c_enc = guess_file_contents(href)
        f_type = f_type or content_type  # in case of error, all above failed, use provided content-type if any
        if not f_type:  # last resort, guess from file path
            if c_type == ContentType.APP_OCTET_STREAM:  # default
                f_ext = os.path.splitext(path)[-1]
                f_type = get_content_type(f_ext, charset="UTF-8", default=ContentType.APP_OCTET_STREAM)
            else:
                f_type = c_type
        f_enc = f_enc or c_enc or ""
        headers.update({
            "Content-Type": f_type,
            "Content-Encoding": f_enc,
        })
        if f_size is not None:
            headers["Content-Length"] = str(f_size)
        if download_headers:
            if os.path.splitext(path)[-1] in ["", "."]:
                f_ext = get_extension(f_type, dot=True)
                path = f"{path}{f_ext}"
            # set name, then filename, to align with order employed by requests-toolbelt multipart class
            content_disposition_params = f"name=\"{content_name}\"; "if content_name else ""
            content_disposition_params += f"filename=\"{os.path.basename(path)}\""
            headers["Content-Disposition"] = f"{content_disposition_type}; {content_disposition_params}"
    f_current = get_file_header_datetime(now())
    headers["Date"] = f_current
    if f_modified:
        f_modified = get_file_header_datetime(f_modified)
        headers["Last-Modified"] = f_modified
    return headers


def make_link_header(
    href,           # type: Union[str, Link]
    hreflang=None,  # type: Optional[str]
    rel=None,       # type: Optional[str]
    type=None,      # type: Optional[str]  # noqa
    title=None,     # type: Optional[str]
    charset=None,   # type: Optional[str]
    **kwargs,       # type: Optional[str]
):                  # type: (...) -> str
    """
    Creates the HTTP Link (:rfc:`8288`) header value from input parameters or a dictionary representation.

    Parameter names are specifically selected to allow direct unpacking from the dictionary representation.
    Otherwise, a dictionary can be passed as the first parameter, allowing other parameters to act as override values.
    Alternatively, all parameters can be supplied individually.

    .. note::
        Parameter :paramref:`rel` is optional to allow unpacking with a single parameter,
        but its value is required to form a valid ``Link`` header.
    """
    if isinstance(href, dict):
        rel = rel or href.get("rel")
        type = type or href.get("type")  # noqa
        title = title or href.get("title")
        charset = charset or href.get("charset")  # noqa
        hreflang = hreflang or href.get("hreflang")
        params = {key: val for key, val in href.items() if val and isinstance(val, str)}
        kwargs.update(params)
        href = href["href"]
    link = f"<{href}>; rel=\"{rel}\""
    if type:
        link += f"; type=\"{type}\""
    if charset:
        link += f"; charset=\"{charset}\""
    if title:
        link += f"; title=\"{title}\""
    if hreflang:
        link += f"; hreflang={hreflang}"
    if kwargs:
        for key, val in kwargs.items():
            link += f"; {key}={val}"
    return link


def parse_link_header(link_header):
    # type: (str) -> Link
    """
    Parses the parameters of the ``Link`` header.
    """
    url, params = link_header.split(";", 1)
    href = url.strip("<>")
    params = parse_kvp(params, multi_value_sep=None, accumulate_keys=False)
    ctype = (params.pop("type", None) or [None])[0]
    rel = str(params.pop("rel")[0])
    link = {"href": href, "rel": rel}  # type: Link
    if ctype and isinstance(ctype, str):
        link["type"] = ctype
    link.update({param: value[0] for param, value in params.items() if value})
    return link


def get_base_url(url):
    # type: (str) -> str
    """
    Obtains the base URL from the given ``url``.
    """
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        raise ValueError("bad url")
    service_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path.strip()}"
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

    Given an :class:`HTTPError` of any type (:mod:`pyramid`, :mod:`requests`), ignores the exception if the actual
    error matches the status code. Other exceptions are re-raised.
    This is equivalent to capturing a specific ``Exception`` within an ``except`` block and calling ``pass`` to drop it.

    :param exception: Any :class:`Exception` instance.
    :param expected_http_error: Single or list of specific pyramid `HTTPError` to handle and ignore.
    :raise exception: If it doesn't match the status code or is not an `HTTPError` of any module.
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
    # type: (AnyStr) -> bytes
    """
    Obtains the bytes representation of the string.
    """
    if not isinstance(string, (str, bytes)):
        raise TypeError(f"Cannot convert item to bytes: {type(string)!r}")
    if isinstance(string, bytes):
        return string
    return string.encode("UTF-8")


def bytes2str(string):
    # type: (AnyStr) -> str
    """
    Obtains the unicode representation of the string.
    """
    if not isinstance(string, (str, bytes)):
        raise TypeError(f"Cannot convert item to unicode: {type(string)!r}")
    if not isinstance(string, bytes):
        return string
    return string.decode("UTF-8")


def data2str(data):
    # type: (Union[AnyValueType, io.IOBase]) -> str
    """
    Converts literal data to a plain string representation.
    """
    if hasattr(data, "seek"):
        data.seek(0)
    if hasattr(data, "read"):
        data = data.read()
    if not isinstance(data, (str, bytes)):
        data = str(data)
    return bytes2str(data)


def islambda(func):
    # type: (Any) -> bool
    return isinstance(func, type(lambda: None)) and func.__name__ == (lambda: None).__name__


first_cap_re = re.compile(r"(.)([A-Z][a-z]+)")
all_cap_re = re.compile(r"([a-z0-9])([A-Z])")


def get_path_kvp(path, sep=",", **params):
    # type: (str, str, **AnyValueType) -> str
    """
    Generates the URL with Key-Value-Pairs (:term:`KVP`) query parameters.

    :param path: WPS URL or Path
    :param sep: separator to employ when multiple values are provided.
    :param params: keyword parameters and their corresponding single or multi values to generate KVP.
    :return: combined path and query parameters as KVP.
    """

    def _value(_v):
        # type: (Any) -> str
        if isinstance(_v, (list, set, tuple)):
            return sep.join([str(_) for _ in _v])
        return str(_v)

    kvp = [f"{k}={_value(v)}" for k, v in params.items()]
    return f"{path}?{'&'.join(kvp)}"


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
    return f"Monitoring job {job_id} : [{status}] {percent} - {message} [{location}]"


def get_job_log_msg(status, message, progress=0, duration=None):
    # type: (Union[Status, str], str, Optional[Number], Optional[str]) -> str
    duration = f"{duration} " if duration is not None else ""
    return f"{duration}{int(progress or 0):3d}% {map_status(status):10} {message}"


def setup_loggers(settings=None,            # type: Optional[AnySettingsContainer]
                  level=None,               # type: Optional[Union[int, str]]
                  force_stdout=False,       # type: bool
                  message_format=None,      # type: Optional[str]
                  datetime_format=None,     # type: Optional[str]
                  log_file=None,            # type: Optional[str]
                  ):                        # type: (...) -> logging.Logger
    """
    Update logging configuration known loggers based on application settings.

    When ``weaver.log_level`` exists in settings, it **overrides** any other INI configuration logging levels.
    Otherwise, undefined logger levels will be set according to whichever is found first between ``weaver.log_level``,
    the :paramref:`level` parameter or default :py:data:`logging.INFO`.
    """
    log_level = (settings or {}).get("weaver.log_level")
    override = False
    if log_level:
        override = True
    else:
        log_level = level or logging.INFO
    if not isinstance(log_level, int):
        log_level = logging.getLevelName(log_level.upper())
    message_format = message_format or get_log_fmt()
    datetime_format = datetime_format or get_log_date_fmt()
    formatter = logging.Formatter(fmt=message_format, datefmt=datetime_format)
    for logger_name in ["weaver", "cwltool"]:
        logger = logging.getLogger(logger_name)
        if override or logger.level == logging.NOTSET:
            logger.setLevel(log_level)
        # define basic formatter/handler if config INI did not provide it
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        if force_stdout:
            all_handlers = logging.root.handlers + logger.handlers
            if not any(isinstance(h, logging.StreamHandler) for h in all_handlers):
                handler = logging.StreamHandler(sys.stdout)
                handler.setFormatter(formatter)
                logger.addHandler(handler)  # noqa: type
        if log_file:
            all_handlers = logging.root.handlers + logger.handlers
            if not any(isinstance(h, logging.FileHandler) for h in all_handlers):
                handler = logging.FileHandler(log_file)
                handler.setFormatter(formatter)
                logger.addHandler(handler)
    return logging.getLogger("weaver")


def make_dirs(path, mode=0o755, exist_ok=False):
    # type: (str, int, bool) -> None
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


def get_caller_name(skip=0, base_class=False, unwrap=True):
    # type: (int, bool, bool) -> str
    """
    Find the name of a parent caller function or method.

    The name is returned with respective formats ``module.class.method`` or ``module.function``.

    Supposing the following call stack ``main -> func2 -> func1 -> func0 -> get_caller_name``.
    Calling ``get_caller_name()`` or ``get_caller_name(skip=0)`` would return the full package location of ``func0``
    because it is the function were ``get_caller_name`` is called from. Using ``get_caller_name(skip=1)``
    would return ``func1`` directly (parent 1-level above ``func0``), and ``func2`` for ``get_caller_name(skip=2)``.

    :param skip:
        Specifies how many levels of stack to skip for getting the caller.
        By default, uses ``skip=0`` to obtain the immediate function that called :func:`get_caller_name`.
    :param base_class:
        Specified if the base class should be returned or the top-most class in case of inheritance
        If the caller is not a class, this doesn't do anything.
    :param unwrap:
        If the caller matching the ``skip`` position is detected to be a function decorated by :func:`functools.wraps`,
        its parent function will be returned instead to reflect the function that was decorated rather than the
        decorator itself.
    :returns: An empty string if skipped levels exceed stack height; otherwise, the requested caller name.
    """
    # reference: https://gist.github.com/techtonik/2151727

    def unfold_stack(frame):
        # type: (FrameType) -> List[FrameType]
        frame_list = []
        while frame:
            frame_list.append(frame)
            frame = frame.f_back
        return frame_list

    def get_frame_caller_name(frame):
        # type: (FrameType) -> str
        name = []
        module = inspect.getmodule(frame)
        # `modname` can be None when frame is executed directly in console
        if module:
            # frame module in case of inherited classes will point to base class
            # but frame local will still refer to top-most class when checking for 'self'
            # (stack: top(mid).__init__ -> mid(base).__init__ -> base.__init__)
            name.append(module.__name__)
        # detect class name
        if "self" in frame.f_locals:
            # I don't know any way to detect call from the object method
            # XXX: there seems to be no way to detect static method call - it will
            #      be just a function call
            cls = frame.f_locals["self"].__class__
            if not base_class and module and inspect.isclass(cls):
                name[0] = cls.__module__
            name.append(cls.__name__)
        codename = frame.f_code.co_name
        if codename != "<module>":  # top level usually
            name.append(codename)  # function or a method
        return ".".join(name)

    stack = unfold_stack(sys._getframe(1))  # noqa: W0212  # index 1 to skip this own function call
    start = 0 + skip
    if len(stack) < start + 1:
        return ""

    callee_frame = stack[start]
    if unwrap:
        # must look higher levels to get the locals available within the current 'parent' level
        # this is so that we can detect the function passed to 'functools.wraps'
        callee_index = 1
        callee_search = True
        while callee_search:
            callee_parent = stack[start + callee_index]
            for callee in callee_parent.f_locals.values():
                if callable(callee) and hasattr(callee, "__wrapped__"):
                    callee_frame = callee_parent
                    callee_index += 1
                    break
            else:
                # if we did unwrap multiple levels, backtrack to the current one
                if callee_index > 2:
                    callee_frame = stack[start + callee_index - 2]
                callee_search = False

    callee_name = get_frame_caller_name(callee_frame)
    del callee_frame
    return callee_name


def setup_cache(settings, reset=True):
    # type: (SettingsType, bool) -> None
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
            settings.pop(key)  # ensure the old name variant doesn't persist (for reset)
    if reset:
        reset_cache()
    # apply defaults to avoid missing items during runtime
    settings["cache.regions"] = "doc, request, result, quotation"
    settings.setdefault("cache.type", "memory")
    settings.setdefault("cache.doc.enable", "false")
    settings.setdefault("cache.doc.expired", "3600")
    settings.setdefault("cache.request.enabled", "false")
    settings.setdefault("cache.request.expire", "60")
    settings.setdefault("cache.result.enabled", "false")
    settings.setdefault("cache.result.expire", "3600")
    settings.setdefault("cache.quotation.enabled", "true")
    settings.setdefault("cache.quotation.expire", "3600")  # consider API limits and rate-limiting, caching for 1h
    set_cache_regions_from_settings(settings)


def reset_cache(regions=None):
    # type: (Optional[List[str]]) -> None
    """
    Invalidates caches for all regions and functions decorated by :func:`beaker.cache.cache_region` or manually cached.

    :param regions:
        List of specific regions to reset. Others are unmodified.
        If omitted, clear all caches regardless of regions.
    """
    # because of references maintained within different objects, we must clear both managers and the caches,
    # although they should technically refer to same definitions, but should still be "not yet" stored as manager
    managers = list(cache_managers.values()) + [
        Cache._get_cache(region_name, region_settings)
        for region_name, region_settings in cache_regions.items()
    ]
    for cache in managers:  # type: Cache
        if regions and cache.namespace_name not in regions:  # pragma: no cover
            continue
        # Force an explicit clear for memory manager, even though following 'do_remove' and 'clear' should collapse
        # the full processing chain itself... Seems to not properly resolve in some cases (threading/timing/weak-refs)?
        if isinstance(cache.namespace, MemoryNamespaceManager):
            cache.namespace.namespaces.clear()
        cache.namespace.do_remove()
        cache.clear()


def invalidate_region(caching_args):
    # type: (Tuple[Callable, str, Tuple[Any]]) -> None
    """
    Caching region invalidation with handling to ignore errors generated by of unknown regions.

    :param caching_args: tuple of ``(function, region, *function-args)`` representing caching key to invalidate.
    """
    func, region, *args = caching_args
    try:
        region_invalidate(func, region, *args)
    except (BeakerException, KeyError):  # ignore if cache region not yet generated
        pass


def get_ssl_verify_option(method, url, settings, request_options=None):
    # type: (str, str, AnySettingsContainer, Optional[RequestOptions]) -> bool
    """
    Obtains the SSL verification option considering multiple setting definitions and the provided request context.

    Obtains the SSL verification option from combined settings from ``weaver.ssl_verify``
    and parsed ``weaver.request_options`` file for the corresponding request.

    :param method: request method (GET, POST, etc.).
    :param url: request URL.
    :param settings: application setting container with preloaded *request options* specifications.
    :param request_options: preprocessed *request options* for method/URL to avoid parsing the settings again.
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


def get_no_cache_option(request_headers, **cache_options):
    # type: (HeadersType, **bool | RequestOptions) -> bool
    """
    Obtains the ``No-Cache`` result from request headers and configured :term:`Request Options`.

    .. seealso::
        - :meth:`Request.headers`
        - :func:`get_request_options`

    :param request_headers: specific request headers that could indicate ``Cache-Control: no-cache``.
    :param cache_options: specific request options that could define ``cache[_enabled]: True|False``.
    :return: whether to disable cache or not
    """
    no_cache_header = str(get_header("Cache-Control", request_headers)).lower().replace(" ", "")
    no_cache = no_cache_header in ["no-cache", "max-age=0", "max-age=0,must-revalidate"]
    cache_params = ["cache", "cache_enabled"]
    no_cache = no_cache is True or any(cache_options.get(cache, True) is False for cache in cache_params)
    return no_cache


def get_request_options(method, url, settings):
    # type: (str, str, AnySettingsContainer) -> RequestOptions
    """
    Obtains the :term:`Request Options` corresponding to the request from the configuration file.

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
        LOGGER.warning(
            "No settings container provided. Request options might not be applied as expected. Calling references: %s",
            "->".join(f"[{get_caller_name(skip=pos)}]" for pos in reversed(range(1, 7)))
        )
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
            url = f"{url}/"  # allow 'domain.com' match since 'urlmatch' requires slash in 'domain.com/*'
        if not urlmatch(req_regex, url, path_required=False):
            continue
        req_opts = deepcopy(req_opts)
        req_opts.pop("url", None)
        req_opts.pop("method", None)
        return req_opts
    return request_options


def retry_on_condition(operation,               # type: AnyCallableAnyArgs
                       *args,                   # type: Params.args
                       condition=Exception,     # type: RetryCondition
                       retries=1,               # type: int
                       interval=0,              # type: Number
                       **kwargs,                # type: Params.kwargs
                       ):                       # type: (...) -> Return
    """
    Retries the operation call up to the amount of specified retries if the condition is encountered.

    :param operation: Any callable lambda, function, method, class that sporadically raises an exception to catch.
    :param condition:
        Exception(s) to catch or callable that takes the raised exception to handle it with more conditions.
        In case of a callable, success/failure result should be returned to indicate if retry is needed.
        If retry is not requested by the handler for the specified exception, it is raised directly.
    :param retries: Amount of retries to perform. If retries are exhausted, the final exception is re-raised.
    :param interval: wait time interval (seconds) between retries.
    :return: Expected normal operation return value if it was handled within the specified amount of retries.
    """
    if (
        (inspect.isclass(condition) and issubclass(condition, Exception)) or
        (
            hasattr(condition, "__iter__") and
            all(inspect.isclass(_exc) and issubclass(_exc, Exception) for _exc in condition)
        )
    ):
        condition_check = lambda _exc: isinstance(_exc, condition)  # noqa: E731  # pylint: disable=C3001
    else:
        condition_check = condition

    # zero is similar to no-retry (not much point to pass through this call if passed explicitly, but valid)
    if not isinstance(retries, int) or retries <= 0:
        LOGGER.warning("Invalid retry amount must be a positive integer, got '%s'. "
                       "Using no-retry pass-through operation.", retries)
        retries = 0

    name = fully_qualified_name(operation)
    remain = retries
    last_exc = None
    LOGGER.debug("Running operation '%s' with conditional retries (%s).", name, retries)
    while remain >= 0:
        try:
            sig = inspect.signature(operation)
            if sig.parameters:
                return operation(*args, **kwargs)
            return operation()
        except Exception as exc:
            if not condition_check(exc):
                LOGGER.error("Operation '%s' failed with unhandled condition to retry. Aborting.", name)
                raise exc
            remain -= 1
            attempt = retries - remain
            last_exc = exc
            LOGGER.warning("Operation '%s' failed but matched handler condition for retry. Retrying (%s/%s)...",
                           name, attempt, retries)
            if interval and remain:
                time.sleep(interval)
    LOGGER.error("Operation '%s' still failing. Maximum retry attempts reached (%s).", name, retries)
    raise last_exc


def retry_on_cache_error(func):
    # type: (AnyCallable) -> AnyCallable
    """
    Decorator to handle invalid cache setup.

    Any function wrapped with this decorator will retry execution once if missing cache setup was the cause of error.
    """
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        # type: (*Any, **Any) -> Return
        try:
            return func(*args, **kwargs)
        except BeakerException as exc:
            if "Cache region not configured" in str(exc):
                LOGGER.debug("Invalid cache region setup detected, retrying operation after setup...")
                setup_cache(get_settings() or {})
            else:  # pragma: no cover
                raise  # if not the expected cache exception, ignore retry attempt
        try:
            return func(*args, **kwargs)
        except BeakerException as exc:  # pragma: no cover
            LOGGER.error("Invalid cache region setup could not be resolved: [%s]", exc)
            raise
    return wrapped


def _request_call(method, url, kwargs):
    # type: (AnyRequestMethod, str, RequestCachingKeywords) -> Response
    """
    Request operation employed by :func:`request_extra` without caching.
    """
    with requests.Session() as request_session:
        if urlparse(url).scheme in ["", "file"]:
            url = f"file://{os.path.abspath(url)}" if not url.startswith("file://") else url
            request_session.mount("file://", FileAdapter())
        resp = request_session.request(method, url, **kwargs)
    return resp


@cache_region("request")
def _request_cached(method, url, kwargs):
    # type: (AnyRequestMethod, str, RequestCachingKeywords) -> Response
    """
    Cached-enabled request operation employed by :func:`request_extra`.
    """
    return _request_call(method, url, kwargs)


def _patch_cached_request_stream(response, stream=False):
    # type: (AnyResponseType, bool) -> None
    """
    Preserves a cached copy of a streamed response contents to allow resolution when reloaded from cache.

    When response contents are streamed, the resulting :class:`Response` object does not contain the contents until the
    aggregated result is obtained by calling :meth:`Response.contents`, :meth:`Response.text` or :meth:`Response.`json`
    methods. If no function ends up being called to aggregate the chunks with :meth:`Response.contents`, and instead
    makes use of one of the interator :meth:`Response.iter_contents`, :meth:`Response.iter_lines` or
    :meth:`Response.__iter__` methods, the object stored in cache ends up in an invalid state where it believes
    contents were already consumed (cannot re-iterate), but are not available anymore to provide them on following
    request calls that reloads it from cache. This patches the object by caching the contents after iterating the
    chunks to allow them to be retrieved for future cached requests.
    """
    if stream:
        # content not yet consumed, first request call just freshly cached
        # don't consume the content, otherwise it might break calling code
        # instead, reapply the same chunk yield, but keep a copy for reuse
        if not getattr(response, "_content_consumed", False):

            iter_content = getattr(response, "iter_content")

            def cached_iter_content(*_, **__):
                # type: (*Any, **Any) -> None
                cached_content = b""
                for chunk in iter_content(*_, **__):
                    cached_content += chunk
                    yield chunk
                # Cache the result, which would be done after calling 'response.content',
                # but which is not automatically accomplished when calling 'iter_content'.
                # Setting '_content' will allow reuse of the chunks by simulated iterator.
                # (see 'requests/models.Response.iter_content' definition)
                setattr(response, "_content", cached_content)
                setattr(response, "_content_consumed", True)

            setattr(response, "iter_content", cached_iter_content)


@retry_on_cache_error
def request_extra(method,                           # type: AnyRequestMethod
                  url,                              # type: str
                  retries=None,                     # type: Optional[int]
                  backoff=None,                     # type: Optional[Number]
                  intervals=None,                   # type: Optional[List[Number]]
                  retry_after=True,                 # type: bool
                  allowed_codes=None,               # type: Optional[List[int]]
                  only_server_errors=True,          # type: bool
                  ssl_verify=None,                  # type: Optional[bool]
                  cache_request=_request_cached,    # type: RequestCachingFunction
                  cache_enabled=True,               # type: bool
                  settings=None,                    # type: Optional[AnySettingsContainer]
                  **request_kwargs,                 # type: Unpack[RequestOptions]
                  ):                                # type: (...) -> AnyResponseType
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
    Any other :py:exc:`IOError` types are converted to 400 responses.

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
    :param cache_request: Decorated function with :func:`cache_region` to perform the request if cache was not hit.
    :param cache_enabled: Whether caching must be used for this request. Disable overrides request options and headers.
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
    request_kwargs = request_options  # update ref to ensure following modifications consider all parameters
    # catch kw passed to request corresponding to 'retries' parameters
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
    no_cache = get_no_cache_option(request_kwargs.get("headers", {}), cache_enabled=cache_enabled, **request_options)
    # remove leftover options unknown to requests method in case of multiple entries
    # see 'requests.request' detailed signature for applicable args
    known_req_opts = set(inspect.signature(requests.Session.request).parameters)
    known_req_opts -= {"url", "method"}  # add as unknown to always remove them since they are passed by arguments
    for req_opt in set(request_kwargs) - known_req_opts:
        request_kwargs.pop(req_opt)
    stream = request_kwargs.get("stream", False)
    region = cache_request._arg_region  # noqa
    request_args = (method, url, request_kwargs)
    caching_args = (cache_request, region, *request_args)
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
                resp = cache_request(*request_args)
                _patch_cached_request_stream(resp, stream)
            if allowed_codes:  # check by itself first if specified to bypass following check of error codes
                if resp.status_code in allowed_codes:
                    return resp
            elif resp.status_code < (500 if only_server_errors else 400):
                return resp
            invalidate_region(caching_args)
            reason = getattr(resp, "reason", type(resp).__name__)
            err_code = getattr(resp, "status_code", getattr(resp, "code", 500))
            failures.append(f"{reason} ({err_code})")
        # function called without retries raises original error as if calling requests module directly
        except (requests.ConnectionError, requests.Timeout) as exc:
            if no_retries:
                raise
            invalidate_region(caching_args)
            failures.append(type(exc).__name__)
    # also pass-through here if no retries
    if no_retries and resp:
        return resp
    detail = f"Request ran out of retries. Attempts generated following errors: {failures}"
    err = HTTPGatewayTimeout(detail=detail)
    # make 'raise_for_status' method available for convenience
    setattr(err, "url", url)
    setattr(err, "reason", err.explanation)
    setattr(err, "raise_for_status", lambda: Response.raise_for_status(err))  # noqa
    return err


def get_secure_filename(file_name):
    # type: (str) -> str
    """
    Obtain a secure file name.

    Preserves leading and trailing underscores contrary to :func:`secure_filename`.
    """
    new_name = file_name.lstrip("_")
    prefix = "_" * (len(file_name) - len(new_name))
    file_name = new_name
    new_name = file_name.rstrip("_")
    suffix = "_" * (len(file_name) - len(new_name))
    file_name = new_name
    while ".." in file_name:
        file_name = file_name.replace("..", ".")
    return f"{prefix}{secure_filename(file_name)}{suffix}"


def get_secure_directory_name(location):
    # type: (str) -> str
    """
    Obtain a secure directory name from a full path location.

    Takes a location path and finds the first secure base name available from path.
    If no secure base name is found, a random UUID value will be returned.
    """
    location_list = location.split("/")
    for list_element in reversed(location_list):
        potential_directory_name = get_secure_filename(list_element)
        if potential_directory_name:
            return potential_directory_name
    # If no potential secured directory name is found, a random one is generated
    unique_directory_name = str(uuid.uuid4())
    return unique_directory_name


def get_secure_path(location):
    # type: (str) -> str
    """
    Obtain a secure path location with validation of each nested component.
    """
    # consider path with potential scheme
    parts = location.split("://", 1)  # type: List[str]
    if len(parts) > 1:
        scheme, ref = parts
    else:
        scheme, ref = None, parts[0]

    # validate parts
    parts = ref.split("/")
    for i, part in enumerate(parts):
        parts[i] = get_secure_filename(part)
    start = "/" if ref.startswith("/") else ""
    trail = "/" if ref.endswith("/") and ref != "/" else ""
    secure_ref = start + "/".join(path for path in parts if path) + trail
    secure_loc = f"{scheme}://{secure_ref}" if scheme else secure_ref
    return secure_loc


def download_file_http(file_reference, file_outdir, settings=None, callback=None, **request_kwargs):
    # type: (str, str, Optional[AnySettingsContainer], Optional[Callable[[str], None]], **Any) -> str
    """
    Downloads the file referenced by an HTTP URL location.

    Respects :rfc:`2183`, :rfc:`5987` and :rfc:`6266` regarding ``Content-Disposition`` header handling to resolve
    any preferred file name. This value is employed if it fulfills validation criteria. Otherwise, the name is extracted
    from the last part of the URL path.

    :param file_reference: HTTP URL where the file is hosted.
    :param file_outdir: Output local directory path under which to place the downloaded file.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param callback:
        Function that gets called progressively with incoming chunks from downloaded file.
        Can be used to monitor download progress or raise an exception to abort it.
    :param request_kwargs: Additional keywords to forward to request call (if needed).
    :return: Path of the local copy of the fetched file.
    :raises HTTPException: applicable HTTP-based exception if any unrecoverable problem occurred during fetch request.
    :raises ValueError: when resulting file name value is considered invalid.
    """

    LOGGER.debug("Fetch file resolved as remote URL reference.")
    request_kwargs.pop("stream", None)
    resp = request_extra("GET", file_reference, stream=True, retries=3, settings=settings, **request_kwargs)
    if resp.status_code >= 400:  # pragma: no cover
        # use method since response object does not derive from Exception, therefore cannot be raised directly
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        raise resp

    # resolve preferred file name or default to last fragment of request path
    file_name = None
    content_type = get_header("Content-Type", resp.headers, default=ContentType.TEXT_PLAIN)
    content_type_ext = get_extension(content_type) or ".txt"
    content_disposition = get_header("Content-Disposition", resp.headers)
    if content_disposition:
        LOGGER.debug("Detected Content-Disposition, looking for preferred file name...")
        options = CaseInsensitiveDict(parse_extra_options(content_disposition, sep=";"))
        file_name_param = options.get("filename")
        file_name_star = options.get("filename*")
        if file_name_star and "''" in file_name_star:
            file_name_encoding, file_name_star = file_name_star.split("''")
            try:
                file_name_star = unquote(file_name_star, file_name_encoding, errors="strict")
            except (LookupError, UnicodeDecodeError):
                file_name_star = None

        # security validation, remove any nested path and abort if any invalid characters
        for file_name_var in [file_name_star, file_name_param]:
            try:
                file_name_maybe = (file_name_var or "").rsplit("/", 1)[-1].strip().replace(" ", "_")
                file_name_maybe = FILE_NAME_QUOTE_PATTERN.match(file_name_maybe)["filename"]
                file_name_secure, file_ext_secure = os.path.splitext(get_secure_filename(file_name_maybe))
                if (
                    file_name_maybe and file_name_secure and  # minimum length is one valid character if no extension
                    len(file_name_maybe) < 256 and  # ensure maximum length respected, including the extension
                    len(file_name_maybe) == len(f"{file_name_secure}{file_ext_secure}")  # skip if dropped characters
                ):
                    file_name = file_name_maybe
                    LOGGER.debug("Using validated Content-Disposition preferred file name: [%s]", file_name)
                    break
            except (IndexError, TypeError):
                LOGGER.debug("Discarding Content-Disposition preferred file name due to failed validation.")

    file_url = None
    if not file_name:
        file_url = file_name = urlparse(file_reference).path.split("/")[-1]
        LOGGER.debug("Using default file name from URL path fragment: [%s]", file_name)

    # Check secure name/extension components individually since a default extension could be resolved if not explicitly
    # provided through 'Content-Disposition' header. Consider that explicitly provided no-extension file name is valid.
    file_name, file_ext = os.path.splitext(file_name)
    file_name = get_secure_filename(file_name)
    file_ext = get_secure_filename(file_ext) if file_ext or file_url is None else get_secure_filename(content_type_ext)
    if not FILE_NAME_LOOSE_PATTERN.match(file_name):
        raise ValueError(
            f"Invalid file name [{file_name!s}] resolved from URL [{file_reference}]. "
            "Aborting download."
        )
    if file_ext:
        if not FILE_NAME_LOOSE_PATTERN.match(file_ext):
            raise ValueError(
                f"Invalid file extension [{file_ext!s}] resolved from URL [{file_reference}]. "
                "Aborting download."
            )
        file_ext = f".{file_ext}"

    file_name = f"{file_name}{file_ext}"
    file_path = os.path.join(file_outdir, file_name)
    with open(file_path, "wb") as file:  # pylint: disable=W1514
        # NOTE:
        #   Setting 'chunk_size=None' lets the request find a suitable size according to
        #   available memory. Without this, it defaults to 1 which is extremely slow.
        for chunk in resp.iter_content(chunk_size=None):
            if callback:
                callback(chunk)
            file.write(chunk)
    return file_path


def validate_s3(*, region, bucket):
    # type: (Any, str, str) -> None
    """
    Validate patterns and allowed values for :term:`AWS` :term:`S3` client configuration.
    """
    if not re.match(AWS_S3_REGIONS_REGEX, region) or region not in AWS_S3_REGIONS:
        raise ValueError(f"Invalid AWS S3 Region format or value for: [{region!s}]\n")
    if not re.match(AWS_S3_BUCKET_NAME_PATTERN, bucket):
        raise ValueError(f"Invalid AWS S3 Bucket format or value for: [{bucket!s}]\n")
    LOGGER.debug("All valid AWS S3 parameters: [Region=%s, Bucket=%s]", region, bucket)


def resolve_s3_from_http(reference):
    # type: (str) -> Tuple[str, RegionName]
    """
    Resolve an HTTP URL reference pointing to an S3 Bucket into the shorthand URL notation with S3 scheme.

    The expected reference should be formatted with one of the following supported formats.

    .. code-block:: text

        # Path-style URL
        https://s3.{Region}.amazonaws.com/{Bucket}/[{dirs}/][{file-key}]

        # Virtual-hosted–style URL
        https://{Bucket}.s3.{Region}.amazonaws.com/[{dirs}/][{file-key}]

        # Access-Point-style URL
        https://{AccessPointName}-{AccountId}.s3-accesspoint.{Region}.amazonaws.com/[{dirs}/][{file-key}]

        # Outposts-style URL
        https://{AccessPointName}-{AccountId}.{outpostID}.s3-outposts.{Region}.amazonaws.com/[{dirs}/][{file-key}]

    .. seealso::
        References on formats:

        - https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
        - https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-bucket-intro.html
        - https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-access-points.html
        - https://docs.aws.amazon.com/AmazonS3/latest/userguide/S3onOutposts.html

    .. seealso::
        References on resolution:

        - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html

    :param reference: HTTP-S3 URL reference.
    :return: Updated S3 reference and applicable S3 Region name.
    """
    s3 = boto3.client("s3")         # type: S3Client  # created with default, environment, or ~/.aws/config
    s3_url = s3.meta.endpoint_url   # includes the region name, to be used to check if we must switch region
    s3_region = s3.meta.region_name
    try:
        if not reference.startswith(s3_url):
            LOGGER.warning(
                "Detected HTTP reference to AWS S3 bucket [%s] that mismatches server region configuration [%s]. "
                "Attempting to switch S3 region for proper resolution.",
                reference, s3_region
            )
            s3_parsed = urlparse(reference)
            s3_host = s3_parsed.hostname
            s3_path = s3_parsed.path
            if ".s3-outposts." in s3_host:
                # boto3 wants:
                # Bucket ARN =
                #   - arn:aws:s3-outposts:{Region}:{AccountId}:outpost/{OutpostId}/bucket/{Bucket}
                #   - arn:aws:s3-outposts:{Region}:{AccountId}:outpost/{OutpostId}/accesspoint/{AccessPointName}
                s3_outpost, s3_region = s3_host.split(".s3-outposts.", 1)
                s3_access_point, s3_outpost_id = s3_outpost.rsplit(".", 1)
                s3_access_name, s3_account = s3_access_point.rsplit("-", 1)
                s3_region = s3_region.split(".amazonaws.com", 1)[0]
                s3_ref = s3_path
                s3_prefix = f"{AWS_S3_ARN}-outposts"
                s3_arn = f"{s3_prefix}:{s3_region}:{s3_account}:outpost/{s3_outpost_id}/accesspoint/{s3_access_name}"
                s3_reference = f"s3://{s3_arn}{s3_ref}"
            elif ".s3-accesspoint." in s3_host:
                # boto3 wants:
                # Bucket ARN = arn:aws:s3:{Region}:{AccountId}:accesspoint/{AccessPointName}
                s3_access_point, s3_region = s3_host.split(".s3-accesspoint.", 1)
                s3_access_name, s3_account = s3_access_point.rsplit("-", 1)
                s3_region = s3_region.split(".amazonaws.com", 1)[0]
                s3_ref = s3_path
                s3_arn = f"{AWS_S3_ARN}:{s3_region}:{s3_account}:accesspoint/{s3_access_name}"
                s3_reference = f"s3://{s3_arn}{s3_ref}"
            elif ".s3." in s3_host:
                s3_bucket, s3_region = reference.split(".s3.", 1)
                s3_region, s3_ref = s3_region.split(".amazonaws.com", 1)
                s3_bucket = s3_bucket.rsplit("://", 1)[-1].strip("/")
                s3_ref = s3_ref.lstrip("/")
                s3_reference = f"s3://{s3_bucket}/{s3_ref}"
            else:
                s3_region, s3_ref = reference.split("https://s3.")[-1].split(".amazonaws.com")
                s3_ref = s3_ref.lstrip("/")
                s3_reference = f"s3://{s3_ref}"
        else:
            s3_ref = reference.replace(s3_url, "")
            s3_ref = s3_ref.lstrip("/")
            s3_reference = f"s3://{s3_ref}"
        if not re.match(AWS_S3_BUCKET_REFERENCE_PATTERN, s3_reference) or not s3_ref:
            raise ValueError("No S3 bucket, region or file/directory reference was "
                             f"found from input reference [{reference}].")
    except (IndexError, TypeError, ValueError) as exc:
        s3_valid_formats = [
            "https://s3.{Region}.amazonaws.com/{Bucket}/[{dirs}/][{file-key}]",
            "https://{Bucket}.s3.{Region}.amazonaws.com/[{dirs}/][{file-key}]",
            "https://{AccessPointName}-{AccountId}.s3-accesspoint.{Region}.amazonaws.com/[{dirs}/][{file-key}]",
            "s3://{Bucket}/[{dirs}/][{file-key}]  (**default region**)"  # not parsed here, but show as valid option
        ]
        raise ValueError(f"Invalid AWS S3 reference format. Could not parse unknown: [{reference!s}]\n"
                         f"Available formats:\n{repr_json(s3_valid_formats, indent=2)}") from exc
    LOGGER.debug("Adjusting HTTP reference to S3 URL style with resolved S3 Region:\n"
                 "  Initial: [%s]\n"
                 "  Updated: [%s]\n"
                 "  Region:  [%s]",
                 reference, s3_reference, s3_region)
    return s3_reference, s3_region


def resolve_s3_reference(s3_reference):
    # type: (str) -> Tuple[str, str, Optional[RegionName]]
    """
    Resolve a reference of :term:`S3` scheme into the appropriate formats expected by :mod:`boto3`.

    :param s3_reference: Reference with ``s3://`` scheme with an ARN or literal Bucket/Object path.
    :return: Tuple of resolved Bucket name, Object path and S3 Region.
    """
    s3_ref = s3_reference[5:]
    if s3_ref.startswith(AWS_S3_ARN):
        s3_arn_match = re.match(AWS_S3_BUCKET_REFERENCE_PATTERN, s3_reference)
        if not s3_arn_match:
            raise ValueError(
                f"Invalid AWS S3 ARN reference must have one of [accesspoint, outpost] target. "
                f"None could be found in [{s3_reference}]."
            )
        if s3_arn_match["type_name"] == "outpost":
            parts = s3_arn_match["path"].split("/", 4)
            s3_bucket = s3_arn_match["bucket"] + "/".join(parts[:3])
            file_key = "/".join(parts[3:])
        elif s3_arn_match["type_name"] == "accesspoint":
            s3_bucket = s3_arn_match["bucket"]
            file_key = s3_arn_match["path"]
        else:
            raise ValueError(
                "Invalid AWS S3 ARN reference must have one of [accesspoint, outpost] target. "
                f"None could be found in [{s3_reference}]."
            )
        s3_region = s3_arn_match["region"]
    else:
        s3_region = None  # default or predefined by caller
        s3_bucket, file_key = s3_ref.split("/", 1)
    # files must always be relative without prefixed '/'
    # directory should always contain the trailing '/'
    if s3_reference.endswith("/"):
        if not file_key.endswith("/"):
            file_key += "/"
    else:
        file_key = file_key.lstrip("/")
    return s3_bucket, file_key, s3_region


def resolve_s3_http_options(**request_kwargs):
    # type: (**Any) -> Dict[str, Union[S3Config, JSON]]
    """
    Converts HTTP requests options to corresponding S3 configuration definitions.

    Resolved parameters will only preserve valid options that can be passed directly to :class:`botocore.client.S3`
    when initialized with :func:`boto3.client` in combination with ``"s3"`` service. Valid HTTP requests options that
    have been resolved will be nested under ``config`` with a :class:`S3Config` where applicable.

    :param request_kwargs: Request keywords to attempt mapping to S3 configuration.
    :return: Resolved S3 client parameters.
    """
    params = {}
    cfg_kw = {}
    if "timeout" in request_kwargs:
        cfg_kw["connect_timeout"] = request_kwargs["timeout"]
        cfg_kw["read_timeout"] = request_kwargs["timeout"]
    if "connect_timeout" in request_kwargs:
        cfg_kw["connect_timeout"] = request_kwargs["connect_timeout"]
    if "read_timeout" in request_kwargs:
        cfg_kw["read_timeout"] = request_kwargs["read_timeout"]
    if "cert" in request_kwargs:
        cfg_kw["client_cert"] = request_kwargs["cert"]  # same combination of str or (str, str) accepted
    if "verify" in request_kwargs:
        params["verify"] = request_kwargs["verify"]  # this is passed directly to the client rather than config
    retries = request_kwargs.pop("retries", request_kwargs.pop("retry", request_kwargs.pop("max_retries", None)))
    if retries is not None:
        cfg_kw["retries"] = {"max_attempts": retries}
    if "headers" in request_kwargs:
        user_agent = get_header("User-Agent", request_kwargs["headers"])
        if user_agent:
            cfg_kw["user_agent"] = user_agent
    config = S3Config(**cfg_kw)
    params["config"] = config
    return params


def resolve_scheme_options(**kwargs):
    # type: (**Any) -> Tuple[SchemeOptions, RequestOptions]
    """
    Splits options into their relevant group by scheme prefix.

    Handled schemes are defined by :data:`SUPPORTED_FILE_SCHEMES`.
    HTTP and HTTPS are grouped together and share the same options.

    :param kwargs: Keywords to categorise by scheme.
    :returns: Categorised options by scheme and all other remaining keywords.
    """
    options = {group: {} for group in SUPPORTED_FILE_SCHEMES}
    keywords = {}
    for opt, val in kwargs.items():
        if any(opt.startswith(scheme) for scheme in list(options)):
            opt, key = opt.split("_", 1)
            options[opt][key] = val
        else:
            keywords[opt] = val
    options["http"].update(options.pop("https"))
    options["https"] = options["http"]
    return options, keywords


class OutputMethod(ExtendedEnum):
    """
    Methodology employed to handle generation of a file or directory output that was fetched.
    """
    # download operations
    AUTO = "auto"
    LINK = "link"
    MOVE = "move"
    COPY = "copy"
    # metadata operations
    META = "meta"


def fetch_file(file_reference,                      # type: str
               file_outdir,                         # type: str
               *,                                   # force named keyword arguments after
               out_method=OutputMethod.AUTO,        # type: OutputMethod
               settings=None,                       # type: Optional[AnySettingsContainer]
               callback=None,                       # type: Optional[Callable[[str], None]]
               **option_kwargs,                     # type: Unpack[Union[SchemeOptions, RequestOptions]]
               ):                                   # type: (...) -> Path
    """
    Fetches a file from local path, AWS-S3 bucket or remote URL, and dumps its content to the output directory.

    The output directory is expected to exist prior to this function call.
    The file reference scheme (protocol) determines from where to fetch the content.
    Output file name and extension will be the same as the original (after link resolution if applicable).
    Requests will consider ``weaver.request_options`` when using ``http(s)://`` scheme.

    .. seealso::
        - :func:`fetch_reference`
        - :func:`resolve_scheme_options`
        - :func:`adjust_file_local`
        - :func:`download_file_http`

    :param file_reference:
        Local filesystem path (optionally prefixed with ``file://``), ``s3://`` bucket location or ``http(s)://``
        remote URL file reference. Reference ``https://s3.[...]`` are also considered as ``s3://``.
    :param file_outdir: Output local directory path under which to place the fetched file.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param callback:
        Function that gets called progressively with incoming chunks from downloaded file.
        Only applicable when download occurs (remote file reference).
        Can be used to monitor download progress or raise an exception to abort it.
    :param out_method:
        Method employed to handle the generation of the output file.
        Only applicable when the file reference is local. Remote location always generates a local copy.
    :param option_kwargs:
        Additional keywords to forward to the relevant handling method by scheme.
        Keywords should be defined as ``{scheme}_{option}`` with one of the known :data:`SUPPORTED_FILE_SCHEMES`.
        If not prefixed by any scheme, the option will apply to all handling methods (if applicable).
    :return: Path of the local copy of the fetched file.
    :raises HTTPException: applicable HTTP-based exception if any occurred during the operation.
    :raises ValueError: when the reference scheme cannot be identified.
    """
    file_href = file_reference  # keep original for reporting in case of error
    if file_href.startswith("file://"):
        file_href = file_href[7:]
    file_name = os.path.basename(os.path.realpath(file_href))  # resolve any different name to use the original
    file_name = get_secure_filename(file_name)
    file_path = os.path.join(file_outdir, file_name)
    LOGGER.debug("Fetching file reference: [%s] using options:\n%s", file_href, repr_json(option_kwargs))
    options, kwargs = resolve_scheme_options(**option_kwargs)
    if os.path.isfile(file_href):
        LOGGER.debug("Fetch file resolved as local reference.")
        file_href = get_secure_path(file_href)
        file_path = adjust_file_local(file_href, file_outdir, out_method)
    elif file_href.startswith("s3://"):
        LOGGER.debug("Fetch file resolved as S3 bucket reference.")
        s3_params = resolve_s3_http_options(**options["http"], **kwargs)
        s3_region = options["s3"].pop("region_name", None)
        s3_bucket, file_key, s3_region_ref = resolve_s3_reference(file_href)
        if s3_region and s3_region_ref and s3_region != s3_region_ref:
            raise ValueError("Invalid AWS S3 reference. "
                             f"Input region name [{s3_region}] mismatches reference region [{s3_region_ref}].")
        s3_region = s3_region_ref or s3_region
        s3_client = boto3.client("s3", region_name=s3_region, **s3_params)  # type: S3Client
        s3_client.download_file(s3_bucket, file_key, file_path, Callback=callback)
    elif file_href.startswith("http"):
        # pseudo-http URL referring to S3 bucket, try to redirect to above S3 handling method if applicable
        if file_href.startswith("https://s3.") or urlparse(file_href).hostname.endswith(".amazonaws.com"):
            LOGGER.debug("Detected HTTP-like S3 bucket file reference. Retrying file fetching with S3 reference.")
            s3_ref, s3_region = resolve_s3_from_http(file_href)
            option_kwargs.pop("s3_region", None)
            return fetch_file(s3_ref, file_outdir, settings=settings, s3_region_name=s3_region, **option_kwargs)
        file_path = download_file_http(
            file_href,
            file_outdir,
            settings=settings,
            callback=callback,
            **options["http"],
            **kwargs
        )
    else:
        scheme = file_reference.split("://", 1)
        scheme = "<none>" if len(scheme) < 2 else scheme[0]
        raise ValueError(
            f"Unresolved location and/or fetch file scheme: '{scheme!s}', "
            f"supported: {list(SUPPORTED_FILE_SCHEMES)}, reference: [{file_reference!s}]"
        )
    LOGGER.debug("Fetch file resolved:\n"
                 "  Reference: [%s]\n"
                 "  File Path: [%s]", file_href, file_path)
    return file_path


def adjust_file_local(file_reference, file_outdir, out_method):
    # type: (str, str, OutputMethod) -> Path
    """
    Adjusts the input file reference to the output location with the requested handling method.

    Handling Methods
    ~~~~~~~~~~~~~~~~~~~~~~

    - :attr:`OutputMethod.LINK`:

      Force generation of a symbolic link instead of hard copy,
      regardless if source is directly a file or a link to one.

    - :attr:`OutputMethod.COPY`:

      Force hard copy of the file to destination, regardless if source is directly a file or a link to one.

    - :attr:`OutputMethod.MOVE`:

      Move the local file to the output directory instead of copying or linking it.
      If the output directory already contains the local file, raises an :class:`OSError`.

    - :attr:`OutputMethod.AUTO` (default):

      Resolve conditionally as follows.

      * When the source is a symbolic link itself, the destination will also be a link.
      * When the source is a direct file reference, the destination will be a hard copy of the file.

    :param file_reference: Original location of the file.
    :param file_outdir: Target directory of the file.
    :param out_method: Method employed to handle the generation of the output.
    :returns: Output file location or metadata.
    """
    file_loc = os.path.realpath(file_reference)
    file_name = os.path.basename(file_loc)  # resolve any different name to use the original
    file_name = get_secure_filename(file_name)
    file_path = os.path.join(file_outdir, file_name)
    if out_method == OutputMethod.META:
        return get_href_headers(file_loc, download_header=True, content_headers=True)
    if out_method == OutputMethod.MOVE and os.path.isfile(file_path):
        LOGGER.debug("Reference [%s] cannot be moved to path [%s] (already exists)", file_reference, file_path)
        raise OSError("Cannot move file, already in output directory!")
    if out_method == OutputMethod.MOVE:
        shutil.move(file_loc, file_outdir)
        if file_loc != file_reference and os.path.islink(file_reference):
            os.remove(file_reference)
    # NOTE:
    #   If file is available locally and referenced as a system link, disabling 'follow_symlinks'
    #   creates a copy of the symlink instead of an extra hard-copy of the linked file.
    elif os.path.islink(file_reference) and not os.path.isfile(file_path):
        if out_method == OutputMethod.LINK:
            os.symlink(os.readlink(file_reference), file_path)
        else:
            shutil.copyfile(file_reference, file_path, follow_symlinks=out_method == OutputMethod.COPY)
    # otherwise copy the file if not already available
    # expand directory of 'file_path' and full 'file_reference' to ensure many symlink don't result in same place
    elif not os.path.isfile(file_path) or os.path.realpath(file_path) != os.path.realpath(file_reference):
        if out_method == OutputMethod.LINK:
            os.symlink(file_reference, file_path)
        else:
            shutil.copyfile(file_reference, file_path)
    else:
        LOGGER.debug("File as local reference has no action to take, file already exists: [%s]", file_path)
    return file_path


def filter_directory_forbidden(listing, key=None):
    # type: (Iterable[FilterType], Optional[Callable[[...], str]]) -> Iterator[FilterType]
    """
    Filters out items that should always be removed from directory listing results.
    """
    if key is None:
        def key(_):
            return _

    is_in = frozenset({"..", "../", "./"})
    equal = frozenset({"."})  # because of file extensions, cannot check 'part in item'
    for item in listing:
        path = key(item)
        if any(part in path for part in is_in):
            continue
        if any(part == path for part in equal):
            continue
        yield item


class PathMatchingMethod(ExtendedEnum):
    GLOB = "glob"
    REGEX = "regex"


def filter_directory_patterns(listing,      # type: Iterable[FilterType]
                              include,      # type: Optional[Iterable[str]]
                              exclude,      # type: Optional[Iterable[str]]
                              matcher,      # type: PathMatchingMethod
                              key=None,     # type: Optional[Callable[[...], str]]
                              ):            # type: (...) -> List[FilterType]
    """
    Filters a list of files according to a set of include/exclude patterns.

    If a file is matched against an include pattern, it will take precedence over matches on exclude patterns.
    By default, any file that is not matched by an excluded pattern will remain in the resulting filtered set.
    Include patterns are only intended to "add back" previously excluded matches. They are **NOT** for defining
    "only desired items". Adding include patterns without exclude patterns is redundant, as all files would be
    retained by default anyway.

    Patterns can use regular expression definitions or Unix shell-style wildcards.
    The :paramref:`matcher` should be selected accordingly to provided patterns matching method.
    Potential functions are :func:`re.match`, :func:`re.fullmatch`, :func:`fnmatch.fnmatch`, :func:`fnmatch.fnmatchcase`
    Literal strings for exact matches are also valid.

    .. note::
        Provided patterns are applied directly without modifications. If the file listing contains different root
        directories than patterns, such as if patterns are specified with relative paths, obtained results could
        mismatch the intended behavior. Make sure to align paths accordingly for the expected filtering context.

    :param listing: Files to filter.
    :param include: Any matching patterns for files that should be explicitly included.
    :param exclude: Any matching patterns for files that should be excluded unless included.
    :param matcher: Pattern matching method to evaluate if a file path matches include and exclude definitions.
    :param key: Function to retrieve the file key (path) from objects containing it to be filtered.
    :return: Filtered files.
    """
    if key is None:
        def key(_):
            return _

    listing_include = include or []
    listing_exclude = exclude or []
    if listing_include or listing_exclude:
        if matcher == PathMatchingMethod.REGEX:
            def is_match(pattern, value):  # type: (str, str) -> bool
                return re.fullmatch(pattern, value) is not None
        elif matcher == PathMatchingMethod.GLOB:
            def is_match(pattern, value):  # type: (str, str) -> bool
                return fnmatch.fnmatchcase(value, pattern)
        else:
            raise ValueError(f"Unknown path pattern matching method: [{matcher}]")
        filtered = [
            item for item in listing if (
                not any(is_match(re_excl, key(item)) for re_excl in listing_exclude)
                or any(is_match(re_incl, key(item)) for re_incl in listing_include)
            )
        ]
        LOGGER.debug("Filtering directory listing\n"
                     "  include:  %s\n"
                     "  exclude:  %s\n"
                     "  listing:  %s\n"
                     "  filtered: %s\n",
                     listing_include, listing_exclude, listing, filtered)
        listing = filtered
    return listing


@overload
def fetch_files_s3(location,                            # type: str
                   out_dir,                             # type: Path
                   out_method,                          # type: AnyMetadataOutputMethod
                   include=None,                        # type: Optional[List[str]]
                   exclude=None,                        # type: Optional[List[str]]
                   matcher=PathMatchingMethod.GLOB,     # type: PathMatchingMethod
                   settings=None,                       # type: Optional[SettingsType]
                   **option_kwargs,                     # type: Unpack[Union[SchemeOptions, RequestOptions]]
                   ):                                   # type: (...) -> List[MetadataResult]
    ...


@overload
def fetch_files_s3(location,                            # type: str
                   out_dir,                             # type: Path
                   out_method,                          # type: AnyDownloadOutputMethod
                   include=None,                        # type: Optional[List[str]]
                   exclude=None,                        # type: Optional[List[str]]
                   matcher=PathMatchingMethod.GLOB,     # type: PathMatchingMethod
                   settings=None,                       # type: Optional[SettingsType]
                   **option_kwargs,                     # type: Unpack[Union[SchemeOptions, RequestOptions]]
                   ):                                   # type: (...) -> List[DownloadResult]
    ...


def fetch_files_s3(location,                            # type: str
                   out_dir,                             # type: Path
                   out_method,                          # type: AnyOutputMethod
                   include=None,                        # type: Optional[List[str]]
                   exclude=None,                        # type: Optional[List[str]]
                   matcher=PathMatchingMethod.GLOB,     # type: PathMatchingMethod
                   settings=None,                       # type: Optional[SettingsType]
                   **option_kwargs,                     # type: Unpack[Union[SchemeOptions, RequestOptions]]
                   ):                                   # type: (...) -> List[AnyOutputResult]
    """
    Download all listed S3 files references under the output directory using the provided S3 bucket and client.

    If nested directories are employed in the file paths, they will be downloaded with the same directory hierarchy
    under the requested output directory.

    .. seealso::
        Filtering is subject to :func:`filter_directory_patterns` and :func:`filter_directory_forbidden`.

    :param location: S3 bucket location (with ``s3://`` scheme) targeted to retrieve files.
    :param out_dir: Desired output location of downloaded files.
    :param out_method: Method employed to handle the generation of the output.
    :param include: Any matching patterns for files that should be explicitly included.
    :param exclude: Any matching patterns for files that should be excluded unless included.
    :param matcher: Pattern matching method to evaluate if a file path matches include and exclude definitions.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param option_kwargs:
        Additional keywords to forward to the relevant handling method by scheme.
        Keywords should be defined as ``{scheme}_{option}`` with one of the known :data:`SUPPORTED_FILE_SCHEMES`.
        If not prefixed by any scheme, the option will apply to all handling methods (if applicable).
    :returns: Output locations of downloaded files.
    """
    LOGGER.debug("Resolving S3 connection and options for directory listing.")
    options, kwargs = resolve_scheme_options(**option_kwargs)
    configs = get_request_options("GET", location, settings)
    options["http"].update(**configs)
    s3_params = resolve_s3_http_options(**options["http"], **kwargs)
    s3_region = options["s3"].pop("region_name", None)
    s3_client = boto3.client("s3", region_name=s3_region, **s3_params)  # type: S3Client
    s3_bucket, dir_key = location[5:].split("/", 1)
    base_url = f"{s3_client.meta.endpoint_url.rstrip('/')}/"

    # adjust patterns with full paths to ensure they still work with retrieved relative S3 keys
    include = [incl.replace(base_url, "", 1) if incl.startswith(base_url) else incl for incl in include or []]
    exclude = [excl.replace(base_url, "", 1) if excl.startswith(base_url) else excl for excl in exclude or []]

    LOGGER.debug("Resolved S3 Bucket [%s] and Region [%s] for download of files.", s3_bucket, s3_region or "default")
    s3_paging = s3_client.get_paginator("list_objects_v2")
    LOGGER.debug("Fetching S3 directory [%s] listing.", location)
    s3_files = (  # definitions with relative paths (like patterns)
        file
        for s3_dir_resp in s3_paging.paginate(Bucket=s3_bucket, Prefix=dir_key)
        for file in s3_dir_resp["Contents"]
    )
    s3_files = (file for file in s3_files if not file["Key"].endswith("/"))
    s3_files = filter_directory_forbidden(s3_files, key=lambda _file: _file["Key"])
    s3_files = filter_directory_patterns(s3_files, include, exclude, matcher, key=lambda _file: _file["Key"])

    if out_method == OutputMethod.META:
        s3_files = list(s3_files)   # ensure generator is not pre-exhausted by following loop
        for file_meta in s3_files:  # type: MetadataResult
            file_key = file_meta.pop("Key")
            file_meta["Content-Location"] = f"{base_url}{file_key}"
        return s3_files

    s3_files = [file["Key"] for file in s3_files]

    # create directories in advance to avoid potential errors in case many workers try to generate the same one
    base_url = base_url.rstrip("/")
    sub_dirs = {os.path.split(str(path))[0] for path in s3_files if "://" not in path or path.startswith(base_url)}
    sub_dirs = [os.path.join(out_dir, path.replace(base_url, "").lstrip("/")) for path in sub_dirs]
    for _dir in reversed(sorted(sub_dirs)):
        os.makedirs(_dir, exist_ok=True)
    base_url += "/"

    LOGGER.debug("Starting fetch of individual S3 files from [%s]:\n%s", base_url, repr_json(s3_files))
    task_kill_event = threading.Event()  # abort remaining tasks if set

    def _abort_callback(_chunk):  # called progressively with downloaded chunks
        # type: (AnyStr) -> None
        if task_kill_event.is_set():
            raise CancelledError("Other failed download task triggered abort event.")

    def _download_file(_client, _bucket, _rel_file_path, _out_dir):
        # type: (S3Client, str, str, str) -> str
        if task_kill_event.is_set():
            raise CancelledError("Other failed download task triggered abort event.")
        try:
            _out_file = os.path.join(_out_dir, _rel_file_path)
            _client.download_file(_bucket, _rel_file_path, _out_file, Callback=_abort_callback)
        except Exception as exc:
            _file_path = os.path.join(_client.meta.endpoint_url, _bucket, _rel_file_path)
            LOGGER.error("Error raised in download worker for [%s]: [%s]", _file_path, exc, exc_info=exc)
            task_kill_event.set()
            raise
        return _out_file

    max_workers = min(len(s3_files), 8)
    if max_workers <= 0:
        raise ValueError(f"No files specified for download from reference [{base_url}].")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = (
            executor.submit(_download_file, s3_client, s3_bucket, file_key, out_dir)
            for file_key in s3_files
        )
        for future in as_completed(futures):
            if future.exception():
                other_futures = set(futures) - {future}
                for o_future in other_futures:
                    o_future.cancel()
                task_kill_event.set()
            yield future.result()
        # wait for any cleanup, must use set() because of https://github.com/python/cpython/issues/86104
        results, failures = wait_until(set(futures), return_when=ALL_COMPLETED)
        if failures or any(not path for path in results):
            raise WeaverException(
                "Directory download failed due to at least one failing file download in listing: "
                f"{[repr(exc.exception()) for exc in failures]}"
            )


def fetch_files_url(file_references,                    # type: Iterable[str]
                    out_dir,                            # type: Path
                    out_method,                         # type: AnyOutputMethod
                    base_url,                           # type: str
                    include=None,                       # type: Optional[List[str]]
                    exclude=None,                       # type: Optional[List[str]]
                    matcher=PathMatchingMethod.GLOB,    # type: PathMatchingMethod
                    settings=None,                      # type: Optional[SettingsType]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> Iterator[AnyOutputResult]
    """
    Download all listed files references under the output directory.

    If nested directories are employed in file paths, relative to :paramref:`base_url`, they will be downloaded
    with the same directory hierarchy under the requested output directory. If the :paramref:`base_url` differs,
    they will simply be downloaded at the root of the output directory. If any conflict occurs in such case, an
    :class:`OSError` will be raised.

    .. seealso::
        Use :func:`download_files_s3` instead if all files share the same S3 bucket.

    :param file_references: Relative or full URL paths of the files to download.
    :param out_dir: Desired output location of downloaded files.
    :param out_method: Method employed to handle the generation of the output.
    :param base_url:
        If full URL are specified, corresponding files will be retrieved using the appropriate scheme per file
        allowing flexible data sources. Otherwise, any relative locations use this base URL to resolve the full
        URL prior to downloading the file.
    :param include: Any matching patterns for files that should be explicitly included.
    :param exclude: Any matching patterns for files that should be excluded unless included.
    :param matcher: Pattern matching method to evaluate if a file path matches include and exclude definitions.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param option_kwargs:
        Additional keywords to forward to the relevant handling method by scheme.
        Keywords should be defined as ``{scheme}_{option}`` with one of the known :data:`SUPPORTED_FILE_SCHEMES`.
        If not prefixed by any scheme, the option will apply to all handling methods (if applicable).
    :returns: Output locations of downloaded files.
    """
    LOGGER.debug("Starting file listing download from references:\n%s", repr_json(file_references))

    # References could be coming from different base URL/scheme/host.
    # The include/exclude patterns will have to match them exactly in the even they don't share the same base URL.
    # However, in the event they have the same URL, patterns could refer to their relative path only to that URL.
    # Adjust patterns accordingly to allow filter against forbidden/include/exclude with relative paths.
    base_url = f"{get_url_without_query(base_url).rstrip('/')}/"
    include = [incl.replace(base_url, "", 1) if incl.startswith(base_url) else incl for incl in include or []]
    exclude = [excl.replace(base_url, "", 1) if excl.startswith(base_url) else excl for excl in exclude or []]
    file_references = (path for path in file_references if not path.endswith("/"))
    file_refs_relative = {path for path in file_references if path.startswith(base_url)}
    file_refs_absolute = set(file_references) - file_refs_relative
    file_refs_relative = {path.replace(base_url, "") for path in file_refs_relative}
    file_refs_absolute = filter_directory_forbidden(file_refs_absolute)
    file_refs_absolute = filter_directory_patterns(file_refs_absolute, include, exclude, matcher)
    file_refs_relative = filter_directory_forbidden(file_refs_relative)
    file_refs_relative = filter_directory_patterns(file_refs_relative, include, exclude, matcher)
    file_refs_relative = {os.path.join(base_url, path) for path in file_refs_relative}
    file_references = sorted(list(set(file_refs_relative) | set(file_refs_absolute)))

    if out_method == OutputMethod.META:
        return [
            get_href_headers(
                url,
                download_headers=True,
                location_headers=True,
                content_headers=True,
                settings=settings,
                **option_kwargs
            )
            for url in file_references
        ]

    # create directories in advance to avoid potential errors in case many workers try to generate the same one
    base_url = base_url.rstrip("/")
    sub_dirs = {os.path.split(path)[0] for path in file_references if "://" not in path or path.startswith(base_url)}
    sub_dirs = [os.path.join(out_dir, path.replace(base_url, "").lstrip("/")) for path in sub_dirs]
    for _dir in reversed(sorted(sub_dirs)):
        os.makedirs(_dir, exist_ok=True)
    base_url += "/"

    LOGGER.debug("Starting fetch of individual files from [%s]:\n%s", base_url, repr_json(file_references))
    task_kill_event = threading.Event()  # abort remaining tasks if set

    def _abort_callback(_chunk):  # called progressively with downloaded chunks
        # type: (AnyStr) -> None
        if task_kill_event.is_set():
            raise CancelledError("Other failed download task triggered abort event.")

    def _download_file(_file_path):
        # type: (str) -> str
        _file_parts = _file_path.split("://", 1)
        if len(_file_parts) == 1:  # relative, no scheme
            if not base_url:
                raise ValueError(f"Cannot download relative reference [{_file_path}] without a base URL.")
            _file_path = _file_path.strip("/")
            _out_file = os.path.join(out_dir, _file_path)
            _file_path = os.path.join(base_url, _file_path)
        elif base_url and _file_path.startswith(base_url):
            _out_file = os.path.join(out_dir, _file_path.replace(base_url, ""))
        else:
            _out_file = os.path.join(out_dir, os.path.split(_file_path)[-1])
        _out_dir = os.path.split(_out_file)[0]
        try:
            return fetch_file(_file_path, _out_dir, out_method=out_method,
                              settings=settings, callback=_abort_callback, **option_kwargs)
        except Exception as exc:
            LOGGER.error("Error raised in download worker for [%s]: [%s]", _file_path, exc, exc_info=exc)
            task_kill_event.set()
            raise

    max_workers = min(len(file_references), 8)
    if max_workers <= 0:
        msg_ref = f" from reference [{base_url}]" if base_url else ""
        raise ValueError(f"No files specified for download{msg_ref}.")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = (
            executor.submit(_download_file, file_key)
            for file_key in file_references
        )
        for future in as_completed(futures):
            if future.exception():
                task_kill_event.set()
            yield future.result()


@overload
def fetch_files_html(html_data,                         # type: str
                     out_dir,                           # type: Path
                     out_method,                        # type: AnyMetadataOutputMethod
                     base_url,                          # type: str
                     include=None,                      # type: Optional[List[str]]
                     exclude=None,                      # type: Optional[List[str]]
                     matcher=PathMatchingMethod.GLOB,   # type: PathMatchingMethod
                     settings=None,                     # type: Optional[AnySettingsContainer]
                     **option_kwargs,                   # type: Unpack[Union[SchemeOptions, RequestOptions]]
                     ):                                 # type: (...) -> Iterator[MetadataResult]
    ...


@overload
def fetch_files_html(html_data,                         # type: str
                     out_dir,                           # type: Path
                     out_method,                        # type: AnyDownloadOutputMethod
                     base_url,                          # type: str
                     include=None,                      # type: Optional[List[str]]
                     exclude=None,                      # type: Optional[List[str]]
                     matcher=PathMatchingMethod.GLOB,   # type: PathMatchingMethod
                     settings=None,                     # type: Optional[AnySettingsContainer]
                     **option_kwargs,                   # type: Unpack[Union[SchemeOptions, RequestOptions]]
                     ):                                 # type: (...) -> Iterator[DownloadResult]
    ...


def fetch_files_html(html_data,                         # type: str
                     out_dir,                           # type: Path
                     out_method,                        # type: AnyOutputMethod
                     base_url,                          # type: str
                     include=None,                      # type: Optional[List[str]]
                     exclude=None,                      # type: Optional[List[str]]
                     matcher=PathMatchingMethod.GLOB,   # type: PathMatchingMethod
                     settings=None,                     # type: Optional[AnySettingsContainer]
                     **option_kwargs,                   # type: Unpack[Union[SchemeOptions, RequestOptions]]
                     ):                                 # type: (...) -> Iterator[AnyOutputResult]
    """
    Retrieves files from a directory listing provided as an index of plain HTML with file references.

    If the index itself provides directories that can be browsed down, the tree hierarchy will be downloaded
    recursively by following links. In such case, links are ignored if they cannot be resolved as a nested index pages.

    Retrieval of file references from directory listing attempts to be as flexible as possible to the HTML response
    format, by ignoring style tags and looking only for ``<a href=""/>`` references. Examples of different supported
    format representations are presented at following locations:

    - https://anaconda.org/anaconda/python/files (raw listing with text code style and minimal file metadata)
    - https://mirrors.edge.kernel.org/pub/ (listing within a formatted table with multiple other metadata fields)

    .. seealso::
        :func:`fetch_files_url`

    :param html_data: HTML data contents with files references to download.
    :param out_dir: Desired output location of retrieved files.
    :param out_method: Method employed to handle the generation of the output.
    :param base_url:
        If full URL are specified, corresponding files will be retrieved using the appropriate scheme per file
        allowing flexible data sources. Otherwise, any relative locations use this base URL to resolve the full
        URL prior to downloading the file.
    :param include: Any matching patterns for files that should be explicitly included.
    :param exclude: Any matching patterns for files that should be excluded unless included.
    :param matcher: Pattern matching method to evaluate if a file path matches include and exclude definitions.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param option_kwargs:
        Additional keywords to forward to the relevant handling method by scheme.
        Keywords should be defined as ``{scheme}_{option}`` with one of the known :data:`SUPPORTED_FILE_SCHEMES`.
        If not prefixed by any scheme, the option will apply to all handling methods (if applicable).
    :returns: Output locations of downloaded files.
    """
    options, kwargs = resolve_scheme_options(**option_kwargs)

    def _list_refs(_url, _data=None):
        # type: (str, Optional[str]) -> Iterator[str]
        if not _data:
            _scheme = _url.split("://")[0]
            _opts = options.get(_scheme, {})  # type: ignore
            _resp = request_extra("GET", _url, settings=settings, **_opts, **kwargs)
            _ctype = get_header("Content-Type", _resp.headers, default=ContentType.TEXT_HTML)
            _xml_like_ctypes = [ContentType.TEXT_HTML] + list(ContentType.ANY_XML)
            if _resp.status_code != 200 or not any(_type in _ctype for _type in _xml_like_ctypes):
                return []
            _data = _resp.text
        _html = BeautifulSoup(_data, builder=HTML_TREE_BUILDER)
        _href = (_ref.get("href") for _ref in _html.find_all("a", recursive=True))
        _href = filter_directory_forbidden(_href)  # preemptively remove forbidden items, avoid access/download attempts
        for _ref in _href:
            if not _ref.startswith(_url):
                _ref = os.path.join(_url, _ref)
            if not _ref.endswith("/"):
                yield _ref
            else:
                yield from _list_refs(_ref)

    files = list(_list_refs(base_url, html_data))
    return fetch_files_url(
        files, out_dir, out_method, base_url,
        include=include, exclude=exclude, matcher=matcher,
        settings=settings, **option_kwargs
    )


@overload
def adjust_directory_local(location,                            # type: Path
                           out_dir,                             # type: Path
                           out_method,                          # type: AnyMetadataOutputMethod
                           include=None,                        # type: Optional[List[str]]
                           exclude=None,                        # type: Optional[List[str]]
                           matcher=PathMatchingMethod.GLOB,     # type: PathMatchingMethod
                           ):                                   # type: (...) -> List[MetadataResult]
    ...


@overload
def adjust_directory_local(location,                            # type: Path
                           out_dir,                             # type: Path
                           out_method,                          # type: AnyDownloadOutputMethod
                           include=None,                        # type: Optional[List[str]]
                           exclude=None,                        # type: Optional[List[str]]
                           matcher=PathMatchingMethod.GLOB,     # type: PathMatchingMethod
                           ):                                   # type: (...) -> List[DownloadResult]
    ...


def adjust_directory_local(location,                            # type: Path
                           out_dir,                             # type: Path
                           out_method,                          # type: AnyOutputMethod
                           include=None,                        # type: Optional[List[str]]
                           exclude=None,                        # type: Optional[List[str]]
                           matcher=PathMatchingMethod.GLOB,     # type: PathMatchingMethod
                           ):                                   # type: (...) -> List[AnyOutputResult]
    """
    Adjusts the input directory reference to the output location with the requested handling method.

    Handling Methods
    ~~~~~~~~~~~~~~~~~~~~~~

    - Source location is the output directory:

      If the source location is exactly the same location as the output (after link resolution), nothing is applied,
      unless filtered listing produces a different set of files. In that case, files to be excluded will be removed
      from the file system. In other situations, below handling methods are considered.

    - :attr:`OutputMethod.LINK`:

      Force generation of the output directory as a symbolic link pointing to the original location, without any copy,
      regardless if the source location is directly a directory or a link to one.
      Not applicable if filtered listing does not match exactly the original source location listing.
      In such case, resolution will use the second :attr:`OutputMethod.AUTO` handling approach instead.

    - :attr:`OutputMethod.COPY`:

      Force hard copy of the directory to the destination, and hard copy of all its underlying contents by resolving
      any symbolic link along the way, regardless if the source location is directly a directory or a link to one.

    - :attr:`OutputMethod.MOVE`:

      Move the local directory's contents under the output directory instead of copying or linking it.
      If the output directory already contains anything, raises an :class:`OSError`.
      If exclusion filters yield any item to be omitted, those items will be deleted entirely from the file system.

    - :attr:`OutputMethod.AUTO` (default):

      Resolve conditionally as follows.

      * When the source is a symbolic link itself, the destination will be a link to it
        (handled as :attr:`OutputMethod.LINK`), unless its restriction regarding filtered listing applies.
        In that case, switches to the other handling method below.

      * When the source is a direct directory reference (or a link with differing listing after filter), the
        destination will be a recursive copy of the source directory, but any encountered links will remain links
        instead of resolving them and creating a copy (as accomplished by :attr:`OutputMethod.COPY`).

    .. seealso::
        :func:`filter_directory_patterns`

    :param location: Local reference to the source directory.
    :param out_dir: Local reference to the output directory.
    :param out_method: Method employed to handle the generation of the output.
    :param include: Any matching patterns for files that should be explicitly included.
    :param exclude: Any matching patterns for files that should be excluded unless included.
    :param matcher: Pattern matching method to evaluate if a file path matches include and exclude definitions.
    :returns: Listing of files after resolution and filtering if applicable.
    """
    if location.startswith("file://"):
        location = location[7:]
    if not os.path.isdir(location):
        raise OSError("Cannot operate with directory. "
                      f"Reference location [{location}] does not exist or is not a directory!")

    loc_dir = os.path.realpath(location)
    out_dir = os.path.realpath(out_dir) if os.path.isdir(out_dir) else out_dir
    loc_dir = f"{loc_dir.rstrip('/')}/"
    out_dir = f"{out_dir.rstrip('/')}/"
    listing = list_directory_recursive(loc_dir)
    # Use relative paths to filter items to ensure forbidden or include/exclude patterns match
    # the provided definitions as expected, since patterns more often do not use the full path.
    # In case the patterns do use full paths though, adjust them to ensure they still work as well.
    include = [incl.replace(loc_dir, "", 1) if incl.startswith(loc_dir) else incl for incl in include or []]
    exclude = [excl.replace(loc_dir, "", 1) if excl.startswith(loc_dir) else excl for excl in exclude or []]
    relative = (path.replace(loc_dir, "") for path in listing)
    relative = filter_directory_forbidden(relative)
    relative = list(sorted(relative))
    filtered = filter_directory_patterns(relative, include, exclude, matcher)
    filtered = list(sorted(filtered))
    extras = list(set(relative) - set(filtered))
    extras = [os.path.join(out_dir, path) for path in extras]
    desired = [os.path.join(loc_dir, path) for path in filtered]
    filtered = list(sorted(os.path.join(out_dir, path) for path in filtered))

    if out_method == OutputMethod.META:
        return [get_href_headers(path, download_headers=True, content_headers=True) for path in filtered]

    if loc_dir == out_dir:
        if not extras:
            LOGGER.debug("Local directory reference has no action to take, already exists: [%s]", loc_dir)
            return filtered
        LOGGER.debug("Local directory reference [%s] matches output, but desired listing differs. "
                     "Removing additional items:\n%s", loc_dir, repr_json(extras))
        for file_path in extras:
            file_path = get_secure_path(file_path)
            if os.path.isfile(file_path):
                os.remove(file_path)
        return filtered

    # Any operation (islink, remove, etc.) that must operate on the link itself rather than the directory it points
    # to must not have the final '/' in the path. Otherwise, the link path (without final '/') is resolved before
    # evaluating the operation, which make them attempt their call on the real directory itself.
    link_dir = str(location).rstrip("/")
    link_dir = get_secure_path(link_dir)

    if (os.path.exists(out_dir) and not os.path.isdir(out_dir)) or (os.path.isdir(out_dir) and os.listdir(out_dir)):
        LOGGER.debug("References under [%s] cannot be placed under target path [%s] "
                     "(output is not a directory or output directory is not empty).", location, out_dir)
        raise OSError("Cannot operate with directory."
                      f"Output location [{out_dir}] already exists or is not an empty directory!")
    if os.path.exists(out_dir):
        os.rmdir(out_dir)  # need to remove to avoid moving contents nested under it

    # avoid unnecessary copy of files marked for exclusion
    def copy_func(src, dst, *args, **kwargs):
        # type: (Path, Path, *Any, **Any) -> None
        if dst not in desired:
            shutil.copy2(src, dst, *args, **kwargs)

    if out_method == OutputMethod.MOVE:
        # Calling 'shutil.move' raises 'NotADirectoryError' if the source directory is a link
        # (although contents would still be moved). Use the resolved path to avoid the error.
        shutil.move(loc_dir, out_dir, copy_function=copy_func)
        # Remove the original link location pointing to the resolved directory to be consistent
        # with 'move' from a direct directory where the original location would not exist anymore.
        if location != loc_dir and os.path.islink(link_dir):
            os.remove(link_dir)
        for file_path in extras:
            os.remove(file_path)
        return filtered
    elif out_method == OutputMethod.LINK and not extras:  # fallback AUTO if not exact listing
        if os.path.islink(link_dir):
            loc_dir = os.readlink(link_dir)
        out_dir = out_dir.rstrip("/")
        os.symlink(loc_dir, out_dir, target_is_directory=True)
        return filtered
    # AUTO: partial copy (links remain links)
    # LINK: idem, when listing differ
    # COPY: full copy (resolve symlinks)
    shutil.copytree(loc_dir, out_dir,
                    symlinks=out_method != OutputMethod.COPY,
                    ignore_dangling_symlinks=True,
                    copy_function=copy_func)
    return filtered


def list_directory_recursive(directory, relative=False):
    # type: (Path, bool) -> Iterator[Path]
    """
    Obtain a flat list of files recursively contained within a local directory.
    """
    for path, _, files in os.walk(directory, followlinks=True):
        for file_name in files:
            yield file_name if relative else os.path.join(path, file_name)


@overload
def fetch_directory(location,                           # type: str
                    out_dir,                            # type: Path
                    *,                                  # force named keyword arguments after
                    out_method=OutputMethod.AUTO,       # type: AnyMetadataOutputMethod
                    include=None,                       # type: Optional[List[str]]
                    exclude=None,                       # type: Optional[List[str]]
                    matcher=PathMatchingMethod.GLOB,    # type: PathMatchingMethod
                    settings=None,                      # type: Optional[AnySettingsContainer]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> List[MetadataResult]
    ...


@overload
def fetch_directory(location,                           # type: str
                    out_dir,                            # type: Path
                    *,                                  # force named keyword arguments after
                    out_method=OutputMethod.AUTO,       # type: AnyDownloadOutputMethod
                    include=None,                       # type: Optional[List[str]]
                    exclude=None,                       # type: Optional[List[str]]
                    matcher=PathMatchingMethod.GLOB,    # type: PathMatchingMethod
                    settings=None,                      # type: Optional[AnySettingsContainer]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> List[DownloadResult]
    ...


def fetch_directory(location,                           # type: str
                    out_dir,                            # type: Path
                    *,                                  # force named keyword arguments after
                    out_method=OutputMethod.AUTO,       # type: OutputMethod
                    include=None,                       # type: Optional[List[str]]
                    exclude=None,                       # type: Optional[List[str]]
                    matcher=PathMatchingMethod.GLOB,    # type: PathMatchingMethod
                    settings=None,                      # type: Optional[AnySettingsContainer]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> List[AnyOutputResult]
    """
    Fetches all files that can be listed from a directory in local or remote location.

    .. seealso::
        - :func:`fetch_reference`
        - :func:`resolve_scheme_options`
        - :func:`adjust_directory_local`
        - :func:`fetch_files_html`
        - :func:`fetch_files_s3`
        - :func:`fetch_files_url`

    .. note::
        When using include/exclude filters, items that do not match a valid entry from the real listing are ignored.
        Special directories such as ``..`` and ``.`` for navigation purpose are always excluded regardless of filters.

    :param location: Directory reference (URL, S3, local). Trailing slash required.
    :param out_dir: Output local directory path under which to place fetched files.
    :param out_method:
        Method employed to handle the generation of the output directory.
        Only applicable when the file reference is local. Remote location always generates a local copy.
    :param include: Any matching patterns for files that should be explicitly included.
    :param exclude: Any matching patterns for files that should be excluded unless included.
    :param matcher: Pattern matching method to evaluate if a file path matches include and exclude definitions.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param option_kwargs:
        Additional keywords to forward to the relevant handling method by scheme.
        Keywords should be defined as ``{scheme}_{option}`` with one of the known :data:`SUPPORTED_FILE_SCHEMES`.
        If not prefixed by any scheme, the option will apply to all handling methods (if applicable).
    :returns: File locations retrieved from directory listing.
    """
    location_without_query = get_url_without_query(location)
    if not location_without_query.endswith("/"):
        raise ValueError(f"Invalid directory location [{location}] must have a trailing slash.")
    LOGGER.debug("Fetching directory reference: [%s] using options:\n%s", location, repr_json(option_kwargs))
    if location.startswith("s3://"):
        LOGGER.debug("Fetching listed files under directory resolved as S3 bucket reference.")
        listing = fetch_files_s3(location, out_dir, out_method,
                                 include=include, exclude=exclude, matcher=matcher,
                                 settings=settings, **option_kwargs)
    elif location.startswith("https://s3."):
        LOGGER.debug("Fetching listed files under directory resolved as HTTP-like S3 bucket reference.")
        s3_ref, s3_region = resolve_s3_from_http(location)
        option_kwargs["s3_region_name"] = s3_region
        listing = fetch_files_s3(s3_ref, out_dir, out_method,
                                 include=include, exclude=exclude,
                                 settings=settings, **option_kwargs)
    elif location.startswith("http://") or location.startswith("https://"):
        # Next two lines are added to match behavior of `download_files_s3` and replicate input directory name
        # in output location
        loc_path = get_secure_directory_name(location_without_query)
        out_dir = os.path.join(out_dir, loc_path)
        LOGGER.debug("Fetch directory resolved as remote HTTP reference. Will attempt listing contents.")
        resp = request_extra("GET", location, **option_kwargs)
        if resp.status_code != 200:
            LOGGER.error("Invalid response [%s] for directory listing from [%s]", resp.status_code, location)
            raise ValueError(f"Cannot parse directory location [{location}] from [{resp.status_code}] response.")
        ctype = get_header("Content-Type", resp.headers, default=ContentType.TEXT_HTML)
        if any(_type in ctype for _type in [ContentType.TEXT_HTML] + list(ContentType.ANY_XML)):
            listing = fetch_files_html(resp.text, out_dir, out_method, location,
                                       include=include, exclude=exclude, matcher=matcher,
                                       settings=settings, **option_kwargs)
        elif ContentType.APP_JSON in ctype:
            body = resp.json()  # type: JSON
            if isinstance(body, list) and all(isinstance(file, str) for file in body):
                listing = fetch_files_url(body, out_dir, out_method, location,
                                          include=include, exclude=exclude, matcher=matcher,
                                          settings=settings, **option_kwargs)
            else:
                LOGGER.error("Invalid JSON from [%s] is not a list of files:\n%s", location, repr_json(body))
                raise ValueError(f"Cannot parse directory location [{location}] "
                                 "expected as JSON response contents providing a list of files.")
        else:
            raise ValueError(f"Cannot list directory [{location}]. Unknown parsing of Content-Type [{ctype}] response.")
    elif location.startswith("file://") or location.startswith("/"):
        LOGGER.debug("Fetch directory resolved as local reference.")
        listing = adjust_directory_local(location, out_dir, out_method,
                                         include=include, exclude=exclude, matcher=matcher)
    else:
        raise ValueError(f"Unknown scheme for directory location [{location}].")
    listing = list(sorted(
        listing,
        key=lambda _file: _file["Content-Location"] if out_method == OutputMethod.META else _file
    ))
    if LOGGER.isEnabledFor(logging.DEBUG):
        for item in listing:
            LOGGER.debug("Resolved file [%s] from [%s] directory listing.", item, location)
    return listing


@overload
def fetch_reference(reference,                          # type: str
                    out_dir,                            # type: Path
                    *,                                  # force named keyword arguments after
                    out_listing=False,                  # type: Literal[False]
                    out_method=OutputMethod.AUTO,       # type: OutputMethod
                    settings=None,                      # type: Optional[AnySettingsContainer]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> str
    ...


@overload
def fetch_reference(reference,                          # type: str
                    out_dir,                            # type: Path
                    *,                                  # force named keyword arguments after
                    out_listing=False,                  # type: Literal[True]
                    out_method=OutputMethod.AUTO,       # type: OutputMethod
                    settings=None,                      # type: Optional[AnySettingsContainer]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> List[str]
    ...


def fetch_reference(reference,                          # type: str
                    out_dir,                            # type: Path
                    *,                                  # force named keyword arguments after
                    out_listing=False,                  # type: bool
                    out_method=OutputMethod.AUTO,       # type: OutputMethod
                    settings=None,                      # type: Optional[AnySettingsContainer]
                    **option_kwargs,                    # type: Unpack[Union[SchemeOptions, RequestOptions]]
                    ):                                  # type: (...) -> Union[str, List[str]]
    """
    Fetches the single file or nested directory files from a local or remote location.

    The appropriate method depends on the format of the location.
    If conditions from :ref:`cwl-dir` are met, the reference will be considered a ``Directory``.
    In every other situation, a single ``File`` reference will be considered.

    .. seealso::
        See the relevant handling methods below for other optional arguments.

        - :func:`fetch_file`
        - :func:`fetch_directory`

    :param reference:
        Local filesystem path (optionally prefixed with ``file://``), ``s3://`` bucket location or ``http(s)://``
        remote URL file or directory reference. Reference ``https://s3.[...]`` are also considered as ``s3://``.
    :param out_dir: Output local directory path under which to place the fetched file or directory.
    :param out_listing:
        Request that the complete file listing of the directory reference is returned.
        Otherwise, return the local directory reference itself.
        In the event of a file reference as input, the returned path will always be the fetched file itself, but it
        will be contained within a single-item list if listing was ``True`` for consistency in the returned type with
        the corresponding call for a directory reference.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param out_method:
        Method employed to handle the generation of the output file or directory.
        Only applicable when the reference is local. Remote location always generates a local copy.
    :param option_kwargs:
        Additional keywords to forward to the relevant handling method by scheme.
        Keywords should be defined as ``{scheme}_{option}`` with one of the known :data:`SUPPORTED_FILE_SCHEMES`.
        If not prefixed by any scheme, the option will apply to all handling methods (if applicable).
    :return: Path of the local copy of the fetched file, the directory, or the listing of the directory files.
    :raises HTTPException: applicable HTTP-based exception if any occurred during the operation.
    :raises ValueError: when the reference scheme cannot be identified.
    """
    if reference.endswith("/"):
        path = fetch_directory(reference, out_dir, out_method=out_method, settings=settings, **option_kwargs)
        path = path if out_listing else f"{os.path.realpath(out_dir)}/"
    else:
        path = fetch_file(reference, out_dir, out_method=out_method, settings=settings, **option_kwargs)
    return [path] if out_listing and isinstance(path, str) else path


class SizedUrlHandler(UrlHandler):
    """
    Avoids an unnecessary request to obtain the content size if the expected file is already available locally.
    """
    @property
    def size(self):
        if self._file:
            path = self._file[7:] if self._file.startswith("file://") else self._file
            if os.path.isfile(path):
                return int(os.stat(path).st_size)
        return super().size


def create_metalink(
    files,          # type: List[FileLink]
    version=4,      # type: Literal[3, 4]
    name=None,      # type: Optional[str]
    workdir=None,   # type: Optional[Path]
):                  # type: (...) -> AnyMetalink
    """
    Generates a MetaLink definition with provided link references.

    If the link includes a local ``file`` path, or when the ``href`` itself is a local path, the IO handler will employ
    those references to avoid the usual behavior performed by :mod:`pywps` that auto-fetches the remote file. To retain
    that behavior, simply make sure that ``href`` is a remote file and that ``path`` is unset or does not exist.

    :param files: File link, and optionally, with additional name, local path, media-type and encoding.
    :param version: Desired metalink content as defined by the corresponding version.
    :param name: Global name identifier for the metalink file.
    :param workdir: Location where to store files when auto-fetching them.
    :returns: Metalink object with appropriate template generation utilities.

    .. note::
        It is always preferable to use MetaLink V4 over V3 as it adds support for ``mediaType`` which can be critical
        for validating and/or mapping output formats in some cases. V3 also enforces "type=http" in the :mod:`pywps`
        :term:`XML` template, which is erroneous when other schemes such as ``file://`` or ``s3://`` are employed.

    .. warning::
        Regardless of MetaLink V3 or V4, ``encoding`` are not reported.
        This is a limitation of MetaLink specification itself.

    .. seealso::
        - https://en.wikipedia.org/wiki/Metalink#Example_Metalink_3.0_.metalink_file
        - https://en.wikipedia.org/wiki/Metalink#Example_Metalink_4.0_.meta4_file
        - :rfc:`5854`
        - :rfc:`6249`
    """
    meta_files = []
    for link in files:
        # find generic details
        meta_name = link.get("name")
        meta_name = str(meta_name) if meta_name is not None else None
        meta_type = link.get("type") or link.get("mediaType")
        meta_enc = link.get("encoding")
        meta_fmt = get_format(meta_type)
        if meta_fmt and not meta_fmt.encoding and meta_enc:
            meta_fmt.encoding = meta_enc
        meta_href = link["href"]
        meta_path = link.get("file")
        if meta_href.startswith("/"):
            meta_href = f"file://{meta_href}"
            meta_path = meta_path or meta_href
        elif meta_href.startswith("file://"):
            meta_path = meta_path or meta_href[7:]
        meta_file = MetaFile(identity=meta_name, fmt=meta_fmt)

        # define source IO handler
        # following steps order are important to avoid duplicate copy/fetch by pywps
        # generate a 'SizedUrlHandler' with '._output._iohandler.prop="url"' and sets '._output._iohandler._url'
        # normally, a 'UrlHandler' would be assigned automatically by using 'meta_file.file = meta_href'
        meta_file._output._iohandler = SizedUrlHandler(meta_href, meta_file._output)
        href_scheme = meta_href.split("://", 1)[0]
        # then, need to set '._output._iohandler._file' to avoid 'UrlHandler' trying to automatically fetch it
        if href_scheme == "file":
            meta_file._output._iohandler._file = meta_href
        elif meta_path and os.path.isfile(meta_path):
            meta_file._output._iohandler._file = os.path.abspath(meta_path)
        else:
            LOGGER.warning(
                "No local file path provided for [%s]."
                "Metalink reference will attempt to automatically fetch it.",
                meta_href
            )
        meta_files.append(meta_file)

    workdir = str(workdir) if workdir else None
    meta_cls = MetaLink4 if version == 4 else MetaLink
    meta_link = meta_cls(identity=name, workdir=workdir, files=tuple(meta_files))
    return meta_link


def load_file(file_path, text=False):
    # type: (Path, bool) -> Union[JSON, str]
    """
    Load :term:`JSON` or :term:`YAML` file contents from local path or remote URL.

    If URL, get the content and validate it by loading, otherwise load file directly.

    :param file_path: Local path or URL endpoint where file to load is located.
    :param text: load contents as plain text rather than parsing it from :term:`JSON`/:term:`YAML`.
    :returns: loaded contents either parsed and converted to Python objects or as plain text.
    :raises ValueError: if YAML or JSON cannot be parsed or loaded from location.
    """
    try:
        if is_remote_file(file_path):
            settings = get_settings()
            headers = {"Accept": ContentType.TEXT_PLAIN}
            cwl_resp = request_extra("GET", file_path, headers=headers, settings=settings)
            return cwl_resp.content if text else yaml.safe_load(cwl_resp.content)
        with open(file_path, mode="r", encoding="utf-8") as f:
            return f.read() if text else yaml.safe_load(f)
    except OSError as exc:
        LOGGER.debug("Loading error: %s", exc, exc_info=exc)
        raise
    except ScannerError as exc:  # pragma: no cover
        LOGGER.debug("Parsing error: %s", exc, exc_info=exc)
        raise ValueError("Failed parsing file content as JSON or YAML.")


def is_remote_file(file_location):
    # type: (str) -> TypeGuard[str]
    """
    Parses to file location to figure out if it is remotely available or a local path.
    """
    cwl_file_path_or_url = file_location.replace("file://", "")
    scheme = urlparse(cwl_file_path_or_url).scheme
    return scheme != "" and not posixpath.ismount(f"{scheme}:")  # windows partition


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
    if not isinstance(replace_character, str) or not len(replace_character) == 1:  # pragma: no cover
        raise ValueError(f"Single replace character is expected, got invalid [{replace_character!s}]")
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
    # type: (str, int, Optional[int]) -> None
    """
    Asserts that the sane name respects conditions.

    .. seealso::
        - argument details in :func:`get_sane_name`
    """
    from weaver.exceptions import InvalidIdentifierValue, MissingIdentifierValue

    if name is None or len(name) == 0:
        raise MissingIdentifierValue(f"Invalid name : {name}")
    name = name.strip()
    if (
        "--" in name
        or name.startswith("-")
        or name.endswith("-")
        or len(name) < min_len
        or (max_len is not None and len(name) > max_len)
        or not re.match(REGEX_ASSERT_INVALID_CHARACTERS, name)
    ):
        raise InvalidIdentifierValue(f"Invalid name : {name}")


def clean_json_text_body(body, remove_newlines=True, remove_indents=True, convert_quotes=True):
    # type: (str, bool, bool, bool) -> str
    """
    Cleans a textual body field of superfluous characters to provide a better human-readable text in a JSON response.
    """
    # cleanup various escape characters and u'' stings
    replaces = [
        (",\n", ", "),
        ("\\n", " "),
        (" \n", " "),
        ("\n'", "'"),
        ("u\'", "\'"),
        ("u\"", "\""),
        ("'. ", ""),
        ("'. '", ""),
        ("}'", "}"),
        ("'{", "{"),
    ]
    patterns = [
        (re.compile(r"(\w+)('{2,})([\s\]\}\)]+)"), "\\1'\\3"),
        (re.compile(r"([\s\[\{\(]+)('{2,})(\w+)"), "\\1'\\3"),
        (re.compile(r"(\w+)(\"{2,})([\s\]\}\)]+)"), "\\1\"\\3"),
        (re.compile(r"([\s\[\{\(]+)(\"{2,})(\w+)"), "\\1\"\\3"),
    ]
    if convert_quotes:
        replaces.extend([("\"", "\'")])
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
    for _from, _to in patterns:
        body = re.sub(_from, _to, body)

    if remove_newlines:
        body_parts = [p.strip() for p in body.split("\n") if p != ""]               # remove new line and extra spaces
        body_parts = [f"{p}." if not p.endswith(".") else p for p in body_parts]    # add terminating dot per sentence
        body_parts = [p[0].upper() + p[1:] for p in body_parts if len(p)]           # capitalize first word
        body_clean = " ".join(p for p in body_parts if p)
    else:
        body_clean = body

    # re-process without newlines to remove escapes created by concat of lines
    if any(rf in body_clean if isinstance(rf, str) else re.match(rf, body) for rf in replaces_from):
        body_clean = clean_json_text_body(
            body_clean,
            remove_newlines=remove_newlines,
            remove_indents=remove_indents,
            convert_quotes=convert_quotes,
        )
    return body_clean


def transform_json(json_data,               # type: Dict[str, JSON]
                   rename=None,             # type: Optional[Dict[AnyKey, Any]]
                   remove=None,             # type: Optional[List[AnyKey]]
                   add=None,                # type: Optional[Dict[AnyKey, Any]]
                   extend=None,             # type: Optional[Dict[AnyKey, Any]]
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
    :param extend: add or extend the fields names with associated values.
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
    extend = extend or {}
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

    # extend
    for k, v in extend.items():
        v = v if isinstance(v, list) else [v]
        if k in json_data:
            if isinstance(json_data[k], list):
                json_data[k].extend(v)
            else:
                json_data[k] = [json_data[k]] + v
        else:
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


def generate_diff(val, ref, val_name="Test", ref_name="Reference", val_show=False, ref_show=False, json=True, indent=2):
    # type: (Any, Any, str, str, bool, bool, bool, Optional[int]) -> str
    """
    Generates a line-by-line diff result of the test value against the reference value.

    Attempts to parse the contents as JSON to provide better diff of matched/sorted lines, and falls back to plain
    line-based string representations otherwise.

    :param val: Test input value.
    :param ref: Reference input value.
    :param val_name: Name to apply in diff for test input value.
    :param ref_name: Name to apply in diff for reference input value.
    :param val_show: Whether to include full contents of test value.
    :param ref_show: Whether to include full contents of reference value.
    :param json: Whether to consider contents as :term:`JSON` for diff evaluation.
    :param indent: Indentation to employ when using :term:`JSON` contents.
    :returns: Formatted multiline diff,
    """
    import json as _json
    if json:
        try:
            val = _json.dumps(val, sort_keys=True, indent=indent, ensure_ascii=False)
        except Exception:  # noqa
            val = str(val)
        try:
            ref = _json.dumps(ref, sort_keys=True, indent=indent, ensure_ascii=False)
        except Exception:  # noqa
            ref = str(ref)
    else:
        val = str(val)
        ref = str(ref)
    if val_show:
        val_name += f"\n\n{val}"
    if ref_show:
        ref_name += f"\n\n{ref}"
    val = val.splitlines()
    ref = ref.splitlines()
    return "\n".join(difflib.context_diff(val, ref, fromfile=val_name, tofile=ref_name))


def apply_number_with_unit(number, unit="", binary=False, decimals=3):
    # type: (Number, str, bool, int) -> str
    """
    Apply the relevant unit and prefix factor to the specified number to create a human-readable value.

    :param number: Numeric value with no unit.
    :param unit: Unit to be applied. Auto-resolved to 'B' if binary requested. Factor applied accordingly to number.
    :param binary: Use binary multiplier (powers of 2) instead of SI decimal multipliers (powers of 10).
    :param decimals: Number of decimals to preserve after unit is applied.
    :return: String of the numeric value with appropriate unit.
    """
    multiplier = 1024. if binary else 1000.
    unit = "B" if binary else unit
    factor = ""
    ratio = 1.0
    negative = number < 0
    number = -1. * number if negative else number
    if number == 0:
        pass
    elif number > multiplier:
        for exp, factor in enumerate(UNIT_SI_POWER_UP, start=1):
            if not (number / float(multiplier ** exp)) >= (multiplier - 1.):
                ratio = float(multiplier ** -exp)
                break
        else:
            ratio = float(multiplier ** -len(UNIT_SI_POWER_UP))
    elif number < multiplier:
        for exp, factor in enumerate([""] + UNIT_SI_POWER_DOWN, start=0):
            if (number * float(multiplier ** exp)) >= 1.:
                ratio = float(multiplier ** exp)
                break
        else:
            ratio = float(multiplier ** len(UNIT_SI_POWER_DOWN))
    factor = f"{factor}i" if factor and binary else factor
    factor = f" {factor}" if factor or unit else ""
    value = (-1. if negative else 1.) * number * ratio
    return f"{value:.{decimals}f}{factor}{unit}"


def parse_number_with_unit(number, binary=None):
    # type: (str, Optional[bool]) -> Number
    """
    Parses a numeric value accompanied by a unit to generate the unit-less value without prefix factor.

    :param number:
        Numerical value and unit. Unit is dissociated from value with first non-numerical match.
        Unit is assumed to be present (not only the multiplier by itself).
        This is important to avoid confusion (e.g.: ``m`` used for meters vs ``m`` prefix for "milli").
    :param binary:
        Force use (``True``) or non-use (``False``) of binary multiplier (powers of 2) instead of
        SI decimal multipliers (powers of 10) for converting value (with applicable unit multiplier if available).
        If unspecified (``None``), auto-detect from unit (e.g.: powers of 2 for ``MiB``, powers of 10 for ``MB``).
        When unspecified, the ``B`` character is used to auto-detect if binary should apply, SI multipliers are
        otherwise assumed.
    :return: Literal value.
    """
    try:
        num = re.match(NUMBER_PATTERN, number)
        grp = num.groupdict()
        f_val = float(num["number"])
        unit = grp["unit"]
        multiplier = 1
        as_bin = False
        if unit:
            as_bin = binary is None and unit[-1] == "B"
            is_bin = unit[:2] in UNIT_BIN_POWER
            is_num = unit[0] in UNIT_SI_POWER_UP
            if is_bin:
                factor = UNIT_BIN_POWER.index(unit[:2]) + 1
            elif is_num:
                factor = UNIT_SI_POWER_UP.index(unit[:1]) + 1
            else:
                factor = 0
            if binary or as_bin:
                multiplier = 2 ** (factor * 10)
            else:
                multiplier = 10 ** (factor * 3)
        f_val = f_val * multiplier
        if binary or as_bin:
            val = int(f_val + 0.5)  # round up
        else:
            i_val = int(f_val)
            val = i_val if i_val == f_val else f_val
    except (AttributeError, KeyError, ValueError, TypeError):
        raise ValueError(f"Invalid number with optional unit string could not be parsed: [{number!s}]")
    return val


def copy_doc(copy_func):
    # type: (AnyCallableAnyArgs) -> Callable[[AnyCallableAnyArgs], Return]
    """
    Decorator to copy the docstring from one callable to another.

    .. code-block:: python

        copy_doc(self.copy_func)(self.func)

        @copy_doc(func)
        def copy_func(self): pass
    """
    def wrapper(func):
        # type: (AnyCallableAnyArgs) -> AnyCallableAnyArgs
        func.__doc__ = copy_func.__doc__
        return func
    return wrapper
