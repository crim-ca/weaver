import tempfile
import pytest
import yaml

from tests import resources
from tests.utils import (
    mocked_remote_server_requests_wps1,
    setup_config_with_mongodb,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver.processes.utils import register_wps_processes_from_config

WPS1_URL1 = resources.TEST_REMOTE_SERVER_URL
WPS1_URL2 = "http://yet-another-server.com"
WPS1_URL3 = "http://emu-server.com"


def test_register_wps_processes_from_config_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write('\n')
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("Empty file should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write('processes:\n')
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("File with empty 'processes' section should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write('providers:\n')
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("File with empty 'providers' section should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write('providers:\nprocesses:\n')
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("File with empty 'providers' and 'processes' sections should not raise any error")


def test_register_wps_processes_from_config_missing():
    try:
        register_wps_processes_from_config("/this/path/des/not/exist", {})
    except Exception:  # noqa
        pytest.fail("Path pointing to missing file should not raise any error")


@mocked_remote_server_requests_wps1([
    # has 1 process listed
    (WPS1_URL1, resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML, [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML]),
    # has 1 process listed
    (WPS1_URL2, resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML, [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML]),
    # has 11 processes listed
    # although they don't match processes in GetCaps, simulate fetching only those directly so we can omit real ones
    (WPS1_URL3, resources.WPS_CAPS_EMU_XML, [resources.WPS_ENUM_ARRAY_IO_XML, resources.WPS_LITERAL_COMPLEX_IO_XML]),
])
def test_register_wps_processes_from_config_valid():
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_path": "/ows/wps",
    }
    config = setup_config_with_mongodb(settings=settings)
    p_store = setup_mongodb_processstore(config)
    s_store = setup_mongodb_servicestore(config)
    p_store.clear_processes()
    s_store.clear_services()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        yaml.safe_dump({
            # dynamic processes, only register provider explicitly, processes fetched on demand
            "providers": [
                WPS1_URL1,  # direct URL string
                {"url": WPS1_URL2},  # implicit name, but as dict
                {"name": "test-explicit-name", "url": WPS1_URL1},
            ],
            # static processes, all the ones under service are registered explicitly, unless filtered
            "processes": [
                WPS1_URL1,
                # direct URL string, has only 1 process that will be retrieved by DescribeProcess 'iteratively'
                # the 'GetCapabilities' provides which processes to iterate over
                resources.GET_CAPABILITIES_TEMPLATE_URL.format(WPS1_URL1),
                # following will call DescribeProcess
                resources.DESCRIBE_PROCESS_TEMPLATE_URL.format(WPS1_URL2, resources.TEST_REMOTE_PROCESS_WPS1_ID),
                # same as GetCapabilities with iterate on available processes with DescribeProcess,
                # but will replace the default server name by the provided one
                {"name": "test-static-process", "url": WPS1_URL2},
                # directly call DescribeProcess bypassing the GetCapabilities
                {"name": "test-filter-process", "url": WPS1_URL3,
                 # should only fetch following two rather than the 11 (fake) ones reported by GetCapabilities
                 "id": [resources.WPS_ENUM_ARRAY_IO_XML, resources.WPS_LITERAL_COMPLEX_IO_XML]}
            ]
        }, f)

        try:
            register_wps_processes_from_config(f.name, config)
        except Exception:  # noqa
            pytest.fail("Valid definitions in configuration file should not raise any error")

    # validate results
    processes = p_store.list_processes()
    providers = s_store.list_services()

    assert len(providers) == 3
    infer_name1 = resources.TEST_REMOTE_SERVER_URL.split("://")[-1]
    svc_1 = s_store.fetch_by_name(infer_name1)
    assert svc_1.url == WPS1_URL1
    infer_name2 = WPS1_URL2.split("://")[-1]
    svc_2 = s_store.fetch_by_name(infer_name2)
    assert svc_2.url == WPS1_URL2
    svc_3 = s_store.fetch_by_name("test-explicit-name")
    assert svc_3.url == WPS1_URL1

    # each fake server has 1 process listed in GetCapabilities
    assert len(processes) == 5

