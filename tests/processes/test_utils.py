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
from weaver.processes.constants import CWL_REQUIREMENT_APP_WPS1
from weaver.processes.utils import register_wps_processes_from_config

WPS1_URL1 = resources.TEST_REMOTE_SERVER_URL
WPS1_URL2 = "http://yet-another-server.com"
WPS1_URL3 = "http://one-more-server.com"
WPS1_URL4 = "http://emu-server.com"


def test_register_wps_processes_from_config_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("Empty file should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("processes:\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("File with empty 'processes' section should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("providers:\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config(f.name, {})
        except Exception:  # noqa
            pytest.fail("File with empty 'providers' section should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("providers:\nprocesses:\n")
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


# a few servers are needed because matching URLs generating inferred names with conflict entries will be dropped
@pytest.mark.slow  # because of XML parsing, convert and registration of many Weaver providers/processes
@pytest.mark.functional
@mocked_remote_server_requests_wps1([
    # has 1 process listed
    (WPS1_URL1, resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML, [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML]),
    # has 1 process listed
    (WPS1_URL2, resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML, [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML]),
    # has 1 process listed
    (WPS1_URL3, resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML, [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML]),
    # has 11 processes listed
    # although they don't match processes in GetCaps, simulate fetching only those directly so we can omit real ones
    (WPS1_URL4, resources.WPS_CAPS_EMU_XML, [resources.WPS_ENUM_ARRAY_IO_XML, resources.WPS_LITERAL_COMPLEX_IO_XML]),
])
def test_register_wps_processes_from_config_valid():
    """
    Validate the different combinations of supported remote WPS-1 processes and providers specifications.
    """
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_path": "/ows/wps",
        # define some options to avoid useless retry/timeout
        # everything is mocked and should return immediately
        "weaver.request_options": {
            "requests": [
                {"url": WPS1_URL1, "method": "get", "timeout": 1, "retry": 0}
            ]
        }
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
                {"name": "test-explicit-name", "url": WPS1_URL3},
            ],
            # static processes, all the ones under service are registered explicitly, unless filtered
            "processes": [
                WPS1_URL1,
                # direct URL string, has only 1 process that will be retrieved by DescribeProcess 'iteratively'
                # the 'GetCapabilities' provides which processes to iterate over
                resources.GET_CAPABILITIES_TEMPLATE_URL.format(WPS1_URL2),
                # following will call DescribeProcess
                resources.DESCRIBE_PROCESS_TEMPLATE_URL.format(WPS1_URL3, resources.TEST_REMOTE_PROCESS_WPS1_ID),
                # same as GetCapabilities with iteration on available processes with DescribeProcess,
                # but will replace the default server name by the provided one (so can reuse same URL)
                {"name": "test-static-process", "url": WPS1_URL1},
                # directly call DescribeProcess bypassing the GetCapabilities
                {"name": "test-filter-process", "url": WPS1_URL4,
                 # should only fetch following two rather than the 11 (fake) ones reported by GetCapabilities
                 "id": [resources.WPS_ENUM_ARRAY_IO_ID, resources.WPS_LITERAL_COMPLEX_IO_ID]}
            ]
        }, f)

        try:
            # note:
            #   can take some time to process since OWSLib must parse all GetCapabilities/DescribeProcesses responses
            register_wps_processes_from_config(f.name, config)
        except Exception:  # noqa
            pytest.fail("Valid definitions in configuration file should not raise any error")

    # validate results
    processes = p_store.list_processes()
    providers = s_store.list_services()

    # generate equivalent of inferred named (simplified)
    infer_name1 = WPS1_URL1.rsplit("://", 1)[-1].replace(".com", "_com")
    infer_name2 = WPS1_URL2.rsplit("://", 1)[-1].replace(".com", "_com")
    infer_name3 = WPS1_URL3.rsplit("://", 1)[-1].replace(".com", "_com")

    # dynamic provider inferred names are sanitized/slug of URL
    assert len(providers) == 3, "Number of dynamic WPS-1 providers registered should match number from file."
    svc1 = s_store.fetch_by_name(infer_name1)
    assert svc1.url == WPS1_URL1
    svc2 = s_store.fetch_by_name(infer_name2)
    assert svc2.url == WPS1_URL2
    svc3 = s_store.fetch_by_name("test-explicit-name")
    assert svc3.url == WPS1_URL3

    # (1) first server has 1 process in GetCapabilities, the basic URL registers only that process
    # (1) second server also has 1 process, but GetCapabilities queries already in the URL are cleaned up
    # (1) third directly references the DescribeProcess request, so it is fetched directly
    # (1) fourth entry is the same as first, just using another name
    # (2) fifth entry provided 2 processes ID explicitly. Although 11 processes are available, only those 2 are created.
    assert len(processes) == 6, "Number of static remote WPS-1 processes registered should match number from file."

    # static processes inferred names are a concatenation of the URL sanitized/slug + process-ID
    proc1_id = infer_name1 + "_" + resources.TEST_REMOTE_PROCESS_WPS1_ID
    proc1 = p_store.fetch_by_id(proc1_id)
    assert proc1.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL1 + "/"
    assert proc1.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
    proc2_id = infer_name2 + "_" + resources.TEST_REMOTE_PROCESS_WPS1_ID
    proc2 = p_store.fetch_by_id(proc2_id)
    assert proc2.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL2 + "/"
    assert proc2.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
    proc3_id = infer_name3 + "_" + resources.TEST_REMOTE_PROCESS_WPS1_ID
    proc3 = p_store.fetch_by_id(proc3_id)
    assert proc3.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL3 + "/"
    assert proc3.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
    # although an explicit name is provided, the URL point to generic GetCapabilities
    # therefore, multiple processes *could* be registered, which require same server-name+process-id concat as above
    proc4_id = "test-static-process_" + resources.TEST_REMOTE_PROCESS_WPS1_ID
    proc4 = p_store.fetch_by_id(proc4_id)
    assert proc4.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL1 + "/"
    assert proc4.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
    # last server is the same, but specific IDs are given
    # still, concat happens to avoid conflicts against multiple servers sharing process-IDs, although distinct
    proc5_id = "test-filter-process_" + resources.WPS_ENUM_ARRAY_IO_ID
    proc5 = p_store.fetch_by_id(proc5_id)
    assert proc5.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL4 + "/"
    assert proc5.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.WPS_ENUM_ARRAY_IO_ID
    proc6_id = "test-filter-process_" + resources.WPS_LITERAL_COMPLEX_IO_ID
    proc6 = p_store.fetch_by_id(proc6_id)
    assert proc6.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL4 + "/"
    assert proc6.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.WPS_LITERAL_COMPLEX_IO_ID
