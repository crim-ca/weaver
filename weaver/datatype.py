"""
Definitions of types used by tokens.
"""
import abc
import copy
import enum
import inspect
import json
import re
import traceback
import uuid
import warnings
from datetime import datetime, timedelta
from logging import ERROR, INFO, Logger, getLevelName, getLogger
from secrets import compare_digest, token_hex
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import colander
import pyramid.httpexceptions
import requests.exceptions
from dateutil.parser import parse as dt_parse
from docker.auth import decode_auth
from owslib.util import ServiceException as OWSServiceException
from owslib.wps import Process as ProcessOWS, WPSException
from pywps import Process as ProcessWPS

from weaver import xml_util
from weaver.exceptions import ProcessInstanceError, ServiceParsingError
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_CONTROL_OPTIONS,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_OPTIONS,
    EXECUTE_MODE_SYNC,
    EXECUTE_TRANSMISSION_MODE_OPTIONS,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import ACCEPT_LANGUAGE_EN_CA, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_PLAIN
from weaver.processes.constants import PROCESS_SCHEMA_OGC, PROCESS_SCHEMA_OLD
from weaver.processes.convert import get_field, null, ows2json, wps2json_io
from weaver.processes.types import (
    PROCESS_APPLICATION,
    PROCESS_BUILTIN,
    PROCESS_TEST,
    PROCESS_WORKFLOW,
    PROCESS_WPS_LOCAL,
    PROCESS_WPS_REMOTE,
    PROCESS_WPS_TYPES
)
from weaver.status import (
    JOB_STATUS_CATEGORIES,
    JOB_STATUS_CATEGORY_FINISHED,
    JOB_STATUS_VALUES,
    STATUS_ACCEPTED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_UNKNOWN,
    map_status
)
from weaver.utils import localize_datetime  # for backward compatibility of previously saved jobs not time-locale-aware
from weaver.utils import (
    fully_qualified_name,
    get_job_log_msg,
    get_log_date_fmt,
    get_log_fmt,
    get_settings,
    now,
    request_extra
)
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_VALUES
from weaver.warning import NonBreakingExceptionWarning
from weaver.wps.utils import get_wps_client, get_wps_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Union

    from owslib.wps import WebProcessingService

    from weaver.typedefs import AnyProcess, AnySettingsContainer, AnyUUID, Number, CWL, JSON

    AnyParams = Dict[str, Any]
    AnyAuthentication = Union["Authentication", "DockerAuthentication"]

LOGGER = getLogger(__name__)


class DictBase(dict):
    """
    Dictionary with extended attributes auto-``getter``/``setter`` for convenience.

    Explicitly overridden ``getter``/``setter`` attributes are called instead of ``dict``-key ``get``/``set``-item
    to ensure corresponding checks and/or value adjustments are executed before applying it to the sub-``dict``.
    """

    def __setattr__(self, item, value):
        """
        Uses an existing property setter if defined in the subclass or employs the default dictionary setter otherwise.
        """
        prop = getattr(type(self), item)
        if isinstance(prop, property) and prop.fset is not None:
            prop.fset(self, value)  # noqa
        else:
            super(DictBase, self).__setitem__(item, value)

    def __getitem__(self, item):
        """
        Uses an existing property getter if defined in the subclass or employs the default dictionary getter otherwise.
        """
        prop = getattr(type(self), item)
        if isinstance(prop, property) and prop.fget is not None:
            return prop.fget(self)  # noqa
        elif item in self:
            return getattr(self, item, None)
        else:
            raise AttributeError(f"Can't get attribute '{item}' in '{self.__name__}'.")

    def __str__(self):
        # type: () -> str
        return type(self).__name__

    def __repr__(self):
        # type: () -> str
        cls = type(self)
        repr_ = dict.__repr__(self)
        return "{0}.{1} ({2})".format(cls.__module__, cls.__name__, repr_)

    def dict(self):
        # type: () -> AnyParams
        """
        Generate a dictionary representation of the object, but with inplace resolution of attributes as applicable.
        """
        # update any entries by key with their attribute
        _dict = {key: getattr(self, key, dict.__getitem__(self, key)) for key, val in self.items()}
        # then, ensure any missing key gets added if a getter property exists for it
        props = {prop[0] for prop in inspect.getmembers(self) if not prop[0].startswith("_") and prop[0] not in _dict}
        for key in props:
            prop = getattr(type(self), key)
            if isinstance(prop, property) and prop.fget is not None:
                _dict[key] = prop.fget(self)  # noqa
        return _dict


class AutoBase(DictBase):
    """
    Base that automatically converts literal class members to properties also accessible by dictionary keys.

    .. code-block:: python

        class Data(AutoBase):
            field = 1
            other = None

        d = Data()
        d.other         # returns None
        d.other = 2     # other is modified
        d.other         # returns 2
        dict(d)         # returns {'field': 1, 'other': 2}
        d.field         # returns 1
        d["field"]      # also 1 !
    """
    def __new__(cls, *args, **kwargs):
        extra_props = set(dir(cls)) - set(dir(DictBase))
        auto_cls = DictBase.__new__(cls, *args, **kwargs)
        for prop in extra_props:
            prop_func = property(
                lambda self, key: dict.__getitem__(self, key),
                lambda self, key, value: dict.__setattr__(self, key, value)
            )
            default = getattr(auto_cls, prop, None)
            setattr(auto_cls, prop, prop_func)
            AutoBase.__setattr__(auto_cls, prop, default)
        return auto_cls

    def __getitem__(self, item):
        return dict.__getitem__(self, item)

    def __setattr__(self, key, value):
        # set both as object and dict reference
        DictBase.__setattr__(self, key, value)
        dict.__setattr__(self, key, value)


class Base(DictBase):
    def __str__(self):
        # type: () -> str
        return f"{type(self).__name__} <{self.id}>"

    @property
    def __name__(self):
        return fully_qualified_name(self)

    @property
    def id(self):
        raise NotImplementedError()

    @property
    def uuid(self):
        return self.id

    def json(self):
        # type: () -> JSON
        """
        Obtain the JSON data representation for response body.

        .. note::
            This method implementation should validate the JSON schema against the API definition whenever
            applicable to ensure integrity between the represented data type and the expected API response.
        """
        raise NotImplementedError("Method 'json' must be defined for JSON request item representation.")

    def params(self):
        # type: () -> AnyParams
        """
        Obtain the internal data representation for storage.

        .. note::
            This method implementation should provide a JSON-serializable definition of all fields representing
            the object to store.
        """
        raise NotImplementedError("Method 'params' must be defined for storage item representation.")


