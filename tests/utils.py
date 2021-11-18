"""
Utility methods for various TestCase setup operations.
"""
import datetime

import json

import contextlib
import functools
import inspect
import mimetypes
import os
import re
import tempfile
import uuid
import warnings
from configparser import ConfigParser
from inspect import isclass
from typing import TYPE_CHECKING

# Note: do NOT import 'boto3' here otherwise 'moto' will not be able to mock it effectively
import colander
import mock
import moto
import pkg_resources
import pyramid_celery
import responses
from owslib.wps import Languages, WebProcessingService
from pyramid import testing
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPException, HTTPNotFound, HTTPUnprocessableEntity
from pyramid.registry import Registry
from requests import Response
from webtest import TestApp, TestResponse

from weaver.app import main as weaver_app
from weaver.config import WEAVER_CONFIGURATION_HYBRID, WEAVER_DEFAULT_INI_CONFIG, get_weaver_config_file
from weaver.database import get_db
from weaver.datatype import Service
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_PLAIN, CONTENT_TYPE_TEXT_XML
from weaver.store.mongodb import MongodbJobStore, MongodbProcessStore, MongodbServiceStore
from weaver.utils import (
    fetch_file,
    get_header,
    get_path_kvp,
    get_url_without_query,
    get_weaver_url,
    null,
    request_extra
)
from weaver.warning import MissingParameterWarning, UnsupportedOperationWarning
from weaver.wps.utils import get_wps_output_url, map_wps_output_location

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Type, Union

    import botocore.client  # noqa
    from owslib.wps import Process as ProcessOWSWPS
    from pywps.app import Process as ProcessPyWPS

    from weaver.typedefs import AnyRequestType, AnyResponseType, SettingsType

    # pylint: disable=C0103,invalid-name,E1101,no-member
    MockPatch = mock._patch  # noqa

    # [WPS1-URL, GetCapPathXML, [DescribePathXML], [ExecutePathXML]]
    MockConfigWPS1 = Sequence[str, str, Optional[Sequence[str]], Optional[Sequence[str]]]

MOCK_AWS_REGION = "us-central-1"
MOCK_HTTP_REF = "http://mock.localhost"


def ignore_warning_regex(func, warning_message_regex, warning_categories=DeprecationWarning):
    # type: (Callable, Union[str, List[str]], Union[Type[Warning], List[Type[Warning]]]) -> Callable
    """
    Wrapper that eliminates any warning matching ``warning_regex`` during testing logging.

    .. note::
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
    """
    Wrapper that eliminates WPS related warnings during testing logging.

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
    """
    Prepares the configuration in order to allow calls to a ``MongoDB`` test database.
    """
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
    """
    Setup store using mongodb, will be enforced if not configured properly.
    """
    config = setup_config_with_mongodb(config)
    store = get_db(config).get_store(MongodbServiceStore)
    store.clear_services()
    return store    # noqa


def setup_mongodb_processstore(config=None):
    # type: (Optional[Configurator]) -> MongodbProcessStore
    """
    Setup store using mongodb, will be enforced if not configured properly.
    """
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
    """
    Setup store using mongodb, will be enforced if not configured properly.
    """
    config = setup_config_with_mongodb(config)
    store = get_db(config).get_store(MongodbJobStore)
    store.clear_jobs()
    return store


