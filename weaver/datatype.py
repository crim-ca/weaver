"""
Definitions of types used by tokens.
"""
import copy
import inspect
import traceback
import uuid
import warnings
from datetime import datetime, timedelta
from logging import ERROR, INFO, Logger, getLevelName, getLogger
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import lxml.etree
import pyramid.httpexceptions
import requests.exceptions
from dateutil.parser import parse as dt_parse
from owslib.wps import Process as ProcessOWS, WPSException
from pywps import Process as ProcessWPS

from weaver.exceptions import ProcessInstanceError
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_CONTROL_OPTIONS,
    EXECUTE_TRANSMISSION_MODE_OPTIONS,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import ACCEPT_LANGUAGE_EN_CA, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML
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
    JOB_STATUS_VALUES,
    STATUS_CATEGORY_FINISHED,
    STATUS_SUCCEEDED,
    STATUS_UNKNOWN,
    map_status
)
from weaver.typedefs import XML
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

    from weaver.typedefs import AnyProcess, AnySettingsContainer, Number, CWL, JSON

LOGGER = getLogger(__name__)


class Base(dict):
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
            super(Base, self).__setitem__(item, value)

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
            raise AttributeError("Can't get attribute '{}'.".format(item))

    def __str__(self):
        # type: () -> str
        return "{0} <{1}>".format(type(self).__name__, self.id)

    def __repr__(self):
        # type: () -> str
        cls = type(self)
        repr_ = dict.__repr__(self)
        return "{0}.{1} ({2})".format(cls.__module__, cls.__name__, repr_)

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
        # type: () -> Dict[str, Any]
        """
        Obtain the internal data representation for storage.

        .. note::
            This method implementation should provide a JSON-serializable definition of all fields representing
            the object to store.
        """
        raise NotImplementedError("Method 'params' must be defined for storage item representation.")

    def dict(self):
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
        # type: () -> Dict[str, Any]
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
        _wps = self.get("_wps")
        if _wps is None:
            # client retrieval could also be cached if recently fetched an not yet invalidated
            self["_wps"] = _wps = get_wps_client(self.url, container=container, **kwargs)
        return _wps

    def links(self, container, fetch=True):
        # type: (AnySettingsContainer, bool) -> List[JSON]
        """
        Obtains the links relevant to the service provider.
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
                "rel": "self",
                "title": "Service definition.",
                "href": svc_url,
                "hreflang": ACCEPT_LANGUAGE_EN_CA,
                "type": CONTENT_TYPE_APP_JSON,
            },
            {
                "rel": "processes",
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

    def summary(self, container, fetch=True):
        # type: (AnySettingsContainer, bool) -> Optional[JSON]
        """
        Obtain the summary information from the provider service.

        When metadata fetching is disabled, the generated summary will contain only information available locally.

        :param container: employed to retrieve application settings.
        :param fetch: indicates whether metadata should be fetched from remote.
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
        except Exception as exc:
            msg = "Exception occurred while fetching wps {0} : {1!r}".format(self.url, exc)
            warnings.warn(msg, NonBreakingExceptionWarning)
        return None

    def processes(self, container):
        # type: (AnySettingsContainer) -> List[Process]
        """
        Obtains a list of remote service processes in a compatible :class:`weaver.datatype.Process` format.

        Note: remote processes won't be stored to the local process storage.
        """
        # FIXME: support other providers (https://github.com/crim-ca/weaver/issues/130)
        if self.type.lower() not in PROCESS_WPS_TYPES:
            return []
        wps = self.wps(container)
        settings = get_settings(container)
        return [Process.convert(process, self, settings) for process in wps.processes]

    def check_accessible(self, settings):
        # type: (AnySettingsContainer) -> bool
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
            msg = "HTTP exception occurred while checking service [{}] accessibility on [{}] : {!r}".format(
                self.name, self.url, exc
            )
            warnings.warn(msg, NonBreakingExceptionWarning)
        return False