class Service(Base):
    """
    Dictionary that contains OWS services.

    It always has ``url`` key.
    """

    def __init__(self, *args, **kwargs):
        super(Service, self).__init__(*args, **kwargs)
        if "name" not in self:
            raise TypeError("Service 'name' is required")
        if "url" not in self:
            raise TypeError("Service 'url' is required")
        self["_wps"] = None

    @property
    def id(self):
        return self.name

    @property
    def url(self):
        """
        Service URL.
        """
        return dict.__getitem__(self, "url")

    @property
    def name(self):
        """
        Service name.
        """
        return dict.__getitem__(self, "name")

    @property
    def type(self):
        """
        Service type.
        """
        return self.get("type", PROCESS_WPS_REMOTE)

    @property
    def public(self):
        """
        Flag if service has public access.
        """
        # TODO: public access can be set via auth parameter.
        return self.get("public", False)

    @property
    def auth(self):
        """
        Authentication method: public, token, cert.
        """
        return self.get("auth", "token")

    def json(self):
        # type: () -> JSON
        # TODO: apply swagger type deserialize schema check if returned in a response
        return self.params()

    def params(self):
        # type: () -> AnyParams
        return {
            "url": self.url,
            "name": self.name,
            "type": self.type,
            "public": self.public,
            "auth": self.auth
        }

    def wps(self, container=None, **kwargs):
        # type: (AnySettingsContainer, Any) -> WebProcessingService
        """
        Obtain the remote WPS service definition and metadata.

        Stores the reference locally to avoid re-fetching it needlessly for future reference.
        """
        try:
            _wps = self.get("_wps")
            if _wps is None:
                # client retrieval could also be cached if recently fetched an not yet invalidated
                self["_wps"] = _wps = get_wps_client(self.url, container=container, **kwargs)
            return _wps
        except (OWSServiceException, xml_util.ParseError) as exc:
            msg = "Invalid XML returned by WPS [{}] at [{}] cannot be parsed.".format(self.name, self.url)
            raise ServiceParsingError(json={"description": msg, "cause": str(exc), "error": exc.__class__.__name__})

    def links(self, container, fetch=True, self_link=None):
        # type: (AnySettingsContainer, bool, Optional[str]) -> List[JSON]
        """
        Obtains the links relevant to the service :term:`Provider`.

        :param container: object that helps retrieve instance details, namely the host URL.
        :param fetch: whether to attempt retrieving more precise details from the remote provider.
        :param self_link: name of a section that represents the current link that will be returned.
        """
        if fetch:
            wps = self.wps(container=container)
            wps_lang = wps.language
            wps_url = wps.url
        else:
            wps_url = self.url
            wps_lang = ACCEPT_LANGUAGE_EN_CA  # assume, cannot validate

        wps_url = urljoin(wps_url, urlparse(wps_url).path)
        wps_url = "{}?service=WPS&request=GetCapabilities".format(wps_url)
        svc_url = "{}/providers/{}".format(get_wps_restapi_base_url(container), self.name)
        proc_url = "{}/processes".format(svc_url)
        links = [
            {
                "rel": "service-desc",
                "title": "Service description (GetCapabilities).",
                "href": wps_url,
                "hreflang": wps_lang,
                "type": CONTENT_TYPE_APP_XML,
            },
            {
                "rel": "service",
                "title": "Service definition.",
                "href": svc_url,
                "hreflang": ACCEPT_LANGUAGE_EN_CA,
                "type": CONTENT_TYPE_APP_JSON,
            },
            {
                "rel": self_link or "self",
                "title": "Provider definition.",
                "href": svc_url,
                "hreflang": ACCEPT_LANGUAGE_EN_CA,
                "type": CONTENT_TYPE_APP_JSON,
            },
            {
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/processes",
                "title": "Listing of processes provided by this service.",
                "href": proc_url,
                "hreflang": ACCEPT_LANGUAGE_EN_CA,
                "type": CONTENT_TYPE_APP_JSON,
            },
        ]
        return links

    def metadata(self, container):
        # type: (AnySettingsContainer) -> List[JSON]
        """
        Obtains the metadata relevant to the service provider.
        """
        wps = self.wps(container=container)
        wps_lang = wps.language
        # FIXME: add more metadata retrieved from 'wps.identification' and 'wps.provider.contact' (?)
        #        if so, should be included only in "long description", while "summary" only returns below info
        meta = [
            {
                "type": "provider-name",
                "title": "Provider Name",
                "role": "http://www.opengis.net/eoc/applicationContext/providerMetadata",
                "value": wps.provider.name,
                "lang": wps_lang
            },
            {
                "type": "provider-site",
                "title": "Provider Name",
                "role": "http://www.opengis.net/eoc/applicationContext/providerMetadata",
                "value": wps.provider.url,
                "lang": wps_lang
            },
            {
                "type": "contact-name",
                "title": "Contact Name",
                "role": "http://www.opengis.net/eoc/applicationContext/providerMetadata",
                "value": wps.provider.contact.name,
                "lang": wps_lang
            }
        ]
        return meta

    def keywords(self, container=None):
        # type: (AnySettingsContainer) -> List[str]
        """
        Obtains the keywords relevant to the service provider.
        """
        wps = self.wps(container=container)
        return wps.identification.keywords

    def summary(self, container, fetch=True, ignore=False):
        # type: (AnySettingsContainer, bool, bool) -> Optional[JSON]
        """
        Obtain the summary information from the provider service.

        When metadata fetching is disabled, the generated summary will contain only information available locally.

        :param container: employed to retrieve application settings.
        :param fetch: indicates whether metadata should be fetched from remote.
        :param ignore: indicates if failing metadata retrieval/parsing should be silently discarded or raised.
        :return: generated summary information.
        """
        try:
            # FIXME: not implemented (https://github.com/crim-ca/weaver/issues/130)
            if self.type.lower() not in PROCESS_WPS_TYPES:
                return None
            # basic information always available (local)
            data = {
                "id": self.name,
                "url": self.url,  # remote URL (bw-compat, also in links)
                "type": PROCESS_WPS_REMOTE,
                "public": self.public,
                "links": self.links(container, fetch=fetch),
            }
            # retrieve more metadata from remote if possible and requested
            if fetch:
                wps = self.wps(container)
                data.update({
                    "title": getattr(wps.identification, "title", None),
                    "description": getattr(wps.identification, "abstract", None),
                    "keywords": self.keywords(container),
                    "metadata": self.metadata(container),
                })
            return sd.ProviderSummarySchema().deserialize(data)
        except colander.Invalid as exc:
            LOGGER.error("Failed schema validation on otherwise valid parsing of provider definition.", exc_info=exc)
            raise  # invalid schema on our side, don't ignore it
        except Exception as exc:
            msg = "Exception occurred while fetching or parsing WPS [{}] at [{}]".format(self.name, self.url)
            err_msg = "{}: {!r}".format(msg, exc)
            LOGGER.debug(err_msg, exc_info=exc)
            if ignore:
                warnings.warn(err_msg, NonBreakingExceptionWarning)
                return None
            if isinstance(exc, ServiceParsingError):
                raise
            raise ServiceParsingError(json={"description": msg, "cause": str(exc), "error": fully_qualified_name(exc)})

    def processes(self, container, ignore=False):
        # type: (AnySettingsContainer, bool) -> Optional[List[Process]]
        """
        Obtains a list of remote service processes in a compatible :class:`weaver.datatype.Process` format.

        .. note::
            Remote processes won't be stored to the local process storage.

        :param container: Employed to retrieve application settings.
        :param ignore: Indicates if failing service retrieval/parsing should be silently discarded or raised.
        :raises ServiceParsingError: If parsing failed and was NOT requested to be ignored.
        :return:
            If parsing was successful, list of converted remote service processes.
            If parsing failed and was requested to be ignored, returns ``None`` to distinguish from empty process list.
        """
        # FIXME: support other providers (https://github.com/crim-ca/weaver/issues/130)
        if self.type.lower() not in PROCESS_WPS_TYPES:
            return []
        try:
            wps = self.wps(container)
        except ServiceParsingError as exc:
            err_msg = repr(exc)
            LOGGER.debug(err_msg, exc_info=exc)
            if ignore:
                warnings.warn(err_msg, NonBreakingExceptionWarning)
                return None
            raise
        settings = get_settings(container)
        return [Process.convert(process, self, settings) for process in wps.processes]

    def check_accessible(self, settings, ignore=True):
        # type: (AnySettingsContainer, bool) -> bool
        """
        Verify if the service URL is accessible.
        """
        try:
            # some WPS don't like HEAD request, so revert to normal GetCapabilities
            # otherwise use HEAD because it is faster to only 'ping' the service
            if self.type.lower() in PROCESS_WPS_TYPES:
                meth = "GET"
                url = "{}?service=WPS&request=GetCapabilities".format(self.url)
            else:
                meth = "HEAD"
                url = self.url
            # - allow 500 for services that incorrectly handle invalid request params, but at least respond
            #   (should be acceptable in this case because the 'ping' request is not necessarily well formed)
            # - allow 400/405 for bad request/method directly reported by the service for the same reasons
            # - enforce quick timeout (but don't allow 408 code) to avoid long pending connexions that never resolve
            allowed_codes = [200, 400, 405, 500]
            resp = request_extra(meth, url, timeout=2, settings=settings, allowed_codes=allowed_codes)
            return resp.status_code in allowed_codes
        except (requests.exceptions.RequestException, pyramid.httpexceptions.HTTPException) as exc:
            msg = "Exception occurred while checking service [{}] accessibility at [{}]".format(self.name, self.url)
            warnings.warn("{}: {!r}".format(msg, exc), NonBreakingExceptionWarning)
            if not ignore:
                raise ServiceParsingError(json={
                    "description": msg,
                    "cause": "Cannot validate or parse service metadata since it is not accessible.",
                    "error": exc.__class__.__name__
                })
        return False


