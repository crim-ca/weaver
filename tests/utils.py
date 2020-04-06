"""
Utility methods for various TestCase setup operations.
"""
import contextlib
import os
import tempfile
import uuid
import warnings
from configparser import ConfigParser
from inspect import isclass
from typing import TYPE_CHECKING

# Note: do NOT import 'boto3' here otherwise 'moto' will not be able to mock it effectively
import mock
import moto
import pyramid_celery
from pyramid import testing
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPException, HTTPNotFound, HTTPUnprocessableEntity
from pyramid.registry import Registry
from requests import Response
from webtest import TestApp

from weaver.app import main as weaver_app
from weaver.config import WEAVER_CONFIGURATION_DEFAULT, WEAVER_DEFAULT_INI_CONFIG, get_weaver_config_file
from weaver.database import get_db
from weaver.datatype import Service
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_TEXT_XML
from weaver.store.mongodb import MongodbJobStore, MongodbProcessStore, MongodbServiceStore
from weaver.utils import get_path_kvp, get_url_without_query, get_weaver_url, null
from weaver.warning import MissingParameterWarning, UnsupportedOperationWarning

if TYPE_CHECKING:
    import botocore.client  # noqa

    from weaver.typedefs import Any, AnyResponseType, Callable, List, Optional, SettingsType, Type, Union

MOCK_AWS_REGION = "us-central-1"


def ignore_warning_regex(func, warning_message_regex, warning_categories=DeprecationWarning):
    # type: (Callable, Union[str, List[str]], Union[Type[Warning], List[Type[Warning]]]) -> Callable
    """Wrapper that eliminates any warning matching ``warning_regex`` during testing logging.

    **NOTE**:
        Wrapper should be applied on method (not directly on :class:`unittest.TestCase`
        as it can disable the whole test suite.
    """
    if isinstance(warning_message_regex, str):
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
    # type: (Optional[str], str) -> SettingsType
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
    """Prepares the configuration in order to allow calls to a ``MongoDB`` test database."""
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
    db = get_db(config)
    store = db.get_store(MongodbProcessStore)
    store.clear_processes()
    # store must be recreated after clear because processes are added automatically on __init__
    db.reset_store(MongodbProcessStore.type)
    store = db.get_store(MongodbProcessStore)
    return store


def setup_mongodb_jobstore(config=None):
    # type: (Optional[Configurator]) -> MongodbJobStore
    """Setup store using mongodb, will be enforced if not configured properly."""
    config = setup_config_with_mongodb(config)
    store = get_db(config).get_store(MongodbJobStore)
    store.clear_jobs()
    return store


def setup_config_with_pywps(config):
    # type: (Configurator) -> Configurator
    """Prepares the ``PyWPS`` interface, usually needed to call the WPS route (not API), or when executing processes."""
    # flush any PyWPS config (global) to make sure we restart from clean state
    import pywps.configuration  # isort: skip
    pywps.configuration.CONFIG = None
    settings = config.get_settings()
    settings.pop("PYWPS_CONFIG", None)
    settings["weaver.wps_configured"] = False
    os.environ.pop("PYWPS_CONFIG", None)
    config.include("weaver.wps")
    return config


def setup_config_with_celery(config):
    # type: (Configurator) -> Configurator
    """Prepares the configuration to define ``Celery`` settings needed to execute processes from mocked
    :class:`webtest.TestApp` application.

    This is also needed when using :func:`mocked_execute_process` since it will prepare underlying ``Celery``
    application object, multiple of its settings and the database connection reference, although ``Celery`` worker
    still *wouldn't actually be running*. This is because :class:`celery.app.Celery` is often employed in the code
    to retrieve ``Weaver`` settings from it when the process is otherwise executed by a worker.

    .. seealso::
        - :func:`mocked_execute_process`
    """
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
    # set default log level for tests to ease debugging failing test cases
    if not config.registry.settings.get("weaver.log_level"):
        config.registry.settings["weaver.log_level"] = "DEBUG"
    if "weaver.url" not in config.registry.settings:
        config.registry.settings["weaver.url"] = "https://localhost"
    # ignore example config files that would be auto-generated when missing
    config.registry.settings["weaver.wps_processes"] = ""
    if settings:
        config.registry.settings.update(settings)
    # create the test application
    config.include("weaver")
    return config


