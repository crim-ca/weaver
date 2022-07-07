import difflib
import errno
import functools
import importlib.util
import inspect
import json
import logging
import os
import posixpath
import re
import shutil
import sys
import tempfile
import time
import warnings
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, overload
from distutils.version import LooseVersion
from urllib.parse import ParseResult, unquote, urlparse, urlunsplit

import boto3
import colander
import pytz
import requests
import yaml
from beaker.cache import cache_region, region_invalidate
from beaker.exceptions import BeakerException
from celery.app import Celery
from jsonschema.validators import RefResolver as JsonSchemaRefResolver
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
from requests import HTTPError as RequestsHTTPError, Response
from requests.structures import CaseInsensitiveDict
from requests_file import FileAdapter
from urlmatch import urlmatch
from webob.headers import EnvironHeaders, ResponseHeaders
from werkzeug.wrappers import Request as WerkzeugRequest
from yaml.scanner import ScannerError

from weaver.base import Constants
from weaver.execute import ExecuteControlOption, ExecuteMode
from weaver.formats import ContentType, get_content_type
from weaver.status import map_status
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.xml_util import XML

if TYPE_CHECKING:
    from types import FrameType
    from typing import (
        Any,
        Callable,
        Dict,
        List,
        Iterable,
        MutableMapping,
        NoReturn,
        Optional,
        Type,
        Tuple,
        Union
    )
    from typing_extensions import TypeGuard

    from weaver.execute import AnyExecuteControlOption, AnyExecuteMode
    from weaver.status import Status
    from weaver.typedefs import (
        AnyKey,
        AnyHeadersContainer,
        AnySettingsContainer,
        AnyRegistryContainer,
        AnyRequestMethod,
        AnyResponseType,
        AnyUUID,
        AnyValueType,
        AnyVersion,
        HeadersType,
        JSON,
        KVP,
        KVP_Item,
        Literal,
        OpenAPISchema,
        Number,
        SettingsType
    )

LOGGER = logging.getLogger(__name__)

SUPPORTED_FILE_SCHEMES = frozenset([
    "file",
    "http",
    "https",
    "s3",
    "vault"
])

# note: word characters also match unicode in this case
FILE_NAME_QUOTE_PATTERN = re.compile(r"^\"?([\w\-.]+\.\w+)\"?$")  # extension required, permissive extra quotes
FILE_NAME_LOOSE_PATTERN = re.compile(r"^[\w\-.]+$")  # no extension required


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


NUMBER_PATTERN = re.compile(r"^(?P<number>[+-]?[0-9]+[.]?[0-9]*([e][+-]?[0-9]+)?)\s*(?P<unit>.*)$")
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
    # type: (MutableMapping, Optional[str], bool, bool) -> Optional[str]
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
    # type: (MutableMapping, Any, bool, bool, bool, bool) -> AnyValueType
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


def get_any_message(info):
    # type: (JSON) -> str
    """
    Retrieves a dictionary 'value'-like key using multiple common variations [message].

    :param info: dictionary that potentially contains a 'message'-like key.
    :returns: value of the matched 'message'-like key or an empty string if not found.
    """
    return info.get("message", "").strip()


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
               ):                   # type: (...) -> Optional[Union[str, List[str]]]
    """
    Find the specified header within a header container.

    Retrieves :paramref:`header_name` by fuzzy match (independently of upper/lower-case and underscore/dash) from
    various framework implementations of *Headers*.

    :param header_name: header to find.
    :param header_container: where to look for :paramref:`header_name`.
    :param default: returned value if :paramref:`header_container` is invalid or :paramref:`header_name` is not found.
    :param pop: remove the matched header(s) by name from the input container.
    """
    def fuzzy_name(_name):
        # type: (str) -> str
        return _name.lower().replace("-", "_")

    if header_container is None:
        return default
    headers = header_container
    if isinstance(headers, (ResponseHeaders, EnvironHeaders, CaseInsensitiveDict)):
        headers = dict(headers)
    if isinstance(headers, dict):
        headers = header_container.items()
    header_name = fuzzy_name(header_name)
    for i, (h, v) in enumerate(list(headers)):
        if fuzzy_name(h) == header_name:
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
            return dict(Cookie=get_header(cookie_header_name, header_container))
        return {}
    except KeyError:  # No cookie
        return {}


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

    All values are normalized under a list, whether their have an unique or multi-value definition.
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


