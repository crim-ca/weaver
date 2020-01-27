"""
Utility methods for various TestCase setup operations.
"""
import os
import uuid
import warnings
from contextlib import ExitStack
from inspect import isclass
from typing import TYPE_CHECKING

import mock
import pyramid_celery
import six
from pyramid import testing
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPNotFound, HTTPUnprocessableEntity
from pyramid.registry import Registry
from requests import Response
from six.moves.configparser import ConfigParser
from webtest import TestApp

from weaver.config import WEAVER_CONFIGURATION_DEFAULT, WEAVER_DEFAULT_INI_CONFIG, get_weaver_config_file
from weaver.database import get_db
from weaver.datatype import Service
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_XML
from weaver.store.mongodb import MongodbJobStore, MongodbProcessStore, MongodbServiceStore
from weaver.utils import get_url_without_query, null
from weaver.warning import MissingParameterWarning, UnsupportedOperationWarning
from weaver.wps import get_wps_output_dir, get_wps_output_url, get_wps_url
from weaver.wps_restapi.processes.processes import execute_process

if TYPE_CHECKING:
    from weaver.typedefs import Any, AnyStr, Callable, List, Optional, SettingsType, Type, Union  # noqa: F401


def ignore_warning_regex(func, warning_message_regex, warning_categories=DeprecationWarning):
    # type: (Callable, Union[AnyStr, List[AnyStr]], Union[Type[Warning], List[Type[Warning]]]) -> Callable
    """Wrapper that eliminates any warning matching ``warning_regex`` during testing logging.

    **NOTE**:
        Wrapper should be applied on method (not directly on :class:`unittest.TestCase`
        as it can disable the whole test suite.
    """
    if isinstance(warning_message_regex, six.string_types):
        warning_message_regex = [warning_message_regex]
    if not isinstance(warning_message_regex, list):
        raise NotImplementedError("Argument 'warning_message_regex' must be a string or a list of string.")
    if not isinstance(warning_categories, list):
        warning_categories = [warning_categories]
    for warn in warning_categories:
        if not isclass(warn) or not issubclass(warn, Warning):
            raise NotImplementedError("Argument 'warning_categories' must be one or multiple subclass(es) of Warning.")

    def do_test(self, *args, **kwargs):
        with warnings.catch_warnings():
            for warn_cat in warning_categories:
                for msg_regex in warning_message_regex:
                    warnings.filterwarnings(action="ignore", message=msg_regex, category=warn_cat)
            func(self, *args, **kwargs)
    return do_test


def ignore_wps_warnings(func):
    """Wrapper that eliminates WPS related warnings during testing logging.

    **NOTE**:
        Wrapper should be applied on method (not directly on :class:`unittest.TestCase`
        as it can disable the whole test suite.
    """
    warn_msg_regex = ["Parameter 'request*", "Parameter 'service*", "Request type '*", "Service '*"]
    warn_categories = [MissingParameterWarning, UnsupportedOperationWarning]
    return ignore_warning_regex(func, warn_msg_regex, warn_categories)


def get_settings_from_config_ini(config_ini_path=None, ini_section_name="app:main"):
    # type: (Optional[AnyStr], AnyStr) -> SettingsType
    parser = ConfigParser()
    parser.read([get_weaver_config_file(config_ini_path, WEAVER_DEFAULT_INI_CONFIG)])
    settings = dict(parser.items(ini_section_name))
    return settings


def setup_config_from_settings(settings=None):
    # type: (Optional[SettingsType]) -> Configurator
    settings = settings or {}
    config = testing.setUp(settings=settings)
    return config