class Job(Base):
    """
    Dictionary that contains OWS service jobs.

    It always has ``id`` and ``task_id`` keys.
    """

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super(Job, self).__init__(*args, **kwargs)
        if "task_id" not in self:
            raise TypeError(f"Parameter 'task_id' is required for '{self.__name__}' creation.")
        if not isinstance(self.id, (str, uuid.UUID)):
            raise TypeError(f"Type 'str' or 'UUID' is required for '{self.__name__}.id'")

    def _get_log_msg(self, msg=None, status=None, progress=None):
        # type: (Optional[str], Optional[str], Optional[Number]) -> str
        if not msg:
            msg = self.status_message
        status = map_status(status or self.status)
        progress = max(0, min(100, progress or self.progress))
        return get_job_log_msg(duration=self.duration_str, progress=progress, status=status, message=msg)

    @staticmethod
    def _get_err_msg(error):
        # type: (WPSException) -> str
        return "{0.text} - code={0.code} - locator={0.locator}".format(error)

    def save_log(self,
                 errors=None,       # type: Optional[Union[str, Exception, WPSException, List[WPSException]]]
                 logger=None,       # type: Optional[Logger]
                 message=None,      # type: Optional[str]
                 level=INFO,        # type: int
                 status=None,       # type: Optional[str]
                 progress=None,     # type: Optional[Number]
                 ):                 # type: (...) -> None
        """
        Logs the specified error and/or message, and adds the log entry to the complete job log.

        For each new log entry, additional :class:`Job` properties are added according to :meth:`Job._get_log_msg`
        and the format defined by :func:`get_job_log_msg`.

        :param errors:
            An error message or a list of WPS exceptions from which to log and save generated message stack.
        :param logger:
            An additional :class:`Logger` for which to propagate logged messages on top saving them to the job.
        :param message:
            Explicit string to be logged, otherwise use the current :py:attr:`Job.status_message` is used.
        :param level:
            Logging level to apply to the logged ``message``. This parameter is ignored if ``errors`` are logged.
        :param status:
            Override status applied in the logged message entry, but does not set it to the job object.
            Uses the current :attr:`Job.status` value if not specified. Must be one of :mod:`Weaver.status` values.
        :param progress:
            Override progress applied in the logged message entry, but does not set it to the job object.
            Uses the current :attr:`Job.progress` value if not specified.

        .. note::
            The job object is updated with the log but still requires to be pushed to database to actually persist it.
        """
        if isinstance(errors, WPSException):
            errors = [errors]
        elif isinstance(errors, Exception):
            errors = str(errors)
        if isinstance(errors, str):
            log_msg = [(ERROR, self._get_log_msg(message, status=status, progress=progress))]
            self.exceptions.append(errors)
        elif isinstance(errors, list):
            log_msg = [
                (ERROR, self._get_log_msg(self._get_err_msg(error), status=status, progress=progress))
                for error in errors
            ]
            self.exceptions.extend([{
                "Code": error.code,
                "Locator": error.locator,
                "Text": error.text
            } for error in errors])
        else:
            log_msg = [(level, self._get_log_msg(message, status=status, progress=progress))]
        for lvl, msg in log_msg:
            fmt_msg = get_log_fmt() % dict(asctime=now().strftime(get_log_date_fmt()),
                                           levelname=getLevelName(lvl),
                                           name=self.__name__,
                                           message=msg)
            if len(self.logs) == 0 or self.logs[-1] != fmt_msg:
                self.logs.append(fmt_msg)
                if logger:
                    logger.log(lvl, msg)

    @property
    def id(self):
        # type: () -> uuid.UUID
        """
        Job UUID to retrieve the details from storage.
        """
        job_id = self.get("id")
        if not job_id:
            job_id = uuid.uuid4()
            self["id"] = job_id
        if isinstance(job_id, str):
            return uuid.UUID(job_id)
        return job_id

    @property
    def task_id(self):
        # type: () -> Optional[AnyUUID]
        """
        Reference Task UUID attributed by the ``Celery`` worker that monitors and executes this job.
        """
        task_id = self.get("task_id", None)
        try:
            # task ID can be a temporary non-UUID value
            if isinstance(task_id, str):
                return uuid.UUID(task_id)
        except ValueError:
            pass
        return task_id

    @task_id.setter
    def task_id(self, task_id):
        # type: (AnyUUID) -> None
        if not isinstance(task_id, (str, uuid.UUID)):
            raise TypeError(f"Type 'str' or 'UUID' is required for '{self.__name__}.task_id'")
        self["task_id"] = task_id

    @property
    def wps_id(self):
        # type: () -> Optional[uuid.UUID]
        """
        Reference WPS Request/Response UUID attributed by the executed ``PyWPS`` process.

        This UUID matches the status-location, log and output directory of the WPS process.
        This parameter is only available when the process is executed on this local instance.

        .. seealso::
            - :attr:`Job.request`
            - :attr:`Job.response`
        """
        wps_id = self.get("wps_id", None)
        if isinstance(wps_id, str):
            return uuid.UUID(wps_id)
        return wps_id

    @wps_id.setter
    def wps_id(self, wps_id):
        # type: (AnyUUID) -> None
        if not isinstance(wps_id, (str, uuid.UUID)):
            raise TypeError(f"Type 'str' or 'UUID' is required for '{self.__name__}.wps_id'")
        self["wps_id"] = wps_id

    @property
    def service(self):
        # type: () -> Optional[str]
        """
        Service identifier of the corresponding remote process.

        .. seealso::
            - :attr:`Service.id`
        """
        return self.get("service", None)

    @service.setter
    def service(self, service):
        # type: (Optional[str]) -> None
        if not isinstance(service, str) or service is None:
            raise TypeError(f"Type 'str' is required for '{self.__name__}.service'")
        self["service"] = service

    @property
    def process(self):
        # type: () -> Optional[str]
        """
        Process identifier of the corresponding remote process.

        .. seealso::
            - :attr:`Process.id`
        """
        return self.get("process", None)

    @process.setter
    def process(self, process):
        # type: (Optional[str]) -> None
        if not isinstance(process, str) or process is None:
            raise TypeError(f"Type 'str' is required for '{self.__name__}.process'")
        self["process"] = process

    @property
    def type(self):
        # type: () -> str
        """
        Obtain the type of the element associated to the creation of this job.

        .. seealso::
            - Defined in https://docs.ogc.org/DRAFTS/18-062.html#_response_6 (within ``StatusInfo`` schema).
            - Queried with https://docs.ogc.org/DRAFTS/18-062.html#_parameter_type
        """
        if self.service is None:
            return "process"
        return "provider"

    def _get_inputs(self):
        # type: () -> List[Optional[Dict[str, JSON]]]
        if self.get("inputs") is None:
            self["inputs"] = list()
        return dict.__getitem__(self, "inputs")

    def _set_inputs(self, inputs):
        # type: (List[Optional[Dict[str, JSON]]]) -> None
        if not isinstance(inputs, list):
            raise TypeError(f"Type 'list' is required for '{self.__name__}.inputs'")
        self["inputs"] = inputs

    # allows to correctly update list by ref using 'job.inputs.extend()'
    inputs = property(_get_inputs, _set_inputs)

    @property
    def user_id(self):
        # type: () -> Optional[str]
        return self.get("user_id", None)

    @user_id.setter
    def user_id(self, user_id):
        # type: (Optional[str]) -> None
        if not isinstance(user_id, int) or user_id is None:
            raise TypeError(f"Type 'int' is required for '{self.__name__}.user_id'")
        self["user_id"] = user_id

    @property
    def status(self):
        # type: () -> str
        return self.get("status", STATUS_UNKNOWN)

    @status.setter
    def status(self, status):
        # type: (str) -> None
        if status == STATUS_ACCEPTED and self.status == STATUS_RUNNING:
            LOGGER.debug(traceback.extract_stack())
        if not isinstance(status, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.status'")
        if status not in JOB_STATUS_VALUES:
            statuses = list(JOB_STATUS_VALUES)
            name = self.__name__
            raise ValueError(f"Status '{status}' is not valid for '{name}.status', must be one of {statuses!s}'")
        self["status"] = status

    @property
    def status_message(self):
        # type: () -> str
        return self.get("status_message", "no message")

    @status_message.setter
    def status_message(self, message):
        # type: (Optional[str]) -> None
        if message is None:
            return
        if not isinstance(message, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.status_message'")
        self["status_message"] = message

    @property
    def status_location(self):
        # type: () -> Optional[str]
        return self.get("status_location", None)

    @status_location.setter
    def status_location(self, location_url):
        # type: (Optional[str]) -> None
        if not isinstance(location_url, str) or location_url is None:
            raise TypeError(f"Type 'str' is required for '{self.__name__}.status_location'")
        self["status_location"] = location_url

    @property
    def notification_email(self):
        # type: () -> Optional[str]
        return self.get("notification_email")

    @notification_email.setter
    def notification_email(self, email):
        # type: (Optional[Union[str]]) -> None
        if not isinstance(email, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.notification_email'")
        self["notification_email"] = email

    @property
    def accept_language(self):
        # type: () -> Optional[str]
        return self.get("accept_language")

    @accept_language.setter
    def accept_language(self, language):
        # type: (Optional[Union[str]]) -> None
        if not isinstance(language, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.accept_language'")
        self["accept_language"] = language

    @property
    def execute_async(self):
        # type: () -> bool
        return self.execution_mode == EXECUTE_MODE_ASYNC

    @property
    def execute_sync(self):
        # type: () -> bool
        return self.execution_mode == EXECUTE_MODE_SYNC

    @property
    def execution_mode(self):
        # type: () -> str
        return self.get("execution_mode", EXECUTE_MODE_ASYNC)

    @execution_mode.setter
    def execution_mode(self, mode):
        # type: (str) -> None
        if not isinstance(mode, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.execution_mode'")
        if mode not in EXECUTE_MODE_OPTIONS:
            modes = list(EXECUTE_MODE_OPTIONS)
            raise ValueError(f"Invalid value for '{self.__name__}.execution_mode'. Must be one of {modes}")
        self["execution_mode"] = mode

    @property
    def is_local(self):
        # type: () -> bool
        return self.get("is_local", not self.service)

    @is_local.setter
    def is_local(self, is_local):
        # type: (bool) -> None
        if not isinstance(is_local, bool):
            raise TypeError(f"Type 'bool' is required for '{self.__name__}.is_local'")
        self["is_local"] = is_local

    @property
    def is_workflow(self):
        # type: () -> bool
        return self.get("is_workflow", False)

    @is_workflow.setter
    def is_workflow(self, is_workflow):
        # type: (bool) -> None
        if not isinstance(is_workflow, bool):
            raise TypeError(f"Type 'bool' is required for '{self.__name__}.is_workflow'")
        self["is_workflow"] = is_workflow

    @property
    def created(self):
        # type: () -> datetime
        created = self.get("created", None)
        if not created:
            self["created"] = now()
        return localize_datetime(self.get("created"))

    @property
    def started(self):
        # type: () -> Optional[datetime]
        started = self.get("started", None)
        if not started:
            return None
        return localize_datetime(started)

    @started.setter
    def started(self, started):
        # type: (datetime) -> None
        if not isinstance(started, datetime):
            raise TypeError(f"Type 'datetime' is required for '{self.__name__}.started'")
        self["started"] = started

    @property
    def finished(self):
        # type: () -> Optional[datetime]
        return self.get("finished", None)

    @property
    def is_finished(self):
        # type: () -> bool
        return self.finished is not None

    def mark_finished(self):
        # type: () -> None
        self["finished"] = now()

    @property
    def updated(self):
        # type: () -> datetime
        updated = self.get("updated")
        # backward compatibility when not already set
        if not updated:
            if self.status == map_status(STATUS_ACCEPTED):
                updated = self.created
            elif self.is_finished:
                updated = self.finished
            else:
                updated = self.started
            updated = localize_datetime(updated or now())
            self.updated = updated  # apply to remain static until saved
        return localize_datetime(updated)

    @updated.setter
    def updated(self, updated):
        # type: (datetime) -> None
        if not isinstance(updated, datetime):
            raise TypeError(f"Type 'datetime' is required for '{self.__name__}.updated'")
        self["updated"] = updated

    @property
    def duration(self):
        # type: () -> Optional[timedelta]
        if not self.started:
            return None
        final_time = self.finished or now()
        return localize_datetime(final_time) - localize_datetime(self.started)

    @property
    def duration_str(self):
        # type: () -> str
        duration = self.duration
        if duration is None:
            return "00:00:00"
        return str(duration).split(".")[0].zfill(8)  # "HH:MM:SS"

    @property
    def progress(self):
        # type: () -> Number
        return self.get("progress", 0)

    @progress.setter
    def progress(self, progress):
        # type: (Number) -> None
        if not isinstance(progress, (int, float)):
            raise TypeError(f"Number is required for '{self.__name__}.progress'")
        if progress < 0 or progress > 100:
            raise ValueError(f"Value must be in range [0,100] for '{self.__name__}.progress'")
        self["progress"] = progress

    def _get_results(self):
        # type: () -> List[Optional[Dict[str, JSON]]]
        if self.get("results") is None:
            self["results"] = list()
        return dict.__getitem__(self, "results")

    def _set_results(self, results):
        # type: (List[Optional[Dict[str, JSON]]]) -> None
        if not isinstance(results, list):
            raise TypeError(f"Type 'list' is required for '{self.__name__}.results'")
        self["results"] = results

    # allows to correctly update list by ref using 'job.results.extend()'
    results = property(_get_results, _set_results)

    def _get_exceptions(self):
        # type: () -> List[Optional[Dict[str, str]]]
        if self.get("exceptions") is None:
            self["exceptions"] = list()
        return dict.__getitem__(self, "exceptions")

    def _set_exceptions(self, exceptions):
        # type: (List[Optional[Dict[str, str]]]) -> None
        if not isinstance(exceptions, list):
            raise TypeError(f"Type 'list' is required for '{self.__name__}.exceptions'")
        self["exceptions"] = exceptions

    # allows to correctly update list by ref using 'job.exceptions.extend()'
    exceptions = property(_get_exceptions, _set_exceptions)

    def _get_logs(self):
        # type: () -> List[Dict[str, str]]
        if self.get("logs") is None:
            self["logs"] = list()
        return dict.__getitem__(self, "logs")

    def _set_logs(self, logs):
        # type: (List[Dict[str, str]]) -> None
        if not isinstance(logs, list):
            raise TypeError(f"Type 'list' is required for '{self.__name__}.logs'")
        self["logs"] = logs

    # allows to correctly update list by ref using 'job.logs.extend()'
    logs = property(_get_logs, _set_logs)

    def _get_tags(self):
        # type: () -> List[Optional[str]]
        if self.get("tags") is None:
            self["tags"] = list()
        return dict.__getitem__(self, "tags")

    def _set_tags(self, tags):
        # type: (List[Optional[str]]) -> None
        if not isinstance(tags, list):
            raise TypeError(f"Type 'list' is required for '{self.__name__}.tags'")
        self["tags"] = tags

    # allows to correctly update list by ref using 'job.tags.extend()'
    tags = property(_get_tags, _set_tags)

    @property
    def access(self):
        # type: () -> str
        """
        Job visibility access from execution.
        """
        return self.get("access", VISIBILITY_PRIVATE)

    @access.setter
    def access(self, visibility):
        # type: (str) -> None
        """
        Job visibility access from execution.
        """
        if not isinstance(visibility, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.access'")
        if visibility not in VISIBILITY_VALUES:
            raise ValueError(f"Invalid 'visibility' value specified for '{self.__name__}.access'")
        self["access"] = visibility

    @property
    def context(self):
        # type: () -> Optional[str]
        """
        Job outputs context.
        """
        return self.get("context") or None

    @context.setter
    def context(self, context):
        # type: (Optional[str]) -> None
        """
        Job outputs context.
        """
        if not (isinstance(context, str) or context is None):
            raise TypeError(f"Type 'str' or 'None' is required for '{self.__name__}.context'")
        self["context"] = context

    @property
    def request(self):
        # type: () -> Optional[str]
        """
        XML request for WPS execution submission as string (binary).
        """
        return self.get("request", None)

    @request.setter
    def request(self, request):
        # type: (Optional[str]) -> None
        """
        XML request for WPS execution submission as string (binary).
        """
        if isinstance(request, xml_util.XML):
            request = xml_util.tostring(request)
        self["request"] = request

    @property
    def response(self):
        # type: () -> Optional[str]
        """
        XML status response from WPS execution submission as string (binary).
        """
        return self.get("response", None)

    @response.setter
    def response(self, response):
        # type: (Optional[str]) -> None
        """
        XML status response from WPS execution submission as string (binary).
        """
        if isinstance(response, xml_util.XML):
            response = xml_util.tostring(response)
        self["response"] = response

    def _job_url(self, base_url=None):
        # type: (Optional[str]) -> str
        if self.service is not None:
            base_url += sd.provider_service.path.format(provider_id=self.service)
        job_path = sd.process_job_service.path.format(process_id=self.process, job_id=self.id)
        return "{base_job_url}{job_path}".format(base_job_url=base_url, job_path=job_path)

    def links(self, container=None, self_link=None):
        # type: (Optional[AnySettingsContainer], Optional[str]) -> List[JSON]
        """
        Obtains the JSON links section of the response body for a :term:`Job`.

        If :paramref:`self_link` is provided (e.g.: `"outputs"`) the link for that corresponding item will also
        be added as `self` entry to the links. It must be a recognized job link field.

        :param container: object that helps retrieve instance details, namely the host URL.
        :param self_link: name of a section that represents the current link that will be returned.
        """
        settings = get_settings(container)
        base_url = get_wps_restapi_base_url(settings)
        job_url = self._job_url(base_url)  # full URL
        job_path = "{}{}".format(base_url, sd.job_service.path.format(job_id=self.id))
        job_exec = job_url.rsplit("/", 1)[0] + "/execution"
        job_list = "{}{}".format(base_url, sd.jobs_service.path)
        job_links = [
            {"href": job_url, "rel": "status", "title": "Job status."},  # OGC
            {"href": job_url, "rel": "monitor", "title": "Job monitoring location."},  # IANA
            {"href": job_path, "rel": "alternate", "title": "Job status generic endpoint."},  # IANA
            {"href": job_list, "rel": "collection", "title": "List of submitted jobs."},  # IANA
            {"href": job_list, "rel": "http://www.opengis.net/def/rel/ogc/1.0/job-list",  # OGC
             "title": "List of submitted jobs."},
            {"href": job_exec, "rel": "http://www.opengis.net/def/rel/ogc/1.0/execute",
             "title": "New job submission endpoint for the corresponding process."},
            {"href": job_url + "/inputs", "rel": "inputs",  # unofficial
             "title": "Submitted job inputs for process execution."}
        ]
        if self.status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_FINISHED]:
            job_status = map_status(self.status)
            if job_status == STATUS_SUCCEEDED:
                job_links.extend([
                    {"href": job_url + "/outputs", "rel": "outputs",  # unofficial
                     "title": "Job outputs of successful process execution (extended outputs with metadata)."},
                    {"href": job_url + "/results", "rel": "http://www.opengis.net/def/rel/ogc/1.0/results",
                     "title": "Job results of successful process execution (direct output values mapping)."},
                ])
            else:
                job_links.append({
                    "href": job_url + "/exceptions", "rel": "http://www.opengis.net/def/rel/ogc/1.0/exceptions",
                    "title": "List of job exceptions if applicable in case of failing job."
                })
        job_links.append({
            "href": job_url + "/logs", "rel": "logs",  # unofficial
            "title": "List of collected job logs during process execution."
        })
        if self_link in ["status", "inputs", "outputs", "results", "logs", "exceptions"]:
            self_link_body = list(filter(lambda _link: _link["rel"].endswith(self_link), job_links))[-1]
            self_link_body = copy.deepcopy(self_link_body)
            # back to specific job if we are in one of its sub-endpoints
            self_link_up = {"href": job_url, "rel": "up", "title": "Job status details."}
        else:
            self_link_body = {"href": job_url, "title": "Job status."}
            # back to full list of jobs if we are already on the job itself
            self_link_up = {"href": job_list, "rel": "up", "title": "List of submitted jobs."}
        self_link_body["rel"] = "self"
        job_links.extend([self_link_body, self_link_up])
        link_meta = {"type": CONTENT_TYPE_APP_JSON, "hreflang": ACCEPT_LANGUAGE_EN_CA}
        for link in job_links:
            link.update(link_meta)
        return job_links

    def json(self, container=None, self_link=None):     # pylint: disable=W0221,arguments-differ
        # type: (Optional[AnySettingsContainer], Optional[str]) -> JSON
        """
        Obtains the JSON data representation for response body.

        .. note::
            Settings are required to update API shortcut URLs to job additional information.
            Without them, paths will not include the API host, which will not resolve to full URI.
        """
        settings = get_settings(container) if container else {}
        job_json = {
            "jobID": self.id,
            "processID": self.process,
            "providerID": self.service,
            "type": self.type,
            "status": map_status(self.status),
            "message": self.status_message,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "updated": self.updated,
            "duration": self.duration_str,
            "runningSeconds": self.duration.total_seconds() if self.duration is not None else None,
            # TODO: available fields not yet employed (https://github.com/crim-ca/weaver/issues/129)
            "nextPoll": None,
            "expirationDate": None,
            "estimatedCompletion": None,
            "percentCompleted": self.progress,
            # new name as per OGC-API, enforced integer
            # https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/statusInfo.yaml
            "progress": int(self.progress),
            "links": self.links(settings, self_link=self_link)
        }
        return sd.JobStatusInfo().deserialize(job_json)

    def params(self):
        # type: () -> AnyParams
        return {
            "id": self.id,
            "task_id": self.task_id,
            "wps_id": self.wps_id,
            "service": self.service,
            "process": self.process,
            "inputs": self.inputs,
            "user_id": self.user_id,
            "status": self.status,
            "status_message": self.status_message,
            "status_location": self.status_location,
            "execution_mode": self.execution_mode,
            "is_workflow": self.is_workflow,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "updated": self.updated,
            "progress": self.progress,
            "results": self.results,
            "exceptions": self.exceptions,
            "logs": self.logs,
            "tags": self.tags,
            "access": self.access,
            "context": self.context,
            "request": self.request,
            "response": self.response,
            "notification_email": self.notification_email,
            "accept_language": self.accept_language,
        }


class AuthenticationTypes(enum.Enum):
    DOCKER = "docker"
    VAULT = "vault"


class Authentication(Base):
    """
    Authentication details to store details required for process operations.
    """

    def __init__(self, auth_scheme, auth_token, auth_link, **kwargs):
        # type: (str, str, Optional[str], Any) -> None
        super(Authentication, self).__init__(**kwargs)
        # ensure values are provided and of valid format
        self.scheme = auth_scheme
        if auth_link:
            self.link = auth_link
        self.token = auth_token
        self.setdefault("id", uuid.uuid4())

    @property
    @abc.abstractmethod
    def type(self):
        # type: () -> AuthenticationTypes
        raise NotImplementedError

    @property
    def id(self):
        # type: () -> uuid.UUID
        _id = dict.__getitem__(self, "id")
        if isinstance(_id, str):
            return uuid.UUID(_id)
        return _id

    @property
    def link(self):
        # type: () -> Optional[str]
        return dict.get(self, "link", None)

    @link.setter
    def link(self, link):
        # type: (str) -> None
        if not isinstance(link, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.url', not '{type(link)}'.")
        self["link"] = link

    @property
    def token(self):
        # type: () -> str
        return dict.__getitem__(self, "token")

    @token.setter
    def token(self, token):
        # type: (str) -> None
        if not isinstance(token, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.token', not '{type(token)}'.")
        self["token"] = token

    @property
    def scheme(self):
        # type: () -> str
        return dict.__getitem__(self, "scheme")

    @scheme.setter
    def scheme(self, scheme):
        # type: (str) -> None
        if not isinstance(scheme, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.scheme', not '{type(scheme)}'.")
        self["scheme"] = scheme

    def json(self):
        return None  # in case it bubbles up by error, never provide it as JSON

    def params(self):
        # type: () -> AnyParams
        return {
            "id": self.id,
            "type": self.type.value,
            "link": self.link,
            "token": self.token,
            "scheme": self.scheme
        }

    @classmethod
    def from_params(cls, **params):
        # type: (Any) -> AnyAuthentication
        """
        Obtains the specialized :class:`Authentication` using loaded parameters from :meth:`params`.
        """
        for param in list(params):
            if not param.startswith("auth_"):
                params[f"auth_{param}"] = params[param]
        auth_type = params.get("auth_type")
        auth_cls = list(filter(lambda auth: auth_type == auth.type.value, [DockerAuthentication, VaultFile]))
        if not auth_cls:
            raise TypeError(f"Unknown authentication type: {auth_type!s}")
        auth_obj = auth_cls[0](**params)
        keys = list(auth_obj.params())
        for key in list(auth_obj):
            if key not in keys:
                del auth_obj[key]
        return auth_obj


class DockerAuthentication(Authentication):
    """
    Authentication associated to a :term:`Docker` image to retrieve from a private registry given by the reference link.

    .. seealso::
        :ref:`app_pkg_docker`
    """
    # note:
    #   Below regex does not match *every* possible name, but rather ones that need authentication.
    #   Public DockerHub images for example do not require authentication, and are therefore not matched.
    DOCKER_LINK_REGEX = re.compile(r"""
        (?:^(?P<uri>
            # protocol
            (?P<protocol>(?:http)s?:\/\/)?
            # registry
            (?:(?P<registry>
                (?:
                # IPv4
                (?P<reg_ipv4>(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}))
                |
                # IPv6
                (?P<reg_ipv6>(?:\[[a-f0-9:]+\]))
                |
                # domain
                (?P<reg_domain>
                    (?:[a-zA-Z](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+
                    (?:[a-zA-Z]{2,6}\.?|[a-zA-Z0-9-]{2,}\.?))
                |
                # hostname
                (?P<reg_host>([A-Za-z][A-Za-z0-9\-]*[A-Za-z0-9]))
                )
                # port
                (?P<reg_port>:\d+)?
                # path, but leaving at least one slash out for 'repo/image' part
                # the last '/' is matched in <image_ref> portion
                (?:\/?|[\/?\.](?P<reg_path>\S+(\/[\/?\.]\S)*))
            ))
            # registry is optional and not greedy, default to DockerHub
            \/)?
            # image reference
            (?P<image>
                # force 'repo/image:label'
                # disallow plain 'image:label' since remote dockers are always expected
                (?P<image_repo>[0-9a-z_-]{1,40}
                # nested project/repo parts
                (?:\/?|[\/?\.]\S+(\/[\/?\.]\S))*)
                (?:\/
                (?P<image_name>[0-9a-z_-]{1,40})
                )
                # label can be a literal or a variable, optional for 'latest'
                (?::
                (?P<label>[a-z0-9][a-z0-9._-]{1,38}[a-z0-9]|\${[A-Z][A-Z0-9_]{,38}[A-Z0-9]})
                )?
            )
        $)
    """, re.X)  # extended to ignore whitespaces and comments
    DOCKER_REGISTRY_DEFAULT_DOMAIN = "index.docker.io"
    DOCKER_REGISTRY_DEFAULT_URI = f"https://{DOCKER_REGISTRY_DEFAULT_DOMAIN}/v1/"  # DockerHub
    type = AuthenticationTypes.DOCKER

    def __init__(self, auth_scheme, auth_token, docker_image_link, **kwargs):
        # type: (str, str, str, Any) -> None
        matches = re.match(self.DOCKER_LINK_REGEX, docker_image_link)
        if not matches:
            raise ValueError(f"Invalid Docker image link does not conform to expected format: [{docker_image_link}]")
        groups = matches.groupdict()
        LOGGER.debug("Parsed Docker image/registry link:\n%s", json.dumps(groups, indent=2))
        if not groups["image"]:
            raise ValueError(f"Invalid Docker image reference does not conform to image format: {docker_image_link}")
        # special case for DockerHub, since it is default, it is often omitted, but could be partially provided
        # swap the domain by the full URI in that case because that's what is expected when doing plain 'docker login'
        registry = groups["reg_domain"]
        image = groups["image"]
        if registry in [self.DOCKER_REGISTRY_DEFAULT_DOMAIN, "", None]:
            if not registry:
                LOGGER.debug("No registry specified for Docker image, using default DockerHub registry.")
            # when "URI" fragment was detected but is not a real URI (since 'reg_domain' empty), link is invalid
            # (i.e.: there is no URI repository, so nowhere to send Auth token since not default DockerHub)
            if groups["uri"] not in [self.DOCKER_REGISTRY_DEFAULT_URI, "", None]:
                registry = groups["uri"]
                raise ValueError(f"Invalid registry specifier detected but not a valid URI: [{registry}]")
            registry = self.DOCKER_REGISTRY_DEFAULT_URI
        # otherwise, resolve the possible confusion between nested URI/paths vs nested repository/project
        elif groups["reg_path"]:
            image = groups["reg_path"] + "/" + groups["image"]
        LOGGER.debug("Resolved Docker image/registry from link: [%s, %s]", registry, image)
        self["image"] = image
        self["registry"] = registry
        super(DockerAuthentication, self).__init__(
            auth_scheme, auth_token, auth_link=docker_image_link, **kwargs
        )

    @property
    def credentials(self):
        # type: () -> JSON
        """
        Generates the credentials to submit the login operation based on the authentication token and scheme.
        """
        if self.scheme == "Basic":
            try:
                usr, pwd = decode_auth(self.token)
            # when token is invalid such as wrong encoding or missing ':', error is raised
            except ValueError:
                return {}
            return {"registry": self.registry, "username": usr, "password": pwd}  # nosec
        return {}

    @property
    def image(self):
        # type: () -> str
        """
        Obtains the image portion of the reference without repository prefix.
        """
        return dict.__getitem__(self, "image")

    @property
    def registry(self):
        # type: () -> str
        """
        Obtains the registry entry that must used for ``docker login <registry>``.
        """
        return dict.__getitem__(self, "registry")

    @property
    def docker(self):
        # type: () -> str
        """
        Obtains the full reference required when doing :term:`Docker` operations such as ``docker pull <reference>``.
        """
        return self.image if self.registry == self.DOCKER_REGISTRY_DEFAULT_URI else f"{self.registry}/{self.image}"

    @property
    def repository(self):
        # type: () -> str
        """
        Obtains the full :term:`Docker` repository reference without any tag.
        """
        return self.docker.rsplit(":", 1)[0]

    @property
    def tag(self):
        # type: () -> Optional[str]
        """
        Obtain the requested tag from the :term:`Docker` reference.
        """
        repo_tag = self.docker.rsplit(":", 1)
        if len(repo_tag) < 2:
            return None
        return repo_tag[-1]

    def params(self):
        # type: () -> AnyParams
        params = super(DockerAuthentication, self).params()
        params.update({"image": self.image, "registry": self.registry})
        return params


class VaultFile(Authentication):
    """
    Dictionary that contains :term:`Vault` file and its authentication information.
    """
    type = AuthenticationTypes.VAULT
    bytes = 32

    def __init__(self, file_name="", file_format=None, auth_token=None, **kwargs):
        # type: (str, Optional[str], Optional[str], Any) -> None
        for key in ["type", "scheme", "link", "token"]:
            kwargs.pop(f"auth_{key}", None)
            kwargs.pop(key, None)
        if not file_name:
            file_name = kwargs.pop("name", "")
        if not file_format:
            file_format = kwargs.pop("format", CONTENT_TYPE_TEXT_PLAIN)
        super(VaultFile, self).__init__(
            auth_scheme="token",
            auth_link=None,  # don't care
            auth_token=auth_token or token_hex(VaultFile.bytes),
            name=file_name,
            format=file_format,
            **kwargs
        )

    @classmethod
    def authorized(cls, file, token):
        # type: (Optional[VaultFile], Optional[str]) -> bool
        """
        Determine whether the file access is authorized.

        This method should be employed to validate access and reduce impact of timing attack analysis.
        """
        default = VaultFile("")
        access = file.token if file else default.token
        return compare_digest(str(access), str(token))

    @property
    def id(self):
        # type: () -> uuid.UUID
        """
        Vault file UUID to retrieve the details from storage.
        """
        file_id = self.get("id")
        if not file_id:
            file_id = uuid.uuid4()
            self["id"] = file_id
        if isinstance(file_id, str):
            return uuid.UUID(file_id)
        return file_id

    @property
    def name(self):
        # type: () -> str
        """
        Name to retrieve the file.
        """
        return dict.__getitem__(self, "name")

    @name.setter
    def name(self, name):
        # type: (str) -> None
        if not isinstance(name, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.name'")
        self["name"] = name

    @property
    def format(self):
        # type: () -> str
        """
        Format Media-Type of the file.
        """
        return dict.__getitem__(self, "format")

    @format.setter
    def format(self, media_type):
        # type: (str) -> None
        if not isinstance(media_type, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.format'")
        self["format"] = media_type

    @property
    def href(self):
        # type: () -> str
        """
        Obtain the vault input reference corresponding to the file.

        This corresponds to the ``href`` value to be provided when submitting an input that should be updated using
        the vault file of specified UUID and using the respective authorization token in ``X-Auth-Vault`` header.
        """
        return f"vault://{self.id!s}"

    def json(self):
        # type: () -> JSON
        body = {
            "file_id": self.id,
            "file_href": self.href,
            "access_token": self.token,
        }
        return sd.VaultFileUploadedBodySchema().deserialize(body)

    def params(self):
        # type: () -> AnyParams
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "type": self.type.value,
            "token": self.token,
            "scheme": self.scheme,
        }


class Process(Base):
    # pylint: disable=C0103,invalid-name
    """
    Dictionary that contains a process definition for db storage.

    It always has ``identifier`` (or ``id`` alias) and a ``package`` definition.
    Parameters can be accessed by key or attribute, and appropriate validators or default values will be applied.
    """

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super(Process, self).__init__(*args, **kwargs)
        # use both 'id' and 'identifier' to support any call (WPS and recurrent 'id')
        if "id" not in self and "identifier" not in self:
            raise TypeError("'id' OR 'identifier' is required")
        if "id" not in self:
            self["id"] = self.pop("identifier")
        if "package" not in self:
            raise TypeError("'package' is required")

    @property
    def id(self):
        # type: () -> str
        return dict.__getitem__(self, "id")

    @property
    def identifier(self):
        # type: () -> str
        return self.id

    @identifier.setter
    def identifier(self, value):
        # type: (str) -> None
        self["id"] = value

    @property
    def title(self):
        # type: () -> str
        return self.get("title", self.id)

    @property
    def abstract(self):
        # type: () -> str
        return self.get("abstract", "")

    @property
    def description(self):
        # OGC-API-Processes v1 field representation
        # bw-compat with existing processes that defined it as abstract
        return self.abstract or self.get("description", "")

    @property
    def keywords(self):
        # type: () -> List[str]
        keywords = self.setdefault("keywords", [])
        if self.type not in keywords:
            keywords.append(self.type)
            self["keywords"] = keywords
        return dict.__getitem__(self, "keywords")

    @property
    def metadata(self):
        # type: () -> List[str]
        return self.get("metadata", [])

    @property
    def version(self):
        # type: () -> Optional[str]
        return self.get("version")

    @property
    def inputs(self):
        # type: () -> Optional[List[Dict[str, JSON]]]
        """
        Inputs of the process following backward-compatible conversion of stored parameters.

        According to `OGC-API`, ``maxOccurs`` and ``minOccurs`` representations should be:
            - ``maxOccurs``: ``int`` or ``"unbounded"``
            - ``minOccurs``: ``int``

        And, ``mediaType`` should be in description as:
            - ``mediaType``: ``string``

        .. note::
            Because of pre-registered/deployed/retrieved remote processes, inputs are formatted in-line
            to respect valid OGC-API schema representation and apply any required correction transparently.
        """

        inputs = self.get("inputs")
        if inputs is not None:
            for input_ in inputs:
                input_formats = get_field(input_, "formats", search_variations=False, default=[])
                for fmt in input_formats:
                    mime_type = get_field(fmt, "mime_type", search_variations=True, pop_found=True)
                    if mime_type is not null:
                        fmt["mediaType"] = mime_type
                input_min = get_field(input_, "min_occurs", search_variations=True, pop_found=True, default=1)
                input_max = get_field(input_, "max_occurs", search_variations=True, pop_found=True, default=1)
                input_["minOccurs"] = int(input_min)
                input_["maxOccurs"] = int(input_max) if input_max != "unbounded" else input_max
                input_desc = get_field(input_, "abstract", search_variations=True, pop_found=True)
                if input_desc:
                    input_["description"] = input_desc
        return inputs

    @property
    def outputs(self):
        # type: () -> Optional[List[Dict[str, JSON]]]
        """
        Outputs of the process following backward-compatible conversion of stored parameters.

        According to `OGC-API`, ``mediaType`` should be in description as:
            - ``mediaType``: ``string``

        .. note::
            Because of pre-registered/deployed/retrieved remote processes, inputs are formatted in-line
            to respect valid OGC-API schema representation and apply any required correction transparently.
        """

        outputs = self.get("outputs", [])
        for output_ in outputs:
            output_formats = get_field(output_, "formats", search_variations=False, default=[])
            for fmt in output_formats:
                mime_type = get_field(fmt, "mime_type", pop_found=True, search_variations=True)
                if mime_type is not null:
                    fmt["mediaType"] = mime_type

            output_desc = get_field(output_, "abstract", search_variations=True, pop_found=True)
            if output_desc:
                output_["description"] = output_desc
        return outputs

    @property
    def jobControlOptions(self):  # noqa: N802
        # type: () -> List[str]
        jco = self.setdefault("jobControlOptions", [EXECUTE_CONTROL_OPTION_ASYNC])
        if not isinstance(jco, list):  # eg: None, bw-compat
            jco = [EXECUTE_CONTROL_OPTION_ASYNC]
        jco = [mode for mode in jco if mode in EXECUTE_CONTROL_OPTIONS]
        if len(jco) == 0:
            jco.append(EXECUTE_CONTROL_OPTION_ASYNC)
        self["jobControlOptions"] = jco
        return dict.__getitem__(self, "jobControlOptions")

    @property
    def outputTransmission(self):  # noqa: N802
        # type: () -> List[str]
        out = self.setdefault("outputTransmission", [EXECUTE_TRANSMISSION_MODE_REFERENCE])
        if not isinstance(out, list):  # eg: None, bw-compat
            out = [EXECUTE_TRANSMISSION_MODE_REFERENCE]
        out = [mode for mode in out if mode in EXECUTE_TRANSMISSION_MODE_OPTIONS]
        if len(out) == 0:
            out.append(EXECUTE_TRANSMISSION_MODE_REFERENCE)
        self["outputTransmission"] = out
        return dict.__getitem__(self, "outputTransmission")

    @property
    def processDescriptionURL(self):  # noqa: N802
        # type: () -> Optional[str]
        return self.get("processDescriptionURL")

    @property
    def processEndpointWPS1(self):  # noqa: N802
        # type: () -> Optional[str]
        return self.get("processEndpointWPS1")

    @property
    def executeEndpoint(self):  # noqa: N802
        # type: () -> Optional[str]
        return self.get("executeEndpoint")

    @property
    def owsContext(self):  # noqa: N802
        # type: () -> Optional[JSON]
        return self.get("owsContext")

    # wps, workflow, etc.
    @property
    def type(self):
        # type: () -> str
        """
        Type of process amongst :mod:`weaver.processes.types` definitions.
        """
        return self.get("type", PROCESS_APPLICATION)

    @property
    def package(self):
        # type: () -> Optional[CWL]
        """
        Package CWL definition as JSON.
        """
        pkg = self.get("package")
        return self._decode(pkg) if isinstance(pkg, dict) else pkg

    @package.setter
    def package(self, pkg):
        # type: (Optional[CWL]) -> None
        self["package"] = self._decode(pkg) if isinstance(pkg, dict) else pkg

    @property
    def payload(self):
        # type: () -> JSON
        """
        Deployment specification as JSON body.
        """
        body = self.get("payload", dict())
        return self._decode(body) if isinstance(body, dict) else body

    @payload.setter
    def payload(self, body):
        # type: (JSON) -> None
        self["payload"] = self._decode(body) if isinstance(body, dict) else dict()

    # encode(->)/decode(<-) characters that cannot be in a key during save to db
    _character_codes = [("$", "\uFF04"), (".", "\uFF0E")]

    @staticmethod
    def _recursive_replace(pkg, index_from, index_to):
        # type: (JSON, int, int) -> JSON
        new = {}
        for k in pkg:
            # find modified key with replace matches
            c_k = k
            for c in Process._character_codes:
                c_f = c[index_from]
                c_t = c[index_to]
                if c_f in k:
                    c_k = k.replace(c_f, c_t)
            # process recursive sub-items
            if isinstance(pkg[k], dict):
                pkg[k] = Process._recursive_replace(pkg[k], index_from, index_to)
            if isinstance(pkg[k], list):
                for i, pkg_i in enumerate(pkg[k]):
                    if isinstance(pkg_i, dict):
                        pkg[k][i] = Process._recursive_replace(pkg[k][i], index_from, index_to)
            # apply new key to obtained sub-items with replaced keys as needed
            new[c_k] = pkg[k]   # note: cannot use pop when using pkg keys iterator (python 3)
        return new

    @staticmethod
    def _encode(obj):
        # type: (Optional[JSON]) -> Optional[JSON]
        if obj is None:
            return None
        return Process._recursive_replace(obj, 0, 1)

    @staticmethod
    def _decode(obj):
        # type: (Optional[JSON]) -> Optional[JSON]
        if obj is None:
            return None
        return Process._recursive_replace(obj, 1, 0)

    @property
    def visibility(self):
        # type: () -> str
        return self.get("visibility", VISIBILITY_PRIVATE)

    @visibility.setter
    def visibility(self, visibility):
        # type: (str) -> None
        if not isinstance(visibility, str):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.visibility'")
        if visibility not in VISIBILITY_VALUES:
            values = list(VISIBILITY_VALUES)
            raise ValueError(
                f"Status '{visibility}' is not valid for '{self.__name__}.visibility, must be one of {values!s}'"
            )
        self["visibility"] = visibility

    @property
    def auth(self):
        # type: () -> Optional[AnyAuthentication]
        """
        Authentication token required for operations with the process.
        """
        auth = self.get("auth", None)
        if isinstance(auth, Authentication):
            return auth
        if isinstance(auth, dict):
            auth = Authentication.from_params(**auth)
            self["auth"] = auth  # store for later reference without reprocess
            return auth
        return None

    @auth.setter
    def auth(self, auth):
        # type: (Optional[AnyAuthentication]) -> None
        if auth is None:
            return
        if isinstance(auth, dict):
            auth = Authentication(**auth)
        if not isinstance(auth, Authentication):
            name = fully_qualified_name(auth)
            raise TypeError(f"Type 'Authentication' is required for '{self.__name__}.auth', not '{name}'.")
        self["auth"] = auth

    def params(self):
        # type: () -> AnyParams
        return {
            "identifier": self.identifier,
            "title": self.title,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "metadata": self.metadata,
            "version": self.version,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "jobControlOptions": self.jobControlOptions,
            "outputTransmission": self.outputTransmission,
            "processEndpointWPS1": self.processEndpointWPS1,
            "processDescriptionURL": self.processDescriptionURL,
            "executeEndpoint": self.executeEndpoint,
            "owsContext": self.owsContext,
            "type": self.type,
            "package": self._encode(self.package),
            "payload": self._encode(self.payload),
            "visibility": self.visibility,
            "auth": self.auth.params() if self.auth else None
        }

    @property
    def params_wps(self):
        # type: () -> AnyParams
        """
        Values applicable to create an instance of :class:`pywps.app.Process`.
        """
        return {
            "identifier": self.identifier,
            "title": self.title,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "metadata": self.metadata,
            "version": self.version,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "package": self.package,
            "payload": self.payload,
        }

    def dict(self):
        # type: () -> AnyParams
        data = super(Process, self).dict()
        data.pop("auth", None)  # remote preemptively just in case any deserialize fails to drop it
        return data

    def json(self):
        # type: () -> JSON
        """
        Obtains the JSON serializable complete representation of the process.
        """
        return sd.Process().deserialize(self.dict())

    def links(self, container=None):
        # type: (Optional[AnySettingsContainer]) -> JSON
        """
        Obtains the JSON links section of many response body for the :term:`Process`.

        :param container: object that helps retrieve instance details, namely the host URL.
        """
        settings = get_settings(container)
        base_url = get_wps_restapi_base_url(settings)
        if self.service:
            base_url += sd.provider_service.path.format(provider_id=self.service)
        proc_desc = base_url + sd.process_service.path.format(process_id=self.id)
        proc_list = base_url + sd.processes_service.path
        jobs_list = proc_desc + sd.jobs_service.path
        proc_exec = proc_desc + "/execution"
        links = [
            {"href": proc_desc, "rel": "self", "title": "Current process description."},
            {"href": proc_desc, "rel": "process-meta", "title": "Process definition."},
            {"href": proc_exec, "rel": "http://www.opengis.net/def/rel/ogc/1.0/execute",
             "title": "Process execution endpoint for job submission."},
            {"href": proc_list, "rel": "http://www.opengis.net/def/rel/ogc/1.0/processes",
             "title": "List of registered processes."},
            {"href": jobs_list, "rel": "http://www.opengis.net/def/rel/ogc/1.0/job-list",
             "title": "List of job executions corresponding to this process."},
            {"href": proc_list, "rel": "up", "title": "List of processes registered under the service."},
        ]
        if self.service:
            wps_base_url = self.processEndpointWPS1.split("?")[0]
            wps_get_caps = wps_base_url + "?service=WPS&request=GetCapabilities&version=1.0.0"
            wps_links = [
                {"href": base_url, "rel": "service", "title": "Provider service description."},
                {"href": base_url, "rel": "service-meta", "title": "Provider service definition."},
                {"href": wps_get_caps, "rel": "service-desc", "title": "Remote service description."},
                {"href": self.processEndpointWPS1, "rel": "http://www.opengis.net/def/rel/ogc/1.0/process-desc",
                 "title": "Remote process description."},
            ]
            for link in wps_links:
                link.setdefault("type", CONTENT_TYPE_APP_XML)
            links.extend(wps_links)
        for link in links:
            link.setdefault("type", CONTENT_TYPE_APP_JSON)
            link.setdefault("hreflang", ACCEPT_LANGUAGE_EN_CA)
        return {"links": links}

    def offering(self, schema=PROCESS_SCHEMA_OGC):
        # type: (str) -> JSON
        """
        Obtains the JSON serializable offering/description representation of the process.

        :param schema:
            One of values defined by :class:`sd.ProcessDescriptionSchemaQuery` to select which
            process description representation to generate (see each schema for details).

        .. note::
            Property name ``offering`` is employed to differentiate from the string process ``description`` field.
            The result of this JSON representation is still the ``ProcessDescription`` schema.
        """
        process = self.dict()
        links = self.links()
        # force selection of schema to avoid ambiguity
        if str(schema or PROCESS_SCHEMA_OGC).upper() == PROCESS_SCHEMA_OLD:
            # nested process fields + I/O as lists
            process.update({"process": dict(process)})
            process.update(links)
            return sd.ProcessDescriptionOLD().deserialize(process)
        # direct process + I/O as mappings
        for io_type in ["inputs", "outputs"]:
            process[io_type] = {
                get_field(io_def, "identifier", search_variations=True, pop_found=True): io_def
                for io_def in process[io_type]
            }
        process.update(links)
        return sd.ProcessDescriptionOGC().deserialize(process)

    def summary(self):
        # type: () -> JSON
        """
        Obtains the JSON serializable summary representation of the process.
        """
        return sd.ProcessSummary().deserialize(self.dict())

    @staticmethod
    def from_wps(wps_process, **extra_params):
        # type: (ProcessWPS, Any) -> Process
        """
        Converts a :mod:`pywps` Process into a :class:`weaver.datatype.Process` using provided parameters.
        """
        assert isinstance(wps_process, ProcessWPS)
        process = wps_process.json
        process_type = getattr(wps_process, "type", wps_process.identifier)
        process.update({"type": process_type, "package": None, "reference": None,
                        "inputs": [wps2json_io(i) for i in wps_process.inputs],
                        "outputs": [wps2json_io(o) for o in wps_process.outputs]})
        process.update(**extra_params)
        return Process(process)

    @staticmethod
    def from_ows(process, service, container, **kwargs):
        # type: (ProcessOWS, Service, AnySettingsContainer, Any) -> Process
        """
        Converts a :mod:`owslib.wps` Process to local storage :class:`weaver.datatype.Process`.
        """
        assert isinstance(process, ProcessOWS)
        wps_xml_url = get_wps_url(container)
        wps_api_url = get_wps_restapi_base_url(container)
        svc_name = None
        if not service or wps_api_url == service.url:
            # local weaver process, using WPS-XML endpoint
            remote_service_url = wps_xml_url
            local_provider_url = wps_api_url
            svc_provider_name = "Weaver"
        else:
            svc_name = service.get("name")  # can be a custom ID or identical to provider name
            remote_service_url = service.url
            local_provider_url = "{}/providers/{}".format(wps_api_url, svc_name)
            svc_provider_name = service.wps().provider.name
        describe_process_url = "{}/processes/{}".format(local_provider_url, process.identifier)
        execute_process_url = "{}/jobs".format(describe_process_url)
        package, info = ows2json(process, svc_name, remote_service_url, svc_provider_name)
        wps_description_url = "{}?service=WPS&request=DescribeProcess&version=1.0.0&identifier={}".format(
            remote_service_url, process.identifier
        )
        kwargs.update({  # parameters that must be enforced to find service
            "url": describe_process_url,
            "executeEndpoint": execute_process_url,
            "processEndpointWPS1": wps_description_url,
            "processDescriptionURL": describe_process_url,
            "type": PROCESS_WPS_REMOTE,
            "package": package,
            "service": svc_name
        })
        return Process(**info, **kwargs)

    @property
    def service(self):
        # type: () -> Optional[str]
        """
        Name of the parent service provider under which this process resides.

        .. seealso::
            - :meth:`Service.processes`
            - :meth:`Process.convert`
        """
        return self.get("service", None)

    @service.setter
    def service(self, service):
        # type: (Optional[str]) -> None
        if not (isinstance(service, str) or service is None):
            raise TypeError(f"Type 'str' is required for '{self.__name__}.service'")
        self["service"] = service

    @staticmethod
    def convert(process, service=None, container=None, **kwargs):
        # type: (AnyProcess, Optional[Service], Optional[AnySettingsContainer], Any) -> Process
        """
        Converts known process equivalents definitions into the formal datatype employed by Weaver.
        """
        if isinstance(process, ProcessOWS):
            return Process.from_ows(process, service, container, **kwargs)
        if isinstance(process, ProcessWPS):
            return Process.from_wps(process, **kwargs)
        if isinstance(process, dict):
            return Process(process, **kwargs)
        if isinstance(process, Process):
            return process
        raise TypeError("Unknown process type to convert: [{}]".format(type(process)))

    def wps(self):
        # type: () -> ProcessWPS
        """
        Converts this :class:`Process` to a corresponding format understood by :mod:`pywps`.
        """
        # import here to avoid circular import errors
        from weaver.processes.wps_default import HelloWPS
        from weaver.processes.wps_package import WpsPackage
        from weaver.processes.wps_testing import WpsTestProcess
        process_map = {
            HelloWPS.identifier: HelloWPS,
            PROCESS_TEST: WpsTestProcess,
            PROCESS_APPLICATION: WpsPackage,    # single CWL package
            PROCESS_BUILTIN: WpsPackage,        # local scripts
            PROCESS_WPS_REMOTE: WpsPackage,     # remote WPS
            PROCESS_WORKFLOW: WpsPackage,       # chaining of CWL packages
        }

        process_key = self.type
        if self.type == PROCESS_WPS_LOCAL:
            process_key = self.identifier
        if process_key not in process_map:
            ProcessInstanceError("Unknown process '{}' in mapping.".format(process_key))
        return process_map[process_key](**self.params_wps)


class Quote(Base):
    """
    Dictionary that contains quote information.

    It always has ``id`` and ``process`` keys.
    """
    # pylint: disable=C0103,invalid-name

    def __init__(self, *args, **kwargs):
        super(Quote, self).__init__(*args, **kwargs)
        if "process" not in self:
            raise TypeError("Field 'Quote.process' is required")
        if not isinstance(self.get("process"), str):
            raise ValueError("Field 'Quote.process' must be a string.")
        if "user" not in self:
            raise TypeError("Field 'Quote.user' is required")
        if not isinstance(self.get("user"), str):
            raise ValueError("Field 'Quote.user' must be a string.")
        if "price" not in self:
            raise TypeError("Field 'Quote.price' is required")
        if not isinstance(self.get("price"), float):
            raise ValueError("Field 'Quote.price' must be a float number.")
        if "currency" not in self:
            raise TypeError("Field 'Quote.currency' is required")
        if not isinstance(self.get("currency"), str) or len(self.get("currency")) != 3:
            raise ValueError("Field 'Quote.currency' must be an ISO-4217 currency string code.")
        if "created" not in self:
            self["created"] = now()
        try:
            self["created"] = dt_parse(str(self.get("created"))).isoformat()
        except ValueError:
            raise ValueError("Field 'Quote.created' must be an ISO-8601 datetime string.")
        if "expire" not in self:
            self["expire"] = now() + timedelta(days=1)
        try:
            self["expire"] = dt_parse(str(self.get("expire"))).isoformat()
        except ValueError:
            raise ValueError("Field 'Quote.expire' must be an ISO-8601 datetime string.")
        if "id" not in self:
            self["id"] = uuid.uuid4()

    @property
    def id(self):
        """
        Quote ID.
        """
        return dict.__getitem__(self, "id")

    @property
    def title(self):
        """
        Quote title.
        """
        return self.get("title")

    @property
    def description(self):
        """
        Quote description.
        """
        return self.get("description")

    @property
    def details(self):
        """
        Quote details.
        """
        return self.get("details")

    @property
    def user(self):
        """
        User ID requesting the quote.
        """
        return dict.__getitem__(self, "user")

    @property
    def process(self):
        """
        WPS Process ID.
        """
        return dict.__getitem__(self, "process")

    @property
    def estimatedTime(self):  # noqa: N802
        """
        Process estimated time.
        """
        return self.get("estimatedTime")

    @property
    def processParameters(self):  # noqa: N802
        """
        Process execution parameters for quote.
        """
        return self.get("processParameters")

    @property
    def location(self):
        """
        WPS Process URL.
        """
        return self.get("location", "")

    @property
    def price(self):
        """
        Price of the current quote.
        """
        return self.get("price", 0.0)

    @property
    def currency(self):
        """
        Currency of the quote price.
        """
        return self.get("currency")

    @property
    def expire(self):
        """
        Quote expiration datetime.
        """
        return self.get("expire")

    @property
    def created(self):
        """
        Quote creation datetime.
        """
        return self.get("created")

    @property
    def steps(self):
        """
        Sub-quote IDs if applicable.
        """
        return self.get("steps", [])

    def params(self):
        # type: () -> AnyParams
        return {
            "id": self.id,
            "price": self.price,
            "currency": self.currency,
            "user": self.user,
            "process": self.process,
            "location": self.location,
            "steps": self.steps,
            "title": self.title,
            "description": self.description,
            "details": self.details,
            "created": self.created,
            "expire": self.expire,
            "estimatedTime": self.estimatedTime,
            "processParameters": self.processParameters,
        }

    def json(self):
        # type: () -> JSON
        return sd.QuoteSchema().deserialize(self)


class Bill(Base):
    """
    Dictionary that contains bill information.

    It always has ``id``, ``user``, ``quote`` and ``job`` keys.
    """

    def __init__(self, *args, **kwargs):
        super(Bill, self).__init__(*args, **kwargs)
        if "quote" not in self:
            raise TypeError("Field 'Bill.quote' is required")
        if not isinstance(self.get("quote"), str):
            raise ValueError("Field 'Bill.quote' must be a string.")
        if "job" not in self:
            raise TypeError("Field 'Bill.job' is required")
        if not isinstance(self.get("job"), str):
            raise ValueError("Field 'Bill.job' must be a string.")
        if "user" not in self:
            raise TypeError("Field 'Bill.user' is required")
        if not isinstance(self.get("user"), str):
            raise ValueError("Field 'Bill.user' must be a string.")
        if "price" not in self:
            raise TypeError("Field 'Bill.price' is required")
        if not isinstance(self.get("price"), float):
            raise ValueError("Field 'Bill.price' must be a float number.")
        if "currency" not in self:
            raise TypeError("Field 'Bill.currency' is required")
        if not isinstance(self.get("currency"), str) or len(self.get("currency")) != 3:
            raise ValueError("Field 'Bill.currency' must be an ISO-4217 currency string code.")
        if "created" not in self:
            self["created"] = now()
        try:
            self["created"] = dt_parse(str(self.get("created"))).isoformat()
        except ValueError:
            raise ValueError("Field 'Bill.created' must be an ISO-8601 datetime string.")
        if "id" not in self:
            self["id"] = uuid.uuid4()

    @property
    def id(self):
        """
        Bill ID.
        """
        return dict.__getitem__(self, "id")

    @property
    def user(self):
        """
        User ID.
        """
        return dict.__getitem__(self, "user")

    @property
    def quote(self):
        """
        Quote ID.
        """
        return dict.__getitem__(self, "quote")

    @property
    def job(self):
        """
        Job ID.
        """
        return dict.__getitem__(self, "job")

    @property
    def price(self):
        """
        Price of the current quote.
        """
        return self.get("price", 0.0)

    @property
    def currency(self):
        """
        Currency of the quote price.
        """
        return self.get("currency")

    @property
    def created(self):
        """
        Quote creation datetime.
        """
        return self.get("created")

    @property
    def title(self):
        """
        Quote title.
        """
        return self.get("title")

    @property
    def description(self):
        """
        Quote description.
        """
        return self.get("description")

    def params(self):
        # type: () -> AnyParams
        return {
            "id": self.id,
            "user": self.user,
            "quote": self.quote,
            "job": self.job,
            "price": self.price,
            "currency": self.currency,
            "created": self.created,
            "title": self.title,
            "description": self.description,
        }

    def json(self):
        # type: () -> JSON
        return sd.BillSchema().deserialize(self)