def setup_config_with_pywps(config):
    # type: (Configurator) -> Configurator
    """
    Prepares the ``PyWPS`` interface, usually needed to call the WPS route (not API), or when executing processes.
    """
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
    """
    Configures :mod:`celery` settings to mock process executions from under a :class:`webtest.TestApp` application.

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
        # allow both local and remote for testing, alternative test should provide explicitly
        config.registry.settings["weaver.configuration"] = WEAVER_CONFIGURATION_HYBRID
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
    config.registry.settings.setdefault("weaver.ssl_verify", "false")
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


def get_module_version(module):
    # type: (Any) -> str
    if not isinstance(module, str):
        version = getattr(module, "__version__", None)
        if version is not None:
            return version
        module = module.__name__
    return pkg_resources.get_distribution(module).version


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

    # add extra methods that 'real' response would have and that are employed by underlying code
    setattr(resp, "raw", StreamReader())
    if isinstance(resp, TestResponse):
        setattr(resp, "url", url)
        setattr(resp, "reason", getattr(resp, "explanation", ""))
        setattr(resp, "raise_for_status", lambda: Response.raise_for_status(resp))
    return resp


def mocked_sub_requests(app, method_function, *args, only_local=False, **kwargs):
    # type: (TestApp, str, *Any, bool, Any) -> AnyResponseType
    """
    Mocks request calls under :class:`webTest.TestApp` to avoid sending real requests.

    Executes ``app.function(*args, **kwargs)`` with a mock of every underlying :func:`requests.request` call
    to relay their execution to the :class:`webTest.TestApp`.

    Generates a `fake` response from a file if the URL scheme is ``mock://``.

    Executes the *real* request if :paramref:`only_local` is ``True`` and that the request URL (expected as first
    argument of :paramref:`args`) doesn't correspond to the base URL of :paramref:`app`.

    :param app: application employed for the test
    :param method_function: test application method to call (i.e.: ``post``, ``post_json``, ``get``, etc.)
    :param only_local:
        When ``True``, only mock requests targeted at :paramref:`app` based on request URL hostname (ignore external).
        Otherwise, mock every underlying request regardless of hostname, including ones not targeting the application.
    """
    from weaver.wps_restapi.swagger_definitions import FileLocal
    from requests.sessions import Session as RealSession
    real_request = RealSession.request

    def _parse_for_app_req(method, url, **req_kwargs):
        """
        Obtain request details with adjustments to support specific handling for :class:`webTest.TestApp`.

        WebTest application employs ``params`` instead of ``data``/``json``.
        Actual query parameters must be pre-appended to ``url``.
        """
        method = method.lower()
        url = req_kwargs.pop("base_url", url)
        body = req_kwargs.pop("data", None)
        _json = req_kwargs.pop("json", None)
        query = req_kwargs.pop("query", None)
        params = req_kwargs.pop("params", {})
        if query:
            url += ("" if query.startswith("?") else "?") + query
        elif params:
            if isinstance(params, str):
                url += ("" if params.startswith("?") else "?") + params
            else:
                url = get_path_kvp(url, **params)
        req_kwargs["params"] = content = body or _json or {}
        # remove unsupported parameters that cannot be passed down to TestApp
        for key in ["timeout", "cert", "auth", "ssl_verify", "verify", "language", "stream"]:
            req_kwargs.pop(key, None)
        cookies = req_kwargs.pop("cookies", None)
        if cookies:
            cookies = dict(cookies)  # in case list of tuples
            for name, value in cookies.items():
                app.set_cookie(name, value)
        # although headers for JSON content can be set, some methods are not working (eg: PUT)
        # obtain the corresponding '<method>_json' function to have the proper behaviour
        headers = req_kwargs.get("headers", {}) or {}
        if (
            (get_header("Content-Type", headers) == CONTENT_TYPE_APP_JSON or isinstance(content, (dict, list)))
            and hasattr(app, method + "_json")
        ):
            method = method + "_json"
            if isinstance(content, str):
                req_kwargs["params"] = json.loads(req_kwargs["params"])
        req = getattr(app, method)
        return url, req, req_kwargs

    def _patch_response_methods(response, url):
        if not hasattr(response, "content"):
            setattr(response, "content", response.body)
        if not hasattr(response, "reason"):
            setattr(response, "reason", response.errors)
        if not hasattr(response, "raise_for_status"):
            setattr(response, "raise_for_status", lambda: Response.raise_for_status(response))
        if getattr(response, "url", None) is None:
            setattr(response, "url", url)

    def mocked_app_request(method, url=None, session=None, **req_kwargs):
        """
        Mock requests under the web test application under specific conditions.

        Request corresponding to :func:`requests.request` that instead gets executed by :class:`webTest.TestApp`,
        unless permitted to call real external requests.
        """
        # if URL starts with '/' directly, it is the shorthand path for this test app, always mock
        # otherwise, filter according to full URL hostname
        url_test_app = get_weaver_url(app.app.registry)
        if only_local and not url.startswith("/") and not url.startswith(url_test_app):
            with session or RealSession() as request_session:
                return real_request(request_session, method, url, **req_kwargs)

        url, func, req_kwargs = _parse_for_app_req(method, url, **req_kwargs)
        redirects = req_kwargs.pop("allow_redirects", True)
        if url.startswith("mock://"):
            path = get_url_without_query(url.replace("mock://", ""))
            _resp = mocked_file_response(path, url)
        else:
            _resp = func(url, expect_errors=True, **req_kwargs)
        if redirects:
            # must handle redirects manually with TestApp
            while 300 <= _resp.status_code < 400:
                _resp = _resp.follow()
        _patch_response_methods(_resp, url)
        return _resp

    # Patch TestResponse json 'property' into method to align with code that calls 'requests.Response.json()'.
    # Must be done with class mock because TestResponse json property cannot be overridden in '_patch_response_methods'.
    class TestResponseJsonCallable(TestResponse):
        def json(self):  # pylint: disable=W0236,invalid-overridden-method  # mismatch property/method is intentional
            return self.json_body

    # ensure that previously created session object is passed to the mocked sub-request to consider
    # any configured adapters, such as the 'file://' adapter added by 'request_extra' (within '_request_call')
    class TestSession(RealSession):
        def request(self, *req_args, **req_kwargs):
            return mocked_app_request(*req_args, **req_kwargs, session=self)

    # permit schema validation against 'mock' scheme during test only
    mock_file_regex = mock.PropertyMock(return_value=colander.Regex(r"^((file|mock)://)?(?:/|[/?]\S+)$"))
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("requests.request", side_effect=mocked_app_request))
        stack.enter_context(mock.patch("requests.Session.request", new=TestSession.request))
        stack.enter_context(mock.patch("requests.sessions.Session.request", new=TestSession.request))
        stack.enter_context(mock.patch.object(FileLocal, "validator", new_callable=mock_file_regex))
        stack.enter_context(mock.patch.object(TestResponse, "json", new=TestResponseJsonCallable.json))
        req_url, req_func, kwargs = _parse_for_app_req(method_function, *args, **kwargs)
        kwargs.setdefault("expect_errors", True)
        resp = req_func(req_url, **kwargs)
        _patch_response_methods(resp, req_url)
        return resp


def mocked_remote_wps(processes, languages=None):
    # type: (List[Union[ProcessPyWPS, ProcessOWSWPS]], Optional[List[str]]) -> Iterable[MockPatch]
    """
    Mocks creation of a :class:`WebProcessingService` with provided :paramref:`processes` and returns them directly.
    """
    class MockProcesses(mock.PropertyMock):
        pass

    class MockLanguages(mock.PropertyMock):
        pass

    lang = Languages([])
    lang.supported = languages or []
    mock_processes = MockProcesses
    mock_processes.return_value = processes
    mock_languages = MockLanguages
    mock_languages.return_value = lang
    return (
        mock.patch.object(WebProcessingService, "getcapabilities", side_effect=lambda *args, **kwargs: None),
        mock.patch.object(WebProcessingService, "processes", new_callable=mock_processes, create=True),
        mock.patch.object(WebProcessingService, "languages", new_callable=mock_languages, create=True),
    )


def mocked_remote_server_requests_wps1(server_configs,          # type: Union[MockConfigWPS1, Sequence[MockConfigWPS1]]
                                       mock_responses=None,     # type: Optional[responses.RequestsMock]
                                       data=False,              # type: bool
                                       ):                       # type: (...) -> Optional[MockPatch]
    """
    Mocks *remote* WPS-1 requests/responses with specified XML contents from local test resources in returned body.

    Can be employed as function decorator or direct function call with an existing :class:`RequestsMock` instance.

    .. seealso::
        ``tests/resources`` directory for available XML files to simulate response bodies.

    Single Server Mock example:

    .. code-block:: python

        @mocked_remote_server_requests_wps1(
            [ "<server-url>", "<getcaps-xml-path>", ["<describe-xml-file1>", "<describe-xml-file2>", ...] ]
        )
        def test_function():
            pass

    Multi-Server Mock example:

    .. code-block:: python

        @mocked_remote_server_requests_wps1(
            [
                [ "<server-url-1>", "<getcaps-xml-path>", ["<describe-xml-file1>", "<describe-xml-file2>", ...] ],
                [ "<server-url-2>", "<getcaps-xml-path>", ["<describe-xml-file1>", "<describe-xml-file2>", ...] ],
            ]
        )
        def test_function():
            pass

    The generated responses mock can be obtained as follows to add further request definitions to simulate:

    .. code-block:: python

        @mocked_remote_server_requests_wps1([...])
        def test_function(mock_responses):
            mock_responses.add("GET", "http://other.com", body="data", headers={"Content-Type": "text/plain"})
            # Call requests here, both provided WPS and above requests will be mocked.

    The generated responses mock can also be passed back into the function to register further WPS services with
    similar handling as the decorator to register relavant requests based on provided server configurations.

    .. code-block:: python

        @mocked_remote_server_requests_wps1([<config-server-2>])
        def test_function(mock_responses):
            mocked_remote_server_requests_wps1([<config-server-2>], mocked_responses)
            # call requests for both server-1 and server-2 configurations

    :param server_configs:
        Single level or nested 2D list/tuples of 3 elements, where each one defines:
            1. WPS server URL to be mocked to simulate response contents from requests for following items.
            2. Single XML file path to the expected response body of a server ``GetCapabilities`` request.
            3. List of XML file paths to one or multiple expected response body of ``DescribeProcess`` requests.
    :param mock_responses:
        Handle to the generated mock instance by this decorator on the first wrapped call to add more configurations.
        In this case, wrapper function is not returned.
    :param data:
        Flag indicating that provided strings are the literal data instead of file references.
        All server configurations must be file OR data references, no mixing between them supported.
    :returns: wrapper that mocks multiple WPS-1 servers and their responses with provided processes and XML contents.
    """

    def get_xml(ref):
        if data:
            return ref
        with open(ref, "r") as file:
            return file.read()

    all_request = set()
    if not isinstance(server_configs[0], (tuple, list)):
        server_configs = [server_configs]

    for test_server_wps, resource_xml_getcap, resource_xml_describe in server_configs:
        assert isinstance(resource_xml_getcap, str)
        assert isinstance(resource_xml_describe, (set, list, tuple))
        if not data:
            assert os.path.isfile(resource_xml_getcap)
            assert all(os.path.isfile(file) for file in resource_xml_describe)

        get_cap_xml = get_xml(resource_xml_getcap)
        version_query = "&version=1.0.0"
        get_cap_url = "{}?service=WPS&request=GetCapabilities".format(test_server_wps)
        all_request.add((responses.GET, get_cap_url, get_cap_xml))
        all_request.add((responses.GET, get_cap_url + version_query, get_cap_xml))
        for proc_desc_xml in resource_xml_describe:
            describe_xml = get_xml(proc_desc_xml)
            # assume process ID is always the first identifier (ignore input/output IDs after)
            proc_desc_id = re.findall("<ows:Identifier>(.*)</ows:Identifier>", describe_xml)[0]
            proc_desc_url = "{}?service=WPS&request=DescribeProcess&identifier={}".format(test_server_wps, proc_desc_id)
            all_request.add((responses.GET, proc_desc_url, describe_xml))
            all_request.add((responses.GET, proc_desc_url + version_query, describe_xml))
            # special case where 'identifier' gets added to 'GetCapabilities', but is simply ignored
            getcap_with_proc_id_url = proc_desc_url.replace("DescribeProcess", "GetCapabilities")
            all_request.add((responses.GET, getcap_with_proc_id_url, get_cap_xml))
            all_request.add((responses.GET, getcap_with_proc_id_url + version_query, get_cap_xml))

    def apply_mocks(_mock_resp, _requests):
        xml_header = {"Content-Type": CONTENT_TYPE_APP_XML}
        for meth, url, body in _requests:
            _mock_resp.add(meth, url, body=body, headers=xml_header)

    def mocked_remote_server_wrapper(test):
        @functools.wraps(test)
        def mock_requests_wps1(*args, **kwargs):
            """
            Mock ``requests`` responses fetching ``test_server_wps`` WPS reference.
            """
            sig = inspect.signature(test)
            sig_has_mock = len(sig.parameters) > (1 if "self" in sig.parameters else 0)

            with responses.RequestsMock(assert_all_requests_are_fired=False) as mock_resp:
                apply_mocks(mock_resp, all_request)
                if not sig_has_mock:
                    return test(*args, **kwargs)
                return test(*args, mock_resp, **kwargs)  # inject mock if parameter for it is available
        return mock_requests_wps1

    if mock_responses is not None:
        apply_mocks(mock_responses, all_request)
        return

    return mocked_remote_server_wrapper


def mocked_wps_output(settings, mock_get=True, mock_head=True):
    # type: (SettingsType, bool, bool) -> Union[responses.RequestsMock, MockPatch]
    """
    Mocks the mapping resolution from HTTP WPS output URL to hosting of matched local file in WPS output directory.

    .. warning::
        When combined in a test where :func:`mocked_sub_requests` is employed, parameter ``local_only=True`` must be
        provided. Otherwise, this mocked response will never be reached since HTTP requests themselves would be mocked
        beforehand by a :class:`TestApp` request.

    :param settings: Application settings to retrieve WPS output configuration.
    :param mock_get: Whether to mock HTTP GET methods received on WPS output URL.
    :param mock_head: Whether to mock HTTP HEAD methods received on WPS output URL.
    :return: Mocked response that would normally be obtained by a file server hosting WPS output directory.
    """
    wps_output_url = get_wps_output_url(settings)

    def request_callback(request):
        # type: (AnyRequestType) -> Tuple[int, Dict[str, str], str]
        wps_out_file = map_wps_output_location(request.url, settings, exists=True, file_scheme=True)
        if wps_out_file and (mock_head and request.method == "HEAD") or (mock_get and request.method == "GET"):
            resp = request_extra(request.method, wps_out_file, settings=settings)
            if request.method == "HEAD" and resp.status_code == 200:
                wps_output_file_path = wps_out_file.replace("file://", "")
                mime_type, encoding = mimetypes.guess_type(wps_output_file_path)
                headers = {
                    "Server": "mocked_wps_output",
                    "Date": str(datetime.datetime.utcnow()),
                    "Content-Type": mime_type or CONTENT_TYPE_TEXT_PLAIN,
                    "Content-Encoding": encoding or "",
                    "Content-Length": str(resp.headers.get("Content-Length", len(resp.content))),
                    "Last-Modified": str(datetime.datetime.fromtimestamp(os.stat(wps_output_file_path).st_mtime))
                }
                return 200, headers, ""
            return resp.status_code, resp.headers, resp.content
        elif wps_out_file:
            return 405, {}, ""
        return 404, {}, ""

    mock_req = responses.RequestsMock(assert_all_requests_are_fired=False)
    any_wps_output_url = re.compile(r"{}/[\w\-_/.]+".format(wps_output_url))  # match any sub-directory/file structure
    if mock_get:
        mock_req.add_callback(responses.GET, any_wps_output_url, callback=request_callback)
    if mock_head:
        mock_req.add_callback(responses.HEAD, any_wps_output_url, callback=request_callback)
    return mock_req


def mocked_execute_process():
    # type: () -> Iterable[MockPatch]
    """
    Contextual mock of a process execution to run locally instead of dispatched :mod:`celery` worker.

    Provides a mock to call :func:`weaver.processes.execution.execute_process` safely within a test
    employing :class:`webTest.TestApp` without a running ``Celery`` app.
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
        Mocks the Celery Task for testing.

        Mocks call ``self.request.id`` in :func:`weaver.processes.execution.execute_process` and
        call ``result.id`` in :func:`weaver.processes.execution.submit_job_handler`.

        .. note::
            Parameter ``self.request`` in this context is the Celery Task handle, not to be confused with HTTP request.
        """
        _id = str(uuid.uuid4())

        @property
        def id(self):
            return self._id

    task = MockTask()

    def mock_execute_process(job_id, wps_url, headers):
        real_execute_process(job_id, wps_url, headers)
        return task

    return (
        mock.patch("weaver.processes.execution.execute_process.delay", side_effect=mock_execute_process),
        mock.patch("celery.app.task.Context", return_value=task)
    )


@contextlib.contextmanager
def mocked_dismiss_process():
    """
    Mock operations called to terminate :mod:`Celery` tasks.

    Can be used either as decorator or context.
    """
    mock_celery_app = mock.MagicMock()
    mock_celery_app.control = mock.MagicMock()
    mock_celery_app.control.revoke = mock.MagicMock()
    mock_celery_revoke = mock.patch("weaver.wps_restapi.jobs.jobs.celery_app", return_value=mock_celery_app)

    try:
        with mock_celery_revoke:
            yield   # for direct use by context or decorator
    finally:
        return mock_celery_revoke  # for use by combined ExitStack context  # pylint: disable=W0150.lost-exception


def mocked_process_job_runner(job_task_id="mocked-job-id"):
    # type: (str) -> Iterable[MockPatch]
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
    # type: () -> Iterable[MockPatch]
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
    # type: (Callable[[...], Any]) -> Callable
    """
    Mocked AWS Credentials for :py:mod:`moto`.

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
    # type: (Callable[[...], Any]) -> Callable
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
    Mock a test file as if retrieved from an AWS-S3 bucket reference.

    Generates a test file reference from dummy data that will be uploaded to the specified S3 bucket name using the
    provided file key. The S3 interface employed is completely dependent of the wrapping context. For instance,
    calling this function with :func:`mocked_aws_s3` decorator will effectively employ the mocked S3 interface.

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