def setup_config_with_mongodb(config=None, settings=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> Configurator
    settings = settings or {}
    settings.update({
        "mongodb.host":     os.getenv("WEAVER_TEST_DB_HOST", "127.0.0.1"),      # noqa: E241
        "mongodb.port":     os.getenv("WEAVER_TEST_DB_PORT", "27017"),          # noqa: E241
        "mongodb.db_name":  os.getenv("WEAVER_TEST_DB_NAME", "weaver-test"),    # noqa: E241
    })
    if config:
        config.registry.settings.update(settings)
    else:
        config = get_test_weaver_config(settings=settings)
    return config


def setup_mongodb_servicestore(config=None):
    # type: (Optional[Configurator]) -> MongodbServiceStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = get_db(config).get_store(MongodbServiceStore)
    store.clear_services()
    return store    # noqa


def setup_mongodb_processstore(config=None):
    # type: (Optional[Configurator]) -> MongodbProcessStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = get_db(config).get_store(MongodbProcessStore)
    store.clear_processes()
    # store must be recreated after clear because processes are added automatically on __init__
    get_db(config)._stores.pop(MongodbProcessStore.type)
    store = get_db(config).get_store(MongodbProcessStore)
    return store


def setup_mongodb_jobstore(config=None):
    # type: (Optional[Configurator]) -> MongodbJobStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = get_db(config).get_store(MongodbJobStore)
    store.clear_jobs()
    # noinspection PyTypeChecker
    return store


def setup_config_with_pywps(config):
    # type: (Configurator) -> Configurator
    settings = config.get_settings()
    settings.update({
        "PYWPS_CFG": {
            "server.url": get_wps_url(settings),
            "server.outputurl": get_wps_output_url(settings),
            "server.outputpath": get_wps_output_dir(settings),
        },
    })
    config.registry.settings.update(settings)
    config.include("weaver.wps")
    return config


def setup_config_with_celery(config):
    # type: (Configurator) -> Configurator
    settings = config.get_settings()

    # override celery loader to specify configuration directly instead of ini file
    celery_settings = {
        "CELERY_BROKER_URL": "mongodb://{}:{}/celery".format(settings.get("mongodb.host"), settings.get("mongodb.port"))
    }
    pyramid_celery.loaders.INILoader.read_configuration = mock.MagicMock(return_value=celery_settings)
    config.include("pyramid_celery")
    config.configure_celery("")  # value doesn't matter because overloaded
    return config


def get_test_weaver_config(config=None, settings=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> Configurator
    if not config:
        # default db required if none specified by config
        config = setup_config_from_settings(settings=settings)
    if "weaver.configuration" not in config.registry.settings:
        config.registry.settings["weaver.configuration"] = WEAVER_CONFIGURATION_DEFAULT
    if "weaver.url" not in config.registry.settings:
        config.registry.settings["weaver.url"] = "https://localhost"
    # ignore example config files that would be auto-generated when missing
    config.registry.settings["weaver.wps_processes"] = None
    if settings:
        config.registry.settings.update(settings)
    # create the test application
    config.include("weaver")
    return config


def get_test_weaver_app(config=None, settings=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> TestApp
    config = get_test_weaver_config(config=config, settings=settings)
    config.scan()
    return TestApp(config.make_wsgi_app())


def get_settings_from_testapp(testapp):
    # type: (TestApp) -> SettingsType
    settings = {}
    if hasattr(testapp.app, "registry"):
        settings = testapp.app.registry.settings or {}
    return settings


def get_setting(env_var_name, app=None, setting_name=None):
    # type: (AnyStr, Optional[TestApp], Optional[AnyStr]) -> Any
    val = os.getenv(env_var_name, null)
    if val != null:
        return val
    if app:
        val = app.extra_environ.get(env_var_name, null)
        if val != null:
            return val
        if setting_name:
            val = app.extra_environ.get(setting_name, null)
            if val != null:
                return val
            settings = get_settings_from_testapp(app)
            if settings:
                val = settings.get(setting_name, null)
                if val != null:
                    return val
    return null


def init_weaver_service(registry):
    # type: (Registry) -> None
    service_store = registry.db.get_store(MongodbServiceStore)
    service_store.save_service(Service({
        "type": "",
        "name": "weaver",
        "url": "http://localhost/ows/proxy/weaver",
        "public": True
    }))


def mocked_sub_requests(app, function, *args, **kwargs):
    """
    Executes ``app.function(*args, **kwargs)`` with a mock of every underlying :func:`requests.request` call
    to relay their execution to the :class:`webTest.TestApp`.
    Generates a `fake` response from a file if the URL scheme is ``mock://``.
    """

    def mocked_request(method, url=None, headers=None, verify=None, cert=None, **req_kwargs):  # noqa: E811
        """
        Request corresponding to :func:`requests.request` that instead gets executed by :class:`webTest.TestApp`.
        """
        method = method.lower()
        headers = headers or req_kwargs.get("headers")
        req = getattr(app, method)
        url = req_kwargs.get("base_url", url)
        query = req_kwargs.get("params")
        if query:
            url = url + "?" + query
        if not url.startswith("mock://"):
            resp = req(url, params=req_kwargs.get("data"), headers=headers)
            setattr(resp, "content", resp.body)
        else:
            path = get_url_without_query(url.replace("mock://", ""))
            if not os.path.isfile(path):
                raise HTTPNotFound("Could not find mock file: [{}]".format(url))
            resp = Response()
            ext = os.path.splitext(path)[-1]
            typ = CONTENT_TYPE_APP_JSON if ext == ".json" else CONTENT_TYPE_TEXT_XML if ext == ".xml" else None
            if not typ:
                return HTTPUnprocessableEntity("Unknown Content-Type for mock file: [{}]".format(url))
            resp.status_code = 200
            resp.headers["Content-Type"] = typ
            setattr(resp, "content_type", typ)
            resp._content = open(path, "rb").read()
            resp.url = url
        return resp

    with ExitStack() as stack:
        stack.enter_context(mock.patch("requests.request", side_effect=mocked_request))
        stack.enter_context(mock.patch("requests.sessions.Session.request", side_effect=mocked_request))
        request_func = getattr(app, function)
        return request_func(*args, **kwargs)


def mocked_execute_process():
    """
    Provides a mock to call :func:`weaver.wps_restapi.processes.processes.execute_process` safely within
    a test employing a :class:`webTest.TestApp` without a running ``Celery`` app.
    This avoids connection error from ``Celery`` during a job execution request.

    Bypasses the ``execute_process.delay`` call by directly invoking the ``execute_process``.

    **Note**: since ``delay`` and ``Celery`` are bypassed, the process execution becomes blocking (not asynchronous).

    .. seealso::
        :func:`mocked_process_job_runner` to completely skip process execution.
    """
    class MockTask(object):
        """
        Mocks call ``self.request.id`` in :func:`weaver.wps_restapi.processes.processes.execute_process` and
        call ``result.id`` in :func:`weaver.wps_restapi.processes.processes.submit_job_handler`.
        """
        _id = str(uuid.uuid4())

        @property
        def id(self):
            return self._id

    task = MockTask()

    def mock_execute_process(job_id, url, headers, notification_email):
        execute_process(job_id, url, headers, notification_email)
        return task

    return (
        mock.patch("weaver.wps_restapi.processes.processes.execute_process.delay", side_effect=mock_execute_process),
        mock.patch("celery.app.task.Context", return_value=task)
    )


def mocked_process_job_runner(job_task_id="mocked-job-id"):
    """
    Provides a mock that will no execute the process execution when call during job creation.

    .. seealso::
        :func:`mocked_execute_process` to still execute the process, but without `Celery` connection.
    """
    result = mock.MagicMock()
    result.id = job_task_id
    return (
        mock.patch("weaver.wps_restapi.processes.processes.execute_process.delay", return_value=result),
    )


def mocked_process_package():
    """
    Provides mocks that bypasses execution when calling :module:`weaver.processes.wps_package` functions.
    """
    return (
        mock.patch("weaver.processes.wps_package._load_package_file", return_value={"class": "test"}),
        mock.patch("weaver.processes.wps_package._load_package_content", return_value=(None, "test", None)),
        mock.patch("weaver.processes.wps_package._get_package_inputs_outputs", return_value=(None, None)),
        mock.patch("weaver.processes.wps_package._merge_package_inputs_outputs", return_value=([], [])),
    )