class Job(Base):
    """
    Dictionary that contains OWS service jobs.

    It always has ``id`` and ``task_id`` keys.
    """

    def __init__(self, *args, **kwargs):
        super(Job, self).__init__(*args, **kwargs)
        if "task_id" not in self:
            raise TypeError("Parameter 'task_id' is required for '{}' creation.".format(type(self)))
        if not isinstance(self.id, str):
            raise TypeError("Type 'str' is required for '{}.id'".format(type(self)))

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
            Uses the current :prop:`Job.status` value if not specified. Must be one of :mod:`Weaver.status` values.
        :param progress:
            Override progress applied in the logged message entry, but does not set it to the job object.
            Uses the current :prop:`Job.progress` value if not specified.

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
                                           name=fully_qualified_name(self),
                                           message=msg)
            if len(self.logs) == 0 or self.logs[-1] != fmt_msg:
                self.logs.append(fmt_msg)
                if logger:
                    logger.log(lvl, msg)

    @property
    def id(self):
        # type: () -> str
        """
        Job UUID to retrieve the details from storage.
        """
        job_id = self.get("id")
        if not job_id:
            job_id = str(uuid.uuid4())
            self["id"] = job_id
        return job_id

    @property
    def task_id(self):
        # type: () -> Optional[str]
        """
        Reference Task UUID attributed by the ``Celery`` worker that monitors and executes this job.
        """
        return self.get("task_id", None)

    @task_id.setter
    def task_id(self, task_id):
        # type: (str) -> None
        if not isinstance(task_id, str):
            raise TypeError("Type 'str' is required for '{}.task_id'".format(type(self)))
        self["task_id"] = task_id

    @property
    def wps_id(self):
        # type: () -> Optional[str]
        """
        Reference WPS Request/Response UUID attributed by the executed ``PyWPS`` process.

        This UUID matches the status-location, log and output directory of the WPS process.
        This parameter is only available when the process is executed on this local instance.

        .. seealso::
            - :attr:`Job.request`
            - :attr:`Job.response`
        """
        return self.get("wps_id", None)

    @wps_id.setter
    def wps_id(self, wps_id):
        # type: (str) -> None
        if not isinstance(wps_id, str):
            raise TypeError("Type 'str' is required for '{}.wps_id'".format(type(self)))
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
            raise TypeError("Type 'str' is required for '{}.service'".format(type(self)))
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
            raise TypeError("Type 'str' is required for '{}.process'".format(type(self)))
        self["process"] = process

    def _get_inputs(self):
        # type: () -> List[Optional[Dict[str, Any]]]
        if self.get("inputs") is None:
            self["inputs"] = list()
        return dict.__getitem__(self, "inputs")

    def _set_inputs(self, inputs):
        # type: (List[Optional[Dict[str, Any]]]) -> None
        if not isinstance(inputs, list):
            raise TypeError("Type 'list' is required for '{}.inputs'".format(type(self)))
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
            raise TypeError("Type 'int' is required for '{}.user_id'".format(type(self)))
        self["user_id"] = user_id

    @property
    def status(self):
        # type: () -> str
        return self.get("status", STATUS_UNKNOWN)

    @status.setter
    def status(self, status):
        # type: (str) -> None
        if status == "accepted" and self.status == "running":
            LOGGER.debug(traceback.extract_stack())
        if not isinstance(status, str):
            raise TypeError("Type 'str' is required for '{}.status'".format(type(self)))
        if status not in JOB_STATUS_VALUES:
            raise ValueError("Status '{0}' is not valid for '{1}.status', must be one of {2!s}'"
                             .format(status, type(self), list(JOB_STATUS_VALUES)))
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
            raise TypeError("Type 'str' is required for '{}.status_message'".format(type(self)))
        self["status_message"] = message

    @property
    def status_location(self):
        # type: () -> Optional[str]
        return self.get("status_location", None)

    @status_location.setter
    def status_location(self, location_url):
        # type: (Optional[str]) -> None
        if not isinstance(location_url, str) or location_url is None:
            raise TypeError("Type 'str' is required for '{}.status_location'".format(type(self)))
        self["status_location"] = location_url

    @property
    def notification_email(self):
        # type: () -> Optional[str]
        return self.get("notification_email")

    @notification_email.setter
    def notification_email(self, email):
        # type: (Optional[Union[str]]) -> None
        if not isinstance(email, str):
            raise TypeError("Type 'str' is required for '{}.notification_email'".format(type(self)))
        self["notification_email"] = email

    @property
    def accept_language(self):
        # type: () -> Optional[str]
        return self.get("accept_language")

    @accept_language.setter
    def accept_language(self, language):
        # type: (Optional[Union[str]]) -> None
        if not isinstance(language, str):
            raise TypeError("Type 'str' is required for '{}.accept_language'".format(type(self)))
        self["accept_language"] = language

    @property
    def execute_async(self):
        # type: () -> bool
        return self.get("execute_async", True)

    @execute_async.setter
    def execute_async(self, execute_async):
        # type: (bool) -> None
        if not isinstance(execute_async, bool):
            raise TypeError("Type 'bool' is required for '{}.execute_async'".format(type(self)))
        self["execute_async"] = execute_async

    @property
    def is_local(self):
        # type: () -> bool
        return self.get("is_local", not self.service)

    @is_local.setter
    def is_local(self, is_local):
        # type: (bool) -> None
        if not isinstance(is_local, bool):
            raise TypeError("Type 'bool' is required for '{}.is_local'".format(type(self)))
        self["is_local"] = is_local

    @property
    def is_workflow(self):
        # type: () -> bool
        return self.get("is_workflow", False)

    @is_workflow.setter
    def is_workflow(self, is_workflow):
        # type: (bool) -> None
        if not isinstance(is_workflow, bool):
            raise TypeError("Type 'bool' is required for '{}.is_workflow'".format(type(self)))
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
            raise TypeError("Type 'datetime' is required for '{}.started'".format(type(self)))
        self["started"] = started

    @property
    def finished(self):
        # type: () -> Optional[datetime]
        return self.get("finished", None)

    def is_finished(self):
        # type: () -> bool
        return self.finished is not None

    def mark_finished(self):
        # type: () -> None
        self["finished"] = now()

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
            raise TypeError("Number is required for '{}.progress'".format(type(self)))
        if progress < 0 or progress > 100:
            raise ValueError("Value must be in range [0,100] for '{}.progress'".format(type(self)))
        self["progress"] = progress

    def _get_results(self):
        # type: () -> List[Optional[Dict[str, Any]]]
        if self.get("results") is None:
            self["results"] = list()
        return dict.__getitem__(self, "results")

    def _set_results(self, results):
        # type: (List[Optional[Dict[str, Any]]]) -> None
        if not isinstance(results, list):
            raise TypeError("Type 'list' is required for '{}.results'".format(type(self)))
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
            raise TypeError("Type 'list' is required for '{}.exceptions'".format(type(self)))
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
            raise TypeError("Type 'list' is required for '{}.logs'".format(type(self)))
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
            raise TypeError("Type 'list' is required for '{}.tags'".format(type(self)))
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
            raise TypeError("Type 'str' is required for '{}.access'".format(type(self)))
        if visibility not in VISIBILITY_VALUES:
            raise ValueError("Invalid 'visibility' value specified for '{}.access'".format(type(self)))
        self["access"] = visibility

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
        if isinstance(request, XML):
            request = lxml.etree.tostring(request)
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
        if isinstance(response, XML):
            response = lxml.etree.tostring(response)
        self["response"] = response

    def _job_url(self, base_url=None):
        if self.service is not None:
            base_url += sd.provider_service.path.format(provider_id=self.service)
        job_path = sd.process_job_service.path.format(process_id=self.process, job_id=self.id)
        return "{base_job_url}{job_path}".format(base_job_url=base_url, job_path=job_path)

    def links(self, container=None, self_link=None):
        # type: (Optional[AnySettingsContainer], Optional[str]) -> JSON
        """
        Obtains the JSON links section of many response body for jobs.

        If :paramref:`self_link` is provided (e.g.: `"outputs"`) the link for that corresponding item will also
        be added as `self` entry to the links. It must be a recognized job link field.

        :param container: object that helps retrieve instance details, namely the host URL.
        :param self_link: name of a section that represents the current link that will be returned.
        """
        settings = get_settings(container)
        base_url = get_wps_restapi_base_url(settings)
        job_url = self._job_url(base_url)
        job_list = "{}/{}".format(base_url, sd.jobs_service.path)
        job_links_body = {"links": [
            {"href": job_url, "rel": "status", "title": "Job status."},
            {"href": job_url, "rel": "monitor", "title": "Job monitoring location."},
            {"href": job_list, "rel": "collection", "title": "List of submitted jobs."}
        ]}
        job_links = ["logs", "inputs"]
        if self.status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_FINISHED]:
            job_status = map_status(self.status)
            if job_status == STATUS_SUCCEEDED:
                job_links.extend(["outputs", "results"])
            else:
                job_links.extend(["exceptions"])
        for link_type in job_links:
            link_href = "{job_url}/{res}".format(job_url=job_url, res=link_type)
            job_links_body["links"].append({"href": link_href, "rel": link_type, "title": "Job {}.".format(link_type)})
        if self_link in ["status", "inputs", "outputs", "results", "logs", "exceptions"]:
            self_link_body = list(filter(lambda _link: _link["rel"] == self_link, job_links_body["links"]))[-1]
            self_link_body = copy.deepcopy(self_link_body)
        else:
            self_link_body = {"href": job_url, "title": "Job status."}
        self_link_body["rel"] = "self"
        job_links_body["links"].append(self_link_body)
        link_meta = {"type": CONTENT_TYPE_APP_JSON, "hreflang": ACCEPT_LANGUAGE_EN_CA}
        for link in job_links_body["links"]:
            link.update(link_meta)
        return job_links_body

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
            "status": self.status,
            "message": self.status_message,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "duration": self.duration_str,
            "runningSeconds": self.duration.total_seconds() if self.duration is not None else None,
            # TODO: available fields not yet employed (https://github.com/crim-ca/weaver/issues/129)
            "nextPoll": None,
            "expirationDate": None,
            "estimatedCompletion": None,
            "percentCompleted": self.progress,
        }
        job_json.update(self.links(settings, self_link=self_link))
        return sd.JobStatusInfo().deserialize(job_json)

    def params(self):
        # type: () -> Dict[str, Any]
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
            "execute_async": self.execute_async,
            "is_workflow": self.is_workflow,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "progress": self.progress,
            "results": self.results,
            "exceptions": self.exceptions,
            "logs": self.logs,
            "tags": self.tags,
            "access": self.access,
            "request": self.request,
            "response": self.response,
            "notification_email": self.notification_email,
            "accept_language": self.accept_language,
        }