def mocked_http_file(test_func):
    # type: (Callable[[...], Any]) -> Callable
    """
    Creates a mock of the function :func:`fetch_file`, to fetch a generated file locally, for test purposes only.

    For instance, calling this function with :func:`mocked_http_file` decorator
    will effectively employ the mocked :func:`fetch_file` and return a generated local file.

    .. seealso::
        - :func:`mocked_reference_test_file`
    """
    def mocked_file_request(file_reference, file_outdir, **kwargs):
        if file_reference and file_reference.startswith(MOCK_HTTP_REF):
            file_reference = file_reference.replace(MOCK_HTTP_REF, "")
        file_path = fetch_file(file_reference, file_outdir, **kwargs)
        return file_path

    def wrapped(*args, **kwargs):
        with mock.patch("weaver.processes.wps_package.fetch_file", side_effect=mocked_file_request):
            return test_func(*args, **kwargs)
    return wrapped


def mocked_reference_test_file(file_name, href_type, file_content="This is a generated file for href test"):
    # type: (str,str,str) -> str
    """
    Generates a test file reference from dummy data for http and file href types.

    .. seealso::
        - :func:`mocked_http_file`
    """
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, file_name)
    with open(path, "w") as tmp_file:
        tmp_file.write(file_content)
    return "file://{}".format(path) if href_type == "file" else os.path.join(MOCK_HTTP_REF, path)