def get_test_weaver_app(config=None, settings=None):
    # type: (Optional[Configurator], Optional[SettingsType]) -> TestApp
    config = get_test_weaver_config(config=config, settings=settings)
    app = weaver_app({}, **config.get_settings())
    return TestApp(app)


def get_settings_from_testapp(testapp):
    # type: (TestApp) -> SettingsType
    settings = {}
    if hasattr(testapp.app, "registry"):
        settings = testapp.app.registry.settings or {}  # noqa
    return settings


def get_setting(env_var_name, app=None, setting_name=None):
    # type: (str, Optional[TestApp], Optional[str]) -> Any
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


def mocked_file_response(path, url):
    # type: (str, str) -> Union[Response, HTTPException]
    """
    Generates a mocked response from the provided file path, and represented as if coming from the specified URL.

    :param path: actual file path to be served in the response
    :param url: wanted file URL
    :return: generated response
    """
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
    content = open(path, "rb").read()
    resp._content = content  # noqa: W0212

    class StreamReader(object):
        _data = [None, content]  # should technically be split up more to respect chuck size...

        def read(self, chuck_size=None):  # noqa: E811
            return self._data.pop(-1)

    setattr(resp, "raw", StreamReader())
    resp.url = url
    return resp


def mocked_sub_requests(app, function, *args, only_local=False, **kwargs):
    # type: (TestApp, str, *Any, bool, **Any) -> AnyResponseType
    """
    Executes ``app.function(*args, **kwargs)`` with a mock of every underlying :func:`requests.request` call
    to relay their execution to the :class:`webTest.TestApp`.

    Generates a `fake` response from a file if the URL scheme is ``mock://``.

    Executes the *real* request if :paramref:`only_local` is ``True`` and that the request URL (expected as first
    argument of :paramref:`args`) doesn't correspond to the base URL of :paramref:`app`.

    :param app: application employed for the test
    :param function: test application method to call (i.e.: ``post``, ``post_json``, ``get``, etc.)
    :param only_local:
        When ``True``, only mock requests targeted at :paramref:`app` based on request URL hostname (ignore external).
        Otherwise, mock every underlying request regardless of hostname, including ones not targeting the application.
    """
    from requests.sessions import Session as RealSession
    real_request = RealSession.request

    def _parse_for_app_req(method, url, **req_kwargs):
        """
        WebTest application employs ``params`` instead of ``data``/``json``.
        Actual query parameters must be pre-appended to ``url``.
        """
        method = method.lower()
        url = req_kwargs.pop("base_url", url)
        body = req_kwargs.pop("data", None)
        query = req_kwargs.pop("query", None)
        params = req_kwargs.pop("params", {})
        if query:
            url += ("" if query.startswith("?") else "?") + query
        elif params:
            if isinstance(params, str):
                url += ("" if params.startswith("?") else "?") + params
            else:
                url = get_path_kvp(url, **params)
        req_kwargs["params"] = body
        # remove unsupported parameters that cannot be passed down to TestApp
        for key in ["timeout", "cert", "auth", "ssl_verify", "verify", "language"]:
            req_kwargs.pop(key, None)
        req = getattr(app, method)
        return url, req, req_kwargs

    def mocked_app_request(method, url=None, **req_kwargs):
        """
        Request corresponding to :func:`requests.request` that instead gets executed by :class:`webTest.TestApp`,
        unless permitted to call real external requests.
        """
        # if URL starts with '/' directly, it is the shorthand path for this test app, always mock
        # otherwise, filter according to full URL hostname
        url_test_app = get_weaver_url(app.app.registry)
        if only_local and not url.startswith("/") and not url.startswith(url_test_app):
            with RealSession() as session:
                return real_request(session, method, url, **req_kwargs)

        url, func, req_kwargs = _parse_for_app_req(method, url, **req_kwargs)
        if not url.startswith("mock://"):
            resp = func(url, expect_errors=True, **req_kwargs)
            setattr(resp, "content", resp.body)
        else:
            path = get_url_without_query(url.replace("mock://", ""))
            resp = mocked_file_response(path, url)
        return resp

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("requests.request", side_effect=mocked_app_request))
        stack.enter_context(mock.patch("requests.Session.request", side_effect=mocked_app_request))
        stack.enter_context(mock.patch("requests.sessions.Session.request", side_effect=mocked_app_request))
        req_url, req_func, kwargs = _parse_for_app_req(function, *args, **kwargs)
        kwargs.setdefault("expect_errors", True)
        return req_func(req_url, **kwargs)