def parse_prefer_header_execute_mode(
    header_container,       # type: AnyHeadersContainer
    supported_modes=None,   # type: Optional[List[AnyExecuteControlOption]]
    wait_max=10,            # type: int
):                          # type: (...) -> Tuple[AnyExecuteMode, Optional[int], HeadersType]
    """
    Obtain execution preference if provided in request headers.

    .. seealso::
        - :term:`OGC API - Processes`: Core, Execution mode <
          https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execution_mode>`_.
          This defines all conditions how to handle ``Prefer`` against applicable :term:`Process` description.
        - :rfc:`7240#section-4.1` HTTP Prefer header ``respond-async``

    .. seealso::
        If ``Prefer`` format is valid, but server decides it cannot be respected, it can be transparently ignored
        (:rfc:`7240#section-2`). The server must respond with ``Preference-Applied`` indicating preserved preferences
        it decided to respect.

    :param header_container: Request headers to retrieve preference, if any available.
    :param supported_modes:
        Execute modes that are permitted for the operation that received the ``Prefer`` header.
        Resolved mode will respect this constrain following specification requirements of :term:`OGC API - Processes`.
    :param wait_max:
        Maximum wait time enforced by the server. If requested wait time is greater, ``wait`` preference will not be
        applied and will fallback to asynchronous response.
    :return:
        Tuple of resolved execution mode, wait time if specified, and header of applied preferences if possible.
        Maximum wait time indicates duration until synchronous response should fallback to asynchronous response.
    :raises HTTPBadRequest: If contents of ``Prefer`` are not valid.
    """

    prefer = get_header("prefer", header_container)
    relevant_modes = {ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC}
    supported_modes = list(set(supported_modes or []).intersection(relevant_modes))

    if not prefer:
        # /req/core/process-execute-default-execution-mode (A & B)
        if not supported_modes:
            return ExecuteMode.ASYNC, None, {}  # Weaver's default
        if len(supported_modes) == 1:
            mode = ExecuteMode.ASYNC if supported_modes[0] == ExecuteControlOption.ASYNC else ExecuteMode.SYNC
            wait = None if mode == ExecuteMode.ASYNC else wait_max
            return mode, wait, {}
        # /req/core/process-execute-default-execution-mode (C)
        return ExecuteMode.SYNC, wait_max, {}

    params = parse_kvp(prefer, pair_sep=",", multi_value_sep=None)
    wait = wait_max
    if "wait" in params:
        try:
            if not len(params["wait"]) == 1:
                raise ValueError("Too many values.")
            wait = params["wait"][0]
            if not str.isnumeric(wait) or "." in wait or wait.startswith("-"):
                raise ValueError("Invalid integer for 'wait' in seconds.")
            wait = int(wait)
        except (TypeError, ValueError) as exc:
            raise HTTPBadRequest(json={
                "code": "InvalidParameterValue",
                "description": "HTTP Prefer header contains invalid 'wait' definition.",
                "error": type(exc).__name__,
                "cause": str(exc),
                "value": str(params["wait"]),
            })

    if wait > wait_max:
        LOGGER.info("Requested Prefer wait header too large (%ss > %ss), revert to async execution.", wait, wait_max)
        return ExecuteMode.ASYNC, None, {}

    auto = ExecuteMode.ASYNC if "respond-async" in params else ExecuteMode.SYNC
    applied_preferences = []
    # /req/core/process-execute-auto-execution-mode (A & B)
    if len(supported_modes) == 1:
        # supported mode is enforced, only indicate if it matches preferences to honour them
        # otherwise, server is allowed to discard preference since it cannot be honoured
        mode = ExecuteMode.ASYNC if supported_modes[0] == ExecuteControlOption.ASYNC else ExecuteMode.SYNC
        wait = None if mode == ExecuteMode.ASYNC else wait_max
        if auto == mode:
            if auto == ExecuteMode.ASYNC:
                applied_preferences.append("respond-async")
            if wait:
                applied_preferences.append(f"wait={wait}")
        # /rec/core/process-execute-honor-prefer (A: async & B: wait)
        # https://datatracker.ietf.org/doc/html/rfc7240#section-3
        applied = {}
        if applied_preferences:
            applied = {"Preference-Applied": ", ".join(applied_preferences)}
        return mode, wait, applied

    # Weaver's default, at server's discretion when both mode are supported
    # /req/core/process-execute-auto-execution-mode (C)
    if len(supported_modes) == 2:
        if auto == ExecuteMode.ASYNC:
            return ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"}
        if wait:
            return ExecuteMode.SYNC, wait, {"Preference-Applied": f"wait={wait}"}
    return ExecuteMode.ASYNC, None, {}


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
    # type: (Optional[str]) -> TypeGuard[str]
    try:
        return bool(urlparse(url).scheme)
    except Exception:  # noqa: W0703 # nosec: B110
        return False