class Process(Base):
    # pylint: disable=C0103,invalid-name
    """
    Dictionary that contains a process definition for db storage.

    It always has ``identifier`` (or ``id`` alias) and a ``package`` definition.
    Parameters can be accessed by key or attribute, and appropriate validators or default values will be applied.
    """

    def __init__(self, *args, **kwargs):
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
        # type: () -> Optional[List[Dict[str, Any]]]
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
        # type: () -> Optional[List[Dict[str, Any]]]
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
            raise TypeError("Type 'str' is required for '{}.visibility'".format(type(self)))
        if visibility not in VISIBILITY_VALUES:
            raise ValueError("Status '{0}' is not valid for '{1}.visibility, must be one of {2!s}'"
                             .format(visibility, type(self), list(VISIBILITY_VALUES)))
        self["visibility"] = visibility

    def params(self):
        # type: () -> Dict[str, Any]
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
        }

    @property
    def params_wps(self):
        # type: () -> Dict[str, Any]
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

    def json(self):
        # type: () -> JSON
        """
        Obtains the JSON serializable complete representation of the process.
        """
        return sd.Process().deserialize(self.dict())

    def links(self, container=None):
        # type: (Optional[AnySettingsContainer]) -> JSON
        """
        Obtains the JSON links section of many response body for the process.

        :param container: object that helps retrieve instance details, namely the host URL.
        """
        settings = get_settings(container)
        base_url = get_wps_restapi_base_url(settings)
        proc_desc = sd.process_service.path.format(process_id=self.id)
        proc_list = sd.processes_service.path
        proc_exec = sd.process_execution_service.path.format(process_id=self.id)
        links = [
            {"href": base_url + proc_desc, "rel": "self", "title": "Process description."},
            {"href": base_url + proc_desc, "rel": "process-desc", "title": "Process description."},
            {"href": base_url + proc_exec, "rel": "execute", "title": "Process execution endpoint for job submission."},
            {"href": base_url + proc_list, "rel": "collection", "title": "List of registered processes."}
        ]
        if self.processEndpointWPS1:
            wps_url = "{}?service=WPS&request=GetCapabilities".format(self.processEndpointWPS1)
            links.append({"href": wps_url, "rel": "service-desc",
                          "type": CONTENT_TYPE_APP_XML, "title": "Service definition."})
        for link in links:
            link.setdefault("type", CONTENT_TYPE_APP_JSON)
            link.setdefault("hreflang", ACCEPT_LANGUAGE_EN_CA)
        return {"links": links}

    def offering(self, schema="OGC"):
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
        if str(schema or "OGC").upper() == "OLD":
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
        # type: (ProcessWPS, **Any) -> Process
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
        else:
            svc_name = service.get("name")
            remote_service_url = service.url
            local_provider_url = "{}/providers/{}".format(wps_api_url, svc_name)
        describe_process_url = "{}/processes/{}".format(local_provider_url, process.identifier)
        execute_process_url = "{}/jobs".format(describe_process_url)
        package, info = ows2json(process, svc_name, remote_service_url)
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
        })
        return Process(**info, **kwargs)

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
            self["id"] = str(uuid.uuid4())

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
        # type: () -> Dict[str, Any]
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
            self["id"] = str(uuid.uuid4())

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
        # type: () -> Dict[str, Any]
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
