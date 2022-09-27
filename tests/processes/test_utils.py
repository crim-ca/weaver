import json
import os
import sys
import tempfile

import mock
import pytest
import yaml

from tests import resources
from tests.utils import (
    mocked_remote_server_requests_wps1,
    setup_config_with_mongodb,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver.exceptions import PackageRegistrationError
from weaver.processes.constants import CWL_REQUIREMENT_APP_WPS1
from weaver.processes.utils import _check_package_file  # noqa: W0212
from weaver.processes.utils import register_cwl_processes_from_config, register_wps_processes_from_config

WPS1_URL1 = resources.TEST_REMOTE_SERVER_URL
WPS1_URL2 = "http://yet-another-server.com"
WPS1_URL3 = "http://one-more-server.com"
WPS1_URL4 = "http://emu-server.com"


class MockResponseOk(object):
    status_code = 200


def test_check_package_file_with_url():
    package_url = "https://example.com/package.cwl"
    with mock.patch("requests.Session.request", return_value=MockResponseOk()) as mock_request:
        res_path = _check_package_file(package_url)
        assert mock_request.call_count == 1
        assert mock_request.call_args[0][:2] == ("head", package_url)  # ignore extra args
    assert res_path == package_url


def test_check_package_file_with_file_scheme():
    with mock.patch("requests.Session.request", return_value=MockResponseOk()) as mock_request:
        with tempfile.NamedTemporaryFile(mode="r", suffix="test-package.cwl") as tmp_file:
            package_file = f"file://{tmp_file.name}"
            res_path = _check_package_file(package_file)
            mock_request.assert_not_called()
            assert res_path == tmp_file.name


def test_check_package_file_with_posix_path():
    with tempfile.NamedTemporaryFile(mode="r", suffix="test-package.cwl") as tmp_file:
        res_path = _check_package_file(tmp_file.name)
        assert res_path == tmp_file.name


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Test for Windows only")
def test_check_package_file_with_windows_path():
    test_file = "C:/Windows/Temp/package.cwl"   # fake existing, just test format handled correctly
    with mock.patch("os.path.isfile", return_value=True) as mock_isfile:
        res_path = _check_package_file(test_file)
        mock_isfile.assert_called_with(test_file)
    assert res_path == test_file


def test_register_wps_processes_from_config_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config({}, f.name)
        except Exception:  # noqa
            pytest.fail("Empty file should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("processes:\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config({}, f.name)
        except Exception:  # noqa
            pytest.fail("File with empty 'processes' section should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("providers:\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config({}, f.name)
        except Exception:  # noqa
            pytest.fail("File with empty 'providers' section should not raise any error")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write("providers:\nprocesses:\n")
        f.flush()
        f.seek(0)
        try:
            register_wps_processes_from_config({}, f.name)
        except Exception:  # noqa
            pytest.fail("File with empty 'providers' and 'processes' sections should not raise any error")


def test_register_wps_processes_from_config_omitted():
    with mock.patch("weaver.processes.utils.register_wps_processes_static") as mocked_static:
        with mock.patch("weaver.processes.utils.register_wps_processes_dynamic") as mocked_dynamic:
            assert register_wps_processes_from_config({"weaver.wps_processes_file": ""}) is None
            assert not mocked_static.called
            assert not mocked_dynamic.called


def test_register_wps_processes_from_config_missing():
    try:
        register_wps_processes_from_config({}, "/this/path/des/not/exist")
    except Exception:  # noqa
        pytest.fail("Path pointing to missing file should not raise any error")


# a few servers are needed because matching URLs generating inferred names with conflict entries will be dropped
@pytest.mark.slow  # because of XML parsing, convert and registration of many Weaver providers/processes
@pytest.mark.functional
@mocked_remote_server_requests_wps1([
    # has 1 process listed
    (WPS1_URL1, resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML]),
    # has 1 process listed
    (WPS1_URL2, resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML]),
    # has 1 process listed
    (WPS1_URL3, resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML]),
    # has 11 processes listed
    # although they don't match processes in GetCaps, simulate fetching only those directly so we can omit real ones
    (WPS1_URL4, resources.TEST_EMU_WPS1_GETCAP_XML, [
        resources.WPS_ENUM_ARRAY_IO_XML, resources.WPS_LITERAL_COMPLEX_IO_XML
    ]),
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
                resources.DESCRIBE_PROCESS_TEMPLATE_URL.format(WPS1_URL3, resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID),
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
            register_wps_processes_from_config(config, f.name)
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
    proc1_id = infer_name1 + "_" + resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    proc1 = p_store.fetch_by_id(proc1_id)
    assert proc1.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL1 + "/"
    assert proc1.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    proc2_id = infer_name2 + "_" + resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    proc2 = p_store.fetch_by_id(proc2_id)
    assert proc2.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL2 + "/"
    assert proc2.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    proc3_id = infer_name3 + "_" + resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    proc3 = p_store.fetch_by_id(proc3_id)
    assert proc3.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL3 + "/"
    assert proc3.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    # although an explicit name is provided, the URL point to generic GetCapabilities
    # therefore, multiple processes *could* be registered, which require same server-name+process-id concat as above
    proc4_id = "test-static-process_" + resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
    proc4 = p_store.fetch_by_id(proc4_id)
    assert proc4.package["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] == WPS1_URL1 + "/"
    assert proc4.package["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
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


def test_register_cwl_processes_from_config_undefined():
    assert register_cwl_processes_from_config({}) == 0


def test_register_cwl_processes_from_config_empty_var():
    settings = {"weaver.cwl_processes_dir": ""}
    assert register_cwl_processes_from_config(settings) == 0


def test_register_cwl_processes_from_config_not_a_dir():
    with tempfile.NamedTemporaryFile(mode="w") as tmp_file:
        tmp_file.write("data")

        settings = {"weaver.cwl_processes_dir": tmp_file.name}
        assert register_cwl_processes_from_config(settings) == 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = os.path.join(tmp_dir, "does-not-exist")
        settings = {"weaver.cwl_processes_dir": tmp_dir}
        assert register_cwl_processes_from_config(settings) == 0


def test_register_cwl_processes_from_config_dir_no_cwl():
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = {"weaver.cwl_processes_dir": tmp_dir}
        assert register_cwl_processes_from_config(settings) == 0

        with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".json", mode="w", delete=False) as tmp_file:
            tmp_file.write(json.dumps({"data": "test"}))

        assert register_cwl_processes_from_config(settings) == 0


def test_register_cwl_processes_from_config_load_recursive():
    from weaver.processes.utils import load_package_file as real_load_pkg_file

    with tempfile.TemporaryDirectory() as tmp_dir:
        first_dir = os.path.join(tmp_dir, "first")
        nested_dir = os.path.join(tmp_dir, "nested")
        deeper_dir = os.path.join(nested_dir, "deeper")
        os.makedirs(first_dir)
        os.makedirs(deeper_dir)

        # Write files in **un**ordered fashion to validate ordered loading occurs:
        # /tmp
        #   /dir
        #     file3.cwl
        #     random.yml
        #     file5.cwl
        #     /first
        #       b_file9.cwl         # note: must appear before file2 and a_file8, 'nested' loaded after 'first'
        #       file2.cwl
        #       invalid.cwl
        #     /nested
        #       a_file8.cwl         # note: must appear after file2 and b_file9, 'nested' loaded after 'first'
        #       random.json
        #       file1.cwl
        #       file4.cwl
        #       /deeper
        #         c_file7.cwl
        #         file0.cwl
        #         file6.cwl
        #         invalid.cwl
        #
        # Loaded order:
        #   /tmp/dir/file3.cwl
        #   /tmp/dir/file5.cwl
        #   /tmp/dir/first/b_file9.cwl
        #   /tmp/dir/first/file2.cwl
        #   /tmp/dir/nested/a_file8.cwl
        #   /tmp/dir/nested/file1.cwl               # note:
        #   /tmp/dir/nested/file4.cwl               dir 'deeper' purposely named to appear before
        #   /tmp/dir/nested/deeper/file0.cwl        'file#' one level above if they were sorted *only*
        #   /tmp/dir/nested/deeper/file6.cwl        alphabetically not considering directory structure
        valid_order = [3, 5, 9, 2, 8, 1, 4, 7, 0, 6]
        # doest not need to be valid CWL, mocked loading
        cwl_ordered = [{"cwlVersion": "v1.0", "id": str(i)} for i in range(len(valid_order))]
        with open(os.path.join(tmp_dir, "file3.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[3]))
        with open(os.path.join(tmp_dir, "file5.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[5]))
        with open(os.path.join(tmp_dir, "random.yml"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write("random: data")
        with open(os.path.join(first_dir, "file2.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[2]))
        with open(os.path.join(first_dir, "invalid.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps({"invalid": True}))
        with open(os.path.join(first_dir, "b_file9.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[9]))
        with open(os.path.join(nested_dir, "file1.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[1]))
        with open(os.path.join(nested_dir, "file4.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[4]))
        with open(os.path.join(nested_dir, "random.json"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps({"random": "data"}))
        with open(os.path.join(nested_dir, "a_file8.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[8]))
        with open(os.path.join(deeper_dir, "c_file7.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[7]))
        with open(os.path.join(deeper_dir, "file0.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[0]))
        with open(os.path.join(deeper_dir, "file6.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(cwl_ordered[6]))
        with open(os.path.join(deeper_dir, "invalid.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps({"invalid": True}))

        def no_op_valid(_cwl, *_, **__):  # type: ignore
            if isinstance(_cwl, dict) and "invalid" in _cwl:
                raise PackageRegistrationError("CWL INVALID")

        with mock.patch("weaver.processes.utils.deploy_process_from_payload", side_effect=no_op_valid) as mocked_deploy:
            with mock.patch("weaver.processes.utils.load_package_file", side_effect=real_load_pkg_file) as mocked_load:
                settings = {"weaver.cwl_processes_dir": tmp_dir}
                assert register_cwl_processes_from_config(settings) == len(cwl_ordered)

        call_count = len(cwl_ordered)  # mock not called if invalid definition invalidated beforehand
        assert mocked_deploy.call_count == call_count
        assert mocked_load.call_count == call_count + 2  # 2 "invalid.cwl"
        valid_calls = list(call for call in mocked_load.call_args_list if "invalid" not in call.args[0])
        deploy_calls = mocked_deploy.call_args_list
        assert len(valid_calls) == len(cwl_ordered)
        assert len(valid_calls) == len(deploy_calls)
        for i, (order, call) in enumerate(zip(valid_order, deploy_calls)):
            assert call.args[0] == cwl_ordered[order], f"Expected CWL does not match load order at position: {i}"


def test_register_cwl_processes_from_config_error_handling():
    from weaver.processes.utils import load_package_file as real_load_pkg_file

    with tempfile.TemporaryDirectory() as tmp_dir:
        with open(os.path.join(tmp_dir, "ignore.cwl"), mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write("not important")

        def raise_deploy(*_, **__):
            raise PackageRegistrationError("test")

        with mock.patch("weaver.processes.utils.deploy_process_from_payload", side_effect=raise_deploy) as mock_deploy:
            with mock.patch("weaver.processes.utils.load_package_file", side_effect=real_load_pkg_file) as mock_load:
                settings = {"weaver.cwl_processes_dir": tmp_dir}
                assert register_cwl_processes_from_config(settings) == 0
                assert mock_deploy.call_count == 0, "Deploy should not be reached due to failed CWL pre-validation."
                assert mock_load.call_count == 1
        with mock.patch("weaver.processes.utils.deploy_process_from_payload", side_effect=raise_deploy) as mock_deploy:
            with mock.patch("weaver.processes.utils.load_package_file", side_effect=real_load_pkg_file) as mock_load:
                result = None  # noqa
                with pytest.raises(PackageRegistrationError):
                    settings["weaver.cwl_processes_register_error"] = "true"
                    result = register_cwl_processes_from_config(settings)
                assert mock_deploy.call_count == 0, "Deploy should not be reached due to failed CWL pre-validation."
                assert mock_load.call_count == 1
                assert result is None  # not returned