class VersionLevel(Constants):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class VersionFormat(Constants):
    OBJECT = "object"  # LooseVersion
    STRING = "string"  # "x.y.z"
    PARTS = "parts"    # tuple/list


@overload
def as_version_major_minor_patch(version, version_format):
    # type: (AnyVersion, Literal[VersionFormat.OBJECT]) -> LooseVersion
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
    Generates a ``MAJOR.MINOR.PATCH`` version with padded with zeros for any missing parts.
    """
    if isinstance(version, (str, float, int)):
        ver_parts = list(LooseVersion(str(version)).version)
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
        return LooseVersion(ver_str)
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
    except Exception:  # noqa: W0703 # nosec: B110
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


def get_file_headers(path, download_headers=False, content_headers=False, content_type=None):
    # type: (str, bool, bool, Optional[str]) -> HeadersType
    """
    Obtain headers applicable for the provided file.

    :param path: File to describe.
    :param download_headers: If enabled, add the attachment filename for downloading the file.
    :param content_headers: If enabled, add ``Content-`` prefixed headers.
    :param content_type: Explicit ``Content-Type`` to provide. Otherwise, use default guessed by file system.
    :return: Headers for the file.
    """
    stat = os.stat(path)
    headers = {}
    if content_headers:
        c_type, c_enc = guess_file_contents(path)
        if c_type == ContentType.APP_OCTET_STREAM:  # default
            f_ext = os.path.splitext(path)[-1]
            c_type = get_content_type(f_ext, charset="UTF-8", default=ContentType.APP_OCTET_STREAM)
        headers.update({
            "Content-Type": content_type or c_type,
            "Content-Encoding": c_enc or "",
            "Content-Length": str(stat.st_size)
        })
        if download_headers:
            headers.update({
                "Content-Disposition": f"attachment; filename=\"{os.path.basename(path)}\"",
            })
    f_modified = get_file_header_datetime(datetime.fromtimestamp(stat.st_mtime))
    f_created = get_file_header_datetime(datetime.fromtimestamp(stat.st_ctime))
    headers.update({
        "Date": f_created,
        "Last-Modified": f_modified
    })
    return headers


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
        raise TypeError(f"Cannot convert item to bytes: {type(string)!r}")
    if isinstance(string, bytes):
        return string
    return string.encode("UTF-8")


def bytes2str(string):
    # type: (Union[str, bytes]) -> str
    """
    Obtains the unicode representation of the string.
    """
    if not isinstance(string, (str, bytes)):
        raise TypeError(f"Cannot convert item to unicode: {type(string)!r}")
    if not isinstance(string, bytes):
        return string
    return string.decode("UTF-8")


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
        # type: (Any) -> str
        if isinstance(_v, (list, set, tuple)):
            return sep.join([str(_) for _ in _v])
        return str(_v)

    kvp = [f"{k}={_value(v)}" for k, v in params.items()]
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


def get_caller_name(skip=2, base_class=False):
    # type: (int, bool) -> str
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

    def stack_(frame):  # type: (FrameType) -> List[FrameType]
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
    except (BeakerException, KeyError):  # ignore if cache region not yet generated
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
        # type: (*Any, **Any) -> Any
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
    # type: (str, str, Dict[str, AnyValueType]) -> Response
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
    # type: (str, str, Dict[str, AnyValueType]) -> Response
    """
    Cached-enabled request operation employed by :func:`request_extra`.
    """
    return _request_call(method, url, kwargs)


@retry_on_cache_error
def request_extra(method,                       # type: AnyRequestMethod
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
    request_kwargs = request_options  # update ref to ensure following modifications consider all parameters
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
    # remove leftover options unknown to requests method in case of multiple entries
    # see 'requests.request' detailed signature for applicable args
    known_req_opts = set(inspect.signature(requests.Session.request).parameters)
    known_req_opts -= {"url", "method"}  # add as unknown to always remove them since they are passed by arguments
    for req_opt in set(request_kwargs) - known_req_opts:
        request_kwargs.pop(req_opt)
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


def download_file_http(file_reference, file_outdir, settings=None, **request_kwargs):
    # type: (str, str, Optional[AnySettingsContainer], **Any) -> str
    """
    Downloads the file referenced by an HTTP URL location.

    Respects :rfc:`2183`, :rfc:`5987` and :rfc:`6266` regarding ``Content-Disposition`` header handling to resolve
    any preferred file name. This value is employed if it fulfill validation criteria. Otherwise, the name is extracted
    from the last part of the URL path.

    :param file_reference: HTTP URL where the file is hosted.
    :param file_outdir: Output local directory path under which to place the downloaded file.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param request_kwargs: Additional keywords to forward to request call (if needed).
    :return: Path of the local copy of the fetched file.
    :raises HTTPException: applicable HTTP-based exception if any unrecoverable problem occurred during fetch request.
    :raises ValueError: when resulting file name value is considered invalid.
    """

    LOGGER.debug("Fetch file resolved as remote URL reference.")
    request_kwargs.pop("stream", None)
    resp = request_extra("get", file_reference, stream=True, retries=3, settings=settings, **request_kwargs)
    if resp.status_code >= 400:
        # pragma: no cover
        # use method since response object does not derive from Exception, therefore cannot be raised directly
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        raise resp

    # resolve preferred file name or default to last fragment of request path
    file_name = None
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
        try:
            file_name_maybe = (file_name_star or file_name_param or "").split("/")[-1].strip().replace(" ", "_")
            file_name_maybe = FILE_NAME_QUOTE_PATTERN.match(file_name_maybe)[1]
            if file_name_maybe and (3 < len(file_name_maybe) < 256):
                file_name = file_name_maybe
                LOGGER.debug("Using validated Content-Disposition preferred file name: [%s]", file_name)
        except (IndexError, TypeError):
            LOGGER.debug("Discarding Content-Disposition preferred file name due to failed validation.")

    if not file_name:
        file_name = urlparse(file_reference).path.split("/")[-1]
        LOGGER.debug("Using default file name from URL path fragment: [%s]", file_name)

    if not FILE_NAME_LOOSE_PATTERN.match(file_name):
        raise ValueError(f"Invalid file name [{file_name!s}] resolved from URL [{file_reference}]. Aborting download.")

    file_path = os.path.join(file_outdir, file_name)
    with open(file_path, "wb") as file:  # pylint: disable=W1514
        # NOTE:
        #   Setting 'chunk_size=None' lets the request find a suitable size according to
        #   available memory. Without this, it defaults to 1 which is extremely slow.
        for chunk in resp.iter_content(chunk_size=None):
            file.write(chunk)
    return file_path


def fetch_file(file_reference, file_outdir, settings=None, link=None, move=False, **request_kwargs):
    # type: (str, str, Optional[AnySettingsContainer], Optional[bool], bool, **Any) -> str
    """
    Fetches a file from local path, AWS-S3 bucket or remote URL, and dumps it's content to the output directory.

    The output directory is expected to exist prior to this function call.
    The file reference scheme (protocol) determines from where to fetch the content.
    Output file name and extension will be the same as the original (after link resolution if applicable).
    Requests will consider ``weaver.request_options`` when using ``http(s)://`` scheme.

    :param file_reference:
        Local filesystem path (optionally prefixed with ``file://``), ``s3://`` bucket location or ``http(s)://``
        remote URL file reference. Reference ``https://s3.[...]`` are also considered as ``s3://``.
    :param file_outdir: Output local directory path under which to place the fetched file.
    :param settings: Additional request-related settings from the application configuration (notably request-options).
    :param link:
        If ``True``, force generation of a symbolic link instead of hard copy, regardless if source is a file or link.
        If ``False``, force hard copy of the file to destination, regardless if source is a file or link.
        If ``None`` (default), resolve automatically as follows.
        When the source is a symbolic link itself, the destination will also be a link.
        When the source is a direct file reference, the destination will be a hard copy of the file.
        Only applicable when the file reference is local.
    :param move:
        Move local file to the output directory instead of copying or linking it.
        No effect if the output directory already contains the local file.
        No effect if download must occurs for remote file.
    :param request_kwargs: Additional keywords to forward to request call (if needed).
    :return: Path of the local copy of the fetched file.
    :raises HTTPException: applicable HTTP-based exception if any occurred during the operation.
    :raises ValueError: when the reference scheme cannot be identified.
    """
    file_href = file_reference
    file_name = os.path.basename(os.path.realpath(file_reference))  # resolve any different name to use the original
    file_path = os.path.join(file_outdir, file_name)
    if file_reference.startswith("file://"):
        file_reference = file_reference[7:]
    LOGGER.debug("Fetching file reference: [%s]", file_href)
    if os.path.isfile(file_reference):
        LOGGER.debug("Fetch file resolved as local reference.")
        if move and os.path.isfile(file_path):
            LOGGER.debug("Reference [%s] cannot be moved to path [%s] (already exists)", file_href, file_path)
            raise OSError("Cannot move file, already in output directory!")
        if move:
            shutil.move(os.path.realpath(file_reference), file_outdir)
        # NOTE:
        #   If file is available locally and referenced as a system link, disabling 'follow_symlinks'
        #   creates a copy of the symlink instead of an extra hard-copy of the linked file.
        elif os.path.islink(file_reference) and not os.path.isfile(file_path):
            if link is True:
                os.symlink(os.readlink(file_reference), file_path)
            else:
                shutil.copyfile(file_reference, file_path, follow_symlinks=link is False)
        # otherwise copy the file if not already available
        # expand directory of 'file_path' and full 'file_reference' to ensure many symlink don't result in same place
        elif not os.path.isfile(file_path) or os.path.realpath(file_path) != os.path.realpath(file_reference):
            if link is True:
                os.symlink(file_reference, file_path)
            else:
                shutil.copyfile(file_reference, file_path)
        else:
            LOGGER.debug("Fetch file as local reference has no action to take, file already exists: [%s]", file_path)
    elif file_reference.startswith("s3://"):
        LOGGER.debug("Fetch file resolved as S3 bucket reference.")
        s3 = boto3.resource("s3")
        bucket_name, file_key = file_reference[5:].split("/", 1)
        bucket = s3.Bucket(bucket_name)
        bucket.download_file(file_key, file_path)
    elif file_reference.startswith("http"):
        # pseudo-http URL referring to S3 bucket, try to redirect to above S3 handling method if applicable
        if file_reference.startswith("https://s3."):
            s3 = boto3.resource("s3")
            # endpoint in the form: "https://s3.[region-name.]amazonaws.com/<bucket>/<file-key>"
            if not file_reference.startswith(s3.meta.endpoint_url):
                LOGGER.warning("Detected HTTP file reference to AWS S3 bucket that mismatches server configuration. "
                               "Will consider it as plain HTTP with read access.")
            else:
                file_reference_s3 = file_reference.replace(s3.meta.endpoint_url, "")
                file_ref_updated = f"s3://{file_reference_s3}"
                LOGGER.debug("Adjusting file reference to S3 shorthand for further parsing:\n"
                             "  Initial: [%s]\n"
                             "  Updated: [%s]", file_reference, file_ref_updated)
                return fetch_file(file_ref_updated, file_outdir, settings=settings, **request_kwargs)
        file_path = download_file_http(file_reference, file_outdir, settings=settings, **request_kwargs)
    else:
        scheme = file_reference.split("://")
        scheme = "<none>" if len(scheme) < 2 else scheme[0]
        raise ValueError(
            f"Unresolved location and/or fetch file scheme: '{scheme!s}', "
            f"supported: {list(SUPPORTED_FILE_SCHEMES)}, reference: [{file_reference!s}]"
        )
    LOGGER.debug("Fetch file resolved:\n"
                 "  Reference: [%s]\n"
                 "  File Path: [%s]", file_href, file_path)
    return file_path


def load_file(file_path, text=False):
    # type: (str, bool) -> Union[JSON, str]
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
            cwl_resp = request_extra("get", file_path, headers=headers, settings=settings)
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


def generate_diff(val, ref, val_name="Test", ref_name="Reference"):
    # type: (Any, Any, str, str) -> str
    """
    Generates a line-by-line diff result of the test value against the reference value.

    Attempts to parse the contents as JSON to provide better diff of matched/sorted lines, and falls back to plain
    line-based string representations otherwise.

    :param val: Test input value.
    :param ref: Reference input value.
    :param val_name: Name to apply in diff for test input value.
    :param ref_name: Name to apply in diff for reference input value.
    :returns: Formatted multiline diff,
    """
    try:
        val = json.dumps(val, sort_keys=True, indent=2, ensure_ascii=False)
    except Exception:  # noqa
        val = str(val)
    try:
        ref = json.dumps(ref, sort_keys=True, indent=2, ensure_ascii=False)
    except Exception:  # noqa
        ref = str(ref)
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
    Parses a numeric value accompanied with a unit to generate the unit-less value without prefix factor.

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