def mocked_execute_process():
    """
    Provides a mock to call :func:`weaver.processes.execution.execute_process` safely within a test employing
    :class:`webTest.TestApp` without a running ``Celery`` app.

    This avoids connection error from ``Celery`` during a job execution request.

    Bypasses ``execute_process.delay`` call by directly invoking the ``execute_process``.

    .. note::
        Since ``delay`` and ``Celery`` are bypassed, the process execution becomes blocking (not asynchronous).

    .. seealso::
        - :func:`mocked_process_job_runner` to completely skip process execution.
        - :func:`setup_config_with_celery`
    """
    from weaver.processes.execution import execute_process as real_execute_process

    class MockTask(object):
        """
        Mocks call ``self.request.id`` in :func:`weaver.processes.execution.execute_process` and
        call ``result.id`` in :func:`weaver.processes.execution.submit_job_handler`.
        """
        _id = str(uuid.uuid4())

        @property
        def id(self):
            return self._id

    task = MockTask()

    def mock_execute_process(job_id, url, headers):
        real_execute_process(job_id, url, headers)
        return task

    return (
        mock.patch("weaver.processes.execution.execute_process.delay", side_effect=mock_execute_process),
        mock.patch("celery.app.task.Context", return_value=task)
    )


def mocked_process_job_runner(job_task_id="mocked-job-id"):
    """
    Provides a mock that will bypass execution of the process when called during job submission.

    .. seealso::
        - :func:`mocked_execute_process` to still execute the process, but directly instead of within ``Celery`` worker.
    """
    result = mock.MagicMock()
    result.id = job_task_id
    return (
        mock.patch("weaver.processes.execution.execute_process.delay", return_value=result),
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


def mocked_aws_credentials(test_func):
    """Mocked AWS Credentials for :py:mod:`moto`.

    When using this fixture, ensures that if other mocks fail, at least credentials should be invalid to avoid
    mistakenly overriding real bucket files.
    """
    def wrapped(*args, **kwargs):
        with mock.patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SECURITY_TOKEN": "testing",
            "AWS_SESSION_TOKEN": "testing"
        }):
            return test_func(*args, **kwargs)
    return wrapped


def mocked_aws_s3(test_func):
    """
    Mocked AWS S3 bucket for :py:mod:`boto3` over mocked AWS credentials using :py:mod:`moto`.

    .. warning::
        Make sure to employ the same :py:data:`MOCK_AWS_REGION` otherwise mock will not work and S3 operations will
        attempt writing to real bucket.
    """
    def wrapped(*args, **kwargs):
        with moto.mock_s3():
            return test_func(*args, **kwargs)
    return wrapped


def mocked_aws_s3_bucket_test_file(bucket_name, file_name, file_content="Test file inside test S3 bucket"):
    # type: (str,str, str) -> str
    """
    Generates a test file reference from dummy data that will be uploaded to the specified S3 bucket name using the
    provided file key.

    The S3 interface employed is completely dependent of the wrapping context. For instance, calling this function
    with :func:`mocked_aws_s3` decorator will effectively employ the mocked S3 interface.

    .. seealso::
        - :func:`mocked_aws_s3`
    """
    import boto3
    if not MOCK_AWS_REGION:
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3 = boto3.client("s3", region_name=MOCK_AWS_REGION)
        s3_location = {"LocationConstraint": MOCK_AWS_REGION}
        s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=s3_location)
    with tempfile.NamedTemporaryFile(mode="w") as tmp_file:
        tmp_file.write(file_content)
        tmp_file.flush()
        s3.upload_file(Bucket=bucket_name, Filename=tmp_file.name, Key=file_name)
    return "s3://{}/{}".format(bucket_name, file_name)
